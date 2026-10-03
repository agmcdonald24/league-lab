"""Expected-value pricing's distributions (Wave I-C, M2): threshold curves and TD-distance shares.

Synthetic data only (no database): the shipped constants are monotone and well-formed, the fitter recovers known
parameters, the TD shares partition, the description parser reads nflverse's return TDs, and the seed file is the
module's constants.
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from league_lab import scoring_ev as E
from league_lab.scoring import compute_points

ROOT = Path(__file__).resolve().parents[1]
DAD_TD_BANDS = [(0, 9, 6), (10, 39, 9), (40, None, 12)]   # MFL 70587: TDs by distance


# ---------------------------------------------------------------------------------------------- the shipped constants
def test_seed_matches_module_constants():
    with open(ROOT / "dbt/seeds/scoring_distributions.csv", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert rows == E.seed_rows(), "regenerate dbt/seeds/scoring_distributions.csv with league_lab.scoring_ev.write_seed()"
    assert tuple(rows[0].keys()) == E.SEED_COLUMNS


def test_every_curve_stat_has_a_pooled_curve_and_the_main_positions():
    for stat in E.CURVE_STATS:
        assert (stat, "ALL") in E.CURVES
    for key in [("passing_yards", "QB"), ("rushing_yards", "QB"), ("rushing_yards", "RB"), ("receiving_yards", "RB"),
                ("receiving_yards", "WR"), ("receiving_yards", "TE"), ("receptions", "WR"), ("receptions", "TE")]:
        assert key in E.CURVES
    assert E.CURVES[("passing_yards", "QB")][0] == E.NORMAL
    assert all(c[0] == E.GAMMA for (s, _), c in E.CURVES.items() if s != "passing_yards")
    for _fam, scale, p1, p2, n in E.CURVES.values():
        assert 0.6 < scale < 1.65 and p1 > 0 and p2 > 0 and n >= E.MIN_CURVE_ROWS


@pytest.mark.parametrize("key", sorted(E.CURVES))
def test_prob_at_least_is_monotone_in_the_mean(key):
    stat, pos = key
    means = np.linspace(0.0, 600.0 if stat == "passing_yards" else 250.0, 2501)
    for t in (1, 3, 5, 8, 12, 25, 50, 75, 100, 150, 200, 250, 300, 350, 400, 500):
        p = E.prob_at_least(stat, pos, means, t)
        assert np.all(np.diff(p) >= -1e-12), f"{stat} {pos} >= {t}: P must not fall as the projection rises"
        assert np.all((p >= 0) & (p <= 1))


def test_prob_at_least_edges_and_shapes():
    assert E.prob_at_least("rushing_yards", "RB", 0.0, 100) == 0.0
    assert E.prob_at_least("rushing_yards", "RB", float("nan"), 100) == 0.0
    assert E.prob_at_least("rushing_yards", "RB", 60.0, 0) == 1.0
    assert isinstance(E.prob_at_least("receptions", "WR", 5.0, 5), float)
    arr = E.prob_at_least("receptions", "WR", np.array([1.0, 5.0, 9.0]), 5)
    assert arr.shape == (3,) and arr[0] < arr[1] < arr[2]
    # a bigger threshold is never more likely
    assert E.prob_at_least("receiving_yards", "WR", 80.0, 100) < E.prob_at_least("receiving_yards", "WR", 80.0, 75)
    # sensible magnitudes (the motivating case: an 85-yard back crosses 100 about one game in three to four)
    assert 0.2 < E.prob_at_least("rushing_yards", "RB", 85.0, 100) < 0.45
    assert 0.15 < E.prob_at_least("passing_yards", "QB", 260.0, 300) < 0.45
    assert E.prob_at_least("passing_yards", "QB", 260.0, 400) < 0.08


def test_position_aliases_and_fallbacks():
    assert E.prob_at_least("passing_yards", "TMQB", 250.0, 300) == E.prob_at_least("passing_yards", "QB", 250.0, 300)
    # a position without its own curve takes the pooled one
    assert E.has_curve("rushing_yards", "TE")
    assert E.prob_at_least("rushing_yards", "TE", 30.0, 50) == E.prob_at_least("rushing_yards", "ALL", 30.0, 50)
    # a stat without a curve: the deterministic step, and has_curve says so
    assert not E.has_curve("fg_made", "K")
    assert E.prob_at_least("fg_made", "K", 2.0, 2) == 1.0 and E.prob_at_least("fg_made", "K", 1.9, 2) == 0.0


def test_prob_in_band_partitions():
    for mean in (20.0, 60.0, 110.0):
        parts = [E.prob_in_band("receiving_yards", "WR", mean, 0, 99), E.prob_in_band("receiving_yards", "WR", mean, 100, 199),
                 E.prob_in_band("receiving_yards", "WR", mean, 200, None)]
        assert sum(parts) == pytest.approx(1.0, abs=1e-12)
        # an inclusive high: 100-199 is P(>=100) - P(>=200)
        assert parts[1] == pytest.approx(E.prob_at_least("receiving_yards", "WR", mean, 100)
                                         - E.prob_at_least("receiving_yards", "WR", mean, 200))


def test_expected_band_points():
    bands = [(100, None, 10)]   # MFL 70587: +10 at 100 rushing yards
    m = np.array([40.0, 85.0, 130.0])
    got = E.expected_band_points("rushing_yards", "RB", m, bands)
    assert got == pytest.approx(10 * E.prob_at_least("rushing_yards", "RB", m, 100))
    assert np.all(np.diff(got) > 0) and got[2] < 10


# ---------------------------------------------------------------------------------------------- fitting (synthetic)
def test_fit_curve_recovers_a_known_gamma():
    rng = np.random.default_rng(7)
    m = rng.uniform(15, 120, 40_000)
    k0, k1 = 0.3, 0.045
    k = k0 + k1 * m
    y = np.round(rng.gamma(k, m / k))
    fam, scale, p1, p2, n = E.fit_curve(m, y, "rushing_yards")
    assert fam == E.GAMMA and n == len(m)
    assert scale == pytest.approx(1.0, abs=0.03)
    E_true = (E.GAMMA, 1.0, k0, k1, n)
    for t in (50, 100, 150):
        for mean in (40.0, 85.0, 110.0):
            truth = E._tail(E_true[0], k0, k1, np.array([mean]), t)[0]
            fitted = E._tail(fam, p1, p2, np.array([scale * mean]), t)[0]
            assert fitted == pytest.approx(truth, abs=0.02)


def test_fit_curve_recovers_a_known_normal_for_passing():
    rng = np.random.default_rng(11)
    m = rng.uniform(150, 320, 30_000)
    y = np.round(rng.normal(0.95 * m, 75.0))
    fam, scale, sd0, sd1, _ = E.fit_curve(m, y, "passing_yards")
    assert fam == E.NORMAL
    assert scale == pytest.approx(0.95, abs=0.02)
    assert sd0 + sd1 * 250 == pytest.approx(75.0, rel=0.08)


def test_fit_curves_pools_and_skips_thin_positions():
    rng = np.random.default_rng(3)
    frames = []
    for pos, n in (("RB", 4000), ("TE", 300)):
        m = rng.uniform(5, 90, n)
        frames.append(pd.DataFrame({"position": pos, "proj_rushing_yards": m, "out_rushing_yards": np.round(rng.gamma(0.05 * m, 20.0)),
                                    **{f"{p}_{s}": np.nan for s in ("passing_yards", "receiving_yards", "receptions") for p in ("proj", "out")}}))
    curves = E.fit_curves(pd.concat(frames, ignore_index=True), min_rows=1500)
    assert ("rushing_yards", "RB") in curves and ("rushing_yards", "ALL") in curves
    assert ("rushing_yards", "TE") not in curves and ("receptions", "ALL") not in curves


# ---------------------------------------------------------------------------------------------- TD distances
@pytest.mark.parametrize("family", E.TD_FAMILIES)
def test_td_shares_partition_and_survival_is_decreasing(family):
    for pos in ("QB", "RB", "WR", "TE", "DEF", "ALL"):
        parts = [E.td_distance_share(family, pos, lo, hi) for lo, hi, _ in DAD_TD_BANDS]
        assert sum(parts) == pytest.approx(1.0, abs=1e-12) and min(parts) >= 0
        s = E.td_survival(family, pos, np.arange(0, 121))
        assert s[0] == 1.0 and np.all(np.diff(s) <= 1e-12) and s[-1] == 0.0


def test_td_shares_hit_the_measured_knots():
    surv, n, source = E.TD_SHARES[("receiving_tds", "WR")]
    assert source == "measured" and n > 1000
    for knot, value in zip(E.TD_KNOTS, surv, strict=True):
        assert E.td_survival("receiving_tds", "WR", knot) == pytest.approx(value, rel=1e-9)
    assert E.td_distance_share("receiving_tds", "WR", 40, None) == pytest.approx(surv[E.TD_KNOTS.index(40)])
    # sanity of the measured magnitudes (2019-2025): most rushing TDs are short, most WR catches for a TD are not
    assert E.td_distance_share("rushing_tds", "RB", 0, 9) > 0.65
    assert E.td_distance_share("receiving_tds", "WR", 10, None) > 0.5
    assert E.td_distance_share("receiving_tds", "TE", 40, None) < E.td_distance_share("receiving_tds", "WR", 40, None)
    assert E.td_distance_share("int_return_tds", "DEF", 40, None) > 0.4


def test_td_family_aliases_and_sources():
    assert E.td_distance_share("RS", "RB", 10, 39) == E.td_distance_share("rushing_tds", "RB", 10, 39)
    assert E.td_distance_share("IR", "Def", 40, None) == E.td_distance_share("int_return_tds", "DEF", 40, None)
    assert E.td_share_source("rushing_tds", "RB") == "measured"
    assert E.td_share_source("passing_tds", "WR") == "shrunk"
    assert E.td_share_source("missed_fg_return_tds", "ALL") == "proxy"
    assert E.td_share_source("no_such_tds", "QB") == "placeholder"


def test_expected_td_distance_points():
    per_td = sum(p * E.td_distance_share("rushing_tds", "RB", lo, hi) for lo, hi, p in DAD_TD_BANDS)
    assert 6 < per_td < 12
    assert E.expected_td_distance_points("rushing_tds", "RB", 0.5, DAD_TD_BANDS) == pytest.approx(0.5 * per_td)
    got = E.expected_td_distance_points("rushing_tds", "RB", np.array([0.0, 1.0]), DAD_TD_BANDS)
    assert got == pytest.approx([0.0, per_td])
    # a flat 6 per TD prices exactly 6 per expected TD whatever the shares
    assert E.expected_td_distance_points("receiving_tds", "TE", 0.4, [(0, None, 6)]) == pytest.approx(2.4)


def test_measure_td_shares_synthetic():
    d = [("rushing_tds", "RB", float(x)) for x in [1, 2, 3, 5, 12, 25, 45, 60]] * 20       # 160 RB TDs
    d += [("rushing_tds", "QB", 1.0)] * 10                                                    # 10 short QB TDs
    d += [("missed_fg_return_tds", "ALL", 105.0), ("kick_return_tds", "ALL", 100.0)] + [("kick_return_tds", "ALL", 95.0)] * 24
    out = E.measure_td_shares(d, shrink=30, min_family=20)
    surv_rb, n_rb, src_rb = out[("rushing_tds", "RB")]
    pooled = out[("rushing_tds", "ALL")][0]
    assert n_rb == 160 and src_rb == "measured"
    own_ge10 = 4 / 8
    assert surv_rb[E.TD_KNOTS.index(10)] == pytest.approx((160 * own_ge10 + 30 * pooled[E.TD_KNOTS.index(10)]) / 190, abs=1e-5)
    surv_qb, n_qb, src_qb = out[("rushing_tds", "QB")]
    assert n_qb == 10 and src_qb == "shrunk"
    assert surv_qb[E.TD_KNOTS.index(10)] == pytest.approx(30 * pooled[E.TD_KNOTS.index(10)] / 40, abs=1e-5)
    assert out[("missed_fg_return_tds", "ALL")][2] == "proxy"
    assert out[("missed_fg_return_tds", "ALL")][0] == out[("kick_return_tds", "ALL")][0]


@pytest.mark.parametrize("desc,yards", [
    ("2-T.Bass kicks 61 yards from BUF 35 to ARI 4. 20-D.Dallas for 96 yards, TOUCHDOWN.", 96),
    ("8-W.Levis pass short left INTERCEPTED by 29-T.Stevenson [95-D.Walker] at TEN 43. 29-T.Stevenson for 43 yards, TOUCHDOWN.", 43),
    ("4-R.Stonehouse punt is BLOCKED by 92-D.Hardy, RECOVERED by CHI-36-J.Owens at TEN 21. 36-J.Owens for 21 yards, TOUCHDOWN.", 21),
    ("13-B.Pinion punts 43 yards to NO 3. 22-R.Shaheed MUFFS catch, RECOVERED by ATL-12-K.Hodge at NO -8. TOUCHDOWN.", 0),
    ("FUMBLES, RECOVERED by DAL-90-D.Lawrence at NYG 1. 90-D.Lawrence for 1 yard, TOUCHDOWN.", 1),
    ("12-T.Brady sacked, FUMBLES, recovered by NE-55 at NE 0. 55-X.Y for no gain, TOUCHDOWN.", 0),
])
def test_return_distance_parses_the_description(desc, yards):
    assert E.return_distance(desc) == yards


def test_td_family_and_distances():
    plays = pd.DataFrame([
        dict(play_type="pass", pass_touchdown=True, rush_touchdown=False, is_interception=False, fumble=False, yards_gained=45,
             description="", passer_position="QB", receiver_position="WR", rusher_position=None),
        dict(play_type="run", pass_touchdown=False, rush_touchdown=True, is_interception=False, fumble=False, yards_gained=3,
             description="", passer_position=None, receiver_position=None, rusher_position="RB"),
        dict(play_type="pass", pass_touchdown=False, rush_touchdown=False, is_interception=True, fumble=False, yards_gained=0,
             description="INTERCEPTED by 1-A.B at X 30. 1-A.B for 70 yards, TOUCHDOWN.", passer_position="QB",
             receiver_position=None, rusher_position=None),
        dict(play_type="field_goal", pass_touchdown=False, rush_touchdown=False, is_interception=False, fumble=False,
             yards_gained=0, description="45 yard field goal is BLOCKED ... 2-D.L for 61 yards, TOUCHDOWN.",
             passer_position=None, receiver_position=None, rusher_position=None),
    ])
    got = E.td_distances(plays)
    assert got == [("passing_tds", "QB", 45.0), ("receiving_tds", "WR", 45.0), ("rushing_tds", "RB", 3.0),
                   ("int_return_tds", "ALL", 70.0), ("blocked_kick_tds", "ALL", 61.0)]


# ---------------------------------------------------------------------------------------------- Sleeper settings
DYNASTY_LIKE = {"rec": 1.0, "rec_yd": 0.1, "rush_yd": 0.1, "pass_yd": 0.05, "rec_td": 6.0, "rush_td": 6.0, "pass_td": 6.0,
                "bonus_rec_yd_100": 3.0, "bonus_rec_yd_200": 6.0, "bonus_rush_yd_100": 3.0, "bonus_rush_yd_200": 6.0,
                "bonus_pass_yd_300": 3.0, "bonus_pass_yd_400": 6.0, "rec_td_40p": 2.0, "rush_td_40p": 2.0, "pass_td_40p": 2.0}


def test_sleeper_expected_bonus():
    line = {"rushing_yards": 85.0, "rushing_tds": 0.6, "receiving_yards": 20.0, "receiving_tds": 0.1, "receptions": 2.5}
    got = E.sleeper_expected_bonus(line, DYNASTY_LIKE, "RB")
    want = (3 * E.prob_in_band("rushing_yards", "RB", 85.0, 100, 199) + 6 * E.prob_at_least("rushing_yards", "RB", 85.0, 200)
            + 3 * E.prob_in_band("receiving_yards", "RB", 20.0, 100, 199) + 6 * E.prob_at_least("receiving_yards", "RB", 20.0, 200)
            + 2 * 0.6 * E.td_survival("rushing_tds", "RB", 40) + 2 * 0.1 * E.td_survival("receiving_tds", "RB", 40))
    assert got == pytest.approx(want)
    # the all-or-nothing price of the same line pays no bonus at all
    assert compute_points(line, DYNASTY_LIKE) == compute_points(line, DYNASTY_LIKE, include_bonuses=False)
    # a scoring without bonus keys: nothing to add
    assert E.sleeper_expected_bonus(line, {"rec": 1.0, "rush_yd": 0.1}, "RB") == 0.0


def test_sleeper_expected_bonus_frame_matches_rows():
    rng = np.random.default_rng(5)
    cols = ["passing_yards", "passing_tds", "rushing_yards", "rushing_tds", "receiving_yards", "receiving_tds", "receptions"]
    df = pd.DataFrame({f"proj_{c}": rng.uniform(0, 1, 12) * (300 if "yards" in c else 2) for c in cols})
    df["position"] = ["QB", "RB", "WR", "TE"] * 3
    got = E.sleeper_expected_bonus_frame(df, DYNASTY_LIKE)
    want = [E.sleeper_expected_bonus({c: r[f"proj_{c}"] for c in cols}, DYNASTY_LIKE, r["position"]) for r in df.to_dict("records")]
    assert got == pytest.approx(want)


# ---------------------------------------------------------------------------------------------- per whole unit (MFL 1/10)
def test_expected_floor_units():
    m = np.array([0.0, 20.0, 85.0, 140.0])
    got = E.expected_floor_units("rushing_yards", "RB", m, 10)
    want = sum(E.prob_at_least("rushing_yards", "RB", m, 10 * j) for j in range(1, 101))
    assert got == pytest.approx(want)
    assert got[0] == 0.0 and np.all(np.diff(got) > 0)
    # below the linear price (the remainder is lost), never by more than a whole unit beyond the mean's scaling
    scale = E.CURVES[("rushing_yards", "RB")][1]
    lin = scale * m / 10
    assert np.all(got[1:] < lin[1:]) and np.all(lin[1:] - got[1:] < 1.0)
    # from a band's low: only the yards past `start` count
    assert E.expected_floor_units("receiving_yards", "WR", 80.0, 10, start=100) < E.expected_floor_units("receiving_yards", "WR", 80.0, 10)
    assert isinstance(E.expected_floor_units("passing_yards", "QB", 250.0, 20), float)
    # no curve: the linear price
    assert E.expected_floor_units("fg_yards", "K", 95.0, 10) == pytest.approx(9.5)
