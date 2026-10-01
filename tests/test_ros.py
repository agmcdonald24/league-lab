"""E2 rest of season: the words (app/lib/ros.py, no database) and the mart (analytics.mart_player_ros_projection)
recomputed independently in Python from the weekly board, the schedule and the league's playoff settings. The database
part is skipped when .env's database is not reachable or the mart is not built."""

import math
import sys
from pathlib import Path

import pandas as pd
import pytest

APP = Path(__file__).resolve().parents[1] / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from lib import ros as ROS  # noqa: E402

ROW = {"player_key": "00-0036963", "gsis_id": "00-0036963", "player_name": "Amon-Ra St. Brown", "position": "WR",
       "is_ranked": True, "roster_status": "ACT", "from_week": 4, "last_week": 17, "playoff_week_start": 15,
       "ros_games": 13, "ros_points": 231.66, "ros_p10": 190.4, "ros_p90": 272.9, "playoff_games": 3,
       "playoff_points": 53.5, "ros_rank_pos": 4, "ros_rank_all": 9, "bye_weeks": [6], "weeks_with_lines": 1,
       "weeks_json": [[4, 18.1], [5, 18.0], [7, 17.7]]}


def test_card_line_says_points_games_range_rank_and_playoffs():
    line = ROS.card_line(ROW)
    assert line == ("Rest of season: **232 points** over 13 games (likely 190–273), **WR4** in this league · "
                    "playoffs (weeks 15–17): 54")


def test_card_line_unranked_and_no_range():
    r = {**ROW, "ros_rank_pos": None, "is_ranked": False, "roster_status": "RES", "ros_p10": None, "ros_p90": None}
    line = ROS.card_line(r)
    assert "not ranked (on injured reserve)" in line and "likely" not in line
    r["roster_status"] = "INA"
    assert "not on an active NFL roster" in ROS.card_line(r)


def test_playoff_window_shrinks_and_ends():
    assert ROS.playoff_window(ROW) == "weeks 15–17"
    assert ROS.playoff_window({**ROW, "from_week": 16}) == "weeks 16–17"
    assert ROS.playoff_window({**ROW, "from_week": 17}) == "week 17"
    assert ROS.playoff_window({**ROW, "playoff_week_start": 18}) is None


def test_weeks_words_names_the_bye_and_unknown_weeks():
    words = ROS.weeks_words({**ROW, "last_week": 8})
    assert words == "wk 4 18.1 · 5 18.0 · 6 bye · 7 17.7 · 8 none"
    assert ROS.weeks_words({**ROW, "weeks_json": '[[4, 18.1]]', "last_week": 4}) == "wk 4 18.1"


def test_lines_note():
    assert ROS.lines_note(ROW).startswith("Only week 4 has betting lines yet")
    assert ROS.lines_note({**ROW, "weeks_with_lines": 0}).startswith("No week has betting lines yet")
    assert "in League of Scrubs scoring" in ROS.lines_note(ROW, "League of Scrubs")


def test_package_points_rounds_each_player_first_and_names_the_unknown():
    rows = pd.DataFrame([{"player_key": "a", "ros_points": 10.5, "ros_games": 12},
                         {"player_key": "b", "ros_points": 10.5, "ros_games": 13},
                         {"player_key": "c", "ros_points": 0.49, "ros_games": 1}])
    assert ROS.package_points(rows, ["a", "b"]) == (22, 25, [])       # 11 + 11, not round(21.0)
    assert ROS.package_points(rows, ["c", "zz"]) == (0, 1, ["zz"])
    assert ROS.package_points(pd.DataFrame(), ["a"]) == (0, 0, ["a"])
    s = ROS.package_sentence(142, 171, "weeks 4–16", ["Joe"])
    assert "you give **142** points, you get **171** (+29)" in s and "No projection yet for Joe" in s


def test_whole_and_rank_label():
    assert ROS.whole(141.5) == 142 and ROS.whole(None) is None and ROS.whole(float("nan")) is None
    assert ROS.rank_label(ROW) == "WR4" and ROS.rank_label({**ROW, "ros_rank_pos": float("nan")}) is None


# ------------------------------------------------------------------------------ the mart, on the database
@pytest.fixture(scope="module")
def conn():
    psycopg = pytest.importorskip("psycopg")
    from league_lab.config import get_settings

    try:
        c = psycopg.connect(get_settings().pipeline_dsn(), connect_timeout=3, autocommit=True)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"no database: {exc}")
    with c:
        if not c.execute("select to_regclass('analytics.mart_player_ros_projection')").fetchone()[0]:
            pytest.skip("mart_player_ros_projection not built")
        yield c


def _frame(conn, sql: str, params: tuple = ()) -> pd.DataFrame:
    cur = conn.execute(sql, params)
    return pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])


