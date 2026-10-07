"""Yahoo Fantasy Sports, read-only (Wave I-K, IK-2): OAuth 2.0, the Fantasy Sports API v2, and the translation helpers.

The rest of League Lab only sees **Sleeper shapes**; ``yahoo_leagues.YahooLeagues`` turns what this module reads into
them. Sources (read 2026-10-05 through WebFetch; nothing was sent to Yahoo from here): Yahoo's OAuth 2.0 guide
(developer.yahoo.com/oauth2/guide/ and /flows_authcode/), the Fantasy Sports API docs (sports.yahoo.com/developer/docs/,
the page developer.yahoo.com/fantasysports/guide/ redirects to), and the JSON nesting the open-source clients ``yfpy``
and ``yahoo_fantasy_api`` document. Everything here is **unverified against a live Yahoo league** until the PO opens one.

* **OAuth 2.0, authorization-code grant only** (the guide lists no other grant: no client-credentials / app-only
  token, so **a public league is not readable without a signed-in Yahoo user** — any signed-in user can read any public
  league, and private leagues they are in): ``authorize_url`` -> ``https://api.login.yahoo.com/oauth2/request_auth``
  (``client_id``, ``redirect_uri``, ``response_type=code``, ``state``, ``scope=fspt-r``); ``exchange_code`` and
  ``refresh`` POST ``…/oauth2/get_token`` with ``Authorization: Basic base64(client_id:client_secret)`` and a form body
  (``grant_type=authorization_code`` + ``code`` + ``redirect_uri`` / ``grant_type=refresh_token`` + ``refresh_token``);
  the client id / secret also in the body, as the guide lists them; the refresh sends the registered redirect URI
  (``LEAGUE_LAB_YAHOO_REDIRECT_URI``) or ``oob``); the answer: ``access_token`` (1 hour), ``refresh_token``, ``expires_in``,
  ``xoauth_yahoo_guid``. ``LEAGUE_LAB_YAHOO_SCOPE`` (set empty) drops the ``scope`` parameter. The credentials are
  ``LEAGUE_LAB_YAHOO_CLIENT_ID`` / ``LEAGUE_LAB_YAHOO_CLIENT_SECRET``; without them (and outside fixture mode) Yahoo is
  "not configured" (``YahooNotConfigured``, code ``yahoo_not_configured``).
* **Who reads**: a request's ``YahooSession`` (refresh token, access token, expiry, guid) sits in the context variable
  ``request_session`` — the API's middleware (``api/league_lab_api/yahoo_connect.py``) fills it from the encrypted
  ``ll_yahoo`` cookie; tokens live only there (never logged, never stored server-side). An access token within a minute
  of expiry (or a 401 ``token_expired``) is refreshed once in place and the session marked ``changed`` (the middleware
  re-sets the cookie); a refused refresh marks it ``expired`` (the cookie is cleared) -> ``YahooSessionExpired``.
* **The API**: ``https://fantasysports.yahooapis.com/fantasy/v2/<resource>?format=json`` with ``Authorization: Bearer``:
  ``game/nfl`` (this season's game key), ``game/<key>/game_weeks``, ``league/<key>/settings`` / ``teams`` /
  ``standings`` / ``scoreboard;week=<w>`` / ``transactions`` / ``players;status=FA;sort=AR;start=<n>;count=25``,
  ``team/<team_key>/roster;week=<w>/players``, ``users;use_login=1/games;game_keys=nfl/leagues`` and ``…/teams``.
  Keys: game ``461`` (or the code ``nfl``, which Yahoo resolves to this season's), league ``461.l.4242``, team
  ``461.l.4242.t.3``, player ``461.p.30121`` (the number is nflverse's ``yahoo_id``).
* **Caches by kind** (``TTL_S``, all far inside Yahoo's 24-hour storage rule), in memory only: keyed by *who* read (a
  hash of the refresh token), so a private league read with one manager's token is never served to another (Yahoo's
  terms § 2: no third-party access to a user's data); stale on error; at most ``MAX_ENTRIES`` answers (expired ones go
  first, then the oldest) so many managers cannot grow the 512 MB server.
* **Budget**: a token bucket of ``LEAGUE_LAB_YAHOO_PER_MIN`` calls a minute (default 60; Yahoo throttles "excessive"
  use without a published number); HTTP 429 or 999 backs off a minute (``YahooBusy``).
* **One normaliser** (``normalise``): Yahoo's JSON is XML turned inside out — collections are ``{"0": {...}, "1":
  {...}, "count": n}``, a resource is a list of a metadata list (single-key dicts and empty lists) and sub-resource
  dicts. ``normalise`` makes collections lists and merges a list of disjoint dicts into one dict; ``items`` reads a
  collection whatever shape it came in.
* **Fixtures**: ``LEAGUE_LAB_YAHOO_FIXTURES=<dir>`` reads ``<dir>/<slug of the resource path>.json`` (``fixture_name``)
  instead of Yahoo, through the same caches and bucket, and the token endpoint answers a fixture token for the code
  ``fixture``; a resource with no file answers as Yahoo does for a league you are not in.

Translation (pure, tested): ``STAT_KEYS`` (Yahoo's NFL stat ids -> Sleeper scoring keys; the table below),
``scoring(settings)``, ``slots(settings)`` (``W/R/T`` -> FLEX, ``Q/W/R/T`` -> SUPER_FLEX, ``W/R`` -> WRRB_FLEX, ``W/T``
-> REC_FLEX; IDP slots left out and said so), ``team_code`` (Yahoo's ``Jax`` / ``Was`` -> Sleeper's ``JAX`` / ``WAS``).
"""

from __future__ import annotations

