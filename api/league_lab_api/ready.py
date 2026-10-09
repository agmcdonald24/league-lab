"""IR-3 (Wave I-R): readiness, apart from liveness. ``GET /api/ready`` (no password, the ``read`` bucket, no secrets).

``/api/health`` stays the cheap liveness answer (200 while the process runs; the database's state in its body).
``/api/ready`` answers **200 only when the product can serve decisions** from the published data, else **503** with the
reason in plain words. The rule, checked in this order on one short connection of its own (5 s to connect, 5 s per
statement — never the request pool):

1. the database answers (``select 1``);
2. the published tables are there: ``ops.projections``, ``analytics.dim_game``, ``analytics.mart_player_week_projections``,
   ``analytics.mart_player_ros_projection`` — when they are away because a publication is being restored (the marker
   ``scripts/sync_to_hosted.sh`` puts on the database for the drop-then-restore path), the reason says so (``publishing``);
3. a publication exists: ``max(ops.projections.fitted_at)`` is not null (its time and age are in the answer; age alone
   never makes the site "not ready" — a missed nightly is the health check's ``stale``, not an outage);
4. the current week has projections: the week of the next regular-season kickoff after now (``league_lab.clock``) has
   rows in ``ops.projections`` (the boards) and in ``analytics.mart_player_week_projections`` (the lists); after the
   last kickoff of the season this check is "season over" and passes;
5. the rest-of-season list is not empty (``analytics.mart_player_ros_projection``).

The publication's id and time (``publication``): the JSON the sync writes as the comment of the ``analytics`` schema
(``{"publication": ..., "published_at": ..., "code": ..., "mode": ...}``), inside the transaction that publishes it, so
it changes with the tables; null on a database published before IR-3 (never a reason for 503).

The answer is kept 60 s after a success and 15 s after a failure (one probe at a time; the others get the last answer):
a check every few seconds neither keeps Neon's compute awake nor queues on it.
"""

from __future__ import annotations

import json
import threading
import time
from datetime import UTC, datetime

import psycopg
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from league_lab import clock

from .settings import app_dsn

router = APIRouter()

OK_TTL_S, FAIL_TTL_S = 60.0, 15.0
CONNECT_TIMEOUT_S, STATEMENT_TIMEOUT_MS = 5, 5000
NEEDED = ("ops.projections", "analytics.dim_game", "analytics.mart_player_week_projections",
          "analytics.mart_player_ros_projection")

_state: dict = {"answer": None, "next": 0.0}
_lock = threading.Lock()


def _iso(t: datetime | None) -> str | None:
    if t is None:
        return None
    return (t if t.tzinfo else t.replace(tzinfo=UTC)).astimezone(UTC).isoformat()


def _json_comment(text: str | None) -> dict | None:
    if not text:
        return None
    try:
        v = json.loads(text)
    except ValueError:
        return None
    return v if isinstance(v, dict) else None


def publication_of(conn: psycopg.Connection) -> dict | None:
    """The publication the ``analytics`` schema carries ({id, published_at, code, mode}), or None (none recorded)."""
    row = conn.execute("select obj_description(to_regnamespace('analytics'), 'pg_namespace')").fetchone()
    meta = _json_comment(row[0] if row else None)
    if not meta or not meta.get("publication"):
        return None
    return {"id": str(meta["publication"]), "published_at": meta.get("published_at"), "code": meta.get("code"),
            "mode": meta.get("mode")}


def _publishing_since(conn: psycopg.Connection) -> str | None:
    """The drop-then-restore path's marker on the database (``{"publishing_since": ...}``), or None."""
    row = conn.execute("select shobj_description(d.oid, 'pg_database') from pg_database d "
                       "where d.datname = current_database()").fetchone()
    meta = _json_comment(row[0] if row else None)
    return str(meta["publishing_since"]) if meta and meta.get("publishing_since") else None


