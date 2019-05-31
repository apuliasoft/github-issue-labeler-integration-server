from functools import wraps  
from datetime import datetime, timedelta
from urllib.parse import urlencode, quote, parse_qsl
import jwt
import requests
import json


__version__ = '0.1'

class GitError(Exception):
  """ 
  Simple handler for GitHub errors management
  """
  def __init__(self, message="", response=None):
    if message == "":
      try:
        self.message = response.json()['message']
      except ValueError:
        self.message = dict(parse_qsl(response.content.decode()))
    else:
      self.message = message
      
    self.response = response
   
  def __str__(self):
    return json.dumps({
      'message': self.message or self.response.headers.get('Status'),
      'headers': dict(self.response.headers),
      'raw': self.response.content.decode()
    })


class GitApp:
  """
  Class for interfacing with git api
  
  """
  API_ENDPOINT = 'https://api.github.com/'
  BASE_ENDPOINT = 'https://github.com/'
  AUTH_ENDPOINT = BASE_ENDPOINT + 'login/oauth/'
  
  def setup(self, APP_ID, CLIENT_ID, CLIENT_SECRET, PRIV_KEY_PATH, PERSONAL_ACCESS_TOKEN=None):
    """
    Simple handler for async instance setup
    
    Parameters:
      APP_ID  (string): APP_ID of git app from app settings page
      CLIENT_ID (string): CLIENT_ID of git app from app settings page
      CLIENT_SECRET (string): CLIENT_SECRET of git app from app settings page
      PRIV_KEY_PATH (string): Path to the private key used to forge server-to-server requests to git
      PERSONAL_ACCESS_TOKEN (string): Optional PERSONAL_ACCESS_TOKEN from user settings page to extend app limit to query git to 5000/hour requests instead of 60
      
    Returns:
      return None
    
    """
    self.APP_ID = APP_ID
    self.CLIENT_ID = CLIENT_ID
    self.CLIENT_SECRET = CLIENT_SECRET
    self.PRIV_KEY_PATH = PRIV_KEY_PATH
    self.PERSONAL_ACCESS_TOKEN = PERSONAL_ACCESS_TOKEN
  
  
  def _request(self, method, endpoint, resource, params = {}, headers = {}, collect_all = False, func = lambda x : x):
    """
    Internal function to forge requests and track git errors or pagination
    
    Parameters:
      method: (string): Type of request to forge
      endpoint (string): Request base url to use in request
      resource (string | tuple): A resource definition in the form of a simple string or a tuple (resource_string_with_params, dictionary) eg ('repos/{repo}/installation', { 'repo': repo })
      params (list): Optional params object to pass in request - default: {}
      headers (list): Optional header object to pass in request - default: {}
      collect_all (boolean): Optional flag to collect all values in case of multiple items - default: False
      func (function): Optional function to process request result before returning - default: identity function
    
    Returns:
      return value of func passed in input
    
    """
    
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
    if method == 'PUT':
      response = requests.put(url, data = params, headers = headers)
    if method == 'DEL':
      response = requests.delete(url, params = params, headers = headers)
  
    # may be a between interval is better?
    if response.status_code != requests.codes.ok and response.status_code != requests.codes.created and response.status_code != requests.codes.no_content:
      raise GitError(response = response)
    
    try:
      items = response.json()
    except ValueError:
      items = dict(parse_qsl(response.content.decode()))
    
    
    try:
      # https://developer.github.com/v3/#pagination && https://developer.github.com/v3/guides/traversing-with-pagination/
      if collect_all:
        # DEBUG limit to first 3 call to avoid rate limit but give enough data to compute
        k=0
        while 'next' in response.links.keys() and k<3:
          k += 1
          response = requests.get(response.links['next']['url'], headers = headers)
          items.extend(response.json())
      
      return func(items)
    except Exception as e:
      raise GitError(response=response)
  
  @property
  def jwtToken(self):
    """
    Generate JWT token to authenticate as a GitHub App 
    https://developer.github.com/apps/building-github-apps/authenticating-with-github-apps/#authenticating-as-a-github-app
    A private-key has to be downloaded from app setup page.
    
    Returns:
      jwt token encoded
      
    """
    with open(self.PRIV_KEY_PATH, 'r') as rsa_priv_file:
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
    """"
    Simple handler to generate the header of a server-to-server request
    
    Returns:
      dictionary header with jwt token authorization 
    """
    return {
      'Authorization': 'Bearer ' + self.jwtToken.decode(), 
      'Accept': 'application/vnd.github.machine-man-preview+json'
    }
  
  def getAuthHeader(self, token):
    """"
    Simple handler to generate the header of an authorized request
    
    Returns:
      dictionary header with token authorization 
      
    """
    if token :
      return { 
        'Authorization': 'token ' + token,
        'Accept': 'application/vnd.github.v3+json'
      }
    else:
      return {}


  @property
  def appManagementUrl(self):
    """"
    Short handler to get app management url
    
    Returns:
      git url (string)
      
    """
    return self.BASE_ENDPOINT + 'settings/connections/applications/' + self.CLIENT_ID

  @property
  def appPageUrl(self):
    """"
    Short handler to get app page url
    
    Returns:
      git url (string)
      
    """
    app = self._request('GET', self.API_ENDPOINT, 'app', headers = self.getJwtHeader())
    
    return app['html_url']
  
  def authorizeUrl(self, next):
    """"
    Convert an url to the authorizable git version
    https://developer.github.com/apps/building-oauth-apps/authorizing-oauth-apps/#web-application-flow
    
    Parameters:
      next (string): Url to which git redirect after authorization process
    
    Returns:
      git url with "redirect back feature" (string)
      
    """
    params = {
      'client_id': self.CLIENT_ID,
      'redirect_uri': next
    }
    
    return (self.AUTH_ENDPOINT + 'authorize?' + urlencode(params))


  def getAccessToken(self, request):
    """
    Complete the authentication process converting a git auth request to a valid token
    https://developer.github.com/apps/building-oauth-apps/authorizing-oauth-apps/#web-application-flow
    
    Parameters:
      auth request from git
      
    Returns:
      A valid git access token 
    
    """
    
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
    """
    Return an installation id related to a repository to get full permissions.
    App need to be installed on the repository to complete without errors!
    https://developer.github.com/v3/apps/#get-a-repository-installation
    
    Parameters:
      repo (string): Repository full name in the format 'owner/name' or 'organization/name'
      
    Returns:
      A valid installation id
    
    """
    return self._request('GET', self.API_ENDPOINT, ('repos/{repo}/installation', { 'repo': repo }), headers = self.getJwtHeader(), func = lambda x : x['id'])
  
  
  def getInstallationAccessToken(self, repo, func = lambda x:x['token']):
    """
    Get a valid access token to work on a repository the app is installed on.
    This way is avoided the limit of 60 requests/hour of non authorized calls.
    https://developer.github.com/apps/building-github-apps/authenticating-with-github-apps/#authenticating-as-an-installation
    
    Parameters:
      repo (string): Repository full name in the format 'owner/name' or 'organization/name'
      func (function): Optional function that let you extract any info from git response - default: lambda x:x['token']
      
    Returns:
      A valid access token to work on the input repository or None
    
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
      repo  (string): Repository full name in the format 'owner/name' or 'organization/name'
      
    Returns:
      True/False based on app installation status
      
    """
    try:
      self.getInstallationId(repo)
      return True
    except GitError: #404
      return False
  
  
  def getUser(self, token):
    """
    Get user info
    https://developer.github.com/v3/users/#get-a-single-user
    
    Parameters:
      token (string): A valid token for web requests
      
    Returns:
      user info in the git format (details in the link in description)
    
    """
    
    return self._request('GET', self.API_ENDPOINT, 'user', headers = {'Authorization': 'token ' + token})
  
  
  def getIssues(self, repo, token=None):
    """
    List issues for a repository
    https://developer.github.com/v3/issues/#list-issues-for-a-repository
    If no token passed the request will be forged using installation access token or personal access token
    
    Parameters:
      repo (string): Repository full name in the format 'owner/name' or 'organization/name'
      token (string): Optional valid git token - default: None
      
    Returns:
      issues list in the git format (details in the link in description)
    
    """
    
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
    """
    List all labels for this repository
    https://developer.github.com/v3/issues/labels/#list-all-labels-for-this-repository
    If no token passed the request will be forged using installation access token or personal access token
    
    Parameters:
      repo (string): Repository full name in the format 'owner/name' or 'organization/name'
      token (string): Optional valid git token - default: None
      
    Returns:
      labels list in the git format (details in the link in description)
    
    """
    
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
    """
    Append a new label to a repository
    https://developer.github.com/v3/issues/labels/#create-a-label
    If no token passed the request will be forged using installation access token
    
    Parameters:
      label (dict): A valid label structured object (details in the documentation link provided)
      repo (string): Repository full name in the format 'owner/name' or 'organization/name'
      token (string): Optional valid git token - default: None
      
    Returns:
      None 
    
    """
    
    args = {
      'params': json.dumps(label),
      'headers': self.getAuthHeader( token or self.getInstallationAccessToken(repo) )
    }
    
    self._request('POST', self.API_ENDPOINT, ('repos/{repo}/labels', { 'repo': repo }), **args)


  def rmLabel(self, repo, label_name, token=None):
    """
    Remove a label from a repository
    https://developer.github.com/v3/issues/labels/#delete-a-label
    If no token passed the request will be forged using installation access token
    
    Parameters:
      repo (string): Repository full name in the format 'owner/name' or 'organization/name'
      label_name (string): The label name to remove
      token (string): Optional valid git token - default: None
      
    Returns:
      None 
    
    """
    
    args = {
      'headers': self.getAuthHeader( token or self.getInstallationAccessToken(repo) )
    }
    
    r = self._request('DEL', self.API_ENDPOINT, ('repos/{repo}/labels/{name}', { 'repo': repo, 'name': quote(label_name) }), **args)


  def rmLabels(self, repo, token=None):
    """
    Remove all labels from a repository
    https://developer.github.com/v3/issues/labels/#delete-a-label
    If no token passed the request will be forged using installation access token
    
    Parameters:
      repo (string): Repository full name in the format 'owner/name' or 'organization/name'
      token (string): Optional valid git token - default: None
      
    Returns:
      None 
    
    """
    
    for label in self.getLabels(repo, token):
      self.rmLabel(repo, label['name'], token)


  def setLabels(self, repo, issue_number, labels, token=None):
    """
    Associate a list of label to a specified issue_number in a repository (already labels are replaced)
    https://developer.github.com/v3/issues/labels/#replace-all-labels-for-an-issue
    If no token passed the request will be forged using installation access token
    
    Parameters:
      repo (string): Repository full name in the format 'owner/name' or 'organization/name'
      issue_number (int): issue number from issue details info
      labels (list): A list of labels name (previous associated to the repository with all required details)
      token (string): Optional valid git token - default: None
      
    Returns:
      None 
    
    """
    
    args = {
      'params': json.dumps(labels),
      'headers': self.getAuthHeader( token or self.getInstallationAccessToken(repo) )
    }
    
    self._request('PUT', self.API_ENDPOINT, ('repos/{repo}/issues/{number}/labels', { 'repo': repo, 'number': issue_number }), **args)
  
  
  def exists(self, repo, token=None):
    """
    Check repository existence
    If no token passed the request will be forged using a personal access token if present
    
    Parameters:
      repo (string): Repository full name in the format 'owner/name' or 'organization/name'
      token (string): Optional valid git token - default: None
      
    Returns:
      True/False based on repository existence 
    
    """
    
    args = {
      'headers': self.getAuthHeader( token or self.PERSONAL_ACCESS_TOKEN )
    }
    
    try:
      self._request('GET', self.API_ENDPOINT, ('repos/{repo}', { 'repo': repo }), **args)
      return True
    except GitError: #404
      return False
  
  def getRepo(self, repo, token=None):
    """
    Get repository informations
    https://developer.github.com/v3/repos/#get
       
    Parameters:
      repo (string): Repository full name in the format 'owner/name' or 'organization/name'
      token (string): Optional valid git token - default: None
    
    Returns:
      A repository object as on git documentation
    
    """
    
    args = {
      'headers': self.getAuthHeader( token or self.getInstallationAccessToken(repo) or self.PERSONAL_ACCESS_TOKEN )
    }
    
    return self._request('GET', self.API_ENDPOINT, ('repos/{repo}', { 'repo': repo }), **args, )
    
    