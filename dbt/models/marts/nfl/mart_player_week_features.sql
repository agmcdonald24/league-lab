{{ config(indexes=[{'columns': ['season', 'week', 'position']}, {'columns': ['gsis_id', 'season', 'week'], 'unique': True}]) }}
-- Weekly feature snapshot (rankings input, T-11): one row per rostered QB/RB/WR/TE and regular-season
-- week in which his team plays, with everything a projection for that week may know:
--   * the player's season-to-date / last-3 / last-5 form after his latest game BEFORE the week
--   * his previous season (for week 1 and thin samples)
--   * the opponent's points allowed to his position, as of the games before the week, versus the
--     league average as of the same point
--   * the Vegas implied team total and home/away from the closing line
--   * the injury report status for that week
--   * (projection v3, plan D5) personnel: who starts at QB vs the QB his recent games were played with, and
--     whether his team's leading target / ball carrier is out this week (int_player_week_personnel; the
--     model reads the qb inputs at QB and the teammate inputs at RB / WR / TE)
-- and the outcome (`points_actual`, `played`) for the backtest. Nothing from the week itself or
-- later leaks into a feature. `f_*` columns are the finished, NULL-free inputs the projection uses;
-- the raw columns next to them show what was actually known.
with prev as (
    select s.gsis_id, s.season + 1 as season, s.games_played as prev_games, s.points_current_scoring_per_game as prev_ppg,
           e.expected_per_game as prev_xppg,
           -- previous-season component rates per game (projection v2 priors for week 1 and thin samples)
           {%- for c in component_stats() if c not in ('red_zone_targets', 'red_zone_carries') %}
           {%- set col = 'fumbles_lost' if c == 'fumbles_lost_total' else c %}
           case when s.games_played > 0 then round(s.{{ col }}::numeric / s.games_played, 3) end as prev_{{ c }}_pg,
           {%- endfor %}
           s.avg_offense_snap_pct as prev_snap_pct
    from {{ ref('mart_player_season') }} as s
    left join {{ ref('mart_player_expected_season') }} as e on e.gsis_id = s.gsis_id and e.season = s.season
    where s.season_type = 'REG'
),

-- position baseline from the previous season (as-of, no peeking): mean PPG of regulars
pos_prev as (
    select season + 1 as season, position,
           round(avg(points_current_scoring_per_game), 2) as pos_prev_ppg
    from {{ ref('mart_player_season') }}
    where season_type = 'REG' and games_played >= 8 and position in ('QB', 'RB', 'WR', 'TE')
    group by 1, 2
),

inj as (
    select season, week, gsis_id, report_status, practice_status
    from {{ ref('stg_nflverse__injuries') }}
),

outcome as (
    select gsis_id, season, week, points_current_scoring as points_actual, played, offense_snap_pct as snap_pct_actual,
           -- component outcomes: what projection v2 is trained on and scored against
           {%- for c in component_stats() %}
           {{ c }} as out_{{ c }}{{ "," if not loop.last }}
           {%- endfor %}
    from {{ ref('fct_player_game') }}
    where season_type = 'REG'
)

select
    u.gsis_id, u.season, u.week, u.game_id, u.team, u.opponent, u.position, u.player_name, u.roster_status, u.roster_week,
    u.is_home, u.spread_line, u.total_line, round(u.implied_team_total::numeric, 2) as implied_team_total,
    -- as-of form (raw)
    a.asof_week, coalesce(a.games_to_date, 0) as games_to_date,
    a.ppg_std, a.ppg_l3, a.ppg_l5, a.points_sd_std, a.xppg_std, a.xppg_l3, a.xppg_l5, a.games_with_xp_std,
    a.target_share_std, a.target_share_l3, a.carry_share_std, a.carry_share_l3, a.snap_pct_l3, a.air_yards_share_l3,
    a.first_read_share_std, a.first_read_share_l3, a.route_participation_l3, a.attempts_std, a.attempts_l3,
    -- as-of component rates per game (season to date, last 3) and snap share season to date
    a.snap_pct_std,
    {%- for c in component_stats() %}
    a.{{ c }}_pg_std, a.{{ c }}_pg_l3,
    {%- endfor %}
    -- previous season
    p.prev_games, p.prev_ppg, p.prev_xppg, pp.pos_prev_ppg, p.prev_snap_pct,
    {%- for c in component_stats() if c not in ('red_zone_targets', 'red_zone_carries') %}
    p.prev_{{ c }}_pg,
    {%- endfor %}
    -- opponent as of the week
    d.opp_allowed_std, d.opp_allowed_l4, d.opp_rank_std, d.opp_games, d.league_allowed_avg,
    -- injury report for the week
    i.report_status, i.practice_status,
    -- personnel (v3, plan D5; as of the week: games before it, week W's injury report, the projected starter)
    pn.pn_qb_changed, pn.pn_qb_games_together, pn.pn_qb_prev_ppg_diff, pn.pn_qb_is_rookie_or_backup, pn.pn_qb_starting,
    pn.pn_top_target_out, pn.pn_top_rusher_out, pn.pn_teammate_share_out, pn.pn_absence_beneficiary,
    pn.pn_asof_week,
    -- finished features (NULL-free): season form falls back to last season, then the position's regulars
    coalesce(a.xppg_l5, a.xppg_std, p.prev_xppg, a.ppg_std, p.prev_ppg, pp.pos_prev_ppg, 0)   as f_xppg_l5,
    coalesce(a.ppg_std, p.prev_ppg, pp.pos_prev_ppg, 0)                                        as f_ppg_std,
    coalesce(a.ppg_l3, a.ppg_std, p.prev_ppg, pp.pos_prev_ppg, 0)                              as f_ppg_l3,
    coalesce(p.prev_ppg, pp.pos_prev_ppg, 0)                                                   as f_ppg_prev,
    coalesce(d.opp_allowed_std - d.league_allowed_avg, 0)                                      as f_opp_allowed_diff,
    coalesce(u.implied_team_total, 22.0)                                                       as f_implied_total,
    u.is_home::int                                                                             as f_home,
    coalesce(a.target_share_l3 - a.target_share_std, 0)                                        as f_target_trend,
    coalesce(a.carry_share_l3 - a.carry_share_std, 0)                                          as f_carry_trend,
    coalesce(a.snap_pct_l3, 0)                                                                 as f_snap_l3,
    least(coalesce(a.games_to_date, 0), 6) / 6.0                                               as f_sample,   -- 0 at week 1 -> 1 after six games
    (a.games_to_date is null and p.prev_games is null)                                         as no_history,
    -- outcome
    o.points_actual, coalesce(o.played, false) as played, o.snap_pct_actual,
    {%- for c in component_stats() %}
    o.out_{{ c }}{{ "," if not loop.last }}
    {%- endfor %}
from {{ ref('int_player_week_universe') }} as u
left join {{ ref('int_player_week_asof_features') }} as a using (gsis_id, season, week)
left join prev as p on p.gsis_id = u.gsis_id and p.season = u.season
left join pos_prev as pp on pp.season = u.season and pp.position = u.position
left join {{ ref('int_opponent_week_asof') }} as d on d.defense = u.opponent and d.season = u.season and d.week = u.week and d.position = u.position
left join inj as i on i.season = u.season and i.week = u.week and i.gsis_id = u.gsis_id
left join {{ ref('int_player_week_personnel') }} as pn on pn.gsis_id = u.gsis_id and pn.season = u.season and pn.week = u.week
left join outcome as o on o.gsis_id = u.gsis_id and o.season = u.season and o.week = u.week
