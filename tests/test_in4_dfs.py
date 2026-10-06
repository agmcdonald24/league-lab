"""IN-4 (Wave I-N): DFS without the homework — the published-slate names, the context signals (role trend, the betting
line, the weather flag, the corner call through IN-3's interface), each signal's "in the projection" label against the
model's own input list, "Worth a look", and the optimiser's stacks and exposure. No database: ``league_lab.dfs`` is
pure."""

from __future__ import annotations

import itertools

import pandas as pd
import pytest

from league_lab import dfs as D
from league_lab.projections import FEATURES_BY_POSITION


# ------------------------------------------------------------------------------------------------ published slate names
@pytest.mark.parametrize("name,expect", [
    ("2026-w05-dk.csv", {"id": "2026-w05-dk-main", "season": 2026, "week": 5, "site": "dk", "label": "main"}),
    ("2026-w05-fd-main.csv", {"id": "2026-w05-fd-main", "season": 2026, "week": 5, "site": "fd", "label": "main"}),
    ("2026-w12-dk-showdown.csv", {"id": "2026-w12-dk-showdown", "season": 2026, "week": 12, "site": "dk",
                                  "label": "showdown"}),
])
def test_slate_names(name, expect):
    assert D.slate_name(name) == expect
    assert D.slate_id_ok(expect["id"])


@pytest.mark.parametrize("name", ["DKSalaries.csv", "2026-w5-dk.csv", "2026-w05-yahoo.csv", "2026-w05-dk-Main.csv",
                                  "2026-w05-dk-main.CSV", "2026-w00-dk.csv", "2026-w23-dk.csv", "../2026-w05-dk.csv",
                                  "2026-w05-dk-a_b.csv", "2026-w05-dk.csv.bak", "", "2026-w05-dk-" + "x" * 21 + ".csv"])
def test_other_names_are_not_slates(name):
    assert D.slate_name(name) is None


@pytest.mark.parametrize("sid", ["../../etc/passwd", "2026-w05-dk", "2026-w05-dk-main/../x", "2026-w05-dk-main.csv",
                                 "2026-w05-dk-MAIN", "2026-w05-dk-main\x00", "%2e%2e", "", None, "2026-w05-dk-" + "a" * 30])
def test_hostile_ids_are_refused(sid):
    assert not D.slate_id_ok(sid)


# ------------------------------------------------------------------------------------------------ role trend
def _games(rows: list[tuple[int, int, int, int, int]]) -> pd.DataFrame:
    """(week, targets, team_targets, offense_snaps, team_snaps) per game."""
    return pd.DataFrame([{"week": w, "targets": t, "team_targets": tt, "carries": 0, "team_carries": 25,
                          "offense_snaps": s, "team_snaps": ts, "routes": None,
                          "team_dropbacks_with_participation": None} for w, t, tt, s, ts in rows])


def test_role_up_summed_numerators_over_summed_denominators():
    g = _games([(1, 4, 40, 40, 65), (2, 5, 35, 42, 66), (3, 9, 36, 60, 64), (4, 10, 34, 62, 66)])
    r = D.role_trend(g, "WR")
    assert r["trend"] == "up" and r["tone"] == "favorable" and r["signal"] == "role"
    ts = next(m for m in r["measures"] if m["measure"] == "target_share")
    assert ts["recent"] == pytest.approx(19 / 70, abs=1e-3) and ts["before"] == pytest.approx(9 / 75, abs=1e-3)
    assert r["words"].startswith("Role up in his last two games (the 2 before in brackets): 27% of the targets (12%)")
    assert r["games"] == [2, 2]


def test_role_down():
    g = _games([(1, 10, 35, 60, 64), (2, 9, 36, 61, 65), (3, 4, 38, 44, 66), (4, 3, 34, 40, 64)])
    r = D.role_trend(g, "TE")
    assert r["trend"] == "down" and r["tone"] == "difficult" and r["words"].startswith("Role down")


def test_role_too_small_a_sample_says_nothing():
    assert D.role_trend(_games([(1, 2, 35, 30, 64), (2, 9, 36, 60, 65), (3, 10, 34, 62, 66)]), "WR") is None
    assert D.role_trend(_games([(3, 9, 36, 60, 64), (4, 10, 34, 62, 66)]), "WR") is None
    assert D.role_trend(_games([]), "WR") is None
    assert D.role_trend(_games([(1, 4, 40, 40, 65), (2, 5, 35, 42, 66), (3, 9, 36, 60, 64), (4, 10, 34, 62, 66)]),
                        "QB") is None


