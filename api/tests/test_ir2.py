"""Wave I-R, IR-2 — one trade verdict (the dependability review of 2026-10-07/08, P0 1 and 2).

Meaning and consistency, never today's projections:

* every primary number of the calculator's answer — the dial, the four tiles, the week table, the headline's verdict, the
  alternative comparison and the recommendation — reads ONE basis (`decision`: against realistic replacements) and
  reconciles to the same before / after totals and weekly changes; the roster-only result is a separately labelled
  explanation (`decision.unfilled`);
* reversing the perspective preserves each team's effect;
* the sentences pair the players of the SAME slot (the review's "It takes over their K from Matthew Stafford"), a FLEX
  cascade is a chain of slots, and depth has one definition (who can play that week; who cannot, named);
* one free agent is never counted for both teams in the same week.

The hand-built cases need no database (a stand-in context, `FakeCtx`); the Folk case reads the fixtures' League of
Scrubs (MacZaddy, team 2, and Run Bijan Run, team 3)."""

from __future__ import annotations

import re

import pytest
from league_lab import trades as T
from league_lab.lineup import Player, parse_slots
from league_lab.roster_value import RosterBoard

from league_lab_api import decisions as D

from .conftest import SCRUBS, needs_db

ONE_QB = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "K", "BN", "BN", "BN", "BN"]
MFL = ["TMQB", "RB", "WR", "WR", "FLEX", "TMPK", "BN", "BN", "BN"]


def P(pid: str, pos: str, value: float | None, **kw) -> Player:
    return Player(id=pid, position=pos, value=value, value_source="proj_points" if value is not None else None, **kw)


def U(pid: str, pos: str, reason: str) -> Player:
    return Player(id=pid, position=pos, value=None, playable=False, reason=reason)


def rows_for(roster: int, week: int, players: list[Player]) -> list[dict]:
    out = []
    for p in players:
        out.append({"roster_id": roster, "week": week, "sleeper_player_id": p.id, "gsis_id": f"g-{p.id}",
                    "player_name": p.id, "position": p.position, "fantasy_positions": [p.position],
                    "role": "bench" if p.playable else "unplayable", "slot": None, "slot_type": None,
                    "player_value": p.value, "value_source": p.value_source if p.playable else None,
                    "lineup_margin": None, "is_locked": False, "reason": p.reason})
    return out


def board(rosters: dict[int, dict[int, list[Player]]], slots) -> RosterBoard:
    rows = []
    for r, by_week in rosters.items():
        for w, ps in by_week.items():
            rows += rows_for(r, w, ps)
    return RosterBoard(rows, slots)


class FakeCtx:
    """The parts of `decisions.TradeContext` the card and the decision read, on a hand-built board (no database, no
    outside world): names are the ids, the free pool is given."""

    def __init__(self, b: RosterBoard, pool: dict[str, dict[int, Player]], this_week: int):
        self.board, self.slots, self.this_week = b, b.slots, this_week
        self.market, self.prices, self.window_cache = None, {}, {}
        self.league_id, self.is_house = "test:ir2", False
        self._pool = pool
        self._pos = {}
        for r in b.rosters:
            for p in b.roster(r):
                row = next((b.row(p, w) for w in b.weeks if b.row(p, w) is not None), None)
                self._pos[p] = row.get("position") if row else None
        self.meta = {pid: {"player_name": pid, "position": next(iter(ws.values())).position, "gsis_id": f"g-{pid}"}
                     for pid, ws in pool.items()}

    def name(self, pid):
        return str(pid)

    def pos(self, pid):
        return self._pos.get(str(pid)) or (self.meta.get(str(pid)) or {}).get("position")

    def gsis(self, pid):
        return f"g-{pid}"

    def player(self, pid):
        return {"sleeper_id": str(pid), "gsis_id": f"g-{pid}", "player_name": str(pid), "position": self.pos(pid)}

    def link(self, pid):
        return f"[{pid}](/player/g-{pid})"

    def team(self, rid):
        return {1: "Alpha", 2: "Beta"}[int(rid)]

    def fa_pool(self, weeks):
        return self._pool, self.meta


