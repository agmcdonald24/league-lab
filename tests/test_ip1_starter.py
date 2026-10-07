"""Wave I-P (IP-1 fix round): st1.1's evaluation -- who started, judged on identification accuracy
(scripts/analysis/ip1_starter_rule.py; docs/METRICS.md § "st1.1"). Hand-built team-weeks, no database.

* the truth is the team's dropback leader; a listing whose QB took no dropback is stale, one whose QB took some and
  lost the lead is an in-game change (never "fixed": no rule before kickoff can see it);
* fixed / still wrong / newly broken, and the rule's two ratios;
* the screen's alternative ("starter unclear") flags a team whose listed QB took no dropback in its newest played game
  while another led, read only from the games before the week.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "analysis"))
import ip1_starter_rule as R  # noqa: E402


def team_weeks(rows):
    """(season, week, team, listed, pick, played) -> int_pn_team_game's columns (game id = season_week_team)."""
    return pd.DataFrame([{"season": s, "week": w, "game_id": f"{s}_{w:02d}_{t}", "team": t, "listed_qb_id": lst,
                          "starting_qb_id": pick, "is_played": played} for s, w, t, lst, pick, played in rows])


def dropbacks(rows):
    """(season, week, team, qb, dropbacks)."""
    return pd.DataFrame([{"game_id": f"{s}_{w:02d}_{t}", "team": t, "gsis_id": q, "dropbacks": n} for s, w, t, q, n in rows])


TG = team_weeks([
    (2024, 9, "WAS", "mariota", "mariota", True),      # stale, not picked: still wrong
    (2024, 10, "WAS", "mariota", "daniels", True),     # stale, picked: fixed
    (2024, 9, "IND", "flacco", "richardson", True),    # the listing was right (a benching): newly broken
    (2024, 9, "MIN", "darnold", "darnold", True),      # in-game change: kept
    (2024, 9, "BUF", "allen", "allen", True),          # right and kept: not in the table
])
DB = dropbacks([
    (2024, 9, "WAS", "daniels", 40), (2024, 10, "WAS", "daniels", 38),
    (2024, 9, "IND", "flacco", 35),
    (2024, 9, "MIN", "darnold", 6), (2024, 9, "MIN", "jones", 30),
    (2024, 9, "BUF", "allen", 33),
])


def test_classify_and_the_confusion_table():
    ev = R.classify(TG, DB).set_index("team")
    assert ev.loc["IND", "cls"] == "newly broken" and ev.loc["MIN", "cls"] == "in-game change (kept)"
    wk = ev.reset_index().set_index(["team", "week"])
    assert wk.loc[("WAS", 9), "cls"] == "still wrong" and wk.loc[("WAS", 10), "cls"] == "fixed"
    assert "BUF" not in ev.index
    t = R.confusion(R.classify(TG, DB))
    a = t.loc["all"]
    assert (a["fixed"], a["still wrong"], a["newly broken"], a["in-game change (kept)"], a["stale listings"]) == (1, 1, 1, 1, 2)


def test_the_unclear_flag_reads_the_games_before_only():
    tg = team_weeks([(2026, 3, "SEA", "lock", "lock", True), (2026, 4, "SEA", "lock", "lock", True),
                     (2026, 5, "SEA", "lock", "lock", False), (2026, 4, "BUF", "allen", "allen", True),
                     (2026, 5, "BUF", "allen", "allen", False)])
    db = dropbacks([(2026, 3, "SEA", "darnold", 46), (2026, 4, "SEA", "darnold", 26), (2026, 4, "BUF", "allen", 33)])
    f = R.unclear_flag(tg, db).set_index(["team", "week"])["unclear"]
    assert not f[("SEA", 3)]                    # no game before it this season
    assert f[("SEA", 4)] and f[("SEA", 5)]      # Lock listed, Darnold led the game before
    assert not f[("BUF", 5)]


def test_kd_team_codes():
    assert R.kd(pd.Series(["OAK", "SD", "STL", "SEA"])).tolist() == ["LV", "LAC", "LA", "SEA"]
