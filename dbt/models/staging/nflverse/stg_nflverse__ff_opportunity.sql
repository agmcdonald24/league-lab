-- ffverse expected stats per player-week, renamed to the nflverse stat names so the same
-- scoring macro can price *expected* production under league scoring. Columns the model does
-- not produce (kicking, fumbles) are zero here: expected points cover pass/rush/receive only.
select
    player_id                                   as gsis_id,
    season,
    week,
    game_id,
    posteam                                     as team,
    full_name                                   as player_name,
    position,
    -- opportunity volume (actual)
    pass_attempt                                as attempts,
    rec_attempt                                 as targets,
    rush_attempt                                as carries,
    pass_air_yards, rec_air_yards,
    -- expected counting stats, nflverse names
    pass_completions_exp                        as completions,
    pass_yards_gained_exp                       as passing_yards,
    pass_touchdown_exp                          as passing_tds,
    pass_interception_exp                       as passing_interceptions,
    pass_two_point_conv_exp                     as passing_2pt_conversions,
    rush_yards_gained_exp                       as rushing_yards,
    rush_touchdown_exp                          as rushing_tds,
    rush_two_point_conv_exp                     as rushing_2pt_conversions,
    receptions_exp                              as receptions,
    rec_yards_gained_exp                        as receiving_yards,
    rec_touchdown_exp                           as receiving_tds,
    rec_two_point_conv_exp                      as receiving_2pt_conversions,
    0::double precision as fumbles_total, 0::double precision as fumbles_lost_total,
    0::double precision as fumble_recovery_tds, 0::double precision as special_teams_tds,
    0::double precision as fg_made_0_19, 0::double precision as fg_made_20_29, 0::double precision as fg_made_30_39,
    0::double precision as fg_made_40_49, 0::double precision as fg_made_50_59, 0::double precision as fg_made_60_,
    0::double precision as fg_missed, 0::double precision as fg_blocked,
    0::double precision as fg_missed_0_19, 0::double precision as fg_missed_20_29, 0::double precision as fg_missed_30_39,
    0::double precision as fg_missed_40_49, 0::double precision as fg_missed_50_59, 0::double precision as fg_missed_60_,
    0::double precision as pat_made, 0::double precision as pat_missed, 0::double precision as pat_blocked,
    -- the model's own actual/expected fantasy points (its scoring, kept for reference only)
    total_fantasy_points                        as ffopp_fantasy_points,
    total_fantasy_points_exp                    as ffopp_fantasy_points_exp,
    -- actuals as the model saw them (for a consistency check against nflverse)
    receptions                                  as actual_receptions,
    rec_yards_gained                            as actual_receiving_yards,
    rush_yards_gained                           as actual_rushing_yards,
    pass_yards_gained                           as actual_passing_yards,
    _fetched_at                                 as source_fetched_at
from {{ source('raw', 'nfl_ff_opportunity') }}
where player_id is not null
  and season >= {{ var('seasons_start') }}
