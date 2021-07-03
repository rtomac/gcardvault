FROM python:3.9-alpine

RUN apk add --no-cache bash git

COPY dist/gcardvault-latest.tar.gz /usr/local/src/

RUN cd /usr/local/src \
    && pip install gcardvault-latest.tar.gz[test] \
    && mkdir -p /root/gcardvault

WORKDIR /root/gcardvault
ENTRYPOINT [ "gcardvault" ]
