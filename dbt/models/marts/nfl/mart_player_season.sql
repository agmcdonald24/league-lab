{{ config(indexes=[{'columns': ['season', 'season_type', 'position']}, {'columns': ['player_name']}]) }}
-- Player x season x season_type aggregates. Numerators and denominators are summed over the
-- player's own appearance games first, then rates are computed (plan §5/§6). Team denominators
-- are therefore "team totals in the games this player appeared in", which is the correct
-- shared window for share metrics. Players who changed teams get `team_count > 1` and a
-- comma-separated `teams` list; per-team splits are a separate view (mart_player_season_team).
with pg as (
    select * from {{ ref('fct_player_game') }}
),

agg as (
    select
        gsis_id,
        season,
        season_type,
        mode() within group (order by position)                 as position,
        max(player_name)                                        as player_name,
        string_agg(distinct team, ',' order by team)            as teams,
        count(distinct team)                                    as team_count,
        count(*)                                                as games_with_stats,
        count(*) filter (where played)                          as games_played,
        count(*) filter (where snaps_known)                     as games_with_snaps,
        min(week) as first_week, max(week) as last_week,
        -- passing
        sum(completions) as completions, sum(attempts) as attempts, sum(passing_yards) as passing_yards,
        sum(passing_tds) as passing_tds, sum(passing_interceptions) as passing_interceptions,
        sum(sacks_suffered) as sacks_suffered, sum(passing_air_yards) as passing_air_yards,
        sum(passing_epa) as passing_epa, sum(dropbacks_excl_scrambles) as dropbacks_excl_scrambles,
        -- rushing
        sum(carries) as carries, sum(rushing_yards) as rushing_yards, sum(rushing_tds) as rushing_tds,
        sum(rushing_first_downs) as rushing_first_downs, sum(rushing_epa) as rushing_epa,
        -- receiving
        sum(targets) as targets, sum(receptions) as receptions, sum(receiving_yards) as receiving_yards,
        sum(receiving_tds) as receiving_tds, sum(receiving_air_yards) as receiving_air_yards,
        sum(receiving_yards_after_catch) as receiving_yards_after_catch,
        sum(receiving_first_downs) as receiving_first_downs, sum(receiving_epa) as receiving_epa,
        -- misc / fumbles
        sum(fumbles_lost_total) as fumbles_lost, sum(special_teams_tds + fumble_recovery_tds) as return_and_recovery_tds,
        -- kicking
        sum(fg_made) as fg_made, sum(fg_att) as fg_att, sum(fg_missed) as fg_missed, sum(fg_blocked) as fg_blocked,
        max(fg_long) as fg_long, sum(fg_made_0_19 + fg_made_20_29 + fg_made_30_39) as fg_made_under_40,
        sum(fg_made_40_49) as fg_made_40_49, sum(fg_made_50p) as fg_made_50p,
        sum(pat_made) as pat_made, sum(pat_att) as pat_att,
        -- snaps (only over games where known)
        sum(offense_snaps) as offense_snaps,
        avg(offense_snap_pct) filter (where snaps_known) as avg_offense_snap_pct,
        -- team denominators over the player's appearance games only (plan §5/§6): a stat row
        -- without an appearance (special-teams-only game) must not widen the denominator
        sum(team_targets) filter (where played) as team_targets, sum(team_carries) filter (where played) as team_carries,
        sum(team_air_yards) filter (where played) as team_air_yards, sum(team_attempts) filter (where played) as team_attempts,
        sum(team_dropbacks_excl_scrambles) filter (where played) as team_dropbacks_excl_scrambles,
        sum(team_dropbacks) filter (where played) as team_dropbacks,
        -- play-derived (Phase 2): routes proxy over games with participation; first reads over charted games
        count(*) filter (where routes_proxy is not null) as games_with_participation,
        sum(routes_proxy) as routes_proxy,
        sum(team_dropbacks_with_participation) filter (where routes_proxy is not null and played) as team_dropbacks_with_participation,
        sum(targets) filter (where routes_proxy is not null) as targets_in_participation_games,
        sum(receiving_yards) filter (where routes_proxy is not null) as receiving_yards_in_participation_games,
        count(*) filter (where routes is not null) as games_with_routes,
        sum(routes) as routes,
        max(routes_provider) as routes_provider,
        sum(targets) filter (where routes is not null) as targets_in_route_games,
        sum(receiving_yards) filter (where routes is not null) as receiving_yards_in_route_games,
        count(*) filter (where charted_targets is not null and team_charted_targets > 0) as games_with_charting,
        sum(charted_targets) as charted_targets, sum(first_read_targets) as first_read_targets,
        sum(designed_targets) as designed_targets, sum(checkdown_targets) as checkdown_targets,
        sum(later_read_targets) as later_read_targets, sum(scramble_drill_targets) as scramble_drill_targets,
        sum(team_first_read_targets) filter (where played) as team_first_read_targets, sum(team_charted_targets) filter (where played) as team_charted_targets,
        sum(drops) as drops, sum(catchable_targets) as catchable_targets, sum(contested_targets) as contested_targets,
        sum(red_zone_targets) as red_zone_targets, sum(inside_10_targets) as inside_10_targets, sum(deep_targets) as deep_targets,
        sum(red_zone_carries) as red_zone_carries, sum(inside_10_carries) as inside_10_carries, sum(inside_5_carries) as inside_5_carries,
        sum(team_red_zone_targets) filter (where played) as team_red_zone_targets, sum(team_red_zone_carries) filter (where played) as team_red_zone_carries,
        sum(dropbacks) as dropbacks, sum(scrambles) as scrambles, sum(sacks_taken) as sacks_taken,
        -- fantasy
        sum(nflverse_fantasy_points_std) as nflverse_fantasy_points_std,
        sum(nflverse_fantasy_points_ppr) as nflverse_fantasy_points_ppr,
        sum(points_current_scoring) as points_current_scoring,
        max(points_current_scoring_league_id) as points_current_scoring_league_id
    from pg
    group by 1, 2, 3
)

