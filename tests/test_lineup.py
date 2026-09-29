"""B1 exact lineup service: the solver against exhaustive enumeration of every legal lineup
(no database needed), the lineup builder on a hand-made league, speed, and the DDL copies."""

import math
import re
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest

from league_lab import db, lineup
from league_lab.lineup import (
    SLOT_ELIGIBILITY,
    LineupInputs,
    Player,
    build,
    parse_slots,
    solve,
    starter_slots,
)

ROOT = Path(__file__).resolve().parents[1]
SCRUBS = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "FLEX", "K", "DEF", "BN", "BN", "BN", "BN", "BN"]
DYNASTY = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "SUPER_FLEX", *["BN"] * 13]


# ------------------------------------------------------------------------------ the yardstick
def _unvalued(p: Player) -> bool:
    """No value yet: playable (or locked) without a finite value, or labelled unvalued: counts 0."""
    return p.value_source == "unvalued" or p.value is None or not math.isfinite(p.value)


def _v(p: Player) -> float:
    return 0.0 if _unvalued(p) else p.value


def brute(players: list[Player], slots: list[str]) -> tuple[float, int, int]:
    """The best legal lineup by enumeration, under the objective the solver promises: total first,
    filled slots second, valued starters third. Each slot takes nobody or one unused eligible player;
    locked players must sit in a slot of their locked type; players who cannot play never start; a
    player with no value yet counts 0. Returns (total, filled, valued). Independent of the solver."""
    types = [s.type for s in parse_slots(slots)[0]]
    locked = [p for p in players if p.locked_slot is not None]
    free = [p for p in players if p.locked_slot is None and p.playable]
    best = (-math.inf, 0, 0)

    def rec(j: int, used: frozenset, total: float, filled: int, valued: int) -> None:
        nonlocal best
        if j == len(types):
            if all(p.id in used for p in locked):
                best = max(best, (round(total, 6), filled, valued))
            return
        rec(j + 1, used, total, filled, valued)                    # leave the slot empty
        for p in [*(q for q in locked if q.locked_slot == types[j]),
                  *(q for q in free if q.positions & SLOT_ELIGIBILITY[types[j]])]:
            if p.id not in used:
                rec(j + 1, used | {p.id}, total + _v(p), filled + 1, valued + (not _unvalued(p)))

    rec(0, frozenset(), 0.0, 0, 0)
    return best


def check(players: list[Player], slots: list[str]) -> lineup.Lineup:
    """solve() == enumeration: total, filled slots and valued starters, legality, bench, and every
    margin re-solved by brute force."""
    lu = solve(players, slots)
    total, filled, valued = brute(players, slots)
    starters = [s.player for s in lu.starts if s.player is not None]
    assert lu.total == pytest.approx(total, abs=1e-6)
    assert len(starters) == filled, "an otherwise-empty slot left empty (or one filled too many)"
    assert sum(p.value_source != "unvalued" for p in starters) == valued, "an unvalued player displaced a valued one"
    by_id = {p.id: p for p in players}
    seen = []
    for s in lu.starts:
        if s.player is None:
            continue
        p = s.player
        seen.append(p.id)
        if s.locked:
            assert p.locked_slot == s.slot.type and s.margin is None
        else:
            assert p.positions & SLOT_ELIGIBILITY[s.slot.type], (p, s.slot)
            assert by_id[p.id].playable
            without = [q for q in players if q.id != p.id]
            assert s.margin == pytest.approx(lu.total - brute(without, slots)[0], abs=1e-6), (p.id, s.slot.label)
            assert s.margin >= 0
        if p.value_source == "unvalued":
            assert p.value == 0.0 and p.reason and (s.margin == 0.0 or s.locked)
    assert len(seen) == len(set(seen)), "a player in two slots"
    assert sum(s.value or 0.0 for s in lu.starts) == pytest.approx(lu.total, abs=1e-6)
    bench_vals = [p.value for p in lu.bench]
    assert bench_vals == sorted(bench_vals, reverse=True)
    assert {p.id for p in lu.bench} | set(seen) | {p.id for p in lu.unplayable} == {p.id for p in players}
    assert not ({p.id for p in lu.bench} & set(seen))
    assert lu.weakest is None or lu.weakest.player.value_source != "unvalued"
    return lu


def P(pid, pos, value, **kw) -> Player:
    return Player(id=pid, position=pos, value=value, value_source="proj_points", **kw)


def slot_of(lu, pid):
    return next((s.slot.label for s in lu.starts if s.player is not None and s.player.id == pid), None)


