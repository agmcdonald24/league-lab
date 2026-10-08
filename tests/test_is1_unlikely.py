"""IS-1 (Wave I-S): a status that rarely plays is not ranked as if it will — the unlikely tier on hand-built rows, the
stored gate (0 this week, later weeks kept), kickers' league-free lines, the overlay's sets as views of the gate, the
audit's first rule. No database."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pandas as pd
import pytest

from league_lab import audit as AU
from league_lab import availability_gate as AG

OCT7 = datetime(2026, 10, 7, 16, 0, tzinfo=UTC)
WEEK4_END = datetime(2026, 10, 6, 0, 15, tzinfo=UTC)


def test_the_rule_is_the_measured_rate_against_the_threshold():
    assert AG.UNLIKELY_BELOW == 0.25
    assert AG.P_PLAY["DOUBTFUL"] < AG.UNLIKELY_BELOW <= AG.P_PLAY["QUESTIONABLE"]
    assert AG.UNLIKELY == {"DOUBTFUL"} and AG.FLAGGED == {"QUESTIONABLE"}
    assert AG.SITS_CODES == AG.CANNOT_PLAY | {"DOUBTFUL"}


@pytest.mark.parametrize("code, sits, cannot, unlikely, indef", [
    ("DOUBTFUL", True, False, True, False), ("QUESTIONABLE", False, False, False, False),
    ("OUT", True, True, False, False), ("IR", True, True, False, True), ("INACTIVE", True, True, False, False),
    ("ACTIVE", False, False, False, False),
])
def test_sits_is_cannot_play_or_unlikely(code, sits, cannot, unlikely, indef):
    b = AG.classify(AG.entry(code, "Sleeper", as_of=OCT7, note="quadriceps"))
    assert (AG.sits(b), b["cannot_play"], b["unlikely"], b["out_indefinitely"]) == (sits, cannot, unlikely, indef)


def test_the_words_say_how_often_such_players_play():
    hall = AG.classify(AG.entry("DOUBTFUL", "Sleeper", as_of=OCT7, note="Quadriceps"))
    assert hall["p_play"] == 0.01 and hall["why"] == "Doubtful (quadriceps) · Sleeper, Oct 7"
    assert hall["week_words"] == "Doubtful: players listed doubtful have played about 1 in 100 times; not ranked this week."
    assert hall["ros_words"] is None                                         # not out indefinitely: his season stays
    assert AG.out_sentence("Hall", hall) == ("Hall is doubtful — players listed doubtful have played about 1 in 100 "
                                            "times (Doubtful (quadriceps) · Sleeper, Oct 7).")
    q = AG.classify(AG.entry("QUESTIONABLE", "ESPN", as_of=OCT7))
    assert q["p_play"] == 0.67 and q["week_words"] is None
    assert q["flag_words"] == "Questionable: players listed questionable have played about 67 in 100 times; ranked as if he plays."
    assert AG.out_sentence("Achane", AG.classify(AG.entry("IR", "Sleeper", note="knee - acl"))).startswith("Achane is out — ")


def test_last_weeks_doubtful_rules_nothing():
    assert AG.pick([AG.entry("DOUBTFUL", "Sleeper", as_of=datetime(2026, 10, 3, tzinfo=UTC))], WEEK4_END) is None
    assert AG.pick([AG.entry("DOUBTFUL", "Sleeper", as_of=OCT7)], WEEK4_END)["code"] == "DOUBTFUL"


def test_sleepers_inactive_with_a_team_is_one_rule_now():
    assert AG.sleeper_code({"status": "Inactive", "team": "NYG", "injury_status": None}) == "INACTIVE"
    assert AG.sleeper_code({"status": "Inactive", "team": "MIA", "injury_status": "IR"}) == "IR"


def _board() -> pd.DataFrame:
    return pd.DataFrame([{"league_id": "L", "gsis_id": g, "week": w, "position": "RB", "proj_carries": 15.0,
                          "proj_points": 12.0, "p10": 4.0, "p50": 11.0, "p90": 21.0}
                         for g in ("hall", "fine") for w in (5, 6)])


def test_the_stored_gate_gives_a_doubtful_player_0_this_week_and_keeps_his_season():
    st = {"hall": AG.classify(AG.entry("DOUBTFUL", "Sleeper", as_of=OCT7, note="quadriceps"))}
    out, rep = AG.gate_frame(_board(), st, 5)
    by = {(r.gsis_id, r.week): r for r in out.itertuples()}
    assert by[("hall", 5)].proj_points == 0 and by[("hall", 5)].p90 == 0
    assert json.loads(by[("hall", 5)].availability)["code"] == "DOUBTFUL"
    assert by[("hall", 6)].proj_points == 12.0                              # later weeks stay
    assert by[("fine", 5)].proj_points == 12.0 and [r["gsis_id"] for r in rep] == ["hall"]


def test_kickers_league_free_lines_drop_the_week_and_the_season_when_out_indefinitely():
    kd = pd.DataFrame([{"unit_id": u, "position": "K", "week": w, "proj_fg": 1.8} for u in ("kir", "kq", "kok") for w in (5, 6)])
    st = {"kir": AG.classify(AG.entry("IR", "Sleeper")), "kq": AG.classify(AG.entry("DOUBTFUL", "ESPN", as_of=OCT7)),
          "kok": AG.classify(AG.entry("QUESTIONABLE", "ESPN", as_of=OCT7))}
    out, gone = AG.drop_frame(kd, st, 5)
    assert {(r.unit_id, r.week) for r in out.itertuples()} == {("kq", 6), ("kok", 5), ("kok", 6)}
    assert gone == ["kir", "kq"]


def test_the_audit_counts_who_is_unlikely_to_play_and_still_ranked():
    st = {"00-0038120": AG.classify(AG.entry("DOUBTFUL", "Sleeper", as_of=OCT7, note="quadriceps")),
          "00-0000009": AG.classify(AG.entry("QUESTIONABLE", "ESPN", as_of=OCT7))}
    week = pd.DataFrame({"gsis_id": ["00-0038120", "00-0000009"], "player_name": ["Breece Hall", "Q"], "team": ["NYJ", "X"],
                         "position": ["RB", "RB"], "proj": [11.8, 9.0], "rank": [18, 25]})
    season = week.assign(proj=[100.0, 90.0])
    got = AU.still_ranked([AU.Board("ref:half", "Half PPR", "week", "RB", week),
                           AU.Board("ref:half", "Half PPR", "season", "RB", season)], st)
    assert [(x["player"], x["view"]) for x in got] == [("Breece Hall", "this week")]   # his season stays; Q stays ranked


def test_the_audits_reader_never_reads_the_stored_record():
    seen = []

    def query(sql, params=()):
        seen.append(sql)
        if "raw.sleeper_player" in sql:
            return pd.DataFrame([{"gsis_id": "00-0038120", "sleeper_id": "8155", "full_name": "Breece Hall", "position": "RB",
                                  "team": "NYJ", "status": "Active", "injury_status": "Doubtful",
                                  "news_updated": str(int(OCT7.timestamp() * 1000)), "body_part": "Quadriceps",
                                  "fetched_at": OCT7}])
        return pd.DataFrame({"t": [WEEK4_END]})
    st, _meta = AG.statuses_from_query(query, 2026, 5)
    assert AG.sits(st["00-0038120"]) and st["00-0038120"]["unlikely"]
    assert not any("projection_lines" in s for s in seen)
