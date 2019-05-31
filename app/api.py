#!/usr/bin/python

from functools import wraps  
from flask import Blueprint, current_app, request, jsonify, redirect, session, url_for
from werkzeug import exceptions as exc

from datetime import datetime

from database import db, Models, Trainings, Classifications
from extensions import git, GitError, opnr
import tasks

import hashlib
import hmac

api = Blueprint('api', __name__)


def authorized(f):
  """
  Decorator to ensure that the call is authorized via a valid token
  """
  @wraps(f)
  def decorator(*args, **kwargs):
    try:
      # check for revoked access_token
      git.getUser(session['access_token'])
    except Exception:
      return jsonify({
        'message': "Unauthorized request",
        'next': git.authorizeUrl(url_for('api.auth', _external=True))
      }),401
    
    return f(session['access_token'], *args, **kwargs)  
  return decorator


@api.route('/auth/', defaults={'next':'/'})
@api.route('/auth/<path:next>')
def auth(next):
  """
  Authorization endpoint
  GitHub app needs this as a callback to return a valid token
  """
  token = git.getAccessToken(request)
  
  if token:
    session['access_token'] = token
    user = git.getUser(token)
    session['user_id'] = user['login']
    return redirect(url_for('api.index', _external=True) + next)
  else: 
    return jsonify({
      'message': "Invalid authorization"
    }),401


@api.route("/")
def index():
  if 'access_token' in session:
    return jsonify({'message': 'User correclty logged on!', 'username': session['user_id']})
  return jsonify({'message': 'User not logged, please login to access api.'})


@api.route('/logout')
def logout():
  """
  Logout endpoint to clear session
  ---
  tags: 
    - management
  responses:
    200:
      description: User is no more authenticated
  """
  session.pop('access_token', None)
  session.pop('user_id', None)
  return redirect(url_for('api.index'))


@api.route('/manage')
def manage():
  """
  Takes user to the app page where he can manage app permissions revocation
  ---
  tags: 
    - management
  responses:
    200:
      description: Redirect to app manamente page
  """
  return redirect(git.appManagementUrl)


@api.route('/install')
def install():
  """
    Redirect user to the app main page where he can install the app or change configurations
    ---
    tags: 
      - management
    responses:
      200:
        description: Redirect to app installation page
  """
  return redirect(git.appPageUrl)


@api.route('/train')
@authorized
def train(token):
  """
    Train a model from a GIT repository using OpenReq API
    ---
    tags:
      - api
    parameters:
      - $ref: "#/parameters/repoParam"
    responses:
      200:
        description: OK
        schema:
          id: messages
      201:
        description: Training already started
      403:
        description: Repository not in the format 'owner/name' or 'organization/name'
      404:
        description: Repository not exists
  """
  repo = request.args['repo']
  try:
    company, property = repo.split("/")
  except ValueError:
    return jsonify({
      'message': "Repository not in the format 'owner/name' or 'organization/name'"
    }), 403
  
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
    if model and not model.ready and (model.updated - datetime.now()).seconds < current_app.config['TRAINING_TIMEOUT'] :
      return jsonify({
        'message': 'Training in progress from previous call... please wait'
      }), 201
    else:
      # check repository existance before start training async task
      if not git.exists(repo):
        return jsonify({
          'message': 'Repository not exists'
        }), 404
      # set training started in local db
      db.session.merge(Models(repo=repo, ready=False))
      db.session.commit()
      tasks.train.delay(repo)
  
  try:
    # associate model to user
    db.session.merge(Trainings(repo=repo, username=session['user_id']))
    db.session.commit()
  except Exception as e:
    return jsonify({
      'message': e.message
    }), 500
  
  return jsonify({
    'message': "Trained model has been associated to your userbase."
  })



