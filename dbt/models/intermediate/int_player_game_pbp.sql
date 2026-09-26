{{ config(indexes=[{'columns': ['gsis_id', 'game_id'], 'unique': True}]) }}
-- Player x game counts derived from plays and participation:
--   * targets by read (FTN, 2022+) - first read, designed, checkdown, later, scramble drill
--   * routes_proxy: dropbacks the player was on the field for (participation), receiving
--     positions only. A PROXY: presence on a dropback is not proof a route was run (blocking
--     tight ends, chip-and-release backs). Labelled as such everywhere it is shown.
--   * dropbacks as the QB on the play (attempts + sacks + scrambles)
-- Team denominators live in int_team_game_pbp; this table carries only the player's numerators
-- plus the team's participation-covered dropbacks for the same game (the routes_proxy denominator).
with plays as (
    select * from {{ ref('fct_play') }} where not is_no_play
),

charting as (
    select game_id, play_id, read_thrown, is_charted_target, is_first_read_target, is_designed_target,
           is_checkdown_target, is_later_read_target, is_scramble_drill_target, is_drop, is_catchable_ball, is_contested_ball
    from {{ ref('fct_play_charting') }}
),

-- receiving numerators
recv as (
    select
        p.receiver_player_id                                         as gsis_id,
        p.game_id,
        count(*) filter (where p.is_target)                          as targets_pbp,
        count(*) filter (where p.is_two_point_target)                as two_point_targets,
        count(*) filter (where p.is_target and p.is_complete)        as receptions_pbp,
        sum(p.receiving_yards) filter (where p.is_target)            as receiving_yards_pbp,
        sum(p.air_yards) filter (where p.is_target)                  as air_yards_pbp,
        count(*) filter (where p.is_target and p.is_red_zone)        as red_zone_targets,
        count(*) filter (where p.is_target and p.yardline_100 <= 10) as inside_10_targets,
        count(*) filter (where p.is_target and p.air_yards >= 20)    as deep_targets,
        count(*) filter (where c.is_charted_target)                  as charted_targets,
        count(*) filter (where c.is_first_read_target)               as first_read_targets,
        count(*) filter (where c.is_designed_target)                 as designed_targets,
        count(*) filter (where c.is_checkdown_target)                as checkdown_targets,
        count(*) filter (where c.is_later_read_target)               as later_read_targets,
        count(*) filter (where c.is_scramble_drill_target)           as scramble_drill_targets,
        count(*) filter (where p.is_target and c.is_drop)            as drops,
        count(*) filter (where p.is_target and c.is_catchable_ball)  as catchable_targets,
        count(*) filter (where p.is_target and c.is_contested_ball)  as contested_targets
    from plays as p
    left join charting as c using (game_id, play_id)
    where p.receiver_player_id is not null
    group by 1, 2
),

-- rushing numerators
rush as (
    select
        p.rusher_player_id                                           as gsis_id,
        p.game_id,
        count(*) filter (where p.is_rush_attempt)                    as carries_pbp,
        count(*) filter (where p.is_rush_attempt and p.is_scramble)  as scrambles,
        count(*) filter (where p.is_rush_attempt and p.is_red_zone)  as red_zone_carries,
        count(*) filter (where p.is_rush_attempt and p.yardline_100 <= 10) as inside_10_carries,
        count(*) filter (where p.is_rush_attempt and p.yardline_100 <= 5)  as inside_5_carries
    from plays as p
    where p.rusher_player_id is not null
    group by 1, 2
),

-- QB on the play
qb as (
    select
        p.qb_player_id                                               as gsis_id,
        p.game_id,
        count(*) filter (where p.is_dropback)                        as dropbacks,
        count(*) filter (where p.is_dropback and p.is_sack)          as sacks_taken,
        count(*) filter (where p.is_dropback and p.is_scramble)      as scramble_dropbacks
    from plays as p
    where p.qb_player_id is not null
    group by 1, 2
),

-- participation: on the field for which kinds of plays
part as (
    select
        b.gsis_id,
        b.game_id,
        count(*)                                                     as plays_on_field,
        count(*) filter (where p.is_dropback)                        as dropbacks_on_field,
        count(*) filter (where p.is_rush_attempt)                    as rushes_on_field
    from {{ ref('bridge_play_participation') }} as b
    join plays as p using (game_id, play_id)
    group by 1, 2
),

keys as (
    select gsis_id, game_id from recv
    union select gsis_id, game_id from rush
    union select gsis_id, game_id from qb
    union select gsis_id, game_id from part
),

-- position for the routes_proxy eligibility: that week's roster position, else the player record
-- (fct_player_game consumes this model, so it cannot be used here)
pos as (
    select k.gsis_id, k.game_id, g.season, g.week,
           coalesce(r.position, d.position) as position,
           r.team
    from keys as k
    join {{ ref('dim_game') }} as g using (game_id)
    left join {{ ref('int_player_week_team') }} as r on r.gsis_id = k.gsis_id and r.season = g.season and r.week = g.week
    left join {{ ref('dim_player') }} as d on d.gsis_id = k.gsis_id
)

select
    k.gsis_id,
    k.game_id,
    pos.season,
    pos.week,
    pos.position,
    pos.team,
    coalesce(recv.targets_pbp, 0)               as targets_pbp,
    coalesce(recv.two_point_targets, 0)         as two_point_targets,
    coalesce(recv.receptions_pbp, 0)            as receptions_pbp,
    recv.receiving_yards_pbp,
    recv.air_yards_pbp,
    coalesce(recv.red_zone_targets, 0)          as red_zone_targets,
    coalesce(recv.inside_10_targets, 0)         as inside_10_targets,
    coalesce(recv.deep_targets, 0)              as deep_targets,
    coalesce(recv.charted_targets, 0)           as charted_targets,
    coalesce(recv.first_read_targets, 0)        as first_read_targets,
    coalesce(recv.designed_targets, 0)          as designed_targets,
    coalesce(recv.checkdown_targets, 0)         as checkdown_targets,
    coalesce(recv.later_read_targets, 0)        as later_read_targets,
    coalesce(recv.scramble_drill_targets, 0)    as scramble_drill_targets,
    coalesce(recv.drops, 0)                     as drops,
    coalesce(recv.catchable_targets, 0)         as catchable_targets,
    coalesce(recv.contested_targets, 0)         as contested_targets,
    coalesce(rush.carries_pbp, 0)               as carries_pbp,
    coalesce(rush.scrambles, 0)                 as scrambles,
    coalesce(rush.red_zone_carries, 0)          as red_zone_carries,
    coalesce(rush.inside_10_carries, 0)         as inside_10_carries,
    coalesce(rush.inside_5_carries, 0)          as inside_5_carries,
    qb.dropbacks,
    qb.sacks_taken,
    qb.scramble_dropbacks,
    part.plays_on_field,
    part.dropbacks_on_field,
    part.rushes_on_field,
    -- routes proxy: receiving positions only; NULL (unknown) when the game has no participation
    case when pos.position in ('WR', 'TE', 'RB', 'FB', 'HB') then part.dropbacks_on_field end as routes_proxy,
    part.plays_on_field is not null             as participation_known
from keys as k
left join pos using (gsis_id, game_id)
left join recv using (gsis_id, game_id)
left join rush using (gsis_id, game_id)
left join qb using (gsis_id, game_id)
left join part using (gsis_id, game_id)
