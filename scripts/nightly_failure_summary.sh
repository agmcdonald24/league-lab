#!/usr/bin/env bash
# The nightly failed: say where, whether the hosted copy was published, and the last 40 log lines (Wave I-H, IH-1).
#
# Written for the `notify` step of .github/workflows/nightly.yml (`if: failure()`, proposed in docs/HOSTING.md § 5
# "When the nightly is late or fails"): GitHub's own failure email ("Run failed: nightly - main (<sha>)", from
# notifications@github.com to the run's actor — Andrew, whose token the trigger dispatches with) links to the run; this
# puts the answer at the top of that run's summary page and as one annotation. No secret, no outside call.
#
#   scripts/nightly_failure_summary.sh [logs dir]      (default: logs; writes to $GITHUB_STEP_SUMMARY, else stdout)
#
# Reads logs/nightly.log (scripts/nightly.sh's own log: "step <name>: FAILED (exit N)", "nightly ABORTED (exit N)
# during: <step>", "nightly FAILED: <steps>", "step sync-hosted: ok" = published) and logs/sync.log (the "verified: all N
# … relations" line, quoted). Anything
# that looks like a password or a connection string with one is blanked before it is printed. Always exits 0: a
# summary must never turn into a second failure.
set -uo pipefail
LOGS="${1:-logs}"
NIGHTLY="$LOGS/nightly.log"
SYNC="$LOGS/sync.log"
OUT="${GITHUB_STEP_SUMMARY:-/dev/stdout}"

redact() {  # postgres://user:secret@host → postgres://user:***@host; PASSWORD=x / password: x → ***
  sed -E -e 's#(postgres(ql)?://[^:/@[:space:]]+:)[^@[:space:]]+@#\1***@#g' \
         -e 's#((PASSWORD|PASSWD|SECRET|TOKEN|password|secret|token)[A-Za-z_]*[=:][[:space:]]*)[^[:space:]]+#\1***#g'
}

stage="" detail="" published="" run_started=1
if [ ! -s "$NIGHTLY" ]; then
  run_started=0
  stage="before scripts/nightly.sh"
  detail="the run failed before the pipeline started: open the job and find the step marked ✗ (Python environment, the PostgreSQL client, the raw archive, or \"Roles, database and .env\" — a missing or malformed secret, named in its annotation)"
else
  # the last night in the file (a local log may hold several): from its last "nightly start" line on
  start_line="$(grep -n '=== .* nightly start' "$NIGHTLY" | tail -1 | cut -d: -f1)"
  night="$(tail -n +"${start_line:-1}" "$NIGHTLY")"
  aborted="$(printf '%s\n' "$night" | grep -E 'nightly ABORTED \(exit [0-9]+\) during: ' | tail -1)"
  failed_steps="$(printf '%s\n' "$night" | grep -E 'step [A-Za-z0-9_-]+: FAILED' | sed -E 's/.*step ([A-Za-z0-9_-]+): FAILED.*/\1/' | awk '!seen[$0]++' | paste -sd ' ' -)"
  if [ -n "$aborted" ]; then
    stage="$(printf '%s' "$aborted" | sed -E 's/.*during: ([^ =]+).*/\1/')"
    detail="the pipeline stopped during \`$stage\` ($(printf '%s' "$aborted" | sed -E 's/.*(exit [0-9]+).*/\1/'))"
  elif [ -n "$failed_steps" ]; then
    stage="${failed_steps%% *}"
    detail="failed step(s): \`$(printf '%s' "$failed_steps" | sed 's/ /`, `/g')\` (the summary table above says which stopped the night and which it carried on past)"
  else
    stage="unknown"
    detail="no failed step in logs/nightly.log: a step after the pipeline failed (the archive cache, the artifact upload) — open the job"
  fi
fi
# published = this night's sync-hosted step went through (a local logs/sync.log may hold an older night's line)
if [ "$run_started" = 1 ] && printf '%s\n' "$night" | grep -qE 'step sync-hosted: ok'; then
  published="yes"
  [ -s "$SYNC" ] && grep -q '^verified: all' "$SYNC" && published="yes — $(grep -h '^verified: all' "$SYNC" | tail -1 | redact)"
else
  published="no — the hosted copy keeps the previous night's data; the app says \"Yesterday's numbers: the morning update did not run\" once it is 30 hours old"
fi

{
  echo "### ⚠️ The nightly failed: ${stage}"
  echo
  echo "* **Where**: ${detail}."
  echo "* **Published to the hosted copy**: ${published}."
  echo "* **What next**: docs/HOSTING.md § 5 \"Reading a failed run\" (the table: each step, what it means, what to do). Re-run: the run page's **Re-run jobs**, or Actions → nightly → Run workflow."
  if [ "$run_started" = 1 ]; then
    echo
    echo "<details><summary>The last 40 lines of logs/nightly.log</summary>"
    echo
    echo '```'
    tail -n 40 "$NIGHTLY" | redact
    echo '```'
    echo
    echo "</details>"
  fi
} >> "$OUT"

if [ "${GITHUB_ACTIONS:-}" = "true" ]; then
  echo "::error title=nightly failed at ${stage}::${detail//$'\n'/ }; published: ${published%% —*}. The run's summary has the last 40 log lines."
fi
exit 0
