"""IL-3: the grading harness for the week's win probability and the ranges (league_lab.odds_grade), on synthetic record
rows with known answers. No database."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from league_lab import odds_grade as G

LG = "111"


def _matchups(ps, ys, league=LG, week=1):
    return pd.DataFrame({"league_id": league, "week": week, "p": ps, "outcome": ys})


def _starters(rows, league=LG, week=1):
    df = pd.DataFrame(rows)
    for c in ("p10", "p25", "p50", "p75", "p90", "value", "actual"):
        if c not in df:
            df[c] = np.nan
    return df.assign(league_id=league, week=week)


def test_a_perfectly_calibrated_coin_flip_scores_a_quarter():
    """100 matchups at p = 0.5, half won: Brier 0.25, log loss ln 2, the calibration table one decile at 50% / 50%,
    no favourite."""
    ps, ys = [0.5] * 100, [1.0, 0.0] * 50
    assert G.brier(ps, ys) == pytest.approx(0.25)
    assert G.log_loss(ps, ys) == pytest.approx(math.log(2))
    table, ece = G.calibration_deciles(ps, ys)
    assert [(d["lo"], d["n"], d["predicted"], d["observed"]) for d in table] == [(0.5, 200, 0.5, 0.5)]
    assert ece == pytest.approx(0.0)
    assert G.favourite(ps, ys) == (None, None, 0)


def test_a_calibrated_favourite_at_seventy_percent():
    """p = 0.7, 7 of 10 won: Brier 0.7·0.3² + 0.3·0.7² = 0.21; the favourite predicted 70% and won 70%; the deciles
    (both sides) 30% → 30% and 70% → 70%."""
    ps, ys = [0.7] * 10, [1.0] * 7 + [0.0] * 3
    assert G.brier(ps, ys) == pytest.approx(0.21)
    assert G.favourite(ps, ys) == (pytest.approx(0.7), pytest.approx(0.7), 10)
    table, ece = G.calibration_deciles(ps, ys)
    assert [(d["decile"], d["n"], d["predicted"], d["observed"]) for d in table] == [(4, 10, 0.3, 0.3), (8, 10, 0.7, 0.7)]
    assert ece == pytest.approx(0.0)
    # the same set read from the underdog's side scores the same
    assert G.brier([0.3] * 10, [0.0] * 7 + [1.0] * 3) == pytest.approx(0.21)


def test_an_overconfident_set_shows_in_the_table():
    ps, ys = [0.9] * 10, [1.0] * 5 + [0.0] * 5
    table, ece = G.calibration_deciles(ps, ys, both_sides=False)
    assert table == [{"decile": 10, "lo": 0.9, "hi": 1.0, "n": 10, "predicted": 0.9, "observed": 0.5}]
    assert ece == pytest.approx(0.4)
    assert G.brier(ps, ys) == pytest.approx(0.5 * 0.01 + 0.5 * 0.81)
    assert G.log_loss([1.0], [0.0]) == pytest.approx(-math.log(G.EPS))       # clipped, never infinite


def test_a_fifty_percent_range_built_to_cover_half_does():
    """P25–P75 = 0–10 and P10–P90 = 0–20; the points alternate 5 (inside both) / 15 (inside the 80% only), and two in
    ten fall outside both: the 50% range covers half, the 80% range 80%."""
    actual = [5, 15, 5, 15, 5, 15, 5, 15, 25, 30]
    s = _starters([{"position": "WR", "p10": 0, "p25": 0, "p50": 5, "p75": 10, "p90": 20, "value": 6, "actual": a}
                   for a in actual])
    c50, n50 = G.coverage(s["actual"], s["p25"], s["p75"])
    c80, n80 = G.coverage(s["actual"], s["p10"], s["p90"])
    assert (c50, n50) == (0.4, 10)            # 4 at 5 inside, 4 at 15 outside, 25 / 30 outside
    assert (c80, n80) == (0.8, 10)
    exact = _starters([{"position": "WR", "p25": 0, "p75": 10, "actual": a} for a in (5, 15) * 5])
    assert G.coverage(exact["actual"], exact["p25"], exact["p75"]) == (0.5, 10)


def test_the_fifty_percent_range_only_where_the_row_carries_it():
    """Weeks 1–3 have three knots: P25 / P75 NaN. Those rows count for the 80% range and not for the 50% one."""
    s = _starters([{"position": "RB", "p10": 0, "p50": 8, "p90": 20, "value": 9, "actual": 7},
                   {"position": "RB", "p10": 0, "p25": 4, "p50": 8, "p75": 12, "p90": 20, "value": 9, "actual": 13}])
    g = G.grade_rows(pd.DataFrame(columns=["league_id", "week", "p", "outcome"]), s, 2026)
    wk = g[g["scope"] == "week"].set_index("metric")
    assert wk.loc["coverage_80", "value"] == 1.0 and wk.loc["coverage_80", "n"] == 2
    assert wk.loc["coverage_50", "value"] == 0.0 and wk.loc["coverage_50", "n"] == 1
    assert wk.loc["mae_median_RB", "value"] == pytest.approx((1 + 5) / 2)      # |8-7|, |8-13|
    assert wk.loc["mae_projection_RB", "value"] == pytest.approx((2 + 4) / 2)  # |9-7|, |9-13|


def test_a_starter_without_a_range_is_graded_at_his_value():
    s = _starters([{"position": "DEF", "value": 7.0, "actual": 10.0},
                   {"position": "K", "p10": 2, "p50": 7, "p90": 12, "value": 8.0, "actual": 9.0}])
    g = G.grade_rows(pd.DataFrame(columns=["league_id", "week", "p", "outcome"]), s, 2026)
    wk = g[g["scope"] == "week"].set_index("metric")
    assert wk.loc["mae_median_DEF", "value"] == pytest.approx(3.0)
    assert wk.loc["mae_median_K", "value"] == pytest.approx(2.0)
    assert wk.loc["coverage_80", "n"] == 1                                    # the DEF has no range: not counted


def test_unknown_points_are_left_out_never_zero():
    s = _starters([{"position": "WR", "p10": 0, "p50": 5, "p90": 20, "value": 6, "actual": np.nan},
                   {"position": "WR", "p10": 0, "p50": 5, "p90": 20, "value": 6, "actual": 4}])
    g = G.grade_rows(pd.DataFrame(columns=["league_id", "week", "p", "outcome"]), s, 2026)
    wk = g[g["scope"] == "week"].set_index("metric")
    assert wk.loc["coverage_80", "n"] == 1 and wk.loc["mae_median_WR", "n"] == 1


def test_grade_rows_scopes_week_league_to_date_and_all():
    m = pd.concat([_matchups([0.5, 0.5], [1.0, 0.0], LG, 1), _matchups([0.7], [1.0], LG, 2),
                   _matchups([0.6], [0.0], "222", 1)], ignore_index=True)
    s = pd.concat([_starters([{"position": "QB", "p10": 10, "p50": 18, "p90": 30, "value": 19, "actual": 20}], LG, 1),
                   _starters([{"position": "QB", "p10": 10, "p50": 18, "p90": 30, "value": 19, "actual": 35}], "222", 1)],
                  ignore_index=True)
    g = G.grade_rows(m, s, 2026)
    key = g.set_index(["league_id", "scope", "week", "metric"])
    assert key.loc[(LG, "week", 1, "brier"), "value"] == pytest.approx(0.25)
    assert key.loc[(LG, "week", 2, "brier"), "value"] == pytest.approx(0.09)
    assert key.loc[(LG, "to_date", 2, "brier"), "value"] == pytest.approx((0.25 + 0.25 + 0.09) / 3)
    assert key.loc[(LG, "to_date", 2, "brier"), "n"] == 3
    assert key.loc[("222", "to_date", 1, "brier"), "value"] == pytest.approx(0.36)
    assert key.loc[("all", "to_date", 2, "brier"), "value"] == pytest.approx((0.25 + 0.25 + 0.09 + 0.36) / 4)
    assert key.loc[("all", "to_date", 2, "coverage_80"), "value"] == 0.5
    assert key.loc[("all", "to_date", 2, "calibration"), "n"] == 8            # both sides of 4 matchups
    assert ("all", "week", 2, "brier") not in key.index                       # the pooled rows are season to date only
    assert set(g["through_week"][g["league_id"] == "all"]) == {2}
    assert (g["metric"] == "calibration").sum() == 3                          # to date only: two leagues + all


def _frames(result="W", scored=True):
    """Two rosters with identical lineups (the same players' ranges on both sides under different keys), one scored
    matchup and one unscored week."""
    rec, rng, teams, weekly = [], [], [], []
    for roster in (1, 2):
        for i, pos in enumerate(("QB", "WR")):
            gid = f"00-{roster}{i}"
            for week in (1, 2):
                rec.append({"league_id": LG, "season": 2026, "week": week, "roster_id": roster, "record_source": "reconstructed",
                            "gsis_id": gid, "sleeper_player_id": f"s{roster}{i}", "player_name": gid, "position": pos,
                            "value": 15.0, "pricing": "flat"})
                rng.append({"league_id": LG, "week": week, "gsis_id": gid, "proj_points": 15.0, "p10": 5.0, "p25": np.nan,
                            "p50": 15.0, "p75": np.nan, "p90": 25.0})
                teams.append({"league_id": LG, "week": week, "gsis_id": gid, "sleeper_player_id": f"s{roster}{i}",
                              "team": f"T{roster}{i}", "opponent": f"O{roster}{i}"})
                weekly.append({"league_id": LG, "week": week, "roster_id": roster, "sleeper_player_id": f"s{roster}{i}",
                               "gsis_id": gid, "is_starter": True, "points_observed": 20.0 if roster == 1 else 10.0,
                               "is_scored_week": scored if week == 1 else False})
    return {"record": pd.DataFrame(rec), "ranges": pd.DataFrame(rng), "teams": pd.DataFrame(teams),
            "matchups": pd.DataFrame([{"league_id": LG, "week": w, "roster_id": 1, "opponent_roster_id": 2, "result": result}
                                      for w in (1, 2)]),
            "weekly": pd.DataFrame(weekly), "fallback": pd.DataFrame(columns=["league_id", "week", "gsis_id", "points"])}


def test_build_inputs_identical_lineups_are_a_coin_flip_and_only_scored_weeks_count():
    m, s = G.build_inputs(_frames(), draws=4000)
    assert list(m["week"]) == [1]                                             # week 2 is not scored: not graded
    assert m["p"].iloc[0] == pytest.approx(0.5, abs=0.02)
    assert m["outcome"].iloc[0] == 1.0
    assert set(s["week"]) == {1} and len(s) == 4
    assert sorted(s["actual"]) == [10.0, 10.0, 20.0, 20.0]
    g = G.grade_rows(m, s, 2026)
    b = g[(g["league_id"] == "all") & (g["metric"] == "brier")]["value"].iloc[0]
    assert b == pytest.approx(0.25, abs=0.02)
    assert g[(g["league_id"] == "all") & (g["metric"] == "coverage_80")]["value"].iloc[0] == 1.0
    assert (g["metric"] == "coverage_50").sum() == 0                          # no five-knot range on these rows


def test_nothing_scored_grades_nothing():
    m, s = G.build_inputs(_frames(scored=False), draws=1000)
    assert m.empty and s.empty
    assert G.grade_rows(m, s, 2026).empty


def test_outcome_words():
    assert [G.outcome(x) for x in ("W", "L", "T", None, "?")] == [1.0, 0.0, 0.5, None, None]


def test_status_reads_the_newest_pooled_rows():
    at = pd.Timestamp("2026-10-05T16:30:00Z")
    rows = pd.DataFrame({"season": 2026, "week": 3, "metric": ["brier", "coverage_80", "coverage_50", "log_loss"],
                         "value": [0.2412, 0.79, 0.51, 0.69], "n": [33, 500, 120, 33], "graded_at": at})

    def q(sql, params=()):
        return pd.DataFrame({"t": ["analytics.odds_grades"]}) if "to_regclass" in sql else rows

    assert G.status(q) == {"season": 2026, "through_week": 3, "brier": 0.2412, "coverage_50": 0.51, "coverage_80": 0.79,
                           "graded_at": "2026-10-05T16:30:00+00:00"}
    assert G.status(lambda sql, params=(): pd.DataFrame({"t": [None]})) is None
    assert G.status(lambda sql, params=(): pd.DataFrame({"t": ["x"]}) if "to_regclass" in sql
                    else rows.iloc[0:0]) is None
