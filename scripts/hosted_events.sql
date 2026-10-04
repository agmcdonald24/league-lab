-- League Lab event store (Wave I-G, IG-2; the decision-quality review § "Engineering requirements"). Plain SQL, idempotent.
--
-- One table, events.events: one row per thing the app learned about a player or a team, with where it came from and
-- when — an injury-report status move (the availability overlay: ESPN / Sleeper), an ESPN news item the app showed, a
-- PlayerWire brief the app showed. Keyed by player (gsis id, the source's own id), team and game; source URL,
-- publication time, effective time, ingestion time, status, and which newer event superseded it. docs/HOSTING.md
-- § "Events", docs/ANY_LEAGUE.md § "Events".
--
-- The schema `events` is NOT one the sync replaces: scripts/sync_to_hosted.sh drops and restores analytics,
-- analytics_seeds and ops only, then runs this file (its "IG-2" block, after U-1) — so the rows survive every nightly.
-- The read-only app role keeps `default_transaction_read_only = on`; it gets SELECT, INSERT and UPDATE of
-- superseded_by on this one table (the API's writer opens its own `BEGIN; SET TRANSACTION READ WRITE; ...; COMMIT`)
-- and nothing else here. usage.events is not touched.
--
-- Run it as the database owner:
--   hosted:  the sync does it every night (LEAGUE_LAB_HOSTED_ADMIN_URL, the Neon owner role)
--   local:   psql "$(uv run python -c 'from league_lab.config import get_settings; print(get_settings().pipeline_dsn())')" \
--                 -v ON_ERROR_STOP=1 -f scripts/hosted_events.sql
--            (the pipeline role owns the Mac's database; on a database it does not own, run it as the owner)

set client_min_messages = warning;    -- a re-run's "already exists, skipping" notices stay out of the nightly's log
create schema if not exists events;

create table if not exists events.events (
  id            bigserial primary key,
  kind          text not null,
  player_key    text,
  gsis_id       text,
  team          text,
  game_key      text,
  status        text,
  headline      text,
  summary       text,
  source        text not null,
  source_url    text,
  published_at  timestamptz,
  effective_at  timestamptz,
  ingested_at   timestamptz not null default now(),
  superseded_by bigint,
  fingerprint   text not null,
  constraint events_fingerprint_unique unique (fingerprint),
  constraint events_kind_word        check (kind in ('availability', 'news', 'brief', 'depth_chart')),
  constraint events_gsis_id_shape    check (gsis_id ~ '^00-[0-9]{7}$'),
  constraint events_player_key_shape check (player_key ~ '^(sleeper|espn|mfl|pw):[A-Za-z0-9_.-]{1,40}$'),
  constraint events_team_abbr        check (team ~ '^[A-Z]{2,3}$'),
  constraint events_game_key_shape   check (game_key ~ '^[0-9]{4}_[0-9]{2}_[A-Z]{2,3}_[A-Z]{2,3}$'),
  constraint events_has_a_subject    check (gsis_id is not null or team is not null),
  constraint events_status_word      check (status ~ '^[A-Za-z_-]{1,24}$'),
  constraint events_source_name      check (length(source) between 1 and 80),
  constraint events_source_url_https check (source_url ~ '^https://' and length(source_url) <= 1000),
  constraint events_headline_length  check (length(headline) <= 500),
  constraint events_summary_length   check (length(summary) <= 4000),
  constraint events_fingerprint_sha  check (fingerprint ~ '^[0-9a-f]{64}$'),
  constraint events_not_self_superseded check (superseded_by is distinct from id)
);
create index if not exists events_gsis_ingested on events.events (gsis_id, ingested_at);
create index if not exists events_team_ingested on events.events (team, ingested_at);
create index if not exists events_live_key on events.events (kind, gsis_id) where superseded_by is null;

comment on table events.events is
  'Structured events (Wave I-G, IG-2): injury-report status moves, news items and PlayerWire briefs the app showed, keyed to player / team / game, with source URL, publication, effective and ingestion times and the newer event that superseded each.';

grant usage on schema events to league_lab_app;
grant select, insert on events.events to league_lab_app;
grant update (superseded_by) on events.events to league_lab_app;
grant usage on sequence events.events_id_seq to league_lab_app;
revoke delete, truncate, references, trigger on events.events from league_lab_app;
