# Integration Service for OpenReq classifier
This project is a simple IS for interfacing with [OpenReq](https://github.com/OpenReqEU/requirements-classifier) requirements classifier.
Once launched locally or deployed remotely, it let you classify issues of GIT repositories.

## Project requirements
In order to deploy the IS correctly you have to follow these steps:

### Create GitHub App 
Follow steps on [GitHub](https://developer.github.com/apps/building-oauth-apps/authorizing-oauth-apps/) to get a working **GitHub App** in your developer account.
Point the following route to these endpoints:

- **Homepage URL**: SERVER_IP:PORT
- **User authorization callback URL**: SERVER_IP:PORT/auth
- **Webhook URL**: SERVER_IP:PORT/webhook

> **Note:** When developing on your machine you can use `http://localhost:5000` as `SERVER_IP` for all fields except webhook for which you need to use a connection forwarder like ngrok. More info on next section.

### Create private key
A private key for the GitHub App is required in order to make calls server to server.
In the app settings page go to section **Private keys**, click on **Generate a private key** and then copy it on your computer or server then set the proper field in configuration file to set the path accordingly.

### Create config file
Once the app is created put a `config.py` in the `app` folder with these values compiled from the info you can get in the app settings page:

```
SECRET_KEY = "super secret key for the flask app"
DEBUG = True
TRAINING_TIMEOUT = 1800
CLASSIFICATION_TIMEOUT = 1800
CONFIDENCE_TRESHOLD = 50

LOG_PATH = "/var/log/is.log"
LOG_FORMAT = "%(asctime)s - %(pathname)s:%(lineno)d - %(levelname)s - %(message)s"

GITHUB_WEBHOOK_SECRET = ""
GITHUB_CLIENT_ID = ""
GITHUB_CLIENT_SECRET = ""
GITHUB_APP_ID = ""
GITHUB_PERSONAL_ACCESS_TOKEN = ""
GITHUB_PRIV_KEY_PATH = "path to private key pem file"

OPENREQ_BASEURL = "OPENREQHOST:port"

SQLALCHEMY_DATABASE_URI = 'sqlite:////path/to/a/db/file.db'
SQLALCHEMY_TRACK_MODIFICATIONS = False

CELERY_BROKER_URL = 'REDISHOST:port'
``` 


## Deploy
Once requirements are met you can choose to deploy using two different setups based on your needs.

### Remote setup - ansible
Remote setup is ideal for production environment when you can configure a dedicated host.
Prepare an host with ssh installed and an ansible user.
Create a file named "hosts" in the root of the ansible playbook and change `SERVER_IP` with the right IP address
```
[web]
SERVER_IP
```
then type in the terminal:

```
$ ansible-playbook -i hosts main.yml
```

> **Note:** Default configuration install app in the root of nginx

### Local setup - docker
Docker setup is the best for development projects.
To get a working docker image with the flask project build first the image with:

```
$ docker build -f docker/Dockerfile -t is:latest .
```

Then launch from your terminal using the docker-compose provided:

```
$ docker-compose up
```

And you will get a working version running on port 5000 with app folder mounted in /app and a complete environment with redis db and celery workers for async tasks.

> **Note:** Remove debug flag in config.py for production (you will loose reloading feature on flask).

#### Setup ngrok port forwarding for webhook
Follow the good guide at [GitHub](https://developer.github.com/webhooks/configuring/#using-ngrok) to install and setup ngrok.
This way you can forward remote calls to your localhost endpoints without the need to use dynamic DNS or port forwarding or proxy.

> **Note:** Just remember to update SERVER_IP:PORT configuration for webhooks in your GitHub App settings page

### Celery workers
IS app use asynchronous tasks in order to avoid timeout when calling training and classification endpoints.
[Celery](http://www.celeryproject.org/) framework is correctly configured in docker-compose but you can always start a new worker instance issuing the command directly from the app folder:

```
celery -A app.celery worker -l debug
```

> **Note:** If you want to monitor Celery tasks from a web interface install [Celery Flower](https://flower.readthedocs.io/en/latest/)
