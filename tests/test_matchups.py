"""C5 (plan R-14 / R-15 / R-11): the Matchups page's pure helpers — the likely-cover rule and the cornerback rank
(Python twins of the SQL in mart_cb_matchups / mart_cb_rankings, pinned on fixtures), the cornerback lines, the
defense-vs-position pictures and the side-by-side verdict. No database: rows are shaped like the marts'."""

import re
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from lib.charts import dvp_bars, dvp_heatmap  # noqa: E402
from lib.matchups import (  # noqa: E402
    call_cover,
    cb_label,
    cb_line,
    comparison_rows,
    comparison_verdict,
    cover_split,
    cover_split_text,
    dvp_heat_frame,
    dvp_selection,
    last_name,
    lean_text,
    line_text,
    matchup_lean,
    most,
    passer_rating,
    rank_corners,
    seasons_text,
)

PAGE = Path(__file__).resolve().parents[1] / "app" / "pages" / "5_Matchups.py"
ROOT = Path(__file__).resolve().parents[1]


# ------------------------------------------------------------------------------------------ words
@pytest.mark.parametrize("name,expected", [
    ("Amon-Ra St. Brown", "St. Brown"), ("Will Lee III", "Lee"), ("Jaycee Horn", "Horn"), ("Joey Porter Jr.", "Porter"),
    ("Patrick Surtain II", "Surtain"), ("Cher", "Cher"), ("", ""), (None, ""),
])
def test_last_name(name, expected):
    assert last_name(name) == expected


def test_small_phrases():
    assert seasons_text(2024, 2024) == "2024"
    assert seasons_text(2022, 2025) == "2022–25"
    assert seasons_text(None, None) == ""
    assert line_text(1, 12, 1) == "1 catch for 12 yards on 1 target"
    assert line_text(5, 55, 7) == "5 catches for 55 yards on 7 targets"
    assert [most(r) for r in (1, 2, 3, 4, 11, 12, 13, 21, 22, 23, 32)] == [
        "the most", "the 2nd-most", "the 3rd-most", "the 4th-most", "the 11th-most", "the 12th-most", "the 13th-most",
        "the 21st-most", "the 22nd-most", "the 23rd-most", "the 32nd-most"]


# ------------------------------------------------------------------------------------------ R-14: the likely-cover rule
CORNERS = dict(lcb="L1", rcb="R1", nb="N1")


def test_clear_lean_to_the_offense_left_meets_the_right_corner():
    c = call_cover(50, 20, 30, "WR", **CORNERS)          # 50% left, 30% right: 20 points apart
    assert c["call_status"] == "called" and c["alignment_lean"] == "left"
    assert c["likely_cover_slot"] == "RCB" and c["call_strength"] == "clear" and c["other_cover_slot"] is None
    assert (c["side_share"], c["other_side_share"]) == (0.5, 0.3)


def test_even_split_names_both_outside_corners():
    # Amon-Ra St. Brown before week 4 of 2026: 66 left, 60 middle, 73 right (199 located)
    c = call_cover(66, 60, 73, "WR", **CORNERS)
    assert c["alignment_lean"] == "right" and c["likely_cover_slot"] == "LCB"
    assert c["call_strength"] == "even" and c["other_cover_slot"] == "RCB"
    assert (c["side_share"], c["other_side_share"]) == (0.367, 0.332)


def test_exactly_fifteen_points_is_clear_and_a_tie_goes_right():
    assert call_cover(45, 25, 30, "WR", **CORNERS)["call_strength"] == "clear"     # 0.45 - 0.30 = 0.15
    assert call_cover(44, 26, 30, "WR", **CORNERS)["call_strength"] == "even"
    tie = call_cover(20, 10, 20, "WR", **CORNERS)
    assert tie["alignment_lean"] == "right" and tie["likely_cover_slot"] == "LCB"


