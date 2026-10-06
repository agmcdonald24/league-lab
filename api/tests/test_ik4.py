"""Wave I-K, IK-4: accounts, phase 1 — sign in by an emailed link, saved leagues, preferences, the watchlist, deleting an
account, the switch, the limits (docs/ACCOUNTS.md § "Built, phase 1"; docs/HOSTING.md § "Accounts").

The flow runs on the clone (`.env`'s database) with the stub mailer (`LEAGUE_LAB_ACCOUNTS=on`, no Resend key: the
messages stay in `accounts.STUB.sent`; nothing is sent anywhere). The schema comes from scripts/hosted_accounts.sql,
applied here with the pipeline role when it may create a schema, else it must already be there (applied by the
database's owner, as the nightly does on Neon). The API writes with the read-only app role exactly as on Render. Every
row the tests make belongs to an `@ik4.test` address and is deleted afterwards.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

from league_lab_api import accounts, db, main
from league_lab_api.main import app
from league_lab_api.settings import ROOT

from .conftest import DB_OK, SCRUBS

SQL_FILE = ROOT / "scripts" / "hosted_accounts.sql"
DOMAIN = "ik4.test"
MFL, ESPN, YAHOO = "mfl:21861", "espn:4242", "yahoo:461.l.4242"
TABLES = ["users", "login_links", "sessions", "connections", "leagues", "user_leagues", "preferences", "watchlist"]


def _pipeline_dsn() -> str:
    from league_lab.config import get_settings
    return get_settings().pipeline_dsn()


def _rw_conn():
    """The app role's own read-write transaction (as the API writes): the clone's accounts schema is the owner's."""
    conn = psycopg.connect(main._app_dsn(), autocommit=False)
    conn.execute("set transaction read write")
    return conn


def _cleanup() -> None:
    with _rw_conn() as conn:
        conn.execute("delete from accounts.users where email like %s", (f"%@{DOMAIN}",))
        conn.execute("delete from accounts.login_links where user_email like %s", (f"%@{DOMAIN}",))
        conn.execute("delete from accounts.leagues l where not exists "
                     "(select 1 from accounts.user_leagues u where u.league_key = l.league_key)")


@pytest.fixture(scope="module")
def schema():
    """scripts/hosted_accounts.sql applied twice (idempotent) when the pipeline role may; else it must be there."""
    if not DB_OK:
        pytest.skip("database not reachable")
    try:
        with psycopg.connect(_pipeline_dsn(), autocommit=True, connect_timeout=5) as conn:
            for _ in range(2):
                with conn.transaction():
                    conn.execute(SQL_FILE.read_text())
    except psycopg.errors.InsufficientPrivilege:
        pass                                             # the clone's owner is postgres: applied by the owner
    except psycopg.Error as exc:
        pytest.skip(f"cannot apply scripts/hosted_accounts.sql: {exc.__class__.__name__}")
    with psycopg.connect(main._app_dsn(), autocommit=True) as conn:
        if conn.execute("select to_regclass('accounts.users')").fetchone()[0] is None:
            pytest.skip("the accounts schema is not on this database (run scripts/hosted_accounts.sql as its owner)")
    _cleanup()
    yield
    _cleanup()


@pytest.fixture
def api(monkeypatch, schema):
    """The API: gate off, accounts on with the stub mailer, a secret, a fresh limiter on a clock the test moves."""
    monkeypatch.delenv("LEAGUE_LAB_APP_PASSWORD", raising=False)
    monkeypatch.delenv("LEAGUE_LAB_RESEND_API_KEY", raising=False)
    monkeypatch.setenv("LEAGUE_LAB_API_SECRET", "ik4-test-secret")
    monkeypatch.setenv(accounts.ENV, "on")
    monkeypatch.setenv("LEAGUE_LAB_PUBLIC_URL", "https://isuckatfantasy.io")
    accounts.reset()
    t = [1000.0]
    monkeypatch.setattr(accounts, "clock", lambda: t[0])
    with TestClient(app) as c:
        c.tick = lambda s: t.__setitem__(0, t[0] + s)
        yield c
    accounts.reset()
    _cleanup()


