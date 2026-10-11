"""IZ-1 (Wave I-Z): `/api/record`'s `history` block (hh1.0) and About's one sentence — the table absent (the hours between
a deploy and the refresh that brings it), unreadable, empty and filled. Never a 500, never an empty record.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from league_lab import h2h

from league_lab_api import h2h_api

from .conftest import SCRUBS, needs_db

DYNASTY = "1321941740235550720"


def graded_rows(ours_noise: float = 2.0, sleeper_noise: float = 6.0) -> pd.DataFrame:
    rng = np.random.default_rng(11)
    rows = []
    for lid in (SCRUBS, DYNASTY):
        for s in (2023, 2024, 2025, 2026):
            for w in range(1, 7 if s < 2026 else 5):
                for pos in ("QB", "RB", "WR", "TE"):
                    act = rng.gamma(2.0, 5.0, 30)
                    o, sl = act + rng.normal(0, ours_noise, 30), act + rng.normal(0, sleeper_noise, 30)
                    src = "kickoff_board" if s == 2026 else "live_walk_forward"
                    rows += [{"league_id": lid, "season": s, "week": w, "position": pos, "gsis_id": f"00-{i}",
                              "ours": o[i], "sleeper": sl[i], "actual": act[i], "ours_source": src, "ours_version": "v3.6"}
                             for i in range(30)]
    inp = h2h.Inputs(pd.DataFrame(rows), {SCRUBS: "League of Scrubs", DYNASTY: "Forever Unclean Dynasty"}, {})
    return h2h.grade(inp)


def fake_query(rows: pd.DataFrame | None, present: bool = True, boom: bool = False):
    def q(sql, params=(), **_kw):
        if boom:
            raise RuntimeError("could not read")
        if sql == h2h_api.EXISTS_SQL:
            return pd.DataFrame([{"present": present}])
        return rows.copy() if rows is not None else pd.DataFrame(columns=[c for c, _ in h2h.GRADE_COLUMNS])
    return q


# ------------------------------------------------------------------------------ the block
def test_absent_or_unreadable_is_not_available_right_now(monkeypatch):
    for kw in ({"present": False}, {"boom": True}):
        monkeypatch.setattr(h2h_api, "query", fake_query(None, **kw))
        h = h2h_api.history(SCRUBS)
        assert h == {"available": False, "status": "unavailable", "sentence": h2h_api.UNAVAILABLE, "caveat": None}
        assert "not available right now" in h["sentence"]


def test_an_empty_table_says_nothing(monkeypatch):
    monkeypatch.setattr(h2h_api, "query", fake_query(None))
    assert h2h_api.history(SCRUBS) == {"available": False, "status": "none", "sentence": None, "caveat": None}


def test_the_sentence_is_built_from_the_rows(monkeypatch):
    rows = graded_rows()
    monkeypatch.setattr(h2h_api, "query", fake_query(rows))
    h = h2h_api.history(SCRUBS)
    assert h["available"] and h["status"] == "graded" and h["scored_in"] is None and h["rule"] == "hh1.0"
    assert [p["position"] for p in h["by_position"]] == ["QB", "RB", "WR", "TE"]
    pooled = rows[(rows["league_id"] == SCRUBS) & rows["season"].isna()]
    words = {p["position"]: p["word"] for p in h["by_position"]}
    assert words == {r.position: r.verdict for r in pooled[(pooled["kind"] == "position") & (pooled["measure"] == "verdict")].itertuples()}
    cc = pooled[pooled["kind"] == "close_calls"]
    n = int(cc["n_rows"].sum())
    share = float((cc["ours"] * cc["n_rows"]).sum() / n)
    weeks = int(pooled[(pooled["kind"] == "position") & (pooled["measure"] == "error")]["n_weeks"].max())
    assert h["sentence"] == (f"Against Sleeper's free projections on {weeks} past weeks (2023, 2024, 2025, 2026), on the "
                             f"weekly miss and the order of players: ahead at QB, RB, WR and TE. On the close start / sit "
                             f"calls the two disagreed on, ours was right {round(100 * share)}% of {n:,} times.")
    assert h["caveat"].startswith("Ours: our model as it runs today, re-run on each past season with only the seasons "
                                  "before it (2026: our projections as published before kickoff). Sleeper's numbers for past")
    assert "favours Sleeper" in h["caveat"]
    assert {b["season"] for b in h["blend"]} == {2024, 2025}


def test_stored_rows_are_labelled_and_a_league_without_rows_reads_the_headline(monkeypatch):
    rows = graded_rows()
    rows["ours_source"] = "stored_walk_forward"
    monkeypatch.setattr(h2h_api, "query", fake_query(rows))
    h = h2h_api.history("999999")
    assert h["scored_in"] == "League of Scrubs" and h["league_id"] == SCRUBS
    assert "without the live board's latest adjustments" in h["caveat"]
    behind = graded_rows(ours_noise=6.0, sleeper_noise=2.0)
    monkeypatch.setattr(h2h_api, "query", fake_query(behind))
    assert ": behind at QB, RB, WR and TE." in h2h_api.history(DYNASTY)["sentence"]


def test_a_malformed_table_is_not_available_never_a_crash(monkeypatch):
    monkeypatch.setattr(h2h_api, "query", fake_query(pd.DataFrame([{"league_id": SCRUBS}])))
    assert h2h_api.history(SCRUBS)["status"] == "unavailable"


# ------------------------------------------------------------------------------ the routes
@needs_db
@pytest.mark.parametrize("league", [SCRUBS, "ref:half"])
@pytest.mark.parametrize("state", ["absent", "unreadable", "empty", "filled"])
def test_record_answers_in_every_state(client, monkeypatch, league, state):
    rows = graded_rows() if state == "filled" else None
    monkeypatch.setattr(h2h_api, "query", fake_query(rows, present=state != "absent", boom=state == "unreadable"))
    r = client.get(f"/api/record?league={league}")
    assert r.status_code == 200, r.text
    h = r.json()["history"]
    if state in ("absent", "unreadable"):
        assert h["status"] == "unavailable" and h["sentence"] == h2h_api.UNAVAILABLE
    elif state == "empty":
        assert h["status"] == "none" and h["sentence"] is None
    else:
        assert h["status"] == "graded" and h["sentence"].startswith("Against Sleeper's free projections on ")
        assert h["league_id"] == SCRUBS


@needs_db
def test_record_with_the_real_table_never_fails(client):
    r = client.get(f"/api/record?league={SCRUBS}")
    assert r.status_code == 200
    assert r.json()["history"]["status"] in ("unavailable", "none", "graded")
