"""Read-only database access for the API: the Streamlit app's `lib/db.py` contract without Streamlit.

* The read-only application role (settings.app_dsn()); nothing here can write — the role is
  `default_transaction_read_only` on the hosted copy, and every statement is a SELECT.
  (---- U-1: one exception, `write_one` below — the usage insert, its own read-write transaction on its own connection.)
* `query(sql, params)` returns a DataFrame (Decimal columns as floats, like the app) and caches it for
  10 minutes keyed on the SQL and its parameters (the app's `st.cache_data(ttl=600)`). The data changes
  once a night, so a cached answer is the answer. Every call returns a copy: callers may add columns.
  INF-2 (Wave I-J, the memory diet): the cache is the `sql` region of `league_lab.memo`'s one byte budget
  (`LEAGUE_LAB_CACHE_MB`, least recently used out first; it was 2,000 entries whatever their size), the copy is
  shallow (pandas 3's copy-on-write makes a caller's change its own without copying the data for every caller),
  and every text value is interned at the fetch (`intern_strings`: one "00-0037840" however many frames hold it).
* A connection pool keeps one connection open (Neon's pooler, or the local server), checked before use
  because Neon closes idle connections when its compute suspends.
* A relation that is missing (the hosted copy is dropped and restored by every sync, for a minute or two)
  raises `DataNotReady`, which the API answers with 503 and the app's own sentence.
"""

from __future__ import annotations

import atexit
import sys
import threading
from decimal import Decimal

import numpy as np
import pandas as pd
import psycopg
from league_lab import memo
from psycopg.types.numeric import FloatLoader
from psycopg_pool import ConnectionPool

from .settings import app_dsn

ANALYTICS = "analytics"
CACHE_TTL_SECONDS = 600


class DataNotReady(RuntimeError):
    """A mart the endpoint needs is not on this database right now."""


_pool: ConnectionPool | None = None
_pool_lock = threading.Lock()
_cache = memo.region("sql", ttl=CACHE_TTL_SECONDS)       # INF-2: (sql, params) -> DataFrame, in the shared budget


def pool() -> ConnectionPool:
    global _pool
    with _pool_lock:
        if _pool is None:
            _pool = ConnectionPool(app_dsn(), min_size=1, max_size=4, open=True, timeout=30,
                                   kwargs={"autocommit": True}, check=ConnectionPool.check_connection,
                                   max_idle=240, name="league-lab-api", configure=_numeric_as_float)
        return _pool


def _numeric_as_float(conn: psycopg.Connection) -> None:
    """INF-2: ``numeric`` comes back as a float, parsed from Postgres' text (no Decimal per cell to convert and drop:
    fewer short-lived objects, less heap left fragmented). The same value ``_run`` made before: ``float(Decimal(t))``
    and ``float(t)`` are both the correctly rounded double of the text ``t``."""
    conn.adapters.register_loader("numeric", FloatLoader)


def close() -> None:
    global _pool
    with _pool_lock:
        if _pool is not None:
            _pool.close()
            _pool = None


atexit.register(close)


def clear_cache() -> None:
    _cache.clear()


