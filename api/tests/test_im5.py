"""IM-5 (Wave I-M): DFS on the API — projections before a file, the salary file's slate, the lineups and the upload CSV.

The salary files are SYNTHETIC (tests/fixtures/dfs/make_synthetic.py: the database's week-5 players, invented
salaries). No league, no team on any request: the routes take none."""

from __future__ import annotations

import csv
import io
import json
import logging
from pathlib import Path

import pytest
from league_lab import dfs as D
from league_lab import memo

from .conftest import needs_db

FX = Path(__file__).with_name("fixtures") / "dfs"
DK_CLASSIC = (FX / "dk_classic_week5.csv").read_text()
DK_SHOWDOWN = (FX / "dk_showdown_week5.csv").read_text()
FD_FULL = (FX / "fd_full_week5.csv").read_text()


def _slate(client, text: str, **params) -> dict:
    r = client.post("/api/dfs/slate", content=text.encode(), params=params, headers={"content-type": "text/csv"})
    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == "no-store"
    return r.json()


@needs_db
@pytest.mark.parametrize("site", ["dk", "fd"])
def test_projections_before_a_file(client, site):
    r = client.get("/api/dfs/projections", params={"site": site, "week": 5, "limit": 1000})
    assert r.status_code == 200, r.text
    b = r.json()
    assert (b["site"], b["week"]) == (site, 5)
    ps = b["players"]
    assert len(ps) > 300
    projs = [p["proj"] for p in ps]
    assert projs == sorted(projs, reverse=True)
    positions = {p["position"] for p in ps}
    assert positions == ({"QB", "RB", "WR", "TE", "DEF", "K"} if site == "dk" else {"QB", "RB", "WR", "TE", "DEF"})
    top = ps[0]
    assert top["p10"] <= top["proj"] <= top["p90"] and top["opponent"]
    assert b["reference"] == ("ppr" if site == "dk" else "scrubs")
    assert any("+3 at 300 passing yards" in w for w in b["scoring"]) == (site == "dk")


@needs_db
def test_projections_default_week_and_position_filter(client):
    b = client.get("/api/dfs/projections", params={"site": "dk", "position": "TE"}).json()
    assert b["week"] == 4 and {p["position"] for p in b["players"]} == {"TE"}
    assert client.get("/api/dfs/projections", params={"site": "yahoo"}).status_code == 400


@needs_db
def test_dk_full_ppr_prices_more_than_fd_half_ppr_for_a_receiver(client):
    dk = {p["key"]: p for p in client.get("/api/dfs/projections", params={"site": "dk", "week": 5, "limit": 1000}).json()["players"]}
    fd = {p["key"]: p for p in client.get("/api/dfs/projections", params={"site": "fd", "week": 5, "limit": 1000}).json()["players"]}
    nacua = "00-0039075"
    assert dk[nacua]["proj"] > fd[nacua]["proj"] + 2


