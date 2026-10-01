"""Sleeper's own weekly projections (plan E1, "Our record") -> ``raw.sleeper_projections``.

Why: the numbers every Sleeper user already sees for free. ``mart_projection_record`` holds League Lab's
frozen board against them, week by week, on the players both projected — the proof (or not) that the
lab beats the free consensus.

Endpoint (not part of Sleeper's documented v1 API, and on another host: configurable as
``LEAGUE_LAB_SLEEPER_PROJECTIONS_URL``, default ``https://api.sleeper.com/projections/nfl``)::

    <base>/<season>/<week>?season_type=regular&position[]=QB&...&position[]=DEF&order_by=ppr

It answers a JSON list, one object per player: ``player_id`` (Sleeper's id; the team abbreviation for a
DEF), ``week``, ``season`` (a string), ``season_type``, ``opponent``, ``team``, ``category`` ('proj'),
``company`` (who made the projection), ``date``, ``game_id``, ``last_modified`` / ``updated_at``, a
``player`` object (name, position, team, injury status) and ``stats``: the projected stat line keyed by
Sleeper's scoring keys (``pass_yd``, ``rec``, ``rec_tgt``, ``fum_lost``, ``fgm_30_39`` ...) plus Sleeper's
own totals ``pts_ppr`` / ``pts_half_ppr`` / ``pts_std``. Parsing is defensive: unknown keys are fine
(the object is kept whole in ``payload``), a missing key is NULL (unknown is not zero), a non-numeric
value is NULL, an object without ``player_id`` is skipped.

Snapshots. Every pull is one snapshot: one ``fetched_at`` for all its rows (key: season, season_type,
week, player_id, fetched_at), never overwritten — what Sleeper said on Tuesday and what it said on
Thursday are different facts. A pull whose bytes equal the week's newest archived snapshot writes no
new file and no new rows (its sidecar records the check). The record uses the LAST snapshot fetched
before the week's first kickoff: the freeze rule of ``ops.projections`` (B5).

Archive (replayable; ``--offline`` reads only these files, never the network)::

    data/raw/sleeper/projections/<season>/<week:02d>_<YYYYmmddTHHMMSSZ>.json.gz   (+ .meta.json sidecar)

A plain ``.json`` without a sidecar in the same folder (a hand ``curl -g ... -o 04_<stamp>.json``) replays
too; its fetch time is the stamp in its name.

Manifest: source ``sleeper``; dataset ``projections`` = one partition per snapshot
(``<season>:<week>:<stamp>``), dataset ``projections_pull`` = the live pull of a week (``<season>:<week>``),
so a failed pull shows on Data Status until a later pull of that week succeeds.

Pricing. ``parse_line`` maps the stat keys onto the weekly-stats column names (``STAT_COLUMNS``:
pass_yd -> passing_yards, rec_tgt -> targets, fum_lost -> fumbles_lost_total ...): the names
``scoring.compute_points`` and the dbt macro ``league_points`` read, so ``price_line`` and the mart price
Sleeper's line in each league's scoring with the machinery that prices League Lab's own projection
(yardage bonuses included, applied to the projected line the same way).
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import httpx
import psycopg
from psycopg.types.json import Jsonb

from ..config import get_settings
from ..db import ensure_table
from ..http import FetchError, _meta_path, fetch_to_archive, read_archive, read_meta
from ..manifest import LoadRecord, get_partition_state, record_manifest
from ..scoring import SLEEPER_LONG_TD_MAP, SLEEPER_STAT_MAP, compute_points

log = logging.getLogger(__name__)

SOURCE = "sleeper"
DATASET = "projections"
PULL_DATASET = "projections_pull"
SEASON_TYPE = "regular"
POSITIONS = ("QB", "RB", "WR", "TE", "K", "DEF")
STAMP = "%Y%m%dT%H%M%SZ"
FILE_RE = re.compile(r"^(\d{1,2})_(\d{8}T\d{6}Z)\.json(\.gz)?$")


def _first_column(expr: str) -> str:
    return expr.split("+")[0].strip()


# Sleeper projected-stat key -> the weekly-stats column it fills. The scoring keys come from
# scoring.SLEEPER_STAT_MAP (a two-column expression such as fgm_50p -> fg_made_50_59 + fg_made_60_ is
# filled through its first column: the price is the same), the volume keys are what the projection
# components are called.
STAT_COLUMNS: dict[str, str] = {
    "pass_att": "attempts", "pass_cmp": "completions", "rush_att": "carries", "rec_tgt": "targets",
    **{k: _first_column(expr) for k, (expr, _) in SLEEPER_STAT_MAP.items()},
    **{k: expr for k, (expr, _) in SLEEPER_LONG_TD_MAP.items()},
}
LINE_COLUMNS: tuple[str, ...] = tuple(dict.fromkeys(STAT_COLUMNS.values()))
POINTS_KEYS = ("pts_ppr", "pts_half_ppr", "pts_std")

COLUMNS: list[tuple[str, str]] = [
    ("season", "integer"), ("season_type", "text"), ("week", "integer"), ("player_id", "text"),
    ("fetched_at", "timestamptz"),                 # the snapshot: when Sleeper answered (sidecar / file stamp)
    ("position", "text"), ("team", "text"), ("opponent", "text"), ("game_id", "text"),
    ("company", "text"), ("category", "text"), ("proj_date", "text"),
    *[(k, "double precision") for k in POINTS_KEYS],
    *[(c, "double precision") for c in LINE_COLUMNS],
    ("payload", "jsonb"), ("file_path", "text"), ("_loaded_at", "timestamptz"),
]
PRIMARY_KEY = ["season", "season_type", "week", "player_id", "fetched_at"]
TABLE = "sleeper_projections"


def ensure_tables(conn: psycopg.Connection) -> None:
    """``raw.sleeper_projections`` (called by ``db migrate``, so dbt finds the source before any pull)."""
    ensure_table(conn, "raw", TABLE, COLUMNS, PRIMARY_KEY,
                 extra_ddl="create index if not exists sleeper_projections_week_idx on raw.sleeper_projections "
                           "(season, week, fetched_at)")
    conn.commit()


# ------------------------------------------------------------------------------ parsing and pricing
def _num(v: Any) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _text(v: Any) -> str | None:
    return None if v is None or v == "" else str(v)


def parse_line(stats: Any) -> dict[str, float | None]:
    """Sleeper's ``stats`` object -> {weekly-stats column: value} for every ``LINE_COLUMNS`` (None = not given)."""
    out: dict[str, float | None] = dict.fromkeys(LINE_COLUMNS)
    if not isinstance(stats, Mapping):
        return out
    for key, col in STAT_COLUMNS.items():
        v = _num(stats.get(key))
        if v is not None:
            out[col] = v
    return out


