# IU-6 — the blog can carry pictures and embeds (Wave I-U) — hand-back, both rounds

Branch `dev/IU6` from `main` `99fb216`. Round 1 (14:09–14:18 ET, 21 minutes): the resize, merged. Round 2 (14:24–
15:40 ET, `league_lab_im4` as the only database written): the cover with its link preview, embeds, links, the security
table, the editor's help line and the template, the e2e.

## 1. Done, not done, cut

| item | state |
| --- | --- |
| 1 a cover per post + link preview | **done.** Column, owner check on save, banner / list thumbnail / home thumbnail, `og:image` + `twitter:image` in the no-script HTML, works without the column. |
| 2 pictures resized in the browser | **done** (round 1, merged). |
| 3 embeds: YouTube behind a tap, X as a link card | **done.** No third-party script anywhere; CSP `frame-src` gains exactly one host. |
| 4 links to any https site | **done** (blog posts only; the site's sentences keep IM-3's nine hosts). |
| 5 the security table | § 5. |
| 6 the editor's help line, WORDS.md, `blog/_template.md` | **done.** |
| 7 e2e at 375 and 1300, outside hosts answered by the test | **done** (`web/e2e/iu6`). Screenshots in `docs/handbacks/iu6/`. |
| cut | a small thumbnail rendition (it would spend a second of the blog's 50 pictures); the cover in revisions; the X post's text (needs X's script). |

## 2. What a post can now hold, and how an editor writes it

* **A cover.** **Picture** → upload (a phone photo is made smaller first) → **Make it the cover** under the picture.
  The editor shows it above the body with **Remove** and at the top of the preview. Saved with the post (a draft
  autosaves; a published post with **Save changes**). It is the post's banner, its thumbnail in the list and on the
  home, and its link preview. Whose pictures: **only pictures the saving account uploaded** (`blog.images.account_id`);
  the post being edited is the account's own (`_get` filters on it), so a cover is always the post owner's picture.
* **A video.** A YouTube link alone on its line (`youtube.com/watch?v=…`, `youtu.be/…`, `youtube.com/shorts/…`) → a
  **▶ Play the video** box with "Watch on YouTube"; the player loads only on the tap.
* **A post on X.** An `x.com` / `twitter.com` `/<handle>/status/<number>` link alone on its line → a card: "A post on X ·
  @handle · Open it on X ›".
* **A link** to any https site: `[words](https://…)`.
* The help line under the body says the first three in one sentence (WORDS.md § the blog editor).

**Bytes.** One rendition per picture, ≤ 300 KB (the server's bound, unchanged); the cover is one of the post's pictures,
not a copy. The e2e's 2400 × 1600 PNG (11.5 MB) was stored as **72,938 bytes** at 1600 × 1067 (a synthetic gradient;
a detailed phone photo will be bigger, up to the 300 KB the steps stop at). 50 posts with one cover each = the blog's
whole 50-picture cap, at most 14.6 MB of the 30 MB cap; **the count, not the bytes, is the limit** (the cap is
blog-wide: `select count(*) from blog.images`). The cover column itself: 16 bytes a row.

## 3. Commits (on top of `d8535ac`)

- `a8b59c5` the cover, server side: `hosted_blog.sql`'s column, `blog_store` (detection, save check, published
  `image`, export), `blog.parse_post` accepts `/blog/img/db/<id>`, CSP `frame-src`; `api/tests/test_iu6.py`;
  `test_io3`'s schema test allows the one additive `alter`
- `cf0b130` the cover on the screens (post banner, list and home thumbnails, the editor's choice) and the help line
- `328093e` embeds and post links in `md.ts`, the tap-to-play in `PostBody.svelte`, `web/e2e/iu6`, io3's inert check
- (last) docs: this file, BLOG.md, WORDS.md, `blog/_template.md`, CHANGELOG, screenshots

## 4. Evidence

**The column (exact line, `scripts/hosted_blog.sql`):**

```sql
alter table blog.posts add column if not exists cover uuid references blog.images (id) on delete set null;
```

Applied twice to `league_lab_im4` with the pipeline role (idempotent). **While it is absent** (the hosted database for
some hours after the deploy): `blog_store.cover_on` asks `pg_attribute` once per process, then at most once a minute
while absent (every ten minutes once present). Without it: `GET /api/blog/mine` → `limits.cover: false`, the editor
offers no cover (the help line drops its cover sentence), a `cover` in a save is **quietly not stored** (200, the rest
saved), every post's `image` is null (the list, the post, the home and the preview as today), the export has no image
line. When the nightly adds the column the API sees it within a minute, no restart. `test_without_the_cover_column_…`
drops the real column on `league_lab_im4` and runs the list, a post, the shell, `/`, `/blog`, RSS, the sitemap, the
export, `mine`, a post's load and two saves (one with a cover) — all 200 — then re-runs the SQL file and shows the
column noticed after the minute.

**The link preview.** A crawler that runs no script gets `index.html` from the API's catch-all with the head block
between `<!-- ll:seo -->` markers replaced by the post's own (`blog.shell` → `preview` → `seo_tags`, every value
`html.escape`d, from the stored post only). Before: a database post's `image` was always null → `og:image` =
`https://isuckatfantasy.io/og.png`. Now: `og:image` and `twitter:image` = `https://isuckatfantasy.io/blog/img/db/<id>`,
`twitter:card` = `summary_large_image`. Proven twice: `test_a_cover_is_stored_…` (TestClient, a title with `<`, `&`,
`"`: escaped) and the e2e (`fetch` of `/blog/<slug>` from the real server, no browser).

**The CSP header, before (main `99fb216`):**

```
default-src 'self'; script-src 'self' 'sha256-8yOK4emASucVfrkU+4aINXAjtjcigTaSHC3JW5CqBuA=' https://*.googletagmanager.com; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; connect-src 'self' https://*.google-analytics.com https://*.analytics.google.com https://*.googletagmanager.com; font-src 'self' data:; manifest-src 'self'; worker-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'
```

**After:** the same, plus `; frame-src https://www.youtube-nocookie.com` at the end. Nothing else changed.

**No request before the tap (e2e, both widths):** every non-localhost request is routed by the test; on the post page,
after load and 1.5 s more, the list of outside requests is **empty**; after the tap it holds only
`https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ?autoplay=1` (answered by the test's stub page, which renders in the
iframe). No `<script src>` from another origin on the page.

## 5. The security table

Server answers are from `api/tests/test_iu6.py` / `test_io3.py` (TestClient on `league_lab_im4`); render answers from
the md.ts tests in `web/e2e/iu6` (pure) and the e2e.

| input | attack | answer |
| --- | --- | --- |
| cover (save) | `javascript:alert(1)`, `data:image/png;base64,…`, `/blog/img/db/x`, `../../etc/passwd`, `x`×64 | 400 `bad_cover` "A cover is one of your own pictures: upload it under Picture first."; nothing stored |
| cover | a well-formed uuid with no picture | 400 `bad_cover` (same words) |
| cover | an id with a quote (`…00000000000'`) or a slash (`…0000000000/0`); an upper-case uuid | 400 `bad_cover` |
| cover | 65 characters; a number instead of a string | 422 (the model's bound / type) |
| cover | another editor's picture | 400 `bad_cover` — the same answer as no picture (no telling whose ids exist) |
| cover | signed out / a cross-site `Origin` | 401 `signed_out` / 403 (the same-site rule) |
| cover | its picture deleted | the post keeps no cover (`on delete set null`), the published list's cache cleared, preview back to `og.png` |
| cover | a file post naming `https://evil.example/x.png`, `javascript:…`, `/blog/img/db/../x.png`, an upper-case id | no picture (`image: null`) |
| resized upload | an SVG with `onload` named `.png` (< 300 KB) | sent as it is; server 400 `bad_image` (io3 e2e) |
| resized upload | an HTML file of ~400 KB with a `<script>`, named `.png`, chosen in the editor | the browser cannot decode it → "A picture is a PNG, JPEG or WebP file."; **no request sent**, the script never ran (iu6 e2e) |
| resized upload | over the bound around the editor | 413 `too_big` (the server's check, unchanged; `test_io3`) |
| resized upload | HTML / GIF / 4 bytes / empty | 400 `bad_image` (unchanged; `test_io3`) |
| embed line | `https://www.youtube.com.evil.example/watch?v=…`, `https://youtu.be.evil.example/…`, `https://evilyoutube.com/…`, `https://evil.example/youtube.com/…` | not an embed: the line stays a paragraph of text |
| embed line | an id of 10 or 12 characters, with `"`, `'`, `/`, `%22`, `"><script>`, `&x="onload=…` | not an embed (text) |
| embed line | `http:`, a user (`user@`), a port, `javascript:…//https://youtu.be/…`, `data:text/html,https://youtu.be/…` | not an embed (text) |
| embed line | an X handle with `-`, `%22`, `"`; 16 characters; a 21-digit or non-digit number; `x.com.evil.example`; `/photo/1` after the number | not an embed (text) |
| embed line | the link inside a sentence, or two links on two lines of one paragraph | not an embed (text) |
| embed render | — | the YouTube placeholder has no `<iframe>`, `<script>`, `<img>`, no `youtube-nocookie` or `ytimg` URL; the X card has no `<script>`, `<iframe>`, `<img>`, no `platform.twitter` / `widgets.js` |
| the tap | a tampered `data-yt-play` | `PostBody` checks the id against `^[A-Za-z0-9_-]{11}$` again before making the iframe; the src is built from it, never read from the page |
| link | `javascript:`, `JaVaScRiPt:`, `data:text/html,…`, `http:`, `//evil.example`, `https://user:pw@…`, `https://…:8443/`, `https://localhost/`, `https:\\evil.example`, `https://evil.example\@good.example/`, `vbscript:`, `ftp:` | the words as text, no `<a>` |
| link | a quote in the target (`"onmouseover="…`) | escaped inside `href`; no attribute escapes |

New routes: none. New lists: none (the cover is one column). `mine`'s pictures stay bounded by 50.

## 6. Tests

All on `league_lab_im4` (`LEAGUE_LAB_DB_NAME=league_lab_im4`); `league_lab` not written in round 2.

- API: `test_iu6.py` 12 · with `test_io3`, `test_io4`, `test_in1`, `test_in2`, `test_im3`: **193 passed, 0 failed** ·
  `test_ip5.py` (reads the blog's sitemap) **35 passed**. The first run had one failure:
  `test_io3::test_the_script_is_idempotent_…` forbade any `alter`. It now allows exactly the one additive line.
- e2e, both projects (`FIXTURES_PORT=8967`, `IU6_API_PORT=8964`, `IO3_API_PORT=8968`):
  - `e2e/iu6 e2e/io3 e2e/in1 e2e/ip0` together: **45 passed, 17 skipped (phone-only / desktop-only skips), 0 failed**.
  - `e2e/in4 e2e/im3`: **15 passed, 1 skipped, 0 failed**.
  - `e2e/iu6` alone again, with the added non-picture test: **6 passed, 4 skipped, 0 failed**.
- Checks: `npm run lint` (eslint + svelte-check + tsc) 0 errors, 0 warnings; `npm run build` green;
  `uv run ruff check src app tests api scripts` clean; `copy_standard.py --check` exit 0; `scripts/gate.sh python`
  **GATE PASSED**.
- Afterwards, `league_lab_im4` holds 0 blog posts, 0 pictures and 0 `@iu6.test` / `@io3.test` accounts, and keeps the
  cover column. No server is left on ports 8960–8969. The in1 / in4 / io3 screenshots the e2e rewrote were restored.

## 7. Edits outside the blog's files

- `api/league_lab_api/security.py`: one directive in `csp()` (`frame-src https://www.youtube-nocookie.com`), as the
  PO asked.
- `scripts/hosted_blog.sql` (the blog's schema file; run by `sync_to_hosted.sh`, which is unchanged).
- `web/src/routes/Home.svelte`: the blog block's thumbnail (one `<img>` and an import).
- `CHANGELOG.md`, `docs/WORDS.md`, `docs/BLOG.md`.

## 8. The PO's lines and by-hand steps

- **Nothing in a PO-owned file.** The nightly's sync already runs `scripts/hosted_blog.sql` as the owner; the first
  nightly after the merge adds the column (a sub-second `alter` on a table of a few rows; the foreign key takes a
  short lock on `blog.posts` and `blog.images`). Until then the site works as today (§ 4).
- `sync_to_hosted.sh` runs the file with `--single-transaction` and a failure there never fails the publish: if the
  `alter` cannot take its lock, the file rolls back whole and the site stays as today until the next night.
- A file post's `image:` (front matter) is now shown too — as its banner and thumbnail, not only in the preview. The
  repository's one post has none.
- If a cover is wanted before the nightly: run the one `alter` line above on Neon as the owner role, by hand.
- `test_io3::test_the_script_is_idempotent_…` now allows exactly that `alter` (a deliberate change in a blog test).

## 9. Found, not mine / limitations

- The 50-picture cap is blog-wide: one editor can use it all, and with covers it will be reached sooner.
- A cover is not kept in a revision; **Earlier versions** brings back text, not the cover.
- WebP covers preview on X and Facebook; some other sites prefer JPEG.
- The X card cannot show the post's text without X's script (by design).

## 10. Next

1. A per-editor or per-post picture cap if more than one editor writes.
2. A JPEG for a picture chosen as cover (the resize can write JPEG on request) if previews elsewhere need it.
