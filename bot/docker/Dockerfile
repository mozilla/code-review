FROM python:3.14.0-slim

# TODO: remove by switching to modern pyproject.toml
RUN pip install setuptools==74.1.2 --disable-pip-version-check --no-cache-dir --quiet

ADD bot /src/bot
RUN cd /src/bot && python setup.py install

# Add mercurial & robustcheckout
ADD tools/docker /src/tools/docker
RUN /src/tools/docker/bootstrap-mercurial.sh

CMD ["code-review-bot"]
