"""JB-1 (Wave J-B): `/api/record` `history.gap` (gp1.0) — the table absent (the hours between a deploy and the refresh),
unreadable, empty and filled. Never a 500, never an empty list for "could not read"."""

from __future__ import annotations

import pandas as pd
import pytest

from league_lab_api import h2h_api

from .conftest import SCRUBS, needs_db
from .test_iz1 import graded_rows

GAP_ROWS = pd.DataFrame([{"league_id": SCRUBS, "family": "position × tier", "slice": s, "rank": i + 1, "n": 1000 - 100 * i,
                          "row_share": 0.1, "gap": 0.3 - 0.05 * i, "gap_lo": 0.1, "gap_hi": 0.5, "share": 0.3 - 0.04 * i,
                          "share_lo": 0.1, "share_hi": 0.4, "bias_ours": 0.2, "bias_sleeper": -0.1, "mae_ours": 4.5,
                          "mae_sleeper": 4.2, "calls": 300, "calls_ours_right": 0.45, "n_population": 20000,
                          "excess_total": 3000.0, "rule": "gp1.0", "built_at": pd.Timestamp("2026-10-14T12:00Z")}
                         for i, s in enumerate(["RB top-12", "WR 13-24", "WR top-12", "TE top-12", "RB 13-24", "WR 25-36"])])


def fake(h2h_rows: pd.DataFrame, gap: pd.DataFrame | None, gap_present: bool = True, gap_boom: bool = False):
    def q(sql, params=(), **_kw):
        if sql == h2h_api.EXISTS_SQL:
            return pd.DataFrame([{"present": True}])
        if sql == h2h_api.ROWS_SQL:
            return h2h_rows.copy()
        if gap_boom:
            raise RuntimeError("could not read")
        if sql == h2h_api.GAP_EXISTS_SQL:
            return pd.DataFrame([{"present": gap_present}])
        return gap.copy() if gap is not None else GAP_ROWS.iloc[0:0].copy()
    return q


@pytest.mark.parametrize("kw,status", [({"gap_present": False}, "unavailable"), ({"gap_boom": True}, "unavailable"),
                                       ({}, "none")])
def test_gap_absent_unreadable_or_empty(monkeypatch, kw, status):
    monkeypatch.setattr(h2h_api, "query", fake(graded_rows(), None, **kw))
    h = h2h_api.history(SCRUBS)
    assert h["status"] == "graded" and h["gap"] == {"available": False, "status": status}


def test_gap_rows_are_the_tables(monkeypatch):
    monkeypatch.setattr(h2h_api, "query", fake(graded_rows(), GAP_ROWS))
    g = h2h_api.history(SCRUBS)["gap"]
    assert g["available"] and g["rule"] == "gp1.0" and g["player_weeks"] == 20000
    assert g["excess_per_player_week"] == pytest.approx(0.15)
    assert [r["slice"] for r in g["rows"]] == GAP_ROWS["slice"].tolist()
    assert g["rows"][0] == {"slice": "RB top-12", "player_weeks": 1000, "share_of_rows": 0.1, "gap": 0.3, "gap_lo": 0.1,
                            "gap_hi": 0.5, "share": 0.3, "share_lo": 0.1, "share_hi": 0.4, "bias_ours": 0.2,
                            "bias_sleeper": -0.1, "close_calls": 300, "close_calls_ours_right": 0.45}


def test_no_history_means_no_gap_block(monkeypatch):
    monkeypatch.setattr(h2h_api, "query", fake(graded_rows().iloc[0:0], GAP_ROWS))
    assert "gap" not in h2h_api.history(SCRUBS)


@needs_db
@pytest.mark.parametrize("state", ["absent", "unreadable", "empty", "filled"])
def test_record_answers_with_the_gap_in_every_state(client, monkeypatch, state):
    gap = GAP_ROWS if state == "filled" else None
    monkeypatch.setattr(h2h_api, "query", fake(graded_rows(), gap, gap_present=state != "absent", gap_boom=state == "unreadable"))
    r = client.get(f"/api/record?league={SCRUBS}")
    assert r.status_code == 200, r.text
    g = r.json()["history"]["gap"]
    assert g["status"] == {"absent": "unavailable", "unreadable": "unavailable", "empty": "none", "filled": "graded"}[state]


@needs_db
def test_record_with_the_real_tables_never_fails(client):
    r = client.get(f"/api/record?league={SCRUBS}")
    assert r.status_code == 200
    h = r.json()["history"]
    assert h["status"] in ("unavailable", "none", "graded")
    if h["status"] == "graded":
        assert h["gap"]["status"] in ("unavailable", "none", "graded")