# ------------------------------------------------------------------------------ fixtures
def test_one_qb_flex_takes_the_best_leftover():
    ps = [P("q1", "QB", 20), P("q2", "QB", 18), P("r1", "RB", 15), P("r2", "RB", 12), P("r3", "RB", 11),
          P("w1", "WR", 14), P("w2", "WR", 9), P("w3", "WR", 8), P("t1", "TE", 7), P("t2", "TE", 10.5)]
    lu = check(ps, ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "BN"])
    assert lu.total == pytest.approx(20 + 15 + 12 + 14 + 9 + 10.5 + 11)
    assert slot_of(lu, "r3") == "FLEX" and slot_of(lu, "q2") is None
    assert [p.id for p in lu.bench] == ["q2", "w3", "t1"]
    assert lu.margins["FLEX"] == pytest.approx(11 - 8)            # w3 replaces r3
    assert lu.margins["QB"] == pytest.approx(20 - 18)             # q2 replaces q1


def test_two_qb():
    ps = [P("q1", "QB", 22), P("q2", "QB", 19), P("q3", "QB", 17), P("r1", "RB", 30), P("w1", "WR", 5)]
    lu = check(ps, ["QB", "QB", "RB", "WR"])
    assert {slot_of(lu, "q1"), slot_of(lu, "q2")} == {"QB1", "QB2"} and slot_of(lu, "q3") is None
    assert lu.lineup["QB1"][0].id == "q1"                          # same-type slots listed best first
    assert lu.margins["QB2"] == pytest.approx(19 - 17)


def test_superflex_starts_a_non_qb_when_that_is_better():
    sf = ["QB", "RB", "WR", "TE", "FLEX", "SUPER_FLEX"]
    ps = [P("q1", "QB", 24), P("q2", "QB", 9), P("r1", "RB", 16), P("r2", "RB", 14), P("r3", "RB", 12),
          P("w1", "WR", 15), P("t1", "TE", 6)]
    lu = check(ps, sf)
    assert lu.lineup["SUPER_FLEX"][0].id in {"r2", "r3"} and slot_of(lu, "q2") is None
    assert lu.total == pytest.approx(24 + 16 + 15 + 6 + 14 + 12)
    # ...and a QB when the QB2 is the better player
    lu = check([*ps[:1], P("q2", "QB", 21), *ps[2:]], sf)
    assert lu.lineup["SUPER_FLEX"][0].id == "q2"
    # a QB3 behind two better QBs never raises the lineup (brief § 1: 25 / 24 / 22)
    base = [P("a", "QB", 25), P("b", "QB", 24), P("w", "WR", 9)]
    two = solve(base, ["QB", "WR", "SUPER_FLEX"]).total
    assert solve([*base, P("c", "QB", 22)], ["QB", "WR", "SUPER_FLEX"]).total == pytest.approx(two)
    # ...while a WR at 12 who pushes a 9-point FLEX to the bench is worth +3 (the brief's example)
    base = [*base[:2], P("w", "WR", 10), P("f", "WR", 9)]
    with_x = solve([*base, P("x", "WR", 12)], ["QB", "WR", "FLEX", "SUPER_FLEX"]).total
    assert with_x - solve(base, ["QB", "WR", "FLEX", "SUPER_FLEX"]).total == pytest.approx(3)


def _greedy_sql_order(players, slots):
    """mart_league_optimal_lineup's order: fixed slots by points, then REC_FLEX, WRRB_FLEX, FLEX, SUPER_FLEX."""
    types = [s.type for s in parse_slots(slots)[0]]
    left = sorted(players, key=lambda p: -p.value)
    total = 0.0
    for kind in ("fixed", "REC_FLEX", "WRRB_FLEX", "FLEX", "SUPER_FLEX"):
        for t in [t for t in types if (t == kind if kind != "fixed" else t in ("QB", "RB", "WR", "TE", "K", "DEF"))]:
            p = next((p for p in left if p.position in SLOT_ELIGIBILITY[t]), None)
            if p is not None:
                total += p.value
                left.remove(p)
    return total


def test_mixed_flex_types_beat_the_greedy_order():
    slots = ["REC_FLEX", "WRRB_FLEX"]
    ps = [P("w", "WR", 10), P("t", "TE", 9), P("r", "RB", 1)]
    lu = check(ps, slots)
    assert lu.total == pytest.approx(19) and _greedy_sql_order(ps, slots) == pytest.approx(11)
    assert slot_of(lu, "t") == "REC_FLEX" and slot_of(lu, "w") == "WRRB_FLEX"
    ps = [P("r1", "RB", 13), P("r2", "RB", 8), P("w1", "WR", 12), P("w2", "WR", 11), P("w3", "WR", 7),
          P("t1", "TE", 9), P("t2", "TE", 8.5)]
    check(ps, ["RB", "WR", "TE", "FLEX", "REC_FLEX", "WRRB_FLEX"])


