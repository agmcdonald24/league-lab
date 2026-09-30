{{ config(indexes=[{'columns': ['gsis_id', 'season', 'window_label'], 'unique': True}, {'columns': ['season', 'window_label', 'quality_rank']}], post_hook="analyze {{ this }}") }}
-- Cornerback rankings (plan R-14, metric cb_rankings v1.0), one row per cornerback x season x window:
--   window 'season'      = that regular season to date
--   window 'last_4'      = his last 4 regular-season games (that season and the one before)
--   window 'two_seasons' = the season before + that season (what the Matchups card ranks on: three games of
--                          a new season are a dozen targets per corner)
-- Numerators are PFR's advanced defense (targets, completions, yards, TDs, INTs where he was the primary
-- defender); the denominator is coverage snaps (int_defender_game_coverage_snaps: participation, else the
-- snap-share estimate), over the same games. Passer rating allowed is the NFL formula on the summed
-- components (targets as attempts), not an average of per-game ratings.
-- Opponent quality: each game's expected yards per target = the opposing offense's WR + TE yards per target
-- over that game's season and the one before, leaving the game out; weighted by his targets in the game.
-- Adjusted yards per target = his yards per target - that expectation + the pool's expectation, shrunk
-- toward the pool's yards per target with the weight of 30 targets. It adjusts for the offenses he faced, not
-- the receivers he covered (public data does not say which receiver a corner's targets went to).
-- Cornerbacks = played CB (or a nickel DB listed CB by PFR) in at least half his games in the window (PFR snap
-- counts; PFR's position when the snap row is missing). Ranked pool = cornerbacks with >= 20 coverage snaps
-- per team game in the window (a starter's share; 80 for the last 4 games) and a target.
-- Quality score = minus the average of three z-scores inside the ranked pool: targets per coverage snap,
-- adjusted yards per target, passer rating allowed (higher = harder to throw on); rank 1 = best. Label: the top
-- quarter 'shutdown', the bottom quarter 'target', the rest 'solid'.
-- Shadow evidence (kept for the record, NOT shown: it caught 2 of 6 commonly reported shadow corners in 2025,
-- docs/METRICS.md): across his games, the targets he drew per target the opposing WR1 got vs per target
-- everyone else got (two-regressor least squares).
with g as (
    select c.*,
           (c.snap_position = 'CB' or (c.snap_position = 'DB' and c.position in ('CB', 'DB'))
            or (c.snap_position is null and c.position = 'CB'))                        as is_cb_game
    from {{ ref('int_defender_game_coverage_snaps') }} as c
    where c.season_type = 'REG'
),

seasons as (select distinct season from g),

windows as (
    select season, 'season' as window_label, season as first_season from seasons
    union all
    select season, 'last_4', season - 1 from seasons
    union all
    select season, 'two_seasons', season - 1 from seasons where season - 1 >= (select min(season) from seasons)
),

-- opponent quality: the offense's WR + TE yards per target
off_game as (
    select game_id, season, team as offense,
           sum(coalesce(targets, 0)) as targets, sum(coalesce(receiving_yards, 0)) as yards
    from {{ ref('fct_player_game') }}
    where season_type = 'REG' and position in ('WR', 'TE')
    group by 1, 2, 3
),

off_season as (
    select season, offense, sum(targets) as targets, sum(yards) as yards from off_game group by 1, 2
),

off_exp as (   -- per game: that offense over the game's season and the one before, the game left out
    select og.game_id, og.offense,
           ((sum(os.yards) - og.yards)::numeric / nullif(sum(os.targets) - og.targets, 0)) as exp_ypt
    from off_game as og
    join off_season as os on os.offense = og.offense and os.season between og.season - 1 and og.season
    group by og.game_id, og.offense, og.yards, og.targets
),

-- the opposing offense's WR1 = its WR with the most targets that season (regular season): shadow evidence
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

gw_all as (
    select w.season, w.window_label, w.first_season,
           g.gsis_id, g.game_id, g.season as game_season, g.week, g.team, g.opponent, g.defender_name, g.position,
           g.is_cb_game, g.coverage_snaps, g.coverage_snaps_source, g.def_targets, g.def_completions_allowed,
           g.def_yards_allowed, g.def_receiving_td_allowed, g.def_ints, g.def_adot,
           x.exp_ypt,
           og.wr1_targets, og.team_targets - og.wr1_targets                              as other_targets,
           row_number() over (partition by w.season, w.window_label, g.gsis_id
                              order by g.season desc, g.week desc)                      as game_back
    from windows as w
    join g on g.season between w.first_season and w.season
    left join off_exp as x on x.game_id = g.game_id and x.offense = g.opponent
    left join opp_game as og on og.game_id = g.game_id and og.offense = g.opponent
),

gw as (
    select * from gw_all where window_label <> 'last_4' or game_back <= 4
),

team_games as (   -- the most games any team has in the window: the minimum-snaps yardstick
    select season, window_label,
           case when window_label = 'last_4' then 4 else max(n) end as team_games
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
        count(*) filter (where gw.is_cb_game)                                         as games_at_cb,
        min(gw.game_season * 100 + gw.week)                                           as first_game_key,
        max(gw.game_season * 100 + gw.week)                                           as last_game_key,
        sum(gw.coverage_snaps)                                                        as coverage_snaps,
        sum(gw.coverage_snaps) filter (where gw.coverage_snaps_source = 'snap_share') as coverage_snaps_estimated,
        sum(gw.def_targets)                                                           as targets,
        sum(gw.def_completions_allowed)                                               as completions_allowed,
        sum(gw.def_yards_allowed)                                                     as yards_allowed,
        sum(gw.def_receiving_td_allowed)                                              as tds_allowed,
        sum(gw.def_ints)                                                              as interceptions,
        sum(gw.def_adot * gw.def_targets) filter (where gw.def_adot is not null)      as adot_weighted,
        sum(gw.def_targets) filter (where gw.def_adot is not null)                    as adot_targets,
        sum(gw.exp_ypt * gw.def_targets) filter (where gw.exp_ypt is not null)        as exp_weighted,
        sum(gw.def_targets) filter (where gw.exp_ypt is not null)                     as exp_targets,
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
        (a.games_at_cb * 2 >= a.games)                                                as is_cb,
        case when a.coverage_snaps > 0 then (a.targets / a.coverage_snaps)::numeric end as targets_per_coverage_snap,
        case when a.targets > 0 then (a.yards_allowed / a.targets)::numeric end       as yards_per_target_allowed,
        case when a.exp_targets > 0 then (a.exp_weighted / a.exp_targets)::numeric end as exp_ypt_faced,
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
),

pooled as (
    select r.*,
           r.is_cb and r.coverage_snaps >= r.min_coverage_snaps and r.targets > 0 and r.exp_ypt_faced is not null as is_ranked
    from rates as r
),

pool as (   -- the ranked pool's yardsticks per season x window
    select season, window_label,
           sum(yards_allowed)::numeric / nullif(sum(targets), 0)                         as pool_ypt,
           sum(exp_ypt_faced * targets)::numeric / nullif(sum(targets), 0)               as pool_exp_ypt
    from pooled
    where is_ranked
    group by 1, 2
),

adjusted as (
    select p.*, pl.pool_ypt, pl.pool_exp_ypt,
           case when p.targets > 0 and p.exp_ypt_faced is not null then
               ((p.yards_per_target_allowed - p.exp_ypt_faced + pl.pool_exp_ypt) * p.targets + pl.pool_ypt * 30)
               / (p.targets + 30) end                                                      as adj_yards_per_target
    from pooled as p
    left join pool as pl using (season, window_label)
),

z as (
    select a.*,
           case when a.is_ranked then
               (a.targets_per_coverage_snap - avg(a.targets_per_coverage_snap) over w)
               / nullif(stddev_samp(a.targets_per_coverage_snap) over w, 0) end             as z_targets,
           case when a.is_ranked then
               (a.adj_yards_per_target - avg(a.adj_yards_per_target) over w)
               / nullif(stddev_samp(a.adj_yards_per_target) over w, 0) end                  as z_yards,
           case when a.is_ranked then
               (a.passer_rating_allowed - avg(a.passer_rating_allowed) over w)
               / nullif(stddev_samp(a.passer_rating_allowed) over w, 0) end                 as z_rating
    from adjusted as a
    window w as (partition by a.season, a.window_label, a.is_ranked)
),

scored as (
    select z.*,
           case when z.is_ranked then -(z.z_targets + z.z_yards + z.z_rating) / 3 end   as quality_score,
           count(*) filter (where z.is_ranked) over (partition by z.season, z.window_label) as n_ranked
    from z
),

ranked as (
    select s.*,
           case when s.is_ranked then rank() over (partition by s.season, s.window_label, s.is_ranked order by s.quality_score desc) end              as quality_rank,
           case when s.is_ranked then rank() over (partition by s.season, s.window_label, s.is_ranked order by s.targets_per_coverage_snap) end       as rank_targets_per_snap,
           case when s.is_ranked then rank() over (partition by s.season, s.window_label, s.is_ranked order by s.adj_yards_per_target) end            as rank_adj_yards_per_target,
           case when s.is_ranked then rank() over (partition by s.season, s.window_label, s.is_ranked order by s.passer_rating_allowed) end           as rank_passer_rating
    from scored as s
)

select
    r.season, r.window_label, r.first_season, r.gsis_id,
    coalesce(p.player_name, r.pfr_name)                                            as defender_name,
    coalesce(p.position, r.player_position)                                        as player_position,
    r.latest_team, r.teams, r.is_cb, r.games, r.games_at_cb,
    r.first_game_key / 100 as first_game_season, r.first_game_key % 100 as first_game_week,
    r.last_game_key / 100 as last_game_season, r.last_game_key % 100 as last_game_week,
    round(r.coverage_snaps::numeric, 1)                                            as coverage_snaps,
    round(coalesce(r.coverage_snaps_estimated, 0)::numeric, 1)                     as coverage_snaps_estimated,
    r.targets::int                                                                 as targets,
    r.completions_allowed::int                                                     as completions_allowed,
    r.yards_allowed::int                                                           as yards_allowed,
    r.tds_allowed::int                                                             as tds_allowed,
    r.interceptions::int                                                           as interceptions,
    round(r.targets_per_coverage_snap::numeric, 4)                                          as targets_per_coverage_snap,
    round(r.yards_per_target_allowed::numeric, 2)                                           as yards_per_target_allowed,
    round(r.exp_ypt_faced::numeric, 2)                                                      as exp_ypt_faced,
    round(r.adj_yards_per_target::numeric, 2)                                               as adj_yards_per_target,
    r.completion_pct_allowed, r.yards_per_coverage_snap, r.adot_allowed,
    round(r.passer_rating_allowed::numeric, 1)                                              as passer_rating_allowed,
    round(r.pool_ypt::numeric, 2) as pool_ypt, round(r.pool_exp_ypt::numeric, 2) as pool_exp_ypt,
    round(r.z_targets::numeric, 3) as z_targets, round(r.z_yards::numeric, 3) as z_yards, round(r.z_rating::numeric, 3) as z_rating,
    round(r.quality_score::numeric, 3)                                                      as quality_score,
    r.team_games, r.min_coverage_snaps, r.is_ranked, r.n_ranked,
    r.quality_rank, r.rank_targets_per_snap, r.rank_adj_yards_per_target, r.rank_passer_rating,
    case when not r.is_ranked then null
         when r.quality_rank <= ceil(r.n_ranked / 4.0) then 'shutdown'
         when r.quality_rank > r.n_ranked - ceil(r.n_ranked / 4.0) then 'target'
         else 'solid' end                                                          as quality_label,
    r.wr1_games, r.wr1_follow_slope, r.other_follow_slope,
    coalesce(r.is_cb and r.wr1_games >= 10 and r.targets >= 40
             and r.wr1_follow_slope >= 0.30 and r.wr1_follow_slope - r.other_follow_slope >= 0.25, false) as shadow_flag
from ranked as r
left join {{ ref('dim_player') }} as p on p.gsis_id = r.gsis_id
where r.is_cb   -- cornerbacks only (a safety or linebacker in coverage is not in this pool)
