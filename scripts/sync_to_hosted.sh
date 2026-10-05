#!/usr/bin/env bash
# Push the marts to the hosted Postgres (plan S-03 / P4-01; Wave H: one writer, the relation audit).
#
# What goes:  every analytics relation the readers of the hosted copy name — the Streamlit console (app/, the
#             weekly packs) and the product API (api/ and the src/league_lab modules it imports) — derived from the
#             code by scripts/hosted_relations.py; every analytics view and its dependencies; analytics_seeds; ops
#             (minus OPS_EXCLUDE). The heavy per-game tables go as a window of seasons (SLIM_TABLES).
# What never goes: raw, staging, intermediate, play-level tables — the hosted copy is ~200 MB, not 4 GB.
#
# Publishing drops the previous marts, then restores the new copy in a single transaction. Free
# tiers (Neon 0.5 GB) cannot hold two copies of the marts at once, so that swap is not atomic: for
# the length of the restore (a minute or two) pages show "marts not built yet" rather than failing.
# The small `ops` schema (the decision record the nightly restores from here) IS swapped inside
# the transaction, so a failed restore never loses it.
#
# One writer (Wave H): GitHub Actions' nightly is the only writer of the hosted copy. Anywhere else this script
# refuses (exit 7) unless LEAGUE_LAB_MAC_WRITES_HOSTED=1 — publishing from the Mac replaces the record Actions keeps
# with the Mac's — or the target is a local simulation (LEAGUE_LAB_HOSTED_ALLOW_LOCAL=1). docs/HOSTING.md § 5.
#
# Needs in .env (or the environment):
#   LEAGUE_LAB_HOSTED_ADMIN_URL      owner connection string of the hosted database (Neon/Supabase "postgres" role)
#   LEAGUE_LAB_HOSTED_APP_PASSWORD   password to set for the read-only league_lab_app role on the hosted database
# Usage:  scripts/sync_to_hosted.sh              (or `make sync-hosted`)
#         scripts/sync_to_hosted.sh --dry-run    (dump only, print the relations and the size)
#         scripts/sync_to_hosted.sh --relations  (the audit: what each reader names and what would be published;
#                                                 reads the local database only, needs no hosted settings)
# Exit codes: 0 published · 4 the target is the local cluster · 5 a relation a reader names is missing on the
# hosted copy after the restore · 6 over the size budget (nothing touched) · 7 not the writer (nothing touched)
set -euo pipefail
cd "$(dirname "$0")/.."
MODE="${1:-publish}"
case "$MODE" in publish|--dry-run|--relations) ;; *) echo "sync_to_hosted.sh: unknown argument: $MODE" >&2; exit 64 ;; esac
mkdir -p logs
exec > >(tee -a logs/sync.log) 2>&1
echo "=== $(date '+%F %T') sync start (code $(git rev-parse --short HEAD 2>/dev/null || echo '?')$([ "$MODE" = publish ] || echo ", $MODE")) ==="
# load .env the way the app does (python-dotenv): values with &, ?, spaces or quotes are safe
if [ -f .env ]; then
  set -a
  # (the caller's environment wins, as in nightly.sh and the app: LEAGUE_LAB_DB_NAME=x publishes x)
  eval "$(uv run python -c 'import os, shlex; from dotenv import dotenv_values; [print(f"{k}={shlex.quote(v)}") for k, v in dotenv_values(".env").items() if v is not None and k not in os.environ]')"
  set +a
fi

