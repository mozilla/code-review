FROM python:3.7-slim

ADD tools /src/tools
ADD integration /src/integration

RUN pip install --disable-pip-version-check --no-cache-dir --quiet /src/tools
RUN pip install --disable-pip-version-check --no-cache-dir --quiet -r /src/integration/requirements.txt

# Setup mercurial
RUN /src/tools/docker/bootstrap-mercurial.sh
RUN ln -s /src/integration/docker/hgrc /etc/mercurial/hgrc.d/code-review.rc

# Setup arc
RUN /src/integration/docker/bootstrap-arc.sh
ENV PATH="$PATH:/opt/arcanist/bin/"

CMD ["/src/integration/run.py"]
