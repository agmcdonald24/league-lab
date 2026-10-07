"""IQ-1 (hotfix): v3.5 -- the weeks after the market week (calibration fi1.0, docs/METRICS.md § "v3.5: rest-of-season
quarterbacks (IQ-1)"). Hand-built season frames, no database.

* the market week is the first week after the newest played one;
* (a) a later week without a line gets the team's own season mean, shrunk toward the league's by 3 games; the spread
  follows in the home team's view; a week with a line and every played week are untouched; ``implied_imputed`` marks it;
* (d) a later week's personnel inputs are the player's market-week row's;
* the switch off (``0``) gives the frame as it was (plus the marker, all False); unset = on; ``MODEL_VERSION`` v3.5;
* pt1.0 ignores an imputed line.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from league_lab import calibration as C
from league_lab import projections as P

PN = {"pn_qb_starting": 1.0, "pn_qb_changed": 0.0, "pn_qb_games_together": 3.0, "pn_qb_prev_ppg_diff": 0.0,
      "pn_qb_is_rookie_or_backup": 0.0}


def frame() -> pd.DataFrame:
    """BUF (lines 28, 30 in weeks 1-2, played), MIA (20, 22), week 3 the market week (lines posted), weeks 4-5 later."""
    rows = []
    lines = {("BUF", 1): (28.0, 50.0), ("BUF", 2): (30.0, 52.0), ("MIA", 1): (20.0, 44.0), ("MIA", 2): (22.0, 46.0),
             ("BUF", 3): (27.0, 49.0), ("MIA", 3): (19.0, 43.0)}
    for team, qb in (("BUF", "allen"), ("MIA", "willis")):
        for wk in (1, 2, 3, 4, 5):
            imp, tot = lines.get((team, wk), (np.nan, np.nan))
            pn = dict(PN) if wk <= 3 else {**PN, "pn_qb_starting": 0.0}       # the last_start fallback said "not him"
            rows.append({"gsis_id": qb, "season": 2026, "week": float(wk), "position": "QB", "team": team,
                         "played": wk <= 2, "f_home": float(wk % 2), "implied_team_total": imp, "total_line": tot,
                         "spread_line": np.nan if np.isnan(imp) else 0.0, **pn})
    return pd.DataFrame(rows)


def test_market_week_and_the_line(monkeypatch):
    monkeypatch.delenv(C.FUTURE_INPUTS_FLAG, raising=False)
    f = frame()
    assert C.market_week(f) == 3
    out = C.future_inputs(f).set_index(["gsis_id", "week"])
    # BUF: 2 games, mean 29 / 51; league = mean of the teams' means (25 / 48); shrink 3 games -> (2*29 + 3*25) / 5
    imp, tot = (2 * 29 + 3 * 25) / 5, (2 * 51 + 3 * 48) / 5
    assert out.loc[("allen", 4.0), "implied_team_total"] == pytest.approx(imp)
    assert out.loc[("allen", 4.0), "total_line"] == pytest.approx(tot)
    assert out.loc[("allen", 4.0), "spread_line"] == pytest.approx(tot - 2 * imp)     # week 4 away: the home side's view
    assert out.loc[("allen", 5.0), "spread_line"] == pytest.approx(2 * imp - tot)     # week 5 at home
    assert bool(out.loc[("allen", 4.0), "implied_imputed"])
    for wk in (1.0, 2.0, 3.0):                                                        # played weeks and the market week
        for c in ("implied_team_total", "total_line", "spread_line", "pn_qb_starting"):
            x, y = out.loc[("allen", wk), c], f.set_index(["gsis_id", "week"]).loc[("allen", wk), c]
            assert (np.isnan(x) and np.isnan(y)) or x == y
        assert not bool(out.loc[("allen", wk), "implied_imputed"])
    assert out.loc[("willis", 5.0), "implied_team_total"] == pytest.approx((2 * 21 + 3 * 25) / 5)
    assert C.LAST_FUTURE_INPUTS["market_week"] == 3 and C.LAST_FUTURE_INPUTS["lines_imputed"] == 4


def test_the_spread_is_the_home_teams_view(monkeypatch):
    monkeypatch.delenv(C.FUTURE_INPUTS_FLAG, raising=False)
    out = C.future_inputs(frame()).set_index(["gsis_id", "week"])
    for wk in (4.0, 5.0):
        r = out.loc[("allen", wk)]
        own = (r["total_line"] + r["spread_line"]) / 2 if r["f_home"] > 0 else (r["total_line"] - r["spread_line"]) / 2
        assert own == pytest.approx(r["implied_team_total"])        # the frame's rule: home implied = (total + spread) / 2


def test_the_market_weeks_personnel_carries(monkeypatch):
    monkeypatch.delenv(C.FUTURE_INPUTS_FLAG, raising=False)
    out = C.future_inputs(frame()).set_index(["gsis_id", "week"])
    assert out.loc[("allen", 4.0), "pn_qb_starting"] == 1.0 and out.loc[("willis", 5.0), "pn_qb_starting"] == 1.0
    assert C.LAST_FUTURE_INPUTS["personnel_moved"] == 4


def test_the_switch(monkeypatch):
    f = frame()
    monkeypatch.setenv(C.FUTURE_INPUTS_FLAG, "0")
    out = C.future_inputs(f)
    assert not out["implied_imputed"].any()
    pd.testing.assert_frame_equal(out.drop(columns="implied_imputed"), f)
    for v, on in (("", True), ("0", False), ("1", True)):
        monkeypatch.setenv(C.FUTURE_INPUTS_FLAG, v)
        assert C.future_inputs_enabled() is on
    monkeypatch.delenv(C.FUTURE_INPUTS_FLAG)
    assert C.future_inputs_enabled() is C.FUTURE_INPUTS_DEFAULT is True
    assert P.MODEL_VERSION == "v3.5"


def test_a_market_week_without_a_line_gets_one_and_nothing_played_moves(monkeypatch):
    monkeypatch.delenv(C.FUTURE_INPUTS_FLAG, raising=False)
    f = frame()
    f.loc[f["week"] == 3, ["implied_team_total", "total_line", "spread_line"]] = np.nan      # the books have not posted
    out = C.future_inputs(f).set_index(["gsis_id", "week"])
    assert bool(out.loc[("allen", 3.0), "implied_imputed"]) and out.loc[("allen", 3.0), "pn_qb_starting"] == 1.0
    assert out.loc[("allen", 1.0), "implied_team_total"] == 28.0


def test_pt10_skips_an_imputed_line(monkeypatch):
    """pass_td_lines reads the target's implied total only where it is the books' (a v3.5 later week keeps the model's)."""
    import tests.test_ip1_pass_td as T  # noqa: PLC0415 - the pt1.0 fixture's stand-ins

    monkeypatch.delenv("LEAGUE_LAB_EV_PRICING", raising=False)
    monkeypatch.setattr(P, "predict_position", T._fake_predict)
    monkeypatch.setenv(C.PASS_TD_FLAG, "1")
    monkeypatch.setattr(C, "pass_td_fit_rows", lambda train, season: T._fit_rows())
    target = T._target().assign(implied_imputed=False)
    target.loc[(target["gsis_id"] == "star") & (target["week"] == 5), "implied_imputed"] = True
    every = pd.concat([T._fake_predict(None, target[target["position"] == pos], T.LEAGUES) for pos in ("QB", "WR")],
                      ignore_index=True)
    every["model_version"], every["fitted_at"], every["train_seasons"] = P.MODEL_VERSION, pd.Timestamp("2026-10-07", tz="UTC"), "2016-2025"
    out = C.pass_td_lines(2026, every, {"QB": None, "WR": None}, target, pd.DataFrame(), T.LEAGUES)
    a = every[(every["gsis_id"] == "star") & (every["week"] == 5)]["proj_passing_tds"].iloc[0]
    b = out[(out["gsis_id"] == "star") & (out["week"] == 5)]["proj_passing_tds"].iloc[0]
    assert a == b                                                    # imputed: the model's count
    assert C.LAST_PASS_TD["moved"] == 1                              # the backup's real line still moves
