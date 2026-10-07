"""ESPN's public player news: the headline line on the player card (Wave I-D, N1).

``https://site.api.espn.com/apis/fantasy/v2/games/ffl/news/players?playerId=<espn_id>&limit=5`` (no key; found through
the browser pane 2026-10-03, the shape in ``docs/ESPN_TERMS.md``) answers, newest first, the items ESPN's fantasy
player card shows: RotoWire's per-player blurbs (``type: "Rotowire"``) and ESPN's own stories that name him
(``Story`` / ``HeadlineNews`` / ``Media``). An unknown id answers ``feed: []``.

* **What we keep** (``item``): the headline, the date (``published``), the source ("RotoWire via ESPN" or "ESPN") and
  a link out (the story's ``links.web.href``; a RotoWire blurb has none, so his ESPN player page). Never the
  description or the story body: they are dropped here, before anything is cached.
* **On demand**: one athlete when a card is opened, never in bulk (Trends' and Waivers' rows do not call this).
* **Cache**: ``LEAGUE_LAB_CACHE_DIR/espn_news/<espn_id>.json`` (the kept items + ``fetched_at``) for an hour, 15 minutes
  on a game day (``injury_feed.ttl_s``); a failed call serves the last copy, or nothing.
* **Budget**: a token bucket of ``LEAGUE_LAB_ESPN_NEWS_PER_MIN`` calls a minute (default 60) for the process; an empty
  bucket serves the last copy, or nothing.
* **Fixtures**: ``LEAGUE_LAB_ESPN_FIXTURES=<dir>`` (the injuries' env) reads ``<dir>/news_<espn_id>.json`` (ESPN's
  shape); a test or this sandbox never calls ESPN. In fixture mode an item's age is measured from the answer's own
  ``timestamp`` (so a recorded answer stays as fresh as the day it was recorded).
* **Off**: ``LEAGUE_LAB_NEWS=off``. A feed outage is no line, never an error.

``fresh(items, now)`` is the card's rule: at most 3, newest first, each at most 14 days old (so the newest is
14 days old at most, or there is no line).
"""

from __future__ import annotations

import gzip
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from .injury_feed import FIXTURES_ENV, GAME_DAY_TTL_S, default_game_day, ttl_s
from .sleeper_client import TokenBucket, cache_dir

ESPN_NEWS = "https://site.api.espn.com/apis/fantasy/v2/games/ffl/news/players"
API_ENV = "LEAGUE_LAB_ESPN_NEWS_API"
SWITCH_ENV = "LEAGUE_LAB_NEWS"
PER_MIN_ENV = "LEAGUE_LAB_ESPN_NEWS_PER_MIN"
CACHE_SUBDIR = "espn_news"
LIMIT = 5                       # items asked of ESPN (the card keeps 3)
MAX_ITEMS = 3
MAX_AGE = timedelta(days=14)
PLAYER_PAGE = "https://www.espn.com/nfl/player/_/id/{id}"
USER_AGENT = "league-lab/api (beta; player news line, one athlete per card opened)"
_ESPN_HOST = re.compile(r"^(?:[a-z0-9-]+\.)*espn\.com$")
_DIGITS = re.compile(r"^\d{1,12}$")


class FeedUnavailable(RuntimeError):
    """ESPN could not be reached (or there is no fixture for the athlete)."""


def switched_off() -> bool:
    return (os.environ.get(SWITCH_ENV) or "").strip().lower() in ("off", "0", "false", "no")


def parse_time(s: Any) -> datetime | None:
    """ESPN's dates: "2026-10-03T13:33:00Z" (this feed), "2026-10-02T21:05:11.000+00:00" (the overview's)."""
    if not isinstance(s, str) or not s.strip():
        return None
    try:
        d = datetime.fromisoformat(s.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=UTC)


def _iso(d: datetime) -> str:
    return d.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _link(raw: dict, espn_id: str) -> str:
    """The story's web page when ESPN gives one (https, an espn.com host); his ESPN player page otherwise (RotoWire's
    blurbs only carry an old ``m.espn.go.com`` link)."""
    href = (((raw.get("links") or {}).get("web") or {}).get("href")) if isinstance(raw.get("links"), dict) else None
    if isinstance(href, str):
        u = urllib.parse.urlsplit(href.strip())
        if u.scheme in ("http", "https") and _ESPN_HOST.match((u.hostname or "").lower()):
            return urllib.parse.urlunsplit(("https", u.netloc, u.path, u.query, ""))
    return PLAYER_PAGE.format(id=espn_id)


