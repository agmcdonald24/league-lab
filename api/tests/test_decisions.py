"""Wave G (G2): the decisions, on demand — `/api/waivers`, `POST /api/trades/evaluate`, `/api/trades/partners`, `/api/team`,
`/api/league` (api/league_lab_api/decisions.py).

Parity (the plan's acceptance, to 0.01): for both house leagues each route reproduces its marts — the house path reads
them, and the on-demand path (`source=sleeper`: the league from the Sleeper fixtures, every roster solved on request)
reproduces them from scratch: every waiver move of `mart_waiver_moves` (dynasty and Scrubs rosters), the Trade Finder's
evaluator numbers for a package, `mart_league_roster_value` / `_rankings` / `_slot_strength`, and
`mart_league_standings` / `_all_play` / `_all_play_week` / `mart_league_transactions` (Sleeper's played weeks and
transactions: `tests/fixtures/make_g2_fixtures.py` writes them from `raw.sleeper_*`). The fictional Test League answers
every route. Sleeper is never called (fixtures)."""

from __future__ import annotations

import json
import time

import numpy as np
import pandas as pd
import pytest
from league_lab import anyleague as A
from league_lab import sleeper_client as SC
from league_lab import trades as T
from league_lab.roster_value import RosterBoard

from league_lab_api import decisions
from league_lab_api.applib import strip_links

from .conftest import ANDREW, DYNASTY, SCRUBS, SLEEPER_FIXTURES, needs_db

TEST_LEAGUE = "9000000000000000001"


@pytest.fixture(autouse=True)
def _fresh_league_weeks():
    A.clear_league_weeks()
    decisions.clear_memo()
    yield
    A.clear_league_weeks()
    decisions.clear_memo()


def _as_of(sql, league: str) -> object:
    return pd.Timestamp(sql("select max(as_of) as a from analytics.mart_waiver_moves where league_id = %s", (league,))[0]["a"]).to_pydatetime()


# ------------------------------------------------------------------------------ the Sleeper client (no database)
def test_season_matchups_and_transactions_are_cached_an_hour():
    class Clock:
        t = 1000.0

        def __call__(self):
            return self.t
    clk, calls = Clock(), []

    def fetch(path):
        calls.append(path)
        return [{"roster_id": 1, "matchup_id": 1, "points": 100.0}] if "matchups" in path else [{"transaction_id": "1"}]
    c = SC.Sleeper(fixtures=None, clock=clk, wall=clk, fetch=fetch, cache_path=None, bucket=SC.TokenBucket(300, clock=clk))
    assert sorted(c.season_matchups("1", 3)) == [1, 2, 3] and len(calls) == 3
    c.transactions("1", 2)
    c.season_matchups("1", 3)
    c.transactions("1", 2)
    assert len(calls) == 4                                          # all cached
    clk.t += 3601
    c.transactions("1", 2)
    assert len(calls) == 5 and SC.TTL_S["season_matchups"] == SC.TTL_S["transactions"] == 3600


def test_a_missing_transactions_fixture_is_an_empty_round(tmp_path):
    c = SC.Sleeper(fixtures=tmp_path, cache_path=None)
    assert c.transactions("123", 7) == [] and c.season_matchups("123", 1) == {1: []}


def test_page_functions_read_only_the_named_definitions():
    ns = decisions.page_functions("2_Waiver_Wire.py", ("_f", "_span"))
    assert ns["_f"](2.345) == "2.3"
    assert ns["_span"](pd.Series({"week": 4, "horizon_last_week": 7})) == "the next 4 weeks"
    with pytest.raises(RuntimeError, match="has no"):
        decisions.page_functions("2_Waiver_Wire.py", ("no_such_function",))


