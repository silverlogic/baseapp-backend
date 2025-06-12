ARG PYTHON_VERSION=3.11.6
FROM --platform=linux/amd64 python:${PYTHON_VERSION}-bookworm

ENV DEBIAN_FRONTEND noninteractive
RUN apt-get update -qq 
RUN apt-get install -y libjpeg62-turbo libjpeg62-turbo-dev libfreetype6 libfreetype6-dev zlib1g-dev
RUN apt-get install -y libgeos-dev libgeos3.11.1 libgeos-c1v5 gdal-bin gettext
RUN apt-get install -y proj-bin libproj-dev libproj25
RUN apt-get install -y locales -qq

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        wget \
        ca-certificates \
        apt-transport-https \
        gnupg \
        chromium && \
    wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - && \
    echo "deb [arch=amd64] https://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google.list && \
    apt-get update -y && \
    apt-get install -y --no-install-recommends google-chrome-stable && \
    rm -rf /etc/apt/sources.list.d/google.list

RUN mkdir -p /usr/src/app

COPY . /usr/src/app

WORKDIR /usr/src/app

RUN pip install --no-cache-dir -r testproject/requirements.txt

EXPOSE 8000
CMD ["sleep", "infinity"]
