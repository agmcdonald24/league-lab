# The blog (Wave I-N, IN-1; the editor: Wave I-O, IO-3)

Andrew, 2026-10-06: "a **blog section** so I can start writing and sharing analysis" — then "a blog that needs a file
and a push won't get written". A post is written **on the site** (the editor, below) or, as before, as a markdown file
in the repository. The public blog serves both as one list, newest first.

## The editor (Wave I-O, IO-3)

**Who may write.** A signed-in account (passkey or the emailed link: docs/ACCOUNTS.md) whose id is listed in
`LEAGUE_LAB_EDITORS` on the server. No password, no token, no username anywhere. When the variable is unset or empty,
accounts are off, or the `blog` tables are missing, **the editor does not exist**: every editor route answers 404 and
no link to it shows. A signed-in account that is not listed gets 403 (`not_editor`); signed out, 401 (`signed_out`).

**Adding an editor (the PO).** The person signs in on the site, opens **Your account** (⋯ menu) and taps **Copy** under
**Your account id**, and sends it. On Render, set the environment variable (comma-separated account ids, any case,
spaces ignored; anything that is not an id is ignored and logged once):

```
LEAGUE_LAB_EDITORS=<account id>[,<another account id>]
```

A change to it needs a deploy (Render restarts the service). Removing an id takes the editor away at once; that
person's posts stay (they are the site's content; nothing deletes them but the editor's own Delete).

