"""Passkeys (Wave I-M, IM-4): sign in with the phone's or computer's own lock (Face ID, a fingerprint, a PIN) — no
email, no password, no third party. docs/ACCOUNTS.md § "Passkeys"; the tables: scripts/hosted_accounts.sql (its IM-4
part); the library: py_webauthn (`webauthn`, api/uv.lock). The account, the session and everything saved to it are
accounts.py's, unchanged: a passkey is a second way to get the same `ll_session` cookie the emailed link gives.

**The routes** (on accounts.py's router, so behind whatever main.py puts in front of it, and behind its same-site guard;
JSON, `no-store`; errors in its contract `{error, detail, code}`):

| Route | Answer |
|---|---|
| `POST /api/account/passkey/register/options` | signed out: options for a **new account** (`purpose: create`); signed in: to **add** one (`add`) |
| `POST /api/account/passkey/register/verify {credential}` | `create`: the account + a session (`{ok, created}`, the cookie); `add`: `{ok, added, passkey}` |
| `POST /api/account/passkey/login/options` | options for a discoverable sign-in (nothing typed: the device offers the account) |
| `POST /api/account/passkey/login/verify {credential}` | a session (`{ok, email}`, the cookie) |
| `DELETE /api/account/passkeys/{id}` | `{ok, removed}` · 409 `last_sign_in` when it is the account's only way in |

**Choices** (WebAuthn Level 3): discoverable credentials (`residentKey: required`), user verification `preferred`,
attestation `none`, the library's algorithms (EdDSA, ES256, RS256). A new account's **user handle** is 32 random bytes
(`accounts.users.webauthn_handle`), never the email; an email account gets one when it adds its first passkey. The
name the device shows is "isuckatfantasy · <the day it was made>" (or the email, when the account has one).

**The challenge** is 32 random bytes made here, kept server-side (`accounts.passkey_challenges`, only its SHA-256),
**single use** (spent under a row lock before anything is verified, so a failed answer spends it too), **5 minutes**,
and bound to: its purpose, the account (`add`), the site it was made for (origin + rp id from the allow-list), and the
browser that asked (a random value in the HttpOnly, SameSite=Strict cookie `ll_passkey`, path `/api/account/passkey`,
stored as its SHA-256). The answer's challenge is looked up by its hash: one the server did not make, one already used,
an old one, one from another browser — each refused in words. Then the library checks the challenge again, the origin,
the rp id hash, user presence, the signature, and the **signature counter** (a counter that does not go up when it was
above zero means a cloned authenticator: refused, and the passkey row says nothing more until a real sign-in moves it).

**Where passkeys work**: `LEAGUE_LAB_PASSKEY_ORIGINS` (comma-separated; default `https://isuckatfantasy.io`; https only).
A ceremony's origin is the request's `Origin` header **only when it is on that list**; the rp id is the shortest listed
host it belongs to (`https://www.isuckatfantasy.io` and `https://isuckatfantasy.io` share `isuckatfantasy.io`). Any other
site (Render's own `*.onrender.com` address, a copy of the page) gets "Passkeys work on isuckatfantasy.io only. Open
https://isuckatfantasy.io/account to use one." — never a cryptic failure. `http://localhost:<port>` only under the test
switch (`LEAGUE_LAB_ACCOUNTS=on`: tests and the fixture API).

**Limits** (accounts.py's in-memory token bucket, keyed by an HMAC of the address): registration options 10 an hour,
sign-in options 30 an hour, answers 20 a minute (the link checks' bucket); 10 passkeys per account.

Nothing secret is logged, printed or returned: a challenge, the ceremony cookie, a session id never; a refusal logs the
exception's class (the library's message can quote what the browser sent). Credential ids and public keys are not
secrets (the private key never leaves the device), and are not logged either.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import importlib.util
import json
import logging
import os
import re
import secrets
import uuid
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

import psycopg
from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import accounts as A
from . import db
from .settings import APP_NAME

log = logging.getLogger("league_lab_api.passkeys")

# py_webauthn pulls in `cryptography` and pyOpenSSL: ~16 MB of memory once imported (measured next to the app's own
# libraries; docs/handbacks/IM-4.md). On a 512 MB server it is imported at the first ceremony, not at start-up.
# The image always has it (api/uv.lock); without it the status says passkeys are not ready.
LIBRARY = importlib.util.find_spec("webauthn") is not None
_W: dict[str, Any] = {}


def _lib() -> dict[str, Any]:
    """{webauthn, WX (its exceptions), S (its structs)} — imported once, on first use."""
    if not _W:
        import webauthn
        from webauthn.helpers import exceptions as WX
        from webauthn.helpers import structs as S
        _W.update(webauthn=webauthn, WX=WX, S=S)
    return _W


def base64url_to_bytes(value: Any) -> bytes:
    """The library's helper without importing the library (TypeError / ValueError on garbage)."""
    if not isinstance(value, str):
        raise TypeError("not base64url text")
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))

