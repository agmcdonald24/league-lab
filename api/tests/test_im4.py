"""Wave I-M, IM-4: passkeys (WebAuthn) — a second way to sign in, with no email and no third party
(docs/ACCOUNTS.md § "Passkeys"; api/league_lab_api/passkeys.py; scripts/hosted_accounts.sql's IM-4 part).

A small **software authenticator** (`SoftKey`: an ES256 key from `cryptography`, CBOR from `cbor2` — both come with
py_webauthn) answers the server's options exactly as a browser hands an authenticator's answer back: attestation
`none`, a discoverable credential with the user handle the options carried, a signature counter. The server side is the
real one: the clone's `accounts` schema (scripts/hosted_accounts.sql applied by IK-4's fixture with the pipeline role),
the app role writing in its own transaction, the client on `https://isuckatfantasy.io` (so the Secure cookies are kept).
Every account a test makes is deleted afterwards (passkey-only accounts are found by their passkeys' label prefix or by
the `@im4.test` address).
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import secrets

import cbor2
import psycopg
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from league_lab_api import accounts, main, passkeys
from league_lab_api.main import app
from league_lab_api.settings import ROOT

from .conftest import DB_OK, SCRUBS

SQL_FILE = ROOT / "scripts" / "hosted_accounts.sql"
ORIGIN = "https://isuckatfantasy.io"
RP = "isuckatfantasy.io"
DOMAIN = "im4.test"
IPHONE = ("Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 "
          "Mobile/15E148 Safari/604.1")
MAC_CHROME = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 "
              "Safari/537.36")
MFL = "mfl:70587"


def b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def sha(b: bytes) -> bytes:
    return hashlib.sha256(b).digest()


class SoftKey:
    """One passkey on one device: what Chromium's virtual authenticator does, in forty lines."""

    def __init__(self, origin: str = ORIGIN):
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.cred_id = secrets.token_bytes(32)
        self.count = 0
        self.handle: bytes = secrets.token_bytes(32)          # replaced by the options' user id at create()
        self.origin = origin

    def _cose(self) -> bytes:
        n = self.key.public_key().public_numbers()
        return cbor2.dumps({1: 2, 3: -7, -1: 1, -2: n.x.to_bytes(32, "big"), -3: n.y.to_bytes(32, "big")})

    def create(self, options: dict, *, origin: str | None = None, rp_id: str | None = None, flags: int = 0x45) -> dict:
        """navigator.credentials.create(): flags UP | UV | AT; the user handle is kept (a discoverable credential)."""
        self.handle = b64d(options["user"]["id"])
        cdj = json.dumps({"type": "webauthn.create", "challenge": options["challenge"], "origin": origin or self.origin,
                          "crossOrigin": False}).encode()
        auth = (sha((rp_id or options["rp"]["id"]).encode()) + bytes([flags]) + self.count.to_bytes(4, "big")
                + bytes(16) + len(self.cred_id).to_bytes(2, "big") + self.cred_id + self._cose())
        att = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth})
        return {"id": b64e(self.cred_id), "rawId": b64e(self.cred_id), "type": "public-key",
                "response": {"clientDataJSON": b64e(cdj), "attestationObject": b64e(att),
                             "transports": ["internal", "hybrid", "warp-drive"]},
                "clientExtensionResults": {}, "authenticatorAttachment": "platform"}

    def get(self, options: dict, *, origin: str | None = None, rp_id: str | None = None, count: int | None = None,
            handle: bytes | None = None, tamper: bool = False) -> dict:
        """navigator.credentials.get(): the counter goes up by one unless told otherwise; ECDSA over authData || hash."""
        self.count = self.count + 1 if count is None else count
        cdj = json.dumps({"type": "webauthn.get", "challenge": options["challenge"],
                          "origin": origin or self.origin}).encode()
        auth = sha((rp_id or options["rpId"]).encode()) + bytes([0x05]) + self.count.to_bytes(4, "big")
        sig = self.key.sign(auth + sha(cdj), ec.ECDSA(hashes.SHA256()))
        if tamper:
            cdj = cdj.replace(b'"webauthn.get"', b'"webauthn.get" ')
        return {"id": b64e(self.cred_id), "rawId": b64e(self.cred_id), "type": "public-key",
                "response": {"clientDataJSON": b64e(cdj), "authenticatorData": b64e(auth), "signature": b64e(sig),
                             "userHandle": b64e(handle if handle is not None else self.handle)},
                "clientExtensionResults": {}}


# ---------------------------------------------------------------- the database
def _rw():
    conn = psycopg.connect(main._app_dsn(), autocommit=False)
    conn.execute("set transaction read write")
    return conn


def q(sql: str, *params):
    with _rw() as conn:
        return conn.execute(sql, params).fetchall()


MADE: list[str] = []          # the passkey-only accounts this module made (deleted afterwards)


def _cleanup() -> None:
    with _rw() as conn:
        if MADE:
            conn.execute("delete from accounts.users where id = any(%s::uuid[])", (MADE,))
        conn.execute("delete from accounts.users where email like %s", (f"%@{DOMAIN}",))
        conn.execute("delete from accounts.login_links where user_email like %s", (f"%@{DOMAIN}",))
        conn.execute("delete from accounts.leagues l where not exists "
                     "(select 1 from accounts.user_leagues u where u.league_key = l.league_key)")
    MADE.clear()


def _pipeline_dsn() -> str:
    from league_lab.config import get_settings
    return get_settings().pipeline_dsn()


