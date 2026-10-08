"""IR-1 (Wave I-R): nobody who cannot play is ranked, valued or projected — each route with a hand-built snapshot (a
top player on IR, one ruled Out today by ESPN, one suspended, one released), the route with the overlay off (the
stored record alone), the start answer, the free calculator and the rest-of-season lists."""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import pytest
from league_lab import availability_gate as AG

from league_lab_api import availability as AV
from league_lab_api import freetrade as FT
from league_lab_api import rankings_api as RK

from .conftest import needs_db

ROUTE, START, CALC = "/api/rankings", "/api/rankings/start", "/api/trade-calc/free"
SEP28 = datetime(2026, 9, 28, 14, 0, tzinfo=UTC)
TODAY = datetime(2026, 10, 3, 15, 0, tzinfo=UTC)
CODES = (("IR", "Sleeper", SEP28, "knee - acl"), ("OUT", "ESPN", TODAY, "ankle"), ("SUS", "Sleeper", SEP28, None),
         ("NO_TEAM", "Sleeper", SEP28, None))


def _st(code, source="Sleeper", when=SEP28, note=None) -> dict:
    return AG.classify(AG.entry(code, source, as_of=when, note=note))


def _snapshot(monkeypatch, by_gsis: dict[str, dict]) -> None:
    """Every list reads this snapshot (statuses), and no stored record."""
    def fake(gsis_ids, season, week, **kw):
        want = None if gsis_ids is None else set(gsis_ids)
        return {g: {"gsis_id": g, **s} for g, s in by_gsis.items() if want is None or g in want}
    monkeypatch.setattr(AV, "statuses", fake)
    monkeypatch.setattr(AV, "stored_status", lambda season, week: {})
    RK.clear()


# ------------------------------------------------------------------------------ the pieces, no database
def test_the_list_splits_on_the_definition():
    d = pd.DataFrame({"key": list("abcde"), "gsis_id": list("abcde"), "player_name": ["A", "B", "C", "D", "E"],
                      "position": "RB", "team": "X", "proj_points": [20.0, 18.0, 16.0, 14.0, 12.0],
                      "report_status": [None, None, None, None, "Questionable"]})
    st = {"a": _st("IR", note="knee - acl"), "b": _st("OUT", "ESPN", TODAY), "c": _st("DOUBTFUL", "ESPN", TODAY),
          "e": _st("QUESTIONABLE", "ESPN", TODAY)}
    gate = {"st": st, "out": frozenset({"a", "b"}), "stored": frozenset()}
    keep, gone = RK._split_not_playing(d, gate, "week")
    assert list(keep["gsis_id"]) == ["c", "d", "e"]                              # Doubtful flagged, not removed
    assert keep.set_index("gsis_id").loc["c", "availability"]["status"] == "Doubtful"
    assert keep.set_index("gsis_id").loc["c", "report_status"] == "Doubtful"
    assert [g["gsis_id"] for g in gone] == ["a", "b"]                            # out indefinitely first
    assert gone[0]["why"] == "IR (knee - acl) · Sleeper, Sep 28" and gone[0]["words"].startswith("On injured reserve")
    assert gone[1]["words"] == "Ruled out this week: he will not play this week, so he is not ranked."
    # the season: the rows the mart does not rank leave; listed only when out indefinitely
    s = d.assign(_ranked=[False, True, True, False, True])
    keep, gone = RK._split_not_playing(s, {"st": st, "out": frozenset({"a"}), "stored": frozenset()}, "season")
    assert list(keep["gsis_id"]) == ["b", "c", "e"] and [g["gsis_id"] for g in gone] == ["a"]
    assert gone[0]["words"] == "On injured reserve: no return date, so no rest-of-season value."


def test_a_player_cleared_since_last_nights_zero_has_no_number_until_the_update():
    d = pd.DataFrame({"key": ["a", "b"], "gsis_id": ["a", "b"], "player_name": ["A", "B"], "position": "RB",
                      "team": "X", "proj_points": [0.0, 9.0], "report_status": [None, None]})
    keep, gone = RK._split_not_playing(d, {"st": {}, "out": frozenset(), "stored": frozenset({"a"})}, "week")
    assert list(keep["gsis_id"]) == ["b"] and gone[0]["code"] == "BACK"
    assert "comes with the next update" in gone[0]["words"]


