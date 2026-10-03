"""Wave I-C (IC-1): the ScoringSpec — the compilers (Sleeper, MFL), pricing actual lines exactly and projected lines in
expectation, and parity with the flat engine (and so with the SQL macro) for the house leagues. No database needed."""

from __future__ import annotations

import json
import random
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from league_lab import scoring as S
from league_lab.scoring import (
    ScoringSpec,
    compute_points,
    compute_points_spec,
    expected_frame,
    expected_points,
    flat_from_spec,
    from_mfl,
    from_sleeper,
    kd_flat,
    price_detail,
)

ROOT = Path(__file__).resolve().parents[1]
MFL = ROOT / "api" / "tests" / "fixtures" / "mfl"

# the house leagues' current settings (dim_league_season, 2026-10-03), non-zero keys only
SCRUBS = {"blk_kick": 2.0, "def_st_ff": 1.0, "def_st_fum_rec": 1.0, "def_st_td": 6.0, "def_td": 6.0, "ff": 1.0,
          "fgm_0_19": 3.0, "fgm_20_29": 3.0, "fgm_30_39": 3.0, "fgm_40_49": 4.0, "fgm_50p": 5.0, "fgmiss": -1.0,
          "fum_lost": -2.0, "fum_rec": 2.0, "fum_rec_td": 6.0, "int": 2.0, "pass_2pt": 2.0, "pass_int": -1.0,
          "pass_td": 4.0, "pass_yd": 0.04, "pts_allow_0": 10.0, "pts_allow_14_20": 1.0, "pts_allow_1_6": 7.0,
          "pts_allow_28_34": -1.0, "pts_allow_35p": -4.0, "pts_allow_7_13": 4.0, "rec": 0.5, "rec_2pt": 2.0,
          "rec_td": 6.0, "rec_yd": 0.1, "rush_2pt": 2.0, "rush_td": 6.0, "rush_yd": 0.1, "sack": 1.0, "safe": 2.0,
          "st_ff": 1.0, "st_fum_rec": 1.0, "st_td": 6.0, "xpm": 1.0, "xpmiss": -1.0}
DYNASTY = {"blk_kick": 2.0, "bonus_pass_yd_300": 3.0, "bonus_pass_yd_400": 6.0, "bonus_rec_yd_100": 3.0,
           "bonus_rec_yd_200": 6.0, "bonus_rush_yd_100": 3.0, "bonus_rush_yd_200": 6.0, "def_2pt": 2.0,
           "def_st_fum_rec": 2.0, "def_st_td": 6.0, "def_td": 6.0, "ff": 1.0, "fgm_0_19": 3.0, "fgm_20_29": 3.0,
           "fgm_30_39": 4.0, "fgm_40_49": 5.0, "fgm_50p": 6.0, "fgmiss_0_19": -2.0, "fgmiss_20_29": -1.0,
           "fgmiss_30_39": -1.0, "fgmiss_40_49": -1.0, "fum_lost": -2.0, "fum_rec": 2.0, "fum_rec_td": 6.0, "int": 2.0,
           "pass_2pt": 2.0, "pass_int": -2.0, "pass_td": 6.0, "pass_td_40p": 2.0, "pass_yd": 0.05000000074505806,
           "pts_allow_0": 30.0, "pts_allow_14_20": 5.0, "pts_allow_1_6": 15.0, "pts_allow_7_13": 10.0, "rec": 1.0,
           "rec_2pt": 2.0, "rec_td": 6.0, "rec_td_40p": 2.0, "rec_yd": 0.10000000149011612, "rush_2pt": 2.0,
           "rush_td": 6.0, "rush_td_40p": 2.0, "rush_yd": 0.10000000149011612, "sack": 2.0, "safe": 2.0,
           "st_fum_rec": 2.0, "st_td": 6.0, "xpm": 1.0, "xpmiss": -1.0}
TE_PREMIUM = {"rec": 1.0, "bonus_rec_te": 0.5, "rec_yd": 0.1, "rec_td": 6.0, "pass_td_50p": 1.0, "rec_td_50p": 1.0,
              "pass_yd": 0.04, "pass_td": 4.0}


def _rules(league: str) -> dict:
    return json.loads((MFL / league / "rules.json").read_text())