def intern_strings(df: pd.DataFrame) -> pd.DataFrame:
    """INF-2: every text column's values through ``sys.intern``, in place (the frame stays equal, value for value and
    dtype for dtype): a gsis_id, a position, a team, a scoring name is one object in the process however many rows and
    frames hold it. Vectorised (``pd.factorize``: one hash pass in C, one ``intern`` per distinct value). A column is
    interned when pandas made it ``str`` or when it is ``object`` holding only strings; anything else is left alone.
    ``category`` was not chosen: consumers group, merge, sort and ``isin`` on these columns, and a categorical changes
    groupby's rows (``observed``) and concat's dtypes."""
    for c in df.columns:
        s = df[c]
        if isinstance(s.dtype, pd.StringDtype):
            pass
        elif s.dtype == object:
            if pd.api.types.infer_dtype(s, skipna=True) != "string":
                continue
        else:
            continue
        vals = np.asarray(s.array, dtype=object)
        codes, uniques = pd.factorize(vals, use_na_sentinel=True)
        na = s.dtype.na_value if isinstance(s.dtype, pd.StringDtype) else None
        pool = np.empty(len(uniques) + 1, dtype=object)
        pool[:-1] = [sys.intern(u) for u in uniques]
        pool[-1] = na                                         # code -1 (a NULL) takes the last element
        new = pool.take(codes)
        if s.dtype == object:
            nulls = s.isna().to_numpy()
            if nulls.any():                                   # keep each NULL as it came (None, never NaN)
                new[nulls] = vals[nulls]
            df[c] = pd.Series(new, index=df.index, dtype=object)   # stays object (pandas 3 would infer str)
        else:
            df[c] = pd.array(new, dtype=s.dtype)
    return df


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
    return intern_strings(df)


_not_kept: set[str] = set()


def not_kept(*sqls: str) -> None:
    """INF-2: these statements' results are not kept in the ``sql`` region — their caller keeps what it builds from them
    (``anyleague.BOARD_INPUT_SQL``: a week's Board, a window's rest-of-season table), so keeping the raw rows as well
    held every board twice."""
    _not_kept.update(sqls)


def query(sql: str, params: tuple = (), *, ttl: float | None = None) -> pd.DataFrame:
    """Run a read-only query (cached 10 minutes, or ``ttl`` seconds, in the budget's ``sql`` region — unless
    ``not_kept``); returns a fresh (shallow, copy-on-write) copy every time."""
    if sql in _not_kept:
        return _run(sql, tuple(params))
    key = (sql, tuple(tuple(p) if isinstance(p, list) else p for p in params))
    hit = _cache.get(key)
    if hit is not None:
        return hit.copy(deep=False)
    df = _run(sql, tuple(params))
    _cache.put(key, df, ttl=ttl)
    return df.copy(deep=False)


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
    close_rw()                                                 # ---- IK-4: the other purposes' writers too


# ---- IK-4 (Wave I-K): the writer generalised — one read-write connection per purpose ("accounts"; usage keeps its
# own above), each behind its own lock, each transaction `BEGIN; SET TRANSACTION READ WRITE; …; COMMIT` on an
# autocommit connection the read pool never sees. `run_rw(fn)` runs `fn(conn)` inside that transaction and returns its
# result; a dropped connection (Neon suspended) rolls the transaction back and runs `fn` once more on a new connection,
# so `fn` must only touch the database. Accounts' rows are read here too (read-your-writes, never the 10-minute cache).
_rw: dict[str, psycopg.Connection] = {}
_rw_locks: dict[str, threading.Lock] = {}
_rw_guard = threading.Lock()


def _rw_conn(purpose: str) -> psycopg.Connection:
    conn = _rw.get(purpose)
    if conn is None or conn.closed or conn.broken:
        conn = psycopg.connect(app_dsn(), autocommit=True, connect_timeout=5, application_name=f"league-lab-{purpose}")
        _rw[purpose] = conn
    return conn


def run_rw(fn, *, purpose: str = "accounts"):
    """``fn(conn)`` in one read-write transaction on the purpose's own connection (one retry on a dropped one)."""
    with _rw_guard:
        lock = _rw_locks.setdefault(purpose, threading.Lock())
    with lock:
        for attempt in (1, 2):
            try:
                conn = _rw_conn(purpose)
                with conn.transaction():
                    conn.execute("set transaction read write")
                    return fn(conn)
            except psycopg.OperationalError:
                stale = _rw.pop(purpose, None)
                if stale is not None:
                    stale.close()
                if attempt == 2:
                    raise
    return None


def close_rw() -> None:
    with _rw_guard:
        for purpose in list(_rw):
            conn = _rw.pop(purpose, None)
            if conn is not None:
                conn.close()
# ---- end IK-4


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
