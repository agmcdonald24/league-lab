"""Wave I-L, IL-5: accounts phase 2 — a Yahoo / ESPN connection follows the account (sealed at rest), the watchlist
screen's answer, and the providers' loose ends (the switches on `/api/providers`, the duplicate-id rule).

The account flow runs as IK-4's does: the clone's `accounts` schema, the stub mailer (`LEAGUE_LAB_ACCOUNTS=on`, no
Resend key), the app role writing in its own transaction. Every row belongs to an `@il5.test` address and is deleted
afterwards. Yahoo runs in IK-2's fixture mode (the code `fixture`, the guid FIXTUREGUID3); ESPN's private switch with
IK-1's synthetic cookies. No request leaves the process.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient
from league_lab import espn_client as E
from league_lab import platforms as P
from league_lab import player_ids as PI
from league_lab import yahoo_client as Y

from league_lab_api import accounts, connections, main, sealed, watchlist
from league_lab_api import yahoo_connect as YC
from league_lab_api.main import app
from league_lab_api.settings import ROOT

from .conftest import DB_OK, SCRUBS

DOMAIN = "il5.test"
SECRET = "il5-test-secret-0123456789"
FX = Path(__file__).with_name("fixtures")
S2 = "AEBx" + "Qz9%2B" * 20
SWID = "{0A1B2C3D-4E5F-4A6B-8C7D-9E0F1A2B3C4D}"
SQL_FILE = ROOT / "scripts" / "hosted_accounts.sql"
WEB_FIXTURES = ROOT / "web" / "fixtures" / "il5"
# three Scrubs free agents with recorded drawer cards (II-2's web fixtures); Zay Flowers (rostered by another team,
# Questionable on the clone) and Jonah Coleman (team 2's, Out on the clone)
WATCH = ["00-0038117", "00-0039880", "00-0038544", "00-0039064", "00-0041496"]


def _rw():
    conn = psycopg.connect(main._app_dsn(), autocommit=False)
    conn.execute("set transaction read write")
    return conn


def q(sql: str, *params):
    with _rw() as conn:
        return conn.execute(sql, params).fetchall()


def _cleanup() -> None:
    with _rw() as conn:
        conn.execute("delete from accounts.users where email like %s", (f"%@{DOMAIN}",))
        conn.execute("delete from accounts.login_links where user_email like %s", (f"%@{DOMAIN}",))
        conn.execute("delete from accounts.leagues l where not exists "
                     "(select 1 from accounts.user_leagues u where u.league_key = l.league_key)")


@pytest.fixture(scope="module")
def schema():
    if not DB_OK:
        pytest.skip("database not reachable")
    with psycopg.connect(main._app_dsn(), autocommit=True) as conn:
        if conn.execute("select to_regclass('accounts.connections')").fetchone()[0] is None:
            pytest.skip("the accounts schema is not on this database (run scripts/hosted_accounts.sql as its owner)")
    _cleanup()
    yield
    _cleanup()


@pytest.fixture
def api(monkeypatch, schema):
    """Gate off; accounts on with the stub mailer; Yahoo in fixture mode; ESPN private off unless a test turns it on."""
    monkeypatch.delenv("LEAGUE_LAB_APP_PASSWORD", raising=False)
    monkeypatch.delenv("LEAGUE_LAB_RESEND_API_KEY", raising=False)
    monkeypatch.setenv("LEAGUE_LAB_API_SECRET", SECRET)
    monkeypatch.setenv(accounts.ENV, "on")
    monkeypatch.setenv("LEAGUE_LAB_PUBLIC_URL", "https://isuckatfantasy.io")
    monkeypatch.setenv(Y.FIXTURES_ENV, str(FX / "yahoo"))
    monkeypatch.delenv(Y.CLIENT_ID_ENV, raising=False)
    monkeypatch.delenv(Y.CLIENT_SECRET_ENV, raising=False)
    monkeypatch.delenv(E.PRIVATE_ENV, raising=False)
    monkeypatch.setattr(YC, "_CLIENT", None)
    accounts.reset()
    with TestClient(app) as c:
        yield c
    accounts.reset()
    _cleanup()


@pytest.fixture
def espn_on(monkeypatch):
    monkeypatch.setenv(E.PRIVATE_ENV, "on")


def addr(name: str) -> str:
    return f"{name}@{DOMAIN}"


def link_token(email: str) -> str:
    msg = [m for m in accounts.STUB.sent if m["to"] == email][-1]
    return re.search(r"#signin=([A-Za-z0-9_-]+)", msg["text"]).group(1)


def sign_in(c: TestClient, email: str, *, keep: bool = False):
    """Ask for a link and open it. ``keep``: this device's other cookies stay (else a fresh browser)."""
    if not keep:
        c.cookies.clear()
    assert c.post("/api/account/login", json={"email": email}).status_code == 202
    r = c.post("/api/account/verify", json={"token": link_token(email)})
    assert r.status_code == 200, r.text
    return r


