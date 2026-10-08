"""IR-3 (Wave I-R): scripts/post_deploy_check.py's judgements on hand-built answers (no server, no database)."""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("post_deploy_check",
                                               Path(__file__).resolve().parents[1] / "scripts" / "post_deploy_check.py")
pdc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pdc)


def _rows(n=12):
    return [{"rank": i, "player_name": f"P{i}", "proj_points": 25.0 - i, "report_status": None} for i in range(1, n + 1)]


def test_a_sane_top_passes():
    ok, text = pdc.check_rankings({"season": 2026, "week": 5, "rows": _rows()})
    assert ok and "nobody ranked who cannot play" in text


@pytest.mark.parametrize("mutate, words", [
    (lambda r: r.__setitem__(4, {**r[4], "report_status": "IR"}), "ranked though they cannot play: #5 P5 (IR)"),
    (lambda r: r.__setitem__(2, {**r[2], "availability": {"cannot_play": True, "status": "Out"}}), "#3 P3 (Out)"),
    (lambda r: r.__setitem__(0, {**r[0], "proj_points": None}), "projection None is not a number"),
    (lambda r: r.__setitem__(1, {**r[1], "rank": 7}), "ranks out of order"),
    (lambda r: r.__delitem__(slice(5, None)), "only 5 ranked"),
])
def test_an_insane_top_fails_with_the_reason(mutate, words):
    rows = _rows()
    mutate(rows)
    ok, text = pdc.check_rankings({"rows": rows})
    assert not ok and words in text


def test_questionable_or_doubtful_is_not_cannot_play():
    rows = _rows()
    rows[0]["report_status"] = "Questionable"
    rows[1]["availability"] = {"cannot_play": False, "status": "Doubtful"}
    assert pdc.check_rankings({"rows": rows})[0]


TRADE = {
    "verdict": "Helps your lineup +19.8 this week (+11.8 over weeks 5–8), them +6.5 over weeks 5–8 (-0.8 this week).",
    "headline": "", "window_label": "Next 4",
    "fit": {"this_week": {"mine": 19.83, "theirs": -0.84}, "window": {"mine": 11.8, "theirs": 6.55}, "words": ""},
    "before": {"mine": {"this_week": 97.54, "horizon": 447.5, "by_week": [97.54, 123.02, 104.61, 122.33]},
               "theirs": {"this_week": 122.65, "horizon": 474.5, "by_week": [122.65, 114.34, 123.32, 114.19]}},
    "after": {"mine": {"this_week": 117.37, "horizon": 459.3, "by_week": [117.37, 114.31, 105.09, 122.53]},
              "theirs": {"this_week": 121.81, "horizon": 481.05, "by_week": [121.81, 122.42, 122.83, 113.99]}},
}


def test_a_consistent_trade_answer_passes_and_returns_the_changes():
    ok, text, ch = pdc.check_trade(copy.deepcopy(TRADE))
    assert ok, text
    assert ch[("mine", "this_week")] == 19.83 and ch[("theirs", "window")] == 6.55


def test_two_bases_in_one_answer_fail():
    """The review's P0 1: the dial and the decision card on different bases — a change that does not reconcile."""
    b = copy.deepcopy(TRADE)
    b["fit"]["window"]["mine"] = 6.1
    ok, text, _ = pdc.check_trade(b)
    assert not ok and "mine window: after − before = +11.80, the change shown is 6.1" in text


def test_a_verdict_that_does_not_carry_the_numbers_fails():
    b = copy.deepcopy(TRADE)
    b["verdict"] = "Helps your lineup -3.1 over weeks 5–8."
    ok, text, _ = pdc.check_trade(b)
    assert not ok and "the words do not carry the changes" in text


def test_an_answer_without_the_decision_fields_says_to_update_the_check():
    ok, text, _ = pdc.check_trade({"verdict": "x"})
    assert not ok and "update this check" in text
