# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:0.12.1 AS uv

FROM python:3.14-slim-bookworm AS builder
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_COMPILE_BYTECODE=1
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev --no-install-project

FROM python:3.14-slim-bookworm AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    DATABASE_PATH=/app/data/vocabulary.sqlite3
WORKDIR /app
RUN groupadd --gid 10001 bot \
    && useradd --uid 10001 --gid bot --no-create-home --shell /usr/sbin/nologin bot \
    && mkdir /app/data /app/logs \
    && chown bot:bot /app/data /app/logs
COPY --from=builder /app/.venv /app/.venv
COPY bot ./bot
USER 10001:10001
CMD ["python", "-m", "bot"]
