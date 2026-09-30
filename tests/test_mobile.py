"""C1 (U-13): the one week rule (lib.ui.current_week) and the Phone table-detail level (lib.table).

No database: current_week() is checked on synthetic schedules (the pure first_open_week and the wired helper with
query() replaced), the Phone column choice on synthetic frames, and show() with st.dataframe captured.
"""

import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pandas as pd
import pytest

APP = Path(__file__).resolve().parents[1] / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from lib import cards, table  # noqa: E402
from lib import ui as app_ui  # noqa: E402

ET = "America/New_York"


def kick(s: str) -> pd.Timestamp:
    return pd.Timestamp(s, tz=ET).tz_convert("UTC")


# NFL 2026 weeks 3-5 as the schedule has them (Thursday, Sunday early / late / night, Monday), in ET
SCHEDULE = pd.DataFrame(
    [(3, kick(t)) for t in ("2026-09-24 20:15", "2026-09-27 13:00", "2026-09-27 16:25", "2026-09-27 20:20", "2026-09-28 20:15")]
    + [(4, kick(t)) for t in ("2026-10-01 20:15", "2026-10-04 13:00", "2026-10-04 16:25", "2026-10-04 20:20", "2026-10-05 20:15")]
    + [(5, kick(t)) for t in ("2026-10-08 20:15", "2026-10-11 13:00", "2026-10-11 20:20", "2026-10-12 20:15")],
    columns=["week", "kickoff_at"],
)


# ------------------------------------------------------------------------------ current_week: three fixtures
def test_before_thursday_is_the_coming_week():
    # Tuesday after week 3's Monday game: week 3 is over, week 4 has not started
    assert app_ui.first_open_week(SCHEDULE, kick("2026-09-29 10:00")) == 4
    # Thursday night's game has kicked off: still week 4 (its players are locked, the rest is still to decide)
    assert app_ui.first_open_week(SCHEDULE, kick("2026-10-01 21:00")) == 4


def test_after_the_monday_game_kicks_off_the_next_week_starts():
    assert app_ui.first_open_week(SCHEDULE, kick("2026-10-05 20:14")) == 4       # a minute before Monday's kickoff
    assert app_ui.first_open_week(SCHEDULE, kick("2026-10-05 20:16")) == 5       # Monday's game under way: week 5


def test_off_season_has_no_current_week():
    assert app_ui.first_open_week(SCHEDULE, kick("2027-02-20 12:00")) is None
    assert app_ui.first_open_week(SCHEDULE.iloc[0:0], kick("2026-09-29 10:00")) is None       # no schedule loaded


def test_naive_now_is_utc_and_per_week_rows_work():
    per_week = SCHEDULE.groupby("week", as_index=False)["kickoff_at"].max()           # week_schedule()'s shape
    assert app_ui.first_open_week(per_week, pd.Timestamp("2026-09-30 14:07")) == 4   # naive = UTC


def test_current_week_reads_the_league_season_and_the_schedule(monkeypatch):
    seen = []

    def fake_query(sql, params=None):
        seen.append((" ".join(sql.split()), params))
        if "from analytics.dim_league_season where league_id" in " ".join(sql.split()):
            return pd.DataFrame({"season": [2026]})
        if "from analytics.dim_game" in sql:
            per_week = SCHEDULE.groupby("week", as_index=False).agg(first_kickoff=("kickoff_at", "min"), kickoff_at=("kickoff_at", "max"))
            return per_week
        raise AssertionError(sql)

    monkeypatch.setattr(app_ui, "query", fake_query)
    assert app_ui.current_week("L1", now=kick("2026-09-29 10:00")) == 4
    assert app_ui.current_week("L1", now=kick("2026-10-06 09:00")) == 5
    assert app_ui.current_week("L1", now=kick("2027-03-01 09:00")) is None
    assert any(p == ("L1",) for _, p in seen) and any(p == (2026,) for _, p in seen)
    assert app_ui.week_first_kickoff(2026, 4) == kick("2026-10-01 20:15")


def test_the_cards_use_the_same_rule(monkeypatch):
    monkeypatch.setattr(cards, "current_week", lambda league_id=None, season=None, now=None: 7 if season == 2026 else None)
    assert cards.decision_week(2026) == 7 and cards.decision_week(2031) is None


