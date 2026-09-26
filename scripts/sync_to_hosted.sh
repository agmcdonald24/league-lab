#!/usr/bin/env bash
# Push the explorer's marts to a hosted Postgres (plan S-03 / P4-01).
#
# What goes:  schemas analytics (tables + views, minus the play-level tables the pages never read),
#             analytics_seeds, ops (load manifest, partition state, backtest results).
# What never goes: raw, staging, intermediate — the hosted copy is ~400 MB, not 3.5 GB.
#
# The restore runs as ONE transaction (drop schemas -> recreate -> grants), so a viewer either sees
# the previous publication or the new one, never a half-built schema. Readers holding a query open
# delay the swap for as long as that query runs (seconds).
#
# Needs in .env (or the environment):
#   LEAGUE_LAB_HOSTED_ADMIN_URL      owner connection string of the hosted database (Neon/Supabase "postgres" role)
#   LEAGUE_LAB_HOSTED_APP_PASSWORD   password to set for the read-only league_lab_app role on the hosted database
# Usage:  scripts/sync_to_hosted.sh            (or `make sync-hosted`)
#         scripts/sync_to_hosted.sh --dry-run  (dump only, print size)
set -euo pipefail
cd "$(dirname "$0")/.."
# load .env the way the app does (python-dotenv): values with &, ?, spaces or quotes are safe
if [ -f .env ]; then
  set -a
  eval "$(uv run python -c 'import shlex; from dotenv import dotenv_values; [print(f"{k}={shlex.quote(v)}") for k, v in dotenv_values(".env").items() if v is not None]')"
  set +a
fi

: "${LEAGUE_LAB_HOSTED_ADMIN_URL:?set LEAGUE_LAB_HOSTED_ADMIN_URL in .env}"
: "${LEAGUE_LAB_HOSTED_APP_PASSWORD:?set LEAGUE_LAB_HOSTED_APP_PASSWORD in .env}"
LOCAL_DSN="$(uv run python -c 'from league_lab.config import get_settings; print(get_settings().pipeline_dsn())')"
# Roles are cluster-wide: pointing this at the local cluster would rewrite the local app role's
# password. Refuse unless explicitly allowed (only useful for a simulation).
local_host="$(uv run python -c 'from league_lab.config import get_settings; s=get_settings(); print(f"{s.db_host}:{s.db_port}")')"
case "$LEAGUE_LAB_HOSTED_ADMIN_URL" in
  *"@${local_host}/"*|*"@localhost:"*|*"@127.0.0.1:"*)
    if [ "${LEAGUE_LAB_HOSTED_ALLOW_LOCAL:-}" != "1" ]; then
      echo "refusing: LEAGUE_LAB_HOSTED_ADMIN_URL points at the local cluster (${local_host}); set LEAGUE_LAB_HOSTED_ALLOW_LOCAL=1 only for a simulation" >&2
      exit 4
    fi ;;
esac
EXCLUDE=(--exclude-table 'analytics.fct_play' --exclude-table 'analytics.bridge_play_participation'
         --exclude-table 'analytics.bridge_play_actor' --exclude-table 'analytics.fct_play_charting')
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
DUMP="$TMP/marts.sql.gz"

echo "dumping marts from the local database ..."
pg_dump "$LOCAL_DSN" --format=plain --no-owner --no-privileges --no-comments \
        --schema=analytics --schema=analytics_seeds --schema=ops "${EXCLUDE[@]}" | gzip -1 > "$DUMP"
echo "dump: $(du -h "$DUMP" | cut -f1) compressed"
[ "${1:-}" = "--dry-run" ] && exit 0

echo "ensuring the read-only role exists on the hosted database ..."
psql "$LEAGUE_LAB_HOSTED_ADMIN_URL" -v ON_ERROR_STOP=1 -q <<SQL
do \$\$ begin
  if not exists (select 1 from pg_roles where rolname = 'league_lab_app') then
    create role league_lab_app login;
  end if;
end \$\$;
alter role league_lab_app with login password '${LEAGUE_LAB_HOSTED_APP_PASSWORD}';
alter role league_lab_app set default_transaction_read_only = on;
alter role league_lab_app set statement_timeout = '30s';
SQL

echo "publishing (one transaction: drop old marts, restore, grant) ..."
{
  echo "drop schema if exists analytics cascade; drop schema if exists analytics_seeds cascade; drop schema if exists ops cascade;"
  gunzip -c "$DUMP"
  cat <<'SQL'
grant usage on schema analytics, analytics_seeds, ops to league_lab_app;
grant select on all tables in schema analytics to league_lab_app;
grant select on all tables in schema analytics_seeds to league_lab_app;
grant select on all tables in schema ops to league_lab_app;
SQL
} | psql "$LEAGUE_LAB_HOSTED_ADMIN_URL" -v ON_ERROR_STOP=1 -q --single-transaction

echo "verifying ..."
psql "$LEAGUE_LAB_HOSTED_ADMIN_URL" -v ON_ERROR_STOP=1 -At -c "
  select 'analytics tables: ' || count(*) from information_schema.tables where table_schema = 'analytics';" \
  -c "select 'published through: ' || coalesce(max(loaded_at)::text, 'n/a') from ops.source_partition;"
echo "done. Point the app at: postgresql://league_lab_app:<password>@<host>/<db>?sslmode=require"
