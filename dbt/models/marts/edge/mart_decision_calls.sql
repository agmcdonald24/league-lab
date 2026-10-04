{{ config(
    materialized='table',
    indexes=[{'columns': ['league_id', 'season', 'week']}],
    pre_hook="create table if not exists ops.lineup_record (run_at timestamptz, as_of timestamptz, first_kickoff_at timestamptz, record_source text, model_version text, pricing text, league_id text, season integer, week integer, roster_id integer, role text, slot text, slot_type text, slot_order integer, bench_rank integer, sleeper_player_id text, gsis_id text, player_name text, position text, value double precision, value_source text, margin double precision, report_status text, reason text, lineup_value double precision, call_rank integer, alt_sleeper_player_id text, alt_gsis_id text, alt_player_name text, alt_value double precision, p_win double precision, is_coin_flip boolean)"
) }}
-- V-1 (Wave I-G): the decision cards' closest calls as recorded before kickoff (ops.lineup_record rows with a
-- call_rank: the starter, the bench player who would come in, P(starter outscores him) and the card's coin-flip
-- rule), graded by what happened: outcome 1 = the starter outscored him, 0.5 = equal, 0 = not; NULL until Sleeper
-- has scored the week. Points as in mart_decision_record (Sleeper's count; else fct_player_game_league; no stat row
-- = 0; a K / DEF with no number = unknown -> no outcome). Python twin: league_lab.validation.grade_calls; the
-- calibration table and the coin-flip line: validation.calibration (docs/METRICS.md § "The decision record").
with calls as (
    select * from {{ source('ops_decisions', 'lineup_record') }}
    where role = 'starter' and call_rank is not null and league_id not like 'mfl:%'   -- V-2: MFL graded on request
),

weekly as (
    select league_id, season, week, sleeper_player_id, points_observed, is_scored_week
    from {{ ref('league_player_week') }}
),

scored as (
    select league_id, season, week from weekly group by 1, 2, 3 having bool_and(coalesce(is_scored_week, false))
),

obs as (
    select league_id, season, week, sleeper_player_id, max(points_observed) as points
    from weekly where points_observed is not null group by 1, 2, 3, 4
),

fb as (
    select league_id, season, week, gsis_id, sum(points) as points
    from {{ ref('fct_player_game_league') }} where season_type = 'REG' group by 1, 2, 3, 4
),

pts as (
    select
        c.league_id, c.season, c.week, c.roster_id, c.record_source, c.call_rank, c.slot,
        c.sleeper_player_id, c.player_name, c.value, c.margin,
        c.alt_sleeper_player_id, c.alt_player_name, c.alt_value, c.p_win, c.is_coin_flip,
        s.week is not null as is_scored,
        case when oa.points is not null then oa.points when c.gsis_id is not null then coalesce(fa.points, 0) end as a_points,
        case when ob.points is not null then ob.points when c.alt_gsis_id is not null then coalesce(fb2.points, 0) end as b_points
    from calls as c
    left join scored as s using (league_id, season, week)
    left join obs as oa on oa.league_id = c.league_id and oa.season = c.season and oa.week = c.week
                       and oa.sleeper_player_id = c.sleeper_player_id
    left join fb as fa on fa.league_id = c.league_id and fa.season = c.season and fa.week = c.week and fa.gsis_id = c.gsis_id
    left join obs as ob on ob.league_id = c.league_id and ob.season = c.season and ob.week = c.week
                       and ob.sleeper_player_id = c.alt_sleeper_player_id
    left join fb as fb2 on fb2.league_id = c.league_id and fb2.season = c.season and fb2.week = c.week
                       and fb2.gsis_id = c.alt_gsis_id
)

select
    league_id, season, week, roster_id, record_source, call_rank, slot, sleeper_player_id, player_name, value, margin,
    alt_sleeper_player_id, alt_player_name, alt_value, p_win, is_coin_flip,
    case when is_scored then 'scored' else 'in_play' end as status,
    case when is_scored then a_points end as starter_points,
    case when is_scored then b_points end as alt_points,
    case
        when not is_scored or a_points is null or b_points is null then null
        when a_points > b_points then 1.0
        when b_points > a_points then 0.0
        else 0.5
    end as outcome
from pts
