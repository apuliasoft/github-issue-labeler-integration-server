#!/usr/bin/python
 
from flask import Flask
from flasgger import Swagger

from openreq import OpenReq
from github import GitApp,GitError

from database import db
from extensions import git, opnr, celery, make_celery
from api import api


# initialize flask app
app = Flask(__name__)
app.config.from_pyfile('config.py', silent=True)

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



if __name__ == "__main__":
  app.run()
else:
  # when running celery worker a context is needed
  import tasks
  print('*** push app context ***')
  app.app_context().push()