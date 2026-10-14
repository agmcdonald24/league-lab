"""JB-4 (Wave J-B): the card's one sentence on points over expected. Hand-built games first (the thresholds, the
unknown case, the sum over the same games; no database), then Michael Wilson on the database."""

import pandas as pd

from league_lab_api import poe

from .conftest import needs_db

WILSON, SCRUBS, UNCLEAN = "00-0038559", "1389709692405551104", "1321941740235550720"


def _games(rows):
    base = {"season_type": "REG", "played": True, "expected_known": True}
    return pd.DataFrame([{**base, **r} for r in rows])


def _counts(rows):
    return pd.DataFrame(rows, columns=["game_id", "targets", "carries"])


def test_a_receivers_sentence_sums_his_games_and_rounds_to_whole_points():
    g = _games([{"game_id": f"g{i}", "points": p, "points_expected": x} for i, (p, x) in
                enumerate([(5.3, 20.1), (12.0, 15.2), (17.0, 14.0), (10.0, 14.5)])])
    c = _counts([(f"g{i}", t, 0) for i, t in enumerate([12, 10, 11, 11])])
    line = poe.sentence(g, c, "WR")
    assert line["words"] == "His 44 targets usually bring about 64 points; he has 44. Depth of target is already allowed for."
    assert (line["targets"], line["expected"], line["actual"], line["games"]) == (44, 63.8, 44.3, 4)
    line = poe.sentence(g.assign(points=[20.0, 20.0, 20.0, 10.0]), c, "TE")            # above: the verb says it
    assert line["words"].startswith("His 44 targets usually bring about 64 points; he has 70.")


def test_a_back_counts_carries_and_targets():
    g = _games([{"game_id": "a", "points": 30.0, "points_expected": 22.5}, {"game_id": "b", "points": 9.0, "points_expected": 18.0}])
    line = poe.sentence(g, _counts([("a", 3, 14), ("b", 2, 12)]), "RB")
    assert line["words"] == ("His 26 carries and 5 targets usually bring about 41 points; he has 39. "
                             "Depth of target and field position are already allowed for.")


def test_the_thresholds_twenty_and_no_quarterback():
    g = _games([{"game_id": "a", "points": 10.0, "points_expected": 9.0}])
    assert poe.sentence(g, _counts([("a", 19, 5)]), "WR") is None                  # a receiver: targets only
    assert poe.sentence(g, _counts([("a", 20, 0)]), "WR")["targets"] == 20
    assert poe.sentence(g, _counts([("a", 4, 15)]), "RB") is None                  # a back: 19 carries + targets
    assert poe.sentence(g, _counts([("a", 5, 15)]), "RB") is not None
    assert poe.sentence(g, _counts([("a", 30, 30)]), "QB") is None
    assert poe.sentence(g, _counts([("a", 30, 30)]), "K") is None and poe.sentence(g, _counts([("a", 30, 0)]), None) is None


def test_unknown_is_never_zero_and_the_games_are_the_same_for_all_four_numbers():
    g = _games([{"game_id": "a", "points": 10.0, "points_expected": 9.0, "expected_known": False},
                {"game_id": "b", "points": 8.0, "points_expected": None}])
    assert poe.sentence(g, _counts([("a", 30, 0), ("b", 30, 0)]), "WR") is None    # no expected value: nothing, not 0
    g = _games([{"game_id": "a", "points": 10.0, "points_expected": 9.0},
                {"game_id": "b", "points": 8.0, "points_expected": 12.0, "expected_known": False},   # left out: its targets too
                {"game_id": "c", "points": 30.0, "points_expected": 5.0, "season_type": "POST"},
                {"game_id": "d", "points": 0.0, "points_expected": 0.0, "played": False},
                {"game_id": "e", "points": 9.5, "points_expected": 11.5}])
    line = poe.sentence(g, _counts([("a", 11, 0), ("b", 30, 0), ("c", 9, 0), ("e", 10, 0)]), "WR")
    assert (line["targets"], line["expected"], line["actual"], line["games"]) == (21, 20.5, 19.5, 2)
    assert line["words"].startswith("His 21 targets usually bring about 21 points; he has 20.")   # 20.5 → 21, 19.5 → 20
    assert poe.sentence(pd.DataFrame(), _counts([("a", 30, 0)]), "WR") is None


def test_a_failure_to_read_costs_no_card(client, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("could not read")
    monkeypatch.setattr(poe, "card_line", boom)
    r = client.get(f"/api/player/{WILSON}?league=ref%3Ahalf")
    if r.status_code == 200:                                        # without a database the card itself may not answer
        assert r.json()["expected_line"] is None


@needs_db
def test_michael_wilson_on_the_card_agrees_with_the_league_mart(client, sql):
    d = client.get(f"/api/player/{WILSON}?league={SCRUBS}&team=2").json()
    line = d["expected_line"]
    assert line["words"] == "His 44 targets usually bring about 64 points; he has 44. Depth of target is already allowed for."
    m = sql("select points, points_expected, games_with_expected from analytics.mart_league_player_season "
            "where league_id = %s and gsis_id = %s and season = 2026", (SCRUBS, WILSON))[0]
    assert (line["expected"], line["actual"], line["games"]) == (round(float(m["points_expected"]), 1),
                                                                  round(float(m["points"]), 1), m["games_with_expected"])
    other = client.get(f"/api/player/{WILSON}?league={UNCLEAN}&team=12").json()["expected_line"]
    assert other["targets"] == 44 and other["expected"] != line["expected"]          # each league its own scoring
    assert client.get(f"/api/player/00-0034796?league={SCRUBS}&team=2").json()["expected_line"] is None   # a QB


def test_the_stats_columns_say_what_is_allowed_for():
    from league_lab_api import stats
    col = {c["id"]: c for c in stats.CATALOGUE}
    assert "Depth of target, field position and down are already allowed for" in col["points_over_expected"]["definition"]
    assert col["points_over_expected"]["definition"].endswith("A bad throw lowers his points, not his expected points.")
    assert "air yards, field position and down" in col["expected_points"]["definition"]
