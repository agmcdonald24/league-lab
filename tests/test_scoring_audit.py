"""Wave I-C (IC-1): the scoring check's arithmetic on constructed rows (no database): the counts, the misses and the
rule each miss points at."""

from __future__ import annotations

import json
from pathlib import Path

from league_lab import scoring_audit as SA
from league_lab.scoring import from_mfl, from_sleeper

ROOT = Path(__file__).resolve().parents[1]
DAD = from_mfl(json.loads((ROOT / "api/tests/fixtures/mfl/70587/rules.json").read_text()))


def test_likely_rule_names_the_piece_whose_removal_closes_the_gap():
    pieces = {"step:rushing_yards": 10.0, "band:rushing_yards:100": 10.0, "distance:rushing_tds": 6.0}
    # theirs 16: our 100-yard bonus is the one too many (the step is worth the same: the first match is kept)
    assert SA.likely_rule(16.0, pieces, DAD, "RB", False).split(":")[0] in ("band", "step")
    assert SA.likely_rule(20.0, pieces, DAD, "RB", False) == "distance:rushing_tds"


def test_likely_rule_counts_and_missing_events():
    d = {"rate:sacks": 6.0, "rate:interceptions": 3.0}
    assert SA.likely_rule(11.0, d, DAD, "DEF", False).startswith("count:sacks")       # one sack more in theirs
    assert SA.likely_rule(13.0, {"step:receiving_yards": 4.0}, DAD, "WR", False).startswith("missing:a touchdown")
    assert SA.likely_rule(0.5, {"step:receiving_yards": 4.0, "x": 9.0}, DAD, "WR", False) == "unexplained"
    assert SA.likely_rule(10.0, {"distance:rushing_tds": 8.0}, DAD, "RB", True).startswith("distance:approximated")


def test_compare_counts_and_words():
    sp = from_sleeper({"rec": 0.5, "rec_yd": 0.1, "rec_td": 6.0, "bonus_rec_yd_100": 3.0})
    rows = [
        {"player": "A", "position": "WR", "theirs": 15.5, "line": {"receptions": 5, "receiving_yards": 70, "receiving_tds": 1}},
        {"player": "B", "position": "WR", "theirs": 13.6, "line": {"receptions": 1, "receiving_yards": 105}},  # ours 14.0
        {"player": "C", "position": "WR", "theirs": 13.0, "line": {"receptions": 4, "receiving_yards": 110}},  # ours 16.0
        {"player": "D", "position": "WR", "theirs": 0.0, "line": None},                                       # no game: not counted
    ]
    out = SA.compare(rows, sp)
    assert (out["n"], out["within_0_1"], out["within_1"]) == (3, 1, 2)
    (m,) = out["misses"]
    assert m["player"] == "C" and m["gap"] == 3.0 and m["likely_rule"] == "band:receiving_yards:100"
    assert out["suspect_rules"][0]["misses"] == 1
    words = SA._words({**out, "week": 2})
    assert words.startswith("Week 2 check: we match the league's own points for 2 of 3 players within 1 point (67%)")


def test_piece_words():
    assert SA.piece_words("band:rushing_yards:100") == "the bonus at 100 rushing yards"
    assert SA.piece_words("distance:receiving_tds") == "receiving tds by distance"
    assert SA.piece_words("count:sacks (one more or fewer than our stat line)").startswith("the count of sacks")


def test_unit_lines_sum_and_keep_lengths_only_when_complete():
    a = {"passing_yards": 200.0, "passing_tds": 2.0, "passing_tds_lengths": [5, 45], "position": "QB"}
    b = {"passing_yards": 30.0, "passing_tds": 1.0, "position": "QB"}                 # no lengths for the backup
    s = SA._sum_lines([a, b])
    assert s["passing_yards"] == 230 and s["passing_tds"] == 3 and "passing_tds_lengths" not in s
    s2 = SA._sum_lines([a, {"passing_yards": 30.0, "passing_tds": 0.0, "passing_tds_lengths": [], "position": "QB"}])
    assert s2["passing_tds_lengths"] == [5, 45]
