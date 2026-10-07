"""Wave I-P (IP-1): the quarterback weak spot -- the analysis tools that reproduce docs/METRICS.md § "The quarterback weak
spot (IP-1)" and the candidates' pieces, on hand-built rows (no database).

* ``guarded_listing`` (st1.0's as-of rule, the twin of ``int_pn_team_game`` under ``pn_starter_from_play``): a listing
  that repeats one the team's newest played game contradicted reads that game's real starter; a changed listing, a
  listing that was right, the first week and a new season read the listing as it is.
* ``rush_td_scale`` (rt1.0): k = sum of actual / sum of projected rushing TDs over the 3 seasons before, clipped.
* ``paired`` + ``experiments.decide``: a candidate uniformly better reads keep, one uniformly worse reads hurts / drop.
* ``cluster_boot``: whole players are resampled (a player's weeks move together), the interval holds the mean.
* ``team_game_frame``: a new head coach is flagged against the team's previous season's last coach (unknown in a
  team's first season of data).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from league_lab import experiments as E
from league_lab import projections as P

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "analysis"))
import ip1_qb_candidates as K  # noqa: E402
import ip1_qb_diagnosis as D  # noqa: E402


def tg(rows):
    """team-weeks: (team, season, week, listed, real starter or None when unplayed)."""
    return pd.DataFrame([{"team": t, "season": s, "week": w, "listed_qb_id": lst, "starting_qb_id": real if real else lst,
                          "is_played": real is not None} for t, s, w, lst, real in rows])


def guard_of(frame):
    g = K.guarded_listing(frame)
    return dict(zip(zip(g["team"], g["season"], g["week"], strict=True), g["guard_qb_id"], strict=True))


def test_guard_reads_the_real_starter_when_a_contradicted_listing_repeats():
    # SEA 2026: Lock listed for weeks 3-5, Darnold threw every pass in weeks 3 and 4
    g = guard_of(tg([("SEA", 2026, 1, "darnold", "darnold"), ("SEA", 2026, 2, "lock", "lock"),
                     ("SEA", 2026, 3, "lock", "darnold"), ("SEA", 2026, 4, "lock", "darnold"), ("SEA", 2026, 5, "lock", None)]))
    assert g[("SEA", 2026, 3)] == "lock"            # week 3: nothing before it said the listing was wrong
    assert g[("SEA", 2026, 4)] == "darnold"         # week 4: week 3's listing (Lock) was contradicted and repeats
    assert g[("SEA", 2026, 5)] == "darnold"         # the unplayed week: the board's input


def test_guard_keeps_a_changed_or_a_right_listing_and_never_crosses_seasons():
    g = guard_of(tg([("PIT", 2022, 14, "pickett", "trubisky"), ("PIT", 2022, 15, "trubisky", "trubisky"),
                     ("WAS", 2024, 17, "mariota", "daniels"), ("WAS", 2025, 1, "mariota", "daniels"),
                     ("BUF", 2025, 1, "allen", "allen"), ("BUF", 2025, 2, "allen", "allen")]))
    assert g[("PIT", 2022, 15)] == "trubisky"       # the listing changed: read as it is
    assert g[("WAS", 2025, 1)] == "mariota"         # a new season starts clean (the dbt window is per season too)
    assert g[("BUF", 2025, 2)] == "allen"           # a listing that was right


def test_guard_misfires_on_a_returning_starter_as_measured():
    # the case that cost st1.0 its keep: the listed starter missed a game hurt, then returned
    g = guard_of(tg([("PIT", 2022, 15, "pickett", "trubisky"), ("PIT", 2022, 16, "pickett", "pickett")]))
    assert g[("PIT", 2022, 16)] == "trubisky"


def qb_rows(seasons, proj=0.1, act=0.15, n=10):
    return pd.DataFrame([{"season": s, "played": True, "out_rushing_tds": act, "v3_rushing_tds": proj}
                         for s in seasons for _ in range(n)])


def test_rush_td_scale_is_mean_unbiased_on_the_three_seasons_before_and_clipped():
    rows = pd.concat([qb_rows([2019], proj=0.1, act=0.5), qb_rows([2020, 2021, 2022], proj=0.1, act=0.12)])
    k, n = K.rush_td_scale(rows, 2023)
    assert k == pytest.approx(1.2) and n == 30       # 2019 is outside the window
    k, _ = K.rush_td_scale(rows, 2020)               # only 2019 (5x) -> the clip
    assert k == K.RT_BOUNDS[1]


def priced_rows(seasons, delta, leagues=("a", "b"), weeks=3, players=9, seed=0):
    rng = np.random.default_rng(seed)
    out = []
    for lid in leagues:
        for s in seasons:
            for w in range(1, weeks + 1):
                for i in range(players):
                    a = float(rng.normal(15, 6))
                    out.append({"league_id": lid, "gsis_id": f"p{i}", "season": s, "week": w,
                                "proj": a + rng.normal(0, 5) + delta, "actual": a})
    return pd.DataFrame(out)


def test_paired_feeds_decide_season_by_season():
    base = priced_rows([2021, 2022, 2023, 2024, 2025], 2.0)
    better = base.assign(proj=base["proj"] - 1.0)      # every projection 1 point nearer the actual (bias 2 -> 1)
    per = K.paired(base, better)
    assert list(per["season"]) == [2021, 2022, 2023, 2024, 2025]
    assert (per["delta_mae"] < 0).all()
    assert E.decide(per)["decision"].iloc[0] == "keep"
    worse = base.assign(proj=base["proj"] + 1.0)
    d = E.decide(K.paired(base, worse)).iloc[0]
    assert d["hurts"] and d["decision"] == "drop"


def test_weekly_needs_eight_players():
    p = priced_rows([2021], 0.0, leagues=("a",), weeks=1, players=7)
    assert K.weekly(p).empty


def test_cluster_boot_resamples_whole_players():
    err = np.array([1.0, 1.0, 1.0, 5.0, 5.0, 5.0])
    groups = np.array(["a", "a", "a", "b", "b", "b"])
    lo, hi = D.cluster_boot(err, groups, n=500)
    assert lo == pytest.approx(1.0) and hi == pytest.approx(5.0)     # all-a or all-b draws exist; never a mix inside a player
    same = D.cluster_boot(np.full(10, 2.5), np.arange(10).astype(str), n=200)
    assert same == (pytest.approx(2.5), pytest.approx(2.5))


def test_new_coach_against_last_seasons_last_coach():
    games = pd.DataFrame([
        {"game_id": "g1", "season": 2024, "week": 1, "home_team": "CHI", "away_team": "GB", "home_score": 20, "away_score": 17,
         "home_qb_id": "q1", "away_qb_id": "q2", "home_coach": "Eberflus", "away_coach": "LaFleur"},
        {"game_id": "g2", "season": 2024, "week": 12, "home_team": "GB", "away_team": "CHI", "home_score": 24, "away_score": 10,
         "home_qb_id": "q2", "away_qb_id": "q1", "home_coach": "LaFleur", "away_coach": "Brown"},
        {"game_id": "g3", "season": 2025, "week": 1, "home_team": "CHI", "away_team": "GB", "home_score": 21, "away_score": 27,
         "home_qb_id": "q1", "away_qb_id": "q2", "home_coach": "Johnson", "away_coach": "LaFleur"},
    ])
    t = D.team_game_frame(games).set_index(["team", "season", "week"])
    assert t.loc[("CHI", 2025, 1), "new_coach"] == 1.0          # Brown finished 2024, Johnson starts 2025
    assert t.loc[("GB", 2025, 1), "new_coach"] == 0.0
    assert np.isnan(t.loc[("CHI", 2024, 1), "new_coach"])       # no previous season in the data: unknown, not 0
    assert t.loc[("GB", 2024, 12), "pts"] == 24 and t.loc[("CHI", 2024, 12), "opp_pts"] == 24


def test_the_component_table_carries_the_line():
    d = pd.DataFrame({"actual": [20.0, 10.0], "x_points": [15.0, 12.0], **{f"out_{c}": [0.0, 0.0] for c in P.ALL_COMPONENTS},
                      **{f"x_{c}": [0.0, 0.0] for c in P.ALL_COMPONENTS}})
    d.loc[0, "out_passing_tds"], d.loc[0, "x_passing_tds"] = 2.0, 1.0      # +4 points of the +5 miss on row 0
    t = D.component_table(d, "x_", {"pass_td": 4.0, "pass_yd": 0.04}, ["passing_tds"], "hand-built")
    line = t[t["component"] == "**the line**"].iloc[0]
    assert line["bias (pts)"] == "+1.50" and line["MAE (pts)"] == "3.50"
    tds = t[t["component"] == "Passing TDs"].iloc[0]
    assert tds["bias (pts)"] == "+2.00" and tds["line's MAE if it were exact"].startswith("1.50")


def test_model_versions_compare_by_number_in_the_marts():
    """The review's L4: the drift and the backtest's ``is_current`` order model versions by their numbers ('v3.10' after
    'v3.9'), never as text; dbt's assert_model_versions_compare_by_number checks the macro on the database."""
    root = Path(__file__).resolve().parents[1]
    macro = (root / "dbt" / "macros" / "version_key.sql").read_text()
    assert "macro version_key" in macro and "::int[]" in macro
    for name in ("mart_projection_drift.sql", "mart_projection_backtest.sql"):
        sql = (root / "dbt" / "models" / "marts" / "nfl" / name).read_text()
        code = "\n".join(line.split("--")[0] for line in sql.splitlines())      # comments may say what text did
        assert "version_key(" in code, name
        assert "max(model_version)" not in code and "max(backtest_model_version)" not in code, name
        assert "model_version <=" not in code and "order by b.model_version desc" not in code, name
    assert "v3.10" < "v3.9"                                                       # why: as text, v3.10 sorts first