@pytest.fixture(scope="module")
def dad() -> ScoringSpec:
    return from_mfl(_rules("70587"))


# ------------------------------------------------------------------ 70587 ("Make Football Great Again"): hand-computed
def test_70587_compiles_per_position(dad):
    assert set(dad.positions) == {"QB", "RB", "WR", "TE", "K", "DEF"}
    assert dad.unpriced == [] and dad.source == "mfl" and dad.flat is None
    rb, wr, te, qb = (dad.positions[p] for p in ("RB", "WR", "TE", "QB"))
    assert rb.distance["rushing_tds"] == [(0.0, 9.0, 6.0), (10.0, 39.0, 9.0), (40.0, 110.0, 12.0)]
    assert rb.bands["rushing_yards"] == [(100.0, None, 10.0)] and rb.bands["receiving_yards"] == [(100.0, None, 10.0)]
    assert wr.bands["rushing_yards"] == [(75.0, None, 10.0)] and wr.bands["receiving_yards"] == [(100.0, None, 10.0)]
    assert te.bands["receiving_yards"] == [(75.0, None, 10.0)]
    assert qb.bands["passing_yards"] == [(250.0, None, 10.0)]
    assert qb.steps["passing_yards"] == [S.Step(20.0, None, 1.0, 20.0, 0.0, 0.0)]
    assert rb.steps["rushing_yards"] == [S.Step(10.0, None, 1.0, 10.0, 0.0, 0.0)]
    assert "receptions" not in rb.rates                          # no points per catch in this league
    assert rb.rates["fumbles_lost_total"] == -3 and qb.rates["passing_interceptions"] == -3
    assert dad.positions["K"].distance["fg_made"] == [(0.0, 39.0, 3.0), (40.0, 49.0, 5.0), (50.0, 59.0, 10.0), (60.0, 99.0, 15.0)]
    d = dad.positions["DEF"]
    assert d.rates == {"fumble_recoveries": 3.0, "interceptions": 3.0, "sacks": 2.0, "safeties": 4.0}
    assert d.bands["points_allowed"] == [(0.0, 0.0, 10.0), (1.0, 3.0, 8.0)]
    # units price with the position they stand for
    assert dad.rules_for("TMQB") is qb and dad.rules_for("TMPK") is dad.positions["K"] and dad.rules_for("Def") is d


def test_70587_rb_120_yards_and_a_45_yard_touchdown(dad):
    line = {"rushing_yards": 120, "rushing_tds": 2, "rushing_tds_lengths": [45, 3], "receiving_yards": 30,
            "receptions": 4}
    # 12 (120 / 10) + 10 (100+) + 12 (45-yard TD) + 6 (3-yard TD) + 3 (30 receiving yards) + 0 per catch
    assert compute_points_spec(line, dad, "RB") == 43.0


def test_70587_qb_line(dad):
    line = {"passing_yards": 262, "passing_tds": 3, "passing_tds_lengths": [5, 25, 60], "passing_interceptions": 1,
            "rushing_yards": 18, "fumbles_lost_total": 1}
    # 13 (262 / 20, whole) + 10 (250+) + 6 + 9 + 12 - 3 + 1 (18 / 10, whole) - 3; a QB's 75+ rushing bonus not reached
    assert compute_points_spec(line, dad, "QB") == 45.0
    assert compute_points_spec(line, dad, "TMQB") == 45.0                   # the team-QB unit: QB's rules


def test_70587_wr_and_te_thresholds_differ(dad):
    wr = {"receiving_yards": 99, "receiving_tds": 1, "receiving_tds_lengths": [15], "receiving_2pt_conversions": 1,
          "receptions": 5}
    assert compute_points_spec(wr, dad, "WR") == 9 + 9 + 2               # 99 yards: no bonus (100+ for a WR)
    te = {"receiving_yards": 75, "rushing_yards": 9}
    assert compute_points_spec(te, dad, "TE") == 7 + 10                  # 75+ for a TE; 9 rushing yards pay 0