# ------------------------------------------------------------------------------ waivers
@needs_db
@pytest.mark.parametrize("league", [DYNASTY, SCRUBS])
def test_waivers_house_route_is_the_mart(client, sql, league):
    team = ANDREW[league]
    d = client.get(f"/api/waivers?league={league}&team={team}&limit=500").json()
    mart = sql("""select * from analytics.mart_waiver_moves where league_id = %s and roster_id = %s and is_best_drop
                  and list_kind <> 'nothing' order by add_rank""", (league, team))
    assert d["source"] == "database" and d["week"] == 4 and d["total_moves"] == len(mart)
    assert [(m["add"]["sleeper_id"], (m["drop"] or {}).get("sleeper_id")) for m in d["moves"]] == \
        [(r["add_sleeper_id"], r["drop_sleeper_id"]) for r in mart]
    for m, r in zip(d["moves"], mart, strict=True):
        assert m["weekly_gain"] == pytest.approx(r["weekly_gain"], abs=0.01)
        assert m["horizon_gain"] == pytest.approx(r["horizon_gain"], abs=0.01)
        assert m["words"]["headline"] and m["words"]["why"] is not None
        assert {"headshot_url", "team", "position"} <= set(m["add"])
    assert d["weakest"] is not None and d["weakest"]["slot"]
    nothing = sql("""select count(*) as n from analytics.mart_waiver_moves where league_id = %s and roster_id = %s
                     and list_kind = 'nothing'""", (league, team))[0]["n"]
    if nothing:
        assert d["notice"].startswith("**Nothing beats what you have.**") and d["moves"] == []
    else:
        assert d["cards"] and d["cards"][0]["title"] in ("Top claim", "Best cover for a coming week")
    fa = d["free_agents"]
    assert fa and all(p["projection"] is None or p["projection"] >= 0 for p in fa)
    proj = [p["projection"] for p in fa if p["projection"] is not None]
    assert proj == sorted(proj, reverse=True)


@needs_db
def test_waiver_words_are_the_pages(client, sql):
    """The card's sentences are the Waiver Wire page's own functions run on the mart row (no copy in the API)."""
    r = sql("""select * from analytics.mart_waiver_moves where league_id = %s and roster_id = 2 and list_kind = 'start_now'
               and is_best_drop order by add_rank limit 1""", (SCRUBS,))[0]
    row = pd.Series(r)
    w = decisions.waiver_words(row, int(r["week"]))
    assert w["headline"].startswith(f"Claim {r['add_name']} ({r['add_position']})")
    assert f"{r['weekly_gain']:+.1f} this week" in w["headline"]
    assert any(line.startswith(f"Your week-{r['week']} lineup: ") for line in w["lines"])


@needs_db
@pytest.mark.parametrize("league,team", [(SCRUBS, 2), (DYNASTY, 12), (DYNASTY, 2), (SCRUBS, 5)])
def test_waivers_on_demand_reproduce_every_mart_move(sql, league, team):
    """Acceptance: the on-demand path (Sleeper's directory minus the rosters, every roster solved on request,
    waivers.sweep_roster) reproduces EVERY row of mart_waiver_moves for the roster — the same moves, gains to 0.01,
    the same ranks, best drops, lists, seats, rest-of-season tie-breaks (as_of = the nightly's)."""
    mart = pd.DataFrame(sql("select * from analytics.mart_waiver_moves where league_id = %s and roster_id = %s", (league, team)))
    od, info = decisions._moves_on_demand(league, team, as_of=_as_of(sql, league))
    assert info["week"] == int(mart["week"].iloc[0]) and len(od) == len(mart)
    if "drop_cost" not in mart or mart["drop_cost"].isna().all():
        # IF-1: a mart built before the drop's cost (no column, or the column empty: the mart view carries the columns
        # since the PO added them, the rows carry values from the next nightly): its ranks are B3's (fewest points); with the drop's value pieces
        # (per player, the same inputs on both paths) `waivers.choose_drops` must give the on-demand ranks
        from league_lab import waivers as W
        cols = ["drop_depth_lost", "drop_future_starts", "drop_future_start_weeks", "drop_season_value", "drop_upside"]
        pieces = od[od["drop_sleeper_id"].notna()].drop_duplicates("drop_sleeper_id").set_index("drop_sleeper_id")[cols]
        recs = mart.to_dict("records")
        for r in recs:
            if isinstance(r.get("drop_sleeper_id"), str) and r["drop_sleeper_id"] in pieces.index:
                r.update(pieces.loc[r["drop_sleeper_id"]].to_dict())
        mart = pd.DataFrame(W.choose_drops(recs))
    key = ["list_kind", "add_sleeper_id", "drop_sleeper_id"]
    m = mart.sort_values(key, na_position="first").reset_index(drop=True)
    o = od.sort_values(key, na_position="first").reset_index(drop=True)
    assert m[key].fillna("").equals(o[key].fillna(""))
    for c in ("weekly_gain", "horizon_gain", "lineup_before", "lineup_after", "add_value", "drop_ros_points", "add_ros_points",
              "drop_horizon_loss", "add_horizon_gain", "drop_value", "displaced_value"):
        np.testing.assert_allclose(pd.to_numeric(o[c]).astype(float), pd.to_numeric(m[c]).astype(float), atol=0.01, err_msg=c)
    for c in ("move_rank", "add_rank", "is_best_drop", "add_slot", "displaced_sleeper_id", "is_no_evidence", "open_roster_spots",
              "rest_of_season_weeks", "fills_empty_slot", "drop_is_starter"):
        assert m[c].astype(object).where(m[c].notna(), None).tolist() == o[c].astype(object).where(o[c].notna(), None).tolist(), c


