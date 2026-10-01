{{ config(indexes=[{'columns': ['receiver_gsis_id', 'defender_gsis_id', 'season'], 'unique': True}, {'columns': ['defender_gsis_id']}],
          pre_hook=["analyze {{ ref('fct_player_game') }}", "analyze {{ ref('dim_player') }}"],
          post_hook="analyze {{ this }}") }}
-- Who a receiver has actually faced (plan R-14), one row per receiver (WR/TE) x cornerback x season, regular
-- season, 2022 on. Two kinds of evidence, never mixed in one row:
--   'on_field'  - completed seasons with participation: his targets, catches, yards and TDs on the plays
--                 where that corner was on the field (play level), and the share of his targets against that
--                 defense those plays make ("on the field for 61% of his targets vs DET"). On the field is not
--                 "covering him": public data does not say which defender covered which receiver.
--   'same_game' - the current season (its participation file arrives after the postseason): his totals
--                 in the games that corner played, with the corner's average share of his defense's snaps.
-- Cornerbacks = the pool of mart_cb_rankings (that season's window).
-- Built over indexed, analyzed tables with equality joins only (C5 performance hotfix): int_target_participation
-- (target plays with the defense's on-field list) -> int_receiver_defender_game (receiver x defender x game), and
-- int_defender_snap_share for the same-game rows.
with cbs as (
    select distinct season, gsis_id from {{ ref('mart_cb_rankings') }} where window_label = 'season' and season >= 2022
),

receivers as (
    select gsis_id from {{ ref('dim_player') }} where position in ('WR', 'TE')
),

last_part_season as (   -- the latest season whose plays carry an on-field list for the defense (they run 2016 on,
                        -- without gaps); later seasons get same-game evidence. A scalar, evaluated once.
    select coalesce(max(season), 2021) as season from {{ ref('int_target_participation') }}
),

-- the corner's rows: receiver x corner x game, WR / TE receivers only. No join: the corner pool and the receivers
-- are stacked under the game rows and flagged with window functions (C5 performance hotfix)
flagged as (
    select receiver_gsis_id, defender_gsis_id, game_id, season, receiver_team, defense, targets, receptions,
           receiving_yards, receiving_tds, targets_vs_defense, 0 as src
    from {{ ref('int_receiver_defender_game') }}
    union all
    select null, gsis_id, null, season, null, null, null, null, null, null, null, 1 from cbs
    union all
    select gsis_id, null, null, null, null, null, null, null, null, null, null, 2 from receivers
),

marked as (
    select f.*,
           bool_or(f.src = 1) over (partition by f.season, f.defender_gsis_id) as is_cb,
           bool_or(f.src = 2) over (partition by f.receiver_gsis_id)          as is_receiver
    from flagged as f
),

on_field_games as (
    select * from marked where src = 0 and is_cb and is_receiver
),

-- per defense first (a traded corner can face him with two defenses: his targets against each count once), then
-- per season; no join back, so nothing for a planner to misestimate
on_field_def as (
    select receiver_gsis_id, defender_gsis_id, season, defense,
           max(receiver_team) as receiver_team, count(distinct game_id) as games,
           sum(targets) as targets, sum(receptions) as receptions, sum(receiving_yards) as receiving_yards,
           sum(receiving_tds) as receiving_tds, max(targets_vs_defense) as targets_vs_defense
    from on_field_games
    group by 1, 2, 3, 4
),

on_field as (
    select receiver_gsis_id, defender_gsis_id, season,
           max(receiver_team) as receiver_team, max(defense) as defense,
           sum(games)::bigint                                          as games,
           sum(targets)                                                as targets,
           sum(receptions)                                             as receptions,
           sum(receiving_yards)                                        as receiving_yards,   -- no catch = 0 yards
           sum(receiving_tds)                                          as receiving_tds,
           null::numeric                                               as defender_snap_share,
           sum(targets_vs_defense)                                     as targets_vs_defense
    from on_field_def
    group by 1, 2, 3
),

-- game level (seasons without participation): the corners who played, and his line in that game
def_snaps as (
    select * from {{ ref('int_defender_snap_share') }}
    where season > (select season from last_part_season)
),

same_game as (
    select pg.gsis_id as receiver_gsis_id, d.gsis_id as defender_gsis_id, pg.season,
           max(pg.team) as receiver_team, max(d.team) as defense,
           count(distinct pg.game_id)                                  as games,
           sum(pg.targets)                                             as targets,
           sum(pg.receptions)                                          as receptions,
           sum(pg.receiving_yards)                                     as receiving_yards,
           sum(pg.receiving_tds)                                       as receiving_tds,
           round(avg(d.snap_share), 3)                                 as defender_snap_share,
           null::bigint                                                as targets_vs_defense
    from {{ ref('fct_player_game') }} as pg
    join receivers as r on r.gsis_id = pg.gsis_id
    join def_snaps as d on d.game_id = pg.game_id and d.team = pg.opponent_team and d.defense_snaps > 0
    join cbs on cbs.season = d.season and cbs.gsis_id = d.gsis_id
    where pg.season_type = 'REG' and pg.played and pg.season >= 2022 and pg.season > (select season from last_part_season)
    group by 1, 2, 3
),

-- the names: dim_player stacked under the rows and broadcast by id with window functions (no join, C5 hotfix)
rows_and_names as (
    select b.*, null::text as name_id, null::text as name, 0 as src
    from (
        select *, 'on_field' as evidence from on_field
        union all
        select *, 'same_game' from same_game
    ) as b
    union all
    select null, null, null, null, null, null, null, null, null, null, null, null, null, gsis_id, player_name, 1
    from {{ ref('dim_player') }}
),

named as (
    select r.*,
           max(r.name) over (partition by coalesce(r.receiver_gsis_id, r.name_id)) as receiver_name,
           max(r.name) over (partition by coalesce(r.defender_gsis_id, r.name_id)) as defender_name
    from rows_and_names as r
)

select b.receiver_gsis_id, b.receiver_name, b.defender_gsis_id, b.defender_name,
       b.season, b.evidence, b.receiver_team, b.defense, b.games,
       b.targets::int as targets, b.receptions::int as receptions, b.receiving_yards::int as receiving_yards,
       b.receiving_tds::int as receiving_tds, b.defender_snap_share,
       b.targets_vs_defense::int as targets_vs_defense,
       round(b.targets::numeric / nullif(b.targets_vs_defense, 0), 3) as share_of_targets
from named as b
where b.src = 0
