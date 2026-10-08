"""IQ-3 (Wave I-Q): v3.6 -- hb1.0, a quarterback's weeks after the market week blend the model's stat line with his own
per-game line (calibration.horizon_blend_lines, docs/METRICS.md § "v3.6: the quarterback model reads the quarterback
(IQ-3)"); and the ``_matrix`` trap (a column unknown in the whole prediction batch is NaN, not 0). No database.

* ``naive_line``: (g x this season per game + lambda x g_prev x last season's + k x the role's mean) / (g + lambda g_prev
  + k), the role the week's listed starter or not;
* ``horizon_rows``: a past season's later weeks as the nightly builds them (the market-week row, T's opponent as of w,
  the team's own line so far shrunk by 3 games, no injury report, T's outcome, h = T - w);
* ``horizon_blend_lines`` (``project``'s hook) moves only QB lines of weeks after the market week, at (1 - w_h) x the
  model + w_h x the naive line (h > 8 takes w_8), prices and ranges the new line through the frozen-line path (the house
  rows equal the request side's price of the NFL-wide line, flat and at the odds); played weeks, the market week and
  every other position are untouched; the switch off, or every weight 0, is ``every`` itself; unset = on;
* a batch of later weeks alone predicts exactly what the same rows predict inside a full season's batch.
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
MODEL = {"attempts": 33.0, "passing_yards": 250.0, "passing_tds": 1.6, "passing_interceptions": 0.8, "carries": 4.0,
         "rushing_yards": 20.0, "rushing_tds": 0.15, "fumbles_lost_total": 0.2}
HIS = {"attempts": 36.0, "passing_yards": 300.0, "passing_tds": 2.4, "passing_interceptions": 0.5, "carries": 6.0,
       "rushing_yards": 40.0, "rushing_tds": 0.4, "fumbles_lost_total": 0.1}
WR_LINE = {"targets": 7.0, "receptions": 5.0, "receiving_yards": 70.0, "receiving_tds": 0.4}
PARAMS = C.NaiveParams(lam=0.5, k=4.0, role_means={c: (MODEL.get(c, 0.0), 0.0) for c in P.ALL_COMPONENTS})
WEIGHTS = {2: 0.5, 3: 0.6, 4: 0.7, 5: 0.8, 6: 0.9, 7: 1.0, 8: 0.25}


def _fake_predict(m, rows, scorings, lines=None):
    """test_ip1_pass_td's stand-in: the real ``projections.price``, bands at +-3 / 6; without ``lines`` the m_ columns."""
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


def _target() -> pd.DataFrame:
    """2026: weeks 1-4 played, week 5 the market week, weeks 6-18 later; a starter with 4 games this season and 16 last
    (his line = HIS), a WR (never touched)."""
    rows = []
    for gid, pos in (("star", "QB"), ("wr", "WR")):
        line = MODEL if pos == "QB" else WR_LINE
        for wk in range(1, 19):
            r = {"gsis_id": gid, "season": 2026, "week": float(wk), "position": pos, "team": "AAA", "played": wk <= 4,
                 "games_to_date": 4.0, "prev_games": 16.0, "pn_qb_starting": 1.0 if pos == "QB" else np.nan}
            r |= {f"m_{c}": line.get(c, 0.0) for c in P.ALL_COMPONENTS}
            r |= {f"{c}_pg_std": HIS.get(c, 0.0) for c in P.ALL_COMPONENTS} | {f"prev_{c}_pg": HIS.get(c, 0.0) for c in P.ALL_COMPONENTS}
            rows.append(r)
    return pd.DataFrame(rows)


