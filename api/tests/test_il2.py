"""Wave I-L, IL-2 — MyFantasyLeague complete on dad's league (`mfl:70587`): transactions, live points, the waiver line,
the correctness sweep.

The 70587 fixtures are MFL's own answers (IC-3, recorded 2026-10-03) except **`transactions*.json`, which IL-2 wrote
from MFL's documented export shape** (the sandbox cannot reach MFL): five moves consistent with the week-4 rosters — team 8
adds Tuten for Conner (week 1), team 3 adds Carnell Tate for Chris Godwin (week 2), team 1 adds Ja'Kobi Lane for Mack
Hollins and teams 5 and 8 trade A.J. Brown + a 2027 3rd for DK Metcalf (week 3), team 8 drops Dalton Schultz (week 4).

1. Transactions through the Router in Sleeper's shape; the League screen's "Latest moves" lists them (one card per move,
   team names, the players' gsis ids), and nothing says "not available".
2. Live points: MFL's `liveScoring_4` (Thursday's game over: Fannin 8 for team 1) narrows the week's odds — his points
   are in, `n_played` counts him; without MFL's live scoring the same week has nobody played; the League card's
   this-week rows carry each franchise's score so far.
3. Waivers: the stamp line — first come, first served on 70587; blind bids on 21861 (MFL's export shows no balance —
   said); a waiver-order league names the team's place, a blind-bid league its balance, when the export has them — and
   "Recently added in this league" (the adds of weeks 3-4 from MFL's transactions: team 1's Ja'Kobi Lane).
4. The weekly results recomputed from our scoring: every franchise of weeks 1-2 within 2 points of MFL's, the misses
   all team defenses (a sack count, two defensive touchdowns' lengths); week 3 is not complete in our NFL stats.
5. The capabilities say what is read now.
"""

from __future__ import annotations

import pytest
from league_lab import anyleague as A
from league_lab import mfl_client as M
from league_lab import platforms as P
from league_lab import player_ids as PI
from league_lab import scoring_audit as SA

from league_lab_api import decisions, myweek, ondemand
from league_lab_api.db import query

from .conftest import needs_db
from .test_i0b import IDS, MFL_FX

KEY = "mfl:70587"


@pytest.fixture(autouse=True)
def mfl(monkeypatch):
    monkeypatch.setenv(M.FIXTURES_ENV, str(MFL_FX))
    monkeypatch.setenv(PI.CSV_ENV, str(IDS))
    monkeypatch.setenv(M.YEAR_ENV, "2026")
    PI.reset()
    A._default = None
    yield
    PI.reset()
    A._default = None


# ------------------------------------------------------------------ 1. transactions
def test_transactions_in_sleeper_shape_through_the_router():
    sl = A.sleeper()
    weeks = {w: sl.transactions(KEY, w) for w in range(1, 5)}
    assert [len(weeks[w]) for w in range(1, 5)] == [1, 1, 2, 1]
    keys = {"transaction_id", "type", "status", "leg", "roster_ids", "adds", "drops", "draft_picks", "waiver_budget",
            "creator", "created", "status_updated", "settings", "metadata", "consenter_ids"}
    for w, ts in weeks.items():
        for t in ts:
            assert set(t) == keys and t["leg"] == w and t["status"] == "complete"
            assert t["type"] in ("free_agent", "waiver", "trade", "commissioner")
            assert isinstance(t["created"], int) and t["created"] > 1_700_000_000_000          # epoch ms
            for sid, rid in {**(t["adds"] or {}), **(t["drops"] or {})}.items():
                assert 1 <= rid <= 12 and sid and not sid.startswith("mfl:")             # every player mapped
    tuten = weeks[1][0]
    d = sl.players()
    assert [d[s]["full_name"] for s in tuten["adds"]] == ["Bhayshul Tuten"] and list(tuten["adds"].values()) == [8]
    assert [d[s]["full_name"] for s in tuten["drops"]] == ["James Conner"]
    trade = weeks[3][1]
    assert trade["type"] == "trade" and trade["roster_ids"] == [5, 8] and len(trade["draft_picks"]) == 1


