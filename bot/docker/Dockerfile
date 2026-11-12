FROM python:3.14.7-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1 \
    UV_PYTHON_DOWNLOADS=never

ADD pyproject.toml uv.lock /src/
ADD bot /src/bot
RUN cd /src && uv sync --frozen --no-dev --no-editable --package code-review-bot
ENV PATH="/src/.venv/bin:$PATH"

# Add mercurial & robustcheckout
ADD tools/docker /src/tools/docker
RUN /src/tools/docker/bootstrap-mercurial.sh

CMD ["code-review-bot"]
