# IQ-4 hand-back — the trust guard (Wave I-Q, 2026-10-07, 21:17–22:35 ET)

Branch `dev/IQ4` (from `main` `6a76100`), worktree `/home/claude/wt-iq4`, database `league_lab_iq4` (its only writer).

## Task

The PO's IQ-4 brief: (0) the bye-week bug first; (1) `league-lab audit-lists` with today's report; (2) grade kickers
and defenses 2–8 weeks ahead and recommend; (3) one sentence of what we know on the three rest-of-season screens;
(4) the site's usage counter.

## 0. The bye-week bug — fixed at its cause, every path tested

**The cause.** Not the API: every reader (`/api/ros`, `anyleague.ros_table`, Rankings' season view,
`refleague.value_of`, the card, the trade engine's market) sums the stored weeks correctly and skips a bye. The rows
were missing. nflverse's weekly roster file lists **only the teams that play that week**; three dbt models read "the
newest roster week on or before W" **across all teams**:

* `dbt/models/intermediate/int_player_week_universe.sql` (the projection universe: every player-week `project` projects),
* `dbt/models/marts/nfl/mart_kd_week.sql` (the kickers),
* `dbt/models/intermediate/features/int_pn_player_week_status.sql` (the personnel inputs' roster status).

Once week 5's file was out (30 teams: no KC, no CAR — checked on the real file from nflverse's GitHub release), every
Chiefs and Panthers player had no universe row for weeks 6–18, so `project` wrote no projection for them, and every
list, value and price built from the stored weeks lost them. **The fix**: a team missing from the newest file reads its
own newest file for the weeks after it (`team_fallback`), unless the player is on a newer file elsewhere (a move during
the bye). Only weeks past the newest file can change; a played week always has its own file for every team that plays,
so history and every training row are unchanged (checked: 0 of 109,409 universe rows read an older file in a played
week; 0 played team-weeks 2016–2026 without a file).

**How the case was made real**: `league-lab ingest nfl --seasons 2026 --datasets rosters_weekly` loaded nflverse's real
2026 file into `league_lab_iq4` (GitHub; 13,028 rows, week 5 = 30 teams). Then the whole chain twice, old models then
new (`dbt run` of the 15 feature models → `league-lab project` → the nightly's projection-marts selection), API on my
database with `LEAGUE_LAB_NOW=2026-10-07T23:30:00Z` (week 5, before Thursday's kickoff):

| | before (main's models) | after (IQ-4) |
|---|---|---|
| universe rows of KC + CAR, each of weeks 6–18 | 0 | 41 |
| kickers in `mart_kd_week`, week 6 (teams) | 26 | 28 (all 28 that play) |
| `project` rows | 20,390 | 21,482 |
| `/api/ros?league=ref:half&position=QB` | **87 QBs from 30 teams**, no KC / CAR | 93 from 32 |
| `/api/ros?league=1389709692405551104&position=QB` | **87 from 30** | 93 from 32 |
| free calculator, Mahomes | `no_projection: true`, value null | value 58.6, QB2 |
| `api/tests/test_iq4.py` (bye paths) | **8 of 8 fail** | 8 of 8 pass |
| projection-marts dbt selection (incl. the guard) | PASS 148 | PASS 148 |

The before reproduces the PO's 19:30 report exactly (87 quarterbacks from 30 teams). The five players after (Half PPR
reference key / League of Scrubs; before: absent from every list, "no rest-of-season projection" in the calculator):

| | rest of season (pos. rank, points) | Rankings season rank | free calculator value (Half PPR) |
|---|---|---|---|
| Patrick Mahomes (KC) | QB2, 236.3 / QB2, 216.5 | 2 / 2, "Bye this week" | 58.6 (QB2) |
| Travis Kelce (KC) | TE6, 103.8 / TE6, 95.4 | 6 / 6 | 31.0 (TE6) |
| Kenneth Walker III (KC) | RB9, 184.8 / RB9, 169.5 | 9 / 9 | 122.2 (RB9) |
| Chuba Hubbard (CAR) | RB10, 164.0 / RB10, 150.6 | 10 / 10 | 99.2 (RB10) |
| Tetairoa McMillan (CAR) | WR11, 149.2 / WR11, 136.8 | 11 / 11 | 74.7 (WR11) |

(Mahomes' 236.3 is weeks 6–17 of `ref:half`'s window, 12 games; the calculator runs to week 18, 13 games: 256.1.)

**Which screens were wrong for bye teams, and since when.** Every screen that reads a stored week after this one:
Rankings "Rest of season", `/ros` (all four views), the free trade calculator, the player card's `ros` / `ref_value`,
and with a league: Trades (the market price: no rows → no price), the partner search and Team's season outlook (KC / CAR
players worth nothing in weeks 6–8 of the horizon), Waivers' rest of season, the League page's roster values. My Week's
own week was right (a bye is a bye). Since the first nightly that loaded week 5's roster file (it was not in IQ-1's copy
nor in `league_lab`, both loaded Mon 5 Oct — which is why they were whole); weeks 1–4 have no byes, so never before
this week. **It would recur every bye week** (week 6 has 4 teams on a bye, and so on to week 14): each time the
bye teams vanish from every later week until their next file. Kickers of bye teams too (`mart_kd_week`); defenses are
built from the schedule and were never affected.

**Tests**: dbt unit tests `dbt/models/intermediate/iq4_bye_week.yml` (the universe and the personnel status on a
four-team fixture with a bye and a player who moves during it; both FAIL on main's SQL, PASS now);
`api/tests/test_iq4.py` (clock pinned in week 5 of the real schedule: `/api/ros` reference and house, the coverage rule
"every team with a game in the window has a QB in the list", Rankings' season view (rank, `bye_this_week`, no game),
the free calculator, the card (reference and house), the trade market SQL). On `league_lab` (no week-5 file) these
pass too: they guard the readers; the dbt tests guard the cause. Rankings' season rows carry `bye_this_week` and the
row says **"Bye this week"** (was "no game this week").

## 1. `league-lab audit-lists` — today's report

`src/league_lab/audit.py` + the command at the end of `cli.py`. Reads every list a visitor opens without a league
(Half PPR, PPR, Standard × this week / rest of season / the free calculator's values × QB RB WR TE K DEF = 54 lists)
the way the site builds them (`anyleague.price_week`, `anyleague.ros_table`, the reference scorings, the typical
league's slots and `ros_window`); read only; **exit 0 always**; markdown on stdout and in `logs/list_audit.md`
(logs/ is git-ignored). Rules (constants at the top): coverage first; a top-12 (QB TE K DEF) / top-24 (RB WR)
projection whose points per game (3+ games, this scoring) rank beyond twice that cut; a top-5 scorer outside the top
15 / 30 unless Out / reserve / a bye explains it (the row says so); Out / Doubtful / reserve above 3.0 this week; a
team with no QB above 10 or two; the projected starter vs the newest game's dropbacks both ways (IQ-2's
`analytics.mart_starter_check` printed when it exists — it does not here, the section says so); the guard's top-24
agreement per position and scoring (floors QB 0.55, RB / WR / TE 0.65); rank moves > 10 places since the previous run
with no game and no status change — **yesterday's board is not kept in the database** (no state table added): the run
saves its ranks in `logs/list_audit_ranks.json` and compares when the previous run's file is there (on Actions' fresh
runner it never is). 11 unit tests on hand-built boards (`tests/test_iq4_audit.py`). ~4 s on my database.

Today's report (`league_lab_iq4`, built 02:17 UTC = 22:17 ET, week 5, after the fix; full text in `logs/list_audit.md`,
95 lines — the K / DEF and calculator sections repeat the rest-of-season ones):

```
## Coverage — every team in every list
- Every team with a game in a list's window has players in it (all 54 lists).
## Projected against what they have scored (3+ games this season)   [flags in all three scorings unless named]
QB this week: Kyler Murray (MIN) #9 here, #30 in points per game (7.8 in 3 games); Tyler Shough (NO) #3 in points
  per game (24.1 in 3) but #20 here; explained: Bryce Young (a bye this week)
RB this week: explained: Kenneth Walker III (a bye this week)
WR: George Pickens (DAL) #11 this week / #19 rest of season, #50 in points per game (5.6 in 4) [Standard]
TE: Mike Gesicki (CIN) #4 in points per game (13.0) but #24 / #26; Juwan Johnson (NO) #2 (13.6) but #20 / #18;
  AJ Barner (SEA) #11 this week, #27 in ppg [Standard]; Cade Otton (TB) #12 rest of season, #28 [Standard];
  explained: Travis Kelce (a bye this week)
QB rest of season (and the calculator's values): Kyler Murray (MIN) #4 here, #30 in points per game (7.8 in 3);
  Tyler Shough (NO) #3 in points per game (24.1) but #22
K this week: Dicker (LAC) #2 (ppg #28), Mevis (LA) #7 (#26), Lutz (DEN) #9 (#30), Borregales (NE) #11 (#29);
  Shrader (IND) ppg #1 but #22, Gay (LV) #4 but #24, McLaughlin (TB) #5 but #21
K rest of season: Dicker #1 (ppg #28); McPherson (CIN) ppg #3 but #27; Shrader ppg #1 but #23
DEF this week: WAS #3 (ppg #25), DAL #4 (#30); LV ppg #2 but #23
DEF rest of season: WAS #2 (#25), ATL #11 (#26), PHI #12 (#29); CIN ppg #5 but #19; LV ppg #2 but #32
## Status this week
- 0 players carry an injury-report status (the week's report is not out yet); 91 are on a reserve list.
- No player ruled out or on a reserve list is projected above a backup.
- Every team playing this week has exactly one quarterback above 10.
## Who starts   (mart_starter_check not on this database: our own check)
- CHI: projected starter Case Keenum (16.2) took no dropback in week 4; Tyson Bagent led them (36)
- SEA: projected starter Drew Lock (14.1) took no dropback in week 4; Sam Darnold led them (26)
- WAS: projected starter Jayden Daniels (18.0) took no dropback in week 4; Athan Kaliakmanis led them (36)
## This week against the later weeks (top 24, rank correlation)
| list | QB | RB | WR | TE | K | DEF |
| Half PPR | 0.58 | 0.94 | 0.95 | 0.85 | 0.30 | 0.33 |
| PPR | 0.58 | 0.96 | 0.97 | 0.91 | 0.30 | 0.33 |
| Standard | 0.58 | 0.93 | 0.91 | 0.76 | 0.30 | 0.33 |
## Rest-of-season rank moves: yesterday's board is not kept anywhere: nothing to compare (ranks saved for the next run)
## Counts: coverage 0, against_scored 43, out_projected 0, qbs_per_team 0, starter_vs_last_game 3, agreement_below_floor 0
```

Reading it: SEA and CHI are IQ-2's two (the override list fixes them); **WAS / Daniels** is the third team to check (he
missed week 4; the listing has him back for week 5 — right if he plays). Murray and Shough are the QB model's weak read
of the individual quarterback (IQ-3's subject). K / DEF flags are what item 2's grade predicts. Before the fix the
first line would have read "missing CAR, KC" for every rest-of-season and value list (the rule's unit test).

## 2. Kickers and defenses 2–8 weeks ahead (METRICS § "Kickers and defenses beyond next week")

Keep rule committed `db1b640` (21:50 ET) before the study ran (`scripts/analysis/iq4_kd_horizon.py`; 2021–2025, one
kd1.0 fit per season, as of W = 3/5/7/9, rows rebuilt as the nightly builds a future week: no line from h = 2, as-of
inputs frozen after W; naive = this season's points per game through W; League of Scrubs, the one house league that
starts K / DEF; 20 cells a horizon). Pooled 2–8: **K Spearman 0.028 (model) / 0.016 (naive), MAE 3.75 / 4.14; DEF
0.040 / 0.033, MAE 4.78 / 5.30** (one week out: K 0.095, DEF 0.257). Model Spearman higher in 3 of 5 seasons, MAE lower
in 5 of 5 → neither "keep" nor "replace" passes → "no different", and the better Spearman is far below the 0.15 floor →
**recommendation: take the K / DEF "Rest of season" list off the public screen.** Context that decides nothing: each
unit's points per game over W+2…W+8 ranked: K 0.023 / 0.087, DEF −0.019 / 0.158. **Built behind a switch**:
`LEAGUE_LAB_KD_ROS` (unset / `off` = Rankings' season view of K and DEF shows the sentence and no rows; `on` = as
before). `/ros` and the free calculator keep K / DEF numbers with the caveat (league tools and trade values need a
number). kd1.0 itself unchanged; the week view untouched.

## 3. The sentence on the three screens

`api/league_lab_api/ros_grade.py` — the one place (constants with the METRICS reference and the date), read by
Rankings' season view, `/api/ros` and the free calculator (`ros_grade` in each answer):

> Beyond next week there is no betting line yet. Graded on 2021–2025, a quarterback projection two to eight weeks ahead
> misses by about 7.6 points per game (6.4 for next week); running backs, receivers and tight ends miss by about 0.2
> more than next week.

K / DEF: Rankings: "Kickers and defenses: graded on 2021–2025, their order two to eight weeks ahead is no better than
chance, so they have no rest-of-season ranking here." `/ros` and the calculator: "… no better than chance; read their
numbers as a rough guide." WORDS.md § "What we know about the rest of the season". e2e `web/e2e/iq4/fixtures.spec.ts`
(recorded from my API on the real bye week; phone 375 and desktop 1300, no sideways scroll; 8 of 8), screenshots in
`docs/handbacks/iq4/`.

## 4. The site's own counter (`usage.py`)

* **The failed writes, found**: a view while browsing sends `league: "ref:half"`; `platforms.check_key` accepts a
  reference key, so the row went in with `league_key = 'ref:half'`, `platform = 'reference'` — and `usage.events`'
  checks (`events_league_key_id`, `events_platform_name`) refuse both: a `CheckViolation`, swallowed and counted as
  `failed`. Every rest-of-season, calculator, Rankings, Players… view without a league was lost (30 of 323 on 7 Oct is
  the share of views made with a reference key; not proven on the live table — I cannot reach it — but reproduced
  here: before the fix the insert fails, after it is counted). A reference key is now counted as a view with no league.
* `rankings` and `write` (the editor) added to `SCREENS` (the existing test that every router name is a screen was
  failing on main for exactly this).
* A connection error (`OperationalError`, `InterfaceError`) is tried once more after 0.5 s on the writer thread (never a
  request's time; `db.write_one` already re-connects once at once); `process` gains `retried` and `failed_kinds`
  (by exception class, at most 20 names).
* `/api/usage/summary` gains `depth`: per day, sessions with 1, 2–3 and 4+ screen views.
* Tests: `api/tests/test_iq4_usage.py` (7). Two lines of `test_u1.py` updated on purpose: they were stale since IK-3
  widened the table's checks (`'espn'` is a platform now; IK-3's `drop constraint if exists` tripped "no 'drop '") —
  both failed on main against a table with IK-3's checks.

## Files

* dbt: `int_player_week_universe.sql`, `mart_kd_week.sql`, `features/int_pn_player_week_status.sql` (IQ-4 blocks),
  new `dbt/models/intermediate/iq4_bye_week.yml` (2 unit tests).
* src: new `audit.py`; `cli.py` (`audit-lists`, IQ-4 block at the end).
* api: new `ros_grade.py`; `rankings_api.py` (season view: `ros_grade`, the K / DEF switch, `bye_this_week`; IQ-4 blocks;
  nothing in the starter part), `ondemand.py` (`ros_grade` on `/api/ros`), `freetrade.py` (`ros_grade`), `usage.py`.
* web: `routes/Rankings.svelte` (season words, "Bye this week"), `routes/Ros.svelte`, `components/scoring/FreeTrade.svelte`,
  `lib/api.ts` (types at the end).
* tests: `api/tests/test_iq4.py` (11), `api/tests/test_iq4_usage.py` (7), `tests/test_iq4_audit.py` (11),
  `api/tests/test_u1.py` (2 lines), `web/e2e/iq4/fixtures.spec.ts` + `web/fixtures/iq4/api_iq4.json` (76 KB).
* scripts: `scripts/analysis/iq4_kd_horizon.py`. docs: METRICS § IQ-4 (keep rule, result, the sentence, the bug),
  WORDS § IQ-4, this file, `docs/handbacks/iq4/*.jpg` (8), CHANGELOG.
* Edits outside my files (smallest, marked): the three dbt models (no owner named; IQ-2 owns `int_pn_team_game.sql`,
  untouched), `ondemand.py` (two keys + one helper), `test_u1.py`.

## Schema in / out

No new relation, column or state table; nothing for `db migrate`. The API answers on a database without anything new
(`ros_grade` is constants; `mart_starter_check` is read only when it exists). Answers gain: `/api/rankings` (season)
`ros_grade`, `kd_hidden`, rows' `bye_this_week`; `/api/ros` and `/api/trade-calc/free` `ros_grade`;
`/api/usage/summary` `depth`, `process.retried`, `process.failed_kinds`.

## Commands

```
uv run league-lab ingest nfl --seasons 2026 --datasets rosters_weekly         # the real week-5 file (GitHub)
uv run league-lab dbt run --select <the 15 feature models>; uv run league-lab project
uv run league-lab dbt build --select <the nightly's projection-marts selection> mart_player_availability
uv run league-lab dbt test --select "int_player_week_universe,test_type:unit" "int_pn_player_week_status,test_type:unit"
uv run league-lab audit-lists
uv run python scripts/analysis/iq4_kd_horizon.py --out <csv>
```

## Evidence — tests

* Mine: `api/tests/test_iq4.py` 11 passed; `api/tests/test_iq4_usage.py` 7 passed; `tests/test_iq4_audit.py` 11 passed;
  dbt unit tests 2 PASS (FAIL on main's SQL); dbt tests of the 3 models PASS 15; projection marts PASS 148, WARN 0.
* Edited modules' files: `test_ip2.py test_in2.py test_f3.py` 106 passed, 6 failed (all in `known_api_failures.txt`);
  `test_i0a test_i0b test_ia3 test_ib3 test_ic2 test_ic4 test_ie0 test_ii4 test_il4` 109 passed, 5 failed (all known);
  `test_u1.py test_im3.py` + mine 90 passed.
* ruff clean; copy standard clean; `npm run lint` 0 errors / 0 warnings; `npm run build` ok; e2e iq4 8 passed;
  `check_root.sh`: 4 failed (all in `known_root_failures.txt`), 1,606 passed, 3 skipped — no new failure.

## Limitations

* The live usage table was not read: the cause of the failed writes is found in the code and reproduced here, the
  count (30 of 323) is consistent with it but not proven against the live rows.
* K / DEF: one house league starts them (20 cells a horizon); the study scores units that played and kickers known by
  W+1 (a slight look-ahead on who kicks, as IQ-1's d).
* The audit's rank-move rule has no yesterday on a fresh runner (nothing stored in the database by design).
* `league_lab_iq4` now carries the real week-5 roster file and a fresh `project` (my database; nobody else's touched).

## For the PO

* **Deploy and nightly**: the bug is in rows the nightly builds. After the merge, the next nightly's `dbt build` +
  `project` + projection marts restore the bye teams (no new step). Until then the live lists keep missing KC / CAR
  (and, once week 6's file is out, week 6's four bye teams). Worth a manual run (or an early nightly) tonight.
* `scripts/nightly.sh` — the soft step, after the projection marts (and after IQ-2's starter mart if it lands):
  ```
  # ---- IQ-4 (Wave I-Q): the trust guard — every public list audited; never a stop (exit 0 always)
  SOFT_WHY="the lists go out unaudited tonight" soft audit-lists uv run league-lab audit-lists
  # ---- end IQ-4
  ```
  and in the run's summary the report's head and counts, e.g. `sed -n '/^## Coverage/,/^$/p;/^## Counts/,$p'
  logs/list_audit.md`.
* Decide `LEAGUE_LAB_KD_ROS` (render.yaml): unset = K / DEF rest-of-season list off Rankings (the grade's
  recommendation); `on` = as before.
* STATUS: the bug, its cause and dates as above; WAS / Daniels on the weekly check list beside SEA and CHI.

## Next task

The audit's flags as a weekly check list (with IQ-2's mart); a bye-week test on the nightly's own fresh database
(load a bye week's file, project, assert the coverage rule); the rest-of-season ranges (still ungraded; no tiers).