def test_missing_corners_fall_back_outside_then_slot():
    assert call_cover(50, 20, 30, "WR", lcb="L1", rcb=None, nb="N1")["likely_cover_slot"] == "LCB"
    assert call_cover(30, 20, 50, "WR", lcb=None, rcb="R1", nb="N1")["likely_cover_slot"] == "RCB"
    only_nb = call_cover(50, 20, 30, "WR", lcb=None, rcb=None, nb="N1")
    assert only_nb["likely_cover_slot"] == "NB" and only_nb["other_cover_slot"] is None
    # an even split with one outside corner missing names only the one there is
    assert call_cover(35, 30, 35, "WR", lcb="L1", rcb=None, nb=None)["other_cover_slot"] is None


@pytest.mark.parametrize("args,status", [
    ((10, 5, 20, "TE"), "tight end"),
    ((5, 3, 6, "WR"), "too few targets"),            # 14 located targets
    ((5, 4, 6, "WR"), "called"),                     # 15
])
def test_no_call_reasons(args, status):
    c = call_cover(*args, **CORNERS)
    assert c["call_status"] == status
    assert (c["likely_cover_slot"] is None) == (status != "called")


def test_no_depth_chart_comes_first():
    for pos in ("WR", "TE"):
        c = call_cover(50, 20, 30, pos, has_depth_chart=False)
        assert c["call_status"] == "no depth chart yet" and c["likely_cover_slot"] is None and c["call_strength"] is None


# ------------------------------------------------------------------------------------------ R-14: the rank
def test_passer_rating_formula():
    assert passer_rating(0, 10, 0, 0, 0) == pytest.approx(39.583, abs=1e-3)       # only the INT part is non-zero
    assert passer_rating(20, 20, 400, 5, 0) == pytest.approx(158.333, abs=1e-3)   # every part capped
    assert passer_rating(0, 0, 0, 0, 0) is None


@pytest.mark.parametrize("rank,n,label", [
    (1, 74, "shutdown"), (19, 74, "shutdown"), (20, 74, "solid"), (55, 74, "solid"), (56, 74, "target"), (74, 74, "target"),
    (16, 64, "shutdown"), (17, 64, "solid"), (48, 64, "solid"), (49, 64, "target"), (None, 74, None),
])
def test_label_quarters(rank, n, label):
    assert cb_label(rank, n) == label


def corners_fixture() -> pd.DataFrame:
    """Five starting corners, a backup under the snap floor and a safety (not a corner)."""
    rows = [
        # name, is_cb, snaps, targets, comp, yards, td, int, exp_ypt
        ("Shut", True, 500, 50, 25, 250, 1, 3, 8.0),    # rarely thrown at, few yards, low rating
        ("Good", True, 500, 60, 33, 360, 2, 2, 7.5),
        ("Mid", True, 500, 75, 45, 525, 3, 1, 7.5),
        ("Hard", True, 500, 80, 50, 640, 4, 1, 8.5),    # tough schedule: the adjustment helps him
        ("Toast", True, 500, 95, 66, 950, 8, 0, 7.0),
        ("Backup", True, 150, 20, 10, 100, 0, 1, 7.5),  # under 340 snaps: not ranked
        ("Safety", False, 600, 30, 15, 150, 0, 2, 7.5),
    ]
    return pd.DataFrame([dict(name=r[0], is_cb=r[1], coverage_snaps=r[2], targets=r[3], completions_allowed=r[4],
                              yards_allowed=r[5], tds_allowed=r[6], interceptions=r[7], exp_ypt_faced=r[8],
                              min_coverage_snaps=340) for r in rows])


def test_rank_orders_the_pool_and_leaves_the_rest_out():
    d = rank_corners(corners_fixture()).set_index("name")
    assert d["is_ranked"].tolist() == [True, True, True, True, True, False, False]
    assert (d.loc[["Backup", "Safety"], "quality_rank"].isna()).all()
    assert d.loc[d["is_ranked"], "quality_rank"].sort_values().index.tolist() == ["Shut", "Good", "Mid", "Hard", "Toast"]
    assert d["n_ranked"].iloc[0] == 5
    # quarters of 5: ceil(5 / 4) = 2 at each end
    assert d.loc[["Shut", "Good", "Mid", "Hard", "Toast"], "quality_label"].tolist() == ["shutdown", "shutdown", "solid", "target", "target"]


