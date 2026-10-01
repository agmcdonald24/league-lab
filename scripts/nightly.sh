#!/usr/bin/env bash
# shellcheck disable=SC2016,SC2329  # steps run through run_step; the backticks are Markdown
# The nightly pipeline (plan B6 / I-01). One script for every machine: GitHub Actions runs it
# (.github/workflows/nightly.yml) against a throwaway Postgres, the Mac runs it through
# scripts/refresh.sh (launchd 08:00), and anyone can run it by hand.
#
#   migrate → restore state (a fresh database takes the backtests, the frozen projection record, the
#     drift history and last night's lineups from the hosted copy; the record also from the archive)
#   → replay the archive (data/raw: Sleeper, nflverse history, nflverse current season; --offline)
#   → live fetch (Sleeper, nflverse current season; conditional requests)
#   → dbt build → backtests (only when missing or made by another model version)
#   → project (projection v2, then the lineups solved on it) → save the record to the archive
#   → projection + lineup marts → drift
#   → backup (NIGHTLY_BACKUP=1) → hosted sync (when LEAGUE_LAB_HOSTED_ADMIN_URL is set)
#
# Usage:  scripts/nightly.sh           the nightly run
#         scripts/nightly.sh --full    also re-check every historical NFL season live (monthly audit;
#                                      conditional requests, so unchanged files cost one round trip)
# Environment (anything not already set is read from .env, the way the app reads it):
#   NIGHTLY_SLEEPER_OFFLINE=1   no live Sleeper fetch: league data stays as archived (sandboxes
#                               without api.sleeper.app). The replay must then succeed.
#   NIGHTLY_BACKUP=1            pg_dump into backups/ after the build (refresh.sh sets it on the Mac)
#   NIGHTLY_BACKTESTS=1         recompute both backtests even when present (backtest-v2 takes minutes)
#   LEAGUE_LAB_HOSTED_ADMIN_URL, LEAGUE_LAB_HOSTED_APP_PASSWORD   publish to the hosted copy at the end
#
# Failure policy. A failed live fetch does not stop the run: the loaders keep the previous good
# data of a failed partition (here: the archive replayed a minute earlier), so the rest of the night
# still builds and publishes, and the run exits 1 at the end naming the step. Without an archive
# (first run, lost cache) there is no previous copy, so a failed live fetch stops the night.
# Anything after the ingest (dbt build, backtests, project, the projection marts, the sync) stops
# the run at once, so a half-built night never reaches the hosted copy; it keeps yesterday's.
# (Drift, the backup, and `project` when an earlier board exists are reported like a failed live
# fetch: the night publishes.)
# Exit codes: 0 every step ok · 1 a step failed (named on the last line) · 2 Postgres is not
# reachable · 3 another run holds the lock · 64 bad arguments.
# Everything is appended to logs/nightly.log (and printed).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
[ -x /opt/homebrew/opt/postgresql@17/bin/psql ] && export PATH="/opt/homebrew/opt/postgresql@17/bin:$PATH"
export PATH="/opt/homebrew/bin:$HOME/.local/bin:$PATH"

FULL=0
for arg in "$@"; do
  case "$arg" in
    --full) FULL=1 ;;
    -h|--help) sed -n '3,35p' "$0"; exit 0 ;;
    *) echo "nightly.sh: unknown argument: $arg (see --help)" >&2; exit 64 ;;
  esac
done

mkdir -p logs .state
exec > >(tee -a logs/nightly.log) 2>&1
T_START=$(date +%s)
echo "=== $(date '+%F %T %Z') nightly start (code $(git rev-parse --short HEAD 2>/dev/null || echo '?'), host $(hostname -s 2>/dev/null || hostname)) ==="

# --- one writer (AGENTS.md rule 2) ---------------------------------------------------------------
# The same lock scripts/refresh.sh always took, now with the owner's pid so a lock left by a killed
# run is recognised as stale instead of blocking every later night.
LOCK="$ROOT/.state/refresh.lock"
if ! mkdir "$LOCK" 2>/dev/null; then
  holder="$(cat "$LOCK/pid" 2>/dev/null || true)"
  if [ -n "$holder" ] && ! kill -0 "$holder" 2>/dev/null; then
    echo "removing a stale lock left by pid $holder (no longer running)"
    rm -rf "$LOCK"
    mkdir "$LOCK"
  else
    echo "$(date '+%F %T') another refresh/nightly is running (lock: $LOCK, pid ${holder:-unknown}); exiting" >&2
    exit 3
  fi
