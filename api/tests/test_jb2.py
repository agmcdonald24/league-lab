"""JB-2 (Wave J-B): a close call says when Sleeper's pre-kickoff numbers lean the other way (sleeper_lean, both My Week
paths); the thresholds of the tally sentence; a snapshot fetched after the first kickoff says nothing; a lean that
cannot be read is no line; no number of the answer moves."""

from __future__ import annotations

import copy

import pandas as pd
import pytest

from league_lab_api import sleeper_lean as SL

from .conftest import SCRUBS, needs_db

SNAP = {"fetched_at": "2026-10-08T17:18:24+00:00", "first_kickoff_at": "2026-10-09T00:15:00+00:00"}


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
    monkeypatch.setattr(SL, "snapshot_before_kickoff", lambda s, w: SNAP)
    monkeypatch.setattr(SL, "season_tally", lambda lg, s: {"n": 13, "ours": 4, "sleeper": 8})
    before = _answer()
    out = SL.apply(copy.deepcopy(before), SCRUBS, house=True)
    assert out["actions"][0]["sleeper_lean"] == ("Sleeper's numbers lean to Justin Jefferson. This season, on the 13 close "
                                                 "calls where we have disagreed, Sleeper was right 8 times, we 4.")
    assert out["cards"][0]["sleeper_lean"]["snapshot"] == SNAP
    assert "sleeper_lean" not in out["review"][0]
    strip = copy.deepcopy(out)
    strip["cards"][0].pop("sleeper_lean")
    strip["actions"][0].pop("sleeper_lean")
    assert strip == before                                                     # no number, order or word moved
    # the on-demand path: no record of its own, the lean stands alone
    od = SL.apply(copy.deepcopy(before), "999", house=False)
    assert od["actions"][0]["sleeper_lean"] == "Sleeper's numbers lean to Justin Jefferson."


def test_a_snapshot_fetched_after_the_first_kickoff_says_nothing(monkeypatch):
    monkeypatch.setattr(SL, "snapshot_before_kickoff", lambda s, w: None)
    out = SL.apply(_answer(), SCRUBS, house=True)
    assert "sleeper_lean" not in out["actions"][0] and "sleeper_lean" not in out["cards"][0]
    # the rule itself: fetched after the first kickoff (a mid-week pull) → None
    monkeypatch.undo()
    monkeypatch.setattr(SL, "missing_relations", lambda rels: ())
    monkeypatch.setattr(SL, "query", lambda *a, **k: pd.DataFrame(
        [{"fetched_at": pd.Timestamp("2026-10-10T12:00:00Z"), "first_kickoff_at": pd.Timestamp("2026-10-09T00:15:00Z")}]))
    assert SL.snapshot_before_kickoff(2026, 5) is None
    monkeypatch.setattr(SL, "query", lambda *a, **k: pd.DataFrame(
        [{"fetched_at": pd.Timestamp("2026-10-08T17:18:24Z"), "first_kickoff_at": pd.Timestamp("2026-10-09T00:15:00Z")}]))
    assert SL.snapshot_before_kickoff(2026, 5)["fetched_at"].startswith("2026-10-08T17:18:24")


def test_a_lean_that_cannot_be_read_is_no_line(monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("no database")
    monkeypatch.setattr(SL, "snapshot_before_kickoff", boom)
    out = SL.apply(_answer(), SCRUBS, house=True)
    assert "sleeper_lean" not in out["actions"][0]


@needs_db
def test_this_databases_week_5_snapshot_was_fetched_before_the_first_kickoff():
    s = SL.snapshot_before_kickoff(2026, 5)
    assert s is not None and s["fetched_at"] < s["first_kickoff_at"]


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
