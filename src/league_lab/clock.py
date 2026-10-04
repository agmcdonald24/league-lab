"""What time it is for the league (Wave I-I, INF-1).

The on-demand path decides locks (a game kicked off), the week's frame and "this week" from the time. A test suite
run on a Sunday afternoon would otherwise see players lock as the games kick off, and the answers it pins move with
the hour. One clock, read on every call:

    now()  →  pin(...) if pinned in this process, else LEAGUE_LAB_NOW (ISO 8601, UTC) if set, else datetime.now(UTC)

`LEAGUE_LAB_NOW` is unset in production (Render): `now()` is the real time there. The suites set it for the whole
session (`tests/conftest.py`, `api/tests/conftest.py`) so a subprocess (the Streamlit twin) sees the same moment.

Use it for the league's "now" on the request path. Do not use it for stamps of a real event (when a feed was fetched,
when a usage count arrived, a write's `run_at`) or for the stale rule (`freshness.py` keeps its own injectable
clock: a pinned clock must never hide a missed morning).
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

ENV = "LEAGUE_LAB_NOW"

_pinned: datetime | None = None


def parse(value: str | datetime) -> datetime:
    """An ISO 8601 moment as an aware UTC datetime. `Z`, any offset (converted) and a naive time (taken as UTC)."""
    if isinstance(value, datetime):
        t = value
    else:
        s = str(value).strip()
        if not s:
            raise ValueError(f"{ENV}: empty")
        t = datetime.fromisoformat(s[:-1] + "+00:00" if s[-1] in "Zz" else s)
    return t.replace(tzinfo=UTC) if t.tzinfo is None else t.astimezone(UTC)


def now() -> datetime:
    """The league's now (aware, UTC). See the module's docstring for the order."""
    if _pinned is not None:
        return _pinned
    env = os.environ.get(ENV, "").strip()
    if env:
        return parse(env)
    return datetime.now(UTC)


def now_floored(step_minutes: int = 5) -> datetime:
    """`now()` down to the last `step_minutes` mark (seconds dropped). For a value that goes into a cached query:
    NFL kickoffs are on five-minute marks (1:00, 4:05, 4:25, 8:20 PM ET), so "kicked off by now" is exact with the
    default step, and the cache key changes every five minutes instead of every call."""
    t = now()
    return t.replace(minute=t.minute - t.minute % max(1, int(step_minutes)), second=0, microsecond=0)


def pin(when: str | datetime) -> datetime:
    """Fix `now()` in this process (tests). Returns the pinned moment."""
    global _pinned
    _pinned = parse(when)
    return _pinned


def unpin() -> None:
    """Back to `LEAGUE_LAB_NOW`, else the real time."""
    global _pinned
    _pinned = None


def is_pinned() -> bool:
    """A pin in this process or `LEAGUE_LAB_NOW` set."""
    return _pinned is not None or bool(os.environ.get(ENV, "").strip())


@contextmanager
def pinned(when: str | datetime) -> Iterator[datetime]:
    """`with pinned("2026-10-05T17:30:00Z"):` — the previous pin comes back after."""
    global _pinned
    before = _pinned
    try:
        yield pin(when)
    finally:
        _pinned = before
