#!/usr/bin/env bash
# Daily refresh: Sleeper league + current NFL season + dbt build, then a backup on success.
# Safe to run by hand any time ("manual refresh is a first-class operation", plan §7).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
mkdir -p logs
[ -x /opt/homebrew/opt/postgresql@17/bin/psql ] && export PATH="/opt/homebrew/opt/postgresql@17/bin:$PATH"
export PATH="/opt/homebrew/bin:$HOME/.local/bin:$PATH"

# one writer at a time (plan §2): refuse to start if another refresh holds the lock
LOCK="$ROOT/.state/refresh.lock"
mkdir -p "$ROOT/.state"
if ! mkdir "$LOCK" 2>/dev/null; then
  echo "$(date '+%F %T') another refresh is running (lock: $LOCK); exiting" >&2
  exit 3
fi
trap 'rmdir "$LOCK"' EXIT

echo "=== $(date '+%F %T') refresh start ==="
if ! pg_isready -q -h "${LEAGUE_LAB_DB_HOST:-localhost}" -p "${LEAGUE_LAB_DB_PORT:-5432}"; then
  echo "PostgreSQL is not accepting connections; start it with: brew services start postgresql@17" >&2
  exit 2
fi
uv run league-lab refresh "$@"
./scripts/backup.sh || echo "backup failed (data was refreshed successfully)" >&2
# publish the marts to the hosted database when one is configured (plan S-03)
if [ -n "${LEAGUE_LAB_HOSTED_ADMIN_URL:-}" ]; then
  ./scripts/sync_to_hosted.sh || echo "hosted sync failed (local data is fine; run make sync-hosted)" >&2
fi
echo "=== $(date '+%F %T') refresh done ==="
