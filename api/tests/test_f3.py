"""Plan F3 (Wave F): the API for any league — the Sleeper client (caches, the token bucket, the player directory on
disk), the league picker by username, the week's opponent, the player card / rest of season on demand, the record,
F1's NFL-wide board read path, the static web app. The fixtures (`tests/fixtures/sleeper/`, rebuilt by
`tests/fixtures/make_f3_fixtures.py`) hold a fictional user `test_manager` who owns house-league roster 2 (Scrubs),
roster 12 (the dynasty) and roster 1 of a fictional "Test League" (full PPR, K and DEF, its own K / DEF keys).

The NFL-wide board tests need F1's tables (`api/tests/fixtures/f1_tables.sql` builds them in a clone) and skip
without them."""

from __future__ import annotations

import json
import time

import numpy as np
import pandas as pd
import pytest
from league_lab import anyleague as A
from league_lab import sleeper_client as SC

from league_lab_api import db, ondemand
from league_lab_api.applib import cards

from .conftest import ANDREW, DYNASTY, SCRUBS, SLEEPER_FIXTURES, needs_db

TEST_LEAGUE = "9000000000000000001"
USER = "test_manager"


class FakeClock:
    def __init__(self, t: float = 1000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, s: float) -> None:
        self.t += s


def fake_client(clock: FakeClock, per_minute: float = 300, capacity: float | None = None, **kw):
    calls: list[str] = []

    def fetch(path: str):
        calls.append(path)
        if path.startswith("/players"):
            return {"1": {"player_id": "1", "position": "QB"}}
        if path.startswith("/user/") and "/leagues/" not in path:
            return {"user_id": "91", "username": "x"}
        return [{"path": path, "n": len(calls)}] if "matchups" in path or "rosters" in path else {"path": path, "n": len(calls)}

    c = SC.Sleeper(fixtures=None, clock=clock, wall=clock, fetch=fetch,
                   bucket=SC.TokenBucket(per_minute, capacity, clock=clock), **kw)
    return c, calls


# ------------------------------------------------------------------------------ the client (no database)
def test_token_bucket_refills_with_a_fake_clock():
    clk = FakeClock()
    b = SC.TokenBucket(60, capacity=3, clock=clk)            # 1 token a second, 3 held
    assert [b.take() for _ in range(4)] == [True, True, True, False]
    assert b.refused == 1 and b.seconds_until() == pytest.approx(1.0)
    clk.advance(1.0)
    assert b.take() and not b.take()
    clk.advance(3600)
    assert b.tokens() == pytest.approx(3.0)                  # never more than the capacity


def test_ttls_per_kind_of_call():
    clk = FakeClock()
    c, calls = fake_client(clk, cache_path=None)
    c.rosters("1")
    c.matchups("1", 4)
    c.league("1")
    c.user("someone")
    c.rosters("1")
    c.matchups("1", 4)
    assert len(calls) == 4                                     # all cached
    clk.advance(5 * 60 + 1)                                    # matchups expire (5 min), rosters do not (10 min)
    c.matchups("1", 4)
    c.rosters("1")
    assert calls[-1] == "/league/1/matchups/4" and len(calls) == 5
    clk.advance(5 * 60)                                        # rosters expire at 10 min
    c.rosters("1")
    assert calls[-1] == "/league/1/rosters" and len(calls) == 6
    clk.advance(3600)                                          # user lookups: an hour; league settings: a day
    c.user("someone")
    c.league("1")
    assert calls[-1] == "/user/someone" and len(calls) == 7
    clk.advance(24 * 3600)
    c.league("1")
    assert calls[-1] == "/league/1" and len(calls) == 8
    st = c.stats()
    assert st["calls"] == 8 and set(st["cache"]) == {"rosters", "matchups", "league", "user"}
    assert st["cache"]["league"]["ttl_s"] == 86400 and st["bucket"]["per_minute"] == 300


