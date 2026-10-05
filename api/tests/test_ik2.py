"""Wave I-K, IK-2: Yahoo through the official OAuth 2.0 Fantasy Sports API (league_lab.yahoo_client / yahoo_leagues,
league_lab_api.yahoo_connect).

Fixtures (`fixtures/yahoo/`, built by `fixtures/make_ik2_yahoo_fixtures.py`): **synthetic** — shaped from Yahoo's docs
and the yfpy / yahoo_fantasy_api clients, never read from Yahoo. League `461.l.4242`: 12 teams, superflex, week 4, the
fixture user (guid FIXTUREGUID3) on team 3; `461.l.5151` has no files (a private league the user is not in).

Covered: the connect → callback → cookie flow (fixture mode, and live mode against a stub token endpoint: Basic auth,
the form, the state check, a refusal at Yahoo, a forged state, a refused exchange); the 503 without the secrets; the
sealed cookie (round trip, tamper, another purpose, expiry, no token in any response body); the middleware (a read
with the cookie, a refresh that re-sets the cookie, a refused refresh that clears it); the league end to end on the
fixture in Sleeper's shapes (league, users, rosters, matchups, transactions, free agents, my leagues).
"""

from __future__ import annotations

import base64
import time
import urllib.parse
from pathlib import Path

import pytest
from league_lab import player_ids as PI
from league_lab import yahoo_client as Y
from league_lab import yahoo_leagues as YL
from league_lab.sleeper_client import Sleeper

from league_lab_api import yahoo_connect as C

from .conftest import needs_db

FX = Path(__file__).with_name("fixtures")
YFX = FX / "yahoo"
IDS = FX / "ff" / "db_playerids.csv"
KEY = "yahoo:461.l.4242"


@pytest.fixture
def fixture_mode(monkeypatch):
    monkeypatch.setenv(Y.FIXTURES_ENV, str(YFX))
    monkeypatch.setenv(PI.CSV_ENV, str(IDS))
    monkeypatch.setenv("LEAGUE_LAB_SLEEPER_FIXTURES", str(FX / "sleeper"))
    monkeypatch.delenv(Y.CLIENT_ID_ENV, raising=False)
    monkeypatch.delenv(Y.CLIENT_SECRET_ENV, raising=False)
    monkeypatch.setattr(C, "_CLIENT", None)
    PI.reset()
    yield
    PI.reset()


@pytest.fixture
def live_mode(monkeypatch):
    """Live mode with a stub token endpoint (no request leaves the process)."""
    monkeypatch.delenv(Y.FIXTURES_ENV, raising=False)
    monkeypatch.setenv(Y.CLIENT_ID_ENV, "cid-test")
    monkeypatch.setenv(Y.CLIENT_SECRET_ENV, "csecret-test")
    seen: list[tuple[dict, dict]] = []

    def stub(form: dict, headers: dict) -> tuple[int, dict]:
        seen.append((form, headers))
        if form.get("grant_type") == "authorization_code" and form.get("code") == "good-code":
            return 200, {"access_token": "AT-1", "token_type": "bearer", "expires_in": 3600, "refresh_token": "RT-1",
                         "xoauth_yahoo_guid": "GUID1"}
        if form.get("grant_type") == "refresh_token" and form.get("refresh_token") == "RT-1":
            return 200, {"access_token": "AT-2", "token_type": "bearer", "expires_in": 3600, "refresh_token": "RT-1"}
        return 400, {"error": "invalid_grant"}
    monkeypatch.setattr(Y, "TOKEN_POST", stub)
    yield seen


def _set_secret(client, monkeypatch):
    monkeypatch.setenv("LEAGUE_LAB_API_SECRET", "test-secret-ik2")


