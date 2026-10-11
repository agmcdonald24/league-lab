"""IZ-1 (Wave I-Z): Sleeper's projections for past weeks -> ``ops.sleeper_history`` (docs/METRICS.md § hh1.0).

Why: the record (``mart_projection_record``, plan E1) starts at 2026 week 5, the first week we saved Sleeper's line
before kickoff. Sleeper's endpoint still answers for past weeks, so the head-to-head can run on about sixty weeks
instead of one — **but what it serves for a past week is a batch written after the week** (every object of a week
carries one ``updated_at`` / ``last_modified``, minutes after the week's last game; 2023's carry none). So these rows
are kept apart from the record, marked ``served = 'after_week'`` with the payload's ``updated_at``:

* never in ``raw.sleeper_projections`` (the record's source and its pre-kickoff rule), and never in the snapshot
  folder the nightly replays into it: the archive is ``data/raw/sleeper/projections_history/<season>/<week>_<stamp>.json.gz``;
* only the players with a projected line are kept (Sleeper's own total, or at least one priced stat: the record's
  rule); the rest of the ~3,300 objects (a player without a line: ``stats`` holds only ``adp_dd_ppr``) are counted.

Which weeks (``wanted_weeks``): ``HISTORY_SEASONS`` weeks 1–18, and each week of the current season whose last game
is over and that has no snapshot fetched before its first kickoff (2026: weeks 1–4).

Done once (``ops.sleeper_history_weeks``, one row a week: ``status`` 'ok' | 'failed', the counts, the attempts): a
week held 'ok' is never asked again; a failed, empty or malformed answer is 'failed' and the next night asks again.
The nightly's database is fresh every night: both tables are state (restored from the hosted copy), and when they
come back empty the archive is replayed first (``--offline`` part of every run), so a lost hosted copy costs no call.
One request a week, at least ``PAUSE_S`` apart, through the ingest's client; ``MAX_FAILS_IN_A_ROW`` failures in a row
stop the night's pulling (the rest is asked the next night). A failed pull never fails the night (exit 0; the summary
says how many weeks are held of how many).
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

import httpx
import psycopg
from psycopg.types.json import Jsonb

from ..http import FetchError, _meta_path, fetch_to_archive, read_archive
from . import sleeper_projections as sp

log = logging.getLogger(__name__)

HISTORY_SEASONS = (2023, 2024, 2025)
WEEKS = tuple(range(1, 19))
SERVED = "after_week"
PAUSE_S = 1.0                     # at least a second between two requests
MAX_FAILS_IN_A_ROW = 3            # then stop for tonight: the rest is asked the next night
GAME_OVER_AFTER = timedelta(hours=5)   # a week's last game is over this long after its kickoff
TABLE = "ops.sleeper_history"
WEEKS_TABLE = "ops.sleeper_history_weeks"
ARCHIVE = ("sleeper", "projections_history")

COLUMNS: list[tuple[str, str]] = [
    ("season", "integer"), ("week", "integer"), ("player_id", "text"), ("position", "text"), ("team", "text"),
    ("opponent", "text"), ("company", "text"),
    ("updated_at", "timestamptz"),       # the payload's updated_at / last_modified (one instant a week; 2023: none)
    ("fetched_at", "timestamptz"),       # when we asked (after the week)
    ("served", "text"),                  # 'after_week': never a pre-kickoff number
    *[(k, "double precision") for k in sp.POINTS_KEYS],
    *[(c, "double precision") for c in sp.LINE_COLUMNS],
]
PRIMARY_KEY = ["season", "week", "player_id"]
WEEK_COLUMNS: list[tuple[str, str]] = [
    ("season", "integer"), ("week", "integer"), ("status", "text"), ("fetched_at", "timestamptz"),
    ("attempts", "integer"), ("n_objects", "integer"), ("n_lines", "integer"), ("by_position", "jsonb"),
    ("updated_at_min", "timestamptz"), ("updated_at_max", "timestamptz"), ("sha256", "text"), ("file_path", "text"),
    ("error", "text"), ("checked_at", "timestamptz"),
]
ROW_COLUMNS = [c for c, _ in COLUMNS]


def ensure_tables(conn: psycopg.Connection) -> None:
    """Both tables (``db migrate`` calls this, so a fresh database restores into them)."""
    from ..db import ensure_table

    ensure_table(conn, "ops", "sleeper_history", COLUMNS, PRIMARY_KEY)
    ensure_table(conn, "ops", "sleeper_history_weeks", WEEK_COLUMNS, ["season", "week"])
    conn.commit()


# ------------------------------------------------------------------------------ parsing
def _instant(v: Any) -> datetime | None:
    """Sleeper's epoch milliseconds -> UTC; None when absent or not a number."""
    try:
        ms = float(v)
    except (TypeError, ValueError):
        return None
    if ms <= 0 or ms != ms:
        return None
    return datetime.fromtimestamp(ms / 1000.0, UTC)


