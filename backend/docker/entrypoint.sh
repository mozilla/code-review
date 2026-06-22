#!/usr/bin/env bash
# This file is the entrypoint for the backend container.

# Make non-zero exit codes & other errors fatal.
set -euo pipefail

# Run the migrations
./manage.py migrate --noinput

gunicorn code_review_backend.app.wsgi
