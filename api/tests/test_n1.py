"""Wave I-D, N1: the news line on the player card — ESPN's player news (league_lab.news_feed) -> `news` on
/api/player/{gsis}. Fixtures: api/tests/fixtures/espn/news_<espn_id>.json (ESPN's answers recorded through the browser
pane 2026-10-03, story bodies emptied): Justin Jefferson (4262921, news the day it was recorded) and James Conner
(3045147, nothing since 2026-08-30). A test never calls ESPN."""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
from league_lab import news_feed as NF
from league_lab.sleeper_client import TokenBucket

from league_lab_api import news

from .conftest import SCRUBS, needs_db

ESPN = Path(__file__).with_name("fixtures") / "espn"
JEFFERSON, JJ_ESPN = "00-0036322", "4262921"
CONNER_ESPN = "3045147"
RECORDED = datetime(2026, 10, 3, 18, 47, 20, tzinfo=UTC).timestamp()
HOUR = 3600.0


def _body(espn_id: str) -> dict:
    return json.loads((ESPN / f"news_{espn_id}.json").read_text())


@pytest.fixture(autouse=True)
def _fresh_news(monkeypatch):
    monkeypatch.delenv(NF.SWITCH_ENV, raising=False)
    news.reset()
    yield
    news.reset()


class Clock:
    def __init__(self, t: float) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


def _feed(tmp_path, clock, *, fetch=None, per_min: float = 60, game_day: bool = False, fixtures=None) -> NF.NewsFeed:
    calls: list[str] = []

    def spy(url: str):
        calls.append(url)
        if fetch is not None:
            return fetch(url)
        return _body(url.split("playerId=")[1].split("&")[0])

    f = NF.NewsFeed(fixtures=fixtures or "", wall=clock, fetch=spy, cache_root=tmp_path / "espn_news",
                    is_game_day=lambda _d: game_day, bucket=TokenBucket(per_min, clock=clock))
    f.calls_made = calls          # type: ignore[attr-defined]
    return f


# ------------------------------------------------------------------------------ the feed: what is kept
def test_parse_keeps_the_headline_date_source_and_link_only():
    items = NF.parse(_body(JJ_ESPN), JJ_ESPN)
    assert len(items) == 5
    assert [set(i) for i in items] == [{"headline", "date", "source", "url"}] * 5
    assert [i["date"] for i in items] == sorted((i["date"] for i in items), reverse=True)
    top = items[0]
    assert top["headline"].startswith("Jefferson (ankle) has been already been ruled out for Sunday's game against the Dolphins")
    assert top["date"] == "2026-10-03T13:33:00Z"
    # RotoWire's blurb: no web link in ESPN's answer -> his ESPN player page; named as RotoWire's
    assert top["source"] == "RotoWire via ESPN"
    assert top["url"] == "https://www.espn.com/nfl/player/_/id/4262921"
    story = items[1]          # ESPN's own story: its web page, https
    assert story["source"] == "ESPN"
    assert story["url"].startswith("https://www.espn.com/fantasy/football/story/_/page/FFSundayInactives-50077553/")
    # nothing of the body leaves the module
    assert "Updated inactives" not in json.dumps(items)


def test_fresh_is_at_most_three_newest_first_and_14_days():
    items = NF.parse(_body(JJ_ESPN), JJ_ESPN)
    at = datetime(2026, 10, 3, 19, 0, tzinfo=UTC)
    out = NF.fresh(items, at)
    assert len(out) == 3 and out[0]["date"] == "2026-10-03T13:33:00Z" and out[2]["date"] == "2026-10-02T18:35:16Z"
    # 15 days on: the newest is 14 days and 5 hours old -> nothing
    assert NF.fresh(items, datetime(2026, 10, 17, 19, 0, tzinfo=UTC)) == []
    # 14 days after the 2026-10-02 18:35 item: only the two newer ones are left
    assert [i["date"] for i in NF.fresh(items, datetime(2026, 10, 16, 18, 40, tzinfo=UTC))] == [
        "2026-10-03T13:33:00Z", "2026-10-03T00:59:53Z"]
    # Conner: nothing since 2026-08-30 -> no line on 2026-10-03
    assert NF.fresh(NF.parse(_body(CONNER_ESPN), CONNER_ESPN), at) == []


