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
#         scripts/sync_to_hosted.sh --rollback   (IR-3: put the previous publication back - only after a swap that kept
#                                                 it as analytics_prev / analytics_seeds_prev / ops_prev; docs/HOSTING.md)
# Exit codes: 0 published · 4 the target is the local cluster · 5 a relation a reader names is missing on the
# hosted copy after the restore · 6 over the size budget (nothing touched) · 7 not the writer (nothing touched)
# · 8 (IR-3) LEAGUE_LAB_HOSTED_PUBLISH=swap and old + new do not fit under LEAGUE_LAB_HOSTED_CAP_MB (nothing published)
# · 9 (IR-3) --rollback with no previous publication kept (nothing touched)
#
# ---- IR-3 (Wave I-R): how a publication replaces the last one - LEAGUE_LAB_HOSTED_PUBLISH (docs/HOSTING.md § "Publishing
# without the gap"):
#   drop  (the default, unchanged)  the previous marts are dropped, then the new copy restored: for the restore's length
#         the tables are away. New and always on: a marker on the database while they are away ({"publishing_since"}:
#         /api/ready answers 503 "publishing" with it, the screens say the numbers are not ready yet) and the
#         publication's id and time as the comment of the analytics schema ({"publication", "published_at", "code"}).
#         Both are their own statements and never fail the publish.
#   swap  the new copy is restored under the live names while the live schemas are renamed aside (`_prev`) - in ONE
#         transaction with the validation (every relation a reader names, each table's rows = the local copy's, the
#         readiness rule: projections, the current week on the boards and the lists, the rest-of-season list). Readers
#         see the old publication until the commit and the new one after it; a failed or interrupted restore or a
#         failed check rolls everything back and the old publication stays. Needs room for two copies: refused (exit 8,
#         nothing published) when the hosted database's size + this copy > LEAGUE_LAB_HOSTED_CAP_MB (default 500).
#         The old copy is kept as `_prev` (the app role's grants revoked) for --rollback until the next run, or
#         dropped at once when keeping it would leave the database over the cap (or LEAGUE_LAB_HOSTED_KEEP_PREV=0).
#   auto  swap when it fits under the cap, otherwise drop (and the log says which and why).
# LEAGUE_LAB_HOSTED_RETRIES (default 0 = as before): a restore whose connection is lost (psql exit 2) is run again whole,
# up to that many times, after LEAGUE_LAB_HOSTED_RETRY_WAIT_S × the attempt (default 30 s); an SQL error never is.
set -euo pipefail
cd "$(dirname "$0")/.."
MODE="${1:-publish}"
case "$MODE" in publish|--dry-run|--relations|--rollback) ;; *) echo "sync_to_hosted.sh: unknown argument: $MODE" >&2; exit 64 ;; esac  # IR-3: --rollback
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
  if { [ "$MODE" = publish ] || [ "$MODE" = --rollback ]; } && [ "${GITHUB_ACTIONS:-}" != true ] && [ "${LEAGUE_LAB_MAC_WRITES_HOSTED:-}" != 1 ] && [ "$target_local" != 1 ]; then
    echo "refusing: GitHub Actions is the one writer of the hosted copy (docs/HOSTING.md § 5). Publishing from here" >&2
    echo "  would replace the decision record it keeps there with this machine's. Publish from GitHub instead:" >&2
    echo "  Actions → nightly → Run workflow. When Actions is down: LEAGUE_LAB_MAC_WRITES_HOSTED=1 make sync-hosted" >&2
    echo "  (and no Actions run in progress). Nothing was touched." >&2
    exit 7
  fi
fi

