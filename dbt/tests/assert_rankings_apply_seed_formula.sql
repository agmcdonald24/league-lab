-- The projection must equal intercept + sum(weight * feature) from the seed, so the page's
-- printed formula and the mart never drift (recomputed here for WR from the raw features).
with w as (select feature, weight from {{ ref('ranking_weights') }} where position = 'WR'),
f as (
    select gsis_id, season, week, proj_points,
           (select weight from w where feature = 'intercept')
         + (select weight from w where feature = 'f_xppg_l5') * f_xppg_l5
         + (select weight from w where feature = 'f_ppg_std') * f_ppg_std
         + (select weight from w where feature = 'f_ppg_l3') * f_ppg_l3
         + (select weight from w where feature = 'f_ppg_prev') * f_ppg_prev
         + (select weight from w where feature = 'f_ppg_std_x_sample') * f_ppg_std * f_sample
         + (select weight from w where feature = 'f_ppg_prev_x_nosample') * f_ppg_prev * (1 - f_sample)
         + (select weight from w where feature = 'f_opp_allowed_diff') * f_opp_allowed_diff
         + (select weight from w where feature = 'f_implied_total') * f_implied_total
         + (select weight from w where feature = 'f_home') * f_home
         + (select weight from w where feature = 'f_target_trend') * f_target_trend
         + (select weight from w where feature = 'f_snap_l3') * f_snap_l3 as recomputed
    from {{ ref('mart_player_week_features') }} as x
    join {{ ref('mart_player_week_rankings') }} as r using (gsis_id, season, week)
    where x.position = 'WR'
)
select * from f where abs(proj_points - recomputed) > 0.02
