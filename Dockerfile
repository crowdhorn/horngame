FROM python:2.7-slim
MAINTAINER Tancrède Lepoint "tancrede.lepoint@sri.com"

#
# Install openjdk-8 on Debian Jessie
#
RUN echo "deb http://ftp.debian.org/debian jessie-backports main" >> /etc/apt/sources.list
RUN apt-get -y update 
RUN apt-get -y -t jessie-backports install "openjdk-8-jre"

#
# Install wget, unzip and gcc (gcc is required by subprocess32)
#
RUN apt-get install -y wget unzip gcc

#
# Install scala 2.11.8
#
WORKDIR /tmp
RUN wget -q www.scala-lang.org/files/archive/scala-2.11.8.deb
RUN dpkg -i scala-2.11.8.deb
ENV SCALA_HOME /usr/share/scala
ENV PATH /usr/share/scala/bin:$PATH

#
# Install eldarica in /eldarica
#
RUN mkdir /eldarica
WORKDIR /eldarica
RUN wget -q https://github.com/jayhorn/eldarica/releases/download/hgame0.4/eldarica.zip
RUN unzip eldarica.zip 
ENV ELDARICA_PATH /eldarica

#
# Install the flask app
#
WORKDIR /app

COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt

COPY . .
RUN pip install --editable .

ENV FLASK_APP horngame
ENV FLASK_DEBUG 1
RUN flask initdb
RUN flask populatedb 

EXPOSE 8081
ENTRYPOINT ["flask", "run", "--host", "0.0.0.0", "--port", "8081"]
