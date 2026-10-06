# syntax=docker/dockerfile:1
# League Lab's read-only API + the phone web app, one image, one deploy (plan D7).
# Build from the REPOSITORY ROOT (it needs app/, src/ and web/):
#   docker build -f api/Dockerfile -t league-lab .
#   docker run -p 8080:8080 -e LEAGUE_LAB_APP_DB_URL=... -e LEAGUE_LAB_APP_PASSWORD=... league-lab
# Render (render.yaml, docs/DEPLOY.md) builds this file and passes $PORT; without it the server listens on 8080.
# Plan F3: the same image serves the API for any Sleeper league (src/league_lab: anyleague, sleeper_client, lineup,
# scoring, kdef's K / DEF pricing) and the web app (web/dist: "/" and the app's routes fall back to index.html; /api is
# the API). The Sleeper player directory is cached for a day under LEAGUE_LAB_CACHE_DIR (lost on a redeploy: one call).
# Plan H0 (Wave H): app/pages is in the image (the Waiver Wire's and Trade Finder's sentence functions are read from
# the page files: api/league_lab_api/decisions.py page_functions), the Python environment is built in its own stage
# (no uv, no build cache, no dev dependencies, no package test suites in the image), LEAGUE_LAB_VERSION stamps
# /api/health, .dockerignore keeps data/ and .env out of the build. The stages were
# proven command by command without a Docker daemon: docs/STATUS.md § Wave H, H0.

# ---- 1. the web app (node; thrown away after the build, only web/dist is kept)
FROM node:22-slim AS web
WORKDIR /src/web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

# ---- 2. the Python environment (uv; thrown away after the build, only the .venv is kept)
FROM python:3.13-slim AS py
COPY --from=ghcr.io/astral-sh/uv:0.8.17 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_PYTHON=/usr/local/bin/python3.13
WORKDIR /srv/api
COPY api/pyproject.toml api/uv.lock ./
# the packages' own test suites (pandas, scipy, numpy …: ~86 MB) are never imported by the server
RUN uv sync --frozen --no-dev --no-install-project \
 && find .venv/lib -type d -name tests -prune -exec rm -rf {} +

# ---- 3. the image that runs: Python + the .venv + the code + web/dist, as the unprivileged user
FROM python:3.13-slim
WORKDIR /srv/api
COPY --from=py /srv/api/.venv /srv/api/.venv
COPY api/league_lab_api ./league_lab_api
# the Streamlit app's own card / week / signals code, loaded unchanged by league_lab_api/applib.py, and the two pages
# whose sentence functions league_lab_api/decisions.py compiles from their source (Waiver Wire, Trade Finder)
COPY app/lib /srv/app/lib
COPY app/pages /srv/app/pages
# the league_lab package the cards (decisions) and the on-demand path (anyleague, lineup, scoring) import (plan E3)
COPY src/league_lab /srv/src/league_lab
# Wave I-N: the blog's posts and pictures (docs/BLOG.md: a markdown file in blog/ and a push publishes it) and the
# week's published DFS salary files (docs/DFS.md § "Published slates"); both are read once at start, never written
COPY blog /srv/blog
COPY dfs/slates /srv/dfs/slates
COPY --from=web /src/web/dist /srv/web/dist
# compile the code once now: the server runs as nobody and cannot write __pycache__ next to it
RUN /srv/api/.venv/bin/python -m compileall -q /srv/api/league_lab_api /srv/app /srv/src \
 && mkdir -p /srv/cache && chown nobody:nogroup /srv/cache
ARG LEAGUE_LAB_VERSION=dev
# MALLOC_ARENA_MAX / MALLOC_TRIM_THRESHOLD_ (INF-2, the memory diet): the sync endpoints run on uvicorn's threadpool,
# and glibc would give every thread its own arena — fragmented memory that never returns; two arenas and an eager
# trim keep the process near what it uses (docs/DEPLOY.md § Memory). LEAGUE_LAB_CACHE_MB (default 64) is the caches'
# budget; set it on Render to change it.
ENV PATH="/srv/api/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    LEAGUE_LAB_WEB_DIST=/srv/web/dist LEAGUE_LAB_CACHE_DIR=/srv/cache LEAGUE_LAB_VERSION=${LEAGUE_LAB_VERSION} \
    MALLOC_ARENA_MAX=2 MALLOC_TRIM_THRESHOLD_=131072
USER nobody
EXPOSE 8080
# one process (one Sleeper call budget and one cache per server: docs/SLEEPER_TERMS.md); $PORT from the host, else 8080
# --forwarded-allow-ips='*' makes request.client the FIRST X-Forwarded-For hop, which the client writes: never key a
# limit or a log on request.client — league_lab_api.ratelimit.client_address is the one place that names a visitor
# (Wave I-M, IM-3; docs/SECURITY_PUBLIC.md § 2).
CMD ["sh", "-c", "exec uvicorn league_lab_api.main:app --host 0.0.0.0 --port \"${PORT:-8080}\" --proxy-headers --forwarded-allow-ips='*'"]