def connect_yahoo(c: TestClient):
    r = c.get("/api/yahoo/connect", follow_redirects=False)
    cb = c.get(r.headers["location"], follow_redirects=False)
    assert cb.status_code == 302 and cb.headers["location"] == "/leagues?platform=yahoo"
    assert c.cookies.get(YC.COOKIE)
    return cb


def rows(email: str):
    return q("select c.provider, c.external_user_id, c.kind, c.status, c.secret_enc, c.label from accounts.connections c "
             "join accounts.users u on u.id = c.user_id where u.email = %s order by c.provider", email)


# ---------------------------------------------------------------- connections
def test_yahoo_connection_row_round_trip_sealed_at_rest(api):
    sign_in(api, addr("yahoo1"))
    cb = connect_yahoo(api)
    got = rows(addr("yahoo1"))
    assert [(p, ext, kind, st) for p, ext, kind, st, _b, _l in got] == [("yahoo", "FIXTUREGUID3", "oauth", "active")]
    blob = bytes(got[0][4])
    assert b"fixture-refresh" not in blob and b"FIXTUREGUID3" not in blob          # encrypted, not encoded
    assert blob.startswith(b"v1.")
    assert connections.open_secret("yahoo", blob) == {"r": "fixture-refresh", "g": "FIXTUREGUID3"}
    assert connections.open_secret("espn", blob) is None                           # another purpose: nothing
    assert sealed.unseal(YC.COOKIE, blob.decode(), max_age_s=1e9) is None
    me = api.get("/api/account/me")
    assert me.status_code == 200
    conns = me.json()["connections"]
    assert [(x["provider"], x["external_user_id"], x["status"]) for x in conns] == [("yahoo", "FIXTUREGUID3", "active")]
    assert conns[0]["connected_at"]
    for text in (me.text, cb.text):
        assert "fixture-refresh" not in text and "fixture-access" not in text and "v1." not in text


def test_a_sign_in_on_another_device_restores_the_connection(api):
    sign_in(api, addr("yahoo2"))
    connect_yahoo(api)
    r = sign_in(api, addr("yahoo2"))                         # a fresh browser: no ll_yahoo
    cookies = r.headers.get_list("set-cookie")
    yc = [c for c in cookies if c.startswith(f"{YC.COOKIE}=")]
    assert yc and "HttpOnly" in yc[0] and "Path=/api" in yc[0] and f"Max-Age={60 * 86400}" in yc[0]
    s = YC.session_from_cookie(api.cookies.get(YC.COOKIE))
    assert s.refresh_token == "fixture-refresh" and s.guid == "FIXTUREGUID3" and s.access_token == ""
    assert api.get("/api/yahoo/status").json()["connected"] is True
    assert api.get("/api/yahoo/leagues").status_code == 200               # the re-issued cookie reads (a refresh)
    # the cookie gone while the session lives (60 days < 90): /me puts it back
    api.cookies.delete(YC.COOKIE)
    me = api.get("/api/account/me")
    assert any(c.startswith(f"{YC.COOKIE}=") for c in me.headers.get_list("set-cookie"))
    # with the cookie there, /me sets nothing
    assert not any(c.startswith(f"{YC.COOKIE}=") for c in api.get("/api/account/me").headers.get_list("set-cookie"))


