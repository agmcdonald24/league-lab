"""IQ-2 (Wave I-Q): who starts -- the override list on the screens and U1 (docs/METRICS.md § "Who starts").

* the pure parts on hand-built mart rows: U1 flags both quarterbacks of a team whose listing is not the depth chart's
  first available quarterback, never a team the override list corrects; the corrected sentence, its three forms;
* ``unclear`` and ``corrected`` with and without ``analytics.mart_starter_check``: without it (a deploy before the
  nightly) ``corrected`` is {} and ``unclear`` is su1.0 exactly as before; a failed read is never an error;
* the database: where the mart is built, 2026 week 5 corrects Seattle (Darnold) and Chicago (Bagent) and flags neither;
* the screens' API: a corrected quarterback's Rankings row carries the sentence and keeps his tier; the start answer
  gives him a call like anyone else; without the mart no row carries a sentence and nothing is a 5xx.
"""

from __future__ import annotations

import pandas as pd
import pytest

from league_lab_api import rankings_api as RK
from league_lab_api import starters as S

from .conftest import needs_db

SEA_LOCK, SEA_DARNOLD, CHI_KEENUM, CHI_BAGENT = "00-0035704", "00-0034869", "00-0028986", "00-0038416"
ROUTE, START = "/api/rankings", "/api/rankings/start"


@pytest.fixture(autouse=True)
def _fresh():
    S._cache._entries.clear()
    RK.clear()
    yield
    S._cache._entries.clear()
    RK.clear()


def chk(*rows):
    cols = list(S.CHECK_COLS)
    return pd.DataFrame([dict(zip(cols, r, strict=True)) for r in rows], columns=cols)


# team, week, listed id / name, depth-available id / name, last_week, override id / name / added / since, projected, source, disputed
SEA = ("SEA", 5, SEA_LOCK, "Drew Lock", SEA_DARNOLD, "Sam Darnold", 4, SEA_DARNOLD, "Sam Darnold", "2026-10-07", 3,
       SEA_DARNOLD, "override", True)
CHI = ("CHI", 5, CHI_KEENUM, "Case Keenum", "00-0039918", "Caleb Williams", 4, CHI_BAGENT, "Tyson Bagent", "2026-10-07", 4,
       CHI_BAGENT, "override", True)
TB = ("TB", 5, "00-0041000", "Jalon Daniels", "00-0034855", "Baker Mayfield", 4, None, None, None, None, "00-0041000",
      "schedule", True)
BUF = ("BUF", 5, "00-0034857", "Josh Allen", "00-0034857", "Josh Allen", 4, None, None, None, None, "00-0034857", "schedule",
       False)
NYG = ("NYG", 5, "00-0031800", "Jameis Winston", "00-0031800", "Jameis Winston", 4, "00-0040000", "Jaxson Dart",
       "2026-10-01", None, "00-0040000", "override", False)


def test_u1_flags_a_disputed_listing_never_a_corrected_team():
    f = S.disputed_from(chk(SEA, CHI, TB, BUF))   # (IQ-2's rows: SEA / CHI by the old override; IW-1 treats 'data' alike)
    assert set(f) == {"00-0041000", "00-0034855"}                      # Tampa Bay only: SEA and CHI are corrected
    assert f["00-0041000"]["role"] == "listed" and f["00-0034855"]["role"] == "depth"
    assert f["00-0041000"]["words"] == (
        "Starter unclear: Tampa Bay lists Jalon Daniels as the starter, but the depth chart puts Baker Mayfield first. "
        "Our projections assume the listing: Daniels as the starter, Mayfield as his backup.")
    assert all("wrong" not in v["words"] for v in f.values())


