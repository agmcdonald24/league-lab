"""IF-1 (Wave I-F, the decision-quality review § "value the bench before prescribing drops"): the drop's cost in pieces,
the cheapest drop per claim, the net gain, "no worthwhile move" — on synthetic rosters (no database)."""

from __future__ import annotations

import pytest

from league_lab import waivers as W
from league_lab.lineup import Player, solve

SLOTS = ["QB", "RB", "WR", "TE", "FLEX", "K", "BN", "BN", "BN"]


def P(pid: str, pos: str, value: float | None, **kw) -> Player:
    return Player(id=pid, position=pos, value=value, value_source="proj_points", **kw)


def _rows(players: list[Player], week: int) -> list[dict]:
    lu = solve(players, SLOTS, margins=False)
    slot = {s.player.id: s.slot for s in lu.starts if s.player is not None}
    return [{"sleeper_player_id": p.id, "gsis_id": f"g-{p.id}", "player_name": p.id.upper(), "position": p.position,
             "value": p.value, "role": "starter" if p.id in slot else ("bench" if p.playable else "unplayable"),
             "slot": slot[p.id].label if p.id in slot else None, "slot_type": slot[p.id].type if p.id in slot else None,
             "is_locked": False, "value_source": "proj_points", "reason": None if p.playable else "bye",
             "report_status": None, "week": week} for p in players]


def sweep(roster: list[Player], fas: dict[str, tuple[str, float]], *, market: dict, replacement: dict | None,
          post: list[list[Player]] | None = None, open_spot: bool = False) -> list[dict]:
    """One roster through ``sweep_roster`` (the nightly's and the on-demand path's per-roster step)."""
    weeks = [roster] * 4
    week_rows = [_rows(ps, 4 + h) for h, ps in enumerate(weeks)]
    rest = [r for wr in week_rows for r in wr] + [r for i, ps in enumerate(post or []) for r in _rows(ps, 8 + i)]
    adds = {a: [P(a, pos, v)] * 4 for a, (pos, v) in fas.items()}
    fa_meta = {a: {"gsis_id": f"g-{a}", "player_name": a.upper(), "position": pos, "games_played": 3, "_row": {}}
               for a, (pos, _) in fas.items()}
    cur = [{"sleeper_player_id": p.id} for p in roster][: (8 if open_spot else 9)]
    key = {"league_id": "L", "season": 2026, "week": 4, "roster_id": 1, "horizon_last_week": 7, "horizon_weeks": 4}
    return W.sweep_roster(SLOTS, week_rows, cur, adds, fa_meta, rest, 4 + len(post or []),
                          lambda sid: 15 * fas[sid][1], key, {}, market=market, replacement=replacement)


def roster(k_value: float = 6.0, wr_bench: float = 9.0) -> list[Player]:
    return [P("qb", "QB", 18), P("rb", "RB", 12), P("wr", "WR", 14), P("te", "TE", 8), P("wr2", "WR", 11),
            P("k", "K", k_value), P("wrb", "WR", wr_bench), P("rbb", "RB", 5), P("teb", "TE", 4)]


# ------------------------------------------------------------------------------ DropCost
def test_the_cost_is_the_most_of_the_pieces_never_their_sum():
    dc = W.drop_cost(2.0, depth=1.5, future=3.0, future_weeks=2, season=8.0, upside=None)
    assert dc.cost == 8.0 and dc.piece == "season_value"
    assert W.drop_cost(2.0).cost == 2.0 and W.drop_cost(2.0).piece == "lineup_loss"
    assert W.drop_cost(0.0, season=0.0).piece is None and W.drop_cost(0.0, season=0.0).cost == 0.0
    # never 0 for a player above replacement: the season value alone sets it
    assert W.drop_cost(0.0, season=W.season_value(140.0, 100.0)).cost == 40.0
    assert W.season_value(None, 100.0) is None                      # unknown, not 0
    assert W.season_value(90.0, 100.0) == 0.0


