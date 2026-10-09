"""IT-3 (Wave I-T): inside a league, the last readers on the one definition, and the caveats on screen. Hand-built
answers and frames; no database."""

import pandas as pd
from league_lab import availability_gate as AG

from league_lab_api import league_gate as LG
from league_lab_api import myweek as M

ACHANE, HEALTHY = "00-0039040", "00-0000003"


def _block(code, note=None, as_of="2026-09-28T15:00:00Z"):
    return {"gsis_id": None, **AG.classify(AG.entry(code, "Sleeper", as_of=as_of, note=note))}


def test_a_starter_who_left_the_roster_is_not_a_wildcard_in_the_slot_chain():
    """The PO's QA (Wave I-S): "Start Wilson at WR in place of Mahomes" (WR2) while Mahomes, a quarterback, was on a
    bye — the submitted lineup still held players no longer on the roster (unknown position), and the chain let one of
    them 'fill' the quarterback spot so a receiver could come in for Mahomes. He keeps his own slot now."""
    pos = {"qb": "QB", "rb1": "RB", "wr1": "WR", "wr2": "WR", "te": "TE", "wilson": "WR"}
    current = {"qb": "QB", "rb1": "RB", "gone": "RB", "wr1": "WR", "wr2": "WR", "te": "TE", "gone2": "FLEX"}
    pairs = M.pair_moves(["wilson"], ["qb"], current, lambda k: pos.get(k))
    assert ("wilson", "qb") not in pairs
    assert pairs == [(None, "qb"), ("wilson", None)]
    # a legal chain still pairs: a running back out, a receiver in through FLEX (the RB in FLEX slides to RB)
    pos2 = {"qb": "QB", "rb1": "RB", "rb2": "RB", "wr1": "WR", "flex": "RB", "wilson": "WR"}
    cur2 = {"qb": "QB", "rb1": "RB", "rb2": "RB", "wr1": "WR", "flex": "FLEX"}
    assert M.pair_moves(["wilson"], ["rb2"], cur2, lambda k: pos2.get(k)) == [("wilson", "rb2")]


def test_my_week_and_waivers_caveats_are_in_a_lineups_words(monkeypatch):
    from league_lab_api import provenance as P
    from league_lab_api import starters as ST

    def caveats_for(players, season, week):
        return [{"kind": "starter_unclear", "effect": P.WITHHOLD, "team": "TB", "players": ["Baker Mayfield"],
                 "listed": "Jalon Daniels", "other": "Baker Mayfield", "words": "No verdict while …"},
                {"kind": "starter_set_by_hand", "effect": P.SOFTEN, "team": "SEA", "players": ["Sam Darnold"],
                 "listed": "Drew Lock", "set": "Sam Darnold", "words": "… read the verdict as a lean …"}]
    monkeypatch.setattr(P, "caveats_for", caveats_for)
    monkeypatch.setattr(ST, "team_name", lambda t: {"TB": "Tampa Bay", "SEA": "Seattle"}.get(t, t))
    monkeypatch.setattr(LG, "week", lambda: (2026, 5))
    m = LG.with_lineup({"week": 5, "lineup_full": [{"gsis_id": "g1", "position": "QB", "team": "TB", "player_name": "Baker Mayfield"}]})
    words = [c["words"] for c in m["caveats"]]
    assert words == ["Tampa Bay's starter is unclear: Jalon Daniels is listed, the depth chart puts Baker Mayfield first. "
                     "Baker Mayfield's projection assumes the listing — check who starts before kickoff.",
                     "Seattle's starter was set by hand (Sam Darnold, not the listed Drew Lock): Sam Darnold's projection "
                     "assumes Darnold starts."]
    assert not any("verdict" in w for w in words) and m["caveats"][0]["verdict_words"] == "No verdict while …"
    assert m["caveat_effect"] == P.WITHHOLD and "provenance" in m


def test_role_alerts_leave_out_a_player_who_sits(monkeypatch):
    from league_lab_api import research as R
    al = pd.DataFrame([{"gsis_id": ACHANE, "player_name": "De'Von Achane", "direction": "up"},
                       {"gsis_id": HEALTHY, "player_name": "B", "direction": "up"}])
    monkeypatch.setattr(R, "missing_relations", lambda names: [])
    monkeypatch.setattr(R, "query", lambda sql, params=None: al.copy())
    monkeypatch.setattr(LG, "blocks", lambda ids, season=None, wk=None: {ACHANE: _block("IR", "knee - acl")})
    out = R.role_alerts(None, 2026)
    assert list(out["gsis_id"]) == [HEALTHY]


def test_the_cards_chart_is_gated_like_its_head(monkeypatch):
    from league_lab_api import ratings as RT
    rows = pd.DataFrame([{"week": w, "proj_points": 11.4, "p10": 4.0, "p25": 7.0, "p75": 15.0, "p90": 19.0,
                          "frozen_source": "kickoff" if w < 5 else None} for w in (4, 5)])
    monkeypatch.setattr(RT, "check_league", lambda league: None)
    monkeypatch.setattr(RT, "missing_relations", lambda names: [])
    monkeypatch.setattr(RT, "query", lambda sql, params=None: rows.copy())
    monkeypatch.setattr(RT.refleague, "is_reference", lambda league: False)
    monkeypatch.setattr(LG, "blocks", lambda ids, season=None, wk=None: {ACHANE: _block("IR", "knee - acl")})
    out = RT.player_projections(ACHANE, "1389709692405551104", 2026, 5)
    by = {w["week"]: w for w in out["weeks"]}
    assert by[5]["proj_points"] == 0.0 and by[5]["p90"] == 0.0 and by[5]["sits"] == "IR (knee - acl) · Sleeper, Sep 28"
    assert by[4]["proj_points"] == 11.4 and "sits" not in by[4]            # a played week is the record: untouched
    monkeypatch.setattr(LG, "blocks", lambda ids, season=None, wk=None: {})
    assert {w["week"]: w["proj_points"] for w in RT.player_projections(ACHANE, "1389709692405551104", 2026, 5)["weeks"]}[5] == 11.4


def test_the_team_qb_unit_asks_the_gate():
    import inspect

    from league_lab import anyleague as A
    src = inspect.getsource(A.unit_lines)
    assert "isin(UNIT_SKIP_STATUS)" not in src and "report_block" in src
    assert [AG.sits(AG.report_block(s)) for s in ("Out", "Doubtful", "Questionable", None)] == [True, True, False, False]


def test_waiver_views_ask_league_gate_not_the_older_overlay():
    import inspect

    from league_lab_api import decisions as D
    src = inspect.getsource(D.waiver_views)
    assert "availability.cannot_play(gs)" not in src and "LG.blocks" in src
