import gzip
import json
from datetime import date

import httpx
import pytest

from league_lab.cli import parse_seasons
from league_lab.http import FetchError, fetch_to_archive, read_meta
from league_lab.ingest.nflverse import current_nfl_season


def test_parse_seasons():
    assert parse_seasons("2025") == [2025]
    assert parse_seasons("2016-2018") == [2016, 2017, 2018]
    assert parse_seasons("2016,2018-2019, 2025") == [2016, 2018, 2019, 2025]
    assert parse_seasons(None) is None


def test_nfl_season_year_is_not_calendar_year():
    assert current_nfl_season(date(2026, 9, 25)) == 2026
    assert current_nfl_season(date(2027, 2, 1)) == 2026
    assert current_nfl_season(date(2027, 3, 1)) == 2027


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_writes_archive_and_meta_then_uses_conditional_request(tmp_path):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(dict(request.headers))
        if request.headers.get("if-none-match") == '"v1"':
            return httpx.Response(304)
        return httpx.Response(200, content=b"hello", headers={"ETag": '"v1"', "Last-Modified": "Mon, 01 Jan 2026 00:00:00 GMT"})

    path = tmp_path / "x" / "file.bin"
    with _client(handler) as c:
        first = fetch_to_archive("https://example.test/file.bin", path, client=c)
        assert first.status_code == 200 and not first.from_cache and path.read_bytes() == b"hello"
        assert read_meta(path)["etag"] == '"v1"'
        second = fetch_to_archive("https://example.test/file.bin", path, client=c)
        assert second.status_code == 304 and second.from_cache and second.content == b"hello"
    assert calls[1]["if-none-match"] == '"v1"'


def test_offline_replay_reads_gzip_archive(tmp_path):
    path = tmp_path / "state.json.gz"
    path.write_bytes(gzip.compress(json.dumps({"week": 3}).encode()))
    f = fetch_to_archive("https://example.test/state", path, offline=True)
    assert json.loads(f.content) == {"week": 3} and f.from_cache


def test_offline_without_archive_raises(tmp_path):
    with pytest.raises(FetchError):
        fetch_to_archive("https://example.test/missing", tmp_path / "missing.json", offline=True)


def test_transient_errors_retry_then_fail_cleanly(tmp_path, monkeypatch):
    from league_lab import http as http_mod
    monkeypatch.setattr(http_mod.time, "sleep", lambda s: None)
    attempts = {"n": 0}

    def handler(request):
        attempts["n"] += 1
        return httpx.Response(503)

    with _client(handler) as c, pytest.raises(FetchError):
        fetch_to_archive("https://example.test/flaky", tmp_path / "flaky.bin", client=c)
    assert attempts["n"] >= 2
    assert not (tmp_path / "flaky.bin").exists(), "a failed download must not leave a partial archive"


def test_markdown_table_formatting():
    from decimal import Decimal

    from league_lab.reports import md_table

    md = md_table(["a", "b", "c"], [(1, Decimal("2.50"), None), ("x|y", True, 3.14159)], limit=1)
    assert md.splitlines()[0] == "| a | b | c |"
    assert "| 1 | 2.5 | — |" in md
    assert "1 more rows in the CSV" in md
    assert md_table(["a"], []).startswith("_no rows_")
