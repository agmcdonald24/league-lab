"""Wave I-L, IL-2 — MyFantasyLeague complete on dad's league: the client's transactions and live scoring.

1. ``MFL.transactions``: the export's URL (``TYPE=transactions&L=&W=&TRANS_TYPE=*``), cached like the other exports (a
   week still open 10 minutes, a settled week a day), the budget respected, a fixture league without moves = [].
2. ``transaction_moves``: MFL's documented shapes — free agents and waivers ``"added,|dropped,"``, blind bids
   ``"added,|bid|dropped,"``, trades both ways with a future pick; IR / taxi / pool rows move nobody (None).
3. ``live_players`` / ``live_franchises`` on the recorded ``liveScoring_4`` (MFL's own answer, week 4 of 70587: Thursday's
   game over, the double header listing each franchise twice).
4. ``range_gaps``: where "the minimum + FLEX" reading of MFL's starter ranges differs from MFL's rule.
5. ``MFLLeagues.transactions`` in Sleeper's shape on the synthetic 70587 fixture (MFL's documented shape — the sandbox
   cannot reach MFL; the PO verifies on the real league after the deploy).
"""

from __future__ import annotations

import json
import urllib.parse
from pathlib import Path

import pytest

from league_lab import mfl_client as M
from league_lab import platforms as P
from league_lab import player_ids as PI
from league_lab.sleeper_client import TokenBucket

ROOT = Path(__file__).resolve().parents[1]
MFL_FX = ROOT / "api" / "tests" / "fixtures" / "mfl"
IDS = ROOT / "api" / "tests" / "fixtures" / "ff" / "db_playerids.csv"


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def _client(answer: dict, clock: Clock | None = None, per_minute: float = 60):
    calls: list[str] = []
    clock = clock or Clock()

    def fetch(url: str):
        calls.append(url)
        return url.replace("api.myfantasyleague.com", "www44.myfantasyleague.com"), json.dumps(answer)
    c = M.MFL(fixtures="", year=2026, clock=clock, bucket=TokenBucket(per_minute, clock=clock), fetch=fetch)
    c.fixtures = None
    return c, calls, clock


ROWS = {"transactions": {"transaction": [
    {"timestamp": "1789600320", "franchise": "0001", "type": "FREE_AGENT", "transaction": "17517,|13289,"},
    {"timestamp": "1789609200", "franchise": "0003", "type": "BBID_WAIVER", "transaction": "17497,|12.50|13163,"}]}}


# ------------------------------------------------------------------ 1. the client
def test_transactions_url_and_rows():
    c, calls, _ = _client(ROWS)
    rows = c.transactions("70587", 2)
    assert [r["franchise"] for r in rows] == ["0001", "0003"]
    q = urllib.parse.parse_qs(urllib.parse.urlparse(calls[0]).query)
    assert q["TYPE"] == ["transactions"] and q["L"] == ["70587"] and q["W"] == ["2"] and q["TRANS_TYPE"] == ["*"]
    assert q["JSON"] == ["1"] and calls[0].startswith("https://api.myfantasyleague.com/2026/export?")
    c.transactions("70587")                                              # the season: no W
    assert "W" not in urllib.parse.parse_qs(urllib.parse.urlparse(calls[1]).query)
    # a single transaction is an object in MFL's JSON: still a list here
    one, _, _ = _client({"transactions": {"transaction": ROWS["transactions"]["transaction"][0]}})
    assert len(one.transactions("70587", 2)) == 1
    empty, _, _ = _client({"transactions": {}})
    assert empty.transactions("70587", 1) == []


def test_transactions_are_cached_ten_minutes_and_a_settled_week_a_day():
    c, calls, clock = _client(ROWS)
    c.transactions("70587", 4)
    c.transactions("70587", 4)
    assert len(calls) == 1                                               # cached
    clock.t += M.TTL_S["transactions"] + 1
    c.transactions("70587", 4)
    assert len(calls) == 2 and M.TTL_S["transactions"] == 600
    c.transactions("70587", 2, settled=True)
    clock.t += 3600
    c.transactions("70587", 2, settled=True)
    assert len(calls) == 3 and M.TTL_S["transactions_past"] == 24 * 3600
    assert c.stats()["cache"]["transactions_past"]["entries"] == 1


