"""Accounts, phase 1 (Wave I-K, IK-4): sign in by an emailed link; the leagues, preferences and watchlist a person saves.
docs/ACCOUNTS.md § "Built, phase 1"; docs/HOSTING.md § "Accounts"; the tables: scripts/hosted_accounts.sql.

Every route is behind the beta password (main.py includes this router with `require_auth`): the gate stays in front,
and nobody needs an account — guest exploration (this browser's localStorage) is unchanged.

**The switch** `LEAGUE_LAB_ACCOUNTS` = `off` | `auto` (default) | `on`:
  * `auto`: on when `LEAGUE_LAB_API_SECRET` is set and `accounts.users` exists (the nightly's sync applies the script),
    with the sign-in methods this server has (---- IM-4): **`passkey`** when the script's passkey tables are there
    (`accounts.passkeys`, `accounts.passkey_challenges`, an optional `users.email`: passkeys.py), **`email`** when
    `LEAGUE_LAB_RESEND_API_KEY` is set. No method → off. `GET /api/account/status` says `enabled`, `methods` and, per
    method, why not (`why`);
  * `on`: as `auto`, but with no Resend key the **stub mailer** keeps the messages in this process's memory (tests and
    the fixture API only: nothing is sent, printed or logged), and passkeys also accept `http://localhost:<port>`;
  * off: every route but `status` answers 404 `accounts_off`; the web app hides sign-in.

**Same site** (---- IM-4): every state-changing route here (POST / PUT / DELETE, passkeys.py's too) refuses a request a
browser marks as coming from another site (`Sec-Fetch-Site`, else `Origin` against the allow-list or the request's own
host) with 403 `cross_site` — by itself, whether or not a gate or a middleware stands in front.

**Sign-in.** `POST /api/account/login {email}` → a link `<LEAGUE_LAB_PUBLIC_URL>/account#signin=<token>` emailed with
Resend (from `LEAGUE_LAB_MAIL_FROM`). The token is 32 random bytes, stored only as its SHA-256, single use, 15 minutes.
It travels in the URL's fragment, which a browser never sends to a server, so no access log (Render's, uvicorn's) ever
holds it; the page posts it: `POST /api/account/verify {token}` → a server-side session (`accounts.sessions`, 90 days)
and the cookie `ll_session` = `<session id>.<HMAC-SHA256(LEAGUE_LAB_API_SECRET, id)>` (HttpOnly, SameSite=Lax, Secure on
https, path /api/account). The link's host is never taken from the request (a forged Host header would mail a link to
someone else's site): `LEAGUE_LAB_PUBLIC_URL`, default https://isuckatfantasy.io. A link, a token or an email body is
never logged, printed or returned; a failed send logs the exception's class only. The answer to `login` is the same
whether the address has an account or not.

**Limits.** Links: 5 per address and 30 per IP address an hour, and `LEAGUE_LAB_ACCOUNTS_DAILY_MAX` (90) a day in all
(Resend's free tier sends 100 a day) — counted in `accounts.login_links`, so a restart forgets nothing. The IP is
kept only as an HMAC. Signed-in writes: 60 a minute per session, link checks 20 a minute per IP (in memory, the usage
limiter's token bucket). Sizes: 50 leagues, 200 preferences (8 KB each), 200 watchlist rows per account.

**Leagues.** `league_key` = `provider:season:external_id` (docs/ACCOUNTS.md principle 3) from the app's key: a Sleeper
id → `sleeper:2026:<id>`, `mfl:<id>` → `mfl:2026:<id>`, `espn:<id>` (or `espn:<season>:<id>`) → `espn:2026:<id>`,
`yahoo:<game>.l.<id>` → `yahoo:2026:<game>.l.<id>`. An upsert by that key: saving twice changes nothing. What a user
sees of a league (its name, the team's name, the scoring line) is on the user's own row, never on the shared one.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import threading
import time
import urllib.error
import urllib.request
import uuid
from collections import deque
from datetime import UTC, datetime
from typing import Any

import psycopg
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import db
from .settings import APP_NAME, env

log = logging.getLogger("league_lab_api.accounts")

ENV = "LEAGUE_LAB_ACCOUNTS"
COOKIE = "ll_session"
COOKIE_PATH = "/api"     # ---- IL-5: was /api/account — the Yahoo / ESPN connect and disconnect routes must see who is
LEGACY_COOKIE_PATH = "/api/account"   # signed in (connections.py); sign-out also clears a cookie set at the old path
SESSION_DAYS = 90
LINK_MINUTES = 15
PER_EMAIL_HOUR, PER_IP_HOUR, DAILY_MAX = 5, 30, 90
MAX_LEAGUES, MAX_PREFS, MAX_WATCH, MAX_VALUE_BYTES = 50, 200, 200, 8192
WRITES_PER_MIN, CHECKS_PER_MIN = 60, 20
MAX_SESSIONS = 20                 # ---- IM-4 fix: live sessions per account (the oldest are dropped past it)
MAX_BUCKETS = 5000                # ---- IM-4 fix: the in-memory limiter's hard size (≈ 1 MB), least recently used out
PUBLIC_URL = "https://isuckatfantasy.io"
MAIL_FROM = "signin@isuckatfantasy.io"
RESEND_URL = "https://api.resend.com/emails"
PROVIDERS = ("sleeper", "mfl", "espn", "yahoo")

_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,189}\.[^@\s]{2,63}$")
_TOKEN = re.compile(r"^[A-Za-z0-9_-]{20,100}$")
_SEASON_KEY = re.compile(r"^(sleeper|mfl|espn|yahoo):(\d{4}):([0-9A-Za-z.]{1,40})$")
_PREF_KEY = re.compile(r"^[a-z][a-z0-9._-]{0,63}$")
_PLAYER_KEY = re.compile(r"^([a-z]{2,8}:)?[A-Za-z0-9_.-]{1,40}$")
_TEAM_ID = re.compile(r"^[0-9A-Za-z._-]{1,40}$")
_DIGITS = re.compile(r"^\d{1,24}$")
_YAHOO = re.compile(r"^\d{1,6}\.l\.\d{1,12}$")


class AccountError(Exception):
    """An answer in the error contract: {"error": words, "detail": words, "code": code} with this status."""

    def __init__(self, status: int, code: str, words: str):
        super().__init__(words)
        self.status, self.code, self.words = status, code, words


def _off() -> AccountError:
    return AccountError(404, "accounts_off", "Accounts are not on for this server yet.")


def _signed_out() -> AccountError:
    return AccountError(401, "signed_out", "Sign in to see your account.")


def _email_off() -> AccountError:  # ---- IM-4: a passkey-only server
    return AccountError(404, "email_off", "Signing in by email is not on for this server. Use a passkey.")


# ---------------------------------------------------------------- the switch
def mode() -> str:
    m = os.environ.get(ENV, "auto").strip().lower()
    if m in ("off", "0", "false", "no"):
        return "off"
    return "on" if m in ("on", "1", "true", "yes") else "auto"


def _secret() -> bytes:
    return env("API_SECRET").encode()


def _resend_key() -> str:
    return env("RESEND_API_KEY").strip()


def daily_max() -> int:
    try:
        return max(1, int(env("ACCOUNTS_DAILY_MAX", str(DAILY_MAX))))
    except ValueError:
        return DAILY_MAX


_ready = {"ok": False, "passkeys": False, "next": 0.0}

# ---- IM-4: one query says whether the phase-1 tables are there and whether the passkey part of the script has run on
# this database (the two tables, the user handle column, an optional email) — each with the app role's right to write.
# A NULL oid (a missing table) makes has_table_privilege NULL, so `coalesce(..., false)` never raises.
READY_SQL = (
    "select coalesce(has_table_privilege(to_regclass('accounts.users'), 'insert'), false), "
    "coalesce(has_table_privilege(to_regclass('accounts.passkeys'), 'insert'), false) "
    "and coalesce(has_table_privilege(to_regclass('accounts.passkey_challenges'), 'insert'), false) "
    "and exists (select 1 from pg_attribute where attrelid = to_regclass('accounts.users') and attname = 'webauthn_handle' "
    "and not attisdropped) "
    "and exists (select 1 from pg_attribute where attrelid = to_regclass('accounts.users') and attname = 'email' "
    "and not attnotnull)")


def _readiness() -> dict:
    """{ok, passkeys} — checked at most once a minute; every ten minutes once everything is there."""
    now = time.monotonic()
    if now >= _ready["next"]:
        try:
            ok, pk = db.run_rw(lambda c: c.execute(READY_SQL).fetchone())
        except psycopg.Error:
            ok, pk = False, False
        ok, pk = bool(ok), bool(ok and pk)
        _ready.update(ok=ok, passkeys=pk, next=now + (600.0 if ok and pk else 60.0))
    return _ready


def schema_ready() -> bool:
    """`accounts.users` exists and the app role may write it."""
    return bool(_readiness()["ok"])


def passkeys_ready() -> bool:
    """---- IM-4: the passkey tables (scripts/hosted_accounts.sql's IM-4 part) are there, and webauthn is installed."""
    from . import passkeys
    return bool(_readiness()["passkeys"]) and passkeys.LIBRARY


def why_not() -> dict[str, str | None]:
    """---- IM-4: per sign-in method, why it is not offered (None: it is): passkey not_ready, email no_mailer."""
    return {"passkey": None if passkeys_ready() else "not_ready", "email": None if mailer() is not None else "no_mailer"}


def methods() -> list[str]:
    """---- IM-4: the sign-in methods this server has, in the order the screen offers them."""
    w = why_not()
    return [m for m in ("passkey", "email") if w[m] is None]


def state() -> tuple[bool, str | None]:
    """(enabled, why not): off | no_secret | not_ready (the tables, or no sign-in method yet: `why_not` says which)."""
    m = mode()
    if m == "off":
        return False, "off"
    if not _secret():
        return False, "no_secret"
    if not schema_ready():
        return False, "not_ready"
    if not methods():
        return False, "not_ready" if not passkeys_ready() else "no_mailer"
    return True, None


def _require_on() -> None:
    if not state()[0]:
        raise _off()


def _require_email() -> None:
    """---- IM-4: the emailed link needs a mailer (a passkey-only server answers 404 `email_off`)."""
    _require_on()
    if mailer() is None:
        raise _email_off()


# ---------------------------------------------------------------- mail
class StubMailer:
    """Keeps the last messages in this process's memory (tests and the fixture API). Never prints or logs them."""

    name = "stub"

    def __init__(self) -> None:
        self.sent: deque[dict] = deque(maxlen=50)

    def send(self, to: str, subject: str, text: str, html: str) -> None:
        self.sent.append({"to": to, "subject": subject, "text": text, "html": html})


class ResendMailer:
    """Resend's REST API (resend.com/docs/api-reference/emails/send-email): POST /emails, Bearer key, a User-Agent."""

    name = "resend"

    def __init__(self, key: str, sender: str) -> None:
        self.key, self.sender = key, sender

    def send(self, to: str, subject: str, text: str, html: str) -> None:
        body = json.dumps({"from": self.sender, "to": [to], "subject": subject, "text": text, "html": html}).encode()
        req = urllib.request.Request(RESEND_URL, data=body, method="POST", headers={
            "Authorization": f"Bearer {self.key}", "Content-Type": "application/json",
            "User-Agent": f"{APP_NAME}-api/1 (+{PUBLIC_URL})"})
        with urllib.request.urlopen(req, timeout=10) as resp:          # noqa: S310 - a fixed https URL
            if resp.status >= 300:
                raise RuntimeError(f"resend answered {resp.status}")


STUB = StubMailer()


def mailer() -> StubMailer | ResendMailer | None:
    key = _resend_key()
    if key:
        return ResendMailer(key, _mail_from())
    return STUB if mode() == "on" else None


def _mail_from() -> str:
    addr = env("MAIL_FROM", MAIL_FROM).strip() or MAIL_FROM
    return addr if "<" in addr else f"{APP_NAME} <{addr}>"


def public_url() -> str:
    return (env("PUBLIC_URL", PUBLIC_URL).strip() or PUBLIC_URL).rstrip("/")


def _message(link: str) -> tuple[str, str, str]:
    subject = f"Your {APP_NAME} sign-in link"
    text = (f"Tap the link to sign in to {APP_NAME}:\n\n{link}\n\nIt works once, for {LINK_MINUTES} minutes, on the "
            f"device you open it on. If you did not ask for it, ignore this email: nobody can sign in without it.\n")
    html = (f'<p>Tap the link to sign in to {APP_NAME}:</p><p><a href="{link}">Sign in to {APP_NAME}</a></p>'
            f"<p>It works once, for {LINK_MINUTES} minutes, on the device you open it on. If you did not ask for it, "
            f"ignore this email: nobody can sign in without it.</p>")
    return subject, text, html


# ---------------------------------------------------------------- small helpers
def normalize_email(raw: Any) -> str | None:
    if not isinstance(raw, str):
        return None
    e = raw.strip().lower()
    return e if len(e) <= 254 and _EMAIL.match(e) else None


def _hash_token(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


def _mac(kind: str, value: str) -> bytes:
    return hmac.new(_secret(), f"{kind}|{value}".encode(), hashlib.sha256).digest()


def cookie_value(session_id: str) -> str:
    return f"{session_id}.{_mac('session', session_id).hex()}"


def session_id_from(cookie: str | None) -> str | None:
    """The session id when the cookie's HMAC is ours, else None (no database read for a forged cookie)."""
    if not cookie or "." not in cookie or not _secret():
        return None
    sid, sig = cookie.split(".", 1)
    try:
        sid = str(uuid.UUID(sid))
    except ValueError:
        return None
    return sid if hmac.compare_digest(sig, _mac("session", sid).hex()) else None


def client_ip(request: Request) -> str:
    """The client's address for the sign-in limits (kept only as an HMAC)."""
    # PO (Wave I-M merge; IM-3's finding): the first hop is whatever the client wrote, and uvicorn's
    # --forwarded-allow-ips='*' copies it into request.client — so the address is IM-3's (ratelimit.client_address:
    # the edge's header on Render, else the hop our proxy appended, else the peer), the same key the limiter uses.
    from . import ratelimit
    return ratelimit.client_group(request.scope)


def agent_family(ua: str | None) -> str:
    u = (ua or "").lower()
    for word, name in (("iphone", "iPhone"), ("ipad", "iPad"), ("android", "Android"), ("macintosh", "Mac"),
                       ("windows", "Windows"), ("linux", "Linux")):
        if word in u:
            return name
    return "Other"


def current_season() -> int:
    """The NFL season now (January–February still belong to the season that started the September before)."""
    try:
        from league_lab import clock
        now = clock.now()
    except Exception:  # noqa: BLE001 - the real time when the pinned clock is unavailable
        now = datetime.now(UTC)
    return now.year if now.month >= 3 else now.year - 1


def league_key(league: Any, season: Any = None) -> str:
    """`provider:season:external_id` from the app's key (or a league_key already). ValueError when it is not one."""
    s = str(league or "").strip()
    m = _SEASON_KEY.match(s)
    if m:
        provider, yr, ext = m.group(1), int(m.group(2)), m.group(3)
    else:
        yr = None
        if s.startswith(("mfl:", "espn:", "yahoo:", "sleeper:")):
            provider, ext = s.split(":", 1)
        else:
            provider, ext = "sleeper", s
        if provider == "espn" and re.match(r"^\d{4}:\d+$", ext):     # IK-1's espn:<season>:<id>
            y, ext = ext.split(":", 1)
            yr = int(y)
        if season is not None and str(season).strip():
            try:
                yr = int(season)
            except (TypeError, ValueError) as exc:
                raise ValueError("season") from exc
        yr = yr or current_season()
    ok = _YAHOO.match(ext) if provider == "yahoo" else _DIGITS.match(ext)
    if provider not in PROVIDERS or not ok or not 2000 <= yr <= 2100:
        raise ValueError("league")
    return f"{provider}:{yr}:{ext}"


def app_key(key: str) -> str:
    """The app's league id for a league_key: the bare Sleeper id, else `<provider>:<external id>`."""
    provider, _season, ext = key.split(":", 2)
    return ext if provider == "sleeper" else f"{provider}:{ext}"


# ---------------------------------------------------------------- the in-memory limiter (usage.allow's pattern)
clock = time.monotonic
_lock = threading.Lock()
_buckets: dict[str, tuple[float, float]] = {}


def allow(key: str, per_min: int, per_s: float = 60.0) -> bool:
    """A token bucket of `per_min` tries refilling over `per_s` seconds (---- IM-4: `per_s`, e.g. 10 an hour)."""
    now = clock()
    rate = per_min / per_s
    with _lock:
        tokens, then = _buckets.pop(key, (float(per_min), now))     # popped and put back: the dict is an LRU
        tokens = min(float(per_min), tokens + (now - then) * rate)
        ok = tokens >= 1.0
        _buckets[key] = (tokens - 1.0 if ok else tokens, now)
        if len(_buckets) > MAX_BUCKETS:                              # ---- IM-4 fix: a hard bound, not only a sweep
            for k in [k for k, (_t, w) in _buckets.items() if now - w > 3600]:
                del _buckets[k]
            while len(_buckets) > MAX_BUCKETS * 9 // 10:
                del _buckets[next(iter(_buckets))]                  # the least recently seen: a fresh bucket later
        return ok


def reset() -> None:
    with _lock:
        _buckets.clear()
    STUB.sent.clear()
    _ready.update(ok=False, passkeys=False, next=0.0)


# ---------------------------------------------------------------- the flows (each one transaction on db.run_rw)
def request_link(email_raw: Any, ip: str) -> None:
    _require_email()
    email = normalize_email(email_raw)
    if email is None:
        raise AccountError(400, "bad_email", "That does not look like an email address.")
    if not allow(f"link-ip:{_mac('ip', ip).hex()}", CHECKS_PER_MIN):
        raise AccountError(429, "rate_limited", "Too many tries from here. Wait a few minutes.")
    token = secrets.token_urlsafe(32)
    ip_hash = _mac("ip", ip)

    def tx(c: psycopg.Connection) -> str:
        n_email, n_ip, n_day = c.execute(
            "select count(*) filter (where user_email = %s and created_at > now() - interval '1 hour'), "
            "count(*) filter (where ip_hash = %s and created_at > now() - interval '1 hour'), "
            "count(*) from accounts.login_links where created_at > now() - interval '1 day'",
            (email, ip_hash)).fetchone()
        if n_email >= PER_EMAIL_HOUR:
            return "email"
        if n_ip >= PER_IP_HOUR:
            return "ip"
        if n_day >= daily_max():
            return "day"
        c.execute("insert into accounts.login_links (token_hash, user_email, expires_at, ip_hash) "
                  f"values (%s, %s, now() + interval '{LINK_MINUTES} minutes', %s)", (_hash_token(token), email, ip_hash))
        return "ok"

    got = db.run_rw(tx)
    if got == "email":
        raise AccountError(429, "rate_limited", "Too many sign-in emails for this address. Try again in an hour.")
    if got == "ip":
        raise AccountError(429, "rate_limited", "Too many sign-in emails from here. Try again in an hour.")
    if got == "day":
        raise AccountError(429, "rate_limited", "Too many sign-ins today. Try again tomorrow.")
    m = mailer()
    try:
        if m is None:
            raise RuntimeError("no mailer")
        m.send(email, *_message(f"{public_url()}/account#signin={token}"))
    except Exception as exc:  # noqa: BLE001 - the class only: never the link, the address or the answer's body
        log.warning("accounts: the sign-in email was not sent (%s)", exc.__class__.__name__)
        db.run_rw(lambda c: c.execute("delete from accounts.login_links where token_hash = %s", (_hash_token(token),)))
        raise AccountError(502, "mail_failed", "We could not send the email. Try again in a few minutes.") from None


def verify(token: Any, ip: str, user_agent: str | None, attach_to: str | None = None) -> tuple[str, str]:
    """(session id, email) for a live link; the link is spent. AccountError 400 `link_invalid` otherwise.
    ---- IM-4: `attach_to` = a signed-in account with no email (a passkey-only one): the link's address is **added** to it
    (a second way in) when no other account has that address; when one has, 409 `email_taken` and the link is not spent."""
    _require_email()
    if not allow(f"check-ip:{_mac('ip', ip).hex()}", CHECKS_PER_MIN):
        raise AccountError(429, "rate_limited", "Too many tries from here. Wait a few minutes.")
    bad = AccountError(400, "link_invalid", "That sign-in link has expired or was already used. Ask for a new one.")
    if not isinstance(token, str) or not _TOKEN.match(token):
        raise bad

    def tx(c: psycopg.Connection):
        if attach_to is not None:                                           # ---- IM-4: "add an email"
            live = c.execute("select user_email from accounts.login_links where token_hash = %s and used_at is null and "
                             "expires_at > now() for update", (_hash_token(token),)).fetchone()
            if live is not None and c.execute("select 1 from accounts.users where email = %s and id <> %s",
                                              (live[0], attach_to)).fetchone():
                return "taken"
        row = c.execute("update accounts.login_links set used_at = now() where token_hash = %s and used_at is null "
                        "and expires_at > now() returning user_email", (_hash_token(token),)).fetchone()
        if row is None:
            return None
        email = row[0]
        if attach_to is not None and c.execute(
                "update accounts.users set email = %s, last_seen_at = now() where id = %s and email is null and "
                "deleted_at is null", (email, attach_to)).rowcount == 1:
            return new_session(c, attach_to, user_agent), email
        uid = c.execute("insert into accounts.users (email, last_seen_at) values (%s, now()) on conflict (email) do "
                        "update set last_seen_at = now(), deleted_at = null returning id", (email,)).fetchone()[0]
        return new_session(c, str(uid), user_agent), email

    got = db.run_rw(tx)
    if got is None:
        raise bad
    if got == "taken":
        raise AccountError(409, "email_taken", "That email already has its own account. Sign out, then open the link "
                           "again to sign in to that account.")
    return got


def new_session(c: psycopg.Connection, user_id: str, user_agent: str | None) -> str:
    """A session row (90 days) — ---- IM-4 fix: and at most `MAX_SESSIONS` live ones per account (the oldest go: a
    script signing in in a loop cannot grow the table; a person has a few devices)."""
    sid = str(c.execute(f"insert into accounts.sessions (user_id, expires_at, user_agent_family) values (%s, now() + "
                        f"interval '{SESSION_DAYS} days', %s) returning id", (user_id, agent_family(user_agent))).fetchone()[0])
    c.execute("delete from accounts.sessions where id in (select id from accounts.sessions where user_id = %s "
              "order by created_at desc, id offset %s)", (user_id, MAX_SESSIONS))
    return sid


def current_user(request: Request) -> tuple[str, str, str] | None:
    """(user id, email, session id) for a live session cookie, else None."""
    sid = session_id_from(request.cookies.get(COOKIE))
    if sid is None:
        return None
    row = db.run_rw(lambda c: c.execute(
        "select s.user_id, u.email from accounts.sessions s join accounts.users u on u.id = s.user_id "
        "where s.id = %s and s.revoked_at is null and s.expires_at > now() and u.deleted_at is null", (sid,)).fetchone())
    return None if row is None else (str(row[0]), row[1], sid)


def _user(request: Request, *, write: bool = False) -> tuple[str, str, str]:
    _require_on()
    who = current_user(request)
    if who is None:
        raise _signed_out()
    if write and not allow(f"write:{who[2]}", WRITES_PER_MIN):
        raise AccountError(429, "rate_limited", "Too many changes at once. Wait a minute.")
    return who


def _team_id(v: Any) -> str | None:
    if v is None or isinstance(v, bool):
        return None
    s = str(v).strip()
    if not _TEAM_ID.match(s):
        raise AccountError(400, "bad_team", "That team id is not one we can save.")
    return s


def _short(v: Any, n: int) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s[:n] if s else None


def _rosters(v: Any) -> int | None:
    try:
        n = int(v)
    except (TypeError, ValueError):
        return None
    return n if 1 <= n <= 64 else None


def me(user_id: str, email: str | None) -> dict:
    pk = passkeys_ready()                                                    # ---- IM-4

    def tx(c: psycopg.Connection) -> dict:
        c.execute("update accounts.users set last_seen_at = now() where id = %s and (last_seen_at is null or "
                  "last_seen_at < now() - interval '1 hour')", (user_id,))
        created = c.execute("select created_at from accounts.users where id = %s", (user_id,)).fetchone()
        leagues = c.execute(
            "select ul.league_key, l.provider, l.season, l.external_id, ul.name, ul.team_external_id, ul.team_name, "
            "ul.scoring_label, ul.total_rosters, ul.is_default, l.last_sync_at, l.sync_status, ul.added_at "
            "from accounts.user_leagues ul join accounts.leagues l on l.league_key = ul.league_key "
            "where ul.user_id = %s and not ul.hidden order by ul.is_default desc, ul.added_at, ul.league_key",
            (user_id,)).fetchall()
        prefs = c.execute("select scope, key, value, updated_at from accounts.preferences where user_id = %s "
                          "order by scope, key", (user_id,)).fetchall()
        watch = c.execute("select league_key, player_key, added_at from accounts.watchlist where user_id = %s "
                          "order by added_at, player_key", (user_id,)).fetchall()
        from . import connections, passkeys  # IL-5: never a secret; IM-4: labels and dates, never a key
        return {"created": created[0] if created else None, "leagues": leagues, "prefs": prefs, "watch": watch,
                "connections": connections.listing(c, user_id), "passkeys": passkeys.listing(c, user_id) if pk else []}

    got = db.run_rw(tx)
    rows = []
    for (key, provider, season, ext, name, team, team_name, scoring, total, is_default, sync_at, sync_status,
         added) in got["leagues"]:
        rows.append({"league": app_key(key), "league_key": key, "provider": provider, "season": season,
                     "external_id": ext, "name": name, "team_id": int(team) if team and team.isdigit() else team,
                     "team_name": team_name, "scoring_label": scoring, "total_rosters": total,
                     "is_default": bool(is_default), "last_sync_at": _iso(sync_at), "sync_status": sync_status,
                     "added_at": _iso(added)})
    default = next((r["league"] for r in rows if r["is_default"]), None)
    return {"email": email, "created_at": _iso(got["created"]), "default_league": default, "leagues": rows,
            "preferences": [{"scope": s, "key": k, "value": v, "updated_at": _iso(t)} for s, k, v, t in got["prefs"]],
            "watchlist": [{"league_key": lk, "league": app_key(lk) if lk else None, "player_key": pk,
                           "added_at": _iso(t)} for lk, pk, t in got["watch"]],
            "connections": got["connections"],                             # ---- IL-5
            "passkeys": got["passkeys"],                                   # ---- IM-4
            "sign_in": {"passkeys": len(got["passkeys"]), "email": bool(email) and mailer() is not None}}


def _iso(t) -> str | None:
    return None if t is None else t.isoformat()


def save_leagues(user_id: str, items: list[LeagueIn]) -> int:
    if len(items) > MAX_LEAGUES:
        raise AccountError(400, "too_many", f"An account keeps at most {MAX_LEAGUES} leagues.")
    rows = []
    for it in items:
        try:
            key = league_key(it.league, it.season)
        except ValueError:
            raise AccountError(400, "bad_league", "That is not a league id we know how to save.") from None
        provider, season, ext = key.split(":", 2)
        fields = it.model_fields_set
        rows.append({"key": key, "provider": provider, "season": int(season), "ext": ext,
                     "set_team": "team_id" in fields, "team": _team_id(it.team_id),
                     "name": _short(it.name, 120), "team_name": _short(it.team_name, 120),
                     "scoring": _short(it.scoring_label, 160), "total": _rosters(it.total_rosters),
                     "default": bool(it.default)})

    def tx(c: psycopg.Connection) -> int:
        for r in rows:
            c.execute("insert into accounts.leagues (league_key, provider, season, external_id) values (%s, %s, %s, %s) "
                      "on conflict (league_key) do update set updated_at = now()",
                      (r["key"], r["provider"], r["season"], r["ext"]))
            c.execute(
                "insert into accounts.user_leagues (user_id, league_key, team_external_id, name, team_name, "
                "scoring_label, total_rosters, added_at) values (%(u)s, %(key)s, %(team)s, %(name)s, %(team_name)s, "
                "%(scoring)s, %(total)s, clock_timestamp()) on conflict (user_id, league_key) do update set "
                "team_external_id = case when %(set_team)s then excluded.team_external_id "
                "else accounts.user_leagues.team_external_id end, "
                "team_name = case when %(set_team)s then excluded.team_name "
                "else coalesce(excluded.team_name, accounts.user_leagues.team_name) end, "
                "name = coalesce(excluded.name, accounts.user_leagues.name), "
                "scoring_label = coalesce(excluded.scoring_label, accounts.user_leagues.scoring_label), "
                "total_rosters = coalesce(excluded.total_rosters, accounts.user_leagues.total_rosters), "
                "hidden = false, updated_at = now()", {**r, "u": user_id})
        n = c.execute("select count(*) from accounts.user_leagues where user_id = %s", (user_id,)).fetchone()[0]
        if n > MAX_LEAGUES:
            raise AccountError(400, "too_many", f"An account keeps at most {MAX_LEAGUES} leagues.")
        want = next((r["key"] for r in reversed(rows) if r["default"]), None)
        has = c.execute("select 1 from accounts.user_leagues where user_id = %s and is_default", (user_id,)).fetchone()
        if want is None and has is None and rows:
            want = rows[0]["key"]                     # the first league saved is the default until another is chosen
        if want is not None:
            _set_default(c, user_id, want)
        return len(rows)

    return db.run_rw(tx)


def _set_default(c: psycopg.Connection, user_id: str, key: str) -> bool:
    c.execute("update accounts.user_leagues set is_default = false where user_id = %s and is_default and "
              "league_key <> %s", (user_id, key))
    return c.execute("update accounts.user_leagues set is_default = true where user_id = %s and league_key = %s",
                     (user_id, key)).rowcount == 1


def _key_or_400(league: Any, season: Any = None) -> str:
    try:
        return league_key(league, season)
    except ValueError:
        raise AccountError(400, "bad_league", "That is not a league id we know how to save.") from None


def set_default(user_id: str, league: Any, season: Any = None) -> None:
    key = _key_or_400(league, season)
    if not db.run_rw(lambda c: _set_default(c, user_id, key)):
        raise AccountError(404, "not_saved", "That league is not saved to your account.")


def remove_league(user_id: str, league: Any, season: Any = None) -> None:
    key = _key_or_400(league, season)

    def tx(c: psycopg.Connection) -> int:
        n = c.execute("delete from accounts.user_leagues where user_id = %s and league_key = %s",
                      (user_id, key)).rowcount
        if n and c.execute("select 1 from accounts.user_leagues where user_id = %s and is_default",
                           (user_id,)).fetchone() is None:
            first = c.execute("select league_key from accounts.user_leagues where user_id = %s order by added_at, "
                              "league_key limit 1", (user_id,)).fetchone()
            if first:
                _set_default(c, user_id, first[0])
        return n

    if not db.run_rw(tx):
        raise AccountError(404, "not_saved", "That league is not saved to your account.")


def _scope(scope: Any) -> str:
    s = str(scope or "global").strip()
    if s == "global":
        return s
    return _key_or_400(s)


def put_preference(user_id: str, scope: Any, key: Any, value: Any) -> None:
    sc = _scope(scope)
    if not isinstance(key, str) or not _PREF_KEY.match(key):
        raise AccountError(400, "bad_key", "That preference name is not one we can save.")
    raw = json.dumps(value, separators=(",", ":"))
    if len(raw.encode()) > MAX_VALUE_BYTES:
        raise AccountError(400, "too_big", "That preference is too big to save (8 KB at most).")

    def tx(c: psycopg.Connection) -> None:
        c.execute("insert into accounts.preferences (user_id, scope, key, value) values (%s, %s, %s, %s::jsonb) "
                  "on conflict (user_id, scope, key) do update set value = excluded.value, updated_at = now()",
                  (user_id, sc, key, raw))
        if c.execute("select count(*) from accounts.preferences where user_id = %s", (user_id,)).fetchone()[0] > MAX_PREFS:
            raise AccountError(400, "too_many", f"An account keeps at most {MAX_PREFS} preferences.")

    db.run_rw(tx)


def delete_preference(user_id: str, scope: Any, key: Any) -> None:
    sc = _scope(scope)
    db.run_rw(lambda c: c.execute("delete from accounts.preferences where user_id = %s and scope = %s and key = %s",
                                  (user_id, sc, str(key or ""))))


def _watch_args(player_key: Any, league: Any) -> tuple[str | None, str]:
    pk = str(player_key or "").strip()
    if not _PLAYER_KEY.match(pk):
        raise AccountError(400, "bad_player", "That player id is not one we can save.")
    lk = _key_or_400(league) if league not in (None, "") else None
    return lk, pk


def watch(user_id: str, player_key: Any, league: Any = None) -> None:
    lk, pk = _watch_args(player_key, league)

    def tx(c: psycopg.Connection) -> None:
        c.execute("insert into accounts.watchlist (user_id, league_key, player_key) values (%s, %s, %s) "
                  "on conflict (user_id, league_key, player_key) do nothing", (user_id, lk, pk))
        if c.execute("select count(*) from accounts.watchlist where user_id = %s", (user_id,)).fetchone()[0] > MAX_WATCH:
            raise AccountError(400, "too_many", f"A watchlist keeps at most {MAX_WATCH} players.")

    db.run_rw(tx)


def unwatch(user_id: str, player_key: Any, league: Any = None) -> None:
    lk, pk = _watch_args(player_key, league)
    db.run_rw(lambda c: c.execute("delete from accounts.watchlist where user_id = %s and league_key is not distinct "
                                  "from %s and player_key = %s", (user_id, lk, pk)))


def sign_out(user_id: str, session_id: str, everywhere: bool) -> int:
    if everywhere:
        return db.run_rw(lambda c: c.execute("update accounts.sessions set revoked_at = now() where user_id = %s and "
                                             "revoked_at is null", (user_id,)).rowcount)
    return db.run_rw(lambda c: c.execute("update accounts.sessions set revoked_at = now() where id = %s and "
                                         "revoked_at is null", (session_id,)).rowcount)


def delete_account(user_id: str, email: str) -> None:
    def tx(c: psycopg.Connection) -> None:
        c.execute("delete from accounts.users where id = %s", (user_id,))          # cascades: every row of the user
        c.execute("delete from accounts.login_links where user_email = %s", (email,))

    db.run_rw(tx)


# ---------------------------------------------------------------- same site (---- IM-4)
SAFE_METHODS = ("GET", "HEAD", "OPTIONS")


def _cross_site() -> AccountError:
    """---- IM-4 fix: the same words and code as IM-3's Guard (security.CROSS_SITE), whichever layer refuses."""
    try:
        from .security import CROSS_SITE as words
    except ImportError:  # pragma: no cover - a tree without IM-3's module
        words = "This request came from another site, so it was refused."
    return AccountError(403, "cross_site", words)


def same_site(request: Request) -> None:
    """Refuse a state-changing request that a browser says comes from another site (login CSRF, a forged "delete my
    account"). A browser sends `Sec-Fetch-Site` and / or `Origin` on every POST, PUT and DELETE, and a page cannot
    forge either; a request with neither is not from a browser, so it carries nobody's cookie by accident.
      * an `Origin` (every browser sends one on these) must be an allowed origin or this request's own host
        (`Origin: null` never is) — whatever `Sec-Fetch-Site` says;
      * no `Origin`: `Sec-Fetch-Site: cross-site` is refused.
    The same rule as IM-3's Guard (security.cross_site), which runs first on the merged server; this one holds by
    itself when the Guard is absent or off (---- IM-4 fix: Origin first, as the Guard; the Guard's words).
    Allowed origins: `LEAGUE_LAB_PASSKEY_ORIGINS` (passkeys.allowed_origins: https only, `http://localhost` under the
    test switch) and `LEAGUE_LAB_PUBLIC_URL`."""
    if request.method in SAFE_METHODS:
        return
    site = (request.headers.get("sec-fetch-site") or "").strip().lower()
    origin = request.headers.get("origin")
    if origin is None:
        if site == "cross-site":
            raise _cross_site()
        return
    from . import passkeys
    o = passkeys.normal_origin(origin)
    if o is not None and (passkeys.site_for(o) is not None or o == passkeys.normal_origin(public_url())
                          or o.split("://", 1)[1] == (request.headers.get("host") or "").strip().lower()):
        return
    raise _cross_site()


# ---------------------------------------------------------------- the routes (main.py: app.include_router)
router = APIRouter(prefix="/api/account", dependencies=[Depends(same_site)])   # ---- IM-4: the guard
NO_STORE = {"Cache-Control": "no-store"}


class LoginIn(BaseModel):
    email: str = Field(default="", max_length=320)


class VerifyIn(BaseModel):
    token: str = Field(default="", max_length=200)


class LogoutIn(BaseModel):
    everywhere: bool = False


class LeagueIn(BaseModel):
    league: str = Field(max_length=80)
    season: int | None = None
    name: str | None = Field(default=None, max_length=400)
    team_id: int | str | None = None
    team_name: str | None = Field(default=None, max_length=400)
    scoring_label: str | None = Field(default=None, max_length=400)
    total_rosters: int | None = None
    default: bool = False


class LeaguesIn(BaseModel):
    leagues: list[LeagueIn] = Field(default_factory=list, max_length=MAX_LEAGUES + 1)


class DefaultIn(BaseModel):
    league: str = Field(max_length=80)
    season: int | None = None


class PreferenceIn(BaseModel):
    scope: str = Field(default="global", max_length=80)
    key: str = Field(max_length=64)
    value: Any = None


class WatchIn(BaseModel):
    player_key: str = Field(max_length=60)
    league: str | None = Field(default=None, max_length=80)


def _ok(body: dict | None = None, status: int = 200) -> JSONResponse:
    return JSONResponse({"ok": True, **(body or {})}, status_code=status, headers=NO_STORE)


def _secure(request: Request) -> bool:
    return request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"


def _set_cookie(resp: Response, request: Request, session_id: str) -> None:
    resp.set_cookie(COOKIE, cookie_value(session_id), max_age=SESSION_DAYS * 86400, httponly=True, samesite="lax",
                    secure=_secure(request), path=COOKIE_PATH)


def _drop_cookie(resp: Response) -> None:
    resp.delete_cookie(COOKIE, path=COOKIE_PATH)
    resp.delete_cookie(COOKIE, path=LEGACY_COOKIE_PATH)                  # ---- IL-5


@router.get("/status")
def status_route(request: Request) -> JSONResponse:
    on, why = state()
    out: dict = {"enabled": on, "reason": why, "signed_in": False, "email": None, "mailer": None,
                 "session_days": SESSION_DAYS}
    if mode() != "off" and _secret():                                      # ---- IM-4: the methods and why not
        from . import passkeys
        w = why_not() if schema_ready() else {"passkey": "not_ready", "email": None if mailer() else "no_mailer"}
        out.update(methods=[k for k in ("passkey", "email") if w[k] is None] if on else [], why=w,
                   passkey_home=passkeys.home(), passkey_here=passkeys.request_site(request) is not None)
    else:
        out.update(methods=[], why={"passkey": why, "email": why}, passkey_home=None, passkey_here=False)
    if on:
        m = mailer()
        out["mailer"] = m.name if m else None
        try:
            who = current_user(request)
        except psycopg.Error:
            who = None
        if who is not None:
            out.update(signed_in=True, email=who[1])
    return JSONResponse(out, headers=NO_STORE)


@router.post("/login", status_code=202)
def login_route(body: LoginIn, request: Request) -> JSONResponse:
    request_link(body.email, client_ip(request))
    return _ok({"sent": True, "minutes": LINK_MINUTES}, status=202)


@router.post("/verify")
def verify_route(body: VerifyIn, request: Request) -> JSONResponse:
    try:                                          # ---- IM-4: signed in with no email: the link adds the address
        who = current_user(request) if state()[0] else None
    except psycopg.Error:
        who = None
    attach = who[0] if who is not None and not who[1] else None
    sid, email = verify(body.token, client_ip(request), request.headers.get("user-agent"), attach_to=attach)
    uid = db.run_rw(lambda c: c.execute("select user_id from accounts.sessions where id = %s", (sid,)).fetchone()[0])
    resp = _ok({"email": email, "added": True} if attach and str(uid) == attach else {"email": email})
    _set_cookie(resp, request, sid)
    # ---- IL-5: this device's Yahoo / ESPN connection joins the account; the account's come back to this device
    from . import connections
    connections.sync(request, resp, str(uid), adopt=True)
    # ---- end IL-5
    return resp


@router.post("/logout")
def logout_route(request: Request, body: LogoutIn | None = None) -> JSONResponse:
    n = 0
    if state()[0]:
        who = current_user(request)
        if who is not None:
            n = sign_out(who[0], who[2], bool(body and body.everywhere))
    resp = _ok({"revoked": n})
    _drop_cookie(resp)
    return resp


@router.get("/me")
def me_route(request: Request) -> JSONResponse:
    uid, email, _sid = _user(request)
    resp = JSONResponse(me(uid, email), headers=NO_STORE)
    from . import connections  # ---- IL-5: the restore (cookie missing)
    connections.sync(request, resp, uid, adopt=False)
    return resp


@router.put("/leagues")
def leagues_route(body: LeaguesIn, request: Request) -> JSONResponse:
    uid, _email, _sid = _user(request, write=True)
    return _ok({"saved": save_leagues(uid, body.leagues)})


@router.delete("/leagues/{league}")
def league_delete_route(league: str, request: Request, season: int | None = None) -> JSONResponse:
    uid, _email, _sid = _user(request, write=True)
    remove_league(uid, league, season)
    return _ok()


@router.put("/default")
def default_route(body: DefaultIn, request: Request) -> JSONResponse:
    uid, _email, _sid = _user(request, write=True)
    set_default(uid, body.league, body.season)
    return _ok()


@router.put("/preferences")
def preference_route(body: PreferenceIn, request: Request) -> JSONResponse:
    uid, _email, _sid = _user(request, write=True)
    put_preference(uid, body.scope, body.key, body.value)
    return _ok()


@router.delete("/preferences")
def preference_delete_route(request: Request, key: str, scope: str = "global") -> JSONResponse:
    uid, _email, _sid = _user(request, write=True)
    delete_preference(uid, scope, key)
    return _ok()


@router.put("/watchlist")
def watch_route(body: WatchIn, request: Request) -> JSONResponse:
    uid, _email, _sid = _user(request, write=True)
    watch(uid, body.player_key, body.league)
    return _ok()


@router.delete("/watchlist")
def unwatch_route(request: Request, player_key: str, league: str | None = None) -> JSONResponse:
    uid, _email, _sid = _user(request, write=True)
    unwatch(uid, player_key, league)
    return _ok()


@router.delete("")
def delete_route(request: Request) -> JSONResponse:
    uid, email, _sid = _user(request, write=True)
    delete_account(uid, email)
    resp = _ok({"deleted": True})
    _drop_cookie(resp)
    return resp


def error_response(exc: AccountError) -> JSONResponse:
    headers = dict(NO_STORE)
    if exc.status == 429:
        headers["Retry-After"] = "3600" if "hour" in exc.words or "tomorrow" in exc.words else "60"
    return JSONResponse({"error": exc.words, "detail": exc.words, "code": exc.code}, status_code=exc.status,
                        headers=headers)


# ---- IM-4 (Wave I-M): passkeys — passkeys.py adds its routes to `router` (above) when it loads; main.py includes the
# router after importing this module, so the routes are there whichever module Python loads first.
from . import passkeys as _passkeys  # noqa: E402,F401 - registers /api/account/passkey/* and /api/account/passkeys/*
# ---- end IM-4
