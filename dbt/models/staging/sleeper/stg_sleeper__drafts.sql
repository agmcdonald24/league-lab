select
    draft_id,
    league_id,
    season::integer                              as season,
    type                                         as draft_type,
    status,
    to_timestamp(start_time / 1000.0)            as started_at,
    (settings ->> 'rounds')::integer             as rounds,
    (settings ->> 'teams')::integer              as teams,
    draft_order,
    slot_to_roster_id,
    metadata ->> 'scoring_type'                  as scoring_type,
    fetched_at
from {{ source('raw', 'sleeper_draft') }}
