FROM python:3

ADD events /src

RUN cd /src && pip install -r requirements.txt && python setup.py install

RUN /src/docker/bootstrap.sh

CMD ["code-review-events"]
