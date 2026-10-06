"""IN-4 (Wave I-N): DFS without the homework on the API — the board's context (the matchup through IN-3's
``matchup_board.matchup_context``, faked here with the brief's exact shape; the role trend; the betting line),
"Worth a look", the published slates (``dfs/slates/``: naming, a past week, a hostile id, an unreadable file listed
and never served), lineups from a published ``slate_id`` with stacks and exposure, the rate buckets.

The salary files are the SYNTHETIC IM-5 fixtures (tests/fixtures/dfs/make_synthetic.py); no real salary file ships."""

from __future__ import annotations

import shutil
import sys
import types
from pathlib import Path

import pytest
from league_lab import memo

from .conftest import needs_db

FX = Path(__file__).with_name("fixtures") / "dfs"


@pytest.fixture
def slates(tmp_path, monkeypatch):
    """A published-slates folder: two good files for week 5 (next week at the pinned clock), a past week's, a bad name,
    a DraftKings file named FanDuel, a file that is not a salary file, a README."""
    from league_lab_api import dfs as api_dfs
    d = tmp_path / "slates"
    d.mkdir()
    shutil.copy(FX / "dk_classic_week5.csv", d / "2026-w05-dk.csv")
    shutil.copy(FX / "fd_full_week5.csv", d / "2026-w05-fd-main.csv")
    shutil.copy(FX / "dk_classic_week5.csv", d / "2026-w03-dk.csv")
    shutil.copy(FX / "dk_classic_week5.csv", d / "2026-w05-fd-alt.csv")
    shutil.copy(FX / "hostile_wrong_headers.csv", d / "2026-w05-dk-junk.csv")
    (d / "salaries.csv").write_text("Name,Salary\nx,1\n")
    (d / "README.md").write_text("how to publish\n")
    monkeypatch.setenv("LEAGUE_LAB_DFS_SLATES", str(d))
    api_dfs.reset_published()
    for name in ("dfs_published", "dfs_context"):
        memo.BUDGET.regions[name].clear()
    yield d
    api_dfs.reset_published()
    memo.BUDGET.regions["dfs_published"].clear()


def _fake_matchups(monkeypatch, *, cb_tone="favorable", certainty="likely"):
    """IN-3's module, faked with the brief's exact shape: every receiver faces a soft corner and a soft defense."""
    import league_lab_api

    def matchup_context(season, week, gsis_ids=None):
        return {g: {"opponent": "KC", "home": True,
                    "defense": {"tone": "favorable", "tough_rank": 28, "n_ranked": 32,
                                "words": "They give up the 5th-most points to his position."},
                    "cb": {"tone": cb_tone, "certainty": certainty, "corner": "J. Doe", "corner_rank": 70,
                           "shutdown": cb_tone == "difficult", "words": "Likely across from J. Doe (70th of 80)."},
                    "tone": "favorable", "words": "A soft matchup."} for g in (gsis_ids or [])}
    fake = types.ModuleType("league_lab_api.matchup_board")
    fake.matchup_context = matchup_context
    monkeypatch.setitem(sys.modules, "league_lab_api.matchup_board", fake)
    monkeypatch.setattr(league_lab_api, "matchup_board", fake, raising=False)


# ------------------------------------------------------------------------------------------------ the board's context
@needs_db
def test_board_with_context_and_no_matchup_module(client, monkeypatch):
    monkeypatch.setitem(sys.modules, "league_lab_api.matchup_board", None)      # an import of it fails
    b = client.get("/api/dfs/projections", params={"site": "dk", "week": 5, "limit": 1000}).json()
    m = b["context_meta"]
    assert m["matchup"] is False and m["matchup_words"] == "Matchup: not available here."
    assert m["lines"] is True                                     # 2026 week 5: 15 of 15 games have a line
    assert m["forecast"] is False                                 # not in a relation the site reads (docs/DFS.md)
    assert m["projection"]["corner"]["WR"] is False and m["projection"]["defense"]["WR"] is True
    sigs = [s for p in b["players"] for s in p["context"]]
    kinds = {s["signal"] for s in sigs}
    assert {"game", "role"} <= kinds and "corner" not in kinds and "defense" not in kinds
    assert all(s["projection_words"] == ("In the projection" if s["in_projection"] else "Not in the projection")
               for s in sigs)
    assert b["worth_a_look"] == {}                                # nothing outside the projection without the corner
    dst = [p for p in b["players"] if p["position"] in ("DEF", "K")]
    assert dst and all(p["context"] == [] for p in dst)