def addr(name: str) -> str:
    return f"{name}@{DOMAIN}"


def link_token(email: str) -> str:
    msg = [m for m in accounts.STUB.sent if m["to"] == email][-1]
    m = re.search(r"https://isuckatfantasy\.io/account#signin=([A-Za-z0-9_-]+)", msg["text"])
    assert m, "the email holds the link"
    assert m.group(0) in msg["html"]
    return m.group(1)


def sign_in(c: TestClient, email: str, **headers) -> TestClient:
    """A fresh browser: ask for the link, open it, keep the cookie (the client's jar)."""
    c.cookies.clear()
    r = c.post("/api/account/login", json={"email": email}, headers=headers)
    assert r.status_code == 202, r.text
    r = c.post("/api/account/verify", json={"token": link_token(email)}, headers=headers)
    assert r.status_code == 200, r.text
    return c


def q(sql: str, *params):
    with _rw_conn() as conn:
        return conn.execute(sql, params).fetchall()


# ---------------------------------------------------------------- keys (no database)
def test_league_keys_for_the_four_providers():
    assert accounts.league_key(SCRUBS, 2026) == f"sleeper:2026:{SCRUBS}"
    assert accounts.league_key(MFL, 2026) == "mfl:2026:21861"
    assert accounts.league_key(ESPN, 2026) == "espn:2026:4242"
    assert accounts.league_key("espn:2025:4242") == "espn:2025:4242"           # IK-1's espn:<season>:<id>
    assert accounts.league_key(YAHOO, 2026) == "yahoo:2026:461.l.4242"
    assert accounts.league_key("yahoo:2026:461.l.4242") == "yahoo:2026:461.l.4242"   # a league_key stays itself
    assert accounts.league_key(SCRUBS) == f"sleeper:{accounts.current_season()}:{SCRUBS}"
    for key, app_key in ((f"sleeper:2026:{SCRUBS}", SCRUBS), ("mfl:2026:21861", MFL), ("espn:2026:4242", ESPN),
                         ("yahoo:2026:461.l.4242", YAHOO)):
        assert accounts.app_key(key) == app_key
    for bad in ("", "abc", "mfl:abc", "yahoo:12345", "espn:4242x", "fantrax:1", "sleeper:1999:1", f"{SCRUBS}; drop"):
        with pytest.raises(ValueError):
            accounts.league_key(bad, 2026)


def test_the_cookie_is_signed_and_a_forged_one_reads_nothing(monkeypatch):
    monkeypatch.setenv("LEAGUE_LAB_API_SECRET", "s1")
    sid = str(uuid.uuid4())
    v = accounts.cookie_value(sid)
    assert accounts.session_id_from(v) == sid
    assert accounts.session_id_from(f"{sid}.{'0' * 64}") is None
    assert accounts.session_id_from("not-a-uuid.abc") is None
    monkeypatch.setenv("LEAGUE_LAB_API_SECRET", "s2")                 # a new secret signs everyone out
    assert accounts.session_id_from(v) is None


def test_the_resend_mailer_sends_one_request(monkeypatch):
    """The documented call (resend.com/docs/api-reference/emails/send-email): no network — urlopen is replaced."""
    seen = {}

    class Resp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake(req, timeout):
        seen.update(url=req.full_url, method=req.get_method(), headers=dict(req.header_items()),
                    body=json.loads(req.data), timeout=timeout)
        return Resp()

    monkeypatch.setattr(accounts.urllib.request, "urlopen", fake)
    monkeypatch.setenv("LEAGUE_LAB_RESEND_API_KEY", "re_test_key")
    monkeypatch.setenv("LEAGUE_LAB_MAIL_FROM", "signin@isuckatfantasy.io")
    m = accounts.mailer()
    assert m.name == "resend"
    m.send("a@ik4.test", *accounts._message("https://isuckatfantasy.io/account#signin=x"))
    assert seen["url"] == "https://api.resend.com/emails" and seen["method"] == "POST"
    assert seen["headers"]["Authorization"] == "Bearer re_test_key"
    assert seen["headers"]["User-agent"].startswith("isuckatfantasy")
    assert seen["body"]["from"] == "isuckatfantasy <signin@isuckatfantasy.io>"
    assert seen["body"]["to"] == ["a@ik4.test"] and "sign-in link" in seen["body"]["subject"]


