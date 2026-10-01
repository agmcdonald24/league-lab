#!/usr/bin/env bash
# Push the explorer's marts to a hosted Postgres (plan S-03 / P4-01).
#
# What goes:  the analytics relations the explorer and packs reference (derived from the code),
#             every analytics view and its dependencies, analytics_seeds, ops.
# What never goes: raw, staging, intermediate, play-level tables — the hosted copy is ~280 MB, not 3.5 GB.
#
# Publishing drops the previous marts, then restores the new copy in a single transaction. Free
# tiers (Neon 0.5 GB) cannot hold two copies of the marts at once, so that swap is not atomic: for
# the length of the restore (a minute or two) pages show "marts not built yet" rather than failing.
# The small `ops` schema (the decision record the nightly restores from here) IS swapped inside
# the transaction, so a failed restore never loses it.
#
# Needs in .env (or the environment):
#   LEAGUE_LAB_HOSTED_ADMIN_URL      owner connection string of the hosted database (Neon/Supabase "postgres" role)
#   LEAGUE_LAB_HOSTED_APP_PASSWORD   password to set for the read-only league_lab_app role on the hosted database
# Usage:  scripts/sync_to_hosted.sh            (or `make sync-hosted`)
#         scripts/sync_to_hosted.sh --dry-run  (dump only, print size)
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p logs
exec > >(tee -a logs/sync.log) 2>&1
echo "=== $(date '+%F %T') sync start (code $(git rev-parse --short HEAD 2>/dev/null || echo '?')) ==="
# load .env the way the app does (python-dotenv): values with &, ?, spaces or quotes are safe
if [ -f .env ]; then
  set -a
  # (the caller's environment wins, as in nightly.sh and the app: LEAGUE_LAB_DB_NAME=x publishes x)
  eval "$(uv run python -c 'import os, shlex; from dotenv import dotenv_values; [print(f"{k}={shlex.quote(v)}") for k, v in dotenv_values(".env").items() if v is not None and k not in os.environ]')"
  set +a
fi

: "${LEAGUE_LAB_HOSTED_ADMIN_URL:?set LEAGUE_LAB_HOSTED_ADMIN_URL in .env}"
: "${LEAGUE_LAB_HOSTED_APP_PASSWORD:?set LEAGUE_LAB_HOSTED_APP_PASSWORD in .env}"
LOCAL_DSN="$(uv run python -c 'from league_lab.config import get_settings; print(get_settings().pipeline_dsn())')"
# Roles are cluster-wide: pointing this at the local cluster would rewrite the local app role's
# password. Refuse unless explicitly allowed (only useful for a simulation).
local_host="$(uv run python -c 'from league_lab.config import get_settings; s=get_settings(); print(f"{s.db_host}:{s.db_port}")')"
# (with or without a port: postgresql://u:p@localhost/db is the local cluster too)
case "$LEAGUE_LAB_HOSTED_ADMIN_URL" in
  *"@${local_host}/"*|*"@${local_host%:*}/"*|*"@localhost:"*|*"@localhost/"*|*"@127.0.0.1:"*|*"@127.0.0.1/"*)
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
# --- the heavy per-game tables go as a window of seasons -------------------------------------
# Neon's free tier caps the project at 512 MB and the full history no longer fits (2026-09-30: the
# sync died mid-restore at that limit, leaving the hosted app without marts). The per-player-game
# tables are ~80% of the copy and the pages only ever browse recent seasons on a phone, so the
# hosted copy carries the newest LEAGUE_LAB_HOSTED_SEASONS seasons (default 3) of them; league
# marts, the decision record and everything small go in full. The Mac keeps the full history.
# Mechanism: season-filtered copies in a local schema `hosted_slim` (same names, same indexes),
# dumped first and moved into `analytics` on the hosted side before the rest is restored, so the
# views that read them restore unchanged.
SLIM_TABLES="fct_player_game mart_player_week_rankings mart_player_context mart_player_recent_form mart_player_expected_points mart_player_trends mart_player_season mart_player_season_team mart_receiver_vs_cb"
HOSTED_SEASONS="${LEAGUE_LAB_HOSTED_SEASONS:-3}"
first_season="$(psql "$LOCAL_DSN" -At -c "select max(season) - ${HOSTED_SEASONS} + 1 from analytics.fct_player_game")"
slim=()
psql "$LOCAL_DSN" -v ON_ERROR_STOP=1 -q -c "drop schema if exists hosted_slim cascade; create schema hosted_slim;"
for t in $closure; do
  case " $SLIM_TABLES " in *" $t "*) ;; *) continue ;; esac
  has_season="$(psql "$LOCAL_DSN" -At -c "select count(*) from information_schema.columns where table_schema = 'analytics' and table_name = '$t' and column_name = 'season'")"
  [ "$has_season" = 1 ] || continue
  psql "$LOCAL_DSN" -v ON_ERROR_STOP=1 -q -c "create table hosted_slim.$t as select * from analytics.$t where season >= $first_season"
  # the same indexes, so the hosted planner sees what the local one sees
  psql "$LOCAL_DSN" -At -c "select regexp_replace(indexdef, '^CREATE (UNIQUE )?INDEX \\S+ ON analytics\\.', 'CREATE \\1INDEX ON hosted_slim.') || ';' from pg_indexes where schemaname = 'analytics' and tablename = '$t'" \
    | psql "$LOCAL_DSN" -v ON_ERROR_STOP=1 -q
  slim+=("$t")
done
FULL_ARGS=()
for t in $closure; do
  case " ${slim[*]:-} " in *" $t "*) continue ;; esac
  FULL_ARGS+=(--table "analytics.$t")
