"""Read-only database access for the API: the Streamlit app's `lib/db.py` contract without Streamlit.

* The read-only application role (settings.app_dsn()); nothing here can write — the role is
  `default_transaction_read_only` on the hosted copy, and every statement is a SELECT.
  (---- U-1: one exception, `write_one` below — the usage insert, its own read-write transaction on its own connection.)
* `query(sql, params)` returns a DataFrame (Decimal columns as floats, like the app) and caches it for
  10 minutes keyed on the SQL and its parameters (the app's `st.cache_data(ttl=600)`). The data changes
  once a night, so a cached answer is the answer. Every call returns a copy: callers may add columns.
* A connection pool keeps one connection open (Neon's pooler, or the local server), checked before use
  because Neon closes idle connections when its compute suspends.
* A relation that is missing (the hosted copy is dropped and restored by every sync, for a minute or two)
  raises `DataNotReady`, which the API answers with 503 and the app's own sentence.
"""

from __future__ import annotations

import atexit
import threading
import time
from decimal import Decimal

import pandas as pd
import psycopg
from psycopg_pool import ConnectionPool

from .settings import app_dsn

ANALYTICS = "analytics"
CACHE_TTL_SECONDS = 600


class DataNotReady(RuntimeError):
    """A mart the endpoint needs is not on this database right now."""


_pool: ConnectionPool | None = None
_pool_lock = threading.Lock()
_cache: dict[tuple, tuple[float, pd.DataFrame]] = {}
_cache_lock = threading.Lock()


def pool() -> ConnectionPool:
    global _pool
    with _pool_lock:
        if _pool is None:
            _pool = ConnectionPool(app_dsn(), min_size=1, max_size=4, open=True, timeout=30,
                                   kwargs={"autocommit": True}, check=ConnectionPool.check_connection,
                                   max_idle=240, name="league-lab-api")
        return _pool


def close() -> None:
    global _pool
    with _pool_lock:
        if _pool is not None:
            _pool.close()
            _pool = None


atexit.register(close)


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


def _run(sql: str, params: tuple) -> pd.DataFrame:
    with pool().connection() as conn, conn.cursor() as cur:
        try:
            cur.execute(sql, params)
        except psycopg.errors.UndefinedTable as exc:
            raise DataNotReady(str(exc).splitlines()[0]) from exc
        cols = [d.name for d in cur.description]
        rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=cols)
    for c in df.columns:
        if df[c].dtype == object:
            sample = df[c].dropna()
            if not sample.empty and isinstance(sample.iloc[0], Decimal):
                df[c] = df[c].astype(float)
    return df


def query(sql: str, params: tuple = (), *, ttl: float | None = None) -> pd.DataFrame:
    """Run a read-only query (cached 10 minutes, or ``ttl`` seconds); returns a fresh copy every time."""
    key = (sql, tuple(tuple(p) if isinstance(p, list) else p for p in params))
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(key)
    if hit is not None and hit[0] > now:
        return hit[1].copy()
    df = _run(sql, tuple(params))
    with _cache_lock:
        _cache[key] = (now + (CACHE_TTL_SECONDS if ttl is None else ttl), df)
        if len(_cache) > 2000:                       # bounded: drop the expired, then the oldest half
            for k in [k for k, (exp, _) in _cache.items() if exp <= now] or list(_cache)[: len(_cache) // 2]:
                _cache.pop(k, None)
    return df.copy()


def scalar(sql: str, params: tuple = ()):
    df = query(sql, params)
    return None if df.empty else df.iloc[0, 0]


# ---- U-1 (Wave I-F): the one write path — usage.events, never the read pool's connections ----------------------
# The app role stays `default_transaction_read_only = on`. A usage insert opens its own explicit transaction on its
# own connection (one, kept open and re-made when Neon has closed it): BEGIN; SET TRANSACTION READ WRITE; INSERT;
# COMMIT. The read pool above never sees a read-write transaction. Any failure is swallowed by the caller
# (usage.py): usage is never load-bearing. `fresh` reads without the 10-minute cache (the summary route).
_writer: psycopg.Connection | None = None
_writer_lock = threading.Lock()


def _writer_conn() -> psycopg.Connection:
    global _writer
    if _writer is None or _writer.closed or _writer.broken:
        _writer = psycopg.connect(app_dsn(), autocommit=True, connect_timeout=5, application_name="league-lab-usage")
    return _writer


def write_one(sql: str, params: tuple) -> None:
    """One INSERT in its own read-write transaction on the writer connection; one retry on a dropped connection."""
    global _writer
    with _writer_lock:
        for attempt in (1, 2):
            try:
                conn = _writer_conn()
                with conn.transaction():                       # autocommit connection: an explicit BEGIN … COMMIT
                    conn.execute("set transaction read write")
                    conn.execute(sql, params)
                return
            except psycopg.OperationalError:
                if _writer is not None:
                    _writer.close()
                _writer = None
                if attempt == 2:
                    raise


def close_writer() -> None:
    global _writer
    with _writer_lock:
        if _writer is not None:
            _writer.close()
            _writer = None


atexit.register(close_writer)


def fresh(sql: str, params: tuple = ()) -> pd.DataFrame:
    """A read on the pool without the cache (the usage summary changes by the second)."""
    return _run(sql, tuple(params))
# ---- end U-1


def missing_relations(names: tuple[str, ...]) -> list[str]:
    """Which of the given analytics relations (tables or views) do not exist yet."""
    df = query("select table_name from information_schema.tables where table_schema = %s and table_name = any(%s)",
               (ANALYTICS, list(names)))
    present = set(df["table_name"]) if not df.empty else set()
    return [n for n in names if n not in present]
