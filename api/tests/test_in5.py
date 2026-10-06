"""Wave I-N, IN-5 — My Week says what it means, and no screen can go blank.

Andrew's morning (2026-10-06, League of Scrubs roster 2, week 5): two open starting spots (QB and TE: Mahomes, Young
and Kelce on a bye, Ferguson out), six players who cannot play, one FLEX coin flip (Washington or Croskey-Merritt).
My Week said "Make 2 changes: Washington at FLEX (or Croskey-Merritt: a coin flip) in place of Mahomes; Croskey-Merritt
out of your lineup." and "Start Kelce out of your lineup." — a receiver "in place of" a quarterback, and a "Start"
that starts nobody. The frame below rebuilds that morning by hand (the sandbox holds 2026 through week 4 only) in
`cards.lineup_rows`' shape after the availability overlay's re-solve (`availability._resolve`: an open slot is a
starter row with `is_empty_slot` and no player); the submitted lineup is Sleeper's.

Also: the words Andrew asked for (Roster alert, News feed) on the API side, and no "nan" / "None" text as an id on the
Team, My Week, League and Waivers answers of the two house leagues.
"""

from __future__ import annotations

import math
from pathlib import Path

import pandas as pd
import pytest

from league_lab_api import decisions as D
from league_lab_api import myweek as M
from league_lab_api.ids import text_id

from .conftest import ANDREW, DYNASTY, SCRUBS, needs_db

SUN_1PM = pd.Timestamp("2026-10-11 17:00", tz="UTC")       # Sunday of week 5, 1:00 PM ET
SUN_425 = pd.Timestamp("2026-10-11 20:25", tz="UTC")
THU = pd.Timestamp("2026-10-09 00:15", tz="UTC")             # Thursday 8:15 PM ET


def _row(role, slot, key, name, pos, value, *, kick=SUN_1PM, chip=None, reason=None, report=None, empty=False):
    return {"role": role, "slot": slot, "slot_type": None if slot is None else slot.rstrip("0123456789"),
            "sleeper_player_id": key, "player_name": name, "position": pos, "value": value, "gsis_id": None,
            "is_empty_slot": empty, "locked_now": False, "kicked_off": False, "report_status": report, "chip": chip,
            "reason": reason, "kickoff_at": kick}


def _empty(slot):
    return _row("starter", slot, None, None, None, None, kick=None, empty=True)


def morning(qb: dict | None = None) -> pd.DataFrame:
    """Scrubs roster 2, week 5, as the overlay re-solved it on 2026-10-06 (values: week 5 projections, half PPR).
    ``qb``: a quarterback the bench could start (the open QB spot filled)."""
    return pd.DataFrame([
        qb or _empty("QB"),
        _row("starter", "RB1", "8150", "Kyren Williams", "RB", 13.1),
        _row("starter", "RB2", "12507", "Omarion Hampton", "RB", 11.3, kick=SUN_425),
        _row("starter", "WR1", "4983", "Justin Jefferson", "WR", 12.7),
        _row("starter", "WR2", "11635", "Michael Wilson", "WR", 9.4, kick=SUN_425),
        _empty("TE"),
        _row("starter", "FLEX1", "12514", "Bhayshul Tuten", "RB", 9.7, kick=THU),
        _row("starter", "FLEX2", "11624", "Parker Washington", "WR", 9.25, kick=THU),
        _row("starter", "K", "4227", "Chase McLaughlin", "K", 8.0),
        _row("starter", "DEF", "DEN", "Denver Broncos", "DEF", 7.0),
        _row("bench", None, "12489", "Jacory Croskey-Merritt", "RB", 9.19),
        _row("unplayable", None, "4046", "Patrick Mahomes", "QB", None, kick=None, reason="bye"),
        _row("unplayable", None, "9228", "Bryce Young", "QB", None, kick=None, reason="bye"),
        _row("unplayable", None, "1466", "Travis Kelce", "TE", None, kick=None, reason="bye"),
        _row("unplayable", None, "12520", "Terrance Ferguson", "TE", 5.8, chip="OUT", report="Out", reason="Out"),
        _row("unplayable", None, "12530", "Jonah Coleman", "RB", 7.1, chip="IR", report="IR", reason="IR slot"),
        _row("unplayable", None, "5872", "Zach Charbonnet", "RB", 6.0, chip="IR", report="IR", reason="IR slot"),
    ])


