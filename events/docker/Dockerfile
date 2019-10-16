FROM python:3.7-slim

ADD tools /src/tools
ADD events /src/events

RUN cd /src/tools && python setup.py install
RUN cd /src/events && python setup.py install

RUN /src/events/docker/bootstrap.sh

CMD ["code-review-events"]