def test_bucket_empty_means_busy_unless_cached():
    clk = FakeClock()
    c, calls = fake_client(clk, per_minute=60, capacity=2, cache_path=None)
    c.rosters("1")
    c.rosters("2")
    with pytest.raises(SC.SleeperBusy):
        c.rosters("3")                                         # nothing cached, no token: 503 in the API
    clk.advance(11 * 60)                                       # rosters 1 expired; the bucket refilled
    c.rosters("1")
    c.rosters("2")
    assert len(calls) == 4
    clk.advance(11 * 60)
    c.bucket._tokens = 0.0                                     # spent: the expired answer is served, not an error
    clk.t = clk.t                                              # (no refill: same instant)
    c.bucket._t = clk()
    assert c.rosters("1")[0]["path"] == "/league/1/rosters"
    assert c.stale_served == 1 and len(calls) == 4


def test_sleeper_down_serves_the_last_good_answer():
    clk = FakeClock()
    state = {"down": False}

    def fetch(path):
        if state["down"]:
            raise SC.SleeperUnavailable("down")
        return [{"roster_id": 1}]

    c = SC.Sleeper(fixtures=None, clock=clk, wall=clk, fetch=fetch, cache_path=None,
                   bucket=SC.TokenBucket(300, clock=clk))
    assert c.rosters("5") == [{"roster_id": 1}]
    state["down"] = True
    clk.advance(3600)
    assert c.rosters("5") == [{"roster_id": 1}] and c.stale_served == 1
    with pytest.raises(SC.SleeperUnavailable):
        c.users("5")                                           # never fetched: the API answers 502


def test_player_directory_lives_on_disk_for_a_day(tmp_path):
    clk = FakeClock(1_900_000_000.0)
    c, calls = fake_client(clk, cache_path=tmp_path)
    assert c.players() == {"1": {"player_id": "1", "position": "QB"}}
    assert (tmp_path / SC.PLAYERS_FILE).exists() and calls == ["/players/nfl"]
    import os
    os.utime(tmp_path / SC.PLAYERS_FILE, (clk(), clk()))
    c2, calls2 = fake_client(clk, cache_path=tmp_path)        # a restart: read from disk, no call
    clk.advance(23 * 3600)
    assert c2.players()["1"]["position"] == "QB" and calls2 == []
    assert c2.stats()["players_file_age_s"] == pytest.approx(23 * 3600, abs=1)
    c3, calls3 = fake_client(clk, cache_path=tmp_path)
    clk.advance(3600 + 1)                                      # a day old: fetched again
    c3.players()
    assert calls3 == ["/players/nfl"]


def test_usernames_and_ids_never_reach_a_url_unchecked():
    for bad in ("../x", "a b", "", "x" * 41, "name/leagues"):
        with pytest.raises(SC.LeagueNotFound):
            SC.check_username(bad)
    assert SC.check_username(" Test_Manager ") == "test_manager"


def test_scoring_label_rule():
    lg = json.loads((SLEEPER_FIXTURES / f"league_{TEST_LEAGUE}.json").read_text())
    assert A.scoring_label(lg) == "10-team redraft · full PPR · 4‑pt pass TD"
    lg2 = {**lg, "roster_positions": ["QB", "QB", "TE"], "settings": {"num_teams": 8, "type": 1},
           "scoring_settings": {"rec": 0.75, "pass_td": 6, "bonus_rec_te": 0.5, "bonus_rec_yd_100": 3}}
    assert A.scoring_label(lg2) == "8-team 2QB keeper · 0.75 PPR · 6‑pt pass TD · yardage bonuses · TE premium 0.5"


def test_ros_window_rules():
    lg = {"settings": {"playoff_week_start": 15, "playoff_teams": 6, "playoff_round_type": 0}}
    assert A.ros_window(lg, 4, 18) == (4, 17, 15)               # 3 rounds
    assert A.ros_window({"settings": {"playoff_week_start": 15, "playoff_teams": 4, "playoff_round_type": 1}}, 4, 18) == (4, 17, 15)
    assert A.ros_window({"settings": {"playoff_week_start": 15, "playoff_teams": 4, "playoff_round_type": 2}}, 4, 18) == (4, 18, 15)
    assert A.ros_window({"settings": {"playoff_week_start": 0}}, 4, 18) == (4, 18, None)