fi
echo $$ > "$LOCK/pid"
FINISHED=0
CURRENT_STEP="setup"
on_exit() {
  local rc=$?
  rm -rf "$LOCK"
  if [ "$FINISHED" != 1 ] && [ "$rc" != 0 ]; then
    echo "=== $(date '+%F %T') nightly ABORTED (exit $rc) during: $CURRENT_STEP ==="
    [ "${GITHUB_ACTIONS:-}" = "true" ] && echo "::error title=nightly aborted::during $CURRENT_STEP (exit $rc); see logs/nightly.log"
  fi
  return 0
}
trap on_exit EXIT

# --- environment: .env the way the app loads it (python-dotenv; values with & ? spaces or quotes
# are safe), never overriding what the caller already exported (CI, NIGHTLY_*, one-off overrides) ---
if [ -f .env ]; then
  set -a
  eval "$(uv run python -c 'import os, shlex; from dotenv import dotenv_values; [print(f"{k}={shlex.quote(v)}") for k, v in dotenv_values(".env").items() if v is not None and k not in os.environ]')"
  set +a
fi

db_host="${LEAGUE_LAB_DB_HOST:-localhost}"; db_port="${LEAGUE_LAB_DB_PORT:-5432}"
for _ in $(seq 1 15); do pg_isready -q -h "$db_host" -p "$db_port" && break; sleep 2; done
if ! pg_isready -q -h "$db_host" -p "$db_port"; then
  echo "PostgreSQL is not accepting connections on $db_host:$db_port (Mac: brew services start postgresql@17)" >&2
  FINISHED=1; exit 2
fi

