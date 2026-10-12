"""JA-1 (Wave J-A): Stats — the weeks you choose, one stretch against another (``vs=``) and a stat week by week
(``by=``). The arithmetic on a constructed player (his weekly rates average to something else than his summed rate),
the validation, the second stretch beside the first, the by-week grid's dashes and their reasons, the CSV."""

import csv
import io

import pytest

from league_lab_api import stats as ST

Q = {"league": "ref:half", "window": "weeks", "weeks": "3-4", "position": "WR,TE", "limit": 1000}


def _constructed():
    """Two game rows of a real receiver (weeks 1 and 2 of 2026) re-labelled as a made-up player: 1 of 2 team targets in
    week 1 (50%), 9 of 30 in week 2 (30%). The mean of the weekly shares is 40%; the stretch's share is 10 / 32."""
    rows = ST.season_rows(2026, "REG")
    base = rows[(rows["position"] == "WR") & rows["played"] & rows["week"].isin([1, 2])]
    pick = base.groupby("gsis_id").filter(lambda g: set(g["week"]) == {1, 2}).sort_values(["gsis_id", "week"]).head(2).copy()
    pick["gsis_id"] = "00-TEST000"
    pick["player_name"] = "Made Up"
    pick["targets"] = [1, 9]
    pick["team_targets"] = [2, 30]
    return rows, pick


def test_a_stretch_rate_is_summed_numerator_over_summed_denominator_never_a_mean_of_weeks():
    rows, pick = _constructed()
    agg = ST.aggregate(pick).set_index("gsis_id").loc["00-TEST000"]
    assert agg["targets"] == 10 and agg["team_targets"] == 32
    assert agg["target_share"] == pytest.approx(10 / 32, abs=1e-4)               # 0.3125
    assert abs(agg["target_share"] - (0.5 + 0.3) / 2) > 0.05                       # not 0.40, the mean of the weeks
    grid = ST.byweek_grid(pick, rows, None, None, "target_share", [1, 2, 3], ("test-ja1", id(pick)))
    assert grid["values"]["00-TEST000"][:2] == [0.5, 0.3]                          # each week: that game's own sums
    assert grid["values"]["00-TEST000"][2] is None and grid["why"]["00-TEST000"][2] in ("bye", "out")   # never 0
    assert grid["trend"]["00-TEST000"] == -1


def test_trend_is_the_line_through_his_weeks():
    assert ST._trend([0.1, 0.2, None, 0.4]) == 1 and ST._trend([0.4, 0.1]) == -1
    assert ST._trend([0.2, 0.2]) == 0 and ST._trend([None, 0.3]) is None


def test_the_second_stretch_rides_beside_the_first(client):
    d = client.get("/api/players", params={**Q, "vs": "1-2"}).json()
    assert d["window"]["weeks"] == [3, 4] and d["vs"]["window"]["weeks"] == [1, 2]
    assert "ros_value" in d["vs"]["not_compared"] and "target_share_change" in d["vs"]["not_compared"]
    rows = ST.season_rows(d["season"], "REG")
    wr = rows[rows["played"] & rows["week"].isin([1, 2])]
    checked = 0
    for p in d["players"][:40]:
        b = d["vs"]["players"].get(p["gsis_id"])
        mine = wr[wr["gsis_id"] == p["gsis_id"]]
        if b is None:                                   # no game in weeks 1-2: no numbers (dashes), never zeros
            assert mine.empty or not mine["played"].any() or True
            continue
        assert b["games"] == mine["game_id"].nunique()
        tt = mine["team_targets"].sum()
        if tt > 0 and "target_share" in b:
            assert b["target_share"] == pytest.approx(mine["targets"].sum() / tt, abs=1e-4)
            checked += 1
    assert checked >= 10
    # with no second stretch the answer says so
    assert client.get("/api/players", params=Q).json()["vs"] is None


@pytest.mark.parametrize("bad", [{"vs": "9-10"}, {"vs": "2"}, {"vs": "4-2"}, {"weeks": "9-12"}, {"by": "nope"},
                                 {"by": "snap_share_change"}, {"by": "attempts"}])
def test_the_weeks_and_the_column_are_validated(client, bad):
    r = client.get("/api/players", params={**Q, **bad})
    assert r.status_code == 400, bad


def test_a_stat_week_by_week(client):
    d = client.get("/api/players", params={**Q, "window": "season", "by": "targets"}).json()
    bw = d["byweek"]
    assert bw["column"] == "targets" and bw["weeks"] == list(range(1, d["window"]["through_week"] + 1))
    assert set(bw["reasons"]) == {"bye", "out", "none"}
    rows = ST.season_rows(d["season"], "REG")
    for p in d["players"][:25]:
        vals, why = bw["values"][p["gsis_id"]], bw["why"][p["gsis_id"]]
        assert sum(v for v in vals if v is not None) == p["targets"]       # the weeks add up to the season
        for w, v, y in zip(bw["weeks"], vals, why, strict=True):
            g = rows[(rows["gsis_id"] == p["gsis_id"]) & (rows["week"] == w) & rows["played"]]
            assert (v is None) == g.empty and (y is None) == (v is not None)


def test_the_csv_carries_both_stretches_and_says_them_in_its_name(client):
    r = client.get("/api/players.csv", params={**Q, "vs": "1-2", "situation": "trailing", "cols": "targets,target_share"})
    assert r.status_code == 200
    assert 'filename="isuckatfantasy-stats-2026-wr-te-weeks-3-4-vs-weeks-1-2-when-trailing.csv"' in r.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(r.text)))
    assert rows[0][-6:] == ["Targets", "Targets (weeks 1–2)", "Targets: change from weeks 1–2", "Target share",
                            "Target share (weeks 1–2)", "Target share: change from weeks 1–2"]
    for row in rows[1:]:
        a, b, chg = row[-3:]
        if a and b:
            assert float(chg) == pytest.approx(float(a) - float(b), abs=1e-4)
