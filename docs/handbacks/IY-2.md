# IY-2 — the post from X shows by itself, at its real size (Wave I-Y) — hand-back

Started 13:33 ET, finished 13:52 ET. Branch `dev/IY2` from `main` `57d587c`, worktree `/home/claude/wt-iq4`.

## 1. Done / not done / cut

All seven items are done. Nothing was cut.

1. **No tap.** Our card (words, "Name (@handle) · date", "Open on X") is the block from the first paint.
   - An `IntersectionObserver` with `rootMargin: 600px 0px` makes X's frame once per block, when the block comes within
     600 px of the screen.
2. **The swap.** On X's first `twttr.private.resize`, the frame takes the card's place at that height and the card is
   removed. The origin and the frame are checked, as before.
   - "Open on X" stays under the frame. Later resize messages keep adjusting the height.
3. **No answer.** If no resize arrives within 10 s, the hidden frame is removed and the card stays. Nothing animates.
4. **Width and backdrop.** The frame is `width: min(550px, 100%)` on the column's left edge, with `color-scheme: light`.
   It uses `theme=dark` when the page is dark.
5. **YouTube.** The block shows the video's own still under **▶ Play the video**:
   `https://i.ytimg.com/vi/<id>/hqdefault.jpg`, the id checked, `loading="lazy"`, `referrerpolicy="no-referrer"`,
   empty alt, filling the 16:9 box.
   - A still that fails to load is removed, leaving the grey block.
   - The player still loads only on the tap. `security.py` is unchanged.
6. **The editor.** Its preview is the same component (`PostBody`), so it behaves the same.
   - "Show the post" is gone from the code, tests, WORDS.md and BLOG.md.
   - The help line now ends: "It shows as the reader will see it: the post from X by itself, the video when tapped."

**How the frame is kept out of sight, and why X can still lay it out.**
- **What I chose.** The frame sits inside the `position: relative` figure as `position: absolute; top: 0; left: 0;
  height: 100%` — exactly the card's own box. It is at its real width, with `opacity: 0`, `pointer-events: none`,
  `aria-hidden="true"` and `tabindex="-1"`.
  - It takes no room, so the figure's height is unchanged (tested).
  - It cannot be seen, clicked or focused.
- **Why not `visibility: hidden` or `height: 0`.** Chrome throttles the rendering of a cross-origin frame it counts as
  not visible: `display: none`, `visibility: hidden`, zero area, or off screen. X sends its size only after it paints;
  you saw no resize at all while the tab was hidden. Either of those choices would very likely never get the resize
  message. An opacity-0 frame over the card's box is laid out at its real width and counts as on screen whenever the
  card is.
- **The cost.** Chrome still throttles the frame while it is off screen, which includes the 600 px of approach. So the
  document, data and scripts load early, but X's paint and resize may wait until the card itself is on screen. Then the
  swap is one paint away, not a network round trip.
- **Not verified here.** That real X sends `twttr.private.resize` from an opacity-0 frame. The sandbox has no route to
  X; it is the first thing to look at live (§ 8).

## 2. Commits

- `02725ac`: the card first, the out-of-sight frame and the swap, the give-up timer, the YouTube still, words and docs,
  the reworked `web/e2e/iy1`.
- The next commit: `iu6` follows the new blocks.
- The last commit: this file and the CHANGELOG.

## 3. Evidence

The post-page test uses Andrew's paste, 30 paragraphs above it, a second X post (bare link), two YouTube pastes and a
forged blockquote. X's address is answered by a stub page that sends `initialized` and `results` only.

| moment | what the page holds |
| --- | --- |
| far from the screen | the card, no `<iframe>`, no request to X |
| 300 px under the screen | one frame, `data-x-frame="waiting"`, src `https://platform.twitter.com/embed/Tweet.html?id=1666992852084092930&dnt=true&theme=light\|dark`, the sandbox, `no-referrer`, `aria-hidden`; computed `opacity: 0`, `position: absolute`, `color-scheme: light`, `pointer-events: none`; the figure's height unchanged (±1 px); the card visible |
| after X's `initialized` and `results` | still the card; the frame still waiting |
| a resize posted by our page (another origin) | nothing |
| a resize from the second post's frame (another window) | that frame shows; ours stays waiting, its card visible |
| X's first resize, 746 | the frame shown at 746 px, `opacity: 1`, in flow, width `min(550, column)` ±0.5 px, on the column's left edge; the card gone; "Open on X" visible |
| a second resize, 812 | 812 px |
| no resize, then 9 s on a fake clock | the frame is still there |
| 10.5 s on a fake clock | the frame removed; the card and its words stay |
| YouTube | the still loaded (a stub picture), 16:9 ±0.05, no frame before the tap; the other still refused → removed, grey block, button still there; the tap makes the youtube-nocookie player |
| at 375 | no sideways scroll |

- Outside requests across the whole test: only the Tweet.html stub, `i.ytimg.com/vi/…` and, after the tap,
  youtube-nocookie.
- Screens are in `docs/handbacks/iy2/`: the card, and after the swap, at 375 and 1300. After the swap the frame holds the
  test's stub, a dark page reading "X's post would show here.", because the sandbox cannot reach X.

## 4. Tests

- **e2e `iy1`** (reworked): **9 passed, 5 skipped** (the pure tests run once, on desktop) on both projects.
- **e2e `iy1 iu6 io3 in1 ip0`**, both projects: **55 passed, 23 skipped, 0 failed**. The skips are the pure tests and
  the desktop-only tests on the phone project.
- **`iu6`**: two expectations follow the new blocks, the still and X's frame waiting out of sight.
- **Checks:** lint 0 / 0, build green, copy standard exit 0, `scripts/gate.sh` (all) **GATE PASSED** (root 783,
  api 40, ruff, web lint, build).

## 5. Edits outside my files

`api/tests/test_iu6.py`: one docstring. Nothing in `security.py`.

## 6. PO lines

None.

## 7. Found, not mine

Nothing new.

## 8. What to look at on the live page

1. **The resize.** Does real X send `twttr.private.resize` to the opacity-0 frame once the card is on screen? If it
   never does, the card simply stays and the frame is removed after 10 s. Nothing breaks, but the post never shows.
2. **The swap.** Is it clean: no empty box, no jump other than the card's height becoming X's?
3. **The backdrop.** On a dark system theme, is the area beside X's 550 px card transparent, with no white?
4. **The YouTube still.** Does it show, and play on the tap?