def test_statuses_the_freshest_word_and_the_overlay_off():
    stored = {"a": AG.entry("IR", "Sleeper", as_of=SEP28), "b": AG.entry("IR", "Sleeper", as_of=SEP28)}
    live = {"b": [AG.entry("ACTIVE", "Sleeper", as_of=TODAY)], "c": [AG.entry("OUT", "ESPN", as_of=TODAY)],
            "d": [AG.entry("NO_TEAM", "Sleeper", as_of=TODAY)]}
    got = AV.statuses(None, None, None, stored=stored, live=live)
    assert set(got) == {"a", "c"}                     # b activated since; d: a free agent the stored gate did not see
    assert got["a"]["out_indefinitely"] and got["c"]["cannot_play"] and not got["c"]["out_indefinitely"]
    off = AV.statuses(["a", "c"], None, None, overlay=False, stored=stored)      # the overlay off: the record still rules
    assert set(off) == {"a"}


def test_the_rest_of_season_answer_lists_who_is_out_indefinitely(monkeypatch):
    _snapshot(monkeypatch, {"a": _st("IR", note="knee - acl"), "b": _st("OUT", "ESPN", TODAY)})
    out = AV.ros_gate({"players": [{"gsis_id": "a", "player_name": "A", "ros_points": 80.0},
                                   {"gsis_id": "b", "player_name": "B", "ros_points": 70.0},
                                   {"gsis_id": "c", "player_name": "C", "ros_points": 60.0}]}, season=2026, week=5)
    assert [p["gsis_id"] for p in out["players"]] == ["b", "c"]
    assert out["players"][0]["availability"]["cannot_play"] is True and out["players"][0]["injury_status"] == "Out"
    assert out["not_playing"][0]["gsis_id"] == "a" and "no rest-of-season value" in out["not_playing"][0]["words"]


def test_the_calculator_refuses_to_price_a_player_out_indefinitely():
    give = FT._side([FT._player("a", {"player_name": "A", "position": "RB", "ros_points": 90.0, "value": 30.0,
                                      "value_rank_pos": 3, "ros_games": 13}, None, 5, {}, _st("IR", note="knee - acl"))])
    get = FT._side([FT._player("b", {"player_name": "B", "position": "WR", "ros_points": 80.0, "value": 20.0,
                                     "value_rank_pos": 9, "ros_games": 13}, None, 5, {}, None)])
    v = FT.verdict(give, get)
    assert v["not_priced"] is True and v["gap"] is None and v["lean"] is None
    assert v["words"].startswith("Not priced: A — On injured reserve: no return date, so no rest-of-season value.")
    assert give["players"][0]["value"] is None and give["value"] is None
    # out this week only: valued, this week's number withheld with the reason
    p = FT._player("c", {"player_name": "C", "position": "RB", "ros_points": 70.0, "value": 10.0, "value_rank_pos": 12,
                         "ros_games": 12, "weeks_json": [[5, 0.0], [6, 7.0]]}, {"points": 0.0}, 5, {},
                   _st("OUT", "ESPN", TODAY))
    assert p["value"] == 10.0 and p["outlook"]["points"] is None and "will not play this week" in p["outlook"]["out"]


def test_the_new_cache_is_a_registered_region():
    from league_lab import memo
    assert "availability_gate" in memo.BUDGET.regions


# ------------------------------------------------------------------------------ the routes on the database
def _top(client, pos="RB", view="week", n=8) -> list[dict]:
    return client.get(ROUTE, params={"league": "ref:half", "position": pos, "view": view, "limit": 200}).json()["rows"][:n]


@needs_db
def test_rankings_week_a_hand_built_snapshot(client, monkeypatch):
    _snapshot(monkeypatch, {})
    top = _top(client)
    snap = {r["gsis_id"]: _st(c, s, w, n) for r, (c, s, w, n) in zip(top, CODES, strict=False)}
    _snapshot(monkeypatch, snap)
    d = client.get(ROUTE, params={"league": "ref:half", "position": "RB", "limit": 200}).json()
    ids = [r["gsis_id"] for r in d["rows"]]
    assert not set(snap) & set(ids)                                            # not ranked
    assert [r["rank"] for r in d["rows"]] == list(range(1, len(ids) + 1))
    assert d["rows"][0]["gsis_id"] == top[4]["gsis_id"] and d["rows"][0]["tier"] == 1   # the tiers start without them
    np_ = {r["gsis_id"]: r for r in d["not_playing"]}
    assert set(np_) == set(snap)
    assert np_[top[0]["gsis_id"]]["why"] == "IR (knee - acl) · Sleeper, Sep 28"
    assert np_[top[1]["gsis_id"]]["source"] == "ESPN" and np_[top[1]["gsis_id"]]["status"] == "Out"
    assert all(r["words"] and "proj_points" not in r for r in d["not_playing"])
    assert d["not_playing_words"] == RK.NOT_PLAYING_WORDS["week"]
    # FLEX the same; the search filters "Not playing" like the list
    flex = client.get(ROUTE, params={"league": "ref:half", "position": "FLEX", "limit": 200}).json()
    assert not set(snap) & {r["gsis_id"] for r in flex["rows"]}
    name = top[0]["player_name"]
    q = client.get(ROUTE, params={"league": "ref:half", "position": "RB", "q": name}).json()
    assert [r["gsis_id"] for r in q["not_playing"]] == [top[0]["gsis_id"]] and q["rows"] == []