@pytest.fixture(scope="module")
def schema():
    """scripts/hosted_accounts.sql applied twice (idempotent) with the pipeline role (the clone's owner), as IK-4's."""
    if not DB_OK:
        pytest.skip("database not reachable")
    try:
        with psycopg.connect(_pipeline_dsn(), autocommit=True, connect_timeout=5) as conn:
            for _ in range(2):
                with conn.transaction():
                    conn.execute(SQL_FILE.read_text())
    except psycopg.errors.InsufficientPrivilege:
        pass
    except psycopg.Error as exc:
        pytest.skip(f"cannot apply scripts/hosted_accounts.sql: {exc.__class__.__name__}")
    with psycopg.connect(main._app_dsn(), autocommit=True) as conn:
        if conn.execute("select to_regclass('accounts.passkeys')").fetchone()[0] is None:
            pytest.skip("the passkey tables are not on this database (run scripts/hosted_accounts.sql as its owner)")
    _cleanup()
    yield
    _cleanup()


def _env(monkeypatch, mode: str = "on") -> None:
    monkeypatch.delenv("LEAGUE_LAB_APP_PASSWORD", raising=False)
    monkeypatch.delenv("LEAGUE_LAB_RESEND_API_KEY", raising=False)
    monkeypatch.delenv(passkeys.ORIGINS_ENV, raising=False)
    monkeypatch.setenv("LEAGUE_LAB_API_SECRET", "im4-test-secret-0123456789")
    monkeypatch.setenv(accounts.ENV, mode)
    monkeypatch.setenv("LEAGUE_LAB_PUBLIC_URL", ORIGIN)


@pytest.fixture
def api(monkeypatch, schema):
    """Gate off, accounts on (passkeys + the stub mailer), the client on https://isuckatfantasy.io, a clock to move."""
    _env(monkeypatch)
    accounts.reset()
    t = [5000.0]
    monkeypatch.setattr(accounts, "clock", lambda: t[0])
    with TestClient(app, base_url=ORIGIN, headers={"Origin": ORIGIN, "User-Agent": IPHONE}) as c:
        c.tick = lambda s: t.__setitem__(0, t[0] + s)
        yield c
    accounts.reset()
    _cleanup()


def create_account(c: TestClient, key: SoftKey | None = None) -> SoftKey:
    """A fresh browser makes an account with one passkey (the "Create an account with a passkey" button)."""
    key = key or SoftKey()
    c.cookies.clear()
    r = c.post("/api/account/passkey/register/options")
    assert r.status_code == 200, r.text
    assert r.json()["purpose"] == "create"
    r = c.post("/api/account/passkey/register/verify", json={"credential": key.create(r.json()["options"])})
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True, "created": True, "email": None}
    MADE.append(q("select user_id from accounts.passkeys where credential_id = %s", key.cred_id)[0][0].__str__())
    return key


def sign_in(c: TestClient, key: SoftKey, **kw) -> dict:
    """"Sign in with a passkey" on a fresh browser."""
    c.cookies.clear()
    o = c.post("/api/account/passkey/login/options")
    assert o.status_code == 200, o.text
    r = c.post("/api/account/passkey/login/verify", json={"credential": key.get(o.json()["options"], **kw)})
    return {"status": r.status_code, **r.json()}


def options(c: TestClient, path: str = "login") -> dict:
    r = c.post(f"/api/account/passkey/{path}/options")
    assert r.status_code == 200, r.text
    return r.json()["options"]


# ---------------------------------------------------------------- no database
def test_origins_come_from_the_allow_list_only(monkeypatch):
    _env(monkeypatch, "auto")
    assert passkeys.allowed_origins() == [ORIGIN]
    assert passkeys.site_for(ORIGIN) == (ORIGIN, RP)
    assert passkeys.site_for("https://isuckatfantasy.io:443/") == (ORIGIN, RP)
    for bad in ("https://evil.example", "http://isuckatfantasy.io", "https://isuckatfantasy.io.evil.example",
                "https://xisuckatfantasy.io", "null", "", None, "https://isuckatfantasy.io/account",
                "http://localhost:8754", "javascript:alert(1)", "https://user@isuckatfantasy.io"):
        assert passkeys.site_for(bad) is None, bad
    monkeypatch.setenv(passkeys.ORIGINS_ENV, "https://isuckatfantasy.io, https://www.isuckatfantasy.io, "
                                             "http://plain.example, http://localhost:8754, not a url")
    assert passkeys.allowed_origins() == [ORIGIN, "https://www.isuckatfantasy.io"]       # https only outside the test switch
    assert passkeys.site_for("https://www.isuckatfantasy.io") == ("https://www.isuckatfantasy.io", RP)   # one rp id
    monkeypatch.setenv(accounts.ENV, "on")                                              # the test switch
    assert passkeys.site_for("http://localhost:8754") == ("http://localhost:8754", "localhost")
    assert passkeys.site_for("http://localhost:5173") == ("http://localhost:5173", "localhost")
    assert passkeys.site_for("http://127.0.0.1:8754") is None                           # an IP is never an rp id
    monkeypatch.setenv(passkeys.ORIGINS_ENV, "garbage")
    assert passkeys.allowed_origins() == [ORIGIN]                                       # a bad list falls back to the site


def test_labels_are_fixed_words_never_the_user_agent():
    assert passkeys.label_for(IPHONE) == "iPhone · Safari"
    assert passkeys.label_for(MAC_CHROME) == "Mac · Chrome"
    assert passkeys.label_for("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/129.0 Safari/537.36 "
                              "Edg/129.0") == "Windows · Edge"
    assert passkeys.label_for("Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/129 Mobile Safari/537.36") == \
        "Android · Chrome"
    assert passkeys.label_for("Mozilla/5.0 (X11; Linux x86_64; rv:131.0) Gecko/20100101 Firefox/131.0") == "Linux · Firefox"
    assert passkeys.label_for("<script>alert(1)</script>") == "Passkey"
    assert passkeys.label_for(None) == "Passkey"