# ---- IR-3 (Wave I-R): the publication mode (the header), the swap's room, and --rollback ---------------------------
PUBLISH_MODE="${LEAGUE_LAB_HOSTED_PUBLISH:-drop}"
case "$PUBLISH_MODE" in drop|swap|auto) ;; *) echo "LEAGUE_LAB_HOSTED_PUBLISH is drop, swap or auto (got: $PUBLISH_MODE)" >&2; exit 64 ;; esac
CAP_MB="${LEAGUE_LAB_HOSTED_CAP_MB:-500}"     # the most the hosted database may hold at once (Neon free: 512 MB)
KEEP_PREV="${LEAGUE_LAB_HOSTED_KEEP_PREV:-1}"
# a simulation on the local cluster (target_local=1 only) may skip the role step: roles are cluster-wide, and the
# local league_lab_app role belongs to every developer's database (never honoured against a hosted database)
SKIP_ROLE=0
[ "${target_local:-0}" = 1 ] && [ "${LEAGUE_LAB_HOSTED_SKIP_ROLE:-}" = 1 ] && SKIP_ROLE=1
PREV_SCHEMAS="analytics_prev analytics_seeds_prev ops_prev"
hosted_q() { psql "$LEAGUE_LAB_HOSTED_ADMIN_URL" -v ON_ERROR_STOP=1 -At -c "$1"; }
hosted_mb() { hosted_q "select round(pg_database_size(current_database()) / 1048576.0)::int"; }
revoke_prev_sql() {  # the app role never reads a kept copy; the revoke also makes every cached plan on the old tables re-plan
  cat <<'SQL'
do $$ declare s text; begin
  foreach s in array array['analytics_prev', 'analytics_seeds_prev', 'ops_prev'] loop
    if exists (select 1 from pg_namespace where nspname = s) and exists (select 1 from pg_roles where rolname = 'league_lab_app') then
      execute format('revoke all on all tables in schema %I from league_lab_app', s);
      execute format('revoke usage on schema %I from league_lab_app', s);
    end if;
  end loop;
end $$;
SQL
}
# a restore whose connection is lost (psql exit 2: Neon's free compute, the network) is run again whole - it is one
# transaction, so nothing of the failed attempt was kept. Off by default (LEAGUE_LAB_HOSTED_RETRIES=0: as before, the
# run fails); an SQL error (exit 3: a size limit, a failed check) is never retried.
RETRIES="${LEAGUE_LAB_HOSTED_RETRIES:-0}"
RETRY_WAIT_S="${LEAGUE_LAB_HOSTED_RETRY_WAIT_S:-30}"
restore_retrying() {  # restore_retrying <stream function>
  local attempt=0 rc
  while :; do
    set +e
    "$1" | psql "$LEAGUE_LAB_HOSTED_ADMIN_URL" -v ON_ERROR_STOP=1 -q --single-transaction
    rc=$?
    set -e
    [ "$rc" = 0 ] && return 0
    if [ "$rc" = 2 ] && [ "$attempt" -lt "$RETRIES" ]; then
      attempt=$((attempt + 1))
      echo "the connection was lost during the restore (attempt $attempt of $((RETRIES + 1)); nothing of it was kept: one transaction); again in $((attempt * RETRY_WAIT_S)) s" >&2
      sleep $((attempt * RETRY_WAIT_S))
      continue
    fi
    return "$rc"
  done
}
if [ "$MODE" = --rollback ]; then
  have_prev="$(hosted_q "select count(*) from pg_namespace where nspname in ('analytics_prev', 'analytics_seeds_prev', 'ops_prev')")"
  if [ "$have_prev" != 3 ]; then
    echo "rollback: no previous publication is kept ($have_prev of 3 _prev schemas): nothing was touched" >&2
    exit 9
  fi
  echo "rollback: putting the previous publication back ($(hosted_q "select coalesce(obj_description(to_regnamespace('analytics_prev'), 'pg_namespace'), 'not recorded')") replaces $(hosted_q "select coalesce(obj_description(to_regnamespace('analytics'), 'pg_namespace'), 'not recorded')")) ..."
  { echo "set client_min_messages = warning; drop schema if exists analytics_bad cascade; drop schema if exists analytics_seeds_bad cascade; drop schema if exists ops_bad cascade;"
    for sch in analytics analytics_seeds ops; do
      echo "alter schema ${sch} rename to ${sch}_bad; alter schema ${sch}_prev rename to ${sch};"
    done
    cat <<'SQL'
do $$ begin
  if exists (select 1 from pg_roles where rolname = 'league_lab_app') then
    grant usage on schema analytics, analytics_seeds, ops to league_lab_app;
    grant select on all tables in schema analytics to league_lab_app;
    grant select on all tables in schema analytics_seeds to league_lab_app;
    grant select on all tables in schema ops to league_lab_app;
    revoke all on all tables in schema analytics_bad, analytics_seeds_bad, ops_bad from league_lab_app;
  end if;
end $$;
SQL
  } | psql "$LEAGUE_LAB_HOSTED_ADMIN_URL" -v ON_ERROR_STOP=1 -q --single-transaction
  psql "$LEAGUE_LAB_HOSTED_ADMIN_URL" -v ON_ERROR_STOP=1 -q -c "set client_min_messages = warning; drop schema analytics_bad cascade; drop schema analytics_seeds_bad cascade; drop schema ops_bad cascade;"
  echo "rollback done: the previous publication is live ($(hosted_q "select coalesce(obj_description(to_regnamespace('analytics'), 'pg_namespace'), 'not recorded')")); the replaced one is dropped. The next nightly publishes anew."
  exit 0