def test_dual_eligibility():
    # Travis Hunter: Sleeper position DB, fantasy_positions DB/WR -> he may start at WR / FLEX
    hunter = Player(id="th", position="DB", value=11.0, fantasy_positions=("DB", "WR"))
    ps = [hunter, P("w1", "WR", 12), P("w2", "WR", 6), P("r1", "RB", 9)]
    lu = check(ps, ["WR", "WR", "FLEX"])
    assert slot_of(lu, "th") in {"WR1", "WR2"} and lu.total == pytest.approx(12 + 11 + 9)
    # a QB/TE may fill QB, TE, FLEX (as a TE) or SUPER_FLEX
    qbte = Player(id="qt", position="TE", value=14.0, fantasy_positions=("QB", "TE"))
    check([qbte, P("q1", "QB", 20), P("t1", "TE", 8), P("r1", "RB", 10)], ["QB", "TE", "FLEX", "SUPER_FLEX"])
    check([qbte, P("q1", "QB", 20), P("t1", "TE", 8)], ["QB", "TE"])


def test_byes_and_injuries_never_start():
    ps = [P("r1", "RB", 25, playable=False, reason="bye"), P("r2", "RB", 20, playable=False, reason="Out"),
          P("r3", "RB", 10, status="Questionable"), P("r4", "RB", None), P("r5", "RB", 4)]
    lu = check(ps, ["RB", "FLEX"])
    assert set(lu.starter_ids) == {"r3", "r5"}
    assert {p.id: p.reason for p in lu.unplayable} == {"r1": "bye", "r2": "Out"}
    assert lu.lineup["RB"][0].status == "Questionable"             # plays, flagged
    assert [(p.id, p.value, p.value_source, p.reason) for p in lu.bench] == [("r4", 0.0, "unvalued", "no value yet")]


# ------------------------------------------------------------------------------ unvalued (no value yet)
def test_the_only_k_is_unvalued_so_he_is_seated_at_zero():
    ps = [P("q1", "QB", 18), P("r1", "RB", 9), Player(id="k1", position="K", value=None, reason="no value yet")]
    lu = check(ps, ["QB", "RB", "K"])
    k = lu.lineup["K"][0]
    assert (k.id, k.value, k.value_source) == ("k1", 0.0, "unvalued") and lu.empty_slots == []
    assert lu.total == pytest.approx(27) and lu.margins["K"] == 0.0     # total unchanged, margin 0
    assert lu.weakest.slot.label == "RB"                                # not a decision: never the weakest


def test_an_unvalued_wr_sits_behind_valued_wrs():
    ps = [P("w1", "WR", 12), P("w2", "WR", 9), P("wu", "WR", None), P("w0", "WR", 0.0)]
    lu = check(ps, ["WR", "WR"])
    assert set(lu.starter_ids) == {"w1", "w2"} and lu.total == pytest.approx(21)
    assert [p.id for p in lu.bench] == ["w0", "wu"]                     # both at 0; valued first
    # at a tie with a valued player worth exactly 0, the valued one starts
    lu = check([P("w0", "WR", 0.0), P("wu", "WR", None)], ["WR"])
    assert lu.starter_ids == ["w0"]
    # an explicit value_source="unvalued" is carried at 0 whatever value it came with
    lu = check([Player(id="x", position="WR", value=7.0, value_source="unvalued"), P("w", "WR", 1.0)], ["WR"])
    assert lu.starter_ids == ["w"] and lu.bench[0].value == 0.0


def test_an_unvalued_player_fills_an_otherwise_empty_flex():
    ps = [P("r1", "RB", 10), P("w1", "WR", 8), Player(id="ru", position="RB", value=None)]
    lu = check(ps, ["RB", "WR", "FLEX", "TE"])
    assert lu.lineup["FLEX"][0].id == "ru" and lu.total == pytest.approx(18)
    assert lu.empty_slots == ["TE"]                                     # empty = nobody eligible at all
    # filled slots second: the valued WR takes WR so the unvalued RB can take FLEX (not WR at FLEX, WR empty)
    lu = check([P("a", "WR", 5), Player(id="u", position="RB", value=None)], ["WR", "FLEX"])
    assert (slot_of(lu, "a"), slot_of(lu, "u")) == ("WR", "FLEX")
    # locked with no value: seated in his slot at 0, no margin
    lu = check([Player(id="d", position="DEF", value=None, locked_slot="DEF"), P("q", "QB", 20)], ["QB", "DEF"])
    assert lu.lineup["DEF"][0].value_source == "unvalued" and lu.starts[1].locked and lu.starts[1].margin is None


