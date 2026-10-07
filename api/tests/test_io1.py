"""IO-1 (Wave I-O): the context record on the site — ``context_record.summary()`` with and without its table (the live
site has none until the nightly: rule 10), ``GET /api/context/record`` and its bucket, DFS's words from the record, the
corner chip's graded effect, the weather from ``analytics.mart_game_weather`` with and without the relation."""

from __future__ import annotations

import pandas as pd
import pytest
from league_lab import memo

from .conftest import needs_db

GRADE_ROWS = [
    {"kind": "summary", "grp": "corner", "n": 2190, "words": "Graded on 2025 (Half PPR): no measurable effect either way."},
    {"kind": "summary", "grp": "worth", "n": 38,
     "words": "Rebuilt for 2025 with the cornerback counting (the rule until this week), listed players beat their projection in 15 of 38 games."},
    {"kind": "corner", "grp": "likely/shutdown", "corner_certainty": "likely", "corner_tier": "shutdown", "n": 99,
     "vs_rest": -0.39, "vs_rest_lo": -1.39, "vs_rest_hi": 0.72, "words": "Graded: no measurable effect (−0.4 points …)."},
    {"kind": "corner", "grp": "likely/target", "corner_certainty": "likely", "corner_tier": "target", "n": 79,
     "vs_rest": 1.5, "vs_rest_lo": 0.2, "vs_rest_hi": 2.9, "words": "Graded: measurably above (+1.5 points …)."},
    {"kind": "summary", "grp": "worth_off", "n": 37,
     "words": "We tried a \"Worth a look\" list and graded it on 2025: it listed a receiver 37 times (in 29 games), and they finished 0.7 points better than everyone else against their projection (−1.1 to +2.7) — not distinguishable from chance. It is off until a rule earns its place in the record; the context chips stay beside each player."},
    {"kind": "worth", "grp": "listed", "n": 0, "words": None},
]


@pytest.fixture
def rec(monkeypatch):
    """context_record's two reads faked: ``state["exists"]`` (the table), ``state["rows"]`` (its rows), ``state["boom"]``."""
    from league_lab_api import context_record as CR
    state = {"exists": True, "rows": GRADE_ROWS, "boom": False}

    def fake_query(sql, params=(), ttl=None):
        if state["boom"]:
            raise RuntimeError("the pool is closed")
        if sql == CR.EXISTS_SQL:
            return pd.DataFrame([{"ok": state["exists"]}])
        if sql == CR.GRADE_SQL:
            return pd.DataFrame(state["rows"])
        raise AssertionError(sql)
    monkeypatch.setattr(CR, "query", fake_query)
    CR.clear()
    yield state
    CR.clear()


def test_summary_without_the_table_is_quiet(rec):
    from league_lab_api import context_record as CR
    rec["exists"] = False
    s = CR.summary()
    assert s["corner"]["graded"] is False and s["corner"]["words"] is None and s["corner"]["n"] == 0
    assert s["worth"] == {"graded": False, "n": 0, "words": None, "line": None}
    CR.clear()
    rec["boom"] = True                                     # any failure: the same quiet answer, never an exception
    assert CR.summary()["worth"]["graded"] is False
    CR.clear()
    rec["boom"], rec["exists"], rec["rows"] = False, True, []
    assert CR.summary()["corner"]["graded"] is False     # the table exists but is empty


def test_summary_with_the_record(rec):
    from league_lab_api import context_record as CR
    s = CR.summary()
    assert s["corner"]["graded"] is True and s["corner"]["n"] == 2190 and s["corner"]["words"].startswith("Graded on 2025")
    assert s["worth"]["graded"] is True and s["worth"]["n"] == 38
    assert s["worth"]["line"].startswith("We tried a \"Worth a look\" list") and "37 times (in 29 games)" in s["worth"]["line"]
    t = s["corner"]["tiers"]
    assert t["likely/shutdown"]["effect"] == "none" and t["likely/target"]["effect"] == "measured"
    assert CR.corner_grade("likely", "shutdown")["n"] == 99 and CR.corner_grade(None, "shutdown") is None
    s["corner"]["words"] = "changed"                        # a copy: the cache is not the caller's to change
    assert CR.summary()["corner"]["words"] != "changed"


def test_the_route_and_its_bucket(client, rec):
    from league_lab_api import ratelimit
    assert ratelimit.bucket_for("GET", "/api/context/record") == "read"
    r = client.get("/api/context/record")
    assert r.status_code == 200
    assert set(r.json()) == {"corner", "worth"} and r.json()["worth"]["graded"] is True
    rec["exists"] = False
    from league_lab_api import context_record as CR
    CR.clear()
    b = client.get("/api/context/record").json()
    assert b["corner"]["graded"] is False and b["worth"]["words"] is None


# ------------------------------------------------------------------------------------------------ DFS
def _fresh():
    for name in ("dfs", "dfs_context"):
        memo.BUDGET.regions[name].clear()


def _fake_matchups(monkeypatch, *, cb_tone="difficult", certainty="likely"):
    import sys
    import types

    import league_lab_api

    def matchup_context(season, week, gsis_ids=None):
        return {g: {"opponent": "KC", "home": True,
                    "defense": {"tone": "favorable", "tough_rank": 28, "n_ranked": 32, "words": "KC give up the 5th-most."},
                    "cb": {"tone": cb_tone, "certainty": certainty, "corner": "J. Doe", "corner_rank": 3,
                           "shutdown": cb_tone == "difficult", "words": "J. Doe (a shutdown corner, #3 of 64) is likely across from him"},
                    "tone": "neutral", "words": "x"} for g in (gsis_ids or [])}
    fake = types.ModuleType("league_lab_api.matchup_board")
    fake.matchup_context = matchup_context
    monkeypatch.setitem(sys.modules, "league_lab_api.matchup_board", fake)
    monkeypatch.setattr(league_lab_api, "matchup_board", fake, raising=False)


