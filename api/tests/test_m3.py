"""Wave I-D (M3): the request side's projected what-if prices like every projected line (``scoring.price_projected``).

Flag off (the default) the on-demand larger-role what-if is the number ``compute_points`` gave, to the bit; flag on, a
Sleeper league with yardage / long-TD bonuses prices them in expectation, as its My Week and the nightly do. No database.
"""

from __future__ import annotations

import json
from pathlib import Path

from league_lab import anyleague as A
from league_lab.scoring import compute_points

from league_lab_api import decisions as DC

FX = Path(__file__).with_name("fixtures") / "sleeper"
DYNASTY, SCRUBS = "1321941740235550720", "1389709692405551104"
BASE = {"targets": 9.1, "receptions": 6.4, "receiving_yards": 96.3, "receiving_tds": 0.62, "carries": 0.3,
        "rushing_yards": 1.9, "rushing_tds": 0.01, "attempts": 0.0, "passing_yards": 0.0, "passing_tds": 0.0,
        "passing_interceptions": 0.0, "fumbles_lost_total": 0.07}
LARGER = {**BASE, "targets": 11.0, "receptions": 7.7, "receiving_yards": 118.2, "receiving_tds": 0.78}


def _scoring(league_id: str):
    return A.league_scoring(json.loads((FX / f"league_{league_id}.json").read_text()))[0]


def _row():
    return {"position": "WR", "base_line": json.dumps(BASE), "larger_line": LARGER, "week": 5, "kind": "target_share",
            "change_text": None, "cause_text": None, "since_week": 3, "games_held": 2}


def test_what_if_equals_compute_points_with_the_flag_off(monkeypatch):
    monkeypatch.setenv("LEAGUE_LAB_EV_PRICING", "0")
    for lid in (DYNASTY, SCRUBS):
        sc = _scoring(lid)
        out = DC._scenario_on_demand(_row(), sc, "League", 5)
        assert out["base_value"] == round(compute_points({**BASE, "position": "WR"}, sc), 2)
        assert out["scenario_value"] == round(compute_points({**LARGER, "position": "WR"}, sc), 2)


def test_what_if_follows_the_flag(monkeypatch):
    monkeypatch.setenv("LEAGUE_LAB_EV_PRICING", "0")
    dyn_off = DC._scenario_on_demand(_row(), _scoring(DYNASTY), "League", 5)
    scr_off = DC._scenario_on_demand(_row(), _scoring(SCRUBS), "League", 5)
    monkeypatch.setenv("LEAGUE_LAB_EV_PRICING", "1")
    dyn_on = DC._scenario_on_demand(_row(), _scoring(DYNASTY), "League", 5)
    scr_on = DC._scenario_on_demand(_row(), _scoring(SCRUBS), "League", 5)
    assert scr_on["base_value"] == scr_off["base_value"] and scr_on["scenario_value"] == scr_off["scenario_value"]
    # 96 yards: all or nothing paid no 100-yard bonus, the expectation pays part of it (and the 40+ TD share)
    assert dyn_on["base_value"] > dyn_off["base_value"]
    # 118 yards: all or nothing paid the full +3, the expectation less than that
    assert dyn_on["scenario_value"] < dyn_off["scenario_value"]
