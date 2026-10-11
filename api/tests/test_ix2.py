"""IX-2 (Wave I-X): the card's bio line, its usage by game situation, and the left-early mark's closed kind. Hand-built
frames; no database; nothing cached between tests."""

import datetime as dt

import pandas as pd

from league_lab_api import onfield as OF
from league_lab_api import player as P


def _bio_row(**kw):
    row = {"birth_date": dt.date(2000, 3, 1), "height": 72, "weight": 205, "college_name": "LSU", "rookie_season": 2021,
           "draft_year": 2021, "draft_round": 1, "draft_pick": 5, "position": "WR"}
    row.update(kw)
    return pd.DataFrame([row])


def test_the_bio_line_says_who_he_is(monkeypatch):
    monkeypatch.setattr(P.clock, "now", lambda: dt.datetime(2026, 10, 11, 12, tzinfo=dt.UTC))
    monkeypatch.setattr(P, "query", lambda sql, params=None: _bio_row())
    b = P.bio("00-0036900")
    assert b["words"] == "6'0\" · 205 lb · 26 years old · 6th season · LSU · 2021 · round 1, pick 5"
    monkeypatch.setattr(P, "query", lambda sql, params=None: _bio_row(rookie_season=2026, draft_year=None, college_name="BYU; Washington",
                                                                      birth_date=dt.date(2004, 10, 12)))
    b = P.bio("x")
    assert b["experience"] == "Rookie" and b["college"] == "BYU / Washington" and b["age"] == "21 years old"
    assert "draft" not in b and "Undrafted" not in b["words"]               # a missing draft row is never "Undrafted"
    monkeypatch.setattr(P, "query", lambda sql, params=None: _bio_row(height=None, weight=0, birth_date=None, college_name=None,
                                                                      rookie_season=None, draft_year=None))
    assert P.bio("x") is None                                                # nothing known: no line (never 0, never N/A)
    monkeypatch.setattr(P, "query", lambda sql, params=None: pd.DataFrame())
    assert P.bio("KC") is None


def test_situations_group_the_five_score_buckets_and_say_a_small_sample(monkeypatch):
    rows = pd.DataFrame([
        {"bucket": "trailing_9plus", "games": 1, "targets": 0, "team_targets": 21, "carries": 0, "team_carries": 5, "team_dropbacks": 23},
        {"bucket": "trailing_1_8", "games": 3, "targets": 14, "team_targets": 59, "carries": 0, "team_carries": 21, "team_dropbacks": 63},
        {"bucket": "tied", "games": 3, "targets": 8, "team_targets": 28, "carries": 0, "team_carries": 15, "team_dropbacks": 32},
        {"bucket": "leading_1_8", "games": 2, "targets": 3, "team_targets": 19, "carries": 0, "team_carries": 17, "team_dropbacks": 22},
        {"bucket": "leading_9plus", "games": 2, "targets": 3, "team_targets": 8, "carries": 1, "team_carries": 3, "team_dropbacks": 10},
    ])
    monkeypatch.setattr(P, "query", lambda sql, params=None: rows)
    s = P.situations("00-0036900", 2026)
    by = {g["key"]: g for g in s["groups"]}
    assert [g["label"] for g in s["groups"]] == ["When trailing", "Within a score", "When leading"]
    assert by["close"]["targets"] == 25 and by["close"]["target_share"] == round(25 / 106, 4) and by["close"]["plays"] == 170
    assert by["trailing"]["plays"] == 28 and not by["trailing"]["too_few"]
    assert by["leading"]["plays"] == 13 and by["leading"]["too_few"] and by["leading"]["words"].endswith("too few to read")
    monkeypatch.setattr(P, "query", lambda sql, params=None: pd.DataFrame())
    assert P.situations("x", 2026) is None


def test_left_early_says_left_early_only_with_the_injury_note():
    hurt = "15 snaps (20% of the team's; usually 94%); hurt on a play in the 2nd quarter"
    assert OF.left_early_case(True, hurt) == ("hurt", "Left early: " + hurt)
    short = "12 snaps (18% of the team's; usually 80%); no target or carry after half-time"
    k, w = OF.left_early_case(True, short)
    assert k == "short" and w == "Played far less than usual: 12 snaps (18% of the team's; usually 80%)"
    assert "left early" not in w.lower() and "hurt" not in w
    k, w = OF.left_early_case(True, short + "; then missed week 5")
    assert w == "Played far less than usual: 12 snaps (18% of the team's; usually 80%); then missed week 5"
    assert OF.left_early_case(False, None) == (None, None)
