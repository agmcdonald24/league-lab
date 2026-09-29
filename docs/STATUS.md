# STATUS

Updated: 2026-09-27 · Owner: Andrew · Integration: Claude (Cowork session)

## Current state

| Item | Value |
|---|---|
| Commit | git `main` (GitHub `agmcdonald24/league-lab`, private); latest change: S-01a (2026-09-27) |
| Phase | 1 (core) bootstrapped on Andrew's Mac 2026-09-26; 1.5 (Manager's Edge) reviewed and polished; 1.6 (Trends), 2 (play-by-play), 2b (Rankings) built; **Iteration 7 (share-ready beta) built 2026-09-26 — hosting steps are Andrew's**; Iteration 8 (projection v2) built; **Iteration 9 started — S-01a done 2026-09-27** |
| Python / uv | 3.13 (project), `uv.lock` committed (97 packages, unchanged this iteration) |
| Key versions | dbt-core 1.11.15, dbt-postgres 1.11.0, polars 1.44.2, psycopg 3.3.6, streamlit 1.64.0, httpx 0.28.1, pandas 3.0.6, plotly 7.1.0 |
| Database | `league_lab` on localhost:5432 (Homebrew PostgreSQL 17 on the Mac; PostgreSQL 16 in the build sandbox); ≈2.2 GB after Phase 2 (raw pbp 751 MB, participation 321 MB) |
| Roles | `league_lab_pipeline` (owner), `league_lab_app` (read-only) |
| League | League of Scrubs — chain 2026 `1389709692405551104` → 2025 `1256450429399617536` → 2024 `1112705311674097664`; 10 rosters; Andrew = roster 2 (MacZaddy / MacDaddy's team of bums / MacDaddy) — *not* hard-coded anywhere |
| Explorer | 13 pages on 127.0.0.1:8501 (Home + 12; Trends 3, Rankings 4); perspective (league, team) in the URL |
| Schedule / backup destination / roster id | O03, O05 still open; roster id noted above |

## Evidence — real league data (sandbox replay of the Mac's Sleeper archive, 2026-09-26)

| Source | Partitions | Rows |
|---|---|---|
| nflverse (18 datasets) | 111 | 2,346,719 |
| sleeper (3 seasons) | 96 | 14,207 |

Database ≈ 1.05 GB; raw archive 52 MB.

* `dbt build`: **214 pass, 1 warn, 0 error** (215 nodes: 2 seeds, 61 models, 8 singular + 143 generic tests).
* The one warning: `assert_optimal_lineup_matches_sleeper_potential` — our optimal-lineup totals equal
  Sleeper's `ppts` for **29 of 30 rosters** across 2024–2026 (exact to the cent); the exception is
  2025 roster 6 at −9.70, a bench defense Sleeper did not count as potential.
* **Points reconciliation on the real league**: 4,240 mapped QB/RB/WR/TE/K player-weeks, **0** with
  |observed − recomputed| > 0.5, mean absolute difference 0.000. The scoring map is exact for this league.
* Identity: 7,415 accepted sleeper↔gsis mappings (was 6,197), 9 resolved by name confirmation
  (e.g. Conklin/Izzo swap between providers), 18 quarantined ambiguous pairs; 2 rostered skill
  players without an NFL id across three seasons (Trey Smack K 2026, Tyler Conklin 2024 — now resolved).
* Andrew's `dbt build` on the Mac (Phase 1, 2026-09-26 10:33): 152/152 pass.
* `pytest`: 14/14 · `ruff`: clean · Streamlit headless: 12/12 pages render; Team Hub / Waiver Wire /
  Matchups / Trade Finder / League Intel screenshots reviewed with the real roster.
* Sanity reads that came out of the marts (week 2 → 3, 2026): Victory is Mine! is 2-0 with a 4-14
  all-play record (+1.56 luck); GoodGameBuddy 0-2 with 12-6 all-play (−1.33); MacZaddy has 3.7 bench
  points left per week and the best lineup efficiency (97%); free-agent WR Malik Washington carries a
  26% target share on 85% snaps; Terry McLaurin (Run Bijan Run) is 7.2 ppg below his expected points.

## Hotfix 2026-09-26 (after Andrew's first `make ingest-nfl` on the Mac)

`rosters_weekly` 2016–2024 failed with *cannot alter type of a column used by a view*: the pilot had
loaded 2025/2026 (`height` integer), dbt had built views on top, and the backfill needed to widen the
column to double. Fix in `db.py`: (1) `downcast_to_existing` casts an incoming float column to the
stored integer type when every value is whole (lossless, no DDL — this is the `height` case); (2) when a
real widening is needed, dependent views are dropped with a logged warning and recreated by the next
`dbt build`. Reproduced and verified in the sandbox on both paths.

## Polish pass 2026-09-26 (Andrew's review of the Edge pages)

* Research page removed; Data Status renumbered to 10.
* `app/lib/table.py`: registry of every displayed column (label, kind, plain-English help); `show()` renders
  readable headers with hover definitions, % as %, booleans as words, blank nulls; `howto()` expanders next to
  every table; glossary on Home. All 11 pages rewritten on it. 11/11 headless page tests pass, screenshots reviewed.
* Identity: espn_id and sportradar_id bridges + source-majority rule → 8,063 accepted mappings (49 quarantined,
  all legacy name collisions / Sleeper "Duplicate Player" entries). One league player still unmapped (Trey Smack, K, 2026 rookie —
  no shared id in any source yet).
* Routes run: no free in-season source; see PROJECT_PLAN P2-12 for the plan.

## Trends 2026-09-26 (Andrew: "are players trending up or down and by which metrics")

* New seed `trend_metrics` (10 metrics), models `int_player_game_metric_long`, `mart_player_trends`,
  `mart_player_trend_tags`, `mart_defense_trends`; 7 new registry rows; definitions in METRICS.md "Trends".
* New page **3 Trends**; trend tags and momentum on Team Hub and Waiver Wire (momentum sort); weekly packs gained
  "Movers" (league recap) and "Your roster's trends" / "Free agents with rising opportunity" (team brief).
* Validated on the complete 2025 season: top risers Luke Musgrave (momentum 2.5: ↑ target share +9 pts, ↑ snaps +16 pts),
  Adam Thielen, Colston Loveland (+15 pts target share); defense trends NE-vs-QB stiffer (17.0 → 7.4 allowed),
  NYJ-vs-TE softer (10.1 → 23.1). 2026 has three games, so every player is `insufficient` by design and the page
  shows the early read (latest game vs season) until week 4 scores land.
* Page renumbering: 3 Trends, 4 Matchups, 5 Trade Finder, 6 League Intel, 7 League, 8 Players, 9 Receivers,
  10 Kickers, 11 Data Status (stale files moved to `backups/stale_iteration3/` on the Mac).
* Packs verified on 2025 week 17 (`--league-id 1256450429399617536`) and 2026 week 3.

## Phase 2 2026-09-26 — play-by-play, FTN charting, participation

* New raw datasets: `pbp` (2016–2026, 490k plays, core ~190-column subset), `pbp_participation`
  (2016–2025, published after each postseason so 2026 is expected-missing), `ftn_charting` (2022–2026).
  Mirrored with curl in the sandbox and loaded with `--offline` in 35 s; the Mac downloads ≈265 MB once.
* New models: `fct_play` (eligibility flags + context), `bridge_play_actor`, `bridge_play_participation`
  (4.9M rows), `fct_play_charting`, `int_team_game_pbp`, `int_player_game_pbp`, `int_play_context_long`,
  `mart_player_context` (153k rows); `fct_team_game` / `fct_player_game` / season marts / recent form /
  availability extended. `raw.routes_feed` + `league-lab import-routes` for a licensed routes file.
* **Reconciliation** (plan §9.4–9.6): play-derived targets = nflverse weekly targets in 4,533 of 4,533
  2025 player-weeks; over 5,344 team-games 2016–2026 sacks match everywhere, attempts differ in 4,
  targets in 2, carries in 1 (upstream stat corrections); dropbacks = attempts − spikes + sacks + scrambles
  holds in every team-game. Halves sum to season totals for every player (tolerance = those corrections).
  Manual first-read check PHI–DAL 2025 week 1: 3 first reads by hand = 3 in the mart.
* **Finding that changed the spec**: FTN `read_thrown = "0"` is *not* first read from 2023 (dictionary
  wording carried into MVP1_PLAN §6). `0` sits on every run/kick/punt and on 2–3% of throws (the slice
  that is NULL in 2022); `1` is the majority code on targeted throws in every season. Coded `1` = first
  read; documented in METRICS.md with the counts.
* **Routes**: the participation proxy runs ≈10–15% above charting-service route counts (Chase 2024:
  705 vs ≈615), so TPRR/YPRR proxies are lower bounds and are labelled proxy on every page. In-season
  routes still need a paid feed (import contract ready).
* Season marts now sum team denominators over **appearance games only** (`played`), per plan §5. This
  moved shares for special-teams-only players (e.g. Bo Melton 2025: 3.7% → 4.9%); fantasy-relevant
  players are unchanged.
* `dbt build`: **259 pass, 1 warn, 0 error** (260 nodes: 3 seeds, 71 models, 14 singular + 172 generic
  tests) in 1 m 58 s. `pytest`: 21/21 (7 new for the routes-feed contract). `ruff`: clean. 12/12 pages
  render; Receivers page screenshots reviewed (first-read table + chart, routes proxy, context splits).
* Sanity reads (2025 REG): first-read share leaders Garrett Wilson 47%, JSN 44%, Nabers 43%, London 43%,
  St. Brown 42%; Chase 72% of his own charted targets were first reads, Bijan 27%; Bo Nix 669 dropbacks
  (634 + 36 scrambles − spikes); Chase target share 35.5% in H1 vs 28.9% in H2; Garrett Wilson 47% first-read
  share with Fields vs 48% with Taylor.

## Rankings 2026-09-26 (Andrew: "a rankings model to rank players each week")

* Weekly feature snapshot `mart_player_week_features` (109k player-weeks 2016–2026), strictly as-of: a
  week-N row sees only games before week N (`assert_features_never_peek`). Universe = rostered
  QB/RB/WR/TE whose team plays; the upcoming week uses the latest published roster (2026 week 3 = 581 players).
* Baseline projection: OLS per position on 2019–2022 (`league-lab fit-rankings`), 13 features, weights in
  `seeds/ranking_weights.csv` and printed in METRICS.md; `mart_player_week_rankings` applies the same formula
  in SQL (`assert_rankings_apply_seed_formula`) with grouped contributions so the page can show *why*.
* **Backtest 2023–2025** (`league-lab backtest`, weights never saw these seasons; 54 season-weeks per position):
  baseline Spearman QB 0.501 / RB 0.670 / WR 0.604 / TE 0.573 vs best naive 0.469 / 0.644 / 0.565 / 0.524 —
  higher in all 12 position-seasons; top-N hit rate 51.9% / 62.3% / 46.4% / 46.3%. Report in `reports/backtests/`.
* Rankings page (4; later pages renumbered 5–12): live board for the next week with form / usage / matchup /
  Vegas / home terms, scope filters, "your players", contribution chart, the backtest scoreboard and the formula.
  Team brief gains week projections for the roster and the best projected free agents.
* Fix on the way: `show()` now coerces numeric kinds to float64 (an all-None column rendered the word "None").
* `dbt build`: **277 pass, 1 warn, 0 error** (278 nodes); `pytest` 21/21; `ruff` clean; 13/13 pages render.

## Share-ready beta 2026-09-26 (Andrew: "offer this publicly ... collect feedback")

* **Hosted publishing**: `scripts/sync_to_hosted.sh` / `make sync-hosted` publishes the analytics relations the
  pages and packs reference (derived from the code at run time: 35 of 49, ≈290 MB) plus seeds and `ops`, creating
  the read-only `league_lab_app` role. Drop-then-restore, not atomic: Neon's free tier caps a project at 0.5 GB and
  cannot hold two copies (the first atomic attempt failed on exactly that), so pages show "not built yet" for the
  restore's minute or two. `make refresh` runs it when `LEAGUE_LAB_HOSTED_ADMIN_URL` is set; refuses the local
  cluster. Simulated end to end in the sandbox; all 13 pages render against the hosted copy with the read-only role.
* **Live**: deployed 2026-09-26 on Neon (us-east-2) + Streamlit Community Cloud from `github.com/agmcdonald24/league-lab`.
  Found on the first walkthrough and fixed: the Receivers guard named a play-level table the hosted copy omits; the
  freshness banner counted historical failures (now: partitions whose latest attempt failed); the viewer toolbar
  showed Fork/GitHub (`client.toolbarMode = viewer`); secrets added after the first deploy needed a reboot (the
  bridge now re-reads secrets before every connection).
* **App for the cloud**: `st.secrets` → environment bridge (`LEAGUE_LAB_*`), optional beta password gate
  (`LEAGUE_LAB_APP_PASSWORD`), sidebar feedback button (`LEAGUE_LAB_FEEDBACK_URL`), `app/requirements.txt`
  (runtime only — Community Cloud reads the entrypoint directory's file first), `app/.streamlit/config.toml`.
* **UI**: sidebar **Table detail** toggle (Essentials hides denominators, z-scores, coverage and fine-grained counts on
  every table via one registry rule; Everything shows all); Home rebuilt as a landing page (what it is, your week at a
  glance — record, all-play, lineup efficiency, next opponent, highest projections, movers — pages, what's new from
  `CHANGELOG.md`, glossary, data & attribution with the FTN CC BY-SA note). Phone width verified.
* Hard-coded to the current league by Andrew's choice; "connect any league" (S-01/S-02) stays in the plan.
* `docs/HOSTING.md` is the step-by-step (Neon or Supabase free tier → GitHub → Streamlit Community Cloud → secrets).
* `dbt build` unchanged (277 pass, 1 warn); `pytest` 21/21; `ruff` clean; 13/13 pages render locally and against the hosted copy.

## Second league 2026-09-27 (Andrew: "include the other league I have so I can share with that group too")

* **Config**: `LEAGUE_LAB_SLEEPER_LEAGUE_ID` takes a comma-separated list; the first id is the *reference* league
  (`Settings.reference_league_id` → dbt var `reference_league_id` → `int_current_league`) whose scoring prices the
  NFL-wide marts. `dim_league_season.is_reference_league` / `scoring_diff_vs_reference`; the sidebar warns a
  non-reference league's viewers which keys differ. `?league=<id>` deep link.
* **Ingestion**: the chain walk stops at Sleeper's "no previous league" marker (`"0"` on older leagues, null on
  newer) instead of fetching league `0` (404 → a failed partition that flipped `make` to exit 1 and the banner to
  "1 partition failing"). `mart_data_status` counts a partition as failing only when its latest attempt failed.
* **Two leagues per season broke three single-league assumptions**, all fixed: `dim_league_season.season` was
  tested unique (now `[league_id, season]`, plus `assert_one_reference_league`); `mart_coverage` joined leagues by
  season (now one row per season: `leagues`, `league_names`, max/min scored weeks); the scoring map did not know
  the second league's keys (78 warn rows: six yardage-game bonuses, three 40+ yard TD bonuses, four missed-FG
  distance buckets).
