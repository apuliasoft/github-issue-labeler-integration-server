# Integration Service for OpenReq classifier
This is a simple IS for interfacing with [OpenReq](https://github.com/OpenReqEU/requirements-classifier) requirements classifier.
Once launched locally or deployed remotely, it let you ask for classifing issues of a GIT repository...

## Project requirements
In order to deploy the IS correctly you have to follow these steps:

### Create GitHub App 
Follow steps on [GitHub](https://developer.github.com/apps/building-oauth-apps/authorizing-oauth-apps/) to get a working **GitHub App** in your developer account.
Point the following route to these endpoints:

- **Homepage URL**: SERVER_IP
- **User authorization callback URL**: SERVER_IP/auth
- **Webhook URL**: SERVER_IP/webhook

> **Note:** When developing on your machine you can use `http://localhost:5000` as `SERVER_IP`.

### Create private key
A private key for the GitHub App is required in order to make calls server to server.
In the app settings page go to section **Private keys**, click on **Generate a private key** and then copy it in the root of the `app` folder named as `private-key.pem`

### Create config file
Once the app is created put a `config.py` in the `app` folder with these values compiled from the info you can get in the app settings page:

```
SECRET_KEY = "super secret key for the flask app"
APP_ID = ""
CLIENT_ID = ""
CLIENT_SECRET = ""
WEBHOOK_SECRET = ""
``` 


## Deploy
Once requirements are met you can choose to deploy using two different setups based on your needs.

### Ansible Setup
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

### Docker Setup
To get a working docker image with the flask project build first the image with:

```
$ docker build -f docker/Dockerfile -t is:latest .
```

Then launch from your terminal with the command:

```
$ docker run -p 5000:5000 -v $(pwd)/app:/app/src is
```

And you will get a working version running on port 5000 with app folder mounted in /app/src.
> **Note:** Remove debug flag in app.py for production (you will loose reloading feature on flask).

#### Setup ngrok port forwarding
https://developer.github.com/webhooks/configuring/#using-ngrok