# ---------------------------------------------------------------- the switch
def test_off_without_a_resend_key(monkeypatch, schema):
    monkeypatch.delenv("LEAGUE_LAB_APP_PASSWORD", raising=False)
    monkeypatch.delenv("LEAGUE_LAB_RESEND_API_KEY", raising=False)
    monkeypatch.setenv("LEAGUE_LAB_API_SECRET", "ik4-test-secret")
    monkeypatch.delenv(accounts.ENV, raising=False)                      # auto
    monkeypatch.setattr(accounts, "passkeys_ready", lambda: False)       # ---- IM-4: no passkeys either (test_im4)
    accounts.reset()
    with TestClient(app) as c:
        s = c.get("/api/account/status")
        assert s.status_code == 200 and s.headers["cache-control"] == "no-store"
        assert s.json()["enabled"] is False and s.json()["reason"] == "not_ready" and s.json()["signed_in"] is False
        assert s.json()["why"] == {"passkey": "not_ready", "email": "no_mailer"}             # ---- IM-4
        for method, path, body in (("post", "/api/account/login", {"email": addr("off")}), ("get", "/api/account/me", None),
                                   ("put", "/api/account/leagues", {"leagues": []}), ("delete", "/api/account", None)):
            r = c.request(method.upper(), path, json=body)
            assert r.status_code == 404 and r.json()["code"] == "accounts_off", path
        assert not accounts.STUB.sent
        monkeypatch.setenv(accounts.ENV, "off")                         # off wins over a key
        monkeypatch.setenv("LEAGUE_LAB_RESEND_API_KEY", "re_x")
        assert c.get("/api/account/status").json()["reason"] == "off"
        monkeypatch.setenv(accounts.ENV, "auto")
        monkeypatch.delenv("LEAGUE_LAB_API_SECRET")
        assert c.get("/api/account/status").json()["reason"] == "no_secret"
        monkeypatch.setenv("LEAGUE_LAB_API_SECRET", "ik4-test-secret")
        s = c.get("/api/account/status").json()                            # a key and a secret: on, with Resend
        assert s["enabled"] is True and s["reason"] is None and s["mailer"] == "resend"
    accounts.reset()


def test_the_beta_gate_stays_in_front(api, monkeypatch):
    monkeypatch.setenv("LEAGUE_LAB_APP_PASSWORD", "correct horse")
    api.cookies.clear()
    for method, path in (("GET", "/api/account/status"), ("POST", "/api/account/login"), ("GET", "/api/account/me")):
        r = api.request(method, path, json={"email": addr("gate")} if method == "POST" else None)
        assert r.status_code == 401 and r.json()["detail"].startswith("Private beta"), path
    assert not accounts.STUB.sent


