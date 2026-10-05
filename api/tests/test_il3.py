"""Wave I-L (IL-3): `/api/status` carries `odds_grades` = the newest season-to-date grade of the week's win probability
and the ranges (`analytics.odds_grades`, written by the nightly's `league-lab grade-odds`): {season, through_week,
brier, coverage_50, coverage_80, graded_at}; None when no row or no table. Read only."""

from __future__ import annotations

import pandas as pd
import pytest

from league_lab_api import main

from .conftest import DYNASTY, SCRUBS, needs_db

KEYS = {"season", "through_week", "brier", "coverage_50", "coverage_80", "graded_at"}


def _fake(rows: pd.DataFrame | None):
    def q(sql, params=(), *a, **k):
        if "to_regclass" in sql:
            return pd.DataFrame({"t": [None if rows is None else "analytics.odds_grades"]})
        return rows if rows is not None else pd.DataFrame()
    return q


def test_odds_grades_reads_the_newest_pooled_rows(monkeypatch):
    rows = pd.DataFrame({"season": 2026, "week": 5, "metric": ["brier", "log_loss", "coverage_80", "coverage_50"],
                         "value": [0.2391, 0.671, 0.7812, 0.4975], "n": [55, 55, 880, 400],
                         "graded_at": pd.Timestamp("2026-10-07T11:40:00Z")})
    monkeypatch.setattr(main, "query", _fake(rows))
    assert main._status_odds_grades() == {"season": 2026, "through_week": 5, "brier": 0.2391, "coverage_50": 0.4975,
                                          "coverage_80": 0.7812, "graded_at": "2026-10-07T11:40:00+00:00"}


def test_odds_grades_none_without_the_table_or_rows(monkeypatch):
    monkeypatch.setattr(main, "query", _fake(None))
    assert main._status_odds_grades() is None
    monkeypatch.setattr(main, "query", _fake(pd.DataFrame(columns=["season", "week", "metric", "value", "n", "graded_at"])))
    assert main._status_odds_grades() is None


def test_odds_grades_a_failed_read_is_none_never_a_500(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("database down")
    monkeypatch.setattr(main, "query", boom)
    assert main._status_odds_grades() is None


@needs_db
def test_status_carries_odds_grades(client):
    """On the database the suite reads: the key is there — a dict with the six keys where the nightly graded, None
    where `analytics.odds_grades` does not exist yet."""
    body = client.get("/api/status").json()
    assert "odds_grades" in body
    og = body["odds_grades"]
    assert og is None or (set(og) == KEYS and (og["brier"] is None or 0.0 <= og["brier"] <= 1.0))


# ------------------------------------------------------------------------------ v3.3: the scaled line is one number
@pytest.fixture
def record_mode(monkeypatch):
    from league_lab import scoring as S

    from league_lab_api import ondemand
    monkeypatch.delenv("LEAGUE_LAB_EV_PRICING", raising=False)
    S.set_record_reader(ondemand._pricing_rows)
    yield
    S.set_record_reader(ondemand._pricing_rows)


@needs_db
@pytest.mark.parametrize("league", [DYNASTY, SCRUBS])
def test_every_wr_line_prices_to_his_stored_projection(sql, record_mode, league):
    """v3.3 scales a new-team WR's line (calibration nt1.0) before anything is priced: on a board built with it, every
    week-5 WR line priced on request equals his house projection (M6's rookie parity, widened to every WR — the
    new-team WRs among them). Holds on a board built without it too."""
    from league_lab import anyleague as A

    from league_lab_api import db
    season, week = 2026, 5
    if not A.nfl_wide_ready(db.query, season, week):
        pytest.skip("no NFL-wide tables for week 5")
    lines = db.query("select * from ops.projection_lines where season = %s and week = %s and position = 'WR'", (season, week))
    stored = db.query("""select gsis_id, proj_points from ops.projections where league_id = %s and season = %s
                         and week = %s and position = 'WR'""", (league, season, week)).set_index("gsis_id")
    sc = sql("select scoring_settings from analytics.dim_league_season where league_id = %s and is_current_season", (league,))
    scoring = {k: float(v) for k, v in sc[0]["scoring_settings"].items() if v is not None}
    priced = A.price_lines(lines, scoring).set_axis(lines["gsis_id"])
    both = [g for g in priced.index if g in stored.index]
    assert len(both) > 100
    off = {g: (round(float(priced[g]), 4), round(float(stored.loc[g, "proj_points"]), 4)) for g in both
           if abs(float(priced[g]) - float(stored.loc[g, "proj_points"])) > 1e-9}
    assert not off, off