def test_align_opponents_rekeys_the_next_game_to_the_week(monkeypatch):
    def fake_query(sql, params=None):
        if "from analytics.dim_game" in sql:
            return pd.DataFrame({"team": ["DET", "CAR"], "opponent": ["CAR", "DET"], "is_home": [True, False],
                                 "kickoff_at": [kick("2026-10-04 13:00")] * 2})
        return pd.DataFrame({"defense": ["CAR", "DET"], "position": ["WR", "WR"], "rank_std": [21, 9], "rank_l4": [20, 8],
                             "points_allowed_per_game_std": [25.0, 31.0]})

    monkeypatch.setattr(app_ui, "query", fake_query)
    df = pd.DataFrame({"player_name": ["Amon-Ra St. Brown", "Bye guy", "Free agent"], "nfl_team": ["DET", "SF", None],
                       "position": ["WR", "WR", "WR"], "opponent": ["GB", "LA", None], "is_bye": [False, False, False],
                       "opp_rank_std": [12, 3, None]})
    out = app_ui.align_opponents(df, 2026, 4)
    assert out["opponent"].tolist()[0] == "CAR" and pd.isna(out["opponent"].tolist()[1])
    assert out["is_bye"].tolist() == [False, True, False]
    assert out["opp_rank_std"].tolist()[0] == 21 and pd.isna(out["opp_rank_std"].tolist()[1])
    assert list(out.columns) == list(df.columns)                                           # only existing columns replaced


# ------------------------------------------------------------------------------ the Phone level: column choice
WIDE = pd.DataFrame({
    "gsis_id": ["00-1", "00-2"], "player_name": ["A", "B"], "position": ["WR", "RB"], "nfl_team": ["DET", "SF"],
    "team_targets": [30, 28], "injury_status": [None, "Healthy"], "practice_status": ["Full", None], "is_on_ir": [False, False],
    "ppg_std": [20.1, 12.0], "expected_per_game": [18.0, 13.2], "target_share": [0.3, 0.1], "opponent": ["CAR", "LA"],
})


def test_phone_takes_the_first_five_essentials():
    cols = ["player_name", "position", "nfl_team", "team_targets", "injury_status", "ppg_std", "expected_per_game", "target_share", "opponent"]
    # team_targets is advanced (a denominator), injury_status is all healthy: neither is shown
    assert table.phone_columns(WIDE, cols) == ["player_name", "position", "nfl_team", "ppg_std", "expected_per_game"]


def test_phone_uses_the_callers_choice_and_never_more_than_five():
    got = table.phone_columns(WIDE, list(WIDE.columns), phone_cols=["player_name", "opponent", "ppg_std", "target_share", "position", "nfl_team"])
    assert got == ["player_name", "opponent", "ppg_std", "target_share", "position"]


def test_phone_shows_an_injury_column_only_when_a_row_is_not_healthy():
    hurt = WIDE.assign(injury_status=[None, "Questionable"])
    cols = ["player_name", "position", "nfl_team", "injury_status", "ppg_std", "expected_per_game", "opponent"]
    assert table.phone_columns(hurt, cols) == ["player_name", "position", "nfl_team", "ppg_std", "injury_status"]
    # an IR flag counts too; practice status alone ("Full") is not an injury
    ir = WIDE.assign(is_on_ir=[False, True])
    assert table.phone_columns(ir, ["player_name", "is_on_ir", "ppg_std"]) == ["player_name", "ppg_std", "is_on_ir"]
    assert table.phone_columns(WIDE, ["player_name", "practice_status", "ppg_std"]) == ["player_name", "ppg_std"]
    # the caller's phone_cols never smuggle in a healthy injury column
    assert table.phone_columns(WIDE, None, phone_cols=["player_name", "injury_status", "ppg_std"]) == ["player_name", "ppg_std"]


def test_phone_without_a_column_list_skips_ids():
    got = table.phone_columns(WIDE.drop(columns=["team_targets"]), None)
    assert "gsis_id" not in got and len(got) == 5 and got[0] == "player_name"
    assert "gsis_id" not in table.phone_columns(WIDE, ["gsis_id", "player_name", "ppg_std"])      # an id is never one of the five


def test_not_healthy_reads_words_flags_and_blanks():
    s = pd.Series([None, "", "Healthy", "ACT", "Questionable", "Out", float("nan"), "IR"])
    assert table.not_healthy(s).tolist() == [False, False, False, False, True, True, False, True]
    assert table.not_healthy(pd.Series([False, True])).tolist() == [False, True]


