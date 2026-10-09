# IU-1 — the Finder's search on the basis (Wave I-U, 2026-10-09; continues IT-1)

## The rule, committed before the numbers

The Finder proposes on the replacement frame (`LEAGUE_LAB_FINDER_SEARCH=basis`, the new default) **only if**, on League of
Scrubs roster 2, the Test League roster 3 and Forever Unclean Dynasty roster 12 (next four weeks, the fixtures, the
pinned clock):

1. the list of trades worth proposing (the decision's recommendation `credible`) is never shorter than the roster-only
   search's, and every trade the roster-only search finds worth proposing is either still found or replaced, with the
   same partner, by one that gains you more on the basis;
2. the Finder's cold time stays within 1.5× of the roster-only search's (measured in the same run), and warm within 1.5×.

Otherwise the roster-only search stays the default (the switch keeps the basis search for the next wave) and this
hand-back says so with the numbers.

## 1. Done / not / cut

1. **The search itself — done; the rule holds, the basis search is the default.** `trades.partners(free=…)` proposes,
   bounds and prices every package on the replacement frame (`_Bars` on covered pools, `_Search.covered_gains`;
   `package_gains_covered` for the exclusive pricing); the API passes the frame's free agents (`decisions.partners`,
   `search.search_basis = "replacement"`; `LEAGUE_LAB_FINDER_SEARCH=roster` switches back). IF-2's roster-only ladder
   (`rank_partners` / `row_story`, computed and thrown away) is gone; IE-1's one-of-two is priced on the same frame.
2. **`partnerReason` — done.** It reads the row player's note (`availability` = `league_gate.note`: `sits`, `why`), not
   `cannot_play`; e2e/ii0 asserts the exact sentence from the saved note.
3. **A pickup's roster cost — done.** `trades.basis_best_move` nets a drop by `waivers.choose_drops`' rule (cost = the
   most of his lineup loss on the frame, his season value above replacement, his backup cover; net = gain − (cost −
   lineup loss)); up to three bench drops tried, best net wins. The roster-only pick is netted the same way before the
   two are compared (a pick the frame already uses as a fill — the partner's kicker covering a bye — is priced over the
   next free agent, `covered_move`'s number, and netted). The sentence names the drop and the netting:
   "(drop X; netted: his season value above replacement, 5.2)"; "(drop X)" when it costs nothing more.
4. **Re-save + e2e — done.** `save_ir2_fixtures.py --finder` twice (118 answers), `api_70587_ie0.json` re-recorded on
   the fixtures' API for the new "Try it" package (its non-trade keys restored to the saved ones). Trades / calculator
   e2e 214 passed / 6 skipped / 0 failed on both projects; the full run below.
5. **The nightly — see § 5 of the final message / below.**

Cut: nothing. Not done: the two "+0.0" alternatives below (§ Found, not mine).

## Evidence

### Worth proposing, before (main 99fb216) / after (dev/IU1), next four weeks, pinned clock

| League, roster | main: rows / worth | after: rows / worth | what changed in the worth list |
|---|---|---|---|
| League of Scrubs, 2 | 5 / 0 | 18 / 0 | — (13 → 0 rows dropped on the basis) |
| Test League, 3 | 14 / 0 | 18 / 1 | new #3: Team 7, D'Andre Swift → Davante Adams + Pittsburgh Steelers (+12.51 / +13.08) |
| Forever Unclean Dynasty, 12 | 20 / 18 | 22 / 19 | top 9 identical and in the same order (Taco Corp. Bo Nix → Jahmyr Gibbs +25.6; Ward of the Rings Bo Nix → Bucky Irving + Jeremiyah Love +24.18; The72Repeat Bo Nix → Breece Hall + Quinshon Judkins +20.87; …). Them GriDDy: Isaiah Likely + Emanuel Wilson → Tucker Kraft (+4.88) and Najee Harris → T.J. Hockenson (+2.92) replaced by Aaron Rodgers + Kenny Gainwell → Kyler Murray (+6.02 / +6.27); Emanuel Wilson → Kraft kept. New: Pitts n' Titts Rodgers + Jordan Addison → Josh Allen (+4.14 / +8.94), 2 da Moon Malik Washington + Caleb Douglas → Saquon Barkley (+1.43 / +2.85). |

Packages evaluated: 207 → 192 / 112 → 66 / 622 → 375; dropped on the basis 13 / 3 / 3 → 0 / 0 / 0.

### Finder timings (TestClient, one process per league; seconds)

| | main cold | after cold (×main) | roster-only, same run | main warm | after warm |
|---|---|---|---|---|---|
| Scrubs 2 | 3.415 | 4.581 (1.34×) | 3.797 | 0.056 | 0.025 |
| Test League 3 | 5.004 | 5.137 (1.03×) | 5.286 | 0.070 | 0.025 |
| Dynasty 12 | 5.103 | 4.765 (0.93×) | 4.988 | 0.082 | 0.027 |

Scrubs' extra second is the 13 more rows it now shows (each is the calculator's decision); the search itself 0.67 →
1.03 s. Within 1.5× of the brief's 3.0 / 4.2 s too (4.5 / 6.3).