import base64
import contextvars
import hashlib
import json
import logging
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import provider_trouble  # ---- IP-5 fix round: refusals noted, held answers bounded
from .sleeper_client import LeagueNotFound, SleeperBusy, SleeperUnavailable, TokenBucket

AUTH_URL = "https://api.login.yahoo.com/oauth2/request_auth"
TOKEN_URL = "https://api.login.yahoo.com/oauth2/get_token"
API = "https://fantasysports.yahooapis.com/fantasy/v2"
SCOPE = "fspt-r"                                        # Fantasy Sports, read
FIXTURES_ENV = "LEAGUE_LAB_YAHOO_FIXTURES"
CLIENT_ID_ENV = "LEAGUE_LAB_YAHOO_CLIENT_ID"
CLIENT_SECRET_ENV = "LEAGUE_LAB_YAHOO_CLIENT_SECRET"
PER_MIN_ENV = "LEAGUE_LAB_YAHOO_PER_MIN"
SCOPE_ENV = "LEAGUE_LAB_YAHOO_SCOPE"
REDIRECT_ENV = "LEAGUE_LAB_YAHOO_REDIRECT_URI"
DEFAULT_PER_MIN = 60
MAX_ENTRIES = 400          # cached answers held at most (a league open is ~18: settings, teams, 12 rosters, …)
USER_AGENT = "league-lab/0.1 (isuckatfantasy beta; docs/YAHOO_TERMS.md)"
log = logging.getLogger(__name__)
FIXTURE_CODE = "fixture"

TTL_S: dict[str, float] = {
    "game": 24 * 3600, "game_weeks": 24 * 3600, "settings": 3600, "teams": 10 * 60, "standings": 10 * 60,
    "roster": 5 * 60, "scoreboard": 5 * 60, "transactions": 5 * 60, "players": 15 * 60, "user": 10 * 60,
}
_LEAGUE_KEY = re.compile(r"^(\d{1,4}|nfl)\.l\.(\d{1,10})$", re.I)
_TEAM_KEY = re.compile(r"^(\d{1,4})\.l\.(\d{1,10})\.t\.(\d{1,3})$")
_LINK = re.compile(r"football\.fantasysports\.yahoo\.com/(?:\d{4}/)?f1/(\d{1,10})(?:/(\d{1,3}))?", re.I)


# ====================================================================================== errors (II-5's setup codes)
class _Coded:
    code = "provider_down"
    words = ""
    fix: str | None = None


class YahooNotConfigured(_Coded, RuntimeError):
    code = "yahoo_not_configured"
    words = "Yahoo sign-in is not set up on this server yet"
    fix = "Yahoo leagues are coming soon. Sleeper and MyFantasyLeague leagues work today."

    def __init__(self, msg: str | None = None) -> None:
        super().__init__(msg or self.words)


# ---- PO 2026-10-05 (a friend's public league, "private or does not exist"): Yahoo answered the APP, not the league.
# Since August 2026 Yahoo no longer gives a new app the Fantasy Sports API by itself: the sign-in works, the tokens are
# valid, and every Fantasy call is refused (HTTP 401 / 403, ``oauth_problem="additional_authorization_required"``)
# until Yahoo approves the access application and adds the client id to its allowlist (sports.yahoo.com/developer/access;
# docs/HOSTING.md § Yahoo, step 1.4). That is "coming soon" (the not-configured code every route already answers in
# words), never "your connection has expired" or "your league is private".
class YahooAccessPending(YahooNotConfigured):
    words = "Yahoo leagues are not open here yet: Yahoo has not switched on this app's access to fantasy data"
    fix = ("Nothing is wrong with your league or your Yahoo sign-in. Yahoo leagues are coming soon; Sleeper and "
           "MyFantasyLeague leagues work today.")


class YahooSignInRequired(_Coded, LeagueNotFound):
    code = "yahoo_sign_in_required"
    words = "Connect your Yahoo account to open Yahoo leagues."
    fix = ("Yahoo only shares a league with a signed-in Yahoo user (even a public league): Connect with Yahoo, then "
           "pick your league.")

    def __init__(self, msg: str | None = None) -> None:
        super().__init__(msg or self.words)


class YahooSessionExpired(YahooSignInRequired):
    code = "yahoo_session_expired"
    words = "Your Yahoo connection has expired."
    fix = "Connect with Yahoo again: it takes a few seconds and your leagues come back."


class YahooLeagueNotFound(_Coded, LeagueNotFound):
    code = "yahoo_league_unknown"
    fix = ("Yahoo shares a private league only with its members, and any public league. Check the link, or pick the "
           "league from your list after you connect.")

    def __init__(self, league_key: str | None = None) -> None:
        self.words = (f"Yahoo league {league_key} is private or does not exist." if league_key
                      else "That Yahoo league is private or does not exist.")
        super().__init__(self.words)


class YahooLinkInvalid(_Coded, LeagueNotFound):
    code = "yahoo_link_invalid"
    words = "That is not a Yahoo league link or key."
    fix = ("Paste your league's address from the Yahoo website (football.fantasysports.yahoo.com/f1/12345), or connect "
           "with Yahoo and pick it from your list.")

    def __init__(self, msg: str | None = None) -> None:
        super().__init__(msg or self.words)


class YahooBusy(_Coded, SleeperBusy):
    code = "busy"
    words = "busy, try again in a minute"


class YahooUnavailable(_Coded, SleeperUnavailable):
    code = "provider_down"
    words = "Yahoo did not answer. Try again in a minute."


def setup_parts(exc: BaseException) -> tuple[str, str, str | None]:
    """(code, words, fix) for II-5's ``SetupError`` from any error this module raises."""
    if isinstance(exc, _Coded):
        return exc.code, (getattr(exc, "words", "") or str(exc)), exc.fix
    if isinstance(exc, LeagueNotFound):
        return "yahoo_league_unknown", str(exc), YahooLeagueNotFound.fix
    return "provider_down", YahooUnavailable.words, None


