# syntax=docker/dockerfile:1
# League Lab's read-only API + the phone web app, one image, one deploy (plan D7).
# Build from the REPOSITORY ROOT (it needs app/lib and web/):
#   docker build -f api/Dockerfile -t league-lab-web .
#   docker run -p 8000:8000 -e LEAGUE_LAB_APP_DB_URL=... -e LEAGUE_LAB_APP_PASSWORD=... league-lab-web
# Render / Fly / Railway / Cloud Run all build this file; they pass $PORT.

FROM node:22-slim AS web
WORKDIR /src/web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv
WORKDIR /srv/api
COPY api/pyproject.toml api/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY api/league_lab_api ./league_lab_api
# the Streamlit app's own card / week / signals code, loaded unchanged by league_lab_api/applib.py
COPY app/lib /srv/app/lib
COPY --from=web /src/web/dist /srv/web/dist
ENV PATH="/srv/api/.venv/bin:$PATH" PYTHONUNBUFFERED=1 LEAGUE_LAB_WEB_DIST=/srv/web/dist
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn league_lab_api.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
