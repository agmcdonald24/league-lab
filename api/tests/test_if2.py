"""Wave I-F, IF-2 — trades compete with the simpler alternatives (docs/reviews/2026-10-03-decision-quality-review.md
§ Priority 3). The review's roster: MFL 70587 team 8 "Big Mac Attack" (`fixtures/mfl/70587/`, the ESPN fixture overlay
on). The finder ranks trades by the starter points they add BEYOND the best alternative over the same weeks (standing
pat, the best legal waiver move); the headline is the first card; a trade below the waiver move is marked and worded;
the calculator names its value concepts and keeps the raw rest-of-season totals out of the fairness test.

On this fixture (the clone of 2026-09-26 + the MFL fixture) the best waiver move is the Atlanta Falcons defense for the
open roster spot, +12.81 over weeks 4–7 (the Waivers screen's top claim, the same number); the review's live numbers
(the Arizona team QB, +11.4; the headline trade +1.0 / +9.8) came from the live server's later projections.
"""

from __future__ import annotations

import re

import pytest
from league_lab import anyleague as A
from league_lab import injury_feed as F
from league_lab import mfl_client as M
from league_lab import player_ids as PI
from league_lab import trades as T
from league_lab.roster_value import RosterBoard

from league_lab_api import availability as AV
from league_lab_api import decisions

from .conftest import needs_db
from .test_i0b import IDS, MFL_FX
from .test_ic4 import ESPN

KEY = "mfl:70587"
HOUSTON_QB, CAROLINA_QB, RICE, TUTEN = "mfl:0682", "mfl:0677", "10229", "12490"
RAW_FAIRNESS = re.compile(r"rest-of-season points for \d+|\d+ rest-of-season points for")


@pytest.fixture(autouse=True)
def _fixtures(monkeypatch):
    monkeypatch.setenv(M.FIXTURES_ENV, str(MFL_FX))
    monkeypatch.setenv(PI.CSV_ENV, str(IDS))
    monkeypatch.setenv(M.YEAR_ENV, "2026")
    monkeypatch.setenv(F.FIXTURES_ENV, str(ESPN))
    monkeypatch.delenv(AV.SWITCH_ENV, raising=False)
    PI.reset()
    F.reset()
    AV._snap = None
    AV._built = None
    AV.clear_context()
    A._default = None
    decisions.clear_memo()
    yield
    PI.reset()
    F.reset()
    AV._snap = None
    AV.clear_context()
    A._default = None
    decisions.clear_memo()


def _partners(client, team=8, window=None) -> dict:
    r = client.get(f"/api/trades/partners?league={KEY}&team={team}" + (f"&window={window}" if window else ""))
    assert r.status_code == 200, r.text[:400]
    return r.json()


def _eval(client, give, get, team=8, partner=12) -> dict:
    r = client.post("/api/trades/evaluate", json={"league": KEY, "team": team, "partner": partner, "give": give, "get": get})
    assert r.status_code == 200, r.text[:400]
    return r.json()


def _names(ps) -> list[str]:
    return [x["player_name"] for x in ps]


# ------------------------------------------------------------------ the finder (the review's acceptance)
@needs_db
def test_finder_ranks_trades_against_the_best_waiver_move(client):
    p = _partners(client)
    alt = p["best_alternative"]
    print("\nbest alternative:", alt["words"], alt["by_week"], alt["source"])
    for r in p["partners"][:5]:
        print(r["rank"], _names(r["give"]), "->", _names(r["get"]), r["you_gain_week"], r["you_gain_horizon"],
              "beyond", r["beyond_alternative"], "|", r["alternative_words"])
    # the ladder: standing pat (0) and the best legal waiver move over the same weeks
    assert alt["kind"] == "waiver" and alt["open_spot"] and alt["drop"] is None
    assert alt["player"]["player_name"] == "Atlanta Falcons" and alt["gain_window"] == pytest.approx(12.81, abs=0.005)
    assert alt["weeks"] == p["weeks"] == [4, 5, 6, 7] and sum(alt["by_week"]) == pytest.approx(alt["gain_window"], abs=0.02)
    assert [a["kind"] for a in p["alternatives"]] == ["stand_pat", "waiver"] and p["alternatives"][0]["gain_window"] == 0
    # the Waivers screen's top claim is the same move and the same number (one decision result across the screens)
    w = client.get(f"/api/waivers?league={KEY}&team=8").json()
    top = next(c for c in w["cards"] if c["title"] == "Top claim")
    assert top["add_sleeper_id"] == alt["player"]["sleeper_id"]
    assert top["move"]["horizon_gain"] == pytest.approx(alt["gain_window"], abs=0.01)
    rows = p["partners"]
    # each trade's gain beyond it; the trades that beat it first, then by that gain; rank 1 is the headline
    for r in rows:
        assert r["beyond_alternative"] == pytest.approx(r["you_gain_horizon"] - alt["gain_window"], abs=0.011)
        assert r["beats_alternative"] == (r["beyond_alternative"] >= 0.05) and r["demoted"] == (not r["beats_alternative"])
    assert [r["rank"] for r in rows] == list(range(1, len(rows) + 1))
    key = [(not r["beats_alternative"], -r["beyond_alternative"]) for r in rows]
    assert key == sorted(key)
    head = p["words"]["headline"]
    first = rows[0]
    assert all(n in head for n in _names(first["give"]) + [re.sub(r"\[|\]\(.*?\)", "", x) for x in _names(first["get"])])
    assert f"**{first['you_gain_horizon']:+.1f}** over weeks 4–7" in head
    assert p["ordering"]["words"].startswith("Ranked by gain beyond your best waiver move over weeks 4–7 (Atlanta Falcons defense, +12.8)")
    assert p["words"]["alternative"] == first["alternative_words"]


