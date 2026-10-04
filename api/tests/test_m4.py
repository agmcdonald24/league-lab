"""Wave I-G (M4): the request side follows the record.

* ``/api/record`` carries ``pricing`` on every week row (``flat`` | ``ev`` | ``mixed``) and a ``pricing`` block (``now``,
  ``by_week``, ``sentence``).
* My Week's lineup total (the on-demand path: lines priced at request time) equals the record's (the house board:
  ``ops.lineup_totals`` from ``ops.projections``) for a roster-week, under the record's mode — the frozen week 4 and
  the live week 5, whatever the clone's last build was; forced to the other mode, the dynasty's would not (the trust
  bug the mode prevents) while Scrubs (no bonus) is the same either way.
* "Sleeper's projection" (``why.market_points``) is priced like ours, in the week's mode.

needs_db on the M4 clone (``league_lab_m1``); the week-4 market line needs the Sleeper projections fixture loaded.
"""

from __future__ import annotations

import pandas as pd
import pytest
from league_lab import anyleague as A
from league_lab import scoring as S

from league_lab_api import db, ondemand, why
from league_lab_api.applib import cards

from .conftest import ANDREW, DYNASTY, SCRUBS, needs_db

FLAG = "LEAGUE_LAB_EV_PRICING"
ALLEN = "00-0034857"


@pytest.fixture(autouse=True)
def _record_of_the_database(monkeypatch):
    """The API's own reader (registered when ondemand is imported), a fresh cache, the env unset: the record decides."""
    monkeypatch.delenv(FLAG, raising=False)
    S.set_record_reader(ondemand._pricing_rows)
    yield
    S.set_record_reader(ondemand._pricing_rows)


def _has_column(sql) -> bool:
    return bool(sql("""select 1 as x from information_schema.columns where table_schema = 'ops'
                       and table_name = 'projections' and column_name = 'pricing'"""))


def _week_label(sql, league: str, season: int, week: int) -> str:
    rows = sql("""select coalesce(bool_or(pricing = 'ev'), false) as ev from ops.projections
                  where league_id = %s and season = %s and week = %s and position in ('QB', 'RB', 'WR', 'TE')""",
               (league, season, week))
    return "ev" if rows and rows[0]["ev"] else "flat"


# ------------------------------------------------------------------------------ /api/record
@needs_db
@pytest.mark.parametrize("league", [DYNASTY, SCRUBS])
def test_record_says_how_each_week_was_priced(client, sql, league):
    if not _has_column(sql):
        pytest.skip("ops.projections has no pricing column here (before the first Wave I-G build)")
    d = client.get(f"/api/record?league={league}").json()
    assert d["available"] is True and set(d["pricing"]) == {"now", "by_week", "sentence"}
    labels = {str(r["week"]): r["pricing"] for r in d["weeks"]}
    assert all(r["pricing"] in ("flat", "ev", "mixed") for r in d["weeks"])
    assert d["pricing"]["by_week"] == dict(sorted(labels.items()))
    mart = sql("""select week, pricing from analytics.mart_projection_record where league_id = %s and scope = 'week'""", (league,))
    assert {str(r["week"]): r["pricing"] for r in mart} == labels
    newest = sql("""select coalesce(bool_or(pricing = 'ev'), false) as ev from ops.projections where league_id = %s
                    and position in ('QB', 'RB', 'WR', 'TE')
                    and fitted_at = (select max(fitted_at) from ops.projections where league_id = %s)""", (league, league))
    assert d["pricing"]["now"] == ("ev" if newest[0]["ev"] else "flat")
    if league == SCRUBS:                                    # no bonus to price: always flat, nothing to say
        assert d["pricing"]["now"] == "flat" and set(labels.values()) <= {"flat"} and d["pricing"]["sentence"] is None
    assert d["pricing"]["sentence"] == S.record_pricing_sentence({int(k): v for k, v in labels.items()}, d["pricing"]["now"])


def test_record_pricing_before_the_column_is_flat(monkeypatch):
    def broken(sql, params=(), **kw):
        raise RuntimeError('column "pricing" does not exist')
    monkeypatch.setattr(ondemand, "query", broken)
    weeks = [{"week": 4, "position": "QB"}, {"week": 4, "position": "ALL", "pricing": None}]
    out = ondemand.record_pricing(DYNASTY, 2026, weeks)
    assert out == {"pricing": {"now": "flat", "by_week": {"4": "flat"}, "sentence": None}}
    assert [w["pricing"] for w in weeks] == ["flat", "flat"]


# ------------------------------------------------------------------------------ My Week = the record, per mode
def _house_total(sql, league, season, week, roster) -> float:
    rows = sql("""select lineup_value from ops.lineup_totals where league_id = %s and season = %s and week = %s
                  and roster_id = %s and not is_realised order by run_at desc limit 1""", (league, season, week, roster))
    if not rows:
        pytest.skip(f"no lineup total for {league} week {week}")
    return float(rows[0]["lineup_value"])


