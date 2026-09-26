"""Sleeper ingestion.

Traverses the league's ``previous_league_id`` chain and loads, per league-season:
league, users, rosters, matchups (per week), transactions (per week/round), drafts and
picks, traded picks, playoff brackets. Also the NFL state and the full player directory
(cached at most once per day, plan §4).

Raw tables keep the full JSON payload (``payload jsonb``) plus a handful of promoted
columns that models key on. All Sleeper IDs are stored as text (they exceed 2^53).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import psycopg
from psycopg.types.json import Jsonb

from ..config import get_settings
from ..db import ensure_table, upsert_rows
from ..http import Fetched, FetchError, fetch_to_archive, read_archive, read_meta
from ..manifest import LoadRecord, get_partition_state, record_manifest

log = logging.getLogger(__name__)
SOURCE = "sleeper"
MAX_WEEKS = 18
PLAYER_DIRECTORY_MAX_AGE = timedelta(hours=20)

# --------------------------------------------------------------------------- raw DDL
TABLES: dict[str, dict[str, Any]] = {
    "sleeper_league": {
        "columns": [
            ("league_id", "text"), ("season", "text"), ("name", "text"), ("status", "text"),
            ("previous_league_id", "text"), ("draft_id", "text"), ("total_rosters", "integer"),
            ("sport", "text"), ("season_type", "text"), ("payload", "jsonb"), ("fetched_at", "timestamptz"),
        ],
        "pk": ["league_id"],
    },
    "sleeper_league_user": {
        "columns": [
            ("league_id", "text"), ("user_id", "text"), ("display_name", "text"), ("team_name", "text"),
            ("is_owner", "boolean"), ("avatar", "text"), ("payload", "jsonb"), ("fetched_at", "timestamptz"),
        ],
        "pk": ["league_id", "user_id"],
    },
    "sleeper_roster": {
        "columns": [
            ("league_id", "text"), ("roster_id", "integer"), ("owner_id", "text"), ("co_owners", "text[]"),
            ("players", "text[]"), ("starters", "text[]"), ("reserve", "text[]"), ("taxi", "text[]"),
            ("settings", "jsonb"), ("metadata", "jsonb"), ("payload", "jsonb"), ("fetched_at", "timestamptz"),
        ],
        "pk": ["league_id", "roster_id"],
    },
    "sleeper_matchup": {
        "columns": [
            ("league_id", "text"), ("week", "integer"), ("roster_id", "integer"), ("matchup_id", "integer"),
            ("points", "double precision"), ("custom_points", "double precision"),
            ("starters", "text[]"), ("starters_points", "double precision[]"), ("players", "text[]"),
            ("players_points", "jsonb"), ("payload", "jsonb"), ("fetched_at", "timestamptz"),
        ],
        "pk": ["league_id", "week", "roster_id"],
    },
    "sleeper_transaction": {
        "columns": [
            ("league_id", "text"), ("week", "integer"), ("transaction_id", "text"), ("type", "text"),
            ("status", "text"), ("created", "bigint"), ("status_updated", "bigint"), ("creator", "text"),
            ("roster_ids", "integer[]"), ("consenter_ids", "integer[]"), ("adds", "jsonb"), ("drops", "jsonb"),
            ("draft_picks", "jsonb"), ("waiver_budget", "jsonb"), ("settings", "jsonb"), ("metadata", "jsonb"),
            ("payload", "jsonb"), ("fetched_at", "timestamptz"),
        ],
        "pk": ["league_id", "transaction_id"],
    },
    "sleeper_draft": {
        "columns": [
            ("draft_id", "text"), ("league_id", "text"), ("season", "text"), ("type", "text"), ("status", "text"),
            ("start_time", "bigint"), ("settings", "jsonb"), ("draft_order", "jsonb"),
            ("slot_to_roster_id", "jsonb"), ("metadata", "jsonb"), ("payload", "jsonb"), ("fetched_at", "timestamptz"),
        ],
        "pk": ["draft_id"],
    },
    "sleeper_draft_pick": {
        "columns": [
            ("draft_id", "text"), ("pick_no", "integer"), ("round", "integer"), ("draft_slot", "integer"),
            ("roster_id", "integer"), ("picked_by", "text"), ("player_id", "text"), ("is_keeper", "boolean"),
            ("metadata", "jsonb"), ("payload", "jsonb"), ("fetched_at", "timestamptz"),
        ],
        "pk": ["draft_id", "pick_no"],
    },
    "sleeper_traded_pick": {
        "columns": [
            ("league_id", "text"), ("season", "text"), ("round", "integer"), ("roster_id", "integer"),
            ("owner_id", "integer"), ("previous_owner_id", "integer"), ("payload", "jsonb"), ("fetched_at", "timestamptz"),
        ],
        "pk": ["league_id", "season", "round", "roster_id"],
    },
    "sleeper_bracket": {
        "columns": [
            ("league_id", "text"), ("bracket_type", "text"), ("m", "integer"), ("r", "integer"),
            ("t1", "integer"), ("t2", "integer"), ("w", "integer"), ("l", "integer"), ("p", "integer"),
            ("payload", "jsonb"), ("fetched_at", "timestamptz"),
        ],
        "pk": ["league_id", "bracket_type", "m"],
    },
    "sleeper_player": {
        "columns": [
            ("player_id", "text"), ("first_name", "text"), ("last_name", "text"), ("full_name", "text"),
            ("position", "text"), ("fantasy_positions", "text[]"), ("team", "text"), ("status", "text"),
            ("active", "boolean"), ("injury_status", "text"), ("number", "integer"), ("years_exp", "integer"),
            ("age", "integer"), ("birth_date", "text"), ("gsis_id", "text"), ("espn_id", "text"), ("yahoo_id", "text"),
            ("sportradar_id", "text"), ("rotowire_id", "text"), ("payload", "jsonb"), ("fetched_at", "timestamptz"),
        ],
        "pk": ["player_id"],
    },
    "sleeper_state": {
        "columns": [
            ("sport", "text"), ("season", "text"), ("season_type", "text"), ("week", "integer"), ("leg", "integer"),
            ("display_week", "integer"), ("previous_season", "text"), ("season_start_date", "text"),
            ("payload", "jsonb"), ("fetched_at", "timestamptz"),
        ],
        "pk": ["sport"],
    },
}


def ensure_tables(conn: psycopg.Connection) -> None:
    for name, spec in TABLES.items():
        ensure_table(conn, "raw", name, spec["columns"], spec["pk"])
    conn.commit()


# --------------------------------------------------------------------------- helpers
def _as_int(v: Any) -> int | None:
    try:
        return int(v) if v is not None and v != "" else None
    except (TypeError, ValueError):
        return None


def _as_text_list(v: Any) -> list[str] | None:
    if v is None:
        return None
    return [str(x) for x in v]


def _as_int_list(v: Any) -> list[int] | None:
    if v is None:
        return None
    out = []
    for x in v:
        i = _as_int(x)
        if i is not None:
            out.append(i)
    return out


def _jsonb(v: Any) -> Jsonb | None:
    return Jsonb(v) if v is not None else None


@dataclass
class SleeperRun:
    league_id: str
    offline: bool = False
    force: bool = False
    include_players: bool = True
    results: list[LoadRecord] | None = None

    def __post_init__(self) -> None:
        self.results = []


class SleeperIngester:
    def __init__(self, conn: psycopg.Connection, run: SleeperRun, client: httpx.Client | None = None):
        self.conn = conn
        self.run = run
        self.s = get_settings()
        self.client = client or httpx.Client(
            timeout=httpx.Timeout(self.s.http_timeout_seconds, connect=30.0),
            headers={"User-Agent": "league-lab/0.1"},
            follow_redirects=True,
            trust_env=True,
        )
        self.archive = self.s.raw_dir / "sleeper"

    # ---- fetch + load skeleton -------------------------------------------------
    def _url(self, path: str) -> str:
        return f"{self.s.sleeper_base_url}/{path.lstrip('/')}"

    def _fetch_json(self, path: str, archive_rel: str, offline: bool | None = None) -> tuple[Any, Fetched]:
        f = fetch_to_archive(
            self._url(path),
            self.archive / archive_rel,
            conditional=False,  # Sleeper does not serve ETags; we compare checksums instead
            offline=self.run.offline if offline is None else offline,
            client=self.client,
            compress=True,
        )
        return json.loads(f.content.decode("utf-8")), f

    def _load(self, dataset: str, partition_key: str, path: str, archive_rel: str, build_rows, table: str,
              where: dict[str, Any], key: list[str], offline: bool | None = None) -> LoadRecord:
        """Fetch one partition and replace it in ``raw.<table>`` transactionally."""
        rec = LoadRecord(source=SOURCE, dataset=dataset, partition_key=partition_key, source_url=self._url(path))
        try:
            payload, fetched = self._fetch_json(path, archive_rel, offline=offline)
        except FetchError as exc:
            rec.status, rec.error = "failed", str(exc)
            record_manifest(self.conn, rec)
            self.conn.commit()
            log.warning("%s %s: %s", dataset, partition_key, exc)
            self.run.results.append(rec)
            return rec
        rec.fetched_at, rec.checksum_sha256, rec.file_path = fetched.fetched_at, fetched.checksum, str(fetched.path)
        prior = get_partition_state(self.conn, SOURCE, dataset, partition_key)
        if prior and prior["checksum_sha256"] == rec.checksum_sha256 and not self.run.force:
            rec.status, rec.row_count = "skipped_unchanged", prior["row_count"]
            record_manifest(self.conn, rec)
            self.conn.commit()
            self.run.results.append(rec)
            return rec
        try:
            rows = build_rows(payload, fetched.fetched_at)
            with self.conn.transaction():
                with self.conn.cursor() as cur:
                    if where:
                        cond = " and ".join(f"{k} = %s" for k in where)
                        cur.execute(f"delete from raw.{table} where {cond}", list(where.values()))
                    else:
                        cur.execute(f"truncate raw.{table}")
                n = upsert_rows(self.conn, "raw", table, rows, key)
                rec.row_count = n
                record_manifest(self.conn, rec)
            self.conn.commit()
        except Exception as exc:
            self.conn.rollback()
            rec.status, rec.error = "failed", f"{type(exc).__name__}: {exc}"
            record_manifest(self.conn, rec)
            self.conn.commit()
            log.exception("load failed for %s %s", dataset, partition_key)
        self.run.results.append(rec)
        return rec

    # ---- endpoints ---------------------------------------------------------------
    def load_state(self) -> dict[str, Any]:
        def rows(p, ts):
            return [{
                "sport": "nfl", "season": p.get("season"), "season_type": p.get("season_type"),
                "week": _as_int(p.get("week")), "leg": _as_int(p.get("leg")), "display_week": _as_int(p.get("display_week")),
                "previous_season": p.get("previous_season"), "season_start_date": p.get("season_start_date"),
                "payload": _jsonb(p), "fetched_at": ts,
            }]
        self._load("state", "nfl", "state/nfl", "state/nfl.json.gz", rows, "sleeper_state", {"sport": "nfl"}, ["sport"])
        meta_path = self.archive / "state/nfl.json.gz"
        if meta_path.exists():
            return json.loads(read_archive(meta_path))
        return {}

    def load_league(self, league_id: str) -> dict[str, Any] | None:
        captured: dict[str, Any] = {}

        def rows(p, ts):
            captured.update(p)
            return [{
                "league_id": str(p["league_id"]), "season": p.get("season"), "name": p.get("name"),
                "status": p.get("status"), "previous_league_id": p.get("previous_league_id"),
                "draft_id": p.get("draft_id"), "total_rosters": _as_int(p.get("total_rosters")),
                "sport": p.get("sport"), "season_type": p.get("season_type"), "payload": _jsonb(p), "fetched_at": ts,
            }]
        rec = self._load("league", league_id, f"league/{league_id}", f"{league_id}/league.json.gz", rows,
                         "sleeper_league", {"league_id": league_id}, ["league_id"])
        if rec.status in ("success", "skipped_unchanged") and not captured:
            # unchanged: read from archive for chain traversal
            captured = json.loads(read_archive(self.archive / f"{league_id}/league.json.gz"))
        return captured or None

    def load_users(self, league_id: str) -> None:
        def rows(p, ts):
            return [{
                "league_id": league_id, "user_id": str(u["user_id"]), "display_name": u.get("display_name"),
                "team_name": (u.get("metadata") or {}).get("team_name"), "is_owner": bool(u.get("is_owner")),
                "avatar": u.get("avatar"), "payload": _jsonb(u), "fetched_at": ts,
            } for u in p]
        self._load("users", league_id, f"league/{league_id}/users", f"{league_id}/users.json.gz", rows,
                   "sleeper_league_user", {"league_id": league_id}, ["league_id", "user_id"])

    def load_rosters(self, league_id: str) -> None:
        def rows(p, ts):
            return [{
                "league_id": league_id, "roster_id": _as_int(r["roster_id"]), "owner_id": r.get("owner_id"),
                "co_owners": _as_text_list(r.get("co_owners")), "players": _as_text_list(r.get("players")),
                "starters": _as_text_list(r.get("starters")), "reserve": _as_text_list(r.get("reserve")),
                "taxi": _as_text_list(r.get("taxi")), "settings": _jsonb(r.get("settings")),
                "metadata": _jsonb(r.get("metadata")), "payload": _jsonb(r), "fetched_at": ts,
            } for r in p]
        self._load("rosters", league_id, f"league/{league_id}/rosters", f"{league_id}/rosters.json.gz", rows,
                   "sleeper_roster", {"league_id": league_id}, ["league_id", "roster_id"])

    def load_matchups(self, league_id: str, week: int) -> LoadRecord:
        def rows(p, ts):
            out = []
            for m in p or []:
                sp = m.get("starters_points")
                out.append({
                    "league_id": league_id, "week": week, "roster_id": _as_int(m["roster_id"]),
                    "matchup_id": _as_int(m.get("matchup_id")), "points": m.get("points"),
                    "custom_points": m.get("custom_points"), "starters": _as_text_list(m.get("starters")),
                    "starters_points": [float(x) if x is not None else None for x in sp] if sp is not None else None,
                    "players": _as_text_list(m.get("players")), "players_points": _jsonb(m.get("players_points")),
                    "payload": _jsonb(m), "fetched_at": ts,
                })
            return out
        return self._load("matchups", f"{league_id}:{week}", f"league/{league_id}/matchups/{week}",
                          f"{league_id}/matchups/week_{week:02d}.json.gz", rows, "sleeper_matchup",
                          {"league_id": league_id, "week": week}, ["league_id", "week", "roster_id"])

    def load_transactions(self, league_id: str, week: int) -> LoadRecord:
        def rows(p, ts):
            return [{
                "league_id": league_id, "week": _as_int(t.get("leg")) or week, "transaction_id": str(t["transaction_id"]),
                "type": t.get("type"), "status": t.get("status"), "created": t.get("created"),
                "status_updated": t.get("status_updated"), "creator": t.get("creator"),
                "roster_ids": _as_int_list(t.get("roster_ids")), "consenter_ids": _as_int_list(t.get("consenter_ids")),
                "adds": _jsonb(t.get("adds")), "drops": _jsonb(t.get("drops")), "draft_picks": _jsonb(t.get("draft_picks")),
                "waiver_budget": _jsonb(t.get("waiver_budget")), "settings": _jsonb(t.get("settings")),
                "metadata": _jsonb(t.get("metadata")), "payload": _jsonb(t), "fetched_at": ts,
            } for t in p or []]
        return self._load("transactions", f"{league_id}:{week}", f"league/{league_id}/transactions/{week}",
                          f"{league_id}/transactions/week_{week:02d}.json.gz", rows, "sleeper_transaction",
                          {"league_id": league_id, "week": week}, ["league_id", "transaction_id"])

    def load_drafts(self, league_id: str) -> list[str]:
        draft_ids: list[str] = []

        def rows(p, ts):
            out = []
            for d in p or []:
                draft_ids.append(str(d["draft_id"]))
                out.append({
                    "draft_id": str(d["draft_id"]), "league_id": league_id, "season": d.get("season"),
                    "type": d.get("type"), "status": d.get("status"), "start_time": d.get("start_time"),
                    "settings": _jsonb(d.get("settings")), "draft_order": _jsonb(d.get("draft_order")),
                    "slot_to_roster_id": _jsonb(d.get("slot_to_roster_id")), "metadata": _jsonb(d.get("metadata")),
                    "payload": _jsonb(d), "fetched_at": ts,
                })
            return out
        rec = self._load("drafts", league_id, f"league/{league_id}/drafts", f"{league_id}/drafts.json.gz", rows,
                         "sleeper_draft", {"league_id": league_id}, ["draft_id"])
        if not draft_ids and rec.status in ("success", "skipped_unchanged"):
            draft_ids = [str(d["draft_id"]) for d in json.loads(read_archive(self.archive / f"{league_id}/drafts.json.gz"))]
        return draft_ids

    def load_draft_picks(self, league_id: str, draft_id: str) -> None:
        def rows(p, ts):
            return [{
                "draft_id": draft_id, "pick_no": _as_int(k["pick_no"]), "round": _as_int(k.get("round")),
                "draft_slot": _as_int(k.get("draft_slot")), "roster_id": _as_int(k.get("roster_id")),
                "picked_by": k.get("picked_by"), "player_id": k.get("player_id"), "is_keeper": k.get("is_keeper"),
                "metadata": _jsonb(k.get("metadata")), "payload": _jsonb(k), "fetched_at": ts,
            } for k in p or []]
        self._load("draft_picks", draft_id, f"draft/{draft_id}/picks", f"{league_id}/draft_{draft_id}_picks.json.gz",
                   rows, "sleeper_draft_pick", {"draft_id": draft_id}, ["draft_id", "pick_no"])

    def load_traded_picks(self, league_id: str) -> None:
        def rows(p, ts):
            return [{
                "league_id": league_id, "season": str(t.get("season")), "round": _as_int(t.get("round")),
                "roster_id": _as_int(t.get("roster_id")), "owner_id": _as_int(t.get("owner_id")),
                "previous_owner_id": _as_int(t.get("previous_owner_id")), "payload": _jsonb(t), "fetched_at": ts,
            } for t in p or []]
        self._load("traded_picks", league_id, f"league/{league_id}/traded_picks", f"{league_id}/traded_picks.json.gz",
                   rows, "sleeper_traded_pick", {"league_id": league_id}, ["league_id", "season", "round", "roster_id"])

    def load_bracket(self, league_id: str, bracket_type: str) -> None:
        def rows(p, ts):
            return [{
                "league_id": league_id, "bracket_type": bracket_type, "m": _as_int(b.get("m")), "r": _as_int(b.get("r")),
                "t1": _as_int(b.get("t1")) if not isinstance(b.get("t1"), dict) else None,
                "t2": _as_int(b.get("t2")) if not isinstance(b.get("t2"), dict) else None,
                "w": _as_int(b.get("w")), "l": _as_int(b.get("l")), "p": _as_int(b.get("p")),
                "payload": _jsonb(b), "fetched_at": ts,
            } for b in p or []]
        self._load(f"{bracket_type}_bracket", league_id, f"league/{league_id}/{bracket_type}_bracket",
                   f"{league_id}/{bracket_type}_bracket.json.gz", rows, "sleeper_bracket",
                   {"league_id": league_id, "bracket_type": bracket_type}, ["league_id", "bracket_type", "m"])

    def load_players(self) -> None:
        """Full NFL player directory (~5 MB). Fetched at most once per PLAYER_DIRECTORY_MAX_AGE."""
        path = self.archive / "players/nfl.json.gz"
        meta = read_meta(path)
        offline = self.run.offline
        if meta and not self.run.force and not offline and path.exists():
            age = datetime.now(UTC) - datetime.fromisoformat(meta["fetched_at"])
            if age < PLAYER_DIRECTORY_MAX_AGE:
                log.info("player directory is %s old; replaying archive instead of re-downloading", age)
                offline = True
        self._load_players_inner(offline=offline)

    def _load_players_inner(self, offline: bool | None = None) -> None:
        def rows(p, ts):
            out = []
            for pid, pl_ in p.items():
                if not isinstance(pl_, dict):
                    continue
                out.append({
                    "player_id": str(pid), "first_name": pl_.get("first_name"), "last_name": pl_.get("last_name"),
                    "full_name": pl_.get("full_name") or " ".join(x for x in [pl_.get("first_name"), pl_.get("last_name")] if x),
                    "position": pl_.get("position"), "fantasy_positions": _as_text_list(pl_.get("fantasy_positions")),
                    "team": pl_.get("team"), "status": pl_.get("status"), "active": pl_.get("active"),
                    "injury_status": pl_.get("injury_status"), "number": _as_int(pl_.get("number")),
                    "years_exp": _as_int(pl_.get("years_exp")), "age": _as_int(pl_.get("age")),
                    "birth_date": pl_.get("birth_date"), "gsis_id": (pl_.get("gsis_id") or "").strip() or None,
                    "espn_id": str(pl_["espn_id"]) if pl_.get("espn_id") is not None else None,
                    "yahoo_id": str(pl_["yahoo_id"]) if pl_.get("yahoo_id") is not None else None,
                    "sportradar_id": pl_.get("sportradar_id"), "rotowire_id": str(pl_["rotowire_id"]) if pl_.get("rotowire_id") is not None else None,
                    "payload": _jsonb(pl_), "fetched_at": ts,
                })
            return out
        self._load("players", "nfl", "players/nfl", "players/nfl.json.gz", rows, "sleeper_player", {}, ["player_id"],
                   offline=offline)

    # ---- orchestration -------------------------------------------------------------
    def league_chain(self, league_id: str) -> list[dict[str, Any]]:
        """Load each league in the previous_league_id chain, newest first."""
        chain: list[dict[str, Any]] = []
        seen: set[str] = set()
        current: str | None = league_id
        # Sleeper marks "no previous league" as "0" (older leagues) or null (newer ones)
        while current and current not in seen and current != "0" and len(chain) < 25:
            seen.add(current)
            league = self.load_league(current)
            if not league:
                break
            chain.append(league)
            current = league.get("previous_league_id")
        return chain

    def weeks_to_fetch(self, league: dict[str, Any], state: dict[str, Any]) -> range:
        settings = league.get("settings") or {}
        status = league.get("status")
        if status == "complete":
            last = _as_int(settings.get("last_scored_leg")) or MAX_WEEKS
            return range(1, min(MAX_WEEKS, last) + 1)
        current = _as_int(state.get("display_week")) or _as_int(state.get("week")) or 1
        if str(state.get("season")) != str(league.get("season")):
            return range(1, MAX_WEEKS + 1)
        return range(1, min(MAX_WEEKS, max(current, 1)) + 1)

    def run_all(self) -> list[LoadRecord]:
        ensure_tables(self.conn)
        state = self.load_state()
        chain = self.league_chain(self.run.league_id)
        for league in chain:
            lid = str(league["league_id"])
            log.info("league %s season %s (%s)", lid, league.get("season"), league.get("status"))
            self.load_users(lid)
            self.load_rosters(lid)
            for wk in self.weeks_to_fetch(league, state):
                self.load_matchups(lid, wk)
                self.load_transactions(lid, wk)
            for did in self.load_drafts(lid):
                self.load_draft_picks(lid, did)
            self.load_traded_picks(lid)
            self.load_bracket(lid, "winners")
            self.load_bracket(lid, "losers")
        if self.run.include_players:
            self.load_players()
        return self.run.results


def ingest_sleeper(conn: psycopg.Connection, league_id: str | None = None, *, offline: bool = False,
                   force: bool = False, include_players: bool = True) -> list[LoadRecord]:
    """Ingest one or more league chains. ``league_id`` may be a comma-separated list; the default
    comes from LEAGUE_LAB_SLEEPER_LEAGUE_ID (also comma-separable) so several leagues can share a
    database — every model is keyed by league_id."""
    ids = [x.strip() for x in (league_id or get_settings().sleeper_league_id).split(",") if x.strip()]
    results: list[LoadRecord] = []
    for i, lid in enumerate(ids):
        run = SleeperRun(league_id=lid, offline=offline, force=force,
                         include_players=include_players and i == len(ids) - 1)
        results += SleeperIngester(conn, run).run_all()
    return results