fi
# ---- end IR-3

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
SLIM_TABLES="fct_player_game fct_player_game_league mart_player_week_features mart_player_week_rankings mart_player_context mart_player_recent_form mart_player_expected_points mart_player_trends mart_player_season mart_player_season_team mart_receiver_vs_cb player_team_history mart_player_game_advanced"  # IM-1: the Stats table's EPA / first-down / deep-target numerators, windowed like the per-game tables (9.3 → ~2.1 MB); IL-1: the Role block's "games without X" reads 2024 on
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

# ---- IR-3: the publication's id (its time, the code that built it) and, for a swap, the room it needs
PUB_TIME="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
PUB_CODE="$(git rev-parse --short=12 HEAD 2>/dev/null || echo unknown)"
PUB_ID="$(date -u +%Y%m%dT%H%MZ)-${PUB_CODE}"
echo "publication id: ${PUB_ID}"      # PO (Wave I-T): the nightly's post-publish check waits for this id on the live site
pub_json() { printf '{"publication": "%s", "published_at": "%s", "code": "%s", "mode": "%s", "seasons_from": %s}' "$PUB_ID" "$PUB_TIME" "$PUB_CODE" "$1" "$first_season"; }
use_swap=0
if [ "$PUBLISH_MODE" != drop ]; then
  # a kept previous publication goes first (it would not fit beside the current one and the new one)
  psql "$LEAGUE_LAB_HOSTED_ADMIN_URL" -v ON_ERROR_STOP=1 -q -c "set client_min_messages = warning; drop schema if exists analytics_prev cascade; drop schema if exists analytics_seeds_prev cascade; drop schema if exists ops_prev cascade;"
  now_mb="$(hosted_mb)"
  need_mb="$(awk -v a="$now_mb" -v b="$total_mb" 'BEGIN { printf "%d", a + b + 0.5 }')"
  if [ "$need_mb" -le "$CAP_MB" ]; then
    use_swap=1
    echo "publication mode: swap (the hosted database holds ${now_mb} MB; + this copy ~${total_mb} MB = ${need_mb} MB <= the ${CAP_MB} MB cap)"
  elif [ "$PUBLISH_MODE" = swap ]; then
    echo "ERROR: LEAGUE_LAB_HOSTED_PUBLISH=swap, but the hosted database (${now_mb} MB) + this copy (~${total_mb} MB) = ${need_mb} MB is over the ${CAP_MB} MB cap: nothing was published (the hosted copy keeps the last publication). Raise LEAGUE_LAB_HOSTED_CAP_MB on a larger plan, or publish with auto / drop." >&2
    exit 8
  else
    echo "publication mode: drop (auto: the hosted database ${now_mb} MB + this copy ~${total_mb} MB = ${need_mb} MB is over the ${CAP_MB} MB cap - two copies do not fit)"
  fi