def test_70587_kicker_and_defense(dad):
    k = {"fg_made": 4, "fg_made_30_39": 1, "fg_made_40_49": 1, "fg_made_50_59": 1, "fg_made_60_": 1, "pat_made": 3}
    assert compute_points_spec(k, dad, "TMPK") == 3 + 5 + 10 + 15 + 3
    d = {"sacks": 3, "interceptions": 1, "fumble_recoveries": 1, "points_allowed": 0, "safeties": 1}
    assert compute_points_spec(d, dad, "DEF") == 6 + 3 + 3 + 10 + 4
    assert compute_points_spec(d | {"points_allowed": 3}, dad, "DEF") == 6 + 3 + 3 + 8 + 4
    assert compute_points_spec(d | {"points_allowed": 4}, dad, "DEF") == 6 + 3 + 3 + 4


def test_70587_distance_without_lengths_is_approximated_and_said(dad):
    # only the 40+ count: the 45-yard TD is exact, the < 40 one splits 0-9 / 10-39 by the placeholder shares
    line = {"rushing_yards": 120, "rushing_tds": 2, "rush_tds_40p": 1, "rush_tds_50p": 0}
    pieces, approx = price_detail(line, dad, "RB")
    assert approx and 6 + 12 <= pieces["distance:rushing_tds"] <= 9 + 12
    # every touchdown 40+: exact again
    pieces, approx = price_detail({"rushing_tds": 1, "rush_tds_40p": 1}, dad, "RB")
    assert not approx and pieces["distance:rushing_tds"] == 12


# ------------------------------------------------------------------ 21861 (full PPR, TE 1.5, FG by the yard)
def test_21861_te_premium_and_fg():
    sp = from_mfl(_rules("21861"))
    te = {"receptions": 6, "receiving_yards": 70, "receiving_tds": 1}
    assert compute_points_spec(te, sp, "TE") == 6 * 1.5 + 7 + 6
    assert compute_points_spec(te, sp, "WR") == 6 + 7 + 6
    k = {"fg_made": 2, "fg_made_20_29": 1, "fg_made_40_49": 1, "pat_made": 2}
    assert compute_points_spec(k, sp, "K") == 3 + 4.45 + 2               # 40-49: 3 + 0.1 x 14.5 (the band's middle)
    assert any("middle of each 10-yard band" in a for a in sp.approximated)
    assert sp.positions["DEF"].bands["points_allowed"][:2] == [(0.0, 0.0, 12.0), (1.0, 6.0, 8.0)]
    flat = flat_from_spec(sp)
    assert flat["rec"] == 1.0 and flat["bonus_rec_te"] == 0.5 and flat["fgm_40_49"] == 4.45


def test_idp_league_reports_unpriced_with_mfl_codes():
    sp = from_mfl(_rules("10015"))
    events = {u["event"] for u in sp.unpriced}
    assert "IDP" in events
    assert all(u["name"] for u in sp.unpriced)


def test_unknown_event_is_unpriced_with_its_name():
    rules = {"positionRules": [{"positions": "WR", "rule": [
        {"event": {"$t": "UY"}, "range": {"$t": "0-999"}, "points": {"$t": "*0.1"}},
        {"event": {"$t": "ZZ"}, "range": {"$t": "0-9"}, "points": {"$t": "1"}},
        {"event": {"$t": "CY"}, "range": {"$t": "0-999"}, "points": {"$t": "*0.1"}}]}]}
    sp = from_mfl(rules)
    assert [(u["event"], u["name"]) for u in sp.unpriced] == [("UY", "punt return yards"), ("ZZ", "ZZ")]
    assert sp.positions["WR"].rates == {"receiving_yards": 0.1}


def test_threshold_points_step():
    # ".1/1" from 30 with thresholdPoints 3: 3 at the range's low, a tenth a yard beyond it
    rules = {"positionRules": {"positions": "RB", "rule": {"event": {"$t": "RY"}, "range": {"$t": "100-999"},
                                                          "points": {"$t": ".1/1"}, "thresholdPoints": {"$t": "5"}}}}
    sp = from_mfl(rules)
    assert compute_points_spec({"rushing_yards": 99}, sp, "RB") == 0
    assert compute_points_spec({"rushing_yards": 100}, sp, "RB") == 5
    assert compute_points_spec({"rushing_yards": 125}, sp, "RB") == 7.5