def test_locked_starter_keeps_his_slot():
    ps = [P("r1", "RB", 5, locked_slot="RB"), P("r2", "RB", 14), P("r3", "RB", 12), P("w1", "WR", 11),
          P("w2", "WR", 3, locked_slot="FLEX")]
    lu = check(ps, ["RB", "RB", "WR", "FLEX"])
    assert slot_of(lu, "r1") in {"RB1", "RB2"} and slot_of(lu, "w2") == "FLEX"
    assert slot_of(lu, "r3") is None and lu.total == pytest.approx(5 + 14 + 11 + 3)
    locked = [s for s in lu.starts if s.locked]
    assert len(locked) == 2 and all(s.margin is None for s in locked)
    assert lu.weakest.player.id in {"r2", "w1"}                    # a locked player is not a decision
    # a lock into a slot the lineup does not have (or already taken) is reported, not forced
    lu = solve([P("k", "K", 8, locked_slot="K"), P("r", "RB", 3)], ["RB"])
    assert lu.unplayable[0].id == "k" and "locked in K" in lu.unplayable[0].reason


def test_fewer_players_than_slots_reports_empty_slots():
    ps = [P("q1", "QB", 18), P("r1", "RB", 11), P("t1", "TE", 4)]
    lu = check(ps, DYNASTY)
    assert lu.total == pytest.approx(33)
    assert lu.empty_slots == ["RB2", "WR1", "WR2", "FLEX", "SUPER_FLEX"]
    assert lu.lineup["TE"][0].id == "t1" and lu.lineup["WR1"] == (None, None)
    assert solve([], SCRUBS).empty_slots == [s.label for s in parse_slots(SCRUBS)[0]]


def test_k_and_def_present_and_absent():
    ps = [P("q1", "QB", 18), P("k1", "K", 9.5), P("k2", "K", 8.0), P("d1", "DEF", 6.0)]
    lu = check(ps, ["QB", "K", "DEF"])
    assert lu.margins == pytest.approx({"QB": 18.0, "K": 1.5, "DEF": 6.0})
    lu = check(ps[:1], ["QB", "K", "DEF"])                        # no K or DEF on the roster: empty, reported
    assert lu.empty_slots == ["K", "DEF"]
    lu = check(ps, DYNASTY)                                        # no K / DEF slot: they cannot play here
    assert {p.id: p.reason for p in lu.unplayable} == {"k1": "no K slot in this lineup", "k2": "no K slot in this lineup",
                                                       "d1": "no DEF slot in this lineup"}
    lu = solve([Player(id="k", position="K", value=None), P("q", "QB", 9)], DYNASTY)   # no K slot and no value:
    assert (lu.unplayable[0].value, lu.unplayable[0].value_source) == (None, None)  # unknown stays NULL


def test_a_negative_value_never_beats_an_empty_slot_and_zero_still_fills():
    lu = check([P("d1", "DEF", -2.0), P("k1", "K", 0.0)], ["DEF", "K"])
    assert lu.empty_slots == ["DEF"] and lu.lineup["K"][0].id == "k1"
    assert lu.bench[0].id == "d1"


def test_slot_parsing():
    slots, ignored = parse_slots(["QB", "RB", "RB", "FLEX", "IDP_FLEX", "DL", "BN", "IR", "TAXI", "super_flex"])
    assert [s.label for s in slots] == ["QB", "RB1", "RB2", "FLEX", "SUPER_FLEX"]
    assert [s.order for s in slots] == [1, 2, 3, 4, 5] and ignored == ["IDP_FLEX", "DL"]
    assert solve([P("q", "QB", 1)], ["QB", "LB"]).ignored_slots == ("LB",)


def test_dicts_are_accepted_as_player_records():
    lu = solve([{"id": "a", "position": "WR", "value": 3.0, "playable": True, "locked_slot": None, "value_source": "proj_points"}],
               ["WR"])
    assert lu.starter_ids == ["a"]


@pytest.mark.parametrize("seed", range(240))
def test_random_rosters_match_enumeration(seed):
    rng = np.random.default_rng(seed)
    pool = ["QB", "RB", "WR", "TE", "K", "DEF", "FLEX", "SUPER_FLEX", "REC_FLEX", "WRRB_FLEX"]
    slots = list(rng.choice(pool, size=int(rng.integers(1, 6))))
    players = []
    for i in range(int(rng.integers(0, 8))):
        pos = str(rng.choice(["QB", "RB", "WR", "TE", "K", "DEF"]))
        value = float(np.round(rng.gamma(2, 5), 2)) if rng.random() > 0.05 else float(np.round(-rng.random() * 3, 2))
        fp = (pos, str(rng.choice(["WR", "TE", "QB"]))) if rng.random() < 0.1 else None
        lock = None
        if rng.random() < 0.1:
            open_types = [t for t in slots if SLOT_ELIGIBILITY[t] & {pos, *(fp or ())}
                          and slots.count(t) > sum(p.locked_slot == t for p in players)]
            lock = str(rng.choice(open_types)) if open_types else None
        r = rng.random()
        value = None if r < 0.15 else (0.0 if r < 0.22 else value)          # unvalued / valued at exactly 0
        players.append(Player(id=f"p{i}", position=pos, value=value, playable=bool(rng.random() > 0.1),
                              locked_slot=lock, fantasy_positions=fp,
                              value_source="unvalued" if rng.random() < 0.05 else "proj_points"))
    check(players, slots)


