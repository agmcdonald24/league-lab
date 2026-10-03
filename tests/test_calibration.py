"""Calibration of the top (Wave I-A, M1): the map is monotone, walk-forward, and the identity when there is no bias.

Synthetic data only (no database): ``calibration.fit_map`` / ``fit_maps`` / ``walk_forward_calibrate`` / ``apply_maps`` /
``calibrate_outputs`` (flag off) / ``score_rows``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from league_lab import calibration as C


def _rows(seasons=(2020, 2021, 2022), n_players=300, weeks=10, top_lift=0.0, seed=0, position="WR", league="L1"):
    """Player-weeks with a projection and an actual = projection + noise (+ ``top_lift`` x the part above 12 points)."""
    rng = np.random.default_rng(seed)
    out = []
    for s in seasons:
        lift = top_lift(s) if callable(top_lift) else top_lift
        talent = rng.gamma(2.0, 3.5, n_players)
        for w in range(1, weeks + 1):
            proj = np.clip(talent + rng.normal(0, 1.0, n_players), 0, None)
            actual = proj + lift * np.maximum(proj - 12.0, 0) + rng.normal(0, 4.0, n_players)
            out.append(pd.DataFrame({"gsis_id": [f"p{i}" for i in range(n_players)], "season": s, "week": w,
                                     "position": position, "league_id": league, "proj_points": proj, "actual": actual,
                                     "p10": np.clip(proj - 6, 0, None), "p25": np.clip(proj - 3, 0, None), "p50": proj,
                                     "p75": proj + 3, "p90": proj + 6}))
    return pd.concat(out, ignore_index=True)


@pytest.mark.parametrize("mode", ["hinge", "two_piece"])
def test_map_is_monotone(mode):
    d = _rows(top_lift=0.4, seed=1)
    m = C.fit_map(d["proj_points"], d["actual"], d["gsis_id"], mode=mode)
    grid = np.linspace(0, 40, 801)
    cal = m.apply(grid)
    assert np.all(np.diff(cal) > 0), "the map must be strictly increasing (it never swaps two players)"
    # an absurd fit is clipped: slopes stay within MAX_SLOPE, so the map is still increasing
    steep = C.CalMap("WR", "L1", knot=10.0, level=0.0, s_lo=-C.MAX_SLOPE, s_hi=C.MAX_SLOPE)
    assert np.all(np.diff(steep.apply(grid)) > 0)


def test_identity_when_there_is_no_bias():
    d = _rows(top_lift=0.0, seed=2)
    for mode in ("hinge", "two_piece"):
        m = C.fit_map(d["proj_points"], d["actual"], d["gsis_id"], mode=mode)
        grid = np.linspace(0, 35, 200)
        assert np.max(np.abs(m.apply(grid) - grid)) < 0.15, (mode, m)
    hinge = C.fit_map(d["proj_points"], d["actual"], d["gsis_id"], mode="hinge")
    assert hinge.identity, hinge
    out = C.apply_maps(d, {("WR", "L1"): hinge})
    assert np.allclose(out["proj_points"], d["proj_points"])


def test_too_few_rows_is_the_identity():
    d = _rows(n_players=20, weeks=3, top_lift=1.0)
    m = C.fit_map(d["proj_points"], d["actual"], d["gsis_id"])
    assert m.n_rows == 0 and m.identity


def test_under_projected_top_is_lifted_and_mae_falls():
    d = _rows(top_lift=0.4, seed=3)
    m = C.fit_map(d["proj_points"], d["actual"], d["gsis_id"], mode="hinge")
    assert 0.25 < m.s_hi <= C.MAX_SLOPE
    below = d["proj_points"] <= m.knot
    cal = C.apply_maps(d, {("WR", "L1"): m})
    assert np.allclose(cal.loc[below, "proj_points"], d.loc[below, "proj_points"]), "nothing below the knot moves"
    test = _rows(seasons=(2023,), top_lift=0.4, seed=4)
    after = C.apply_maps(test, {("WR", "L1"): m})
    top = test["proj_points"] > m.knot
    mae_before = (test.loc[top, "actual"] - test.loc[top, "proj_points"]).abs().mean()
    mae_after = (after.loc[top, "actual"] - after.loc[top, "proj_points"]).abs().mean()
    assert mae_after < mae_before


def test_over_projected_top_is_not_lowered_by_the_hinge():
    d = _rows(top_lift=-0.3, seed=5)
    m = C.fit_map(d["proj_points"], d["actual"], d["gsis_id"], mode="hinge")
    assert m.identity, "the production map only lifts the top; it never lowers a projection"


def test_walk_forward_uses_earlier_seasons_only():
    # no bias in 2020-2021, a strong top lift from 2022 on: the 2022 map (fitted on 2020-2021) is the identity,
    # the 2023 map (fitted on 2020-2022) lifts the top
    d = _rows(seasons=(2020, 2021, 2022, 2023), top_lift=lambda s: 0.0 if s < 2022 else 0.5, seed=6)
    cal, maps = C.walk_forward_calibrate(d, [2022, 2023], mode="hinge")
    by_window = {m.seasons: m for m in maps}
    assert set(by_window) == {"2020-2021", "2020-2022"}
    assert by_window["2020-2021"].identity
    assert by_window["2020-2022"].s_hi > 0.1
    c22 = cal[cal["season"] == 2022].reset_index(drop=True)
    assert np.allclose(c22["proj_points"], d[d["season"] == 2022]["proj_points"].to_numpy())
    # the 2023 rows did not influence any map: refitting with 2023's outcomes scrambled gives the same maps
    scrambled = d.copy()
    scrambled.loc[scrambled["season"] == 2023, "actual"] = 0.0
    _, maps2 = C.walk_forward_calibrate(scrambled, [2022, 2023], mode="hinge")
    assert [(m.knot, m.s_hi) for m in maps] == [(m.knot, m.s_hi) for m in maps2]


def test_bands_move_with_the_point_and_keep_their_order():
    d = _rows(seasons=(2023,), weeks=2, seed=7)
    m = C.CalMap("WR", "L1", knot=10.0, s_hi=0.3)
    out = C.apply_maps(d, {("WR", "L1"): m})
    delta = out["proj_points"] - d["proj_points"]
    assert np.allclose(out["p90"] - d["p90"], delta)
    assert (out["p10"] >= 0).all()
    cols = ["p10", "p25", "p50", "p75", "p90"]
    assert (np.diff(out[cols].to_numpy(), axis=1) >= -1e-12).all()
    assert np.allclose(out["proj_points_raw"], d["proj_points"])
    other = d.assign(league_id="L2")
    assert np.allclose(C.apply_maps(other, {("WR", "L1"): m})["proj_points"], other["proj_points"]), "other scorings untouched"


def test_calibrate_outputs_is_a_no_op_with_the_flag_off(monkeypatch):
    monkeypatch.delenv(C.FLAG, raising=False)
    pred, ranges = pd.DataFrame({"position": ["WR"], "proj_points": [20.0]}), pd.DataFrame({"proj_points": [20.0]})
    out_p, out_r = C.calibrate_outputs(None, 2026, pred, ranges, {})   # never touches the connection
    assert out_p is pred and out_r is ranges
    monkeypatch.setenv(C.FLAG, "1")
    assert C.enabled()
    monkeypatch.setenv(C.FLAG, "0")
    assert not C.enabled()


def test_buckets_and_bias_table():
    d = _rows(seasons=(2023,), weeks=2, n_players=40, seed=8)
    b = C.with_buckets(d)
    assert set(b["bucket"]) == {"top 6", "7-12", "13-24", "25+"}
    assert (b.groupby(["season", "week"])["rank"].min() == 1).all()
    assert b.loc[b["rank"] <= 6, "bucket"].eq("top 6").all()
    assert sorted(b["decile"].unique()) == list(range(1, 11))
    t = C.bias_table(b, "bucket")
    assert list(t["bucket"]) == ["top 6", "7-12", "13-24", "25+"]
    top = b[b["bucket"] == "top 6"]
    assert t.loc[t["bucket"] == "top 6", "bias"].iloc[0] == pytest.approx((top["actual"] - top["proj_points"]).mean())


def test_score_rows_matches_the_definitions():
    d = _rows(seasons=(2023,), weeks=1, n_players=30, seed=9)
    s = C.score_rows(d)
    assert len(s) == 1
    assert s["mae"].iloc[0] == pytest.approx((d["actual"] - d["proj_points"]).abs().mean())
    inside = ((d["actual"] >= d["p10"]) & (d["actual"] <= d["p90"])).mean()
    assert s["coverage_80"].iloc[0] == pytest.approx(inside)
    same = C.compare(d, d)
    assert same["d_mae"].iloc[0] == 0 and same["d_spearman"].iloc[0] == 0


def test_production_hook_moves_only_the_calibrated_positions(monkeypatch):
    """Flag on: maps fitted on the stored out-of-sample rows (the newest WINDOW seasons, CAL_POSITIONS only) move the
    house leagues' rows of those positions and the ranges of the reference each league is; nothing else moves."""
    oof = pd.concat([_rows(seasons=(2023, 2024, 2025), top_lift=0.4, seed=10, position=p, league="L1") for p in ("WR", "RB")],
                    ignore_index=True)
    oof = pd.concat([oof, _rows(seasons=(2019,), top_lift=5.0, seed=11, league="L1")], ignore_index=True)  # outside WINDOW
    monkeypatch.setattr(C, "load_oof", lambda conn, before: oof[oof["season"] < before])
    monkeypatch.setenv(C.FLAG, "1")
    pred = pd.DataFrame({"league_id": ["L1", "L1", "L1", "L2"], "position": ["WR", "RB", "K", "WR"],
                         "proj_points": [20.0, 20.0, 9.0, 20.0], "p10": [8.0, 8.0, 3.0, 8.0], "p25": [14.0] * 4,
                         "p50": [19.0] * 4, "p75": [24.0] * 4, "p90": [30.0] * 4})
    ranges = pd.DataFrame({"scoring_name": ["ref1", "ref1", "other"], "position": ["WR", "RB", "WR"], "proj_points": [20.0] * 3,
                           "p10": [8.0] * 3, "p25": [14.0] * 3, "p50": [19.0] * 3, "p75": [24.0] * 3, "p90": [30.0] * 3})
    out, rng = C.calibrate_outputs(None, 2026, pred, ranges, {"L1": "ref1"})
    by = out.set_index(["league_id", "position"])["proj_points"]
    assert by[("L1", "WR")] > 20.0                       # the calibrated position of a calibrated scoring
    assert by[("L1", "RB")] == 20.0 and by[("L1", "K")] == 9.0 and by[("L2", "WR")] == 20.0
    r = rng.set_index(["scoring_name", "position"])["proj_points"]
    assert r[("ref1", "WR")] == pytest.approx(by[("L1", "WR")])
    assert r[("ref1", "RB")] == 20.0 and r[("other", "WR")] == 20.0
    assert "proj_points_raw" not in out and "proj_points_raw" not in rng