def test_disconnect_deletes_the_row_and_another_device_does_not_bring_it_back(api):
    sign_in(api, addr("yahoo3"))
    connect_yahoo(api)
    device_b = TestClient(app)
    sign_in(device_b, addr("yahoo3"))                        # restored on B
    assert device_b.cookies.get(YC.COOKIE)
    out = api.post("/api/yahoo/disconnect")                  # A disconnects, signed in
    assert out.json() == {"connected": False, "removed": 1}
    assert rows(addr("yahoo3")) == []
    assert device_b.get("/api/account/me").json()["connections"] == []   # B's own cookie does not re-make the row
    assert rows(addr("yahoo3")) == []
    sign_in(api, addr("yahoo3"))
    assert api.cookies.get(YC.COOKIE) is None                # nothing to restore


def test_a_guest_connection_stays_a_cookie_and_joins_the_account_at_sign_in(api):
    before = q("select count(*) from accounts.connections")[0][0]
    api.cookies.clear()
    connect_yahoo(api)                                       # a guest: cookie only
    assert q("select count(*) from accounts.connections")[0][0] == before
    assert api.post("/api/yahoo/disconnect").json() == {"connected": False, "removed": 0}
    connect_yahoo(api)
    sign_in(api, addr("guest"), keep=True)                   # signing in on this device adopts it
    assert [r[0] for r in rows(addr("guest"))] == ["yahoo"]


def test_a_rotated_refresh_token_updates_the_row(api):
    sign_in(api, addr("rotate"))
    connect_yahoo(api)
    api.cookies.set(YC.COOKIE, YC.cookie_value(Y.YahooSession(refresh_token="fixture-refresh-2", guid="FIXTUREGUID3")),
                    path="/api")
    api.get("/api/account/me")
    assert connections.open_secret("yahoo", rows(addr("rotate"))[0][4])["r"] == "fixture-refresh-2"


def test_delete_account_cascades_to_connections(api):
    sign_in(api, addr("gone"))
    connect_yahoo(api)
    uid = q("select id from accounts.users where email = %s", addr("gone"))[0][0]
    assert api.delete("/api/account").status_code == 200
    assert q("select count(*) from accounts.connections where user_id = %s", uid)[0][0] == 0
    fk = q("select confdeltype from pg_constraint where conname = 'connections_user_id_fkey'")
    assert fk == [("c",)]                                    # on delete cascade, in the schema itself


def test_espn_private_connection_behind_its_switch(api, espn_on):
    sign_in(api, addr("espn"))
    r = api.post("/api/espn/connect", json={"espn_s2": S2, "swid": SWID})
    assert r.status_code == 200 and "with your account" in r.json()["words"]
    got = rows(addr("espn"))
    assert len(got) == 1 and got[0][0] == "espn" and got[0][2] == "cookie"
    assert re.fullmatch(r"espn-[0-9a-f]{16}", got[0][1])     # an HMAC of the SWID, never the SWID
    assert SWID.strip("{}").encode() not in bytes(got[0][4]) and S2.encode() not in bytes(got[0][4])
    assert connections.open_secret("espn", got[0][4]) == {"s2": S2, "swid": SWID}
    sign_in(api, addr("espn"))                               # another device
    assert api.get("/api/espn/status").json()["connected"] is True
    assert api.post("/api/espn/disconnect").json()["removed"] == 1
    assert rows(addr("espn")) == []


