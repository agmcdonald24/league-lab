"""V-1 (Wave I-G): the decision record on /api/record (needs_db: the clone `league_lab_i0a` with `league-lab validate`
run and `mart_decision_record` / `mart_decision_calls` built). Scrubs weeks 1-2 are graded (reconstructed: the record
did not exist when they were played), and the numbers reconcile: the sum of the weeks is the season, each week is the
sum of its roster-weeks, and the API's grade is the Python twin's (league_lab.validation on the source tables)."""

from __future__ import annotations

import pytest
from league_lab import validation as V

from .conftest import SCRUBS, needs_db

TEST_LEAGUE = "9000000000000000001"     # the fictional league of the Sleeper fixtures

pytestmark = needs_db


def _have_marts(sql) -> bool:
    return sql("select to_regclass('analytics.mart_decision_record') is not null and "
               "to_regclass('analytics.mart_decision_calls') is not null as ok")[0]["ok"]


@pytest.fixture
def decisions(client, sql):
    if not _have_marts(sql):
        pytest.skip("mart_decision_record not built on this database (league-lab validate + dbt build first)")
    d = client.get(f"/api/record?league={SCRUBS}").json()
    assert d["available"] is True and "decisions" in d
    return d["decisions"]


def test_scrubs_weeks_1_and_2_are_graded(decisions, sql):
    assert decisions["available"] is True and decisions["season"] == 2026
    assert [w["week"] for w in decisions["weeks"]] == [1, 2]
    assert {w["record_source"] for w in decisions["weeks"]} == {"reconstructed"}
    assert decisions["reconstructed_weeks"][:2] == [1, 2] and "rebuilt" in decisions["note"]
    assert all(w["rosters"] == 10 for w in decisions["weeks"])
    # the regret is never negative and the submitted points are Sleeper's matchup scores
    assert all(w["regret"] >= 0 for w in decisions["weeks"])
    for w in decisions["weeks"]:
        m = sql("""select round(sum(points)::numeric, 2) as s from analytics.fct_league_matchup
                   where league_id = %s and season = 2026 and week = %s""", (SCRUBS, w["week"]))[0]["s"]
        assert w["submitted"] == pytest.approx(float(m), abs=0.011)


def test_the_weeks_add_up_to_the_season_and_the_roster_weeks_to_the_week(decisions, sql):
    tot = decisions["season_totals"]
    assert tot["weeks"] == 2 and tot["roster_weeks"] == 20
    for k in ("submitted", "app", "optimum", "regret", "edge"):
        assert tot[k] == pytest.approx(sum(w[k] for w in decisions["weeks"]), abs=0.001), k
    rows = sql("""select week, round(sum(submitted_points), 2) as submitted, round(sum(app_points), 2) as app,
                         round(sum(optimum_points), 2) as optimum, round(sum(regret), 2) as regret,
                         round(sum(app_edge), 2) as edge
                  from analytics.mart_decision_record where league_id = %s and season = 2026 and status = 'scored'
                  group by week order by week""", (SCRUBS,))
    for w, r in zip(decisions["weeks"], rows, strict=True):
        for k in ("submitted", "app", "optimum", "regret", "edge"):
            assert w[k] == pytest.approx(float(r[k]), abs=0.001), (w["week"], k)
        assert w["edge"] == pytest.approx(w["app"] - w["submitted"], abs=0.011)
        assert w["regret"] == pytest.approx(w["optimum"] - w["submitted"], abs=0.011)


def test_the_calls_line_and_table(decisions, sql):
    cal = decisions["calls"]
    n = sql("""select count(*) as n from analytics.mart_decision_calls
               where league_id = %s and season = 2026 and outcome is not null and p_win is not null""", (SCRUBS,))[0]["n"]
    assert cal["n"] == n and cal["n"] > 0 and sum(r["n"] for r in cal["table"]) == n
    assert 0 <= cal["brier"] <= 1 and 0 <= cal["won"] <= n
    cf = cal["coin_flips"]
    assert 0 < cf["n"] <= n and decisions["sentences"]["calls"] == (
        f"The coin flips landed {round(100 * cf['won'] / cf['n'])}% for the side we leaned "
        f"({round(100 * cf['expected'] / cf['n'])}% expected, {cf['n']} calls).")
    assert decisions["sentences"]["edge"].startswith("Weeks 1–2: had every team started our lineup")


def test_the_api_grade_is_the_python_twin_on_the_source_tables(decisions):
    import psycopg
    from league_lab.config import get_settings

    with psycopg.connect(get_settings().pipeline_dsn(), autocommit=True) as conn:
        g = V.load_inputs(V.frame_query(conn), 2026, [SCRUBS])
    twin = V.summary(V.grade_roster_weeks(g), V.grade_calls(g))
    assert twin["weeks"] == decisions["weeks"] and twin["season_totals"] == decisions["season_totals"]
    assert twin["calls"]["n"] == decisions["calls"]["n"] and twin["calls"]["coin_flips"] == decisions["calls"]["coin_flips"]
    assert twin["sentences"] == decisions["sentences"]


def test_a_league_we_do_not_keep_has_no_decisions(client):
    d = client.get(f"/api/record?league={TEST_LEAGUE}").json()
    assert d["available"] is False and "decisions" not in d


def test_decisions_are_unavailable_not_an_error_without_the_marts(client, monkeypatch):
    from league_lab_api import db

    real = db.missing_relations
    monkeypatch.setattr(db, "missing_relations",
                        lambda names: [n for n in names if n.startswith("mart_decision")] or real(names))
    d = client.get(f"/api/record?league={SCRUBS}").json()
    assert d["available"] is True and d["decisions"]["available"] is False and "not built" in d["decisions"]["why"]
