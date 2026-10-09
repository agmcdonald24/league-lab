"""The event store (Wave I-G, IG-2; the decision-quality review § "Engineering requirements"). docs/HOSTING.md § "Events".

* **The row** (``events.events``, created by ``scripts/hosted_events.sql``; locally by ``scripts/init_db.sql``): one thing
  the app learned about a player or a team — an injury-report status move (the availability overlay: ESPN / Sleeper),
  an ESPN news item it showed, a PlayerWire brief it showed — keyed by player (``gsis_id``; ``player_key`` = the
  source's own id: ``espn:4262921``, ``sleeper:6794``, ``pw:<brief id>``), ``team`` (nflverse abbreviations) and
  ``game_key`` (nflverse ``game_id``: an availability move's team game in the week in play, IH-2), with ``status``,
  ``headline`` / ``summary``, ``source`` and ``source_url``, ``published_at`` / ``effective_at`` / ``ingested_at``, and
  ``superseded_by`` (the newer event of the same kind about the same player). ``fingerprint`` (sha256 of kind, subject,
  status, URL and time) is unique: the same item seen twice is one row.
* **Times.** Availability: ``published_at`` = the copy's own time (ESPN's feed ``timestamp``, else when it was read;
  Sleeper: when the directory was read), ``effective_at`` = the report's date (ESPN's entry ``date``, Sleeper's
  ``news_updated``; NULL when Sleeper gives none). News and briefs: ``published_at`` = the item's date. The event's
  "when" everywhere is ``coalesce(effective_at, published_at, ingested_at)`` (``at`` in the readers).
* **Superseded.** One live event per player per kind: a new availability event supersedes every older live one of
  the player (the overlay's current status is always the newest row); a news item or a brief supersedes the older
  ones by time (an older item that arrives late is stored already superseded by the newer live one).
* **The writers** never sit on a request's path: ``observe_*`` build the rows (or a job that builds them) and put them
  on a bounded queue (``QUEUE_MAX`` jobs; full = dropped, counted) that one daemon thread drains, writing each batch
  in its own ``BEGIN; SET TRANSACTION READ WRITE; ...; COMMIT`` on its own connection (U-1's pattern: the app role
  stays ``default_transaction_read_only = on``; the read pool never sees a read-write transaction). A failure is
  counted and logged, never raised. A fingerprint this process already queued is not queued again.
  - ``observe_availability(snapshot)``: the overlay's merged copy (``availability.snapshot``); the writer thread diffs
    each player's status (the newer of ESPN / Sleeper, the overlay's own rule) against the copy before — the first copy
    of a process against the store's live statuses — and writes one event per move (off the list = ``ACTIVE``). Only
    when both sources are in the copy: a source that failed to load is not a status move.
  - ``observe_items(gsis, items)``: the news items a screen showed (the player card's news line, My Week's "What
    changed"): ESPN's as ``news`` (``status`` = IF-4's ``about``: player | league), PlayerWire's as ``brief``
    (``status`` = the verification, ``summary`` = the brief's text, ``source_url`` = its first evidence link).
* **The readers** (the read-only role, ``db.query`` cached a minute): ``for_player``, ``for_team``, ``recent``,
  ``cite``, ``info``. Each answers [] (``info``: ``ready: false``) when the store is off, missing or unreachable —
  never an error.
* **Off switch**: ``LEAGUE_LAB_EVENTS=off`` (also 0 / false / no): nothing is written or read. In fixture mode
  (``LEAGUE_LAB_SLEEPER_FIXTURES``: the tests, this sandbox) the store is off unless ``LEAGUE_LAB_EVENTS=on``: a test
  run never writes fixture events into a developer's database by accident.
"""

from __future__ import annotations

import hashlib
import logging
import math
import os
import queue
import re
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

import pandas as pd
import psycopg
from league_lab import anyleague as A
from league_lab.clock import now as league_now

from . import db
from .settings import app_dsn

log = logging.getLogger("league_lab_api.events")

