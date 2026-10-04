"""Is the data a day old? The one rule the API, the web app and the console share (Wave I-H, IH-1).

`as_of` is the newest `ops.projections.fitted_at` — the same value `/api/health` reports: the morning update
(`scripts/nightly.sh`, dispatched at 07:37 ET) refits the board and publishes it, so a night that did not run or did
not publish leaves `as_of` where it was. The nightly lands about 08:00 ET; 30 hours gives a missed morning six
hours of grace (the trigger's re-checks at 09:37 and 11:37 ET included) before a manager is told.

    nightly_state(as_of)  →  {"as_of", "age_hours", "stale", "limit_hours", "words"}

`stale` is null when `as_of` is unknown (no projections, the database unreachable): unknown is not stale and not
fresh (AGENTS.md rule 5). `words` is the banner's sentence when stale, else null. The web app's overlay (ESPN and
Sleeper's injury feeds, read on request) keeps working when the nightly does not, so the app's words say injury
statuses are still live; the console reads only the nightly's rows and says so instead (`CONSOLE_TAIL`).
docs/HOSTING.md § 5 "When the nightly is late or fails".
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

STALE_AFTER_HOURS = 30
STALE_WORDS = "Yesterday's numbers: the morning update did not run. Injury statuses are still live."
CONSOLE_TAIL = "This console's injury tags are from that update too."
ET = ZoneInfo("America/New_York")


def _now() -> datetime:
    """The clock (a test fixes it)."""
    return datetime.now(UTC)


def _parse(as_of) -> datetime | None:
    if as_of is None:
        return None
    if isinstance(as_of, str):
        if not as_of.strip():
            return None
        as_of = datetime.fromisoformat(as_of.strip().replace("Z", "+00:00"))
    if not isinstance(as_of, datetime):               # a pandas Timestamp is a datetime; anything else is unknown
        return None
    if as_of != as_of:                                # NaT
        return None
    return as_of if as_of.tzinfo else as_of.replace(tzinfo=UTC)


def stale_words(as_of: datetime, now: datetime, *, console: bool = False) -> str:
    """The banner: "Yesterday's numbers …" when the last update is from yesterday (New York's calendar), else the
    day it is from ("Numbers from Friday, Oct 2: …") — two or more missed mornings."""
    day, today = as_of.astimezone(ET).date(), now.astimezone(ET).date()
    if (today - day).days <= 1:
        first = "Yesterday's numbers: the morning update did not run."
    else:
        first = f"Numbers from {as_of.astimezone(ET):%A, %b %-d}: the morning update has not run since."
    return f"{first} {CONSOLE_TAIL if console else 'Injury statuses are still live.'}"


def nightly_state(as_of, now: datetime | None = None, *, console: bool = False) -> dict:
    """The stale state of the published data (see the module's docstring)."""
    t = _parse(as_of)
    if t is None:
        return {"as_of": None, "age_hours": None, "stale": None, "limit_hours": STALE_AFTER_HOURS, "words": None}
    now = now or _now()
    age = max(0.0, (now - t).total_seconds() / 3600.0)
    stale = age > STALE_AFTER_HOURS
    return {"as_of": t.isoformat(), "age_hours": round(age, 1), "stale": stale, "limit_hours": STALE_AFTER_HOURS,
            "words": stale_words(t, now, console=console) if stale else None}
