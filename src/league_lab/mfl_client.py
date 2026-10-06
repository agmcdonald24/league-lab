"""MyFantasyLeague, read-only (Wave I-0, I0-B): the client and the translation into Sleeper's shapes.

The rest of League Lab only ever sees **Sleeper shapes** (league / users / rosters / matchups dicts, Sleeper player
ids as ``player_key``), so an MFL league is this module plus the dispatch in ``platforms.py``; every screen works
unchanged. MFL's export API is public for leagues that allow it (docs/MFL_TERMS.md); no login, no writes.

* **The client** (``MFL``): ``league``, ``rules``, ``rosters``, ``schedule``, ``standings``, ``live_scoring(week)``,
  ``weekly_results(week)`` (a league's host), ``players(ids)`` (``DETAILS=1``) and ``injuries(week)`` (the ``api.``
  host). Base ``https://api.myfantasyleague.com/<year>/export?TYPE=…&L=…&JSON=1``; MFL redirects a league's calls to
  the league's own ``www4N.`` host: redirects are followed and the host is remembered per league (also read from
  the league's ``baseURL``). A plain User-Agent names us (``USER_AGENT``).
* **Caches by kind** (``TTL_S``): league / rules a day, rosters 10 minutes, schedule / live scoring 5 minutes,
  standings 10 minutes, players a day, injuries an hour; an expired answer is served when MFL fails (stale on error).
* **Budget**: a token bucket of ``LEAGUE_LAB_MFL_PER_MIN`` calls a minute (default 60: MFL is stricter than
  Sleeper); HTTP 429 or an ``error`` body that says to slow down backs off for a minute (``MFLBusy``).
* **Refusals**: a league that does not allow API reads (or does not exist) answers with an ``error`` body ->
  ``LeagueNotFound(PRIVATE_SENTENCE)``.
* **Fixtures**: ``LEAGUE_LAB_MFL_FIXTURES=<dir>`` reads ``<dir>/<league>/<kind>.json`` (``league``, ``rules``,
  ``rosters``, ``schedule``, ``leagueStandings``, ``liveScoring_<w>``, ``weeklyResults_<w>``) and
  ``<dir>/players.json``, ``<dir>/injuries_<w>.json``, ``<dir>/leagueSearch_<slug>.json`` instead of the network,
  through the same caches and bucket.
* **Search by name** (Wave I-0, I0-C): ``league_search(text)`` — MFL's public ``TYPE=leagueSearch`` (the ``api.``
  host, cached 10 minutes, the same bucket) -> this season's leagues whose name has the text, best matches first.
  MFL's ``homeURL`` lacks the colon after ``https``: the link is rebuilt from the id (``home_url``).

The translation (pure functions, tested on fixtures): ``slots`` (MFL's starter limits -> Sleeper slots),
``scoring`` (MFL rules -> Sleeper scoring keys + what is approximated or unpriced), ``franchise_rows``,
``starters_by_franchise``, ``weekly_matchups``.
"""

from __future__ import annotations

import html
import json
import math
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from .sleeper_client import (
    LeagueNotFound,
    SleeperBusy,
    SleeperUnavailable,
    TokenBucket,
    cache_max,
    prune_cache,
)

MFL_API = "https://api.myfantasyleague.com"
FIXTURES_ENV = "LEAGUE_LAB_MFL_FIXTURES"
API_ENV = "LEAGUE_LAB_MFL_API"
YEAR_ENV = "LEAGUE_LAB_MFL_YEAR"
PER_MIN_ENV = "LEAGUE_LAB_MFL_PER_MIN"
DEFAULT_PER_MIN = 60
VERSION = "0.1"
USER_AGENT = f"league-lab/{VERSION} (beta; contact in docs/MFL_TERMS.md)"
PRIVATE_SENTENCE = ("MyFantasyLeague would not share this league: it may be private or the link may be wrong. "
                    "Ask the commissioner to allow API access")

TTL_S: dict[str, float] = {
    "league": 24 * 3600, "rules": 24 * 3600, "rosters": 10 * 60, "schedule": 5 * 60, "live_scoring": 5 * 60,
    "weekly_results": 10 * 60, "standings": 10 * 60, "players": 24 * 3600, "injuries": 3600,
    "search": 10 * 60,                                                     # I0-C: leagueSearch
}
# ---- IL-2 (Wave I-L): the transactions export — this week's (and the season's) 10 minutes; a past week's a day
# (its moves are settled)
TTL_S.update({"transactions": 10 * 60, "transactions_past": 24 * 3600})
# ---- end IL-2
_LEAGUE = re.compile(r"^\d{1,8}$")
_HOST = re.compile(r"^https://(api|www\d{1,3})\.myfantasyleague\.com$")


# ---- IM-3 (Wave I-M): MFL moves a league's calls to its www4N host by a redirect; urllib would follow a redirect to any
# host. Only https://<name>.myfantasyleague.com is followed: anything else is MFLUnavailable (no request leaves for it).
_REDIRECT_OK = re.compile(r"^https://[a-z0-9-]{1,40}\.myfantasyleague\.com(?::443)?(?:/|$)", re.I)