ORIGINS_ENV = "LEAGUE_LAB_PASSKEY_ORIGINS"
DEFAULT_ORIGIN = "https://isuckatfantasy.io"
CHALLENGE_MINUTES = 5
TIMEOUT_MS = 180_000                      # what the browser is told; the challenge itself lives 5 minutes
REGISTER_PER_HOUR, LOGIN_PER_HOUR = 10, 30
MAX_PASSKEYS = 10
MAX_ANSWER_BYTES = 32_768                 # an authenticator's answer is a few kB at most (attestation `none`)
COOKIE = "ll_passkey"
COOKIE_PATH = "/api/account/passkey"
TRANSPORTS = ("usb", "nfc", "ble", "internal", "hybrid", "smart-card", "cable")

_LOCAL = re.compile(r"^http://localhost(:\d{1,5})?$")
_HOST = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)*$")


# ---------------------------------------------------------------- the words (every refusal has its own)
def _err(status: int, code: str, words: str) -> A.AccountError:
    return A.AccountError(status, code, words)


def _off() -> A.AccountError:
    return _err(404, "passkeys_off", "Passkeys are not on for this server yet.")


def _wrong_site() -> A.AccountError:
    h = home()
    return _err(400, "passkey_wrong_site", f"Passkeys work on {h.split('://', 1)[1]} only. Open {h}/account to use one.")


def _bad() -> A.AccountError:
    return _err(400, "passkey_bad", "That is not a passkey answer we can read. Try again.")


def _spent() -> A.AccountError:
    return _err(400, "passkey_challenge", "That passkey request is not one we made, or it was already used. Start again.")


def _expired() -> A.AccountError:
    return _err(400, "passkey_expired", f"That took longer than {CHALLENGE_MINUTES} minutes. Start again.")


def _other_browser() -> A.AccountError:
    return _err(400, "passkey_browser", "That passkey request was started in another browser or tab. Start again here.")


def _refused() -> A.AccountError:
    return _err(400, "passkey_refused", "Your device's answer did not check out, so nothing changed. Try again.")


def _cloned() -> A.AccountError:
    return _err(400, "passkey_cloned", "This passkey's counter went backwards, which can mean it was copied. You are not "
                "signed in. Use another passkey, or remove this one from your account.")


def _unknown() -> A.AccountError:
    return _err(400, "passkey_unknown", f"That passkey is not saved to any {APP_NAME} account (it may have been removed). "
                "Sign in another way, or create a new account.")


def _taken() -> A.AccountError:
    return _err(409, "passkey_taken", "That passkey is already saved to an account.")


# ---------------------------------------------------------------- where passkeys work (the allow-list)
def normal_origin(raw: Any) -> str | None:
    """`scheme://host[:port]` (lower case, default port dropped) for an origin, else None (`null`, a path, garbage)."""
    if not isinstance(raw, str):
        return None
    raw = raw.strip()
    if not raw or raw == "null" or len(raw) > 300:
        return None
    try:
        u = urlsplit(raw)
        port = u.port
    except ValueError:
        return None
    scheme, host = u.scheme.lower(), (u.hostname or "").lower()
    if scheme not in ("https", "http") or not _HOST.match(host) or u.path not in ("", "/") or u.query or u.fragment \
            or u.username or u.password:
        return None
    if port is None or (scheme, port) in (("https", 443), ("http", 80)):
        return f"{scheme}://{host}"
    return f"{scheme}://{host}:{port}"


