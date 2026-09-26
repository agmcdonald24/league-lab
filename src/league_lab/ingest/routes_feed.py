"""Routes-feed import contract (plan P2-12): a CSV from *any* provider -> ``raw.routes_feed``.

No free in-season source publishes routes run. When Andrew (or a leaguemate) licenses one, its
export is dropped in with::

    league-lab import-routes path/to/routes.csv --provider pff

CSV contract (header names, any column order, extra columns ignored):

    season, week, routes, and one of gsis_id | sleeper_id | pfr_id      required
    player_name, team, targets, receiving_yards                            optional (kept for reconciliation)

* ``season``/``week`` = NFL season and week as nflverse numbers them (REG 1-18, POST 19+).
* ``routes`` = the provider's route count for that player-game; never derived from snaps.
* Rows are replaced per (provider, season). Identity is resolved in dbt through
  ``analytics.player_id_map`` — never by name.

The staging model ``stg_routes_feed`` exposes it and ``fct_player_game.routes`` picks it up when
present; ``routes_proxy`` (participation-derived) stays separate and labelled.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
import psycopg

from ..db import ensure_table, pg_type_for, replace_partition
from ..manifest import LoadRecord, record_manifest

log = logging.getLogger(__name__)
SOURCE = "routes_feed"
TABLE = "routes_feed"
REQUIRED = ("season", "week", "routes")
ID_COLUMNS = ("gsis_id", "sleeper_id", "pfr_id")
OPTIONAL = ("player_name", "team", "targets", "receiving_yards")


class RoutesFeedError(ValueError):
    pass


def read_routes_csv(path: Path, provider: str) -> pl.DataFrame:
    df = pl.read_csv(path, infer_schema_length=0, null_values=["NA", "", "NULL"])
    df = df.rename({c: c.strip().lower() for c in df.columns})
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise RoutesFeedError(f"{path.name}: missing required columns {missing}")
    ids = [c for c in ID_COLUMNS if c in df.columns]
    if not ids:
        raise RoutesFeedError(f"{path.name}: needs one of {ID_COLUMNS}")
    keep = [c for c in (*REQUIRED, *ID_COLUMNS, *OPTIONAL) if c in df.columns]
    df = df.select(keep)
    for c in ID_COLUMNS + ("player_name", "team"):
        if c not in df.columns:
            df = df.with_columns(pl.lit(None, dtype=pl.Utf8).alias(c))
    for c in ("targets", "receiving_yards"):
        if c not in df.columns:
            df = df.with_columns(pl.lit(None, dtype=pl.Float64).alias(c))
        else:
            df = df.with_columns(pl.col(c).cast(pl.Float64, strict=False))
    df = df.with_columns(
        pl.col("season").cast(pl.Int32), pl.col("week").cast(pl.Int32),
        pl.col("routes").cast(pl.Float64, strict=False).cast(pl.Int32),
        pl.lit(provider).alias("provider"),
        pl.lit(path.name).alias("source_file"),
        pl.lit(datetime.now(UTC)).alias("imported_at"),
    )
    if df.filter(pl.col("routes").is_null() | (pl.col("routes") < 0)).height:
        raise RoutesFeedError(f"{path.name}: routes must be non-negative integers")
    if df.filter(pl.all_horizontal(pl.col(c).is_null() for c in ID_COLUMNS)).height:
        raise RoutesFeedError(f"{path.name}: every row needs a player id")
    key = df.select("season", "week", "gsis_id", "sleeper_id", "pfr_id")
    if key.n_unique() != df.height:
        raise RoutesFeedError(f"{path.name}: duplicate (season, week, player) rows")
    return df.select("season", "week", "gsis_id", "sleeper_id", "pfr_id", "player_name", "team", "routes",
                     "targets", "receiving_yards", "provider", "source_file", "imported_at")


def import_routes(conn: psycopg.Connection, path: Path, provider: str) -> list[LoadRecord]:
    df = read_routes_csv(path, provider)
    checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    out: list[LoadRecord] = []
    ensure_table(conn, "raw", TABLE, [(c, pg_type_for(t)) for c, t in zip(df.columns, df.dtypes, strict=True)])
    for season in sorted(df["season"].unique().to_list()):
        part = df.filter(pl.col("season") == season)
        rec = LoadRecord(source=SOURCE, dataset=provider, partition_key=str(season), source_url=str(path),
                         checksum_sha256=checksum, fetched_at=datetime.now(UTC), file_path=str(path))
        with conn.transaction():
            rec.row_count = replace_partition(conn, "raw", TABLE, part, {"provider": provider, "season": season})
            record_manifest(conn, rec)
        conn.commit()
        log.info("routes_feed %s %s: %s rows", provider, season, rec.row_count)
        out.append(rec)
    return out
