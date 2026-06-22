FROM python:3.14.5-slim

ADD tools /src/tools
ADD backend /src/backend

# Setup tools
RUN cd /src/tools && pip install --disable-pip-version-check --no-cache-dir --quiet .

WORKDIR /src/backend

# Activate Django settings for in docker image
ENV DEBUG=false

RUN pip install --disable-pip-version-check --no-cache-dir --quiet .

ENTRYPOINT ["/src/backend/docker/entrypoint.sh"]
