#!/usr/bin/env python3
"""Replicate PlayerWire's published briefs into the hosted Postgres schema `playerwire` (plan N2, docs/PLAYERWIRE.md).

Runs on Andrew's Mac only (PlayerWire's read API is loopback there): launchd every 15 minutes
(`scripts/launchd/com.leaguelab.playerwire-sync.plist`) or `make playerwire-sync`. It is the ONE writer of schema
`playerwire` and connects as role `playerwire_writer`, which can write nothing else — the marts (`analytics`,
`analytics_seeds`, `ops`) stay GitHub Actions' alone (HOSTING.md § 5, extended in docs/PLAYERWIRE.md § "One writer").

The protocol is PlayerWire's reference consumer (`playerwire/examples/league_lab_sync.py`, docs/API.md § "Consumer
protocol") against Postgres:

1. **Bootstrap** (no cursor yet, or after a 410/409): page through ``GET /v1/briefs`` at one pinned watermark, then in
   ONE transaction write every brief, mark the live rows the snapshot no longer has as withdrawn, and save the
   ``sync_cursor``. A crash before the commit leaves neither the briefs nor the cursor.
2. **Changes**: ``GET /v1/brief-changes?cursor=…`` until ``has_more`` is false. Each page's upserts and tombstones and
   its ``next_cursor`` commit together; re-applying a page is harmless.
3. **Versions**: an upsert never replaces a newer version, and never revives a tombstone of the same or a newer
   version (a re-delivered old version cannot bring back a withdrawn brief).
4. **Tombstones**: the row stays (``deleted = true``, the tombstone's version and reason) and loses all of its text —
   headline, news, analysis and the evidence link are cleared and ``payload`` becomes the tombstone (a withdrawn
   brief's text must not remain visible; the table's check constraint enforces it).
5. **Recovery**: 410 ``cursor_expired`` / 409 ``cursor_filter_mismatch`` → reset the cursor and bootstrap again (on a
   later snapshot page: restart the snapshot, nothing written yet). 429 / 503 → wait ``Retry-After`` (bounded), retry.

League Lab replicates every brief (no ``player_id`` filter) and maps players at read time through
``analytics.player_id_map`` (AGENTS.md rule 3). Synthetic briefs (PlayerWire's fictional fixtures, served only by a
preview-mode server) are never written unless ``--allow-synthetic``.

Environment (``.env`` is read; the caller's environment wins):
  PLAYERWIRE_API_URL          PlayerWire's read API (default http://127.0.0.1:8790)
  PLAYERWIRE_API_KEY          its bearer key (``python3 -m pw client create --name league-lab --scopes read``)
  PLAYERWIRE_HOSTED_URL       the writer's DSN: postgresql://playerwire_writer:<password>@<host>/<db>?sslmode=require
  PLAYERWIRE_WRITER_PASSWORD  (init-schema only) the password to set for playerwire_writer
  LEAGUE_LAB_HOSTED_ADMIN_URL (init-schema only) the database owner's DSN

Commands:
  sync [--once] [--interval 900] [--dry-run]   bootstrap if needed, then drain the changes (``--once`` for launchd)
  status                                       the replica's counts and the last run (JSON)
  init-schema                                  create / update the schema and the role (scripts/init_playerwire_schema.sql)

Exit codes: 0 done (or another sync holds the lock) · 1 PlayerWire or the database failed (recorded in
``playerwire.sync_state.last_error``) · 2 configuration (a variable missing, the wrong role).
"""

from __future__ import annotations

import argparse
import contextlib
import copy
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_SQL = ROOT / "scripts" / "init_playerwire_schema.sql"
DEFAULT_API = "http://127.0.0.1:8790"
WRITER_ROLE = "playerwire_writer"
LOCK_KEY = 0x504C5752                     # pg advisory lock: one sync at a time ("PLWR")
RESYNC_CODES = ("cursor_expired", "cursor_filter_mismatch")
FILTER_SIGNATURE = json.dumps({"player_id": []})   # everything; League Lab maps players at read time
PAGE_LIMIT = 200                          # PlayerWire's maximum
ABSENT = "absent_from_snapshot"           # the reason given to a live row a new bootstrap no longer has
STATE_KEYS = ("sync_cursor", "high_watermark", "snapshot_watermark", "filter_signature", "bootstrapped_at",
              "last_sync_at", "last_error", "last_error_at", "api_url")
