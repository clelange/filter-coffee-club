FROM node:22-alpine AS frontend-builder
WORKDIR /src/frontend
RUN corepack enable
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm exec svelte-kit sync && pnpm build

FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/backend \
    FCC_DATA_DIR=/data \
    FCC_FRONTEND_DIR=/app/frontend/build
WORKDIR /app
COPY pyproject.toml README.md alembic.ini ./
COPY backend/ backend/
COPY migrations/ migrations/
COPY scripts/start.sh scripts/start.sh
COPY --from=frontend-builder /src/frontend/build frontend/build
RUN apt-get update \
    && apt-get install --no-install-recommends -y sqlite3 \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir . \
    && groupadd --system fcc \
    && useradd --system --gid fcc --home-dir /app fcc \
    && mkdir -p /data \
    && chown -R fcc:fcc /data \
    && chmod +x scripts/start.sh
USER fcc
EXPOSE 8000
VOLUME ["/data"]
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=2)"]
ENTRYPOINT ["/app/scripts/start.sh"]