@pytest.fixture
def blend(monkeypatch):
    monkeypatch.delenv("LEAGUE_LAB_EV_PRICING", raising=False)
    monkeypatch.setattr(P, "predict_position", _fake_predict)
    target = _target()

    def run(switch: str | None, weights: dict | None = None):
        if switch is None:
            monkeypatch.delenv(C.HORIZON_BLEND_FLAG, raising=False)
        else:
            monkeypatch.setenv(C.HORIZON_BLEND_FLAG, switch)
        monkeypatch.setattr(C, "fit_horizon_weights", lambda train, season, scorings, pos="QB": dict(WEIGHTS if weights is None else weights))
        monkeypatch.setattr(C, "fit_naive", lambda rows, scorings: PARAMS)
        every = pd.concat([_fake_predict(None, target[target["position"] == pos], LEAGUES) for pos in ("QB", "WR")],
                          ignore_index=True)
        every["model_version"], every["fitted_at"], every["train_seasons"] = P.MODEL_VERSION, pd.Timestamp("2026-10-07", tz="UTC"), "2016-2025"
        train = pd.DataFrame({"season": [2025], "position": ["QB"]})
        return every, C.horizon_blend_lines(2026, every, {"QB": None, "WR": None}, target, train, LEAGUES, LEAGUES)
    return run


def _row(df, gid, week, lid="L1"):
    return df[(df["gsis_id"] == gid) & (df["week"] == week) & (df["league_id"] == lid)].iloc[0]


def test_naive_line_is_his_record_shrunk_toward_his_role():
    rows = pd.DataFrame({"games_to_date": [3.0, 0.0, 2.0], "prev_games": [10.0, 0.0, 0.0], "pn_qb_starting": [1.0, 1.0, 0.0],
                         **{f"{c}_pg_std": [2.0, np.nan, 1.0] for c in P.ALL_COMPONENTS},
                         **{f"prev_{c}_pg": [1.0, np.nan, np.nan] for c in P.ALL_COMPONENTS}})
    p = C.NaiveParams(lam=0.5, k=4.0, role_means={c: (1.5, 0.2) for c in P.ALL_COMPONENTS})
    n = C.naive_line(rows, p)
    assert n.loc[0, "n_passing_tds"] == pytest.approx((3 * 2.0 + 0.5 * 10 * 1.0 + 4 * 1.5) / (3 + 5 + 4))
    assert n.loc[1, "n_passing_tds"] == pytest.approx(1.5)                    # no games: the starters' mean
    assert n.loc[2, "n_passing_tds"] == pytest.approx((2 * 1.0 + 4 * 0.2) / 6)   # not the listed starter: the others' mean


def test_only_later_qb_weeks_move_by_the_horizon_weight(blend):
    every, out = blend(None)
    assert len(out) == len(every) and set(out.columns) == set(every.columns)
    naive = {c: (4 * HIS.get(c, 0.0) + 0.5 * 16 * HIS.get(c, 0.0) + 4 * MODEL.get(c, 0.0)) / (4 + 8 + 4) for c in P.ALL_COMPONENTS}
    for wk, h in ((6, 2), (8, 4), (12, 8), (18, 8)):                     # h = week - 5 + 1; beyond 8 takes w_8
        w = WEIGHTS[min(h, 8)]
        r = _row(out, "star", wk)
        for c in P.ALL_COMPONENTS:
            assert r[f"proj_{c}"] == pytest.approx((1 - w) * MODEL.get(c, 0.0) + w * naive[c])
        assert r["p90"] - r["proj_points"] == pytest.approx(6.0)        # ranged around the new line
    cols = [*COMPS, "proj_points", "p10", "p25", "p50", "p75", "p90"]
    for gid, wk in [*(("star", w) for w in range(1, 6)), *(("wr", w) for w in range(1, 19))]:
        for lid in LEAGUES:
            x, y = _row(every, gid, wk, lid), _row(out, gid, wk, lid)
            assert [y[c] for c in cols] == [x[c] for c in cols]           # played weeks, the market week, the WR
    assert C.LAST_HORIZON_BLEND["moved"] == 13 and C.LAST_HORIZON_BLEND["market_week"] == 5


@pytest.mark.parametrize("mode", ["flat", "ev"])
@pytest.mark.parametrize("switch", ["1", "0"])
def test_the_new_line_prices_to_the_house_rows_bit_for_bit(blend, mode, switch):
    with S.pinned_pricing(mode):
        every, out = blend(switch)
        nfl = P.nfl_lines(out)
        house = P.house_rows(out, LEAGUES, {"L1": "L1", "L2": "L2"})
        for lid, (_, sc) in LEAGUES.items():
            h = house[house["league_id"] == lid].set_index(["gsis_id", "week"])
            req = A.price_lines(nfl, sc).set_axis(pd.MultiIndex.from_frame(nfl[["gsis_id", "week"]]))
            assert (h.loc[req.index, "proj_points"].to_numpy() == req.to_numpy()).all()
    assert (out is every) == (switch == "0")


