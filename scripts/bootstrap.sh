#!/usr/bin/env bash
# League Lab one-shot local setup for macOS (Apple Silicon, Homebrew PostgreSQL 17).
#
#   ./scripts/bootstrap.sh            # start PG17, create roles/db, uv sync, pilot ingest, dbt build
#   ./scripts/bootstrap.sh --full     # same, but ingest every season from LEAGUE_LAB_SEASONS_START
#   ./scripts/bootstrap.sh --skip-ingest
#
# Re-runnable: every step is idempotent. Secrets are generated once into .env (git-ignored).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
MODE="pilot"
for arg in "$@"; do
  case "$arg" in
    --full) MODE="full" ;;
    --skip-ingest) MODE="skip" ;;
    -h|--help) sed -n '2,9p' "$0"; exit 0 ;;
    *) echo "unknown flag: $arg" >&2; exit 2 ;;
  esac
done

step() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
ok()   { printf '\033[1;32m    ok:\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m    warn:\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m    error:\033[0m %s\n' "$*" >&2; exit 1; }

# --- 0. prerequisites ---------------------------------------------------------------
step "Checking prerequisites"
export PATH="/opt/homebrew/bin:$HOME/.local/bin:$PATH"   # Apple Silicon Homebrew + uv, even from a non-login shell
command -v brew >/dev/null || die "Homebrew not found. Install from https://brew.sh then re-run."
if [ -x /opt/homebrew/opt/postgresql@17/bin/psql ]; then
  export PATH="/opt/homebrew/opt/postgresql@17/bin:$PATH"
elif ! command -v psql >/dev/null; then
  warn "postgresql@17 not found; installing with Homebrew"
  brew install postgresql@17
  export PATH="/opt/homebrew/opt/postgresql@17/bin:$PATH"
fi
ok "psql: $(psql --version)"

if ! command -v uv >/dev/null; then
  warn "uv not found; installing with Homebrew"
  brew install uv
fi
ok "uv: $(uv --version)"

# --- 1. PostgreSQL service ------------------------------------------------------------
step "Starting PostgreSQL 17 (brew services)"
if pg_isready -q -h localhost -p 5432; then
  ok "a server already answers on localhost:5432"
else
  brew services start postgresql@17 || die "brew services start failed; try: brew services restart postgresql@17"
  for i in $(seq 1 30); do
    pg_isready -q -h localhost -p 5432 && break
    sleep 1
  done
  pg_isready -q -h localhost -p 5432 || die "PostgreSQL did not come up on localhost:5432. Check: brew services list; tail /opt/homebrew/var/log/postgresql@17.log"
  ok "PostgreSQL is accepting connections"
fi
# Homebrew creates a superuser named after your macOS user with no password.
psql -d postgres -Atc "select 1" >/dev/null 2>&1 || die "Cannot connect to the 'postgres' maintenance database as $(whoami). If your cluster was initialised with a different superuser, run: psql -U <superuser> -d postgres -f scripts/init_db.sql manually, then re-run with --skip-ingest."

# --- 2. secrets (.env) ----------------------------------------------------------------
step "Configuring .env"
if [ ! -f .env ]; then
  PIPELINE_PW="$(openssl rand -hex 16)"
  APP_PW="$(openssl rand -hex 16)"
  sed -e "s|^LEAGUE_LAB_DB_PASSWORD=.*|LEAGUE_LAB_DB_PASSWORD=${PIPELINE_PW}|" \
      -e "s|^LEAGUE_LAB_APP_DB_PASSWORD=.*|LEAGUE_LAB_APP_DB_PASSWORD=${APP_PW}|" \
      -e "s|^# LEAGUE_LAB_DATA_DIR=.*|LEAGUE_LAB_DATA_DIR=${ROOT}/data|" \
      .env.example > .env
  chmod 600 .env
  ok "wrote .env with generated passwords (kept out of git)"
else
  ok ".env already exists; keeping it"
fi
# shellcheck disable=SC1091
set -a; source .env; set +a

# --- 3. roles, database, schemas, grants -----------------------------------------------
step "Creating roles/database/schemas (scripts/init_db.sql)"
psql -v ON_ERROR_STOP=1 -q -d postgres \
  -v pipeline_pw="'${LEAGUE_LAB_DB_PASSWORD}'" -v app_pw="'${LEAGUE_LAB_APP_DB_PASSWORD}'" \
  -f scripts/init_db.sql
ok "league_lab database, league_lab_pipeline and league_lab_app roles are ready"

# --- 4. python environment --------------------------------------------------------------
step "Installing Python 3.13 environment with uv (uv sync --locked)"
uv python install 3.13 >/dev/null
uv sync --locked
ok "virtualenv ready: .venv"

# --- 5. schemas + ops tables, connectivity checks -----------------------------------------
step "Migrating ops schema and checking both roles"
uv run league-lab db migrate
uv run league-lab db check

# --- 6. data ------------------------------------------------------------------------------
if [ "$MODE" != "skip" ]; then
  step "Ingesting Sleeper league history"
  uv run league-lab ingest sleeper || warn "some Sleeper partitions failed (see table above); continuing"
  CURRENT_SEASON="$(uv run python -c 'from league_lab.ingest.nflverse import current_nfl_season; print(current_nfl_season())')"
  if [ "$MODE" = "full" ]; then
    step "Ingesting nflverse ${LEAGUE_LAB_SEASONS_START:-2016}-${CURRENT_SEASON} (this downloads ~60 files)"
    uv run league-lab ingest nfl || warn "some nflverse partitions failed; continuing"
  else
    PILOT="$((CURRENT_SEASON-1)),${CURRENT_SEASON}"
    step "Ingesting nflverse pilot seasons ${PILOT} (run ./scripts/bootstrap.sh --full for 2016+)"
    uv run league-lab ingest nfl --seasons "$PILOT" || warn "some nflverse partitions failed; continuing"
  fi

  step "Building dbt models and running tests"
  uv run league-lab dbt deps
  uv run league-lab dbt build
fi

step "Done"
cat <<EOF
    Explorer:   make app          (opens http://127.0.0.1:8501)
    Status:     make status
    Refresh:    make refresh      (Sleeper + current NFL season + dbt build)
    Full history: ./scripts/bootstrap.sh --full   (or: make backfill)
    Docs:       docs/SETUP_RUNBOOK.md, docs/PROJECT_PLAN.md, docs/STATUS.md
EOF
