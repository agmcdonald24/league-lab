"""A refused or failed provider read is never remembered as "nothing there" (Wave I-P, IP-5; docs/SECURITY_PUBLIC.md § 15).

Wave I-O gave each visitor a share of the providers' budget (``provider_share``), so a refused read is common now: a
visitor whose share is spent is refused while everyone else is served. Many readers turn a refusal into a default — no
opponent, no live points, an empty directory, a player "unmapped" — which is right for the one answer (unknown, never
0) and wrong for a cache another visitor reads next. Here:

* **The provider clients** (Sleeper, MFL) call ``note("busy" | "failed")`` when a read raises — refused with nothing
  held, or the provider failed with nothing held. A read served from what the client holds (even past its TTL) is not
  trouble: the held answer is the last good one.
* **A cache** builds inside ``watch()``: every note made while it builds — in this thread or in a pool started with the
  request's context (``contextvars.copy_context``, the rule test_io4 enforces) — lands on the watch. A troubled build is
  **not kept**; ``kept()`` serves the last good value it holds for the key (its own stamps ride with it), else the
  request answers busy (``SleeperBusy`` → 503 "busy, try again in a minute", the app's words).
* A reader that recovers a refusal by serving a held good value of its own calls ``forgive(exc)``: the note is taken
  back from the watches open now.

Nothing here reads a provider, a database or the clock beyond ``time.monotonic``.
"""

from __future__ import annotations

import contextvars
import threading
import time
from collections.abc import Callable, Hashable, Iterator
from contextlib import contextmanager
from typing import Any

HOLD_S = 6 * 3600.0          # how long a cache keeps its last good value for a troubled rebuild (the LRU budget still evicts)


class Watch:
    """The trouble one build met: ``busy`` refusals and ``failed`` reads (counted, not raised)."""

    __slots__ = ("busy", "failed")

    def __init__(self) -> None:
        self.busy = 0
        self.failed = 0

    @property
    def clean(self) -> bool:
        return self.busy <= 0 and self.failed <= 0


_WATCHES: contextvars.ContextVar[tuple[Watch, ...]] = contextvars.ContextVar("league_lab_provider_trouble", default=())
_lock = threading.Lock()
TOTALS = {"busy": 0, "failed": 0, "forgiven": 0, "not_kept": 0, "kept_served": 0}


def _kind(exc: BaseException | str) -> str:
    if isinstance(exc, str):
        return "busy" if exc == "busy" else "failed"
    from .sleeper_client import SleeperBusy
    return "busy" if isinstance(exc, SleeperBusy) else "failed"


def note(kind: BaseException | str) -> None:
    """A provider read raised (refused / failed with nothing held): every open watch of this context counts it."""
    k = _kind(kind)
    with _lock:
        TOTALS[k] += 1
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
    * else rebuilt under ``watch()``: clean → kept and returned; troubled (a refusal or failure was swallowed below) or
      raised busy / unavailable → the last good value held for ``key`` (with the stamps it carries), else
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
    if held is not None:
        _absorb(w)
        return held[2]
    raise SleeperBusy("busy, try again in a minute")


def _absorb(w: Watch) -> None:
    """A held good value answered for a troubled build: the watches still open (a cache around this one) do not count
    the trouble this one absorbed."""
    with _lock:
        TOTALS["kept_served"] += 1
        for o in _WATCHES.get():
            o.busy, o.failed = max(0, o.busy - w.busy), max(0, o.failed - w.failed)


def _count(k: str) -> None:
    with _lock:
        TOTALS[k] += 1


def info() -> dict:
    """``/api/status``-style counts (process-wide)."""
    with _lock:
        return dict(TOTALS)
