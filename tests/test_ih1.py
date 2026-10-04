"""Wave I-H (IH-1): scripts/nightly_failure_summary.sh — the `notify` step's summary on a failed nightly.

It names the failing stage (an aborted night's step, else the first failed step, else "before scripts/nightly.sh"
when the pipeline never started), says whether this night published (its own `step sync-hosted: ok`, not an older
sync.log), prints the last 40 log lines with passwords blanked, writes one ::error annotation in CI, and exits 0.
The stale rule's own tests are api/tests/test_ih1.py (league_lab/freshness.py).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "nightly_failure_summary.sh"
START = "=== 2026-10-04 07:37:01 EDT nightly start (code abc, host x) ===\n"


def run(tmp_path: Path, nightly: str | None, sync: str | None = None, ci: bool = True) -> tuple[str, str]:
    logs = tmp_path / "logs"
    logs.mkdir()
    if nightly is not None:
        (logs / "nightly.log").write_text(nightly)
    if sync is not None:
        (logs / "sync.log").write_text(sync)
    summary = tmp_path / "summary.md"
    env = {k: v for k, v in os.environ.items() if k not in ("GITHUB_ACTIONS", "GITHUB_STEP_SUMMARY")}
    env["GITHUB_STEP_SUMMARY"] = str(summary)
    if ci:
        env["GITHUB_ACTIONS"] = "true"
    res = subprocess.run(["bash", str(SCRIPT), str(logs)], capture_output=True, text=True, env=env, timeout=30)
    assert res.returncode == 0, res.stderr
    return summary.read_text(), res.stdout


@pytest.mark.skipif(not SCRIPT.exists(), reason="the script is missing")
def test_a_failed_build_names_the_step_blanks_secrets_and_says_nothing_was_published(tmp_path):
    log = START + ("filler line\n" * 50) + (
        "--- 07:40:05 step dbt-build: FAILED (exit 1) after 9m00s\n"
        "connecting postgresql://league_lab_pipeline:s3cr3t@localhost:5432/league_lab\n"
        "LEAGUE_LAB_HOSTED_APP_PASSWORD=hunter2\n"
        "=== 2026-10-04 07:50:00 nightly FAILED: dbt-build (see the step lines above; logs/nightly.log) ===\n")
    out, stdout = run(tmp_path, log, sync="verified: all 79 relations (an older night)\n")
    assert out.startswith("### ⚠️ The nightly failed: dbt-build\n")
    assert "failed step(s): `dbt-build`" in out
    assert "**Published to the hosted copy**: no" in out          # no sync-hosted ok tonight: an old sync.log is ignored
    assert "s3cr3t" not in out and "hunter2" not in out and "league_lab_pipeline:***@localhost" in out
    block = out.split("```")[1].strip().splitlines()
    assert len(block) == 40 and block[-1].startswith("=== 2026-10-04 07:50:00 nightly FAILED")
    assert stdout.startswith("::error title=nightly failed at dbt-build::")


def test_an_aborted_night_names_its_step_and_only_tonights_lines_count(tmp_path):
    log = ("=== 2026-10-03 07:37:01 EDT nightly start (code abc, host x) ===\n"
           "--- 07:40:05 step project: FAILED (exit 1) after 1m00s\n"
           + START + "--- 07:38:05 step restore-state: FAILED (exit 2) after 0m10s\n"
           "=== 2026-10-04 07:38:06 nightly ABORTED (exit 2) during: restore-state ===\n")
    out, _ = run(tmp_path, log)
    assert "The nightly failed: restore-state" in out and "stopped during `restore-state` (exit 2)" in out
    assert "`project`" not in out.split("<details>")[0]


def test_a_night_that_published_says_so(tmp_path):
    log = START + ("--- 07:38:05 step fetch-sleeper: FAILED (exit 1) after 0m10s\n"
                   "--- 08:00:05 step sync-hosted: ok in 0m18s\n")
    out, _ = run(tmp_path, log, sync="verified: all 79 relations the readers name are on the hosted copy\n")
    assert "The nightly failed: fetch-sleeper" in out
    assert "**Published to the hosted copy**: yes — verified: all 79 relations" in out


def test_a_run_that_never_reached_the_pipeline(tmp_path):
    out, stdout = run(tmp_path, None, ci=False)
    assert "The nightly failed: before scripts/nightly.sh" in out and "Roles, database and .env" in out
    assert "<details>" not in out and stdout == ""                 # no log to quote; no annotation outside CI
