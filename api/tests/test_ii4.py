"""Wave I-I (II-4): the Season views apart, news as a decision-impact feed, the home's clocks (the product and analytics
review § 5–8; INTERFACES.md § II-4; docs/METRICS.md § "Value to my lineup" → "The three views").

* Season: `view=outlook` (My roster outlook — your players only), `view=upgrades` (Potential upgrades — before
  acquisition cost; free agents → the add / drop, rostered players → the trade calculator), `view=projections`
  (Rest-of-season projections). Each states its counterfactual and the costs it includes / leaves out; the numbers are
  IB-3's and F2's unchanged (the same rows, the same values as `view=lineup` / `view=points`); injury cover is apart and
  never added to the lineup value.
* "What changed": every line carries what_changed / why_here / decision_status / forecast_status / next_step; the
  forecast status is "included" only with a recorded update (the overlay's applied status, or the report already in the
  rows), never for a headline alone; an injury item newer than the last check is "pending"; a recap ranks after every
  development; the same event shows once.
* The clocks: data built / injuries checked / news, apart — stamps, never a stale warning.
"""

from __future__ import annotations

import pandas as pd
import pytest

from league_lab_api import myweek, ondemand

from .conftest import SCRUBS, needs_db
from .test_if4 import overlay  # noqa: F401 - the ESPN fixture overlay (Jefferson Out since the build)

TEST_LEAGUE = "9000000000000000001"


def _key(p: dict) -> str:
    return str(p.get("player_key") or p.get("gsis_id"))


# ------------------------------------------------------------------------------------------------ the three views
def test_the_three_views_state_their_counterfactuals():
    cf = ondemand.COUNTERFACTUAL
    assert set(cf) == set(ondemand.SEASON_VIEWS) == {"outlook", "upgrades", "projections"}
    assert ondemand.SEASON_LABELS == {"outlook": "My roster outlook", "upgrades": "Potential upgrades",
                                      "projections": "Rest-of-season projections"}
    assert "loses" in cf["outlook"] and "injury cover is shown apart and is not added in" in cf["outlook"]
    assert cf["upgrades"].startswith("Before acquisition cost") and "nobody dropped and nothing sent" in cf["upgrades"]
    assert "This is not his trade value." in cf["upgrades"]
    assert "no roster, no lineup and no cost" in cf["projections"]
    # an acquisition view names the costs it leaves out
    assert ondemand.COSTS_INCLUDED["upgrades"] == [] and "the players a trade sends" in ondemand.COSTS_NOT_INCLUDED["upgrades"]


def test_cover_is_apart_and_unknown_is_not_zero():
    assert ondemand.cover_of("RB", []) is None
    assert ondemand.cover_of("RB", [None, None]) is None
    c = ondemand.cover_of("RB", [2.0, 4.0, None])
    assert c == {"points": 3.0, "weeks": 2, "words": c["words"]}
    assert "if a starting RB misses a week" in c["words"] and "per week" in c["words"] and "not counted" in c["words"]
    assert "none over the waiver wire" in ondemand.cover_of("WR", [0.0])["words"]


def test_the_views_need_a_team(client):
    for v in ("outlook", "upgrades"):
        r = client.get(f"/api/ros?league={SCRUBS}&view={v}")
        assert r.status_code == 400 and "team" in r.json()["error"]
    assert client.get(f"/api/ros?league={SCRUBS}&view=upgrades&team=2&who=mine").status_code == 400


@needs_db
@pytest.mark.parametrize("league,team", [(SCRUBS, 2), (TEST_LEAGUE, 3)])
def test_outlook_and_upgrades_keep_the_lineup_numbers(league, team):
    """The split moves no number: outlook = the lineup view's own rows, upgrades = everyone else's, value for value."""
    old = {w: ondemand.ros(league, "ALL", 500, view="lineup", team=team, who=w)["players"] for w in ("mine", "fa", "others")}
    before = {_key(p): p["lineup_points"] for w in old for p in old[w]}
    out = ondemand.ros(league, "ALL", 500, view="outlook", team=team)
    assert out["view"] == "outlook" and out["season_view"]["label"] == "My roster outlook"
    assert out["season_view"]["counterfactual"] == ondemand.COUNTERFACTUAL["outlook"]
    assert out["players"] and all(p["lineup_kind"] == "mine" for p in out["players"])
    assert all(p["lineup_points"] == before[_key(p)] for p in out["players"])
    assert [_key(p) for p in out["players"]] == [_key(p) for p in old["mine"]]
    for p in out["players"]:
        assert len(p["lineup_start_weeks"]) == p["lineup_weeks"]
        if p["cover"] is not None:                       # a bench week's edge, never in the value
            assert p["cover"]["weeks"] <= out["window"]["weeks"] - p["lineup_weeks"]
    up = ondemand.ros(league, "ALL", 500, view="upgrades", team=team)
    assert up["season_view"]["key"] == "upgrades" and up["season_view"]["costs_not_included"]
    assert up["players"] and not any(p["lineup_kind"] == "mine" for p in up["players"])
    assert all(p["lineup_points"] == before[_key(p)] for p in up["players"])
    for p in up["players"]:
        a = p["acquire"]
        if p["lineup_kind"] == "fa":
            assert a["kind"] == "add_drop" and a["path"].startswith("/waivers?add=")
        else:
            assert a["kind"] == "trade" and a["path"].startswith("/trade-calc?partner=") and "get=" in a["path"]
    fa = ondemand.ros(league, "ALL", 500, view="upgrades", team=team, who="fa")
    assert fa["who"] == "fa" and all(p["lineup_kind"] == "fa" for p in fa["players"])


