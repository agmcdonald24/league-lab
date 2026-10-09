### IU-3 — small things that make screens disagree or read oddly (Wave I-U, 2026-10-09)

Task: `/home/claude/waveIU/BRIEF.md` § IU-3. Branch `dev/IU3` from `main` `99fb216`, worktree `/home/claude/wt-iq2`,
database `league_lab_im4` (the real 2026 board; Sleeper directory copy of 2026-10-05 12:00 UTC; real clock: week 5).

**Done**: 1 (start/sit), 2 (the card's rate words, the chart's reason), 3 (Trends), 4 (About's saved answer), 5 (the
table, and the format strings on My Week / Team / Waivers). **6 (MFL's cold load): profiled, nothing changed** — the
largest piece is not avoidable by a format or a cache I own; below. **Nothing the nightly reads changed** (no dbt
model, no `project` input, no solve: `league_status.note` gained a `rate_words` key that only the API reads), so the
chain was not run.

#### 1. Start/sit for a quarterback whose starter was set by hand or is unclear

`rankings_api.start` asks the trade verdict's rule (`provenance.caveats_for` / `effect`) through `start_caveats`, with
the caveat in a start/sit's words (the trade's sentence kept as `verdict_words`); the answer carries `caveats` and
`caveat_effect`. Set by hand → the call stands, as a lean that says whom it assumes (`answer.caveat`,
`verdict_unqualified`, `words_unqualified` kept); unclear → no call (the rows' own `starter_unclear`, unchanged).

| Ask (League of Scrubs, week 5) | Before | After |
|---|---|---|
| Darnold (SEA, set by hand) vs Goff | clear — "Start Goff: he outscores Darnold in 70 of 100 such weeks — a clear call, not a sure one." caveats: none | clear, softened — "… not a sure one. **Read it as a lean: Seattle's starter was set by hand (Sam Darnold, not the listed Drew Lock), and this call assumes Darnold starts.**" `caveat_effect` soften |
| Bagent (CHI, set by hand) vs Goff | clear, 69 in 100, no caveat | the same call + "Read it as a lean: Chicago's starter was set by hand (Tyson Bagent, not the listed Case Keenum), and this call assumes Bagent starts." |
| Jalon Daniels (TB, unclear) vs Goff | no call — "Starter unclear: Tampa Bay lists Jalon Daniels … Starter unclear — no call." | unchanged words; now `caveat_effect` withhold with its caveat |
| Mayfield (TB, unclear) vs Goff | no call (as above) | unchanged; withhold |
| Allen vs Goff (no flag) | a lean, 56 in 100 | unchanged, no caveat |

Screenshots: `docs/handbacks/iu3/start-handset_{375,1300}.jpg`, `start-unclear_{375,1300}.jpg` (Compare's "Who should
I start?", which draws `answer.words`: no web change).

#### 2. The card

* **Rate words**: `league_status.note(block, position=…)` carries `rate_words` (`availability_gate.short_words`, the
  Rankings row's words, by position); the card's Availability line after a flag: "⚠️ **Questionable (hamstring) ·
  ESPN, Oct 8**. Questionable: about 7 in 10 play." (WR; QB "about 1 in 2"). A player who sits keeps his reason, not
  a rate. `player.status_note` passes the position (the watchlist row gets the key too, unused). No Questionable
  player has a current word on this copy (its directory's game statuses are week 4's), so this is shown by
  `test_iu3.py`, not on the database.
* **The chart**: a week with `sits` (IT-3's field) is described "Week 5 vs CIN: not played yet · 0, he sits: IR (knee
  - acl) · Sleeper, Sep 28" instead of "projected 0.0 (0.0–0.0)" (`PointsChart.svelte`).

#### 3. Trends and a player who sits

Rule (the Rankings'): a player who sits this week — cannot play, or a status that rarely plays (Doubtful) — is not a
"due" or "hot" call this week; he is listed under `availability.left_out_players` with his reason; his season trend is
not touched. Trends now asks `league_gate` (the stored record + Sleeper + ESPN + the week's report) instead of the older
overlay's snapshot with `NOT_IN_TRENDS` (which kept Doubtful listed and, with the overlay off, nothing at all).

On this copy (both house leagues, all positions, overlay off): **before** 453 players listed, 0 left out — 20 players on
injured reserve were in the list (A.J. Brown, Jordan Mason, De'Von Achane, Travis Etienne, Jaxson Dart, David Njoku …);
**after** 433 listed, those 20 left out with "IR (…) · Sleeper, <date>". The top five by momentum are unchanged (Cody
White, Kyle Williams, Darren Waller, Jordan Addison, Matthew Stafford). No Doubtful player has a current word on this
copy; on the live site a Doubtful player (unlikely) now leaves the list the same way.

#### 4. About's saved answer

`web/fixtures/ir4/api_ir4.json`: the two `/api/about` entries re-recorded from the app on `league_lab_im4` with the
clock pinned in week 5 (`LEAGUE_LAB_NOW=2026-10-08T16:00:00Z`, IR-4's recipe), in the file's own shape (26 lines
changed); the clause now reads "At quarterback 61 in 100 against 60 for his own record: the smallest margin of the
four." The spec (`web/e2e/ir4/fixtures.spec.ts`, About test) reads the quarterback clause from the saved answer and
asserts the screen shows it — no sentence is written in the spec.

#### 5. One rounding on every screen

Where a projection, a gain and a total are printed (web), and with how many decimals:

| Screen | Projection | Gain / margin | Total |
|---|---|---|---|
| Rankings (week) | 1 (`fmt.pts`) | — | — |
| The card (head, projection block) | 1 (`headNumber` / the "Projected" tile) | — | — |
| Waivers (browse, cards) | 1 (`f1`) | 1 with a sign (`s1`: "+1.2", the true minus); the closest-call margin **2 → 1** | 1 (`f1`, lineup value) |
| Team | 1 (`f1`) | the roster row's margin **2 → 1** | 1 (`f1`) |
| My Week (`LineupTable`) | **2 → 1** | margin **2 → 1** | the summary sentence's total is the API's words ("Your best lineup projects 97.54 …"): left |
| Trades / the calculator | IU-1's screens: not touched | | |

Rule, the screens' own majority: **projections one decimal, gains one decimal with a sign, totals one decimal.**
Applied where it is a format string (`LineupTable.svelte`'s `num` and margins, `Team.svelte`, `Waivers.svelte`); the
`ig1` spec's "no bare 0.00" guard became "no bare 0.0". **Left** (contract or words, not format strings): My Week's
summary sentence written by the API with two decimals ("Your best lineup projects 97.54 in week 5"),
the trade screens (IU-1), `lineup_value` in the console pages (PO). `scripts/` reads none of these (grepped); the e2e
specs that read a lineup number were checked (`ig1` updated; the full run below).

#### 6. MFL's cold load (`mfl:70587`, team 1, My Week) — profiled, not changed

In a process already warm from another league (as the live server is), MFL's first load is **1.15 s** here (warm
0.17–0.32 s); in a cold process 2.4 s (imports and the pool's first connections). Of the 1.15 s: the two roster contexts
0.63 s (of which pricing the NFL-wide board in MFL's scoring once, `price_board`, 0.28 s — then cached 10 minutes), the
cards 0.22 s, the lineup rows 0.10 s, MFL's own calls 0.12 s (fixtures here: on the live site these are network calls
to MFL, which is the likeliest part of the 4.2 s the sandbox cannot measure). Every NFL-wide query is under 40 ms
(lines 37 ms, ranges 20 ms, status 19 ms). Nothing here is a large avoidable piece I own: cut. Next: time MFL's
own calls on the live server (the API's timings already split `sleeper` / `priced` / `solve` / `frame`).

#### Tests

* New: `api/tests/test_iu3.py` 3 passed (start/sit's caveat words for both kinds and the withhold effect, a failing
  flag source costs nothing; the card's rate words by position and the reason for a player who sits; Trends asks
  `league_gate`). Nothing cached between tests. `tests/test_is2_league_status.py`: the note's expected dict gained
  `rate_words` (updated on purpose) — 9 passed.
* API files of the modules I edited (`test_iu3`, `test_it3`, `test_is2`, `test_parity`, `test_player`, `test_myweek`,
  `test_research`, `test_ip2`, `test_iq2`, `test_ir1`, `test_ir4`, `test_it2`, on `league_lab_im4`): 3 failed / 162
  passed — all 3 in the known list (`test_myweek::test_worked_example_dynasty_12`,
  `test_research::test_trends_route[both leagues]`, which fails at "three games played → an early read": data state).
  **`test_parity` passes**: no console diff is required.
* Root suite (`check_root.sh`): 4 failed / 1705 passed / 3 skipped, **0 new** (the first run's one new failure was the
  note test above, fixed).
* `scripts/gate.sh python`: GATE PASSED (root 783, api 34, ruff). ruff and the copy standard clean; `npm run lint` 0
  errors (207 files); the build.
* **e2e, the whole fixtures suite** (My Week, Team, Waivers, the card, Compare and About are opened by most specs; both
  projects): **599 passed, 17 skipped, 0 failed** (13.2 m). The rewritten handback screenshots were checked out again.

Screenshots (`docs/handbacks/iu3/`, JPEG q70, 375 and 1300, the API on `league_lab_im4`): `start-handset_*`,
`start-unclear_*`, `myweek-lineup_*` (one decimal: K. Williams 19.3, "margin 10.3 over Croskey-Merritt"). No sideways
scroll, no page errors. No card screenshot: no Questionable word is current on this copy, and the chart's reason shows on
a tap of the week.

#### Edits outside my files

* `api/league_lab_api/rankings_api.py` — the start handler (mine today): `start_caveats` and two marked `# ---- IU-3`
  blocks in `start`.
* `web/src/components/card/PointsChart.svelte` (the card), `web/e2e/ig1/fixtures.spec.ts` (the "no bare 0.00" guard at
  one decimal), `web/e2e/ir4/fixtures.spec.ts` and `web/fixtures/ir4/api_ir4.json` (item 4), `CHANGELOG.md`,
  `docs/WORDS.md`, `tests/test_is2_league_status.py`.

#### The PO's lines

None required. For the console's player page to say the rate as the API card does (`test_parity` passes today because
no parity case has a current Questionable word), `app/pages/0_Player.py`:

```diff
-gate_note = LS.note(_blk)
+gate_note = LS.note(_blk, position=p["position"])                                    # IU-3: the position's rate
@@
-    _words = f" {gate_note['words']}" if gate_note and gate_note.get("sits") and gate_note.get("words") else ""
+    _words = (f" {gate_note['words']}" if gate_note and gate_note.get("sits") and gate_note.get("words")
+              else f" {gate_note['rate_words']}." if gate_note and gate_note.get("rate_words") else "")   # IU-3
```

#### Found, not mine

* My Week's summary sentence prints its total with two decimals ("Your best lineup projects 97.54 in week 5") — it is
  the API's words (`myweek.py`); one decimal there changes a sentence the console page mirrors (parity): a PO call.
* Trades and the calculator print their own decimals (IU-1's screens).

#### Next

The card's chart could also say the reason without a tap (a line under it for the card's week); a Questionable player's
rate beside the chip in the card's head (`CardHead.svelte`); MFL's own calls timed on the live server.