@needs_db
def test_league_screen_lists_mfls_moves(client):
    d = client.get(f"/api/league?league={KEY}&team=1").json()
    assert d["source"] == "sleeper" and d["on_demand"]["transaction_rounds"] == 4
    tx = d["transactions"]
    assert d["transactions_total"] == 11 == len(tx)                      # one row per player moved
    assert len({t["transaction_id"] for t in tx}) == 5                   # five moves
    assert [t["week"] for t in tx] == sorted((t["week"] for t in tx), reverse=True)        # newest first
    knight = [t for t in tx if t["team_name"] == "Knight Train"]
    assert {(t["action"], t["player_name"]) for t in knight} == {("add", "Ja'Kobi Lane"), ("drop", "Mack Hollins")}
    trade = [t for t in tx if t["transaction_type"] == "trade"]
    assert {(t["team_name"], t["action"], t["player_name"]) for t in trade} == {
        ("Big Mac Attack", "add", "A.J. Brown"), ("Millertime", "drop", "A.J. Brown"),
        ("Millertime", "add", "DK Metcalf"), ("Big Mac Attack", "drop", "DK Metcalf")}
    assert all(t["gsis_id"] for t in tx) and all(t["waiver_bid"] is None for t in tx)
    caps = client.get("/api/providers").json()["providers"][1]
    assert caps["provider"] == "mfl" and caps["features"]["transactions"]["unavailable"] is None


# ------------------------------------------------------------------ 2. live points
def test_live_points_are_mfls_scores_by_sleeper_id():
    lp = A.sleeper().mfl.live_points(KEY, 4)
    fannin = PI.table().mfl_to_sleeper("17103")
    assert lp["points"][fannin] == 8.0 and fannin in lp["done"]
    assert lp["teams_done"] == {"CLE", "PIT"}                          # Thursday's game of week 4
    assert lp["franchises"][1]["score"] == 8.0 and lp["franchises"][5]["yet_to_play"] == 7.0
    assert ondemand.mfl_week_points(None, KEY, 4)[fannin] == 8.0
    assert ondemand.mfl_teams_done(None, KEY, 4) == {"CLE", "PIT"}
    assert myweek.live_scored(KEY, 4, set(), house=False) == {"CLE", "PIT"}
    assert myweek.live_scored(KEY, 4, {"ATL"}, house=True) == {"ATL"}           # a house league: the nightly only
    assert myweek.live_scored("1389709692405551104", 4, set(), house=False) == set()   # Sleeper: unchanged


def test_this_weeks_matchups_carry_the_live_score():
    ms = A.sleeper().matchups(KEY, 4)
    by = {}
    for m in ms:
        by.setdefault(m["roster_id"], []).append(m)
    assert {m["points"] for m in by[1]} == {8.0} and len(by[1]) == 2         # both games of the double header
    assert list(by[1][0]["players_points"].values()) == [8.0]
    assert A.sleeper().matchups(KEY, 3)[0].get("players_points") is None      # another week: the schedule's rows


@needs_db
def test_live_points_narrow_the_weeks_odds(client, monkeypatch):
    d = client.get(f"/api/my-week?league={KEY}&team=1").json()
    assert d["week"] == 4
    w = d["win"]
    assert w["p"] is not None and w["n_played"] == 1 and w["opp_n_played"] == 0
    assert w["line"].endswith(f"1 of your {w['n_starters']} have played, 0 of theirs.")
    assert len(w["also"]) == 1 and w["also"][0]["n_played"] == 1                # the double header's second game
    # without MFL's live scoring the same week has nobody played (IH-3's rule: the nightly has not scored week 4)
    monkeypatch.setattr(ondemand, "mfl_teams_done", lambda client, league_id, week: set())
    A._default = None
    before = client.get(f"/api/my-week?league={KEY}&team=1").json()["win"]
    assert before["n_played"] == 0 and before["p"] is not None
    assert before["mine"] != pytest.approx(w["mine"])                         # Fannin's 8 replaced his range


