"""R-10 role alerts and R-12 scenario upside on fixtures (no database): the alert rule (step change,
one-game blip, blowout, teammate out / back, trade, return from injury, games held), the scenario's
input moves, the upside stash on a synthetic roster, and the DDL copies in the views."""

import re
from pathlib import Path

import pandas as pd
import pytest

from league_lab import signals, waivers
from league_lab.lineup import Player
from league_lab.signals import Game, alerts_for_season, larger_role_row, window_inputs

ROOT = Path(__file__).resolve().parents[1]


def G(pid: str, week: int, snap: float | None, *, pos: str = "WR", team: str = "AAA", status: str = "played",
      tgt: float = 0, team_tgt: float = 35, car: float = 0, team_car: float = 25, route: float | None = None,
      margin: float = 3, name: str | None = None) -> Game:
    return Game(gsis_id=pid, season=2025, week=week, team=team, position=pos, player_name=name or pid.upper(),
                status=status, snap_share=snap, route_share=route, targets=tgt, team_targets=team_tgt, carries=car,
                team_carries=team_car, team_margin=margin, game_id=f"2025_{week:02d}_{team}")


def starter(pid: str, weeks: range, pos: str = "WR", team: str = "AAA", out: tuple = (), snap: float = 0.85) -> list[Game]:
    """A teammate who starts every week, except the weeks in ``out`` (injured)."""
    return [G(pid, w, 0.0 if w in out else snap, pos=pos, team=team, status="out_injured" if w in out else "played",
              tgt=0 if w in out else 8) for w in weeks]


def alerts(games: list[Game], prev: dict | None = None, reports: dict | None = None) -> dict:
    return {(a.game.gsis_id, a.game.week): a for a in alerts_for_season(games, prev or {}, reports or {})}


# ------------------------------------------------------------------------------ the alert rule
def test_step_change_in_snaps_fires_in_the_first_week_it_shows():
    """A WR3 on 40% of the snaps for five games, then 78%: an alert in that game (one game), then two and
    three games; from the fourth game on it is his role, not news."""
    snaps = [0.40, 0.38, 0.42, 0.41, 0.39, 0.78, 0.80, 0.76, 0.79]
    games = [G("wr3", w, s, tgt=3 if s < 0.5 else 6) for w, s in enumerate(snaps, 1)]
    got = alerts(games)
    a6 = got[("wr3", 6)]
    assert (a6.direction, a6.k, a6.since_week, a6.trigger) == ("up", 1, 6, None)
    assert signals.change_text(a6).startswith("snap share 40% → 78%")
    assert (got[("wr3", 7)].k, got[("wr3", 7)].since_week) == (2, 6)
    assert (got[("wr3", 8)].k, got[("wr3", 8)].since_week) == (3, 6)
    assert ("wr3", 9) not in got                                   # held four games: the change is his role now
    assert all(w >= 6 for (_, w) in got)                           # nothing before the change


def test_one_week_target_blip_is_not_an_alert():
    """Same snaps, one game with 40% of the targets: target share alone for one game is noise."""
    tg = [5, 6, 5, 6, 5, 14, 5, 6]
    games = [G("wr", w, 0.85, tgt=t) for w, t in enumerate(tg, 1)]
    assert alerts(games) == {}


def test_one_game_snap_jump_in_a_blowout_is_garbage_time():
    snaps = [0.30, 0.28, 0.33, 0.31, 0.75, 0.30]
    games = [G("rb2", w, s, pos="RB", margin=28 if w == 5 else 3) for w, s in enumerate(snaps, 1)]
    assert alerts(games) == {}
    # the same jump in a close game is an alert
    games = [G("rb2", w, s, pos="RB", margin=3) for w, s in enumerate(snaps, 1)]
    assert ("rb2", 5) in alerts(games)


