# IO-3 — the blog editor (Wave I-O, Iteration 25)

**Task**: Wave I-O package IO-3 (`/home/claude/waveIO/BRIEF.md` § "IO-3 — the blog editor"). **Branch**: `dev/IO3` from
`main` `cf8e743`. **Database**: `league_lab_im4`, schema `blog` only (applied with the pipeline role, as the header of
`scripts/hosted_events.sql` shows); test rows in `accounts` only through the app's own code paths (`@io3.test`
addresses, deleted after each run). No dbt, no other schema, nothing outside.

## Done, against the numbered list

1. **Storage** — `scripts/hosted_blog.sql` (idempotent, applied twice in the tests): `blog.posts` (id, slug unique,
   title, summary, body, body_bytes, minutes, tags, author, status draft / published / deleted, account_id, revision,
   created / updated / published / deleted at; a check on every length and the status), `blog.revisions` (the last 20
   bodies per post; autosaves within two minutes fold into one row, an explicit save never does), `blog.images` (item
   5's upload). Limits: body ≤ 200 KB, ≤ 500 posts, ≤ 30 MB in all (posts + revisions + pictures). The public reads
   (`GET /api/blog`, `/api/blog/{slug}`, RSS, the sitemap, the shell's meta) serve file posts and published database
   posts as one list, newest first (`blog.posts()`); a slug a file holds cannot be saved or published. Without the
   tables the blog is exactly today's (tested: same list, same `public, max-age=300`).
2. **Who may write** — an account listed in `LEAGUE_LAB_EDITORS` (comma-separated account ids; case and spaces do not
   matter; a non-id is ignored and logged once). Unset / empty, accounts off, or the tables missing: every editor route
   is 404 — the switch is the router's **first dependency**, so even a wrong body is 404, not a 422 — and no link shows.
   Signed out 401, not an editor 403, a forged cookie 401. The Account screen shows **Your account id** with Copy
   (`components/blog/AccountId.svelte`; `GET /api/account/me` gains `id`). Every write: signed in, an editor, the Guard's
   cross-site rule + `accounts.same_site`, the `write` bucket + 60 changes a minute per session, validated.
3. **Routes** — `GET /api/blog/mine`, `POST /api/blog/posts`, `PUT /api/blog/posts/{id}` (carries `revision`: stale →
   409 with the newer post, never a silent overwrite), `POST …/{id}/publish`, `…/unpublish`, `…/restore`, `DELETE …/{id}`
   (deleted, restorable 30 days, then pruned with its revisions), `GET /api/blog/export` (one zip of `blog/<date>-<slug>.md`
   in the files' own front matter; `blog.parse_post` reads each back to the same post — tested), plus
   `GET /api/blog/posts/{id}`, `…/revisions/{n}`, `POST /api/blog/images`, `DELETE /api/blog/images/{id}`, public
   `GET /blog/img/db/{id}`. Buckets: export `research`; writes `write`; reads `read`; pictures `read` (the `/blog/img/` prefix).
4. **The editor** — `/blog/new`, `/blog/edit/<id>` (`routes/BlogEditor.svelte`, its own chunk); **Write** in the ⋯ menu
   and **Write a post** + **Your posts** on `/blog`, **Edit** on a published post — editors only. Title, summary, tags,
   author line (defaults to the last one used), address; the body with a live preview through `mdDoc` (the public post's
   own `PostBody.svelte`: no second renderer, no raw HTML path), side by side from 900 px, Write / Preview below; toolbar
   Bold, Heading, List, Quote, Link, Table, **Player** (search → `[Name](/player/<gsis>)`), **Players table** (players +
   Stats columns → the ```` ```players ```` block), **Picture**; autosave 2.5 s after the last change for a draft (a
   published post: **Save changes**), the unsent text kept on the device (`localStorage`, try / catch) and offered back;
   the two-tab conflict in words with **Use the newer version** / **Keep mine and save it over**; **Earlier versions**
   (put one back); Publish / Unpublish / Delete (two taps) / Restore; after publishing "Live at /blog/<slug>" + **Copy
   link**; **Download every post**; an address made from the title moves on to `-2` by itself when taken. Typing in a
   20 KB post: 3.9–9.7 ms a key across runs (the preview is debounced
   150 ms, 400 ms past 20 KB).
5. **Starters** — **New post from…**: *Matchups to target and avoid* (the board's favorable / difficult WR and TE with
   the defense's and the corner's sentence and the board's own words on what the tone assumes), *This week's top
   projections and their ranges* (QB / RB / WR / TE tables, 10th–90th), *Players whose role is changing* (the DFS
   board's role signal, up / down — DraftKings' list is only the source of the role words; no DFS points written). Half
   PPR, plain markdown with the numbers written in, "*As of <date>, week N …*", "*Your take: …*"; a draft, never
   published by itself. Text from the API is neutralised for `mdDoc` (`starters.ts` `mdText`: no link, bold, table cell
   or block marker can come from a name or a sentence). **Pictures: the upload shipped** — PNG / JPEG / WebP by their
   first bytes (an SVG or HTML named `.png` refused), ≤ 300 KB, ≤ 50, `blog.images`, served at `/blog/img/db/<id>` with
   the type the bytes say, `nosniff`, a year's cache; `mdDoc` accepts exactly that address besides `blog/img/` files.
6. **Tests and docs** — below; `docs/BLOG.md` rewritten (the editor first, files second, adding an editor), WORDS §
   "The blog editor", CHANGELOG.

## Not done / limits

* A database post's link-preview picture is `og.png` (a file post's `image:` has no editor field yet).
* RSS and the sitemap keep their 10-minute cache (a feed reader sees a new post within 10 minutes).
* A body that is not JSON at all is FastAPI's 422 before the editor's switch is read (it parses first); every other
  request to an editor route is 404 when there is no editor.
* `PATCH` (no such route) on an editor path is 405, as for any path with other methods.
* An editor sees only the posts their account wrote; the export is that editor's posts.
* The players block in a starter's post is live (it moves with the nightly) and says so; the starter's own numbers are
  written in.

## Files

New: `api/league_lab_api/blog_store.py`, `scripts/hosted_blog.sql`, `api/tests/test_io3.py`,
`web/src/routes/BlogEditor.svelte`, `web/src/components/blog/{editor.svelte.ts, starters.ts, AccountId.svelte}`,
`web/e2e/io3/fixtures.spec.ts`, `docs/handbacks/io3/*.png`, this file. Mine, edited: `api/league_lab_api/blog.py`,
`web/src/routes/Blog.svelte`, `web/src/lib/md.ts` (one regex: the uploaded pictures' address), `docs/BLOG.md`, a marked
line (+ its import) in `web/src/routes/Account.svelte`.

**Edits outside my files** (marked `IO-3`): `api/league_lab_api/ratelimit.py` (`/api/blog/export` → research),
`api/league_lab_api/accounts.py` (`me_route`: `"id": uid`, one line), `api/league_lab_api/security.py` (`body_limit`:
320 KB for `/api/blog/images`, two lines), `api/tests/test_ik4.py` + `web/fixtures/ik4/me.json` (the recorded `me`
answer gains a fixed `id`), `web/src/lib/router.svelte.ts` (route `write`: `/blog/new`, `/blog/edit/<id>` ahead of the
post pattern), `web/src/App.svelte` (the editor's chunk; `openDoor` + `write`), `web/src/components/TopBar.svelte` (the
⋯ menu's **Write**, editors only), `docs/WORDS.md`, `CHANGELOG.md`. `main.py`: none (the routes ride on blog.py's
router; `mine` and `export` are declared ahead of `/api/blog/{slug}`).

## Schema in / out

In: `accounts.users` / `accounts.sessions` (who is signed in, via `accounts.current_user`); the matchup board, the
DFS projections and the Stats frame (the starters and the players table, through their public routes). Out: schema
`blog` — empty 384 kB on this database (tables, indexes, TOAST); a 20 KB post with 20 revisions ≈ 420 KB before TOAST
compression; hard ceiling ≈ 32 MB (the 30 MB cap + rows and indexes) on Neon's 0.5 GB.

## The PO lines

`scripts/sync_to_hosted.sh`, after the IK-4 block:

```bash
# ---- IO-3 (Wave I-O): the blog's editor — docs/BLOG.md § "The editor". The `blog` schema is never dropped above (only
# analytics, analytics_seeds and ops are); scripts/hosted_blog.sql creates blog.posts, blog.revisions and blog.images if
# missing, grants the app role SELECT / INSERT / UPDATE / DELETE on posts and revisions and SELECT / INSERT / DELETE on
# images (its default_transaction_read_only stays on) and prunes posts deleted 30 days ago and revisions past the newest
# 20. Idempotent, a few ms, its own transaction after IK-4, the same owner connection (no new secret). A failure here
# never fails the publish: the blog stays the files' and the editor off until a sync applies it.
if psql "$LEAGUE_LAB_HOSTED_ADMIN_URL" -v ON_ERROR_STOP=1 -q --single-transaction -f scripts/hosted_blog.sql; then
  echo "blog: $(psql "$LEAGUE_LAB_HOSTED_ADMIN_URL" -At -c "select (select count(*) from blog.posts where status = 'published') || ' published, ' || (select count(*) from blog.posts) || ' posts, ' || (select count(*) from blog.images) || ' pictures, ' || pg_size_pretty((select sum(pg_total_relation_size(c.oid)) from pg_class c join pg_namespace n on n.oid = c.relnamespace where n.nspname = 'blog' and c.relkind = 'r')::bigint)" 2>/dev/null || echo '?')"
else
  echo "WARNING: scripts/hosted_blog.sql failed: the blog stays the files' and the editor off until a sync applies it (the publish itself is fine)" >&2
fi
# ---- end IO-3
```

(Checked on `league_lab_im4`: "blog: 0 published, 0 posts, 0 pictures, 384 kB".)

`render.yaml`, in the service's `envVars` (the value is one or more account ids — a uuid each, any case, joined by
commas — that the editor copies from **Your account** → **Your account id**; `sync: false` keeps the id out of git):

```yaml
      # ---- IO-3 (Wave I-O): the blog's writers — comma-separated account ids ("Your account id" on the Account screen);
      # unset or empty: no editor on the site (docs/BLOG.md § "The editor")
      - key: LEAGUE_LAB_EDITORS
        sync: false     # Render asks for it: e.g. 0f1e2d3c-4b5a-4968-8776-5a4b3c2d1e0f[,another id]
```

`scripts/nightly.sh`, `api/Dockerfile`: nothing.

## New environment variables, dependencies

`LEAGUE_LAB_EDITORS` (above). No new dependency (zip: the standard library; the picture check: the first bytes, as
`blog.py` already does).

## Commands and evidence

* `uv run pytest api/tests/test_io3.py` — **18 passed**; with the files of every module edited: `test_io3 test_in1
  test_im3 test_static test_ik4 test_im4` — **154 passed** (`test_ik4::test_record_web_fixtures` updated on purpose for
  the new `id`). `test_il5::test_watchlist_rows_in_a_league` fails on `main` too (the week's state), untouched.
* `uv run ruff check src app tests api` — clean. `uv run python scripts/copy_standard.py --check` — clean.
* `cd web && npm run lint && npm run build` — clean (193 files, 0 errors, 0 warnings).
* `FIXTURES_PORT=8830 npx playwright test --config playwright.fixtures.config.ts e2e/io3` — **12 passed**, 6 skipped
  (desktop-only checks skip on the phone) at 375 and 1300; the spec starts its own API on :8863 with a throwaway secret
  and an editor made through `accounts.request_link` → the stub mailer → `accounts.verify`, and deletes it after.
  `e2e/in1` + `e2e/ik4` — **22 passed** (4 skipped, as on main).
* Screenshots: `docs/handbacks/io3/` (editor, post, list, account at 375 and 1300; starter, conflict at 1300; picture).

## What I attacked, and what happened

TestClient (through the Guard and the limiter) and a live run of the fixture API on :8863 with curl:

| Attack | Result |
|---|---|
| every editor route with `LEAGUE_LAB_EDITORS` unset / empty / `" , "` (signed in), accounts off, the tables missing | 404 `not_found` on all 12 (a wrong body too) |
| signed out, a forged `ll_session`, signed in but not listed | 401, 401, 403 `not_editor` on all |
| cross-site writes: `Origin: https://evil.example`, `Origin: null`, `Sec-Fetch-Site: cross-site`; a text/plain form post | 403 `cross_site` (the Guard); text/plain without Origin: 422 (not JSON), nothing written |
| another editor's post by id (read, save, publish) | 404 |
| stored XSS in title, summary, author, tags, slug, body (script, `onerror`, `javascript:` / `data:` / `//host` / `/\host` links, attribute breaking in a link and a picture, an outside picture, `<td onclick>`, `</code><script>`, `</pre><script>` in a fence, entities, the placeholder characters U+E000 / U+E001) | tags refused (400); the rest stored as typed and inert: the JSON is `application/json` + nosniff; RSS parses with only the feed's elements; the sitemap carries the slug only; the shell's head has the title escaped once (`&lt;script&gt;`); the preview and the public post: no script / iframe / svg / style element, no `on*` attribute, links only in-app or https to the allowed hosts, pictures only `/blog/img/` (e2e `inert` at 375 and 1300) |
| oversized: 200 KB + 1 byte, 240 KB, 300 KB / 400 KB requests | 413 `too_big` in words; the Guard's 413 past 256 KB |
| 30 MB / 500-post / 50-picture caps (lowered in the test) | 413 `blog_full`, 409 `too_many`, 409 `too_many_images` |
| control characters (NUL, ESC), pasted U+2028 / form feed / CR | NUL / ESC refused 400; line separators become line ends (an autosave never fails on a paste) |
| slug collisions: a file's slug, reserved (`new`, `edit`, `mine`, `export` …), shape (`Bad Slug`, `a--b`, 81 chars, `o\nk`, `../etc`), another post's; a file pushed later with a published post's slug | the text saved, the address kept and the reason given; publish 409 `slug_taken`; the file wins in every public read, logged |
| the revision conflict (two tabs) | 409 `conflict` + the newer body; the UI offers both ways, nothing overwritten (API test + e2e) |
| pictures: SVG / HTML / GIF named `.png`, 4 bytes, empty, 300 KB + 8, 330 KB; `/blog/img/db/` with `..%2F`, an upper-case id, `x.png`, `%0a` | 400 `bad_image`; 413; 413 (Guard); 404 for every address but a stored lower-case uuid; served with the type its bytes say + nosniff |
| `/blog/new` and `/blog/edit/<id>` opened directly | 200 with the blog's preview (never the 404 an unknown slug gets) |

Fixed while attacking: a body between 200 and 256 KB answered pydantic's 422 (echoing the body) → now 413 in words; the
switch ran after body validation (a 422 could reveal the routes) → now the router's first dependency; the phone preview
overflowed its column (a grid item's min-width) → `minmax(0,1fr)` + a bounding-box check in the e2e; pasted line
separators refused an autosave → normalised.

## Without the schema or the variable (the deploy before the nightly)

No `blog` schema (or no right to it, or the database down): `published_meta()` is `[]` and the readiness check says no
— `/api/blog`, a post, RSS, the sitemap and the shell are exactly the files' (same headers: `public, max-age=300`), the
editor's routes are 404, `/blog/img/db/*` is 404, no Write link. With the schema: the list and a post answer
`public, max-age=0, must-revalidate` so a post just published shows on the next load. `LEAGUE_LAB_EDITORS` unset: the
editor does not exist whatever the tables. Tested: `test_without_the_tables_*`, `test_the_database_down_leaves_the_files`.

## Wrong and not mine

* `test_il5::test_watchlist_rows_in_a_league` fails on `main` (rostered vs free_agent: the sandbox's week state).
* Running `e2e/in1` rewrites `docs/handbacks/in1/home-desktop.png` (its screenshot path is fixed); I restored it each time.

## Next

The editor's link-preview picture for a database post (an `image` field pointing at an uploaded picture); a feed / sitemap
cache that clears on publish; "Earlier versions" with a diff.
