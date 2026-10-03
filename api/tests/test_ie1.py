"""Wave I-E, IE-1 — the casual-user review (docs/reviews/2026-10-03-mfl-70587-usability-review.md) § "make the default
experience a weekly action list", § "make waiver horizons visually unambiguous", § "replace the interest dial's implied
acceptance prediction", § "avoid unnecessary extra assets".

The review's roster is MFL 70587 team 8 "Big Mac Attack" (the ESPN fixture overlay on: McConkey Questionable in the
MFL fixture's week 4); the Sleeper case is League of Scrubs roster 2 (overlay on: Justin Jefferson Out). Numbers do not
move: the cards, the lineup and the gains are pinned below at the values they had before this wave.
"""

from __future__ import annotations

import pandas as pd
import pytest
from league_lab import anyleague as A
from league_lab import injury_feed as F
from league_lab import mfl_client as M
from league_lab import player_ids as PI

from league_lab_api import availability as AV
from league_lab_api import decisions, myweek

from .conftest import SCRUBS, needs_db
from .test_i0b import IDS, MFL_FX
from .test_ic4 import ESPN

KEY = "mfl:70587"
EFFECT = ("Makes their lineup weaker", "About even", "Improves their lineup", "Improves it a lot")


@pytest.fixture(autouse=True)
def _fixtures(monkeypatch):
    """MFL 70587 from the fixtures, and the availability overlay on (the ESPN fixture feed)."""
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


def _week(client, league, team) -> dict:
    r = client.get(f"/api/my-week?league={league}&team={team}")
    assert r.status_code == 200, r.text
    return r.json()


def _ordered(acts: list[dict]) -> bool:
    return [a["urgency"] for a in acts] == sorted(a["urgency"] for a in acts)


# ------------------------------------------------------------------ My Week: the review's roster
@needs_db
def test_team8_one_receiver_decision_already_submitted(client):
    d = _week(client, KEY, 8)
    acts = d["actions"]
    assert 1 <= len(acts) <= 3 and _ordered(acts)
    rec = [a for a in acts if "McConkey" in a["action"]]
    assert len(rec) == 1, [a["action"] for a in acts]            # Addison vs McConkey + Nabers vs Addison: ONE decision
    a = rec[0]
    print("team 8 action:", a["action"], "|", a["reason"], "|", a["submitted_words"], "|", a["lock"])
    assert a["kind"] == "close" and a["slot_label"] == "WR/TE 2 · WR/TE 3"
    for who in ("Addison", "Nabers", "McConkey"):
        assert who in a["action"]
    assert a["action"].startswith("Keep ") and "ahead of" in a["action"] and a["action"].endswith("for now.")
    assert [p["name"] for p in a["sit"]] == ["McConkey"] and {p["name"] for p in a["start"]} == {"Addison", "Nabers"}
    assert "questionable status breaks the tie" in a["reason"] and "again before kickoff" in a["reason"]
    assert a["submitted"] is True and a["submitted_words"] == "Already in your MFL lineup — nothing to change."
    assert a["lock"]["words"] == "before Sun 4:05 PM ET"                    # Addison's kickoff: the swap locks then
    # the two cards behind it (the analysis, layer 3), both pointing at it; the clear McCaffrey call is not an action
    idx = acts.index(a)
    both = [c for c in d["cards"] if c["action"] == idx]
    assert {(c["player_name"], c["alt_name"]) for c in both} == {("Ladd McConkey", "Jordan Addison"), ("Malik Nabers", "Jordan Addison")}
    assert sorted(a["cards"]) == sorted(d["cards"].index(c) for c in both)
    assert d["set_line"] == "The rest of your lineup is set — nothing to change."
    assert d["edit_link"]["label"] == "Open MFL to edit your lineup"
    assert d["edit_link"]["url"] == "https://www44.myfantasyleague.com/2026/options?L=70587&O=02"
    assert d["nothing_submitted"] == myweek.NOTHING_SUBMITTED and "never changes your lineup or claims" in d["nothing_submitted"]
    assert d["next_lock"]["words"] == "before Sun 4:05 PM ET"
    # numbers do not move (the cards as they were before Wave I-E)
    pinned = {"WR+TE3": (6.88, 6.6, 0.28), "WR+TE2": (7.11, 6.6, 0.51), "RB2": (15.45, 9.72, 5.73)}
    assert {c["slot"]: (c["value"], c["alt_value"], c["margin"]) for c in d["cards"]} == pinned
    assert [(r["slot"], r["value"]) for r in d["lineup"]] == [("team QB", 30.4), ("RB1", 19.17), ("RB2", 15.45),
                                                              ("WR/TE 1", 12.7), ("WR/TE 2", 7.11), ("WR/TE 3", 6.88),
                                                              ("team K", 12.89), ("DEF", 10.81)]


