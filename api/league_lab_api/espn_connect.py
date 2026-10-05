"""A private ESPN league read with the manager's own cookies (Wave I-K, IK-1) — **off unless
``LEAGUE_LAB_ESPN_PRIVATE=on``** (and ``LEAGUE_LAB_API_SECRET`` is set).

ESPN has no sign-in for other apps. A private league answers only a request that carries two of the manager's own
ESPN cookies, ``espn_s2`` and ``SWID`` (what cwendt94/espn-api asks its users to copy from the browser). This module:

* ``POST /api/espn/connect`` ``{"espn_s2": "...", "swid": "{...}"}`` — the one-time form: checks the two look like
  ESPN's, seals them (``sealed.seal``: encrypted and authenticated with ``LEAGUE_LAB_API_SECRET``) into the
  ``ll_espn`` cookie (HttpOnly, SameSite=Lax, Secure on https, ``Path=/api``, 30 days) and answers ``{ok, connected,
  words}``. The server keeps nothing: no file, no table, no log line holds the cookies.
* ``POST /api/espn/disconnect`` — clears the cookie.
* ``GET /api/espn/status`` — ``{private: <the switch>, connected: <a readable ll_espn came with this request>,
  words}``.
* ``auth_middleware`` — for each request, the ``ll_espn`` cookie (switch on only) is unsealed into
  ``espn_client.AUTH`` (a ContextVar) for that request alone; ``espn_client.ESPN`` sends the pair to ESPN with the
  reads of that request and forgets it.

Switch off: ``connect`` answers 404 ``espn_private_off``, the middleware ignores any ``ll_espn`` cookie, and a private
league is ``espn_league_private`` with the "ask the commissioner to make it public" fix.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from league_lab import espn_client as E

from . import sealed

router = APIRouter()
COOKIE = "ll_espn"
PURPOSE = "espn-cookies"
PATH = "/api"
MAX_AGE_S = 30 * 86400
WORDS = "Your ESPN cookies stay in your browser; isuckatfantasy reads your league with them and never stores them."
HOW = ("On fantasy.espn.com, signed in: your browser's developer tools → Application (Storage) → Cookies → "
       "https://fantasy.espn.com — copy the values of espn_s2 and SWID.")
OFF = "Private ESPN leagues are not switched on on this server."
# ---- IL-5: signed in, the cookies are also kept with the account, encrypted, so another device signs in to them
WORDS_SAVED = ("Your ESPN cookies are kept in this browser and, encrypted, with your account so your other devices can "
               "read your league; Disconnect removes them from both.")


def _secure(request: Request) -> bool:
    return request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"


def _no_store(body: dict, status: int = 200) -> JSONResponse:
    return JSONResponse(body, status_code=status, headers={"Cache-Control": "no-store"})


def pair_from(request: Request) -> tuple[str, str] | None:
    """The cookie pair this request carries in ``ll_espn`` (None: switch off, no cookie, or not readable)."""
    if not E.private_enabled():
        return None
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    d = sealed.unseal(PURPOSE, token, max_age_s=MAX_AGE_S)
    if not isinstance(d, dict):
        return None
    return E.clean_cookies(d.get("s2"), d.get("swid"))


async def auth_middleware(request: Request, call_next):
    """``espn_client.AUTH`` = this request's ESPN cookies (switch on only), reset when the request is done."""
    pair = pair_from(request) if request.url.path.startswith(PATH) else None
    token = E.AUTH.set(pair)
    try:
        return await call_next(request)
    finally:
        E.AUTH.reset(token)


@router.get("/api/espn/status")
def status(request: Request):
    return _no_store({"private": E.private_enabled(), "connected": pair_from(request) is not None, "words": WORDS,
                      "how": HOW if E.private_enabled() else None})


@router.post("/api/espn/connect")
async def connect(request: Request):
    if not E.private_enabled():
        return _no_store({"error": OFF, "detail": OFF, "code": "espn_private_off"}, 404)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001 - any unreadable body is the same answer (and is never echoed)
        body = None
    pair = E.clean_cookies((body or {}).get("espn_s2"), (body or {}).get("swid")) if isinstance(body, dict) else None
    if pair is None:
        words = "Those do not look like ESPN's espn_s2 and SWID cookies."
        return _no_store({"error": words, "detail": words, "code": "espn_cookies_invalid", "fix": HOW}, 400)
    from . import connections  # ---- IL-5: signed in, the connection follows the account
    saved = connections.on_connect(request, "espn", {"s2": pair[0], "swid": pair[1]})
    resp = _no_store({"ok": True, "connected": True, "words": WORDS_SAVED if saved else WORDS})
    resp.set_cookie(COOKIE, sealed.seal(PURPOSE, {"s2": pair[0], "swid": pair[1]}), max_age=MAX_AGE_S, httponly=True,
                    samesite="lax", secure=_secure(request), path=PATH)
    return resp


@router.post("/api/espn/disconnect")
def disconnect(request: Request):
    from . import connections  # ---- IL-5: signed in, the account's row goes too
    resp = _no_store({"ok": True, "connected": False, "words": WORDS,
                      "removed": connections.on_disconnect(request, "espn")})
    resp.delete_cookie(COOKIE, path=PATH)
    return resp
