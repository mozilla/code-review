FROM python:3.12.0-slim

ADD tools /src/tools
RUN cd /src/tools && python setup.py install

ADD bot /src/bot
RUN cd /src/bot && python setup.py install

# Add mercurial & robustcheckout
RUN /src/tools/docker/bootstrap-mercurial.sh

CMD ["code-review-bot"]