def test_mart_reproduces_from_the_board(conn):
    """Every row: the window is lib.ui's week rule to the league's final (winners-bracket rounds), byes are weeks with
    no game for his team, the totals are the board's weekly projections added up, the range follows the stated
    independence assumption, and the ranks are the order of the totals among ranked players."""
    from lib.ui import first_open_week

    mart = _frame(conn, "select * from analytics.mart_player_ros_projection")
    if mart.empty:
        pytest.skip("no weeks left in the season")
    games = _frame(conn, "select season, week, kickoff_at, home_team, away_team from analytics.dim_game where season_type = 'REG'")
    for league_id, m in mart.groupby("league_id"):
        lg = _frame(conn, """select l.season, l.playoff_week_start, l.playoff_teams,
                                    (select max(round) from staging.stg_sleeper__brackets b
                                     where b.league_id = l.league_id and b.bracket_type = 'winners') as rounds,
                                    coalesce((r.payload -> 'settings' ->> 'playoff_round_type')::int, 0) as round_type
                             from analytics.dim_league_season l join raw.sleeper_league r using (league_id)
                             where l.league_id = %s""", (league_id,)).iloc[0]
        season = int(lg["season"])
        g = games[games["season"] == season]
        from_week = first_open_week(g[["week", "kickoff_at"]], now=pd.Timestamp(m["built_at"].iloc[0]))   # the clock at build time
        rounds = int(lg["rounds"]) if pd.notna(lg["rounds"]) else math.ceil(math.log2(int(lg["playoff_teams"])))
        rt = int(lg["round_type"])
        last_week = min(int(g["week"].max()), int(lg["playoff_week_start"]) - 1 + rounds * (2 if rt == 2 else 1) + (1 if rt == 1 else 0))
        assert set(m["from_week"]) == {from_week} and set(m["last_week"]) == {last_week}
        board = _frame(conn, """select coalesce(gsis_id, case team when 'LA' then 'LAR' else team end) as player_key, week, team,
                                       proj_points, p10, p90
                                from analytics.mart_player_week_projections
                                where league_id = %s and season = %s and week between %s and %s and proj_points is not null""",
                       (league_id, season, from_week, last_week))
        plays = {(int(r.week), t) for r in g.itertuples() for t in (r.home_team, r.away_team)}
        board = board[[(int(w), t) in plays for w, t in zip(board["week"], board["team"], strict=True)]]
        board["var"] = ((board["p90"].astype(float) - board["p10"].astype(float)) / 2.563) ** 2
        po = int(lg["playoff_week_start"])
        exp = board.groupby("player_key").agg(
            ros_points=("proj_points", lambda s: round(float(s.astype(float).sum()), 2)), ros_games=("week", "size"),
            sd=("var", lambda s: math.sqrt(s.sum())))
        exp["playoff_points"] = board[board["week"] >= po].groupby("player_key")["proj_points"].apply(
            lambda s: round(float(s.astype(float).sum()), 2)).reindex(exp.index).fillna(0.0)
        got = m.set_index("player_key")
        assert set(exp.index) == set(got.index), "same players"
        j = exp.join(got[["ros_points", "ros_games", "playoff_points", "ros_p10", "ros_p90", "ros_sd"]], rsuffix="_mart")
        assert (j["ros_games"] == j["ros_games_mart"]).all()
        assert (j["ros_points"] - j["ros_points_mart"].astype(float)).abs().max() < 0.005
        assert (j["playoff_points"] - j["playoff_points_mart"].astype(float)).abs().max() < 0.005
        assert (j["sd"] - j["ros_sd"].astype(float)).abs().max() < 0.006
        p90 = j["ros_points"] + 1.2816 * j["sd"]
        assert (p90 - j["ros_p90"].astype(float)).abs().max() < 0.06
        # byes: every player whose team has a bye inside the window shows one fewer game than the window's weeks
        for key, r in got.iterrows():
            team_weeks = {w for (w, t) in plays if t == r["team"] and from_week <= w <= last_week}
            assert list(r["bye_weeks"]) == sorted(set(range(from_week, last_week + 1)) - team_weeks), key
        # ranks: the order of the totals among ranked players, by position and overall
        ranked = got[got["is_ranked"]]
        for pos, sub in ranked.groupby("position"):
            order = sub.sort_values(["ros_points", "player_key"], ascending=[False, True], key=lambda s: s if s.name == "player_key" else s.astype(float))
            assert order["ros_rank_pos"].astype(int).tolist() == list(range(1, len(order) + 1)), pos
        assert got.loc[~got["is_ranked"], ["ros_rank_pos", "ros_rank_all"]].isna().all().all()


def test_mart_matches_the_trade_engines_sum_on_the_same_weeks(conn):
    """The trade engine's market (league_lab.trades.MARKET_SQL, ops.projections) over the same weeks adds up to the same
    totals: one projection everywhere."""
    from league_lab import trades as T

    mart = _frame(conn, "select league_id, season, from_week, last_week, player_key, ros_points from analytics.mart_player_ros_projection")
    if mart.empty:
        pytest.skip("no weeks left in the season")
    for (league_id, season, w0, w1), m in mart.groupby(["league_id", "season", "from_week", "last_week"]):
        sql = T.MARKET_SQL.replace("week >= %s", "week between %s and %s")
        eng = _frame(conn, sql, (league_id, int(season), int(w0), int(w1))).set_index("player_key")
        got = m.set_index("player_key")["ros_points"].astype(float)
        assert (eng.reindex(got.index)["season_points"] - got).abs().max() < 0.005
