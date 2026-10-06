"""Each week's League outlook, kept (Wave I-O, IO-2; scripts/hosted_outlook.sql, docs/handbacks/IO-2.md).

What cannot be backfilled: the rest-of-season board is refit every night, so last week's power ranking can only be
compared with this week's if it was written down at the time. This module writes it down and reads it back.

* **The row** (``outlook.snapshots``): per league key, season and week — the power ranking (per team: the per-week
  number, its rank and the team's name) and the rest-of-season rows (projected wins, playoff odds, top seed), the model
  version, when it was built and when the week closes (its first kickoff). ``week`` = the first week the outlook has
  not seen played (the week the ranking looks ahead from).
* **When**: offered every time an outlook is built (``outlook._build``). The first build of a league-week inserts; a
  later build replaces it **only until that week's first kickoff** — after it the week is closed and nothing is
  written (a build made once games are under way is not stored at all).
* **Off the critical path**: the build only puts the row on a bounded queue (``QUEUE_MAX``; full = dropped and
  counted) that one daemon thread drains through ``db.run_rw`` (its own read-write connection; the read pool never
  sees a write). A failed write is counted and logged, never raised: the answer never waits for it or fails with it.
* **Switch** ``LEAGUE_LAB_OUTLOOK_STORE`` = ``auto`` (default: on when ``outlook.snapshots`` exists and the app role may
  insert and update it — probed once a minute, every ten once it is there) | ``off``. Without the table (the deploy
  lands before the nightly applies the SQL) everything is off and quiet: no arrows, no write, no error.
* **Bounds** (the site is public — any visitor's League screen triggers a write): only leagues anyone can read
  (Sleeper, MyFantasyLeague; never an ESPN or Yahoo key); a row ≤ ``MAX_BYTES`` of JSON (the table checks it too);
  house leagues and leagues an account has saved always; any other league at most ``NEW_PER_DAY`` new a day and
  ``VISITOR_MAX`` held (checked inside the write's transaction); 20 weeks kept (the nightly prunes, the SQL file).
* **Reads**: ``movement`` (last week's row for the arrows; a DB read per outlook build, never per request) and
  ``card`` (the page shell's preview: the last build kept in memory, else the newest stored row — never a provider
  call, never a simulation).
"""

from __future__ import annotations

import json
import logging
import os
import queue
import threading
import time
from datetime import datetime, timedelta
from typing import Any

import pandas as pd
import psycopg
from league_lab import clock, memo, platforms

from . import db

log = logging.getLogger("league_lab_api.outlook_store")

ENV = "LEAGUE_LAB_OUTLOOK_STORE"
NEW_PER_DAY = 20          # leagues nobody keeps (not a house league, not saved by an account) first stored in a day
VISITOR_MAX = 200         # such leagues held at once (each ≤ 20 rows)
KEEP_WEEKS = 20
MAX_BYTES = 8192          # power + rows as JSON text (a 32-team league with names ≈ 7 KB)
QUEUE_MAX = 64
SHARE_PLATFORMS = frozenset({"sleeper", "mfl"})     # leagues anyone can read: a share link, a stored row, a preview
NAME_MAX = 60             # a team's name in a row (provider text, cut)

stats = {"queued": 0, "written": 0, "closed": 0, "capped": 0, "failed": 0, "dropped": 0, "skipped": 0}
_queue: queue.Queue[dict] = queue.Queue(maxsize=QUEUE_MAX)
_worker: threading.Thread | None = None
_wlock = threading.Lock()
_ready = {"ok": False, "next": 0.0}
# the preview card of each league's latest build (a league key → {name, week, top}), ~300 bytes each; and the shell's
# lookups of the stored row (a hit or a miss) so a crawler's repeated hit never repeats the query
_cards = memo.region("outlook_card", ttl=14 * 86400.0, max_entries=512)
_card_reads = memo.region("outlook_card_db", ttl=600.0, max_entries=1024)

READY_SQL = ("select coalesce(has_table_privilege(to_regclass('outlook.snapshots'), 'insert'), false) "
             "and coalesce(has_table_privilege(to_regclass('outlook.snapshots'), 'update'), false) "
             "and coalesce(has_table_privilege(to_regclass('outlook.snapshots'), 'select'), false)")
KICKOFF_SQL = "select min(kickoff_at) as k from analytics.dim_game where season = %s and week = %s"
READ_SQL = ("select week, built_at, power, rows from outlook.snapshots "
            "where league_key = %s and season = %s and week in (%s, %s)")
LATEST_SQL = ("select league_name, week, power, rows from outlook.snapshots where league_key = %s "
              "order by season desc, week desc limit 1")
