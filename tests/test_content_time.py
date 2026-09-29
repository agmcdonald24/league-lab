"""Content time (B6 follow-up): a partition's "loaded" time is when its bytes were fetched from the
source, whether they come from the network or from the archive (``--offline``), so a database
rebuilt from the archive every night (GitHub Actions) reports the same times as one that loaded
everything live (the Mac). No database needed."""

import contextlib
import functools
import hashlib
import json
import os
from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import polars as pl

from league_lab import manifest
from league_lab.http import fetch_to_archive, read_meta
from league_lab.ingest import nflverse

T_ARCHIVED = datetime(2026, 9, 26, 3, 6, 11, 123456, tzinfo=UTC)


def _archive(path, data: bytes, fetched_at: datetime | None = T_ARCHIVED, etag='"v1"'):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    if fetched_at is not None:
        meta = {"url": "https://example.test/x", "etag": etag, "last_modified": None,
                "fetched_at": fetched_at.isoformat(), "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
        path.with_name(path.name + ".meta.json").write_text(json.dumps(meta))


def _client(status: int, content: bytes = b"", etag: str | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, content=content, headers={"ETag": etag} if etag else {})
    return httpx.Client(transport=httpx.MockTransport(handler))


# ------------------------------------------------------------------------------ http: Fetched.fetched_at
def test_offline_replay_carries_the_archive_fetch_time(tmp_path):
    path = tmp_path / "teams.parquet"
    _archive(path, b"bytes")
    assert fetch_to_archive("https://example.test/x", path, offline=True).fetched_at == T_ARCHIVED


def test_offline_replay_without_a_sidecar_uses_the_file_time(tmp_path):
    path = tmp_path / "pbp_2016.parquet"          # mirrored with curl: no .meta.json
    _archive(path, b"bytes", fetched_at=None)
    os.utime(path, (T_ARCHIVED.timestamp(), T_ARCHIVED.timestamp()))
    assert fetch_to_archive("https://example.test/x", path, offline=True).fetched_at == T_ARCHIVED


def test_live_download_is_now_and_a_replay_reproduces_it_exactly(tmp_path):
    path = tmp_path / "injuries_2026.parquet"
    before = datetime.now(UTC)
    with _client(200, b"new report", '"v2"') as c:
        live = fetch_to_archive("https://example.test/x", path, client=c)
    assert before <= live.fetched_at <= datetime.now(UTC)
    assert read_meta(path)["fetched_at"] == live.fetched_at.isoformat()
    assert fetch_to_archive("https://example.test/x", path, offline=True).fetched_at == live.fetched_at


def test_unchanged_answers_keep_the_content_time(tmp_path):
    path = tmp_path / "state.json"
    _archive(path, b"same")
    os.utime(path, (1_000_000_000, 1_000_000_000))
    meta_before = read_meta(path)
    with _client(304) as c:                        # conditional request answered "not modified"
        f = fetch_to_archive("https://example.test/x", path, client=c)
    assert f.status_code == 304 and f.fetched_at == T_ARCHIVED and read_meta(path) == meta_before
    with _client(200, b"same", '"v9"') as c:       # same bytes, new ETag (a re-upload; Sleeper: no 304 at all)
        f = fetch_to_archive("https://example.test/x", path, client=c, conditional=False)
    meta = read_meta(path)
    assert f.fetched_at == T_ARCHIVED and meta["fetched_at"] == T_ARCHIVED.isoformat()
    assert meta["etag"] == '"v9"' and meta["checked_at"] > meta["fetched_at"]
    assert path.stat().st_mtime == 1_000_000_000   # the file itself was not rewritten
    with _client(200, b"changed", '"v10"') as c:   # new bytes: a new content time
        f = fetch_to_archive("https://example.test/x", path, client=c, conditional=False)
    assert f.fetched_at > T_ARCHIVED and read_meta(path)["fetched_at"] == f.fetched_at.isoformat()


# ------------------------------------------------------------------------------ manifest: source_partition.loaded_at
class _Cursor:
    def __init__(self, log):
        self.log = log

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self.log.append((" ".join(sql.split()), params))

    def fetchone(self):
        return (42,)


class _Conn:
    def __init__(self):
        self.log = []

    def cursor(self):
        return _Cursor(self.log)

    def transaction(self):
        return contextlib.nullcontext()

    def commit(self):
        pass

    def rollback(self):
        pass


def _partition_insert(conn):
    rows = [(sql, p) for sql, p in conn.log if sql.startswith("insert into ops.source_partition")]
    assert len(rows) <= 1
    return rows[0] if rows else None


def test_source_partition_loaded_at_is_the_records_fetch_time():
    conn = _Conn()
    manifest.record_manifest(conn, manifest.LoadRecord("nflverse", "teams", "all", fetched_at=T_ARCHIVED, row_count=36))
    sql, params = _partition_insert(conn)
    assert "coalesce(%s, now())" in sql and "loaded_at=excluded.loaded_at" in sql and params[-1] == T_ARCHIVED
    conn = _Conn()                                 # no fetch time at all (never the case for a fetched file): now()
    manifest.record_manifest(conn, manifest.LoadRecord("nflverse", "teams", "all"))
    assert _partition_insert(conn)[1][-1] is None
    conn = _Conn()                                 # an unchanged or failed attempt never moves the partition state
    manifest.record_manifest(conn, manifest.LoadRecord("nflverse", "teams", "all", status="skipped_unchanged", fetched_at=datetime.now(UTC)))
    assert _partition_insert(conn) is None


# ------------------------------------------------------------------------------ the loader end to end (database calls stubbed)
def _run_teams_load(tmp_path, monkeypatch, *, offline: bool, client=None):
    captured = []
    settings = SimpleNamespace(raw_dir=tmp_path, nflverse_base_url="https://example.test", ff_playerids_url="",
                               seasons_start=2016, pbp_columns="core")
    monkeypatch.setattr(nflverse, "get_settings", lambda: settings)
    monkeypatch.setattr(nflverse, "get_partition_state", lambda *a: None)
    monkeypatch.setattr(nflverse, "downcast_to_existing", lambda conn, schema, table, df: df)
    monkeypatch.setattr(nflverse, "ensure_table", lambda *a, **k: None)
    monkeypatch.setattr(nflverse, "replace_partition", lambda conn, schema, table, df, where: df.height)
    monkeypatch.setattr(nflverse, "record_manifest", lambda conn, rec: captured.append(rec))
    if client is not None:
        monkeypatch.setattr(nflverse, "fetch_to_archive", functools.partial(fetch_to_archive, client=client))
    rec = nflverse.load_dataset(_Conn(), nflverse.DATASETS["teams"], None, offline=offline)
    assert rec.status == "success" and captured == [rec]
    return rec


def _teams_parquet(tmp_path) -> bytes:
    f = tmp_path / "t.parquet"
    pl.DataFrame({"team_abbr": ["PIT", "PHI"], "team_name": ["Steelers", "Eagles"], "team_conf": ["AFC", "NFC"],
                  "team_division": ["AFC North", "NFC East"]}).write_parquet(f)
    return f.read_bytes()


def test_offline_load_propagates_the_archive_time_to_the_partition(tmp_path, monkeypatch):
    _archive(tmp_path / "nflverse" / "teams" / "teams_colors_logos.parquet", _teams_parquet(tmp_path))
    rec = _run_teams_load(tmp_path, monkeypatch, offline=True)
    assert rec.fetched_at == T_ARCHIVED           # what record_manifest writes as source_partition.loaded_at


def test_live_load_of_new_content_is_stamped_now(tmp_path, monkeypatch):
    before = datetime.now(UTC)
    with _client(200, _teams_parquet(tmp_path), '"v1"') as c:
        rec = _run_teams_load(tmp_path, monkeypatch, offline=False, client=c)
    assert before <= rec.fetched_at <= datetime.now(UTC)
    assert read_meta(tmp_path / "nflverse" / "teams" / "teams_colors_logos.parquet")["fetched_at"] == rec.fetched_at.isoformat()


# ------------------------------------------------------------------------------ the caption on every page
def test_freshness_caption_is_eastern_and_labelled(monkeypatch):
    import sys
    from datetime import date
    from pathlib import Path

    import pandas as pd

    app = str(Path(__file__).resolve().parents[1] / "app")
    sys.path.insert(0, app)
    try:
        from lib import db as app_db
        from lib import ui

        captions = []
        monkeypatch.setattr(ui, "st", SimpleNamespace(caption=captions.append, warning=lambda *a: None))
        monkeypatch.setattr(app_db, "missing_relations", lambda names: list(names))

        def fake_query(sql, params=()):
            if "group by source" in sql:
                return pd.DataFrame({"source": ["nflverse", "sleeper"], "last_loaded": [T_ARCHIVED, None], "failures": [0, 0]})
            if "mart_coverage" in sql:
                return pd.DataFrame({"season": [2026], "through_game_date": [date(2026, 9, 28)], "through_reg_week": [4],
                                     "league_scored_weeks": [3]})
            return pd.DataFrame({"loaded": [T_ARCHIVED]})
        monkeypatch.setattr(ui, "query", fake_query)
        ui.freshness_banner()
    finally:
        sys.path.remove(app)
    # 2026-09-26 03:06 UTC is Friday 11:06 PM in New York (EDT)
    assert "**nflverse** loaded Fri Sep 25, 11:06 PM ET" in captions[0] and "**sleeper** loaded never" in captions[0]
