# IY-3: a published post never disappears because one read failed; X's frame, round 3 (Wave I-Y) — hand-back

Started 16:49 ET, finished 17:04 ET. Branch `dev/IY3` from `main` `62a793c`, worktree `/home/claude/wt-iq4`,
database `league_lab_iq4`.

## 1. Done / not done / cut

All eight items are done; nothing was cut.

**A. The fault.** The changes are in `blog_store.py` and `blog.py`, plus the shell's headers in `main.py`'s blog block.

* **Three outcomes are now kept apart.** Before, one read that raised counted as "no posts" for a minute.
  - A read that succeeds: the answer, kept a minute and remembered as the last good answer.
  - A read that succeeds but finds no table or no right: a real state, kept a minute, as before.
  - A read that raises: the last good answer, if this process ever had one, else "unread". Either way the next read is
    tried within 5 s (`RETRY_S`).
* **Pictures.** `image()` now also keeps its last good picture. Before, a failed read after the minute's cache gave 404.
* **Bound on what is kept.** The last good answers sit outside the memory budget's region, so it cannot evict them.
  - One list.
  - 40 bodies, at most about 8 MB in the worst case.
  - 20 pictures, at most about 6 MB.
  - An unpublish or delete made in this process forgets that post at once.
* **Unknown is not "no post".** When the process never read the store and cannot now:
  - The list is the files' posts, with `public, max-age=5`.
  - A database post's address answers 503: "This post did not load. Try again in a few seconds.", `Retry-After: 5`,
    `no-store`. The API, the page's HTML and a picture all do this.
  - The post page shows those words with **Try again**.
  - RSS and the sitemap are the files' posts with `max-age=5`.
* **Logging.** Once per failure streak, at warning, with the exception's class and never its text. For example:
  `blog: the published list not read (PoolTimeout); serving the last good answer if there is one`.

**B. X's frame.**

* `scrolling="no"` and `allowfullscreen` are set; the sandbox is unchanged.
* The 10 s give-up counts only while `document.visibilityState` is `visible`.
* After a give-up, the block tries once more the next time it is on screen in a visible document. That makes two
  attempts in all; then the card stays.

## 2. Commits

- `6aece5c`: the store, the 503, the post page's Try again, X's frame, the tests.
- The next commit: `test_io3`'s down-database test now expects the 503.
- The last commit: docs, this file and the CHANGELOG.

## 3. Evidence: what a visitor gets

| case | the list (`/api/blog`, home, `/blog`) | a post's page (`/api/blog/<slug>`, `/blog/<slug>`) | a picture (`/blog/img/db/<id>`) |
| --- | --- | --- | --- |
| the store reads well | every post, `max-age=0, must-revalidate` | 200 | 200 |
| a read raises; this process read it before | the last good list, same headers; tried again within 5 s | 200 with the last good body if it was read before; a body never read gives 503 | the last good picture (≤ 20 kept); one never read gives 503 |
| a read raises; never read by this process | the files' posts, `max-age=5`; RSS and the sitemap the same | a database post gives **503** with the words, `Retry-After: 5`, `no-store` (the HTML too); a file's post gives 200 | 503, `no-store`, `Retry-After: 5` |
| the table or the right is not there (the read succeeded) | the files' posts, `max-age=300`, as before | 404 "No post at that address.", `no-store` | 404, `no-store` |
| the read succeeded, and there is no such post | — | 404, `no-store` (the HTML 404 is `no-cache`: revalidated every time) | 404, `no-store` |

Neither the 404 nor the 503 can be kept by a browser, crawler or CDN. The 503 is `no-store`, and the 404 is `no-store`
(the API) or `no-cache` (the HTML). The 404 now happens only after a read that succeeded.

## 4. Tests

**API (`league_lab_iq4`).** `test_iy3.py` has **7 passed**. A stand-in `db` that only `blog_store` sees raises
`PoolTimeout`, `OperationalError` or `QueryCanceled`, and the region's clock is faked.
- Under each of the three failures, after a good read:
  - the list holds the post, its API answer and page are 200 with the body, and the picture serves;
  - the three warnings appear once each, with the class and without the text;
  - the retry happens within 5 s;
  - a post published while reads fail is not listed until the store answers again, then appears.
- Never read: 503 for the database post's API and HTML and for a picture, all `no-store` with `Retry-After: 5`; the
  files' post 200; RSS and the sitemap `max-age=5`; after recovery 200, and the 404 for an unknown slug as before.
- The table absent: unchanged.
- An unpublish made in this process is not served from the last good list.
- The bounds hold: 40 bodies, 20 pictures.

**Every blog API file.** `test_iy3`, `test_io3`, `test_iu6`, `test_in1`, `test_im3`, `test_io4`, `test_ip5`,
`test_in2`: 235 run. The one failure on the first run was `test_io3::test_the_database_down_leaves_the_files`, which
expected `published_body` to return None, the old 404. It now expects `Unread`, a 503 for a database slug and a 200 for
the file's post: changed on purpose.

**e2e `iy1`, both projects: 11 passed** (the pure tests run on desktop only).
- The frame carries `scrolling="no"` and `allowfullscreen`.
- A hidden document runs 30 s on a fake clock and the frame stays. Once visible, it is still there at 9 s and gone at
  10.5 s, and a second frame comes because the block is on screen. That one goes after 10.5 s, and 30 s more makes
  no third request.
- A 503 shows the words and Try again, never "No post at that address."; Try again loads the post.

**Blog e2e and checks.** `iy1 iu6 io3 in1 ip0` on both projects: **57 passed, 23 skipped, 0 failed**. Lint 0 errors,
0 warnings; build green; copy standard exit 0; `scripts/gate.sh` (all) **GATE PASSED** (root 783, api 40).

## 5. Edits outside my files

`api/league_lab_api/main.py`, the blog's block: a 503 shell gets `Retry-After: 5` and `no-store`.

## 6. PO lines

None.

## 7. Found, not mine

The pool has four connections, so a busy minute can still make reads fail. Now they fail soft. Whether the pool should
be larger is IU-4's `db.py`.

## 8. Next

1. On the live log, count `blog: … not read (…)` warnings per day.
2. On the live page, check that X's card has no white bar (`scrolling="no"`), that its video goes full screen, and that
   a post opened in a background tab shows when you switch to it.
