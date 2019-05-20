from celery import Celery

from openreq import OpenReq
from github import GitApp,GitError

git = GitApp()
opnr = OpenReq()

from config import CELERY_BROKER_URL
celery = Celery(broker=CELERY_BROKER_URL)

def make_celery(app):
  celery.conf.update(app.config)
  
  class ContextTask(celery.Task):
      def __call__(self, *args, **kwargs):
        with app.app_context():
          return self.run(*args, **kwargs)
    
  celery.Task = ContextTask
