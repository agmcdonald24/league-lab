# IZ-2 — a trade answers five questions in order (Wave I-Z)

Start 18:52 ET, end 19:20 ET (2026-10-11). Branch `dev/IZ2` from `integ/IZ` (`2182488`), worktree `/home/claude/wt-iq4`,
database `league_lab_iq4`. Ports 8921 (this branch's API at the PO's Saturday clock, 2026-10-10T16:00Z, to record),
8927 (e2e).

## 1. Done / not done / cut

* **Done — 1. Five sections in the review's order** (`web/src/routes/decisions/TradeFive.svelte`,
  `web/src/lib/tradefive.ts`), each one sentence first, the detail under it or on demand:
  1. *What changes in your starters*: the decision's sentence; the **lineup panel** (Slot · Before · After · Pts):
     only the slots that change, the displaced player named with why he leaves (traded, to the bench, the free agent no
     longer needed), who takes the slot and how (from the trade, from the bench, a free agent for the week), the week's
     total; the week strip (both teams, the window) under it; the sentences slot by slot on demand.
  2. *What they get*: their sentence, their panel, their weeks, **Why they might say no** (the first reason, in
     words); yes / no reasons on demand ("not a guess at his answer").
  3. *What it costs beyond the players named*: the cut (or "Nobody is cut …"), backup coverage; their depth, bye cover
     (the assumed pickups), roster-slot notes and roster size on demand.
  4. *Could you get there another way*: the decision's alternative sentence, then **Keep your roster · Best claim ·
     This trade** — three totals over the window in one row, the best outlined, the claim named and its assumption
     ("a waiver claim (rolling waivers): it can be lost to a team ahead of you"), their own best claim in one line.
  5. *What could change the answer*: the first caveat or flag as the lead; one line per player in the trade (given,
     received, cut: report status, why he sits, why he cannot play); the starter caveats; on demand the trust line's
     per-position checks and what is missing (no season value, out indefinitely, role after his latest game).
* **Done — 2. Three things kept apart, by name** (under the verdict): **Lineup points** (best lineup each week, you and
  them) · **Market price** (season value above replacement, in season points — "From League Lab's rest-of-season
  projections, data published 11 Oct, 6:38 pm ET") · **Plausibility** (the label and its first reason). No sentence
  calls a low lineup value "free" (asserted).
* **Done — 3. The phone**: the sections stack; the panel fits 375 (asserted: no sideways scroll, the panel's right
  edge inside the screen).
* **Done — 4. The free calculator**: "A trade's five questions, without a league" — 1–4 say what a league would add,
  5 says who is out or without a projection; the values named as season value.
* **Done — 5.** Tests, WORDS, CHANGELOG. The calculator no longer repeats II-1's trade card (its parts are in the
  sections; the Trade Finder keeps it).
* **IZ-4's place**: section 5, one line per player — `TradeFive.svelte`, the `newsFor(key)` hook (returns null) and
  the `data-testid="trade-news"` line under each `five-player`, marked `---- IZ-2 → IZ-4`.
* **Not done**: a *role* caveat per player — the calculator's answer carries no role data; section 5 says a role
  change after his latest game is not in the numbers. Nothing re-priced, no API change.

## 2. Commits

`59d3582` 1 + 2 · `4772e44` 3 + 4, e2e iz2 · `e67817c` the how-to and the three specs · `e330984` tests, WORDS, CHANGELOG ·
`9a3d027` the screens · the hand-back.

## 3. Evidence

**The Folk trade's numbers, before and after** (the calculator's `evaluate` at the Saturday clock, dumped to JSON before
any change and again after): identical — you +1.01 this week, +1.79 over weeks 5–8 ([1.01, 0.1, 0.48, 0.2]); Run
Bijan Run −0.10 / −1.56; not worth proposing; implausible. `test_ix5::test_the_known_trade_stays_fixed` PASSED before
and after. No file under `api/league_lab_api`, `src`, `app` changed (`git diff 2182488..HEAD`: empty).