def _real_roster(n: int, rng) -> list[Player]:
    mix = ["QB", "QB", "RB", "RB", "RB", "WR", "WR", "WR", "TE", "K", "DEF", "RB", "WR", "WR", "TE",
           "QB", "RB", "WR", "WR", "TE", "RB", "WR", "QB", "RB", "WR", "TE"]
    return [Player(id=f"p{i}", position=mix[i], value=float(rng.gamma(3, 4)), playable=bool(rng.random() > 0.1),
                   status="Questionable" if rng.random() < 0.1 else None) for i in range(n)]


@pytest.mark.parametrize(("slots", "n"), [(SCRUBS, 15), (SCRUBS, 17), (DYNASTY, 21), (DYNASTY, 26)])
def test_real_slot_sets_solve_in_under_5_ms(slots, n):
    rng = np.random.default_rng(n)
    rosters = [_real_roster(n, rng) for _ in range(40)]
    solve(rosters[0], slots)                                       # warm-up (imports, caches)
    times = []
    for r in rosters:
        t0 = time.perf_counter()
        lu = solve(r, slots)                                       # with every margin re-solved
        times.append(time.perf_counter() - t0)
        assert lu.margins
    assert float(np.median(times)) < 0.005, f"median {np.median(times) * 1e3:.2f} ms"
    assert max(times) < 0.025, f"worst {max(times) * 1e3:.2f} ms"


# ------------------------------------------------------------------------------ the builder
def _inputs() -> LineupInputs:
    """One hand-made league, one roster: week 1 scored, week 2 in progress (KC played Thursday),
    week 3 ahead with BUF on bye. Added after week 2: a veteran K (LAR, i.e. nflverse LA), a WR with
    no v2 projection and the Rams DEF (never scored in this league) — the last two have no value yet."""
    kick = datetime(2026, 9, 17, 0, 15, tzinfo=UTC)
    games = {w: {"KC": kick + timedelta(days=7 * (w - 1)), "BUF": kick + timedelta(days=7 * (w - 1), hours=60),
                 "LA": kick + timedelta(days=7 * (w - 1), hours=61)} for w in (1, 2, 3)}
    del games[3]["BUF"]
    cur = [{"sleeper_player_id": sid, "gsis_id": g, "player_name": name, "position": pos, "nfl_team": team,
            "is_on_ir": ir, "is_on_taxi": taxi}
           for sid, g, name, pos, team, ir, taxi in [
               ("1", "g1", "Mahomes", "QB", "KC", False, False), ("2", "g2", "Allen", "QB", "BUF", False, False),
               ("3", "g3", "Cook", "RB", "BUF", False, False), ("4", "g4", "Kyren", "RB", "LAR", False, False),
               ("5", "g5", "Kelce", "TE", "KC", False, False), ("6", "g6", "Hurt WR", "WR", "LAR", True, False),
               ("7", None, "Rookie K", "K", "KC", False, False), ("KC", None, "Chiefs", "DEF", "KC", False, False),
               ("8", "g8", "Taxi RB", "RB", "KC", False, True), ("9", "g9", "Vet K", "K", "LAR", False, False),
               ("10", "g10", "New WR", "WR", "KC", False, False), ("LAR", None, "Rams", "DEF", "LAR", False, False)]]
    slot = {"1": "QB", "3": "RB", "4": "FLEX", "5": "TE", "7": "K", "KC": "DEF"}
    week_list = {w: [{**r, "is_starter": r["sleeper_player_id"] in slot, "slot": slot.get(r["sleeper_player_id"]),
                      "points_observed": obs, "is_scored_week": w == 1}
                     for r, obs in zip(cur[:9], [20.0, 30.0, 12.0, 9.0, 7.0, 0.0, 8.0, 4.0, 1.0], strict=True)]
                 for w in (1, 2)}
    proj = {}
    for w in (1, 2, 3):
        for g, team, pts, status in [("g1", "KC", 21.0, None), ("g2", "BUF", 24.0, "Questionable"), ("g3", "BUF", 14.0, None),
                                     ("g4", "LA", 13.0, "Out" if w == 3 else None), ("g5", "KC", 8.0, None),
                                     ("g6", "LA", 11.0, None), ("g8", "KC", 6.0, None)]:
            if w == 3 and team == "BUF":
                continue                                           # no projection row on a bye
            proj[("L", w, g)] = {"proj_points": pts, "team": team, "report_status": status, "roster_status": "ACT"}
    return LineupInputs(
        season=2026, leagues=[{"league_id": "L", "roster_positions": ["QB", "RB", "TE", "FLEX", "SUPER_FLEX", "K", "DEF", "BN"],
                               "last_scored_leg": 1, "roster_ids": [1]}],
        weeks={"L": [1, 2, 3]}, proj=proj,
        weekly={("L", w): {1: rows} for w, rows in week_list.items()}, current={"L": {1: cur}},
        sleeper={r["sleeper_player_id"]: {"position": r["position"], "fantasy_positions": [r["position"]],
                                          "team": r["nfl_team"]} for r in cur},
        k_ppg={("L", "g9"): 9.5}, games=games, fingerprints={("L", 1, 1): "abc"}, model_version="v2.0")