def test_unknown_athlete_and_bad_answers_are_no_news():
    assert NF.parse({"timestamp": "2026-10-03T18:47:11Z", "status": "success", "resultsCount": 0, "feed": []}, "1") == []
    assert NF.parse({"code": 404, "message": "not found"}, "1") == []
    assert NF.parse(None, "1") == []
    assert NF.item({"headline": "  ", "published": "2026-10-03T13:33:00Z"}, "1") is None
    assert NF.item({"headline": "x", "published": "soon"}, "1") is None
    # a link to another host is never passed on: his ESPN page instead
    odd = NF.item({"headline": "x", "published": "2026-10-03T13:33:00Z", "links": {"web": {"href": "https://evil.example/x"}}}, "7")
    assert odd is not None and odd["url"] == "https://www.espn.com/nfl/player/_/id/7"
    assert NF.clean_id("4262921.0") == "4262921" and NF.clean_id("abc") is None and NF.clean_id(None) is None


# ------------------------------------------------------------------------------ the feed: cache, bucket, outage
def test_cache_an_hour_off_game_days_15_minutes_on_them(tmp_path):
    clock = Clock(RECORDED)
    f = _feed(tmp_path, clock)
    assert len(f.latest(JJ_ESPN)) == 3 and len(f.calls_made) == 1
    clock.t += 59 * 60
    assert len(f.latest(JJ_ESPN)) == 3 and len(f.calls_made) == 1          # within the hour: the copy
    clock.t += 2 * 60
    f.latest(JJ_ESPN)
    assert len(f.calls_made) == 2                                           # an hour old: ESPN again
    g = _feed(tmp_path / "g", Clock(RECORDED), game_day=True)
    g.latest(JJ_ESPN)
    g.wall.t += 16 * 60                                                     # type: ignore[attr-defined]
    g.latest(JJ_ESPN)
    assert len(g.calls_made) == 2                                           # a game day: 15 minutes
    assert "playerId=4262921" in f.calls_made[0] and "limit=5" in f.calls_made[0]


def test_the_disk_copy_keeps_only_the_line_and_survives_a_restart(tmp_path):
    clock = Clock(RECORDED)
    _feed(tmp_path, clock).latest(JJ_ESPN)
    disk = json.loads((tmp_path / "espn_news" / f"{JJ_ESPN}.json").read_text())
    assert set(disk) == {"fetched_at", "as_of", "items"}
    assert all(set(i) == {"headline", "date", "source", "url"} for i in disk["items"])
    assert '"story"' not in json.dumps(disk) and "Updated inactives" not in json.dumps(disk)
    again = _feed(tmp_path, clock)                                           # a restart within the hour
    assert len(again.latest(JJ_ESPN)) == 3 and again.calls_made == []


def test_an_outage_is_no_line_or_the_last_copy(tmp_path):
    def down(_url):
        raise NF.FeedUnavailable("ESPN news: timed out")

    clock = Clock(RECORDED)
    f = _feed(tmp_path, clock, fetch=down)
    assert f.latest(JJ_ESPN) == [] and f.failures == 1                      # never a copy: nothing, no error
    ok = _feed(tmp_path / "b", clock)
    ok.latest(JJ_ESPN)
    ok._fetch = lambda _u: down(_u)                                          # ESPN goes down an hour later
    clock.t += 2 * HOUR
    assert len(ok.latest(JJ_ESPN)) == 3 and ok.failures == 1 and ok.stale_served == 1


def test_the_bucket_caps_calls_a_minute(tmp_path):
    clock = Clock(RECORDED)
    f = _feed(tmp_path, clock, per_min=1)
    assert len(f.latest(JJ_ESPN)) == 3
    assert f.latest(CONNER_ESPN) == []                                      # bucket empty: no call, no line
    assert len(f.calls_made) == 1
    clock.t += 61
    f.latest(CONNER_ESPN)
    assert len(f.calls_made) == 2


def test_switched_off_never_calls(tmp_path, monkeypatch):
    monkeypatch.setenv(NF.SWITCH_ENV, "off")
    f = _feed(tmp_path, Clock(RECORDED))
    assert f.latest(JJ_ESPN) == [] and f.calls_made == []


def test_fixture_mode_measures_age_from_the_recorded_answer(tmp_path):
    fx = tmp_path / "espn"
    fx.mkdir()
    shutil.copy(ESPN / f"news_{JJ_ESPN}.json", fx)
    f = NF.NewsFeed(fixtures=fx, wall=Clock(datetime(2027, 1, 1, tzinfo=UTC).timestamp()))
    assert len(f.latest(JJ_ESPN)) == 3                                      # recorded 2026-10-03: fresh then
    assert f.latest("999") == []                                             # no fixture: no line
    assert f.cache_root is None and not (tmp_path / "espn_news").exists()   # fixtures are never cached


