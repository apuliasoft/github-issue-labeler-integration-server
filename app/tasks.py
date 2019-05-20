from flask import current_app
from extensions import git, opnr, celery
from database import db, Models, Trainings, Classifications
from utils import issuesToRequirements, cplabels

@celery.task
def train(repo):
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


@celery.task
def classify(repo, model, issues = None, first=False):
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
  if first :
    db.session.query(Classifications).filter(Classifications.repo==repo).update({'classified': True})
    db.session.commit()
  
@celery.task
def test_task(w):
  db.session.query(Models).filter(Models.repo=="pippo").first()
  print(w)

