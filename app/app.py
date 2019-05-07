#!/usr/bin/python
# -*- coding: utf-8 -*-

from functools import wraps  
from flask import Flask, request, jsonify, redirect, session, url_for
from werkzeug import exceptions as exc
import os
from openreq import OpenReq
from github import GitApp,GitError
import time
from flask_sqlalchemy import SQLAlchemy
#from sqlalchemy.exc import IntegrityError
from sqlalchemy import func
from celery import Celery


api = Flask(__name__)
api.config.from_pyfile('config.py', silent=True)


class AppNotInstalled(exc.HTTPException):
  description = "App not installed on this repository"

class ModelNotTrained(exc.HTTPException):
  description = "Train the model before you can use it"


git = GitApp(
  api.config['APP_ID'], 
  api.config['CLIENT_ID'], 
  api.config['CLIENT_SECRET'], 
  os.path.join(os.path.dirname(__file__), "private-key.pem")
)

if 'PERSONAL_ACCESS_TOKEN' in api.config:
  git.PERSONAL_ACCESS_TOKEN = api.config['PERSONAL_ACCESS_TOKEN']

opnr = OpenReq(api.config['OPENREQ_BASEURL'])

db = SQLAlchemy(api)

class Models(db.Model):
  repo = db.Column(db.String(100), primary_key=True)
  ready = db.Column(db.Boolean, default=False)
  created = db.Column(db.DateTime, server_default=db.func.now())
  updated = db.Column(db.DateTime, server_default=db.func.now(), server_onupdate=db.func.now())
  
  def __repr__(self):
    return '<Model %r ready %d>' % (self.name, self.ready)

class Trainings(db.Model):
  username = db.Column(db.String(100), primary_key=True)
  model = db.Column(db.String(100), primary_key=True)
  
  def __repr__(self):
    return '<Model %r associated to user %r>' % (self.model, self.username)

class Classifications(db.Model):
  username = db.Column(db.String(100))
  repo = db.Column(db.String(100), primary_key=True)
  model = db.Column(db.String(100))
  classified = db.Column(db.Boolean, default=False)
  
  def __repr__(self):
    return '<Classification of %r using model %r for user %r>' % (self.repo, self.model, self.username)

# check if db is created or create
db.create_all()


celery = Celery(api.name, broker=api.config['CELERY_BROKER_URL'])
celery.conf.update(api.config)

def authorized(f):
  @wraps(f)
  def decorator(*args, **kwargs):
    try:
      # check for revoked access_token
      git.getUser(session['access_token'])
    except Exception:
      return jsonify({
        'message': "Unauthorized request",
        'next': git.authorizeUrl(url_for('auth', _external=True))
      }),401
    
    return f(session['access_token'], *args, **kwargs)  
  return decorator

@api.route('/auth/', defaults={'next':'/'})
@api.route('/auth/<path:next>')
def auth(next):
  token = git.getAccessToken(request)
  
  if token:
    session['access_token'] = token
    user = git.getUser(token)
    session['user_id'] = user['login']
    return redirect(url_for('index', _external=True) + next)
  else: 
    return jsonify({
      'message': "Invalid authorization"
    }),401


@api.route("/")
def index():
  if 'access_token' in session:
    return "<a href='" + url_for('manage') + "' target='_blank'>Manage access to App</a>"
  return "Api for issue classification"


@api.route('/logout')
def logout():
  session.pop('access_token', None)
  session.pop('user_id', None)
  return redirect(url_for('index'))


@api.route('/manage')
def manage():
  """
    Take user to the app page where he can manage app permissions revokation
  """
  return redirect(git.appManagementUrl)


@api.route('/check-installed/<path:repo>')
def is_app_installed(repo):
  return jsonify(git.isInstalled(repo))
  

@api.route('/install')
def install():
  """
    Redirect user to the app main page where he can install the app or change configurations
  """
  return redirect(git.appPageUrl)


def _issuesToRequirements(issues, isForClassify = False):
  # requirements don't need 'requirement_type' when for classify 
  if isForClassify :
    return [ { 
      'id': issue['number'],
      'text': issue['body']
    } for issue in issues if 'pull_request' not in issue ]
  else:
    return [ { 
      'id': str(issue['number']) + "_" + str(label['id']),
      'requirement_type': label['name'],
      'text': issue['body']
    } for issue in issues if 'pull_request' not in issue for label in issue['labels'] ]

@celery.task
def _train(repo):
  company, property = repo.split("/")
  # retrieve issues for repo
  issues = git.getIssues(repo)
  # convert github issues to requirement
  requirements = _issuesToRequirements(issues)
  # call openreq api to train issues retrived
  opnr.train(company, property, requirements)
  # model is ready
  db.session.query(Models).filter(Models.repo==repo).update({'ready': True})
  db.session.commit() 


@api.route('/train')
@authorized
def train(token):
  """
    Train a model from a GIT repository using OpenReq API
    
    Parameters:
      repo  (string): a repository in the form owner/repo
    
    Results:
      return 200 if everything is OK
  """
  repo = request.args['repo']
  company, property = repo.split("/")
  
  requirements = []
  # check if repo has been trained calling openreq
  # check also if a training istance is in progress (within time limit) but not saved in openreq (using local db)
  model = db.session.query(Models).filter(Models.repo==repo).first()
  if opnr.exists(company, property):
    # model exists remotely but not match local view
    if not model or not model.ready:
      db.session.merge(Models(repo=repo, ready=True))
      db.session.commit()
  else:
    # model not exists but we have locally an attempt (timeout?) to training
    if model and not model.ready and (model.updated - model.created).seconds < 1800 :
      return jsonify({
        'message': 'Training in progress from previous call... please wait'
      }), 201
    else:
      # set training started in local db
      db.session.merge(Models(repo=repo, ready=False))
      db.session.commit()
      _train.delay(repo)
  
  try:
    # associate model to user
    db.session.merge(Trainings(model=repo, username=session['user_id']))
    db.session.commit()
  except Exception as e:
    return jsonify({
      'message': e.message
    }), 500
  
  return jsonify({
    'message': "Trained model has been associated to your userbase."
  })


