-- depends_on: {{ ref('scoring_stat_map') }}
-- Plan F1 (Wave F): ops.projection_ranges.proj_points is the ops.projection_lines stat line priced in the reference
-- scoring, re-priced here with the SQL macro every league's actual points use (league_points; the line has no
-- kicking, 2-pt or long-TD columns: zero_stat_columns). Checked for the two house scorings (scrubs, dynasty);
-- te_premium's bonus_rec_te is priced in Python only (the macro has no position, docs/METRICS.md). Also: no range
-- row without its line. A row here is a violation.
-- warn, not error: it compares stored rows with the seed as built now, and the nightly's full build runs BEFORE
-- `project` — an error here would stop the night before the refit that rewrites the live weeks (a reference's
-- settings are never edited: add a new name instead, docs/METRICS.md § "NFL-wide outputs").
{{ config(severity='warn') }}
{%- set line_columns = ['targets', 'receptions', 'receiving_yards', 'receiving_tds', 'carries', 'rushing_yards',
    'rushing_tds', 'attempts', 'passing_yards', 'passing_tds', 'passing_interceptions', 'fumbles_lost_total'] %}

with l as (
    select season, week, gsis_id,
           {%- for c in line_columns %}
           proj_{{ c }} as {{ c }},
           {%- endfor %}
           {{ zero_stat_columns(line_columns) }}
    from {{ source('ops', 'projection_lines') }}
),

r as (
    select r.scoring_name, r.season, r.week, r.gsis_id, r.proj_points, s.scoring_settings
    from {{ source('ops', 'projection_ranges') }} as r
    join {{ ref('reference_scorings') }} as s on s.name = r.scoring_name
    where r.scoring_name in ('scrubs', 'dynasty')
)

select r.scoring_name, r.season, r.week, r.gsis_id, r.proj_points,
       {{ league_points('r.scoring_settings', 'l') }} as sql_points,
       'priced line differs' as problem
from r
join l using (season, week, gsis_id)
where abs(r.proj_points - {{ league_points('r.scoring_settings', 'l') }}) > 1e-6

union all

select r.scoring_name, r.season, r.week, r.gsis_id, r.proj_points, null, 'range without a line' as problem
from {{ source('ops', 'projection_ranges') }} as r
left join l using (season, week, gsis_id)
where l.gsis_id is null