### The Folk case (Scrubs roster 2, a full roster; also `api/tests/test_iu1.py::test_the_folk_case_nets_the_drop_on_the_basis` on the clone)

| your best move | drop | gross | cost (piece) | netted |
|---|---|---|---|---|
| IT-1 (main): Washington Commanders defense | Jacory Croskey-Merritt | +6.71 | — (not netted) | — |
| the same claim, netted | Jacory Croskey-Merritt | +6.71 | 5.19 (season value above replacement; backup cover 0.58) | +1.52 |
| **IU-1**: Washington Commanders defense | **Bryce Young** | +6.71 | 0 (no starts, no season value, no backup cover) | **+6.71** |
| (Travis Kelce, tried in the probe) | | +6.48 | 2.74 (season value) | +3.97 |

Words: "the Washington Commanders defense claim gives +6.7 over weeks 5–8 (drop Bryce Young); Jacoby Brissett is
already counted in every number here (he fills a starting spot that is empty)" — the roster-only pick Brissett (drop
Young), netted on the frame: 0.0 (the PO's clause, still true). The partner (Run Bijan Run): its roster-only pick Cameron
Dicker (drop Rhamondre Stevenson) was not netted on main (Dicker is the frame's fill for Reichard's bye, so the basis
search could not price him: +2.0); now priced over the next free kicker and netted for Stevenson's season value (19.98):
−17.97 → their best move is standing pat (0); the verdict: "Run Bijan Run's starters end 1.3 behind their own best move"
(was 3.3). The calculator line: "add Cameron Dicker, drop Rhamondre Stevenson (netted: his season value above
replacement, 20.0): +0.0 over weeks 5–8 on the same basis".

## 2. Commits (dev/IU1, from main 99fb216)

- `89792cd` the partner search can propose on the replacement frame; the switch; the rule, before its numbers
- `b23fae6` (wip) the roster-only ladder removed, IE-1 on the search's frame; the basis waiver move nets its drop; the
  sentences say the drop and the netting
- `e654237` the fill-used pick priced over the next free agent and netted; "(drop X; netted: …)" in one pair of
  parentheses; `partnerReason` reads the note; tests; answers re-saved, ie0 re-recorded; ct1.3, WORDS, METRICS, CHANGELOG
- `2a7713d` the PO's clause reads the gain before netting (`covered_gross_window`); answers re-saved again
- this hand-back

## 4. Tests

