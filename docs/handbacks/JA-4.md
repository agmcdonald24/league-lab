# JA-4 — small faults on game-day screens (Wave J-A)

**Start 01:55 ET, Monday 2026-10-12 (read from `date`); end 02:20.** Branch `dev/JA4` (from `integ/JA` = IZ-4 merged +
JA-1 … JA-3, `bdc4e87`), `/home/claude/wt-iq4`, database `league_lab_iq4`. The app only on provider fixtures; news off
or stubbed (the tests stub `news.recent`; the e2e routes the news read).

## 1. Done / not done / cut

* **Done — 1. News on Waivers' top claims, without making Waivers wait.** `/api/waivers` is unchanged (it reads no
  news). After the claims show, the screen asks `GET /api/news/players?ids=…` for the claim players (the three strongest
  and the one in focus: at most four gsis ids, validated; the `read` bucket, explicit in `bucket_for`; `Cache-Control:
  private, max-age=60`): the feed's own reader (`news.recent` — the per-player cache My Week's reads fill, at most one
  second for what is not cached). A line lands on its claim through My Week's component (`DecisionNews`, IZ-4's words);
  no line, or a failed read, is no line. The claims render while the read waits (e2e holds the answer back).
* **Done — 2. Sentences, not a status in brackets**: the trade's depth / refuse reason (`decisions.ir2_depth`, II-1's
  words via IR-2) — `because_words` / `cannot_sentence`; the other places that built a reason that way: the card's
  roster line (IZ-3's "(bye)") and My Week's fallback (`cant_words`, "can't play (…)"). Grepped: `TradeCalc.svelte`'s
  struck-through drop "(why)" and `Trades.svelte`'s rejected row "(partner team)" are labels, not a status in a sentence:
  left.
* **Done — 3. The trade's section 5, a role note per player** (QB / RB / WR / TE): `roles.role_change`'s headline (the
  card's Role block reads the same function on the same rows) and his latest game cut short this season (the game log's
  `left_early` and `onfield.left_early_case` words), as `roles` on `/api/trades/evaluate`; one line under the player
  ("Role: … · Week 4: Left early: …"). Nothing new computed; a kicker or defense has none; a failed read is no line.
* **Checked — 4.** JA-1's Stats CSV name already carries the weeks, the comparison and the situation
  (`Players.svelte:327`: `…-stats-2026-weeks-3-4-wrs-vs-weeks-1-2-when-trailing.csv`): nothing to do.
* **Not done**: the saved partners answer `web/fixtures/trades_partners_9000000000000000001_3_RB.json` still holds the
  old bracketed words (a recording; no spec reads them; re-recording it would change much more than the words).

## 2. Commits

`JA-4: 1.` the news read · `JA-4: 2.` the sentences (test_ir2, test_iz3 on purpose) · `JA-4: 3.` the role note and
test_ja4 · `1bd1355` e2e/ja4, the recording, the screens, WORDS, CHANGELOG · the hand-back.

## 3. Evidence — each sentence before and after

* Trade depth, a player whose game started: "they lose Jaylen Warren, an RB who cannot play in week 4 (game started
  (bench)): no RB left on their bench who can play in week 4 (Jaylen Warren game started (bench) cannot)" → "they lose
  Jaylen Warren, an RB who cannot play in week 4 because his game has started: no RB left on their bench who can play in
  week 4; Jaylen Warren's game has started, so he cannot be moved this week".
* A bench player ruled out: "… who can play in week 4 (Breece Hall Out cannot)" → "…; Breece Hall cannot play in week
  4: he is ruled out". IR slot: "(arb4 in the IR slot cannot)" → "; arb4 cannot play in week 5: he is in the IR slot".
* The card's roster line: "Can't play for you this week (bye)." → "Can't play for you this week: he is on a bye."
* My Week's fallback (a reason none of its words covers): "<name> can't play (<reason>)" → "<name> cannot play this week
  because he is listed doubtful" for a known status, "<name> cannot play this week: <reason>" otherwise.
* Section 5, Stafford (the Folk trade): (no line) → "Role: Too early to say: 4 games with a snap so far this season; a
  change is called from his last 2 games against at least 3 before them (5 games)."; Ja'Marr Chase (test): "… · Week 4:
  Left early: 15 snaps (20% of the team's; usually 94%); hurt on a play in the 2nd quarter".
* Waivers: the claims, then (when the feed has an item about a claim player) "News <headline> · <source> ↗ · N h ago" and
  "Context only: not in the projection" under the claim. No recorded news exists about a fixture claim player, so the
  screens show the real state (no line) and the e2e's line is a labelled test line.
* Screens: `docs/handbacks/ja4/ja4-{waivers-claims,trade-section5}-{375,1300}.jpg`; no sideways scroll at 375 (asserted).

## 4. Tests

* New: `api/tests/test_ja4.py` 6 passed (the claim news route: bounded, validated, the `read` bucket, a failed read is no
  line; **the Waivers answer identical with the news on and off**; the sentences have no bracket; the role note is the
  card's headline and the game log's words, none for a kicker, a failed read is no note).
* The API files of the changed code (test_ir2, test_iz3, test_iz4, test_ja4, test_ix5 — the Folk trade —, test_in5,
  test_ix4, test_ii1, test_if1, test_ib2): 276 passed, 10 failed; the 10 re-run with `bdc4e87`'s sources: 10 failed —
  **no new failure**. Updated on purpose: test_ir2 (the IR-slot depth sentence), test_iz3 (the roster line). **Cut for
  the clock**: the broad set of every file that calls `/api/waivers`, `/api/my-week` or the trade route (71 files, about
  22 minutes here; started, stopped at 15 % without a comparison against the base) — the PO's full run covers it.
* e2e on fixtures, both projects, the 48 spec files that open Waivers, the calculator, My Week or the card (ja4
  included): **438 passed**, 0 failed. Other packages' screenshots it rewrote (in1, in5) restored.
* ruff, the copy standard, `npm run lint`, `npm run build`: clean. `scripts/gate.sh`: ok (79 s, exit 0).

## 5. Edits outside my files

`api/league_lab_api/main.py` (the router, a marked block; the trade route's one line), `ratelimit.py` (`bucket_for`, a
marked block), `decisions.py` (the depth sentence and its two helpers), `myweek.py` (`cant_words`' fallback),
`player.py` (the roster line's "out" words), `web/src/routes/Waivers.svelte`, `decisions/ClaimCard.svelte`,
`decisions/TradeFive.svelte`, `docs/WORDS.md`, `CHANGELOG.md`.

## 6. PO lines

None needed. `app/whats_new.md` (optional): "A claim on Waivers now shows the latest news about the player, and a trade
names each player's role trend."

## 7. Found, not mine

* `web/fixtures/trades_partners_9000000000000000001_3_RB.json` (a saved answer) keeps the bracketed words until it is
  re-recorded.
* A role note is read from `fct_player_game` through the week before the trade's first week; the card reads through
  the week itself — the same rows (an unplayed week has none).

## 8. Next

Re-record the partners answer with the next fixture refresh.
