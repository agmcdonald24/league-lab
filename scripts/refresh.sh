#!/usr/bin/env bash
# Daily refresh on the Mac: the launchd job (scripts/launchd/com.leaguelab.refresh.plist, 08:00)
# and `make refresh` run this. It is the nightly pipeline GitHub Actions runs,
# scripts/nightly.sh (lock, .env, every step, logs/nightly.log), plus a local backup.
# Safe to run by hand any time ("manual refresh is a first-class operation", plan §7).
#
#   scripts/refresh.sh          replay the archive, fetch Sleeper + the current NFL season, dbt build,
#                               project, back up, publish to the hosted copy when configured
#   scripts/refresh.sh --full   also re-check every historical NFL season live (monthly audit)
#
# If GitHub Actions publishes the hosted copy (docs/HOSTING.md § Nightly on GitHub Actions), take
# LEAGUE_LAB_HOSTED_ADMIN_URL out of the Mac's .env or unload the launchd job: one writer.
set -euo pipefail
export NIGHTLY_BACKUP="${NIGHTLY_BACKUP:-1}"
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/nightly.sh" "$@"
