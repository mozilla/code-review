FROM python:3.11.3-slim

ADD tools /src/tools
RUN cd /src/tools && python setup.py install

ADD bot /src/bot
RUN cd /src/bot && python setup.py install

CMD ["code-review-bot"]