@needs_db
def test_dk_classic_slate(client):
    b = _slate(client, DK_CLASSIC)
    assert (b["site"], b["contest"], b["week"], b["cap"]) == ("dk", "dk_classic", 5, 50_000)
    assert any("Week 5: the week whose games the file lists." == n for n in b["notes"])
    assert len(b["games"]) == 15
    c = b["counts"]
    assert c["on_file"] == c["matched"] + c["unmatched"] and c["matched"] >= 560
    why = {u["name"]: u["reason"] for u in b["unmatched"]}
    assert why["Zzyzx Notaplayer"] == "no WR of that name on MIN in our players"
    moved = [u for u in b["unmatched"] if u["team"] == "MIA" and "we have that name as WR on LA" in u["reason"]]
    assert len(moved) == 1                                    # the "traded" receiver: listed, never guessed
    by = {p["name"]: p for p in b["players"]}
    for spelled in ("Marvin Harrison", "AJ Brown", "CJ Stroud", "TJ Hockenson"):
        assert spelled in by, spelled                         # the sites' spellings match ours
    p = by["Amon-Ra St. Brown"]
    assert p["pts_per_k"] == pytest.approx(round(p["proj"] / (p["salary"] / 1000), 2), abs=0.011)
    assert p["ceil_per_k"] == pytest.approx(round(p["p90"] / (p["salary"] / 1000), 2), abs=0.011)
    assert set(b["fit"]) == {"QB", "RB", "WR", "TE", "DEF"} and all(b["fit"][k] for k in b["fit"])
    assert b["fit"]["WR"]["slope_per_1000"] > 0 and "each $1,000 of salary buys" in b["fit"]["WR"]["words"]
    und, ovr = b["undervalued"], b["overpriced"]
    assert und and ovr and not set(und) & set(ovr)
    keyed = {p["key"]: p for p in b["players"]}
    gaps = [keyed[k]["value_gap"] for k in und]
    assert gaps == sorted(gaps, reverse=True) and all(g >= 1 for g in gaps)
    assert all(keyed[k]["value_gap"] <= -1 for k in ovr)
    assert all(keyed[k]["reason"] for k in und + ovr)
    assert not any(keyed[k]["out"] for k in und + ovr)
    words = " ".join(keyed[k]["reason"] for k in und + ovr)
    for never in ("lock", "guaranteed", "free money", "beat"):
        assert never not in words.lower()


@needs_db
def test_fd_full_slate(client):
    b = _slate(client, FD_FULL)
    assert (b["site"], b["contest"], b["week"], b["cap"]) == ("fd", "fd_full", 5, 60_000)
    assert b["counts"]["unmatched"] <= 5 and b["counts"]["matched"] >= 560
    assert not any(p["position"] == "K" for p in b["players"])


@needs_db
def test_dk_showdown_slate_one_line_for_the_slate(client):
    b = _slate(client, DK_SHOWDOWN)
    assert b["contest"] == "dk_showdown" and len(b["games"]) == 1
    assert set(b["fit"]) == {"ALL"}
    assert all(p["cpt_salary"] == int(p["salary"] * 1.5) for p in b["players"])


@needs_db
def test_json_body_and_week_override(client):
    r = client.post("/api/dfs/slate", json={"text": DK_CLASSIC}, params={"week": 4})
    assert r.status_code == 200 and r.json()["week"] == 4
    # IM-5 fix: only this week (4 under the pinned clock) and the next
    r = client.post("/api/dfs/slate", json={"text": DK_CLASSIC}, params={"week": 9})
    assert r.status_code == 400 and r.json()["code"] == "bad_week"
    assert r.json()["error"] == "DFS shows this week (week 4) and next week (week 5) only."


@needs_db
def test_hostile_files_are_refused_in_words(client):
    r = client.post("/api/dfs/slate", content=(FX / "hostile_wrong_headers.csv").read_bytes())
    assert r.status_code == 400 and r.json()["code"] == "not_a_salary_file"
    assert r.json()["error"].startswith("That does not look like a DraftKings or FanDuel salary file")
    # IM-5 fix: over the Guard's upload limit (LEAGUE_LAB_MAX_UPLOAD_KB, 2 MB): the Guard's 413 in words, before the
    # route; between our 1 MB cap and the Guard's: ours (the screen says the same sentence for either, on a 413)
    big = (DK_CLASSIC * 60).encode()
    assert len(big) > 3_000_000
    r = client.post("/api/dfs/slate", content=big)
    assert r.status_code == 413 and r.json()["code"] == "too_large"
    assert r.json()["error"] == "That is more than this server takes in one request."
    mid = (DK_CLASSIC * 25).encode()
    assert 1_000_000 < len(mid) < 2_000_000
    r = client.post("/api/dfs/slate", content=mid)
    assert r.status_code == 413 and r.json()["code"] == "too_large" and "under 1 MB" in r.json()["error"]