def test_expected_bonus_curves():
    """P(yards >= 100 | projected yards) is increasing; a scoring without yardage bonuses is untouched; a receiver
    projected just under 100 gains part of the bonus, one projected over it pays for the games he falls short."""
    rng = np.random.default_rng(12)
    n = 6000
    proj_yd = rng.uniform(10, 130, n)
    out_yd = np.clip(proj_yd + rng.normal(0, 30, n), 0, None)
    comps = {f"proj_{c}": np.zeros(n) for c in ("rushing_yards", "passing_yards")} | {f"out_{c}": np.zeros(n) for c in ("rushing_yards", "passing_yards")}
    rows = pd.DataFrame({"position": "WR", "proj_receiving_yards": proj_yd, "out_receiving_yards": out_yd, "actual": 1.0, **comps})
    curves = C.fit_bonus_curves(rows)
    p100 = curves[("WR", "receiving_yards", 100)].predict(np.linspace(0, 150, 151))
    assert np.all(np.diff(p100) >= 0) and p100[0] < 0.05 and p100[-1] > 0.8
    test = rows.iloc[:2].copy()
    test["proj_receiving_yards"] = [85.0, 115.0]
    assert np.allclose(C.bonus_delta(test, {"rec": 0.5, "rec_yd": 0.1}, curves), 0.0)
    d = C.bonus_delta(test, {"bonus_rec_yd_100": 3.0, "bonus_rec_yd_200": 6.0}, curves)
    assert 0 < d[0] < 3 and -3 < d[1] < 0
