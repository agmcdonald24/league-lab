# IX-5 — what we claim, said once and truly; a simpler menu (Wave I-X)

Start 03:54 ET, end __END__ ET (2026-10-11). Branch `dev/IX5` from `integ/IX` (`d131d37`, IX-1 to IX-4), worktree
`/home/claude/wt-iq4`, database `league_lab_iq4`. Ports 8921 (this branch's API at the PO's Saturday clock, to record),
8927 (e2e).

## 1. Done / not done / cut

* **Done — 1. The trust line says each position's verdict** (`provenance._checked_words`): a span where no position is
  graded and the statuses differ now names every position with its own verdict ("two to eight weeks ahead: quarterbacks
  weak, kickers no better than chance"); was the worst status for the whole span. Table-driven test over all 63
  position sets × three spans, the sentence read back and compared with `CHECKS` (189 cases). The audit is in § 3.
* **Done — 2. "Near enough to trust" goes**: Next 4's caption (API `WINDOW_WHY`, web `decisions.ts`, Trades' how-to)
  says what METRICS says.
* **Done — 3. A kicker or defense is never the strongest move on a four-week gain** (`decisions.ix5_kd_last`,
  `ix5_guide_card`): chosen only on this week's gain, only when the graded positions leave room, listed last, its number
  this week's, a guide sentence on the card, no window total (also in Help now and My Week's claim); the heading and the
  intro count the graded claims only. The rule is in METRICS § "What we claim, said once (IX-5)".
* **Done — 4. "Fit" said as what it is**: "net lineup points" (his new team's gain minus his old team's loss, the weeks
  said) on Trades' lists, their card sentences and how-to; the console's `trades.fit_line` now prints the API's
  "Improvement to your starting lineup" (the API's words since IT-1: no saved answer changes).
* **Done — 5. No internal names**: Waivers' recent adds say "Sleeper transactions" (the provider's name), not
  `analytics.mart_league_transactions`. Saved answers scanned for printed table names: none other is printed (the
  `source`/`points_source` fields that hold one are not shown).
* **Done — 6. One direction for a defense's rank**: "gives up the Nth-most" (1 = the most; "the most" / "the fewest" at
  the ends) in `research.gives_up_words`, `lib/research.ts`, `cards.rank_words` / `reason_pieces` (shared with the
  console), `lib/words.ts`; Matchups' chips and cell titles "#N of 32 vs POS"; the how-to and `RANK_NOTE`; the card help.
  Verified and left: `CardHead`/`player.py` ("#N of 32 vs POS (1 = gives up the most)"), Compare's caption and note
  (already 1 = the most), `matchup_board.TONE_WORDS` (no number), `outlook.ts` "Nth-hardest" (a fantasy team's schedule
  of fantasy opponents, not a defense's rank; one direction already).
* **Done — 7. The menu**: with a league My Week · Waivers · Trades · Research (Stats, Rankings, Trends, Matchups,
  Compare); without one Home · Rankings · Research · Trades; DFS in the ⋯ menu (`menu-dfs`), its route unchanged; tab
  keys and test ids kept; eyebrows "Research · Stats" / "Research · Rankings".
* **Done — 8. The known trade**: `test_the_known_trade_stays_fixed` (Scrubs, team 2 gives Folk for Stafford + Reichard):
  reconciliation of headline, summary tiles and weekly table, no cross-position explanation, implausible, the trust
  line's QB / K words.
* **Done — 9.** Tests, saved answers, WORDS, METRICS, CHANGELOG.
* **Not done / cut**: the plausibility label "A roster-fit idea" keeps "fit" (a label, not the number; 59 saved answers
  pin it) — see § 8.

## 2. Commits

`ac2d731` 1 · `581262e` 2 · `8d30dbf` 3 + 5 · `ba4ccff` 4 · `dde4145` 6 · `6589717` 7 · `82daf0f` 8 · `995d48e` docs ·
`a0b8ab0` test_ie_po · `dc82c9d` e2e, recordings, screens · the hand-back.

## 3. Evidence

**The audit (item 1): each sentence about what has been checked, its number (METRICS § IR-4), what changed.**

| Sentence (where) | Number behind it | Change |
|---|---|---|
| trust line, per span and position (`provenance.block`, every analysis) | next week QB .587 RB .686 WR .618 TE .599 graded; K .095 DEF .257 weak; 2–8 weeks QB .495 weak, RB/WR/TE graded, K .028 DEF .040 chance | the mixed, none-graded case names each position (was the worst for all) |
| Next 4's caption (calculator, Partners, Trades' how-to) | next four weeks RB .660 WR .594 TE .564; QB .538 vs his record's .537; K/DEF not pooled (.095/.257 then chance) | "far enough to matter, near enough to trust" → "RB, WR, TE graded; QB a lean, level with their own record; K and DEF a rough guide, no better than chance after next week" |
| `ros_grade.WORDS` (QB misses about 7.4 two to eight weeks ahead, 6.4 next week; RB/WR/TE about 0.2 more) | 7.41 / 6.44; +0.18 / +0.15 / +0.16 | none (true) |
| `KD_WORDS`, `KD_CALC_WORDS` (K/DEF order 2–8 weeks no better than chance) | .028 / .040 | none (true) |
| About's per-position rows (`STATUS_WORDS`) | the same table | none |
| `USEFUL_WORDS` (WR / RB / TE / QB .584 / .575 / .555 / .613 against his record's .539 / .552 / .524 / .595) | METRICS § useful decision + PO's IT-5 QB re-grade | none (true) |
| Waivers' guide sentence (new) | K .095 / DEF .257 next week; .028 / .040 after | new |
| (noted, not changed) the per-check words' order for RB/WR/TE 2–8 weeks reads `CHECKS` .636/.569/.545 (IR-4's run on the rows with a record) against the table's .633/.568/.540 (IQ-1's cells) | same status | § 7 |