@needs_db
def test_projections_are_the_points_view():
    pts = ondemand.ros(SCRUBS, "WR", 40, view="points", team=2)
    pr = ondemand.ros(SCRUBS, "WR", 40, view="projections", team=2)
    assert pr["view"] == "projections" and pr["season_view"]["label"] == "Rest-of-season projections"
    assert [(_key(p), p["ros_points"]) for p in pr["players"]] == [(_key(p), p["ros_points"]) for p in pts["players"]]
    for p in pr["players"]:
        if p["ros_points"] is not None and p["ros_games"]:
            assert p["ros_per_game"] == round(p["ros_points"] / p["ros_games"], 1)


# ------------------------------------------------------------------------------------------------ the news item
def _rows() -> pd.DataFrame:
    return pd.DataFrame([
        {"gsis_id": "g1", "sleeper_player_id": "1", "player_name": "Puka Nacua", "position": "WR", "role": "starter",
         "slot": "WR1", "report_status": "Questionable"},
        {"gsis_id": "g2", "sleeper_player_id": "2", "player_name": "Kyren Williams", "position": "RB", "role": "starter",
         "slot": "RB1", "report_status": None},
        {"gsis_id": "g3", "sleeper_player_id": "3", "player_name": "Tyler Bass", "position": "K", "role": "bench",
         "slot": "BN", "report_status": None},
        {"gsis_id": "g4", "sleeper_player_id": "4", "player_name": "Jordan Mason", "position": "RB", "role": "unplayable",
         "slot": "BN", "report_status": "Out"},
    ])


META = {"checked_at": "2026-10-04T15:00:00Z", "changes": []}


def test_five_parts_and_included_only_with_a_recorded_update():
    lines = [
        {"kind": "news", "gsis_id": "g1", "player_name": "Puka Nacua", "text": "Nacua (hip) was limited at practice Friday.",
         "source": "RotoWire via ESPN", "at": "2026-10-04T12:00:00Z", "url": "https://x"},
        {"kind": "news", "gsis_id": "g2", "player_name": "Kyren Williams", "text": "Williams expected to handle a full workload.",
         "source": "ESPN", "at": "2026-10-04T13:00:00Z", "url": None},
        {"kind": "news", "gsis_id": "g3", "player_name": "Tyler Bass", "text": "Bass has been ruled out with a groin injury.",
         "source": "ESPN", "at": "2026-10-04T16:30:00Z", "url": None},
        {"kind": "news", "gsis_id": "g4", "player_name": "Jordan Mason", "text": "Mason (knee) ruled out for Sunday.",
         "source": "ESPN", "at": "2026-10-04T14:00:00Z", "url": None},
    ]
    out = {x["gsis_id"]: x for x in myweek.decision_feed(lines, META, _rows(), None)}
    for x in out.values():
        assert set(x) >= {"what_changed", "why_here", "decision_status", "forecast_status", "next_step", "priority",
                          "item_kind", "decision_words", "forecast_words"}
        assert x["what_changed"]["source"] and x["what_changed"]["published_at"] and x["what_changed"]["checked_at"]
        assert x["decision_status"] in ("changed", "watch", "none")
        assert x["forecast_status"] in ("included", "contextual", "pending")
    # a hip item on a Questionable starter: watch it, context only (the projection reads no news)
    assert out["g1"]["decision_status"] == "watch" and out["g1"]["forecast_status"] == "contextual"
    assert out["g1"]["why_here"] == "Starts at WR1 in your best lineup this week"
    assert out["g1"]["next_step"] == {"kind": "player", "label": "Inspect Nacua", "gsis_id": "g1"}
    # an ordinary item: no action, context only
    assert out["g2"]["decision_status"] == "none" and out["g2"]["forecast_status"] == "contextual"
    # an injury item newer than the last injury check: the update is pending (never "included")
    assert out["g3"]["forecast_status"] == "pending" and out["g3"]["decision_status"] == "watch"
    assert out["g3"]["why_here"] == "On your bench this week"
    # the report already in the rows (Out since the build): reflected, not counted twice, no action
    assert out["g4"]["forecast_status"] == "included" and out["g4"]["decision_status"] == "none"
    # no headline alone is ever "included"
    assert not any(x["forecast_status"] == "included" for x in out.values() if x["gsis_id"] in ("g1", "g2", "g3"))


