# IX-4 — My Week: one matchup number, the lineup it is, three decisions (Wave I-X)

**Start 03:13 ET, Sunday 2026-10-11 (read from `date`); end 03:52.** Branch `dev/IX4` (from `integ/IX` = IX-1 … IX-3,
`bb03c90`), `/home/claude/wt-iq4`, database `league_lab_iq4`. Ports 8921–8923 (the API at three clocks), 8927 (e2e).

## 1. Done / not done / cut

* **Done — 1. One matchup summary** (`myweek.matchup_summary`, both paths; the web's `matchupOf` builds the same words
  for an answer saved before it). Before either side's first kickoff: "Week 5 vs **X**: you project 98, they project
  122." + "Each side's best lineup by our projections." + the chance without totals ("You're a clear underdog this
  week: 31%."). Once a starter of either side has kicked off (`kickoff_at` ≤ the request's clock: `win.n_started` /
  `opp_n_started`, new): "… 122 to 183 expected." + "Points scored so far plus projections for players still to play
  (9 of your 10 have played, 8 of theirs)." — "(a game has kicked off; no points are in yet)" before the first points;
  every starter played: the score, no chance. IH-3's opponent line and win line are gone; the league line keeps the
  rank only ("Your best lineup ranks 10th of 10 in the league in week 5.", `cards.league_line`: the console's Home too).
* **Done — 2. Recommended lineup** (`myweek.recommend` → `recommended`): the best lineup with the calls applied (an
  injury tiebreak puts the bench player IN the slot, the other on the bench; `annotate_swaps` and its "the call above
  keeps …" flags deleted), its own **Projected total**, and where the provider's lineup is known "✓ Matches your Sleeper
  lineup." / "≠ 8 changes from your Sleeper lineup." with "≠ In Sleeper now: Jefferson" / "Open in Sleeper now" on each
  differing row (the actions' own pairing, `pair_moves` + IO-4's rule for a player who left the roster). Unknown: nothing.
  `lineup` (the best lineup on paper) is unchanged in the answer: test_myweek / test_parity compare it with the mart and
  the console.
* **Done — 3. The unclear starter on the call** (`myweek.rule_calls`, run in `league_gate.with_lineup` after the caveats,
  both paths): a call whose players include a QB or a team-QB unit of a flagged team — withheld (unclear) or a lean that
  is not clear (sources disagree, under 3 points / 70%) — reads "X or Y at team QB: check who starts first.", chip Close
  call, the caveat's sentence and the gap as its reason, "Your MFL lineup has Houston Texans QB there now."; a clear lean
  keeps its call with "Read it as a lean. …"; the row says "? Check who starts for Chicago before kickoff". METRICS §
  "Starter uncertainty in a decision" carries the rule. The review's case (Chicago team QB over Houston by 1.9) is
  `test_ix4` (unit + the MFL answer on the database) and `e2e/ix4`.
* **Done — 4. Three decisions first** (`decisionsOf`): actions + the ones past three (`more_actions`, new) + Waivers'
  claim + the "no clear upgrade" lines, by urgency (a starter who cannot play, then a change for points, then a call to
  re-check, then a claim); the rest behind **More: N other calls**. **No news card without news** (no line either).
* **Done — 5.** Every piece above runs on both paths (`finish` in `myweek.my_week` and `ondemand.my_week`).
* **Done — 6.** test_ix4 (16), specs and saved answers, WORDS § IX-4, METRICS (two notes), CHANGELOG.
* **Not done / cut**: no saved answer was re-recorded: the web derives the summary for an answer saved before IX-4
  (`matchupOf`, `rankLine`), so the old recordings show the new screen; the new recordings are `web/fixtures/ix4/`. The
  console's own Home keeps "Your lineup" over the best lineup (PO-owned; § 6). The swap → recommended path is tested by
  unit test only (no injury tiebreak on this copy's fixtures: test_ie_po's case skips).

## 2. Commits

`1f61d3e` the answer (items 1–3, 5) · `9432b12` the screen (1, 2, 4) · `abca470` tests · `dc57cf6` WORDS, METRICS,
CHANGELOG · `8f97a21` e2e, recordings, screens · `3cbcb8e` annotate_swaps deleted · the hand-back. (Items 1–5 landed in
two commits, the answer and the screen, not one per item: the pieces share one function per path.)

## 3. Evidence (Saturday clock 2026-10-10T16:00Z unless said; the review's numbers were the live site's, this copy's
Sleeper fixtures differ)

Every figure left on the screen, and which number it is:

| Figure | Number |
|---|---|
| summary, before | `lineup_value` (my best lineup's starters' projections, the overlay's re-solve) · `opponent.lineup_value` (his, the same way) |
| summary, live | `win.mine` / `win.theirs`: the best lineups' starters, points (Sleeper's / MFL's) where the game is in, projection otherwise |
| chance | `win.percent` (calibrated, unchanged) — no total beside it |
| league line | the rank of `lineup_value` in `mart_league_roster_rankings` (house leagues; none on demand) — no total |
| table rows · Margin | each starter's projection in the league's scoring · what the lineup loses without him (unchanged) |
| Projected total | `recommended.total` = the recommended starters' projections = `lineup_value` unless a call swapped a player |
| an action's points | `gain` (the change's projected points) · a close call's margin (the cards') |

