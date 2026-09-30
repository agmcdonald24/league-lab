-- depends_on: {{ ref('mart_lineup_recommendation') }}
-- League rankings of every current roster (plan B2), one row per league x roster x measure. Every rank
-- names its horizon (`horizon`: "week 4" or "weeks 4–7"), so no page shows a bare "3rd":
--   lineup_value   this week's best legal lineup (B1 proposed lineup)            horizon = this week
--   horizon_value  the sum of the proposed lineups of the next four weeks        horizon = weeks N–N+3
--   bench_value    depth: the best lineup the bench alone would field this week  horizon = this week
-- rank 1 = the highest value; ties share a rank (rank()); `n_rosters` = rosters ranked in the league.
{{ config(materialized='view') }}

with v as (
    select * from {{ ref('mart_league_roster_value') }}
),

long as (
    select league_id, season, roster_id, team_name, manager_name, week, 'lineup_value' as measure,
           'Lineup value' as measure_label, week_label as horizon, lineup_value as value
    from v
    union all
    select league_id, season, roster_id, team_name, manager_name, week, 'horizon_value',
           'Lineup value, next 4 weeks', horizon_label, horizon_value
    from v
    union all
    select league_id, season, roster_id, team_name, manager_name, week, 'bench_value',
           'Depth (bench lineup)', week_label, bench_value
    from v
)

select
    l.*,
    rank() over (partition by league_id, measure order by value desc)          as league_rank,
    count(*) over (partition by league_id, measure)                            as n_rosters,
    rank() over (partition by league_id, measure order by value desc) || '/'
        || count(*) over (partition by league_id, measure)                     as rank_label
from long as l
where l.value is not null
