"""Wave I-I, II-0 (the fifth review § 1): the legal replacement chain, roster-aware names, one frame for the trade story.

No database: `lineup.replacement_chain` is checked against the solver itself on hand-built rosters (a locked FLEX,
players eligible at two positions, an empty slot, an MFL team QB, Superflex) and on random ones (every move legal, the
cost the re-solve's, a locked starter never moves); `cards.replacement_chain_rows` on a lineup frame; `cards.display_name`
on a surname collision; `trades.week_story`'s words carry exactly the table's numbers.
"""

from __future__ import annotations

import random
import re
import sys
from pathlib import Path

import pandas as pd
import pytest

APP = Path(__file__).resolve().parents[1] / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from lib import cards  # noqa: E402

from league_lab import lineup as lu  # noqa: E402
from league_lab import trades as T  # noqa: E402

SCRUBS = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "FLEX", "K", "DEF", "BN", "BN", "BN", "BN", "BN", "IR"]
SUPERFLEX = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "SUPER_FLEX", "BN", "BN", "BN", "BN"]
MFL_70587 = ["TMQB", "RB", "RB", "WR+TE", "WR+TE", "WR+TE", "TMPK", "DEF", "BN", "BN", "BN"]


def P(pid, pos, value, **kw):
    return lu.Player(id=str(pid), position=pos, value=value, value_source=kw.pop("value_source", "proj_points"), **kw)


def macz(**over) -> list[lu.Player]:
    """MacZaddy's week-4 roster on the clone (values to the cent; ids = names)."""
    base = [P("Mahomes", "QB", 20.26), P("Kyren", "RB", 12.8), P("Hampton", "RB", 11.28), P("McMillan", "WR", 12.75),
            P("Jefferson", "WR", 12.68), P("Kelce", "TE", 10.14), P("ParkerW", "WR", 12.16), P("Tuten", "RB", 9.72),
            P("McLaughlin", "K", 8.07), P("Chiefs", "DEF", 7.16), P("Shough", "QB", 18.17), P("Young", "QB", 17.25),
            P("MichaelW", "WR", 9.2), P("Croskey", "RB", 9.19), P("Ferguson", "TE", 5.79)]
    return [over.get(p.id, p) for p in base]


def test_the_review_case_a_cascade_through_flex():
    """Kyren sits: the RB at FLEX moves to RB, the WR fills the open FLEX; the cost is the re-solve's."""
    ch = lu.replacement_chain(macz(), SCRUBS, "Kyren")
    assert ch["cost"] == pytest.approx(12.8 - 9.2, abs=1e-6)
    assert [(c["kind"], c["player_id"], c["from_slot"], c["to_slot"]) for c in ch["chain"]] == [
        ("slides", "Tuten", "FLEX2", "RB1"), ("enters", "MichaelW", "BN", "FLEX2")]
    assert ch["words"] == "RB moves from FLEX to RB; a WR fills the open FLEX"
    assert lu.chain_words(ch["chain"], {"Tuten": "Bhayshul Tuten", "MichaelW": "Michael Wilson"}) == (
        "Bhayshul Tuten (RB) moves from FLEX to RB; Michael Wilson (WR) fills the open FLEX")
    assert ch["enters"] == "MichaelW" and ch["empty_slot"] is None and ch["legal"] is True


def test_a_locked_flex_stays_where_he_is():
    """Tuten's game has started (locked at FLEX): he cannot slide to RB, so the bench RB comes in directly."""
    ch = lu.replacement_chain(macz(Tuten=P("Tuten", "RB", 9.72, locked_slot="FLEX")), SCRUBS, "Kyren")
    assert [(c["kind"], c["player_id"], c["to_slot"]) for c in ch["chain"]] == [("enters", "Croskey", "RB1")]
    assert ch["cost"] == pytest.approx(12.8 - 9.19, abs=1e-6)
    assert ch["words"] == "an RB comes off the bench into RB"
    # and a locked bench RB (his game started on the bench) never enters: the WR cascade again
    ch = lu.replacement_chain(macz(Croskey=P("Croskey", "RB", 9.19, playable=False, reason="game started (bench)")),
                              SCRUBS, "Kyren")
    assert [c["player_id"] for c in ch["chain"]] == ["Tuten", "MichaelW"]
    # a locked player is not a decision: no chain for him
    assert lu.replacement_chain(macz(Kyren=P("Kyren", "RB", 12.8, locked_slot="RB")), SCRUBS, "Kyren") is None