@api.route('/classify')
@authorized
def classify(token):
  """
    Classify a repository using a model trained from another repository
    ---
    tags:
      - api
    parameters:
      - name: repo
        in: query
        type: string
        required: true
        description: Repository to classify in the format 'owner/name' or 'organization/name'
      - name: model
        in: query
        type: string
        required: true
        description: Repository to use as a model in the format 'owner/name' or 'organization/name'
    responses:
      200:
        description: OK
        schema:
          id: messages
      403:
        description: Forbidden
        schema:
          id: messages
      404:
        description: One of the repositories in input not exists
        schema:
          id: messages
  """
  repo = request.args['repo']
  model = request.args['model'] 
  
  if not git.exists(repo):
    return jsonify({
      'message': 'Repository to classify not exists'
    }), 404
        
  try:
    company, property = model.split("/")
  except ValueError:
    return jsonify({
      'message': "Repository model not in the format 'owner/name' or 'organization/name'"
    }), 403
  
  # check repo if user has installed app on and get installation token for successive calls to api
  try:
    token = git.getInstallationAccessToken(repo)
    if not token:
      raise GitError()
  except GitError:
    return jsonify({
      'message': "App not installed on this repository"
    }), 403
  
  # check model if exists
  if not opnr.exists(company, property):
    return jsonify({
      'message': "Train the model before you can use it"
    }), 403
  
  
  # check if repo is already classified with that model
  # XXX check if is good to avoid successive classification on the same model or need check for timeout classification
  classification = db.session.query(Classifications).filter(Classifications.repo == repo).first()
  if not classification or classification.model != model or (classification.started - datetime.now()).seconds >= current_app.config['CLASSIFICATION_TIMEOUT'] :
    db.session.merge(Classifications(repo=repo, model=model, started=datetime.now()))
    db.session.commit()
    tasks.classify.delay(repo, model, token, batch=True)
    
    return jsonify({
      'message': "Classification scheduled successfully."
    })
  else:
    return jsonify({
      'message': "Repository has been classified already or classification is still in progress."
    })


@api.route("/my-models")
@authorized
def my_models(token):
  """
  List trained models associated to current user
  ---
  tags:
    - api
  responses:
    200:
      description: Models list
      schema:
        type: array
        items:
          type: object
          properties:
            name:
              type: string
            ready:
              type: boolean
          description: Repository full name
          
  """
  return jsonify([ 
    { 'name': t.repo, 'ready': t.model.ready } 
    for t in db.session.query(Trainings).filter_by(username = session['user_id']).join(Models)
  ])


@api.route('/check-installed')
@authorized
def check_installed(token):
  """
  Check if github app is installed in a specific repository
  ---
  tags: 
    - api
  parameters:
    - $ref: "#/parameters/repoParam"
  responses:
    200:
      description: OK
      schema:
        type: boolean
    404:
      description: Invalid repository
      schema:
        id: messages
  """
  
  repo = request.args['repo']
  
  if not git.exists(repo, token):
    return jsonify({
      'message': 'Invalid repository'
    }), 404
  
  return jsonify(git.isInstalled(repo))


@api.route("/is-owner")
@authorized
def is_owner(token):
  """
  Return true/false if current user own the repository passed in input
  ---
  tags:
    - api
  parameters:
    - $ref: "#/parameters/repoParam"
  responses:
    200:
      description: OK
      schema:
        type: boolean
    404:
      description: Invalid repository
      schema:
        id: messages
  """
  
  repo = request.args['repo']
  
  if not git.exists(repo, token):
    return jsonify({
      'message': 'Invalid repository'
    }), 404
  
  try:
    return jsonify(git.getUserPermissions(repo, session['user_id'], token) in ['admin','write'])
  except GitError:
    return jsonify(False)


@api.route("/webhook", methods = ['GET','POST'])
def webhook(): 
  """
  WebHook endpoint
  No need to call directly
  Needed by Git as a callback endpoint to receive server side events
  ---
  """
  # check git signature in payload 
  signature = hmac.new(bytes(current_app.config['WEBHOOK_SECRET'], 'latin-1'), request.data, hashlib.sha1).hexdigest()
  if hmac.compare_digest(str(signature), request.headers['X-Hub-Signature'].split('=')[1]):
   
    data = request.get_json()
    
    # check for incoming issues (new or changed)
    if 'issue' in data and data['action'] in ['opened', 'edited']:
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
      
      tasks.classify.delay(repo, classification.model, [issue])
      
      return jsonify({
        'message': "Issue classified."
      })
  
  return jsonify({
    'message': "nothing to do with this by now"
  }), 204 # CHECK may be a 501 is more proper




# test endpoints can be removed when project is ready to production
  
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
  #r = requests.get('https://api.github.com/app/installation/repositories'.format(username = session['user_id']), headers=git.jwtHeader)
  r = requests.get('https://api.github.com/user/repos', headers=git.getAuthHeader(token))
  #return jsonify(r.json())
  return jsonify([ x['full_name'] for x in r.json() ])

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

@api.route("/access_token")
@authorized
def access_token(token):
  return jsonify(session['access_token'])


@api.route("/test")
@authorized
def test(token):
  repo = request.args['repo']
  return jsonify(git.exists(repo, token))
  return "testato"


@api.errorhandler(404)
def error404(error):
  return '<strong>api: 404 error:</strong> %s: %s' % ( request.url, error)
