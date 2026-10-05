"""Accounts, phase 2 (Wave I-L, IL-5): a provider connection follows the account (docs/ACCOUNTS.md § "Built, phase 2").

The cookies stay the request-path carriers — IK-2's ``ll_yahoo`` (a Yahoo refresh token) and IK-1's ``ll_espn`` (a
private ESPN league's ``espn_s2`` + ``SWID``, only behind ``LEAGUE_LAB_ESPN_PRIVATE=on``). For a signed-in person the
row in ``accounts.connections`` is the durable copy, so a sign-in on another device gets the connection back:

* **store** — when a signed-in person connects (``/api/yahoo/callback``, ``POST /api/espn/connect``), and when someone
  signs in on a device that already carries a connection cookie (``POST /api/account/verify``: the guest's connection
  joins the account). ``GET /api/account/me`` only **updates** a row the account already has (Yahoo may hand out a new
  refresh token on a refresh); it never makes one — a device that kept its own cookie after the person disconnected
  elsewhere does not put the connection back.
* **restore** — ``POST /api/account/verify`` and ``GET /api/account/me`` re-issue the cookie from the row when the
  request carries none (a new device; a cookie past its 60 / 30 days while the 90-day session lives). Yahoo only when
  this server can talk to Yahoo (``yahoo_connect.configured()``); ESPN only with the private switch on.
* **delete** — ``POST /api/yahoo/disconnect`` / ``POST /api/espn/disconnect`` signed in delete the row;
  ``DELETE /api/account`` deletes it with the account (``connections.user_id`` references ``users`` ``on delete
  cascade``; ``api/tests/test_il5.py`` checks it).

**At rest** the secret is ``sealed.seal`` (encrypt-then-MAC, the keys derived from ``LEAGUE_LAB_API_SECRET``) under the
purpose ``account-connection|<provider>`` — a cookie never opens as a row or a row as a cookie. What is sealed is the
least that restores the connection: Yahoo's refresh token and the user's GUID (never the hour-long access token; the
re-issued cookie refreshes it on its first read), ESPN's two cookies. ``external_user_id`` is Yahoo's GUID, and for
ESPN an HMAC of the ``SWID`` (``espn-<16 hex>``) — never the SWID itself. One connection per provider per account: a
new one replaces the old. Nothing here logs a token, a cookie or a sealed value; a failed write logs the exception's
class only and never fails the request it rides on (the cookie still works on this device).
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
from typing import Any

import psycopg
from fastapi import Request, Response

from . import accounts, db, sealed

log = logging.getLogger("league_lab_api.connections")

PROVIDERS = ("yahoo", "espn")
KIND = {"yahoo": "oauth", "espn": "cookie"}
LABEL = {"yahoo": "Yahoo Fantasy (read-only)", "espn": "ESPN private league cookies"}
MAX_AGE_S = 400 * 86400            # a sealed row is re-sealed at every write; Yahoo's refresh token has no stated end


# ---------------------------------------------------------------- the secret at rest
def _purpose(provider: str) -> str:
    return f"account-connection|{provider}"


def seal_secret(provider: str, data: dict) -> bytes:
    return sealed.seal(_purpose(provider), data).encode()


def open_secret(provider: str, blob: Any) -> dict | None:
    if blob is None:
        return None
    try:
        text = bytes(blob).decode()
    except (TypeError, ValueError):
        return None
    d = sealed.unseal(_purpose(provider), text, max_age_s=MAX_AGE_S)
    return d if isinstance(d, dict) else None


def external_id(provider: str, data: dict) -> str:
    if provider == "yahoo":
        g = str(data.get("g") or "").strip()
        return g[:200] if g else "yahoo"
    swid = str(data.get("swid") or "").upper().encode()
    key = (os.environ.get(sealed.SECRET_ENV) or "").encode()
    return "espn-" + hmac.new(key, b"espn-swid|" + swid, hashlib.sha256).hexdigest()[:16]


def _same(provider: str, a: dict | None, b: dict | None) -> bool:
    if not a or not b:
        return False
    fields = ("r",) if provider == "yahoo" else ("s2", "swid")
    return all(a.get(f) == b.get(f) for f in fields)


# ---------------------------------------------------------------- the cookies (the request-path carriers)
def _secure(request: Request) -> bool:
    return request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"


def cookie_data(request: Request, provider: str) -> dict | None:
    """What this request's provider cookie carries, in the row's shape (None: no readable cookie)."""
    if provider == "yahoo":
        from . import yahoo_connect
        s = yahoo_connect.session_from_cookie(request.cookies.get(yahoo_connect.COOKIE))
        return None if s is None or not s.refresh_token else {"r": s.refresh_token, "g": s.guid}
    from . import espn_connect
    pair = espn_connect.pair_from(request)                       # None with the private switch off
    return None if pair is None else {"s2": pair[0], "swid": pair[1]}


def _can_restore(provider: str) -> bool:
    if provider == "yahoo":
        from . import yahoo_connect
        return yahoo_connect.configured()
    from league_lab import espn_client
    return espn_client.private_enabled()


def issue_cookie(resp: Response, request: Request, provider: str, data: dict) -> None:
    if provider == "yahoo":
        from league_lab import yahoo_client as Y

        from . import yahoo_connect
        value = yahoo_connect.cookie_value(Y.YahooSession(refresh_token=str(data["r"]), guid=data.get("g")))
        resp.set_cookie(yahoo_connect.COOKIE, value, max_age=yahoo_connect.COOKIE_DAYS * 86400, httponly=True,
                        samesite="lax", secure=_secure(request), path="/api")
    else:
        from . import espn_connect
        resp.set_cookie(espn_connect.COOKIE, sealed.seal(espn_connect.PURPOSE, {"s2": data["s2"], "swid": data["swid"]}),
                        max_age=espn_connect.MAX_AGE_S, httponly=True, samesite="lax", secure=_secure(request),
                        path=espn_connect.PATH)


# ---------------------------------------------------------------- the rows
def save(user_id: str, provider: str, data: dict) -> None:
    """Upsert the account's connection to ``provider`` (one per provider: another identity replaces it)."""
    ext, blob = external_id(provider, data), seal_secret(provider, data)

    def tx(c: psycopg.Connection) -> None:
        c.execute("delete from accounts.connections where user_id = %s and provider = %s and external_user_id <> %s",
                  (user_id, provider, ext))
        c.execute("insert into accounts.connections (user_id, provider, external_user_id, label, kind, secret_enc, "
                  "status, last_sync_at) values (%s, %s, %s, %s, %s, %s, 'active', now()) on conflict (user_id, "
                  "provider, external_user_id) do update set secret_enc = excluded.secret_enc, status = 'active', "
                  "kind = excluded.kind, label = excluded.label, last_error = null, last_sync_at = now()",
                  (user_id, provider, ext, LABEL[provider], KIND[provider], blob))

    db.run_rw(tx)