* **Scoring map v2** (`league_lab.scoring`, seed `scoring_stat_map` + `kind`): yardage-game bonuses as exclusive
  buckets (`column:low:high`), 40+/50+ yard passing/rushing/receiving TDs counted from play-by-play
  (`int_player_game_pbp.pass_tds_40p` … joined onto the stats row in `fct_player_game` and `league_player_week`),
  missed-FG distance buckets. Expected points use `include_bonuses=false`. Seeds `+full_refresh: true`. Sandbox
  checks: long-TD counts never exceed the weekly TD counts (0 violations), receiving = passing long TDs in every
  game, 2023–2025 REG totals ≈ 100 / 30 / 100 per season (40+); reference-league reconciliation still 0 rows.
* Second league: *Forever Unclean Dynasty* (12 teams, superflex, 1 PPR, 6-pt pass TD, chain 2021–2026). Its
  rankings/expected points are in the reference league's scoring until S-01 — the sidebar says so.
* **First live use with two leagues surfaced three app bugs** (Andrew): the sidebar snapped back to the reference
  league on every page (Streamlit drops the query string on navigation → the choice now also lives in
  `st.session_state`, URL > session > reference; the URL's team applies only to the URL's league since roster ids
  repeat); Trade Finder / League Intel indexed a pivot with `K` — the dynasty league starts no kicker
  (`league_positions()` = positions present); the Rankings guard named `mart_player_week_features`, which the page
  never reads and the hosted sync therefore omits (`tests/test_app_guards.py` now enforces guard = read). `query()`
  turns `UndefinedTable` into a "being refreshed" notice for the sync's drop-restore window. Verified with the
  headless page run (13/13) and a Playwright walk: `?team=5` on Team Hub → Matchups → Rankings keeps team 5.