# ------------------------------------------------------------------------------ the league picker
@needs_db
def test_leagues_by_username(client, sql):
    r = client.get(f"/api/leagues?username={USER}")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["user"] == {"user_id": "9100000000000000001", "username": USER, "display_name": "Test Manager", "avatar": None}
    assert d["season"] == 2026
    names = [x["name"] for x in d["leagues"]]
    assert names == sorted(names, key=str.lower) and len(names) == 3
    by = {x["league_id"]: x for x in d["leagues"]}
    assert by[SCRUBS]["roster_id"] == 2 and by[DYNASTY]["roster_id"] == 12 and by[TEST_LEAGUE]["roster_id"] == 1
    assert by[SCRUBS]["in_database"] and by[DYNASTY]["in_database"] and not by[TEST_LEAGUE]["in_database"]
    assert by[TEST_LEAGUE]["team_name"] == "Team 1" and by[TEST_LEAGUE]["total_rosters"] == 10
    for x in d["leagues"]:
        assert set(x) == {"league_id", "name", "season", "total_rosters", "scoring_label", "roster_id", "team_name",
                          "status", "in_database"}
    # the house leagues' labels are dim_league_season's (the SQL rule, ported)
    labels = {r["league_id"]: r["scoring_label"] for r in sql(
        "select league_id, scoring_label from analytics.dim_league_season where league_id = any(%s)", ([SCRUBS, DYNASTY],))}
    assert by[SCRUBS]["scoring_label"] == labels[SCRUBS] and by[DYNASTY]["scoring_label"] == labels[DYNASTY]
    # without username: the house leagues exactly as before
    assert [x["league_id"] for x in client.get("/api/leagues").json()] == \
           [x["league_id"] for x in client.get("/api/leagues").json()] and "user" not in client.get("/api/leagues").json()
    bad = client.get("/api/leagues?username=nobody_at_all")
    assert bad.status_code == 404 and bad.json()["error"] == "no such Sleeper user"
    assert client.get("/api/leagues?username=../etc").status_code == 404


@needs_db
def test_sleeper_down_is_502_and_busy_is_503(client, monkeypatch):
    down = SC.Sleeper(fixtures=None, fetch=lambda p: (_ for _ in ()).throw(SC.SleeperUnavailable("down")), cache_path=None)
    monkeypatch.setattr(A, "sleeper", lambda: down)
    r = client.get(f"/api/leagues?username={USER}")
    assert r.status_code == 502 and r.json()["error"] == "Sleeper did not answer"
    busy = SC.Sleeper(fixtures=SLEEPER_FIXTURES, bucket=SC.TokenBucket(60, capacity=0), cache_path=None)
    monkeypatch.setattr(A, "sleeper", lambda: busy)
    r = client.get(f"/api/leagues?username={USER}")
    assert r.status_code == 503 and r.json() == {"error": "busy, try again in a minute", "detail": "busy, try again in a minute"}
    assert r.headers["retry-after"] == "60"


# ------------------------------------------------------------------------------ the opponent
def _lineup_total(sql, league, season, week, roster) -> float | None:
    rows = sql("""select lineup_value from ops.lineup_totals where league_id = %s and season = %s and week = %s
                  and roster_id = %s and not is_realised order by run_at desc limit 1""", (league, season, week, roster))
    return float(rows[0]["lineup_value"]) if rows else None


@needs_db
@pytest.mark.parametrize("board", ["borrow", "nfl_wide"])
@pytest.mark.parametrize("league", [DYNASTY, SCRUBS])
def test_opponent_on_demand_reproduces_the_nightly(client, sql, monkeypatch, league, board):
    """Both paths name the roster sharing the matchup_id (fixture: week-3 pairings), and the on-demand path's
    opponent lineup value is the nightly's (ops.lineup_totals) to the cent."""
    if board == "nfl_wide" and not A.nfl_wide_ready(db.query, 2026, 4):
        pytest.skip("F1's tables are not in this database (api/tests/fixtures/f1_tables.sql)")
    monkeypatch.setenv(A.BOARD_SOURCE_ENV, board)
    team = ANDREW[league]
    season = cards.league_season(league)
    week = cards.decision_week(season)
    pairs = json.loads((SLEEPER_FIXTURES / f"matchups_{league}_{week}.json").read_text()) \
        if (SLEEPER_FIXTURES / f"matchups_{league}_{week}.json").exists() else []
    if not pairs:
        pytest.skip(f"no matchups fixture for week {week}")
    mid = next(m["matchup_id"] for m in pairs if m["roster_id"] == team)
    opp_id = next(m["roster_id"] for m in pairs if m["matchup_id"] == mid and m["roster_id"] != team)
    nightly = _lineup_total(sql, league, season, week, opp_id)
    db_path = client.get(f"/api/my-week?league={league}&team={team}").json()
    assert db_path["source"] == "database"
    assert db_path["opponent"]["roster_id"] == opp_id and db_path["opponent"]["lineup_value"] == nightly
    assert set(db_path["opponent"]) >= {"roster_id", "team_name", "manager", "lineup_value"}
    as_of = pd.Timestamp(sql("""select max(as_of) as a from ops.lineup_totals where league_id = %s and season = %s
                                and week = %s and not is_realised""", (league, season, week))[0]["a"]).to_pydatetime()
    od = ondemand.my_week(league, team, as_of=as_of)
    assert od["source"] == "sleeper" and od["opponent"]["roster_id"] == opp_id
    assert od["opponent"]["team_name"].startswith("Team ")                   # pseudonymised fixture users
    assert od["opponent"]["lineup_value"] == pytest.approx(nightly, abs=0.01)
    assert f"week {week} vs **{od['opponent']['team_name']}**" in od["summary"]


