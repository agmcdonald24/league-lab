"""JB-2 (Wave J-B): a close call says when Sleeper's pre-kickoff numbers lean the other way (sleeper_lean, both My Week
paths); the thresholds of the tally sentence; sl1.1 — a snapshot fetched after either player's kickoff, or a game
already started, says nothing, a Sunday pair priced on Friday still shows; a lean that
cannot be read is no line; no number of the answer moves."""

from __future__ import annotations

import copy

import pandas as pd
import pytest
from league_lab import clock

from league_lab_api import sleeper_lean as SL

from .conftest import SCRUBS, needs_db

T = pd.Timestamp
FRIDAY, SATURDAY = T("2026-10-10T12:00:00Z"), "2026-10-10T16:00:00Z"
THURSDAY_NIGHT, SUNDAY = T("2026-10-09T00:15:00Z"), T("2026-10-11T17:00:00Z")


def _snap(ids, fetched=FRIDAY, kick=SUNDAY) -> dict:
    return {g: {"fetched_at": fetched, "kickoff_at": kick} for g in ids}


def _answer() -> dict:
    cards = [{"slot": "FLEX2", "gsis_id": "B", "player_name": "Denzel Boston", "alt_gsis_id": "J", "alt_name": "Justin Jefferson",
              "margin": 0.01, "status": "close", "strength": "coin flip"},
             {"slot": "RB2", "gsis_id": "H", "player_name": "Omarion Hampton", "alt_gsis_id": "C", "alt_name": "Jacory Croskey-Merritt",
              "margin": 2.9, "status": "set", "strength": "lean"}]
    full = [{"gsis_id": "B", "market_points": 8.91}, {"gsis_id": "J", "market_points": 13.82},
            {"gsis_id": "H", "market_points": 11.25}, {"gsis_id": "C", "market_points": 11.64}]
    return {"week": 5, "season": 2026, "cards": cards, "lineup_full": full, "lineup_value": 98.19,
            "actions": [{"kind": "close", "cards": [0], "action": "Start Boston ahead of Jefferson for now.", "gain": None}],
            "more_actions": [], "review": [{"kind": "no_clear_upgrade", "cards": [1], "words": "…"}]}


def test_the_tally_sentence_and_its_threshold():
    assert SL.tally_words({"n": 13, "ours": 4, "sleeper": 8}) == (
        "This season, on the 13 close calls where we have disagreed, Sleeper was right 8 times, we 4.")
    assert SL.tally_words({"n": 10, "ours": 9, "sleeper": 1}).endswith("Sleeper was right 1 time, we 9.")
    assert SL.tally_words({"n": 9, "ours": 4, "sleeper": 5}) is None          # under 10 graded: the lean alone
    assert SL.tally_words(None) is None
    assert SL.lean_words("Justin Jefferson", {"n": 6, "ours": 2, "sleeper": 4}) == "Sleeper's numbers lean to Justin Jefferson."


def test_only_a_close_call_sleeper_reads_the_other_way():
    a = _answer()
    found = SL.leans(a["cards"], {"B": 8.91, "J": 13.82, "H": 11.25, "C": 11.64})
    assert list(found) == [0] and found[0]["name"] == "Justin Jefferson"      # the set / lean call (RB2) is not close
    assert SL.leans(a["cards"], {"B": 13.82, "J": 8.91}) == {}                 # Sleeper agrees with us
    assert SL.leans(a["cards"], {"B": 10.0, "J": 10.02}) == {}                 # level by Sleeper's numbers
    assert SL.leans(a["cards"], {"B": 8.91}) == {}                             # no Sleeper number for one of them


def test_the_line_on_the_call_and_nothing_moves(monkeypatch):
    monkeypatch.setattr(SL, "snapshots", lambda season, week, ids: _snap(ids))
    monkeypatch.setattr(SL, "season_tally", lambda lg, s: {"n": 13, "ours": 4, "sleeper": 8})
    before = _answer()
    with clock.pinned(SATURDAY):
        out = SL.apply(copy.deepcopy(before), SCRUBS, house=True)
    assert out["actions"][0]["sleeper_lean"] == ("Sleeper's numbers lean to Justin Jefferson. This season, on the 13 close "
                                                 "calls where we have disagreed, Sleeper was right 8 times, we 4.")
    assert out["cards"][0]["sleeper_lean"]["snapshot"]["fetched_at"].startswith("2026-10-10T12:00")
    assert "sleeper_lean" not in out["review"][0]
    strip = copy.deepcopy(out)
    strip["cards"][0].pop("sleeper_lean")
    strip["actions"][0].pop("sleeper_lean")
    assert strip == before                                                     # no number, order or word moved
    # the on-demand path: no record of its own, the lean stands alone
    with clock.pinned(SATURDAY):
        od = SL.apply(copy.deepcopy(before), "999", house=False)
    assert od["actions"][0]["sleeper_lean"] == "Sleeper's numbers lean to Justin Jefferson."


def _two_pairs() -> dict:
    """A Thursday-night pair (TB at DAL, kicked off 9 Oct 00:15 UTC) and a Sunday pair (11 Oct 17:00 UTC), both close,
    Sleeper the other way on both."""
    cards = [{"slot": "WR2", "gsis_id": "T1", "player_name": "Thu Starter", "alt_gsis_id": "T2", "alt_name": "Thu Other",
              "status": "close", "strength": "coin flip"},
             {"slot": "FLEX", "gsis_id": "S1", "player_name": "Sun Starter", "alt_gsis_id": "S2", "alt_name": "Sun Other",
              "status": "close", "strength": "coin flip"}]
    full = [{"gsis_id": g, "market_points": v} for g, v in (("T1", 9.0), ("T2", 12.0), ("S1", 8.0), ("S2", 11.0))]
    return {"week": 5, "season": 2026, "cards": cards, "lineup_full": full, "more_actions": [], "review": [],
            "actions": [{"kind": "close", "cards": [0]}, {"kind": "close", "cards": [1]}]}