# ------------------------------------------------------------------ not configured
def test_connect_503_without_the_secrets(client, monkeypatch):
    monkeypatch.delenv(Y.FIXTURES_ENV, raising=False)
    monkeypatch.delenv(Y.CLIENT_ID_ENV, raising=False)
    monkeypatch.delenv(Y.CLIENT_SECRET_ENV, raising=False)
    for path in ("/api/yahoo/connect", "/api/yahoo/callback?code=x&state=y"):
        r = client.get(path, follow_redirects=False)
        assert r.status_code == 503, path
        body = r.json()
        assert body["code"] == "yahoo_not_configured"
        assert body["error"] == "Yahoo sign-in is not set up on this server yet"
    st = client.get("/api/yahoo/status").json()
    assert st == {"configured": False, "connected": False, "fixtures": False}


def test_connect_503_with_yahoo_secrets_but_no_api_secret(client, monkeypatch):
    monkeypatch.delenv(Y.FIXTURES_ENV, raising=False)
    monkeypatch.setenv(Y.CLIENT_ID_ENV, "cid")
    monkeypatch.setenv(Y.CLIENT_SECRET_ENV, "sec")
    r = client.get("/api/yahoo/connect", follow_redirects=False)
    assert r.status_code == 503 and r.json()["code"] == "yahoo_not_configured"


def test_the_beta_gate_covers_the_routes(client, monkeypatch, fixture_mode):
    monkeypatch.setenv("LEAGUE_LAB_APP_PASSWORD", "pw")
    assert client.get("/api/yahoo/connect", follow_redirects=False).status_code == 401
    assert client.get("/api/yahoo/status").status_code == 401


# ------------------------------------------------------------------ the OAuth flow (live mode, stub token endpoint)
def test_connect_redirects_to_yahoo_with_a_signed_state(client, monkeypatch, live_mode):
    _set_secret(client, monkeypatch)
    r = client.get("/api/yahoo/connect", follow_redirects=False, headers={"x-forwarded-proto": "https",
                                                                           "host": "isuckatfantasy.io"})
    assert r.status_code == 302
    u = urllib.parse.urlparse(r.headers["location"])
    q = dict(urllib.parse.parse_qsl(u.query))
    assert f"{u.scheme}://{u.netloc}{u.path}" == Y.AUTH_URL
    assert q["client_id"] == "cid-test" and q["response_type"] == "code" and q["scope"] == "fspt-r"
    assert q["redirect_uri"] == "https://isuckatfantasy.io/api/yahoo/callback"
    nonce = r.cookies.get(C.STATE_COOKIE)
    assert nonce and q["state"].startswith(nonce + ".")
    sc = r.headers["set-cookie"]
    assert "HttpOnly" in sc and "Path=/api/yahoo" in sc and "secure" in sc.lower()


def test_redirect_uri_override(client, monkeypatch, live_mode):
    _set_secret(client, monkeypatch)
    monkeypatch.setenv("LEAGUE_LAB_YAHOO_REDIRECT_URI", "https://isuckatfantasy.io/api/yahoo/callback")
    r = client.get("/api/yahoo/connect", follow_redirects=False)
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(r.headers["location"]).query))
    assert q["redirect_uri"] == "https://isuckatfantasy.io/api/yahoo/callback"


def test_callback_exchanges_the_code_and_sets_the_sealed_cookie(client, monkeypatch, live_mode):
    _set_secret(client, monkeypatch)
    r = client.get("/api/yahoo/connect", follow_redirects=False)
    state = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(r.headers["location"]).query))["state"]
    cb = client.get(f"/api/yahoo/callback?code=good-code&state={urllib.parse.quote(state)}", follow_redirects=False)
    assert cb.status_code == 302 and cb.headers["location"] == "/leagues?platform=yahoo"
    form, headers = live_mode[-1]
    assert form == {"grant_type": "authorization_code", "code": "good-code",
                    "redirect_uri": "http://testserver/api/yahoo/callback", "client_id": "cid-test",
                    "client_secret": "csecret-test"}
    assert headers["Authorization"] == "Basic " + base64.b64encode(b"cid-test:csecret-test").decode()
    assert headers["Content-Type"] == "application/x-www-form-urlencoded"
    raw = cb.cookies.get(C.COOKIE)
    assert raw and "RT-1" not in raw and "AT-1" not in raw            # sealed, not readable
    s = C.session_from_cookie(raw)
    assert (s.refresh_token, s.access_token, s.guid) == ("RT-1", "AT-1", "GUID1")
    set_cookies = cb.headers.get_list("set-cookie")
    mine = next(x for x in set_cookies if x.startswith(C.COOKIE + "="))
    assert "HttpOnly" in mine and "Path=/api" in mine and "SameSite=lax" in mine and "Max-Age=5184000" in mine
    assert any(x.startswith(C.STATE_COOKIE + "=") and "Max-Age=0" in x for x in set_cookies)   # the state is spent
    assert client.get("/api/yahoo/status").json()["connected"] is True