## Iteration 8 — Projection v2 2026-09-26 (Andrew: "whats the next phase … lets kick that off")

* **Built** (plan M-01 + M-03, part of M-02): `league_lab.projections` — per position, a gradient-boosted regressor
  per stat-line component (scikit-learn HistGradientBoosting; Poisson for counts/TDs, squared error for yards) on
  ~70 as-of features, priced per configured league with the scoring map; quantile regressors for P10/P50/P90 with
  split-conformal calibration on the newest training season. CLI `league-lab project` (nightly, in `refresh.sh`)
  and `backtest-v2`; tables `ops.projections / projection_backtest / projection_importance`; marts
  `mart_player_week_projections` (outcome priced under the league's own scoring via `league_points` +
  `zero_stat_columns`) and `mart_projection_backtest`. Rankings page: model switch (v2 default, baseline as the
  check), floor–ceiling chart, projected stat line, per-league backtest with coverage, importances.
* **Walk-forward 2021–2025** (each season by a model trained on the seasons before it; 90 season-weeks per position;
  Spearman of the v2 projection vs the baseline, reference league): QB 0.542 vs 0.513 (+0.029), RB 0.661 vs 0.651
  (+0.010), WR 0.610 vs 0.600 (+0.010), TE 0.554 vs 0.555 (−0.001, a tie). MAE lower or equal at every position
  (QB 5.86 vs 6.12, RB 4.29 vs 4.32, WR 4.07 vs 4.09, TE 3.01 vs 3.01). Dynasty league (6-pt pass TD, full PPR,
  bonuses): QB +0.028, RB +0.010, WR +0.011, TE +0.002 — and there the "baseline" is the reference-scoring formula,
  i.e. what that league saw before. **Interval coverage** (target 80%): QB 78%, RB 80%, WR 81%, TE 81% in both
  leagues; widths are player-specific (a WR1 in the dynasty league: floor ≈ 6–9, projection ≈ 15–18, ceiling ≈ 28–30).
* **What it took to get the interval right** (three iterations, all in the report history): (1) quantile GBMs on raw
  points collapsed at P10 — a fifth of played WR weeks score 0, the model's initial constant sat on that mass and
  never left it (every WR's floor was 0 in one league and not the other, by luck); (2) quantiles of the residual
  around the priced line fixed that but learned in-sample residuals, so the intervals were too narrow (coverage 52–78%)
  and the P50 model got worse than the line; (3) residuals against **out-of-fold** lines (components fitted on the
  odd training seasons price the even ones and vice versa) plus split-conformal widening on the newest training
  season → calibrated. The board ranks by the priced line; P50 is informational.
* **Honesty notes**: the first run used the routes proxy (`route_participation_l3`) and TE leaned on it hardest —
  but the participation file arrives after the postseason, so the live board would never have it; removed.
  Gains over the baseline are modest and real at QB/RB/WR and nil at TE; the calibrated interval is the bigger
  product change. Everything shown for 2026 is out of sample (trained on 2016–2025).
* Verified: `make pytest` 25/25, `ruff` clean; 13 pages × 2 leagues render headlessly; walk-forward report under
  `reports/backtests/projection_v2_2021_2025_*.md`.

## S-01a 2026-09-27 — per-league observed points (Iteration 9)

Task: league pages priced PPG / xPPG / ranks in the reference league's scoring. Plan sections: Iteration 9 (S-01a),
Iteration 7 (S-01a row). **Where it was validated:** a replica, not the Mac's live database — the Mac's nightly backup
`backups/league_lab_20260927_080431.dump` (pg_dump 17.11, 08:04 today, code `aee5c98` = the same models as `1ad4e67`)
restored into PostgreSQL 17.10 in a cloud sandbox, Python 3.13 from `uv.lock`. The Mac's database still holds the
pre-S-01a marts until its next `make build` (or the 08:00 nightly).

* **Baseline first** (replica, unchanged code): `make build` PASS=289 WARN=2 ERROR=0 (291 nodes) — identical to the
  Mac's 08:00 refresh log, same two warnings (`assert_recomputed_points_reconcile` 6 rows,
  `assert_optimal_lineup_matches_sleeper_potential` 7 rows).
* **Built**: `fct_player_game_league` (league_id × gsis_id × game_id; every `fct_player_game` row × each current
  league-season; `points` = `league_points` over the stats row + long-TD counts, `points_expected` = same map over the
  ffverse expected stats without bonus keys; 368,662 rows = 184,331 × 2; 52 MB) and `mart_league_player_season`
  (league × player × regular season: points, PPG, L3/L5 PPG, xPPG, PPG − xPPG, positional ranks; 41,664 rows; 8 MB).
  Re-keyed on them: `mart_player_availability` (points_std, ppg_std, points_per_game_l3/_l5, expected_per_game,
  diff_per_game, games_with_expected), `mart_league_keeper_candidates`, `mart_league_positional_strength` (through
  availability) and `mart_league_draft` (season points under the chain's current scoring, via `chain_id`). The
  NFL-wide marts (`fct_player_game`, `mart_player_season`, `mart_player_recent_form`, `mart_player_expected_*`) are
  untouched: the research pages and the projection features read them.
* **After**: `make build` **PASS=301 WARN=2 ERROR=0** (303 nodes: 4 seeds, 69 table models, 193 data tests, 37 views;
  +2 models, +10 tests), the same two warnings with the same row counts (6, 7). 9 m 25 s on the replica's 2 vCPUs
  (the Mac runs 291 nodes in 2 m 20 s). `make pytest` 25/25, `make lint` clean.
* **Josh Allen check** (acceptance): dynasty Team Hub (Pitts n' Titts, roster 1) PPG **49.6** (49.65 = Sleeper
  48.0 + 51.3 = 99.30 ÷ 2 games), was **38.2** (38.24 — League of Scrubs scoring, which is still what the League of
  Scrubs Team Hub shows). xPPG 32.7 (was 27.2), PPG − xPPG +16.9 (was +11.0). Seen in SQL, in the headless run's
  rendered dataframe and in the browser.
* **`assert_league_points_match_recomputed`** (the acceptance test): PASS — 737 rostered player-games in the two
  current league-seasons (460 dynasty, 277 League of Scrubs), 737 equal to the cent, 0 missing, max |diff| 0.00;
  in 2026 Sleeper's observed points equal the recomputed ones on all 737. Negative control: pricing the dynasty's
  460 in League of Scrubs scoring (what the pages showed) fails 389 of them (dynasty − reference = +2.21 per
  player-game on average).
* **Reference league did not move** — `assert_reference_league_matches_nfl_marts` PASS (per-game points, season
  points / PPG / games / position, L3/L5, expected points, and no player-game missing for either league), and a
  before/after diff of the league marts on the replica: League of Scrubs 0 changed cells (804 availability rows,
  157 keeper, 49 positional strength, 450 draft picks). Dynasty: only points-derived columns changed —
  availability 351 of 804 rows, keeper facts 223 of 291 (184 position ranks), positional strength 48 of 48
  (16 position ranks), draft 416 of 480 season-point values (159 ranks).
* **Projection inputs untouched**: `mart_player_week_projections` and `fct_player_game.points_current_scoring`
  byte-identical before/after; `mart_player_week_features` identical except `prev_snap_pct` in 21,628 rows by
  ≤ 4.4e-16 (float summation order in an `avg` over double precision — none of the 44 models upstream of the
  features/projections changed).
* **Sidebar**: on a non-reference league the notice is now one line, "NFL research pages use reference scoring
  (League of Scrubs)"; the key-by-key difference sits in a caption under it until U-10 moves it into an expander.
  Players, Trends, Receivers and Matchups' defense-vs-position section carry a one-line reference-scoring note;
  the Opp rank / points-allowed tooltips say reference scoring; Home's projection panel and the packs' baseline
  tables are labelled baseline / reference scoring.
* **Hosted budget**: pages and packs name the same 37 analytics relations as before (the new marts are
  pipeline-only), so the sync publishes the same 47 relations: 310.9 MB estimated on the replica with the sync
  script's own selection (309.9 MB before; limit 500 MB). Nothing was synced.
* **Headless page check** (HANDOFF.md): 13 pages × 2 leagues = 26 runs, 0 exceptions.
* **Browser walk** (Chromium via Playwright, local app on the replica): dynasty Team Hub, Trade Finder and Waiver
  Wire (team 1), plus League of Scrubs Team Hub (team 9) for contrast — 0 exceptions. Team Hub: Allen 49.6 / L3 49.6 /
  xPPG 32.7 / +16.9; QB starter PPG 78.4 (Allen 49.65 + Hurts 28.78), rank 1; roster value Allen 99.3 pts, pos rank 1.
  Trade Finder: QB/RB/WR/TE matrix (no K), sell-high list led by Allen +16.9. Waiver Wire: 79 free agents ranked by
  dynasty xPPG (Noah Fant 14.1; 11.2 in League of Scrubs scoring). League of Scrubs Team Hub: Allen 38.2, no notice.
  Console: 8 × 404 from Streamlit probing `/<previous page>/_stcore/health|host-config` on hard navigation — framework
  noise, not page errors.
* **Data partitions touched**: none — no ingestion, no raw/ops writes; dbt rebuilt the replica only.
* **Not done / open**: (1) the Mac's database and the hosted copy still have the old marts — `make build` (or the
  nightly) and a push are needed, see next actions; (2) `metric_registry.csv` versions for `expected_points` and
  `positional_strength` (definition now per league) were not bumped and no row was added for per-league points —
  the seeds were out of bounds for this task; (3) still reference-scored on league-facing screens, labelled:
  Opp rank, Home's baseline projection panel, the packs' baseline tables, the Rankings board's as-of inputs
  (PPG / xPPG L5 / prev PPG; the page's how-to says reference scoring, but the shared PPG tooltip there reads
  "this league's scoring" — pre-existing); (4) expected points
  leave bonus keys out in every league, so in the dynasty PPG − xPPG includes the bonus points; (5) past seasons on
  a league page are priced in the league's current scoring (by design, so years compare); (6) seen on the walk,
  pre-existing, not S-01a: the dynasty "Roster value" table says "Waiver / free agent" for players drafted in earlier
  seasons — the mart only reads the current season's draft.