def has_line(row: Mapping[str, Any]) -> bool:
    """The record's rule (``mart_projection_record`` ``sl``): Sleeper's own total, or at least one priced stat."""
    if any(row.get(k) is not None for k in sp.POINTS_KEYS):
        return True
    return any(row.get(c) is not None for c in ("attempts", "carries", "targets", "passing_yards", "rushing_yards",
                                                 "receiving_yards", "receptions", "passing_tds", "rushing_tds",
                                                 "receiving_tds", "fg_made_0_19", "pat_made"))


@dataclass
class Parsed:
    rows: list[dict[str, Any]]
    n_objects: int
    by_position: dict[str, int]
    updated_min: datetime | None
    updated_max: datetime | None


def history_rows(payload: Any, season: int, week: int, fetched_at: datetime) -> Parsed:
    """One week's answer -> the rows with a projected line (``served = 'after_week'``, the payload's ``updated_at``).
    Raises ValueError when the answer is not a non-empty list (``sp.projection_rows``'s contract)."""
    if not isinstance(payload, list) or not payload:
        raise ValueError("expected a non-empty JSON list of projections, got "
                         + ("an empty list" if isinstance(payload, list) else type(payload).__name__))
    base = sp.projection_rows(payload, season, week, fetched_at)
    rows, stamps = [], []
    for r in base:
        if not has_line(r):
            continue
        item = r["payload"]
        upd = _instant(item.get("updated_at")) or _instant(item.get("last_modified"))
        if upd is not None:
            stamps.append(upd)
        out = {c: r.get(c) for c in ROW_COLUMNS if c in r}
        out.update({"updated_at": upd, "served": SERVED, "fetched_at": fetched_at})
        rows.append(out)
    by_pos = Counter(r.get("position") or "?" for r in rows)
    return Parsed(rows, len(payload), dict(sorted(by_pos.items())), min(stamps, default=None), max(stamps, default=None))


# ------------------------------------------------------------------------------ which weeks
def wanted_weeks(current_season: int, first_kickoffs: Mapping[tuple[int, int], datetime],
                 last_kickoffs: Mapping[tuple[int, int], datetime], pre_kickoff: Iterable[tuple[int, int]],
                 now: datetime, seasons: Iterable[int] = HISTORY_SEASONS) -> list[tuple[int, int]]:
    """The history seasons' weeks 1–18 (only seasons before the current one), then the current season's weeks whose
    last game is over (``GAME_OVER_AFTER`` after its last kickoff) and that have no snapshot fetched before the first
    kickoff (``pre_kickoff``: (season, week) the record can use)."""
    out = [(int(s), w) for s in sorted(set(seasons)) if int(s) < int(current_season) for w in WEEKS]
    have = {(int(s), int(w)) for s, w in pre_kickoff}
    for (s, w), last in sorted(last_kickoffs.items()):
        if int(s) != int(current_season) or (s, w) not in first_kickoffs:
            continue
        if now >= last + GAME_OVER_AFTER and (int(s), int(w)) not in have:
            out.append((int(s), int(w)))
    return out