@pytest.mark.parametrize(("ua", "level"), [
    ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1", "phone"),
    ("Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Mobile Safari/537.36", "phone"),
    ("Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/604.1", "essentials"),
    ("Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15", "essentials"),
    ("", "essentials"),
])
def test_default_level_follows_the_browser(ua, level):
    assert table.default_detail_level(ua) == level


# ------------------------------------------------------------------------------ show() at the Phone level, links
def _capture(monkeypatch, level):
    seen = {}
    monkeypatch.setattr(table.st, "dataframe", lambda data, **kw: seen.update(data=data, **kw))
    monkeypatch.setattr(table, "detail_level", lambda: level)
    monkeypatch.setattr(app_ui, "_link_context", lambda: {"league": "L1", "team": "12"})
    return seen


def test_show_at_phone_is_five_columns_first_pinned_and_linked(monkeypatch):
    seen = _capture(monkeypatch, "phone")
    table.show(WIDE, list(WIDE.columns))
    assert list(seen["data"].columns) == ["player_name", "position", "nfl_team", "ppg_std", "expected_per_game"]
    cfg = seen["column_config"]
    assert cfg["player_name"]["pinned"] is True and cfg["player_name"]["type_config"]["type"] == "link"
    assert parse_qs(urlsplit(seen["data"]["player_name"].iloc[0]).query)["id"] == ["00-1"]


def test_show_at_essentials_keeps_the_callers_columns(monkeypatch):
    seen = _capture(monkeypatch, "essentials")
    table.show(WIDE, ["player_name", "team_targets", "ppg_std", "expected_per_game", "target_share", "opponent"])
    assert list(seen["data"].columns) == ["player_name", "ppg_std", "expected_per_game", "target_share", "opponent"]
    assert seen["column_config"]["player_name"].get("pinned") is not True


def test_two_players_per_row_link_both(monkeypatch):
    seen = _capture(monkeypatch, "essentials")
    moves = pd.DataFrame({"add_gsis_id": ["00-7", "00-8"], "add_name": ["Mike Gesicki", "Tyler Allgeier"],
                          "drop_gsis_id": ["00-9", None], "drop_name": ["Isaiah Likely", None],
                          "waiver_claim": ["Mike Gesicki TE", "Tyler Allgeier RB"], "waiver_drop": ["Isaiah Likely", None],
                          "weekly_gain": [2.9, 0.4]})
    table.show(moves, ["waiver_claim", "waiver_drop", "weekly_gain"],
               links={"waiver_claim": ("add_gsis_id", "add_name"), "waiver_drop": ("drop_gsis_id", "drop_name")})
    claim, drop = seen["data"]["waiver_claim"].tolist(), seen["data"]["waiver_drop"].tolist()
    assert parse_qs(urlsplit(claim[0]).query) == {"name": ["Mike Gesicki TE"], "id": ["00-7"], "league": ["L1"], "team": ["12"]}
    assert parse_qs(urlsplit(drop[0]).query)["id"] == ["00-9"]
    assert pd.isna(drop[1])                                                           # an open roster spot: no drop, no link
    for c in ("waiver_claim", "waiver_drop"):
        assert seen["column_config"][c]["type_config"]["type"] == "link"


def test_a_shown_label_without_an_id_searches_the_bare_name(monkeypatch):
    seen = _capture(monkeypatch, "essentials")
    df = pd.DataFrame({"gsis_id": [None], "player_name": ["Kansas City Chiefs"], "player": ["Kansas City Chiefs (DEF)"], "v": [1.0]})
    table.show(df, ["player", "v"], links={"player": ("gsis_id", "player_name")})
    assert parse_qs(urlsplit(seen["data"]["player"].iloc[0]).query) == {"name": ["Kansas City Chiefs"], "league": ["L1"], "team": ["12"]}


def test_kicker_names_link_by_default(monkeypatch):
    seen = _capture(monkeypatch, "essentials")
    table.show(pd.DataFrame({"gsis_id": ["00-0035358"], "kicker_name": ["Chase McLaughlin"], "points": [9.0]}), ["kicker_name", "points"])
    assert seen["column_config"]["kicker_name"]["type_config"]["type"] == "link"
