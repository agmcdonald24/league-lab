#!/bin/bash
# Wave I-K (IK-3): record the setup flow's answers for web/e2e/ik3 from a fixture API — the API's own JSON on the
# synthetic leagues: IK-1's ESPN fixtures (api/tests/fixtures/espn_leagues: 4242 public, 5150 private) and IK-2's Yahoo
# fixtures (api/tests/fixtures/yahoo: 461.l.4242), plus the Sleeper / MFL fixtures. Nothing here calls ESPN or Yahoo.
#   web/e2e/ik3/record.sh            (repository root; needs the database in .env for My Week; ports 8743-8745)
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
OUT=$ROOT/web/fixtures/ik3
CACHE=${CACHE:-$(mktemp -d)}
mkdir -p "$OUT"
cd "$ROOT/api"
common() {
  env -u LEAGUE_LAB_APP_PASSWORD -u LEAGUE_LAB_AVAILABILITY \
    LEAGUE_LAB_SLEEPER_FIXTURES=$PWD/tests/fixtures/sleeper LEAGUE_LAB_MFL_FIXTURES=$PWD/tests/fixtures/mfl \
    LEAGUE_LAB_PLAYER_IDS_CSV=$PWD/tests/fixtures/ff/db_playerids.csv LEAGUE_LAB_MFL_YEAR=2026 \
    LEAGUE_LAB_ESPN_LEAGUE_FIXTURES=$PWD/tests/fixtures/espn_leagues LEAGUE_LAB_ESPN_SEASON=2026 \
    LEAGUE_LAB_NOW=2026-10-03T16:00:00Z LEAGUE_LAB_CACHE_DIR=$CACHE "$@"
}
start() { # port, extra env...
  local port=$1; shift
  common env "$@" uv run uvicorn league_lab_api.main:app --port "$port" >"$CACHE/api_$port.log" 2>&1 &
  for _ in $(seq 60); do curl -sf "localhost:$port/api/health" >/dev/null 2>&1 && return; sleep 1; done
  echo "API on $port did not start" >&2; exit 1
}
get() { curl -s -o "$OUT/$2" -w "%{http_code} $2\n" "localhost:$1$3" ${4:+-H "Cookie: $4"}; }
# 8743: Yahoo in fixture mode (set up), the ESPN private switch off
start 8743 LEAGUE_LAB_YAHOO_FIXTURES=$PWD/tests/fixtures/yahoo
get 8743 providers.json /api/providers
get 8743 espn_4242.json "/api/leagues?espn=4242"
get 8743 espn_link_team.json "/api/leagues?espn=https%3A%2F%2Ffantasy.espn.com%2Ffootball%2Fteam%3FleagueId%3D4242%26teamId%3D3"
get 8743 error_espn_private.json "/api/leagues?espn=5150"
get 8743 error_espn_unknown.json "/api/leagues?espn=777"
get 8743 error_espn_link.json "/api/leagues?espn=https%3A%2F%2Fexample.com%2Fx"
get 8743 yahoo_me_not_connected.json "/api/leagues?yahoo_me=1"
get 8743 yahoo_me_connected.json "/api/leagues?yahoo_me=1" "ll_yahoo=fixture"
get 8743 yahoo_461.l.4242.json "/api/leagues?yahoo=https%3A%2F%2Ffootball.fantasysports.yahoo.com%2Ff1%2F4242%2F3" "ll_yahoo=fixture"
get 8743 error_yahoo_link.json "/api/leagues?yahoo=not%20a%20league" "ll_yahoo=fixture"
get 8743 my-week_espn_4242_1.json "/api/my-week?league=espn%3A4242&team=1"
get 8743 my-week_yahoo_461.l.4242_3.json "/api/my-week?league=yahoo%3A461.l.4242&team=3" "ll_yahoo=fixture"
# 8744: a server with no Yahoo keys ("coming soon") and the ESPN private switch on
start 8744 LEAGUE_LAB_ESPN_PRIVATE=on LEAGUE_LAB_API_SECRET=ik3-recording-secret-not-real-0123456789
get 8744 providers_private_no_yahoo.json /api/providers
get 8744 error_espn_private_form.json "/api/leagues?espn=5150"
get 8744 yahoo_me_not_configured.json "/api/leagues?yahoo_me=1"
kill %1 %2 2>/dev/null || true
