# syntax=docker/dockerfile:1.7
# Optional local verification target: native Docker-filtered context, not runtime.
FROM scratch AS context-audit
COPY . /

FROM ghcr.io/astral-sh/uv:0.8.13 AS uv

FROM python:3.12.11-slim-bookworm AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

RUN groupadd --system --gid 10001 fleet \
    && useradd --system --uid 10001 --gid fleet --home-dir /app fleet

WORKDIR /app
COPY --from=uv /uv /uvx /bin/
COPY services/api/pyproject.toml services/api/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY services/api/alembic.ini ./alembic.ini
COPY services/api/migrations ./migrations
COPY services/api/src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev \
    && chown -R fleet:fleet /app

USER fleet
EXPOSE 8000
HEALTHCHECK --interval=20s --timeout=5s --start-period=20s --retries=5 \
  CMD ["python", "-c", "import json,urllib.request; value=json.load(urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)); raise SystemExit(0 if value.get('status') == 'ok' else 1)"]

CMD ["uvicorn", "fleet_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