def test_small_change_is_not_an_alert():
    """+12 points of snaps is below the practical minimum (20)."""
    snaps = [0.60, 0.62, 0.58, 0.61, 0.73, 0.74, 0.72]
    assert alerts([G("wr", w, s) for w, s in enumerate(snaps, 1)]) == {}


def test_teammate_out_names_the_trigger_and_lets_carry_share_count_in_one_game():
    """RB1 (70% of the snaps) is out in week 5; RB2's carry share goes 30% -> 68% on a modest snap rise.
    Carry share alone would need two games; the named reason makes one game enough."""
    weeks = range(1, 8)
    rb1 = starter("rb1", weeks, pos="RB", out=(5, 6), snap=0.70)
    rb2 = [G("rb2", w, 0.42 if w < 5 else 0.55, pos="RB", car=7.5 if w < 5 else 17, name="Backup Back") for w in weeks]
    got = alerts(rb1 + rb2)
    a = got[("rb2", 5)]
    assert (a.direction, a.k, a.trigger.kind, a.trigger.text()) == ("up", 1, "teammate_out", "RB1 out")
    assert [c.metric for c in a.changes] == ["carry_share"]
    assert (got[("rb2", 6)].k, got[("rb2", 6)].trigger.text()) == (2, "RB1 out")
    # an absence beneficiary: the cause in words, and an expiry tied to the teammate's return
    assert signals.alert_kind(a.direction, a.trigger) == "absence_beneficiary"
    assert signals.cause_text(a) == "RB1 out injured"
    assert signals.expiry(a) == (8, "ends when RB1 returns, and after week 8 at the latest")
    # RB1 back in week 7: the fill-in's bigger role is not re-reported as a three-game change (it expired)
    assert not any(pid == "rb2" and w == 7 and x.direction == "up" for (pid, w), x in got.items())


def test_teammate_back_ends_the_story_with_a_down_alert():
    """The TE2 who filled in for the injured TE1 loses the snaps the week TE1 returns."""
    weeks = range(1, 9)
    te1 = starter("te1", weeks, pos="TE", out=(2, 3, 4, 5), snap=0.88)
    te2 = [G("te2", w, 0.20 if w == 1 else (0.78 if w <= 5 else 0.10), pos="TE") for w in weeks]
    got = alerts(te1 + te2, prev={"te1": 0.9})
    assert got[("te2", 2)].trigger.text() == "TE1 out"
    down = got[("te2", 6)]
    assert (down.direction, down.k, down.trigger.kind, down.trigger.text()) == ("down", 1, "teammate_back", "TE1 back")
    assert signals.alert_kind(down.direction, down.trigger) == "role_down" and signals.cause_text(down) == "TE1 back"
    # TE1's own return is not a role change (he was hurt, not benched)
    assert not any(pid == "te1" for pid, _ in got)


def test_starter_hurt_in_week_one_counts_as_a_starter_through_last_season():
    """TE1 left week 1 after 25% of the snaps and went on IR: with one prior game, last season's level
    (90%) says he was the starter, so TE2's jump names him."""
    te1 = [G("te1", 1, 0.25, pos="TE")] + [G("te1", w, 0.0, pos="TE", status="out_injured") for w in (2, 3)]
    te2 = [G("te2", 1, 0.40, pos="TE"), G("te2", 2, 0.80, pos="TE"), G("te2", 3, 0.79, pos="TE")]
    got = alerts(te1 + te2, prev={"te1": 0.90})
    assert got[("te2", 2)].trigger.text() == "TE1 out"
    assert alerts(te1 + te2, prev={"te1": 0.30})[("te2", 2)].trigger is None   # a backup last season: no named reason


