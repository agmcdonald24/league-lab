"""Usage tracking (Wave I-F, U-1; plan § 17 E): which screens get used. docs/HOSTING.md § "Usage".

* **The row** (`usage.events`, created by `scripts/hosted_usage.sql`): when, which screen (the web router's route
  name), which league and team number, the platform (from the league key), the release (`/api/health`'s version),
  and `session` — a random id the server mints and the browser keeps in the cookie `ll_usage` until midnight in New
  York. Nothing about a person: no name, username, IP address, user agent or login token; every value is
  allow-listed here and checked again by the table.
* **The write** never touches the read pool: `db.write_one` opens its own `BEGIN; SET TRANSACTION READ WRITE;
  INSERT; COMMIT` on its own connection (the role stays `default_transaction_read_only = on`). The route only puts the
  row on a bounded queue (`QUEUE_MAX`; full = the row is dropped and counted) that one daemon thread of its own
  drains: a slow or unreachable database never holds a request, and never takes the server's request threads (the
  read routes run on them). A failure is counted and logged, never raised — usage is never load-bearing.
* **Limits**: one row a second per session, sustained (`PER_S`), with a burst of `BURST` (tapping through three tabs
  in a second is three views, measured on the live server: a strict 1/s dropped the second of two quick screens), and
  at most `GLOBAL_PER_S` rows a second from all sessions together (a client that drops the cookie gets a new session
  each time; the global cap still bounds it).
* **Off switch**: `LEAGUE_LAB_USAGE=off` (also 0 / false / no): the route still answers 204, sets no cookie and writes
  nothing; the summary says `enabled: false`.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import re
import secrets
import threading
import time
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import psycopg
from league_lab import platforms

from . import db

log = logging.getLogger("league_lab_api.usage")

ENV = "LEAGUE_LAB_USAGE"
COOKIE = "ll_usage"
NY = ZoneInfo("America/New_York")
# the web router's route names (web/src/lib/router.svelte.ts RouteName); anything else is stored as "other"
SCREENS = frozenset({"week", "player", "leagues", "ros", "about", "trends", "matchups", "players", "receivers",
                     "compare", "waivers", "trades", "trade-calc", "team", "league"}
                    | {"account", "watchlist"}      # ---- IL-5: IK-4's account screen and the watchlist (were "other")
                    | {"home", "blog", "post", "dfs"})   # ---- IN-1: the home page, the blog, a post (+ IM-5's "dfs", missing)
PER_S, BURST = 1.0, 5    # per session: a token bucket (one a second, five at once)
GLOBAL_PER_S = 20        # all sessions together
MAX_BODY = 2048          # bytes; a bigger body counts the view with no league / team
QUEUE_MAX = 1000         # rows waiting for the writer thread; beyond it a row is dropped (the database is down)
_SESSION = re.compile(r"^[0-9a-f]{32}$")
_VERSION = re.compile(r"^[A-Za-z0-9._+-]{1,40}$")

INSERT = ("insert into usage.events (at, screen, league_key, roster_id, platform, version, session) "
          "values (%s, %s, %s, %s, %s, %s, %s)")

clock = time.monotonic   # the rate limit's clock (tests replace it)
_lock = threading.Lock()
_buckets: dict[str, tuple[float, float]] = {}    # session -> (tokens left, when)
_window: list[float] = [0.0, 0]        # [the current second, rows allowed in it]
stats = {"written": 0, "failed": 0, "limited": 0, "dropped": 0}
_queue: queue.Queue[dict] = queue.Queue(maxsize=QUEUE_MAX)
_worker: threading.Thread | None = None


def enabled() -> bool:
    return os.environ.get(ENV, "on").strip().lower() not in ("off", "0", "false", "no")


def session_from(cookie: str | None) -> str | None:
    """The cookie's id when it is one we mint (32 hex characters), else None."""
    s = (cookie or "").strip().lower()
    return s if _SESSION.match(s) else None


def new_session() -> str:
    return secrets.token_hex(16)


def seconds_left_today(now: datetime | None = None) -> int:
    """Seconds until the next midnight in New York (the session id lives for the day); at least a minute."""
    now = (now or datetime.now(UTC)).astimezone(NY)
    midnight = datetime.combine(now.date() + timedelta(days=1), datetime.min.time(), tzinfo=NY)
    return max(60, int((midnight - now).total_seconds()))


def parse(body: bytes) -> dict:
    """The POST body as a dict ({} when it is not a small JSON object). JSON or text/plain (sendBeacon) alike."""
    if not body or len(body) > MAX_BODY:
        return {}
    try:
        v = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return {}
    return v if isinstance(v, dict) else {}


