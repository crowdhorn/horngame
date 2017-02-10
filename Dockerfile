FROM python:2.7-slim
MAINTAINER Tancrède Lepoint "tancrede.lepoint@sri.com"

RUN echo "deb http://ftp.de.debian.org/debian jessie-backports main" >> /etc/apt/sources.list
RUN apt-get -y update 
RUN apt-get install -y wget unzip openjdk-8-jdk ant gcc

RUN mkdir /scala
WORKDIR /scala
RUN wget www.scala-lang.org/files/archive/scala-2.11.8.deb
RUN dpkg -i scala-2.11.8.deb
ENV SCALA_HOME /usr/share/scala
ENV PATH /usr/share/scala/bin:$PATH

RUN mkdir /eldarica
WORKDIR /eldarica
RUN wget https://github.com/jayhorn/eldarica/releases/download/hgame0.4/eldarica.zip
RUN unzip eldarica.zip 
ENV ELDARICA_PATH /eldarica

WORKDIR /app

ENV FLASK_APP horngame
ENV FLASK_DEBUG 1

COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt

COPY . .
RUN pip install --editable .

RUN flask initdb
RUN flask populatedb 

EXPOSE 8081
ENTRYPOINT ["flask", "run", "--host", "0.0.0.0", "--port", "8081"]
