FROM python:3.7-slim

ADD tools /src/tools
ADD events /src/events

RUN cd /src/tools && python setup.py install
RUN cd /src/events && python setup.py install

RUN /src/tools/docker/bootstrap-mercurial.sh
RUN ln -s /src/events/docker/hgrc /etc/mercurial/hgrc.d/code-review.rc

CMD ["code-review-events"]