# ---------------------------------------------------------------- the switch (item 3)
def test_the_status_matrix(monkeypatch, schema):
    """no secret / tables missing / passkeys only / both / passkey tables missing with a mailer / off."""
    with TestClient(app, base_url=ORIGIN) as c:
        def status() -> dict:
            accounts.reset()
            r = c.get("/api/account/status")
            assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
            return r.json()

        _env(monkeypatch, "auto")
        monkeypatch.delenv("LEAGUE_LAB_API_SECRET")
        s = status()
        assert (s["enabled"], s["reason"], s["methods"]) == (False, "no_secret", [])

        monkeypatch.setenv("LEAGUE_LAB_API_SECRET", "im4-test-secret-0123456789")
        s = status()                                                    # auto, a secret, the tables: passkeys only
        assert (s["enabled"], s["reason"], s["methods"], s["mailer"]) == (True, None, ["passkey"], None)
        assert s["why"] == {"passkey": None, "email": "no_mailer"} and s["passkey_home"] == ORIGIN
        assert s["passkey_here"] is True and s["signed_in"] is False and s["email"] is None
        r = c.post("/api/account/login", json={"email": f"x@{DOMAIN}"})
        assert r.status_code == 404 and r.json()["code"] == "email_off"   # the emailed link needs a mailer
        assert "Use a passkey" in r.json()["error"]

        monkeypatch.setenv("LEAGUE_LAB_RESEND_API_KEY", "re_test_not_a_key")
        s = status()                                                    # both
        assert (s["enabled"], s["methods"], s["mailer"]) == (True, ["passkey", "email"], "resend")

        # the nightly has not applied IM-4's SQL yet: the tables of phase 1 only
        real = accounts.READY_SQL
        monkeypatch.setattr(accounts, "READY_SQL", real.split(", coalesce(has_table_privilege(to_regclass("
                                                                    "'accounts.passkeys')")[0] + ", false")
        s = status()
        assert (s["enabled"], s["methods"], s["why"]["passkey"]) == (True, ["email"], "not_ready")
        r = c.post("/api/account/passkey/login/options", headers={"Origin": ORIGIN})
        assert r.status_code == 404 and r.json()["code"] == "passkeys_off"          # no 500
        monkeypatch.delenv("LEAGUE_LAB_RESEND_API_KEY")
        s = status()
        assert (s["enabled"], s["reason"], s["methods"]) == (False, "not_ready", [])
        assert s["why"] == {"passkey": "not_ready", "email": "no_mailer"}
        assert c.post("/api/account/passkey/register/options", headers={"Origin": ORIGIN}).json()["code"] == "accounts_off"

        # no accounts schema at all
        monkeypatch.setattr(accounts, "READY_SQL", "select false, false")
        s = status()
        assert (s["enabled"], s["reason"], s["methods"]) == (False, "not_ready", [])
        monkeypatch.setattr(accounts, "READY_SQL", real)

        monkeypatch.setenv(accounts.ENV, "off")                         # off wins over everything
        monkeypatch.setenv("LEAGUE_LAB_RESEND_API_KEY", "re_test_not_a_key")
        s = status()
        assert (s["enabled"], s["reason"], s["methods"]) == (False, "off", [])
        assert c.post("/api/account/passkey/login/options", headers={"Origin": ORIGIN}).json()["code"] == "accounts_off"
    accounts.reset()


def test_status_says_when_this_site_cannot_use_passkeys(monkeypatch, schema):
    _env(monkeypatch, "auto")
    accounts.reset()
    with TestClient(app, base_url="https://isuckatfantasy.onrender.com") as c:
        s = c.get("/api/account/status").json()
        assert s["enabled"] is True and s["methods"] == ["passkey"] and s["passkey_here"] is False
        r = c.post("/api/account/passkey/register/options", headers={"Origin": "https://isuckatfantasy.onrender.com"})
        assert r.status_code == 400 and r.json() == {
            "error": "Passkeys work on isuckatfantasy.io only. Open https://isuckatfantasy.io/account to use one.",
            "detail": "Passkeys work on isuckatfantasy.io only. Open https://isuckatfantasy.io/account to use one.",
            "code": "passkey_wrong_site"}
        assert passkeys.COOKIE not in r.headers.get("set-cookie", "")
    accounts.reset()


