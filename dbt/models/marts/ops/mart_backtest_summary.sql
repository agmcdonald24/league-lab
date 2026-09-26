{{ config(
    materialized='view',
    pre_hook="create table if not exists ops.backtest_results (run_id text, run_at timestamptz, season integer, week integer, position text, scorer text, n_players integer, spearman double precision, top_n integer, hit_rate double precision, mae double precision, top_n_actual_ppg double precision, top_n_picked_ppg double precision)"
) }}
-- The source table is created by `league-lab db migrate` and filled by `league-lab backtest`; the
-- pre-hook creates it empty when a build runs on a machine whose ops schema predates it.
-- Rankings backtest scoreboard (from `league-lab backtest`): how the baseline projection and the
-- naive scorers did on held-out seasons, averaged over season-weeks. Read it before trusting a rank.
select
    season,
    position,
    scorer,
    case scorer
        when 'proj_points' then 'League Lab baseline'
        when 'naive_ppg_std' then 'Season PPG to date'
        when 'naive_ppg_l3' then 'Last-3 PPG'
        when 'naive_xppg_l5' then 'Expected points (L5)'
        else scorer end                                  as scorer_label,
    count(*)                                             as weeks,
    max(top_n)                                           as top_n,
    round(avg(spearman)::numeric, 3)                     as spearman,
    round(avg(hit_rate)::numeric, 3)                     as hit_rate,
    round(avg(mae)::numeric, 2)                          as mae,
    round(avg(top_n_picked_ppg)::numeric, 2)             as top_n_picked_ppg,
    round(avg(top_n_actual_ppg)::numeric, 2)             as top_n_ceiling_ppg,
    max(run_at)                                          as run_at
from {{ source('ops', 'backtest_results') }}
group by 1, 2, 3, 4
