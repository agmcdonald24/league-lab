select
    p.draft_id,
    d.league_id,
    p.pick_no,
    p.round,
    p.draft_slot,
    p.roster_id,
    p.picked_by                                 as picked_by_user_id,
    p.player_id                                 as sleeper_player_id,
    coalesce(p.is_keeper, false)                as is_keeper,
    p.metadata ->> 'position'                   as drafted_position,
    p.metadata ->> 'team'                       as drafted_team,
    p.fetched_at
from {{ source('raw', 'sleeper_draft_pick') }} as p
left join {{ source('raw', 'sleeper_draft') }} as d using (draft_id)