LOCAL_DSN="$(uv run python -c 'from league_lab.config import get_settings; print(get_settings().pipeline_dsn())')"
if [ "$MODE" != --relations ]; then
  : "${LEAGUE_LAB_HOSTED_ADMIN_URL:?set LEAGUE_LAB_HOSTED_ADMIN_URL in .env}"
  : "${LEAGUE_LAB_HOSTED_APP_PASSWORD:?set LEAGUE_LAB_HOSTED_APP_PASSWORD in .env}"
  # Roles are cluster-wide: pointing this at the local cluster would rewrite the local app role's
  # password. Refuse unless explicitly allowed (only useful for a simulation).
  local_host="$(uv run python -c 'from league_lab.config import get_settings; s=get_settings(); print(f"{s.db_host}:{s.db_port}")')"
  target_local=0
  # (with or without a port: postgresql://u:p@localhost/db is the local cluster too)
  case "$LEAGUE_LAB_HOSTED_ADMIN_URL" in
    *"@${local_host}/"*|*"@${local_host%:*}/"*|*"@localhost:"*|*"@localhost/"*|*"@127.0.0.1:"*|*"@127.0.0.1/"*)
      target_local=1
      if [ "${LEAGUE_LAB_HOSTED_ALLOW_LOCAL:-}" != "1" ]; then
        echo "refusing: LEAGUE_LAB_HOSTED_ADMIN_URL points at the local cluster (${local_host}); set LEAGUE_LAB_HOSTED_ALLOW_LOCAL=1 only for a simulation" >&2
        exit 4
      fi ;;
  esac
  # --- one writer (Wave H) ----------------------------------------------------------------------
  if [ "$MODE" = publish ] && [ "${GITHUB_ACTIONS:-}" != true ] && [ "${LEAGUE_LAB_MAC_WRITES_HOSTED:-}" != 1 ] && [ "$target_local" != 1 ]; then
    echo "refusing: GitHub Actions is the one writer of the hosted copy (docs/HOSTING.md § 5). Publishing from here" >&2
    echo "  would replace the decision record it keeps there with this machine's. Publish from GitHub instead:" >&2
    echo "  Actions → nightly → Run workflow. When Actions is down: LEAGUE_LAB_MAC_WRITES_HOSTED=1 make sync-hosted" >&2
    echo "  (and no Actions run in progress). Nothing was touched." >&2
    exit 7
  fi
fi

# --- what to publish: the relation closure ------------------------------------------------------
# Derived from the code in ONE place, scripts/hosted_relations.py (its docstring has the rule): the readers are the
# console (app/, src/league_lab/reports.py) and the API (api/league_lab_api/, the app/lib modules and page functions
# it loads, the src/league_lab modules it imports, followed import by import); a name is every analytics. /
# analytics_seeds. / ops. / raw. / staging. / intermediate.<x> in them plus the bare names given to
# missing_relations / require_relations. Published: those analytics relations + every analytics view + the
# analytics relations the views read; analytics_seeds and ops whole (ops minus OPS_EXCLUDE). The other schemas are
# never published: a name there is a pipeline function in a shared module (listed below, so an API route that
# starts reading one shows up here first).
OPS_EXCLUDE="ops.player_prior_oof ops.player_prior_oof_pred"   # E4's experiment harness tables (rebuilt by it when missing); no reader
REL_TSV="$(uv run python scripts/hosted_relations.py)"
named() {  # named <group|all> <schema>: the relation names that group of readers names in that schema
  echo "$REL_TSV" | awk -F'\t' -v g="$1" -v s="$2" '($1 == g || g == "all") && index($2, s ".") == 1 { print substr($2, length(s) + 2) }' | sort -u
}
local_has() {  # local_has <schema> <names...>: the ones the local database has (tables or views)
  local s="$1"; shift
  [ $# -gt 0 ] || return 0
  psql "$LOCAL_DSN" -At -v ON_ERROR_STOP=1 -c "select c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace where n.nspname = '$s' and c.relkind in ('r', 'v', 'm', 'p') and c.relname = any(string_to_array('$*', ' ')) order by 1"
}
csv() { tr '\n' ',' | sed 's/,$//'; }
used="$(named all analytics)"
closure="$(psql "$LOCAL_DSN" -At -v ON_ERROR_STOP=1 <<SQL
with used(name) as (select unnest(string_to_array('$(echo "$used" | csv)', ','))),
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
# what each reader group names that the local database has (schema.name lines): the audit, and what the
# verification below checks on the hosted copy (bash 3.2 on a Mac: no associative arrays)
reads() {  # reads <api|console>
  local s
  # shellcheck disable=SC2046  # one word per relation name
  for s in analytics analytics_seeds ops; do local_has "$s" $(named "$1" "$s") | sed "s/^/$s./"; done
}
api_list="$(reads api)"
console_list="$(reads console)"
# shellcheck disable=SC2046
others="$(for s in raw staging intermediate; do local_has "$s" $(named all "$s") | sed "s/^/$s./"; done)"
echo "readers: $(uv run python scripts/hosted_relations.py --files | cut -f1 | sort | uniq -c | awk '{printf "%s%s %s files", (NR > 1 ? ", " : ""), $2, $1}')"
echo "the API reads $(echo "$api_list" | wc -l | tr -d ' ') relations: $(echo "$api_list" | tr '\n' ' ')"
echo "the console reads $(echo "$console_list" | wc -l | tr -d ' ') relations ($(echo "$console_list" | grep -c '^analytics\.') analytics)"
echo "named in shared pipeline code, never published (not read by a page or a route): $(echo "$others" | tr '\n' ' ')"
echo "ops published whole except: $OPS_EXCLUDE"

# --- the heavy per-game tables go as a window of seasons -------------------------------------
# Neon's free tier caps the project at 512 MB and the full history no longer fits (2026-09-30: the
# sync died mid-restore at that limit, leaving the hosted app without marts). The per-player-game
# tables are ~80% of the copy and the readers only ever browse recent seasons on a phone, so the
# hosted copy carries the newest LEAGUE_LAB_HOSTED_SEASONS seasons (default 3) of them; league
# marts, the decision record and everything small go in full. The Mac keeps the full history.
# Wave H: + fct_player_game_league (the API joins it to fct_player_game, already windowed; Matchups reads last season
# on) and mart_player_week_features (the API and Trade Finder read the current season's status columns only).
# Mechanism: season-filtered copies in a local schema `hosted_slim` (same names, same indexes),
# dumped first and moved into `analytics` on the hosted side before the rest is restored, so the
# views that read them restore unchanged.
SLIM_TABLES="fct_player_game fct_player_game_league mart_player_week_features mart_player_week_rankings mart_player_context mart_player_recent_form mart_player_expected_points mart_player_trends mart_player_season mart_player_season_team mart_receiver_vs_cb player_team_history"  # IL-1: the Role block's "games without X" reads 2024 on
HOSTED_SEASONS="${LEAGUE_LAB_HOSTED_SEASONS:-3}"
MAX_MB="${LEAGUE_LAB_HOSTED_MAX_MB:-480}"    # refuse to publish above this (Neon free: 512 MB; leave room for the catalog and WAL)
first_season="$(psql "$LOCAL_DSN" -At -c "select max(season) - ${HOSTED_SEASONS} + 1 from analytics.fct_player_game")"
slim=()
for t in $closure; do
  case " $SLIM_TABLES " in *" $t "*) ;; *) continue ;; esac
  has_season="$(psql "$LOCAL_DSN" -At -c "select count(*) from information_schema.columns where table_schema = 'analytics' and table_name = '$t' and column_name = 'season'")"
  [ "$has_season" = 1 ] && slim+=("$t")