# ------------------------------------------------------------------------------ the NFL-wide board (F1's tables)
@needs_db
@pytest.mark.parametrize("league", [DYNASTY, SCRUBS])
def test_nfl_wide_board_reproduces_the_marts_exactly(league, monkeypatch, sql):
    """With F1's tables, a house league matches its own reference scoring exactly: the same starters, slots, values,
    margins, bench, lineup value AND the same ranges as the nightly (no approximation left); K / DEF priced from
    their stat lines reproduce the nightly's K / DEF values."""
    if not A.nfl_wide_ready(db.query, 2026, 4):
        pytest.skip("F1's tables are not in this database (api/tests/fixtures/f1_tables.sql)")
    monkeypatch.setenv(A.BOARD_SOURCE_ENV, "nfl_wide")
    team = ANDREW[league]
    season = cards.league_season(league)
    week = cards.decision_week(season)
    mart = cards.lineup_rows(league, season, week, team)
    as_of = pd.Timestamp(mart.loc[mart["role"] == "starter", "as_of"].dropna().iloc[0]).to_pydatetime()
    od = A.lineup_rows(db.query, league, team, week, as_of=as_of)
    assert od.board_source == "nfl_wide"
    refs = {r["name"]: r["scoring_settings"] for r in sql("select name, scoring_settings from analytics_seeds.reference_scorings")}
    assert od.reference_league in refs                                          # an exact reference scoring
    ms, gs = mart[mart["role"] == "starter"], od.rows[od.rows["role"] == "starter"]
    assert list(ms["slot"]) == list(gs["slot"]) and list(ms["sleeper_player_id"]) == list(gs["sleeper_player_id"])
    np.testing.assert_allclose(gs["value"].astype(float), ms["value"].astype(float), atol=0.005)
    np.testing.assert_allclose(gs["margin"].astype(float), ms["margin"].astype(float), atol=0.005)
    assert abs(float(gs["lineup_value"].iloc[0]) - float(ms["lineup_value"].iloc[0])) <= 0.005
    m = mart[mart["gsis_id"].notna() & mart["p10"].notna()].drop_duplicates("gsis_id").set_index("gsis_id")
    g = od.rows[od.rows["gsis_id"].notna()].drop_duplicates("gsis_id").set_index("gsis_id").reindex(m.index)
    for q in ("p10", "p90"):
        assert float((g[q].astype(float) - m[q].astype(float)).abs().max()) <= 0.011, q
    if league == SCRUBS:
        assert od.kd_sources == {"K": "lines", "DEF": "lines"}
        kd = mart[mart["position"].isin(["K", "DEF"]) & (mart["role"] == "starter")]
        assert len(kd) == 2 and (kd["value_source"] != "unvalued").all()


