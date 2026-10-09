# IT-2 — the injury field at its cause, a third source, an audit line that means something (Wave I-T, 2026-10-09)

Branch `dev/IT2` (from `main` `7341acc`), worktree `/home/claude/wt-iq4`, database `league_lab_iq4`.
METRICS § "The week's own injury report, a frozen week, the audit's two lines" (av1.2); WORDS § IT-2.

## 1. Done / not done / cut

* **Item 1 (done).** `mart_player_next_matchup`: `injury_status`, `injury`, `practice_status` are now NULL unless
  `injury_week = next_week`; `injury_week` is kept. The dbt unit test `next_matchup_report_is_the_coming_weeks_only`
  **fails on the old SQL (FAIL 1)** and passes on the new. Readers listed in § 3.
* **Item 2 (done).** The week's own injury report is now the gate's third source, after the stored record, Sleeper
  and ESPN. It comes from `mart_player_week_projections.report_status` for that week, and `availability.statuses`
  and the audit share one merge (`availability_gate.merge`).
  * **Where it sits:** it has a week, not a time, so it is an undated word. It decides only when no dated word speaks
    about him. Any dated word outranks it, even an older reserve-list one: IR from September stays IR rather than
    becoming "Out", otherwise his rest of season would come back. A dated game status from before the week is
    dropped as last week's before the report is consulted.
  * **What is now redundant:** `player.status_note`'s report fallback and its `injury_week = report_for_week` check
    are redundant twice over (the gate now reads the report, and the mart nulls the other weeks). They are kept, plus
    one line so the card keeps its report line with the injury and practice detail. The lineup solve's
    `report_block` call is **not** redundant: it runs in `src/` in the nightly and cannot call the API. It is the
    same rule through the same gate.
* **Item 3 (done: write nothing to a frozen week).** `project` writes nothing to a frozen week.
  * **Why:** `freeze_plan` never rewrites a kept unit. `availability` is part of that frozen record: what was known
    at kickoff, and why a row is 0. Writing Friday's news beside a kickoff row that still carries 12.94 would make
    the record claim knowledge nobody had at kickoff. It would also change, after the fact, which rows a grader who
    reads `availability` treats as decision-zeros.
  * **Who reads Friday's news instead, at read time:**
    * the routes — `availability.statuses`: stored record + Sleeper + ESPN + the week's report;
    * the nightly lineup solve — the stored record + `report_block` of the week's report;
    * the audit — the directory.
  * **What a grader can still read:** `proj_points` and `p10`–`p90` exactly as published, and `availability` exactly
    as known at kickoff.
* **Item 4 (done).** The audit's first rule is now two lines, and still reads the directory, never the stored field:
  * (a) **the alarm, must be 0:** rows a visitor can see, after the routes' own gate;
  * (b) **a note:** stored rows the screens gate, with the names and whether only the live word hides them.
* **Item 5 (done for Rankings).** Questionable's rate by position: QB 45.8 %, RB 63.5 %, WR 70.3 %, TE 69.7 %.
  **No position falls under 25 %.** The ranked row shows "Questionable: about 2 in 3 play · Questionable (ankle) ·
  NFL injury report" in full under the row; the server uses the rate of his position.
* **Not done / cut:**
  * The card's rate words: `player.py` is IT-3's tonight; the words are in the gate block for it.
  * Item 6 entirely (QB start/sit softening, kickers in `lineup.py`, a Trends policy for Doubtful).
  * No re-recording of saved e2e answers was needed.

## 2. Commits

`c80a6e7`, `54b08e1`, `6e04611`, the `test_ip2` update, and this hand-back (last hash in the final message).

## 3. Evidence (`league_lab_iq4`)

**The mart, before → after.** On this copy the calendar's next week is 4 (week 4 is not final in its schedule).
* `mart_player_next_matchup`: 63 players with a report word before, 39 after.
* The 24 who lost an older week's word include Kyler Murray (week 2 Out), Joe Burrow (week 2 Q), Jaylen Warren (3 Q),
  Rome Odunze (1 Q), Chris Olave (2 Q), Jayden Reed and Alec Pierce (3 Out) — full list in METRICS.