def test_role_flat_or_mixed_says_nothing():
    flat = _games([(1, 7, 35, 50, 64), (2, 7, 36, 50, 65), (3, 7, 34, 51, 66), (4, 7, 35, 50, 64)])
    assert D.role_trend(flat, "WR") is None
    # targets up, snaps down: mixed, nothing said
    mixed = _games([(1, 4, 40, 60, 65), (2, 5, 35, 62, 66), (3, 9, 36, 40, 64), (4, 10, 34, 42, 66)])
    assert D.role_trend(mixed, "WR") is None


def test_role_unknown_measure_is_not_zero():
    g = _games([(1, 4, 40, 40, 65), (2, 5, 35, 42, 66), (3, 9, 36, None, None), (4, 10, 34, 62, 66)])
    r = D.role_trend(g, "WR")
    assert r is not None and {m["measure"] for m in r["measures"]} == {"target_share"}   # snaps unknown: not used


# ------------------------------------------------------------------------------------------------ in the projection?
@pytest.mark.parametrize("signal", sorted(D.SIGNAL_INPUTS))
@pytest.mark.parametrize("position", ["QB", "RB", "WR", "TE"])
def test_each_label_is_read_from_the_models_input_list(signal, position):
    want = bool(set(D.SIGNAL_INPUTS[signal]) & set(FEATURES_BY_POSITION[position]))
    assert D.in_projection(signal, position) is want
    assert D.projection_table()[signal][position] is want


def test_what_the_projection_holds_today():
    # the defense rank, the role shares and the betting line are model inputs; the corner call, routes per dropback
    # and the weather are not (projections.FEATURES_BY_POSITION, v3.3)
    t = D.projection_table()
    assert all(t["defense"].values()) and all(t["role"].values()) and all(t["game"].values())
    assert not any(t["corner"].values()) and not any(t["routes"].values()) and not any(t["weather"].values())
    assert "opp_rank_std" in FEATURES_BY_POSITION["WR"] and "implied_team_total" in FEATURES_BY_POSITION["RB"]
    assert "route_participation_l3" not in FEATURES_BY_POSITION["WR"]


# ------------------------------------------------------------------------------------------------ game, weather
def test_game_environment_matches_the_marts_formula():
    home = D.game_environment("BUF", 47.5, 2.5, True)       # nflverse: spread_line > 0 = the home team favoured
    away = D.game_environment("MIA", 47.5, 2.5, False)
    assert home["implied"] == 25.0 and away["implied"] == 22.5
    assert home["words"] == "Over/under 47.5, BUF favoured by 2.5: Vegas expects BUF to score 25.0."
    assert away["words"] == "Over/under 47.5, MIA underdogs by 2.5: Vegas expects MIA to score 22.5."
    assert D.game_environment("DET", 54.5, 5.5, True)["tone"] == "favorable"          # 30.0 >= 26
    assert D.game_environment("TEN", 39.5, -6.5, True)["tone"] == "difficult"         # 16.5 <= 18
    assert D.game_environment("NYG", 43.5, 3.0, False)["tone"] == "neutral"
    assert D.game_environment("NYG", None, 3.0, False) is None


def test_weather_flag():
    assert D.weather_flag("dome", 1, 0, 0, 0, 0, "WR") is None
    assert D.weather_flag("none", 0, 25, 0, 50, 0, "WR") is None                     # no forecast loaded
    assert D.weather_flag("forecast", 0, 8, 0.0, 62, 0, "WR") is None                # nothing unusual
    w = D.weather_flag("forecast", 0, 20.3, 0.0, 78.9, 0, "WR")
    assert w == {"tone": "difficult", "words": "Forecast at kickoff (outdoors): wind 20 mph."}
    assert D.weather_flag("forecast", 0, 20.3, 0.0, 78.9, 0, "RB")["tone"] is None
    assert "snow" in D.weather_flag("forecast", 0, 5, 0.3, 28, 1, "QB")["words"]


# ------------------------------------------------------------------------------------------------ signals, Worth a look
def _mc(cb_tone="favorable", certainty="likely", d_tone="favorable", shutdown=False):
    return {"opponent": "KC", "home": True,
            "defense": {"tone": d_tone, "tough_rank": 28, "n_ranked": 32, "words": "KC give up the 5th-most points to receivers."},
            "cb": {"tone": cb_tone, "certainty": certainty, "corner": "J. Doe", "corner_rank": 70, "shutdown": shutdown,
                   "words": "Likely lined up against J. Doe, 70th of 80 corners."},
            "tone": "favorable", "words": "A soft matchup."}