**Writing** (`/blog/new`, `/blog/edit/<id>`; **Write** in the ⋯ menu and **Write a post** on `/blog`, editors only;
`/blog` also lists the editor's own posts, and a published post of theirs shows **Edit**):

| Piece | What it does |
|---|---|
| the fields | title (140), summary (400; the list, the link preview and the feed show it), tags (8 of 32: letters, numbers, spaces, dashes), the author line (60; empty = the site's name; a new post starts with the last one used), the address (`/blog/<slug>`: follows the title until typed; the files' pattern, ≤ 80; a published post keeps its address) |
| the body and the preview | markdown, with a live preview through `lib/md.ts` `mdDoc` in `components/blog/PostBody.svelte` — the public post's own renderer (escaped first; no raw HTML path, no second renderer). Side by side from 900 px, a **Write / Preview** switch below. The preview waits 150 ms after typing (400 ms past 20 KB): typing in a 20 KB post measured 9.7 ms a key on this box |
| the toolbar | Bold, Heading, List, Quote, Link, Table; **Player** (search → `[Name](/player/<gsis>)`); **Players table** (pick up to 12 players and up to 8 Stats columns → the ```` ```players ```` block below) |
| saving | a **draft saves itself** 2.5 s after the last change (`PUT … autosave: true`); the unsent text is also kept on the device (`localStorage` `ll.blog.draft.<id>`, in a try / catch) and offered back on the next visit ("Put it back") when the server never got it. A **published** post saves only on **Save changes** (readers never see half a sentence) |
| two tabs, one post | every save carries the revision it edited; a stale one is **409** with the newer post, shown as "This post was changed in another tab or on another device … Nothing was overwritten." with **Use the newer version** / **Keep mine and save it over** — never a silent overwrite |
| revisions | the last 20 bodies of each post (`blog.revisions`); autosaves within two minutes of the last autosave fold into one row, an explicit save is always its own (so 20 reach back at least 40 minutes of typing). **Earlier versions** lists them (date, size); **Put this one back** loads one into the editor, where it saves as a new version — nothing earlier is lost |
| Publish / Unpublish / Delete | publish needs a title and an address no file holds; the first publish sets the post's date (a republish keeps it). Unpublish → a draft. Delete → **Deleted**, restorable for 30 days (**Restore as a draft**), then gone with its revisions (the API prunes on its writes; the nightly's script too). After publishing: "Live at /blog/<slug>" with **Copy link** |
| **New post from…** | three starters on an empty new post fill a **draft** from the live routes on Half PPR, as plain markdown with the numbers written in and "*As of <date>, week N. The numbers are written in: they will not change after this is published.*", with "*Your take: …*" where his words go: **Matchups to target and avoid** (the matchup board's favorable and difficult WR and TE: projection, 10th–90th range, the defense's and the corner's sentence, the board's own words on what the tone assumes), **This week's top projections and their ranges** (the board's top 8 at QB, RB, WR, TE in a table), **Players whose role is changing** (the DFS board's role signal, up and down; DraftKings' list is only the source of the role words — no DFS points are written). A starter never publishes |
| pictures | **Picture** uploads one from the device: PNG, JPEG or WebP **by its first bytes** (the name and the declared type are never trusted; an SVG or an HTML file named `.png` is refused), ≤ 300 KB, ≤ 50 on the blog; stored in `blog.images`, served at `/blog/img/db/<id>` (`image/png` / `image/jpeg` / `image/webp` as the bytes say, `nosniff`, a year's cache — an id is never reused); the editor inserts `![file name](/blog/img/db/<id>)` and lists the pictures uploaded before (Insert, Delete). A file in `blog/img/` in the repository works as before. `mdDoc` accepts exactly these two forms of picture address |
| **Download every post** | `GET /api/blog/export`: one zip of `blog/<date>-<slug>.md` files with the files' own front matter (`title`, `date`, `summary`, `author`, `tags`, `draft: true` for a draft; values quoted), the editor's posts that are not deleted. `blog.parse_post` reads each back to the same post (tested): his way out, and the backup |

**Routes** (behind the beta gate like every `/api/`; JSON; `no-store`; errors `{error, detail, code}`; `blog_store.py`):

| Route | Answer | Bucket |
|---|---|---|
| `GET /api/blog/mine` | `{account_id, author, posts: [{id, slug, title, summary, tags, author, status, revision, date, created_at, updated_at, published_at, deleted_at, minutes, bytes}], limits}` (no bodies) | read |
| `GET /api/blog/posts/{id}` · `…/revisions/{n}` | the post with `body` and `revisions: [{id, revision, saved_at, bytes}]` · one revision's `{revision, title, body, saved_at}` | read |
| `POST /api/blog/posts` | 201, a new draft (the address from the title, `-2`, `-3` … when taken) | write |
| `PUT /api/blog/posts/{id}` `{title, summary, tags, author, body, slug, revision, autosave, slug_auto}` | the saved post; 409 `conflict` + `post` (the newer one) when `revision` is stale; a typed address that cannot be taken leaves the old one and says why (`slug_problem`: `shape` / `reserved` / `taken_by_file` / `taken` / `published`, `slug_words`) — the text is saved all the same; an address made from the title (`slug_auto`) moves on to the next free one (`-2`, `-3` …) without a word | write |
| `POST …/{id}/publish` `{revision}` · `…/unpublish` · `…/restore` · `DELETE …/{id}` | the post; 400 `no_title`, 409 `slug_taken` / `deleted` / `not_published` / `not_deleted` / `conflict` | write |
| `GET /api/blog/export` | `application/zip`, `Content-Disposition: attachment; filename="isuckatfantasy-blog-<date>.zip"` | research (CPU slots) |
| `POST /api/blog/images` (the picture as the body, any content type) · `DELETE /api/blog/images/{id}` | 201 `{id, url, kind, size, created_at}`; 400 `bad_image`, 413 `too_big`, 409 `too_many_images` · `{ok}`, 404 `no_image`. `GET /api/blog/mine` lists `images` | write |
| `GET /blog/img/db/{id}` (public, never gated) | the picture; 404 for anything but a stored lower-case uuid, and without the table | read (`/blog/img/` prefix) |

Every route: 404 `not_found` without an editor on the server, 401 `signed_out`, 403 `not_editor`; every write also the
same-site rule (`accounts.same_site`, IM-3's Guard first: 403 `cross_site`), the limiter's `write` bucket and 60 changes
a minute per session (429 `rate_limited`). Ids are checked as lower-case uuids before any query; an editor reads and
writes only the posts their account wrote.

**Limits** (`blog_store.py`): a body ≤ 200 KB (UTF-8; 413 `too_big` in words up to the Guard's 256 KB, which refuses
anything bigger first), no control characters but tab and newline (400 `bad_body`; a paste's line separators — `\r`,
U+2028, U+2029, form feed — become line ends, and in a one-line field spaces); ≤ 500 posts (409 `too_many`); a picture ≤
300 KB (the Guard's bound for `/api/blog/images` is 320 KB: `security.body_limit`), ≤ 50 pictures; ≤ 30 MB in all —
posts, revisions and pictures together (413 `blog_full`); the last 20 revisions of a post. Words a post's address may not be: `new`,
`edit`, `mine`, `export`, `posts`, `rss`, `img`, `editor`, `drafts`, `db`, `feed`, `write`.

**Stored** (`scripts/hosted_blog.sql`, schema `blog`, idempotent; the nightly's sync runs it after the publish, which
never drops it): `blog.posts` (id, slug unique, title, summary, body, body_bytes, minutes, tags, author, status `draft` /
`published` / `deleted`, account_id — no foreign key: a post stays when its writer's account is deleted —, revision,
created_at, updated_at, published_at, deleted_at; checks on every length and the status), `blog.revisions` (post_id
→ posts on delete cascade, revision, title, body, body_bytes, autosave, saved_at) and `blog.images` (id, kind `png` /
`jpg` / `webp`, bytes, size ≤ 307,200, account_id, created_at). The app role gets SELECT, INSERT, UPDATE, DELETE on the
posts and revisions (and the revisions' sequence), SELECT, INSERT, DELETE on the pictures and writes in its own read-write transaction
(`db.run_rw`, purpose `blog`). Size on Neon: a 20 KB post with 20 revisions is ~400 KB before TOAST compression; the
hard ceiling is ~32 MB (the 30 MB cap plus rows and indexes).

**The public side.** `blog.posts()` = the files' posts + the published database posts (`blog_store.published_meta`:
no bodies, one query a minute per process, cleared by this process's writes), newest first by date then slug; a
database post's body is read on demand (`published_body`, only for a slug from that list — a closed set; 40 bodies at
most in the memory budget's region `blog_db`, plus at most 20 pictures once they have been asked for: ≤ 14 MB). The list, a post, RSS, the sitemap and the shell's meta tags all
read `posts()`: a published database post unfurls, is in the feed and the sitemap like a file. A slug a file holds is
the file's: the editor cannot save or publish it, and a published database post that later meets a newer file with its
slug is left out (logged). With the table there, `/api/blog` and a post answer `public, max-age=0, must-revalidate` (a
post published a moment ago shows on the next load); without it, today's five minutes.

**Without the tables or the variable (the deploy before the nightly).** No `blog` schema, no right to read it, or the
database down: `published_meta()` is `[]`, the readiness check says no — the blog is exactly the files' (same list,
same headers), the editor's routes are 404 and no Write link shows (`test_io3`: the tables pointed at absent names,
the database down). `LEAGUE_LAB_EDITORS` unset: the same, whatever the tables.

**Tests.** `api/tests/test_io3.py` (15): every editor route 404 with no editors / accounts off / the tables missing, 401
signed out (and a forged cookie), 403 not an editor, cross-site refused on every write (`Origin` elsewhere, `Origin:
null`, `Sec-Fetch-Site: cross-site`), the flow (create, two-tab conflict, publish, the public list / post / RSS /
sitemap, unpublish, delete, restore, revisions), another editor's posts invisible, the address rules and the file
collision, hostile text in every field through the JSON, RSS, the sitemap and the shell's meta tags, every limit, the
export round trip, the buckets, the script. `web/e2e/io3/fixtures.spec.ts` (at 375 and 1300, against the real API on
:8863 that the spec starts with a throwaway secret and an editor made through the accounts code): write → preview →
publish → the public post → unpublish → delete, every hostile shape inert in the preview and the post, a starter, two
tabs, a dropped connection, typing in a 20 KB post, a visitor with no Write, the account id.

## Posts as files (Wave I-N, IN-1)

Posts are also markdown files in this repository; a push to `main` publishes them with the next deploy. Writing one:
`blog/README.md` (the file name, the front matter, pictures, `draft: true`) and `blog/_template.md`. The editor's
**Download every post** gives files in this same form.

### How the files are read

| Piece | Where | What it does |
|---|---|---|
| the posts | `blog/<yyyy-mm-dd>-<slug>.md` (+ `blog/img/`) | one file per post: a front matter (`title` required; `date`, `summary`, `author` — default "isuckatfantasy" —, `tags`, `draft`, `image`) and the body in markdown. `README.md`, `_template.md` and anything off the name pattern are not posts. |
| the reader | `api/league_lab_api/blog.py` | reads the folder (`LEAGUE_LAB_BLOG_DIR`, default `<repo>/blog`; `/srv/blog` in the image) into an index: one entry of the memory budget (`league_lab.memo` region `blog`, at most 4 entries — folder × drafts switch —, one hour), re-read after that. No YAML engine: `key: value` lines only. |
| `GET /api/blog?limit=` | `blog.py` | `{"posts": [{slug, title, date, summary, author, tags, minutes, image}]}`, newest first; `limit` 1–50 (default 20; anything else 400). Bucket `read`. |
| `GET /api/blog/{slug}` | `blog.py` | the post's meta + `markdown`; 404 `{"error": "No post at that address.", "code": "no_post"}`. The slug must match `^[a-z0-9]+(-[a-z0-9]+)*$` (≤ 80) and is then looked up in the index — nothing from the URL is ever opened. Bucket `read`. |
| `GET /blog/rss.xml` | `blog.py` | RSS 2.0, the newest 20; every text escaped. Bucket `read` (`ratelimit.PAGES_READ`). |
| `GET /blog/img/{name}` | `blog.py` | a picture from `blog/img/`: the name `^[a-z0-9][a-z0-9_-]{0,79}\.(png|jpg|jpeg|webp)$`, its first bytes must be that format's (an HTML file named `.png` is refused), ≤ 2 MB, no link, cached 30 days. **SVG is refused** (it can carry script). Bucket `read`. |
| `GET /sitemap.xml` | `blog.py` | `/`, `/home`, `/blog`, each post (its date as `lastmod`), `/players`, `/matchups`, `/trade-calc`, `/dfs`. `web/public/robots.txt` points at it. |
| link previews | `blog.py` `shell` + `main.py`'s SPA fallback | the HTML shell's head between `<!-- ll:seo -->` and `<!-- /ll:seo -->` (in `web/index.html`) is replaced per path: `<title>`, `description`, `canonical`, `og:title` / `description` / `type` / `url` / `image` (+ size), `twitter:card` `summary_large_image`, a post's `article:published_time`; text escaped, built from the post's meta, the origin `https://isuckatfantasy.io`. `/`, `/home`, `/blog`, `/blog/<slug>` (an unknown one: the blog's preview with status **404**), `/players`, `/matchups`, `/trade-calc`, `/dfs`; every other path gets the file as it is. `/` keeps the title `isuckatfantasy` (the image workflow greps it). The inline prefetch script is outside the block, so the CSP's hash (`security.py`) still matches (`test_in1`). |
| the share image | `web/public/og.png` | 1200 × 630, the brand (a Playwright screenshot of a small HTML card; to remake it, render a 1200 × 630 page and save the PNG under the same name — previews cache it, so a new design may take a new name and a line in `blog.py` `DEFAULT_IMAGE`). A post's `image:` replaces it for that post. |
| the screens | `web/src/routes/Blog.svelte`, `components/blog/PostBody.svelte` | `/blog` (the list, an aside: about, RSS, the tools) and `/blog/<slug>` (the title, "By … · date · N min read", **Copy link**, the body at a readable measure — 44rem — beside the aside from 900 px, more posts). In the frame (tabs, search, the drawer): a player link opens his card like everywhere. The menu (⋯) has **Home** and **Blog**. |
| the renderer | `web/src/lib/md.ts` `mdDoc` | escapes every character first, then adds only its own tags: headings (`#` and `##` → h2, `###` → h3 …), paragraphs, **bold**, *italic*, `code`, fenced code, `- ` and `1. ` lists, `> ` quotes, tables (alignment from the separator row; inside a box that scrolls sideways by itself), `---`, links (in-app paths and https to the hosts `md` already trusts; others become text), pictures from `/blog/img/` only. Raw HTML is shown as text. `md()` (the sentences) is unchanged. |
| analytics | `App.svelte` → `lib/analytics.ts` | a `page_view` per post (its path `/blog/<slug>`; a post to another post counts); the usage count's screens `home`, `blog`, `post` (`usage.SCREENS`). |
| drafts | `LEAGUE_LAB_BLOG_DRAFTS=on` | lists and serves `draft: true` posts (marked **Draft**) — for a preview on a laptop; never set it on Render. |

### Limits of a file post (all in `blog.py`)

300 posts (the newest), 200 KB a post, 140 characters a title, 400 a summary, 8 tags of 32, 80 characters a slug, 2 MB
a picture. A post over a limit is skipped and logged (`blog: … skipped`), never served half. Two files with one slug:
the newer file is served, the older is logged. A post's `date` is shown as written (a future date is not held back:
`draft: true` is the way to hold one).

### Publishing a file

1. Write `blog/<today>-<slug>.md` from `_template.md`; pictures in `blog/img/`.
2. Optional: `LEAGUE_LAB_BLOG_DRAFTS=on` with the app running locally, open `/blog`.
3. Remove `draft: true`, commit, push. The deploy serves it; the link previews and the sitemap follow by themselves.

**The image needs the folder**: `api/Dockerfile` copies `blog/` to `/srv/blog` (the PO's line:
`COPY blog /srv/blog`). Without it the blog is empty on the server (an absent folder is an empty blog, never an error).

## The players block (both kinds of post)

The first ```` ```players ```` fence of a post — gsis ids and column ids, one per line or `cols: a, b`, at most 12
players and 8 columns — becomes those players' rows of the Stats frame on Half PPR, season to date, per game, in the
Stats screen's own table (`components/blog/PlayersBlock.svelte`; the Stats screen's request
`/api/players?league=ref:half&position=ALL&window=season&limit=1000`, cached like it). Without `cols:` it shows games,
points, targets, share of team passes and receiving yards; an unknown or unavailable column is left out; an id with no
game this season is counted under the table ("Not in this season's table yet: 1 player"), never a row of zeros. A
second fence stays a code block. The numbers move with every nightly: the block says "Live: this season to date".

## Not built

* Comments, search, tag pages, a newsletter, scheduled posts.
* ---- IO-3: a post's `image:` (its link-preview picture) exists for files only; a database post previews with `og.png`
  (a picture uploaded from the editor shows in the post, not in the link preview).
* ---- IO-3: the players block's numbers are live (they move with the nightly) even in a post written from a starter —
  the starter's own numbers are written in as text; the block is the one live thing, and it says so.
* ---- IO-3: RSS and the sitemap keep their 10-minute cache: a post published now reaches a feed reader within 10 minutes.
* The copy standard's sweep (`scripts/copy_standard.py`) does not read `blog/` (its globs are the code and WORDS); a
  post follows `docs/WORDS.md` by hand.
