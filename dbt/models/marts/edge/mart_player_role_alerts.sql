{{ config(
    materialized='view',
    pre_hook=[
        "create table if not exists ops.player_role_alerts ( season integer, week integer, game_id text, gsis_id text, player_name text, position text, team text, direction text, games_held integer, since_week integer, confidence text, primary_metric text, metrics_changed text[], z double precision, snap_from double precision, snap_to double precision, route_from double precision, route_to double precision, target_from double precision, target_to double precision, carry_from double precision, carry_to double precision, trigger_kind text, trigger_gsis_id text, trigger_name text, trigger_status text, trigger_text text, change_text text, prior_games integer, kind text, cause_text text, expires_after_week integer, expiry_rule text, signals_version text, run_at timestamptz)"
    ]
) }}
-- Role alerts (plan R-10): per player x week, a step change in his role over the last one to three games
-- (snap share, route share, target share, carry share vs the games before) with a stated cause: `kind`
-- (role_up / role_down / absence_beneficiary / depth_move / new_team), `cause_text` (a teammate out or back,
-- a benching or depth-chart move, a trade — or "the coaches changed his role"), the evidence (`*_from` /
-- `*_to`, `change_text`), the confidence (`games_held`: one to three games) and the expiry
-- (`expires_after_week`, `expiry_rule`). Written by `league-lab project` / `league-lab signals`
-- (src/league_lab/signals.py, every season; the rule is in that module's docstring and docs/METRICS.md
-- § Role alerts). Added here:
--   is_latest      the alert game is his team's latest played game this season: still news
--   trigger_ended  an absence alert whose injured teammate is active with no injury designation today
--                  (the latest report): the reason is going away, so is the bigger role
--   is_live        is_latest and not trigger_ended: what the pages show as this week's alerts
-- A view on ops (no rebuild needed after `project`); it reads only analytics relations besides ops.
with a as (
    select * from {{ source('ops', 'player_role_alerts') }}
),

last_game as (
    select season, team, max(week) as team_last_week
    from {{ ref('fct_team_game') }}
    where season_type = 'REG'
    group by 1, 2
),

status_now as (
    select distinct on (gsis_id) gsis_id, roster_status, injury_status
    from {{ ref('mart_player_availability') }}
    where gsis_id is not null
    order by gsis_id, league_id
),

flags as (
    select
        a.*,
        lg.team_last_week,
        coalesce(a.week = lg.team_last_week, false) as is_latest,
        coalesce(a.kind = 'absence_beneficiary' and a.trigger_status = 'out_injured'
                 and t.roster_status = 'ACT' and t.injury_status is null, false) as trigger_ended,
        t.injury_status as trigger_injury_now
    from a
    left join last_game as lg on lg.season = a.season and lg.team = a.team
    left join status_now as t on t.gsis_id = a.trigger_gsis_id
)

select
    season, week, game_id, gsis_id, player_name, position, team, direction,
    case direction when 'up' then 'bigger role' else 'smaller role' end as direction_label,
    kind, cause_text, games_held, since_week, confidence, primary_metric, metrics_changed, z,
    snap_from, snap_to, route_from, route_to, target_from, target_to, carry_from, carry_to,
    trigger_kind, trigger_gsis_id, trigger_name, trigger_status, trigger_text, change_text, prior_games,
    expires_after_week, expiry_rule, team_last_week, is_latest, trigger_ended, trigger_injury_now,
    is_latest and not trigger_ended as is_live,
    signals_version, run_at
from flags
