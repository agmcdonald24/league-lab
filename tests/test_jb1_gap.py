"""JB-1 (Wave J-B): gp1.0's slices, shares and ship rule on constructed rows with known answers (no database)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from league_lab import h2h_gap as G

LOS = "1389709692405551104"


def rows(n_weeks: int = 6, per: int = 40, seed: int = 3, positions=("RB", "WR")) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    out = []
    for s in (2023, 2024):
        for w in range(1, n_weeks + 1):
            for pos in positions:
                act = rng.gamma(2.0, 5.0, per)
                for i in range(per):
                    out.append({"league_id": LOS, "season": s, "week": w, "position": pos, "gsis_id": f"00-{pos}{i:03d}",
                                "ours": act[i] + rng.normal(0, 4), "sleeper": act[i] + rng.normal(0, 3), "actual": act[i],
                                "prev_played": [np.nan, True, False][i % 3], "role": ["none", "role up", "role down"][i % 3],
                                "pn_qb_changed": [False, True, None][i % 3], "rookie_season": [s, s - 1, 2012, np.nan][i % 4],
                                "career_games_before": [0, 5, 30, 2][i % 4], "is_home": [True, False][i % 2],
                                "total_line": [38.5, 44.5, 50.5, None][i % 4]})
    return pd.DataFrame(out)


def test_the_slices_are_assigned_as_the_rule_says():
    d = G.assign(rows())
    one = d[(d["season"] == 2023) & (d["week"] == 1) & (d["position"] == "RB")].sort_values("ours", ascending=False)
    assert one["our_rank"].tolist() == list(range(1, 41))
    assert one["slice_position × tier"].tolist() == (["RB top-12"] * 12 + ["RB 13-24"] * 12 + ["RB 25-36"] * 12
                                                      + ["RB 37+"] * 4)
    by = d.set_index("gsis_id").loc["00-RB000"].iloc[0]          # i = 0
    assert by["slice_first game back"].startswith("not back (no earlier") and by["slice_role"] == "none"
    assert by["slice_QB change"] == "same QB" and by["slice_experience"] == "rookie" and by["slice_history"] == "0-2 games"
    assert by["slice_venue"] == "home" and by["slice_season stage"] == "weeks 1-4"
    two = d.set_index("gsis_id").loc["00-RB002"].iloc[0]         # i = 2: did not play the previous game; 2012 rookie
    assert two["slice_first game back"] == "first game back" and two["slice_role"] == "role down"
    assert two["slice_QB change"] == "unknown" and two["slice_experience"] == "veteran"
    assert two["slice_history"] == "8+ games"                     # 30 games before
    early = d.set_index("gsis_id").loc["00-RB003"].iloc[0]       # unknown rookie season, 2 games: a cold start
    assert early["slice_experience"] == "unknown" and early["slice_history"] == "0-2 games"
    assert set(d["slice_game total"]) == {"low (≤ 44.5)", "middle (≤ 50.5)", "not held"} or "not held" in set(d["slice_game total"])
    assert (d["excess"] == (d["ours"] - d["actual"]).abs() - (d["sleeper"] - d["actual"]).abs()).all()


def test_a_career_begun_before_2016_counts_as_eight_plus_games():
    r = rows().head(1).assign(rookie_season=2011, career_games_before=0)
    assert G.assign(r)["slice_history"].iloc[0] == "8+ games"


@pytest.mark.parametrize("family", G.FAMILIES)
def test_each_familys_shares_sum_to_one_and_the_gap_is_the_mean(family):
    d = G.assign(rows())
    t = G.family_table(d, f"slice_{family}")
    assert t["share"].sum() == pytest.approx(1.0)
    assert t["n"].sum() == len(d) and t["row_share"].sum() == pytest.approx(1.0)
    for r in t.itertuples():
        m = d[f"slice_{family}"].astype(str) == r.slice
        assert r.gap == pytest.approx(d.loc[m, "excess"].mean())
        assert r.gap_lo <= r.gap + 1e-9 and r.gap <= r.gap_hi + 1e-9
    again = G.family_table(d, f"slice_{family}")
    assert again["share_lo"].tolist() == t["share_lo"].tolist()


def test_a_slice_that_holds_all_the_excess_has_share_one():
    d = G.assign(rows())
    d["excess"] = np.where(d["position"] == "WR", 1.0, 0.0)
    t = G.family_table(d.assign(slice_pos=d["position"]), "slice_pos").set_index("slice")
    assert t.loc["WR", "share"] == 1.0 and t.loc["RB", "share"] == 0.0
    assert t.loc["WR", "share_lo"] == pytest.approx(1.0) and t.loc["WR", "gap"] == 1.0


def test_close_calls_belong_to_the_player_we_rank_higher():
    d = pd.DataFrame({"league_id": LOS, "season": 2024, "week": 1, "position": "RB", "gsis_id": ["a", "b", "c", "d"],
                      "ours": [10.0, 9.0, 5.0, 4.0], "sleeper": [9.0, 10.0, 4.0, 5.0], "actual": [10.0, 20.0, 5.0, 6.0],
                      "slice_x": ["A", "B", "C", "D"]})
    t = G.close_calls(d, "slice_x").set_index("slice")
    # (a, b): we rank a higher, b scored more -> slice A, wrong; (c, d): we rank c higher, d scored more -> slice C, wrong
    assert t.loc["A", "calls"] == 1 and t.loc["A", "calls_ours_right"] == 0
    assert t.loc["C", "calls"] == 1 and "B" not in t.index


def test_the_component_family_prices_each_part_of_the_line():
    d = pd.DataFrame({"wk": [202301, 202301], "position": ["RB", "RB"],
                      "proj_rushing_yards": [80.0, 50.0], "out_rushing_yards": [60.0, 50.0], "sl_rushing_yards": [65.0, 40.0],
                      "proj_receptions": [3.0, 2.0], "out_receptions": [3.0, 4.0], "sl_receptions": [None, 3.0]})
    t = G.component_table(d, {"rush_yd": 0.1, "rec": 0.5}).set_index("slice")
    # rushing: 0.1 x ((20 - 5) + (0 - 10)) = 0.5; receptions: 0.5 x ((0 - 3) + (2 - 1)) = -1.0 (Sleeper's missing key = 0)
    assert t.loc["rushing_yards", "gap"] == pytest.approx(0.25) and t.loc["receptions", "gap"] == pytest.approx(-0.5)
    assert t["share"].sum() == pytest.approx(1.0) and t.loc["rushing_yards", "share"] == pytest.approx(0.5 / -0.5)


def lines(base_noise: float, seed: int, shift: dict | None = None) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    out = []
    for s in (2023, 2024, 2025):
        for w in range(1, 6):
            for pos in ("QB", "RB", "WR", "TE"):
                act = rng.gamma(2.0, 5.0, 30)
                for i in range(30):
                    out.append({"league_id": LOS, "gsis_id": f"{pos}{i}", "season": s, "week": w, "position": pos,
                                "actual": act[i], "proj_points": act[i] + rng.normal(0, base_noise)})
    return pd.DataFrame(out)


def test_the_ship_rule():
    base = lines(4.0, 1)
    sl = base[["gsis_id", "season", "week"]].assign(sleeper=base["actual"] + 3.0)
    better = base.copy()
    rb = better["position"] == "RB"
    better.loc[rb, "proj_points"] = 0.5 * better.loc[rb, "proj_points"] + 0.5 * better.loc[rb, "actual"]
    r = G.ship_rule(base, better, sl, target="RB")
    assert r["a"] and r["b"] and r["ships"] and r["rows_moved"] == int(rb.sum())
    assert G.ship_rule(base, better, sl)["target"] == "RB"            # the position it moved most
    worse_2024 = better.copy()
    m = rb & (worse_2024["season"] == 2024)
    worse_2024.loc[m, "proj_points"] = base.loc[m, "proj_points"] + 1.0
    assert not G.ship_rule(base, worse_2024, sl, target="RB")["a"]
    hurts_wr = better.copy()
    wr = hurts_wr["position"] == "WR"
    hurts_wr.loc[wr, "proj_points"] += 0.5 * (hurts_wr.loc[wr, "proj_points"] - hurts_wr.loc[wr, "actual"])   # 50% more miss
    r2 = G.ship_rule(base, hurts_wr, sl, target="RB")
    assert r2["a"] and not r2["b"] and not r2["ships"]
    same = G.ship_rule(base, base.copy(), sl, target="RB")
    assert not same["a"] and same["rows_moved"] == 0                 # no better = not shipped
    assert "does not ship" in G.ship_markdown("x", same)


def test_the_summary_names_the_largest_slices():
    d = G.assign(rows())
    tables = {f: G.family_table(d, f"slice_{f}") for f in G.FAMILIES}
    top = G.summary_rows(tables, k=6)
    assert len(top) == 6 and top["share"].is_monotonic_decreasing
    md = G.summary_lines(top, len(d), float(d["excess"].sum()))
    assert md[1].startswith("**Where the gap is** (gp1.0") and len([x for x in md if x.startswith("| ") and "---" not in x]) == 7
    assert G.leaders(tables)["slice"].tolist() == tables["position × tier"].head(2)["slice"].tolist()


def test_the_summarys_slice_words():
    assert G.slice_words("position × tier", "WR 37+") == "WR, our 37th and lower"
    assert G.slice_words("position × tier", "RB top-12") == "RB, our top 12"
    assert G.slice_words("first game back", "first game back") == "first game back after a missed game: first game back"