def test_benching_is_a_depth_move_for_both_quarterbacks():
    """The new starter's jump names the benched one (kind depth_move, the same game); the benched starter's drop
    needs a second game without a named reason (a one-game drop is too often an off day), then names the new one."""
    weeks = range(1, 7)
    qb1 = [G("qb1", w, 0.97 if w < 4 else 0.03, pos="QB", name="Old Starter") for w in weeks]
    qb2 = [G("qb2", w, 0.03 if w < 4 else 0.97, pos="QB", name="New Starter") for w in weeks]
    got = alerts(qb1 + qb2)
    up = got[("qb2", 4)]
    assert up.trigger.text() == "Old Starter benched"
    assert signals.alert_kind(up.direction, up.trigger) == "depth_move"
    assert ("qb1", 4) not in got
    down = got[("qb1", 5)]
    assert (down.direction, down.k, down.since_week, down.trigger.text()) == ("down", 2, 4, "New Starter took over")
    assert signals.alert_kind(down.direction, down.trigger) == "depth_move"


def test_return_from_injury_is_not_a_bigger_role():
    games = [G("wr", 1, 0.30), G("wr", 2, 0.0, status="out_injured"), G("wr", 3, 0.0, status="out_injured"),
             G("wr", 4, 0.85), G("wr", 5, 0.86), G("wr", 6, 0.84)]
    assert not [a for a in alerts(games).values() if a.direction == "up"]


def test_trade_is_the_trigger():
    games = [G("wr", w, 0.92, team="AAA", tgt=8) for w in range(1, 6)] + [G("wr", w, 0.45, team="BBB", tgt=3) for w in (6, 7)]
    got = alerts(games)
    a = got[("wr", 6)]
    assert (a.direction, a.trigger.kind, a.trigger.text()) == ("down", "traded", "traded to BBB")
    assert signals.alert_kind(a.direction, a.trigger) == "new_team"


def test_route_share_is_structural_and_unknown_is_not_zero():
    """Routes move in one game like snaps; a season without participation data (route None) never fires on routes."""
    base = dict(pos="TE")
    games = [G("te", w, 0.70, route=0.45, **base) for w in range(1, 5)] + [G("te", 5, 0.75, route=0.90, **base)]
    a = alerts(games)[("te", 5)]
    assert [c.metric for c in a.changes] == ["route_share"]
    games = [G("te", w, 0.70, route=None, **base) for w in range(1, 6)]
    assert alerts(games) == {}


def test_target_share_alone_is_not_an_alert_for_a_receiver():
    """ra1.1: two games of a bigger target share on the same snaps is supporting evidence, not an alert (2025: 32-42%
    of those held); the same jump with the snaps is one."""
    tg = [3, 3, 4, 3, 3, 11, 12, 11]
    games = [G("wr", w, 0.80, tgt=t) for w, t in enumerate(tg, 1)]
    assert alerts(games) == {}
    snaps = [0.45, 0.44, 0.46, 0.45, 0.44, 0.85, 0.86, 0.84]
    got = alerts([G("wr", w, s, tgt=t) for w, (s, t) in enumerate(zip(snaps, tg, strict=True), 1)])
    assert got[("wr", 6)].direction == "up" and signals.alert_kind("up", got[("wr", 6)].trigger) == "role_up"
    assert signals.cause_text(got[("wr", 6)]) == "no teammate out, no trade: the coaches changed his role"


def test_one_game_drop_without_a_reason_waits_for_the_second_game():
    snaps = [0.85, 0.86, 0.84, 0.85, 0.40, 0.42]
    got = alerts([G("wr", w, s) for w, s in enumerate(snaps, 1)])
    assert ("wr", 5) not in got
    assert (got[("wr", 6)].direction, got[("wr", 6)].k, got[("wr", 6)].since_week) == ("down", 2, 5)


