FROM python:3.13.2-slim

RUN pip install setuptools==74.1.2 --disable-pip-version-check --no-cache-dir --quiet

ADD tools /src/tools
RUN cd /src/tools && python setup.py install

ADD bot /src/bot
RUN cd /src/bot && python setup.py install

# Add mercurial & robustcheckout
RUN /src/tools/docker/bootstrap-mercurial.sh

CMD ["code-review-bot"]
