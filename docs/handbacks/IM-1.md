# IM-1 hand-back — the Stats tables' data: more metrics, every one honest (Wave I-M, 2026-10-05/06)

**Task**: Wave I-M package IM-1 (`/home/claude/waveIM/BRIEF.md` § IM-1). **Branch**: `dev/IM1` from `main` `ab50682`
(commits `IM-1: …`; the last one is named in the PO message). **Database**: `league_lab_im1` (the only writer; 2026 through
week 4). Plan sections: docs/METRICS.md § "The Stats Explorer" → new § "More columns, every one honest (adv1.0)";
docs/DATA_INVENTORY.md; docs/WORDS.md § "The Stats tables' columns (Wave I-M, IM-1)".

## Done / not done (the package's numbered list)

1. **The two empty columns — done, no bug.** On the clone `analytics.mart_player_ngs_week` is built (26,381 rows; 2026:
   NGS weeks 1–4). The WR / TE preset's `separation` and `yac_over_expected` fill: **40 of the top 40 receivers by
   targets have both** (the 40th has 23 targets). Of every WR / TE with a game: WR 96 / 184, TE 37 / 107 have a value.
   The rest have none because NGS publishes a receiver's week only with **5+ targets**: on the clone every WR / TE
   player-week with 5+ targets has an NGS row (287 / 287) and only one with 4 does; the receivers without a value have
   at most 10 targets in the season and at most 4 in any week. They show — with "No Next Gen Stats week in this window:
   NGS publishes a week only when he clears its minimum (5+ targets …), so this is unknown, not zero." The live site's
   blank columns are the missing mart only (the first nightly builds it; `stats.NGS_NOT_BUILT` says so meanwhile).
   Test: `test_the_two_empty_columns_fill_for_2026_with_the_mart_built`.
