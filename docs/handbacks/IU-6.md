# IU-6 — the blog can carry pictures and embeds (Wave I-U) — hand-back

Branch `dev/IU6` from `main` `99fb216`. Worked 14:09–14:30 ET: the package arrived with 21 minutes to the hard stop,
so **one item is done (item 2, the resize) and the rest is cut**, with what I found for each so the next round
starts from facts.

## 1. Done, not done, cut

| item | state |
| --- | --- |
| 1 cover image + link preview | **not done (cut for the clock).** Findings and a design below (§ 4). |
| 2 pictures resized before they are stored | **done.** Browser-side shrink; server checks unchanged; e2e. |
| 3 embeds (YouTube, X) | **not done (cut).** No iframe, no third-party script added anywhere. |
| 4 links | **answered, not changed** (§ 5). |
| 5 security table | for what shipped only (§ 6). |
| 6 editor help line | the picture help line and the picture panel's label say what the editor now does (WORDS.md); no cover / embed words because neither shipped; `blog/_template.md` untouched. |
| 7 e2e | one new test in `web/e2e/io3/fixtures.spec.ts` (the resize); no embed e2e (nothing to embed). |
| screenshots in `docs/handbacks/iu6/` | the editor after a resized upload, `iu6-editor-resized-375.jpg` / `-1300.jpg` (JPEG q70, taken by the e2e). No list-with-thumbnails / cover / embed shots: those screens were not built. |

## 2. What an editor can now do

Choose a phone photo (several MB, PNG / JPEG / WebP, any size) in **Picture**. If it is 300 KB or less it is sent as
it is (a crisp PNG chart stays a PNG and the server still judges it by its first bytes). If it is bigger, the browser
(`web/src/components/blog/shrink.ts`):

1. decodes it with `createImageBitmap(file, {imageOrientation: "from-image"})` (a phone's rotation is applied; a file
   the browser cannot decode → "A picture is a PNG, JPEG or WebP file.", nothing sent);
2. draws it on a canvas with its longest side at most 1600 px (never enlarged), on white (a transparent PNG does not
   turn black as a JPEG);
3. writes WebP at quality 0.85, 0.75, 0.65, 0.55, 0.45 until one is ≤ 300 KB; a browser that cannot write WebP
   (it hands back a PNG) switches to JPEG at the same steps;
4. if none fits, the same at 75 % and 50 % of that size; still none → "That picture could not be made small enough.
   Try a smaller one.", nothing sent.

What arrives is then checked by the server exactly as before (`blog_store.upload`: ≤ 300 KB else 413, PNG / JPEG /
WebP by the first bytes else 400, 50 pictures, 30 MB in all). No server line changed.

**Bytes.** A stored picture is ≤ 300 KB (307 200 bytes), by the server's check. The blog-wide caps are 50 pictures
and 30 MB for posts + revisions + pictures together (`_room`). 50 pictures at the bound = 14.6 MB, under the 30 MB
cap; **the binding limit for pictures is the count (50 for the whole blog), not the bytes** — which matters for the
cover design (a cover per post spends one of the 50). A second, small thumbnail rendition was not built: it would
spend a second of the 50 per picture; the list can show the one picture at a small size instead (`loading="lazy"`).
Measured once: the e2e's 2400 × 1600 PNG (11 523 418 bytes, a synthetic gradient) was stored as 72 938 bytes at
1600 × 1067. Not measured: a real phone photo (more detail → bigger; the steps stop at the first that is ≤ 300 KB).

## 3. Commits

- `IU-6: a picture over 300 KB is made smaller in the editor's browser …` — `shrink.ts`, `BlogEditor.svelte`
  (import, one line in `onFile`, the two picture sentences), the io3 e2e test.
- `IU-6: hand-back, CHANGELOG, WORDS` — this file, the CHANGELOG bullet, WORDS.md's pictures row.

## 4. The link preview and the cover — findings for the next round (nothing changed)

**How `/blog/<slug>` reaches a crawler that runs no script today:** the web app's catch-all in `main.py` calls
`blog.shell(index.html, path)`, which replaces the block between `<!-- ll:seo -->` and `<!-- /ll:seo -->` with
`blog.seo_tags(blog.preview(path))`: `<title>`, `description`, canonical, `og:type/site_name/title/description/url/
image`, `article:published_time`, `twitter:card` = `summary_large_image`, `twitter:title/description/image` — every
value through `html.escape(…, quote=True)`, from the stored post only (title, summary, date, author, slug). So
`og:title` / `og:description` / `twitter:card` are already in the HTML a crawler receives. `og:image` is the post's
`image` when it has one, else `https://isuckatfantasy.io/og.png` (1200 × 630). **A file post** can set `image:` in its
front matter today; **a database post** (written in the editor) always has `"image": None`
(`blog_store._read_published`), so it always previews with the site's default picture.