def test_adjusted_yards_per_target_by_hand():
    d = rank_corners(corners_fixture()).set_index("name")
    pool = d[d["is_ranked"]]
    pool_ypt = pool["yards_allowed"].sum() / pool["targets"].sum()                          # 2725 / 360
    pool_exp = (pool["exp_ypt_faced"] * pool["targets"]).sum() / pool["targets"].sum()
    hard = (640 / 80 - 8.5 + pool_exp) * 80 / 110 + pool_ypt * 30 / 110                       # shrunk with 30 targets
    assert d.loc["Hard", "adj_yards_per_target"] == pytest.approx(hard)
    assert d.loc["Hard", "adj_yards_per_target"] < d.loc["Hard", "yards_per_target_allowed"]  # faced strong offenses
    # the score is minus the mean of three sample z-scores
    z = lambda col: (pool[col] - pool[col].mean()) / pool[col].std(ddof=1)  # noqa: E731
    score = -(z("targets_per_coverage_snap") + z("adj_yards_per_target") + z("passer_rating_allowed")) / 3
    assert d.loc[pool.index, "quality_score"].tolist() == pytest.approx(score.tolist())


# ------------------------------------------------------------------------------------------ R-14: the lines
def cb_row(**kw) -> dict:
    """A mart_cb_matchups row: Amon-Ra St. Brown vs CAR, week 4 of 2026, as built on the C5 clone."""
    row = dict(
        gsis_id="00-0036963", player_name="Amon-Ra St. Brown", position="WR", season=2026, week=4, opponent="CAR",
        lcb_gsis_id="00-0035277", lcb_name="Mike Jackson", rcb_gsis_id="00-0041063", rcb_name="Will Lee III",
        nb_gsis_id="00-0036944", nb_name="Jaycee Horn",
        located_targets=199, left_share=0.332, middle_share=0.302, right_share=0.367, side_share=0.367, other_side_share=0.332,
        alignment_lean="right", call_status="called", call_strength="even", likely_cover_slot="LCB",
        likely_cover_gsis_id="00-0035277", likely_cover_name="Mike Jackson",
        other_cover_slot="RCB", other_cover_gsis_id="00-0041063", other_cover_name="Will Lee III",
        cover_is_ranked=True, cover_rank=37, cover_label="solid", cb_n_ranked=74, cb_min_coverage_snaps=380,
        lcb_rank=37, lcb_label="solid", rcb_rank=None, rcb_label=None, nb_rank=24, nb_label="solid",
        games_vs_opp=0, targets_vs_opp=None, receptions_vs_opp=None, yards_vs_opp=None,
        games_vs_cover=0, targets_vs_cover=None, receptions_vs_cover=None, yards_vs_cover=None,
        first_season_vs_cover=None, last_season_vs_cover=None, evidence_vs_cover=None,
    )
    row.update(kw)
    return row


def test_even_line_names_both_corners_with_their_ranks():
    assert cb_line(cb_row()) == ("**Amon-Ra St. Brown** vs CAR: no clear side (37% of his targets one way, 33% the other): "
                                 "**Mike Jackson (left corner, #37 of 74, solid)** or **Will Lee III (right corner, unranked: "
                                 "too few snaps)**.")


def test_clear_line_names_one_corner_the_share_and_the_history():
    r = cb_row(player_name="Parker Washington", opponent="CIN", call_strength="clear", side_share=0.47, other_side_share=0.29,
               likely_cover_slot="RCB", likely_cover_name="DJ Turner II", cover_rank=18, cover_label="shutdown",
               other_cover_slot=None, other_cover_name=None,
               games_vs_cover=3, targets_vs_cover=11, receptions_vs_cover=11, yards_vs_cover=137,
               first_season_vs_cover=2023, last_season_vs_cover=2025, evidence_vs_cover="on_field")
    assert cb_line(r) == ("**Parker Washington** vs CIN: likely across from **DJ Turner II (right corner, #18 of 74, shutdown)** "
                          "— 47% of his targets went to that side, 29% to the other. 11 catches for 137 yards on 11 targets "
                          "with Turner on the field (2023–25).")


