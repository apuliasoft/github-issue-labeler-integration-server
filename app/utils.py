def issuesToRequirements(issues, isForClassify = False):
  """
  Convert github issues to requirements format as specified in openreq documentation
  
  Parameters:
    issues  (list): Issues list in github format
    isForClassify (boolean): Flag to change requirements format based on different input required by OpenReq specs
  
  Returns:
    list: Requirements suitable for OpenReq 
    
  """
  if type(issues) != list:
    raise TypeError("Pass a list of issues in the git format")
  
  # requirements don't need 'requirement_type' when for classify 
  if isForClassify :
    return [ { 
      'id': issue['number'],
      'text': issue['body']
    } for issue in issues if 'pull_request' not in issue ]
  else:
    return [ { 
      'id': str(issue['number']) + "_" + str(label['id']),
      'requirement_type': label['name'],
      'text': issue['body']
    } for issue in issues if 'pull_request' not in issue and 'labels' in issue for label in issue['labels'] ]


def cplabels(repo_from, repo_to, token):
  """
  Copy labels from a git repository to another.
  Original labels in the source repository are deleted.
  Write permission is required on the destination repository through a token
  
  Parameters:
    repo_from (string): Source repository full name in the format 'owner/name' or 'organization/name'
    repo_to (string): Destination repository full name in the format 'owner/name' or 'organization/name'
    token (string): A valid token to get write permission on the destination repository
  
  Returns:
    None
  
  """
  from extensions import git
  
  # delete existing labels to avoid duplicate errors
  git.rmLabels(repo_to, token)
  # get labels list from src repo
  labels = git.getLabels(repo_from, token)
  # copy labels to dest repo calling api
  for label in labels:
    try: 
      git.addLabel({ k:label.get(k,"") for k in ['name','color','description'] }, repo_to, token)
    except GitError:
      pass