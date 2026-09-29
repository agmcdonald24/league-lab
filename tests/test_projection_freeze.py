"""B5 decision record: a league-week's projections freeze at its first kickoff (no database needed)."""

import re
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from league_lab import db, projections
from league_lab.projections import freeze_plan, score_drift

ROOT = Path(__file__).resolve().parents[1]
T0 = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)                 # "now" of the first refit below
KICKOFFS = {1: T0 - timedelta(days=19), 2: T0 - timedelta(days=12), 3: T0 - timedelta(days=5),
            4: T0 + timedelta(days=2, hours=8), 5: T0 + timedelta(days=9)}   # week 6: no schedule yet
KEYS = ["league_id", "week"]


def _refit(fitted_at: datetime, value: float, weeks=range(1, 7), leagues=("L1", "L2")) -> pd.DataFrame:
    """A refit's rows: two players per league-week, every value = ``value`` (so runs are told apart)."""
    rows = [{"league_id": lg, "season": 2026, "week": w, "gsis_id": f"P{i}", "position": "WR",
             "proj_points": value + i, "p10": value - 5, "p90": value + 9, "fitted_at": fitted_at}
            for lg in leagues for w in weeks for i in (1, 2)]
    return pd.DataFrame(rows)


def _stored(table: pd.DataFrame) -> pd.DataFrame:
    """What _write_projections reads back: one row per stored league-week."""
    if table.empty:
        return pd.DataFrame(columns=[*KEYS, "fitted_at", "frozen_source", "frozen_at"])
    return table.groupby(KEYS, as_index=False).agg(fitted_at=("fitted_at", "max"), frozen_source=("frozen_source", "max"),
                                                    frozen_at=("frozen_at", "max"))


