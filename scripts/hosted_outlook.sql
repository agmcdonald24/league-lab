-- League Lab outlook snapshots (Wave I-O, IO-2; docs/STATUS.md § "Wave I-O" → IO-2, api/league_lab_api/outlook_store.py). Plain SQL,
-- idempotent.
--
-- One table, outlook.snapshots: one row per league and week — the League screen's power ranking (per team: the points
-- its best lineup is expected to score per week over the rest of the season, and its rank) and the rest-of-season rows
-- (projected wins, playoff odds, top seed), the model version and when it was built. Written by the API when it builds
-- a league's outlook, replaced by a later build only until that week's first kickoff (`closes_at`; after it the week is
-- closed), so last week's ranking can be compared with this week's: the movement arrows on the League screen are drawn
-- from these rows and from nothing else. What cannot be backfilled: the rest-of-season board is refit every night.
--
-- Bounds (the site is public: any visitor's League screen can trigger a write):
--   * a row: power + rows ≤ 8 KB of JSON (a 32-team league with names ≈ 7 KB; a 12-team ≈ 2.7 KB), checked here;
--   * leagues: house leagues always; every other league — saved by an account or not (fix round: no exemption) — at
--     most 20 new a day and at most 200 held (the API checks both inside the write's transaction); a league-week is
--     replaced at most once an hour; past 40 MB of pg_total_relation_size (read at most once a minute) no new row;
--   * weeks: rows built more than 20 weeks (140 days) ago are pruned below, and each league keeps its newest 20 weeks.
--   Worst case: (200 + 2 house leagues) × 20 weeks × ≤ 8.5 KB a row on disk ≈ 34.3 MB + indexes (< 40 MB, the guard);
--   typical (12 teams, 1.75 KB a row on disk) ≈ 7 MB at the cap.
--
-- The schema `outlook` is NOT one the sync replaces: scripts/sync_to_hosted.sh drops and restores analytics,
-- analytics_seeds and ops only, then runs this file — so the rows survive every nightly. The read-only app role keeps
-- `default_transaction_read_only = on`; it gets SELECT, INSERT and UPDATE on this one table (the API's writer opens its
-- own `BEGIN; SET TRANSACTION READ WRITE; ...; COMMIT`) and nothing else here. Pruning is the owner's (below).
--
-- Run it as the database owner:
--   hosted:  the sync does it every night (LEAGUE_LAB_HOSTED_ADMIN_URL, the Neon owner role)
--   local:   psql "$(uv run python -c 'from league_lab.config import get_settings; print(get_settings().pipeline_dsn())')" \
--                 -v ON_ERROR_STOP=1 -f scripts/hosted_outlook.sql
--            (the pipeline role owns the Mac's database; on a database it does not own, run it as the owner)

set client_min_messages = warning;    -- a re-run's "already exists, skipping" notices stay out of the nightly's log
create schema if not exists outlook;

create table if not exists outlook.snapshots (
  league_key    text not null,
  season        int not null,
  week          int not null,
  kind          text not null,
  league_name   text,
  model_version text not null,
  built_at      timestamptz not null,
  closes_at     timestamptz not null,
  teams         int not null,
  power         jsonb not null,
  rows          jsonb not null,
  primary key (league_key, season, week),
  constraint snapshots_league_key   check (league_key ~ '^([0-9]{1,24}|mfl:[0-9]{1,12})$'),
  constraint snapshots_season_year  check (season between 2000 and 2100),
  constraint snapshots_week_number  check (week between 1 and 22),
  constraint snapshots_kind_word    check (kind in ('house', 'saved', 'visitor')),
  constraint snapshots_name_length  check (length(league_name) <= 120),
  constraint snapshots_version      check (model_version ~ '^[A-Za-z0-9._-]{1,24}$'),
  constraint snapshots_teams        check (teams between 1 and 32),
  constraint snapshots_power_array  check (jsonb_typeof(power) = 'array'),
  constraint snapshots_rows_array   check (jsonb_typeof(rows) = 'array'),
  constraint snapshots_size         check (octet_length(power::text) + octet_length(rows::text) <= 8192)
);
create index if not exists snapshots_kind_built on outlook.snapshots (kind, built_at);

comment on table outlook.snapshots is
  'Each league-week''s League screen outlook (Wave I-O, IO-2): power ranking per team and the rest-of-season rows, frozen at the week''s first kickoff; the movement arrows read it.';

grant usage on schema outlook to league_lab_app;
grant select, insert, update on outlook.snapshots to league_lab_app;
revoke delete, truncate, references, trigger on outlook.snapshots from league_lab_app;

-- Retention: every run (the sync, once a night) drops what no reader needs any more — the movement reads last week's
-- row only; 20 weeks keeps a season's record. By built_at (the API's clock at the build) and by week per league.
delete from outlook.snapshots where built_at < now() - interval '140 days';
delete from outlook.snapshots s
 using (select league_key, season, week,
               row_number() over (partition by league_key order by season desc, week desc) as k
          from outlook.snapshots) old
 where s.league_key = old.league_key and s.season = old.season and s.week = old.week and old.k > 20;
