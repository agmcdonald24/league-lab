-- League Lab usage tracking (Wave I-F, U-1; plan § 17 E "which screens get used"). Plain SQL, idempotent.
--
-- One table, usage.events: one row per screen view of the phone web app — which screen, which league and team
-- number, when, the release, and a random id the browser keeps for one day. Nothing about a person: no name,
-- username, IP address, user agent, login token, player or free text (the API allow-lists every value and the
-- checks below refuse anything else). docs/HOSTING.md § "Usage".
--
-- The schema `usage` is NOT one the sync replaces: scripts/sync_to_hosted.sh drops and restores analytics,
-- analytics_seeds and ops only, then runs this file (its "U-1" block) — so the rows survive every nightly.
-- The read-only app role keeps `default_transaction_read_only = on`; it gets INSERT and SELECT on this one table
-- (the API's insert opens its own `BEGIN; SET TRANSACTION READ WRITE; INSERT; COMMIT`) and nothing else here.
--
-- Run it as the database owner:
--   hosted:  the sync does it every night (LEAGUE_LAB_HOSTED_ADMIN_URL, the Neon owner role)
--   local:   psql "$(uv run python -c 'from league_lab.config import get_settings; print(get_settings().pipeline_dsn())')" \
--                 -v ON_ERROR_STOP=1 -f scripts/hosted_usage.sql
--            (the pipeline role owns the Mac's database; on a database it does not own, run it as the owner)

set client_min_messages = warning;    -- a re-run's "already exists, skipping" notices stay out of the nightly's log
create schema if not exists usage;

create table if not exists usage.events (
  at         timestamptz not null default now(),
  screen     text not null,
  league_key text,
  roster_id  int,
  platform   text,
  version    text,
  session    text,
  constraint events_screen_word   check (screen ~ '^[a-z-]{1,24}$'),
  constraint events_league_key_id check (league_key ~ '^(mfl:)?[0-9]{1,24}$'),
  constraint events_roster_number check (roster_id between 0 and 9999),
  constraint events_platform_name check (platform in ('sleeper', 'mfl')),
  constraint events_version_stamp check (version ~ '^[A-Za-z0-9._+-]{1,40}$'),
  constraint events_session_token check (session ~ '^[0-9a-f]{32}$')
);
create index if not exists events_at on usage.events (at);

comment on table usage.events is
  'One row per screen view of the web app (Wave I-F, U-1). No names, usernames or IP addresses; session is a random id kept by the browser for one day.';

grant usage on schema usage to league_lab_app;
grant select, insert on usage.events to league_lab_app;
revoke update, delete, truncate, references, trigger on usage.events from league_lab_app;

-- ---- IG-3 (Wave I-G): retention. Every run (the sync's U-1 block, once a night) deletes the views older than 180 days,
-- so usage.events holds about six months (at ~168 bytes a row with its index: well under the hosted plan's room). The
-- owner deletes; the app role still cannot. The console's Usage page and docs/HOSTING.md § "Usage" say so.
delete from usage.events where at < now() - interval '180 days';
-- ---- end IG-3
