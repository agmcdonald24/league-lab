"""ESPN's public NFL injuries feed: the read-only client of the availability overlay (Wave I-0, I0-A).

``https://site.api.espn.com/apis/site/v2/sports/football/nfl/injuries`` (no key) lists, per NFL team, every player
on the injury report with his game status (``Out``, ``Doubtful``, ``Questionable``, ``Injured Reserve``, ``Active``),
when it last changed (``date``) and the body part (``details.type``). It moves within minutes of a team's ruling
(Justin Jefferson, ruled out 2026-10-02 at 18:35 UTC, was there 20 minutes before Sleeper's directory had him), so
the API checks it at request time instead of waiting for the nightly build.

* **Polling** (``ttl_s``): every 15 minutes on a game day (a game that day in ``analytics.dim_game``: Thursday,
  Sunday, Monday and the Saturday / holiday slates; the caller passes ``is_game_day``), hourly otherwise.
* **Cache**: the parsed entries (not ESPN's 8.7 MB body) in ``LEAGUE_LAB_CACHE_DIR/espn_injuries.json`` with
  ``fetched_at``; a restart reads it back. A failed download keeps the last copy (``stale_served``).
* **Budget**: a token bucket of ``LEAGUE_LAB_ESPN_PER_MIN`` calls a minute (default 2): one process never asks ESPN
  more than a couple of times a minute, whatever the traffic.
* **Fixtures**: ``LEAGUE_LAB_ESPN_FIXTURES=<dir>`` reads ``<dir>/injuries.json`` (ESPN's shape) instead of the
  network; tests and this sandbox never call ESPN.

The athlete id is not a field of the entry: it is in the athlete's links (``.../player/_/id/4262921/...``) and in
the app link's ``uid`` (``a:4262921``); ``athlete.id`` is taken when ESPN sends one.
"""

from __future__ import annotations

import gzip
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from .sleeper_client import TokenBucket, cache_dir

ESPN_INJURIES = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/injuries"
FIXTURES_ENV = "LEAGUE_LAB_ESPN_FIXTURES"
API_ENV = "LEAGUE_LAB_ESPN_API"
PER_MIN_ENV = "LEAGUE_LAB_ESPN_PER_MIN"
CACHE_FILE = "espn_injuries.json"
GAME_DAY_TTL_S = 15 * 60
OFF_DAY_TTL_S = 60 * 60
USER_AGENT = "league-lab/api (beta; availability overlay)"
_ID_IN_HREF = re.compile(r"/id/(\d+)")
_ID_IN_UID = re.compile(r"(?:^|[~:])a:(\d+)")


class FeedUnavailable(RuntimeError):
    """ESPN could not be reached and there is no earlier copy."""


def _parse_time(s: Any) -> datetime | None:
    if not isinstance(s, str) or not s:
        return None
    t = s.strip().replace("Z", "+00:00")
    if re.match(r".*T\d\d:\d\d\+", t):            # ESPN writes minutes only: 2026-10-02T18:35Z
        t = t.replace("+", ":00+", 1)
    try:
        d = datetime.fromisoformat(t)
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=UTC)


def athlete_id(entry: dict) -> str | None:
    a = entry.get("athlete") or {}
    if a.get("id"):
        return str(a["id"])
    for link in a.get("links") or []:
        href = str((link or {}).get("href") or "")
        m = _ID_IN_HREF.search(href) or _ID_IN_UID.search(href)
        if m:
            return m.group(1)
    m = _ID_IN_HREF.search(str((a.get("headshot") or {}).get("href") or ""))
    return m.group(1) if m else None


def parse(feed: dict) -> list[dict]:
    """ESPN's body -> one entry per athlete: espn_id, name, position, team, status (ESPN's word), fantasy (ESPN's
    fantasy status: OUT / IR / PUP-R / INACTIVE ...), injury (body part), date (when it last changed, ISO UTC),
    return_date. An athlete listed twice keeps his newest entry."""
    out: dict[str, dict] = {}
    for team in (feed or {}).get("injuries") or []:
        for e in (team or {}).get("injuries") or []:
            aid = athlete_id(e)
            if not aid:
                continue
            a = e.get("athlete") or {}
            det = e.get("details") or {}
            when = _parse_time(e.get("date"))
            row = {"espn_id": aid, "name": a.get("displayName"),
                   "position": (a.get("position") or {}).get("abbreviation"),
                   "team": (a.get("team") or {}).get("abbreviation") or team.get("displayName"),
                   "status": e.get("status"), "fantasy": (det.get("fantasyStatus") or {}).get("abbreviation"),
                   "injury": det.get("type"), "return_date": det.get("returnDate"),
                   "date": when.isoformat() if when else None}
            old = out.get(aid)
            if old is None or (row["date"] or "") > (old["date"] or ""):
                out[aid] = row
    return list(out.values())


def default_game_day(d: date) -> bool:
    """Without the schedule: Thursday, Sunday and Monday."""
    return d.weekday() in (0, 3, 6)


def ttl_s(game_day: bool) -> int:
    return GAME_DAY_TTL_S if game_day else OFF_DAY_TTL_S


def _per_minute() -> float:
    try:
        return max(0.1, float(os.environ.get(PER_MIN_ENV) or 2))
    except ValueError:
        return 2.0


