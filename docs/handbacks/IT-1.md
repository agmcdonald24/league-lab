# IT-1 — one basis on every trade screen (Wave I-T, 2026-10-09; continues IR-2 / IS-3)

Branch `dev/IT1` from `main` `7341acc`, worktree `/home/claude/wt-ir2`, database `league_lab` read only (pinned clock
2026-10-03T16:00Z). Nothing written to any database.

## 1. Done / not done / cut

All six items are done; nothing was cut.

1. **The Trade Finder's rows are the calculator's answer.** Each row is built by `decisions.it1_row_decision`: `ir2_decision`
   runs on the row's own card (the covered pair that card priced), then `provenance.with_trade` / `rule_trade` are
   applied exactly as `main.trades_evaluate` applies them, so a withheld verdict is not "worth proposing" in the Finder either.
   - The row's label, gains, strip, story, alternative line, tier and order are copied from that decision
     (`it1_apply_row`, `it1_rank`). A compact copy rides on the row as `decision`.
   - The decision is kept on the frame beside the card, so a warm Finder prices nothing again.
   - Packages are still proposed by `trades.partners` (roster-only gains). A package whose decision does not raise both
     lineups is no longer listed; `search.dropped_on_the_basis` counts them.
   - The Finder's "Your best move" is the basis move (`it1_finder_alternative`).
   - Explore now says when trades past the first three are also worth proposing (the Finder promotes three at most).
2. **Every saved Finder answer re-saved from the API** (`web/fixtures/save_ir2_fixtures.py --finder`):
   - all 24 `trades_partners_*.json`, plus every recording key holding a Finder answer (ie1, if2, ig1, ii0, ii1, mfl ie0);
   - the calculator answers those Finder answers lead to (first row, first "best" row, first credible row; four windows);
   - every `trades_evaluate_*` answer and every recorded evaluate key;
   - the tick package's labels in `ia2_packages.json`.
   The old Scrubs package `…_2_9_12490_…` (5 files) and the stale ii1 key `6650→3294` are removed. e2e/ir2, ii1
   (Dynasty case) and ie0 (Try it) were re-recorded from the fixture API. Specs read the saved answers, never a hard-coded number.
3. **One minus sign.** One helper, `it1_minus`, converts every sentence of the decision, the card and the Finder's
   headline ("−0.3", U+2212). It does not touch ids, dates or names.
   **The tile caption:** a line under the four tiles names the roster-only total that other screens show:
   "Totals with the assumed pickups for empty slots; your roster alone, as My Team shows it: 97.54 → 118.18 this week."
4. **The best waiver move on the basis** (`trades.basis_best_move`, hooked into `ii1_alternative` for both teams).
   - The roster pool for each week has its empty slots filled from the free pool, and an add is worth what it raises
     that lineup (exact entry bar).
   - Moves tried: an open spot; otherwise a drop of the cheapest bench player. A starter is dropped only when the bench is empty.
   - Players used as fills are not candidates.
   - The basis move replaces the roster-only pick when it adds more on the basis. The old pick is kept as `roster_only_pick`.
5. **The reason beside a player who sits** shows on the calculator's two roster lists and on the Finder's row players.
   It is the `availability` note from `league_gate.note` (`/api/team` rows since IS-2; Finder row players via
   `it1_row_notes`, one request-time read). No status code is tested here.
6. **Every Trades / calculator e2e is green on both projects, then a full run** (see 4).

## 2. Commits

| Commit | What |
|---|---|
| `694f93e` | Finder rows = the calculator's decision; comparison test |
| `04eb749` | One minus sign, the tile caption, the basis waiver search, only trades raising both lineups, status notes, the re-save step |
| `a1de55d` | Status-note test; the label refresh |
| `a0e20e4` | Every Finder / calculator answer re-saved; the Finder's best move; specs on the saved answers |
| `102bd2c` | Explore's sentence; comparison on three leagues; WORDS, METRICS (ct1.2), registry row, CHANGELOG |

## 3. Evidence

**The three-row comparison**, `api/tests/test_it1.py::test_three_finder_rows_are_the_calculators_answer`. For each row,
`/api/trades/partners` is compared field by field with `POST /api/trades/evaluate`, the route with caveats and the starter rule.
- Fields compared: the dial (all fields), both sides' gains and by-week, the strip, the verdict, the alternative words /
  beats / beyond, the recommendation key / credible / label, the card's credible flag, and the caveat.
- The recommendation words are also compared word for word when the partner's own move was compared. When it was not
  (IL-4), the card says so.