def test_depth_chart_promotion_is_the_named_reason():
    """RB2 (#2 on the depth chart) moves to #1 before week 4 and his snaps jump: kind depth_move, the cause says so,
    and the named reason makes a one-game carry-share change count (as a teammate out would)."""
    rb = [G("rb", w, 0.35 if w < 4 else 0.62, pos="RB", car=6 if w < 4 else 16) for w in range(1, 6)]
    depth = {("AAA", w): {"rb": 2 if w < 4 else 1} for w in range(1, 6)}
    got = {(a.game.gsis_id, a.game.week): a for a in alerts_for_season(rb, {}, {}, depth)}
    a = got[("rb", 4)]
    assert (a.direction, a.trigger.kind, a.trigger.text()) == ("up", "depth_up", "up to RB1 on the depth chart")
    assert signals.alert_kind(a.direction, a.trigger) == "depth_move"
    # without depth charts (seasons before 2025) the same change needs a second game and is a plain bigger role
    got = alerts(rb)
    assert ("rb", 4) not in got
    b = got[("rb", 5)]
    assert (b.k, b.since_week, b.trigger) == (2, 4, None) and signals.alert_kind(b.direction, b.trigger) == "role_up"


def test_alert_rows_carry_kind_cause_and_expiry():
    snaps = [0.40, 0.38, 0.42, 0.41, 0.39, 0.78]
    df = signals.alert_rows(alerts_for_season([G("wr3", w, s) for w, s in enumerate(snaps, 1)], {}, {}))
    r = df.iloc[0]
    assert list(df.columns) == signals.ALERT_COLUMNS
    assert (r["kind"], r["expires_after_week"], r["games_held"]) == ("role_up", 9, 1)
    assert r["expiry_rule"] == "after week 9 his projection has caught up if the role holds"


def test_alert_outcomes_real_false_expired():
    """Up alert real when the next games keep at least half the change; an absence alert whose teammate is back for
    the next game expired (as designed), not false."""
    weeks = range(1, 10)
    rb1 = starter("rb1", weeks, pos="RB", out=(5,), snap=0.70)
    rb2 = [G("rb2", w, 0.40 if w != 5 else 0.80, pos="RB") for w in weeks]
    wr = [G("wr", w, 0.40 if w < 5 else 0.80) for w in weeks]
    games = rb1 + rb2 + wr
    df = signals.alert_rows(alerts_for_season(games, {}, {}))
    first = df[signals.first_detections(df)]
    res = dict(zip(first["gsis_id"], signals.alert_outcomes(first, games), strict=True))
    assert res == {"rb2": "expired", "wr": "real"}


# ------------------------------------------------------------------------------ scenario upside
def test_window_inputs_follow_the_feature_definitions():
    g = pd.DataFrame({"snap_share": [0.70, 0.80], "targets": [6.0, 8.0], "team_targets": [30.0, 40.0], "carries": [0.0, 1.0],
                      "team_carries": [25.0, 25.0], "receiving_air_yards": [50.0, 70.0], "team_air_yards": [200.0, 200.0],
                      "first_read_targets": [None, None], "team_first_read_targets": [None, None],
                      "red_zone_targets": [1.0, 0.0], "red_zone_carries": [0.0, 0.0], "points_expected": [10.0, 14.0]})
    w = window_inputs(g)
    assert w["snap_pct_l3"] == 0.75 and w["target_share_l3"] == 0.2 and w["carry_share_l3"] == 0.02
    assert w["targets_pg_l3"] == 7.0 and w["xppg_l3"] == 12.0 and w["air_yards_share_l3"] == 0.3
    assert "first_read_share_l3" not in w                          # not charted: left as it is (unknown is not zero)


