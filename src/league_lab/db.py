"""Database helpers: connections, raw-schema DDL, and transactional partition loads.

Design notes
------------
* Raw tables are owned by the pipeline role and created idempotently from code (``migrate``).
* Every load replaces exactly one *partition* (e.g. one season, one league-week) inside a
  single transaction: ``DELETE ... WHERE partition = X`` then ``COPY``. A failed load rolls
  back and leaves the previous good data untouched (plan §7, §9).
* Polars frames are streamed to Postgres with ``COPY ... FROM STDIN`` (CSV), which is the
  fastest path in psycopg3 and keeps memory bounded.
"""

from __future__ import annotations

import io
import logging
from collections.abc import Iterable, Sequence
from contextlib import contextmanager
from typing import Any

import polars as pl
import psycopg
from psycopg import sql

from .config import get_settings

log = logging.getLogger(__name__)
SCHEMAS = ("raw", "ops", "staging", "intermediate", "analytics", "analytics_seeds")

OPS_DDL = """
create table if not exists ops.load_manifest (
    load_id             bigserial primary key,
    source              text not null,
    dataset             text not null,
    partition_key       text not null,
    source_url          text,
    source_last_modified text,
    source_etag         text,
    fetched_at          timestamptz,
    checksum_sha256     text,
    schema_fingerprint  text,
    row_count           integer,
    status              text not null check (status in ('success','failed','skipped_unchanged','contract_failed')),
    error               text,
    code_version        text,
    file_path           text,
    started_at          timestamptz not null default now(),
    finished_at         timestamptz
);
create index if not exists load_manifest_src_idx on ops.load_manifest (source, dataset, partition_key, started_at desc);

create table if not exists ops.source_partition (
    source              text not null,
    dataset             text not null,
    partition_key       text not null,
    last_load_id        bigint references ops.load_manifest(load_id),
    checksum_sha256     text,
    source_etag         text,
    source_last_modified text,
    row_count           integer,
    loaded_at           timestamptz,
    primary key (source, dataset, partition_key)
);
-- Licensed routes-run import contract (plan P2-12). Exists empty so dbt can model it before any
-- provider file is imported; `league-lab import-routes` fills it.
create table if not exists ops.backtest_results (
    run_id            text,
    run_at            timestamptz,
    season            integer,
    week              integer,
    position          text,
    scorer            text,
    n_players         integer,
    spearman          double precision,
    top_n             integer,
    hit_rate          double precision,
    mae               double precision,
    top_n_actual_ppg  double precision,
    top_n_picked_ppg  double precision
);
-- Projection v2 (plan M-01/M-03): written by `league-lab project` / `league-lab backtest-v2`;
-- exist empty so dbt can model them before the first run.
create table if not exists ops.projections (
    model_version text, fitted_at timestamptz, train_seasons text, league_id text, season integer, week integer,
    gsis_id text, position text,
    proj_targets double precision, proj_receptions double precision, proj_receiving_yards double precision,
    proj_receiving_tds double precision, proj_carries double precision, proj_rushing_yards double precision,
    proj_rushing_tds double precision, proj_attempts double precision, proj_passing_yards double precision,
    proj_passing_tds double precision, proj_passing_interceptions double precision, proj_fumbles_lost_total double precision,
    proj_points double precision, p10 double precision, p25 double precision, p50 double precision, p75 double precision,
    p90 double precision, frozen_at timestamptz, frozen_source text
);
-- Decision record (plan B5): a league-week's rows are frozen once its first game kicks off.
-- frozen_source: NULL = live (rewritten by every refit), 'kickoff' = the board as published before the
-- week's first kickoff (frozen_at = that publication time), 'refit' = the week was already under way
-- when its rows were locked (not a kickoff record). An existing table gains the columns here.
alter table ops.projections add column if not exists frozen_at timestamptz;
alter table ops.projections add column if not exists frozen_source text;
-- Plan D6 (Wave D): the 50% range ("most weeks"), calibrated like the 80% one. NULL on rows written
-- before it existed (2026 weeks 1-3 are frozen with P10/P50/P90 only).
alter table ops.projections add column if not exists p25 double precision;
alter table ops.projections add column if not exists p75 double precision;
alter table ops.projections add column if not exists pricing text;  -- M4 (Wave I-G): flat | ev, NULL = flat
alter table ops.projections add column if not exists availability text;  -- IR-1 (Wave I-R): why a 0 (JSON)
create index if not exists projections_idx on ops.projections (league_id, season, week, position);
create table if not exists ops.projection_backtest (
    run_id text, run_at timestamptz, model_version text, train_seasons text, league_id text, season integer, week integer,
    position text, scorer text, n_players integer, spearman double precision, top_n integer, hit_rate double precision,
    mae double precision, coverage_80 double precision, pinball_10 double precision, pinball_50 double precision,
    pinball_90 double precision, interval_width double precision
);
-- v3 ship (2026-10-01): the 50% range's scores are kept from v3.0 on (v2.0's rows predate it: NULL)
alter table ops.projection_backtest add column if not exists coverage_50 double precision;
alter table ops.projection_backtest add column if not exists interval_width_50 double precision;
alter table ops.projection_backtest add column if not exists pinball_25 double precision;
alter table ops.projection_backtest add column if not exists pinball_75 double precision;
alter table ops.projection_backtest add column if not exists pricing text;  -- M4 (Wave I-G)
create table if not exists ops.projection_importance (
    model_version text, run_at timestamptz, league_id text, position text, feature text, importance double precision
);
-- Plan U-15: `model` = 'component' (what drives the projection: the component models, written by
-- `league-lab project`, `component` = 'total' in points or one stat in its own unit) or 'quantile_p50'
-- (the interval model, written by `backtest-v2`; the rows written before U-15 are that model).
alter table ops.projection_importance add column if not exists model text;
alter table ops.projection_importance add column if not exists component text;
alter table ops.projection_importance add column if not exists feature_label text;
alter table ops.projection_importance add column if not exists unit text;
alter table ops.projection_importance add column if not exists importance_sd double precision;
alter table ops.projection_importance add column if not exists importance_points double precision;
alter table ops.projection_importance add column if not exists baseline_mae double precision;
alter table ops.projection_importance add column if not exists n_rows integer;
alter table ops.projection_importance add column if not exists train_seasons text;
alter table ops.projection_importance add column if not exists eval_season integer;
alter table ops.projection_importance add column if not exists fit_seasons text;
update ops.projection_importance set model = 'quantile_p50', component = coalesce(component, 'p50_residual'),
    unit = coalesce(unit, 'points') where model is null;
-- Drift monitor (plan M-06): the live board's played weeks scored like the backtest, written by
-- `league-lab drift` and at the end of `league-lab project`.
create table if not exists ops.projection_drift (
    run_at timestamptz, model_version text, league_id text, season integer, week integer, position text,
    n_players integer, spearman double precision, top_n integer, hit_rate double precision, mae double precision,
    coverage_80 double precision, interval_width double precision, games_played integer, games_scheduled integer,
    frozen_share double precision
);
-- Exact lineup service (plan B1): written by `league-lab lineups` and at the end of `league-lab
-- project` (src/league_lab/lineup.py; replaces the season's rows). One row per starting slot
-- (filled or empty), bench player and player who cannot play, per league x season x week x roster x
-- proposed / realised; the totals table has one row per lineup.
create table if not exists ops.lineups (
    run_at timestamptz, model_version text, league_id text, season integer, week integer, roster_id integer,
    is_realised boolean, role text, slot text, slot_type text, slot_order integer, bench_rank integer,
    sleeper_player_id text, gsis_id text, player_name text, position text, value double precision,
    value_source text, margin double precision, is_locked boolean, report_status text, reason text
);
create index if not exists lineups_idx on ops.lineups (league_id, season, week, roster_id);
create table if not exists ops.lineup_totals (
    run_at timestamptz, as_of timestamptz, model_version text, league_id text, season integer, week integer,
    roster_id integer, is_realised boolean, lineup_value double precision, bench_value double precision,
    slots_total integer, slots_filled integer, empty_slots text, weakest_slot text, weakest_margin double precision,
    weakest_sleeper_player_id text, n_players integer, n_bench integer, n_unplayable integer, n_locked integer,
    n_questionable integer, n_ppg_valued integer, inputs_fingerprint text, n_unvalued integer
);
-- B5: share of a scored week's rows that are the board as published before kickoff
alter table ops.projection_drift add column if not exists frozen_share double precision;
alter table ops.lineup_totals add column if not exists n_unvalued integer;   -- B1 follow-up (2026-09-29)
create table if not exists raw.routes_feed (
    season          integer,
    week            integer,
    gsis_id         text,
    sleeper_id      text,
    pfr_id          text,
    player_name     text,
    team            text,
    routes          integer,
    targets         double precision,
    receiving_yards double precision,
    provider        text,
    source_file     text,
    imported_at     timestamptz
);
-- Waiver engine (plan B3): written by `league-lab waivers` and at the end of `league-lab project`
-- (src/league_lab/waivers.py; replaces the season's rows). One row per league x season x week x
-- roster x add x drop that gains this week or over the 4-week horizon, or one `nothing` row per roster.
create table if not exists ops.waiver_moves (
    run_at timestamptz, as_of timestamptz, model_version text, league_id text, season integer, week integer,
    roster_id integer, horizon_weeks integer, horizon_last_week integer, list_kind text, move_rank integer,
    add_rank integer, is_best_drop boolean, add_sleeper_id text, add_gsis_id text, add_name text,
    add_position text, add_value double precision, add_value_source text, add_reason text, add_report_status text,
    add_games_played integer, is_no_evidence boolean, drop_sleeper_id text, drop_gsis_id text, drop_name text,
    drop_position text, drop_value double precision, drop_ros_points double precision, add_ros_points double precision,
    rest_of_season_weeks integer, drop_horizon_loss double precision, drop_is_starter boolean, weekly_gain double precision,
    horizon_gain double precision, week_gains double precision[], add_horizon_gain double precision,
    lineup_before double precision, lineup_after double precision, add_slot text, add_slot_type text,
    fills_empty_slot boolean, displaced_sleeper_id text, displaced_gsis_id text, displaced_name text,
    displaced_position text, displaced_value double precision, displaced_slot text, open_roster_spots integer,
    inputs_fingerprint text
);
create index if not exists waiver_moves_idx on ops.waiver_moves (league_id, season, week, roster_id);
"""

