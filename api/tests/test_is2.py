"""IS-2 (Wave I-S): inside a league, the same "can he play" check as the public lists, and the reason beside the zero.

Each moved reader gets a player whose old field (``mart_player_availability.injury_status`` / nflverse's
``report_status``) says nothing and whose status block (``availability.statuses``) says IR: the reader must leave him
out and say why. And the reverse: an old "Out" with no word from the one definition no longer leaves anyone out.
Hand-built frames and blocks; no database."""

import pandas as pd
import pytest
from league_lab import availability_gate as AG
from league_lab import league_status as LS

from league_lab_api import decisions as D
from league_lab_api import league_gate as LG

ACHANE = "00-0039040"
OUT_ONLY = "00-0000002"
HEALTHY = "00-0000003"


def _block(code, note=None, as_of="2026-09-28T15:00:00Z"):
    return {"gsis_id": None, **AG.classify(AG.entry(code, "Sleeper", as_of=as_of, note=note))}


IR = _block("IR", "knee - acl")
OUT = _block("OUT", "ankle", as_of="2026-10-07T20:00:00Z")


@pytest.fixture
def gate(monkeypatch):
    """league_gate.blocks answers from a hand-built table (the request-time statuses)."""
    table = {ACHANE: IR, OUT_ONLY: OUT}

    def blocks(ids, season=None, wk=None):
        return {g: table[g] for g in (table if ids is None else ids) if g in table}
    monkeypatch.setattr(LG, "blocks", blocks)
    return table


def test_the_block_words_are_the_gates():
    n = LG.note(IR)
    assert n["why"] == "IR (knee - acl) · Sleeper, Sep 28" and n["sits"] is True and n["out_indefinitely"] is True
    assert n["words"] == AG.ROS_WORDS.format(reason="On injured reserve")
    o = LG.note(OUT)
    assert o["sits"] is True and o["out_indefinitely"] is False and o["words"].startswith("Ruled out this week")
    assert LG.note(None) is None and LG.sits(None) is False


def test_waiver_browse_leaves_out_an_ir_player_the_old_field_calls_healthy(monkeypatch, gate):
    fa = pd.DataFrame([
        {"sleeper_id": "9226", "gsis_id": ACHANE, "player_name": "De'Von Achane", "position": "RB", "nfl_team": "MIA",
         "roster_status": "ACT", "injury_status": None, "games_played": 4, "proj_points": 11.42, "p10": 3.0, "p25": 6.0,
         "p75": 15.0, "p90": 19.0},
        {"sleeper_id": "2", "gsis_id": OUT_ONLY, "player_name": "Out Only", "position": "RB", "nfl_team": "NYJ",
         "roster_status": "ACT", "injury_status": None, "games_played": 4, "proj_points": 9.0, "p10": 2.0, "p25": 5.0,
         "p75": 12.0, "p90": 15.0},
        {"sleeper_id": "3", "gsis_id": HEALTHY, "player_name": "Last Week Out", "position": "RB", "nfl_team": "NYJ",
         "roster_status": "ACT", "injury_status": "Out", "games_played": 4, "proj_points": 7.0, "p10": 2.0, "p25": 4.0,
         "p75": 9.0, "p90": 11.0},
    ])
    monkeypatch.setattr(D, "query", lambda sql, params=None: fa.copy())
    monkeypatch.setattr(D.ui, "league_slots", lambda lid: ["QB", "RB", "WR", "TE"], raising=False)
    monkeypatch.setattr(D, "bio", lambda ids: {})
    out = D._free_agents("L", 2026, 5, "RB", 50, True, {}, {})
    by = {p["gsis_id"]: p for p in out}
    assert ACHANE not in by                                    # out indefinitely: not a free agent to add this week
    o = by[OUT_ONLY]                                           # out this week: listed at 0, with the reason beside it
    assert o["projection"] == 0.0 and o["injury_status"] == "Out"
    assert o["availability"]["why"] == "Out (ankle) · Sleeper, Oct 7" and o["availability"]["sits"] is True
    h = by[HEALTHY]                                            # last week's report word rules nothing
    assert h["projection"] == 7.0 and h["injury_status"] is None and h["availability"] is None