def test_larger_role_moves_opportunity_and_holds_efficiency():
    """Targets per game 4 -> 8 in the window: catches, yards and touchdowns per game double at his
    last-3 rate; last-3 points move by the priced change of that line (half PPR: 0.5 per catch,
    0.1 per yard, 6 per TD)."""
    base = pd.Series({"snap_pct_l3": 0.5, "target_share_l3": 0.12, "targets_pg_l3": 4.0, "receptions_pg_l3": 3.0,
                      "receiving_yards_pg_l3": 36.0, "receiving_tds_pg_l3": 0.2, "carries_pg_l3": 0.0, "rushing_yards_pg_l3": 0.0,
                      "rushing_tds_pg_l3": 0.0, "targets_pg_std": 4.0, "ppg_l3": 7.3, "xppg_l3": 7.0, "week": 6.0})
    scoring = {"rec": 0.5, "rec_yd": 0.1, "rec_td": 6.0}
    row, moved = larger_role_row(base, {"snap_pct_l3": 0.85, "target_share_l3": 0.24, "targets_pg_l3": 8.0, "xppg_l3": 13.0}, scoring)
    assert row["receptions_pg_l3"] == pytest.approx(6.0) and row["receiving_yards_pg_l3"] == pytest.approx(72.0)
    assert row["receiving_tds_pg_l3"] == pytest.approx(0.4)
    assert row["ppg_l3"] == pytest.approx(7.3 + (3.0 * 0.5 + 36.0 * 0.1 + 0.2 * 6))   # the line doubled
    assert moved["snap_pct_l3"] == [0.5, 0.85] and "week" not in moved and "carries_pg_l3" not in moved
    # the window equal to his last three games: nothing moves, the scenario is the base
    same, moved = larger_role_row(base, {"snap_pct_l3": 0.5, "targets_pg_l3": 4.0, "target_share_l3": 0.12}, scoring)
    assert moved == {} and same.equals(base)


def test_larger_role_caps_inputs_at_the_position_90th_percentile():
    base = pd.Series({"snap_pct_l3": 0.5, "target_share_l3": 0.12, "targets_pg_l3": 4.0, "receptions_pg_l3": 3.0,
                      "receiving_yards_pg_l3": 36.0, "receiving_tds_pg_l3": 0.2, "ppg_l3": 7.3})
    row, _ = larger_role_row(base, {"target_share_l3": 0.45, "targets_pg_l3": 16.0, "snap_pct_l3": 0.95}, {"rec": 0.5},
                             caps={"target_share_l3": 0.28, "targets_pg_l3": 9.5, "snap_pct_l3": 0.97})
    assert row["target_share_l3"] == 0.28 and row["targets_pg_l3"] == 9.5 and row["snap_pct_l3"] == 0.95
    assert row["receptions_pg_l3"] == pytest.approx(3.0 * 9.5 / 4.0)     # volume capped, efficiency held
    # his own level above the cap is kept (never capped below where he already is)
    row, _ = larger_role_row(pd.concat([base.drop("target_share_l3"), pd.Series({"target_share_l3": 0.33})]), {"target_share_l3": 0.40}, {},
                             caps={"target_share_l3": 0.28})
    assert row["target_share_l3"] == 0.33


def test_quarterback_scenario_scales_passing_with_attempts():
    """A backup who started one game: attempts per game (last 3) 12 -> 36 at the window's level, passing yards and
    touchdowns per game scale with them; points move by the priced change (4-pt passing TD, 0.04 per yard)."""
    base = pd.Series({"snap_pct_l3": 0.35, "attempts_pg_l3": 12.0, "passing_yards_pg_l3": 80.0, "passing_tds_pg_l3": 0.5,
                      "passing_interceptions_pg_l3": 0.3, "carries_pg_l3": 1.0, "rushing_yards_pg_l3": 4.0, "rushing_tds_pg_l3": 0.0,
                      "ppg_l3": 5.4})
    row, moved = larger_role_row(base, {"snap_pct_l3": 0.98, "attempts_pg_l3": 36.0, "carries_pg_l3": 1.0}, {"pass_yd": 0.04, "pass_td": 4.0})
    assert row["passing_yards_pg_l3"] == pytest.approx(240.0) and row["passing_tds_pg_l3"] == pytest.approx(1.5)
    assert row["passing_interceptions_pg_l3"] == pytest.approx(0.9)
    assert row["ppg_l3"] == pytest.approx(5.4 + 160 * 0.04 + 1.0 * 4.0)
    assert "rushing_yards_pg_l3" not in moved                          # carries did not move


