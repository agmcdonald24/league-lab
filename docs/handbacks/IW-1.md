# IW-1 — who starts at quarterback, decided by the data (Wave I-W)

**Start 15:34 ET, Saturday 2026-10-10; end 16:49.** Branch `dev/IW1` (from `main` 5a0b9ac), `/home/claude/wt-iq4`,
database `league_lab_iq4`. The rule: docs/METRICS.md § "Who starts, decided by the data" (sq1.0).

## 1. Done / not done / cut

* **Read first** (item 1) — what each source knew on the copy:
  * Seattle week 4 and 5: the schedule lists Drew Lock both weeks; the depth chart's newest snapshot before each
    kickoff (daily, about 06:00 UTC; the copy's last is 5 Oct) puts Sam Darnold first; Darnold led the dropbacks in
    weeks 3 and 4 (46, 26); no report names either.
  * Chicago week 5: the schedule lists Case Keenum (35 dropbacks in week 3); the 5 Oct chart reads Caleb Williams,
    Tyson Bagent, Keenum; Bagent led week 4 (36); all three ACT on week 5's roster; Sleeper's "Out" for Williams is
    dated 2 Oct — before week 4's last game, so the gate reads it as week 4's (stale); no week-5 report on the copy.
  * Baltimore week 5: the schedule and the chart name Lamar Jackson; he led week 4 (23, Tyler Huntley 10); on the copy
    Sleeper says Questionable (4 Oct) until I ruled him Out (§ 3).
* **Candidates and the rule, before any new number** (items 2–3): done — committed `b6dc3c1` 15:36, the study run at
  15:37. S4 (seen on 7 Oct), S5 the snaps first, S6 two of three; Sleeper's `depth_chart_order` is not a candidate (one
  snapshot, no dated history: gradable only from now). **The rule picks S4.**
* **Shipped** (item 4): `int_pn_team_game` — an unplayed game with a listing takes S4's pick (`starter_source` 'data'
  where it differs); availability as `availability_gate` asks it (report Out / Doubtful, reserve lists, and for the
  nearest week Sleeper's directory codes with the gate's stale rule); Questionable is available. **The hand list is
  emptied** (`starter_overrides.csv` = its header); the mechanism stays, unused. Seattle and Baltimore come out right
  from the data alone; **Chicago does not** (§ 3).