BRIEF_COLUMNS = ("brief_id", "version", "status", "pw_player_id", "primary_sleeper_id", "primary_gsis_id", "category",
                 "headline", "news", "analysis", "verification_status", "published_at", "updated_at", "evidence_url",
                 "evidence_publisher", "evidence_published_at")


def utcnow() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def log(message: str) -> None:
    print(f"{utcnow().isoformat()} playerwire-sync: {message}", file=sys.stderr, flush=True)


# ------------------------------------------------------------------------------------------------ PlayerWire's API
class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(f"HTTP {status} {code}: {message}")
        self.status, self.code, self.message = status, code, message


Transport = Callable[[str, dict], tuple[int, dict, bytes]]


def http_transport(base_url: str, timeout: float = 30) -> Transport:
    """``transport(path_and_query, headers) -> (status, headers, body)`` over urllib (a network failure is an
    ApiError with status 0, so the caller records it like any other)."""
    base = base_url.rstrip("/")

    def transport(target: str, headers: dict) -> tuple[int, dict, bytes]:
        req = urllib.request.Request(base + target, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - a configured http(s) base URL
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers or {}), e.read()
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise ApiError(0, "unreachable", f"PlayerWire at {base} did not answer ({getattr(e, 'reason', e)})") from e
    return transport


