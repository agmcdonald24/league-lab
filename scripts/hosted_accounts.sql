-- League Lab accounts, phase 1 (Wave I-K, IK-4; docs/ACCOUNTS.md § "Built, phase 1") and passkeys (Wave I-M, IM-4;
-- § "Passkeys"). Plain SQL, idempotent.
--
-- Sign-in by an emailed link or a passkey, the leagues a person saves, their preferences and watchlist. Ten tables in
-- the schema `accounts`, the design's model (docs/ACCOUNTS.md § "The model") with these phase-1 decisions:
--   * email is text, stored lower-case (a check; no citext extension to install on Neon);
--   * the display fields of a saved league (its name, the team's name, the scoring line) live on the user's own row
--     (user_leagues), never on the shared `leagues` row: one user can never change what another user sees;
--   * `connections` exists for the next wave (Yahoo's refresh token, an ESPN connection); nothing writes it yet;
--   * deleting an account deletes every row at once (on delete cascade from users); no audit window.
-- Nothing here is a secret: a login link's token and a passkey challenge are stored only as their SHA-256, a session row holds no token (the
-- cookie carries the session id + an HMAC made with LEAGUE_LAB_API_SECRET, which lives on Render only), the IP a link
-- was asked from only as an HMAC (the rate limit's key).
--
-- The schema `accounts` is NOT one the sync replaces: scripts/sync_to_hosted.sh drops and restores analytics,
-- analytics_seeds and ops only, then runs this file (its "IK-4" block, after IG-2) — so the rows survive every nightly.
-- These are the first rows the nightly cannot rebuild: Neon's point-in-time restore is their backup.
-- The read-only app role keeps `default_transaction_read_only = on`; it gets SELECT, INSERT, UPDATE and DELETE on these
-- ten tables and nothing else here (the API's writer opens its own `BEGIN; SET TRANSACTION READ WRITE; ...; COMMIT`:
-- league_lab_api/db.py `run_rw`). No new role, no new connection string.
--
-- Run it as the database owner:
--   hosted:  the sync does it every night (LEAGUE_LAB_HOSTED_ADMIN_URL, the Neon owner role)
--   local:   psql "$(uv run python -c 'from league_lab.config import get_settings; print(get_settings().pipeline_dsn())')" \
--                 -v ON_ERROR_STOP=1 -f scripts/hosted_accounts.sql
--            (the pipeline role owns the Mac's database; on a database it does not own, run it as the owner)

set client_min_messages = warning;    -- a re-run's "already exists, skipping" notices stay out of the nightly's log
create schema if not exists accounts;

create table if not exists accounts.users (
  id           uuid primary key default gen_random_uuid(),
  email        text not null,
  created_at   timestamptz not null default now(),
  last_seen_at timestamptz,
  deleted_at   timestamptz,
  constraint users_email_unique unique (email),
  constraint users_email_shape  check (email = lower(email) and length(email) between 3 and 254
                                       and email ~ '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$')
);

create table if not exists accounts.login_links (
  token_hash bytea primary key,
  user_email text not null,
  created_at timestamptz not null default now(),
  expires_at timestamptz not null,
  used_at    timestamptz,
  ip_hash    bytea,
  constraint login_links_token_sha256 check (octet_length(token_hash) = 32),
  constraint login_links_ip_hmac      check (ip_hash is null or octet_length(ip_hash) = 32),
  constraint login_links_email_shape  check (user_email = lower(user_email) and length(user_email) between 3 and 254)
);
create index if not exists login_links_email_created on accounts.login_links (user_email, created_at);
create index if not exists login_links_ip_created on accounts.login_links (ip_hash, created_at);
create index if not exists login_links_created on accounts.login_links (created_at);

create table if not exists accounts.sessions (
  id                uuid primary key default gen_random_uuid(),
  user_id           uuid not null references accounts.users (id) on delete cascade,
  created_at        timestamptz not null default now(),
  expires_at        timestamptz not null,
  revoked_at        timestamptz,
  user_agent_family text,
  constraint sessions_agent_word check (user_agent_family ~ '^[A-Za-z ]{1,24}$')
);
create index if not exists sessions_user on accounts.sessions (user_id);

create table if not exists accounts.connections (
  id               uuid primary key default gen_random_uuid(),
  user_id          uuid not null references accounts.users (id) on delete cascade,
  provider         text not null,
  external_user_id text not null,
  label            text,
  kind             text not null,
  secret_enc       bytea,
  status           text not null default 'active',
  last_sync_at     timestamptz,
  last_error       text,
  created_at       timestamptz not null default now(),
  constraint connections_one_per_identity unique (user_id, provider, external_user_id),
  constraint connections_provider_name check (provider in ('sleeper', 'mfl', 'espn', 'yahoo')),
  constraint connections_kind_word     check (kind in ('lookup', 'league_key', 'oauth', 'cookie')),
  constraint connections_status_word   check (status in ('active', 'expired', 'revoked', 'failing')),
  constraint connections_external_len  check (length(external_user_id) between 1 and 200),
  constraint connections_label_len     check (length(label) <= 200),
  constraint connections_error_len     check (length(last_error) <= 500)
);

create table if not exists accounts.leagues (
  league_key    text primary key,
  provider      text not null,
  season        int not null,
  external_id   text not null,
  name          text,
  scoring_label text,
  total_rosters int,
  public        boolean,
  last_sync_at  timestamptz,
  sync_status   text,
  sync_error    text,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  constraint leagues_provider_name check (provider in ('sleeper', 'mfl', 'espn', 'yahoo')),
  constraint leagues_season_year   check (season between 2000 and 2100),
  constraint leagues_key_parts     check (league_key = provider || ':' || season || ':' || external_id),
  constraint leagues_external_id   check (external_id ~ '^[0-9]{1,24}$'
                                          or (provider = 'yahoo' and external_id ~ '^[0-9]{1,6}\.l\.[0-9]{1,12}$')),
  constraint leagues_name_len      check (length(name) <= 120),
  constraint leagues_scoring_len   check (length(scoring_label) <= 160),
  constraint leagues_rosters_count check (total_rosters between 1 and 64),
  constraint leagues_sync_word     check (sync_status in ('ok', 'failing', 'not_found', 'private')),
  constraint leagues_error_len     check (length(sync_error) <= 500)
);

create table if not exists accounts.user_leagues (
  user_id          uuid not null references accounts.users (id) on delete cascade,
  league_key       text not null references accounts.leagues (league_key) on delete cascade,
  connection_id    uuid references accounts.connections (id) on delete set null,
  team_external_id text,
  name             text,
  team_name        text,
  scoring_label    text,
  total_rosters    int,
  is_default       boolean not null default false,
  hidden           boolean not null default false,
  added_at         timestamptz not null default now(),
  updated_at       timestamptz not null default now(),
  primary key (user_id, league_key),
  constraint user_leagues_team_id     check (team_external_id ~ '^[0-9A-Za-z._-]{1,40}$'),
  constraint user_leagues_name_len    check (length(name) <= 120),
  constraint user_leagues_team_len    check (length(team_name) <= 120),
  constraint user_leagues_scoring_len check (length(scoring_label) <= 160),
  constraint user_leagues_rosters     check (total_rosters between 1 and 64)
);
create unique index if not exists user_leagues_one_default on accounts.user_leagues (user_id) where is_default;
create index if not exists user_leagues_league on accounts.user_leagues (league_key);

create table if not exists accounts.preferences (
  user_id    uuid not null references accounts.users (id) on delete cascade,
  scope      text not null,
  key        text not null,
  value      jsonb not null,
  updated_at timestamptz not null default now(),
  primary key (user_id, scope, key),
  constraint preferences_scope_shape check (scope = 'global' or scope ~ '^(sleeper|mfl|espn|yahoo):[0-9]{4}:[0-9A-Za-z.]{1,40}$'),
  constraint preferences_key_shape   check (key ~ '^[a-z][a-z0-9._-]{0,63}$'),
  constraint preferences_value_size  check (octet_length(value::text) <= 8192)
);

create table if not exists accounts.watchlist (
  user_id    uuid not null references accounts.users (id) on delete cascade,
  league_key text,
  player_key text not null,
  added_at   timestamptz not null default now(),
  constraint watchlist_one_row     unique nulls not distinct (user_id, league_key, player_key),
  constraint watchlist_league_key  check (league_key ~ '^(sleeper|mfl|espn|yahoo):[0-9]{4}:[0-9A-Za-z.]{1,40}$'),
  constraint watchlist_player_key  check (player_key ~ '^([a-z]{2,8}:)?[A-Za-z0-9_.-]{1,40}$')
);

-- ---- IM-4 (Wave I-M): passkeys (WebAuthn) — a second way to sign in, with no email and no third party
-- (docs/ACCOUNTS.md § "Passkeys"; api/league_lab_api/passkeys.py). Two changes to `users`, both idempotent and both
-- keeping every row: a passkey-only account has no email (email becomes optional: the unique constraint and the shape
-- check already let NULL through), and each account gets a WebAuthn user handle (32 random bytes made by the API — never
-- the email) the first time it makes a passkey. Then the credentials and the server-side challenges.
alter table accounts.users alter column email drop not null;
alter table accounts.users add column if not exists webauthn_handle bytea;
create unique index if not exists users_webauthn_handle on accounts.users (webauthn_handle) where webauthn_handle is not null;
do $$ begin
  alter table accounts.users add constraint users_webauthn_handle_len
    check (webauthn_handle is null or octet_length(webauthn_handle) between 16 and 64);
exception when duplicate_object then null;
end $$;

-- One row per passkey: the credential id the authenticator made, its public key (COSE, as the authenticator sent it:
-- public by nature), the signature counter (a counter that goes backwards means a cloned authenticator: refused), the
-- transports the browser reported (a hint for the next sign-in), and a label made from fixed words picked from the
-- browser's User-Agent at creation ("iPhone · Safari") — never the User-Agent itself. Nothing here is a secret: the
-- private key never leaves the person's device.
create table if not exists accounts.passkeys (
  id            uuid primary key default gen_random_uuid(),
  user_id       uuid not null references accounts.users (id) on delete cascade,
  credential_id bytea not null,
  public_key    bytea not null,
  sign_count    bigint not null default 0,
  transports    text[] not null default '{}',
  label         text not null,
  backed_up     boolean not null default false,
  created_at    timestamptz not null default now(),
  last_used_at  timestamptz,
  constraint passkeys_credential_len    check (octet_length(credential_id) between 1 and 1023),
  constraint passkeys_public_key_len    check (octet_length(public_key) between 16 and 2048),
  constraint passkeys_sign_count        check (sign_count between 0 and 4294967295),
  constraint passkeys_transport_words   check (transports <@ array['usb', 'nfc', 'ble', 'internal', 'hybrid', 'smart-card', 'cable']::text[]),
  constraint passkeys_label_len         check (length(label) between 1 and 60)
);
create unique index if not exists passkeys_credential on accounts.passkeys (credential_id);
create index if not exists passkeys_user on accounts.passkeys (user_id);

-- A ceremony's challenge, kept on the server: single use (used_at), 5 minutes (expires_at), stored only as its
-- SHA-256, bound to the browser that asked (browser_hash = SHA-256 of a random value in its HttpOnly `ll_passkey`
-- cookie), to the site it was made for (rp_id, origin: from LEAGUE_LAB_PASSKEY_ORIGINS' allow-list) and to its purpose:
-- `create` (a new account; user_handle = the new account's handle), `add` (the signed-in account `user_id` adds one),
-- `login` (anyone; the passkey names the account). ip_hash = HMAC of the address (the rate limit), never the address.
create table if not exists accounts.passkey_challenges (
  challenge_hash bytea primary key,
  purpose        text not null,
  user_id        uuid references accounts.users (id) on delete cascade,
  user_handle    bytea,
  browser_hash   bytea not null,
  rp_id          text not null,
  origin         text not null,
  ip_hash        bytea,
  created_at     timestamptz not null default now(),
  expires_at     timestamptz not null,
  used_at        timestamptz,
  constraint passkey_challenges_sha256  check (octet_length(challenge_hash) = 32 and octet_length(browser_hash) = 32),
  constraint passkey_challenges_purpose check (purpose in ('create', 'add', 'login')),
  constraint passkey_challenges_owner   check ((purpose = 'add') = (user_id is not null)),
  constraint passkey_challenges_handle  check (purpose = 'login' or octet_length(user_handle) between 16 and 64),
  constraint passkey_challenges_ip_hmac check (ip_hash is null or octet_length(ip_hash) = 32),
  constraint passkey_challenges_site    check (length(rp_id) between 1 and 253 and length(origin) between 8 and 300)
);
create index if not exists passkey_challenges_created on accounts.passkey_challenges (created_at);
-- IM-4 fix: the API counts the new accounts of the last hour and day (its global ceilings) on this index
create index if not exists users_created on accounts.users (created_at);
-- ---- end IM-4

comment on schema accounts is
  'Accounts, phase 1 (Wave I-K, IK-4): sign-in by an emailed link, saved leagues, preferences, watchlist. Never dropped by the nightly; docs/ACCOUNTS.md.';
comment on table accounts.login_links is 'Single-use sign-in links (15 minutes). The token itself is never stored: token_hash = sha256(token).';
comment on table accounts.sessions is 'Server-side sessions (90 days, revocable). The cookie ll_session carries id + HMAC(LEAGUE_LAB_API_SECRET, id).';
comment on table accounts.connections is 'Provider connections (Yahoo OAuth, ESPN, MFL league keys). Reserved: nothing writes it in phase 1.';
comment on table accounts.passkeys is 'Passkeys (WebAuthn, IM-4): credential id, public key, signature counter, a label from fixed words. No secret: the private key stays on the device.';
comment on table accounts.passkey_challenges is 'WebAuthn challenges (IM-4): single use, 5 minutes, stored as sha256, bound to one browser and one site.';

grant usage on schema accounts to league_lab_app;
grant select, insert, update, delete on accounts.users, accounts.login_links, accounts.sessions, accounts.connections,
  accounts.leagues, accounts.user_leagues, accounts.preferences, accounts.watchlist, accounts.passkeys,
  accounts.passkey_challenges to league_lab_app;
revoke truncate, references, trigger on accounts.users, accounts.login_links, accounts.sessions, accounts.connections,
  accounts.leagues, accounts.user_leagues, accounts.preferences, accounts.watchlist, accounts.passkeys,
  accounts.passkey_challenges from league_lab_app;

-- Retention, every run (the sync's "IK-4" block, once a night): links older than a day (used or not: they lived 15
-- minutes; the rate limit reads the last 24 hours), sessions expired or revoked more than a day ago, and a shared league
-- row nobody has saved for a week. A user's own rows go only when the user deletes them or the account.
delete from accounts.login_links where created_at < now() - interval '1 day';
delete from accounts.passkey_challenges where created_at < now() - interval '1 day';     -- IM-4: they lived 5 minutes
delete from accounts.sessions where expires_at < now() - interval '1 day' or revoked_at < now() - interval '1 day';
delete from accounts.leagues l
 where l.updated_at < now() - interval '7 days'
   and not exists (select 1 from accounts.user_leagues u where u.league_key = l.league_key);
