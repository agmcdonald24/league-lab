"""IP-3 (Wave I-P): what Trends' "below / above expectation" and the role chips have meant for the next game —
``context_record.summary()`` gains ``trend`` and ``role`` beside ``corner`` and ``worth`` (absent rows: graded False;
a grade of Wave I-O's shape keeps its two keys working), ``GET /api/trends`` carries ``record``, Trends' how-to says
what the grade found (no "due" / "running hot"), and the record's reason category is research.trend_cause's."""

from __future__ import annotations

import pandas as pd
import pytest

from .conftest import DYNASTY, needs_db

IO_ROWS = [
    {"kind": "summary", "grp": "corner", "n": 2190, "words": "Graded on 2025 (Half PPR): no measurable effect either way."},
    {"kind": "summary", "grp": "worth", "n": 37, "words": "Graded on 2025 …, listed players … — not distinguishable from chance."},
    {"kind": "summary", "grp": "worth_off", "n": 37, "words": "We tried a \"Worth a look\" list …"},
    {"kind": "corner", "grp": "likely/shutdown", "corner_certainty": "likely", "corner_tier": "shutdown", "n": 99,
     "vs_rest": -0.39, "vs_rest_lo": -1.39, "vs_rest_hi": 0.72, "words": "Graded: no measurable effect (…)."},
]
TREND_WORDS = ("Graded on 2025 and 2026 weeks 1–4 (Half PPR), in their next game: players below expectation scored 1.5 "
               "points more than their points per game before and finished 0.2 points above the other players against "
               "their projection (−0.1 to +0.5; 2,467 games) — no measurable difference; …")
HEAD = ("Graded on 2025 and 2026 weeks 1–4 (Half PPR): in their next game, players below expectation scored 1.5 more than before and "
        "players above it 1.9 less — and their projections already expected that (no measurable difference against them; "
        "4,282 games).")
IP_ROWS = IO_ROWS + [
    {"kind": "summary", "grp": "trend", "n": 4282, "words": TREND_WORDS},
    {"kind": "summary", "grp": "trend_head", "n": 4282, "words": HEAD},
    {"kind": "summary", "grp": "role", "n": 1837, "words": "Graded on 2025 weeks 5–18 (Half PPR), in their next game: …"},
    {"kind": "trend", "grp": "below/all/all/1", "n": 2467, "vs_rest": 0.17, "vs_rest_lo": -0.15, "vs_rest_hi": 0.49,
     "span": "2025 and 2026 weeks 1–4"},
    {"kind": "trend_raw", "grp": "below/all/all/1", "n": 2467, "mean_miss": 1.54},
    {"kind": "trend", "grp": "above/all/all/1", "n": 1815, "vs_rest": -0.6, "vs_rest_lo": -0.9, "vs_rest_hi": -0.3},
    {"kind": "trend_raw", "grp": "above/all/all/1", "n": 1815, "mean_miss": -1.91},
    {"kind": "role", "grp": "up/all/all/1", "n": 1022, "vs_rest": 0.22, "vs_rest_lo": -0.21, "vs_rest_hi": 0.64},
]


@pytest.fixture
def rec(monkeypatch):
    """context_record's two reads faked: ``state["exists"]`` (the table), ``state["rows"]`` (its rows), ``state["boom"]``."""
    from league_lab_api import context_record as CR
    state = {"exists": True, "rows": IP_ROWS, "boom": False}

    def fake_query(sql, params=(), ttl=None):
        if state["boom"]:
            raise RuntimeError("the pool is closed")
        if sql == CR.EXISTS_SQL:
            return pd.DataFrame([{"ok": state["exists"]}])
        if sql == CR.GRADE_SQL:
            return pd.DataFrame(state["rows"])
        raise AssertionError(sql)
    monkeypatch.setattr(CR, "query", fake_query)
    CR.clear()
    yield state
    CR.clear()


def test_summary_gains_trend_and_role(rec):
    from league_lab_api import context_record as CR
    s = CR.summary()
    assert s["trend"]["graded"] is True and s["trend"]["n"] == 4282
    assert s["trend"]["words"] == TREND_WORDS and s["trend"]["head"] == HEAD
    below, above = s["trend"]["tags"]["below"], s["trend"]["tags"]["above"]
    assert below == {"n": 2467, "vs_rest": 0.17, "lo": -0.15, "hi": 0.49, "effect": "none",
                     "span": "2025 and 2026 weeks 1–4", "raw": 1.54}
    assert above["effect"] == "measured" and above["raw"] == -1.91
    assert s["role"]["graded"] is True and s["role"]["trends"]["up"]["effect"] == "none"
    assert s["role"]["trends"]["down"] is None
    # Wave I-O's keys unchanged beside them
    assert s["corner"]["graded"] is True and s["worth"]["graded"] is True


