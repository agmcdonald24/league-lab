{{ config(
    materialized='view',
    pre_hook="create table if not exists ops.feature_experiments (run_id text, run_at timestamptz, model_version text, harness_version text, feature_group text, group_table text, group_columns text, test_seasons text, train_seasons text, data_key text, position text, league_id text, test_season integer, n_weeks integer, n_player_weeks integer, spearman double precision, hit_rate double precision, mae double precision, coverage_80 double precision, interval_width double precision, interval_score double precision, baseline_spearman double precision, baseline_hit_rate double precision, baseline_mae double precision, baseline_coverage_80 double precision, baseline_interval_width double precision, baseline_interval_score double precision, delta_spearman double precision, delta_hit_rate double precision, delta_mae double precision, delta_coverage_80 double precision, delta_interval_width double precision, delta_interval_score double precision, decision text, group_verdict text, runtime_s double precision, no_peek_warnings text, label text, note text)"
) }}
-- Plan D1 (Wave D): the feature-group harness's verdicts, one row per group x position from each group's
-- latest run (`league-lab experiment <group>`, src/league_lab/experiments.py). The season is the paired
-- unit: each test season's delta (group - baseline) is first averaged over the leagues, then the
-- seasons are averaged and counted (seasons_better_*). `decision` / `group_verdict` are the harness's
-- (docs/METRICS.md § "Feature experiments"), passed through, never recomputed here.
-- The rows come from two places: the runs on this database (ops.feature_experiments) and the published record
-- (seed feature_experiments: the Wave D runs, exported from the PO's database so that a fresh build shows
-- "What we tried" without re-running 10 CPU-minutes per group). The same run in both = one row (ops wins).
with every_row as (
    select distinct on (run_id, feature_group, position, league_id, test_season)
           run_id, run_at, model_version, harness_version, feature_group, group_table, group_columns, test_seasons, train_seasons, data_key, position, league_id, test_season, n_weeks, n_player_weeks, spearman, hit_rate, mae, coverage_80, interval_width, interval_score, baseline_spearman, baseline_hit_rate, baseline_mae, baseline_coverage_80, baseline_interval_width, baseline_interval_score, delta_spearman, delta_hit_rate, delta_mae, delta_coverage_80, delta_interval_width, delta_interval_score, decision, group_verdict, runtime_s, no_peek_warnings, label, note
    from (
        select 0 as pri, run_id, run_at, model_version, harness_version, feature_group, group_table, group_columns, test_seasons, train_seasons, data_key, position, league_id, test_season, n_weeks, n_player_weeks, spearman, hit_rate, mae, coverage_80, interval_width, interval_score, baseline_spearman, baseline_hit_rate, baseline_mae, baseline_coverage_80, baseline_interval_width, baseline_interval_score, delta_spearman, delta_hit_rate, delta_mae, delta_coverage_80, delta_interval_width, delta_interval_score, decision, group_verdict, runtime_s, no_peek_warnings, label, note
        from {{ source('ops', 'feature_experiments') }}
        union all
        select 1 as pri, run_id, run_at, model_version, harness_version, feature_group, group_table, group_columns, test_seasons, train_seasons, data_key, position, league_id, test_season, n_weeks, n_player_weeks, spearman, hit_rate, mae, coverage_80, interval_width, interval_score, baseline_spearman, baseline_hit_rate, baseline_mae, baseline_coverage_80, baseline_interval_width, baseline_interval_score, delta_spearman, delta_hit_rate, delta_mae, delta_coverage_80, delta_interval_width, delta_interval_score, decision, group_verdict, runtime_s, no_peek_warnings, label, note
        from {{ ref('feature_experiments') }}
    ) as u
    order by run_id, feature_group, position, league_id, test_season, pri
),

latest as (
    select distinct on (feature_group) feature_group, run_id
    from every_row
    where feature_group <> 'baseline'
    order by feature_group, run_at desc
),

runs as (
    select e.*
    from every_row as e
    join latest as l using (feature_group, run_id)
),

per_season as (
    select feature_group, position, test_season,
           avg(spearman) as spearman, avg(baseline_spearman) as baseline_spearman,
           avg(mae) as mae, avg(baseline_mae) as baseline_mae,
           avg(delta_spearman) as delta_spearman, avg(delta_mae) as delta_mae, avg(delta_hit_rate) as delta_hit_rate,
           avg(delta_coverage_80) as delta_coverage_80, avg(delta_interval_width) as delta_interval_width,
           avg(interval_score) as interval_score, avg(baseline_interval_score) as baseline_interval_score,
           avg(delta_interval_score) as delta_interval_score,
           sum(n_player_weeks) as n_player_weeks, count(distinct league_id) as n_leagues
    from runs
    group by 1, 2, 3
)

select
    r.feature_group,
    max(r.label)                                           as label,
    max(r.note)                                            as note,
    max(r.group_table)                                     as group_table,
    max(r.group_columns)                                   as group_columns,
    s.position,
    max(r.model_version)                                   as model_version,
    max(r.test_seasons)                                    as test_seasons,
    count(distinct s.test_season)                          as n_seasons,
    max(s.n_leagues)                                       as n_leagues,
    round(avg(s.spearman)::numeric, 4)                     as spearman,
    round(avg(s.baseline_spearman)::numeric, 4)            as baseline_spearman,
    round(avg(s.delta_spearman)::numeric, 4)               as delta_spearman,
    count(distinct s.test_season) filter (where s.delta_spearman > 0) as seasons_better_spearman,
    round(avg(s.mae)::numeric, 3)                          as mae,
    round(avg(s.baseline_mae)::numeric, 3)                 as baseline_mae,
    round(avg(s.delta_mae)::numeric, 3)                    as delta_mae,
    count(distinct s.test_season) filter (where s.delta_mae < 0) as seasons_better_mae,
    round(avg(s.delta_hit_rate)::numeric, 4)               as delta_hit_rate,
    round(avg(s.delta_coverage_80)::numeric, 4)            as delta_coverage_80,
    round(avg(s.delta_interval_width)::numeric, 3)         as delta_interval_width,
    round(avg(s.interval_score)::numeric, 4)               as interval_score,
    round(avg(s.delta_interval_score)::numeric, 4)         as delta_interval_score,
    max(r.decision)                                        as decision,
    max(r.group_verdict)                                   as group_verdict,
    max(r.no_peek_warnings)                                as no_peek_warnings,
    max(r.runtime_s)                                       as runtime_s,
    max(r.run_at)                                          as run_at
from per_season as s
join runs as r on r.feature_group = s.feature_group and r.position = s.position and r.test_season = s.test_season
group by r.feature_group, s.position
