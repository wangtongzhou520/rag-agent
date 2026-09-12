# syntax=docker/dockerfile:1.7

FROM ghcr.io/astral-sh/uv:0.12.7 AS uv

FROM python:3.13-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy
WORKDIR /app

COPY --from=uv /uv /uvx /bin/
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY app ./app
COPY mcp_server ./mcp_server
COPY scripts ./scripts
COPY config ./config
COPY evals ./evals
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

FROM python:3.13-slim AS runtime

ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

RUN groupadd --system --gid 10001 ragent \
    && useradd --system --uid 10001 --gid ragent --home-dir /app ragent
COPY --from=builder --chown=ragent:ragent /app /app
RUN mkdir -p /app/resources/uploads \
    && chown -R ragent:ragent /app/resources

USER ragent
EXPOSE 9090

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9090"]
