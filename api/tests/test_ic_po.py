"""Wave I-C, the PO's integration pieces: a double header in dad's league (MFL 70587 plays twice in weeks 2, 4, 6–9,
11 and 13: both opponents on My Week), the spec's read-back naming the stat and the position of every bonus, the
MFL note reading the spec's words, and the scoring check without play-by-play (the `*_tds_10p` columns)."""

from __future__ import annotations

import pytest
from league_lab import anyleague as A
from league_lab import mfl_client as M
from league_lab import player_ids as PI

from .conftest import needs_db
from .test_i0b import IDS, MFL_FX

KEY = "mfl:70587"


@pytest.fixture(autouse=True)
def _mfl_fixtures(monkeypatch):
    monkeypatch.setenv(M.FIXTURES_ENV, str(MFL_FX))
    monkeypatch.setenv(PI.CSV_ENV, str(IDS))
    monkeypatch.setenv(M.YEAR_ENV, "2026")
    PI.reset()
    A._default = None
    yield
    PI.reset()
    A._default = None


def test_double_header_names_both_opponents():
    """Week 4 of 70587: Knight Train (roster 1) plays Big Mac Attack and Klaby Crew — `A.opponent` answers the first
    and carries the second in `also` (no solve: no database needed)."""
    opp = A.opponent(None, KEY, 1, 4, solve=False)
    assert opp is not None and opp["team_name"] == "Big Mac Attack"
    assert [o["team_name"] for o in opp["also"]] == ["Klaby Crew"]
    assert opp["matchup_id"] != opp["also"][0]["matchup_id"]
    one = A.opponent(None, KEY, 1, 1, solve=False)           # week 1: one game, no `also`
    assert one is not None and "also" not in one


@needs_db
def test_my_week_carries_the_double_header(client):
    r = client.get(f"/api/my-week?league={KEY}&team=1")
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    if d["week"] != 4:
        pytest.skip(f"the fixture's week is {d['week']}, not a double-header week")
    o = d["opponent"]
    assert o["team_name"] == "Big Mac Attack" and o["also"][0]["team_name"] == "Klaby Crew"
    assert o["lineup_value"] is not None and o["also"][0]["lineup_value"] is not None


def test_readback_names_stat_and_position():
    spec = A.league_spec(A.sleeper().league(KEY))
    rb = spec.readback()
    assert rb[0] == "TDs by distance 6 / 9 / 12 (0–9 / 10–39 / 40+ yards)"
    assert "1 pt per 10 rushing / receiving yards" in rb and "1 pt per 20 passing yards" in rb
    assert "+10 at 75 rushing (QB/WR/TE) / receiving (TE) · +10 at 100 rushing (RB) / receiving (RB/WR) · +10 at 250 passing" in rb
    assert any("return touchdowns are not projected" in a for a in spec.approximated)


def test_mfl_note_reads_the_spec():
    from league_lab_api import ondemand
    note = ondemand.mfl_scoring_note(A.sleeper().league(KEY))
    assert note.startswith("Lineup read as team QB, 2 RB, 3 WR/TE, team K, DEF.")
    assert "Sleeper bonus" not in note and "Not counted in the projections" not in note     # the old compiler's words
    assert "Return touchdowns are not projected" in note


@needs_db
def test_scoring_check_without_play_by_play_is_exact_on_the_ten_yard_cut(client):
    """`fct_player_game.*_tds_10p` (dbt, Wave I-C) make MFL's 0–9 / 10–39 / 40+ bands exact without `fct_play`:
    every player line matches; the misses left are defensive return touchdowns (no length on a DEF line)."""
    r = client.get(f"/api/league/scoring-check?league={KEY}&week=2")
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    if d["n"] == 0:
        pytest.skip(d["words"])
    assert d["within_1"] >= d["n"] - 2
    assert all(m["position"] == "DEF" for m in d["misses"])