class Client:
    """GET only. 429 / 503 are retried after ``Retry-After`` (1–120 s, at most ``max_retries`` times)."""

    def __init__(self, transport: Transport, api_key: str | None = None, *, max_retries: int = 5,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self.transport, self.api_key, self.max_retries, self.sleep = transport, api_key, max_retries, sleep

    def get(self, path: str, params: list[tuple[str, Any]] | None = None) -> dict:
        query = urllib.parse.urlencode([(k, v) for k, v in (params or []) if v is not None])
        target = path + ("?" + query if query else "")
        headers = {"Accept": "application/json", "User-Agent": "league-lab/playerwire-sync"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        for attempt in range(self.max_retries + 1):
            status, resp_headers, body = self.transport(target, headers)
            if status == 200:
                return json.loads(body)
            try:
                payload = json.loads(body)
            except (ValueError, TypeError):
                payload = {}
            err = payload.get("error", {}) if isinstance(payload, dict) else {}
            if status in (429, 503) and attempt < self.max_retries:
                ra = str({k.lower(): v for k, v in resp_headers.items()}.get("retry-after", "1")).strip()
                self.sleep(min(max(int(ra) if ra.isdigit() else 1, 1), 120))
                continue
            raise ApiError(status, err.get("code", "http_error"),
                           err.get("message") or body[:200].decode("utf-8", errors="replace"))
        raise AssertionError("unreachable")


# ------------------------------------------------------------------------------------------------ payload → row
def _text(v: Any) -> str | None:
    s = str(v).strip() if v is not None else ""
    return s or None


def _ts(v: Any) -> datetime | None:
    if not isinstance(v, str) or not v.strip():
        return None
    try:
        d = datetime.fromisoformat(v.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=UTC)


def _https(v: Any) -> str | None:
    s = _text(v)
    return s if s and s.lower().startswith("https://") else None


def _ids(player: Any) -> tuple[str | None, str | None, str | None]:
    """(PlayerWire id, sleeper id, gsis id) of a payload's Player."""
    p = player if isinstance(player, dict) else {}
    ext = p.get("external_ids") if isinstance(p.get("external_ids"), dict) else {}
    return _text(p.get("id")), _text(ext.get("sleeper")), _text(ext.get("gsis"))


def brief_row(brief: dict) -> dict:
    """The display columns of one brief (the payload itself is stored whole next to them)."""
    pw_id, sleeper, gsis = _ids(brief.get("primary_player"))
    evidence = [e for e in brief.get("evidence") or [] if isinstance(e, dict)]
    first = evidence[0] if evidence else {}
    analysis = brief.get("analysis")
    return {
        "brief_id": str(brief["id"]), "version": int(brief["version"]), "status": _text(brief.get("status")) or "published",
        "pw_player_id": pw_id, "primary_sleeper_id": sleeper, "primary_gsis_id": gsis,
        "category": _text(brief.get("category")), "headline": _text(brief.get("headline")), "news": _text(brief.get("news")),
        "analysis": _text(analysis.get("text")) if isinstance(analysis, dict) else None,
        "verification_status": _text(brief.get("verification_status")),
        "published_at": _ts(brief.get("published_at")), "updated_at": _ts(brief.get("updated_at")),
        "evidence_url": _https(first.get("url")), "evidence_publisher": _text(first.get("publisher")),
        "evidence_published_at": _ts(first.get("source_published_at")),
    }


def brief_players(brief: dict) -> list[dict]:
    """The primary player and every related player (one row per PlayerWire id; the primary wins a duplicate)."""
    out: dict[str, dict] = {}
    for role, players in (("primary", [brief.get("primary_player")]), ("related", brief.get("related_players") or [])):
        for p in players:
            pw_id, sleeper, gsis = _ids(p)
            if pw_id and pw_id not in out:
                out[pw_id] = {"pw_player_id": pw_id, "sleeper_id": sleeper, "gsis_id": gsis, "role": role}
    return list(out.values())


def tombstone_payload(t: dict) -> dict:
    """What a withdrawn brief keeps: the tombstone's id, version, operation, change time and coarse reason only."""
    return {k: t.get(k) for k in ("id", "version", "operation", "changed_at", "reason")}


# ------------------------------------------------------------------------------------------------ the stores
class Store(Protocol):
    def transaction(self) -> contextlib.AbstractContextManager: ...
    def state(self) -> dict: ...
    def set_state(self, **fields: Any) -> None: ...
    def current(self, brief_id: str) -> tuple[int, bool] | None: ...
    def live(self) -> dict[str, int]: ...
    def put_brief(self, row: dict, players: list[dict], payload: dict, now: datetime) -> None: ...
    def put_tombstone(self, brief_id: str, version: int, reason: str, payload: dict, now: datetime) -> None: ...


class MemoryStore:
    """The same contract in memory: the tests' fake database and ``--dry-run``'s scratch copy. A transaction that
    raises restores the copy taken when it began (as a rollback would)."""

    def __init__(self) -> None:
        self.briefs: dict[str, dict] = {}
        self.players: dict[str, list[dict]] = {}
        self._state: dict[str, Any] = dict.fromkeys(STATE_KEYS)
        self.commits = 0

    @contextlib.contextmanager
    def transaction(self) -> Iterator[None]:
        saved = copy.deepcopy((self.briefs, self.players, self._state))
        try:
            yield
        except BaseException:
            self.briefs, self.players, self._state = saved
            raise
        self.commits += 1

    def state(self) -> dict:
        return dict(self._state)

    def set_state(self, **fields: Any) -> None:
        unknown = set(fields) - set(STATE_KEYS)
        if unknown:
            raise KeyError(f"unknown sync_state fields: {sorted(unknown)}")
        self._state.update(fields)

    def current(self, brief_id: str) -> tuple[int, bool] | None:
        r = self.briefs.get(brief_id)
        return None if r is None else (r["version"], r["deleted"])

    def live(self) -> dict[str, int]:
        return {k: r["version"] for k, r in self.briefs.items() if not r["deleted"]}

    def put_brief(self, row: dict, players: list[dict], payload: dict, now: datetime) -> None:
        self.briefs[row["brief_id"]] = {**row, "payload": copy.deepcopy(payload), "synced_at": now, "deleted": False,
                                        "deleted_reason": None, "deleted_at": None}
        self.players[row["brief_id"]] = [dict(p) for p in players]

    def put_tombstone(self, brief_id: str, version: int, reason: str, payload: dict, now: datetime) -> None:
        old = self.briefs.get(brief_id, {})
        self.briefs[brief_id] = {
            **dict.fromkeys(BRIEF_COLUMNS), **{k: old.get(k) for k in ("pw_player_id", "primary_sleeper_id",
                                                                       "primary_gsis_id", "category", "published_at")},
            "brief_id": brief_id, "version": version, "status": "withdrawn", "payload": dict(payload),
            "synced_at": now, "deleted": True, "deleted_reason": reason, "deleted_at": now}
        self.players.pop(brief_id, None)


class PgStore:
    """``playerwire.*`` over one psycopg connection (autocommit; ``transaction()`` is BEGIN … COMMIT / ROLLBACK)."""

    def __init__(self, conn: Any) -> None:
        self.conn = conn

    def transaction(self) -> contextlib.AbstractContextManager:
        return self.conn.transaction()

    def _one(self, sql: str, params: tuple = ()) -> tuple | None:
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()

    def state(self) -> dict:
        row = self._one(f"select {', '.join(STATE_KEYS)} from playerwire.sync_state where id = 1")
        return dict(zip(STATE_KEYS, row, strict=True)) if row else dict.fromkeys(STATE_KEYS)

    def set_state(self, **fields: Any) -> None:
        from psycopg import sql
        unknown = set(fields) - set(STATE_KEYS)
        if unknown:
            raise KeyError(f"unknown sync_state fields: {sorted(unknown)}")
        sets = sql.SQL(", ").join(sql.SQL("{} = {}").format(sql.Identifier(k), sql.Placeholder()) for k in fields)
        with self.conn.cursor() as cur:
            cur.execute("insert into playerwire.sync_state (id) values (1) on conflict (id) do nothing")
            cur.execute(sql.SQL("update playerwire.sync_state set {} where id = 1").format(sets), tuple(fields.values()))

    def current(self, brief_id: str) -> tuple[int, bool] | None:
        row = self._one("select version, deleted from playerwire.briefs where brief_id = %s for update", (brief_id,))
        return None if row is None else (int(row[0]), bool(row[1]))

    def live(self) -> dict[str, int]:
        with self.conn.cursor() as cur:
            cur.execute("select brief_id, version from playerwire.briefs where not deleted")
            return {r[0]: int(r[1]) for r in cur.fetchall()}

    def put_brief(self, row: dict, players: list[dict], payload: dict, now: datetime) -> None:
        from psycopg.types.json import Jsonb
        cols = [*BRIEF_COLUMNS, "payload", "synced_at", "deleted", "deleted_reason", "deleted_at"]
        vals = [*(row[c] for c in BRIEF_COLUMNS), Jsonb(payload), now, False, None, None]
        updates = ", ".join(f"{c} = excluded.{c}" for c in cols if c != "brief_id")
        with self.conn.cursor() as cur:
            cur.execute(f"insert into playerwire.briefs ({', '.join(cols)}) values ({', '.join(['%s'] * len(cols))}) "
                        f"on conflict (brief_id) do update set {updates}", vals)
            cur.execute("delete from playerwire.brief_players where brief_id = %s", (row["brief_id"],))
            if players:
                cur.executemany("insert into playerwire.brief_players (brief_id, pw_player_id, sleeper_id, gsis_id, role) "
                                "values (%s, %s, %s, %s, %s)",
                                [(row["brief_id"], p["pw_player_id"], p["sleeper_id"], p["gsis_id"], p["role"])
                                 for p in players])

    def put_tombstone(self, brief_id: str, version: int, reason: str, payload: dict, now: datetime) -> None:
        from psycopg.types.json import Jsonb
        with self.conn.cursor() as cur:
            cur.execute(
                """insert into playerwire.briefs (brief_id, version, status, payload, synced_at, deleted, deleted_reason,
                                                  deleted_at)
                   values (%s, %s, 'withdrawn', %s, %s, true, %s, %s)
                   on conflict (brief_id) do update set
                     version = excluded.version, status = 'withdrawn', headline = null, news = null, analysis = null,
                     verification_status = null, updated_at = null, evidence_url = null, evidence_publisher = null,
                     evidence_published_at = null, payload = excluded.payload, synced_at = excluded.synced_at,
                     deleted = true, deleted_reason = excluded.deleted_reason, deleted_at = excluded.deleted_at""",
                (brief_id, version, Jsonb(payload), now, reason, now))
            cur.execute("delete from playerwire.brief_players where brief_id = %s", (brief_id,))


# ------------------------------------------------------------------------------------------------ applying
def apply_upsert(store: Store, brief: dict, now: datetime, *, allow_synthetic: bool = False) -> str:
    """'applied' | 'stale' (a newer version, or a tombstone at least as new, is already here) | 'synthetic'."""
    if brief.get("synthetic") and not allow_synthetic:
        return "synthetic"
    row = brief_row(brief)
    cur = store.current(row["brief_id"])
    if cur is not None:
        version, deleted = cur
        if row["version"] < version or (deleted and row["version"] <= version):
            return "stale"
    store.put_brief(row, brief_players(brief), brief, now)
    return "applied"


def apply_delete(store: Store, tomb: dict, now: datetime) -> str:
    """'applied' | 'stale' (the row already holds a newer version: a brief restored after this withdrawal)."""
    brief_id, version = str(tomb["id"]), int(tomb["version"])
    cur = store.current(brief_id)
    if cur is not None and cur[0] > version:
        return "stale"
    store.put_tombstone(brief_id, version, str(tomb.get("reason") or "withdrawn"), tombstone_payload(tomb), now)
    return "applied"


class Syncer:
    def __init__(self, client: Client, store: Store, *, api_url: str = DEFAULT_API, page_limit: int = PAGE_LIMIT,
                 allow_synthetic: bool = False, max_bootstrap_attempts: int = 3,
                 clock: Callable[[], datetime] = utcnow, say: Callable[[str], None] = log) -> None:
        self.client, self.store, self.api_url = client, store, api_url
        self.page_limit, self.allow_synthetic = page_limit, allow_synthetic
        self.max_bootstrap_attempts, self.clock, self.say = max_bootstrap_attempts, clock, say

    def _snapshot(self) -> tuple[list[dict], str, str]:
        for attempt in range(1, self.max_bootstrap_attempts + 1):
            briefs: list[dict] = []
            cursor = None
            try:
                while True:
                    page = self.client.get("/v1/briefs", [("limit", self.page_limit), ("cursor", cursor)])
                    briefs.extend(page["data"])
                    if not page["has_more"]:
                        return briefs, page["sync_cursor"], page["snapshot_watermark"]
                    cursor = page["next_cursor"]
            except ApiError as e:
                if cursor is None or e.code not in RESYNC_CODES or attempt == self.max_bootstrap_attempts:
                    raise
                self.say(f"{e.code} on a later snapshot page (attempt {attempt}): restarting the snapshot")
        raise AssertionError("unreachable")

    def bootstrap(self) -> dict:
        briefs, sync_cursor, watermark = self._snapshot()
        now = self.clock()
        counts = {"briefs": 0, "synthetic": 0, "withdrawn_absent": 0, "watermark": watermark}
        with self.store.transaction():
            live = self.store.live()
            seen: set[str] = set()
            for b in briefs:
                if b.get("synthetic") and not self.allow_synthetic:
                    counts["synthetic"] += 1
                    continue
                row = brief_row(b)                       # the snapshot is the truth at its watermark: written as is
                self.store.put_brief(row, brief_players(b), b, now)
                seen.add(row["brief_id"])
                counts["briefs"] += 1
            for brief_id, version in sorted(live.items()):
                if brief_id not in seen:                 # withdrawn while we were not looking (or ineligible now)
                    self.store.put_tombstone(brief_id, version, ABSENT, {"id": brief_id, "version": version,
                                             "operation": "delete", "changed_at": now.isoformat(), "reason": ABSENT}, now)
                    counts["withdrawn_absent"] += 1
            self.store.set_state(sync_cursor=sync_cursor, snapshot_watermark=watermark, high_watermark=watermark,
                                 filter_signature=FILTER_SIGNATURE, bootstrapped_at=now, last_sync_at=now,
                                 last_error=None, last_error_at=None, api_url=self.api_url)
        self.say(f"bootstrap: {counts['briefs']} briefs at watermark {watermark}")
        return counts

    def apply_changes(self) -> dict:
        totals = {"pages": 0, "upserts": 0, "deletes": 0, "stale": 0, "synthetic": 0}
        while True:
            cursor = self.store.state()["sync_cursor"]
            page = self.client.get("/v1/brief-changes", [("cursor", cursor), ("limit", self.page_limit)])
            now = self.clock()
            with self.store.transaction():
                for change in page["data"]:
                    if change.get("operation") == "upsert":
                        r = apply_upsert(self.store, change["brief"], now, allow_synthetic=self.allow_synthetic)
                        totals["upserts" if r == "applied" else r] += 1
                    elif change.get("operation") == "delete":
                        r = apply_delete(self.store, change["tombstone"], now)
                        totals["deletes" if r == "applied" else r] += 1
                self.store.set_state(sync_cursor=page["next_cursor"], high_watermark=page.get("high_watermark"),
                                     last_sync_at=now, last_error=None, last_error_at=None)
            totals["pages"] += 1
            if not page["has_more"]:
                return totals

    def reset(self) -> None:
        with self.store.transaction():
            self.store.set_state(sync_cursor=None, snapshot_watermark=None, filter_signature=None)

    def sync_once(self) -> dict:
        result: dict[str, Any] = {"bootstrapped": False}
        st = self.store.state()
        if st["sync_cursor"] is None or st["filter_signature"] != FILTER_SIGNATURE:
            result["bootstrap"] = self.bootstrap()
            result["bootstrapped"] = True
        try:
            result["changes"] = self.apply_changes()
        except ApiError as e:
            if e.code not in RESYNC_CODES:
                raise
            self.say(f"{e.code}: {e.message} -> bootstrapping again")
            self.reset()
            result["bootstrap"] = self.bootstrap()
            result["bootstrapped"] = True
            result["resynced_after"] = e.code
            result["changes"] = self.apply_changes()
        return result


# ------------------------------------------------------------------------------------------------ the command line
def load_env() -> None:
    """``.env`` into the environment (the caller's environment wins), as sync_to_hosted.sh and the app read it."""
    env = ROOT / ".env"
    if not env.exists():
        return
    try:
        from dotenv import dotenv_values
    except ImportError:          # pragma: no cover - python-dotenv is a League Lab dependency
        return
    for k, v in dotenv_values(env).items():
        if v is not None and k not in os.environ:
            os.environ[k] = v


def _connect(dsn: str) -> Any:
    import psycopg
    return psycopg.connect(dsn, autocommit=True, connect_timeout=15, application_name="playerwire-sync")


def _record_error(dsn: str | None, message: str) -> None:
    if not dsn:
        return
    try:
        with _connect(dsn) as conn:
            PgStore(conn).set_state(last_error=message[:500], last_error_at=utcnow())
    except Exception as e:  # noqa: BLE001 - the database is what failed: say so, nothing more to do
        log(f"could not record the error in playerwire.sync_state ({e.__class__.__name__})")


def _settings() -> tuple[str, str | None, str | None]:
    api = (os.environ.get("PLAYERWIRE_API_URL") or DEFAULT_API).strip()
    if not api.startswith(("http://", "https://")):
        raise SystemExit(f"PLAYERWIRE_API_URL must be an http(s) URL, got {api!r}")
    return api, os.environ.get("PLAYERWIRE_API_KEY") or None, os.environ.get("PLAYERWIRE_HOSTED_URL") or None


def cmd_sync(args: argparse.Namespace) -> int:
    api, key, dsn = _settings()
    if not key:
        log("PLAYERWIRE_API_KEY is not set: only a --no-auth / preview PlayerWire server will answer")
    client = Client(http_transport(api), key)
    if args.dry_run:
        return _dry_run(client, api, dsn, args)
    if not dsn:
        log("PLAYERWIRE_HOSTED_URL is not set (the playerwire_writer DSN; docs/PLAYERWIRE.md § Set up)")
        return 2
    while True:
        rc = _sync_cycle(client, api, dsn, args)
        if args.once or rc == 2:
            return rc
        time.sleep(max(60, args.interval))


def _sync_cycle(client: Client, api: str, dsn: str, args: argparse.Namespace) -> int:
    import psycopg
    try:
        with _connect(dsn) as conn:
            who = conn.execute("select current_user").fetchone()[0]
            if who != WRITER_ROLE and not args.allow_other_role:
                log(f"connected as {who!r}, not {WRITER_ROLE!r}: the writer DSN must use the dedicated role "
                    "(docs/PLAYERWIRE.md § One writer); --allow-other-role for a local test database")
                return 2
            if not conn.execute("select pg_try_advisory_lock(%s)", (LOCK_KEY,)).fetchone()[0]:
                print(json.dumps({"skipped": "another playerwire sync holds the lock"}), flush=True)
                return 0
            t0 = time.monotonic()
            result = Syncer(client, PgStore(conn), api_url=api, page_limit=args.page_limit,
                            allow_synthetic=args.allow_synthetic).sync_once()
            result["seconds"] = round(time.monotonic() - t0, 2)
            print(json.dumps(result, default=str), flush=True)
            return 0
    except ApiError as e:
        log(str(e))
        _record_error(dsn, str(e))
        return 1
    except psycopg.Error as e:
        msg = f"database: {e.__class__.__name__}: {str(e).splitlines()[0] if str(e) else ''}"
        log(msg)
        _record_error(dsn, msg)
        return 1


def _dry_run(client: Client, api: str, dsn: str | None, args: argparse.Namespace) -> int:
    """The same run against a scratch copy in memory (the database's cursor and versions when it can be read):
    prints what would change, writes nothing anywhere."""
    store = MemoryStore()
    source = "empty (no PLAYERWIRE_HOSTED_URL): a bootstrap"
    if dsn:
        try:
            with _connect(dsn) as conn:
                pg = PgStore(conn)
                st = pg.state()
                with conn.cursor() as cur:
                    cur.execute("select brief_id, version, deleted from playerwire.briefs")
                    for brief_id, version, deleted in cur.fetchall():
                        store.briefs[brief_id] = {"brief_id": brief_id, "version": int(version), "deleted": bool(deleted)}
                store.set_state(**{k: st[k] for k in ("sync_cursor", "filter_signature")})
                source = f"the database's cursor and {len(store.briefs)} rows"
        except Exception as e:  # noqa: BLE001 - a dry run reads what it can
            source = f"empty (database not readable: {e.__class__.__name__}): a bootstrap"
    try:
        result = Syncer(client, store, api_url=api, page_limit=args.page_limit, allow_synthetic=args.allow_synthetic,
                        say=lambda _m: None).sync_once()
    except ApiError as e:
        log(str(e))
        return 1
    live = [r for r in store.briefs.values() if not r["deleted"] and "headline" in r]
    result.update({"dry_run": True, "started_from": source, "written": "nothing",
                   "briefs_after": len([r for r in store.briefs.values() if not r["deleted"]]),
                   "with_sleeper_id": sum(1 for r in live if r.get("primary_sleeper_id")),
                   "with_gsis_id_only": sum(1 for r in live if r.get("primary_gsis_id") and not r.get("primary_sleeper_id")),
                   "without_ids": sum(1 for r in live if not r.get("primary_sleeper_id") and not r.get("primary_gsis_id"))})
    print(json.dumps(result, default=str, indent=2), flush=True)
    return 0


def cmd_status(_args: argparse.Namespace) -> int:
    api, key, dsn = _settings()
    out: dict[str, Any] = {"api_url": api, "api_key_set": bool(key)}
    try:
        status, _h, _b = http_transport(api, timeout=5)("/health/live", {"Accept": "application/json"})
        out["api_live"] = status == 200
    except ApiError as e:
        out["api_live"], out["api_error"] = False, e.message
    if not dsn:
        out["database"] = "PLAYERWIRE_HOSTED_URL is not set"
        print(json.dumps(out, indent=2))
        return 2
    try:
        with _connect(dsn) as conn:
            row = conn.execute(
                """select count(*) filter (where not deleted), count(*) filter (where deleted),
                          max(published_at) filter (where not deleted),
                          count(*) filter (where not deleted and primary_sleeper_id is not null),
                          count(*) filter (where not deleted and primary_sleeper_id is null and primary_gsis_id is not null),
                          count(*) filter (where not deleted and primary_sleeper_id is null and primary_gsis_id is null)
                   from playerwire.briefs""").fetchone()
            out.update(dict(zip(("briefs", "withdrawn", "newest_published_at", "with_sleeper_id", "with_gsis_id_only",
                                 "without_ids"), row, strict=True)))
            st = PgStore(conn).state()
            st["sync_cursor"] = "set" if st["sync_cursor"] else None       # opaque and long: present or not
            out["sync_state"] = st
            out["connected_as"] = conn.execute("select current_user").fetchone()[0]
    except Exception as e:  # noqa: BLE001 - a status line
        out["database_error"] = f"{e.__class__.__name__}: {str(e).splitlines()[0] if str(e) else ''}"
        print(json.dumps(out, indent=2, default=str))
        return 1
    print(json.dumps(out, indent=2, default=str))
    return 0


def writer_url_template(admin_url: str) -> str:
    """The admin DSN with the writer's user and a password placeholder (never the secret itself)."""
    u = urllib.parse.urlsplit(admin_url)
    host = u.hostname or "<host>"
    netloc = f"{WRITER_ROLE}:<PLAYERWIRE_WRITER_PASSWORD>@{host}" + (f":{u.port}" if u.port else "")
    return urllib.parse.urlunsplit((u.scheme or "postgresql", netloc, u.path, u.query, ""))


def cmd_init_schema(args: argparse.Namespace) -> int:
    admin = args.admin_url or os.environ.get("LEAGUE_LAB_HOSTED_ADMIN_URL")
    if not admin:
        log("set LEAGUE_LAB_HOSTED_ADMIN_URL (the database owner's DSN) in .env, or pass --admin-url")
        return 2
    if not os.environ.get("PLAYERWIRE_WRITER_PASSWORD"):
        log("set PLAYERWIRE_WRITER_PASSWORD in .env (a long random password: openssl rand -hex 24)")
        return 2
    rc = subprocess.run(["psql", admin, "-v", "ON_ERROR_STOP=1", "-q", "-f", str(SCHEMA_SQL)], check=False).returncode
    if rc == 0:
        print(f"PLAYERWIRE_HOSTED_URL={writer_url_template(admin)}")
        print("(put that line in .env with the password filled in; the direct, non-pooler host is fine)")
    return rc


def main(argv: list[str] | None = None) -> int:
    load_env()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("sync", help="bootstrap if needed, then drain the changes")
    p.add_argument("--once", action="store_true", help="one cycle, then exit (launchd)")
    p.add_argument("--interval", type=int, default=900, help="seconds between cycles without --once (min 60)")
    p.add_argument("--dry-run", action="store_true", help="fetch and apply to a scratch copy in memory; write nothing")
    p.add_argument("--page-limit", type=int, default=PAGE_LIMIT)
    p.add_argument("--allow-synthetic", action="store_true", help="also write synthetic (fixture) briefs; tests only")
    p.add_argument("--allow-other-role", action="store_true",
                   help=f"connect as a role other than {WRITER_ROLE} (a local test database)")
    sub.add_parser("status", help="the replica's counts and the last run")
    p = sub.add_parser("init-schema", help="create / update schema playerwire and role playerwire_writer")
    p.add_argument("--admin-url", help="the database owner's DSN (default LEAGUE_LAB_HOSTED_ADMIN_URL)")
    args = parser.parse_args(argv)
    return {"sync": cmd_sync, "status": cmd_status, "init-schema": cmd_init_schema}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
