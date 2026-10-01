{{ config(
    indexes=[{'columns': ['receiver_gsis_id', 'defender_gsis_id', 'season']}, {'columns': ['season', 'defender_gsis_id']}],
    post_hook="analyze {{ this }}") }}
-- Receiver x defender x game (2022 on, participation seasons): his targets, catches, yards on catches and TDs on
-- the plays that defender was on the field (every defender listed, not only corners), and targets_vs_defense = all
-- his targets against that game's defense that season (the denominator of "on the field for 61% of his targets
-- vs DET"), carried on the row so mart_receiver_vs_cb needs no join back. No join at all (C5 performance hotfix):
-- the defender list is unnested in the select list and the denominator is a window count.
with t as (
    select p.*, count(*) over (partition by p.receiver_gsis_id, p.season, p.defteam) as targets_vs_defense
    from {{ ref('int_target_participation') }} as p
),

on_field as (   -- one row per target play x defender on the field (a defender listed twice counts once)
    select distinct game_id, play_id, season, posteam, defteam, receiver_gsis_id, is_complete, receiving_yards, is_td,
           targets_vs_defense, unnest(string_to_array(defense_players, ';')) as defender_gsis_id
    from t
)

select receiver_gsis_id, defender_gsis_id, game_id, season,
       max(posteam)                                                         as receiver_team,
       max(defteam)                                                         as defense,
       count(*)                                                             as targets,
       count(*) filter (where is_complete)                                  as receptions,
       coalesce(sum(receiving_yards) filter (where is_complete), 0)         as receiving_yards,
       count(*) filter (where is_td)                                        as receiving_tds,
       max(targets_vs_defense)                                              as targets_vs_defense
from on_field
where defender_gsis_id <> ''
group by 1, 2, 3, 4
