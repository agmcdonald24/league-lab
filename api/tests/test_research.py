"""Plan G1 (Wave G): the research routes for any league — /api/trends, /api/matchups/defense, /api/matchups/cb,
/api/players, /api/receivers, /api/compare, /api/player/{gsis}/games.

Every route against both house leagues (shapes + a number checked against the mart with independent SQL), the
on-demand path (the same house league served from the Sleeper fixtures with `source=sleeper`: points priced on
request with `scoring.compute_points` equal the league marts to 0.01), the fictional Test League, and the errors."""

from __future__ import annotations

import json

import pandas as pd
import pytest
from league_lab import anyleague as A
from league_lab import research as R
from league_lab import sleeper_client as SC

from league_lab_api import research

from .conftest import ANDREW, DYNASTY, SCRUBS, SLEEPER_FIXTURES, needs_db

pytestmark = needs_db
TEST_LEAGUE = "9000000000000000001"
HOUSE = [DYNASTY, SCRUBS]
PLAYER_KEYS = {"gsis_id", "player_name", "position", "team", "headshot_url", "rostered_by_roster_id", "rostered_by_team"}
CHASE, NABERS = "00-0036900", "00-0039337"


@pytest.fixture(autouse=True)
def _fresh_research_cache():
    research.clear_priced()
    yield
    research.clear_priced()


def _scorings(sql) -> dict[str, dict]:
    return {r["league_id"]: {k: float(v) for k, v in r["scoring_settings"].items() if v is not None}
            for r in sql("select league_id, scoring_settings from analytics.dim_league_season where is_current_season")}


def _f(v):
    return None if v is None else float(v)


# ------------------------------------------------------------------------------ the pricing (the acceptance)
@pytest.mark.parametrize("season", [2025, 2026])
@pytest.mark.parametrize("league", HOUSE)
def test_priced_on_request_equals_the_league_mart(sql, league, season):
    """Every NFL game of the season priced with scoring.compute_points (the position passed) = fct_player_game_league
    to 0.01 — the acceptance of plan G1, both house leagues, every row."""
    cols = ", ".join(f"p.{c}" for c in R.PRICE_COLUMNS)
    rows = sql(f"""select p.gsis_id, p.game_id, p.position, p.has_stat_row, {cols}, l.points as mart
                   from analytics.fct_player_game p
                   join analytics.fct_player_game_league l on l.league_id = %s and l.gsis_id = p.gsis_id and l.game_id = p.game_id
                   where p.season = %s""", (league, season))
    df = pd.DataFrame(rows)
    priced = R.price_games(df, _scorings(sql)[league])
    diff = (priced - df["mart"].astype(float)).abs()
    assert len(df) > 2000 and priced.notna().all()
    assert diff.max() <= 0.01, df.loc[diff.idxmax(), ["gsis_id", "game_id"]].to_dict()


@pytest.mark.parametrize("league", HOUSE)
def test_priced_expected_points(sql, league):
    """Expected points priced from a house league's: exact when the two agree on the keys the published expected line
    lacks (the league itself; the Test League from Scrubs); dynasty <-> Scrubs differ on interceptions only."""
    sc = _scorings(sql)
    other = SCRUBS if league == DYNASTY else DYNASTY
    ecols = ", ".join(f"e.{c}" for c in R.EXPECTED_COLUMNS.values())
    for ref in (league, other):
        df = pd.DataFrame(sql(f"""select p.gsis_id, p.position, {ecols}, r.points_expected as ref_expected, l.points_expected as mart
                                  from analytics.fct_player_game p
                                  join analytics.mart_player_expected_points e on e.gsis_id = p.gsis_id and e.game_id = p.game_id
                                  join analytics.fct_player_game_league r on r.league_id = %s and r.gsis_id = p.gsis_id and r.game_id = p.game_id
                                  join analytics.fct_player_game_league l on l.league_id = %s and l.gsis_id = p.gsis_id and l.game_id = p.game_id
                                  where p.season = 2025 and l.expected_known""", (ref, league)))
        diff = (R.price_expected(df, sc[league], sc[ref]) - df["mart"].astype(float)).abs()
        if ref == league:
            assert diff.max() <= 0.01
        else:   # the approximation: the interception weight (-2 vs -1) times expected interceptions (the passers')
            assert (diff[df["position"] != "QB"] > 0.0101).mean() < 0.03 and 0.3 < diff[df["position"] == "QB"].mean() < 1.0
    assert R.expected_reference(sc[league], sc) == (league, True)
    assert R.expected_reference(sc[league], sc, exclude=league) == (other, False)
    test = json.loads((SLEEPER_FIXTURES / f"league_{TEST_LEAGUE}.json").read_text())["scoring_settings"]
    assert R.expected_reference({k: float(v) for k, v in test.items()}, sc) == (SCRUBS, True)


