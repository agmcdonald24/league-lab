{{ config(
    materialized='view',
    pre_hook="create table if not exists ops.projection_drift (run_at timestamptz, model_version text, league_id text, season integer, week integer, position text, n_players integer, spearman double precision, top_n integer, hit_rate double precision, mae double precision, coverage_80 double precision, interval_width double precision, games_played integer, games_scheduled integer, frozen_share double precision); alter table ops.projection_drift add column if not exists frozen_share double precision"
) }}
-- Drift monitor (plan M-06): how the live projection v2 board has done on the weeks of the projected
-- season already played (from `ops.projection_drift`, written by `league-lab drift` and at the end of
-- `league-lab project`), next to what the walk-forward backtest measured for the same league and
-- position (`mart_projection_backtest`, scorer v2_points, averaged over its held-out seasons).
-- Season means use COMPLETE weeks only (every scheduled game has players in): a week still being
-- played is a handful of players from a couple of teams, so it is reported as `week_in_progress`
-- and joins the averages once its last game is in.
-- B5: `frozen_share` = share of the scored player-weeks (complete weeks) whose projection is the board
-- as published before that week's first kickoff (the frozen record); `refit_weeks` lists the complete
-- weeks scored on refit values instead (played before the freeze existed: 2026 weeks 1-3).
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
        round((sum(n_players * coalesce(frozen_share, 0)) filter (where is_complete_week)
               / nullif(sum(n_players) filter (where is_complete_week), 0))::numeric, 3)  as frozen_share,
        string_agg(week::text, ', ' order by week)
            filter (where is_complete_week and coalesce(frozen_share, 0) < 1)             as refit_weeks,
        max(model_version)                                                                as model_version,
        max(run_at)                                                                       as run_at
    from d
    group by 1, 2, 3
),

backtest as (
    select
        league_id,
        position,
        model_version,
        min(season)::text || '–' || max(season)::text                                    as backtest_seasons,
        sum(weeks)                                                                        as backtest_weeks,
        avg(spearman)                                                                     as backtest_spearman,
        avg(hit_rate)                                                                     as backtest_hit_rate,
        avg(mae)                                                                          as backtest_mae,
        avg(coverage_80)                                                                  as backtest_coverage_80,
        avg(interval_width)                                                               as backtest_interval_width
    from {{ ref('mart_projection_backtest') }}
    where scorer = 'v2_points'                     -- v3: every QB-TE version's backtest, joined on the board's version
    group by 1, 2, 3
),

-- ---- IP-1 (Wave I-P): each complete week next to the backtest of the model that MADE it (2026 weeks 1-3 were v2.0's;
-- joining the season's newest version put v2.0's 6.5 at QB beside v3.0's 5.4), the newest backtested version at or
-- before the week's own when that one has none (v3.3 / v3.4 add line blends that backtest-v2 does not run: v3.0's
-- model); the season's backtest = the mean over its complete weeks, as the season's own numbers are
week_backtest as (
    select d.league_id, d.season, d.position, d.week, bt.model_version as backtest_model_version,
           bt.backtest_spearman, bt.backtest_hit_rate, bt.backtest_mae, bt.backtest_coverage_80, bt.backtest_interval_width
    from d
    left join lateral (
        select b.* from backtest as b
        where b.league_id = d.league_id and b.position = d.position and b.model_version <= d.model_version
        order by b.model_version desc
        limit 1
    ) as bt on true
    where d.is_complete_week
),

season_backtest as (
    select league_id, season, position,
           round(avg(backtest_spearman)::numeric, 3)                                         as backtest_spearman,
           round(avg(backtest_hit_rate)::numeric, 3)                                         as backtest_hit_rate,
           round(avg(backtest_mae)::numeric, 2)                                              as backtest_mae,
           round(avg(backtest_coverage_80)::numeric, 3)                                      as backtest_coverage_80,
           round(avg(backtest_interval_width)::numeric, 1)                                   as backtest_interval_width,
           max(backtest_model_version)                                                       as backtest_model_version
    from week_backtest
    group by 1, 2, 3
)
-- ---- end IP-1

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
    coalesce(sb.backtest_spearman, round(b.backtest_spearman::numeric, 3))               as backtest_spearman,
    s.hit_rate,
    coalesce(sb.backtest_hit_rate, round(b.backtest_hit_rate::numeric, 3))               as backtest_hit_rate,
    s.mae,
    coalesce(sb.backtest_mae, round(b.backtest_mae::numeric, 2))                         as backtest_mae,
    s.coverage_80,
    coalesce(sb.backtest_coverage_80, round(b.backtest_coverage_80::numeric, 3))         as backtest_coverage_80,
    s.interval_width,
    coalesce(sb.backtest_interval_width, round(b.backtest_interval_width::numeric, 1))   as backtest_interval_width,
    b.backtest_seasons,
    b.backtest_weeks,
    s.frozen_share,
    s.refit_weeks,
    s.model_version,
    s.run_at
from season as s
-- ---- IP-1: was "the backtest of the newest version on the board" (a season whose early weeks were frozen under v2.0
-- compared with v3.0's once a v3.0 week was scored). The labels (seasons, weeks) from the newest backtested version the season's weeks were scored against;
-- the numbers from season_backtest (each week's own model)
left join season_backtest as sb on sb.league_id = s.league_id and sb.season = s.season and sb.position = s.position
left join lateral (                -- no complete week yet: the newest backtested version at or before the board's
    select x.* from backtest as x
    where x.league_id = s.league_id and x.position = s.position
      and x.model_version <= coalesce(sb.backtest_model_version, s.model_version)
    order by x.model_version desc
    limit 1
) as b on true