@needs_db
def test_league_week_odds_and_the_live_score_on_the_card(client):
    o = client.get(f"/api/league/week-odds?league={KEY}").json()
    assert o["week"] == 4 and len(o["games"]) == 12 and o["note"] is None
    played = {sd["roster_id"]: sd["n_played"] for g in o["games"] for sd in (g["a"], g["b"])}
    assert played[1] == 1 and played[8] == 0 and played[10] == 1
    d = client.get(f"/api/league?league={KEY}&team=1").json()
    this = next(m for m in d["matchups"] if not m["played"])
    live = {sd["roster_id"]: sd["live"] for g in this["games"] for sd in (g["a"], g["b"])}
    assert live[1] == 8.0 and live[10] == 10.0 and live[6] == 12.0 and live[8] is None    # 0 so far: nothing said
    last = next(m for m in d["matchups"] if m["played"])
    assert all(sd["live"] is None for g in last["games"] for sd in (g["a"], g["b"]))


# ------------------------------------------------------------------ 3. the waiver line
def test_waiver_line_first_come_and_blind_bids(monkeypatch):
    fcfs = decisions.waivers_deadline_for(KEY, 2026, 4, False)
    assert fcfs["kind"] == "fcfs" and fcfs["words"].startswith("Free agents are first come, first served on MFL")
    assert decisions.mfl_waiver_franchise(fcfs, KEY, 1) == fcfs             # first come: no order, no budget
    bb = decisions.mfl_waiver_franchise(decisions.waivers_deadline_for("mfl:21861", 2026, 4, False), "mfl:21861", 4)
    assert bb["kind"] == "blind_bid_fcfs" and bb["budget_left"] is None
    assert "see MFL for the time; your blind-bid balance is not in MFL's league export;" in bb["words"]
    # the export's fields when a league carries them (MFL's documented `bbidAvailableBalance` / `waiverSortOrder`)
    raw = A.sleeper().mfl.client.league("21861")
    fr = M._as_list(raw["franchises"]["franchise"])
    fr[3] = {**fr[3], "bbidAvailableBalance": "87.50", "waiverSortOrder": "4"}
    monkeypatch.setattr(A.sleeper().mfl.client, "league", lambda lid: {**raw, "franchises": {"franchise": fr}})
    bb2 = decisions.mfl_waiver_franchise(decisions.waivers_deadline_for("mfl:21861", 2026, 4, False), "mfl:21861", 4)
    assert bb2["budget_left"] == 87.5 and "your blind-bid balance is $87.5;" in bb2["words"]
    wo = decisions.mfl_waiver_franchise({**bb2, "kind": "waiver_order", "words": "Claims run on MFL's schedule for this "
                                         "league (waiver order): see MFL for the time."}, "mfl:21861", 4)
    assert wo["waiver_order"] == 4 and wo["words"].endswith("see MFL for the time; you are 4th in the waiver order.")
    assert decisions.mfl_waiver_franchise(fcfs, "1389709692405551104", 1) == fcfs            # Sleeper: unchanged


@needs_db
def test_waivers_recently_added_on_mfl(client, monkeypatch):
    d = client.get(f"/api/waivers?league={KEY}&team=1").json()
    r = d["recent_adds"]
    assert r["weeks"] == [3, 4] and r["unavailable"] is None and r["total"] == 1
    assert r["source"] == "MyFantasyLeague transactions"
    row = r["rows"][0]
    assert (row["player_name"], row["position"], row["team_name"], row["week"], row["transaction_type"], row["mine"]) == \
        ("Ja'Kobi Lane", "WR", "Knight Train", 3, "free_agent", True)
    assert row["gsis_id"] and row["waiver_bid"] is None
    # a platform whose moves are not read says so, never an empty list
    monkeypatch.setattr(P, "unavailable", lambda provider, feature: "Transactions: not available for MFL leagues yet")
    assert decisions.recent_adds(KEY, 1, 4, False)["unavailable"] == "Transactions: not available for MFL leagues yet"


