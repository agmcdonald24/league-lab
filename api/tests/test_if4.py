"""Wave I-F, IF-4 — the decision-quality review (docs/reviews/2026-10-03-decision-quality-review.md) § Priority 4 "use
clarity to expose the difficult decisions" and its table of interface and language fixes.

The review's case: League of Scrubs roster 6 "GoodGameBuddy", Williams vs Tuten at FLEX (0.22 apart), the submitted
lineup equal to the optimizer's: the home said "nothing to change". The main-database clone has the rosters of
2026-09-26, when Tuten was on roster 2 — so the case is built from the clone's own rows: roster 6's lineup with
Tuten's real row (from roster 2) in CeeDee Lamb's FLEX slot, Williams on the bench, and Sleeper's lineup = the
optimizer's. No number moves: the cards' numbers are the rows' own.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

import pandas as pd
import pytest
from league_lab import injury_feed as F
from league_lab import news_feed as NF

from league_lab_api import availability as AV
from league_lab_api import myweek, news
from league_lab_api.applib import cards

from .conftest import SCRUBS, needs_db
from .test_ic4 import ESPN
from .test_ie1 import _card, _rows

WILLIAMS, TUTEN = "00-0037240", "00-0040719"


def _plain(md: str) -> str:
    return re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", md or "")


@pytest.fixture
def overlay(monkeypatch):
    """The availability overlay and the news line from the ESPN fixtures (a test never calls ESPN)."""
    monkeypatch.setenv(F.FIXTURES_ENV, str(ESPN))
    monkeypatch.delenv(AV.SWITCH_ENV, raising=False)
    monkeypatch.delenv(NF.SWITCH_ENV, raising=False)
    F.reset()
    news.reset()
    AV._snap = None
    AV._built = None
    AV.clear_context()
    yield
    F.reset()
    news.reset()
    AV._snap = None
    AV.clear_context()


@pytest.fixture
def no_overlay(monkeypatch):
    monkeypatch.setenv(AV.SWITCH_ENV, "off")
    monkeypatch.setenv(NF.SWITCH_ENV, "off")
    AV.clear_context()
    yield
    AV.clear_context()


def _roster6_with_tuten(monkeypatch) -> dict:
    """cards.lineup_rows for roster 6 = the clone's rows with Tuten's real row (roster 2's) in Lamb's FLEX slot; Sleeper's
    lineup = the optimizer's starters. Returns {"tuten": value, "williams": value} as the rows hold them."""
    orig = cards.lineup_rows
    seen: dict = {}

    def rows_for(league_id, season, week, roster_id):
        base = orig(league_id, season, week, roster_id)
        if str(league_id) != SCRUBS or int(roster_id) != 6 or base.empty:
            return base
        other = orig(league_id, season, week, 2)
        t = other[other["gsis_id"] == TUTEN]
        lamb = base[(base["role"] == "starter") & base["slot"].astype(str).str.startswith("FLEX")
                    & (base["position"] == "WR") & (base["gsis_id"] != WILLIAMS)].sort_values("value")
        assert not t.empty and not lamb.empty, "the clone lost Tuten or roster 6's FLEX receivers"
        out = base.drop(index=lamb.index[:1]).copy()
        tut = t.iloc[0].copy()
        wi = out.index[out["gsis_id"] == WILLIAMS][0]
        will = out.loc[wi].copy()
        # the optimizer's pick starts at Lamb's FLEX (the higher projection), the other one takes Williams's bench place
        up, down = (tut, will) if float(tut["value"]) >= float(will["value"]) else (will, tut)
        slot_cols = [c for c in ("roster_id", "slot", "slot_type", "slot_order", "role", "lineup_value", "bench_value",
                                 "bench_rank", "is_weakest_slot", "margin", "team_name", "manager_name") if c in out.columns]
        bench_src, flex_src = out.loc[wi], lamb.iloc[0]
        for c in slot_cols:
            up[c], down[c] = flex_src[c], bench_src[c]
        up["margin"] = round(float(up["value"]) - float(down["value"]), 2)     # the other one is the best bench player at FLEX
        out = out.drop(index=[wi])
        out = pd.concat([out, up.to_frame().T, down.to_frame().T], ignore_index=True)
        for c in base.columns:                                                  # concat of a Series loses dtypes
            try:
                out[c] = out[c].astype(base[c].dtype)
            except (TypeError, ValueError):
                pass
        order = {"starter": 0, "bench": 1, "unplayable": 2}                     # the frame's own order (slot, then bench rank)
        out = out.assign(_o=out["role"].map(order).fillna(3)).sort_values(["_o", "slot_order", "bench_rank"]).drop(columns="_o")
        out = out.reset_index(drop=True)
        seen.update(start=str(up["gsis_id"]), other=str(down["gsis_id"]), start_value=float(up["value"]),
                    other_value=float(down["value"]), margin=float(up["margin"]), tuten=float(tut["value"]),
                    williams=float(will["value"]))
        return out

    monkeypatch.setattr(cards, "lineup_rows", rows_for)

    def optimizer_lineup(league_id, roster_id, *, house):
        r = rows_for(league_id, cards.league_season(league_id), cards.decision_week(cards.league_season(league_id)), roster_id)
        st = r[(r["role"] == "starter") & r["sleeper_player_id"].map(lambda s: isinstance(s, str))]
        return {str(s): str(t) for s, t in zip(st["sleeper_player_id"], st["slot_type"], strict=False)}

    monkeypatch.setattr(myweek, "current_starters", optimizer_lineup)
    return seen


# ------------------------------------------------------------------ 1. Decisions worth reviewing
@needs_db
def test_scrubs_roster6_williams_tuten_no_clear_upgrade(client, no_overlay, monkeypatch):
    seen = _roster6_with_tuten(monkeypatch)
    r = client.get(f"/api/my-week?league={SCRUBS}&team=6")
    assert r.status_code == 200, r.text
    d = r.json()
    print("roster 6:", seen, "| actions:", [a["action"] for a in d["actions"]], "| review:", [x["words"] for x in d["review"]],
          "| set:", d["set_line"])
    flex = [c for c in d["cards"] if {c["gsis_id"], c["alt_gsis_id"]} == {TUTEN, WILLIAMS}]
    assert len(flex) == 1 and flex[0]["strength"] == "coin flip" and flex[0]["status"] == "close"
    c = flex[0]
    # numbers do not move: the card's numbers are the rows' own
    assert (c["gsis_id"], c["value"], c["alt_value"], c["margin"]) == (seen["start"], seen["start_value"], seen["other_value"], seen["margin"])
    # not an action (the lineup already follows the optimizer) ...
    assert all("Tuten" not in _plain(a["action"]) and "Williams" not in _plain(a["action"]) for a in d["actions"])
    # ... but discoverable: "No clear upgrade", never "nothing to change"
    rv = [x for x in d["review"] if {x["start"]["gsis_id"], x["other"]["gsis_id"]} == {TUTEN, WILLIAMS}]
    assert len(rv) == 1
    x = rv[0]
    sn, on = ("Tuten", "Williams") if seen["start"] == TUTEN else ("Williams", "Tuten")
    assert x["kind"] == "no_clear_upgrade" and x["slot_label"] == "FLEX" and x["submitted"] is True
    assert x["start"]["name"] == sn and x["other"]["name"] == on and x["start"]["gsis_id"] == seen["start"]
    assert _plain(x["words"]) == (f"{on} or {sn} at FLEX: a coin flip, {seen['margin']:.1f} points apart; "
                                  f"your lineup has {sn} — no clear upgrade.")
    assert x["compare"] == {"a": seen["other"], "b": seen["start"]} and x["margin"] == seen["margin"]
    assert x["cards"] == [d["cards"].index(c)]
    assert d["set_line"] == myweek.SET_ELSEWHERE == "No clear upgrade elsewhere."
    assert "nothing to change" not in (d["set_line"] or "")
    assert d["changed"] == {"lines": [], "empty": "Nothing has changed since the morning build."}


def test_review_rules_on_hand_built_frames():
    rows = _rows([("1", "RB1", "RB", 15.0), ("2", "FLEX1", "RB", 10.02)], [("3", "WR", 9.80), ("4", "WR", 5.0)])
    coin = _card("2", "3", 0.22, "close", "coin flip")
    coin["slot"] = "FLEX1"
    # set as the optimizer has it: one line, the set line says so
    res = myweek.build_actions(rows, [coin], {"1": "RB", "2": "FLEX"}, SCRUBS)
    assert res["actions"] == [] and len(res["review"]) == 1 and res["set_line"] == "No clear upgrade elsewhere."
    assert _plain(res["review"][0]["words"]) == ("3 or 2 at FLEX: a coin flip, 0.2 points apart; your lineup "
                                                 "has 2 — no clear upgrade.")            # (the frame's names: "Player 3")
    # the submitted lineup has the other one (0.22 apart: not an action either) — the line names him
    res = myweek.build_actions(rows, [dict(coin)], {"1": "RB", "3": "FLEX"}, SCRUBS)
    assert res["actions"] == [] and res["review"][0]["start"]["key"] == "3"
    assert "your lineup has 3" in _plain(res["review"][0]["words"]) and "less than half a point" in res["set_line"]
    # IF-3's flag: the matchup rank does not settle it
    res = myweek.build_actions(rows, [{**coin, "matchup_uncertain": True}], {"1": "RB", "2": "FLEX"}, SCRUBS)
    assert _plain(res["review"][0]["words"]).endswith("your lineup has 2; the matchup rank does not settle it — no clear upgrade.")
    assert res["review"][0]["matchup_uncertain"] is True
    # unknown submitted lineup: "our lineup", no set line
    res = myweek.build_actions(rows, [dict(coin)], None, SCRUBS)
    assert "our lineup has 2" in _plain(res["review"][0]["words"]) and res["set_line"] is None
    # a clear call already set: nothing to review, the set line as before; a set lineup with no close call at all
    res = myweek.build_actions(rows, [_card("2", "3", 4.0, "set", "clear")], {"1": "RB", "2": "FLEX"}, SCRUBS)
    assert res["review"] == [] and res["set_line"] == myweek.SET_ALL
    # a coin flip with an injury in it stays an action (IE-1), not a review line
    rows_q = _rows([("1", "RB1", "RB", 15.0), ("2", "FLEX1", "RB", 10.02, "Questionable")], [("3", "WR", 9.80)])
    res = myweek.build_actions(rows_q, [_card("2", "3", 0.22, "close", "coin flip", {"kind": "injury", "pick": "3", "side": "alt"})],
                               {"1": "RB", "3": "FLEX"}, SCRUBS)
    assert [a["kind"] for a in res["actions"]] == ["close"] and res["review"] == []
    assert res["set_line"] == myweek.SET_REST == "The rest of your lineup is set."


# ------------------------------------------------------------------ 2. What changed
@needs_db
def test_what_changed_from_the_overlay_fixture(client, overlay):
    """Scrubs roster 2 (the ESPN fixture: Justin Jefferson Out since the build): his status line with the feed and the
    time, then the news of the week's players from the last 24 hours — at most five lines."""
    d = client.get(f"/api/my-week?league={SCRUBS}&team=2").json()
    ch = d["changed"]
    print("changed:", ch)
    assert 1 <= len(ch["lines"]) <= myweek.MAX_CHANGED
    st = [x for x in ch["lines"] if x["kind"] == "status"]
    assert st and "Jefferson" in st[0]["text"] and st[0]["source"] and st[0]["at"]
    assert ch["lines"][0]["kind"] == "status"                       # the status changes lead
    nw = [x for x in ch["lines"] if x["kind"] == "news"]
    assert nw and nw[0]["source"] == "RotoWire via ESPN" and nw[0]["about"] == "player"
    assert nw[0]["text"].startswith("Jefferson (ankle) has been already been ruled out")


def test_nothing_changed_words():
    assert myweek.what_changed({"changes": []}, pd.DataFrame()) == {"lines": [], "empty": "Nothing has changed since the morning build."}
    assert myweek.what_changed(None, None)["lines"] == []


# ------------------------------------------------------------------ the news line: the item about him first
def test_news_item_about_him_first():
    items = [{"headline": "Fantasy football Week 4 inactives: Daniels, DeVonta to sit; McConkey questionable", "date": "2026-10-03T00:59:53Z",
              "source": "ESPN", "url": "https://www.espn.com/x"},
             {"headline": "Williams caught four passes for 52 yards in Sunday's win.", "date": "2026-10-01T12:00:00Z",
              "source": "RotoWire via ESPN", "url": "https://www.espn.com/y"},
             {"headline": "Lions' Jameson Williams: deep threat vs Carolina", "date": "2026-09-30T12:00:00Z", "source": "ESPN",
              "url": "https://www.espn.com/z"}]
    out = news.ordered(items, "Jameson Williams")
    assert [x["about"] for x in out] == ["player", "player", "league"]
    assert out[0]["source"] == "RotoWire via ESPN" and out[-1]["headline"].startswith("Fantasy football Week 4 inactives")
    assert news.about({"headline": "DeVonta Smith out", "source": "ESPN"}, "Jameson Williams") == "league"
    assert news.about({"headline": "Odell Beckham Jr. returns", "source": "ESPN"}, "Odell Beckham Jr.") == "player"
    assert news.about({"headline": "Williamson signs", "source": "ESPN"}, "Jameson Williams") == "league"


def test_news_for_card_and_recent_on_the_fixture(overlay):
    jj = "00-0036322"                                   # Justin Jefferson (ESPN 4262921 in the fixture id table)
    card = news.for_card(jj, "Justin Jefferson")
    # the three newest: RotoWire (Oct 3), the inactives story (Oct 3, names "DeVonta", not him), RotoWire (Oct 2):
    # the story moves behind the two blurbs about him and is labelled league news
    assert [x["about"] for x in card] == ["player", "player", "league"]
    assert card[0]["source"] == "RotoWire via ESPN" and card[2]["headline"].startswith("Fantasy football Week 4 inactives")
    rec = news.recent([jj], names={jj: "Justin Jefferson"})
    assert len(rec) == 1 and rec[0][0] == jj and rec[0][1]["about"] == "player"
    assert datetime.fromisoformat(rec[0][1]["date"].replace("Z", "+00:00")) > datetime(2026, 10, 2, 18, 47, tzinfo=UTC)


# ------------------------------------------------------------------ the e2e's recorded answers (web/e2e/if4)
@needs_db
@pytest.mark.skipif(not __import__("os").environ.get("IF4_RECORD"), reason="records web/fixtures/if4/api_if4.json: IF4_RECORD=1")
def test_record_e2e_answers(client, monkeypatch, overlay):
    """The answers the web's e2e replays (the review's roster 6 case as built above, roster 2 with the overlay's
    changes, Williams's card for the pane, the status line), keyed like web/e2e/ie1's recordings."""
    import json
    from pathlib import Path
    from urllib.parse import urlencode

    def key(path: str, **q) -> str:
        return path + ("?" + urlencode(sorted((k, str(v)) for k, v in q.items())) if q else "")

    out: dict = {}

    def rec(path: str, **q):
        r = client.get(key(path, **q))
        out[key(path, **q)] = {"status": r.status_code, "body": r.json()}

    rec("/api/my-week", league=SCRUBS, team=2)                          # the overlay on: what changed
    rec("/api/status")
    monkeypatch.setenv(AV.SWITCH_ENV, "off")
    AV.clear_context()
    _roster6_with_tuten(monkeypatch)
    rec("/api/my-week", league=SCRUBS, team=6)                          # the review's case: no clear upgrade
    rec(f"/api/player/{WILLIAMS}", league=SCRUBS, team=6)
    rec(f"/api/player/{TUTEN}", league=SCRUBS, team=6)
    f = Path(__file__).resolve().parents[2] / "web" / "fixtures" / "if4" / "api_if4.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(out, indent=1, default=str) + "\n")
    assert all(v["status"] == 200 for v in out.values()), {k: v["status"] for k, v in out.items()}
