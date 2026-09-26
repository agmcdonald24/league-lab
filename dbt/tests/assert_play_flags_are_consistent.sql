-- Eligibility flags in fct_play must be mutually consistent (plan §9.5: sack/scramble, nullified,
-- two-point, spike/kneel). Any row here is a definition bug.
select game_id, play_id, play_type, 'sack counted as pass attempt' as problem from {{ ref('fct_play') }} where is_sack and is_pass_attempt
union all
select game_id, play_id, play_type, 'target on a nullified play' from {{ ref('fct_play') }} where is_no_play and (is_target or is_dropback or is_rush_attempt)
union all
select game_id, play_id, play_type, 'two-point try counted as target or carry' from {{ ref('fct_play') }} where is_two_point and (is_target or is_rush_attempt or is_dropback)
union all
select game_id, play_id, play_type, 'scramble without rusher / with pass attempt' from {{ ref('fct_play') }} where is_scramble and (rusher_player_id is null or is_pass_attempt)
union all
select game_id, play_id, play_type, 'spike counted as target or dropback' from {{ ref('fct_play') }} where is_spike and (is_target or is_dropback)
union all
select game_id, play_id, play_type, 'kneel counted as dropback or target' from {{ ref('fct_play') }} where is_kneel and (is_dropback or is_target)
union all
select game_id, play_id, play_type, 'target without receiver' from {{ ref('fct_play') }} where is_target and receiver_player_id is null
union all
select game_id, play_id, play_type, 'dropback that is neither attempt, sack nor scramble' from {{ ref('fct_play') }} where is_dropback and not (is_pass_attempt or is_sack or is_scramble)
