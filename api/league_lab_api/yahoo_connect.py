"""Connect with Yahoo (Wave I-K, IK-2): the OAuth 2.0 routes and the encrypted ``ll_yahoo`` cookie.

* ``GET /api/yahoo/connect`` -> 302 to Yahoo's sign-in (``request_auth``: our client id, the redirect URI, ``scope=fspt-r``
  — Fantasy Sports read — and ``state``: a random nonce signed with HMAC, ten minutes, also held in the short
  ``ll_yahoo_state`` cookie so the callback is bound to the browser that started it). Fixture mode
  (``LEAGUE_LAB_YAHOO_FIXTURES``, no real client id): straight to our callback with the code ``fixture``.
* ``GET /api/yahoo/callback?code&state`` -> the state checked, the code exchanged for tokens (``yahoo_client.
  exchange_code``) -> the ``ll_yahoo`` cookie -> 302 ``/leagues?platform=yahoo``. A refusal at Yahoo (``error=
  access_denied``), a stale or forged state, or a refused exchange -> 302 ``/leagues?platform=yahoo&yahoo_error=<denied
  | state | refused | down>`` (the setup screen says it in words).
* ``POST /api/yahoo/disconnect`` -> the cookie cleared (Yahoo documents no revocation endpoint for OAuth 2.0; the
  manager removes the app at Yahoo's account page — the About words say so). ``GET /api/yahoo/status`` ->
  ``{configured, connected, fixtures}``.
* Not configured (no ``LEAGUE_LAB_YAHOO_CLIENT_ID`` / ``LEAGUE_LAB_YAHOO_CLIENT_SECRET``, or no
  ``LEAGUE_LAB_API_SECRET`` to seal the cookie with), outside fixture mode: connect and callback answer **503**
  ``{"code": "yahoo_not_configured", "error": "Yahoo sign-in is not set up on this server yet", …}``.
* **The cookie**: ``ll_yahoo`` = ``seal({r: refresh token, a: access token, e: expiry, g: guid}, "yahoo")`` —
  HttpOnly, SameSite=Lax, Secure on https, path ``/api``, 60 days. The tokens live only there: never in a log, a
  response body or the database (``YahooSession.__repr__`` hides them). If the sealed value would pass 3,800
  characters (Yahoo access tokens are long), the access token is left out and refreshed on the next read.
* **The middleware** (``YahooSessionMiddleware``, pure ASGI, outermost): every ``/api/`` request with an ``ll_yahoo``
  cookie gets its ``YahooSession`` in ``yahoo_client.request_session`` for the request's reads; when a read refreshed
  the access token the cookie is re-set on the response, and when Yahoo refused the refresh it is cleared.

``seal`` / ``unseal``: the standard library only (no ``cryptography`` in the lock) — encrypt-then-MAC: a keystream of
HMAC-SHA256(enc_key, nonce || counter) blocks XORed with the JSON, then HMAC-SHA256(mac_key, version || purpose ||
nonce || ciphertext) as the tag (checked in constant time before anything is decrypted); the two keys are derived from
``LEAGUE_LAB_API_SECRET`` per ``purpose`` (``yahoo``; IK-1 may use ``espn``), so a cookie sealed for one purpose never
opens as another. A random 16-byte nonce per seal; an expiry inside the sealed payload.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from http.cookies import SimpleCookie
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from league_lab import yahoo_client as Y

from . import auth
from .settings import env

COOKIE = "ll_yahoo"
STATE_COOKIE = "ll_yahoo_state"
COOKIE_DAYS = 60
STATE_S = 600
MAX_COOKIE = 3800
DONE = "/leagues?platform=yahoo"
VERSION = b"v1"
_FIXTURE_SECRET = "league-lab fixture mode only: not a secret"


# ====================================================================================== seal / unseal
def _secret() -> str | None:
    s = env("API_SECRET")
    if s:
        return s
    if Y.fixtures_dir() is not None:
        return _FIXTURE_SECRET
    return None


def _keys(purpose: str) -> tuple[bytes, bytes]:
    s = _secret()
    if not s:
        raise Y.YahooNotConfigured("LEAGUE_LAB_API_SECRET is not set")
    root = hashlib.sha256(b"league-lab-seal|" + s.encode()).digest()
    enc = hmac.new(root, b"enc|" + purpose.encode(), hashlib.sha256).digest()
    mac = hmac.new(root, b"mac|" + purpose.encode(), hashlib.sha256).digest()
    return enc, mac


def _stream(key: bytes, nonce: bytes, n: int) -> bytes:
    out = bytearray()
    i = 0
    while len(out) < n:
        out += hmac.new(key, nonce + i.to_bytes(4, "big"), hashlib.sha256).digest()
        i += 1
    return bytes(out[:n])


def seal(obj: Any, purpose: str, *, days: float = COOKIE_DAYS, now: float | None = None) -> str:
    """``obj`` (JSON-able) -> an opaque URL-safe string only this server (this ``LEAGUE_LAB_API_SECRET``) opens."""
    enc, mac = _keys(purpose)
    body = json.dumps({"x": int((now if now is not None else time.time()) + days * 86400), "v": obj},
                      separators=(",", ":")).encode()
    nonce = os.urandom(16)
    ct = bytes(a ^ b for a, b in zip(body, _stream(enc, nonce, len(body)), strict=True))
    tag = hmac.new(mac, VERSION + purpose.encode() + nonce + ct, hashlib.sha256).digest()
    return VERSION.decode() + "." + base64.urlsafe_b64encode(nonce + ct + tag).decode().rstrip("=")


def unseal(text: str | None, purpose: str, *, now: float | None = None) -> Any:
    """The sealed object, or None (missing, tampered, another purpose or secret, expired)."""
    if not text or not text.startswith(VERSION.decode() + "."):
        return None
    try:
        enc, mac = _keys(purpose)
        raw = text.split(".", 1)[1]
        blob = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
    except (Y.YahooNotConfigured, ValueError):
        return None
    if len(blob) < 16 + 32 + 1:
        return None
    nonce, ct, tag = blob[:16], blob[16:-32], blob[-32:]
    if not hmac.compare_digest(tag, hmac.new(mac, VERSION + purpose.encode() + nonce + ct, hashlib.sha256).digest()):
        return None
    try:
        d = json.loads(bytes(a ^ b for a, b in zip(ct, _stream(enc, nonce, len(ct)), strict=True)))
    except ValueError:
        return None
    if not isinstance(d, dict) or int(d.get("x") or 0) < (now if now is not None else time.time()):
        return None
    return d.get("v")


def session_from_cookie(text: str | None) -> Y.YahooSession | None:
    v = unseal(text, "yahoo")
    return Y.YahooSession.from_cookie(v) if isinstance(v, dict) else None


def cookie_value(session: Y.YahooSession) -> str:
    v = seal(session.to_cookie(), "yahoo")
    if len(v) > MAX_COOKIE:                            # a long access token: keep the refresh token only
        v = seal({**session.to_cookie(), "a": "", "e": 0}, "yahoo")
    return v


def fixture_cookie() -> str:
    """Tests / e2e: the sealed ``ll_yahoo`` value of the fixture user (fixture mode or a set API secret)."""
    return cookie_value(Y.YahooSession(refresh_token="fixture-refresh", access_token="fixture-access-0",
                                       expires_at=time.time() + 3600, guid="FIXTUREGUID3"))


# ====================================================================================== state (CSRF)
def _state(nonce: str, now: float | None = None) -> str:
    exp = int((now if now is not None else time.time()) + STATE_S)
    _, mac = _keys("yahoo-state")
    sig = hmac.new(mac, f"{nonce}.{exp}".encode(), hashlib.sha256).hexdigest()[:32]
    return f"{nonce}.{exp}.{sig}"


def _state_ok(state: str | None, cookie_nonce: str | None, now: float | None = None) -> bool:
    try:
        nonce, exp, sig = str(state or "").split(".")
        _, mac = _keys("yahoo-state")
    except (ValueError, Y.YahooNotConfigured):
        return False
    good = hmac.new(mac, f"{nonce}.{exp}".encode(), hashlib.sha256).hexdigest()[:32]
    return (hmac.compare_digest(sig, good) and exp.isdigit() and int(exp) >= (now if now is not None else time.time())
            and bool(cookie_nonce) and hmac.compare_digest(nonce, str(cookie_nonce)))


# ====================================================================================== routes
router = APIRouter()


def _gate(request: Request) -> None:
    """The beta password gate (``main.require_auth``'s rule, without importing main)."""
    token = auth.token_from(request.cookies.get(auth.COOKIE), request.headers.get("authorization"))
    if not auth.valid(token):
        raise HTTPException(status_code=401, detail="Private beta. Enter the password from your invite.")


def _secure(request: Request) -> bool:
    return request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"


def _redirect_uri(request: Request) -> str:
    fixed = Y.redirect_uri_env()
    if fixed:
        return fixed
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}/api/yahoo/callback"


