{{ config(
    materialized='view',
    pre_hook="create table if not exists ops.projection_backtest (run_id text, run_at timestamptz, model_version text, train_seasons text, league_id text, season integer, week integer, position text, scorer text, n_players integer, spearman double precision, top_n integer, hit_rate double precision, mae double precision, coverage_80 double precision, pinball_10 double precision, pinball_50 double precision, pinball_90 double precision, interval_width double precision)"
) }}
-- Projection v2 scoreboard (from `league-lab backtest-v2`): walk-forward, per league and held-out
-- season, the v2 projection (priced line and P50) next to the OLS baseline, plus how often the
-- actual landed inside [P10, P90] (target 0.80). Read it before trusting an interval.
select
    league_id,
    season,
    train_seasons,
    position,
    scorer,
    case scorer
        when 'v2_points' then 'v2 · projected line, priced'
        when 'v2_p50' then 'v2 · P50 (median)'
        when 'baseline' then 'Baseline formula (reference scoring)'
        -- plan R-13 (model kd1.0, positions K / DEF): the model and its two PPG yardsticks
        when 'kd_points' then 'K/DEF model · projected line, priced'
        when 'season_ppg' then 'Season-to-date PPG'
        when 'last3_ppg' then 'Last-3-games PPG'
        else scorer end                                  as scorer_label,
    count(*)                                             as weeks,
    max(top_n)                                           as top_n,
    round(avg(spearman)::numeric, 3)                     as spearman,
    round(avg(hit_rate)::numeric, 3)                     as hit_rate,
    round(avg(mae)::numeric, 2)                          as mae,
    round(avg(coverage_80)::numeric, 3)                  as coverage_80,
    round(avg(interval_width)::numeric, 1)               as interval_width,
    max(model_version)                                   as model_version,
    max(run_at)                                          as run_at
from {{ source('ops', 'projection_backtest') }}
group by 1, 2, 3, 4, 5, 6
