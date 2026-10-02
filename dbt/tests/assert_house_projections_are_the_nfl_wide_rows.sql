-- Plan F1 (Wave F): a house league whose scoring IS a reference scoring (the same scoring_settings) has QB-TE rows
-- in ops.projections that are the NFL-wide rows: the stat line of ops.projection_lines, and proj_points / P10-P90
-- of that reference's ops.projection_ranges (to 1e-9), with the same freeze label and fitted_at — every week,
-- frozen ones included, and no row on one side without the other. A row here is a violation.
-- warn, not error: a `project` whose NFL-wide write failed (reported by that step) leaves the two apart until the
-- next refit, and the nightly's full build runs BEFORE `project` — an error would stop the night that repairs it.
{{ config(severity='warn') }}
{%- set comps = ['targets', 'receptions', 'receiving_yards', 'receiving_tds', 'carries', 'rushing_yards', 'rushing_tds',
    'attempts', 'passing_yards', 'passing_tds', 'passing_interceptions', 'fumbles_lost_total'] %}
{%- set ranged = ['proj_points', 'p10', 'p25', 'p50', 'p75', 'p90'] %}

with house as (
    select d.league_id, s.name as scoring_name
    from {{ ref('dim_league_season') }} as d
    join {{ ref('reference_scorings') }} as s on s.scoring_settings = d.scoring_settings
    where d.is_current_season
),

seasons as (
    select distinct season from {{ source('ops', 'projection_lines') }}
),

p as (
    select p.*, h.scoring_name
    from {{ source('ops', 'projections') }} as p
    join house as h using (league_id)
    where p.position in ('QB', 'RB', 'WR', 'TE') and p.season in (select season from seasons)
),

r as (
    select r.*, h.league_id
    from {{ source('ops', 'projection_ranges') }} as r
    join house as h using (scoring_name)
),

l as (
    select l.*, h.league_id
    from {{ source('ops', 'projection_lines') }} as l
    cross join house as h
)

select p.league_id, p.season, p.week, p.gsis_id, 'differs from the line or the range' as problem
from p
join l using (league_id, season, week, gsis_id)
join r using (league_id, season, week, gsis_id)
where false
  {%- for c in comps %}
  or abs(coalesce(p.proj_{{ c }}, 0) - coalesce(l.proj_{{ c }}, 0)) > 1e-9
  {%- endfor %}
  {%- for c in ranged %}
  or (p.{{ c }} is null) <> (r.{{ c }} is null) or abs(p.{{ c }} - r.{{ c }}) > 1e-9
  {%- endfor %}
  or p.frozen_source is distinct from l.frozen_source or p.frozen_source is distinct from r.frozen_source
  or p.fitted_at is distinct from l.fitted_at or p.fitted_at is distinct from r.fitted_at

union all

select coalesce(p.league_id, r.league_id), coalesce(p.season, r.season), coalesce(p.week, r.week),
       coalesce(p.gsis_id, r.gsis_id), 'row on one side only'
from p
full join r using (league_id, season, week, gsis_id)
where p.gsis_id is null or r.gsis_id is null