ENV = "LEAGUE_LAB_EVENTS"
ESPN_NEWS_ENV = "LEAGUE_LAB_EVENTS_ESPN_NEWS"     # off: ESPN's news items are not stored (status moves and briefs are)
KINDS = ("availability", "news", "brief", "depth_chart")
QUEUE_MAX = 500                 # jobs (a job is one batch of rows) waiting for the writer thread
SEEN_MAX = 20000                # fingerprints this process queued (bounded: the oldest are forgotten)
READ_TTL_S = 60                 # the readers' cache
MAX_ROWS = 200                  # rows one read returns at most
EPOCH = datetime(2000, 1, 1, tzinfo=UTC)
# Sleeper / ESPN team abbreviations -> nflverse's (the analytics' dim_team): LAR -> LA, WSH -> WAS
TEAM_FIX = {"LAR": "LA", "WSH": "WAS", "JAC": "JAX"}
_GSIS = re.compile(r"^00-[0-9]{7}$")
_TEAM = re.compile(r"^[A-Z]{2,3}$")
_PKEY = re.compile(r"^(sleeper|espn|mfl|pw):[A-Za-z0-9_.-]{1,40}$")
_GAME = re.compile(r"^[0-9]{4}_[0-9]{2}_[A-Z]{2,3}_[A-Z]{2,3}$")
_STATUS = re.compile(r"^[A-Za-z_-]{1,24}$")
COLUMNS = ("kind", "player_key", "gsis_id", "team", "game_key", "status", "headline", "summary", "source", "source_url",
           "published_at", "effective_at", "fingerprint")

clock: Callable[[], datetime] = league_now    # the readers' "now" (tests pin it); ---- INF-1: league_lab.clock
stats = {"queued": 0, "written": 0, "duplicate": 0, "superseded": 0, "failed": 0, "dropped": 0, "moves": 0}
_queue: queue.Queue = queue.Queue(maxsize=QUEUE_MAX)
_worker: threading.Thread | None = None
_lock = threading.Lock()
_seen: OrderedDict[str, None] = OrderedDict()
_conn: psycopg.Connection | None = None
_conn_lock = threading.Lock()
_avail_last: dict[str, dict] | None = None      # gsis -> {code, source, team, name}: the last copy (writer thread only)
_avail_present: tuple[bool, bool] | None = None
_read_warned = False


def enabled() -> bool:
    v = (os.environ.get(ENV) or "").strip().lower()
    if v in ("off", "0", "false", "no"):
        return False
    if v in ("on", "1", "true", "yes"):
        return True
    return not os.environ.get(A.FIXTURES_ENV)      # fixture mode: off unless asked for


