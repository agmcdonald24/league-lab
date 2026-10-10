# IW-1 — who starts at quarterback, decided by the data (Wave I-W)

**Round 1: start 15:34 ET, Saturday 2026-10-10; end 16:49. Round 2: 16:49 – 16:52 (stopped by the PO's rule). Round 3:
start 16:52:47 ET (read from `date`), end 17:27.** Branch `dev/IW1` (from `main` 5a0b9ac), `/home/claude/wt-iq4`,
database `league_lab_iq4`. The rule: docs/METRICS.md § "Who starts, decided by the data" (sq1.0; sq1.1 = the PO's
decision).

## Round 3 (the PO's decision: S7 ships, S4 recorded beside it, both graded)

* **0. The decision in METRICS** (`3775ffc`, first): § "Who starts, decided by the data", "The PO's decision (round
  3, 16:53 ET) — sq1.1", in the PO's words; then a "Shipped (sq1.1)" paragraph and "The record" (`b8f000d`).
* **1. S7 shipped** (`2e9e11f`, `14f598b`): `int_pn_team_game`'s `starting_qb_id` = S7's pick for every unplayed game
  with a listing; `s4_qb_id`, `s7_qb_id`, `starter_reason` (`listing_out` | `two_sources` | `unsupported`) and
  `starter_rule` kept on the row. **The way back: dbt var `starter_from_data`** = `s7` (default) | `s4` (the study's
  pick) | `false` / `off` / `listing` (the listing, as before IW-1). The dbt unit test now has a Chicago-like team
  (listed Keenum-like, chart's first a Questionable Williams-like, last week's leader a Bagent-like → the Williams-like,
  'data'). Chicago on the copy, today's facts (Williams Questionable in Sleeper's copy — the 2 Oct "Out" is week 4's by
  the gate's stale rule; chart Williams first; week 4's snaps Bagent; listing Keenum):

  | Case | Pick | `starter_source` / reason | The sentence on Williams', Keenum's (and the pick's) rows |
  |---|---|---|---|
  | today's facts | **Caleb Williams** | data / unsupported | "Chicago: we project Caleb Williams to start — the depth chart lists him first; the schedule still lists Case Keenum; Tyson Bagent took the snaps in week 4." |
  | Williams ruled Out (made on the copy: Sleeper's row Out, dated 10 Oct 15:00 UTC; undone, row back to `11560|Out|1790961024845|Out`) | **Tyson Bagent** | data / two_sources | "Chicago: we project Tyson Bagent to start — he led the team's dropbacks in week 4; the schedule lists Case Keenum and the depth chart lists Caleb Williams first." (on Bagent's and Keenum's rows; Williams' row: Not playing) |

  Seattle unchanged (Sam Darnold, 'data', the same sentence); Baltimore on the copy = Lamar Jackson (the listing:
  Questionable on the copy, available — right; with him ruled Out, round 1 showed Tyler Huntley). The rows that move
  (week 5, the final `game` chain against round 1's final chain, S4):

  | League | QB | round 1 (S4: Keenum) | round 3 (S7: Williams) |
  |---|---|---:|---:|
  | Dynasty / Scrubs | Caleb Williams (CHI) | 9.25 / 7.84 | **23.02 / 18.61** |
  | Dynasty / Scrubs | Case Keenum (CHI) | 21.30 / 16.59 | **6.97 / 5.49** |
  | Dynasty / Scrubs | Tyson Bagent (CHI) | 4.12 / 3.16 | 4.40 / 3.42 |
  | Dynasty / Scrubs | Sam Darnold (SEA) | 20.30 / 15.68 | 20.02 / 15.45 |
  | Dynasty / Scrubs | Drew Lock (SEA) | 5.24 / 4.20 | 5.28 / 4.23 |
  | Dynasty / Scrubs | Lamar Jackson (BAL) | 20.88 / 16.51 | 21.36 / 16.91 |

  Seattle and Baltimore move by the chains' run-to-run drift only.

  The Out case was shown at the pick and the sentence (the model and the API, before the final chain); its projection
  numbers were not chained (one 12-minute chain was all the clock allowed, and it had to be the clean one).
* **2. The site grades its own pick** (`e61b3dc`): `ops.starter_record` (created by `db migrate`), written by
  `league-lab starter-record`: per team-game from 2026 week 5, the listing, S4's pick, S7's pick, the projected one and
  `shipped` (`s7`), rewritten until kickoff and never after; once the game is in, the dropback leader (`truth_qb_id`)
  and `listed_right`, `s4_right`, `s7_right`, `projected_right`. `mart_starter_check` carries each team's tallies
  (`record_games`, `record_projected_right`, `record_listed_right`, `record_s4_right`, `record_s7_right`). About:
  "Our projected starter was the game's quarterback in N of M games since week 5" — nothing while M is 0 (and nothing
  before the table exists). Plumbing on a pretend graded week (week 5 "played": leader rows marked `PRETEND-*` in
  `fct_player_game` — Chicago Bagent, Seattle Darnold, Baltimore Jackson; graded with the clock at 13 Oct):

  ```
  Run(season=2026, written=0, graded=3, rows=28)
   team | listed     | s4         | s7         | projected  | shipped | truth      | listed_right | s4_right | s7_right | projected_right
   BAL  | 00-0034796 | 00-0034796 | 00-0034796 | 00-0034796 | s7      | 00-0034796 | t            | t        | t        | t
   CHI  | 00-0028986 | 00-0028986 | 00-0039918 | 00-0039918 | s7      | 00-0038416 | f            | f        | f        | f
   SEA  | 00-0035704 | 00-0034869 | 00-0034869 | 00-0034869 | s7      | 00-0034869 | f            | t        | t        | t
  mart_starter_check: BAL 1 game, 1/1/1/1 right; CHI 1, 0/0/0/0; SEA 1, projected 1, listed 0, S4 1, S7 1
  About: Our projected starter was the game's quarterback in 2 of 3 games since week 5.
  -- undone: PRETEND rows deleted, the grades cleared, the mart rebuilt: 0 graded of 28, About: None
  ```

  The PO's lines (`scripts/nightly.sh`, § 6): the table in `STATE_TABLES` and `RECORD_TABLES`, and the step.
* **3. `project`'s waiver solve reads the live week** (`b13a6e0`): `waivers.value_inputs` reads `MARKET_SQL` and
  `REPLACEMENT_SQL` through `live_week.sql(…, live_week.active_on(cur.connection))`; test
  `tests/test_iv1_live.py::test_the_waiver_solve_reads_the_market_and_the_replacement_through_the_live_week`.
  **`test_ros`'s check**: still failed with the overlays active after this fix (the test builds its own statement from
  `MARKET_SQL` on its own connection, not through either production path); it now reads the live week the way the
  engines do (`tests/test_ros.py`, three lines) and **with the overlays active (1,104 rows in `ops.projection_live`) it passes**.
* **4. Rankings' "Not playing" rows at 375 px** (`a892a29`): the list is one `minmax(0, 1fr)` column (`grid-cols-1`),
  each row `min-w-0`, long words wrap. **`iq2` passes on the phone project** (and desktop: 4 of 4), its answer re-recorded with S7.
* **5.** The chain, the tests and the copy below (§ 3, § 4).

## Round 2 (start 16:49 ET, stopped 16:52 by the PO's rule)

* **S7's rule committed first** (`09d75f6`, 16:49): S4 + an unsupported listing dropped; the PO's product ship rule
  (≥ 11 of 12 stale fixed, accuracy ≥ S4 − 0.003); history flatters the listing; a Questionable starter stated.
* **S7's numbers** (`e87a49a`, 16:50), the same 670 team-games:

| | Right | Accuracy | Stale fixed | Newly broken |
|---|---:|---:|---:|---:|
| S4 (shipped) | 641 | 0.9567 | 10 of 12 | 6 |
| S7 | 639 | 0.9537 (allowance ≥ 0.9537: met by a hair) | **10 of 12** (rule: 11) | 8 |

  S7 differs from S4 in two games, both newly broken: Chicago 2026 wk 3 (Tyson Bagent picked; Case Keenum started) and
  Green Bay 2025 wk 18 (Jordan Love picked; Clayton Tune started). Its 8 newly broken = S4's 6 (Arizona 2025 wk 6
  Murray / Brissett, Atlanta wk 8 Penix / Cousins, Buffalo wk 18 Allen / Trubisky, Chargers wk 18 Herbert / Lance,
  Philadelphia wk 18 Hurts / McKee, Pittsburgh wk 12 Rodgers / Rudolph) + those two. The two stale listings both still
  miss — Seattle 2026 wk 3 and Chicago 2026 wk 4 — had the listed quarterback leading the newest game (one source backs
  him). History flatters the listing (corrected after the games), so a rule that distrusts an unsupported listing looks
  worse in history than live; live, S7 would pick Caleb Williams for Chicago week 5.
* **Verdict by the PO's rule: S7 does not ship** (10 < 11). Per the instruction, I stopped there: items 2–5 of round 2
  (the Questionable cases, the self-grading record, the 375 px "Not playing" fix, the final chain and tests) were not
  started. S4 stays shipped; Chicago on the copy stays Case Keenum ("Starter unclear").
* **`trades.MARKET_SQL` outside `db._run`**: the live site's trade engine and Finder read it through `db._run`
  (`decisions.py` 732, 5109), so they and the season list agree. One production path does not: `project`'s waiver solve,
  `waivers.py:722` (`_frame(cur, MARKET_SQL, …)`, the stored waiver moves' rest-of-season market reads the kickoff board
  for the week under way). One-line fix: `_frame(cur, live_week.sql(MARKET_SQL, live_week.active_on(cur.connection)), …)`
  (and the same for `REPLACEMENT_SQL` on the next line). Also `reports.py:418` (the CLI's report pack, not the site).
  The failing `test_ros` reads on its own connection by design (a test).

## 1. Done / not done / cut

* **Round 3: items 0 – 5 done; nothing cut.** Not done: the projection numbers of Chicago's "Williams ruled Out" case
  went through the model and the API (pick Tyson Bagent, the sentence on each row), not through a chain (§ Round 3).
* Round 2: S7's rule and numbers; stopped by the PO's rule (above).
* Round 1:
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
* Round 1 cut item 6 (the site grading its own pick); **round 3 built it** (above).

## 2. Commits

Round 3:

* `3775ffc` the PO's decision in METRICS (sq1.1), first
* `2e9e11f` S7 shipped in `int_pn_team_game` (var `starter_from_data`), S4's and S7's picks kept; the unit test with a Chicago-like team
* `14f598b` the rule's reason reaches the row (`starter_reason`); S7's sentence for an unsupported listing
* `e61b3dc` the site grades its own pick: `ops.starter_record`, `league-lab starter-record`, `mart_starter_check`'s record, About's line
* `b13a6e0` `project`'s waiver solve reads the live week, with a test
* `a892a29` Rankings' "Not playing" rows inside a 375 px page
* `b8f000d` sq1.1 in METRICS, the registry row, WORDS, CHANGELOG
* `1e9e6a9` `test_ros` reads the live week as the engines do; the iq2 saved answer re-recorded with S7
* this file (the last commit)

Rounds 1 – 2 (`3b765d2`, `e87a49a`, `09d75f6` round 2):

* `b6dc3c1` IW-1: the rule that picks who starts, before any new number (sq1.0: S4 seen, S5 the snaps first, S6 two of three; the pick = the most accurate of those fixing >= 80% of stale listings)
* `b65464e` IW-1: the candidates' numbers and the pick (S4, by the rule committed first); who starts from the data in int_pn_team_game (an unplayed game with a listing: S4's pick; availability as the gate asks it); the han
* `b403ff4` IW-1: the words — no 'set by hand', no 'Starter corrected': one sentence when the sources disagree (who we project and why), 'Who starts' chip, the caveats a lean without the hand-set branch (kind starter_proje
* `9709349` IW-1: S5 / S6 tests (a starter back from injury, ruled out, Seattle's stale listing, three names, no chart); CHANGELOG
* `1abdf2e` IW-1: sq1.0 in the metric registry
* `7fe68d2` IW-1: the directory's word applies to the nearest week not yet kicked off (the clock; var starter_now for the unit test) — a Monday game the copy has no box score for no longer drags it back a week
* `dee0ded` IW-1: the pick's sentence says why when the listed starter is ruled out (Baltimore's case)
* the saved answers re-recorded and this file (the last commits)

## 3. Evidence

### Round 3's chain (`LEAGUE_LAB_FREEZE=game`, 17:09, the final code; 734 s) — ERROR 0 in every step

```
== 17:09:09 db migrate
== 17:09:11 dbt build (full)
21:14:57  Done. PASS=734 WARN=5 ERROR=0 SKIP=0 NO-OP=0 TOTAL=739
== 17:14:58 project
== 17:20:48 projection marts
21:21:08  Done. PASS=145 WARN=0 ERROR=0 SKIP=0 NO-OP=0 TOTAL=145
== 17:21:08 availability guards (as errors)
21:21:18  Done. PASS=2 WARN=0 ERROR=0 SKIP=0 NO-OP=0 TOTAL=2
== 17:21:18 audit
## Players who cannot play or are unlikely to play and are ranked or valued on the screens: 0
== 17:21:23 done
```

Then `league-lab starter-record`: 28 written (week 5's unplayed games with a listing), 0 graded, 28 rows; the copy is
left so (Chicago Williams 'data', Seattle Darnold 'data', Baltimore Jackson the listing; no made-up status; no pretend
rows). **The record, weeks 1 – 5, against `main`'s chain: 0 rows differ** in `ops.projections` (6,032),
`projection_lines` (2,954), `projection_ranges` (14,770), `kd_lines` (316), `kd_ranges` (1,580), `lineup_record`
(2,249), `context_record` (4,620), `projection_drift` (32), `mart_projection_drift` (8); `mart_projection_record` 2 of
10 differ: week 5's `in_play` row of each house league, `pairs_no_sleeper` 1 → 0 (the week under way, rebuilt every
night; its listed pairs now hold Caleb Williams, whom Sleeper projects, where Case Keenum was) — no kept week.

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

Round 3 (after the final chain):

* dbt: PASS 734, ERROR 0 (the unit test with the Chicago-like team among them); the projection marts 145, the guards 2.
* `scripts/gate.sh python`: **GATE PASSED** (root 783, api 36, ruff). ruff `src api tests scripts`: clean (3 old
  findings in `web/fixtures/save_*_fixtures.py`, untouched). Copy standard: clean. `web`: lint 0 / 0, build OK.
* `check_root.sh`: 1,750 passed, 4 failed — all four in the known list; **new failures: none** (`test_ros` and `test_metric_registry`, new in round 1, pass).
* API test files of the routes with starter words (the 14 files below): 159 passed, 14 failed — **the same 14 as round
  1** (12 known + `test_decisions::test_waivers_house_route_is_the_mart` ×2, which fail on `main`'s code on this copy).
* New: `tests/test_starter_record.py` (4), `test_iv1_live.py::test_the_waiver_solve_reads_…` (1),
  `api/tests/test_iq2.py` Chicago = Williams (the database week 5, Rankings' rows), `test_s7s_sentence_for_an_unsupported_listing`.
* e2e: `iq2` 4 / 4 (phone and desktop; saved answer re-recorded from the copy at 17:23, `IQ2_LIVE`), `ir4` + `ip2` +
  `io4` 26 / 26, both projects.

Rounds 1 – 2:

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

Round 3: `int_pn_team_game.sql` (S7, `starter_reason`, `starter_rule`), `int_starter_override.yml` (the Chicago-like
team), `mart_starter_check.sql` (the reason, both picks, the record's tallies), `dbt/models/sources/sources.yml`
(`ops.starter_record`), `metric_registry.csv` (sq1.1 replaces sq1.0's row); `src/league_lab/db.py` (migrate creates the
table), `cli.py` (`starter-record`), `waivers.py` (`value_inputs`); new `src/league_lab/starter_record.py`,
`tests/test_starter_record.py`; `tests/test_ros.py`, `tests/test_iv1_live.py`; `api/league_lab_api/about.py` (the
line, the learned-from words), `starters.py` (S7's sentence); `web/src/routes/About.svelte`, `web/src/lib/about.ts`,
`api.ts`, `web/src/components/availability/NotPlaying.svelte`; `web/e2e/iq2`, `web/fixtures/iq2/api_iq2.json`; docs
METRICS, WORDS, CHANGELOG.

Rounds 1 – 2: Each marked `# ---- IW-1` (or in an IW-1 block): `dbt/models/intermediate/features/int_pn_team_game.sql` (the rule),
`int_starter_override.yml` (unit tests' inputs + the new unit test), `int_player_week_personnel.yml` (accepted value
'data'), `dbt/tests/assert_personnel_is_asof.sql` ('data' like 'override'); `api/league_lab_api/starters.py`
(`projected_words`, `corrected_from` reads the pick, U1 skips a rule-set team), `provenance.py` (rule words, kind
`starter_projected`), `league_gate.py`, `rankings_api.py` (the lean's words), `about.py`; `web/src/routes/Rankings.svelte`
(chip text), `web/src/lib/api.ts` (kind), `web/src/lib/about.ts`, two comments in `MyWeek.svelte` / `Waivers.svelte`;
`scripts/analysis/iq2_starter_source.py` (S5, S6); specs `web/e2e/iq2`, `web/e2e/ir4`; saved answers (§ 4).

## 6. PO lines

**`scripts/nightly.sh`** — the starter record: the table in `STATE_TABLES` and `RECORD_TABLES` (never rebuilt, so a
fresh database must get it back from the hosted copy), and the step after the context record (soft; idempotent):

```diff
--- a/scripts/nightly.sh	2026-10-10 17:11:37.015855710 -0400
+++ b/scripts/nightly.sh	2026-10-10 17:11:37.080040074 -0400
@@ -288,6 +288,11 @@
 STATE_TABLES="$STATE_TABLES ops.horizon_record"
 RECORD_TABLES="$RECORD_TABLES ops.horizon_record"
 # ---- end IU-5
+# ---- IW-1 (Wave I-W): the starter record (sq1.1): the listing, S4's and S7's picks kept until kickoff, graded after the
+# game; never rebuilt (a night lost loses that night's rewrite only), so record as well as state
+STATE_TABLES="$STATE_TABLES ops.starter_record"
+RECORD_TABLES="$RECORD_TABLES ops.starter_record"
+# ---- end IW-1
 # ---- IV-1 (Wave I-V): fr1.1, the live week's overlays (LEAGUE_LAB_FREEZE=game): a game that kicked off keeps the last
 # live number written before its kickoff until the week is over, so they are state (not record: no grade reads them).
 # `db migrate` creates them; a copy that does not have them yet is "not published there"; empty with the switch unset.
@@ -558,6 +563,12 @@
 # ops.context_record, graded after the games in ops.context_grade (docs/METRICS.md § "The context record").
 SOFT_WHY="the record's kept weeks are untouched; a week missed tonight is rebuilt from as-of inputs (labelled reconstructed)" soft context-record uv run league-lab context-record
 # ---- end IO-1
+# ---- IW-1 (Wave I-W): the starter record (league-lab starter-record; idempotent): every unplayed game's listing, S4's
+# and S7's picks rewritten until kickoff, the games that are in graded against the dropback leader (docs/METRICS.md
+# § "Who starts, decided by the data", sq1.1). About's line reads the table; mart_starter_check's tallies are the last
+# full build's (one night behind).
+SOFT_WHY="the record keeps last night's picks; tonight's kickoffs keep the pick from the last run before them" soft starter-record uv run league-lab starter-record
+# ---- end IW-1
 # plan E1: Sleeper's projections for the next week to kick off, one snapshot a night, so the record has the last one
 # saved before the first kickoff (the moment this board freezes). Soft: a failed pull loses one night's snapshot.
 if [ "${NIGHTLY_SLEEPER_OFFLINE:-}" = 1 ]; then
```

**`app/whats_new.md`** — replaces round 1's diff (the top entry now says S7's clause and the weekly grade; Oct 9's
"a starter we set by hand" reworded):

```diff
--- a/app/whats_new.md	2026-10-10 17:11:17.186859212 -0400
+++ b/app/whats_new.md	2026-10-10 17:11:17.262193810 -0400
@@ -3,6 +3,17 @@
 Written for the people in the league, newest first. Home shows the top entry. Every release adds one here
 in plain words (docs/WORDS.md); CHANGELOG.md keeps the technical version.
 
+## Oct 10 · who starts at quarterback comes from the data
+
+- **Nobody picks a starting quarterback by hand any more.** We take the schedule's listed starter unless he is ruled
+  out, the depth chart and the team's last game both name someone else, or neither of them names him; then we project
+  the quarterback the data points to, and his row says so in one sentence ("Chicago: we project Caleb Williams to
+  start — the depth chart lists him first; the schedule still lists Case Keenum; Tyson Bagent took the snaps in week
+  4."). On every game of 2025 and of this season through week 4 a rule like it named the quarterback who started about
+  95 times in 100.
+- **We grade our own pick every week.** Once a game is in, About says how often our projected starter was the
+  quarterback who played: "Our projected starter was the game's quarterback in N of M games since week 5."
+
 ## Oct 9 (night) · this week's numbers keep up with the news until each game kicks off
 
 - **A week no longer stands still after Thursday night.** The numbers for a week used to be set at its first kickoff
@@ -24,8 +35,8 @@
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

The way back, if ever: `--vars '{starter_from_data: s4}'` (S4) or `false` (the listing) on the nightly's dbt build;
the record keeps grading both picks either way. No workflow or render line.

## 7. Found, not mine

* **The record's freeze is the last nightly before kickoff**, not the kickoff itself (the nightly runs once a day): a
  Sunday game's row holds Saturday night's pick. A Sunday-morning refresh (the roadmap's third item) would make it
  closer. The record starts with the 28 team-games of week 5 not kicked off when it was first written (17:22 ET).
* `mart_starter_check`'s tallies are the last full build's (the record step runs after it): one night behind; About's
  line reads the table and is current.
* The "Williams ruled Out" sentence names him on the depth chart without saying he is ruled out (the mart's
  `depth_available` reads the report and the roster, not Sleeper's directory); the pick is right.
* Run-to-run drift of weeks 6 – 18 between two chains is still there (hb1.0's weights; IU-2 / IV-1).
* Rounds 1 – 2's findings now closed: Chicago (S7 ships), `test_ros` (reads the live week), Rankings' "Not playing" at
  375 px (fixed), `waivers.py:722` (reads the live week).

## 8. Next

1. The PO's two lines (§ 6), so the record starts tonight; after four graded weeks, `mart_starter_check`'s
   `record_s4_right` against `record_s7_right` (or `ops.starter_record`) decides which rule stays.
2. A Sunday refresh after the inactives would move the record's freeze next to kickoff and settle Chicago-like cases.
3. Chicago's "ruled out" words: let `mart_starter_check`'s `depth_available` read Sleeper's directory the way the rule
   does.