fi
if [ "$use_swap" = 1 ]; then
  # the validation the swap commits only after: every relation a reader names, and each table's rows as the local copy
  need_pre="$( { for t in $closure; do echo "analytics.$t"; done; printf '%s\n%s\n' "$api_list" "$console_list"; } | sed '/^$/d' | sort -u)"
  slim_in="$(echo "${slim[*]:-}" | tr ' ' ',')"
  counts_sql="$(psql "$LOCAL_DSN" -At -v ON_ERROR_STOP=1 <<SQL
select string_agg(format('select %L as name, %s::bigint as want', n.nspname || '.' || c.relname,
         (xpath('/row/c/text()', query_to_xml(format('select count(*) as c from %I.%I',
            case when n.nspname = 'analytics' and c.relname = any(string_to_array('$slim_in', ',')) then 'hosted_slim' else n.nspname end,
            c.relname), false, true, '')))[1]::text), ' union all ' order by 1)
from pg_class c join pg_namespace n on n.oid = c.relnamespace
where c.relkind in ('r', 'p') and (
      (n.nspname = 'analytics' and c.relname = any(string_to_array('$(echo "$closure" | csv)', ',')))
   or n.nspname = 'analytics_seeds'
   or (n.nspname = 'ops' and not (n.nspname || '.' || c.relname) = any(string_to_array('$excl_csv', ','))))
SQL
)"
  echo "the swap checks $(echo "$need_pre" | wc -l | tr -d ' ') relations and the rows of $(echo "$counts_sql" | grep -o ' as name' | wc -l | tr -d ' ') tables before it commits"
fi

if [ "$SKIP_ROLE" = 1 ]; then
  echo "a local simulation (LEAGUE_LAB_HOSTED_SKIP_ROLE=1): the cluster-wide read-only role is left as it is"
else
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
fi   # ---- IR-3: SKIP_ROLE

