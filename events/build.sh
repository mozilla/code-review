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
"${TASKCLUSTER_ROOT_URL}/tasks/${TASK_ID}" > events/code_review_events/version.json

# Run 'taskboot build' with our local copy of the Git repository where we updated the version.json with correct values.
# To do so, we use '--target /path/to/existing/clone' instead of passing environment variables (GIT_REPOSITORY, GIT_REVISION)
# to taskboot that would activate an automated clone.
taskboot --target /code-review build --image mozilla/code-review --tag "$CHANNEL" --tag "$COMMIT_SHA" --write /events.tar events/docker/Dockerfile
