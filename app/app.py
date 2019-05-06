#!/usr/bin/python
# -*- coding: utf-8 -*-

from functools import wraps  
from flask import Flask, request, jsonify, redirect, session, url_for
import os
from openreq import OpenReq
from github import GitApp,GitError
import time
from flask_sqlalchemy import SQLAlchemy
#from sqlalchemy.exc import IntegrityError
from sqlalchemy import func

api = Flask(__name__)
api.config.from_pyfile('config.py', silent=True)

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
  model = db.Column(db.String(100), primary_key=True)
  status = db.Column(db.Integer) # 0 training started - 1 trained
  created = db.Column(db.DateTime, server_default=db.func.now())
  updated = db.Column(db.DateTime, server_default=db.func.now(), server_onupdate=db.func.now())
  
  def __repr__(self):
    return '<Model %r in status %d>' % (self.model, self.status)

class Trainings(db.Model):
  username = db.Column(db.String(100), primary_key=True)
  model = db.Column(db.String(100), primary_key=True)
  
  def __repr__(self):
    return '<Model %r associated to user %r>' % (self.model, self.username)

class Classifications(db.Model):
  username = db.Column(db.String(100), primary_key=True)
  repo = db.Column(db.String(100), primary_key=True)
  model = db.Column(db.String(100))
  status = db.Column(db.Integer) # 0 classification started - 1 associated 
  
  def __repr__(self):
    return '<Classification of %r using model %r for user %r>' % (self.repo, self.model, self.username)

# check if db is created or create
db.create_all()

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


@api.route('/train')
@authorized
def train(token):
  start = time.time()
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
  # check also if a training istance has already issued (with time limit) but not saved in openreq (using local db)
  model = db.session.query(Models).filter(Models.model==repo).first()
  if opnr.exists(company, property):
    # model exists remotely but not match local view
    if not model or model.status == 0:
      db.session.merge(Models(model=repo, status=1))
      db.session.commit()
  else:
    # model not exists but we have locally an attempt (timeout?) to training
    if not ( model and model.status == 0 and (model.updated - model.created).seconds < 1800 ):
      # set training started in local db
      db.session.merge(Models(model=repo, status=0))
      db.session.commit()
      # retrieve issues for repo
      issues = git.getIssues(repo)
      # convert github issues to requirement
      requirements = _issuesToRequirements(issues)
      # call openreq api to train issues retrived
      opnr.train(company, property, requirements)
      # update model status to trained
      db.session.query(Models).filter(Models.model==repo).update({'status': 1})
      db.session.commit() 
  
  try:
    # associate model to user
    db.session.merge(Trainings(model=repo, username=session['user_id']))
    db.session.commit()
  except Exception as e:
    return jsonify({
      'message': e.message
    }), 500
  
  return jsonify({
    'message': "Model has been trained and associated to your userbase.",
    'requirements': len(requirements),
    'time': time.time() - start
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
  
  return jsonify({'message': 'labels copied', 'time': time.time() - start})


@api.route('/classify')
@authorized
def classify(token):
  """
    Classify a repository using a model trainer from another repository
    
    Parameters:
      repo  (string): a repository in the form owner/repo
      model (string): a model available on OpenReq server in the form company/property
    
    Results:
      return 200 if everything is OK
  """
  repo = request.args['repo']
  model = request.args['model'] 
  company, property = model.split("/")
  times = {}
  
  # check repo if user has installed app on and get installation token for successive calls to api
  try:
    token = git.getInstallationAccessToken(repo)
  except GitError:
    return jsonify({
      'message': "App not installed on this repository",
      'next': git.appPageUrl
    }), 403
  
  # check model if exists
  if not opnr.exists(company, property):
    return jsonify({
      'message': "Train the model before you can use it",
      'next': url_for('train', _external=True) + '?repo=' + model
    }), 404
  
  start = time.time()
  # copy label from model to repo 
  #_cplabels(model, repo, token)
  times['cplabels'] = time.time() - start
  
  start = time.time()
  # retrieve issues for repo and convert to requirements
  requirements = _issuesToRequirements(git.getIssues(repo, token), isForClassify=True)
  # call openreq api to classify repo based on model
  recommendations = opnr.classify(company, property, requirements)
  times['classification'] = time.time() - start
  
  start = time.time()
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
  
  times['issue_update'] = time.time() - start
  
  return jsonify({
    'message': "Repository has been classified.",
     'time': times
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
  # TODO webhook endpoint
  return "ok"

# test endpoints
@api.route("/initdb")
@authorized
def initdb(token):
  db.create_all()
  
  
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
  #repo = request.args['repo']
  model = request.args['model'] 
  company, property = model.split("/")
  return jsonify(opnr.classify(company, property, []))
  requirements = _issuesToRequirements(git.getIssues(repo), isForClassify=True)
  r = opnr.classify(company, property, requirements[0:1])
  return jsonify(r)
  recc = r.json()['recommendations'][0]
  git.setLabels(repo, requirements[0]['id'],[recc['requirement_type']])
  return jsonify(recc['requirement_type'])

@api.route('/labels')
@authorized
def labels(token):
  repo = request.args['repo']
  #model = request.args['model']
  
  return jsonify(git.getIssues(repo))
  token = git.getInstallationAccessToken(repo)
  #return jsonify(git.getLabels(repo, token))
  #_cplabels(model, repo, token)
  git.rmLabels(repo, token)
  return jsonify(True)



@api.errorhandler(404)
def error404(error):
  return '<strong>api: 404 error:</strong> %s: %s' % ( request.url, error)

if __name__ == "__main__":
  api.run(debug = True, host = '0.0.0.0')
