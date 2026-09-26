"""Sleeper payload -> raw row shaping, using the real API shapes captured on 2026-09-25."""
import psycopg

from league_lab.ingest import sleeper as s
from league_lab.ingest.sleeper import SleeperIngester, SleeperRun

LEAGUE = {"league_id": "1389709692405551104", "name": "League of Scrubs", "season": "2026", "status": "in_season",
          "previous_league_id": "1256450429399617536", "draft_id": "1389709692405551105", "total_rosters": 10,
          "sport": "nfl", "season_type": "regular",
          "settings": {"playoff_week_start": 15, "playoff_teams": 4, "num_teams": 10, "leg": 3, "last_scored_leg": 2},
          "scoring_settings": {"rec": 0.5, "pass_td": 4.0},
          "roster_positions": ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "FLEX", "K", "DEF", "BN"]}

MATCHUP = {"points": 109.98, "players": ["12495", "8183", "WAS"], "roster_id": 1, "custom_points": None, "matchup_id": 1,
           "starters": ["8183", "0", "WAS"], "starters_points": [18.78, 0, 10.0],
           "players_points": {"12495": 0.8, "8183": 18.78, "WAS": 10.0}}


def _ingester():
    ing = SleeperIngester.__new__(SleeperIngester)
    ing.run = SleeperRun(league_id="1389709692405551104", offline=True)
    return ing


def test_weeks_to_fetch_completed_and_live():
    ing = _ingester()
    state = {"season": "2026", "display_week": 3}
    assert list(ing.weeks_to_fetch(dict(LEAGUE, status="complete", settings={"last_scored_leg": 16}), state)) == list(range(1, 17))
    assert list(ing.weeks_to_fetch(LEAGUE, state)) == [1, 2, 3]
    # a prior season still "in_season" (never closed) falls back to the full range
    assert len(ing.weeks_to_fetch(dict(LEAGUE, season="2025"), state)) == 18


def test_matchup_values_keep_ids_as_text_and_points_map():
    m = MATCHUP
    assert s._as_text_list(m["starters"]) == ["8183", "0", "WAS"]
    assert s._as_int(m["roster_id"]) == 1
    assert isinstance(s._jsonb(m["players_points"]), psycopg.types.json.Jsonb)
    assert s._jsonb(None) is None


def test_helpers_tolerate_missing_and_mixed_values():
    assert s._as_int("7") == 7 and s._as_int(None) is None and s._as_int("") is None and s._as_int("x") is None
    assert s._as_text_list(None) is None and s._as_text_list([1, "a"]) == ["1", "a"]
    assert s._as_int_list([1, "2", None, "x"]) == [1, 2]