done
slim_csv="$(echo "${slim[*]:-}" | tr ' ' ',')"
excl_csv="$(echo "$OPS_EXCLUDE" | tr ' ' ',')"
# size: tables + indexes as stored locally; a slim table at its window's share of rows
size_mb="$(psql "$LOCAL_DSN" -At -v ON_ERROR_STOP=1 <<SQL
select round((
  coalesce((select sum(pg_total_relation_size(c.oid)) from pg_class c join pg_namespace n on n.oid = c.relnamespace
            where c.relkind = 'r' and (n.nspname = 'analytics_seeds' or (n.nspname = 'ops' and not (n.nspname || '.' || c.relname) = any(string_to_array('$excl_csv', ','))))), 0)
  + coalesce((select sum(pg_total_relation_size(c.oid)) from pg_class c join pg_namespace n on n.oid = c.relnamespace
              where n.nspname = 'analytics' and c.relkind = 'r' and c.relname = any(string_to_array('$(echo "$closure" | csv)', ','))
                and not c.relname = any(string_to_array('$slim_csv', ','))), 0)
)::numeric / 1048576.0, 1)
SQL
)"
slim_mb=0
for t in "${slim[@]:-}"; do
  [ -n "$t" ] || continue
  slim_mb="$(psql "$LOCAL_DSN" -At -c "select round(($slim_mb + pg_total_relation_size('analytics.$t') * (select count(*) filter (where season >= $first_season)::numeric / greatest(count(*), 1) from analytics.$t) / 1048576.0)::numeric, 1)")"