def probe(conn: psycopg.Connection, now: datetime | None = None, wall: datetime | None = None) -> tuple[bool, dict]:
    """(ready, answer) on an open connection — the rule in the module's docstring, in its order. ``now``: the app's
    clock (the week; pinned in tests); ``wall``: the real time (the publication's age, as the health check's)."""
    now = now or clock.now()
    wall = wall or datetime.now(UTC)
    conn.execute("select 1")
    checks: dict = {"database": "ok"}
    missing = [name for name, there in zip(NEEDED, conn.execute(
        "select " + ", ".join(f"to_regclass('{n}') is not null" for n in NEEDED)).fetchone(), strict=True) if not there]
    if missing:
        since = _publishing_since(conn)
        checks["missing"] = missing
        if since:
            checks["publishing_since"] = since
            return False, {"ready": False, "code": "publishing", "checks": checks,
                           "reason": "The numbers are being replaced: a new publication started at "
                                     f"{since} and is not in place yet."}
        return False, {"ready": False, "code": "missing_tables", "checks": checks,
                       "reason": "The published tables are missing: " + ", ".join(missing) + "."}
    checks["publication"] = publication_of(conn)
    fitted = conn.execute("select max(fitted_at) from ops.projections").fetchone()[0]
    checks["as_of"] = _iso(fitted)
    if fitted is None:
        return False, {"ready": False, "code": "no_projections", "checks": checks,
                       "reason": "No projections have been published."}
    checks["age_hours"] = round((wall - (fitted if fitted.tzinfo else fitted.replace(tzinfo=UTC)))
                                .total_seconds() / 3600, 1)
    nxt = conn.execute("select season, week from analytics.dim_game where season_type = 'REG' and kickoff_at > %s "
                       "order by kickoff_at limit 1", (now,)).fetchone()
    if nxt is None:
        checks["week"] = {"season": None, "week": None, "note": "season over"}
    else:
        season, week = int(nxt[0]), int(nxt[1])
        board, lists = conn.execute(
            "select exists(select 1 from ops.projections where season = %s and week = %s),"
            " exists(select 1 from analytics.mart_player_week_projections where season = %s and week = %s)",
            (season, week, season, week)).fetchone()
        checks["week"] = {"season": season, "week": week, "board": bool(board), "lists": bool(lists)}
        if not board or not lists:
            what = "the boards" if not board else "the lists"
            return False, {"ready": False, "code": "week_missing", "checks": checks,
                           "reason": f"Week {week} of {season} has no projections in {what}."}
    ros = conn.execute("select exists(select 1 from analytics.mart_player_ros_projection)").fetchone()[0]
    checks["rest_of_season"] = bool(ros)
    if not ros:
        return False, {"ready": False, "code": "lists_empty", "checks": checks,
                       "reason": "The rest-of-season list is empty."}
    return True, {"ready": True, "code": "ready", "checks": checks, "reason": "The published numbers can be served."}


def check(dsn: str | None = None) -> tuple[bool, dict]:
    """Probe on a short connection of its own. A connection that fails is "does not answer"; a query that fails (a
    table dropped between two statements, a timeout) is "query"; anything else is "error" — the class name only, never
    text that could carry a host or a user, and never a 500."""
    try:
        # PO hotfix 2026-10-08: no `options=-c statement_timeout=…` at connect. The hosted database is reached through a
        # pooler that refuses startup options, so every probe on the live site answered "does not answer" (503) while
        # the app's own pool, on the same address, served every screen. The timeout is set for this transaction only
        # (`set local`: nothing is left on a pooled connection).
        with psycopg.connect(dsn or app_dsn(), connect_timeout=CONNECT_TIMEOUT_S,
                             application_name="league-lab-ready", prepare_threshold=None) as conn:  # one transaction: `set local` lives in it
            conn.execute(f"set local statement_timeout = {int(STATEMENT_TIMEOUT_MS)}")
            return probe(conn)
    except psycopg.errors.QueryCanceled as exc:   # ---- IS-4: a statement timeout is an OperationalError in psycopg,
        return False, {"ready": False, "code": "query", "checks": {"database": "ok"},   # but the database did answer
                       "reason": f"A readiness query took longer than {STATEMENT_TIMEOUT_MS // 1000} s ({exc.__class__.__name__})."}
    except psycopg.OperationalError as exc:
        return False, {"ready": False, "code": "database", "checks": {"database": f"unreachable: {exc.__class__.__name__}"},
                       "reason": f"The database does not answer ({exc.__class__.__name__})."}
    except psycopg.Error as exc:
        return False, {"ready": False, "code": "query", "checks": {"database": "ok"},
                       "reason": f"A readiness query failed ({exc.__class__.__name__})."}
    except Exception as exc:  # noqa: BLE001 - readiness answers in words, never a 500
        return False, {"ready": False, "code": "error", "checks": {},
                       "reason": f"The readiness check failed ({exc.__class__.__name__})."}


def _fresh() -> bool:
    return _state["answer"] is not None and time.monotonic() < _state["next"]


def cached() -> tuple[bool, dict]:
    """The last answer while it is fresh (60 s after a success, 15 s after a failure). One probe at a time: while one
    runs the others get the last answer; before the first answer they wait for it (and never probe again)."""
    if _fresh():
        return _state["answer"]
    first = _state["answer"] is None
    if not _lock.acquire(blocking=first):
        return _state["answer"]
    try:
        if not _fresh() and not (first and _state["answer"] is not None):
            ok, body = check()
            body["checked_at"] = _iso(datetime.now(UTC))
            _state.update(answer=(ok, body), next=time.monotonic() + (OK_TTL_S if ok else FAIL_TTL_S))
    finally:
        _lock.release()
    return _state["answer"]


def reset() -> None:
    _state.update(answer=None, next=0.0)


# ---- IU-4 (Wave I-U): a request that finds a published table missing (a drop-path publish has begun) makes the next
# /api/ready probe at once instead of serving a 200 kept for up to 60 s; a failure is then kept 15 s, so `publishing`
# is what a monitor sees for the whole gap, even a 5 s one.
def _tables_away() -> None:
    _state["next"] = 0.0


from . import db as _db  # noqa: E402 - the hook stays beside its handler

_db.on_tables_away.append(_tables_away)
# ---- end IU-4


@router.get("/api/ready", include_in_schema=False)
def ready() -> JSONResponse:
    ok, body = cached()
    return JSONResponse(body, status_code=200 if ok else 503, headers={"Cache-Control": "no-store"})