@pytest.mark.parametrize("league", HOUSE)
def test_season_twins_reproduce_the_marts(sql, league):
    """research.season_table over the league's game rows = mart_league_player_season (every column, 2025), and for the
    reference league the trend windows / points allowed = the reference-scored NFL marts."""
    from league_lab_api.db import query
    ctx = research.context(league)
    g = research.league_games(ctx, 2025)
    st = R.season_table(g[g["season_type"] == "REG"])
    m = pd.DataFrame(sql("select * from analytics.mart_league_player_season where league_id = %s and season = 2025", (league,)))
    j = st.merge(m, on="gsis_id", suffixes=("", "_m"))
    assert len(j) == len(m) == len(st)
    for c in research.LPS_COLS[1:]:
        a, b = pd.to_numeric(j[c], errors="coerce").astype(float), pd.to_numeric(j[c + "_m"], errors="coerce").astype(float)
        assert ((a - b).abs().fillna(0) <= 0.01).all() and (a.isna() == b.isna()).all(), c
    if league == SCRUBS:      # the reference league: its scoring is the NFL marts'
        tw = R.trend_windows(g[g["season_type"] == "REG"])
        tt = query("select gsis_id, games, points_l3, points_change, expected_points_l3, expected_points_change "
                   "from analytics.mart_player_trend_tags where season = 2025", ())
        j = tw.merge(tt, on="gsis_id", suffixes=("", "_m"))
        assert len(j) == len(tt)
        for c in ("games", "points_l3", "points_change", "expected_points_l3", "expected_points_change"):
            assert ((j[c].astype(float) - j[c + "_m"].astype(float)).abs().fillna(0) <= 0.001).all(), c
        da = R.defense_allowed(g[g["season_type"] == "REG"])
        dt = query("select * from analytics.mart_defense_trends where season = 2025", ())
        j = da.merge(dt, on=["defense", "position"], suffixes=("", "_m"))
        assert len(j) == 160 and (j["direction"] == j["direction_m"]).all()
        assert ((j["change"].astype(float) - j["change_m"].astype(float)).abs().fillna(0) <= 0.01).all()


# ------------------------------------------------------------------------------ /api/player/{gsis}/games
@pytest.mark.parametrize("league", HOUSE)
def test_games_route_and_on_demand_parity(client, sql, league):
    gsis = CHASE
    d = client.get(f"/api/player/{gsis}/games?league={league}&season=2025").json()
    assert d["source"] == "database" and set(d["player"]) == PLAYER_KEYS and d["player"]["headshot_url"]
    mart = {r["game_id"]: r for r in sql("""select game_id, points, points_expected from analytics.fct_player_game_league
                                            where league_id = %s and gsis_id = %s and season = 2025""", (league, gsis))}
    assert len(d["games"]) == len(mart) >= 16
    g0 = d["games"][0]
    assert {"season", "season_type", "week", "opponent", "is_home", "targets", "receptions", "receiving_yards", "points",
            "expected_points", "points_ref", "expected_points_ref"} <= set(g0)
    for g in d["games"]:
        assert g["points"] == pytest.approx(float(mart[g["game_id"]]["points"]), abs=0.005)
        assert g["expected_points"] == pytest.approx(_f(mart[g["game_id"]]["points_expected"]), abs=0.005)
    o = client.get(f"/api/player/{gsis}/games?league={league}&season=2025&source=sleeper").json()
    assert o["source"] == "sleeper" and o["expected_points_exact"] is True
    for a, b in zip(d["games"], o["games"], strict=True):
        assert a["game_id"] == b["game_id"] and a["points"] == pytest.approx(b["points"], abs=0.01)
        assert a["expected_points"] == pytest.approx(b["expected_points"], abs=0.01)
    reg = client.get(f"/api/player/{gsis}/games?league={league}&season=2025&season_type=REG").json()
    assert {g["season_type"] for g in reg["games"]} == {"REG"}