def test_both_locked_the_slot_goes_empty_with_no_legal_move():
    roster = [P("Q", "QB", 20.0), P("R1", "RB", 10.0), P("R2", "RB", 8.0, locked_slot="RB"), P("W1", "WR", 9.0),
              P("W2", "WR", 7.0), P("W3", "WR", 6.0)]
    ch = lu.replacement_chain(roster, ["QB", "RB", "RB", "WR", "BN", "BN", "BN"], "R1")
    assert ch["chain"][0]["kind"] == "empty" and ch["empty_slot"] in ("RB1", "RB2") and ch["enters"] is None
    assert ch["cost"] == pytest.approx(10.0)
    assert ch["words"] == "no legal move: RB goes empty"


def test_a_player_eligible_at_two_positions_slides():
    """A WR/RB (fantasy_positions) at WR may slide to RB; the WR on the bench fills WR."""
    roster = [P("R1", "RB", 12.0), P("H", "WR", 11.0, fantasy_positions=("WR", "RB")), P("W1", "WR", 13.0),
              P("W9", "WR", 8.0)]
    ch = lu.replacement_chain(roster, ["RB", "WR", "WR", "BN", "BN"], "R1")
    assert [(c["kind"], c["player_id"]) for c in ch["chain"]] == [("slides", "H"), ("enters", "W9")]
    assert ch["cost"] == pytest.approx(12.0 - 8.0)


def test_mfl_team_qb_is_replaced_only_by_a_team_qb():
    roster = [P("cin", "TMQB", 22.0), P("tb", "TMQB", 19.5), P("qbX", "QB", 25.0), P("r1", "RB", 10.0), P("r2", "RB", 9.0),
              P("w1", "WR", 9.0), P("w2", "WR", 8.0), P("t1", "TE", 7.0), P("k", "TMPK", 8.0), P("d", "DEF", 6.0)]
    ch = lu.replacement_chain(roster, MFL_70587, "cin")
    assert [(c["kind"], c["player_id"], c["to_slot"]) for c in ch["chain"]] == [("enters", "tb", "TMQB")]
    assert ch["words"] == "a team QB comes off the bench into team QB"
    assert ch["cost"] == pytest.approx(2.5)


def test_superflex_cascade():
    """The QB sits: the Superflex QB moves to QB, the best bench player fills Superflex."""
    roster = [P("q1", "QB", 22.0), P("q2", "QB", 18.0), P("r1", "RB", 12.0), P("r2", "RB", 11.0), P("w1", "WR", 13.0),
              P("w2", "WR", 12.5), P("t", "TE", 8.0), P("f", "WR", 10.0), P("b1", "WR", 9.0), P("b2", "RB", 7.0)]
    ch = lu.replacement_chain(roster, SUPERFLEX, "q1")
    assert [(c["kind"], c["player_id"], c["from_slot"], c["to_slot"]) for c in ch["chain"]] == [
        ("slides", "q2", "SUPER_FLEX", "QB"), ("enters", "b1", "BN", "SUPER_FLEX")]
    assert ch["words"] == "QB moves from Superflex to QB; a WR fills the open Superflex"