# ------------------------------------------------------------------ Sleeper: parity with the flat engine
ROWS = [  # tests/test_scoring.py's rows
    ({"rec": 0.5, "rec_yd": 0.1, "rec_td": 6.0, "fum_lost": -2.0},
     {"receptions": 7, "receiving_yards": 105, "receiving_tds": 1, "fumbles_lost_total": 1}),
    ({"fgm_0_19": 3, "fgm_20_29": 3, "fgm_30_39": 3, "fgm_40_49": 4, "fgm_50p": 5, "fgmiss": -1, "xpm": 1, "xpmiss": -1},
     {"fg_made_30_39": 1, "fg_made_40_49": 1, "fg_made_50_59": 1, "fg_made_60_": 1, "fg_missed": 1, "fg_blocked": 1,
      "pat_made": 3, "pat_missed": 0, "pat_blocked": 1}),
    ({"rec_yd": 0.1, "bonus_rec_yd_100": 3.0, "bonus_rec_yd_200": 6.0, "bonus_rush_yd_100": 3.0},
     {"receiving_yards": 210, "rushing_yards": 100}),
    ({"rec_yd": 0.1, "bonus_rec_yd_100": 3.0, "bonus_rec_yd_200": 6.0}, {"receiving_yards": 199}),
    ({"pass_td": 4.0, "pass_td_40p": 2.0, "rec_td": 6.0, "rec_td_40p": 2.0, "rec_td_50p": 1.0},
     {"passing_tds": 3, "pass_tds_40p": 2, "receiving_tds": 1, "rec_tds_40p": 1, "rec_tds_50p": 1}),
    ({"fgmiss_0_19": -2, "fgmiss_20_29": -1, "fgmiss_50p": -0.5, "fgm_50p": 5},
     {"fg_missed_0_19": 1, "fg_missed_20_29": 2, "fg_missed_50_59": 1, "fg_missed_60_": 1, "fg_made_50_59": 1}),
]


@pytest.mark.parametrize("scoring,stats", ROWS)
def test_spec_equals_flat_on_every_test_scoring_row(scoring, stats):
    assert compute_points_spec(stats, from_sleeper(scoring)) == compute_points(stats, scoring)


def _random_line(rng: random.Random, position: str) -> dict:
    tds = {k: rng.choice([0, 0, 0, 1, 1, 2, 3]) for k in ("passing_tds", "rushing_tds", "receiving_tds")}
    line = {"position": position, "passing_yards": rng.choice([0, 0, rng.randint(-5, 450)]),
            "passing_interceptions": rng.randint(0, 3), "passing_2pt_conversions": rng.randint(0, 1),
            "rushing_yards": rng.randint(-10, 230), "rushing_2pt_conversions": rng.randint(0, 1),
            "receptions": rng.randint(0, 12), "receiving_yards": rng.randint(-5, 230),
            "receiving_2pt_conversions": rng.randint(0, 1), "fumbles_total": rng.randint(0, 2),
            "fumbles_lost_total": rng.randint(0, 1), "special_teams_tds": rng.choice([0, 0, 0, 1]),
            "fumble_recovery_tds": rng.choice([0, 0, 0, 1]), **tds}
    for fam, short in (("passing_tds", "pass"), ("rushing_tds", "rush"), ("receiving_tds", "rec")):
        n40 = rng.randint(0, tds[fam])
        line[f"{short}_tds_40p"], line[f"{short}_tds_50p"] = n40, rng.randint(0, n40)
    for c in ("fg_made_0_19", "fg_made_20_29", "fg_made_30_39", "fg_made_40_49", "fg_made_50_59", "fg_made_60_",
              "fg_missed_0_19", "fg_missed_20_29", "fg_missed_30_39", "fg_missed_40_49", "fg_missed_50_59",
              "fg_missed_60_", "pat_made", "pat_missed", "pat_blocked", "fg_blocked"):
        line[c] = rng.choice([0, 0, 1, 2]) if position == "K" else 0
    line["fg_made"] = sum(line[c] for c in line if c.startswith("fg_made_"))
    line["fg_missed"] = sum(line[c] for c in line if c.startswith("fg_missed_"))
    return line


