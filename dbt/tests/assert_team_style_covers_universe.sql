-- D4 (feature-table contract, plan Iteration 12): int_player_week_team_style has exactly one row per row of
-- int_player_week_universe - none missing, none extra - and its offense / defense are the universe's team and
-- opponent for that week (a player's row never carries another team's numbers).
{{ config(severity='error') }}
select coalesce(u.gsis_id, t.gsis_id) as gsis_id, coalesce(u.season, t.season) as season, coalesce(u.week, t.week) as week,
       case when t.gsis_id is null then 'universe row missing' else 'row outside the universe' end as problem
from {{ ref('int_player_week_universe') }} as u
full join {{ ref('int_player_week_team_style') }} as t using (gsis_id, season, week)
where u.gsis_id is null or t.gsis_id is null
union all
select t.gsis_id, t.season, t.week, 'offense numbers are not his team''s'
from {{ ref('int_player_week_team_style') }} as t
join {{ ref('int_player_week_universe') }} as u using (gsis_id, season, week)
join {{ ref('int_team_week_style') }} as o on o.team = {{ kd_team('u.team') }} and o.season = u.season and o.week = u.week
join {{ ref('int_team_week_style') }} as d on d.team = {{ kd_team('u.opponent') }} and d.season = u.season and d.week = u.week
where t.ts_off_plays_pg_std is distinct from o.off_plays_pg_std
   or t.ts_def_neutral_pass_rate_std is distinct from d.def_neutral_pass_rate_std
   or t.ts_off_games is distinct from o.off_games