@needs_db
def test_waivers_route_on_demand_matches_the_house_route(client, sql):
    """`source=sleeper` serves the same answer as the mart (moves, gains, words), computed now."""
    a = client.get(f"/api/waivers?league={SCRUBS}&team=2&limit=20").json()
    b = client.get(f"/api/waivers?league={SCRUBS}&team=2&limit=20&source=sleeper").json()
    assert b["source"] == "sleeper" and b["total_moves"] == a["total_moves"]
    assert [m["add"]["sleeper_id"] for m in a["moves"]] == [m["add"]["sleeper_id"] for m in b["moves"]]
    assert [m["words"]["headline"] for m in a["moves"]] == [m["words"]["headline"] for m in b["moves"]]
    assert [c["title"] for c in a["cards"]] == [c["title"] for c in b["cards"]]
    assert b["on_demand"]["free_agents"] > 300 and b["weakest"]["slot"] == a["weakest"]["slot"]


# ------------------------------------------------------------------------------ trades
def _page_trade(sql, league: str, team: int, give: list[str], get: list[str]) -> T.Trade:
    """What app/pages/6_Trade_Finder.py computes for the package (its queries and its calls, verbatim)."""
    horizon = pd.DataFrame(sql("""select roster_id, week, this_week, horizon_first_week, horizon_last_week, role, slot, slot_type,
                                         sleeper_player_id, gsis_id, player_name, position, fantasy_positions, player_value,
                                         value_source, lineup_margin, is_locked, reason
                                  from analytics.mart_league_roster_horizon where league_id = %s""", (league,)))
    for c in ("player_value", "lineup_margin"):
        horizon[c] = pd.to_numeric(horizon[c]).astype(float)
    slots = sql("select roster_positions from analytics.dim_league_season where league_id = %s", (league,))[0]["roster_positions"]
    season, this_week = 2026, int(horizon["this_week"].iloc[0])
    mr = pd.DataFrame(sql(T.MARKET_SQL, (league, season, this_week)))
    points = dict(zip(mr["player_key"], mr["season_points"], strict=True))
    rr = pd.DataFrame(sql(T.REPLACEMENT_SQL, (league, season, this_week, league)))
    replacement = dict(zip(rr["position"], rr["replacement"], strict=True))
    board = RosterBoard(horizon.to_dict("records"), tuple(slots))
    market = T.market_by_player(board, points)
    prices = T.price_by_player(board, market, replacement)
    return T.evaluate(board, give, get, market=market, prices=prices)


def _package(sql, league: str, team: int, partner: int = 1) -> tuple[list[str], list[str]]:
    """One player each way: my highest-valued starter this week for roster 1's (a package the page would show)."""
    def top(r):
        return sql("""select sleeper_player_id from analytics.mart_league_roster_horizon where league_id = %s and roster_id = %s
                      and is_this_week and role = 'starter' and not is_locked order by player_value desc, sleeper_player_id limit 1""",
                   (league, r))[0]["sleeper_player_id"]
    return [top(team)], [top(partner)]