UPSERT_SQL = """insert into outlook.snapshots
                  (league_key, season, week, kind, league_name, model_version, built_at, closes_at, teams, power, rows)
                values (%(league_key)s, %(season)s, %(week)s, %(kind)s, %(league_name)s, %(model_version)s, %(built_at)s,
                        %(closes_at)s, %(teams)s, %(power)s::jsonb, %(rows)s::jsonb)
                on conflict (league_key, season, week) do update
                   set kind = excluded.kind, league_name = excluded.league_name, model_version = excluded.model_version,
                       built_at = excluded.built_at, teams = excluded.teams, power = excluded.power, rows = excluded.rows
                 where outlook.snapshots.closes_at > %(now)s"""
SAVED_SQL = ("select exists (select 1 from accounts.user_leagues ul join accounts.leagues l using (league_key) "
             "where l.provider = %s and l.external_id = %s)")
SAVED_READY_SQL = ("select coalesce(has_table_privilege(to_regclass('accounts.user_leagues'), 'select'), false) "
                   "and coalesce(has_table_privilege(to_regclass('accounts.leagues'), 'select'), false)")
KNOWN_SQL = "select exists (select 1 from outlook.snapshots where league_key = %s)"
NEW_TODAY_SQL = ("select count(*) from (select league_key from outlook.snapshots where kind = 'visitor' "
                 "group by league_key having min(built_at) > %s) x")
VISITORS_SQL = "select count(distinct league_key) from outlook.snapshots where kind = 'visitor'"


# ------------------------------------------------------------------------------------------------------- the switch
def mode() -> str:
    return "off" if os.environ.get(ENV, "auto").strip().lower() in ("off", "0", "false", "no") else "auto"


def ready() -> bool:
    """The table is there and the app role may read, insert and update it (checked once a minute; ten once it is)."""
    if mode() == "off":
        return False
    now = time.monotonic()
    if now >= _ready["next"]:
        try:
            df = db.fresh(READY_SQL)
            ok = bool(df.iloc[0, 0]) if not df.empty else False
        except Exception:  # noqa: BLE001 - no database, no table: off and quiet
            ok = False
        _ready.update(ok=ok, next=now + (600.0 if ok else 60.0))
    return bool(_ready["ok"])


def reset() -> None:
    """Forget the probe and the cards (tests; a schema applied while the process runs is seen within a minute)."""
    _ready.update(ok=False, next=0.0)
    _cards.clear()
    _card_reads.clear()


def shareable(league_key: str | None) -> bool:
    """A league anyone can already read (Sleeper, MyFantasyLeague): it may get a share link, a stored row and a
    preview card. An ESPN or Yahoo key (read with someone's own connection) never does."""
    try:
        key = platforms.check_key(str(league_key or ""))
    except Exception:  # noqa: BLE001 - not a league key
        return False
    return not platforms.is_reference(key) and platforms.platform(key) in SHARE_PLATFORMS


# --------------------------------------------------------------------------------------------------------- the row
def _num(v, nd: int = 3):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else round(f, nd)


def snapshot(ans: dict, *, league_name: str | None, week: int, built_at: datetime) -> dict:
    """The stored row from an outlook answer (``outlook._build``'s): compact, names cut to ``NAME_MAX``."""
    power = [{"roster_id": int(r["roster_id"]), "rank": int(r["rank"]), "per_week": _num(r["per_week"], 1),
              "team_name": str(r.get("team_name") or "")[:NAME_MAX]} for r in ans["power"]["rows"]]
    rows = [{"roster_id": int(r["roster_id"]), "wins_mean": _num(r.get("wins_mean"), 2),
             "playoff": _num(r.get("playoff")), "top_seed": _num(r.get("top_seed")), "title": _num(r.get("title"))}
            for r in (ans.get("outlook") or {}).get("rows") or []]
    return {"league_key": str(ans["league_id"]), "season": int(ans["season"]), "week": int(week),
            "league_name": (league_name or None) and str(league_name)[:120], "model_version": str(ans["version"]),
            "built_at": built_at, "teams": len(power), "power": power, "rows": rows}


def first_kickoff(season: int, week: int) -> datetime | None:
    try:
        df = db.query(KICKOFF_SQL, (int(season), int(week)))
    except Exception:  # noqa: BLE001
        return None
    if df.empty or pd.isna(df["k"].iloc[0]):
        return None
    k = pd.Timestamp(df["k"].iloc[0])
    return (k.tz_localize("UTC") if k.tzinfo is None else k.tz_convert("UTC")).to_pydatetime()


def offer(row: dict, *, house: bool, now: datetime | None = None) -> str:
    """Hand the row to the writer (never waits). What happened: queued | off | private | closed | too_big | dropped."""
    if not ready():
        return "off"
    if not shareable(row["league_key"]):
        return "private"
    now = now or clock.now()
    closes = first_kickoff(row["season"], row["week"])
    if closes is None or now >= closes:
        stats["closed"] += 1
        return "closed"
    power, rows = json.dumps(row["power"], separators=(",", ":")), json.dumps(row["rows"], separators=(",", ":"))
    if len(power.encode()) + len(rows.encode()) > MAX_BYTES:
        stats["skipped"] += 1
        return "too_big"
    item = {**row, "power": power, "rows": rows, "closes_at": closes, "now": now, "kind": "house" if house else None}
    global _worker
    try:
        with _wlock:
            if _worker is None or not _worker.is_alive():
                _worker = threading.Thread(target=_drain, name="league-lab-outlook-store", daemon=True)
                _worker.start()
        _queue.put_nowait(item)
    except queue.Full:
        stats["dropped"] += 1
        return "dropped"
    stats["queued"] += 1
    return "queued"


