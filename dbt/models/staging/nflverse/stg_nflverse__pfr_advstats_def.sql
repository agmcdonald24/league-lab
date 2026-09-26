-- PFR advanced defense per player-game (coverage stats when targeted). PFR ids; mapped to gsis in
-- int_defender_game_coverage.
select
    game_id, pfr_game_id, season, week, game_type,
    case when game_type = 'REG' then 'REG' else 'POST' end as season_type,
    team, opponent, pfr_player_name, pfr_player_id,
    def_ints, def_targets, def_completions_allowed, def_completion_pct, def_yards_allowed,
    def_yards_allowed_per_cmp, def_yards_allowed_per_tgt, def_receiving_td_allowed, def_passer_rating_allowed,
    def_adot, def_air_yards_completed, def_yards_after_catch, def_times_blitzed, def_times_hurried,
    def_times_hitqb, def_sacks, def_pressures, def_tackles_combined, def_missed_tackles, def_missed_tackle_pct
from {{ source('raw', 'nfl_pfr_advstats_def') }}
where season >= {{ var('seasons_start') }}
