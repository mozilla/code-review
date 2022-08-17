#!/bin/bash

COMMIT_SHA=$1
VERSION=$2
SOURCE=$3
BUILD_URL=$4
CHANNEL=$5

# create a version.json per https://github.com/mozilla-services/Dockerflow/blob/master/docs/version_object.md
printf '{"commit": "%s", "version": "%s", "source": "%s", "build": "%s"}\n' \
"$COMMIT_SHA" \
"$VERSION" \
"$SOURCE" \
"$BUILD_URL" > backend/code_review_backend/version.json

taskboot build --image mozilla/code-review --tag "$CHANNEL" --tag "$COMMIT_SHA" --write /backend.tar backend/Dockerfile