done
echo "publishing $(echo "$closure" | wc -l | tr -d ' ') analytics relations the pages read (of $(psql "$LOCAL_DSN" -At -c "select count(*) from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='analytics' and relkind in ('r','v')")); ${#slim[@]} of them as seasons ${first_season}+ (${slim[*]:-none})"
size_mb="$(psql "$LOCAL_DSN" -At -c "select round((coalesce((select sum(pg_total_relation_size(c.oid)) from pg_class c join pg_namespace n on n.oid = c.relnamespace where n.nspname in ('hosted_slim', 'ops', 'analytics_seeds') and c.relkind = 'r'), 0) + coalesce((select sum(pg_total_relation_size(c.oid)) from pg_class c join pg_namespace n on n.oid = c.relnamespace where n.nspname = 'analytics' and c.relkind = 'r' and c.relname = any(string_to_array('$(echo "$closure" | tr '\n' ',' | sed 's/,$//')', ',')) and not c.relname = any(string_to_array('$(echo "${slim[*]:-}" | tr ' ' ',')', ','))), 0)) / 1048576.0)")"
echo "hosted copy will be about ${size_mb} MB (tables + indexes, as stored locally)"
if [ "${size_mb%.*}" -gt 440 ]; then
  echo "WARNING: that is close to Neon's 512 MB project limit; lower LEAGUE_LAB_HOSTED_SEASONS or trim SLIM_TABLES before it fails mid-restore" >&2
fi
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"; psql "$LOCAL_DSN" -q -c "drop schema if exists hosted_slim cascade" 2>/dev/null' EXIT
DUMP="$TMP/marts.sql.gz"
SLIM_DUMP="$TMP/slim.sql.gz"

echo "dumping marts from the local database ..."
# (with --table given, pg_dump ignores --schema and emits no CREATE SCHEMA, so the other schemas
# are selected by table pattern and the schemas are created explicitly before the restore)
pg_dump "$LOCAL_DSN" --format=plain --no-owner --no-privileges --no-comments \
        --table 'analytics_seeds.*' --table 'ops.*' "${FULL_ARGS[@]}" | gzip -1 > "$DUMP"
if [ ${#slim[@]} -gt 0 ]; then
  pg_dump "$LOCAL_DSN" --format=plain --no-owner --no-privileges --no-comments --table 'hosted_slim.*' | gzip -1 > "$SLIM_DUMP"
else
  : | gzip -1 > "$SLIM_DUMP"
fi
echo "dump: $(du -h "$DUMP" | cut -f1) + $(du -h "$SLIM_DUMP" | cut -f1) compressed"
[ "${1:-}" = "--dry-run" ] && exit 0

echo "ensuring the read-only role exists on the hosted database ..."
# (the password goes in as a psql variable, quoted by psql: a quote in it cannot break the SQL or
# echo the line, and this log is uploaded as a CI artifact)
psql "$LEAGUE_LAB_HOSTED_ADMIN_URL" -v ON_ERROR_STOP=1 -q -v app_pw="$LEAGUE_LAB_HOSTED_APP_PASSWORD" <<'SQL'
do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'league_lab_app') then
    create role league_lab_app login;
  end if;
end $$;
alter role league_lab_app with login password :'app_pw';
alter role league_lab_app set default_transaction_read_only = on;
alter role league_lab_app set statement_timeout = '30s';
SQL

# Free tiers cap the project at ~0.5 GB, and a drop inside the same transaction as the restore
# does not free space until commit - so the old copy of the marts (analytics, analytics_seeds:
# the bulk) is dropped first (its own transaction) and the new one restored right after. Between
# the two, pages say "marts not built yet" instead of failing; the window is the restore time,
# printed below. `ops` is a few MB and is the only copy of the decision record when GitHub
# Actions publishes (ops.projections: each week's board frozen at kickoff; the nightly restores it
# from here), so it is dropped INSIDE the restore transaction: a restore that dies midway rolls
# back and the previous ops survives.
echo "publishing: dropping the previous marts, then restoring (pages show 'not built yet' meanwhile; ops swaps atomically) ..."
t0=$(date +%s)
psql "$LEAGUE_LAB_HOSTED_ADMIN_URL" -v ON_ERROR_STOP=1 -q -c "drop schema if exists analytics cascade; drop schema if exists analytics_seeds cascade;"
{
  echo "drop schema if exists ops cascade; create schema if not exists analytics; create schema if not exists analytics_seeds; create schema ops; drop schema if exists hosted_slim cascade; create schema hosted_slim;"
  # the season-window tables first, moved into analytics so the views restored next find them
  gunzip -c "$SLIM_DUMP"
  for t in "${slim[@]:-}"; do [ -n "$t" ] && echo "alter table hosted_slim.$t set schema analytics;"; done
  echo "drop schema hosted_slim;"
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
# every relation the pages read must be there, visible to the app role - or the run fails loudly
hosted_have="$(psql "$LEAGUE_LAB_HOSTED_ADMIN_URL" -At -c "select table_name from information_schema.tables where table_schema = 'analytics' order by 1")"
missing="$(comm -23 <(echo "$closure" | sort) <(echo "$hosted_have" | sort))"
if [ -n "$missing" ]; then
  echo "ERROR: published copy is missing relations the pages read: $(echo "$missing" | tr '\n' ' ')" >&2
  exit 5
fi
echo "verified: all $(echo "$closure" | wc -l | tr -d ' ') page relations are on the hosted copy ($(psql "$LEAGUE_LAB_HOSTED_ADMIN_URL" -At -c "select pg_size_pretty(pg_database_size(current_database()))") on the hosted database; seasons ${first_season}+ for ${#slim[@]} per-game tables)"
echo "done. Point the app at: postgresql://league_lab_app:<password>@<host>/<db>?sslmode=require"
