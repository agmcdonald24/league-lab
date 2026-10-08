# IR-2 — one trade verdict (Wave I-R, 2026-10-08; the dependability review's P0 1 and 2)

Branch `dev/IR2` from `main` `3dfa01d`. Database `league_lab` read only (the fixtures', clock pinned at
2026-10-03T16:00Z); nothing written anywhere.

## What was built

1. **One primary basis, one response object.** `POST /api/trades/evaluate` now carries `decision`
   (`api/league_lab_api/decisions.py::ir2_decision`). Basis: **against realistic replacements** — the II-1 covered frame
   (every empty starting slot filled with the best free agent who can play it that week) for both teams, compared with
   each team's best waiver move re-priced on the same frame. Why this one: it is the PO's choice and the review's; it
   already existed and was tested (II-1's card), so making it primary was a re-wiring, not a new model; and the
   roster-only basis is the one that manufactured the review's swings (an empty QB / K slot counted 0: "Improves it a
   lot" for a team whose starters lose). The dial, the four tiles, the week table, the strip and story, the verdict and
   headline, the alternative line, the recommendation, the slot changes, the depth and this week's lineup tables all
   read it. The legacy top-level fields (`fit`, `before`, `after`, `interest`, `verdict`, `headline`, `strip`, `story`,
   `effect_words`, `alternative`, `alternative_words`, `beats_alternative`, `beyond_alternative`, `starters_in` /
   `starters_out`, `lineup_words`, `backup_words`, `their_change`, `hold_words`, `values.starter_points`,
   `lineups.*.slots/out/total`, `card.credible`) are **copied** from it (`ir2_apply`), never computed beside it; `_hold`'s
   own roster-only comparison is no longer computed. The roster-only result is `decision.unfilled` ("If empty slots were
   left empty"), an expander on the screen labelled an explanation, not the verdict.
2. **The waiver claim is uncertain access.** `decision.fills` names the assumed pickups per side, week and state (before
   / after the trade) with their projections, and says they are assumed, not sure (another team can add him first; on
   waivers a claim can be lost; on a full roster the pickup takes a bench spot, not counted). The alternative names its
   add / drop plan and its availability ("a waiver claim (rolling waivers): it can be lost to a team ahead of you").
   **One free agent is never counted for both teams** (`trades.covered_pair`): in each state of the league the roster
   earlier in the league's order fills first and the other excludes those players, week by week — so the answer does not
   depend on whose side asks. The Finder's cards use the same pair (`il4_sides`).
3. **Explanations from the slots.** `trades.slot_changes` re-seats the after lineup to keep every player where he was
   (`lineup._reseat`) and lists each changed slot with its two players, chained (a player entering the lineup, then the
   player he displaces, slot by slot: the FLEX cascade). `ir2_changes` words them; `ir2_need` is the dial's line;
   `need_words` (kept) reads the same changes. The review's "It takes over their K from Matthew Stafford" is now "It puts
   Maye at their QB in place of Stafford and puts Folk at their K in place of Reichard."
4. **One depth definition** (`ir2_depth`, read by the backup line and — through `_depth_words` — the card, Finder
   included): for each player a side loses who does not start this week, the bench left at his position after the trade
   who can play that week, and named separately those who cannot (a bye, injured reserve, the IR slot, the taxi squad).
   The review's "1 RB left" vs "3 RB left" was the IR-slot RBs counted in one sentence and not the other.
5. **IR-1 hook** (`ir2_out_indefinitely`, marked): IR-1's definition was not on `main`; until it is wired, the board's
   own this-week reason ("NFL injured reserve" / the IR slot) puts a sentence in the verdict and the recommendation
   ("Zach Charbonnet is in the IR slot, so these numbers count no games from him."). **PO line**: replace the body of
   `ir2_out_indefinitely` with IR-1's `out_indefinitely` once merged.
6. **IR-4 contract**: `decision` has no `caveats` key yet; IR-4's `provenance.for_trade(...)` list can be set as
   `out["decision"]["caveats"]` right after `ir2_apply` in `evaluate` (one line) — the screen does not print it yet.

## Files

`api/league_lab_api/decisions.py` (IR-2 block after IE-2; `evaluate` wiring; `need_words`, `_depth_words`, `il4_sides`,
the card's alternative words, `trade_story`'s `_hold` call removed), `src/league_lab/trades.py` (`fill_lineup`,
`covered_side`'s exclusion and first-week lineups, `covered_pair`, `slot_changes`), `web/src/routes/decisions/TradeCalc.svelte`,
`web/src/lib/api.ts` (IR-2 block at the end), `web/e2e/ir2/fixtures.spec.ts`, `web/fixtures/ir2/api_ir2.json`,
`api/tests/test_ir2.py`, `tests/test_ir2_trades.py`, tests changed on purpose (below), `docs/METRICS.md` (§ "One trade
verdict", ct1.1), `dbt/seeds/metric_registry.csv` (the `credible_trade` row: ct1.1), `docs/WORDS.md` (§ "One trade verdict"), `CHANGELOG.md`, this file, `docs/handbacks/ir2/*.jpg`.
Edits outside my files: `web/src/lib/api.ts` and `docs/WORDS.md`, `CHANGELOG.md` (marked blocks / one bullet).

## Response shape (`decision`, the one place the screen reads the verdict)

```
decision = {basis: "replacement", basis_label, basis_words, weeks, span, window, this_week (None in the playoffs window),
  mine / theirs: {before: {this_week, window, by_week[]}, after: {…}, gain_week, gain_window, by_week[], cuts[]},
  dial: {score, label, their_gain, you, caption, title, need}, verdict, headline, effect_words, their_effect_words,
  fit_words, strip: {weeks, mine, theirs}, story,
  alternative: {mine (the claim, gain_* on the basis), theirs, beyond: {mine, theirs}, beats, words, other_objective},
  recommendation: {credible, key: worth_proposing | not_worth_proposing, label, words, plausibility},
  changes: {mine: [{slot, slot_type, slot_word, in, out, in_from, out_to, in_how, out_why, in_player, out_player,
                    in_value, out_value, words}], theirs: […], words: {mine: [], theirs: []}},
  depth: {mine / theirs: {words, lost: [{player, position, usable[], cannot_play[{player_name, why}], words}], joins[]}},
  fills: {mine / theirs: {rows: [{week, state, player, value}], words}},
  unfilled: {label, words, mine / theirs: {gain_week, gain_window, by_week, before, after}},
  out_indefinitely: {players, words} | None}
```

## Evidence — the Folk case on the fixtures (League of Scrubs, MacZaddy 2 ↔ Run Bijan Run 3, give 650, get 421 + 11792, Next 4)

Old = `main` 3dfa01d on the same database and clock; new = this branch. The fixtures' numbers differ from the live
page the review saw (−3.1 / +2.1 vs +6.1 / −7.1); the shape of the failure is the same.

| | Old page | New page |
|---|---|---|
| Dial | Improves it a lot (their +7.53), You +12.61 | Makes their lineup weaker (their −1.28), You +0.52 |
| Dial line | takes over their K from Matthew Stafford | puts Maye at their QB in place of Stafford and puts Folk at their K in place of Reichard |
| Tile You · this week | +20.6 (97.54 → 118.18) | −0.3 (127.12 → 126.86) |
| Tile You · weeks 5–8 | +12.6 (448.75 → 461.36) | +0.5 (486.53 → 487.05) |
| Tile RBR · this week | −0.5 | −0.5 |
| Tile RBR · weeks 5–8 | +7.5 (480.92 → 488.45) | −1.3 (498.84 → 497.56) |
| Week strip you / them | +20.64 −8.71 +0.48 +0.20 / −0.50 +8.71 −0.48 −0.20 | −0.26 +0.10 +0.48 +0.20 / −0.50 −0.10 −0.48 −0.20 |
| Week table you before → after | 97.54 123.06 105.63 122.52 → 118.18 114.35 106.11 122.72 | 127.12 123.06 113.83 122.52 → 126.86 123.16 114.31 122.72 |
| Week table them | 123.5 115.48 125.4 116.54 → 123.0 124.19 124.92 116.34 | 123.5 124.29 125.4 125.65 → 123.0 124.19 124.92 125.45 |
| Verdict | Helps your lineup +20.6 this week (+12.6 over weeks 5–8), them +7.5 …: helps both lineups. | Helps your lineup +0.5 over weeks 5–8 (−0.3 this week), costs their lineup 0.5 (1.3 over weeks 5–8); about even by season value: a lineup loss for them. |
| Effect | about 20.6 more points this week, about 13 more in total | about 0.3 fewer points this week, about 0.5 more points in total |
| Against your best waiver move | +12.6; the Brissett claim gives +20.9 (drop Young): does not beat it (beyond −8.29) | +0.5, 0.5 more than your best waiver move (add Brissett, drop Young: +0.0 on the same basis; a waiver claim …) |
| "Worth proposing?" card you / them | +0.52 / −1.28 (beside a dial saying +7.53) | +0.52 / −1.28 (= the tiles) |
| Card beyond you / them | 0.52 / −3.29 | 0.52 / −3.29 |
| Recommendation | card `credible` false, no sentence | Not worth proposing: your starters gain +0.5 beyond your best waiver move over weeks 5–8 (the bar is 1 point); Run Bijan Run's starters gain −3.3 beyond their own best move over weeks 5–8. |
| Your starters | Stafford starts at QB and Reichard starts at K; Folk goes to Run Bijan Run. | Matthew Stafford (from the trade) starts at QB in place of Jacoby Brissett (the free agent who would have covered it). Will Reichard (from the trade) starts at K in place of Nick Folk (traded). |
| Lineup total this week | 97.54 → 118.18 (+20.64) | 127.12 → 126.86 (−0.26) = the tile |
| Their starters | Maye starts at QB and Folk starts at K; Stafford goes to you and Reichard goes to you. | Drake Maye (from the bench) starts at QB in place of Matthew Stafford (traded). Nick Folk (from the trade) starts at K in place of Will Reichard (traded). |
| Backup line | you lose Croskey-Merritt, a backup RB (1 RB left on your bench) | you lose Jacory Croskey-Merritt, a backup RB: 1 RB left on your bench who can play in week 5 (Zach Charbonnet in the IR slot and Jonah Coleman in the IR slot cannot) |
| Card depth line | … a backup RB (3 RB left on the bench) | the same sentence as the backup line |
| Alternatives line | Standing pat … 97.5 … Brissett adds about 21 points …: more than this trade | (the alternative line above; the roster-only comparison is gone) |
| Roster-only explanation | — | If empty slots were left empty: your starters +20.6 this week, +12.6 over weeks 5–8; Run Bijan Run's −0.5 and +7.5 … an explanation, not the verdict. |

Assumed pickups (new): yours without the trade Brissett (QB, wk 5), Hockenson (TE, wk 5), Panthers (DEF, wk 7); with it
Hockenson (TE, wk 5), Dicker (K, wk 6), Panthers (DEF, wk 7). Theirs without: Dicker (K, wk 6), Hockenson (TE, wk 8); with:
Hockenson (TE, wk 8) — no player counted for both teams in one week and state.

Every window on the same package (one basis each): week −0.26 / their −0.50; next4 +0.52 / −1.28; ros (weeks 5–16) −1.25
/ −1.33; playoffs (weeks 15–16) −0.15 / −1.34 — all "Makes their lineup weaker", all "Not worth proposing". Reversed
(team 3 giving Stafford + Reichard for Folk): each team's numbers identical (`test_folk_reversed_preserves_each_teams_effect`).
Face validity: Stafford (QB 20.88 this week) replacing the free QB Brissett (20.90) is a wash for MacZaddy in week 5 —
Mahomes's bye week, which the roster-only basis priced as a 20-point gain; Folk for Reichard is a near-equal kicker swap
(8.51 / 8.27; Reichard's week-6 bye is covered by a free kicker either way). A wash for one, a small loss for the
other, is the right answer for a kicker-for-QB-plus-kicker swap in a 1-QB league.

## Tests (regression scenarios: meaning and consistency, no hard-coded projections)

`api/tests/test_ir2.py` — 13 passed:
* `test_folk_every_primary_number_on_one_basis` — every primary number reconciles (`assert_reconciles`: by-week =
  after − before, window = Σ, this week = first week, strip = by-week, dial = their window gain and its label, you = your
  window gain, verdict carries the window number, headline ends with the verdict, story total, card effects = decision,
  card beyond = decision, recommendation = card ∧ alternative line); legacy fields are copies; the lineup table total =
  the tiles; the card and the dial agree in sign; the roster-only result labelled.
* `test_folk_sentences_pair_the_same_slot` — Folk ↔ Reichard at K, Stafford out at QB with the bench QB in; the dial line
  says both; never "K from"; every pairing legal for its slot.
* `test_folk_depth_sentences_agree` — the backup line and the card's line are the same sentence; usable count = the
  bench's; IR-slot RBs named, not counted.
* `test_folk_reversed_preserves_each_teams_effect` — reversal.
* `test_flex_cascade_is_a_chain_of_slots` — RB1 for a WR: WR takes FLEX in place of RB3; RB3 moves FLEX → RB in place of
  RB1 (traded); in that order.
* `test_mixed_position_package_pairs_each_slot` — RB + K for WR + K: kickers paired both sides; skill players at RB/FLEX.
* `test_reversal_preserves_each_teams_effect` — hand-built reversal (numbers and sentences).
* `test_surplus_qb_in_a_one_qb_league_adds_nothing` — a backup QB behind a better starter: 0, "Does not help".
* `test_one_free_agent_is_never_counted_for_both_teams` — both kickers on a bye: fills disjoint per state; same answer
  from either side; the pickups named and said to be assumed.
* `test_depth_has_one_definition_and_names_who_cannot_play` — bench left who can play, the IR-slot player named, the
  incoming bench player joins; the card's sentence identical.
* `test_mfl_team_units_are_slots_like_any_other` — team QB for team QB + WR: "team QB" slot, units paired.
* `test_need_words_pair_by_slot`, `test_a_player_on_a_reserve_list_is_said_in_the_verdict` (the IR-1 hook).

`tests/test_ir2_trades.py` — 4 passed (`fill_lineup` = `fill_empty`; `covered_pair` exclusivity and side-independence;
`slot_changes` FLEX chain and K pairing; a renumbering is not a change).

Edited modules' existing tests (decisions / trades): `test_decisions, test_ii1, test_il4, test_ia2, test_ie0, test_ie1,
test_ie2, test_if2, test_ii0, test_ig1, test_ib0, test_in5, test_ih2, test_ie_po, test_if1, test_ii4, test_ii5, test_il2,
test_ik1, test_ik2, test_ik3` + `test_ir2`: 263 passed, 54 failed, 6 skipped — **all 54 in
`known_api_failures.txt`, 0 new**. Re-run after the last change (the card's alternative words, the reserve-list hook) of
`test_ii1, test_il4, test_if2, test_ie2, test_ie1, test_ia2, test_ie0, test_ii0, test_ib0, test_ir2`: 84 passed, 26
failed (all known), 2 skipped — 0 new. Root: `tests/test_trades.py`, `tests/test_trades_ii1.py`, `tests/test_ir2_trades.py`
46 passed; `check_root.sh`: 1623 passed, 4 failed (all known), 3 skipped — 0 new (the metric registry's coverage test
needed the `credible_trade` row bumped to ct1.1: `dbt/seeds/metric_registry.csv`, notes name ct1.0 → ct1.1). ruff: clean. Copy standard: clean. Web lint (eslint + svelte-check + tsc): 0 errors, 0 warnings. Build:
ok. e2e `web/e2e/ir2` (recorded from the fixture API on :8962, replayed on :8927): 2 passed (375 and 1300; no sideways
scroll); screenshots `docs/handbacks/ir2/ir2-folk-{phone,desktop}.jpg`.

**Tests changed on purpose** (their expected words were the old basis / the old pairing):
* `api/tests/test_ia2.py::test_window_on_partners_and_evaluate_test_league` — the dial's caption says the basis
  ("…, against realistic replacements"); the rest of the dial unchanged.
* `api/tests/test_ib0.py::_totals` (test_one_lineup_total_on_every_screen) — the calculator's shared total is now the
  roster-only total (`decision.unfilled`); the test also asserts the basis total = that + the named pickups.
* `api/tests/test_ie1.py::test_the_dial_is_the_effect_on_their_starters` — the dial line pairs each changed slot of
  their lineup (it used to claim no need when the incoming player sat); Rice is named at the WR/TE he takes.
* `api/tests/test_ie2.py::test_the_full_package_names_both_assets_in_the_lineup_story` — "in place of Houston Texans QB
  (traded)" (slot by slot) instead of "Texans QB goes to Madeyes Revenge".

## Commands

```
cd api && OMP_NUM_THREADS=1 uv run pytest -q tests/test_ir2.py
OMP_NUM_THREADS=1 uv run pytest -q tests/test_ir2_trades.py tests/test_trades.py tests/test_trades_ii1.py
# the fixture API for the e2e recording (from api/):
LEAGUE_LAB_NOW=2026-10-03T16:00:00Z LEAGUE_LAB_SLEEPER_FIXTURES=$PWD/tests/fixtures/sleeper \
 LEAGUE_LAB_MFL_FIXTURES=$PWD/tests/fixtures/mfl LEAGUE_LAB_MFL_YEAR=2026 \
 LEAGUE_LAB_PLAYER_IDS_CSV=$PWD/tests/fixtures/ff/db_playerids.csv LEAGUE_LAB_GATE=open LEAGUE_LAB_AVAILABILITY=off \
 LEAGUE_LAB_USAGE=off LEAGUE_LAB_NEWS=off LEAGUE_LAB_RATE_LIMIT=off OMP_NUM_THREADS=1 PYTHONPATH=. \
 uv run uvicorn league_lab_api.main:app --port 8962
cd web && npm run build && IR2_RECORD=http://127.0.0.1:8962 FIXTURES_PORT=8927 SHOTS_DIR=../docs/handbacks/ir2 \
 npx playwright test --config playwright.fixtures.config.ts e2e/ir2      # replay: drop IR2_RECORD
```

## Not done / limitations

* **The Finder's partner rows** (`/api/trades/partners`) still carry their own `interest` / gains on the roster-only
  basis beside their card (II-1's tiers and verdict already read the card). Not the calculator; the same re-wiring
  (`ir2_decision` per row) is the next step — it costs a covered pair per row, which IL-4 made lazy.
* **The best waiver move** is IF-1's / IF-2's choice made on the roster-only numbers, then re-priced on the basis; the
  best claim on the basis itself may be a different player (here: Brissett is worth +0.0 on the basis because the free
  fill already counts him). Not re-searched.
* The pickup's roster cost (a drop on a full roster) and other teams' competition for the free agent are said, not
  priced; waiver state per player is not read.
* **League ranks** ("How we calculated this") still compare roster-only lineup values (the other rosters are valued
  that way); labelled as before, not on the basis.
* My Week / Waivers / Team show the roster-only total (95.48 in `test_ib0`'s case) and the calculator's tile the basis
  total (114.23 = that + the free-agent fills); the basis line under the tiles and the pickups sentence say why. PO's call
  whether the tile should show the roster-only total as its caption instead.
* Evaluate is ~0.6 s slower on the fixtures (1.2 s vs 0.6 s): the covered pair for the decision is shared with the card.

## Found, not mine

* `api/tests/test_ii1.py::test_folk_package_is_not_promoted` / `…_on_the_clone_rosters` fail on `main` already (known
  list): they rebuild the Folk package by swapping kickers on the clone's rosters, and the fixtures now hold Folk on
  roster 2 with week 5 as this week (`raw[1] >= 15` reads 0.1 here). Not investigated further; `test_ir2.py` reads the
  fixture's own rosters.
* The live review URL's numbers (−3.1 / +2.1, +6.1 / −7.1) cannot be reproduced here (no outside world); the fixtures
  show the same split.