# Polars dtype -> Postgres type. Anything unknown becomes text.
_PG_TYPES: dict[type, str] = {
    pl.Int8: "smallint",
    pl.Int16: "smallint",
    pl.Int32: "integer",
    pl.Int64: "bigint",
    pl.UInt8: "smallint",
    pl.UInt16: "integer",
    pl.UInt32: "bigint",
    pl.UInt64: "numeric",
    pl.Float32: "real",
    pl.Float64: "double precision",
    pl.Boolean: "boolean",
    pl.Utf8: "text",
    pl.String: "text",
    pl.Date: "date",
    pl.Datetime: "timestamptz",
    pl.Categorical: "text",
}


_WIDEN_RANK = {"boolean": 0, "smallint": 1, "integer": 2, "bigint": 3, "real": 4, "double precision": 5,
               "numeric": 6, "text": 9}
_INFO_SCHEMA_ALIAS = {"character varying": "text", "timestamp with time zone": "timestamptz"}


def widen_type(existing: str, incoming: str) -> str | None:
    """Return the type to ALTER an existing column to when the incoming type is wider, else None."""
    existing = _INFO_SCHEMA_ALIAS.get(existing, existing)
    if existing == incoming:
        return None
    if existing in _WIDEN_RANK and incoming in _WIDEN_RANK:
        return incoming if _WIDEN_RANK[incoming] > _WIDEN_RANK[existing] else None
    if incoming == "text" or existing in ("date", "timestamptz") and incoming in _WIDEN_RANK:
        return "text"
    return None


