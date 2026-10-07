"""IP-4 (Wave I-P): the player card's ratings (percentiles of the Stats frame's season columns with a stated minimum
sample) and the projection made before each game (GET /api/player/{gsis}/ratings, /api/player/{gsis}/projections)."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from league_lab_api import ratelimit
from league_lab_api import ratings as R

from .conftest import SCRUBS, needs_db

PUKA, LAMAR, BREECE = "00-0039075", "00-0034796", "00-0038120"
CAT = {cid: {"id": cid, "format": "pct", "definition": f"def of {cid}", "source": "test", "reason": "no targets"}
       for cid, _l, _x in R.RECEIVING}
CAT["epa_per_target"]["minimum"] = {"field": "targets", "n": 20}
CAT["epa_per_target"]["format"] = "dec2"


def wr(gid: str, targets: float, share: float | None, epa: float | None = 0.1, **kw) -> dict:
    row = {"gsis_id": gid, "position": "WR", "targets": targets, "target_share": share, "epa_per_target": epa}
    for cid, _l, _x in R.RECEIVING:
        row.setdefault(cid, kw.get(cid, share))
    return row


def frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


# ------------------------------------------------------------------------------------------------ the arithmetic
def test_rank_of_counts_below_and_half_the_ties():
    v = pd.Series([1.0, 2.0, 2.0, 3.0, 4.0])
    assert R.rank_of(v, 4.0) == (1.0, 5)                     # above all four others
    assert R.rank_of(v, 1.0) == (0.0, 5)                     # below all
    p, n = R.rank_of(v, 2.0)                                 # one below, one tie (himself not counted): 1.5 / 4
    assert (p, n) == (0.375, 5)
    assert R.rating_of(1.0) == 99 and R.rating_of(0.0) == 0 and R.rating_of(0.5) == 50
    assert R.rating_of(math.nan) is None


def test_lower_is_better_ranks_the_other_way():
    v = pd.Series([0.02, 0.04, 0.06, 0.08])
    assert R.rank_of(v, 0.02, lower_better=True)[0] == 1.0
    assert R.rank_of(v, 0.08, lower_better=True)[0] == 0.0


def test_a_population_of_one_is_not_ranked():
    p, n = R.rank_of(pd.Series([5.0]), 5.0)
    assert math.isnan(p) and n == 1


def test_percentiles_on_a_hand_built_frame():
    rows = [wr(f"00-000000{i}", targets=20 + i, share=0.10 + 0.02 * i) for i in range(5)]
    out = R.ratings_from(frame(rows), "00-0000004", "WR", CAT)
    ts = next(r for r in out["ratings"] if r["key"] == "target_share")
    assert ts["rating"] == 99 and ts["percentile"] == 100.0 and ts["n"] == 5
    assert ts["words"].startswith("1st of 5 receivers")
    low = R.ratings_from(frame(rows), "00-0000000", "WR", CAT)
    assert next(r for r in low["ratings"] if r["key"] == "target_share")["rating"] == 0
    assert out["n_ranked"] == 5 and out["population"] == "15+ targets"
    # the overall is the plain mean of the ratings shown
    shown = [r["rating"] for r in out["ratings"] if r["rating"] is not None]
    assert out["overall"] == round(sum(shown) / len(shown)) and out["overall_n"] == len(shown)
    assert "not a projection" in out["label"]


def test_ties_share_a_rating():
    rows = [wr("00-0000001", 30, 0.20), wr("00-0000002", 30, 0.20), wr("00-0000003", 30, 0.10)]
    a = R.ratings_from(frame(rows), "00-0000001", "WR", CAT)
    b = R.ratings_from(frame(rows), "00-0000002", "WR", CAT)
    ra = next(r for r in a["ratings"] if r["key"] == "target_share")["rating"]
    rb = next(r for r in b["ratings"] if r["key"] == "target_share")["rating"]
    assert ra == rb == 74                                    # (1 below + 0.5 x 1 tie) / 2 others = 0.75 -> 74


def test_under_the_minimum_is_a_dash_never_a_low_rating():
    rows = [wr(f"00-000000{i}", targets=30, share=0.2 + 0.01 * i) for i in range(4)] + [wr("00-0000009", 6, 0.40)]
    out = R.ratings_from(frame(rows), "00-0000009", "WR", CAT)
    assert all(r["rating"] is None for r in out["ratings"]) and out["overall"] is None
    assert all("ratings start at 15+ targets" in r["words"] for r in out["ratings"])
    # and he is not in anyone else's population: the 4 qualified players rank among themselves
    other = R.ratings_from(frame(rows), "00-0000003", "WR", CAT)
    assert next(r for r in other["ratings"] if r["key"] == "target_share")["n"] == 4


def test_a_columns_own_minimum():
    rows = [wr(f"00-000000{i}", targets=25, share=0.2, epa=0.1 * i) for i in range(4)] + [wr("00-0000008", 16, 0.3, epa=0.9)]
    out = R.ratings_from(frame(rows), "00-0000008", "WR", CAT)
    epa = next(r for r in out["ratings"] if r["key"] == "epa_per_target")
    assert epa["rating"] is None and "needs 20+ targets" in epa["words"]
    assert next(r for r in out["ratings"] if r["key"] == "target_share")["rating"] is not None   # 16 >= 15: in
    # the 25-target players rank on EPA among the four who clear 20 (not five)
    top = R.ratings_from(frame(rows), "00-0000003", "WR", CAT)
    assert next(r for r in top["ratings"] if r["key"] == "epa_per_target")["n"] == 4


def test_a_missing_value_is_unknown_with_the_reason():
    rows = [wr(f"00-000000{i}", targets=25, share=0.2 + 0.01 * i) for i in range(4)]
    rows[0]["first_read_target_share"] = None
    out = R.ratings_from(frame(rows), "00-0000000", "WR", CAT)
    fr = next(r for r in out["ratings"] if r["key"] == "first_read_target_share")
    assert fr["rating"] is None and fr["display"] == "—" and fr["words"].startswith("No value for him")


def test_a_player_with_no_games():
    rows = [wr(f"00-000000{i}", targets=25, share=0.2) for i in range(3)]
    out = R.ratings_from(frame(rows), "00-0000099", "WR", CAT)
    assert out["overall"] is None and not out["qualified"]
    assert all(r["words"] == "No games this season yet." and r["rating"] is None for r in out["ratings"])
    empty = R.ratings_from(pd.DataFrame(columns=["gsis_id", "position", "targets"]), "00-0000099", "WR", CAT)
    assert empty["n_ranked"] == 0 and empty["overall"] is None


def test_the_overall_needs_three_ratings():
    rows = [wr(f"00-000000{i}", targets=25, share=0.2 + 0.01 * i) for i in range(3)]
    for r in rows:
        for cid, _l, _x in R.RECEIVING[2:]:
            r[cid] = None
    out = R.ratings_from(frame(rows), "00-0000002", "WR", CAT)
    assert out["overall_n"] == 2 and out["overall"] is None and "3 or more" in out["overall_words"]


def test_every_position_names_six_to_eight_catalogue_columns():
    from league_lab_api import stats as ST
    for pos, items in R.RATINGS.items():
        assert 6 <= len(items) <= 8, pos
        for cid, _label, _lower in items:
            assert cid in ST.CAT and pos in ST.CAT[cid]["positions"], (pos, cid)


@pytest.mark.parametrize("value,fmt,want", [(0.2734, "pct", "27.3%"), (8.04, "dec1", "8.0"), (-0.123, "dec2", "-0.12"),
                                            (None, "pct", "—"), (math.nan, "dec1", "—")])
def test_display(value, fmt, want):
    assert R.fmt_value(value, fmt) == want


def test_the_routes_buckets():
    assert ratelimit.bucket_for("GET", f"/api/player/{PUKA}/ratings", "league=ref:half") == "research"
    assert ratelimit.bucket_for("GET", f"/api/player/{PUKA}/projections", "league=ref:half") == "read"   # one indexed read
    assert ratelimit.bucket_for("GET", f"/api/player/{PUKA}/games", "league=ref:half") == "research"     # unchanged
    assert ratelimit.bucket_for("GET", f"/api/player/{PUKA}", "league=ref:half") == "research"           # unchanged


# ------------------------------------------------------------------------------------------------ the routes
def test_bad_ids_and_parameters(client):
    for bad in ("DEN", "00-123", "../etc", "00-00390751"):
        assert client.get(f"/api/player/{bad}/ratings").status_code in (400, 404)
        assert client.get(f"/api/player/{bad}/projections", params={"league": "ref:half"}).status_code in (400, 404)
    assert client.get(f"/api/player/{PUKA}/ratings", params={"league": "x" * 65}).status_code == 400
    assert client.get(f"/api/player/{PUKA}/ratings", params={"season": 1999}).status_code == 400
    assert client.get(f"/api/player/{PUKA}/projections", params={"league": "x" * 65}).status_code == 400


@needs_db
def test_ratings_route_on_the_database(client):
    r = client.get(f"/api/player/{PUKA}/ratings", params={"league": "ref:half"})
    assert r.status_code == 200
    j = r.json()
    assert {"season", "through_week", "position", "n_ranked", "ratings", "overall"} <= set(j)
    assert j["position"] == "WR" and 6 <= len(j["ratings"]) <= 8
    for x in j["ratings"]:
        assert {"key", "label", "value", "percentile", "rating", "words"} <= set(x)
        assert x["rating"] is None or 0 <= x["rating"] <= 99
    shown = [x["rating"] for x in j["ratings"] if x["rating"] is not None]
    if len(shown) >= 3:
        assert j["overall"] == round(sum(shown) / len(shown))
    # the same in every league (NFL-wide)
    assert client.get(f"/api/player/{PUKA}/ratings", params={"league": SCRUBS}).json()["ratings"] == j["ratings"]
    for g in (LAMAR, BREECE):
        assert client.get(f"/api/player/{g}/ratings").json()["position"] in ("QB", "RB")


@needs_db
def test_projections_route(client):
    j = client.get(f"/api/player/{PUKA}/projections", params={"league": SCRUBS}).json()
    assert j["weeks"] and all(set(w) >= {"week", "proj_points", "p10", "p90", "source"} for w in j["weeks"])
    assert [w["week"] for w in j["weeks"]] == sorted(w["week"] for w in j["weeks"])
    assert max(w["week"] for w in j["weeks"]) <= j["through_week"]
    ref = client.get(f"/api/player/{PUKA}/projections", params={"league": "ref:half"}).json()
    assert ref["weeks"] and ref["why"] is None
    tep = client.get(f"/api/player/{PUKA}/projections", params={"league": "ref:ppr.tep"}).json()
    assert tep["weeks"] == [] and "Half PPR" in tep["why"]


@needs_db
def test_a_kickers_past_projections_on_a_reference_key(client):
    j = client.get("/api/player/00-0037692/projections", params={"league": "ref:half"}).json()   # Brandon Aubrey
    assert j["weeks"] and all(w["p25"] is None and w["p10"] is not None for w in j["weeks"])

