"""N2: scripts/playerwire_sync.py — PlayerWire's briefs into the hosted `playerwire` schema (docs/PLAYERWIRE.md).

The API is a fake PlayerWire (`FakePlayerWire`: a change log, snapshot pages at a pinned watermark, change pages,
tombstones, expired cursors, 429 / 503 with Retry-After) answering through the script's transport seam, as
PlayerWire's own consumer tests drive its reference client. The database is the script's `MemoryStore` (the same
contract as `PgStore`, a transaction that raises rolls back). `test_pg_store_end_to_end` runs the same scenario on a
real Postgres when `LEAGUE_LAB_PLAYERWIRE_TEST_DSN` names one with the schema (scripts/init_playerwire_schema.sql);
it is skipped otherwise. No test touches the network.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import sys
import urllib.parse
from datetime import UTC, datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("playerwire_sync", ROOT / "scripts" / "playerwire_sync.py")
PS = importlib.util.module_from_spec(_spec)
sys.modules["playerwire_sync"] = PS
_spec.loader.exec_module(PS)

NOW = datetime(2026, 10, 3, 18, 0, tzinfo=UTC)


def player(pid: str, name: str, sleeper: str | None = None, gsis: str | None = None, pos: str = "WR") -> dict:
    ext = {k: v for k, v in (("sleeper", sleeper), ("gsis", gsis), ("espn", "1")) if v}
    return {"id": pid, "name": name, "position": pos, "external_ids": ext}


def brief(bid: str, version: int = 1, *, primary: dict | None = None, related: list[dict] | None = None,
          headline: str = "Jefferson (ankle) ruled out for Sunday", news: str = "Justin Jefferson will not play Sunday.",
          verification: str = "official", published: str = "2026-10-03T13:33:00Z", synthetic: bool = False,
          analysis: str | None = "The Vikings lean on Addison.") -> dict:
    """A brief shaped as handoff/contracts/brief.schema.json requires (every required key present)."""
    p = primary or player("pw_jj", "Justin Jefferson", "6794", "00-0036322")
    return {
        "id": bid, "version": version, "status": "published", "synthetic": synthetic, "primary_player": p,
        "related_players": related or [], "category": "game_status", "headline": headline, "news": news,
        "analysis": None if analysis is None else {"text": analysis, "author": "andrew", "method": "manual",
                                                     "created_at": published},
        "verification_status": verification, "event_time": None, "published_at": published, "updated_at": published,
        "claims": [{"id": "c1", "subject_player_id": p["id"], "type": "game_status", "value": "out", "assertion": "asserted",
                    "attribution": "team", "report_date": "2026-10-03", "game_id": None, "evidence_ids": ["e1"],
                    "game_date": "2026-10-05"}],
        "evidence": [{"id": "e1", "source_id": "vikings", "publisher": "Minnesota Vikings",
                      "url": "https://www.vikings.com/news/injury-report", "source_published_at": "2026-10-03T13:00:00Z",
                      "observed_at": "2026-10-03T13:05:00Z", "origin_group_id": None, "independence": "independent"},
                     {"id": "e2", "source_id": "x", "publisher": "Second", "url": "https://example.com/2",
                      "source_published_at": None, "observed_at": "2026-10-03T13:06:00Z", "origin_group_id": None,
                      "independence": "unknown"}],
        "sentence_support": [{"sentence_index": 0, "claim_ids": ["c1"]}],
    }


class FakePlayerWire:
    """A PlayerWire read API in memory: an append-only change log; `/v1/briefs` pages the live briefs at a pinned
    watermark; `/v1/brief-changes` pages the log after a `sync:<seq>` cursor. `forced` answers come first (FIFO)."""

    def __init__(self) -> None:
        self.log: list[dict] = []
        self.live: dict[str, dict] = {}
        self.expired_below = 0                 # a sync cursor below this seq -> 410 cursor_expired
        self.forced: list[tuple[int, dict, dict]] = []
        self.calls: list[str] = []
        self.auth: list[str | None] = []

    def publish(self, b: dict) -> None:
        self.live[b["id"]] = copy.deepcopy(b)
        self.log.append({"sequence": str(len(self.log) + 1), "operation": "upsert", "changed_at": b["updated_at"],
                         "brief": copy.deepcopy(b)})

    def withdraw(self, bid: str, reason: str = "withdrawn") -> None:
        version = self.live.pop(bid)["version"] + 1
        self.log.append({"sequence": str(len(self.log) + 1), "operation": "delete", "changed_at": "2026-10-03T15:00:00Z",
                         "tombstone": {"id": bid, "version": version, "operation": "delete",
                                       "changed_at": "2026-10-03T15:00:00Z", "reason": reason}})

    def force(self, status: int, body: dict | None = None, headers: dict | None = None) -> None:
        self.forced.append((status, headers or {}, body or {}))

    @staticmethod
    def _err(code: str) -> dict:
        return {"error": {"code": code, "message": code.replace("_", " "), "request_id": "r"}}

    def transport(self, target: str, headers: dict) -> tuple[int, dict, bytes]:
        self.calls.append(target)
        self.auth.append(headers.get("Authorization"))
        if self.forced:
            status, h, body = self.forced.pop(0)
            return status, h, json.dumps(body).encode()
        u = urllib.parse.urlsplit(target)
        q = dict(urllib.parse.parse_qsl(u.query))
        limit = int(q.get("limit", 50))
        if u.path == "/v1/briefs":
            if "cursor" in q:
                _snap, wm, off = q["cursor"].split(":")
                wm, off = int(wm), int(off)
            else:
                wm, off = len(self.log), 0
            items = sorted(self.live.values(), key=lambda b: b["id"])
            page = items[off:off + limit]
            more = off + limit < len(items)
            body = {"data": page, "has_more": more, "next_cursor": f"snap:{wm}:{off + limit}" if more else None,
                    "sync_cursor": f"sync:{wm}", "snapshot_watermark": str(wm)}
            return 200, {}, json.dumps(body).encode()
        if u.path == "/v1/brief-changes":
            seq = int(q["cursor"].split(":")[1])
            if seq < self.expired_below:
                return 410, {}, json.dumps(self._err("cursor_expired")).encode()
            page = self.log[seq:seq + limit]
            nxt = seq + len(page)
            body = {"data": page, "has_more": nxt < len(self.log), "next_cursor": f"sync:{nxt}",
                    "high_watermark": str(len(self.log))}
            return 200, {}, json.dumps(body).encode()
        return 404, {}, json.dumps(self._err("not_found")).encode()


def make(fake: FakePlayerWire, store=None, *, page_limit: int = 2, key: str | None = "pwk_test", sleeps=None, **kw):
    store = store if store is not None else PS.MemoryStore()
    client = PS.Client(fake.transport, key, sleep=(sleeps.append if sleeps is not None else (lambda _s: None)))
    return PS.Syncer(client, store, page_limit=page_limit, clock=lambda: NOW, say=lambda _m: None, **kw), store


def three(fake: FakePlayerWire) -> None:
    fake.publish(brief("b1"))
    fake.publish(brief("b2", primary=player("pw_ja", "Jordan Addison", "9756", None), headline="Addison set for more targets",
                       related=[player("pw_jj", "Justin Jefferson", "6794", "00-0036322")], verification="reported"))
    fake.publish(brief("b3", primary=player("pw_x", "Practice Squad Guy"), headline="Signed to the practice squad"))


# ------------------------------------------------------------------------------------------------ payload -> row
def test_brief_row_derives_the_display_columns_and_players():
    b = brief("b2", 3, primary=player("pw_ja", "Jordan Addison", " 9756 ", None),
              related=[player("pw_jj", "Justin Jefferson", "6794", "00-0036322"), player("pw_ja", "dup", "1")])
    row = PS.brief_row(b)
    assert row["brief_id"] == "b2" and row["version"] == 3 and row["status"] == "published"
    assert (row["pw_player_id"], row["primary_sleeper_id"], row["primary_gsis_id"]) == ("pw_ja", "9756", None)
    assert row["headline"].startswith("Jefferson") and row["news"] == "Justin Jefferson will not play Sunday."
    assert row["analysis"] == "The Vikings lean on Addison." and row["verification_status"] == "official"
    assert row["published_at"] == datetime(2026, 10, 3, 13, 33, tzinfo=UTC)
    # the first evidence item is the attribution: https only
    assert (row["evidence_url"], row["evidence_publisher"]) == ("https://www.vikings.com/news/injury-report", "Minnesota Vikings")
    assert PS.brief_row({**b, "evidence": [{**b["evidence"][0], "url": "http://insecure.example"}]})["evidence_url"] is None
    assert PS.brief_row({**b, "analysis": None})["analysis"] is None
    assert PS.brief_players(b) == [
        {"pw_player_id": "pw_ja", "sleeper_id": "9756", "gsis_id": None, "role": "primary"},
        {"pw_player_id": "pw_jj", "sleeper_id": "6794", "gsis_id": "00-0036322", "role": "related"}]


# ------------------------------------------------------------------------------------------------ bootstrap
def test_bootstrap_writes_every_page_and_the_cursor_in_one_commit():
    fake = FakePlayerWire()
    three(fake)
    s, store = make(fake)
    r = s.sync_once()
    assert r["bootstrapped"] and r["bootstrap"]["briefs"] == 3 and r["changes"]["pages"] == 1
    assert [c.split("?")[0] for c in fake.calls] == ["/v1/briefs", "/v1/briefs", "/v1/brief-changes"]   # 2 snapshot pages
    assert all(a == "Bearer pwk_test" for a in fake.auth)
    assert set(store.briefs) == {"b1", "b2", "b3"} and store.commits == 2    # the snapshot, then the (empty) change page
    st = store.state()
    assert st["sync_cursor"] == "sync:3" and st["snapshot_watermark"] == "3" and st["last_sync_at"] == NOW
    assert st["filter_signature"] == PS.FILTER_SIGNATURE and st["last_error"] is None
    assert store.briefs["b1"]["payload"] == brief("b1")                      # rule 6: the payload whole
    assert store.players["b2"][1] == {"pw_player_id": "pw_jj", "sleeper_id": "6794", "gsis_id": "00-0036322",
                                      "role": "related"}
    # nothing new: one change call, no snapshot
    fake.calls.clear()
    r = s.sync_once()
    assert not r["bootstrapped"] and r["changes"] == {"pages": 1, "upserts": 0, "deletes": 0, "stale": 0, "synthetic": 0}
    assert [c.split("?")[0] for c in fake.calls] == ["/v1/brief-changes"]


def test_synthetic_briefs_are_never_written_unless_allowed():
    fake = FakePlayerWire()
    fake.publish(brief("fx", synthetic=True))
    fake.publish(brief("real"))
    s, store = make(fake)
    assert s.sync_once()["bootstrap"]["synthetic"] == 1 and set(store.briefs) == {"real"}
    fake.publish(brief("fx2", synthetic=True))
    assert s.sync_once()["changes"]["synthetic"] == 1 and "fx2" not in store.briefs
    s2, store2 = make(fake, allow_synthetic=True)
    s2.sync_once()
    assert {"fx", "fx2"} <= set(store2.briefs)


# ------------------------------------------------------------------------------------------------ changes and versions
def test_changes_apply_in_order_and_never_replace_a_newer_version():
    fake = FakePlayerWire()
    fake.publish(brief("b1"))
    s, store = make(fake)
    s.sync_once()
    fake.publish(brief("b1", 2, headline="Jefferson (ankle) now doubtful"))      # a correction
    fake.publish(brief("b4", headline="New brief"))
    r = s.sync_once()["changes"]
    assert r["upserts"] == 2 and store.briefs["b1"]["version"] == 2
    assert store.briefs["b1"]["headline"] == "Jefferson (ankle) now doubtful" and "b4" in store.briefs
    # a re-delivered older version (a replayed page) is stale: the row keeps version 2
    with store.transaction():
        assert PS.apply_upsert(store, brief("b1", 1), NOW) == "stale"
        assert PS.apply_upsert(store, brief("b1", 2, headline="same version again"), NOW) == "applied"   # idempotent
    assert store.briefs["b1"]["version"] == 2
    # replaying the whole feed from the start changes nothing
    before = copy.deepcopy(store.briefs)
    store.set_state(sync_cursor="sync:0")
    s.sync_once()
    assert {k: v["version"] for k, v in store.briefs.items()} == {k: v["version"] for k, v in before.items()}


def test_a_tombstone_keeps_the_row_and_none_of_its_text():
    fake = FakePlayerWire()
    three(fake)
    s, store = make(fake)
    s.sync_once()
    fake.withdraw("b2", "unsupported")
    assert s.sync_once()["changes"]["deletes"] == 1
    row = store.briefs["b2"]
    assert row["deleted"] is True and row["deleted_reason"] == "unsupported" and row["version"] == 2
    assert row["status"] == "withdrawn" and row["deleted_at"] == NOW
    for col in ("headline", "news", "analysis", "evidence_url", "evidence_publisher", "verification_status"):
        assert row[col] is None, col
    assert row["payload"] == {"id": "b2", "version": 2, "operation": "delete", "changed_at": "2026-10-03T15:00:00Z",
                              "reason": "unsupported"}
    assert "Addison" not in json.dumps(row, default=str)                     # nothing of the text survives
    assert row["pw_player_id"] == "pw_ja" and "b2" not in store.players     # ids stay (status counts); no mentions
    # a late re-delivery of the withdrawn version cannot bring it back; a restored, newer version does
    with store.transaction():
        assert PS.apply_upsert(store, brief("b2", 1, primary=player("pw_ja", "Jordan Addison", "9756")), NOW) == "stale"
        assert PS.apply_upsert(store, brief("b2", 2, primary=player("pw_ja", "Jordan Addison", "9756")), NOW) == "stale"
        assert store.briefs["b2"]["deleted"]
        assert PS.apply_upsert(store, brief("b2", 3, primary=player("pw_ja", "Jordan Addison", "9756")), NOW) == "applied"
    assert store.briefs["b2"]["deleted"] is False and store.briefs["b2"]["deleted_reason"] is None
    # a tombstone older than the row (the brief was restored after it) is stale
    with store.transaction():
        assert PS.apply_delete(store, {"id": "b2", "version": 2, "reason": "withdrawn"}, NOW) == "stale"
    assert store.briefs["b2"]["deleted"] is False


def test_a_tombstone_for_a_brief_never_seen_is_kept_so_it_cannot_arrive_later():
    store = PS.MemoryStore()
    with store.transaction():
        assert PS.apply_delete(store, {"id": "ghost", "version": 4, "operation": "delete", "reason": "removed",
                                       "changed_at": "x"}, NOW) == "applied"
        assert PS.apply_upsert(store, brief("ghost", 4), NOW) == "stale"
    assert store.briefs["ghost"]["deleted"] and store.briefs["ghost"]["headline"] is None


# ------------------------------------------------------------------------------------------------ cursor after commit
def test_the_cursor_moves_only_with_a_committed_page():
    fake = FakePlayerWire()
    fake.publish(brief("b1"))
    s, store = make(fake, page_limit=1)
    s.sync_once()
    assert store.state()["sync_cursor"] == "sync:1"
    fake.publish(brief("b5"))
    fake.publish(brief("b6"))
    real = store.put_brief

    def broken(row, players, payload, now):
        if row["brief_id"] == "b6":
            raise RuntimeError("disk full")
        return real(row, players, payload, now)

    store.put_brief = broken                                                    # type: ignore[method-assign]
    with pytest.raises(RuntimeError):
        s.sync_once()
    # b5's page committed with its cursor; b6's page rolled back and its cursor never moved
    assert "b5" in store.briefs and "b6" not in store.briefs and store.state()["sync_cursor"] == "sync:2"
    store.put_brief = real                                                      # type: ignore[method-assign]
    assert s.sync_once()["changes"]["upserts"] == 1 and "b6" in store.briefs and store.state()["sync_cursor"] == "sync:3"


def test_a_failed_bootstrap_writes_nothing():
    fake = FakePlayerWire()
    three(fake)
    s, store = make(fake)
    store.set_state = lambda **_k: (_ for _ in ()).throw(RuntimeError("lost the connection"))  # type: ignore[method-assign]
    with pytest.raises(RuntimeError):
        s.bootstrap()
    assert store.briefs == {} and store.state()["sync_cursor"] is None


# ------------------------------------------------------------------------------------------------ resync
def test_an_expired_cursor_bootstraps_again_and_withdraws_what_the_snapshot_lost():
    fake = FakePlayerWire()
    three(fake)
    s, store = make(fake)
    s.sync_once()
    # while the Mac slept: b3 withdrawn and b1 corrected, and the cursor fell out of retention
    fake.live.pop("b3")
    fake.live["b1"] = brief("b1", 2, headline="Corrected")
    fake.log.extend([{"sequence": "4", "operation": "noop"}] * 2)
    fake.expired_below = 5
    r = s.sync_once()
    assert r["resynced_after"] == "cursor_expired" and r["bootstrapped"]
    assert r["bootstrap"]["withdrawn_absent"] == 1
    assert store.briefs["b3"]["deleted"] and store.briefs["b3"]["deleted_reason"] == PS.ABSENT
    assert store.briefs["b3"]["headline"] is None
    assert store.briefs["b1"]["version"] == 2 and store.briefs["b1"]["headline"] == "Corrected"
    assert store.state()["sync_cursor"] == "sync:5"


def test_a_filter_mismatch_resyncs_too():
    fake = FakePlayerWire()
    fake.publish(brief("b1"))
    s, store = make(fake)
    s.sync_once()
    fake.force(409, FakePlayerWire._err("cursor_filter_mismatch"))
    assert s.sync_once()["resynced_after"] == "cursor_filter_mismatch"
    assert store.state()["sync_cursor"] == "sync:1"


def test_a_resync_code_on_a_later_snapshot_page_restarts_the_snapshot():
    fake = FakePlayerWire()
    three(fake)
    s, store = make(fake)
    real = fake.transport
    state = {"n": 0}

    def flaky(target, headers):
        if target.startswith("/v1/briefs") and "cursor=" in target and state["n"] == 0:
            state["n"] += 1
            return 410, {}, json.dumps(FakePlayerWire._err("cursor_expired")).encode()
        return real(target, headers)

    s.client.transport = flaky
    assert s.sync_once()["bootstrap"]["briefs"] == 3
    assert [c.split("?")[0] for c in fake.calls].count("/v1/briefs") == 3      # page 1, (410), page 1, page 2


def test_a_wrong_filter_signature_bootstraps():
    fake = FakePlayerWire()
    fake.publish(brief("b1"))
    s, store = make(fake)
    store.set_state(sync_cursor="sync:1", filter_signature='{"player_id": ["x"]}')
    assert s.sync_once()["bootstrapped"]


# ------------------------------------------------------------------------------------------------ the client
def test_429_and_503_wait_retry_after_then_retry():
    fake = FakePlayerWire()
    fake.publish(brief("b1"))
    sleeps: list[float] = []
    s, store = make(fake, sleeps=sleeps)
    fake.force(429, FakePlayerWire._err("rate_limited"), {"Retry-After": "7"})
    fake.force(503, FakePlayerWire._err("not_ready"), {"retry-after": "500"})
    fake.force(503, FakePlayerWire._err("unavailable"), {})
    s.sync_once()
    assert sleeps == [7, 120, 1] and "b1" in store.briefs


def test_auth_failures_and_outages_raise_with_the_code():
    fake = FakePlayerWire()
    s, store = make(fake, key=None)
    fake.force(401, FakePlayerWire._err("missing_credentials"))
    with pytest.raises(PS.ApiError) as e:
        s.sync_once()
    assert e.value.status == 401 and e.value.code == "missing_credentials" and fake.auth == [None]
    assert store.state()["sync_cursor"] is None
    c = PS.Client(lambda _t, _h: (503, {}, b"down"), None, max_retries=2, sleep=lambda _s: None)
    with pytest.raises(PS.ApiError) as e:
        c.get("/v1/briefs")
    assert e.value.status == 503 and e.value.message == "down"


def test_an_unreachable_api_is_an_api_error():
    t = PS.http_transport("http://127.0.0.1:9", timeout=0.5)            # discard port: nothing listens
    with pytest.raises(PS.ApiError) as e:
        t("/health/live", {})
    assert e.value.code == "unreachable"


# ------------------------------------------------------------------------------------------------ the command line
def test_writer_url_template_never_carries_a_secret():
    u = PS.writer_url_template("postgresql://neondb_owner:s3cret@ep-x-123.us-east-2.aws.neon.tech/neondb?sslmode=require")
    assert u == ("postgresql://playerwire_writer:<PLAYERWIRE_WRITER_PASSWORD>@ep-x-123.us-east-2.aws.neon.tech/neondb"
                 "?sslmode=require")
    assert "s3cret" not in u


def test_sync_without_the_writer_dsn_is_a_configuration_error(monkeypatch, capsys):
    monkeypatch.setattr(PS, "load_env", lambda: None)
    monkeypatch.delenv("PLAYERWIRE_HOSTED_URL", raising=False)
    monkeypatch.setenv("PLAYERWIRE_API_URL", "http://127.0.0.1:9")
    assert PS.main(["sync", "--once"]) == 2
    monkeypatch.setenv("PLAYERWIRE_API_URL", "ftp://x")
    with pytest.raises(SystemExit):
        PS.main(["sync", "--once"])


def test_dry_run_writes_nothing_and_reports(monkeypatch, capsys):
    fake = FakePlayerWire()
    three(fake)
    monkeypatch.setattr(PS, "load_env", lambda: None)
    monkeypatch.delenv("PLAYERWIRE_HOSTED_URL", raising=False)
    monkeypatch.setattr(PS, "http_transport", lambda _base, timeout=30: fake.transport)
    assert PS.main(["sync", "--once", "--dry-run"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["dry_run"] and out["written"] == "nothing" and out["bootstrap"]["briefs"] == 3
    assert (out["with_sleeper_id"], out["with_gsis_id_only"], out["without_ids"]) == (2, 0, 1)


def test_the_schema_sql_keeps_the_marts_and_the_briefs_apart():
    sql = (ROOT / "scripts" / "init_playerwire_schema.sql").read_text().lower()
    code = "\n".join(line.split("--")[0] for line in sql.splitlines())       # statements, not the comments
    assert "analytics." not in code and "ops." not in code                      # nothing in playerwire reads the marts
    assert "create schema if not exists playerwire authorization playerwire_writer" in code
    assert "grant select on all tables in schema playerwire to league_lab_app" in code
    assert "alter default privileges in schema playerwire grant select on tables to league_lab_app" in code
    assert "\\getenv writer_pw playerwire_writer_password" in code              # the password never on argv
    assert "briefs_withdrawn_text_gone" in code
    sync = (ROOT / "scripts" / "sync_to_hosted.sh").read_text()
    assert "playerwire" not in sync                                             # the nightly never names it


@pytest.mark.skipif(not os.environ.get("LEAGUE_LAB_PLAYERWIRE_TEST_DSN"),
                    reason="LEAGUE_LAB_PLAYERWIRE_TEST_DSN not set (a Postgres with scripts/init_playerwire_schema.sql applied)")
def test_pg_store_end_to_end():
    import psycopg
    with psycopg.connect(os.environ["LEAGUE_LAB_PLAYERWIRE_TEST_DSN"], autocommit=True) as conn:
        conn.execute("truncate playerwire.brief_players, playerwire.briefs")
        conn.execute("update playerwire.sync_state set sync_cursor = null, filter_signature = null")
        fake = FakePlayerWire()
        three(fake)
        s, store = make(fake, PS.PgStore(conn))
        assert s.sync_once()["bootstrap"]["briefs"] == 3
        fake.withdraw("b2", "unsupported")
        fake.publish(brief("b1", 2, headline="Corrected"))
        r = s.sync_once()["changes"]
        assert (r["upserts"], r["deletes"]) == (1, 1)
        rows = {b: (v, d, h, n, p) for b, v, d, h, n, p in conn.execute(
            "select brief_id, version, deleted, headline, news, payload from playerwire.briefs").fetchall()}
        assert rows["b1"][:3] == (2, False, "Corrected") and rows["b1"][4]["headline"] == "Corrected"
        assert rows["b2"][1:4] == (True, None, None) and rows["b2"][4]["reason"] == "unsupported"
        assert conn.execute("select count(*) from playerwire.brief_players where brief_id = 'b2'").fetchone()[0] == 0
        assert conn.execute("select sync_cursor from playerwire.sync_state").fetchone()[0] == "sync:5"
        # the table refuses a withdrawn row with text
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute("update playerwire.briefs set headline = 'x' where brief_id = 'b2'")
        # a failure mid-page rolls the page and its cursor back
        fake.publish(brief("b7"))
        real = store.put_brief
        store.put_brief = lambda *a: (_ for _ in ()).throw(RuntimeError("boom"))  # type: ignore[method-assign]
        with pytest.raises(RuntimeError):
            s.sync_once()
        assert conn.execute("select count(*) from playerwire.briefs where brief_id = 'b7'").fetchone()[0] == 0
        assert conn.execute("select sync_cursor from playerwire.sync_state").fetchone()[0] == "sync:5"
        store.put_brief = real                                                   # type: ignore[method-assign]
        assert s.sync_once()["changes"]["upserts"] == 1
