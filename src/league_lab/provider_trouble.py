"""A refused or failed provider read is never remembered as "nothing there" (Wave I-P, IP-5; docs/SECURITY_PUBLIC.md § 15).

Wave I-O gave each visitor a share of the providers' budget (``provider_share``), so a refused read is common now: a
visitor whose share is spent is refused while everyone else is served. Many readers turn a refusal into a default — no
opponent, no live points, an empty directory, a player "unmapped" — which is right for the one answer (unknown, never
0) and wrong for a cache another visitor reads next. Here:

* **The provider clients** (Sleeper, MFL, ESPN, Yahoo) call ``note("busy" | "failed")`` when a read raises — refused
  with nothing held, or the provider failed with nothing held — and ``note("stale")`` when they serve a held answer past
  its TTL (fix round, review M1: one client with its share spent must not pin everyone to its old reads). A held answer
  is served at most ``max_age`` after it was read (``STALE_MAX_S``); older, the requester gets busy.
* **A cache** builds inside ``watch()``: every note made while it builds — in this thread or in a pool started with the
  request's context (``contextvars.copy_context``, the rule test_io4 enforces) — lands on the watch. A troubled build is
  **not kept**; ``kept()`` serves the last good value it holds for the key (its own stamps ride with it), else the
  request answers busy (``SleeperBusy`` → 503 "busy, try again in a minute", the app's words).
* A reader that recovers a refusal by serving a held good value of its own calls ``forgive(exc)``: the note is taken
  back from the watches open now.

Nothing here reads a provider or a database; the clock: ``time.monotonic`` and the wall clock's weekday (``game_day``).
"""

from __future__ import annotations

import contextvars
import threading
import time
from collections.abc import Callable, Hashable, Iterator
from contextlib import contextmanager
from typing import Any

HOLD_S = 15 * 60.0           # a cache's last good value for a troubled rebuild (fix round: the game-day roster bound)


class Watch:
    """What one build met: ``busy`` refusals and ``failed`` reads (counted, not raised) — trouble — and ``stale``: a
    held answer served past its TTL (fix round, review M1). Trouble: never kept, the held value or busy. Stale only:
    the requester gets the answer, nothing is kept (another client must not be pinned to this client's old reads)."""

    __slots__ = ("busy", "failed", "stale")

    def __init__(self) -> None:
        self.busy = 0
        self.failed = 0
        self.stale = 0

    @property
    def troubled(self) -> bool:
        return self.busy > 0 or self.failed > 0

    @property
    def clean(self) -> bool:
        return not self.troubled and self.stale <= 0


_WATCHES: contextvars.ContextVar[tuple[Watch, ...]] = contextvars.ContextVar("league_lab_provider_trouble", default=())
_lock = threading.Lock()
TOTALS = {"busy": 0, "failed": 0, "stale_served": 0, "forgiven": 0, "not_kept": 0, "kept_served": 0}

# ---- fix round (review M1): how old a held answer may be when it is served past its TTL (seconds since it was read,
# per provider and kind of read); older, the requester gets busy (refused) or the failure (the provider failed). A game
# day (Thursday, Sunday, Monday in New York) tightens the live reads: rosters 15 minutes, this week's scores 10.
MIN, HOUR, DAY = 60.0, 3600.0, 86400.0
STALE_MAX_S: dict[str, dict[str, float]] = {
    "sleeper": {"players": 2 * DAY, "league": 2 * DAY, "users": 2 * DAY, "rosters": 30 * MIN, "matchups": 15 * MIN,
                "user": DAY, "user_leagues": DAY, "state": DAY, "season_matchups": DAY, "transactions": DAY},
    "mfl": {"league": 2 * DAY, "rules": 2 * DAY, "players": 2 * DAY, "rosters": 30 * MIN, "live_scoring": 15 * MIN,
            "schedule": DAY, "weekly_results": DAY, "standings": HOUR, "injuries": 6 * HOUR, "search": HOUR,
            "transactions": HOUR, "transactions_past": 2 * DAY},
    "espn": {"settings": 2 * DAY, "status": HOUR, "teams": DAY, "rosters": 30 * MIN, "schedule": 15 * MIN,
             "transactions": HOUR, "free_agents": DAY},
    "yahoo": {"game": 2 * DAY, "game_weeks": 2 * DAY, "settings": DAY, "teams": HOUR, "standings": HOUR,
              "roster": 30 * MIN, "scoreboard": 15 * MIN, "transactions": HOUR, "players": HOUR, "user": HOUR},
}
GAME_DAY_MAX_S: dict[str, dict[str, float]] = {
    "sleeper": {"rosters": 15 * MIN, "matchups": 10 * MIN}, "mfl": {"rosters": 15 * MIN, "live_scoring": 10 * MIN},
    "espn": {"rosters": 15 * MIN, "schedule": 10 * MIN}, "yahoo": {"roster": 15 * MIN, "scoreboard": 10 * MIN},
}
DEFAULT_MAX_S = 15 * MIN                     # a kind not listed: a quarter of an hour