def item(raw: Any, espn_id: str) -> dict | None:
    """One feed item -> {headline, date, source, url}; None without a headline or a date."""
    if not isinstance(raw, dict):
        return None
    head = " ".join(str(raw.get("headline") or "").split())
    when = parse_time(raw.get("published")) or parse_time(raw.get("lastModified"))
    if not head or when is None:
        return None
    source = "RotoWire via ESPN" if str(raw.get("type") or "").lower() == "rotowire" else "ESPN"
    return {"headline": head, "date": _iso(when), "source": source, "url": _link(raw, espn_id)}


def parse(body: Any, espn_id: str) -> list[dict]:
    """ESPN's answer -> the kept items, newest first, one per headline."""
    feed = (body or {}).get("feed") if isinstance(body, dict) else None
    out: list[dict] = []
    seen: set[str] = set()
    for raw in feed if isinstance(feed, list) else []:
        it = item(raw, espn_id)
        if it is None or it["headline"].lower() in seen:
            continue
        seen.add(it["headline"].lower())
        out.append(it)
    out.sort(key=lambda x: x["date"], reverse=True)
    return out


def fresh(items: Iterable[dict], now: datetime, *, max_age: timedelta = MAX_AGE, n: int = MAX_ITEMS) -> list[dict]:
    """The card's rule: newest first, at most ``n``, each no older than ``max_age`` at ``now`` (an item dated more than
    a day ahead of ``now`` is a bad date: left out)."""
    keep = []
    for it in sorted(items, key=lambda x: x.get("date") or "", reverse=True):
        d = parse_time(it.get("date"))
        if d is None or d < now - max_age or d > now + timedelta(days=1):
            continue
        keep.append({k: it[k] for k in ("headline", "date", "source", "url")})
        if len(keep) >= n:
            break
    return keep


def _per_minute() -> float:
    try:
        return max(0.1, float(os.environ.get(PER_MIN_ENV) or 60))
    except ValueError:
        return 60.0


def clean_id(espn_id: Any) -> str | None:
    s = str(espn_id or "").strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s if _DIGITS.match(s) else None


