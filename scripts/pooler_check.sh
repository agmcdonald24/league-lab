#!/usr/bin/env bash
# The pooler check (IS-4, Wave I-S): what only the hosted setup can break, caught here. A local PgBouncer in
# TRANSACTION mode in front of a sandbox database, configured as strictly as a hosted pooler (no startup parameters
# ignored, a pool of 2, prepared statements as Neon keeps them), and through it the code that talks to the hosted
# database: the readiness probe, the API's pool (db.query, repeated past psycopg's prepare threshold), the usage
# writer's connection, the sync's read-only verification queries, and the post-deploy check against an API started on
# the pooled address. One line per check; exit 1 if any fails.
#
#   scripts/pooler_check.sh                         # this tree
#   scripts/pooler_check.sh --ready-from 748ff76    # + the readiness probe of another commit (the 2026-10-08 bug)
#
# Needs: pgbouncer (apt-get install -y pgbouncer), sudo -u postgres (PgBouncer will not run as root), the .env of this
# worktree (the database and the two roles; passwords go only into a 0600 file in a temp dir, removed at exit).
# Env: POOLER_PORT (6439), POOLER_API_PORT (8964), POOLER_DB (the .env's LEAGUE_LAB_DB_NAME),
#      POOLER_PREPARED (1000, as Neon's pooler: protocol-level prepared statements kept; 0 = a pooler that keeps none -
#      the API's pool then fails: psycopg prepares a statement after 5 runs, see docs/HOSTING.md).
set -uo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"
OLD_REF=""
[ "${1:-}" = --ready-from ] && OLD_REF="${2:?--ready-from <commit>}"
PORT="${POOLER_PORT:-6439}"; API_PORT="${POOLER_API_PORT:-8964}"; PREPARED="${POOLER_PREPARED:-1000}"
envval() { grep "^$1=" .env | head -1 | cut -d= -f2-; }
DB="${POOLER_DB:-$(envval LEAGUE_LAB_DB_NAME)}"
APP_USER="$(envval LEAGUE_LAB_APP_DB_USER)"; APP_USER="${APP_USER:-league_lab_app}"
PIPE_USER="$(envval LEAGUE_LAB_DB_USER)"; PIPE_USER="${PIPE_USER:-league_lab_pipeline}"
APP_PW="$(envval LEAGUE_LAB_APP_DB_PASSWORD)"; PIPE_PW="$(envval LEAGUE_LAB_DB_PASSWORD)"
command -v pgbouncer >/dev/null || { echo "pgbouncer is not installed (apt-get install -y pgbouncer)" >&2; exit 2; }

DIR="$(mktemp -d)"; chmod 755 "$DIR"
API_PID=""
cleanup() {
  [ -n "$API_PID" ] && kill "$API_PID" 2>/dev/null
  [ -f "$DIR/pgbouncer.pid" ] && sudo -n -u postgres kill "$(cat "$DIR/pgbouncer.pid")" 2>/dev/null
  sleep 0.5; rm -rf "$DIR"
}
trap cleanup EXIT
printf '"%s" "%s"\n"%s" "%s"\n' "$APP_USER" "$APP_PW" "$PIPE_USER" "$PIPE_PW" > "$DIR/userlist.txt"
cat > "$DIR/pgbouncer.ini" <<INI
[databases]
* = host=127.0.0.1 port=5432
[pgbouncer]
listen_addr = 127.0.0.1
listen_port = $PORT
unix_socket_dir =
auth_type = scram-sha-256
auth_file = $DIR/userlist.txt
pool_mode = transaction
default_pool_size = 2
max_client_conn = 60
max_prepared_statements = $PREPARED
ignore_startup_parameters =
server_reset_query =
logfile = $DIR/pgbouncer.log
pidfile = $DIR/pgbouncer.pid
INI
chown -R postgres "$DIR"; chmod 600 "$DIR/userlist.txt"
sudo -n -u postgres pgbouncer -d "$DIR/pgbouncer.ini" || { echo "pgbouncer did not start" >&2; exit 2; }
for _ in $(seq 1 30); do (exec 3<>/dev/tcp/127.0.0.1/"$PORT") 2>/dev/null && break; sleep 0.2; done
POOLED_APP="postgresql://${APP_USER}:${APP_PW}@127.0.0.1:${PORT}/${DB}"
POOLED_PIPE="postgresql://${PIPE_USER}:${PIPE_PW}@127.0.0.1:${PORT}/${DB}"
echo "pooler check: PgBouncer $(pgbouncer --version | head -1 | awk '{print $2}') in transaction mode on 127.0.0.1:$PORT -> $DB (pool 2, prepared statements kept: $PREPARED, startup parameters ignored: none)"

