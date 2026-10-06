-- League Lab blog store (Wave I-O, IO-3; docs/BLOG.md § "The editor"). Plain SQL, idempotent.
--
-- Two tables: blog.posts (one row per post written on the site: its slug, title, summary, markdown body, tags, author,
-- status draft / published / deleted, who wrote it, a revision number) and blog.revisions (the last 20 saved bodies of
-- each post, so a lost draft can be found again). The public blog serves these posts' published rows beside the
-- markdown files in blog/ (api/league_lab_api/blog.py); the editor writes them (api/league_lab_api/blog_store.py).
--
-- The schema `blog` is NOT one the sync replaces: scripts/sync_to_hosted.sh drops and restores analytics,
-- analytics_seeds and ops only, then runs this file — so the posts survive every nightly. The read-only app role keeps
-- `default_transaction_read_only = on`; it gets SELECT, INSERT, UPDATE and DELETE on these two tables (the API's writer
-- opens its own `BEGIN; SET TRANSACTION READ WRITE; ...; COMMIT`: db.run_rw, purpose "blog") and nothing else here.
-- No foreign key to accounts.users: a post is the site's content and stays when its writer's account is deleted.
--
-- Size: the API refuses a body over 200 KB, more than 500 posts, and more than 30 MB of bodies in all (posts and
-- revisions together), so the schema stays under ~32 MB on Neon whatever happens; a real blog is a few hundred KB.
--
-- Run it as the database owner:
--   hosted:  the sync does it every night (LEAGUE_LAB_HOSTED_ADMIN_URL, the Neon owner role)
--   local:   psql "$(uv run python -c 'from league_lab.config import get_settings; print(get_settings().pipeline_dsn())')" \
--                 -v ON_ERROR_STOP=1 -f scripts/hosted_blog.sql
--            (the pipeline role owns the Mac's database; on a database it does not own, run it as the owner)

set client_min_messages = warning;    -- a re-run's "already exists, skipping" notices stay out of the nightly's log
create schema if not exists blog;

create table if not exists blog.posts (
  id            uuid primary key default gen_random_uuid(),
  slug          text not null,
  title         text not null default '',
  summary       text not null default '',
  body          text not null default '',
  body_bytes    integer not null default 0,
  minutes       integer not null default 1,
  tags          text[] not null default '{}',
  author        text not null default '',
  status        text not null default 'draft',
  account_id    uuid not null,
  revision      integer not null default 1,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  published_at  timestamptz,
  deleted_at    timestamptz,
  constraint posts_slug_unique     unique (slug),
  constraint posts_slug_shape      check (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$' and length(slug) <= 80),
  constraint posts_status_word     check (status in ('draft', 'published', 'deleted')),
  constraint posts_title_length    check (length(title) <= 140),
  constraint posts_summary_length  check (length(summary) <= 400),
  constraint posts_author_length   check (length(author) <= 60),
  constraint posts_body_size       check (octet_length(body) <= 204800 and body_bytes = octet_length(body)),
  constraint posts_tags_count      check (coalesce(array_length(tags, 1), 0) <= 8),
  constraint posts_minutes_range   check (minutes between 1 and 10000),
  constraint posts_revision_pos    check (revision >= 1),
  constraint posts_published_when  check (status <> 'published' or published_at is not null),
  constraint posts_deleted_when    check (status <> 'deleted' or deleted_at is not null)
);
create index if not exists posts_status_published on blog.posts (status, published_at desc);

create table if not exists blog.revisions (
  id          bigserial primary key,
  post_id     uuid not null references blog.posts (id) on delete cascade,
  revision    integer not null,
  title       text not null default '',
  body        text not null default '',
  body_bytes  integer not null default 0,
  autosave    boolean not null default false,
  saved_at    timestamptz not null default now(),
  constraint revisions_body_size check (octet_length(body) <= 204800 and body_bytes = octet_length(body)),
  constraint revisions_title_length check (length(title) <= 140)
);
create index if not exists revisions_post_saved on blog.revisions (post_id, saved_at desc);

comment on table blog.posts is
  'Blog posts written on the site (Wave I-O, IO-3): slug, title, summary, markdown body, tags, author, status draft / published / deleted (restorable for 30 days), the writing account, a revision number for the editor''s conflict check.';
comment on table blog.revisions is
  'The last 20 saved bodies of each blog post (Wave I-O, IO-3), at most one every two minutes while autosaving.';

grant usage on schema blog to league_lab_app;
grant select, insert, update, delete on blog.posts to league_lab_app;
grant select, insert, update, delete on blog.revisions to league_lab_app;
grant usage on sequence blog.revisions_id_seq to league_lab_app;
revoke truncate, references, trigger on blog.posts, blog.revisions from league_lab_app;

-- Retention (every run; the API also prunes when it writes): a deleted post is restorable for 30 days, then gone with
-- its revisions (on delete cascade); revisions beyond the newest 20 of a post go. Re-running deletes nothing more.
delete from blog.posts where status = 'deleted' and deleted_at < now() - interval '30 days';
delete from blog.revisions r
 where r.id in (select id from (select id, row_number() over (partition by post_id order by saved_at desc, id desc) n
                                  from blog.revisions) k where k.n > 20);