def test_trade_fill_pool_marks_an_ir_player_unplayable_with_his_reason(monkeypatch, gate):
    pool = pd.DataFrame([
        {"sleeper_id": "9226", "gsis_id": ACHANE, "player_name": "De'Von Achane", "position": "RB", "week": w,
         "value": 11.0, "report_status": None, "roster_status": "ACT", "team": "MIA"} for w in (5, 6)] + [
        {"sleeper_id": "2", "gsis_id": OUT_ONLY, "player_name": "Out Only", "position": "RB", "week": w,
         "value": 9.0, "report_status": None, "roster_status": "ACT", "team": "NYJ"} for w in (5, 6)] + [
        {"sleeper_id": "3", "gsis_id": HEALTHY, "player_name": "Last Week Out", "position": "RB", "week": 5,
         "value": 7.0, "report_status": "Doubtful", "roster_status": "ACT", "team": "NYJ"}])
    games = pd.DataFrame(columns=["home_team", "away_team", "kickoff_at"])
    monkeypatch.setattr(D, "query", lambda sql, params=None: pool.copy() if "is_free_agent" in sql else games)
    got, _meta = D._house_fa_pool("L", 2026, (5, 6))
    assert got["9226"][5].playable is False and got["9226"][5].reason == "IR (knee - acl) · Sleeper, Sep 28"
    assert got["9226"][6].playable is False                    # out indefinitely: every week
    assert got["2"][5].playable is False and got["2"][6].playable is True       # out this week only
    assert got["3"][5].playable is True                        # a report status is not the definition


def test_on_demand_free_agents_get_the_request_time_blocks(monkeypatch, gate):
    seen = {}

    def fake(query, league_id, rosters, players, slots, blocks=None):
        seen["blocks"] = blocks
        return pd.DataFrame()
    monkeypatch.setattr(D.A, "free_agents", fake)
    D.il4_free_agents({"league_id": "X"}, [], {}, ["RB"])
    assert seen["blocks"] is not None and ACHANE in seen["blocks"]


def test_no_status_test_of_its_own():
    """The readers ask sits(); none keeps a set of status codes or tests a status string (the old ones are gone)."""
    import inspect

    from league_lab_api import ondemand, player
    src = inspect.getsource(D._free_agents) + inspect.getsource(D._house_fa_pool)
    assert "injury_status is distinct from" not in D.FA_SQL and "injury_status is distinct from" not in D.FA_POOL_SQL
    assert '("Out", "Doubtful")' not in src
    assert "UNPLAYABLE_NOW" not in inspect.getsource(ondemand.lineup_values)
    assert "ov = overlay_status(gsis, inj)" not in inspect.getsource(player)
    assert LS.sits(IR) and not LS.sits(_block("QUESTIONABLE"))


def test_waiver_browse_without_any_record_answers(monkeypatch):
    """Between a deploy and the refresh (no stored record, the overlay off): nobody has a word — no 500 (a frame's
    missing block is NaN, not None: the first check on last night's schema answered 500 before the fix)."""
    fa = pd.DataFrame([{"sleeper_id": "3", "gsis_id": HEALTHY, "player_name": "A", "position": "RB", "nfl_team": "NYJ",
                        "roster_status": "ACT", "injury_status": "Out", "games_played": 4, "proj_points": 7.0,
                        "p10": 2.0, "p25": 4.0, "p75": 9.0, "p90": 11.0},
                       {"sleeper_id": "4", "gsis_id": None, "player_name": "B", "position": "DEF", "nfl_team": "NYJ",
                        "roster_status": "ACT", "injury_status": None, "games_played": 4, "proj_points": None,
                        "p10": None, "p25": None, "p75": None, "p90": None}])
    monkeypatch.setattr(LG, "blocks", lambda ids, season=None, wk=None: {})
    monkeypatch.setattr(D, "query", lambda sql, params=None: fa.copy() if "is_free_agent" in sql else pd.DataFrame(
        columns=["unit_id", "proj_points", "p10", "p90"]))
    monkeypatch.setattr(D.ui, "league_slots", lambda lid: ["RB"], raising=False)
    monkeypatch.setattr(D, "bio", lambda ids: {})
    out = D._free_agents("L", 2026, 5, "RB", 50, True, {}, {})
    assert all(p["availability"] is None for p in out)
    assert next(p for p in out if p["gsis_id"] == HEALTHY)["projection"] == 7.0