@needs_db
def test_board_with_the_matchup_signal(client, monkeypatch):
    _fake_matchups(monkeypatch)
    memo.BUDGET.regions["dfs"].clear()
    b = client.get("/api/dfs/projections", params={"site": "dk", "week": 5, "limit": 1000}).json()
    assert b["context_meta"]["matchup"] is True and b["context_meta"]["matchup_words"] is None
    wr = [p for p in b["players"] if p["position"] == "WR"]
    corner = [s for p in wr for s in p["context"] if s["signal"] == "corner"]
    assert corner and all(not s["in_projection"] and s["projection_words"] == "Not in the projection" for s in corner)
    look = b["worth_a_look"]
    assert set(look) == {"WR"} and 0 < len(look["WR"]) <= 8
    by = {p["key"]: p for p in b["players"]}
    projs = [by[k]["proj"] for k in look["WR"]]
    assert projs == sorted(projs, reverse=True)
    first = by[look["WR"][0]]
    assert first["worth"] and first["worth_reasons"][0].endswith("(not in the projection)")
    # an unclear corner never counts: no list
    _fake_matchups(monkeypatch, certainty="unclear")
    b2 = client.get("/api/dfs/projections", params={"site": "dk", "week": 5, "limit": 1000}).json()
    assert b2["worth_a_look"] == {}


# ------------------------------------------------------------------------------------------------ published slates
@needs_db
def test_published_slates_listed(client, slates):
    r = client.get("/api/dfs/slates")
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["week"] == 4                                         # the pinned clock: this week 4, next week 5
    assert [s["id"] for s in b["slates"]] == ["2026-w05-dk-main", "2026-w05-fd-main"]
    dk = b["slates"][0]
    assert (dk["site"], dk["label"], dk["contest"], dk["on_file"], dk["matched"], dk["unmatched"]) == \
        ("dk", "main", "dk_classic", 599, 597, 2)
    assert b["not_offered"] == [{"id": "2026-w03-dk-main",
                                 "reason": "week 3 of 2026: DFS offers this week (week 4) and next week only"}]
    bad = {u["file"]: u["reason"] for u in b["unreadable"]}
    assert set(bad) == {"2026-w05-dk-junk.csv", "2026-w05-fd-alt.csv", "salaries.csv"}
    assert bad["2026-w05-fd-alt.csv"] == "named FanDuel but it is a DraftKings file"
    assert bad["2026-w05-dk-junk.csv"].startswith("That does not look like a DraftKings or FanDuel salary file")
    assert bad["salaries.csv"].startswith("the name is not <season>-w<week>-<dk|fd>[-<label>].csv")
    assert [s["id"] for s in client.get("/api/dfs/slates", params={"site": "fd"}).json()["slates"]] == ["2026-w05-fd-main"]


@needs_db
def test_published_slate_is_the_uploads_answer(client, slates):
    pub = client.get("/api/dfs/slate/2026-w05-dk-main")
    assert pub.status_code == 200, pub.text
    p = pub.json()
    up = client.post("/api/dfs/slate", content=(FX / "dk_classic_week5.csv").read_bytes(), params={"week": 5},
                     headers={"content-type": "text/csv"}).json()
    assert (p["slate_id"], p["published"], p["label"]) == ("2026-w05-dk-main", True, "main")
    assert (up["slate_id"], up["published"]) == (None, False)
    for k in ("site", "contest", "week", "games", "counts", "fit", "undervalued", "overpriced", "unmatched", "skipped"):
        assert p[k] == up[k], k
    assert [(x["key"], x["proj"], x["value_gap"]) for x in p["players"]] == \
        [(x["key"], x["proj"], x["value_gap"]) for x in up["players"]]
    assert all("context" in x for x in p["players"])


@needs_db
@pytest.mark.parametrize("sid", ["2026-w03-dk-main", "2026-w05-dk-junk", "2026-w05-fd-alt", "2026-w05-dk-other",
                                 "..%2F..%2Fetc%2Fpasswd", "2026-w05-dk-main.csv", "2026-W05-dk-main", "x" * 300])
def test_published_slate_hostile_or_absent_ids(client, slates, sid):
    r = client.get(f"/api/dfs/slate/{sid}")
    assert r.status_code == 404
    if "%2F" not in sid:                                          # an encoded slash never reaches the route at all
        assert r.json()["error"] == "No published slate by that name for this week."
    assert "root:" not in r.text


