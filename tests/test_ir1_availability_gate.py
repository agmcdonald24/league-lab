"""IR-1 (Wave I-R): who cannot play — the definition on hand-built rows, the stored gate on a hand-built board, the
audit's first rule. No database."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pandas as pd
import pytest

from league_lab import audit as AU
from league_lab import availability_gate as AG

SEP28 = datetime(2026, 9, 28, 14, 0, tzinfo=UTC)
WEEK4_END = datetime(2026, 10, 6, 0, 15, tzinfo=UTC)       # week 4's last kickoff (Monday night)
OCT8 = datetime(2026, 10, 8, 15, 0, tzinfo=UTC)


@pytest.mark.parametrize("row, code", [
    ({"injury_status": "IR", "status": "Inactive", "team": "MIA"}, "IR"),
    ({"injury_status": "PUP", "status": "Active", "team": "SF"}, "PUP"),
    ({"injury_status": "NFI", "team": "SF"}, "NFI"),
    ({"injury_status": "Sus", "status": "Active", "team": "DAL"}, "SUS"),
    ({"injury_status": "Out", "status": "Active", "team": "MIN"}, "OUT"),
    ({"injury_status": "DNR", "team": "MIN"}, "OUT"),
    ({"injury_status": "Doubtful", "team": "MIN"}, "DOUBTFUL"),
    ({"injury_status": "Questionable", "team": "MIN"}, "QUESTIONABLE"),
    ({"injury_status": None, "status": "Injured Reserve", "team": "NYG"}, "IR"),
    ({"injury_status": "", "status": "Physically Unable to Perform", "team": "NYG"}, "PUP"),
    ({"injury_status": None, "status": "Active", "team": None}, "NO_TEAM"),          # released / unsigned
    ({"injury_status": None, "status": "Active", "team": "KC"}, "ACTIVE"),
    ({"injury_status": "NA", "status": "Active", "team": "KC"}, None),               # NA: no settled meaning: no word
])
def test_sleeper_codes(row, code):
    assert AG.sleeper_code(row) == code


@pytest.mark.parametrize("code, cannot, indef, doubtful", [
    ("IR", True, True, False), ("PUP", True, True, False), ("NFI", True, True, False), ("SUS", True, True, False),
    ("OUT", True, False, False), ("NO_TEAM", True, False, False), ("DOUBTFUL", False, False, True),
    ("QUESTIONABLE", False, False, False), ("ACTIVE", False, False, False),
])
def test_the_definition(code, cannot, indef, doubtful):
    c = AG.classify(AG.entry(code, "Sleeper", as_of=SEP28, note="Knee - ACL"))
    assert (c["cannot_play"], c["out_indefinitely"], c["doubtful"]) == (cannot, indef, doubtful)
    assert (c["week_words"] is not None) == AG.sits(c) and (c["ros_words"] is not None) == indef   # IS-1: Doubtful sits


def test_the_words_say_what_where_and_when():
    c = AG.classify(AG.entry("IR", "Sleeper", as_of=SEP28, note="Knee - ACL"))
    assert c["why"] == "IR (knee - acl) · Sleeper, Sep 28"
    assert c["ros_words"] == "On injured reserve: no return date, so no rest-of-season value."
    assert c["week_words"] == "On injured reserve: he will not play this week, so he is not ranked."
    assert AG.out_sentence("Achane", c) == "Achane is out — on injured reserve (IR (knee - acl) · Sleeper, Sep 28)."
    assert AG.classify(None)["cannot_play"] is False


def test_news_updated_in_milliseconds_is_read():
    assert AG.ts("1790626507704") == datetime.fromtimestamp(1790626507.704, UTC)
    assert AG.ts(None) is None and AG.ts("garbage") is None


def test_last_weeks_game_status_rules_nothing_a_reserve_list_does():
    out_last_week = AG.entry("OUT", "Sleeper", as_of=datetime(2026, 10, 3, tzinfo=UTC))
    ir_long_ago = AG.entry("IR", "Sleeper", as_of=SEP28)
    assert AG.pick([out_last_week], WEEK4_END) is None                     # last Sunday's "Out" is not this week's
    assert AG.pick([ir_long_ago], WEEK4_END)["code"] == "IR"                # a reserve list stays until it changes
    assert AG.pick([AG.entry("OUT", "ESPN", as_of=OCT8)], WEEK4_END)["code"] == "OUT"   # ruled out today


def test_the_freshest_word_wins():
    stored_ir = AG.entry("IR", "Sleeper", as_of=SEP28)
    activated = AG.entry("ACTIVE", "Sleeper", as_of=OCT8)
    espn_out = AG.entry("OUT", "ESPN", as_of=OCT8)
    assert AG.pick([stored_ir, activated])["code"] == "ACTIVE"
    assert AG.pick([AG.entry("ACTIVE", "Sleeper", as_of=SEP28), espn_out])["code"] == "OUT"
    assert AG.pick([AG.entry("OUT", "Sleeper", as_of=OCT8), AG.entry("QUESTIONABLE", "ESPN", as_of=OCT8)])["source"] == "ESPN"
    assert AG.pick([AG.entry("IR", "Sleeper"), AG.entry("ACTIVE", "ESPN", as_of=SEP28)])["code"] == "ACTIVE"   # undated loses


def _board() -> pd.DataFrame:
    rows = []
    for g in ("ir", "out", "doubt", "fine"):
        for w in (5, 6, 7):
            rows.append({"league_id": "L", "gsis_id": g, "week": w, "position": "RB", "proj_carries": 15.0,
                         "proj_points": 12.0, "p10": 4.0, "p25": 8.0, "p50": 11.0, "p75": 15.0, "p90": 21.0})
    return pd.DataFrame(rows)


def test_the_stored_gate_zero_this_week_none_later():
    st = {"ir": AG.classify(AG.entry("IR", "Sleeper", as_of=SEP28, note="knee - acl")),
          "out": AG.classify(AG.entry("OUT", "ESPN", as_of=OCT8)),
          "doubt": AG.classify(AG.entry("DOUBTFUL", "ESPN", as_of=OCT8))}
    out, rep = AG.gate_frame(_board(), {g: s for g, s in st.items() if s["cannot_play"]}, 5)
    by = {(r.gsis_id, r.week): r for r in out.itertuples()}
    for g in ("ir", "out"):          # this week: the row kept, every number 0, the reason recorded
        r = by[(g, 5)]
        assert r.proj_points == 0 and r.p10 == 0 and r.p90 == 0 and r.proj_carries == 0
        assert json.loads(r.availability)["code"] == st[g]["code"]
    assert ("ir", 6) not in by and ("ir", 7) not in by                     # out indefinitely: no later week
    assert by[("out", 6)].proj_points == 12.0                              # out this week only: later weeks kept
    assert by[("doubt", 5)].proj_points == 12.0 and by[("doubt", 5)].availability is None   # doubtful: flagged elsewhere
    assert by[("fine", 7)].proj_points == 12.0
    assert {r["gsis_id"] for r in rep} == {"ir", "out"}


def test_the_gate_leaves_a_frame_without_players_alone():
    df = pd.DataFrame({"week": [5], "proj_points": [3.0]})
    assert AG.gate_frame(df, {}, 5)[0] is df


def test_the_audit_flags_who_cannot_play_and_is_still_ranked():
    st = {"00-0039040": AG.classify(AG.entry("IR", "Sleeper", as_of=SEP28, note="knee - acl")),
          "00-0000002": AG.classify(AG.entry("OUT", "ESPN", as_of=OCT8))}
    week = pd.DataFrame({"gsis_id": ["00-0039040", "00-0000002", "00-0000003"], "player_name": ["De'Von Achane", "B", "C"],
                         "team": ["MIA", "X", "Y"], "position": ["RB"] * 3, "proj": [10.93, 0.0, 9.0], "rank": [21, 60, 25]})
    season = week.assign(proj=[0.0, 80.0, 90.0])
    boards = [AU.Board("ref:half", "Half PPR", "week", "RB", week), AU.Board("ref:half", "Half PPR", "season", "RB", season)]
    got = AU.still_ranked(boards, st)
    assert [(x["player"], x["view"]) for x in got] == [("De'Von Achane", "this week")]   # B: 0 this week, out one week
    assert "IR (knee - acl) · Sleeper, Sep 28" in got[0]["why"]


def test_the_stored_copy_falls_back_to_the_roster_file_never_to_everyone_healthy():
    class Cur:
        def __init__(self):
            self.description = []

        def execute(self, sql, params=()):
            if "raw.sleeper_player" in sql:
                raise RuntimeError("no table")
            self.description = [type("D", (), {"name": "t"})()]

        def fetchall(self):
            return [(None,)]

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class Conn:
        def cursor(self):
            return Cur()

        def rollback(self):
            pass

    got, meta = AG.stored(Conn(), 2026, 5, {"a": "RES", "b": "ACT", "c": "SUS"})
    assert meta["fallback"] is True and set(got) == {"a", "c"}
    assert got["a"]["code"] == "IR" and got["a"]["source"] == "NFL roster file"
