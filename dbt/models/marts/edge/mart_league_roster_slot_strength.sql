-- depends_on: {{ ref('mart_lineup_recommendation') }}
-- Starter strength vs depth (plan B2), this week, one row per current league x roster x slot type the
-- league starts (QB, RB, WR, TE, FLEX, SUPER_FLEX, K, DEF):
--   starter_strength = the best lineup minus the best lineup with the roster's top player at that slot
--   type removed, the whole lineup re-solved. That is exactly the B1 margin of that starter
--   (`ops.lineups.margin`: lineup value minus a fresh solve without him), so it is read, not re-solved;
--   the equality is checked by hand in docs/STATUS.md (B2) and by tests/test_roster_value.py.
--   `replacement_*` = who comes into the lineup when he is removed (see mart_league_roster_horizon).
-- A slot type whose slots are all empty, or whose top starter is locked (his game has kicked off: not a
-- decision, no margin) has a null strength. Superflex is a slot like any other: its top player is whoever
-- the solver seats there (a QB, or a RB / WR / TE worth more than the QB2).
{{ config(materialized='view') }}

with h as materialized (
    select * from {{ ref('mart_league_roster_horizon') }} where is_this_week
),

slots as (
    select league_id, season, roster_id, team_name, manager_name, week, slot_type,
           count(*)                                    as slots,
           count(*) filter (where role = 'empty')      as empty_slots,
           min(slot_order)                             as first_slot_order
    from h where role in ('starter', 'empty')
    group by 1, 2, 3, 4, 5, 6, 7
)

select
    s.league_id,
    s.season,
    s.roster_id,
    s.team_name,
    s.manager_name,
    s.week,
    s.slot_type,
    s.slots,
    s.empty_slots,
    s.first_slot_order,
    t.slot                                  as top_slot,
    t.player_name                           as top_player_name,
    t.gsis_id                               as top_gsis_id,
    t.position                              as top_position,
    t.player_value                          as top_value,
    t.is_locked                             as top_is_locked,
    t.lineup_margin                         as starter_strength,
    t.replacement_name,
    t.replacement_value
from slots as s
left join h as t
       on t.league_id = s.league_id and t.season = s.season and t.roster_id = s.roster_id
      and t.slot_type = s.slot_type and t.is_top_at_slot_type