**The first screen of the Folk trade, top to bottom (1300):** "Trade calculator — You give Nick Folk; you get Matthew
Stafford and Will Reichard." · the window (Next 4) and its caption · the dial "Makes their lineup weaker" and four
tiles (you +1.0 / +1.8; Run Bijan Run −0.1 / −1.6) · "Helps your lineup +1.0 this week (+1.8 over weeks 5–8), costs
their lineup 0.1 (1.6 over weeks 5–8); …" · **Lineup points** … **Market price** you give 0, you get 8, data published
… **Plausibility** Implausible: a K for a starter … · "Not worth proposing: …" · the trust line · You give / You get ·
**1** "Your starting lineup: about 1.0 more points this week, about 1.8 more …" with the panel QB Jacoby Brissett →
Matthew Stafford +0.1, K Nick Folk → Ka'imi Fairbairn +0.9 · **2** their sentence, QB Stafford → Brissett −0.1, "Why
they might say no: Their starters lose 0.1 this week." · **3** "You must cut Bryce Young to make room (he does not start
for you: no lineup points lost)." · **4** Keep 482.1 · **Best claim 488.8 (+6.7)** · This trade 483.9 (+1.8), the claim
"add Washington Commanders defense, drop Bryce Young" and its assumption · **5** the players' lines and the checks.

Words before → after (WORDS § IZ-2 has all): the result's paragraphs "You give / You get / Cut", "Against your best
waiver move", "Starter points, week by week", "Worth proposing? …" (II-1's card), "Your starters this week, slot by
slot", "Backup coverage", their sentence → the five headed sections above; the how-to's "Your starters this week, slot
by slot" bullet → "The answer, in five questions …" and "Three things, never mixed …".

Screens (JPEG, 375 and 1300): `docs/handbacks/iz2/` — the Folk trade, a trade worth proposing (Folk for MarShawn Lloyd,
GoodGameBuddy: the trade 491.0 beats the claim 488.8 and keeping 482.1), the free calculator.

## 4. Tests

* New `api/tests/test_iz2.py`: 5 passed (keep / claim / trade is the answer's own comparison — trade − claim =
  `beyond`; the panel's rows name both players and its total is the tiles'; the reasons are never a chance; the market
  price's date).
* `test_ix5`, `test_ir2`, `test_ii1`, `test_iz2`: 219 passed, 3 failed — `test_ir2::test_folk_sentences_pair_the_same_slot`,
  `test_ir2::test_folk_depth_sentences_agree`, `test_ii1::test_folk_package_is_not_promoted`: the database's Folk
  package at the pinned clock (no K slot change, a different cut); no API code changed, so they fail on the base too.
* e2e `iz2`: 8 passed (phone + desktop). Every spec that opens the calculator (20 files, both projects): 211 passed,
  5 skipped, 0 failed. Updated on purpose: ie2 (the order), ir2 (the effects from Lineup points; one recommendation),
  ii1 (plausibility and the reasons in the sections).
* ruff clean; copy standard clean; `npm run lint` and `npm run build` clean. No `src/` edit (no root check needed).
* Saved answers: none changed (the screen reads fields every saved answer already holds); new `web/fixtures/iz2/`
  (recorded from this branch's API).
* `scripts/gate.sh` (19:18 ET, after the last code commit): src 783 ran, api 40 ran, ruff, lint, build — 71 s, exit 0.

## 5. Edits outside my files

`web/src/components/scoring/FreeTrade.svelte` (one card), `web/e2e/ie2`, `ir2`, `ii1` (on purpose), WORDS, CHANGELOG.

## 6. PO lines

None needed. Optional `app/whats_new.md`: "A trade now reads top to bottom: what changes in your starters, what they
get and why they might say no, what it costs beyond the players named, whether a claim or standing pat does as well,
and what could change the answer."

## 7. Found, not mine

* II-1's refuse reason reads oddly when a player's game has started: "They lose MarShawn Lloyd, an RB who cannot play in
  week 5 (game started (bench)): … (Josh Jacobs game started (bench) and MarShawn Lloyd game started (bench)) cannot)."
* The three `test_ir2` / `test_ii1` Folk tests above pin the package as it stood on an older copy.
* Running all fixture specs rewrites other packages' screenshots under `docs/handbacks/` (in1, in4, in5, io1–io3, ip3,
  iu6 write there by default); I restored them with `git checkout`.

## 8. Next

IZ-4: fill `newsFor` in section 5. A role caveat needs role data in the trade answer (a small API addition).
