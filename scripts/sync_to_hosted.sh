#!/usr/bin/env bash
# Push the explorer's marts to a hosted Postgres (plan S-03 / P4-01).
#
# What goes:  the analytics relations the explorer and packs reference (derived from the code),
#             every analytics view and its dependencies, analytics_seeds, ops.
# What never goes: raw, staging, intermediate, play-level tables — the hosted copy is ~280 MB, not 3.5 GB.
#
# Publishing drops the previous copy, then restores the new one in a single transaction. Free
# tiers (Neon 0.5 GB) cannot hold two copies at once, so the swap is not atomic: for the length
# of the restore (a minute or two) pages show "marts not built yet" rather than failing.
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
# What to publish: every analytics relation the explorer or the weekly packs reference (read from
# the code, so a new page's mart is picked up automatically), plus every analytics view and the
# tables those views depend on, plus the seeds and ops schemas. Play-level tables (fct_play, the
# bridges, fct_play_charting) are never referenced by a page and stay local.
used="$(grep -rhoE 'analytics\.[a-z_]+' app/*.py app/pages/*.py app/lib/*.py src/league_lab/reports.py | sed 's/analytics\.//' | sort -u)"
closure="$(psql "$LOCAL_DSN" -At -v ON_ERROR_STOP=1 <<SQL
with used(name) as (select unnest(string_to_array('$(echo "$used" | tr '\n' ',' | sed 's/,$//')', ','))),
views as (select c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace where n.nspname = 'analytics' and c.relkind = 'v'),
view_deps as (
  select distinct d2.relname
  from pg_class v join pg_namespace n on n.oid = v.relnamespace
  join pg_rewrite r on r.ev_class = v.oid
  join pg_depend dp on dp.objid = r.oid and dp.classid = 'pg_rewrite'::regclass
  join pg_class d2 on d2.oid = dp.refobjid join pg_namespace n2 on n2.oid = d2.relnamespace
  where n.nspname = 'analytics' and v.relkind = 'v' and n2.nspname = 'analytics' and d2.oid <> v.oid)
select distinct name from (select name from used union select relname from views union select relname from view_deps) x
join pg_class c on c.relname = x.name join pg_namespace n on n.oid = c.relnamespace and n.nspname = 'analytics'
order by 1
SQL
)"
TABLE_ARGS=()
for t in $closure; do TABLE_ARGS+=(--table "analytics.$t"); done
echo "publishing $(echo "$closure" | wc -l | tr -d ' ') analytics relations the pages read (of $(psql "$LOCAL_DSN" -At -c "select count(*) from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='analytics' and relkind in ('r','v')"))"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
DUMP="$TMP/marts.sql.gz"

echo "dumping marts from the local database ..."
# (with --table given, pg_dump ignores --schema and emits no CREATE SCHEMA, so the other schemas
# are selected by table pattern and the schemas are created explicitly before the restore)
pg_dump "$LOCAL_DSN" --format=plain --no-owner --no-privileges --no-comments \
        --table 'analytics_seeds.*' --table 'ops.*' "${TABLE_ARGS[@]}" | gzip -1 > "$DUMP"
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

# Free tiers cap the project at ~0.5 GB, and a drop inside the same transaction as the restore
# does not free space until commit - so the old copy is dropped first (its own transaction) and
# the new one restored right after. Between the two, pages say "marts not built yet" instead of
# failing; the window is the restore time, printed below.
echo "publishing: dropping the previous copy, then restoring (pages show 'not built yet' meanwhile) ..."
t0=$(date +%s)
psql "$LEAGUE_LAB_HOSTED_ADMIN_URL" -v ON_ERROR_STOP=1 -q -c "drop schema if exists analytics cascade; drop schema if exists analytics_seeds cascade; drop schema if exists ops cascade;"
{
  echo "create schema if not exists analytics; create schema if not exists analytics_seeds; create schema if not exists ops;"
  gunzip -c "$DUMP"
  cat <<'SQL'
grant usage on schema analytics, analytics_seeds, ops to league_lab_app;
grant select on all tables in schema analytics to league_lab_app;
grant select on all tables in schema analytics_seeds to league_lab_app;
grant select on all tables in schema ops to league_lab_app;
SQL
} | psql "$LEAGUE_LAB_HOSTED_ADMIN_URL" -v ON_ERROR_STOP=1 -q --single-transaction
echo "restored in $(( $(date +%s) - t0 )) s"

echo "verifying ..."
psql "$LEAGUE_LAB_HOSTED_ADMIN_URL" -v ON_ERROR_STOP=1 -At -c "
  select 'analytics tables: ' || count(*) from information_schema.tables where table_schema = 'analytics';" \
  -c "select 'published through: ' || coalesce(max(loaded_at)::text, 'n/a') from ops.source_partition;"
echo "done. Point the app at: postgresql://league_lab_app:<password>@<host>/<db>?sslmode=require"
