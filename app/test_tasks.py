import unittest

from extensions import git, GitError
from app import app
import os

from tasks import train, classify

class TestTasks(unittest.TestCase):
  
  def setUp(self):
    # setup flask app context to avoid dependency problems
    app.testing = True
    # change path if not testing from app environment
    git.PRIV_KEY_PATH = os.path.join(os.path.dirname(__file__), "private-key.pem")
    self.app = app.test_client()
  
  def test_values(self):
    # check wrong repo format
    self.assertRaises(ValueError, train, "wrongrepo")
    self.assertRaises(ValueError, classify, "wrong/repo", "wrongrepo", "wrongtoken")
    
  def test_valid(self):
    with self.assertRaises(GitError):
      # check non existant repo
      train("wrong/repo")
      classify( "wrongrepo", "wrong/repo", "wrongtoken")
      # check non valid token
      classify( "wrong/repo", "wrong/repo", "wrongtoken")
    
    
    
if __name__ == '__main__':
  unittest.main()
  