# ------------------------------------------------------------------------------ the card
def _espn_fixtures(tmp_path, monkeypatch, *, stamp: str | None = None, files=(JJ_ESPN, CONNER_ESPN)) -> Path:
    fx = tmp_path / "espn"
    fx.mkdir()
    shutil.copy(ESPN / "db_playerids_espn.csv", fx)
    shutil.copy(ESPN / "injuries.json", fx)
    for e in files:
        b = _body(e)
        if stamp:
            b["timestamp"] = stamp
        (fx / f"news_{e}.json").write_text(json.dumps(b))
    monkeypatch.setenv(NF.FIXTURES_ENV, str(fx))
    news.reset()
    return fx


@needs_db
def test_card_news_from_the_fixture_feed(client, tmp_path, monkeypatch):
    _espn_fixtures(tmp_path, monkeypatch)
    d = client.get(f"/api/player/{JEFFERSON}", params={"league": SCRUBS}).json()
    # IF-4 (the decision-quality review): the three newest, the items about him first — the inactives story (Oct 3,
    # "… DeVonta to sit; McConkey questionable", not about him) moves behind his two RotoWire blurbs, labelled "league"
    assert [n["date"] for n in d["news"]] == ["2026-10-03T13:33:00Z", "2026-10-02T18:35:16Z", "2026-10-03T00:59:53Z"]
    assert d["news"][0]["source"] == "RotoWire via ESPN" and d["news"][2]["source"] == "ESPN"
    assert d["news"][1]["headline"] == "Jefferson (ankle) has been ruled out for Sunday's game versus the Dolphins."
    assert [n["about"] for n in d["news"]] == ["player", "player", "league"]
    assert all(n["url"].startswith("https://www.espn.com/") for n in d["news"])
    assert all(set(n) == {"headline", "date", "source", "url", "about"} for n in d["news"])
    st = client.get("/api/status").json()["news"]
    assert st["enabled"] is True and st["mode"] == "fixtures" and st["calls"] == 1


@needs_db
def test_card_hides_stale_news(client, tmp_path, monkeypatch):
    _espn_fixtures(tmp_path, monkeypatch, stamp="2026-10-20T12:00:00Z")      # the same items, read 17 days later
    d = client.get(f"/api/player/{JEFFERSON}", params={"league": SCRUBS}).json()
    assert d["news"] == []


@needs_db
def test_card_outage_is_an_empty_line(client, tmp_path, monkeypatch):
    _espn_fixtures(tmp_path, monkeypatch, files=())                           # no answer for him: the feed is "out"
    r = client.get(f"/api/player/{JEFFERSON}", params={"league": SCRUBS})
    assert r.status_code == 200 and r.json()["news"] == []

    def boom(_eid):
        raise RuntimeError("anything at all")

    monkeypatch.setattr(news, "espn_id", boom)
    r = client.get(f"/api/player/{JEFFERSON}", params={"league": SCRUBS})
    assert r.status_code == 200 and r.json()["news"] == []


@needs_db
def test_card_news_off_switch(client, tmp_path, monkeypatch):
    fx = _espn_fixtures(tmp_path, monkeypatch)
    monkeypatch.setenv(NF.SWITCH_ENV, "off")
    d = client.get(f"/api/player/{JEFFERSON}", params={"league": SCRUBS}).json()
    assert d["news"] == [] and NF.feed().calls == 0
    assert client.get("/api/status").json()["news"] == {"enabled": False}
    assert (fx / f"news_{JJ_ESPN}.json").exists()


@needs_db
def test_fixture_mode_without_espn_fixtures_is_off(client):
    # every API test runs on the Sleeper fixtures without ESPN's (conftest): the card answers news: [] and never calls
    d = client.get(f"/api/player/{JEFFERSON}", params={"league": SCRUBS}).json()
    assert d["news"] == [] and news.enabled() is False


@needs_db
def test_rows_never_fetch_news(client, tmp_path, monkeypatch):
    # Waivers' and Trends' rows: no call to the news feed (one athlete per card opened, never in bulk)
    _espn_fixtures(tmp_path, monkeypatch)
    assert client.get("/api/waivers", params={"league": SCRUBS, "team": 2}).status_code == 200
    assert client.get("/api/trends", params={"league": SCRUBS}).status_code == 200
    assert NF.feed().calls == 0
