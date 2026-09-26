{{ config(indexes=[
    {'columns': ['game_id', 'play_id'], 'unique': True},
    {'columns': ['season', 'posteam']},
    {'columns': ['receiver_player_id', 'season']},
    {'columns': ['rusher_player_id', 'season']},
    {'columns': ['qb_player_id', 'season']},
]) }}
-- One row per play with the eligibility flags every play-derived metric must use (plan §6):
--
--   is_no_play        nullified / no play (penalty declined, timeout rows, ...). Kept, never counted.
--   is_dropback       pass attempt, sack or scramble on a real play; excludes two-point tries so
--                     team dropbacks reconcile with attempts + sacks + scrambles in team stats
--   is_pass_attempt   ball thrown (completion, incompletion, interception, spike); sacks excluded.
--                     Spikes count as attempts in official stats (reconciles with team `attempts`)
--                     but are not dropbacks and never targets
--   is_target         pass attempt to an identified receiver, excluding two-point tries
--                     (reconciles exactly with nflverse weekly `targets`, 2025: 0 of 4,533 player-weeks differ)
--   is_rush_attempt   rush attempt incl. scrambles and kneels, excluding two-point tries
--                     (reconciles exactly with nflverse weekly `carries`)
--   is_two_point      two-point conversion try (pass or run) - flagged separately, never a target/carry
--
-- Context (plan §6): half with overtime separate, pre-play score state from the offense's
-- perspective (raw score kept), down-and-distance bucket, field zone, QB on the play.
with p as (
    select * from {{ ref('stg_nflverse__pbp') }}
)

select
    p.game_id,
    p.play_id,
    p.season,
    p.season_type,
    p.week,
    p.game_date,
    p.posteam,
    p.defteam,
    p.home_team,
    p.away_team,
    p.posteam = p.home_team                                      as posteam_is_home,
    p.qtr,
    case p.game_half when 'Half1' then 'H1' when 'Half2' then 'H2' when 'Overtime' then 'OT' end as half,
    p.down,
    p.ydstogo,
    p.yardline_100,
    p.goal_to_go,
    p.quarter_seconds_remaining,
    p.half_seconds_remaining,
    p.game_seconds_remaining,
    p.clock,
    p.play_type,
    p.description,
    -- pre-play score state (never from the final score)
    p.posteam_score_pre,
    p.defteam_score_pre,
    p.score_differential_pre,
    case when p.score_differential_pre is null then null
         when p.score_differential_pre <= -9 then 'trailing_9plus'
         when p.score_differential_pre < 0  then 'trailing_1_8'
         when p.score_differential_pre = 0  then 'tied'
         when p.score_differential_pre <= 8 then 'leading_1_8'
         else 'leading_9plus' end                                as score_state,
    case when p.down is null then null
         when p.down = 1 then '1st'
         when p.down = 2 and p.ydstogo <= 3 then '2nd_short'
         when p.down = 2 and p.ydstogo <= 6 then '2nd_medium'
         when p.down = 2 then '2nd_long'
         when p.ydstogo <= 3 then '3rd_4th_short'
         when p.ydstogo <= 6 then '3rd_4th_medium'
         else '3rd_4th_long' end                                 as down_distance,
    case when p.yardline_100 is null then null
         when p.yardline_100 <= 10 then 'inside_10'
         when p.yardline_100 <= 20 then 'red_zone_11_20'
         when p.yardline_100 <= 50 then 'opp_half'
         else 'own_half' end                                     as field_zone,
    p.yardline_100 <= 20                                         as is_red_zone,
    -- eligibility flags
    p.play_type = 'no_play' or p.play_deleted                    as is_no_play,
    p.qb_kneel                                                   as is_kneel,
    p.qb_spike                                                   as is_spike,
    p.two_point_attempt                                          as is_two_point,
    p.penalty                                                    as has_penalty,
    p.aborted_play                                               as is_aborted,
    p.qb_dropback and not p.two_point_attempt
        and p.play_type <> 'no_play' and not p.play_deleted      as is_dropback,
    p.pass_attempt and not p.sack and p.play_type in ('pass', 'qb_spike')
        and not p.play_deleted                                   as is_pass_attempt,
    p.sack and p.play_type <> 'no_play'                          as is_sack,
    p.qb_scramble and p.play_type = 'run'                        as is_scramble,
    p.pass_attempt and not p.sack and p.play_type = 'pass' and not p.play_deleted
        and p.receiver_player_id is not null and not p.two_point_attempt as is_target,
    p.pass_attempt and not p.sack and p.play_type = 'pass' and not p.play_deleted
        and p.receiver_player_id is not null and p.two_point_attempt     as is_two_point_target,
    p.pass_attempt and not p.sack and p.play_type = 'pass' and not p.play_deleted
        and p.receiver_player_id is null                         as is_throw_without_receiver,  -- throwaways, spikes-as-pass, batted
    p.rush_attempt and p.play_type in ('run', 'qb_kneel') and not p.play_deleted
        and p.rusher_player_id is not null and not p.two_point_attempt as is_rush_attempt,
    p.complete_pass                                              as is_complete,
    p.interception                                               as is_interception,
    p.touchdown, p.pass_touchdown, p.rush_touchdown, p.first_down, p.fumble, p.fumble_lost, p.success,
    p.shotgun, p.no_huddle,
    -- actors
    p.passer_player_id,
    p.receiver_player_id,
    p.rusher_player_id,
    p.kicker_player_id,
    p.td_player_id,
    p.interception_player_id,
    -- QB on the play: the passer on throws and sacks, the rusher on scrambles (plan §6)
    case when p.qb_scramble and p.play_type = 'run' then p.rusher_player_id else p.passer_player_id end as qb_player_id,
    -- yards
    p.air_yards,
    p.yards_after_catch,
    p.yards_gained,
    p.passing_yards,
    p.receiving_yards,
    p.rushing_yards,
    p.pass_location,
    p.pass_length,
    p.run_location,
    p.run_gap,
    -- models
    p.epa, p.wpa, p.wp_pre, p.completion_probability, p.cpoe, p.xpass, p.pass_oe,
    p.drive, p.fixed_drive, p.series
from p