def test_build_proposed_realised_locks_byes_and_flags():
    as_of = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)               # week 2: KC played Thursday, BUF / LA not yet
    rows, totals, _ = build(_inputs(), as_of=as_of)
    tot = {(t["week"], t["is_realised"]): t for t in totals}
    assert set(tot) == {(1, False), (1, True), (2, False), (3, False)}
    for (week, realised) in tot:                                   # every lineup: each slot and each player once
        sub = [x for x in rows if (x["week"], x["is_realised"]) == (week, realised)]
        assert sorted(x["slot"] for x in sub if x["slot"]) == sorted(["QB", "RB", "TE", "FLEX", "SUPER_FLEX", "K", "DEF"])
        ids = [x["sleeper_player_id"] for x in sub if x["sleeper_player_id"]]
        assert len(ids) == len(set(ids))
    r = {(x["week"], x["is_realised"], x["sleeper_player_id"]): x for x in rows if x["sleeper_player_id"]}

    # week 1 (scored): the proposal uses that week's Sleeper list, no IR / taxi flags (unknown for a past
    # week), no locks; K without an NFL id and DEF at the points Sleeper counted for them this season
    assert r[(1, False, "2")]["slot"] == "QB" and r[(1, False, "1")]["slot"] == "SUPER_FLEX"
    assert r[(1, False, "2")]["report_status"] == "Questionable"
    assert r[(1, False, "6")]["role"] == "bench"
    assert (r[(1, False, "7")]["value"], r[(1, False, "7")]["value_source"]) == (8.0, "observed_ppg")
    assert (r[(1, False, "KC")]["value"], r[(1, False, "KC")]["value_source"]) == (4.0, "observed_ppg")
    assert (1, False, "9") not in r                                # not on the roster yet
    # realised: Allen QB, Mahomes SF, Cook RB, Kyren FLEX, Kelce, K, DEF at Sleeper's points
    assert tot[(1, True)]["lineup_value"] == 30 + 20 + 12 + 9 + 7 + 8 + 4
    assert tot[(1, True)]["inputs_fingerprint"] == "abc" and tot[(1, False)]["inputs_fingerprint"] is None
    assert {x["value_source"] for k, x in r.items() if k[1] and x["role"] == "starter"} == {"sleeper_observed"}

    # week 2 (in progress): KC has kicked off -> Mahomes, Kelce, the K and the DEF are locked in their
    # Sleeper slots (no margin: not a decision); Allen (BUF) is still free; IR slot / taxi cannot play
    w2 = {k[2]: x for k, x in r.items() if k[:2] == (2, False)}
    assert [w2[s]["slot"] for s in ("1", "5", "7", "KC")] == ["QB", "TE", "K", "DEF"]
    assert all(w2[s]["is_locked"] and w2[s]["margin"] is None for s in ("1", "5", "7", "KC"))
    assert w2["2"]["slot"] == "SUPER_FLEX" and not w2["2"]["is_locked"]
    assert w2["6"]["reason"] == "IR slot" and w2["8"]["reason"] == "taxi squad"
    assert tot[(2, False)]["n_locked"] == 4 and tot[(2, False)]["weakest_slot"] == "FLEX"

    # week 3: no Sleeper list yet -> today's roster; BUF on bye (no projection row), Kyren Out; the
    # veteran K (LAR -> LA plays) at his season PPG beats the rookie K
    w3 = {k[2]: x for k, x in r.items() if k[:2] == (3, False)}
    assert (w3["2"]["reason"], w3["3"]["reason"], w3["4"]["reason"]) == ("bye", "bye", "Out")
    assert (w3["9"]["slot"], w3["9"]["value"], w3["9"]["value_source"]) == ("K", 9.5, "season_ppg")
    assert w3["7"]["role"] == "bench" and w3["1"]["slot"] == "QB" and w3["1"]["margin"] == pytest.approx(21.0)
    t3 = tot[(3, False)]
    # the WR without a projection fills the otherwise-empty FLEX at 0 (unvalued); RB / SUPER_FLEX: nobody eligible
    assert (w3["10"]["slot"], w3["10"]["value"], w3["10"]["value_source"], w3["10"]["reason"], w3["10"]["margin"]) == \
        ("FLEX", 0.0, "unvalued", "no value yet", 0.0)
    # the Rams DEF has no value yet and sits behind the Chiefs DEF (valued at Sleeper's PPG)
    assert (w3["LAR"]["role"], w3["LAR"]["value_source"], w3["KC"]["slot"]) == ("bench", "unvalued", "DEF")
    assert t3["empty_slots"] == "RB, SUPER_FLEX" and t3["lineup_value"] == 21 + 8 + 9.5 + 4   # total unchanged
    assert (t3["n_unvalued"], t3["n_ppg_valued"], t3["weakest_slot"], t3["weakest_margin"]) == (1, 2, "K", 1.5)
    assert t3["bench_value"] == 8.0                                  # the rookie K; the unvalued add nothing


