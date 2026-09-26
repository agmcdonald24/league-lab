-- depends_on: {{ ref('scoring_stat_map') }}
{{ config(indexes=[{'columns': ['gsis_id', 'season']}, {'columns': ['player_name']}, {'columns': ['season', 'season_type', 'position']}, {'columns': ['game_id']}]) }}
-- Player x game facts (QB/RB/WR/TE/K and anyone else with a stat row): raw counting stats,
-- team denominators from fct_team_game, snaps, historical roster context, and computed
-- shares. Fantasy points under the *current* league scoring are added for cross-year research;
-- league history uses the historical scoring version in league_player_week.
with stats as (
    -- weekly stats plus the play-by-play long-touchdown counts the bonus scoring keys need
    -- (pass_td_40p ...); 0 when the game has no plays loaded, which only under-counts a bonus
    select w.*,
           coalesce(b.pass_tds_40p, 0) as pass_tds_40p, coalesce(b.pass_tds_50p, 0) as pass_tds_50p,
           coalesce(b.rush_tds_40p, 0) as rush_tds_40p, coalesce(b.rush_tds_50p, 0) as rush_tds_50p,
           coalesce(b.rec_tds_40p, 0)  as rec_tds_40p,  coalesce(b.rec_tds_50p, 0)  as rec_tds_50p
    from {{ ref('stg_nflverse__player_stats_week') }} as w
    left join {{ ref('int_player_game_pbp') }} as b on b.gsis_id = w.gsis_id and b.game_id = w.game_id
),

team as (
    select
        team, game_id, attempts as team_attempts, targets as team_targets, carries as team_carries,
        passing_air_yards as team_air_yards, dropbacks_excl_scrambles as team_dropbacks_excl_scrambles,
        receptions as team_receptions, receiving_yards as team_receiving_yards, rushing_yards as team_rushing_yards
    from {{ ref('fct_team_game') }}
),

snaps as (
    select gsis_id, game_id, offense_snaps, offense_snap_pct, snap_position
    from {{ ref('int_player_game_snaps') }}
),

roster as (
    select gsis_id, season, week, team as roster_team, roster_status, depth_chart_position
    from {{ ref('int_player_week_team') }}
),

current_scoring as (
    select scoring_settings, league_id as current_league_id, season as current_league_season
    from {{ ref('int_current_league') }}
),

pbp as (
    select * from {{ ref('int_player_game_pbp') }}
),

team_pbp as (
    select team, game_id, dropbacks as team_dropbacks, dropbacks_with_participation as team_dropbacks_with_participation,
           first_read_targets as team_first_read_targets, charted_targets as team_charted_targets,
           charting_coverage as team_charting_coverage, red_zone_targets as team_red_zone_targets,
           red_zone_carries as team_red_zone_carries
    from {{ ref('int_team_game_pbp') }}
),

-- licensed routes (raw.routes_feed via player_id_map; never by name). One provider row per player-week.
feed as (
    select coalesce(f.gsis_id, m_s.gsis_id, m_p.gsis_id) as gsis_id, f.season, f.week, f.routes, f.provider,
           row_number() over (partition by coalesce(f.gsis_id, m_s.gsis_id, m_p.gsis_id), f.season, f.week order by f.imported_at desc) as rn
    from {{ ref('stg_routes_feed') }} as f
    left join {{ ref('player_id_map') }} as m_s on m_s.sleeper_id = f.sleeper_id and f.gsis_id is null
    left join {{ ref('player_id_map') }} as m_p on m_p.pfr_id = f.pfr_id and f.gsis_id is null and f.sleeper_id is null
)

