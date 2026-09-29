{{ config(
    materialized='view',
    pre_hook=[
        "create table if not exists ops.lineups (run_at timestamptz, model_version text, league_id text, season integer, week integer, roster_id integer, is_realised boolean, role text, slot text, slot_type text, slot_order integer, bench_rank integer, sleeper_player_id text, gsis_id text, player_name text, position text, value double precision, value_source text, margin double precision, is_locked boolean, report_status text, reason text)",
        "create table if not exists ops.lineup_totals (run_at timestamptz, as_of timestamptz, model_version text, league_id text, season integer, week integer, roster_id integer, is_realised boolean, lineup_value double precision, bench_value double precision, slots_total integer, slots_filled integer, empty_slots text, weakest_slot text, weakest_margin double precision, weakest_sleeper_player_id text, n_players integer, n_bench integer, n_unplayable integer, n_locked integer, n_questionable integer, n_ppg_valued integer, inputs_fingerprint text)"
    ]
) }}
-- Exact lineup service (plan B1): per league x season x week x roster, the PROPOSED starting lineup
-- one row per starting slot (filled or empty), from `ops.lineups` / `ops.lineup_totals` (written by
-- `league-lab lineups` and at the end of `league-lab project`; src/league_lab/lineup.py). The lineup is
-- a maximum-weight matching of the roster to the league's slots at projection v2 `proj_points` (K at the
-- league's season PPG, DEF at the PPG Sleeper observed: `value_source`); `lineup_margin` = the lineup
-- total minus the best total without that player (re-solved), so the smallest margin is the decision
-- that matters (`weakest_slot`); a locked player (his game has kicked off) has no margin. For weeks
-- Sleeper has scored, `realised_optimal` is the best lineup the same roster could have started at the
-- points Sleeper counted (hindsight). Names from dim_player (by gsis_id), else Sleeper's name.
with l as (
    select * from {{ source('ops', 'lineups') }}
    where not is_realised and role in ('starter', 'empty')
),

t as (
    select * from {{ source('ops', 'lineup_totals') }} where not is_realised
),

realised as (
    select league_id, season, week, roster_id, lineup_value as realised_optimal
    from {{ source('ops', 'lineup_totals') }} where is_realised
)

select
    l.league_id,
    l.season,
    l.week,
    l.roster_id,
    m.team_name,
    m.manager_name,
    l.slot,
    l.slot_type,
    l.slot_order,
    l.sleeper_player_id,
    l.gsis_id,
    coalesce(p.player_name, l.player_name)                  as player_name,
    l.position,
    l.value                                                 as player_value,
    l.value_source,
    l.margin                                                as lineup_margin,
    coalesce(l.slot = t.weakest_slot, false)                as is_weakest_slot,
    l.role = 'empty'                                        as is_empty_slot,
    l.is_locked,
    l.report_status,
    coalesce(l.report_status = 'Questionable', false)       as is_questionable,
    t.lineup_value,
    t.bench_value,
    t.weakest_slot,
    t.weakest_margin,
    t.empty_slots,
    r.realised_optimal,
    t.model_version,
    t.as_of,
    t.run_at
from l
join t using (league_id, season, week, roster_id)
left join realised as r using (league_id, season, week, roster_id)
left join {{ ref('dim_league_member') }} as m using (league_id, roster_id)
left join {{ ref('dim_player') }} as p on p.gsis_id = l.gsis_id