# ---------------------------------------------------------------- the whole flow
def test_link_session_leagues_upserted_twice_is_one_row(api, caplog):
    caplog.set_level(logging.DEBUG)
    email = addr("andrew")
    s = api.get("/api/account/status").json()
    assert s == {"enabled": True, "reason": None, "signed_in": False, "email": None, "mailer": "stub", "session_days": 90,
                 # ---- IM-4: the sign-in methods (passkeys too: test_im4) and where passkeys work
                 "methods": ["passkey", "email"], "why": {"passkey": None, "email": None},
                 "passkey_home": "https://isuckatfantasy.io", "passkey_here": False}
    r = api.post("/api/account/login", json={"email": "  Andrew@IK4.test "})
    assert r.status_code == 202 and r.json() == {"ok": True, "sent": True, "minutes": 15}
    token = link_token(email)                                  # lower-cased address; the link on the public URL
    assert token not in r.text
    stored = q("select token_hash, expires_at - created_at, used_at, ip_hash from accounts.login_links where user_email = %s", email)
    assert len(stored) == 1 and bytes(stored[0][0]) == accounts._hash_token(token) and stored[0][2] is None
    assert stored[0][1].total_seconds() == 15 * 60 and len(bytes(stored[0][3])) == 32
    assert api.get("/api/account/me").status_code == 401                    # no session yet

    r = api.post("/api/account/verify", json={"token": token}, headers={"user-agent": "Mozilla/5.0 (iPhone; CPU)",
                                                                        "x-forwarded-proto": "https"})
    assert r.status_code == 200 and r.json() == {"ok": True, "email": email}
    cookie = r.headers["set-cookie"]
    assert cookie.startswith(f"{accounts.COOKIE}=") and "HttpOnly" in cookie and "Secure" in cookie
    # ---- IL-5: the path is /api (the Yahoo / ESPN connect and disconnect routes must see who is signed in)
    assert "samesite=lax" in cookie.lower() and "Path=/api;" in cookie and f"Max-Age={90 * 86400}" in cookie
    assert token not in r.text and token not in cookie
    api.cookies.clear()                                                     # the jar keeps a Secure one off http
    api.cookies.set(accounts.COOKIE, r.cookies[accounts.COOKIE])
    again = api.post("/api/account/verify", json={"token": token})          # single use
    assert again.status_code == 400 and again.json()["code"] == "link_invalid"
    assert q("select s.user_agent_family, s.expires_at - s.created_at from accounts.sessions s join accounts.users u "
             "on u.id = s.user_id where u.email = %s", email)[0][0] == "iPhone"

    st = api.get("/api/account/status").json()
    assert st["signed_in"] is True and st["email"] == email
    me = api.get("/api/account/me").json()
    assert me["email"] == email and me["leagues"] == [] and me["default_league"] is None

    body = {"leagues": [
        {"league": SCRUBS, "season": 2026, "name": "League of Scrubs", "team_id": 2, "team_name": "MacZaddy",
         "scoring_label": "10-team redraft · half PPR", "total_rosters": 10},
        {"league": MFL, "season": 2026, "name": "MFL 21861", "team_id": 4},
        {"league": ESPN, "season": 2026, "name": "ESPN 4242"},
        {"league": YAHOO, "season": 2026, "name": "Yahoo 4242", "team_id": 3}]}
    for _ in range(2):                                                       # saving twice changes nothing
        r = api.put("/api/account/leagues", json=body)
        assert r.status_code == 200 and r.json() == {"ok": True, "saved": 4}
    assert q("select count(*) from accounts.user_leagues ul join accounts.users u on u.id = ul.user_id "
             "where u.email = %s", email)[0][0] == 4
    keys = {r[0] for r in q("select league_key from accounts.leagues where league_key in (%s, %s, %s, %s)",
                            f"sleeper:2026:{SCRUBS}", "mfl:2026:21861", "espn:2026:4242", "yahoo:2026:461.l.4242")}
    assert len(keys) == 4
    me = api.get("/api/account/me").json()
    assert [(x["league"], x["league_key"], x["provider"], x["team_id"]) for x in me["leagues"]] == [
        (SCRUBS, f"sleeper:2026:{SCRUBS}", "sleeper", 2), (MFL, "mfl:2026:21861", "mfl", 4),
        (ESPN, "espn:2026:4242", "espn", None), (YAHOO, "yahoo:2026:461.l.4242", "yahoo", 3)]
    assert me["default_league"] == SCRUBS                     # the first league saved is the default
    scrubs = me["leagues"][0]
    assert scrubs["name"] == "League of Scrubs" and scrubs["team_name"] == "MacZaddy" and scrubs["total_rosters"] == 10

    # a team pick moves (the per-league pick), a name left out stays; a team cleared on purpose clears
    api.put("/api/account/leagues", json={"leagues": [{"league": SCRUBS, "season": 2026, "team_id": 5}]})
    api.put("/api/account/leagues", json={"leagues": [{"league": MFL, "season": 2026, "team_id": None}]})
    me = api.get("/api/account/me").json()
    assert me["leagues"][0]["team_id"] == 5 and me["leagues"][0]["name"] == "League of Scrubs"
    assert me["leagues"][1]["team_id"] is None

    # the default league, then removing it hands the default to the next
    assert api.put("/api/account/default", json={"league": YAHOO, "season": 2026}).status_code == 200
    assert api.get("/api/account/me").json()["default_league"] == YAHOO
    assert api.delete("/api/account/leagues/yahoo:2026:461.l.4242").status_code == 200
    me = api.get("/api/account/me").json()
    assert len(me["leagues"]) == 3 and me["default_league"] == SCRUBS
    assert api.delete("/api/account/leagues/yahoo:2026:461.l.4242").json()["code"] == "not_saved"
    assert api.put("/api/account/leagues", json={"leagues": [{"league": "fantrax:9"}]}).json()["code"] == "bad_league"

    # nothing secret anywhere in the log
    assert token not in caplog.text and email not in caplog.text