def pg_type_for(dtype: pl.DataType) -> str:
    for k, v in _PG_TYPES.items():
        if dtype == k or isinstance(dtype, k):
            return v
    if isinstance(dtype, pl.List):
        return "text[]"
    return "text"


@contextmanager
def connect(dsn: str | None = None, autocommit: bool = False):
    """Open a pipeline connection (or one for the given DSN)."""
    conn = psycopg.connect(dsn or get_settings().pipeline_dsn(), autocommit=autocommit)
    try:
        yield conn
    finally:
        conn.close()


def migrate(conn: psycopg.Connection) -> None:
    """Create schemas and ops tables if missing. Safe to run repeatedly.

    The ops tables a `project` step writes (lineups, waiver moves and upside stashes, role alerts, scenarios)
    are created here too, from the writer's own DDL, so a fresh or upgraded database passes `dbt build`'s
    source tests BEFORE the first `project` (the Mac hit this: `make build` ran before `make project` and
    three sources did not exist yet)."""
    # local: those modules import this one
    from . import experiments, lineup, projections, signals, waivers

    with conn.cursor() as cur:
        for schema in SCHEMAS:
            cur.execute(sql.SQL("create schema if not exists {}").format(sql.Identifier(schema)))
        cur.execute(OPS_DDL)
        for ddl in (*lineup.DDL.values(), waivers.UPSIDE_DDL, *signals.DDL.values(), experiments.DDL,   # D1: ops.feature_experiments
                    *projections.NFL_DDL.values()):   # F1: ops.projection_lines / projection_ranges / kd_lines / kd_ranges
            cur.execute(ddl)
        # ---- M6 (Wave I-H): ops.calibration_oof exists on a fresh database, so the nightly's restore-state can fill it
        from . import calibration
        cur.execute(calibration.OOF_DDL)
        cur.execute(calibration.OOF_MODEL_DDL)
        cur.execute(projections.MARKET_RECORD_DDL)       # the record's Sleeper side at the odds (dbt reads it as a source)
        # ---- end M6
        # ---- IP-3 (Wave I-P): the context record and its grade exist on a fresh database (IO-1 put them in the nightly's
        # STATE_TABLES; restore-state counts every state table, so a fresh database stopped the night there), with every
        # column the hosted copy may hold (Wave I-P's trend columns included): the restore copies into them
        from . import context_record
        cur.execute(context_record.DDL)
        cur.execute(context_record.GRADE_DDL)
        # ---- end IP-3
    conn.commit()
    # plan D3: raw.nfl_weather + the stadium reference (dbt resolves venues before any weather is fetched)
    from .ingest import weather

    weather.ensure_tables(conn)
    # plan E1: raw.sleeper_projections (Sleeper's own projections, the benchmark of mart_projection_record)
    from .ingest import sleeper_projections

    sleeper_projections.ensure_tables(conn)


