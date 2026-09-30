-- depends_on: {{ ref('scoring_stat_map') }}
{{ config(
    indexes=[{'columns': ['league_id', 'season', 'week', 'position']}, {'columns': ['gsis_id', 'season', 'week']}],
    pre_hook="create table if not exists ops.projections (model_version text, fitted_at timestamptz, train_seasons text, league_id text, season integer, week integer, gsis_id text, position text, proj_targets double precision, proj_receptions double precision, proj_receiving_yards double precision, proj_receiving_tds double precision, proj_carries double precision, proj_rushing_yards double precision, proj_rushing_tds double precision, proj_attempts double precision, proj_passing_yards double precision, proj_passing_tds double precision, proj_passing_interceptions double precision, proj_fumbles_lost_total double precision, proj_points double precision, p10 double precision, p50 double precision, p90 double precision, frozen_at timestamptz, frozen_source text); alter table ops.projections add column if not exists frozen_at timestamptz; alter table ops.projections add column if not exists frozen_source text"
) }}
-- Projection v2 (plan M-01/M-03) per league x season x week x player: the projected stat line,
-- the points it is worth under THAT league's scoring, and the P10 / P50 / P90 of the league's
-- points (conformally calibrated: ~80% of outcomes land inside), next to the as-of context and
-- the outcome for played weeks. Written by `league-lab project`; empty until it has run.
-- Ranking rule: by proj_points (the priced line) among rankable players (Out / Doubtful / IR excluded,
-- like the baseline); the interval belongs to that projection.
with p as (
    select * from {{ source('ops', 'projections') }}
),

f as (
    select gsis_id, season, week, game_id, team, opponent, position, player_name, is_home, implied_team_total, spread_line,
           games_to_date, report_status, practice_status, roster_status, no_history,
           report_status is distinct from 'Out' and report_status is distinct from 'Doubtful' and roster_status <> 'RES' as is_rankable,
           ppg_std, ppg_l3, xppg_l5, prev_ppg, opp_rank_std, snap_pct_l3, target_share_l3, carry_share_l3, first_read_share_l3,
           points_actual, played,
           {%- for c in component_stats() if c not in ('red_zone_targets', 'red_zone_carries') %}
           out_{{ c }}{{ "," if not loop.last }}
           {%- endfor %}
    from {{ ref('mart_player_week_features') }}
),

l as (
    select league_id, league_name, scoring_settings, is_reference_league from {{ ref('dim_league_season') }}
),

-- the outcome priced under the league's own scoring with the same macro every mart uses (stat
-- keys, yardage bonuses; long-TD counts are not carried here and price as 0), so "actual" on a
-- dynasty board is dynasty points, not the reference league's
outcome_line as (
    select gsis_id, season, week, played,
           {%- set have = [] -%}
           {%- for c in component_stats() if c not in ('red_zone_targets', 'red_zone_carries') %}
           {%- do have.append(c) %}
           coalesce(out_{{ c }}, 0) as {{ c }},
           {%- endfor %}
           {{ zero_stat_columns(have) }}
    from f
),

priced as (
    select p.league_id, o.gsis_id, o.season, o.week,
           case when o.played then {{ league_points('l.scoring_settings', 'o') }} end as points_actual_league
    from p
    join outcome_line as o using (gsis_id, season, week)
    join l on l.league_id = p.league_id
),

-- Plan R-13: kickers and team defenses (model kd1.0, `league_lab.kdef`) for the leagues that start
-- them, appended below with the same columns. Context and outcome come from mart_kd_week; the
-- skill-position stat line, usage and PPG columns are NULL (not 0: they do not apply). A DEF row
-- has gsis_id NULL: the unit is the team (`team`); ops.projections keys it by the Sleeper id ('KC').
kd as (
    select u.*,
           count(*) filter (where u.played) over (partition by u.position, u.unit_id, u.season order by u.week
                                                   rows between unbounded preceding and 1 preceding) as games_to_date
    from {{ ref('mart_kd_week') }} as u
),

