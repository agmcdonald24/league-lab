"""The Python scoring map and the dbt seed must never diverge (they are the same contract)."""
import csv
from pathlib import Path

from league_lab.scoring import SLEEPER_STAT_MAP, compute_points, seed_rows, unmapped_keys

ROOT = Path(__file__).resolve().parents[1]


def test_seed_matches_python_map():
    with open(ROOT / "dbt/seeds/scoring_stat_map.csv", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert rows == seed_rows(), "regenerate dbt/seeds/scoring_stat_map.csv from league_lab.scoring.seed_rows()"


def test_half_ppr_receiver_line():
    scoring = {"rec": 0.5, "rec_yd": 0.1, "rec_td": 6.0, "fum_lost": -2.0}
    stats = {"receptions": 7, "receiving_yards": 105, "receiving_tds": 1, "fumbles_lost_total": 1}
    assert compute_points(stats, scoring) == 7 * 0.5 + 10.5 + 6 - 2


def test_kicker_buckets_and_blocked_kicks():
    scoring = {"fgm_0_19": 3, "fgm_20_29": 3, "fgm_30_39": 3, "fgm_40_49": 4, "fgm_50p": 5, "fgmiss": -1, "xpm": 1, "xpmiss": -1}
    stats = {"fg_made_30_39": 1, "fg_made_40_49": 1, "fg_made_50_59": 1, "fg_made_60_": 1, "fg_missed": 1, "fg_blocked": 1,
             "pat_made": 3, "pat_missed": 0, "pat_blocked": 1}
    # 3 + 4 + 5 + 5 - 2 (missed + blocked) + 3 - 1 (blocked PAT)
    assert compute_points(stats, scoring) == 17


def test_unmapped_keys_are_reported_not_silently_dropped():
    scoring = {"rec": 0.5, "sack": 1.0, "bonus_rec_te": 0.5, "pass_yd": 0.0, "bonus_rec_yd_100": 3.0, "rec_td_40p": 2.0}
    assert unmapped_keys(scoring) == ["bonus_rec_te", "sack"]
    assert "pass_yd" in SLEEPER_STAT_MAP


def test_yardage_bonuses_are_exclusive_buckets():
    # Sleeper: bonus_rec_yd_100 = a 100-199 yard game, bonus_rec_yd_200 = 200+; never both
    scoring = {"rec_yd": 0.1, "bonus_rec_yd_100": 3.0, "bonus_rec_yd_200": 6.0, "bonus_rush_yd_100": 3.0}
    assert compute_points({"receiving_yards": 99}, scoring) == 9.9
    assert compute_points({"receiving_yards": 100}, scoring) == 13.0
    assert compute_points({"receiving_yards": 199}, scoring) == 19.9 + 3.0
    assert compute_points({"receiving_yards": 200}, scoring) == 20.0 + 6.0
    assert compute_points({"receiving_yards": 210, "rushing_yards": 100}, scoring) == 21.0 + 6.0 + 3.0
    # expected points leave every bonus out
    assert compute_points({"receiving_yards": 210}, scoring, include_bonuses=False) == 21.0


def test_long_touchdowns_count_per_play():
    scoring = {"pass_td": 4.0, "pass_td_40p": 2.0, "rec_td": 6.0, "rec_td_40p": 2.0, "rec_td_50p": 1.0}
    stats = {"passing_tds": 3, "pass_tds_40p": 2, "receiving_tds": 1, "rec_tds_40p": 1, "rec_tds_50p": 1}
    assert compute_points(stats, scoring) == 12 + 4 + 6 + 2 + 1
    assert compute_points(stats, scoring, include_bonuses=False) == 18


def test_kicker_miss_buckets():
    scoring = {"fgmiss_0_19": -2, "fgmiss_20_29": -1, "fgmiss_50p": -0.5, "fgm_50p": 5}
    stats = {"fg_missed_0_19": 1, "fg_missed_20_29": 2, "fg_missed_50_59": 1, "fg_missed_60_": 1, "fg_made_50_59": 1}
    assert compute_points(stats, scoring) == -2 - 2 - 1 + 5