@needs_db
@pytest.mark.parametrize("league", [DYNASTY, SCRUBS])
def test_trade_evaluate_reproduces_the_trade_finder(client, sql, league):
    """Dynasty 12 / Scrubs 2 give their best starter to roster 1 for roster 1's: before / after / fit / market are the
    Trade Finder's (its queries and `trades.evaluate`, run here), and the on-demand path gives the same numbers."""
    team = ANDREW[league]
    give, get = _package(sql, league, team)
    page = _page_trade(sql, league, team, give, get)
    body = {"league": league, "team": team, "partner": 1, "give": give, "get": get}
    for source in ("", "?source=sleeper"):
        d = client.post("/api/trades/evaluate" + source, json=body).json()
        assert d["source"] == ("sleeper" if source else "database")
        for who, side in (("mine", page.mine), ("theirs", page.theirs)):
            assert d["before"][who]["by_week"] == pytest.approx([round(x, 2) for x in side.before], abs=0.01)
            assert d["after"][who]["by_week"] == pytest.approx([round(x, 2) for x in side.after], abs=0.01)
            assert d["after"][who]["bench"] == pytest.approx(side.bench_after, abs=0.01)
        assert d["fit"]["this_week"]["mine"] == pytest.approx(page.mine.gain_week, abs=0.01)
        assert d["fit"]["next_4"]["theirs"] == pytest.approx(page.theirs.gain_horizon, abs=0.01)
        span = d["span"]
        assert d["verdict"] == T.verdict(page, span)
        # IE-2: the console's sentence through the review's dictionary (the label changes, the numbers stay)
        assert strip_links(d["fit"]["words"]) == decisions.dictionary_words(T.fit_line(page, span))
        if not source:                        # the market: MARKET_SQL / REPLACEMENT_SQL exactly
            assert (d["market"]["give"], d["market"]["get"]) == (page.mine.price_out, page.mine.price_in)
            assert strip_links(d["market"]["words"]) == decisions.dictionary_words(T.fairness_line(page))
        else:                                 # priced on request from the NFL-wide board: the same whole points (± 1)
            assert abs(d["market"]["give"] - page.mine.price_out) <= 1 and abs(d["market"]["get"] - page.mine.price_in) <= 1
        # IF-2: the raw totals are labelled as such — "Rest-of-season projected points (…), all positions added up — not a
        # fairness test" (the decision-quality review: they were read as a second value test)
        assert d["ros"] is None or (d["ros"]["words"].startswith("Rest-of-season projected points")
                                    and "not a fairness test" in d["ros"]["words"])
        assert d["lineups"]["mine"]["slots"] and d["size_words"].startswith("Roster size")


@needs_db
def test_trade_errors_are_plain_words(client):
    r = client.post("/api/trades/evaluate", json={"league": DYNASTY, "team": 12, "partner": 1, "give": ["nobody"], "get": []})
    assert r.status_code == 400 and "error" in r.json()
    r = client.post("/api/trades/evaluate", json={"league": DYNASTY, "team": 99, "partner": 1, "give": [], "get": []})
    assert r.status_code == 404


@needs_db
@pytest.mark.parametrize("league", [DYNASTY, SCRUBS])
def test_partners_are_the_pages_sweep(client, sql, league):
    """The partner finder = `trades.partners` on the page's board (the best package both lineups gain from per team),
    the same on demand; `want` keeps the packages that bring a player at that position."""
    team = ANDREW[league]
    d = client.get(f"/api/trades/partners?league={league}&team={team}").json()
    od = client.get(f"/api/trades/partners?league={league}&team={team}&source=sleeper").json()
    def key(rows):          # a package's players in any order (the board lists a roster in its rows' order)
        return [(r["partner"], r["shape"], tuple(sorted(x["sleeper_id"] for x in r["give"])),
                 tuple(sorted(x["sleeper_id"] for x in r["get"])), r["you_gain_horizon"], r["they_gain_horizon"]) for r in rows]
    assert key(d["partners"]) == key(od["partners"])
    assert all(r["you_gain_horizon"] >= 0.01 and r["they_gain_horizon"] >= 0.01 for r in d["partners"])
    assert d["words"]["headline"].startswith(("**Best partner:", "**No trade raises both lineups.**",
                                              "**No compelling trade found.**"))           # ---- II-1: the honest answer
    w = client.get(f"/api/trades/partners?league={league}&team={team}&want=WR").json()
    assert all(x["position"] == "WR" for r in w["partners"] for x in r["get"])


