"""IZ-4 (Wave I-Z; the review's Pass 2: "surface sourced injury / personnel changes beside the affected decision").

A news item about a player in one of My Week's decisions sits on that decision and leaves the feed; the trade's section
5 carries the same line per player; nothing is inferred from news text — the decisions, their order and every number
are identical with the feed on and off (both paths)."""

from __future__ import annotations

import copy

import pandas as pd
import pytest
from league_lab import clock

from league_lab_api import decision_news, news

from .conftest import SCRUBS, needs_db

SATURDAY = "2026-10-10T16:00:00Z"
JEFFERSON = "00-0036322"
KELCE = "00-0030506"          # in a decision on both paths at the Saturday clock: "Your tight end spot is open: Kelce is on a bye"


def _line(g: str | None, at: str, text: str = "x") -> dict:
    return {"kind": "news", "gsis_id": g, "player_name": "Justin Jefferson" if g == JEFFERSON else "Someone", "text": text,
            "source": "RotoWire via ESPN", "at": at, "url": None, "forecast_status": "contextual",
            "forecast_words": "Context only: not in the projection"}


def _answer(lines: list[dict]) -> dict:
    act = {"kind": "close", "start": [{"key": "13346", "name": "Boston"}], "sit": [{"key": "6794", "name": "Jefferson"}]}
    rev = {"kind": "no_clear_upgrade", "start": {"key": "9487", "gsis_id": "00-0039000"}, "other": {"key": "8150", "gsis_id": "00-0037746"}}
    return {"actions": [act], "more_actions": [], "review": [rev], "changed": {"lines": lines, "empty": "…"}}


ROWS = pd.DataFrame([{"sleeper_player_id": "13346", "gsis_id": "00-0041037"}, {"sleeper_player_id": "6794", "gsis_id": JEFFERSON}])


def test_a_line_about_a_decisions_player_moves_onto_it_and_leaves_the_feed():
    lines = [_line(JEFFERSON, "2026-10-11T15:00:00Z", "pregame workout"), _line("00-0099999", "2026-10-11T16:00:00Z", "other")]
    out = decision_news.attach(_answer(lines), ROWS)
    a = out["actions"][0]
    assert [x["text"] for x in a["news"]] == ["pregame workout"] and a["news_more"] == []
    assert a["news"][0]["forecast_words"] == "Context only: not in the projection"
    assert [x["text"] for x in out["changed"]["lines"]] == ["other"] and out["changed"]["on_decisions"] == 1
    assert out["review"][0]["news"] == []


def test_two_on_the_decision_the_newest_first_the_rest_for_why():
    lines = [_line(JEFFERSON, "2026-10-11T10:00:00Z", "old"), _line(JEFFERSON, "2026-10-11T15:00:00Z", "newest"),
             _line("00-0041037", "2026-10-11T12:00:00Z", "boston"), _line("00-0037746", "2026-10-11T09:00:00Z", "review")]
    out = decision_news.attach(_answer(lines), ROWS)
    a = out["actions"][0]
    assert [x["text"] for x in a["news"]] == ["newest", "boston"] and [x["text"] for x in a["news_more"]] == ["old"]
    assert [x["text"] for x in out["review"][0]["news"]] == ["review"]
    assert out["changed"]["lines"] == []                     # nothing left: the screen draws no feed (IX-4's rule)


def test_no_lines_nothing_moves():
    out = decision_news.attach(_answer([]), ROWS)
    assert out["actions"][0]["news"] == [] and out["changed"]["lines"] == [] and out["changed"]["on_decisions"] == 0


def _item(headline: str) -> dict:
    return {"headline": headline, "date": "2026-10-10T14:00:00Z", "source": "RotoWire via ESPN", "url": None, "about": "player"}


def _strip(d: dict) -> dict:
    """The answer without the news: every decision's fields but `news` / `news_more`, the cards, the lineups, the
    numbers."""
    keep = {k: copy.deepcopy(d.get(k)) for k in ("actions", "more_actions", "review", "cards", "lineup", "lineup_full",
                                                  "recommended", "matchup", "win", "lineup_value", "set_line", "league_line")}
    for k in ("actions", "more_actions", "review"):
        for x in keep[k] or []:
            x.pop("news", None)
            x.pop("news_more", None)
    return keep


@needs_db
@pytest.mark.parametrize("source", ["", "&source=sleeper"])          # the house path and the on-demand path
def test_the_feed_on_and_off_gives_the_same_decisions_and_numbers(client, monkeypatch, source):
    url = f"/api/my-week?league={SCRUBS}&team=2{source}"
    monkeypatch.setattr(news, "recent", lambda ids, **k: [])
    with clock.pinned(SATURDAY):
        off = client.get(url).json()
    monkeypatch.setattr(news, "recent", lambda ids, **k: [(KELCE, _item("Kelce (illness) is expected to travel with the team"))]
                        if KELCE in ids else [])
    with clock.pinned(SATURDAY):
        on = client.get(url).json()
    assert _strip(on) == _strip(off)                             # no number, verdict or order reads the news
    decs = [x for k in ("actions", "more_actions", "review") for x in on.get(k) or []]
    hit = [x for x in decs if any(n.get("gsis_id") == KELCE for n in x.get("news") or [])]
    assert hit, "the item sits on the decision that names Kelce"
    assert "Kelce" in hit[0]["action"]
    assert hit[0]["news"][0]["text"] == "Kelce (illness) is expected to travel with the team"
    assert hit[0]["news"][0]["source"] == "RotoWire via ESPN"
    assert not any(ln.get("gsis_id") == KELCE for ln in on["changed"]["lines"])       # left the feed
    assert on["changed"]["on_decisions"] == 1


def test_the_trade_section_5_line_by_player(monkeypatch):
    ans = {"give": [{"gsis_id": JEFFERSON, "sleeper_id": "6794", "player_name": "Justin Jefferson"}],
           "get": [{"gsis_id": "00-0041037", "sleeper_id": "13346", "player_name": "Denzel Boston"}], "cut": []}
    monkeypatch.setattr(news, "recent", lambda ids, **k: [(JEFFERSON, _item("pregame workout"))])
    out = decision_news.with_trade(dict(ans))
    assert list(out["news"]) == ["6794"]
    ln = out["news"]["6794"][0]
    assert ln["text"] == "pregame workout" and ln["source"] == "RotoWire via ESPN" and ln["why_here"] is None
    assert ln["forecast_words"] == "Context only: not in the projection"
    monkeypatch.setattr(news, "recent", lambda ids, **k: [])
    assert decision_news.with_trade(dict(ans))["news"] == {}
