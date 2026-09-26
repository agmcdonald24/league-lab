{{ config(indexes=[{'columns': ['gsis_id', 'season']}, {'columns': ['game_id', 'play_id']}]) }}
-- Who did what on each play: passer / receiver / rusher / kicker / scorer. Actor != on-field
-- (that is bridge_play_participation). One row per (game_id, play_id, role, gsis_id).
with p as (select * from {{ ref('fct_play') }})

select game_id, play_id, season, posteam as team, 'passer' as role, passer_player_id as gsis_id from p where passer_player_id is not null
union all
select game_id, play_id, season, posteam, 'receiver', receiver_player_id from p where receiver_player_id is not null
union all
select game_id, play_id, season, posteam, 'rusher', rusher_player_id from p where rusher_player_id is not null
union all
select game_id, play_id, season, posteam, 'kicker', kicker_player_id from p where kicker_player_id is not null
union all
select game_id, play_id, season, posteam, 'scorer', td_player_id from p where td_player_id is not null