def _test_switch() -> bool:
    return A.mode() == "on"


def allowed_origins() -> list[str]:
    """The allow-list: `LEAGUE_LAB_PASSKEY_ORIGINS` (https only; `http://localhost:<port>` under the test switch)."""
    out: list[str] = []
    for part in (os.environ.get(ORIGINS_ENV) or DEFAULT_ORIGIN).split(","):
        o = normal_origin(part)
        if o and (o.startswith("https://") or (_LOCAL.match(o) and _test_switch())) and o not in out:
            out.append(o)
    return out or [DEFAULT_ORIGIN]


def home() -> str:
    """The first allowed origin: where the words send a person whose page is somewhere else."""
    return allowed_origins()[0]


def _host(origin: str) -> str:
    return origin.split("://", 1)[1].split(":", 1)[0]


def site_for(origin: Any) -> tuple[str, str] | None:
    """(origin, rp id) when a passkey may be made or used from this origin, else None. Never the request's word alone:
    the origin must be on the allow-list (or localhost under the test switch)."""
    o = normal_origin(origin)
    if o is None:
        return None
    allowed = allowed_origins()
    if o in allowed:
        host = _host(o)
        return o, min((h for h in map(_host, allowed) if host == h or host.endswith("." + h)), key=len)
    if _test_switch() and _LOCAL.match(o):
        return o, "localhost"
    return None


def request_site(request: Request) -> tuple[str, str] | None:
    """The status's hint (`passkey_here`): would a ceremony from the page that asked work? The `Origin` header when
    sent, else this request's scheme and host. A hint only: the ceremonies check the `Origin` header themselves."""
    origin = request.headers.get("origin")
    if origin is None:
        proto = (request.headers.get("x-forwarded-proto") or request.url.scheme or "").split(",")[0].strip()
        origin = f"{proto}://{request.headers.get('host') or ''}"
    return site_for(origin)


def _ceremony_site(request: Request) -> tuple[str, str]:
    got = site_for(request.headers.get("origin"))
    if got is None:
        raise _wrong_site()
    return got


# ---------------------------------------------------------------- small helpers
def _sha(b: bytes) -> bytes:
    return hashlib.sha256(b).digest()


def _require() -> None:
    A._require_on()
    if not A.passkeys_ready():
        raise _off()


def _limit(request: Request, name: str, n: int, per_s: float, words: str) -> bytes:
    ip_hash = A._mac("ip", A.client_ip(request))
    if not A.allow(f"{name}:{ip_hash.hex()}", n, per_s):
        raise _err(429, "rate_limited", words)
    return ip_hash


def label_for(user_agent: str | None) -> str:
    """"iPhone · Safari", "Mac · Chrome", "Windows · Edge": fixed words picked from the User-Agent, never the string."""
    u = (user_agent or "").lower()
    browser = next((name for word, name in (
        ("edg/", "Edge"), ("edga/", "Edge"), ("edgios/", "Edge"), ("opr/", "Opera"), ("samsungbrowser", "Samsung Internet"),
        ("firefox/", "Firefox"), ("fxios", "Firefox"), ("crios", "Chrome"), ("chrome/", "Chrome"), ("safari/", "Safari"))
        if word in u), None)
    family = A.agent_family(user_agent)
    parts = [p for p in (None if family == "Other" else family, browser) if p]
    return " · ".join(parts) if parts else "Passkey"


def _today() -> str:
    try:
        from league_lab import clock
        now = clock.now()
    except Exception:  # noqa: BLE001 - the real day when the pinned clock is unavailable
        now = datetime.now(UTC)
    return f"{now:%b} {now.day}, {now.year}"


def _iso(t) -> str | None:
    return None if t is None else t.isoformat()


