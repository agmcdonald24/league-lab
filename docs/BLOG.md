# The blog (Wave I-N, IN-1)

Andrew, 2026-10-06: "a **blog section** so I can start writing and sharing analysis." Posts are markdown files in this
repository; a push to `main` publishes them with the next deploy. Writing one: `blog/README.md` (the file name, the
front matter, pictures, `draft: true`) and `blog/_template.md`.

## How it works

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

## Limits (all in `blog.py`)

300 posts (the newest), 200 KB a post, 140 characters a title, 400 a summary, 8 tags of 32, 80 characters a slug, 2 MB
a picture. A post over a limit is skipped and logged (`blog: … skipped`), never served half. Two files with one slug:
the newer file is served, the older is logged. A post's `date` is shown as written (a future date is not held back:
`draft: true` is the way to hold one).

## Publishing (Andrew)

1. Write `blog/<today>-<slug>.md` from `_template.md`; pictures in `blog/img/`.
2. Optional: `LEAGUE_LAB_BLOG_DRAFTS=on` with the app running locally, open `/blog`.
3. Remove `draft: true`, commit, push. The deploy serves it; the link previews and the sitemap follow by themselves.

**The image needs the folder**: `api/Dockerfile` copies `blog/` to `/srv/blog` (the PO's line:
`COPY blog /srv/blog`). Without it the blog is empty on the server (an absent folder is an empty blog, never an error).

## The players block

The first ```` ```players ```` fence of a post — gsis ids and column ids, one per line or `cols: a, b`, at most 12
players and 8 columns — becomes those players' rows of the Stats frame on Half PPR, season to date, per game, in the
Stats screen's own table (`components/blog/PlayersBlock.svelte`; the Stats screen's request
`/api/players?league=ref:half&position=ALL&window=season&limit=1000`, cached like it). Without `cols:` it shows games,
points, targets, share of team passes and receiving yards; an unknown or unavailable column is left out; an id with no
game this season is counted under the table ("Not in this season's table yet: 1 player"), never a row of zeros. A
second fence stays a code block. The numbers move with every nightly: the block says "Live: this season to date".

## Not built

* Comments, search, tag pages, a newsletter, scheduled posts.
* The copy standard's sweep (`scripts/copy_standard.py`) does not read `blog/` (its globs are the code and WORDS); a
  post follows `docs/WORDS.md` by hand.