def test_a_grade_of_wave_io_shape_keeps_corner_and_worth(rec):
    from league_lab_api import context_record as CR
    rec["rows"] = IO_ROWS
    s = CR.summary()
    assert s["corner"]["graded"] is True and s["corner"]["words"].startswith("Graded on 2025")
    assert s["worth"]["graded"] is True and s["worth"]["line"].startswith("We tried")
    assert s["trend"] == {"graded": False, "n": 0, "words": None, "head": None, "tags": {}}
    assert s["role"] == {"graded": False, "n": 0, "words": None, "trends": {}}


def test_without_the_table_every_key_is_quiet(rec):
    from league_lab_api import context_record as CR
    rec["exists"] = False
    s = CR.summary()
    assert set(s) == {"corner", "worth", "trend", "role", "horizon"}   # IR-4: + horizon
    assert not any(s[k]["graded"] for k in s) and s["trend"]["head"] is None
    CR.clear()
    rec["exists"], rec["boom"] = True, True
    assert CR.summary()["trend"]["graded"] is False and CR.summary()["role"]["graded"] is False


def test_the_route_carries_the_new_keys(client, rec):
    from league_lab_api.ratelimit import bucket_for
    d = client.get("/api/context/record").json()
    assert d["trend"]["head"] == HEAD and d["role"]["graded"] is True
    assert bucket_for("GET", "/api/context/record") == "read"


def test_trends_howto_promises_nothing():
    from league_lab_api import research as RS
    assert "running hot" not in RS.TRENDS_HOWTO and "below = due" not in RS.TRENDS_HOWTO
    assert "about as much as their projection already expected" in RS.TRENDS_HOWTO


CASES = [
    # (position, gap, games, tds, rz_targets, rz_carries, pass_tds, shares, qb_changed)
    ("WR", -2.0, 3, 0, 3, 0, 0, [0.2, 0.2, 0.2], False),
    ("WR", -2.0, 3, 1, 1, 0, 0, [0.2, 0.2, 0.2], True),
    ("TE", -2.0, 3, 1, 1, 0, 0, [0.25, 0.2, 0.18], False),
    ("RB", -2.0, 3, 1, 0, 1, 0, [0.5, 0.5, 0.5], False),
    ("QB", -2.0, 3, 0, 0, 0, 0, [None, None, None], True),
    ("RB", 2.0, 3, 2, 0, 2, 0, [0.5, 0.5, 0.5], False),
    ("QB", 2.0, 2, 0, 0, 0, 4, [None, None], False),
    ("WR", 2.0, 4, 1, 1, 0, 0, [0.15, 0.2, 0.25], True),
    ("WR", 2.0, 4, 1, 1, 0, 0, [0.20, 0.2, 0.21], True),
    ("WR", 2.0, 4, 1, 1, 0, 0, [0.20, 0.2, 0.21], False),
]


@pytest.mark.parametrize("case", CASES)
def test_the_records_reason_is_the_screens(case):
    """The record grades by the reason Trends prints: league_lab.context_record.trend_reason is research.trend_cause's
    category on the same numbers."""
    from league_lab import context_record as C

    from league_lab_api import research as RS
    pos, gap, games, tds, rzt, rzc, ptd, shares, qb = case
    key = "carry_shares" if pos == "RB" else "target_shares"
    cause = RS.trend_cause({"gap": gap, "position": pos, "work_games": games, "tds": tds, "rz_targets": rzt,
                            "rz_carries": rzc, "pass_tds": ptd, key: shares, "qb_changed": qb})
    want = ("none" if cause is None else "touchdowns" if "touchdown" in cause else "quarterback" if "quarterback" in cause
            else "share")
    sh = [x for x in shares if x is not None]
    rz = rzt + (rzc if pos in ("RB", "QB") else 0)
    got = C.trend_reason(pos, gap, games, tds, rz, ptd, sh[0] if len(sh) >= 2 else None, sh[-1] if len(sh) >= 2 else None, qb)
    assert got == want, (case, cause)


@needs_db
def test_trends_carries_the_record(client):
    d = client.get(f"/api/trends?league={DYNASTY}&view=all&limit=5&metrics=none").json()
    assert "record" in d and set(d["record"]) >= {"graded", "n", "words", "head", "tags"}


# ------------------------------------------------------------------------------ fix round: the grade where it is implied
GRADED_ROLE = "Graded on 2025 weeks 5–18 (Half PPR), in their next game: after \"role up\" players finished 0.2 points …"


def _summary(role: bool = True, trend: bool = True, measured: bool = False) -> dict:
    import copy

    from league_lab_api import context_record as CR
    s = copy.deepcopy(CR.EMPTY)
    if role:
        s["role"] = {"graded": True, "n": 1837, "words": GRADED_ROLE,
                     "trends": {"up": {"n": 1022, "vs_rest": 0.22, "lo": -0.21, "hi": 0.64, "effect": "none"}, "down": None}}
    if trend:
        below = {"n": 2467, "vs_rest": -0.6 if measured else 0.17, "lo": -0.9 if measured else -0.15,
                 "hi": -0.3 if measured else 0.49, "effect": "measured" if measured else "none",
                 "span": "2025 and 2026 weeks 1–4", "raw": 1.54}
        s["trend"] = {"graded": True, "n": 4282, "words": TREND_WORDS, "head": HEAD,
                      "tags": {"below": below, "above": {"n": 1815, "vs_rest": -0.15, "lo": -0.45, "hi": 0.15,
                                                         "effect": "none", "span": "2025 and 2026 weeks 1–4", "raw": -1.91}}}
    return s