def test_history_this_season_and_same_game_evidence():
    line = cb_line(cb_row(games_vs_opp=1, targets_vs_opp=5, receptions_vs_opp=3, yards_vs_opp=41,
                          games_vs_cover=1, targets_vs_cover=4, receptions_vs_cover=2, yards_vs_cover=20,
                          first_season_vs_cover=2026, last_season_vs_cover=2026, evidence_vs_cover="same_game"))
    assert line.endswith(" 3 catches for 41 yards on 5 targets against CAR this season; "
                         "2 catches for 20 yards on 4 targets in games Jackson played (2026).")


@pytest.mark.parametrize("status,expected", [
    ("tight end", "tight ends mostly draw linebackers and safeties, so no cornerback call."),
    ("too few targets", "too few targets since 2025 to tell which side he works (11 with a direction); CAR's outside corners: "
                        "Mike Jackson (left corner, #37 of 74, solid) and Will Lee III (right corner, unranked: too few snaps)."),
    ("no depth chart yet", "no depth chart for CAR yet, so no cornerback call."),
])
def test_no_call_lines_say_why(status, expected):
    r = cb_row(call_status=status, located_targets=11, likely_cover_gsis_id=None, likely_cover_name=None, likely_cover_slot=None)
    assert cb_line(r) == f"**Amon-Ra St. Brown** vs CAR: {expected}"


def test_lean_text_uses_the_same_shares():
    t = lean_text(cb_row())
    assert t.startswith("Since the start of 2025, 199 of his targets had a direction: 33% to the left, 30% over the middle, 37% to the right")
    assert lean_text(cb_row(located_targets=0)) == "No targets with a direction since the start of 2025."


def test_cover_split_by_hand():
    g = pd.DataFrame({"gsis_id": ["a"] * 5 + ["b"] * 2, "player_name": ["A"] * 5 + ["B"] * 2,
                      "cover_label": ["shutdown", "solid", "target", "shutdown", None, "solid", "target"],
                      "points": [10.0, 20.0, 30.0, 12.0, 8.0, 5.0, 7.0]})
    s = cover_split(g).set_index("gsis_id")
    assert s.loc["a", "ppg_vs_shutdown"] == 11.0 and s.loc["a", "games_vs_shutdown"] == 2
    assert s.loc["a", "ppg_vs_rest"] == round((20 + 30 + 8) / 3, 1) and s.loc["a", "games_vs_rest"] == 3   # unranked counts as rest
    assert pd.isna(s.loc["b", "ppg_vs_shutdown"]) and s.loc["b", "games_vs_shutdown"] == 0
    assert cover_split_text(s.loc["b"]) == "vs shutdown corners no games, vs the rest 6.0 a game (2 games)"
    assert cover_split(pd.DataFrame()).empty


# ------------------------------------------------------------------------------------------ R-15 pictures
def dvp_frame(n=32) -> pd.DataFrame:
    teams = [f"T{i:02d}" for i in range(1, n + 1)]
    return pd.DataFrame({"defense": teams, "points_allowed_per_game_std": [40.0 - i for i in range(n)],
                         "rank_std": list(range(1, n + 1))})


def test_selection_keeps_top_bottom_and_yours_with_gaps():
    sel = dvp_selection(dvp_frame(), "points_allowed_per_game_std", {"T13": "Amon-Ra St. Brown", "T05": "Parker Washington"}, n=8)
    assert sel["defense"].tolist() == [f"T{i:02d}" for i in range(1, 9)] + ["T13"] + [f"T{i:02d}" for i in range(25, 33)]
    assert sel["gap_before"].tolist() == [0] * 8 + [4] + [11] + [0] * 7
    assert sel.loc[sel["is_mine"], "defense"].tolist() == ["T05", "T13"]
    assert len(sel) + int(sel["gap_before"].sum()) == 32


def test_selection_with_n_equal_to_the_rows_is_every_defense_ranked():
    sel = dvp_selection(dvp_frame(), "points_allowed_per_game_std", {"T13": "X"}, n=32)
    assert sel["defense"].tolist() == [f"T{i:02d}" for i in range(1, 33)] and sel["gap_before"].sum() == 0


