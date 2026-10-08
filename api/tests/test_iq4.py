"""IQ-4 (Wave I-Q): the bye-week bug — a player whose team is on a bye this week keeps his rest of season everywhere.

The case is real, not a mock: the clock is pinned inside 2026 week 5 (Wednesday 7 Oct, 20:00 UTC, before the week's
first kickoff), the season's first bye week (Kansas City and Carolina have no game). Every path that shows a
rest-of-season number or a trade value is asked for a Chiefs or Panthers player: the reference key's list
(``anyleague.ros_table``), the house league's (``mart_player_ros_projection``), Rankings' season view, the free trade
calculator (``refleague.value_of``), the player card's ``ros`` / ``ref_value`` and the trade engine's market
(``trades.MARKET_SQL``). The cause was upstream (dbt ``int_player_week_universe`` / ``mart_kd_week`` /
``int_pn_player_week_status`` read the newest weekly roster file across all teams; a bye week's file has no row for
the teams on a bye) and has its own dbt unit tests (``dbt/models/intermediate/iq4_bye_week.yml``); these hold every
reader to "ranked by his remaining games". A database whose board lost the bye teams fails here.
"""

from __future__ import annotations

import pytest
from league_lab import clock

from .conftest import SCRUBS, needs_db

WEEK5 = "2026-10-07T20:00:00Z"
MAHOMES, KELCE, WALKER, HUBBARD, MCMILLAN = "00-0033873", "00-0030506", "00-0038134", "00-0036555", "00-0040124"
BYE = {"KC", "CAR"}


@pytest.fixture
def week5(sql):
    rows = sql("""select home_team, away_team from analytics.dim_game
                  where season = 2026 and week = 5 and season_type = 'REG'""")
    teams = {t for r in rows for t in (r["home_team"], r["away_team"])}
    if not rows or teams & BYE:
        pytest.skip("this database's 2026 week 5 is not KC's and CAR's bye")
    with clock.pinned(WEEK5):
        yield teams


def _games_left(sql, team: str, first: int, last: int) -> int:
    r = sql("""select count(*) as n from analytics.dim_game where season = 2026 and season_type = 'REG'
               and week between %s and %s and %s in (home_team, away_team)""", (first, last, team))
    return int(r[0]["n"])


def _teams_in_window(sql, first: int, last: int) -> set[str]:
    rows = sql("""select home_team, away_team from analytics.dim_game where season = 2026 and season_type = 'REG'
                  and week between %s and %s""", (first, last))
    return {t for r in rows for t in (r["home_team"], r["away_team"])}


@needs_db
@pytest.mark.parametrize("league", ["ref:half", SCRUBS])
def test_ros_keeps_bye_teams_ranked_by_their_remaining_games(client, sql, week5, league):
    r = client.get(f"/api/ros?league={league}&position=QB&limit=500")
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    ps = {p["gsis_id"]: p for p in d["players"] if p.get("gsis_id")}
    assert MAHOMES in ps, "Mahomes (KC, bye in week 5) is missing from the rest-of-season list"
    m = ps[MAHOMES]
    assert m["pos_rank"] is not None and m["ros_points"] > 0
    assert m["ros_games"] == _games_left(sql, "KC", d["from_week"], d["last_week"])
    assert 5 in m["bye_weeks"] and m["week_points"] is None
    # the coverage rule: every team with a game in the window has a quarterback in the list
    have = {p["team"] for p in d["players"]}
    want = _teams_in_window(sql, d["from_week"], d["last_week"])
    assert want - have == set(), f"teams missing from the list: {sorted(want - have)}"


@needs_db
@pytest.mark.parametrize("league", ["ref:half", SCRUBS])
def test_rankings_season_view_says_bye_this_week(client, week5, league):
    seen = {}
    for pos in ("QB", "RB", "TE", "WR"):
        r = client.get(f"/api/rankings?league={league}&view=season&position={pos}&limit=200")
        assert r.status_code == 200, r.text[:300]
        for x in r.json()["rows"]:
            seen[x.get("gsis_id")] = x
    for g in (MAHOMES, KELCE, WALKER, HUBBARD, MCMILLAN):
        assert g in seen, f"{g} missing from Rankings' rest of season"
        x = seen[g]
        assert x["rank"] is not None and x["proj_points"] > 0
        assert x["bye_this_week"] is True and x["opponent"] is None
    others = [x for x in seen.values() if x.get("team") not in BYE and x.get("opponent")]
    assert others and all(x["bye_this_week"] is False for x in others)


@needs_db
def test_free_trade_calculator_values_a_bye_player(client, week5):
    r = client.get(f"/api/trade-calc/free?league=ref:half&give={MAHOMES},{KELCE}&get={HUBBARD},{MCMILLAN},{WALKER}")
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    for side in ("give", "get"):
        assert d[side]["unknown"] == []
        for p in d[side]["players"]:
            assert p["no_projection"] is False and p["value"] is not None and p["ros_points"] > 0, p["player_name"]
            assert p["outlook"]["bye"] is True and p["outlook"]["points"] is None
            assert p["outlook"]["games"] == d["window"]["last"] - d["window"]["first"]   # one bye inside the window


@needs_db
@pytest.mark.parametrize("league", ["ref:half", SCRUBS])
def test_card_carries_a_bye_players_rest_of_season(client, week5, league):
    r = client.get(f"/api/player/{MAHOMES}?league={league}")
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    assert d["ros"] is not None and d["ros"]["points"] > 0 and d["ros"]["pos_rank"] is not None
    if league.startswith("ref:"):
        assert d["ref_value"] is not None and d["ref_value"]["value"] is not None


@needs_db
def test_trade_market_counts_a_bye_players_remaining_weeks(sql, week5):
    from league_lab import trades as T
    rows = sql(T.MARKET_SQL, (SCRUBS, 2026, 5))
    pts = {r["player_key"]: float(r["season_points"]) for r in rows}
    for g in (MAHOMES, KELCE, HUBBARD):
        assert pts.get(g, 0) > 0, f"{g} has no rest-of-season market value in the house league"