# ---------------------------------------------------------------- the flow (items 1, 2, 4)
def test_create_sign_out_sign_in_and_the_leagues_come_back(api, caplog):
    caplog.set_level(logging.DEBUG)
    s = api.get("/api/account/status").json()
    assert s["methods"] == ["passkey", "email"] and s["passkey_here"] is True

    # one tap: the options for a new account
    r = api.post("/api/account/passkey/register/options")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    o = r.json()["options"]
    assert o["rp"] == {"name": "isuckatfantasy", "id": RP}
    assert o["attestation"] == "none" and o["excludeCredentials"] == []
    assert o["authenticatorSelection"]["residentKey"] == "required"
    assert o["authenticatorSelection"]["userVerification"] == "preferred"
    assert {p["alg"] for p in o["pubKeyCredParams"]} >= {-7, -8, -257}
    assert len(b64d(o["user"]["id"])) == 32 and o["user"]["name"].startswith("isuckatfantasy · ")
    assert len(b64d(o["challenge"])) == 32
    cookie = r.headers["set-cookie"]
    assert cookie.startswith(f"{passkeys.COOKIE}=") and "HttpOnly" in cookie and "Secure" in cookie
    assert "SameSite=strict" in cookie and "Path=/api/account/passkey" in cookie and "Max-Age=300" in cookie
    row = q("select purpose, user_id, rp_id, origin, expires_at - created_at, used_at from accounts.passkey_challenges "
            "where challenge_hash = %s", sha(b64d(o["challenge"])))
    assert row and row[0][:4] == ("create", None, RP, ORIGIN) and row[0][4].total_seconds() == 300 and row[0][5] is None
    assert q("select count(*) from accounts.passkey_challenges where challenge_hash = %s", b64d(o["challenge"]))[0][0] == 0

    key = SoftKey()
    r = api.post("/api/account/passkey/register/verify", json={"credential": key.create(o)})
    assert r.status_code == 200 and r.json() == {"ok": True, "created": True, "email": None}, r.text
    assert f"{accounts.COOKIE}=" in r.headers["set-cookie"] and f'{passkeys.COOKIE}=""' in r.headers["set-cookie"]
    uid = q("select user_id from accounts.passkeys where credential_id = %s", key.cred_id)[0][0]
    MADE.append(str(uid))
    user = q("select email, webauthn_handle from accounts.users where id = %s", uid)[0]
    assert user[0] is None and bytes(user[1]) == key.handle                     # no email; the handle the options carried
    pk = q("select label, sign_count, transports, backed_up, last_used_at from accounts.passkeys where user_id = %s", uid)
    assert pk == [("iPhone · Safari", 0, ["hybrid", "internal"], False, None)]

    st = api.get("/api/account/status").json()
    assert st["signed_in"] is True and st["email"] is None
    me = api.get("/api/account/me").json()
    assert me["email"] is None and me["leagues"] == [] and me["sign_in"] == {"passkeys": 1, "email": False}
    assert [(p["label"], p["last_used_at"], p["synced"]) for p in me["passkeys"]] == [("iPhone · Safari", None, False)]
    assert set(me["passkeys"][0]) == {"id", "label", "created_at", "last_used_at", "synced"}       # never a key or an id

    # this browser's leagues, default, a preference and a watched player go to the account (the phase-1 routes)
    assert api.put("/api/account/leagues", json={"leagues": [
        {"league": SCRUBS, "season": 2026, "name": "League of Scrubs", "team_id": 2, "team_name": "MacZaddy"},
        {"league": MFL, "season": 2026, "name": "MFL 70587", "team_id": 1, "default": True}]}).status_code == 200
    assert api.put("/api/account/preferences", json={"key": "stats.views", "value": [{"name": "WR", "qs": "p=WR"}]}).status_code == 200
    assert api.put("/api/account/watchlist", json={"player_key": "00-0036963"}).status_code == 200

    # sign out, then a fresh browser signs in with the passkey: everything comes back
    assert api.post("/api/account/logout", json={}).json() == {"ok": True, "revoked": 1}
    assert api.get("/api/account/me").status_code == 401
    got = sign_in(api, key)
    assert got == {"status": 200, "ok": True, "email": None}
    me = api.get("/api/account/me").json()
    assert [(lg["league"], lg["team_id"], lg["is_default"]) for lg in me["leagues"]] == [(MFL, 1, True), (SCRUBS, 2, False)]
    assert me["default_league"] == MFL and me["preferences"][0]["value"] == [{"name": "WR", "qs": "p=WR"}]
    assert [w["player_key"] for w in me["watchlist"]] == ["00-0036963"]
    assert me["passkeys"][0]["last_used_at"] is not None
    assert q("select sign_count from accounts.passkeys where user_id = %s", uid)[0][0] == 1
    assert q("select count(*) from accounts.sessions where user_id = %s and revoked_at is null", uid)[0][0] == 1

    # nothing secret in the log: no challenge, no ceremony cookie, no session
    sid = accounts.session_id_from(api.cookies.get(accounts.COOKIE))
    assert sid and sid not in caplog.text and o["challenge"] not in caplog.text
    assert passkeys.COOKIE not in caplog.text and api.cookies.get(accounts.COOKIE) not in caplog.text


def test_a_replayed_or_expired_challenge_is_refused(api):
    key = create_account(api)
    api.cookies.clear()
    o = options(api)
    answer = key.get(o)
    r = api.post("/api/account/passkey/login/verify", json={"credential": answer})
    assert r.status_code == 200
    api.cookies.delete(accounts.COOKIE)
    r = api.post("/api/account/passkey/login/verify", json={"credential": answer})          # the same answer again
    assert r.status_code == 400 and r.json()["code"] == "passkey_challenge"
    assert r.json()["error"] == "That passkey request is not one we made, or it was already used. Start again."
    assert api.get("/api/account/me").status_code == 401

    o = options(api)                                                         # older than 5 minutes
    q("update accounts.passkey_challenges set expires_at = now() - interval '1 second' where challenge_hash = %s "
      "returning 1", sha(b64d(o["challenge"])))
    r = api.post("/api/account/passkey/login/verify", json={"credential": key.get(o)})
    assert r.status_code == 400 and r.json()["code"] == "passkey_expired"
    assert r.json()["error"] == "That took longer than 5 minutes. Start again."

    forged = dict(o, challenge=b64e(secrets.token_bytes(32)))                # a challenge the server never made
    r = api.post("/api/account/passkey/login/verify", json={"credential": key.get(forged)})
    assert r.json()["code"] == "passkey_challenge"
    o = options(api, "login")                                                # a sign-in challenge used to register
    r = api.post("/api/account/passkey/register/verify", json={"credential": SoftKey().create(
        {"challenge": o["challenge"], "rp": {"id": RP}, "user": {"id": b64e(secrets.token_bytes(32))}})})
    assert r.status_code == 400 and r.json()["code"] == "passkey_challenge"
    # a failed answer spends its challenge too (single use, whatever the outcome)
    o = options(api)
    bad = key.get(o, tamper=True)
    assert api.post("/api/account/passkey/login/verify", json={"credential": bad}).json()["code"] == "passkey_refused"
    assert api.post("/api/account/passkey/login/verify", json={"credential": key.get(o)}).json()["code"] == \
        "passkey_challenge"
    assert api.get("/api/account/me").status_code == 401