def test_the_pick_s_sentence_when_the_sources_disagree():
    """IW-1 (Wave I-W): the data rule's pick (sq1.0, starter_source 'data') against the listing: one sentence in a
    manager's words, never a hand-set word; nothing when the pick is the listing."""
    rows = pd.DataFrame([
        {"team": "SEA", "week": 5, "listed_qb_id": SEA_LOCK, "listed_name": "Drew Lock", "depth_available_qb_id": SEA_DARNOLD,
         "depth_available_name": "Sam Darnold", "last_week": 4, "projected_qb_id": SEA_DARNOLD, "projected_name": "Sam Darnold",
         "last_qb_id": SEA_DARNOLD, "last_name": "Sam Darnold", "starter_source": "data", "listing_disputed": True},
        {"team": "BAL", "week": 5, "listed_qb_id": "00-0034796", "listed_name": "Lamar Jackson",
         "depth_available_qb_id": "00-0035993", "depth_available_name": "Tyler Huntley", "last_week": 4,
         "projected_qb_id": "00-0035993", "projected_name": "Tyler Huntley", "last_qb_id": "00-0034796",
         "last_name": "Lamar Jackson", "starter_source": "data", "listing_disputed": True},
        {"team": "BUF", "week": 5, "listed_qb_id": "00-0034857", "listed_name": "Josh Allen", "depth_available_qb_id": "00-0034857",
         "depth_available_name": "Josh Allen", "last_week": 4, "projected_qb_id": "00-0034857", "projected_name": "Josh Allen",
         "last_qb_id": "00-0034857", "last_name": "Josh Allen", "starter_source": "schedule", "listing_disputed": False}])
    f = S.corrected_from(rows)
    assert set(f) == {SEA_DARNOLD, SEA_LOCK, "00-0035993", "00-0034796"}
    assert f[SEA_DARNOLD]["role"] == "set" and f[SEA_LOCK]["role"] == "listed"
    assert f[SEA_DARNOLD]["words"] == f[SEA_LOCK]["words"] == (
        "Seattle: we project Sam Darnold to start — he led the team's dropbacks in week 4; the schedule lists Drew Lock.")
    assert f["00-0035993"]["words"] == (
        "Baltimore: we project Tyler Huntley to start — Lamar Jackson, the listed starter, is ruled out and he is next on "
        "the depth chart.")
    assert all("hand" not in v["words"] and "corrected" not in v["words"] for v in f.values())
    # IQ-2's mechanism stays (unused: the seed keeps its header only); a listing the pick agrees with says nothing
    assert S.corrected_from(rows.iloc[[2]]) == {}
    # U1 never speaks for a team whose starter the rule set (one sentence per disagreement)
    assert S.disputed_from(rows) == {}


def test_with_the_mart_unclear_is_u1_and_corrected_reads_it(monkeypatch):
    monkeypatch.setattr(S, "check", lambda season, week: chk(SEA, CHI, TB, BUF))
    u = S.unclear(2026, 5)
    assert {v["team"] for v in u.values()} == {"TB"}
    c = S.corrected(2026, 5)
    assert {v["team"] for v in c.values()} == {"SEA", "CHI"} and c[SEA_DARNOLD]["role"] == "set"   # ---- IW-1: the pick's own row


def test_without_the_mart_nothing_changes(monkeypatch):
    """The deploy lands before the nightly: no mart (and no seed table) -> corrected {} and su1.0 exactly as before."""
    seen = []

    def missing(names):
        seen.append(tuple(names))
        return [n for n in names if n == S.CHECK]            # the mart is not built; su1.0's relations are there
    listing = pd.DataFrame([{"team": "SEA", "listed_id": SEA_LOCK, "game_id": "g4", "last_week": 4}])
    drop = pd.DataFrame([{"game_id": "g4", "team": "SEA", "gsis_id": SEA_DARNOLD, "dropbacks": 26.0}])
    names = pd.DataFrame([{"gsis_id": SEA_LOCK, "player_name": "Drew Lock"}, {"gsis_id": SEA_DARNOLD, "player_name": "Sam Darnold"}])

    def query(sql, params=()):
        if "mart_starter_check" in sql:
            raise AssertionError("the mart is never read when it is missing")
        return listing if "with listing" in sql else drop if "dropbacks" in sql else names
    monkeypatch.setattr(S, "missing_relations", missing)
    monkeypatch.setattr(S, "query", query)
    assert S.corrected(2026, 5) == {}
    u = S.unclear(2026, 5)
    assert set(u) == {SEA_LOCK, SEA_DARNOLD} and u[SEA_LOCK]["words"].startswith(
        "Starter unclear: Seattle lists Drew Lock as the starter, but he did not drop back once in week 4")
    assert (S.CHECK,) in seen


