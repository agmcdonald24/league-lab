# IQ-2 — who starts (Wave I-Q, 2026-10-07, branch `dev/IQ2` from `main` `6a76100`, database `league_lab_im4`)

## Task

The brief's package "IQ-2 — who starts": (1) a hand-kept override list that ships tonight regardless; (2) candidate
sources for the market week's starter, measured on identification with the rule written first; (3) "Starters to check"
(`analytics.mart_starter_check`) and a better `starters.unclear` trigger if one measures better; (4) tests.

## What shipped

* **The override list** — seed `dbt/seeds/starter_overrides.csv` (`season, team, from_week, through_week, gsis_id,
  reason, source, added_on`), `int_starter_override` (its state: `in_force`, `expired_in_week`, `on_roster`,
  `led_since_week`, the listing it corrects), applied in `int_pn_team_game` to **unplayed games only**
  (`starter_source` 'override' | 'schedule'; dbt var `starter_overrides`, default true). It expires by itself once the
  team plays a game at or after `from_week` that the named QB does not lead in dropbacks; a QB not on the team's newest
  weekly roster (ACT / INA / DEV) is a dbt **error**; a row in force older than 21 days (by `added_on`) **warns**.
  Rows (PO-checked; each name resolved to exactly one QB of that team in `dim_player` and on the week-4 roster):

  | season | team | from_week | through_week | gsis_id | name | listed (corrected) |
  |---|---|---|---|---|---|---|
  | 2026 | SEA | 5 | (until removed) | `00-0034869` | Sam Darnold | Drew Lock `00-0035704` |
  | 2026 | CHI | 5 | (until removed) | `00-0038416` | Tyson Bagent | Case Keenum `00-0028986` |

* **The screens** — `starters.corrected(season, week)`; Rankings (week and rest-of-season views) and "Who should I
  start?" show the chip **Starter corrected** and one sentence on the corrected QB's row and the listed QB's row:
  "Seattle's listing says Drew Lock; Sam Darnold has led the team's dropbacks since week 3, so we project Darnold as the
  starter. Set by hand on 7 Oct." / "Chicago's listing says Case Keenum; Tyson Bagent led the team's dropbacks in week 4,
  so we project Bagent as the starter. Set by hand on 7 Oct." Tiers and start / sit calls as anyone's; a corrected team
  is never "Starter unclear".
* **`analytics.mart_starter_check`** — one row per team for its next unplayed game: `listed_*`, `depth_*` (newest
  depth-chart snapshot's QB1), `depth_available_*` (the first not Out / Doubtful / on a reserve list), `last_*` (the last
  game's dropback leader), `*_report` / `*_roster` for each, `report_published`, `override_*` (+ `override_added_on`,
  `override_led_since_week`, `override_reason`), `projected_qb_id` / `projected_name` / `starter_source`, `agree` (listing
  = depth QB1 = last leader), `listing_disputed` (U1). 32 rows, 16 kB.