def ensure_table(
    conn: psycopg.Connection,
    schema: str,
    table: str,
    columns: Sequence[tuple[str, str]],
    primary_key: Sequence[str] | None = None,
    extra_ddl: str | None = None,
) -> None:
    """Create ``schema.table`` if missing; add any columns that are new. Never drops columns."""
    with conn.cursor() as cur:
        col_sql = sql.SQL(", ").join(
            sql.SQL("{} {}").format(sql.Identifier(c), sql.SQL(t)) for c, t in columns
        )
        pk_sql = sql.SQL("")
        if primary_key:
            pk_sql = sql.SQL(", primary key ({})").format(
                sql.SQL(", ").join(sql.Identifier(c) for c in primary_key)
            )
        cur.execute(
            sql.SQL("create table if not exists {}.{} ({}{})").format(
                sql.Identifier(schema), sql.Identifier(table), col_sql, pk_sql
            )
        )
        cur.execute(
            "select column_name, data_type from information_schema.columns where table_schema=%s and table_name=%s",
            (schema, table),
        )
        existing = {r[0]: r[1] for r in cur.fetchall()}
        for c, t in columns:
            if c not in existing:
                cur.execute(
                    sql.SQL("alter table {}.{} add column {} {}").format(
                        sql.Identifier(schema), sql.Identifier(table), sql.Identifier(c), sql.SQL(t)
                    )
                )
            else:
                wider = widen_type(existing[c], t)
                if wider:
                    # upstream files drift between seasons (e.g. height int -> float); widen, never narrow
                    _alter_column_type(conn, schema, table, c, wider)
        if extra_ddl:
            cur.execute(extra_ddl)