def listing(c: psycopg.Connection, user_id: str) -> list[dict]:
    """`/api/account/me`'s `passkeys` (inside its transaction): labels and dates, never a key or a credential id."""
    rows = c.execute("select id, label, created_at, last_used_at, backed_up from accounts.passkeys where user_id = %s "
                     "order by created_at, id", (user_id,)).fetchall()
    return [{"id": str(i), "label": label, "created_at": _iso(made), "last_used_at": _iso(used), "synced": bool(bk)}
            for i, label, made, used, bk in rows]


# ---------------------------------------------------------------- the ceremony cookie and the challenge row
def _set_ceremony(resp: JSONResponse, request: Request, nonce: str) -> None:
    resp.set_cookie(COOKIE, nonce, max_age=CHALLENGE_MINUTES * 60, httponly=True, samesite="strict",
                    secure=A._secure(request), path=COOKIE_PATH)


def _drop_ceremony(resp: JSONResponse) -> None:
    resp.delete_cookie(COOKIE, path=COOKIE_PATH)


def _store_challenge(c: psycopg.Connection, challenge: bytes, nonce: str, purpose: str, user_id: str | None,
                     handle: bytes | None, site: tuple[str, str], ip_hash: bytes) -> None:
    c.execute("insert into accounts.passkey_challenges (challenge_hash, purpose, user_id, user_handle, browser_hash, "
              f"rp_id, origin, ip_hash, expires_at) values (%s, %s, %s, %s, %s, %s, %s, %s, now() + interval "
              f"'{CHALLENGE_MINUTES} minutes')",
              (_sha(challenge), purpose, user_id, handle, _sha(nonce.encode()), site[1], site[0], ip_hash))


def _answer(raw: Any) -> dict:
    """The browser's PublicKeyCredential as JSON (base64url fields), checked for shape and size before anything else."""
    if not isinstance(raw, dict) or len(json.dumps(raw, separators=(",", ":"))) > MAX_ANSWER_BYTES:
        raise _bad()
    resp = raw.get("response")
    if raw.get("type") != "public-key" or not isinstance(raw.get("id"), str) or not isinstance(raw.get("rawId"), str) \
            or not isinstance(resp, dict) or not isinstance(resp.get("clientDataJSON"), str):
        raise _bad()
    return raw


def _client_challenge(answer: dict) -> bytes:
    try:
        data = json.loads(base64url_to_bytes(answer["response"]["clientDataJSON"]))
        ch = base64url_to_bytes(data["challenge"])
    except (ValueError, KeyError, TypeError, AttributeError):
        raise _bad() from None
    if not 16 <= len(ch) <= 64:
        raise _spent()
    return ch


def _spend(answer: dict, purposes: tuple[str, ...], request: Request) -> dict:
    """The challenge this answer carries, spent now (single use, under a row lock), and every binding checked."""
    ch = _client_challenge(answer)
    h = _sha(ch)

    def tx(c: psycopg.Connection):
        row = c.execute("select purpose, user_id, user_handle, browser_hash, rp_id, origin, used_at is not null, "
                        "expires_at <= now() from accounts.passkey_challenges where challenge_hash = %s for update",
                        (h,)).fetchone()
        if row is not None and not row[6]:
            c.execute("update accounts.passkey_challenges set used_at = now() where challenge_hash = %s", (h,))
        return row

    row = db.run_rw(tx)
    if row is None or row[6]:
        raise _spent()
    purpose, user_id, handle, browser_hash, rp_id, origin, _used, expired = row
    if expired:
        raise _expired()
    if purpose not in purposes:
        raise _spent()
    nonce = request.cookies.get(COOKIE) or ""
    if not nonce or not hmac.compare_digest(_sha(nonce.encode()), bytes(browser_hash)):
        raise _other_browser()
    if normal_origin(request.headers.get("origin")) != origin:
        raise _wrong_site()
    return {"purpose": purpose, "user_id": None if user_id is None else str(user_id),
            "handle": None if handle is None else bytes(handle), "rp_id": rp_id, "origin": origin, "challenge": ch}


