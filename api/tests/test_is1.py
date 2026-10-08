"""IS-1 (Wave I-S): a status that rarely plays is not ranked as if it will. Breece Hall, "Doubtful (quadriceps) ·
Sleeper, Oct 7", was RB19 with a full projection on the live Rankings. Each route with a hand-built snapshot: Rankings
(week: not ranked, not tiered, under "Unlikely to play"; season: kept), "Who should I start?" ("He is doubtful"), the
board, the Not-playing order, the overlay's sets as views of the gate."""

from __future__ import annotations

from datetime import UTC, datetime

from league_lab import availability_gate as AG

from league_lab_api import availability as AV
from league_lab_api import rankings_api as RK

from .conftest import needs_db

ROUTE, START = "/api/rankings", "/api/rankings/start"
OCT7 = datetime(2026, 10, 7, 16, 0, tzinfo=UTC)
SEP28 = datetime(2026, 9, 28, 14, 0, tzinfo=UTC)


def _st(code, source="Sleeper", when=OCT7, note=None) -> dict:
    return AG.classify(AG.entry(code, source, as_of=when, note=note))


def _snapshot(monkeypatch, by_gsis: dict[str, dict]) -> None:
    def fake(gsis_ids, season, week, **kw):
        want = None if gsis_ids is None else set(gsis_ids)
        return {g: {"gsis_id": g, **s} for g, s in by_gsis.items() if want is None or g in want}
    monkeypatch.setattr(AV, "statuses", fake)
    monkeypatch.setattr(AV, "stored_status", lambda season, week: {})
    monkeypatch.setattr(AV, "season_ppg", lambda ids, season: {})
    RK.clear()


def test_the_overlays_sets_are_views_of_the_gate():
    assert AV.CANNOT_PLAY is AG.SITS_CODES and AV.NOT_IN_TRENDS is AG.CANNOT_PLAY and AV.FLAGGED is AG.FLAGGED
    assert AV.CANNOT_PLAY - {"NO_TEAM"} == {"OUT", "DOUBTFUL", "IR", "PUP", "NFI", "SUS", "INACTIVE"}       # as before
    assert AV.NOT_IN_TRENDS - {"NO_TEAM"} == {"OUT", "IR", "PUP", "NFI", "SUS", "INACTIVE"}                 # as before
    assert AV.sits is AG.sits
    # a lineup benches whom the lists leave out: every code the overlay produces sits() exactly when the overlay says so
    for code in ("OUT", "DOUBTFUL", "QUESTIONABLE", "IR", "PUP", "NFI", "SUS", "INACTIVE", "ACTIVE"):
        assert (code in AV.CANNOT_PLAY) == AG.sits(_st(code)), code


def test_the_not_playing_group_leads_with_who_a_visitor_looks_for():
    rows = [AV.not_playing_row({"key": k, "gsis_id": k, "player_name": n}, s) for k, n, s in (
        ("a", "Aaron Depth", _st("IR")), ("b", "Bijan Star", _st("IR")), ("c", "Breece Hall", _st("DOUBTFUL")),
        ("d", "Dee Depth", _st("DOUBTFUL")))]
    got = AV.order_not_playing(rows, {"a": 0.0, "b": 0.0, "c": 11.8, "d": 2.0}, None)
    assert [r["key"] for r in got][2:] == ["c", "d"]                     # Out first, then Unlikely to play
    assert {r["group"] for r in got[:2]} == {"out"} and got[2]["group_label"] == "Unlikely to play"
    assert got[2]["p_play"] == 0.01


def test_the_order_falls_back_to_points_per_game(monkeypatch):
    monkeypatch.setattr(AV, "season_ppg", lambda ids, season: {"a": 3.0, "b": 19.0})
    rows = [AV.not_playing_row({"key": k, "gsis_id": k, "player_name": n}, _st("IR")) for k, n in (("a", "A"), ("b", "B"))]
    assert [r["key"] for r in AV.order_not_playing(rows, {"a": 0.0, "b": 0.0}, 2026)] == ["b", "a"]


