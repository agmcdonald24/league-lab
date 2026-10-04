"""V-1 (Wave I-G): the decision record freezes before kickoff, the grade (regret, the app's edge) and the close calls'
calibration — no database needed (stand-in connection, synthetic weeks)."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from league_lab import lineup, validation
from league_lab.lineup import LineupInputs, build, close_calls, record_plan, record_rows

from .test_lineup import _inputs

ROOT = Path(__file__).resolve().parents[1]
T0 = datetime(2026, 10, 8, 12, 0, tzinfo=UTC)        # a Thursday morning: week 5 kicks off tonight
KICK = {4: T0 - timedelta(days=7), 5: T0 + timedelta(hours=12), 6: T0 + timedelta(days=7)}


# ------------------------------------------------------------------------------ the freeze rule
def test_record_plan_writes_the_next_week_keeps_started_weeks_and_reconstructs_missing_ones():
    weeks = {"L": [3, 4, 5, 6, 7]}                      # week 3 and 7: no kickoff known -> left alone
    kick = {**KICK, 3: T0 - timedelta(days=14)}
    plan = record_plan(weeks, [("L", 4)], kick, T0)
    assert plan == {("L", 3): "reconstruct", ("L", 4): "keep", ("L", 5): "write"}
    # once week 5 kicks off it is kept and week 6 is the one written
    plan = record_plan(weeks, [("L", 3), ("L", 4), ("L", 5)], kick, KICK[5] + timedelta(minutes=1))
    assert plan == {("L", 3): "keep", ("L", 4): "keep", ("L", 5): "keep", ("L", 6): "write"}
    # a week kicks off at its first kickoff exactly
    assert record_plan({"L": [5]}, [], KICK, KICK[5])[("L", 5)] == "reconstruct"


class _Cursor:
    """Just enough of a psycopg cursor for ``write_record`` against an in-memory ``ops.lineup_record``."""

    def __init__(self, db: _DB):
        self.db, self._rows = db, []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql: str, params: tuple = ()):
        s = " ".join(sql.split())
        if s.startswith("create table") or s.startswith("alter table"):
            self._rows = []
        elif s.startswith("select distinct league_id, week from ops.lineup_record"):
            self._rows = sorted({(r["league_id"], r["week"]) for r in self.db.table})
        elif "information_schema.columns" in s:
            self._rows = []                               # no M4 column here: flat
        elif "string_agg(distinct model_version" in s:
            self._rows = [(lg, w, "v3.0", "flat") for lg, w in zip(params[1], params[2], strict=True)]
        elif "from ops.projections as p" in s:
            self._rows = []                               # no ranges: the calls carry no odds
        elif s.startswith("delete from ops.lineup_record"):
            keys = set(zip(params[1], params[2], strict=True))
            self.db.table = [r for r in self.db.table if (r["league_id"], r["week"]) not in keys]
        else:
            raise AssertionError(f"unexpected SQL: {s[:80]}")

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def copy(self, sql: str):
        db = self.db
        cols = re.search(r"\((.*)\)", sql).group(1).split(", ")

        class _Copy:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def write_row(self, row):
                db.table.append(dict(zip(cols, row, strict=True)))
        return _Copy()


class _DB:
    def __init__(self):
        self.table: list[dict] = []
        self.commits = 0

    def cursor(self):
        return _Cursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass


def _weekly_inputs() -> LineupInputs:
    """test_lineup's league moved to weeks 4-6 (kickoffs KICK), the projection of player g3 set per call."""
    inp = _inputs()
    games = {w: {t: KICK[w] + timedelta(hours=h) for t, h in (("KC", 0), ("BUF", 60), ("LA", 61))} for w in (4, 5, 6)}
    proj = {}
    for (lg, _, g), v in inp.proj.items():
        for w in (4, 5, 6):
            proj[(lg, w, g)] = dict(v)
    return LineupInputs(season=2026, leagues=[{**inp.leagues[0], "last_scored_leg": 3}], weeks={"L": [4, 5, 6]}, proj=proj,
                        weekly={}, current=inp.current, sleeper=inp.sleeper, k_ppg=inp.k_ppg, games=games,
                        model_version="v3.0", starters={})


