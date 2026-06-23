#!/usr/bin/env bash
# This file is the entrypoint for the backend container.

# Make non-zero exit codes & other errors fatal.
set -euo pipefail

# Ensure the database accepts connections
echo "Checking database status at $DATABASE_URL"
while ! nc -z db 5432; do
    echo "-----> Waiting for PostgreSQL server to be ready"
    sleep 1;
done
echo "-----> PostgreSQL service is available"

# Run the migrations
./manage.py migrate --noinput

gunicorn code_review_backend.app.wsgi