# Free tiers cap the project at ~0.5 GB, and a drop inside the same transaction as the restore
# does not free space until commit - so the old copy of the marts (analytics, analytics_seeds:
# the bulk) is dropped first (its own transaction) and the new one restored right after. Between
# the two, pages say "marts not built yet" instead of failing; the window is the restore time,
# printed below. `ops` is a few MB and is the only copy of the decision record when GitHub
# Actions publishes (ops.projections: each week's board frozen at kickoff; the nightly restores it
# from here), so it is dropped INSIDE the restore transaction: a restore that dies midway rolls
# back and the previous ops survives.
if [ "$use_swap" = 1 ]; then
# ---- IR-3: the swap - the live schemas renamed aside and the new copy restored under their names, validated, in ONE
# transaction (--single-transaction): until the commit every reader sees the previous publication; any failure (the
# restore, a lost connection, a check below) rolls all of it back and the previous publication stays as it was.
echo "publishing: restoring beside the live publication, checking, then switching in one transaction (pages keep the previous numbers until the commit) ..."
t0=$(date +%s)
swap_stream() {  # ---- IR-3: the swap transaction as a stream (re-run whole by restore_retrying)
  cat <<'SQL'
drop schema if exists hosted_slim cascade;
do $$ declare s text; begin
  foreach s in array array['analytics', 'analytics_seeds', 'ops'] loop
    if exists (select 1 from pg_namespace where nspname = s) then
      execute format('alter schema %I rename to %I', s, s || '_prev');
    end if;
  end loop;
end $$;
create schema analytics; create schema analytics_seeds; create schema ops; create schema hosted_slim;
SQL
  gunzip -c "$SLIM_DUMP"
  for t in "${slim[@]:-}"; do [ -n "$t" ] && echo "alter table hosted_slim.$t set schema analytics;"; done
  echo "drop schema hosted_slim;"
  gunzip -c "$DUMP"
  cat <<'SQL'
do $$ begin
  if exists (select 1 from pg_roles where rolname = 'league_lab_app') then
    grant usage on schema analytics, analytics_seeds, ops to league_lab_app;
    grant select on all tables in schema analytics to league_lab_app;
    grant select on all tables in schema analytics_seeds to league_lab_app;
    grant select on all tables in schema ops to league_lab_app;
  end if;
end $$;
SQL
  revoke_prev_sql
  # the publication's id, in the same transaction as its tables (/api/ready reads it)
  echo "comment on schema analytics is \$pub\$$(pub_json swap)\$pub\$;"
  # the checks: a failure raises, and the transaction - the whole publication - rolls back
  echo "do \$chk\$ declare missing text; begin
  select string_agg(n, ' ') into missing from unnest(string_to_array('$(echo "$need_pre" | csv)', ',')) n where to_regclass(n) is null;
  if missing is not null then raise exception 'publication refused (the previous one stays): missing relations: %', missing; end if;
end \$chk\$;"
  if [ -n "$counts_sql" ]; then
    echo "do \$chk\$ declare r record; got bigint; bad text := ''; begin
  for r in $counts_sql loop
    execute 'select count(*) from ' || r.name into got;
    if got <> r.want then bad := bad || format(' %s %s of %s;', r.name, got, r.want); end if;
  end loop;
  if bad <> '' then raise exception 'publication refused (the previous one stays): rows differ from the local copy:%', bad; end if;
end \$chk\$;"
  fi
  cat <<'SQL'
do $chk$ declare s int; w int; begin
  if (select max(fitted_at) from ops.projections) is null then
    raise exception 'publication refused (the previous one stays): no projections';
  end if;
  select season, week into s, w from analytics.dim_game where season_type = 'REG' and kickoff_at > now() order by kickoff_at limit 1;
  if found and not exists (select 1 from ops.projections where season = s and week = w) then
    raise exception 'publication refused (the previous one stays): week % of % has no projections on the boards', w, s;
  end if;
  if found and not exists (select 1 from analytics.mart_player_week_projections where season = s and week = w) then
    raise exception 'publication refused (the previous one stays): week % of % has no projections in the lists', w, s;
  end if;
  if not exists (select 1 from analytics.mart_player_ros_projection) then
    raise exception 'publication refused (the previous one stays): the rest-of-season list is empty';
  end if;
end $chk$;
SQL
}
restore_retrying swap_stream
echo "switched in $(( $(date +%s) - t0 )) s: publication ${PUB_ID} is live"
after_mb="$(hosted_mb)"
if [ "$KEEP_PREV" = 1 ] && [ "$after_mb" -le "$CAP_MB" ]; then
  echo "the previous publication is kept as analytics_prev / analytics_seeds_prev / ops_prev until the next run (${after_mb} MB in all; scripts/sync_to_hosted.sh --rollback puts it back)"
else
  psql "$LEAGUE_LAB_HOSTED_ADMIN_URL" -v ON_ERROR_STOP=1 -q -c "set client_min_messages = warning; drop schema if exists analytics_prev cascade; drop schema if exists analytics_seeds_prev cascade; drop schema if exists ops_prev cascade;"
  echo "the previous publication is dropped (${after_mb} MB with it; cap ${CAP_MB} MB, LEAGUE_LAB_HOSTED_KEEP_PREV=${KEEP_PREV}): $(hosted_mb) MB now"
fi
else
# ---- end IR-3 (the drop path below is the pre-IR-3 path, unchanged but for the marker and the stamp around it)
echo "publishing: dropping the previous marts, then restoring (pages show 'not built yet' meanwhile; ops swaps atomically) ..."
t0=$(date +%s)
# ---- IR-3: the marker while the tables are away (/api/ready: 503 "publishing"); its own statement, never fatal
psql "$LEAGUE_LAB_HOSTED_ADMIN_URL" -q -c "do \$m\$ begin execute format('comment on database %I is %L', current_database(), '{\"publishing_since\": \"$PUB_TIME\", \"mode\": \"drop\"}'); end \$m\$;" \
  || echo "WARNING: could not mark the database as publishing (the publish goes on; /api/ready says 'missing tables' meanwhile)" >&2
