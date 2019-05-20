def issuesToRequirements(issues, isForClassify = False):
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
    } for issue in issues if 'pull_request' not in issue for label in issue['labels'] ]


def cplabels(repo_from, repo_to, token):
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
