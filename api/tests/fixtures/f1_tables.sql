-- Plan F3: the NFL-wide tables the API for any league reads (plan F1 builds the real ones; the PO reconciles the
-- column names with F1 at integration — anyleague.NFL_WIDE is the one place the read path names them).
-- This file creates them in a developer clone with the DDL F3 expects and fills them from ops.projections, so
-- the read path (anyleague.load_board's `nfl_wide` source) is tested before F1's writer is merged:
--
--   PGPASSWORD=... psql -U postgres -h localhost -d league_lab_f3 -v ON_ERROR_STOP=1 -f api/tests/fixtures/f1_tables.sql
--
-- * ops.projection_lines: one row per player-week (QB-TE), the 12 stat-line components, the freeze columns.
-- * ops.projection_ranges: one row per scoring_name x player-week (QB-TE and K / DEF): proj_points, p10-p90 in that
--   scoring. Here: the two house leagues' rows under two reference names (each house league is then an EXACT match).
-- * ops.kd_lines: one row per K / DEF unit-week, kdef.predict_kd's league-free line (proj_<K_LINE / DEF_LINE>).
--   SYNTHETIC here: ops.projections keeps only the priced K / DEF points, not the line, so a kicker's line is
--   "proj_pat_made = his League of Scrubs points" and a defense's "proj_sacks = its Scrubs points" (Scrubs: xpm 1,
--   sack 1) — it prices back to the Scrubs value exactly and moves with a league's xpm / sack weights.
-- * analytics_seeds.reference_scorings: name, label, scoring_settings (JSON text) — the seed F1 owns.
-- Owned by the pipeline role, readable by the app role (as the real tables will be).

set role league_lab_pipeline;

drop table if exists ops.projection_lines;
create table ops.projection_lines (
    model_version text not null, fitted_at timestamptz, train_seasons text,
    season integer not null, week integer not null, gsis_id text not null, position text not null,
    proj_targets double precision, proj_receptions double precision, proj_receiving_yards double precision,
    proj_receiving_tds double precision, proj_carries double precision, proj_rushing_yards double precision,
    proj_rushing_tds double precision, proj_attempts double precision, proj_passing_yards double precision,
    proj_passing_tds double precision, proj_passing_interceptions double precision, proj_fumbles_lost_total double precision,
    frozen_at timestamptz, frozen_source text
);
insert into ops.projection_lines
select distinct on (season, week, gsis_id)
       model_version, fitted_at, train_seasons, season, week, gsis_id, position,
       proj_targets, proj_receptions, proj_receiving_yards, proj_receiving_tds, proj_carries, proj_rushing_yards,
       proj_rushing_tds, proj_attempts, proj_passing_yards, proj_passing_tds, proj_passing_interceptions,
       proj_fumbles_lost_total, frozen_at, frozen_source
from ops.projections
where position in ('QB', 'RB', 'WR', 'TE')
order by season, week, gsis_id, league_id;
create index on ops.projection_lines (season, week);

drop table if exists ops.projection_ranges;
create table ops.projection_ranges (
    model_version text not null, fitted_at timestamptz, scoring_name text not null,
    season integer not null, week integer not null, gsis_id text not null, position text not null,
    proj_points double precision, p10 double precision, p25 double precision, p50 double precision,
    p75 double precision, p90 double precision, frozen_at timestamptz, frozen_source text
);
insert into ops.projection_ranges
select model_version, fitted_at,
       case league_id when '1389709692405551104' then 'half_ppr_4pt_kdef' else 'sf_ppr_6pt_bonuses' end,
       season, week, gsis_id, position, proj_points, p10, p25, p50, p75, p90, frozen_at, frozen_source
from ops.projections
where league_id in ('1389709692405551104', '1321941740235550720');
create index on ops.projection_ranges (season, week);

drop table if exists ops.kd_lines;
create table ops.kd_lines (
    model_version text not null, fitted_at timestamptz, season integer not null, week integer not null,
    position text not null, unit_id text not null,
    proj_fg_made_0_19 double precision, proj_fg_made_20_29 double precision, proj_fg_made_30_39 double precision,
    proj_fg_made_40_49 double precision, proj_fg_made_50p double precision, proj_fg_missed double precision,
    proj_pat_made double precision, proj_pat_missed double precision, proj_fg_missed_0_19 double precision,
    proj_fg_missed_20_29 double precision, proj_fg_missed_30_39 double precision, proj_fg_missed_40_49 double precision,
    proj_fg_missed_50p double precision,
    proj_sacks double precision, proj_interceptions double precision, proj_fumble_recoveries double precision,
    proj_forced_fumbles double precision, proj_def_tds double precision, proj_st_tds double precision,
    proj_safeties double precision, proj_blocked_kicks double precision, proj_points_allowed double precision,
    proj_pa_0 double precision, proj_pa_1_6 double precision, proj_pa_7_13 double precision, proj_pa_14_20 double precision,
    proj_pa_21_27 double precision, proj_pa_28_34 double precision, proj_pa_35p double precision,
    frozen_at timestamptz, frozen_source text
);
insert into ops.kd_lines (model_version, fitted_at, season, week, position, unit_id, proj_pat_made, proj_sacks,
                          frozen_at, frozen_source)
select model_version, fitted_at, season, week, position, gsis_id,
       case when position = 'K' then proj_points end, case when position = 'DEF' then proj_points end,
       frozen_at, frozen_source
from ops.projections
where league_id = '1389709692405551104' and position in ('K', 'DEF');
create index on ops.kd_lines (season, week);

reset role;
create schema if not exists analytics_seeds authorization league_lab_pipeline;   -- dbt creates it; a bare clone may not have it
set role league_lab_pipeline;
drop table if exists analytics_seeds.reference_scorings;
create table analytics_seeds.reference_scorings (name text not null, label text, scoring_settings text not null);
insert into analytics_seeds.reference_scorings
select case league_id when '1389709692405551104' then 'half_ppr_4pt_kdef' else 'sf_ppr_6pt_bonuses' end,
       scoring_label, scoring_settings::text
from analytics.dim_league_season
where league_id in ('1389709692405551104', '1321941740235550720');

grant select on ops.projection_lines, ops.projection_ranges, ops.kd_lines, analytics_seeds.reference_scorings
    to league_lab_app;
reset role;
