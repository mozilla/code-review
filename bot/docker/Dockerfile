FROM python:3.10.5-slim

ADD tools /src/tools
RUN cd /src/tools && python setup.py install

ADD bot /src/bot
RUN cd /src/bot && python setup.py install

CMD ["code-review-bot"]
