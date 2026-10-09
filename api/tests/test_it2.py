"""IT-2 (Wave I-T): on a copy with neither live source, a player Out on this week's own injury report is not ranked
(the pooler check's API on the fixtures ranked Breece Hall #18 while "Out"); a Questionable row says its rate."""

from __future__ import annotations

from league_lab import availability_gate as AG

from league_lab_api import availability as AV
from league_lab_api import rankings_api as RK

from .conftest import needs_db

ROUTE = "/api/rankings"


def test_statuses_take_the_weeks_own_report_when_nothing_else_speaks():
    got = AV.statuses(["hall", "q"], 2026, 5, overlay=False, stored={},
                      report={"hall": AG.report_entry("Out"), "q": AG.report_entry("Questionable")})
    assert AV.sits(got["hall"]) and got["hall"]["why"] == "Out · NFL injury report"
    assert not AV.sits(got["q"]) and got["q"]["status"] == "Questionable"


@needs_db
def test_rankings_leave_out_a_player_out_on_this_weeks_report_with_the_overlay_off(client, monkeypatch):
    monkeypatch.setattr(AV, "stored_status", lambda season, week: {})
    monkeypatch.setattr(AV, "week_report", lambda season, week: {})
    monkeypatch.setattr(AV, "enabled", lambda: False)
    RK.clear()
    rows = client.get(ROUTE, params={"league": "ref:half", "position": "RB", "limit": 200}).json()["rows"]
    hall, q = rows[3], rows[5]
    monkeypatch.setattr(AV, "week_report", lambda season, week: {hall["gsis_id"]: AG.report_entry("Out"),
                                                                  q["gsis_id"]: AG.report_entry("Questionable")})
    RK.clear()
    d = client.get(ROUTE, params={"league": "ref:half", "position": "RB", "limit": 200}).json()
    assert hall["gsis_id"] not in {r["gsis_id"] for r in d["rows"]}
    np_ = {r["gsis_id"]: r for r in d["not_playing"]}
    assert np_[hall["gsis_id"]]["why"] == "Out · NFL injury report" and np_[hall["gsis_id"]]["group"] == "out"
    qrow = next(r for r in d["rows"] if r["gsis_id"] == q["gsis_id"])
    assert qrow["availability"]["short"] == "Questionable: about 2 in 3 play" and qrow["availability"]["p_play"] == 0.64