select
    s.gsis_id,
    s.game_id,
    s.season,
    s.season_type,
    s.week,
    s.team,
    s.opponent_team,
    g.game_date,
    g.home_team = s.team                                     as is_home,
    g.went_to_overtime,
    s.player_name,
    s.position,
    s.position_group,
    r.roster_status,
    r.depth_chart_position,
    r.roster_team,
    -- appearance evidence (plan §5): stat row present, snaps if known
    true                                                     as has_stat_row,
    sn.offense_snaps,
    sn.offense_snap_pct,
    sn.offense_snaps is not null                             as snaps_known,
    coalesce(sn.offense_snaps, 0) > 0
        or coalesce(s.attempts, 0) + coalesce(s.carries, 0) + coalesce(s.targets, 0)
         + coalesce(s.fg_att, 0) + coalesce(s.pat_att, 0) > 0 as played,
    -- passing
    s.completions, s.attempts, s.passing_yards, s.passing_tds, s.passing_interceptions,
    s.sacks_suffered, s.sack_yards_lost, s.sack_fumbles, s.sack_fumbles_lost,
    s.passing_air_yards, s.passing_yards_after_catch, s.passing_first_downs,
    s.passing_epa, s.passing_cpoe, s.passing_2pt_conversions,
    coalesce(s.attempts, 0) + coalesce(s.sacks_suffered, 0)  as dropbacks_excl_scrambles,
    -- rushing
    s.carries, s.rushing_yards, s.rushing_tds, s.rushing_fumbles, s.rushing_fumbles_lost,
    s.rushing_first_downs, s.rushing_epa, s.rushing_2pt_conversions,
    -- receiving
    s.receptions, s.targets, s.receiving_yards, s.receiving_tds, s.receiving_fumbles,
    s.receiving_fumbles_lost, s.receiving_air_yards, s.receiving_yards_after_catch,
    s.receiving_first_downs, s.receiving_epa, s.receiving_2pt_conversions,
    -- misc
    s.special_teams_tds, s.fumble_recovery_tds, s.fumbles_total, s.fumbles_lost_total,
    -- kicking
    s.fg_made, s.fg_att, s.fg_missed, s.fg_blocked, s.fg_long, s.fg_pct,
    s.fg_made_0_19, s.fg_made_20_29, s.fg_made_30_39, s.fg_made_40_49, s.fg_made_50_59, s.fg_made_60_,
    s.fg_made_50_59 + s.fg_made_60_                          as fg_made_50p,
    s.fg_missed_0_19, s.fg_missed_20_29, s.fg_missed_30_39, s.fg_missed_40_49, s.fg_missed_50_59, s.fg_missed_60_,
    s.pat_made, s.pat_att, s.pat_missed, s.pat_blocked,
    -- team denominators (independent totals)
    t.team_attempts, t.team_targets, t.team_carries, t.team_air_yards,
    t.team_dropbacks_excl_scrambles, t.team_receptions, t.team_receiving_yards, t.team_rushing_yards,
    -- shares (zero denominator -> NULL; signed air yards flagged, not clipped)
    case when t.team_targets > 0 then round(s.targets::numeric / t.team_targets, 4) end      as target_share,
    case when t.team_carries > 0 then round(s.carries::numeric / t.team_carries, 4) end      as carry_share,
    case when t.team_air_yards <> 0
         then round(s.receiving_air_yards::numeric / t.team_air_yards, 4) end                as air_yards_share,
    coalesce(t.team_air_yards, 0) <= 0                                                       as air_yards_denominator_unstable,
    case when s.targets > 0 then round(s.receiving_air_yards::numeric / s.targets, 2) end    as adot,
    case when s.receptions > 0 then round(s.receiving_yards_after_catch::numeric / s.receptions, 2) end as yac_per_reception,
    s.nflverse_target_share,
    s.nflverse_air_yards_share,
    s.nflverse_wopr,
    -- play-derived (Phase 2). routes_proxy = dropbacks on the field (participation), receiving
    -- positions only; NULL when the game has no participation file (unknown, not zero).
    pb.routes_proxy,
    tp.team_dropbacks,
    tp.team_dropbacks_with_participation,
    case when tp.team_dropbacks_with_participation > 0 and pb.routes_proxy is not null
         then round(pb.routes_proxy::numeric / tp.team_dropbacks_with_participation, 4) end   as route_participation,
    case when pb.routes_proxy > 0 then round(s.targets::numeric / pb.routes_proxy, 4) end       as tprr_proxy,
    case when pb.routes_proxy > 0 then round(s.receiving_yards::numeric / pb.routes_proxy, 2) end as yprr_proxy,
    -- licensed routes when a provider file has been imported (else NULL)
    fd.routes,
    fd.provider                                                                                as routes_provider,
    case when fd.routes > 0 then round(s.targets::numeric / fd.routes, 4) end                  as tprr,
    case when fd.routes > 0 then round(s.receiving_yards::numeric / fd.routes, 2) end          as yprr,
    -- first-read targets (FTN charting, 2022+): counts and coverage travel with the rate
    pb.charted_targets,
    pb.first_read_targets,
    pb.designed_targets,
    pb.checkdown_targets,
    pb.later_read_targets,
    pb.scramble_drill_targets,
    tp.team_first_read_targets,
    tp.team_charted_targets,
    tp.team_charting_coverage                                                                  as charting_coverage,
    case when tp.team_first_read_targets > 0
         then round(pb.first_read_targets::numeric / tp.team_first_read_targets, 4) end        as first_read_target_share,
    pb.drops, pb.catchable_targets, pb.contested_targets,
    pb.red_zone_targets, pb.inside_10_targets, pb.deep_targets,
    pb.red_zone_carries, pb.inside_10_carries, pb.inside_5_carries,
    tp.team_red_zone_targets, tp.team_red_zone_carries,
    pb.scrambles,
    -- QB: true dropbacks (attempts + sacks + scrambles) next to the stats-only version above
    pb.dropbacks,
    pb.sacks_taken,
    -- long touchdowns from play-by-play (the *_td_40p / *_td_50p bonus keys); 0 when no plays are loaded
    s.pass_tds_40p, s.pass_tds_50p, s.rush_tds_40p, s.rush_tds_50p, s.rec_tds_40p, s.rec_tds_50p,
    -- fantasy points
    s.nflverse_fantasy_points_std,
    s.nflverse_fantasy_points_ppr,
    case when cs.scoring_settings is null then null
         else {{ league_points('cs.scoring_settings', 's') }} end as points_current_scoring,
    cs.current_league_id                                     as points_current_scoring_league_id,
    cs.current_league_season                                 as points_current_scoring_season
from stats as s
left join {{ ref('dim_game') }} as g using (game_id)
left join team as t on t.team = s.team and t.game_id = s.game_id
left join snaps as sn on sn.gsis_id = s.gsis_id and sn.game_id = s.game_id
left join roster as r on r.gsis_id = s.gsis_id and r.season = s.season and r.week = s.week
left join pbp as pb on pb.gsis_id = s.gsis_id and pb.game_id = s.game_id
left join team_pbp as tp on tp.team = s.team and tp.game_id = s.game_id
left join feed as fd on fd.gsis_id = s.gsis_id and fd.season = s.season and fd.week = s.week and fd.rn = 1
left join current_scoring as cs on true
