"""IZ-1 (Wave I-Z): hh1.0's grade and bl1.0's blend on constructed cases with known answers (no database).

docs/METRICS.md § "Us against Sleeper on the weeks Sleeper still serves" is the rule; these cases check the code says
what the rule says: the measures, the start / sit pairs, the verdict words, the blend's fit on earlier seasons only.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from league_lab import h2h
from league_lab.config import PROJECT_ROOT
from league_lab.ingest import sleeper_projections as sp

LOS, DYN = "1389709692405551104", "1321941740235550720"
LEAGUES = {LOS: "League of Scrubs", DYN: "Forever Unclean Dynasty"}


def population(ours_noise: float, sleeper_noise: float, seasons=(2023, 2024, 2025), weeks=range(1, 19), n=40,
               seed=1, leagues=(LOS,), positions=("RB",)) -> pd.DataFrame:
    """Actual points per player-week; each side = actual + its own noise (the smaller noise is the better side)."""
    rng = np.random.default_rng(seed)
    rows = []
    for lid in leagues:
        for s in seasons:
            for w in weeks:
                for pos in positions:
                    act = rng.gamma(2.0, 5.0, n)
                    o = act + rng.normal(0, ours_noise, n)
                    sl = act + rng.normal(0, sleeper_noise, n)
                    for i in range(n):
                        rows.append({"league_id": lid, "season": s, "week": w, "position": pos, "gsis_id": f"00-{i:04d}",
                                     "ours": round(o[i], 2), "sleeper": round(sl[i], 2), "actual": round(act[i], 2),
                                     "ours_source": "live_walk_forward", "ours_version": "v3.6"})
    return pd.DataFrame(rows)


def inputs(pop: pd.DataFrame) -> h2h.Inputs:
    return h2h.Inputs(pop, {k: v for k, v in LEAGUES.items() if k in set(pop["league_id"])}, {"lines": 1, "matched": 1})


def pooled(df: pd.DataFrame, kind: str, measure: str, pos: str = "RB", lid: str = LOS) -> pd.Series:
    r = df[(df["league_id"] == lid) & (df["position"] == pos) & df["season"].isna() & (df["kind"] == kind)
           & (df["measure"] == measure)]
    assert len(r) == 1, (kind, measure, len(r))
    return r.iloc[0]


# ------------------------------------------------------------------------------ the measures
def test_spearman_uses_average_ranks_and_needs_eight_players():
    a = np.array([1, 2, 3, 4, 5, 6, 7, 8.0])
    assert h2h.spearman(a, a * 3) == pytest.approx(1.0)
    assert h2h.spearman(a, -a) == pytest.approx(-1.0)
    assert np.isnan(h2h.spearman(a[:7], a[:7]))
    tied = np.array([1, 1, 2, 3, 4, 5, 6, 7.0])
    assert h2h.spearman(tied, a) == pytest.approx(pd.Series(tied).rank().corr(pd.Series(a).rank()))


def test_hit_rate_is_the_records_top_n():
    proj = np.arange(10, 0, -1.0)                          # ranks players 0..9
    actual = np.array([10, 9, 1, 1, 1, 1, 1, 1, 1, 8.0])   # top 3 by actual: 0, 1, 9
    ids = np.array([f"p{i}" for i in range(10)])
    assert h2h.hit_rate(proj, actual, ids, 3) == pytest.approx(2 / 3)


def test_pairs_known_answer():
    # four players; ours ranks A > B > C > D, Sleeper ranks B > A and D > C; actual: B 20, A 10, C 5, D 5
    ours = np.array([10.0, 9.0, 5.0, 4.0])
    slp = np.array([9.0, 10.0, 4.0, 5.0])
    act = np.array([10.0, 20.0, 5.0, 5.0])
    c = h2h.pair_counts(ours, slp, act)
    # close disagreements: (A, B) within 3 and swapped, actual B -> Sleeper right; (C, D) within 3 and swapped, a push
    assert c["close_n"] == 1 and c["close_ours"] == 0 and c["close_push"] == 1
    # all pairs with different actuals: 5 (C-D is a push); ours right on A>C, A>D, B>C, B>D = 4; Sleeper on all 5
    assert c["all_n"] == 5 and c["all_ours"] == 4 and c["all_sleeper"] == 5


def test_a_tie_in_a_projection_is_not_a_disagreement_and_counts_half():
    c = h2h.pair_counts(np.array([5.0, 5.0]), np.array([6.0, 5.0]), np.array([9.0, 1.0]))
    assert c["close_n"] == 0 and c["all_ours"] == 0.5 and c["all_sleeper"] == 1


def test_startable_is_top_n_by_either_side():
    o = np.array([9.0, 8, 1, 0])
    s = np.array([0.0, 1, 9, 8])
    ids = np.array(["a", "b", "c", "d"])
    assert h2h.startable_mask(o, s, ids, 1).tolist() == [True, False, True, False]


@pytest.mark.parametrize("lo,hi,low,expected", [(-0.3, -0.1, True, "ahead"), (0.1, 0.3, True, "behind"),
                                                (-0.1, 0.1, True, "level"), (0.01, 0.2, False, "ahead"),
                                                (-0.2, -0.01, False, "behind"), (0.0, 0.0, False, "level")])
def test_the_words(lo, hi, low, expected):
    assert h2h.word(lo, hi, low) == expected


@pytest.mark.parametrize("e,o,expected", [("ahead", "level", "ahead"), ("level", "behind", "behind"),
                                          ("ahead", "behind", "level"), ("level", "level", "level"),
                                          (None, "ahead", "ahead"), (None, None, None)])
def test_the_positions_one_word(e, o, expected):
    assert h2h.headline_word(e, o) == expected


# ------------------------------------------------------------------------------ the grade on known answers
def test_the_better_side_is_ahead_the_worse_behind_and_identical_is_level():
    df = h2h.grade(inputs(population(ours_noise=2.0, sleeper_noise=6.0)))
    e, o, v = pooled(df, "position", "error"), pooled(df, "position", "order"), pooled(df, "position", "verdict")
    assert e["ours"] < e["sleeper"] and e["diff_hi"] < 0 and e["verdict"] == "ahead"
    assert o["diff_lo"] > 0 and o["verdict"] == "ahead" and v["verdict"] == "ahead"
    assert e["n_weeks"] == 54 and e["n_rows"] == 54 * 40
    cc = pooled(df, "close_calls", "share")
    assert cc["ours"] > 0.5 and cc["verdict"] == "ahead" and cc["ours"] + cc["sleeper"] == pytest.approx(1)
    assert pooled(df, "startable_pairs", "share")["verdict"] == "ahead"
    seasons = df[(df["kind"] == "position") & (df["measure"] == "verdict") & df["season"].notna()]
    assert sorted(seasons["season"].astype(int)) == [2023, 2024, 2025] and set(seasons["verdict"]) == {"ahead"}

    behind = h2h.grade(inputs(population(ours_noise=6.0, sleeper_noise=2.0)))
    assert pooled(behind, "position", "verdict")["verdict"] == "behind"
    assert pooled(behind, "close_calls", "share")["verdict"] == "behind"

    pop = population(ours_noise=3.0, sleeper_noise=3.0)
    pop["sleeper"] = pop["ours"]
    same = h2h.grade(inputs(pop))
    assert pooled(same, "position", "verdict")["verdict"] == "level"
    assert pooled(same, "position", "error")["diff"] == 0
    assert pooled(same, "close_calls", "share")["n_rows"] == 0          # they never disagree


def test_the_interval_is_from_resampling_weeks_and_is_reproducible():
    pop = population(ours_noise=3.0, sleeper_noise=3.2, seed=7)
    a, b = h2h.grade(inputs(pop)), h2h.grade(inputs(pop))
    ea, eb = pooled(a, "position", "error"), pooled(b, "position", "error")
    assert ea["diff_lo"] == eb["diff_lo"] and ea["diff_hi"] == eb["diff_hi"]
    assert ea["diff_lo"] <= ea["diff"] <= ea["diff_hi"]
    wk = h2h.weekly(pop)
    assert ea["diff"] == pytest.approx((wk["mae_o"] - wk["mae_s"]).mean())


def test_both_house_scorings_are_graded_and_the_headline_is_the_first():
    df = h2h.grade(inputs(population(2.0, 6.0, leagues=(LOS, DYN), seasons=(2024,), weeks=range(1, 6))))
    assert set(df["league_id"]) == {LOS, DYN}
    assert set(df.loc[df["headline"], "league_id"]) == {LOS}


def test_nothing_graded_is_an_empty_table():
    assert h2h.grade(h2h.Inputs(pd.DataFrame(), LEAGUES, {})).empty


# ------------------------------------------------------------------------------ the blend (bl1.0): fitted on earlier seasons only
def test_the_blend_leans_on_the_better_side_and_says_gains_only_by_the_rule():
    pop = population(ours_noise=6.0, sleeper_noise=1.0)
    df = h2h.grade(inputs(pop))
    b = df[(df["kind"] == "blend") & (df["measure"] == "error")]
    assert sorted(b["season"].astype(int)) == [2024, 2025]
    assert (b["w"] >= 0.8).all() and (b["blend"] < 0.99 * b["ours"]).all()
    assert pooled(df, "blend", "verdict")["verdict"] == "gains"
    useless = population(ours_noise=1.0, sleeper_noise=8.0, seed=3)
    df2 = h2h.grade(inputs(useless))
    assert pooled(df2, "blend", "verdict")["verdict"] == "no gain"


def test_the_blend_weight_never_sees_the_test_season():
    pop = population(ours_noise=3.0, sleeper_noise=3.0, seed=5)
    test = pop["season"] == 2025
    pop.loc[test, "sleeper"] = pop.loc[test, "actual"]          # Sleeper perfect only in the test season
    df = h2h.grade(inputs(pop))
    w2025 = df[(df["kind"] == "blend") & (df["measure"] == "error") & (df["season"] == 2025)]["w"].iloc[0]
    assert w2025 <= 0.7                                          # fitted on 2023-2024, where neither side is better
    assert h2h.fit_w(pop[pop["season"] == 2025]) == 1.0           # (fitted on the test season it would be 1)


def test_kickoff_board_weeks_are_graded_but_not_in_the_blend():
    pop = population(2.0, 6.0, seasons=(2024, 2025, 2026), weeks=range(1, 5))
    pop.loc[pop["season"] == 2026, "ours_source"] = "kickoff_board"
    df = h2h.grade(inputs(pop))
    assert 2026 in set(df.loc[(df["kind"] == "position"), "season"].dropna().astype(int))
    assert set(df.loc[df["kind"] == "blend", "season"].dropna().astype(int)) <= {2024, 2025}
    assert pooled(df, "position", "error")["ours_source"] == "live_walk_forward"


# ------------------------------------------------------------------------------ pricing and the summary
def test_sleepers_line_is_priced_like_the_record():
    payload = json.loads((Path(__file__).parent / "fixtures" / "sleeper_projections" / "projections_2026_w04.json").read_text())
    rows = [r for r in sp.projection_rows(payload, 2026, 4, pd.Timestamp("2026-10-01", tz="UTC"))
            if r["position"] in ("QB", "RB", "WR", "TE")]
    hist = pd.DataFrame([{c: r[c] for c in (*sp.LINE_COLUMNS, "position")} for r in rows])
    scoring = {"rec": 0.5, "pass_yd": 0.04, "pass_td": 4, "pass_int": -1, "rush_yd": 0.1, "rush_td": 6, "rec_yd": 0.1,
               "rec_td": 6, "fum_lost": -2, "pass_2pt": 2, "rush_2pt": 2, "rec_2pt": 2}
    got = h2h.price_sleeper(hist, scoring)
    want = [round(sp.price_line(r["payload"]["stats"], scoring), 2) for r in rows]
    assert got.tolist() == pytest.approx(want, abs=1e-9)


def test_the_summary_is_one_table_and_says_what_is_missing():
    weeks = pd.DataFrame([{"season": 2023, "week": w, "status": "ok", "n_objects": 3300, "n_lines": 400, "attempts": 1,
                           "error": None} for w in range(1, 19)]
                         + [{"season": 2026, "week": 1, "status": "failed", "n_objects": None, "n_lines": None,
                             "attempts": 2, "error": "FetchError: 404 not found"}])
    pop = population(2.0, 6.0, positions=("QB", "RB", "WR", "TE"), weeks=range(1, 4), n=30)
    inp = h2h.Inputs(pop, LEAGUES, {"lines": 1000, "matched": 990, "unmatched_ids": ["1234"]})
    text = h2h.summary_text(weeks, h2h.grade(inp), inp)
    assert "held: 18 of 19 asked (2023 18/18, 2026 0/1)" in text
    assert "NOT held (asked again next night): 1 weeks — 2026 wk 1" in text
    assert "Matched by id (QB–TE lines): 990 of 1,000" in text
    assert "Player-weeks graded (League of Scrubs): QB 2023 90" in text
    assert text.count("\n| QB |") == 1 and "| word |" in text and "favours Sleeper" in text
    assert "our live model (v3.6) re-run on each past season" in text
    empty = h2h.summary_text(None, pd.DataFrame(), None)
    assert "not pulled yet" in empty and "No player-week graded yet" in empty


# ------------------------------------------------------------------------------ the record never reads the history
def test_the_record_reads_only_its_own_snapshots():
    sql = (PROJECT_ROOT / "dbt" / "models" / "marts" / "edge" / "mart_projection_record.sql").read_text()
    sources = set(re.findall(r"source\('(\w+)', '(\w+)'\)", sql))
    assert ("raw", "sleeper_projections") in sources and not any("history" in t for _, t in sources)
    assert "p.fetched_at < k.first_kickoff_at" in sql


def test_the_rows_written_carry_the_columns_types():
    # pandas holds an integer column with a gap (the pooled rows' season) as floats: 2024.0 would not COPY as integer
    df = h2h.grade(inputs(population(2.0, 6.0, seasons=(2023, 2024, 2025), weeks=range(1, 4))))
    rows = h2h.rows_for_copy(df)
    i = {c: k for k, (c, _) in enumerate(h2h.GRADE_COLUMNS)}
    seasons = {r[i["season"]] for r in rows}
    assert None in seasons and {s for s in seasons if s is not None} == {2023, 2024, 2025}
    assert all(type(s) is int for s in seasons if s is not None)
    assert all(r[i["n_weeks"]] is None or type(r[i["n_weeks"]]) is int for r in rows)
    assert all(type(r[i["headline"]]) is bool for r in rows)
    assert all(r[i["diff"]] is None or type(r[i["diff"]]) is float for r in rows)
