{{ config(
    materialized='view',
    pre_hook="create table if not exists ops.projection_drift (run_at timestamptz, model_version text, league_id text, season integer, week integer, position text, n_players integer, spearman double precision, top_n integer, hit_rate double precision, mae double precision, coverage_80 double precision, interval_width double precision, games_played integer, games_scheduled integer)"
) }}
-- Drift monitor (plan M-06): how the live projection v2 board has done on the weeks of the projected
-- season already played (from `ops.projection_drift`, written by `league-lab drift` and at the end of
-- `league-lab project`), next to what the walk-forward backtest measured for the same league and
-- position (`mart_projection_backtest`, scorer v2_points, averaged over its held-out seasons).
-- Season means use COMPLETE weeks only (every scheduled game has players in): a week still being
-- played is a handful of players from a couple of teams, so it is reported as `week_in_progress`
-- and joins the averages once its last game is in.
with d as (
    select *, games_played >= games_scheduled as is_complete_week
    from {{ source('ops', 'projection_drift') }}
),

season as (
    select
        league_id,
        season,
        position,
        count(*) filter (where is_complete_week)                                          as weeks_scored,
        min(week) filter (where is_complete_week)                                         as first_week,
        max(week) filter (where is_complete_week)                                         as last_week,
        max(week) filter (where not is_complete_week)                                     as week_in_progress,
        sum(n_players) filter (where is_complete_week)                                    as player_weeks,
        round((avg(spearman) filter (where is_complete_week))::numeric, 3)                as spearman,
        round((avg(hit_rate) filter (where is_complete_week))::numeric, 3)                as hit_rate,
        round((avg(mae) filter (where is_complete_week))::numeric, 2)                     as mae,
        round((avg(coverage_80) filter (where is_complete_week))::numeric, 3)             as coverage_80,
        round((avg(interval_width) filter (where is_complete_week))::numeric, 1)          as interval_width,
        max(model_version)                                                                as model_version,
        max(run_at)                                                                       as run_at
    from d
    group by 1, 2, 3
),

backtest as (
    select
        league_id,
        position,
        min(season)::text || '–' || max(season)::text                                    as backtest_seasons,
        sum(weeks)                                                                        as backtest_weeks,
        round(avg(spearman), 3)                                                           as backtest_spearman,
        round(avg(hit_rate), 3)                                                           as backtest_hit_rate,
        round(avg(mae), 2)                                                                as backtest_mae,
        round(avg(coverage_80), 3)                                                        as backtest_coverage_80,
        round(avg(interval_width), 1)                                                     as backtest_interval_width
    from {{ ref('mart_projection_backtest') }}
    where scorer = 'v2_points'
    group by 1, 2
)

select
    s.league_id,
    s.season,
    s.position,
    s.weeks_scored,
    s.first_week,
    s.last_week,
    s.week_in_progress,
    s.player_weeks,
    s.spearman,
    b.backtest_spearman,
    s.hit_rate,
    b.backtest_hit_rate,
    s.mae,
    b.backtest_mae,
    s.coverage_80,
    b.backtest_coverage_80,
    s.interval_width,
    b.backtest_interval_width,
    b.backtest_seasons,
    b.backtest_weeks,
    s.model_version,
    s.run_at
from season as s
left join backtest as b using (league_id, position)