# ====================================================================================== keys and links
def check_league_key(text: str) -> str:
    """``461.l.4242`` (or ``nfl.l.4242``) -> itself, lower-cased; anything else is ``YahooLinkInvalid``."""
    s = str(text or "").strip().lower()
    if s.startswith("yahoo:"):
        s = s[6:].strip()
    if not _LEAGUE_KEY.match(s):
        raise YahooLinkInvalid(f"not a Yahoo league key: {text!r}")
    return s


def parse_link(text: str) -> tuple[str, int | None]:
    """A pasted Yahoo link or key -> (league key, team id or None). ``football.fantasysports.yahoo.com/f1/4242/3`` ->
    (``nfl.l.4242``, 3) — the code ``nfl`` stands for this season's game (``Yahoo.resolve`` makes it numeric);
    ``461.l.4242`` / ``yahoo:461.l.4242`` / ``461.l.4242.t.3`` as they are."""
    s = str(text or "").strip()
    m = _LINK.search(s)
    if m:
        return f"nfl.l.{m.group(1)}", int(m.group(2)) if m.group(2) else None
    low = s.lower().removeprefix("yahoo:").strip()
    t = _TEAM_KEY.match(low)
    if t:
        return f"{t.group(1)}.l.{t.group(2)}", int(t.group(3))
    return check_league_key(low), None


def team_key(league_key: str, team_id: int | str) -> str:
    return f"{league_key}.t.{int(team_id)}"


def team_id_of(team_key_: str) -> int:
    return int(str(team_key_).rsplit(".t.", 1)[1])


def player_id_of(player_key: str) -> str:
    """``461.p.30121`` -> ``30121`` (nflverse's ``yahoo_id``)."""
    return str(player_key).rsplit(".p.", 1)[-1]


def fixture_name(path: str) -> str:
    """The fixture file of a resource path: ``league/461.l.4242/scoreboard;week=3`` ->
    ``league_461.l.4242_scoreboard_week_3.json``."""
    return re.sub(r"[^A-Za-z0-9.]+", "_", path).strip("_") + ".json"


# ====================================================================================== the session (OAuth)
@dataclass
class YahooSession:
    """One manager's Yahoo connection, as the ``ll_yahoo`` cookie holds it. ``changed``: refreshed during this
    request (the cookie is re-set); ``expired``: Yahoo refused the refresh (the cookie is cleared)."""
    refresh_token: str
    access_token: str = ""
    expires_at: float = 0.0
    guid: str | None = None
    changed: bool = False
    expired: bool = False

    def who(self) -> str:
        return hashlib.sha256(("yahoo|" + self.refresh_token).encode()).hexdigest()[:16]

    def to_cookie(self) -> dict:
        return {"r": self.refresh_token, "a": self.access_token, "e": int(self.expires_at), "g": self.guid}

    @classmethod
    def from_cookie(cls, d: Mapping) -> YahooSession | None:
        r = d.get("r") if isinstance(d, Mapping) else None
        if not r or not isinstance(r, str):
            return None
        return cls(refresh_token=r, access_token=str(d.get("a") or ""), expires_at=float(d.get("e") or 0),
                   guid=(str(d["g"]) if d.get("g") else None))

    def __repr__(self) -> str:                         # never the tokens (a log line, a traceback)
        return f"YahooSession(who={self.who()}, expires_at={int(self.expires_at)}, changed={self.changed})"


request_session: contextvars.ContextVar[YahooSession | None] = contextvars.ContextVar("yahoo_session", default=None)
# tests: replace the token endpoint (form dict, headers) -> (status, JSON body); None: HTTP to TOKEN_URL
TOKEN_POST: Callable[[dict, dict], tuple[int, dict]] | None = None


def fixtures_dir() -> Path | None:
    v = os.environ.get(FIXTURES_ENV)
    return Path(v) if v else None


def credentials() -> tuple[str, str]:
    cid, sec = os.environ.get(CLIENT_ID_ENV, "").strip(), os.environ.get(CLIENT_SECRET_ENV, "").strip()
    if fixtures_dir() is not None and not (cid and sec):
        return "fixture-client", "fixture-secret"
    if not cid or not sec:
        raise YahooNotConfigured()
    return cid, sec


def configured() -> bool:
    """Connect with Yahoo can work here: the two secrets are set (or fixture mode)."""
    try:
        credentials()
    except YahooNotConfigured:
        return False
    return True


# ---- PO 2026-10-05: is the Fantasy API open to this app? Two signals, either says "not yet" (the setup screen then
# says "coming soon" and invites nobody to connect; `/api/yahoo/connect` itself still works, so the operator can probe):
# * ``LEAGUE_LAB_YAHOO_ACCESS=pending`` (render.yaml) — what we know: set until `/api/yahoo/status?probe=1` answers ok;
# * the last refusal Yahoo gave this process for the app's entitlement, for ``ACCESS_RETRY_S`` (Yahoo can also take an
#   approved app's access away again: the screen follows without a deploy, and the next probe after the hour re-tests).
# ``access_report()`` is Yahoo's last non-200 answer (status, oauth_problem, the description's first words, the
# resource — never a token), for `/api/yahoo/status` and the log line.
ACCESS_ENV = "LEAGUE_LAB_YAHOO_ACCESS"
ACCESS_RETRY_S = 3600.0
_OAUTH_PROBLEM = re.compile(r'oauth_problem=\\?"?([a-z_]+)', re.I)     # in a header, or JSON-escaped in the body
_access: dict[str, Any] = {"pending_until": 0.0, "last": None, "ok_at": None}


