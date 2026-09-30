"""C5 (plan R-14 / R-15 / R-11): the Matchups page's pure helpers — the cornerback lines, the defense-vs-position
picture's row choice and the side-by-side verdict. No database: rows are shaped like the marts'."""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from lib.charts import dvp_bars  # noqa: E402
from lib.matchups import (  # noqa: E402
    cb_line,
    cb_rank_text,
    comparison_rows,
    comparison_verdict,
    dvp_selection,
    last_name,
    lean_text,
    line_text,
    rank_words,
    seasons_text,
)

PAGE = Path(__file__).resolve().parents[1] / "app" / "pages" / "5_Matchups.py"


def cb_row(**kw) -> dict:
    """A mart_cb_matchup_week row (Amon-Ra St. Brown vs CAR, week 4 of 2026, as built on the C5 clone)."""
    row = dict(
        gsis_id="00-0036963", player_name="Amon-Ra St. Brown", position="WR", season=2026, week=4, opponent="CAR",
        lcb_gsis_id="00-0035277", lcb_name="Mike Jackson", rcb_gsis_id="00-0041063", rcb_name="Will Lee III",
        nb_gsis_id="00-0036944", nb_name="Jaycee Horn",
        located_targets=199, left_share=0.332, middle_share=0.302, right_share=0.367,
        alignment_lean="right", often_inside=True, call_status="called", likely_cover_slot="LCB",
        likely_cover_gsis_id="00-0035277", likely_cover_name="Mike Jackson",
        inside_cover_gsis_id="00-0036944", inside_cover_name="Jaycee Horn",
        cover_is_ranked=True, cover_rank_targets_per_snap=67, cb_n_ranked=82, cb_min_coverage_snaps=380,
        games_vs_opp=0, targets_vs_opp=None, receptions_vs_opp=None, yards_vs_opp=None,
        games_vs_cover=0, targets_vs_cover=None, receptions_vs_cover=None, yards_vs_cover=None,
        first_season_vs_cover=None, last_season_vs_cover=None, evidence_vs_cover=None,
    )
    row.update(kw)
    return row


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
    assert rank_words(1, 82) == "rarely thrown at"
    assert rank_words(27, 82) == "rarely thrown at"        # 27 <= 82 / 3
    assert rank_words(28, 82) == "thrown at about average"
    assert rank_words(54, 82) == "thrown at about average"  # 54 <= 2 * 82 / 3
    assert rank_words(55, 82) == "thrown at often"


# ------------------------------------------------------------------------------------------ R-14 cornerbacks
def test_called_line_names_the_corner_his_rank_and_the_inside_corner():
    line = cb_line(cb_row())
    assert line.startswith("**Amon-Ra St. Brown** vs CAR: likely across from him **Mike Jackson** (CAR's left corner; ")
    assert "thrown at often: #67 of 82 corners, 1 = least" in line
    assert "he also works inside, against Jaycee Horn" in line
    assert line.endswith("No game against CAR yet this season.")


def test_called_line_history_this_season_and_with_the_cover():
    line = cb_line(cb_row(games_vs_opp=1, targets_vs_opp=5, receptions_vs_opp=3, yards_vs_opp=41,
                          games_vs_cover=2, targets_vs_cover=11, receptions_vs_cover=11, yards_vs_cover=137,
                          first_season_vs_cover=2023, last_season_vs_cover=2025, evidence_vs_cover="on_field",
                          inside_cover_name=None))
    assert "3 catches for 41 yards on 5 targets against CAR this season" in line
    assert "11 catches for 137 yards on 11 targets with Jackson on the field (2023–25)." in line
    assert "works inside" not in line
    # the current season (no participation yet): games he played, not "on the field"
    same = cb_line(cb_row(games_vs_cover=1, targets_vs_cover=4, receptions_vs_cover=2, yards_vs_cover=20,
                          first_season_vs_cover=2026, last_season_vs_cover=2026, evidence_vs_cover="same_game"))
    assert "in games Jackson played (2026)" in same


def test_unranked_corner_says_why():
    r = cb_row(cover_is_ranked=False, cover_rank_targets_per_snap=None)
    assert cb_rank_text(r) == "not ranked: under 380 pass plays in coverage since 2025"
    assert "not ranked: under 380 pass plays" in cb_line(r)


