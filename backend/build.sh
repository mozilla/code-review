#!/bin/sh
COMMIT_SHA=$1
VERSION=$2
SOURCE=$3
CHANNEL=$4

# Create a version.json per https://github.com/mozilla-services/Dockerflow/blob/master/docs/version_object.md
printf '{"commit": "%s", "version": "%s", "source": "%s", "build": "%s"}\n' \
"$COMMIT_SHA" \
"$VERSION" \
"$SOURCE" \
"${TASKCLUSTER_ROOT_URL}/tasks/${TASK_ID}" > backend/code_review_backend/version.json

taskboot --target /code-review build --image mozilla/code-review --tag "$CHANNEL" --tag "$COMMIT_SHA" --write /backend.tar backend/Dockerfile