def remove(user_id: str, provider: str) -> int:
    return int(db.run_rw(lambda c: c.execute("delete from accounts.connections where user_id = %s and provider = %s",
                                             (user_id, provider)).rowcount) or 0)


def stored(user_id: str) -> dict[str, tuple[str, dict | None]]:
    """{provider: (status, the opened secret or None)} for the account's Yahoo / ESPN rows."""
    rows = db.run_rw(lambda c: c.execute(
        "select provider, status, secret_enc from accounts.connections where user_id = %s and provider = any(%s)",
        (user_id, list(PROVIDERS))).fetchall())
    return {p: (st, open_secret(p, blob)) for p, st, blob in rows or []}


def listing(c: psycopg.Connection, user_id: str) -> list[dict]:
    """``/api/account/me``'s ``connections`` (inside its transaction): never a secret."""
    rows = c.execute("select provider, external_user_id, created_at, status, last_sync_at from accounts.connections "
                     "where user_id = %s order by provider, created_at", (user_id,)).fetchall()
    return [{"provider": p, "external_user_id": ext, "connected_at": None if t is None else t.isoformat(),
             "status": st, "last_sync_at": None if s is None else s.isoformat()} for p, ext, t, st, s in rows]


# ---------------------------------------------------------------- the hooks the routes call (never raise)
def _who(request: Request) -> tuple[str, str, str] | None:
    try:
        if not accounts.state()[0]:
            return None
        return accounts.current_user(request)
    except psycopg.Error:
        return None


def on_connect(request: Request, provider: str, data: dict | None) -> bool:
    """A connection made on this request (the Yahoo callback, ESPN's form): stored when someone is signed in."""
    if not data or not sealed.available():
        return False
    who = _who(request)
    if who is None:
        return False
    try:
        save(who[0], provider, data)
        return True
    except (psycopg.Error, sealed.SealUnavailable) as exc:
        log.warning("connections: the %s connection was not stored (%s)", provider, exc.__class__.__name__)
        return False


def on_disconnect(request: Request, provider: str) -> int:
    """Disconnect on this device, signed in: the account's row goes too."""
    who = _who(request)
    if who is None:
        return 0
    try:
        return remove(who[0], provider)
    except psycopg.Error as exc:
        log.warning("connections: the %s connection was not removed (%s)", provider, exc.__class__.__name__)
        return 0


def sync(request: Request, resp: Response, user_id: str, *, adopt: bool) -> list[str]:
    """Rows ↔ this request's cookies for a signed-in account. ``adopt`` (the sign-in): a cookie the account has no row
    for joins it. Always: a row with no cookie re-issues it (the restore); a cookie that differs from the account's
    row updates the row (a rotated refresh token). Returns the providers restored (tests, never a secret)."""
    if not sealed.available():
        return []
    restored: list[str] = []
    try:
        rows = stored(user_id)
        for p in PROVIDERS:
            have = cookie_data(request, p)
            status, row = rows.get(p, (None, None))
            if have is not None:
                if (row is not None and not _same(p, have, row)) or (row is None and adopt):
                    save(user_id, p, have)
            elif row is not None and status == "active" and _can_restore(p):
                issue_cookie(resp, request, p, row)
                restored.append(p)
    except (psycopg.Error, sealed.SealUnavailable) as exc:
        log.warning("connections: sync skipped (%s)", exc.__class__.__name__)
    return restored
