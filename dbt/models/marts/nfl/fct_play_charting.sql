{{ config(indexes=[{'columns': ['game_id', 'play_id'], 'unique': True}, {'columns': ['season', 'week']}]) }}
-- FTN charting joined to fct_play (2022+). Grain (game_id, play_id). Every rate built on this
-- table must carry the coverage it was computed on: `is_charted_target` is the classified subset.
with c as (
    select * from {{ ref('stg_nflverse__ftn_charting') }}
),

p as (
    select game_id, play_id, season, week, posteam, receiver_player_id, qb_player_id,
           is_target, is_pass_attempt, is_dropback, is_two_point
    from {{ ref('fct_play') }}
)

select
    p.game_id,
    p.play_id,
    p.season,
    p.week,
    p.posteam,
    p.receiver_player_id,
    p.qb_player_id,
    p.is_target,
    p.is_dropback,
    c.read_thrown,
    c.read_thrown_raw,
    p.is_target and c.read_thrown is not null                as is_charted_target,
    p.is_target and c.read_thrown = 'first'                  as is_first_read_target,
    p.is_target and c.read_thrown = 'designed'               as is_designed_target,
    p.is_target and c.read_thrown = 'checkdown'              as is_checkdown_target,
    p.is_target and c.read_thrown = 'scramble_drill'         as is_scramble_drill_target,
    p.is_target and c.read_thrown = 'later'                  as is_later_read_target,
    c.is_throw_away,
    c.is_drop,
    c.is_catchable_ball,
    c.is_contested_ball,
    c.is_created_reception,
    c.is_interception_worthy,
    c.is_play_action,
    c.is_screen_pass,
    c.is_rpo,
    c.is_motion,
    c.is_no_huddle,
    c.is_qb_out_of_pocket,
    c.is_qb_sneak,
    c.is_trick_play,
    c.is_qb_fault_sack,
    c.starting_hash,
    c.qb_location,
    c.n_offense_backfield,
    c.n_defense_box,
    c.n_blitzers,
    c.n_pass_rushers,
    c.charted_at
from c
join p using (game_id, play_id)
