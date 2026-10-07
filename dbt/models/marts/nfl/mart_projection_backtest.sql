{{ config(
    materialized='view',
    pre_hook="create table if not exists ops.projection_backtest (run_id text, run_at timestamptz, model_version text, train_seasons text, league_id text, season integer, week integer, position text, scorer text, n_players integer, spearman double precision, top_n integer, hit_rate double precision, mae double precision, coverage_80 double precision, pinball_10 double precision, pinball_50 double precision, pinball_90 double precision, interval_width double precision); alter table ops.projection_backtest add column if not exists coverage_50 double precision; alter table ops.projection_backtest add column if not exists interval_width_50 double precision; alter table ops.projection_backtest add column if not exists pinball_25 double precision; alter table ops.projection_backtest add column if not exists pinball_75 double precision"
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
        when 'v2_points' then 'The projection (' || model_version || ') · its line, priced'
        when 'v2_p50' then 'The projection (' || model_version || ') · middle outcome'
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
    round(avg(coverage_50)::numeric, 3)                  as coverage_50,         -- v3.0 on (NULL for v2.0)
    round(avg(interval_width_50)::numeric, 1)            as interval_width_50,
    round(avg((pinball_10 + pinball_90) / 2)::numeric, 3) as interval_score,     -- the harness's: lower = sharper at the same honesty
    model_version,
    -- v3: every model version keeps its rows (v2.0's are its record); the pages and the drift strip read the
    -- current one: the newest QB-TE version, and kd1.0 for K / DEF
    -- ---- IP-1 fix round 2: the newest version by its numbers ('v3.10' after 'v3.9'), not as text
    model_version = (select model_version from {{ source('ops', 'projection_backtest') }} where model_version like 'v%'
                     order by {{ version_key('model_version') }} desc nulls last limit 1)
      or model_version not like 'v%'                     as is_current,
    max(run_at)                                          as run_at
from {{ source('ops', 'projection_backtest') }}
group by 1, 2, 3, 4, 5, 6, model_version