**Before → after (the ten that matter most):**
1. Calculator, Folk trade: "two to eight weeks ahead no better than chance, quarterbacks weak" → "next week graded,
   kickers weak; two to eight weeks ahead: quarterbacks weak, kickers no better than chance".
2. Next 4: "the next four weeks: far enough to matter, near enough to trust" → "the next four weeks: running backs,
   receivers and tight ends graded; quarterbacks a lean, level with their own record; kickers and defenses a rough
   guide, no better than chance after next week".
3. Waivers, Scrubs team 2 (this database, week 5): the three were Brissett, Hockenson, **Patriots DEF +13.65 over weeks
   5–8**; now Brissett, Hockenson, Robinson/Dowdle (RB; the defense stays in Help now on this week's +4.28).
4. Waivers, MFL 70587 team 8: "The three strongest claims below …" → heading "The two strongest moves", intro "… After
   them, a kicker or defense for this week only: a rough guide."; the Saints DEF card "+0.1 this week" with "Kickers and
   defenses are judged on this week only: their projections are a rough guide (weakly graded for next week, no better
   than chance after)."
5. Trades' lists: value "Fit" / "Fit weeks 4–7" → "Net lineup points"; "(fit **+9.9** over weeks 4–7): the fit, from the
   projections, is the reason …" → "(net **+9.9** lineup points over weeks 4–7: your gain minus their loss): that, from
   the projections, is the reason …"; "best fit X" → "worth most to X".
6. Matchups chip: "#31 toughest vs RB" → "#2 of 32 vs RB"; answer "gives up the 2nd-fewest to WRs" → "gives up the
   31st-most to WRs"; how-to "#1 is the toughest for the offense" → "#1 gives up the most points to the position".
7. Cards (console and web): "who give up the 7th-fewest points to running backs" → "the 26th-most"; "2nd-fewest WR
   points allowed" → "31st-most WR points allowed".
8. Waivers' recent adds: "· analytics.mart_league_transactions" → "· Sleeper transactions".
9. Tabs with a league: "My Team · Waivers · Trades · Players · DFS" → "My Week · Waivers · Trades · Research"; without:
   "Home · Rankings · Players · Trades · DFS" → "Home · Rankings · Research · Trades"; DFS in ⋯.
10. Console simulator: "**Fit** (what the best lineups gain): you …" → "**Improvement to your starting lineup** (best
    lineup each week): you …".

Screens (375 and 1300, JPEG): `docs/handbacks/ix5/` — the menu with a league and browsing (⋯ open), Waivers (Scrubs),
the MFL guide card, the calculator's trust line, Matchups. No sideways scroll at 375 (asserted).

## 4. Tests

