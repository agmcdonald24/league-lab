-- Plan F1 (Wave F): the B5 freeze labels on the NFL-wide tables are as honest as on ops.projections
-- (assert_frozen_projections_precede_kickoff, the same five rules). The freeze unit is the week for the line
-- tables (ops.projection_lines, ops.kd_lines) and the scoring x week for the range tables (ops.projection_ranges,
-- ops.kd_ranges).
-- * a 'kickoff' row says when its board was published (frozen_at = fitted_at) and that precedes the week's first kickoff;
-- * a 'refit' row carries no frozen_at;
-- * a row written after its week's first kickoff is never left live (unlabelled);
-- * one label per unit, and no other label value.
-- A row here is a violation.
with kickoff as (
    select season, week, min(kickoff_at) as first_kickoff
    from {{ ref('dim_game') }}
    group by 1, 2
),

rows_ as (
    select 'projection_lines' as tbl, 'week' as unit, season, week, gsis_id as row_key, frozen_source, frozen_at, fitted_at
    from {{ source('ops', 'projection_lines') }}
    union all
    select 'projection_ranges', scoring_name, season, week, gsis_id, frozen_source, frozen_at, fitted_at
    from {{ source('ops', 'projection_ranges') }}
    union all
    select 'kd_lines', 'week', season, week, position || ':' || unit_id, frozen_source, frozen_at, fitted_at
    from {{ source('ops', 'kd_lines') }}
    union all
    select 'kd_ranges', scoring_name, season, week, position || ':' || unit_id, frozen_source, frozen_at, fitted_at
    from {{ source('ops', 'kd_ranges') }}
),

p as (
    select r.*, k.first_kickoff
    from rows_ as r
    left join kickoff as k using (season, week)
),

mixed as (
    select tbl, unit, season, week
    from p
    group by 1, 2, 3, 4
    having count(distinct coalesce(frozen_source, '(live)')) > 1
)

select *, 'kickoff row without a pre-kickoff frozen_at' as problem
from p
where frozen_source = 'kickoff'
  and (frozen_at is null or first_kickoff is null or frozen_at >= first_kickoff or frozen_at is distinct from fitted_at)

union all

select *, 'refit row with a frozen_at' as problem
from p
where frozen_source = 'refit' and frozen_at is not null

union all

select *, 'unknown frozen_source' as problem
from p
where frozen_source not in ('kickoff', 'refit')

union all

select *, 'written after kickoff but still live' as problem
from p
where frozen_source is null and fitted_at >= first_kickoff

union all

select p.*, 'more than one label in a unit' as problem
from p
join mixed using (tbl, unit, season, week)
