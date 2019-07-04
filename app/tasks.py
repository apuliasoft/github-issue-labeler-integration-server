from flask import current_app
from extensions import git, opnr, celery
from database import db, Models, Trainings, Classifications
from utils import issuesToRequirements, cplabels

@celery.task
def train(repo):
  """
  Asyncronous train task.
  Retrive issues from input git repository and start a training on OpenReq instance, then save do db.
  
  Parameters:
    repo (string): A repository full name in the format 'owner/name' or 'organization/name'
  
  Returns:
    None
  
  """
  
  try:
    company, property = repo.split("/")
    # retrieve issues for repo
    issues = git.getIssues(repo)
    # convert github issues to requirement
    requirements = issuesToRequirements(issues)
    # call openreq api to train issues retrived
    opnr.train(company, property, requirements)
    # model is ready
    db.session.query(Models).filter(Models.repo==repo).update({'ready': True})
    db.session.commit() 
  except Exception as e:
    current_app.logger.error(e, exc_info=True)
    raise

@celery.task
def classify(repo, model, token, issues = None, batch=False):
  """
  Asyncronous classify task.
  Retrive issues from source git repository and start a classification on OpenReq instance.
  Then update labels in the source repository and save do db.
  
  Parameters:
    repo (string): A repository full name to classify in the format 'owner/name' or 'organization/name'
    model (string): A repository full name to use as a model in the format 'owner/name' or 'organization/name'
    token (string): A valid token to get write permission on the repository to classify
    issues (list): Issues list in the git format
    batch (boolean): Flag to update db in case of first batch classification process
  
  Returns:
    None
  
  """
  try:
    company, property = model.split("/")
    
    # copy label from model to repo if this is the first batch attempt
    if batch :
      cplabels(model, repo, token)
    
    # retrieve issues for repo if not passed and convert to requirements
    if not issues:
      issues = git.getIssues(repo, token)
    requirements = issuesToRequirements(issues, isForClassify=True)
    # call openreq api to classify repo based on model
    recommendations = opnr.classify(company, property, requirements)
      
    # write labels to issues on repo 
    # use requirements list instead of issues one for optimization purpose 
    # because req[id] = issue[number] and label = requirement_type
    for rec in recommendations:
      if rec['confidence'] > current_app.config['CONFIDENCE_TRESHOLD'] :
        git.setLabels(repo, rec['requirement'], [rec['requirement_type']], token)
    
     # set repo as classified if on first batch classification
    if batch :
      db.session.query(Classifications).filter(Classifications.repo==repo).update({
        'classified': True, 
        'completed': db.func.current_timestamp()
      })
      db.session.commit()
  except Exception as e:
    current_app.logger.error(e, exc_info=True)
    raise