@pytest.mark.parametrize("slots", [SCRUBS, SUPERFLEX])
def test_random_rosters_every_move_is_legal_and_locks_hold(slots):
    rng = random.Random(19)
    positions = ["QB", "RB", "WR", "TE"] + (["K", "DEF"] if "K" in slots else [])
    checked = cascades = 0
    for trial in range(150):
        players = [P(f"{trial}-{i}", rng.choice(positions), round(rng.uniform(0, 25), 2)) for i in range(rng.randint(9, 16))]
        base = lu.solve(players, slots, margins=False)
        starters = [s for s in base.starts if s.player is not None]
        locked = {s.player.id: s.slot.type for s in starters if rng.random() < 0.2}
        bench_locked = {p.id for p in base.bench if rng.random() < 0.2}
        roster = [P(p.id, p.position, p.value, locked_slot=locked.get(p.id)) if p.id in locked else
                  P(p.id, p.position, p.value, playable=False, reason="game started (bench)") if p.id in bench_locked else p
                  for p in players]
        base = lu.solve(roster, slots, margins=False)
        current = {s.player.id: s.slot.label for s in base.starts if s.player is not None}
        labels = {s.slot.label: s.slot for s in base.starts}
        for pid in current:
            ch = lu.replacement_chain(roster, slots, pid, current=current)
            if pid in locked:
                assert ch is None
                continue
            rest = lu.solve([p for p in roster if p.id != pid], slots, margins=False)
            assert ch["cost"] == pytest.approx(base.total - rest.total, abs=1e-6)
            pos = {p.id: p.position for p in roster}
            for c in ch["chain"]:
                if c["player_id"] is None:
                    continue
                assert c["player_id"] not in locked                         # a locked starter never moves
                assert c["player_id"] not in bench_locked                   # a locked bench player never enters
                if c["to_slot"] != lu.BENCH_SLOT:
                    assert pos[c["player_id"]] in labels[c["to_slot"]].elig  # every move is legal
            assert ch["chain"][0]["to_slot"] == current[pid]                # the chain starts at his slot
            checked += 1
            cascades += any(c["kind"] == "slides" for c in ch["chain"])
    assert checked > 500 and cascades > 10


# ------------------------------------------------------------------ the chain on a lineup frame (the card's rows)
def frame(lineup: lu.Lineup, names: dict[str, str], locked_bench: set[str] = frozenset()) -> pd.DataFrame:
    out = []
    for s in lineup.starts:
        p = s.player
        out.append({"role": "starter", "slot": s.slot.label, "slot_type": s.slot.type, "slot_order": s.slot.order,
                    "bench_rank": None, "gsis_id": p.id if p else None, "player_name": names.get(p.id) if p else None,
                    "position": p.position if p else None, "value": p.value if p else None, "value_source": "proj_points",
                    "margin": s.margin, "is_locked": s.locked, "is_empty_slot": p is None, "kicked_off": False})
    for i, p in enumerate(lineup.bench, 1):
        out.append({"role": "bench", "slot": None, "slot_type": None, "slot_order": None, "bench_rank": i, "gsis_id": p.id,
                    "player_name": names.get(p.id), "position": p.position, "value": p.value, "value_source": "proj_points",
                    "margin": None, "is_locked": False, "is_empty_slot": False, "kicked_off": p.id in locked_bench})
    df = pd.DataFrame(out)
    for c in ("report_status", "reason", "opponent", "opp_rank", "team"):
        df[c] = None
    df["is_weakest_slot"] = False
    df["locked_now"] = df["is_locked"] | df["kicked_off"]
    return df


NAMES = {"Tuten": "Bhayshul Tuten", "MichaelW": "Michael Wilson", "Croskey": "Jacory Croskey-Merritt",
         "Kyren": "Kyren Williams", "ParkerW": "Parker Washington", "Hampton": "Omarion Hampton"}