2. **New columns from data already in the database — done** (all the brief lists): EPA total and per target / carry /
   dropback; success rate (receiving, rushing, dropbacks); first downs (receiving, rushing) and per target / carry; WOPR;
   RACR; deep targets, deep-target share (of the team's deep targets) and deep targets as a share of his targets;
   targets / carries inside the 10; touchdown rates (per target, per carry, per pass attempt); yards per reception; yards
   per touch; expected fantasy points (total) and points over expected (+ per game); QB: AY/A, TD %, INT %, sack %,
   scramble yards (scrambles existed), rushing share of his fantasy points. **Deviation, said plainly**: the play-by-play
   numerators are not added to `int_player_game_pbp` but to a new intermediate beside it
   (`int_player_game_efficiency`) feeding a new mart — widening `int_player_game_pbp` rebuilds `fct_player_game` and the
   54 models under it (`dbt ls --select int_player_game_pbp+`: the whole projection chain), too long on this box and a
   wider `fct_player_game` on the hosted copy.
3. **New feeds — done for PFR weekly and the remaining NGS fields.** The 2026 weekly PFR files were downloaded
   (`data/raw/nflverse/pfr_advstats_{rec,rush,pass}/advstats_week_*_2026.parquet`, git-ignored; through week 4,
   published in season) and their columns read: the loader and `raw.nfl_pfr_advstats_*` already existed (2018 →; the
   clone already held 2026 weeks 1–4, so nothing was reloaded and `src/league_lab/ingest/**` is unchanged). Built:
   drops, drops per target, broken tackles, broken tackles per touch, yards before / after contact per carry, bad throws
   per attempt, times pressured, pressured per dropback. **Unavailable with the reason** (PFR publishes them in season
   files only, so no window can use them): receiving yards after contact, on-target throws. NGS: cushion, receivers'
   intended air yards, rushing efficiency, carries against 8+ in the box, time to the line of scrimmage (new in the
   mart), aggressiveness, QB intended air yards. NGS has **no catch percentage over expected**: no column claims one.
   PFR joins PFR id → gsis id through `analytics.player_id_map` only; unmapped rows: **7 of 1,290 2026 rows (3
   players)** — `dbt/tests/assert_pfr_advstats_rows_map_to_gsis.sql` (warn > 0, error > 25) and
   `test_pfr_rows_join_by_id_and_the_unmapped_are_counted`.
4. **The catalogue's shape — done.** Every row has `group` (the twelve, `stats.GROUPS`; the API also returns
   `groups`); the catalogue is ordered group by group in that order, display order inside a group
   (`stats.GROUP_ORDER`). `PRESETS` keep `wrte` / `rb` / `qb`, lead with 14 columns each (WR / TE incl. aDOT, air-yard
   share, EPA per target) and carry `full` (every column that applies to the position and is available, catalogue order;
   the API computes it per season: `stats.presets(catalogue)`). A noisy rate carries `minimum: {field, n}` (the sample
   below which the screen should grey it; the field is in the row). `GET /api/players.csv`: the same parameters plus
   `cols=` | `preset=` + `view=key|full`, `per_game=1`; a header of labels; `text/csv`;
   `isuckatfantasy-stats-<season>[-playoffs]-<positions>-<window>[-weeks-a-b].csv`; streamed from the same frame;
   unknown = empty cell; text starting `= + - @` disarmed with `'`; an unknown column is a 400 in words; a league
   without rosters (IM-3's `ref:` keys) gets no "Rostered by" column (absent, not empty).
5. **Rules — done.** Rates are summed numerator / summed denominator (tests on hand-built frames and SQL reconciliation
   on the clone); a zero or meaningless denominator is null (RACR with air yards ≤ 0, rushing share with points ≤ 0);
   PFR counts divide only by the games PFR covered. Timings and memory below.
6. **dbt — done.** Built on the clone: `int_player_game_efficiency`, `mart_player_game_advanced`, `mart_player_ngs_week`
   (+ tests); nothing downstream of them (`dbt ls --select <them>+` lists only themselves). The nightly's full
   `dbt build` picks them up (no selector change); the nightly's `ingest nfl` already loads `pfr_advstats_*`.
7. **Docs — done.** DATA_INVENTORY (50 rows + the PFR feed row + the metrics row; existing rows' exposure refreshed),
   METRICS § adv1.0, 14 registry rows (seed reloaded on the clone), WORDS, CHANGELOG, DEPLOY's region list.

**Not done**: nothing of the list is left unbuilt. Not attempted: the screen (IM-2's), PFR rows recovered through
`int_pfr_gsis_map` (it would map 2 of the 3 unmapped players; the brief says `player_id_map`).

## Files

* dbt: `dbt/models/intermediate/int_player_game_efficiency.sql` (new), `dbt/models/marts/nfl/mart_player_game_advanced.sql`
  (new), `dbt/models/marts/nfl/mart_player_ngs_week.sql` (+2 columns), both `schema.yml`s, `dbt/tests/assert_pfr_advstats_rows_map_to_gsis.sql`
  (new), `dbt/seeds/metric_registry.csv` (+14).
* API: `api/league_lab_api/stats.py` (catalogue, groups, presets, the advanced merge, aggregate, points, CSV helpers,
  the `stats_agg` region); `api/tests/test_im1.py` (new, 17 tests).
* Outside my files (smallest edits): `api/league_lab_api/research.py` (4 lines in `players()` / `stats_frame()`:
  `presets(cat)`, `groups`, `ctx.scoring` into `points()`, `aggregate_window`), `api/league_lab_api/main.py` (one
  self-contained `# ---- IM-1` block: the `/api/players.csv` route), `docs/DEPLOY.md` (one word: `stats_agg` in the
  region list), `CHANGELOG.md`, `docs/WORDS.md`.

## Schema in / out

* In: `analytics.fct_play`, `analytics.fct_player_game`, `analytics.player_id_map`, `staging.stg_nflverse__pfr_advstats_{rec,rush,pass}`,
  `staging.stg_nflverse__ngs_*`.
* Out: `intermediate.int_player_game_efficiency` (gsis_id, game_id; 55,986 rows, 8.7 MB; not published);
  **`analytics.mart_player_game_advanced`** (gsis_id, game_id unique; season, season_type, week, team;
  target / carry / dropback successes, dropback_epa, scramble_yards, team_deep_targets; has_pfr_rec / _rush / _pass,
  pfr_drops, pfr_carries, pfr_rush_yards_before / after_contact, pfr_broken_tackles, pfr_bad_throws, pfr_pass_drops,
  pfr_times_pressured / hurried / hit / blitzed — 59,606 rows 2016–2026, **9.3 MB**, ≈ 2.1 MB for the hosted window of
  3 seasons); `analytics.mart_player_ngs_week` + `avg_time_to_los`, `rec_avg_intended_air_yards` (3.2 → 3.5 MB).
* API: `/api/players?window=…` rows gain the new fields for the requested positions; `catalogue[]` gains `group` and
  (some) `minimum`; `presets[].full`; `groups`. A QB-only request no longer carries receiving fields (receiving columns
  now list RB / WR / TE). New route `GET /api/players.csv`.

## Commands

```bash
uv run league-lab dbt build --select int_player_game_efficiency mart_player_game_advanced mart_player_ngs_week
uv run league-lab dbt test --select assert_pfr_advstats_rows_map_to_gsis      # WARN 7
uv run league-lab dbt seed --select metric_registry && uv run league-lab dbt test --select metric_registry
cd api && OMP_NUM_THREADS=1 PYTHONPATH=. uv run pytest -q tests/test_im1.py tests/test_ii3.py tests/test_il1.py tests/test_inf2.py -p no:cacheprovider
uv run ruff check src app tests api && uv run python scripts/copy_standard.py --check
/home/claude/waveIM/check_api.sh /home/claude/wt-im1 ; /home/claude/waveIM/check_root.sh /home/claude/wt-im1
```

## Evidence

* **Tests added**: `api/tests/test_im1.py`, 17 tests (catalogue shape and groups; every new rate's numerator /
  denominator / aggregation / reason and its `minimum` field; presets 10–14 + `full`; window arithmetic on hand-built
  frames — 6 / 12 successes = 50%, not the 30% mean of weekly rates; deep share 3 / 6, not the mean of 40% and 100%;
  PFR drops divided by the PFR-covered game's targets only; zero / meaningless denominators null; QB rates; points over
  expected on the same games; the rushing share priced with the league's scoring; CSV cells; on the clone: the two
  NGS columns, SQL reconciliation of success rate / EPA per target / deep share / drop rate (≥ 100 receivers), EPA per
  dropback / success / pressure rate (≥ 25 QBs), a one-week window, the mart missing → the reason and no failure, the
  unmapped PFR count, the CSV against the JSON frame; the CSV without an ownership field). Result: **17 passed**; with `test_ii3.py`, `test_il1.py`,
  `test_inf2.py`: **48 passed, 2 skipped** (the skips are the recording tests). dbt: the 15 new schema tests pass;
  `assert_pfr_advstats_rows_map_to_gsis` WARN 7 (by design). `tests/test_metric_registry.py`,
  `test_nightly_relations.py`, `test_app_guards.py`: 10 passed. Ruff clean; `copy_standard.py --check` clean.
* **The PO's check scripts** (run twice for the API — at `576d05b`'s parent and at `576d05b`, identical results; root
  once at `576d05b`; the last commit after them, `72bcab3`, only drops the CSV's "Rostered by" column for a league
  without rosters, and `test_im1.py` passes on it, 17 / 17):

  ```
  check_api.sh:  === summary: 94 failed, 711 passed, 15 skipped, 41 deselected in 1291.97s (0:21:31)
  === NEW failures (not in /home/claude/waveIM/known_api_failures.txt):
  tests/test_ia2.py::test_partners_route_applies_both_rules
  tests/test_ib0.py::test_one_lineup_total_on_every_screen[dynasty-overlay-off]
  tests/test_ib0.py::test_one_lineup_total_on_every_screen[dynasty-overlay-on]
  tests/test_ii1.py::test_folk_package_is_not_promoted
  tests/test_ii1.py::test_folk_package_on_the_clone_rosters
  === known failures that now pass (fine: data-state tests):
  1          (tests/test_ib0.py::test_the_trade_board_this_week_is_the_context)
  check_root.sh: === summary: 4 failed, 1314 passed, 3 skipped in 293.90s (0:04:53)
  === NEW failures (not in /home/claude/waveIM/known_root_failures.txt):
  (none)
  ```

  **The five "new" API failures are not this branch's**: the base package (`git archive ab50682 api/league_lab_api
  api/tests`, run with the same venv against `league_lab_im1`) fails the same five (10 failed, 3 passed for the three
  test functions, the known Scrubs / MFL / test-league variants included). They are the Trade Finder, the trade
  evaluator's Folk package and Team / My Week lineup totals on the dynasty league — none reads `stats.py` or the new
  relations; they depend on this clone's data state (the PO's known list was made on another database), not on the code.
* **Timings** (`/api/players?league=<Scrubs>&position=WR&window=season`, TestClient, fresh process each; the base
  `ab50682` package and this branch alternated three times on the loaded box — load average 6–8 on 2 cores):

  | | cold | warm (median of 5) | answer (50 rows) |
  |---|---|---|---|
  | before (`ab50682`) | 0.49 / 0.41 / 0.61 s | 0.28 / 0.15 / 0.22 s | 124 KB |
  | after (this branch) | 0.73 / 0.62 / 0.88 s | 0.087 / 0.077 / 0.113 s | 217 KB |

  Without the per-window aggregate cache the branch's warm request was 0.23–0.46 s against 0.16–0.36 s (101 columns
  made the aggregate the request's largest cost); the window aggregate is NFL-wide, so it is now kept per window (memo
  region `stats_agg`, ≤ 8 entries). Cold is ~0.2 s slower (the advanced mart's read + the wider aggregate).
* **Memory** (`memo.frame_bytes`, what the budget counts): the season frame (region `stats`) 56 → 89 columns — 2026
  weeks 1–4 **0.59 → 0.93 MB**, a full season (2025) **2.53 → 3.95 MB** (+1.4 MB at most per season held); pandas'
  deep count 0.99 → 1.33 MB and 4.23 → 5.65 MB. New region `stats_agg`: 0.63 MB per window (2026 season), 0.81 MB
  (2025), at most 8 → ≤ 6.5 MB, inside `LEAGUE_LAB_CACHE_MB`'s LRU.
* **Relation sizes** (local, tables + indexes): `analytics.mart_player_game_advanced` **9.3 MB** (59,606 rows, 2016–2026;
  2024–2026 = 13,461 rows ≈ **2.1 MB** if windowed); `analytics.mart_player_ngs_week` **3.2 → 3.5 MB**;
  `intermediate.int_player_game_efficiency` 8.7 MB (not published). `scripts/hosted_relations.py` already lists
  `analytics.mart_player_game_advanced` for the API (stats.py names it).
* **Coverage** (Scrubs, 2026 season window, min games 1): WR 184, RB 111, TE 107, QB 51 players; the table below.

### Every new column (50): id, label, group, status, 2026 coverage on the clone (players with a value / with a game)

| id | label | group | status | WR | RB | TE | QB |
|---|---|---|---|---|---|---|---|
| `yards_per_reception` | Receiving yards per reception | Receiving | derived | 156 / 184 | 87 / 111 | 91 / 107 | n/a |
| `receiving_first_downs` | Receiving first downs | Receiving | present | 184 / 184 | 111 / 111 | 107 / 107 | n/a |
| `rushing_first_downs` | Rushing first downs | Rushing | present | 184 / 184 | 111 / 111 | 107 / 107 | 51 / 51 |
| `yards_per_touch` | Yards per touch | Rushing | derived | 159 / 184 | 103 / 111 | 91 / 107 | n/a |
| `adjusted_yards_per_attempt` | Adjusted yards per attempt | Passing | derived | n/a | n/a | n/a | 49 / 51 |
| `td_rate` | Touchdown passes per attempt | Passing | derived | n/a | n/a | n/a | 49 / 51 |
| `int_rate` | Interceptions per attempt | Passing | derived | n/a | n/a | n/a | 49 / 51 |
| `sack_rate` | Sacks per dropback | Passing | derived | n/a | n/a | n/a | 49 / 51 |
| `scramble_yards` | Scramble yards | Passing | derived | n/a | n/a | n/a | 51 / 51 |
| `rushing_points_share` | Share of his fantasy points from rushing | Passing | derived | n/a | n/a | n/a | 47 / 51 |
| `wopr` | Weighted opportunity rating (WOPR) | Air yards | derived | 184 / 184 | 111 / 111 | 107 / 107 | n/a |
| `racr` | Receiver air conversion ratio (RACR) | Air yards | derived | 169 / 184 | 31 / 111 | 89 / 107 | n/a |
| `deep_targets` | Deep targets (20+ air yards) | Air yards | derived | 174 / 184 | 103 / 111 | 96 / 107 | n/a |
| `deep_target_share` | Deep-target share (of his team's deep targets) | Air yards | derived | 174 / 184 | 101 / 111 | 96 / 107 | n/a |
| `deep_target_rate` | Deep targets, share of his targets | Air yards | derived | 172 / 184 | 88 / 111 | 95 / 107 | n/a |
| `inside_10_targets` | Targets inside the 10 | Red zone | derived | 174 / 184 | 103 / 111 | 96 / 107 | n/a |
| `inside_10_carries` | Carries inside the 10 | Red zone | derived | 174 / 184 | 103 / 111 | 96 / 107 | 51 / 51 |
| `receiving_epa` | Receiving EPA | Efficiency | derived | 172 / 184 | 88 / 111 | 96 / 107 | n/a |
| `epa_per_target` | EPA per target | Efficiency | derived | 172 / 184 | 88 / 111 | 95 / 107 | n/a |
| `receiving_success_rate` | Receiving success rate | Efficiency | derived | 172 / 184 | 88 / 111 | 95 / 107 | n/a |
| `first_downs_per_target` | First downs per target | Efficiency | derived | 172 / 184 | 88 / 111 | 95 / 107 | n/a |
| `receiving_td_rate` | Touchdowns per target | Efficiency | derived | 172 / 184 | 88 / 111 | 95 / 107 | n/a |
| `rushing_epa` | Rushing EPA | Efficiency | derived | 36 / 184 | 96 / 111 | 8 / 107 | 49 / 51 |
| `epa_per_carry` | EPA per carry | Efficiency | derived | 36 / 184 | 96 / 111 | 8 / 107 | 49 / 51 |
| `rushing_success_rate` | Rushing success rate | Efficiency | derived | 36 / 184 | 96 / 111 | 8 / 107 | 49 / 51 |
| `first_downs_per_carry` | First downs per carry | Efficiency | derived | 36 / 184 | 96 / 111 | 8 / 107 | 49 / 51 |
| `rushing_td_rate` | Touchdowns per carry | Efficiency | derived | 36 / 184 | 96 / 111 | 8 / 107 | 49 / 51 |
| `dropback_epa` | EPA on dropbacks | Efficiency | derived | n/a | n/a | n/a | 49 / 51 |
| `epa_per_dropback` | EPA per dropback | Efficiency | derived | n/a | n/a | n/a | 49 / 51 |
| `passing_success_rate` | Dropback success rate | Efficiency | derived | n/a | n/a | n/a | 49 / 51 |
| `expected_points` | Expected fantasy points | Expected points | derived | 174 / 184 | 103 / 111 | 96 / 107 | 51 / 51 |
| `points_over_expected` | Points over expected | Expected points | derived | 174 / 184 | 103 / 111 | 96 / 107 | 51 / 51 |
| `cushion` | Average cushion (yards) | Next Gen Stats | derived | 96 / 184 | n/a | 37 / 107 | n/a |
| `ngs_intended_air_yards` | Intended air yards per target (Next Gen Stats) | Next Gen Stats | derived | 96 / 184 | n/a | 37 / 107 | n/a |
| `rush_efficiency` | Rushing efficiency (Next Gen Stats) | Next Gen Stats | derived | n/a | 45 / 111 | n/a | n/a |
| `stacked_box_rate` | Carries against 8+ defenders in the box | Next Gen Stats | derived | n/a | 45 / 111 | n/a | n/a |
| `time_to_los` | Time to the line of scrimmage (seconds) | Next Gen Stats | derived | n/a | 45 / 111 | n/a | n/a |
| `aggressiveness` | Aggressiveness (throws into tight windows) | Next Gen Stats | derived | n/a | n/a | n/a | 42 / 51 |
| `ngs_pass_intended_air_yards` | Intended air yards per attempt (Next Gen Stats) | Next Gen Stats | derived | n/a | n/a | n/a | 42 / 51 |
| `drops` | Drops | Advanced (PFR) | derived | 162 / 184 | 84 / 111 | 91 / 107 | n/a |
| `drop_rate` | Drops per target | Advanced (PFR) | derived | 162 / 184 | 84 / 111 | 91 / 107 | n/a |
| `broken_tackles` | Broken tackles | Advanced (PFR) | derived | 165 / 184 | 99 / 111 | 91 / 107 | n/a |
| `broken_tackle_rate` | Broken tackles per touch | Advanced (PFR) | derived | 149 / 184 | 98 / 111 | 87 / 107 | n/a |
| `yards_before_contact_per_carry` | Yards before contact per carry | Advanced (PFR) | derived | n/a | 91 / 111 | n/a | 45 / 51 |
| `yards_after_contact_per_carry` | Yards after contact per carry | Advanced (PFR) | derived | n/a | 91 / 111 | n/a | 45 / 51 |
| `rec_yards_after_contact` | Receiving yards after contact | Advanced (PFR) | unavailable | — | — | — | n/a |
| `bad_throw_rate` | Bad throws per attempt | Advanced (PFR) | derived | n/a | n/a | n/a | 46 / 51 |
| `times_pressured` | Times pressured | Advanced (PFR) | derived | n/a | n/a | n/a | 46 / 51 |
| `pressure_rate` | Pressured per dropback | Advanced (PFR) | derived | n/a | n/a | n/a | 46 / 51 |
| `on_target_rate` | On-target throws per attempt | Advanced (PFR) | unavailable | n/a | n/a | n/a | — |

## The PO lines I need (PO-owned files)

* `scripts/sync_to_hosted.sh` line 135 — add `mart_player_game_advanced` to the windowed tables (it has `season`; 9.3 MB
  in full → ≈ 2.1 MB for 3 seasons):
  `SLIM_TABLES="fct_player_game fct_player_game_league mart_player_week_features mart_player_week_rankings mart_player_context mart_player_recent_form mart_player_expected_points mart_player_trends mart_player_season mart_player_season_team mart_receiver_vs_cb player_team_history mart_player_game_advanced"  # IL-1: the Role block's "games without X" reads 2024 on; IM-1: the Stats advanced numerators`
  Without it the sync publishes the whole 9.3 MB (still inside Neon's budget, ≈ 300 MB used of 512).
* Nothing else: `scripts/hosted_relations.py` already picks the mart up from `stats.py`; the nightly's full `dbt build`
  and its `ingest nfl` (which loads `pfr_advstats_*`) need no change; `app/whats_new.md` — if the PO wants a line:
  "Players · Stats: 50 more numbers per player — EPA, success rate, WOPR, deep targets, drops, broken tackles, yards
  after contact, pressures and more — and a Download CSV."

## Limitations (honest list)

* The live site shows the new columns only after the first nightly builds `mart_player_game_advanced` and the sync
  publishes it; until then they are — with "These columns arrive with the nightly update; they are not on this copy
  yet." and leave the Full table (tested). The EPA / first-down / deep / inside-10 / AY/A / rates-on-the-stat-line
  columns come from `fct_player_game` and work at once.
* Dropback EPA is the play's EPA (a receiver's fumble after the catch counts against the passer): `fct_play` has no
  `qb_epa`. Bad throws per attempt keeps spikes and throwaways in the attempts (PFR's own rate does not). Both are said
  in the definitions.
* PFR coverage is "the games PFR lists him in": a receiver with no target in a game has no PFR row, so his drops per
  game divide by all his games (true: no target, no drop), while his drop rate divides by the PFR-covered games'
  targets. 2 of the 3 unmapped 2026 PFR players (Hibner, Strand) are in `int_pfr_gsis_map` but not in
  `player_id_map` — the map, not this mart, would have to change.
* NGS's rushing "weeks" sample counter keys on RYOE (IL-1's choice), so for 2016–17 (no RYOE) the hover of efficiency /
  8+ box / time to the line says 0 NGS weeks although the values exist.
* Counts from `int_player_game_pbp` (deep targets, inside-10 / red-zone looks) are null, not 0, for a player who played
  but was never on the end of a play (10 of 184 WRs on the clone) — the existing red-zone columns behave the same.
* The catalogue answer is bigger (101 entries; the 50-row JSON 124 → 217 KB before gzip). IM-2 may want a
  `catalogue=0` switch later; not built.

## Next task

IM-2 reads `group`, `groups`, `presets[].full`, `minimum` and `/api/players.csv`. After the merge: the PO's
`SLIM_TABLES` line, a nightly, then check the live Stats Full table (WR / TE: separation and YAC over expected filled;
the PFR columns present).