def price_line(stats: Any, scoring: Mapping[str, float]) -> float:
    """Sleeper's projected line priced in a league's ``scoring_settings`` (scoring.compute_points)."""
    return compute_points(parse_line(stats), scoring)


def projection_rows(payload: Any, season: int, week: int, fetched_at: datetime, file_path: str | None = None,
                    season_type: str = SEASON_TYPE) -> list[dict[str, Any]]:
    """raw.sleeper_projections rows of one snapshot (the request's season / week; one row per player_id,
    the last object wins on a duplicate). Raises ValueError when the answer is not a list."""
    if not isinstance(payload, list):
        raise ValueError(f"expected a JSON list of projections, got {type(payload).__name__}")
    rows: dict[str, dict[str, Any]] = {}
    for item in payload:
        if not isinstance(item, Mapping):
            continue
        pid = _text(item.get("player_id"))
        if pid is None:
            continue
        stats = item.get("stats") if isinstance(item.get("stats"), Mapping) else {}
        player = item.get("player") if isinstance(item.get("player"), Mapping) else {}
        rows[pid] = {
            "season": int(season), "season_type": season_type, "week": int(week), "player_id": pid,
            "fetched_at": fetched_at,
            "position": _text(player.get("position") or item.get("position")),
            "team": _text(item.get("team") or player.get("team")), "opponent": _text(item.get("opponent")),
            "game_id": _text(item.get("game_id")), "company": _text(item.get("company")),
            "category": _text(item.get("category")), "proj_date": _text(item.get("date")),
            **{k: _num(stats.get(k)) for k in POINTS_KEYS},
            **parse_line(stats),
            "payload": dict(item), "file_path": file_path,
        }
    if len(rows) < sum(1 for i in payload if isinstance(i, Mapping) and _text(i.get("player_id"))):
        log.warning("sleeper projections %s week %s: duplicate player_id objects (the last one kept)", season, week)
    return list(rows.values())