def test_a_failed_read_is_never_an_error(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("relation does not exist")
    monkeypatch.setattr(S, "missing_relations", lambda names: [])
    monkeypatch.setattr(S, "query", boom)
    assert S.check(2026, 5) is None and S.corrected(2026, 5) == {} and S.unclear(2026, 5) == {}
    assert S.corrected(2026, 0) == {} and S.corrected("x", 5) == {} and S.check(2026, 99) is None
    # an empty mart for the week (its rows are for another week) -> the old behaviour
    monkeypatch.setattr(S, "query", lambda sql, params=(): pd.DataFrame(columns=list(S.CHECK_COLS)))
    assert S.check(2026, 5) is None


@needs_db
def test_the_database_week_5():
    """Where the mart is built: the data rule's pick (IW-1). Without it (a database before the nightly): today's su1.0
    flags and no sentence."""
    if S.check(2026, 5) is None:
        assert S.corrected(2026, 5) == {}
        assert {"SEA", "CHI"} <= {v["team"] for v in S.unclear(2026, 5).values()}
        return
    c = S.corrected(2026, 5)
    # IW-1: the data rule (sq1.0) starts Darnold for Seattle; Chicago keeps its listing (Keenum) while the depth chart
    # names Caleb Williams first: "Starter unclear" (U1), no pick sentence
    assert c[SEA_DARNOLD]["words"].startswith("Seattle: we project Sam Darnold to start — he led the team's dropbacks")
    assert not ({CHI_BAGENT, CHI_KEENUM} & set(c))
    u = S.unclear(2026, 5)
    assert "SEA" not in {v["team"] for v in u.values()}
    assert all(v["role"] in ("listed", "depth") for v in u.values())


def _week5(monkeypatch):
    """The screens at week 5 (the pinned clock is week 4's Saturday): Wednesday 2026-10-07 evening."""
    from league_lab import clock
    clock.pin("2026-10-07T23:00:00Z")          # conftest unpins after every test


def _has_mart() -> bool:
    return S.check(2026, 5) is not None


@needs_db
def test_rankings_row_and_start_answer_for_a_corrected_quarterback(client, monkeypatch):
    _week5(monkeypatch)
    d = client.get(ROUTE, params={"league": "ref:half", "position": "QB", "limit": 200})
    assert d.status_code == 200
    body = d.json()
    if body.get("week") != 5 or not _has_mart():
        pytest.skip("the database is not at week 5 with mart_starter_check built")
    by = {x["gsis_id"]: x for x in body["rows"]}
    sea = by[SEA_DARNOLD]
    assert sea["starter_corrected"]["role"] == "set" and sea["starter_corrected"]["words"].startswith("Seattle: we project Sam Darnold to start")   # ---- IW-1
    assert not sea.get("starter_unclear") and sea["tier"] is not None          # tiers like anyone else
    assert by[SEA_LOCK]["starter_corrected"]["role"] == "listed"
    assert not by[CHI_BAGENT].get("starter_corrected")          # ---- IW-1: Chicago keeps its listing (Keenum), no pick sentence
    assert by[SEA_DARNOLD]["proj_points"] > by[SEA_LOCK]["proj_points"]        # projected as the starter
    other = next(x["gsis_id"] for x in body["rows"] if not x.get("starter_unclear") and not x.get("starter_corrected"))
    a = client.get(START, params={"league": "ref:half", "ids": f"{SEA_DARNOLD},{other}"})
    assert a.status_code == 200
    ans = a.json()
    assert ans["answer"]["verdict"] in ("clear", "a lean", "a coin flip") and ans["starter_unclear"] == []
    p = next(x for x in ans["players"] if x["gsis_id"] == SEA_DARNOLD)
    assert p["starter_corrected"]["words"] == sea["starter_corrected"]["words"] and p["pct_best"] is not None
    season = client.get(ROUTE, params={"league": "ref:half", "position": "QB", "view": "season", "limit": 200}).json()
    assert {x["gsis_id"]: x for x in season["rows"]}[SEA_DARNOLD]["starter_corrected"]["role"] == "set"


@needs_db
def test_rankings_without_the_mart_no_5xx_and_no_sentence(client, monkeypatch):
    _week5(monkeypatch)
    monkeypatch.setattr(S, "missing_relations", lambda names: [n for n in names if n == S.CHECK])
    for params in ({"position": "QB"}, {"position": "QB", "view": "season"}, {"position": "WR"}):
        r = client.get(ROUTE, params={"league": "ref:half", "limit": 200, **params})
        assert r.status_code == 200
        assert not any(x.get("starter_corrected") for x in r.json()["rows"])
    r = client.get(START, params={"league": "ref:half", "ids": f"{SEA_DARNOLD},{SEA_LOCK}"})
    assert r.status_code == 200 and all(not p.get("starter_corrected") for p in r.json()["players"])