def test_transactions_respect_the_budget():
    c, calls, _ = _client(ROWS, per_minute=1)
    c.transactions("70587", 1)
    with pytest.raises(M.MFLBusy):
        c.transactions("70587", 2)                                       # the bucket is empty, nothing cached
    assert len(calls) == 1 and c.transactions("70587", 1)               # a cached week is still served


def test_fixture_league_without_moves_and_the_70587_fixture():
    c = M.MFL(fixtures=MFL_FX, year=2026)
    assert c.transactions("21861", 3) == []                              # no file recorded: no moves
    assert len(c.transactions("70587")) == 5                             # the season file
    assert [r["type"] for r in c.transactions("70587", 3)] == ["TRADE", "FREE_AGENT"]


# ------------------------------------------------------------------ 2. the shapes
def test_free_agent_waiver_and_blind_bid():
    fa = M.transaction_moves({"timestamp": "1789600320", "franchise": "0001", "type": "FREE_AGENT",
                              "transaction": "17517,|13289,"})
    assert fa == {"kind": "free_agent", "type": "FREE_AGENT", "franchise": "0001", "adds": {"17517": "0001"},
                  "drops": {"13289": "0001"}, "bid": None, "picks": [], "timestamp": 1789600320}
    drop_only = M.transaction_moves({"timestamp": "1", "franchise": "0008", "type": "FREE_AGENT", "transaction": "|13772,"})
    assert drop_only["adds"] == {} and drop_only["drops"] == {"13772": "0008"}
    w = M.transaction_moves({"timestamp": "2", "franchise": "0002", "type": "WAIVER", "transaction": "15000,15001,|"})
    assert w["kind"] == "waiver" and set(w["adds"]) == {"15000", "15001"} and w["drops"] == {} and w["bid"] is None
    b = M.transaction_moves({"timestamp": "3", "franchise": "0003", "type": "BBID_WAIVER",
                             "transaction": "17497,|12.50|13163,"})
    assert b["kind"] == "waiver" and b["bid"] == 12.5 and b["adds"] == {"17497": "0003"} and b["drops"] == {"13163": "0003"}
    no_drop = M.transaction_moves({"timestamp": "4", "franchise": "0003", "type": "BBID_WAIVER", "transaction": "17497,|5.00|"})
    assert no_drop["bid"] == 5.0 and no_drop["drops"] == {}


def test_trade_both_ways_with_a_future_pick():
    t = M.transaction_moves({"timestamp": "1790188200", "franchise": "0005", "type": "TRADE", "franchise2": "0008",
                             "franchise1_gave_up": "14104,FP_0005_2027_3,", "franchise2_gave_up": "14102,",
                             "comments": "", "expires": "1790793000"})
    assert t["kind"] == "trade"
    assert t["adds"] == {"14104": "0008", "14102": "0005"} and t["drops"] == {"14104": "0005", "14102": "0008"}
    assert t["picks"] == [("0005", "0008", "0005", 2027, 3)]
    assert M.transaction_moves({"timestamp": "5", "franchise": "0005", "type": "TRADE"}) is None   # no partner: unread


@pytest.mark.parametrize("row", [
    {"timestamp": "1", "franchise": "0001", "type": "IR", "transaction": "|15708,"},
    {"timestamp": "1", "franchise": "0001", "type": "TAXI", "transaction": "15708,|"},
    {"timestamp": "1", "franchise": "0001", "type": "SURVIVOR_PICK", "transaction": "BUF"},
    {"timestamp": "1", "franchise": "0001", "type": "WAIVER_REQUEST", "transaction": "1,|2,"},
    {"timestamp": "1", "franchise": "", "type": "FREE_AGENT", "transaction": "1,|2,"},
    {"timestamp": "1", "franchise": "0001", "type": "FREE_AGENT", "transaction": "|"},
])
def test_rows_that_move_nobody_between_teams(row):
    assert M.transaction_moves(row) is None


