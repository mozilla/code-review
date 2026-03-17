FROM node:16-alpine

# Add worker user
RUN mkdir -p /builds/worker/artifacts && \
    delgroup $(grep ":1000:" /etc/group | cut -d: -f1) 2>/dev/null || true && \
    deluser $(grep ":1000:" /etc/passwd | cut -d: -f1) 2>/dev/null || true && \
    addgroup -g 1000 worker && \
    adduser -u 1000 -G worker -h /builds/worker -s /bin/bash -D worker && \
    chown -R worker:worker /builds/worker

RUN apk add --no-cache git bash lcms2-dev libpng-dev autoconf build-base coreutils shadow python3

# %include-run-task

ENV SHELL=/bin/bash \
    HOME=/builds/worker \
    PATH=/builds/worker/.local/bin:$PATH

VOLUME /builds/worker/checkouts
VOLUME /builds/worker/.cache

CMD ["/bin/bash"]