select
    a.*,
    -- rates: NULL on zero denominators; never clipped
    case when team_targets > 0 then round(targets::numeric / team_targets, 4) end            as target_share,
    case when team_carries > 0 then round(carries::numeric / team_carries, 4) end            as carry_share,
    case when team_air_yards <> 0 then round(receiving_air_yards::numeric / team_air_yards, 4) end as air_yards_share,
    coalesce(team_air_yards, 0) <= 0                                                          as air_yards_denominator_unstable,
    case when games_played > 0 then round(targets::numeric / games_played, 2) end             as targets_per_game,
    case when games_played > 0 then round(carries::numeric / games_played, 2) end             as carries_per_game,
    case when targets > 0 then round(receptions::numeric / targets, 4) end                    as catch_rate,
    case when targets > 0 then round(receiving_yards::numeric / targets, 2) end               as yards_per_target,
    case when targets > 0 then round(receiving_air_yards::numeric / targets, 2) end           as adot,
    case when receptions > 0 then round(receiving_yards_after_catch::numeric / receptions, 2) end as yac_per_reception,
    case when carries > 0 then round(rushing_yards::numeric / carries, 2) end                 as yards_per_carry,
    case when attempts > 0 then round(completions::numeric / attempts, 4) end                 as completion_rate,
    case when attempts > 0 then round(passing_yards::numeric / attempts, 2) end               as yards_per_attempt,
    case when fg_att > 0 then round(fg_made::numeric / fg_att, 4) end                         as fg_pct,
    case when games_played > 0 then round(points_current_scoring / games_played, 2) end       as points_current_scoring_per_game,
    case when games_played > 0 then round(nflverse_fantasy_points_ppr::numeric / games_played, 2) end as nflverse_ppr_per_game,
    -- routes / TPRR / YPRR remain NULL until a verified route source exists (plan §6)
    -- routes: licensed feed when imported (NULL otherwise); participation proxy always labelled as such
    case when routes > 0 then round(targets_in_route_games::numeric / routes, 4) end          as targets_per_route_run,
    case when routes > 0 then round(receiving_yards_in_route_games::numeric / routes, 2) end  as yards_per_route_run,
    case when routes_proxy > 0 then round(targets_in_participation_games::numeric / routes_proxy, 4) end        as tprr_proxy,
    case when routes_proxy > 0 then round(receiving_yards_in_participation_games::numeric / routes_proxy, 2) end as yprr_proxy,
    case when team_dropbacks_with_participation > 0
         then round(routes_proxy::numeric / team_dropbacks_with_participation, 4) end          as route_participation,
    case when games_with_participation > 0 then round(routes_proxy::numeric / games_with_participation, 1) end as routes_proxy_per_game,
    -- first-read target share (plan §6): player first-read targets / team first-read targets over
    -- the player's games, with the coverage it was computed on. NULL before 2022 and on zero denominators.
    case when team_first_read_targets > 0 then round(first_read_targets::numeric / team_first_read_targets, 4) end as first_read_target_share,
    case when team_charted_targets > 0 then round(team_charted_targets::numeric / nullif(team_targets, 0), 4) end   as charting_coverage,
    case when charted_targets > 0 then round(first_read_targets::numeric / charted_targets, 4) end   as first_read_rate_of_targets,
    case when charted_targets > 0 then round(designed_targets::numeric / charted_targets, 4) end     as designed_rate_of_targets,
    case when team_red_zone_targets > 0 then round(red_zone_targets::numeric / team_red_zone_targets, 4) end as red_zone_target_share,
    case when team_red_zone_carries > 0 then round(red_zone_carries::numeric / team_red_zone_carries, 4) end as red_zone_carry_share,
    case when games_played > 0 and dropbacks is not null then round(dropbacks::numeric / games_played, 1) end as dropbacks_per_game,
    '1.0'::text                                                                               as first_read_metric_version
from agg as a
