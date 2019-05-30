from celery import Celery

from openreq import OpenReq
from github import GitApp, GitError

# Initialize GitApp, OpenReq and Celery classes 

git = GitApp()

opnr = OpenReq()

# Celery class need a broker as a minimum parameter set to start without errors so we need to import directly from config before app is initialized
from config import CELERY_BROKER_URL
celery = Celery(broker=CELERY_BROKER_URL)

def make_celery(app):
  # Integrate Celery class with Flask app context after inizialization http://flask.pocoo.org/docs/1.0/patterns/celery/
  celery.conf.update(app.config)
  
  class ContextTask(celery.Task):
      def __call__(self, *args, **kwargs):
        with app.app_context():
          return self.run(*args, **kwargs)
    
  celery.Task = ContextTask