def free(by_week: dict[int, list[Player]]) -> dict[str, dict[int, Player]]:
    out: dict[str, dict[int, Player]] = {}
    for w, ps in by_week.items():
        for p in ps:
            out.setdefault(p.id, {})[w] = p
    return out


def decide(b: RosterBoard, pool, me: int, give: list[str], get: list[str], weeks=(5, 6), window="next4") -> tuple[dict, dict]:
    """(decision, card) for a package on a hand-built board, through the calculator's own functions."""
    ctx = FakeCtx(b, pool, weeks[0])
    weeks = tuple(weeks)
    span = f"weeks {weeks[0]}–{weeks[-1]}" if len(weeks) > 1 else f"week {weeks[0]}"
    fr = T._free_by_week(pool, weeks)
    frame = {"pool": pool, "meta": ctx.meta, "free": fr, "guard": T.guard_positions(b, weeks, fr), "market": {},
             "rules": {"waiver": "rolling", "platform": "sleeper", "league_type": None, "trade_deadline": None},
             "alts": {}}
    card = D._ii1_card(ctx, b, weeks, span, window, frame, me, give, get)
    them = b.owner(get[0])
    trade = T.evaluate(b, give, get, weeks, prices=ctx.prices)
    out = {"span": span, "partner_team": ctx.team(them), "partner": them}
    return D.ir2_decision(ctx, out, trade, trade, b, weeks, window, me, give, get, frame, card), card


def s1(x: float) -> str:
    """The decision's own sign (IT-1: one minus sign, U+2212)."""
    return (f"{x:+.1f}" if abs(x) >= 0.05 else "+0.0").replace("-", "\u2212")


def assert_reconciles(d: dict, card: dict, window: str = "next4") -> None:
    """Every primary number of the decision reconciles to the same before / after totals and weekly changes."""
    for k in ("mine", "theirs"):
        s = d[k]
        assert s["by_week"] == pytest.approx([a - b for a, b in zip(s["after"]["by_week"], s["before"]["by_week"], strict=True)],
                                             abs=0.011)
        assert s["gain_window"] == pytest.approx(s["after"]["window"] - s["before"]["window"], abs=0.011)
        assert s["gain_window"] == pytest.approx(sum(s["by_week"]), abs=0.03)
        assert s["before"]["window"] == pytest.approx(sum(s["before"]["by_week"]), abs=0.011)
        if d["this_week"] is not None:
            assert s["gain_week"] == pytest.approx(s["after"]["this_week"] - s["before"]["this_week"], abs=0.011)
            assert s["gain_week"] == pytest.approx(s["by_week"][0], abs=0.011)
        assert d["strip"][k] == pytest.approx(s["by_week"], abs=0.011)          # the week table and the strip
    # the dial: their effect over the window, your gain beside it, its label from that same number
    assert d["dial"]["their_gain"] == pytest.approx(d["theirs"]["gain_window"], abs=0.006)
    assert d["dial"]["you"] == pytest.approx(d["mine"]["gain_window"], abs=0.006)
    assert d["dial"]["label"] == D.effect_label(d["theirs"]["gain_window"])
    # the headline's verdict says the same numbers
    assert s1(d["mine"]["gain_window"]) in d["verdict"] or "no change" in d["verdict"]
    assert d["headline"].endswith(d["verdict"])
    assert d["story"]["window"]["change"] == pytest.approx(d["mine"]["gain_window"], abs=0.03)
    # the card (the "Worth proposing?" section) is on the same basis: same effects, same beyond, same answer
    g = "this_week" if window == "week" else "window"
    assert card["your_effect"][g] == pytest.approx(d["mine"]["gain_week" if window == "week" else "gain_window"], abs=0.006)
    assert card["their_effect"][g] == pytest.approx(d["theirs"]["gain_week" if window == "week" else "gain_window"], abs=0.006)
    assert card["beyond"]["mine"] == pytest.approx(d["alternative"]["beyond"]["mine"], abs=0.006)
    assert d["alternative"]["beyond"]["theirs"] == card["beyond"]["theirs"]
    assert d["recommendation"]["credible"] == (card["credible"] and d["alternative"]["beats"])
    assert d["recommendation"]["words"].startswith(d["recommendation"]["label"])
    assert d["basis"] == "replacement" and d["unfilled"]["label"] == D.IR2_UNFILLED_LABEL