@needs_db
@pytest.mark.parametrize("week", [4, 5])
@pytest.mark.parametrize("league", [DYNASTY, SCRUBS])
def test_my_week_total_equals_the_records_under_each_mode(sql, monkeypatch, league, week):
    """The on-demand lineup (lines priced now, NFL-wide board) and the house board's total for the same roster-week
    agree under the record's mode (the env unset); forcing the other mode moves the dynasty's on-demand total away
    from the record, never Scrubs'."""
    if not _has_column(sql) or not A.nfl_wide_ready(db.query, 2026, week):
        pytest.skip("the clone has no pricing column / no NFL-wide tables for the week")
    monkeypatch.setenv(A.BOARD_SOURCE_ENV, "nfl_wide")
    team, season = ANDREW[league], cards.league_season(league)
    mart = cards.lineup_rows(league, season, week, team)
    if mart.empty:
        pytest.skip(f"no house lineup for week {week}")
    as_of = pd.Timestamp(mart.loc[mart["role"] == "starter", "as_of"].dropna().iloc[0]).to_pydatetime()
    house = _house_total(sql, league, season, week, team)
    S.clear_pricing_cache()
    od = A.lineup_rows(db.query, league, team, week, as_of=as_of)
    total = float(od.rows.loc[od.rows["role"] == "starter", "lineup_value"].iloc[0])
    assert total == pytest.approx(house, abs=0.005), (league, week, _week_label(sql, league, season, week))
    other = "0" if _week_label(sql, league, season, week) == "ev" else "1"
    monkeypatch.setenv(FLAG, other)
    A.clear_priced()
    forced = A.lineup_rows(db.query, league, team, week, as_of=as_of)
    ftotal = float(forced.rows.loc[forced.rows["role"] == "starter", "lineup_value"].iloc[0])
    if league == SCRUBS:
        assert ftotal == pytest.approx(house, abs=0.005)
    else:
        assert abs(ftotal - house) > 0.05, "forcing the other mode should move a bonus league"


# ------------------------------------------------------------------------------ "Sleeper's projection"
def _allen_market(monkeypatch) -> dict:
    """The market mart holding Josh Allen's week-4 line from the Sleeper projections fixture (invented: 267 passing
    yards, 2.0 passing TDs), the way the API reads it (``why.MARKET_SQL``)."""
    import json
    from pathlib import Path

    fx = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "sleeper_projections" / "projections_2026_w04.json"
    item = next(i for i in json.loads(fx.read_text()) if i.get("player_id") == "4984")
    # = league_lab.ingest.sleeper_projections.STAT_COLUMNS (that module needs httpx, which the API's env does not carry)
    cols = {"pass_att": "attempts", "pass_cmp": "completions", "rush_att": "carries", "rec_tgt": "targets",
            **{k: S._PY_EXPR[k][0] for k in S.SLEEPER_STAT_MAP}, **{k: e for k, (e, _) in S.SLEEPER_LONG_TD_MAP.items()}}
    line = {c: float(item["stats"][k]) for k, c in cols.items() if isinstance(item["stats"].get(k), (int, float))}
    row = {"gsis_id": ALLEN, "sleeper_id": "4984", "season": 2026, "week": 4, "position": "QB", "team": "BUF",
           "opponent": "NE", "fetched_at": "2026-10-01T12:15:00Z", **line}
    df = pd.DataFrame([row])
    monkeypatch.setattr(why, "missing_relations", lambda names: [])
    monkeypatch.setattr(why, "query", lambda sql, params=(): df[df["gsis_id"].isin(params[2])].copy())
    return {**line, "position": "QB"}


def test_sleeper_projection_is_priced_in_the_weeks_mode(monkeypatch):
    """Josh Allen's market line for week 4 in the dynasty: flat in a flat week = the old all-or-nothing price
    (``compute_points``, 31.58); at the odds in an EV week (33.20: a 300-yard bonus within reach, a long TD's share);
    the record decides per week, the env overrides; Scrubs (no bonus) 25.50 either way; a K stays flat."""
    old = _allen_market(monkeypatch)
    dyn = A.league_scoring(A.sleeper().league(DYNASTY))[0]
    scr = A.league_scoring(A.sleeper().league(SCRUBS))[0]
    S.set_record_reader(lambda: [(2026, 4, pd.Timestamp("2026-10-01T19:25Z"), False),
                                 (2026, 5, pd.Timestamp("2026-10-04T07:00Z"), True)])
    flat = why.market_points(2026, 4, [ALLEN], dyn)[ALLEN]            # week 4 frozen flat: its own label
    assert flat == round(S.compute_points(old, dyn), 2) == 31.58          # the pre-I-G number, to the cent
    S.set_record_reader(lambda: [(2026, 4, pd.Timestamp("2026-10-04T07:00Z"), True)])
    ev = why.market_points(2026, 4, [ALLEN], dyn)[ALLEN]
    assert ev == 33.2                                                     # before / after (the hand-back)
    monkeypatch.setenv(FLAG, "0")                                         # the env overrides the record
    assert why.market_points(2026, 4, [ALLEN], dyn)[ALLEN] == 31.58
    for v in ("0", "1"):
        monkeypatch.setenv(FLAG, v)
        assert why.market_points(2026, 4, [ALLEN], scr)[ALLEN] == round(S.compute_points(old, scr), 2) == 25.5
