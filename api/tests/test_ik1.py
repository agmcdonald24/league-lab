"""Wave I-K, IK-1: ESPN leagues on demand — the cookie routes (espn_connect), the sealed cookie (sealed), the private
switch end to end through a request, and (once IK-3's Router routes ``espn:`` keys) the league on every screen.

Fixtures: ``fixtures/espn_leagues/`` — 4242 ("Synthetic Public League", public, 10 teams, week 4) and 5150 (the same,
private: 401 without cookies); synthetic, built from cwendt94/espn-api's documented shapes
(``fixtures/make_ik1_fixtures.py``). No test calls ESPN.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from league_lab import anyleague as A
from league_lab import espn_client as E
from league_lab import espn_leagues as L
from league_lab import platforms as P
from league_lab import player_ids as PI
from league_lab.sleeper_client import LeagueNotFound

from league_lab_api import espn_connect, sealed

from .conftest import needs_db

FX = Path(__file__).with_name("fixtures")
LEAGUES = FX / "espn_leagues"
KEY = "espn:4242"
SECRET = "t" * 40
S2 = "AEBx" + "Qz9%2B" * 20
SWID = "{0A1B2C3D-4E5F-4A6B-8C7D-9E0F1A2B3C4D}"
WIRED = hasattr(P, "is_espn") and "espn" in (getattr(P, "provider_of", lambda k: "")("espn:1") or "")
needs_router = pytest.mark.skipif(not WIRED, reason="IK-3's Router does not route espn: keys on this branch yet")


@pytest.fixture(autouse=True)
def _espn_fixtures(monkeypatch):
    monkeypatch.setenv(E.FIXTURES_ENV, str(LEAGUES))
    monkeypatch.setenv(E.SEASON_ENV, "2026")
    monkeypatch.setenv(PI.CSV_ENV, str(FX / "ff" / "db_playerids.csv"))
    monkeypatch.delenv(E.PRIVATE_ENV, raising=False)
    monkeypatch.delenv(E.ENABLED_ENV, raising=False)
    PI.reset()
    A._default = None
    yield
    PI.reset()
    A._default = None


@pytest.fixture
def private_on(monkeypatch):
    monkeypatch.setenv(E.PRIVATE_ENV, "on")
    monkeypatch.setenv(E.SECRET_ENV, SECRET)


# ------------------------------------------------------------------ the sealed cookie
def test_sealed_round_trip_tamper_purpose_expiry(monkeypatch):
    monkeypatch.setenv(sealed.SECRET_ENV, SECRET)
    tok = sealed.seal("espn-cookies", {"s2": S2, "swid": SWID}, now=1000)
    assert tok.startswith("v1.") and S2 not in tok and "0A1B2C3D" not in tok
    assert sealed.unseal("espn-cookies", tok, max_age_s=60, now=1030) == {"s2": S2, "swid": SWID}
    assert sealed.unseal("espn-cookies", tok, max_age_s=60, now=1061) is None              # expired
    assert sealed.unseal("yahoo", tok, max_age_s=60, now=1030) is None                     # another purpose
    body = bytearray(sealed._unb64(tok[3:]))
    body[20] ^= 1
    assert sealed.unseal("espn-cookies", "v1." + sealed._b64(bytes(body)), max_age_s=60, now=1030) is None
    assert sealed.unseal("espn-cookies", "v1.!!", max_age_s=60) is None and sealed.unseal("espn-cookies", None, max_age_s=60) is None
    assert sealed.seal("x", 1) != sealed.seal("x", 1)                                       # a fresh nonce each time
    monkeypatch.setenv(sealed.SECRET_ENV, "u" * 40)
    assert sealed.unseal("espn-cookies", tok, max_age_s=10**9) is None                      # another secret
    monkeypatch.delenv(sealed.SECRET_ENV)
    assert sealed.available() is False and sealed.unseal("espn-cookies", tok, max_age_s=10**9) is None
    with pytest.raises(sealed.SealUnavailable):
        sealed.seal("espn-cookies", {})


# ------------------------------------------------------------------ the routes
def test_switch_off_routes_say_off(client):
    st = client.get("/api/espn/status")
    assert st.status_code == 200 and st.json()["private"] is False and st.json()["connected"] is False
    assert st.json()["words"] == ("Your ESPN cookies stay in your browser; isuckatfantasy reads your league with them "
                                  "and never stores them.")
    r = client.post("/api/espn/connect", json={"espn_s2": S2, "swid": SWID})
    assert r.status_code == 404 and r.json()["code"] == "espn_private_off" and "set-cookie" not in r.headers
    assert r.headers["cache-control"] == "no-store"


def test_connect_sets_a_sealed_cookie_and_status_reads_it(client, private_on, caplog):
    caplog.set_level(logging.DEBUG)
    bad = client.post("/api/espn/connect", json={"espn_s2": "<script>", "swid": "nope"})
    assert bad.status_code == 400 and bad.json()["code"] == "espn_cookies_invalid" and "<script>" not in bad.text
    assert client.post("/api/espn/connect", content=b"not json").status_code == 400
    r = client.post("/api/espn/connect", json={"espn_s2": S2, "swid": SWID.lower().strip("{}")})
    assert r.status_code == 200 and r.json() == {"ok": True, "connected": True, "words": espn_connect.WORDS}
    cookie = r.headers["set-cookie"]
    assert cookie.startswith("ll_espn=v1.") and "HttpOnly" in cookie and "Path=/api" in cookie
    assert "samesite=lax" in cookie.lower() and "Max-Age=2592000" in cookie
    value = cookie.split(";")[0][len("ll_espn="):]
    assert S2 not in value and "0A1B2C3D" not in value.upper()                              # sealed, not plain
    assert client.get("/api/espn/status").json()["connected"] is True
    out = client.post("/api/espn/disconnect")
    assert out.json()["connected"] is False and 'll_espn=""' in out.headers["set-cookie"]
    client.cookies.clear()
    assert client.get("/api/espn/status").json()["connected"] is False
    assert S2 not in caplog.text and "0A1B2C3D" not in caplog.text.upper()


def test_https_cookie_is_secure(client, private_on):
    r = client.post("/api/espn/connect", json={"espn_s2": S2, "swid": SWID}, headers={"x-forwarded-proto": "https"})
    assert "Secure" in r.headers["set-cookie"]


def test_routes_are_behind_the_beta_gate(client, monkeypatch):
    monkeypatch.setenv("LEAGUE_LAB_APP_PASSWORD", "letmein")
    assert client.get("/api/espn/status").status_code == 401
    assert client.post("/api/espn/connect", json={}).status_code == 401


# ------------------------------------------------------------------ the private league through a request
def _mini_app(directory: dict) -> TestClient:
    """The real middleware and routes, plus one route that reads an ESPN league (IK-3's routes do it in the app)."""
    app = FastAPI()
    app.middleware("http")(espn_connect.auth_middleware)
    app.include_router(espn_connect.router)
    espn = L.ESPNLeagues(E.ESPN(), lambda: directory)

    @app.get("/api/test-espn/{key}")
    def read(key: str):
        try:
            espn.require_access(key)
            lg = espn.league(key)
            return {"name": lg["name"], "rosters": len(espn.rosters(key))}
        except LeagueNotFound as exc:
            return {"code": getattr(exc, "code", None), "error": str(exc), "fix": getattr(exc, "fix", None)}
    return TestClient(app)


@pytest.fixture(scope="module")
def directory() -> dict:
    return json.loads((FX / "sleeper" / "players_nfl.json").read_text())


def test_private_league_switch_off_is_the_error(directory, monkeypatch):
    monkeypatch.setenv(E.SECRET_ENV, SECRET)
    c = _mini_app(directory)
    c.cookies.set("ll_espn", sealed.seal(espn_connect.PURPOSE, {"s2": S2, "swid": SWID}), path="/api")
    d = c.get("/api/test-espn/espn:5150").json()                    # a cookie, but the switch is off: ignored
    assert d["code"] == "espn_league_private" and d["error"].startswith("ESPN league 5150 is private.")
    assert "commissioner" in d["fix"]
    assert c.get("/api/test-espn/espn:4242").json() == {"name": "Synthetic Public League", "rosters": 10}


def test_private_league_switch_on_reads_with_the_cookie(directory, private_on, caplog):
    caplog.set_level(logging.DEBUG)
    c = _mini_app(directory)
    d = c.get("/api/test-espn/espn:5150").json()
    assert d["code"] == "espn_league_private" and "Private league?" in d["fix"]
    assert c.post("/api/espn/connect", json={"espn_s2": S2, "swid": SWID}).status_code == 200
    assert c.get("/api/test-espn/espn:5150").json() == {"name": "Synthetic Private League", "rosters": 10}
    other = TestClient(c.app)                                       # a visitor without the cookie, same process
    assert other.get("/api/test-espn/espn:5150").json()["code"] == "espn_league_private"
    assert E.AUTH.get() is None                                     # nothing left behind after the request
    assert S2 not in caplog.text


def test_unknown_league_words():
    with pytest.raises(LeagueNotFound) as e:
        E.ESPN().settings("777")
    assert E.setup_words(e.value, "777") == ("espn_league_unknown", "ESPN has no league 777 in 2026.",
                                             f"Check the id: it is {E.WHERE}.")


# ------------------------------------------------------------------ end to end through IK-3's Router
@needs_router
def test_espn_league_card(client):
    r = client.get("/api/leagues", params={"espn": "https://fantasy.espn.com/football/team?leagueId=4242&teamId=11"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["league"]["league_id"] == KEY and len(d["teams"]) == 10 and d["roster_id"] == 10
    bad = client.get("/api/leagues", params={"espn": "5150"})
    assert bad.status_code == 404 and bad.json()["code"] == "espn_league_private"
    assert client.get("/api/leagues", params={"espn": "777"}).json()["code"] == "espn_league_unknown"


@needs_router
@needs_db
def test_every_screen_answers_for_an_espn_league(client):
    mw = client.get(f"/api/my-week?league={KEY}&team=2")
    assert mw.status_code == 200, mw.text
    d = mw.json()
    assert d["league_name"] == "Synthetic Public League" and len(d["lineup"]) == 9
    for path in (f"/api/team?league={KEY}&team=2", f"/api/waivers?league={KEY}&team=2",
                 f"/api/trades/partners?league={KEY}&team=2", f"/api/league?league={KEY}&team=2",
                 f"/api/leagues/{KEY}/rosters"):
        r = client.get(path)
        assert r.status_code == 200, (path, r.text[:300])