def assert_slot_pairs(d: dict, slots) -> None:
    """A sentence never pairs players who could not both play that slot."""
    elig = {s.label: s.elig for s in parse_slots(slots)[0]}
    for k in ("mine", "theirs"):
        for ch in d["changes"][k]:
            for who in ("in_player", "out_player"):
                p = ch[who]
                if p is not None and p.get("position"):
                    assert p["position"] in elig[ch["slot"]], (ch["words"], p)


def same_effects(a: dict, b: dict) -> None:
    """``a`` read from one team, ``b`` from the other: each team's effect is the same."""
    for x, y in (("mine", "theirs"), ("theirs", "mine")):
        for f in ("gain_week", "gain_window", "by_week"):
            assert a[x][f] == pytest.approx(b[y][f], abs=0.006), (x, f)
        for st in ("before", "after"):
            assert a[x][st]["by_week"] == pytest.approx(b[y][st]["by_week"], abs=0.006)


# ------------------------------------------------------------------------------ hand-built cases (no database)
A = [P("aqb", "QB", 20), P("arb1", "RB", 15), P("arb2", "RB", 12), P("arb3", "RB", 11), P("awr1", "WR", 16),
     P("awr2", "WR", 14), P("ate", "TE", 9), P("ak", "K", 8), P("awr3", "WR", 5), P("aqb2", "QB", 13)]
B = [P("bqb", "QB", 18), P("brb1", "RB", 16), P("brb2", "RB", 13), P("bwr1", "WR", 13), P("bwr2", "WR", 12),
     P("bte", "TE", 7), P("brb3", "RB", 10), P("bk", "K", 8.5), P("bwr3", "WR", 4), P("bqb2", "QB", 12)]
FREE = [P("fk1", "K", 9.0), P("fk2", "K", 6.0), P("fqb", "QB", 14.0), P("fwr", "WR", 6.0), P("fte", "TE", 6.5)]


def two(a=A, b=B, *, a6=None, b6=None, slots=ONE_QB) -> RosterBoard:
    return board({1: {5: list(a), 6: list(a6 if a6 is not None else a)},
                  2: {5: list(b), 6: list(b6 if b6 is not None else b)}}, slots)


def test_flex_cascade_is_a_chain_of_slots():
    """Give the RB1 for a WR: the third RB slides from FLEX to RB, the WR takes the FLEX — two links of one chain,
    each sentence about one slot (never "the WR takes over the RB from …")."""
    b = two()
    d, card = decide(b, free({5: FREE, 6: FREE}), 1, ["arb1"], ["bwr1"])
    ch = {c["slot_word"]: c for c in d["changes"]["mine"]}
    assert set(ch) == {"FLEX", "RB"}
    assert ch["FLEX"]["in"] == "bwr1" and ch["FLEX"]["in_how"] == "trade" and ch["FLEX"]["out"] == "arb3"
    assert ch["RB"]["in"] == "arb3" and ch["RB"]["in_how"] == "slot" and ch["RB"]["out"] == "arb1"
    assert ch["RB"]["out_why"] == "traded"
    order = [c["slot_word"] for c in d["changes"]["mine"]]
    assert order == ["FLEX", "RB"]                                     # the chain starts where the WR enters
    assert d["changes"]["words"]["mine"] == ["bwr1 (from the trade) starts at FLEX in place of arb3",
                                             "arb3 moves from FLEX to RB in place of arb1 (traded)"]
    assert_reconciles(d, card)
    assert_slot_pairs(d, ONE_QB)