def test_with_alert_line_is_the_hold_rate_share_of_the_gap():
    assert signals.with_alert(10.0, 14.0, 1) == pytest.approx(10.0 + signals.HOLD_RATE[1] * 4.0)
    assert signals.with_alert(10.0, 14.0, 7) == 10.0                    # no rate: the projection
    label, note = signals.presentation(1)
    assert label == ("with the alert" if signals.SCENARIO_SHIP else "what if")
    assert "%" in note and "2023-2025" in note


def test_upside_stash_valued_at_base_and_if_it_holds():
    """A WR free agent projects 6 (below the FLEX, 9): no gain at base; 11 if his new role holds, so he
    would start at FLEX (+2). The drop is the bench player the lineup misses least."""
    slots = ["QB", "RB", "WR", "TE", "FLEX", "BN", "BN"]

    def P(pid, pos, v):
        return Player(id=pid, position=pos, value=v, value_source="proj_points")
    roster = [P("qb", "QB", 20.0), P("rb", "RB", 12.0), P("wr", "WR", 13.0), P("te", "TE", 8.0), P("flex", "WR", 9.0),
              P("bn1", "RB", 5.0), P("bn2", "WR", 2.0)]
    weeks = [list(roster) for _ in range(4)]
    base = [P("fa", "WR", 6.0)] * 4
    holds = [P("fa", "WR", 11.0)] * 3 + [P("fa", "WR", 6.0)]       # the scenario covers three of the four weeks
    [s] = waivers.upside_for_roster(slots, weeks, {"fa": base}, {"fa": holds}, ["bn1", "bn2"], False, {"bn1": 50.0, "bn2": 20.0})
    assert s.drop in ("bn1", "bn2") and s.drop_loss == 0.0
    assert s.drop == "bn2"                                          # both cost nothing: the fewer rest-of-season points
    assert s.base_gains == (0.0, 0.0, 0.0, 0.0)
    assert s.holds_gains == pytest.approx((2.0, 2.0, 2.0, 0.0)) and s.holds_slot == "FLEX"


# ------------------------------------------------------------------------------ DDL copies
@pytest.mark.parametrize("mart, ddl, columns", [
    ("mart_player_role_alerts", signals.DDL["ops.player_role_alerts"], signals.ALERT_COLUMNS),
    ("mart_player_scenarios", signals.DDL["ops.player_scenarios"], signals.SCENARIO_COLUMNS),
    ("mart_waiver_upside", waivers.UPSIDE_DDL, waivers.UPSIDE_COLUMNS),
])
def test_view_prehook_ddl_matches_the_writer(mart, ddl, columns):
    text = (ROOT / f"dbt/models/marts/edge/{mart}.sql").read_text()
    hook = re.search(r'"(create table if not exists ops\.[^"]+)"', text).group(1)
    norm = lambda s: re.sub(r"\s+", " ", s).strip()   # noqa: E731
    assert norm(hook) == norm(ddl)
    ddl_cols = [c.strip().split()[0] for c in norm(ddl).split("(", 1)[1].rsplit(")", 1)[0].split(",")]
    assert ddl_cols == columns


def test_upside_fingerprint_is_the_waiver_engines():
    """mart_waiver_upside's inputs_current uses the same roster fingerprint as waivers.FINGERPRINT_SQL."""
    mart = (ROOT / "dbt/models/marts/edge/mart_waiver_upside.sql").read_text()
    body = re.search(r"fp as \(\n(.*?)\n\)\n", mart, re.S).group(1)
    norm = lambda s: re.sub(r"\s+", " ", re.sub(r"\{\{\s*ref\('([a-z_]+)'\)\s*\}\}", r"analytics.\1", s)).strip()   # noqa: E731
    assert norm(body) == norm(waivers.FINGERPRINT_SQL)