* **Words** (item 5): done — no "set by hand" / "Starter corrected" in any API answer, screen, saved answer or spec;
  one sentence when the pick differs from the listing ("Seattle: we project Sam Darnold to start — he led the team's
  dropbacks in week 4; the schedule lists Drew Lock."), the chip says "Who starts"; a listing the rule keeps against
  the chart stays "Starter unclear" (U1, one sentence); "Who should I start?" keeps its lean for the rule's pick, no
  hand-set branch (caveat kind `starter_projected`); About says where the starter comes from.
* **Cut: item 6** (the site grading its own pick: a record table, `mart_starter_check`'s accuracy, About's line) —
  not built. No `STATE_TABLES` / `RECORD_TABLES` line is needed from this package.

## 2. Commits

* `b6dc3c1` IW-1: the rule that picks who starts, before any new number (sq1.0: S4 seen, S5 the snaps first, S6 two of three; the pick = the most accurate of those fixing >= 80% of stale listings)
* `b65464e` IW-1: the candidates' numbers and the pick (S4, by the rule committed first); who starts from the data in int_pn_team_game (an unplayed game with a listing: S4's pick; availability as the gate asks it); the han
* `b403ff4` IW-1: the words — no 'set by hand', no 'Starter corrected': one sentence when the sources disagree (who we project and why), 'Who starts' chip, the caveats a lean without the hand-set branch (kind starter_proje
* `9709349` IW-1: S5 / S6 tests (a starter back from injury, ruled out, Seattle's stale listing, three names, no chart); CHANGELOG
* `1abdf2e` IW-1: sq1.0 in the metric registry
* `7fe68d2` IW-1: the directory's word applies to the nearest week not yet kicked off (the clock; var starter_now for the unit test) — a Monday game the copy has no box score for no longer drags it back a week
* `dee0ded` IW-1: the pick's sentence says why when the listed starter is ruled out (Baltimore's case)
* the saved answers re-recorded and this file (the last commits)

## 3. Evidence

### The candidates (`iq2_starter_source.py study`, 15:37 ET, after the rule's commit `b6dc3c1`)

Played team-games of 2025 – 2026 week 4 (670; 12 stale listings; 21 in-game changes no rule can see). The listing's
0.951 is helped by hindsight: nflverse rewrites a played game's listing to the real starter after the game, so the
live listing (Seattle's Drew Lock for two weeks after Darnold took over) is worse than its history.

| Candidate | Accuracy (listing 0.951 →) | Stale fixed | Fixed | Newly broken | ≥ 80%? |
|---|---|---|---|---|---|
| **S4 two sources agree** (its numbers seen on 7 Oct) | **0.957** | 10 of 12 | 10 | 6 | yes |
| S5 the snaps first | 0.916 | 10 of 12 | 10 | 33 | yes |
| S6 two of three | 0.954 | 10 of 12 | 10 | 8 | yes |
| S5 on 2021 – 2024 (no chart: the newest leader, else the listing) | 0.912 (listing 0.956) | 29 of 37 | 37 | 133 | — |

**The pick: S4.** Its 6 newly broken (pick / who started): Arizona 2025 wk 6 Kyler Murray / Jacoby Brissett; Atlanta
2025 wk 8 Michael Penix Jr. / Kirk Cousins; Buffalo 2025 wk 18 Josh Allen / Mitchell Trubisky; the Chargers 2025 wk 18
Justin Herbert / Trey Lance; Philadelphia 2025 wk 18 Jalen Hurts / Tanner McKee; Pittsburgh 2025 wk 12 Aaron Rodgers /
Mason Rudolph — starters rested or held out late. The starter back from injury breaks S5 (Baltimore 2025 wk 9: Tyler
Huntley for Lamar Jackson; Washington wk 5 and 9: Marcus Mariota for Jayden Daniels; San Francisco wk 4 and 11; 33 in
all), not S4 (listing and chart name him). S6's 8: S4's 6, Chicago 2026 wk 3 (Tyson Bagent for Case Keenum) and Green
Bay 2025 wk 18 (Jordan Love for Clayton Tune).

### Seattle, Chicago, Baltimore from the data alone (week 5 on the copy; hand list empty)

| Team | Listing | Chart's first available | Newest game's leader | Pick | Right? |
|---|---|---|---|---|---|
| Seattle | Drew Lock | Sam Darnold | Sam Darnold (wk 4) | **Sam Darnold** ('data') | yes |
| Baltimore (made on the copy: Lamar Jackson ruled Out in Sleeper's directory, dated 9 Oct) | Lamar Jackson | Tyler Huntley | Lamar Jackson (wk 4) | **Tyler Huntley** ('data') | yes |
| Chicago | Case Keenum | Caleb Williams | Tyson Bagent (wk 4) | **Case Keenum** (the listing) | **no** |

Chicago fails: the listing is stale and the other two sources disagree, so S4 keeps the listing. Which source failed:
the schedule (still Keenum). What would fix it: the week-5 report ruling Williams out (then the chart's first available
is Bagent, who also led week 4: S4 picks Bagent) — on the copy there is no week-5 report and Sleeper's 2 Oct "Out" is
week 4's by the gate's stale rule; with Williams only Questionable, a rule that drops a listing nobody else names (S7,
§ 7) — not run. Chicago's row says "Starter unclear: The Bears list Case Keenum …, but the depth chart puts Caleb
Williams first. Our projections assume the listing …" and "Who should I start?" gives no call on him.

**Baltimore on the copy** (made as IV-1 did: Lamar Jackson's Sleeper entry set to Out, dated 9 Oct 15:00 UTC; the `game`
chain at 16:21; undone at 16:32 and the chain run again clean): the pick is Tyler Huntley from the data alone
('data'), and the live week follows (League of Scrubs / ref:half, the same numbers):

| | kickoff board | live | the row's sentence |
|---|---:|---:|---|
| Tyler Huntley | 4.76 | **20.71** | "Baltimore: we project Tyler Huntley to start — Lamar Jackson, the listed starter, is ruled out and he is next on the depth chart." |
| Lamar Jackson | 16.77 | **0** (Out (ankle) · Sleeper, Oct 9) | Not playing |
| Zay Flowers | 12.08 | 12.17 | — (receivers read no QB input) |

Seattle in the same run: Sam Darnold 15.39 → 15.41 (he was already the projected starter, by the hand row then),
"Seattle: we project Sam Darnold to start — he led the team's dropbacks in week 4; the schedule lists Drew Lock."
Chicago: Case Keenum 5.15 → 16.38, Tyson Bagent 14.88 → 2.97, and "Starter unclear: Chicago lists Case Keenum as the
starter, but the depth chart puts Caleb Williams first. …" (§ 7).

### The quarterback rows that move against `main` (week 5's live overlay, both house leagues; ≥ 0.5 points)

`main` = the PO's `game` chain of last night (hand list: Seattle → Darnold, Chicago → Bagent); IW-1 = the `game` chain
at 15:49 (no Baltimore case):

| League | QB | main | IW-1 | Why |
|---|---|---:|---:|---|
| Dynasty / Scrubs | Case Keenum (CHI) | 6.76 / 5.35 | 21.34 / 16.59 | the rule keeps the listing (above) |
| Dynasty / Scrubs | Tyson Bagent (CHI) | 19.61 / 15.03 | 3.72 / 2.87 | the hand row is gone |
| Dynasty / Scrubs | Caleb Williams (CHI) | 9.64 / 8.24 | 8.44 / 7.21 | his teammates' inputs |
| Dynasty | Jared Goff (DET) | 30.29 | 26.72 | no starter change: the chains' run-to-run drift (§ 7) |
| Dynasty / Scrubs | Josh Allen (BUF) | 27.82 / 23.14 | 26.42 / 21.80 | the same |
| Dynasty / Scrubs | Aaron Rodgers (PIT) | 21.22 / 16.09 | 20.48 / 15.49 | the same |

Seattle does not move (Darnold both: the hand row then, the data now). **The record, weeks 1–5, 0 rows differ** against
`main` in all ten record tables (`ops.projections` 6,032 rows, `projection_lines` 2,954, `projection_ranges` 14,770,
`kd_lines` 316, `kd_ranges` 1,580, `lineup_record` 2,249, `context_record` 4,620, `projection_drift` 32,
`mart_projection_record` 10, `mart_projection_drift` 8).

### The chains (`LEAGUE_LAB_FREEZE=game /home/claude/waveIT/chain.sh /home/claude/wt-iq4 league_lab_iq4`)

Clean (15:49, before the nearest-week fix; no Baltimore case), 774 s:

```
== 15:49:39 db migrate
== 15:49:41 dbt build (full)
19:56:30  Done. PASS=734 WARN=5 ERROR=0 SKIP=0 NO-OP=0 TOTAL=739
== 15:56:30 project
== 16:02:06 projection marts
20:02:19  Done. PASS=145 WARN=0 ERROR=0 SKIP=0 NO-OP=0 TOTAL=145
== 16:02:19 availability guards (as errors)
20:02:28  Done. PASS=2 WARN=0 ERROR=0 SKIP=0 NO-OP=0 TOTAL=2
== 16:02:28 audit
## Players who cannot play or are unlikely to play and are ranked or valued on the screens: 0
== 16:02:33 done
== 16:02:38 END
```

With the Baltimore case (16:21, final code), ERROR 0 in every step, both availability guards as errors, the audit's
first line 0:

```
== 16:20:59 db migrate
== 16:21:00 dbt build (full)
20:26:17  Done. PASS=734 WARN=5 ERROR=0 SKIP=0 NO-OP=0 TOTAL=739
== 16:26:18 project
== 16:31:45 projection marts
20:31:59  Done. PASS=145 WARN=0 ERROR=0 SKIP=0 NO-OP=0 TOTAL=145
== 16:31:59 availability guards (as errors)
20:32:07  Done. PASS=2 WARN=0 ERROR=0 SKIP=0 NO-OP=0 TOTAL=2
== 16:32:08 audit
## Players who cannot play or are unlikely to play and are ranked or valued on the screens: 0
== 16:32:13 done
== 16:32:17 END
```

The Baltimore case undone (Lamar Jackson's directory row as it was), clean again (16:32), ERROR 0 in every step — the
copy is left in this state (hand list empty in the seed and the seeded table: 0 rows; Seattle 'data', Chicago and
Baltimore the listing):

```
== 16:32:45 db migrate
== 16:32:46 dbt build (full)
20:38:06  Done. PASS=734 WARN=5 ERROR=0 SKIP=0 NO-OP=0 TOTAL=739
== 16:38:06 project
== 16:43:29 projection marts
20:43:42  Done. PASS=145 WARN=0 ERROR=0 SKIP=0 NO-OP=0 TOTAL=145
== 16:43:42 availability guards (as errors)
20:43:50  Done. PASS=2 WARN=0 ERROR=0 SKIP=0 NO-OP=0 TOTAL=2
== 16:43:50 audit
## Players who cannot play or are unlikely to play and are ranked or valued on the screens: 0
== 16:43:55 done
== 16:43:59 END
```

## 4. Tests

* dbt: the full build's tests in every chain, PASS 734, ERROR 0 — including the new unit test
  `int_pn_team_game::starter_from_data_decides_unplayed_games` (Seattle-, Chicago- and Baltimore-like teams, a team
  without a chart, played games untouched) and IQ-2's unit test with the new inputs mocked; `assert_personnel_is_asof`
  reads 'data' like 'override'.
* `tests/test_iq2_starter_source.py` 5 passed (S5 / S6: a starter back from injury, ruled out, Seattle's stale listing,
  three names, no chart). `tests/test_metric_registry.py`: sq1.0 registered.
* `scripts/gate.sh python`: **GATE PASSED** (root 783, api 36, ruff). ruff `src app tests api`: clean. Copy standard:
  clean. `web`: lint 0 errors / 0 warnings, build OK.
* `check_root.sh`: 1,743 passed; new against the known list: `test_metric_registry` (fixed since: sq1.0's row) and
  `tests/test_ros.py::test_mart_matches_the_trade_engines_sum_on_the_same_weeks` — the ROS mart reads the live week's
  overlay, `trades.MARKET_SQL` reads `ops.projections` on its own connection, so while the overlays hold rows (this
  copy, the PO's `game` chains) the two sums differ: Wave I-V's state, no code of mine in either path (§ 7).
* API test files of every route that carries starter words (rankings, start/sit, the card, My Week, Waivers / team /
  trades' caveats: `test_iq2`, `test_ir4`, `test_it3`, `test_iu3`, `test_ip2`, `test_is2`, `test_ir0`, `test_it2`,
  `test_is1`, `test_ir1`, `test_myweek`, `test_player`, `test_decisions`, `test_iv1`): 158 passed, 14 failed — 12 in
  the known list, 2 (`test_decisions::test_waivers_house_route_is_the_mart` ×2) fail the same way on `main`'s code on
  this copy (shown in IV-1: the stored waiver week is 5, the test expects 4). **New failures: none.** Updated on
  purpose: `test_iq2` (the pick's sentence, the database's week 5), `test_ir4` / `test_it3` / `test_iu3` (kind
  `starter_projected`, the words).
* e2e, both projects: `ir4`, `io4`, `ip2` 26 passed (`ir4`'s saved answer: Seattle's row sentence is the new one and Chicago's hand-set pick is gone — what the API answers on the copy; `ir4` 12 / 12 again after); `iq2` re-recorded from the copy (desktop, `IQ2_LIVE`) — the only
  saved answer re-recorded; the others changed only in the sentences above (78 files, one or two lines each) — then
  desktop 2 / 2 and phone 1 / 2: the phone's first test passes every starter assertion and then fails its "nothing
  wider than the screen" check on Rankings' **Not playing** rows (Jaxson Dart, Dillon Gabriel, Graham Mertz on IR:
  right edge 389 px at 375), which the re-recorded answer now carries and the October 7 one did not (§ 7).

## 5. Edits outside my files

Each marked `# ---- IW-1` (or in an IW-1 block): `dbt/models/intermediate/features/int_pn_team_game.sql` (the rule),
`int_starter_override.yml` (unit tests' inputs + the new unit test), `int_player_week_personnel.yml` (accepted value
'data'), `dbt/tests/assert_personnel_is_asof.sql` ('data' like 'override'); `api/league_lab_api/starters.py`
(`projected_words`, `corrected_from` reads the pick, U1 skips a rule-set team), `provenance.py` (rule words, kind
`starter_projected`), `league_gate.py`, `rankings_api.py` (the lean's words), `about.py`; `web/src/routes/Rankings.svelte`
(chip text), `web/src/lib/api.ts` (kind), `web/src/lib/about.ts`, two comments in `MyWeek.svelte` / `Waivers.svelte`;
`scripts/analysis/iq2_starter_source.py` (S5, S6); specs `web/e2e/iq2`, `web/e2e/ir4`; saved answers (§ 4).

## 6. PO lines

**`app/whats_new.md`** — the screen still says "a starter we set by hand" (Oct 9's entry); a new top entry and that
bullet reworded:

```diff
--- a/app/whats_new.md	2026-10-10 16:21:54.358796678 -0400
+++ b/app/whats_new.md	2026-10-10 16:22:02.388252505 -0400
@@ -3,6 +3,14 @@
 Written for the people in the league, newest first. Home shows the top entry. Every release adds one here
 in plain words (docs/WORDS.md); CHANGELOG.md keeps the technical version.
 
+## Oct 10 · who starts at quarterback comes from the data
+
+- **Nobody picks a starting quarterback by hand any more.** We take the schedule's listed starter unless he is ruled
+  out, or the depth chart and the team's last game both name someone else; then we project that quarterback, and his
+  row says so in one sentence ("Seattle: we project Sam Darnold to start — he led the team's dropbacks in week 4; the
+  schedule lists Drew Lock."). On every game of 2025 and of this season through week 4 it named the quarterback who
+  started about 96 times in 100.
+
 ## Oct 9 (night) · this week's numbers keep up with the news until each game kicks off
 
 - **A week no longer stands still after Thursday night.** The numbers for a week used to be set at its first kickoff
@@ -24,8 +32,8 @@
   another, and so missed some trades, two-for-ones among them. Each suggestion is still the calculator's own verdict.
 - **A waiver move named beside a trade now counts what you give up.** It names the player you would drop and takes
   his value off the gain.
-- **"Who should I start?" tells you when a call leans on a starter we set by hand.** If a team's starting
-  quarterback was corrected by hand, the answer says to read it as a lean.
+- **"Who should I start?" tells you when a call leans on a starter the sources disagree on.** If a team's starting
+  quarterback is not the one the schedule lists, the answer says to read it as a lean.
 - **A player's card says more when he is hurt.** Questionable shows how often such players play (about 2 in 3; closer
   to half for quarterbacks). A week he will miss reads "0, he sits" with the reason, not a bare 0.0.
 - **Trends no longer calls a player "due" in a week he will not play.** He is listed apart, with the reason.
```

No nightly, workflow or render line (item 6, which needs a `STATE_TABLES` / `RECORD_TABLES` line, was cut). The way
back, if ever: `--vars '{starter_from_data: false}'` on the nightly's dbt build gives the listing back (the hand list
stays empty).

## 7. Found, not mine

* **Chicago is where S4 is weakest, live.** The listing (Case Keenum) is stale and S4 keeps a listing unless the chart
  and the newest game agree on someone else; here they do not (the chart: Caleb Williams first; week 4: Tyson Bagent).
  With Williams Questionable (available) S4 keeps Keenum — wrong whoever starts. The 2 Oct "Out" in Sleeper's copy is
  read as week 4's by the gate's stale rule. A candidate for the next study, **written here before any number**: S7 =
  S4, except that a listing neither the chart's first available quarterback nor the newest game's dropback leader names
  is not kept (then the chart's first available). Not run, not shipped.
* `tests/test_ros.py::test_mart_matches_the_trade_engines_sum_on_the_same_weeks` fails on this copy while the live
  overlays hold rows (the ROS mart reads the live mart, `trades.MARKET_SQL` reads `ops.projections` on its own
  connection): Wave I-V's state, not this change (§ 4).
* **Rankings' "Not playing" rows overflow at 375 wide** (each row's right edge 389 px): IR-1's list layout; the iq2 spec's
  phone run shows it now that its saved answer carries those rows. Not touched.
* Run-to-run drift of weeks 6–18 between two chains (hb1.0's weights; IU-2 / IV-1) is still there: the QB rows of
  Detroit, Buffalo and Pittsburgh in § 3 move without any starter change.

## 8. Next

1. Item 6, cut tonight: the record of the pick at each kickoff (the week's first kickoff and the live pick), graded
   against the game's dropback leader, in `mart_starter_check` and one About line; the PO's `STATE_TABLES` /
   `RECORD_TABLES` line with it.
2. S7 (§ 7) on 2025 – 2026 week 4 by the same rule, then live grading of S4 against S7 from week 5.
3. The Sunday refresh after the inactives (the roadmap's third item) would settle Chicago-like cases on game day.