def _refusal(exc: Exception, what: str) -> A.AccountError:
    """The library's refusal in our words. Logged as the exception's class only (its message can quote the browser's)."""
    msg = str(exc).lower()
    if "origin" in msg or "rp id" in msg:
        return _wrong_site()
    if "sign count" in msg:
        return _cloned()
    if "challenge" in msg:
        return _spent()
    log.info("passkeys: a %s answer was refused (%s)", what, exc.__class__.__name__)
    return _refused()


def _library_errors() -> tuple[type[Exception], ...]:
    return (_lib()["WX"].WebAuthnException, ValueError, KeyError, TypeError, AttributeError)


def _transports(answer: dict) -> list[str]:
    got = (answer.get("response") or {}).get("transports")
    return sorted({t for t in got if t in TRANSPORTS}) if isinstance(got, list) else []


def _session(c: psycopg.Connection, user_id: str, request: Request) -> str:
    return str(c.execute(f"insert into accounts.sessions (user_id, expires_at, user_agent_family) values (%s, now() + "
                         f"interval '{A.SESSION_DAYS} days', %s) returning id",
                         (user_id, A.agent_family(request.headers.get("user-agent")))).fetchone()[0])


def _signed_in(request: Request, body: dict, user_id: str, session_id: str) -> JSONResponse:
    """The answer that signs this device in: the session cookie (accounts.py's), the ceremony cookie gone, and the
    device's Yahoo / ESPN connection joins the account (or the account's comes back: IL-5's sync, as the link does)."""
    resp = A._ok(body)
    A._set_cookie(resp, request, session_id)
    _drop_ceremony(resp)
    from . import connections
    connections.sync(request, resp, user_id, adopt=True)
    return resp


# ---------------------------------------------------------------- the routes (on accounts.py's router)
class AnswerIn(BaseModel):
    credential: dict[str, Any] = Field(default_factory=dict)


@A.router.post("/passkey/register/options")
def register_options_route(request: Request) -> JSONResponse:
    """Signed out: a new account's options. Signed in: options to add a passkey to this account."""
    _require()
    site = _ceremony_site(request)
    ip_hash = _limit(request, "pk-register", REGISTER_PER_HOUR, 3600.0,
                     "Too many new passkeys from here. Try again in an hour.")
    who = A.current_user(request)
    challenge, nonce = secrets.token_bytes(32), secrets.token_urlsafe(32)
    if who is None:
        purpose, user_id, handle, have = "create", None, secrets.token_bytes(32), []
        name = f"{APP_NAME} · {_today()}"
        db.run_rw(lambda c: _store_challenge(c, challenge, nonce, purpose, None, handle, site, ip_hash))
    else:
        purpose, user_id, email = "add", who[0], who[1]
        name = email or f"{APP_NAME} · {_today()}"

        def tx(c: psycopg.Connection):
            h = c.execute("update accounts.users set webauthn_handle = coalesce(webauthn_handle, %s) where id = %s "
                          "returning webauthn_handle", (secrets.token_bytes(32), user_id)).fetchone()[0]
            have = c.execute("select credential_id, transports from accounts.passkeys where user_id = %s",
                             (user_id,)).fetchall()
            if len(have) >= MAX_PASSKEYS:
                raise _err(400, "too_many", f"An account keeps at most {MAX_PASSKEYS} passkeys. Remove one first.")
            _store_challenge(c, challenge, nonce, purpose, user_id, bytes(h), site, ip_hash)
            return bytes(h), have

        handle, have = db.run_rw(tx)
    w, S = _lib()["webauthn"], _lib()["S"]
    exclude = [S.PublicKeyCredentialDescriptor(id=bytes(cid), transports=[S.AuthenticatorTransport(t) for t in tr or []
                                                                           if t in TRANSPORTS])
               for cid, tr in have]
    opts = w.generate_registration_options(
        rp_id=site[1], rp_name=APP_NAME, user_name=name, user_id=handle, user_display_name=name, challenge=challenge,
        timeout=TIMEOUT_MS, attestation=S.AttestationConveyancePreference.NONE,
        authenticator_selection=S.AuthenticatorSelectionCriteria(
            resident_key=S.ResidentKeyRequirement.REQUIRED, user_verification=S.UserVerificationRequirement.PREFERRED),
        exclude_credentials=exclude)
    resp = JSONResponse({"options": json.loads(w.options_to_json(opts)), "purpose": purpose}, headers=A.NO_STORE)
    _set_ceremony(resp, request, nonce)
    return resp