def _fixture_flow() -> bool:
    return Y.fixtures_dir() is not None and not (os.environ.get(Y.CLIENT_ID_ENV) and os.environ.get(Y.CLIENT_SECRET_ENV))


def configured() -> bool:
    """Connect with Yahoo works on this server: both Yahoo secrets and the API secret (or fixture mode)."""
    return Y.configured() and _secret() is not None


def not_configured() -> JSONResponse:
    e = Y.YahooNotConfigured()
    return JSONResponse({"error": e.words, "detail": e.words, "code": e.code, "fix": e.fix}, status_code=503,
                        headers={"Cache-Control": "no-store"})


def _done(error: str | None = None) -> RedirectResponse:
    r = RedirectResponse(DONE + (f"&yahoo_error={error}" if error else ""), status_code=302)
    r.headers["Cache-Control"] = "no-store"
    return r


@router.get("/api/yahoo/connect", dependencies=[Depends(_gate)], include_in_schema=False)
def connect(request: Request):
    if not configured():
        return not_configured()
    nonce = secrets.token_urlsafe(18)
    state = _state(nonce)
    if _fixture_flow():
        target = f"/api/yahoo/callback?code={Y.FIXTURE_CODE}&state={state}"
    else:
        target = Y.authorize_url(_redirect_uri(request), state)
    r = RedirectResponse(target, status_code=302)
    r.headers["Cache-Control"] = "no-store"
    r.set_cookie(STATE_COOKIE, nonce, max_age=STATE_S, httponly=True, samesite="lax", secure=_secure(request),
                 path="/api/yahoo")
    return r


