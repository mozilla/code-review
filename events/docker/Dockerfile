FROM python:3.8.2-slim

ADD tools /src/tools
ADD events /src/events

RUN cd /src/tools && python setup.py install
RUN cd /src/events && python setup.py install

RUN /src/tools/docker/bootstrap-mercurial.sh

# Setup jemalloc to manage Ram more efficiently on Heroku
ENV LD_PRELOAD="libjemalloc.so.2"
ENV MALLOC_CONF="narenas:1,tcache:false,background_thread:false,dirty_decay_ms:0,muzzy_decay_ms:0"

CMD ["code-review-events"]
