# The hosted demo: one container with Postgres inside it, holding a 60-day simulated desk built when the image is.
FROM node:26-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund --ignore-scripts
COPY web/ ./
RUN npm run build

FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src LC_ALL=C.UTF-8 LANG=C.UTF-8
RUN apt-get update && apt-get install -y --no-install-recommends postgresql postgresql-contrib curl && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.13 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
COPY migrations ./migrations
COPY scripts/docker-start.sh scripts/docker-build-demo.sh ./scripts/
COPY --from=web /web/dist ./web/dist
ENV DATABASE_URL=postgres://postgres@127.0.0.1:5432/outbound PUBLIC_DEMO=1 HOST=0.0.0.0 PORT=8800 \
    PUBLIC_URL=https://outbound-desk.onrender.com
# The demo database is built here, once, so starting the container takes seconds instead of minutes.
RUN chmod +x scripts/*.sh && mkdir -p /data && chown postgres /data && NO_WORKER=1 ./scripts/docker-build-demo.sh
EXPOSE 8800
HEALTHCHECK CMD curl -sf localhost:8800/api/health || exit 1
CMD ["./scripts/docker-start.sh"]
