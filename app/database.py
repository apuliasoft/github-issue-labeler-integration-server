from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Models(db.Model):
  repo = db.Column(db.String(100), primary_key=True)
  ready = db.Column(db.Boolean, default=False)
  created = db.Column(db.DateTime, server_default=db.func.now())
  updated = db.Column(db.DateTime, server_default=db.func.now(), server_onupdate=db.func.now())
  
  def __repr__(self):
    return '<db.Model %r ready %d>' % (self.name, self.ready)

class Trainings(db.Model):
  username = db.Column(db.String(100), primary_key=True)
  model = db.Column(db.String(100), primary_key=True)
  
  def __repr__(self):
    return '<db.Model %r associated to user %r>' % (self.model, self.username)

class Classifications(db.Model):
  username = db.Column(db.String(100))
  repo = db.Column(db.String(100), primary_key=True)
  model = db.Column(db.String(100))
  classified = db.Column(db.Boolean, default=False)
  started = db.Column(db.DateTime, server_default=db.func.now())
  
  def __repr__(self):
    return '<Classification of %r using db.Model %r for user %r>' % (self.repo, self.model, self.username)
    
    