def test_card_rows_name_the_chain_and_respect_a_lock_since_the_solve():
    rows = frame(lu.solve(macz(), SCRUBS), NAMES)
    kyren = rows[rows["gsis_id"] == "Kyren"].iloc[0]
    a = cards.alternative(kyren, rows)
    assert a["alt"]["gsis_id"] == "MichaelW" and a["mover"]["gsis_id"] == "Tuten"
    assert a["chain"]["named_words"] == "Bhayshul Tuten (RB) moves from FLEX to RB; Michael Wilson (WR) fills the open FLEX"
    assert "comes in after a teammate slides over" in a["how"]
    # Croskey-Merritt's game kicks off after the solve (he is on the bench): same chain, he cannot enter anyway
    rows2 = frame(lu.solve(macz(), SCRUBS), NAMES, locked_bench={"Croskey"})
    assert cards.alternative(rows2[rows2["gsis_id"] == "Kyren"].iloc[0], rows2)["alt"]["gsis_id"] == "MichaelW"
    # Tuten's game kicks off after the solve (he starts at FLEX): he stays; Croskey-Merritt comes in at RB; the card's
    # margin is the re-solve's (3.61), not the stored 3.60
    rows3 = frame(lu.solve(macz(), SCRUBS), NAMES)
    rows3.loc[rows3["gsis_id"] == "Tuten", "kicked_off"] = True
    rows3["locked_now"] = rows3["is_locked"] | rows3["kicked_off"]
    a3 = cards.alternative(rows3[rows3["gsis_id"] == "Kyren"].iloc[0], rows3)
    assert a3["alt"]["gsis_id"] == "Croskey" and a3["mover"] is None and a3["chain"]["cost"] == pytest.approx(3.61)
    dec = cards.decisions(rows3, n=10)
    k = dec[dec["gsis_id"] == "Kyren"].iloc[0]
    assert k["margin"] == pytest.approx(3.61) and k["alt_name"] == "Jacory Croskey-Merritt"


# ------------------------------------------------------------------ names
def test_display_name_full_on_a_surname_collision():
    roster = ["Parker Washington", "Malik Washington", "Kyren Williams", "Kansas City Chiefs", "Michael Penix Jr."]
    assert cards.display_name("Parker Washington", roster) == "Parker Washington"
    assert cards.display_name("Malik Washington", roster) == "Malik Washington"
    assert cards.display_name("Kyren Williams", roster) == "Williams"
    assert cards.display_name("Michael Penix Jr.", roster) == "Penix"
    assert cards.display_name("Kansas City Chiefs", roster, "DEF") == "Kansas City Chiefs"
    assert cards.display_name("Parker Washington", ["Parker Washington"]) == "Washington"
    assert cards.display_name(None, roster) == ""
    # the card's reason line uses them (decisions() rows carry short_name / alt_short_name)
    names = dict(NAMES, ParkerW="Parker Washington", MichaelW="Malik Washington")
    rows = frame(lu.solve(macz(), SCRUBS), names)
    dec = cards.decisions(rows, n=10)
    k = dec[dec["gsis_id"] == "Kyren"].iloc[0]
    assert k["alt_short_name"] == "Malik Washington" and k["short_name"] == "Williams"
    assert "Washington" not in cards.reason_line(k.to_dict()).replace("Malik Washington", "")


# ------------------------------------------------------------------ one frame, one story
@pytest.mark.parametrize("by_week", [[-1.5, 0.2, 3.0, 0.0], [0.1, 19.4, -8.4, 0.0], [0.0, 2.0, 1.0, 0.5], [-1.0, -2.0, 0.0, 0.0],
                                     [2.04, 1.0, None, 0.0]])
def test_week_story_says_the_tables_numbers(by_week):
    s = T.week_story([4, 5, 6, 7], by_week, "weeks 4–7", this_week=4)
    w0 = by_week[0]
    if w0 <= -0.05:
        assert s["this_week"]["kind"] == "loss" and f"loses {abs(w0):.1f} this week" in s["words"]
        assert "Nothing changes this week" not in s["words"]
    elif w0 >= 0.05:
        assert s["this_week"]["kind"] == "gain" and f"gains {w0:.1f} this week" in s["words"]
    else:
        assert s["words"].startswith("Nothing changes this week")
    total = round(sum(x for x in by_week if x is not None), 2)
    assert s["window"]["change"] == pytest.approx(total)
    nums = {float(x) for x in re.findall(r"\d+\.\d", s["words"])}
    table = {round(abs(x), 1) for x in by_week if x is not None} | {round(abs(total), 1)}
    assert nums <= table                                                    # every number said is a number shown
    assert [r["change"] for r in s["by_week"]] == [None if x is None else round(x, 2) for x in by_week]


def test_week_story_a_window_that_starts_later_has_no_this_week():
    s = T.week_story([5, 6], [1.0, 2.0], "weeks 5–6", this_week=4)
    assert s["this_week"]["kind"] == "unknown" and "this week" not in s["words"]
    assert s["words"] == "Your lineup gains 3.0 over weeks 5–6 in total."
