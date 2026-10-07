"""IL-3 (Wave I-L): v3.3 — the mean-unbiased new-team scale at WR (calibration nt1.0, docs/METRICS.md § "v3.3").

* ``new_team_scale``: k = sum(actual) / sum(projected) over the new-team rows (both scorings pooled), clipped to
  0.70–1.10; no scale under 30 rows.
* In ``blend_lines``: a veteran WR on a new team (< 3 games with his team in the current stint) gets every component
  of his line × k, priced and ranged by the same models; a WR long with his team, a new-team RB and a cold start are
  not scaled by it; ``LEAGUE_LAB_NEW_TEAM_SCALE=0`` turns only this part off; ``LEAGUE_LAB_COLD_START=0`` turns all off.

No database: M6's stand-ins (``tests/test_m6.py``) for the history queries, ``ops.calibration_oof`` and
``predict_position``."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from league_lab import calibration as C
from league_lab import projections as P

from .test_m6 import COMPS, FIT, LEAGUES, _fake_predict, _FakeConn

BASE = {"targets": 6.0, "receptions": 4.0, "receiving_yards": 55.0, "receiving_tds": 0.3, "carries": 0.2,
        "rushing_yards": 1.0, "rushing_tds": 0.0, "fumbles_lost_total": 0.05}


def test_the_scale_is_sum_actual_over_sum_projected_pooled_and_clipped():
    f = pd.DataFrame({"position": "WR", "new_team": True, "proj_points": [10.0] * 20 + [5.0] * 20,
                      "actual": [8.0] * 20 + [5.0] * 20, "league_id": ["L1"] * 20 + ["L2"] * 20})
    assert C.new_team_scale(f, "WR") == (pytest.approx((160 + 100) / (200 + 100)), 40)
    low = f.assign(actual=1.0)
    assert C.new_team_scale(low, "WR") == (0.70, 40)                       # clipped at the floor
    assert C.new_team_scale(f.iloc[:29], "WR") == (1.0, 29)                # under 30 rows: no scale
    ignored = pd.concat([f, f.assign(new_team=False, actual=100.0), f.assign(actual=np.nan, proj_points=1.0),
                         f.assign(proj_points=0.4, actual=100.0), f.assign(position="RB", actual=100.0)])
    assert C.new_team_scale(ignored, "WR") == C.new_team_scale(f, "WR")    # flag, played, priced >= 0.5, position


def _target() -> pd.DataFrame:
    """Week 5 of 2026: a veteran WR traded after week 3 (1 game with his new team), a WR with his team all along, a
    veteran RB on a new team, a rookie WR (cold start)."""
    rows = []
    for gid, pos, team in (("moved", "WR", "NEW"), ("stayed", "WR", "OLD"), ("rbmoved", "RB", "NEW"), ("rook", "WR", "AAA")):
        r = {"gsis_id": gid, "season": 2026, "week": 5, "position": pos, "team": team}
        r |= {f"m_{c}": BASE.get(c, 0.0) for c in P.ALL_COMPONENTS}
        rows.append(r)
    return pd.DataFrame(rows)


def _history():
    games = ([("moved", 2025, w, "OLD") for w in range(1, 18)] + [("moved", 2026, w, "OLD") for w in (1, 2, 3)]
             + [("moved", 2026, 4, "NEW")]
             + [("stayed", 2025, w, "OLD") for w in range(1, 18)] + [("stayed", 2026, w, "OLD") for w in (1, 2, 3, 4)]
             + [("rbmoved", 2025, w, "OLD") for w in range(1, 18)]
             + [(f"v{s}_{i}", s, w, "XXX") for s in (2023, 2024, 2025) for i in range(20) for w in (1, 2, 3, 4)]
             + [(f"v{s}_{i}", s, 5, "YYY") for s in (2023, 2024, 2025) for i in range(20)])
    draft = [("moved", 40, 2019), ("stayed", 41, 2019), ("rbmoved", 42, 2019), ("rook", 8, 2026)] + [
        (f"v{s}_{i}", 50, 2018) for s in (2023, 2024, 2025) for i in range(20)]
    return games, draft


def _oof() -> pd.DataFrame:
    """2023–2025: 20 veteran WRs a season, traded after week 4, in week 5 (their first game with the new team)
    projected 10 (L1) / 14 (L2) and scoring 8 / 11.2 — the scale is 0.8 in both scorings."""
    fit = []
    for s in (2023, 2024, 2025):
        for i in range(20):
            for lid, (p, a) in {"L1": (10.0, 8.0), "L2": (14.0, 11.2)}.items():
                fit.append({"gsis_id": f"v{s}_{i}", "season": s, "week": 5, "position": "WR", "league_id": lid,
                            "proj_points": p, "actual": a})
    return pd.DataFrame(fit)


@pytest.fixture
def run(monkeypatch):
    monkeypatch.delenv("LEAGUE_LAB_EV_PRICING", raising=False)
    monkeypatch.setattr(C, "load_oof", lambda conn, season: _oof())
    monkeypatch.setattr(C, "anchor_league", lambda oof, leagues: "L1")
    monkeypatch.setattr(P, "predict_position", _fake_predict)
    games, draft = _history()
    conn = _FakeConn(games, draft)
    target = _target()

    def go(cold: str | None = None, nt: str | None = None):
        for flag, v in ((C.COLD_START_FLAG, cold), (C.NEW_TEAM_SCALE_FLAG, nt)):
            if v is None:
                monkeypatch.delenv(flag, raising=False)
            else:
                monkeypatch.setenv(flag, v)
        every = pd.concat([_fake_predict(None, target[target["position"] == pos], FIT) for pos in ("RB", "WR")],
                          ignore_index=True)
        every["model_version"], every["fitted_at"], every["train_seasons"] = P.MODEL_VERSION, pd.Timestamp("2026-10-05", tz="UTC"), "2016-2025"
        return every, C.blend_lines(conn, 2026, every, {"WR": None, "RB": None}, target, FIT, LEAGUES)
    return go


def _row(df, gid, lid="L1"):
    return df[(df["gsis_id"] == gid) & (df["league_id"] == lid)].iloc[0]


def test_a_veteran_wr_on_a_new_team_is_scaled_by_k(run):
    every, out = run()
    assert C.LAST_NEW_TEAM_SCALE["WR"] == (pytest.approx(0.8), 120)            # 60 rows x 2 scorings, both at 0.8
    a, b = _row(every, "moved"), _row(out, "moved")
    assert all(b[c] == pytest.approx(a[c] * 0.8, rel=1e-12) for c in COMPS)   # every component of the line
    assert b["proj_points"] == pytest.approx(a["proj_points"] * 0.8, abs=0.011)
    plan = C.LAST_LINE_BLEND.set_index("gsis_id")
    assert plan.loc["moved", "kind"] == "new_team" and plan.loc["moved", "games"] == 1.0
    assert plan.loc["moved", "k"] == pytest.approx(0.8)


def test_who_is_not_scaled(run):
    every, out = run()
    for gid in ("stayed", "rbmoved"):          # 4 games with his team; a new-team RB (WR only)
        for lid in ("L1", "L2"):
            assert [_row(out, gid, lid)[c] for c in [*COMPS, "proj_points"]] == [_row(every, gid, lid)[c] for c in [*COMPS, "proj_points"]]
    plan = C.LAST_LINE_BLEND.set_index("gsis_id")
    assert "rook" not in plan.index or plan.loc["rook", "kind"] == "cold"     # a cold start is the cold blend's, never both


def test_the_switches(run):
    every, out = run(nt="0")                                                  # only the new-team part off
    assert _row(out, "moved")["proj_points"] == _row(every, "moved")["proj_points"]
    assert C.LAST_NEW_TEAM_SCALE == {}
    every, out = run(cold="0")                                                # the whole blend off: v3.0's lines
    assert out is every
    every, out = run(nt="1")
    assert _row(out, "moved")["proj_points"] != _row(every, "moved")["proj_points"]


def test_the_version():
    assert P.MODEL_VERSION == "v3.4"          # ---- IP-1: v3.4 = v3.3 + pt1.0 (QB passing TDs); nt1.0 unchanged
    assert C.NEW_TEAM_SCALE_POSITIONS == ("WR",) and C.NEW_TEAM_SCALE_BOUNDS == (0.70, 1.10)
    assert C.NEW_TEAM_POSITIONS == ()                                         # M6's cold blend keyed on team games: still dropped


def test_the_flag_looks_ahead_one_game_a_week():
    """A WR with 1 game for his new team now (2026, played through week 4): flagged for weeks 5 and 6 (his 2nd and 3rd
    games with the team), not from week 7 (he will have 3 by then); a past week keeps the games actually played; a
    bye (no row) does not count as a game."""
    games = pd.DataFrame([("moved", 2025, w, "OLD") for w in range(1, 18)] + [("moved", 2026, w, "OLD") for w in (1, 2, 3)]
                         + [("moved", 2026, 4, "NEW")], columns=["gsis_id", "season", "week", "team"])
    rows = pd.DataFrame({"gsis_id": "moved", "season": 2026, "week": [4, 5, 7, 8, 9], "team": ["NEW"] * 5,
                         "position": "WR"})                       # week 6: his bye (no row)
    rows = rows.assign(team_games_before=C.team_games_before(rows, games), career_games_before=20.0, cold=False)
    assert rows["team_games_before"].tolist() == [0.0, 1.0, 1.0, 1.0, 1.0]
    assert C.new_team_ahead(rows, games).tolist() == [True, True, True, False, False]   # wk 4 (0), 5 (1), 7 (2), 8 (3)
