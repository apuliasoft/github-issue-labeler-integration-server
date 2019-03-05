#!/usr/bin/python
# -*- coding: utf-8 -*-

from functools import wraps  
from flask import Flask, request, jsonify, redirect, session, url_for
import os
from openreq import OpenReq
from github import GitApp

api = Flask(__name__)
api.config.from_pyfile('config.py', silent=True)

git = GitApp(
  api.config['APP_ID'], 
  api.config['CLIENT_ID'], 
  api.config['CLIENT_SECRET'], 
  os.path.join(os.path.dirname(__file__), "private-key.pem")
)

def authorized(f):
  @wraps(f)
  def decorator(*args, **kwargs):
    #TODO check for revoked access_token call https://api.github.com/user
    if 'access_token' not in session:
      return redirect(git.authorizeUrl(url_for('auth', _external=True) + request.path[1:]))
    
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
    return "Invalid authorization",401


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

@api.route('/train')
@authorized
def train(token):
  """
    Train a model from a repository using OpenReq API
    
    Parameters:
      repo  (string): a repository in the form owner/repo
    
    Results:
      return 200 if everything is OK
  """
  repo = request.args['repo']
  company, property = repo.split("/")
  # check if repo has been trained already
  if OpenReq.exists(company, property):
    # retrieve issues for repo
    issues = git.getIssues(repo)
    # call openreq api to train issues retrived
    OpenReq.trainModel(company, property, issues)
    
  # associate trained model to user
  return "OK" # TODO define return form 


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
    if not OpenReq.checkModelexists(company, property):
      return "Train the model before you can use it", 404
    # retrieve issues for repo
    # for each issue call openreq api to classify repo based on model
    for issue in git.getIssues(repo):
      labels = OpenReq.classifyIssue(company, property, issue)
      #   write labels for issue
      git.setLabels(issue,labels)
  else:
    return "App not installed on this repository", 401
  
  return "OK" # TODO define return form 

@api.route("/webhook")
def webhook():
  # TODO webhook endpoint
  pass
  
  
# test endpoints

@api.route("/myrepos")
@authorized
def myrepos(token):
  r = requests.get('https://api.github.com/users/{username}/repos'.format(username = session['user_id']), headers={'Authorization': 'token ' + token})
  #return jsonify(r.json())
  return jsonify([ x['full_name'] for x in r.json() ])


@api.route("/issues/<path:repo>")
def issues(repo):
  return jsonify(git.getIssues(repo))

@api.route("/login")
@authorized
def login(token):
  return jsonify(git.getUser(token))

@api.route("/test")
@authorized
def test(token):
  repo = request.args['repo']
  return jsonify(git.isInstalled(repo))



@api.errorhandler(404)
def error404(error):
  return '<strong>api: 404 error:</strong> %s: %s' % ( request.url, error)

if __name__ == "__main__":
  api.run(debug = True, host = '0.0.0.0')