def _apply(table: pd.DataFrame, new: pd.DataFrame, now: datetime) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The in-memory twin of _write_projections: relabel, then replace only the 'write'/'delete' weeks."""
    plan = freeze_plan(new, _stored(table), KICKOFFS, now)
    t = table.copy()
    for r in plan[plan["relabel"]].itertuples():
        m = (t["league_id"] == r.league_id) & (t["week"] == r.week) & t["frozen_source"].isna()
        t.loc[m, "frozen_source"] = r.frozen_source
        t.loc[m, "frozen_at"] = r.frozen_at
    drop = plan.loc[plan["action"].isin(["write", "delete"]), KEYS].assign(_drop=True)
    t = t.merge(drop, on=KEYS, how="left")
    t = t[t["_drop"].isna()].drop(columns="_drop")
    w = new.merge(plan.loc[plan["action"] == "write", [*KEYS, "frozen_source", "frozen_at"]], on=KEYS)
    out = pd.concat([t, w], ignore_index=True).astype({"frozen_source": object, "frozen_at": object})
    return out.sort_values([*KEYS, "gsis_id"]).reset_index(drop=True), plan


def _week(table: pd.DataFrame, league: str, week: int) -> pd.DataFrame:
    return table[(table["league_id"] == league) & (table["week"] == week)].reset_index(drop=True)


def test_freeze_plan_rules():
    stored = pd.DataFrame([
        # written before week 1's kickoff and not labelled yet: the board managers saw -> kickoff
        {"league_id": "L1", "week": 1, "fitted_at": KICKOFFS[1] - timedelta(hours=10), "frozen_source": None, "frozen_at": None},
        # written after week 2 had started (the 2026 weeks 1-3 case) -> refit, no frozen_at
        {"league_id": "L1", "week": 2, "fitted_at": KICKOFFS[2] + timedelta(days=1), "frozen_source": None, "frozen_at": None},
        # already labelled by an earlier run: kept as is, not relabelled
        {"league_id": "L1", "week": 3, "fitted_at": KICKOFFS[3] - timedelta(hours=1), "frozen_source": "kickoff",
         "frozen_at": KICKOFFS[3] - timedelta(hours=1)},
        # a live week: rewritten
        {"league_id": "L1", "week": 4, "fitted_at": T0 - timedelta(days=1), "frozen_source": None, "frozen_at": None},
        # a live week the refit no longer projects: deleted (the old season-wide delete did the same)
        {"league_id": "L1", "week": 5, "fitted_at": T0 - timedelta(days=1), "frozen_source": None, "frozen_at": None},
    ])
    new = pd.DataFrame({"league_id": ["L1", "L1", "L1", "L1", "L1", "L2"], "week": [1, 2, 3, 4, 6, 2]})
    plan = freeze_plan(new, stored, KICKOFFS, T0).set_index(KEYS)

    assert plan.loc[("L1", 1), ["action", "relabel", "frozen_source"]].tolist() == ["keep", True, "kickoff"]
    assert plan.loc[("L1", 1), "frozen_at"] == KICKOFFS[1] - timedelta(hours=10)     # = the kept rows' fitted_at
    assert plan.loc[("L1", 2), ["action", "relabel", "frozen_source"]].tolist() == ["keep", True, "refit"]
    assert plan.loc[("L1", 2), "frozen_at"] is None
    assert plan.loc[("L1", 3), ["action", "relabel", "frozen_source"]].tolist() == ["keep", False, "kickoff"]
    assert plan.loc[("L1", 4), ["action", "frozen_source"]].tolist() == ["write", None]   # not started: live
    assert plan.loc[("L1", 5), "action"] == "delete"
    assert plan.loc[("L1", 6), ["action", "started", "frozen_source"]].tolist() == ["write", False, None]  # no kickoff known
    # a league-week first written after its kickoff (a league added mid-season): written once, labelled refit
    assert plan.loc[("L2", 2), ["action", "started", "frozen_source"]].tolist() == ["write", True, "refit"]
    # a stored week of a started kickoff is kept even when the refit no longer projects it
    gone = freeze_plan(new[new["week"] != 1], stored, KICKOFFS, T0).set_index(KEYS)
    assert gone.loc[("L1", 1), "action"] == "keep"


def test_freeze_plan_on_an_empty_table_writes_everything():
    plan = freeze_plan(pd.DataFrame({"league_id": ["L1"] * 3, "week": [2, 4, 6]}),
                       pd.DataFrame(columns=[*KEYS, "fitted_at", "frozen_source", "frozen_at"]), KICKOFFS, T0)
    assert plan["action"].tolist() == ["write"] * 3
    assert plan["frozen_source"].tolist() == ["refit", None, None]


def test_played_weeks_are_identical_across_refits_and_the_kickoff_board_is_kept():
    # before B5 every week was rewritten by each refit; B5's first run finds those rows (written after
    # weeks 1-3 had kicked off) and locks them as refit values
    table = _refit(T0 - timedelta(days=3), 10.0).assign(frozen_source=None, frozen_at=None).astype({"frozen_source": object, "frozen_at": object})
    before = table.copy()
    run1, _ = _apply(table, _refit(T0, 20.0), T0)
    run2, plan2 = _apply(run1, _refit(T0 + timedelta(hours=1), 30.0), T0 + timedelta(hours=1))
    for lg in ("L1", "L2"):
        for w in (1, 2, 3):
            kept = _week(run2, lg, w)
            assert kept.equals(_week(run1, lg, w))                                   # byte-identical between two runs
            assert kept["proj_points"].tolist() == _week(before, lg, w)["proj_points"].tolist()   # the pre-B5 values
            assert set(kept["frozen_source"]) == {"refit"} and kept["frozen_at"].isna().all()
        for w in (4, 5, 6):
            live = _week(run2, lg, w)
            assert live["proj_points"].tolist() == [31.0, 32.0] and live["frozen_source"].isna().all()   # still refit
    assert not plan2["relabel"].any()                                                # labels are set once

    # the clock passes week 4's first kickoff: the board published last before it is the record
    last_pre_kickoff = T0 + timedelta(hours=1)
    after = KICKOFFS[4] + timedelta(hours=12)
    run3, plan3 = _apply(run2, _refit(after, 40.0), after)
    run4, _ = _apply(run3, _refit(after + timedelta(days=1), 50.0), after + timedelta(days=1))
    for lg in ("L1", "L2"):
        wk4 = _week(run4, lg, 4)
        assert wk4.equals(_week(run3, lg, 4))
        assert wk4["proj_points"].tolist() == [31.0, 32.0]                         # what managers saw before kickoff
        assert set(wk4["frozen_source"]) == {"kickoff"} and (wk4["frozen_at"] == last_pre_kickoff).all()
        assert (wk4["frozen_at"] < KICKOFFS[4]).all()
        assert _week(run4, lg, 5)["proj_points"].tolist() == [51.0, 52.0]          # week 5 is still live
    assert sorted(plan3.loc[plan3["relabel"], "week"].unique().tolist()) == [4]


def _ddl_columns(text: str, table: str) -> list[str]:
    body = re.search(rf"create table if not exists ops\.{table} \((.*?)\)\s*(;|\"|$)", text, re.S).group(1)
    return [part.split()[0] for part in body.replace("\n", " ").split(",")]


def test_projections_ddl_is_the_same_everywhere_and_upgrades_an_existing_table():
    """Three copies of each DDL (migration, the writer's DDL dict, the dbt model's pre_hook) must agree, and each
    must add the B5 columns to a table created before them (the Mac's database already holds 2026 projections)."""
    mart = (ROOT / "dbt/models/marts/nfl/mart_player_week_projections.sql").read_text()
    cols = _ddl_columns(db.OPS_DDL, "projections")
    assert cols == _ddl_columns(projections.DDL["ops.projections"], "projections") == _ddl_columns(mart, "projections")
    assert cols[-2:] == ["frozen_at", "frozen_source"]
    drift_view = (ROOT / "dbt/models/marts/nfl/mart_projection_drift.sql").read_text()
    for text in (db.OPS_DDL, projections.DDL["ops.projections"], mart):
        for col in ("frozen_at timestamptz", "frozen_source text"):
            assert f"alter table ops.projections add column if not exists {col}" in text
    for text in (db.OPS_DDL, projections.DDL["ops.projection_drift"], drift_view):
        assert "alter table ops.projection_drift add column if not exists frozen_share double precision" in text


def test_score_drift_reports_the_share_scored_on_the_kickoff_board():
    rows = []
    for week, source in ((1, "refit"), (2, "kickoff"), (3, None)):
        for i in range(10):
            rows.append({"league_id": "L1", "season": 2026, "week": week, "position": "WR", "gsis_id": f"W{i}", "game_id": "G",
                         "played": True, "is_rankable": True, "proj_points": float(i), "p10": 0.0, "p90": 20.0,
                         "points_actual": float(i), "model_version": "v2.0", "frozen_source": source})
    res = score_drift(pd.DataFrame(rows)).set_index("week")["frozen_share"]
    assert res.to_dict() == {1: 0.0, 2: 1.0, 3: 0.0}     # refit values and an unlabelled (not yet locked) week both count as 0
    unlabelled = score_drift(pd.DataFrame(rows).drop(columns="frozen_source"))
    assert (unlabelled["frozen_share"] == 0.0).all()      # a board without the label is not a kickoff record


# ------------------------------------------------------------------------------ stale injury flag (freshness_banner)
@pytest.fixture
def banner(monkeypatch):
    sys.path.insert(0, str(ROOT / "app"))
    from lib import db as app_db
    from lib import ui

    calls = SimpleNamespace(caption=[], warning=[])
    monkeypatch.setattr(ui, "st", SimpleNamespace(caption=calls.caption.append, warning=calls.warning.append))

    def run(loaded, last_final: date, next_kickoff, dim_game=True):
        def fake_query(sql, params=()):
            if "group by source" in sql:
                return pd.DataFrame({"source": ["nflverse"], "last_loaded": [loaded], "failures": [0]})
            if "mart_coverage" in sql:
                return pd.DataFrame({"season": [2026], "through_game_date": [last_final], "through_reg_week": [3], "league_scored_weeks": [3]})
            if "dataset = 'injuries'" in sql:
                return pd.DataFrame({"loaded": [loaded]})
            if "dim_game" in sql:
                return pd.DataFrame({"next_kickoff": [next_kickoff]})
            raise AssertionError(sql)

        calls.caption.clear()
        calls.warning.clear()
        monkeypatch.setattr(ui, "query", fake_query)
        monkeypatch.setattr(app_db, "missing_relations", lambda names: [] if dim_game else list(names))
        ui.freshness_banner()
        return list(calls.warning)

    yield run
    sys.path.remove(str(ROOT / "app"))


def test_freshness_banner_flags_a_stale_injury_report(banner):
    now = pd.Timestamp.now(tz="UTC")
    today = now.tz_convert("America/New_York").date()
    # loaded yesterday, next kickoff in 3 days: more than 48 h before it -> stale
    w = banner(now - pd.Timedelta(days=1), today - timedelta(days=2), now + pd.Timedelta(days=3))
    assert len(w) == 1 and w[0].startswith("Injury report last loaded ") and "; treat Questionable tags as stale." in w[0]
    assert "48 h before the next kickoff" in w[0] and "last final game" not in w[0]
    # loaded before the last final game's date -> stale on that rule too
    w = banner(now - pd.Timedelta(days=4), today - timedelta(days=2), now + pd.Timedelta(days=3))
    assert "predates the last final game" in w[0] and "48 h" in w[0]
    # never loaded
    assert "last loaded never" in banner(None, today - timedelta(days=2), now + pd.Timedelta(days=1))[0]


def test_freshness_banner_quiet_when_fresh_or_offseason(banner):
    now = pd.Timestamp.now(tz="UTC")
    today = now.tz_convert("America/New_York").date()
    assert banner(now - pd.Timedelta(hours=2), today - timedelta(days=1), now + pd.Timedelta(days=1)) == []   # fresh
    assert banner(now - pd.Timedelta(days=90), today - timedelta(days=100), now + pd.Timedelta(days=60)) == []  # offseason
    # a database without dim_game (hosted copy before the next sync): the last-final-game rule alone
    assert banner(now - pd.Timedelta(days=1), today - timedelta(days=2), None, dim_game=False) == []
    assert "predates the last final game" in banner(now - pd.Timedelta(days=4), today - timedelta(days=2), None, dim_game=False)[0]
