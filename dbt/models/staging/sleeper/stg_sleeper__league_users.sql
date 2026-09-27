select
    league_id,
    user_id,
    display_name,
    btrim(coalesce(team_name, display_name)) as team_name,   -- Sleeper keeps trailing spaces users typed
    is_owner                          as is_commissioner,
    avatar,
    fetched_at
from {{ source('raw', 'sleeper_league_user') }}