# Sleeper's lineup that morning: Mahomes at QB, Kelce at TE, Croskey-Merritt in the second FLEX, Washington on the bench
SUBMITTED = {"4046": "QB", "8150": "RB", "12507": "RB", "4983": "WR", "11635": "WR", "1466": "TE", "12514": "FLEX",
             "12489": "FLEX", "4227": "K", "DEN": "DEF"}
FLEX_FLIP = {"key": "11624", "alt_key": "12489", "margin": 0.06, "status": "close", "strength": "coin flip",
             "tiebreak": None, "action": None, "slot": "FLEX2"}

BEFORE = ("Make 2 changes: Washington at FLEX (or Croskey-Merritt: a coin flip) in place of Mahomes; Croskey-Merritt out "
          "of your lineup.", "Start Kelce out of your lineup.")
AFTER_QB = "Your quarterback spot is open: Mahomes and Young are on a bye. Add a quarterback before Sun 1:00 PM ET."
AFTER_TE = "Your tight end spot is open: Kelce is on a bye and Ferguson is out. Add a tight end before Sun 1:00 PM ET."


def _actions(rows=None, cards=None, current=SUBMITTED, league=SCRUBS) -> dict:
    return M.build_actions(morning() if rows is None else rows, [dict(FLEX_FLIP)] if cards is None else cards, current,
                           league)


# ------------------------------------------------------------------ 1. open spots are their own action
def test_andrews_morning_two_open_spots():
    res = _actions()
    acts = res["actions"]
    for a in acts:
        print("action:", a["action"], "|", a["reason"], "|", a["submitted_words"], "|", a["href"])
    for r in res["review"]:
        print("review:", r["words"])
    print("set line:", res["set_line"])
    assert [a["action"] for a in acts] == [AFTER_QB, AFTER_TE]
    qb, te = acts
    for a, pos, who in ((qb, "QB", ["4046"]), (te, "TE", ["1466"])):
        assert a["kind"] == "change" and a["urgency"] == 1               # counted with the roster alerts
        assert not a["action"].startswith("Start") and "in place of" not in a["action"]
        assert a["href"] == f"/waivers?position={pos}" and a["open_slot"]["position"] == pos
        assert a["open_slot"]["players"] == who and [p["key"] for p in a["sit"]] == who and a["start"] == []
        assert a["submitted"] is False and a["lock"]["words"] == "before Sun 1:00 PM ET"
        assert a["lock"]["kickoff"] == SUN_1PM.isoformat()
    assert qb["reason"] == ("Nobody else on your roster can play quarterback this week. Mahomes is still in your Sleeper "
                            "lineup: start the player you add in his place.")
    assert qb["href_label"] == "Find a quarterback on Waivers" and te["href_label"] == "Find a tight end on Waivers"
    assert qb["submitted_words"] == "Nothing is claimed from here: add a quarterback in Sleeper."
    assert qb["slot_label"] == "QB" and te["slot_label"] == "TE"
    # the FLEX choice is the coin flip it is (Washington for Croskey-Merritt: 0.06 apart), named once, not an action
    assert [r["words"] for r in res["review"]] == [
        "Washington or Croskey-Merritt at FLEX: a coin flip, 0.1 points apart; your lineup has Croskey-Merritt — no clear upgrade."]
    text = " ".join(a["action"] for a in acts) + " ".join(r["words"] for r in res["review"])
    assert text.count("Croskey-Merritt") == 2 and "out of your lineup" not in text
    assert res["set_line"].startswith(M.SET_ELSEWHERE) and res["next_lock"]["words"] == "before Sun 1:00 PM ET"


def test_a_receiver_never_replaces_a_quarterback():
    res = _actions()
    for a in res["actions"]:
        assert "Washington" not in a["action"] or "Mahomes" not in a["action"]
    # and with a bigger FLEX gain the swap is its own action, the right pair
    rows = morning()
    rows.loc[rows["sleeper_player_id"] == "11624", "value"] = 10.4
    acts = _actions(rows, [dict(FLEX_FLIP, margin=1.21, status="change", strength="lean")])["actions"]
    swap = [a for a in acts if "Washington" in a["action"]]
    assert len(swap) == 1 and swap[0]["action"] == "Start Washington at FLEX in place of Croskey-Merritt."
    assert swap[0]["gain"] == pytest.approx(1.21)
    assert [a["action"] for a in acts if a.get("open_slot")] == [AFTER_QB, AFTER_TE]