# season, archive location and the pipeline DSN from the code's own settings (one source of truth)
{ read -r SEASON; read -r RAW_DIR; read -r LOCAL_DSN; } < <(uv run python -c '
from league_lab.config import get_settings
from league_lab.ingest.nflverse import current_nfl_season
s = get_settings()
print(current_nfl_season()); print(s.raw_dir); print(s.pipeline_dsn())')
[ -n "${SEASON:-}" ] && [ -n "${LOCAL_DSN:-}" ] || { echo "could not read the settings (.env?)" >&2; exit 1; }
START="${LEAGUE_LAB_SEASONS_START:-2016}"
HISTORY="${START}-$((SEASON - 1))"
echo "season $SEASON (history $HISTORY), archive $RAW_DIR ($(du -sh "$RAW_DIR" 2>/dev/null | cut -f1 || echo 'absent')), database ${LEAGUE_LAB_DB_NAME:-league_lab}@$db_host:$db_port"

# --- step runner: named steps with timing lines and a summary ------------------------------------
STEP_NAMES=(); STEP_SECS=(); STEP_RESULTS=(); FAILED=()
fmt() { printf '%dm%02ds' $(($1 / 60)) $(($1 % 60)); }
in_ci() { [ "${GITHUB_ACTIONS:-}" = "true" ]; }

record() {  # record <name> <seconds> <result>
  STEP_NAMES+=("$1"); STEP_SECS+=("$2"); STEP_RESULTS+=("$3")
}

run_step() {  # run_step <name> <command...>: run it, print a timing line, return its exit code
  local name="$1"; shift
  local t0 rc=0 dt
  CURRENT_STEP="$name"
  t0=$(date +%s)
  in_ci && echo "::group::$name"
  echo "--- $(date '+%T') step $name: $*"
  "$@" || rc=$?
  dt=$(( $(date +%s) - t0 ))
  in_ci && echo "::endgroup::"
  if [ "$rc" = 0 ]; then
    echo "--- $(date '+%T') step $name: ok in $(fmt "$dt")"
  else
    echo "--- $(date '+%T') step $name: FAILED (exit $rc) after $(fmt "$dt")"
  fi
  LAST_SECS=$dt
  return "$rc"
}

summary() {
  local total=$(( $(date +%s) - T_START )) i line
  echo "=== nightly summary ($(date '+%F %T %Z'), total $(fmt "$total")) ==="
  for i in "${!STEP_NAMES[@]}"; do
    printf '  %-26s %7s  %s\n' "${STEP_NAMES[$i]}" "$(fmt "${STEP_SECS[$i]}")" "${STEP_RESULTS[$i]}"
  done
  if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
    {
      echo "### Nightly: ${#FAILED[@]} failed step(s), total $(fmt "$total")"
      echo
      echo "| step | time | result |"
      echo "|---|---:|---|"
      for i in "${!STEP_NAMES[@]}"; do echo "| ${STEP_NAMES[$i]} | $(fmt "${STEP_SECS[$i]}") | ${STEP_RESULTS[$i]} |"; done
      while IFS= read -r line; do printf '\n`Done. %s`\n' "${line#*Done. }"; done < <(grep -h "Done. PASS=" logs/nightly.log 2>/dev/null | tail -2)
      while IFS= read -r line; do printf '\n`%s`\n' "$line"; done < <(grep -h "^verified: all" logs/sync.log 2>/dev/null | tail -1)
    } >> "$GITHUB_STEP_SUMMARY"
  fi
}

finish() {  # print the summary and exit: 1 if any step failed
  summary
  FINISHED=1
  if [ ${#FAILED[@]} -gt 0 ]; then
    echo "=== $(date '+%F %T') nightly FAILED: ${FAILED[*]} (see the step lines above; logs/nightly.log) ==="
    in_ci && echo "::error title=nightly failed::step(s) ${FAILED[*]} failed; open the step's log group or the nightly-logs artifact"
    exit 1
  fi
  echo "=== $(date '+%F %T') nightly done ==="
  exit 0
}

hard() {  # hard <name> <command...>: on failure stop the night here (nothing is published)
  local name="$1"
  if run_step "$@"; then record "$name" "$LAST_SECS" ok; return 0; fi
  record "$name" "$LAST_SECS" "FAILED: stopped here"
  FAILED+=("$name")
  finish
}

soft() {  # soft <name> <command...>: on failure keep going, fail the run at the end ($SOFT_WHY says why that is safe)
  local name="$1"
  if run_step "$@"; then record "$name" "$LAST_SECS" ok; return 0; fi
  record "$name" "$LAST_SECS" "FAILED: continued${SOFT_WHY:+ ($SOFT_WHY)}"
  FAILED+=("$name")
}

live() {  # live <replayed: 1|0> <name> <command...>: a live fetch. Soft when the archive replay ran
  # (a failed partition keeps the copy it loaded); hard when there was no archive, because then a
  # failed partition has no data at all and the build would fail on it or publish without it
  local replayed="$1"; shift
  if [ "$replayed" = 1 ]; then
    SOFT_WHY="failed partitions keep the copy the archive replay loaded" soft "$@"
    return 0
  fi
  local name="$1"
  if run_step "$@"; then record "$name" "$LAST_SECS" ok; return 0; fi
  record "$name" "$LAST_SECS" "FAILED: stopped here (no archive to fall back on: the failed partitions have no data)"
  FAILED+=("$name")
  finish
}

skip() {  # skip <name> <reason>
  echo "--- $(date '+%T') step $1: skipped ($2)"
  record "$1" 0 "skipped: $2"
}

q() { psql "$LOCAL_DSN" -v ON_ERROR_STOP=1 -Atqc "$1"; }

# dbt overwrites dbt/target/run_results.json on every invocation: keep each step's copy in logs/
dbt_step() {  # dbt_step <name> <dbt args...>
  local name="$1" rc=0; shift
  uv run league-lab dbt "$@" || rc=$?
  [ -f dbt/target/run_results.json ] && cp dbt/target/run_results.json "logs/run_results.$name.json"
  return "$rc"
}

# State the archive cannot rebuild: the two backtests behind the Rankings scoreboards (written by
# `league-lab backtest` and `backtest-v2`, the latter minutes of CPU), the DECISION RECORD (plan
# B5: `ops.projections`, each league-week's board frozen at its first kickoff, and the drift
# history `ops.projection_drift` scored on it) and the lineups solved on it (`ops.lineups`,
# `ops.lineup_totals`, and the waiver moves `ops.waiver_moves`; re-solved by `project`, restored only so a soft `project` failure publishes
# last night's board WITH last night's lineups). A fresh database (every CI run) copies them back
# from the hosted copy, where the last sync put them (the sync publishes all of `ops`); the
# backtests are recomputed after the build only when neither place has them, when they come
# from another MODEL_VERSION, or on request (NIGHTLY_BACKTESTS=1). On the Mac every table is
# already in the database: nothing happens.
#
# The record is the one thing this pipeline cannot recompute, so it is handled harder than the
# rest: (1) "cannot reach the hosted copy" is NOT "empty" — the night stops, because refitting
# every played week blind and then publishing it would overwrite the record with refit values;
# (2) a failed copy stops the night too; (3) after `project`, the record is also written to the
# archive ($RAW_DIR/record/, so it rides the Actions cache): if the hosted copy is reachable but
# has lost it (a restore that died midway), the archive's copy is used instead.
STATE_TABLES="ops.backtest_results ops.projection_backtest ops.projection_importance ops.projections ops.projection_drift ops.lineups ops.lineup_totals ops.waiver_moves ops.waiver_upside ops.player_role_alerts ops.player_scenarios"
RECORD_TABLES="ops.projections ops.projection_drift"
RECORD_DIR="$RAW_DIR/record"   # one <schema>.<table>.sql.gz per record table

is_record() { case " $RECORD_TABLES " in *" $1 "*) return 0;; esac; return 1; }

restore_state() {
  local t n h rc
  for t in $STATE_TABLES; do
    n="$(q "select count(*) from $t")" || return 1
    if [ "$n" != 0 ]; then echo "$t: $n rows here, kept"; continue; fi
    if [ -z "${LEAGUE_LAB_HOSTED_ADMIN_URL:-}" ]; then
      echo "$t: empty, no hosted copy configured to restore from"
      is_record "$t" && restore_record_from_archive "$t"
      continue
    fi
    h="$(psql "$LEAGUE_LAB_HOSTED_ADMIN_URL" -Atqc "select count(*) from $t" 2>&1 | head -1)"; rc=${PIPESTATUS[0]}
    if [ "$rc" != 0 ]; then
      if is_record "$t"; then
        echo "$t: cannot read the hosted copy ($h)" >&2
        echo "$t: the decision record cannot be verified; refusing to refit every played week blind" >&2
        return 1
      fi
      echo "$t: cannot read the hosted copy ($h); the backtests step recomputes it"
      continue
    fi
    if [ "$h" = 0 ]; then
      echo "$t: empty here and on the hosted copy"
      is_record "$t" && restore_record_from_archive "$t"
      continue
    fi
    if pg_dump "$LEAGUE_LAB_HOSTED_ADMIN_URL" --data-only --no-owner --no-privileges --table "$t" \
         | psql "$LOCAL_DSN" -v ON_ERROR_STOP=1 -q --single-transaction 2>&1 | grep -v '^ *set_config\|^ *setval\|^ *-*$\|^(1 row)$'; then :; fi
    n="$(q "select count(*) from $t")" || return 1
    if [ "$n" = "$h" ]; then
      echo "$t: restored $n rows from the hosted copy"
    elif is_record "$t"; then
      echo "$t: restore from the hosted copy failed ($n of $h rows); the decision record must not be refit blind" >&2
      return 1
    else
      echo "$t: restore from the hosted copy failed ($n of $h rows); the backtests step recomputes it"
    fi
  done
}

# the archive's copy of the record (written by save_record after every successful `project`)
restore_record_from_archive() {  # restore_record_from_archive <table>
  local t="$1" n f="$RECORD_DIR/$1.sql.gz"
  if [ ! -f "$f" ]; then
    echo "$t: no copy in the archive either ($f): first publication, or the record is gone"
    in_ci && echo "::warning title=decision record::$t is empty on the hosted copy and in the archive: tonight starts a new record (every played week becomes a refit value)"
    return 0
  fi
  echo "$t: taking the archive's copy ($(stat -c %y "$f" | cut -c1-19)) ..."
  if gunzip -c "$f" | psql "$LOCAL_DSN" -v ON_ERROR_STOP=1 -q --single-transaction >/dev/null 2>&1; then :; fi
  n="$(q "select count(*) from $t")" || return 1
  if [ "$n" = 0 ]; then
    echo "$t: the archive's copy did not restore" >&2
    return 1
  fi
  echo "$t: restored $n rows from the archive's copy"
}

save_record() {  # a copy of each record table next to the archive, so it rides the Actions cache
  local t f
  mkdir -p "$RECORD_DIR"
  for t in $RECORD_TABLES; do
    f="$RECORD_DIR/$t.sql.gz"
    if pg_dump "$LOCAL_DSN" --data-only --no-owner --no-privileges --table "$t" | gzip -1 > "$f.tmp"; then
      mv "$f.tmp" "$f"
      echo "$t: saved to $f ($(du -h "$f" | cut -f1))"
    else
      rm -f "$f.tmp"
      echo "$t: could not save to $f" >&2
      return 1
    fi
  done
}

backtests() {
  local n1 n2 mv
  n1="$(q 'select count(*) from ops.backtest_results')" || return 1
  if [ "$n1" = 0 ] || [ "${NIGHTLY_BACKTESTS:-}" = 1 ]; then
    echo "baseline backtest: ${n1} rows${NIGHTLY_BACKTESTS:+, NIGHTLY_BACKTESTS=1}: league-lab backtest (2023-2025, seconds)"
    uv run league-lab backtest || return 1
  else
    echo "baseline backtest: $n1 rows, kept"
  fi
  mv="$(uv run python -c 'from league_lab.projections import MODEL_VERSION; print(MODEL_VERSION)')" || return 1
  n2="$(q "select count(*) from ops.projection_backtest where model_version = '$mv'")" || return 1
  if [ "$n2" = 0 ] || [ "${NIGHTLY_BACKTESTS:-}" = 1 ]; then
    echo "projection v2 backtest: ${n2} rows for model $mv${NIGHTLY_BACKTESTS:+, NIGHTLY_BACKTESTS=1}: league-lab backtest-v2 (walk-forward 2021-2025, minutes)"
    uv run league-lab backtest-v2 || return 1
  else
    echo "projection v2 backtest: $n2 rows for model $mv, kept"
  fi
}

# `project` ends by scoring the board as last built, i.e. before tonight's refit (plan M-06). On a
# fresh database that board was empty, so nothing got scored: score the board just published.
# Where project's own pass wrote rows (the Mac, every night after the first) they are kept.
drift_if_unscored() {
  local n
  n="$(q 'select count(*) from ops.projection_drift where season = (select max(season) from analytics.mart_player_week_projections)')" || return 1
  if [ "$n" != 0 ]; then
    echo "ops.projection_drift: $n rows for the projected season, written by project: kept"
    return 0
  fi
  echo "no drift rows for the projected season (fresh database): league-lab drift on the board just built"
  uv run league-lab drift
}

# --- the night ----------------------------------------------------------------------------------
hard migrate uv run league-lab db migrate
hard restore-state restore_state

# 1. Replay the archive. On a fresh database this restores everything as of the last run; on a
#    loaded one every partition's checksum matches and is skipped.
SLEEPER_REPLAYED=1; NFLVERSE_REPLAYED=1
if [ "${NIGHTLY_SLEEPER_OFFLINE:-}" = 1 ]; then
  # the replay is the only Sleeper load tonight, so it must succeed
  hard replay-sleeper uv run league-lab ingest sleeper --offline
elif [ ! -f "$RAW_DIR/sleeper/state/nfl.json.gz" ]; then
  SLEEPER_REPLAYED=0
  skip replay-sleeper "no Sleeper archive yet (first run or cache miss); the live step loads the whole chain"
elif run_step replay-sleeper uv run league-lab ingest sleeper --offline; then
  record replay-sleeper "$LAST_SECS" ok
else
  record replay-sleeper "$LAST_SECS" "incomplete: the live Sleeper step reloads it"
fi

if [ "$FULL" = 1 ]; then
  skip replay-nflverse-history "--full: every historical season is re-checked live instead"
  hard fetch-nflverse-history uv run league-lab ingest nfl --seasons "$HISTORY"
elif [ ! -d "$RAW_DIR/nflverse" ]; then
  skip replay-nflverse-history "no nflverse archive yet (first run or cache miss)"
  hard fetch-nflverse-history uv run league-lab ingest nfl --seasons "$HISTORY"
elif run_step replay-nflverse-history uv run league-lab ingest nfl --offline --seasons "$HISTORY"; then
  record replay-nflverse-history "$LAST_SECS" ok
else
  # partitions without an archived file (a partial cache, a newly registered dataset): download
  # them; present ones answer 304 and are skipped. History must be complete before a build.
  record replay-nflverse-history "$LAST_SECS" "incomplete: fetched live below"
  hard fetch-nflverse-history uv run league-lab ingest nfl --seasons "$HISTORY"
fi

if [ ! -d "$RAW_DIR/nflverse" ]; then
  NFLVERSE_REPLAYED=0
  skip replay-nflverse-current "no archive for $SEASON yet; the live step loads it"
elif run_step replay-nflverse-current uv run league-lab ingest nfl --offline --seasons "$SEASON"; then
  record replay-nflverse-current "$LAST_SECS" ok
else
  record replay-nflverse-current "$LAST_SECS" "incomplete: the live nflverse step reloads it"
fi

# 2. Live: what changed upstream since the archive was written.
if [ "${NIGHTLY_SLEEPER_OFFLINE:-}" = 1 ]; then
  skip fetch-sleeper "NIGHTLY_SLEEPER_OFFLINE=1: league data is the archive's (state fetched $(sed -n 's/.*"fetched_at": "\([^"]*\)".*/\1/p' "$RAW_DIR/sleeper/state/nfl.json.gz.meta.json" 2>/dev/null || echo '?'))"
else
  live "$SLEEPER_REPLAYED" fetch-sleeper uv run league-lab ingest sleeper
fi
live "$NFLVERSE_REPLAYED" fetch-nflverse-current uv run league-lab ingest nfl --seasons "$SEASON"

# 3. Build, then the pieces that read the built marts.
hard dbt-build dbt_step dbt-build build
hard backtests backtests
# projection v2. A failure is fatal only when there is no earlier board to fall back on (neither this
# database nor the hosted copy had projections: publishing would blank the Rankings pages); otherwise
# last night's projections stay (on a fresh database: the ones restore-state copied back).
if run_step project uv run league-lab project; then
  record project "$LAST_SECS" ok
elif [ "$(q 'select count(*) from ops.projections')" != 0 ]; then
  record project "$LAST_SECS" "FAILED: continued with the previous projections"
  FAILED+=(project)
else
  record project "$LAST_SECS" "FAILED: stopped here (no earlier projections)"
  FAILED+=(project)
  finish
fi
soft save-record save_record
# the projection marts on tonight's projections (+ mart_projection_backtest+: dbt's view swap
# cascades to mart_projection_drift, which must be rebuilt or it never reaches the hosted copy)
# and the lineup mart on the lineups `project` solved last (plan B1)
hard projection-marts dbt_step projection-marts build --select mart_player_week_projections+ mart_projection_backtest+ mart_lineup_recommendation+ mart_projection_importance mart_player_role_alerts+ mart_waiver_upside
soft drift drift_if_unscored

# 4. Keep and publish.
if [ "${NIGHTLY_BACKUP:-}" = 1 ]; then
  soft backup ./scripts/backup.sh
else
  skip backup "NIGHTLY_BACKUP is not 1 (the CI database is thrown away; its durable state is the archive cache + the hosted copy)"
fi
if [ -n "${LEAGUE_LAB_HOSTED_ADMIN_URL:-}" ]; then
  hard sync-hosted ./scripts/sync_to_hosted.sh
else
  skip sync-hosted "LEAGUE_LAB_HOSTED_ADMIN_URL is not set"
fi

finish
