select
    game_id, season, week, game_type, team, opponent, pfr_player_name, pfr_player_id,
    receiving_broken_tackles, receiving_drop, receiving_drop_pct, receiving_int, receiving_rat
from {{ source('raw', 'nfl_pfr_advstats_rec') }}
where season >= {{ var('seasons_start') }}