def test_sl11_a_thursday_pair_is_hidden_after_thursdays_kickoff_a_sunday_pair_shows_with_a_friday_snapshot(monkeypatch):
    def snap(season, week, ids):
        out = _snap([g for g in ids if g.startswith("S")], fetched=FRIDAY, kick=SUNDAY)
        out.update(_snap([g for g in ids if g.startswith("T")], fetched=FRIDAY, kick=THURSDAY_NIGHT))
        return out
    monkeypatch.setattr(SL, "snapshots", snap)
    monkeypatch.setattr(SL, "season_tally", lambda lg, s: None)
    with clock.pinned(SATURDAY):
        out = SL.apply(_two_pairs(), SCRUBS, house=True)
    assert "sleeper_lean" not in out["actions"][0]                             # Thursday's game has started
    assert out["actions"][1]["sleeper_lean"] == "Sleeper's numbers lean to Sun Other."   # sl1.0 hid this one
    # the snapshot after one player's kickoff hides the pair even before the other's (a mixed Thursday / Sunday pair)
    mixed = {"T1": {"fetched_at": FRIDAY, "kickoff_at": THURSDAY_NIGHT}, "T2": {"fetched_at": FRIDAY, "kickoff_at": SUNDAY}}
    assert SL.pair_ok(mixed, "T1", "T2", T("2026-10-08T12:00:00Z")) is None
    # a snapshot fetched before both kickoffs, but a game already started at the request: nothing (unchanged)
    early = {g: {"fetched_at": T("2026-10-08T17:18:24Z"), "kickoff_at": THURSDAY_NIGHT} for g in ("T1", "T2")}
    assert SL.pair_ok(early, "T1", "T2", T("2026-10-08T20:00:00Z"))["kickoff_at"].startswith("2026-10-09T00:15")
    assert SL.pair_ok(early, "T1", "T2", T(SATURDAY)) is None
    assert SL.pair_ok({"T1": early["T1"]}, "T1", "T2", T("2026-10-08T20:00:00Z")) is None   # no line for one of them


def test_snapshots_join_each_players_own_game(monkeypatch):
    monkeypatch.setattr(SL, "missing_relations", lambda rels: ())

    def q(sql, params):
        if "mart_market_line" in sql:
            return pd.DataFrame([{"gsis_id": "R", "team": "LAR", "fetched_at": FRIDAY},     # Sleeper spells the Rams LAR
                                 {"gsis_id": "B", "team": "BUF", "fetched_at": FRIDAY},
                                 {"gsis_id": "X", "team": "KC", "fetched_at": FRIDAY}])     # a bye: no game that week
        return pd.DataFrame([{"home_team": "LA", "away_team": "BUF", "kickoff_at": T("2026-10-13T00:15:00Z")},
                             {"home_team": "DAL", "away_team": "TB", "kickoff_at": THURSDAY_NIGHT}])
    monkeypatch.setattr(SL, "query", q)
    s = SL.snapshots(2026, 5, ["R", "B", "X"])
    assert set(s) == {"R", "B"} and s["R"]["kickoff_at"] == T("2026-10-13T00:15:00Z")


def test_a_lean_that_cannot_be_read_is_no_line(monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("no database")
    monkeypatch.setattr(SL, "snapshots", boom)
    out = SL.apply(_answer(), SCRUBS, house=True)
    assert "sleeper_lean" not in out["actions"][0]


@needs_db
def test_this_databases_week_5_snapshot_was_fetched_before_boston_and_jeffersons_games():
    s = SL.snapshots(2026, 5, ["00-0041037", "00-0036322"])                     # Boston, Jefferson
    assert SL.pair_ok(s, "00-0041037", "00-0036322", T("2026-10-10T16:00:00Z")) is not None


@needs_db
@pytest.mark.parametrize("source", ["", "&source=sleeper"])
def test_both_my_week_paths_ask_for_the_lean(client, monkeypatch, source):
    seen = []
    real = SL.apply
    monkeypatch.setattr(SL, "apply", lambda ans, league, *, house: (seen.append(house), real(ans, league, house=house))[1])
    r = client.get(f"/api/my-week?league={SCRUBS}&team=2{source}")
    assert r.status_code == 200 and seen == [source == ""]


def test_the_tally_reads_the_record_as_about_does(monkeypatch):
    """The live week 5: 13 disagreements, ours right on 4, Sleeper right 17 of 26 calls of which 9 both got right — so
    Sleeper right on 8 of the disagreements (one was level by Sleeper's numbers), the count About's record line says."""
    monkeypatch.setattr(SL, "missing_relations", lambda rels: ())
    monkeypatch.setattr(SL, "query", lambda *a, **k: pd.DataFrame(
        [{"pairs_disagree": 13, "pairs_ours_right_disagree": 4, "pairs_sleeper_right": 17, "pairs_both_right": 9}]))
    assert SL.season_tally(SCRUBS, 2026) == {"n": 13, "ours": 4, "sleeper": 8}
    monkeypatch.setattr(SL, "query", lambda *a, **k: pd.DataFrame(
        [{"pairs_disagree": None, "pairs_ours_right_disagree": None, "pairs_sleeper_right": None, "pairs_both_right": None}]))
    assert SL.season_tally(SCRUBS, 2026) is None                          # nothing graded yet: no tally
