# IN-1 hand-back — a home page, the league-setup screen on a desktop, the blog (Wave I-N, 2026-10-06)

**Task**: IN-1 of `/home/claude/waveIN/BRIEF.md` (Wave I-N, Iteration 24). **Branch** `dev/IN1` from `main` `967b2d9`,
worktree `/home/claude/wt-in1`. Plan sections: the brief's § IN-1 (1–6) and § "Interfaces fixed now" (the blog's list;
IN-3's board as a reader). Screenshots: `docs/handbacks/in1/` (375 and 1300; `*-full-*` are whole pages).

## Done / not done (the package's numbered list)

1. **Home — done.** `web/src/routes/Home.svelte` (+ `components/home/home.ts`, pure). `/home` always; `/` when no league is
   in the URL nor remembered on the device (`router.svelte.ts` reads `ll.league`; a returning manager's `/` is My Week).
   In the frame (tabs, search, the drawer) on the reference league. Above the fold at **1300 × 800 and 375 × 667** (e2e
   asserts the boxes): the name, one sentence (IM-3's front-door sentence), **Open your league** / **Browse players**,
   and **This week's top projections** (Half PPR, QB · RB · WR · TE, 5 rows). Below: **Matchups to target this week**
   (IN-3's `GET /api/matchups/board?league=ref:half&position=WR&sort=tone&limit=5`; hidden on any failure — on this
   branch it is a 404), **How the projections have done** (About's own grades: average miss this season vs the
   backtest, inside the range vs the 80% aim, the worse positions in the bad color and the lead sentence naming the
   weakest first — "quarterbacks are our weak spot: 6.5 points off on average, against 5.4 in past seasons"; then the
   record's line from `/api/record`), **From the blog** (newest 3), **the tools** as tiles (Players, Trade calculator
   `/trade-calc?league=ref:half`, Matchups, DFS). Every module hides itself when its call fails (no error card on the
   home). IM-3's front door left `/leagues` (moved here).
   **The projections' range — read this**: no existing route lists *this week's* range for a reference key (`/api/ros`
   has this week's projection `week_points` but the rest-of-season range; `/api/players` has no projection; DFS
   projections are DraftKings / FanDuel scoring). So the module reads **IN-3's board first** (rows with a projection and
   `p10` / `p90` → "range 9.4–25.4") and, when the board is missing, falls back to `/api/ros` sorted by `week_points`
   with the **season's** range, labelled as such ("season 173 (141–204)" and a footnote that says which). The board
   reader is tolerant (`home.ts` `fromBoard`: `projection` as a number or `{proj_points, p10, p90}`, else `proj` /
   `proj_points`; tone / words at the row or under `context` / `matchup`) — **at the merge, check IN-3's field names**
   against `fromBoard` / `toneOf` (two small functions; e2e `home: when the matchup board answers…` shows the shape I
   assumed).
2. **League setup on a desktop — done.** `routes/Leagues.svelte`: three parts — the form (header, steps, platform, the
   platform's box), **the results**, the extras (what the platform gives, the guest line, the account). A phone stacks
   them in that order (the leagues come right under the field, no longer under the provider cards); from 900 px the
   results sit **beside** the form, at the top (`max-w-6xl`, `26rem` + the rest), with "Your leagues show here once you
   find them" before a search. After **Find my leagues** (and a league link, MFL, ESPN, Yahoo): the results scroll into
   view when they are not already near the top and **take focus** (`tabindex=-1`, a region); the button says
   "Looking…" and is disabled (`aria-busy`); "No leagues for that username this season." in the same place. **Proved**:
   e2e types `fixture_user`, holds the answer to see the loading state, then asserts the first league row's box inside
   the viewport at **1300 × 700** (and the field still in view, nothing scrolled) and at **375 × 667**, focus on the
   results; the empty case's line in view too.
3. **The blog — done**, players block included. API `api/league_lab_api/blog.py`: the folder read once (memo region
   `blog`, ≤ 4 entries, 1 h), strict slug, nothing from a URL opened (a test patches `Path.open` / `read_text` and asks
   12 hostile slugs), drafts only with `LEAGUE_LAB_BLOG_DRAFTS=on`, an absent folder = an empty blog. Routes
   `GET /api/blog?limit=` (1–50), `GET /api/blog/{slug}`, `GET /blog/rss.xml`, `GET /blog/img/{name}` (png / jpg / webp,
   first bytes checked, ≤ 2 MB, no link, SVG refused, 30-day cache), `GET /sitemap.xml`. Screens `/blog` and
   `/blog/<slug>` (`routes/Blog.svelte`, `components/blog/PostBody.svelte`): a 44rem measure beside an aside at 1300,
   tables that scroll inside their own box at 375 (asserted), the date, minutes, **Copy link** (asserted on the
   clipboard; no clipboard → the address in a field), more posts, "No post at that address." `lib/md.ts` gained
   **`mdDoc`** (headings, ordered lists, quotes, tables with alignment, `code` and fenced code, `---`, *italic*,
   pictures from `/blog/img/` only), escaping first; `md()` untouched. A player link opens the drawer (asserted).
   **The players block** (`components/blog/PlayersBlock.svelte`): the first ```` ```players ```` fence (gsis ids and
   column ids, one per line or `cols: a, b`; ≤ 12 players, ≤ 8 columns) → those players' rows of the Stats frame
   (`/api/players?league=ref:half&position=ALL&window=season&limit=1000`, the Stats screen's own request, cached) in
   the Stats screen's own `StatsTable`, per game, sortable, "Live: this season to date, per game, in Half PPR scoring".
4. **Links that preview — done.** The SPA fallback puts each path's preview into the shell between `<!-- ll:seo -->`
   markers (`web/index.html`): `<title>`, description, canonical, `og:title / description / type / url / image`
   (+ 1200 × 630), `twitter:card summary_large_image` (+ title / description / image), a post's
   `article:published_time`; escaped (a hostile title tested); for `/`, `/home`, `/blog`, a post (unknown → the blog's
   preview with **404**), `/players`, `/matchups`, `/trade-calc`, `/dfs`; anything else the file as it is. `/` keeps
   `<title>isuckatfantasy</title>` (the image workflow greps it). `web/public/og.png` (1200 × 630, 104 KB, a Playwright
   screenshot of a small HTML card). `/sitemap.xml`; `robots.txt` points at it. **CSP**: the inline script is
   untouched; `test_in1` checks the served page's inline script hash is the one in the served policy, and the built app
   on the fixture API with GA forced on showed **0 CSP violations** on `/`, `/home`, `/blog`, a post, `/leagues`.
5. **Two launch pieces — done.** `blog/2026-10-06-how-to-read-this-sites-numbers.md` (author isuckatfantasy: the
   projection, the two ranges and their measured coverage, how the record is kept, where we have been wrong — QB order
   0.39 vs 0.59 and miss 6.5 vs 5.4, TE 3.5 vs 3.0, the market gap, the lineups' −1.2 on two rebuilt weeks, what a
   projection does not know; numbers from `/api/about` on this database and docs/METRICS.md / HANDOFF). `blog/README.md`
   (file name, front matter, players link and block, pictures, `draft: true`, push to publish) and `blog/_template.md`.
   Analytics: one `page_view` per post path (App's GA effect now follows the slug: post → post counts; asserted).
6. **Docs — done.** `docs/BLOG.md`, `docs/WORDS.md` § "The home page, the setup screen, the blog", `CHANGELOG.md`
   (created `## 2026-10-06 — Wave I-N`), this file, the screenshots.

## Files

Mine: `api/league_lab_api/blog.py` (new), `api/tests/test_in1.py` (new), the SPA fallback + one router block in
`api/league_lab_api/main.py`, `web/src/routes/{Home,Blog}.svelte` (new), `web/src/components/home/home.ts`,
`web/src/components/blog/{PostBody,PlayersBlock}.svelte` (new), `web/src/App.svelte`, `web/src/routes/Leagues.svelte`,
`web/src/lib/router.svelte.ts`, `web/index.html`, `web/public/{og.png,robots.txt}`, `blog/**`, `docs/BLOG.md`,
`web/e2e/in1/fixtures.spec.ts`, `web/fixtures/in1/api_in1.json` (158 KB, recorded from the fixture API; ROS rows
trimmed of `why`, the Stats frame kept to three players), `docs/handbacks/IN-1.md`, `docs/handbacks/in1/*.png`.
`web/src/components/Login.svelte` not touched (nothing needed).

**Edits outside my files** (each in an `IN-1` block): `api/league_lab_api/ratelimit.py` (`PAGES_READ` /
`PAGES_READ_PREFIX` + two lines at the top of `bucket_for`: the feed, the sitemap and the pictures are `read`;
`/api/blog*` was already `read` by default — asserted), `api/league_lab_api/usage.py` (`SCREENS` += `home`, `blog`,
`post`, **and `dfs`** — IM-5's screen was missing: DFS views were stored as "other" and `test_u1`'s router check failed
on `main`; it passes now), `web/src/components/TopBar.svelte` (⋯ menu: **Home**, **Blog**; IN-2 owns the tabs),
`web/src/lib/api.ts` (types and paths at the end), `web/src/lib/md.ts` (`mdDoc` appended, the brief's "extend it"),
`docs/WORDS.md`, `CHANGELOG.md`. **Existing e2e changed on purpose** ("/" without a league is the home now): 13
`page.goto("/")` → `"/leagues"` in `fixtures.spec.ts`, `i0b`, `i0c` ×2, `ic3` ×2, `ic4`, `ie0`, `ie2`, `ig3`, `ih2`,
`ih3`, `v2`; `fixtures.spec.ts`'s gated walk goes home → **Open your league**; `im3`'s first test asserts the home
(the front door's new place) and the second `/leagues`' form instead of the front door.

## Schema in / out

No database change, nothing written. New answers: `GET /api/blog` `{"posts": [{slug, title, date, summary, author,
tags, minutes, image}]}` (+ `draft: true` with drafts on); `GET /api/blog/{slug}` the same + `markdown`, 404
`{"error": "No post at that address.", "code": "no_post"}`; `/blog/rss.xml` (RSS 2.0), `/sitemap.xml`, `/blog/img/*`.
The HTML shell's head per path (above).

## The PO lines I need

* `api/Dockerfile`, after `COPY src/league_lab /srv/src/league_lab`: **`COPY blog /srv/blog`** (`blog.folder()` is
  `<ROOT>/blog` = `/srv/blog` in the image; without the line the blog is empty on Render, never an error).
* `render.yaml`: nothing. **Never** set `LEAGUE_LAB_BLOG_DRAFTS` there.
* `docs/STATUS.md`: the IN-1 line from this file's summary. `app/whats_new.md`: "A home page with this week's top
  projections and how they have done; a blog (the first post: how to read this site's numbers); the league setup shows
  your leagues right beside the box on a computer."
* Optional: `scripts/copy_standard.py` `GLOBS` += `"blog/**/*.md"` (posts are user-facing; the sweep does not read them
  today). Optional: the image workflow's smoke could `curl -sf …/blog/rss.xml` and `…/sitemap.xml`.
* At the merge with IN-3: check `home.ts` `fromBoard` / `toneOf` against the board's real rows (see 1).
  With IN-2: put **Home** in the no-league tab bar (route name `home`, path `/home`); my menu items can stay.

## New environment variables / dependencies

`LEAGUE_LAB_BLOG_DIR` (default `<repo>/blog`), `LEAGUE_LAB_BLOG_DRAFTS` (off; `on` lists drafts). No new dependency.

## Evidence (commands run, results; this box, 2 shared cores)

* `cd api && OMP_NUM_THREADS=1 PYTHONPATH=. uv run pytest -q tests/test_in1.py tests/test_static.py tests/test_im3.py
  tests/test_auth.py tests/test_ik4.py tests/test_im4.py` → **140 passed** (test_in1: 27 — front matter, what is not a
  post, drafts, a repeated slug, an absent folder, list / post / limits, 12 hostile slugs never opened, RSS valid and
  escaped, the sitemap, robots, 11 bad pictures refused, the previews per path, the CSP hash, a shell without markers,
  the buckets, the launch post's links).
* `tests/test_u1.py` → 19 passed, 2 failed (`test_no_name_username_or_ip_in_a_row`, `test_the_sync_keeps…`: this
  sandbox's usage schema / sync file — `check_api.sh` deselects the file); `test_the_row_is_allow_listed` failed on
  `main` (IM-5's `dfs`) and passes now. The full API suite: not run (the brief).
* `uv run ruff check src app tests api` clean; `uv run python scripts/copy_standard.py --check` clean; `cd web && npm
  run lint` (182 files, 0 errors / warnings) and `npm run build` clean (the first bundle `index-*.js` 229.6 KB, gzip 72
  KB, includes the home; `Blog-*.js` 11 KB its own chunk).
* `FIXTURES_PORT=8710 npx playwright test --config playwright.fixtures.config.ts e2e/in1` → **15 passed**, 3 skipped
  (the setup test runs one size per project): the home above the fold at both sizes and its modules hiding (the board
  missing; every call failing), the home with a board, setup at 1300 × 700 and 375 × 667, the blog (list, post, share,
  the demo post with every markdown piece, raw HTML as text, the players block, the drawer, GA), the missing / empty
  blog, the menu, `mdDoc`'s escaping. The changed specs: `im3 i0b i0c ic3 ic4 ie0 ie2 ig3 ih2 ih3 v2` → 71 passed /
  1 skipped; `e2e/fixtures.spec.ts` → 34 passed. **The whole fixtures e2e** (one run, 12.7 min, before the last two home
  fixes below): **443 passed, 1 failed, 6 skipped** — the failure `il5 … Watching / Watch, Remove` [desktop] is a GA
  event read racing the load (`watchlist_remove` not yet pushed); alone it passes (7 / 7). After the fixes: `in1`, `im3`
  and `fixtures.spec.ts` again → 15 + 43 passed.
* Found by the "every call failing" test and fixed: the projections module's effect read the state it wrote, so a
  failed load retried forever (`untrack`); the module now hides when nothing loaded.
* The built app on the fixture API (`LEAGUE_LAB_GATE=open`, GA forced on, gtag stubbed): **0 CSP violations** on `/`,
  `/home`, `/blog`, a post, `/leagues`; every answer's policy carries the inline script's hash.
* Timings on the fixture API (warm): `/api/blog` 2–3 ms, a post 2 ms, a post's shell 2 ms, RSS 2 ms, sitemap 2 ms.

## Limitations

* The home's top projections show this week's **range** only once IN-3's board answers (above); until then the
  season's range, said so.
* "Matchups to target" assumes the board accepts `sort=tone` and that its first rows are the friendliest; it hides on
  any non-200.
* `/` without a league renders the home during the boot request: with `LEAGUE_LAB_GATE=password` the home shows for a
  moment before the password screen (its calls answer 401 and the modules stay hidden). The gate is open today.
* A post's date is shown as written (no scheduling; `draft: true` holds one back). One players block per post.
* The shell's per-path preview reads the post index (a memo entry): a slug that is not a post costs a dict lookup.

## Seen, not mine

* `TopBar`'s "No league ·" and About's `grade_note` ("…not No league · Half PPR's") still say "No league" (IN-2's
  words, `league_name` for a reference key).
* `GET /api` (no slash) answers the SPA shell with 200 (the fallback); harmless.

## Next

The PO's `COPY blog /srv/blog`; the merge checks with IN-2 (the Home tab) and IN-3 (the board's rows); Andrew's first
post from `blog/_template.md`.

## Fix round (2026-10-06, branch `fix/IN1` from `integ/IN` `cd56421`)

* **Review L5**: `blog.py` uses `fullmatch` for `FILE_NAME`, `IMG_NAME` (the post's `image:` and the picture route) and
  `SLUG`: with `re.match` a `$`-anchored pattern accepted a trailing newline. `test_in1`
  `test_a_trailing_newline_is_not_a_slug_nor_a_picture` (a file name, a picture actually named `chart.png\n` on disk,
  `%0a` / `%0A` on both routes, a slug in the index) fails on the old code, passes now.
* **Review nit (`md.ts`)**: `inline` holds each link's opening tag aside (U+E001) until the end and refuses a target that
  holds a placeholder, so a picture, code, bold or italic written inside a link's target never lands in its `href`
  (`[x](/p![a](/blog/img/a.png))` is the words "x"); bold / italic around a link still wrap it. `md()`'s output for
  ordinary sentences is unchanged. Cases in the e2e's markdown test.
* **The home on the real board** (fixture API from the merged tree, 8761): "Matchups to target" and this week's range
  ("range 7.3–28.8") come from `/api/matchups/board`. Read wrong with real data, fixed: (1) the note said the matchup is
  "not added to" the projection — the defense against his position **is** a projection input (the board's own
  `projection_words`); now "The defense he faces is already in his projection; who plays cornerback is not."; (2) the
  board's sentence names both possible corners on an unclear call (every WR this week): five rows ran a page long — the
  home shows the defense's sentence, plus the corner's only when the call is likely (`home.ts` `homeWords`); (3) "to
  target" lists favorable rows only (sorted by tone, highest projection first among them); (4) each row shows his
  projection ("16.8 this week"). The recording `web/fixtures/in1/api_in1.json` now carries the board's real answers
  (each position by projection, WR by tone); the spec's default is that board, a second test keeps the 404 fallback.
  Screenshots: `home-{phone,desktop}.png`, `home-full-*.png` (the e2e on the real answers), `home-live-{375,1300}.png`
  and `home-live-full-*.png` (straight from the fixture API).