@pytest.mark.parametrize(("query", "error"), [("error=access_denied&state=x", "denied"),
                                              ("code=good-code&state=forged.1.abc", "state"),
                                              ("code=good-code", "state")])
def test_callback_refusals_redirect_with_a_reason(client, monkeypatch, live_mode, query, error):
    _set_secret(client, monkeypatch)
    client.get("/api/yahoo/connect", follow_redirects=False)
    r = client.get(f"/api/yahoo/callback?{query}", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == f"/leagues?platform=yahoo&yahoo_error={error}"
    assert not r.cookies.get(C.COOKIE)


def test_callback_state_from_another_browser_is_refused(client, monkeypatch, live_mode):
    _set_secret(client, monkeypatch)
    r = client.get("/api/yahoo/connect", follow_redirects=False)
    state = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(r.headers["location"]).query))["state"]
    client.cookies.clear()                                                # the state cookie is not this browser's
    cb = client.get(f"/api/yahoo/callback?code=good-code&state={urllib.parse.quote(state)}", follow_redirects=False)
    assert cb.headers["location"].endswith("yahoo_error=state")


def test_callback_refused_exchange(client, monkeypatch, live_mode):
    _set_secret(client, monkeypatch)
    r = client.get("/api/yahoo/connect", follow_redirects=False)
    state = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(r.headers["location"]).query))["state"]
    cb = client.get(f"/api/yahoo/callback?code=bad-code&state={urllib.parse.quote(state)}", follow_redirects=False)
    assert cb.headers["location"].endswith("yahoo_error=refused") and not cb.cookies.get(C.COOKIE)


def test_disconnect_clears_the_cookie(client, monkeypatch, fixture_mode):
    client.cookies.set(C.COOKIE, C.fixture_cookie())
    assert client.get("/api/yahoo/status").json()["connected"] is True
    r = client.post("/api/yahoo/disconnect")
    assert r.json() == {"connected": False, "removed": 0}    # ---- IL-5: `removed` = the account's row (none: a guest)
    sc = r.headers["set-cookie"]
    assert sc.startswith(C.COOKIE + "=") and "Max-Age=0" in sc and "Path=/api" in sc


# ------------------------------------------------------------------ the sealed cookie
def test_seal_round_trip_tamper_purpose_expiry(monkeypatch):
    monkeypatch.setenv("LEAGUE_LAB_API_SECRET", "s1")
    obj = {"r": "refresh", "a": "access", "e": 1, "g": None}
    v = C.seal(obj, "yahoo")
    assert C.unseal(v, "yahoo") == obj
    assert C.seal(obj, "yahoo") != v                                      # a fresh nonce each time
    assert C.unseal(v, "espn") is None                                    # another purpose
    body = v.split(".", 1)[1]
    flipped = body[:20] + ("A" if body[20] != "A" else "B") + body[21:]
    assert C.unseal("v1." + flipped, "yahoo") is None                     # tampered
    assert C.unseal(C.seal(obj, "yahoo", days=-1), "yahoo") is None       # expired
    assert C.unseal("garbage", "yahoo") is None and C.unseal(None, "yahoo") is None
    monkeypatch.setenv("LEAGUE_LAB_API_SECRET", "s2")
    assert C.unseal(v, "yahoo") is None                                   # another server secret