@pytest.mark.parametrize("scoring", [SCRUBS, DYNASTY, TE_PREMIUM], ids=["scrubs", "dynasty", "te_premium"])
def test_house_league_parity_on_2000_random_lines(scoring):
    """The old compute_points (= the SQL macro, tests/test_scoring.py pins that) and the spec agree on every line."""
    rng = random.Random(17)
    sp = from_sleeper(scoring)
    for _ in range(2000):
        line = _random_line(rng, rng.choice(["QB", "RB", "WR", "TE", "K"]))
        assert compute_points_spec(line, sp) == compute_points(line, scoring), line


def test_sleeper_spec_unpriced_and_def():
    sp = from_sleeper(SCRUBS)
    assert {u["event"] for u in sp.unpriced} == {"def_st_ff", "def_st_fum_rec", "st_ff", "st_fum_rec"}
    d = sp.positions["DEF"]
    assert d.rates["sacks"] == 1.0 and d.rates["st_tds"] == 6.0
    assert compute_points_spec({"sacks": 2, "interceptions": 1, "points_allowed": 0}, sp, "DEF") == 2 + 2 + 10
    assert compute_points_spec({"points_allowed": 35}, sp, "DEF") == -4
    assert kd_flat(sp, "DEF") == SCRUBS                     # a Sleeper spec hands kd1.0 its own settings back


def test_te_premium_is_positional():
    sp = from_sleeper(TE_PREMIUM)
    assert sp.positions["TE"].premiums == {"receptions": 0.5} and sp.positions["WR"].premiums == {}
    assert compute_points_spec({"receptions": 4}, sp, "TE") == 6.0
    assert compute_points_spec({"receptions": 4}, sp, "WR") == 4.0
    assert compute_points_spec({"receptions": 4}, sp) == 4.0          # no position: no premium (as the old engine)


def test_json_round_trip(dad):
    for sp in (dad, from_sleeper(DYNASTY), from_mfl(_rules("21861"))):
        back = ScoringSpec.from_json(json.loads(json.dumps(sp.to_json())))
        assert back.to_json() == sp.to_json() and back.key() == sp.key()


def test_readback_in_plain_words(dad):
    rb = dad.readback()
    assert rb[0] == "TDs by distance 6 / 9 / 12" and "1 pt per 10 yards" in rb
    assert "+10 at 75 yards · +10 at 100 yards · +10 at 250 yards" in rb and "INT −3" in rb
    assert "FG by distance 3 / 5 / 10 / 15" in rb
    scrubs = from_sleeper(SCRUBS).readback()
    assert scrubs[0] == "0.5 per catch" and "4-pt pass TD" in scrubs


# ------------------------------------------------------------------ projected lines: expected value
def test_expected_points_pieces(dad):
    line = {"rushing_yards": 57.0, "rushing_tds": 0.5, "receptions": 3.0, "receiving_yards": 20.0}
    per_td = sum(b[2] * S._band_share("rushing_tds", "RB", b) for b in dad.positions["RB"].distance["rushing_tds"])
    if S._EV is None:                                                   # the placeholder shares
        assert per_td == pytest.approx(6 * (1 - 0.35) + 9 * (0.35 - 0.06) + 12 * 0.06)
    assert 6 < per_td < 9
    lin = expected_points(line, dad, "RB", ev=False)
    assert lin == pytest.approx(5.7 + 2.0 + 0.5 * per_td, abs=0.01)     # linear: 57 yards price 5.7, no catches
    ev = expected_points(line, dad, "RB", ev=True)
    bonus = 10 * float(S.prob_at_least("rushing_yards", "RB", 57.0, 100)) + 10 * float(S.prob_at_least("receiving_yards", "RB", 20.0, 100))
    floor_cost = (lin - (ev - bonus))                                   # the whole-tens expectation is below linear
    assert 0.2 < floor_cost < 1.5


def test_expected_band_probability_is_monotone_and_bounded(dad):
    means = np.arange(0, 200, 5.0)
    df = pd.DataFrame({"rushing_yards": means})
    only = ScoringSpec(positions={"RB": S.Rules(bands={"rushing_yards": dad.positions["RB"].bands["rushing_yards"]})},
                       source="mfl")
    bonus = expected_frame(df, only, ["RB"] * len(means), ev=True)
    assert (expected_frame(df, only, ["RB"] * len(means), ev=False) == (means >= 100) * 10).all()
    assert np.all(np.diff(bonus) >= -0.011) and bonus.min() >= 0 and bonus.max() <= 10
    assert 3 < bonus[means == 100][0] < 7                    # at the threshold, roughly a coin flip