def test_a_second_user_never_sees_the_first(api):
    a = sign_in(api, addr("first"))
    a.put("/api/account/leagues", json={"leagues": [{"league": SCRUBS, "season": 2026, "name": "League of Scrubs",
                                                     "team_id": 2, "team_name": "MacZaddy"}]})
    a.put("/api/account/preferences", json={"scope": "global", "key": "stats.views", "value": [{"name": "A", "qs": "x=1"}]})
    a.put("/api/account/watchlist", json={"player_key": "00-0036963"})
    a_cookie = a.cookies.get(accounts.COOKIE)

    b = sign_in(api, addr("second"))
    me = b.get("/api/account/me").json()
    assert me["email"] == addr("second") and me["leagues"] == [] and me["preferences"] == [] and me["watchlist"] == []
    # B saves the same league with other words: A's row keeps A's words (the display fields are per user)
    b.put("/api/account/leagues", json={"leagues": [{"league": SCRUBS, "season": 2026, "name": "B's name", "team_id": 7}]})
    assert b.delete("/api/account/preferences", params={"key": "stats.views"}).status_code == 200
    api.cookies.clear()
    api.cookies.set(accounts.COOKIE, a_cookie)
    me = api.get("/api/account/me").json()
    assert me["email"] == addr("first") and me["leagues"][0]["name"] == "League of Scrubs"
    assert me["leagues"][0]["team_id"] == 2 and me["preferences"][0]["value"] == [{"name": "A", "qs": "x=1"}]
    assert q("select count(*) from accounts.leagues where league_key = %s", f"sleeper:2026:{SCRUBS}")[0][0] == 1


def test_preferences_by_scope_and_key(api):
    sign_in(api, addr("prefs"))
    views = [{"name": "WR · season", "qs": "position=WRTE&window=season"}]
    assert api.put("/api/account/preferences", json={"scope": "global", "key": "stats.views", "value": views}).status_code == 200
    assert api.put("/api/account/preferences", json={"scope": MFL, "key": "view", "value": "/team"}).status_code == 200
    api.put("/api/account/preferences", json={"scope": "global", "key": "stats.views", "value": views + views})
    me = api.get("/api/account/me").json()
    got = {(p["scope"], p["key"]): p["value"] for p in me["preferences"]}
    assert got == {("global", "stats.views"): views + views, (f"mfl:{accounts.current_season()}:21861", "view"): "/team"}
    r = api.put("/api/account/preferences", json={"scope": "global", "key": "Bad Key!", "value": 1})
    assert r.status_code == 400 and r.json()["code"] == "bad_key"
    r = api.put("/api/account/preferences", json={"scope": "global", "key": "big", "value": "x" * 9000})
    assert r.status_code == 400 and r.json()["code"] == "too_big"
    r = api.put("/api/account/preferences", json={"scope": "nope", "key": "k", "value": 1})
    assert r.status_code == 400 and r.json()["code"] == "bad_league"
    api.delete("/api/account/preferences", params={"scope": "global", "key": "stats.views"})
    assert [p["key"] for p in api.get("/api/account/me").json()["preferences"]] == ["view"]


