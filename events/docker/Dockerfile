FROM python:3-slim

ADD events /src

RUN cd /src && pip install --disable-pip-version-check --no-cache-dir -r requirements.txt && python setup.py install

RUN /src/docker/bootstrap.sh

CMD ["code-review-events"]