def test_status_lines_questionable_recaps_and_dedup():
    lines = [
        {"kind": "news", "gsis_id": "g2", "player_name": "Kyren Williams",
         "text": "Williams rushed 18 times for 92 yards in Sunday's win over the 49ers.", "source": "ESPN",
         "at": "2026-10-04T13:00:00Z"},
        {"kind": "status", "flag": "questionable", "gsis_id": "g1", "player_name": "Puka Nacua",
         "text": "Questionable: Nacua (hip) — your lineup is unchanged", "source": "Injury report (ESPN)",
         "at": "2026-10-04T12:00:00Z"},
        {"kind": "status", "gsis_id": "g4", "text": "Jordan Mason is out (knee) — he was on your bench; the lineup does not change",
         "source": "Injury report (ESPN)", "at": "2026-10-04T11:00:00Z"},
        {"kind": "status", "gsis_id": "g2", "text": "Kyren Williams is out (ankle) — Jordan Mason starts at RB1",
         "source": "Injury report (ESPN)", "at": "2026-10-04T11:30:00Z"},
        {"kind": "status", "gsis_id": "g2", "text": "Kyren Williams is out (ankle) — Jordan Mason starts at RB1",
         "source": "Injury report (ESPN)", "at": "2026-10-04T11:30:00Z"},
    ]
    out = myweek.decision_feed(lines, META, _rows(), None)
    assert len(out) == 4                                              # the same event once
    assert [x["priority"] for x in out] == [1, 2, 3, 4]
    assert [x["decision_status"] for x in out] == ["changed", "watch", "none", "none"]
    ch, q, bench, recap = out
    assert ch["forecast_status"] == "included" and ch["next_step"]["kind"] == "compare"
    assert ch["what_changed"]["event_at"] == "2026-10-04T11:30:00Z" and ch["what_changed"]["published_at"] is None
    assert q["forecast_status"] == "contextual" and "Questionable tag does not change" in q["forecast_words"]
    assert bench["forecast_status"] == "included" and bench["decision_status"] == "none"
    assert recap["item_kind"] == "recap" and recap["forecast_status"] == "contextual"   # recaps after developments


def test_the_words_have_one_meaning():
    assert myweek.DECISION_WORDS == {"changed": "Recommendation changed", "watch": "Watch for confirmation",
                                     "none": "No action currently indicated"}
    assert myweek.FORECAST_WORDS["included"] == "Included in the current projection"
    assert myweek.FORECAST_WORDS["contextual"] == "Context only: not in the projection"
    assert myweek.FORECAST_WORDS["pending"].startswith("Update pending")


def test_clocks_are_three_stamps(monkeypatch):
    monkeypatch.setattr(myweek, "updated_at", lambda: "2026-10-04T11:37:00+00:00")
    ch = {"lines": [{"kind": "news", "at": "2026-10-04T12:00:00Z"}, {"kind": "news", "at": "2026-10-04T13:05:00Z"},
                    {"kind": "status", "at": "2026-10-04T14:00:00Z"}]}
    c = myweek.clocks({"checked_at": "2026-10-04T15:00:00Z"}, ch)
    assert c == {"data_built": "2026-10-04T11:37:00+00:00", "injuries_checked": "2026-10-04T15:00:00Z",
                 "news": "2026-10-04T13:05:00Z"}
    assert myweek.clocks(None, None) == {"data_built": "2026-10-04T11:37:00+00:00", "injuries_checked": None, "news": None}


@needs_db
def test_my_week_feed_on_the_overlay_fixture(client, overlay):  # noqa: F811
    """Scrubs roster 2 with the ESPN fixtures: Jefferson Out since the build (the overlay's recorded change) leads as
    "Recommendation changed" / included; the RotoWire item on his ankle is reflected (included via that record, no
    action) — not counted twice; the clocks are apart."""
    d = client.get(f"/api/my-week?league={SCRUBS}&team=2").json()
    lines = d["changed"]["lines"]
    st = [x for x in lines if x["kind"] == "status" and "Jefferson" in x["text"]]
    assert st and st[0]["decision_status"] == "changed" and st[0]["forecast_status"] == "included"
    assert st[0]["priority"] == 1
    nw = [x for x in lines if x["kind"] == "news" and x["gsis_id"] == st[0]["gsis_id"]]
    assert nw and nw[0]["forecast_status"] == "included" and nw[0]["decision_status"] == "none"
    assert set(d["clocks"]) == {"data_built", "injuries_checked", "news"}
    assert d["clocks"]["injuries_checked"] and d["clocks"]["news"] == max(x["what_changed"]["published_at"] for x in nw)
