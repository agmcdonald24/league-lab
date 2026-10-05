"""IL-4 (Wave I-L): Sleeper's player directory trimmed at the load (`league_lab.sleeper_client`), and the console's line
for it (`memo.directory_words`). No database, no network: an injected fetch and a temporary disk copy."""

from __future__ import annotations

import json
import sys

import pytest

from league_lab import memo
from league_lab import sleeper_client as SC

# a row as Sleeper sends it (raw.sleeper_player's payload keys, 2026-09-26): 53 fields, nested metadata
FULL = {
    "active": True, "age": 26, "birth_city": None, "birth_country": None, "birth_date": "2000-01-02", "birth_state": None,
    "college": "Somewhere State", "competitions": [], "depth_chart_order": 1, "depth_chart_position": "QB",
    "espn_id": 4361741, "fantasy_data_id": 23189, "fantasy_positions": ["QB"], "first_name": "Jalen", "full_name": "Jalen Test",
    "gsis_id": "00-0036999", "hashtag": "#jalentest-NFL-KC-1", "height": "75", "high_school": "Some High (Town, TX)",
    "injury_body_part": "Ankle", "injury_notes": None, "injury_start_date": None, "injury_status": "Questionable",
    "kalshi_id": "abc", "last_name": "Test", "metadata": {"channel_id": "1", "rookie_year": "2022"},
    "news_updated": 1759500000000, "number": 1, "oddsjam_id": "X", "opta_id": None, "pandascore_id": None,
    "player_id": "9001", "player_shard": "a1f", "position": "QB", "practice_description": None,
    "practice_participation": None, "rotowire_id": 15000, "rotoworld_id": None, "search_first_name": "jalen",
    "search_full_name": "jalentest", "search_last_name": "test", "search_rank": 12, "sport": "nfl",
    "sportradar_id": "uuid", "stats_id": None, "status": "Active", "swish_id": 1, "team": "KC", "team_abbr": None,
    "team_changed_at": None, "weight": "220", "yahoo_id": 33000, "years_exp": 4,
}


def _directory() -> dict:
    other = {**FULL, "player_id": "9002", "first_name": "Sam", "full_name": "Sam Other", "gsis_id": None,
             "injury_status": None, "injury_body_part": None, "depth_chart_order": None, "team": "KC"}
    return {"9001": dict(FULL), "9002": other}


def _client(fetch=None, **kw) -> SC.Sleeper:
    calls: list[str] = []

    def f(path):
        calls.append(path)
        return json.loads(json.dumps(_directory()))
    c = SC.Sleeper(fixtures=None, fetch=fetch or f, cache_path=kw.pop("cache_path", None), **kw)
    c._calls = calls  # noqa: SLF001 - the test's own counter
    return c


def test_rows_keep_only_the_fields_read():
    d = _client().players()
    assert set(d) == {"9001", "9002"}
    a, b = d["9001"], d["9002"]
    assert set(a) <= set(SC.DIRECTORY_FIELDS) and len(SC.DIRECTORY_FIELDS) == 15
    for f in SC.DIRECTORY_FIELDS:                       # every kept field keeps its value; get() answers as before
        assert a.get(f) == FULL[f]
        assert b.get(f) == (None if f in ("gsis_id", "injury_status", "injury_body_part", "depth_chart_order") else
                            {**FULL, "player_id": "9002", "first_name": "Sam", "full_name": "Sam Other"}[f])
    assert "metadata" not in a and "hashtag" not in a and "yahoo_id" not in a
    assert "gsis_id" not in b                           # a null is left out: get() answers None all the same


def test_one_shared_read_only_copy_with_interned_text():
    c = _client()
    d1, d2 = c.players(), c.players()
    assert d1 is d2 and isinstance(d1, dict) and isinstance(d1, SC.Directory)   # no copy per call
    assert d1["9001"]["team"] is d1["9002"]["team"]                              # one "KC" for the directory
    assert d1["9001"]["player_id"] is next(k for k in d1 if k == "9001")          # the key and the row's id: one string
    assert d1["9001"]["team"] is sys.intern("KC")
    for mutate in (lambda: d1.__setitem__("x", {}), lambda: d1.pop("9001"), lambda: d1.update({}),
                   lambda: d1.setdefault("x", {}), lambda: d1.clear(), lambda: d1.__delitem__("9001")):
        with pytest.raises(TypeError, match="read only"):
            mutate()
    merged = dict(d1)                                   # a reader that adds rows copies it (Router.players)
    merged["mfl:1"] = {"player_id": "mfl:1"}
    assert "mfl:1" not in d1


