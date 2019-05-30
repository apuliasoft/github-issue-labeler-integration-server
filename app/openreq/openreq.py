import requests
import json

__version__ = '0.1'

class OpenReqError(Exception):
  """ 
  Simple handler for OpenReq errors management
  """
  def __init__(self, message="", response=None):
    if message == "":
      self.message = response.json()['message']
    else:
      self.message = message
      
    self.response = response
  
  def __str__(self):
    return  self.message


class OpenReq:
  """
  Class for interfacing with openreq api
  
  """
  def setup(self, BASEURL):
    """
    Simple handler for async instance setup
    
    Parameters:
      BASEURL (string): Hostname:port where openreq is installed 
      
    Returns:
      return None
    
    """
    self.API_ENDPOINT = BASEURL + '/upc/classifier-component/'
  
  def exists(self, company, property):
    """
    Check model existence
    
    Parameters:
      company (string): Company to which model belongs to
      property (string): Property associated to model
      
    Returns:
      True/False based on model existence 
    
    """
    try:
      # There isn't a native way to check for model existence 
      # so try to classify empty requirements to see a 200 response
      self.classify(company, property, [])
      return True
    except Exception:
      return False
  
  def classify(self, company, property, requirements):
    """
    Classify requirements with a model (company+property)
    
    Parameters:
      company (string): Company to which model belongs to
      property (string): Property associated to model
      requirements (list): List of requirements to classify (refer to openreq docs for requirement specification)
    
    Returns:
      list of recommendations after classification process is performed
    
    """
    
    params = {
      'company': company,
      'property': property
    }
    
    r = requests.post(self.API_ENDPOINT + 'classify', params = { 'company': company, 'property': property }, json = { 'requirements': requirements })
    
    if r.status_code != requests.codes.ok and r.status_code != requests.codes.created and r.status_code != requests.codes.no_content:
      raise OpenReqError(response=r)
    
    return r.json()['recommendations']
    
  
  def train(self, company, property, requirements):
    """
    Train a model from requirements and associate to company + property
    
    Parameters:
      company (string): Company to which model will belongs to
      property (string): Property associated to model
      requirements (list): List of requirements to train the model (refer to openreq docs for requirement specification)
    
    Returns:
      None
    
    """
    
    params = {
      'company': company,
      'property': property
    }
    
    r = requests.post(self.API_ENDPOINT + 'train', params = { 'company': company, 'property': property }, json = { 'requirements': requirements })
    
    if r.status_code != requests.codes.ok and r.status_code != requests.codes.created and r.status_code != requests.codes.no_content:
      raise OpenReqError(response=r)