@needs_db
def test_finder_top_three_before_and_after(client):
    """Before IF-2 the first card (Houston Texans QB for Kansas City Chiefs QB, +5.5) was not the headline (Chicago Bears
    QB for Kansas City Chiefs QB and Rice, +14.6). After: the headline is the first card and the only trade that beats
    the claim (+1.8 beyond it); the next two are marked below it."""
    rows = _partners(client)["partners"]
    top3 = [(_names(r["give"]), _names(r["get"]), r["you_gain_horizon"], r["beyond_alternative"]) for r in rows[:3]]
    print("\ntop three:", top3)
    assert top3[0][:2] == (["Chicago Bears QB"], ["Kansas City Chiefs QB", "Rashee Rice"])
    assert top3[0][2] == pytest.approx(14.59, abs=0.01) and top3[0][3] == pytest.approx(1.78, abs=0.01)
    assert rows[0]["beats_alternative"] and not rows[1]["beats_alternative"] and not rows[2]["beats_alternative"]
    # numbers of the trades unchanged: the old first card is still found, with its own gains
    old = next(r for r in rows if _names(r["give"]) == ["Houston Texans QB"] and _names(r["get"]) == ["Kansas City Chiefs QB"])
    assert (old["you_gain_week"], old["you_gain_horizon"], old["they_gain_horizon"]) == (1.76, 5.53, 16.66)


@needs_db
def test_a_trade_below_the_waiver_move_is_marked_and_worded(client):
    rows = _partners(client)["partners"]
    below = [r for r in rows if r["demoted"]]
    assert below
    for r in below:
        assert "the Atlanta Falcons defense claim gives +12.8 over weeks 4–7 for an open spot" in r["alternative_words"]
        assert "the trade does not beat it on starter points" in r["alternative_words"]
        o = r["other_objective"]
        if o is not None:                     # a reason only from the numbers: this week, or season value coming in
            assert o["kind"] in ("this_week", "season_value") and o["words"] in r["alternative_words"]
            if o["kind"] == "this_week":
                assert r["you_gain_week"] - 1.2 >= 0.5
            else:
                assert r["price_in"] > r["price_out"]
    beat = rows[0]
    assert beat["alternative_words"] == ("+14.6 over weeks 4–7: 1.8 more than your best waiver move (the Atlanta Falcons "
                                         "defense claim gives +12.8 over weeks 4–7 for an open spot). The trade also takes "
                                         "the open roster spot the claim would use.")


@needs_db
def test_the_week_strip_adds_up_to_both_sides_gains(client):
    rows = _partners(client)["partners"]
    for r in rows:
        s = r["strip"]
        assert s["weeks"] == [4, 5, 6, 7] and len(s["mine"]) == len(s["theirs"]) == 4
        assert sum(s["mine"]) == pytest.approx(r["you_gain_horizon"], abs=0.03)
        assert sum(s["theirs"]) == pytest.approx(r["they_gain_horizon"], abs=0.03)
        assert s["mine"][0] == pytest.approx(r["you_gain_week"], abs=0.011)


@needs_db
def test_the_one_week_window_compares_this_week(client):
    p = _partners(client, window="week")
    alt = p["best_alternative"]
    print("\nweek:", alt["words"], [(r["you_gain_horizon"], r["beyond_alternative"]) for r in p["partners"][:3]])
    assert alt["weeks"] == [4] and alt["gain_window"] == alt["gain_week"]
    for r in p["partners"]:
        assert r["beyond_alternative"] == pytest.approx(r["you_gain_horizon"] - alt["gain_week"], abs=0.011)
    if p["partners"]:
        assert p["partners"][0]["rank"] == 1 and "this week" in p["ordering"]["words"]