def _cplabels(repo_from, repo_to, token):
  start = time.time()
  # delete existing labels to avoid duplicate errors
  git.rmLabels(repo_to, token)
  # get labels list from src repo
  labels = git.getLabels(repo_from, token)
  # copy labels to dest repo calling api
  for label in labels:
    try: 
      git.addLabel({ k:label.get(k,"") for k in ['name','color','description'] }, repo_to, token)
    except GitError:
      pass

@celery.task
def _classify(repo, model, issues = None, first=False):
  company, property = model.split("/")
  
  # check repo if user has installed app on and get installation token for successive calls to api
  try:
    token = git.getInstallationAccessToken(repo)
    if not token:
      raise AppNotInstalled()
  except GitError:
    raise AppNotInstalled()
  
  # check model if exists
  if not opnr.exists(company, property):
    raise ModelNotTrained()
  
  # copy label from model to repo if this is the first attempt
  if first :
    start = time.time() 
    _cplabels(model, repo, token)
  
  # retrieve issues for repo if not passed and convert to requirements
  if not issues:
    issues = git.getIssues(repo, token)
  requirements = _issuesToRequirements(issues, isForClassify=True)
  # call openreq api to classify repo based on model
  recommendations = opnr.classify(company, property, requirements)
    
  # write labels to issues on repo 
  """ 
    HACK: check if is right!!
    use requirements list instead of issues list for optimization purpose
    because req[id] = issue[number] 
    and get label directly from recommandations list pointing directly to item position with same key of requirement
  """
  for rec in recommendations:
    if rec['confidence'] > 50 :
      git.setLabels(repo, rec['requirement'], [rec['requirement_type']], token)
  
   # set repo as classified if on first batch classification
  if first :
    db.session.query(Classifications).filter(Classifications.repo==repo).update({'classified': True})
    db.session.commit()
  


@api.route('/classify')
@authorized
def classify(token):
  """
    Classify a repository using a model trained from another repository
    
    Parameters:
      repo  (string): a repository in the form owner/repo
      model (string): a model available on OpenReq server in the form company/property
    
    Results:
      return 200 if everything is OK
  """
  repo = request.args['repo']
  model = request.args['model'] 
  
  # check if repo is already classified with that model
  # XXX check if is good to avoid successive classification on the same model or need check for timeout classification
  classification = db.session.query(Classifications).filter(Classifications.repo == repo).first()
  if not classification or classification.model != model:
    db.session.merge(Classifications(repo=repo, model=model))
    db.session.commit()
    _classify.delay(repo, model, first=True)
    
    return jsonify({
      'message': "Classification scheduled successfully."
    })
  else:
    return jsonify({
      'message': "Repository has been classified already."
    })


@api.route("/myModels")
@authorized
def myModels(token):
  return jsonify([ t.model for t in Trainings.query.filter_by(username=session['user_id'])])


@api.route("/isOwner")
@authorized
def isOwner(repo):
  pass


@api.route("/webhook", methods = ['GET','POST'])
def webhook():
  data = request.get_json()
  # check for incoming issues
  if 'issue' in data and data['action'] in ['opened', 'edited']:
    # TODO security?? check data['installation']['id']
    issue = data['issue']
    repo = data['repository']['full_name']
    # username = data['sender']['login']
    # check if repo first classification has done
    # retrieve model associated to the repo
    classification = db.session.query(Classifications).filter(Classifications.repo == repo).first()
    if not classification or not classification.classified:
      return jsonify({
        'message': "No model associated to this repository or batch classification still in progress"
      }), 404
    
    _classify.delay(repo, classification.model, [issue])
    
    return jsonify({
      'message': "Issue classified."
    })
  
  return jsonify({
    'message': "nothing to do with this by now"
  }), 204 # CHECK may be a 501 is more proper

# test endpoints
  
@api.route("/limit")
@authorized
def limit(token):
  import requests
  
  limits = {}
  
  r = requests.get('https://api.github.com/rate_limit')
  limits['no_token'] = r.json()
  
  r = requests.get('https://api.github.com/rate_limit', headers={'Authorization': 'token ' + token})
  limits['auth_token'] = r.json()
  
  return jsonify(limits)
  #return jsonify([ x['full_name'] for x in r.json() ])

@api.route("/myrepos")
@authorized
def myrepos(token):
  import requests
  r = requests.get('https://api.github.com/app/installation/repositories'.format(username = session['user_id']), headers=git.jwtHeader)
  return jsonify(r.json())
  #return jsonify([ x['full_name'] for x in r.json() ])

@api.route("/exists")
@authorized
def exists(token):
  repo = request.args['repo']
  company, property = repo.split("/")
  return jsonify(opnr.exists(company, property))

@api.route("/issues")
@authorized
def issues(token):
  repo = request.args['repo']
  return jsonify(git.getIssues(repo))
  #return jsonify({'requirements': _issuesToRequirements(git.getIssues(repo))})

@api.route("/login")
@authorized
def login(token):
  return jsonify(git.getUser(token))

@api.route("/test")
@authorized
def test(token):
  pass

@api.errorhandler(404)
def error404(error):
  return '<strong>api: 404 error:</strong> %s: %s' % ( request.url, error)

if __name__ == "__main__":
  api.run(debug = True, host = '0.0.0.0')
