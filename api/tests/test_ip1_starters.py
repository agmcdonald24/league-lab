"""IP-1 (Wave I-P, fix round 2): "Starter unclear" -- the flag (``league_lab_api.starters.unclear``).

* 2026 week 5 on the database: Chicago, Seattle and Washington, both quarterbacks each, the listed one and the one who
  played, the sentence as a screen prints it;
* a week with no flag (week 1: no game before it; week 6: no listing yet);
* as of the week: week 4 flags Seattle from week 3's game and not Chicago, whose week-4 game (Keenum listed, no dropback)
  is the week itself;
* never raises: a missing relation, a failing read, a week out of range -> {};
* the pure part on hand-built rows; the cache is a registered memo region.
"""

from __future__ import annotations

import pandas as pd
import pytest
from league_lab import memo

from league_lab_api import starters as S

from .conftest import needs_db


@pytest.fixture(autouse=True)
def _fresh_cache():
    S._cache._entries.clear()
    yield
    S._cache._entries.clear()


@pytest.fixture
def su10(monkeypatch):
    """IQ-2: these tests pin su1.0 itself -- the trigger the screens keep where analytics.mart_starter_check is not
    built (a deploy before the nightly); with the mart, U1 replaces it (api/tests/test_iq2.py)."""
    monkeypatch.setattr(S, "check", lambda season, week: None)


@needs_db
def test_week_5_flags_chicago_seattle_and_washington(su10):
    f = S.unclear(2026, 5)
    assert {v["team"] for v in f.values()} == {"CHI", "SEA", "WAS"}
    assert len(f) == 6 and sorted(v["role"] for v in f.values()) == ["listed"] * 3 + ["played"] * 3
    sea = {v["role"]: (gid, v) for gid, v in f.items() if v["team"] == "SEA"}
    assert sea["listed"][1]["listed"] == "Drew Lock" and sea["played"][1]["played"] == "Sam Darnold"
    assert sea["listed"][0] == "00-0035704" and sea["played"][0] == "00-0034869"
    assert sea["listed"][1]["words"] == (
        "Starter unclear: Seattle lists Drew Lock as the starter, but he did not drop back once in week 4; Sam Darnold "
        "took most of the dropbacks. Our projections assume the listing: Lock as the starter, Darnold as his backup.")
    assert all("wrong" not in v["words"] for v in f.values())


@needs_db
def test_weeks_without_a_flag(su10):
    assert S.unclear(2026, 1) == {}          # no game before week 1
    assert S.unclear(2026, 6) == {}          # nflverse has not listed week 6's starters yet


@needs_db
def test_the_weeks_own_game_never_counts(su10):
    teams = {v["team"] for v in S.unclear(2026, 4).values()}
    assert "SEA" in teams                    # Lock listed, Darnold led week 3
    assert "CHI" not in teams                # Keenum led week 3; his week-4 game (no dropback) is the week itself


def test_never_raises(monkeypatch):
    assert S.unclear(2026, 0) == {} and S.unclear(2026, 23) == {} and S.unclear("x", 5) == {}
    monkeypatch.setattr(S, "missing_relations", lambda names: ["fct_player_game"])
    assert S.unclear(2026, 5) == {}

    def boom(*a, **k):
        raise RuntimeError("relation does not exist")
    monkeypatch.setattr(S, "missing_relations", lambda names: [])
    monkeypatch.setattr(S, "query", boom)
    assert S.unclear(2026, 5) == {}


def test_the_pure_part_and_the_cache(monkeypatch):
    listing = pd.DataFrame([{"team": "SEA", "listed_id": "lock", "game_id": "g4sea", "last_week": 4},
                            {"team": "BUF", "listed_id": "allen", "game_id": "g4buf", "last_week": 4},
                            {"team": "LA", "listed_id": "staff", "game_id": "g4la", "last_week": 4}])
    drop = pd.DataFrame([{"game_id": "g4sea", "team": "SEA", "gsis_id": "darnold", "dropbacks": 26.0},
                         {"game_id": "g4buf", "team": "BUF", "gsis_id": "allen", "dropbacks": 3.0},     # dropped back: no flag
                         {"game_id": "g4buf", "team": "BUF", "gsis_id": "backup", "dropbacks": 30.0},
                         {"game_id": "g4la", "team": "LA", "gsis_id": "b", "dropbacks": 20.0},
                         {"game_id": "g4la", "team": "LA", "gsis_id": "a", "dropbacks": 20.0}])          # a tie: the first id
    names = {"lock": "Drew Lock", "darnold": "Sam Darnold", "staff": "Matthew Stafford", "a": "Jimmy Garoppolo Jr."}
    f = S.flags_from(listing, drop, names)
    assert set(f) == {"lock", "darnold", "staff", "a"}
    assert f["a"]["role"] == "played" and f["staff"]["words"].startswith("Starter unclear: The Rams list Matthew Stafford")
    assert "Garoppolo as his backup" in f["a"]["words"]
    # the cache: one entry per (season, week) in a registered region; a second call reads no relation
    assert "starters" in memo.BUDGET.regions and S._cache.max_entries == 32
    calls = []
    monkeypatch.setattr(S, "missing_relations", lambda names_: [])
    monkeypatch.setattr(S, "query", lambda sql, params=(): calls.append(sql) or pd.DataFrame(columns=["team", "listed_id", "game_id", "last_week"]))
    assert S.unclear(2026, 7) == {} and S.unclear(2026, 7) == {}
    assert len(calls) == 2            # IQ-2: the mart's read (no row for the week), then the listing; the second call none