def test_prob_at_least_fallback_is_marked():
    assert S._EV is None or hasattr(S._EV, "prob_at_least")
    p = S.prob_at_least("receiving_yards", "WR", np.array([50.0, 100.0, 150.0]), 100)
    assert 0 < p[0] < p[1] < p[2] < 1


def test_expected_frame_matches_expected_points_row_by_row(dad):
    rng = random.Random(3)
    rows = [{"position": rng.choice(["QB", "RB", "WR", "TE", "TMQB"]), "passing_yards": rng.uniform(0, 320),
             "passing_tds": rng.uniform(0, 2.5), "rushing_yards": rng.uniform(0, 110), "rushing_tds": rng.uniform(0, 1),
             "receiving_yards": rng.uniform(0, 110), "receiving_tds": rng.uniform(0, 1), "receptions": rng.uniform(0, 8),
             "passing_interceptions": rng.uniform(0, 1.2), "fumbles_lost_total": rng.uniform(0, 0.3)} for _ in range(50)]
    df = pd.DataFrame(rows)
    frame = expected_frame(df, dad, df["position"].to_numpy(), ev=True)
    for i, r in enumerate(rows):
        assert frame[i] == pytest.approx(expected_points(r, dad, r["position"], ev=True), abs=0.011)


def test_kd_flat_for_mfl(dad):
    k = kd_flat(dad, "K")
    assert (k["fgm_0_19"], k["fgm_30_39"], k["fgm_40_49"], k["fgm_50p"], k["xpm"]) == (3.0, 3.0, 5.0, 10.0, 1.0)
    d = kd_flat(dad, "DEF")
    assert d["sack"] == 2 and d["int"] == 3 and d["fum_rec"] == 3 and d["safe"] == 4
    assert d["pts_allow_0"] == 10 and d["pts_allow_1_6"] == 4.0          # 1-3 -> 8 averaged over 1-6
    assert 6 < d["def_td"] < 12                                         # a defensive TD at its expected distance


def test_fallback_path_without_m2(monkeypatch, dad):
    """The marked fallback (M2's scoring_ev absent): the placeholder shares and the normal spread."""
    monkeypatch.setattr(S, "_EV", None)
    per_td = sum(b[2] * S._band_share("rushing_tds", "RB", b) for b in dad.positions["RB"].distance["rushing_tds"])
    assert per_td == pytest.approx(6 * (1 - 0.35) + 9 * (0.35 - 0.06) + 12 * 0.06)
    p = S.prob_at_least("rushing_yards", "RB", np.array([0.0, 99.5]), 100)
    assert p[0] == 0 and p[1] == pytest.approx(0.5)
    floor = S.expected_floor_units("rushing_yards", "RB", np.array([57.0]), 10.0)
    assert 4.7 < floor[0] < 5.7                              # below linear 5.7: whole tens only


def test_ten_yard_cut_makes_the_split_exact(dad):
    line = {"rushing_tds": 3, "rush_tds_10p": 2, "rush_tds_40p": 1, "rush_tds_50p": 0}
    pieces, approx = price_detail(line, dad, "RB")
    assert not approx and pieces["distance:rushing_tds"] == 6 + 9 + 12


def test_sleeper_keys_beyond_the_flat_engine_are_priced_on_actual_lines():
    sc = {"pass_cmp": 0.1, "pass_inc": -0.5, "rush_att": 0.1, "rec_fd": 0.5, "bonus_pass_cmp_25": 2.0,
          "bonus_rush_rec_yd_100": 3.0, "tkl": 1.0}
    sp = from_sleeper(sc)
    line = {"completions": 26, "attempts": 36, "carries": 4, "receiving_first_downs": 2}
    assert compute_points_spec(line, sp, "QB") == pytest.approx(2.6 - 5.0 + 0.4 + 1.0 + 2.0)
    assert compute_points(line, sc) == 0                           # the flat engine (and the SQL macro) price none
    assert {u["event"] for u in sp.unpriced} == {"bonus_rush_rec_yd_100", "tkl"}
