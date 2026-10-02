#!/usr/bin/env bash
# Daily refresh on the Mac: the launchd job (scripts/launchd/com.leaguelab.refresh.plist, 08:00)
# and `make refresh` run this. It is the nightly pipeline GitHub Actions runs,
# scripts/nightly.sh (lock, .env, every step, logs/nightly.log), plus a local backup.
# Safe to run by hand any time ("manual refresh is a first-class operation", plan §7).
#
#   scripts/refresh.sh          replay the archive, fetch Sleeper + the current NFL season, dbt build,
#                               project, back up — the Mac's own database (the research console, `make app`)
#   scripts/refresh.sh --full   also re-check every historical NFL season live (monthly audit)
#
# One writer (Wave H): GitHub Actions is the only writer of the hosted copy, so this job does NOT publish to it
# (nightly.sh skips sync-hosted off Actions). It still READS the hosted copy when the Mac's .env has
# LEAGUE_LAB_HOSTED_ADMIN_URL (restore-state: a table this database lost comes back from there).
# To make the Mac publish again (Actions down for days): add LEAGUE_LAB_MAC_WRITES_HOSTED=1 to the Mac's .env AND
# disable the Actions workflow (Actions → nightly → ⋯ → Disable workflow) — never both; remove the line to stop.
# docs/HOSTING.md § 5 "The Mac's launchd job".
set -euo pipefail
export NIGHTLY_BACKUP="${NIGHTLY_BACKUP:-1}"
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/nightly.sh" "$@"