@pytest.mark.parametrize("status,expected", [
    ("tight end", "tight ends mostly draw linebackers and safeties, so no cornerback call. CAR's slot corner, if he lines up wide: Jaycee Horn."),
    ("too few targets", "too few targets since last season to tell which side he plays (11); CAR's outside corners are Mike Jackson and Will Lee III."),
    ("no depth chart yet", "no depth chart for CAR yet, so no cornerback call."),
])
def test_no_call_lines_say_why(status, expected):
    r = cb_row(call_status=status, located_targets=11, likely_cover_gsis_id=None, likely_cover_name=None, likely_cover_slot=None)
    assert cb_line(r) == f"**Amon-Ra St. Brown** vs CAR: {expected}"


def test_lean_text_uses_the_same_shares():
    t = lean_text(cb_row())
    assert t.startswith("Since the start of 2025, 199 of his targets had a direction: 33% to the left, 30% over the middle, 37% to the right")
    assert lean_text(cb_row(located_targets=0)) == "No targets with a direction since the start of 2025."


# ------------------------------------------------------------------------------------------ R-15 picture
def dvp_frame(n=32) -> pd.DataFrame:
    teams = [f"T{i:02d}" for i in range(1, n + 1)]
    return pd.DataFrame({"defense": teams, "points_allowed_per_game_std": [40.0 - i for i in range(n)],
                         "rank_std": list(range(1, n + 1))})


def test_selection_keeps_top_bottom_and_yours_with_gaps():
    sel = dvp_selection(dvp_frame(), "points_allowed_per_game_std", {"T13": "Amon-Ra St. Brown", "T05": "Parker Washington"}, n=8)
    assert sel["defense"].tolist() == [f"T{i:02d}" for i in range(1, 9)] + ["T13"] + [f"T{i:02d}" for i in range(25, 33)]
    assert sel["gap_before"].tolist() == [0] * 8 + [4] + [11] + [0] * 7
    assert sel.loc[sel["is_mine"], "defense"].tolist() == ["T05", "T13"]
    assert sel.set_index("defense").loc["T13", "facing"] == "Amon-Ra St. Brown"
    # the skipped rows plus the shown rows are every defense
    assert len(sel) + int(sel["gap_before"].sum()) == 32


def test_selection_small_league_of_rows_shows_everything():
    sel = dvp_selection(dvp_frame(12), "points_allowed_per_game_std", {}, n=8)
    assert len(sel) == 12 and sel["gap_before"].sum() == 0 and not sel["is_mine"].any()


def test_selection_orders_by_the_chosen_window():
    d = dvp_frame(20).assign(points_allowed_per_game_l4=[float(i) for i in range(20)])
    sel = dvp_selection(d, "points_allowed_per_game_l4", {}, n=3)
    assert sel["defense"].tolist()[:3] == ["T20", "T19", "T18"]


def test_bars_mark_yours_in_words_and_label_only_yours():
    sel = dvp_selection(dvp_frame(), "points_allowed_per_game_std", {"T13": "Amon-Ra St. Brown"}, n=8)
    fig = dvp_bars(sel, "points_allowed_per_game_std", "t", "x", league_avg=24.5, rank_col="rank_std", n_total=32)
    bar = fig.data[0]
    labels = list(bar.y)
    assert labels.count("<b>T13 ◀</b>") == 1
    gaps = [lb for lb in labels if lb.startswith("⋯")]
    assert len(gaps) == 2 and len(set(gaps)) == 2                       # unique categories, one per skipped run
    assert [t for t in bar.text if t] == ["28.0"]                      # T13 = 40 - 12
    assert "your Amon-Ra St. Brown" in bar.customdata[labels.index("<b>T13 ◀</b>")]
    assert fig.layout.shapes[0].x0 == 24.5                             # the league-average hairline


# ------------------------------------------------------------------------------------------ R-11 side by side
def player(name, proj, p10, p90, opp="GB", gives_up="volume", **kw) -> dict:
    d = dict(player_name=name, position="RB", proj_points=proj, p10=p10, p90=p90, opponent=opp, is_home=True,
             points_allowed_pg=29.2, rank_points=4, opps_allowed_pg=32.3, rank_opportunity=6, yards_per_opp_allowed=4.8,
             rank_efficiency=8, td_rate_allowed=0.062, rank_td_rate=5, adjusted_points_pg=5.7, rank_adjusted=1,
             gives_up=gives_up, n_defenses=32)
    d.update(kw)
    return d