def test_bars_mark_yours_in_words_and_label_only_yours_with_the_rank():
    sel = dvp_selection(dvp_frame(), "points_allowed_per_game_std", {"T13": "Amon-Ra St. Brown"}, n=8)
    fig = dvp_bars(sel, "points_allowed_per_game_std", "t", "x", league_avg=24.5, rank_col="rank_std", n_total=32)
    bar = fig.data[0]
    labels = list(bar.y)
    assert labels.count("<b>T13 ◀</b>") == 1
    assert len([lb for lb in labels if lb.startswith("⋯")]) == 2
    assert [t for t in bar.text if t] == ["28.0 · #13"]                 # T13 = 40 - 12, rank 13
    assert "your Amon-Ra St. Brown" in bar.customdata[labels.index("<b>T13 ◀</b>")]
    assert fig.layout.shapes[0].x0 == 24.5                             # the league-average hairline


def heat_dvp() -> pd.DataFrame:
    rows = []
    for i, t in enumerate(["AAA", "BBB", "CCC", "DDD"]):
        for j, p in enumerate(["QB", "RB", "WR", "TE"]):
            rank = (i + j) % 4 + 1
            rows.append(dict(defense=t, position=p, points_allowed_per_game_std=30.0 - rank, rank_std=rank))
    return pd.DataFrame(rows)


def test_heat_frame_pins_your_opponents_then_orders_by_mean_rank():
    marks = {"DDD": {"WR": "Amon-Ra St. Brown"}, "CCC": {"RB": "Kenny Gainwell", "TE": "George Kittle"}}
    f = dvp_heat_frame(heat_dvp(), ["QB", "RB", "WR", "TE"], "points_allowed_per_game_std", "rank_std", marks)
    assert f["defense"].tolist()[:2] == ["CCC", "DDD"]                  # yours first (tied mean rank: by name)
    assert f["is_mine"].tolist() == [True, True, False, False]
    assert f.set_index("defense").loc["CCC", "facing"] == "Kenny Gainwell (RB); George Kittle (TE)"
    only = dvp_heat_frame(heat_dvp(), ["QB", "RB", "WR", "TE"], "points_allowed_per_game_std", "rank_std", marks, only_marked=True)
    assert only["defense"].tolist() == ["CCC", "DDD"]
    assert f.loc[0, "RB"] == 30.0 - f.loc[0, "RB_rank"]


def test_heatmap_rings_your_cells_and_prints_every_value():
    marks = {"DDD": {"WR": "Amon-Ra St. Brown"}, "CCC": {"RB": "Kenny Gainwell", "TE": "George Kittle"}}
    f = dvp_heat_frame(heat_dvp(), ["QB", "RB", "WR", "TE"], "points_allowed_per_game_std", "rank_std", marks)
    fig = dvp_heatmap(f, ["QB", "RB", "WR", "TE"], "t", n_total=4)
    hm = fig.data[0]
    assert list(hm.y)[:2] == ["<b>CCC ◀</b>", "<b>DDD ◀</b>"]
    rings = [s for s in fig.layout.shapes if s.type == "rect"]
    assert len(rings) == 3                                                # Gainwell RB, Kittle TE, St. Brown WR
    cells = [a for a in fig.layout.annotations if a.xref != "paper"]
    assert len(cells) == 16                                               # a number in every cell
    assert "your Amon-Ra St. Brown" in hm.customdata[1][2]
    assert hm.zmin == 1 and hm.zmax == 4 and hm.xgap == 2


# ------------------------------------------------------------------------------------------ R-11 side by side
def player(name, proj, p10, p90, opp="GB", gid=None, **kw) -> dict:
    d = dict(gsis_id=gid or name, player_name=name, position="RB", proj_points=proj, p10=p10, p90=p90, opponent=opp,
             is_home=True, points_allowed_pg=29.2, rank_points=4, opps_allowed_pg=32.3, rank_opportunity=6,
             targets_allowed_pg=3.3, rank_targets=30, carries_allowed_pg=29.0, rank_carries=1,
             yards_per_opp_allowed=4.8, rank_efficiency=8, td_rate_allowed=0.062, rank_td_rate=5,
             adjusted_points_pg=5.7, rank_adjusted=1, gives_up="volume and big plays", n_defenses=32)
    d.update(kw)
    return d


