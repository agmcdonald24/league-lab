-- One row per league-season in the chain. Settings are promoted from the JSON payload.
select
    league_id,
    season::integer                                                  as season,
    name                                                             as league_name,
    status,
    previous_league_id,
    draft_id,
    total_rosters,
    (payload -> 'settings' ->> 'num_teams')::integer                 as num_teams,
    (payload -> 'settings' ->> 'playoff_week_start')::integer        as playoff_week_start,
    (payload -> 'settings' ->> 'playoff_teams')::integer             as playoff_teams,
    (payload -> 'settings' ->> 'last_scored_leg')::integer           as last_scored_leg,
    (payload -> 'settings' ->> 'leg')::integer                       as current_leg,
    (payload -> 'settings' ->> 'trade_deadline')::integer            as trade_deadline_week,
    (payload -> 'settings' ->> 'waiver_type')::integer               as waiver_type,
    (payload -> 'settings' ->> 'waiver_budget')::integer             as waiver_budget,
    -- Sleeper: 0 = redraft, 1 = keeper, 2 = dynasty
    case (payload -> 'settings' ->> 'type')::integer when 2 then 'dynasty' when 1 then 'keeper' else 'redraft' end as league_type,
    payload -> 'scoring_settings'                                    as scoring_settings,
    payload -> 'roster_positions'                                    as roster_positions,
    (payload -> 'scoring_settings' ->> 'rec')::numeric               as ppr_value,
    fetched_at
from {{ source('raw', 'sleeper_league') }}
