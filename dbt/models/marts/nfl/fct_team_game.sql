{{ config(indexes=[{'columns': ['team', 'game_id'], 'unique': True}]) }}
-- Team x game totals: independent denominators for all share metrics.
select
    t.team,
    t.game_id,
    t.season,
    t.season_type,
    t.week,
    t.opponent_team,
    g.game_date,
    g.home_team = t.team                     as is_home,
    t.attempts, t.completions, t.passing_yards, t.passing_tds, t.passing_interceptions,
    t.sacks_suffered, t.passing_air_yards, t.passing_yards_after_catch, t.passing_first_downs,
    t.passing_epa,
    t.carries, t.rushing_yards, t.rushing_tds, t.rushing_first_downs, t.rushing_epa,
    t.targets, t.receptions, t.receiving_yards, t.receiving_tds, t.receiving_air_yards,
    t.dropbacks_excl_scrambles,
    t.plays_excl_scrambles,
    case when t.plays_excl_scrambles > 0
         then round(t.dropbacks_excl_scrambles::numeric / t.plays_excl_scrambles, 4) end as pass_rate_excl_scrambles,
    t.fumbles_total, t.fumbles_lost_total, t.penalties, t.penalty_yards,
    -- play-derived (Phase 2): true dropbacks = attempts + sacks + scrambles (no spikes/kneels/2-pt)
    pb.dropbacks,
    pb.scrambles,
    pb.spikes,
    pb.kneels,
    pb.two_point_tries,
    pb.plays                                                          as plays_pbp,
    case when pb.plays > 0 then round(pb.dropbacks::numeric / pb.plays, 4) end as dropback_rate,
    pb.red_zone_targets, pb.red_zone_carries,
    pb.charted_targets, pb.first_read_targets, pb.designed_targets, pb.charting_coverage,
    pb.dropbacks_with_participation, pb.participation_coverage
from {{ ref('stg_nflverse__team_stats_week') }} as t
left join {{ ref('dim_game') }} as g using (game_id)
left join {{ ref('int_team_game_pbp') }} as pb on pb.team = t.team and pb.game_id = t.game_id
