# JB-2 — the clean record on the screen (Wave J-B)

**Start 12:39 ET, Wednesday 2026-10-14 (read from `date`); end 13:07.** Branch `dev/JB2` (from `integ/JB` = Wave J-A,
JB-3, JB-4, JB-1; `7d25c24`), `/home/claude/wt-iq4`, database `league_lab_iq4`. Provider fixtures, news off. **This
database has no week-5 actuals** (the record's week 5 is `in_play` here), so the record screens are built on a fixture
shaped like the live record the PO read on 14 October; the lean's numbers are this database's own (below).

## 1. Done / not done / cut

* **Done — 1. A close call says when Sleeper's numbers lean the other way** (`api/league_lab_api/sleeper_lean.py`, run
  last in `/api/my-week` on both paths; METRICS § sl1.0). A card that is close by the screen's rule (status "close" or
  strength "coin flip") whose other player Sleeper's line has higher (≥ 0.05 points, priced in the league's scoring:
  the `market_points` the lineup rows already carry) gives the call that shows it (an action — also one behind More — or
  a "no clear upgrade" line) one line: "Sleeper's numbers lean to <name>." plus, from **10** graded disagreements, the
  record's season tally (`mart_projection_record`, scope season, ALL: N = `pairs_disagree`, ours = `pairs_ours_right_
  disagree`, Sleeper = `pairs_sleeper_right` − `pairs_both_right`, the count About's record line already says).
  **Only** when the week's snapshot (`mart_market_line`'s, the newest) was fetched before the week's first kickoff; a
  call exists only before its kickoff; an on-demand league has no record, so its lean stands alone; unreadable → no
  line (logged). No number, word or order of the call moves (tested).
* **Done — 2. The record week by week, on About** (the screen that holds the record): the old "Start/sit calls, week by
  week" table became **The record, week by week** — Week · Miss ours · Sleeper · Calls right ours · Sleeper (of n) ·
  Both · neither — labelled "Both numbers frozen before kickoff …", **By position** on tap, the week's lineups in one
  line from `decisions` ("In week 5 our recommended lineups scored 1,251.1; managers' own 1,287.3; Sleeper's numbers
  would have scored 1,323.0." — no verdict word), and **Earlier seasons** (the history's error and close calls by
  position) labelled "Sleeper's past numbers are served after the games …". Nothing until a week is scored (the table is
  drawn from the scored weeks only); "Our record is not available right now." when `/api/record` cannot be read.
* **Done — 3.** WORDS § JB-2, METRICS § sl1.0, tests, e2e at 375 and 1300.
* **Not done**: no screen of the lean from the live API (this database's My Week has no close call at any clock tried
  today: no cards at all on the house leagues); the e2e's answer is IX-4's saved week-5 answer put through the route's
  own steps.

## 2. Commits

`9685dee` / `fed65a6` item 1 · `1c55ceb` item 2 · `65002a8` test_jb2, METRICS, WORDS · `a4e1954` the tally's arithmetic
(About's count), e2e/jb2, screens · the hand-back.

## 3. Evidence

* **The Boston / Jefferson call** (IX-4's saved answer: League of Scrubs team 2, week 5, FLEX2, ours Boston 9.87 against
  Jefferson 9.86 — a coin flip): Sleeper's week-5 snapshot on this database (fetched 5 Oct 12:25 UTC, before the 9 Oct
  00:15 first kickoff) priced in League of Scrubs scoring: Boston **8.91**, Jefferson **13.82** → the call now reads,
  under its reason: "Sleeper's numbers lean to Justin Jefferson. This season, on the 13 close calls where we have
  disagreed, Sleeper was right 8 times, we 4." (the tally from the live record's week 5: 13 disagreements, ours right 4,
  Sleeper 17 right of 26 of which 9 both → 8; one disagreement was level by Sleeper's numbers). The PO's brief said 9;
  About's own line has always said 8 from the same columns — the screens agree.
* **About** (fixture: this database's `/api/record` with week 5 scored from the live numbers): the row "5 · 4.3 · 4.1 ·
  13 · 17 of 26 · 9 · 5"; by position "Week 5 · QB: miss 6.8 ours · 6.4 Sleeper's (30 players)", RB 4.6 · 4.4, TE 3.3 ·
  3.0, WR 4.2 · 4.0; the lineups' line as above; Earlier seasons QB 5.8 · 5.8 · 52% of 3,927, RB 4.4 · 4.2 · 43% of
  11,461, WR 4.1 · 3.9 · 47% of 19,087, TE 3.1 · 3.0 · 46% of 4,562 (this database's `ops.sleeper_h2h`).
* Screens: `docs/handbacks/jb2/jb2-{myweek-lean,about-record}-{375,1300}.jpg`; no sideways scroll at 375 (asserted).

## 4. Tests

* New: `api/tests/test_jb2.py` 9 passed — the tally's threshold (13 → the sentence, 10 → "1 time", 9 → the lean alone),
  only a close call Sleeper reads the other way (agreeing, level, a missing number: nothing), the line on the call with
  **nothing else in the answer moved**, the on-demand path's lean without a tally, a snapshot fetched after the first
  kickoff says nothing (the rule on constructed times, and this database's week-5 snapshot passes it), an unreadable lean
  is no line, the tally's arithmetic as About counts it, both My Week paths ask for the lean.
* The test files of the routes and modules changed (`/api/my-week`, `/api/record`, `myweek`: 45 files): 582 passed, 60
  failed, 16 skipped; the 60 re-run with `7d25c24`'s route (main.py, no `sleeper_lean`): 60 failed — **no new failure**.
* e2e on fixtures, both projects, the 39 spec files that open My Week or About (`jb2` included): **341 passed**, 0
  failed; no existing spec needed an update (the old week table kept its `record-table` id, its rows and ≤ 5 columns).
  Other packages' screenshots the run rewrote: restored.
* ruff, the copy standard, `npm run lint`, `npm run build`: clean. `scripts/gate.sh`: ok (78 s, exit 0).

## 5. Edits outside my files

`api/league_lab_api/main.py` (the my-week route: one call per path), `web/src/routes/MyWeek.svelte` (the line on the
action and review cards), `web/src/routes/About.svelte` (the record's table, the lineups' line, the history table, the
unreadable words), `web/src/lib/api.ts` (the JB-2 block), `docs/METRICS.md`, `docs/WORDS.md`, `CHANGELOG.md`.

## 6. PO lines

`app/whats_new.md` (optional): "A close call now says when Sleeper's numbers lean the other way, and About shows our
record against Sleeper's week by week."

## 7. Found, not mine

* About's decision block says "The best lineups in hindsight beat the ones started by 460.2 points" (V-1's API
  sentence, `record_decisions`): a verdict word on the same screen; not changed here.
* The brief's "Sleeper on 9" for week 5 counts a disagreement where Sleeper had the two level as Sleeper's; the record's
  columns say 8 (About and this line).
* `mart_market_line` keeps only the newest snapshot: once a pull lands after a week's first kickoff, the lean goes quiet
  for the rest of that week (by the rule) — a pre-kickoff snapshot kept apart would let it stay.

## 8. Next

A recorded My Week answer with a live close call from the nightly's week 6 to screen the lean end to end.

## JB-2b — sl1.1: the lean before each pair's own kickoffs (13:08–13:13 ET)

* **Why** (the PO, on § 7's finding): under sl1.0 a pull after Thursday night's kickoff hid every lean until the next
  week — exactly the Friday-to-Sunday window when most calls are made.
* **The rule now** (`sleeper_lean.snapshots` / `pair_ok`; METRICS § sl1.1 with the reason): the lean shows when the
  snapshot pricing the two players was fetched before **both** players' own kickoffs (each player's game that week in
  `dim_game`, by his line's team, one spelling of a team code) and neither game has started at the request. A pair with
  a started game shows nothing (unchanged); the tally sentence is unchanged (the record is pre-first-kickoff by
  construction). WORDS: the "nothing when" clause of the My Week row. The words of the lean do not change.
* **Tests**: `test_jb2` 10 passed — a Thursday-night pair hidden at Saturday's clock while a Sunday pair priced by a
  Friday snapshot shows (sl1.0 hid it); a mixed Thursday / Sunday pair with a Friday snapshot hidden; a snapshot from
  before both kickoffs but a game started at the request: nothing; each player's own game (LAR / LA, a bye); this
  database's week-5 snapshot passes for Boston and Jefferson (their Sunday 11 Oct games). `e2e/jb2` 8 passed (the
  fixture regenerated: its snapshot field now carries the pair's kickoff). ruff, the copy standard, `scripts/gate.sh`
  (79 s, exit 0; web too: the spec's comment and the fixture changed).
