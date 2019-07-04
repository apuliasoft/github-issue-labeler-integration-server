FROM python:3-slim

MAINTAINER Vito Tafuni "vito.tafuni@apuliasoft.com"

COPY ./ansible/files/requirements.txt /tmp/requirements.txt
COPY ./app /app
RUN pip install -r /tmp/requirements.txt

WORKDIR /app

CMD python app.py