# ------------------------------------------------------------------ 3. live scoring (MFL's own recording)
def test_live_scoring_week_4_players_and_franchises():
    live = M.MFL(fixtures=MFL_FX, year=2026).live_scoring("70587", 4)
    pl = M.live_players(live)
    done = {i: p for i, p in pl.items() if p["seconds_left"] == 0}
    assert {i: p["score"] for i, p in done.items()} == {"17103": 8.0, "0510": 10.0, "0710": 4.0, "15742": 12.0}
    assert pl["17103"]["franchise"] == "0001" and pl["17103"]["status"] == "starter"
    assert all(p["seconds_left"] == 3600 for i, p in pl.items() if i not in done)          # not kicked off yet
    fr = M.live_franchises(live)
    assert len(fr) == 12                                                 # the double header lists each twice: one row each
    assert fr["0001"] == {"score": 8.0, "seconds_left": 0.0, "yet_to_play": 0.0, "playing": 0.0}
    assert fr["0005"]["score"] == 4.0 and fr["0005"]["yet_to_play"] == 7.0
    assert M.live_players(None) == {} and M.live_franchises({}) == {}


# ------------------------------------------------------------------ 4. starter ranges
def test_range_gaps():
    assert M.range_gaps({"RB": (2, 4), "WR": (2, 4), "TE": (1, 3)}, flex=2, super_flex=0) == []     # 21861: exact
    assert M.range_gaps({"TE": (1, 2), "WR": (2, 4)}, flex=2, super_flex=0) == [
        "TE: we allow up to 3 in the lineup (the 2 FLEX spots), MyFantasyLeague at most 2"]
    assert M.range_gaps({"K": (0, 1)}, flex=1, super_flex=0) == [
        "K: MyFantasyLeague allows up to 1, we start 0 (the FLEX does not take a K)"]
    assert M.range_gaps({"QB": (1, 2)}, flex=0, super_flex=1) == []
    assert M.range_gaps({"QB": (1, 3)}, flex=1, super_flex=1) == ["QB: MyFantasyLeague allows up to 3, we start at most 2"]
    for lid in ("21861", "10015", "70587"):                              # the fixture leagues: exact
        assert M.slots(M.MFL(fixtures=MFL_FX, year=2026).league(lid))[1]["range_gaps"] == []


# ------------------------------------------------------------------ 5. the adapter, Sleeper's shape
@pytest.fixture
def ids(monkeypatch):
    monkeypatch.setenv(PI.CSV_ENV, str(IDS))
    PI.reset()
    yield
    PI.reset()


def test_adapter_transactions_in_sleeper_shape(ids):
    mf = P.MFLLeagues(M.MFL(fixtures=MFL_FX, year=2026), lambda: {})
    w3 = mf.transactions("mfl:70587", 3)
    assert len(w3) == 2
    t = w3[1]
    assert t["type"] == "trade" and t["status"] == "complete" and t["leg"] == 3 and t["roster_ids"] == [5, 8]
    sid = {i: PI.table().mfl_to_sleeper(i) for i in ("14104", "14102")}       # A.J. Brown, DK Metcalf
    assert t["adds"] == {sid["14104"]: 8, sid["14102"]: 5} and t["drops"] == {sid["14104"]: 5, sid["14102"]: 8}
    assert t["draft_picks"] == [{"season": "2027", "round": 3, "roster_id": 5, "previous_owner_id": 5, "owner_id": 8}]
    assert t["created"] == 1790188200 * 1000 and t["settings"] is None and t["transaction_id"].startswith("mfl-1790188200-0005-")
    assert mf.transactions("mfl:70587", 3)[1]["transaction_id"] == t["transaction_id"]    # stable across reads
    w4 = mf.transactions("mfl:70587", 4)
    assert w4[0]["adds"] is None and list(w4[0]["drops"].values()) == [8]
    assert [x["roster_ids"] for x in mf.transactions("mfl:70587", 3)] == [[1], [5, 8]]    # oldest first
    assert mf.unmapped("mfl:70587") == []                                # transaction players are not "rostered"