def _top(client, view="week", n=12) -> list[dict]:
    return client.get(ROUTE, params={"league": "ref:half", "position": "RB", "view": view, "limit": 200}).json()["rows"][:n]


@needs_db
def test_rankings_a_doubtful_player_is_not_ranked_this_week_and_keeps_his_season(client, monkeypatch):
    _snapshot(monkeypatch, {})
    top = _top(client)
    hall, q, ir = top[2], top[3], top[0]
    snap = {hall["gsis_id"]: _st("DOUBTFUL", note="quadriceps"), q["gsis_id"]: _st("QUESTIONABLE", "ESPN"),
            ir["gsis_id"]: _st("IR", when=SEP28, note="knee - acl")}
    _snapshot(monkeypatch, snap)
    d = client.get(ROUTE, params={"league": "ref:half", "position": "RB", "limit": 200}).json()
    ids = [r["gsis_id"] for r in d["rows"]]
    assert hall["gsis_id"] not in ids and ir["gsis_id"] not in ids          # neither ranked nor tiered
    assert q["gsis_id"] in ids                                              # Questionable: ranked, flagged
    qrow = next(r for r in d["rows"] if r["gsis_id"] == q["gsis_id"])
    assert qrow["report_status"] == "Questionable" and qrow["availability"]["p_play"] == 0.67
    assert "67 in 100" in qrow["availability"]["words"]
    np_ = {r["gsis_id"]: r for r in d["not_playing"]}
    assert np_[hall["gsis_id"]]["group"] == "unlikely" and np_[ir["gsis_id"]]["group"] == "out"
    assert np_[hall["gsis_id"]]["words"] == ("Doubtful: players listed doubtful have played about 1 in 100 times; not "
                                             "ranked this week.")
    assert [r["group"] for r in d["not_playing"]] == ["out", "unlikely"]
    assert d["rows"][0]["tier"] == 1 and [r["rank"] for r in d["rows"]] == list(range(1, len(ids) + 1))
    # the season: a doubtful player keeps his rest of season (not out indefinitely); the IR one leaves it
    s = client.get(ROUTE, params={"league": "ref:half", "position": "RB", "view": "season", "limit": 200}).json()
    sid = {r["gsis_id"] for r in s["rows"]}
    assert hall["gsis_id"] in sid and ir["gsis_id"] not in sid


@needs_db
def test_who_should_i_start_says_he_is_doubtful(client, monkeypatch):
    _snapshot(monkeypatch, {})
    top = _top(client)
    a, b = top[2], top[6]
    _snapshot(monkeypatch, {a["gsis_id"]: _st("DOUBTFUL", note="quadriceps")})
    d = client.get(START, params={"league": "ref:half", "ids": f"{a['gsis_id']},{b['gsis_id']}"}).json()
    assert d["answer"]["verdict"] == "out" and d["answer"]["pick"] == b["gsis_id"]
    assert " is doubtful — players listed doubtful have played about 1 in 100 times (Doubtful (quadriceps) · Sleeper, Oct 7)." \
        in d["answer"]["words"]
    assert d["out"][0]["group"] == "unlikely"


@needs_db
def test_the_board_leaves_a_doubtful_player_out(client, monkeypatch):
    _snapshot(monkeypatch, {})
    rows = client.get("/api/matchups/board", params={"league": "ref:half", "position": "RB", "limit": 20}).json()["rows"]
    g = rows[1]["gsis_id"]
    _snapshot(monkeypatch, {g: _st("DOUBTFUL")})
    from league_lab_api import matchup_board as MB
    MB._cache.clear()
    b = client.get("/api/matchups/board", params={"league": "ref:half", "position": "RB", "limit": 100}).json()
    assert g not in {r["gsis_id"] for r in b["rows"]} and b["not_playing"][0]["gsis_id"] == g