# ------------------------------------------------------------------------------ /api/trends
@pytest.mark.parametrize("league", HOUSE)
def test_trends_route(client, sql, league):
    d = client.get(f"/api/trends?league={league}&season=2025&limit=20&view=over").json()
    assert d["source"] == "database" and d["view"] == "over" and len(d["players"]) == 20 and d["total"] >= 20
    gaps = [p["gap"] for p in d["players"]]
    assert gaps == sorted(gaps, reverse=True) and all(g > 0 for g in gaps)
    p = d["players"][0]
    assert PLAYER_KEYS <= set(p) and {"ppg", "xppg", "gap", "gap_direction", "momentum", "tags", "metrics", "role_alert",
                                      "points_l3", "points_l3_ref", "expected_points_l3_ref"} <= set(p)
    assert p["gap_direction"] == "over"
    m = sql("""select ppg, expected_per_game, diff_per_game from analytics.mart_league_player_season
               where league_id = %s and gsis_id = %s and season = 2025""", (league, p["gsis_id"]))[0]
    assert (p["ppg"], p["xppg"], p["gap"]) == (float(m["ppg"]), float(m["expected_per_game"]), float(m["diff_per_game"]))
    t = sql("select points_l3, momentum from analytics.mart_player_trend_tags where gsis_id = %s and season = 2025",
            (p["gsis_id"],))[0]
    assert p["points_l3_ref"] == pytest.approx(float(t["points_l3"])) and p["momentum"] == pytest.approx(_f(t["momentum"]))
    if league == SCRUBS:                      # the reference league: its own points are the _ref ones
        assert p["points_l3"] == pytest.approx(float(t["points_l3"]), abs=0.01)
    u = client.get(f"/api/trends?league={league}&season=2025&limit=20&view=under").json()
    assert all(x["gap"] < 0 for x in u["players"])
    o = client.get(f"/api/trends?league={league}&season=2025&limit=20&view=over&source=sleeper").json()
    assert o["source"] == "sleeper"
    assert [(x["gsis_id"], x["ppg"], x["xppg"], x["gap"]) for x in o["players"]] == \
        [(x["gsis_id"], x["ppg"], x["xppg"], x["gap"]) for x in d["players"]]
    now = client.get(f"/api/trends?league={league}&limit=5").json()          # 2026: three games played → an early read
    assert now["early_read"] is True and "four games" in now["notice"] and isinstance(now["role_alerts"], list)
    mine = client.get(f"/api/trends?league={league}&who=team&team={ANDREW[league]}&limit=50").json()
    assert mine["players"] and {x["rostered_by_roster_id"] for x in mine["players"]} == {ANDREW[league]}
    assert client.get(f"/api/trends?league={league}&view=sideways").status_code == 400


# ------------------------------------------------------------------------------ /api/matchups/defense
@pytest.mark.parametrize("league", HOUSE)
def test_matchups_defense_route(client, sql, league):
    d = client.get(f"/api/matchups/defense?league={league}").json()
    expected_pos = ["QB", "RB", "WR", "TE", "K"] if league == SCRUBS else ["QB", "RB", "WR", "TE"]
    assert d["positions"] == expected_pos and d["n_defenses"] == 32 and len(d["teams"]) == 32 * len(expected_pos)
    row = next(t for t in d["teams"] if t["position"] == "WR" and t["rank_std"] == 1)
    cur = sql("""select points_allowed_per_game_std, rank_std from analytics.mart_defense_vs_position_current
                 where defense = %s and position = 'WR'""", (row["defense"],))[0]
    assert row["points_allowed_per_game_std_ref"] == float(cur["points_allowed_per_game_std"])
    assert row["rank_std_ref"] == cur["rank_std"]
    # this league's points allowed: the league mart's points of the WRs who faced that defense, per game
    hand = sql("""select avg(pts) as v from (select p.game_id, sum(l.points) as pts from analytics.fct_player_game p
                  join analytics.fct_player_game_league l on l.league_id = %s and l.gsis_id = p.gsis_id and l.game_id = p.game_id
                  where p.season = 2026 and p.season_type = 'REG' and p.position = 'WR' and p.opponent_team = %s
                  group by p.game_id) x""", (league, row["defense"]))[0]["v"]
    assert row["points_allowed_per_game_std"] == pytest.approx(float(hand), abs=0.01)
    if league == SCRUBS:
        assert all(t["points_allowed_per_game_std"] == t["points_allowed_per_game_std_ref"] for t in d["teams"])
    assert {"gives_up", "rank_targets", "points_allowed_pg_ref", "direction", "direction_ref"} <= set(row)
    o = client.get(f"/api/matchups/defense?league={league}&source=sleeper").json()
    key = {(t["defense"], t["position"]): (t["points_allowed_per_game_std"], t["rank_std"]) for t in d["teams"]}
    assert all(key[(t["defense"], t["position"])] == (t["points_allowed_per_game_std"], t["rank_std"]) for t in o["teams"])
    assert client.get(f"/api/matchups/defense?league={league}&position=XX").status_code == 404



