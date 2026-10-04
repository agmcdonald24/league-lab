-- League Lab: roles, database, schemas and grants.
-- Run as a superuser (Homebrew Postgres: your macOS user) against the *postgres* maintenance DB:
--   psql -v ON_ERROR_STOP=1 -v pipeline_pw="'...'" -v app_pw="'...'" -d postgres -f scripts/init_db.sql
-- Another database name (a worktree, the CI service): add  -v db_name=league_lab_ci  (default league_lab).
-- Idempotent: safe to re-run, including on a cluster where the roles already exist (they are
-- shared by every database in the cluster). Passwords are only (re)set when the variables are supplied.

\if :{?db_name}
\else
  \set db_name league_lab
\endif

-- Roles ------------------------------------------------------------------------------
select 'create role league_lab_pipeline login' where not exists (select 1 from pg_roles where rolname = 'league_lab_pipeline') \gexec
select 'create role league_lab_app login' where not exists (select 1 from pg_roles where rolname = 'league_lab_app') \gexec

\if :{?pipeline_pw}
  alter role league_lab_pipeline password :pipeline_pw;
\endif
\if :{?app_pw}
  alter role league_lab_app password :app_pw;
\endif

-- Database ---------------------------------------------------------------------------
select format('create database %I owner league_lab_pipeline', :'db_name')
where not exists (select 1 from pg_database where datname = :'db_name') \gexec

\connect :"db_name"

-- Lock down PUBLIC, then hand the pipeline role the schemas it owns ------------------
revoke create on schema public from public;
revoke all on database :"db_name" from public;
grant connect on database :"db_name" to league_lab_app;

create schema if not exists raw          authorization league_lab_pipeline;
create schema if not exists ops          authorization league_lab_pipeline;
create schema if not exists staging      authorization league_lab_pipeline;
create schema if not exists intermediate authorization league_lab_pipeline;
create schema if not exists analytics    authorization league_lab_pipeline;
create schema if not exists analytics_seeds authorization league_lab_pipeline;

-- Read-only app role: SELECT on analytics (+ ops for the data-status page), nothing else ---
grant usage on schema analytics, analytics_seeds, ops to league_lab_app;
grant select on all tables in schema analytics, analytics_seeds, ops to league_lab_app;
-- future objects created by the pipeline role inherit the grant
alter default privileges for role league_lab_pipeline in schema analytics       grant select on tables to league_lab_app;
alter default privileges for role league_lab_pipeline in schema analytics_seeds grant select on tables to league_lab_app;
alter default privileges for role league_lab_pipeline in schema ops             grant select on tables to league_lab_app;
alter role league_lab_app set default_transaction_read_only = on;
alter role league_lab_app set statement_timeout = '30s';

-- ---- IG-2 (Wave I-G): the event store events.events — the same file the sync runs on the hosted copy, run here as the
-- pipeline role so the schema is its own (the app role: SELECT, INSERT, UPDATE of superseded_by; docs/HOSTING.md § "Events")
set role league_lab_pipeline;
\ir hosted_events.sql
reset role;
-- ---- end IG-2
