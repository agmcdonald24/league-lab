-- Who owns whom right now, per league-season (from the current roster payloads).
with r as (
    select league_id, roster_id, player_ids, starter_ids, reserve_ids, taxi_ids
    from {{ ref('stg_sleeper__rosters') }}
)
select
    r.league_id,
    l.season,
    r.roster_id,
    m.team_name,
    m.manager_name,
    pid                                          as sleeper_player_id,
    idm.gsis_id,
    coalesce(sp.full_name, pid)                  as player_name,
    sp.position,
    sp.team                                      as nfl_team,
    pid = any(coalesce(r.starter_ids, '{}'))     as is_current_starter,
    pid = any(coalesce(r.reserve_ids, '{}'))     as is_on_ir,
    pid = any(coalesce(r.taxi_ids, '{}'))        as is_on_taxi
from r
cross join lateral unnest(coalesce(r.player_ids, '{}')) as pid
join {{ ref('dim_league_season') }} as l using (league_id)
left join {{ ref('dim_league_member') }} as m using (league_id, roster_id)
left join {{ ref('stg_sleeper__players') }} as sp on sp.sleeper_player_id = pid
left join {{ ref('player_id_map') }} as idm on idm.sleeper_id = pid
