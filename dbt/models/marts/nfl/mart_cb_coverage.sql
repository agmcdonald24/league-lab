{{ config(indexes=[{'columns': ['gsis_id', 'season', 'window_label'], 'unique': True}], post_hook="analyze {{ this }}") }}
-- Cornerback quality (plan R-14, metric cb_coverage v1.0), one row per defender x season x window:
--   window 'season'      = that regular season to date
--   window 'two_seasons' = the season before + that season (what Matchups ranks on: two games of a new
--                          season are a handful of targets per corner)
-- Numerators are PFR's advanced defense (targets, completions, yards, TDs, INTs where he was the primary
-- defender); the denominator is coverage snaps (int_defender_game_coverage_snaps: participation, else the
-- snap-share estimate), over the same games. Passer rating allowed is the NFL formula on the summed
-- components (targets as attempts), not an average of per-game ratings.
-- Cornerbacks = played CB in at least half his games (PFR snap counts), or listed as CB (nflverse players),
-- or listed at LCB / RCB / NB on a depth chart that season. Ranked among cornerbacks with >= 20 coverage snaps per team game in the window (1 = hardest to throw on).
-- Shadow evidence: across his games, how many more targets he drew per target the opposing WR1 got,
-- against per target everyone else got (two-regressor least squares; a shadow corner follows the WR1).
with g as (
    select * from {{ ref('int_defender_game_coverage_snaps') }}
    where season_type = 'REG'
),

seasons as (select distinct season from g),

windows as (
    select season, 'season' as window_label, season as first_season from seasons
    union all
    select season, 'two_seasons', season - 1 from seasons where season - 1 >= (select min(season) from seasons)
),

-- the opposing offense's WR1 = its WR with the most targets that season (regular season)
wr_targets as (
    select season, team, gsis_id, sum(targets) as targets
    from {{ ref('fct_player_game') }}
    where season_type = 'REG' and position = 'WR' and targets is not null
    group by 1, 2, 3
),

wr1 as (
    select distinct on (season, team) season, team, gsis_id as wr1_gsis_id
    from wr_targets
    order by season, team, targets desc, gsis_id
),

opp_game as (
    select t.game_id, t.team as offense, t.targets as team_targets, w.wr1_gsis_id, coalesce(pg.targets, 0) as wr1_targets
    from {{ ref('fct_team_game') }} as t
    join wr1 as w on w.season = t.season and w.team = t.team
    left join {{ ref('fct_player_game') }} as pg on pg.gsis_id = w.wr1_gsis_id and pg.game_id = t.game_id
    where t.season_type = 'REG'
),

depth_cb as (   -- listed at a cornerback slot on any depth chart of that season
    select distinct season, gsis_id
    from {{ ref('stg_nflverse__depth_charts') }}
    where pos_abb in ('LCB', 'RCB', 'NB', 'CB', 'SCB')
),

gw as (
    select w.season, w.window_label, w.first_season,
           g.gsis_id, g.game_id, g.season as game_season, g.week, g.team, g.opponent, g.defender_name, g.position, g.snap_position,
           g.coverage_snaps, g.coverage_snaps_source, g.def_targets, g.def_completions_allowed, g.def_yards_allowed,
           g.def_receiving_td_allowed, g.def_ints, g.def_adot,
           og.wr1_targets, og.team_targets - og.wr1_targets as other_targets
    from windows as w
    join g on g.season between w.first_season and w.season
    left join opp_game as og on og.game_id = g.game_id and og.offense = g.opponent
),

team_games as (   -- the most games any team has in the window: the minimum-snaps yardstick
    select season, window_label, max(n) as team_games
    from (select season, window_label, team, count(distinct game_id) as n from gw group by 1, 2, 3) as x
    group by 1, 2
),

agg as (
    select
        gw.season, gw.window_label, gw.first_season, gw.gsis_id,
        (array_agg(gw.team order by gw.game_season desc, gw.week desc))[1]           as latest_team,
        string_agg(distinct gw.team, ',' order by gw.team)                            as teams,
        max(gw.defender_name)                                                         as pfr_name,
        max(gw.position)                                                              as player_position,
        count(*)                                                                      as games,
        count(*) filter (where gw.snap_position = 'CB')                               as games_at_cb,
        sum(gw.coverage_snaps)                                                        as coverage_snaps,
        sum(gw.coverage_snaps) filter (where gw.coverage_snaps_source = 'snap_share') as coverage_snaps_estimated,
        sum(gw.def_targets)                                                           as targets,
        sum(gw.def_completions_allowed)                                               as completions_allowed,
        sum(gw.def_yards_allowed)                                                     as yards_allowed,
        sum(gw.def_receiving_td_allowed)                                              as tds_allowed,
        sum(gw.def_ints)                                                              as interceptions,
        sum(gw.def_adot * gw.def_targets) filter (where gw.def_adot is not null)      as adot_weighted,
        sum(gw.def_targets) filter (where gw.def_adot is not null)                    as adot_targets,
        -- shadow evidence over games with a known opposing WR1
        count(*) filter (where gw.wr1_targets is not null and gw.def_targets is not null) as wr1_games,
        covar_pop(gw.def_targets, gw.wr1_targets)                                     as c_y1,
        covar_pop(gw.def_targets, gw.other_targets)                                   as c_y2,
        var_pop(gw.wr1_targets)                                                       as v_1,
        var_pop(gw.other_targets)                                                     as v_2,
        covar_pop(gw.wr1_targets, gw.other_targets)                                   as c_12
    from gw
    group by 1, 2, 3, 4
),