def test_mixed_position_package_pairs_each_slot():
    """RB + K for WR + K: the K sentence pairs the two kickers, the RB / FLEX sentences the skill players; the other
    side's sentences the same way (the review: "It takes over their K from Matthew Stafford")."""
    b = two()
    d, card = decide(b, free({5: FREE, 6: FREE}), 1, ["arb1", "ak"], ["bwr1", "bk"])
    k = next(c for c in d["changes"]["mine"] if c["slot_word"] == "K")
    assert (k["in"], k["out"]) == ("bk", "ak")
    kt = next(c for c in d["changes"]["theirs"] if c["slot_word"] == "K")
    assert (kt["in"], kt["out"]) == ("ak", "bk")
    assert "ak at their K in place of bk" in d["dial"]["need"]
    for c in d["changes"]["theirs"]:
        if c["in"] == "arb1":
            assert c["slot_word"] in ("RB", "FLEX")
    assert_slot_pairs(d, ONE_QB)
    assert_reconciles(d, card)


def test_reversal_preserves_each_teams_effect():
    b = two()
    pool = free({5: FREE, 6: FREE})
    d1, _ = decide(b, pool, 1, ["arb1", "ak"], ["bwr1", "bk"])
    d2, _ = decide(b, pool, 2, ["bwr1", "bk"], ["arb1", "ak"])
    same_effects(d1, d2)
    assert d1["changes"]["words"]["mine"] == d2["changes"]["words"]["theirs"]


def test_surplus_qb_in_a_one_qb_league_adds_nothing():
    """A backup QB behind a better starter adds no starter points: the raw projected points are not added."""
    b = two()
    d, card = decide(b, free({5: FREE, 6: FREE}), 1, ["awr3"], ["bqb2"])
    assert d["mine"]["gain_week"] == 0 and d["mine"]["gain_window"] == 0
    assert d["changes"]["mine"] == []
    assert d["dial"]["you"] == 0
    assert "Does not help your lineup" in d["verdict"]
    assert not d["recommendation"]["credible"]
    assert_reconciles(d, card)


def test_one_free_agent_is_never_counted_for_both_teams():
    """Both kickers on a bye in week 6, one good free kicker: in each state of the league one team gets him and the
    other the next one — and the answer is the same whichever side asks."""
    a6 = [p for p in A if p.id != "ak"] + [U("ak", "K", "bye")]
    b6 = [p for p in B if p.id != "bk"] + [U("bk", "K", "bye")]
    b = two(a6=a6, b6=b6)
    pool = free({5: FREE, 6: FREE})
    m, t = T.covered_pair(b, 1, ["awr3"], ["bwr3"], (5, 6), T._free_by_week(pool, (5, 6)))
    for st in ("fills_before", "fills_after"):
        assert set(getattr(m, st)[1]).isdisjoint(getattr(t, st)[1])
        assert {*getattr(m, st)[1], *getattr(t, st)[1]} == {"fk1", "fk2"}
    m2, t2 = T.covered_pair(b, 2, ["bwr3"], ["awr3"], (5, 6), T._free_by_week(pool, (5, 6)))
    assert (m.before, m.after, t.before, t.after) == (t2.before, t2.after, m2.before, m2.after)
    d, card = decide(b, pool, 1, ["awr3"], ["bwr3"])
    assert "fk1 (K, week 6)" in (d["fills"]["mine"]["words"] or "") + (d["fills"]["theirs"]["words"] or "")
    assert "not a sure one" in d["fills"]["mine"]["words"]
    assert_reconciles(d, card)


def test_depth_has_one_definition_and_names_who_cannot_play():
    """A backup given away: the bench left at his position who can play that week, and — named — those who cannot (a
    bye, the IR slot); the card's sentence is the same sentence."""
    a = [*A, P("arb5", "RB", 4), U("arb4", "RB", "IR slot")]
    a6 = [*[p for p in A if p.id != "arb2"], P("arb5", "RB", 4), U("arb2", "RB", "bye"), U("arb4", "RB", "IR slot")]
    b = two(a=a, a6=a6)
    d, card = decide(b, free({5: FREE, 6: FREE}), 1, ["arb5"], ["bwr3"])
    words = d["depth"]["mine"]["words"]
    assert words.startswith("you lose arb5, a backup RB: no RB left on your bench who can play in week 5 "
                            "(arb4 in the IR slot cannot)")
    assert words.endswith("bwr3 joins your bench as a backup WR")
    lost = d["depth"]["mine"]["lost"][0]["words"]
    assert card["depth_cost"]["mine"].startswith(lost[0].upper() + lost[1:] + ".")       # the same sentence


