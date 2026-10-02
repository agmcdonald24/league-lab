"""Wave H (H2): the nightly's record tables, the hosted relation closure, the one-writer rule. No database needed.

* `scripts/nightly.sh`: every record table is a state table (restore_state walks STATE_TABLES and treats the record
  ones harder), and the NFL-wide boards the API prices every league from are record tables.
* `scripts/hosted_relations.py` (what `scripts/sync_to_hosted.sh` publishes): the API's readers include the
  src/league_lab modules it imports, and the names include what the routes read — qualified, through
  `anyleague.NFL_WIDE`, or bare in `missing_relations((...))`.
* `scripts/sync_to_hosted.sh` refuses to publish off GitHub Actions unless told this machine is the writer.
"""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NIGHTLY = (ROOT / "scripts" / "nightly.sh").read_text()
SYNC = (ROOT / "scripts" / "sync_to_hosted.sh").read_text()
NFL_WIDE_TABLES = {"ops.projection_lines", "ops.projection_ranges", "ops.kd_lines", "ops.kd_ranges"}


def _shell_list(text: str, name: str) -> list[str]:
    return re.search(rf'^{name}="([^"]*)"', text, re.M).group(1).split()


def _hosted_relations():
    spec = importlib.util.spec_from_file_location("hosted_relations", ROOT / "scripts" / "hosted_relations.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_record_tables_are_state_tables_and_hold_the_nfl_wide_boards():
    state, record = _shell_list(NIGHTLY, "STATE_TABLES"), _shell_list(NIGHTLY, "RECORD_TABLES")
    assert set(record) <= set(state)
    assert {"ops.projections", "ops.projection_drift"} | NFL_WIDE_TABLES <= set(record)


def test_the_api_readers_follow_its_imports():
    files = {str(p.relative_to(ROOT)) for p in _hosted_relations().readers()["api"]}
    for mod in ("anyleague", "research", "decisions", "sleeper_client", "waivers", "trades", "lineup", "kdef",
                "scoring", "roster_value"):
        assert f"src/league_lab/{mod}.py" in files, mod
    assert {"api/league_lab_api/decisions.py", "api/league_lab_api/research.py", "app/lib/cards.py",
            "app/pages/2_Waiver_Wire.py", "app/pages/6_Trade_Finder.py"} <= files
    # the model fit is not followed: its input tables are not the readers' (its outputs reach them through ops)
    assert "src/league_lab/projections.py" not in files


def test_every_relation_a_route_reads_is_named():
    hr = _hosted_relations()
    api = hr.relations()["api"]
    # qualified in the API's own files
    direct = {f"{s}.{n}" for p in (ROOT / "api" / "league_lab_api").glob("*.py")
              for s, n in hr.QUALIFIED.findall(p.read_text()) if s in ("analytics", "ops", "analytics_seeds")}
    assert direct <= api
    # through anyleague.NFL_WIDE (F1's tables) and the seed of reference scorings
    assert NFL_WIDE_TABLES | {"analytics_seeds.reference_scorings"} <= api
    # what the routes read, qualified or bare in a missing_relations((...)) guard
    assert {"analytics.mart_projection_record", "analytics.mart_player_scenarios",
            "analytics.mart_player_ros_projection", "analytics.fct_player_game_league"} <= api


def test_ops_left_out_of_the_hosted_copy_is_read_by_no_one():
    excluded = set(_shell_list(SYNC, "OPS_EXCLUDE"))
    assert excluded == {"ops.player_prior_oof", "ops.player_prior_oof_pred"}
    named = set().union(*_hosted_relations().relations().values())
    assert not excluded & named


@pytest.mark.parametrize("writer", ["", "0"])
def test_sync_refuses_off_actions_unless_this_machine_is_the_writer(writer):
    env = {**os.environ, "GITHUB_ACTIONS": "", "LEAGUE_LAB_MAC_WRITES_HOSTED": writer,
           "LEAGUE_LAB_HOSTED_ADMIN_URL": "postgresql://owner:pw@ep-example.invalid:5432/neondb?sslmode=require",
           "LEAGUE_LAB_HOSTED_APP_PASSWORD": "x", "LEAGUE_LAB_HOSTED_ALLOW_LOCAL": ""}
    run = subprocess.run(["bash", "scripts/sync_to_hosted.sh"], cwd=ROOT, env=env, capture_output=True, text=True,
                         timeout=120)
    assert run.returncode == 7, run.stdout + run.stderr
    assert "one writer" in run.stdout + run.stderr and "Nothing was touched" in run.stdout + run.stderr
