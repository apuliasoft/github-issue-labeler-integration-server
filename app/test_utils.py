import unittest

from utils import issuesToRequirements, cplabels
from github import GitError

class TestUtils(unittest.TestCase):
  def test_issuesToRequirements(self):
    # empty issue empty requirements
    self.assertEqual(issuesToRequirements([]), [])
    # check result format and if excluding pull_requests when isForClassify = True
    self.assertEqual(
      issuesToRequirements([
        {'number': 1, 'body': 'test pull', 'pull_request': 'anyvalue'}, 
        {'number': 2, 'body': 'test'}
      ], True),
      [{'id': 2, 'text': 'test'}]
    )
    # check result format and if excluding issues with no labels when isForClassify = False
    self.assertEqual(
      issuesToRequirements([
        {'number': 1, 'body': 'test1', 'labels': [{'id': 2, 'name': 'label2'}]}, 
        {'number': 2, 'body': 'test2', 'labels': []},
        {'number': 2, 'body': 'test2'} # this test is a wrong manual format without labels key
      ], False),
      [{'id': '1_2', 'text': 'test1', 'requirement_type': 'label2'}]
    )
  
  def test_values(self):
    # check if error raised when wrong token provided
    with self.assertRaises(GitError):
      cplabels("git/git", "git/git", "wrong token")
  
  def test_types(self):
    # check if input issues is a list of dict
    self.assertRaises(TypeError, issuesToRequirements, 1)
    self.assertRaises(TypeError, issuesToRequirements, "")
    self.assertRaises(TypeError, issuesToRequirements, [1,2,3])
    #cplabels(repo_from, repo_to, token)
  
    
if __name__ == '__main__':
  unittest.main()
  