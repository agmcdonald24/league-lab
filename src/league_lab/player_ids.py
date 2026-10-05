"""The player-id table (Wave I-0, I0-B): one row per player with his MyFantasyLeague, ESPN, Yahoo, Sleeper and gsis ids.

Source: nflverse / dynastyprocess ``db_playerids.csv`` (about 12,500 rows; ``mfl_id``, ``gsis_id``, ``sleeper_id``,
``espn_id``, ``name``, ``position``, ``team`` and more), published on GitHub raw (``CSV_URL``).

* **Where it is read from**: ``LEAGUE_LAB_PLAYER_IDS_CSV=<file>`` when set (tests: ``api/tests/fixtures/ff/``; never
  downloaded over), else ``LEAGUE_LAB_CACHE_DIR/db_playerids.csv`` (``sleeper_client.cache_dir()``).
* **Download**: ``download_if_stale()`` fetches the CSV at most once a day (the file's age on disk); a failed
  download keeps the last copy (and answers with it) when there is one. ``table()`` calls it on first use and when
  the copy it holds is a day old, so a long-running server picks up the next day's file without a restart.
* **Lookups** (strings in, string or None out; "NA" and blanks are None): ``mfl_to_sleeper``, ``mfl_to_gsis``,
  ``espn_to_gsis``, ``sleeper_to_gsis``; ``row_by_mfl`` for the name / position / team; (IK-2, Wave I-K) ``yahoo_to_sleeper``,
  ``yahoo_to_gsis``, ``row_by_yahoo`` — nflverse's ``yahoo_id`` is the number in Yahoo's player key ``461.p.30121``.

Identity never goes through a name here (AGENTS.md rule 3): the table is keyed by ids only.
"""

from __future__ import annotations

import csv
import os
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .sleeper_client import cache_dir

CSV_URL = "https://raw.githubusercontent.com/dynastyprocess/data/master/files/db_playerids.csv"
CSV_ENV = "LEAGUE_LAB_PLAYER_IDS_CSV"
FILE = "db_playerids.csv"
MAX_AGE_S = 24 * 3600
COLUMNS = ("mfl_id", "gsis_id", "sleeper_id", "espn_id", "name", "position", "team",
           "yahoo_id")                                     # ---- IK-2 (Wave I-K): Yahoo player ids
_NA = {"", "NA", "None", "none", "nan", "NaN", "NULL", "null"}


def _clean(v: str | None) -> str | None:
    s = (v or "").strip()
    if s in _NA:
        return None
    if s.endswith(".0") and s[:-2].isdigit():      # a numeric id written as a float by an upstream tool
        s = s[:-2]
    return s


@dataclass
class IdTable:
    """The table in memory: one dict per lookup direction (ids as strings)."""
    path: Path | None = None
    loaded_at: float = 0.0
    mtime: float = 0.0
    rows: int = 0
    by_mfl: dict[str, dict] = field(default_factory=dict)
    sleeper_gsis: dict[str, str] = field(default_factory=dict)
    espn_gsis: dict[str, str] = field(default_factory=dict)
    by_yahoo: dict[str, dict] = field(default_factory=dict)          # ---- IK-2: yahoo_id -> the row
    yahoo_dupes: set[str] = field(default_factory=set)               # ---- IK-2: ids on two players (no match)

    def mfl_to_sleeper(self, mfl_id: str | int | None) -> str | None:
        r = self.by_mfl.get(_clean(str(mfl_id)) or "")
        return r.get("sleeper_id") if r else None

    def mfl_to_gsis(self, mfl_id: str | int | None) -> str | None:
        r = self.by_mfl.get(_clean(str(mfl_id)) or "")
        return r.get("gsis_id") if r else None

    def espn_to_gsis(self, espn_id: str | int | None) -> str | None:
        return self.espn_gsis.get(_clean(str(espn_id)) or "")

    def sleeper_to_gsis(self, sleeper_id: str | int | None) -> str | None:
        return self.sleeper_gsis.get(_clean(str(sleeper_id)) or "")

    def row_by_mfl(self, mfl_id: str | int | None) -> dict | None:
        return self.by_mfl.get(_clean(str(mfl_id)) or "")

    # ---- IK-2 (Wave I-K): Yahoo's player id (the number in ``461.p.30121``) -> Sleeper / gsis
    def yahoo_to_sleeper(self, yahoo_id: str | int | None) -> str | None:
        r = self.by_yahoo.get(_clean(str(yahoo_id)) or "")
        return r.get("sleeper_id") if r else None

    def yahoo_to_gsis(self, yahoo_id: str | int | None) -> str | None:
        r = self.by_yahoo.get(_clean(str(yahoo_id)) or "")
        return r.get("gsis_id") if r else None

    def row_by_yahoo(self, yahoo_id: str | int | None) -> dict | None:
        return self.by_yahoo.get(_clean(str(yahoo_id)) or "")
    # ---- end IK-2