# ------------------------------------------------------------------------------------------------ the row
def _when(v: Any) -> datetime | None:
    """A time (datetime / pandas Timestamp / ISO text / epoch seconds or ms) as an aware UTC datetime; None if none."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    if isinstance(v, datetime):
        return (v if v.tzinfo else v.replace(tzinfo=UTC)).astimezone(UTC)
    if isinstance(v, int | float) and not isinstance(v, bool):
        return datetime.fromtimestamp(float(v) / (1000.0 if v > 1e11 else 1.0), UTC)
    try:
        t = pd.Timestamp(v)
    except (ValueError, TypeError):
        return None
    if pd.isna(t):
        return None
    return (t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")).to_pydatetime()


def iso(v: Any) -> str | None:
    d = _when(v)
    return None if d is None else d.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def team_abbr(t: Any) -> str | None:
    s = str(t or "").strip().upper()
    s = TEAM_FIX.get(s, s)
    return s if _TEAM.match(s) else None


def fingerprint(kind: str, subject: str, status: str | None, url: str | None, when: datetime | None) -> str:
    raw = "|".join([kind, subject or "", status or "", url or "", iso(when) or ""])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _text(v: Any, n: int) -> str | None:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    s = " ".join(str(v).split())
    return s[:n] or None


def make(kind: str, *, source: str, gsis_id: str | None = None, team: str | None = None, player_key: str | None = None,
         game_key: str | None = None, status: str | None = None, headline: str | None = None, summary: str | None = None,
         source_url: str | None = None, published_at: Any = None, effective_at: Any = None) -> dict | None:
    """One row, every value checked as the table checks it (a value that does not fit is left out); None without a kind,
    a source or a subject (a gsis id or a team)."""
    if kind not in KINDS:
        return None
    g = gsis_id if isinstance(gsis_id, str) and _GSIS.match(gsis_id) else None
    t = team_abbr(team)
    src = _text(source, 80)
    if (g is None and t is None) or not src:
        return None
    url = source_url.strip() if isinstance(source_url, str) and source_url.strip().lower().startswith("https://") else None
    url = url if url and len(url) <= 1000 else None
    st = status.strip() if isinstance(status, str) and _STATUS.match(status.strip()) else None
    pub, eff = _when(published_at), _when(effective_at)
    row = {"kind": kind, "player_key": player_key if isinstance(player_key, str) and _PKEY.match(player_key) else None,
           "gsis_id": g, "team": t, "game_key": game_key if isinstance(game_key, str) and _GAME.match(game_key) else None,
           "status": st, "headline": _text(headline, 500), "summary": _text(summary, 4000), "source": src,
           "source_url": url, "published_at": pub, "effective_at": eff}
    row["fingerprint"] = fingerprint(kind, g or t or "", st, url, eff or pub)
    return row


# ------------------------------------------------------------------------------------------------ the writer
def _start() -> None:
    global _worker
    with _lock:
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_drain, name="league-lab-events", daemon=True)
            _worker.start()


def _put(job: Callable[[], list[dict]] | list[dict]) -> bool:
    _start()
    try:
        _queue.put_nowait(job)
    except queue.Full:
        stats["dropped"] += 1
        return False
    return True


def submit(rows: Iterable[dict | None]) -> int:
    """Queue the rows this process has not queued before (never waits); how many were queued. 0 when off."""
    if not enabled():
        return 0
    fresh: list[dict] = []
    with _lock:
        for r in rows:
            if not r or r["fingerprint"] in _seen:
                continue
            _seen[r["fingerprint"]] = None
            fresh.append(r)
        while len(_seen) > SEEN_MAX:
            _seen.popitem(last=False)
    if not fresh:
        return 0
    if not _put(fresh):
        _forget(fresh)
        return 0
    stats["queued"] += len(fresh)
    return len(fresh)


def _forget(rows: list[dict]) -> None:
    with _lock:
        for r in rows:
            _seen.pop(r["fingerprint"], None)


def _drain() -> None:
    global _avail_last
    while True:
        job = _queue.get()
        rows: list[dict] = []
        try:
            rows = job() if callable(job) else job
            if rows:
                write(rows)
        except Exception as exc:  # noqa: BLE001 - the store is never load-bearing
            stats["failed"] += max(1, len(rows or []))
            _forget(rows or [])
            _avail_last = None              # the next copy diffs against the store again (no move is lost for good)
            log.warning("events: a write failed (%s)", exc.__class__.__name__)
        finally:
            _queue.task_done()


def flush(timeout: float = 5.0) -> bool:
    """Wait until the writer thread has handled every queued job (tests; the QA route)."""
    deadline = time.monotonic() + timeout
    while _queue.unfinished_tasks:
        if time.monotonic() > deadline:
            return False
        time.sleep(0.01)
    return True


AT = "coalesce(effective_at, published_at, ingested_at)"
INSERT_SQL = (f"insert into events.events ({', '.join(COLUMNS)}) values ({', '.join(['%s'] * len(COLUMNS))}) "
              f"on conflict (fingerprint) do nothing returning id, {AT} as at")
NEWER_SQL = (f"select id from events.events where kind = %s and gsis_id = %s and id <> %s and superseded_by is null "
             f"and {AT} > %s order by {AT} desc, id desc limit 1")
SUPERSEDE_BY_ORDER_SQL = ("update events.events set superseded_by = %s where kind = %s and gsis_id = %s and id < %s "
                          "and superseded_by is null")
SUPERSEDE_BY_TIME_SQL = (f"update events.events set superseded_by = %s where kind = %s and gsis_id = %s and id <> %s "
                         f"and superseded_by is null and {AT} <= %s")
SELF_SQL = "update events.events set superseded_by = %s where id = %s"
LIVE_SQL = ("select id, status from events.events where kind = 'availability' and gsis_id = %s and superseded_by is null "
            "order by id desc limit 1")


def _writer() -> psycopg.Connection:
    global _conn
    if _conn is None or _conn.closed or _conn.broken:
        _conn = psycopg.connect(app_dsn(), autocommit=True, connect_timeout=5, application_name="league-lab-events",
                                 prepare_threshold=None)   # ---- IT-4: no prepared statements (a pooler need not keep them)
    return _conn


def write(rows: list[dict]) -> int:
    """Insert the batch in one read-write transaction on the writer connection (one retry on a dropped connection);
    supersede as the module says. Returns the rows inserted (a known fingerprint is skipped). Raises on failure."""
    global _conn
    with _conn_lock:
        for attempt in (1, 2):
            try:
                conn = _writer()
                n = dup = sup = 0
                with conn.transaction():                   # autocommit connection: an explicit BEGIN … COMMIT
                    conn.execute("set transaction read write")
                    for r in rows:
                        got = conn.execute(INSERT_SQL, tuple(r[c] for c in COLUMNS)).fetchone()
                        if got is None and r["kind"] == "availability" and r["gsis_id"]:
                            live = conn.execute(LIVE_SQL, (r["gsis_id"],)).fetchone()
                            if live is not None and live[1] != r["status"]:
                                # the same report again after another status (a copy that dropped him for a while):
                                # a new move, not a duplicate — its fingerprint names the event it follows
                                again = {**r, "fingerprint": hashlib.sha256(f"{r['fingerprint']}|after:{live[0]}".encode()).hexdigest()}
                                got = conn.execute(INSERT_SQL, tuple(again[c] for c in COLUMNS)).fetchone()
                        if got is None:
                            dup += 1
                            continue
                        n += 1
                        new_id, at = got
                        if not r["gsis_id"]:
                            continue
                        if r["kind"] == "availability":
                            sup += conn.execute(SUPERSEDE_BY_ORDER_SQL, (new_id, r["kind"], r["gsis_id"], new_id)).rowcount
                            continue
                        newer = conn.execute(NEWER_SQL, (r["kind"], r["gsis_id"], new_id, at)).fetchone()
                        if newer is not None:                   # an older item arriving late: stored superseded
                            conn.execute(SELF_SQL, (newer[0], new_id))
                            sup += 1
                        else:
                            sup += conn.execute(SUPERSEDE_BY_TIME_SQL, (new_id, r["kind"], r["gsis_id"], new_id, at)).rowcount
                stats["written"] += n
                stats["duplicate"] += dup
                stats["superseded"] += max(sup, 0)
                return n
            except psycopg.OperationalError:
                if _conn is not None:
                    _conn.close()
                _conn = None
                if attempt == 2:
                    raise
    return 0


def close() -> None:
    global _conn
    with _conn_lock:
        if _conn is not None:
            _conn.close()
            _conn = None


def reset(*, availability_baseline: Mapping[str, dict] | None = None) -> None:
    """Forget the process's memory (tests): the queued fingerprints, the counters, the last availability copy
    (``availability_baseline`` {gsis: {code, source, team, name}} stands in for it; None = read the store again)."""
    global _avail_last, _avail_present, _read_warned
    flush()
    with _lock:
        _seen.clear()
        for k in stats:
            stats[k] = 0
    _avail_last = None if availability_baseline is None else {g: dict(v) for g, v in availability_baseline.items()}
    _avail_present = None
    _read_warned = False


# ------------------------------------------------------------------------------------------------ availability
LIVE_STATUS_SQL = ("select distinct on (gsis_id) gsis_id, status, source, team, headline from events.events "
                   "where kind = 'availability' and superseded_by is null and gsis_id is not null "
                   "order by gsis_id, id desc")


def observe_availability(snap: Any) -> bool:
    """The overlay built a new merged copy: diff it on the writer thread (never here). False when off / no copy."""
    if not enabled() or snap is None:
        return False
    try:
        return _put(lambda: availability_rows(snap))
    except Exception:  # noqa: BLE001 - never into the overlay
        return False


def _store_statuses() -> dict[str, dict]:
    """{gsis: {code, source, team, name}} the store holds live (the first copy of a process diffs against it)."""
    try:
        df = db.fresh(LIVE_STATUS_SQL)
    except Exception as exc:  # noqa: BLE001 - no table yet: nothing known (the writes will say why)
        log.warning("events: the live statuses could not be read (%s)", exc.__class__.__name__)
        return {}
    out = {}
    for r in df.to_dict("records"):
        out[str(r["gsis_id"])] = {"code": r["status"] or "ACTIVE", "source": r["source"], "team": r["team"],
                                  "name": str(r["headline"] or "").split(" is ")[0] or None}
    return out


def current_statuses(snap: Any) -> dict[str, dict]:
    """{gsis: the overlay's entry} for every player either source lists (the newer of the two: ``availability._pick``)."""
    from . import availability as AV
    out = {}
    for g in set(getattr(snap, "espn", {})) | set(getattr(snap, "sleeper", {})):
        c = AV._pick([snap.espn.get(g), snap.sleeper.get(g)])          # noqa: SLF001 - the overlay's own rule
        if c is not None and c.get("code"):
            out[g] = c
    return out


def _headline(name: str | None, code: str, note: str | None) -> str:
    """"Jaycee Horn is on injured reserve (knee)" / "... is questionable" / "... is no longer on the injury report"."""
    from . import availability as AV
    who = name or "A player"
    if code == "ACTIVE":
        return f"{who} is no longer on the injury report"
    words = AV.WORDS.get(code) or f"is {(AV.LABEL.get(code) or code).lower()}"
    return f"{who} {words}" + (f" ({note})" if note else "")


def _copy_time(snap: Any, source: str) -> datetime | None:
    if source == "ESPN":
        return _when(getattr(snap, "espn_timestamp", None)) or _when(getattr(snap, "espn_fetched", None))
    return _when(getattr(snap, "sleeper_fetched", None))


def availability_rows(snap: Any) -> list[dict]:
    """The status moves between the last copy and this one, as rows (runs on the writer thread)."""
    global _avail_last, _avail_present
    from league_lab import news_feed as NF
    present = (getattr(snap, "espn_fetched", None) is not None, bool(getattr(snap, "_players", None)))
    if not all(present):
        return []                       # a source that failed to load is not a status move: wait for both
    cur = current_statuses(snap)
    if _avail_last is None:
        _avail_last = _store_statuses()
    rows: list[dict] = []
    for g, c in cur.items():
        prev = _avail_last.get(g)
        if (prev or {}).get("code", "ACTIVE") == c["code"]:
            continue
        eid, sid = c.get("espn_id"), c.get("sleeper_id")
        rows.append(make("availability", source=c["source"], gsis_id=g, team=c.get("team"),
                         game_key=game_key_for(c.get("team")),                                  # ---- IH-2
                         player_key=f"espn:{eid}" if c["source"] == "ESPN" and eid else f"sleeper:{sid}" if sid else None,
                         status=c["code"], headline=_headline(c.get("name"), c["code"], c.get("note")),
                         summary=None, source_url=NF.PLAYER_PAGE.format(id=eid) if c["source"] == "ESPN" and eid else None,
                         published_at=_copy_time(snap, c["source"]), effective_at=c.get("as_of")))
    for g, prev in _avail_last.items():
        if g in cur or prev.get("code", "ACTIVE") == "ACTIVE":
            continue
        src = prev.get("source") or "ESPN"
        rows.append(make("availability", source=src, gsis_id=g, team=prev.get("team"), status="ACTIVE",
                         game_key=game_key_for(prev.get("team")),                               # ---- IH-2
                         headline=_headline(prev.get("name"), "ACTIVE", None),
                         summary=f"No longer listed by {src} (the injury report and Sleeper's directory both clear).",
                         published_at=_copy_time(snap, src) or clock(), effective_at=None))
    _avail_last = {g: {"code": c["code"], "source": c["source"], "team": team_abbr(c.get("team")), "name": c.get("name")}
                   for g, c in cur.items()}
    _avail_present = present
    rows = [r for r in rows if r is not None]
    stats["moves"] += len(rows)
    fresh = []
    with _lock:
        for r in rows:
            if r["fingerprint"] not in _seen:
                _seen[r["fingerprint"]] = None
                fresh.append(r)
    return fresh


# ---- IH-2 (Wave I-H): the game an availability move is about (IG-2 left `game_key` empty). The NFL week in play = the
# week of the first kickoff no more than 12 hours ago (a Monday-night status is still that week's; Tuesday's is the
# next week's); the player's team's game that week (nflverse `game_id` from `analytics.dim_game`, the key V-2's grade
# and the matchup evidence join on); a team on bye that week, an unknown team or an unreadable schedule: null — unknown
# is not a game. Read on the writer thread, cached an hour.
WEEK_GAMES_SQL = """with wk as (select season, week from analytics.dim_game
                               where kickoff_at is not null and kickoff_at >= %s order by kickoff_at limit 1)
                    select g.game_id, g.home_team, g.away_team from analytics.dim_game g join wk using (season, week)"""
GAMES_TTL_S = 3600
GAME_WINDOW = timedelta(hours=12)
_games: tuple[float, dict[str, str]] | None = None


def week_games(now: datetime | None = None) -> dict[str, str]:
    """{team (nflverse abbreviation): game_id} for the week in play; a team on bye is absent. {} when unreadable."""
    global _games
    t = time.monotonic()
    if now is None and _games is not None and t - _games[0] < GAMES_TTL_S:
        return _games[1]
    at = (now or clock()) - GAME_WINDOW
    try:
        df = db.fresh(WEEK_GAMES_SQL, (at,))
    except Exception as exc:  # noqa: BLE001 - no schedule: no game key, never a failed write
        log.warning("events: the schedule could not be read (%s): game_key stays empty", exc.__class__.__name__)
        if now is None:                 # not asked again for five minutes (the writer thread writes rows in batches)
            _games = (t - GAMES_TTL_S + 300, {})
        return {}
    out: dict[str, str] = {}
    for r in df.to_dict("records"):
        gid = r.get("game_id")
        if isinstance(gid, str) and _GAME.match(gid):
            for k in ("home_team", "away_team"):
                if isinstance(r.get(k), str):
                    out[r[k]] = gid
    if now is None:
        _games = (t, out)
    return out


def game_key_for(team: Any, now: datetime | None = None) -> str | None:
    """The nflverse game id of ``team``'s game in the week in play (None: a bye, no team, or no schedule)."""
    t = team_abbr(team)
    if t is None:
        return None
    try:
        return week_games(now).get(t)
    except Exception:  # noqa: BLE001 - a key, never a failure
        return None
# ---- end IH-2


# ------------------------------------------------------------------------------------------------ news and briefs
def item_row(gsis: str, it: Mapping) -> dict | None:
    """A news-line item (``news.for_card`` / ``news.recent`` / ``playerwire.recent``) -> its row."""
    if not isinstance(it, Mapping):
        return None
    if it.get("kind") == "playerwire":
        bid = it.get("brief_id")
        return make("brief", source=str(it.get("source") or "PlayerWire"), gsis_id=gsis,
                    player_key=f"pw:{bid}" if bid else None, status=it.get("verification"), headline=it.get("headline"),
                    summary=it.get("summary"), source_url=it.get("url"), published_at=it.get("date"))
    if (os.environ.get(ESPN_NEWS_ENV) or "").strip().lower() in ("off", "0", "false", "no"):
        return None                     # ESPN's headlines stay out of the store (docs/ESPN_TERMS.md § What we keep)
    return make("news", source=str(it.get("source") or "ESPN"), gsis_id=gsis, status=it.get("about"),
                headline=it.get("headline"), summary=None, source_url=it.get("url"), published_at=it.get("date"))


def observe_items(gsis: str, items: Iterable[Mapping]) -> int:
    """The items a screen showed for one player -> their events (queued; never raises)."""
    if not enabled() or not isinstance(gsis, str):
        return 0
    try:
        return submit(item_row(gsis, it) for it in items or [])
    except Exception:  # noqa: BLE001 - never into a screen
        return 0


# ------------------------------------------------------------------------------------------------ the readers
SELECT = ("select id, kind, player_key, gsis_id, team, game_key, status, headline, summary, source, source_url, "
          f"published_at, effective_at, ingested_at, superseded_by, fingerprint, {AT} as at from events.events")
FOR_PLAYER_SQL = f"{SELECT} where gsis_id = %s and {AT} >= %s and kind = any(%s) order by {AT} desc, id desc limit {MAX_ROWS}"
FOR_TEAM_SQL = f"{SELECT} where team = %s and {AT} >= %s and kind = any(%s) order by {AT} desc, id desc limit {MAX_ROWS}"
RECENT_SQL = (f"{SELECT} where gsis_id = any(%s) and {AT} >= %s and kind = any(%s) and (superseded_by is null or %s) "
              f"order by {AT} desc, id desc limit {MAX_ROWS}")
INFO_SQL = ("select count(*)::int as rows, count(*) filter (where superseded_by is null)::int as live, "
            "max(ingested_at) as newest from events.events")


def _since(since: Any = None, hours: float | None = None) -> datetime:
    """The window's start, floored to the minute (the query cache keys on it)."""
    if hours is not None:
        d = clock() - timedelta(hours=float(hours))
    else:
        d = _when(since) or EPOCH
    return d.replace(second=0, microsecond=0)


def _kinds(kinds: Iterable[str] | None) -> list[str]:
    ks = [k for k in (kinds or KINDS) if k in KINDS]
    return ks or list(KINDS)


def _rows(sql: str, params: tuple) -> list[dict]:
    global _read_warned
    if not enabled():
        return []
    try:
        df = db.query(sql, params, ttl=READ_TTL_S)
    except Exception as exc:  # noqa: BLE001 - no schema / no grant / unreachable: no events, never an error
        if not _read_warned:
            log.warning("events: the store could not be read (%s): the screens use the live sources",
                        exc.__class__.__name__)
            _read_warned = True
        return []
    _read_warned = False
    out = []
    for r in df.astype(object).where(df.notna(), None).to_dict("records"):
        for k in ("published_at", "effective_at", "ingested_at", "at"):
            r[k] = iso(r.get(k))
        for k in ("id", "superseded_by"):
            r[k] = None if r.get(k) is None else int(r[k])
        r["live"] = r["superseded_by"] is None
        out.append(r)
    return out


def for_player(gsis: str, since: Any = None, kinds: Iterable[str] | None = None) -> list[dict]:
    """His events since ``since`` (all when None), newest first, live and superseded (``live`` says which)."""
    if not isinstance(gsis, str) or not _GSIS.match(gsis):
        return []
    return _rows(FOR_PLAYER_SQL, (gsis, _since(since), _kinds(kinds)))


def for_team(team: str, since: Any = None, kinds: Iterable[str] | None = None) -> list[dict]:
    """A team's events (its players' status moves — a corner's IR included), newest first."""
    t = team_abbr(team)
    if t is None:
        return []
    return _rows(FOR_TEAM_SQL, (t, _since(since), _kinds(kinds)))


def recent(gsis_ids: Iterable[str], hours: float = 24, kinds: Iterable[str] | None = None, *,
           live_only: bool = True) -> list[dict]:
    """The players' events of the last ``hours`` (live only unless asked), newest first."""
    ids = sorted({g for g in gsis_ids or [] if isinstance(g, str) and _GSIS.match(g)})
    if not ids:
        return []
    return _rows(RECENT_SQL, (ids, _since(hours=hours), _kinds(kinds), not live_only))


def cite(ev: Mapping | None) -> dict | None:
    """The compact citation a screen carries: {id, kind, source, url, at, status, headline}."""
    if not ev:
        return None
    return {"id": ev.get("id"), "kind": ev.get("kind"), "source": ev.get("source"), "url": ev.get("source_url"),
            "at": ev.get("at"), "status": ev.get("status"), "headline": ev.get("headline")}


def info() -> dict:
    """/api/status -> events: {enabled, ready, rows, live, newest, process}."""
    if not enabled():
        return {"enabled": False, "rows": None, "newest": None}
    try:
        df = db.query(INFO_SQL, (), ttl=READ_TTL_S)
        r = df.iloc[0] if not df.empty else {}
        return {"enabled": True, "ready": True, "rows": int(r["rows"]), "live": int(r["live"]),
                "newest": iso(r["newest"]), "process": dict(stats)}
    except Exception as exc:  # noqa: BLE001 - a status line, never a failure
        return {"enabled": True, "ready": False, "rows": None, "newest": None, "process": dict(stats),
                "cause": exc.__class__.__name__}