@needs_db
def test_rankings_season_leaves_out_only_who_is_out_indefinitely(client, monkeypatch):
    _snapshot(monkeypatch, {})
    top = _top(client, view="season")
    snap = {r["gsis_id"]: _st(c, s, w, n) for r, (c, s, w, n) in zip(top, CODES, strict=False)}
    _snapshot(monkeypatch, snap)
    d = client.get(ROUTE, params={"league": "ref:half", "position": "RB", "view": "season", "limit": 200}).json()
    ids = {r["gsis_id"] for r in d["rows"]}
    assert top[0]["gsis_id"] not in ids and top[2]["gsis_id"] not in ids       # IR, suspended: no season number
    assert top[1]["gsis_id"] in ids                                            # out this week only: keeps his season
    assert {r["gsis_id"] for r in d["not_playing"]} == {top[0]["gsis_id"], top[2]["gsis_id"]}
    assert all("no rest-of-season value" in r["words"] for r in d["not_playing"])


@needs_db
def test_rankings_with_the_overlay_off_the_stored_record_still_applies(client, monkeypatch):
    monkeypatch.setattr(AV, "stored_status", lambda season, week: {})
    RK.clear()
    top = _top(client)
    g = top[0]["gsis_id"]
    monkeypatch.setattr(AV, "enabled", lambda: False)
    monkeypatch.setattr(AV, "stored_status", lambda season, week: {g: AG.entry("IR", "Sleeper", as_of=SEP28, note="knee - acl")})
    RK.clear()
    d = client.get(ROUTE, params={"league": "ref:half", "position": "RB", "limit": 200}).json()
    assert g not in {r["gsis_id"] for r in d["rows"]} and d["not_playing"][0]["gsis_id"] == g


@needs_db
def test_who_should_i_start_says_he_is_out_never_a_call(client, monkeypatch):
    _snapshot(monkeypatch, {})
    top = _top(client)
    a, b, c = top[0], top[5], top[6]
    _snapshot(monkeypatch, {a["gsis_id"]: _st("IR", note="knee - acl")})
    d = client.get(START, params={"league": "ref:half", "ids": f"{a['gsis_id']},{b['gsis_id']}"}).json()
    assert d["answer"]["verdict"] == "out" and d["answer"]["pick"] == b["gsis_id"]
    assert " is out — on injured reserve (IR (knee - acl) · Sleeper, Sep 28)." in d["answer"]["words"]
    assert d["answer"]["words"].endswith(".") and "Start " in d["answer"]["words"]
    assert d["out"][0]["gsis_id"] == a["gsis_id"] and a["gsis_id"] not in {p["gsis_id"] for p in d["players"]}
    assert d["missing"] == []
    # three players, one out: the call is among the other two, after the sentence
    d3 = client.get(START, params={"league": "ref:half", "ids": f"{a['gsis_id']},{b['gsis_id']},{c['gsis_id']}"}).json()
    assert d3["answer"]["verdict"] in ("clear", "a lean", "a coin flip")
    assert " is out — " in d3["answer"]["words"] and "Of the others: " in d3["answer"]["words"]
    assert {p["gsis_id"] for p in d3["players"]} == {b["gsis_id"], c["gsis_id"]}


@needs_db
def test_the_free_calculator_route_refuses_a_trade_on_a_player_out_indefinitely(client, monkeypatch):
    _snapshot(monkeypatch, {})
    top = _top(client, view="season")
    _snapshot(monkeypatch, {top[0]["gsis_id"]: _st("IR", note="knee - acl")})
    r = client.get(CALC, params={"league": "ref:half", "give": top[0]["gsis_id"], "get": top[3]["gsis_id"]})
    assert r.status_code == 200
    v = r.json()["verdict"]
    assert v["not_priced"] is True and v["words"].startswith("Not priced: ")


@pytest.mark.parametrize("path", [ROUTE, START, CALC])
def test_the_routes_stay_in_their_buckets(path):
    from league_lab_api import ratelimit
    assert ratelimit.bucket_for("GET", path) in ("research", "read")
