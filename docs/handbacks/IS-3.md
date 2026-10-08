# IS-3 — trade suggestions and waiver picks on the verdict's basis; the trade tests whole again (Wave I-S, 2026-10-08)

Branch `dev/IS3` from `main` `76b98df`, worktree `/home/claude/wt-ir2`, database `league_lab` read only (pinned clock
2026-10-03T16:00Z). Nothing written to any database.

## 1. Done / not done / cut

* **Done — item 4, the three `test.fixme` trade tests run again**, each on a trade that is legal on today's fixtures and
  has the same meaning, re-saved from the API (never patched):
  * `e2e/ia2/fixtures.spec.ts` "tick a player: the dial moves and its label changes" (Scrubs) and
    `e2e/ib2/fixtures.spec.ts` "the calculator keeps the decision in view" (Scrubs): the Scrubs tick package is now
    MacZaddy's Kyren Williams (8150) for Christian McCaffrey (4034, team 1); ticking Cam Skattebo (12481) as well turns
    the dial from "Improves it a lot" to "Makes their lineup weaker". Chosen by `save_ia2_fixtures.py`'s rule on
    today's rosters (players on the same roster in the saved team fixtures and in the database). Saved by
    `web/fixtures/save_ir2_fixtures.py --scrubs` (next 4 and the three other windows, both packages; the script asserts
    the label changes); `ia2_packages.json` updated by the same run.
  * `e2e/ii1/fixtures.spec.ts` "a kicker for a starter is labelled implausible": McLaughlin (6650) is gone; MacZaddy's
    kicker is Nick Folk (650), for GIBB ME ANOTA ONE's starting QB Dak Prescott (3294, team 10) — the API answers
    "Implausible: a K for a starter (Dak Prescott) …", as before. Re-recorded with `II1_RECORD` from the fixture API.
* **Item 3 — profiled, no change needed for the target**: the covered pair is already computed once per package (the
  card and the decision share `il4_sides`' frame cache). Warm: 0.057 s for a package already asked, **0.67 s for a new
  package on a warm context** (under 0.8 s); cold (context + package) 0.68–0.83 s. Of the 0.67 s, 0.55 s is the card's
  two waiver alternatives (`ii1_alternative` → `best_alternative`): the partner's add-for-drop sweep (`_fill_alternative`
  0.375 s, `best_fill` × 15) and yours (`best_waiver_move` 0.14 s); both are kept per team on the context, so a second
  package with the same partner is fast. The 1.2 s quoted in IR-2's hand-back was one cold call (context included).
* **Not done (cut for the clock)**: item 1 (the Finder's partner rows from `ir2_decision` + the three-row comparison
  test + Finder timings), item 2 (the best waiver move searched on the basis), item 5 (one minus sign in every decision
  sentence; the tile's caption naming both totals). Item 1 changes every saved `/api/trades/partners` answer, so it needs
  its own re-save and a full e2e run: it did not fit with a full run before 20:00. Next wave: item 1 first (cards are
  lazy per IL-4: price the decision only for the rows the Finder shows, reuse the card's covered pair), then 5, then 2.

## 2. Commits

`60501da` IS-3: the three fixme'd trade e2e tests on legal trades of today's fixtures, re-saved from the API.
The next commit: this hand-back and the CHANGELOG bullet.

## 3. Evidence

| Test | Old saved trade (not legal today) | New trade (legal on `league_lab`) | Meaning kept |
|---|---|---|---|
| ia2:65 / ib2:143 (Scrubs) | 12490 (Tuten) to team 9 for 11624 + 7021 | 8150 (Kyren Williams) to team 1 for 4034 (McCaffrey); tick 12481 (Skattebo) | the tick changes the dial's label: "Improves it a lot" → "Makes their lineup weaker" |
| ii1:126 | 6650 (McLaughlin) for 3294 (Prescott), team 10 | 650 (Folk) for 3294 (Prescott), team 10 | a kicker for a starter is "Implausible", its reason names the starter |

Face validity: Williams (RB, 19.3 this week) for McCaffrey (RB) is an even RB swap that helps team 1 ("Improves it a
lot"); asking for Skattebo too turns it into a loss for them ("Makes their lineup weaker") — the direction a manager
would expect. Folk (K) for Prescott (their starting QB) is implausible: every other partner's starting QB gives the same
label (Hurts, Lamar Jackson, Burrow, Goff, Love, Allen), Stafford alone is "plausible" (Run Bijan Run lose a QB they
have a backup for, Maye).

Evaluate timings (fixtures, warm context): same package 0.057 s; new package 0.67 s; cold 0.68–0.83 s (profile above).
Finder timings: not measured (item 1 not done).

## 4. Tests

* e2e ia2 + ib2 + ii1 (replay, both projects): 36 passed, 0 failed, 0 fixme.
* Full e2e (`FIXTURES_PORT=8938`, both projects, on `60501da`): **595 passed, 0 failed, 17 skipped** (12.6 min; the 17
  are the specs' own skips, as on the fix-round run: 589 + 6 failed + 17 there).
* `scripts/gate.sh python`: GATE PASSED (ruff clean).
* No Python, `src/` or `web/src` change on this branch (fixtures, specs and the save script only): the API suites,
  `check_root.sh` and `npm run lint` / build are not affected; the build was re-run before the e2e (ok).

## 5. Edits outside my files

`CHANGELOG.md` (one bullet under `## 2026-10-08 — Wave I-S (dependability, second round)`).

## 6. PO lines

None.

## 7. Found, not mine

* Several older saved Scrubs answers (`trades_evaluate_*1389709692405551104_2_9_12490_*`) are still not legal on
  today's fixtures and carry no `decision`; no spec asserts on them now (the saved Scrubs Finder answer was built from
  that package and may still link to it: the Finder fixtures are item 1's re-save).

## 8. Next

Item 1 (Finder rows = the calculator's answer, with the three-row test and timings), item 5, item 2.
