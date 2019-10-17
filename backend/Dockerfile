FROM python:3.7-slim

ADD backend /src/backend

RUN cd /src/backend && pip install --no-cache-dir .
RUN pip install --no-cache-dir gunicorn

CMD gunicorn code_review_backend.app.wsgi
