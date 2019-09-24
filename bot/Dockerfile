FROM python:3-alpine

RUN apk add --update gcc musl-dev libffi-dev openssl-dev

ADD tools /src/tools
ADD bot /src/bot

RUN cd /src/tools && python setup.py install
RUN cd /src/bot && python setup.py install

CMD ["code-review-bot"]