FAILS=0
line() { local v="$1"; shift; [ "$v" = ok ] || FAILS=$((FAILS + 1)); printf '%-4s %s\n' "$v" "$*"; }

# 1. the readiness probe (this tree, and another commit's when asked)
probe() {  # probe <label> <ready.py path>
  local out
  out="$(cd api && LEAGUE_LAB_APP_DB_URL="$POOLED_APP" PYTHONPATH=. uv run --quiet python - "$2" 2>&1 <<'PY'
import importlib.util, os, sys, pathlib, tempfile
import league_lab_api.settings, league_lab_api.db  # noqa: F401 - puts src/ on the path as the app does
src = pathlib.Path(sys.argv[1]).read_text().replace("from .settings import", "from league_lab_api.settings import")
p = pathlib.Path(tempfile.mkdtemp()) / "ready_under_test.py"; p.write_text(src)
spec = importlib.util.spec_from_file_location("ready_under_test", p); m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
ok, body = m.check(os.environ["LEAGUE_LAB_APP_DB_URL"])
print(("OK " if ok else "BAD ") + f"{body.get('code')}: {body.get('reason')}")
PY
)"
  out="$(echo "$out" | grep -E "^(OK|BAD) " | tail -1)"; [ -n "$out" ] || out="BAD the probe did not run"
  if [[ "$out" == OK* ]]; then line ok "ready probe ($1): ${out#OK }"; else line FAIL "ready probe ($1): ${out#BAD }"; fi
}
probe "this tree" "$ROOT/api/league_lab_api/ready.py"
L1=0; L2=0
if [ -n "$OLD_REF" ]; then
  L1="$(sudo -n -u postgres wc -l < "$DIR/pgbouncer.log")"
  git show "$OLD_REF:api/league_lab_api/ready.py" > "$DIR/ready_old.py" && probe "$OLD_REF" "$DIR/ready_old.py"
  L2="$(sudo -n -u postgres wc -l < "$DIR/pgbouncer.log")"
  echo "     pooler log for $OLD_REF's probe: $(sudo -n -u postgres sed -n "$((L1 + 1)),${L2}p" "$DIR/pgbouncer.log" | grep -m1 -o 'unsupported startup parameter.*' | cut -c1-90)"
fi

# 2. the API's pool, past psycopg's prepare threshold (5 runs of one statement), two pools' worth of clients; the
# usage writer's connection (autocommit, its own read-write transaction)
out="$(cd api && LEAGUE_LAB_APP_DB_URL="$POOLED_APP" PYTHONPATH=. uv run --quiet python 2>&1 <<'PY'
import os, psycopg
from concurrent.futures import ThreadPoolExecutor
from league_lab_api import db
db.clear_cache()
def one(i):
    return int(db.query("select count(*) as n from ops.projections where week = %s", (i % 3 + 1,), ttl=0)["n"].iloc[0])
try:
    with ThreadPoolExecutor(6) as ex:
        res = list(ex.map(one, range(24)))
    print(f"OK pool: 24 queries on 6 threads, each statement run 8 times (past the prepare threshold): {len(set(res))} distinct answers")
except Exception as e:
    print(f"BAD pool: {e.__class__.__name__}: {str(e).splitlines()[0][:160]}")
try:
    with psycopg.connect(os.environ["LEAGUE_LAB_APP_DB_URL"], autocommit=True, connect_timeout=5, application_name="league-lab-usage") as c:
        with c.transaction():
            c.execute("set transaction read write"); c.execute("select 1")
    print("OK usage writer: connect (application_name), BEGIN; SET TRANSACTION READ WRITE; a statement; COMMIT")
except Exception as e:
    print(f"BAD usage writer: {e.__class__.__name__}: {str(e).splitlines()[0][:160]}")