# ------------------------------------------------------------------ 4. the weekly results recomputed
@needs_db
def test_weekly_results_recomputed_from_our_scoring():
    lg = A.sleeper().league(KEY)
    gaps = []
    for w, within in ((1, 10), (2, 11)):
        r = SA.franchise_recompute(query, lg, w)
        assert r["why_empty"] is None and len(r["franchises"]) == 12
        assert r["within_1"] == within and r["max_gap"] <= 2.0                # tolerance: 2 points a franchise
        for f in r["franchises"]:
            assert f["priced"] == f["starters"] and not f["unpriced"]       # every starter priced
            for b in f["biggest"]:
                gaps.append((w, f["franchise"], b["player"], b["position"], b["gap"]))
    assert gaps == [(1, "0007", "Kansas City Chiefs", "DEF", -2.0), (1, "0010", "Pittsburgh Steelers", "DEF", 1.36),
                    (2, "0006", "New England Patriots", "DEF", 1.36)]
    assert "not complete" in SA.franchise_recompute(query, lg, 3)["why_empty"]


# ------------------------------------------------------------------ 5. what the capabilities say
def test_capabilities_say_what_is_read_now():
    c = P.capabilities("mfl")["features"]
    assert c["transactions"]["status"] == "yes" and c["transactions"]["words"].startswith(
        "adds, drops, trades and waiver claims from MFL's transactions export")
    assert c["matchups"]["status"] == "yes" and "live points from MFL's live scoring" in c["matchups"]["words"]
    assert "waiver order and blind-bid balances are read" in c["waivers"]["words"]
    assert P.unavailable("mfl", "transactions") is None


def test_playoff_teams_never_more_than_the_league():
    st = A.sleeper().league(KEY)["settings"]
    assert st["playoff_week_start"] == 15 and st["playoff_teams"] == 12 and st["num_teams"] == 12
    assert A.ros_window(A.sleeper().league(KEY), 4, 18) == (4, 18, 15)        # the window is unchanged (4 rounds)


# ------------------------------------------------------------------ the web's e2e recordings (web/e2e/il2)
@needs_db
@pytest.mark.skipif(not __import__("os").environ.get("IL2_RECORD"), reason="records web/fixtures/il2/api_il2.json: IL2_RECORD=1")
def test_record_e2e_answers(client):
    """The answers web/e2e/il2 replays: dad's league team 1 — League (the moves, this week's live scores and odds), My
    Week (the win line with Thursday's game in), the MFL pick and rosters, the providers, the status."""
    import json
    from urllib.parse import urlencode

    from league_lab_api.settings import ROOT

    def key(path: str, **q) -> str:
        return path + ("?" + urlencode(sorted((k, str(v)) for k, v in q.items())) if q else "")

    out: dict = {}

    def rec(path: str, **q):
        r = client.get(key(path, **q))
        out[key(path, **q)] = {"status": r.status_code, "body": r.json()}

    rec("/api/leagues", mfl_search="70587")
    rec("/api/leagues/mfl%3A70587/rosters")
    rec("/api/league", league=KEY, team=1)
    rec("/api/league/week-odds", league=KEY)
    rec("/api/my-week", league=KEY, team=1)
    rec("/api/waivers", league=KEY, team=1, position="ALL")
    rec("/api/providers")
    rec("/api/status")
    f = ROOT / "web" / "fixtures" / "il2" / "api_il2.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(out, indent=1, default=str) + "\n")
    assert all(v["status"] == 200 for v in out.values()), {k: v["status"] for k, v in out.items()}