- `tests/test_iu1_trades.py` (new, 5): the bye cover is worth what it adds over the free QB (roster-only +15, frame +1);
  the bounded search on the frame finds the exhaustive best 1-for-1 (and not the roster-only search's bye cover);
  every proposed package is priced on the frame (= `package_gains_covered` when no free agent is shared); the drop is
  netted (season value beyond lineup loss picks the other bench player); a pick the frame uses as a fill is priced
  as `covered_move` prices him.
- `api/tests/test_iu1.py` (new, 3): `search_basis` "replacement", the roster-only ladder gone, every row raises both
  lineups, the worth list never shorter than the roster-only switch's (Scrubs); the sentence's drop / netting / the PO
  clause against a cancelling net; the Folk case (drop Bryce Young, the partner's Dicker netted, no nested parentheses).
- Root suite: 1,710 passed / 4 failed (all four in known_root_failures) / 3 skipped. `scripts/gate.sh python`: GATE
  PASSED (783 root + 34 api). ruff clean; `copy_standard.py --check` clean; web lint 0 errors, build clean.
- API trade files (test_it1 ir2 il4 ii1 if2 ia2 ie1 ie2 ie0 ii0 ib0 ig1 ir0 decisions in5 ih2 iu1): 160 passed /
  45 failed / 3 skipped — every failure in /home/claude/waveIP/known_api_failures.txt (none new); test_iu1 + test_it1
  re-run after the last change: 13 passed.
- e2e (FIXTURES_PORT=8917): Trades / calculator specs (decisions h1 ia2 ib1 ib2 ie0 ie1 ie2 if2 ig1 ii0 ii1 ii6 in1 in2
  inf1 ip3 iq4 ir1 ir2 ir4 il1 il2 il5) on phone + desktop: **214 passed, 6 skipped, 0 failed**; then **one full run:
  599 passed, 17 skipped, 0 failed** (616, 13.5 min). The first trade run had ie0 "Finder → Try it" failing on both
  projects (the new first team-QB package had no saved calculator answer): re-recorded, green.

## 5. Edits outside my files

`dbt/seeds/metric_registry.csv` (the `credible_trade` row: ct1.2 → ct1.3 and its note), `docs/METRICS.md` (§ The
Trade Finder searches on the basis), `docs/WORDS.md` (§ IU-1), `CHANGELOG.md` (new top heading "2026-10-09 — Wave I-U",
one bullet). Readers of the changed words (`grep` of `scripts/` and `web/e2e/`): `post_deploy_check.py` reads the
verdict / headline / fit words only (unchanged); e2e ii6 / if2 / ii1 read the alternative sentence from the saved
answers (re-saved); nothing parses "(drop …)".

## 6. PO lines changed (as a diff)

```diff
 rop = alt.get("roster_only_pick") or {}
 rname = (rop.get("player") or {}).get("player_name")
-covered = rop.get("covered_window")
+covered = rop.get("covered_gross_window", rop.get("covered_window"))   # IU-1: before any netting of his drop
```

The roster-only pick's `covered_window` is now netted for his drop; the clause ("…is already counted in every number
here (he fills a starting spot that is empty)") is about what he adds over the free fill, so it reads that number,
kept beside it. Scrubs still says it (Brissett: 0.0 gross, 0.0 netted).

## 7. Found, not mine

- A best move that adds nothing is still said as a move: Dynasty 12's "the Michael Mayer claim gives +0.0 over weeks
  5–8 (drop Chris Godwin Jr.; netted: his backup cover, 0.1)" (main: "+0.0 … (drop Chris Godwin Jr.)"; IF-1's fill pick,
  kept because nothing beats it on the frame); the Folk partner's "add Cameron Dicker, drop Rhamondre Stevenson
  (netted: …, 20.0): +0.0 … on the same basis". `_alt_gain` already counts both as standing pat (0); the words do not.
- On the basis, giving a kicker or a defense is worth what the free one adds back: those packages now lead "Explore"
  (Scrubs: Michael Wilson + Buffalo Bills → Chuba Hubbard, +11.83; Nick Folk → MarShawn Lloyd, +8.7; Test League:
  Baltimore Ravens → Tyler Warren, +15.82). None is worth proposing (the streamable guardrail), and none was proposed by
  the roster-only search. A PO call: keep (the basis's honest number) or keep them out of the search (`allow`).
- Test League: dropping Ladd McConkey costs 0 — his rest of season (127.9) is under the WR replacement (173.5) in
  `price_by_player`. The model's rule; reads oddly.
- `basis_best_move(only=…)` for a pick that drops a *starter* counts the free pool's refill of his slot (a second
  pickup; the probe's Jaylen Wright: "lineup loss" −3.94). The search itself never drops a starter while anyone sits.
- The calculator's cold evaluate is slower with the netting (measured mid-wave: the Folk package 0.7 → 1.5 s, a new
  partner 0.2 → 0.5 s: three drops tried and the roster-only pick priced).

## 8. Next

The "+0.0" moves said as standing pat (both teams; Waivers keeps its own pick); the K / DEF giveaways in Explore; a
starter's drop in the `only` path priced without the refill; the evaluate's netted search cached per window.

## The nightly

Nothing the nightly computes changes. `trades.partners` keeps its roster-only default (`free=None`); its one other
caller, `reports.py` (`league-lab report`), is not in `nightly.sh`. `basis_best_move`, `package_gains_covered` and the
decisions changes are read only by the API. The nightly's dbt build seeds `metric_registry.csv`, so the
`credible_trade` row's new version and note land in that table (text). The post-publish check (in CI) calls the live
`/api/trades/evaluate` and reads its verdict / headline / fit words, which this package does not change.