def event(payload: dict, *, version: str | None, session: str) -> dict:
    """The row: allow-listed values only (never a name, a username or free text)."""
    screen = str(payload.get("screen") or "").strip().lower()
    league = None
    raw_league = payload.get("league")
    if isinstance(raw_league, str | int) and not isinstance(raw_league, bool):
        try:
            league = platforms.check_key(str(raw_league))
        except Exception:  # noqa: BLE001 - not a league key: counted without one
            league = None
    roster = payload.get("roster_id")
    if isinstance(roster, str) and roster.strip().isdigit():
        roster = int(roster.strip())
    roster = roster if league and isinstance(roster, int) and not isinstance(roster, bool) and 0 <= roster <= 9999 else None
    version = version if version and _VERSION.match(version) else None
    return {"at": datetime.now(UTC), "screen": screen if screen in SCREENS else "other", "league_key": league,
            "roster_id": roster, "platform": platforms.platform(league) if league else None, "version": version,
            "session": session if _SESSION.match(session or "") else None}


def allow(session: str) -> bool:
    """PER_S rows a second per session (bursts of BURST), GLOBAL_PER_S rows a second in all."""
    now = clock()
    with _lock:
        tokens, then = _buckets.get(session, (float(BURST), now))
        tokens = min(float(BURST), tokens + (now - then) * PER_S)
        second = float(int(now))
        if _window[0] != second:
            _window[0], _window[1] = second, 0
        if tokens < 1.0 or _window[1] >= GLOBAL_PER_S:
            _buckets[session] = (tokens, now)
            stats["limited"] += 1
            return False
        _window[1] += 1
        _buckets[session] = (tokens - 1.0, now)
        if len(_buckets) > 10000:                    # bounded: forget the sessions whose bucket is full again
            for k in [k for k, (t, w) in _buckets.items() if t + (now - w) * PER_S >= BURST]:
                _buckets.pop(k, None)
        return True


def reset() -> None:
    """Forget the rate limit's memory and the counters (tests)."""
    with _lock:
        _buckets.clear()
        _window[0], _window[1] = 0.0, 0
        for k in stats:
            stats[k] = 0


def submit(row: dict) -> bool:
    """Hand the row to the writer thread (never waits); False when the queue is full (dropped, counted)."""
    global _worker
    with _lock:
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_drain, name="league-lab-usage", daemon=True)
            _worker.start()
    try:
        _queue.put_nowait(row)
    except queue.Full:
        stats["dropped"] += 1
        return False
    return True


def _drain() -> None:
    while True:
        row = _queue.get()
        try:
            write(row)
        finally:
            _queue.task_done()


def flush(timeout: float = 5.0) -> bool:
    """Wait until the writer thread has handled every queued row (tests; the summary's QA)."""
    deadline = time.monotonic() + timeout
    while _queue.unfinished_tasks:
        if time.monotonic() > deadline:
            return False
        time.sleep(0.01)
    return True


def write(row: dict) -> bool:
    """Insert the row; any failure is swallowed (counted, logged by class only). Runs after the response."""
    try:
        db.write_one(INSERT, (row["at"], row["screen"], row["league_key"], row["roster_id"], row["platform"],
                              row["version"], row["session"]))
    except Exception as exc:  # noqa: BLE001 - usage is never load-bearing
        stats["failed"] += 1
        log.warning("usage: insert failed (%s)", exc.__class__.__name__)
        return False
    stats["written"] += 1
    return True


# ---- reading it (GET /api/usage/summary; the console's Usage page asks the same questions of the same table)
_SINCE = "at >= ((now() at time zone 'America/New_York')::date - %s::int)::timestamp at time zone 'America/New_York'"
_DAY = "(at at time zone 'America/New_York')::date"


def summary(days: int = 7) -> dict:
    """Views per screen per day, views / leagues / sessions per day, the window's totals (days in New York)."""
    days = max(1, min(int(days), 90))
    out: dict = {"enabled": enabled(), "days": days, "ready": True, "process": dict(stats)}
    back = (days - 1,)
    try:
        per = db.fresh(f"select {_DAY} as day, screen, count(*)::int as views from usage.events where {_SINCE} "
                       "group by 1, 2 order by 1 desc, 3 desc, 2", back)
        by_day = db.fresh(f"select {_DAY} as day, count(*)::int as views, count(distinct league_key)::int as leagues, "
                          f"count(distinct session)::int as sessions from usage.events where {_SINCE} "
                          "group by 1 order by 1 desc", back)
        by_screen = db.fresh(f"select screen, count(*)::int as views from usage.events where {_SINCE} "
                             "group by 1 order by 2 desc, 1", back)
        tot = db.fresh(f"select count(*)::int as views, count(distinct league_key)::int as leagues, "
                       f"count(distinct session)::int as sessions from usage.events where {_SINCE}", back)
    except (db.DataNotReady, psycopg.Error) as exc:
        out.update(ready=False, words="Usage is not set up on this database yet: the next nightly creates the table "
                                      "(scripts/hosted_usage.sql).", cause=exc.__class__.__name__)
        return out
    out.update(views_by_screen_day=per.to_dict("records"), by_day=by_day.to_dict("records"),
               by_screen=by_screen.to_dict("records"), totals=tot.to_dict("records")[0])
    return out