def test_starter_slots_follow_roster_positions_without_bench():
    rp = ["QB", "RB", "WR", "FLEX", "DL", "K", "DEF", "BN", "BN", "IR", "TAXI"]
    assert starter_slots(rp, ["q", "r", "0", "w", "idp", "k", "CLE"]) == {
        "q": "QB", "r": "RB", "w": "FLEX", "idp": "DL", "k": "K", "CLE": "DEF"}     # "0" = empty WR; DL keeps its place
    assert starter_slots(rp, ["q", "r"]) == {"q": "QB", "r": "RB"} and starter_slots(rp, None) == {}


def _no_list_inputs(weekly: bool = False) -> LineupInputs:
    """Week 1 in progress with NO Sleeper weekly list (the fetch has not run since Thursday): PIT @ CLE has
    kicked off, KC and BUF have not. Sleeper's `starters` array: QB Watson (CLE), RB Hunt (KC), WR "0"
    (empty), FLEX Pickens (PIT), DL an IDP, K Butker (KC), DEF Cleveland."""
    kick = datetime(2026, 9, 11, 0, 15, tzinfo=UTC)
    games = {1: {"CLE": kick, "PIT": kick, "KC": kick + timedelta(days=3), "BUF": kick + timedelta(days=3, hours=4)}}
    roster = [("q", "g-q", "Watson", "QB", "CLE"), ("r", "g-r", "Hunt", "RB", "KC"), ("w", "g-w", "Pickens", "WR", "PIT"),
              ("idp", None, "Garrett", "DL", "KC"), ("k", "g-k", "Butker", "K", "KC"), ("CLE", None, "Browns", "DEF", "CLE"),
              ("rp", "g-rp", "Warren", "RB", "PIT"), ("rb", "g-rb", "Cook", "RB", "BUF"), ("wk", "g-wk", "Rice", "WR", "KC")]
    cur = [{"sleeper_player_id": sid, "gsis_id": g, "player_name": n, "position": pos, "nfl_team": t, "is_on_ir": False,
            "is_on_taxi": False} for sid, g, n, pos, t in roster]
    proj = {("L", 1, g): {"proj_points": pts, "team": t, "report_status": None, "roster_status": "ACT"}
            for g, t, pts in [("g-q", "CLE", 20.0), ("g-r", "KC", 6.0), ("g-w", "PIT", 11.0), ("g-rp", "PIT", 16.0),
                              ("g-rb", "BUF", 14.0), ("g-wk", "KC", 9.0)]}
    rp = ["QB", "RB", "WR", "FLEX", "DL", "K", "DEF", "BN", "BN", "BN", "BN"]
    weekly_list = {}
    if weekly:   # a Sleeper list for the week says Pickens sits and Warren starts at FLEX: the list wins
        weekly_list = {("L", 1): {1: [{**r, "is_starter": r["sleeper_player_id"] in {"q", "r", "rp", "idp", "k", "CLE"},
                                       "slot": {"q": "QB", "r": "RB", "rp": "FLEX", "idp": "DL", "k": "K", "CLE": "DEF"}.get(r["sleeper_player_id"]),
                                       "points_observed": None, "is_scored_week": False} for r in cur]}}
    return LineupInputs(
        season=2026, leagues=[{"league_id": "L", "roster_positions": rp, "last_scored_leg": 0, "roster_ids": [1]}],
        weeks={"L": [1]}, proj=proj, weekly=weekly_list, current={"L": {1: cur}},
        sleeper={r["sleeper_player_id"]: {"position": r["position"], "fantasy_positions": [r["position"]], "team": r["nfl_team"]} for r in cur},
        k_ppg={("L", "g-k"): 8.0}, games=games, model_version="v2.0",
        starters={("L", 1): ["q", "r", "0", "w", "idp", "k", "CLE"]})


