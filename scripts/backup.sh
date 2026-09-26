#!/usr/bin/env bash
# Dump the league_lab database (custom format) into backups/ and keep the last 7 daily copies
# plus one weekly copy (plan §7). Restore test:  ./scripts/restore_test.sh backups/<file>.dump
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
set -a; [ -f .env ] && source .env; set +a
[ -x /opt/homebrew/opt/postgresql@17/bin/pg_dump ] && export PATH="/opt/homebrew/opt/postgresql@17/bin:$PATH"

mkdir -p backups
STAMP="$(date +%Y%m%d_%H%M%S)"
OUT="backups/league_lab_${STAMP}.dump"
export PGPASSWORD="${LEAGUE_LAB_DB_PASSWORD:-}"
pg_dump -h "${LEAGUE_LAB_DB_HOST:-localhost}" -p "${LEAGUE_LAB_DB_PORT:-5432}" -U "${LEAGUE_LAB_DB_USER:-league_lab_pipeline}" \
  -d "${LEAGUE_LAB_DB_NAME:-league_lab}" -Fc -Z 6 -f "$OUT"
echo "wrote $OUT ($(du -h "$OUT" | cut -f1))"

# config/metadata inventory alongside the dump
{
  echo "code_version=$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo unversioned)"
  echo "created_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "pg_dump=$(pg_dump --version)"
} > "backups/league_lab_${STAMP}.inventory.txt"

# retention: 7 most recent daily dumps; keep Sunday copies as weekly
ls -1t backups/league_lab_*.dump 2>/dev/null | tail -n +8 | while read -r f; do
  day="$(echo "$f" | sed -E 's/.*league_lab_([0-9]{8})_.*/\1/')"
  if [ "$(date -j -f %Y%m%d "$day" +%u 2>/dev/null || date -d "$day" +%u)" != "7" ]; then
    rm -f "$f" "${f%.dump}.inventory.txt"
  fi
done
