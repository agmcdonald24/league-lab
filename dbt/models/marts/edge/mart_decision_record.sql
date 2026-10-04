{{ config(
    materialized='table',
    indexes=[{'columns': ['league_id', 'season', 'week', 'roster_id']}],
    pre_hook=[
        "create table if not exists ops.lineup_record (run_at timestamptz, as_of timestamptz, first_kickoff_at timestamptz, record_source text, model_version text, pricing text, league_id text, season integer, week integer, roster_id integer, role text, slot text, slot_type text, slot_order integer, bench_rank integer, sleeper_player_id text, gsis_id text, player_name text, position text, value double precision, value_source text, margin double precision, report_status text, reason text, lineup_value double precision, call_rank integer, alt_sleeper_player_id text, alt_gsis_id text, alt_player_name text, alt_value double precision, p_win double precision, is_coin_flip boolean)",
        "create table if not exists ops.lineup_totals (run_at timestamptz, as_of timestamptz, model_version text, league_id text, season integer, week integer, roster_id integer, is_realised boolean, lineup_value double precision, bench_value double precision, slots_total integer, slots_filled integer, empty_slots text, weakest_slot text, weakest_margin double precision, weakest_sleeper_player_id text, n_players integer, n_bench integer, n_unplayable integer, n_locked integer, n_questionable integer, n_ppg_valued integer, inputs_fingerprint text, n_unvalued integer)"
    ]
) }}
-- V-1 (Wave I-G), the decision record graded: per league x season x week x roster, the app's lineup as recorded
-- before the week's first kickoff (ops.lineup_record, src/league_lab/lineup.py V-1 block; record_source 'kickoff',
-- or 'reconstructed' for a week played before the record existed) against the lineup the manager submitted
-- (league_player_week.is_starter, Sleeper's points) and the hindsight optimum (ops.lineup_totals is_realised).
-- The Python twin is league_lab.validation.grade_roster_weeks (api/tests/test_v1.py holds them equal); definitions:
-- docs/METRICS.md § "The decision record".
--
-- * submitted_points = Sleeper's starters' points; app_points = the record's starters at the points they scored that
--   week (Sleeper's count in the league; a starter on no roster that week: fct_player_game_league in the league's
--   scoring; no stat row = did not play = 0; a K / DEF with no number = unknown -> app_points NULL, n_app_unknown);
-- * regret = optimum - submitted; app_edge = app - submitted (what following the record would have added);
--   app_regret = optimum - app;
-- * is_news_affected: a starter of a 'kickoff' record whose week's final injury report (mart_player_week_features)
--   differs from the one the build saw, or who went to NFL injured reserve (a reconstructed week read the final
--   report: never flagged);
-- * status 'scored' once Sleeper has scored the week (every league_player_week row is_scored_week); before that
--   'in_play' and every point column is NULL (nothing after the outcome enters before it is final).
with rec as (
    select * from {{ source('ops_decisions', 'lineup_record') }} where role = 'starter'
),

weekly as (
    select league_id, season, week, roster_id, sleeper_player_id, is_starter, points_observed, is_scored_week
    from {{ ref('league_player_week') }}
),

scored as (
    select league_id, season, week
    from weekly
    group by 1, 2, 3
    having bool_and(coalesce(is_scored_week, false))
),

submitted as (
    select league_id, season, week, roster_id,
           sum(case when is_starter then coalesce(points_observed, 0) else 0 end) as submitted_points,
           array_agg(sleeper_player_id) filter (where is_starter) as starter_ids
    from weekly
    group by 1, 2, 3, 4
),

obs as (
    select league_id, season, week, sleeper_player_id, max(points_observed) as points
    from weekly
    where points_observed is not null
    group by 1, 2, 3, 4
),

fb as (
    select league_id, season, week, gsis_id, sum(points) as points
    from {{ ref('fct_player_game_league') }}
    where season_type = 'REG'
    group by 1, 2, 3, 4
),

final_status as (
    select season, week, gsis_id, max(report_status) as report_status, max(roster_status) as roster_status
    from {{ ref('mart_player_week_features') }}
    group by 1, 2, 3
),

starters as (
    select
        r.league_id, r.season, r.week, r.roster_id, r.record_source, r.model_version, r.pricing, r.sleeper_player_id,
        case
            when o.points is not null then o.points
            when r.gsis_id is not null then coalesce(fb.points, 0)
        end as points,
        (r.record_source = 'kickoff' and r.gsis_id is not null and f.gsis_id is not null
         and (r.report_status is distinct from f.report_status or f.roster_status = 'RES')) as is_news_starter
    from rec as r
    left join obs as o using (league_id, season, week, sleeper_player_id)
    left join fb on fb.league_id = r.league_id and fb.season = r.season and fb.week = r.week and fb.gsis_id = r.gsis_id
    left join final_status as f on f.season = r.season and f.week = r.week and f.gsis_id = r.gsis_id
),

per_roster as (
    select
        league_id, season, week, roster_id,
        min(record_source) as record_source,
        min(model_version) as model_version,
        min(pricing) as pricing,
        count(*) as n_starters,
        count(*) filter (where points is null) as n_unknown,
        sum(points) as app_raw,
        count(*) filter (where is_news_starter) as n_news_starters,
        array_agg(sleeper_player_id) as record_ids
    from starters
    group by 1, 2, 3, 4
),

opt as (
    select league_id, season, week, roster_id, lineup_value as optimum_points
    from {{ source('ops', 'lineup_totals') }}
    where is_realised
),

graded as (
    select
        p.league_id, p.season, p.week, p.roster_id, p.record_source, p.model_version, p.pricing,
        case when s.week is not null then 'scored' else 'in_play' end as status,
        case when s.week is not null then round(sub.submitted_points::numeric, 2) end as submitted_points,
        case when s.week is not null and p.n_unknown = 0 then round(p.app_raw::numeric, 2) end as app_points,
        case when s.week is not null then round(o.optimum_points::numeric, 2) end as optimum_points,
        p.n_starters,
        case when sub.roster_id is not null then
            (select count(*) from unnest(p.record_ids) as x(id) where not (x.id = any(coalesce(sub.starter_ids, '{}'))))
        end as n_changed,
        case when s.week is not null then p.n_unknown end as n_app_unknown,
        p.n_news_starters,
        p.n_news_starters > 0 as is_news_affected
    from per_roster as p
    left join scored as s using (league_id, season, week)
    left join submitted as sub using (league_id, season, week, roster_id)
    left join opt as o using (league_id, season, week, roster_id)
)

select
    g.league_id, g.season, g.week, g.roster_id, m.team_name, g.record_source, g.model_version,
    coalesce(g.pricing, 'flat') as pricing, g.status,
    g.submitted_points, g.app_points, g.optimum_points,
    g.optimum_points - g.submitted_points as regret,
    g.app_points - g.submitted_points as app_edge,
    g.optimum_points - g.app_points as app_regret,
    g.n_starters, g.n_changed, g.n_app_unknown, g.n_news_starters, g.is_news_affected
from graded as g
left join {{ ref('dim_league_member') }} as m on m.league_id = g.league_id and m.roster_id = g.roster_id
