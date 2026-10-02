"""The read-only Sleeper client: TTL caches per kind of call, the player directory on disk, one token bucket.

Plan F3 (Wave F) split it out of ``anyleague`` (E3's spike) so the API for any league holds Sleeper's rules in one
place. Sleeper's API is free, read-only and keyless; it asks for **under 1,000 calls a minute** (docs/SLEEPER_TERMS.md).

* **Caches** (``TTL_S``): the player directory (~15 MB) a day, on disk under ``LEAGUE_LAB_CACHE_DIR`` (default
  ``<repo>/.cache/``, git-ignored) so a restart does not re-download it; a league's settings and its users a day;
  rosters 10 minutes; matchups 5 minutes (a played week's matchups and a round's transactions an hour: Wave G); a username lookup and a user's league list an hour; the NFL state an hour.
* **Stale on error**: an expired entry is kept; when Sleeper fails (or the bucket is empty) the last good answer is
  served instead of an error, and the response is no older than the last success.
* **Token bucket** (``TokenBucket``): ``LEAGUE_LAB_SLEEPER_PER_MIN`` calls a minute (default 300, under a third of
  Sleeper's limit), refilled continuously, burst = one minute's worth. A call that finds the bucket empty and has
  nothing cached raises ``SleeperBusy`` (the API answers 503 ``{"error": "busy, try again in a minute"}``).
  One process holds one bucket (``anyleague.sleeper()``, the process-wide client); several processes need a shared one (Wave G).
* **Fixtures**: ``LEAGUE_LAB_SLEEPER_FIXTURES=<dir>`` reads ``league_<id>.json``, ``rosters_<id>.json``,
  ``users_<id>.json``, ``matchups_<id>_<week>.json``, ``transactions_<id>_<round>.json`` (Wave G), ``user_<username>.json``,
  ``user_leagues_<user_id>.json``,
  ``players_nfl.json`` instead of the network (tests and this sandbox never call Sleeper). Fixture reads go through
  the same caches and the same bucket, so the tests exercise both.
* **Clock**: ``clock`` (monotonic seconds) and ``wall`` (epoch seconds, for the disk file's age) are injectable:
  the unit tests drive the TTLs and the bucket with a fake clock.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

SLEEPER_API = "https://api.sleeper.app/v1"
FIXTURES_ENV = "LEAGUE_LAB_SLEEPER_FIXTURES"
API_ENV = "LEAGUE_LAB_SLEEPER_API"            # override the host (a proxy, a mock)
CACHE_DIR_ENV = "LEAGUE_LAB_CACHE_DIR"
PER_MIN_ENV = "LEAGUE_LAB_SLEEPER_PER_MIN"
DEFAULT_PER_MIN = 300                          # Sleeper asks for < 1,000 a minute; we stay under a third of it
REPO = Path(__file__).resolve().parents[2]
PLAYERS_FILE = "sleeper_players_nfl.json"

# seconds an answer is fresh, by kind of call
TTL_S: dict[str, float] = {
    "players": 24 * 3600,       # ~15 MB; Sleeper: at most once a day
    "league": 24 * 3600,        # settings, scoring, slots: change a few times a season
    "users": 24 * 3600,         # team names: cosmetic
    "rosters": 10 * 60,         # waivers and trades
    "matchups": 5 * 60,         # the week's pairings and Sleeper's live points
    "user": 3600,               # username -> user id
    "user_leagues": 3600,       # a user's leagues this season
    "state": 3600,              # the NFL week Sleeper is on
    "season_matchups": 3600,    # Wave G (G2): a played week's matchups (standings, all-play, luck): settled
    "transactions": 3600,       # Wave G (G2): a round's transactions (claims, drops, trades)
}

_ID = re.compile(r"^\d{1,24}$")
_USERNAME = re.compile(r"^[A-Za-z0-9_.\-]{1,40}$")


class LeagueNotFound(LookupError):
    """Sleeper has no such league (or no such roster / user)."""


class SleeperUnavailable(RuntimeError):
    """Sleeper could not be reached (or a fixture is missing)."""


class SleeperBusy(RuntimeError):
    """Our own budget of Sleeper calls is spent for the moment (the token bucket is empty)."""


def check_id(league_id: str) -> str:
    """A Sleeper league / user id is digits; anything else never reaches a URL or a file name."""
    s = str(league_id).strip()
    if not _ID.match(s):
        raise LeagueNotFound(f"not a Sleeper league id: {league_id!r}")
    return s


def check_username(username: str) -> str:
    """Sleeper usernames are letters, digits and _ . - ; lower-cased (Sleeper's lookup ignores case)."""
    s = str(username or "").strip()
    if not _USERNAME.match(s):
        raise LeagueNotFound(f"not a Sleeper username: {username!r}")
    return s.lower()


class TokenBucket:
    """``per_minute`` tokens a minute, refilled continuously, at most ``capacity`` held (default: one minute's).
    ``take()`` spends one if there is one. Thread-safe; ``clock`` is injectable (tests)."""

    def __init__(self, per_minute: float = DEFAULT_PER_MIN, capacity: float | None = None,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.rate = float(per_minute) / 60.0
        self.per_minute = float(per_minute)
        self.capacity = float(capacity if capacity is not None else per_minute)
        self.clock = clock
        self._tokens = self.capacity
        self._t = clock()
        self._lock = threading.Lock()
        self.refused = 0

    def _refill(self) -> None:
        now = self.clock()
        self._tokens = min(self.capacity, self._tokens + (now - self._t) * self.rate)
        self._t = now

    def take(self, n: float = 1.0) -> bool:
        with self._lock:
            self._refill()
            if self._tokens >= n:
                self._tokens -= n
                return True
            self.refused += 1
            return False

    def tokens(self) -> float:
        with self._lock:
            self._refill()
            return self._tokens

    def seconds_until(self, n: float = 1.0) -> float:
        with self._lock:
            self._refill()
            return max(0.0, (n - self._tokens) / self.rate) if self.rate > 0 else float("inf")


def _per_minute() -> float:
    try:
        return max(1.0, float(os.environ.get(PER_MIN_ENV) or DEFAULT_PER_MIN))
    except ValueError:
        return float(DEFAULT_PER_MIN)


def cache_dir() -> Path:
    return Path(os.environ.get(CACHE_DIR_ENV) or REPO / ".cache")


class Sleeper:
    """Read-only Sleeper client: TTL caches by kind, the player directory on disk, one token bucket; fixture mode
    when ``LEAGUE_LAB_SLEEPER_FIXTURES`` is set (or ``fixtures`` is passed)."""

    def __init__(self, fixtures: str | Path | None = None, base: str | None = None, timeout: float = 10.0, *,
                 clock: Callable[[], float] = time.monotonic, wall: Callable[[], float] = time.time,
                 bucket: TokenBucket | None = None, cache_path: str | Path | None = None,
                 fetch: Callable[[str], Any] | None = None) -> None:
        fx = fixtures if fixtures is not None else os.environ.get(FIXTURES_ENV)
        self.fixtures = Path(fx) if fx else None
        self.base = (base or os.environ.get(API_ENV) or SLEEPER_API).rstrip("/")
        self.timeout = timeout
        self.clock, self.wall = clock, wall
        self.bucket = bucket or TokenBucket(_per_minute(), clock=clock)
        # the disk copy of the player directory: never in fixture mode unless asked (tests pass cache_path)
        self.cache_path = Path(cache_path) if cache_path is not None else (None if self.fixtures else cache_dir())
        self._fetch = fetch
        self.calls = 0                         # reads that went to Sleeper (or a fixture file)
        self.stale_served = 0                  # answers served past their TTL because Sleeper failed / we were busy
        self._cache: dict[str, tuple[float, float, str, Any]] = {}   # path -> (expires, fetched, kind, data)
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ the one read
    def _read(self, path: str, fixture: str) -> Any:
        if self._fetch is not None:
            return self._fetch(path)
        if self.fixtures is not None:
            f = self.fixtures / fixture
            if not f.exists():
                if fixture.startswith(("league_", "user_")) and not fixture.startswith("user_leagues_"):
                    return None                # what Sleeper answers for an id / username it does not have
                if fixture.startswith(("matchups_", "transactions_")):
                    return []                  # a week Sleeper has no pairings (or no transactions) for
                raise SleeperUnavailable(f"no fixture {f}")
            return json.loads(f.read_text())
        req = urllib.request.Request(f"{self.base}{path}", headers={"User-Agent": "league-lab/api"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:  # noqa: S310 - fixed https host
                return json.loads(r.read().decode("utf-8") or "null")
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise SleeperUnavailable(f"Sleeper {path}: {exc}") from exc

    def _get(self, path: str, fixture: str, kind: str) -> Any:
        now = self.clock()
        with self._lock:
            hit = self._cache.get(path)
        if hit is not None and hit[0] > now:
            return hit[3]
        if kind == "players":
            disk = self._players_from_disk()
            if disk is not None:
                return disk
        if not self.bucket.take():
            if hit is not None:                # busy: the last good answer beats an error
                self.stale_served += 1
                return hit[3]
            raise SleeperBusy("busy, try again in a minute")
        self.calls += 1
        try:
            data = self._read(path, fixture)
        except SleeperUnavailable:
            if hit is not None:
                self.stale_served += 1
                return hit[3]
            raise
        with self._lock:
            self._cache[path] = (now + TTL_S[kind], now, kind, data)
        if kind == "players":
            self._players_to_disk(data)
        return data

    # ------------------------------------------------------------------ the player directory on disk
    def _players_file(self) -> Path | None:
        return None if self.cache_path is None else self.cache_path / PLAYERS_FILE

    def _players_from_disk(self) -> dict | None:
        f = self._players_file()
        if f is None or not f.exists():
            return None
        age = self.wall() - f.stat().st_mtime
        if age >= TTL_S["players"]:
            return None
        try:
            data = json.loads(f.read_text())
        except (OSError, json.JSONDecodeError):
            return None
        now = self.clock()
        with self._lock:                       # in memory for the rest of the file's day
            self._cache["/players/nfl"] = (now + TTL_S["players"] - age, now - age, "players", data)
        return data

    def _players_to_disk(self, data: Any) -> None:
        f = self._players_file()
        if f is None or not isinstance(data, dict) or not data:
            return
        try:
            f.parent.mkdir(parents=True, exist_ok=True)
            tmp = f.with_suffix(".tmp")
            tmp.write_text(json.dumps(data))
            tmp.replace(f)
        except OSError:
            pass                               # a read-only disk: the in-memory copy still holds the day

    # ------------------------------------------------------------------ the calls
    def league(self, league_id: str) -> dict:
        league_id = check_id(league_id)
        data = self._get(f"/league/{league_id}", f"league_{league_id}.json", "league")
        if not isinstance(data, dict) or data.get("sport", "nfl") != "nfl":
            raise LeagueNotFound(f"no Sleeper NFL league {league_id}")
        return data

    def rosters(self, league_id: str) -> list[dict]:
        league_id = check_id(league_id)
        return list(self._get(f"/league/{league_id}/rosters", f"rosters_{league_id}.json", "rosters") or [])

    def users(self, league_id: str) -> list[dict]:
        league_id = check_id(league_id)
        return list(self._get(f"/league/{league_id}/users", f"users_{league_id}.json", "users") or [])

    def matchups(self, league_id: str, week: int) -> list[dict]:
        league_id = check_id(league_id)
        return list(self._get(f"/league/{league_id}/matchups/{int(week)}", f"matchups_{league_id}_{int(week)}.json",
                              "matchups") or [])

    def season_matchups(self, league_id: str, through_week: int) -> dict[int, list[dict]]:
        """Wave G (G2): every played week's matchups, weeks 1..``through_week`` (``/league/<id>/matchups/<week>`` each,
        cached an hour: a played week is settled), for standings, all-play and luck in a league the database lacks."""
        league_id = check_id(league_id)
        return {w: list(self._get(f"/league/{league_id}/matchups/{w}", f"matchups_{league_id}_{w}.json", "season_matchups") or [])
                for w in range(1, int(through_week) + 1)}

    def transactions(self, league_id: str, round_: int) -> list[dict]:
        """Wave G (G2): one round's transactions (``/league/<id>/transactions/<round>``: waiver claims, free-agent adds,
        drops, trades; a round is a week), cached an hour."""
        league_id = check_id(league_id)
        return list(self._get(f"/league/{league_id}/transactions/{int(round_)}", f"transactions_{league_id}_{int(round_)}.json",
                              "transactions") or [])

    def players(self) -> dict[str, dict]:
        return dict(self._get("/players/nfl", "players_nfl.json", "players") or {})

    def user(self, username: str) -> dict:
        name = check_username(username)
        u = self._get(f"/user/{name}", f"user_{name}.json", "user")
        if not isinstance(u, dict) or not u.get("user_id"):
            raise LeagueNotFound(f"no Sleeper user {username}")
        return u

    def user_leagues(self, user_id: str, season: int) -> list[dict]:
        """A user's NFL leagues of a season (``/user/<id>/leagues/nfl/<season>``: full league objects)."""
        uid = check_id(user_id)
        return list(self._get(f"/user/{uid}/leagues/nfl/{int(season)}", f"user_leagues_{uid}.json", "user_leagues") or [])

    def state(self) -> dict:
        return dict(self._get("/state/nfl", "state_nfl.json", "state") or {})

    # ------------------------------------------------------------------ the status line
    def stats(self) -> dict:
        """What /api/status shows: calls made, the bucket, and per kind of call the cached entries and their ages."""
        now = self.clock()
        with self._lock:
            entries = list(self._cache.values())
        kinds: dict[str, dict] = {}
        for exp, fetched, kind, _ in entries:
            k = kinds.setdefault(kind, {"entries": 0, "fresh": 0, "oldest_s": 0.0, "newest_s": None, "ttl_s": TTL_S[kind]})
            age = max(0.0, now - fetched)
            k["entries"] += 1
            k["fresh"] += int(exp > now)
            k["oldest_s"] = round(max(k["oldest_s"], age), 1)
            k["newest_s"] = round(age if k["newest_s"] is None else min(k["newest_s"], age), 1)
        f = self._players_file()
        disk_age = round(self.wall() - f.stat().st_mtime, 1) if f is not None and f.exists() else None
        return {"mode": "fixtures" if self.fixtures is not None else "live", "calls": self.calls,
                "stale_served": self.stale_served,
                "bucket": {"tokens": round(self.bucket.tokens(), 1), "capacity": self.bucket.capacity,
                           "per_minute": self.bucket.per_minute, "refused": self.bucket.refused},
                "cache": kinds, "players_file_age_s": disk_age}