def test_mfl_team_units_are_slots_like_any_other():
    """An MFL team-QB unit for a team-QB unit and a WR: the team QB sentence pairs the two units, in "team QB" words."""
    a = [P("mfl:kc_qb", "TMQB", 19), P("arb1", "RB", 15), P("awr1", "WR", 16), P("awr2", "WR", 14), P("arb2", "RB", 9),
         P("mfl:kc_k", "TMPK", 8), P("awr3", "WR", 5)]
    bb = [P("mfl:buf_qb", "TMQB", 21), P("brb1", "RB", 14), P("bwr1", "WR", 13), P("bwr2", "WR", 12), P("brb2", "RB", 10),
          P("mfl:buf_k", "TMPK", 8.5), P("mfl:det_qb", "TMQB", 17)]
    b = board({1: {5: a, 6: a}, 2: {5: bb, 6: bb}}, MFL)
    pool = free({5: [P("fwr", "WR", 6.0)], 6: [P("fwr", "WR", 6.0)]})
    d, card = decide(b, pool, 1, ["mfl:kc_qb"], ["mfl:buf_qb", "bwr2"])
    qb = next(c for c in d["changes"]["mine"] if c["slot"] == "TMQB")
    assert (qb["in"], qb["out"], qb["slot_word"]) == ("mfl:buf_qb", "mfl:kc_qb", "team QB")
    tq = next(c for c in d["changes"]["theirs"] if c["slot"] == "TMQB")
    assert (tq["in"], tq["out"]) == ("mfl:kc_qb", "mfl:buf_qb")
    assert_slot_pairs(d, MFL)
    assert_reconciles(d, card)


def test_need_words_pair_by_slot():
    """`need_words` (kept for any reader) reads the slot changes too: the K sentence names the kickers."""
    b = two()
    tr = T.evaluate(b, ["ak"], ["bk"], (5,))
    ctx = FakeCtx(b, {}, 5)
    assert D.need_words(tr.theirs, ctx) == "puts ak at their K in place of bk"


# ------------------------------------------------------------------------------ the review's case on the fixtures
FOLK, STAFFORD, REICHARD = "650", "421", "11792"


@pytest.fixture
def folk(monkeypatch):
    monkeypatch.setenv("LEAGUE_LAB_AVAILABILITY", "off")
    D.clear_memo()
    ctx = D.trade_context(SCRUBS)
    if ctx.board.owner(FOLK) != 2 or ctx.board.owner(STAFFORD) != 3 or ctx.board.owner(REICHARD) != 3:
        pytest.skip("the fixtures' rosters do not hold the Folk package")
    return D.evaluate(SCRUBS, 2, 3, [FOLK], [STAFFORD, REICHARD], window="next4")


