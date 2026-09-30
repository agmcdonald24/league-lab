{{ config(
    materialized='view',
    pre_hook="create table if not exists ops.projection_importance (model_version text, run_at timestamptz, league_id text, position text, feature text, importance double precision); alter table ops.projection_importance add column if not exists model text; alter table ops.projection_importance add column if not exists component text; alter table ops.projection_importance add column if not exists feature_label text; alter table ops.projection_importance add column if not exists unit text; alter table ops.projection_importance add column if not exists importance_sd double precision; alter table ops.projection_importance add column if not exists importance_points double precision; alter table ops.projection_importance add column if not exists baseline_mae double precision; alter table ops.projection_importance add column if not exists n_rows integer; alter table ops.projection_importance add column if not exists train_seasons text; alter table ops.projection_importance add column if not exists eval_season integer; alter table ops.projection_importance add column if not exists fit_seasons text"
) }}
-- What drives projection v2 (plan U-15), for the Rankings page's "The model" expander.
-- model = 'component': the component models (targets, catches, yards, TDs ... per position), written by
--   `league-lab project` once per model version x training window: for each input, how much the error grows
--   when that input is scrambled, on the newest training season (eval_season) with a twin of the models
--   fitted without it (fit_seasons; train_seasons is the production window the rows describe).
--   component = 'total' is the headline, in points of the reference league's scoring (unit 'points');
--   the other rows break it down per stat, in that stat's unit, with importance_points = rise x points per unit.
-- model = 'quantile_p50': the interval (floor / ceiling) model's median, written by `backtest-v2`
--   (every row written before U-15 is this model); its main input is the projection itself.
-- importance_rank: 1 = the input that adds the most error, per model version, model, position and component.
select
    model_version,
    coalesce(model, 'quantile_p50')                              as model,
    league_id,
    position,
    coalesce(component, 'p50_residual')                          as component,
    feature,
    coalesce(feature_label, feature)                             as feature_label,
    coalesce(unit, 'points')                                     as unit,
    importance,
    importance_sd,
    importance_points,
    baseline_mae,
    n_rows,
    train_seasons,
    fit_seasons,
    eval_season,
    run_at,
    rank() over (partition by model_version, coalesce(model, 'quantile_p50'), position, coalesce(component, 'p50_residual')
                 order by importance desc, feature)              as importance_rank
from {{ source('ops', 'projection_importance') }}
