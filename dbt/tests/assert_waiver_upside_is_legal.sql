-- Plan R-12: every upside stash is a legal claim on the rosters it was computed on (the same rules as
-- assert_waiver_moves_are_legal): the add is a free agent in this league on an active NFL roster, not
-- Out / IR; the drop is on this roster, not in its IR slot or on its taxi squad, not locked this week;
-- no drop only with an open roster spot. Only leagues unchanged since the rows were computed.
{{ config(severity='error') }}
with u as (
    select * from {{ ref('mart_waiver_upside') }} where inputs_current
),

locked as (
    select league_id, season, week, roster_id, sleeper_player_id
    from {{ source('ops', 'lineups') }}
    where not is_realised and (is_locked or reason = 'game started (bench)')
)

select 'add is not a free agent on an active NFL roster (or is Out / IR)' as problem, u.league_id, u.roster_id, u.add_sleeper_id, u.drop_sleeper_id
from u
left join {{ ref('mart_player_availability') }} as a on a.league_id = u.league_id and a.sleeper_id = u.add_sleeper_id
where a.sleeper_id is null or not a.is_free_agent or a.roster_status is distinct from 'ACT' or a.injury_status in ('Out', 'IR')

union all

select 'drop is not on this roster, or is in its IR slot / on its taxi squad', u.league_id, u.roster_id, u.add_sleeper_id, u.drop_sleeper_id
from u
left join {{ ref('mart_league_roster_membership') }} as d
       on d.league_id = u.league_id and d.roster_id = u.roster_id and d.sleeper_player_id = u.drop_sleeper_id
where u.drop_sleeper_id is not null and (d.sleeper_player_id is null or coalesce(d.is_on_ir, false) or coalesce(d.is_on_taxi, false))

union all

select 'drop is locked this week', u.league_id, u.roster_id, u.add_sleeper_id, u.drop_sleeper_id
from u
join locked as l on l.league_id = u.league_id and l.season = u.season and l.week = u.week and l.roster_id = u.roster_id
                and l.sleeper_player_id = u.drop_sleeper_id

union all

select 'no drop without an open roster spot', u.league_id, u.roster_id, u.add_sleeper_id, u.drop_sleeper_id
from u
where u.drop_sleeper_id is null and coalesce(u.open_roster_spots, 0) <= 0
