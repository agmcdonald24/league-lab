select
    league_id,
    week,
    roster_id,
    matchup_id,
    points::numeric          as points,
    custom_points::numeric   as custom_points,
    starters          as starter_ids,
    starters_points,
    players           as player_ids,
    players_points,
    fetched_at
from {{ source('raw', 'sleeper_matchup') }}