League of Scrubs team 2 (MacZaddy), before → after:
* "Week 5 vs **GoodGameBuddy**, projects 122 — you project 98" + "You're a clear underdog this week: 31%, 98 to 122
  expected." + "Your best lineup projects **98.19** in week 5, 10th of 10 in the league." →
  "Week 5 vs **GoodGameBuddy**: 98 to 122 expected." / "Points scored so far plus projections for players still to play
  (a game has kicked off; no points are in yet)." / "You're a clear underdog this week: 31%." / "Your best lineup ranks
  10th of 10 in the league in week 5."
* Thursday clock: "Week 5 vs **GoodGameBuddy**: you project 98, they project 122." / "Each side's best lineup by our
  projections."; week-4 Monday clock: "Week 4 vs **GoodGameBuddy**: 122 to 183 expected." / "… (9 of your 10 have
  played, 8 of theirs)." / "You're a clear underdog this week: 1%." (projected total 115.8: projections only).
* "Your lineup" → "Recommended lineup" / "≠ 8 changes from your Sleeper lineup." / WR1 Nacua "≠ In Sleeper now:
  Jefferson", QB (empty) "≠ In Sleeper now: Mahomes", FLEX2 Boston "≠ Open in Sleeper now" / Projected total 98.2.
* 3 action cards + "More: 4 other calls" (was 3 cards + "4 more roster alerts: the lineup below shows every slot.");
  the News feed card with "Nothing has changed since the morning build." → nothing.

MFL `mfl:70587` team 8 (Big Mac Attack), before → after:
* "Week 5 vs **Uh, Winning!**, projects 100 — you project 114" + "You're a slight favorite this week: 61%, 114 to 100
  expected." + "Your best lineup projects **114.38** in week 5." → "Week 5 vs **Uh, Winning!**: 114 to 100 expected." /
  the basis / "You're a slight favorite this week: 61%." (no league line: no rank on demand).
* Roster alert "Start Chicago Bears QB at team QB in place of Houston Texans QB." / "The change is worth about 2 more
  projected points this week." (the caveat only under the table) → Close call "Chicago Bears QB or Houston Texans QB at
  team QB: check who starts first." / "We project Caleb Williams to start for Chicago, not the listed Case Keenum:
  Chicago Bears QB's projection assumes Williams starts. By our projections Chicago Bears QB is about 1.9 points ahead:
  less than a starter's week against his backup's (about 10 points)." / "→ Your MFL lineup has Houston Texans QB there
  now."; its row "≠ In MFL now: Houston Texans QB" and "? Check who starts for Chicago before kickoff"; "≠ 1 change
  from your MFL lineup."

Screens (375 and 1300, full page): `docs/handbacks/ix4/ix4-{scrubs2-before,scrubs2-live,scrubs2-played,mfl8-live}-{375,1300}.png`;
no sideways scroll at 375 (asserted); at 1300 the two columns use the width.

## 4. Tests