def access_switch_pending() -> bool:
    return (os.environ.get(ACCESS_ENV) or "").strip().lower() in ("pending", "off")


def access_pending(wall: Callable[[], float] = time.time) -> bool:
    return access_switch_pending() or float(_access["pending_until"]) > wall()


def access_report() -> dict:
    return {"switch": "pending" if access_switch_pending() else "open", "pending": access_pending(),
            "last_refusal": _access["last"], "last_ok_at": _access["ok_at"]}


def reset_access() -> None:
    _access.update({"pending_until": 0.0, "last": None, "ok_at": None})


def oauth_problem(text: str, headers: Mapping | None = None) -> str | None:
    h = headers or {}
    m = _OAUTH_PROBLEM.search(f"{text or ''} {h.get('WWW-Authenticate') or h.get('www-authenticate') or ''}")
    return m.group(1).lower() if m else None


def _description(text: str) -> str:
    try:
        d = json.loads(text or "null")
        err = d.get("error") if isinstance(d, dict) else None
        s = (err.get("description") if isinstance(err, dict) else err) or ""
    except (json.JSONDecodeError, AttributeError):
        s = text or ""
    return " ".join(str(s).split())[:200]


def _note_refusal(path: str, status: int, problem: str | None, text: str, pending: bool,
                  wall: Callable[[], float] = time.time) -> None:
    now = wall()
    _access["last"] = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)), "status": int(status),
                       "problem": problem, "resource": path, "description": _description(text),
                       "access_pending": bool(pending)}
    if pending:
        _access["pending_until"] = now + ACCESS_RETRY_S
    log.warning("yahoo refused: HTTP %s problem=%s resource=%s pending=%s description=%r", status, problem, path,
                pending, _access["last"]["description"])


def scope() -> str:
    """``fspt-r`` (Fantasy Sports, read); ``LEAGUE_LAB_YAHOO_SCOPE`` overrides it — set it empty to send no scope (the
    app's registered permission then applies) if Yahoo ever refuses the parameter."""
    v = os.environ.get(SCOPE_ENV)
    return SCOPE if v is None else v.strip()


def redirect_uri_env() -> str | None:
    return (os.environ.get(REDIRECT_ENV) or "").strip() or None


def authorize_url(redirect_uri: str, state: str) -> str:
    cid, _ = credentials()
    q = {"client_id": cid, "redirect_uri": redirect_uri, "response_type": "code", "state": state}
    if scope():
        q["scope"] = scope()
    q["language"] = "en-us"
    return f"{AUTH_URL}?{urllib.parse.urlencode(q)}"