# ------------------------------------------------------------------ My Week: the Sleeper case
@needs_db
def test_scrubs_roster2_a_change_before_the_first_lock(client):
    d = _week(client, SCRUBS, 2)
    acts = d["actions"]
    assert 1 <= len(acts) <= 3 and _ordered(acts)
    a = acts[0]
    print("scrubs action:", a["action"], "|", a["reason"], "|", a["submitted_words"], "|", a["lock"])
    assert a["kind"] == "change" and a["urgency"] == 1 and a["submitted"] is False
    assert "Wilson" in a["action"] and "Jefferson" in a["action"] and "in place of" in a["action"] and "at FLEX" in a["action"]
    assert "Croskey-Merritt" in a["action"] and "coin flip" in a["action"]       # Wilson vs Croskey-Merritt: either
    assert a["reason"].startswith("Jefferson is out") and "about 9 more projected points" in a["reason"]
    assert a["gain"] == pytest.approx(9.2, abs=0.01)                              # Wilson 9.20 for Jefferson (Out: 0)
    assert a["submitted_words"] == "Not in your Sleeper lineup yet: make the change in Sleeper."
    assert a["lock"]["words"] == "before Sun 9:30 AM ET"                          # Croskey-Merritt's London kickoff
    # the three cards that share Croskey-Merritt are one decision (no reassurance cards for Hampton and Tuten)
    assert len(acts) == 1 and sorted(a["cards"]) == [0, 1, 2] and all(c["action"] == 0 for c in d["cards"])
    assert d["set_line"] == "The rest of your lineup is set — nothing to change."
    assert d["edit_link"] == {"label": "Open Sleeper to edit your lineup", "url": f"https://sleeper.com/leagues/{SCRUBS}",
                              "platform": "Sleeper"}
    assert d["next_lock"]["words"] == "before Sun 9:30 AM ET" and set(d["next_lock"]["players"]) == {"Jefferson", "Wilson", "Croskey-Merritt"}
    pinned = {"FLEX2": (9.2, 9.19, 0.01), "FLEX1": (9.72, 9.19, 0.53), "RB2": (11.28, 9.19, 2.09)}
    assert {c["slot"]: (c["value"], c["alt_value"], c["margin"]) for c in d["cards"]} == pinned


# ------------------------------------------------------------------ the rules, on a frame built by hand
def _rows(starters, bench, unplayable=()):
    out = []
    for i, (k, slot, pos, v, *rest) in enumerate(starters):
        out.append({"role": "starter", "slot": slot, "slot_type": slot.rstrip("0123456789"), "sleeper_player_id": k,
                    "player_name": f"Player {k}", "position": pos, "value": v, "gsis_id": None, "is_empty_slot": False,
                    "locked_now": False, "report_status": rest[0] if rest else None, "chip": None, "reason": None,
                    "kickoff_at": pd.Timestamp("2026-10-04 17:00", tz="UTC") + pd.Timedelta(hours=i)})
    for k, pos, v in bench:
        out.append({"role": "bench", "slot": None, "slot_type": None, "sleeper_player_id": k, "player_name": f"Player {k}",
                    "position": pos, "value": v, "gsis_id": None, "is_empty_slot": False, "locked_now": False,
                    "report_status": None, "chip": None, "reason": None, "kickoff_at": pd.Timestamp("2026-10-04 20:25", tz="UTC")})
    for k, pos, v, chip in unplayable:
        out.append({"role": "unplayable", "slot": None, "slot_type": None, "sleeper_player_id": k, "player_name": f"Player {k}",
                    "position": pos, "value": v, "gsis_id": None, "is_empty_slot": False, "locked_now": False,
                    "report_status": "Out", "chip": chip, "reason": "Out", "kickoff_at": pd.Timestamp("2026-10-04 17:00", tz="UTC")})
    return pd.DataFrame(out)


def _card(k, alt, margin, status, strength="lean", tb=None):
    return {"key": k, "alt_key": alt, "margin": margin, "status": status, "strength": strength, "tiebreak": tb, "action": None}


def test_a_set_lineup_is_a_complete_answer():
    rows = _rows([("1", "RB1", "RB", 15.0), ("2", "WR1", "WR", 12.0)], [("3", "WR", 8.0)])
    cards = [_card("2", "3", 4.0, "set", "clear")]
    res = myweek.build_actions(rows, cards, {"1": "RB", "2": "WR"}, SCRUBS)
    assert res["actions"] == [] and res["set_line"] == myweek.SET_ALL and res["next_lock"] is None
    assert cards[0]["action"] is None