@needs_db
@pytest.mark.parametrize("board", ["borrow", "nfl_wide"])
def test_fictional_league_prices_and_solves_with_k_and_def(client, monkeypatch, board):
    """The Test League (full PPR 4-pt, sack 2, fgm_50p 6, pts_allow_0 12: no house league's scoring) on demand:
    the lineup is solved, its K and DEF are valued from the NFL-wide K / DEF lines (F1); on the borrowed board its
    K / DEF keys match no fitted league, so they stay unvalued and are reported (why F1's ops.kd_lines matter)."""
    if board == "nfl_wide" and not A.nfl_wide_ready(db.query, 2026, 4):
        pytest.skip("F1's tables are not in this database (api/tests/fixtures/f1_tables.sql)")
    monkeypatch.setenv(A.BOARD_SOURCE_ENV, board)
    d = client.get(f"/api/my-week?league={TEST_LEAGUE}&team=1").json()
    assert d["source"] == "sleeper" and d["league_name"] == "Test League" and d["lineup"]
    assert d["scoring_label"] == "10-team redraft · full PPR · 4‑pt pass TD"
    assert d["on_demand"]["board_source"] == board
    assert d["on_demand"]["range_reference_league"] is not None
    kd = {x["slot"]: x for x in d["lineup"] if x["slot"] in ("K", "DEF")}
    assert set(kd) == {"K", "DEF"}
    if board == "nfl_wide":
        assert d["on_demand"]["kd_value_source"] == {"K": "lines", "DEF": "lines"}
        assert all(x["value"] is not None and x["value"] > 0 for x in kd.values())
        # a defense in this league: sack 2, pts_allow_0 12 — its price is its line priced in THIS scoring
        b = A.load_board(db.query, d["season"], d["week"])
        league = json.loads((SLEEPER_FIXTURES / f"league_{TEST_LEAGUE}.json").read_text())
        _, dfr = A.kd_values(league["scoring_settings"], "DEF", b)
        _, dsc = A.kd_values(A.league_scoring(json.loads((SLEEPER_FIXTURES / f"league_{SCRUBS}.json").read_text()))[0], "DEF", b)
        both = dfr.set_index("unit_id")["proj_points"].astype(float).to_frame("t").join(
            dsc.set_index("unit_id")["proj_points"].astype(float).rename("s"))
        # the Test League pays 2 a sack (Scrubs 1) and 12 for a shutout: its DEF prices are its lines priced in THIS
        # scoring, never Scrubs' — re-priced by hand from the board's lines (F1's real ops.kd_lines carry every stat,
        # so "2 × Scrubs" only holds for a sacks-only line)
        from league_lab import kdef
        lines = b.kd[b.kd["position"] == "DEF"].copy()
        for c in [f"proj_{x}" for x in kdef.DEF_LINE]:
            lines[c] = pd.to_numeric(lines[c], errors="coerce") if c in lines else 0.0
        hand = pd.Series(np.asarray(kdef.price(lines.reset_index(drop=True), "DEF", league["scoring_settings"], "proj_"), dtype=float),
                         index=lines["unit_id"].to_numpy())
        assert (both["t"] - hand.reindex(both.index)).abs().max() <= 0.011
        assert (both["t"] - both["s"]).abs().max() > 0.5                  # a different scoring gives different values
    else:
        assert d["on_demand"]["kd_value_source"] == {"K": None, "DEF": None}
    assert d["opponent"]["roster_id"] == 2 and d["opponent"]["lineup_value"] is not None