def test_depth_counts_the_weeks_he_sits_above_the_wire_times_the_miss_chance():
    d = W.depth_lost([9.0, 9.0, None, 9.0], [7.0, 10.0, 7.0, 7.0], [True, True, True, False], "WR", [3, 3, 3, 3])
    assert d == pytest.approx(2.0 * W.cover_chance("WR", 3))
    assert W.cover_chance("DEF", 1) == 0.0 and W.cover_chance("RB", 2) == pytest.approx(1 - (1 - 0.12) ** 2)


# ------------------------------------------------------------------------------ the review's case, synthetic
def test_a_kicker_claim_drops_the_kicker_it_replaces_not_a_bench_wr_above_replacement():
    """Carlson for McPherson: the K claim's best drop is the displaced K; the bench WR (40 season points above the
    best free-agent WR) is the alternative and costs more."""
    rows = sweep(roster(), {"kfa": ("K", 8.0), "wrfa": ("WR", 6.0)},
                 market={"g-wrb": 140.0, "g-k": 90.0, "g-rbb": 70.0, "g-teb": 50.0}, replacement={"WR": 100.0, "K": 120.0, "RB": 90.0, "TE": 80.0})
    k = [r for r in rows if r["add_sleeper_id"] == "kfa"]
    best = next(r for r in k if r["is_best_drop"])
    assert best["drop_sleeper_id"] == "k" and best["drop_is_incumbent"] and best["drop_cost"] == 0.0
    wrb = next(r for r in k if r["drop_sleeper_id"] == "wrb")
    assert wrb["drop_season_value"] == 40.0 and wrb["drop_cost"] == 40.0 and wrb["drop_cost_piece"] == "season_value"
    assert wrb["net_horizon_gain"] < 0 < best["net_horizon_gain"] and not wrb["is_worthwhile"]
    assert best["net_horizon_gain"] == best["horizon_gain"] == pytest.approx(8.0)        # (8 − 6) × 4 weeks


def test_equal_costs_prefer_the_starter_the_claim_replaces():
    """Every drop free (all below replacement): the K claim still drops the K, not the bench player with the fewest
    points — B3's old tie-break ('the least useful player') was the review's bug."""
    rows = sweep(roster(wr_bench=3.0), {"kfa": ("K", 8.0), "wrfa": ("WR", 10.0), "rbfa": ("RB", 6.0), "tefa": ("TE", 5.0)},
                 market={"g-wrb": 20.0, "g-k": 90.0, "g-rbb": 30.0, "g-teb": 10.0},
                 replacement={"WR": 100.0, "K": 120.0, "RB": 90.0, "TE": 80.0})
    best = next(r for r in rows if r["add_sleeper_id"] == "kfa" and r["is_best_drop"])
    assert best["drop_sleeper_id"] == "k"
    assert {r["drop_cost"] for r in rows if r["add_sleeper_id"] == "kfa"} == {0.0}


def test_one_qb_and_superflex_value_the_qb3_differently():
    """QB3 projecting 220 season points: on a 1-QB wire a 230-point QB is free (his season value 0); on a superflex
    wire the best free QB has 120 (his season value 100)."""
    roster3 = [P("qb", "QB", 18), P("rb", "RB", 12), P("wr", "WR", 14), P("te", "TE", 8), P("wr2", "WR", 11),
               P("k", "K", 6), P("qb2", "QB", 15), P("qb3", "QB", 14), P("teb", "TE", 4)]
    one_qb = W.drop_pieces(SLOTS, [roster3] * 4, [], {"fq": [P("fq", "QB", 15.3)] * 4}, {"fq": {"position": "QB"}},
                           {"qb3": {"position": "QB", "gsis_id": "g3"}}, {}, {"qb3"}, 7, 15, lambda sid: 230.0,
                           market={"g3": 220.0}, replacement=None)
    sflex = W.drop_pieces(SLOTS, [roster3] * 4, [], {"fq": [P("fq", "QB", 8.0)] * 4}, {"fq": {"position": "QB"}},
                          {"qb3": {"position": "QB", "gsis_id": "g3"}}, {}, {"qb3"}, 7, 15, lambda sid: 120.0,
                          market={"g3": 220.0}, replacement=None)
    assert one_qb["qb3"]["drop_season_value"] == 0.0 and one_qb["qb3"]["drop_replacement_points"] == 230.0
    assert sflex["qb3"]["drop_season_value"] == 100.0
    # and his depth: he beats the superflex wire's QB every week he sits; not the 1-QB wire's
    assert sflex["qb3"]["drop_depth_lost"] > 0 == one_qb["qb3"]["drop_depth_lost"]