def _with_cook(inp: LineupInputs, pts: float) -> LineupInputs:
    proj = {k: ({**v, "proj_points": pts} if k[2] == "g3" else v) for k, v in inp.proj.items()}
    return LineupInputs(**{**inp.__dict__, "proj": proj})


def _record(db: _DB, week: int) -> dict[str, dict]:
    return {r["sleeper_player_id"]: r for r in db.table if r["week"] == week and r["sleeper_player_id"]}


def test_two_builds_before_kickoff_the_second_wins_and_a_build_after_changes_nothing():
    db = _DB()
    first = lineup.write_record(db, _with_cook(_weekly_inputs(), 14.0), as_of=T0 - timedelta(hours=10))
    assert first.written == [("L", 5)] and first.reconstructed == [("L", 4)]
    assert _record(db, 5)["3"]["value"] == 14.0 and _record(db, 4)["3"]["value"] == 14.0
    assert {r["record_source"] for r in db.table if r["week"] == 5} == {"kickoff"}
    assert {r["record_source"] for r in db.table if r["week"] == 4} == {"reconstructed"}
    # the reconstructed week was solved as of one second before its first kickoff: nobody locked
    assert all(r["as_of"] == KICK[4] - timedelta(seconds=1) for r in db.table if r["week"] == 4)

    # a second build before kickoff (Cook's projection moved): it replaces week 5; week 4 is kept as it was
    second = lineup.write_record(db, _with_cook(_weekly_inputs(), 2.0), as_of=T0)
    assert second.written == [("L", 5)] and second.reconstructed == []
    assert _record(db, 5)["3"]["value"] == 2.0 and _record(db, 4)["3"]["value"] == 14.0
    w5 = [r for r in db.table if r["week"] == 5]
    assert len({r["run_at"] for r in w5}) == 1 and w5[0]["run_at"] == T0     # one build's rows, not a mix
    frozen = sorted((r["week"], r["sleeper_player_id"] or "", r["value"]) for r in db.table if r["week"] == 5)

    # a build after week 5's kickoff: week 5 keeps the second build's rows; week 6 is the next one written
    third = lineup.write_record(db, _with_cook(_weekly_inputs(), 30.0), as_of=KICK[5] + timedelta(minutes=5))
    assert third.plan[("L", 5)] == "keep" and third.written == [("L", 6)]
    assert sorted((r["week"], r["sleeper_player_id"] or "", r["value"]) for r in db.table if r["week"] == 5) == frozen
    assert _record(db, 6)["3"]["value"] == 30.0


def test_the_record_is_the_build_lineup_with_its_total_and_one_row_per_player():
    db = _DB()
    inp = _weekly_inputs()
    rows, totals, _ = build(inp, as_of=T0)
    lineup.write_record(db, inp, rows, totals, as_of=T0)
    w5 = [r for r in db.table if r["week"] == 5]
    built = [r for r in rows if r["week"] == 5 and not r["is_realised"]]
    assert sorted((r["role"], r["slot"] or "", r["sleeper_player_id"] or "") for r in w5) == \
        sorted((r["role"], r["slot"] or "", r["sleeper_player_id"] or "") for r in built)
    total = next(t for t in totals if t["week"] == 5 and not t["is_realised"])["lineup_value"]
    assert {r["lineup_value"] for r in w5} == {total}
    assert total == pytest.approx(sum(r["value"] or 0 for r in w5 if r["role"] == "starter"), abs=0.011)
    assert set(lineup.RECORD_COLUMNS) == set(w5[0])


def test_record_ddl_matches_the_columns_and_the_dbt_pre_hooks():
    def cols(text: str) -> list[str]:
        body = re.search(r"create table if not exists ops\.lineup_record \((.*?)\)\s*(;|\"|,|$)", text, re.S).group(1)
        return [part.split()[0] for part in body.replace("\n", " ").split(",")]
    assert cols(lineup.RECORD_DDL) == lineup.RECORD_COLUMNS
    for model in ("mart_decision_record", "mart_decision_calls"):
        assert cols((ROOT / f"dbt/models/marts/edge/{model}.sql").read_text()) == lineup.RECORD_COLUMNS


