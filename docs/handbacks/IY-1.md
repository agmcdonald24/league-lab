# IY-1: embed code pasted into a blog post works (Wave I-Y) — hand-back

Started 12:39 ET, finished 12:56 ET. Branch `dev/IY1` from `main` `7969341`, worktree `/home/claude/wt-iq4`, database
`league_lab_iq4`.

## 1. Done / not done / cut

All five items are done.

* **The parser.** Embed code from X and YouTube is read, never passed through. One function in `web/src/lib/md.ts`
  handles every post. The server renders no post body: a crawler gets the head tags and RSS carries the summary.
* **The X block.** It shows the post's words and "Name (@handle) · date", then **Show the post** and **Open on X**.
  X's own frame appears only after the tap. It is sized by X's height message and is 560 px tall, scrolling inside
  itself, until a message arrives.
* **The CSP.** `frame-src` gains `https://platform.twitter.com` and nothing else changes.
* **The editor.** The help line names both ways. The preview is the reader's own renderer (`PostBody`), so the writer
  sees what the reader will see.
* **Tests.** Parser, frame handler and post-page tests on both projects, plus the API test for the header.

Nothing was cut.

**Andrew's post.** His stored post (the paste on one line) renders right with no edit: the first test feeds it in
character for character.

## 2. Commits

- `c8ab859`: the parser, the X block, the tap-to-show frame (`components/blog/xframe.ts`), the CSP, the tests
  (`web/e2e/iy1`; `iu6` and `test_iu6` follow the new block and header).
- `5e5ea5d`: the help line, WORDS.md, BLOG.md, the screenshots.
- The last commit: this file and the CHANGELOG.

## 3. Evidence

**What each pasted input becomes:**

| input | becomes |
| --- | --- |
| Andrew's paste (one line, `x.com`, the widgets.js script after it) | the X block: his words, "Ari Meirov (@MySportsUpdate) · June 9, 2023", Show the post, Open on X; the script dropped |
| the same paste broken over lines / with Windows line ends / without the script / with `twitter.com` | the same block |
| the paste in the middle of a sentence | the words before and after stay paragraphs; the block stands alone |
| YouTube's `<iframe src="https://www.youtube.com/embed/<id>?si=…" …>` (or `youtube-nocookie.com`) | the Play block from the id; the iframe's other attributes are not read |
| a blockquote with a `javascript:` link and an `onclick`, no status link | text, as written (escaped) |
| a status id with letters, of 4 or 26 digits; a handle with `-`; `x.com.evil.example`; `http:`; `class="tweet"` | text, as written |
| a valid status link with hostile insides (an `onmouseover` on the blockquote, `javascript:` / `onclick` links, `<img onerror>`, `<b>`, `&lt;script&gt;`, `&#106;avascript`, `&#0;`, a surrogate entity) | the block with only the plain words: `click bold <script>alert(6)</script> javascript`, shown as text |
| a second `<script>` from another host after the blockquote | text, after the block |
| widgets.js alone; any other HTML (`<div onclick>`, another iframe) | text |
| the paste inside a code fence | code, as written |
| YouTube iframes with a 10-character id, a quote in the id, a look-alike host, another host, `http:`, a `javascript:` src | text |
| the private-use mark the parser uses, typed by a writer | dropped |

**The frame's height messages:**

| message | result |
| --- | --- |
| from `https://platform.twitter.com`, from our frame, an object or a JSON string | height set, clamped to 200–2000 px (50 → 200, 99999 → 2000) |
| from `https://evil.example` or `https://platform.x.com` | ignored |
| from another window, or with no source | ignored |
| `"garbage"`, `{}`, the wrong method, empty params, `NaN`, `"640px"`, a string over 20 KB | ignored |

**The CSP** (`security.py`): `frame-src https://www.youtube-nocookie.com` → `frame-src https://www.youtube-nocookie.com
https://platform.twitter.com`. `script-src` is unchanged: `'self' 'sha256-8yOK4…' https://*.googletagmanager.com`.

**The post page, end to end.** The fixture API answers the post with Andrew's paste, a YouTube iframe paste and a
forged blockquote.
- **Before the tap.** The page holds no iframe, no `blockquote.twitter-tweet` and no widgets.js script. No request
  leaves for X or YouTube. The forged code shows as text and never runs. No sideways scroll at 375.
- **After the tap.** One iframe with exactly this src, `sandbox`, `loading="lazy"`, `referrerpolicy="no-referrer"` and
  title "Post on X":
  `https://platform.twitter.com/embed/Tweet.html?id=1666992852084092930&dnt=true&theme=light|dark`
  - The test's stub page at that address posts a resize message, and the frame becomes 812 px tall.
  - The frame is as wide as the column. The only outside request is that address.
- **Screenshots.** In `docs/handbacks/iy1/`: before the tap, and after it at 375 and 1300. After the tap the frame
  shows the test's stub ("X's post would show here."), because this sandbox cannot reach X.

## 4. Tests

- **e2e, both projects** (`FIXTURES_PORT=8927`, `IU6_API_PORT=8924`, `IO3_API_PORT=8928`): `e2e/iy1 e2e/iu6 e2e/io3
  e2e/in1 e2e/ip0` gave **53 passed, 23 skipped, 0 failed**. The skips are the pure tests and the desktop-only ones on
  the phone project.
  - `iy1` alone: 7 passed, 5 skipped.
- **API** (`league_lab_iq4`): `test_iu6.py`, `test_im3.py`, `test_in1.py` gave **103 passed**. The CSP test is now
  `test_the_csp_frames_only_youtube_nocookie_and_x`.
- **Checks:** `npm run lint` 0 errors, 0 warnings. `npm run build` green. Copy standard exit 0. `scripts/gate.sh` (all):
  **GATE PASSED** (root 783, api 40, ruff, web lint, build).
- **Unit tests.** `web/src` has no unit-test runner, and adding vitest would be a new dependency. The parser and
  frame-handler unit tests are pure-function tests in `web/e2e/iy1`, as `in1` and `iu6` do.

## 5. Edits outside my files

- `api/league_lab_api/security.py`: one directive.
- `api/tests/test_iu6.py`: its CSP test.
- `web/e2e/iu6`: the X block is now ours; its words are "Open on X" and "Show the post".
- Docs: `docs/WORDS.md`, `docs/BLOG.md`, `CHANGELOG.md`.

## 6. PO lines

None.

## 7. Found, not mine

`league_lab_iq4` holds one `@iu6.test` account created at 02:17 ET today, before this package started. It has no posts
and no pictures. I left it.

## 8. Next / what only the live site can show

These need the live site; the sandbox cannot reach X.
1. **X's frame.** Does `https://platform.twitter.com/embed/Tweet.html?id=1666992852084092930&dnt=true&theme=light` render
   inside our sandbox, with the video playing? The sandbox includes `allow-same-origin` and `allow-scripts`, and the CSP
   now allows that frame.
2. **The resize message.** Does X still send `twttr.private.resize`? If it does not, the frame stays at 560 px and
   scrolls inside itself.
3. **Dark theme.** Does `theme=dark` follow a phone in dark mode?
4. **Andrew's post.** Does `/blog/what-s-monti-ossenfort-up-to-now` show the block with no edit?