* New: `api/tests/test_ix4.py` 16 passed (+ test_ie_po: 1 passed, 1 skipped — no injury tiebreak on the fixture week).
* The test files of every module and route changed (`myweek`, `ondemand`, `league_gate`, `cards`, `/api/my-week`: 42
  files): 531 passed, 68 failed, 15 skipped. The same 68 re-run with integ/IX's four source files and two test files
  (`bb03c90`): 68 failed. **New failures: 0.** (They read week 4's state at the pinned clock on a copy that holds week 5.)
* Updated on purpose: test_myweek (2 asserts: the league line without the total), test_ie_po (the swap is in the
  recommended lineup, no flag); e2e fixtures.spec (3 lines: the summary's words), ia1 (the heading and caption), if4
  and in5 (no News feed card without news), ih3 (the chance in the summary; 3 tests rewritten), il2 (the live line).
* ruff clean; copy standard clean; `npm run lint` and `npm run build` clean.
* e2e on fixtures, both projects, the 27 spec files that open My Week (fixtures.spec, decisions, i0a, ia1, ib1, ib3,
  ic3, ic4, ie0, ie1, if4, ig1, ig2, ig3, ih1, ih2, ih3, ii2, ii4, ii6, ik4, il2, in5, ix4, n1, n2, v2): 256 passed, 2
  failed (in5's empty-feed title, phone and desktop) → updated on purpose → in5 10 passed. ix4: 8 passed.
* `scripts/gate.sh`: see the end of this file.

## 5. Edits outside my files

`app/lib/cards.py` (`league_line`: the rank only — the console's Home renders it); `api/league_lab_api/league_gate.py`
(`with_lineup` → `rule_calls`, two lines); `api/league_lab_api/ondemand.py` (`finish`, the import); `web/src/lib/api.ts`
(the `// ---- IX-4` block at the end); `web/src/components/LineupTable.svelte` (`total`, the two row marks); the e2e
specs in § 4; `docs/WORDS.md`, `docs/METRICS.md`, `CHANGELOG.md`.

## 6. PO lines

The console's Home loses the total with `cards.league_line` (now the rank only); to say it once, labelled, and name the
table for what it is:
```diff
--- app/Home.py
         if not rows.empty:
-            st.markdown(league_line(league_id, roster_id, week, rows))
+            lv = rows.loc[rows["role"] == "starter", "lineup_value"].dropna()
+            if not lv.empty:
+                st.markdown(f"Week {week}: your best lineup projects **{float(lv.iloc[0]):.0f}** (by our projections).")
+            if (ll := league_line(league_id, roster_id, week, rows)):
+                st.markdown(ll)
         st.markdown("**The calls that matter**")
         decision_cards(league_id, roster_id, week, season, rows=rows)
-        st.markdown("**Your lineup**")
+        st.markdown("**Best lineup by our projections**")
```
(test_parity still holds: `api["league_line"]` is in the page.) `app/whats_new.md`: "My Week says one matchup number and
what it is, names the table Recommended lineup and shows how it differs from your Sleeper lineup, and says check who
starts first on a close call at a quarterback whose starter is in doubt."

## 7. Found, not mine

* The Sleeper fixture lineup of League of Scrubs team 2 holds four players no longer on the roster (four "A player in
  your Sleeper lineup is no longer on your roster" alerts; "8 changes", one of them with no row to mark): the fixtures'
  date, not the code. On the live site the review saw Boston/Jefferson instead.
* The stored rows' `locked_now` is the build's (`kicked_off` from the nightly) and does not follow `LEAGUE_LAB_NOW`: a
  Thursday clock still marks Thursday's players locked (GoodGameBuddy's two); the summary reads `kickoff_at` against
  the clock instead.
* An MFL opponent's total moves between kickoff states (101.0 before Thursday's kickoff, 100.0 after) — his lineup is
  re-solved with the lock; the summary says the number of the moment.
* 68 tests in the My Week files fail on integ/IX already (week-4 expectations on a week-5 copy).

## 8. Next

The console's Home lines (§ 6); a saved answer with an injury tiebreak so the swap is pinned end to end; IX-5.

## The gate

`scripts/gate.sh` on `dev/IX4` (03:51 ET, after the last code commit): decision suite src ok (44 s), api ok (2 s), ruff
ok, web lint + type check ok (28 s), web build ok (4 s) — 78 s, exit 0.
