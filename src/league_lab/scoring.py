"""Sleeper scoring keys -> nflverse weekly stat columns.

This is the single definition of how League Lab recomputes fantasy points from NFL statistics
under a league's ``scoring_settings``. The dbt seed ``scoring_stat_map.csv`` is generated from
this table (``league-lab`` never edits the seed by hand) and the ``league_points`` macro reads it.

Two kinds of key:

* ``stat`` — a count or yardage the weekly stats carry directly (``rec`` -> ``receptions``).
  The expression is a ``+``-joined list of columns of the ``stg_nflverse__player_stats_week``
  shape. The long-touchdown keys (``pass_td_40p`` ...) are counts too, derived from
  play-by-play (``int_player_game_pbp``) and joined onto the stats row.
* ``bonus`` — a per-game threshold (``bonus_rec_yd_100`` = a 100-199 receiving-yard game). The
  expression is ``column:low:high`` (``high`` empty = no upper bound); it pays the weight once
  when ``low <= column < high``. Sleeper's yardage buckets are exclusive ranges: a 210-yard game
  pays ``bonus_rec_yd_200`` and not ``bonus_rec_yd_100``. The long-touchdown counts are filed
  as ``bonus`` too (plain column expression) so one switch leaves every bonus out.

Only offensive player and kicker keys are mapped. Team-defense keys (``sack``, ``int``,
``pts_allow_*`` ...) are intentionally unmapped: individual/team defense projection is out of
MVP1 scope, and observed DEF points still arrive from Sleeper's own ``players_points``.

Known approximations (documented in docs/METRICS.md):
* ``fgmiss``/``xpmiss``: Sleeper charges blocked kicks as misses; nflverse separates them, so the
  expression adds ``*_blocked``. The distance buckets ``fgmiss_0_19`` ... map to nflverse's
  ``fg_missed_*`` buckets, which do not include blocked kicks (nflverse has no per-distance
  blocked buckets) — a blocked FG scores 0 there instead of the bucket's penalty.
* ``fgm_50p`` / ``fgmiss_50p`` = 50-59 + 60+ buckets.
* ``fum`` (any fumble) uses ``fumbles_total``; ``fum_lost`` uses ``fumbles_lost_total``.
* Long-touchdown keys count plays with ``yards_gained >= 40`` (``>= 50``) that scored, by the
  passer / rusher / receiver on the play (laterals credit the first receiver).
* Position-conditional catch premiums (``bonus_rec_te``, ``bonus_rec_rb``, ``bonus_rec_wr``:
  ``SLEEPER_POSITION_MAP``, plan F1) are priced by ``compute_points`` when the stats row carries the
  player's ``position`` (the projection's ``price`` passes it), and only then. They stay OUT of
  ``MAPPED_KEYS`` and of the seed: the SQL ``league_points`` macro has no position to condition on,
  so ``unmapped_keys`` keeps reporting them and dbt's reconciliation test still flags a league that
  enables one instead of silently under-counting. The ``*_fd`` first-down keys are unmapped.
* Expected points (``int_expected_points_week``) apply the ``stat`` keys only: a threshold on an
  expected yardage would pay a bonus deterministically at 100.0 expected yards and not at 99.9.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

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
    "fgmiss_0_19": ("fg_missed_0_19", "FG missed 0-19 (blocked kicks not bucketed by nflverse)"),
    "fgmiss_20_29": ("fg_missed_20_29", "FG missed 20-29"),
    "fgmiss_30_39": ("fg_missed_30_39", "FG missed 30-39"),
    "fgmiss_40_49": ("fg_missed_40_49", "FG missed 40-49"),
    "fgmiss_50p": ("fg_missed_50_59 + fg_missed_60_", "FG missed 50+"),
    "xpm": ("pat_made", "PAT made"),
    "xpmiss": ("pat_missed + pat_blocked", "PAT missed incl. blocked"),
}

# Long-touchdown keys: counts derived from play-by-play (int_player_game_pbp), joined onto the
# stats row by the models that score. kind = bonus so expected points leave them out.
SLEEPER_LONG_TD_MAP: dict[str, tuple[str, str]] = {
    "pass_td_40p": ("pass_tds_40p", "passing TDs of 40+ yards (play-by-play)"),
    "pass_td_50p": ("pass_tds_50p", "passing TDs of 50+ yards (play-by-play)"),
    "rush_td_40p": ("rush_tds_40p", "rushing TDs of 40+ yards (play-by-play)"),
    "rush_td_50p": ("rush_tds_50p", "rushing TDs of 50+ yards (play-by-play)"),
    "rec_td_40p": ("rec_tds_40p", "receiving TDs of 40+ yards (play-by-play)"),
    "rec_td_50p": ("rec_tds_50p", "receiving TDs of 50+ yards (play-by-play)"),
}

# Per-game yardage bonuses: sleeper_key -> (column, low, high_exclusive | None, description).
# Sleeper's buckets are exclusive ranges (100-199, 200+), so exactly one pays for a given game.
SLEEPER_BONUS_MAP: dict[str, tuple[str, int, int | None, str]] = {
    "bonus_pass_yd_300": ("passing_yards", 300, 400, "300-399 passing yard game"),
    "bonus_pass_yd_400": ("passing_yards", 400, None, "400+ passing yard game"),
    "bonus_rush_yd_100": ("rushing_yards", 100, 200, "100-199 rushing yard game"),
    "bonus_rush_yd_200": ("rushing_yards", 200, None, "200+ rushing yard game"),
    "bonus_rec_yd_100": ("receiving_yards", 100, 200, "100-199 receiving yard game"),
    "bonus_rec_yd_200": ("receiving_yards", 200, None, "200+ receiving yard game"),
}

# Position-conditional per-catch premiums (plan F1, the TE-premium reference scoring): sleeper_key ->
# (stat column, position, description). Priced by compute_points only for a stats row that carries
# ``position``; not in MAPPED_KEYS / the seed (the SQL macro cannot condition on position).
SLEEPER_POSITION_MAP: dict[str, tuple[str, str, str]] = {
    "bonus_rec_te": ("receptions", "TE", "per catch by a tight end (TE premium)"),
    "bonus_rec_rb": ("receptions", "RB", "per catch by a running back"),
    "bonus_rec_wr": ("receptions", "WR", "per catch by a wide receiver"),
}

# Every key League Lab can recompute, with its kind.
MAPPED_KEYS: dict[str, str] = (
    {k: "stat" for k in SLEEPER_STAT_MAP}
    | {k: "bonus" for k in SLEEPER_LONG_TD_MAP}
    | {k: "bonus" for k in SLEEPER_BONUS_MAP}
)

# Python evaluation of the same expressions (used by tests and the synthetic fixture generator).
_PY_EXPR: dict[str, tuple[str, ...]] = {
    k: tuple(part.strip() for part in expr.split("+"))
    for k, (expr, _) in {**SLEEPER_STAT_MAP, **SLEEPER_LONG_TD_MAP}.items()
}


def bonus_hit(stats: Mapping[str, float | int | None], key: str) -> int:
    """1 when a yardage-bonus key pays for this stat row, else 0."""
    column, low, high = SLEEPER_BONUS_MAP[key][:3]
    value = float(stats.get(column) or 0)
    return int(value >= low and (high is None or value < high))


def compute_points(
    stats: Mapping[str, float | int | None], scoring: Mapping[str, float], *, include_bonuses: bool = True
) -> float:
    """Fantasy points for one player-game row under a Sleeper ``scoring_settings`` dict.

    ``include_bonuses=False`` scores the ``stat`` keys only (what expected points use). A position-
    conditional premium (``SLEEPER_POSITION_MAP``) counts when ``stats["position"]`` is its position
    (a per-catch value, so it counts with or without bonuses); a row without ``position`` prices it 0.
    """
    total = 0.0
    for key, weight in scoring.items():
        if not weight:
            continue
        kind = MAPPED_KEYS.get(key)
        if kind is None:
            pk = SLEEPER_POSITION_MAP.get(key)
            if pk is not None and stats.get("position") == pk[1]:
                total += float(stats.get(pk[0]) or 0) * float(weight)
            continue
        if kind == "bonus" and not include_bonuses:
            continue
        if key in SLEEPER_BONUS_MAP:
            value = float(bonus_hit(stats, key))
        else:
            value = sum(float(stats.get(c) or 0) for c in _PY_EXPR[key])
        total += value * float(weight)
    return round(total, 2)


def unmapped_keys(scoring: Mapping[str, float]) -> list[str]:
    """Scoring keys with a non-zero weight that the stat map (and so the SQL macro) cannot recompute (DEF,
    first downs...). The position-conditional premiums are listed too: only a stats row that carries the
    player's position prices them (``priced_keys`` is the projection's view)."""
    return sorted(k for k, w in scoring.items() if w and k not in MAPPED_KEYS)


def priced_keys(scoring: Mapping[str, float], columns: Iterable[str] | None = None) -> dict[str, float]:
    """The non-zero keys ``compute_points`` prices (``MAPPED_KEYS`` + the position premiums), as floats; with
    ``columns``, only the keys whose stat columns are all among them (the projected QB-TE line: kicking, 2-pt
    and long-TD keys price 0 on it). Two scorings with the same ``priced_keys(..., line columns)`` price every
    projected line identically (plan F1: how a league is matched to a reference scoring)."""
    keep = None if columns is None else set(columns)
    out: dict[str, float] = {}
    for k, w in scoring.items():
        if not w:
            continue
        if k in SLEEPER_POSITION_MAP:
            cols = {SLEEPER_POSITION_MAP[k][0]}
        elif k in SLEEPER_BONUS_MAP:
            cols = {SLEEPER_BONUS_MAP[k][0]}
        elif k in _PY_EXPR:
            cols = set(_PY_EXPR[k])
        else:
            continue
        if keep is None or cols <= keep:
            out[k] = float(w)
    return out


def seed_rows() -> list[dict[str, str]]:
    rows = [
        {"sleeper_key": k, "kind": "stat", "stat_expression": expr, "description": desc}
        for k, (expr, desc) in SLEEPER_STAT_MAP.items()
    ]
    rows += [
        {"sleeper_key": k, "kind": "bonus", "stat_expression": expr, "description": desc}
        for k, (expr, desc) in SLEEPER_LONG_TD_MAP.items()
    ]
    rows += [
        {
            "sleeper_key": k,
            "kind": "bonus",
            "stat_expression": f"{column}:{low}:{'' if high is None else high}",
            "description": desc,
        }
        for k, (column, low, high, desc) in SLEEPER_BONUS_MAP.items()
    ]
    return rows


def write_seed(path: str) -> None:
    """Regenerate ``dbt/seeds/scoring_stat_map.csv`` (rule 8 in AGENTS.md)."""
    import csv

    rows = seed_rows()
    with open(path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
