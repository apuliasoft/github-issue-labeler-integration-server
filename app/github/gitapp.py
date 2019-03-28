# -*- coding: utf-8 -*-

from functools import wraps  
from datetime import datetime, timedelta
from urllib import urlencode
from urlparse import parse_qsl
import jwt
import requests
import json


__version__ = '1.0.0'

class GitError(Exception):
  """ 
    Simple handler for GitHub errors management
  """
  def __init__(self, message="", response=None):
    if message == "":
      try:
        self.message = response.json()['message']
      except ValueError:
        self.message = dict(parse_qsl(response.content))
    else:
      self.message = message
      
    self.response = response
   
  def __str__(self):
    return {
      'message': self.message,
      'headers': self.response.headers,
      'raw': self.response.content
    }


class GitApp:
  
  API_ENDPOINT = 'https://api.github.com/'
  BASE_ENDPOINT = 'https://github.com/'
  AUTH_ENDPOINT = BASE_ENDPOINT + 'login/oauth/'
  
  def __init__(self, APP_ID, CLIENT_ID, CLIENT_SECRET, priv_key, PERSONAL_ACCESS_TOKEN=None):
    self.APP_ID = APP_ID
    self.CLIENT_ID = CLIENT_ID
    self.CLIENT_SECRET = CLIENT_SECRET
    self.priv_key = priv_key
    self.PERSONAL_ACCESS_TOKEN = PERSONAL_ACCESS_TOKEN
  
  
  def _request(self, method, endpoint, resource, params = {}, headers = {}, collect_all = False, func = lambda x : x):
    # create request url
    
    if type(resource) == tuple:
      res, res_params = resource
    else:
      res, res_params = (resource, {})
    
    
    url = endpoint + res.format(**res_params)
    
    # make request based on method
    if method == 'GET':
      response = requests.get(url, params = params, headers = headers)
    if method == 'POST':
      response = requests.post(url, data = params, headers = headers)
  
  
    if response.status_code != requests.codes.ok and response.status_code != requests.codes.created:
      raise GitError(response=response)
    
    try:
      items = response.json()
    except ValueError:
      items = dict(parse_qsl(response.content))
    
    # DEBUG limit to first 3 call to avoid rate limit but give enough data to compute
    k=0
    
    try:
      # https://developer.github.com/v3/#pagination && https://developer.github.com/v3/guides/traversing-with-pagination/
      if collect_all:
        while 'next' in response.links.keys() and k<3:
          k += 1
          response = requests.get(response.links['next']['url'])
          items.extend(response.json())
      
      return func(items)
    except Exception as e:
      return response
  
  @property
  def jwtToken(self):
    """
      Generate JWT token to authenticate as a GitHub App 
      https://developer.github.com/apps/building-github-apps/authenticating-with-github-apps/#authenticating-as-a-github-app
      'private-key.pem' has to be downloaded from app setup page and put in the root folder 
    """
    with open(self.priv_key, 'r') as rsa_priv_file:
      priv_rsakey = rsa_priv_file.read()
    
    payload = {
      # issued at time
      'iat': datetime.now(),
      # JWT expiration time (10 minute maximum)
      'exp': datetime.utcnow() + timedelta(minutes=10),
      # GitHub App's identifier
      'iss': self.APP_ID
    }
    
    return jwt.encode(payload, key=priv_rsakey, algorithm='RS256')
  

  def getJwtHeader(self):
    return {
      'Authorization': 'Bearer ' + self.jwtToken, 
      'Accept': 'application/vnd.github.machine-man-preview+json'
    }
  
  def getAuthHeader(self, token):
    if token :
      return { 
        'Authorization': 'token ' + token
      }
    else:
      return {}


  @property
  def appManagementUrl(self):
    return self.BASE_ENDPOINT + 'settings/connections/applications/' + self.CLIENT_ID

  @property
  def appPageUrl(self):
    app = self._request('GET', self.API_ENDPOINT, 'app', headers = self.getJwtHeader())
    
    return app['html_url']
  
  def authorizeUrl(self, next):
    params = {
      'client_id': self.CLIENT_ID,
      'redirect_uri': next
    }
    
    return (self.AUTH_ENDPOINT + 'authorize?' + urlencode(params))


  def getAccessToken(self, request):
    #TODO check state to avoid forged requests
    params = {
      'client_id': self.CLIENT_ID,
      'client_secret': self.CLIENT_SECRET,
      'code': request.args['code'],
      'state': request.args.get('state','')
    }
    
    r = self._request('POST', self.AUTH_ENDPOINT, 'access_token', params)#, func = lambda x:x['access_token'])
    
    if 'error' in r:
      raise GitError(r['error_description'])
    
    return r['access_token']
  
  
  def getInstallationId(self, repo):
    return self._request('GET', self.API_ENDPOINT, ('repos/{repo}/installation', { 'repo': repo }), headers = self.getJwtHeader(), func = lambda x : x['id'])
  
  
  def getInstallationAccessToken(self, repo, func = lambda x:x['token']):
    # https://developer.github.com/apps/building-github-apps/authenticating-with-github-apps/#authenticating-as-an-installation
    """
      When you need to work on a repository the app is installed on, then is preferable to use an installation access token.
    """
    try:
      installation_id = self.getInstallationId(repo)
      r = self._request('POST', self.API_ENDPOINT, ('app/installations/{installation_id}/access_tokens', {'installation_id':installation_id}), headers = self.getJwtHeader(), func = func)
      return r
    except GitError: #404
      return None
  
  
  def isInstalled(self, repo):
    """
      Check if user has installed this app for the input repository
      
      Parameters:
        repo  (string): repository in the form :owner/:repo
        
      Returns:
        return True/False if the app is installed in the repository
    """
    try:
      self.getInstallationId(repo)
      return True
    except GitError: #404
      return False
  
  
  def getUser(self, token):
    return self._request('GET', self.API_ENDPOINT, 'user', headers = {'Authorization': 'token ' + token})
  
  
  def getIssues(self, repo, token=None):
    args = {
      'collect_all': True,
      'params': {
        'per_page': 100, 
        'page': 1, 
        'state': 'all'
      },
      'headers': self.getAuthHeader( token or self.getInstallationAccessToken(repo) or self.PERSONAL_ACCESS_TOKEN )
    }
    
    return self._request('GET', self.API_ENDPOINT, ('repos/{repo}/issues', { 'repo': repo }), **args)
  
  def getLabels(self, repo, token=None):
    args = {
      'collect_all': True,
      'params': {
        'per_page': 100, 
        'page': 1
      },
      'headers': self.getAuthHeader( token or self.getInstallationAccessToken(repo) or self.PERSONAL_ACCESS_TOKEN )
    }
    
    return self._request('GET', self.API_ENDPOINT, ('repos/{repo}/labels', { 'repo': repo }), **args)
  
  def addLabel(self, label, repo, token=None):
    args = {
      'params': json.dumps(label),
      'headers': self.getAuthHeader( token or self.getInstallationAccessToken(repo) )
    }
    
    return self._request('POST', self.API_ENDPOINT, ('repos/{repo}/labels', { 'repo': repo }), **args)
    
    
  
  def setLabels(self, issue, labels):
    # POST /repos/:owner/:repo/issues/:number/labels
    # PUT to replace labels
    pass
  
  