@A.router.post("/passkey/register/verify")
def register_verify_route(body: AnswerIn, request: Request) -> JSONResponse:
    """The device's answer to the options above: a new account and a session (`create`), or one more passkey (`add`)."""
    _require()
    _limit(request, "check-ip", A.CHECKS_PER_MIN, 60.0, "Too many tries from here. Wait a few minutes.")
    answer = _answer(body.credential)
    ch = _spend(answer, ("create", "add"), request)
    try:
        v = _lib()["webauthn"].verify_registration_response(
            credential=answer, expected_challenge=ch["challenge"], expected_rp_id=ch["rp_id"],
            expected_origin=ch["origin"], require_user_verification=False)
    except _library_errors() as exc:
        raise _refusal(exc, "registration") from None
    cred_id, key, count = bytes(v.credential_id), bytes(v.credential_public_key), int(v.sign_count)
    label, transports = label_for(request.headers.get("user-agent")), _transports(answer)
    synced = bool(v.credential_backed_up)
    insert = ("insert into accounts.passkeys (user_id, credential_id, public_key, sign_count, transports, label, "
              "backed_up) values (%s, %s, %s, %s, %s, %s, %s) returning id, created_at")

    if ch["purpose"] == "add":
        who = A.current_user(request)
        if who is None or who[0] != ch["user_id"]:
            raise A._signed_out()

        def add(c: psycopg.Connection):
            if c.execute("select 1 from accounts.passkeys where credential_id = %s", (cred_id,)).fetchone():
                raise _taken()
            if c.execute("select count(*) from accounts.passkeys where user_id = %s", (who[0],)).fetchone()[0] \
                    >= MAX_PASSKEYS:
                raise _err(400, "too_many", f"An account keeps at most {MAX_PASSKEYS} passkeys. Remove one first.")
            return c.execute(insert, (who[0], cred_id, key, count, transports, label, synced)).fetchone()

        try:
            pid, made = db.run_rw(add)
        except psycopg.errors.UniqueViolation:            # the same passkey saved by a request a moment earlier
            raise _taken() from None
        resp = A._ok({"added": True, "passkey": {"id": str(pid), "label": label, "created_at": _iso(made),
                                                 "last_used_at": None, "synced": synced}})
        _drop_ceremony(resp)
        return resp

    def create(c: psycopg.Connection):
        if c.execute("select 1 from accounts.passkeys where credential_id = %s", (cred_id,)).fetchone():
            raise _taken()
        uid = str(c.execute("insert into accounts.users (email, webauthn_handle, last_seen_at) values (null, %s, now()) "
                            "returning id", (ch["handle"],)).fetchone()[0])
        c.execute(insert, (uid, cred_id, key, count, transports, label, synced))
        return uid, _session(c, uid, request)

    try:
        uid, sid = db.run_rw(create)
    except psycopg.errors.UniqueViolation:
        raise _taken() from None
    return _signed_in(request, {"created": True, "email": None}, uid, sid)


@A.router.post("/passkey/login/options")
def login_options_route(request: Request) -> JSONResponse:
    """Options for a discoverable sign-in: no account named, the device offers the passkeys it holds for this site."""
    _require()
    site = _ceremony_site(request)
    ip_hash = _limit(request, "pk-login", LOGIN_PER_HOUR, 3600.0, "Too many passkey sign-ins from here. Try again in an hour.")
    challenge, nonce = secrets.token_bytes(32), secrets.token_urlsafe(32)
    db.run_rw(lambda c: _store_challenge(c, challenge, nonce, "login", None, None, site, ip_hash))
    w, S = _lib()["webauthn"], _lib()["S"]
    opts = w.generate_authentication_options(rp_id=site[1], challenge=challenge, timeout=TIMEOUT_MS, allow_credentials=[],
                                             user_verification=S.UserVerificationRequirement.PREFERRED)
    resp = JSONResponse({"options": json.loads(w.options_to_json(opts))}, headers=A.NO_STORE)
    _set_ceremony(resp, request, nonce)
    return resp


