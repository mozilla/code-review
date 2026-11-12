FROM python:3.14.7-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1 \
    UV_PYTHON_DOWNLOADS=never

ADD pyproject.toml uv.lock /src/
ADD backend /src/backend

# System dependencies
RUN apt-get update && apt-get install -q --yes netcat-openbsd

WORKDIR /src/backend

# Activate Django settings for in docker image
ENV DEBUG=false

RUN uv sync --frozen --no-dev --package code-review-backend
ENV PATH="/src/.venv/bin:$PATH"

# Collect all static files
RUN ./manage.py collectstatic --no-input

ENTRYPOINT ["/src/backend/docker/entrypoint.sh"]