-- the kicker's outcome as a weekly-stats row (the columns the scoring map prices) and the defense's
-- outcome columns, so each league prices it with its own map: league_points() for K, def_points() for DEF
kd_line as (
    select position, unit_id, season, week, played,
           coalesce(out_fg_made_0_19, 0) as fg_made_0_19, coalesce(out_fg_made_20_29, 0) as fg_made_20_29,
           coalesce(out_fg_made_30_39, 0) as fg_made_30_39, coalesce(out_fg_made_40_49, 0) as fg_made_40_49,
           coalesce(out_fg_made_50p, 0) as fg_made_50_59, coalesce(out_fg_missed, 0) as fg_missed,
           coalesce(out_fg_missed_0_19, 0) as fg_missed_0_19, coalesce(out_fg_missed_20_29, 0) as fg_missed_20_29,
           coalesce(out_fg_missed_30_39, 0) as fg_missed_30_39, coalesce(out_fg_missed_40_49, 0) as fg_missed_40_49,
           coalesce(out_fg_missed_50p, 0) as fg_missed_50_59, coalesce(out_pat_made, 0) as pat_made,
           coalesce(out_pat_missed, 0) as pat_missed,
           {{ zero_stat_columns(['fg_made_0_19', 'fg_made_20_29', 'fg_made_30_39', 'fg_made_40_49', 'fg_made_50_59', 'fg_missed',
                                 'fg_missed_0_19', 'fg_missed_20_29', 'fg_missed_30_39', 'fg_missed_40_49', 'fg_missed_50_59',
                                 'pat_made', 'pat_missed']) }},
           out_sacks, out_interceptions, out_fumble_recoveries, out_forced_fumbles, out_def_tds, out_st_tds,
           out_safeties, out_blocked_kicks, out_points_allowed
    from kd
),

kd_priced as (
    select p.league_id, p.position, p.gsis_id as unit_id, p.season, p.week,
           case when k.played then
               case when p.position = 'K' then {{ league_points('l.scoring_settings', 'k') }}
                    else {{ def_points('l.scoring_settings', 'k', 'out_') }} end
           end as points_actual_league
    from p
    join kd_line as k on k.position = p.position and k.unit_id = p.gsis_id and k.season = p.season and k.week = p.week
    join l on l.league_id = p.league_id
    where p.position in ('K', 'DEF')
),

kd_rows as (
    select p.*, u.player_name, u.team, u.opponent, u.game_id, u.is_home, u.implied_team_total, u.spread_line, u.games_to_date,
           u.report_status, u.roster_status, u.played,
           u.report_status is distinct from 'Out' and u.report_status is distinct from 'Doubtful'
               and u.roster_status is distinct from 'RES'                                            as is_rankable,
           pr.points_actual_league
    from p
    join kd as u on u.position = p.position and u.unit_id = p.gsis_id and u.season = p.season and u.week = p.week
    left join kd_priced as pr on pr.league_id = p.league_id and pr.position = p.position and pr.unit_id = p.gsis_id
                             and pr.season = p.season and pr.week = p.week
    where p.position in ('K', 'DEF')
)