def test_a_spot_the_bench_can_fill_stays_a_swap():
    acts = _actions(morning(qb=_row("starter", "QB", "12497", "Tyler Shough", "QB", 16.2)))["actions"]
    assert [a["action"] for a in acts if not a.get("open_slot")] == ["Start Shough at QB in place of Mahomes."]
    assert [a["action"] for a in acts if a.get("open_slot")] == [AFTER_TE]


def test_the_slot_chain_pairs_a_receiver_with_a_running_back():
    # Williams (RB1) is out; the best lineup slides Tuten from FLEX to RB and starts Croskey-Merritt... no: a receiver,
    # Washington, takes the FLEX: Washington replaces Williams only through the chain (an RB slot does not take a WR)
    rows = pd.DataFrame([
        _row("starter", "RB1", "12514", "Bhayshul Tuten", "RB", 9.7),
        _row("starter", "WR1", "4983", "Justin Jefferson", "WR", 12.7),
        _row("starter", "FLEX", "11624", "Parker Washington", "WR", 9.25),
        _row("unplayable", None, "8150", "Kyren Williams", "RB", 13.1, chip="OUT", report="Out", reason="Out"),
    ])
    cur = {"8150": "RB", "4983": "WR", "12514": "FLEX"}
    acts = M.build_actions(rows, [], cur, SCRUBS)["actions"]
    assert [a["action"] for a in acts] == ["Start Washington at FLEX in place of Williams."]
    assert acts[0]["reason"].startswith("Williams is out")
    assert M.fits(["4983", "12514", "11624"], ["RB", "WR", "FLEX"], {"4983": "WR", "12514": "RB", "11624": "WR"}.get)
    assert not M.fits(["4983", "11624", "1"], ["QB", "WR", "FLEX"], {"4983": "WR", "11624": "WR", "1": "WR"}.get)
    assert M.fits(["a", "b"], ["", "QB"], {"a": "WR", "b": "QB"}.get)            # a code that says nothing takes anyone


def test_the_coin_flip_clause_once():
    # Jefferson (WR2) out; Wilson comes in at FLEX (the chain: Washington to WR2), level with Croskey-Merritt
    rows = pd.DataFrame([
        _row("starter", "WR1", "4983x", "Tetairoa McMillan", "WR", 12.7),
        _row("starter", "WR2", "11624", "Parker Washington", "WR", 12.1),
        _row("starter", "FLEX", "11635", "Michael Wilson", "WR", 9.2),
        _row("bench", None, "12489", "Jacory Croskey-Merritt", "RB", 9.19),
        _row("unplayable", None, "4983", "Justin Jefferson", "WR", 12.6, chip="OUT", report="Out", reason="Out"),
    ])
    cur = {"4983x": "WR", "4983": "WR", "11624": "FLEX"}
    card = {"key": "11635", "alt_key": "12489", "margin": 0.01, "status": "close", "strength": "coin flip",
            "tiebreak": None, "action": None}
    acts = M.build_actions(rows, [card], cur, SCRUBS)["actions"]
    assert [a["action"] for a in acts] == ["Start Wilson at FLEX (or Croskey-Merritt: a coin flip) in place of Jefferson."]
    assert acts[0]["action"].count("coin flip") == 1


def test_nothing_on_the_roster_plays_the_position():
    rows = pd.DataFrame([_row("starter", "RB1", "8150", "Kyren Williams", "RB", 13.1), _empty("K")])
    acts = M.build_actions(rows, [], {"8150": "RB"}, "mfl:70587")["actions"]
    assert [a["action"] for a in acts] == [
        "Your kicker spot is open: nobody on your roster can play there this week. Add a kicker before Sun 1:00 PM ET."]
    assert acts[0]["reason"] == "" and acts[0]["submitted_words"] == "Nothing is claimed from here: add a kicker in MFL."
    assert acts[0]["href"] == "/waivers?position=K"


