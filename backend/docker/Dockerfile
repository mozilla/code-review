FROM python:3.14.7-slim

ADD backend /src/backend

# System dependencies
RUN apt-get update && apt-get install -q --yes netcat-openbsd

WORKDIR /src/backend

# Activate Django settings for in docker image
ENV DEBUG=false

RUN pip install --disable-pip-version-check --no-cache-dir --quiet .

# Collect all static files
RUN ./manage.py collectstatic --no-input

ENTRYPOINT ["/src/backend/docker/entrypoint.sh"]
