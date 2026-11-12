FROM python:3.15.0-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1 \
    UV_PYTHON_DOWNLOADS=never

ADD pyproject.toml uv.lock /src/
ADD integration /src/integration
RUN cd /src && uv sync --frozen --no-dev --package code-review-integration
ENV PATH="/src/.venv/bin:$PATH"

# Setup mercurial
ADD tools/docker /src/tools/docker
RUN /src/tools/docker/bootstrap-mercurial.sh

CMD ["/src/integration/run.py"]
