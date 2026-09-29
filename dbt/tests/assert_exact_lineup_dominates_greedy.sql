-- depends_on: {{ ref('mart_lineup_recommendation') }}
-- Plan B1: on every scored roster-week of the lineup season, the exact realised lineup (maximum-weight
-- matching over Sleeper's points, `ops.lineup_totals`) must reach Sleeper's max points — ties allowed,
-- never below. Sleeper publishes max points ("potential points", ppts) only per roster and season; the
-- per-week figure is `mart_league_optimal_lineup.points_optimal` (the greedy fill over the same Sleeper
-- points), which sums to Sleeper's ppts for every roster of both leagues in 2026 and is held to it by
-- `assert_optimal_lineup_matches_sleeper_potential`. So: exact >= greedy per roster-week (error), and
-- greedy = ppts per roster-season (warn, the existing test).
-- Rows fail when (a) the exact total is below the greedy one, or (b) a scored roster-week the lineup
-- service covers has no exact row. Only roster-weeks whose Sleeper points are unchanged since the
-- lineup was solved are compared (`inputs_fingerprint`, same expression as src/league_lab/lineup.py):
-- in the nightly the full dbt build runs before `league-lab project` re-solves, and a stat correction in
-- between must not fail the night — the rebuild after `project` then compares every row.
{{ config(severity='error') }}
with fresh as (
    select league_id, season, week, roster_id,
           md5(string_agg(sleeper_player_id || '=' || coalesce(points_observed::text, ''), ',' order by sleeper_player_id)) as fp
    from {{ ref('league_player_week') }}
    where is_scored_week
    group by 1, 2, 3, 4
),

exact as (
    select t.league_id, t.season, t.week, t.roster_id, t.lineup_value, t.run_at
    from {{ source('ops', 'lineup_totals') }} as t
    join fresh as f
      on f.league_id = t.league_id and f.season = t.season and f.week = t.week and f.roster_id = t.roster_id
     and f.fp = t.inputs_fingerprint
    where t.is_realised
),

-- the scored weeks the last lineup run covered, per league-season (a week scored after it is not yet due)
covered as (
    select league_id, season, max(week) as last_week, max(run_at) as run_at
    from {{ source('ops', 'lineup_totals') }}
    where is_realised
    group by 1, 2
),

greedy as (
    select g.league_id, g.season, g.week, g.roster_id, g.points_optimal
    from {{ ref('mart_league_optimal_lineup') }} as g
    join covered as c on c.league_id = g.league_id and c.season = g.season and g.week <= c.last_week
)

select 'exact below greedy' as problem, g.league_id, g.season, g.week, g.roster_id,
       e.lineup_value as exact_total, g.points_optimal as greedy_total,
       round((e.lineup_value - g.points_optimal)::numeric, 2) as diff
from greedy as g
join exact as e using (league_id, season, week, roster_id)
where e.lineup_value < g.points_optimal - 0.005

union all

select 'no exact lineup for a scored roster-week' as problem, g.league_id, g.season, g.week, g.roster_id,
       null, g.points_optimal, null
from greedy as g
where not exists (
    select 1 from {{ source('ops', 'lineup_totals') }} as t
    where t.is_realised and t.league_id = g.league_id and t.season = g.season and t.week = g.week and t.roster_id = g.roster_id
)