rates as (
    select
        a.*,
        tg.team_games,
        20 * tg.team_games                                                            as min_coverage_snaps,
        (a.games_at_cb * 2 >= a.games or a.player_position = 'CB' or d.gsis_id is not null) as is_cb,
        case when a.coverage_snaps > 0 then (a.targets / a.coverage_snaps)::numeric end as targets_per_coverage_snap,
        case when a.targets > 0 then (a.yards_allowed / a.targets)::numeric end                   as yards_per_target_allowed,
        case when a.targets > 0 then round((a.completions_allowed / a.targets)::numeric, 3) end   as completion_pct_allowed,
        case when a.coverage_snaps > 0 then round((a.yards_allowed / a.coverage_snaps)::numeric, 3) end as yards_per_coverage_snap,
        case when a.adot_targets > 0 then round((a.adot_weighted / a.adot_targets)::numeric, 1) end as adot_allowed,
        -- NFL passer rating on the summed components, targets as attempts; each part clamped to [0, 2.375]
        case when a.targets > 0 then ((100.0 / 6 * (
              least(greatest((a.completions_allowed / a.targets - 0.3) * 5, 0), 2.375)
            + least(greatest((a.yards_allowed / a.targets - 3) * 0.25, 0), 2.375)
            + least(greatest(a.tds_allowed / a.targets * 20, 0), 2.375)
            + least(greatest(2.375 - a.interceptions / a.targets * 25, 0), 2.375)))::numeric) end as passer_rating_allowed,
        case when (a.v_1 * a.v_2 - a.c_12 * a.c_12) > 0
             then round(((a.c_y1 * a.v_2 - a.c_y2 * a.c_12) / (a.v_1 * a.v_2 - a.c_12 * a.c_12))::numeric, 3) end as wr1_follow_slope,
        case when (a.v_1 * a.v_2 - a.c_12 * a.c_12) > 0
             then round(((a.c_y2 * a.v_1 - a.c_y1 * a.c_12) / (a.v_1 * a.v_2 - a.c_12 * a.c_12))::numeric, 3) end as other_follow_slope
    from agg as a
    join team_games as tg using (season, window_label)
    left join depth_cb as d on d.gsis_id = a.gsis_id and d.season = a.season
),

ranked as (
    select
        r.*,
        r.is_cb and r.coverage_snaps >= r.min_coverage_snaps and r.targets > 0     as is_ranked
    from rates as r
)

select
    r.season, r.window_label, r.first_season, r.gsis_id,
    coalesce(p.player_name, r.pfr_name)                                            as defender_name,
    coalesce(p.position, r.player_position)                                        as player_position,
    r.latest_team, r.teams, r.is_cb, r.games, r.games_at_cb,
    round(r.coverage_snaps::numeric, 1)                                            as coverage_snaps,
    round(coalesce(r.coverage_snaps_estimated, 0)::numeric, 1)                     as coverage_snaps_estimated,
    r.targets::int                                                                 as targets,
    r.completions_allowed::int                                                     as completions_allowed,
    r.yards_allowed::int                                                           as yards_allowed,
    r.tds_allowed::int                                                             as tds_allowed,
    r.interceptions::int                                                           as interceptions,
    round(r.targets_per_coverage_snap, 4) as targets_per_coverage_snap, round(r.yards_per_target_allowed, 2) as yards_per_target_allowed,
    r.completion_pct_allowed, r.yards_per_coverage_snap, r.adot_allowed, round(r.passer_rating_allowed, 1) as passer_rating_allowed,
    r.team_games, r.min_coverage_snaps, r.is_ranked,
    count(*) filter (where r.is_ranked) over (partition by r.season, r.window_label)  as n_ranked,
    case when r.is_ranked then rank() over (partition by r.season, r.window_label, r.is_ranked order by r.yards_per_target_allowed) end as rank_yards_per_target,
    case when r.is_ranked then rank() over (partition by r.season, r.window_label, r.is_ranked order by r.targets_per_coverage_snap) end as rank_targets_per_snap,
    case when r.is_ranked then rank() over (partition by r.season, r.window_label, r.is_ranked order by r.passer_rating_allowed) end as rank_passer_rating,
    r.wr1_games, r.wr1_follow_slope, r.other_follow_slope,
    coalesce(r.is_cb and r.wr1_games >= 10 and r.targets >= 40
             and r.wr1_follow_slope >= 0.30 and r.wr1_follow_slope - r.other_follow_slope >= 0.25, false) as shadow_flag
from ranked as r
left join {{ ref('dim_player') }} as p on p.gsis_id = r.gsis_id
where r.is_cb   -- cornerbacks only (a safety or linebacker in coverage is not in this pool)