PY
)"
while IFS= read -r l; do case "$l" in "OK "*) line ok "${l#OK }";; "BAD "*) line FAIL "${l#BAD }";; esac; done <<< "$out"

# 3. the sync's read-only verification (the queries scripts/sync_to_hosted.sh runs after a restore), as psql does it
if v="$(psql "$POOLED_PIPE" -v ON_ERROR_STOP=1 -At -c "select 'analytics tables: ' || count(*) from information_schema.tables where table_schema = 'analytics';" \
      -c "select 'published through: ' || coalesce(max(loaded_at)::text, 'n/a') from ops.source_partition;" \
      -c "select pg_size_pretty(pg_database_size(current_database()))" \
      -c "select coalesce(obj_description(to_regnamespace('analytics'), 'pg_namespace'), 'no publication comment')" 2>&1)"; then
  line ok "sync verification: $(echo "$v" | tr '\n' ';' | sed 's/;$//')"
else
  line FAIL "sync verification: $(echo "$v" | head -1)"
fi

# 4. the API on the pooled address, and the post-deploy journey against it
(cd api && LEAGUE_LAB_APP_DB_URL="$POOLED_APP" LEAGUE_LAB_NOW="${LEAGUE_LAB_NOW:-2026-10-03T16:00:00Z}" \
  LEAGUE_LAB_SLEEPER_FIXTURES="$ROOT/api/tests/fixtures/sleeper" LEAGUE_LAB_MFL_FIXTURES="$ROOT/api/tests/fixtures/mfl" \
  LEAGUE_LAB_MFL_YEAR=2026 LEAGUE_LAB_PLAYER_IDS_CSV="$ROOT/api/tests/fixtures/ff/db_playerids.csv" LEAGUE_LAB_GATE=open \
  LEAGUE_LAB_AVAILABILITY=off LEAGUE_LAB_USAGE=off LEAGUE_LAB_NEWS=off OMP_NUM_THREADS=1 PYTHONPATH=. \
  exec uv run --quiet uvicorn league_lab_api.main:app --port "$API_PORT" > "$DIR/api.log" 2>&1) &
API_PID=$!
for _ in $(seq 1 60); do curl -sf -o /dev/null "http://127.0.0.1:$API_PORT/api/health" && break; sleep 1; done
pdc="$(python3 scripts/post_deploy_check.py "http://127.0.0.1:$API_PORT" 2>&1)"; rc=$?
echo "$pdc" | sed -n '2,$p' | sed 's/^/     post-deploy: /'
pooled_fails="$(echo "$pdc" | grep -E '^FAIL' | grep -cE '^FAIL +[a-z ]+ +(0|5[0-9][0-9]) |database|unreachable')"
if [ "$rc" = 0 ]; then line ok "post-deploy check on the pooled API: all checks passed"
elif [ "$pooled_fails" = 0 ]; then line ok "post-deploy check on the pooled API: every route answered through the pooler ($(echo "$pdc" | grep -c '^FAIL ') content check(s) failed on the data, not the connection: the lines above)"
else line FAIL "post-deploy check on the pooled API: $pooled_fails check(s) failed on a 5xx / no answer / the database (the lines above)"; fi
# the logs, minus the lines of the other commit's probe (that failure is expected and already counted above)
sudo -n -u postgres awk -v a="$L1" -v b="$L2" 'NR <= a || NR > b' "$DIR/pgbouncer.log" > "$DIR/pooler_mine.log"
errs="$(cat "$DIR/pooler_mine.log" "$DIR/api.log" 2>/dev/null | grep -ciE 'prepared statement .* (does not exist|already exists)|unsupported startup parameter|server conn crashed')"
[ "$errs" = 0 ] && line ok "pooler / API logs: no prepared-statement or startup-parameter errors" \
  || line FAIL "pooler / API logs: $errs prepared-statement / startup-parameter errors: $(grep -hiE 'prepared statement|unsupported startup' "$DIR/pooler_mine.log" "$DIR/api.log" | head -2 | cut -c1-160 | tr '\n' ' ')"

[ "$FAILS" = 0 ] && echo "POOLER CHECK PASSED" || echo "POOLER CHECK FAILED: $FAILS"
[ "$FAILS" = 0 ]
