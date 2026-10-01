-- Plan E4: each Wave E feature table has exactly one row per int_player_week_universe row (the harness's no-peek
-- check refuses rows outside the universe and warns on missing ones; this makes both a build failure).
with u as (select gsis_id, season, week from {{ ref('int_player_week_universe') }}),
t as (
    select 'rookie_prior' as tbl, gsis_id, season, week from {{ ref('int_e4_player_week_rookie_prior') }}
    union all
    select 'oline_quality', gsis_id, season, week from {{ ref('int_e4_player_week_oline_quality') }}
    union all
    select 'qb_x_offense', gsis_id, season, week from {{ ref('int_e4_player_week_qb_x_offense') }}
)
select g.tbl, 'missing' as problem, u.gsis_id, u.season, u.week
from u cross join (select distinct tbl from t) as g
where not exists (select 1 from t where t.tbl = g.tbl and (t.gsis_id, t.season, t.week) = (u.gsis_id, u.season, u.week))
union all
select t.tbl, 'outside', t.gsis_id, t.season, t.week
from t where not exists (select 1 from u where (u.gsis_id, u.season, u.week) = (t.gsis_id, t.season, t.week))