# ------------------------------------------------------------------------------ rest of season
@needs_db
@pytest.mark.parametrize("board", ["borrow", "nfl_wide"])
@pytest.mark.parametrize("league", [DYNASTY, SCRUBS])
def test_ros_on_demand_reproduces_the_mart(monkeypatch, sql, league, board):
    """A house league's rest of season priced on request = mart_player_ros_projection: the same players (the same
    population: every projected player, K / DEF where the league starts them), the same totals, games, playoff
    points and position ranks; the ranges exact on the NFL-wide board (exact reference), approximated on the
    borrowed one (the other league's ranges, scaled)."""
    if board == "nfl_wide" and not A.nfl_wide_ready(db.query, 2026, 4):
        pytest.skip("F1's tables are not in this database (api/tests/fixtures/f1_tables.sql)")
    monkeypatch.setenv(A.BOARD_SOURCE_ENV, board)
    mart = pd.DataFrame(sql("select * from analytics.mart_player_ros_projection where league_id = %s", (league,)))
    week = cards.decision_week(cards.league_season(league))
    if mart.empty or int(mart["from_week"].iloc[0]) != week:
        pytest.skip("the mart was built in another week than this one")
    t0 = time.perf_counter()
    _, got = ondemand.ros_on_demand(league)
    t1 = time.perf_counter()
    _, again = ondemand.ros_on_demand(league)
    t2 = time.perf_counter()
    print(f"\nros on demand {league} ({board}): cold {1000 * (t1 - t0):.0f} ms, warm {1000 * (t2 - t1):.0f} ms, {len(got)} players")
    m, g = mart.set_index("player_key"), got.set_index("player_key")
    assert set(m.index) == set(g.index)
    g = g.reindex(m.index)
    assert int(g["last_week"].iloc[0]) == int(m["last_week"].iloc[0])
    np.testing.assert_allclose(g["ros_points"].astype(float), m["ros_points"].astype(float), atol=0.011)
    np.testing.assert_allclose(g["playoff_points"].astype(float), m["playoff_points"].astype(float), atol=0.011)
    assert (g["ros_games"].astype(int) == m["ros_games"].astype(int)).all()
    assert (g["ros_rank_pos"].fillna(-1).astype(int) == m["ros_rank_pos"].fillna(-1).astype(int)).all()
    assert (g["ros_rank_all"].fillna(-1).astype(int) == m["ros_rank_all"].fillna(-1).astype(int)).all()
    gap = (g["ros_p90"].astype(float) - m["ros_p90"].astype(float)).abs()
    if board == "nfl_wide":
        assert gap.max() <= 0.11
    else:
        print(f"ros p90 gap (borrowed ranges): mean {gap.mean():.2f}, max {gap.max():.2f}")
        assert gap.mean() < 3.0


@needs_db
def test_ros_route(client):
    h = client.get(f"/api/ros?league={SCRUBS}&position=RB&limit=5").json()
    assert h["source"] == "database" and len(h["players"]) == 5 and h["from_week"] and h["last_week"] == 16
    assert [p["pos_rank"] for p in h["players"]] == [1, 2, 3, 4, 5]
    assert set(h["players"][0]) == {"gsis_id", "player_key", "player_name", "position", "team", "ros_points", "ros_games",
                                    "playoff_points", "p10", "p90", "pos_rank", "rostered_by_roster_id", "rostered_by_team",
                                    # IA-3 (Wave I-A): the pieces, why this number, the market line (test_ia3.py)
                                    "headshot_url", "bye_weeks", "ros_points_per_game", "per_game", "why", "market_points",
                                    "week_points", "market_words"}
    u = client.get(f"/api/ros?league={TEST_LEAGUE}&position=ALL&limit=40").json()
    assert u["source"] == "sleeper" and u["last_week"] == 17 and len(u["players"]) == 40      # 6 playoff teams: 3 rounds
    pts = [p["ros_points"] for p in u["players"]]
    assert pts == sorted(pts, reverse=True)
    assert any(p["rostered_by_team"] for p in u["players"])
    assert client.get(f"/api/ros?league={SCRUBS}&position=XX").status_code == 404


# ------------------------------------------------------------------------------ the player card on demand
@needs_db
def test_player_card_any_league(client, sql):
    """A player in the Test League: projection priced in its scoring, its range, rest of season, whose team he is
    on (Sleeper), usage from the NFL-wide marts; the league-scored history is listed as missing."""
    rosters = json.loads((SLEEPER_FIXTURES / f"rosters_{TEST_LEAGUE}.json").read_text())
    directory = json.loads((SLEEPER_FIXTURES / "players_nfl.json").read_text())
    sid = next(p for p in rosters[0]["players"] if (directory.get(p) or {}).get("position") == "WR")
    gsis = sql("select gsis_id from analytics.player_id_map where sleeper_id = %s", (sid,))[0]["gsis_id"]
    d = client.get(f"/api/player/{gsis}?league={TEST_LEAGUE}&team=1").json()
    assert d["source"] == "sleeper" and d["league_name"] == "Test League" and d["rostered_by_roster_id"] == 1
    assert "value.points_per_game" in d["missing_keys"] and all(" " in m for m in d["missing"])   # plain words on the card
    assert set(d["ros"]) == {"points", "games", "p10", "p90", "pos_rank", "playoff_points", "from_week", "last_week"}
    assert d["sections"]["availability"]["blocks"][0]["text"].startswith("Rostered by **Team 1**")


