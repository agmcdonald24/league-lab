"""IS-2 (Wave I-S): the src readers inside a league ask availability_gate.sits — never the mart's injury_status or
nflverse's report_status. Each test has a player whose old field says nothing and whose block says IR (he must be left
out, with the reason), and one whose old field says "Out" with no word from the one definition (he is not). No
database: hand-built inputs."""

import json
from datetime import UTC, datetime

import pandas as pd
from league_lab import anyleague as A
from league_lab import availability_gate as AG
from league_lab import league_status as LS
from league_lab import lineup as LU

ACHANE, HEALTHY = "00-0039040", "00-0000003"


def _block(code, note=None, as_of="2026-09-28T15:00:00Z"):
    return AG.classify(AG.entry(code, "Sleeper", as_of=as_of, note=note))


def test_note_and_sits_are_the_gates_and_tolerate_a_missing_block():
    ir = _block("IR", "knee - acl")
    n = LS.note(ir)
    assert n == {"status": "IR", "why": "IR (knee - acl) · Sleeper, Sep 28", "sits": True, "out_indefinitely": True,
                 "words": "On injured reserve: no return date, so no rest-of-season value."}
    for nothing in (None, float("nan"), {}, "IR"):
        assert LS.sits(nothing) is False and LS.note(nothing) is None and LS.out_indefinitely(nothing) is False
    assert LS.sits(_block("QUESTIONABLE")) is False and LS.sits(_block("OUT")) is True


def test_record_block_reads_the_stored_record():
    rec = AG.record_text(_block("IR", "knee - acl"))
    b = LS.record_block(rec)
    assert LS.sits(b) and b["why"] == "IR (knee - acl) · Sleeper, Sep 28"
    assert LS.record_block(None) is None and LS.record_block("not json") is None
    assert LS.record_block(json.dumps({"code": "MADE_UP"})) is None


def test_directory_block_is_classify_over_sleepers_entry():
    b = LS.directory_block({"injury_status": "IR", "news_updated": 1759071600000, "injury_body_part": "Knee - ACL", "team": "MIA"})
    assert LS.sits(b) and b["status"] == "IR" and b["why"].startswith("IR (knee - acl) · Sleeper")
    assert LS.directory_block({"injury_status": None, "status": "Active", "team": "MIA"}) is None


def _fa_query(nfl_injury):
    def query(sql, params=None):
        if "player_id_map" in sql:
            return pd.DataFrame({"sleeper_id": ["9226", "3"], "gsis_id": [ACHANE, HEALTHY]})
        if "mart_player_availability" in sql:
            return pd.DataFrame({"sleeper_id": ["9226", "3"], "gsis_id": [ACHANE, HEALTHY],
                                 "player_name": ["De'Von Achane", "Last Week Out"], "position": ["RB", "RB"],
                                 "nfl_team": ["MIA", "NYJ"], "roster_status": ["ACT", "ACT"],
                                 "injury_status": nfl_injury, "games_played": [4, 4]})
        return pd.DataFrame()
    return query


DIRECTORY = {"9226": {"position": "RB", "fantasy_positions": ["RB"], "team": "MIA", "status": "Inactive",
                      "injury_status": "IR", "news_updated": 1759071600000, "injury_body_part": "Knee - ACL",
                      "full_name": "De'Von Achane"},
             "3": {"position": "RB", "fantasy_positions": ["RB"], "team": "NYJ", "status": "Active",
                   "injury_status": None, "full_name": "Last Week Out"}}


def test_on_demand_free_agents_leave_out_who_sits_by_the_directory():
    # the mart's report row says nothing about Achane and "Out" (last week's) about the other
    fa = A.free_agents(_fa_query([None, "Out"]), "L", [], DIRECTORY, ["RB"])
    assert list(fa["gsis_id"]) == [HEALTHY]
    assert fa.iloc[0]["injury_status"] is None


def test_on_demand_free_agents_take_the_request_time_blocks_when_given():
    fa = A.free_agents(_fa_query([None, None]), "L", [], {**DIRECTORY, "9226": {**DIRECTORY["9226"], "injury_status": None,
                                                                              "status": "Active"}},
                       ["RB"], blocks={ACHANE: _block("IR", "knee - acl")})
    assert list(fa["gsis_id"]) == [HEALTHY]


def _inputs(record, report_status=None):
    proj = {("L", 5, ACHANE): {"proj_points": 11.42, "team": "MIA", "report_status": report_status, "roster_status": "ACT",
                               "availability": record}}
    return LU.LineupInputs(season=2026, leagues=[], weeks={"L": [5]}, proj=proj, weekly={}, current={},
                           sleeper={"9226": {"position": "RB", "fantasy_positions": ["RB"], "team": "MIA"}},
                           k_ppg={}, games={5: {"MIA": datetime(2026, 10, 11, 17, tzinfo=UTC)}})


def _row():
    return {"sleeper_player_id": "9226", "gsis_id": ACHANE, "position": "RB", "nfl_team": "MIA"}


def test_lineup_sits_a_player_the_stored_record_leaves_out():
    rec = AG.record_text(_block("IR", "knee - acl"))
    p = LU._proposed_player(_inputs(rec), "L", 5, _row(), None, {}, True, datetime(2026, 10, 8, tzinfo=UTC))
    assert p.playable is False and p.reason == "IR" and p.status == "IR"


def test_lineup_no_longer_sits_on_nflverse_report_status():
    p = LU._proposed_player(_inputs(None, "Doubtful"), "L", 5, _row(), None, {}, True, datetime(2026, 10, 8, tzinfo=UTC))
    assert p.playable is True and p.status == "Doubtful"           # flagged, as the Rankings flag him


def test_replacement_sql_reads_the_record_not_the_report():
    from league_lab import trades as T
    assert "injury_status is distinct from" not in T.REPLACEMENT_SQL and "'availability'" in T.REPLACEMENT_SQL
