-- IR-1 (Wave I-R, 2026-10-08; docs/METRICS.md § "Who cannot play"): De'Von Achane, on injured reserve, was the 21st
-- running back at 10.93. On the stored board (mart_player_week_projections, every league), for the live week (the
-- first regular-season week whose first game has not kicked off) and every later week: a player Sleeper's directory
-- (staging.stg_sleeper__players, the copy the nightly has just loaded — the copy `project`'s gate read) puts on a
-- reserve list with no return date (injured reserve, PUP, non-football injury, suspended: availability_gate's
-- out_indefinitely, read the same way: injury_status first, else the status in words) must have 0 this week and no
-- later week. A row here is a player who cannot play and is still projected.
-- Severity by var: warn inside the nightly's builds (the full build runs BEFORE `project`, on last night's board),
-- error when the PO's hard step runs it after `project` + projection-marts:
--   dbt test --select assert_nobody_who_cannot_play_is_projected --vars '{availability_gate_severity: error}'
{{ config(severity=var('availability_gate_severity', 'warn')) }}
with live as (
    select season, min(week) as week
    from (select season, week, min(kickoff_at) as first_kickoff
          from {{ ref('dim_game') }} where season_type = 'REG' group by season, week) as w
    where first_kickoff > now()
    group by season
),

directory as (
    select coalesce(nullif(p.gsis_id, ''), m.gsis_id) as gsis_id, p.full_name, p.injury_status, p.status, p.fetched_at,
           case
               when upper(coalesce(p.injury_status, '')) not in ('', 'NA', 'ACTIVE')
                   then upper(p.injury_status) in ('IR', 'PUP', 'NFI', 'SUS')
               else lower(coalesce(p.status, '')) in ('injured reserve', 'physically unable to perform',
                                                      'non-football injury', 'suspended')
           end as out_indefinitely
    from {{ ref('stg_sleeper__players') }} as p
    left join {{ ref('player_id_map') }} as m on m.sleeper_id = p.sleeper_player_id
)

select b.league_id, b.season, b.week, b.gsis_id, b.player_name, b.position, b.proj_points, d.injury_status, d.status,
       d.fetched_at
from {{ ref('mart_player_week_projections') }} as b
join live as l on l.season = b.season and b.week >= l.week
join directory as d on d.gsis_id = b.gsis_id
where d.out_indefinitely
  and ((b.week = l.week and coalesce(b.proj_points, 0) > 0) or (b.week > l.week and b.proj_points is not null))