def test_later_starts_count_above_the_wire_only():
    """After the horizon the bench WR starts once (a starter's bye): 9 against the wire's 30/(6−1) = 6-point WR costs 3;
    a K who starts every later week below the best free K (120/5 = 24 per week) costs nothing (the wire covers him)."""
    bye = [p for p in roster() if p.id != "wr"] + [P("wr", "WR", None, playable=False, reason="bye")]
    rows = sweep(roster(), {"kfa": ("K", 8.0)}, market={"g-wrb": 99.0, "g-k": 90.0, "g-rbb": 30.0, "g-teb": 10.0},
                 replacement={"WR": 30.0, "K": 120.0, "RB": 90.0, "TE": 80.0}, post=[bye, roster()])
    wrb = next(r for r in rows if r["drop_sleeper_id"] == "wrb")
    k = next(r for r in rows if r["drop_sleeper_id"] == "k")
    assert wrb["drop_future_start_weeks"] == 1 and wrb["drop_future_starts"] == pytest.approx(3.0)
    assert k["drop_future_start_weeks"] == 2 and k["drop_future_starts"] == 0.0


def test_no_worthwhile_move_when_the_net_gain_is_small():
    """A +0.5 per week claim (2.0 over the horizon) that must drop someone: not worth a roster spot (under 1 this week,
    under 3 over the horizon); the rows say so."""
    rows = sweep(roster(k_value=7.5), {"kfa": ("K", 8.0)}, market={"g-wrb": 99.0, "g-k": 90.0, "g-rbb": 30.0, "g-teb": 10.0},
                 replacement={"WR": 100.0, "K": 120.0, "RB": 90.0, "TE": 80.0})
    best = next(r for r in rows if r["add_sleeper_id"] == "kfa" and r["is_best_drop"])
    assert best["net_weekly_gain"] == pytest.approx(0.5) and best["net_horizon_gain"] == pytest.approx(2.0)
    assert best["is_worthwhile"] is False


def test_choose_drops_reads_the_pieces_from_old_rows():
    """The API's read of a mart built before the cost columns: the season value alone re-ranks the rows."""
    base = {"list_kind": "start_now", "add_sleeper_id": "a", "weekly_gain": 1.6, "horizon_gain": 13.5, "add_horizon_gain": 13.5,
            "week_gains": [1.6, 1.0, 8.4, 2.5]}
    rows = [{**base, "drop_sleeper_id": "wr", "displaced_sleeper_id": "k", "drop_ros_points": 79.0, "drop_season_value": 38.0},
            {**base, "drop_sleeper_id": "k", "displaced_sleeper_id": "k", "drop_ros_points": 104.5, "drop_season_value": 0.0}]
    out = W.choose_drops(rows)
    best = next(r for r in out if r["is_best_drop"])
    assert best["drop_sleeper_id"] == "k" and best["add_rank"] == 1 and best["drop_is_incumbent"]
    wr = next(r for r in out if r["drop_sleeper_id"] == "wr")
    assert wr["net_horizon_gain"] == pytest.approx(13.5 - 38.0) and wr["move_rank"] == 2
    assert W.choose_drops([{"list_kind": "nothing"}]) == [{"list_kind": "nothing"}]
