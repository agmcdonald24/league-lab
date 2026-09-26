select
    league_id,
    user_id,
    display_name,
    coalesce(team_name, display_name) as team_name,
    is_owner                          as is_commissioner,
    avatar,
    fetched_at
from {{ source('raw', 'sleeper_league_user') }}