def projections_url(base: str, season: int, week: int, season_type: str = SEASON_TYPE) -> str:
    query = "&".join([f"season_type={season_type}", *[f"position[]={p}" for p in POSITIONS], "order_by=ppr"])
    return f"{base.rstrip('/')}/{int(season)}/{int(week)}?{query}"


# ------------------------------------------------------------------------------ the archive
@dataclass(frozen=True)
class Snapshot:
    season: int
    week: int
    path: Path

    @property
    def stamp(self) -> str:
        m = FILE_RE.match(self.path.name)
        return m.group(2) if m else ""


def archive_dir(raw_dir: Path, season: int) -> Path:
    return raw_dir / "sleeper" / "projections" / str(int(season))


def snapshot_name(week: int, at: datetime) -> str:
    return f"{int(week):02d}_{at.astimezone(UTC):{STAMP}}.json.gz"


def archived_snapshots(raw_dir: Path, seasons: Iterable[int] | None = None, weeks: Iterable[int] | None = None) -> list[Snapshot]:
    """Every archived snapshot (.json.gz from a pull, .json from a hand curl), oldest first per week."""
    root = raw_dir / "sleeper" / "projections"
    if not root.exists():
        return []
    want_s = {int(s) for s in seasons} if seasons else None
    want_w = {int(w) for w in weeks} if weeks else None
    out = []
    for sdir in sorted(p for p in root.iterdir() if p.is_dir() and p.name.isdigit()):
        if want_s is not None and int(sdir.name) not in want_s:
            continue
        for f in sdir.iterdir():
            m = FILE_RE.match(f.name)
            if m and (want_w is None or int(m.group(1)) in want_w):
                out.append(Snapshot(int(sdir.name), int(m.group(1)), f))
    return sorted(out, key=lambda s: (s.season, s.week, s.stamp, s.path.name))


def snapshot_fetched_at(path: Path) -> datetime:
    """When Sleeper answered: the sidecar's fetched_at, else the stamp in the file name, else the mtime."""
    meta = read_meta(path)
    if meta and meta.get("fetched_at"):
        ts = datetime.fromisoformat(meta["fetched_at"])
        return ts if ts.tzinfo else ts.replace(tzinfo=UTC)
    m = FILE_RE.match(path.name)
    if m:
        return datetime.strptime(m.group(2), STAMP).replace(tzinfo=UTC)
    return datetime.fromtimestamp(path.stat().st_mtime, UTC)


def _sha(path: Path) -> str:
    meta = read_meta(path) or {}
    return meta.get("sha256") or hashlib.sha256(read_archive(path)).hexdigest()


# ------------------------------------------------------------------------------ where rows go
class Store(Protocol):
    def partition_state(self, dataset: str, partition_key: str) -> dict[str, Any] | None: ...
    def replace(self, rows: list[dict[str, Any]], rec: LoadRecord, season: int, week: int, fetched_at: datetime) -> int: ...
    def record(self, rec: LoadRecord) -> None: ...


ROW_COLUMNS = [c for c, _ in COLUMNS if c != "_loaded_at"]


class PgStore:
    """raw.sleeper_projections + the load manifest: one transaction per snapshot (its rows + the manifest row)."""

    def __init__(self, conn: psycopg.Connection):
        self.conn = conn

    def partition_state(self, dataset: str, partition_key: str) -> dict[str, Any] | None:
        return get_partition_state(self.conn, SOURCE, dataset, partition_key)

    def replace(self, rows: list[dict[str, Any]], rec: LoadRecord, season: int, week: int, fetched_at: datetime) -> int:
        cols = ", ".join(ROW_COLUMNS)
        marks = ", ".join(["%s"] * len(ROW_COLUMNS))
        try:
            with self.conn.transaction(), self.conn.cursor() as cur:
                cur.execute("delete from raw.sleeper_projections where season = %s and season_type = %s and week = %s "
                            "and fetched_at = %s", (season, SEASON_TYPE, week, fetched_at))
                if rows:
                    cur.executemany(f"insert into raw.sleeper_projections ({cols}, _loaded_at) values ({marks}, now())",
                                    [tuple(Jsonb(r[c]) if c == "payload" else r[c] for c in ROW_COLUMNS) for r in rows])
                rec.row_count = len(rows)
                record_manifest(self.conn, rec)
            self.conn.commit()
        except Exception as exc:  # noqa: BLE001 - a failed snapshot is a manifest row, the rest still loads
            self.conn.rollback()
            rec.status, rec.error = "failed", f"{type(exc).__name__}: {exc}"
            self.record(rec)
            log.exception("sleeper projections load failed for %s", rec.partition_key)
        return rec.row_count or 0

    def record(self, rec: LoadRecord) -> None:
        record_manifest(self.conn, rec)
        self.conn.commit()