def test_build_locks_todays_starters_when_the_week_has_no_sleeper_list():
    as_of = datetime(2026, 9, 11, 12, 0, tzinfo=UTC)                # PIT @ CLE under way, KC / BUF not yet
    rows, totals, _ = build(_no_list_inputs(), as_of=as_of)
    r = {x["sleeper_player_id"]: x for x in rows if x["sleeper_player_id"]}
    # started starters are locked in the slot Sleeper's array implies (no margin: not a decision)
    assert {k: (r[k]["slot"], r[k]["is_locked"], r[k]["margin"]) for k in ("q", "w", "CLE")} == {
        "q": ("QB", True, None), "w": ("FLEX", True, None), "CLE": ("DEF", True, None)}
    assert r["CLE"]["value_source"] == "unvalued"                  # a locked DEF with no Sleeper points yet: 0
    # a started bench player cannot come in, although he out-projects everyone at RB
    assert (r["rp"]["role"], r["rp"]["reason"]) == ("unplayable", "game started (bench)")
    # the rest is solved: Sleeper's RB starter Hunt (KC, not started) is free to move and loses RB to Cook;
    # the empty ("0") WR slot is filled by Rice; the K stays; the IDP has no modelled slot
    assert (r["rb"]["slot"], r["wk"]["slot"], r["k"]["slot"], r["r"]["role"]) == ("RB", "WR", "K", "bench")
    assert not r["r"]["is_locked"] and r["idp"]["reason"] == "no DL slot in this lineup"
    t = totals[0]
    rest = solve([Player(id=i, position=pos, value=v) for i, pos, v in [("r", "RB", 6.0), ("rb", "RB", 14.0), ("wk", "WR", 9.0), ("k", "K", 8.0)]],
                 ["RB", "WR", "K"])                                # the open slots once QB, FLEX and DEF are locked
    assert t["lineup_value"] == pytest.approx(20.0 + 11.0 + 0.0 + rest.total) == 62.0
    assert (t["n_locked"], t["slots_filled"], t["empty_slots"], t["weakest_slot"]) == (3, 6, None, "K")   # RB 14-6 ties K 8: lower value
    # before the kickoff nothing is locked: Warren (16) starts at RB, Pickens at WR, Cook at FLEX
    rows, totals, _ = build(_no_list_inputs(), as_of=datetime(2026, 9, 10, 12, 0, tzinfo=UTC))
    r = {x["sleeper_player_id"]: x for x in rows if x["sleeper_player_id"]}
    assert (r["rp"]["slot"], r["w"]["slot"], r["rb"]["slot"], totals[0]["n_locked"]) == ("RB", "WR", "FLEX", 0)
    assert totals[0]["lineup_value"] == 20 + 16 + 11 + 14 + 8 + 0


def test_build_prefers_the_weekly_list_to_todays_starters():
    rows, totals, _ = build(_no_list_inputs(weekly=True), as_of=datetime(2026, 9, 11, 12, 0, tzinfo=UTC))
    r = {x["sleeper_player_id"]: x for x in rows if x["sleeper_player_id"]}
    assert (r["rp"]["slot"], r["rp"]["is_locked"]) == ("FLEX", True)    # the list's FLEX, not the array's
    assert (r["w"]["role"], r["w"]["reason"]) == ("unplayable", "game started (bench)")


# ------------------------------------------------------------------------------ DDL copies agree
def _ddl_columns(text: str, table: str) -> list[str]:
    body = re.search(rf"create table if not exists ops\.{table} \((.*?)\)\s*(;|\"|,|$)", text, re.S).group(1)
    return [part.split()[0] for part in body.replace("\n", " ").split(",")]


@pytest.mark.parametrize(("table", "columns"), [("lineups", lineup.LINEUP_COLUMNS), ("lineup_totals", lineup.TOTALS_COLUMNS)])
def test_lineup_ddl_is_the_same_everywhere(table, columns):
    """Migration, the writer's DDL dict and the dbt view's pre_hook must agree with the writer's columns."""
    cols = _ddl_columns(db.OPS_DDL, table)
    assert cols == _ddl_columns(lineup.DDL[f"ops.{table}"], table)
    assert cols == _ddl_columns((ROOT / "dbt/models/marts/edge/mart_lineup_recommendation.sql").read_text(), table)
    assert cols == columns