# ------------------------------------------------------------------------------ the Team Hub
@needs_db
@pytest.mark.parametrize("league", [DYNASTY, SCRUBS])
@pytest.mark.parametrize("source", ["", "&source=sleeper"])
def test_team_reproduces_the_roster_marts(client, sql, league, source):
    """Roster value and rank (mart_league_roster_value / _rankings), slot strength (_slot_strength) and the roster rows
    (_horizon, this week): the house path reads them, the on-demand path re-solves every roster and lands on them."""
    team = ANDREW[league]
    d = client.get(f"/api/team?league={league}&team={team}{source}").json()
    v = sql("select * from analytics.mart_league_roster_value where league_id = %s and roster_id = %s", (league, team))[0]
    for c in ("lineup_value", "bench_value", "horizon_value", "weakest_margin", "worst_week_value"):
        assert d["value"][c] == pytest.approx(float(v[c]), abs=0.01), c
    assert d["value"]["weakest_slot"] == v["weakest_slot"] and d["value"]["weakest_replacement_name"] == v["weakest_replacement_name"]
    for r in sql("select * from analytics.mart_league_roster_rankings where league_id = %s", (league,)):
        if r["roster_id"] == team:
            assert d["ranks"][r["measure"]]["league_rank"] == r["league_rank"]
            assert d["ranks"][r["measure"]]["value"] == pytest.approx(float(r["value"]), abs=0.01)
        row = next(x for x in d["league"] if x["roster_id"] == r["roster_id"])
        assert row[r["measure"]] == pytest.approx(float(r["value"]), abs=0.01) and row[f"{r['measure']}_rank"] == r["league_rank"]
    ss = {r["slot_type"]: r for r in sql("select * from analytics.mart_league_roster_slot_strength where league_id = %s and roster_id = %s",
                                          (league, team))}
    assert {s["slot_type"] for s in d["slot_strength"]} == set(ss)
    for s in d["slot_strength"]:
        m = ss[s["slot_type"]]
        assert (s["top"] or {}).get("gsis_id") == m["top_gsis_id"]
        assert (s["starter_strength"] is None) == (m["starter_strength"] is None)
        if m["starter_strength"] is not None:
            assert s["starter_strength"] == pytest.approx(float(m["starter_strength"]), abs=0.01)
        assert s["replacement_name"] == m["replacement_name"] and s["slots"] == m["slots"]
    rows = sql("""select sleeper_player_id, role, slot, player_value from analytics.mart_league_roster_horizon
                  where league_id = %s and roster_id = %s and is_this_week and role <> 'empty'""", (league, team))
    got = {(r["sleeper_id"], r["role"], r["slot"]): r["value"] for r in d["roster"] if r["role"] != "empty"}
    assert got == pytest.approx({(r["sleeper_player_id"], r["role"], r["slot"]): r["player_value"] for r in rows}, abs=0.01)
    assert d["words"]["lineup"][0].startswith(f"**Week {d['week']}: your best lineup projects")
    assert all(x["headshot_url"] is not None or x["position"] == "DEF" or x["gsis_id"] is None for x in d["roster"])


# ------------------------------------------------------------------------------ the league
@needs_db
@pytest.mark.parametrize("league", [DYNASTY, SCRUBS])
@pytest.mark.parametrize("source", ["", "&source=sleeper"])
def test_league_reproduces_standings_all_play_and_transactions(client, sql, league, source):
    """mart_league_standings / _all_play / _all_play_week / mart_league_transactions: read (house) or rebuilt from
    Sleeper's played weeks and transactions (on demand) — the same wins, points, standings, all-play wins, expected
    wins, luck (to 0.01) and the same transactions."""
    team = ANDREW[league]
    d = client.get(f"/api/league?league={league}&team={team}&limit=500").json()
    st = {r["roster_id"]: r for r in sql("select * from analytics.mart_league_standings where league_id = %s", (league,))}
    assert {r["roster_id"] for r in d["standings"]} == set(st)
    for r in d["standings"]:
        m = st[r["roster_id"]]
        assert (r["wins"], r["losses"], r["ties"], r["standing"]) == (m["wins"], m["losses"], m["ties"], m["standing"])
        for c in ("points_for", "points_against", "avg_points", "stddev_points", "best_week", "worst_week", "lineup_efficiency"):
            assert float(r[c]) == pytest.approx(float(m[c]), abs=0.01), c
    ap = {r["roster_id"]: r for r in sql("select * from analytics.mart_league_all_play where league_id = %s", (league,))}
    for r in d["all_play"]:
        m = ap[r["roster_id"]]
        assert (r["all_play_wins"], r["all_play_rank"], r["top_half_weeks"]) == (m["all_play_wins"], m["all_play_rank"], m["top_half_weeks"])
        for c in ("all_play_win_pct", "expected_wins", "luck_wins", "avg_points_rank"):
            assert float(r[c]) == pytest.approx(float(m[c]), abs=0.01), c
    apw = {(r["week"], r["roster_id"]): r for r in sql("select * from analytics.mart_league_all_play_week where league_id = %s", (league,))}
    assert {(r["week"], r["roster_id"]) for r in d["all_play_week"]} == set(apw)
    for r in d["all_play_week"]:
        m = apw[(r["week"], r["roster_id"])]
        assert (r["all_play_wins"], r["week_points_rank"], r["result"]) == (m["all_play_wins"], m["week_points_rank"], m["result"])
        assert float(r["week_median_others"]) == pytest.approx(float(m["week_median_others"]), abs=0.01)
    tx = sql("select transaction_id, action, sleeper_player_id, roster_id, status, waiver_bid from analytics.mart_league_transactions where league_id = %s", (league,))
    assert d["transactions_total"] == len(tx)
    if len(tx) <= 500:
        assert {(r["transaction_id"], r["action"], r["sleeper_player_id"], r["roster_id"], r["status"], r["waiver_bid"])
                for r in d["transactions"]} == {tuple(x.values()) for x in tx}
    assert d["words"]["headline"].startswith(("**You've been", "**Your record"))


