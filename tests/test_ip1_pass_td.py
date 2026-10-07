"""Wave I-P (IP-1): v3.4 -- a quarterback's passing TDs regressed toward his team's implied total (calibration pt1.0,
docs/METRICS.md § "The quarterback weak spot (IP-1)").

* ``fit_pass_td`` is least squares without intercept on played rows (unplayed rows and rows without an implied total
  never enter), the identity under ``PASS_TD_MIN_ROWS``.
* ``apply_pass_td``: a x the model + b x the implied total x attempts / 33, at least 0; a week without an implied total
  keeps the model's.
* ``pass_td_lines`` (``project``'s hook) changes only QB lines, only their passing TDs, prices and ranges the new line
  through the frozen-line path, and the house rows equal the request side's price of the NFL-wide line bit for bit, flat
  and at the odds; switch off (or a fit under the minimum) = ``every`` itself.
* The switch defaults to the harness's verdict (on); ``MODEL_VERSION`` is v3.4.

No database: ``pass_td_fit_rows`` is played by a stand-in; ``predict_position`` by test_m6's stand-in (the real
``projections.price``, bands at +-3 / 6).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from league_lab import anyleague as A
from league_lab import calibration as C
from league_lab import projections as P
from league_lab import scoring as S

COMPS = [f"proj_{c}" for c in P.ALL_COMPONENTS]
REF = {"pass_yd": 0.04, "pass_td": 4.0, "pass_int": -1.0, "rush_yd": 0.1, "rush_td": 6.0, "fum_lost": -2.0}
BONUS = {"pass_yd": 0.04, "pass_td": 6.0, "pass_int": -2.0, "rush_yd": 0.1, "rush_td": 6.0, "fum_lost": -2.0,
         "bonus_pass_yd_300": 3.0, "bonus_rush_yd_100": 3.0}
LEAGUES = {"L1": ("Ref league", REF), "L2": ("Bonus league", BONUS)}


def _fake_predict(m, rows, scorings, lines=None):
    out = rows[["gsis_id", "season", "week", "position"]].copy().reset_index(drop=True)
    src = lines.reset_index(drop=True) if lines is not None else rows.reset_index(drop=True).rename(
        columns=lambda c: "proj_" + c[2:] if c.startswith("m_") else c)
    for c in COMPS:
        out[c] = pd.to_numeric(src[c], errors="coerce").fillna(0.0).to_numpy(dtype=float) if c in src else 0.0
    frames = []
    for lid, (_, sc) in scorings.items():
        o = out.copy()
        o["league_id"] = lid
        o["proj_points"] = P.price(o, sc, "proj_")
        o["p10"], o["p25"], o["p50"] = np.clip(o["proj_points"] - 6, 0, None), np.clip(o["proj_points"] - 3, 0, None), o["proj_points"]
        o["p75"], o["p90"] = o["proj_points"] + 3, o["proj_points"] + 6
        frames.append(o)
    return pd.concat(frames, ignore_index=True)


QB_LINE = {"attempts": 33.0, "passing_yards": 290.0, "passing_tds": 1.2, "passing_interceptions": 0.8, "carries": 4.0,
           "rushing_yards": 20.0, "rushing_tds": 0.15, "fumbles_lost_total": 0.2}
WR_LINE = {"targets": 7.0, "receptions": 5.0, "receiving_yards": 70.0, "receiving_tds": 0.4}


def _target() -> pd.DataFrame:
    """Weeks 5 and 6 of 2026: a starter (implied 27 in week 5, no line yet in week 6), a backup (implied 20, 3 attempts),
    a WR (never touched)."""
    rows = []
    for gid, pos, wk, implied, scale in (("star", "QB", 5, 27.0, 1.0), ("star", "QB", 6, np.nan, 1.0),
                                         ("backup", "QB", 5, 20.0, 0.09), ("wr", "WR", 5, 27.0, 1.0)):
        line = QB_LINE if pos == "QB" else WR_LINE
        r = {"gsis_id": gid, "season": 2026, "week": float(wk), "position": pos, "team": "AAA", "implied_team_total": implied}
        r |= {f"m_{c}": line.get(c, 0.0) * scale for c in P.ALL_COMPONENTS}
        rows.append(r)
    return pd.DataFrame(rows)


def _fit_rows(a: float = 0.1, b: float = 0.06, n: int = 600, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    implied = rng.uniform(15, 30, n)
    att = rng.uniform(2, 42, n)
    model = rng.uniform(0, 2.5, n)
    out = a * model + b * implied * att / C.PASS_TD_ATTEMPTS
    return pd.DataFrame({"season": 2025, "played": True, "implied_team_total": implied, "proj_attempts": att,
                         "proj_passing_tds": model, "out_passing_tds": out})


@pytest.fixture
def lines(monkeypatch):
    monkeypatch.delenv("LEAGUE_LAB_EV_PRICING", raising=False)
    monkeypatch.setattr(P, "predict_position", _fake_predict)
    target = _target()

    def run(switch: str | None, fit_rows: pd.DataFrame | None = None):
        if switch is None:
            monkeypatch.delenv(C.PASS_TD_FLAG, raising=False)
        else:
            monkeypatch.setenv(C.PASS_TD_FLAG, switch)
        monkeypatch.setattr(C, "pass_td_fit_rows", lambda train, season: _fit_rows() if fit_rows is None else fit_rows)
        every = pd.concat([_fake_predict(None, target[target["position"] == pos], LEAGUES) for pos in ("QB", "WR")],
                          ignore_index=True)
        every["model_version"], every["fitted_at"], every["train_seasons"] = P.MODEL_VERSION, pd.Timestamp("2026-10-07", tz="UTC"), "2016-2025"
        return every, C.pass_td_lines(2026, every, {"QB": None, "WR": None}, target, pd.DataFrame(), LEAGUES)
    return run


def _row(df, gid, week=5, lid="L1"):
    return df[(df["gsis_id"] == gid) & (df["week"] == week) & (df["league_id"] == lid)].iloc[0]


def test_fit_recovers_the_coefficients_on_played_rows_only():
    rows = _fit_rows(a=0.2, b=0.055)
    noise = pd.DataFrame({"season": 2025, "played": [False] * 50, "implied_team_total": 24.0, "proj_attempts": 30.0,
                          "proj_passing_tds": 1.0, "out_passing_tds": 9.0})          # unplayed: never fitted
    a, b, n = C.fit_pass_td(pd.concat([rows, noise, rows.head(5).assign(implied_team_total=np.nan)], ignore_index=True))
    assert (a, b) == (pytest.approx(0.2), pytest.approx(0.055)) and n == 600
    assert C.fit_pass_td(_fit_rows(n=C.PASS_TD_MIN_ROWS - 1)) == (1.0, 0.0, C.PASS_TD_MIN_ROWS - 1)


def test_apply_blends_where_the_line_is_posted_and_never_goes_below_zero():
    d = pd.DataFrame({"proj_passing_tds": [1.2, 1.2, 0.1], "proj_attempts": [33.0, 33.0, 2.0],
                      "implied_team_total": [27.0, np.nan, 20.0]})
    out = C.apply_pass_td(d, 0.1, 0.06)
    assert out[0] == pytest.approx(0.1 * 1.2 + 0.06 * 27.0)
    assert out[1] == 1.2                                   # no implied total: the model's
    assert (C.apply_pass_td(d, -5.0, 0.0) >= 0).all()


def test_only_qb_passing_tds_move_and_the_range_is_the_new_lines(lines):
    every, out = lines("1")
    assert len(out) == len(every) and set(out.columns) == set(every.columns)
    a, b = _row(every, "star"), _row(out, "star")
    assert b["proj_passing_tds"] == pytest.approx(0.1 * 1.2 + 0.06 * 27.0 * 33.0 / C.PASS_TD_ATTEMPTS)
    assert all(b[c] == a[c] for c in COMPS if c != "proj_passing_tds")
    assert b["proj_points"] - a["proj_points"] == pytest.approx(4.0 * (b["proj_passing_tds"] - a["proj_passing_tds"]))
    assert b["p90"] - b["proj_points"] == pytest.approx(6.0)
    for gid, wk in (("star", 6), ("wr", 5)):              # no posted line yet; not a quarterback
        for lid in LEAGUES:
            x, y = _row(every, gid, wk, lid), _row(out, gid, wk, lid)
            assert [y[c] for c in [*COMPS, "proj_points", "p10", "p90"]] == [x[c] for c in [*COMPS, "proj_points", "p10", "p90"]]
    back = _row(out, "backup")
    assert back["proj_passing_tds"] == pytest.approx(0.1 * 0.108 + 0.06 * 20.0 * 2.97 / C.PASS_TD_ATTEMPTS)
    assert C.LAST_PASS_TD["moved"] == 2 and C.LAST_PASS_TD["rows"] == 600


@pytest.mark.parametrize("mode", ["flat", "ev"])
@pytest.mark.parametrize("switch", ["1", "0"])
def test_the_new_line_prices_to_the_house_rows_bit_for_bit(lines, mode, switch):
    with S.pinned_pricing(mode):
        every, out = lines(switch)
        nfl = P.nfl_lines(out)
        house = P.house_rows(out, LEAGUES, {"L1": "L1", "L2": "L2"})
        for lid, (_, sc) in LEAGUES.items():
            h = house[house["league_id"] == lid].set_index(["gsis_id", "week"])
            req = A.price_lines(nfl, sc).set_axis(pd.MultiIndex.from_frame(nfl[["gsis_id", "week"]]))
            assert (h.loc[req.index, "proj_points"].to_numpy() == req.to_numpy()).all()
    assert (out is every) == (switch == "0")


def test_a_fit_under_the_minimum_leaves_every_line(lines):
    every, out = lines("1", fit_rows=_fit_rows(n=10))
    assert out is every and C.LAST_PASS_TD == {"a": 1.0, "b": 0.0, "rows": 10, "moved": 0}


def test_the_switch_defaults_to_the_harness_verdict_and_the_version(monkeypatch):
    monkeypatch.delenv(C.PASS_TD_FLAG, raising=False)
    assert C.pass_td_enabled() is C.PASS_TD_DEFAULT is True
    for v, on in (("", True), ("0", False), ("off", False), ("1", True), ("on", True)):
        monkeypatch.setenv(C.PASS_TD_FLAG, v)
        assert C.pass_td_enabled() is on
    assert P.MODEL_VERSION == "v3.5" and C.PASS_TD_POSITIONS == ("QB",)   # IQ-1: v3.5 keeps pt1.0


def test_a_scenario_larger_role_follows_the_new_passing_tds():
    """signals.scenarios refits the models: the base becomes the stored line (pt1.0's passing TDs) and the larger role's
    passing TDs move by the same ratio, every other component as the model made it; M6's cold start (every component
    x k) is unchanged."""
    model = {c: 0.0 for c in COMPS} | {"proj_attempts": 33.0, "proj_passing_yards": 250.0, "proj_passing_tds": 2.0,
                                        "proj_rushing_yards": 10.0}
    larger = {c: v * 1.1 for c, v in model.items()}
    stored = {"gsis_id": "qb", "week": 5, **model, "proj_passing_tds": 1.5}
    b, s = C.rescale_to_stored(pd.DataFrame([model]), pd.DataFrame([larger]), [("qb", 5)], pd.DataFrame([stored]))
    assert b.iloc[0]["proj_passing_tds"] == 1.5 and b.iloc[0]["proj_passing_yards"] == 250.0
    assert s.iloc[0]["proj_passing_tds"] == pytest.approx(2.2 * 0.75)
    assert s.iloc[0]["proj_passing_yards"] == pytest.approx(275.0) and s.iloc[0]["proj_rushing_yards"] == pytest.approx(11.0)