@pytest.mark.parametrize("league", [*HOUSE, TEST_LEAGUE])
def test_matchups_defense_starters(client, sql, league):
    """With team=: that roster's current starters at the heatmap's positions and the defense each faces this week (the
    cells the Matchups screen rings) — the same starters /api/matchups/cb marks is_starter."""
    team = ANDREW.get(league, 3)
    d = client.get(f"/api/matchups/defense?league={league}&team={team}").json()
    assert "starters" not in client.get(f"/api/matchups/defense?league={league}").json()
    st = d["starters"]
    assert st and d["team"] == team and all({"gsis_id", "player_name", "position", "team", "headshot_url", "slot", "opponent",
                                             "is_home"} <= set(s) for s in st)
    assert all(s["position"] in d["positions"] for s in st)
    cb = client.get(f"/api/matchups/cb?league={league}&team={team}&limit=500").json()
    cb_starters = {m["gsis_id"] for m in cb["matchups"] if m["is_starter"]}
    assert cb_starters <= {s["gsis_id"] for s in st}
    for s in st:
        if s["opponent"] is None:
            continue
        g = sql("""select home_team, away_team from analytics.dim_game where season = %s and week = %s and season_type = 'REG'
                   and %s in (home_team, away_team)""", (d["season"], d["week"], s["team"]))[0]
        assert s["opponent"] == (g["away_team"] if s["is_home"] else g["home_team"])
        assert s["is_home"] == (g["home_team"] == s["team"])
    if league == TEST_LEAGUE:
        assert all(s["slot"] for s in st)


# ------------------------------------------------------------------------------ /api/matchups/cb
@pytest.mark.parametrize("league", HOUSE)
def test_matchups_cb_route(client, sql, league):
    team = ANDREW[league]
    d = client.get(f"/api/matchups/cb?league={league}&team={team}").json()
    roster = {r["gsis_id"] for r in sql("""select gsis_id from analytics.mart_player_availability where league_id = %s
                                           and rostered_by_roster_id = %s and position in ('WR', 'TE')""", (league, team))}
    have = sql("select gsis_id from analytics.mart_cb_matchups where season = %s and week = %s and gsis_id = any(%s)",
               (d["season"], d["week"], list(roster)))
    assert {m["gsis_id"] for m in d["matchups"]} == {r["gsis_id"] for r in have} and d["matchups"]
    m = d["matchups"][0]
    assert PLAYER_KEYS <= set(m) and {"line", "lean", "corners", "faced", "cover_split", "likely_cover_name", "cover_rank",
                                      "proj_points", "p10", "p90", "is_starter"} <= set(m)
    assert m["rostered_by_roster_id"] == team and m["line"].startswith(f"**{m['player_name']}** vs {m['opponent']}")
    pj = sql("""select proj_points from analytics.mart_player_week_projections where league_id = %s and season = %s
                and week = %s and gsis_id = %s""", (league, d["season"], d["week"], m["gsis_id"]))
    assert m["proj_points"] == (float(pj[0]["proj_points"]) if pj else None)
    assert d["summary"] == [x["line"] for x in d["matchups"] if x["is_starter"]]
    every = client.get(f"/api/matchups/cb?league={league}&limit=500").json()
    assert len(every["matchups"]) >= len(d["matchups"])
    assert client.get(f"/api/matchups/cb?league={league}&team=99").status_code == 404


