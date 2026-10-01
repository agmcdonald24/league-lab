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

### PO merge and QA — round 1 (B1 + B5 + B6), 2026-09-29

* Three Opus developers in parallel again (worktrees `wt-b1` / `wt-b5` / `wt-b6`, branches `dev/B1` / `dev/B5` /
  `dev/B6`, clones `league_lab_b1` / `_b5` / `_b6`) off `0fda8e7`. Merged into `integration/wave-b`: conflicts in
  `db.py` (both migrations kept), `table.py` (both registry blocks), CHANGELOG / STATUS ("keep both"), `refresh.sh`
  (B6's version: it execs `nightly.sh`). Cross-branch fixes by the PO: `nightly.sh` restores `ops.projections` and
  `ops.projection_drift` before `project` (B5 × B6: a fresh CI database would otherwise refit every played week) and
  builds `mart_lineup_recommendation+` (B1 × B6). B1 accepted as designed: Sleeper's observed points for realised
  lineups (`points_actual` omits 2-pt conversions and long-TD bonuses), `ops.projections` as the source,
  `mart_league_optimal_lineup` as the max-points oracle, `lineup_margin`. PO decision on the empty K/DEF slots: a
  playable player with no value fills an otherwise-empty slot at 0 (B1 follow-up 1, `8e6147d`; `uv add scipy`).
* Verified on the main database before QA: `pytest` 298, `ruff` clean, `project` kept weeks 1–3 frozen (labelled
  `refit`) and rewrote 4–18, 8,978 lineup rows / 440 roster-weeks, zero empty K/DEF slots in week 4, drift view
  survives the `+` build, 26 page runs × 2 leagues with 0 exceptions.
* One QA agent (Opus) on the integrated build: two fresh-database `nightly.sh` runs against a hosted simulation
  (9m31s fresh with the record restored, 5m11s loaded; exit 0; weeks 1–3 byte-identical to the main database 6/6
  after each), the week-4 kickoff path (week 4 kept and labelled `kickoff`, `frozen_at` before the Oct 2 00:15 UTC
  kickoff, the freeze test's negative control caught 5/5 corruptions), four week-4 lineups re-solved by brute force
  independently of `lineup.py` (totals, filled slots, weakest slot and every margin match), realised lineups vs
  Sleeper's max points 21/22 equal + 1 higher (the −1 defense), all 33 remaining empty slots are byes / IR / taxi,
  Playwright on both leagues (captions, the "Kickoff board" column, the banner), the sync's local-cluster guard and
  the workflow desk-checked (action tags exist; actionlint / shellcheck clean). Findings and what was done:
  1. **HIGH** — `restore_state` treated an unreachable hosted copy as empty, and the sync then published the refit
     board over the record → for the two record tables "cannot read" and "copy failed" now stop the night; a
     reachable copy that has lost the record is repaired from the archive (`save-record` writes both tables to
     `data/raw/record/` after every `project`, so they ride the Actions cache); only "empty everywhere" starts a new
     record, with a CI warning. Exercised all five paths by hand (`scratchpad/state_harness.sh`).
  2. **HIGH** — Neon was the only copy of the record and the sync dropped `ops` before restoring → `ops` (a few MB)
     is now dropped inside the restore transaction (a failed restore rolls back); the marts still swap outside it
     (Neon's 0.5 GB cannot hold two copies). Plus the archive copy above.
  3. **MEDIUM** — locks needed Sleeper's weekly list; without it started starters were dropped instead of locked
     (week 4 at kickoff + 12 h: 0 locks, 2 rosters lost a slot, values down to −17.5) → B1 follow-up 2 (`8fa1755`):
     today's roster carries `is_starter` / `slot` from Sleeper's ordered `starters` array (`stg_sleeper__rosters
     .starter_ids`); 6 PIT/CLE starters locked, no roster loses a slot, real-clock output unchanged.
  4. **MEDIUM** — projection v2 was not reproducible on identical inputs (unordered training scan → the
     early-stopping validation split moved; RB/WR/TE values differed up to 1.48 points, only 166–193 of ~590 rows per
     week identical) → `load_frame` orders the rows; two consecutive `project` runs are byte-identical on all 36
     league-weeks. MODEL_VERSION unchanged (same model, now deterministic).
  5. **MEDIUM** — the stale-injury flag could never fire on a CI-built copy (replay time ≠ report time) → B6
     follow-up (`62e31f9`): a partition's `loaded_at` is the content time (the archive sidecar's `fetched_at`; a 304
     keeps it), the freshness caption is ET; the flag now behaves the same on the runner and the Mac.
  6. LOW — a soft `project` failure published empty lineups from the runner → `ops.lineups` / `ops.lineup_totals`
     restored too, so that night republishes last night's board with last night's lineups; HOSTING's failure table
     updated. LOW — the sync let `.env` override the caller's environment (`LEAGUE_LAB_DB_NAME=x` built x, published
     the `.env` database) → the environment wins, as in `nightly.sh`. LOW — the app password was interpolated into
     SQL and the sync log is a CI artifact → quoted psql variable. LOW — local-cluster guard without a port (QA fixed,
     `5b24701`). LOW — a failed live fetch with no archive claimed "previous good data" → stops the night (B6
     follow-up).
* Left open (round 2 or later): an unvalued K/DEF counts 0 until R-13; a K/DEF with negative season PPG loses to an
  empty slot; the freeze is per week (Sunday games fixed at Thursday's kickoff); `metric_registry` rows for lineups /
  `frozen_share` (seeds); pg_dump's `set_config` / `setval` noise in the sync log; the freeze test's "more than one
  label" branch returns every row of the league-week. Only verifiable on GitHub: the live Sleeper fetch, the PGDG
  client install, cache save/restore, artifacts, masking, Neon (must be Postgres 17: pg_dump 17 emits
  `SET transaction_timeout`; the Mac's pg_dump 17 already syncs to it, so it is), runner timing and disk. If the
  repository were public, GitHub disables scheduled workflows after 60 days without activity (off-season).

### PO merge and QA — round 2 (B2 + B3 + B4), 2026-09-30

* Three Opus developers in parallel off `04a4111` (worktrees `wt-b2` / `wt-b3` / `wt-b4`, clones
  `league_lab_b2` / `_b3` / `_b4`, ports 8521–8523), each with the shared round-2 brief (answer-first cards,
  phone width, one projection, plain words, page ownership). Merged into `integration/wave-b2`: conflicts
  only in `table.py` (both appended blocks kept), METRICS and STATUS ("keep both"). PO fixes: `ops.waiver_moves`
  added to the nightly's restored state (a soft `project` failure republishes last night's moves with last
  night's lineups); the U-11 registry entries `claim_week` / `claim_season` / `compared_with` removed (the
  shortlist is gone). Decisions confirmed as delivered: B2's lineup gain solved at page time (scipy in
  `app/requirements.txt`), buy-low sorted by 4-week fit, the "Inherited" label; B3's "unknown is not zero"
  (an unvalued starter keeps his slot, an unvalued player is never a drop), rest-of-season points as the drop
  tie-break, free-agent defenses not evaluated (R-13); B4's week from the clock, the alternative = whoever the
  re-solve brings in (both named on a slide), no card for a starter nobody can replace.
* Verified on the main database: `pytest` 530, `ruff` clean, migrate, `mart_league_acquisitions+` and the
  projection/lineup/waiver marts built, `project` writes lineups then waiver moves, headless check on every
  page × both leagues (+ the Player page by id) with 0 exceptions.
* One QA agent, phone-first (iPhone 14 emulation, 390 × 844, both leagues as Andrew's rosters), 12 minutes:
  no sideways scroll on any of the 7 walked pages; Team Hub, Waiver Wire, Trade Finder and Matchups show a card
  before any table; the league/team selection survived every hop on the phone layout (Andrew's report not
  reproduced — a hypothesis: player links open a new tab, and in that new session switching league has no
  remembered team); every card matches its mart (Home = Matchups first card = `weakest_slot` / margin; Waiver
  card = `mart_waiver_moves` rank 1; Team Hub closest call = the same) for both rosters; the TE1 / RB2
  projection is the same number on Home, Player, Team Hub and the mart (9.47 Kittle, 10.73 Hampton); no jargon
  on any card. Findings: (HIGH) Rankings' default week and Team Hub's opponent column take the week from
  `mart_nfl_calendar` (3 on a database loaded before Monday night's game was final) while the cards take it
  from the clock (4) — they agree once a nightly has marked the last game final, so the live app is
  consistent, but it is one week rule too many → U-13 makes one `current_week()` helper; (MEDIUM) Matchups'
  defender table (14 columns) and defense-vs-position tables (6) sit outside expanders; League Intel opens on a
  23-column standings table with no card → U-13 / U-16; (LOW, fixed by the PO) the injury banner took ~300 px
  on a phone and pushed Home's first card below the fold → one sentence; four jargon phrases ("margin",
  "re-solved") reworded. (LOW, open) player links open a new tab (Streamlit's LinkColumn); browser Back is
  imprecise after page hops (query-param rewrites add history entries); the Player page leads with Usage, the
  projection is second.
* Known gaps carried into Iteration 10 (U-13): player names on Team Hub / Trade Finder (B2's `narrow_table`,
  column `player`) and the waiver cards' claim/drop columns are not links yet (B4's `show()` link needs
  `player_name` + `gsis_id`); Receivers / Players / League tables need `gsis_id` in their SELECTs for the
  same reason; the Matchups caption still takes its week from `mart_nfl_calendar` while the cards take it
  from the clock (they agree after a nightly); `metric_registry` rows for roster value, lineup gain, trade
  fit, weekly/horizon gain (seeds).

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

### B2 2026-09-30 — roster value and league rankings (branch `dev/B2`, clone `league_lab_b2`)

* **Built** (plan Iteration 9b B2 + the review's acquisition finding): four views on the B1 lineup service —
  `mart_league_roster_horizon` (every current roster's proposed lineup rows for this week and the next three, with
  names, eligibility, margins, the replacement of each starter, the best starter per slot type and the acquisition
  label), `mart_league_roster_value` (per roster: this week's lineup value, weakest slot + margin + replacement,
  bench value, 4-week horizon value and its worst week), `mart_league_roster_rankings` (every roster ranked on lineup
  value, horizon and depth, one row per measure, each naming its horizon), `mart_league_roster_slot_strength`
  (starter strength per slot type) — and the table `mart_league_acquisitions` (how each rostered player joined his
  roster, across the whole chain for a dynasty). `src/league_lab/roster_value.py` (`RosterBoard`: rebuild a
  roster-week from the published rows, `gain` / `loss` / `trade_candidates`) serves Trade Finder and the weekly pack.
  Team Hub, Trade Finder and League Intel's roster section rewritten phone-first; `mart_league_positional_strength`
  is read by no page or pack any more (kept as a mart; the sync stops publishing it because nothing references it).
  `reports.py` team brief: "Your positional strength" / "Trade fits" replaced by roster value + rank, closest call,
  starter strength, buy-low / sell-high by lineup gain; keeper facts carry the chain acquisition. Definitions:
  `docs/METRICS.md` § Roster value; models: `docs/DATA_MODEL.md` § Roster value (B2).
* **Design choices** (PO to confirm): (1) starter strength is **read** from `ops.lineups.margin` (B1 already stores
  lineup − fresh solve without him), not re-solved; (2) the replacement ("Tucker over Monangai") is the bench player
  worth value − margin, from the alternating-path property of the matching, found in SQL by a window over integer
  cents (no self-join: the first version took 4.4 s, now < 50 ms per view); (3) Trade Finder's lineup gain is solved
  at page time with `lineup.solve` (0.24 s for the dynasty's 202 candidates × 4 weeks, cached 10 min), because a
  gain for every player × every other roster × 4 weeks would be ~20k solves a night for lists nobody opens —
  `app/requirements.txt` gains `scipy==1.18.1` (the hosted app installs from it; B3/B4 may add the same line);
  (4) "this week" = the first REG week with a kickoff after `now()` (a view: it moves on without a rebuild), horizon =
  this week + 3; (5) acquisition = the latest move into this roster (its current stint), whole chain for a dynasty,
  current season for redraft/keeper; a roster taken over by a new manager marks older players **Inherited** — owner
  *and co-owners* count (Andrew's dynasty roster 12 has had him as owner or co-owner every season since 2021, so
  nothing on it is "inherited"; PhillyRoc took over roster 9 in 2024: 4 players inherited); (6) no `--select`
  appended: the four views declare `-- depends_on: mart_lineup_recommendation`, so the existing
  `mart_lineup_recommendation+` in the Makefile `project` target and nightly `projection-marts` rebuilds and tests
  them (`dbt ls` confirms); the acquisitions table is built by the main `dbt build`.
* **Evidence** (clone, this week = 4, horizon 4–7, both leagues):
  - Rebuilding every roster-week of the horizon from the published rows reproduces `ops.lineup_totals.lineup_value`
    to the cent 88/88; every one of the 773 unlocked starters' margins equals lineup value − a fresh `solve()`
    without him to the cent; the replacement named by the mart is the player who enters that re-solve 773/773
    (`scratchpad/waveB_r2/b2/verify_board.py`). By hand: dynasty roster 1 (130.26) without Tre Tucker 130.11 → 0.15
    = his FLEX margin, Monangai enters; without Jalen Hurts 118.62 → 11.64 = his SUPER_FLEX margin; Andrew's roster 12
    (109.69) without Kenny Gainwell 109.24 → 0.45 (Emanuel Wilson enters) = the card "RB2, Kenny Gainwell over
    Emanuel Wilson by 0.45".
  - **QB3 in superflex**: roster 12 starts Bo Nix 20.60 (QB) and Michael Penix Jr. 19.81 (SUPER_FLEX), Aaron Rodgers
    17.86 and Malik Willis 17.28 on the bench: lineup 109.69 without Willis, and without both, change +0.00. Adding
    Kirk Cousins (16.19, a bench QB of roster 2) to roster 12: +0.00; to The72Repeat (roster 5, whose SUPER_FLEX is RB
    David Montgomery 11.66 and QB2 McCord 9.17 sits): +4.53 = 16.19 − 11.66. Removing The72Repeat's QB2/QB3 (McCord,
    Sanders): 126.86 → 126.86. The old mart counted SUPER_FLEX as a QB slot (roster 5 "QB starters" = Purdy + McCord).
  - **WR who improves FLEX**: dynasty roster 1 starts WR Collins 16.15 / Watson 14.28 and Tre Tucker 10.00 at FLEX;
    adding Tee Higgins (WR 13.25, roster 6) → 133.51, +3.25 (seated at FLEX, Tucker out) = his margin in the new
    lineup; George Pickens 13.10 → +3.10. A position-by-position count of the two WR slots (the old mart) sees 0.
    Unit test: a WR better than WR2 takes WR2 and pushes WR2 into FLEX, gain 18.00 − 10.00.
  - **Trade Finder lineup gain**: Javonte Williams (RB 13.88, roster 7's RB1, margin 2.10) gives Andrew's roster 12
    **+6.34** in week 4 (109.69 → 116.03, Gainwell out) and costs roster 7 **2.10** (128.59 → 126.49, Travis Kelce
    comes in): fit +4.24; weeks 4–7 +28.11 (6.34, 6.78, 7.87, 7.12) vs 16.55 (2.10, 6.91, 4.13, 3.41): fit +11.56.
    Card on the page (dynasty, team 12): "Buy low: ask The72Repeat (jnaumann1011) about Quinshon Judkins (RB) … adds
    +3.9 to your week-4 lineup and costs them 0.0; over weeks 4–7: +15.5 for you, 1.3 for them (fit +14.2)".
  - **Every rank names its horizon**: `mart_league_roster_rankings.horizon` not null (test); Team Hub "10th of 12 in
    the league (week 4)", "(weeks 4–7)"; League Intel columns "Week 4", "Weeks 4–7", "Depth · week 4"; the pack's
    table has a `horizon` column.
  - **Acquisition across the chain** (Sleeper raw log → page): Amon-Ra St. Brown — draft pick 21 (round 2) of the
    2021 rookie draft `716476861135253504` by roster 12 → "Rookie draft 2021 · 2.09"; George Kittle — trade
    `956061477281034240` (3-team, created 2023-04-24, processed 2023-04-25, adds 4217→12, drops 4217→9, roster 9 =
    Kuch4120 then) → "Trade 2023 offseason · from Kuch4120"; Aaron Rodgers — drafted 2021 by roster 3, to 12 in 2022
    wk 3, to 9 in May 2024, back in trade `1223826061477814272` (2025-05-03, adds 96→12, drops 96→9) → "Trade 2025
    offseason · from PhillyRoc"; also Bo Nix → "Trade 2025 offseason · from Chargers2017" (2025-09-03). The old
    Team Hub showed all four as "Waiver / free agent" (it read the 2026 draft only): 200 of the dynasty's 291
    rostered players were acquired before 2026 and all 200 showed "Waiver / free agent". Every rostered player has
    an acquisition row (448/448; 0 without an event), none has a later move off his roster (both dbt tests).
  - dbt: `--select mart_league_acquisitions+ assert_every_rostered_player_has_acquisition
    assert_acquisition_starts_current_stint` PASS=36 (5 models, 31 tests); the Makefile / nightly projection-marts
    select `mart_player_week_projections+ mart_projection_backtest+ mart_lineup_recommendation+` PASS=49 (now
    includes the four views). Negative controls: Kittle's acquisition row deleted → FAIL 1; Godwin's dated to his
    2021 draft → stint test FAIL 2 (the 2022 trade away: a drop and an add elsewhere); one `ops.lineup_totals` value
    +1 → reconcile test FAIL 1; all restored (lineup totals md5 identical), PASS=36 again.
  - `pytest` 439 passed (+130 in `tests/test_roster_value.py`: rebuild to the cent, margin = fresh solve, QB3 adds
    0, superflex by eligibility, WR through FLEX, fit, taxi/Out/locked, horizon, `trade_candidates`, and the SQL
    replacement rule vs the solver on 120 random rosters), `ruff` clean, headless page check 26 runs, 0 exceptions.
    Views: horizon 42 ms, value 50 ms, rankings 49 ms, slot strength 28 ms (whole league).
  - Playwright (Streamlit on 8521, dynasty team 12 and League of Scrubs team 2): `scratchpad/waveB_r2/b2/shots/`
    `{team_hub,trade_finder,league_intel}_{dynasty,scrubs}_{390,1300}.png` (first screen) and `…_full.png` (whole page
    with the roster / buy-low expander open); at 390 px the page never scrolls sideways (scrollWidth = clientWidth);
    the tables pin the first column and keep the decision columns (value, margin / gain, fit) on screen.
* **Open**: Josh Jacobs has no v2 projection in weeks 4–7 (unvalued, 0) on two rosters — a projection-side gap, not
  B2's; a takeover inside a season is dated to that season's start (Sleeper keeps one owner per season); the
  replacement's name is arbitrary between two bench players of exactly equal value (same total); Trade Finder
  ignores roster size and what is sent back (T-01); no `metric_registry.csv` rows (seeds out of bounds) — would add
  `roster_lineup_value`, `roster_horizon_value`, `roster_bench_value`, `starter_strength`, `lineup_gain`,
  `trade_fit` (v1.0, grain roster / roster × slot type / player × roster).
### B3 2026-09-30 — waiver engine (branch `dev/B3`, clone `league_lab_b3`)

* **Built** (plan Iteration 9b, B3, with the round-2 amendments): `src/league_lab/waivers.py` —
  `waiver_moves(conn, season, as_of)` evaluates, for every roster of both leagues, every free agent on an active NFL
  roster (`mart_player_availability`: free agent, `ACT`, not Out / IR, a position the league starts) × every droppable
  player (not IR slot / taxi / locked / without a value), plus "no drop" when the roster has an open spot, by re-solving
  the B1 lineup after the move minus before on the players and values of `ops.lineups` (the add valued by B1's own
  `_proposed_player`: v2 `proj_points` in the league's scoring, K season PPG, byes / Out / started games) for the
  **decision week** (first week with a game still to kick off: week 4) and the horizon weeks 4–7. Writes
  `ops.waiver_moves` (moves with weekly gain > 0 → *start now*, else horizon gain > 0 → *cover*; one `nothing` row per
  roster without a move); view `mart_waiver_moves` (names, `lineup_value` from `mart_lineup_recommendation`,
  `inputs_current`, `on_current_lineup`). Called at the end of `league-lab project` after the lineups (+1 import, +1
  call in `projections.py`; logged, never fatal) and as `league-lab waivers [--verify LEAGUE:ROSTER]`. Waiver Wire
  page rebuilt answer-first (below). Definitions in `docs/METRICS.md` § Waiver moves, tables in `docs/DATA_MODEL.md`.
* **Decisions** (PO to confirm): (1) **unknown is not zero** — a starter with no value yet (unscored K / DEF) keeps his
  slot and a player without a value in any horizon week is never a drop: the first run proposed dropping four League of
  Scrubs rosters' only (unscored) DEF "for free" and GoodGameBuddy's injured Josh Jacobs; (2) **ranking** = horizon
  gain, then weekly gain, then no drop, then the drop with the fewest rest-of-season projected points; the card flags a
  drop who projects more than the add over the season (MacZaddy: every cover drops QB3 Bryce Young, 213 vs 123 for
  Allgeier — Young shares Mahomes' week-5 bye, Shough covers it, so Young is the one who never starts in weeks 4–7);
  (3) **no `--select` edit**: `mart_waiver_moves` refs `mart_lineup_recommendation` (for `lineup_value`), so the
  existing `mart_lineup_recommendation+` in the Makefile `project` target and `nightly.sh` rebuilds it (PASS=41 on that
  line); (4) the legality test only holds leagues whose rosters and statuses are unchanged since the moves were
  computed (`inputs_fingerprint`, same SQL in `waivers.py` and the mart, pytest-checked), so a claim between the nightly
  `dbt build` and `project` cannot fail the night; coverage (every roster has a row) is always checked; (5) the
  "Adds worth a claim" shortlist and "Your bench, weakest first" are removed (the engine names the drop and what he
  costs); the free-agent table and recent moves stay, each in an expander; the FA table's projection column now uses
  the decision week (was `mart_nfl_calendar.next_week` = 3, a week already kicked off); (6) free-agent DEFs are not
  evaluated (`mart_player_availability` has no DEF; B1 has no value path for a never-rostered DEF: R-13).
* **Evidence** (after `league-lab project` on the clone: refit 3 m 00 s, weeks 1–3 kept, lineups 8,978 rows in 0.72 s,
  then `waiver moves written for 2026: 2249 rows (2244 moves, 5 rosters with nothing better) … in 1.57 s (sweep 1.21 s;
  372 of 6134 free-agent x roster pairs past the bar)`; standalone `league-lab waivers` 1.70 s in-process, 3.1 s wall
  with interpreter start). **22-roster sweep: 1.21–1.31 s (< 5 s), rows written 2,249** (dynasty 85 start-now / 78
  cover / 5 nothing; League of Scrubs 566 / 1,515 / 0), 12 of 22 rosters have a start-now claim, 39 best claims are
  "no evidence yet". Every roster's re-solve of `ops.lineups` equals `ops.lineup_totals` (22/22).
  - **Pruning rule**: a move's gain ≤ the add's gain with nobody dropped = `max(0, value − bar)`, bar = lineup −
    best lineup with one open slot he can play removed (exact; the cheapest starter he can push out after the
    reshuffle, 0 for an empty slot); free agents at or below the bar in all four weeks are skipped. **Loses nothing**:
    `league-lab waivers --verify` MacZaddy (LoS 2) pruned 283 rows in 0.62 s vs unpruned (every FA × drop × week, plain
    `solve()`) 283 rows in 4.98 s — IDENTICAL on every column; Shake & Bake (dynasty 12) 1 = 1 (0 of 212 past the bar);
    dynasty 1 44 = 44. Tests: 24 random rosters (822 moves, 280 covers, 51 no-drop) pruned = unpruned; the bar equals
    `solve()`'s add gain on 40 random rosters × 4 positions × 5 values.
  - **Numbers are the published ones**: all 1,156 displaced-starter values = `mart_lineup_recommendation.player_value`;
    all 1,446 projection-valued adds = `mart_player_week_projections.proj_points`; all 798 K adds =
    `mart_league_player_season.ppg`; `lineup_before` = `lineup_value` on all 2,249 rows.
  - **Hand re-solve** (independent integer program, scipy `milp`/HiGHS, on the published marts;
    `scratchpad/waveB_r2/b3/hand_check.py`): dynasty 1 Pitts n' Titts "Claim Michael Mayer, drop Dylan Sampson" week 4
    IP 130.26 → 131.37 = +1.11 (Mayer 8.44 takes TE from Goedert 7.33; Watson WR↔FLEX reshuffle), weeks 5/6/7 +0.11 /
    +1.13 / 0.00, horizon +2.35 = stored. **Gesicki** (same roster, #3): 130.26 → 130.59, +0.33 over Goedert 7.33,
    horizon +0.33 = stored. MacZaddy "Claim Tyler Allgeier, drop Bryce Young": weeks 4–6 0.00, week 7 IP 91.14 →
    100.72 = +9.58 (Hampton, Tuten, Croskey-Merritt on bye: RB2 empty) = stored; MacZaddy week 4 lineup 112.33
    unchanged → "Nothing on the wire beats this week's lineup (112.3 for week 4)" + the Allgeier cover card + flyer
    Sean Tucker (no games). **Shake & Bake: nothing beats what he has** — per week 4–7 the bar vs the best free agent
    (IP gain of adding him with nobody dropped = 0.00 in all 16 cases): week 4 QB 19.81 vs Kaliakmanis 9.21, RB 7.54 vs
    Kendre Miller 6.97, WR 11.08 vs Keenan Allen 8.14, **TE 9.47 (Kittle) vs Mayer 8.44 — and Gesicki 7.66**, the TE
    the U-11 shortlist offered (Kittle's 9.47 is the number `mart_lineup_recommendation` / My Week show). "Nothing" rows
    also for dynasty 4, 5, 9, 10.
  - **dbt**: `mart_lineup_recommendation+` PASS=27 (15 waiver tests + legality) and the Makefile line PASS=41;
    negative controls on the legality test (add = a rostered player, drop = an IR-slot player, no drop on a full
    roster, drop from another roster, one roster's rows deleted) → FAIL 5; same with the leagues' fingerprints changed →
    FAIL 1 (coverage only; the rest skipped as stale); restored → PASS.
  - **Tests**: `tests/test_waivers.py` 77 (empty-slot fill, beating a starter names the displaced starter, no gain
    below the bench / at a tie, the drop's horizon value counted (backup TE: +2 +2 −3 +2), locked starter not
    displaced (a cover from week 2), a free agent on bye this week covers later, open spot vs full roster, unknown is
    not zero, negative / unvalued adds, pruned = unpruned, the bar, ranking, DDL and fingerprint copies agree).
    `pytest` 386 passed, `ruff` clean, headless page check 26 runs (13 pages × 2 leagues) 0 exceptions.
  - **Page** (Playwright, both leagues, 390 × 844 and 1300 × 900; `scrollWidth = clientWidth` at 390, no exception, no
    page error; screenshots `scratchpad/waveB_r2/b3/shots/`): cards first ("Claim Michael Mayer (TE), drop Dylan
    Sampson: +1.1 this week at TE, +2.4 over the next 4 weeks" + "He starts at TE; Dallas Goedert (TE, projected 7.3)
    goes to your bench. Your week-4 lineup: 130.3 → 131.4."), best cover, flyer, or "Nothing beats what you have";
    one line on upside stashes; the five-column table (Claim, Drop, This week, Next 4 wks, Why) in an expander; "How to
    read this"; the free-agent browser and recent moves in expanders (the only tables wider than five columns).
* **Open**: `ops.waiver_moves` is not in `nightly.sh`'s `STATE_TABLES` (outside the line B3 may edit): on a fresh CI
  database a soft `project` failure republishes last night's lineups but no moves (the page then says they are not
  computed yet) — add it next to `ops.lineup_totals`; the U-11 registry entries `claim_week` / `claim_season` /
  `compared_with` in `app/lib/table.py` are now unused (append-only rule: PO to delete, they also show in Home's
  glossary); no `metric_registry.csv` row for `weekly_gain` / `horizon_gain` (seeds out of bounds); a "nothing" card
  could name the closest miss (e.g. Mayer 8.4 vs Kittle 9.5) — not stored today; waiver priority / FAAB, two-for-one
  moves and free-agent DEFs are not modelled; K values rest on 2–3 games so far.
### B4 2026-09-30 — player card and My Week (branch `dev/B4`, clone `league_lab_b4`)

* **Built** (plan Iteration 9b, B4, with the round-2 amendments): `app/lib/cards.py` (shared decision cards:
  `decision_week`, `lineup_rows` — one query over `mart_lineup_recommendation` + `ops.lineups` bench / unplayable +
  `dim_game` kickoff + `mart_defense_vs_position_current` —, the pure `decisions` / `alternative` / `bench_gap`, and
  `decision_cards`, `lineup_table`, `league_line`, `howto_cards`); **My Week** replaces Home's "Your week" (team, record,
  opponent; the lineup value and, when B2's `mart_league_roster_rankings` is on the database, its rank; up to three
  decision cards; the proposed lineup in four columns; margins, bench and who can't play in an expander; usage movers in
  an expander) and Home's intro is two plain sentences; **Matchups** opens with the same cards and "Your best lineup this
  week" (expander), the start/sit board moved into an expander (its SELECT gained `gsis_id`); the **player card**
  `app/pages/0_Player.py` → `/Player?id=<gsis>` (+ `league` / `team`; `0_` puts it second in the sidebar without
  renaming any page), search box (name → gsis, punctuation-blind: "amonra st brown" finds Amon-Ra St. Brown), four
  bordered sections — Usage, Projection (week N, this league's scoring), Availability, Value — each ending in
  "unavailable: <why>" when it has nothing; **links**: `player_url` / `player_link` at the end of `app/lib/ui.py`
  and `show()` in `app/lib/table.py` renders `player_name` as a `LinkColumn` (`display_text` regex on the leading
  `name=` parameter, left-aligned; URL `Player?name=…&id=…&league=…&team=…`, name first so the column still sorts by
  name) whenever the frame carries `gsis_id` — displayed or not; a row without a gsis id (a team defense) links to the
  card's search for that name. Definitions in `docs/METRICS.md` § Lineup value → Decision cards. No new mart, no
  dbt change, no registry column (the lineup table's labels are `show()` overrides).
* **Decisions** (PO to confirm): (1) the week is the first regular-season week whose **last** game has not kicked off
  (clock, `dim_game`), not `mart_nfl_calendar.next_week` — the calendar follows finals in the data and in this clone
  still says week 3 (1 of 16 week-3 games final when it was loaded), while every week-3 game has kicked off; on the Mac
  after a nightly the two agree except between the Monday-night kickoff and the next nightly. The Matchups caption and
  start/sit board still follow the calendar (not my section). (2) The named alternative is **who the re-solve brings
  in** (value = starter value − margin), not always "the best bench player eligible for the slot": the two differ when
  a teammate slides (58 of 978 cards over weeks 4–18; 0 of Andrew's six week-4 cards); the card then names both ("Judkins
  would come in at FLEX and Golden would move to WR2"), so the number on the card is always B1's margin. (3) A starter
  nobody on the bench can replace (only K, only DEF: margin = value) gets no card — League of Scrubs roster 2's DEF
  (1.00, no backup) would otherwise be its second "call". (4) Locked = B1's `is_locked` **or** his game has kicked off
  at page time. (5) Values and margins on cards and the lineup table show two decimals (0.15 apart must not read as
  "10.0 vs 9.9"); the projection section of the card keeps one decimal like Rankings / Waiver Wire. (6) "coin flip"
  < 1 point, "lean" < 3, else "clear".
* **Evidence** (clone `league_lab_b4`, clock 2026-09-30, decision week 4):
  * **My Week = the mart**: `tests/test_my_week.py` runs Home (AppTest) for dynasty roster 12 and League of Scrubs
    roster 2 and asserts the lineup table equals `mart_lineup_recommendation` slot by slot (gsis id, name, value), the
    week is the first open week, the cards equal an independent SQL (smallest-margin unlocked valued starters over the
    best eligible bench player, the entering player when a teammate slides, forced starters skipped) and the first card
    is the mart's `weakest_slot`. 2 passed; negative controls: a dropped TE row → 2 failed; cards ordered by value → 2
    failed. Andrew's week 4 by hand from `ops.lineups`: dynasty 12 (lineup 109.69) — RB2 Gainwell 7.54 over bench RB
    Emanuel Wilson 7.09 = 0.45 (margin 0.45), TE Kittle 9.47 over Likely 8.84 = 0.63, FLEX Boston 11.08 over Godwin 9.21
    = 1.87 (Rodgers 17.86 / Willis 17.28 are QBs, not FLEX-eligible); Scrubs 2 (112.33) — FLEX2 Croskey-Merritt 9.13
    over Tuten 9.07 = 0.06, RB2 Hampton 10.73 over Tuten = 1.66, QB Mahomes 19.98 over Young 17.75 = 2.23 (DEF Kansas
    City 1.00, margin 1.00, no bench DEF: skipped).
  * **Every card re-solved**: all 330 proposed roster-weeks of weeks 4–18 (both leagues) through `decisions()` and then
    `lineup.solve()` without the starter: 978 cards, 978 bring in exactly the named player and lose exactly the margin;
    920 direct swaps, 58 slides; the first card is the mart's weakest slot in 323 / 330 roster-weeks — in 5 that
    starter is irreplaceable (a lone K / DEF) and 2 have no card at all (League of Scrubs rosters 6 wk 11 and 4 wk 13:
    empty bench) (`scratchpad/waveB_r2/b4/verify_decisions.py`).
    `tests/test_cards.py` (12): the eligibility map equals the solver's; Andrew's dynasty week 4 rebuilt by hand; a slide
    (W2 10.0 benched → FLEX WR 9.5 slides, RB 8.0 enters: margin 2.0, not 3.0); forced / locked / unvalued starters
    skipped; 360 random rosters on three slot sets (dynasty, League of Scrubs, WRRB_FLEX + REC_FLEX + FLEX) against the
    solver; `show()` links with `st.dataframe` captured (gsis not displayed but used; a DEF row → search link; label and
    `display_text`), frames without `gsis_id` untouched; `player_link` encoding; B2 rank phrase. Negative controls: target
    off by 0.05 → 4 failed; the slid-in player replaced by the slot's best → 4 failed.
  * **Player card**, both leagues, AppTest and Playwright: Amon-Ra St. Brown (rostered WR, dynasty 12: shares 35.1 /
    42.9 / 92.5 / 42.9 %, 17.0 proj, floor 7.6, ceiling 28.7, 9.1 targets, @ CAR #21 vs WR, next 4 with the week-6 bye,
    starts at WR1, "without him the lineup loses 7.76 (Chris Godwin Jr., 9.21, would come in): clear"), Ryan Miller (free-agent WR, both leagues: Questionable, 2.6 proj),
    Chase McLaughlin (K, Scrubs: projection "unavailable: the model projects QB, RB, WR and TE …", FG 6 of 6, 13.50 at K
    "nobody on the bench can play K: he is a must-start"), Josh Jacobs (no v2 projection: "unavailable: he is on the
    exempt list"; usage "unavailable: no games this season yet"; bench 5 of 5 with no value this week), Aaron Rodgers
    (free-agent QB, Scrubs), a DEF name link → search ("team defenses have no card"). No empty section in any.
  * **Queries per card** (psycopg `execute` counted on a cold cache, `count_queries.py`): 5 for a rostered player, 4
    for a free agent — `dim_game` (week), one profile join (`dim_player` ⟕ `mart_player_availability` ⟕
    `mart_player_season` ⟕ `mart_player_trend_tags` ⟕ `mart_league_player_season` ×2), `mart_player_week_projections`,
    `dim_game` ⟕ `mart_defense_vs_position_current` (schedule + ranks), `lineup_rows` (the roster's lineup). Page chrome
    on top: connection check, banner (4), `require_relations`, perspective (2–3).
  * **Links**: rendered pages (AppTest, dynasty 12 / Scrubs 2) — player names are links in Home (lineup, full lineup,
    movers), Matchups (full lineup, start/sit board), Rankings (2 boards), Trends (1), Waiver Wire (the "Adds worth a
    claim" shortlist, when it has rows). Frames with names but **no `gsis_id`** (their SELECT omits it; each is a
    one-token fix in the owner's page): Team Hub skill / kicker / keeper tables (B2), Trade Finder theirs / yours /
    buy-low / sell-high (B2), Waiver Wire free agents / bench / transactions (B3), Receivers (5 tables: selected by
    name), Players (season, games), League (lineups, transactions, draft); Kickers uses `kicker_name`, Matchups' CB
    table `defender_name`, Team Hub `top_players` (text lists). Browser: a card link and a grid cell both open
    `/Player?name=…&id=…&league=…&team=…` in a new tab on the right player.
  * `grep mart_player_week_rankings app/Home.py` → nothing (only `4_Rankings.py` reads it). `tests/test_app_guards.py`
    passes (the card guards `mart_player_availability`, `mart_player_week_projections`, `mart_league_player_season`,
    `dim_game`, all read as `analytics.<name>` on the page). `pytest` 323 passed (+14), `ruff` clean. Headless check
    (`scratchpad/waveB_r2/b4/apptest_b4.py`): 14 pages × 2 leagues = 28 runs + 6 Player runs with `at.query_params["id"]` /
    `["name"]`, 0 exceptions, 0 errors. Playwright 390 × 844 and 1300 × 900, full height: Home, Matchups, four player
    cards, both leagues — main-area `scrollWidth` = viewport (no horizontal page scroll), the lineup table 4 columns,
    card metrics wrap two or three per row at 390 px. B2's rank line exercised with a stand-in view shaped like B2's
    committed `mart_league_roster_rankings` (created, read — "109.69 in week 4, 10th of 12 in the league" — and dropped).
* **Open**: the unlinked frames above (owners' pages); the Matchups caption / board follow `mart_nfl_calendar` (week 3 in
  this clone) while the cards follow the clock (week 4); an alternative whose game kicks off after the nightly still
  counts in B1's stored margin until the next run; the card cannot name the slid teammate on a path longer than one
  slide ("the lineup reshuffles" — none in weeks 4–18); `st.column_config.LinkColumn` opens the card in a new tab
  (Streamlit's behaviour; a markdown link on a card does too); no `metric_registry.csv` row (seeds out of bounds; cards
  define no new metric).

## Andrew's mobile review of the live app (2026-09-29, after round 1)

Reviewed from his phone, spoken; the points, page by page (the plan's "Round 1 status and Andrew's
mobile review" says what each one became):

* **General / mobile**: could there be a mobile version and a desktop version? Tables are too big
  for a phone; Rankings' filters are "very clunky"; Trade Finder and League Intel "don't do well on
  mobile"; keep the big tables but "at the bottom, tight", and put the answer "in your face".
* **Home**: "a nice homepage for an agent to use"; reads like AI, needs dumbing down for a broad
  audience; a release "hype-up"; cool things are buried.
* **Team Hub**: stack the sections differently; the roster-value "acquired" is wrong for the
  dynasty team; a note somewhere says it uses League of Scrubs data only — should follow the
  selected league; wants a profile ("set your profile", pick through your teams in several leagues)
  and, eventually, any Sleeper league connected, not just these two; clicking through pages
  sometimes loses whose team / which league it is.
* **Waiver Wire**: the shortlist recommended only Mike Gesicki (dynasty) "2.9 below your TE1 this
  week"; the TE1 is 10.3 there but 11.5 on his team view (and 9.4 in the other league) — "I don't
  know what these projected v2s are"; hide the IR / Out column when empty; break "rank buys" and the
  like into their own dashboards; tables too big for mobile.
* **Rankings**: injury column not needed (a filter instead); "where did these projections come
  from — did you train a model?"; what are Spearman this season / backtest; importance "price line
  0.017 … snap 0.7% — crazy that it's that low"; what is "price line".
* **Matchups**: the start/sit board does not make the decision stand out — be upfront and
  suggestive, table in the background; cornerbacks: who will Amon-Ra be matched against, how do the
  CBs rank, is there a projection for it; defense vs position as a chart; "look up any player next to
  matchup" unclear.
* **Trade Finder**: fine on desktop, not on mobile; a trade simulator; buy-low across the league with
  owners (already there) — also by position.
* **League Intel**: "not sure what this means"; the charts (schedule luck, points left on the bench,
  weekly scoring rank) are the interesting part, but only eight teams fit; fold it into League;
  standings / high scores / matchups / lineups feel superfluous.
* **Players**: keep. **Receivers**: add context on why the metrics matter and how to use the chart.
  **Kickers**: "could use some love".

PO findings from the review, checked in the code the same day: the 10.3 vs 11.5 is two models —
the shortlist uses projection v2 in the selected league's scoring, Home's "Your week" table uses
`mart_player_week_rankings` (the baseline model, reference scoring); the importance table on
Rankings is the permutation importance of the P50 *quantile* model, whose dominant input is the
priced line itself — it describes the residual adjuster, not the projection (plan U-15).

## Wave C (Iteration 10)

### PO merge — round 1 (C1 + C2 + C3), 2026-09-30

* Three Opus developers in parallel off `8d8cead` (worktrees `wt-c1` / `wt-c2` / `wt-c3`, clones `league_lab_c1` /
  `_c2` / `_c3`, ports 8531–8533) with the Wave C brief (page ownership split by region: C1 layout, C2 text, C3
  model). Merged into `integration/wave-c`: C1 first, C3 (CHANGELOG / STATUS keep both), then C2 — Rankings,
  Matchups and League conflicted where C1 restructured a region whose `howto` text C2 rewrote: resolved as C1's
  structure with C2's text pasted into it; `7_League_Intel.py` stays deleted (C1) and C2's three rewritten boxes
  for it were carried into League; Home is C2's (its page guide already falls back to League when Intel is gone).
  PO fix-ups: the label renames C2 could not make (`Proj (v2)` → Proj, `Floor (P10)` / `Ceiling (P90)` / `Median (P50)`
  → Floor / Ceiling / Middle, `Spearman` → Order score, the Rankings picker "League Lab projection · …" / "Old formula",
  chart titles), the K/DEF registry help (`player_value`, `value_source`) now that kickers and defenses are projected,
  "It starts at DEF" on waiver cards, and one What's new line each for C1 and C3 in `app/whats_new.md`.
* Decisions confirmed as delivered: C1 — Phone level from the User-Agent (`Mobi`), injuries as "· Q/D/O" after the
  name on Rankings, the "Points by week" line chart dropped in favour of the rank heatmap, no "likely cover" claim
  on the cornerback card until R-14; C2 — importance from the held-out twin (2016–2024 models scored on 2025), the
  priced-line MAE rise as the single number, computed once per training window, What's new from `app/whats_new.md`;
  C3 — DEF keyed by the Sleeper id in `ops.projections.gsis_id` (NULL in the mart, keyed by team), an unmapped K
  takes his team's only projected kicker, both K and DEF ship as the model (`KD_SHIP`), `kd1.0` rows in
  `ops.projection_backtest`.
* Verified on the main database: `pytest` 571, `ruff` clean, migrate, `mart_kd_team_game+ mart_player_availability+`
  built, `project` (v2 → K/DEF → lineups → waivers → importance), the projection/lineup/importance marts rebuilt,
  `backtest-kd` run once so the hosted copy carries the K/DEF backtest, the headless check on every page × both
  leagues + the Player page with 0 exceptions.
* One QA agent, phone-first, 20 minutes: every walked page (Home, League, Matchups, Rankings, Kickers, Waiver Wire, Team
  Hub, Player) has no sideways scroll and no table over five columns — including inside every expander — on both
  leagues; the Phone level is the default on a phone user agent, Essentials on desktop; every League chart shows all
  10 / 12 teams; the selection survived Home → League → Matchups → Kickers → Home; the Kickers card (McLaughlin 8.07,
  Reichard 10.28), the Scrubs waiver card (Browns DEF +0.90 / +9.74) and Team Hub / My Week K and DEF values all equal
  the marts; "The model" answers the three questions in plain words; Rankings now defaults to week 4. QA fixed two
  things (`a5d3262`): the range chart's hover called the bar's width "P90"; Home's "10th most of 10" now says "the
  fewest in the league". Open LOW items: under touch emulation a table link needs two taps (unconfirmed on a real
  iPhone); Kickers sits behind "View 3 more" in the phone sidebar; luck wording differs between Home and League on a
  tie; the freshness line, "(#2 vs RB)", "first choice … 46%" and "QB2 by points per game" still read as insider
  phrases on Home; the backtest chart title still says Spearman; a defense drop's "costs 21.6 (already counted)"
  reads oddly next to a net +9.7; the Player page leads with Usage; the schedule-luck x-axis title clips at 390 px.
* Left for round 2 / later: Rankings' Position selector still QB–TE (K/DEF boards need the backtest selector reworked);
  the D/ST keys `def_st_ff` / `def_st_fum_rec` / `st_ff` / `st_fum_rec` price at 0 (≈0.1 pt/game); `backtest-kd` is
  not in the nightly (run it after a `KD_MODEL_VERSION` change); the Player card's no-projection text for a K on a
  bye; names inside cards (Team Hub, Waiver Wire) are not links; importance is in the reference scoring only;
  `metric_registry` rows for `projection_importance` and `kd_projection`.

### C1 2026-09-30 — U-13 mobile pass + U-16 League consolidation (branch `dev/C1`, clone `league_lab_c1`)

**What changed.**
* **Phone detail level** (`app/lib/table.py`): `detail_level()` is now `phone | essentials | everything`;
  `phone_columns(df, cols, overrides, phone_cols)` (pure) picks at most five columns — the caller's `phone_cols`, else
  the first five essentials; identifiers never count; injury-report columns (`report_status`, `injury_status`,
  `is_on_ir`, `is_questionable`) only when some row is not Healthy, and then the first of them takes the fifth place;
  practice status and the injury text never show at Phone. `show()` applies it, pins the first column at Phone, and
  gained `phone_cols=`, `links=`, `widths=`, `pin=`. The sidebar radio (`ui._sidebar_links`) has three options; a new
  session starts on **Phone when the browser's User-Agent says phone** (`"Mobi"`: iPhone, Android phones; not iPad,
  not desktop) — read server-side from `st.context.headers`, no JavaScript. The choice is kept in `st.session_state`
  and re-assigned before the widget (the `perspective()` trick), so it survives page hops; `?detail=phone|essentials|
  everything` seeds it. A viewport-width component was not built: the User-Agent is cheaper and deterministic.
* **One week rule** (end of `app/lib/ui.py`): `current_week(league_id=None, *, season=None, now=None)` = the first
  regular-season week of the league's season whose **last** game has not kicked off (B4's rule; pure core
  `first_open_week(games, now)`), with `current_season()`, `week_schedule()`, `week_first_kickoff()`,
  `week_opponents()` and `align_opponents(df, season, week)` (re-keys a frame's opponent / is_home / is_bye /
  opp_rank_std / opp_rank_l4 / opp_points_allowed_pg_std to the week; `mart_player_availability` and
  `mart_player_next_matchup` key them to `mart_nfl_calendar`). Used by `cards.decision_week` (now a wrapper),
  Rankings' default week, the Matchups caption, board, receiver line and lookup, Team Hub's usage table and Waiver
  Wire's free-agent browse. `mart_nfl_calendar` is left to history.
* **League (U-16)**: `7_League_Intel.py` deleted, folded into `8_League.py`: season picker → one answer line →
  three charts with **every team** (schedule luck and points left on the bench as horizontal bars, weekly scoring
  rank as a heatmap; your team solid and bold with ◀; no drag/zoom so a phone scrolls) → B2's roster rankings
  (5 columns, current season) → expanders: Standings, Manager profiles (Intel's table), Weekly scores and high
  scores, Matchups and lineups, Transactions, Draft review, Past seasons. The 8-team line charts are gone.
* **Matchups** (below B4's cards): the start/sit board stays in its expander; "Cornerbacks your receivers face" is
  a card (toughest / easiest matchup of your starting WR/TE by rank vs position, and the toughest opponent's
  starting corners' passer rating allowed, targets-weighted) + the 14-column CB table in an expander; "Defense vs
  position" is a card (best and toughest matchup in your lineup; whole league: who gives up the most per position)
  + the tables and heat grid in an expander; the lookup moved into an expander. "Likely cover" is not claimed:
  alignment data is R-14.
* **Rankings** (filters and board region only): a wrapping horizontal row — Position (segmented), Week, and a
  "More filters" popover (projection, season, who, **injury** filter: anyone ranked / no injury tag / only tagged,
  count); a caption lists non-default filters. One answer card (#1 at the position with the bad-week / good-week
  range; your players on the board with rank and projection), then the board as **five columns at every level**
  (#, player — "· Q" after a tagged name —, opponent, projection, range "7.8–32.0"; a played week swaps opponent for
  the actual). The full board, "your players", the drift scoreboard and the backtest detail moved into expanders.
* **Links**: `show()` links `player_name` and `kicker_name` whenever `gsis_id` is in the frame, and any other name
  column through `links={"col": ("id_col", "plain_name_col")}`. Added `gsis_id` to the SELECTs of Team Hub (roster,
  slot strength via `top_gsis_id`, usage, keeper facts), Trade Finder (candidates), Waiver Wire (`add_gsis_id` /
  `drop_gsis_id` → both claim and drop link; free agents; recent moves via `player_id_map`), League (lineups from
  `league_player_week`, transactions via `player_id_map` on `sleeper_player_id`, draft), Receivers (every table),
  Players (season table; the game log now selects by `gsis_id`, not by name), Kickers (weekly), Matchups (lookup).
  B2's two `narrow_table` helpers now call `show()`.
* **Other pages, layout only**: answer line/card first and wide tables in expanders on Trends, Players, Receivers,
  Kickers and Data Status (the last is nobody's page in Wave C; touched only for the walk's "every page" rule).
  Stale "League Intel" mentions removed from Home's page table, `reference_scoring_note`, README, METRICS,
  LIMITATIONS and two dbt descriptions.

**Evidence** (clone `league_lab_c1`, now = 2026-09-30 14:07 UTC, `mart_nfl_calendar.next_week` = 3):
* Playwright walk (`scratchpad/waveC/c1/walk.py`), 13 pages × 2 leagues (dynasty roster 12, Scrubs roster 2) × 2
  viewports (390 × 844 iPhone 14 UA, 1300 × 900) = 52 page views: `scrollWidth == clientWidth` on all 52; 20 tables
  outside expanders, the widest 5 columns (`aria-colcount`); a bordered answer card above the first table on every
  page that has one; 0 Streamlit exceptions. At 390 px the default level is Phone (Players' season table 5 columns
  vs 20 at 1300; Receivers 5 vs 12; Trends 5 vs 10); opened expanders at 390: Team Hub roster, League standings,
  Matchups CBs = 5 columns each.
* League charts (Plotly data): schedule luck / bench / weekly rank = 12 / 12 / 12 teams (dynasty) and 10 / 10 / 10
  (Scrubs) at both widths. Answer lines: dynasty 12 "the unluckiest team by schedule (−0.9 wins); your bench has left
  49 points unstarted (the 7th most of 12, 2 weeks)"; Scrubs 2 "the 5th-unluckiest (−0.2 wins) … 7 points (the fewest
  in the league)" — reproduced by `rank()` over `mart_league_manager_profile` (−0.22 ties 5th; 7.40 = 10th of 10).
* One week: Home "My week — week 4", Rankings' week selectbox **4**, Matchups caption "NFL 2026 · week 4 · first
  kickoff Thu Oct 1, 8:15 PM ET", Waiver Wire "week 4", on both leagues — while `mart_nfl_calendar` says 3. Team Hub's
  usage table: Malik Willis vs **MIN** (#20 vs QB) = `mart_player_week_projections` week 4 (MIN, 20); the
  availability mart still says KC (#30), week 3.
* Player card from a name (phone, click in the grid → new tab, card heading = the player, 0 exceptions): Team Hub
  roster (Bo Nix; Patrick Mahomes), Trade Finder buy-low (Quinshon Judkins; De'Von Achane), Waiver Wire claim
  (Tyler Allgeier) **and** drop (Bryce Young) in the same row, League transactions (Case Keenum; Sam Darnold) and
  draft (Jeremiyah Love), Receivers (Amon-Ra St. Brown), Rankings (Chris Olave), Matchups board (Aaron Rodgers),
  Players (Christian Watson). Not links: team rows (standings, profiles, roster rankings, kicker summary), defenders
  (no card for defenders), defenses; rows without an NFL id link to the card's search (League draft 10 of 150 picks,
  transactions 24 of 358 rows, lineups 36 of 1,336 — team defenses mostly). Card text (Team Hub's closest call,
  Waiver cards) is not linked: that copy is C2's.
* Detail level: iPhone → Phone (League standings 5 columns), desktop → Essentials (14); Everything picked on League
  stays Everything after hopping to Team Hub and back; `?detail=phone` on desktop → Phone.
* `pytest` 552 passed (22 new in `tests/test_mobile.py`: `current_week` before Thursday / after Thursday's kickoff /
  after the Monday game / off-season / no schedule, the wired helper with `query` stubbed, `decision_week` delegating,
  `align_opponents`; the Phone column choice, injury rule, ids, User-Agent default, `show()` at Phone and
  Essentials, two links per row, kicker links); `ruff check src tests app` clean; `tests/test_app_guards.py` passes
  with the Intel page gone; headless check (Home + 12 pages × 2 leagues + 6 Player-by-id runs = 32) 0 exceptions,
  plus 78 more runs at Phone, Everything and whole-league: 0 exceptions, no table wider than 5 at Phone.
* Screenshots (scratchpad `waveC/c1/shots/`): `{phone,desktop}_{dyn,scr}_{Matchups,League,Rankings,Team_Hub}_{fold,full}.png`,
  `phone_{dyn,scr}_{Team_Hub,League,Matchups}_open.png`, `link_*.png` (the card each click opened).

**Decisions for the PO.** Rankings shows injury as "· Q/D/O" after the name, not as a column (keeps the range in
five columns at every level); the Phone default comes from the User-Agent (no width component); tables that are the
page's main content on research pages (Players, Receivers, Trends) sit in an expander that starts open; the
League page drops the "Points by week" line chart (the rank heatmap covers every team) and the standings'
points-for bar; Data Status got the answer-first layout although no Wave C task owns it.

**Open.** Player links still open a new tab (Streamlit's LinkColumn), and a new tab is a new session: the level
returns to the device default and the team comes from the URL. Merge notes: C2's edits to `7_League_Intel.py`'s
`howto` strings (if any) must be carried into the matching `8_League.py` expanders (git will report modify/delete);
Home's page table and the Essentials sentence were edited in two lines (C2 owns Home's copy). No `--select` appended,
no seeds touched; `metric_registry` rows I would have added: none (no new metric).
### C3 2026-09-30 — R-13 kicker and D/ST projections (branch `dev/C3`, clone `league_lab_c3`)

* **Built.** `src/league_lab/kdef.py` (model `kd1.0`): per kicker-week and team-defense-week a stat line —
  K: FG made 0–19 / 20–29 / 30–39 / 40–49 / 50+, FG missed (blocked = missed), PAT made / missed; DEF: sacks,
  INT, fumble recoveries, forced fumbles, defensive TDs (INT + fumble returns), ST TDs, safeties, blocked kicks
  and **points allowed as a bucket distribution** (point forecast + out-of-fold errors → P(each `pts_allow_*`
  bucket)) — priced in each league's scoring; one `HistGradientBoostingRegressor` per component (Poisson /
  squared error), as-of team, opponent, game (Vegas, home, dome) and kicker-accuracy features; P10/P50/P90 =
  projection + out-of-fold residual quantiles (calibrated interval). New marts `mart_kd_team_game` (team ×
  game facts, 5,822 rows) and `mart_kd_week` (K / DEF unit × week with outcomes, 11,706 rows), macros
  `def_points()` (the D/ST scoring twin of `kdef.DEF_STAT_MAP`) and `kd_team()` (OAK/SD → LV/LAC so the 2016–2019
  schedule meets the stats files). `projections.project` appends the K/DEF rows to the v2 rows **before the one
  `_write_projections` call** (freeze unchanged); `mart_player_week_projections` gains K/DEF rows (a `union all`
  branch; no new columns, types unchanged); `mart_player_availability` gains the 32 team defenses for leagues that
  start a DEF; `lineup.py` values K/DEF from `proj_points` (fallbacks unchanged); the waiver engine now sees
  free-agent defenses through the availability rows; Kickers page opens with "Next week's kickers";
  `league-lab backtest-kd`. Docs: METRICS § Kicker and defense projections (+ Lineup value sources), DATA_MODEL.
* **Decisions** (PO to confirm): (1) **boosting, not a hand rates model** — same family and machinery as v2;
  the inputs interact and have holes the trees take as they are; (2) **calibrated interval, not quantile models**
  (errors barely depend on the level; ~5k rows); floor clipped at 0 like v2 (Scrubs D/ST < 0 in 6.6% of
  team-weeks); (3) **DEF key in `ops.projections.gsis_id` = the Sleeper id** (`KC`, `LAR`); the mart shows DEF
  `gsis_id` NULL and is keyed by `team` (dbt tests split by position); (4) **an unmapped Sleeper kicker** (Trey
  Smack, no `player_id_map` row) takes his NFL team's projected kicker that week **only when the team has exactly
  one** (never a name join; ambiguous = no value); (5) backtest rows go to **`ops.projection_backtest` tagged
  `kd1.0`** (restored by the nightly's restore-state like v2's) and `backtest()`'s delete now skips `kd*` rows so a
  `backtest-v2` rerun cannot wipe them; (6) K rows follow the injury report like QB–TE (Out / Doubtful / NFL IR
  cannot play) once projected; (7) lineups' `model_version` stays the v2 tag (the K/DEF provenance is
  `value_source = 'proj_points'` + the `kd1.0` rows); (8) the D/ST keys not projected (`def_st_ff`,
  `def_st_fum_rec`, `st_ff`, `st_fum_rec`: 1 point each in Scrubs, ~0.1 a game) price 0 and are logged.
* **Backtest** (walk-forward, League of Scrubs scoring, ~30 units × 18 weeks a season, same unit-weeks for all
  three scorers; 80 s):

  | Pos | Scorer | 2021 | 2022 | 2023 | 2024 | 2025 | mean Spearman | MAE | top-10 hit | coverage 80 |
  |---|---|---|---|---|---|---|---|---|---|---|
  | K | **kd1.0** | 0.186 | 0.077 | 0.105 | 0.180 | 0.147 | **0.139** | 3.71 | 40.3% | 79.3% |
  | K | season PPG | 0.101 | −0.000 | 0.045 | 0.082 | 0.118 | 0.069 | 4.06 | 36.3% | |
  | K | last-3 PPG | 0.052 | 0.061 | 0.024 | 0.065 | 0.083 | 0.057 | 4.23 | 36.2% | |
  | DEF | **kd1.0** | 0.263 | 0.165 | 0.249 | 0.316 | 0.332 | **0.265** | 4.64 | 44.9% | 80.2% |
  | DEF | season PPG | 0.098 | 0.013 | 0.050 | 0.154 | 0.076 | 0.078 | 5.14 | 36.6% | |
  | DEF | last-3 PPG | 0.081 | 0.088 | 0.110 | 0.132 | 0.047 | 0.092 | 5.35 | 38.4% | |

  **Ship decision: both ship as the model** (`KD_SHIP`): kd1.0 beats season PPG on Spearman in every season at
  both positions and has the lower MAE every season. Honest caveat: a kicker Spearman of 0.14 is a small edge.
* **Evidence** (clone `league_lab_c3`, 2026-09-30):
  - D/ST pricing vs Sleeper (Scrubs rostered D/ST 2024–2025): 349 / 398 exact, 388 within 1 pt, MAE 0.19; the
    mart's SQL pricing (`league_points()` / `def_points()`) equals `kdef`'s Python pricing on all 5,434 played
    K/DEF unit-weeks 2021–2025 (max difference 0.00).
  - Coverage: every rostered Scrubs K and DEF has a projection for every remaining week his team plays — DEF 154 /
    154 roster-weeks (11 defenses), K 140 / 140 (10 kickers: 126 by NFL id + 14 for Trey Smack via GB's only
    kicker). `ops.projections` 2026: K 448 + DEF 448 rows (32 units × weeks 4–18 with a game).
  - Lineups (Scrubs, week 4): every K/DEF starter `value_source = 'proj_points'`; **0 unvalued starters** (before:
    5 starters — Smack K, CAR/MIN/CIN/NE DEF — plus Josh Jacobs on a bench, an RB without a v2 row, out of scope);
    weeks 4–18: `n_unvalued` 0 and `n_ppg_valued` 0 for every Scrubs roster.
  - Waivers: 1,222 free-agent DEF moves (582 *start now* over 6 rosters, 21 defenses evaluated); MacZaddy's top
    claim is "Claim Cleveland Browns (DEF), drop Kansas City Chiefs: +0.9 this week, +9.7 over the next 4 weeks";
    the sweep 2.1–2.5 s (was 1.65 s).
  - Worked example (week 4, reproduced by hand): Will Reichard (MIN vs MIA) 0.002 + 0.534 + 0.635 FG 0–39 × 3 +
    0.561 FG 40–49 × 4 + 0.426 FG 50+ × 5 − 0.374 missed + 2.844 PAT − 0.082 PAT missed = **10.28** = stored
    `proj_points`; P10 / P50 / P90 = 10.28 + (−5.66, −0.42, +5.98) = 4.62 / 9.86 / 16.26. Vikings D/ST vs MIA:
    3.33 sacks + 2 × 1.11 INT + 2 × 0.57 FR + 0.86 FF + 6 × (0.22 + 0.02) TD + 2 × (0.015 + 0.022) + bucket
    probabilities (0.02, 0.07, 0.20, 0.30, 0.24, 0.12, 0.05) × (10, 7, 4, 1, 0, −1, −4) = **10.54** = stored.
  - Freeze and determinism: two consecutive `project` runs give byte-identical weeks 4–18 for all positions
    (17,164 rows, md5 without `fitted_at` `b42e5bb8…` both times); weeks 1–3 untouched (3,554 rows, md5
    `e2631911…` before any change and after); QB–TE weeks 4–18 unchanged by the K/DEF addition (16,268 rows,
    `aacf0043…` before and after); `ops.projection_drift` unchanged (18 rows, `f9e64de2…` without `run_at`); v2
    backtest rows unchanged (2,160, `9fe9cc91…`). `assert_frozen_projections_precede_kickoff` passes.
  - dbt: `build --select mart_player_week_projections+ mart_projection_backtest+ mart_lineup_recommendation+
    mart_player_availability+` PASS=73 (incl. the lineup, roster-value and waiver-legality tests); `mart_kd_*`
    PASS=10; pytest 541 passed (11 new in `tests/test_kdef.py`); ruff clean; headless check 34 runs, 0 exceptions.
  - `league-lab project` time, back to back on a quiet sandbox (load 1.2–2.0, `OMP_NUM_THREADS=2`): **before (main,
    `8d8cead`) 130.3 s, after 134.8 s**; the K/DEF step itself ≈ 12 s (load + fit K + fit DEF + price), the waiver
    sweep 2.0 s (was 1.7 s: more candidates), lineups unchanged (0.6–0.8 s). Earlier runs under three developers'
    contention (load 5–7) took 1,142 s before / 1,393 s after — the difference there is the contention, not R-13.
* **Open / for the PO**: `app/lib/table.py` help strings for `player_value` / `value_source` still say "K = season
  PPG, DEF = Sleeper PPG" (shared registry, append-only for C3: C1/C2 to update); the Player card's
  no-projection text for a K ("the model projects QB, RB, WR and TE") is now only reached on a bye and should say
  so; the waiver card says "He starts at DEF" for a team defense; Rankings' Position selector does not gain K/DEF
  (not a one-line change: the baseline branch and the backtest selector index by QB–TE); a `metric_registry` row
  I would have added: `kd_projection, kd1.0, league points of the projected K/DEF stat line, per unit-week, active`.
  The nightly does not rerun `backtest-kd` on its own (the rows are restored with `ops.projection_backtest`; run
  `league-lab backtest-kd` after a `KD_MODEL_VERSION` change).
### C2 2026-09-30 — U-14 plain words + U-15 model explainer and honest importance (branch `dev/C2`, clone `league_lab_c2`)

* **Built.** *Home* (`app/Home.py`): a three-sentence intro; **Worth a look** — four one-line links with the
  selected team's number (schedule luck with its league rank, points left on the bench per week with its rank, the
  best bargain on the roster = the starter-level player (top 12 QB/TE, top 24 RB/WR by PPG) who cost least: free
  agent / waiver first, then the latest draft round, trades excluded; the rostered player with the highest first-read
  share over the last 3 games → his card), league-level lines without a team, 4 queries; `st.page_link`s that keep the
  session (league / team in `query_params`) and wrap at phone width (a 2-line CSS rule scoped to page links); the
  League Intel link resolves to League when U-16 deletes the page. The page list is now **the questions a manager
  asks** → page (13 links, same file-existence rule). **What's new** reads `app/whats_new.md` (one plain entry per
  release, rewritten from CHANGELOG, newest shown, the rest under "Earlier updates"); CHANGELOG stays the technical
  record. Glossary shows Column + Meaning (no field names). My Week untouched. *Every page's "How to read this"*: 31
  `howto(...)` / expander bodies on all 13 pages + the cards' box (`cards.howto_cards`) rewritten to 3–5 bullets
  that say what to do, text-only edits inside the literals. *Registry*: 53 `help=` strings de-jargoned (no key,
  label or kind touched). *Rankings "The model"* (my region only): "Is this a model you trained? Yes", what it learned
  from, what it predicts (one small gradient-boosted model per stat, priced in the league's scoring), floor/ceiling,
  how it was graded, Spearman once with its gloss, the kickoff board, what it does not know, refresh cadence; then
  **What it leans on most**: the top input per position in one line, a "how we measured it" caption, a tab per
  position (the board's position first) with a one-line reading and the top 10 as a numbered list in points
  (a grid hid the number at 390 px). The old quantile table is gone from the page. The old-formula expander caption
  is plain too. `docs/WORDS.md`: the rules and the term → words table.
* **Importance (U-15).** `projections.component_importance`: per input, 5 shuffles, every component re-predicted,
  **MAE** (in the stat's unit, so × points per unit = points; a Poisson deviance has no points equivalent), the
  headline = rise in MAE of the **priced line** vs actual points in the reference scoring (`component = 'total'`),
  plus one row per stat in its unit with `importance_points`. `importance_after_project` runs at the end of `project`
  (after lineups and waivers), **once per `MODEL_VERSION` × training window**, on the newest training season (2025)
  with a **twin** of the component models fitted on 2016–2024 (= the backtest's 2025 fold), kept on later runs;
  `run_importance()` forces. `ops.projection_importance` gains `model`, `component`, `feature_label`, `unit`,
  `importance_sd`, `importance_points`, `baseline_mae`, `n_rows`, `train_seasons`, `eval_season`, `fit_seasons`
  (migrate + `_write` DDL); the 300 pre-U-15 rows are labelled `quantile_p50` / `p50_residual` and `backtest-v2` now
  rewrites only those. New view `mart_projection_importance` (5 tests), appended to the `make project` and nightly
  `projection-marts` `--select`. `FEATURE_LABELS`: a plain name for all 74 inputs. `MODEL_VERSION` unchanged.
* **Evidence** (clone `league_lab_c2`, 2026-09-30):
  * **Projections byte-identical**: md5 over every value column of `ops.projections` 2026 weeks 4–18 (16,268 rows,
    `fitted_at` excluded) = `0d99a972fe70107f3e40c8b8373b664f` on the clone as delivered, after a `project` on the
    unchanged code (14:13 UTC), after the first `project` with U-15 (15:00, importance computed) and after the second
    (15:10, importance kept). Timings under a shared 2-core box: 2 m 32 s before; 6 m 16 s with the one-off importance
    (the importance step 2 m 44 s: 4 twin fits + 74 × 5 shuffles × 4 positions); 3 m 43 s on the next run (importance
    step: one count query). Note for the PO: `OMP_WAIT_POLICY=PASSIVE` made the fit ~7× faster while C3's fit shared
    the cores (OpenMP spin-waiting), with identical numbers.
  * **Importance, 2025, League of Scrubs scoring, points of error added** (top 3; the average miss in brackets):
    QB (6.03) snap share L3 +0.38, pass attempts/G L3 +0.20, Vegas implied total +0.18; RB (4.29) carry share L3
    +0.36, rushing yards/G season +0.11, target share season +0.06; WR (3.90) snap share L3 +0.12, receiving yards/G
    last season +0.04, xPPG season +0.04; TE (2.98) target share season +0.19, snap share L3 +0.10, receiving yards/G
    last season +0.10. 2,442 rows (74 inputs × (1 total + the position's stats)). **In-sample vs held out**
    (production models on 2025 vs the twin): same top input for all four positions; rank correlation over the 74
    inputs 0.68 / 0.80 / 0.62 / 0.58, top-10 overlap 7 / 9 / 8 / 6; in-sample inflates what the model memorised
    (QB rushing yards/G 0.20 vs 0.05) — hence the twin. **Priced vs weighted sum** of per-stat rises: Spearman
    0.97–0.98, top-10 overlap 8–9 of 10 (`scratchpad/waveC/c2/imp_compare.py`).
  * **Rankings** (AppTest, both leagues as dynasty 12 / Scrubs 2): the top line names QB snap share L3 · RB carry
    share L3 · WR snap share L3 · TE target share season; 4 tabs, 4 readings, 4 lists of 10; no `priced_line` and no
    "interval model" caption on the page. Playwright: expander at 390 and 1300 px, main `scrollWidth` = viewport.
  * **Home** (AppTest + Playwright, dynasty 12 / Scrubs 2): Worth a look = "Schedule luck: −0.9 wins … (12th luckiest
    of 12)", "Points left on your bench: 24.6 a week (7th most of 12)", "Best bargain: Parker Washington (Free agent
    2025 wk 9) is the WR14", "first look: Parker Washington 46%" / "−0.2 wins (5th of 10)", "3.7 a week (10th of 10)",
    "Bryce Young (Free agent 2026 wk 2) is the QB2", "Parker Washington 46%"; each reproduced by hand from
    `mart_league_manager_profile` (rank over the league), `mart_league_keeper_candidates` ⟕ `mart_league_acquisitions`
    and `mart_player_availability` (0.4643). Whole-league Home renders both leagues. 390 px: `scrollWidth` 390, every
    link wraps; 1300 px fine. Screenshots `scratchpad/waveC/c2/shots/{home,rankings_model}_{dyn12,scrubs2}_{390,1300}.png`.
  * `pytest` 538 passed (+8: `tests/test_projection_importance.py` — every input named and plain, unit points,
    the priced importance reproduced by hand with the same shuffles, a 0-point stat adds 0 points, unused / constant
    inputs 0, determinism and a skipped column not shifting the others, too few rows; negative controls: unweighted
    aggregation → 3 failed, one label removed → 1 failed). `ruff` clean. Headless check: 13 pages × 2 leagues + 6
    Player runs + Home/Rankings as dynasty 12 + Home without a team × 2 = 38 runs, 0 exceptions, 0 errors. `dbt build`
    of the project select: PASS=70.
  * **Jargon grep** (`v2|P10|P90|P50|Spearman|xPPG|z-score|mart|quantile|gsis` in user-visible string literals of
    `app/`, SQL / identifiers / docstrings skipped): 33 hits — 12 in my copy, each with its gloss in the same box
    (xPPG = expected points per game; Spearman naming the grade tables' column header; P10/P90 explained in the Floor /
    Ceiling tooltips); 10 registry **labels** I may not edit; 11 in C1's Rankings / Waiver Wire regions (see Open).
* **Open / for the PO.** (1) Labels to rename at merge (registry, C1 regions): `Proj (v2)` → `Proj`; `Floor (P10)` →
  `Floor`; `Ceiling (P90)` → `Ceiling`; `Median (P50)` → `Middle`; `Spearman` / `Spearman · backtest` / `Spearman · this
  season` → `Order score …`; `xPPG …` labels keep (glossed in every tooltip); Rankings' model picker "Projection v2 · …"
  → "League Lab projection · …"; chart legend "Floor to ceiling (P10–P90)" and hover "P10/P90" → floor/ceiling; "v2
  minus baseline (Spearman, per held-out season)" → "Projection minus old formula (order score, per past season)";
  "No v2 backtest … (`make backtest-v2`)" → "No backtest for this league yet". (2) League Intel's three rewritten boxes
  live in `7_League_Intel.py`, which U-16 deletes: carry them into League with the charts. (3) "What's new" has only
  my entry for Wave C: add one line each for C1 (phone layout, League page) and C3 (kicker and defense projections)
  in `app/whats_new.md`. (4) The Waiver Wire box no longer says "free-agent defenses are not valued yet" (C3 changes
  that). (5) Importance is measured in the reference league's scoring only; the dynasty page says so.

### PO merge — round 2 (C4 + C5 + C6), 2026-09-30

* Three Opus developers in parallel off `f72afd4` (worktrees `wt-c4` / `wt-c5` / `wt-c6`, clones, ports 8551–8553).
  Merged into `integration/wave-c2` with "keep both" conflicts only (registry blocks, METRICS, STATUS, CHANGELOG,
  What's new). PO fix-ups: the nightly restores `ops.waiver_upside`, `ops.player_role_alerts` and
  `ops.player_scenarios` with the rest of the `project` output (a soft `project` failure republishes a consistent
  night); the projection-marts selection in the Makefile and `nightly.sh` is `mart_player_role_alerts+ mart_waiver_upside`
  (C6 had appended the alerts view without `+`, which would have cascade-dropped nothing today but leaves
  `mart_waiver_upside` outside the rebuild); the release stamp in `app/requirements.txt` bumped (Community Cloud
  restarts only when that file changes — see HOSTING).
* Decisions confirmed as delivered: C4 — one `RosterBoard` per league in `evaluate`, "both accept" judged on the 4-week
  gain, every 2-for-1 pair searched (exact branch and bound = exhaustive), the market score = v2 rest-of-season points
  above the best free agent at the position (documented with its limits, shown next to fit, never blended); C5 — no
  "covered by" claim (public data has no assignment), the likely cover = the outside corner on the side his targets
  favour, ranks on two seasons, the shadow flag and the nickel call computed but not shown (1 of 6 known 2025 shadow
  corners caught), `mart_defender_coverage_season` and `mart_matchup_cb_context` retired; C6 — alerts in Python inside
  `project()` (rule ra1.1, refits the component models for the scenario base, ~25 s), the larger-role scenario shipped as
  a "what if" (`SCENARIO_SHIP=False`: 46–48 % nearer than base over 1–2 games held, 72 % at three), the upside list in
  its own table.
* Verified on the main database: `pytest` 691, `ruff` clean, migrate, the C5/C6 intermediate and mart builds, `project`
  (v2 → K/DEF → lineups → waivers → signals → importance), the projection-marts rebuild, the headless check on every page
  × both leagues + Player + Trade Finder with a package in the URL, 0 exceptions.
* **Andrew's first `make build` on the Mac (PostgreSQL 17, 4 threads) exposed two things the sandbox had not:**
  (1) three `ops` sources (`player_role_alerts`, `player_scenarios`, `waiver_upside`) did not exist because they were
  created by `project`, which runs after `build` → `db migrate` now creates every project-written table from the
  writers' own DDL (lineups, waiver moves and upside, role alerts, scenarios), verified on an empty database;
  (2) `mart_defense_position_profile` ran 31+ minutes (killed) and `mart_receiver_vs_cb` 325 s — a planner problem
  (fresh upstream tables without statistics, inequality joins, a self-join estimated at one row), reproduced here by
  disabling autovacuum (>275 s, cancelled) → C5 hotfix `9a2ba49`: six indexed, analyzed intermediate tables, every
  `week < week` join replaced by a small week bridge, big inputs stacked (`union all`) and grouped instead of
  joined, `analyze` pre-hooks on the upstream tables; both marts now 1–3 s with or without statistics, md5-identical
  output, 34/34 dbt tests. Also `receiver_vs_cb_counts_consistent` (4 rows failed on the Mac's newer data: a reception
  or TD on a play with no target in the source) now warns.
* One QA agent, phone-first, 25 minutes, both leagues as Andrew's rosters: no sideways scroll, answer before any
  table on Trade Finder / Matchups / Trends / Waiver Wire / Player; the top trade package's before/after lineup values
  equal `ops.lineup_totals` and an independent `lineup.solve` on the post-trade rosters (113.06 → 113.54 / 115.30 →
  119.73 Scrubs; 109.69 → 115.12 / 126.86 → 133.64 dynasty); the cornerback card equals `mart_cb_matchups` /
  `mart_cb_rankings` (St. Brown: even call, Mike Jackson #37 of 74); the comparison's default pair equals Home's first
  card; the top role alert's numbers equal `mart_player_role_alerts` (Germie Bernard 4 % → 79 % snaps, Pittman out); the
  upside card equals `mart_waiver_upside`; the trade URL round-trips in a fresh browser; "covered by" appears nowhere;
  the scenario is always a labelled what-if with its hit rate. No HIGH or MEDIUM findings. PO fixes from the LOW list: a
  stash with zero upside is no longer listed; the what-if sentence now says plainly that it beat the projection less than
  half the time; "Out of the lineup after the trade" instead of "Sits". Open LOW: the upside card on Waiver Wire has no
  hit rate (the Player page has it); the role alert sits low on the Player page; "you give 0" market for a QB behind a
  better free agent reads as wrong without the explanation; "Vs the offenses faced +5.7 (#1)" and a defense drop's
  "(already counted)" still read as insider phrases.

### C4 2026-09-30 — T-01 trade evaluator + T-02 trade simulator (branch `dev/C4`, clone `league_lab_c4`)

* **Built.** `src/league_lab/trades.py` on B1's lineup service and B2's `RosterBoard` (page time with scipy, no
  nightly table or mart: a whole league's partner sweep takes ~1 s). `evaluate(board, give, get)` re-solves **both**
  rosters in every week of the horizon (this week + 3) and returns per side: lineup value before / after (week and
  horizon), depth (the bench's own lineup, = B1's `bench_value`), the closest call after (`Lineup.weakest`), who
  starts / who sits, roster size (a side over its limit **cuts** its cheapest player over the horizon, counted in the
  gain; a side left with an open spot is shown the best free agent), and the **market** kept apart: rest-of-season
  projected points above the best free agent at the position (`REPLACEMENT_SQL`, `price_by_player`), summed in whole
  points. `partners(board, me)`: every other roster's best 1-for-1 and 2-for-1 (either direction) that raise both
  lineups over the horizon, ranked by the smaller gain, exact branch and bound. `fit_line` / `fairness_line` /
  `verdict` (the three lines of the simulator). `roster_value.RosterBoard` gains `roster`, `is_active`,
  `active_count`, `is_locked`, `has_value`, `pool_with`, `lineup_with` (nothing existing changed). **Trade Finder**
  rewritten: three cards (best partner + package + both gains; buy low, with the best per position; sell high), the
  partner table in an expander, **Try a trade** (partner, players both ways as multiselects; verdict, fit line,
  market line, league rank change on week / 4 weeks / depth, roster size; the market table: market, PPG, xPPG, and in
  an expander season points, position rank, games, age, NFL season, this week's value; both lineups slot by slot with
  the change, who starts and who sits; week by week in an expander), the package in the URL
  (`?partner=&give=&get=`, Sleeper ids), buy-low / sell-high lists filterable by position and owner.
  `reports.py` team brief: new "Trade partners" section (both lineups' gains + market given / received; the
  existing sections unchanged; the board rows now carry `gsis_id`). `app/lib/table.py`: a `# ---- C4 trades` block.
* **Design choices** (PO to confirm): (1) one board for both rosters (`evaluate(board, give, get)`, not
  `board_a, board_b`: a league's `RosterBoard` holds every roster); (2) "both accept" = both **horizon** gains ≥ 0.01
  (the horizon includes this week; a trade that helps both this week but costs one side over four weeks is not
  listed); (3) the 2-for-1 search is wider than the plan's "second piece = the giver's lowest-margin bench player":
  every pair in either direction, but a pair counts only if **each** piece adds to the receiver's lineup — a pure
  throw-in changes neither lineup, so it is the 1-for-1; (4) the market score starts from the v2 projection (the one
  projection every page uses; its strongest inputs are xPPG L5 / season, so it is usage-weighted without a second
  model) and is position-adjusted by the waiver wire (best free agent's season points), not by a league-wide VOR
  rank: simple, explainable ("above what you could pick up"), and it prices a kicker at 0 and a one-QB league's QBs
  low; "about even" = within 10 points or 10 %; (5) the cut is chosen one at a time (joint choice only matters for
  3-for-1s); (6) no nightly table: the sweep is < 1.3 s per roster, cached 10 min on (league, roster, data key).
* **Evidence** (clone `league_lab_c4`, this week = 4, horizon 4–7, no locks in weeks 4–7):
  - **Hand check** (`scratchpad/waveC2/c4/hand_check2.py`: `ops.lineups` rows → an integer program (scipy milp /
    HiGHS, not the assignment solver) per roster-week, the trade applied by hand, every legal cut tried, market by its
    own SQL): **dynasty, Shake & Bake (12)**: top partner The72Repeat (5), best package the 1-for-2 **Bo Nix for
    Breece Hall + Quinshon Judkins**: roster 12 109.69 / 116.42 / 104.90 / 106.81 → 115.12 / 122.95 / 111.32 / 115.74
    (+5.43 this week, +27.31 over 4 weeks), must cut Jaylen Wright (costs 0.00), depth 83.92 → 76.95; roster 5 126.86
    / 119.26 / 120.46 / 119.75 → 133.64 / 128.00 / 126.59 / 127.10 (+6.78, +29.00), depth 69.62 → 64.42; market: Nix
    306.31 − 113.21 (Justin Fields) = 193 given, Hall 205.94 − 93.72 = 112 + Judkins 157.47 − 93.72 = 64 → 176
    received: "about even: worth offering". Also the 1-for-1 Aaron Rodgers for Breece Hall (+6.28 / +26.37 vs +4.04 /
    +21.28, market 160 vs 112). **League of Scrubs, MacZaddy (2)**: top partner GoodGameBuddy (6), the 1-for-2 **Bryce
    Young for Jameson Williams + MarShawn Lloyd**: 113.06 / 98.15 / 109.20 / 91.83 → 113.54 / 98.15 / 109.20 / 102.77
    (+0.48, +11.42), must cut Jacory Croskey-Merritt (0.00), depth 40.84 → 47.39; roster 6 115.30 / 111.43 / 107.74 /
    112.37 → 119.73 / 111.43 / 109.24 / 115.68 (+4.43, +9.24), opens a spot (best free agent Daniel Carlson, K,
    +13.5, reported not added); market 0 (Young 213.31 < the free agent Drake Maye's 238.83) vs 11 (Williams 123.17 −
    112.21): "they may ask for more". Every number = `evaluate` to the cent; `before` = `ops.lineup_totals`, depth
    before = `mart_league_roster_value.bench_value`.
  - **Two-for-one with a forced cut that costs points**: Scrubs, Patrick Mahomes for Tony Pollard + Joe Burrow
    (roster 5): roster 2 must cut Jacory Croskey-Merritt, whose loss over the horizon is **0.06** (counted: +0.76 over
    4 weeks instead of +0.82), confirmed by trying every legal cut. **Bug found by this check and fixed**: the first
    version stopped comparing cuts after the first starter when no cut was free, and cut Terrance Ferguson (costs
    11.41: −10.59 instead of +0.76). New test `test_the_cut_is_the_cheapest_over_the_horizon_when_nobody_is_free`
    fails on the old rule; the random-package test now brute-forces every single cut.
  - **Never a one-sided trade in the "both accept" list**: all 22 dynasty and 18 Scrubs listed packages re-evaluated:
    both horizon gains ≥ 0.01; unit tests: a 1-for-1 where one side loses and a K-for-WR are never offered.
  - **Exact search**: `partners` = `partners_exhaustive` for every partner and shape (after the fix): dynasty 11/11
    (exhaustive 315 s vs 0.6 s), Scrubs 9/9 (64 s vs 0.6 s). **Sweep time** (every roster, fresh board, box shared
    with two builds, load 3.7): dynasty median 0.81 s, max 1.20 s; Scrubs median 0.63 s, max 0.98 s (< 3 s).
  - **URL round trip** (Playwright, both leagues, phone and desktop): the URL the page writes
    (`?league=…&team=12&partner=5&give=11563&get=8155%2C12512`), opened in a fresh browser, shows the same package,
    lines and tables (4/4); AppTest: a second partner's link opens that package, and the URL it writes reproduces it.
  - `pytest` 609 passed (+38: `tests/test_trades.py` 33 — 1-for-1 both gain, one side loses, depth / closest call /
    starts / sits, 2-for-1 forced cut + market sums, the cheapest cut when nobody is free, K-for-WR with the K slot
    empty and the kicker priced 0, bye weeks over the horizon, empty slot, locks, IR / taxi, fill vs brute force, 96
    random packages, partner search vs exhaustive, lines and verdicts, ranks, URL ids; `tests/test_trade_finder_page.py`
    5 on the database), `ruff` clean, headless check 39 runs 0 exceptions (Trade Finder with `partner`/`give`/`get`
    params: a package, a broken link, an empty one, bad ids, another team, a K-for-WR, a two-for-one with a cut).
  - Playwright (Streamlit on 8551): `scratchpad/waveC2/c4/shots2/tf_{dyn,scr}_{390,1300}_{cards,simulator,
    simulator2,simulator3,full}.png`; at 390 px scrollWidth = clientWidth, every table outside an expander ≤ 5 columns
    (market 5, lineups 4), a card before the first table, 0 exceptions.
* **Open**: the market is this season only (dynasty future value, picks, keeper costs not modelled); an injured
  player's season points count every projected week; a 1-for-1 that empties a slot does not suggest the free agent to
  refill it (only an opened spot gets a fill); a traded player's Sleeper IR / taxi status on his new roster is not
  modelled (he takes a bench spot). No `metric_registry.csv` rows (seeds out of bounds): proposed `trade_fit` v1.1
  and `trade_market_score` v1.0 (METRICS § Trades). No `--select` appended (no mart).
### C5 2026-09-30 — R-14 cornerback matchups + R-15 defense vs position as a picture + R-11 matchup comparison (branch `dev/C5`, clone `league_lab_c5`)

* **Built.** *Marts* (`dbt/models/marts/nfl/`, no `ops` source, so no `--select` change): `mart_cb_rankings`
  (cornerback × season × window season / last_4 / two_seasons; rank on targets per coverage snap, yards per target
  adjusted for the offenses faced, rating allowed; shutdown / solid / target), `mart_cb_matchups` (WR / TE × week from
  2025: the opponent's corners from its depth chart before kickoff, target direction since last season, the likely
  cover with `call_strength` clear / even, the cover's rank, his history), `mart_receiver_vs_cb` (who was on the field
  for his targets, with `share_of_targets`; same-game rows for the current season), `mart_defense_position_profile`
  (opportunity vs efficiency allowed, opponent-adjusted, as of each week, + targets / carries ranks);
  `int_defender_game_coverage_snaps`. Retired `mart_defender_coverage_season`, `mart_matchup_cb_context` (Matchups
  was the only reader; drop them on the hosted copy at will). *Page* (`app/pages/5_Matchups.py` below B4's cards):
  **Two players side by side** (opens on the first decision card whose two players are QB / RB / WR / TE; verdict
  "The lineup says Gainwell by 0.45; the matchup agrees: his defense gives up the most carries to RBs"; a 3-column
  static table; "the projection decides" caption), **Cornerbacks your receivers face** (one line per starting WR / TE:
  the likely cover with his side, rank of N and label, the share behind the call, the history; expanders: receiver by
  receiver — the opponent's three corners with their two-season / season / last-4 ranks, corners faced this season,
  on the field last season, vs the cover before —, "His points against the best corners", "Every starting corner,
  ranked" with a window switch), **Defense vs position**: heatmap (every defense × the league's positions, color =
  rank, number = points a game, your opponents pinned with ◀ and your starters' cells ringed) or ranked bars for one
  position, last-4 toggle, "Only your opponents" on by default at the Phone level, the table in the expander.
  `app/lib/matchups.py` (the words, the heatmap rows, the verdict, and `call_cover` / `rank_corners`: Python twins of
  the two SQL rules), `app/lib/charts.py` (`dvp_bars`, `dvp_heatmap` appended at the end), `app/lib/table.py`
  (C5 block). Definitions: `docs/METRICS.md` § Cornerback matchups, § Matchup comparison.
* **Evidence** (clone `league_lab_c5`, 2026 week 4):
  * **Amon-Ra St. Brown** (dynasty 12) vs CAR: 66 / 60 / 73 targets left / middle / right since 2025 (`fct_play`,
    before week 4); CAR's chart of 2026-09-26: LCB Mike Jackson, RCB Will Lee III, NB Jaycee Horn → right lean,
    37% vs 33% = **even**: "Mike Jackson (left corner, #37 of 74, solid) or Will Lee III (right corner, unranked: too
    few snaps)". Jackson rebuilt from `int_defender_game_coverage_snaps` (2025 + 2026): 19 games, 635 coverage snaps,
    106 targets, 60 catches, 744 yards, 4 TD, 4 INT → 0.167 targets per snap, 7.02 yards per target, offenses' 7.76
    → adjusted 7.04, rating 75.4; z 0.63 / −0.05 / −0.90 → score 0.107 → **#37 of 74, solid**. No meeting since 2022.
  * **Parker Washington** (Scrubs 2 and dynasty 12) vs CIN: 53 / 27 / 33 → 47% left vs 29% = **clear** → RCB DJ
    Turner II (#18 of 74, shutdown: 81 targets on 605 snaps, adjusted 6.87, rating 79.4); "11 catches for 137 yards on
    11 targets with Turner on the field (2023–25)" = the raw participation rows (6 in 2023, 5 in 2025, all his CIN
    targets). Tetairoa McMillan (Scrubs 2) vs DET: 43% vs 36% even → Rock Ya-Sin (#17, shutdown) or D.J. Reed (#39).
  * **Rule check on 2025** (as-of rows): clear calls — the named corner charged with 0.204 of the receiver's targets,
    the other outside corner 0.141, other throws 0.137; even calls 0.185 vs 0.163. **Shadow flag**: 1 of 6 commonly
    reported 2025 shadow corners (Ramsey yes; Surtain II — the most negative slope —, Stingley Jr., Gardner, Gonzalez,
    Terrell no), 0 of 10 flagged in 2024 flagged again → not shown.
  * **Rankings**: 74 ranked (2026 two seasons), 76 (2026 season), 121 (last 4), 64–78 per completed season. Top 5:
    Surtain II, Porter Jr., McDuffie, Stokes, Still; bottom 5: Alford, Stevenson, Robertson, Baker Jr., Hart. The
    full 2026 pool rebuilt at full precision: 74 / 74, 0 rank and 0 label differences; the Python twin re-derives every
    `mart_cb_matchups` call (16,972 rows, 0 differences).
  * **Coverage of lineups**: every WR / TE starter of the 22 proposed week-4 lineups has a row (83 / 83: 6 clear, 54
    even, 22 tight ends, 1 too few targets; 46 covers ranked).
  * **R-11**: on all 22 rosters the comparison opens on the first card's pair and quotes its margin (22 / 22).
  * **Checks**: dbt `mart_cb_rankings+ mart_receiver_vs_cb+ mart_defense_position_profile+` PASS (33 + 16 on the
    rebuild), `tests/test_matchups.py` 55, full `pytest` 626, `ruff` clean, headless check 32 runs 0 exceptions,
    Playwright at 390 × 844 (iPhone) and 1300 × 900, both leagues: no sideways scroll, heatmap 358 px wide at 390.
* **Hotfix 2026-10-01 (branch `hotfix/c5-perf`): planner-proof Matchups marts.** Andrew's Mac (PostgreSQL 17,
  4 threads) ran `mart_defense_position_profile` > 1,885 s and `mart_receiver_vs_cb` 325 s. Reproduced here by
  rebuilding `fct_team_game` / `fct_player_game` without statistics (autovacuum off) right before the marts: the
  profile ran > 275 s (1 thread) / > 134 s (4 threads), both cancelled — the planner estimated 28 team-games and
  chose a nested loop with a join filter on four keys; the receiver mart took 61–64 s with or without statistics (a
  join back on receiver × corner × season estimated at 1 row, looped over ~100k rows). Now six intermediate tables
  (`dbt/models/intermediate/matchups/`, `docs/DATA_MODEL.md` § Matchups "Performance"), indexed and analyzed, the
  upstream tables analyzed in `pre_hook`s, and no join between large inputs: stacked rows + `group by`, window
  functions for the as-of baseline, the league rates, the corner / receiver flags and the names; the only join left
  in the profile chain is to the 1,598-row week bridge (index loop, 182 distinct keys). Same output: md5 of the
  ordered rows `cc7cac48…` (profile, 24,704 rows), `a236ff95…` (receiver vs CB, 39,572), `2505dfc5…`
  (`mart_cb_matchups`, rebuilt downstream) before and after. Timings (sandbox, PostgreSQL 16): profile 2.9 s → 1.0 s
  with statistics, > 275 s → 1.0 s without (1 thread), > 134 s → 1.0 s (4 threads); receiver vs CB 62 s → 3.1–3.3 s
  in every case; the whole chain (12 models from `fct_team_game`) 34 s (1 thread) / 26 s (4 threads) without
  statistics. Without statistics and without the pre-hook the new game-level query still runs in 0.43 s
  (estimates 28 vs 5,344 rows, but there is no join to get wrong). `dbt build` of the chain + `mart_cb_matchups`:
  34 / 34 PASS.
* **Left open.** No projection change from the corner (a model change); the PPG split is evidence only. Shadow
  coverage, receiver alignment and slot assignment are not in public data. `metric_registry` rows not added (seeds are
  out of bounds): `cb_rankings` v1.0, `cb_matchups` v1.0, `defense_profile` v1.0.
### C6 2026-09-30 — R-10 role alerts + R-12 scenario upside + U-17 Receivers/Kickers context (branch `dev/C6`, clone `league_lab_c6`)

* **Built.** `src/league_lab/signals.py` (rule `ra1.1`, docs/METRICS.md § Role alerts / § Scenario upside), run by
  `projections.project` right after the projections are written (one import + one call; logged, never fatal) and on
  its own by `league-lab signals`; `league-lab signals-backtest` (read-only) calibrates the scenario and measures the
  alerts' precision with the rule as it runs in season (no routes). New `intermediate.int_player_game_role` (every
  QB–TE on a weekly roster × each played team game, missed games with their reason), `ops.player_role_alerts`
  (2016–2026, 7,074 rows; the season rewritten each run, other seasons when their `signals_version` differs),
  `ops.player_scenarios`, `ops.waiver_upside` (written by the waiver engine right after `ops.waiver_moves`), views
  `mart_player_role_alerts` / `mart_player_scenarios` / `mart_waiver_upside` (`signals.yml`, `assert_waiver_upside_is_legal`).
  Pages: Trends opens with **Role alerts this week** (up to three cards — your players, free agents with a bigger role,
  then the rest — every alert in an expander), the Player card ends with **Signals** (role, cause, expiry, the
  what-if in this league's scoring with its backtest hit rate), Waiver Wire's third card region is the **upside
  stash** (replacing "arrive with the role alerts"); Receivers and Kickers copy (why each number matters, worked
  examples from the selection, yardsticks computed from the selected season's top 12, chart captions saying what a
  good position looks like). `app/lib/signals.py` holds the shared phrases; COLUMNS `# ---- C6 signals` block.
* **Alerts.** A detected role change with a stated cause: `kind` role_up / role_down / absence_beneficiary /
  depth_move / new_team, `cause_text`, evidence before → after, `games_held` 1–3, `expires_after_week` (+ the
  absence rule "ends when X returns", live in `mart_player_role_alerts.trigger_ended` / `is_live`). Known cases fire in
  the right week with the right cause: Chase Brown 2024 wk 9 ("Zack Moss out injured", snaps 36% → 80%), Cedric Tillman
  2024 wk 7 ("Amari Cooper traded", targets 1% → 25%), Drake Maye 2024 wk 6 and Jaxson Dart 2025 wk 4 (depth_move,
  "Jacoby Brissett benched" / "Russell Wilson benched"), Rico Dowdle 2025 wk 5 ("Chuba Hubbard out injured"; nothing
  in wk 7 when Hubbard was back), TreVeyon Henderson 2025 wk 9, Amari Cooper 2024 wk 7 (new_team, snaps 89% → 35%).
  Controls: Ja'Marr Chase 2024 wk 10 (49.9 points) and Kyle Pitts 2025 wk 15 (40.1) — no alert all season; 43 of 44
  big 2024–25 weeks by established players fired nothing. **Precision, 2025 first detections, still real three games
  later: bigger roles 120 / 180 = 66.7% (29 more expired as designed: the starter came back), smaller roles 77 / 120 =
  64.2%** (2023 75.5% / 71.6%, 2024 75.0% / 59.6%). ra1.1 over ra1.0 (what the branch first had): a structural share
  (snaps / routes) must move, 1.5 bar with a named reason, no one-game drop without one, expired fill-in roles
  suppressed, depth-chart moves as a reason — 2025 up precision 57% → 67%.
* **This week** (data through week 2 for 30 teams, week 3 for 2): 8 live alerts in each league among rostered players
  and free agents, e.g. Aaron Jones (MIN) "Filling in: snap share 46% → 81%, carry share 35% → 82% since week 2 (one game
  so far). Why: Jordan Mason out injured" — rostered in both leagues; free agents Konata Mumpfield, Myles Price, Ben
  Sinnott (+ Germie Bernard, Kaleb Johnson in League of Scrubs).
* **Scenario upside.** Base = the stored projection (refitted component models; `project` checks every base to
  1e-6: max diff 0.0 on 26 rows); larger role = his last-3 inputs at the new role's level, capped at the position's
  90th percentile, efficiency held, priced per league; `with_alert_points` = base + hold rate (69.5% / 76.4% / 81.4%) ×
  gap. **Backtest 2023–2025** (models fitted on the seasons before; next-3-game PPG): the larger role was nearer than
  the projection 45.6% of the time at one game held (n = 285), 47.4% at two (n = 266), 72% at three (n = 18); the
  "with the alert" line 47.0% / 48.1%; mean miss 3.34 / 3.37 / 3.31 (base / larger / with) at one game. **Shipped as a
  "what if"** with the hit rate on the page, no probability (`SCENARIO_SHIP = False`). On average those players did
  outscore the projection by about the gap (+1.12 vs +1.04 at one game held): recorded for the next iteration.
* **Upside stash** = free agents with a live scenario whose horizon gain at their projection is ≤ 0 (the start-now /
  cover lists carry the rest), valued as B3 does at the projection and "if it holds", B3's drop rule: 81 rows, 22
  rosters, 8 free agents this week (none would start for its roster even if the role holds; the card says so); the
  positive case is `test_upside_stash_valued_at_base_and_if_it_holds` (+2.0 a week at FLEX).
* **Checks.** `ops.projections` byte-identical across a `project` with the hook (md5 weeks 4–18 `1a6e0c16…`, weeks
  1–3 `5396dcb9…`, 17,164 / 3,554 rows), `ops.lineups` proposed and `ops.waiver_moves` too; two consecutive `project`
  runs give identical C6 tables (md5 excluding `run_at` / `as_of`); `project` ≈ 250–285 s here (signals step 23–25 s);
  pytest 598 passed (27 in `tests/test_signals.py`), ruff clean, dbt `project` select 104 PASS, the headless check (35 runs) on every page ×
  both leagues + the Player page (alert, no alert, K, smaller role): 0 exceptions; Playwright at 390 × 844 (phone UA)
  and 1300 × 900 for Trends and Waiver Wire on both leagues, the Player card (alert, no alert, K, smaller role),
  Receivers and Kickers (League of Scrubs), every expander opened: no sideways scroll, no table wider than the
  viewport, cards before tables.
* **Decisions** (PO to confirm): (1) alerts in Python (`signals.py`), not a dbt model: the rule walks windows of 1–3
  games per player with teammate lookups and needs the fitted models for the scenario anyway; (2) the scenario refits
  the four positions' component models in the hook (≈ 25 s) instead of reaching into `project()`'s locals — the brief
  allows one call only; the refit is deterministic and checked against the stored projection; (3) the larger role uses
  the level observed since the change (capped at the position's p90), not "the absent teammate's share + his" — it
  covers depth moves and trades the same way, and the teammate's share is already in the games since; (4) the upside
  list is its own table (`ops.waiver_upside`, `list_kind = 'upside'`), so `ops.waiver_moves`, its tests and B3's page
  region are untouched; (5) scenarios only for players with a live bigger-role alert (no alert → "no role change
  detected"); (6) `mart_player_role_alerts` appended to the Makefile `project` and nightly projection-marts `--select`
  (the scenario and upside views were already descendants); (7) `metric_registry` rows not added (seeds are out of
  bounds): `role_alert` ra1.1 and `scenario_upside` sc1.0 would be the two.
* **Open.** The what-if is not calibrated to be shown as a chance (by design); the scenario's gap is too big for WR and
  too small for QB/TE on average — a position-specific shrink is the next step if it is wanted. Depth charts exist from
  2025 only, so `depth_move` by depth chart (not benching) starts there. A depth-chart promotion before the player has
  played (a Wednesday "named starter") is not an alert yet.

## Wave D (Iteration 12)

Projection v3, round 1: D1 (the feature-group harness) + D2 (game context) · D3 (weather) · D4 (team volume
and style). Each dev appends a section below; nothing edits `mart_player_week_features` until the PO keeps a group.

### D1 — feature-group harness (dev/D1)

* `league-lab experiment <group> [<group> ...] [--seasons 2023-2025] [--leagues ...]`, `--list`, `baseline`
  (`src/league_lab/experiments.py`); groups register in `src/league_lab/feature_groups/<family>.py` as
  `GROUPS = {name: {table, columns, positions, in_season, label, note}}`; the rule, the no-peek check and the
  outputs are in `docs/METRICS.md` § "Feature experiments".
* `projections.py` hooks, defaults unchanged: `load_frame(..., extra_tables=None)`, `fit_position(..., features=None)`
  (the model keeps `features`; `predict_position` uses them), `_matrix(d, features=None)`, and the walk-forward
  loop of `backtest` factored out as `walk_forward(...)` (same calls, same order).
* Results: `ops.feature_experiments` (DDL in `db.migrate`), `mart_feature_experiments` (view), Rankings →
  "The model" → "What we tried".
* Harness ready: `2baa78b` at 2026-10-01 12:40:56 UTC (19 min after the start); `29fdc2c` 12:45 UTC fixes boolean
  columns in the outcome probe (D3 / D4 told to take it).
* Defaults byte-identical (OMP_NUM_THREADS=1, same database): `ops.projections` 2026 weeks 4–18, every column but
  `fitted_at` / `frozen_at`, 17,164 rows, md5 `e6e45f116f5188f7dfdea2f4e1062120` from `league-lab project` on
  `2951c80` and on the hooked code; `league-lab backtest-v2 --seasons 2025`, the 432 `v2.0` rows of
  `ops.projection_backtest` but `run_id` / `run_at`, md5 `412207ebe4d71b8e69cf605820c53f8f` before (code of
  `2951c80`, run from an archive copy) and after.
* The harness's baseline reproduces `backtest-v2`: its 2025 season means equal the 2025 `v2_points` weekly means of
  `ops.projection_backtest` to 6 decimals in all 8 league × position cells (Spearman, MAE, coverage, interval score).
* Baseline (2023–2025, both leagues, 24 cells, key `cb461af0c56b4811`): 18 min 30 s wall on the shared box (load
  average ≈ 5: D3 and D4 fitting too), **9 min 19 s CPU** (single thread: what it takes alone). The PO's ~5 min
  estimate was low: a test season costs ~3 CPU-min for four positions (components + out-of-fold lines + 3 quantile
  models × 2 leagues per position). A group on fewer positions costs proportionally less.
* No-peek check on planted leaks (`tests/test_experiments.py::test_no_peek_check_catches_planted_leaks`, live DB):
  the week's own points as an input → refused at QB / RB / WR / TE (|r| 1.00 vs 0.34–0.48 with the adjacent weeks)
  plus the serve-gap warning; `pl_asof_week = week` → refused (as-of); an `in_season` column filled in week 1 →
  refused (week 1); an honest numeric + boolean pair passes. On the production inputs the largest probe excess is
  0.047 (limit 0.10).

### D2 — game context through the harness (dev/D1)

* `dbt/models/intermediate/features/int_player_week_game_context.sql` (+ `int_player_week_game_context.yml`, named
  after the model so the three branches' docs files never collide; `dbt/tests/assert_game_context_known_before_kickoff.sql`):
  109,123 rows = `int_player_week_universe`, unique index on the grain; 15 `gc_` columns, all from the published
  schedule (definitions, shares and the rest-day reconciliation with nflverse in `docs/METRICS.md` § "Game context").
  `dbt build` of the model + its tests: PASS=9 (unique grain, ranges, not-nulls, known-before-kickoff).
* Registered in `src/league_lab/feature_groups/game_context.py`: `game_context` (all 15), `rest` (5), `time` (6:
  weekday, kickoff hour, primetime, 1 pm window, time zones crossed, west-coast early), `venue` (4: dome, turf,
  division, neutral). The no-peek check passes (largest probe excess 0.019; no warnings: no serve gap).
* One session, `league-lab experiment game_context rest time venue` (baseline from the cache): 80 min 36 s wall on
  the shared box, 40 min 11 s CPU (≈ 10 CPU-min per four-position group).
* Harness table (mean over 2023–2025 of the league-averaged season Δ = group − baseline; "n/3" = seasons better):

| Group | Pos | ΔSpearman | better | ΔMAE (pts) | better | Δ interval score | Δ coverage (pp) | Δ width | Decision |
|---|---|---|---|---|---|---|---|---|---|
| game_context | QB | +0.0012 | 1/3 | −0.013 | 1/3 | −0.0073 | −0.62 | −0.18 | drop |
| game_context | RB | +0.0001 | 1/3 | +0.008 | 1/3 | +0.0008 | +0.84 | +0.06 | drop |
| game_context | TE | −0.0020 | 0/3 | +0.017 | 0/3 | +0.0019 | −0.23 | +0.02 | drop |
| game_context | WR | +0.0004 | 2/3 | +0.000 | 1/3 | −0.0009 | −0.21 | −0.08 | drop |
| rest | QB | +0.0029 | 2/3 | +0.004 | 2/3 | −0.0038 | −0.35 | −0.01 | drop |
| rest | RB | −0.0004 | 0/3 | −0.011 | 2/3 | −0.0017 | +0.62 | +0.01 | drop |
| rest | TE | +0.0002 | 2/3 | +0.008 | 1/3 | +0.0037 | +0.04 | +0.02 | drop |
| rest | WR | +0.0012 | 3/3 | +0.002 | 1/3 | −0.0014 | −0.37 | −0.13 | drop |
| time | QB | −0.0012 | 1/3 | +0.007 | 1/3 | −0.0027 | +0.50 | +0.21 | drop |
| time | RB | −0.0002 | 1/3 | +0.005 | 1/3 | +0.0002 | −0.16 | +0.00 | drop |
| time | TE | −0.0011 | 1/3 | +0.009 | 1/3 | +0.0036 | −0.19 | +0.03 | drop |
| time | WR | +0.0001 | 2/3 | +0.002 | 1/3 | −0.0008 | −0.53 | −0.09 | drop |
| venue | QB | +0.0035 | 1/3 | +0.011 | 1/3 | −0.0066 | −0.09 | −0.12 | drop |
| venue | RB | +0.0002 | 3/3 | +0.004 | 1/3 | +0.0018 | +0.09 | +0.05 | drop |
| venue | TE | −0.0019 | 1/3 | +0.012 | 0/3 | +0.0035 | −0.11 | +0.00 | drop |
| venue | WR | +0.0006 | 2/3 | −0.007 | 2/3 | −0.0013 | −0.42 | −0.13 | drop |

* Group verdict: **drop** for all four (no position helps, none hurts: every |mean ΔSpearman| < 0.004, every
  |mean ΔMAE| < 0.02 points, against bars of 0.005 and 0.05). The QB swings are fit noise, not signal: every group
  adds +0.010 to +0.017 to QB in 2023 and gives it back in 2024–2025 (≈ 670 QB player-weeks a season), which is what
  the 2-of-3 rule is for. **Recommendation: drop game context at every position**: v2 already sees the Vegas
  implied total, spread and total, which price kickoff, rest, travel and venue. The interval does not sharpen
  either (Δ interval score within ±0.0073 against 0.64–1.80 points). The table stays as a building block (the
  K/DEF model or D6's per-role variance could use the dome / kickoff columns); nothing reads it in production.

### D4 — team volume and style (dev/D4, clone `league_lab_d4`, 2026-10-01)

* **Built.** Three intermediate tables under `dbt/models/intermediate/features/` (docs: `team_style.yml`, METRICS §
  "Team volume and style", DATA_MODEL § "Feature group `team_style`"): `int_team_game_style` (offense × game facts
  from `fct_play` + team stats: plays, dropbacks, neutral plays / dropbacks, nflfastR xpass, snap-to-snap pace, time
  of possession from the game clock, drives, drive points, scoring drives, red-zone trips, first downs, giveaways;
  5,588 rows 2016–2026), `int_team_week_style` (team × REG week incl. byes and unplayed weeks, 6,176 rows: offense
  `off_` and defense-allowed `def_` × 12 metrics × season-to-date / last 4 / last season, shrunk
  (n × window + 3 × last season) / (n + 3), n = games this season before the week), `int_player_week_team_style`
  (the group's table, 109,123 rows = the universe: `ts_off_*` his offense, `ts_def_*` this week's opponent defense,
  52 inputs incl. `ts_pace_product` and `ts_pass_env`, plus `ts_off_asof_week` / `ts_def_asof_week` for the
  harness's as-of check). Macro `ts_shrink` / `ts_sums` (`dbt/macros/team_style.sql`). Groups registered in
  `src/league_lab/feature_groups/team_style.py`: `team_style` (52), `team_style_volume` (7), `team_style_pass_rate`
  (5), `team_style_efficiency` (14), `team_style_defense_faced` (24), plus `team_style_lean` (3, see below).
  Nothing in production reads the tables; the nightly's full `dbt build` builds them (≈ 25 s) — no `--select` added.
* **Tests.** dbt: 17 — 16 data tests (keys; counts nest; clock in range; `team_week_style_is_asof` / `player_team_style_is_asof`
  (asof_week < week); `assert_team_style_is_asof` (game counts and plays per game re-derived from `fct_play` on its
  own path, shrinkage included: 0 rows); `team_week_style_week1_is_last_season`; rates in range;
  `assert_team_style_covers_universe` (one row per universe row, his team's and his opponent's numbers); and a dbt
  **unit test** of the shrinkage on a fixture, 22 expected rows incl. the last-4 window, a playoff game that must not
  count, a team without a last season (league prior) and a season without any prior) — the 17th. Negative controls: weight 2
  instead of 3 → the unit test fails; `week <= W` instead of `< W` → unit test fails, and with the data tests alone
  `team_week_style_is_asof` 5,344, `player_team_style_is_asof` 100,443, `week1_is_last_season` 318,
  `assert_team_style_is_asof` 5,344 failing rows. pytest `tests/test_team_style.py` 21 (twins of the shrinkage and the
  neutral situation on fixtures, the SQL hard-codes the same constants, the unit test's expected rows follow the
  twin, the groups validate with `experiments.check_spec`, every column documented).
* **League sanity, 2025** (pooled): plays per game 60.3 (band 58–68 ✓); time of possession 30.2 min per team-game
  (OT included; 2,332 of 2,637 regulation games sum to 60:00 ± 15 s) ✓; seconds per play 31.8; **neutral pass rate
  53.2% — below the plan's 55–62% band** with the plan's own definition (1st/2nd down, Q1–3, within 7); the same
  filter over all downs gives 58.5% (third downs are passes). Kept the early-down definition (it is the
  coaching-choice signal); PO to confirm.
* **Hand-check, DET 2025 week 6** (`raw.nfl_pbp` / `raw.nfl_team_stats_week`, not through `fct_play`;
  `scratchpad/waveD/d4/handcheck.sql`): DET's weeks 1–5 plays 64 + 58 + 65 + 54 + 59 = 300 → 60.0 a game; 2024
  (the prior) 1,097 / 17 = 64.529; (5 × 60.0 + 3 × 64.529) / 8 = **61.698** = `off_plays_pg_std` 61.6985; last 4
  (58 + 65 + 54 + 59) / 4 = 59.0 → (295 + 193.588) / 8 = **61.074** = `off_plays_pg_l4`. Neutral pass rate: neutral
  dropbacks 1 + 17 + 15 + 7 + 11 = 51 of 2 + 30 + 39 + 17 + 24 = 112 plays = 0.4554; 2024 192 / 383 = 0.5013;
  (5 × 0.4554 + 3 × 0.5013) / 8 = **0.4726** = `off_neutral_pass_rate_std`. First downs (team stats, pass + rush)
  15 + 25 + 23 + 14 + 22 = 99 (play-by-play first downs on the same plays: also 99) → 19.8; 2024 386 / 17 = 22.706;
  (99 + 68.118) / 8 = **20.890** = `off_first_downs_pg_std` 20.8897. `off_asof_week` = 5.
* **Coverage** (`int_player_week_team_style` vs the universe, offense / defense numbers known): 2016 8,993 of 9,851
  (week 1 has no earlier season), 2017–2026 100% (9,681 · 9,373 · 9,608 · 9,800 · 10,538 · 10,161 · 10,034 · 9,898 ·
  10,268 · 9,911).
* **What the market already knew** (4,766 team-games 2017–2025; `scratchpad/waveD/d4/market_corr.py`, full table in
  `market_corr.csv`): r with the implied team total / game total — points per drive 0.67 / 0.49, yards per play
  0.64 / 0.50, first downs 0.62 / 0.49, red-zone trips 0.60 / 0.42, scoring drives 0.64 / 0.45, sacks per dropback
  −0.43 / −0.30, time of possession 0.31 / 0.08, neutral pass rate 0.29 / 0.24, PROE 0.26 / 0.26, `ts_pace_product`
  0.25 / 0.16, plays 0.22 / 0.17, pace −0.04 / −0.10; defense side 0.0–0.38. Beyond the lines (partial r with what
  then happened, implied total and total held fixed): efficiency adds ≈ 0 to drive points (−0.01 to +0.02); plays
  per game +0.11 and pace −0.12 to the plays run; PROE +0.25, `ts_pass_env` +0.21, neutral pass rate +0.20 to the
  dropback share (the implied total itself: −0.03). New information exists at the team level — in volume and in
  pass/rush split, not in efficiency.
* **Harness** (`league-lab experiment …`, D1's walk-forward, test seasons 2023–2025, both leagues, `OMP_NUM_THREADS=1`;
  baseline 1,216 s, then 1,898 / 1,295 / 1,169 / 741 / 669 / 554 s on a box shared with two other fits). Mean over
  seasons of the league-averaged Δ (group − baseline); "better" = seasons of 3:

  | group | pos | Δ Spearman (better) | Δ MAE (better) | Δ interval score | decision |
  |---|---|---|---|---|---|
  | team_style (52) | QB / RB / WR / TE | −0.0026 (1) / −0.0024 (0) / −0.0010 (1) / −0.0055 (0) | +0.015 / +0.032 / +0.023 / +0.008 | +0.000 / +0.005 / +0.001 / +0.005 | drop ×4 |
  | volume (7) | QB / RB / WR / TE | +0.0004 (1) / −0.0019 (0) / +0.0001 (2) / −0.0017 (2) | +0.016 / +0.020 / +0.003 / +0.009 | −0.002 / −0.000 / +0.000 / +0.003 | drop ×4 |
  | pass_rate (5) | QB / RB / WR / TE | **+0.0096 (3)** / −0.0012 (0) / +0.0005 (2) / −0.0009 (2) | **−0.014 (2)** / +0.004 / −0.004 (3) / +0.015 | **−0.009** / −0.003 / −0.001 / +0.002 | **keep QB**, drop RB / WR / TE; verdict keep |
  | efficiency (14) | QB / RB / WR / TE | +0.0011 (1) / −0.0002 (1) / −0.0005 (1) / −0.0038 (0) | +0.004 / +0.007 / +0.009 / +0.008 | −0.001 / +0.002 / +0.001 / +0.006 | drop ×4 |
  | defense_faced (24) | QB / RB / WR / TE | −0.0035 (1) / −0.0029 (0) / −0.0003 (1) / −0.0031 (1) | +0.016 / +0.006 / +0.008 / +0.006 | +0.004 / +0.006 / +0.003 / +0.005 | drop ×4 |
  | lean (3) | QB / RB / WR / TE | +0.0024 (1) / −0.0017 (0) / −0.0001 (1) / +0.0024 (3) | −0.011 / +0.006 / +0.001 / +0.005 | −0.012 / −0.000 / −0.000 / +0.002 | drop ×4 |

  Baseline (v2, mean of the two leagues and three seasons): Spearman QB 0.534, RB 0.683, WR 0.624, TE 0.583; MAE
  7.08 / 4.44 / 4.40 / 3.22. No no-peek failures or warnings on any group. Coverage changes ≤ 1 point everywhere.
* **The one keep does not hold up on earlier seasons.** `team_style_pass_rate` at QB is a keep by the rule (+0.017,
  +0.002, +0.010; 3 of 3), but every group, even the full 52-input one, gains +0.009 to +0.020 at QB in 2023 (QB
  weeks have ~32 players: the season-to-season noise is about ±0.01). Re-run QB-only on 2021 and 2022 with the
  harness's own pieces (`walk_forward` + `summarize_scores`; 2023 reproduced exactly: +0.0164 / +0.0180,
  `scratchpad/waveD/d4/qb_extend.py`): **2021 −0.0049, 2022 −0.0054** (MAE −0.032, +0.047). Over 2021–2025 the mean
  is +0.0037, better in 3 of 5 — the rule's 5-season version (≥ +0.005 and 4 of 5) says drop.
* **The two hypotheses, below the points** (component models alone, same walk-forward, Poisson counts, MAE change
  vs v2, seasons better of 3; `scratchpad/waveD/d4/component_check.py`): *volume helps RB / WR counts* — no: RB
  carries +0.19% (1), RB targets −0.10% (3), WR targets −0.20% (2), TE targets −0.14% (2), all well under a percent;
  *defense faced helps the pass / rush split* — no: QB attempts −0.30% (1), QB carries +0.50%, RB carries −0.01%,
  WR targets −0.05%. What does move the split is the offense's own pass rate: QB attempts −1.08% (2; deviance 2) with
  `pass_rate`, −0.86% (3) with `volume`. Why so little: v2 already sees each player's attempts / targets / carries
  per game (season, last 3, last season), which are team plays × pass rate × his share — the team numbers are new
  only for a player whose history is short or whose team changed.
* **Recommendation: drop** `team_style` and its sub-groups for v3; at most keep `team_style_pass_rate` for QB **only
  if** the PO accepts the 2023–2025 rule result over the 2021–2022 check (I would not). Revisit pass rate with D5's
  QB-change inputs (a new starter changes the pass rate the history was built on). The tables can stay: they cost
  ≈ 25 s a night, and they are the natural home for a "this offense throws a lot / runs fast" line on the Player
  card if the PO wants one (not built).
* **For the PO to confirm.** (1) A third model, `int_team_game_style`, beside the two named in the brief (the per-game
  facts, reused by both sides and the hand-check). (2) The early-down neutral pass rate (53.2% in 2025) vs the plan's
  55–62% band. (3) The last-4 window shrinks with the season's game count (both windows weigh this season
  n / (n + 3)), so week 2's last 4 equals its season to date. (4) `ts_pass_env` is divided by the league's rate
  (log5-style), not the bare product. (5) PROE uses nflfastR's xpass (league mean −2.2% in 2025: the model's
  training years passed more). (6) `team_style_lean` was added: its three inputs were chosen on 2017–2025 team-level
  correlations, which include the test seasons (it dropped anyway). (7) No `metric_registry.csv` rows (seeds are out
  of bounds this round): add `team_style` v1.0 at merge if the PO keeps anything. (8) The `ops.feature_experiments`
  rows (24 baseline + 144 group rows) live in the `league_lab_d4` clone only.
* **Verified.** `dbt build` of the three models: PASS=20 (3 models + 17 tests); `pytest` 732 passed (before the lean group) / see the hand
  back for the final count; `ruff` clean; headless page check (both leagues, 13 pages each + 6 Player runs): 32 runs,
  0 exceptions, 0 errors. No page touched.
### D3 2026-10-01 — weather: Open-Meteo loader, stadium reference, the `weather` feature group (branch `dev/D3`, clone `league_lab_d3`)

* **Built.** `src/league_lab/ingest/weather.py` + `league-lab ingest weather [--seasons] [--forecast] [--offline] [--force]`:
  Open-Meteo hourly weather at the stadium for the kickoff hour and the two after → `raw.nfl_weather`
  (`source = 'archive'`: ERA5, **one call per stadium-season**, one row per game; `'forecast'`: one call per stadium
  per run for its games in the next 16 days, one row per game **per fetch, never deleted**). Archive under
  `data/raw/open_meteo/{archive/<season>/<stadium>.json.gz, forecast/<season>/<stadium>/<time>.json.gz}` with the
  usual sidecars, `--offline` replay, manifest source `open_meteo` (partitions `<season>:<stadium>`); a stadium-season
  is re-fetched only when a played game (older than the archive's 5-day delay) is not in its file. Stadium reference
  `src/league_lab/ingest/reference/stadiums.csv` (49 venues: the 47 nflverse `stadium_id`s 2016–2026 + Croke Park and
  Berlin's Olympiastadion; lat / lon from the Wikipedia / GeoHack infoboxes, time zone, roof type, tenants, every name
  nflverse used) and `stadium_game_venues.csv` (the seven 2025 international games nflverse records at the home
  team's stadium) → `raw.nfl_stadiums` / `raw.nfl_stadium_game_venues`, loaded by `db migrate`. dbt:
  `intermediate.int_game_weather` (game grain: venue, roof decision, the value and its source / known-at time, each
  source's numbers side by side) and `intermediate.int_player_week_weather` (contract grain: `wx_dome`,
  `wx_wind_mph`, `wx_gust_mph`, `wx_precip_in`, `wx_temp_f`, `wx_cold`, `wx_windy`, `wx_snow`, `wx_source`),
  `int_player_week_weather.yml`, tests `assert_weather_dome_rows_zero`, `assert_weather_never_peeks`,
  `assert_weather_one_row_per_universe_row`, `assert_stadium_reference_covers_schedules` (warn). Groups for the
  harness: `src/league_lab/feature_groups/weather.py` (`weather`, `wind`, `temp`, `dome`). K/DEF hook:
  `kdef.WEATHER_FEATURES` (`wx_wind_mph`, `wx_dome`), off in kd1.0, `league-lab backtest-kd --weather` (report only).
  Docs: SOURCES § Open-Meteo (+ licence), METRICS § Weather (+ the train / serve gap and how to measure it),
  DATA_MODEL (raw + intermediate), HOSTING § Weather in the nightly (the two lines for `nightly.sh`).
* **Evidence.**
  - Stadium coverage: every `stadium_id` in the archived `games.parquet` 2016–2026 is in the CSV, every game
    resolves to a venue, every home game resolved by id has its home team as a tenant that season, and no kickoff
    before 10:00 ET sits at a US venue (`tests/test_weather.py::test_stadium_reference_covers_every_schedules_stadium`);
    the same in dbt on the database (`assert_stadium_reference_covers_schedules`: PASS). Resolution on 3,033 games
    2016–2026: 3,025 by id, 7 per-game corrections, 1 by name (2026_05_PHI_JAX → Tottenham).
  - Loader on fixtures (hand-built from Open-Meteo's documented response format — the API is blocked here; never
    fetched): 17 tests. Batching: 7 archivable games at 5 stadium-seasons → **5 calls** (BUF00 2024's three games in
    one); a game inside the 5-day delay waits; a second run makes 0 calls (`skipped_unchanged`); a newly archivable
    game re-fetches only its stadium-season; `--offline` rebuilds identical rows with a client that fails on any
    request; two forecasts of one game → two rows (77.0 h and 53.0 h ahead), kept after the archive arrives and
    after a forecast file is lost; HTTP 400 → `failed`, nothing written, no file left. Worked example
    (2024_01_ARI_BUF fixture, 13:00 EDT = 17:00 UTC): wind 12/15/18 → 15.0, temp 61/63/65 → 63.0, gusts at 18–20 UTC
    21/27/24 → 27, precipitation 0.02 + 0.05 + 0.01 = 0.08.
  - On the database: the staged fixtures replayed with `ingest weather --offline` → 3 partitions `success` (archive
    2024:BUF00, 2025:DUB00, forecast 2026:BUF00, 1 row each), again → 3 × `skipped_unchanged`; `int_game_weather` then
    took `archive` for 2024_01_ARI_BUF (over the schedules' 20 mph / 61 °F) and for 2025_04_MIN_PIT (at DUB00, not
    PIT00), `forecast` (77 h ahead) for 2026_04_NE_BUF; 17 dbt tests PASS. The demo rows were deleted afterwards
    (the evaluation below runs on the schedules' observations only).
  - Feature table: 109,123 rows = `int_player_week_universe`; dbt build 2 models + 21 tests PASS. Hand check:
    Josh Allen 2024 wk 16 (NE at BUF, schedules 14 °F / 2 mph) → `wx_temp_f` 14, `wx_wind_mph` 2, `wx_cold` 1,
    `wx_source` nflverse_observed; wk 15 at DET → `wx_dome` 1, every value 0.
  - Coverage (player-weeks, open-air with wind and temperature / dome / unknown): 2016 7,401 / 2,358 / 92 ·
    2017 7,245 / 2,251 / 185 · 2018 7,015 / 2,182 / 176 · 2019 7,139 / 2,198 / 271 · 2020 6,370 / 3,430 / 0 ·
    2021 7,033 / 3,081 / 424 · **2022 3,627 / 3,156 / 3,378** · 2023 5,512 / 3,033 / 1,489 · 2024 6,306 / 3,404 / 188 ·
    2025 6,632 / 3,439 / 197 · 2026 780 / 3,331 / 5,800 (upcoming weeks: no forecast here). Precipitation and gusts:
    NULL outdoors until the first real run.
  - Data sanity (2016–2025 team-games, schedules' wind): passing yards per team-game 253.5 dome · 243.7 under 10 mph ·
    231.4 at 10–14 · 221.6 at 15–19 · 210.7 at 20+ (YPA 7.43 → 6.73); kicker 50+ makes per game 0.348 dome → 0.244
    → 0.218 → 0.227 → 0.147. The effect is real; the question is whether the model lacks it (the Vegas total prices it).
* **Feature-group evaluation (local; the D1 harness could not be merged here, see Decisions).** Walk-forward test
  seasons 2023–2025, the v2 model with the group's columns added (nothing else changed), both leagues' scoring,
  Spearman / MAE of `proj_points` per league-season-week-position and the 80% interval score, paired across the
  three seasons (keep = mean Δ beyond 2 × its standard error). Δ vs v2, mean of 3 seasons (League of Scrubs |
  Dynasty):

  | Group | QB Δ Spearman | RB | WR | TE | QB Δ MAE | RB | WR | TE | Verdict |
  |---|---|---|---|---|---|---|---|---|---|
  | weather (8 columns) | +0.003 \| +0.001 | −0.000 \| −0.000 | +0.000 \| −0.000 | −0.001 \| −0.001 | +0.002 \| +0.005 | +0.005 \| +0.005 | +0.002 \| −0.000 | +0.006 \| +0.005 | drop: noise (Scrubs TE MAE worse in 3/3) |
  | wind | +0.001 \| +0.003 | +0.000 \| −0.000 | +0.000 \| −0.000 | −0.001 \| +0.000 | +0.020 \| +0.029 | +0.003 \| +0.001 | −0.003 \| −0.004 | +0.007 \| +0.006 | drop: noise (TE MAE worse 3/3 both leagues) |
  | temp | +0.002 \| +0.004 | −0.001 \| −0.001 | −0.000 \| +0.000 | −0.003 \| −0.001 | +0.012 \| +0.014 | +0.007 \| +0.005 | −0.001 \| −0.004 | +0.014 \| +0.013 | drop (TE worse) |
  | dome | −0.001 \| +0.002 | −0.001 \| −0.001 | −0.000 \| +0.000 | −0.004 \| −0.003 | +0.013 \| +0.008 | +0.004 \| +0.004 | +0.003 \| +0.002 | +0.007 \| +0.008 | drop (RB, TE worse) |

  Baseline (v2) means: Spearman QB 0.539 | 0.528, RB 0.681 | 0.686, WR 0.617 | 0.631, TE 0.575 | 0.591. Interval
  score Δ within ±0.3 everywhere (QB weather −0.03 | −0.29, the only gain, not beyond noise). Fit time per test season
  ~7 min with three devs on 2 cores. Rows: `scratchpad/waveD/d3/weather_eval_rows.csv`, summary
  `weather_eval_summary.csv`, script `eval_weather.py`.
* **K / DEF with weather** (`backtest-kd` vs `backtest-kd --weather`, wind + dome added, 2021–2025, League of Scrubs):

  | | 2021 | 2022 | 2023 | 2024 | 2025 | all |
  |---|---|---|---|---|---|---|
  | K Spearman kd1.0 → +wind | 0.186 → 0.185 | 0.077 → 0.056 | 0.105 → 0.134 | 0.180 → 0.202 | 0.147 → 0.170 | **0.139 → 0.149** |
  | K MAE | 3.64 → 3.64 | 3.56 → 3.61 | 3.63 → 3.62 | 3.87 → 3.86 | 3.83 → 3.81 | 3.71 → 3.71 |
  | DEF Spearman | 0.263 → 0.261 | 0.165 → 0.172 | 0.249 → 0.243 | 0.316 → 0.319 | 0.332 → 0.334 | 0.265 → 0.266 |
  | DEF MAE | 4.70 → 4.72 | 4.44 → 4.43 | 4.92 → 4.91 | 4.51 → 4.50 | 4.61 → 4.60 | 4.64 → 4.63 |

  K: +0.010 on average (+0.022 to +0.029 in 2023–2025; −0.021 in 2022, the season with 91 of 198 open-air games
  missing their wind), standard error 0.009 — not beyond noise yet; MAE flat; top-10 hit 40.3% → 40.1%. DEF: nothing.
* **Recommendation.** Keep nothing for QB–TE now (weather, wind, temp, dome: Δ Spearman within ±0.004 everywhere,
  TE MAE slightly worse — the Vegas total already carries the weather). Do not ship K wind yet (kd1.0 stays). Re-run
  both after the first real Open-Meteo run: it fills the 2022–2023 holes, adds precipitation and gusts and puts every
  season on one definition; K wind is the candidate (wind + the kicker's range is where the data shows the effect),
  shipped as kd1.1 only if it stays ahead in 4 of 5 seasons with the gap beyond 2 × its standard error.
* **Decisions** (PO to confirm): (1) **the D1 merge was refused by the permission system in this session** (the
  task also says "do not merge"), so the harness table is a local evaluation with the same model and scorer; the
  group file follows D1's announced format (`GROUPS = {name: {table, columns, label, note}}`, no `in_season`), so after
  integration `OMP_NUM_THREADS=1 OMP_WAIT_POLICY=PASSIVE uv run league-lab experiment weather wind temp dome` produces
  the harness table; (2) the CSVs live in `src/league_lab/ingest/reference/` (`.gitignore`'s `data/` would hide
  `src/league_lab/data/`); (3) `wx_source` has a fifth value, `dome`; (4) a retractable roof not decided yet counts as
  **closed** (89% of 2016–2025 retractable games); the stadium reference beats nflverse's roof for fixed roofs (MCG,
  Stade de France, Munich are open-air); (5) gusts / precipitation / snowfall are read at k+1..k+3 (Open-Meteo reports
  them for the preceding hour), wind / temperature at k..k+2 — both cover the game's first three hours; (6) archive
  rows are written for every game the file covers (closed-roof games included; dbt decides), forecast rows for every
  game at the stadium not yet kicked off; (7) `db.migrate()` gains one call (`weather.ensure_tables`) so dbt resolves
  venues before any weather is fetched; (8) the coverage test is a dbt **warning** (a new venue in a future schedule
  must not stop the nightly), the pytest is the hard check; (9) an extra model, `int_game_weather` (game grain), sits
  under `features/` next to the contract table; (10) `cli.py`: `ingest weather`, `backtest-kd --weather`.
* **Open.** (a) The first real run (Mac or Actions): `uv run league-lab ingest weather --forecast` — 280 archive calls
  for 2016–2026 (~8 min, ~1,300 weighted calls of the 10,000/day free tier) + ~23 forecasts; the first contact with
  the live API (the fixtures follow the docs; a renamed variable would show as a `failed` partition). (b) The PO adds
  the two `nightly.sh` lines (HOSTING § Weather in the nightly). (c) Precipitation stays NULL until (a) — the harness
  treats NULL as unknown; re-run the groups after it. (d) Forecast history lives only in the archive cache on
  Actions (a forecast cannot be fetched again): worth saving like the decision record (`data/raw/record/` or the
  hosted sync) before the gap measurement depends on it. (e) The Kickers page "wind is the reason" line waits for a
  shipped kd1.1. (f) `metric_registry.csv` rows for the `wx_` features (seeds were out of bounds for this round).

### D6 2026-10-01 — sharper ranges and decisions (branch `dev/D6`, clone `league_lab_d6`)

Andrew: "if an 80% confidence interval is like a 20-point spread, how useful is that?". Definitions, the
experiment and the calibration are in `docs/METRICS.md` § "Ranges and decisions"; this section is the evidence.

* **Built.** (1) The **50% range** `p25` / `p75` ("most weeks"): two more residual quantile regressors (0.25,
  0.75) per position × league in `projections.fit_position`, fitted after the P10 / P50 / P90 models (own seeds:
  those are bit-for-bit unchanged), split-conformal widened for 50% (`_conformal_widening`, now shared with the
  80% range), sorted and kept inside [P10, P50] / [P50, P90] in `predict_position`; new columns on
  `ops.projections` (B5 way: `db.py` migrate, the writer's DDL and the mart pre-hook each `alter table … add
  column if not exists`) and `mart_player_week_projections` (`p25`, `p75`, `actual_inside_50`; tests
  `projection_50_range_inside_80_range`, `projection_50_range_both_ends_or_neither`); `score_predictions`
  also returns `coverage_50` / `pinball_25` / `pinball_75` / `interval_width_50` (not persisted:
  `ops.projection_backtest` keeps its columns). (2) `src/league_lab/decisions.py`: P(A outscores B) from the
  two players' quantiles (piecewise-linear quantile function, exponential upper tail, Gaussian copula with the
  measured same-game correlations, 40,000-draw Monte Carlo, fixed seed). (3) `app/lib/cards.py`: the card
  headline is the probability ("Kenny Gainwell outscores Emanuel Wilson 53% of the time — a coin flip."), the
  margin second, then "Most weeks" and "A bad week to a good week"; Rankings' board column is "Most weeks"
  (P25–P75; the 80% "Range" on a week without it) and the full table gains the two columns. Docs: METRICS,
  DATA_MODEL (`ops.projections`, the mart), WORDS (four rows).
* **The experiment** (scripts `exp_cache.py` / `exp_fit.py` / `exp_score.py` / `exp_insea.py` /
  `exp_decide.py` in the session scratchpad `waveD/d6/`): walk-forward 2023–2025 in both leagues' scoring,
  components and out-of-fold lines fitted once per test season × position (12 min wall) and shared by every
  variant; 11 residual-model families × 1–7 conformal schemes = 30 variants (61 min wall for the family fits on
  the shared box, load 4–10).
  The v2 variant reproduces the harness's cached baseline (`ops.feature_experiments`, key
  `cb461af0c56b4811`) to four decimals in all 24 cells (e.g. League of Scrubs 2023 QB: interval score 1.2212,
  coverage 0.7326, width 17.729, Spearman 0.5257); the production code (`walk_forward` on 2025 QB) reproduces
  the experiment's v2 50% numbers exactly (pinball 2.2125 / 2.5062 Scrubs). Spearman is the same in every row
  (QB 0.533, RB 0.683, WR 0.624, TE 0.583: the point projection never moves). Mean over 2023–2025 × both
  leagues; "Top-N" = the board's top 24 RB / WR, top 12 QB / TE by projection each week:

| Variant | Pos | Interval score | Δ vs v2 | Coverage 80 | Width 80 | Top-N width 80 | Top-N coverage 80 | Coverage 50 | Width 50 | Top-N width 50 | Top-N coverage 50 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| v2 (production) | QB | 1.509 | +0.0% | 75.5% | 21.9 | 23.4 | 77.4% | 46.7% | 11.7 | 12.1 | 47.6% |
| (a) + role features (frame: SD/dud rate L16, TD share, receiving / rushing share) | QB | 1.508 | -0.1% | 75.3% | 21.8 | 23.2 | 77.4% | 46.6% | 11.8 | 12.4 | 48.4% |
| (a) + aDOT / deep-target share (WR, TE) | QB | 1.508 | -0.1% | 75.3% | 21.8 | 23.2 | 77.4% | 46.6% | 11.8 | 12.4 | 48.4% |
| (a) roleB + per-tail conformal | QB | 1.503 | -0.4% | 75.7% | 21.8 | 23.2 | 77.6% | 46.5% | 11.6 | 12.2 | 48.0% |
| (b) scale model x fixed shape | QB | 1.543 | +2.2% | 75.3% | 21.6 | 23.1 | 78.3% | 46.4% | 11.7 | 12.2 | 48.1% |
| (b) scale model, normalised conformal | QB | 1.566 | +3.8% | 75.3% | 21.9 | 23.5 | 78.7% | 46.4% | 11.8 | 12.4 | 48.1% |
| (b) scale model with role features, normalised conformal | QB | 1.561 | +3.4% | 75.6% | 22.2 | 24.1 | 79.2% | 46.3% | 11.8 | 12.5 | 49.2% |
| (c) per-tail conformal | QB | 1.510 | +0.0% | 75.5% | 21.9 | 23.4 | 77.5% | 46.1% | 11.5 | 11.9 | 47.0% |
| (c) conformal per projection tier (terciles) | QB | 1.509 | +0.0% | 75.8% | 22.1 | 24.1 | 78.8% | 47.2% | 11.8 | 12.2 | 48.1% |
| (c) conformal per role (deep/short WR-TE, receiving RB, rushing QB) | QB | 1.508 | -0.1% | 76.1% | 22.1 | 23.6 | 78.1% | 46.9% | 11.7 | 12.1 | 48.0% |
| (c) conformal per tier x role | QB | 1.512 | +0.2% | 76.3% | 22.4 | 24.7 | 79.5% | 47.8% | 12.0 | 12.5 | 49.2% |
| (a)+(c) roleB, per-tail, per tier | QB | 1.508 | -0.1% | 75.5% | 22.1 | 23.6 | 78.2% | 46.3% | 11.7 | 12.0 | 47.1% |
| (d) two-part: regulars / the rest | QB | 1.502 | -0.5% | 75.2% | 21.9 | 23.9 | 78.0% | 46.2% | 11.6 | 12.4 | 49.3% |
| (d) two-part, per-tail conformal | QB | 1.501 | -0.5% | 75.8% | 22.1 | 23.9 | 78.9% | 45.8% | 11.5 | 12.3 | 48.9% |
| in-season recalibration | QB | 1.508 | -0.1% | 75.6% | 21.9 | 23.4 | 77.4% | 47.0% | 11.7 | 12.2 | 47.8% |
| control: no features (residual quantiles by projection bin) | QB | 1.531 | +1.5% | 76.2% | 23.0 | 24.8 | 80.0% | 48.7% | 12.3 | 13.4 | 53.2% |
| regularised: early stopping | QB | 1.519 | +0.7% | 74.6% | 22.1 | 23.7 | 77.0% | 46.4% | 11.6 | 12.3 | 48.6% |
| regularised: leaf >= 200 | QB | 1.515 | +0.4% | 74.6% | 21.7 | 23.7 | 78.0% | 46.5% | 11.8 | 12.5 | 49.5% |
| v2 (production) | RB | 0.971 | +0.0% | 79.8% | 13.6 | 19.1 | 77.3% | 51.3% | 6.9 | 10.1 | 47.6% |
| (a) + role features (frame: SD/dud rate L16, TD share, receiving / rushing share) | RB | 0.969 | -0.2% | 79.9% | 13.6 | 19.2 | 77.8% | 51.2% | 6.9 | 9.9 | 47.3% |
| (a) + aDOT / deep-target share (WR, TE) | RB | 0.969 | -0.2% | 79.9% | 13.6 | 19.2 | 77.8% | 51.2% | 6.9 | 9.9 | 47.3% |
| (a) roleB + per-tail conformal | RB | 0.969 | -0.2% | 80.0% | 13.6 | 19.3 | 78.0% | 50.9% | 6.8 | 9.9 | 46.6% |
| (b) scale model x fixed shape | RB | 0.984 | +1.3% | 80.6% | 13.3 | 19.1 | 73.1% | 52.1% | 6.6 | 9.3 | 43.1% |
| (b) scale model, normalised conformal | RB | 0.985 | +1.5% | 80.6% | 13.3 | 19.3 | 73.6% | 52.5% | 6.7 | 9.5 | 44.3% |
| (b) scale model with role features, normalised conformal | RB | 0.981 | +1.1% | 80.9% | 13.4 | 19.6 | 74.7% | 52.1% | 6.8 | 9.7 | 44.8% |
| (c) per-tail conformal | RB | 0.970 | -0.1% | 80.2% | 13.6 | 19.1 | 77.4% | 51.0% | 6.9 | 10.0 | 47.4% |
| (c) conformal per projection tier (terciles) | RB | 0.971 | +0.0% | 79.9% | 13.8 | 19.9 | 79.5% | 51.3% | 7.2 | 11.0 | 51.0% |
| (c) conformal per role (deep/short WR-TE, receiving RB, rushing QB) | RB | 0.971 | +0.0% | 80.1% | 13.7 | 19.2 | 77.7% | 51.6% | 7.0 | 10.1 | 47.9% |
| (c) conformal per tier x role | RB | 0.971 | -0.0% | 80.2% | 13.9 | 20.0 | 79.8% | 51.3% | 7.2 | 11.0 | 51.4% |
| (a)+(c) roleB, per-tail, per tier | RB | 0.966 | -0.5% | 80.2% | 13.8 | 20.7 | 79.9% | 51.0% | 7.1 | 11.4 | 51.2% |
| (d) two-part: regulars / the rest | RB | 0.974 | +0.4% | 80.7% | 13.5 | 19.8 | 79.0% | 51.5% | 7.1 | 10.8 | 50.2% |
| (d) two-part, per-tail conformal | RB | 0.972 | +0.1% | 80.3% | 13.8 | 20.4 | 78.3% | 51.8% | 7.1 | 11.0 | 50.1% |
| in-season recalibration | RB | 0.971 | +0.0% | 79.9% | 13.6 | 19.1 | 77.3% | 50.7% | 6.9 | 10.1 | 47.6% |
| control: no features (residual quantiles by projection bin) | RB | 0.973 | +0.2% | 79.6% | 14.5 | 21.2 | 82.4% | 51.0% | 7.3 | 11.2 | 51.8% |
| regularised: early stopping | RB | 0.971 | -0.0% | 80.2% | 13.8 | 19.4 | 78.0% | 51.6% | 7.0 | 10.2 | 47.8% |
| regularised: leaf >= 200 | RB | 0.973 | +0.2% | 80.0% | 13.9 | 19.7 | 78.4% | 51.4% | 7.1 | 10.4 | 48.5% |
| v2 (production) | WR | 0.957 | +0.0% | 81.4% | 13.8 | 19.8 | 75.9% | 49.7% | 6.9 | 10.5 | 46.8% |
| (a) + role features (frame: SD/dud rate L16, TD share, receiving / rushing share) | WR | 0.954 | -0.3% | 81.5% | 13.6 | 19.7 | 76.1% | 49.4% | 6.9 | 10.5 | 46.9% |
| (a) + aDOT / deep-target share (WR, TE) | WR | 0.954 | -0.3% | 81.0% | 13.7 | 19.8 | 75.9% | 49.5% | 6.9 | 10.5 | 46.8% |
| (a) roleB + per-tail conformal | WR | 0.954 | -0.3% | 81.2% | 13.5 | 19.6 | 75.9% | 50.0% | 6.8 | 10.3 | 46.2% |
| (b) scale model x fixed shape | WR | 0.961 | +0.4% | 80.8% | 13.2 | 20.4 | 73.0% | 49.2% | 6.4 | 9.8 | 43.1% |
| (b) scale model, normalised conformal | WR | 0.961 | +0.4% | 80.8% | 13.2 | 20.3 | 73.0% | 49.3% | 6.4 | 9.7 | 42.6% |
| (b) scale model with role features, normalised conformal | WR | 0.960 | +0.3% | 80.7% | 13.2 | 20.3 | 73.1% | 49.1% | 6.4 | 9.7 | 42.9% |
| (c) per-tail conformal | WR | 0.957 | -0.0% | 81.5% | 13.6 | 19.6 | 75.7% | 50.1% | 6.8 | 10.4 | 46.4% |
| (c) conformal per projection tier (terciles) | WR | 0.956 | -0.1% | 81.1% | 14.3 | 21.3 | 79.7% | 49.6% | 7.2 | 11.1 | 49.0% |
| (c) conformal per role (deep/short WR-TE, receiving RB, rushing QB) | WR | 0.957 | -0.0% | 81.2% | 13.8 | 19.8 | 76.0% | 49.5% | 6.9 | 10.5 | 46.8% |
| (c) conformal per tier x role | WR | 0.956 | -0.1% | 81.3% | 14.3 | 21.4 | 80.1% | 49.8% | 7.2 | 11.1 | 49.7% |
| (a)+(c) roleB, per-tail, per tier | WR | 0.950 | -0.7% | 81.0% | 13.9 | 21.6 | 80.2% | 49.9% | 7.0 | 11.2 | 49.4% |
| (d) two-part: regulars / the rest | WR | 0.958 | +0.1% | 80.6% | 13.3 | 20.4 | 77.7% | 49.7% | 6.8 | 10.7 | 47.5% |
| (d) two-part, per-tail conformal | WR | 0.960 | +0.3% | 80.7% | 13.8 | 20.9 | 78.5% | 50.0% | 6.8 | 10.7 | 47.5% |
| in-season recalibration | WR | 0.957 | +0.0% | 81.0% | 13.7 | 19.7 | 75.9% | 50.1% | 6.9 | 10.5 | 46.8% |
| control: no features (residual quantiles by projection bin) | WR | 0.957 | -0.0% | 80.5% | 14.1 | 21.3 | 79.8% | 49.5% | 7.1 | 11.2 | 50.2% |
| regularised: early stopping | WR | 0.957 | +0.0% | 81.4% | 13.8 | 19.8 | 75.9% | 49.7% | 6.9 | 10.5 | 46.8% |
| regularised: leaf >= 200 | WR | 0.957 | -0.0% | 81.6% | 13.8 | 20.0 | 76.5% | 50.2% | 6.9 | 10.7 | 47.5% |
| v2 (production) | TE | 0.719 | +0.0% | 80.9% | 9.5 | 14.4 | 76.3% | 50.7% | 5.0 | 8.3 | 47.9% |
| (a) + role features (frame: SD/dud rate L16, TD share, receiving / rushing share) | TE | 0.717 | -0.2% | 80.8% | 9.5 | 14.8 | 76.6% | 51.7% | 5.0 | 8.3 | 49.3% |
| (a) + aDOT / deep-target share (WR, TE) | TE | 0.716 | -0.3% | 81.1% | 9.4 | 14.7 | 77.1% | 50.3% | 4.9 | 8.0 | 48.8% |
| (a) roleB + per-tail conformal | TE | 0.714 | -0.6% | 81.3% | 10.0 | 15.3 | 78.0% | 50.0% | 4.9 | 8.0 | 48.1% |
| (b) scale model x fixed shape | TE | 0.735 | +2.3% | 80.2% | 9.0 | 14.4 | 71.3% | 51.4% | 4.8 | 7.5 | 43.1% |
| (b) scale model, normalised conformal | TE | 0.735 | +2.3% | 80.7% | 9.2 | 15.5 | 75.5% | 51.8% | 5.0 | 8.1 | 46.8% |
| (b) scale model with role features, normalised conformal | TE | 0.733 | +2.0% | 81.1% | 9.2 | 15.6 | 75.8% | 51.4% | 5.0 | 8.1 | 47.7% |
| (c) per-tail conformal | TE | 0.717 | -0.2% | 81.1% | 9.9 | 14.9 | 77.7% | 50.3% | 5.0 | 8.3 | 47.8% |
| (c) conformal per projection tier (terciles) | TE | 0.717 | -0.2% | 81.3% | 9.8 | 15.6 | 80.5% | 50.7% | 5.1 | 8.4 | 48.6% |
| (c) conformal per role (deep/short WR-TE, receiving RB, rushing QB) | TE | 0.718 | -0.1% | 81.2% | 9.5 | 14.5 | 76.7% | 50.6% | 5.0 | 8.4 | 48.3% |
| (c) conformal per tier x role | TE | 0.718 | -0.1% | 81.3% | 9.8 | 15.6 | 80.9% | 50.8% | 5.1 | 8.5 | 49.0% |
| (a)+(c) roleB, per-tail, per tier | TE | 0.715 | -0.5% | 81.5% | 10.2 | 16.4 | 80.6% | 49.8% | 5.0 | 8.3 | 48.3% |
| (d) two-part: regulars / the rest | TE | 0.727 | +1.2% | 81.3% | 9.5 | 15.3 | 79.0% | 51.9% | 5.0 | 8.3 | 48.6% |
| (d) two-part, per-tail conformal | TE | 0.727 | +1.2% | 81.6% | 10.2 | 15.8 | 79.6% | 51.1% | 5.0 | 8.2 | 48.2% |
| in-season recalibration | TE | 0.719 | +0.0% | 80.4% | 9.4 | 14.4 | 76.3% | 50.5% | 5.0 | 8.3 | 48.0% |
| control: no features (residual quantiles by projection bin) | TE | 0.719 | +0.0% | 81.0% | 10.5 | 16.6 | 82.6% | 51.2% | 5.3 | 8.9 | 52.9% |
| regularised: early stopping | TE | 0.720 | +0.3% | 80.8% | 10.1 | 14.8 | 77.0% | 51.3% | 5.0 | 8.0 | 47.2% |
| regularised: leaf >= 200 | TE | 0.722 | +0.5% | 80.9% | 9.5 | 15.4 | 78.6% | 51.2% | 4.9 | 8.3 | 48.7% |

* **Kept: nothing for the 80% range** (no variant beats v2 by 2% at any position: best −0.7%, WR). Kept: the
  50% range on v2's machinery. Why nothing sharpens: the control with **no inputs at all** (residual quantiles
  by projection bin) is within 0.2% of v2 at RB / WR / TE — given the projection, the inputs do not tell a
  volatile player from a steady one; the width is weekly noise. A scale model is worse (+0.4% to +3.8%).
* **50% range coverage** (target 48–52%): RB 51.3%, WR 49.7%, TE 50.7% — **QB 46.7%** (per league-season
  43.1–49.5%; v2's 80% range at QB is 75.5% on the same seasons). Width at 50% vs 80%, top 24 in League of
  Scrubs: RB 9.5 vs 17.9, WR 9.4 vs 17.5 points; top 12 QB 10.1 vs 19.4, TE 7.5 vs 13.1.
* **Production run** (2026, trained 2016–2025): QB widening 80% 1.06 / 1.80 (unchanged), 50% 0.67 / 0.83
  (Scrubs / dynasty); RB 0.03 / 0.01; WR 0.01 / −0.00. All 16,268 v2 rows of weeks 4–18 carry P25 / P75 and
  satisfy P10 ≤ P25 ≤ P50 ≤ P75 ≤ P90 (mean width 6.08 vs 12.18 at 80%); the 896 K / DEF rows are NULL (kd1.0).
  Crossings clipped: P75 = P90 on 1 row (George Kittle, week 4), P25 = P50 on 104 (QB 49, WR 54, TE 1), P25 =
  P10 > 0 on 413 (mostly TE).
* **The point estimate did not move** (md5, `ops.projections` season 2026): weeks 4–18 `proj_points` 17,164
  rows `d4877509be0f2435074eaac87ce6ed24` before (a `project` on `690d99b` in this clone) and after; every
  column but `fitted_at` / `frozen_at` / `p25` / `p75` `fa4947af69924cd311e6ecd0cdab3faf` before and after
  (P10 / P50 / P90 unchanged). **Weeks 1–3 untouched**: 3,554 rows, the original columns
  `e26319116f0e4cda6ab13d745e80afdf` before and after both runs, `p25` / `p75` NULL on all of them. **Two
  consecutive `project` runs byte-identical**: every column but `fitted_at` / `frozen_at`
  `c6e0905b3a5a9e60fd2210d9a65d69ae` both times (236 s and 287 s wall, OMP_NUM_THREADS=1, shared box).
* **dbt**: `dbt build --select mart_player_week_projections+ mart_projection_backtest+ mart_lineup_recommendation+
  mart_projection_importance mart_player_role_alerts+ mart_waiver_upside` PASS=107 (incl. the two new tests);
  `assert_frozen_projections_precede_kickoff` PASS=1.
* **Same-game correlations** (Gaussian copula, normal scores of the randomised PIT, held-out 2023–2025, pairs
  where both were projected ≥ 5, mean of the two leagues): teammates QB–WR +0.22 (9,801 pairs), QB–TE +0.21
  (3,265), QB–RB +0.03, RB–RB −0.08 (2,592), RB–WR −0.03 (14,536), WR–WR +0.02 (8,083), TE–WR +0.01, QB–QB
  −0.41 (540: a starter and his replacement); opponents QB–QB +0.11 (2,216), QB–WR +0.07, WR–WR +0.05 (11,246),
  QB–TE +0.04, others within ±0.03; pooled teammates +0.05, opponents +0.03.
* **Decision calibration, 2024–2025** (both leagues' Sleeper rosters of those seasons, B1's solver on the
  walk-forward values, QB–TE slots; every filled slot vs the bench player the re-solve brings in): 5,374
  pairs, 4,895 with both players playing. **Brier 0.2210** vs 0.3672 for "the higher projection wins = 100%"
  and 0.2491 for a coin flip; mean predicted 64.7%, observed 63.2% (2024: 64.0 / 63.7, Brier 0.2193; 2025:
  65.3 / 62.7, 0.2227). Deciles predicted → observed: 49.7 → 49.0, 53.5 → 52.1, 56.2 → 54.1, 58.8 → 57.3, 61.7 →
  60.2, 64.8 → 61.6, 67.9 → 64.4, 71.8 → 74.3, 76.8 → 77.3, 85.6 → 81.7. By word: coin flip 975 pairs 51.9 →
  51.0%, lean 1,756 59.5 → 56.8%, clear 2,164 74.6 → 73.9%. The cards' three closest calls (2,005 pairs):
  Brier 0.2460 vs a coin's 0.2486 (mean 56.6% predicted, 54.1% observed). 242 pairs share a game (Brier 0.2022
  with the correlation, 0.2020 without). A shrink toward 50% fitted on one season does not help the other.
* **Worked examples, week 4** (live board, `cards.decisions` on `lineup_rows`; "by hand" = the independent
  integral P(A > B) = mean over A's quantile levels of F_B(Q_A(u)) on a 4,000-level grid):
  dynasty roster 12 — **RB2 Kenny Gainwell (TB vs GB) 7.54 over Emanuel Wilson (SEA vs LAC) 7.09, 0.45
  apart: 53% (Monte Carlo 0.5340, by hand 0.5336), a coin flip; most weeks 3–10 vs 2–9, bad to good week 1–16
  vs 1–15** (P10 / P25 / P50 / P75 / P90 0.96 / 3.44 / 5.98 / 9.98 / 16.03 and 1.17 / 2.24 / 5.76 / 9.07 /
  14.52); TE Kittle over Likely 48% (0.4817 / 0.4790); FLEX Boston over Godwin 58%, a lean (0.5808 /
  0.5788). League of Scrubs roster 2 — **FLEX2 Jacory Croskey-Merritt (WAS vs IND) 9.13 over Bhayshul Tuten
  (JAX vs CIN) 9.07, 0.06 apart: 46% (0.4649 / 0.4644), a coin flip; most weeks 4–11 vs 4–13, bad to good week
  2–17 vs 2–19** (1.82 / 4.10 / 7.68 / 11.36 / 17.30 and 1.92 / 4.40 / 8.28 / 13.16 / 19.17: the projection and
  the range disagree, and the card says both); RB2 Hampton over Tuten 59%, a lean; QB Mahomes over Bryce Young
  55%, a lean (most weeks 17–24 vs 13–25). No week-4 pair shares a game.
* **Checks**: `pytest` 765 passed (`tests/test_decisions.py` 15: the quantile function's knots, tails and
  clipped-range floor, three-knot fallback, Monte Carlo vs the closed form for two normals at ρ = 0 / 0.35 /
  −0.3 within 0.01 and the piecewise-linear version within 0.02, determinism and symmetry, correlation
  direction, the relationship / ρ lookup, words and percent, Brier and deciles, the DDL in all three copies;
  `test_my_week` on the live clone checks the cards' first lines); `ruff` clean; headless page check 38 runs
  (13 pages × 2 leagues, the Player page by id × 6, Home and Matchups for dynasty roster 12, Rankings week 2
  — frozen, P25 / P75 NULL — and week 4 for both rosters): 0 exceptions. Screenshots (390 and 1300 px, both
  rosters, no horizontal scroll at 390): `waveD/d6/shots/{home,matchups,rankings}_{dyn12,scrubs2}_{390,1300}.png`.
* **For the PO to decide.** (1) **Starters' ranges are too narrow**: top-N coverage 75.9–77.4% (80%) and
  46.8–47.9% (50%); conformal per projection tier fixes it (78.8–80.5% / 48.1–51.0%) at no interval-score cost
  by widening starters' ranges (top-24 WR 19.8 → 21.3 at 80%, 10.5 → 11.1 at 50%); not kept under the 2% rule;
  it is `_conformal_widening` per tercile of the calibration season's lines. It barely moves the decision
  probability (Brier 0.2208 vs 0.2210, mean overconfidence 0.9 vs 1.5 points). (2) **QB** misses at both
  levels (75.5% / 46.7%): partial games (2023: 88 QB weeks on ≤ 25% of the snaps, 62.5% below P10; full games
  6.9%), the ≤ 50%-snap share rising from 12–13% (2016–17) to 18–20%; no variant fixes it — it needs injury
  inputs (D5). (3) The probability is ~1.5 points overconfident on average (2025 more than 2024); no shrink
  applied.
* **Open / not verified**: weeks frozen before the first D6 refit keep NULL P25 / P75 (in the PO's database
  week 4 freezes at 2026-10-02 00:15 UTC; its cards then fall back to the 80% range and the three-knot
  distribution); the harness's cached baseline stays valid (P10 / P90 unchanged) but its `data_key` does not see
  the residual path — a future change there needs `HARNESS_VERSION` bumped or the interval code in the key; the
  Player page still shows floor / ceiling only (not in D6's ownership); K / DEF cards keep the margin's words.

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