* **`starters.unclear` reads U1** (the listing is not the depth chart's first available QB) wherever the mart is built,
  minus corrected teams; without the mart (a deploy before the nightly) it is su1.0 exactly as before.
* **No starter source ships** (none passes the rule; table below).

## Evidence

**The rule** (METRICS § "Who starts", written 19:36 ET, committed `3c19084` before any candidate number was read; the
study ran 19:55 ET). Before the rule I had looked only at data coverage (depth charts exist for 2025–2026 only) and at
today's depth chart for CHI / SEA / WAS.

**The as-of**: all 670 played team-games of 2025 – 2026 wk 4 have a depth-chart snapshot before kickoff (median 10.8 h
before, max 18.7 h: daily captures); QB1 before vs the first snapshot after a game differs in 2 of 670 (a chart rebuilt
after the fact would always name the game's QB). Injury report: `date_modified` before kickoff for ≥ 99.9% of Out /
Doubtful rows 2021–2024 (2025–26 carry no stamp). INA (game-day inactive) is never read. **The historical listing is
nflverse's post-game value** (one schedule snapshot), so the base is better in history than live: the bias favours
the listing.

**Identification** (`scripts/analysis/iq2_starter_source.py study`; truth = the dropback leader; stale = listed QB took
no dropback):

| Window | Candidate | Accuracy listing → cand. | On stale listings | Fixed | Newly broken | (a) acc | (b) ≥60% | (c) ≤1/6 | Board ΔMAE |
|---|---|---|---|---|---|---|---|---|---|
| 2025–26 wk 4 (670) | S1 depth QB1 | 0.951 → 0.891 | 6/12 (50%) | 7 | 47 | fail | fail | fail | not run |
| 2025–26 wk 4 | S2 depth, first available | 0.951 → 0.949 | 12/12 (100%) | 13 | 14 | fail | pass | fail | not run |
| 2025–26 wk 4 | S3 listing unless ruled out | 0.951 → 0.958 | 5/12 (42%) | 5 | 0 | pass | fail | pass | not run |
| 2025–26 wk 4 | S4 two sources agree (own) | 0.951 → 0.957 | 10/12 (83%) | 10 | 6 | pass | pass | **fail** | not run |
| 2021–26 wk 4 (2,844) | S3 listing unless ruled out | 0.955 → 0.958 | 10/49 (20%) | 10 | 0 | pass | fail | pass | not run |

The board (d) is run only for a candidate passing (a)–(c): none did, so it was not run. S2's breaks: a hurt starter the
chart kept on top who was Questionable and then inactive on game day (Murray ARI 2025 wks 6/7/9, McCarthy MIN 7–8,
Purdy SF 3/9) and week-18 rests (BUF, GB, LAC, PHI). S4's six: ARI 2025 wk 6, ATL wk 8, BUF / LAC / PHI wk 18, PIT
wk 12. Only 12 stale listings exist in the depth-chart window (2024's 33 have no chart).

**The unclear trigger** (2025–26 wk 4, 12 stale listings): U0 su1.0 42 flags / 7 caught / 35 not stale; **U1 27 / 12 /
15**; U2 (either) 57 / 12 / 45; U3 (both) 12 / 7 / 5. U1 catches more with fewer flags → by the rule it replaces U0.
(U0 on 2022–26 wk 4 reproduces su1.0 exactly: 169 flags, 32 of 49.)

**2026 week 5 on this database**: su1.0 flagged CHI, SEA, WAS. Now: CHI and SEA corrected (not flagged); U1 flags
**Tampa Bay** only (listed Jalon Daniels, who led week 4; the depth chart puts Baker Mayfield first, INA in week 4; no
week-5 report yet); WAS is no longer flagged (listed Jayden Daniels = depth chart QB1; Kaliakmanis led week 4). The
mart's `agree = false`: CHI, SEA (corrected), TB, WAS, and the bye teams CAR / KC (week 6 not listed yet).

**Before / after** (`project` twice on `league_lab_im4`, v3.5 both — list off, then on; reference league (League of
Scrubs) scoring; weeks 1–4 frozen and untouched: "kept frozen weeks [1, 2, 3, 4]" both runs): 76 of 7,917 rows moved,
six players, all SEA / CHI quarterbacks.

| Player | Week 5 | Weeks 6–18 (12 games) | QB rank wk 5 | QB rank wks 5–18 |
|---|---|---|---|---|
| Sam Darnold | 4.2 → **15.0** | 52.5 → **177.9** | #41 → #25 | #42 → #25 |
| Drew Lock | 14.1 → 4.3 | 154.9 → 47.8 | #28 → #41 | #32 → #43 |
| Tyson Bagent | 3.0 → **15.3** | 32.9 → **159.0** | #67 → #24 | #75 → #32 |
| Case Keenum | 16.2 → 5.2 | 190.3 → 59.2 | #15 → #37 | #19 → #38 |
| Caleb Williams | 7.4 → 8.1 | 93.7 → 101.2 | #32 → #31 | #34 → #33 |
| Smith-Njigba, Wilson, Price, Barner (SEA); Swift, Monangai, Burden, Odunze (CHI) | unchanged (e.g. JSN 14.7) | unchanged (JSN 176.9) | | |

The receivers do not move: their `pn_qb_*` inputs change (JSN wk 5 `pn_qb_changed` 1, `pn_qb_prev_ppg_diff` −0.96), but
the RB / WR / TE models do not read QB inputs (`projections.FEATURES_BY_POSITION`). Half PPR via the API after: Darnold
15.0 wk 5, rest of season 178 (weeks 6–18) on Compare; Rankings week 5 Bagent #24 (15.27, tier 5), Darnold #25 (15.03,
tier 5), Keenum #37, Lock #41.

**Face validity**: QB top 24 by week 5, rank correlation with the later weeks' mean 0.60 → 0.64 (RB / WR / TE 0.94 /
0.95 / 0.85 unchanged); with 2026 points per game (2+ games) 0.11 → 0.22 (still weak: IQ-3's subject). Darnold 15.0
against 29.7 and 14.3 in his two starts; Bagent 15.3 against 9.8 in his one game as the leader.

**dbt** (`league_lab_im4`): the chain + seed + override + mart build PASS 55 (2 unit tests, 3 new data tests, the
edited `assert_personnel_is_asof` and `assert_starter_from_play`); the nightly's projection-marts selection PASS 145 + the
registry re-run PASS 3; the guard, the pricing and both freeze tests PASS 4.

**Tests**: `api/tests/test_iq2.py` 8 passed (incl. the database at week 5 and the routes at week 5, and without the
mart); `api/tests/test_ip1_starters.py` 5 passed; `api/tests/test_ip2.py` 47 passed; root
`tests/test_iq2_starter_source.py` 4 passed (+ `tests/test_ip1_starter.py` 3 passed); ruff clean; copy standard clean;
`npm run lint` 0 errors / 0 warnings; `npm run build` ok; e2e `web/e2e/iq2` 4 passed (phone 375, desktop 1300; recorded
live from the fixture API at week 5, replayed), `web/e2e/ip2` 8 passed. No `src/` edit, so `check_root.sh` not run.
Existing tests changed on purpose: `test_ip2.py::test_search_and_paging` (the rankings cache key has one more element:
the corrected QBs), `test_ip1_starters.py` (the su1.0 tests pin su1.0 with a fixture; the cache test counts the mart's
read).

## Files

New: `dbt/seeds/starter_overrides.csv`, `dbt/models/intermediate/features/int_starter_override.sql` + `.yml` (seed and
model docs, 2 unit tests), `dbt/models/marts/nfl/mart_starter_check.sql`, `dbt/tests/assert_starter_override_on_roster.sql`,
`assert_starter_override_is_fresh.sql`, `assert_starter_override_unplayed_only.sql`, `scripts/analysis/iq2_starter_source.py`,
`api/tests/test_iq2.py`, `tests/test_iq2_starter_source.py`, `web/e2e/iq2/fixtures.spec.ts`, `web/fixtures/iq2/api_iq2.json`
(62 kB), `docs/handbacks/iq2/*.jpg` (4), this file.
Edited (mine): `dbt/models/intermediate/features/int_pn_team_game.sql`, `api/league_lab_api/starters.py`,
`dbt/tests/assert_starter_from_play.sql`, `dbt/tests/assert_personnel_is_asof.sql` (override-aware, marked),
`api/tests/test_ip1_starters.py`.
**Edits outside my files** (marked blocks / smallest edits): `dbt/dbt_project.yml` (the seed's column types),
`dbt/models/intermediate/features/int_player_week_personnel.yml` (`starter_source` doc + accepted values),
`api/league_lab_api/rankings_api.py` (the starter part: `_starters_corrected`, the cache key, the row / start field,
`UNCLEAR_TIER`'s words), `web/src/routes/Rankings.svelte` and `web/src/components/rankings/StartAnswer.svelte` (the
chip and sentence), `web/src/lib/api.ts` (types at the end; `StarterUnclear.role` gains "depth"), `api/tests/test_ip2.py`
(cache key length), `docs/METRICS.md`, `docs/WORDS.md`, `CHANGELOG.md` (new heading `## 2026-10-08 — Wave I-Q`),
`dbt/seeds/metric_registry.csv` (3 rows: `starter_override` so1.0, `starter_source_study` 1.0,
`starter_unclear_depth_chart` su1.1 — a CSV cannot carry a marker).

## Schema in / out

In: `raw.nfl_schedules` (via `dim_game`), `fct_player_game.dropbacks`, `fct_team_game`, `stg_nflverse__rosters_weekly`,
`stg_nflverse__injuries`, `int_depth_chart_current`, `stg_nflverse__depth_charts` (study only), `dim_player`.
Out: `analytics_seeds.starter_overrides`, `intermediate.int_starter_override`, `intermediate.int_pn_team_game.starter_source`
(new column), `analytics.mart_starter_check`; API rows `starter_corrected` {team, listed, set, role, words} on
`/api/rankings` (both views, QB) and `/api/rankings/start` players. No state table, nothing `db migrate` must create.

## Commands

`uv run league-lab dbt build --select starter_overrides int_starter_override int_pn_team_game`;
`uv run league-lab dbt run --select "int_pn_team_game+,+mart_player_week_features" --vars '{starter_overrides: false}'`
+ `uv run league-lab project` (before); `uv run league-lab dbt build --select "int_pn_team_game+,+mart_player_week_features"
starter_overrides int_starter_override mart_starter_check` + `project` (after); the nightly's projection-marts
selection; `uv run python scripts/analysis/iq2_starter_source.py asof|study`; the tests above.

## Limitations

* No source fixes the listing automatically; the list is by hand and the weekly check is the PO's.
* The study's depth-chart window is 2025 – 2026 wk 4 (12 stale listings); older charts are not in the database.
* An override row stays in force for the week after a returning starter's comeback until that game is played (it
  expires on evidence) — e.g. if Caleb Williams returns in week 6, CHI keeps Bagent for week 6 unless the row is given a
  `through_week` or removed. The mart shows the disagreement (`depth_available` vs `projected`); the screens do not.
* History is not corrected (by design): Seattle's weeks 3–4 still list Lock as the starter, so Darnold's and his
  receivers' `pn_qb_changed` read 1 and Darnold's start count misses two starts.
* The receivers' projections do not read the quarterback at all (RB / WR / TE models have no QB input).
* If a nightly built `int_pn_team_game` but failed before `mart_starter_check`, the screens would fall back to su1.0 and
  could call a corrected team "unclear" while the numbers use the override (both are in the same `dbt build`).
* U1 still flags mostly non-stale listings (15 of 27): the words stay "unclear".

## For the PO

* `scripts/nightly.sh`: **no line**. The full `dbt build` builds the seed, `int_starter_override`, the new column, the
  mart and runs the new tests; `project` reads the corrected starters. The hosted sync picks up
  `analytics.mart_starter_check` from `starters.py` by itself (`scripts/hosted_relations.py` lists it; 16 kB).
* **Decide**: `assert_starter_override_on_roster` is `error` as the brief says — a typo'd or departed QB stops the
  nightly's hard `dbt-build` step (the children are skipped). Acceptable, or warn + skip the row?
* **Decide**: CHI's row has no `through_week`; set `through_week: 5` if you prefer to re-confirm Bagent each week.
* **Decide**: S3 (listing unless the report / reserve list rules him out) never broke a listing (0 in 2,844 team-games,
  10 fixed) but fails (b); it is not shipped. It could ship as a no-regret rule under a looser rule, your call.
* The weekly check (Tuesday): `select team, week, listed_name, depth_name, depth_available_name, last_name,
  listed_report, override_name, projected_name, agree, listing_disputed from analytics.mart_starter_check where not agree
  order by team;` — add a row to the seed for a stale listing (with `added_on`), re-date a row to re-confirm it, delete
  a row to end it (the kill switch for all: `--vars '{starter_overrides: false}'`, or empty the CSV).
* STATUS / What's new line (suggested): "Seattle and Chicago now have the right starting quarterback: we set Sam Darnold
  and Tyson Bagent by hand while the data source still lists Drew Lock and Case Keenum, and the rankings say so."
* `docs/DEPLOY.md` § Memory: the `starters` region now holds two entries per week (flags and corrections), still ≤ 32.

## What the first nightly does differently

`dbt build` seeds `starter_overrides`, builds `int_starter_override` and `mart_starter_check` (seconds), rebuilds
`int_pn_team_game` with `starter_source`, runs 2 more unit tests and 3 more data tests (+ 6 generic). `project`
then projects Darnold and Bagent as their teams' starters for weeks 5–18 (≈ 76 rows per league move: the six SEA / CHI
quarterbacks; no other player; frozen weeks untouched), and the projection marts, the decision record for week 5 and
the hosted copy carry it. On the site: the two QBs' rows say "Starter corrected"; "Starter unclear" switches from su1.0
(CHI, SEA, WAS this week) to U1 (TB this week).

## Next task

A weekly habit, not code: the Tuesday check above. Code: carry a corrected starter into the *history* inputs only when
the play data confirms it (st1.0 measured that and failed on returning starters — a narrower version, for teams with an
override in force, is the next thing to try); and, for IQ-3, give the receivers a QB input (their models have none).