class NewsFeed:
    """Per-athlete news, cached in memory and on disk with ``fetched_at``. ``wall`` (epoch seconds), ``fetch`` (url ->
    parsed JSON), ``bucket`` and ``cache_dir`` are injectable for the tests."""

    def __init__(self, fixtures: str | Path | None = None, *, url: str | None = None, timeout: float = 3.0,
                 wall: Callable[[], float] = time.time, fetch: Callable[[str], Any] | None = None,
                 cache_root: str | Path | None = None, is_game_day: Callable[[date], bool] | None = None,
                 bucket: TokenBucket | None = None) -> None:
        fx = fixtures if fixtures is not None else os.environ.get(FIXTURES_ENV)
        self.fixtures = Path(fx) if fx else None
        self.url = url or os.environ.get(API_ENV) or ESPN_NEWS
        self.timeout = timeout
        self.wall = wall
        self._fetch = fetch
        root = Path(cache_root) if cache_root is not None else (None if self.fixtures else cache_dir() / CACHE_SUBDIR)
        self.cache_root = root
        self.is_game_day = is_game_day or default_game_day
        self.bucket = bucket or TokenBucket(_per_minute())
        self.calls = 0
        self.failures = 0
        self.stale_served = 0
        self.last_error: str | None = None
        self._mem: dict[str, dict] = {}         # espn_id -> {"fetched_at", "as_of", "items"}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ the copy
    def _path(self, espn_id: str) -> Path | None:
        return None if self.cache_root is None else self.cache_root / f"{espn_id}.json"

    def _from_disk(self, espn_id: str) -> dict | None:
        p = self._path(espn_id)
        if p is None or not p.exists():
            return None
        try:
            d = json.loads(p.read_text())
        except (OSError, json.JSONDecodeError):
            return None
        return d if isinstance(d, dict) and isinstance(d.get("items"), list) else None

    def _to_disk(self, espn_id: str, d: dict) -> None:
        p = self._path(espn_id)
        if p is None:
            return
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_suffix(".tmp")
            tmp.write_text(json.dumps(d))
            tmp.replace(p)
        except OSError:
            pass                                   # a read-only disk: the in-memory copy still serves

    def request_url(self, espn_id: str) -> str:
        return f"{self.url}?{urllib.parse.urlencode({'playerId': espn_id, 'limit': LIMIT})}"

    def _read(self, espn_id: str) -> Any:
        if self._fetch is not None:
            return self._fetch(self.request_url(espn_id))
        if self.fixtures is not None:
            f = self.fixtures / f"news_{espn_id}.json"
            if not f.exists():
                raise FeedUnavailable(f"no fixture {f.name}")
            return json.loads(f.read_text())
        req = urllib.request.Request(self.request_url(espn_id), headers={
            "User-Agent": USER_AGENT, "Accept": "application/json", "Accept-Encoding": "gzip"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:  # noqa: S310 - fixed https host
                body = r.read()
                if (r.headers.get("Content-Encoding") or "").lower() == "gzip":
                    body = gzip.decompress(body)
                return json.loads(body.decode("utf-8") or "{}")
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise FeedUnavailable(f"ESPN news: {exc}") from exc

    def interval_s(self, now: float | None = None) -> int:
        now = self.wall() if now is None else now
        try:
            day = datetime.fromtimestamp(now - 4 * 3600, UTC).date()      # the slate's Eastern day (injury_feed)
            return ttl_s(bool(self.is_game_day(day)))
        except Exception:  # noqa: BLE001 - a schedule lookup failing must not break the line
            return GAME_DAY_TTL_S

    def copy(self, espn_id: Any) -> dict | None:
        """{fetched_at, as_of, items} for one athlete, read from ESPN first when the copy is older than the interval.
        None when there has never been a copy and ESPN cannot be reached (or the bucket is empty)."""
        eid = clean_id(espn_id)
        if eid is None:
            return None
        with self._lock:
            d = self._mem.get(eid)
            if d is None:
                d = self._from_disk(eid)
                if d is not None:
                    self._mem[eid] = d
            now = self.wall()
            if d is not None and now - float(d.get("fetched_at") or 0) < self.interval_s(now):
                return d
            if not self.bucket.take():
                if d is not None:
                    self.stale_served += 1
                return d
            self.calls += 1
        try:                                       # outside the lock: one slow answer does not hold every card
            body = self._read(eid)
            if not isinstance(body, dict) or not body:      # ---- IP-5: an empty body is a failure, not "no news"
                raise FeedUnavailable("ESPN news: an empty answer")
        except (FeedUnavailable, ValueError, TypeError) as exc:
            with self._lock:
                self.failures += 1
                self.last_error = str(exc)[:200]
                if d is not None:
                    self.stale_served += 1
            return d
        stamp = parse_time((body or {}).get("timestamp")) if isinstance(body, dict) else None
        new = {"fetched_at": now, "as_of": _iso(stamp) if stamp else None, "items": parse(body, eid)}
        with self._lock:
            self._mem[eid] = new
            self.last_error = None
        self._to_disk(eid, new)
        return new

    def now_for(self, d: dict) -> datetime:
        """The clock the 14-day rule reads: the wall clock live; the recorded answer's own time on fixtures."""
        if self.fixtures is not None and self._fetch is None and d.get("as_of"):
            t = parse_time(d["as_of"])
            if t is not None:
                return t
        return datetime.fromtimestamp(self.wall(), UTC)

    def latest(self, espn_id: Any) -> list[dict]:
        """The card's ``news``: at most 3 items, newest first, none older than 14 days. [] when there is nothing (no
        news, the feed is off or out)."""
        if switched_off():
            return []
        d = self.copy(espn_id)
        if not d:
            return []
        return fresh(d.get("items") or [], self.now_for(d))

    def stats(self) -> dict:
        return {"mode": "fixtures" if self.fixtures is not None else "live", "calls": self.calls,
                "failures": self.failures, "stale_served": self.stale_served, "athletes_cached": len(self._mem),
                "per_minute": self.bucket.per_minute, "last_error": self.last_error}


_default: NewsFeed | None = None
_default_lock = threading.Lock()


def feed() -> NewsFeed:
    """The process-wide client (one bucket, one cache); rebuilt when the fixture setting changes (tests)."""
    global _default
    fx = os.environ.get(FIXTURES_ENV)
    with _default_lock:
        if _default is None or str(_default.fixtures or "") != str(Path(fx) if fx else ""):
            _default = NewsFeed()
        return _default


def reset() -> None:
    global _default
    with _default_lock:
        _default = None