@router.get("/api/yahoo/callback", dependencies=[Depends(_gate)], include_in_schema=False)
def callback(request: Request, code: str | None = None, state: str | None = None, error: str | None = None):
    if not configured():
        return not_configured()
    if error:
        r = _done("denied")
    elif not code or not _state_ok(state, request.cookies.get(STATE_COOKIE)):
        r = _done("state")
    else:
        try:
            session = Y.exchange_code(code, _redirect_uri(request))
        except Y.YahooSessionExpired:
            r = _done("refused")
        except (Y.YahooUnavailable, Y.YahooNotConfigured):
            r = _done("down")
        else:
            r = _done()
            r.set_cookie(COOKIE, cookie_value(session), max_age=COOKIE_DAYS * 86400, httponly=True, samesite="lax",
                         secure=_secure(request), path="/api")
    r.delete_cookie(STATE_COOKIE, path="/api/yahoo")
    return r


@router.post("/api/yahoo/disconnect", dependencies=[Depends(_gate)], include_in_schema=False)
def disconnect(request: Request):
    r = JSONResponse({"connected": False}, headers={"Cache-Control": "no-store"})
    r.delete_cookie(COOKIE, path="/api", secure=_secure(request), httponly=True, samesite="lax")
    return r


@router.get("/api/yahoo/status", dependencies=[Depends(_gate)], include_in_schema=False)
def status(request: Request):
    return JSONResponse({"configured": configured(), "connected": Y.request_session.get() is not None
                         or session_from_cookie(request.cookies.get(COOKIE)) is not None,
                         "fixtures": Y.fixtures_dir() is not None}, headers={"Cache-Control": "no-store"})