# ------------------------------------------------------------------------------ the cards' calls
def _card_frame(rows: list[dict], totals: list[dict]) -> pd.DataFrame:
    """The columns app/lib/cards.py ``decisions`` reads (LINEUP_SQL's), from build() rows of one roster-week."""
    weakest = totals[0]["weakest_slot"]
    df = pd.DataFrame(rows)
    df["is_empty_slot"] = df["role"] == "empty"
    df["locked_now"] = df["is_locked"].fillna(False).astype(bool)
    df["is_weakest_slot"] = df["slot"] == weakest
    for c in ("team", "opponent", "opp_rank", "p10", "p25", "p50", "p75", "p90"):
        df[c] = None
    df["value"] = df["value"].astype(float)
    return df


@pytest.mark.parametrize("seed", range(12))
def test_close_calls_are_the_cards_decisions(seed):
    """The record's calls (lineup.close_calls) pick the same starters and alternatives as app/lib/cards.py."""
    import random

    from app.lib import cards

    rng = random.Random(seed)
    inp = _weekly_inputs()
    proj = {k: {**v, "proj_points": round(rng.uniform(2, 25), 2)} for k, v in inp.proj.items()}
    inp = LineupInputs(**{**inp.__dict__, "proj": proj})
    rows, totals, _ = build(inp, as_of=T0)
    rw = [r for r in rows if r["week"] == 5 and not r["is_realised"]]
    tot = [t for t in totals if t["week"] == 5 and not t["is_realised"]]
    ours = [(s["sleeper_player_id"], a["sleeper_player_id"]) for s, a, _ in close_calls(rw, tot[0]["weakest_slot"])]
    theirs = cards.decisions(_card_frame(rw, tot))
    assert ours == list(zip(theirs["sleeper_player_id"], theirs["alt_sleeper_player_id"], strict=True)) if len(theirs) else ours == []


def test_coin_flip_is_the_cards_rule():
    from app.lib import cards

    for p, m in [(0.52, 3.0), (0.56, 0.2), (None, 0.9), (None, 1.2), (0.549, 0.0)]:
        assert lineup.is_coin_flip(p, m) == cards.is_coin_flip({"p_win": p, "margin": m})


# ------------------------------------------------------------------------------ grading
def _grade_inputs() -> validation.GradeInputs:
    """One league, week 1 scored, two rosters; roster 1 started A (12) over B (20) at QB; the record said B. Roster 2
    followed the record. A dropped player C (no roster) was the record's flex for roster 2 and scored 7 elsewhere."""
    rec = pd.DataFrame([
        # roster 1: record = B, R1, W1
        {"sleeper_player_id": "B", "gsis_id": "gB", "call_rank": 1, "alt_sleeper_player_id": "A", "alt_gsis_id": "gA",
         "p_win": 0.53, "is_coin_flip": True, "roster_id": 1},
        {"sleeper_player_id": "R1", "gsis_id": "gR1", "roster_id": 1},
        {"sleeper_player_id": "W1", "gsis_id": "gW1", "roster_id": 1, "report_status": "Questionable"},
        # roster 2: record = Q2, R2, C (dropped before kickoff)
        {"sleeper_player_id": "Q2", "gsis_id": "gQ2", "roster_id": 2},
        {"sleeper_player_id": "R2", "gsis_id": "gR2", "roster_id": 2, "call_rank": 1, "alt_sleeper_player_id": "X2",
         "alt_gsis_id": "gX2", "p_win": 0.61, "is_coin_flip": False},
        {"sleeper_player_id": "C", "gsis_id": "gC", "roster_id": 2},
    ])
    for c, v in {"league_id": "L", "season": 2026, "week": 1, "role": "starter", "record_source": "kickoff",
                 "model_version": "v3.0", "pricing": "flat", "slot": "QB", "player_name": "x", "value": 10.0,
                 "margin": 0.5, "alt_player_name": "y", "alt_value": 9.5}.items():
        rec[c] = v
    for c in ("report_status", "call_rank", "alt_sleeper_player_id", "alt_gsis_id", "p_win", "is_coin_flip"):
        if c not in rec:
            rec[c] = None
    weekly = pd.DataFrame([
        ("L", 1, 1, "A", True, 12.0), ("L", 1, 1, "B", False, 20.0), ("L", 1, 1, "R1", True, 8.0),
        ("L", 1, 1, "W1", True, 5.0), ("L", 1, 1, "Z1", False, 1.0),
        ("L", 1, 2, "Q2", True, 15.0), ("L", 1, 2, "R2", True, 6.0), ("L", 1, 2, "X2", True, 9.0),
        ("L", 1, 2, "X3", False, 3.0),
    ], columns=["league_id", "week", "roster_id", "sleeper_player_id", "is_starter", "points_observed"])
    weekly["gsis_id"] = "g" + weekly["sleeper_player_id"]
    weekly["is_scored_week"] = True
    optimum = pd.DataFrame([("L", 1, 1, 33.0), ("L", 1, 2, 30.0)], columns=["league_id", "week", "roster_id", "optimum_points"])
    fallback = pd.DataFrame([("L", 1, "gC", 7.0)], columns=["league_id", "week", "gsis_id", "points"])
    # W1 was Questionable when the record was built and Out on the final report: roster 1 is news-affected
    status = pd.DataFrame([(1, "gW1", "Out", "ACT"), (1, "gQ2", None, "ACT")], columns=["week", "gsis_id", "report_status", "roster_status"])
    return validation.GradeInputs(rec, weekly, optimum, fallback, status)


