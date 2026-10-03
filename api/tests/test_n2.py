"""N2: PlayerWire's briefs first on the card's news line, ESPN's headlines fill the rest (league_lab_api/playerwire.py,
news.py; docs/PLAYERWIRE.md).

Fixtures: api/tests/fixtures/playerwire/briefs.json (rows of playerwire.briefs / brief_players as the Mac's sync writes
them, the analytics.player_id_map rows they map through, as_of 2026-10-03 19:00 UTC) and N1's ESPN fixtures (Justin
Jefferson's recorded answer). No test reads a database or the network: the database path is driven through a
stand-in for `query`.
"""

from __future__ import annotations

import json
import logging
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest
from league_lab import news_feed as NF

from league_lab_api import news
from league_lab_api import playerwire as PW
from league_lab_api.db import DataNotReady

from .conftest import SCRUBS, needs_db

FIX = Path(__file__).with_name("fixtures")
PW_FIX = FIX / "playerwire" / "briefs.json"
ESPN = FIX / "espn"
JEFFERSON, ADDISON, OTHER = "00-0036322", "00-0038994", "00-0099999"
JJ_ESPN = "4262921"
AS_OF = datetime(2026, 10, 3, 19, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    for k in (NF.SWITCH_ENV, PW.SWITCH_ENV, PW.FIXTURES_ENV):
        monkeypatch.delenv(k, raising=False)
    news.reset()
    yield
    news.reset()


def _pw(tmp_path, monkeypatch, keep: set[str] | None = None, **edit) -> Path:
    """The PlayerWire fixture (only the briefs in ``keep`` when given), pointed at by LEAGUE_LAB_PLAYERWIRE_FIXTURES."""
    fx = json.loads(PW_FIX.read_text())
    if keep is not None:
        fx["briefs"] = [b for b in fx["briefs"] if b["brief_id"] in keep]
        fx["brief_players"] = [p for p in fx["brief_players"] if p["brief_id"] in keep]
    fx.update(edit)
    p = tmp_path / "pw.json"
    p.write_text(json.dumps(fx))
    monkeypatch.setenv(PW.FIXTURES_ENV, str(p))
    PW.reset()
    return p


def _espn(tmp_path, monkeypatch) -> Path:
    fx = tmp_path / "espn"
    fx.mkdir()
    for f in ("db_playerids_espn.csv", "injuries.json", f"news_{JJ_ESPN}.json"):
        shutil.copy(ESPN / f, fx)
    monkeypatch.setenv(NF.FIXTURES_ENV, str(fx))
    NF.reset()
    return fx


# ------------------------------------------------------------------------------------------------ the order and the fill
def test_playerwire_first_newest_first_and_espn_not_asked_when_three(tmp_path, monkeypatch):
    _pw(tmp_path, monkeypatch)
    _espn(tmp_path, monkeypatch)
    out = news.for_card(JEFFERSON)
    assert [n["headline"] for n in out] == ["Addison in line for more targets with Jefferson out",
                                            "Jefferson (ankle) ruled out for Sunday", "Jefferson did not practice Friday"]
    assert [n["date"] for n in out] == ["2026-10-03T16:00:00Z", "2026-10-03T14:10:00Z", "2026-10-02T21:00:00Z"]
    assert all(n["kind"] == "playerwire" for n in out)
    assert [n["related"] for n in out] == [True, False, False]          # the Addison brief names him as related
    assert [n["verification"] for n in out] == ["reported", "official", "corroborated"]
    assert out[1]["source"] == "Minnesota Vikings via PlayerWire" and out[0]["source"] == "Star Tribune via PlayerWire"
    assert out[1]["url"] == "https://www.vikings.com/news/injury-report-week-5"
    assert out[1]["summary"].startswith("Justin Jefferson (ankle) has been ruled out for Sunday's game")
    # N1's four keys on every item, the rest new keys only
    assert all({"headline", "date", "source", "url"} <= set(n) for n in out)
    assert set(out[0]) == {"headline", "date", "source", "url", "summary", "kind", "verification", "related"}
    assert NF.feed().calls == 0                                            # three briefs: ESPN never asked


def test_espn_fills_the_slots_playerwire_leaves(tmp_path, monkeypatch):
    _pw(tmp_path, monkeypatch, keep={"pw_jj_out"})
    _espn(tmp_path, monkeypatch)
    out = news.for_card(JEFFERSON)
    assert [n["kind"] for n in out] == ["playerwire", "espn", "espn"]
    assert out[0]["headline"] == "Jefferson (ankle) ruled out for Sunday"
    # ESPN's two newest, unchanged from N1 (+ kind), no summary
    assert [n["date"] for n in out[1:]] == ["2026-10-03T13:33:00Z", "2026-10-03T00:59:53Z"]
    assert out[1]["source"] == "RotoWire via ESPN" and set(out[1]) == {"headline", "date", "source", "url", "kind"}
    assert NF.feed().calls == 1


def test_no_playerwire_brief_is_espn_as_before(tmp_path, monkeypatch):
    _pw(tmp_path, monkeypatch, keep=set())
    _espn(tmp_path, monkeypatch)
    out = news.for_card(JEFFERSON)
    assert [n["kind"] for n in out] == ["espn"] * 3
    assert [n["date"] for n in out] == ["2026-10-03T13:33:00Z", "2026-10-03T00:59:53Z", "2026-10-02T18:35:16Z"]


def test_the_14_day_cutoff(tmp_path, monkeypatch):
    _pw(tmp_path, monkeypatch, keep={"pw_jj_13d", "pw_jj_old"})
    out = PW.for_card(JEFFERSON)
    assert [n["headline"] for n in out] == ["Jefferson limited in Wednesday practice"]      # 13 days in, 15 days out
    # a day later the 13-day brief is 14 days and an hour old: gone
    assert PW.for_card(JEFFERSON, now=datetime(2026, 10, 4, 21, 0, tzinfo=UTC)) == []
    # dated more than a day ahead of the clock: a bad date, left out
    assert PW.for_card(JEFFERSON, now=datetime(2026, 9, 16, 0, 0, tzinfo=UTC)) == []


def test_withdrawn_briefs_are_never_shown(tmp_path, monkeypatch):
    _pw(tmp_path, monkeypatch, keep={"pw_jj_withdrawn"})
    assert PW.for_card(JEFFERSON) == []
    # even a withdrawn row that somehow kept its text
    p = _pw(tmp_path, monkeypatch, keep={"pw_jj_out"})
    fx = json.loads(p.read_text())
    fx["briefs"][0]["deleted"] = True
    p.write_text(json.dumps(fx))
    PW.reset()
    assert PW.for_card(JEFFERSON) == []


def test_unmapped_and_conflicting_briefs_are_hidden_but_counted(tmp_path, monkeypatch):
    _pw(tmp_path, monkeypatch)
    everyone = [PW.for_card(g) for g in (JEFFERSON, ADDISON, OTHER)]
    shown = {n["headline"] for items in everyone for n in items}
    assert "Practice-squad receiver signed" not in shown                  # no id League Lab knows
    assert "A brief whose two ids disagree" not in shown                   # Sleeper id says Jefferson, gsis id says another
    assert PW.for_card(OTHER) == []
    # by gsis alone when the brief has no Sleeper id
    assert [n["headline"] for n in PW.for_card(ADDISON)] == ["Addison in line for more targets with Jefferson out",
                                                            "Addison: full practice Thursday"]
    st = PW.info()
    assert st == {"enabled": True, "source": "fixtures", "rows": 8, "withdrawn": 1,
                  "newest_published_at": "2026-10-03T18:00:00Z", "unmapped": 2,
                  "last_sync_at": "2026-10-03T18:45:00Z", "last_error": None}


def test_the_identity_rule():
    assert PW.resolve("6794", None, JEFFERSON, None) == JEFFERSON
    assert PW.resolve("6794", JEFFERSON, JEFFERSON, JEFFERSON) == JEFFERSON
    assert PW.resolve("6794", OTHER, JEFFERSON, OTHER) is None             # the two ids disagree
    assert PW.resolve(None, ADDISON, None, ADDISON) == ADDISON              # gsis only
    assert PW.resolve("404", ADDISON, None, ADDISON) == ADDISON             # an unmapped Sleeper id: the gsis id
    assert PW.resolve("404", None, None, None) is None


# ------------------------------------------------------------------------------------------------ the switches
def test_playerwire_off_is_espn_only(tmp_path, monkeypatch):
    _pw(tmp_path, monkeypatch)
    _espn(tmp_path, monkeypatch)
    monkeypatch.setenv(PW.SWITCH_ENV, "off")
    out = news.for_card(JEFFERSON)
    assert [n["kind"] for n in out] == ["espn"] * 3
    assert news.info()["playerwire"] == {"enabled": False}


def test_news_off_is_no_line_at_all(tmp_path, monkeypatch):
    _pw(tmp_path, monkeypatch)
    _espn(tmp_path, monkeypatch)
    monkeypatch.setenv(NF.SWITCH_ENV, "off")
    assert news.for_card(JEFFERSON) == [] and news.info() == {"enabled": False}


def test_fixture_mode_without_playerwire_fixtures_never_reads_a_database(monkeypatch):
    # conftest puts every API test on the Sleeper fixtures; without LEAGUE_LAB_PLAYERWIRE_FIXTURES PlayerWire is off
    def boom(*_a, **_k):
        raise AssertionError("PlayerWire read a database in fixture mode")
    monkeypatch.setattr(PW, "query", boom)
    assert PW.enabled() is False and news.for_card(JEFFERSON) == [] and news.enabled() is False


def test_status_block(tmp_path, monkeypatch):
    _pw(tmp_path, monkeypatch)
    _espn(tmp_path, monkeypatch)
    st = news.info()
    assert st["enabled"] is True and st["mode"] == "fixtures"              # ESPN's N1 keys stay at the top level
    assert st["playerwire"]["rows"] == 8 and st["playerwire"]["unmapped"] == 2


# ------------------------------------------------------------------------------------------------ the database path
def _db_mode(monkeypatch):
    """Not in fixture mode (so PlayerWire reads `query`), with ESPN on its fixtures (never the network)."""
    from league_lab import anyleague as A
    monkeypatch.delenv(A.FIXTURES_ENV, raising=False)


def test_database_rows_go_through_the_same_rules(tmp_path, monkeypatch):
    _db_mode(monkeypatch)
    _espn(tmp_path, monkeypatch)
    calls: list[tuple] = []
    rows = pd.DataFrame([
        {"brief_id": "a", "version": 1, "status": "published", "deleted": False, "headline": "Own brief",
         "news": "Summary.", "verification_status": "official", "published_at": pd.Timestamp("2026-10-03T14:00:00Z"),
         "evidence_url": "https://www.vikings.com/x", "evidence_publisher": "Minnesota Vikings", "role": "primary",
         "sleeper_id": "6794", "gsis_id": None, "via_sleeper": JEFFERSON, "via_gsis": None},
        {"brief_id": "a", "version": 1, "status": "published", "deleted": False, "headline": "Own brief",
         "news": "Summary.", "verification_status": "official", "published_at": pd.Timestamp("2026-10-03T14:00:00Z"),
         "evidence_url": "https://www.vikings.com/x", "evidence_publisher": "Minnesota Vikings", "role": "related",
         "sleeper_id": "6794", "gsis_id": None, "via_sleeper": JEFFERSON, "via_gsis": None},
        {"brief_id": "c", "version": 1, "status": "published", "deleted": False, "headline": "Conflict",
         "news": None, "verification_status": "reported", "published_at": pd.Timestamp("2026-10-03T15:00:00Z"),
         "evidence_url": "https://x.example/c", "evidence_publisher": None, "role": "primary",
         "sleeper_id": "6794", "gsis_id": OTHER, "via_sleeper": JEFFERSON, "via_gsis": OTHER},
        {"brief_id": "h", "version": 1, "status": "published", "deleted": False, "headline": "Plain http",
         "news": None, "verification_status": "reported", "published_at": pd.Timestamp("2026-10-03T16:00:00Z"),
         "evidence_url": "http://x.example/h", "evidence_publisher": "X", "role": "primary",
         "sleeper_id": "6794", "gsis_id": None, "via_sleeper": JEFFERSON, "via_gsis": None},
    ])

    def fake_query(sql, params=(), *, ttl=None):
        calls.append((sql, params, ttl))
        return rows

    monkeypatch.setattr(PW, "query", fake_query)
    out = news.for_card(JEFFERSON)
    assert [n["kind"] for n in out] == ["playerwire", "espn", "espn"]
    assert out[0] == {"headline": "Own brief", "date": "2026-10-03T14:00:00Z", "source": "Minnesota Vikings via PlayerWire",
                      "url": "https://www.vikings.com/x", "summary": "Summary.", "kind": "playerwire",
                      "verification": "official", "related": False}             # one per brief, his own over a mention
    sql, params, ttl = calls[0]
    assert params == (JEFFERSON,) * 4 and ttl == PW.CACHE_TTL_S
    assert "analytics.player_id_map" in sql and "not b.deleted" in sql and "b.status = 'published'" in sql
    assert " name" not in sql.lower()                                          # rule 3: ids only


def test_a_missing_schema_is_espn_only_logged_once_then_a_pause(tmp_path, monkeypatch, caplog):
    _db_mode(monkeypatch)
    _espn(tmp_path, monkeypatch)
    n = {"calls": 0}

    def missing(*_a, **_k):
        n["calls"] += 1
        raise DataNotReady('relation "playerwire.briefs" does not exist')

    monkeypatch.setattr(PW, "query", missing)
    with caplog.at_level(logging.WARNING, logger="league_lab_api.playerwire"):
        first = news.for_card(JEFFERSON)
        second = news.for_card(JEFFERSON)
    assert [n_["kind"] for n_ in first] == ["espn"] * 3 and first == second
    assert n["calls"] == 1                                                      # the second card waits out the pause
    assert len([r for r in caplog.records if "PlayerWire briefs unavailable" in r.message]) == 1
    st = news.info()["playerwire"]
    assert st["enabled"] is True and st["available"] is False and "does not exist" in st["error"]
    # back: the next read after the pause works and the warning re-arms
    monkeypatch.setattr(PW, "_down_until", 0.0)
    monkeypatch.setattr(PW, "query", lambda *_a, **_k: pd.DataFrame())
    assert [n_["kind"] for n_ in news.for_card(JEFFERSON)] == ["espn"] * 3 and PW._warned is False


def test_database_status_counts(monkeypatch):
    _db_mode(monkeypatch)

    def fake_query(sql, params=(), *, ttl=None):
        if "sync_state" in sql:
            return pd.DataFrame([{"last_sync_at": pd.Timestamp("2026-10-03T18:45:00Z"), "last_error": None,
                                  "last_error_at": None, "high_watermark": "12"}])
        return pd.DataFrame([{"rows": 40, "withdrawn": 3, "newest_published_at": pd.Timestamp("2026-10-03T18:00:00Z"),
                              "unmapped": 2, "conflicting": 1}])

    monkeypatch.setattr(PW, "query", fake_query)
    assert PW.info() == {"enabled": True, "source": "database", "rows": 40, "withdrawn": 3,
                         "newest_published_at": "2026-10-03T18:00:00Z", "unmapped": 2, "conflicting": 1,
                         "last_sync_at": "2026-10-03T18:45:00Z", "last_error": None}


def test_the_hosted_audit_does_not_see_the_playerwire_schema():
    # the nightly's relation audit (scripts/hosted_relations.py) only knows analytics / analytics_seeds / ops / raw /
    # staging / intermediate: naming playerwire.* in the API never makes the nightly publish, drop or verify it
    import importlib.util
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location("hosted_relations", root / "scripts" / "hosted_relations.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert "playerwire" not in mod.SCHEMAS
    src = (root / "api" / "league_lab_api" / "playerwire.py").read_text()
    assert {m.group(0) for m in mod.QUALIFIED.finditer(src)} == {"analytics.player_id_map"}


@needs_db
def test_card_carries_playerwire_then_espn(client, tmp_path, monkeypatch):
    _pw(tmp_path, monkeypatch, keep={"pw_jj_out"})
    _espn(tmp_path, monkeypatch)
    d = client.get(f"/api/player/{JEFFERSON}", params={"league": SCRUBS}).json()
    assert [n["kind"] for n in d["news"]] == ["playerwire", "espn", "espn"]
    assert d["news"][0]["summary"].startswith("Justin Jefferson (ankle)") and d["news"][0]["verification"] == "official"
    st = client.get("/api/status").json()["news"]
    assert st["playerwire"]["source"] == "fixtures" and st["playerwire"]["rows"] == 1
