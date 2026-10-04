-- PlayerWire briefs on the hosted Postgres (plan N2; docs/PLAYERWIRE.md). Idempotent: run it again any time.
--
-- What it makes:
--   role   playerwire_writer   LOGIN, the ONLY writer of schema playerwire (the Mac's scripts/playerwire_sync.py)
--   schema playerwire          owned by playerwire_writer: briefs, brief_players, sync_state
--   grants league_lab_app      (the API's read-only role) USAGE on the schema + SELECT on its tables, now and later
--
-- Why a schema of its own (HOSTING.md § 5, the one-writer rule, extended): the nightly's sync_to_hosted.sh drops and
-- restores `analytics`, `analytics_seeds` and `ops` and nothing else; `playerwire` is never in its dump, its drop or its
-- relation audit, and the nightly never writes it. playerwire_writer has no privilege on any other schema, so the
-- briefs' writer cannot touch the marts and the marts' writer never touches the briefs. Nothing in `playerwire` may
-- reference `analytics` (no view, no foreign key): `drop schema analytics cascade` would take it along. The API joins
-- `analytics.player_id_map` at request time instead.
--
-- Run as the database owner (Neon: neondb_owner), with the writer's password in the environment (never on argv):
--   PLAYERWIRE_WRITER_PASSWORD=... psql "$LEAGUE_LAB_HOSTED_ADMIN_URL" -v ON_ERROR_STOP=1 -f scripts/init_playerwire_schema.sql
-- or `make playerwire-schema` (reads both from .env). Needs psql 16+ (\getenv) and Postgres 16+ (role grants WITH SET).

\set ON_ERROR_STOP on
set client_min_messages = warning;
\getenv writer_pw PLAYERWIRE_WRITER_PASSWORD
\if :{?writer_pw}
\else
  do $$ begin raise exception 'PLAYERWIRE_WRITER_PASSWORD is not set: export it (or put it in .env and use make playerwire-schema)'; end $$;
\endif

-- ---------------------------------------------------------------------------------------------------- roles
do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'playerwire_writer') then
    create role playerwire_writer login;
  end if;
  -- the API's read-only role; normally made by sync_to_hosted.sh (which also sets its password every night).
  -- Made here only when this runs first, with the same read-only settings.
  if not exists (select 1 from pg_roles where rolname = 'league_lab_app') then
    create role league_lab_app login;
  end if;
end $$;
alter role playerwire_writer with login password :'writer_pw';
alter role playerwire_writer connection limit 3;
alter role playerwire_writer set statement_timeout = '60s';
alter role playerwire_writer set idle_in_transaction_session_timeout = '120s';
alter role league_lab_app set default_transaction_read_only = on;
alter role league_lab_app set statement_timeout = '30s';

-- the owner (neondb_owner: CREATEROLE, not a superuser) must be able to SET ROLE to the writer to create objects it
-- will own; a re-grant is a notice, not an error
grant playerwire_writer to current_user;

-- ---------------------------------------------------------------------------------------------------- schema
create schema if not exists playerwire authorization playerwire_writer;
alter schema playerwire owner to playerwire_writer;
revoke all on schema playerwire from public;

set role playerwire_writer;

-- One row per brief, the current version as served (or its tombstone). Display columns are derived from `payload`
-- by the sync (AGENTS.md rule 6: the full payload is kept). A withdrawn brief keeps its row (deleted = true, the
-- tombstone's version and reason) so a late re-delivery of an older version cannot bring it back, and keeps none of
-- its text: headline / news / analysis / evidence are NULL and `payload` is the tombstone (PlayerWire's withdrawal
-- semantics; the check below enforces it).
create table if not exists playerwire.briefs (
    brief_id              text primary key,
    version               integer not null check (version >= 1),
    status                text not null,                 -- 'published' (live) | 'withdrawn' (a tombstone)
    pw_player_id          text,                          -- PlayerWire's permanent player id (primary_player.id)
    primary_sleeper_id    text,                          -- primary_player.external_ids.sleeper
    primary_gsis_id       text,                          -- primary_player.external_ids.gsis (nullable)
    category              text,
    headline              text,
    news                  text,
    analysis              text,                          -- analysis.text (analysis may be null)
    verification_status   text,                          -- official | reported | corroborated | disputed
    published_at          timestamptz,
    updated_at            timestamptz,
    evidence_url          text,                          -- evidence[0].url (https)
    evidence_publisher    text,                          -- evidence[0].publisher
    evidence_published_at timestamptz,                   -- evidence[0].source_published_at
    payload               jsonb not null,                -- the brief as served; for a tombstone, the tombstone
    synced_at             timestamptz not null default now(),
    deleted               boolean not null default false,
    deleted_reason        text,
    deleted_at            timestamptz,
    constraint briefs_withdrawn_text_gone check (
        not deleted or (headline is null and news is null and analysis is null and evidence_url is null))
);
create index if not exists briefs_primary_sleeper on playerwire.briefs (primary_sleeper_id) where not deleted;
create index if not exists briefs_primary_gsis on playerwire.briefs (primary_gsis_id) where not deleted;
create index if not exists briefs_published on playerwire.briefs (published_at desc) where not deleted;

-- The players a brief names: its primary player and every related player, by PlayerWire id with the external ids
-- the payload carried. The API maps them through analytics.player_id_map (rule 3: ids, never names).
create table if not exists playerwire.brief_players (
    brief_id     text not null references playerwire.briefs (brief_id) on delete cascade,
    pw_player_id text not null,
    sleeper_id   text,
    gsis_id      text,
    role         text not null check (role in ('primary', 'related')),
    primary key (brief_id, pw_player_id)
);
create index if not exists brief_players_sleeper on playerwire.brief_players (sleeper_id);
create index if not exists brief_players_gsis on playerwire.brief_players (gsis_id);

-- The replication cursor and the last run (one row). The cursor is written in the same transaction as the briefs it
-- covers, never before.
create table if not exists playerwire.sync_state (
    id                 integer primary key check (id = 1),
    sync_cursor        text,
    high_watermark     text,
    snapshot_watermark text,
    filter_signature   text,
    bootstrapped_at    timestamptz,
    last_sync_at       timestamptz,
    last_error         text,
    last_error_at      timestamptz,
    api_url            text
);
insert into playerwire.sync_state (id) values (1) on conflict (id) do nothing;

-- ---------------------------------------------------------------------------------------------------- read access
grant usage on schema playerwire to league_lab_app;
grant select on all tables in schema playerwire to league_lab_app;
alter default privileges in schema playerwire grant select on tables to league_lab_app;

reset role;

select 'playerwire schema ready: ' || count(*) || ' tables, owner ' || pg_get_userbyid(n.nspowner)
from pg_namespace n join pg_class c on c.relnamespace = n.oid and c.relkind = 'r'
where n.nspname = 'playerwire' group by n.nspowner;