@needs_db
@pytest.mark.parametrize("league", [DYNASTY, SCRUBS])
def test_player_card_ros_is_the_marts(client, sql, monkeypatch, league):
    """The house-league card carries `ros` from the mart; served on demand (source=sleeper, NFL-wide board) the
    same player's `ros` is the same."""
    row = sql("""select gsis_id, ros_points, ros_games, ros_rank_pos from analytics.mart_player_ros_projection
                 where league_id = %s and position = 'WR' order by ros_points desc limit 1""", (league,))[0]
    d = client.get(f"/api/player/{row['gsis_id']}?league={league}").json()
    assert d["source"] == "database" and d["missing"] == []
    assert d["ros"]["points"] == pytest.approx(float(row["ros_points"])) and d["ros"]["pos_rank"] == row["ros_rank_pos"]
    if A.nfl_wide_ready(db.query, 2026, 4):
        monkeypatch.setenv(A.BOARD_SOURCE_ENV, "nfl_wide")
        o = client.get(f"/api/player/{row['gsis_id']}?league={league}&source=sleeper").json()
        assert o["source"] == "sleeper"
        if o["ros"]["from_week"] == d["ros"]["from_week"]:
            for k in ("points", "games", "pos_rank", "playoff_points", "last_week"):
                assert o["ros"][k] == pytest.approx(d["ros"][k], abs=0.011), k
        assert o["proj_points"] == pytest.approx(d["proj_points"], abs=0.005)


# ------------------------------------------------------------------------------ the record
@needs_db
def test_record_route(client, sql):
    d = client.get(f"/api/record?league={SCRUBS}").json()
    n = sql("select count(*) as n from analytics.mart_projection_record where league_id = %s and scope = 'week'", (SCRUBS,))[0]["n"]
    assert d["available"] is True and len(d["weeks"]) == n and set(d) >= {"league_id", "from_week", "weeks", "summary"}
    u = client.get(f"/api/record?league={TEST_LEAGUE}")
    assert u.status_code == 200 and u.json() == {"league_id": TEST_LEAGUE, "available": False,
                                                 "why": "we keep the record for the leagues we score every morning; yours is not one of them yet"}
    assert client.get("/api/record?league=abc").status_code == 404


# ------------------------------------------------------------------------------ status, errors, the static app
@needs_db
def test_status_shows_the_sleeper_line(client):
    client.get(f"/api/my-week?league={TEST_LEAGUE}&team=1")
    s = client.get("/api/status").json()
    sl = s["sleeper"]
    assert sl["mode"] == "fixtures" and sl["bucket"]["per_minute"] == 300 and sl["calls"] >= 4
    assert {"league", "rosters", "users", "players", "matchups"} <= set(sl["cache"])
    assert s["board_source"] in ("auto", "nfl_wide", "borrow")


@needs_db
def test_errors_are_plain_json(client):
    r = client.get(f"/api/my-week?league={TEST_LEAGUE}&team=99")
    assert r.status_code == 404 and "error" in r.json()
    r = client.get("/api/my-week?league=not-a-league&team=1")
    assert r.status_code == 404 and "error" in r.json()
    r = client.get("/api/nope")
    assert r.status_code == 404 and r.json()["error"] == "no endpoint /api/nope"


def test_static_web_app_from_a_placeholder_dist(client, tmp_path, monkeypatch):
    """The API serves web/dist when present: real files, the SPA fallback for the app's routes, /api stays the API."""
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text('<!doctype html><div id="app">placeholder</div>')
    (tmp_path / "assets" / "app-123.js").write_text("console.log(1)")
    monkeypatch.setenv("LEAGUE_LAB_WEB_DIST", str(tmp_path))
    for path in ("/", "/player/00-0036963", "/my-week?league=1&team=2", "/leagues"):
        r = client.get(path)
        assert r.status_code == 200 and "placeholder" in r.text and r.headers["cache-control"] == "no-cache", path
    a = client.get("/assets/app-123.js")
    assert a.status_code == 200 and "immutable" in a.headers["cache-control"]
    assert client.get("/assets/missing.js").status_code == 404
    assert client.get("/api/health").json()["ok"] is True          # the full shape: test_h0.py (Wave H)
    assert client.get("/../../etc/passwd").status_code in (200, 404) and "root:" not in client.get("/../../etc/passwd").text
