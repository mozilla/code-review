FROM python:3.9.1-slim

ADD tools /src/tools
RUN cd /src/tools && python setup.py install

ADD bot /src/bot
RUN cd /src/bot && python setup.py install

CMD ["code-review-bot"]