def test_long_access_token_is_left_out_of_the_cookie(monkeypatch):
    monkeypatch.setenv("LEAGUE_LAB_API_SECRET", "s1")
    s = Y.YahooSession(refresh_token="RT", access_token="x" * 4000, expires_at=time.time() + 3600)
    v = C.cookie_value(s)
    assert len(v) <= C.MAX_COOKIE
    back = C.session_from_cookie(v)
    assert back.refresh_token == "RT" and back.access_token == "" and back.expires_at == 0


def test_session_repr_hides_the_tokens():
    s = Y.YahooSession(refresh_token="SECRET-RT", access_token="SECRET-AT")
    assert "SECRET" not in repr(s) and "SECRET" not in str(s)


# ------------------------------------------------------------------ fixture mode: the whole flow + the league
def test_fixture_connect_flow_end_to_end(client, fixture_mode):
    r = client.get("/api/yahoo/connect", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"].startswith("/api/yahoo/callback?code=fixture&state=")
    cb = client.get(r.headers["location"], follow_redirects=False)
    assert cb.headers["location"] == "/leagues?platform=yahoo"
    assert C.session_from_cookie(cb.cookies.get(C.COOKIE)).guid == "FIXTUREGUID3"
    st = client.get("/api/yahoo/status").json()
    assert st == {"configured": True, "connected": True, "fixtures": True}
    leagues = client.get("/api/yahoo/leagues").json()["leagues"]
    assert [x["key"] for x in leagues] == [KEY]
    assert leagues[0]["team_id"] == 3 and leagues[0]["team_name"] == "Synthetic Team 3"
    assert "fixture-refresh" not in client.get("/api/yahoo/leagues").text


def test_leagues_without_the_cookie_says_connect(client, fixture_mode):
    r = client.get("/api/yahoo/leagues")
    assert r.status_code == 401 and r.json()["code"] == "yahoo_sign_in_required"


def test_middleware_refreshes_an_expired_token_and_resets_the_cookie(client, fixture_mode):
    stale = C.cookie_value(Y.YahooSession(refresh_token="fixture-refresh", access_token="old", expires_at=1))
    client.cookies.set(C.COOKIE, stale)
    r = client.get("/api/yahoo/leagues")
    assert r.status_code == 200
    new = r.cookies.get(C.COOKIE)
    assert new and new != stale
    s = C.session_from_cookie(new)
    assert s.access_token.startswith("fixture-access-") and s.expires_at > time.time()


def test_middleware_clears_the_cookie_when_yahoo_refuses_the_refresh(client, fixture_mode):
    client.cookies.set(C.COOKIE, C.cookie_value(Y.YahooSession(refresh_token="revoked", access_token="old", expires_at=1)))
    r = client.get("/api/yahoo/leagues")
    assert r.status_code == 401 and r.json()["code"] == "yahoo_session_expired"
    sc = [x for x in r.headers.get_list("set-cookie") if x.startswith(C.COOKIE + "=")]
    assert sc and "Max-Age=0" in sc[0]


def _adapter() -> YL.YahooLeagues:
    return YL.YahooLeagues(Y.Yahoo(), Sleeper().players)


def test_the_league_in_sleeper_shapes_end_to_end(fixture_mode):
    token = Y.request_session.set(C.session_from_cookie(C.fixture_cookie()))
    try:
        yl = _adapter()
        lg = yl.league(KEY)
        assert lg["league_id"] == KEY and lg["platform"] == "yahoo" and lg["total_rosters"] == 12
        assert [s for s in lg["roster_positions"] if s != "BN"] == ["QB", "WR", "WR", "WR", "RB", "RB", "TE", "FLEX",
                                                                    "SUPER_FLEX", "K", "DEF"]
        assert lg["settings"]["leg"] == 4 and lg["settings"]["reserve_slots"] == 1
        assert lg["settings"]["waiver_type"] == 2 and lg["settings"]["playoff_week_start"] == 15
        assert lg["scoring_settings"]["rec"] == 0.5 and lg["scoring_settings"]["pass_td"] == 4
        assert lg["yahoo"]["scoring"]["unpriced"] == ["Extra Point Returned"]
        users = yl.users(KEY)
        assert len(users) == 12 and users[2]["metadata"]["team_name"] == "Synthetic Team 3"
        rosters = yl.rosters(KEY)
        mine = rosters[2]
        assert mine["roster_id"] == 3 and len(mine["starters"]) == 11 and "0" not in mine["starters"]
        assert set(mine["starters"]) <= set(mine["players"]) and len(mine["reserve"]) == 1
        assert "yahoo:99001" in mine["players"] and yl.unmapped(KEY) == [
            {"yahoo_id": "99001", "name": "Synthetic Prospect", "position": "WR"}]
        assert yl.mapped_by(KEY) == {"table": 192, "defense": 12, "name": 1, "unmapped": 1}
        assert sum(r["settings"]["wins"] for r in rosters) == 18              # 3 weeks × 6 games
        m3 = yl.matchups(KEY, 3)
        assert len(m3) == 12 and len({m["matchup_id"] for m in m3}) == 6
        assert set(yl.season_matchups(KEY, 3)) == {1, 2, 3}
        t3 = yl.transactions(KEY, 3)
        assert {t["type"] for t in t3} == {"trade", "waiver"}
        assert next(t for t in t3 if t["type"] == "waiver")["settings"] == {"waiver_bid": 14}
        assert len(yl.free_agents(KEY)) == 25
        with pytest.raises(Y.YahooLeagueNotFound) as e:
            yl.league("yahoo:461.l.5151")
        assert e.value.code == "yahoo_league_unknown"
    finally:
        Y.request_session.reset(token)


def test_the_league_without_a_session_needs_sign_in(fixture_mode):
    with pytest.raises(Y.YahooSignInRequired) as e:
        _adapter().league(KEY)
    code, words, fix = Y.setup_parts(e.value)
    assert code == "yahoo_sign_in_required" and "Connect" in words and fix


# ------------------------------------------------------------------ the pricing pipeline (until IK-3's Router lands)
class _RouterShim:
    """Test-only: what IK-3's Router does for a ``yahoo:`` key (dispatch to ``YahooLeagues``; ``players()`` merges its
    unmapped rows), so the real on-demand pipeline prices and solves the Yahoo league on this branch."""

    def __init__(self) -> None:
        self.sleeper = Sleeper()
        self.yahoo = YL.YahooLeagues(Y.Yahoo(), self.sleeper.players, ids=PI.table)
        self.calls = 0

    def __getattr__(self, name):
        return getattr(self.sleeper, name)

    def _p(self, key):
        return self.yahoo if YL.is_yahoo(key) else self.sleeper

    def league(self, key):
        return self._p(key).league(key)

    def rosters(self, key):
        return self._p(key).rosters(key)

    def users(self, key):
        return self._p(key).users(key)

    def matchups(self, key, week):
        return self._p(key).matchups(key, week)

    def players(self):
        return {**self.sleeper.players(), **self.yahoo.extra_players}


@needs_db
def test_the_yahoo_league_prices_and_solves_through_the_pipeline(fixture_mode, monkeypatch):
    from league_lab import anyleague as A

    from league_lab_api.db import query
    orig = A.check_id
    monkeypatch.setattr(A, "check_id", lambda k: YL.check_key(k) if YL.is_yahoo(k) else orig(k))
    token = Y.request_session.set(C.session_from_cookie(C.fixture_cookie()))
    try:
        od = A.lineup_rows(query, KEY, 3, 4, client=_RouterShim())
    finally:
        Y.request_session.reset(token)
    t = od.totals
    assert t["slots_total"] == 11 and t["slots_filled"] == 11 and t["lineup_value"] > 60
    slots = list(od.rows.loc[od.rows["role"] == "starter", "slot"])
    assert "SUPER_FLEX" in slots and "FLEX" in slots and "DEF" in slots
    assert od.unmapped_players == [{"sleeper_player_id": "yahoo:99001", "player_name": "Synthetic Prospect",
                                    "position": "WR", "team": "KC"}]
    assert "0.5 per catch" in od.scoring["priced"]