def test_a_tiny_difference_is_not_an_action():
    # the submitted lineup starts 3 (8.0) where the best lineup starts 2 (8.3): 0.3 points, nobody hurt
    rows = _rows([("1", "RB1", "RB", 15.0), ("2", "WR1", "WR", 8.3)], [("3", "WR", 8.0)])
    res = myweek.build_actions(rows, [_card("2", "3", 0.3, "close", "coin flip")], {"1": "RB", "3": "WR"}, SCRUBS)
    assert res["actions"] == [] and res["set_line"].startswith(myweek.SET_ALL) and "less than half a point" in res["set_line"]


def test_an_out_starter_comes_first_and_at_most_three():
    rows = _rows([("1", "QB", "QB", 20.0), ("2", "RB1", "RB", 12.0), ("3", "WR1", "WR", 11.0), ("4", "TE", "TE", 9.0),
                  ("5", "K", "K", 8.0)],
                 [("11", "RB", 6.0), ("13", "WR", 5.0), ("14", "TE", 4.0), ("15", "K", 3.0)],
                 [("21", "RB", 13.0, "OUT"), ("23", "WR", 12.0, "OUT"), ("24", "TE", 10.0, "OUT"), ("25", "K", 9.0, "OUT")])
    cur = {"1": "QB", "21": "RB", "23": "WR", "24": "TE", "25": "K"}       # four starters out in the submitted lineup
    res = myweek.build_actions(rows, [], cur, KEY)
    assert len(res["actions"]) == 3 and all(a["kind"] == "change" for a in res["actions"])
    assert res["set_line"] == "1 more change: the lineup below shows every slot."
    assert res["actions"][0]["lock"]["words"] == "before Sun 1:00 PM ET"    # a swap locks at the first of the two kickoffs
    assert all(a["submitted_words"] == "Not in your MFL lineup yet: make the change in MFL." for a in res["actions"])


def test_unknown_submitted_lineup_says_nothing_it_cannot_know():
    rows = _rows([("1", "RB1", "RB", 15.0), ("2", "WR1", "WR", 6.9, "Questionable")], [("3", "WR", 6.6)])
    cards = [_card("2", "3", 0.3, "close", "coin flip", {"kind": "injury", "pick": "3", "side": "alt"})]
    res = myweek.build_actions(rows, cards, None, SCRUBS)
    assert res["set_line"] is None and len(res["actions"]) == 1
    a = res["actions"][0]
    assert a["kind"] == "close" and a["submitted"] is None and a["submitted_words"] is None
    assert a["action"].startswith("Start ")                                 # not "Keep": we do not know what is submitted


# ------------------------------------------------------------------ Waivers: this week first, no triple copy
@needs_db
def test_waivers_lead_with_this_week_and_say_the_total_is_cumulative(client):
    w = client.get(f"/api/waivers?league={KEY}&team=8").json()
    top, help_ = w["top3"], w["views"]["help"]["moves"]
    assert top and help_
    for c in [*top, *help_]:
        print("card:", c["lead"], "|", c.get("total_words"), "| alt:", c.get("alternative_to"))
        if (c["this_week"] or 0) >= 0.05:
            assert c["lead"].endswith("this week") and ("more starter point" in c["lead"])
        assert c["total_words"] is None or (c["total_words"].endswith("over weeks 4–7 in total"))
    # the Falcons: about 1 more starter point this week first, the four-week +12.8 second and cumulative (unchanged gains)
    f = top[0]
    assert f["lead"] == "Falcons defense instead of Jaguars: about 1 more starter point this week"
    assert f["total_words"] == "+12.8 over weeks 4–7 in total" and f["gain"] == pytest.approx(12.81) and f["this_week"] == pytest.approx(1.2)
    # alternatives are labelled: Schultz takes the same WR/TE spot this week as Vele, above him
    assert top[2]["alternative_to"] == "Devaughn Vele" and top[1]["alternative_to"] is None
    # no triple copy: the answer is not a card's sentence, and Help now starts after the three
    assert w["answer"] == "The three strongest claims are below, each with what it adds this week."
    assert w["answer"] != help_[0]["lead"] and all(w["answer"] != c["lead"] for c in top)
    key = lambda c: (c["move"]["add"]["sleeper_id"], (c["move"].get("drop") or {}).get("sleeper_id"))  # noqa: E731
    assert not ({key(c) for c in top} & {key(c) for c in help_})
    assert "beyond the ones above" in w["views"]["help"]["line"]
    assert w["not_additive"].startswith("Each claim is weighed on its own") and "1 open roster spot" in w["not_additive"]
    # My Week's third action: the claim that raises this week's starters most (Schultz +3.0 this week)
    h = w["home_action"]
    assert h["kind"] == "move" and h["urgency"] == 3 and h["href"] == "/waivers"
    assert h["action"] == "Claim Dalton Schultz: about 3 more starter points this week." and h["gain"] == pytest.approx(3.0)
    assert "+8.1 over weeks 4–7 in total" in h["reason"] and h["submitted_words"].startswith("Nothing is claimed from here")


