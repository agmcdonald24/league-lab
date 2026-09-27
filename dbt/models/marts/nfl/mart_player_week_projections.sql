-- depends_on: {{ ref('scoring_stat_map') }}
{{ config(
    indexes=[{'columns': ['league_id', 'season', 'week', 'position']}, {'columns': ['gsis_id', 'season', 'week']}],
    pre_hook="create table if not exists ops.projections (model_version text, fitted_at timestamptz, train_seasons text, league_id text, season integer, week integer, gsis_id text, position text, proj_targets double precision, proj_receptions double precision, proj_receiving_yards double precision, proj_receiving_tds double precision, proj_carries double precision, proj_rushing_yards double precision, proj_rushing_tds double precision, proj_attempts double precision, proj_passing_yards double precision, proj_passing_tds double precision, proj_passing_interceptions double precision, proj_fumbles_lost_total double precision, proj_points double precision, p10 double precision, p50 double precision, p90 double precision)"
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
    p.model_version, p.train_seasons, p.fitted_at
from p
join f using (gsis_id, season, week)
join l on l.league_id = p.league_id
left join priced as pr on pr.league_id = p.league_id and pr.gsis_id = p.gsis_id and pr.season = p.season and pr.week = p.week