# ------------------------------------------------------------------------------ /api/players
@pytest.mark.parametrize("league", HOUSE)
def test_players_route(client, sql, league):
    d = client.get(f"/api/players?league={league}&season=2025&position=WR&limit=10").json()
    assert d["total"] > 100 and len(d["players"]) == 10 and d["columns"][:2] == ["targets", "target_share"]
    assert (d["season"], d["league_season"], d["season_type"]) == (2025, 2026, "REG")
    pts = [p["points"] for p in d["players"]]
    assert pts == sorted(pts, reverse=True)
    p = d["players"][0]
    assert PLAYER_KEYS <= set(p) and {"ppg", "points", "points_current_scoring_ref", "targets", "target_share"} <= set(p)
    m = sql("""select l.points, l.ppg, s.points_current_scoring, s.targets from analytics.mart_league_player_season l
               join analytics.mart_player_season s on s.gsis_id = l.gsis_id and s.season = l.season and s.season_type = 'REG'
               where l.league_id = %s and l.gsis_id = %s and l.season = 2025""", (league, p["gsis_id"]))[0]
    assert (p["points"], p["ppg"]) == (float(m["points"]), float(m["ppg"]))
    assert p["points_current_scoring_ref"] == float(m["points_current_scoring"]) and p["targets"] == m["targets"]
    # paging, sorting, search
    page2 = client.get(f"/api/players?league={league}&season=2025&position=WR&limit=5&offset=5").json()
    assert [x["gsis_id"] for x in page2["players"]] == [x["gsis_id"] for x in d["players"][5:10]]
    by_t = client.get(f"/api/players?league={league}&season=2025&position=WR&sort=targets&dir=asc&limit=5&min_games=8").json()
    assert [x["targets"] for x in by_t["players"]] == sorted(x["targets"] for x in by_t["players"])
    q = client.get(f"/api/players?league={league}&season=2025&q=chase").json()
    assert CHASE in {x["gsis_id"] for x in q["players"]} and all("chase" in x["player_name"].lower() for x in q["players"])
    assert len(client.get(f"/api/players?league={league}&limit=100000").json()["players"]) <= 500
    assert client.get(f"/api/players?league={league}&sort=nope").status_code == 400
    o = client.get(f"/api/players?league={league}&season=2025&position=WR&limit=10&source=sleeper").json()
    assert [(x["gsis_id"], x["points"], x["ppg"]) for x in o["players"]] == [(x["gsis_id"], x["points"], x["ppg"]) for x in d["players"]]
    post = client.get(f"/api/players?league={league}&season=2025&season_type=POST&position=QB&limit=3").json()
    assert post["players"] and all(x["points"] is not None for x in post["players"])


# ------------------------------------------------------------------------------ /api/receivers
@pytest.mark.parametrize("league", HOUSE)
def test_receivers_route(client, sql, league):
    d = client.get(f"/api/receivers?league={league}&season=2025&limit=5").json()
    top = sql("""select gsis_id from analytics.mart_player_season where season = 2025 and season_type = 'REG'
                 and position in ('WR', 'TE', 'RB') and targets >= 10 order by targets desc, gsis_id limit 5""")
    assert [r["gsis_id"] for r in d["receivers"]] == [r["gsis_id"] for r in top]
    r = d["receivers"][0]
    assert PLAYER_KEYS <= set(r) and {"target_share", "adot", "points_per_game", "points_per_game_ref", "target_share_l3",
                                      "points_per_game_l3", "first_read_target_share", "context"} <= set(r)
    s = sql("""select sum(targets)::float / sum(team_targets) as ts, count(*) filter (where played) as g
               from analytics.fct_player_game where gsis_id = %s and season = 2025 and season_type = 'REG'""", (r["gsis_id"],))[0]
    assert r["target_share"] == pytest.approx(s["ts"]) and r["games"] == s["g"]
    lp = sql("""select sum(points) / count(*) filter (where played) as ppg from analytics.fct_player_game_league
                where league_id = %s and gsis_id = %s and season = 2025 and season_type = 'REG'""", (league, r["gsis_id"]))[0]
    assert r["points_per_game"] == pytest.approx(float(lp["ppg"]), abs=0.01)
    assert {c["bucket_key"] for c in r["context"]} <= {"H1", "H2", "OT"} and d["yardsticks"]["WR"]["target_share"] > 0.15
    two = client.get(f"/api/receivers?league={league}&season=2025&players={CHASE},{NABERS}&weeks=1-6&context=qb").json()
    assert [x["gsis_id"] for x in two["receivers"]] == [CHASE, NABERS] and two["weeks"] == [1, 6]
    assert client.get(f"/api/receivers?league={league}&weeks=x").status_code == 400