class _MFLRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001 - urllib's signature
        if not _REDIRECT_OK.match(str(newurl or "")):
            raise urllib.error.URLError(f"redirect to another host refused: {urllib.parse.urlparse(str(newurl)).netloc!r}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_OPENER = urllib.request.build_opener(_MFLRedirects)
# ---- end IM-3


class MFLBusy(SleeperBusy):
    """Our MFL budget is spent for the moment (or MFL asked us to slow down)."""


class MFLUnavailable(SleeperUnavailable):
    """MyFantasyLeague could not be reached (or a fixture is missing)."""


def check_league(league_id: str | int) -> str:
    s = str(league_id).strip()
    if not _LEAGUE.match(s):
        raise LeagueNotFound(f"not a MyFantasyLeague league id: {league_id!r}")
    return s


def parse_link(text: str) -> tuple[str, str | None, int | None]:
    """A pasted MFL link (or a bare id) -> (league id, franchise id or None, year or None).
    ``https://www45.myfantasyleague.com/2026/home/21861#0`` / ``…/options?L=21861&F=0004`` / ``21861`` / ``mfl:21861``."""
    s = (text or "").strip()
    if s.lower().startswith("mfl:"):                                     # I0-C: a league key from the search list
        s = s[4:].strip()
    if _LEAGUE.match(s):
        return s, None, None
    m = re.search(r"myfantasyleague\.com/(\d{4})/[a-z_]+/(\d{1,8})", s)
    u = urllib.parse.urlparse(s if "://" in s else "https://" + s)
    q = urllib.parse.parse_qs(u.query)
    year = int(m.group(1)) if m else (int(mm.group(1)) if (mm := re.search(r"/(\d{4})/", u.path)) else None)
    lid = (q.get("L") or [None])[0] or (m.group(2) if m else None)
    fid = (q.get("F") or q.get("FRANCHISE_ID") or [None])[0]
    if not lid or not _LEAGUE.match(lid):
        raise LeagueNotFound("that does not look like a MyFantasyLeague league link")
    if fid is not None and not re.match(r"^\d{4}$", fid):
        fid = None
    return lid, fid, year


# ---- I0-C (Wave I-0): find a league by its name (MFL's public leagueSearch)
SEARCH_MIN = 3            # characters: shorter text is not sent to MFL
SEARCH_MAX = 25           # matches the API shows
_HOME = re.compile(r"^https?:?//(www\d{1,3})\.myfantasyleague\.com/(\d{4})/home/(\d{1,8})/?$", re.I)


def search_text(text: str | None) -> str:
    """The search text as sent to MFL (and cached): spaces collapsed, lower case (MFL matches without case), 60 max."""
    return " ".join(str(text or "").split()).lower()[:60]


def search_slug(text: str | None) -> str:
    """Fixture file name part: ``leagueSearch_<slug>.json`` (``addicts``, ``addicts_1_redraft``)."""
    return re.sub(r"[^a-z0-9]+", "_", search_text(text)).strip("_")


def looks_like_link(text: str | None) -> bool:
    """A link, a league id or a ``mfl:`` key (answered as ``?mfl=`` does), rather than a league's name."""
    s = (text or "").strip().lower()
    return bool(_LEAGUE.match(s)) or "myfantasyleague.com" in s or "://" in s or s.startswith("mfl:")


def rank_matches(rows: list[dict], text: str) -> list[dict]:
    """Best first: the exact name, then names that start with the text, then a word that starts with it, then the
    rest; MFL's order (by league id) within each group."""
    q = search_text(text)
    word = re.compile(r"(^|[^a-z0-9])" + re.escape(q))

    def rank(r: dict) -> int:
        n = " ".join(r["name"].split()).lower()
        return 0 if n == q else 1 if n.startswith(q) else 2 if word.search(n) else 3
    return sorted(rows, key=rank)
# ---- end I0-C


def _year() -> int:
    env = os.environ.get(YEAR_ENV)
    if env and env.isdigit():
        return int(env)
    t = time.gmtime()
    return t.tm_year if t.tm_mon >= 3 else t.tm_year - 1      # MFL opens the new season in the spring


def _per_minute() -> float:
    try:
        return max(1.0, float(os.environ.get(PER_MIN_ENV) or DEFAULT_PER_MIN))
    except ValueError:
        return float(DEFAULT_PER_MIN)


def _as_list(v: Any) -> list:
    """MFL's JSON gives a single element as an object and several as a list."""
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def _t(v: Any) -> str | None:
    """MFL wraps some text in ``{"$t": "..."}``."""
    if isinstance(v, dict):
        v = v.get("$t")
    return None if v is None else str(v)


class MFL:
    """Read-only MyFantasyLeague client (see the module docstring)."""

    def __init__(self, fixtures: str | Path | None = None, year: int | None = None, base: str | None = None,
                 timeout: float = 10.0, *, clock: Callable[[], float] = time.monotonic,
                 bucket: TokenBucket | None = None, fetch: Callable[[str], tuple[str, str]] | None = None) -> None:
        fx = fixtures if fixtures is not None else os.environ.get(FIXTURES_ENV)
        self.fixtures = Path(fx) if fx else None
        self.year = int(year or _year())
        self.base = (base or os.environ.get(API_ENV) or MFL_API).rstrip("/")
        self.timeout = timeout
        self.clock = clock
        self.bucket = bucket or TokenBucket(_per_minute(), clock=clock)
        self._fetch = fetch                      # tests: url -> (final url, body text)
        self.calls = 0
        self.stale_served = 0
        self.hosts: dict[str, str] = {}           # league id -> https://www4N.myfantasyleague.com
        self._backoff_until = 0.0
        self._cache: dict[str, tuple[float, float, str, Any]] = {}
        self._lock = threading.Lock()
        # ---- IG-3: when each cached answer was read from MFL (wall clock, epoch seconds): the "MFL rosters updated" line
        self.wall: Callable[[], float] = time.time
        self._read_at: dict[str, float] = {}

    # ------------------------------------------------------------------ the one read
    def _url(self, type_: str, league: str | None, extra: Mapping[str, str | int] | None, host: str | None) -> str:
        q = {"TYPE": type_}
        if league:
            q["L"] = league
        q.update({k: str(v) for k, v in (extra or {}).items()})
        q["JSON"] = "1"
        return f"{host or self.base}/{self.year}/export?{urllib.parse.urlencode(q, safe=',')}"

    def _http(self, url: str) -> tuple[str, str]:
        if self._fetch is not None:
            return self._fetch(url)
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        try:
            with _OPENER.open(req, timeout=self.timeout) as r:  # noqa: S310 - fixed https hosts (IM-3: redirects too)
                return r.geturl(), r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                self._backoff_until = self.clock() + 60
                raise MFLBusy("busy, try again in a minute") from exc
            raise MFLUnavailable(f"MyFantasyLeague {url}: HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise MFLUnavailable(f"MyFantasyLeague {url}: {exc}") from exc

    def _read(self, type_: str, league: str | None, extra: Mapping[str, str | int] | None, fixture: str,
              api_host: bool) -> Any:
        if self.fixtures is not None and self._fetch is None:
            f = self.fixtures / fixture
            if not f.exists():
                if league and not (self.fixtures / league).exists():
                    return {"error": "no such league (fixtures)"}
                raise MFLUnavailable(f"no fixture {f}")
            return json.loads(f.read_text())
        host = None if api_host or league is None else self.hosts.get(league)
        final, text = self._http(self._url(type_, league, extra, host))
        if league and not api_host:
            h = urllib.parse.urlparse(final)
            origin = f"{h.scheme}://{h.netloc}"
            if _HOST.match(origin) and not origin.startswith("https://api."):
                self.hosts[league] = origin
        try:
            return json.loads(text or "null")
        except json.JSONDecodeError as exc:
            raise MFLUnavailable(f"MyFantasyLeague {type_}: not JSON") from exc

    def _get(self, type_: str, kind: str, league: str | None = None, extra: Mapping[str, str | int] | None = None,
             fixture: str = "", api_host: bool = False) -> Any:
        key = self._url(type_, league, extra, None)
        now = self.clock()
        with self._lock:
            hit = self._cache.get(key)
        if hit is not None and hit[0] > now:
            return hit[3]
        if now < self._backoff_until or not self.bucket.take():
            if hit is not None:
                self.stale_served += 1
                return hit[3]
            raise MFLBusy("busy, try again in a minute")
        self.calls += 1
        try:
            data = self._read(type_, league, extra, fixture, api_host)
        except MFLUnavailable:
            if hit is not None:
                self.stale_served += 1
                return hit[3]
            raise
        if isinstance(data, dict) and "error" in data:
            msg = (_t(data.get("error")) or "").lower()
            if "too many" in msg or "slow down" in msg or "rate" in msg:
                self._backoff_until = self.clock() + 60
                if hit is not None:
                    self.stale_served += 1
                    return hit[3]
                raise MFLBusy("busy, try again in a minute")
            raise LeagueNotFound(PRIVATE_SENTENCE)
        with self._lock:
            self._cache[key] = (now + TTL_S[kind], now, kind, data)
            prune_cache(self._cache, now)                                     # ---- IM-3 fix: bounded (sleeper_client)
            self._read_at[key] = self.wall()                                                    # ---- IG-3
            if len(self._read_at) > 2 * cache_max():                                 # ---- IM-3 fix: bounded too
                for k in list(self._read_at)[:len(self._read_at) - cache_max()]:
                    del self._read_at[k]
        if kind == "league" and league and isinstance(data, dict):
            base = str((data.get("league") or {}).get("baseURL") or "").rstrip("/")
            if _HOST.match(base) and league not in self.hosts:
                self.hosts[league] = base
        return data

    # ---- IG-3 (Wave I-G): the export's fetch time (the on-demand cache's age): a stale answer served on an MFL failure
    # keeps the time it was read, so the line never claims a fresher roster than the one shown
    def fetched_at(self, type_: str, league_id: str, extra: Mapping[str, str | int] | None = None) -> float | None:
        """When the cached ``TYPE=type_`` export of this league was read from MFL (epoch seconds; None: not read)."""
        with self._lock:
            return self._read_at.get(self._url(type_, check_league(league_id), extra, None))
    # ---- end IG-3

    # ------------------------------------------------------------------ the calls
    def league(self, league_id: str) -> dict:
        lid = check_league(league_id)
        d = self._get("league", "league", lid, fixture=f"{lid}/league.json")
        if not isinstance(d, dict) or not isinstance(d.get("league"), dict):
            raise LeagueNotFound(PRIVATE_SENTENCE)
        return d["league"]

    def rules(self, league_id: str) -> dict:
        lid = check_league(league_id)
        return dict((self._get("rules", "rules", lid, fixture=f"{lid}/rules.json") or {}).get("rules") or {})

    def rosters(self, league_id: str) -> list[dict]:
        lid = check_league(league_id)
        d = self._get("rosters", "rosters", lid, fixture=f"{lid}/rosters.json") or {}
        return _as_list((d.get("rosters") or {}).get("franchise"))

    def schedule(self, league_id: str) -> list[dict]:
        lid = check_league(league_id)
        d = self._get("schedule", "schedule", lid, fixture=f"{lid}/schedule.json") or {}
        return _as_list((d.get("schedule") or {}).get("weeklySchedule"))

    def standings(self, league_id: str) -> list[dict]:
        lid = check_league(league_id)
        d = self._get("leagueStandings", "standings", lid, fixture=f"{lid}/leagueStandings.json") or {}
        return _as_list((d.get("leagueStandings") or {}).get("franchise"))

    def live_scoring(self, league_id: str, week: int) -> dict:
        lid = check_league(league_id)
        d = self._get("liveScoring", "live_scoring", lid, {"W": int(week)}, fixture=f"{lid}/liveScoring_{int(week)}.json")
        return dict((d or {}).get("liveScoring") or {})

    def weekly_results(self, league_id: str, week: int) -> dict:
        lid = check_league(league_id)
        d = self._get("weeklyResults", "weekly_results", lid, {"W": int(week)},
                      fixture=f"{lid}/weeklyResults_{int(week)}.json")
        return dict((d or {}).get("weeklyResults") or {})

    # ---- IL-2 (Wave I-L): MFL's transactions export (``TYPE=transactions&L=&W=&TRANS_TYPE=*``): every completed
    # move of the week MFL names (``W``), or the season to date (no ``week``). Rows as MFL sends them (one dict each:
    # ``timestamp``, ``franchise``, ``type``, ``transaction`` / the trade's ``franchise2`` + ``franchise1_gave_up`` /
    # ``franchise2_gave_up``); ``transaction_moves`` reads them. ``settled``: a past week (cached a day, not 10 minutes).
    # Fixtures: ``<league>/transactions_<w>.json`` (a week) / ``<league>/transactions.json`` (the season).
    def transactions(self, league_id: str, week: int | None = None, *, settled: bool = False) -> list[dict]:
        lid = check_league(league_id)
        extra: dict[str, str | int] = {"TRANS_TYPE": "*"}
        if week:
            extra["W"] = int(week)
        kind = "transactions_past" if settled and week else "transactions"
        try:
            d = self._get("transactions", kind, lid, extra,
                          fixture=f"{lid}/transactions_{int(week)}.json" if week else f"{lid}/transactions.json")
        except MFLUnavailable:
            if self.fixtures is not None and self._fetch is None:     # a fixture league with no moves recorded
                return []
            raise
        return [r for r in _as_list(((d or {}).get("transactions") or {}).get("transaction")) if isinstance(r, dict)]
    # ---- end IL-2

    def players(self, ids: list[str] | None = None) -> list[dict]:
        """MFL's player list (``DETAILS=1``): every player, or the ``ids`` given (fixture: one file holds them all)."""
        extra: dict[str, str | int] = {"DETAILS": 1}
        if ids:
            extra["PLAYERS"] = ",".join(sorted({str(i) for i in ids}))
        d = self._get("players", "players", None, extra, fixture="players.json", api_host=True) or {}
        rows = _as_list((d.get("players") or {}).get("player"))
        if ids:
            want = {str(i) for i in ids}
            rows = [r for r in rows if str(r.get("id")) in want]
        return rows

    def injuries(self, week: int | None = None) -> list[dict]:
        extra = {"W": int(week)} if week else None
        d = self._get("injuries", "injuries", None, extra, fixture=f"injuries_{int(week or 0)}.json", api_host=True) or {}
        return _as_list((d.get("injuries") or {}).get("injury"))

    # ---- I0-C (Wave I-0)
    def league_search(self, text: str) -> list[dict]:
        """MFL's public league search -> this season's leagues whose name has ``text``, best matches first:
        ``[{id, name, year, home_url}]``. Fewer than ``SEARCH_MIN`` characters: ``[]`` without a call. MFL's
        ``homeURL`` (``https//www45…``, no colon) is never passed on: ``home_url`` is rebuilt from the id, on the
        league's own ``www4N`` host when the ``homeURL`` names it (remembered for the league's next calls), else
        ``www``. An ``error`` body or (fixture mode) no file is "no match"; MFL down raises ``MFLUnavailable``."""
        q = search_text(text)
        if len(q) < SEARCH_MIN:
            return []
        try:
            d = self._get("leagueSearch", "search", None, {"SEARCH": q}, fixture=f"leagueSearch_{search_slug(q)}.json",
                          api_host=True)
        except LeagueNotFound:
            return []
        except MFLUnavailable:
            if self.fixtures is not None and self._fetch is None:
                return []
            raise
        lg = d.get("leagues") if isinstance(d, dict) else None
        out: list[dict] = []
        seen: set[str] = set()
        for r in _as_list(lg.get("league")) if isinstance(lg, dict) else []:
            if not isinstance(r, dict):
                continue
            lid, year = str(r.get("id") or "").strip(), str(r.get("year") or "").strip()
            if not _LEAGUE.match(lid) or year != str(self.year) or lid in seen:
                continue
            seen.add(lid)
            name = " ".join(html.unescape(str(r.get("name") or "")).split()) or f"MFL league {lid}"
            m = _HOME.match(str(r.get("homeURL") or "").strip())
            host = "https://www.myfantasyleague.com"
            if m and m.group(3) == lid:
                host = f"https://{m.group(1).lower()}.myfantasyleague.com"
                self.hosts.setdefault(lid, host)
            out.append({"id": lid, "name": name, "year": int(year), "home_url": f"{host}/{self.year}/home/{lid}"})
        return rank_matches(out, q)
    # ---- end I0-C

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
        return {"mode": "fixtures" if self.fixtures is not None else "live", "year": self.year, "calls": self.calls,
                "stale_served": self.stale_served, "hosts": dict(self.hosts),
                "bucket": {"tokens": round(self.bucket.tokens(), 1), "capacity": self.bucket.capacity,
                           "per_minute": self.bucket.per_minute, "refused": self.bucket.refused},
                "cache": kinds}


# ====================================================================================== translation (pure)
FLEX_OK = {"RB", "WR", "TE"}
IDP = {"DT", "DE", "LB", "CB", "S", "DL", "DB", "IDP"}
POS = {"QB": "QB", "RB": "RB", "WR": "WR", "TE": "TE", "PK": "K", "K": "K", "DEF": "DEF", "Def": "DEF", "TMDEF": "DEF"}
# MFL team codes that differ from Sleeper's (a defense's Sleeper id is its team code)
TEAM = {"KCC": "KC", "GBP": "GB", "NEP": "NE", "JAC": "JAX", "LVR": "LV", "SFO": "SF", "TBB": "TB", "NOS": "NO",
        "OAK": "LV", "SDC": "LAC", "STL": "LAR", "WSH": "WAS"}


def _limit(s: Any) -> tuple[int, int]:
    txt = str(s or "0").strip()
    if "-" in txt:
        lo, hi = txt.split("-", 1)
        return int(lo or 0), int(hi or lo or 0)
    return int(txt or 0), int(txt or 0)


def slot_name(name: Any) -> str | None:
    """IC-2 (Wave I-C): an MFL starter position -> the slot name League Lab solves (``lineup.parse_slots`` reads it):
    the league's own word, upper-cased, with MFL's spellings of Sleeper's positions (``PK`` -> ``K``, ``Def`` ->
    ``DEF``); combined slots (``WR+TE``, ``RB+WR+TE``) and team units (``TMQB``, ``TMPK``, ``TMDEF``) kept as they
    are. None for an IDP or unknown position (reported, not solved)."""
    # lazy: the solver module (scipy) only when a league is translated
    from .lineup import slot_eligibility
    raw = str(name or "").strip()
    if not raw:
        return None
    up = raw.upper()
    canon = {"PK": "K", "DEF": "DEF", "D": "DEF"}.get(up, up)
    if "+" in canon:
        canon = "+".join({"PK": "K", "DEF": "DEF"}.get(x.strip(), x.strip()) for x in canon.split("+"))
    return canon if slot_eligibility(canon) is not None else None


def slots(league: Mapping) -> tuple[list[str], dict]:
    """MFL's ``starters`` (``count`` and per-position ``limit`` "1" or "2-4") -> ``roster_positions``: every position
    at its minimum under the league's own name (``slot_name``: ``TMQB``, ``WR+TE``, ``TMPK``; ``PK`` -> ``K``, ``Def``
    -> ``DEF``), the remaining starters as ``FLEX`` (RB/WR/TE) — ``SUPER_FLEX`` when QB has a range —; the bench =
    ``rosterSize`` - starters. IDP positions are left out (said in the note). Returns (slots, note: {idp: [...],
    flex: n, super_flex: n, bench: n, approximated: bool, ranges, units: [...]})."""
    st = league.get("starters") or {}
    rows = _as_list(st.get("position"))
    count = int(st.get("count") or 0)
    idp_n = int(st.get("idp_starters") or 0)
    fixed: list[str] = []
    ranged: dict[str, tuple[int, int]] = {}
    idp: list[str] = []
    for r in rows:
        name = str(r.get("name") or "")
        lo, hi = _limit(r.get("limit"))
        pos = None if name in IDP else slot_name(name)          # IC-2: the league's own slot names
        if pos is None:
            idp.append(name)
            continue
        fixed += [pos] * lo
        if hi > lo:
            ranged[pos] = (lo, hi)
    offense = (count - idp_n) if count else len(fixed)
    if idp and not idp_n:          # an IDP league that does not say how many: the IDP minimums are the IDP starters
        offense = count - sum(_limit(r.get("limit"))[0] for r in rows if str(r.get("name")) in idp)
    extra = max(0, offense - len(fixed))
    sf = 0
    if "QB" in ranged and extra > 0:
        sf = min(extra, ranged["QB"][1] - ranged["QB"][0])
    flex = extra - sf
    # QB-like slots first, then RB / WR / TE and the combined slots, K, DEF last (Sleeper's order; MFL's own order
    # inside a group)
    order = {"QB": 0, "TMQB": 0, "RB": 1, "WR": 2, "TE": 3, "K": 5, "TMPK": 5, "DEF": 6, "TMDEF": 6}
    tail = ("K", "TMPK", "DEF", "TMDEF")
    out = sorted(fixed, key=lambda p: order.get(p, 4))
    out = [p for p in out if p not in tail] + ["FLEX"] * flex + ["SUPER_FLEX"] * sf + [p for p in out if p in tail]
    roster_size = int(league.get("rosterSize") or 0)
    bench = max(0, roster_size - count) if roster_size else 0
    note = {"idp": idp, "flex": flex, "super_flex": sf, "bench": bench,
            "approximated": bool(ranged), "ranges": {k: f"{a}-{b}" for k, (a, b) in ranged.items()},
            "units": sorted({p for p in fixed if p.startswith("TM")})}
    note["range_gaps"] = range_gaps(ranged, flex, sf)                     # ---- IL-2
    return out + ["BN"] * bench, note


# ---- IL-2 (Wave I-L): where "the minimum + FLEX" reading of MFL's starter ranges differs from MFL's own rule (each
# position within its range, the starters adding up to the count). The count already caps a FLEX position at its
# minimum + the FLEX spots, so the two differ only when (a) a range is narrower than the FLEX spots (we would start more
# of that position than MFL's maximum) or (b) a position the FLEX does not admit has a range (a kicker, a defense, a
# team unit, or a quarterback beyond the superflex spots: MFL lets its extra spots take it, ours do not).
def range_gaps(ranged: Mapping[str, tuple[int, int]], flex: int, super_flex: int) -> list[str]:
    out = []
    for p, (lo, hi) in sorted(ranged.items()):
        if p in FLEX_OK:
            if lo + flex > hi:
                out.append(f"{p}: we allow up to {lo + flex} in the lineup (the {flex} FLEX spot{'s' if flex != 1 else ''}), "
                           f"MyFantasyLeague at most {hi}")
        elif p == "QB":
            if lo + super_flex < hi:
                out.append(f"QB: MyFantasyLeague allows up to {hi}, we start at most {lo + super_flex}")
        else:
            out.append(f"{p}: MyFantasyLeague allows up to {hi}, we start {lo} (the FLEX does not take a {p})")
    return out
# ---- end IL-2


# --- scoring ---------------------------------------------------------------------------------------------------
# MFL event -> Sleeper key (per-unit "*x" rules), for the offense / kicker groups and the defense group
OFFENSE = {"#P": "pass_td", "PY": "pass_yd", "IN": "pass_int", "P2": "pass_2pt", "#R": "rush_td", "RY": "rush_yd",
           "R2": "rush_2pt", "#C": "rec_td", "CY": "rec_yd", "C2": "rec_2pt", "CC": "rec", "EP": "xpm", "EM": "xpmiss",
           "FL": "fum_lost", "FU": "fum", "#FR": "fum_rec_td", "MG": "fgmiss"}
DEFENSE = {"FC": "ff", "IC": "int", "SK": "sack", "SF": "safe", "#T": "def_td", "#FR": "def_td", "#IR": "def_td",
           "BLK": "blk_kick", "FR": "fum_rec", "#ST": "st_td", "#UT": "st_td", "#KT": "st_td"}
YARD_BONUS = {("pass_yd", 300): "bonus_pass_yd_300", ("pass_yd", 400): "bonus_pass_yd_400",
              ("rush_yd", 100): "bonus_rush_yd_100", ("rush_yd", 200): "bonus_rush_yd_200",
              ("rec_yd", 100): "bonus_rec_yd_100", ("rec_yd", 200): "bonus_rec_yd_200"}
# touchdowns scored by length (flat points per band): the short band is the TD, a long band a "_40p" bonus
TD_BY_LENGTH = {"PS": "pass_td", "RS": "rush_td", "RC": "rec_td"}
# MFL events with names, for the "unpriced" list
EVENT_NAMES = {"PY": "passing yards", "RY": "rushing yards", "CY": "receiving yards", "PS": "passing TD by length", "RS": "rushing TD by length", "RC": "receiving TD by length",
               "#UT": "punt return TD", "#KT": "kickoff return TD", "UY": "punt return yards", "KY": "kickoff return yards",
               "DR": "defensive return TD", "IR": "interception return TD", "BF": "blocked FG return TD",
               "BP": "blocked punt return TD", "BLF": "blocked field goal", "BLP": "blocked punt", "BLE": "blocked extra point",
               "TK": "tackles", "AS": "assisted tackles", "PD": "passes defended", "FF": "forced fumbles (player)",
               "TPA": "points allowed", "FC": "fumbles recovered (player)", "IC": "interceptions (player)",
               "SF": "safeties (player)", "SK": "sacks (player)", "YA": "yards allowed", "#T": "touchdowns (returns)", "TYA": "total yards allowed"}
FG_BANDS = [("fgm_0_19", 0, 19, 17.0), ("fgm_20_29", 20, 29, 24.5), ("fgm_30_39", 30, 39, 34.5),
            ("fgm_40_49", 40, 49, 44.5), ("fgm_50p", 50, 99, 55.0)]
PA_BANDS = [("pts_allow_0", 0, 0), ("pts_allow_1_6", 1, 6), ("pts_allow_7_13", 7, 13), ("pts_allow_14_20", 14, 20),
            ("pts_allow_21_27", 21, 27), ("pts_allow_28_34", 28, 34), ("pts_allow_35p", 35, 45)]


def _range(s: str | None) -> tuple[float, float]:
    m = re.match(r"^\s*(-?\d+(?:\.\d+)?)\s*-\s*(-?\d+(?:\.\d+)?)\s*$", s or "")
    if not m:
        v = float(s) if s and re.match(r"^-?\d+(\.\d+)?$", s.strip()) else 0.0
        return v, v
    return float(m.group(1)), float(m.group(2))


def _points(p: str | None) -> tuple[str, float, float]:
    """MFL's points string -> (kind, a, b): "*0.05" per unit (per, 0.05, 1); "6" flat (flat, 6, 0); "1/25" one point
    per 25 units (per, 1/25, 25); "2.5/.5" (per, 2.5/0.5 ... per half a unit)."""
    s = (p or "0").strip()
    if s.startswith("*"):
        return "per", float(s[1:] or 0), 1.0
    if "/" in s:
        a, b = s.split("/", 1)
        a_f, b_f = float(a or 0), float(b or 1)
        return "per", (a_f / b_f if b_f else 0.0), b_f
    return "flat", float(s or 0), 0.0


def _groups(rules: Mapping) -> list[tuple[set[str], list[dict]]]:
    out = []
    for g in _as_list(rules.get("positionRules")):
        pos = set(str(g.get("positions") or "").split("|")) - {""}
        rs = []
        for r in _as_list(g.get("rule")):
            rs.append({"event": _t(r.get("event")) or "", "range": _t(r.get("range")),
                       "points": _t(r.get("points")), "threshold": _t(r.get("thresholdPoints"))})
        out.append((pos, rs))
    return out


def scoring(rules: Mapping) -> tuple[dict[str, float], dict]:
    """MFL ``rules`` -> (Sleeper ``scoring_settings``, report). The report: ``approximated`` (sentences: FG distance
    bands from MFL's per-yard rule at the band midpoints; points-allowed bands mapped onto Sleeper's by the average
    over each Sleeper band's points), ``unpriced`` (MFL events with no Sleeper key, by name, and IDP-only groups),
    ``idp_groups``."""
    sc: dict[str, float] = {}
    approx: list[str] = []
    unpriced: dict[str, str] = {}
    idp_groups: list[str] = []
    groups = _groups(rules)
    def put(key: str, val: float) -> None:
        sc[key] = round(sc.get(key, 0.0) + val, 6) if key in sc and key in ("def_td", "st_td") else round(val, 6)

    rec_by_pos: dict[str, float] = {}
    for pos, rs in groups:
        if pos and pos <= (IDP | {"Def", "DEF", "TMDEF"}) and not (pos & {"Def", "DEF", "TMDEF"}):
            idp_groups.append("|".join(sorted(pos)))
            continue
        is_def = bool(pos & {"Def", "DEF", "TMDEF"})
        by_event: dict[str, list[dict]] = {}
        for r in rs:
            by_event.setdefault(r["event"], []).append(r)
        for ev, items in by_event.items():
            if is_def:
                if ev == "TPA":
                    bands = []
                    for r in items:
                        lo, hi = _range(r["range"])
                        kind, a, _ = _points(r["points"])
                        bands.append((lo, hi, a if kind == "flat" else 0.0))
                    for key, lo, hi in PA_BANDS:
                        vals = []
                        for pts in range(lo, hi + 1):
                            v = next((b[2] for b in bands if b[0] <= pts <= b[1]), 0.0)
                            vals.append(v)
                        sc[key] = round(sum(vals) / len(vals), 3)
                    mfl_b = sorted((int(b[0]), int(b[1])) for b in bands)
                    if [(lo, hi) for _, lo, hi in PA_BANDS[:len(mfl_b)]] != mfl_b:
                        approx.append("points allowed: MyFantasyLeague's bands " +
                                      ", ".join(f"{a}-{b}" for a, b in mfl_b) +
                                      " are mapped onto Sleeper's (0, 1-6, 7-13, 14-20, 21-27, 28-34, 35+) by the "
                                      "average over each band")
                    continue
                key = DEFENSE.get(ev)
                kind, a, _ = _points(items[0]["points"])
                if key is None or kind != "per" or len(items) > 1:
                    unpriced[ev] = EVENT_NAMES.get(ev, ev) + " (defense)"
                    continue
                if ev == "#T":
                    sc["def_td"] = a
                    sc["st_td"] = a
                    sc["def_st_td"] = a
                else:
                    put(key, a)
                continue
            # offense / kicker group
            if ev == "FG":
                fg = []
                for r in items:
                    lo, hi = _range(r["range"])
                    kind, a, _ = _points(r["points"])
                    base = float(r["threshold"]) if r["threshold"] else 0.0
                    fg.append((lo, hi, kind, a, base))
                per_yard = False
                for key, _lo, _hi, mid in FG_BANDS:
                    r = next((x for x in fg if x[0] <= mid <= x[1]), None)
                    if r is None:
                        continue
                    if r[2] == "flat":
                        sc[key] = round(r[3], 3)
                    else:
                        per_yard = True
                        sc[key] = round(r[4] + r[3] * max(0.0, mid - r[0]), 3) if r[4] else round(r[3] * mid, 3)
                if per_yard:
                    approx.append("field goals: MyFantasyLeague scores some by the yard; each Sleeper distance band "
                                  "is priced at its middle (17, 24.5, 34.5, 44.5 and 55 yards)")
                continue
            if ev == "MG":
                kind, a, _ = _points(items[0]["points"])
                sc["fgmiss"] = a
                if len(items) > 1:
                    approx.append("missed field goals: priced at MyFantasyLeague's first distance band")
                continue
            if ev == "CC":
                kind, a, _ = _points(items[0]["points"])
                if kind == "per" and len(items) == 1:
                    for p in pos & {"QB", "RB", "WR", "TE"}:
                        rec_by_pos[p] = a
                else:
                    unpriced["CC"] = "receptions in bands"
                continue
            if ev in TD_BY_LENGTH:
                key = TD_BY_LENGTH[ev]
                bands = sorted((_range(r["range"]) + (_points(r["points"]),) for r in items), key=lambda b: b[0])
                if all(b[2][0] == "flat" for b in bands):
                    base = bands[0][2][1]
                    sc[key] = base
                    long_ = [b for b in bands if b[0] >= 30]
                    if long_ and round(long_[0][2][1] - base, 6) != 0:
                        sc[f"{key}_40p"] = round(long_[0][2][1] - base, 6)
                        if int(long_[0][0]) != 40:
                            approx.append(f"{EVENT_NAMES[ev]}: MyFantasyLeague's long-touchdown band starts at "
                                          f"{int(long_[0][0])} yards; priced as Sleeper's 40+ bonus")
                    continue
                unpriced[ev] = EVENT_NAMES.get(ev, ev)
                continue
            key = OFFENSE.get(ev)
            if key is None:
                unpriced[ev] = EVENT_NAMES.get(ev, ev)
                continue
            per = [x for x in items if _points(x["points"])[0] == "per" and not x["threshold"]]
            if len(items) == 1 and per:
                sc[key] = _points(items[0]["points"])[1]
            elif per or all(x["threshold"] for x in items):
                # yardage in bands: the first band's per-unit rule is the rate; a higher band's thresholdPoints
                # (the points at its first yard) less the rate's points there is a yardage bonus, which Sleeper keys
                # by band (bonus_pass_yd_300 / _400, bonus_rush_yd_100 / _200, bonus_rec_yd_100 / _200)
                first = sorted(items, key=lambda x: _range(x["range"])[0])
                rate = _points(first[0]["points"])[1]
                sc[key] = rate
                missed = []
                for x in first[1:]:
                    lo = _range(x["range"])[0]
                    if not x["threshold"]:
                        missed.append(int(lo))
                        continue
                    bonus = round(float(x["threshold"]) - rate * lo, 6)
                    bkey = YARD_BONUS.get((key, int(lo)))
                    if bkey is None:
                        missed.append(int(lo))
                    elif bonus:
                        sc[bkey] = bonus
                if missed:
                    approx.append(f"{EVENT_NAMES.get(ev, key)}: MyFantasyLeague's yardage bands from "
                                  + ", ".join(str(m) for m in missed) + " yards have no Sleeper bonus; the band "
                                  "below them is extended")
            else:
                unpriced[ev] = EVENT_NAMES.get(ev, ev) + " (in bands)"
    # receptions: the wide receivers' rate (else the running backs', else the lowest) is "rec"; a position's
    # different rate is a premium on top of it (bonus_rec_te: TE premium)
    if rec_by_pos:
        rec_all = rec_by_pos.get("WR", rec_by_pos.get("RB", min(rec_by_pos.values())))
        sc["rec"] = rec_all
        for p, key in (("TE", "bonus_rec_te"), ("RB", "bonus_rec_rb"), ("WR", "bonus_rec_wr")):
            if p in rec_by_pos and round(rec_by_pos[p] - rec_all, 6) != 0:
                sc[key] = round(rec_by_pos[p] - rec_all, 6)
    if idp_groups:
        unpriced["IDP"] = "individual defensive players (" + ", ".join(idp_groups) + ")"
    # ---- IC-1 (Wave I-C): the rules as a ScoringSpec (scoring.from_mfl) — the truth every pricing path reads
    # (``anyleague.league_scoring``); the flat dict above stays for the old readers, filled from the spec where the
    # I0-B translation found no Sleeper key (70587's TDs by distance and "1/10" yards came back empty).
    from .scoring import flat_from_spec, from_mfl
    spec = from_mfl(rules)
    for k, v in flat_from_spec(spec).items():
        if not sc.get(k):
            sc[k] = v
    return sc, {"approximated": approx, "unpriced": sorted(unpriced.values()), "unpriced_events": sorted(unpriced),
                "idp_groups": idp_groups, "spec": spec.to_json(),
                "spec_unpriced": [f"{u['name']} ({u['event']})" for u in spec.unpriced],
                "spec_approximated": list(spec.approximated)}
    # ---- /IC-1


# --- franchises, rosters, starters, schedule ------------------------------------------------------------------
def franchise_ids(league: Mapping) -> list[str]:
    return [str(f.get("id")) for f in _as_list((league.get("franchises") or {}).get("franchise"))]


def franchise_names(league: Mapping, standings: list[dict] | None = None) -> dict[str, str]:
    out = {}
    for f in _as_list((league.get("franchises") or {}).get("franchise")):
        out[str(f.get("id"))] = html.unescape(str(f.get("name") or "")).strip() or f"Team {f.get('id')}"
    for s in standings or []:
        fid = str(s.get("id"))
        if fid in out and not out[fid] and s.get("fname"):
            out[fid] = html.unescape(str(s["fname"])).strip()
    return out


# ---- IC-4 (Wave I-D): manager names. MFL's ``league`` export carries a franchise's ``owner_name`` only when the league
# shows it to the caller (a commissioner's or an owner's signed-in request, or a league that publishes it); the public
# export League Lab reads has none for 70587, 21861 or 10015 (checked live 2026-10-03). None = not shared.
def franchise_owners(league: Mapping) -> dict[str, str]:
    """franchise id -> its owner's name where the export carries one (``owner_name``)."""
    out = {}
    for f in _as_list((league.get("franchises") or {}).get("franchise")):
        n = html.unescape(str(f.get("owner_name") or "")).strip()
        if n:
            out[str(f.get("id"))] = n
    return out
# ---- end IC-4


def starters_by_franchise(live: Mapping | None, results: Mapping | None) -> dict[str, list[str]]:
    """franchise id -> its starters' MFL ids: the week's live scoring (``status == "starter"``) when it lists them,
    else a weekly result's ``starters`` string."""
    out: dict[str, list[str]] = {}
    for m in _as_list((live or {}).get("matchup")):
        for f in _as_list(m.get("franchise")):
            ids = [str(p.get("id")) for p in _as_list((f.get("players") or {}).get("player"))
                   if str(p.get("status") or "").lower() == "starter"]
            if ids:
                out[str(f.get("id"))] = ids
    for f in _as_list((live or {}).get("franchise")):          # a league without head-to-head
        ids = [str(p.get("id")) for p in _as_list((f.get("players") or {}).get("player"))
               if str(p.get("status") or "").lower() == "starter"]
        if ids:
            out.setdefault(str(f.get("id")), ids)
    for m in _as_list((results or {}).get("matchup")) + [{"franchise": (results or {}).get("franchise")}]:
        for f in _as_list(m.get("franchise")):
            fid = str(f.get("id"))
            ids = [x for x in str(f.get("starters") or "").split(",") if x]
            if ids and fid not in out:
                out[fid] = ids
    return out


def weekly_matchups(schedule: list[dict], week: int, rid_of: Mapping[str, int]) -> list[dict]:
    """One week of MFL's schedule -> Sleeper's ``/matchups/<week>`` rows (roster_id, matchup_id, points; 0 before
    the games, as Sleeper)."""
    w = next((x for x in schedule if str(x.get("week")) == str(int(week))), None)
    out = []
    for i, m in enumerate(_as_list((w or {}).get("matchup")), 1):
        for f in _as_list(m.get("franchise")):
            rid = rid_of.get(str(f.get("id")))
            if rid is None:
                continue
            try:
                pts = float(f.get("score")) if f.get("score") not in (None, "") else 0.0
            except (TypeError, ValueError):
                pts = 0.0
            out.append({"roster_id": rid, "matchup_id": i, "points": pts, "starters": [], "players": []})
    return out


def standings_settings(standings: list[dict]) -> dict[str, dict]:
    out = {}
    for s in standings:
        pf = float(s.get("pf") or 0)
        out[str(s.get("id"))] = {"wins": int(float(s.get("h2hw") or 0)), "losses": int(float(s.get("h2hl") or 0)),
                                 "ties": int(float(s.get("h2ht") or 0)), "fpts": int(math.floor(pf)),
                                 "fpts_decimal": int(round((pf - math.floor(pf)) * 100))}
    return out


# ---- IL-2 (Wave I-L): one MFL transaction row -> the moves it made. MFL's documented shapes (the export's
# ``transaction`` attribute; ffscrapr's ``mfl_transactions`` reads them the same way): FREE_AGENT and WAIVER
# ``"<added ids>,|<dropped ids>,"``; BBID_WAIVER ``"<added>,|<bid>|<dropped>,"``; TRADE ``franchise`` gave
# ``franchise1_gave_up`` to ``franchise2``, which gave ``franchise2_gave_up`` (draft picks ``FP_<franchise>_<year>_<round>``
# among them). Other types (IR, TAXI, AUCTION_*, the *_REQUEST pending ones, pool picks) move nobody between teams: None.
TRANSACTION_KIND = {"FREE_AGENT": "free_agent", "WAIVER": "waiver", "BBID_WAIVER": "waiver", "TRADE": "trade"}
_PICK = re.compile(r"^FP_(\d{4})_(\d{4})_(\d{1,2})$")


def _ids(s: Any) -> list[str]:
    return [x.strip() for x in str(s or "").split(",") if x.strip() and not x.strip().startswith(("FP_", "DP_"))]


def _picks(s: Any) -> list[tuple[str, int, int]]:
    """``FP_0005_2027_1`` -> (original franchise, season, round); current-draft ``DP_`` picks are not read."""
    out = []
    for x in str(s or "").split(","):
        m = _PICK.match(x.strip())
        if m:
            out.append((m.group(1), int(m.group(2)), int(m.group(3))))
    return out


def transaction_moves(row: Mapping) -> dict | None:
    """``{kind, franchise, adds: {mfl id: franchise}, drops: {mfl id: franchise}, bid, picks: [(from, to, original,
    season, round)], timestamp}`` or None for a type that moves nobody between teams (or a row it cannot read)."""
    typ = str(row.get("type") or "").strip().upper()
    kind = TRANSACTION_KIND.get(typ)
    fid = str(row.get("franchise") or "").strip()
    try:
        ts = int(float(row.get("timestamp")))
    except (TypeError, ValueError):
        ts = None
    if kind is None or not fid:
        return None
    adds: dict[str, str] = {}
    drops: dict[str, str] = {}
    bid: float | None = None
    picks: list[tuple] = []
    if kind == "trade":
        other = str(row.get("franchise2") or "").strip()
        if not other:
            return None
        for giver, taker, gave in ((fid, other, row.get("franchise1_gave_up")), (other, fid, row.get("franchise2_gave_up"))):
            for i in _ids(gave):
                drops[i], adds[i] = giver, taker
            picks += [(giver, taker, o, y, r) for o, y, r in _picks(gave)]
    else:
        parts = str(row.get("transaction") or "").split("|")
        added, dropped = parts[0], parts[-1] if len(parts) > 1 else ""
        if typ == "BBID_WAIVER" and len(parts) >= 3:
            try:
                bid = float(parts[1])
            except ValueError:
                bid = None
        adds = {i: fid for i in _ids(added)}
        drops = {i: fid for i in _ids(dropped)}
    if not adds and not drops and not picks:
        return None
    return {"kind": kind, "type": typ, "franchise": fid, "adds": adds, "drops": drops, "bid": bid, "picks": picks,
            "timestamp": ts}


def _num(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def live_players(live: Mapping | None) -> dict[str, dict]:
    """MFL's ``liveScoring`` -> {mfl id: {score, seconds_left, status, franchise}} for every player it lists (a double
    header lists a franchise twice: one row per player). ``seconds_left`` = MFL's ``gameSecondsRemaining`` (3600 before
    kickoff, 0 when his game is over — or when he has no game this week)."""
    out: dict[str, dict] = {}
    frs = [f for m in _as_list((live or {}).get("matchup")) for f in _as_list(m.get("franchise"))]
    frs += _as_list((live or {}).get("franchise"))                     # a league without head-to-head
    for f in frs:
        for p in _as_list((f.get("players") or {}).get("player")):
            pid = str(p.get("id") or "")
            if pid:
                out[pid] = {"score": _num(p.get("score")), "seconds_left": _num(p.get("gameSecondsRemaining")),
                            "status": str(p.get("status") or "").lower() or None, "franchise": str(f.get("id"))}
    return out


def live_franchises(live: Mapping | None) -> dict[str, dict]:
    """MFL's ``liveScoring`` -> {franchise id: {score, seconds_left, yet_to_play, playing}} (the franchise's own totals)."""
    out: dict[str, dict] = {}
    frs = [f for m in _as_list((live or {}).get("matchup")) for f in _as_list(m.get("franchise"))]
    frs += _as_list((live or {}).get("franchise"))
    for f in frs:
        out[str(f.get("id"))] = {"score": _num(f.get("score")), "seconds_left": _num(f.get("gameSecondsRemaining")),
                                 "yet_to_play": _num(f.get("playersYetToPlay")),
                                 "playing": _num(f.get("playersCurrentlyPlaying"))}
    return out
# ---- end IL-2


def defense_sleeper_id(team: str | None) -> str | None:
    if not team:
        return None
    t = str(team).upper()
    return TEAM.get(t, t)
