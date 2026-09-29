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