def _drain() -> None:
    while True:
        item = _queue.get()
        try:
            got = write(item)
            stats[got] = stats.get(got, 0) + 1
        except Exception as exc:  # noqa: BLE001 - the store is never load-bearing
            stats["failed"] += 1
            log.warning("outlook store: write failed for %s week %s: %s", item.get("league_key"), item.get("week"),
                        type(exc).__name__)
        finally:
            _queue.task_done()


def flush(timeout: float = 10.0) -> None:
    """Wait until the writer has handled every queued row (tests)."""
    end = time.monotonic() + timeout
    while _queue.unfinished_tasks and time.monotonic() < end:
        time.sleep(0.02)


def _saved(conn: psycopg.Connection, league_key: str) -> bool:
    """An account has saved this league (accounts.user_leagues): False when the accounts tables are not there."""
    if not conn.execute(SAVED_READY_SQL).fetchone()[0]:
        return False
    provider = platforms.platform(league_key)
    external = league_key.split(":", 1)[1] if ":" in league_key else league_key
    return bool(conn.execute(SAVED_SQL, (provider, external)).fetchone()[0])


def write(item: dict) -> str:
    """One row in one read-write transaction: written | capped | closed. The caps are checked inside it."""
    def fn(conn: psycopg.Connection) -> str:
        key = item["league_key"]
        kind = item.get("kind") or ("saved" if _saved(conn, key) else "visitor")
        if kind == "visitor" and not conn.execute(KNOWN_SQL, (key,)).fetchone()[0]:
            since = item["now"] - timedelta(days=1)
            if (conn.execute(NEW_TODAY_SQL, (since,)).fetchone()[0] >= NEW_PER_DAY
                    or conn.execute(VISITORS_SQL).fetchone()[0] >= VISITOR_MAX):
                return "capped"
        cur = conn.execute(UPSERT_SQL, {**item, "kind": kind})
        return "written" if cur.rowcount else "closed"
    return db.run_rw(fn, purpose="outlook")


# -------------------------------------------------------------------------------------------------------- the reads
def _rows(v) -> list:
    if isinstance(v, str):
        v = json.loads(v)
    return list(v) if isinstance(v, list) else []


def stored(league_key: str, season: int, week: int) -> dict:
    """{"prev": last week's row ({week, built_at, power, rows}) or None, "current": this week's row is stored}. Off,
    missing or failing: {"prev": None, "current": False}."""
    out: dict[str, Any] = {"prev": None, "current": False}
    if not ready() or not shareable(league_key):
        return out
    try:
        df = db.fresh(READ_SQL, (str(league_key), int(season), int(week) - 1, int(week)))
    except Exception:  # noqa: BLE001 - the arrows are never load-bearing
        return out
    for r in df.itertuples():
        if int(r.week) == int(week):
            out["current"] = True
        else:
            out["prev"] = {"week": int(r.week), "built_at": r.built_at, "power": _rows(r.power), "rows": _rows(r.rows)}
    return out


def remember_card(league_key: str, card: dict) -> None:
    if shareable(league_key):
        _cards.put(str(league_key), card)


def card(league_key: str | None) -> dict | None:
    """The preview card for a league link: {name, week, top: [{team, per_week, playoff}, …]} from the last build this
    process kept, else from the newest stored row; None (the default card) for anything else — a private league, nothing
    cached, the store off. Never a provider call, never a simulation."""
    try:
        key = platforms.check_key(str(league_key or ""))
    except Exception:  # noqa: BLE001
        return None
    if not shareable(key):
        return None
    hit = _cards.get(key)
    if hit is not None:
        return hit
    if not ready():
        return None
    got = _card_reads.get(key, "miss")
    if got != "miss":
        return got
    res = None
    try:
        df = db.fresh(LATEST_SQL, (key,))
        if not df.empty:
            r = df.iloc[0]
            power = sorted(_rows(r["power"]), key=lambda p: p.get("rank") or 99)
            odds = {o.get("roster_id"): o.get("playoff") for o in _rows(r["rows"])}
            res = {"name": r["league_name"] if isinstance(r["league_name"], str) else None, "week": int(r["week"]),
                   "top": [{"team": p.get("team_name") or "", "per_week": p.get("per_week"),
                            "playoff": odds.get(p.get("roster_id"))} for p in power[:5]]}
    except Exception:  # noqa: BLE001 - the default card
        res = None
    _card_reads.put(key, res)
    return res