def test_the_watchlist(api):
    sign_in(api, addr("watch"))
    for _ in range(2):
        assert api.put("/api/account/watchlist", json={"player_key": "00-0036963"}).status_code == 200
        assert api.put("/api/account/watchlist", json={"player_key": "00-0036963", "league": SCRUBS}).status_code == 200
    # ---- IL-5: GET /api/account/watchlist is the watchlist screen's answer now (league_lab_api/watchlist.py)
    w = api.get("/api/account/watchlist", params={"league": SCRUBS})
    assert w.status_code == 200 and w.json()["count"] == 1               # one player, saved with and without a league
    rows = api.get("/api/account/me").json()["watchlist"]
    assert len(rows) == 2 and {r["league"] for r in rows} == {None, SCRUBS}
    assert api.put("/api/account/watchlist", json={"player_key": "<script>"}).json()["code"] == "bad_player"
    api.delete("/api/account/watchlist", params={"player_key": "00-0036963"})
    assert [r["league"] for r in api.get("/api/account/me").json()["watchlist"]] == [SCRUBS]


def test_sign_out_and_sign_out_everywhere(api):
    sign_in(api, addr("devices"))
    phone = api.cookies.get(accounts.COOKIE)
    sign_in(api, addr("devices"))
    laptop = api.cookies.get(accounts.COOKIE)
    assert phone != laptop

    def me_with(cookie: str) -> int:
        api.cookies.clear()
        api.cookies.set(accounts.COOKIE, cookie)
        return api.get("/api/account/me").status_code

    assert me_with(phone) == 200 and me_with(laptop) == 200
    api.cookies.clear()
    api.cookies.set(accounts.COOKIE, phone)
    r = api.post("/api/account/logout", json={})
    assert r.json() == {"ok": True, "revoked": 1} and f'{accounts.COOKIE}=""' in r.headers["set-cookie"]
    assert me_with(phone) == 401 and me_with(laptop) == 200
    sign_in(api, addr("devices"))
    tablet = api.cookies.get(accounts.COOKIE)
    api.cookies.clear()
    api.cookies.set(accounts.COOKIE, tablet)
    assert api.post("/api/account/logout", json={"everywhere": True}).json()["revoked"] == 2
    assert me_with(laptop) == 401 and me_with(tablet) == 401


def test_an_expired_link_or_session_signs_nobody_in(api):
    email = addr("late")
    api.post("/api/account/login", json={"email": email})
    q("update accounts.login_links set expires_at = now() - interval '1 second' where user_email = %s returning 1", email)
    r = api.post("/api/account/verify", json={"token": link_token(email)})
    assert r.status_code == 400 and r.json()["code"] == "link_invalid"
    assert api.post("/api/account/verify", json={"token": "x" * 43}).json()["code"] == "link_invalid"
    assert api.post("/api/account/verify", json={"token": "short"}).json()["code"] == "link_invalid"
    sign_in(api, email)
    q("update accounts.sessions s set expires_at = now() - interval '1 second' from accounts.users u "
      "where u.id = s.user_id and u.email = %s returning 1", email)
    assert api.get("/api/account/me").status_code == 401
    assert api.get("/api/account/status").json()["signed_in"] is False