def test_espn_switch_off_writes_and_restores_nothing(api, monkeypatch, espn_on):
    sign_in(api, addr("espnoff"))
    api.post("/api/espn/connect", json={"espn_s2": S2, "swid": SWID})
    assert len(rows(addr("espnoff"))) == 1
    monkeypatch.setenv(E.PRIVATE_ENV, "off")
    r = sign_in(api, addr("espnoff"))
    assert not any(c.startswith("ll_espn=") for c in r.headers.get_list("set-cookie"))
    assert api.post("/api/espn/connect", json={"espn_s2": S2, "swid": SWID}).status_code == 404


def test_without_accounts_on_the_routes_are_unchanged(api, monkeypatch):
    monkeypatch.setenv(accounts.ENV, "off")
    accounts.reset()
    before = q("select count(*) from accounts.connections")[0][0]
    connect_yahoo(api)
    assert api.post("/api/yahoo/disconnect").json() == {"connected": False, "removed": 0}
    assert q("select count(*) from accounts.connections")[0][0] == before


def test_the_session_cookie_reaches_the_provider_routes(api):
    r = sign_in(api, addr("path"))
    c = next(x for x in r.headers.get_list("set-cookie") if x.startswith(f"{accounts.COOKIE}="))
    assert "Path=/api;" in c
    out = api.post("/api/account/logout", json={})
    gone = out.headers.get_list("set-cookie")
    assert any("Path=/api;" in x for x in gone) and any("Path=/api/account" in x for x in gone)   # the old path too


# ---------------------------------------------------------------- the watchlist screen
def _watch(api, keys, league=None):
    for k in keys:
        assert api.put("/api/account/watchlist", json={"player_key": k, "league": league}).status_code == 200


def test_watchlist_rows_in_a_league(api):
    sign_in(api, addr("watch"))
    _watch(api, WATCH)
    _watch(api, [WATCH[0]], league=SCRUBS)                   # saved twice (with and without a league): one row
    r = api.get("/api/account/watchlist", params={"league": SCRUBS, "team": 2})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] == len(WATCH) and body["shown"] == len(WATCH) and body["league"] == SCRUBS
    assert body["league_name"] and isinstance(body["week"], int)
    assert [p["player_key"] for p in body["players"]] == WATCH
    for p in body["players"]:
        assert p["read"] and p["player_name"] and p["position"] in ("QB", "RB", "WR", "TE")
        assert p["owner"]["words"] in ("Free agent", "On your team", "Not in this league's player pool") \
            or p["owner"]["words"].startswith("Rostered by ")
        assert p["proj_points"] is None or isinstance(p["proj_points"], float)
    kinds = {p["player_key"]: p["owner"]["kind"] for p in body["players"]}
    assert kinds["00-0038117"] == "free_agent" and kinds["00-0041496"] == "yours" and kinds["00-0039064"] == "rostered"
    # the same numbers as the drawer's card
    card = api.get(f"/api/player/{WATCH[0]}", params={"league": SCRUBS, "team": 2}).json()
    assert body["players"][0]["proj_points"] == card["proj_points"]
    assert body["players"][0]["player_name"] == card["player_name"]
    if os.environ.get("IL5_RECORD") == "1":                   # the e2e's fixture (web/fixtures/il5)
        WEB_FIXTURES.mkdir(parents=True, exist_ok=True)
        (WEB_FIXTURES / "watchlist.json").write_text(json.dumps(body, indent=1) + "\n")


def test_watchlist_defaults_to_the_default_league_and_says_a_bad_row(api):
    sign_in(api, addr("watch2"))
    assert api.put("/api/account/leagues", json={"leagues": [{"league": SCRUBS, "season": 2026, "team_id": 2}]}).status_code == 200
    _watch(api, [WATCH[1], "00-9999999"])
    body = api.get("/api/account/watchlist").json()
    assert body["league"] == SCRUBS
    good, bad = body["players"]
    assert good["read"] and not bad["read"] and bad["words"]
    assert api.get("/api/account/watchlist", params={"league": SCRUBS}).json()["count"] == 2


