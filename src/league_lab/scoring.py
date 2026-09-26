"""Sleeper scoring keys -> nflverse weekly stat columns.

This is the single definition of how League Lab recomputes fantasy points from NFL statistics
under a league's ``scoring_settings``. The dbt seed ``scoring_stat_map.csv`` is generated from
this table (``league-lab`` never edits the seed by hand) and the ``league_points`` macro reads it.

Only offensive player and kicker keys are mapped. Team-defense keys (``sack``, ``int``,
``pts_allow_*`` ...) are intentionally unmapped: individual/team defense projection is out of
MVP1 scope, and observed DEF points still arrive from Sleeper's own ``players_points``.

Known approximations (documented in docs/METRICS.md):
* ``fgmiss``/``xpmiss``: Sleeper charges blocked kicks as misses; nflverse separates them, so the
  expression adds ``*_blocked``.
* ``fgm_50p`` = 50-59 + 60+ buckets.
* ``fum`` (any fumble) uses ``fumbles_total``; ``fum_lost`` uses ``fumbles_lost_total``.
* Bonus keys (``bonus_rec_te``, ``pass_td_40p`` ...) are unmapped; if a league enables them the
  reconciliation test in dbt will flag the gap rather than silently under-count.
"""

from __future__ import annotations

from collections.abc import Mapping

# sleeper_key -> (sql expression over stg_nflverse__player_stats_week columns, description)
SLEEPER_STAT_MAP: dict[str, tuple[str, str]] = {
    "pass_yd": ("passing_yards", "passing yards"),
    "pass_td": ("passing_tds", "passing touchdowns"),
    "pass_int": ("passing_interceptions", "interceptions thrown"),
    "pass_2pt": ("passing_2pt_conversions", "2-pt conversions passed"),
    "rush_yd": ("rushing_yards", "rushing yards"),
    "rush_td": ("rushing_tds", "rushing touchdowns"),
    "rush_2pt": ("rushing_2pt_conversions", "2-pt conversions rushed"),
    "rec": ("receptions", "receptions"),
    "rec_yd": ("receiving_yards", "receiving yards"),
    "rec_td": ("receiving_tds", "receiving touchdowns"),
    "rec_2pt": ("receiving_2pt_conversions", "2-pt conversions received"),
    "fum": ("fumbles_total", "fumbles (any)"),
    "fum_lost": ("fumbles_lost_total", "fumbles lost"),
    "fum_rec_td": ("fumble_recovery_tds", "fumble recovery touchdowns"),
    "st_td": ("special_teams_tds", "special teams touchdowns"),
    "fgm_0_19": ("fg_made_0_19", "FG made 0-19"),
    "fgm_20_29": ("fg_made_20_29", "FG made 20-29"),
    "fgm_30_39": ("fg_made_30_39", "FG made 30-39"),
    "fgm_40_49": ("fg_made_40_49", "FG made 40-49"),
    "fgm_50p": ("fg_made_50_59 + fg_made_60_", "FG made 50+"),
    "fgmiss": ("fg_missed + fg_blocked", "FG missed incl. blocked"),
    "xpm": ("pat_made", "PAT made"),
    "xpmiss": ("pat_missed + pat_blocked", "PAT missed incl. blocked"),
}

# Python evaluation of the same expressions (used by tests and the synthetic fixture generator).
_PY_EXPR: dict[str, tuple[str, ...]] = {
    k: tuple(part.strip() for part in expr.split("+")) for k, (expr, _) in SLEEPER_STAT_MAP.items()
}


def compute_points(stats: Mapping[str, float | int | None], scoring: Mapping[str, float]) -> float:
    """Fantasy points for one player-game row under a Sleeper ``scoring_settings`` dict."""
    total = 0.0
    for key, weight in scoring.items():
        cols = _PY_EXPR.get(key)
        if not cols or not weight:
            continue
        value = sum(float(stats.get(c) or 0) for c in cols)
        total += value * float(weight)
    return round(total, 2)


def unmapped_keys(scoring: Mapping[str, float]) -> list[str]:
    """Scoring keys with a non-zero weight that League Lab cannot recompute (DEF, bonuses...)."""
    return sorted(k for k, w in scoring.items() if w and k not in SLEEPER_STAT_MAP)


def seed_rows() -> list[dict[str, str]]:
    return [
        {"sleeper_key": k, "stat_expression": expr, "description": desc}
        for k, (expr, desc) in SLEEPER_STAT_MAP.items()
    ]