**The cover, as I would build it (not built):** a nullable column `blog.posts.cover uuid references blog.images (id)
on delete set null` (an `alter table … add column if not exists` in `scripts/hosted_blog.sql`, run by the publish);
`SaveIn` gains `cover` (an id or null), and `save` accepts it only when `select 1 from blog.images where id = %s and
account_id = %s` matches the saving account (else 400 `bad_cover`, the same answer for "not yours" and "no such
picture"); `_read_published` selects it and sets `image` = `/blog/img/db/<id>`, so `preview()` and `seo_tags()` carry
it with no change; the list, the home card and the post page render `image` (escaped attribute, `loading="lazy"`,
fixed aspect box). The app must tolerate the column missing (hosted before the next publish): `to_regclass` /
`information_schema` check once, as `ready()` does. A crawler-side `og:image` for a WebP: Facebook and X accept WebP;
LinkedIn's support is uneven — a JPEG cover is the safe choice (the shrink could write JPEG for a picture chosen as
cover).

## 5. Links in a post today (`web/src/lib/md.ts`, unchanged)

`[label](href)`: an in-app path (`/…`, not `//` or `/\`) → `<a href>` with the league context; `https://` to one of
nine hosts (`isuckatfantasy.io`, `espn.com`, `sleeper.com`, `sleeper.app`, `myfantasyleague.com`, `yahoo.com`,
`nfl.com`, `draftkings.com`, `fanduel.com`, and their subdomains), no user / password / port → `<a href …
rel="noopener" target="_blank">`; anything else (another https host, `http:`, `javascript:`, `data:`, a link holding a
picture or code) → the label as plain text. Nothing is wrong in what it does; "links to any https site" is a product
choice the brief asks for, not a defect — not changed today. If it is made: allow any `https:` host with no
credentials or port, add `nofollow ugc` to `rel` (`noopener noreferrer nofollow ugc`), keep everything else.

**CSP:** the app sends one (`security.py`, `csp()`): `default-src 'self'` and no `frame-src`, so any iframe is
refused today; `frame-ancestors 'none'`, `object-src 'none'`. An embed would need exactly
`frame-src https://www.youtube-nocookie.com` added — not done, since no embed shipped. The resize needs no CSP change
(a canvas from a local file; no network).

## 6. Security table (what shipped: the resized upload)

The server's route and checks are untouched, so every attack is answered by the same lines IO-3 / IO-4 reviewed.

| input | attack | answer | how verified |
| --- | --- | --- | --- |
| upload | an SVG (with `onload`) named `.png`, under 300 KB | sent as it is (under the bound, no decode), server 400 "A picture is a PNG, JPEG or WebP file." | io3 e2e (existing test, green with the change) |
| upload | an HTML / SVG file over 300 KB | the browser cannot decode it → "A picture is a PNG, JPEG or WebP file.", nothing sent; a script that skips the editor and posts it gets the server's 413 / 400 | reasoning + the server's unchanged checks; **no test of the over-300 KB non-picture path** |
| upload | an oversized picture posted around the editor (curl) | server 413 `too_big` (unchanged) | existing API tests (`test_io3` / `test_io4`), not re-run by me |
| upload | an 11.5 MB 2400 × 1600 PNG through the editor | shrunk to 1600 × 1067, WebP / JPEG by its first bytes, 72 938 bytes, server 201; no sideways scroll at 375 | new e2e (both projects) |
| upload | 51st picture | server 409 `too_many_images` (unchanged) | not re-run |
| new route | — | none added; no new list | — |

## 7. Tests

- `web`: `npm run lint` (eslint + svelte-check + tsc) 0 errors 0 warnings; `npm run build` green.
- `scripts/copy_standard.py --check` exit 0.
- e2e `e2e/io3` (the editor; the only screen changed), both projects, `IO3_API_PORT=8968 FIXTURES_PORT=8967`: the full
  spec **17 passed, 9 skipped (the phone-skipped ones), 0 failed** in 2.2 min with the resize test desktop-only; then
  the resize test on both projects after adding the 375 run and the screenshots: **2 passed**. Other blog / home
  specs (`in1`, `in4`, …) not run: their screens did not change.
- No Python changed: ruff / `gate.sh python` / the blog API tests not run (nothing of theirs moved).

## 8. Edits outside my files

None. (`CHANGELOG.md`, `docs/WORDS.md` as the brief asks.)

## 9. PO lines

None needed for what shipped. For the cover (next): `scripts/hosted_blog.sql` gains the `alter table` (mine to write
next round; `sync_to_hosted.sh` already runs that file).

## 10. Found, not mine

- The 50-picture cap is blog-wide (`select count(*) from blog.images`), not per post or per editor: one editor can
  use all 50. With covers this will be reached quickly.

## 11. Next

1. The cover per § 4 (column, owner check on save, `image` from the stored post → banner, list, home, `og:image`),
   with an e2e that a crawler's HTML (no script) carries the cover's absolute URL, escaped.
2. Embeds: one bare link on its own line; YouTube by `^[A-Za-z0-9_-]{11}$` from `youtube.com/watch?v=`,
   `youtu.be/`, `youtube.com/shorts/` only; a click-to-load placeholder → iframe to
   `https://www.youtube-nocookie.com/embed/<id>` (`sandbox="allow-scripts allow-same-origin allow-presentation"`,
   `loading="lazy"`, `referrerpolicy="strict-origin-when-cross-origin"`, a title); X by
   `^https://(x|twitter)\.com/([A-Za-z0-9_]{1,15})/status/(\d{1,20})$` → a plain link card; CSP `frame-src` +1 host.
3. Then links to any https host (§ 5).