@needs_db
def test_dfs_words_and_the_corner_chip_with_the_record(client, rec, monkeypatch):
    _fake_matchups(monkeypatch)
    _fresh()
    b = client.get("/api/dfs/projections", params={"site": "dk", "week": 5, "limit": 1000}).json()
    m = b["context_meta"]
    # the fix round: "Worth a look" is off the screen; the record's one line says why, every number from the grade
    assert m["worth_line"].startswith("We tried a \"Worth a look\" list") and "worth_record" not in m
    assert m["words"] == "Context, not a forecast: these signals sit beside the projection and do not change it."
    assert m["corner_record"].startswith("Graded on 2025") and b["worth_a_look"] == {}
    corner = [s for p in b["players"] for s in p["context"] if s["signal"] == "corner"]
    # a likely shutdown corner: information only (no tone, so no colour and nothing sorts or filters on it), its quarter
    # for the words, its row of the grade
    assert corner and all(s["tone"] is None and s["quarter"] == "shutdown" and s["graded_effect"] == "none"
                          and s["graded"].startswith("Graded: no measurable effect") for s in corner)


@needs_db
def test_dfs_without_the_record_keeps_todays_words(client, rec, monkeypatch):
    _fake_matchups(monkeypatch)
    rec["exists"] = False
    _fresh()
    b = client.get("/api/dfs/projections", params={"site": "dk", "week": 5, "limit": 1000}).json()
    m = b["context_meta"]
    assert m["worth_line"] is None and m["corner_record"] is None          # no line at all without the record
    assert m["words"] == "Context, not a forecast: these signals sit beside the projection and do not change it."
    corner = [s for p in b["players"] for s in p["context"] if s["signal"] == "corner"]
    assert corner and not any("graded" in s for s in corner) and all(s["tone"] is None for s in corner)


def test_corner_quarter_never_needs_a_tone():
    from league_lab_api import dfs as api_dfs
    q = api_dfs.corner_quarter
    assert q({"certainty": "likely", "corner": "A", "shutdown": True, "tone": None}) == "shutdown"
    assert q({"certainty": "likely", "corner": "A", "tone": "favorable"}) == "target"
    # the matchup board's own tone may stop carrying the corner: the call's words still name the quarter
    assert q({"certainty": "likely", "corner": "A", "tone": None, "corner_rank": 60,
              "words": "A (easy to throw on, #60 of 64) is likely across from him"}) == "target"
    assert q({"certainty": "likely", "corner": "A", "tone": None, "corner_rank": None, "words": "A (unranked) is …"}) == "unranked"
    assert q({"certainty": "unclear", "corner": "A", "tone": "favorable"}) is None and q(None) is None


WX_ROWS = [{"game_id": "2026_05_CHI_GB", "wx_source": "forecast", "wx_dome": 0, "wx_wind_mph": 20.27, "wx_precip_in": 0.0,
            "wx_temp_f": 78.9, "wx_snow": 0, "forecast_at": "2026-10-05T12:01:14Z"}]


@needs_db
def test_weather_with_and_without_the_relation(client, monkeypatch):
    from league_lab_api import dfs as api_dfs
    real_query = api_dfs.query

    def query(sql, params=(), **kw):
        if sql == api_dfs.WX_SQL:
            return pd.DataFrame(WX_ROWS)
        return real_query(sql, params, **kw)
    monkeypatch.setattr(api_dfs, "query", query)
    # without the relation (the live site until the nightly): no weather, no error
    monkeypatch.setattr(api_dfs, "missing_relations", lambda names: list(names))
    _fresh()
    r = client.get("/api/dfs/projections", params={"site": "dk", "week": 5, "limit": 1000})
    assert r.status_code == 200
    b = r.json()
    assert b["context_meta"]["forecast"] is False
    assert not [s for p in b["players"] for s in p["context"] if s["signal"] == "weather"]
    # with it: Green Bay's 20 mph wind on both teams' passers and receivers, never in the projection
    monkeypatch.setattr(api_dfs, "missing_relations", lambda names: [])
    _fresh()
    b = client.get("/api/dfs/projections", params={"site": "dk", "week": 5, "limit": 1000}).json()
    assert b["context_meta"]["forecast"] is True
    wx = [(p["team"], p["position"], s) for p in b["players"] for s in p["context"] if s["signal"] == "weather"]
    assert wx and {t for t, _p, _s in wx} <= {"GB", "CHI"}
    assert all(s["words"] == "Forecast at kickoff (outdoors): wind 20 mph." and not s["in_projection"]
               and s["projection_words"] == "Not in the projection" for _t, _p, s in wx)
    assert all(s["tone"] == ("difficult" if p in ("QB", "WR", "TE") else None) for _t, p, s in wx)
    _fresh()


@needs_db
def test_weather_mart_failure_is_quiet(client, monkeypatch):
    from league_lab_api import dfs as api_dfs

    def boom(names):
        raise RuntimeError("no catalog")
    monkeypatch.setattr(api_dfs, "missing_relations", boom)
    _fresh()
    r = client.get("/api/dfs/projections", params={"site": "dk", "week": 5, "limit": 50})
    assert r.status_code == 200 and r.json()["context_meta"]["forecast"] is False
    _fresh()