# ------------------------------------------------------------------------------ the run
@dataclass
class ProjectionsRun:
    store: Store
    raw_dir: Path
    base_url: str
    force: bool = False
    now: datetime = field(default_factory=lambda: datetime.now(UTC).replace(microsecond=0))
    client: httpx.Client | None = None
    kickoffs: Mapping[tuple[int, int], datetime] = field(default_factory=dict)   # (season, week) -> first kickoff
    results: list[LoadRecord] = field(default_factory=list)

    def _fail(self, rec: LoadRecord, error: str, status: str = "failed") -> LoadRecord:
        rec.status, rec.error = status, error
        self.store.record(rec)
        self.results.append(rec)
        log.warning("sleeper projections %s %s: %s", rec.dataset, rec.partition_key, error)
        return rec

    def load_snapshot(self, snap: Snapshot) -> LoadRecord:
        """One archived snapshot -> its rows (skipped when the manifest already holds these bytes)."""
        fetched_at = snapshot_fetched_at(snap.path)
        meta = read_meta(snap.path) or {}
        rec = LoadRecord(source=SOURCE, dataset=DATASET, partition_key=f"{snap.season}:{snap.week}:{fetched_at:{STAMP}}",
                         source_url=meta.get("url") or str(snap.path), fetched_at=fetched_at, file_path=str(snap.path))
        try:
            data = read_archive(snap.path)
            rec.checksum_sha256 = hashlib.sha256(data).hexdigest()
            prior = self.store.partition_state(DATASET, rec.partition_key)
            if prior and prior.get("checksum_sha256") == rec.checksum_sha256 and not self.force:
                rec.status, rec.row_count = "skipped_unchanged", prior.get("row_count")
                self.store.record(rec)
                self.results.append(rec)
                return rec
            rows = projection_rows(json.loads(data), snap.season, snap.week, fetched_at, str(snap.path))
        except (OSError, ValueError) as exc:
            return self._fail(rec, f"{snap.path.name}: {exc}", "contract_failed" if isinstance(exc, ValueError) else "failed")
        self.store.replace(rows, rec, snap.season, snap.week, fetched_at)
        if rec.status == "success":
            log.info("sleeper projections %s week %s @ %s: %s rows", snap.season, snap.week, f"{fetched_at:{STAMP}}", rec.row_count)
        self.results.append(rec)
        return rec

    def replay(self, seasons: Iterable[int] | None = None, weeks: Iterable[int] | None = None) -> list[LoadRecord]:
        snaps = archived_snapshots(self.raw_dir, seasons, weeks)
        if not snaps:
            log.info("no Sleeper projections archived under %s yet: nothing to replay", self.raw_dir / "sleeper" / "projections")
        for snap in snaps:
            self.load_snapshot(snap)
        return self.results

    def pull(self, season: int, week: int) -> LoadRecord:
        """Fetch the week's projections now: a new snapshot file (unless the bytes equal the week's newest
        snapshot), then its rows. A failed or malformed answer leaves no file behind."""
        url = projections_url(self.base_url, season, week)
        pull_rec = LoadRecord(source=SOURCE, dataset=PULL_DATASET, partition_key=f"{season}:{week}", source_url=url)
        d = archive_dir(self.raw_dir, season)
        before = archived_snapshots(self.raw_dir, [season], [week])
        path = d / snapshot_name(week, self.now)
        try:
            fetched = fetch_to_archive(url, path, conditional=False, client=self.client, compress=True)
            payload = json.loads(fetched.content)
            if not isinstance(payload, list) or not payload:
                raise ValueError("expected a non-empty JSON list of projections, got "
                                 + ("an empty list" if isinstance(payload, list) else type(payload).__name__))
        except (FetchError, ValueError) as exc:
            path.unlink(missing_ok=True)
            _meta_path(path).unlink(missing_ok=True)
            return self._fail(pull_rec, str(exc), "contract_failed" if isinstance(exc, ValueError) else "failed")
        # the snapshot's time is the pull's (the file name's stamp, to the second): the sidecar is aligned to it
        # and keeps the moment the answer arrived as answered_at
        meta = read_meta(path) or {}
        meta.update({"answered_at": meta.get("fetched_at"), "fetched_at": self.now.isoformat()})
        _meta_path(path).write_text(json.dumps(meta, indent=2))
        pull_rec.fetched_at, pull_rec.checksum_sha256, pull_rec.row_count = self.now, fetched.checksum, len(payload)
        newest = before[-1] if before else None
        snap = Snapshot(season, week, path)
        if newest is not None and newest.path != path and _sha(newest.path) == fetched.checksum:
            # nothing changed since the last snapshot: keep that one, note the check on its sidecar
            path.unlink(missing_ok=True)
            _meta_path(path).unlink(missing_ok=True)
            meta = read_meta(newest.path)
            if meta is not None:
                meta["checked_at"] = self.now.isoformat()
                _meta_path(newest.path).write_text(json.dumps(meta, indent=2))
            log.info("sleeper projections %s week %s: unchanged since %s", season, week, newest.path.name)
            pull_rec.status = "skipped_unchanged"
            snap = newest
        self.store.record(pull_rec)
        self.results.append(pull_rec)
        if (k := self.kickoffs.get((int(season), int(week)))) is not None and self.now >= k:
            log.warning("week %s of %s kicked off at %s: this snapshot is archived, but the record uses the last one "
                        "fetched before kickoff", week, season, k)
        return self.load_snapshot(snap)