@needs_db
def test_no_folder_is_no_published_slate(client, tmp_path, monkeypatch):
    from league_lab_api import dfs as api_dfs
    monkeypatch.setenv("LEAGUE_LAB_DFS_SLATES", str(tmp_path / "absent"))
    api_dfs.reset_published()
    try:
        b = client.get("/api/dfs/slates").json()
        assert (b["slates"], b["unreadable"], b["not_offered"]) == ([], [], [])
        assert client.get("/api/dfs/slate/2026-w05-dk-main").status_code == 404
    finally:
        api_dfs.reset_published()


# ------------------------------------------------------------------------------------------------ lineups from a published slate
@needs_db
def test_lineups_from_a_published_slate_with_stacks_and_exposure(client, slates):
    r = client.post("/api/dfs/lineups", json={"slate_id": "2026-w05-dk-main", "n": 3, "mode": "cash",
                                              "stack": {"with_qb": 2, "bring_back": True, "no_def_vs_qb": True},
                                              "max_exposure": 0.67})
    assert r.status_code == 200, r.text
    b = r.json()
    assert (b["contest"], b["slate_id"], len(b["lineups"])) == ("dk_classic", "2026-w05-dk-main", 3)
    assert b["stack"] == {"with_qb": 2, "bring_back": True, "no_def_vs_qb": True} and b["max_exposure"] == 0.67
    counts: dict[str, int] = {}
    for lu in b["lineups"]:
        slots = lu["slots"]
        qb = next(s for s in slots if s["slot"] == "QB")
        assert sum(1 for s in slots if s["position"] in ("WR", "TE") and s["team"] == qb["team"]) >= 2
        assert any(s["position"] in ("RB", "WR", "TE") and s["team"] == qb["opponent"] for s in slots)
        assert not any(s["position"] == "DEF" and s["opponent"] == qb["team"] for s in slots)
        for s in slots:
            counts[s["key"]] = counts.get(s["key"], 0) + 1
    assert max(counts.values()) <= 2
    assert b["upload_csv"].startswith("QB,RB,RB,WR,WR,WR,TE,FLEX,DST")


@needs_db
@pytest.mark.parametrize("body,status,code", [
    ({"slate_id": "../x", "n": 1}, 404, "not_published"),
    ({"slate_id": "2026-w03-dk-main", "n": 1}, 404, "not_published"),
    ({"slate_id": "2026-w05-dk-main", "n": 1, "stack": {"with_qb": 3}}, 400, "bad_stack"),
    ({"slate_id": "2026-w05-dk-main", "n": 1, "stack": {"with_qb": True}}, 400, "bad_stack"),
    ({"slate_id": "2026-w05-dk-main", "n": 1, "stack": {"sql": 1}}, 400, "bad_stack"),
    ({"slate_id": "2026-w05-dk-main", "n": 1, "stack": {"bring_back": "yes"}}, 400, "bad_stack"),
    ({"slate_id": "2026-w05-dk-main", "n": 2, "max_exposure": 0.05}, 400, "bad_exposure"),
    ({"slate_id": "2026-w05-dk-main", "n": 2, "max_exposure": "1"}, 400, "bad_exposure"),
    ({"slate_id": "2026-w05-dk-main", "n": 21}, 400, "bad_n"),
])
def test_lineups_refuse_bad_published_requests(client, slates, body, status, code):
    r = client.post("/api/dfs/lineups", json=body)
    assert r.status_code == status, r.text
    assert r.json()["code"] == code


# ------------------------------------------------------------------------------------------------ limits
def test_rate_buckets_and_memory_regions():
    from league_lab_api import dfs as api_dfs
    from league_lab_api.ratelimit import bucket_for
    assert bucket_for("GET", "/api/dfs/slates") == "research"
    assert bucket_for("GET", "/api/dfs/slate/2026-w05-dk-main") == "research"
    assert bucket_for("POST", "/api/dfs/slate") == "heavy" and bucket_for("POST", "/api/dfs/lineups") == "heavy"
    assert api_dfs.RATE_BUCKETS_IN4 == {"/api/dfs/slates": "research", "/api/dfs/slate/{slate_id}": "research"}
    regions = memo.BUDGET.regions
    assert regions["dfs_context"].max_entries == 4 and regions["dfs_published"].max_entries == 4