* `mart_player_availability`: rows with a word 126 → 78. Of the 48 lost, 24 are free agents, Murray in League of
  Scrubs among them.
* `mart_player_role_alerts` (765 latest rows): `trigger_ended` 86 → 88 (two absence alerts end because the
  teammate's "Out" was last week's); `trigger_injury_now` 48 → 42.

**Readers of the report fields** of `mart_player_next_matchup` / `mart_player_availability`, all right at once now:
* **SQL:** `mart_player_availability`, `mart_player_role_alerts` (`trigger_ended`, `trigger_injury_now`),
  `mart_waiver_moves` / `mart_waiver_upside` (input fingerprints), `assert_waiver_upside_is_legal` ("Out / IR" adds),
  `assert_waiver_moves_are_legal` (comments only since the PO's fix), `mart_league_positional_strength` (reads the mart).
* **Python:** `player.py` (the card and `status_note`), `decisions.py` FA browse, `ondemand.py`, `myweek.py`,
  `research.py`, `src` `anyleague.py`, `reports.py`, `signals.py`, `trades.py`, `waivers.py`, `league_status.py`, and
  the console pages `app/…` (PO).
* **Tests run:** the dbt tests (whole chain below), the root suite, and these API files: ip2, player, parity, il5,
  ip4, i0a, ib0, iq4, research, ia3, ii4, ib3, ie1, ii1, ig1.
* **IS-2's corrections that became redundant** (not removed): `anyleague.py:1913` (was the mart's Out/IR),
  `waivers.py:1140/1181` (`UPSIDE_SQL` / stashes), the `reports.py` `_gated` calls, `decisions.py`'s FA browse
  through `league_gate`, and `player.status_note`'s week check. Each also adds Sleeper's and ESPN's fresher word, so
  they are not purely redundant.

**The audit's two lines, the live four reproduced.** I set the directory rows of Mariota, Hall, Adonai Mitchell and
Pat Bryant to "Doubtful", news Oct 9, as on the live site; their week-5 rows froze at kickoff with numbers. Then I
**restored** the rows.
```
## Players who cannot play or are unlikely to play and are ranked or valued on the screens: 0
- Note — stored rows the screens gate: 4 (week 5 froze at its first kickoff; its numbers are never rewritten): Marcus Mariota (WAS, Doubtful (knee) · Sleeper, Oct 9, this week 5.5, hidden by the live word alone); Breece Hall (NYJ, Doubtful (quadriceps) · Sleeper, Oct 9, this week 10.6, …); Adonai Mitchell (…, 7.2, …); Pat Bryant (…, 4.3, …)
```

**The third source.**
* On a copy with no live feed, a player Out on the week's report is not ranked and appears under "Not playing" as
  "Out · NFL injury report" (`api/tests/test_it2.py`).
* On this copy's week 4, Caleb Williams (Out on week 4's report) now leaves the week-4 QB list. `test_ip2` was updated
  to that rule.
* Week 5 has no report rows on this copy (0 entries; week 4 has 39). So Breece Hall is still RB18 here: this copy's
  only word on him is week 4's "Out", which is stale. On the live site Sleeper's "Doubtful · Oct 7" hides him.

**Face validity (week 5, API code, overlay off):**
* RB: 110 ranked, 23 not playing, led by Mason, Etienne, Achane.
* WR: 170 ranked, 33 not playing. QB: 83 ranked, 4 not playing.
* The tops match IS-1's list on this copy.

