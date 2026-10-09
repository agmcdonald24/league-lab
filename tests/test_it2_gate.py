"""IT-2 (Wave I-T): the week's own injury report is the gate's third source (undated: it rules only when nothing dated
speaks); the merge the API and the audit share; "Questionable: about 2 in 3 play" by position; the audit's first rule
split into what a visitor can see (the alarm) and the stored rows the screens gate (a note). No database."""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from league_lab import audit as AU
from league_lab import availability_gate as AG

SEP28 = datetime(2026, 9, 28, 14, 0, tzinfo=UTC)
OCT3 = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)
OCT9 = datetime(2026, 10, 9, 20, 0, tzinfo=UTC)
WEEK4_END = datetime(2026, 10, 6, 0, 15, tzinfo=UTC)


def test_a_player_out_on_this_weeks_report_with_no_other_word_sits():
    got = AG.merge({}, {}, {"hall": AG.report_entry("Out")}, WEEK4_END)
    assert AG.sits(got["hall"]) and got["hall"]["source"] == "NFL injury report" and got["hall"]["why"] == "Out · NFL injury report"
    assert AG.sits(AG.merge({}, {}, {"d": AG.report_entry("Doubtful")})["d"])          # Doubtful on the report: unlikely
    assert not AG.sits(AG.merge({}, {}, {"q": AG.report_entry("Questionable")})["q"])  # Questionable: ranked, flagged
    assert AG.report_entry(None) is None and AG.report_entry("Healthy") is None


def test_the_report_has_a_week_not_a_time_any_dated_word_outranks_it():
    # an older reserve-list word stays: IR from September is never turned into "Out" (his season would come back)
    ir = AG.merge({"a": AG.entry("IR", "Sleeper", as_of=SEP28)}, {}, {"a": AG.report_entry("Out")}, WEEK4_END)["a"]
    assert ir["code"] == "IR" and ir["out_indefinitely"]
    # a fresh dated word wins (ESPN cleared him today; the report row said Questionable)
    assert "b" not in AG.merge({}, {"b": [AG.entry("ACTIVE", "ESPN", as_of=OCT9)]}, {"b": AG.report_entry("Questionable")}, WEEK4_END)
    # last week's dated game status is dropped first, then the report decides
    c = AG.merge({}, {"c": [AG.entry("QUESTIONABLE", "Sleeper", as_of=OCT3)]}, {"c": AG.report_entry("Out")}, WEEK4_END)["c"]
    assert c["code"] == "OUT" and c["source"] == "NFL injury report"


def test_questionable_says_its_rate_by_position():
    q = AG.classify(AG.entry("QUESTIONABLE", "ESPN", as_of=OCT9))
    assert AG.short_words(q) == "Questionable: about 2 in 3 play"
    assert AG.short_words(q, "QB") == "Questionable: about 1 in 2 play"
    assert AG.short_words(q, "RB") == "Questionable: about 2 in 3 play"
    assert AG.short_words(q, "WR") == "Questionable: about 7 in 10 play"
    assert AG.short_words(AG.classify(AG.entry("DOUBTFUL", "ESPN", as_of=OCT9))) is None      # he sits: no rate on a row
    # the 25 % rule per position: no position's Questionable falls under it
    assert min(AG.P_PLAY_POS["QUESTIONABLE"].values()) >= AG.UNLIKELY_BELOW
    assert max(AG.P_PLAY_POS["DOUBTFUL"].values()) < AG.UNLIKELY_BELOW


def _query_for(directory: list[dict], record: list[dict], report: list[dict], kickoff: datetime):
    def query(sql, params=()):
        if "raw.sleeper_player" in sql:
            return pd.DataFrame(directory, columns=["gsis_id", "sleeper_id", "full_name", "position", "team", "status",
                                                    "injury_status", "news_updated", "body_part", "fetched_at"])
        if "projection_lines" in sql:
            return pd.DataFrame(record, columns=["gsis_id", "availability"])
        if "report_status" in sql:
            return pd.DataFrame(report, columns=["gsis_id", "report_status"])
        if "min(kickoff_at)" in sql:
            return pd.DataFrame({"k": [kickoff]})
        return pd.DataFrame({"t": [WEEK4_END]})
    return query


def test_the_audits_first_rule_splits_the_alarm_from_the_frozen_note():
    ms = str(int(OCT9.timestamp() * 1000))
    directory = [{"gsis_id": "00-0038120", "sleeper_id": "8155", "full_name": "Breece Hall", "position": "RB", "team": "NYJ",
                  "status": "Active", "injury_status": "Doubtful", "news_updated": ms, "body_part": "Quadriceps",
                  "fetched_at": OCT9}]
    q = _query_for(directory, [], [], datetime(2026, 10, 2, 0, 15, tzinfo=UTC))   # before the pinned clock
    src = AG.sources_from_query(q, 2026, 5)
    assert set(src["directory"]) == {"00-0038120"} and src["record"] == {} and src["report"] == {}
    screens = AG.merge(src["record"], {g: [e] for g, e in src["directory"].items()}, src["report"], src["pwe"])
    stored_only = AG.merge(src["record"], None, src["report"], src["pwe"])
    assert AG.sits(screens["00-0038120"]) and "00-0038120" not in stored_only      # hidden by the live word alone
    rows = pd.DataFrame({"gsis_id": ["00-0038120"], "player_name": ["Breece Hall"], "team": ["NYJ"], "position": ["RB"],
                         "proj": [10.6], "rank": [18]})
    sr = AU.still_ranked([AU.Board("ref:half", "Half PPR", "week", "RB", rows)], {g: AG.classify(e) for g, e in src["directory"].items()})
    assert [x["gsis_id"] for x in sr] == ["00-0038120"]                           # a stored row: the note, not the alarm
    assert AU._week_started(q, 2026, 5) is True
