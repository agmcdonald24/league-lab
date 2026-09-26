select
    sport,
    season::integer          as season,
    season_type,
    week,
    leg,
    display_week,
    previous_season::integer as previous_season,
    season_start_date::date  as season_start_date,
    fetched_at
from {{ source('raw', 'sleeper_state') }}