# ------------------------------------------------------------------------------ /api/compare
@pytest.mark.parametrize("league", HOUSE)
def test_compare_route(client, league):
    d = client.get(f"/api/compare?league={league}&a={CHASE}&b={NABERS}").json()
    a, b = d["a"], d["b"]
    assert set(a) == set(b) and PLAYER_KEYS <= set(a)
    assert {"projection", "season", "usage", "last3", "ros", "next4", "matchup"} <= set(a)
    assert set(a["season"]) == set(b["season"]) and len(a["next4"]) == 4
    assert {"passing_tds", "rushing_tds", "receiving_tds"} <= set(a["season"])   # the screen's touchdowns a game
    card = client.get(f"/api/player/{CHASE}?league={league}").json()                 # same numbers everywhere
    assert a["projection"]["proj_points"] == pytest.approx(card["proj_points"]) and a["ros"] == card["ros"]
    assert d["verdict"] and [r["what"] for r in d["table"]][:3] == ["Projection", "Floor – ceiling", "Opponent"]
    assert client.get(f"/api/compare?league={league}&a={CHASE}&b=00-0000000").status_code == 404


# ------------------------------------------------------------------------------ any league: the Test League fixtures
def test_every_route_on_the_test_league(client):
    t = TEST_LEAGUE
    routes = [f"/api/trends?league={t}&limit=5", f"/api/matchups/defense?league={t}", f"/api/matchups/cb?league={t}&team=1",
              f"/api/players?league={t}&limit=5", f"/api/receivers?league={t}&limit=3",
              f"/api/compare?league={t}&a={CHASE}&b={NABERS}", f"/api/player/{CHASE}/games?league={t}&season=2025"]
    out = {}
    for u in routes:
        r = client.get(u)
        assert r.status_code == 200, (u, r.text[:300])
        out[u] = r.json()
        assert out[u]["source"] == "sleeper" and out[u]["league_name"] == "Test League"
        assert out[u]["expected_points_reference"] == SCRUBS and out[u]["expected_points_exact"] is True
    d = out[routes[1]]
    assert d["positions"] == ["QB", "RB", "WR", "TE", "K"]       # the league starts a K (and a DEF: no DvP rows for it)
    cb = out[routes[2]]
    assert cb["matchups"] and all(m["rostered_by_team"] == "Team 1" for m in cb["matchups"])
    games = out[routes[6]]["games"]
    # full PPR, 4-pt pass TD: a receiver's points = the Scrubs (half PPR) points + half a point per catch
    assert all(g["points"] == pytest.approx(g["points_ref"] + 0.5 * g["receptions"], abs=0.01) for g in games)
    assert client.get(f"/api/matchups/cb?league={t}&team=99").status_code == 404


# ------------------------------------------------------------------------------ errors
def test_research_errors(client, monkeypatch):
    for u in ("/api/trends?league=abc", "/api/players?league=9000000000000000099", "/api/matchups/defense?league=12"):
        r = client.get(u)
        assert r.status_code == 404 and "error" in r.json(), u
    assert client.get(f"/api/player/00-0000000/games?league={SCRUBS}").status_code == 404
    down = SC.Sleeper(fixtures=None, fetch=lambda p: (_ for _ in ()).throw(SC.SleeperUnavailable("down")), cache_path=None)
    monkeypatch.setattr(A, "sleeper", lambda: down)
    r = client.get(f"/api/trends?league={TEST_LEAGUE}")
    assert r.status_code == 502 and r.json()["error"] == "Sleeper did not answer"
    assert client.get(f"/api/trends?league={SCRUBS}").status_code == 200          # a house league never needs Sleeper
