-- D5 (personnel): the feature table is the universe, row for row, and its quarterback inputs only read games
-- before the week. Returns offending rows with the problem:
--   * a universe row missing, or a row outside the universe;
--   * proj_qb_id is not the schedule's starting QB of his team's game that week (raw.nfl_schedules), where the
--     schedule has one (v3: an unfilled future game falls back to the team's newest played start, 'last_start');
--   * usual_qb_id is not the starting QB of any game he played BEFORE the week (this season or last);
--   * pn_qb_is_rookie_or_backup disagrees with the projected starter's starts before the week counted on the raw
--     schedule (played games, any team, from 2016);
--   * pn_qb_games_together exceeds his own games before the week with >= 50% of the snaps.
{{ config(severity='error') }}
with p as (
    select * from {{ ref('int_player_week_personnel') }}
),

sched as (
    select s.season, s.week, {{ kd_team('t.team') }} as team, nullif(t.qb, '') as qb, s.home_score is not null as played
    from {{ source('raw', 'nfl_schedules') }} as s
    cross join lateral (values (s.home_team, s.home_qb_id), (s.away_team, s.away_qb_id)) as t(team, qb)
    where s.game_type = 'REG' and s.season >= {{ var('seasons_start') }}
),

raw_starts as (
    select p.gsis_id, p.season, p.week, count(s.*) as starts
    from p join sched as s on s.qb = p.proj_qb_id and s.played and (s.season, s.week) < (p.season, p.week)
    group by 1, 2, 3
)

select coalesce(u.gsis_id, p.gsis_id) as gsis_id, coalesce(u.season, p.season) as season, coalesce(u.week, p.week) as week,
       case when p.gsis_id is null then 'universe row missing' else 'row outside the universe' end as problem
from {{ ref('int_player_week_universe') }} as u
full join p using (gsis_id, season, week)
where u.gsis_id is null or p.gsis_id is null

union all
select p.gsis_id, p.season, p.week, 'proj_qb_id is not the schedule''s starter of the week'
from p
left join sched as s on s.season = p.season and s.week = p.week and s.team = p.team
where (s.qb is not null and p.proj_qb_id is distinct from s.qb)
   or (s.qb is null and s.played)                                      -- a played game always has its starter
   or (s.qb is null and p.proj_qb_source is distinct from 'last_start' and p.proj_qb_id is not null)

union all
select p.gsis_id, p.season, p.week, 'usual_qb_id is not from a game he played before the week'
from p
where p.usual_qb_id is not null
  and not exists (select 1 from {{ ref('int_pn_player_game') }} as g
                  where g.gsis_id = p.gsis_id and g.played and g.starting_qb_id = p.usual_qb_id
                    and (g.season = p.season - 1 or (g.season = p.season and g.week < p.week)))

union all
select p.gsis_id, p.season, p.week, 'pn_qb_is_rookie_or_backup disagrees with the raw schedule''s starts before the week'
from p
left join raw_starts as r using (gsis_id, season, week)
where p.proj_qb_id is not null and p.pn_qb_is_rookie_or_backup is distinct from (coalesce(r.starts, 0) < 8)::int

union all
select p.gsis_id, p.season, p.week, 'pn_qb_games_together counts games at or after the week'
from p
where p.pn_qb_games_together > (select count(*) from {{ ref('int_pn_player_game') }} as g
                                where g.gsis_id = p.gsis_id and g.snap_share >= 0.5 and (g.season, g.week) < (p.season, p.week))
