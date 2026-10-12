# IZ-4 — news on the decision it affects (Wave I-Z)

**Start 19:42 ET, Sunday 2026-10-11 (read from `date`); end 20:10.** Branch `dev/IZ4` (from `integ/IZ` = IX-4 merged +
IZ-1 … IZ-3, `29ebb94`), `/home/claude/wt-iq4`, database `league_lab_iq4`. The app only on provider fixtures, news only
from saved answers (`LEAGUE_LAB_NEWS=off`; the tests stub `news.recent`).

## 1. Done / not done / cut

* **Done — 1. My Week** (`decision_news.attach`, run in `myweek.finish`, so both paths): a feed line whose player is in a
  decision — an action's start / sit (a roster alert names him; either player of a close call), a "no clear upgrade"
  line's two players, an action's past three (behind More) — moves onto that decision as `news` (at most two, the
  newest first) and `news_more` (the rest, under the call's "Why?"; a review line's "More news"). The line is the feed's
  own (II-4's words, source, time and forecast words: "Context only: not in the projection" where that is true). The
  feed keeps the lines no decision took (`changed.on_decisions` says how many moved) and is not drawn when none is left
  (IX-4's rule). A line about a player in two decisions sits on both.
* **Done — 2. The trade's section 5**: `/api/trades/evaluate` gains `news` ({Sleeper id: [line]}: the feed's newest item
  of the last 24 hours about each player given, received or cut — `news.recent`, its cache and its one-second budget;
  `why_here` dropped, section 5 names the side) and IZ-2's `newsFor(key)` hook draws it with the same component
  (`DecisionNews.svelte`) under the player's row.
* **Cut — 3. Waivers' top claims**: the Waivers answer has no news at hand (no `news.recent` in `decisions.waivers`); the
  line would cost a new read of up to three players on every Waivers visit (up to about a second on a cold cache, the
  ESPN bucket shared with My Week and the card). Not built.
* **Done — 4. Nothing is read from news**: `attach` only moves lines; `test_iz4` builds My Week with the feed stubbed
  off and on (an item about Kelce, in the "tight end spot is open" alert on both paths) and asserts the actions (words,
  reasons, gains, order), the review lines, the cards, both lineups, the recommendation, the summary, the win and the set
  line are identical, the item on the alert and not in the feed.
* **Done — 5. Both paths**: the same test on the house path and `source=sleeper` (on demand).
* **Not done**: no screen of section 5's line — no saved answer holds news about a saved trade's players, and I invent
  none (the line is covered by `test_iz4` and the type check). The PO's live case (Boston ahead of Jefferson, the
  pregame-workout item) is not on this copy; the evidence is the saved Jefferson case of `web/fixtures/ig2`.

## 2. Commits

`92953ef` items 1, 2, 5 · `0949ecc` test_iz4 · `8735539` the cut, WORDS, CHANGELOG · `e37a535` test_ig2 on purpose ·
`f87fa12` e2e/iz4, the recording, the screens · the line's spacing (eslint) · the hand-back.

## 3. Evidence (League of Scrubs team 2, the saved answer of `web/fixtures/ig2`, as the screen reads)

* **Before**: the call "⚠︎ Roster alert — Start Wilson at FLEX (or Croskey-Merritt: a coin flip) in place of Jefferson."
  / "Jefferson is out; the change is worth about 9 more projected points this week." and, lower, a **News feed** of
  three lines: "Justin Jefferson is out (ankle) — Michael Wilson starts at FLEX2 · Injury report (ESPN) ↗ · 9 d ago",
  "Terrance Ferguson is on injured reserve (ankle) — he was on your bench; the lineup does not change · Injury report
  (ESPN) ↗ · 9 d ago", "Justin Jefferson: Jefferson (ankle) ruled out for Sunday · Minnesota Vikings via PlayerWire ↗ ·
  8 d ago" — the manager matches them himself.
* **After**: the same call and reason, and under them "News Justin Jefferson: Jefferson (ankle) ruled out for Sunday ·
  Minnesota Vikings via PlayerWire ↗ · 8 d ago" then "News Justin Jefferson is out (ankle) — Michael Wilson starts at
  FLEX2 · Injury report (ESPN) ↗ · 9 d ago" (the newest first); the News feed keeps one line, Ferguson's (he is in no
  decision). The saved lines carry no forecast words (recorded before II-4 gave them), so none shows; a line that has
  them shows "Context only: not in the projection" under it (test_iz4). The call's words, reason, gain, the cards and
  the lineup are the saved answer's (asserted in e2e/iz4).
* The recording `web/fixtures/iz4/my-week_scrubs_2.json`: ig2's saved body for `/api/my-week?league=1389709692405551104&team=2`
  with `more_actions: []`, through `decision_news.attach(body, rows)` where `rows` is a frame of `lineup_full`'s
  (`key` → `sleeper_player_id`, `gsis_id`) — the API's own function, nothing else changed.
* Screens: `docs/handbacks/iz4/iz4-scrubs2-{before,after}-{375,1300}.jpg`; no sideways scroll at 375 (asserted).

## 4. Tests

* New: `api/tests/test_iz4.py` 6 passed (the line moves and leaves the feed; two at most, the newest first, the rest
  for Why; no lines, nothing moves; **feed on vs off identical on the house path and on demand**; the trade's line by
  player and none when the feed is off).
* The test files of every module and route changed (`myweek`, `main`'s trade route, `/api/my-week`,
  `/api/trades/evaluate`: 48 files): 594 passed, 88 failed, 15 skipped. The 88 re-run with integ/IZ's `myweek.py` and
  `main.py` (`29ebb94`): 87 fail there too; **one new**, `test_ig2::test_a_failing_store_never_fails_a_request` (it
  required the feed to hold lines; the Jefferson line is on his decision now) → updated on purpose → passes.
* Updated on purpose: `test_ig2` (above). `test_if4`, `web/e2e/if4`, `in5`, `ix4`, `iz2`: **no change needed** — their
  saved answers carry no `news` field, so they render as before (the feed shape is unchanged).
* e2e, both projects, the 29 spec files that open My Week or the calculator (IX-4's 27 + iz2 + iz4): 274 passed; after
  the line's spacing fix (it touches only the news line, drawn only in iz4) iz4 again: 8 passed.
* ruff clean; copy standard clean; `npm run lint` and `npm run build` clean; `scripts/gate.sh` ok (74 s, exit 0; a first
  run failed on two useless mustaches in the new component, fixed before this one).

## 5. Edits outside my files

`api/league_lab_api/myweek.py` (`finish`: one call), `api/league_lab_api/main.py` (the trade route: a marked block of
two lines), `web/src/lib/api.ts` (the IZ-4 block at the end), `web/src/routes/MyWeek.svelte` (the news on the action and
review cards), `web/src/routes/decisions/TradeFive.svelte` (IZ-2's hook filled), `docs/WORDS.md`, `CHANGELOG.md`.

## 6. PO lines

`app/whats_new.md`: "News about a player now sits on the call about him on My Week, with its source and time, instead
of in a separate feed."

## 7. Found, not mine

* The feed reads one item per player (`news.recent`: the newest of 24 hours), so "two on a decision" is at most its two
  players' newest items plus the status lines; a second item about the same player is never in the answer.
* No saved trade answer has news about its players (the iz2 recordings were made with the feed off).

## 8. Next

A recorded trade with a news item (from the nightly's feed) to screen section 5's line; Waivers' line if the PO accepts
the read.