## Wave A (Iteration 9)

### PO merge and QA 2026-09-29

* Three Opus developers ran in parallel, each in its own git worktree, branch and database clone (`league_lab_u10`,
  `_u11`, `_m06`) off `59ed8ca` (S-01a); merged into `integration/wave-a` (conflicts in CHANGELOG, STATUS and the
  `table.py` registry, all "keep both"), rebuilt on the main database (`dim_league_season+`, `mart_projection_drift`,
  `league-lab drift`; 80 pass / 2 pre-existing warns), `pytest` 29/29, `ruff` clean, headless check 26/26.
* One QA agent walked the integrated build on both leagues (~30 controls, 22 rosters via SQL). Findings and what
  was done: (1) **sidebar selectors dropped every second change** — the League/Team selectboxes were unkeyed with a
  moving `index=`, so their identity flipped between runs; now keyed widgets whose value the app re-asserts before
  each render (a keyed widget's own state does not survive a page change) with the URL seeding only a fresh visit or
  a pasted link — verified by a Playwright walk: three league switches in a row, three team switches, team kept across
  Matchups → Rankings, "whole league" on Rankings then Team Hub back on the last team, pasted deep link honoured;
  (2) the shortlist's "best bench" could be the weakest starter himself — bench is now the best PPG among players
  beyond the top N *by projection*; (3) blank comparison cells now say why ("no games this season", "no v2
  projection for him this week"); (4) shortlist only from active NFL rosters (`roster_status = 'ACT'`, so no
  inactive-list or practice-squad adds); (5) the label's "6-pt" uses a non-breaking hyphen; (6) drift caption says
  "complete weeks". PO decision: the season bar needs two games (a one-game PPG is a box score, not a rate).
* Not done: shortlist columns are wide (horizontal scroll under ~1900 px); Players / Receivers / Data Status have no
  league selector and therefore no label (by design).


### U-10 2026-09-29 — scoring summary line

* `dim_league_season.scoring_label` (SQL, from `num_teams`, `roster_positions`, `league_type`, `scoring_settings`):
  dynasty "12-team superflex dynasty · full PPR · 6-pt pass TD · yardage bonuses" (all six seasons), League of Scrubs
  "10-team redraft · half PPR · 4-pt pass TD" (all three). Rules in `docs/DATA_MODEL.md`; synthetic rows checked the
  other branches (0.25 PPR, standard, 2QB, TE premium 0.5, missing num_teams / pass_td).
* Sidebar (`perspective()`): the label is a caption under the League selector on every page that has one (10 of 13;
  Players, Receivers and Data Status have no league selector and were not touched). On a non-reference league the
  one-line "NFL research pages use reference scoring (League of Scrubs)" notice stays; the key-by-key diff moved into
  a collapsed expander "Scoring differences vs the reference league". The label is read via `to_jsonb(d) ->>
  'scoring_label'`, so page code pushed before the hosted marts are synced shows no label instead of failing.
* Tests: `not_null_dim_league_season_scoring_label` PASS; `assert_scoring_label_describes_leagues` PASS (negative
  control with the expectations swapped returns 2 rows). `dbt build --select dim_league_season+` PASS=76 WARN=2
  ERROR=0 (78 nodes; the same two warnings, 6 and 7 rows). `pytest` 25/25, `ruff` clean. Headless check 26/26 runs,
  0 exceptions. Playwright (Team Hub, both leagues): label shown, expander closed by default, diff visible only after
  a click; no page errors. Validated on the sandbox clone `league_lab_u10`, not the Mac.
* Open: at the default sidebar width the dynasty label wraps onto two visual lines (the break falls inside "6-pt").
### U-11 2026-09-29 — waiver shortlist ("Adds worth a claim")

* **Built** (plan Iteration 9, U-11): Waiver Wire section above the free-agent table for the selected roster (whole-league
  view: a one-line hint). Page SQL, one query (`SHORTLIST_SQL`, gsis_id joins): per position the league starts (DEF
  skipped; K only where started), N = starting slots (SUPER_FLEX counts as QB; FLEX types ignored); **this week** = free
  agent's v2 `proj_points` for `next_week_info()` vs the roster's N-th best *playable* projection (Out / Doubtful / IR
  are not starters, the Rankings rule; IR-slot players left out); **season** = free agent's PPG vs the (N+1)-th best PPG on
  the roster. Free agents: `is_free_agent`, not Out / IR (injury or NFL RES). Up to 3 per position that clear a bar (both
  bars first, then projection); text columns state both comparisons; Proj / Floor (P10) / Ceiling (P90) / PPG / injury
  shown. Nothing clears → "Nothing on the wire beats what you have at <POS>."; no bar evaluable (K: no v2 kicker model and
  no bench K) → "Nothing to compare at K: …". Free-agent table: new `proj_v2` column, default *Rank by* "Projection v2
  (week N)"; all earlier rankings and filters kept. Columns registered in `app/lib/table.py` (`# ---- U-11 waiver
  shortlist`). No new mart: a mart downstream of projections would lag a day, because `scripts/refresh.sh` rebuilds only
  `mart_player_week_projections` after `league-lab project`.
* **Evidence** (`league_lab_u11`, week 3 next): dynasty team 1 → 4 rows (WR Ryan Miller; TE Michael Mayer, Mike Gesicki,
  Evan Engram), "Nothing on the wire beats…" at QB and RB, no K; League of Scrubs team 2 → 5 rows (2 WR, 3 TE), QB/RB
  captions, K "Nothing to compare". Every roster in both leagues (22) at weeks 3, 4, 99 and none: ≤ 3 per position, every
  row clears a bar, no K on the dynasty, dynasty max 8 rows. Headless page check 26/26 with 0 exceptions; `pytest` 25/25;
  `ruff` clean; Playwright walk of both leagues (team selected + whole league): 0 exceptions, no "None" in the shortlist,
  default rank "Projection v2 (week 3)", table sorted by it; console only Streamlit's `/<page>/_stcore/*` 404 probes.
* **Open**: 40 of the 124 week-3 rows (all rosters) qualify only on a one-game PPG (labelled "1 game"); a ≥ 2-game rule
  for the season bar is Andrew's call. Kickers get no "this week" comparison until v2 projects K. Only 18 of the 124
  rows clear the week bar: in week 3 the free-agent pool rarely out-projects a starter.
### M-06 2026-09-29 — drift monitor (branch `dev/M-06`)

* **Built**: `projections.drift()` / `score_drift()` score the live v2 board's played weeks like the backtest
  (players who played and are rankable; `proj_points` vs `points_actual` in the league's scoring; `_spearman`,
  `_hit_rate`, `TOP_N`, 8-player minimum) into `ops.projection_drift` (league × season × week × position, plus
  `games_played / games_scheduled` so a week in progress is visible). Called at the end of `league-lab project`
  (a failure there is logged, never fatal to the projections) and on its own as `league-lab drift`. View
  `mart_projection_drift` (complete weeks only, next to the backtest's `v2_points` means). Rankings, v2 only:
  strip "How the model is doing this season" above the backtest.
* **Evidence** (clone `league_lab_m06`, after a fresh `league-lab project`): 18 rows for 2026 — weeks 1–2 every
  position in both leagues (16/16 games), week 3 WR only (1/16 games, 10 players; QB/RB/TE under 8). Season means
  (League of Scrubs, 2 weeks vs backtest 2021–2025): Spearman QB 0.430 vs 0.542, RB 0.675 vs 0.661, WR 0.537 vs
  0.610, TE 0.558 vs 0.554; coverage QB 75% vs 78%, RB 82% vs 80%, WR 80% vs 81%, TE 78% vs 81%. Dynasty: QB 0.402
  vs 0.534, RB 0.688 vs 0.663, WR 0.553 vs 0.625, TE 0.570 vs 0.571. Hand check, week 2 WR League of Scrubs:
  SQL average-rank `corr()` 0.5423364769 = stored 0.5423364769 = `scipy.stats.spearmanr` (144 players).
  `pytest` 29/29 (4 new in `tests/test_projection_drift.py`), `ruff` clean, dbt view + 4 tests PASS, headless
  26/26 runs 0 exceptions, browser check of the strip on both leagues.
* **Found on the way**: the clone's stored 2026 projections (fitted 2026-09-26 23:53 UTC, i.e. on the Mac before
  S-01a) and a refit here differ in 19,820 of 19,822 rows, while two consecutive refits here are identical. Cause not
  isolated — another platform, and S-01a moved `prev_snap_pct` by ≤ 4.4e-16; either can move the trees. Effect on the
  drift is small but visible (dynasty week 1 QB Spearman 0.309 → 0.328, League of Scrubs week 1 WR 0.521 → 0.532).
  So past weeks' projections are not a kickoff snapshot; the drift scores the board as it stands (METRICS.md § Drift).
* **Open**: no `metric_registry.csv` row for the drift metrics (seeds out of bounds); freezing played weeks'
  projections at kickoff would make the drift exact — a separate task.

## Wave B (Iteration 9b)

### B1 2026-09-29 — exact lineup service (branch `dev/B1`)

* **Built**: `src/league_lab/lineup.py` — `solve(players, slots)`: maximum-weight bipartite matching
  (`scipy.optimize.linear_sum_assignment`) of players to the league's starting slots (`SLOT_ELIGIBILITY` on Sleeper
  `fantasy_positions`; BN/IR/TAXI dropped, IDP reported); each player at most once, empty slots allowed and reported,
  unplayable players listed with the reason, locked players kept in their slot; returns lineup, total, bench (value
  order) and per filled slot the **margin** = total − best total with him removed (re-solved). `lineups(conn, season)`
  (CLI `league-lab lineups`; called at the end of `project()` after `drift()`, failure logged, not fatal) writes
  `ops.lineups` (one row per starting slot / bench player / unplayable player per league × season × week × roster ×
  proposed|realised) and `ops.lineup_totals` (one row per lineup: value, bench value, weakest slot and margin, counts,
  `inputs_fingerprint`); view `mart_lineup_recommendation` (proposed lineup with names, margins, weakest slot,
  `realised_optimal`); Makefile `project` / `refresh.sh` select it. Design, sources and limits in `docs/METRICS.md`
  § Lineup value and `docs/DATA_MODEL.md`.
* **Decisions** (PO to confirm): (1) the realised optimum uses **Sleeper's points for every position**, not the
  projections mart's `points_actual` for QB–TE as specified — `points_actual` drops 2-pt conversions and long-TD
  bonuses (28 rostered player-weeks exactly 2 short in weeks 1–2), so it would sit below Sleeper's max points by
  construction; (2) `lineups()` reads `ops.projections` (+ features for status), not `mart_player_week_projections`,
  because inside `project` that mart still holds the previous refit (values rounded as the mart rounds); (3) Sleeper
  publishes max points only per roster-season, so the error test compares each roster-week with
  `mart_league_optimal_lineup` (its weekly reconstruction, = ppts for all 22 rosters in 2026) and skips roster-weeks
  whose Sleeper points changed since the solve (fingerprint), so a stat correction between the nightly `dbt build`
  and `project` cannot fail the night; (4) `lineup_margin`, not `margin`, in the mart (`margin` is the matchup margin
  in the registry). **Accepted by the PO 2026-09-29.**
* **Evidence** (clone `league_lab_b1`, 2026 weeks 1–18, weeks 1–2 scored, week 3 fully kicked off at run time):
  `league-lab lineups` → 9,048 rows / 440 roster-weeks (396 proposed, 44 realised) in 1.1–1.3 s (solver 0.2–0.4 s; a
  first cold run 3.3 s); week 4 for all 22 rosters 25 ms. End to end: `league-lab project` (refit 39 min here, CPU
  shared with another worktree's refit) logged "lineups written … 1.30 s" after the drift; then the Makefile line
  `dbt build --select mart_player_week_projections+ mart_projection_backtest+ mart_lineup_recommendation+` PASS=23, and
  all 7,096 projection-valued lineup rows equal the rebuilt `mart_player_week_projections.proj_points` exactly.
  `dbt build --select mart_lineup_recommendation+ assert_exact_lineup_dominates_greedy` PASS=11; source tests PASS=4.
  Negative controls: realised total −1 → FAIL 1; same row with a changed fingerprint → skipped (PASS); realised row
  deleted → FAIL 1 (coverage). Exact vs greedy on all 1,384 scored roster-weeks 2021–2026 (ad hoc, not persisted):
  1,367 equal, 17 higher (13 a negative scorer left out, 4 Travis Hunter DB/WR at WR), 0 lower; the Hunter weeks close
  the 2025 greedy-vs-ppts gaps (League of Scrubs roster 6 −9.70 — not "a bench defense" as noted above — and dynasty
  roster 11 −17.30 → 0). Only 2023 dynasty roster 4 (−3.05) stays below Sleeper, as the greedy does. 2026 season to
  date: exact = ppts for 21 of 22 rosters, League of Scrubs roster 4 +1.00 (a −1 DEF left out).
* **Sanity reads** (after the sandbox refit; the Mac-fitted projections the clone came with gave the same shape, e.g.
  dynasty roster 1 week 4 = 131.75): dynasty roster 1 week 4 = 130.26 — QB Allen 32.32 (margin 22.47), RB Cook 17.86
  (8.01) / Henderson 10.83 (0.98), WR Collins 16.15 (6.30) / Watson 14.28 (4.43), TE Goedert 7.33 (0.53), FLEX Tucker
  10.00 (**0.15**, weakest; Monangai 9.85 first on the bench), SUPER_FLEX Hurts 21.49 (11.64); bench lineup 50.48;
  A.J. Brown / Tyson IR slot, Singleton / Meyers / Strand taxi, Sampson NFL IR. Same roster week 2 realised 168.70 =
  Sleeper max for the week (started 146.40); weeks 1–2 386.65 = Sleeper ppts 386.65. Superflex: dynasty roster 5
  (The72Repeat) week 4 starts RB David Montgomery 11.66 at SUPER_FLEX over QB2 Kyle McCord 9.17 (margin 0.20); a
  non-QB superflex in 1–4 of 12 dynasty lineups in each of weeks 4–18. League of Scrubs roster 2 (MacZaddy) week 4 =
  112.33: K McLaughlin 13.50 (`season_ppg`, = his league PPG over 2 games), DEF Kansas City 1.00 (`observed_ppg`, one
  scored week), weakest FLEX2 Croskey-Merritt 9.13 (0.06); QBs Young 17.75 / Shough 16.55 on the bench (1 QB slot).
* **Tests**: `tests/test_lineup.py` 179 (solver vs exhaustive enumeration incl. every margin: 1QB, 2QB, superflex ×3,
  mixed FLEX/REC_FLEX/WRRB_FLEX where the greedy order loses 19 → 11, dual eligibility, byes/injuries/no value, locks,
  fewer players than slots, K/DEF present/absent, negative values, 160 random rosters; the builder on a hand-made league
  with a scored week, an in-progress week with locks and a bye week; speed: median 0.3 ms per solve with margins on the
  real slot sets, < 5 ms asserted; DDL copies agree). `pytest` 208/208, `ruff` clean, `db migrate` OK, headless page
  check 26/26 runs, 0 exceptions (pages untouched).
* **Follow-up (PO decision 2026-09-29) — unvalued players fill otherwise-empty slots.** A playable, eligible player
  with no value yet (K / DEF Sleeper has not scored in this league, a K with no NFL id and no points, a QB–TE with no v2
  projection although his team plays) is carried at 0 with `value_source = 'unvalued'`, `reason = 'no value yet'`. The
  objective is now total first, filled slots second, valued starters third (tie weights 1e-9 / 1e-12), so he is seated
  only where nobody valued can play, never displaces a valued player (even one worth exactly 0), never changes the
  total; margin 0, never the weakest slot. `ops.lineup_totals.n_unvalued` (DDL in `lineup.DDL`, `db.py`, the mart's
  pre_hook, each with `alter table … add column if not exists` for existing tables; `db migrate` added it in place on
  the clone), exposed in the mart and registered in `table.py`; new mart test `lineup_unvalued_starter_counts_zero`,
  `value_source` accepts `unvalued`, the weakest-slot test skips unvalued rows. `is_empty_slot` now means nobody eligible
  (bye, Out, IR, taxi, nobody at the position). `scipy>=1.18.1` declared (`uv add scipy`; version unchanged).
  **Evidence**: week-4 empty slots before → after: League of Scrubs 5 → 0 (rosters 3 K Trey Smack, 4 DEF Carolina,
  7 DEF Minnesota, 8 DEF Cincinnati, 10 DEF New England now `unvalued` starters, value 0, margin 0, totals unchanged),
  dynasty 0 → 0; all weeks 101 → 31 and 2 → 2 (every remaining proposed empty slot has no eligible player: byes).
  `league-lab lineups` 8,978 rows / 440 roster-weeks in 1.0 s; dbt `mart_lineup_recommendation+` +
  `assert_exact_lineup_dominates_greedy` PASS=12, source tests PASS=4; exact vs greedy on 1,384 historical
  roster-weeks unchanged (1,367 equal, 17 higher, 0 lower). `tests/test_lineup.py` 262 (enumeration now checks all
  three objective levels; new fixtures: the only K unvalued, an unvalued WR behind valued WRs and behind a WR worth
  exactly 0, an unvalued RB filling an otherwise-empty FLEX next to a truly empty TE, a locked unvalued DEF; 240 random
  rosters — 44 seat an unvalued player, 34 bench one, 21 start a valued player worth 0; the builder fixture gained a WR
  without a projection seated at FLEX and an unvalued DEF behind a valued one). `pytest` 291/291, `ruff` clean,
  `uv lock --check` OK, headless page check 26/26, 0 exceptions.
* **Follow-up 2 (PO, from QA) — locks without a weekly list.** QA found that when Sleeper's weekly matchup list for the
  week in progress does not exist yet (a Thursday game before the next fetch, or a soft-failed fetch in CI), the
  fallback roster carried no starters, so players whose game had started were dropped to "game started (bench)"
  instead of locked. Fix: today's roster rows now carry `is_starter` / `slot` from Sleeper's `starters` array, read from
  `staging.stg_sleeper__rosters.starter_ids` (already stored, ordered, in `raw.sleeper_roster.starters`; no ingestion,
  dbt or column change); `lineup.starter_slots()` maps it onto `roster_positions` without BN / IR / TAXI (IDP slots
  keep their place, "0" = empty). The weekly list stays the first choice. **Evidence** (clone, `lineups(as_of=2026-10-02
  12:15 UTC)` = week 4's first kickoff, PIT @ CLE, + 12 h; no week-4 list): before (`8e6147d`) 0 locks, 26 "game
  started (bench)", 2 empty slots (League of Scrubs roster 6 DEF Pittsburgh 15.0, roster 10 TE), lineup values
  −0.37 … −17.39 on 6 rosters; after: **6 locked** (dynasty 8 WR2 Metcalf, 12 FLEX Boston; League of Scrubs 6 RB2
  Judkins, WR2 Boston, DEF Pittsburgh 15.0, 10 TE Freiermuth), 20 "game started (bench)", **0 empty slots, no roster
  loses a slot**; the 4 remaining deltas (−0.37 … −1.41) are the lock itself: Sleeper's own lineup benched a started
  Metcalf / Warren / Fannin, or (roster 6) locked Boston at WR2 pushing out a free Jameson Williams (9.61 − 9.14).
  At the real clock the output is byte-identical to `8e6147d` apart from run_at / as_of (md5 of both tables, 8,978 /
  440 rows; weeks 1–3 have lists, no week-4 game has started). Tests: `test_lineup.py` 265 (+3: the starters-array
  mapping with "0", IDP alignment and a short array; a week with no list: started starters locked in the array's
  slots, a started bench player blocked, a not-started starter moved, the "0" slot filled, total = locked + optimum of
  the rest = 62, and the pre-kickoff lineup; the weekly list beats the array). `pytest` 294/294, `ruff` clean, dbt
  lineup build PASS=12 (and the mart tests PASS=11 with the locked state loaded), source tests PASS=4, headless page
  check 26/26, 0 exceptions.
* **Open**: an unvalued K/DEF counts 0, so the lineup value understates those rosters until Sleeper scores him (R-13 is
  the real fix); a K / DEF with a negative season PPG would still lose to an empty slot (none in 2026 so far); in a
  realised lineup an empty slot can also mean "only a negative scorer" (League of Scrubs roster 4, week 1, DEF −1); no
  `metric_registry.csv` row (seeds out of bounds); the view and `ops.lineups` (≈9k rows) will be published by the
  hosted sync (every analytics view + `ops.*`).

### B5 2026-09-29 — decision record (branch `dev/B5`, clone `league_lab_b5`)

* **Built** (plan Iteration 9b, B5): a league-week's rows in `ops.projections` are rewritten by every refit until the
  week's first kickoff (`min(dim_game.kickoff_at)`) and never after (`projections.freeze_plan`, applied in one
  transaction by `_write_projections`; `project()` changed by one call). New columns `frozen_source` (NULL live /
  `kickoff` / `refit`) and `frozen_at` (= the kept rows' `fitted_at`, before the first kickoff; only for `kickoff`),
  added to an existing table by `db migrate`, the writer and the mart's pre-hook (`alter table … add column if not
  exists`). Design: a label on the table, not an `ops.projection_snapshots` table — the row a manager saw is the only
  row, so mart, page, drift and the hosted copy need no second copy (`docs/METRICS.md` § Decision record,
  `docs/DATA_MODEL.md`). **2026 weeks 1–3 hold refit values** (rows fitted 2026-09-26 23:53 UTC, after those weeks
  kicked off): labelled `refit`, kept unchanged, and the Rankings board and strip say "refit values". Drift reads the
  projection from `ops.projections` (the frozen rows) and writes `frozen_share`; `mart_projection_drift` carries the
  player-weighted `frozen_share` and `refit_weeks`. Freshness banner: "Injury report last loaded <when>; treat
  Questionable tags as stale." when the injuries partition's last content change (`mart_data_status`; nflverse's
  `date_modified` is empty since 2025) is before the last final game's date or more than 48 h before the next kickoff
  (`dim_game`, guarded by `missing_relations`), only when a game is within 7 days. dbt:
  `assert_frozen_projections_precede_kickoff` (kickoff times, not run times), `accepted_values` on
  `frozen_source`, `projection_drift_frozen_share_in_range`.
* **Evidence**: `db migrate` added the columns to the 19,822-row table. `league-lab project` run 1: weeks 1–3 kept
  (per league-week md5 of the value columns identical to the pre-B5 rows, 6/6) and labelled `refit`; weeks 4–18
  rewritten (16,268 rows). Run 2: whole-row md5 (every column, labels included) of weeks 1–3 identical to run 1, 6/6;
  weeks 4–18 rewritten (30/30 league-weeks new md5). Drift after B5 = M-06's numbers (18 rows, Spearman identical,
  MAE within 1e-15), `frozen_share` 0 everywhere. `dbt build --select mart_player_week_projections+
  mart_projection_backtest+` PASS=14 twice and `mart_projection_drift` is still a view afterwards;
  `source:ops.projections+ source:ops.projection_drift+ mart_projection_backtest+` PASS=16. Kickoff path simulated on
  the clone (clock set to week 4's first kickoff + 12 h): week 4 kept and labelled `kickoff`, `frozen_at` 2026-09-29
  18:22:23 UTC < kickoff 2026-10-02 00:15 UTC, weeks 5–18 rewritten, the freeze test PASS; negative control (one
  `kickoff` row moved past kickoff, one `refit` row given a `frozen_at`) → FAIL 2 naming both; real clock restored →
  every league-week byte-identical to run 2. `pytest` 36/36 (7 new in `tests/test_projection_freeze.py`: freeze rules,
  two in-memory refits byte-identical on played weeks, kickoff board kept, DDL copies agree and upgrade, `frozen_share`,
  banner flag on/off), `ruff` clean, headless check 26/26 runs 0 exceptions, Playwright on the dynasty Rankings page:
  strip "Scored on refit values: weeks 1 and 2 …", week 3 caption, banner flag shown by the data itself (loaded
  Sat Sep 26, next kickoff Thu Oct 1), gone with the threshold raised to 200 h (restored).
* **Open**: B6's nightly on an ephemeral Postgres must carry `ops.projections` forward between runs (e.g. restore it
  from the hosted copy before `project`), or every played week is re-created as `refit` each night. The freeze is per
  week: Sunday games' board is fixed at Thursday's kickoff (a per-game freeze is a refinement). For week 4 to be the
  first kickoff record on the Mac, B5 must be running before the Friday 2026-10-02 08:00 refresh. Hosted acceptance
  (the strip on Neon, "38+ relations" in the sync log) is Andrew's `make sync-hosted`; the sync will add
  `analytics.dim_game` (≈3k rows) because the banner reads it. `project` took 3 min alone and 36 min while two other
  model fits shared the sandbox's 2 cores. No `metric_registry.csv` row for `frozen_share` (seeds out of bounds).
### B6 — the nightly pipeline on GitHub Actions (2026-09-29; absorbs I-01)

* **Built**: `scripts/nightly.sh`, one script for every machine: migrate → restore state → replay the archive
  (`ingest sleeper --offline`, `ingest nfl --offline` for 2016…last season, then the current season) → live
  fetch (Sleeper; `ingest nfl --seasons <current>`, conditional requests) → `dbt build` → backtests (only when
  missing or from another `MODEL_VERSION`) → `project` → projection marts → drift → backup (`NIGHTLY_BACKUP=1`) →
  `sync_to_hosted.sh` (when `LEAGUE_LAB_HOSTED_ADMIN_URL` is set). Timing line per step, a summary table (also the
  Actions run summary), `::error` annotation naming the failing step, everything appended to `logs/nightly.log`.
  Failure policy: an ingest failure keeps going on the previous good data (the archive replayed a minute earlier)
  and fails the run at the end; a failure from the build on stops before anything is published. Same
  `.state/refresh.lock` as before, now with the holder's pid (a lock left by a killed run is cleared). `.env` is
  read without overriding the caller's environment. `NIGHTLY_SLEEPER_OFFLINE=1` skips the live Sleeper fetch.
* `scripts/refresh.sh` (launchd, `make refresh`) is now `NIGHTLY_BACKUP=1 scripts/nightly.sh`. Changes on the
  Mac: the archive replay runs first (4 s measured: every checksum matches, nothing reloads); a failed ingest no
  longer blocks the publish; a failed `project` still publishes with last night's projections (as before) but is
  fatal on a fresh database, where there is no earlier board.
  `make refresh` used to run `league-lab refresh` (no lock, no projections, no sync) although the runbook said it
  was `refresh.sh`; it now is. `make nightly` runs the CI path.
* `.github/workflows/nightly.yml`: `schedule` 11:37 UTC (07:37 EDT / 06:37 EST) + `workflow_dispatch` (inputs:
  `--full` history audit, recompute backtests); `concurrency: nightly` (queued, never cancelled); `ubuntu-24.04`,
  `services: postgres:17` (throwaway password, `--shm-size=1g`); `uv sync --locked`; `postgresql-client-17` from
  PGDG (the runner's 16 cannot dump a 17 server); `scripts/init_db.sql` against the service with generated role
  passwords (masked); `.env` for the service + the league-id secret (validated); the two hosted secrets reach
  `nightly.sh` as environment variables (python-dotenv expands `${...}` even inside quotes, so a `.env` line cannot
  carry every password); archive restore/save through `actions/cache` (key `league-lab-raw-v1-<season>-<content
  fingerprint>`, saved only when the fingerprint changed); artifacts `nightly-logs` and `dbt-run-results` (14 days).
* `scripts/init_db.sql` takes `-v db_name=…` (default `league_lab`; quoted with `%I` / `:"db_name"`), so the same
  script creates a worktree's or the CI service's database; re-running it where the roles exist changes nothing
  unless passwords are passed. `bootstrap.sh` passes `LEAGUE_LAB_DB_NAME`.
* **Two findings the fresh database exposed** (both would have blanked hosted pages on the first CI sync):
  (1) the backtests behind the Rankings scoreboards (`ops.backtest_results`, `ops.projection_backtest`,
  `ops.projection_importance`) are not derivable from the archive → `restore-state` copies them back from the
  hosted copy, recomputed only when neither has them; (2) `project` scores drift on the board *as last built*,
  which in a fresh database is empty → `drift` re-scores the just-published board when the season has no drift rows
  (on the Mac `project`'s own rows are kept, so M-06's semantics there are unchanged).
* **Evidence** (this sandbox: 2 CPUs shared with two other agents' builds, load average 4–8; Postgres 16 here, 17
  in CI). `league_lab_b6` created from nothing as the workflow does it (`init_db.sql -v db_name=league_lab_b6` with
  the `.env` passwords; a second run without passwords changes nothing; the shared roles and the other databases
  untouched). Hosted target `league_lab_b6_hosted`, owned by a CREATEROLE role holding ADMIN on `league_lab_app`
  (Neon's owner shape), `LEAGUE_LAB_HOSTED_ALLOW_LOCAL=1`, app password = the local one; dropped afterwards.
  Sleeper replayed from the archive (`NIGHTLY_SLEEPER_OFFLINE=1`), nflverse history replayed, current season live.

  | step | run A: fresh db, hosted empty | run B: fresh db, hosted from A (every CI night) | run C: `refresh.sh` on the loaded db (the Mac) |
  |---|---:|---:|---:|
  | migrate / restore-state | 1 s / 0 s (nothing to restore) | 1 s / 1 s (864 + 2,160 + 300 rows restored) | 1 s / 0 s (kept) |
  | replay-sleeper | 7 s | 3 s | 2 s |
  | replay-nflverse-history (2016–2025) | 1 m 12 s | 46 s | 2 s (all unchanged) |
  | replay-nflverse-current | 7 s | 4 s | 0 s |
  | fetch-sleeper | skipped | skipped | skipped |
  | fetch-nflverse-current (live) | 11 s (19 unchanged, 1 new) | 9 s | 9 s |
  | dbt-build | 8 m 38 s | 5 m 48 s | 2 m 39 s |
  | backtests | 15 m 50 s (recomputed) | 1 s (kept) | 1 s (kept) |
  | project / projection-marts / drift | 2 m 35 s / 27 s / 1 s | 2 m 38 s / 25 s / 2 s | 2 m 37 s / 6 s / 0 s |
  | backup / sync-hosted | skipped / 13 s | skipped / 10 s | 57 s (400 MB) / 9 s |
  | **total** | **29 m 23 s** | **10 m 09 s** | **6 m 44 s** |

  Every run: `Done. PASS=308 WARN=2 ERROR=0 SKIP=0 NO-OP=0 TOTAL=310` (the two known warnings, 6 and 7 rows, as on the
  Mac), projection marts `PASS=12`, sync `verified: all 38 page relations are on the hosted copy` (hosted copy
  319 MB; the app role reads it and cannot write). Drift: `project`'s own pass wrote 0 rows on the fresh database
  ("weeks none played"), the drift step then 24; on the loaded database `project` wrote 24 and they were kept. An
  earlier fresh run's first live fetch loaded week-4 data into 18 current-season partitions. Lock: a live holder
  → exit 3; a dead holder's lock is removed. `actionlint` 1.7.12 with shellcheck 0.11.0: 0 errors;
  `yaml.safe_load` ok; shellcheck clean on `nightly.sh`/`refresh.sh`; the workflow's secret/`.env` step run with
  stubbed `psql`/`uv` (good ids, missing, malformed, URL without password, no URL); the cache fingerprint is
  deterministic. `pytest` 29 passed, `ruff` clean.
* **Sandbox-only settings, not committed**: a `sitecustomize` that clears Python 3.13's `VERIFY_X509_STRICT` (this
  sandbox's TLS-intercepting proxy CA has no keyUsage extension; chain and hostname verification stay on) — the
  first attempt without it failed every live nflverse fetch with `CERTIFICATE_VERIFY_FAILED` and was stopped; and
  `OMP_NUM_THREADS=1` — a second attempt with default threads stalled in `backtest-v2` under the three-way CPU
  contention (first fit after 11 min) and was stopped; single-threaded, the whole recompute took 15 m 50 s.
* **Unresolved / only verifiable on GitHub**: the live Sleeper fetch (blocked here; ~9 league-seasons ≈ 400
  requests + the 5 MB player directory, estimated 1–2 min); the PGDG client install, `actions/cache` save/restore
  and the artifact uploads; the restore of the backtests from Neon (tested against the local hosted simulation
  only); real runner timings (this sandbox shared its 2 CPUs with two other agents' builds) and disk (the database
  is 3.4 GB + the 0.3 GB archive, inside the runner's ~14 GB).
  **B5 × B6**: the CI database is new every night, so frozen projections (B5) must be carried like the backtests —
  add B5's table to `STATE_TABLES` in `nightly.sh` (restored from the hosted copy before `project`), or every
  night's "first publication" is that night. A licensed routes file imported on the Mac is not in the archive.
  (The "last loaded" = replay time problem found in QA is fixed: follow-up below.)
* **Andrew**: merge to `main`, add the three secrets (HOSTING.md § 5), run it once by hand from the Actions tab,
  then retire the launchd job or take `LEAGUE_LAB_HOSTED_ADMIN_URL` out of the Mac's `.env` (one writer).

#### B6 follow-up 2026-09-29 — content time, not replay time (QA finding, MEDIUM)

* **Finding**: on a fresh database every partition's `ops.source_partition.loaded_at` was the replay time, so the
  CI-built copy said "loaded this morning" for files unchanged for days (nflverse `teams`: 2026-09-29 19:25 UTC vs
  the archive's 2026-09-26), B5's stale-injury flag could never fire there, and "sleeper loaded …" showed the replay.
* **Decision implemented**: `loaded_at` is the **content time**, the `fetched_at` of the bytes loaded
  (`manifest.record_manifest` writes `rec.fetched_at`, `now()` only without one). `http.fetch_to_archive` makes that
  one instant everywhere: an `--offline` replay returns the sidecar's `fetched_at` (the file's mtime without a
  sidecar: the curl-mirrored pbp history); a live download of new bytes stamps the download and writes the same
  instant to the sidecar; a 304, or a 200 with the archived bytes (Sleeper sends no 304; nflverse re-uploads under
  new ETags), keeps the archived `fetched_at`, leaves the file alone and records the check as `checked_at` in the
  sidecar (the Sleeper player directory's once-a-day guard now reads `checked_at`). **No new column**: "when this
  database last checked" already exists as `ops.load_manifest.started_at` (every attempt, unchanged ones included)
  → `mart_data_status.last_attempt_at`, shown next to `last_loaded_at` on Data Status. `mart_data_status`, the banner
  and the sync's "published through" line read `loaded_at` unchanged, so they now show content time. No dbt source
  has a `freshness:` config, so no test depends on the timestamp. A database loaded before this change keeps its old
  insert times until a partition's content changes (the CI copy is rebuilt every night, so it is right at once).
* `nightly.sh` (ingest section only; `restore_state`, the sync and the record steps untouched): a live fetch with no
  archive behind it (replay skipped: first run or lost cache) is now fatal, `FAILED: stopped here (no archive to fall
  back on: the failed partitions have no data)`, instead of "continued with the previous good data"; with an archive
  it still continues ("failed partitions keep the copy the archive replay loaded"). The loader's own line now says
  "whatever those partitions held before was kept (nothing, if they were never loaded)". The workflow's cache
  fingerprint ignores `*.meta.json`, so a night that only records checks does not save a new cache entry.
* `app/lib/ui.py` `freshness_banner`, caption only: "**nflverse** loaded Tue Sep 29, 4:53 PM ET", Eastern and
  labelled like the B5 warning under it (was unlabelled UTC `2026-09-29 20:53`).
* **Evidence** (`league_lab_b6` dropped and recreated with `init_db.sql`, `nightly.sh` with
  `NIGHTLY_SLEEPER_OFFLINE=1`, `OMP_NUM_THREADS=2`, quiet sandbox; hosted simulation created and dropped again):
  fresh night 19 m 35 s (dbt 5 m 50 s `PASS=326 WARN=2 ERROR=0 TOTAL=328`, backtests recomputed 9 m 53 s because the
  simulation was empty, project 2 m 01 s, sync `verified: all 40 page relations`, `published through: 2026-09-29
  20:34:18.278195+00` = the newest content, tonight's schedules download); a second night on the loaded database
  8 m 00 s (dbt 5 m 27 s, same PASS line, backtests kept). `mart_data_status.last_loaded_at` (UTC) vs the archive's
  `fetched_at`:

  | partition | archive `fetched_at` | fresh night | second night (loaded db) |
  |---|---|---|---|
  | sleeper `state` | 2026-09-26 10:33:15.032896 | 2026-09-26 10:33:15.032896 | 2026-09-26 10:33:15.032896 |
  | nflverse `teams` | 2026-09-26 02:40:38.704114 | 2026-09-26 02:40:38.704114 | 2026-09-26 02:40:38.704114 |
  | nflverse `injuries` (2026) | 2026-09-29 17:35:05.483554 | 2026-09-29 17:35:05.483554 | 2026-09-29 17:35:05.483554 |
  | nflverse `snap_counts` (2026; archived file removed before the run, so downloaded live) | — | 2026-09-29 20:34:17.896380 (tonight) | same |
  | nflverse `schedules` (changed upstream during the evening) | 2026-09-29 18:36:43 | 2026-09-29 20:34:18 (tonight) | 2026-09-29 20:53:32 (changed again) |

  `last_attempt_at` moved to each night's check (20:33–20:34, then 20:53) while `last_loaded_at` stayed put. The
  replica's "2026-09-26 03:06" for `teams` quoted in the QA note was itself that database's replay time; the
  archive says 02:40:38. pbp 2016 (no sidecar) shows its file time, 2026-09-26 13:48:37. Tests:
  `tests/test_content_time.py` (8: offline replay carries the sidecar time / the file time; a live download is now
  and a replay reproduces it to the microsecond; 304 and identical 200 keep the content time without rewriting the
  file; `record_manifest` writes the record's fetch time and moves nothing on an unchanged attempt; the nflverse
  loader end to end, offline and live, database calls stubbed; the ET caption). `pytest` 309 passed, `ruff` clean,
  headless check 26 renders (13 pages × 2 leagues), 0 exceptions. No-archive path: with an empty `data/raw/sleeper`
  and the blocked Sleeper API the night stopped at `fetch-sleeper` with the new line, exit 1.

## Next concrete actions

1. **Andrew (S-01a)**: review the commit, then `make build` on the Mac (≈2.5 min; the 08:00 nightly would do it too)
   and `git push` **before the next nightly** — the nightly publishes the new marts to Neon, and Community Cloud runs
   the page code from GitHub, so an unpushed commit leaves hosted pages showing per-league numbers under the old
   sidebar text. Then `make sync-hosted` if you want it live now. Optional: OK a `metric_registry.csv` bump
   (`expected_points`, `positional_strength` → 1.1, per-league note).
1b. **Next agent**: `docs/HANDOFF.md` → Iteration 9 in `docs/PROJECT_PLAN.md`: **U-10** (scoring summary line; the
   raw diff into an expander), then U-11 / U-12 / M-05 / M-06.
2. **Andrew**: reset the Neon owner password (it was pasted in chat) and update `.env`; optionally `LEAGUE_LAB_APP_PASSWORD` / `LEAGUE_LAB_FEEDBACK_URL` in the Streamlit secrets.
3. **Andrew (decisions)**: O03 refresh time, O05 backup destination, review of the Edge pages (U04), acceptance (H03).
4. **Next engineering** (Andrew's call): R-07 an ML challenger on the same harness (only kept if it beats the baseline);
   R-08 rest-of-season projections + lineup optimizer; P2-14 defensive participation for CB context; Phase 3 ops hardening; Phase 4 hosting.

## Source-license notes

nflverse (attribution), dynastyprocess crosswalk (MIT), ffverse/ffopportunity (MIT), Pro-Football-Reference
data via nflverse (see nflverse terms), Sleeper API (public read-only). FTN (Phase 2) CC-BY-SA 4.0.