# Kenny Gainwell vs Emanuel Wilson, dynasty team 12, week 4 of 2026 (the closest call on the clone)
GAINWELL = player("Kenny Gainwell", 7.54, 1.0, 16.0, gid="00-0036919")
WILSON = player("Emanuel Wilson", 7.09, 1.2, 14.5, opp="LAC", gid="00-0038449", points_allowed_pg=14.5, rank_points=22,
                targets_allowed_pg=7.0, rank_targets=3, carries_allowed_pg=26.0, rank_carries=8, yards_per_opp_allowed=2.9,
                rank_efficiency=32, td_rate_allowed=0.015, rank_td_rate=24, adjusted_points_pg=-1.4, rank_adjusted=20,
                gives_up="volume")
DECISION = {"gsis_id": "00-0036919", "alt_gsis_id": "00-0038449", "margin": 0.45}


def test_verdict_quotes_the_lineup_margin_and_the_matchup_agrees():
    assert comparison_verdict(GAINWELL, WILSON, DECISION) == (
        "The lineup says Gainwell by 0.45; the matchup agrees: his defense gives up the most carries to RBs.")
    # the order of the two pickers does not change the call
    assert comparison_verdict(WILSON, GAINWELL, DECISION).startswith("The lineup says Gainwell by 0.45")


def test_verdict_when_the_matchup_leans_the_other_way():
    tucker = player("Sean Tucker", 8.10, 2.0, 15.0, gid="t", rank_adjusted=18)
    monangai = player("Kyle Monangai", 7.95, 2.0, 15.5, gid="m", rank_adjusted=5, rank_carries=4, rank_targets=20,
                      rank_efficiency=9, rank_td_rate=12)
    v = comparison_verdict(tucker, monangai, {"gsis_id": "t", "alt_gsis_id": "m", "margin": 0.15})
    assert v == "The lineup says Tucker by 0.15; the matchup leans Monangai: his defense gives up the 4th-most carries to RBs."


def test_verdict_uses_the_adjusted_ranks_when_nothing_stands_out():
    a = player("Courtland Sutton", 11.0, 3.0, 20.0, gid="s", position="WR", rank_adjusted=9, rank_targets=16,
               rank_efficiency=14, rank_td_rate=20)
    b = player("Xavier Worthy", 10.6, 2.0, 21.0, gid="w", position="WR", rank_adjusted=24)
    assert comparison_verdict(a, b, {"gsis_id": "s", "alt_gsis_id": "w", "margin": 0.42}) == (
        "The lineup says Sutton by 0.42; the matchup agrees: 9th-most WR points allowed by his defense once the "
        "offenses it faced are counted, 9th-fewest WR points allowed by Worthy's.")


def test_history_with_no_catch_reads_zero_yards():
    assert line_text(0, float("nan"), 3) == "0 catches for 0 yards on 3 targets"
    assert line_text(None, None, None) == "0 catches for 0 yards on 0 targets"


def test_verdict_about_even_and_outside_the_lineup():
    a = player("Josh Allen", 32.32, 18.1, 50.8, gid="a", position="QB", rank_adjusted=10)
    b = player("Lamar Jackson", 27.32, 15.2, 39.5, gid="b", position="QB", rank_adjusted=13)
    assert comparison_verdict(a, b) == "Allen projects 5.00 more (32.32 vs 27.32); the matchups are about even."
    assert matchup_lean(a, b) == (None, "the matchups are about even")


def test_verdict_names_full_names_when_last_names_match_and_reads_wr_reasons():
    a = player("A Receiver", 12.0, 4.0, 24.0, gid="x", position="WR", rank_adjusted=2, rank_targets=9, rank_efficiency=3, rank_td_rate=15)
    b = player("B Receiver", 11.5, 6.0, 20.0, gid="y", position="WR", rank_adjusted=25)
    assert comparison_verdict(a, b) == ("A Receiver projects 0.50 more (12.00 vs 11.50); the matchup leans A Receiver: "
                                        "his defense gives up the 3rd-most yards per target to WRs.")