# ------------------------------------------------------------------------------ where rows go
class Store(Protocol):
    def held(self) -> set[tuple[int, int]]: ...
    def attempts(self, season: int, week: int) -> int: ...
    def save(self, season: int, week: int, rows: list[dict[str, Any]], week_row: dict[str, Any]) -> None: ...
    def fail(self, week_row: dict[str, Any]) -> None: ...


class PgStore:
    """``ops.sleeper_history`` + ``ops.sleeper_history_weeks``: one transaction a week (its rows and its week row)."""

    def __init__(self, conn: psycopg.Connection):
        self.conn = conn

    def held(self) -> set[tuple[int, int]]:
        with self.conn.cursor() as cur:
            cur.execute(f"select season, week from {WEEKS_TABLE} where status = 'ok'")
            return {(int(s), int(w)) for s, w in cur.fetchall()}

    def attempts(self, season: int, week: int) -> int:
        with self.conn.cursor() as cur:
            cur.execute(f"select attempts from {WEEKS_TABLE} where season = %s and week = %s", (season, week))
            r = cur.fetchone()
        return int(r[0] or 0) if r else 0

    def _upsert_week(self, cur: psycopg.Cursor, week_row: dict[str, Any]) -> None:
        cols = [c for c, _ in WEEK_COLUMNS]
        vals = [Jsonb(week_row.get(c)) if c == "by_position" and week_row.get(c) is not None else week_row.get(c)
                for c in cols]
        sets = ", ".join(f"{c} = excluded.{c}" for c in cols if c not in ("season", "week"))
        cur.execute(f"insert into {WEEKS_TABLE} ({', '.join(cols)}) values ({', '.join(['%s'] * len(cols))}) "
                    f"on conflict (season, week) do update set {sets}", vals)

    def save(self, season: int, week: int, rows: list[dict[str, Any]], week_row: dict[str, Any]) -> None:
        with self.conn.transaction(), self.conn.cursor() as cur:
            cur.execute(f"delete from {TABLE} where season = %s and week = %s", (season, week))
            if rows:
                cur.executemany(f"insert into {TABLE} ({', '.join(ROW_COLUMNS)}) values ({', '.join(['%s'] * len(ROW_COLUMNS))})",
                                [tuple(r.get(c) for c in ROW_COLUMNS) for r in rows])
            self._upsert_week(cur, week_row)
        self.conn.commit()

    def fail(self, week_row: dict[str, Any]) -> None:
        with self.conn.transaction(), self.conn.cursor() as cur:
            # a failed week keeps no rows (an earlier partial load cannot be graded as if whole)
            cur.execute(f"delete from {TABLE} where season = %s and week = %s", (week_row["season"], week_row["week"]))
            self._upsert_week(cur, week_row)
        self.conn.commit()


# ------------------------------------------------------------------------------ the run
def archive_root(raw_dir: Path) -> Path:
    return raw_dir.joinpath(*ARCHIVE)


def archived(raw_dir: Path) -> dict[tuple[int, int], Path]:
    """The newest archived answer of each (season, week) in the history archive."""
    root = archive_root(raw_dir)
    out: dict[tuple[int, int], Path] = {}
    if not root.exists():
        return out
    for sdir in sorted(p for p in root.iterdir() if p.is_dir() and p.name.isdigit()):
        for f in sorted(sdir.iterdir()):
            m = sp.FILE_RE.match(f.name)
            if m:
                key = (int(sdir.name), int(m.group(1)))
                if key not in out or f.name > out[key].name:
                    out[key] = f
    return out


