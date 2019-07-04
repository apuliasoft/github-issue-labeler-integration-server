from flask_sqlalchemy import SQLAlchemy

# initialize db interface
db = SQLAlchemy()

class Models(db.Model):
  """
  Class mapping table of repositories used as a model by a classification process
  """
  repo = db.Column(db.String(100), primary_key=True)
  ready = db.Column(db.Boolean, default=False)
  created = db.Column(db.DateTime, server_default=db.func.now())
  updated = db.Column(db.DateTime, server_default=db.func.now(), server_onupdate=db.func.now())
  
  def __repr__(self):
    return '<Model %r ready %d>' % (self.name, self.ready)

class Trainings(db.Model):
  """
  Class mapping table of model repositories associated to git user
  """
  username = db.Column(db.String(100), primary_key=True)
  repo = db.Column(db.String(100), db.ForeignKey(Models.repo), primary_key=True)
  model = db.relationship(Models, foreign_keys='Trainings.repo')
  
  def __repr__(self):
    return '<Model %r associated to user %r>' % (self.model, self.username)

class Classifications(db.Model):
  """
  Class mapping table of classification sessions of git repositories and relative models
  """
  username = db.Column(db.String(100))
  repo = db.Column(db.String(100), primary_key=True)
  model = db.Column(db.String(100))
  classified = db.Column(db.Boolean, default=False)
  started = db.Column(db.DateTime, server_default=db.func.now())
  completed = db.Column(db.DateTime, default=None)
  
  def __repr__(self):
    return '<Classification of %r using model %r for user %r>' % (self.repo, self.model, self.username)