class InjuryFeed:
    """ESPN's injuries, cached on disk with ``fetched_at``; ``entries()`` refreshes when the copy is older than the
    day's interval. ``wall`` (epoch seconds) and ``fetch`` are injectable for the tests."""

    def __init__(self, fixtures: str | Path | None = None, *, url: str | None = None, timeout: float = 15.0,
                 wall: Callable[[], float] = time.time, fetch: Callable[[str], Any] | None = None,
                 cache_path: str | Path | None = None, is_game_day: Callable[[date], bool] | None = None,
                 bucket: TokenBucket | None = None, background: bool = False) -> None:
        fx = fixtures if fixtures is not None else os.environ.get(FIXTURES_ENV)
        self.fixtures = Path(fx) if fx else None
        self.url = url or os.environ.get(API_ENV) or ESPN_INJURIES
        self.timeout = timeout
        self.wall = wall
        self._fetch = fetch
        self.cache_path = Path(cache_path) if cache_path is not None else (None if self.fixtures else cache_dir() / CACHE_FILE)
        self.is_game_day = is_game_day or default_game_day
        self.bucket = bucket or TokenBucket(_per_minute())
        self.calls = 0
        self.failures = 0
        self.stale_served = 0
        self.last_error: str | None = None
        self._data: dict | None = None            # {"fetched_at": epoch, "source_timestamp": str, "entries": [...]}
        self._lock = threading.Lock()
        self.background = background              # a stale copy is served while a thread reads ESPN (live server)
        self._refreshing = False

    # ------------------------------------------------------------------ the copy
    def _from_disk(self) -> dict | None:
        if self.cache_path is None or not self.cache_path.exists():
            return None
        try:
            d = json.loads(self.cache_path.read_text())
        except (OSError, json.JSONDecodeError):
            return None
        return d if isinstance(d, dict) and isinstance(d.get("entries"), list) else None

    def _to_disk(self, d: dict) -> None:
        if self.cache_path is None:
            return
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.cache_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(d))
            tmp.replace(self.cache_path)
        except OSError:
            pass                                   # a read-only disk: the in-memory copy still serves

    def _read(self) -> dict:
        if self._fetch is not None:
            return self._fetch(self.url)
        if self.fixtures is not None:
            f = self.fixtures / "injuries.json"
            if not f.exists():
                raise FeedUnavailable(f"no fixture {f}")
            return json.loads(f.read_text())
        req = urllib.request.Request(self.url, headers={"User-Agent": USER_AGENT, "Accept": "application/json",
                                                        "Accept-Encoding": "gzip"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:  # noqa: S310 - fixed https host
                body = r.read()
                if (r.headers.get("Content-Encoding") or "").lower() == "gzip":
                    body = gzip.decompress(body)
                return json.loads(body.decode("utf-8") or "{}")
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise FeedUnavailable(f"ESPN injuries: {exc}") from exc

    def interval_s(self, now: float | None = None) -> int:
        now = self.wall() if now is None else now
        try:
            # the slate is an Eastern-time day; ET is UTC-4 / -5 in season: -4 h is right on every game night but
            # the few hours after a late Monday game, when "game day" holds anyway
            day = datetime.fromtimestamp(now - 4 * 3600, UTC).date()
            return ttl_s(bool(self.is_game_day(day)))
        except Exception:  # noqa: BLE001 - a schedule lookup failing must not break the feed
            return GAME_DAY_TTL_S

    def snapshot(self, *, refresh: bool = True) -> dict | None:
        """The current copy ({fetched_at, source_timestamp, entries}), refreshed first when it is older than the
        interval (``refresh``). None when there has never been a copy and ESPN cannot be reached."""
        with self._lock:
            if self._data is None:
                self._data = self._from_disk()
            d = self._data
            now = self.wall()
            if not refresh or (d is not None and now - float(d.get("fetched_at") or 0) < self.interval_s(now)):
                return d
            if self.background and d is not None:
                if not self._refreshing:          # serve the copy now; one thread reads ESPN for the next request
                    self._refreshing = True
                    threading.Thread(target=self._refresh, daemon=True).start()
                return d
            return self._refresh_locked(now, d)

    def _refresh(self) -> None:
        try:
            with self._lock:
                self._refresh_locked(self.wall(), self._data)
        finally:
            self._refreshing = False

    def _refresh_locked(self, now: float, d: dict | None) -> dict | None:
        if not self.bucket.take():
            if d is not None:
                self.stale_served += 1
            return d
        self.calls += 1
        try:
            feed = self._read()
        except (FeedUnavailable, ValueError) as exc:
            self.failures += 1
            self.last_error = str(exc)[:200]
            if d is not None:
                self.stale_served += 1
            return d
        self._data = {"fetched_at": now, "source_timestamp": (feed or {}).get("timestamp"), "entries": parse(feed)}
        self.last_error = None
        self._to_disk(self._data)
        return self._data

    def fetched_at(self) -> datetime | None:
        d = self.snapshot(refresh=False)
        return datetime.fromtimestamp(float(d["fetched_at"]), UTC) if d and d.get("fetched_at") else None

    def stats(self) -> dict:
        d = self.snapshot(refresh=False)
        age = None if not d else round(self.wall() - float(d.get("fetched_at") or 0), 1)
        return {"mode": "fixtures" if self.fixtures is not None else "live", "calls": self.calls, "failures": self.failures,
                "stale_served": self.stale_served, "age_s": age, "interval_s": self.interval_s(),
                "entries": None if not d else len(d.get("entries") or []), "last_error": self.last_error}


_default: InjuryFeed | None = None


def feed() -> InjuryFeed:
    """The process-wide client (one copy, one bucket); rebuilt when the fixture setting changes (tests)."""
    global _default
    fx = os.environ.get(FIXTURES_ENV)
    if _default is None or str(_default.fixtures or "") != str(Path(fx) if fx else ""):
        _default = InjuryFeed(background=not fx)
    return _default


def reset() -> None:
    global _default
    _default = None