def game_day(wall: float | None = None) -> bool:
    """Thursday, Sunday or Monday in New York (the wall clock; no schedule read)."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    t = datetime.fromtimestamp(time.time() if wall is None else float(wall), ZoneInfo("America/New_York"))
    return t.weekday() in (0, 3, 6)


def max_age(provider: str, kind: str, wall: float | None = None) -> float:
    """How old a held answer of this kind may be served (seconds since read)."""
    if game_day(wall) and kind in GAME_DAY_MAX_S.get(provider, {}):
        return GAME_DAY_MAX_S[provider][kind]
    return STALE_MAX_S.get(provider, {}).get(kind, DEFAULT_MAX_S)


def held_usable(provider: str, kind: str, age_s: float, wall: float | None = None) -> bool:
    """A held answer read ``age_s`` seconds ago may be served past its TTL (and is then noted ``stale``)."""
    return float(age_s) <= max_age(provider, kind, wall)


def serve_held(client: Any, provider: str, hit: tuple | None, kind: str, now: float) -> bool:
    """A provider client's held answer ``hit`` = (expires, fetched, kind, data) may answer a refused / failed read: True
    when it is younger than ``max_age`` (the client's ``stale_served`` counts it and it is noted ``stale``)."""
    wall = client.wall() if callable(getattr(client, "wall", None)) else None
    if hit is None or not held_usable(provider, kind, now - hit[1], wall):
        return False
    client.stale_served = getattr(client, "stale_served", 0) + 1
    note("stale")
    return True


def fixture_gap(exc: BaseException) -> bool:
    """A fixture file never recorded (tests, e2e): the reader's old "not there" default stands; a real refusal or
    failure is raised (fix round: never an empty default that reaches an answer)."""
    return str(exc).startswith("no fixture")


def _kind(exc: BaseException | str) -> str:
    if isinstance(exc, str):
        return exc if exc in ("busy", "stale") else "failed"
    from .sleeper_client import SleeperBusy
    return "busy" if isinstance(exc, SleeperBusy) else "failed"


def note(kind: BaseException | str) -> None:
    """A provider read raised (refused / failed with nothing held), or (``"stale"``) a held answer was served past its
    TTL: every open watch of this context counts it. ``stale`` is not trouble in ``TOTALS`` (``stale_served``)."""
    k = _kind(kind)
    with _lock:
        TOTALS["stale_served" if k == "stale" else k] += 1
        for w in _WATCHES.get():
            setattr(w, k, getattr(w, k) + 1)


def forgive(exc: BaseException | str) -> None:
    """The caller recovered ``exc`` with a held good value of its own: the note is taken back."""
    k = _kind(exc)
    with _lock:
        TOTALS["forgiven"] += 1
        for w in _WATCHES.get():
            setattr(w, k, max(0, getattr(w, k) - 1))


@contextmanager
def watch() -> Iterator[Watch]:
    """Count the trouble of what runs inside (nested watches each count it)."""
    w = Watch()
    token = _WATCHES.set((*_WATCHES.get(), w))
    try:
        yield w
    finally:
        _WATCHES.reset(token)


def kept(region: Any, key: Hashable, build: Callable[[], Any], *, ttl: float, stamp: Hashable = None,
         hold_s: float = HOLD_S, clock: Callable[[], float] = time.monotonic) -> Any:
    """``build()`` kept in ``region`` (a ``memo.Region``) for ``ttl`` seconds as ``(stamp, fresh_until, value)``; the
    entry itself lives ``max(ttl, hold_s)`` (the budget's LRU still evicts it) so a troubled rebuild can serve it.

    * fresh (same ``stamp``, inside ``ttl``): the value.
    * else rebuilt under ``watch()``: clean → kept and returned; stale only (a provider answer served past its TTL,
      bounded by ``max_age``) → returned to this requester, nothing kept; troubled (a refusal or failure was swallowed
      below) or raised busy / unavailable → the last good value held for ``key`` (with the stamps it carries), else
      ``SleeperBusy`` — never the troubled value, never kept."""
    from .sleeper_client import SleeperBusy, SleeperUnavailable
    held = region.get(key)
    now = clock()
    if held is not None and held[0] == stamp and held[1] > now:
        return held[2]
    with watch() as w:
        try:
            value = build()
        except (SleeperBusy, SleeperUnavailable):
            if held is not None:
                _absorb(w)
                return held[2]
            raise
    if w.clean:
        region.put(key, (stamp, now + float(ttl), value), ttl=max(float(ttl), float(hold_s)))
        return value
    _count("not_kept")
    if not w.troubled:                       # stale only: this requester's answer, kept for nobody
        return value
    if held is not None:
        _absorb(w)
        return held[2]
    raise SleeperBusy("busy, try again in a minute")


def _absorb(w: Watch) -> None:
    """A held value answered for a troubled build: the watches still open (a cache around this one) do not count the
    trouble this one absorbed — but the value is past its TTL or stamp, so they count it ``stale`` (they serve it and
    keep nothing: review M1)."""
    with _lock:
        TOTALS["kept_served"] += 1
        for o in _WATCHES.get():
            o.busy, o.failed = max(0, o.busy - w.busy), max(0, o.failed - w.failed)
            o.stale += 1


def _count(k: str) -> None:
    with _lock:
        TOTALS[k] += 1


def info() -> dict:
    """``/api/status``-style counts (process-wide)."""
    with _lock:
        return dict(TOTALS)