def _token_request(form: dict, wall: Callable[[], float] = time.time) -> dict:
    cid, sec = credentials()
    # Yahoo's guide lists the client id / secret in the body as well as in the Basic header: both are sent
    form = {**form, "client_id": cid, "client_secret": sec}
    headers = {"Authorization": "Basic " + base64.b64encode(f"{cid}:{sec}".encode()).decode(),
               "Content-Type": "application/x-www-form-urlencoded", "User-Agent": USER_AGENT}
    if TOKEN_POST is not None:
        status, body = TOKEN_POST(dict(form), headers)
    elif fixtures_dir() is not None:
        status, body = _fixture_token(form, wall)
    else:
        req = urllib.request.Request(TOKEN_URL, data=urllib.parse.urlencode(form).encode(), headers=headers,
                                     method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as r:  # noqa: S310 - fixed https host
                status, body = r.status, json.loads(r.read().decode("utf-8", "replace") or "{}")
        except urllib.error.HTTPError as exc:
            try:
                status, body = exc.code, json.loads(exc.read().decode("utf-8", "replace") or "{}")
            except (ValueError, OSError):
                status, body = exc.code, {}
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            raise YahooUnavailable(f"Yahoo sign-in: {type(exc).__name__}") from exc
    if status >= 500:
        raise YahooUnavailable(f"Yahoo sign-in: HTTP {status}")
    if status != 200 or not body.get("access_token"):
        # Yahoo: {"error": "invalid_grant", ...} — never echo the body (it may carry a token)
        raise YahooSessionExpired(f"Yahoo refused the token request ({body.get('error') or status})")
    return body


def _fixture_token(form: dict, wall: Callable[[], float]) -> tuple[int, dict]:
    ok = (form.get("grant_type") == "authorization_code" and form.get("code") == FIXTURE_CODE) or \
         (form.get("grant_type") == "refresh_token" and str(form.get("refresh_token", "")).startswith("fixture-refresh"))
    if not ok:
        return 400, {"error": "invalid_grant"}
    n = int(wall())
    return 200, {"access_token": f"fixture-access-{n}", "token_type": "bearer", "expires_in": 3600,
                 "refresh_token": "fixture-refresh", "xoauth_yahoo_guid": "FIXTUREGUID3"}


def exchange_code(code: str, redirect_uri: str, *, wall: Callable[[], float] = time.time) -> YahooSession:
    """The callback's ``code`` -> a new session (Yahoo's token answer)."""
    body = _token_request({"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri}, wall)
    return YahooSession(refresh_token=str(body.get("refresh_token") or ""), access_token=str(body["access_token"]),
                        expires_at=wall() + float(body.get("expires_in") or 3600),
                        guid=(str(body["xoauth_yahoo_guid"]) if body.get("xoauth_yahoo_guid") else None), changed=True)


def refresh(session: YahooSession, *, wall: Callable[[], float] = time.time) -> YahooSession:
    """A new access token for the session, in place (``changed``); refused -> ``expired`` + ``YahooSessionExpired``."""
    try:
        body = _token_request({"grant_type": "refresh_token", "refresh_token": session.refresh_token,
                               "redirect_uri": redirect_uri_env() or "oob"}, wall)
    except YahooSessionExpired:
        session.expired = True
        raise
    session.access_token = str(body["access_token"])
    session.expires_at = wall() + float(body.get("expires_in") or 3600)
    if body.get("refresh_token"):
        session.refresh_token = str(body["refresh_token"])
    session.changed = True
    return session


# ====================================================================================== the normaliser
def _is_index(k: Any) -> bool:
    return isinstance(k, str) and k.isdigit()


def normalise(x: Any) -> Any:
    """Yahoo's JSON -> plain dicts and lists (see the module docstring). A dict of indexes and ``count`` (a
    collection, possibly empty) is a list; a dict with indexes among other keys (``roster``: ``{"0": {"players": …},
    "week": "4"}``) keeps its keys and merges the indexed values in; any other dict keeps every key (``count`` too: a
    roster position's). A list's nested lists are spliced in (empty ones vanish); a list of dicts with no key in
    common is merged into one dict (a resource: metadata + sub-resources), else it stays a list
    (``[{"manager": …}, {"manager": …}]``)."""
    if isinstance(x, dict):
        idx = sorted((k for k in x if _is_index(k)), key=int)
        rest = {k: normalise(v) for k, v in x.items() if not _is_index(k)}
        if set(rest) <= {"count"} and (idx or "count" in rest):
            return [normalise(x[k]) for k in idx]
        for k in idx:
            v = normalise(x[k])
            if isinstance(v, dict):
                for kk, vv in v.items():
                    rest.setdefault(kk, vv)
        return rest
    if isinstance(x, list):
        flat: list[Any] = []

        def splice(v: Any) -> None:
            if isinstance(v, list):
                for e in v:
                    splice(e)
            else:
                flat.append(v)
        for e in x:
            splice(e)
        flat = [normalise(e) for e in flat]
        if flat and all(isinstance(e, dict) for e in flat):
            seen: set[str] = set()
            for e in flat:
                if seen & set(e):
                    return flat
                seen |= set(e)
            merged: dict = {}
            for e in flat:
                merged.update(e)
            return merged
        return flat
    return x


def items(v: Any, name: str) -> list:
    """The members of a normalised collection or repeated element, always a list: ``[{"team": T1}, {"team": T2}]``
    -> [T1, T2]; ``{"bonus": B}`` (one element, merged by ``normalise``) -> [B]; None / anything else -> []."""
    if isinstance(v, dict):
        return [v[name]] if name in v else []
    if isinstance(v, list):
        return [e[name] for e in v if isinstance(e, dict) and name in e]
    return []


def _f(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


# ====================================================================================== translation (pure)
# Yahoo's NFL stat ids (the ``stat_categories`` of a league's settings; ids and names as Yahoo publishes them in
# every league's settings — yfpy / yahoo_fantasy_api document the same table) -> Sleeper scoring keys. One id may
# set several keys (2-point conversions: passing, rushing and receiving). An id not here, or one whose key no stat
# line carries, is listed on the league card as unpriced with the league's own name for it.
STAT_KEYS: dict[int, tuple[str, ...]] = {
    1: ("pass_att",), 2: ("pass_cmp",), 3: ("pass_inc",), 4: ("pass_yd",), 5: ("pass_td",), 6: ("pass_int",),
    7: ("pass_sack",), 8: ("rush_att",), 9: ("rush_yd",), 10: ("rush_td",), 11: ("rec",), 12: ("rec_yd",),
    13: ("rec_td",), 15: ("st_td",), 16: ("pass_2pt", "rush_2pt", "rec_2pt"), 17: ("fum",), 18: ("fum_lost",),
    19: ("fgm_0_19",), 20: ("fgm_20_29",), 21: ("fgm_30_39",), 22: ("fgm_40_49",), 23: ("fgm_50p",),
    24: ("fgmiss_0_19",), 25: ("fgmiss_20_29",), 26: ("fgmiss_30_39",), 27: ("fgmiss_40_49",), 28: ("fgmiss_50p",),
    29: ("xpm",), 30: ("xpmiss",),
    # team defense (DEF)
    32: ("sack",), 33: ("int",), 34: ("fum_rec",), 35: ("def_td",), 36: ("safe",), 37: ("blk_kick",),
    49: ("def_st_td",), 50: ("pts_allow_0",), 51: ("pts_allow_1_6",), 52: ("pts_allow_7_13",),
    53: ("pts_allow_14_20",), 54: ("pts_allow_21_27",), 55: ("pts_allow_28_34",), 56: ("pts_allow_35p",),
    57: ("fum_rec_td",), 60: ("pass_td_40p",), 62: ("rush_td_40p",), 64: ("rec_td_40p",),
    78: ("rec_tgt",), 79: ("pass_fd",), 80: ("rec_fd",), 81: ("rush_fd",),
}
# names for the ids we leave unpriced when the league's settings do not name them
STAT_NAMES: dict[int, str] = {
    14: "Return Yards", 31: "Points Allowed", 38: "Tackle Solo", 39: "Tackle Assist", 40: "Sack (IDP)",
    41: "Interception (IDP)", 42: "Fumble Force", 43: "Fumble Recovery (IDP)", 44: "Defensive Touchdown (IDP)",
    45: "Safety (IDP)", 46: "Pass Defended", 47: "Blocked Kick (IDP)", 48: "Return Yards (DEF)",
    58: "Pick Sixes Thrown", 59: "40+ Yard Completions", 61: "40+ Yard Runs", 63: "40+ Yard Receptions",
    65: "Tackles for Loss", 66: "Turnover Return Yards", 67: "4th Down Stops", 68: "Tackles for Loss (DEF)",
    69: "Defensive Yards Allowed", 70: "Yards Allowed Negative", 71: "Yards Allowed 0-99", 72: "Yards Allowed 100-199",
    73: "Yards Allowed 200-299", 74: "Yards Allowed 300-399", 75: "Yards Allowed 400-499", 76: "Yards Allowed 500+",
    77: "Three and Outs Forced", 82: "Extra Point Returned",
}
# yardage bonuses Yahoo states as {target, points} on a stat; Sleeper keys them by band (the 300 band is 300-399
# and the 400 band 400+, so Yahoo's cumulative bonuses add up into the higher band)
BONUS_KEYS: dict[tuple[str, int], str] = {
    ("pass_yd", 300): "bonus_pass_yd_300", ("pass_yd", 400): "bonus_pass_yd_400",
    ("rush_yd", 100): "bonus_rush_yd_100", ("rush_yd", 200): "bonus_rush_yd_200",
    ("rec_yd", 100): "bonus_rec_yd_100", ("rec_yd", 200): "bonus_rec_yd_200",
}


def stat_names(settings: Mapping) -> dict[int, str]:
    """The league's own names for its stat ids (``stat_categories``)."""
    out: dict[int, str] = {}
    for st in items((settings.get("stat_categories") or {}).get("stats"), "stat"):
        try:
            out[int(st.get("stat_id"))] = str(st.get("name") or st.get("display_name") or "")
        except (TypeError, ValueError):
            continue
    return out


def scoring(settings: Mapping) -> tuple[dict[str, float], dict]:
    """A league's ``settings`` (normalised) -> (Sleeper ``scoring_settings``, report ``{approximated, unpriced,
    unpriced_stat_ids}``). ``stat_modifiers`` gives the points per unit of each stat id; ``bonuses`` give a flat bonus
    at a target."""
    names = {**STAT_NAMES, **stat_names(settings)}
    sc: dict[str, float] = {}
    approx: list[str] = []
    unpriced: dict[int, str] = {}
    for st in items((settings.get("stat_modifiers") or {}).get("stats"), "stat"):
        try:
            sid, val = int(st.get("stat_id")), _f(st.get("value"))
        except (TypeError, ValueError):
            continue
        keys = STAT_KEYS.get(sid)
        if keys is None:
            if val:
                unpriced[sid] = names.get(sid) or f"Yahoo stat {sid}"
            continue
        for k in keys:
            sc[k] = round(val, 6)
        bonuses = items(st.get("bonuses"), "bonus")
        if bonuses:
            base = keys[0]
            got = sorted(((int(_f(b.get("target"))), _f(b.get("points"))) for b in bonuses), key=lambda t: t[0])
            run = 0.0
            for target, pts in got:
                run += pts
                bkey = BONUS_KEYS.get((base, target))
                if bkey is None:
                    unpriced[sid * 1000 + target] = f"{names.get(sid) or base} bonus at {target}"
                    continue
                sc[bkey] = round(run, 6)
            if any(BONUS_KEYS.get((base, t)) for t, _ in got) and len(got) > 1:
                approx.append(f"{names.get(sid) or base}: Yahoo's bonuses are read as cumulative (each target "
                              "reached adds its points)")
    return sc, {"approximated": approx, "unpriced": [unpriced[k] for k in sorted(unpriced)],
                "unpriced_stat_ids": sorted(k for k in unpriced if k < 1000)}


# Yahoo roster positions -> the slot names League Lab solves (lineup.parse_slots); IDP slots are not modelled
SLOT = {"QB": "QB", "RB": "RB", "WR": "WR", "TE": "TE", "K": "K", "DEF": "DEF", "W/R/T": "FLEX",
        "Q/W/R/T": "SUPER_FLEX", "W/R": "WRRB_FLEX", "W/T": "REC_FLEX", "BN": "BN", "IR": "IR"}
IDP_SLOTS = {"D", "DB", "DL", "LB", "DT", "DE", "CB", "S"}


def slots(settings: Mapping) -> tuple[list[str], dict]:
    """``roster_positions`` -> (Sleeper's ``roster_positions``: starters in Yahoo's order then ``BN`` × bench; IR
    counted apart), the note ``{ir, idp, unknown, yahoo}``."""
    starters: list[str] = []
    bench = ir = 0
    idp: list[str] = []
    unknown: list[str] = []
    raw: list[dict] = []
    for rp in items(settings.get("roster_positions"), "roster_position"):
        pos, n = str(rp.get("position") or ""), int(_f(rp.get("count"), 0))
        raw.append({"position": pos, "count": n})
        s = SLOT.get(pos)
        if s == "BN":
            bench += n
        elif s == "IR":
            ir += n
        elif s:
            starters += [s] * n
        elif pos in IDP_SLOTS:
            idp += [pos] * n
        else:
            unknown += [pos] * n
    return starters + ["BN"] * bench, {"ir": ir, "idp": idp, "unknown": unknown, "yahoo": raw}


YAHOO_TEAM = {"JAC": "JAX", "WSH": "WAS", "LA": "LAR", "OAK": "LV", "SD": "LAC", "STL": "LAR"}


def team_code(abbr: str | None) -> str | None:
    """Yahoo's team abbreviation (``Jax``, ``Was``, ``KC``) -> Sleeper's (``JAX``, ``WAS``, ``KC``)."""
    if not abbr:
        return None
    t = str(abbr).strip().upper()
    return YAHOO_TEAM.get(t, t) or None


def position_of(p: Mapping) -> str | None:
    pos = str(p.get("primary_position") or p.get("display_position") or "").split(",")[0].strip()
    return {"DEF": "DEF", "K": "K", "PK": "K"}.get(pos, pos) or None


def player_row(p: Mapping) -> dict:
    """A normalised Yahoo player -> ``{yahoo_id, name, position, team, injury_status, selected}``."""
    name = p.get("name") or {}
    sel = p.get("selected_position") or {}
    return {"yahoo_id": player_id_of(str(p.get("player_key") or p.get("player_id") or "")),
            "name": (name.get("full") if isinstance(name, Mapping) else str(name)) or None,
            "position": position_of(p), "team": team_code(p.get("editorial_team_abbr")),
            "injury_status": p.get("status") or None,
            "selected": (sel.get("position") if isinstance(sel, Mapping) else None)}


# ====================================================================================== the client
def _per_minute() -> float:
    try:
        return max(1.0, float(os.environ.get(PER_MIN_ENV) or DEFAULT_PER_MIN))
    except ValueError:
        return float(DEFAULT_PER_MIN)


class Yahoo:
    """Read-only Yahoo Fantasy Sports client (see the module docstring). ``fetch`` (tests): (url, headers) ->
    (status, headers, body text)."""

    def __init__(self, fixtures: str | Path | None = None, base: str | None = None, timeout: float = 10.0, *,
                 clock: Callable[[], float] = time.monotonic, wall: Callable[[], float] = time.time,
                 bucket: TokenBucket | None = None,
                 fetch: Callable[[str, dict], tuple[int, Mapping, str]] | None = None) -> None:
        fx = fixtures if fixtures is not None else os.environ.get(FIXTURES_ENV)
        self.fixtures = Path(fx) if fx else None
        self.base = (base or API).rstrip("/")
        self.timeout = timeout
        self.clock = clock
        self.wall = wall
        self.bucket = bucket or TokenBucket(_per_minute(), clock=clock)
        self._fetch = fetch
        self.calls = 0
        self.stale_served = 0
        self.refreshed = 0
        self._backoff_until = 0.0
        self._cache: dict[tuple[str, str], tuple[float, float, str, Any]] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ the one read
    def _session(self) -> YahooSession:
        s = request_session.get()
        if s is None or not s.refresh_token:
            raise YahooSignInRequired()
        if s.expired:
            raise YahooSessionExpired()
        return s

    def _http(self, path: str, token: str) -> tuple[int, Mapping, str]:
        url = f"{self.base}/{path}?format=json"
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json", "User-Agent": USER_AGENT}
        if self._fetch is not None:
            return self._fetch(url, headers)
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:  # noqa: S310 - fixed https host
                return r.status, dict(r.headers), r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            try:
                body = exc.read().decode("utf-8", "replace")
            except OSError:
                body = ""
            return exc.code, dict(exc.headers or {}), body
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise YahooUnavailable(f"Yahoo {path}: {type(exc).__name__}") from exc

    def _fixture(self, path: str) -> tuple[int, Mapping, str]:
        assert self.fixtures is not None
        f = self.fixtures / fixture_name(path)
        if not f.exists():
            return 400, {}, json.dumps({"error": {"description": "You are not allowed to view this page because "
                                                                 "you are not in this league. (fixtures)"}})
        return 200, {}, f.read_text()

    def _read(self, path: str, session: YahooSession, league_key: str | None) -> Any:
        if session.expires_at - 60 < self.wall():
            refresh(session, wall=self.wall)
            self.refreshed += 1
        for attempt in (0, 1):
            status, headers, text = (self._fixture(path) if self.fixtures is not None and self._fetch is None
                                     else self._http(path, session.access_token))
            if status == 401 and attempt == 0 and ("token_expired" in text or "token_expired" in
                                                   str(headers.get("WWW-Authenticate") or headers.get("www-authenticate") or "")):
                refresh(session, wall=self.wall)
                self.refreshed += 1
                continue
            break
        if status in (429, 999):
            self._backoff_until = self.clock() + 60
            raise YahooBusy("busy, try again in a minute")
        if status >= 500:
            raise YahooUnavailable(f"Yahoo {path}: HTTP {status}")
        try:
            data = json.loads(text or "null")
        except json.JSONDecodeError as exc:
            if status != 200:
                data = None
            else:
                raise YahooUnavailable(f"Yahoo {path}: not JSON") from exc
        if status != 200:                                 # ---- PO 2026-10-05: say what Yahoo said, to the right party
            low = text.lower()
            problem = oauth_problem(text, headers)
            not_member = "not in this league" in low or "not allowed to view" in low
            # the app's entitlement, not the league or the manager: Yahoo's own word for it, or a 403 on a resource
            # that names no league (this season's game, the manager's own leagues)
            pending = status in (401, 403) and not not_member and (
                problem == "additional_authorization_required" or (status == 403 and league_key is None))
            _note_refusal(path, status, problem, text, pending, self.wall)
            if pending:
                raise YahooAccessPending()
            if status == 401:
                if not_member or "not allowed" in low:
                    raise YahooLeagueNotFound(league_key)
                session.expired = True
                raise YahooSessionExpired()
            if league_key is None:                        # no league was asked for: never "that league is private"
                raise YahooUnavailable(f"Yahoo {path}: HTTP {status}")
            raise YahooLeagueNotFound(league_key)
        _access["ok_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.wall()))
        _access["pending_until"] = 0.0                    # Yahoo answered a Fantasy call: the app's access is open
        if not isinstance(data, dict) or "fantasy_content" not in data:
            raise YahooLeagueNotFound(league_key) if isinstance(data, dict) and "error" in data \
                else YahooUnavailable(f"Yahoo {path}: no fantasy_content")
        return normalise(data["fantasy_content"])

    def get(self, path: str, kind: str, league_key: str | None = None) -> Any:
        """The normalised ``fantasy_content`` of one resource path, read as the request's manager (cached by kind)."""
        session = self._session()
        key = (session.who(), path)
        now = self.clock()
        with self._lock:
            hit = self._cache.get(key)
        if hit is not None and hit[0] > now:
            return hit[3]
        if now < self._backoff_until or not self.bucket.take():
            if provider_trouble.serve_held(self, "yahoo", hit, kind, now):         # ---- IP-5 fix round: bounded
                return hit[3]
            provider_trouble.note("busy")                                          # ---- IP-5 fix round
            raise YahooBusy("busy, try again in a minute")
        self.calls += 1
        try:
            data = self._read(path, session, league_key)
        except YahooBusy:                       # ---- IP-5: Yahoo's 429 / 999 — the held answer, as for an empty bucket
            if provider_trouble.serve_held(self, "yahoo", hit, kind, now):
                return hit[3]
            provider_trouble.note("busy")
            raise
        except YahooUnavailable:
            if provider_trouble.serve_held(self, "yahoo", hit, kind, now):         # ---- IP-5 fix round
                return hit[3]
            provider_trouble.note("failed")
            raise
        with self._lock:
            self._cache[key] = (now + TTL_S[kind], now, kind, data)
            if len(self._cache) > MAX_ENTRIES:            # many managers: expired answers first, then the oldest
                for k in [k for k, v in self._cache.items() if v[0] <= now]:
                    del self._cache[k]
                for k, _ in sorted(self._cache.items(), key=lambda kv: kv[1][1])[:max(0, len(self._cache) - MAX_ENTRIES)]:
                    del self._cache[k]
        return data

    # ------------------------------------------------------------------ resources
    def game_key(self, code: str = "nfl") -> str:
        g = (self.get(f"game/{code}", "game") or {}).get("game") or {}
        k = str(g.get("game_key") or "")
        if not k.isdigit():
            raise YahooUnavailable("Yahoo game: no game_key")
        return k

    def resolve(self, league_key: str) -> str:
        """``nfl.l.4242`` -> ``461.l.4242`` (this season's game key); a numeric key as it is."""
        lk = check_league_key(league_key)
        gk, lid = lk.split(".l.")
        return lk if gk.isdigit() else f"{self.game_key(gk)}.l.{lid}"

    def game_weeks(self, game_key: str) -> list[dict]:
        g = (self.get(f"game/{game_key}/game_weeks", "game_weeks") or {}).get("game") or {}
        return [w for w in items(g.get("game_weeks"), "game_week") if isinstance(w, dict)]

    def _league(self, lk: str, sub: str, kind: str) -> dict:
        lg = (self.get(f"league/{lk}/{sub}" if sub else f"league/{lk}", kind, lk) or {}).get("league")
        if not isinstance(lg, dict):
            raise YahooLeagueNotFound(lk)
        return lg

    def settings(self, lk: str) -> dict:
        """The league's metadata merged with its ``settings`` (normalised)."""
        lg = self._league(lk, "settings", "settings")
        st = lg.get("settings") or {}
        return {**{k: v for k, v in lg.items() if k != "settings"}, "settings": st if isinstance(st, dict) else {}}

    def teams(self, lk: str) -> list[dict]:
        return items(self._league(lk, "teams", "teams").get("teams"), "team")

    def standings(self, lk: str) -> list[dict]:
        st = self._league(lk, "standings", "standings").get("standings")
        if isinstance(st, list):                          # [{"teams": …}]
            st = st[0] if st and isinstance(st[0], dict) else {}
        return items((st or {}).get("teams"), "team")

    def scoreboard(self, lk: str, week: int) -> list[dict]:
        sb = self._league(lk, f"scoreboard;week={int(week)}", "scoreboard").get("scoreboard") or {}
        return items(sb.get("matchups"), "matchup")

    def transactions(self, lk: str) -> list[dict]:
        return items(self._league(lk, "transactions", "transactions").get("transactions"), "transaction")

    def free_agents(self, lk: str, start: int = 0, count: int = 25) -> list[dict]:
        lg = self._league(lk, f"players;status=FA;sort=AR;start={int(start)};count={int(count)}", "players")
        return items(lg.get("players"), "player")

    def roster(self, team_key_: str, week: int) -> list[dict]:
        lk = team_key_.rsplit(".t.", 1)[0]
        t = (self.get(f"team/{team_key_}/roster;week={int(week)}/players", "roster", lk) or {}).get("team") or {}
        return items((t.get("roster") or {}).get("players"), "player")

    def my_games(self) -> list[dict]:
        """The signed-in manager's NFL game of this season with its ``leagues`` and ``teams`` (two reads)."""
        out: dict[str, dict] = {}
        for sub in ("leagues", "teams"):
            data = self.get(f"users;use_login=1/games;game_keys=nfl/{sub}", "user") or {}
            for u in items(data.get("users"), "user"):
                for g in items(u.get("games"), "game"):
                    gk = str(g.get("game_key") or "")
                    row = out.setdefault(gk, {k: v for k, v in g.items() if k not in ("leagues", "teams")})
                    row[sub] = items(g.get(sub), sub[:-1])
        return list(out.values())

    def stats(self) -> dict:
        now = self.clock()
        with self._lock:
            entries = list(self._cache.values())
        kinds: dict[str, dict] = {}
        for exp, fetched, kind, _ in entries:
            k = kinds.setdefault(kind, {"entries": 0, "fresh": 0, "oldest_s": 0.0, "ttl_s": TTL_S[kind]})
            k["entries"] += 1
            k["fresh"] += int(exp > now)
            k["oldest_s"] = round(max(k["oldest_s"], now - fetched), 1)
        return {"mode": "fixtures" if self.fixtures is not None else "live", "calls": self.calls,
                "stale_served": self.stale_served, "refreshed": self.refreshed, "configured": configured(),
                "bucket": {"tokens": round(self.bucket.tokens(), 1), "capacity": self.bucket.capacity,
                           "per_minute": self.bucket.per_minute, "refused": self.bucket.refused},
                "cache": kinds}