def test_watchlist_signed_out_and_off(api, monkeypatch):
    api.cookies.clear()
    assert api.get("/api/account/watchlist").json()["code"] == "signed_out"
    monkeypatch.setenv(accounts.ENV, "off")
    accounts.reset()
    assert api.get("/api/account/watchlist").status_code == 404


def test_owner_words():
    assert watchlist.owner({"rostered_by_roster_id": 4, "header": "WR · KC · on **Run Bijan Run** (macz)"}, 2)["words"] \
        == "Rostered by Run Bijan Run"
    assert watchlist.owner({"rostered_by_roster_id": 2, "header": "WR · KC · on **Mine**"}, 2)["kind"] == "yours"
    assert watchlist.owner({"rostered_by_roster_id": None, "is_free_agent": True}, 2)["words"] == "Free agent"
    assert watchlist.owner({"rostered_by_roster_id": None, "is_free_agent": False}, None)["kind"] == "not_in_pool"


# ---------------------------------------------------------------- providers under the switches
def test_verified_switch_flips_status_and_drops_the_tail(monkeypatch):
    monkeypatch.delenv(P.VERIFIED_ENV, raising=False)
    assert P.capabilities("espn")["status"] == P.capabilities("yahoo")["status"] == "unverified"
    monkeypatch.setenv(P.VERIFIED_ENV, " ESPN, yahoo ,nonsense")
    for prov in ("espn", "yahoo"):
        c = P.capabilities(prov)
        assert c["status"] == "supported" and "off" not in c
        assert not any(P.UNVERIFIED in v["words"] for v in c["features"].values())
        assert all(v["status"] == "partial" for v in c["features"].values())        # a feature keeps its own status
    assert P.capabilities("mfl")["status"] == "supported"
    monkeypatch.setenv(P.VERIFIED_ENV, "yahoo")
    assert P.capabilities("espn")["status"] == "unverified" and P.capabilities("yahoo")["status"] == "supported"


def test_espn_kill_switch_says_off(monkeypatch, client):
    monkeypatch.setenv(P.ESPN_SWITCH_ENV, "off")
    monkeypatch.setenv(P.VERIFIED_ENV, "espn")                 # off wins over verified
    c = P.capabilities("espn")
    assert c["status"] == "off" and c["off"] == "ESPN leagues: not available right now"
    body = client.get("/api/providers").json()
    espn = next(p for p in body["providers"] if p["provider"] == "espn")
    assert espn["status"] == "off" and espn["off"].endswith("not available right now")
    assert next(p for p in body["providers"] if p["provider"] == "yahoo")["status"] == "unverified"
    monkeypatch.setenv(P.ESPN_SWITCH_ENV, "on")
    assert P.capabilities("espn")["status"] == "supported"


def test_yahoo_not_configured_keeps_coming_soon(monkeypatch, client):
    for k in (Y.FIXTURES_ENV, Y.CLIENT_ID_ENV, Y.CLIENT_SECRET_ENV):
        monkeypatch.delenv(k, raising=False)
    body = client.get("/api/providers").json()
    assert body["yahoo_configured"] is False
    assert next(p for p in body["providers"] if p["provider"] == "yahoo")["status"] == "unverified"


# ---------------------------------------------------------------- the duplicate-id rule
HEAD = "mfl_id,gsis_id,sleeper_id,espn_id,name,position,team,yahoo_id\n"