| League | Partner | Give → get | Label | You (window) | Recommendation |
|---|---|---|---|---|---|
| Scrubs (2) | 8 | 13346 → 4866 | Improves their lineup | +4.71 | Not worth proposing |
| Scrubs (2) | 5 | 6794 → 12474 | Improves their lineup | +4.66 | Not worth proposing |
| Scrubs (2) | 4 | 10232 → 7594 | Improves their lineup | +3.91 | Not worth proposing |
| Test League (3) | 7 | 11584 → 12490 + 2133 | Improves it a lot | +9.36 | Not worth proposing |
| Test League (3) | 1 | 13279 → 10859 | Improves their lineup | +7.31 | Not worth proposing |
| Dynasty (12) | 10 | 11563 → 11584 + 13287 | Improves it a lot | +24.18 | Worth proposing |
| Dynasty (12) | 5 | 11563 → 8155 + 12512 | Improves it a lot | +20.87 | Worth proposing |

The third row of the Test League and Dynasty is compared too (the test asserts all three rows); the printout above
shows the ones it printed.

**Finder timings** (fixtures, `/api/trades/partners`, seconds; before = `7341acc`'s `decisions.py`). All within 1.5×.

| League | Cold before | Cold after | Warm before | Warm after |
|---|---|---|---|---|
| Scrubs 2 | 2.66–2.78 | 2.96–3.03 (1.1×) | 0.051–0.066 | 0.043–0.050 |
| Test League 3 | 3.76–4.06 | 4.22–4.26 (1.08×) | 0.055–0.064 | 0.059–0.064 |
| Dynasty 12 | 3.82 | 4.16 (1.09×) | 0.059 | 0.066–0.073 (1.1–1.2×) |

**Evaluate timings** (Folk case): cold 0.70 s (context + package); a new partner on a warm context 0.20 s; the same partner 0.06 s.

**The case where the best waiver move changes** (Folk for Stafford + Reichard, Scrubs, next 4):

| | Before (roster-only pick, re-priced) | After (searched on the basis) |
|---|---|---|
| Your best waiver move | add Jacoby Brissett, drop Bryce Young: +20.9 roster-only, **+0.0** on the basis (Brissett only covers the Mahomes bye the free fill already covers) | add Washington Commanders defense, drop Jacory Croskey-Merritt: **+6.7** on the basis |
| Alternative line | "+0.5 over weeks 5–8, 0.5 more than your best waiver move" (beats) | "+0.5 over weeks 5–8, not more than your best waiver move (… +6.7 …): the trade does not beat it on starter points." |
| Recommendation | Not worth proposing (their side short) | Not worth proposing: "your starters end 6.2 behind your best waiver move … Run Bijan Run's starters end 4.8 behind their own best move" |
| Their move | Dicker for Stevenson, +2.0 | add Washington Commanders defense, drop Josh Downs: +3.5 |

**What the Finder now says.** Credible counts before → after IT-1:
- Scrubs 2: 0 → 0. Through item 1 alone it rose to 3, because every trade "beat" the roster-only pick, which is worth
  0 on the basis. Item 4 removed that artefact.
- Test League 3: 3 → 0.
- Dynasty 12: 3 → 3.

On the basis, a better defense or a better flex player off the wire beats every Scrubs and Test League package.

**Face validity: the top of the lists** (players: position, projection this week, season points, status):

| # | Tier | Partner | You give | You get | You / them over weeks 5–8 | Label | Recommendation |
|---|---|---|---|---|---|---|---|
| D1 | credible | Taco Corp. | Bo Nix (QB 23.3, 272) | Jahmyr Gibbs (RB 23.1, 256) | +25.6 / +13.8 | Improves it a lot | Worth proposing |
| D2 | credible | Ward of the Rings | Bo Nix | Bucky Irving (RB 13.1) + Jeremiyah Love (RB 14.5) | +24.2 / +19.7 | Improves it a lot | Worth proposing |
| D3 | credible | The72Repeat | Bo Nix | Breece Hall (RB 13.1) + Quinshon Judkins (RB 13.0) | +20.9 / +20.4 | Improves it a lot | Worth proposing |
| D4 | explore | Taco Corp. | Michael Penix Jr. (QB 18.7) | J.K. Dobbins + D'Andre Swift | +16.8 / +15.1 | Improves it a lot | Worth proposing (past the first three: Explore says so) |
| S1 | explore | MikeDaddy | Denzel Boston (WR 9.9) | Saquon Barkley (RB 9.0) | +4.7 / +3.6 | Improves their lineup | Not worth proposing |
| S3 | explore | Scrote Squad | Michael Wilson (WR 14.1) | Chuba Hubbard (RB, bye this week) | +3.9 / +4.1 | Improves their lineup | Not worth proposing |

- Every player listed plays this week, except Hubbard on his bye. His card says "cannot play this week (bye): the gain
  comes after it", and the bye is in the strip.
- Dynasty roster 12's credible trades all give Bo Nix for running backs. Each raises both lineups on the basis by
  more than a point beyond each side's own best waiver move. Scrubs' best ideas are small WR-for-RB swaps that a +6.7
  claim beats.

**Fixtures size:** 33,847,755 → 37,869,338 bytes (+4.0 MB). The saved Finder answers predated the II-1 cards (about
30 KB each); today's answers carry a card per row plus the row decision (about 200 KB for Dynasty).
I did not trim them: the screens read the cards.

## 4. Tests

- **Mine:**
  - `api/tests/test_it1.py`: 7 passed. The comparison on three leagues; order and tiers on the decision; the Finder row's status note.
  - `tests/test_it1_trades.py`: 3 passed. The basis pick beats the bye-cover pick; a full roster drops its cheapest bench player; no move.
- **Edited modules' API tests** (test_it1, ir2, ii1, il4, if2, ia2, ie1, ie2, ie0, ii0, ib0, ig1, ir0, decisions, in5,
  ih2): 155 passed, 45 failed, 3 skipped. **All 45 are in `known_api_failures.txt`; 0 new.**
