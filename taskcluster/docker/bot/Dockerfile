FROM python:3.7-alpine
# %include tools
# %include bot
COPY topsrcdir/tools /src/tools
COPY topsrcdir/bot /src/bot

RUN /src/bot/docker/bootstrap.sh

CMD ["code-review-bot"]
