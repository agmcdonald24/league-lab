"""Wave I-0, I0-C: find a MyFantasyLeague league by its name (mfl_client.MFL.league_search, `?mfl_search=`).

Fixture: `fixtures/mfl/leagueSearch_addicts.json` is MFL's answer to `TYPE=leagueSearch&SEARCH=addicts` fetched
2026-10-03 through the browser pane (72 leagues, all 2026), trimmed to MFL's first 30 as they came (21861 among them;
two names with stray spaces; every `homeURL` written `https//…`, MFL's missing colon).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from league_lab import anyleague as A
from league_lab import mfl_client as M
from league_lab import player_ids as PI

FX = Path(__file__).with_name("fixtures")
MFL_FX = FX / "mfl"


@pytest.fixture(autouse=True)
def _mfl_fixtures(monkeypatch):
    monkeypatch.setenv(M.FIXTURES_ENV, str(MFL_FX))
    monkeypatch.setenv(PI.CSV_ENV, str(FX / "ff" / "db_playerids.csv"))
    monkeypatch.setenv(M.YEAR_ENV, "2026")
    PI.reset()
    A._default = None
    yield
    PI.reset()
    A._default = None


def _fake(body, calls: list):
    def fetch(url: str):
        calls.append(url)
        return url, json.dumps(body) if not isinstance(body, str) else body
    return fetch


# ------------------------------------------------------------------ the client
def test_search_parses_the_saved_answer():
    rows = M.MFL().league_search("addicts")
    assert len(rows) == 30 and {r["year"] for r in rows} == {2026}
    assert all(r["id"].isdigit() and r["home_url"].startswith("https://www") for r in rows)
    mine = next(r for r in rows if r["id"] == "21861")
    assert mine == {"id": "21861", "name": "Addicts 1 Redraft $300 No Trade", "year": 2026,
                    "home_url": "https://www45.myfantasyleague.com/2026/home/21861"}
    names = [r["name"] for r in rows]
    assert "Game of Addicts!" in names and "Addicts anonymous" in names        # MFL's stray spaces trimmed
    # best first: names that start with the text, then a word that does, then the rest ("Fanaddicts")
    assert names[:4] == ["Addicts anonymous", "Addicts 1 Redraft $300 No Trade", "Addicts 4 Redraft $500 No Trade",
                         "Addicts 5 Redraft $500 No Trade"]
    assert names[-1] == "Football Fanaddicts"


def test_search_calls_mfl_once_per_ten_minutes_on_the_api_host():
    t = [0.0]
    calls: list[str] = []
    body = json.loads((MFL_FX / "leagueSearch_addicts.json").read_text())
    c = M.MFL(fixtures=None, year=2026, fetch=_fake(body, calls), clock=lambda: t[0])
    c.fixtures = None
    assert len(c.league_search("  Addicts ")) == 30
    assert calls == ["https://api.myfantasyleague.com/2026/export?TYPE=leagueSearch&SEARCH=addicts&JSON=1"]
    c.league_search("ADDICTS")                                     # the same search (case and spaces aside): cached
    assert len(calls) == 1 and c.hosts["21861"] == "https://www45.myfantasyleague.com"
    t[0] += 601
    c.league_search("addicts")
    assert len(calls) == 2 and c.stats()["cache"]["search"]["ttl_s"] == 600


def test_search_three_character_minimum_makes_no_call():
    calls: list[str] = []
    c = M.MFL(fixtures=None, year=2026, fetch=_fake({}, calls))
    c.fixtures = None
    assert c.league_search("ad") == [] and c.league_search("  a  ") == [] and calls == []


@pytest.mark.parametrize("body", [
    {"version": "1.0", "leagues": ""},
    {"version": "1.0", "leagues": {}},
    {"version": "1.0", "leagues": {"league": []}},
    {"error": {"$t": "Invalid search"}},
])
def test_search_nothing_found_shapes(body):
    c = M.MFL(fixtures=None, year=2026, fetch=_fake(body, []))
    c.fixtures = None
    assert c.league_search("nothing like it") == []


def test_search_this_season_only_one_league_and_odd_rows():
    body = {"leagues": {"league": {"year": "2026", "id": "777", "name": "Dad&apos;s  League", "homeURL": "junk"}}}
    c = M.MFL(fixtures=None, year=2026, fetch=_fake(body, []))
    c.fixtures = None
    assert c.league_search("dad") == [{"id": "777", "name": "Dad's League", "year": 2026,
                                       "home_url": "https://www.myfantasyleague.com/2026/home/777"}]
    body = {"leagues": {"league": [{"year": "2025", "id": "1", "name": "Last year"}, {"year": "2026", "id": "x1", "name": "Bad id"},
                                   {"year": "2026", "id": "2", "name": "This year",
                                    "homeURL": "https//www46.myfantasyleague.com/2026/home/3"}]}}
    c = M.MFL(fixtures=None, year=2026, fetch=_fake(body, []))
    c.fixtures = None
    got = c.league_search("year")
    assert [r["id"] for r in got] == ["2"]
    assert got[0]["home_url"] == "https://www.myfantasyleague.com/2026/home/2"   # the homeURL names another league


def test_search_mfl_down_and_busy():
    c = M.MFL(fixtures=None, year=2026, fetch=lambda url: (_ for _ in ()).throw(M.MFLUnavailable("MyFantasyLeague down")))
    c.fixtures = None
    with pytest.raises(M.MFLUnavailable):
        c.league_search("addicts")
    c = M.MFL(fixtures=None, year=2026, fetch=_fake({"error": {"$t": "Too many requests, slow down"}}, []))
    c.fixtures = None
    with pytest.raises(M.MFLBusy):
        c.league_search("addicts")


@pytest.mark.parametrize("text,link", [("21861", True), ("mfl:21861", True), ("www45.myfantasyleague.com/2026/home/21861", True),
                                       ("https://www45.myfantasyleague.com/2026/options?L=21861&F=0004", True),
                                       ("Addicts 1 Redraft", False), ("addicts", False), ("2026 League of Addicts", False)])
def test_looks_like_link(text, link):
    assert M.looks_like_link(text) is link


def test_parse_link_takes_a_league_key():
    assert M.parse_link("mfl:21861") == ("21861", None, None)


# ------------------------------------------------------------------ the route
def test_route_search_by_name(client):
    r = client.get("/api/leagues", params={"mfl_search": "addicts"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["platform"] == "mfl" and d["query"] == "addicts" and d["season"] == 2026 and d["total"] == 30
    assert len(d["matches"]) == 25 and "first 25 of 30" in d["note"]
    m = next(x for x in d["matches"] if x["name"] == "Addicts 1 Redraft $300 No Trade")
    assert m == {"league_id": "mfl:21861", "name": "Addicts 1 Redraft $300 No Trade", "year": 2026,
                 "home_url": "https://www45.myfantasyleague.com/2026/home/21861"}
    assert all(x["league_id"].startswith("mfl:") and x["year"] == 2026 for x in d["matches"])


def test_route_bad_home_url_never_leaks(client):
    text = client.get("/api/leagues", params={"mfl_search": "addicts"}).text
    assert "https//" not in text and "homeURL" not in text


def test_route_three_character_rule(client):
    before = A.sleeper().mfl.client.calls
    for q in ("ad", " a ", ""):
        r = client.get("/api/leagues", params={"mfl_search": q})
        assert r.status_code == 200 and r.json()["matches"] == [] and "at least 3 letters" in r.json()["note"]
    assert A.sleeper().mfl.client.calls == before                  # nothing asked of MFL


def test_route_no_match(client):
    d = client.get("/api/leagues", params={"mfl_search": "Zebra Llama Club"}).json()
    assert d["matches"] == [] and d["total"] == 0 and "No MyFantasyLeague league this season" in d["note"]


@pytest.mark.parametrize("text", ["https://www45.myfantasyleague.com/2026/options?L=21861&F=0004",
                                  "www45.myfantasyleague.com/2026/home/21861", "21861", "mfl:21861"])
def test_route_a_link_in_the_box_answers_as_before(client, text):
    got = client.get("/api/leagues", params={"mfl_search": text})
    same = client.get("/api/leagues", params={"mfl": text})
    assert got.status_code == same.status_code == 200, got.text
    assert got.json() == same.json() and got.json()["league"]["league_id"] == "mfl:21861" and "matches" not in got.json()
    if "F=0004" in text:
        assert got.json()["roster_id"] == 4


def test_route_a_private_league_link_still_404s(client):
    r = client.get("/api/leagues", params={"mfl_search": "https://www45.myfantasyleague.com/2026/home/99999999"})
    assert r.status_code == 404 and "Ask the commissioner to allow API access" in r.json()["error"]


def test_route_mfl_down_is_502(client, monkeypatch):
    def down(self, text):
        raise M.MFLUnavailable("MyFantasyLeague https://api.myfantasyleague.com/…: HTTP 500")
    monkeypatch.setattr(M.MFL, "league_search", down)
    r = client.get("/api/leagues", params={"mfl_search": "addicts"})
    assert r.status_code == 502 and r.json()["error"] == "MyFantasyLeague did not answer"