def dependent_views(conn: psycopg.Connection, schema: str, table: str) -> list[tuple[str, str, str]]:
    """(schema, name, relkind) of views / materialized views that select from ``schema.table``."""
    with conn.cursor() as cur:
        cur.execute(
            """select distinct n.nspname, c.relname, c.relkind
               from pg_depend d
               join pg_rewrite r on r.oid = d.objid
               join pg_class c on c.oid = r.ev_class
               join pg_namespace n on n.oid = c.relnamespace
               where d.refclassid = 'pg_class'::regclass
                 and d.refobjid = %s::regclass
                 and d.classid = 'pg_rewrite'::regclass
                 and c.relkind in ('v', 'm')
                 and c.oid <> d.refobjid""",
            (f'"{schema}"."{table}"',),
        )
        return [(r[0], r[1], r[2]) for r in cur.fetchall()]


def _alter_column_type(conn: psycopg.Connection, schema: str, table: str, column: str, new_type: str) -> None:
    """ALTER COLUMN TYPE; if dbt views depend on the column, drop them first (dbt rebuilds every
    view on the next `dbt build`, and nothing else reads staging/intermediate views)."""
    stmt = sql.SQL("alter table {}.{} alter column {} type {} using {}::{}").format(
        sql.Identifier(schema), sql.Identifier(table), sql.Identifier(column), sql.SQL(new_type),
        sql.Identifier(column), sql.SQL(new_type),
    )
    with conn.cursor() as cur:
        try:
            cur.execute("savepoint alter_col")
            cur.execute(stmt)
            cur.execute("release savepoint alter_col")
            return
        except psycopg.errors.FeatureNotSupported:
            cur.execute("rollback to savepoint alter_col")
        deps = dependent_views(conn, schema, table)
        for vschema, vname, kind in deps:
            log.warning(
                "dropping %s %s.%s so raw.%s.%s can be widened to %s (run `league-lab dbt build` to recreate it)",
                "materialized view" if kind == "m" else "view", vschema, vname, table, column, new_type,
            )
            cur.execute(
                sql.SQL("drop {} if exists {}.{} cascade").format(
                    sql.SQL("materialized view" if kind == "m" else "view"), sql.Identifier(vschema), sql.Identifier(vname)
                )
            )
        cur.execute(stmt)


def downcast_to_existing(conn: psycopg.Connection, schema: str, table: str, df: pl.DataFrame) -> pl.DataFrame:
    """When an incoming column is *nominally* wider than the stored column (float vs integer) but
    every value is a whole number, cast the frame instead of altering the table. Lossless, and it
    avoids DDL that would invalidate dependent views. Anything not lossless is left for ensure_table."""
    with conn.cursor() as cur:
        cur.execute(
            "select column_name, data_type from information_schema.columns where table_schema=%s and table_name=%s",
            (schema, table),
        )
        existing = {r[0]: r[1] for r in cur.fetchall()}
    if not existing:
        return df
    int_targets = {"smallint": pl.Int16, "integer": pl.Int32, "bigint": pl.Int64}
    casts = []
    for c, t in zip(df.columns, df.dtypes, strict=True):
        ex = existing.get(c)
        if ex in int_targets and t in (pl.Float32, pl.Float64):
            col = df[c].fill_nan(None)
            if col.drop_nulls().is_empty() or (col.drop_nulls() == col.drop_nulls().floor()).all():
                casts.append(col.cast(int_targets[ex]).alias(c))
    return df.with_columns(casts) if casts else df


