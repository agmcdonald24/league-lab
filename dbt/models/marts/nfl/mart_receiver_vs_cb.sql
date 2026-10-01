{{ config(indexes=[{'columns': ['receiver_gsis_id', 'defender_gsis_id', 'season'], 'unique': True}, {'columns': ['defender_gsis_id']}], post_hook="analyze {{ this }}") }}
-- Who a receiver has actually faced (plan R-14), one row per receiver (WR/TE) x cornerback x season, regular
-- season, 2022 on. Two kinds of evidence, never mixed in one row:
--   'on_field'  - completed seasons with participation: his targets, catches, yards and TDs on the plays
--                 where that corner was on the field (play level), and the share of his targets against that
--                 defense those plays make ("on the field for 61% of his targets vs DET"). On the field is not
--                 "covering him": public data does not say which defender covered which receiver.
--   'same_game' - the current season (its participation file arrives after the postseason): his totals
--                 in the games that corner played, with the corner's average share of his defense's snaps.
-- Cornerbacks = the pool of mart_cb_rankings (that season's window).
with cbs as (
    select distinct season, gsis_id from {{ ref('mart_cb_rankings') }} where window_label = 'season' and season >= 2022
),

receivers as (
    select gsis_id from {{ ref('dim_player') }} where position in ('WR', 'TE')
),

part_seasons as (   -- seasons whose plays carry an on-field list for the defense
    select distinct season from {{ ref('stg_nflverse__pbp_participation') }} where defense_players is not null and season >= 2022
),

-- play level: every target with the defense on the field
tgt as (
    select p.game_id, p.play_id, p.season, p.posteam, p.defteam, p.receiver_player_id,
           p.is_complete, coalesce(p.receiving_yards, 0) as receiving_yards,
           (p.pass_touchdown and p.td_player_id = p.receiver_player_id) as is_td,
           pa.defense_players
    from {{ ref('fct_play') }} as p
    join {{ ref('stg_nflverse__pbp_participation') }} as pa on pa.game_id = p.game_id and pa.play_id = p.play_id
    where p.season in (select season from part_seasons) and p.season_type = 'REG'
      and p.is_target and not p.is_no_play and not p.is_two_point and p.receiver_player_id is not null
      and pa.defense_players is not null
),

-- his targets against each defense that season (the share's denominator)
vs_defense as (
    select receiver_player_id as receiver_gsis_id, season, defteam, count(*) as targets
    from tgt
    group by 1, 2, 3
),

on_field_plays as (
    select t.receiver_player_id as receiver_gsis_id, x.gsis_id as defender_gsis_id, t.season, t.defteam,
           t.posteam, t.game_id, t.is_complete, t.receiving_yards, t.is_td
    from tgt as t
    cross join lateral (select distinct g as gsis_id from unnest(string_to_array(t.defense_players, ';')) as u(g) where g <> '') as x
    join cbs on cbs.season = t.season and cbs.gsis_id = x.gsis_id
    join receivers as r on r.gsis_id = t.receiver_player_id
),

on_field_den as (   -- his targets against every defense the corner was on the field for (a traded corner: both)
    select k.receiver_gsis_id, k.defender_gsis_id, k.season, sum(v.targets) as targets_vs_defense
    from (select distinct receiver_gsis_id, defender_gsis_id, season, defteam from on_field_plays) as k
    join vs_defense as v using (receiver_gsis_id, season, defteam)
    group by 1, 2, 3
),

on_field as (
    select t.receiver_gsis_id, t.defender_gsis_id, t.season,
           max(t.posteam) as receiver_team, max(t.defteam) as defense,
           count(distinct t.game_id)                                   as games,
           count(*)                                                    as targets,
           count(*) filter (where t.is_complete)                       as receptions,
           coalesce(sum(t.receiving_yards) filter (where t.is_complete), 0) as receiving_yards,   -- no catch = 0 yards
           count(*) filter (where t.is_td)                             as receiving_tds,
           null::numeric                                               as defender_snap_share,
           max(d.targets_vs_defense)                                   as targets_vs_defense
    from on_field_plays as t
    join on_field_den as d using (receiver_gsis_id, defender_gsis_id, season)
    group by 1, 2, 3
),

-- game level (seasons without participation): the corners who played, and his line in that game
def_snaps as (
    select m.gsis_id, s.game_id, s.season, s.team, s.defense_snaps,
           s.defense_snaps::numeric / nullif(max(s.defense_snaps) over (partition by s.game_id, s.team), 0) as snap_share
    from {{ ref('stg_nflverse__snap_counts') }} as s
    join {{ ref('int_pfr_gsis_map') }} as m on m.pfr_id = s.pfr_player_id
    where s.season >= 2022 and s.season not in (select season from part_seasons) and s.game_type = 'REG'
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
    where pg.season_type = 'REG' and pg.played and pg.season >= 2022
    group by 1, 2, 3
)

select b.receiver_gsis_id, rp.player_name as receiver_name, b.defender_gsis_id, dp.player_name as defender_name,
       b.season, b.evidence, b.receiver_team, b.defense, b.games,
       b.targets::int as targets, b.receptions::int as receptions, b.receiving_yards::int as receiving_yards,
       b.receiving_tds::int as receiving_tds, b.defender_snap_share,
       b.targets_vs_defense::int as targets_vs_defense,
       round(b.targets::numeric / nullif(b.targets_vs_defense, 0), 3) as share_of_targets
from (
    select *, 'on_field' as evidence from on_field
    union all
    select *, 'same_game' from same_game
) as b
left join {{ ref('dim_player') }} as rp on rp.gsis_id = b.receiver_gsis_id
left join {{ ref('dim_player') }} as dp on dp.gsis_id = b.defender_gsis_id