# ------------------------------------------------------------------ the dial: the effect on their starters
@needs_db
def test_the_dial_is_the_effect_on_their_starters(client):
    body = {"league": KEY, "team": 8, "partner": 12, "give": ["mfl:0671"], "get": ["mfl:0662", "10229"]}
    e = client.post("/api/trades/evaluate", json=body).json()
    i = e["interest"]
    print("dial:", i)
    assert i["title"] == "Effect on their starters" and i["label"] in EFFECT
    assert i["label"] == decisions.effect_label(e["fit"]["window"]["theirs"]) and i["their_gain"] == e["fit"]["window"]["theirs"]
    assert "interest" not in i["caption"] and "say no" not in i["label"].lower()
    assert i["need"] is None                 # the Bears QB does not start for them (the Panthers QB does): no need claimed
    # Madeyes Revenge's Rice to Knight Train for the Bengals QB (the Finder's lead for team 12): the need Rice fills there
    e = client.post("/api/trades/evaluate", json={"league": KEY, "team": 12, "partner": 1, "give": ["10229"],
                                                  "get": ["mfl:0656"]}).json()
    print("need:", e["interest"])
    assert e["interest"]["need"] and e["interest"]["need"].startswith(("starts at their WR/TE", "fills their", "takes over their"))
    assert "Rice" not in e["interest"]["need"]
    p = client.get(f"/api/trades/partners?league={KEY}&team=8").json()
    assert {r["interest"]["label"] for r in p["partners"]} <= set(EFFECT)


# ------------------------------------------------------------------ the Finder: the least costly package first
@needs_db
def test_the_cheaper_package_leads_and_the_extra_asset_is_optional(client):
    p = client.get(f"/api/trades/partners?league={KEY}&team=12").json()
    rows = [r for r in p["partners"] if r["partner"] == 1]
    lead, two = rows[0], next(r for r in rows if r.get("optional"))
    print("finder:", [x["player_name"] for x in lead["give"]], lead["you_gain_horizon"], "|", two["optional"]["words"])
    assert lead["is_best"] and not two["is_best"] and len(lead["give"]) == 1 and len(two["give"]) == 2
    assert rows.index(lead) < rows.index(two)
    assert abs(lead["you_gain_horizon"] - two["you_gain_horizon"]) < decisions.SAME_GAIN
    assert two["you_gain_horizon"] == pytest.approx(19.8, abs=0.05)              # the two-for-one's own gain, unchanged
    assert two["optional"]["player_name"] == "RJ Harvey" and two["optional"]["season_points"] > 0
    assert two["optional"]["words"].startswith("Adding RJ Harvey does not change your gain; it costs you RB depth")
    assert lead["cheaper_than"]["words"] == "Same gain for you without RJ Harvey."


@needs_db
def test_the_reviews_own_package_gives_the_same_gain_without_tuten(client):
    """The review: "Houston QB for Rice and Houston QB plus Tuten for Rice with the same +9.5". On the fixture both are
    −2.42 for Big Mac Attack over weeks 4–7: Tuten adds nothing to your side of it (he is the optional asset)."""
    ev = {}
    for give in (["mfl:0682", "12490"], ["mfl:0682"]):
        e = client.post("/api/trades/evaluate", json={"league": KEY, "team": 8, "partner": 12, "give": give, "get": ["10229"]}).json()
        ev[len(give)] = e
        print(give, "you", e["fit"]["this_week"]["mine"], e["fit"]["window"]["mine"], "them", e["fit"]["window"]["theirs"])
    assert ev[2]["fit"]["window"]["mine"] == pytest.approx(ev[1]["fit"]["window"]["mine"], abs=0.01)
    assert ev[2]["fit"]["this_week"]["mine"] == pytest.approx(ev[1]["fit"]["this_week"]["mine"], abs=0.01)