psql "$LEAGUE_LAB_HOSTED_ADMIN_URL" -v ON_ERROR_STOP=1 -q -c "drop schema if exists analytics cascade; drop schema if exists analytics_seeds cascade;"
drop_stream() {  # ---- IR-3: the pre-IR-3 restore transaction, unchanged, as a stream (re-run whole by restore_retrying)
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
}
restore_retrying drop_stream
echo "restored in $(( $(date +%s) - t0 )) s"
# ---- IR-3: the publication's id, and the marker cleared (each its own statement, never fatal)
psql "$LEAGUE_LAB_HOSTED_ADMIN_URL" -q -c "comment on schema analytics is \$pub\$$(pub_json drop)\$pub\$;" \
  || echo "WARNING: could not record the publication's id (the publish itself is fine)" >&2
psql "$LEAGUE_LAB_HOSTED_ADMIN_URL" -q -c "do \$m\$ begin execute format('comment on database %I is null', current_database()); end \$m\$;" \
  || echo "WARNING: could not clear the publishing marker (/api/ready ignores it while the tables are there)" >&2
fi   # ---- IR-3: swap / drop

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

# ---- IO-2 (Wave I-O): the League outlook's weekly snapshots — docs/STATUS.md § "Wave I-O" → IO-2. The `outlook` schema is never
# dropped above; scripts/hosted_outlook.sql creates outlook.snapshots if missing, grants the app role SELECT / INSERT /
# UPDATE on it (its default_transaction_read_only stays on) and prunes rows past 20 weeks. Idempotent, a few ms, its own
# transaction, the same owner connection. A failure never fails the publish: the arrows stay off until a sync applies it.
if psql "$LEAGUE_LAB_HOSTED_ADMIN_URL" -v ON_ERROR_STOP=1 -q --single-transaction -f scripts/hosted_outlook.sql; then
  echo "outlook: $(psql "$LEAGUE_LAB_HOSTED_ADMIN_URL" -At -c "select count(*) || ' weeks kept (' || count(distinct league_key) || ' leagues), ' || pg_size_pretty(pg_total_relation_size('outlook.snapshots')) from outlook.snapshots" 2>/dev/null || echo '?')"
else
  echo "WARNING: scripts/hosted_outlook.sql failed: no outlook is kept until a sync applies it (the publish itself is fine)" >&2
fi
# ---- end IO-2

# ---- IO-3 (Wave I-O): the blog's editor — docs/BLOG.md § "The editor". The `blog` schema is never dropped above (only
# analytics, analytics_seeds and ops are); scripts/hosted_blog.sql creates blog.posts, blog.revisions and blog.images if
# missing, grants the app role SELECT / INSERT / UPDATE / DELETE on posts and revisions and SELECT / INSERT / DELETE on
# images (its default_transaction_read_only stays on) and prunes posts deleted 30 days ago and revisions past the newest
# 20. Idempotent, a few ms, its own transaction after IK-4, the same owner connection (no new secret). A failure here
# never fails the publish: the blog stays the files' and the editor off until a sync applies it.
if psql "$LEAGUE_LAB_HOSTED_ADMIN_URL" -v ON_ERROR_STOP=1 -q --single-transaction -f scripts/hosted_blog.sql; then
  echo "blog: $(psql "$LEAGUE_LAB_HOSTED_ADMIN_URL" -At -c "select (select count(*) from blog.posts where status = 'published') || ' published, ' || (select count(*) from blog.posts) || ' posts, ' || (select count(*) from blog.images) || ' pictures, ' || pg_size_pretty((select sum(pg_total_relation_size(c.oid)) from pg_class c join pg_namespace n on n.oid = c.relnamespace where n.nspname = 'blog' and c.relkind = 'r')::bigint)" 2>/dev/null || echo '?')"
else
  echo "WARNING: scripts/hosted_blog.sql failed: the blog stays the files' and the editor off until a sync applies it (the publish itself is fine)" >&2
fi
# ---- end IO-3

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
