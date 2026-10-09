#!/usr/bin/env bash
# The release gate (IR-3, Wave I-R): the decision suite that must pass before an image is published or deployed.
# .github/workflows/image.yml's `gate` job runs exactly this; the image job needs it (and Render deploys only a commit
# whose checks are green: render.yaml autoDeployTrigger checksPass). Run it yourself before a merge:
#
#   scripts/gate.sh            # python + web (about 2-4 minutes here)
#   scripts/gate.sh python     # the decision suite + ruff only
#   scripts/gate.sh web        # eslint + svelte-check/tsc (npm run lint) + the build
#
# The decision suite needs NO warehouse: every database address is pointed at a closed port below, so a test that
# quietly started reading Postgres fails here (or skips — and a skip FAILS the gate: a gate that skips is no gate).
# The suites run at the pinned moment (tests/conftest.py, api/tests/conftest.py: LEAGUE_LAB_NOW).
#   root (src/league_lab): trade math on hand-built frames (test_trades, test_trades_ii1, test_roster_value),
#     lineup legality and slot assignment incl. FLEX cascades, locks and byes (test_lineup*, test_ir3_gate), the
#     replacement chain's words from the actual seating (test_lineup_ii0), league scoring (test_scoring*), K / DEF units
#     (test_kdef), MFL team units and slots (test_mfl_il2), waivers and required drops (test_waivers*), the decision
#     odds (test_decisions), the card words (test_cards), the frozen record (test_projection_freeze), the memory budget
#     (test_memo), the pinned clock (test_clock), the post-deploy check's judgements (test_ir3_post_deploy)
#   api: readiness (test_ir3 without its one database test), the image's build context (test_build_context)
# Outside the gate (they need the warehouse; the PO runs them at merge, the nightly runs dbt's tests): the API's route
# suites (test_decisions, test_ii1, test_parity ... ~1,600 tests, most read the database), the root tests that read
# Postgres, dbt build/test, the Playwright e2e (they need the fixture API and its database).
# Adding a test: put its file in ROOT_GATE / API_GATE below only if it runs without a database (the skip rule shows
# at once if it does not).
set -uo pipefail
cd "$(dirname "$0")/.."
WHAT="${1:-all}"
case "$WHAT" in all|python|web) ;; *) echo "gate.sh: python | web | all" >&2; exit 64 ;; esac

ROOT_GATE=(
  tests/test_trades.py tests/test_trades_ii1.py tests/test_roster_value.py
  tests/test_lineup.py tests/test_lineup_ic2.py tests/test_lineup_ii0.py tests/test_ir3_gate.py
  tests/test_scoring.py tests/test_scoring_spec.py tests/test_scoring_ev.py tests/test_kdef.py tests/test_mfl_il2.py
  tests/test_waivers.py tests/test_waivers_if1.py tests/test_waivers_ig3.py
  tests/test_decisions.py tests/test_cards.py tests/test_projection_freeze.py tests/test_memo.py tests/test_clock.py
  tests/test_ir3_post_deploy.py
)
API_GATE=(tests/test_ir3.py tests/test_is4.py tests/test_it4.py tests/test_build_context.py tests/test_ir0.py)  # test_ir0: PO, 2026-10-08 (the starter rule on the trade verdict; the readiness probe through the pooler)
API_DESELECT="not on_the_database"          # test_ir3's one database test
MIN_RAN=750                                  # 798 ran on 2026-10-08; fewer than this: something is not being collected

NOWHERE='postgresql://gate:none@127.0.0.1:1/none'
export LEAGUE_LAB_DB_URL="$NOWHERE" LEAGUE_LAB_APP_DB_URL="$NOWHERE" LEAGUE_LAB_DB_HOST=127.0.0.1 LEAGUE_LAB_DB_PORT=1
export LEAGUE_LAB_AVAILABILITY=off LEAGUE_LAB_USAGE=off LEAGUE_LAB_NEWS=off LEAGUE_LAB_RATE_LIMIT=off OMP_NUM_THREADS=1
OUT="$(mktemp -d)"; trap 'rm -rf "$OUT"' EXIT
FAILED=()
t_all=$(date +%s)

step() {  # step <name> <command...>: one line per step with its time; a failure is remembered, the rest still runs
  local name="$1"; shift
  local t0; t0=$(date +%s)
  echo "::group::gate: $name" 2>/dev/null || true
  if "$@"; then rc=0; else rc=$?; fi
  echo "::endgroup::" 2>/dev/null || true
  if [ "$rc" = 0 ]; then echo "gate ok   $name ($(( $(date +%s) - t0 )) s)"; else echo "gate FAIL $name (exit $rc, $(( $(date +%s) - t0 )) s)"; FAILED+=("$name"); fi
}

junit_count() {  # junit_count <xml...>: "<ran> <skipped> <failed>" summed over junit files
  python3 - "$@" <<'PY'
import sys, xml.etree.ElementTree as ET
ran = skipped = failed = 0
for p in sys.argv[1:]:
    try:
        root = ET.parse(p).getroot()
    except (OSError, ET.ParseError):
        continue
    for s in root.iter("testsuite"):
        n, sk = int(s.get("tests", 0)), int(s.get("skipped", 0))
        f = int(s.get("failures", 0)) + int(s.get("errors", 0))
        ran += n - sk; skipped += sk; failed += f
print(ran, skipped, failed)
PY
}

no_skips() {  # no_skips <label> <xml>: a skipped test fails the gate (it needed something the gate does not have)
  read -r ran skipped failed < <(junit_count "$2")
  echo "$1: $ran ran, $skipped skipped, $failed failed"
  [ "$skipped" = 0 ] || { echo "a gate test skipped: it needs something the gate does not have (a database?) - move it out of the gate list" >&2; return 1; }
}

if [ "$WHAT" != web ]; then
  step "decision suite (src, no database)" bash -c "uv run pytest -q -p no:cacheprovider ${ROOT_GATE[*]} --junitxml='$OUT/root.xml'"
  no_skips "  root" "$OUT/root.xml" || FAILED+=("root skips")
  step "decision suite (api, no database)" bash -c "cd api && uv run pytest -q -p no:cacheprovider ${API_GATE[*]} -k '$API_DESELECT' --junitxml='$OUT/api.xml'"
  no_skips "  api" "$OUT/api.xml" || FAILED+=("api skips")
  read -r ran _ _ < <(junit_count "$OUT/root.xml" "$OUT/api.xml")
  if [ "$ran" -lt "$MIN_RAN" ]; then echo "gate FAIL only $ran tests ran (at least $MIN_RAN expected)"; FAILED+=("too few tests"); fi
  step "ruff" uv run ruff check src app tests api scripts/post_deploy_check.py
fi
if [ "$WHAT" != python ]; then
  step "web lint + type check (npm run lint)" bash -c "cd web && npm run --silent lint"
  step "web build (npm run build)" bash -c "cd web && npm run --silent build"
fi

echo "gate: $(( $(date +%s) - t_all )) s"
if [ ${#FAILED[@]} -gt 0 ]; then
  echo "GATE FAILED: ${FAILED[*]} - this commit must not be published"
  exit 1
fi
echo "GATE PASSED"