def test_the_parse_trims_each_row_as_it_goes_and_is_idempotent():
    text = json.dumps(_directory())
    d = SC.loads_directory(text)
    assert isinstance(d, SC.Directory) and set(d["9001"]) <= set(SC.DIRECTORY_FIELDS)
    again = SC.trim_directory(d)
    assert again == d and again["9001"] is d["9001"]    # a trimmed row is kept as it is
    assert SC.loads_directory("null") is None and SC.trim_directory([1]) == [1]


def test_the_disk_copy_is_written_trimmed_and_an_old_full_copy_is_trimmed_at_read(tmp_path):
    c = _client(cache_path=tmp_path)
    c.players()
    on_disk = json.loads((tmp_path / SC.PLAYERS_FILE).read_text())
    assert set(on_disk["9001"]) <= set(SC.DIRECTORY_FIELDS)                       # the refresh keeps the trimmed shape
    (tmp_path / SC.PLAYERS_FILE).write_text(json.dumps(_directory()))            # a copy written before IL-4
    fresh = SC.Sleeper(fixtures=None, fetch=lambda p: pytest.fail("the disk copy is fresh"), cache_path=tmp_path)
    d = fresh.players()
    assert set(d["9001"]) <= set(SC.DIRECTORY_FIELDS) and isinstance(d, SC.Directory)


def test_fixture_mode_and_the_refresh_after_a_day_stay_trimmed(tmp_path):
    (tmp_path / "players_nfl.json").write_text(json.dumps(_directory()))
    t = {"now": 1000.0}
    c = SC.Sleeper(fixtures=tmp_path, clock=lambda: t["now"], wall=lambda: t["now"],
                   bucket=SC.TokenBucket(300, clock=lambda: t["now"]))
    d1 = c.players()
    assert set(d1["9001"]) <= set(SC.DIRECTORY_FIELDS)
    t["now"] += SC.TTL_S["players"] + 1                 # a day later: read again, trimmed again
    d2 = c.players()
    assert d2 is not d1 and set(d2["9001"]) <= set(SC.DIRECTORY_FIELDS) and c.calls == 2


def test_directory_info_and_the_console_words():
    c = _client()
    assert c.directory_info() == {"loaded": False, "rows": 0, "fields": 0, "mb": 0.0, "kept": 15}
    c.players()
    info = c.directory_info()
    assert info["loaded"] and info["rows"] == 2 and info["fields"] == 15 and info["mb"] >= 0
    words = memo.directory_words({"directory": {"loaded": True, "rows": 12229, "fields": 15, "mb": 8.6}})
    assert words == "Sleeper's player directory: 12,229 players, 15 fields, 8.6 MB (outside the caches' budget)."
    assert memo.directory_words({"directory": {"loaded": False}}).endswith("not read yet (the first league opened reads it).")
    assert memo.directory_words({}) == "Sleeper's player directory: not reported by this server."


def test_the_trimmed_directory_is_a_quarter_of_the_full_one():
    """At Sleeper's size (the synthetic directory scripts/measure_memory.py --synthetic-directory writes): the brief's
    target is under 12 MB as `/api/status` counts it (`memo.sizeof`, the unit of `outside_mb`)."""
    import importlib.util
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("measure_memory", root / "scripts" / "measure_memory.py")
    mm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mm)
    fx = json.loads((root / "api" / "tests" / "fixtures" / "sleeper" / "players_nfl.json").read_text())
    text = json.dumps(mm.synthetic_directory(fx))
    full = memo.sizeof({"/players/nfl": (0, 0, "players", json.loads(text))}) / 1048576
    kept = memo.sizeof({"/players/nfl": (0, 0, "players", SC.loads_directory(text))}) / 1048576
    assert full > 30 and kept < 12 and kept < full / 3, (full, kept)