done
total_mb="$(awk -v a="$size_mb" -v b="$slim_mb" 'BEGIN { printf "%.1f", a + b }')"
echo "publishing $(echo "$closure" | wc -l | tr -d ' ') analytics relations (of $(psql "$LOCAL_DSN" -At -c "select count(*) from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='analytics' and relkind in ('r','v')")); ${#slim[@]} of them as seasons ${first_season}+ (${slim[*]:-none})"
echo "hosted copy will be about ${total_mb} MB (tables + indexes as stored locally: ${slim_mb} MB windowed, ${size_mb} MB in full; budget ${MAX_MB} MB, Neon free 512 MB)"
if [ "$MODE" = --relations ]; then
  echo "analytics closure: $(echo "$closure" | tr '\n' ' ')"
  exit 0
fi
if [ "${total_mb%.*}" -gt "$MAX_MB" ]; then
  echo "ERROR: over the ${MAX_MB} MB budget: nothing was touched (the hosted copy keeps the last publication). Lower" >&2
  echo "  LEAGUE_LAB_HOSTED_SEASONS, add a big per-game table to SLIM_TABLES, or raise LEAGUE_LAB_HOSTED_MAX_MB on a paid plan." >&2
  exit 6
elif [ "${total_mb%.*}" -gt 440 ]; then
  echo "WARNING: that is close to Neon's 512 MB project limit; lower LEAGUE_LAB_HOSTED_SEASONS or trim SLIM_TABLES before it fails mid-restore" >&2
fi

psql "$LOCAL_DSN" -v ON_ERROR_STOP=1 -q -c "drop schema if exists hosted_slim cascade; create schema hosted_slim;"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"; psql "$LOCAL_DSN" -q -c "drop schema if exists hosted_slim cascade" 2>/dev/null' EXIT
for t in "${slim[@]:-}"; do
  [ -n "$t" ] || continue
  psql "$LOCAL_DSN" -v ON_ERROR_STOP=1 -q -c "create table hosted_slim.$t as select * from analytics.$t where season >= $first_season"
  # the same indexes, so the hosted planner sees what the local one sees
  psql "$LOCAL_DSN" -At -c "select regexp_replace(indexdef, '^CREATE (UNIQUE )?INDEX \\S+ ON analytics\\.', 'CREATE \\1INDEX ON hosted_slim.') || ';' from pg_indexes where schemaname = 'analytics' and tablename = '$t'" \
    | psql "$LOCAL_DSN" -v ON_ERROR_STOP=1 -q
done
echo "windowed copies as built: $(psql "$LOCAL_DSN" -At -c "select round(coalesce(sum(pg_total_relation_size(c.oid)), 0) / 1048576.0, 1) from pg_class c join pg_namespace n on n.oid = c.relnamespace where n.nspname = 'hosted_slim' and c.relkind = 'r'") MB (estimated ${slim_mb})"
FULL_ARGS=()
for t in $closure; do
  case " ${slim[*]:-} " in *" $t "*) continue ;; esac
  FULL_ARGS+=(--table "analytics.$t")
done
for t in $OPS_EXCLUDE; do FULL_ARGS+=(--exclude-table "$t"); done
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
[ "$MODE" = --dry-run ] && exit 0

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

# ---- U-1 (Wave I-F): usage tracking — docs/HOSTING.md § "Usage". The `usage` schema is never dropped above (only
# analytics, analytics_seeds and ops are); scripts/hosted_usage.sql creates usage.events if missing and grants the
# app role INSERT + SELECT on that one table (its default_transaction_read_only stays on). Idempotent, a few ms, its
# own transaction after the restore, the same owner connection as above (no new secret). A failure here never fails
# the publish: the marts are already restored, and usage is never load-bearing.
if psql "$LEAGUE_LAB_HOSTED_ADMIN_URL" -v ON_ERROR_STOP=1 -q --single-transaction -f scripts/hosted_usage.sql; then
  echo "usage: $(psql "$LEAGUE_LAB_HOSTED_ADMIN_URL" -At -c "select count(*) || ' events kept, ' || pg_size_pretty(pg_total_relation_size('usage.events')) from usage.events" 2>/dev/null || echo '?')"
else
  echo "WARNING: scripts/hosted_usage.sql failed: screen views are not counted until a sync applies it (the publish itself is fine)" >&2
fi
# ---- end U-1

