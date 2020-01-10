FROM python:3.8-slim

ADD tools /src/tools
ADD events /src/events

RUN cd /src/tools && python setup.py install
RUN cd /src/events && python setup.py install

RUN /src/tools/docker/bootstrap-mercurial.sh

CMD ["code-review-events"]