@router.get("/api/yahoo/leagues", dependencies=[Depends(_gate)], include_in_schema=False)
def my_leagues():
    """The signed-in manager's Yahoo leagues this season (``YahooLeagues.my_leagues``), for the setup screen's pick
    (IK-3's ``/api/leagues?yahoo_me=1`` is the screen's answer; this is the raw list). 401-style codes as JSON."""
    from league_lab import yahoo_leagues as YL
    try:
        rows = YL.YahooLeagues(_client(), lambda: {}).my_leagues()
    except (Y.YahooSignInRequired, Y.YahooNotConfigured, Y.YahooBusy, Y.YahooUnavailable) as exc:
        code, words, fix = Y.setup_parts(exc)
        st = 401 if isinstance(exc, Y.YahooSignInRequired) else 503 if not isinstance(exc, Y.YahooUnavailable) else 502
        return JSONResponse({"error": words, "detail": words, "code": code, "fix": fix}, status_code=st,
                            headers={"Cache-Control": "no-store"})
    return JSONResponse({"leagues": rows}, headers={"Cache-Control": "no-store"})


_CLIENT: tuple[str, Y.Yahoo] | None = None


def _client() -> Y.Yahoo:
    """A process-wide client for this module's own reads (rebuilt when the fixture directory changes)."""
    global _CLIENT
    fx = os.environ.get(Y.FIXTURES_ENV, "")
    if _CLIENT is None or _CLIENT[0] != fx:
        _CLIENT = (fx, Y.Yahoo())
    return _CLIENT[1]


# ====================================================================================== the middleware
class YahooSessionMiddleware:
    """Puts the request's ``YahooSession`` (from ``ll_yahoo``) in ``yahoo_client.request_session`` and re-sets /
    clears the cookie when a read refreshed the token / was refused (see the module docstring)."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http" or not str(scope.get("path", "")).startswith("/api/"):
            return await self.app(scope, receive, send)
        raw = b"; ".join(v for k, v in scope.get("headers") or [] if k == b"cookie").decode("latin-1")
        session = None
        if COOKIE in raw:
            jar = SimpleCookie()
            try:
                jar.load(raw)
            except Exception:  # noqa: BLE001 - a malformed cookie header is "no cookie"
                jar = SimpleCookie()
            if COOKIE in jar:
                session = session_from_cookie(jar[COOKIE].value)
        if session is None:
            return await self.app(scope, receive, send)
        token = Y.request_session.set(session)
        secure = scope.get("scheme") == "https" or any(k == b"x-forwarded-proto" and v == b"https"
                                                       for k, v in scope.get("headers") or [])

        async def send_wrapper(message):
            if message.get("type") == "http.response.start" and (session.changed or session.expired):
                already = any(k.lower() == b"set-cookie" and v.startswith(COOKIE.encode() + b"=")
                              for k, v in message.get("headers") or [])
                if not already:
                    flags = "; Path=/api; HttpOnly; SameSite=lax" + ("; Secure" if secure else "")
                    if session.expired:
                        line = f'{COOKIE}=""; Max-Age=0{flags}'
                    else:
                        line = f"{COOKIE}={cookie_value(session)}; Max-Age={COOKIE_DAYS * 86400}{flags}"
                    message = {**message, "headers": [*(message.get("headers") or []),
                                                      (b"set-cookie", line.encode("latin-1"))]}
            await send(message)
        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            Y.request_session.reset(token)


def install(app) -> None:
    """``main.py``'s one line: the routes (ahead of the ``/api/{rest}`` catch-all, wherever the line sits) and the
    middleware (outermost)."""
    app.router.routes[0:0] = list(router.routes)
    app.add_middleware(YahooSessionMiddleware)