def test_off_and_zero_weights_are_the_identity(blend, monkeypatch):
    every, out = blend("0")
    assert out is every
    every, out = blend(None, weights={h: 0.0 for h in range(2, 9)})
    assert out is every
    monkeypatch.delenv(C.HORIZON_BLEND_FLAG, raising=False)
    assert C.horizon_blend_enabled() is True and C.HORIZON_BLEND_DEFAULT is True
    assert P.MODEL_VERSION == "v3.6" and C.HORIZON_BLEND_POSITIONS == ("QB",)


def test_horizon_rows_build_later_weeks_as_the_nightly():
    rows = []
    for gid, team, opp in (("allen", "BUF", "MIA"), ("willis", "MIA", "BUF")):
        for wk in range(1, 7):
            o = opp if wk % 2 else "NYJ"
            imp = {"BUF": 28.0, "MIA": 20.0}[team] + wk if wk <= 3 else np.nan
            rows.append({"gsis_id": gid, "season": 2025, "week": float(wk), "position": "QB", "team": team, "opponent": o,
                         "f_home": float(wk % 2), "played": True, "implied_team_total": imp,
                         "total_line": 50.0 if wk <= 3 else np.nan, "spread_line": 0.0, "questionable": 1.0,
                         "games_to_date": float(wk - 1), "pn_qb_starting": 1.0,
                         **{c: 10.0 * wk for c in C.HB_OPP}, **{f"out_{c}": float(wk) for c in P.ALL_COMPONENTS}})
    s = pd.DataFrame(rows)
    r = C.horizon_rows(s, 2, h_max=4)                 # market week 3, later weeks 4-6 (h 2-4)
    assert sorted(r["h"].unique()) == [2.0, 3.0, 4.0] and len(r) == 6
    a = r[(r["gsis_id"] == "allen") & (r["h"] == 3)].iloc[0]
    assert a["week"] == 5.0 and a["games_to_date"] == 2.0          # T's week number; his history as of week 2
    assert a["out_passing_yards"] == 5.0 and a["questionable"] == 0.0
    assert a["opponent"] == "MIA" and a["opp_allowed_std"] == 30.0  # MIA as an opponent, as of week 3's row
    lg = ((29 + 30) / 2 + (21 + 22) / 2) / 2                       # the teams' means through week 2, then the league's
    assert a["implied_team_total"] == pytest.approx((2 * 29.5 + 3 * lg) / 5)


def test_a_later_weeks_batch_predicts_as_inside_the_season():
    """The ``_matrix`` trap: a column unknown in the whole batch (no line in any later week) used to become 0."""
    rng = np.random.default_rng(0)
    n = 600
    d = pd.DataFrame({"x": rng.normal(size=n), "implied_team_total": rng.uniform(15, 32, n)})
    d.loc[rng.random(n) < 0.2, "implied_team_total"] = np.nan
    d["out_passing_tds"] = np.clip(0.08 * d["implied_team_total"].fillna(22) + 0.3 * d["x"] + rng.normal(0, 0.3, n), 0, None)
    model = P._regressor("poisson").fit(P._binnable(P._matrix(d, ["x", "implied_team_total"])), d["out_passing_tds"])
    later = pd.DataFrame({"x": [0.5, -0.2], "implied_team_total": [np.nan, np.nan]})
    season = pd.concat([d[["x", "implied_team_total"]].head(5), later], ignore_index=True)
    alone = model.predict(P._matrix(later, ["x", "implied_team_total"]))
    inside = model.predict(P._matrix(season, ["x", "implied_team_total"]))[-2:]
    assert np.array_equal(alone, inside)
    zero = model.predict(later.fillna(0.0).to_numpy(dtype=float))           # what the trap predicted
    assert not np.allclose(alone, zero)