select
    p.league_id, l.league_name, l.is_reference_league,
    p.season, p.week, p.gsis_id, p.position, f.player_name, f.team, f.opponent, f.game_id, f.is_home,
    f.implied_team_total, f.spread_line, f.games_to_date, f.report_status, f.practice_status, f.roster_status, f.no_history, f.is_rankable,
    round(p.proj_points::numeric, 2) as proj_points,
    round(p.p10::numeric, 2) as p10, round(p.p50::numeric, 2) as p50, round(p.p90::numeric, 2) as p90,
    round((p.p90 - p.p10)::numeric, 2) as interval_width,
    round(p.proj_targets::numeric, 1) as proj_targets, round(p.proj_receptions::numeric, 1) as proj_receptions,
    round(p.proj_receiving_yards::numeric, 1) as proj_receiving_yards, round(p.proj_receiving_tds::numeric, 2) as proj_receiving_tds,
    round(p.proj_carries::numeric, 1) as proj_carries, round(p.proj_rushing_yards::numeric, 1) as proj_rushing_yards,
    round(p.proj_rushing_tds::numeric, 2) as proj_rushing_tds, round(p.proj_attempts::numeric, 1) as proj_attempts,
    round(p.proj_passing_yards::numeric, 1) as proj_passing_yards, round(p.proj_passing_tds::numeric, 2) as proj_passing_tds,
    round(p.proj_passing_interceptions::numeric, 2) as proj_passing_interceptions, round(p.proj_fumbles_lost_total::numeric, 2) as proj_fumbles_lost,
    -- as-of context shown next to the projection (reference-league scoring for the PPG columns)
    f.ppg_std, f.ppg_l3, f.xppg_l5, f.prev_ppg, f.opp_rank_std, f.snap_pct_l3, f.target_share_l3, f.carry_share_l3, f.first_read_share_l3,
    -- outcome
    f.played, round(pr.points_actual_league::numeric, 2) as points_actual,
    f.out_targets, f.out_receptions, f.out_receiving_yards, f.out_receiving_tds, f.out_carries, f.out_rushing_yards, f.out_rushing_tds,
    f.out_attempts, f.out_passing_yards, f.out_passing_tds, f.out_passing_interceptions,
    case when f.played then (pr.points_actual_league between p.p10 and p.p90) end as actual_inside_interval,
    rank() over (partition by p.league_id, p.season, p.week, p.position order by case when f.is_rankable then p.proj_points end desc nulls last, p.gsis_id) as rank_pos,
    case when f.played then rank() over (partition by p.league_id, p.season, p.week, p.position order by case when f.played then pr.points_actual_league end desc nulls last, p.gsis_id) end as actual_rank_pos,
    p.model_version, p.train_seasons, p.fitted_at,
    -- B5 decision record: NULL = live board (rewritten by every refit until the week's first kickoff);
    -- 'kickoff' = the board as published before the week's first kickoff (frozen_at = when), kept since;
    -- 'refit' = the week was already under way when its rows were locked (2026 weeks 1-3): not a kickoff record
    p.frozen_source, p.frozen_at
from p
join f using (gsis_id, season, week)
join l on l.league_id = p.league_id
left join priced as pr on pr.league_id = p.league_id and pr.gsis_id = p.gsis_id and pr.season = p.season and pr.week = p.week

union all

select
    k.league_id, l.league_name, l.is_reference_league,
    k.season, k.week, case when k.position = 'K' then k.gsis_id end as gsis_id, k.position, k.player_name, k.team, k.opponent,
    k.game_id, k.is_home, k.implied_team_total::numeric, k.spread_line::double precision, k.games_to_date::bigint, k.report_status,
    null::text as practice_status, k.roster_status, false as no_history, k.is_rankable,
    round(k.proj_points::numeric, 2) as proj_points,
    round(k.p10::numeric, 2) as p10, round(k.p50::numeric, 2) as p50, round(k.p90::numeric, 2) as p90,
    round((k.p90 - k.p10)::numeric, 2) as interval_width,
    null::numeric as proj_targets, null::numeric as proj_receptions, null::numeric as proj_receiving_yards, null::numeric as proj_receiving_tds,
    null::numeric as proj_carries, null::numeric as proj_rushing_yards, null::numeric as proj_rushing_tds, null::numeric as proj_attempts,
    null::numeric as proj_passing_yards, null::numeric as proj_passing_tds, null::numeric as proj_passing_interceptions,
    null::numeric as proj_fumbles_lost,
    null::numeric as ppg_std, null::numeric as ppg_l3, null::numeric as xppg_l5, null::numeric as prev_ppg, null::bigint as opp_rank_std,
    null::numeric as snap_pct_l3, null::numeric as target_share_l3, null::numeric as carry_share_l3, null::numeric as first_read_share_l3,
    k.played, round(k.points_actual_league::numeric, 2) as points_actual,
    null::integer as out_targets, null::integer as out_receptions, null::integer as out_receiving_yards, null::integer as out_receiving_tds,
    null::integer as out_carries, null::integer as out_rushing_yards, null::integer as out_rushing_tds, null::integer as out_attempts,
    null::integer as out_passing_yards, null::integer as out_passing_tds, null::integer as out_passing_interceptions,
    case when k.played then (k.points_actual_league between k.p10 and k.p90) end as actual_inside_interval,
    rank() over (partition by k.league_id, k.season, k.week, k.position order by case when k.is_rankable then k.proj_points end desc nulls last, k.gsis_id) as rank_pos,
    case when k.played then rank() over (partition by k.league_id, k.season, k.week, k.position order by case when k.played then k.points_actual_league end desc nulls last, k.gsis_id) end as actual_rank_pos,
    k.model_version, k.train_seasons, k.fitted_at,
    k.frozen_source, k.frozen_at
from kd_rows as k
join l on l.league_id = k.league_id
