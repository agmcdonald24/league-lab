{{ config(
    materialized='view',
    pre_hook=[
        "create table if not exists ops.player_scenarios ( run_at timestamptz, model_version text, signals_version text, league_id text, season integer, week integer, gsis_id text, position text, alert_week integer, since_week integer, games_held integer, confidence text, kind text, trigger_kind text, trigger_gsis_id text, trigger_name text, cause_text text, change_text text, base_points double precision, larger_points double precision, points_gain double precision, with_alert_points double precision, hold_rate double precision, backtest_n integer, backtest_hit_rate double precision, presentation text, presentation_note text, base_targets double precision, larger_targets double precision, base_receptions double precision, larger_receptions double precision, base_receiving_yards double precision, larger_receiving_yards double precision, base_carries double precision, larger_carries double precision, base_rushing_yards double precision, larger_rushing_yards double precision, base_attempts double precision, larger_attempts double precision, base_passing_yards double precision, larger_passing_yards double precision, base_tds double precision, larger_tds double precision, base_line jsonb, larger_line jsonb, features_set jsonb, expires_after_week integer, expiry_rule text)"
    ]
) }}
-- Scenario upside (plan R-12): per league x season x week x QB / RB / WR / TE with a live bigger-role alert,
-- the projection as it is (base_points = the stored projection) and the larger-role scenario (larger_points:
-- the same component models re-predicting his stat line with his last-3-games inputs at the level of the
-- games since the change, each capped at the position's 90th percentile, priced in the league's scoring),
-- the probability-weighted line (with_alert_points = base + the historical hold rate x the gap), the
-- calibration the page shows instead of a bare probability (backtest_n, backtest_hit_rate, presentation =
-- 'with the alert' when that line beat the projection on the 2023-2025 backtest, else 'what if'), the inputs
-- set (features_set: {input: [base, scenario]}), both stat lines, and when it lapses (expires_after_week,
-- expiry_rule). Written by `league-lab project` / `league-lab signals`; `proj_points` is joined from the
-- published projection so the dbt test can hold base_points to it.
with s as (
    select * from {{ source('ops', 'player_scenarios') }}
)

select
    s.league_id, s.season, s.week, s.gsis_id, coalesce(p.player_name, dp.player_name) as player_name, s.position,
    p.team, p.opponent, s.alert_week, s.since_week, s.games_held, s.confidence, s.kind, s.trigger_kind, s.trigger_gsis_id,
    s.trigger_name, s.cause_text, s.change_text, s.base_points, s.larger_points, s.points_gain, s.with_alert_points,
    s.hold_rate, s.backtest_n, s.backtest_hit_rate, s.presentation, s.presentation_note,
    s.base_targets, s.larger_targets, s.base_receptions, s.larger_receptions, s.base_receiving_yards, s.larger_receiving_yards,
    s.base_carries, s.larger_carries, s.base_rushing_yards, s.larger_rushing_yards, s.base_attempts, s.larger_attempts,
    s.base_passing_yards, s.larger_passing_yards, s.base_tds, s.larger_tds,
    s.base_line, s.larger_line, s.features_set, s.expires_after_week, s.expiry_rule,
    p.proj_points, s.model_version, s.signals_version, s.run_at
from s
left join {{ ref('mart_player_week_projections') }} as p
       on p.league_id = s.league_id and p.season = s.season and p.week = s.week and p.gsis_id = s.gsis_id
left join {{ ref('dim_player') }} as dp on dp.gsis_id = s.gsis_id
