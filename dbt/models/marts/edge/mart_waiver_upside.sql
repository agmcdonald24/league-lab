{{ config(
    materialized='view',
    pre_hook=[
        "create table if not exists ops.waiver_upside ( run_at timestamptz, as_of timestamptz, league_id text, season integer, week integer, roster_id integer, horizon_last_week integer, list_kind text, upside_rank integer, add_sleeper_id text, add_gsis_id text, add_name text, add_position text, add_team text, base_value double precision, scenario_value double precision, points_gain double precision, with_alert_value double precision, presentation text, alert_week integer, since_week integer, games_held integer, confidence text, kind text, trigger_kind text, trigger_name text, cause_text text, change_text text, expires_after_week integer, expiry_rule text, drop_sleeper_id text, drop_gsis_id text, drop_name text, drop_position text, drop_horizon_loss double precision, base_weekly_gain double precision, base_horizon_gain double precision, holds_weekly_gain double precision, holds_horizon_gain double precision, holds_week_gains double precision[], holds_slot text, open_roster_spots integer, inputs_fingerprint text)"
    ]
) }}
-- Waiver upside stashes (plan R-12, list_kind = 'upside'; the list B3 left out): per league x season x
-- decision week x roster, every free agent with a live bigger-role alert and a larger-role scenario who
-- does not help this roster at his projection today (base horizon gain <= 0: the stash case), valued like a
-- B3 move twice — at his projection (base_*_gain: what the start-now / cover lists see) and
-- "if it holds" (holds_*_gain: the scenario's projection for the weeks it covers) — with the drop that
-- costs the lineup least over the horizon (none on an open spot). Written by the waiver engine right after
-- ops.waiver_moves (src/league_lab/waivers.py § upside). `inputs_current` = the league's rosters and
-- statuses are unchanged since (the same fingerprint as mart_waiver_moves).
with u as (
    select * from {{ source('ops', 'waiver_upside') }}
),

-- keep identical to waivers.FINGERPRINT_SQL (as mart_waiver_moves does): the league's rosters and statuses now
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
    u.league_id, u.season, u.week, u.roster_id, u.horizon_last_week, u.list_kind, u.upside_rank,
    u.add_sleeper_id, u.add_gsis_id, u.add_name, u.add_position, u.add_team, u.base_value, u.scenario_value, u.points_gain,
    u.with_alert_value, u.presentation, u.alert_week, u.since_week, u.games_held, u.confidence, u.kind, u.trigger_kind,
    u.trigger_name, u.cause_text, u.change_text,
    u.expires_after_week, u.expiry_rule, u.drop_sleeper_id, u.drop_gsis_id, u.drop_name, u.drop_position, u.drop_horizon_loss,
    u.base_weekly_gain, u.base_horizon_gain, u.holds_weekly_gain, u.holds_horizon_gain, u.holds_week_gains, u.holds_slot,
    u.open_roster_spots, coalesce(fp.fp = u.inputs_fingerprint, false) as inputs_current, u.inputs_fingerprint, u.as_of, u.run_at
from u
left join fp on fp.league_id = u.league_id
