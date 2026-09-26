{{ config(indexes=[{'columns': ['season', 'week', 'position']}, {'columns': ['gsis_id', 'season', 'week'], 'unique': True}]) }}
-- Weekly projection and rank per position, from the feature snapshot and the seed weights - the
-- same linear formula `league-lab fit-rankings` fitted, so the page can print every term:
--   proj = intercept + sum(weight * feature)
-- Contributions are grouped for reading: form (expected points and PPG terms), usage (trend and
-- snaps), matchup (opponent allowed vs league), vegas (implied team total), home. Naive baselines
-- ride along for the backtest. `is_rankable` excludes Out / Doubtful / IR; `no_history` marks
-- rows projected from position averages only.
with f as (
    select *,
           f_ppg_std * f_sample         as f_ppg_std_x_sample,
           f_ppg_prev * (1 - f_sample)  as f_ppg_prev_x_nosample
    from {{ ref('mart_player_week_features') }}
),

w as (
    select position, feature, weight from {{ ref('ranking_weights') }}
),

terms as (
    select
        f.gsis_id, f.season, f.week, w.feature, w.weight,
        case w.feature
            when 'intercept' then 1
            when 'f_xppg_l5' then f.f_xppg_l5
            when 'f_ppg_std' then f.f_ppg_std
            when 'f_ppg_l3' then f.f_ppg_l3
            when 'f_ppg_prev' then f.f_ppg_prev
            when 'f_ppg_std_x_sample' then f.f_ppg_std_x_sample
            when 'f_ppg_prev_x_nosample' then f.f_ppg_prev_x_nosample
            when 'f_opp_allowed_diff' then f.f_opp_allowed_diff
            when 'f_implied_total' then f.f_implied_total
            when 'f_home' then f.f_home
            when 'f_target_trend' then f.f_target_trend
            when 'f_carry_trend' then f.f_carry_trend
            when 'f_snap_l3' then f.f_snap_l3
        end as value
    from f
    join w on w.position = f.position
),

proj as (
    select
        gsis_id, season, week,
        round(sum(weight * value)::numeric, 2)                                                                     as proj_points,
        round(sum(weight * value) filter (where feature = 'intercept')::numeric, 2)                                as c_intercept,
        round(sum(weight * value) filter (where feature in ('f_xppg_l5', 'f_ppg_std', 'f_ppg_l3', 'f_ppg_prev',
                                                            'f_ppg_std_x_sample', 'f_ppg_prev_x_nosample'))::numeric, 2) as c_form,
        round(sum(weight * value) filter (where feature in ('f_target_trend', 'f_carry_trend', 'f_snap_l3'))::numeric, 2) as c_usage,
        round(sum(weight * value) filter (where feature = 'f_opp_allowed_diff')::numeric, 2)                       as c_matchup,
        round(sum(weight * value) filter (where feature = 'f_implied_total')::numeric, 2)                          as c_vegas,
        round(sum(weight * value) filter (where feature = 'f_home')::numeric, 2)                                   as c_home
    from terms
    group by 1, 2, 3
),

ranked as (
    select
        f.gsis_id, f.season, f.week, f.game_id, f.team, f.opponent, f.position, f.player_name,
        f.is_home, f.implied_team_total, f.spread_line, f.total_line,
        f.games_to_date, f.asof_week, f.report_status, f.practice_status, f.roster_status, f.no_history,
        f.report_status is distinct from 'Out' and f.report_status is distinct from 'Doubtful'
            and f.roster_status <> 'RES'                                                        as is_rankable,
        p.proj_points, p.c_intercept, p.c_form, p.c_usage, p.c_matchup, p.c_vegas, p.c_home,
        -- inputs shown next to the projection
        f.xppg_l5, f.ppg_std, f.ppg_l3, f.prev_ppg, f.opp_allowed_std, f.league_allowed_avg, f.opp_rank_std,
        f.target_share_l3, f.target_share_std, f.carry_share_l3, f.carry_share_std, f.snap_pct_l3,
        f.first_read_share_l3, f.points_sd_std,
        -- naive baselines (same as-of inputs, no formula)
        f.f_ppg_std as naive_ppg_std, f.f_ppg_l3 as naive_ppg_l3, f.f_xppg_l5 as naive_xppg_l5,
        f.points_actual, f.played
    from f
    join proj as p using (gsis_id, season, week)
)

select
    r.*,
    rank() over (partition by season, week, position order by case when is_rankable then proj_points end desc nulls last, gsis_id) as rank_pos,
    rank() over (partition by season, week order by case when is_rankable then proj_points end desc nulls last, gsis_id)           as rank_overall,
    case when played then rank() over (partition by season, week, position order by case when played then points_actual end desc nulls last, gsis_id) end as actual_rank_pos
from ranked as r
