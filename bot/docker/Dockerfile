FROM python:3.8.0-alpine

ADD tools /src/tools
ADD bot /src/bot

RUN /src/bot/docker/bootstrap.sh

CMD ["code-review-bot"]