**The chain** (`/home/claude/waveIT/chain.sh /home/claude/wt-iq4 league_lab_iq4`, 01:58 → 02:11). **ERROR 0 in
every step:**
```
== 01:58:46 db migrate
schemas and ops tables are in place
== 01:58:48 dbt build (full)
[0m06:04:32  Done. PASS=733 WARN=5 ERROR=0 SKIP=0 NO-OP=0 TOTAL=738
== 02:04:32 project
02:04:43 INFO league_lab.calibration: fi1.0: market week 5; later weeks' lines from the teams' own season (7229 rows, shrink 3.0 games), personnel of the market week (432 rows moved)
02:09:33 INFO league_lab.calibration: hb1.0: market week 5; QB weeks after it blended with the naive line, weight by horizon {2: 0.0, 3: 0.45, 4: 0.25, 5: 0.35, 6: 0.55, 7: 1.0, 8: 0.85} (lambda 0.25, k 6.0); 1039 QB lines moved
02:09:40 INFO league_lab.kdef: kd League of Scrubs (551104): D/ST keys not projected (price 0): def_st_ff, def_st_fum_rec, st_ff, st_fum_rec
02:09:47 INFO league_lab.availability_gate: availability gate: week 6, Sleeper directory (copy of 2026-10-05T12:00:39.609393Z): 77 players who cannot play or are unlikely to play get 0 this week (77 of them out indefinitely: no later weeks)
projected 19584 rows for 2026 (2 league(s), weeks 1-18); wrote 13332 (weeks [6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18]), kept frozen weeks [1, 2, 3, 4, 5]
availability gate, week 6: Sleeper directory copy of 2026-10-05T12:00:39.609393Z; 77 players who cannot play or are unlikely to play get 0 this week, 77 of them
== 02:10:29 projection marts
[0m06:10:44  Done. PASS=145 WARN=0 ERROR=0 SKIP=0 NO-OP=0 TOTAL=145
== 02:10:45 availability guards (as errors)
[0m06:10:53  Done. PASS=2 WARN=0 ERROR=0 SKIP=0 NO-OP=0 TOTAL=2
== 02:10:54 audit
# List audit — 2026, week 5
_Built 2026-10-09 06:10 UTC; every list a visitor can open without a league (Half PPR, PPR, Standard; this week and rest of season; the free calculator's values)._

## Players who cannot play or are unlikely to play and are ranked or valued on the screens: 0
```

## 4. Tests

* **Mine:** `tests/test_it2_gate.py` 4; `api/tests/test_it2.py` 2; the IS-1 / IR-1 files 43 + 20 (one IS-1
  expectation updated on purpose: an RB's Questionable rate is 0.64).
* **Edited modules' and the mart readers' API files:**
  * batch 1: 180 passed / 14 failed — 12 known, plus `test_ib0::…would_not_start[None]` (the same environmental case
    as in IR-1 / IS-1) and `test_ip2::…flagged_quarterback…` (fixed: the third source; 47/47 now);
  * batch 2: 86 passed / 13 failed — 12 known, plus `test_ia3::test_the_pieces_add_up…[1321941740235550720-False]`
    (0.05000000000000071 against a 0.05 floor on Amon-Ra St. Brown's rest-of-season pieces after the chain's refit:
    a rounding edge in IA-3's sum, not the gate).
* **Root:** `check_root.sh` 1,696 passed / 4 failed, 0 new.
* `scripts/gate.sh python` **PASSED** (root 781, api 29, ruff); ruff and the copy standard clean.
* **Web:** `npm run lint` 0 errors; build OK.
* **e2e on port 8929**, every spec that opens Rankings (ip2, iq2, iq4, ir1, ir4, is1, it2): **42 passed, 0 failed**
  on both projects.

## 5. Edits outside my files

* `api/league_lab_api/player.py` `status_note`: one block (`from_report` when the gate's word is the report) — IT-3 owns the file.
* `api/tests/test_ip2.py`: the report-gated quarterback.
* `web/src/routes/Rankings.svelte`: the rate line under the row.
* `web/src/lib/api.ts`: types at the end.
* CHANGELOG, WORDS, METRICS, and `metric_registry.csv` (av1.2).

## 6. The PO's lines

None.

## 7. Found, not mine

* `test_ia3`'s pieces sum has a 0.05 floor that a refit can land exactly on.
* `mart_player_role_alerts` now ends two absence alerts midweek whose teammate's "Out" was last week's. That is right
  by the rule, but the alert may come back on Friday's report (IT-3's reader).
* A partial `dbt build` of `mart_player_availability` drops the views that depend on it (`mart_waiver_upside`,
  `mart_waiver_moves`) until a build that includes them. The nightly's full build always does.

## 8. Next

* The card's "about 2 in 3 play" (IT-3's `player.py`).
* Item 6.
* A report row for the live week on the copies, so the third source can be seen deciding on real data.