# ------------------------------------------------------------------------------ the fictional Test League: every route answers
@needs_db
def test_test_league_answers_every_route(client):
    team = 3
    w = client.get(f"/api/waivers?league={TEST_LEAGUE}&team={team}").json()
    assert w["source"] == "sleeper" and w["week"] == 4 and w["free_agents"]
    assert w["moves"] or w["notice"]
    assert all(m["words"]["headline"].startswith("Claim ") for m in w["moves"])
    p = client.get(f"/api/trades/partners?league={TEST_LEAGUE}&team={team}").json()
    assert p["source"] == "sleeper" and p["words"]["headline"]
    pk = next((r for r in p["partners"] if r["is_best"]), None)
    if pk is not None:
        e = client.post("/api/trades/evaluate", json={"league": TEST_LEAGUE, "team": team, "partner": pk["partner"],
                                                      "give": [x["sleeper_id"] for x in pk["give"]],
                                                      "get": [x["sleeper_id"] for x in pk["get"]]}).json()
        assert e["fit"]["next_4"]["mine"] == pytest.approx(pk["you_gain_horizon"], abs=0.01) and e["verdict"]
    t = client.get(f"/api/team?league={TEST_LEAGUE}&team={team}").json()
    assert t["source"] == "sleeper" and t["value"]["lineup_value"] > 0 and len(t["league"]) == 10
    assert t["ranks"]["lineup_value"]["n_rosters"] == 10 and t["slot_strength"] and t["roster"]
    lg = client.get(f"/api/league?league={TEST_LEAGUE}&team={team}").json()
    assert lg["source"] == "sleeper" and len(lg["standings"]) == 10 and lg["weeks_scored"] == 2
    assert lg["transactions_total"] > 0 and {r["action"] for r in lg["transactions"]} == {"add", "drop"}
    assert sum(r["wins"] for r in lg["standings"]) == sum(r["losses"] for r in lg["standings"]) == 10
    assert lg["words"]["headline"]


@needs_db
def test_unknown_team_and_league_are_404(client):
    assert client.get(f"/api/team?league={DYNASTY}&team=99").status_code == 404
    assert client.get(f"/api/waivers?league={TEST_LEAGUE}&team=99").status_code == 404
    assert client.get("/api/league?league=12345").status_code == 404
    assert client.get(f"/api/waivers?league={DYNASTY}&team=12&position=XX").status_code == 404


@needs_db
def test_latency_cold_and_warm(client):
    """Each route cold (empty caches) and warm, on demand (the Test League) — reported in the hand-back; bounded loosely
    (two shared cores)."""
    urls = [f"/api/waivers?league={TEST_LEAGUE}&team=3", f"/api/trades/partners?league={TEST_LEAGUE}&team=3",
            f"/api/team?league={TEST_LEAGUE}&team=3", f"/api/league?league={TEST_LEAGUE}&team=3"]
    out = {}
    for u in urls:
        t0 = time.perf_counter()
        assert client.get(u).status_code == 200
        t1 = time.perf_counter()
        assert client.get(u).status_code == 200
        out[u.split("?")[0]] = (round((t1 - t0) * 1000), round((time.perf_counter() - t1) * 1000))
    print("LATENCY", json.dumps(out))
    assert all(cold < 20000 and warm < 10000 for cold, warm in out.values())


def test_fixtures_hold_the_played_weeks():
    """make_g2_fixtures.py wrote the played weeks and transactions the on-demand league reads."""
    for lid in (DYNASTY, SCRUBS, TEST_LEAGUE):
        assert (SLEEPER_FIXTURES / f"matchups_{lid}_1.json").exists() and (SLEEPER_FIXTURES / f"transactions_{lid}_1.json").exists()
    t = json.loads((SLEEPER_FIXTURES / f"transactions_{TEST_LEAGUE}_3.json").read_text())
    assert any(x["type"] == "trade" for x in t) and all(x["creator"] is None for x in t)