ROLE_UP = {"trend": "up", "tone": "favorable", "words": "Role up …", "signal": "role"}


def test_signals_carry_their_projection_label():
    sig = D.signals("WR", _mc(), ROLE_UP, D.game_environment("KC", 50.5, 3.5, True), None)
    by = {s["signal"]: s for s in sig}
    assert by["defense"]["in_projection"] and by["defense"]["projection_words"] == "In the projection"
    assert not by["corner"]["in_projection"] and by["corner"]["projection_words"] == "Not in the projection"
    assert by["role"]["in_projection"] and by["game"]["in_projection"]
    ok, why = D.worth(sig)
    assert ok and why[0].endswith("(not in the projection)") and len(why) == 4


def test_an_unclear_corner_never_counts_and_a_shutdown_corner_rules_out():
    sig = D.signals("WR", _mc(certainty="unclear"), ROLE_UP, None, None)
    assert next(s for s in sig if s["signal"] == "corner")["tone"] is None
    assert D.worth(sig) == (False, [])
    shut = D.signals("WR", _mc(cb_tone="difficult", shutdown=True), ROLE_UP, None, None)
    corner = next(s for s in shut if s["signal"] == "corner")
    assert corner["shutdown"] and corner["tone"] == "difficult"
    assert D.worth(shut)[0] is False


def test_no_matchup_module_no_worth_a_look():
    # everything else is an input of the projection: without the corner call nothing is outside it
    sig = D.signals("WR", None, ROLE_UP, D.game_environment("KC", 50.5, 3.5, True), None)
    assert all(s["in_projection"] for s in sig) and D.worth(sig)[0] is False


def test_the_corner_is_for_receivers_only():
    sig = D.signals("TE", _mc(), ROLE_UP, None, None)
    assert {s["signal"] for s in sig} == {"defense", "role"}


def test_worth_a_look_order_and_who_can_play():
    rows = [{"key": "a", "position": "WR", "worth": True, "proj": 10.0, "pts_per_k": 3.1, "out": False},
            {"key": "b", "position": "WR", "worth": True, "proj": 14.0, "pts_per_k": 2.2, "out": False},
            {"key": "c", "position": "WR", "worth": True, "proj": 20.0, "pts_per_k": 3.5, "out": True},
            {"key": "d", "position": "WR", "worth": False, "proj": 30.0, "pts_per_k": 4.0, "out": False},
            {"key": "e", "position": "TE", "worth": True, "proj": 8.0, "pts_per_k": None, "out": False}]
    assert D.worth_a_look(rows) == {"WR": ["b", "a"], "TE": ["e"]}
    assert D.worth_a_look(rows, by="pts_per_k") == {"WR": ["a", "b"], "TE": ["e"]}


# ------------------------------------------------------------------------------------------------ stacks and exposure
def _stack_slate() -> list[dict]:
    """Two games, BUF@MIA and CHI@JAX: each team a QB, two WRs, a TE, two RBs, a defense; salaries roomy."""
    ps = []
    proj = {"QB": 20.0, "WR": 12.0, "TE": 8.0, "RB": 11.0, "DEF": 7.0}
    games = {"BUF": ("MIA", "BUF@MIA"), "MIA": ("BUF", "BUF@MIA"), "CHI": ("JAX", "CHI@JAX"), "JAX": ("CHI", "CHI@JAX")}
    for t, (opp, game) in games.items():
        bump = {"BUF": 3.0, "MIA": 0.0, "CHI": 1.0, "JAX": -1.0}[t]
        for pos, k in (("QB", 1), ("WR", 2), ("TE", 1), ("RB", 2), ("DEF", 1)):
            for j in range(k):
                v = proj[pos] + bump - j * 1.5
                ps.append({"key": f"{t}-{pos}{j}", "position": pos, "team": t, "opponent": opp, "game": game,
                           "salary": 5000, "proj": round(v, 2), "p10": round(v * 0.4, 2), "p90": round(v * 1.7, 2),
                           "out": False})
    return ps


def _lineup_players(lu: dict, ps: list[dict]) -> list[dict]:
    by = {p["key"]: p for p in ps}
    return [by[s["key"]] for s in lu["slots"]]


@pytest.mark.parametrize("with_qb", [1, 2])
def test_qb_stack(with_qb):
    ps = _stack_slate()
    res = D.solve_lineups(ps, "dk_classic", n=3, stack=D.Stack(with_qb=with_qb))
    assert len(res.lineups) == 3
    for lu in res.lineups:
        lp = _lineup_players(lu, ps)
        qb = next(p for p in lp if p["position"] == "QB")
        mates = [p for p in lp if p["position"] in ("WR", "TE") and p["team"] == qb["team"]]
        assert len(mates) >= with_qb
    assert any(n.startswith("Stacks: every lineup has the quarterback with at least") for n in res.notes)


