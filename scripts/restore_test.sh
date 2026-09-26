#!/usr/bin/env bash
# Restore a backup into a throwaway database (league_lab_restore_test) and run row-count checks.
# Usage: ./scripts/restore_test.sh backups/league_lab_YYYYMMDD_HHMMSS.dump
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
[ $# -eq 1 ] || { echo "usage: $0 <backup.dump>" >&2; exit 2; }
DUMP="$1"
[ -x /opt/homebrew/opt/postgresql@17/bin/pg_restore ] && export PATH="/opt/homebrew/opt/postgresql@17/bin:$PATH"
set -a; [ -f .env ] && source .env; set +a
TEST_DB="league_lab_restore_test"

psql -q -d postgres -c "drop database if exists ${TEST_DB}"
psql -q -d postgres -c "create database ${TEST_DB} owner league_lab_pipeline"
export PGPASSWORD="${LEAGUE_LAB_DB_PASSWORD:-}"
pg_restore -h "${LEAGUE_LAB_DB_HOST:-localhost}" -U "${LEAGUE_LAB_DB_USER:-league_lab_pipeline}" -d "$TEST_DB" --no-owner --no-privileges "$DUMP"

echo "row counts in ${TEST_DB} vs live:"
for t in raw.nfl_player_stats_week raw.sleeper_matchup analytics.fct_player_game analytics.league_player_week; do
  live=$(psql -At -h "${LEAGUE_LAB_DB_HOST:-localhost}" -U "${LEAGUE_LAB_DB_USER:-league_lab_pipeline}" -d "${LEAGUE_LAB_DB_NAME:-league_lab}" -c "select count(*) from $t" 2>/dev/null || echo "n/a")
  rest=$(psql -At -h "${LEAGUE_LAB_DB_HOST:-localhost}" -U "${LEAGUE_LAB_DB_USER:-league_lab_pipeline}" -d "$TEST_DB" -c "select count(*) from $t" 2>/dev/null || echo "n/a")
  printf '  %-36s restored=%-10s live=%s\n' "$t" "$rest" "$live"
done
echo "drop the test database when satisfied: psql -d postgres -c 'drop database ${TEST_DB}'"