def test_regret_and_edge_on_a_synthetic_week():
    rw = validation.grade_roster_weeks(_grade_inputs()).set_index("roster_id")
    r1, r2 = rw.loc[1], rw.loc[2]
    # roster 1: submitted A 12 + R1 8 + W1 5 = 25; the record B 20 + 8 + 5 = 33; optimum 33
    assert (r1.submitted_points, r1.app_points, r1.optimum_points) == (25.0, 33.0, 33.0)
    assert (r1.regret, r1.app_edge, r1.app_regret, r1.n_changed) == (8.0, 8.0, 0.0, 1)
    assert bool(r1.is_news_affected) and r1.n_news_starters == 1
    # roster 2: submitted Q2 15 + R2 6 + X2 9 = 30; the record Q2 15 + R2 6 + C 7 (his points elsewhere) = 28
    assert (r2.submitted_points, r2.app_points, r2.regret, r2.app_edge, r2.app_regret) == (30.0, 28.0, 0.0, -2.0, 2.0)
    assert not bool(r2.is_news_affected) and r2.status == "scored"


def test_unknown_points_and_unscored_weeks_are_not_zero():
    g = _grade_inputs()
    g.record.loc[g.record["sleeper_player_id"] == "C", "gsis_id"] = None          # a DEF-like player with no number
    rw = validation.grade_roster_weeks(g).set_index("roster_id")
    assert pd.isna(rw.loc[2].app_points) and rw.loc[2].n_app_unknown == 1 and pd.isna(rw.loc[2].app_edge)
    g = _grade_inputs()
    g.weekly["is_scored_week"] = False
    rw = validation.grade_roster_weeks(g)
    assert set(rw["status"]) == {"in_play"} and rw[["submitted_points", "app_points", "optimum_points"]].isna().all().all()
    calls = validation.grade_calls(g)
    assert calls["outcome"].isna().all()


def test_summary_weeks_add_up_to_the_season():
    g = _grade_inputs()
    w2 = g.record.copy()
    w2["week"] = 2
    weekly2 = g.weekly.copy()
    weekly2["week"] = 2
    weekly2.loc[weekly2["sleeper_player_id"] == "A", "points_observed"] = 30.0       # A outscored B in week 2
    g2 = validation.GradeInputs(pd.concat([g.record, w2]), pd.concat([g.weekly, weekly2]),
                                pd.concat([g.optimum, g.optimum.assign(week=2, optimum_points=[43.0, 30.0])]),
                                pd.concat([g.fallback, g.fallback.assign(week=2)]), g.status)
    s = validation.summary(validation.grade_roster_weeks(g2), validation.grade_calls(g2))
    assert s["available"] and [w["week"] for w in s["weeks"]] == [1, 2]
    for k in ("submitted", "app", "optimum", "regret", "edge"):
        assert s["season_totals"][k] == pytest.approx(sum(w[k] for w in s["weeks"]), abs=1e-9)
    assert s["season_totals"]["edge"] == 8.0 - 2.0 + (33.0 - 43.0) - 2.0
    assert s["news"]["roster_weeks"] == 1 and s["news"]["edge"] == 8.0 and "injury report" in s["sentences"]["news"]   # W1: week 1 only
    # the coin flip (B over A): won week 1, lost week 2 -> 50% for the side we leaned, 53% expected, 2 calls
    assert s["sentences"]["calls"] == "The coin flips landed 50% for the side we leaned (53% expected, 2 calls)."
    assert s["calls"]["n"] == 4 and s["calls"]["coin_flips"]["n"] == 2


