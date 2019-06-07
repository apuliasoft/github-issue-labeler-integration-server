#!/usr/bin/python
 
from flask import Flask, request
from flasgger import Swagger

from openreq import OpenReq
from github import GitApp,GitError

from database import db
from extensions import git, opnr, celery, make_celery
from api import api

import logging

# initialize flask app
app = Flask(__name__)
app.config['LOG_PATH'] = "/var/log/is.log"
app.config['LOG_FORMAT'] = "%(asctime)s - %(pathname)s:%(lineno)d - %(levelname)s - %(message)s"
app.config.from_pyfile('config.py', silent=True)

log_handler = logging.FileHandler(app.config['LOG_PATH'])
log_handler.setFormatter(logging.Formatter(app.config['LOG_FORMAT']))
app.logger.addHandler(log_handler)

# register api endpoints
app.register_blueprint(api)

# configure swagger to be similar to openreq
Swagger(app, template_file = 'api_template.yaml', config = {
  "headers": [
  ],
  "specs": [{
    "endpoint": 'api-docs',
    "route": '/api-docs'
  }],
  "static_url_path": "/swagger_static",
  "swagger_ui": True,
  "specs_route": "/swagger-ui.html"
})

# setup git interface
git.setup(
  app.config['GITHUB_APP_ID'], 
  app.config['GITHUB_CLIENT_ID'], 
  app.config['GITHUB_CLIENT_SECRET'], 
  app.config['GITHUB_PRIV_KEY_PATH']
)
if 'GITHUB_PERSONAL_ACCESS_TOKEN' in app.config:
  git.PERSONAL_ACCESS_TOKEN = app.config['GITHUB_PERSONAL_ACCESS_TOKEN']

# setup openreq interface
opnr.setup(app.config['OPENREQ_BASEURL'])

# setup db sqlalchemy interface
db.init_app(app)
with app.app_context():
  db.create_all()

# setup celery interface
make_celery(app)

@app.errorhandler(404)
def error404(error):
  app.logger.warning('404 not found for %s', request.url)
  return '<h1>404 error</h1><p>%s</p>' % error, 404

@app.errorhandler(Exception)
def unhandled_exception(e):
  app.logger.error('Unhandled Exception: %s', (e))
  return '<h1>500 error</h1>', 500

if __name__ == "__main__":
  app.run(host='0.0.0.0')
else:
  # when running celery worker a context is needed
  import tasks
  print('*** push app context ***')
  app.app_context().push()