def test_bring_back_and_no_defense_against_the_qb():
    ps = _stack_slate()
    # without the rule the best lineup takes the BUF defense... against nobody; force the conflict: MIA's QB is best
    for p in ps:
        if p["key"] == "MIA-QB0":
            p["proj"] = 40.0
        if p["key"] == "BUF-DEF0":
            p["proj"] = 30.0
    free = D.solve_lineups(ps, "dk_classic", n=1).lineups[0]
    lp = _lineup_players(free, ps)
    assert {"MIA-QB0", "BUF-DEF0"} <= {p["key"] for p in lp}          # the conflict happens unconstrained
    res = D.solve_lineups(ps, "dk_classic", n=2, stack=D.Stack(with_qb=1, bring_back=True, no_def_vs_qb=True))
    for lu in res.lineups:
        lp = _lineup_players(lu, ps)
        qb = next(p for p in lp if p["position"] == "QB")
        assert any(p["position"] in ("RB", "WR", "TE") and p["team"] == qb["opponent"] for p in lp)
        assert not any(p["position"] == "DEF" and p["opponent"] == qb["team"] for p in lp)
    # the rule never changed what is maximised: the stacked lineup is the best one among lineups meeting the rules
    assert res.lineups[0]["proj"] <= free["proj"]


def test_an_impossible_stack_names_its_rule():
    # each team keeps ONE pass catcher: "QB + 2 pass catchers" cannot be met; the slate itself still can
    keep = {"BUF-WR0", "MIA-WR0", "CHI-WR0", "JAX-TE0"}
    ps = [p for p in _stack_slate() if p["position"] not in ("WR", "TE") or p["key"] in keep]
    assert D.solve_lineups(ps, "dk_classic", n=1).lineups
    res = D.solve_lineups(ps, "dk_classic", n=1, stack=D.Stack(with_qb=2, no_def_vs_qb=True))
    assert res.lineups == []
    assert res.notes[-1] == ("No lineup can meet the quarterback with at least 2 of his own pass catchers (WR or TE) on "
                             "this slate with these players set to always in and left out. Turn that rule off or change "
                             "who is in.")


def test_stacks_do_not_apply_to_showdown():
    ps = [{**p, "cpt_salary": 7500} for p in _stack_slate() if p["game"] == "BUF@MIA"]
    res = D.solve_lineups(ps, "dk_showdown", n=1, stack=D.Stack(with_qb=1))
    assert res.lineups and res.notes[0].startswith("Stacks apply to classic and full-roster contests")


@pytest.mark.parametrize("share,n,cap", [(0.34, 3, 1), (0.5, 4, 2), (0.6, 5, 3)])
def test_max_exposure(share, n, cap):
    ps = _stack_slate() + [{**p, "key": p["key"] + "b", "proj": round(p["proj"] - 0.7, 2)} for p in _stack_slate()]
    res = D.solve_lineups(ps, "dk_classic", n=n, max_exposure=share)
    assert len(res.lineups) == n
    counts: dict[str, int] = {}
    for lu in res.lineups:
        for s in lu["slots"]:
            counts[s["key"]] = counts.get(s["key"], 0) + 1
    assert max(counts.values()) <= cap
    assert f"Exposure: each player in at most {cap} of the {n} lineups." in res.notes


def test_exposure_exempts_a_player_set_always_in():
    ps = _stack_slate() + [{**p, "key": p["key"] + "b", "proj": round(p["proj"] - 0.7, 2)} for p in _stack_slate()]
    res = D.solve_lineups(ps, "dk_classic", n=3, max_exposure=0.34, locks=["JAX-TE0"])
    assert all("JAX-TE0" in {s["key"] for s in lu["slots"]} for lu in res.lineups)


def test_lineups_stay_distinct_and_ordered_with_rules():
    ps = _stack_slate()
    res = D.solve_lineups(ps, "dk_classic", n=4, stack=D.Stack(with_qb=1, bring_back=True))
    sets = [frozenset(s["key"] for s in lu["slots"]) for lu in res.lineups]
    assert len(set(sets)) == len(sets)
    totals = [lu["proj"] for lu in res.lineups]
    assert totals == sorted(totals, reverse=True)
    for a, b in itertools.combinations(sets, 2):
        assert a != b
