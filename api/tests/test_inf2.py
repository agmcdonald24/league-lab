"""INF-2 (Wave I-J, the memory diet): the answers stay the same while the server keeps less.

* the fetch interns every text value (`db.intern_strings`): the frame is equal, value for value and dtype for dtype,
  and one gsis_id is one object in two frames;
* one Board per week (`anyleague.load_board`): two leagues priced one after the other share the Board object, and a
  league priced on the shared Board gets the numbers a fresh Board gives;
* the caches are regions of one budget (`league_lab.memo`) and `/api/status` says so.
The budget's eviction order itself is tested without a database: `tests/test_memo.py`.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from league_lab import anyleague as A
from league_lab import memo

from league_lab_api import db
from league_lab_api.applib import cards

from .conftest import DYNASTY, SCRUBS, needs_db


# ------------------------------------------------------------------------------ 1. interning keeps frames equal
def _fetched(rows: list[tuple], cols: list[str]) -> pd.DataFrame:
    """What `db._run` builds from `cur.fetchall()` before its conversions."""
    return pd.DataFrame(rows, columns=cols)


def _fresh(s: str) -> str:
    """A string equal to `s` but a new object (what psycopg hands back for every row)."""
    return "".join(list(s))


def test_interning_keeps_the_frame_equal_and_shares_the_strings():
    rows = [(_fresh("00-0037840"), "WR", 1.5, None, {"a": 1}, None),
            (_fresh("00-0037840"), _fresh("WR"), None, _fresh("Q"), None, True),
            (_fresh("00-0036322"), None, 3.25, _fresh("Q"), {"b": 2}, False)]
    cols = ["gsis_id", "position", "proj", "report_status", "payload", "flag"]
    before = _fetched(rows, cols)
    after = db.intern_strings(_fetched(rows, cols))
    pd.testing.assert_frame_equal(after, before)                       # values, NULLs, dtypes, index
    assert list(after.dtypes) == list(before.dtypes)
    assert after["gsis_id"].iloc[0] is after["gsis_id"].iloc[1]         # one object for one id
    other = db.intern_strings(_fetched([(_fresh("00-0037840"), "RB", 0.0, None, None, None)], cols))
    assert other["gsis_id"].iloc[0] is after["gsis_id"].iloc[0]         # ... across frames too
    assert after["position"].isna().iloc[2] and pd.isna(after["report_status"].iloc[0])
    assert after["payload"].iloc[1] is None                             # an object column's NULL stays None
    # an object column that is not all text is left alone (dicts, bools with NULLs)
    assert after["payload"].iloc[0] == {"a": 1} and after["flag"].tolist() == before["flag"].tolist()


def test_interning_object_column_of_text_keeps_none():
    df = pd.DataFrame({"s": np.array([_fresh("KC"), None, _fresh("KC")], dtype=object)}, dtype=object)
    before = df.copy()
    db.intern_strings(df)
    pd.testing.assert_frame_equal(df, before)
    assert df["s"].iloc[1] is None and df["s"].iloc[0] is df["s"].iloc[2]


@needs_db
def test_the_fetch_interns_and_the_cache_hands_out_equal_copies():
    sql = "select gsis_id, position from analytics.dim_player where gsis_id = any(%s) order by gsis_id"
    ids = ["00-0037840", "00-0036322", "00-0033873"]
    a = db.query(sql, (ids,))
    b = db.query(sql + " ", (ids,))                                     # another SQL text: another fetch
    assert len(a) == 3
    pd.testing.assert_frame_equal(a, b)
    assert all(x is y for x, y in zip(a["gsis_id"], b["gsis_id"], strict=True))
    c = db.query(sql, (ids,))                                           # the cached one: an equal, separate frame
    c["extra"] = 1
    assert "extra" not in db.query(sql, (ids,)).columns
    assert memo.BUDGET.regions["sql"].nbytes > 0


# ------------------------------------------------------------------------------ 2. one Board per week, shared
@needs_db
def test_two_leagues_priced_one_after_the_other_share_the_board():
    season = cards.league_season(SCRUBS)
    week = cards.decision_week(season)
    sl = A.sleeper()
    priced = {}
    for lid in (SCRUBS, DYNASTY):
        scoring, slots = A.league_scoring(sl.league(lid))
        priced[lid] = A.price_week(db.query, lid, scoring, slots, season, week)
    assert priced[SCRUBS].board is priced[DYNASTY].board                 # one Board for the week
    assert A.load_board(db.query, season, week) is priced[SCRUBS].board
    assert len(A._boards) == 1
    # the shared Board gives the numbers a fresh one gives (nothing priced on it wrote into it)
    fresh = A.load_board(db.query, season, week, cache=False)
    assert fresh is not priced[SCRUBS].board
    for lid in (SCRUBS, DYNASTY):
        scoring, slots = A.league_scoring(sl.league(lid))
        again = A.price_board(fresh, lid, scoring, A.kd_starts(slots), units=A.unit_starts(slots))
        pd.testing.assert_series_equal(again.proj, priced[lid].proj)
        pd.testing.assert_frame_equal(again.ranges, priced[lid].ranges)
        assert again.reference == priced[lid].reference
    pd.testing.assert_frame_equal(fresh.line, priced[SCRUBS].board.line)
    # a Priced in the budget is the league's own frames: the Board is counted once, in `boards`
    assert memo.sizeof(priced[SCRUBS]) < memo.sizeof(priced[SCRUBS].board)


# ------------------------------------------------------------------------------ 3. the operator sees it
@needs_db
def test_status_reports_memory(client):
    m = client.get("/api/status").json()["memory"]
    assert m["rss_mb"] > 50 and m["budget_mb"] == pytest.approx(memo.BUDGET.limit / 1048576, abs=0.1)
    assert {"sql", "boards", "priced", "ros", "league_weeks", "contexts", "decisions", "research_priced",
            "research_memo", "about", "stats", "scoring_checks"} <= set(m["regions"])
    assert m["cache_mb"] == pytest.approx(sum(m["regions"].values()), abs=0.5)