# ------------------------------------------------------------------ the calculator
@needs_db
def test_the_reviews_headline_trade_against_the_claim(client):
    """The review's headline: Houston Texans QB for Rice + Carolina team QB. On the fixture +1.7 this week, +7.86 over
    weeks 4–7 (the live review: +1.0 / +9.8): the claim's +12.81 beats it on starter points; the answer says so."""
    e = _eval(client, [HOUSTON_QB], [RICE, CAROLINA_QB])
    print("\ncalc:", e["alternative_words"], "| strip", e["strip"])
    assert e["fit"]["this_week"]["mine"] == 1.7 and e["fit"]["window"]["mine"] == 7.86          # unchanged
    assert e["alternative"]["player"]["player_name"] == "Atlanta Falcons"
    assert e["beyond_alternative"] == pytest.approx(7.86 - 12.81, abs=0.011) and not e["beats_alternative"]
    assert "the trade does not beat it on starter points" in e["alternative_words"]
    assert "takes the open roster spot the claim would use" in e["alternative_words"]       # 2 for 1: it uses the spot
    s = e["strip"]
    assert s["weeks"] == [4, 5, 6, 7]
    assert sum(s["mine"]) == pytest.approx(e["fit"]["window"]["mine"], abs=0.03)
    assert sum(s["theirs"]) == pytest.approx(e["fit"]["window"]["theirs"], abs=0.03)


@needs_db
def test_the_calculator_names_its_value_concepts_and_drops_the_raw_fairness_line(client):
    """The review: "you get more season value" and then "492 rest-of-season points for 164" — two concepts, unnamed.
    On the fixture the package Houston Texans QB + Tuten for Rice reads 493 for 134 rest-of-season points: the raw line is
    labelled "not a fairness test"; the warning (if any) is on season value above replacement."""
    e = _eval(client, [HOUSTON_QB, TUTEN], [RICE])
    before = T.sanity([HOUSTON_QB, TUTEN], [RICE], ros={HOUSTON_QB: 355.0, TUTEN: 138.0, RICE: 134.0}, ours={}, market={})
    print("\nbefore:", before, "| after:", e["sanity"], "|", e["values"]["season_value"]["words"], "|", e["how"]["ros"])
    v = e["values"]
    assert [v[k]["label"] for k in ("projected_points", "starter_points", "depth", "season_value", "ros_points")] == [
        "Projected points", "Starter points", "Backup coverage", "Season value above replacement", "Rest-of-season projected points"]
    assert v["season_value"]["fairness"] is True and v["ros_points"]["fairness"] is False
    assert v["season_value"]["words"].startswith("Season value above replacement: you give 14, you get 7")
    assert "You give 2 players for 1: 1 roster spot freed." in v["season_value"]["words"]
    assert "Not counted (no season projection): Houston Texans QB." in v["season_value"]["words"]
    assert e["ros"]["words"] == ("Rest-of-season projected points (weeks 4–18), all positions added up — not a fairness test: "
                                 "you give 493, you get 134.")
    assert e["how"]["ros"] == e["ros"]["words"]
    # no raw-total fairness sentence anywhere in the answer's words
    texts = [e.get("verdict"), e.get("headline"), e.get("sanity"), e.get("hold_words"), e.get("alternative_words"),
             *(x for x in e["how"].values() if isinstance(x, str)), *(x["words"] or "" for x in v.values())]
    assert not any(RAW_FAIRNESS.search(t or "") for t in texts)
    assert e["sanity"] is None                                   # Houston Texans QB has no season value: not judged
    assert v["depth"]["mine"] == {"before": 43.91, "after": 22.61}
    assert v["starter_points"]["mine"] == e["fit"]["window"]["mine"]


# ------------------------------------------------------------------ the pieces (no database)
ALT = {"kind": "waiver", "player": {"player_name": "Arizona Cardinals QB", "position": "TMQB"}, "drop": None,
       "open_spot": True, "gain_week": 1.4, "gain_window": 11.4, "by_week": [1.4, 3.0, 3.0, 4.0], "weeks": [4, 5, 6, 7]}


def _alt(**kw) -> dict:
    a = {**ALT, **kw}
    return {**a, "words": decisions.alternative_words(a, "weeks 4–7", "next4")}


def test_the_reviews_sentence():
    """"+9.8 over weeks 4–7; the Arizona team QB claim gives +11.4 for an open spot: the trade does not beat it"."""
    d = decisions.trade_vs_alternative(1.0, 9.8, _alt(), "weeks 4–7", "next4")
    assert d["beyond_alternative"] == pytest.approx(-1.6) and not d["beats_alternative"]
    assert d["alternative_words"] == ("+9.8 over weeks 4–7; the Arizona Cardinals QB claim gives +11.4 over weeks 4–7 for an "
                                      "open spot: the trade does not beat it on starter points.")
    assert d["other_objective"] is None
    d = decisions.trade_vs_alternative(1.0, 14.0, _alt(), "weeks 4–7", "next4")
    assert d["beats_alternative"] and d["alternative_words"].startswith("+14.0 over weeks 4–7: 2.6 more than your best waiver move")