def _frame_to_csv(df: pl.DataFrame) -> io.StringIO:
    """Serialize a frame to CSV suitable for COPY. Lists become Postgres array literals."""
    out = df
    for name, dtype in zip(out.columns, out.dtypes, strict=True):
        if isinstance(dtype, pl.List):
            inner = pl.col(name).list.eval(
                pl.concat_str([pl.lit('"'), pl.element().cast(pl.Utf8).str.replace_all('"', '\\"'), pl.lit('"')])
            )
            out = out.with_columns(
                pl.when(pl.col(name).is_null())
                .then(None)
                .otherwise(pl.concat_str([pl.lit("{"), inner.list.join(","), pl.lit("}")]))
                .alias(name)
            )
        elif dtype == pl.Datetime or isinstance(dtype, pl.Datetime):
            out = out.with_columns(pl.col(name).dt.to_string("%Y-%m-%d %H:%M:%S%.f%z").alias(name))
    buf = io.StringIO()
    out.write_csv(buf, include_header=False, null_value="", quote_style="necessary")
    buf.seek(0)
    return buf


def copy_frame(conn: psycopg.Connection, schema: str, table: str, df: pl.DataFrame) -> int:
    """COPY a polars frame into an existing table (columns matched by name). Returns rows."""
    if df.height == 0:
        return 0
    cols = sql.SQL(", ").join(sql.Identifier(c) for c in df.columns)
    stmt = sql.SQL("copy {}.{} ({}) from stdin with (format csv, null '')").format(
        sql.Identifier(schema), sql.Identifier(table), cols
    )
    buf = _frame_to_csv(df)
    with conn.cursor() as cur, cur.copy(stmt) as cp:
        while chunk := buf.read(1 << 20):
            cp.write(chunk)
    return df.height


def replace_partition(
    conn: psycopg.Connection,
    schema: str,
    table: str,
    df: pl.DataFrame,
    where: dict[str, Any],
) -> int:
    """Delete rows matching ``where`` (AND of equalities) then COPY ``df``. Caller commits."""
    with conn.cursor() as cur:
        if where:
            cond = sql.SQL(" and ").join(
                sql.SQL("{} = {}").format(sql.Identifier(k), sql.Literal(v)) for k, v in where.items()
            )
            cur.execute(
                sql.SQL("delete from {}.{} where {}").format(
                    sql.Identifier(schema), sql.Identifier(table), cond
                )
            )
        else:
            cur.execute(sql.SQL("truncate {}.{}").format(sql.Identifier(schema), sql.Identifier(table)))
    return copy_frame(conn, schema, table, df)


def upsert_rows(
    conn: psycopg.Connection,
    schema: str,
    table: str,
    rows: Iterable[dict[str, Any]],
    key: Sequence[str],
) -> int:
    """Row-wise upsert used for small JSON-shaped Sleeper payloads."""
    rows = list(rows)
    if not rows:
        return 0
    cols = list(rows[0].keys())
    insert = sql.SQL("insert into {}.{} ({}) values ({}) on conflict ({}) do update set {}").format(
        sql.Identifier(schema),
        sql.Identifier(table),
        sql.SQL(", ").join(sql.Identifier(c) for c in cols),
        sql.SQL(", ").join(sql.Placeholder() for _ in cols),
        sql.SQL(", ").join(sql.Identifier(k) for k in key),
        sql.SQL(", ").join(
            sql.SQL("{} = excluded.{}").format(sql.Identifier(c), sql.Identifier(c))
            for c in cols
            if c not in key
        ),
    )
    with conn.cursor() as cur:
        cur.executemany(insert, [tuple(r[c] for c in cols) for r in rows])
    return len(rows)


def fetch_all(conn: psycopg.Connection, query: str, params: Sequence[Any] | None = None) -> list[tuple]:
    with conn.cursor() as cur:
        cur.execute(query, params)
        return cur.fetchall()
