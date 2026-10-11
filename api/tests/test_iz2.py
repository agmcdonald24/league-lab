"""IZ-2 (Wave I-Z): a trade answers five questions in order — the web orders and words the calculator's answer, it does
not re-price it. What the screen relies on, pinned on the database's answers:

* keep / claim / trade on one basis: the claim's total the screen prints is standing pat plus the claim's gain
  (`lib/tradefive.threeWays`); that is the API's own comparison read the other way (trade − claim = `beyond`);
* the lineup panel's rows are the decision's `changes` with both players named (the displaced player and who takes
  the slot), and the panel's total is the tiles' this-week total;
* the reasons they might say no are words, never a chance; the market price carries its date (`provenance`).
"""

from __future__ import annotations

import re

import pytest

from .conftest import needs_db

SCRUBS = "1389709692405551104"
CASES = [(SCRUBS, 2, 3, ["650"], ["421", "11792"]),      # the review's known trade (implausible)
         (SCRUBS, 2, 6, ["650"], ["11581"])]             # a trade the Trade Finder lists as worth proposing


def _evaluate(monkeypatch, league, team, partner, give, get):
    from league_lab_api import decisions as D
    monkeypatch.setenv("LEAGUE_LAB_AVAILABILITY", "off")
    D.clear_memo()
    ctx = D.trade_context(league)
    if any(ctx.board.owner(k) != team for k in give) or any(ctx.board.owner(k) != partner for k in get):
        pytest.skip("the database's rosters do not hold this package")
    return D.evaluate(league, team, partner, give, get, window="next4")


@needs_db
@pytest.mark.parametrize("case", CASES, ids=["folk", "lloyd"])
def test_three_ways_are_the_answers_own_comparison(monkeypatch, case):
    out = _evaluate(monkeypatch, *case)
    d = out["decision"]
    keep, trade = d["mine"]["before"]["window"], d["mine"]["after"]["window"]
    assert trade - keep == pytest.approx(d["mine"]["gain_window"], abs=0.011)
    alt = d["alternative"]["mine"]
    if alt.get("kind") == "waiver" and alt.get("player"):
        claim = keep + alt["gain_window"]
        assert trade - claim == pytest.approx(d["alternative"]["beyond"]["mine"], abs=0.011)
        assert alt["availability_words"]                       # the assumption the screen says under the claim


@needs_db
@pytest.mark.parametrize("case", CASES, ids=["folk", "lloyd"])
def test_the_panel_rows_name_both_players(monkeypatch, case):
    out = _evaluate(monkeypatch, *case)
    d = out["decision"]
    for side in ("mine", "theirs"):
        for c in d["changes"][side]:
            assert c["slot_word"] and (c.get("in_player") or c.get("out_player")), c
            assert c["in_how"] in ("trade", "bench", "free agent", "slot", None)
            assert c["out_why"] in ("traded", "cut", "bench", "free agent no longer needed", "slot", None)
        tot = out["lineups"][side]["total"]
        assert (tot["before"], tot["after"]) == (d[side]["before"]["this_week"], d[side]["after"]["this_week"])
    never = re.compile(r"%|probab|chance (that|of) (they|him)|likely to accept", re.I)
    for w in [*out["card"]["why_refuse"], *out["card"]["why_consider"], *out["card"]["plausibility"]["reasons"]]:
        assert not never.search(w), w


@needs_db
def test_the_market_price_has_its_date(monkeypatch):
    from league_lab_api import provenance as P
    out = P.with_trade(_evaluate(monkeypatch, *CASES[0]))
    assert out["market"]["give"] is not None and out["market"]["get"] is not None
    assert re.search(r"data published \d+ \w{3}, \d+:\d\d (am|pm) ET", out["provenance"]["words"])
