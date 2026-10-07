-- ---- IQ-2 (Wave I-Q): a hand-kept override sets the starter of UNPLAYED games only, inside its window, while in force
-- -- never a played game (a training row, a history input, the record). Returns offending team-games.
{{ config(severity='error') }}
with t as (select * from {{ ref('int_pn_team_game') }}),
o as (select * from {{ ref('int_starter_override') }})
select t.season, t.week, t.team, t.listed_qb_id, t.starting_qb_id, 'an override on a played game' as problem
from t where t.is_played and t.starter_source = 'override'
union all
select t.season, t.week, t.team, t.listed_qb_id, t.starting_qb_id, 'an override with no row in force for the game'
from t
where t.starter_source = 'override'
  and not exists (select 1 from o where o.in_force and o.season = t.season and o.team = t.team and o.gsis_id = t.starting_qb_id
                  and t.week >= o.from_week and (o.through_week is null or t.week <= o.through_week))
{%- if var('starter_overrides', true) %}
union all
select t.season, t.week, t.team, t.listed_qb_id, t.starting_qb_id, 'an unplayed game in a row''s window without it'
from t
join o on o.in_force and o.season = t.season and o.team = t.team and t.week >= o.from_week
      and (o.through_week is null or t.week <= o.through_week)
where not t.is_played and t.starter_source <> 'override'
{%- endif %}
-- ---- end IQ-2