def test_another_objective_only_from_the_numbers():
    d = decisions.trade_vs_alternative(3.4, 9.8, _alt(), "weeks 4–7", "next4")
    assert d["other_objective"] == {"kind": "this_week", "words": "It gives more this week: +3.4 against the claim's +1.4."}
    d = decisions.trade_vs_alternative(1.0, 9.8, _alt(), "weeks 4–7", "next4", price_out=10, price_in=60)
    assert d["other_objective"]["kind"] == "season_value" and "60 for 10" in d["other_objective"]["words"]
    d = decisions.trade_vs_alternative(1.0, 9.8, _alt(), "weeks 4–7", "next4", price_out=50, price_in=55)
    assert d["other_objective"] is None                         # about even by season value: no reason invented
    d = decisions.trade_vs_alternative(1.0, 9.8, _alt(), "weeks 4–7", "next4", bench=(20.0, 26.5))
    assert d["other_objective"]["kind"] == "depth"


def test_a_claim_with_a_drop_and_standing_pat_in_words():
    a = _alt(open_spot=False, drop={"player_name": "Bhayshul Tuten"})
    assert a["words"] == "the Arizona Cardinals QB claim gives +11.4 over weeks 4–7 (drop Bhayshul Tuten)"
    sp = decisions._stand_pat([4, 5, 6, 7], "weeks 4–7", "test")
    sp["words"] = decisions.alternative_words(sp, "weeks 4–7", "next4")
    d = decisions.trade_vs_alternative(0.5, 2.0, sp, "weeks 4–7", "next4")
    assert d["beats_alternative"] and d["alternative_words"] == ("+2.0 over weeks 4–7; no waiver claim improves your starting "
                                                                "lineup over weeks 4–7: the trade beats standing pat.")
    assert decisions.ordering_words(sp, "weeks 4–7", "next4").startswith("Ranked by what each trade adds")
    d = decisions.trade_vs_alternative(-8.6, -2.4, sp, "weeks 4–7", "next4")
    assert not d["beats_alternative"] and d["alternative_words"].endswith("the trade does not beat standing pat.")


def test_season_value_line_names_package_size_and_unknowns():
    assert T.season_value_line(14, 7, 2, 1, ["mfl:0682"], {"mfl:0682": "Houston Texans QB"}.get) == (
        "Season value above replacement: you give 14, you get 7 (about even). You give 2 players for 1: 1 roster spot freed. "
        "Not counted (no season projection): Houston Texans QB.")
    assert T.season_value_line(10, 61, 1, 2) == ("Season value above replacement: you give 10, you get 61 (you get 51 more). "
                                                 "You get 2 players for 1: 1 more roster spot used.")


def test_the_calculator_warning_is_on_season_value_not_raw_totals():
    prices = {"a": 40.0, "b": 2.0, "c": 10.0}
    assert decisions.calc_sanity(["a", "b"], ["c"], prices, {}, {}, str) == (
        "you give 42 season value above replacement for 10: 32 more, over 25% of what you give")
    assert decisions.calc_sanity(["a"], ["c", "x"], prices, {}, {}, str) is None              # x unknown: not judged
    assert decisions.calc_sanity(["c"], ["a"], prices, {}, {}, str) is None                   # you get the value


def _board() -> RosterBoard:
    me = [("q1", "QB", 20.0), ("w1", "WR", 10.0), ("w2", "WR", 14.0), ("r1", "RB", 8.0)]
    them = [("q2", "QB", 18.0), ("r2", "RB", 15.0), ("r3", "RB", 13.0), ("w4", "WR", 3.0), ("r4", "RB", 12.0)]
    rows = []
    for roster, players in ((1, me), (2, them)):
        for sid, pos, v in players:
            for w in (4, 5):
                rows.append({"roster_id": roster, "week": w, "sleeper_player_id": sid, "position": pos,
                             "player_value": v + (2.0 if (sid == "r2" and w == 5) else 0.0), "value_source": "proj_points",
                             "role": "bench", "is_locked": False, "reason": None, "slot_type": None, "fantasy_positions": [pos]})
    return RosterBoard(rows, ("QB", "RB", "WR", "FLEX", "BN"))


def test_package_weeks_add_up_to_the_package_gains():
    b = _board()
    pk = T.package_gains(b, ["w1"], ["r2"], b.weeks)
    mine, theirs = T.package_weeks(b, ["w1"], ["r2"], b.weeks)
    assert mine == (5.0, 7.0) and sum(mine) == pytest.approx(pk.my_horizon) and mine[0] == pytest.approx(pk.my_week)
    assert sum(theirs) == pytest.approx(pk.their_horizon) and theirs[0] == pytest.approx(pk.their_week)
