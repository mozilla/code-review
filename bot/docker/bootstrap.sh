#!/bin/sh

# Add build deps
apk --update add --virtual build-dependencies gcc musl-dev libffi-dev openssl-dev

# Install python dependencies
cd /src/tools && python setup.py install
cd /src/bot && python setup.py install

# Cleanup
apk del build-dependencies
rm -rf /var/cache/apk/*
