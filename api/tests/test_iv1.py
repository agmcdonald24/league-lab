"""IV-1 (Wave I-V): the API follows the data. Every statement passes db._run, which makes a stored projection table's
read live only where an overlay exists and holds rows (league_lab.live_week); no overlay, an empty one, or a catalog
that cannot be read: the statement unchanged — never a 500 for it. Read once per publication. No database."""

from __future__ import annotations

import psycopg
import pytest
from league_lab import live_week as LW

from league_lab_api import db

Q = "select proj_points from ops.projection_ranges where season = %s and week = %s"


class _Cur:
    def __init__(self, rows):
        self.rows, self.seen = list(rows), []

    def execute(self, q, params=None):
        self.seen.append(q)

    def fetchone(self):
        return self.rows.pop(0)


@pytest.fixture(autouse=True)
def _fresh():
    db._live.clear()
    yield
    db._live.clear()


def test_no_overlay_table_runs_the_statement_unchanged():
    cur = _Cur([(False,) * len(LW.LIVE_TABLES)])            # the deploy before the nightly that creates them
    assert db._live_sql(cur, Q) == Q
    assert db._live_sql(_Cur([]), Q) == Q                     # read once (the region holds the answer)


def test_empty_overlays_run_the_statement_unchanged():
    cur = _Cur([(True,) * len(LW.LIVE_TABLES), (False,) * len(LW.LIVE_TABLES)])
    assert db._live_sql(cur, Q) == Q


def test_an_overlay_with_rows_makes_the_read_live():
    cur = _Cur([(True,) * len(LW.LIVE_TABLES), (False, False, True, False, False)])
    out = db._live_sql(cur, Q)
    assert LW.relation("ops.projection_ranges") + " as projection_ranges" in out


def test_a_catalog_error_is_the_stored_rows_never_a_500():
    class Broken(_Cur):
        def execute(self, q, params=None):
            raise psycopg.errors.UndefinedTable("relation does not exist")
    assert db._live_sql(Broken([]), Q) == Q


def test_statements_that_read_no_projection_table_are_never_inspected():
    cur = _Cur([])
    assert db._live_sql(cur, "select 1 from analytics.mart_player_week_projections") == \
        "select 1 from analytics.mart_player_week_projections" and cur.seen == []


def test_the_answer_is_dropped_with_a_new_publication():
    from league_lab import memo
    db._live.put("active", frozenset({"ops.projections"}))
    memo.drop_published()
    assert db._live.get("active") is None


def test_a_player_cleared_after_a_frozen_weeks_kickoff_is_told_what_is_true(monkeypatch):
    """The sentence under the switch `week`: in a week whose first game has kicked off no update brings his number
    (the pinned clock is 2026-10-03 16:00 UTC: week 4 kicked off Oct 2, week 5 kicks off Oct 9)."""
    import pandas as pd

    from league_lab_api import rankings_api as RA
    monkeypatch.setattr(RA, "query", lambda sql, params=(): pd.DataFrame({"k": [pd.Timestamp("2026-10-02T00:15Z")]}))
    assert RA._week_frozen(2026, 4)
    monkeypatch.setattr(RA, "query", lambda sql, params=(): pd.DataFrame({"k": [pd.Timestamp("2026-10-09T00:15Z")]}))
    assert not RA._week_frozen(2026, 5)
    words = RA.BACK_FROZEN_WORDS.format(why="Questionable (hamstring) · Sleeper, Oct 9")
    assert words == ("His status changed after this week's numbers were set at its first kickoff (Questionable "
                     "(hamstring) · Sleeper, Oct 9); there is no number for him this week.")
    assert RA._out_words({"player_name": "Caleb Williams", "code": "BACK", "words": words}) == \
        "Williams has no number this week: " + words
    old = RA.BACK_WORDS.format(why="cleared to play")
    assert RA._out_words({"player_name": "Caleb Williams", "code": "BACK", "words": old}).endswith("until the next update: " + old)