@dataclass
class HistoryRun:
    store: Store
    raw_dir: Path
    base_url: str
    now: datetime = field(default_factory=lambda: datetime.now(UTC).replace(microsecond=0))
    client: httpx.Client | None = None
    pause: Callable[[float], None] = time.sleep
    pause_s: float = PAUSE_S
    log_lines: list[str] = field(default_factory=list)
    replayed: list[tuple[int, int]] = field(default_factory=list)
    pulled: list[tuple[int, int]] = field(default_factory=list)
    failed: list[tuple[tuple[int, int], str]] = field(default_factory=list)

    def _week_row(self, season: int, week: int, status: str, fetched_at: datetime | None, parsed: Parsed | None,
                  path: Path | None, sha: str | None, error: str | None) -> dict[str, Any]:
        return {"season": season, "week": week, "status": status, "fetched_at": fetched_at,
                "attempts": self.store.attempts(season, week) + 1,
                "n_objects": parsed.n_objects if parsed else None, "n_lines": len(parsed.rows) if parsed else None,
                "by_position": parsed.by_position if parsed else None,
                "updated_at_min": parsed.updated_min if parsed else None,
                "updated_at_max": parsed.updated_max if parsed else None,
                "sha256": sha, "file_path": str(path) if path else None, "error": error, "checked_at": self.now}

    def load_file(self, season: int, week: int, path: Path) -> bool:
        """An archived answer -> the week's rows (no network). False (and a 'failed' week) when it does not parse."""
        fetched_at = sp.snapshot_fetched_at(path)
        try:
            data = read_archive(path)
            parsed = history_rows(json.loads(data), season, week, fetched_at)
        except (OSError, ValueError) as exc:
            self.store.fail(self._week_row(season, week, "failed", fetched_at, None, path, None, f"{path.name}: {exc}"))
            self.failed.append(((season, week), f"archive {path.name}: {exc}"))
            return False
        self.store.save(season, week, parsed.rows,
                        self._week_row(season, week, "ok", fetched_at, parsed, path, hashlib.sha256(data).hexdigest(), None))
        self.replayed.append((season, week))
        return True

    def replay(self, weeks: Iterable[tuple[int, int]]) -> None:
        files = archived(self.raw_dir)
        held = self.store.held()
        for key in weeks:
            if key not in held and key in files:
                self.load_file(key[0], key[1], files[key])

    def pull_week(self, season: int, week: int) -> bool:
        url = sp.projections_url(self.base_url, season, week)
        path = archive_root(self.raw_dir) / str(int(season)) / sp.snapshot_name(week, self.now)
        try:
            fetched = fetch_to_archive(url, path, conditional=False, client=self.client, compress=True)
            parsed = history_rows(json.loads(fetched.content), season, week, self.now)
            if not parsed.rows:
                raise ValueError(f"{parsed.n_objects} objects, none with a projected line")
        except (FetchError, ValueError, httpx.HTTPError) as exc:
            path.unlink(missing_ok=True)
            _meta_path(path).unlink(missing_ok=True)
            self.store.fail(self._week_row(season, week, "failed", self.now, None, None, None, f"{type(exc).__name__}: {exc}"))
            self.failed.append(((season, week), f"{type(exc).__name__}: {exc}"))
            log.warning("sleeper history %s week %s: %s", season, week, exc)
            return False
        self.store.save(season, week, parsed.rows,
                        self._week_row(season, week, "ok", self.now, parsed, path, fetched.checksum, None))
        self.pulled.append((season, week))
        log.info("sleeper history %s week %s: %s objects, %s with a line %s, updated_at %s", season, week,
                 parsed.n_objects, len(parsed.rows), parsed.by_position, parsed.updated_max)
        return True

    def pull(self, weeks: Iterable[tuple[int, int]]) -> None:
        held = self.store.held()
        todo = [k for k in weeks if k not in held]
        in_a_row = 0
        for i, (s, w) in enumerate(todo):
            if i:
                self.pause(self.pause_s)
            if self.pull_week(s, w):
                in_a_row = 0
                continue
            in_a_row += 1
            if in_a_row >= MAX_FAILS_IN_A_ROW:
                rest = len(todo) - i - 1
                log.warning("sleeper history: %s failures in a row; %s weeks left for the next night", in_a_row, rest)
                self.log_lines.append(f"stopped after {in_a_row} failures in a row; {rest} weeks left for the next night")
                break


