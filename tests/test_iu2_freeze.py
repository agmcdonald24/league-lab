"""IU-2 (Wave I-U): fr1.0, the live week after its first kickoff. The switch (LEAGUE_LAB_FREEZE=week|game, default
week), the week under way and its games not kicked off, the live rows (gated like the live week), the shadow's moves
and reasons, the step that never raises, and the overlay's DDL / mart / source wiring. No database."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from league_lab import availability_gate as AG
from league_lab import projections as P

ROOT = Path(__file__).resolve().parents[1]
THU = datetime(2026, 10, 9, 0, 15, tzinfo=UTC)          # week 5's first kickoff (TB at DAL)
SUN_LONDON = datetime(2026, 10, 11, 13, 30, tzinfo=UTC)  # PHI at JAX
SUN_1PM = datetime(2026, 10, 11, 17, 0, tzinfo=UTC)      # CIN at MIA
NEXT_THU = datetime(2026, 10, 16, 0, 15, tzinfo=UTC)
FRI = datetime(2026, 10, 9, 16, 0, tzinfo=UTC)

GAMES = pd.DataFrame({"week": [5, 5, 5, 6], "home_team": ["DAL", "JAX", "MIA", "KC"],
                      "away_team": ["TB", "PHI", "CIN", "LV"], "kickoff_at": [THU, SUN_LONDON, SUN_1PM, NEXT_THU]})


@pytest.mark.parametrize("value, unit", [(None, "week"), ("", "week"), ("week", "week"), ("WEEK", "week"),
                                         ("games", "week"), ("1", "week"), ("game", "game"), (" Game ", "game")])
def test_the_switch_is_week_unless_it_says_game(monkeypatch, value, unit):
    if value is None:
        monkeypatch.delenv(P.FREEZE_FLAG, raising=False)
    else:
        monkeypatch.setenv(P.FREEZE_FLAG, value)
    assert P.freeze_unit() == unit


def test_the_week_under_way_is_the_one_whose_first_game_kicked_off_and_that_has_a_game_left():
    assert P.started_week(GAMES, datetime(2026, 10, 8, 12, tzinfo=UTC))[0] is None      # before Thursday: no week under way
    week, teams = P.started_week(GAMES, FRI)
    assert week == 5 and set(teams["team"]) == {"JAX", "PHI", "MIA", "CIN"}            # Thursday's game is not live
    week, teams = P.started_week(GAMES, datetime(2026, 10, 11, 14, 0, tzinfo=UTC))       # London in progress
    assert week == 5 and set(teams["team"]) == {"MIA", "CIN"}
    assert P.started_week(GAMES, SUN_1PM)[0] is None                                    # the last game kicked off
    assert P.started_week(GAMES.iloc[0:0], FRI)[0] is None


def _pred() -> pd.DataFrame:
    rows = []
    for lid in ("house_a", "house_b"):
        for g, pos, pts in (("thu_wr", "WR", 12.0), ("jax_wr", "WR", 14.0), ("jax_wr2", "WR", 6.0), ("mia_rb", "RB", 11.0),
                            ("mia_qb", "QB", 18.0)):
            for wk in (5, 6):
                rows.append({"league_id": lid, "season": 2026, "week": wk, "gsis_id": g, "position": pos,
                             "proj_points": pts, "proj_targets": 5.0, "p10": pts / 2, "p90": pts * 2, "model_version": "v3.6",
                             "pricing": "flat", "availability": None})
    return pd.DataFrame(rows)


TEAMS = pd.DataFrame({"position": ["WR", "WR", "WR", "RB", "QB"], "gsis_id": ["thu_wr", "jax_wr", "jax_wr2", "mia_rb", "mia_qb"],
                      "team": ["DAL", "JAX", "JAX", "MIA", "MIA"]})


def _sits(code: str, why: str) -> dict:
    return AG.classify(AG.entry(code, "Sleeper", as_of=FRI, note=why))


def test_live_rows_are_the_unplayed_games_of_the_week_gated_and_never_labelled_frozen():
    pred = _pred()
    before = pred.copy()
    _, teams = P.started_week(GAMES, FRI)
    live = P.live_rows(pred, 5, teams, TEAMS, {"jax_wr": _sits("OUT", "hamstring")})
    assert set(live["gsis_id"]) == {"jax_wr", "jax_wr2", "mia_rb", "mia_qb"}             # not Thursday's DAL receiver
    assert set(live["week"]) == {5} and len(live) == 8                                    # both house leagues
    out = live[live["gsis_id"] == "jax_wr"]
    assert (out["proj_points"] == 0).all() and (out["proj_targets"] == 0).all() and (out["p90"] == 0).all()
    assert json.loads(out["availability"].iloc[0])["code"] == "OUT"
    assert live["frozen_source"].isna().all() and live["frozen_at"].isna().all()
    assert set(live["game_kickoff"]) == {SUN_LONDON, SUN_1PM}
    pd.testing.assert_frame_equal(pred, before)                                            # tonight's frame untouched


def test_the_shadow_names_who_sits_who_is_back_whose_teammate_sits_and_the_threshold():
    _, teams = P.started_week(GAMES, FRI)
    live = P.live_rows(_pred(), 5, teams, TEAMS, {"jax_wr": _sits("OUT", "hamstring")})
    live.loc[live["gsis_id"] == "jax_wr2", "proj_points"] = 9.5                          # +3.5 against 6.0
    live.loc[live["gsis_id"] == "mia_rb", "proj_points"] = 12.9                          # +1.9: under the threshold
    stored = live[["league_id", "gsis_id", "position"]].copy()
    stored["proj_points"] = stored["gsis_id"].map({"jax_wr": 14.0, "jax_wr2": 6.0, "mia_rb": 11.0, "mia_qb": 0.0})
    stored["availability"] = [AG.record_text(_sits("OUT", "ankle")) if g == "mia_qb" else None for g in stored["gsis_id"]]
    stored["model_version"], stored["frozen_source"] = "v3.6", "kickoff"
    moves = P.shadow_moves(live, stored, {"jax_wr": "A. Receiver", "jax_wr2": "B. Backup"})
    by = {(m["league_id"], m["gsis_id"]): m for m in moves}
    assert {g for _, g in by} == {"jax_wr", "jax_wr2", "mia_qb"}                         # mia_rb moved 1.9: not listed
    assert by[("house_a", "jax_wr")]["reason"].startswith("sits: ") and by[("house_a", "jax_wr")]["delta"] == -14.0
    assert by[("house_a", "jax_wr2")]["reason"] == "teammate sits: A. Receiver (WR)"
    assert by[("house_a", "mia_qb")]["reason"].startswith("back: the kickoff board had him out (OUT)")
    assert by[("house_b", "jax_wr2")]["delta"] == 3.5 and by[("house_b", "jax_wr2")]["kickoff_points"] == 6.0
    stored2 = stored.assign(model_version="v3.5", availability=None)
    live2 = live.assign(availability=None)
    reasons = {m["reason"] for m in P.shadow_moves(live2, stored2, {})}
    assert reasons == {"the model changed since the kickoff board (v3.5 -> v3.6)"}
    assert P.shadow_moves(live.iloc[0:0], stored, {}) == [] and P.shadow_moves(live, stored.iloc[0:0], {}) == []


class _Broken:
    """A connection whose every query fails: the step logs, says so, and returns."""
    def cursor(self):
        raise RuntimeError("no database")

    def rollback(self):
        self.rolled = True

    def commit(self):
        pass


def test_the_step_never_raises_and_still_writes_its_shadow(monkeypatch, tmp_path):
    monkeypatch.setattr(P, "SHADOW_PATH", tmp_path / "logs" / "freeze_shadow.json")
    monkeypatch.delenv(P.FREEZE_FLAG, raising=False)
    conn = _Broken()
    s = P.live_after_project(conn, 2026, _pred(), pd.DataFrame(), FRI)
    assert s["error"] and s["mode"] == "week" and conn.rolled
    assert json.loads((tmp_path / "logs" / "freeze_shadow.json").read_text())["error"]


def _ddl_columns(text: str) -> list[str]:
    body = re.search(r"\((.*?)\);", text, re.S).group(1)
    return [part.split()[0] for part in body.replace("\n", " ").split(",")]


def test_the_overlay_has_the_shape_of_ops_projections_and_migrate_creates_it():
    live = _ddl_columns(P.NFL_DDL[P.LIVE_TABLE])
    stored = _ddl_columns(P.DDL["ops.projections"]) + ["pricing", "availability"]            # the create + its alters
    assert set(stored) <= set(live) and set(live) - set(stored) == {"team", "game_kickoff"}
    assert P.DDL[P.LIVE_TABLE] == P.NFL_DDL[P.LIVE_TABLE]                                    # migrate runs NFL_DDL
    mart = (ROOT / "dbt/models/marts/nfl/mart_player_week_projections.sql").read_text()
    assert "create table if not exists ops.projection_live (like ops.projections)" in mart   # a fresh database builds
    assert "source('ops', 'projection_live')" in mart
    assert "- name: projection_live" in (ROOT / "dbt/models/sources/sources.yml").read_text()


def test_the_week_path_leaves_freeze_plan_and_the_writer_alone():
    """The switch is read in one place, after the B5 writer: freeze_plan and _write_projections never see it."""
    import inspect

    for f in (P.freeze_plan, P._write_projections, P.write_nfl_wide):
        assert "FREEZE_FLAG" not in inspect.getsource(f) and "freeze_unit" not in inspect.getsource(f)
    src = inspect.getsource(P.project)
    assert src.index("_write_projections(conn, pred, season, now)") < src.index("live_after_project(")


def test_the_reason_names_the_stat_line_that_moved():
    row = {"proj_passing_yards_kickoff": 251.0, "proj_passing_yards": 270.4, "proj_passing_tds_kickoff": 1.71,
           "proj_passing_tds": 1.95, "proj_carries_kickoff": 2.0, "proj_carries": 2.0, "proj_targets_kickoff": None}
    assert P._line_moves(row) == "passing_tds 1.71 -> 1.95, passing_yards 251.00 -> 270.40"
    assert P._line_moves({}) == ""


def test_freeze_shadow_prints_and_writes_the_summary_part_and_never_fails(monkeypatch, tmp_path):
    from typer.testing import CliRunner

    from league_lab.cli import app

    monkeypatch.setattr(P, "SHADOW_PATH", tmp_path / "freeze_shadow.json")
    md = tmp_path / "logs" / "freeze_shadow.md"
    r = CliRunner().invoke(app, ["freeze-shadow", "--md", str(md)])
    assert r.exit_code == 0 and "no freeze_shadow.json yet" in r.output and md.read_text().startswith("fr1.0 shadow: no")
    (tmp_path / "freeze_shadow.json").write_text(json.dumps({
        "mode": "week", "week": 5, "games_left": 14, "players_live": 580, "move_threshold": 2.0, "seconds": 0.3,
        "computed_at": "2026-10-09T16:19:21+00:00", "gate_source": "Sleeper directory", "gate_copy": "2026-10-05",
        "moves": [{"league_id": "1", "league": "House", "gsis_id": "g", "name": "A. Receiver", "position": "WR", "team": "JAX",
                   "kickoff_points": 14.0, "live_points": 0.0, "delta": -14.0, "reason": "sits: Out · Sleeper"}]}))
    r = CliRunner().invoke(app, ["freeze-shadow", "--md", str(md)])
    assert r.exit_code == 0 and "A. Receiver" in r.output
    text = md.read_text()
    assert text.startswith("fr1.0 shadow: week under way: 5; 1 house-league rows move by 2.0 points or more")
    assert "| House | A. Receiver | WR | JAX | 14.00 | 0.00 | -14.00 | sits: Out · Sleeper |" in text
    (tmp_path / "freeze_shadow.json").write_text("{not json")
    assert CliRunner().invoke(app, ["freeze-shadow"]).exit_code == 0


def test_the_reason_names_a_yardage_bonus_the_line_crossed():
    row = {"proj_passing_yards_kickoff": 292.42, "proj_passing_yards": 304.91, "proj_receiving_yards_kickoff": 98.2,
           "proj_receiving_yards": 99.0}
    dynasty = {"bonus_pass_yd_300": 3.0, "bonus_pass_yd_400": 6.0, "bonus_rec_yd_100": 3.0, "rec": 1.0}
    assert P._bonus_crossings(row, dynasty) == "crosses the 300-yard passing bonus (+3)"
    assert P._bonus_crossings({**row, "proj_passing_yards": 290.0}, dynasty) == ""
    assert P._bonus_crossings(row, {"rec": 0.5}) == ""
    down = {"proj_receiving_yards_kickoff": 104.0, "proj_receiving_yards": 97.0}
    assert P._bonus_crossings(down, dynasty) == "crosses the 100-yard receiving bonus (-3)"