def test_another_browser_cannot_finish_a_ceremony(api):
    key = create_account(api)
    api.cookies.clear()
    o = options(api)
    api.cookies.clear()                                                      # the ceremony cookie is gone
    r = api.post("/api/account/passkey/login/verify", json={"credential": key.get(o)})
    assert r.status_code == 400 and r.json()["code"] == "passkey_browser"
    assert r.json()["error"] == "That passkey request was started in another browser or tab. Start again here."
    o = options(api)
    api.cookies.set(passkeys.COOKIE, secrets.token_urlsafe(32), domain=RP, path=passkeys.COOKIE_PATH)
    assert api.post("/api/account/passkey/login/verify", json={"credential": key.get(o)}).json()["code"] == \
        "passkey_browser"


def test_a_wrong_origin_or_rp_id_is_refused(api):
    key = create_account(api)
    api.cookies.clear()
    words = "Passkeys work on isuckatfantasy.io only. Open https://isuckatfantasy.io/account to use one."
    for path in ("register", "login"):                                       # the options: another site's Origin
        r = api.post(f"/api/account/passkey/{path}/options", headers={"Origin": "https://evil.example"})
        assert r.status_code in (400, 403), r.text
        assert r.json()["code"] in ("passkey_wrong_site", "cross_site")
    r = api.post("/api/account/passkey/login/options", headers={"Origin": "https://evil.example",
                                                                 "Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 400 and r.json()["error"] == words              # same-origin to the guard, not on the list
    # the device signed for another origin (a phishing page relaying our challenge)
    o = options(api)
    r = api.post("/api/account/passkey/login/verify", json={"credential": key.get(o, origin="https://evil.example")})
    assert r.status_code == 400 and r.json()["code"] == "passkey_wrong_site" and r.json()["error"] == words
    # the device signed for another rp id
    o = options(api)
    r = api.post("/api/account/passkey/login/verify", json={"credential": key.get(o, rp_id="evil.example")})
    assert r.status_code == 400 and r.json()["code"] == "passkey_wrong_site"
    # the answer posted from another page than the one that asked
    o = options(api)
    r = api.post("/api/account/passkey/login/verify", json={"credential": key.get(o)},
                 headers={"Origin": "https://www.isuckatfantasy.io", "Sec-Fetch-Site": "same-site"})
    assert r.status_code in (400, 403) and r.json()["code"] in ("passkey_wrong_site", "cross_site")
    # registration: another origin, another rp id
    api.cookies.clear()
    r = api.post("/api/account/passkey/register/options")
    k2 = SoftKey()
    r = api.post("/api/account/passkey/register/verify",
                 json={"credential": k2.create(r.json()["options"], origin="https://isuckatfantasy.io.evil.example")})
    assert r.json()["code"] == "passkey_wrong_site"
    r = api.post("/api/account/passkey/register/options")
    r = api.post("/api/account/passkey/register/verify",
                 json={"credential": k2.create(r.json()["options"], rp_id="evil.example")})
    assert r.json()["code"] == "passkey_wrong_site"
    assert q("select count(*) from accounts.passkeys where credential_id = %s", k2.cred_id)[0][0] == 0
    assert api.get("/api/account/me").status_code == 401


def test_a_cloned_authenticator_is_refused(api, caplog):
    key = create_account(api)
    assert sign_in(api, key, count=7)["status"] == 200
    assert q("select sign_count from accounts.passkeys where credential_id = %s", key.cred_id)[0][0] == 7
    caplog.set_level(logging.INFO)
    for count in (7, 3):                                                     # the same counter, then one going back
        got = sign_in(api, key, count=count)
        assert got["status"] == 400 and got["code"] == "passkey_cloned", got
        assert got["error"].startswith("This passkey's counter went backwards, which can mean it was copied.")
        assert api.get("/api/account/me").status_code == 401
    assert "counter that did not go up" in caplog.text
    assert q("select sign_count from accounts.passkeys where credential_id = %s", key.cred_id)[0][0] == 7
    assert sign_in(api, key, count=8)["status"] == 200


def test_unknown_passkeys_bad_signatures_and_garbage(api):
    key = create_account(api)
    got = sign_in(api, SoftKey())                                            # a passkey no account has
    assert got["status"] == 400 and got["code"] == "passkey_unknown"
    got = sign_in(api, key, handle=secrets.token_bytes(32))                 # the right key, another account's handle
    assert got["code"] == "passkey_unknown"
    other = SoftKey()
    other.cred_id, other.handle = key.cred_id, key.handle                    # someone else's key, our credential id
    got = sign_in(api, other)
    assert got["status"] == 400 and got["code"] == "passkey_refused"
    assert got["error"] == "Your device's answer did not check out, so nothing changed. Try again."
    for junk in ({}, {"type": "public-key"}, {"id": "x", "rawId": "x", "type": "public-key", "response": {}},
                 {"id": "x", "rawId": "x", "type": "public-key", "response": {"clientDataJSON": "!!!"}},
                 {"id": "x", "rawId": "x", "type": "public-key", "response": {"clientDataJSON": "x" * 40000}}):
        r = api.post("/api/account/passkey/login/verify", json={"credential": junk})
        assert r.status_code == 400 and r.json()["code"] == "passkey_bad", junk
    assert api.post("/api/account/passkey/login/verify", json={}).json()["code"] == "passkey_bad"
    assert api.get("/api/account/me").status_code == 401


def test_add_list_and_remove_passkeys(api):
    phone = create_account(api)
    uid = MADE[-1]
    # add a second one (a laptop), signed in on this device
    api.headers["User-Agent"] = MAC_CHROME
    r = api.post("/api/account/passkey/register/options")
    o = r.json()["options"]
    assert r.json()["purpose"] == "add" and b64d(o["user"]["id"]) == phone.handle            # the same account handle
    assert [b64d(x["id"]) for x in o["excludeCredentials"]] == [phone.cred_id]
    assert o["excludeCredentials"][0]["transports"] == ["hybrid", "internal"]
    laptop = SoftKey()
    r = api.post("/api/account/passkey/register/verify", json={"credential": laptop.create(o)})
    assert r.status_code == 200 and r.json()["added"] is True and r.json()["passkey"]["label"] == "Mac · Chrome"
    labels = [p["label"] for p in api.get("/api/account/me").json()["passkeys"]]
    assert labels == ["iPhone · Safari", "Mac · Chrome"]
    # the same passkey twice: refused
    r = api.post("/api/account/passkey/register/options")
    r = api.post("/api/account/passkey/register/verify", json={"credential": laptop.create(r.json()["options"])})
    assert r.status_code == 409 and r.json()["code"] == "passkey_taken"
    # an add started for one account cannot be finished by another session
    r = api.post("/api/account/passkey/register/options")
    o = r.json()["options"]
    api.cookies.delete(accounts.COOKIE)
    r = api.post("/api/account/passkey/register/verify", json={"credential": SoftKey().create(o)})
    assert r.status_code == 401 and r.json()["code"] == "signed_out"
    # the laptop signs in and removes the phone's passkey; the last one cannot go
    assert sign_in(api, laptop)["status"] == 200
    ids = {p["label"]: p["id"] for p in api.get("/api/account/me").json()["passkeys"]}
    assert api.delete(f"/api/account/passkeys/{ids['iPhone · Safari']}").json() == {"ok": True, "removed": 1}
    assert sign_in(api, phone)["code"] == "passkey_unknown"                  # it opens nothing now
    assert sign_in(api, laptop)["status"] == 200
    r = api.delete(f"/api/account/passkeys/{ids['Mac · Chrome']}")
    assert r.status_code == 409 and r.json()["code"] == "last_sign_in"
    assert r.json()["error"] == ("This passkey is the only way into your account: without it nobody could sign in to "
                                 "it again. Add another passkey first, or delete the account.")
    assert api.delete("/api/account/passkeys/not-a-uuid").json()["code"] == "not_saved"
    assert api.delete(f"/api/account/passkeys/{ids['iPhone · Safari']}").status_code == 404
    assert q("select count(*) from accounts.passkeys where user_id = %s", uid)[0][0] == 1


def test_an_email_account_adds_a_passkey_and_may_remove_it(api):
    """The emailed link's account adds a passkey (it gets a handle then); with a mailer its email is a way in too."""
    import re
    email = f"pk@{DOMAIN}"
    api.cookies.clear()
    assert api.post("/api/account/login", json={"email": email}).status_code == 202
    token = re.search(r"#signin=([A-Za-z0-9_-]+)", [m for m in accounts.STUB.sent if m["to"] == email][-1]["text"]).group(1)
    assert api.post("/api/account/verify", json={"token": token}).status_code == 200
    assert q("select webauthn_handle from accounts.users where email = %s", email)[0][0] is None
    o = api.post("/api/account/passkey/register/options").json()["options"]
    assert o["user"]["name"] == email
    key = SoftKey()
    assert api.post("/api/account/passkey/register/verify", json={"credential": key.create(o)}).json()["added"] is True
    assert bytes(q("select webauthn_handle from accounts.users where email = %s", email)[0][0]) == key.handle
    me = api.get("/api/account/me").json()
    assert me["email"] == email and me["sign_in"] == {"passkeys": 1, "email": True}
    assert sign_in(api, key) == {"status": 200, "ok": True, "email": email}
    assert api.delete(f"/api/account/passkeys/{me['passkeys'][0]['id']}").json()["removed"] == 1


def test_an_account_without_email_through_every_account_route(api):
    create_account(api)
    uid = MADE[-1]
    for method, path, body in (
            ("PUT", "/api/account/leagues", {"leagues": [{"league": MFL, "season": 2026, "team_id": 1}]}),
            ("PUT", "/api/account/leagues", {"leagues": [{"league": SCRUBS, "season": 2026, "team_id": 2}]}),
            ("PUT", "/api/account/default", {"league": SCRUBS, "season": 2026}),
            ("PUT", "/api/account/preferences", {"key": "theme", "value": "dark"}),
            ("DELETE", "/api/account/preferences?key=theme", None),
            ("PUT", "/api/account/watchlist", {"player_key": "00-0036963"}),
            ("DELETE", f"/api/account/leagues/{MFL}?season=2026", None),
            ("GET", "/api/account/me", None),
            ("GET", "/api/account/status", None)):
        r = api.request(method, path, json=body)
        assert r.status_code == 200, (path, r.text)
    w = api.get("/api/account/watchlist", params={"league": SCRUBS})
    assert w.status_code == 200 and w.json()["count"] == 1
    assert api.delete("/api/account/watchlist", params={"player_key": "00-0036963"}).status_code == 200
    assert api.post("/api/account/logout", json={"everywhere": True}).json()["revoked"] == 1
    key = SoftKey()
    key2 = create_account(api, key)
    uid2 = MADE[-1]
    r = api.delete("/api/account")
    assert r.status_code == 200 and r.json() == {"ok": True, "deleted": True}
    for t in ("passkeys", "sessions", "user_leagues", "preferences", "watchlist", "passkey_challenges"):
        assert q(f"select count(*) from accounts.{t} where user_id = %s", uid2)[0][0] == 0, t
    assert sign_in(api, key2)["code"] == "passkey_unknown"
    assert q("select count(*) from accounts.users where id = %s", uid)[0][0] == 1          # the other account stays


# ---------------------------------------------------------------- safe on a public site (item 5)
def test_every_state_changing_account_route_refuses_another_site(api):
    create_account(api)
    hostile = ({"Origin": "https://evil.example"}, {"Origin": "https://evil.example", "Sec-Fetch-Site": "cross-site"},
               {"Sec-Fetch-Site": "cross-site", "Origin": "null"}, {"Origin": "null"})
    routes = (("POST", "/api/account/login", {"email": f"a@{DOMAIN}"}), ("POST", "/api/account/verify", {"token": "x" * 43}),
              ("POST", "/api/account/logout", {}), ("PUT", "/api/account/leagues", {"leagues": []}),
              ("DELETE", f"/api/account/leagues/{MFL}", None), ("PUT", "/api/account/default", {"league": MFL}),
              ("PUT", "/api/account/preferences", {"key": "k", "value": 1}), ("DELETE", "/api/account/preferences?key=k", None),
              ("PUT", "/api/account/watchlist", {"player_key": "00-0036963"}),
              ("DELETE", "/api/account/watchlist?player_key=00-0036963", None), ("DELETE", "/api/account", None),
              ("POST", "/api/account/passkey/register/options", None), ("POST", "/api/account/passkey/register/verify", {}),
              ("POST", "/api/account/passkey/login/options", None), ("POST", "/api/account/passkey/login/verify", {}),
              ("DELETE", "/api/account/passkeys/00000000-0000-0000-0000-000000000000", None))
    for method, path, body in routes:
        for h in hostile:
            r = api.request(method, path, json=body, headers=h)
            assert r.status_code == 403 and r.json()["code"] == "cross_site", (method, path, h, r.text)
            assert r.json()["error"] == ("This request came from another website, so it was refused. Open "
                                         "isuckatfantasy.io and try again.")
    assert api.get("/api/account/me").status_code == 200                    # still signed in: nothing happened
    # allowed: the site itself (Origin on the list, or the request's own host), a same-origin fetch, a non-browser
    for h in ({"Origin": ORIGIN}, {"Sec-Fetch-Site": "same-origin"}, {"Sec-Fetch-Site": "none"}, {}):
        api.headers.pop("Origin", None)
        r = api.put("/api/account/preferences", json={"key": "k", "value": 1}, headers=h)
        assert r.status_code == 200, (h, r.text)
    with TestClient(app, base_url="https://isuckatfantasy.onrender.com") as other:      # Render's own address
        r = other.post("/api/account/logout", json={}, headers={"Origin": "https://isuckatfantasy.onrender.com"})
        assert r.status_code == 200
        r = other.post("/api/account/logout", json={}, headers={"Origin": "https://isuckatfantasy.onrender.com",
                                                                "Sec-Fetch-Site": "cross-site"})
        assert r.status_code == 403


def test_the_ceremonies_are_rate_limited(api):
    create_account(api)                                                       # 1 of the 10 registrations this hour
    api.cookies.clear()
    codes = [api.post("/api/account/passkey/register/options").status_code for _ in range(10)]
    assert codes == [200] * 9 + [429]
    r = api.post("/api/account/passkey/register/options")
    assert r.json() == {"error": "Too many new passkeys from here. Try again in an hour.",
                        "detail": "Too many new passkeys from here. Try again in an hour.", "code": "rate_limited"}
    assert r.headers["retry-after"] == "3600"
    other = api.post("/api/account/passkey/register/options", headers={"x-forwarded-for": "198.51.100.4"})
    assert other.status_code == 200                                           # another address has its own bucket
    codes = [api.post("/api/account/passkey/login/options").status_code for _ in range(31)]
    assert codes == [200] * 30 + [429]
    api.tick(360)                                                             # 6 minutes: one registration back
    assert api.post("/api/account/passkey/register/options").status_code == 200
    assert api.post("/api/account/passkey/register/options").status_code == 429
    api.tick(3600)
    assert api.post("/api/account/passkey/login/options").status_code == 200
    # the answers: 20 a minute per address (the link checks' bucket)
    codes = [api.post("/api/account/passkey/login/verify", json={}, headers={"x-forwarded-for": "203.0.113.50"}).status_code
             for _ in range(21)]
    assert codes == [400] * 20 + [429]


def test_localhost_only_under_the_test_switch(monkeypatch, schema):
    _env(monkeypatch, "auto")
    accounts.reset()
    with TestClient(app, base_url="http://localhost:8754", headers={"Origin": "http://localhost:8754"}) as c:
        r = c.post("/api/account/passkey/register/options")
        assert r.status_code == 400 and r.json()["code"] == "passkey_wrong_site"
        monkeypatch.setenv(passkeys.ORIGINS_ENV, "http://localhost:8754")            # listed: still https only
        assert c.post("/api/account/passkey/register/options").json()["code"] == "passkey_wrong_site"
        monkeypatch.setenv(accounts.ENV, "on")
        r = c.post("/api/account/passkey/register/options")
        assert r.status_code == 200 and r.json()["options"]["rp"]["id"] == "localhost"
        assert "Secure" not in r.headers["set-cookie"]                      # http://localhost: no Secure flag
        key = SoftKey(origin="http://localhost:8754")
        r = c.post("/api/account/passkey/register/verify", json={"credential": key.create(r.json()["options"])})
        assert r.status_code == 200 and r.json()["created"] is True
        MADE.append(str(q("select user_id from accounts.passkeys where credential_id = %s", key.cred_id)[0][0]))
        o = c.post("/api/account/passkey/login/options").json()["options"]
        assert o["rpId"] == "localhost" and o["allowCredentials"] == [] and o["userVerification"] == "preferred"
        assert c.post("/api/account/passkey/login/verify", json={"credential": key.get(o)}).status_code == 200
    accounts.reset()
    _cleanup()


def test_a_guest_connection_joins_a_new_passkey_account(api, monkeypatch):
    """IL-5's connections ride on the passkey sign-in as on the link: a Yahoo cookie on this device joins the account."""
    from league_lab import yahoo_client as Y

    from league_lab_api import connections
    from league_lab_api import yahoo_connect as YC
    seen: list[tuple[str, bool]] = []
    monkeypatch.setattr(connections, "sync", lambda request, resp, uid, *, adopt: seen.append((uid, adopt)) or [])
    key = create_account(api)
    assert seen == [(MADE[-1], True)]
    assert sign_in(api, key)["status"] == 200 and seen[-1] == (MADE[-1], True)
    assert Y and YC                                                          # the modules the real sync reads


# ---------------------------------------------------------------- the schema (item 2)
def test_the_passkey_tables_and_their_grants():
    if not DB_OK:
        pytest.skip("database not reachable")
    sql = SQL_FILE.read_text().lower()
    assert sql.count("create table if not exists accounts.") == 10
    assert "alter table accounts.users alter column email drop not null" in sql
    assert "alter table accounts.users add column if not exists webauthn_handle bytea" in sql
    code = "\n".join(line.split("--")[0] for line in sql.splitlines())
    assert "drop table" not in code and "drop schema" not in code and "drop column" not in code
    with psycopg.connect(main._app_dsn(), autocommit=True) as conn:
        for t in ("passkeys", "passkey_challenges"):
            assert conn.execute("select has_table_privilege(%s, 'insert'), has_table_privilege(%s, 'delete'), "
                                "has_table_privilege(%s, 'truncate')", (f"accounts.{t}",) * 3).fetchone() == \
                (True, True, False), t
        assert conn.execute("select attnotnull from pg_attribute where attrelid = 'accounts.users'::regclass and "
                            "attname = 'email'").fetchone()[0] is False
        cons = {r[0] for r in conn.execute("select conname from pg_constraint where conrelid in "
                                           "('accounts.passkeys'::regclass, 'accounts.passkey_challenges'::regclass)")}
        assert {"passkey_challenges_purpose", "passkey_challenges_owner", "passkeys_transport_words"} <= cons
        fks = conn.execute("select confdeltype from pg_constraint where conrelid = 'accounts.passkeys'::regclass "
                           "and contype = 'f'").fetchall()
        assert fks == [("c",)]                                                # on delete cascade: the account takes them


def test_a_passkey_account_adds_an_email(api):
    """With a mailer, a passkey-only account adds its email through the emailed link (a second way in); an address that
    already has an account is refused in words and the link is kept for signing in to that account."""
    import re

    def link(email: str) -> str:
        assert api.post("/api/account/login", json={"email": email}).status_code == 202
        return re.search(r"#signin=([A-Za-z0-9_-]+)",
                         [m for m in accounts.STUB.sent if m["to"] == email][-1]["text"]).group(1)

    key = create_account(api)
    uid = MADE[-1]
    session = api.cookies.get(accounts.COOKIE)
    r = api.post("/api/account/verify", json={"token": link(f"added@{DOMAIN}")})
    assert r.status_code == 200 and r.json() == {"ok": True, "email": f"added@{DOMAIN}", "added": True}
    assert q("select email from accounts.users where id = %s", uid)[0][0] == f"added@{DOMAIN}"
    me = api.get("/api/account/me").json()
    assert me["email"] == f"added@{DOMAIN}" and me["sign_in"] == {"passkeys": 1, "email": True}
    assert api.cookies.get(accounts.COOKIE) != session                       # a fresh session for the same account
    assert sign_in(api, key)["email"] == f"added@{DOMAIN}"                   # the passkey still opens it
    # another passkey-only account cannot take an address that has an account
    create_account(api)
    token = link(f"added@{DOMAIN}")
    r = api.post("/api/account/verify", json={"token": token})
    assert r.status_code == 409 and r.json()["code"] == "email_taken"
    assert r.json()["error"] == "That email already has its own account. Sign out, then open the link again to sign in to that account."
    api.post("/api/account/logout", json={})
    r = api.post("/api/account/verify", json={"token": token})                # the link was kept
    assert r.status_code == 200 and r.json() == {"ok": True, "email": f"added@{DOMAIN}"}
    assert api.get("/api/account/me").json()["passkeys"][0]["label"] == "iPhone · Safari"