# ---- IG-2 (Wave I-G): the event store — docs/HOSTING.md § "Events". The `events` schema is never dropped above (only
# analytics, analytics_seeds and ops are); scripts/hosted_events.sql creates events.events if missing and grants the
# app role SELECT + INSERT + UPDATE (superseded_by) on that one table (its default_transaction_read_only stays on).
# Idempotent, a few ms, its own transaction after U-1, the same owner connection (no new secret). A failure here never
# fails the publish: the marts are already restored, and the event store is never load-bearing (the screens fall
# back on the overlay and the live feeds).
if psql "$LEAGUE_LAB_HOSTED_ADMIN_URL" -v ON_ERROR_STOP=1 -q --single-transaction -f scripts/hosted_events.sql; then
  echo "events: $(psql "$LEAGUE_LAB_HOSTED_ADMIN_URL" -At -c "select count(*) || ' events kept (' || count(*) filter (where superseded_by is null) || ' live), ' || pg_size_pretty(pg_total_relation_size('events.events')) from events.events" 2>/dev/null || echo '?')"
else
  echo "WARNING: scripts/hosted_events.sql failed: no events are stored until a sync applies it (the publish itself is fine)" >&2
fi
# ---- end IG-2

# ---- IK-4 (Wave I-K): accounts — docs/HOSTING.md § "Accounts". The `accounts` schema is never dropped above (only
# analytics, analytics_seeds and ops are); scripts/hosted_accounts.sql creates its eight tables if missing, grants the
# app role SELECT / INSERT / UPDATE / DELETE on those eight only (its default_transaction_read_only stays on) and prunes
# spent links and ended sessions. Idempotent, a few ms, its own transaction after IG-2, the same owner connection (no
# new secret). A failure here never fails the publish: accounts stay off (status: not_ready) until a sync applies it.
if psql "$LEAGUE_LAB_HOSTED_ADMIN_URL" -v ON_ERROR_STOP=1 -q --single-transaction -f scripts/hosted_accounts.sql; then
  echo "accounts: $(psql "$LEAGUE_LAB_HOSTED_ADMIN_URL" -At -c "select (select count(*) from accounts.users) || ' accounts, ' || (select count(*) from accounts.user_leagues) || ' saved leagues, ' || pg_size_pretty((select sum(pg_total_relation_size(c.oid)) from pg_class c join pg_namespace n on n.oid = c.relnamespace where n.nspname = 'accounts' and c.relkind = 'r')::bigint)" 2>/dev/null || echo '?')"
else
  echo "WARNING: scripts/hosted_accounts.sql failed: accounts stay off until a sync applies it (the publish itself is fine)" >&2
fi
# ---- end IK-4

echo "verifying ..."
psql "$LEAGUE_LAB_HOSTED_ADMIN_URL" -v ON_ERROR_STOP=1 -At -c "
  select 'analytics tables: ' || count(*) from information_schema.tables where table_schema = 'analytics';" \
  -c "select 'published through: ' || coalesce(max(loaded_at)::text, 'n/a') from ops.source_partition;"
# every relation a reader names (and the local database has) must be there, visible to the app role - or the run
# fails loudly: the analytics closure, and every ops / analytics_seeds table the API or the console names
hosted_have="$(psql "$LEAGUE_LAB_HOSTED_ADMIN_URL" -At -c "select table_schema || '.' || table_name from information_schema.tables where table_schema in ('analytics', 'analytics_seeds', 'ops') order by 1")"
need="$( { for t in $closure; do echo "analytics.$t"; done; printf '%s\n%s\n' "$api_list" "$console_list"; } | sed '/^$/d' | sort -u)"
missing="$(comm -23 <(echo "$need") <(echo "$hosted_have" | sort))"
if [ -n "$missing" ]; then
  echo "ERROR: published copy is missing relations the readers name: $(echo "$missing" | tr '\n' ' ')" >&2
  exit 5
fi
api_missing="$(comm -23 <(echo "$api_list" | sort) <(echo "$hosted_have" | sort))"
[ -z "$api_missing" ] || { echo "ERROR: the API reads relations the hosted copy lacks: $api_missing" >&2; exit 5; }
echo "verified: all $(echo "$need" | wc -l | tr -d ' ') relations the pages and the API read are on the hosted copy (the API's $(echo "$api_list" | wc -l | tr -d ' ') included; $(psql "$LEAGUE_LAB_HOSTED_ADMIN_URL" -At -c "select pg_size_pretty(pg_database_size(current_database()))") on the hosted database; seasons ${first_season}+ for ${#slim[@]} per-game tables)"
echo "done. Point the app at: postgresql://league_lab_app:<password>@<host>/<db>?sslmode=require"