def test_the_calibration_table_on_synthetic_coin_flips():
    import numpy as np

    rng = np.random.default_rng(7)
    p = rng.uniform(0.45, 0.75, 400)
    outcome = (rng.uniform(size=400) < p).astype(float)
    calls = pd.DataFrame({"p_win": p, "outcome": outcome, "is_coin_flip": p < 0.55, "status": "scored"})
    cal = validation.calibration(calls)
    assert cal["n"] == 400 and len(cal["table"]) == 10 and sum(r["n"] for r in cal["table"]) == 400
    assert [r["predicted"] for r in cal["table"]] == sorted(r["predicted"] for r in cal["table"])
    # calibrated by construction: every bin within sampling noise, the Brier near the expected p(1-p)
    assert all(abs(r["observed"] - r["predicted"]) < 0.25 for r in cal["table"])
    assert cal["brier"] == pytest.approx(float(np.mean(p * (1 - p))), abs=0.03)
    flips = calls[calls["is_coin_flip"]]
    assert cal["coin_flips"] == {"n": len(flips), "won": round(flips["outcome"].sum(), 2), "expected": round(flips["p_win"].sum(), 2)}
    # a perfect forecaster of certain outcomes scores 0; an always-wrong one 1
    assert validation.calibration(pd.DataFrame({"p_win": [1.0, 0.0], "outcome": [1.0, 0.0], "is_coin_flip": False,
                                                "status": "scored"}))["brier"] == 0.0
    assert validation.calibration(calls.iloc[0:0])["n"] == 0


def test_record_rows_label_calls_and_never_mix_realised_rows():
    inp = _weekly_inputs()
    rows, totals, _ = build(inp, as_of=T0)
    meta = {("L", 5): {"first_kickoff_at": KICK[5], "model_version": "v3.0", "pricing": "ev"}}
    out = record_rows(rows, totals, meta, {}, "kickoff", T0)
    assert {r["week"] for r in out} == {5} and {r["pricing"] for r in out} == {"ev"}
    ranks = sorted(r["call_rank"] for r in out if r.get("call_rank") is not None)
    assert ranks == list(range(1, len(ranks) + 1)) and len(ranks) <= lineup.N_CALLS
    assert all(r["role"] == "starter" for r in out if r.get("call_rank") is not None)


# ------------------------------------------------------------------------------ the console page (database; skipped without)
def test_the_record_page_shows_our_lineups_against_the_ones_started():
    """app/pages/13_Record.py on the database (.env): the new section renders the same season numbers as the summary."""
    import sys

    psycopg = pytest.importorskip("psycopg")
    from league_lab.config import get_settings

    try:
        with psycopg.connect(get_settings().pipeline_dsn(), connect_timeout=3) as c:
            if not c.execute("select to_regclass('analytics.mart_decision_record')").fetchone()[0]:
                pytest.skip("mart_decision_record not built")
    except psycopg.OperationalError as exc:
        pytest.skip(f"no database: {exc}")
    from streamlit.testing.v1 import AppTest

    app = ROOT / "app"
    if str(app) not in sys.path:
        sys.path.insert(0, str(app))
    at = AppTest.from_file(str(app / "pages" / "13_Record.py"), default_timeout=240)
    at.query_params["league"] = "1389709692405551104"
    at.query_params["team"] = "2"
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    assert "Our lineups against the ones started" in [h.value for h in at.subheader]
    labels = {m.label: m.value for m in at.metric}
    assert "Our lineups would have added" in labels and labels["Best lineup in hindsight"].startswith("+")
    assert any("had every team started our lineup" in m.value for m in at.markdown)
