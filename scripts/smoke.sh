#!/usr/bin/env bash
# Smoke test of a running isuckatfantasy (League Lab) server (plan H0, Wave H): one line per check, exit 1 if any check fails.
#
#   scripts/smoke.sh <base-url> [password] [sleeper-username]
#
#   scripts/smoke.sh https://isuckatfantasy.io 'the beta password'      (league-lab.onrender.com answers too)
#   scripts/smoke.sh http://localhost:8701 h0-beta-pass test_manager      # + a league by username (calls Sleeper)
#
# Checks: /api/health (200, the version, the database's as_of, database "ok"); the web app at "/"; the beta gate
# (401 without the password, 401 with a wrong one, 200 from POST /api/login with the right one); /api/status;
# /api/leagues (the house leagues); /api/leagues/<league>/rosters; /api/my-week for a house league and team.
# Only when a Sleeper username is given: /api/leagues?username=<it> and a My Week of that user's first league
# (those two ask Sleeper, through the server's cache and call budget).
# Optional: SMOKE_LEAGUE / SMOKE_TEAM pick the house league and roster for My Week (default: the first of each);
# SMOKE_TIMEOUT seconds per request (default 90: a server that was asleep takes up to a minute to answer).
# Needs curl and python3 (for reading the JSON). Nothing is written anywhere; the password is never printed.
set -uo pipefail