def run_history(conn: psycopg.Connection, *, offline: bool = False, now: datetime | None = None,
                client: httpx.Client | None = None, pause: Callable[[float], None] = time.sleep,
                current_season: int | None = None) -> dict[str, Any]:
    """``league-lab ingest sleeper-history``: replay the history archive into the weeks not held, then (unless
    ``offline``) ask Sleeper for the weeks still missing. Returns the counts the summary prints."""
    from ..config import get_settings
    from .nflverse import current_nfl_season

    s = get_settings()
    ensure_tables(conn)
    now = now or datetime.now(UTC).replace(microsecond=0)
    season = int(current_season or current_nfl_season(now.date()))
    first = sp.read_first_kickoffs(conn, season)
    last = read_last_kickoffs(conn, season)
    want = wanted_weeks(season, first, last, pre_kickoff_weeks(conn, season, first), now)
    store = PgStore(conn)
    run = HistoryRun(store=store, raw_dir=s.raw_dir, base_url=s.sleeper_projections_url, now=now, client=client, pause=pause)
    run.replay(want)
    if not offline:
        own = client is None
        if own:
            run.client = httpx.Client(timeout=httpx.Timeout(s.http_timeout_seconds, connect=30.0), follow_redirects=True,
                                      headers={"User-Agent": "league-lab/0.1 (+local analytics)"}, trust_env=True)
        try:
            run.pull(want)
        finally:
            if own and run.client is not None:
                run.client.close()
    held = store.held()
    return {"wanted": want, "held": sorted(k for k in want if k in held), "replayed": run.replayed, "pulled": run.pulled,
            "failed": run.failed, "notes": run.log_lines, "offline": offline}


def read_last_kickoffs(conn: psycopg.Connection, season: int) -> dict[tuple[int, int], datetime]:
    """(season, week) -> the week's LAST kickoff (UTC), regular season (``raw.nfl_schedules``)."""
    from .weather import kickoff_utc

    with conn.cursor() as cur:
        cur.execute("""select week, gameday, gametime from raw.nfl_schedules
                       where season = %s and game_type = 'REG' and gameday is not null""", (int(season),))
        rows = cur.fetchall()
    out: dict[tuple[int, int], datetime] = {}
    for week, gameday, gametime in rows:
        k = kickoff_utc(gameday, gametime)
        key = (int(season), int(week))
        out[key] = max(out.get(key, k), k)
    return out


def pre_kickoff_weeks(conn: psycopg.Connection, season: int, first: Mapping[tuple[int, int], datetime]) -> set[tuple[int, int]]:
    """The current season's weeks with a snapshot in ``raw.sleeper_projections`` fetched before the first kickoff."""
    with conn.cursor() as cur:
        cur.execute("select to_regclass('raw.sleeper_projections') is not null")
        if not cur.fetchone()[0]:
            return set()
        cur.execute("""select week, min(fetched_at) from raw.sleeper_projections
                       where season = %s and season_type = 'regular' group by week""", (int(season),))
        rows = cur.fetchall()
    return {(int(season), int(w)) for w, t in rows if (int(season), int(w)) in first and t < first[(int(season), int(w))]}


def report_lines(res: Mapping[str, Any]) -> list[str]:
    """The pull's lines for the log and the summary: weeks held of wanted, by season; tonight's work; failures."""
    want, held = res["wanted"], set(map(tuple, res["held"]))
    by = Counter(s for s, _w in want)
    have = Counter(s for s, w in want if (s, w) in held)
    seasons = ", ".join(f"{s} {have[s]}/{by[s]}" for s in sorted(by))
    out = [f"weeks held: {len(held)} of {len(want)} ({seasons})",
           f"tonight: {len(res['pulled'])} pulled, {len(res['replayed'])} from the archive, {len(res['failed'])} failed"
           + (" (offline: no request)" if res.get("offline") else "")]
    for (s, w), why in res["failed"][:10]:
        out.append(f"  failed {s} week {w}: {why[:160]} (asked again next night)")
    if len(res["failed"]) > 10:
        out.append(f"  ... and {len(res['failed']) - 10} more failed weeks")
    out.extend(res.get("notes") or [])
    return out