def test_the_trade_lists_line_comes_from_the_record(monkeypatch):
    from league_lab_api import context_record as CR
    from league_lab_api import decisions as DC
    assert CR.gap_line(_summary()["trend"]) == ("Their projections already expect the gap to close part-way: no edge in "
                                                "buying or selling on it — graded on 4,282 games (2025 and 2026 weeks 1–4, "
                                                "Half PPR).")
    m = CR.gap_line(_summary(measured=True)["trend"])
    assert "players below their work finished 0.6 points below the rest against their projection (−0.9 to −0.3)" in m
    assert CR.gap_line(_summary(trend=False)["trend"]) is None
    monkeypatch.setattr(CR, "summary", lambda: _summary(trend=False))
    w = DC.gap_words()
    assert w["gap_graded"] is False and w["gap_line"] == DC.GAP_LINE_NO_RECORD and "graded" not in w["gap_line"].lower()
    monkeypatch.setattr(CR, "summary", lambda: _summary())
    w = DC.gap_words()
    assert w["gap_graded"] is True and w["gap_line"].startswith("Their projections already expect the gap")
    assert w["titles"] == {"below": "Scoring below his work", "above": "Scoring above his work"}


def test_the_trade_cards_never_say_buy_or_sell_on_the_gap():
    import re

    from league_lab_api import decisions as DC
    t = {"player": {"player_name": "Kenneth Walker III", "position": "RB"}, "team_name": "Run Bijan Run",
         "diff_per_game": -1.5, "gain_week": 8.0, "loss_week": 7.9, "fit_horizon": 9.9}
    b = DC.below_line(t, "weeks 4–7", 4)
    assert b == ("**Kenneth Walker III (RB, Run Bijan Run) scores 1.5 per game below his work.** He would add **+8.0** to "
                 "your week-4 lineup and cost them **7.9** (fit **+9.9** over weeks 4–7): the fit, from the projections, "
                 "is the reason to ask about him — not the gap.")
    a = DC.above_line({**t, "player": {"player_name": "Patrick Mahomes", "position": "QB"}, "team_name": "GoodGameBuddy",
                       "diff_per_game": 5.0}, "weeks 4–7", 4)
    never = re.compile(r"\b(buy|sell|due|bargain|regression|turn around|running hot)\b", re.I)
    for line in (b, a, DC.below_line(None, "weeks 4–7", 4), DC.above_line(None, "weeks 4–7", 4), *DC.TRADE_HOWTO[:1]):
        assert not never.search(line.replace("buying or selling", "")), line


def test_the_player_cards_help_no_longer_says_due():
    from league_lab_api import player as PL
    assert "running hot" not in PL.HOWTO and "below = due" not in PL.HOWTO
    assert "his projection already counts it" in PL.HOWTO


def test_dfs_role_chip_and_panel_carry_the_record(monkeypatch):
    from league_lab_api import context_record as CR
    from league_lab_api import dfs as DF
    role_sig = {"signal": "role", "label": "Role trend", "tone": "favorable", "words": "Role up …", "trend": "up",
                "in_projection": True, "projection_words": "In the projection"}
    monkeypatch.setattr(DF, "_context_parts", lambda s, w: {"role": {}, "game": {}, "wx": {}, "lines": False, "forecast": False})
    monkeypatch.setattr(DF, "_matchup_fn", lambda: None)
    monkeypatch.setattr(DF.D, "signals", lambda *a, **k: [dict(role_sig)])
    rows = [{"key": "k", "gsis_id": "g", "position": "WR", "team": "SEA", "out": False}]
    monkeypatch.setattr(CR, "summary", lambda: _summary())
    out, meta = DF.context_for(2026, 5, rows)
    sig = out["k"]["context"][0]
    assert sig["graded"] == GRADED_ROLE and sig["graded_effect"] == "none" and meta["role_record"] == GRADED_ROLE
    monkeypatch.setattr(CR, "summary", lambda: _summary(role=False))       # without the record: today's words
    out, meta = DF.context_for(2026, 5, rows)
    assert "graded" not in out["k"]["context"][0] and meta["role_record"] is None


def test_stats_role_columns_carry_the_record(monkeypatch):
    from league_lab_api import context_record as CR
    from league_lab_api import stats as ST
    monkeypatch.setattr(CR, "summary", lambda: _summary())
    cat = {c["id"]: c for c in ST.catalogue(2026)}
    for cid in ("target_share_change", "carry_share_change", "snap_share_change"):
        assert cat[cid]["graded"] == GRADED_ROLE
    assert "graded" not in cat["target_share"]
    monkeypatch.setattr(CR, "summary", lambda: _summary(role=False))
    assert all("graded" not in c for c in ST.catalogue(2026))
