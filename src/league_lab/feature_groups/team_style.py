"""Feature group ``team_style`` (plan D4, Wave D / projection v3): team volume and style.

The table is ``intermediate.int_player_week_team_style`` (dbt, ``dbt/models/intermediate/features/``): per
player-week, his own offense's numbers (``ts_off_*``) and this week's opponent defense's (``ts_def_*``: what
it allowed), as of the week, season to date (``_std``) and last 4 games (``_l4``), each shrunk toward last
season. Definitions: ``docs/METRICS.md`` § "Team volume and style".

This module also holds the Python twins of the two rules the SQL hard-codes (``tests/test_team_style.py``
pins them on fixtures and checks the SQL uses the same constants):

* ``shrink`` - the early-season shrinkage (dbt macro ``ts_shrink``);
* ``is_play`` / ``is_neutral`` / ``neutral_pass_rate`` - what a play is and the neutral situation
  (``int_team_game_style``).

None of the columns is ``in_season`` in the harness's sense: week 1 carries last season's full-season values
(known before kickoff, by design), not NULL. The as-of evidence is the ``ts_*_asof_week`` marker (< week, the
harness's check 3) and the dbt tests ``assert_team_style_is_asof`` / ``team_week_style_is_asof``.
"""

from __future__ import annotations

from collections.abc import Iterable

TABLE = "intermediate.int_player_week_team_style"

# ------------------------------------------------------------------------------ the rules (Python twins of the SQL)
SHRINK_GAMES = 3                 # the prior's weight in games (int_team_week_style: prior_games)
NEUTRAL_DOWNS = (1, 2)           # int_team_game_style: down in (1, 2)
NEUTRAL_LAST_QUARTER = 3         # ... and qtr <= 3
NEUTRAL_SCORE = 7                # ... and abs(score_differential_pre) <= 7
MAX_CLOCK_GAP = 75               # seconds: a longer row-to-row gap is a source clock glitch


def shrink(window: float | None, n: int, prior: float | None, k: int = SHRINK_GAMES) -> float | None:
    """value = (n x window + k x prior) / (n + k); n = the team's games this season before the week.

    Week 1 (n = 0) is the prior; no prior (2016, the first season loaded) leaves the in-season value (None in
    week 1); an in-season value that cannot be computed falls back to the prior. The same n weights both the
    season-to-date and the last-4 window (the in-season weight grows with the season, not with the window)."""
    if prior is None:
        return window
    if n == 0 or window is None:
        return prior
    return (n * window + k * prior) / (n + k)


def is_play(is_dropback: bool, is_rush_attempt: bool, is_kneel: bool) -> bool:
    """A snap that can produce a stat line: a dropback (pass attempt, sack, scramble) or a designed run.
    Kneels are not plays; spikes, two-point tries and nullified snaps are neither dropbacks nor rush attempts
    in fct_play, so they fall out too."""
    return bool(is_dropback) or (bool(is_rush_attempt) and not bool(is_kneel))


def is_neutral(down: int | None, qtr: int | None, score_differential_pre: int | None) -> bool:
    """1st or 2nd down, quarters 1-3, the offense's pre-play score within 7 points either way. Unknown -> False."""
    if down is None or qtr is None or score_differential_pre is None:
        return False
    return down in NEUTRAL_DOWNS and qtr <= NEUTRAL_LAST_QUARTER and abs(score_differential_pre) <= NEUTRAL_SCORE


def neutral_pass_rate(plays: Iterable[dict]) -> float | None:
    """Neutral dropbacks / neutral plays over fct_play-shaped rows (keys: is_dropback, is_rush_attempt, is_kneel,
    down, qtr, score_differential_pre). Pooled: a window's rate is its sums, not the mean of game rates."""
    num = den = 0
    for p in plays:
        if is_play(p.get("is_dropback"), p.get("is_rush_attempt"), p.get("is_kneel")) and \
                is_neutral(p.get("down"), p.get("qtr"), p.get("score_differential_pre")):
            den += 1
            num += bool(p.get("is_dropback"))
    return num / den if den else None


# ------------------------------------------------------------------------------ the columns
METRICS = ["plays_pg", "sec_per_play", "neutral_pass_rate", "proe", "first_downs_pg", "top_min_pg",
           "red_zone_trips_pg", "points_per_drive", "scoring_drive_rate", "yards_per_play", "sacks_per_dropback",
           "giveaways_pg"]
WINDOWS = ("std", "l4")


def cols(side: str, metrics: Iterable[str]) -> list[str]:
    return [f"ts_{side}_{m}_{w}" for m in metrics for w in WINDOWS]


VOLUME = [*cols("off", ["plays_pg", "sec_per_play", "top_min_pg"]), "ts_pace_product"]
PASS_RATE = [*cols("off", ["neutral_pass_rate", "proe"]), "ts_pass_env"]
EFFICIENCY = cols("off", ["first_downs_pg", "yards_per_play", "points_per_drive", "scoring_drive_rate",
                          "red_zone_trips_pg", "sacks_per_dropback", "giveaways_pg"])
DEFENSE_FACED = cols("def", METRICS)
ALL = ["ts_off_games", "ts_def_games", *cols("off", METRICS), *DEFENSE_FACED, "ts_pace_product", "ts_pass_env"]

GROUPS = {
    "team_style": {
        "table": TABLE, "columns": ALL,
        "label": "Team volume and style (all)",
        "note": "his offense's and the opponent defense's plays, pace, pass rate, first downs, possession, drives; season and last 4, shrunk to last season",
    },
    "team_style_volume": {
        "table": TABLE, "columns": VOLUME,
        "label": "How many plays his offense runs",
        "note": "plays per game, seconds per play (neutral), time of possession; the matchup's expected plays",
    },
    "team_style_pass_rate": {
        "table": TABLE, "columns": PASS_RATE,
        "label": "How often his offense throws",
        "note": "neutral pass rate, pass rate over expected (nflfastR xpass); the matchup's expected pass rate",
    },
    "team_style_efficiency": {
        "table": TABLE, "columns": EFFICIENCY,
        "label": "How well his offense moves the ball",
        "note": "first downs, yards per play, points per drive, scoring drives, red-zone trips, sacks, giveaways",
    },
    "team_style_defense_faced": {
        "table": TABLE, "columns": DEFENSE_FACED,
        "label": "What the opponent's defense allows",
        "note": "the same twelve numbers for the offenses this week's opponent has faced (plays, pass rate, first downs, sacks, takeaways ...)",
    },
}