def test_delete_the_account(api):
    email = addr("leaving")
    sign_in(api, email)
    api.put("/api/account/leagues", json={"leagues": [{"league": MFL, "season": 2026, "team_id": 4}]})
    api.put("/api/account/preferences", json={"key": "stats.views", "value": []})
    api.put("/api/account/watchlist", json={"player_key": "00-0036963"})
    uid = q("select id from accounts.users where email = %s", email)[0][0]
    r = api.delete("/api/account")
    assert r.status_code == 200 and r.json() == {"ok": True, "deleted": True}
    assert api.get("/api/account/me").status_code == 401
    for t in ("sessions", "user_leagues", "preferences", "watchlist", "connections"):
        assert q(f"select count(*) from accounts.{t} where user_id = %s", uid)[0][0] == 0, t
    assert q("select count(*) from accounts.users where email = %s", email)[0][0] == 0
    assert q("select count(*) from accounts.login_links where user_email = %s", email)[0][0] == 0
    sign_in(api, email)                                                    # the address may come back: a new account
    assert api.get("/api/account/me").json()["leagues"] == []


def test_the_rate_limits(api, monkeypatch):
    email = addr("limit")
    for i in range(5):
        api.tick(5)
        assert api.post("/api/account/login", json={"email": email}).status_code == 202, i
    r = api.post("/api/account/login", json={"email": email})
    assert r.status_code == 429 and r.json()["code"] == "rate_limited" and r.headers["retry-after"] == "3600"
    assert len([m for m in accounts.STUB.sent if m["to"] == email]) == 5
    # 30 an hour from one IP address, whatever the addresses
    sent = 0
    for i in range(40):
        api.tick(5)
        r = api.post("/api/account/login", json={"email": addr(f"ip{i}")}, headers={"x-forwarded-for": "203.0.113.9"})
        if r.status_code == 202:
            sent += 1
        else:
            assert r.status_code == 429 and "from here" in r.json()["error"]
    assert sent == 30
    # the in-memory bucket: 20 checks a minute from one address, then a wait
    for _ in range(20):
        api.post("/api/account/verify", json={"token": "x" * 43}, headers={"x-forwarded-for": "198.51.100.7"})
    r = api.post("/api/account/verify", json={"token": "x" * 43}, headers={"x-forwarded-for": "198.51.100.7"})
    assert r.status_code == 429 and r.headers["retry-after"] == "60"
    api.tick(60)
    assert api.post("/api/account/verify", json={"token": "x" * 43},
                    headers={"x-forwarded-for": "198.51.100.7"}).json()["code"] == "link_invalid"
    # the day's cap (Resend's free tier: 100 a day)
    n = q("select count(*) from accounts.login_links where created_at > now() - interval '1 day'")[0][0]
    monkeypatch.setenv("LEAGUE_LAB_ACCOUNTS_DAILY_MAX", str(n))
    r = api.post("/api/account/login", json={"email": addr("daily")}, headers={"x-forwarded-for": "192.0.2.1"})
    assert r.status_code == 429 and "today" in r.json()["error"]
    # signed-in writes: 60 a minute per session
    monkeypatch.delenv("LEAGUE_LAB_ACCOUNTS_DAILY_MAX")
    sign_in(api, addr("writer"), **{"x-forwarded-for": "192.0.2.2"})
    codes = [api.put("/api/account/preferences", json={"key": "k", "value": i}).status_code for i in range(61)]
    assert codes[:60] == [200] * 60 and codes[60] == 429


def test_a_bad_address_and_a_failed_send(api, monkeypatch, caplog):
    r = api.post("/api/account/login", json={"email": "not an address"})
    assert r.status_code == 400 and r.json()["code"] == "bad_email"

    class Down:
        name = "resend"

        def send(self, *_a):
            raise OSError("connection refused")

    caplog.set_level(logging.DEBUG)
    monkeypatch.setattr(accounts, "mailer", lambda: Down())
    email = addr("unsent")
    r = api.post("/api/account/login", json={"email": email})
    assert r.status_code == 502 and r.json()["code"] == "mail_failed"
    assert q("select count(*) from accounts.login_links where user_email = %s", email)[0][0] == 0   # the link is gone
    assert "OSError" in caplog.text and email not in caplog.text and "signin=" not in caplog.text