def test_verdict_close_with_different_profiles_and_a_ceiling():
    a = player("Kenny Gainwell", 7.54, 1.0, 16.0, gives_up="volume and big plays")
    b = player("Emanuel Wilson", 7.09, 1.2, 14.5, opp="LAC", gives_up="volume")
    v = comparison_verdict(a, b)
    assert v == ("Both project close (7.54 vs 7.09); Gainwell's defense gives up volume and big plays, "
                 "Wilson's gives up volume — Gainwell has the higher ceiling (16.0 vs 14.5).")
    t = comparison_rows(a, b).set_index("What")
    assert t.loc["Projection", "Kenny Gainwell"] == "7.54" and t.loc["Projection", "Emanuel Wilson"] == "7.09"
    assert t.loc["Floor – ceiling", "Kenny Gainwell"] == "1.0 – 16.0"
    assert t.loc["Opponent", "Emanuel Wilson"] == "vs LAC"
    assert t.loc["Points allowed / game", "Kenny Gainwell"] == "29.2 (#4)"
    assert t.loc["Touchdown rate", "Kenny Gainwell"] == "6.2% (#5)"
    assert t.loc["Vs the offenses faced", "Kenny Gainwell"] == "+5.7 (#1)"
    assert t.loc["Gives up", "Emanuel Wilson"] == "volume"


def test_verdict_one_player_ahead_on_everything():
    v = comparison_verdict(player("Josh Allen", 32.3, 18.1, 50.8, gives_up="about average", position="QB"),
                           player("Lamar Jackson", 27.3, 15.2, 39.5, gives_up="about average", position="QB"))
    assert v == ("Allen projects 5.00 more (32.30 vs 27.30); both defenses are about average — Allen has both the higher "
                 "ceiling (50.8 vs 39.5) and the safer floor (18.1 vs 15.2).")


def test_verdict_split_ceiling_and_floor():
    v = comparison_verdict(player("A Receiver", 12.0, 4.0, 24.0, gives_up="big plays"),
                           player("B Receiver", 11.5, 6.0, 20.0, gives_up="volume"))
    # same last name: the full names are used
    assert "A Receiver has the higher ceiling (24.0 vs 20.0), B Receiver the safer floor (6.0 vs 4.0)." in v


def test_verdict_without_a_projection_makes_no_call():
    v = comparison_verdict(player("Kenny Gainwell", None, None, None), player("Emanuel Wilson", 7.09, 1.2, 14.5))
    assert v == "No projection this week for Gainwell (a bye, or no games yet), so no call."
    t = comparison_rows(player("On Bye", None, None, None, opp=None), player("Emanuel Wilson", 7.09, 1.2, 14.5))
    assert set(t["On Bye"]) == {"—"}


def test_numbers_in_the_verdict_are_numbers_in_the_table():
    import re
    a = player("Chris Olave", 12.13, 5.1, 21.3, gives_up="volume", position="WR")
    b = player("Puka Nacua", 11.84, 4.6, 24.0, opp="SF", gives_up="big plays", position="WR")
    v = comparison_verdict(a, b)
    cells = " ".join(comparison_rows(a, b).drop(columns="What").to_numpy().ravel())
    for num in re.findall(r"\d+\.\d+", v):
        assert num in cells, num


# ------------------------------------------------------------------------------------------ the page
def test_page_reads_the_new_marts_and_one_projection():
    src = PAGE.read_text()
    for mart in ("mart_cb_matchup_week", "mart_cb_coverage", "mart_receiver_vs_cb", "mart_defense_position_profile",
                 "mart_player_week_projections", "mart_defense_vs_position_current"):
        assert f"analytics.{mart}" in src, mart
    assert "mart_player_week_rankings" not in src          # the old formula stays on Rankings (round-2 convention 3)
    assert "mart_matchup_cb_context" not in src            # retired: replaced by the two cornerback marts
    assert "decision_cards(league_id, roster_id, lu_week, lu_season, rows=lu_rows)" in src   # B4's cards stay on top