@pytest.mark.parametrize("col,lookup,dupes", [
    ("mfl_id", lambda t, x: t.mfl_to_gsis(x), "mfl_dupes"),
    ("espn_id", lambda t, x: t.espn_to_gsis(x), "espn_dupes"),
    ("yahoo_id", lambda t, x: t.yahoo_to_gsis(x), "yahoo_dupes"),
])
def test_an_external_id_on_two_players_maps_to_nobody(tmp_path, caplog, monkeypatch, col, lookup, dupes):
    monkeypatch.setattr(PI, "_logged", set())
    cols = HEAD.strip().split(",")

    def line(**kw):
        return ",".join(str(kw.get(c, "")) for c in cols) + "\n"
    f = tmp_path / "ids.csv"
    f.write_text(HEAD + line(**{"gsis_id": "00-1", col: "500", "name": "A"}) + line(**{"gsis_id": "00-2", col: "500", "name": "B"})
                 + line(**{"gsis_id": "00-3", col: "600", "name": "C"}) + line(**{"gsis_id": "00-3", col: "600", "name": "C"})
                 + line(**{"gsis_id": "00-4", col: "700", "name": "D"}) + line(**{col: "700", "name": "E"}))
    with caplog.at_level(logging.WARNING, logger="league_lab.player_ids"):
        t = PI.read(f)
        PI.read(f)                                           # a reload: not logged again
    assert lookup(t, "500") is None and lookup(t, "700") is None      # two gsis ids / a gsis id and none: nobody
    assert lookup(t, "600") == "00-3"                                  # the same player twice: kept
    assert getattr(t, dupes) == {"500", "700"}
    assert PI.duplicates(t)[col] == ["500", "700"]
    warn = [r.getMessage() for r in caplog.records if col in r.getMessage()]
    assert len(warn) == 1 and "500: 00-1, 00-2" in warn[0] and "700: 00-4, no gsis id" in warn[0]


def test_the_fixture_id_table_has_no_duplicates():
    t = PI.read(FX / "ff" / "db_playerids.csv")
    assert PI.duplicates(t) == {"mfl_id": [], "espn_id": [], "yahoo_id": []}


def test_a_refused_refresh_marks_the_row_expired_and_it_is_not_restored(api):
    sign_in(api, addr("expired"))
    connect_yahoo(api)
    api.cookies.set(YC.COOKIE, YC.cookie_value(Y.YahooSession(refresh_token="dead-token", expires_at=1)), path="/api")
    r = api.get("/api/yahoo/leagues")                        # the read refreshes; Yahoo (the fixture) refuses
    assert any(c.startswith(f'{YC.COOKIE}=""') for c in r.headers.get_list("set-cookie"))
    assert rows(addr("expired"))[0][3] == "expired"
    api.cookies.delete(YC.COOKIE)
    me = api.get("/api/account/me")
    assert me.json()["connections"][0]["status"] == "expired"
    assert not any(c.startswith(f"{YC.COOKIE}=") for c in me.headers.get_list("set-cookie"))
    connect_yahoo(api)                                       # connecting again makes it active
    assert rows(addr("expired"))[0][3] == "active"


@pytest.mark.parametrize("name,env", [("providers_espn_off.json", {P.ESPN_SWITCH_ENV: "off"}),
                                      ("providers_verified.json", {P.VERIFIED_ENV: "espn,yahoo"})])
def test_record_the_providers_web_fixtures(client, monkeypatch, name, env):
    """/api/providers under each switch (Yahoo in fixture mode: configured) — the e2e's fixtures (IL5_RECORD=1)."""
    monkeypatch.setenv(Y.FIXTURES_ENV, str(FX / "yahoo"))
    monkeypatch.delenv(E.PRIVATE_ENV, raising=False)
    monkeypatch.delenv(P.ESPN_SWITCH_ENV, raising=False)
    monkeypatch.delenv(P.VERIFIED_ENV, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    body = client.get("/api/providers").json()
    status = {p["provider"]: p["status"] for p in body["providers"]}
    assert status["espn"] == ("off" if P.ESPN_SWITCH_ENV in env else "supported")
    if os.environ.get("IL5_RECORD") == "1":
        WEB_FIXTURES.mkdir(parents=True, exist_ok=True)
        (WEB_FIXTURES / name).write_text(json.dumps(body, indent=1) + "\n")
    assert json.loads((WEB_FIXTURES / name).read_text()) == body
