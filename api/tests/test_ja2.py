"""JA-2 (Wave J-A): the same weeks on Compare and Matchups. Compare's rows over a stretch and against another (the Stats
frame's arithmetic); what each defense gave up over a stretch and its rank (1 = gives up the most), the change in rank,
too few games said; the numbers a decision reads (the card's, My Week's, the trade's matchup words; Compare's
forecasts; the season's ranks) unchanged with a stretch in the address."""

import pytest

SCRUBS = "1389709692405551104"
CHASE, WILSON = "00-0036900", "00-0038559"


def test_compare_over_the_weeks_and_against_others(client):
    r = client.get("/api/compare/weeks", params={"league": "ref:half", "a": CHASE, "b": WILSON, "window": "weeks",
                                                  "weeks": "3-4", "vs": "1-2"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["window"]["weeks"] == [3, 4] and d["vs"]["weeks"] == [1, 2]
    rows = {x["id"]: x for x in d["rows"]}
    assert {"games", "points_per_game", "targets_per_game", "target_share", "snap_share"} <= set(rows)
    assert "attempts_per_game" not in rows                      # no quarterback here
    s = client.get("/api/players", params={"league": "ref:half", "window": "weeks", "weeks": "3-4", "vs": "1-2",
                                           "position": "ALL", "limit": 1000}).json()
    me = next(p for p in s["players"] if p["gsis_id"] == CHASE)
    assert rows["target_share"]["a"]["a"] == me["target_share"]
    assert rows["target_share"]["a"]["b"] == s["vs"]["players"][CHASE]["target_share"]
    assert "forecasts" in d["note"]
    for bad in ({"vs": "x"}, {"window": "weeks", "weeks": "9-12"}, {"a": CHASE, "b": CHASE}):
        assert client.get("/api/compare/weeks", params={"league": "ref:half", "a": CHASE, "b": WILSON, **bad}).status_code == 400


def test_compare_forecasts_do_not_move_with_the_weeks(client):
    base = {"league": "ref:half", "a": CHASE, "b": WILSON}
    plain = client.get("/api/compare", params=base).json()
    weeks = client.get("/api/compare", params={**base, "window": "weeks", "weeks": "1-2", "vs": "3-4"}).json()
    assert plain["a"].get("proj_points") == weeks["a"].get("proj_points") and plain["table"] == weeks["table"]


def test_matchups_over_a_stretch_rank_and_change(client):
    q = {"league": SCRUBS, "position": "WR"}
    plain = client.get("/api/matchups/defense", params=q).json()
    d = client.get("/api/matchups/defense", params={**q, "window": "weeks", "weeks": "3-4", "vs": "1-2"}).json()
    # every season number stays as it was (the card, My Week and the trade read the season)
    assert plain["teams"] == d["teams"]
    st = d["stretch"]
    assert st["weeks"] == [3, 4] and st["vs"] == [1, 2] and "#1 = gives up the most" in st["note"]
    cells = [c for c in st["cells"] if c["position"] == "WR"]
    assert len(cells) == 32
    ranked = sorted((c for c in cells if c["rank"] is not None), key=lambda c: c["rank"])
    assert ranked[0]["ppg"] == max(c["ppg"] for c in ranked)                      # 1 = gives up the most
    assert all(c["rank"] is None for c in cells if c["few"]) and all(c["games"] >= 2 for c in ranked)
    for c in cells:
        if c["rank"] is not None and c["vs_rank"] is not None:
            assert c["rank_change"] == c["vs_rank"] - c["rank"]
    bad = client.get("/api/matchups/defense", params={**q, "window": "weeks", "weeks": "12-14"})
    assert bad.status_code == 400


@pytest.mark.parametrize("path", ["/api/player/00-0036900", "/api/my-week"])
def test_the_numbers_a_decision_reads_ignore_the_weeks(client, path):
    q = {"league": SCRUBS, "team": 2}
    a = client.get(path, params=q)
    b = client.get(path, params={**q, "window": "weeks", "weeks": "1-2", "vs": "3-4"})
    assert a.status_code == b.status_code
    if a.status_code == 200:
        ja, jb = a.json(), b.json()
        for k in ("generated_at", "built_at", "as_of", "now"):
            ja.pop(k, None)
            jb.pop(k, None)
        assert ja == jb