@needs_db
def test_formula_cells_are_text_and_the_upload_neutralises_them(client):
    b = _slate(client, (FX / "hostile_formulas.csv").read_text(), week=5)     # its one game is BUF@MIA (week 11's)
    assert [s["reason"] for s in b["skipped"]] == ["its ID is not a DraftKings player id",
                                                   "its salary is not a number"]
    assert b["players"] == [] and b["unmatched"][0]["name"].startswith("=cmd")
    lu = {"slots": [{"upload_id": "=cmd|' /C calc'!A0"}, {"upload_id": "+x"}]}
    assert D.upload_csv("dk_classic", [lu]).splitlines()[1] == "'=cmd|' /C calc'!A0,'+x"


@needs_db
def test_the_file_is_never_logged(client, caplog):
    marker = "Qwertyuiop Zxcvbnm"
    text = DK_CLASSIC.replace("Zzyzx Notaplayer", marker)
    with caplog.at_level(logging.DEBUG):
        b = _slate(client, text)
    assert any(u["name"] == marker for u in b["unmatched"])
    assert not any(marker in rec.getMessage() for rec in caplog.records)


@needs_db
def test_lineups_from_the_slate(client):
    b = _slate(client, DK_CLASSIC)
    body = {"contest": b["contest"], "players": b["players"], "mode": "cash", "n": 3}
    r = client.post("/api/dfs/lineups", json=body)
    assert r.status_code == 200, r.text
    out = r.json()
    lus = out["lineups"]
    assert len(lus) == 3 and len({frozenset(s["key"] for s in lu["slots"]) for lu in lus}) == 3
    first = lus[0]
    assert [s["slot"] for s in first["slots"]] == ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "DST"]
    assert first["salary"] <= 50_000 and first["salary_left"] == 50_000 - first["salary"]
    assert first["low"] < first["proj"] < first["high"] and first["proven"]
    assert all(t < 1500 for t in out["solve_ms"])
    rows = list(csv.reader(io.StringIO(out["upload_csv"])))
    assert rows[0] == ["QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "DST"] and len(rows) == 4
    keyed = {p["key"]: p for p in b["players"]}
    assert rows[1] == [keyed[s["key"]]["site_id"] for s in first["slots"]]
    assert not any(keyed[s["key"]]["out"] for lu in lus for s in lu["slots"])
    # lock the cheapest QB, exclude the best lineup's top scorer; tournament
    qb = min((p for p in b["players"] if p["position"] == "QB" and not p["out"]), key=lambda p: p["salary"])["key"]
    top = max(first["slots"], key=lambda s: s["proj"])["key"]
    r = client.post("/api/dfs/lineups", json=body | {"n": 1, "locks": [qb], "excludes": [top], "mode": "tournament"})
    keys = {s["key"] for s in r.json()["lineups"][0]["slots"]}
    assert qb in keys and top not in keys and r.json()["mode"] == "tournament"


@needs_db
def test_showdown_and_fanduel_lineups(client):
    sd = _slate(client, DK_SHOWDOWN)
    lu = client.post("/api/dfs/lineups", json={"contest": "dk_showdown", "players": sd["players"]}).json()["lineups"][0]
    assert [s["slot"] for s in lu["slots"]] == ["CPT", "FLEX", "FLEX", "FLEX", "FLEX", "FLEX"]
    cpt = lu["slots"][0]
    p = next(x for x in sd["players"] if x["key"] == cpt["key"])
    assert cpt["upload_id"] == p["cpt_id"] and cpt["salary"] == p["cpt_salary"]
    fd = _slate(client, FD_FULL)
    lu = client.post("/api/dfs/lineups", json={"contest": "fd_full", "players": fd["players"]}).json()["lineups"][0]
    teams = [s["team"] for s in lu["slots"]]
    assert max(teams.count(t) for t in set(teams)) <= 4 and lu["salary"] <= 60_000


def test_lineups_refuse_bad_requests(client):
    for body, code in (({"contest": "x", "players": [{}]}, "bad_contest"), ({"contest": "dk_classic"}, "no_players"),
                       ({"contest": "dk_classic", "players": [{"position": "QB", "salary": "a"}]}, "bad_request"),
                       ({"contest": "dk_classic", "players": [{"position": "LB", "salary": 1}]}, "bad_player"),
                       ({"contest": "dk_classic", "players": [{"key": "a", "position": "QB", "salary": 5000}], "n": 50}, "bad_n")):
        r = client.post("/api/dfs/lineups", json=body)
        assert r.status_code == 400 and r.json()["code"] == code, (body, r.text)


def test_one_memo_region_and_the_rate_buckets():
    assert "dfs" in memo.BUDGET.regions
    from league_lab_api import dfs as api_dfs
    assert api_dfs.RATE_BUCKETS == {"/api/dfs/slate": "heavy", "/api/dfs/lineups": "heavy",
                                    "/api/dfs/projections": "read"}


# ------------------------------------------------------------------------------------------------ IM-5 fix: bounded work
def test_the_reviews_hostile_body_is_refused_fast(client):
    import time
    body = ("a,," * 333_000).encode()
    t0 = time.perf_counter()
    r = client.post("/api/dfs/slate", content=body)
    assert r.status_code == 400 and r.json()["code"] == "too_many_columns"
    assert time.perf_counter() - t0 < 1.0


def test_hostile_lineups_requests_are_refused_before_any_solve(client, monkeypatch):
    import time

    from league_lab_api import dfs as api_dfs
    called = []
    monkeypatch.setattr(api_dfs.D, "solve_lineups", lambda *a, **k: called.append(1))
    p = {"position": "WR", "salary": 3000, "proj": 5.0, "p90": 9.0, "p10": 1.0, "team": "BUF"}
    t0 = time.perf_counter()
    r = client.post("/api/dfs/lineups", json={"contest": "dk_classic",
                                               "players": [p | {"key": f"k{i}", "game": f"g{i}"} for i in range(2000)]})
    assert r.status_code == 400 and r.json()["code"] == "too_many_players" and time.perf_counter() - t0 < 1.5
    r = client.post("/api/dfs/lineups", json={"contest": "dk_classic",
                                               "players": [p | {"key": f"k{i}", "game": f"g{i}"} for i in range(17)]})
    assert r.status_code == 400 and r.json()["code"] == "too_many_games"
    r = client.post("/api/dfs/lineups", json={"contest": "dk_showdown",
                                               "players": [p | {"key": f"k{i}", "game": f"g{i % 2}"} for i in range(6)]})
    assert r.status_code == 400 and r.json()["code"] == "too_many_games"
    for bad in ({"proj": 1e9}, {"key": "x" * 41}, {"name": "n" * 81}, {"salary": -5}, {"p90": float("inf")}):
        r = client.post("/api/dfs/lineups", content=json.dumps({"contest": "dk_classic", "players": [p | {"key": "a", "game": "g"} | bad]}).replace("Infinity", "1e999"),
                        headers={"content-type": "application/json"})
        assert r.status_code == 400, bad
    assert called == []


def test_a_second_build_while_one_runs_is_told_to_wait(client, monkeypatch):
    from league_lab_api import dfs as api_dfs
    monkeypatch.setattr(api_dfs, "BUSY_WAIT_S", 0.1)
    assert api_dfs._WORK.acquire(timeout=1)
    try:
        r = client.post("/api/dfs/lineups", json={"contest": "dk_classic", "players": [
            {"key": "a", "position": "QB", "salary": 5000, "proj": 10.0, "team": "BUF", "game": "g"}]})
        assert r.status_code == 429 and r.json()["code"] == "busy" and r.headers["retry-after"] == "5"
        assert r.json()["error"] == "Another lineup is being built right now. Try again in a few seconds."
        r = client.post("/api/dfs/slate", content=DK_CLASSIC.encode())
        assert r.status_code == 429 and r.json()["code"] == "busy"
    finally:
        api_dfs._WORK.release()


@needs_db
def test_projections_only_this_week_and_the_next(client):
    assert client.get("/api/dfs/projections", params={"site": "dk", "week": 5}).status_code == 200
    r = client.get("/api/dfs/projections", params={"site": "dk", "week": 12})
    assert r.status_code == 400 and r.json()["code"] == "bad_week"
    assert client.get("/api/dfs/projections", params={"site": "fd", "week": 3}).status_code == 400
