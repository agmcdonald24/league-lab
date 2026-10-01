{{ config(
    indexes=[{'columns': ['game_id', 'play_id'], 'unique': True}, {'columns': ['receiver_gsis_id', 'season', 'defteam']}],
    pre_hook=["analyze {{ ref('fct_play') }}"],
    post_hook="analyze {{ this }}") }}
-- Every regular-season target (2022 on) whose play carries the defense's on-field list (participation; a season's
-- file arrives after its postseason, so the current season has none): one row per target play with the
-- ';'-separated defender ids. Feeds int_receiver_defender_game and mart_receiver_vs_cb (plan R-14).
-- No join (C5 performance hotfix): the raw participation table has no index, so a planner that misjudged the
-- sizes could loop over it; instead the target rows and the participation rows are stacked and grouped on
-- (game_id, play_id) - both sides are unique on it - keeping the plays that have both.
with stacked as (
    select p.game_id, p.play_id, p.season, p.posteam, p.defteam, p.receiver_player_id as receiver_gsis_id,
           p.is_complete, coalesce(p.receiving_yards, 0) as receiving_yards,
           (p.pass_touchdown and p.td_player_id = p.receiver_player_id) as is_td,
           null::text as defense_players, true as is_target
    from {{ ref('fct_play') }} as p
    where p.season >= 2022 and p.season_type = 'REG'
      and p.is_target and not p.is_no_play and not p.is_two_point and p.receiver_player_id is not null
    union all
    select pa.game_id, pa.play_id, null, null, null, null, null, null, null, pa.defense_players, false
    from {{ ref('stg_nflverse__pbp_participation') }} as pa
    where pa.season >= 2022 and pa.defense_players is not null
)

select game_id, play_id, max(season) as season, max(posteam) as posteam, max(defteam) as defteam,
       max(receiver_gsis_id) as receiver_gsis_id, bool_or(is_complete) as is_complete,
       max(receiving_yards) as receiving_yards, bool_or(is_td) as is_td, max(defense_players) as defense_players
from stacked
group by game_id, play_id
having bool_or(is_target) and bool_or(not is_target)
