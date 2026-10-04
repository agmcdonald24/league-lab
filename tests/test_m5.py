"""M5 (Wave I-G): v3.1 -- the ranges' target, the fringe level, cold starts (each behind its switch, off by default).

No database: synthetic frames and fixtures only (docs/METRICS.md § "Calibration of the top" -> "v3.1")."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from league_lab import calibration as C
from league_lab import experiments as X
from league_lab import projections as P
from league_lab.scoring import compute_points

# a synthetic league spec with every graded part the components leave out
SPEC = {"pass_yd": 0.04, "pass_td": 4.0, "pass_int": -1.0, "pass_2pt": 2.0, "pass_td_40p": 2.0, "pass_td_50p": 1.0,
        "rush_yd": 0.1, "rush_td": 6.0, "rush_2pt": 2.0, "rush_td_40p": 2.0, "rec": 1.0, "rec_yd": 0.1, "rec_td": 6.0,
        "rec_2pt": 2.0, "rec_td_40p": 2.0, "rec_td_50p": 3.0, "fum_lost": -2.0, "fum": -0.5, "fum_rec_td": 6.0,
        "st_td": 6.0, "bonus_rec_yd_100": 3.0, "bonus_rush_yd_100": 3.0, "bonus_pass_yd_300": 3.0}


def _line(**kw) -> dict[str, float]:
    row = {f"out_{c}": 0.0 for c in P.ALL_COMPONENTS} | {f"outx_{c}": 0.0 for c in P.GRADED_EXTRAS}
    row.update(kw)
    return row


def _frame() -> pd.DataFrame:
    rows = [
        _line(position="WR", out_targets=9, out_receptions=7, out_receiving_yards=131, out_receiving_tds=2,
              outx_rec_tds_40p=1, outx_rec_tds_50p=1, outx_receiving_2pt_conversions=1, outx_fumbles_total=1),
        _line(position="QB", out_attempts=35, out_passing_yards=312, out_passing_tds=3, out_passing_interceptions=1,
              out_carries=4, out_rushing_yards=22, outx_pass_tds_40p=1, outx_passing_2pt_conversions=1),
        _line(position="RB", out_carries=20, out_rushing_yards=104, out_rushing_tds=1, out_fumbles_lost_total=1,
              outx_rush_tds_40p=1, outx_fumble_recovery_tds=1, outx_fumbles_total=1),
        _line(position="TE", out_targets=3, out_receptions=2, out_receiving_yards=18),
    ]
    return pd.DataFrame(rows)


# ------------------------------------------------------------------------------ 1. the ranges' target
def test_graded_actual_equals_the_graded_points_on_a_synthetic_spec():
    d = _frame()
    got = P.graded_actual(d, SPEC).to_numpy()
    want = []
    for r in d.to_dict("records"):
        stats = {k[4:] if k.startswith("out_") else k[5:] if k.startswith("outx_") else k: v for k, v in r.items()}
        want.append(compute_points(stats, SPEC))
    assert got == pytest.approx(want)
    # by hand, the WR: 7 catches 7 + 131 yd 13.1 + 2 TD 12 + 100-yd bonus 3 + 40+ TD 2 + 50+ TD 3 + 2-pt 2 + fumble -0.5
    assert got[0] == pytest.approx(7 + 13.1 + 12 + 3 + 2 + 3 + 2 - 0.5)
    # the components alone miss exactly the extras (the v3.0 target)
    comp = P.price(d, SPEC, "out_").to_numpy()
    assert got[0] - comp[0] == pytest.approx(2 + 3 + 2 - 0.5)
    assert got[3] == pytest.approx(comp[3])      # nothing extra happened: the same number


def test_graded_actual_without_the_extra_columns_is_the_components_price():
    d = _frame().drop(columns=[f"outx_{c}" for c in P.GRADED_EXTRAS])
    assert P.graded_actual(d, SPEC).to_numpy() == pytest.approx(P.price(d, SPEC, "out_").to_numpy())


def test_range_actual_follows_the_switch(monkeypatch):
    d = _frame()
    monkeypatch.delenv(P.RANGE_TARGET_FLAG, raising=False)
    assert not P.range_target_graded()
    assert P.range_actual(d, SPEC).to_numpy() == pytest.approx(P.price(d, SPEC, "out_").to_numpy())
    monkeypatch.setenv(P.RANGE_TARGET_FLAG, "graded-all")      # the harness's setting: every position
    assert P.range_target_graded("WR")
    assert P.range_actual(d, SPEC).to_numpy() == pytest.approx(P.graded_actual(d, SPEC).to_numpy())
    for on in ("graded", "1", "on"):                           # production: the kept positions only (QB)
        monkeypatch.setenv(P.RANGE_TARGET_FLAG, on)
        assert P.range_target_graded() and P.range_target_graded("QB") and not P.range_target_graded("WR")
        qb, wr = d[d["position"] == "QB"], d[d["position"] == "WR"]
        assert P.range_actual(qb, SPEC).to_numpy() == pytest.approx(P.graded_actual(qb, SPEC).to_numpy())
        assert P.range_actual(wr, SPEC).to_numpy() == pytest.approx(P.price(wr, SPEC, "out_").to_numpy())
    monkeypatch.setenv(P.RANGE_TARGET_FLAG, "components")
    assert not P.range_target_graded() and not P.range_target_graded("QB")


def _synthetic_train(n_per_season: int = 160, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for season in (2019, 2020, 2021):
        for i in range(n_per_season):
            r = {f: rng.normal() for f in P.FEATURES_BY_POSITION["TE"]}
            lam = 3 + r["ppg_l3"]
            r |= {"gsis_id": f"p{i % 40}", "season": season, "week": float(1 + i % 17), "position": "TE", "played": True,
                  "no_history": False, "out_targets": rng.poisson(max(lam, 0.5) * 1.5), "out_receptions": rng.poisson(max(lam, 0.5)),
                  "out_receiving_yards": max(0.0, rng.normal(10 * max(lam, 0.5), 15)), "out_receiving_tds": rng.poisson(0.3),
                  "out_fumbles_lost_total": rng.poisson(0.02)}
            for c in P.ALL_COMPONENTS:
                r.setdefault(f"out_{c}", 0.0)
            r["outx_receiving_2pt_conversions"] = 1.0       # every game carries a 2-point catch the components miss
            rows.append(r)
    return pd.DataFrame(rows)


def test_fit_position_fits_the_ranges_on_the_graded_actual_under_the_switch(monkeypatch):
    """The point projection is the same either way; the residual models move by the graded extra (2 points a game)."""
    monkeypatch.setitem(P.HGB, "max_iter", 40)
    train = _synthetic_train()
    spec = {"t": ("t", {"rec": 1.0, "rec_yd": 0.1, "rec_td": 6.0, "rec_2pt": 2.0})}
    test = train[train["season"] == 2021].head(60)
    monkeypatch.delenv(P.RANGE_TARGET_FLAG, raising=False)
    base = P.predict_position(P.fit_position(train, "TE", spec), test, spec)
    monkeypatch.setenv(P.RANGE_TARGET_FLAG, "graded-all")
    alt = P.predict_position(P.fit_position(train, "TE", spec), test, spec)
    assert alt["proj_points"].to_numpy() == pytest.approx(base["proj_points"].to_numpy())
    shift = float((alt["p50"] - base["p50"]).mean())
    assert 1.5 < shift < 2.5


def test_shared_component_fits_fit_once_per_rows(monkeypatch):
    calls = []

    def fake(x, d, position):
        calls.append(position)
        return {"n": len(calls)}

    monkeypatch.setattr(P, "_fit_components", fake)
    d = pd.DataFrame({f"out_{c}": [1.0, 2.0] for c in P.COMPONENTS["TE"]})
    x = np.ones((2, 3))
    with X.shared_component_fits() as cache:
        a, b = P._fit_components(x, d, "TE"), P._fit_components(x.copy(), d, "TE")
        c = P._fit_components(x + 1, d, "TE")
    assert a is b and c is not a and cache.hits == 1 and len(calls) == 2
    assert P._fit_components is fake                   # restored


def test_decide_ranges_rules():
    def rows(lid, pos, d_is, cov80, cov50, b80=0.80, b50=0.50):
        return [{"league_id": lid, "position": pos, "season": s, "delta_interval_score": v, "coverage_80": cov80,
                 "coverage_50": cov50, "baseline_coverage_80": b80, "baseline_coverage_50": b50,
                 "delta_interval_score_50": v / 2} for s, v in zip((2023, 2024, 2025), d_is, strict=True)]
    p = pd.DataFrame(rows("a", "WR", (-0.02, -0.01, 0.001), 0.80, 0.50) + rows("a", "RB", (-0.02, -0.02, -0.02), 0.84, 0.50)
                     + rows("a", "TE", (0.0001, -0.0002, 0.0), 0.80, 0.50)
                     + rows("a", "QB", (-0.02, -0.01, -0.01), 0.735, 0.44, b80=0.73, b50=0.44))
    dec = X.decide_ranges(p).set_index("position")["decision"].to_dict()
    assert dec == {"WR": "keep", "RB": "drop", "TE": "no change", "QB": "keep"}
    assert X.coverage_holds(0.79, 0.70, X.V31_COVERAGE_80)
    assert not X.coverage_holds(0.70, 0.73, X.V31_COVERAGE_80)


# ------------------------------------------------------------------------------ 2. the fringe level
def test_every_switch_off_is_a_no_op(monkeypatch):
    for f in (C.FLAG, C.FRINGE_FLAG, C.COLD_START_FLAG):
        monkeypatch.delenv(f, raising=False)
    pred, ranges = pd.DataFrame({"position": ["WR"], "proj_points": [10.0]}), pd.DataFrame()
    out, rng = C.calibrate_outputs(None, 2026, pred, ranges, {})       # no database touched
    assert out is pred and rng is ranges


def _fringe_rows(fringe_bias: float, seasons=(2020, 2021, 2022), seed: int = 1) -> pd.DataFrame:
    """60 players a week, projections spread 2-22; the top 24 unbiased, the rest off by ``fringe_bias``."""
    rng = np.random.default_rng(seed)
    out = []
    for s in seasons:
        for w in range(1, 18):
            proj = np.sort(rng.uniform(2, 22, 60))[::-1]
            rank = np.arange(1, 61)
            noise = rng.normal(0, 4, 60)
            actual = proj + noise + np.where(rank > 24, fringe_bias, 0.0)
            out.append(pd.DataFrame({"gsis_id": [f"p{i}" for i in range(60)], "season": s, "week": w, "position": "WR",
                                     "league_id": "L", "proj_points": proj, "actual": actual,
                                     "p10": np.maximum(proj - 6, 0), "p25": np.maximum(proj - 3, 0), "p50": proj,
                                     "p75": proj + 3, "p90": proj + 6}))
    return pd.concat(out, ignore_index=True)


def test_fringe_map_lowers_an_over_projected_fringe_and_leaves_the_top():
    rows = _fringe_rows(-1.0)
    m = C.fit_fringe(rows, "WR", "L")
    assert not m.identity and m.levels[-1] == 0.0
    assert all(v < -0.5 for v in m.levels[:-1])
    top = m.knots[-1]
    grid = np.linspace(0, 40, 4001)
    cal = m.apply(grid)
    assert np.all(np.diff(cal) > 0)                              # monotone (strictly)
    assert cal[grid >= top] == pytest.approx(grid[grid >= top])  # the top is untouched
    assert np.all(cal >= C.FRINGE_FLOOR * grid - 1e-12)


def test_fringe_map_is_monotone_when_the_fringe_is_under_projected():
    m = C.fit_fringe(_fringe_rows(+6.0), "WR", "L")
    assert m.levels[0] > 0
    grid = np.linspace(0, 40, 4001)
    assert np.all(np.diff(m.apply(grid)) > 0)
    slopes = np.diff(m.levels) / np.diff(m.knots)
    assert np.all(slopes >= -C.MAX_SLOPE - 1e-9)


def test_fringe_noise_is_the_identity_and_too_few_rows_too():
    rows = _fringe_rows(0.0)
    m = C.fit_fringe(rows, "WR", "L")
    assert max(abs(v) for v in m.levels) < 0.25
    assert C.fit_fringe(rows.head(100), "WR", "L").identity


def test_apply_fringe_keeps_the_order_within_a_week_and_moves_the_bands():
    rows = _fringe_rows(-1.0, seasons=(2023,))
    m = C.fit_fringes(_fringe_rows(-1.0))
    out = C.apply_fringe(rows, m)
    for _, g in out.groupby(["season", "week"]):
        assert (g["proj_points"].rank().to_numpy() == g["proj_points_raw"].rank().to_numpy()).all()
    moved = out["proj_points"] - out["proj_points_raw"]
    assert (moved <= 1e-12).all() and (moved < -0.1).any()
    ok = out["p90"] > 0
    assert ((out["p90"] - out["proj_points"])[ok] >= (rows["p90"] - rows["proj_points"])[ok] - 1e-9).all()
    assert (out[["p10", "p25", "p50", "p75", "p90"]].diff(axis=1).iloc[:, 1:] >= -1e-12).all().all()


# ------------------------------------------------------------------------------ 3. cold starts
def test_the_cold_start_blend_is_the_identity_at_n_games():
    assert C.blend_identity_at(C.COLD_N)
    cp = C.ColdPrior("WR", "L", {"all": 9.0, "pick 1-32": 12.0}, (0.0, 0.5, 0.8))
    proj = np.array([5.0, 5.0, 5.0, 5.0, 5.0])
    games = np.array([0, 1, 2, 3, 40])
    cold = C.is_cold(games)
    out = cp.blend(proj, games, np.array(["pick 1-32"] * 5), cold)
    assert out == pytest.approx([12.0, 0.5 * 5 + 0.5 * 12, 0.8 * 5 + 0.2 * 12, 5.0, 5.0])


def test_is_cold_draft_bucket_and_careers_before_the_window():
    assert C.is_cold(np.array([0, 2, 3]), np.array([False, True, False])).tolist() == [True, False, False]
    assert C.draft_bucket(pd.Series([1, 32, 33, 100, 200, None])).tolist() == [
        "pick 1-32", "pick 1-32", "pick 33-64", "pick 65-128", "pick 129+", "undrafted"]


def test_career_games_before_counts_strictly_earlier_played_games():
    games = pd.DataFrame({"gsis_id": ["a", "a", "a", "b"], "season": [2025, 2025, 2026, 2026], "week": [1, 2, 1, 3]})
    rows = pd.DataFrame({"gsis_id": ["a", "a", "a", "b", "b", "c"], "season": [2025, 2026, 2026, 2026, 2026, 2026],
                         "week": [1, 1, 5, 3, 4, 1]})
    assert C.career_games_before(rows, games).tolist() == [0, 2, 3, 0, 1, 0]


def test_fit_cold_prior_learns_the_bucket_and_keeps_the_model_where_it_is_better():
    rng = np.random.default_rng(3)
    n = 400
    games = rng.integers(0, 3, n)
    bucket = np.where(rng.random(n) < 0.5, "pick 1-32", "undrafted")
    truth = np.where(bucket == "pick 1-32", 12.0, 4.0) + rng.normal(0, 3, n)   # players differ within a bucket
    proj = np.where(games == 0, 8.0, truth + rng.normal(0, 0.5, n))   # the model knows nothing at game 0, then the player
    rows = pd.DataFrame({"season": 2022, "proj_points": proj, "actual": truth + rng.normal(0, 1, n),
                         "career_games_before": games, "cold": True, "bucket": bucket})
    cp = C.fit_cold_prior(rows, "WR", "L")
    assert cp.prior["pick 1-32"] > cp.prior["undrafted"] + 5
    assert cp.weights[0] <= 0.2 and cp.weights[1] >= 0.8 and cp.weights[2] >= 0.8


def test_v31_switches_on_without_a_kept_position_change_nothing(monkeypatch):
    monkeypatch.setenv(C.FRINGE_FLAG, "1")
    monkeypatch.setenv(C.COLD_START_FLAG, "1")
    monkeypatch.delenv(C.FLAG, raising=False)
    monkeypatch.setattr(C, "FRINGE_POSITIONS", ())
    monkeypatch.setattr(C, "COLD_POSITIONS", ())
    oof = _fringe_rows(-1.0, seasons=(2023, 2024, 2025))     # the WINDOW seasons before 2026
    monkeypatch.setattr(C, "load_oof", lambda conn, season: oof)
    pred = _fringe_rows(-1.0, seasons=(2026,))
    out, rng = C.calibrate_outputs(None, 2026, pred, pd.DataFrame(), {"L": "ref"})
    assert out["proj_points"].to_numpy() == pytest.approx(pred["proj_points"].to_numpy())
    # with WR kept, the fringe moves and the top does not
    monkeypatch.setattr(C, "FRINGE_POSITIONS", ("WR",))
    out, _ = C.calibrate_outputs(None, 2026, pred, pd.DataFrame(), {"L": "ref"})
    moved = out["proj_points"].to_numpy() - pred["proj_points"].to_numpy()
    assert (moved < -0.1).any() and (moved <= 1e-12).all()


class _FakeConn:
    """Answers the two history queries of ``v31_outputs`` (the games, the draft slots) from fixtures."""

    def __init__(self, games, draft):
        self.games, self.draft = games, draft

    def cursor(self):
        conn = self

        class Cur:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def execute(self, sql, params=None):
                self.rows = conn.games if "fct_player_game" in sql else conn.draft

            def fetchall(self):
                return self.rows

        return Cur()


def test_cold_start_on_moves_a_rookie_toward_his_draft_slot_and_never_a_veteran(monkeypatch):
    monkeypatch.setenv(C.COLD_START_FLAG, "1")
    monkeypatch.delenv(C.FRINGE_FLAG, raising=False)
    monkeypatch.delenv(C.FLAG, raising=False)
    monkeypatch.setattr(C, "COLD_POSITIONS", ("WR",))
    rng = np.random.default_rng(5)
    fit = []      # 3 seasons of cold WR rows: first-round rookies score 9, the model said 5 at game 0
    for s in (2023, 2024, 2025):
        for i in range(60):
            fit.append({"gsis_id": f"r{s}_{i}", "season": s, "week": 1, "position": "WR", "league_id": "L",
                        "proj_points": 5.0, "actual": 9.0 + rng.normal(0, 1)})
    oof = pd.DataFrame(fit)
    monkeypatch.setattr(C, "load_oof", lambda conn, season: oof)
    draft = [(f"r{s}_{i}", 10, s) for s in (2023, 2024, 2025) for i in range(60)] + [("rook", 12, 2026), ("vet", 40, 2019)]
    games = [("vet", 2025, w) for w in range(1, 18)]
    pred = pd.DataFrame({"gsis_id": ["rook", "vet"], "season": 2026, "week": 5, "position": "WR", "league_id": "L",
                         "proj_points": [5.0, 5.0], "p10": [1.0, 1.0], "p25": [3.0, 3.0], "p50": [5.0, 5.0],
                         "p75": [7.0, 7.0], "p90": [9.0, 9.0]})
    ranges = pred.drop(columns="league_id").assign(scoring_name="ref")
    # M6 (Wave I-H): production blends the stat line (calibration.blend_lines, tests/test_m6.py); M5's points wiring is
    # kept behind ``cold_on_points`` for the harness's comparison, and calibrate_outputs no longer calls it
    out, rng_out = C.v31_outputs(_FakeConn(games, draft), 2026, pred, ranges, {"L": "ref"}, cold_on_points=True)
    same, _ = C.calibrate_outputs(_FakeConn(games, draft), 2026, pred, ranges, {"L": "ref"})
    assert same["proj_points"].tolist() == pred["proj_points"].tolist()
    rook, vet = out.set_index("gsis_id").loc["rook"], out.set_index("gsis_id").loc["vet"]
    assert rook["proj_points"] > 8.0 and vet["proj_points"] == 5.0
    assert rook["p90"] - rook["proj_points"] == pytest.approx(4.0)        # the range moved with the point
    assert rng_out.set_index("gsis_id").loc["rook", "proj_points"] == pytest.approx(rook["proj_points"])
    assert list(out.columns) == list(pred.columns)