@needs_db
def test_folk_every_primary_number_on_one_basis(folk):
    out, d = folk, folk["decision"]
    assert_reconciles(d, out["card"])
    # the legacy fields the page used to read are copies of the decision, never a second answer
    assert out["fit"]["window"] == {"mine": d["mine"]["gain_window"], "theirs": d["theirs"]["gain_window"]}
    assert out["fit"]["this_week"] == {"mine": d["mine"]["gain_week"], "theirs": d["theirs"]["gain_week"]}
    assert out["interest"] == d["dial"]
    for k in ("mine", "theirs"):
        assert out["before"][k]["by_week"] == d[k]["before"]["by_week"]
        assert out["after"][k]["horizon"] == d[k]["after"]["window"]
    assert out["strip"] == d["strip"] and out["verdict"] == d["verdict"]
    assert out["beats_alternative"] == d["alternative"]["beats"]
    assert out["card"]["credible"] == d["recommendation"]["credible"]
    # this week's lineup table totals are the tiles' this-week numbers
    tot = out["lineups"]["mine"]["total"]
    assert (tot["before"], tot["after"]) == (d["mine"]["before"]["this_week"], d["mine"]["after"]["this_week"])
    # the top tiles and the "Worth proposing?" section can no longer disagree in sign (the review's −3.1 vs +6.1)
    assert (out["card"]["their_effect"]["window"] >= 0.05) == (d["dial"]["their_gain"] >= 0.05)
    # the roster-only numbers are the separately labelled explanation
    assert d["unfilled"]["label"] == "If empty slots were left empty"
    assert "an explanation, not the verdict" in d["unfilled"]["words"]


@needs_db
def test_folk_sentences_pair_the_same_slot(folk):
    d = folk["decision"]
    theirs = {c["slot_word"]: c for c in d["changes"]["theirs"]}
    assert theirs["K"]["in"] == FOLK and theirs["K"]["out"] == REICHARD
    assert theirs["QB"]["out"] == STAFFORD and theirs["QB"]["in_how"] == "bench"
    assert re.search(r"\bat their K in place of Reichard\b", d["dial"]["need"])
    assert re.search(r"\bat their QB in place of Stafford\b", d["dial"]["need"])
    assert "K from" not in d["dial"]["need"]
    mine = {c["slot_word"]: c for c in d["changes"]["mine"]}
    assert mine["K"]["in"] == REICHARD and mine["K"]["out"] == FOLK
    assert mine["QB"]["in"] == STAFFORD
    assert_slot_pairs(d, D.trade_context(SCRUBS).slots)


@needs_db
def test_folk_depth_sentences_agree(folk):
    out, d = folk, folk["decision"]
    dm = d["depth"]["mine"]
    lost = dm["lost"][0]
    assert lost["player"]["sleeper_id"] == "12533"                      # Croskey-Merritt, the required cut
    assert out["backup_words"] == f"Backup coverage: {dm['words']}."
    assert out["card"]["depth_cost"]["mine"].startswith(lost["words"][0].upper() + lost["words"][1:] + ".")
    n = len(lost["usable"])
    assert f"{n if n else 'no'} RB left on your bench who can play in week" in dm["words"]
    for x in lost["cannot_play"]:                                       # the IR-slot RBs are named, not counted
        assert x["player_name"] in dm["words"] and x["player_name"] not in lost["usable"]


@needs_db
def test_folk_reversed_preserves_each_teams_effect(folk):
    rev = D.evaluate(SCRUBS, 3, 2, [STAFFORD, REICHARD], [FOLK], window="next4")
    same_effects(folk["decision"], rev["decision"])
    assert rev["decision"]["dial"]["their_gain"] == pytest.approx(folk["decision"]["mine"]["gain_window"], abs=0.006)
    assert rev["card"]["beyond"]["mine"] == pytest.approx(folk["card"]["beyond"]["theirs"], abs=0.006)


def test_a_player_on_a_reserve_list_is_said_in_the_verdict():
    """The IR-1 hook: a package with a player on injured reserve (the board's own reason) says so in the verdict and
    the recommendation; his numbers are the board's (no games)."""
    a = [*A, U("arb9", "RB", "NFL injured reserve")]
    b = two(a=a)
    d, _ = decide(b, free({5: FREE, 6: FREE}), 1, ["arb9"], ["bwr3"])
    assert d["out_indefinitely"]["players"][0]["player"]["sleeper_id"] == "arb9"
    words = "arb9 is on injured reserve: no return date, so these numbers count no games from him."
    assert d["verdict"].endswith(words) and d["recommendation"]["words"].endswith(words)
    d2, _ = decide(b, free({5: FREE, 6: FREE}), 1, ["awr3"], ["bwr3"])
    assert d2["out_indefinitely"] is None