def read_first_kickoffs(conn: psycopg.Connection, season: int) -> dict[tuple[int, int], datetime]:
    """(season, week) -> the week's first kickoff (UTC) from raw.nfl_schedules (regular season)."""
    from .weather import kickoff_utc

    with conn.cursor() as cur:
        cur.execute("""select week, gameday, gametime from raw.nfl_schedules
                       where season = %s and game_type = 'REG' and gameday is not null""", (int(season),))
        rows = cur.fetchall()
    out: dict[tuple[int, int], datetime] = {}
    for week, gameday, gametime in rows:
        k = kickoff_utc(gameday, gametime)
        key = (int(season), int(week))
        out[key] = min(out.get(key, k), k)
    return out


def next_week(kickoffs: Mapping[tuple[int, int], datetime], season: int, now: datetime) -> int | None:
    """The first regular-season week whose first game has not kicked off: the week the next freeze is about."""
    weeks = sorted(w for (s, w), k in kickoffs.items() if s == int(season) and k > now)
    return weeks[0] if weeks else None


def ingest_sleeper_projections(conn: psycopg.Connection, season: int | None = None, week: int | None = None, *,
                               offline: bool = False, force: bool = False, now: datetime | None = None,
                               client: httpx.Client | None = None) -> list[LoadRecord]:
    """``league-lab ingest sleeper-projections``. Live: pull ``week`` of ``season`` (default: the current NFL
    season and its next week to kick off) into a new snapshot. ``offline``: replay every archived snapshot
    (narrowed by ``season`` / ``week`` when given) without touching the network."""
    from .nflverse import current_nfl_season

    s = get_settings()
    ensure_tables(conn)
    now = now or datetime.now(UTC).replace(microsecond=0)
    run = ProjectionsRun(store=PgStore(conn), raw_dir=s.raw_dir, base_url=s.sleeper_projections_url, force=force,
                         now=now, client=client)
    if offline:
        return run.replay([season] if season else None, [week] if week else None)
    season = season or current_nfl_season(now.date())
    run.kickoffs = read_first_kickoffs(conn, season)
    if week is None:
        week = next_week(run.kickoffs, season, now)
        if week is None:
            return [run._fail(LoadRecord(source=SOURCE, dataset=PULL_DATASET, partition_key=f"{season}:none"),
                              f"no regular-season week of {season} still to kick off in raw.nfl_schedules: pass --week")]
        log.info("sleeper projections: pulling %s week %s (the next week to kick off, %s)", season, week, run.kickoffs[(season, week)])
    own = client is None
    if own:
        run.client = httpx.Client(timeout=httpx.Timeout(s.http_timeout_seconds, connect=30.0), follow_redirects=True,
                                  headers={"User-Agent": "league-lab/0.1 (+local analytics)"}, trust_env=True)
    try:
        run.pull(season, week)
    finally:
        if own and run.client is not None:
            run.client.close()
    return run.results
