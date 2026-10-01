"""Feature group ``rookie_prior`` (plan E4, Wave E): draft capital and age as the prior for a player with little history.

Andrew: "what else could make this better". v3 projects a player from his own games (``games_to_date``,
``prev_games``, his per-game rates) and his position's average last season (``pos_prev_ppg``); a rookie in weeks
1-4 has almost nothing of his own, and the model cannot tell a first-round back from an undrafted one. The
hypothesis: where he was drafted (the league's own pre-season opinion of him) and how old he is carry the prior
until his games take over.

The table is ``intermediate.int_e4_player_week_rookie_prior`` (dbt, ``dbt/models/intermediate/features/``): one row
per ``int_player_week_universe`` row, static within a season, from ``raw.nfl_players`` (draft round / overall pick /
draft year, rookie season, birth date) - all fixed before the season, nothing read from a game. Definitions:
``docs/METRICS.md`` § "Feature experiments" -> "Wave E groups".

The Python twins below are the rules the SQL hard-codes (``tests/test_e4_feature_groups.py`` pins them on fixtures
and, with a database, reproduces every 2025 row).
"""

from __future__ import annotations

from datetime import date

TABLE = "intermediate.int_e4_player_week_rookie_prior"


def draft_tier(in_players_table: bool, draft_round: int | None) -> int | None:
    """3 = 1st round, 2 = day 2 (rounds 2-3), 1 = day 3 (rounds 4-7), 0 = undrafted; None = unknown player."""
    if not in_players_table:
        return None
    if draft_round is None:
        return 0
    return 3 if draft_round == 1 else 2 if draft_round <= 3 else 1


def years_in(season: int, draft_year: int | None, rookie_season: int | None) -> int | None:
    """Seasons since he entered the league (draft year; an undrafted player's rookie season), floored at 0."""
    entry = draft_year if draft_year is not None else rookie_season
    return None if entry is None else max(0, season - entry)


def age_on_sep1(season: int, birth_date: date | None) -> float | None:
    """Age in years on September 1 of the season, one decimal (days / 365.25, as the SQL)."""
    return None if birth_date is None else round((date(season, 9, 1) - birth_date).days / 365.25, 1)


COLUMNS = ["rk_draft_round", "rk_draft_pick", "rk_draft_tier", "rk_undrafted", "rk_years_in", "rk_is_rookie", "rk_age"]
EARLY_WEEKS = 4             # rookie_prior_early: the columns in weeks 1-4 only (the subset where the full group moved)
EARLY = [c.replace("rk_", "rk_early_", 1) for c in COLUMNS]

GROUPS = {
    "rookie_prior": {
        "table": TABLE, "columns": COLUMNS,
        "label": "Draft capital and age",
        "note": "E4: draft round, overall pick, draft tier (1st / day 2 / day 3 / undrafted), undrafted flag, years in "
                "the league, rookie flag, age on Sep 1 - the league's pre-season opinion of a player with little history",
    },
    "rookie_prior_early": {
        "table": TABLE, "columns": EARLY,
        "label": "Draft capital and age, first four weeks",
        "note": "E4: the same seven inputs in weeks 1-4 only (NULL from week 5 on): the prior while his season has "
                "little history, nothing after",
    },
}