def test_the_app_role_stays_read_only_outside_its_transaction(api):
    """The read pool never writes; the writer's transaction is explicit; the role may not truncate or reach outside."""
    with psycopg.connect(main._app_dsn(), autocommit=True) as conn:
        assert conn.execute("show default_transaction_read_only").fetchone()[0] == "on"
        with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
            conn.execute("insert into accounts.users (email) values ('ro@ik4.test')")
        for t in TABLES:
            assert conn.execute("select has_table_privilege(%s, 'delete'), has_table_privilege(%s, 'truncate')",
                                (f"accounts.{t}", f"accounts.{t}")).fetchone() == (True, False), t
        assert conn.execute("select has_schema_privilege('accounts', 'create')").fetchone()[0] is False
    sign_in(api, addr("pool"))
    with db.pool().connection() as pooled:
        assert pooled.execute("show transaction_read_only").fetchone()[0] == "on"
        assert all(pooled is not c for c in db._rw.values())


def test_the_script_is_idempotent_and_drops_nothing():
    sql = SQL_FILE.read_text().lower()
    code = "\n".join(line.split("--")[0] for line in sql.splitlines())
    assert not re.search(r"\b(drop|truncate)\s+(schema|table|role|column)", code) and not re.search(r"^\s*truncate", code, re.M)
    # ---- IM-4: the only alters keep every row (email becomes optional, a column and a check are added): test_im4
    assert all(a in ("alter table accounts.users alter column email drop not null",
                     "alter table accounts.users add column if not exists webauthn_handle bytea",
                     "alter table accounts.users add constraint users_webauthn_handle_len")
               for a in re.findall(r"alter table[^;\n]*?(?=;|\n)", code)), re.findall(r"alter table[^;\n]*", code)
    assert "create schema if not exists accounts" in sql
    assert sql.count("create table if not exists accounts.") == 10                                  # ---- IM-4: + 2
    assert "grant select, insert, update, delete on accounts.users" in sql
    assert "create role" not in sql and "alter role" not in sql


# ---------------------------------------------------------------- the web app's answers (recorded for web/e2e/ik4)
def test_record_web_fixtures(api, monkeypatch):
    """The shapes the e2e's in-test server copies (web/fixtures/ik4/): written when IK4_RECORD=1, else compared."""
    import os
    out: dict[str, object] = {}
    monkeypatch.setattr(accounts, "passkeys_ready", lambda: False)  # ---- IM-4: these are an email-only server's answers
    out["status_off.json"] = {"enabled": False, "reason": "no_mailer", "signed_in": False, "email": None,
                              "mailer": None, "session_days": 90}
    out["status_signed_out.json"] = api.get("/api/account/status").json()
    sign_in(api, addr("record"))
    api.put("/api/account/leagues", json={"leagues": [
        {"league": "9000000000000000001", "season": 2026, "name": "Test League", "team_id": 1, "team_name": "fixture_user",
         "scoring_label": "12-team redraft · half PPR", "total_rosters": 12},
        {"league": "mfl:70587", "season": 2026, "name": "MFL 70587", "team_id": 8, "total_rosters": 12}]})
    api.put("/api/account/preferences", json={"key": "stats.views", "value": [{"name": "WR · season", "qs": "position=WRTE"}]})
    me = api.get("/api/account/me").json()
    me["email"] = "manager@example.com"
    for row in me["leagues"]:
        row["added_at"] = "2026-10-05T12:00:00+00:00"
    for p in me["preferences"]:
        p["updated_at"] = "2026-10-05T12:00:00+00:00"
    me["created_at"] = "2026-10-05T12:00:00+00:00"
    out["me.json"] = me
    out["status_signed_in.json"] = {**api.get("/api/account/status").json(), "email": "manager@example.com"}
    d = Path(ROOT / "web" / "fixtures" / "ik4")
    if os.environ.get("IK4_RECORD") == "1":
        d.mkdir(parents=True, exist_ok=True)
        for name, body in out.items():
            (d / name).write_text(json.dumps(body, indent=1) + "\n")
    for name, body in out.items():
        assert json.loads((d / name).read_text()) == body, name