def read(path: str | Path) -> IdTable:
    """Parse the CSV (only ``COLUMNS`` are kept). A missing column is tolerated (its lookups answer None)."""
    p = Path(path)
    t = IdTable(path=p, loaded_at=time.time(), mtime=p.stat().st_mtime)
    with p.open(newline="", encoding="utf-8") as fh:
        for raw in csv.DictReader(fh):
            r = {c: _clean(raw.get(c)) for c in COLUMNS}
            t.rows += 1
            if r["mfl_id"]:
                t.by_mfl[r["mfl_id"]] = r
            if r["sleeper_id"] and r["gsis_id"]:
                t.sleeper_gsis[r["sleeper_id"]] = r["gsis_id"]
            if r["espn_id"] and r["gsis_id"]:
                t.espn_gsis[r["espn_id"]] = r["gsis_id"]
            if r["yahoo_id"]:                       # ---- IK-2: a yahoo_id on two players' rows is quarantined
                prev = t.by_yahoo.get(r["yahoo_id"])
                if r["yahoo_id"] in t.yahoo_dupes or (prev is not None and prev.get("gsis_id") != r["gsis_id"]):
                    t.yahoo_dupes.add(r["yahoo_id"])
                    t.by_yahoo.pop(r["yahoo_id"], None)
                elif prev is None:
                    t.by_yahoo[r["yahoo_id"]] = r
    return t


def path() -> Path:
    env = os.environ.get(CSV_ENV)
    return Path(env) if env else cache_dir() / FILE


def _download(url: str, timeout: float) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "league-lab/api (player id table, once a day)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - fixed https host
        return r.read()


def download_if_stale(*, max_age_s: float = MAX_AGE_S, fetch: Callable[[str, float], bytes] | None = None,
                      wall: Callable[[], float] = time.time, timeout: float = 20.0) -> Path | None:
    """The local copy's path, downloading it first when it is missing or ``max_age_s`` old. With
    ``LEAGUE_LAB_PLAYER_IDS_CSV`` set, that file is the table (never downloaded over). A failed download keeps the
    last copy (None when there is none)."""
    if os.environ.get(CSV_ENV):
        p = Path(os.environ[CSV_ENV])
        return p if p.exists() else None
    f = cache_dir() / FILE
    if f.exists() and wall() - f.stat().st_mtime < max_age_s:
        return f
    try:
        body = (fetch or _download)(CSV_URL, timeout)
        if not body or b"mfl_id" not in body[:2000]:
            raise ValueError("not the id table")
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp")
        tmp.write_bytes(body)
        tmp.replace(f)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        pass                                            # keep the last copy
    return f if f.exists() else None


_lock = threading.Lock()
_table: IdTable | None = None


def table(*, refresh: bool = False) -> IdTable:
    """The process-wide table: loaded on first use, reloaded when the file changed (a new day's download, another
    ``LEAGUE_LAB_PLAYER_IDS_CSV``). No file at all: an empty table (every lookup None; the callers count the misses)."""
    global _table
    with _lock:
        held = _table
        stale = held is None or refresh or held.path != path() or time.time() - held.loaded_at >= MAX_AGE_S
        if not stale and held is not None and held.path is not None and held.path.exists() \
                and held.path.stat().st_mtime == held.mtime:
            return held
        p = download_if_stale()
        if p is None:
            _table = IdTable()
            return _table
        if held is not None and held.path == p and p.stat().st_mtime == held.mtime:
            held.loaded_at = time.time()
            return held
        _table = read(p)
        return _table


def reset() -> None:
    """Forget the table (tests)."""
    global _table
    with _lock:
        _table = None


def mfl_to_sleeper(mfl_id: str | int | None) -> str | None:
    return table().mfl_to_sleeper(mfl_id)


def mfl_to_gsis(mfl_id: str | int | None) -> str | None:
    return table().mfl_to_gsis(mfl_id)


def espn_to_gsis(espn_id: str | int | None) -> str | None:
    return table().espn_to_gsis(espn_id)


def sleeper_to_gsis(sleeper_id: str | int | None) -> str | None:
    return table().sleeper_to_gsis(sleeper_id)


# ---- IK-2 (Wave I-K)
def yahoo_to_sleeper(yahoo_id: str | int | None) -> str | None:
    return table().yahoo_to_sleeper(yahoo_id)


def yahoo_to_gsis(yahoo_id: str | int | None) -> str | None:
    return table().yahoo_to_gsis(yahoo_id)
# ---- end IK-2