def test_an_unknown_lineup_still_says_the_spot_is_open():
    res = _actions(current=None)
    opens = [a for a in res["actions"] if a.get("open_slot")]
    # no lineup to read: the players in order of their projection (Ferguson has one, Kelce's bye has none)
    assert [a["action"] for a in opens] == [AFTER_QB, AFTER_TE.replace("Kelce is on a bye and Ferguson is out",
                                                                       "Ferguson is out and Kelce is on a bye")]
    assert all(a["submitted"] is None and a["sit"] == [] for a in opens)
    assert opens[0]["reason"] == "Nobody else on your roster can play quarterback this week."


def test_a_flex_spot_and_the_deadline():
    rows = pd.DataFrame([_row("starter", "RB1", "8150", "Kyren Williams", "RB", 13.1, kick=THU), _empty("FLEX"),
                         _row("unplayable", None, "12514", "Bhayshul Tuten", "RB", 9.7, kick=None, reason="bye")])
    acts = M.build_actions(rows, [], {"8150": "RB", "12514": "FLEX"}, SCRUBS)["actions"]
    assert acts[0]["action"] == ("Your FLEX spot is open: Tuten is on a bye. Add a running back, wide receiver or tight end "
                                 "before Thu 8:15 PM ET.")
    assert acts[0]["href"] == "/waivers" and acts[0]["open_slot"]["players"] == ["12514"]
    # the main slate: the kickoff most of the roster's games share; the earliest on a tie; nothing left -> None
    assert M.open_deadline(morning()) == SUN_1PM
    tie = pd.DataFrame([_row("bench", None, "1", "A B", "WR", 1.0, kick=SUN_425), _row("bench", None, "2", "C D", "WR", 1.0)])
    assert M.open_deadline(tie) == SUN_1PM
    assert M.open_deadline(tie.assign(locked_now=True)) is None


def test_the_hotfix_words_stay():
    a = M._action("change", [], ["1466"], False, 0.0, ["1466"], [], [], [(None, "1466")], set(), "Sleeper",
                  name=lambda k: "Kelce", plain=lambda k: "Kelce", status=lambda k: None,
                  cant_words=lambda k: "is on a bye", val=lambda k: None, slot_of=lambda k: None)
    assert a["action"] == "Take Kelce out of your lineup."


def test_more_actions_than_three_count_as_roster_alerts():
    assert M.more_words([{"kind": "change"}]) == "1 more roster alert: the lineup below shows every slot."
    assert M.more_words([{"kind": "change"}, {"kind": "change"}, {"kind": "close"}]) == (
        "2 more roster alerts and 1 close call: the lineup below shows every slot.")
    assert M.more_words([{"kind": "close"}]) == "1 more close call: the lineup below shows every slot."


# ------------------------------------------------------------------ 3(d). no "nan" / "None" as text on the way out
BAD = {"nan", "NaN", "None", "null", "undefined"}


def _walk(x, path="$"):
    if isinstance(x, dict):
        for k, v in x.items():
            yield from _walk(v, f"{path}.{k}")
    elif isinstance(x, list):
        for i, v in enumerate(x):
            yield from _walk(v, f"{path}[{i}]")
    else:
        yield path, x


def bad_values(answer) -> list[str]:
    """Every string value that is a missing value spelled out ("nan", "None"), and every float NaN, with its path."""
    out = []
    for p, v in _walk(answer):
        if (isinstance(v, str) and v.strip() in BAD) or (isinstance(v, float) and math.isnan(v)):
            out.append(f"{p} = {v!r}")
    return out


def test_ids_helpers_never_spell_a_missing_value():
    for nothing in (None, float("nan"), "nan", "NaN", "None", "", " ", pd.NaT):
        assert text_id(nothing) is None
    for nothing in (None, float("nan"), "nan", "NaN", ""):
        assert D._sid(nothing) is None                           # the PO's hotfix helper (one place) agrees
    assert text_id(4046) == "4046" and text_id("4046") == "4046" and text_id(8150.0) == "8150" and text_id("DEN") == "DEN"
    assert bad_values({"a": [{"b": "nan"}, {"c": None}], "d": float("nan"), "e": "Nancy"}) == ["$.a[0].b = 'nan'", "$.d = nan"]


