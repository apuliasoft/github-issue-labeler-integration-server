# -*- coding: utf-8 -*-

import requests
import json

__version__ = '1.0.0'

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
  
  def __init__(self, OPENREQ_BASEURL):
    self.API_ENDPOINT = OPENREQ_BASEURL + '/upc/classifier-component/'
  
  def exists(self, company, property):
    try:
      # There isn't a native way to check for model existance 
      # so try to classify empty requirements to see a 200 response
      self.classify(company, property, [])
      return True
    except Exception:
      return False
  
  def classify(self, company, property, requirements):
    params = {
      'company': company,
      'property': property
    }
    
    r = requests.post(self.API_ENDPOINT + 'classify', params = { 'company': company, 'property': property }, json = { 'requirements': requirements })
    
    if r.status_code != requests.codes.ok and r.status_code != requests.codes.created and r.status_code != requests.codes.no_content:
      raise OpenReqError(response=r)
    
    return r.json()['recommendations']
    
  
  def train(self, company, property, requirements):
    params = {
      'company': company,
      'property': property
    }
    
    r = requests.post(self.API_ENDPOINT + 'train', params = { 'company': company, 'property': property }, json = { 'requirements': requirements })
    
    return r