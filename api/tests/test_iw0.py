"""PO (Wave I-W, 2026-10-10): the night the first trade evaluation after a publication waited 30 s for a pooled
connection and came back a 500. No database needed (the release gate runs this file).

* a pool that has no connection within ``db.POOL_WAIT_S`` is ``db.Busy`` -> 503 "busy" in words, never a 500;
* a 500 names the kind of error (the exception's class) and never its text;
* the publish refreshes the planner's statistics of the tables it restores, in both paths, inside the transaction;
* the post-deploy check prints the kind / code of a failed answer."""
from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path

import pytest
from psycopg_pool import PoolTimeout

from league_lab_api import db, main

ROOT = Path(__file__).resolve().parents[2]


class _NoConnection:
    def connection(self, *a, **k):
        raise PoolTimeout("couldn't get a connection after 12.00 sec")

    def get_stats(self):
        return {"pool_size": 4, "pool_available": 0, "requests_waiting": 3, "connections_ms": 1}


def test_a_pool_with_no_connection_is_busy_in_words(monkeypatch):
    monkeypatch.setattr(db, "pool", lambda: _NoConnection())
    with pytest.raises(db.Busy):
        db._run("select 1", ())
    assert issubclass(db.Busy, db.DataNotReady) and db.POOL_WAIT_S <= 15
    r = asyncio.run(main._busy(None, db.Busy("busy")))
    body = json.loads(r.body)
    assert r.status_code == 503 and body["code"] == "busy" and "busy right now" in body["detail"]
    assert r.headers["retry-after"] == "5"


def test_a_500_names_its_kind_and_never_its_text():
    r = asyncio.run(main._server_error(None, ValueError("secret text 123")))
    body = json.loads(r.body)
    assert r.status_code == 500 and body["kind"] == "ValueError"
    assert "secret" not in r.body.decode() and body["status"] == "/api/status"


def test_the_publish_refreshes_statistics_in_both_paths():
    s = (ROOT / "scripts" / "sync_to_hosted.sh").read_text()
    assert s.count("execute format('analyze %I.%I', r.nspname, r.relname);") == 2
    swap = s[s.index("swap_stream() {"):s.index("restore_retrying swap_stream")]
    drop = s[s.index("drop_stream() {"):s.index("restore_retrying drop_stream")]
    for stream in (swap, drop):                       # after the tables and the grants, inside the stream (one transaction)
        assert stream.index("grant select on all tables in schema ops") < stream.index("analyze %I.%I")


def test_the_check_prints_the_kind_of_a_failure():
    spec = importlib.util.spec_from_file_location("post_deploy_check_iw0", ROOT / "scripts" / "post_deploy_check.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    assert mod._why({"error": "Something broke on our side.", "kind": "PoolTimeout"}).startswith("[PoolTimeout] Something broke")
    assert mod._why({"error": "busy right now", "code": "busy"}) == "[busy] busy right now"
    assert mod._why({"error": "plain"}) == "plain" and mod._why("text") == "text"