@needs_db
@pytest.mark.parametrize("league", [SCRUBS, DYNASTY])
def test_no_nan_text_on_the_house_answers(client, league):
    team = ANDREW[league]
    found = {}
    for path in (f"/api/team?league={league}&team={team}", f"/api/my-week?league={league}&team={team}",
                 f"/api/league?league={league}&team={team}", f"/api/waivers?league={league}&team={team}"):
        r = client.get(path)
        assert r.status_code == 200, (path, r.text[:300])
        found[path] = bad_values(r.json())
    print({k: len(v) for k, v in found.items()})
    assert {k: v[:5] for k, v in found.items() if v} == {}


# ------------------------------------------------------------------ 3(a). the recording for the e2e (web/fixtures/in5/)
# The database holds the nightly's week-5 lineups: League of Scrubs roster 2 has its QB and TE slots empty (Mahomes, Young
# and Kelce on a bye) — Andrew's morning itself. The clock is pinned to his report (Tuesday 09:20 ET); the Sleeper lineup
# is reconstructed (the sandbox's Sleeper fixture is an older roster): Mahomes at QB and Kelce at TE still in it,
# Croskey-Merritt in the second FLEX where the best lineup starts Jefferson (level with Boston: a coin flip).
IN5_FIXTURES = Path(__file__).resolve().parents[2] / "web" / "fixtures" / "in5"
ANDREWS_MORNING = "2026-10-06T13:20:00Z"
LINEUP_0920 = {"4046": "QB", "8150": "RB", "12507": "RB", "9493": "WR", "10232": "WR", "1466": "TE", "9487": "FLEX",
               "12533": "FLEX", "650": "K", "BUF": "DEF"}


def _morning_answers(client, monkeypatch) -> tuple[dict, dict]:
    from league_lab import clock

    from league_lab_api import availability as AV
    monkeypatch.setattr(M, "current_starters", lambda league_id, roster_id, house: (
        dict(LINEUP_0920) if str(league_id) == SCRUBS and int(roster_id) == 2 else None))
    AV.clear_context()
    D.clear_memo()
    with clock.pinned(ANDREWS_MORNING):
        d = client.get(f"/api/my-week?league={SCRUBS}&team=2").json()
        t = client.get(f"/api/team?league={SCRUBS}&team=2").json()
    return d, t


@needs_db
def test_record_andrews_morning(client, monkeypatch):
    """My Week and Team on the morning's own rows, through the real routes: the open spots are the actions, the swap
    names the coin flip once, the open rows have no id, nothing spells a missing value. IN5_RECORD=1 writes the e2e's
    answers (web/fixtures/in5/)."""
    import json
    import os
    d, t = _morning_answers(client, monkeypatch)
    for a in d["actions"]:
        print("action:", a["action"], "|", a["reason"])
    assert d["week"] == 5 and t["week"] == 5
    acts = [a["action"] for a in d["actions"]]
    assert acts[0] == ("Your quarterback spot is open: [Mahomes](/player/00-0033873) and [Young](/player/00-0039150) are on a "
                       "bye. Add a quarterback before Sun 1:00 PM ET.")
    assert acts[1] == "Your tight end spot is open: [Kelce](/player/00-0030506) is on a bye. Add a tight end before Sun 1:00 PM ET."
    assert acts[2] == ("Start [Jefferson](/player/00-0036322) at FLEX (or [Boston](/player/00-0041037): a coin flip) in place of "
                       "[Croskey-Merritt](/player/00-0040242).")
    assert all(a["kind"] == "change" for a in d["actions"]) and d["actions"][0]["href"] == "/waivers?position=QB"
    empty = [x for x in t["roster"] if x["role"] == "empty"]
    assert [x["slot"] for x in empty] == ["QB", "TE"] and all(x["sleeper_id"] is None for x in empty)
    assert bad_values(d) == [] and bad_values(t) == []
    if os.environ.get("IN5_RECORD"):
        IN5_FIXTURES.mkdir(parents=True, exist_ok=True)
        (IN5_FIXTURES / "my-week_open.json").write_text(json.dumps(d))
        (IN5_FIXTURES / "team_open.json").write_text(json.dumps(t))
        # the answer the screen got at 09:20 (before the PO's hotfix): both open rows carried the id "nan"
        nan = json.loads(json.dumps(t))
        for x in nan["roster"]:
            if x["role"] == "empty":
                x["sleeper_id"] = "nan"
        (IN5_FIXTURES / "team_open_nan.json").write_text(json.dumps(nan))
