{{ config(
    materialized='view',
    pre_hook=[
        "create table if not exists ops.waiver_moves (run_at timestamptz, as_of timestamptz, model_version text, league_id text, season integer, week integer, roster_id integer, horizon_weeks integer, horizon_last_week integer, list_kind text, move_rank integer, add_rank integer, is_best_drop boolean, add_sleeper_id text, add_gsis_id text, add_name text, add_position text, add_value double precision, add_value_source text, add_reason text, add_report_status text, add_games_played integer, is_no_evidence boolean, drop_sleeper_id text, drop_gsis_id text, drop_name text, drop_position text, drop_value double precision, drop_ros_points double precision, add_ros_points double precision, rest_of_season_weeks integer, drop_horizon_loss double precision, drop_is_starter boolean, weekly_gain double precision, horizon_gain double precision, week_gains double precision[], add_horizon_gain double precision, lineup_before double precision, lineup_after double precision, add_slot text, add_slot_type text, fills_empty_slot boolean, displaced_sleeper_id text, displaced_gsis_id text, displaced_name text, displaced_position text, displaced_value double precision, displaced_slot text, open_roster_spots integer, inputs_fingerprint text)"
    ]
) }}
-- Waiver engine (plan B3): per league x season x decision week x roster, every add/drop pair that
-- improves the roster's best lineup this week (`list_kind = 'start_now'`) or over the 4-week horizon
-- only (`'cover'`: a bye or injury cover), ranked (`move_rank`; `is_best_drop` + `add_rank` = the best
-- drop per free agent), or one `'nothing'` row when no legal move gains ("nothing beats what you have").
-- Written by `league-lab waivers` and at the end of `league-lab project` (src/league_lab/waivers.py):
-- the B1 lineup solver re-run on the roster after the move minus before, on the players and values
-- `ops.lineups` holds (projection v2 in this league's scoring; K at season PPG; locks kept).
-- `lineup_value` is the decision week's lineup value as mart_lineup_recommendation publishes it, so
-- `lineup_before` must equal it (tested) while `on_current_lineup` (the moves were solved on the
-- lineups published now: same `as_of`; a `league-lab lineups` run since makes it false). `inputs_current` = the league's rosters and free-agent
-- statuses are unchanged since the moves were computed (same fingerprint expression as waivers.py):
-- a claim made since then may have taken the add, so the page says so and the legality test skips
-- those rows. Names from dim_player (by gsis_id), else Sleeper's; the add's NFL team from availability.
with m as (
    select * from {{ source('ops', 'waiver_moves') }}
),

lineup as (
    select distinct league_id, season, week, roster_id, lineup_value, as_of as lineup_as_of
    from {{ ref('mart_lineup_recommendation') }}
),

-- keep identical to waivers.FINGERPRINT_SQL (tests/test_waivers.py)
fp as (
select a.league_id, md5(a.fp || '|' || coalesce(r.fp, '')) as fp
from (select league_id, string_agg(sleeper_id || ':' || coalesce(rostered_by_roster_id::text, '') || ':'
                                   || coalesce(roster_status, '') || ':' || coalesce(injury_status, ''), ','
                                   order by sleeper_id, gsis_id) as fp
      from {{ ref('mart_player_availability') }} group by league_id) as a
left join (select league_id, string_agg(roster_id::text || ':' || sleeper_player_id || ':' || coalesce(is_on_ir::text, '')
                                        || ':' || coalesce(is_on_taxi::text, ''), ','
                                        order by roster_id, sleeper_player_id) as fp
           from {{ ref('mart_league_roster_membership') }} group by league_id) as r using (league_id)
)

select
    m.league_id,
    m.season,
    m.week,
    m.roster_id,
    mem.team_name,
    mem.manager_name,
    m.list_kind,
    m.move_rank,
    m.add_rank,
    m.is_best_drop,
    m.add_sleeper_id,
    m.add_gsis_id,
    coalesce(pa.player_name, m.add_name)            as add_name,
    m.add_position,
    av.nfl_team                                     as add_team,
    m.add_value,
    m.add_value_source,
    m.add_reason,
    m.add_report_status,
    m.add_games_played,
    m.is_no_evidence,
    m.drop_sleeper_id,
    m.drop_gsis_id,
    coalesce(pd.player_name, m.drop_name)           as drop_name,
    m.drop_position,
    m.drop_value,
    m.drop_is_starter,
    m.drop_horizon_loss,
    m.drop_ros_points,
    m.add_ros_points,
    m.rest_of_season_weeks,
    m.weekly_gain,
    m.horizon_gain,
    m.week_gains,
    m.add_horizon_gain,
    m.lineup_before,
    m.lineup_after,
    l.lineup_value,
    m.add_slot,
    m.add_slot_type,
    m.fills_empty_slot,
    m.displaced_sleeper_id,
    m.displaced_gsis_id,
    coalesce(px.player_name, m.displaced_name)      as displaced_name,
    m.displaced_position,
    m.displaced_value,
    m.displaced_slot,
    m.open_roster_spots,
    m.horizon_weeks,
    m.horizon_last_week,
    coalesce(m.as_of = l.lineup_as_of, false)       as on_current_lineup,
    coalesce(fp.fp = m.inputs_fingerprint, false)   as inputs_current,
    m.model_version,
    m.as_of,
    m.run_at
from m
left join lineup as l using (league_id, season, week, roster_id)
left join {{ ref('dim_league_member') }} as mem using (league_id, roster_id)
left join {{ ref('dim_player') }} as pa on pa.gsis_id = m.add_gsis_id
left join {{ ref('dim_player') }} as pd on pd.gsis_id = m.drop_gsis_id
left join {{ ref('dim_player') }} as px on px.gsis_id = m.displaced_gsis_id
left join {{ ref('mart_player_availability') }} as av on av.league_id = m.league_id and av.sleeper_id = m.add_sleeper_id
left join fp on fp.league_id = m.league_id