- **Root:**
  - `check_root.sh`: 1695 passed, 4 failed (known), 0 new.
  - test_it1_trades, test_ir2_trades, test_metric_registry: 10 passed.
- **Other checks:** `scripts/gate.sh python` GATE PASSED; ruff clean; copy standard clean; `npm run lint` clean; build ok.
- **e2e:**
  - Every spec that opens Trades or the calculator, on both projects: decisions, ia2, ib2, ie0, ie1, ie2, if2, ig1,
    ii0, ii1, ii6, in1, in2, inf1, ip3, iq4, ir1, ir2, ir4, il1, il2, il5, h1, ib1. All green after the rewrites.
  - **Full run** (`FIXTURES_PORT=8919`, both projects, after the last screen change): **597 passed, 0 failed, 17 skipped**
    (the specs' own skips).
  - An earlier full run had 596 passed and 1 failed (`im4:107`, the passkey account test, phone). It passed on rerun
    (4 of 4) and is not a trade screen.

**Tests changed on purpose:**
- `api/tests/test_ir2.py`: the sign helper uses the true minus.
- `api/tests/test_il4.py`:
  - `recommendation` joins the fields that may differ when the partner's move was not compared; its key and label must agree.
  - The lazy-and-eager test takes the first league / team with a compelling answer (Dynasty 12 when the Test League has none).
- **e2e:**
  - ia2 window test: the none-headline line.
  - ib2 / ie0 / ii0 / decisions: open Explore when nothing is credible; the row count is credible plus up to 12.
  - ie0 Try it: the package comes from the saved answer.
  - ie1: the cheaper package comes from the saved answer (now Millertime).
  - if2: the headline / Explore branch from the saved answer.
  - ig1: the answer's own first line.
  - ii0: a card whose incoming player cannot play says that first.
  - ii1: "credible trades lead" now runs on Dynasty 12; the Test League has none.
  - ii6: the best move, count and weeks come from the saved answer.
  - ir2: the true minus and the tile caption.

## 5. Edits outside my files

- `CHANGELOG.md`, `docs/WORDS.md`, `docs/METRICS.md`: marked IT-1 blocks.
- `dbt/seeds/metric_registry.csv`: the `credible_trade` row is now ct1.2; the registry coverage test needs it.
- `web/src/lib/api.ts`: my IR-2 block (`UnfilledSide`).
- `api/tests/test_il4.py`: a test of the module I edit.

## 6. PO lines

- **The nightly:** nothing it reads changed meaning.
  - `project`, the solves and the dbt models / tests do not read `trades.py` or the decision code.
  - `reports.py` reads `trades.partners` / `market_by_player` / `price_by_player` / `season_value`, all unchanged.
    `fill_empty` returns the same numbers (it now calls `fill_lineup`).
  - The one thing `dbt seed` loads is the registry row (a notes / version change). Run the chain at merge only for that.
- **Item 3's tile caption:** say if you prefer the roster-only total in the tile itself.

## 7. Found, not mine

- `partnerReason` (`web/src/lib/decisions.ts`, IB-2) still picks its sentence from the player field `cannot_play` (the
  board's reason). It is not a status-code test, but it is a second read beside `league_gate.note`. Worth folding into
  the note next wave.
- The environment notice named `/home/claude/wt-ip3` (that is IT-4's `dev/IT4`). I worked only in `/home/claude/wt-ir2`
  as the brief says, and did not touch `wt-ip3`.

## 8. Next

- **The Finder's search on the basis** (`trades.partners` still proposes on roster-only gains; the basis decides).
- **The pickups' roster cost** (a drop on a full roster) priced, not only said.
- **`partnerReason` on the note.**
