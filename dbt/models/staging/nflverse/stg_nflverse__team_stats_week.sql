-- Team totals per game: the opportunity denominators. Independent of the player table
-- (plan §5: never derive team totals by summing participant rows).
select
    team,
    season,
    week,
    season_type,
    game_id,
    opponent_team,
    completions, attempts, passing_yards, passing_tds, passing_interceptions,
    sacks_suffered, sack_yards_lost, passing_air_yards, passing_yards_after_catch,
    passing_first_downs, passing_epa,
    carries, rushing_yards, rushing_tds, rushing_first_downs, rushing_epa,
    receptions, targets, receiving_yards, receiving_tds, receiving_air_yards,
    receiving_yards_after_catch, receiving_first_downs,
    fumbles_total, fumbles_lost_total, penalties, penalty_yards,
    -- dropbacks here = pass attempts + sacks. Scrambles need play-by-play (Phase 2), so this
    -- undercounts true dropbacks slightly; the column name says so.
    attempts + sacks_suffered                   as dropbacks_excl_scrambles,
    attempts + sacks_suffered + carries         as plays_excl_scrambles,
    _fetched_at                                 as source_fetched_at
from {{ source('raw', 'nfl_team_stats_week') }}
where season >= {{ var('seasons_start') }}
