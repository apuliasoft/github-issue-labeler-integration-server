FROM ubuntu:16.04

MAINTAINER Vito Tafuni "vito.tafuni@apuliasoft.com"

RUN apt-get update -y && \
    apt-get install -y python-pip python-dev

COPY ./ansible/files/requirements.txt /app/requirements.txt

WORKDIR /app

RUN pip install -r requirements.txt

ENTRYPOINT [ "python" ]

CMD [ "src/app.py" ]