* New `api/tests/test_ix5.py`: 199 passed (189 trust-line cases, caption, K/DEF rule and intro, Fit, the two house
  leagues' Waivers on the database, the known trade).
* The test files of every module and route changed (`provenance`, `decisions`, `research`, `context_record`, `cards`,
  `/api/waivers`, `/api/trades/*`, `/api/matchups/*`, `/api/compare`: 74 files): 1,237 passed, 103 failed, 25 skipped.
  The 103 re-run on `d131d37`'s code and tests (exported): 102 fail there too (week-4 state at the pinned clock on a
  copy holding week 5; corner regulars). **New: 1** — `test_ie_po::test_top_three_claims_are_ordered_by_this_weeks_gain`
  (MFL team 8's Saints guide card now last by design) → updated on purpose, passes.
* Updated on purpose: test_ir4 (none needed), test_ib3, test_ia1, test_if3 (one direction), test_ip3 (net lineup
  points), test_ie_po; root test_trades, test_trade_finder_page (fit_line), test_matchups (one direction).
* Root suite (`check_root.sh`): 4 failed (all known), 1,750 passed — **no new failures**.
* ruff clean; copy standard clean; `npm run lint` and `npm run build` clean.
* e2e: `e2e/ix5` 12 passed (phone + desktop). All fixture specs (the tabs are on every screen): __E2E__.
* Saved answers updated on purpose (only the changed words): 41 (`window_why`), 8 (Fit sentences), 47 (Nth-fewest →
  Nth-most, n = 32; the card help and the rank note); new `web/fixtures/ix5/api_ix5.json` (recorded).
* `scripts/gate.sh`: __GATE__.

## 5. Edits outside my files

`app/lib/cards.py` (`reason_pieces`, `rank_words`, the card help: the console's mirror changes with it — its Home and
Start/Sit cards print "the Nth-most"; parity tests pass), `src/league_lab/trades.py` (`fit_line`),
`api/league_lab_api/context_record.py` (one sentence), `web/src/routes/Players.svelte` and `Rankings.svelte` (the
eyebrow only), `web/src/lib/feed.ts` (`topIntro`), `TopBar.svelte`, `TradeCalc.svelte` (one sentence), `ClaimCard.svelte`
(the guide line), the e2e specs listed in § 4, WORDS, METRICS, CHANGELOG.

## 6. PO lines

`app/pages/6_Trade_Finder.py` (console, PO-owned) still says "Fit":

```diff
-    "**Fit** is what the starting lineups gain. **Market** is what the players are worth on the market: their projected points "
+    "**Improvement to your starting lineup** is what the best lineups gain over the weeks. **Market** is what the players are worth on the market: their projected points "
-           "the gap was no reason to trade on its own. Both lists are ordered by lineup fit, from the projections.")
+           "the gap was no reason to trade on its own. Both lists are ordered by net lineup points, from the projections.")
-      "fit_week": Col(f"Fit · {wk}", "signed1", "You gain minus they lose, this week"),
-      "fit_horizon": Col(f"Fit · {span}", "signed1", f"You gain minus they lose over {span_words}: the lineup points the trade creates")}
+      "fit_week": Col(f"Net lineup points · {wk}", "signed1", "You gain minus they lose, this week"),
+      "fit_horizon": Col(f"Net lineup points · {span}", "signed1", f"You gain minus they lose over {span_words}: the lineup points the trade creates")}
-        "fit_week": Col(f"Fit · {wk}", "signed1", "They gain minus you lose, this week"),
-        "fit_horizon": Col(f"Fit · {span}", "signed1", f"They gain minus you lose over {span_words}")}
+        "fit_week": Col(f"Net lineup points · {wk}", "signed1", "They gain minus you lose, this week"),
+        "fit_horizon": Col(f"Net lineup points · {span}", "signed1", f"They gain minus you lose over {span_words}")}
-    "it, so it is no reason to trade on its own. Both lists are ordered by **Fit**, from the projections. Filter by "
+    "it, so it is no reason to trade on its own. Both lists are ordered by **net lineup points**, from the projections. Filter by "
-    "**Fit** is what the new team gains minus what the old team loses. A big positive fit means he matters more to the other "
-    "team than to his own: an easier ask when you buy, a better sale when you sell.",
+    "**Net lineup points** is what his new team's best lineup gains minus what his old team's loses, over the next four "
+    "weeks. A big positive number means he matters more to the other team than to his own: an easier ask when you buy, a "
+    "better sale when you sell.",
```

`app/whats_new.md` (one line, if wanted): "What we claim is said once: each position's check by name, no 'near enough to
trust', kickers and defenses judged on this week on Waivers, 'net lineup points' for Fit, a defense's rank one way
(1 = gives up the most). The menu is My Week · Waivers · Trades · Research; DFS is in the ⋯ menu."

## 7. Found, not mine

* `provenance.CHECKS` RB / WR / TE two to eight weeks ahead carry IR-4's run on the rows with a record (.636 / .569 /
  .545, misses 4.73 / 4.62 / 3.42) while METRICS' table prints IQ-1's cells (.633 / .568 / .540, 4.70 / 4.59 / 3.41); the
  per-check words show "(order 0.64)". Same status; one source would be cleaner.
* `test_if3` (3) and `test_ig2` (2) fail on the base too: the database's Carolina corners now list Will Lee III as a
  regular (data, not words).
* The old saved answers (`waivers_*.json` at the fixtures' root) were recorded with a defense among the three; the
  screens that read them show it without the guide (no API re-run behind them). Re-record when the fixture weeks move.

## 8. Next

* "A roster-fit idea" (plausibility label) → "A lineup idea (no market price)" with its 59 saved answers.
* The console page lines in § 6.
