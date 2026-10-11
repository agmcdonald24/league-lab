{{ config(indexes=[{'columns': ['gsis_id', 'season', 'week']}]) }}
-- As-of each played regular-season game: what was known about the player AFTER that game
-- (season-to-date, last-3 and last-5 windows for points, expected points and usage). The
-- feature-snapshot mart joins the latest row with week < target week, so a projection for
-- week N never sees week N or later (T-11: no peeking).
-- ---- IX-6, lf2.0: the study's candidates (var lf_candidate; unset: the SQL as before). P1: a marked game's per-game
-- values leave the window's average; P3: they are scaled to a full game (lf_scale); P2: the game is not in rf at all.
{%- set lf_cand = (var('lf_candidate', '') or '') | string | lower %}
{%- set lf_mode = lf_cand[:2] if lf_cand in ['p1a', 'p1b', 'p2a', 'p2b', 'p3a', 'p3b'] else '' %}
with rf as (
    select
        gsis_id, game_id, season, season_type, week, game_no, team, player_name, position,
        games_l3, games_l5,
        target_share_l3, target_share_l5, target_share_std, targets_l3,
        carry_share_l3, carry_share_l5, carry_share_std, carries_l3,
        air_yards_share_l3, snap_pct_l3, snap_pct_l5,
        points_per_game_l3, points_per_game_l5, points_per_game_std,
        first_read_share_l3, first_read_share_std, route_participation_l3
        {%- if lf_mode in ['p1', 'p3'] %}, lf_mark, lf_scale{% endif %}
    from {{ ref('mart_player_recent_form') }}
    where season_type = 'REG'
),

xp as (
    select gsis_id, game_id, points_expected
    from {{ ref('int_expected_points_week') }}
),

pg as (
    select gsis_id, game_id, attempts, targets, carries, points_current_scoring,
           -- stat-line components (projection v2 projects these, then prices them per league)
           receptions, receiving_yards, receiving_tds, rushing_yards, rushing_tds,
           passing_yards, passing_tds, passing_interceptions, fumbles_lost_total,
           red_zone_targets, red_zone_carries, offense_snap_pct
    from {{ ref('fct_player_game') }}
),

w as (
    select
        rf.*,
        pg.attempts, pg.targets, pg.carries, pg.points_current_scoring,
        xp.points_expected,
        count({{ lfv('xp.points_expected', lf_mode) }}) over (partition by rf.gsis_id, rf.season order by rf.week) as games_with_xp_std,
        avg({{ lfv('xp.points_expected', lf_mode) }})   over (partition by rf.gsis_id, rf.season order by rf.week) as xppg_std,
        avg({{ lfv('xp.points_expected', lf_mode) }})   over (partition by rf.gsis_id, rf.season order by rf.week rows between 2 preceding and current row) as xppg_l3,
        avg({{ lfv('xp.points_expected', lf_mode) }})   over (partition by rf.gsis_id, rf.season order by rf.week rows between 4 preceding and current row) as xppg_l5,
        avg({{ lfv('pg.attempts', lf_mode) }})          over (partition by rf.gsis_id, rf.season order by rf.week rows between 2 preceding and current row) as attempts_l3,
        avg({{ lfv('pg.attempts', lf_mode) }})          over (partition by rf.gsis_id, rf.season order by rf.week) as attempts_std,
        stddev_samp({{ lfv('pg.points_current_scoring', lf_mode) }}) over (partition by rf.gsis_id, rf.season order by rf.week) as points_sd_std,
        -- per-game component rates, season to date and last 3 (as-of: window ends at this game)
        {%- for c in component_stats() %}
        avg({{ lfv('pg.' ~ c, lf_mode) }}) over (partition by rf.gsis_id, rf.season order by rf.week) as {{ c }}_pg_std,
        avg({{ lfv('pg.' ~ c, lf_mode) }}) over (partition by rf.gsis_id, rf.season order by rf.week rows between 2 preceding and current row) as {{ c }}_pg_l3,
        {%- endfor %}
        avg({{ lfv('pg.offense_snap_pct', lf_mode) if lf_mode != 'p3' else 'case when rf.lf_mark then rf.lf_scale * pg.offense_snap_pct else pg.offense_snap_pct end' }}) over (partition by rf.gsis_id, rf.season order by rf.week) as snap_pct_std
    from rf
    left join xp using (gsis_id, game_id)
    left join pg using (gsis_id, game_id)
)

select
    gsis_id, game_id, season, week, game_no as games_to_date, team, player_name, position,
    points_current_scoring, points_expected,
    points_per_game_std as ppg_std, points_per_game_l3 as ppg_l3, points_per_game_l5 as ppg_l5, points_sd_std,
    games_with_xp_std, round(xppg_std::numeric, 3) as xppg_std, round(xppg_l3::numeric, 3) as xppg_l3, round(xppg_l5::numeric, 3) as xppg_l5,
    target_share_std, target_share_l3, target_share_l5, targets_l3,
    carry_share_std, carry_share_l3, carry_share_l5, carries_l3,
    air_yards_share_l3, snap_pct_l3, snap_pct_l5,
    first_read_share_std, first_read_share_l3, route_participation_l3,
    round(attempts_std::numeric, 2) as attempts_std, round(attempts_l3::numeric, 2) as attempts_l3,
    {%- for c in component_stats() %}
    round({{ c }}_pg_std::numeric, 3) as {{ c }}_pg_std, round({{ c }}_pg_l3::numeric, 3) as {{ c }}_pg_l3,
    {%- endfor %}
    round(snap_pct_std::numeric, 4) as snap_pct_std
from w