if [[ $# -lt 1 || "$1" == "-h" || "$1" == "--help" ]]; then
  awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "$0"
  exit 2
fi
BASE="${1%/}"
PASSWORD="${2:-}"
USERNAME="${3:-}"
TIMEOUT="${SMOKE_TIMEOUT:-90}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
FAILS=0
TOKEN=""

# one request: prints "<status> <seconds>", the body in $TMP/body
request() {   # request <method> <path> [json-body] [token]
  local method="$1" path="$2" data="${3:-}" token="${4:-}"
  local args=(-sS -o "$TMP/body" -w '%{http_code} %{time_total}' --max-time "$TIMEOUT" -X "$method")
  [[ -n "$token" ]] && args+=(-H "Authorization: Bearer $token")
  [[ -n "$data" ]] && args+=(-H 'Content-Type: application/json' --data-binary "$data")
  curl "${args[@]}" "$BASE$path" 2>"$TMP/err" || echo "000 0"
}

# reads $TMP/body as JSON into `b`, evaluates a Python condition; prints the summary expression or the reason
judge() {     # judge <python condition> <python summary expression>
  python3 - "$TMP/body" "$1" "$2" <<'PY'
import json, sys
path, cond, summary = sys.argv[1:4]
raw = open(path, encoding="utf-8", errors="replace").read()
try:
    b = json.loads(raw)
except ValueError:
    b = raw
try:
    ok = bool(eval(cond, {"b": b}))
    text = str(eval(summary, {"b": b}))
except Exception as exc:  # noqa: BLE001 - any surprise in the body is a failed check
    ok = False
    text = "not the expected answer" if isinstance(b, str) else "{}: {}".format(exc.__class__.__name__, exc)
if not ok:
    text = text + " | body: " + raw[:160].replace("\n", " ")
print(("ok " if ok else "bad ") + text)
PY
}

# check <label> <expected status> <method> <path> <python condition> <python summary> [json-body] [token]
check() {
  local label="$1" want="$2" method="$3" path="$4" cond="$5" summary="$6" data="${7:-}" token="${8:-}"
  local got code secs verdict text
  got="$(request "$method" "$path" "$data" "$token")"
  code="${got%% *}"
  secs="${got##* }"
  if [[ "$code" == "000" ]]; then
    verdict="FAIL"
    text="no answer: $(head -c 160 "$TMP/err" | tr '\n' ' ')"
  else
    text="$(judge "$cond" "$summary")"
    if [[ "$code" == "$want" && "$text" == ok\ * ]]; then verdict="ok"; else verdict="FAIL"; fi
    text="${text#* }"
  fi
  [[ "$verdict" == "FAIL" ]] && FAILS=$((FAILS + 1))
  printf '%-4s %-44s %s %5.2fs  %s\n' "$verdict" "$label" "$code" "$secs" "$text"
}

json_string() { python3 -c 'import json, sys; print(json.dumps({"password": sys.argv[1]}))' "$1"; }
field() { python3 -c "import json, sys; b = json.load(open(sys.argv[1])); print($1)" "$TMP/body" 2>/dev/null; }

echo "League Lab smoke test: $BASE"

# 1. health (no password): the release, the database's newest projection fit, the database reachable
check "health" 200 GET /api/health \
  'b["ok"] is True and b["version"] and b["as_of"] and b["database"] == "ok"' \
  '"version {version}, as_of {as_of}, board {board_source}, database {database}".format(**b)'

# 2. the web app's page
check "web app (/)" 200 GET / \
  'isinstance(b, str) and "<html" in b.lower() and "isuckatfantasy" in b' '"index.html served (isuckatfantasy)"'

# 3. the beta gate
SESSION="$(request GET /api/session)"
GATE="$(field 'b["gate"]')"
if [[ "${SESSION%% *}" != "200" || -z "$GATE" ]]; then
  printf '%-4s %-44s %s\n' "FAIL" "gate (GET /api/session)" "no answer (${SESSION%% *}): is the address right and the server Live?"
  echo "FAILED: the server does not answer; the remaining checks were not run."
  exit 1
elif [[ "$GATE" == "True" ]]; then
  check "gate: /api/status without the password" 401 GET /api/status 'isinstance(b, dict) and "error" in b' '"refused, as it should be"'
  check "gate: login with a wrong password" 401 POST /api/login 'isinstance(b, dict) and "error" in b' '"refused, as it should be"' \
    "$(json_string 'not-the-password-smoke')"
  if [[ -z "$PASSWORD" ]]; then
    printf '%-4s %-44s %s\n' "FAIL" "gate: login" "this server has a password: pass it as the second argument"
    echo "FAILED: the remaining checks need the password."
    exit 1
  else
    check "gate: login (POST /api/login)" 200 POST /api/login 'b["ok"] is True and b["token"]' '"signed in"' "$(json_string "$PASSWORD")"
    TOKEN="$(field 'b.get("token") or ""')"
  fi
else
  printf '%-4s %-44s %s\n' "ok" "gate" "no password on this server (LEAGUE_LAB_APP_PASSWORD unset): open to anyone with the link"
fi

# 4. freshness and the Sleeper budget
check "status" 200 GET /api/status 'b["freshness"] and "sleeper" in b' \
  'b["freshness"][:80] + " ... sleeper " + b["sleeper"]["mode"] + ", " + str(b["sleeper"]["calls"]) + " calls"' "" "$TOKEN"

# 5. the house leagues, a team picker, a My Week
check "leagues (house)" 200 GET /api/leagues 'isinstance(b, list) and len(b) >= 1' \
  '", ".join("{league_name} {season}".format(**x) for x in b)' "" "$TOKEN"
LEAGUE="${SMOKE_LEAGUE:-$(field 'b[0]["league_id"]')}"
if [[ -n "$LEAGUE" ]]; then
  check "rosters ($LEAGUE)" 200 GET "/api/leagues/$LEAGUE/rosters" 'isinstance(b, list) and len(b) >= 2' \
    'str(len(b)) + " teams"' "" "$TOKEN"
  TEAM="${SMOKE_TEAM:-$(field 'sorted(x["roster_id"] for x in b)[0]')}"
  check "my week ($LEAGUE, team $TEAM)" 200 GET "/api/my-week?league=$LEAGUE&team=$TEAM" \
    'b["lineup"] and b.get("source", "database") == "database"' \
    '"week {}, {} lineup rows, opponent {}".format(b.get("week"), len(b["lineup"]), (b.get("opponent") or {}).get("team_name"))' \
    "" "$TOKEN"
fi

# 6. only when asked: a league by Sleeper username, then that user's first league on demand (asks Sleeper)
if [[ -n "$USERNAME" ]]; then
  check "leagues of Sleeper user $USERNAME" 200 GET "/api/leagues?username=$USERNAME" 'len(b["leagues"]) >= 1' \
    '", ".join("{name} (team {roster_id})".format(**x) for x in b["leagues"])' "" "$TOKEN"
  # a league the database does not have first (the on-demand path), else the first with a team of theirs
  PICK="$(field 'next("{league_id} {roster_id}".format(**x) for x in sorted(b["leagues"], key=lambda x: bool(x.get("in_database"))) if x["roster_id"] is not None)')"
  if [[ -n "$PICK" ]]; then
    check "my week (${PICK% *}, team ${PICK#* }, any league)" 200 GET "/api/my-week?league=${PICK% *}&team=${PICK#* }" \
      'b["lineup"]' '"week {}, source {}, {} lineup rows".format(b.get("week"), b.get("source"), len(b["lineup"]))' "" "$TOKEN"
  fi
fi

if [[ "$FAILS" -gt 0 ]]; then
  echo "FAILED: $FAILS check(s). What to do: docs/DEPLOY.md § When it breaks."
  exit 1
fi
echo "All checks passed."