def test_verdict_without_a_projection_makes_no_call():
    v = comparison_verdict(player("Kenny Gainwell", None, None, None), WILSON)
    assert v == "No projection this week for Gainwell (a bye, or no games yet), so no call."
    t = comparison_rows(player("On Bye", None, None, None, opp=None), WILSON)
    assert set(t["On Bye"]) == {"—"}


def test_no_games_yet_means_no_matchup_read():
    assert matchup_lean(player("A", 1, 0, 2, rank_adjusted=None), WILSON) == (None, "no games yet to read the matchups from")


def test_table_rows_and_numbers_behind_the_verdict():
    t = comparison_rows(GAINWELL, WILSON).set_index("What")
    assert t.loc["Projection", "Kenny Gainwell"] == "7.54" and t.loc["Projection", "Emanuel Wilson"] == "7.09"
    assert t.loc["Floor – ceiling", "Kenny Gainwell"] == "1.0 – 16.0"
    assert t.loc["Opponent", "Emanuel Wilson"] == "vs LAC"
    assert t.loc["Carries allowed / game", "Kenny Gainwell"] == "29.0 (#1)"   # the verdict's "the most carries"
    assert t.loc["Targets allowed / game", "Emanuel Wilson"] == "7.0 (#3)"
    assert t.loc["Touchdown rate", "Kenny Gainwell"] == "6.2% (#5)"
    assert t.loc["Vs the offenses faced", "Kenny Gainwell"] == "+5.7 (#1)"
    # receivers only: no carries row
    wr = comparison_rows(player("W1", 10, 1, 20, position="WR"), player("W2", 9, 1, 18, position="WR"))
    assert "Carries allowed / game" not in set(wr["What"])
    # every number in a non-lineup verdict is a cell of the table, or the gap between the two projections
    a, b = player("Chris Olave", 12.13, 5.1, 21.3, position="WR", gid="o"), player("Puka Nacua", 11.84, 4.6, 24.0, position="WR", gid="n")
    cells = " ".join(comparison_rows(a, b).drop(columns="What").to_numpy().ravel())
    v = comparison_verdict(a, b)
    assert v.startswith("Olave projects 0.29 more (12.13 vs 11.84)")
    for num in re.findall(r"\d+\.\d+", v.replace("0.29 more", "")):
        assert num in cells, num


# ------------------------------------------------------------------------------------------ the page and the marts
def test_page_reads_the_new_marts_and_one_projection():
    src = PAGE.read_text()
    for mart in ("mart_cb_matchups", "mart_cb_rankings", "mart_receiver_vs_cb", "mart_defense_position_profile",
                 "mart_player_week_projections", "mart_defense_vs_position_current", "fct_player_game_league"):
        assert f"analytics.{mart}" in src, mart
    assert "mart_player_week_rankings" not in src          # the old formula stays on Rankings (round-2 convention 3)
    for retired in ("mart_matchup_cb_context", "mart_cb_coverage", "mart_cb_matchup_week", "heat_style"):
        assert retired not in src, retired
    assert "decision_cards(league_id, roster_id, lu_week, lu_season, rows=lu_rows)" in src   # B4's cards stay on top


def test_sql_rules_match_the_python_twins():
    """The constants the SQL hard-codes are the ones the Python twins use."""
    from lib.matchups import CLEAR_LEAN, MIN_LOCATED_TARGETS, SHRINK_TARGETS
    m = (ROOT / "dbt/models/marts/nfl/mart_cb_matchups.sql").read_text()
    r = (ROOT / "dbt/models/marts/nfl/mart_cb_rankings.sql").read_text()
    assert f"b.located_targets < {MIN_LOCATED_TARGETS} then 'too few targets'" in m
    assert f"p.side_share - p.other_side_share >= {CLEAR_LEAN:.2f} then 'clear'" in m
    assert f"pl.pool_ypt * {SHRINK_TARGETS})" in r and f"(p.targets + {SHRINK_TARGETS})" in r
    assert "ceil(r.n_ranked / 4.0)" in r
