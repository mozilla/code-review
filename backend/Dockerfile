FROM python:3.7-slim

ADD backend /src/backend

WORKDIR /src/backend

# Activate Django settings for in docker image
ENV DJANGO_DOCKER=true

RUN pip install --disable-pip-version-check --no-cache-dir --quiet .

# Collect all static files
RUN ./manage.py collectstatic --no-input

CMD gunicorn code_review_backend.app.wsgi