@A.router.post("/passkey/login/verify")
def login_verify_route(body: AnswerIn, request: Request) -> JSONResponse:
    """The device's signature: the passkey names its account (the credential id, and the user handle must agree)."""
    _require()
    _limit(request, "check-ip", A.CHECKS_PER_MIN, 60.0, "Too many tries from here. Wait a few minutes.")
    answer = _answer(body.credential)
    ch = _spend(answer, ("login",), request)
    try:
        cred_id = base64url_to_bytes(answer["rawId"])
        handle_raw = (answer.get("response") or {}).get("userHandle")
        handle = base64url_to_bytes(handle_raw) if isinstance(handle_raw, str) and handle_raw else None
    except (ValueError, TypeError, AttributeError):
        raise _bad() from None
    row = db.run_rw(lambda c: c.execute(
        "select p.id, p.user_id, p.public_key, p.sign_count, u.webauthn_handle, u.email from accounts.passkeys p "
        "join accounts.users u on u.id = p.user_id where p.credential_id = %s and u.deleted_at is null",
        (cred_id,)).fetchone())
    if row is None:
        raise _unknown()
    pid, uid, key, count, want_handle, email = row
    if handle is None or want_handle is None or not hmac.compare_digest(handle, bytes(want_handle)):
        raise _unknown()
    try:
        v = _lib()["webauthn"].verify_authentication_response(
            credential=answer, expected_challenge=ch["challenge"], expected_rp_id=ch["rp_id"],
            expected_origin=ch["origin"], credential_public_key=bytes(key), credential_current_sign_count=int(count),
            require_user_verification=False)
    except _library_errors() as exc:
        err = _refusal(exc, "sign-in")
        if err.code == "passkey_cloned":
            log.warning("passkeys: passkey %s answered with a counter that did not go up (refused)", pid)
        raise err from None

    def tx(c: psycopg.Connection) -> str:
        c.execute("update accounts.passkeys set sign_count = greatest(sign_count, %s), last_used_at = now() where id = %s",
                  (int(v.new_sign_count), pid))
        c.execute("update accounts.users set last_seen_at = now() where id = %s", (uid,))
        return _session(c, str(uid), request)

    sid = db.run_rw(tx)
    return _signed_in(request, {"email": email}, str(uid), sid)


@A.router.delete("/passkeys/{passkey_id}")
def remove_route(passkey_id: str, request: Request) -> JSONResponse:
    """Remove one of this account's passkeys — never its only way in (409 `last_sign_in`, with what to do instead)."""
    uid, email, _sid = A._user(request, write=True)
    if not A.passkeys_ready():
        raise _off()
    try:
        pid = str(uuid.UUID(passkey_id))
    except ValueError:
        raise _err(404, "not_saved", "That passkey is not saved to your account.") from None
    email_works = bool(email) and A.mailer() is not None

    def tx(c: psycopg.Connection) -> str:
        ids = [str(r[0]) for r in c.execute("select id from accounts.passkeys where user_id = %s for update",
                                            (uid,)).fetchall()]
        if pid not in ids:
            return "missing"
        if len(ids) == 1 and not email_works:
            return "last"
        c.execute("delete from accounts.passkeys where id = %s and user_id = %s", (pid, uid))
        return "ok"

    got = db.run_rw(tx)
    if got == "missing":
        raise _err(404, "not_saved", "That passkey is not saved to your account.")
    if got == "last":
        raise _err(409, "last_sign_in", "This passkey is the only way into your account: without it nobody could sign "
                   "in to it again. Add another passkey first, or delete the account.")
    return A._ok({"removed": 1})
