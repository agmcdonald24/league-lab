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
    scoring = {"rec": 0.5, "sack": 1.0, "bonus_rec_te": 0.5, "pass_yd": 0.0}
    assert unmapped_keys(scoring) == ["bonus_rec_te", "sack"]
    assert "pass_yd" in SLEEPER_STAT_MAP
