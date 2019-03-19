#!/usr/bin/python
# -*- coding: utf-8 -*-

from functools import wraps  
from flask import Flask, request, jsonify, redirect, session, url_for
import os
from openreq import OpenReq
from github import GitApp
import time

api = Flask(__name__)
api.config.from_pyfile('config.py', silent=True)

git = GitApp(
  api.config['APP_ID'], 
  api.config['CLIENT_ID'], 
  api.config['CLIENT_SECRET'], 
  os.path.join(os.path.dirname(__file__), "private-key.pem"),
  PERSONAL_ACCESS_TOKEN = api.config['PERSONAL_ACCESS_TOKEN'] 
)

opnr = OpenReq(api.config['OPENREQ_BASEURL'])

def authorized(f):
  @wraps(f)
  def decorator(*args, **kwargs):
    try:
      # check for revoked access_token
      git.getUser(session['access_token'])
    except Exception:
      return jsonify({
        'message': "Unauthorized request",
        'next': git.authorizeUrl(url_for('auth', _external=True) + request.path[1:])
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


def _issuesToRequirements(issues):
  return [ { 
    'id': issue['node_id'] + label['node_id'],
    'reqDomains': "",
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
  
  # check if repo has been trained already
  if not opnr.exists(company, property):
    # retrieve issues for repo
    issues = git.getIssues(repo)
    # convert github issues to requirement
    requirements = _issuesToRequirements(issues)
    # call openreq api to train issues retrived
    opnr.train(company, property, requirements)
  else:
    requirements = []
  
  # TODO associate trained model to user
  
  return jsonify({
    'message': "Model has been trained and associated to your userbase.",
    'requirements': len(requirements),
    'time': time.time() - start
  })


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
  # check repo if user has installed app on
  if git.isInstalled(repo) :
    # check model if exists
    if not opnr.exists(company, property):
      return jsonify({
        'message': "Train the model before you can use it"
      }), 404
    # retrieve issues for repo
    # for each issue call openreq api to classify repo based on model
    for issue in git.getIssues(repo):
      labels = opnr.classify(company, property, issue)
      #   write labels for issue
      git.setLabels(issue,labels)
  else:
    return jsonify({
      'message': "App not installed on this repository"
    }), 401
  
  return "OK" # TODO define return form 

@api.route("/webhook")
def webhook():
  # TODO webhook endpoint
  pass
  
  
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

  #return jsonify(git.getIssues(repo, token))
  return jsonify(git.getIssues(repo, git.PERSONAL_ACCESS_TOKEN))
  #return jsonify({'requirements': _issuesToRequirements(git.getIssues(repo))})

@api.route("/login")
@authorized
def login(token):
  return jsonify(git.getUser(token))

@api.route("/test")
@authorized
def test(token):
  repo = request.args['repo']
  model = request.args['model'] 
  company, property = model.split("/")
  requirements = _issuesToRequirements(git.getIssues(repo))
  r = opnr.classify(company, property, requirements[0:1])
  return jsonify(r.json())



@api.errorhandler(404)
def error404(error):
  return '<strong>api: 404 error:</strong> %s: %s' % ( request.url, error)

if __name__ == "__main__":
  api.run(debug = True, host = '0.0.0.0')
