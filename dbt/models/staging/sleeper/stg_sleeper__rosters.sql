-- Current roster state per league-season (as of the last fetch). Season-end state for
-- completed seasons; live state for the current one.
select
    league_id,
    roster_id,
    owner_id,
    co_owners,
    players                                                   as player_ids,
    starters                                                  as starter_ids,
    reserve                                                   as reserve_ids,
    taxi                                                      as taxi_ids,
    (settings ->> 'wins')::integer                            as wins,
    (settings ->> 'losses')::integer                          as losses,
    (settings ->> 'ties')::integer                            as ties,
    (settings ->> 'fpts')::numeric
        + coalesce((settings ->> 'fpts_decimal')::numeric, 0) / 100      as points_for,
    (settings ->> 'fpts_against')::numeric
        + coalesce((settings ->> 'fpts_against_decimal')::numeric, 0) / 100 as points_against,
    (settings ->> 'ppts')::numeric
        + coalesce((settings ->> 'ppts_decimal')::numeric, 0) / 100      as potential_points,
    (settings ->> 'waiver_position')::integer                 as waiver_position,
    (settings ->> 'waiver_budget_used')::integer              as waiver_budget_used,
    (settings ->> 'total_moves')::integer                     as total_moves,
    metadata ->> 'record'                                     as record_string,
    metadata ->> 'streak'                                     as streak,
    fetched_at
from {{ source('raw', 'sleeper_roster') }}
