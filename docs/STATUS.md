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

### PO merge — rounds 1 and 2 and the v3 ship, 2026-10-01

* **Round 1** (D1 harness + D2 game context, D3 weather, D4 team volume and style; three Opus devs in parallel,
  ~2.5 h because every harness run refits the model three times per group): every feature group **dropped** at every
  position — Δ order score within ±0.004, the Vegas implied total / spread / total already carry day, time, rest,
  travel, dome, wind, temperature, pace, pass rate, first downs and the defense faced. Wind for kickers: 0.139 →
  0.149 Spearman (standard error 0.009 — re-test after the Open-Meteo backfill; `backtest-kd --weather`). Kept: the
  harness (`league-lab experiment`, paired decision rule, no-peek check, `mart_feature_experiments`, "What we tried"
  on Rankings), the weather loader (first real run from the Mac: `uv run league-lab ingest weather --forecast`,
  ~280 archive calls, ~8 min; the nightly replays and fetches it — `NIGHTLY_WEATHER_OFFLINE=1` in sandboxes), the
  feature tables (built by the full build, unused in production). PO integration: the nightly's weather steps,
  `ops.feature_experiments` restored with the state; D3 could not merge D1 (its session refused `git merge`) so its
  weather groups were run by the PO on the integrated branch — all four drop.
* **Round 2** (D5 personnel, D6 ranges and decisions, D7 front-end spike): **personnel is the one group that pays** —
  `qb` at QB (+0.0445 Spearman over 2021–2025, 5 of 5 seasons; MAE −0.52; interval score −0.082) and `teammates` at
  RB/WR/TE (+0.005–0.006; WR 5 of 5 seasons at +0.0047, just under the +0.005 bar but taken for consistency);
  `oline` and `own_injury` drop. D6: 30 residual-model variants, none sharpens the 80% range by ≥ 2% (the no-inputs
  control is within 0.2% — the width is weekly noise); shipped the 50% "most weeks" range (`p25` / `p75`), per-tier
  conformal calibration (starters were covered at 76% / 47%, now 80% / 50% at RB/WR/TE; QB stays 2–4 points low
  because of partial games), and the win probability `decisions.py` (Brier 0.221 vs 0.249 coin flip on 5,374
  real B1 pairs 2024–25; deciles within 1–3 points) on the decision cards. D7: My Week + Player on FastAPI + Svelte
  against the same marts, first content 371 ms vs 1,909 ms, 36 KB vs 1.9 MB, one-tap links in session; the
  recommendation (port page by page, My Week and Player first, Trade Finder last) is in `docs/FRONTEND_DECISION.md`.
* **v3.0 ship** (`8f89988`): `FEATURES_BY_POSITION` (QB + 5 starting-QB inputs; RB/WR/TE + 4 teammate inputs),
  `MODEL_VERSION = "v3.0"`, the 9 inputs in `mart_player_week_features` from `int_player_week_personnel` (never-peek
  extended), five-season backtest written next to v2.0's rows, importance v3.0 ("Is he the projected starter?" is the
  #1 QB input at +1.83 points of error), the C6 OAK/SD → LV/LAC fix (+83 alerts), `ops.projection_backtest` gains the
  50% columns, `mart_projection_backtest` one row per model version with `is_current`. PO: release stamp, the API's
  My Week tests re-pinned to the card shape (D6 changed the headline; v3 flipped the week-4 pair), `scipy` in
  `api/pyproject.toml` (the cards import it), the lineup solve-time test loosened (a benchmark, failed once at load 7).
  Week 4 froze on the Mac with v2.0 rows (2026-10-02 00:15 UTC); v3 starts at week 5 there.
* **QA on the integrated branch** (`7149f49`, 25 min scoped: numbers on Home / Player / Rankings vs the marts, both
  leagues, 390 px): every number matched. Fixed by the PO: (1) a card whose starter projects more but outscores the
  alternative *less* often (the quantile-implied mean and the point projection disagree on a close call) read as
  "start A … B wins more often" — the card now leads with the recommendation ("A projects 0.31 more on average; B
  outscores him 51% of the time — a coin flip … the projection says A, the ranges say either"), and the wide range
  names both players; (2) Home's first card sat at y = 819 of 844 on a phone — the intro paragraph now shows at the
  top only until a team is picked, then sits under My week (first card y ≈ 625 with the stale-injury banner, less on
  a fresh database); (3) the Player page and `/api/player` show the "most weeks" range (p25–p75) between the
  projection and the floor, how-to updated, the API's parity and card tests re-pinned; (4) "The model" on Rankings
  describes both ranges and the per-tier calibration, the leftover "price line" sentence is gone; (5) "What we tried"
  lacked the personnel rows and showed `team_style_pass_rate` as a keep — the PO's 480 experiment rows (20 groups,
  both leagues) are now **the seed `dbt/seeds/feature_experiments.csv`** (same columns as `ops.feature_experiments`;
  `mart_feature_experiments` unions the seed with the live table, the live row wins on the same run), so `make build`
  on any database shows the record; `team_style_pass_rate` @ QB overridden to drop (kept by the 3-season rule, 2021
  and 2022 reverse it), `qb` / `teammates` noted as shipped in v3.0. `uv run pytest` targeted 54 + experiments 20,
  `api` 37 passed, headless check 39 runs ALL OK, ruff clean.
  **Modeling open item (from QA 2): the quantile models are fitted on residuals independently of the point model,
  so the median of the range can sit on the other side of the alternative's median from the point projection on a
  close pair. Either centre the ranges on the projection (shift so p50 = proj_points) or solve the lineup on the
  range's median; decide with the week-5 drift numbers — until then the card says both.**

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

### D5 2026-10-01 — personnel: starting QB, offensive line, teammates out, own injuries (branch `dev/D5`, clone `league_lab_d5`)

* **Built.** Five intermediate models under `dbt/models/intermediate/features/` (docs + tests:
  `int_player_week_personnel.yml`; definitions: METRICS § "Personnel"; DATA_MODEL § "Feature group `personnel`"):
  `int_pn_team_game` (team × REG game: the schedule's starting / projected QB, played, team snaps / targets / carries,
  5,822 rows), `int_pn_player_game` (QB / RB / WR / TE / OL × played game: played, missed injured / other, snap share,
  targets, carries, points, the game's starter, injured-miss streak; 218,397), `int_pn_player_week_status` (week W's
  report + practice + weekly roster for every player-week; 265,667), `int_pn_window_player` (team × week × player: shares
  over the last four played games before W, out / gone this week; 121,464) and the group's table
  `int_player_week_personnel` (109,123 rows = the universe, 20 `pn_` inputs + `proj_qb_id` / `usual_qb_id` references +
  `pn_asof_week`). One code per franchise. Registered in `src/league_lab/feature_groups/personnel.py`: `personnel` (20),
  `qb` (5), `oline` (3), `teammates` (4), `own_injury` (6). Nothing in production reads the tables; the nightly's full
  `dbt build` builds them (78 s) — no `--select` appended.
* **Tests.** dbt `--select int_pn_team_game+ int_pn_player_week_status+`: PASS=27 (5 models, 22 tests: keys, ranges,
  as-of marker, week 1 without in-season inputs, QB flags agree, `assert_personnel_is_asof` — universe row for row, the
  projected starter = the raw schedule's, the usual QB from a game he played before the week, career starts re-counted
  on the raw schedule — and `assert_personnel_ol_count_from_raw`: the OL count re-derived from raw snap counts, injuries
  and weekly rosters on its own path, every team-week 2016–2026, 0 differences). Negative control: a window that
  includes the week's own game fails `pn_window_is_asof` on 113,684 rows and changes the OL count on 631 of 5,018
  team-weeks. pytest `tests/test_personnel.py` 13 (QB-change twin on fixtures incl. the CIN case, OL-count twin incl. the
  MIN case, the SQL hard-codes the twins' constants, the groups validate and every column is documented, and on the
  database both twins reproduce every 2025 row). The harness's no-peek check: all five groups pass, **0 refusals**,
  largest probe excess 0.040 (`pn_top_rusher_out`, RB). Its warnings are the report's publishing calendar, not a peek:
  on the clone's data (fetched 2026-09-26) week 4's report is not out, so `oline` / `teammates` / `pn_practice_ord` are
  NULL for week 4.
* **As of: which report.** nflverse `injuries` holds one row per player-week: the team's final game-status report
  (Friday for a Sunday game); `date_modified` (2016–24) is a median 47–55 h before kickoff, 24 of ≈ 52,000 rows were
  modified after kickoff (13 in 2020). Reserve lists from the weekly roster (0 RES player-weeks 2017–25 with snaps in
  that game). The roster's INA is the game-day inactive list (0 of 7,204 INA player-weeks 2022–25 played) and is never read.
* **Hand checks** (METRICS § "Personnel"): QB change 2025 — CIN week 3 (Burrow → Browning), NYG week 4 (Wilson → Dart),
  ARI week 6 (Murray → Brissett): every RB / WR / TE row 0 the week before, 1 that week; the new starter's
  `pn_qb_starting` 1, the old one's 0; gap −1.86 / NULL (Dart, no start) / −9.79. Offensive line, MIN 2025 week 5 from
  the raw tables: O'Neill, Jackson, Jurgens Out among the five → 3, share 1.8703 = the table. Teammates, LA 2025 week 7:
  Nacua Out → `pn_top_target_out` 1 on every other Rams row.
* **Coverage** by season and sub-group: METRICS § "Personnel" (2017–2025: QB change 88–92% of rows, OL / teammates 94%
  (100% from week 2), report 99.5–100%, last-season games missed 81–86%; 2016 lower: no 2015).
* **Harness** (`OMP_NUM_THREADS=1 … league-lab experiment personnel qb oline teammates own_injury`, one session, baseline
  from the cache, **66 min wall** (personnel 1,573 s, qb 752, oline 559, teammates 543, own_injury 507); test seasons
  2023–2025, both leagues; mean of the league-averaged season Δ; (n) = seasons better of 3):

  | group | pos | Δ Spearman (better) | Δ MAE pts (better) | Δ interval score | Δ coverage pp | Δ width | decision |
  |---|---|---|---|---|---|---|---|
  | personnel (20) | QB | **+0.0484 (3)** | **−0.532 (3)** | −0.082 | −0.23 | −1.43 | keep |
  | personnel | RB | **+0.0066 (3)** | −0.037 (3) | −0.011 | +0.34 | −0.06 | keep |
  | personnel | WR | **+0.0057 (3)** | −0.025 (3) | −0.003 | −0.71 | −0.11 | keep |
  | personnel | TE | +0.0027 (3) | +0.009 (1) | +0.003 | +0.06 | +0.05 | drop — verdict **keep** |
  | qb (5) | QB | **+0.0528 (3)** | **−0.541 (3)** | −0.084 | −0.62 | −1.61 | keep |
  | qb | RB / WR / TE | −0.0003 (1) / +0.0003 (1) / +0.0000 (1) | −0.005 / −0.003 / +0.012 | ±0.003 | | | drop ×3 — verdict **keep** |
  | oline (3) | QB / RB / WR / TE | +0.0041 (2) / −0.0003 (0) / −0.0003 (1) / +0.0005 (3) | +0.012 / −0.007 / +0.009 / +0.000 | ±0.010 | | | drop ×4 — verdict **drop** |
  | teammates (4) | QB | −0.0069 (0) | +0.040 (1) | −0.003 | −0.48 | −0.04 | drop (hurts) |
  | teammates | RB | **+0.0064 (3)** | −0.035 (3) | −0.009 | +0.20 | −0.00 | keep |
  | teammates | WR | **+0.0053 (3)** | −0.013 (3) | −0.004 | −0.34 | −0.12 | keep |
  | teammates | TE | **+0.0054 (3)** | −0.009 (3) | −0.002 | +0.40 | +0.02 | keep — verdict **mixed** |
  | own_injury (6) | QB / RB / WR / TE | +0.0027 (2) / −0.0008 (0) / +0.0000 (2) / −0.0035 (0) | +0.012 / −0.007 / +0.004 / +0.012 | ±0.005 | | | drop ×4 — verdict **drop** |

  Baseline (v2): Spearman QB 0.533, RB 0.683, WR 0.624, TE 0.583; MAE 7.08 / 4.44 / 4.40 / 3.22. The QB gain is ten times
  anything round 1 found: 2023 +0.072, 2024 +0.022, 2025 +0.065 (`qb`).
* **QB and WR on 2021–2022** (`scratchpad/waveD/d5/qb_wr_extend.py`, D4's pattern: `walk_forward` + `summarize_scores`, QB and
  WR only, 17 min; 2023 reproduces the harness to 4 decimals: `qb` QB +0.0718 / −0.627, `personnel` QB +0.0700, WR
  +0.0028, `teammates` WR +0.0023). Five seasons 2021 / 2022 / 2023 / 2024 / 2025:
  - `qb` at QB: Spearman +0.046 / +0.018 / +0.072 / +0.022 / +0.065 → **mean +0.0446, 5 of 5**; MAE −0.56 / −0.38 / −0.63 /
    −0.27 / −0.73 → **−0.51, 5 of 5**. Holds (unlike D4's pass rate). `qb` at WR: +0.0039 / +0.0005 / −0.0001 / −0.0004 /
    +0.0014 → +0.0011, 3 of 5: nothing.
  - `teammates` at WR: +0.0032 / +0.0042 / +0.0023 / +0.0056 / +0.0082 → **mean +0.0047, 5 of 5**; MAE −0.003 / −0.008 /
    −0.011 / −0.012 / −0.016 → −0.010, 5 of 5. Consistent every season, **0.0003 under the +0.005 bar** of the rule's
    5-season version. At QB: +0.0041 / −0.0050 / −0.0021 / −0.0185 / −0.0001 → −0.0043, 1 of 5 (drop).
  - `personnel` at QB: +0.055 / +0.017 / +0.070 / +0.015 / +0.061 → +0.0434, 5 of 5; at WR: +0.0058 / +0.0067 / +0.0028 /
    +0.0069 / +0.0074 → **+0.0059, 5 of 5** (MAE −0.023, 5 of 5): passes the 5-season bar.
* **Where the QB gain comes from** (`scratchpad/waveD/d5/qb_segments.py`, 2025, reference league, 677 played QB rows,
  MAE 6.04 → 5.39): 74% from the 140 rows of QBs who played without being the projected starter (relief and mop-up:
  v2 projected 6.5 from their history, actual 2.1, with `qb` 3.3), 12% from the 43 rows of a new starter (v2 9.0, actual
  13.2, with `qb` 12.4 — the superflex decision: "Browning starts this week"), 14% from the 494 usual starters' rows. v2
  projects "points if he plays" from his own history and cannot tell a starter from a backup; the projected starter is
  known a week ahead.
* **Recommendation.** Ship two small per-position sets in v3: **QB ← `qb`** (5 inputs; 5 of 5 seasons, +0.045 Spearman,
  −0.51 points MAE, interval score −0.08: also a sharper range for D6) and **RB / WR / TE ← `teammates`** (4 inputs; 3 of
  3 at each position, +0.005 to +0.006; WR 5 of 5 at +0.0047). Drop `oline` and `own_injury` (no position helps:
  the line's absences and a player's own history are in the lines and in his recent usage already) and `qb` at RB / WR /
  TE (the WR "new quarterback" mechanism does not show in five seasons). Alternative for WR only: `personnel` (+0.0059,
  passes the 5-season bar) at 20 inputs for +0.001 — not worth it. Expect the live gain at RB / WR / TE to be smaller
  than the backtest's until the freeze rule changes (decision 3).
* **For the PO to confirm.** (1) Per-position inputs need a change outside D5's files: `projections.py` has one `FEATURES`
  for every position — v3 needs e.g. `FEATURES_BY_POSITION = {QB: FEATURES + personnel.QB, RB/WR/TE: FEATURES +
  personnel.TEAMMATES}` used by `fit_position` / `predict_position` / `component_importance` and by `signals.py`'s scenario
  refits, `load_frame` joining `int_player_week_personnel` (or the PO adds the 9 columns to
  `mart_player_week_features`), plus `FEATURE_LABELS` for the Rankings explainer; the harness needs nothing.
  (2) `pn_qb_prev_ppg_diff` = points per start over the newest 17 starts of the last two seasons and this one (not "last
  season" alone: a backup's last start is often two seasons back). (3) **The freeze gap**: on Thursday 2026-10-01 (week
  4, first kickoff tonight) nflverse's injury file has 257 rows for 30 teams with practice participation but only 2
  designations; Friday's Out / Doubtful arrive after B5 freezes the week at its first kickoff. Training uses the final
  report, so `teammates` (and v2's existing `questionable`) see less on the frozen board than in the backtest; reserve-list
  and released teammates are known in time. Freezing each game at its own kickoff (not the week's first) would close it.
  The `qb` inputs are not affected (the projected starter is filled about a week ahead: on 2026-09-26 weeks 3–4 were
  filled; week 3's 30 unplayed projections all matched the actual starters; 2 of 32 week-4 projections changed during
  the week). (4) The harness scores every QB who played, mop-up included; three quarters of the QB gain is there. It is
  real (v2 over-projects backups by ~4 points) and the decision-relevant part (new starters, 12%) improves too.
  (5) `pn_practice_ord` added to the brief's list (own_injury dropped anyway). (6) `pn_top_target_out` /
  `pn_top_rusher_out` are about the leading teammate **other than him** (for the WR1 himself: the WR2), and "out" includes
  "gone" (released / traded: the C6 absence logic) and Doubtful. (7) `pn_absence_beneficiary` reads `ops.player_role_alerts`
  (the mart view was missing from the clone and would be dropped by any cascade). (8) No `metric_registry.csv` rows (seeds
  out of bounds): add `personnel` v1.0 at merge if kept. (9) The `ops.feature_experiments` rows (5 groups × 24) are in
  `league_lab_d5` only.
* **Found on the way (not D5's files).** `int_player_game_role` (C6) joins `dim_game`'s OAK / SD to `fct_team_game`'s LV / LAC
  and loses the Raiders 2016–19 and the Chargers 2016 (so do the role alerts); `kd_team()` on both sides fixes it.
  `tests/test_lineup.py::test_real_slot_sets_solve_in_under_5_ms[slots3-26]` failed once at load average 7 (worst 112 ms
  vs 25 ms) and passes alone: a timing flake.
* **Verified.** pytest **763 passed** (56 s on a quiet box; the first run at load 7 had the timing flake above); `ruff check src tests app` clean;
  headless page check (both leagues, every page + 6 Player runs): 32 runs, 0 exceptions. No page touched.
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
* **For the PO to decide** (point 1 decided: adopted, see the follow-up below). (1) **Starters' ranges are too narrow**: top-N coverage 75.9–77.4% (80%) and
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
### D7 2026-10-01 — front-end spike: My Week + the player card on a phone-first stack (branch `dev/D7`, clone `league_lab_d7`)

A decision, not a migration: Andrew's note is `docs/FRONTEND_DECISION.md` (recommendation: port page by page, My
Week + Player first, then Waiver Wire / Team Hub / Matchups; Trade Finder last; the rule: the Streamlit page stays
until the new one matches the headless check's numbers). Nothing in `app/`, `src/`, `dbt/` changed
(`git diff --stat integration/wave-d -- app src dbt` empty); no root dependency added.

* **`api/`** (FastAPI, Python 3.13, its own `pyproject.toml` + `uv.lock`, psycopg pool on the read-only role,
  10-minute query cache like `st.cache_data`, gzip, 503 on a missing mart): `/api/leagues`, `/api/leagues/{id}/rosters`,
  `/api/my-week?league&team`, `/api/player/{gsis}?league&team`, `/api/search?league&q`, `/api/status`,
  `/api/session|login|logout`; everything else serves `web/dist` (SPA fallback, hashed assets immutable).
  `league_lab_api/applib.py` loads `app/lib/cards.py`, `ui.py`, `signals.py` **unchanged** as a private package
  whose `db` is the API's and whose `streamlit` is a recording stand-in: `lineup_rows` (LINEUP_SQL), `decisions`,
  `alternative`, `bench_gap`, `league_line`, `lineup_frame`, `current_week`, `freshness_banner` run as is, and the
  card text is `render_decision`'s own output (captured), so D6's wording change reaches the web app without a
  change here. Copied verbatim (marked): Home's record / opponent / movers queries, `lineup_table(full=True)`'s
  six lines for the bench rows, and the whole player page (its queries and sentences are inline in `0_Player.py`).
  Gate: `LEAGUE_LAB_APP_PASSWORD` (unset = open) → POST `/api/login` → HttpOnly `ll_auth` cookie (180 days) or a
  bearer token, `<expiry>.<HMAC-SHA256>` keyed on `LEAGUE_LAB_API_SECRET` or the password (a new password signs
  everyone out). `api/Dockerfile` (+ `Dockerfile.dockerignore`) builds web + API into one image (no Docker daemon
  here: the image layout was reproduced by hand — `uv sync --frozen --no-dev` in a copy holding only `api/`,
  `app/lib`, `web/dist`, no streamlit installed — and served both leagues' My Week, a player card and the
  manifest; ~125 MB RSS).
* **`web/`** (Svelte 5 + TypeScript + Tailwind 4, Vite 8; 26 KB JS + 5 KB CSS gzipped): `/` My Week (picker remembered
  in `localStorage`, a `?league&team` link wins; the three cards; the lineup in 4 columns, the flag column only when a
  row has a flag; full lineup, How to read this, movers in `<details>`), `/player/<gsis>` (Projection, Value,
  Availability, Usage, Signals — answer first; search; Back). History-API router: names are real links handled in
  place (one tap, same tab, one history entry), Back restores the scroll position, picks rewrite the URL without a
  history entry. Manifest + icons + a small service worker (installable); light / dark from the system; an inline
  script starts the first screen's API call before the bundle arrives.
* **API tests** (`cd api && uv run pytest -q`): **39 passed** (68 s). Against independent SQL for dynasty 12 and Scrubs
  2, week 4: the lineup table = `mart_lineup_recommendation` slot by slot (value, margin), lineup value in the league
  line, full list = starters + `ops.lineups` bench / can't play; the cards = the (up to) three unlocked, valued starters
  with the smallest margins below their own value (by hand: dynasty RB2 0.45, TE 0.63, FLEX 1.87; Scrubs FLEX2 0.06,
  RB2 1.66, QB 2.23), alternative = value − margin and on the bench in `ops.lineups`; worked example dynasty 12:
  "RB2: start Kenny Gainwell over Emanuel Wilson, 7.54 vs 7.09 projected — 0.45 apart, a coin flip", lineup 109.69
  (10th of 12). Player: Projected / Floor / Ceiling = `mart_player_week_projections` for ten players (rostered WR,
  starter RB, bench RB, taxi, IR slot, free agent ×2, K, no projection, Out); the starter's lineup sentence carries the
  mart's value and margin. **Parity** (`tests/test_parity.py`, Streamlit's AppTest in the repo env via
  `tests/streamlit_twin.py`): Home ×2 leagues — every card block, the record and league lines, both lineup tables
  (slot, name, value, margin, flag), How to read this, the freshness line and warning identical; Player ×10 — every
  section title, metric (label, value, delta) and sentence identical (links compared as text). Gate: all six data
  endpoints 401 without a token, wrong password 401 "That is not it.", bad / tampered / expired tokens 401, cookie and
  bearer 200, a new password invalidates old tokens. Static: SPA fallback, manifest type, immutable assets, gzip.
* **Web checks**: `npm run lint` (eslint + svelte-check + tsc) clean; Playwright `npm run e2e` **24 passed** (12 × phone
  390 × 844 iPhone UA with touch, 12 × desktop 1300 × 900): no sideways scroll on both routes (incl. the full-lineup
  and How-to expanders), the first card ends inside the first screen, tables ≤ 5 columns, a card name and a table
  name open the card on ONE tap with no popup and exactly one new history entry, in-app Back + browser Back / Forward,
  scroll restored on Back, the pick remembered across a bare visit, search, dark mode, manifest + service worker,
  and the password screen against a gated API (wrong → "That is not it.", right → cards, a name tap and a new tab
  stay signed in).
* **Side by side** (`npm run measure`, `e2e/measure.spec.ts`; Streamlit 8577 through `e2e/gzip-proxy.mjs` on 8578
  because `streamlit run` serves its JS uncompressed; 5 loads / 10 taps; load average 7–8 on 2 CPUs throughout —
  D5 / D6 fits): first content phone web 371 ms vs Streamlit 1,909 (repeat 100 vs 2,069); desktop 305 vs 1,927;
  weight 36 KB (7 requests) vs 1,929 KB gzipped / 5,528 KB raw (140 requests); name → card 151 vs 1,830 ms phone
  (Streamlit in a new tab), 131 vs 2,012 desktop; back to My Week 68 vs 938 (Streamlit: sidebar → Home); change
  team 33 (216 first) vs 1,082; slow 4G phone: first content 542 vs 5,365 ms (12,719 uncompressed), name → card
  268 vs 2,296. Fold at 390 × 844: web 3 of 3 cards fully visible (first at 253 px), Streamlit 0 (first at 819 px).
  `e2e/streamlit-probe.mjs` (10 tries each): one sidebar page hop adds 3 history entries; the browser's Back returned
  to My Week 0/10 on the phone, 3/10 on the desktop; with `LEAGUE_LAB_APP_PASSWORD` set, a card name's new tab asks
  for the password again (checked). One-tap on Streamlit is driver-dependent in emulation (Python Playwright: 2 taps,
  8 of 8; Node: 1 tap) — always a new tab.
* **Headless check** (`apptest_wc.py` on this worktree, both leagues × 13 pages + 6 Player-by-id runs): 32 runs, 0
  exceptions (no app file changed).
* **Decisions for the PO.** (1) Svelte over React (26 KB vs ~60 KB of framework JS; same TypeScript). (2) Routes under
  `/api/…` so the app's own paths (`/`, `/player/…`) never collide. (3) The player card shows Projection first (the
  Streamlit page leads with Usage, an open LOW from Wave B) and keeps the fifth section, Signals (C6), which the plan
  row's "four sections" predates. (4) The cards' text is captured from `render_decision` rather than re-templated, so
  the web cards follow `cards.py`. (5) The stale-injury warning is a one-line "⚠️ Injury news may be stale ›" that opens
  to the full sentence (the first screen stays the answer). (6) Measurements against Streamlit behind a gzip proxy
  (the uncompressed numbers are reported next to them).
* **Open.** The spike is not deployed (no host credentials here): `api/README.md` has the Render / Fly / Railway /
  Cloud Run steps. The player page's sentences are a verbatim copy until they move into `app/lib` (the port rule's
  step 1); after D6 merges, re-run `api/tests/test_parity.py` (it fails on any drift). If `cards.py` starts
  importing `league_lab.*`, the image needs `src/` and that module's dependencies. Absolute timings are from a loaded
  2-core sandbox and a local database; the hosted app adds the Neon round trips to both. No `--select` appended, no
  seeds or metrics touched.

* **Follow-up 2026-10-01 (PO decision on point 1): per-tier calibration adopted.** `_conformal_widening` now
  runs per position × league × projection tier for both ranges: tiers = terciles of the calibration season's
  priced (out-of-fold) line within the position (`TIER_QUANTILES = (1/3, 2/3)`, cut points stored on the model,
  a projected row takes its tier from its own `proj_points`); a tier with < 200 calibration rows takes the
  position-wide widening (`TIER_MIN_ROWS`; never binds: smallest tier 206 rows in the walk-forward, QB 2023,
  213+ in production). This is the experiment's `v2_bucket_tier` (the production `walk_forward` on 2025 QB
  reproduces it: interval score 1.28327 / 1.77809, coverage 0.76147 / 0.74251, Scrubs / dynasty). Walk-forward
  2023–2025, both leagues, position-wide → per tier (top-N = the board's top 24 RB / WR, top 12 QB / TE by
  projection each week among those who played; rest = the others who played):

  | Pos | Coverage 80: all / top-N / rest | Coverage 50: all / top-N / rest | Top-N width 80 / 50 (points) | Interval score 80 / 50 |
  |---|---|---|---|---|
  | QB | 75.5 → **75.8** / 77.4 → **78.8** / 74.6 → 74.3% | 46.7 → **47.2** / 47.6 → **48.1** / 46.2 → 46.9% | 23.4 → 24.1 / 12.1 → 12.2 | 1.5092 → 1.5094 (+0.01%) / 2.7785 → 2.7831 (+0.17%) |
  | RB | 79.8 → **79.9** / 77.3 → **79.5** / 80.8 → 80.1% | 51.3 → **51.3** / 47.7 → **51.0** / 52.7 → 51.4% | 19.1 → 19.9 / 10.1 → 11.0 | 0.9709 → 0.9710 (+0.01%) / 1.7048 → 1.7055 (+0.04%) |
  | WR | 81.4 → **81.1** / 75.9 → **79.7** / 82.7 → 81.4% | 49.7 → **49.6** / 46.8 → **49.0** / 50.4 → 49.8% | 19.8 → 21.3 / 10.5 → 11.1 | 0.9572 → 0.9558 (−0.15%) / 1.6752 → 1.6759 (+0.04%) |
  | TE | 80.9 → **81.3** / 76.3 → **80.5** / 81.9 → 81.5% | 50.7 → **50.7** / 47.9 → **48.6** / 51.3 → 51.2% | 14.4 → 15.6 / 8.3 → 8.4 | 0.7186 → 0.7174 (−0.17%) / 1.2643 → 1.2648 (+0.04%) |

  RB / WR / TE are inside 78–82% / 48–52% overall and on the top-N (TE top-12 50%: 48.6%); QB stays below
  (75.8% / 47.2%; top-12 78.8% / 48.1%): partial games, as above. Production widenings per tier (League of
  Scrubs, low / middle / top): 80% QB 0.79 / 1.81 / 1.28, RB −0.01 / 0.20 / 0.60, WR 0.00 / −0.04 / 0.26, TE
  0.00 / 0.04 / 0.32; 50% QB 0.53 / 0.80 / 0.91, RB −0.02 / 0.23 / 0.39, WR 0.00 / −0.17 / 0.38, TE 0.02 / 0.03 /
  0.30. Mean width, 2026 weeks 4–18: 12.34 (80%) / 6.18 (50%), was 12.18 / 6.08; all 16,268 v2 rows ordered.
  **md5** (`ops.projections` 2026): weeks 4–18 `proj_points` `d4877509be0f2435074eaac87ce6ed24` unchanged;
  weeks 1–3 (original columns) `e26319116f0e4cda6ab13d745e80afdf` unchanged, P25 / P75 NULL; two consecutive
  `project` runs byte-identical, every column but `fitted_at` / `frozen_at` `cc2606c0402d82cef400085a8bbb17f6`
  both times (233 s / 229 s). dbt (`mart_player_week_projections+ … mart_waiver_upside` +
  `assert_frozen_projections_precede_kickoff`) PASS=108. Decision probability on the shipped ranges: Brier
  0.2208 (was 0.2210), mean predicted 64.1% vs observed 63.2% (was 64.7%); week 4: Gainwell over Wilson 53%
  (Monte Carlo 0.5333, by hand 0.5327), Croskey-Merritt over Tuten 47% (0.4658 / 0.4651; most weeks 4–12 vs
  4–13). Tests: `tests/test_decisions.py` +2 (the CQR quantile and its 50-row floor; the per-tier lookup and the
  position-wide fallback); `test_projection_freeze.py` unchanged and passing. METRICS § Ranges and decisions:
  the tier rule and this table.

### v3 ship 2026-10-01 — projection v3.0 = v2 + the starting-QB inputs at QB + the teammate inputs at RB / WR / TE (branch `dev/V3`, clone `league_lab_d5`)

The PO accepted D5's recommendation: `qb` at QB (5 inputs), `teammates` at RB / WR / TE (4); `oline`, `own_injury` and
`personnel`-at-WR not taken. Definitions: METRICS § "Projection v3" and § "Personnel".

* **Code.** `projections.py`: `MODEL_VERSION = "v3.0"`, `QB_INPUTS` / `TEAMMATE_INPUTS` (from
  `feature_groups.personnel`), `FEATURES_BY_POSITION`, `ALL_FEATURES` (what `load_frame` reads); `fit_position` defaults
  to the position's inputs and the model keeps them (`predict_position`, the P50 and the component importance read
  `m.features`; the importance twin fits on the position's inputs); `walk_forward` takes per-position lists; nine plain
  labels in `FEATURE_LABELS`; `backtest` replaces only its own version's rows. `signals.py`: the scenario refits
  (`component_models`, `predict_lines(…, position)`) use the position's inputs (the base reproduces the stored
  projection to 0.00e+00 on 26 rows); `SIGNALS_VERSION` ra1.2 (same rule, recomputed on the fixed role table).
  `experiments.py`: the baseline is the production model per position, a group adds its columns to each position's
  inputs, `data_key` includes `FEATURES_BY_POSITION`, and a group whose columns are already inputs at one of its
  positions is refused (`personnel` / `qb` / `teammates` moved to `personnel.SHIPPED_GROUPS`). dbt:
  `mart_player_week_features` left-joins the nine inputs + `pn_asof_week` (`assert_features_never_peek` checks
  `pn_asof_week` < week and no teammate input in week 1; `features_personnel_in_range`); `int_player_week_personnel`:
  an unplayed game nflverse has not filled yet takes the team's newest played starter (`proj_qb_source`), so weeks
  5–18 are not "unknown starter" (2016–2025 rows unchanged); `int_player_game_role`: `kd_team()` on the schedule, roster
  and snap sides (the C6 defect: 99,738 → 101,230 rows, 5,264 → 5,344 team-games; role alerts 7,074 → 7,157:
  absence_beneficiary 2,312 → 2,346, role_up 1,865 → 1,881, role_down 1,915 → 1,937, depth_move 889 → 899, new_team 93 →
  94; the Raiders 2016–19 0 → 58, the Chargers 2016 0 → 24); `mart_projection_backtest` per model version with
  `is_current`, `coverage_50`, `interval_width_50`, `interval_score` (unique key test); `mart_projection_drift` joins the
  backtest of the board's model version; `ops.projection_backtest` gains `coverage_50`, `interval_width_50`,
  `pinball_25`, `pinball_75` (db migrate, the writer's DDL, the mart pre-hook). App: Rankings reads the current
  version's backtest and "The model" has a paragraph on what v3 added, the evidence and what was dropped;
  `app/whats_new.md` "Oct 1"; `CHANGELOG.md` 2026-10-01. API: `scipy` added to `api/pyproject.toml` (D6's decision
  probability in the cards imports it; the parity test failed without it — a dependency, not a wording change).
* **Backtest v3.0** (`league-lab backtest-v2 --seasons 2021-2025`, 17 min 13 s, `OMP_NUM_THREADS=1`), v2.0 = the stored
  record; mean over seasons of the league-averaged season means; (n/5) = seasons better:

  | Pos | Spearman v2.0 → v3.0 | Δ (n/5) | MAE v2.0 → v3.0 | Δ (n/5) | Cov 80 v2.0 → v3.0 | Cov 50 v3.0 | Width 80 v2.0 → v3.0 | Width 50 v3.0 | Interval score v2.0 → v3.0 |
  |---|---|---|---|---|---|---|---|---|---|
  | QB | 0.5377 → 0.5822 | **+0.0445 (5)** | 7.013 → 6.494 | **−0.520 (5)** | 77.9% → 78.4% | 48.9% | 22.79 → 21.47 | 11.13 | 1.5163 → 1.4344 (−0.082) |
  | RB | 0.6618 → 0.6704 | +0.0086 (5) | 4.542 → 4.498 | −0.044 (5) | 79.7% → 80.4% | 51.0% | 13.58 → 13.92 | 7.33 | 0.9929 → 0.9792 |
  | WR | 0.6173 → 0.6220 | +0.0047 (4) | 4.466 → 4.464 | −0.002 (3) | 81.0% → 80.7% | 49.9% | 13.66 → 14.20 | 7.33 | 0.9678 → 0.9603 |
  | TE | 0.5624 → 0.5648 | +0.0024 (4) | 3.285 → 3.288 | +0.002 (2) | 81.0% → 81.3% | 50.4% | 9.68 → 10.04 | 5.24 | 0.7364 → 0.7327 |

  QB by season +0.048 / +0.018 / +0.071 / +0.024 / +0.062; top-N hit rate +0.9 pp at QB. Width and coverage include D6's
  per-tier widening. **Reproduces the harness**: on identical data (2023–2025 vs the harness's cached v2 baseline)
  v3.0 = QB +0.0528, MAE −0.541, interval score −0.082 (the `qb` run cell for cell: e.g. Scrubs 2023 0.6012, dynasty
  2025 0.5885 = `ops.feature_experiments`), RB +0.0065, WR +0.0058, TE +0.0061 (`teammates`: +0.0064 / +0.0053 /
  +0.0054; ±0.002 per cell from the Raiders / Chargers alerts the role fix added). The stored v2.0 record differs from
  that baseline by up to ±0.004 per cell (an older run): the five-season RB / WR / TE deltas carry that noise.
* **Importance v3.0** (component, 2025 held out from a 2016–2024 twin, written by `project`): QB 1st **Is he the
  projected starter?** +1.83 points (2nd the implied total +0.18), 6th games with this week's QB +0.07; RB 4th top ball
  carrier out +0.06; WR 5th share of the team's targets out +0.02; TE 10th the same +0.02.
* **`league-lab project` on the clone** (week 4 had not kicked off: 18:05 UTC): weeks 1–3 untouched — 3,554 rows, md5
  `186253414a410e81805c7852d89e3e5f` before and after both runs; weeks 4–18 rewritten (16,268 v3.0 + 896 kd1.0 rows);
  two consecutive runs byte-identical: 17,164 rows, md5 `b535e82e0b5f33ec1165cc5ae3f6a0e9` (every column but
  `fitted_at`). Run 1 7 min 20 s (importance included), run 2 4 min 17 s. Drift: 18 rows (weeks 1–3, v2.0 boards; the
  strip compares with v2.0's backtest until a v3.0 week is scored). Lineups 8,978 rows, waivers 3,996, scenarios 26.
* **Checks.** `pytest` **781 passed**; `ruff` clean; `dbt build --select mart_player_week_features+
  mart_player_week_projections+ mart_projection_backtest+ mart_lineup_recommendation+ mart_projection_importance
  mart_player_role_alerts+ mart_waiver_upside mart_projection_drift int_player_game_role+ int_pn_team_game+`: PASS=154
  (incl. `assert_features_never_peek`, `assert_personnel_is_asof`, `assert_personnel_ol_count_from_raw`); headless
  check both leagues + Player runs: 32 runs, 0 exceptions; API `tests/test_parity.py` 12 passed (after `scipy`). The
  API's `tests/test_myweek.py` has 3 failures that pin numbers and words of the v2 board before D6 ("0.13 apart, a coin
  flip" — D6's card now leads with the probability — and Wilson / Gainwell's order, which v3 flipped): D7's fixtures to
  re-pin, not changed here.
* **On the Mac** (week 4 froze at 2026-10-02 00:15 UTC with v2.0 rows: v3 starts at week 5 there; weeks 1–4 keep their
  v2.0 rows and `model_version` says so):
  ```
  git pull && make sync
  uv run league-lab db migrate                     # the backtest's 50%-range columns (and D6's p25 / p75)
  make build                                       # dbt: the fixed role table, personnel, the features mart (~3 min)
  uv run league-lab signals                        # role alerts for every season under ra1.2 (~30 s)
  uv run league-lab dbt build --select int_player_week_personnel+   # the absence input sees the recomputed alerts
  make backtest-v2                                 # v3.0, 2021-2025 (~12-17 min); v2.0's rows stay
  make project                                     # the v3 board for week 5 on, importance, lineups, waivers, signals
  make sync-hosted && git push                     # or let the 08:00 nightly publish
  ```
  The nightly does not run `backtest-v2`: until it is run once, Rankings' backtest shows v2.0's record (`is_current`
  falls back to the newest version that has rows).

## Wave E (Iteration 13)

### PO merge — Wave E, 2026-10-01/02

* **Delivered** (four Opus devs in parallel, ~35 min each; one 13-minute QA pass): E1 "Our record" (loader, snapshots,
  `mart_projection_record`, the page; the record starts the first week Andrew's nightly archives Sleeper before
  kickoff — the sandbox cannot reach Sleeper, so no real response has been parsed yet), E2 rest of season
  (`mart_player_ros_projection`, Player / Rankings / Trade Finder), E3 the any-league design (`docs/ANY_LEAGUE.md`)
  and spike (`/api/my-week` for a league the database does not have; parity 111.46 / 117.02 exact), E4 model tests
  (`rookie_prior`, `rookie_prior_early`, `oline_quality`, `qb_x_offense`, `player_prior`: **all drop** — Andrew's two
  questions answered from the evidence in METRICS § "Wave E groups": the model already lowers teammates when a much
  worse QB starts, slightly too little on good offenses; which lineman is out barely moves fantasy points).
  The experiment record (seed) is now 600 rows, 25 groups.
* **QA findings fixed by the PO**: (1) `mart_projection_record` counted a Sleeper player with no stat line as a
  projection of 0 (it would have tilted the record our way) — a listed player now needs Sleeper's own total or a
  priced stat; (2) the Trade Finder rest-of-season sentence contradicted the verdict on lopsided trades — it now says
  it is the players' plain totals before the roster spot and the re-solved lineup, with the betting-line caveat;
  (3) `docs/ANY_LEAGUE.md` overstated the range approximation ("within 0.3%" was week 4; QB top end is off 1.2–1.5
  points, width 7%) and the "rarely more than 0.1 from a reference scoring" claim was unmeasured — corrected, and
  the Scrubs K / DEF parity footnoted (valued from Scrubs' own fit); (4) Rankings "Yours" says when it stops at four;
  (5) Home's guide and What's new carry "Our record"; (6) the E4 cover test names its three tables literally;
  (7) `/api/player` mirrors the Player page's rest-of-season line and how-to (the parity tests caught the gap).
* **Checks**: `uv run pytest -q` 821 passed; `api` 51 passed; headless 41 runs ALL OK; ruff clean; the new models
  built on the PO's database (PASS=57).
* **Hotfix after the Mac run (2026-10-02 01:53 ET)**: the first `make project` after week 4 froze failed
  `scenario_base_is_the_projection` (24 rows): `signals_after_project` built the week-4 scenarios off the refit
  while the board for a kicked-off week keeps its kickoff numbers (B5). Scenarios now skip frozen weeks
  (reproduced by freezing week 4 on the PO's copy: 24 week-4 rows → 0, base = stored projection to 0.00e+00 on the
  14 remaining rows, the mart's 10 tests pass). The nightly would have stopped at `projection-marts` the same way.
* **Hotfix 2 (2026-10-02 02:39 ET, `make build`)**: `assert_frozen_projections_precede_kickoff` failed on 595 rows —
  the first week frozen with K / DEF rows present. `kdef` stamped its rows with its own `now()` seconds after the
  QB–TE batch, and the freeze relabel wrote the league-week's max `fitted_at` as every row's `frozen_at`, so the
  QB–TE rows of Scrubs week 4 had `frozen_at <> fitted_at`. Fix: one `fitted_at` per run (the K / DEF rows take the
  QB–TE stamp), the relabel sets `frozen_at = fitted_at` per row, and `_write_projections` repairs rows frozen by
  the old relabel (idempotent; logged). Reproduced on the PO's copy (581 rows), `project` repaired them, the test
  passes, new weeks carry one `fitted_at`.
* **Leads the PO is NOT shipping yet** (E4): `player_prior` as a *linear correction* (RB MAE −0.054, WR −0.040, TE
  −0.014, 3 of 3 seasons; the control — a constant shift — makes MAE worse) and `rookie_prior_early` at RB / WR for
  weeks 1–4 (+0.005–0.008 Spearman, 3 of 3). Both need a `projections.py` change and recalibrated ranges → v3.1
  candidates, judged on 2021–2025 before anything ships.

### E4 2026-10-01 — model tests: rookie prior, offensive-line quality, QB × offense, player prior (branch `dev/E4`, clone `league_lab_e4`)

Andrew: "is the model treating everything equal?" (an elite QB lost on an elite offense vs a bad QB on a bad one; a
Pro Bowl tackle vs a backup guard out) and the PO's shortlist (a player-identity prior, rookie / cold-start priors).
Tests only: nothing in production reads the new tables; `projections.py` is untouched.

* **Built.** Four groups, five registrations (definitions, as-of rules, verdicts: METRICS § "Feature experiments" →
  "Wave E groups"; tables: DATA_MODEL § "Feature groups of Wave E"):
  `rookie_prior` / `rookie_prior_early` (`int_e4_player_week_rookie_prior`, 109,123 rows = the universe; draft round,
  pick, tier, undrafted, years in, rookie, age — fixed before the season; `_early` = the same seven in weeks 1–4 only),
  `oline_quality` (`int_e4_player_week_oline_quality` + helper `int_e4_ol_starter_week`, 27,350 starter-weeks: D5's
  five starters each with career starts before the week, draft score, last season's snaps and a 1–5 quality rank;
  the group = D5's count and window share + career starts / draft capital / last-season snaps out + the best one out's
  rank), `qb_x_offense` (`int_e4_player_week_qb_x_offense`: the QB gap × implied total, × game total, × last season's
  team points per game, × last season's EPA per play, backup × implied total, the gap in four steps),
  `player_prior` (`ops.player_prior_oof`, built in Python — see the design). Registries in
  `src/league_lab/feature_groups/{rookie_prior,oline_quality,qb_x_offense,player_prior}.py`.
* **Design: player_prior is the real out-of-fold residual, not the proxy.** `player_prior.component_walk_forward` fits
  the production component models (same filter, inputs per position, hyper-parameters, frame order) for every season
  S = 2017–2026 on seasons < S and projects season S; the feature for (player, S, W) is the exponentially weighted mean
  (half-life 8 games) of (actual − projected, reference scoring) over his games before (S, W). The harness gets a small
  hook: a group spec may carry `"build": callable(conn)` that `experiments.get_group` calls first (+8 lines in
  `experiments.py`); `player_prior.build` refits only when `ops.player_prior_oof`'s `data_key` (model version, inputs,
  hyper-parameters, scoring, the frame's rows / points) changed: 395 CPU-s, 672 s wall, once. The per-row projections
  are kept in `ops.player_prior_oof_pred` (99,272 rows), which reproduce the harness's cached baseline on 2023–2025 to
  0.00e+00 (Spearman, MAE, hit rate, 24 cells) — so they also score any week subset without refitting the baseline.
* **Verdicts** (harness 2023–2025, both leagues, `OMP_NUM_THREADS=1`): **every group drops at every position.**
  Mean ΔSpearman (seasons better of 3) / ΔMAE:
  `rookie_prior` QB −0.0091 (0) / +0.049, RB +0.0015 (2) / +0.003, WR +0.0013 (3) / −0.009, TE +0.0046 (3) / +0.010 — 793 s;
  `rookie_prior_early` QB −0.0008 (1), RB +0.0011 (2) / −0.009, WR +0.0016 (3) / −0.013 (3 of 3), TE +0.0019 (3) — 602 s;
  `oline_quality` QB −0.0047 (0) / +0.035, RB −0.0004 (1) / −0.008 (3), WR +0.0001 (2) / −0.015, TE −0.0018 (0) — 652 s;
  `qb_x_offense` QB −0.0052 (1) / +0.032 (hurts: worse 2 of 3), RB −0.0004 (1) / −0.005, WR +0.0003 (2) / −0.013, TE −0.0031 (0) — 529 s;
  `player_prior` QB −0.0019 (2) / +0.009, RB +0.0005 (2) / −0.000, WR +0.0017 (3) / −0.017 (2), TE −0.0047 (1) / +0.011 — 552 s.
  No-peek: 0 refusals; largest probe excess 0.0075 (`pn_olq_best_out`, QB); `pp_asof_week` < week on all 109,123
  rows; `oline_quality` has D5's serve-gap warning (week 4's injury report is not in the clone: publishing calendar,
  not a peek). Hand checks: MIN 2025 week 5 (O'Neill, Jackson, Jurgens out) → 3 out, 115 career starts, draft capital
  6, best out = rank 1 (O'Neill), 0.9865 last-season snaps = `tests/test_e4_feature_groups.py`'s fixture; Puka Nacua
  2025 week 6 `pp_resid_ewm` 4.3290 over 33 games = the same weighted mean computed by hand in SQL from
  `ops.player_prior_oof_pred`.
* **Weeks 1–4** (the plan's second number for `rookie_prior`): draft capital orders RBs and WRs better early —
  `rookie_prior` RB +0.0067 / WR +0.0054, `rookie_prior_early` RB +0.0079 / WR +0.0078, 3 of 3 seasons each; QB worse
  (−0.018 / −0.007). It does not help rookies themselves (their weeks 1–4 MAE is flat or worse). Over a season that
  is +0.001–0.002 Spearman: under the bar, and the 2026 season is past week 4.
* **player_prior as a linear correction** (follow-up, `scripts/e4/player_prior_correction.py`): proj + k × the
  player's past miss, k per position fitted on earlier seasons only → ΔMAE RB −0.054 (3 of 3 seasons), WR −0.040 (3),
  TE −0.014 (3), QB +0.007; a constant-shift control is worse (+0.03 to +0.12). Point projection only, ranges not refit.
* **Andrew's questions, plainly.** (1) *Elite QB on an elite offense vs bad QB on a bad offense:* the model does not
  treat them the same — it lowers a team's receivers and backs when the starter is replaced by a worse one — but it
  lowers them a little too little, more so on a good offense: those players finish 0.7 ± 0.3 points below their
  projection when a much worse QB starts on a top-third offense, 0.3 ± 0.3 on a bottom-third one, ~0 when the usual
  QB plays. That is ~6% of player-weeks; handing the model the interactions did not fix it in the walk-forward.
  (2) *Pro Bowl tackle vs backup guard:* by snaps, starts, draft slot and years, which lineman is out barely moves
  fantasy points, and the model's misses do not depend on it (QB +0.29 ± 0.31 with a top-two lineman out vs
  +0.36 ± 0.13 with nobody out; WR / TE −0.04 either way; RB −0.21 ± 0.17 vs +0.10 ± 0.07, the only hint). The proxy
  cannot see grades (PFF), pass-block win rates or contracts.
* **For the PO: ship nothing as v3.1 from the groups.** None passes the rule. Two leads worth a proper test, in order:
  (a) `player_prior` as a post-hoc correction at RB / WR / TE (RB clears the MAE bar 3 of 3, WR close) — needs the
  ranges recalibrated around the corrected projection and a `projections.py` change (PO-only): a
  `walk_forward(..., correction=...)` pass in the harness so it is judged on all six metrics, 2021–2025;
  (b) `rookie_prior_early` at RB / WR for weeks 1–4 of 2027, re-tested on 2021–2025 with a weeks-1–4 decision.
* **Tests.** pytest `tests/test_e4_feature_groups.py` 14 passed (twins on fixtures — draft tier / years in / age,
  OL quality on MIN 2025 week 5, the QB products and bucket, the as-of EWM; the SQL hard-codes the twins' constants;
  the registries validate; with the database the twins reproduce every 2025 row and `ops.player_prior_oof` from the
  out-of-fold projections); full suite 795 passed (59.7 s); ruff clean; dbt `--select int_e4_player_week_rookie_prior+
  int_e4_ol_starter_week+ int_e4_player_week_qb_x_offense+` PASS=16 (4 models, 12 tests).
* **Deviations (for the PO to confirm).** `pn_olq_best_out` is 0 when nobody is out (the plan said NULL): NULL keeps
  meaning "not known" (week 1, report not out), as everywhere else. `rk_age` is the age on September 1 (constant in
  the season), not at the week. The first `qb_x_offense` run had four products (QB −0.0043 / +0.025, RB +0.0002,
  WR +0.0005 / −0.006, TE −0.0023 — drop; its rows: `scratchpad/waveE/e4/e4_qb_x_offense_4col_run.csv`); the
  recorded run adds × EPA per play and the bucket, as the plan listed. `rookie_prior_early` is an extra group (the
  weeks 1–4 result asked for it). Two scripts under `scripts/e4/` (week subsets, the correction) — new files outside
  the listed paths, ruff clean; move or drop them as you prefer.
* **For the seed.** `scratchpad/waveE/e4_experiments.csv` = the 120 rows of `ops.feature_experiments` for the five
  groups (24 each), for `dbt/seeds/feature_experiments.csv`. Nightly: nothing to add (the full build builds the three
  dbt tables, ~15 s; `ops.player_prior_oof` is built only by `league-lab experiment player_prior`).

### E2 2026-10-01 — rest of season (branch `dev/E2`, clone `league_lab_e2`)

* **Mart** `mart_player_ros_projection` (`dbt/models/marts/edge/`, + `mart_player_ros_projection.yml`, 14 tests): one row
  per league × player — Scrubs 645 (581 QB/RB/WR/TE + 32 K + 32 DEF), dynasty 581; ~1.1 MB; builds in 2.4 s. Window
  `from_week` (lib.ui's week rule in SQL from `dim_game`, at build time: 4 in the clone) … `last_week` = **the league's
  final** (Scrubs 16, dynasty 17: playoff start + winners-bracket rounds), byes excluded (no `dim_game` row for his team
  = no game: every team's bye is in weeks 5–14, so every 2026 row has exactly one in the window), `ros_points`,
  `ros_games`, `playoff_points` (weeks ≥ `dim_league_season.playoff_week_start`), ranks by position and overall within
  the league (active NFL roster only; injured reserve keeps its total, no rank), range = weekly 80% ranges combined as
  independent normals (sd = (p90 − p10) / 2.563, √Σ, ∓ 1.2816 sd, floored at 0 — stated as the assumption in the yml,
  METRICS and on the pages), `weeks_json`, `bye_weeks`, `weeks_with_lines`. DEF keyed by its Sleeper id (`player_key`).
  Betting lines verified: `mart_player_week_features.implied_team_total` is set for 581 week-4 rows and 0 rows of weeks
  5–18, so `weeks_with_lines` = 1 everywhere.
* **Surfaces** (`app/lib/ros.py`: the shared sentences, pure, tested): Player card — one line after the stat line
  ("Rest of season: **232 points** over 13 games (likely 190–273), **WR4** in this league · playoffs (weeks 15–17): 54")
  and a caption with the week-by-week values ("wk 4 18.1 · 5 18.0 · 6 bye · 7 17.7 …") and the betting-line note;
  Rankings — **a new "Rest of season" section under the weekly board** (the board is untouched): its own position
  switch (QB RB WR TE + K / DEF where the league has them + All = overall rank), an answer card (#1, "Yours: …"), a
  five-column list (Rank · Player · Points · Games · Playoffs) and an expander with every column; the "Who" filter
  applies, ranks stay the league's; Trade Finder — under Fit and Market in "Try a trade" ("Rest of season (weeks 4–17,
  through this league's final): you give **232** points, you get **120** (−112).") and as a caption on the best-partner
  card; "Rest of season" + "ROS rank" columns in "Market line: every number". The engine is unchanged. Every surface
  degrades to nothing (no exception) on a copy without the mart (`missing_relations`, not `require_relations`).
  `table.py`: 15 columns under `# ---- E2 rest of season`. How-to bullets on all three pages; WORDS.md rows.
* **Evidence.** By hand (`waveE/e2/hand.sql`: the board's weekly rows, a `dim_game` join per week by team, no mart
  logic): Amon-Ra St. Brown, dynasty (**Andrew's roster 12**), weeks 4–17, bye 6 → 13 games, 231.61 points, playoffs
  53.55, sd 32.55 → 189.9–273.3 — the mart: 13 / 231.61 / 53.55 / 32.55 / 189.9–273.3; Puka Nacua, Scrubs, weeks 4–16,
  bye 11 → 12 games, 184.66, playoffs 30.30, sd 27.02 — the mart: the same, WR1. `tests/test_ros.py` recomputes **every**
  row in Python (window, byes, totals, playoffs, sd, p90, ranks) and checks the trade engine's `MARKET_SQL` on the same
  weeks: equal on all 1,226 rows. Same player on the three pages (AppTest, dynasty roster 12): Player "232 points …
  WR4", Rankings "Yours: #4 Amon-Ra St. Brown 232", Trade Finder "you give 232" and ROS rank "WR4". Edge cases: a
  kicker (McLaughlin, Scrubs: "97 points over 12 games … K16"), injured reserve (Jaxson Dart, Scrubs: 211 points, "not
  ranked (on injured reserve)"). `uv run pytest -q` 790 passed (9 new in `tests/test_ros.py`); ruff clean; `test_app_guards` passes; headless check
  (`apptest_e2.py`, 39 runs, both leagues) ALL OK, 0 exceptions. Screenshots 390 / 1300 px:
  `scratchpad/waveE/e2/{player_dynasty,rankings_scrubs,rankings_dynasty,trade_dynasty}_{390,1300}.png`.
* **Decisions for the PO.** (1) The window ends at **the league's final**, not week 18: weeks after it count for nobody
  in the league; the plan's example said "playoffs (weeks 15–17)" — Scrubs' playoffs are 15–16. (2) The trade engine's
  market (`trades.MARKET_SQL`, "Season pts") still runs to week 18: +14% points in Scrubs, +7% in the dynasty over what
  the league plays; I left it (no engine change) and labelled both; suggest the market adopt `last_week` (one `between`
  in `MARKET_SQL` / `REPLACEMENT_SQL`). (3) Ranks exclude players not on an active NFL roster (IR, inactive): their
  projections run full (Dart 211, Mason 111) because the model does not know IR — the projection itself should, for
  weeks inside a known IR stint (PO-owned `projections.py`). (4) The range is centred on the projection (not on the
  quantiles' median) and is the narrowest honest one: its coverage is not measured (no per-row walk-forward output in
  the clone) — measure on 2024–25 and inflate by position if it under-covers. (5) `metric_registry.csv` (seeds are out
  of bounds): add `ros_points` ros1.0 (numerator Σ proj_points over the league's remaining weeks with a game, grain
  league × player, status active) and `ros_range` ros1.0 (independence assumption).
* **Makefile** `project`: `mart_player_ros_projection` appended to the `--select` line (it is already covered by
  `mart_player_week_projections+`; `scripts/nightly.sh` `projection-marts` needs no change for the same reason — add it
  for symmetry if you like). The hosted sync picks it up (the pages name `analytics.mart_player_ros_projection`).

### E1 2026-10-01 — "Our record": League Lab against Sleeper's own projections (branch `dev/E1`, clone `league_lab_e1`)

**What.** `league-lab ingest sleeper-projections` (`src/league_lab/ingest/sleeper_projections.py`) pulls Sleeper's
projections for the next week to kick off into `raw.sleeper_projections` (full payload + the stat line parsed into
the weekly-stats column names; one snapshot per pull, never overwritten; archive
`data/raw/sleeper/projections/<season>/<week>_<stamp>.json.gz`; `--offline` replays it; host configurable as
`LEAGUE_LAB_SLEEPER_PROJECTIONS_URL`; DDL in `db migrate`). `mart_projection_record` holds our kickoff board vs
Sleeper's last pre-kickoff snapshot (priced in each league's scoring with `league_points`) vs the actual points,
per league × season × week × position (QB–TE: Spearman, MAE, top-N hit rate on the players both projected; `ALL`:
the cards' start/sit calls — who called it right) plus season-to-date rows. Page `app/pages/13_Record.py` "Our
record"; one paragraph + link in Rankings' "The model" after "How it was graded". Nightly: `replay-projections`
(after `replay-weather`), `fetch-projections` (soft, before `save-record`, skipped with `NIGHTLY_SLEEPER_OFFLINE=1`),
`mart_projection_record` on the projection-marts `--select` (Makefile `project` too; new target
`make sleeper-projections`). Definitions: METRICS § "Projection record".

**Evidence (sandbox: Sleeper unreachable, every Sleeper number below is a FIXTURE).**
* Pricing (acceptance): Sleeper's line priced with League of Scrubs' settings (standard half PPR) reproduces the
  fixture's `pts_half_ppr` on all 29 priced players with a worst difference of 0.00 (≤ 0.05 required); with rec = 1 /
  0 it reproduces `pts_ppr` / `pts_std` the same way; worked by hand: Josh Allen 25.50 (Scrubs), 31.575 (dynasty);
  Will Reichard 9.1. The fixture's `pts_*` are computed from Sleeper's own keys, never through our mapping.
* Loader round trip (`tests/test_sleeper_projections.py`, 18 tests): pull → one snapshot file + sidecar, 31 rows
  (32 objects, one without `player_id`); `--offline` on a fresh store rebuilds identical rows; replaying again =
  `skipped_unchanged`; an unchanged pull adds no file; a changed pull is a second snapshot (62 rows); a bad / empty
  / 404 answer fails and leaves no file; a hand-curled `.json` replays with its name's stamp as the fetch time.
* In `league_lab_e1`: 5 fixture snapshots replayed through the CLI (weeks 2 and 4; week 2 has one AFTER kickoff,
  which the record ignores: `sleeper_fetched_at` = 2026-09-17 12:00 UTC); **to show a scored week the clone's
  week-2 and week-4 boards were relabelled `kickoff` (they are `refit` / live in the PO's database) — clone only**.
  The mart: 30 rows; hand checks (`scratchpad/waveE/e1/check_record.py`): SQL `league_points` = Python
  `price_line` on 2,136 priced rows (max diff 0.0000); Scrubs week 2 WR recomputed in pandas (n 137, Spearman 0.555 /
  0.533, MAE 4.18 / 4.33, hit@36 0.500 / 0.472) = the mart; the SQL's start/sit pairs = `cards.decisions()` on the
  same lineup rows, 132 of 132. Fixture record (meaningless numbers): Scrubs week 2, 18 of 29 calls right vs 12 for
  "Sleeper", MAE 4.07 vs 4.19; dynasty 15 of 33 vs 15, 4.91 vs 5.00; week 4 `in_play`.
* dbt: `mart_projection_record` + 15 tests PASS (incl. `n_both ≥ 1`, `1 ≤ n_players ≤ n_both` on scored rows, calls
  add up, snapshots precede kickoff); `uv run pytest -q` 799 passed; ruff clean; shellcheck clean; headless check
  41 runs ALL OK (every page, both leagues); the page's three states checked (empty, week in play only, scored);
  screenshots 390 / 1300 px in `scratchpad/waveE/e1/shots/`.

**Open.** No real Sleeper answer has been seen: the parser follows the documented shape and keeps everything in
`payload`; the first pull on the Mac is the real test (commands in the hand-back). K is priced, DEF is not (pairs
with a DEF are counted apart). The record starts the first week Andrew's nightly pulls Sleeper before kickoff.

### E3 2026-10-01 — any league: the design and a working spike (branch `dev/E3`, clone `league_lab_e3`)

Design for Andrew and the PO: `docs/ANY_LEAGUE.md`. Nothing in `app/`, `dbt/`, the seeds, `projections.py`,
`lineup.py`, `decisions.py` or `cards.py` changed; the spike reads them.

* **Built.** `src/league_lab/anyleague.py`: a read-only Sleeper client (league / rosters / users / the player
  directory, TTL cache; `LEAGUE_LAB_SLEEPER_FIXTURES=<dir>` reads fixtures; ids must be digits), `load_board` (the
  week's NFL-wide stat lines from one league's `ops.projections` rows + every fitted league's ranges + status from
  `mart_player_week_projections` + K / DEF from `ops.projections` × `mart_kd_week`), `price_lines`
  (`scoring.compute_points`, bonuses included), `choose_reference` + `approximate_ranges` (the ratio method), and
  `lineup_rows`, which assembles a `lineup.LineupInputs` for one roster-week and runs **`lineup.build`** (the
  nightly's own code: IR / taxi / bye / Out / Doubtful / locks / unvalued) and returns the frame
  `cards.lineup_rows` returns. `write_fixtures` / `python -m league_lab.anyleague fixtures <dir> <ids>` builds the
  fixtures from `raw.sleeper_*` payloads trimmed to the fields read (no avatars, nicknames, chat; managers and team
  names pseudonymised as "Manager n" / "Team n"):
  `api/tests/fixtures/sleeper/` (120 KB: both leagues, 312 rostered players). API: `ondemand.py` (same JSON as
  `myweek.my_week` + `source`, `on_demand`), `/api/my-week` falls through when the league is not a current league of
  the database (`source=sleeper` forces it), `myweek.cards_from_rows` (the card extraction, shared; cards gain
  `p_win`), 404 for a league Sleeper does not have, 502 when Sleeper does not answer. `api/league_lab_api/__init__.py`
  puts `src/` on the path; **the Dockerfile now copies `src/league_lab`** (since D6 `cards.py` imports
  `league_lab.decisions`, which the image did not contain — not verified here: no Docker daemon).
* **Parity (acceptance)**, week 4, the mart's `as_of` (2026-10-01 19:26 UTC), each league served as if it were new
  (ranges from the other league): dynasty roster 12 — lineup value **111.46 = 111.46**; QB Nix 19.78, RB1
  Croskey-Merritt 9.70, RB2 Wilson 8.68, WR1 St. Brown 18.13, WR2 Washington 14.60, TE Kittle 10.36, FLEX Boston
  11.13, SUPER_FLEX Rodgers 19.08, margins 1.01 / 1.48 / 0.46 / 7.90 / 4.37 / 0.84 / 0.90 / 0.31 — all identical;
  13 bench in the same order, 4 can't play (taxi ×3, IR) with the same reasons. Scrubs roster 2 — **117.02 =
  117.02**, 10 slots identical incl. K McLaughlin 8.07 and DEF KC 7.16 (identical kicking / defense keys → the
  fitted kd1.0 values — i.e. Scrubs' own K / DEF fit, since the dynasty has none; QA: a new league with different
  K / DEF keys gets them unvalued), 5 bench, 2 IR. Pricing: `compute_points` on the stat line = `ops.projections.proj_points`
  for all 581 week-4 players in both leagues (max gap < 1e-9; no rounding, bonus or stat difference); 0 stat-line
  mismatches between the leagues. Unmapped players on both rosters: 0. Scoring keys the projection cannot price:
  dynasty `not_projected` = long-TD ×3, 2-pt ×3, `fum_rec_td`, `st_td` (0 in the nightly too); Scrubs 2-pt ×3,
  `fum_rec_td`, `st_td`; unmapped: none (DEF keys count only in a league that starts a DEF).
* **Range approximation (the open modeling piece).** `p_q(new) = proj(new) + (p_q(ref) − proj(ref)) × proj(new) /
  proj(ref)`, the reference = the fitted scoring nearest by median |log price ratio|. Weeks 4–18 (8,134 player-weeks),
  each league from the other, mean abs gap P10 / P25 / P50 / P75 / P90: dynasty 0.23 / 0.26 / 0.32 / 0.59 / 0.84,
  Scrubs 0.19 / 0.22 / 0.26 / 0.49 / 0.69 points; 80% width 13.96 → 13.78 and 11.49 → 11.63. 80% coverage on weeks
  1–3 (715 played rows each): fitted 79.2% → rebuilt 78.0% (dynasty), 78.2% → 78.0% (Scrubs); unscaled offsets 59.9%
  / 88.5%; one scale per position slightly worse (P90 gap 0.87 / 0.72). Error vs distance (P90 gap / 80% width):
  |log ratio| ≤ 0.1 3.5%, 0.1–0.2 5.5%, 0.2–0.3 7.0%. Andrew's rosters, week 4: dynasty 12 (25 players) P10 0.52 /
  P90 1.09; Scrubs 2 (16) 0.65 / 0.98; card probabilities within 0.1 of the database path (tested).
* **Latency** (`ondemand.my_week`, local database, fixtures — no Sleeper network): cold 259–331 ms (board query
  34–91 ms, cards 67–69 ms, pricing 11–18, ranges 11–15, inputs 14–19, solve 1.6–2.7, frame 20–21), warm 141–158 ms
  (cards 61–72 ms — the 3 × 40,000-draw win probability — is the largest part; board 11–15 from the cache).
* **Checks.** `cd api && uv run pytest -q`: **51 passed, 2 skipped** (37 + 14 new in `tests/test_anyleague.py`;
  `test_myweek.py::test_unknown_team_and_league` now sets the fixture directory: an unknown league is looked up on
  Sleeper, and league "1" is still a 404). `uv run ruff check src tests app api/league_lab_api api/tests` clean; `cd
  api && uv run ruff check .` clean. Scratch: `waveE/e3/measure_ranges.py` (the range table), `try_ondemand.py`.
* **For the PO.** (1) Range method: ratio scaling from the nearest of a few *reference scorings* fitted nightly
  (proposed seed `reference_scorings.csv`: Scrubs, dynasty, full PPR 4-pt, standard, TE premium). (2)
  `projections.py`: fit `fit_position` / `predict_position` on that fixed dict instead of the env's leagues; write
  `ops.projection_lines` (one row per player-week) + `ops.projection_ranges` (per reference scoring); `kdef.py`: keep
  `predict_kd`'s league-free lines (`ops.kd_lines`). (3) Wave F order: those outputs → username league picker +
  on-demand My Week + the opponent (matchups call) → the player card in the user's scoring → waiver wire on request →
  Wave G (accounts, payments, shared cache, rate limit) → Trade Finder.
* **Not verified / open.** No Sleeper from the sandbox: the live client is untested against the real host (Andrew:
  `cd api && uv run uvicorn league_lab_api.main:app --port 8581`, then open
  `http://localhost:8581/api/my-week?league=<any Sleeper league id>&team=<roster id>`; the first call fetches the
  ~15 MB player directory). The opponent, the league rank and Sleeper's weekly lineup lists are not on the on-demand
  path; a K / DEF in a scoring no fitted league shares is unvalued; Sleeper's terms for commercial use are Andrew's
  to check. No `--select` appended; no seeds or metrics touched.

## Wave F (Iteration 14)

### PO merge — Wave F, 2026-10-02

* **Delivered** (three Opus devs in parallel, ~25–40 min each; one 11-minute QA walk through the built app against the
  API): F1 the NFL-wide outputs (`reference_scorings` seed — scrubs, dynasty, ppr, standard, te_premium; `ops.projection_lines`
  9,911 rows, `ops.projection_ranges` 5 × 9,911, `ops.kd_lines` 1,088, `ops.kd_ranges` 5,440 on the PO's copy; the house
  leagues' `ops.projections` unchanged to the last digit; the freeze applies to all four tables; `project` 1.3–2× longer);
  F3 the API for any league (`/api/leagues?username=`, the opponent, `/api/player` and `/api/ros` on demand, `/api/record`,
  the Sleeper client with caches and a 300/min token bucket, the Dockerfile serving `web/dist`, `docs/SLEEPER_TERMS.md`);
  F2 the web app phase 1 (sign in with a Sleeper username → league picker → My Week → player card → Rest of season →
  Our record; 14 fixture e2e, first content ~100 ms on fixtures, 34.5 KB gzipped).
* **Integration**: F3 expected the K / DEF ranges as rows of `projection_ranges`; F1 keeps them in `ops.kd_ranges`
  (`unit_id` key) — the reader now has both (`anyleague.NFL_WIDE["kd_ranges"]`); the pricer passes the position so a
  TE premium prices; `/api/leagues/{id}/rosters` serves an unknown league from Sleeper (F2's team picker); the fictional
  league's DEF test re-pinned to a hand re-pricing of F1's real lines (it assumed F3's synthetic sacks-only line). On the
  NFL-wide board both house leagues reproduce the marts (lineup 111.15 / 117.02, slots, values, margins; `api` 83 passed
  on both boards; the default `auto` picks `nfl_wide` once the tables hold the week).
* **QA findings fixed by the PO**: (HIGH) Rest of season showed every defense as a free agent in a house league —
  the availability join used `gsis_id`, which a defense lacks; it joins on the Sleeper id for them; (MED) the betting-line
  caveat on `/api/ros` + the screen; `missing` on a player card in plain words (`missing_keys` keeps the keys); the record
  page's "the nightly" / "whose were closer" / the promise to a league that gets no record; (LOW) the Movers line's
  Trends-page reference gone from the app, a league Sleeper does not have is a 404 on `/api/record` and says so in the
  app, link hit areas ~44 px, `/api/status` says which board is in use. Left: the fixture team names differ between
  screens (pseudonymised fixtures, not a bug); one Back-button skip seen once after switching leagues twice (not
  reproduced); 1300 px walk for the house leagues not repeated.
* **Checks**: root `pytest` 829 passed; `api` 83 passed; web lint 0 / 0, build, 14 fixture e2e; dbt 130 PASS on the
  projection marts + the four new tests; ruff clean.
* **Open for Wave G** (waits on Sleeper's licensing answer): accounts, payments, hosting (the Dockerfile is ready; no
  daemon here to build it), a shared cache / bucket across processes, `ops.projection_*` into `RECORD_TABLES` after
  the first hosted sync, Trade Finder and waivers on demand, search for an unknown league, the one-query ROS board.

### F1 2026-10-02 — NFL-wide model outputs (reference scorings, `ops.projection_lines` / `_ranges`, `ops.kd_lines` / `_ranges`)

* **What**: `league-lab project` fits the residual ranges per **reference scoring** (seed `reference_scorings.csv`:
  `scrubs`, `dynasty` — the house leagues' settings copied from `dim_league_season` — `ppr`, `standard`,
  `te_premium`) instead of per house league, and writes the stat line once for the NFL (`ops.projection_lines`), the
  ranges per reference scoring (`ops.projection_ranges`), the K / DEF lines (`ops.kd_lines`) and their priced ranges
  and offsets per reference scoring (`ops.kd_ranges`), all under the B5 freeze. The house leagues' `ops.projections`
  is derived from the same numbers (line priced in the league's scoring + the ranges of the reference that IS the
  league; a league no reference is would be fitted on its own). `bonus_rec_te` (and the RB / WR catch premiums) are
  priced by `compute_points` when the row carries the position — Python only; the SQL macro and the seed are
  unchanged (`unmapped_keys` still reports them). Docs: METRICS § "NFL-wide outputs", DATA_MODEL § ops,
  ANY_LEAGUE § "What changes elsewhere".
* **Evidence (clone `league_lab_f1`, 2026-10-02, week 4 kicked off 00:15 UTC)**:
  * Rows: `projection_lines` 9,911 (weeks 1–3 `refit` v2.0 1,777, week 4 `kickoff` v3.0 581 frozen_at 2026-10-01
    19:25:19, weeks 5–18 live 7,553); `projection_ranges` 49,555 (5 × 9,911; `scrubs` / `dynasty` weeks 1–4 copied
    from the record with its labels, `ppr` / `standard` / `te_premium` weeks 1–4 ranged around the stored line,
    `refit`); `kd_lines` 1,088 (K 544, DEF 544; weeks 1–4 `refit`); `kd_ranges` 5,440 (5 scorings × K / DEF × 544).
  * House rows = NFL-wide rows, every week 1–18: 9,911 QB–TE rows per league, max gap 0 on the 12 components and on
    proj_points / P10–P90 (P25 / P75 NULL on the same rows), 0 label / fitted_at mismatches, 0 rows on one side only;
    lines × the league's scoring (`compute_points`) = `ops.projections.proj_points` max gap 0 (both leagues); the SQL
    `league_points` re-pricing of the lines = `projection_ranges.proj_points` at 1e-9 for `scrubs` / `dynasty`: 0
    violations. Scrubs K / DEF: 896 rows = `kd_ranges` `scrubs` and = `kd_lines` × Scrubs' scoring, gap 0 (week 4's
    kickoff rows included: the refit line reproduces them exactly). TE premium: `te_premium` − `ppr` = 0.5 × projected
    TE catches (≤ 0.0096, two 2-decimal roundings), 0 at QB / RB / WR.
  * No change to the house leagues' numbers: `ops.projections` after F1 vs before (same data, a snapshot taken after
    a pre-F1 run): 20,718 rows, max value gap 0; only `fitted_at` of the 15,938 rewritten rows (weeks 5–18) moved;
    weeks 1–4 untouched (labels, `frozen_at`, `fitted_at`).
  * Week 4 frozen in every table (table above); dbt: `assert_frozen_nfl_wide_precede_kickoff`,
    `assert_projection_ranges_price_the_lines`, `assert_house_projections_are_the_nfl_wide_rows`,
    `assert_frozen_projections_precede_kickoff`, the four sources' one-row-per-key tests, the seed's tests — 17 PASS;
    each new test fails on a one-row mutation (range +0.01 → 1; a line +1e-6 → 2; a live row labelled `kickoff` → 544).
  * Runtime of `project` (OMP_NUM_THREADS=1, shared cores): 233 s before, 463 s after (1.99×; the fits 2:50 → 6:10);
    a second run 312 s (1.34×, less contention). The second run kept weeks 1–4 in all four tables and rewrote 5–18.
  * The freeze on the new tables: writing the same rows twice leaves all four tables md5-identical; a write at week
    5's first kickoff + 1 h labels week 5 `kickoff` in every table (543 / 2,715 / 60 / 300 rows, frozen_at =
    fitted_at) and keeps its values against a refit that changed them (scripts in the hand-back).
  * `backtest-v2` unchanged (not run): it calls `league_scorings` and the same `fit_position` / `predict_position`;
    the only change on that path is the position riding along into `compute_points`, which neither house scoring
    weights — the same path reproduced `ops.projections` to 0 above.
* **Nightly**: the four tables are in `STATE_TABLES` (restored from the hosted copy on a fresh database), not in
  `RECORD_TABLES`: `restore_state` stops the night when a record table cannot be read on the hosted copy, and the
  hosted copy has no such tables until the first sync after the merge, so adding them now would stop the first
  night on the Mac and in Actions. If a restore fails, `project` re-seeds the frozen QB–TE lines and the house
  ranges from `ops.projections` (a record table); only the `ppr` / `standard` / `te_premium` ranges and the K / DEF
  lines of frozen weeks would come back as `refit` values. Promote them to `RECORD_TABLES` once one sync has
  published them (Wave G, when customers' frozen weeks become a record).

### F3 2026-10-02 — the API for any league

**What a Sleeper manager gets from the API now, for any league.** Type a Sleeper username → their leagues this season
and their team in each (`/api/leagues?username=`); My Week with **this week's opponent** and his best lineup value;
the player card, rest of season (`/api/ros`) priced in their league's scoring; the record for the house leagues. A
house league gives the same numbers on demand as from the nightly (tested to the cent, opponent and rest of season
included).

* **Sleeper client** (`src/league_lab/sleeper_client.py`, split out of `anyleague`): caches by kind (player directory a
  day, on disk in `LEAGUE_LAB_CACHE_DIR`; league / users a day; rosters 10 min; matchups 5 min; user lookups 1 h),
  the last good answer on failure, a token bucket of 300 calls/min (503 `{"error": "busy, try again in a minute"}`),
  `/api/status` → `sleeper` (calls, bucket, cache ages per kind, the directory file's age). Budget per active league:
  `docs/SLEEPER_TERMS.md` (4 calls a first open, 0.3 calls/min kept open, ~1,000 open leagues per process).
* **F1's read path** (`anyleague.load_board`): `ops.projection_lines` / `ops.projection_ranges` / `ops.kd_lines` /
  `reference_scorings` when they hold the week (names in `anyleague.NFL_WIDE`, the one place), else E3's borrowing.
  A league's range reference: exact match on the mapped keys (rounded to 3 places), else the nearest by median
  |log price ratio| over the reference set. K / DEF priced from their stat lines with `kdef.price` in the league's own
  scoring (the API now depends on `pydantic-settings`: `kdef` → `rankings` → `config`). Tested in this clone with the
  tables built by `api/tests/fixtures/f1_tables.sql` (DDL F3 expects + a fill from `ops.projections`; the K / DEF
  lines are synthetic — `ops.projections` keeps no K / DEF line — PAT-only kickers, sack-only defenses that price back
  to the Scrubs values).
* **Evidence** (week 4, this clone): `cd api && uv run pytest -q` **81 passed, 2 skipped** (51 before + 30 in
  `tests/test_f3.py`); `uv run ruff check src tests app api/league_lab_api api/tests` clean.
  - NFL-wide board, both house leagues: starters, slots, values, margins, bench and lineup value equal the marts
    (≤ 0.005), ranges equal (≤ 0.011, an exact reference: `half_ppr_4pt_kdef`, `sf_ppr_6pt_bonuses`); Scrubs K / DEF
    from lines = the nightly's. Borrowed board unchanged (E3's numbers: roster P90 gap 1.09 / 0.98).
  - Opponent (fixture: week-3 pairings as week 4): Scrubs 2 vs roster 6, **120.31** on demand = `ops.lineup_totals`;
    dynasty 12 vs roster 1, **131.91** = `ops.lineup_totals`; both boards.
  - Rest of season on demand vs `mart_player_ros_projection`: the **same players** (645 Scrubs incl. K / DEF, 581
    dynasty), ros_points / playoff_points ≤ 0.011, games, position and overall ranks identical — so the on-demand
    `pos_rank` is the mart's population (every projected player on an active NFL roster, rostered or not); P90 ≤ 0.11 on
    the NFL-wide board, mean gap 0.99 / 1.40 on the borrowed one. Bijan Robinson, Scrubs: 236.25 over 12 games,
    196.5–276.0, RB1, playoffs 39.18 — mart and on demand.
  - Test League (fictional, full PPR 4-pt, sack 2 / fgm_50p 6 / pts_allow_0 12, K + DEF): solved, K and DEF valued from
    lines (a defense prices at 2 × its Scrubs value: sack 2); on the borrowed board its K / DEF stay unvalued and
    reported. `/api/leagues?username=test_manager`: 3 leagues, rosters 12 / 2 / 1, labels = `dim_league_season`'s.
  - Latency (this sandbox, three devs on two cores; fixtures, so no Sleeper time): `/api/my-week` on demand cold
    483–571 ms / warm 112–137 ms (opponent solve 18–62 ms cold, 5–14 warm); `/api/leagues?username=` 107 ms cold;
    `/api/ros` on demand cold 1.5–1.8 s (14 weekly boards) / warm 0.13–0.34 s, house league 9 ms; `/api/player` on
    demand 1.2 s cold (includes rest of season) / 0.6 s; `/api/record` 3–14 ms; `/api/status` 13 ms.
* **Decisions for the PO**: (1) the database path's opponent also asks Sleeper's matchups (the nightly's
  `fct_league_matchup` has no week-4 rows yet), falling back to the table; `summary` stays Home.py's copy (parity).
  (2) Errors carry `error` (contract) and keep `detail` (the D7 web client). (3) `opponent` adds `matchup_id`. (4) On
  demand the player card lists `missing` (`value.points_per_game`, `signals.upside`) and reads the NFL-wide columns
  (usage, injury, role alerts) from the first house league's marts. (5) Rest-of-season windows for a new league use
  ceil(log2(playoff teams)) rounds (the mart's fallback; the bracket call is not spent). (6) Fixture user ids are
  pseudonymised (`91…`) in the current fixtures (earlier commits still hold the real ids).
* **Open**: `/api/search` for an unknown league (the card's search box) is not on demand yet; the ROS board loads
  week by week (one query for all weeks would cut the cold 1.5 s); the Sleeper winners-bracket call for exact playoff
  rounds; a shared cache / bucket for several processes (Wave G); F1's real column names at integration
  (`anyleague.NFL_WIDE`).

### F2 2026-10-02 — the web app, phase 1: any Sleeper manager's screens (branch `dev/F2`, clone `league_lab_f2`)

* **What.** `web/` now opens with **"Your Sleeper username"** (after the beta password, which stays) →
  `GET /api/leagues?username=` → the league picker (name, size + scoring, "Your team: …"; "You have no team in this
  league" for `roster_id: null`) → **My Week** for any league with the **opponent of the week** ("Week 4 vs **Hail
  Marys**, projects 108 — you project 134") → the **player card** (+ the rest-of-season line, sections in `missing`
  left out and named) → **Rest of season** (`/ros`: the answer, "Yours", Rank · Player · Points · Games · Playoffs;
  K / DEF only where the league starts them; All = overall) → **Our record** (`/record`: the summary sentences, two
  numbers, the start/sit table; the Streamlit page's empty states). Username and league list remembered on the
  phone; a `?league=&team=` link still wins and works for any league id. Three tabs under the picker; "Other leagues
  (your Sleeper username)…" is the league select's last option; a linked league in neither list is named from My
  Week's answer.
* **Built against the contract with fixtures.** `web/fixtures/`: 36 response files + 47 player cards (796 KB),
  rebuilt by `web/fixtures/make_fixtures.py` — saved from the API on the clone (leagues, rosters, My Week dynasty 12
  / Scrubs 2 week 4, every lineup player's card, search, status) with the contract's new fields added (`source`,
  the `opponent` object, `ros`, `missing`), `/api/ros` from `mart_player_ros_projection` in the contract's shape
  (19 files), `/api/record` (Scrubs: the clone's real empty answer; dynasty: three hand-written scored weeks — the
  mart is empty on the clone), and the fictional **Test League** `9000000000000000001` (10 made-up teams; team 3's
  roster of real players with their week-4 Scrubs-scoring projections; `source: "sleeper"`, `missing: ["value"]`,
  record `available: false`). `e2e/fixtures.ts` answers every `/api` call from them (route interception, the gate
  simulated).
* **Evidence.** `npm run e2e:fixtures`: **14 passed** (7 tests × phone 390 × 844 / desktop 1300 × 900, ~20 s): the
  full path password → username → picker → My Week → tap a player → card → Back (scroll position equal) → rest of
  season → record on the Test League, one history entry per tap, no popup, no sideways scroll, ≤ 5 columns, the first
  card inside the first screen, no "not in the database" anywhere. The spike's live-API suite (`npm run e2e` against
  the API on :8681): **22 passed, 2 skipped** (the gated pair needs a password API). `npm run measure:fixtures` (7
  loads each, cold, median): first content **92 ms phone / 97 ms desktop** (Test League), 105 / 111 ms (dynasty 12) —
  limit 500 ms. `npm run lint`: 0 errors, 0 warnings (107 files). Build: 100.8 KB JS (34.5 KB gzipped) + 21.8 KB CSS
  (5.3 KB). Worked example: the WR answer "Puka Nacua, 185 points over 12 games (likely 150–219) · playoffs: 30" =
  the mart's 184.66 / 12 / 150.0 / 219.3 / 30.3 rounded half up; the dynasty opponent line "projects 110.7 — you
  project 111.2" = roster 11's week-4 starters in `ops.lineups` (110.69) vs My Week's `lineup_value` 111.15 (one
  decimal because whole points would both read 111).
* **Decisions for the PO.** (1) `/` with nothing remembered now opens the sign-in, not the reference league. (2)
  The rest-of-season answer, "Yours", its caption and how-to, and Our record's sentences are assembled in
  `web/src/lib/ros.ts` / `record.ts` with the Streamlit pages' words (`4_Rankings.py`, `13_Record.py`): the contract
  sends numbers only. The port rule wants them in `app/lib` and sent by the API (PO: move the Record page's sentences
  to `app/lib/record.py`, the Rankings ROS answer to `app/lib/ros.py`). (3) Expanders remember being open per page,
  so Back can restore the scroll of a page whose expanders were open (desktop failed without it).
* **Assumed (requests to F3).** `/api/leagues/{id}/rosters` answers for an unknown league; `/api/ros` adds
  `positions` (else the UI reads K / DEF from My Week's lineup), `rank` for `position=ALL` (else list order), the
  playoff window and `weeks_with_lines`; `/api/record`'s `summary` is the season `ALL` row and `weeks` the
  `scope = 'week'` rows; the player card keeps the `ros.card_line` sentence in the Projection section (or sends
  `ros.line`); errors may be `{"error"}` or today's `{"detail"}` (both read); `opponent` may be today's string
  (then the record line keeps "week N vs **X**"). Usernames are sent as typed (trimmed): F3 should match them
  case-insensitively.
* **Not verified.** Real Sleeper (no network here), F3's real responses for the new routes (fixtures only), a real
  iPhone (Chromium with the iPhone 13 profile).

## Wave G (Iteration 15)

### PO merge — Wave G, 2026-10-02

* **Delivered** (four Opus devs in parallel, 35–58 min each; one 23-minute integration pass that reconciled G3's assumed
  research shapes with G1's real ones in one mapping layer, `web/src/lib/shapes.ts`, and re-saved the research fixtures from
  the live API): G1 the research routes for any league (trends, defense heatmap, cornerbacks, players, receivers, compare,
  game logs; priced-on-request points equal the league marts to 0.0000 on 40,652 games); G2 the decisions for any league
  (waivers, trade evaluate / partners, team hub, league — the nightly's own code paths, mart parity row for row); G3 the
  design system (dark-first tokens, team colors, the player card as the unit, a 1 KB inline-SVG chart kit, one bar on every
  screen) + the five research screens + "About the numbers" (the record folded in, as Andrew asked); G4 the four decision
  screens. Live walk of 54 screens against the integrated API: 0 console errors, 0 failed requests, no sideways scroll.
* **PO fixes after integration**: `/api/team` carries the league behind each slot (`league: {avg, best, rank, n}`) and each
  week (`{median, best, rank, n}`) — G4's screen had these only in its fixtures; `/api/trends` takes `metrics=none` (the
  screens never read the metric rows: 716 KB → ~60 KB) and the app asks for `min_games=2` so a one-game player is not "due";
  the defense route documented; the STATUS sections ordered.
* **Checks**: `api` 138 passed; web lint 0 / 0, build, 52 fixture e2e; ruff clean; root `pytest` unchanged (no `src` model
  code touched beyond `waivers.sweep_roster`, re-verified against `ops.waiver_moves` row for row).
* **Open**: real headshots and real Sleeper only on the Mac (the sandbox reaches neither); buy-low / sell-high lists and
  the upside stash on Waivers; the keeper table on demand; "What it leans on most" on About needs a route; the cornerback
  starters follow Sleeper's current lineup; the one-query rest-of-season board; Wave H (accounts, Stripe, hosting) waits
  on Sleeper's licence — the non-commercial beta can be hosted meanwhile (`api/Dockerfile`).

### Integration (PO) 2026-10-02 — G3's research screens on G1's real answers (branch `integration/wave-g`)

The research screens were built on fixtures from an assumed contract; they now read G1's answers through one mapping
layer, `web/src/lib/shapes.ts` (`Remote` takes the mapper): trends `gap_direction` → `direction`, `role_alert.kind_label`
→ `label`; defense `points_allowed_per_game_std` / `rank_std` / `points_allowed_per_game_l4` → `points_allowed_pg` /
`rank` / `points_allowed_pg_l4`, `direction` (softer / stiffer) → `trend`, `weeks_used` [1, 2, 3] → 3; players `ppg` →
`points_per_game`; receivers `games` / `points_per_game` / `snap_pct` / `form_week` → `games_played` / `ppg` /
`avg_offense_snap_pct` / `through_week`; compare `projection.*`, `season` (totals ÷ games), `last3`, `next4[0]` →
the side's `proj_points`…, `season_stats`, `form`, `opponent` / `opp_rank`. Two API additions where the screen could not
derive the number: `/api/matchups/defense?team=` returns `starters` (that roster's current starters + slot, the defense
each faces from `dim_game`; none set on Sleeper → the lineup My week proposes, which also fills `/api/matchups/cb`'s
`is_starter` for the Test League) and compare's `season` carries `rushing_tds` / `receiving_tds` (the screen's
touchdowns a game); 3 tests added (`test_matchups_defense_starters` × 3 leagues, one assert in `test_compare_route`).
The Matchups copy no longer says "one scale for every league" (G1 prices defense points in the league's scoring). The
research fixtures are now saved from the API (`web/fixtures/make_research_fixtures.py`, minus trends' `metrics` and
receivers' `context`); 6 e2e expectations follow the real numbers. Live walk on :8690 (phone 390 × 844 dark, three
leagues, + desktop 1300 × 900 once; 54 screens incl. one evaluated trade): 0 console errors, 0 failed requests, 0
"undefined" / "NaN" / "[object Object]" / "null", 0 sideways scroll. Gates: api 138 passed, web lint + build green,
fixture e2e 52 passed, ruff clean. Open: G2's live `/api/team` has no `slot_strength[].league` / `weekly[].league` and
`/api/waivers` no `positions` (G4's fixtures add them as "requested"), so live the Team Hub shows no league rank /
average beside each slot and week (Waivers' tabs fall back correctly); `api/README.md` does not yet list `team=` /
`starters` on `/api/matchups/defense`.

### G1 2026-10-02 — the research, on demand (branch `dev/G1`, clone `league_lab_g1`)

**What.** Seven routes in `api/league_lab_api/research.py` (routes block `# ---- G1 research` in `main.py`), pure
helpers in `src/league_lab/research.py`, tests `api/tests/test_research.py` (24), the JSON in `api/README.md`
§ Research (G1): `/api/trends`, `/api/matchups/defense`, `/api/matchups/cb`, `/api/players`, `/api/receivers`,
`/api/compare`, `/api/player/{gsis}/games`. `anyleague.py`, `player.py`, `ondemand.py`, `applib.py`, `app/` unchanged
(read / imported only: `anyleague.price_week` / `league_scoring` / `team_names` / `check_id`, `player.SCHED_SQL`,
`ondemand.PlayerContext` / `ros_card`; `app/lib/matchups.py` loaded unchanged for the cornerback and comparison
sentences, `signals.py` for the role alerts).

**Design.**
* One frame per league-season: every `fct_player_game` row with `points` / `points_expected` in the league's scoring
  (`research.league_games`) — `fct_player_game_league` for a house league; for any other league the stat columns
  priced with `scoring.compute_points` (position passed; `research.price_games`) and cached 10 minutes per scoring.
* Everything a screen derives from per-game points is the same arithmetic over that frame, each a Python twin of its
  dbt model: `season_table` (`mart_league_player_season`, numeric rounding reproduced in integer cents),
  `trend_windows` (`mart_player_trends`' points / expected-points windows), `defense_allowed`
  (`mart_defense_vs_position_current` + `mart_defense_trends`).
* Expected points on demand: a house league's `points_expected` + the scoring difference on the 7 expected stats the
  published mart carries (`price_expected`); exact when the leagues agree on interceptions / fumbles / 2-pt tries
  (`expected_reference` picks such a league: the Test League → Scrubs, exact).
* Reference-scored mart fields are renamed `<column>_ref`; the league's own number takes the plain name next to it.
* Rostered-by: `mart_player_availability` (house) or Sleeper's rosters through `player_id_map` (`ondemand.ros`'s rule).

**Evidence.**
* `cd api && uv run pytest -q`: **105 passed, 2 skipped** (81 + 2 skipped before; the 2 skips are F3's NFL-wide-table
  tests, which need `f1_tables.sql` in the clone). `uv run ruff check src tests app api/league_lab_api api/tests`: clean.
* Pricing parity (the acceptance), every game, on demand (`source=sleeper`, the Sleeper fixtures' scoring) vs the house
  path (the league marts): dynasty and Scrubs × 2024 / 2025 / 2026 = 18,961 / 19,400 / 2,291 games each — max |points|
  **0.0000**, max |expected points| **0.0000**; the season table (1,996 / 2,019 / 1,311 players, every
  `mart_league_player_season` column) max diff **0.0000**; points allowed 2026 (160 defense × position rows) max diff
  0.0000, 0 rank differences. Against the marts with independent SQL: `price_games` = `fct_player_game_league.points`
  on every 2025 and 2026 row (test); `season_table` = `mart_league_player_season` (2025, every column, both leagues);
  for the reference league `trend_windows` = `mart_player_trend_tags` (596 players 2025, ≤ 0.0001) and
  `defense_allowed` = `mart_defense_trends` (160 rows, every direction) and `mart_defense_vs_position_current` (exact).
* Hand-checked per route (both house leagues): trends' `ppg` / `xppg` / `gap` = `mart_league_player_season`,
  `points_l3_ref` / `momentum` = `mart_player_trend_tags`; defense's league points allowed = a hand `avg(sum(points))`
  over `fct_player_game_league`, `_ref` = the mart; cb rows = the roster's WR / TE in `mart_cb_matchups`, `proj_points` =
  `mart_player_week_projections`; players' `points` / `ppg` = `mart_league_player_season`, `_ref` and stats =
  `mart_player_season`, paging / sort / search; receivers' target share = Σ targets / Σ team targets and league points
  per game = `fct_player_game_league`; compare's projection and rest of season = `/api/player`'s; games' `points` /
  `expected_points` = `fct_player_game_league` per game. Test League: every route 200, `source: sleeper`, a receiver's
  points = the Scrubs points + 0.5 a catch (full vs half PPR) on every 2025 game. Errors: 404 (bad id, a league Sleeper
  lacks, an unknown player, a bad position, a team not in the league), 400 (bad sort / view / weeks), 502 (Sleeper down,
  unknown league; a house league still answers).
* Expected points priced from the other house league (the approximation when no league matches): dynasty from Scrubs,
  2025 REG, 5,283 games: QBs off by 0.60 a game on average (max 2.03: the −2 vs −1 interception weight × expected
  interceptions), 0.3% of the other rows off by more than 0.01.
* Latency (ms, cold = every cache emptied incl. the Sleeper client / warm; TestClient; load average 5–7 on two shared
  cores, so cold numbers are pessimistic):

  | route | dynasty | Scrubs | Test League (on demand) |
  |---|---|---|---|
  | `/api/trends` | 385 / 65 | 194 / 43 | 349 / 74 |
  | `/api/matchups/defense` | 386 / 33 | 256 / 33 | 658 / 49 |
  | `/api/matchups/cb?team=` | 140 / 90 | 92 / 51 | 311 / 102 |
  | `/api/players` (2026) | 83 / 26 | 55 / 20 | 428 / 46 |
  | `/api/players?season=2025` | 76 / 24 | 61 / 20 | 1,704 / 42 (pricing a full season) |
  | `/api/receivers` | 125 / 58 | 103 / 53 | 254 / 163 |
  | `/api/compare` | 355 / 36 | 335 / 42 | 4,106 / 404 (the on-demand card's rest of season: 14 weeks priced) |
  | `/api/player/{gsis}/games` | 40 / 15 | 31 / 14 | 80 / 43 |

**Decisions for the PO.**
* `/api/trends` names the gap fields as the contract does (`ppg`, `xppg`, `gap`, `gap_direction`) rather than
  `expected_per_game` / `diff_per_game`; `/api/players` keeps `mart_league_player_season`'s names (`points`, `ppg`,
  `expected_per_game`, `diff_per_game`, `position_rank_ppg`).
* `season` at the top of a response is the season of its rows (`season=`); the league's own is `league_season`.
* `team` / `position` keep the mart's value when the row has one (the season's team), `dim_player`'s otherwise.
* `/api/matchups/cb`'s `is_starter` is Sleeper's current lineup (`is_current_starter` / the roster's `starters`), not the
  proposed lineup the Streamlit page prefers: it only orders the list and picks the summary lines.
* Errors: a parameter the route cannot use answers **400** `{"error"}` (new; the contract lists 404 / 502 / 503).
* The heatmap rows cover the positions the league starts among QB, RB, WR, TE, K (no DEF rows: the mart has none).
* `metrics` on a trends row: the moved metrics (up / down), every metric while he has fewer than four games
  (the early read), `metrics=all` always; points metrics are flagged `ref_scored`.
* Not re-priced (reference scoring, `_ref`): `mart_player_trends`' `points` / `expected_points` metric rows,
  `expected_points_z`, `mart_defense_position_profile`'s point fields and the ranks on them (`rank_points_ref`,
  `rank_adjusted_ref`; the comparison verdict reads them, as the page does), `mart_player_recent_form`'s
  `points_per_game_std_ref`.

**Open.** Real Sleeper (fixtures only here); a hosted copy keeps 3 seasons of `fct_player_game` (older `season=`
answers empty); every relation the routes read is one an `app/` page names, so `sync_to_hosted.sh` publishes it.

### G2 2026-10-02 — the decisions, on demand (`/api/waivers`, `/api/trades/evaluate`, `/api/trades/partners`, `/api/team`, `/api/league`)

* **What**: `api/league_lab_api/decisions.py` + the routes block `# ---- G2 decisions` in `main.py` (contract: the Wave G
  brief; `api/README.md` § "Decisions (G2)"). A house league is served from its marts (the numbers the Streamlit pages
  show); any other Sleeper league — or `source=sleeper` for a house league — is computed on request with the nightly's
  own engines. New on-demand entry points: `anyleague.league_weeks` (every roster × the horizon on ONE `LineupInputs`,
  `lineup.build`; the whole week's board priced into it, so a free agent is valued by `lineup._proposed_player` exactly
  as B1 values him), `anyleague.horizon_frame` (`mart_league_roster_horizon`'s columns and rules: top at slot type, the
  replacement matched to the cent), `anyleague.free_agents` (Sleeper's directory − every roster, `player_id_map`, the
  nightly's filter: active NFL roster, not Out / IR, a started position; NFL status from the marts' NFL-wide columns,
  else the directory's); `waivers.sweep_roster` (the per-roster step of `load_and_sweep`, extracted unchanged: the
  nightly calls it too); `trades.partners(want=)` (None = unchanged); `Sleeper.season_matchups` / `Sleeper.transactions`
  (cached an hour). Words: the Waiver Wire's `_headline` / `_card` / `_why` and the Trade Finder's `size_words` /
  `closest` / `lineup_frame` are compiled from the page files (`decisions.page_functions`: the named `def`s only, via
  `ast`); Team Hub / League first lines quoted (marked); `trades.verdict` / `fit_line` / `fairness_line`,
  `app/lib/ros.py` called directly.
* **Parity (clone `league_lab_g2`, week 4, as_of = the nightly's)** — `api/tests/test_decisions.py`, 28 tests:
  * Waivers on demand vs `mart_waiver_moves`, **every row**: Scrubs 2 433 / 433 moves, Scrubs 5 393 / 393, dynasty 2
    24 / 24, dynasty 1 14 / 14 (script), dynasty 12 the one "nothing" row; max gap 0.00 on weekly / horizon gain, lineup
    before / after, add value, drop value, drop / add rest-of-season points, drop horizon loss; 0 differences in move
    rank, add rank, best drop, list, seat, displaced starter, no-evidence flag, open spots (K and DEF free agents
    included: Scrubs' top claim is the Giants DEF). The extraction left the nightly identical: `load_and_sweep` re-run
    on Scrubs 2 / 5 and dynasty 12 = `ops.waiver_moves` row for row; root `tests/test_waivers.py`, `test_trades.py`,
    `test_roster_value.py`, `test_lineup.py`, `test_trade_finder_page.py`: 510 passed.
  * Trade Finder (dynasty 12 and Scrubs 2 each give their best unlocked starter to roster 1 for roster 1's): before /
    after per week, depth, fit this week / next 4, verdict and the fit sentence = the page's calls (`RosterBoard` on
    `mart_league_roster_horizon`, `MARKET_SQL`, `REPLACEMENT_SQL`, `trades.evaluate`) to 0.01, on the house path and on
    demand; market exact on the house path, ± 1 whole point allowed on demand (dynasty: identical). Example (dynasty 12, the
    partner finder's best: Bo Nix + Isaiah Likely for Breece Hall): you 111.15 → 114.74 this week, 446.96 → 469.02
    over weeks 4–7; them +5.63 / +21.97; market 228 out / 112 in — identical on both paths. Partners: the same
    packages and gains on both paths.
  * Team: `mart_league_roster_value` (lineup 111.15 / bench 79.83 / horizon 446.96 for dynasty 12), every roster's
    three ranks (`_rankings`), `_slot_strength` (top player, strength, replacement) and this week's `_horizon` rows,
    house and on demand, to 0.01.
  * League: `mart_league_standings` (W-L-T, standing, PF / PA / avg / sd / best / worst, lineup efficiency),
    `mart_league_all_play` (all-play wins, rank, win %, expected wins, luck, top-half weeks), `_all_play_week` and
    `mart_league_transactions` (Scrubs: every transaction × action × player × roster × status × bid), house and from
    Sleeper's weeks 1–2 + rounds 1–3 (fixtures from `raw.sleeper_*`: `api/tests/fixtures/make_g2_fixtures.py`).
  * Test League (fictional, 10 teams, K and DEF): every route answers (team 3: moves or "nothing", partners, a trade,
    the hub with 10 ranked rosters, standings from hand-made weeks 1–2, 20 transactions incl. a trade and a failed
    claim). Roster 1 of the Test League is over the roster limit in the F3 fixture, so its waivers say "no single claim
    is legal" (the engine's rule) — the tests use team 3.
* **Latency** (TestClient, this sandbox, four devs on two cores; cold = every cache emptied incl. the priced board):
  | Route | dynasty 12 (marts) | Scrubs 2 (marts) | dynasty 12 on demand | Scrubs 2 on demand | Test League 3 |
  |---|---|---|---|---|---|
  | waivers | 140 / 24 ms | 229 / 73 | 3,600 / 32 | 5,459 / 83 | 2,345 / 31 |
  | partners | 959 / 12 | 1,245 / 36 | 4,868 / 17 | 3,993 / 12 | 2,759 / 15 |
  | evaluate | 174 / 82 | 317 / 83 | 4,117 / 132 | 3,839 / 73 | 2,425 / 21 |
  | team | 226 / 51 | 443 / 92 | 1,368 / 28 | 985 / 20 | 873 / 23 |
  | league | 116 / 26 | 293 / 116 | 131 / 93 | 83 / 59 | 94 / 77 |
  Cold on demand is the board priced for 15 weeks (rest of season and the market, ~0.7–1.5 s), every roster solved for
  4 weeks (0.1–0.2 s), the waiver sweep (0.3 s for 381 free agents, 121 past the bar) and the partner search (~1 s);
  warm answers come from 2-minute caches (10 minutes on a house league, like the page's `st.cache_data`).
* **Checks**: `cd api && uv run pytest -q` 109 passed, 2 skipped (83 before + 28 new: 111 collected); `uv run ruff check
  src tests app api/league_lab_api api/tests` clean.
* **Deviations (decisions for the PO)**: (1) `waivers.load_and_sweep`'s per-roster block moved into `sweep_roster`
  (same code; the nightly's numbers re-checked row for row) so the on-demand path IS the nightly's rule, not a copy.
  (2) `moves` lists one row per free agent (his best drop, the page's list); every drop of a free agent is not served
  (an `all=1` is easy if G4 needs it). (3) The house free-agent list reads `mart_player_availability` (the page's
  browse population, Out / IR / NFL IR hidden); on demand it is the directory filter above. (4) Not on demand (they
  need the league's history in the database): keeper / acquisition facts on `/api/team`, manager profiles, the draft
  and the roster-rankings table on `/api/league` (`not_on_demand` says so; the rankings are on `/api/team`).
  (5) `players_nfl.json` grew by the 530 free agents of the house leagues (210 KB) so the directory-minus-rosters rule
  is testable; weeks 1–2 matchups and rounds 1–3 transactions added for all three leagues (no user ids, no notes).
  (6) The Team Hub's and League's first-line sentences are quoted, not captured (top-level page code).
* **Not verified / open**: no Sleeper from the sandbox (the live `/transactions/{round}` and played-week calls are
  untested against the real host; the fixture shapes are Sleeper's as archived in `raw.sleeper_*`). The on-demand
  market prices every week from the NFL-wide board (identical to `ops.projections` on this copy). Commands for Andrew
  (Mac): `cd api && uv run pytest -q`; `uv run uvicorn league_lab_api.main:app --port 8581`, then
  `/api/waivers?league=<id>&team=<roster>`, `/api/team?…`, `/api/league?…`, `/api/trades/partners?…` and
  `curl -X POST localhost:8581/api/trades/evaluate -H 'content-type: application/json' -d '{"league": "<id>", "team": 2,
  "partner": 1, "give": ["<sleeper id>"], "get": ["<sleeper id>"]}'` (with the beta cookie when the gate is on).

### G4 2026-10-02 — the decision screens: Waivers, Trade Finder, Team Hub, League (branch `dev/G4`)

**What.** Four screens under the Decisions tab of the web app, on G2's routes and in G3's design system (merged
`dev/G3` once at the 45-minute mark: `api.ts` had both teams' appended blocks in conflict, both kept): **Waivers**
(`/waivers`: the top claim's sentence first, tiles, the moves as cards with week-by-week gain bars and the drop, the
free agents by position with this week's projection and its range on one track, list + player card at 1300 px),
**Trade Finder** (`/trades`: the best partner first with "Try this trade"; partner select and both rosters as tick
lists; the package POSTed as soon as both sides have a player: verdict, fit tiles, market and rest-of-season bars,
league rank and roster-size lines, both lineups after the trade; the partner finder by position; the package is the
URL), **Team** (`/team`: the answer, value / next 4 weeks / depth / record tiles with ranks, strength by slot vs the
league as bars with the league average as the tick, the next four weeks vs the league's middle, every roster's lineup
value, the roster as player rows), **League** (`/league`: luck first, standings with all-play, who has been lucky as
diverging bars, bench points, the weekly scoring rank grid, the latest moves, the draft). Each screen is its own chunk
(`web/src/lib/decisionPages.ts`). `web/README.md` § "The decision screens".

**Contract.** G2 committed its routes during the round (`1d618ba`), so the screens read G2's real shapes and the
fixtures are **saved from G2's API** run from a scratch export of `dev/G2` on the G4 clone (`web/fixtures/
save_decision_fixtures.py`; the Test League on G2's on-demand path with its Sleeper fixtures, team names mapped to the
web fixtures'). Requested of G2 (added by the saver from G2's own answers): `/api/team` `slot_strength[].league`,
`weekly[].league`; `/api/waivers` `positions`; the league name on `/api/league`.

**Evidence.** `npm run lint` clean (eslint + svelte-check 0 / 0 + tsc); `npm run build` (main chunk 22 KB gzip;
Waivers 6.9, Trades 7.9, Team 4.6, League 5.8 KB gzip, loaded on first use). Fixture e2e
(`e2e/decisions/fixtures.spec.ts`, 18 tests: 4 screens × light / dark × 390 × 844 / 1300 × 900 + the Decisions tab):
18 passed; every number checked is read from the fixture served (waiver gains, lineup values, ranks, slot bars,
luck, verdicts, fit / market / rest-of-season, POST body = the package). With F2's and G3's specs: 50 passed, 2 failed
— G3's "the decisions tabs say what is coming" expects the `Coming` placeholder that G4 replaces (one line for the PO:
`getByTestId("coming")` → `getByTestId("waivers")`). Answer visible after a cold open on fixtures (median of 5):
phone 198–335 ms, desktop 218–301 ms. Screenshots `g4_<screen>_<league>_<phone|desktop>_<light|dark>.png` (40).

**Open.** Buy-low / sell-high lists and the upside-stash cards (not in G2's contract); the keeper / acquisition table
(G2 sends `keeper.rows`; the screen shows the acquisition line and each starter's "acquired"); the Test League's
fixture rosters differ between G2's Sleeper fixtures and F2's web fixtures (names mapped, rosters not); G3's
placeholder test above.

### G3 2026-10-02 — the design system and the research screens (web)

* **What**: a design system (`docs/DESIGN.md`): `web/src/app.css` tokens (dark first, light from the system; surfaces,
  ink, accent, deltas, chart roles, a type scale with 11 px uppercase labels and 36 / 48 px numbers, radii, a 900 px
  `wide` breakpoint), `web/src/lib/theme.ts` (all 32 teams' primary + accent in nflverse codes, position colors from the
  dataviz palette's slots, `seqFill`, `fmt`), a hand-rolled chart kit (`lib/chart.ts` + LineChart, Heatmap, Sparkline,
  Bar, Meter: inline SVG, ~1 KB, tokens only), and the components TopBar (one bar for every league screen: the picker +
  My week · Rest of season · Research · Decisions · About, a bottom bar on a phone), Card, PlayerCard, PlayerRow,
  Headshot (silhouette fallback), PosBadge, TeamBadge, StatTile, Table (columns past three show from 640 px), ListDetail,
  Tabs, Chips, ScreenHead, Coming, GameLog. The tokens + core components were committed at minute 11 (`4251a09`) for
  G4's merge.
* **Screens**: new Trends (over / under: the gap as a diverging bar per player, due / running hot cards, list + detail
  with the game log), Matchups (your starters' ranks, the defense-vs-position heatmap with your cells ringed, the
  cornerbacks with `cb_line` and the side bar), Players (sortable, headshots, search / position / NFL team / whose),
  Receivers (role bars against the top-12 yardstick, the recent share), Compare (opens on My Week's closest call;
  paired bars; the next 4 weeks); the player card gets a PlayerCard header and **Points by week** (points vs expected,
  2026 / 2025); "Our record" became **About the numbers** (`/about`, `/record` still opens it): the Rankings page's
  "The model" words in six cards, then the record. My Week, Rest of season and Leagues restyled; Decisions' four tabs
  show a "coming" card for G4's screens. Research screens and About are lazy chunks (4–6 KB gzipped each).
* **Contract (G1)**: `web/src/lib/api.ts` `// ---- G3` block = the shapes the screens read; fixtures built from the
  clone's marts by `web/fixtures/make_research_fixtures.py` for dynasty 12, Scrubs 2 and the Test League (Scrubs'
  numbers, its own owners). **Requests to G1 / the PO**: `/api/matchups/defense?team=` adds `starters` (the team's
  starters and the defense each faces: the heatmap's rings and the answer); `/api/trends` rows carry `ppg`, `xppg`,
  `gap`, `direction` ("over" / "under" / "even", ±0.5) and `role_alert` with `label` (`kind_label`); `/api/matchups/cb`
  rows carry `line` (`cb_line`), `lean` (`lean_text`), `is_starter`, the week's `proj_points` / `p25` / `p75`;
  `/api/compare` sides: `season_stats`, `form`, `usage`, `ros`, `next4` (the same keys on both sides);
  `/api/receivers` adds `yardsticks` {WR, TE}; `/api/player/{gsis}` adds `headshot_url`. The screens ask
  `/api/trends?view=all&limit=200`, `/api/players?…&limit=500` and filter / sort on the phone.
* **Evidence**: `npm run lint` 0 errors 0 warnings; `npm run build` (first screen ≈ 45 KB gzipped JS + 6.7 KB CSS);
  `npm run e2e:fixtures` **34 passed** (Wave F's 7 tests updated for the About tab + 10 new, each on the phone 390 × 844
  and desktop 1300 × 900: Trends, Matchups, Players, Receivers, Compare, the Test League's research, headshots,
  the bars, and every screen in light and in dark with no sideways scroll); `npm run measure:fixtures` My Week first
  content 102 / 95 ms phone, 100 / 98 desktop (Test League), 98 / 89, 120 / 120 (dynasty) — limit 500; research
  screens on fixtures (scratch measurement, median of 5 cold): Trends 168 / 160, Matchups 130 / 135, Players 150 / 180,
  Receivers 126 / 133, Compare 122 / 106, player card 84 / 83, About 94 / 96 ms (phone / desktop). Same numbers:
  Compare's 8.7 / 8.2 = My Week's card (8.68 vs 8.22); the player card's 18.1 = the lineup's 18.13; Trends' gap =
  `mart_player_availability.diff_per_game`.
* **Not verified**: real headshots (the sandbox cannot reach static.www.nfl.com; tests abort them, so every screenshot
  shows the silhouette); the screens against G1's real API (fixtures only); an iPhone's SF Pro (screenshots are DejaVu,
  wider). Open: "What it leans on most" (feature importance) is not on About (no route); route participation / TPRR
  read 0 for 2026 in the mart and are hidden until filled in.


## Wave H (Iteration 16)

### PO merge — Wave H, 2026-10-02

* **Delivered** (three Opus devs, 30–40 min each): H0 the deploy kit (`render.yaml`, the Dockerfile proven stage by stage
  and fixed — `app/pages` was missing from the image and broke `/api/waivers` and trades; `$PORT`; `nobody`; 260 MB python
  stage; `.github/workflows/image.yml` builds, starts and checks the image and pushes it to GHCR; `scripts/smoke.sh`;
  `docs/DEPLOY.md` as Andrew's walk-through: Render Starter, $7/month, Ohio next to Neon); H1 the gaps (upside stash and
  buy-low / sell-high on Waivers, `/api/about` with "what it leans on most" and the grades, the rest-of-season board in
  one round of queries — dynasty cold 1,079 → 249 ms, `/api/search` for any league); H2 one writer (GitHub Actions
  publishes the hosted copy, the Mac's launchd no longer does unless `LEAGUE_LAB_MAC_WRITES_HOSTED=1`; `sync_to_hosted.sh`
  refuses elsewhere), the NFL-wide boards in `RECORD_TABLES` with a first-night rule that cannot stop the night, the
  relation closure derived in one place (`scripts/hosted_relations.py`: the API's 63 relations + the console's 71;
  `mart_kd_week` / `mart_kd_team_game` added), the hosted copy windowed to ~200 MB, a full nightly dry run in the sandbox
  (exit 0, 14 min).
* **PO**: the integrated API walked against a hosted-shaped copy (H2's scratch target, app role): every route 200 for
  both house leagues and the Test League, including H1's on-demand upside stash (it reads `ops.player_scenarios`, which
  is published — H2's warning about `staging.stg_sleeper__players` concerned the nightly's own functions, which the API
  does not call); `int_player_week_team` gets `analyze` after build (H2 measured 396 s of the nightly's 8-minute dbt
  build lost to a plan made before statistics existed); `docs/HANDOFF.md` says who writes now. Checks: `api` 155 passed,
  web lint 0 / 0, build, 58 fixture e2e, shellcheck + actionlint clean, root `pytest` green.
* **Andrew's path to the beta** (`docs/DEPLOY.md`): GitHub secrets present → run the nightly workflow once (publishes
  the current tables; the copy on Neon today predates the new app) → Render Blueprint with the read-only Neon URL and the
  beta password → `scripts/smoke.sh https://<address> '<password>'` → share the link. Not verified from the sandbox:
  a real `docker build`, GHCR, Render's acceptance of `autoDeployTrigger` / `buildFilter` / `region: ohio` (fallbacks in
  the doc), Render's current prices.
* **Deploy, 2026-10-02 (PO, in the browser)**: Render Blueprint `league-lab` created from `render.yaml` (Starter, Ohio,
  service `https://league-lab.onrender.com`). The first build failed in 10 s: `COPY app/pages` → "/app/pages": not found.
  Cause: `api/Dockerfile.dockerignore` (D7/E3, pre-Wave H) still existed, and BuildKit prefers `<Dockerfile>.dockerignore`
  over the root `.dockerignore` H0 kept current — the stale file never let `app/pages` through. Fix: the stale file is
  deleted; `api/tests/test_build_context.py` fails if a `<Dockerfile>.dockerignore` reappears, if a path the Dockerfile
  copies is untracked or excluded by `.dockerignore`, or if `.env` / `data/` / `dbt/` would get in. (The sandbox has no
  Docker; the two ignore files diverged unseen.)
  Second build (`d4e101e`, after GitHub's `image` workflow passed in 2 m 37 s — `autoDeployTrigger: checksPass` held
  Render until then): 1 m 04 s, Live. Checked on the server from the app's own origin (the `scripts/smoke.sh` checks
  plus Team / Waivers / ROS / Record / About / Trends / League for both house leagues): 22 of 22 ok, slowest 1.01 s
  (dynasty waivers), `/api/health` `version d4e101eb33df, as_of 2026-10-02T16:12Z, database ok`, `board_source_in_use
  nfl_wide` (Neon has the NFL-wide boards), the gate 401 without / with a wrong password, a Sleeper-username lookup live
  from Render (7 calls, 0 refused), `/api/search` 79 ms. Screens walked at 375 px: Leagues, My Week, Team, Waivers,
  Trends, About, Rest of Season — headshots, charts and numbers present. Record says "no week on the record yet"
  (right: week 4 is the first archived-before-kickoff week and is not scored until Tuesday). Writer reality: the
  GitHub nightly has never completed (secrets unset), so `LEAGUE_LAB_MAC_WRITES_HOSTED=1` is set in the Mac's `.env`
  and the Mac's 08:00 job publishes Neon; `docs/HANDOFF.md` says so. Not run: `scripts/smoke.sh` itself (neither the
  sandbox nor the Mac's shell can reach `onrender.com`; the same checks ran from the browser).
* **GitHub nightly, 2026-10-02 evening**: Andrew set the three secrets and ran the workflow by hand (#4): the secrets
  check passed, `migrate ok`, then `restore-state FAILED` — `pg_dump: error: aborting because of server version
  mismatch; server version: 18.6, pg_dump version: 17.11`. Neon is Postgres 18; `nightly.yml` installed client 17 and
  ran a `postgres:17` service. Fix: both to 18. The Mac (Homebrew 17) is unaffected: its tables are "kept", it never
  dumps from Neon in normal operation. Next: push, re-run; if green, remove `LEAGUE_LAB_MAC_WRITES_HOSTED=1` from the
  Mac's `.env` the same day (the Mac's 08:00 and Actions' 07:37 must not both publish).
  **Run #5 (`bded338`): green in 23 m 42 s** — restore-state 26 s (the record came down from Neon), nflverse history
  52 s, weather 7 m 39 s (first run, no archive), dbt-build 9 m 00 s (641 pass, 3 warn), project 3 m 58 s,
  projection-marts 10 s, sync-hosted 18 s; `verified: all 79 relations the pages and the API read are on the hosted
  copy (the API's 66 included; 202 MB)`. The beta's `/api/status` showed the new load times minutes later.
  GitHub Actions is now the writer in fact, not only by design; the Mac flag comes out of `.env` the same evening.

### H2 2026-10-02 — one writer, the record kept, the hosted relation audit (branch `dev/H2`, clone `league_lab_h2`)

* **One writer.** GitHub Actions' nightly is the only writer of the hosted copy (the beta must not depend on the Mac
  being awake). Off Actions, `nightly.sh` skips `sync-hosted` ("GitHub Actions is the one writer of the hosted copy")
  and `sync_to_hosted.sh` refuses with exit 7 before touching anything, unless `LEAGUE_LAB_MAC_WRITES_HOSTED=1` (the
  fallback while Actions is down: disable the workflow first) or the target is a local simulation
  (`LEAGUE_LAB_HOSTED_ALLOW_LOCAL=1` and a local URL). The Mac's launchd `refresh.sh` keeps building the Mac's own
  database (the research console, packs, backtests, the full history, a second archive of Sleeper's snapshots) and
  still *reads* the hosted copy in `restore-state`. Gate cases (stub runners on the real block): no URL → skip; Mac
  with URL → skip; Actions → run; Mac + flag → run; local simulation → run. `make sync-hosted` with a Neon-shaped URL
  off Actions → exit 7 (test). The workflow needs no new secret (`LEAGUE_LAB_SLEEPER_LEAGUE_ID`,
  `LEAGUE_LAB_HOSTED_ADMIN_URL`, `LEAGUE_LAB_HOSTED_APP_PASSWORD`); `fetch-projections` runs there (never offline),
  after `project`, before `save-record`. Before the freeze: the first kickoff of a week is Thursday 8:15–8:30 PM ET in
  161 of 190 regular-season weeks 2016–2026 and never earlier than 12:30 PM ET (Thanksgiving) (`dim_game`); the run
  starts 07:37 ET (06:37 in winter) — 5+ hours early.
* **The record kept.** `RECORD_TABLES` = `ops.projections`, `ops.projection_drift` + F1's `ops.projection_lines`,
  `ops.projection_ranges`, `ops.kd_lines`, `ops.kd_ranges` (still in `STATE_TABLES` too). `restore_state` now asks the
  hosted copy once which state tables it has: unreachable → a record table stops the night (as before); reachable
  but the table was never published there (the first night after a table joins the record, or a hosted copy older
  than it) → said so, then this database's rows (kept), else the archive's copy, else the record starts that night
  with a warning — instead of stopping every night. A failed archive restore now fails the step (before, `run_step`'s
  `||` context swallowed it). Isolated runs of the real functions (`harness.sh` in the hand-back), fresh migrated
  database:

  | case | hosted copy | archive | result |
  |---|---|---|---|
  | A | `league_lab_hosted` (no F1 tables, no `feature_experiments`) | none | 11 tables restored; the 4 F1 tables "not on the hosted copy (never published there)" → "no copy in the archive" warning; **returned 0** (the pre-H2 function with the same RECORD_TABLES: **returned 1**, `relation "ops.projection_lines" does not exist`) |
  | B | same | `save_record` of the clone | the 4 F1 tables restored from the archive: 9,911 / 49,555 / 1,088 / 5,440 rows; 0 |
  | C | unreachable (port 5999) | none | stops at `ops.projections`: "refusing to refit every played week blind"; 1 |
  | D | `league_lab_hosted_h2` | none | all 16 tables restored; the record tables content-equal to the source (jsonb md5; column order differs from a fresh migrate); 0 |
  | E | `league_lab_hosted` | — (clone with rows) | the 4 F1 tables "N rows here, kept (the hosted copy does not have this table yet: the next sync publishes it)"; 0 |

  `save_record` writes the 6 tables in 1.8 s: 1.9 MB + 4 KB + 564 KB + 2.3 MB + 148 KB + 84 KB gzipped (~5 MB in the
  Actions cache). Not carried: `raw.sleeper_projections` — the hosted copy never holds `raw`, and its durable copy is
  the archive itself (one file per snapshot, replayed nightly); a dump next to it would sit in the same cache.
* **The hosted relation audit.** The closure is derived in one place, `scripts/hosted_relations.py`: readers = the
  console (`app/`, `reports.py`) and the API (`api/league_lab_api/*.py`, the `app/lib` modules and page functions it
  loads, every `src/league_lab` module it imports, followed import by import — `anyleague`, `research`, `decisions`,
  `sleeper_client`, `waivers`, `trades`, `lineup`, `roster_value`, `kdef`, `scoring`, `config`; the walk stops at the
  model fit and loaders); names = `analytics.` / `analytics_seeds.` / `ops.<x>` plus bare names in
  `missing_relations` / `require_relations`. Against `league_lab`: the API reads **63 relations** (50 analytics +
  `analytics_seeds.reference_scorings` + 12 ops); the console 71. Added to the closure by the API side: **`mart_kd_week`,
  `mart_kd_team_game`** (4.5 MB; named by `lineup.py`); every other relation the API reads was already published
  (the sandbox's `league_lab_hosted` predates `mart_player_role_alerts`, `mart_player_ros_projection`,
  `mart_projection_record` and F1's tables; a sync today publishes them). The window now also covers
  **`fct_player_game_league`** (52 MB in full; the API joins it to the windowed `fct_player_game`, Matchups reads last
  season on) and **`mart_player_week_features`** (68 MB; read for the current season only). Left out of `ops`:
  `ops.player_prior_oof` / `_oof_pred` (E4's harness; absent on the PO's copy, read by no one). After the restore the
  sync fails (exit 5) if any relation a reader names is missing. `src/league_lab/signals.py` (in the brief's list) is
  the nightly's writer; the API reads its output through `ops` and `app/lib/signals.py`.
  Sync of `league_lab` into `league_lab_hosted_h2`: **198.5 MB estimated → 200 MB database** (101.6 MB windowed + 98.3
  MB in full; `ops` 30 MB), restore 4 s, `verified: all 79 relations the pages and the API read are on the hosted copy
  (the API's 63 included …)`. Budget: warns above 440 MB, **refuses above 480 MB** before touching the hosted copy
  (`LEAGUE_LAB_HOSTED_MAX_MB`, exit 6; with the budget set to 100 MB: exit 6, the target's 80 tables / 202 MB
  unchanged, no `hosted_slim` left behind). Every GET route against it in-process (TestClient, the app role, Sleeper
  fixtures; Scrubs 2, dynasty 12, Test League 3; 16 routes each): **47 × 200, 0 × 5xx, 0 "not built"**; the one 404 is
  `/api/search` for the Test League (H1's row).
* **Dry run** (`NIGHTLY_SLEEPER_OFFLINE=1 NIGHTLY_WEATHER_OFFLINE=1`, clone `league_lab_h2` of `league_lab` with
  `raw.nfl_pbp`, `raw.nfl_pbp_participation`, `analytics.bridge_play_participation`, `intermediate.int_play_context_long`
  dropped, a scratch copy of the archive, hosted target `league_lab_hosted_h2`; env overrides instead of editing `.env`):
  **exit 0, 13 m 57 s**. migrate 2 s · restore-state 1 s (16 kept) · replay-sleeper 3 s · replay-nflverse-history 2 s ·
  replay-nflverse-current 2 s · replay-weather / replay-projections skipped (no archive) · fetch-sleeper skipped
  (offline) · fetch-nflverse-current 12 s (live) · fetch-weather skipped · **dbt-build 8 m 41 s** (`PASS=610 WARN=3
  ERROR=0`) · backtests 1 s (kept) · **project 4 m 23 s** · fetch-projections skipped (offline) · save-record 1 s ·
  projection-marts 13 s (`PASS=139`) · drift 0 s (26 rows written by `project`) · backup skipped · **sync-hosted 14 s**
  (211.2 MB estimated, 206 MB database, `verified: all 79 …`). Skipped models for the dropped tables, through the new
  `NIGHTLY_DBT_EXCLUDE` (sandbox only): `source:raw.nfl_pbp source:raw.nfl_pbp_participation stg_nflverse__pbp+1
  stg_nflverse__pbp_participation+1 bridge_play_participation+1 int_play_context_long+1` = 11 models (the two pbp
  staging views, `fct_play`, `bridge_play_participation`, `int_play_context_long`, `int_player_game_pbp`,
  `int_team_game_pbp`, `int_target_participation`, `int_defender_game_coverage_snaps`, `mart_coverage`,
  `mart_player_context`) + the two source tests; their tables stay as cloned. The record through the night: frozen
  rows (`frozen_source` not null) md5-identical in `league_lab`, the clone after the night and the published copy —
  `ops.projections` 4,780 (1,226 kickoff), `projection_lines` 2,358 (581), `projection_ranges` 11,790 (1,162),
  `kd_lines` 256, `kd_ranges` 1,280.
* **Found (PO, dbt)**: `int_player_week_universe` took **396 s** of the 8 m 41 s build — planned right after
  `int_player_week_team` was rebuilt, before autovacuum analysed it (autoanalyze 17:00:56 UTC, the query started
  ~17:00:28); EXPLAIN with statistics is a cheap hash join. A fresh database in Actions has the same order. An
  `analyze {{ this }}` post-hook on `int_player_week_team` (the universe model has one for itself) should take ~6
  minutes off every night.
* **Checks**: shellcheck clean on `nightly.sh`, `refresh.sh`, `sync_to_hosted.sh`; actionlint clean on `nightly.yml`;
  `tests/test_nightly_relations.py` 6 passed (record ⊆ state, the API's readers follow its imports, every relation a
  route reads is named, `OPS_EXCLUDE` read by no one, the sync's exit 7 off Actions ×2); ruff clean.
* **Open**: the live Sleeper and Open-Meteo steps and the Neon restore (no network here); the Mac's launchd behaviour
  (no Mac) — the gate is the same block; `docs/HANDOFF.md` lines 13–14, 84, 135 still say the Mac syncs (PO's file).

### H0 2026-10-02 — the deploy kit (branch `dev/H0`)

Plan row H0: everything Andrew needs to put the API + the web app on a server, written for him to do himself.

**Files.** New: `render.yaml`, `.github/workflows/image.yml`, `scripts/smoke.sh`, `docs/DEPLOY.md`, `.dockerignore`,
`api/tests/test_h0.py`. Changed: `api/Dockerfile`, `api/league_lab_api/main.py` (block `# ---- H0 health`),
`api/README.md` § Deploy (rewritten short, points at DEPLOY.md), `api/tests/test_f3.py` (one assertion pinned the old
`{"ok": true}` health body), this section, `CHANGELOG.md`.

**Design.** Render builds `api/Dockerfile` from the repository (Blueprint `runtime: docker`, root context, Starter
$7/month, region `ohio` = Neon's us-east-2, one instance, health check `/api/health`, `autoDeployTrigger: checksPass`,
`buildFilter` = what the image holds). The GitHub workflow builds the same image on every such push to `main`, starts
it once (health without a database, the app's page, user `nobody`, the cache writable and the code not) and pushes
`ghcr.io/<owner>/league-lab:<sha>` + `:main`; Render waits for that green check, so a Dockerfile that does not build
never reaches the server. Chosen over Render pulling the GHCR image because it needs no registry token and no deploy
hook secret (two fewer things for Andrew to create); the switch is five documented steps and the workflow already
calls `RENDER_DEPLOY_HOOK_URL` when that secret exists. No Render disk: the server writes only Sleeper's ~15 MB player
directory (a day), and a disk costs money, needs a root-owned mount the `nobody` user cannot write, and turns off
zero-downtime deploys; a redeploy costs one Sleeper call.

**The image, proven without a Docker daemon** (each stage's commands run in
`scratchpad/waveH/h0/img/`, the context = the tracked files the `.dockerignore` whitelist lets through):

* Node stage: `npm ci --no-audit --no-fund` (175 packages, 3 s) + `npm run build` (vite 8.3.2, 21 assets, 404 KB
  `dist`) on a copy of `web/`'s tracked files — green.
* Python stage: `uv sync --frozen --no-dev --no-install-project` (uv 0.8.17 = the image's pinned
  `ghcr.io/astral-sh/uv:0.8.17`, CPython 3.13, `UV_COMPILE_BYTECODE=1`) on `api/pyproject.toml` + `uv.lock`: 12 s,
  no pytest / ruff / httpx in the `.venv`; the packages' own `tests` directories removed (−86 MB: `.venv` 344 → 260 MB).
* Final stage, laid out as the `COPY` lines say (`/srv/api/.venv`, `/srv/api/league_lab_api`, `/srv/app/lib`,
  `/srv/app/pages`, `/srv/src/league_lab`, `/srv/web/dist`, `compileall`, `/srv/cache` owned by `nobody`), started
  with the image's exact `CMD` under `env -i` (only the image's `ENV` + `render.yaml`'s values) as uid `nobody`
  (`setpriv`), `PORT=8701`: listens on 8701 (`$PORT` honoured; 8080 without it); `/api/health` answers; the cache
  directory is writable by `nobody` and the code is not (`PermissionError`).
* **Fixed — `app/pages` was not in the image**: `decisions.page_functions` reads `app/pages/2_Waiver_Wire.py` and
  `6_Trade_Finder.py` at run time. With the old `COPY` lines: `/api/waivers` (Scrubs 2) **500** and
  `POST /api/trades/evaluate` **500** (`FileNotFoundError`); with `COPY app/pages`: 200 / 200.
* Also changed: the default port 8000 → 8080 (`EXPOSE 8080`), uv and its cache no longer in the final image (a
  separate `py` stage), `PYTHONDONTWRITEBYTECODE=1` + the code compiled at build time (`nobody` cannot write
  `__pycache__`), `ARG LEAGUE_LAB_VERSION` → `/api/health`'s version, `chown nobody:nogroup`.
* Not run: `docker build` itself (no daemon). The workflow's first run on GitHub is the first real build; its "Start the
  image once" step checks what is proven here.

**`/api/health`** (marked block in `main.py`): `{"ok": true, "version", "as_of": max(ops.projections.fitted_at),
"board_source", "database": "ok" | "unreachable: <class>"}`, no password, `Cache-Control: no-store`, always 200 while
the process runs (a host restart would not fix a database); `as_of` read on its own 5-second connection at most once
an hour (once a minute while failing), one refresh at a time, so Render's frequent checks neither keep Neon's compute
awake nor wait on the pool. `version`: `LEAGUE_LAB_VERSION`, else `RENDER_GIT_COMMIT`, else `git rev-parse`, else `dev`.
`api/tests/test_h0.py` (3 tests): the body against independent SQL, the Render fallback, gate on + database down.

**The API run against the hosted copy** (`league_lab_hosted`, read-only role, the Test League from fixtures, port
8701, the image layout above). Every route the web app calls (`web/src/lib`'s query strings: 19 per league for
dynasty 12, Scrubs 2, Test League 3, + session / health / status / leagues / username / `/` / an app route = 64):

| Database | Routes 2xx | Failures |
|---|---|---|
| `league_lab` (the full copy) | 63 / 64 | `/api/search` for the Test League: 404 "no current-season league" (search is house-only; H1's row) |
| `league_lab_hosted` (as published) | 36 / 64 | 21 × 500, 6 × 503, the 404 above |
| a scratch clone of it + the relations below (`league_lab_hosted_h0`, dropped afterwards) | 63 / 64 | the 404 above; no SQL error left in the Postgres log |

**Missing from the hosted copy** (for H2 — the sync script's closure; each was found by the route walk and the server
log, then confirmed by adding it to the clone):

* Route-breaking:
  * `analytics.mart_player_ros_projection` (table) — 503 on `/api/ros` and `/api/waivers` for both house leagues.
  * Stale shape, the relation is there: `ops.projections` lacks `p25`, `p75`; `analytics.mart_player_week_projections`
    lacks `p25`, `p75`, `actual_inside_50` — **500** on `/api/my-week`, `/api/player/{gsis}`, `/api/matchups/defense`,
    `/api/matchups/cb`, `/api/compare` for all three leagues, and on `/api/ros`, `/api/waivers`,
    `/api/trades/evaluate`, `/api/trades/partners`, `/api/team` for the Test League (the borrowed board reads
    `ops.projections`). A sync of a current build carries these (the sync copies whole tables): run the nightly once
    before the deploy (DEPLOY.md "Before you start"). Same staleness, no route of today failing (H1's `/api/about` reads
    the grades): `analytics.mart_projection_backtest` (`coverage_50`, `interval_score`, `interval_width_50`,
    `is_current`), `ops.projection_backtest` (`coverage_50`, `interval_width_50`, `pinball_25`, `pinball_75`),
    `analytics.mart_player_week_features` (10 `pn_*` columns).
* Silent (200, a weaker answer; the error is caught):
  * `ops.projection_lines`, `ops.projection_ranges`, `ops.kd_lines`, `ops.kd_ranges`,
    `analytics_seeds.reference_scorings` — F1's NFL-wide board: without them every non-house league is priced from the
    borrowed board (`/api/status` `board_source_in_use`: `nfl_wide` once added).
  * `analytics.mart_kd_week` — K / DEF on the on-demand path (`anyleague`: "K / DEF unvalued, reported").
  * `analytics.mart_projection_record` — `/api/record` for a house league answers without the record.
  * `analytics.mart_player_role_alerts` (a view) and the one relation it reads that the hosted copy lacks,
    `analytics.fct_team_game` (2 MB) — Trends' role alerts and the player card's signals come back empty (8 alerts for
    dynasty once added).

**Smoke script** (`scripts/smoke.sh <base-url> [password] [sleeper-username]`, one line per check, `shellcheck`
clean): against the patched clone with Sleeper's full player directory (12,229 players from `raw.sleeper_player`, as
fixtures) — 11 / 11 ok, exit 0 (health, the app's page, 401 without / 401 wrong / 200 login, status, house leagues,
rosters, My Week Scrubs 1, `test_manager`'s leagues, My Week Test League 1 on demand). Against `league_lab_hosted` as
published — 2 FAIL (both My Week: 500), exit 1. No server / no password: stops with one FAIL line, exit 1.

**Measured** (the image layout, uid `nobody`, the sandbox's two shared cores): memory 149 MB after start, 284–288 MB
peak after the 64 routes twice with the full player directory (Starter has 512 MB); the 64 routes 9.6 s cold in total
(slowest 1.44 s: a player card on demand), 2.4 s warm (slowest 0.32 s).

**Checks.** `cd api && uv run pytest -q`: **139 passed, 2 skipped** (3.9 min); `uv run ruff check src tests app
api/league_lab_api api/tests`: clean; `actionlint` (1.7.12, with shellcheck): clean on both workflows; `shellcheck
scripts/smoke.sh`: clean; `render.yaml` parses (PyYAML).

**Not verified here** (no Docker daemon, no internet): a real `docker build` / push (the workflow's first run is),
Render's acceptance of the Blueprint fields (`autoDeployTrigger: checksPass`, `buildFilter`, `region: ohio` — DEPLOY.md
says what to do if Render rejects one), the docker/* action versions (`setup-buildx-action@v3`, `login-action@v3`,
`build-push-action@v6`), the GHCR package's visibility, the deploy hook's `imgURL` parameter, the prices (Render
Starter $7, Standard $25; read 2026-10-02 from memory of Render's pricing, not the live page).

### H1 2026-10-02 — the gaps: upside stash and buy low / sell high on Waivers, "What it leans on most" on About, rest of season in one round of queries, search for any league (branch `dev/H1`, clone `league_lab_h1`)

**What.**
* `/api/waivers` gains `upside` (the Waiver Wire's third card region: `mart_waiver_upside` with `app/lib/signals.py`'s
  `stash_headline` / `upside_detail`; any other league: Sleeper's free agents with an NFL-wide role alert in
  `ops.player_scenarios`, the what-if re-priced in the league's scoring with `scoring.compute_points` on the
  `base_line` / `larger_line` the table keeps, `why` saying the lineup gains are the nightly's per house league) and
  `trade_lists` (the Trade Finder's buy-low / sell-high: `roster_value.trade_candidates` on the horizon board —
  `mart_league_roster_horizon` + `mart_player_availability` for a house league, `anyleague.horizon_frame` + the season
  table priced on request otherwise; best by position, the page's two card sentences quoted). `decisions.waiver_extras`.
* `GET /api/about?league=` (`api/league_lab_api/about.py`): the model's words, `importance`
  (`mart_projection_importance`: component / total, newest version, top 10 per position, the page's "how we measured it"
  caption and per-position sentence) and `grades` (`mart_projection_drift` this season next to the backtest,
  `mart_projection_backtest` per past season, current model). Any other league reads the closest house scoring
  (`research.expected_ref`) and says so in `why`.
* `anyleague.ros_table`: on the NFL-wide board the whole window is read in one round of queries (`load_window`: lines,
  ranges — only the exact reference scoring's when there is one —, K / DEF lines and ranges, status, references), every
  week's stat lines priced in one vectorised pass (`compute_points_frame`: the same terms in the same order, equal to
  `compute_points` bit for bit — `price_lines` uses it everywhere), each week's reference and ranges and K / DEF chosen
  by `price_week`'s rules over the whole window at once (`skill_window`, `kd_window`); a week the NFL-wide tables do not
  hold, or the borrowed board, is priced week by week as before. The answer is cached 10 minutes (the priced weeks' rule).
* `/api/search` for a league the database does not hold: Sleeper's directory (`sleeper().players()`, cached) by name,
  `player_id_map`, whose team from the league's rosters (`research.search_on_demand`); house leagues unchanged.
* Web: Waivers draws the upside stash (up to three cards: the player, the what-if, the page's lines, "as he is" / "lineup
  gain if it holds" tiles) and "Buy low, sell high" (the two sentences, best by position, your sell-high players, the full
  buy-low list in an expander); "How to read this" gains three lines. About draws "What it leans on most" (a position
  switch, one bar per input, the lead sentence, how it was measured) and "How the model is doing" (per position: order
  score, average miss, inside the range — this season vs the backtest — and weeks scored; "How to read the grades").
  Fixtures saved from the API (`web/fixtures/save_h1_fixtures.py`: `upside` / `trade_lists` added to the 17 saved
  waivers files, `about_<league>.json` × 3); `e2e/fixtures.ts` serves `/api/about`; `e2e/h1/fixtures.spec.ts` (3 tests ×
  phone / desktop).

**Evidence.**
* Rest of season on demand, NFL-wide board (`ondemand.ros_on_demand`, every cache emptied incl. the query cache; median
  of 3; load ≈ 0.5), cold / warm ms: dynasty 1,079 / 114 → **249 / 2**; Scrubs (K + DEF) 1,237 / 146 → **336 / 3**;
  Test League (no exact reference: five references' ranges read) 1,698 / 181 → **531 / 2** (min 487). In the test run:
  211 / 326 / 439 ms. Parity: `test_f3.py::test_ros_on_demand_reproduces_the_mart` (both boards, both leagues; 0.011)
  green; new `test_ros_window_equals_the_week_by_week_path` (all three leagues): the one-round answer = the week-by-week
  `price_week` path on every column, every player, to 1e-9, the same references.
* `compute_points_frame` = `compute_points` bit for bit on every 2026 stat line in the three fixture scorings and the five
  reference scorings (TE premium included).
* `/api/about`: importance = the mart rows (labels, values, order) per position; grades = `mart_projection_drift`
  (this season, backtest) and `mart_projection_backtest` per season, both house leagues; the Test League reads Scrubs'
  (`why`); unknown league 404. Note: importance is measured on League of Scrubs only in this copy, so the dynasty shows
  Scrubs' rows with `scored_in` = League of Scrubs.
* `/api/waivers`: `upside` = `mart_waiver_upside` row for row (dynasty 12: 3 stashes, Scrubs 2: 3); `trade_lists` = the
  Trade Finder's lists computed independently (`trade_candidates` on the mart board + the page's candidate query): same
  players, same order, fit to 0.01; dynasty 12 on demand (`source=sleeper`) = the house buy-low list (fit and PPG − xPPG
  to 0.01); the Test League's stashes priced in its full-PPR scoring = `compute_points(larger_line)` (Myles Price 3.48 =
  dynasty's full-PPR price, Scrubs' half PPR 2.90). Latency (TestClient, first call): dynasty 12 577 ms (extras 213),
  Scrubs 2 769 (212), Test League 4,599 (1,183: the season table priced on request, then cached 10 minutes).
* `/api/search` on the Test League: "brown" → A.J. Brown (gsis 00-0035676, the fixture roster that holds him), free
  agents flagged; one letter → []; the house search unchanged.
* Checks: `cd api && uv run pytest -q` **152 passed** (138 + 14 new in `tests/test_h1.py`; one earlier run under load:
  150 passed, 2 skipped); `uv run ruff check src tests app api/league_lab_api api/tests` clean; web `npm run lint` 0 / 0,
  `npm run build`, `npm run e2e:fixtures` **58 passed** (52 + 6); root `uv run pytest -q` **829 passed, 1 skipped**.

**Decisions for the PO.**
* Buy low / sell high are the Trade Finder's lists (players on other rosters / yours, by PPG − xPPG, with the lineup fit),
  shown on Waivers as asked; the web Trade Finder still has none (one component to reuse).
* The on-demand stash carries no lineup gain (the nightly's `upside_for_roster` could run on `league_weeks` the way
  `sweep_roster` does — a follow-up, ~1 s per request); the stash list is every free agent with a live alert, ordered by
  the what-if's gain.
* The keeper table on demand (task 5) was not attempted (time box): `/api/team` keeps the honest `keeper_why` line.
* `price_week` now prices with the vectorised `price_lines` too (bit for bit equal): My Week / the player card get faster
  cold.

**Open.** Real Sleeper (fixtures only); the Test League's on-demand waivers stay ~4–5 s cold (the season table and the
board); the hosted copy (`league_lab_hosted`) has no `ops.projection_lines` yet (H2's relation audit), so there the rest
of season borrows week by week as before.

## Wave I-0 (Iteration 17, part 0)

### PO merge — Wave I-0, 2026-10-03 (Friday night, for Sunday)

* **Delivered** (two Opus devs in parallel, ~25 min each): I0-A the availability overlay (ESPN's public injuries
  feed every 15 min on game days / hourly otherwise + Sleeper's daily directory, newest wins per player; applied at
  request time: the lineup re-solved with `lineup.solve` when a starter can no longer play, "who moved and why"
  sentences, OUT / DOUBTFUL / IR chips, "Injuries checked hh:mm", Trends / Waivers / trades / ROS exclusions, the
  same-team-QB rule; `availability.py`, `injury_feed.py`); I0-B MyFantasyLeague on demand (`mfl:<id>` keys,
  `mfl_client.py` with caches / 60 a minute / redirects followed, `platforms.py` answering MFL in Sleeper's shapes so no
  screen changed, `player_ids.py` the nflverse id table downloaded once a day, `/api/leagues?mfl=`, the Leagues
  screen's link box + team picker; league 21861: 216 of 216 rostered players mapped, the live JSON re-parsed through
  the pane).
* **PO**: merged on `integration/wave-i0` (two doc conflicts, both kept; one STATUS heading deduped); I0-A's
  temporary CSV reader replaced by I0-B's `player_ids.table()` (the fixture copy next to the ESPN fixtures still wins
  in tests). Checks: `api` 197 passed (159 + 19 + 19), root 835 passed, web lint / build clean, 62 fixture e2e
  (58 + 2 + 2), ruff clean. QA walk of the integrated API in full fixture mode: every route 200 for `mfl:21861`
  (team 4: lineup solved, opponent from MFL's schedule, Etienne IR → Kendre Miller at RB2 by the overlay), the house
  league with Jefferson Out by the fixture feed: "Justin Jefferson is out (ankle) — Michael Wilson starts at FLEX2",
  Jefferson on "Can't play" with the OUT chip and reason, no card names him, Trends left 28 out, status `warning`
  null. Two devs used the browser pane for fixtures (own tabs, read-only).
* **Not verified until the deploy**: Render reaching ESPN, MFL and GitHub raw (the id table); `/api/status →
  availability.espn.mode: live`, `unmapped_espn` low, `sleeper.mfl.hosts` after the first MFL league; a private MFL
  league's real refusal text (none found to test). Decisions taken: `/api/record` for MFL answers 200
  `{available: false}` like any unkept Sleeper league (I0-B's choice, kept); Doubtful counts as cannot play (as the
  nightly); the opponent's projected total is not overlay-adjusted yet; `/api/team` and Trends' role alerts untouched.

### I0-A 2026-10-02 — the availability overlay (what would be wrong at 1 PM Sunday)

Branch `dev/I0A`. Andrew's beta walk: My Week said start Justin Jefferson, ruled Out at 2:35 PM ET; Jonah Coleman (IR)
was "running hot". Cause: availability came only from nflverse's injury file via the nightly (lags the report by hours).

- **Sources** (`src/league_lab/injury_feed.py`, `api/league_lab_api/availability.py`): ESPN's public injuries feed
  (15 min on game days per `dim_game`, hourly otherwise; parsed entries cached in `LEAGUE_LAB_CACHE_DIR/espn_injuries.json`
  with `fetched_at`; last copy kept on failure; gzip; on the live server a stale copy is served while one thread reads
  ESPN) + Sleeper's directory (unchanged daily cache). ESPN → gsis via the directory's `espn_id`, then the id table.
- **Live numbers (browser pane, 2026-10-03T03:58Z)**: 800 entries, 32 teams, 8.7 MB; statuses Out / Questionable /
  Active / Injured Reserve / Doubtful; fantasy statuses OUT, QUESTIONABLE, IR, IR-R, PUP-R, INACTIVE, DOUBTFUL. The athlete
  id is only in `athlete.links[].href` (no `athlete.id`). Sleeper's `espn_id` maps 118 of ESPN's 400 skill entries; the
  id table maps 158 of 158 in the fixture. Two "Justin Jefferson"s on the feed (MIN WR 4262921 Out; CLE LB 5150249).
  Sleeper had Jefferson Out with `news_updated` 18:55 UTC — 20 min after ESPN.
- **Applied**: My Week (both paths: re-solve with `lineup.solve`, chip + reason, `availability.changes`), Trends (left
  out + count), Waivers (no claim / free agent who cannot play; drop who cannot play = 0 this week; one QB per NFL team
  by `depth_chart_order`), trades (this week's board), rest of season (`injury_status`), `/api/status` (`availability`;
  warning dropped when ESPN < 1 h old). Web: "Injuries checked 2:40 PM", the sentences under "Your lineup", the chip.
- **Evidence**: `api/tests/test_i0a.py` 19 passed. Scrubs roster 2 on the clone with the fixture feed: "Justin Jefferson is
  out (ankle) — Michael Wilson starts at FLEX2" (Wilson 9.20 vs Croskey-Merritt 9.19), lineup 117.02 → 113.54 = minus
  Jefferson's margin 3.48 exactly; Test League roster 10: Jefferson out — Stefon Diggs starts at FLEX, RB1 / RB2 stay
  empty (Etienne IR, Price Out) and say so. Trends (Scrubs): 38 players left out (IR, Out). API suite 178 passed (159 +
  19); web lint / build clean; `e2e:fixtures` 60 passed (58 + 2: `web/e2e/i0a/`); parity tests untouched and green.
- **Off switch**: `LEAGUE_LAB_AVAILABILITY=off`; off in fixture mode unless `LEAGUE_LAB_ESPN_FIXTURES` is set.

## Wave I-A (Iteration 17, part A)

### PO merge — Wave I-A, 2026-10-03 (Saturday, 01:40–03:20 ET)

* **Delivered** (four Opus devs in parallel, 27–46 min each): IA-1 the words — every call on My Week gets a reason
  sentence from the data it has (matchup rank + home/away, carry / target share moves, the injury, the betting line,
  the gap; `cards.reason_line`, shared with the console), short names + headshots on the phone lineup, "Your lineup",
  Trends renamed "Below and above expectation" with a sentence and a stat strip per row, TEs out of the cornerback
  section, "Choose a player" on Compare; IA-2 the decisions — the trade calculator as its own link, the interest dial
  (their gain over the window → 0–100, four labels, "by our numbers over weeks 4–7"), the window control (this week /
  next 4 / rest of season / playoffs on evaluate and partners), lineups shown once, buy low / sell high moved to
  Trades (`/api/trades/lists`), the sanity bound (`trades.sanity`: no suggestion gives away > 25% more ROS value than
  it gets; none that only works because ours is < 65% of the market's) — the Jefferson-for-Lloyd case is refused;
  IA-3 the rankings — headshot / bye / games / range bar / the projected pieces per row with a tap-to-expand on the
  phone, "why this number" (the pieces × the scoring = the points, within 0.05 on 40 rows) on the ROS row and the
  player card, the market line ("Sleeper has him at 16.2") where a snapshot exists, the "How to read the rankings"
  paragraph (ROS and About); M1 the diagnosis — **no star penalty**: top-6 bias 2023–2025 QB −0.98 / RB +0.34 /
  WR +0.51 / TE +0.45 in Scrubs scoring, slope ≈ 0 above the starter line; the dynasty top is under by 0.7–1.4
  mostly because yardage bonuses are paid all-or-nothing on the projected line; the real miss is a fringe projected
  0.3–0.6 too high; Andrew's gap is a *level* gap with the market (ours under Sleeper's for 75–100% of the top 24 at
  RB / WR / TE by 1–3 points a week; Bowers is a cold start at 49% of the market). A walk-forward two-piece
  calibration (`calibration.py`, flag `LEAGUE_LAB_PROJECTION_CALIBRATION`, **off**) gains only at the WR fringe
  (MAE −0.07); the ROS top 12 does not move. v3.1 leads: expected-bonus pricing, the fringe level, cold starts.
* **PO**: four merges (doc conflicts kept both; headings deduped; `api.ts` both blocks); **`analytics.mart_market_line`
  built** from IA-3's proposal (both IA-2 and IA-3 found `mart_projection_record` carries no per-player Sleeper
  rows and the hosted copy never holds `raw`): the latest snapshot per week, league-free, priced per league by
  `why.market_points`; the trade finder's `market_week` now reads it through `why` (the raw read is gone), and the
  hosted closure picks the mart up from `why.py`'s SQL (`scripts/hosted_relations.py`: `api analytics.mart_market_line`).
  It is empty in the sandbox; on Neon it fills from the nightly's `fetch-projections` — which pulls the *next* week to
  kick off, so week 4 has no market line and week 5 on does (the UI says "not in yet"). A coin flip now reads as one
  in the headline ("FLEX2: Wilson or Croskey-Merritt — a coin flip") so IA-1's tiebreaker ("Go with Croskey-Merritt
  on the matchup") never contradicts it — `cards.is_coin_flip`, both apps, the root test's regex widened, the saved
  web fixtures updated in place. About shows "How to read the rankings"; the tab reads "Calculator" (the long label
  scrolled the row at 375); three `metric_registry` rows (trade_interest, calibration_bias, market_line). Checks: API
  269 passed, root 848 passed, web lint / build clean, 100 fixture e2e, ruff clean. QA walk in full fixture mode: My
  Week cards carry `why` on house, Test and MFL leagues; partners over the ROS window 4.6 s cold (house) with 66
  packages set aside; evaluate over the playoffs window with the dial; `/api/trades/lists`; ROS rows with the pieces;
  the player card's why; About's how-to; Trends 28 left out; waivers without the trade lists.
* **Not verified until the deploy**: the market line on Neon (first rows after the Saturday nightly, week 5);
  the ROS-window partner search on Render for the dynasty league (~5 s cold here); real headshots in the lineup.

### IA-3 2026-10-03 — the rankings: more to see, and "why this number" (dev/IA3)

* **Rest of season** (`Ros.svelte`, `ros.ts`): headshot, bye ("bye 11 ·" before the owner), games left, ROS points, a
  floor–ceiling range bar (from 640 px), playoffs, and the position's stat line a game as columns from 900 px; every
  column sorts (header buttons, `aria-sort`, ▲ / ▼); a `›` on every row opens the pieces as tiles, the facts line,
  "Why this number" and — where it exists — the market line and what the model leans on for the position. A phone
  (375) shows rank · name · points · `›`. "How to read the rankings" (`about.RANKINGS_HOWTO`, also `/api/about`
  `rankings_howto`) sits under the answer.
* **API** (`ondemand.ros_rows` / `ros_more`, marked IA-3): rows + `headshot_url`, `bye_weeks`, `ros_points_per_game`,
  `per_game`, `why` (pieces, sentence, games, total), `market_points`, `week_points`, `market_words`; the answer +
  `piece_columns`, `leans_on`, `market_week`, `market_note`, `howto_rankings`. House leagues sum
  `mart_player_week_projections`' per-week lines over the weeks `weeks_json` counts (byes out, the mart's window);
  any other league reads `anyleague._ros_table`'s new `ros_<stat>` sums (the stat line now rides through
  `skill_window` / `_priced_frames`). `/api/player` + `why` / `market` / `leans_on` (top-level keys: the sections stay
  the page's, parity untouched); `/api/my-week` rows + `market_points` (`main.why_market_rows`, marked).
* **The pieces** (`why.py`): per-unit prices from the league's scoring (`weights`: every stat key, position premiums);
  each listed piece is rounded to the cent and a remainder line ("yardage bonuses …" / "the small pieces and
  rounding") makes the list add up; a remainder under 0.05 is no line.
* **The market** (`why.market_points`): `mart_projection_record` holds per-position aggregates, not player rows, and
  the API role cannot read `raw`; so the market reads a proposed league-free mart `analytics.mart_market_line`
  (docs/DATA_MODEL.md), priced per league with `scoring.compute_points`. Not built (dbt is the PO's): every answer says
  `market_points: null` and the card "Sleeper's number for this week is not in yet." Checked live in this clone: the
  proposed SQL built from the hand-built Sleeper fixture (`tests/fixtures/sleeper_projections`, 29 players) gave
  `market_points` on 28 ROS rows per league (Scrubs, dynasty, Test League), the card and My Week; table and rows
  removed afterwards.
* Timings (in process, warm): `/api/ros` Scrubs ALL 114 ms, WR 22 ms (the per-week line sums vectorised); Test League
  ALL ~2.0 s cold (the window board), WR 65 ms warm. Answer ~80–100 KB uncompressed for 50 rows.
* Checks: `api/tests/test_ia3.py` 13 (the pieces add up for 10 rows × 4 positions × Scrubs / dynasty / Test League;
  market null without the mart, empty mart, failing read; present and priced per league with a constructed mart on
  `/api/ros`, `/api/player`, `/api/my-week`; the gap words; the honesty paragraph is one text); `test_f3`'s ROS key
  set updated; API suite 237 passed; root 834 passed, 2 skipped; ruff clean; web lint / build clean;
  `npm run e2e:fixtures` 74 passed (66 + 8 in `web/e2e/ia3/`; `fixtures.spec.ts`' ROS header list updated).
  Fixtures: `web/fixtures/save_ia3_fixtures.py` adds the new fields to `ros_*.json` / `player/*.json` in place
  (numbers untouched; a row whose total differs keeps no pieces).

### M1 2026-10-03 — is the top of the distribution under-projected? (branch `dev/M1`, clone `league_lab_m1`)

Andrew: "I don't think anybody has Dak rated number one overall… what's the reasoning?", Jefferson at 10.0, Brissett
top 8 rest of season. Diagnose first, calibrate only if the numbers call for it (PROJECT_PLAN § 17 B).

* **Answer.** The model does not pull stars toward the middle. On 2023–2025, out of sample, the top 6 per position
  in League of Scrubs' scoring (no bonuses) miss by QB −0.98 (too high), RB +0.34, WR +0.51 and TE +0.45. They change
  sign by season (2019–2022: −0.27 / −0.67 / −0.06 / −0.51), and the miss does not grow above the starter line
  (slope ≈ 0, |t| ≤ 1, clustered by player). In the dynasty scoring the top 24 RB / WR / TE are +0.7 to +1.4. About two
  thirds of that is the yardage bonuses, priced all-or-nothing on the projected line: without them the dynasty top-6
  miss is RB +0.47, WR +0.53, TE +0.59. What is real is small and not at the top. The bottom half of each position is
  0.3–0.6 too high, and the starter line is about 0.5 low. Dak (QB2 in dynasty) and Brissett (QB9) are superflex and
  6-point-TD arithmetic, and the market agrees on their week-4 numbers (Dak 23.8 vs Sleeper 23.3; Brissett 21.2 vs
  20.5). Jefferson is 12.7 in Scrubs for week 4 in the clone (usage); Sleeper had him at 13.8–14.7 in weeks 1–3, and
  he is Out now.
* **Top-6 bias** (mean actual − projected, 2023–2025, 324 player-weeks each; per season 2023 / 2024 / 2025):

  | | Scrubs | per season | Dynasty | per season | Dynasty without bonuses |
  |---|---|---|---|---|---|
  | QB | −0.98 | −1.27 / −1.05 / −0.63 | −0.34 | −0.59 / −0.27 / −0.18 | −1.01 |
  | RB | +0.34 | −0.90 / +1.27 / +0.64 | +1.19 | −0.32 / +2.76 / +1.14 | +0.47 |
  | WR | +0.51 | +1.57 / −0.46 / +0.40 | +1.43 | +2.77 / +0.33 / +1.19 | +0.53 |
  | TE | +0.45 | +0.69 / −0.31 / +0.98 | +0.88 | +1.08 / +0.07 / +1.50 | +0.59 |

* **Against the market** (Sleeper's lines for 2026 weeks 1–4, one read-only snapshot through the browser pane
  2026-10-03, priced in both house scorings; `mart_projection_record` is empty in every sandbox database). Our
  number is under Sleeper's for 75–100% of Sleeper's top 24 at RB / WR / TE, by 1.1–2.7 points a week, and about 1
  point at QB. It is under 70% of Sleeper's for 4–21% at RB / WR and 12–29% at TE (Bowers week 4: 6.0 vs 12.2, a cold
  start after missed games). On the weeks the clone has outcomes for (1–2 plus one week-3 game; 66–205 player-weeks
  per position), the average bias is ours +0.9 to +1.2 vs Sleeper −0.5 to +0.3 at RB / TE, both within ±0.6 at QB / WR; MAE
  is a tie (ours − Sleeper −0.45 to +0.20).
* **Calibration built and measured** (`src/league_lab/calibration.py`). The per-row walk-forward (`oof_rows`) is
  needed because `ops.projection_backtest` is per week; it reproduces every stored v3.0 cell exactly. The rest is the
  bias tables, a monotone two-piece linear map per position × scoring (knot at the 80th percentile, coefficients
  clustered by player and shrunk to 0 below |t| = 1, slopes within ±0.5, so the order never changes), walk-forward,
  and expected-bonus curves. Results on 2023–2025 (and 2026 weeks 1–3): the *hinge* (top only, up only) is the
  identity everywhere except dynasty WR (MAE +0.012). The *two-piece* on the last 3 seasons passes the MAE bar only
  at WR (−0.082 dynasty / −0.074 Scrubs, 3 of 3; 2026 −0.14 / −0.15), by lowering the fringe. RB is −0.01 / −0.02,
  TE ≈ 0, and QB worse (+0.02 / +0.03). *Expected bonuses* (dynasty): top-6 bias RB +1.19 → +0.51, WR +1.43 → +0.61,
  but weekly MAE +0.02 to +0.03 (a mean fix of a skewed bonus does not help a median loss).
* **Wired, off.** `LEAGUE_LAB_PROJECTION_CALIBRATION=1`: `project` (one marked block after `house_rows`) fits the
  two-piece maps for WR on the newest 3 seasons of `ops.calibration_oof` (`calibration.run_build_oof()`, offline,
  about 2 CPU-minutes) and applies them to the house leagues' rows and their reference ranges. Proven on the clone
  (flag-on `project`, 2026): weeks 1–4 identical to before, freeze labels included; weeks 5–18 move only WR (dynasty
  mean −0.18, range −0.77 to +0.53; Scrubs −0.39, −0.78 to +0.08); QB / RB / TE / K / DEF and the ppr / standard /
  te_premium ranges unchanged. Known side effects, so it stays off: `signals_after_project`'s scenario check refuses
  ("scenario base differs from the stored projection by 0.70", logged, not fatal), dbt's
  `assert_projection_ranges_price_the_lines` (warn) would flag the calibrated weeks, and on-demand leagues (priced
  from the line) do not see it. The clone was re-projected with the flag off afterwards.
* **Rest of season, before → after** (top 12 of both house leagues). Unchanged under the flag: dynasty is 11 QBs and
  Bijan; the Scrubs top 12 is RBs and QBs. Jefferson moves 196.8 → 203.7 (dynasty, #53 → #51) and 149.2 → 150.2
  (Scrubs). Expected bonuses would lift dynasty's top by 7–13 points over 13 games, QBs included (Brissett #10 → #8),
  with no new names in the top 12.
* **For the PO.** (1) Leave the flag off. (2) IA-3's words: "under the market" is normal (about 2 points), and "well
  under" belongs at < 70%. (3) v3.1 candidates: expected-bonus pricing in the pricing of a projected line, for
  leagues with yardage bonuses; the starter-line level and the fringe as a model fix, not a map; a cold-start rule
  for players back from injury. (4) A real pre-kickoff Sleeper record still needs the nightly's `fetch-projections`.
* **Tests.** `tests/test_calibration.py` 13 passed (monotone in both modes, identity without bias, too few rows =
  identity, a lifted top lowers MAE, the hinge never lowers, walk-forward uses earlier seasons only (2023's outcomes
  scrambled give the same maps), bands move and keep their order, the flag-off hook is a no-op, the flag-on hook
  moves only WR of the calibrated scorings, buckets and deciles, the harness's definitions, the bonus curves). Root
  suite: see the hand-back. ruff clean.
* **Deviations.** `REPORT.md` is not a file: the sandbox refuses report files from developer agents, so the full
  report with every table is the hand-back text. The Sleeper comparison uses a post-game snapshot (Sleeper's
  `updated_at` is just after each week's last game), not the pre-kickoff record.

## Wave I-B (Iteration 17, part B)

### PO merge — Wave I-B, 2026-10-03 (Saturday, 11:30–13:00 ET)

* **Why**: a second reviewer walked the live beta (plan § 17 "Second review"); #1 was a trust bug the PO confirmed —
  the I0-A overlay re-solved My Week only, so Waivers / Team / the player card / the trade board read the nightly's
  lineup and could contradict My Week between builds. #2–#7 adopted as written.
* **Delivered** (four Opus devs in parallel, 30–45 min each): IB-0 one availability truth —
  `availability.roster_context(league, roster, week)` is the one read of a roster's week (the build's rows + the
  overlay, re-solved with `lineup.solve`, cached for the overlay's interval); My Week, the opponent's total, Waivers
  (total, weakest, drop words — never "would not start" for an overlay starter), Team, the player card's Availability
  and the trade board all read it; `test_ib0.py` asserts one total on all four screens, overlay on and off, both
  paths (Scrubs 113.54 / 117.02 / 117.02 / 113.54 before → 113.54 everywhere); the cards gain `status` (change / set /
  close from Sleeper's current starters) and `strength`. IB-1 navigation by task — **My Team · Waivers · Trades ·
  Players** (sub-tabs This week · Season · Team · League; Partners · Calculator; Trends · Matchups · Receivers · Compare
  · Players), About in the ⋯ menu and the My Team footer, a search field in the top bar (a magnifier under 1280 px),
  the player page inside the frame, and `PlayerPane.svelte` + `lib/pane.svelte.ts` (`openPane(gsis, {from,
  context})`, a sheet on the phone / a 25 rem panel from 900 px, state in `?pane=&from=`, Back closes it) with the
  contextual actions — Compare with my starter / Evaluate add / drop / Add to trade / Full page — wired on My Week's
  lineup rows, Players, Trends' phone rows and the search field; `overflow-x: clip` so sticky works at last. IB-2
  Waivers short — `top3` with one reason each and the claim's cost, views Help now · Bye coverage · Stashes · All
  available (one answer, chips switch; the chip row within 1.1 phone screens on Scrubs, was ~6 desktop screens), the
  "best alternative before a drop" line whenever the drop starts this week or next; the calculator leads with the dial
  row and pins a verdict bar while the rosters scroll, Why? / Lineups collapsed; partner cards = package · label · gain
  · one reason · Try it; `?add=&drop=` from the pane. IB-3 matchup meaning — Favorable / Neutral / Difficult as the
  signal on every cell and corner (tone cut = the card's own rule, so a cell and a reason line agree), one rank
  direction (`tough_rank`, 1 = fewest allowed; the rank in words), corner `certainty` beside the tone, no shutdown
  badge; **Value to my lineup** leads Season (`/api/ros?view=lineup&team=&who=`: a player's gain to this roster over
  the window, the bench *or* the best free agent filling in; a backup QB behind a healthy starter is 0 with the
  sentence; Everyone / Yours / Free agents / Other teams); the My Week card = status chip · slot + strength · the
  call · one reason · Compare these players · the small print behind Why?.
* **PO**: merges in the order IB0 → IB3 → IB2 → IB1 (doc conflicts kept both; `decisions.py`: IB-0's context line then
  IB-2's views; the ROS spec: IB-1's `sub-ros` then IB-3's `view=points` tap); IB-2's `_starts_soon` now reads IB-0's
  `roster_context` for this week (one overlay pass, not two); the API suite sets `LEAGUE_LAB_MFL_FIXTURES` for every
  test (IB-0's MFL cases had reached for the live host). Checks: API 316 passed, root 848, web lint / build clean,
  **130 fixture e2e**, ruff clean. QA walk in fixture mode with Jefferson Out: My Week = Waivers = Team = 113.54,
  the opponent 120.31 with his own changes, cards close / set / set with strengths, Waivers' top 3 with reasons,
  Value to my lineup (Washington +38 … Jefferson +35), defense cells with tone + rank words, corner rows with tone +
  certainty + the corners' words, the MFL league's cards with statuses.
* **Decisions kept**: "set" = Sleeper starts the recommended player in any slot (RB1/RB2/FLEX swaps are one lineup);
  Waivers re-prices the nightly's moves under the overlay but does not search again (a free agent who only matters
  because of today's news waits for the next build); own players' lineup value counts the best free agent at the
  position as the fill (a lone kicker is not worth his whole projection); the console keeps "#18 of 74, shutdown" for
  parity while the web says it in words; the Test League fixture rosters carry no `starters`, so its cards all read
  "change" in fixtures. Cold latency up on Waivers (~2.1 s) and Team (~1.8 s) when the overlay touches many rosters;
  contexts are cached after the first read.
* **Not verified until the deploy**: the sheet on real iOS Safari (88dvh, safe-area, swipe-back), the pinned verdict
  bar under the notch, the fixed-vs-sticky bar after `overflow-x: clip`, Render latency on a Sunday with many Outs.

### IB-1 2026-10-03 — navigation by task, and the research pane everywhere (branch `dev/IB1`)

- **Four tabs** (`TopBar.svelte` `SECTIONS`): **My Team** (This week `/` · Season `/ros` · Team `/team` · League
  `/league`) · **Waivers** (`/waivers`) · **Trades** (Partners `/trades` · Calculator `/trade-calc`) · **Players**
  (Trends · Matchups · Receivers · Compare · Players). Testids `tab-myteam|waivers|trades|players`; sub-tabs keep
  `sub-<route>` (new: `sub-week`, `sub-ros`). Every path kept (bookmarks, `/record`). Phone: the four in the bottom bar,
  the second row under the top bar.
- **Top bar**: the **search field** (always open from 1280 px; a magnifier under that, the field then covers the row,
  with Cancel) → a hit opens the pane; the **overflow menu** (⋯: About the numbers, Other leagues). About also at the
  foot of every My Team screen (`foot-about`). The wordmark shows from 640 px (the picker needs the width at 375).
- **The player's page keeps the frame** (`App.svelte` renders it under the top bar; its own header + search are gone,
  "‹ Back" / "‹ My week" stays); the tab you came from stays lit.
- **The research pane** (`components/PlayerPane.svelte` + `lib/pane.svelte.ts`, contract in
  `scratchpad/waveIB/PANE_API.md`): `openPane(gsis, {from, context})`, `closePane()`, `paneLink(gsis, opts)` (an
  attachment for a name link); `PlayerRow` / `PlayerCard` / `LineupTable` take a `pane` prop. From 900 px a sticky
  25rem panel beside the screen; on a phone a bottom sheet (Back / × / the dim / Escape close it). Contents: the
  player card unit, the actions, the card's sections (`lib/card.ts`, shared with the full page), his game log.
  Actions: `lineup` → "Compare with my starter" (bench → the weakest starter he could replace) / "Compare with my best
  bench option" (a starter) → `/compare?a=&b=`; `waiver` → "Evaluate add / drop" → `/waivers?add=&drop=` (IB-2 reads
  `add`); `trade` → "Add to trade" → `/trade-calc` ticked; always "Full page". In the URL as `?pane=&from=`; the first
  pane is a history entry (Back closes it), a swap replaces it, "Full page" replaces it (Back lands on the screen).
- **Wired**: My Week's lineup and full-lineup names, Players' list names, the search field, Trends' rows on a phone
  (the sheet instead of the page; desktop keeps Trends' own detail beside the list).
- **Fix found on the way**: `html, body { overflow-x: hidden }` made `<body>` a scroll box, so no `sticky` element
  stuck (ListDetail's detail never did either) → `overflow-x: clip` (hidden kept as the fallback).
- **E2e renames (mechanical)**: `tab-ros` → `sub-ros`; `tab-about` → ⋯ then `menu-about`; `tab-research` →
  `tab-players`; `tab-decisions` → `tab-waivers` / `tab-trades` / `tab-myteam`; a lineup name → the pane, then
  `pane-full`; `app.spec.ts`'s search → the top bar's field then `pane-full`; `measure.spec.ts` taps the cards' names
  only (the lineup's open the pane). The top bar's placeholder is "Search players" (IA-1 keeps "Find a player" off
  Compare).
- **Checks**: web lint (eslint + svelte-check 151 files, 0 / 0) and build clean; `npm run e2e:fixtures` 110 / 110
  (100 existing + 10 new in `web/e2e/ib1/`, 375 and 1300 px). No API or Python change.

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


### I0-B 2026-10-03 — MyFantasyLeague, read-only, on demand (branch `dev/I0B`, clone `league_lab_i0b`)

**What.** An MFL league is a key (`mfl:21861`), a client (`src/league_lab/mfl_client.py`) and a translation into
Sleeper's shapes (`src/league_lab/platforms.py`: `anyleague.sleeper()` is now a `Router`; `anyleague.check_id`
accepts both keys); the id table (`src/league_lab/player_ids.py`: `mfl_to_sleeper`, `mfl_to_gsis`, `espn_to_gsis`,
`sleeper_to_gsis`, `download_if_stale()` once a day into `LEAGUE_LAB_CACHE_DIR`, `LEAGUE_LAB_PLAYER_IDS_CSV`
override — I0-A's CSV reader in `availability.py` can switch to it). Routes: `GET /api/leagues?mfl=<link or id>`; every
on-demand route answers for `mfl:` keys unchanged. Web: the Leagues screen's "On MyFantasyLeague? Paste your league
link" → the league card with its teams → My Week; remembered on the phone; "· MFL" in the league switcher. Design and
the translation rules: docs/ANY_LEAGUE.md § "MyFantasyLeague"; calls and contact: docs/MFL_TERMS.md.

**Evidence (fixtures fetched 2026-10-03 through the browser pane; `api/tests/test_i0b.py`, 18 tests).**
* 21861 slots: QB, RB, RB, WR, WR, TE, FLEX, FLEX, K, DEF + 8 BN. Scoring: pass_yd 0.05, pass_td 4, pass_int −1,
  rec 1, bonus_rec_te 0.5, fgm 3 / 3 / 3.45 / 4.45 / 5.5, pts_allow 12 / 8 / 2.857 / 0…; label "12-team redraft ·
  full PPR · 4‑pt pass TD · TE premium 0.5". IDP league 10015: DT / DE / LB / CB / S left out and said so; 19 events
  listed as not counted (tackles, sacks (player), return yards…); yardage bands → bonus_*_yd_*.
* Players: 216 of 216 rostered in 21861 mapped to Sleeper ids (202 by the id table, 14 defenses by team code).
* Every route 200 for `mfl:21861` in fixture mode (my-week, team, waivers, trades/partners, trades/evaluate, ros,
  league, search, about, trends, matchups/defense, matchups/cb, players, receivers, compare, player card, player
  games, record (available: false), leagues/mfl:21861/rosters, status); `mfl:99999999` (MFL's own error body) → 404
  "MyFantasyLeague would not share this league: … Ask the commissioner to allow API access".
* The live re-test (pane, 2026-10-03 00:44 ET): league, rosters, schedule, standings, weekly results week 3 equal the
  saved fixtures (SHA-256 of the canonical JSON); live scoring week 4 differs only in player order (same starters);
  the live rules parse to the same scoring; the final code on the live copy: 216 / 216 mapped (full 12,518-row table),
  10 starters per team.
* Checks: ruff clean; API suite 175 passed, 2 skipped (176 with the unmapped-starter test added after); root suite 834 passed, 2 skipped; web lint / build clean;
  `npm run e2e:fixtures` 60 passed
  (the new `e2e/i0b/fixtures.spec.ts`, phone + desktop).

### I0-C 2026-10-03 — find an MFL league by its name (branch `dev/I0C`, clone `league_lab_i0b` read-only)

**Why.** Andrew's dad uses the MFL phone app and may know only his league's name. **What.** The one MFL box on the
Leagues screen takes a link, an id or the name. `mfl_client.MFL.league_search(text)` (MFL's public
`TYPE=leagueSearch`, `api.` host, cached 10 minutes, the same bucket; fewer than 3 characters → no call; an `error`
body or no fixture file → no match) → this season's leagues, best first, `home_url` rebuilt from the id (MFL's
`homeURL` lacks the colon: `https//www45…`). `GET /api/leagues?mfl_search=<text>`: a link / id / `mfl:` key answers
exactly as `?mfl=`; a name → `{platform, query, season, matches (≤ 25), total, note}`. Web: copy "Paste your league
link, or type your league's name as it appears in the MFL app."; the matches as a list (name + "MFL · 2026"); tap →
the league card and the team picker ("‹ Not this league" back to the list) → My Week; remembered as before. The box is
now `type="text"` (it was `type="url"`, which made the browser refuse a bare id or a link without `https://`).

**Evidence.** Fixture `api/tests/fixtures/mfl/leagueSearch_addicts.json`: the live answer for `SEARCH=addicts`
(browser pane, own tab, one page, closed after; 72 leagues, all 2026, every `homeURL` `https//…`), trimmed to MFL's
first 30. `api/tests/test_i0c.py` 27 passed (parsing, ranking, 10-minute cache, the 3-character rule with no call,
empty / error / single-object / last-season answers, a link / id / `mfl:` key in the box equal to `?mfl=`, the private
404, MFL down → 502, `https//` and `homeURL` absent from the response). `web/e2e/i0c/fixtures.spec.ts` (phone + desktop:
type "addicts" → 25 of 30 → pick → 12 teams → My Week; no match; two letters; a bare id → the card).
Checks: ruff clean; API suite 224 passed (197 + 27) with `LEAGUE_LAB_ESPN_FIXTURES` unset — with this worktree's `.env`
(the ESPN fixture feed has Jefferson Out, so the overlay moves the house lineups) 8 house-league parity tests fail
exactly as on `main`, none touched by I0-C; root suite 834 passed, 2 skipped; web lint / build clean;
`npm run e2e:fixtures` 66 passed (62 + 4). I0-B's e2e: label and mock follow the box (`?mfl_search=`).


### IA-1 2026-10-03 — say it like a person would: My Week, Trends, Matchups, Compare (branch `dev/IA1`, clone `league_lab_i0a`)

**Why.** Andrew's walk of the beta on his phone: "it's not very conversational", "names are squished on my iPhone",
"put the pictures there", "I don't know if that's helpful week to week … reasons why". **What.**

* **The card says why** (`app/lib/cards.py`, the console's words too): `reason_pieces` scores what the card can know
  (+ = good for him this week): the injury tag and practice (`report_status`, `practice_status`), the matchup
  (`opp_rank` vs his position, home / away: ≤ 10 "gives up the Nth-most", ≥ 23 "the Nth-fewest"), the betting line
  (`implied_team_total` ≥ 26 / ≤ 18), his share of his team's carries (RB) or targets (WR / TE) game by game (a move of
  10 points from one game to the next, or 6 over three games in a row), and the level of that share. `reason_line`
  writes ONE sentence: the strongest piece for the starter and the strongest against the other player; with a
  percentage under 55% (or under 1 point apart without one) "Too close to call: … the ranges say either. Go with X on
  the matchup / the role / the betting line: …" (an injury first). `reason_facts` is the one extra read per set of
  cards (`REASON_SQL`: `mart_player_week_features` for the decision week + `fct_player_game` shares this season, and
  `dim_team`'s 32 nicknames), gsis-keyed, so the on-demand path (any Sleeper / MFL league) gets the same sentences.
  The odds and the numbers ("… outscores … 51% of the time — a coin flip. 9.20 vs 9.19 projected: 0.01 apart.") moved
  into the small print; "Too close to lose sleep over" went (the reason line says it). `/api/my-week` cards carry
  `why` (= the second block). How to read this updated.
* **My Week (web)**: `shortName()` in `names.svelte.ts`; `LineupTable` with a 32 px headshot on every row, short names
  under 640 px, the flag and the margin under the name on a phone (the Flag column is gone: the name keeps the width);
  `/api/my-week` lineup rows carry `headshot_url` and `team` (marked block in `myweek.py`, one `dim_player` read). The
  header: "Your lineup" + "Starters, the bench, who can't play — tap a name for his card."; the expander under it is
  "The bench and who can't play"; the Trends link "Who's above or below expectation ›".
* **Trends**: "Below and above expectation" (title, answer, chips Below / Above, the cards, How to read this, the game
  log's words, the detail); per row a strip under the name: targets and carries a game (last 3, the season), snaps
  over the last 3, expected and actual points; the gap bar kept; the sentence "Getting the targets of a 20.0-point
  player, scoring 39.4: 4 touchdowns in 2 games on 6 red-zone targets." (`research.trend_why` / `trend_cause`: red-zone
  chances without a touchdown, touchdown passes, a quarterback change from `pn_qb_changed`, a share that moved 6+
  points; no cause when none of those holds). One query (`WORK_SQL`) for the page's players.
* **Matchups**: the cornerback section lists wide receivers only (the TE rows and the "tight ends draw linebackers"
  sentence are gone, web side; the API and the console are unchanged), titled "The cornerbacks your receivers face"
  (the section-title style), headshots on every receiver row (they were there via `PlayerRow`). **Compare**: "Choose a
  player" on both pickers.

**Before / after** (the API on `league_lab_i0a`, week 4; before = `main` at `63a351b`):

| Card | Before (the headline under the call) | After (the reason line) |
|---|---|---|
| Scrubs 2, FLEX2 Wilson / Croskey-Merritt (a close call) | **Michael Wilson outscores Jacory Croskey-Merritt 51% of the time — a coin flip.** 9.20 vs 9.19 projected: 0.01 apart. | Too close to call: the projection has them level, the ranges say either. Go with Croskey-Merritt on the matchup: he is at home against the Colts, who give up the 2nd-most points to running backs. |
| Scrubs 2, RB2 Hampton / Croskey-Merritt (a role drop) | **Omarion Hampton outscores Jacory Croskey-Merritt 62% of the time — a lean.** 11.28 vs 9.19 projected: 2.09 apart. | Hampton's share of the carries rose from 57% to 72% last game; Croskey-Merritt's share of the carries fell from 50% to 38% last game. |
| Dynasty 12, TE Kittle / Likely (home, a tough defense) | **George Kittle projects 0.84 more on average; Isaiah Likely outscores him 53% of the time — a coin flip.** 10.36 vs 9.52 projected: 0.84 apart. Too close to lose sleep over — the projection says George Kittle, the ranges say either. | Too close to call: the projection says Kittle by 0.8, the ranges say either. Go with Likely on the matchup: Kittle is at home against the Broncos, who give up the 8th-fewest points to tight ends. |
| Dynasty 12, Superflex Penix / Willis | **Michael Penix Jr. outscores Malik Willis 55% of the time — a lean.** | Vegas expects Willis's Dolphins to score only 16, and the projection has Penix 0.9 points ahead. |

**Evidence.** `api/tests/test_ia1.py` 9 passed: `shortName` (13 cases, run under Node with type stripping), the reason
on three cards built from the fixture weeks' numbers (home / away, a role drop with the three-in-a-row form, a close
call) + an injury tiebreak with two Wilsons + no extra read, the API's cards on both house leagues (reason = second
block, odds in the small print, headshot / team on every lineup row), the Trends sentences and the new row fields
(targets a game checked against `fct_player_game`). `test_parity.py`: the reason line is pinned on both sides (page and
API). Fixtures: `web/fixtures/save_ia1_fixtures.py` brings the saved My Week answers (three + I0-A's) and the three
Trends answers to the new shapes in place (cards that the API answers today copied; others rebuilt from their own
numbers). `web/e2e/ia1/fixtures.spec.ts` (375 × 812 and 1300 × 900): short names on the phone / whole on the desktop,
a headshot per row, the header, every card's reason (body size > small print), Trends' words / strip / sentence,
Matchups' title (bold) with no TE row, Compare's label. The shared spec's Trends and Matchups assertions follow the
new words (4 → 3 cornerback cards: the TE is left out).

**Decisions for the PO.** (1) On a coin flip the reason may name the *other* player as the tiebreak ("Go with
Croskey-Merritt on the matchup") under "Start Wilson over Croskey-Merritt" — the brief's example; the headline stays
the projection's call. (2) The expander under "Your lineup" is "The bench and who can't play" (two "Your lineup"
titles would read as a repeat). (3) TEs are dropped from the cornerback section in the web only; `/api/matchups/cb`
and the console keep them (parity). (4) The lineup's Flag column moved under the name at every width. (5)
`mart_player_next_matchup` is not used: on the clone its `next_week` is 3 while the decision week is 4; the week's
features (`mart_player_week_features`) carry home / away and the line for the decision week itself. (6) The console's
"What's new" (`app/whats_new.md`) is not touched (only `cards.py` in `app/` is IA-1's).

### IA-2 2026-10-03 — the decisions screens: the trade calculator, the interest dial, the window, the sanity bound (branch `dev/IA2`)

Andrew's beta walk (2026-10-02): "a slider would be really cool", "why those four to seven weeks?", "showing the lineups
twice doesn't make any sense", "some of the trades it's suggesting are crazy" (Justin Jefferson for MarShawn Lloyd).

- **The window** (`decisions.py`, block "IA-2"): `window=week|next4|ros|playoffs` on `POST /api/trades/evaluate` (body)
  and `GET /api/trades/partners` (query); default `next4` (the old behaviour, the old response keys kept). `week` = the
  board's first week; `ros` / `playoffs` extend the board (`window_board`): one row per player and week past the next
  four from the rest-of-season board (house: `mart_player_ros_projection.weeks_json`; on demand: `anyleague.ros_table`
  through `ros_on_demand` — `load_window` + `skill_window`), on the bench (the solver picks the starters) or unplayable
  on a bye; IR slot / taxi squad / NFL IR / no NFL team carried from the board's last week. `ros` = this week to the
  league's final (`ros_window`), `playoffs` = `playoff_week_start` to the final. The response names the weeks (`span`,
  `weeks`, `window_label`, `window_why`); `fit.window` (= `fit.next_4`, its name before) is the window's gain; this
  week's numbers and lineups always come from this week (the playoffs window evaluates this week on its own; `_View`
  feeds `trades.fit_line` / `verdict` both). The league-rank line compares the horizon only when the window is next4.
- **The dial**: `interest(their_gain, my_gain, span)` → `{score 0–100, label, their_gain, you, caption}` on every
  evaluate and every partner row. Labels: their window gain < 0.05 "No deal" (they lose, or gain nothing shown as
  +0.0), < 2 "Maybe", 2–6 "Likely", > 6 "Hard to say no"; score piecewise linear through (−6, 0) (0, 25) (2, 50) (6, 75)
  (12, 100), each label a quarter of the dial.
- **The sanity bound** (`trades.sanity`, `trades.partners(..., allow=, rejected=)`): a package that would be a roster's
  best is set aside, and the search goes on, when (b) a player you give has our projection this week under 65% of
  Sleeper's ("the market disagrees with our number on <player> (ours x, Sleeper's y)") or (a) the rest-of-season points
  you give exceed what comes back by more than 25% of what you give ("you give 149 rest-of-season points for 97: 52
  more, over 25% of what you give" — Jefferson for Lloyd on Scrubs' board). Unknown is not zero: a player with no
  number is not judged. `rejected` (three examples: partner, give, get, why) and `rejected_count` on
  `/api/trades/partners`; `sanity` (the reason or null) on evaluate — the calculator says it, never hides the trade.
  Sleeper's number: `mart_projection_record` holds no per-player rows (its Sleeper prices are a CTE), so `market_week`
  reads its source, `raw.sleeper_projections` (the week's latest snapshot, skill players with a stat line, priced with
  `compute_points` in the league's scoring — the mart's `league_points` rule). This clone holds no snapshot: rule (b)
  is off here and the response says so (`sanity.market_note`); tested on a constructed board and with a monkeypatched
  market on Scrubs.
- **Buy low / sell high** left `/api/waivers` (`waiver_extras` returns the upside stash only) for
  `GET /api/trades/lists?league=&team=&position=` (Wave H's `_trade_lists`, memoised; on demand on the trade context's
  solve). test_h1's three list tests read the new route (same assertions).
- **Web**: `/trade-calc` (`routes/decisions/TradeCalc.svelte`; a route in `router.svelte.ts`, a loader in
  `decisionPages.ts`, "Trade calculator" in TopBar's Decisions row — the row lives in `TopBar.svelte`, so the marked
  entry is there, not in `App.svelte`, which needed no change): window control → partner → the dial's row (Dial,
  your gain, the four fit tiles, the verdict, the sanity line) → the pickers → market / rest of season / ranks / roster
  size → your lineup, theirs under an expander → week by week. Every tick re-asks evaluate (250 ms debounce); the last
  answer stays while the next is asked, so the needle swings. Trades keeps the best partner ("Try this trade" opens
  the calculator with the package and the window in the link), the window control, the partner finder (with "N
  lopsided trades left out"), and gains buy low / sell high under it. Waivers points to Trades. New design-system
  entries: Dial, Window control (DESIGN.md § Charts).
- Evidence (fixtures, next4 → week / ros / playoffs, the best package's window gains, mine / theirs): Scrubs 2 (Tuten
  for Dowdle + Worthy) +9.74 / +10.29 "Hard to say no" (93) → −0.53 / +9.72 (90) · +3.50 / +18.72 (100, weeks 4–16) ·
  −0.16 / +0.61 "Maybe" (33, weeks 15–16); Test League 3 (Love for Golden + C. Williams) +16.59 / +12.51 (100) →
  "Maybe" 32 · 83 (weeks 4–17) · "Likely" 53 (weeks 15–17). Partner search on demand, cold (Test League): next4 5.6 s
  (the league solve), week 0.4 s, ros 3.5 s, playoffs 0.7 s; Scrubs (house) 1.2 / 0.4 / 4.9 / 0.4 s; memoised 10 min
  (house) / 2 min. Set aside by the bound (next4): Scrubs 8, dynasty 283 (mostly 2-for-1s giving two starters for one),
  Test League 31.
- Checks: `api/tests/test_ia2.py` 23 (dial buckets, the window on both routes for the Test League and both house
  leagues, the constructed Jefferson-for-Lloyd board for both rules, the partner search unchanged without rules, both
  rules on the Scrubs route, the lists moved, the Trade Finder's compiled sentences); API suite 247 passed; ruff clean;
  web lint / build clean; fixtures re-saved by `web/fixtures/save_ia2_fixtures.py` (partners re-saved: the bound
  changes some suggestions; window variants; `trades_lists_*`; `trade_lists` dropped from the waivers fixtures; the
  evaluate fixtures re-saved, plus one "tick" variant per league, `ia2_packages.json`); `web/e2e/ia2/` 16 (8 × phone
  at 375 px and desktop); G4's trades test and the tab-row test, H1's buy-low tests follow the move.

## Wave I-B (Iteration 17, part B)

### IB-0 2026-10-03 — one availability truth (branch `dev/IB0`, clone `league_lab_i0a`)

The second review's #1: I0-A's overlay re-solved the lineup on My Week only; Waivers' "would not start", the Team Hub,
the player card's lineup line and the trade board read the nightly's `ops.lineups`, so between a build and the next
morning two screens disagreed (115.75 vs 117.3 on the live app).

- **One context** (`api/league_lab_api/availability.py`, `# ---- IB-0`): `roster_context(league, roster, week)` = the
  nightly's rows (`cards.lineup_rows`; any other league `anyleague.lineup_rows`) + `apply_to_rows` (the overlay, the
  lineup re-solved by `lineup.solve` when a status changed since the build). Every rostered player's `status` (OUT /
  DOUBTFUL / IR / Q / ok), `can_play`, `starter`, `slot`, `value`, `locked`; `lineup_value`, `changes`, `checked_at`,
  `as_of_build`. Kept in process for the overlay's interval (at most 10 min; 2 min on demand), keyed by league, roster,
  week, the overlay's stamp and the build. `touched()` names the rosters the overlay can move (a starter or bench player
  who cannot play by a copy newer than the build); `contexts()` reads several side by side (4 threads).
- **Readers**: My Week (both paths) and the opponent's projected total (his context; I0-A left it); Waivers (the total,
  the weakest starter, and `moves_on_context`: each move's this-week gain, lineup before / after, seat, displaced
  starter and the drop's cost re-solved on the context, the later weeks kept, moves that no longer gain dropped, the
  ranks re-run with `waivers.rank_moves`' order, the page's sentences written after; `drop_words`: a drop who starts
  this week carries `starts_this_week` / `slot_this_week` and is never "would not start"); the Team Hub (lineup / bench
  / horizon value, the closest call, slot strengths, the roster, this week's league comparison and every rank, re-read
  for each roster the overlay moved); the player card (its lineup line reads the context; Availability adds "Justin
  Jefferson is out (ankle): he starts at FLEX2 this week" / "Not in this week's lineup: …" when the overlay moved his
  roster, and the injury line shows the overlay's status when newer than the build); the trade board (this week's rows
  of every roster the overlay moved are its context's, before I0-A's `horizon_overlay`). ROS and Trends unchanged
  (already on the overlay).
- **The card's status** (`app/lib/cards.py`, both apps): `cards.decisions` adds `strength` (clear: 3+ points or
  p_win ≥ 0.7; coin flip: `is_coin_flip`; else lean) and, when the rows carry `cards.SLEEPER_STARTER` (who Sleeper
  starts now), `status`: close (a coin flip) / set (Sleeper starts him and not the other player) / change. The API fills
  the column from Sleeper's roster `starters` (house leagues fall back on `mart_player_availability.is_current_starter`);
  each My Week card carries `status`, `strength`, `in_sleeper_lineup`. Rendering unchanged (IB-3 draws it).
- **Croskey-Merritt on the clone** (Scrubs roster 2, 2026-10-02 build, ESPN fixture: Jefferson Out). Before (main):
  My Week 113.54 (Michael Wilson 9.20 starts at FLEX2, Croskey-Merritt 9.19 bench 3) · Waivers 117.02, weakest FLEX2
  Tuten 9.72, "Claim Alvin Kamara: +0.0 this week at FLEX2, +9.1 over the next 4 weeks" · Team 117.02 "6th of 10",
  closest call "FLEX2, Tuten over Wilson by 0.52" · calculator before 113.54 · his card "on MacZaddy's bench (4 of 5) …
  would have to beat Tuten (9.72), 0.53 more". After: all four 113.54 · Waivers weakest FLEX2 Wilson 9.20 over
  Croskey-Merritt by 0.01, Kamara "+0.6 this week at FLEX1, +9.6" · Team "113.5 — 5th of 10", "FLEX2, Michael Wilson
  over Jacory Croskey-Merritt by 0.01" · his card "on MacZaddy's bench (3 of 3) … would have to beat Michael Wilson
  (9.20)". The review's case (Wilson Out too, `test_ib0`'s `wilson_out`): Croskey-Merritt starts at FLEX2, all four
  113.53; his card "**Justin Jefferson is out (ankle): he starts at FLEX2 this week.**" and "starts at FLEX2 … he is
  a must-start"; Waivers' only drop of him reads "Dropping Jacory Croskey-Merritt costs your lineup 9.2 over the next 4
  weeks" (main: six moves said he "would not start"). Test League roster 10: 95.41 on all four (main: 123.09 on
  Waivers / Team); dynasty 12: 111.15 (the opponent 131.91 → 130.88); MFL 21861 team 4: 116.80 (122.41 off).
- **Evidence**: `api/tests/test_ib0.py` 21 passed (the four-screen equality × {Scrubs, dynasty, Test League, Scrubs on
  demand, MFL} × overlay on / off; the opponent; the cache; Waivers never "would not start" for an overlay starter,
  both paths; the player card, both paths; the trade board; status change / set / close on a frame and on the fixture
  cards: set = Scrubs FLEX2 Tuten, change = dynasty Superflex Penix, close = dynasty RB2 E. Wilson; the drop sentence).
  API suite 290 passed (269 + 21; I0-A's 19 green, parity green); root suite 847 passed, 2 skipped (the clone has no
  `ops.player_prior_oof` / archived schedules); ruff clean; web lint / build clean (types only: `web/src/lib/api.ts`,
  `// ---- IB-0` fields on `DecisionCard`, `Opponent`, `WaiverDrop`, `Waivers`, `Team`). Latency (shared sandbox, cold, Scrubs, overlay on vs off): Waivers ≈ 2.1 s vs 1.2 s, Team
  ≈ 1.8 s vs 0.5 s (9 of 10 rosters touched by the fixture feed; read once, then kept); My Week unchanged.
- **Not covered**: a free agent who becomes worth a claim only because of the overlay (the build's moves are re-priced,
  not re-searched; the next nightly finds him); a player the build sat as Out who is back does not mark another roster
  as touched on Team / the trade board (his own roster's context still re-solves).

### IB-3 2026-10-03 — matchup meaning first, "Value to my lineup", the card's default content (branch `dev/IB3`, clone `league_lab_m1`)

**Why.** The second review (#3, #6, #7): rank numbers led the Matchups screen and ran in opposite directions
(defense #1 = gives up the most, corner #1 = hardest to throw on); a "shutdown" badge said more than a lean of the
targets supports; the Season screen led with "who scores the most", so backup QBs ranked high with no word about
their use to the roster; the My Week cards repeated names and numbers and did not say whether anything had to change.

* **Matchups** (`research.py` IB-3 block: `defense_meaning`, `cb_meaning`; `Matchups.svelte`, `Heatmap … tones`,
  `research.ts`): every defense-vs-position row gets `tone` (favorable / neutral / difficult: the 10 of 32 that give up
  the most / the fewest, the card's reason-line cut), `tough_rank` (1 = gives up the fewest), `rank_words`; every
  cornerback call gets `certainty` (likely / unclear / no call from `call_strength`), `tone` (the named corner's
  quarter; an unclear call only when every named corner is ranked and agrees, else neutral; none when no ranked corner
  is named), the corners with their rank in words ("the 18th-hardest of 74 starting corners to throw on"), `history`;
  both answers `rank_note` ("#1 = the toughest for the offense"). The screen: a tone chip per starter (the word in the
  state color, ▲ / ▼, the rank small and grey under it), the heatmap filled by tone with a three-tone legend, the
  answer in words ("vs IND, who gives up the 2nd-most to RBs: favorable"), each cornerback card with the tone and its
  certainty beside it and no shutdown badge. The mart columns and `app/lib/matchups`' `line` are unchanged (parity).
* **Value to my lineup** (`ondemand.py` IB-3 block: `lineup_values`, `ros_lineup_view`; `GET /api/ros?view=lineup&team=
  &who=all|mine|fa|others`; `Ros.svelte`, `ros.ts`): the ROS screen opens on it when a team is picked (a toggle: Value
  to my lineup · Who scores the most; `?view=points` in the URL), with Everyone / Yours / Free agents / Other teams.
  Definition (METRICS § "Value to my lineup"): the trade engine's ROS board, week by week; one of yours = what the
  lineup loses without him (bench or the best free agent at his position fills in), anyone else = what he adds, nobody
  dropped; one sentence per row. IA-3's pieces, "why this number" and the market line stay on both views.
* **My Week card** (`MyWeek.svelte` card markup, `week.ts`): status chip first (Change needed / Already set / Close
  call — `card.status ?? derived`: close on `is_coin_flip`'s rule, set / change from the lineup rows'
  `is_current_starter` when the API sends it, no chip otherwise), the slot and the strength word (Clear / Lean / Coin
  flip — `card.strength ?? derived`), the call in one line with both names, IA-1's reason (last names), "Compare these
  players" (`/compare?a=&b=`), and the odds / ranges / numbers behind "Why?".

**Numbers** (clone `league_lab_m1`, week 4). Scrubs roster 2, yours by value over weeks 4–16: Washington +38,
McMillan +37, K. Williams +36, Jefferson +35, Hampton +33, Kelce +18, Mahomes +8.9 (a free agent QB is close), Tuten
+4.9, M. Wilson +2.0, then McLaughlin and the Chiefs 0 (a free kicker / defense projects as much: "Starts for you in
12 of 13 weeks left, but the best free agent at K projects as much"), Ferguson 0, Shough 0 ("Your QB2 only plays in
week 5, and the best free agent would score as much then"), Bryce Young 0 ("Your backup QB never starts for you
behind Mahomes"). Everyone: Bijan Robinson +129 (on Run Bijan Run) first. Dynasty roster 12 (superflex): St. Brown
+93, Washington +56, Willis +29 … no bench QB called "QB2". Timings in process: Scrubs 3.1 s cold / 0.4 s warm, dynasty
0.6 s, Test League (on demand) 6.7 s cold. Tones (Scrubs, 160 cells): 50 favorable / 61 neutral / 49 difficult.

**Checks.** `api/tests/test_ib3.py` 19 passed (the cut points and their scaling, the words, the corner rules; on both
house leagues one direction on both routes and a label beside every call; a backup QB below every starter for Scrubs 2
and the Test League; the value machinery; 400 without a team; the saved cards carry change / set / close and the web's
constants equal `cards.py`'s). API suite 288 passed (269 + 19); ruff clean; web lint / build clean; `npm run
e2e:fixtures` 106 passed (100 + 6: `web/e2e/ib3/`, 3 × 375 / 1300). Shared specs follow the new defaults (the ROS tests tap "Who scores the most" or open
`?view=points`; the Matchups answer and the cornerback line in the new words). Fixtures: `web/fixtures/save_ib3_fixtures.py`
(matchups in place from the API's own functions; `ros-lineup_*` from the API in process; `status` / `strength` on the
house leagues' saved cards as IB-0 computes them, `is_current_starter` on the Test League's rows so the web derives).

**Decisions for the PO.** (1) A player of yours is valued against the bench *or* the best free agent at his position
(a lone kicker is worth his edge over the waiver wire); the brief said "the margin over the next-best at his slot".
(2) Anyone else's gain assumes a bench spot (nobody dropped), the trade engine's fill rule. (3) The lineup view is a
`view=` on `/api/ros` (one screen, one route); it needs `team` (400 otherwise). (4) "Who scores the most" stays the
view without a team. (5) Heatmap: the cell's fill is the tone, the number still printed (points a game), ▲ / ▼ in the
cell. (6) The console and `cb_line` keep "#18 of 74, shutdown" (parity); the web composes its own corner lines.
(7) `Heatmap.svelte` (no owner listed) got an additive `tones` prop.

### IB-2 2026-10-03 — Waivers short, the trade builder with the decision in view (branch `dev/IB2`, clone `league_lab_ia3`)

The second review (#5): Waivers ran six desktop screens; the trade builder lost the verdict while you browsed rosters;
nothing showed the waiver alternative before suggesting you give up a useful player.

- **API** (`decisions.py`, block "IB-2", one hook line in `waivers` after I0-A's overlay): `/api/waivers` gains `top3`,
  `views`, `default_view`. *Top 3*: the best-drop claims by lineup gain over the horizon, one per position (two defenses
  compete for one slot), the overlay's "cannot play" and one-QB-per-team rules applied; each `{move, reason, cost, gain,
  gain_label, this_week}`. *One reason* (`_reason`, one fact): the role ("Starts at K this week over McLaughlin (8.1)",
  "Fills your empty RB2 …"), the bye ("Fills your empty DEF in week 5, when Kansas City Chiefs is on a bye" — only when a
  player he could stand in for is away), the stash's role change, the flyer, else the weeks it helps. *Cost*: "Drop X:
  he sits anyway" / "costs your lineup 21.6 over weeks 4–7" / "he starts for you this week" / "No drop: an open spot".
  *Views*: `help` (claims with this week's gain ≥ 0.05, most first, ≤ 8), `bye` (the next week after this one where a
  bye leaves a starting slot empty — `mart_league_roster_horizon` / the on-demand solve's `role = 'empty'` — and the
  claims that gain most that week; else "Your bench covers every bye through week N" + the cover claims), `stash` /
  `all` (counts; the lists are the existing `upside` and `free_agents`). **One answer carries every view** (my call, not
  `view=`): a chip switches with no request (instant on a phone, the on-demand league solved once, one cache entry per
  position, the saved fixtures one per position as before). *The alternative before a drop*: every move object in the
  answer (top 3, views, `moves`, `cards`) whose drop starts this week or next gets `drop_starts {weeks, slot, text}` and
  `keep_alternative {move, line}` — the best claim at the same position whose drop sits (or needs no drop), from the
  full add × drop table the sweep already priced: "Or drop Croskey-Merritt instead (he sits) and keep Kansas City
  Chiefs: +9.7 over weeks 4–7"; none: "No free agent at DEF helps without dropping a starter …". "Starts" = this week
  the lineup My Week shows (`cards.lineup_rows` / `anyleague.lineup_rows` + `availability.apply_to_rows`: a player who
  starts because a teammate is Out counts), next week the horizon's solved lineup (`_starts_soon`; IB-0's
  `roster_context` replaces its first half in integration).
- **Web**: Waivers = the answer (the first move's sentence) + one lineup line (Wave G's four tiles folded into it) → the
  three moves (`ClaimCard.svelte`: the claim, the gain, one reason, the cost, the warn box with the alternative) →
  `Chips` Help now · Bye coverage · Stashes · All available (`?view=`, rewritten in place; the default leaves the URL)
  → the view → "How to read this". `?add=&drop=` (the pane's "Evaluate add / drop") shows that claim first, or picks the
  free agent in All available. Wave G's `MoveCard.svelte` and the "more claims" expander are gone (Help now is that
  list). Trade calculator: the decision first (the dial's row: the dial, the four lineup-impact tiles, the verdict);
  once it scrolls away a **verdict bar** is pinned to the top (the package in last names, the dial's label + score,
  "You +x"; open on desktop, a tap opens it on a phone); "Why?" (the headline, market, rest of season, ranks, roster
  size, week by week) and "Lineups" (yours, theirs under its own expander) collapsed. Trades' partner cards: the
  package, "They: <label>", your gain over the window, one reason (`partnerReason`: who cannot play, who starts for you
  this week, or when the gain comes), Try it (Wave G's two bars and the market line dropped). The research pane:
  `decisions.ts` imports IB-1's `lib/pane.svelte.ts` through an eager `import.meta.glob` (a static import when the
  file exists, `{}` when not — this branch builds without it): `paneAt` on the claim cards' and partner cards' names,
  `openPlayer` on a free agent's row on a phone (desktop keeps the detail beside the list) and on a name in the
  calculator's roster lists ("Add to trade": `{from: "trade", sleeper_id, side, partner}`); without the pane the links
  stay links.
- **Evidence** (this clone; the API suite's overlay off unless said): Scrubs roster 2 — top 3 Allgeier (RB, +9.85, "Fills
  your empty RB2 in week 7 …", drop Croskey-Merritt: sits), New York Giants (DEF, +9.66, drop Kansas City Chiefs: he
  starts this week → "Or drop Croskey-Merritt instead (he sits) and keep Kansas City Chiefs: +9.7 over weeks 4–7"),
  Daniel Carlson (K, +4.03, drop McLaughlin: starts this week and next → keep him, drop Croskey-Merritt: +4.0); Help
  now 8 (Reichard +2.21 this week first); Bye coverage week 5: the DEF slot empty (the Chiefs' bye), 8 DEF claims
  (Falcons +8.3 that week); 4 of the 50 paged moves drop a starter, all 4 carry the line. Overlay case (Jefferson +
  Michael Wilson forced Out): Croskey-Merritt starts this week, so every claim dropping him gets the warning and the
  keep-him alternative; with the overlay off none does. Test League roster 9 (on demand): every claim drops Marvin
  Harrison Jr., who sits — no line; with the WR / TE starters ahead of him forced Out, each says he starts and offers
  the alternative; in the web fixture (the ESPN fixture's overlay on: Mayfield Out) the top claim is C.J. Stroud for Kyler
  Murray, who starts — with "Or drop Harrison Jr. instead (he sits) and keep Murray: +22.1 over weeks 4–7". Dynasty 12 /
  Test League 3: nothing to claim (`top3` empty, Help now says the notice). Page length
  (default view): phone 375 × 812 — the chip row at 1113 px (Scrubs), 989 (Test League 9), 363 (dynasty), the bound
  1624; desktop 1300 × 900 — Scrubs 2001 px tall (2.2 screens; the review counted six). Latency: `views_ms` 150 ms
  (house), the on-demand starters re-use the league solve.
- **Checks**: `api/tests/test_ib2.py` 7 (the alternative and its "none" line on a constructed table, one reason = one
  fact, the top 3 / views / alternative on Scrubs against `mart_waiver_moves` and `mart_league_roster_horizon` read
  independently, every Scrubs roster's invariant, dynasty's nothing, the Test League on demand with and without forced
  Outs, the overlay case); API suite 276 passed (269 + 7); ruff clean; web lint / build clean; fixture e2e 114 (100 + 14:
  `web/e2e/ib2/`, 7 × phone at 375 × 812 and desktop) — Wave G's waivers test, H1's stash tests (`&view=stash`) and
  IA-2's calculator tests (the chip is in the verdict bar; the lineups open from "Lineups") follow the layout.
  Fixtures: `web/fixtures/save_ib2_fixtures.py` merges `top3` / `views` / `default_view` and the two move fields into
  the saved waivers answers (nothing else in them changes) and saves `waivers_9000000000000000001_9_ALL.json` whole.
- **Found**: `html, body { overflow-x: hidden }` (`app.css`) makes `body` the sticky container, so `position: sticky`
  never sticks on any screen (ListDetail's `wide:sticky` detail included; IA-2's bottom chip only ever showed in
  place). The verdict bar uses `position: fixed`; `overflow-x: clip` would fix sticky everywhere (a design-system call
  for the PO, DESIGN.md says so). The fixture savers' `os.environ.pop("LEAGUE_LAB_ESPN_FIXTURES")` is undone by
  `settings.py`'s `load_dotenv(override=False)` when the worktree's .env sets it: IA-2's saved answers were taken with
  the overlay on; `save_ib2_fixtures.py` sets the ESPN fixture explicitly so it reproduces.

## Wave I-C (Iteration 17, part C)

### PO merge — Wave I-C, 2026-10-03 (Saturday, 13:30–15:30 ET)

* **Why**: Andrew's dad's league (MFL 70587, "Make Football Great Again") pulled in but the tool "basically doesn't
  work for him" — `TMQB / RB / RB / WR+TE ×3 / TMPK / Def` read as "2 RB, DEF", a 15-point lineup, every WR "Can't
  play", and its scoring (TDs by distance 6 / 9 / 12, `1/10` yards, +10 bonuses at the league's own thresholds, FG
  3 / 5 / 10 / 15, team units) compiled to an **empty** `scoring_settings`. He also suspected the scoring of his own
  two leagues. Plan § 17 "Third: dad's league" has the diagnosis.
* **Delivered** (four Opus devs in parallel, 40–60 min each): **IC-1** `scoring.ScoringSpec` — the rules as data per
  position (rates, flat bands, TDs and kicks by distance, MFL's whole-unit steps, premiums; `from_sleeper`,
  `from_mfl`, `rules_for` for the units, JSON round trip, `readback()`), exact pricing of actual lines
  (`price_detail`), expected-value pricing of projected lines (`expected_frame`: bands at their probability, distance
  bands at the measured share of TDs that long, `1/10` at the expected whole tens), the scoring check
  (`scoring_audit.check` → `GET /api/league/scoring-check?league=&week=`: our points against the platform's own for
  every rostered player, misses named with the rule, the SQL macro compared on house leagues). **IC-2** slots as
  eligibility sets (`lineup.Slot(label, type, elig, order)`: Sleeper names, `A+B[+C]`, `TMQB` / `TMPK` / `TMDEF`),
  team units as players (`mfl:0656` "Cincinnati Bengals QB", priced from the team's starting quarterback's line /
  the team's kicker; unrostered units on Waivers), MFL starters seated in the slot that admits them, "No slot for a
  K in this league" apart from "Can't play". **IC-3** the 70587 fixtures (`api/tests/fixtures/mfl/70587/`), the
  Leagues card's read-backs (`ondemand.league_card`: lineup, scoring, not priced, approximated, the check) on the MFL
  card and every Sleeper row, the audit of Scrubs and the dynasty (below), the e2e. **M2** `scoring_ev`: threshold
  curves (gamma for rushing / receiving yards and receptions, normal for passing yards, fitted on 39,622 out-of-sample
  player-weeks 2019–2025), TD-distance shares measured on every TD play (`fct_play`: receiving ≥10 0.548 / ≥40 0.119,
  rushing 0.259 / 0.062, passing 0.547 / 0.120; defensive and return families; FG bands 0.567 / 0.271 / 0.157 /
  0.005), `expected_floor_units` for "1 per whole 10", the backtest (dynasty: top-6 weekly bias RB +1.34 → +0.31, WR
  +1.65 → +0.70; season-total MAE better at every position; weekly MAE +0.01–0.03), seed `scoring_distributions.csv`.
* **The audit of Andrew's two leagues (IC-3, the answer to "some issue between scoring and settings")**: our points
  equal Sleeper's to the tenth for **285 / 285** Scrubs and **580 / 580** dynasty player-weeks in 2026 weeks 1–2, and
  for 14,624 of 14,629 over 2024–2025 (the five: a long-TD bonus on a lateral credited to the first receiver, a
  special-teams fumble recovery Sleeper pays and we do not price, a 5-yard stat correction); the SQL macro agrees on
  every row. **The scoring is right. What is off is the dynasty's projections**: its +3 / +6 yardage bonuses and the
  +2 long-TD bonus are priced all-or-nothing / at 0 on a projected line — starters earned 115 bonus points in weeks
  1–2 (~4.8 a lineup a week), the projections priced almost none, concentrated on the stars (M1's +1.19 top-6 RB
  bias is this). Expected-value pricing closes it (M2) and stays **off for Sleeper leagues** (`LEAGUE_LAB_EV_PRICING`)
  until the nightly prices with the same engine, so the player page, Trends and the record (the nightly's
  `proj_points`) never disagree with My Week (the on-demand `price_lines`) — the next modelling task (v3.1). MFL
  leagues always price in expectation: they have no nightly to agree with.
* **PO**: merges IC3 → M2 → IC1 → IC2 (doc conflicts kept both; no code conflicts). Then: (1) **the 10-yard TD cut
  in dbt** — `int_player_game_pbp` → `fct_player_game` / `fct_player_game_league` / `league_player_week` carry
  `pass/rush/rec_tds_10p` next to `_40p` / `_50p` (rebuilt here: 3,084 / 5,632 receiving TDs ≥ 10 yards 2019–2025 =
  M2's 0.548), and IC-1's `fct_play` lengths query is gone — `hosted_relations.py` had put `analytics.fct_play`
  (233 MB) in the API's closure, which would have blown the hosted copy's 480 MB budget; the check reads the counts
  (70587 week 1: 161 / 163, week 2: 155 / 156 within a point; the misses are defensive return touchdowns, whose
  length no team line carries). A copy built before this change approximates the < 40 split and says so. (2) **The
  read-back names the stat and the position of every rule** (IC-3 found "10 yards a point" for Scrubs' 1-per-25
  passing): 70587 → "TDs by distance 6 / 9 / 12 (0–9 / 10–39 / 40+ yards) · 1 pt per 10 rushing / receiving yards ·
  1 pt per 20 passing yards · +10 at 75 rushing (QB/WR/TE) / receiving (TE) · +10 at 100 rushing (RB) / receiving
  (RB/WR) · +10 at 250 passing · INT −3 · fumble lost −3 · FG by distance 3 / 5 / 10 / 15 · DEF points allowed 0 →
  10, 1–3 → 8"; the spec says return touchdowns and 2-point conversions are not projected. (3) **Double headers**:
  70587 plays twice in weeks 2, 4, 6–9, 11 and 13 — `anyleague.opponent` carries the second opponent in `also`, the
  on-demand My Week runs both through the overlay, the header reads "Week 4 vs **Big Mac Attack** and **Klaby Crew**
  (a double header) — they project 115 and 114 — you project 83". (4) The old I0-B `mfl_scoring_note` (the "Sleeper
  bonus … extended" sentences, now wrong) reads the spec's words. (5) M2's seed wired (`dbt/seeds/schema.yml`,
  `metric_registry` row `expected_value_pricing`). (6) IC-1's test-only id table folded into the shared
  `fixtures/ff/db_playerids.csv`. (7) `api/tests/test_ic_po.py` (5). Checks: **root 968 passed** (848 before), **API
  353** (316), **web lint / typecheck / build clean, 134 fixture e2e** (130), ruff clean; the 70587 e2e answers
  re-recorded from the merged API (`IC3_RECORD`). QA walk (fixtures, overlay on): the card's read-backs and "Week 2
  check: we match your league's points for 155 of 156 players within 1 point"; Knight Train's week = 8 slots in the
  league's words, team QB 29.00 (Burrow's line in dad's scoring: 250 yards → 12 whole twenties, 1.7 TDs at the
  measured 8.0 a TD, −2.1 INT, +5 for the 250-yard bonus at even odds), team K 10.02, RB2 empty with the reason (Hall
  and Price Out in the ESPN fixture), the double-header line, a "Change needed · team QB" card.
* **Decisions kept**: TMQB = the starting quarterback's line, not the team's sum (IC-2 measured the sum over-counts
  KC 29.2 vs Mahomes 22.8); MFL's `1/10` priced at the expected whole tens (M2: linear was 0.3–0.5 a stat a game
  high); flat bonuses by probability for MFL specs always, Sleeper specs behind the flag (above); the spec travels
  in the league dict as `scoring_spec` next to the flat `scoring_settings` every old reader keeps; `scoring_report`
  gains `priced` / `approximated` / `unpriced`.
* **Open**: the nightly on the spec (then EV pricing on for Sleeper leagues, the harness re-run — v3.1); the
  rest-of-season table has no unit rows and the Team Hub's slot strength names a unit without its team (IC-2); a
  defensive touchdown's distance is priced at its expected value on actual lines; QB passing-yard bonuses project
  20–30% high in 2023–2025 (the QB line itself, M1's list); the hosted copy carries the `*_tds_10p` columns from the
  next nightly (until then 70587's check says "approximated" for the 10–39 band).


### IC-3 2026-10-03 — dad's league fixtures, the Leagues card tells the truth, the audit of Andrew's two leagues

* **70587 fixtures** (`api/tests/fixtures/mfl/70587/`): MFL's own answers, byte for byte, fetched read-only through the
  browser pane (league, rules, rosters, schedule, standings, weeklyResults 1–3, liveScoring 4); the 177 players they
  name (rosters + every player in those results, units included) appended to the shared `fixtures/mfl/players.json`
  (216 → 260 ids, every old id kept). Facts for the readers: the rules' groups are `QB PK WR RB TE Def` (the units
  score by QB / PK), bonuses differ by group (QB PY 250 / RY 75; RB RY 100 / CY 100; WR RY 75 / CY 100; TE RY 75 /
  CY 75), `precision 0`; **weeks 2, 4, 6–9, 11, 13 are double headers** (12 matchups: each franchise twice).
* **The card** (`ondemand.league_card`, on `/api/leagues?mfl=` and on every `/api/leagues?username=` row): the lineup
  League Lab solves read back in the league's own words (`Your lineup: TMQB · 2 RB · 3 WR/TE · TMPK · DEF` once IC-2's
  slots are in; before, the starters it could not read are named: "Not in the lineup League Lab solves: TMQB, WR/TE,
  TMPK."), the scoring in one line (IC-1's `ScoringSpec.readback()` when present, else the flat settings), what is
  not priced, how the projections handle the scoring (the dynasty's long-TD and all-or-nothing yardage bonuses said in
  words), and the scoring check (IC-1's `/api/league/scoring-check`, loaded by the web after the card shows; "not
  available for this league yet" until then). Web: `Leagues.svelte` (snippet `readback`), `leagues.ts` (types,
  `checkLine`, `missLine`).
* **Audit** (the answer to "some issue between scoring and settings"): Sleeper's points vs `compute_points` on
  `fct_player_game`, 2026 weeks 1–2: Scrubs 285 / 285, dynasty 580 / 580 within 0.1; SQL macro = Python on all 716
  priced rows; 2024–2025: 14,624 / 14,629 (misses: a long-TD bonus on a lateral credited to the first receiver ×2,
  an unpriced `st_fum_rec`, a 5-yard stat correction). The gap is in the projections: dynasty starters were paid 115
  bonus points in weeks 1–2 (87 yardage, 28 long-TD); projections priced 9 (none of which hit). Pinned by
  `api/tests/test_ic3.py::test_audit_house_leagues_weeks_1_2_match_sleeper`.
* **E2E** `web/e2e/ic3/` on `web/fixtures/mfl/api_70587.json` (the API's answers, recorded with `IC3_RECORD=<api>`
  from a trial merge of dev/IC3 + dev/IC1 + dev/IC2 + dev/M2 — code merged clean, docs only conflicted): paste 70587
  → card ("Your lineup: TMQB · 2 RB · 3 WR/TE · TMPK · DEF"; "TDs by distance 6 / 9 / 12 · 1 pt per 10 yards · …";
  "Week 2 check: … 155 of 156 players within 1 point") → Knight Train → My Week 8 slots (team QB Bengals 29.0, RB1
  Hubbard 10.97, RB2 empty — Hall and Price Out —, WR/TE Egbuka 9.48 / Robinson 7.36 / Fannin 5.85, team K Chargers
  10.02, DEF Lions 10.26 = 82.94) → Team / Waivers / Season answer; a Sleeper row's card. 375 (phone) and 1300 px.
  IC-1's check on the trial: Scrubs weeks 1 / 2: 146 / 146, 144 / 144; dynasty 219 / 219, 228 / 228 (SQL = spec on
  every row); 70587: 161 / 163, 155 / 156 within 1.

### M2 2026-10-03 — the numbers expected-value pricing needs (branch `dev/M2`, clone `league_lab_m1`)

* **What.** New `src/league_lab/scoring_ev.py`, pure and fitted offline. The constants live in the module; the seed
  proposal `dbt/seeds/scoring_distributions.csv` (272 rows) is generated from them and pinned by a test. It has:
  `prob_at_least(stat, position, mean, threshold)`, `prob_in_band` (high inclusive), `expected_band_points`,
  `has_curve`, `td_distance_share(family, position, low, high)`, `td_survival`, `expected_td_distance_points`,
  `td_share_source`, `expected_floor_units` (MFL's "1 per whole 10" in expectation), `sleeper_expected_bonus(_frame)`
  (Sleeper's bonus keys in expectation); `run_fit()` (the PO moved it to `scoring_ev_fit.py`: its play-table SQL
  would have put `analytics.fct_play` in the hosted closure). Methods and every table: METRICS § "Expected-value
  pricing".
* **Threshold curves.** Gamma for rushing and receiving yards and receptions (shape k0 + k1 × mean); normal for
  passing yards (sd 79). Both are monotone in the mean by construction. They are fitted on the walk-forward lines of
  2019–2025 (39,622 player-weeks, `calibration.oof_rows(lines=True)`; `ops.calibration_oof` holds points only, so
  the lines were rebuilt, about 45 s a season) by log loss at the thresholds leagues use. Out of sample (fitted
  2019–2022, scored 2023–2025) they match or beat M1's isotonic curves at every position × stat, and they work at
  any threshold (70587's 75 and 250).
* **TD distances are measured, not placeholders.** `analytics.fct_play` (in every clone) has each TD's
  `yards_gained`, the definition dbt uses for `*_tds_40p`, and reproduces `fct_player_game`'s TD and 40+ / 50+ counts
  exactly. Survival shares at 5–80 yards per family × position, 2019–2025: receiving ≥ 10 / ≥ 40 = 0.548 / 0.119
  (WR 0.604 / 0.166, TE 0.432 / 0.035); rushing 0.259 / 0.062 (RB 0.258 / 0.071); passing (QB) 0.547 / 0.120;
  interception returns ≥ 40 = 0.494; fumble returns 0.309; punt and kick returns ≥ 0.9. The spec's pooled
  `return_tds` and `def_tds`, and `fg_made` (made FGs by distance: 50–59 0.157, 60+ 0.005), are there too. The plan's
  fallback rushing 0.35 and passing 0.60 / 0.14 are high.
* **Does it help** (dynasty scoring, 2023–2025, curves fitted on earlier seasons only). The top-6 weekly bias goes
  RB +1.34 → +0.31, WR +1.65 → +0.70, TE +0.91 → +0.65 and QB +0.07 → −1.39. Weekly MAE is +0.01 to +0.03 and
  Spearman ±0.001. Season-total MAE per player goes QB 24.1 → 23.3, RB 17.6 → 16.9, WR 18.4 → 18.3 and
  TE 12.8 → 12.6 (top 24: −0.6 to −5.9 in 11 of 12 buckets). Expected bonuses match those paid at RB / WR / TE
  (0.217 / 0.205 / 0.053 per row expected, against 0.203 / 0.193 / 0.045 paid); QB passing comes out 0.55 against 0.42 (the
  QB line runs high in 2023–2025). In a 70587-style scoring with floor-aware yards, weekly bias over all rows is
  within ±0.20 at every position and season-total MAE falls 1.6–6.6 against flat pricing.
* **For the PO.** (1) **Yes: turn EV pricing on** for projected lines in leagues with flat bonuses, distance TDs or
  whole-unit rates; leagues without them are unchanged. The QB top-6 bias it exposes is the QB model's (M1's v3.1
  list). (2) IC-1: price `per_unit_from` with `expected_floor_units`; linear is high by 0.3–0.5 per yardage stat per
  game. (3) Wire the seed in `dbt/seeds/schema.yml` (proposal in the hand-back) or leave it unread: the module never
  reads it.
* **Tests.** `tests/test_scoring_ev.py`, 52 passed. They cover: the seed equals the constants; every curve is
  monotone on a 2,500-point grid × 16 thresholds; edges and shapes; partitions; the fitter recovers a known gamma and
  a known normal; thin positions pool; TD shares partition and decrease; aliases (TMQB, Def, MFL codes); shrinkage;
  the description parser; floor units; Sleeper bonus pricing per row = per frame; the pooled families; FG bands.
  Ruff clean; root suite 899 passed, 2 skipped.

### IC-1 2026-10-03 — a real scoring engine, and the scoring check that proves it (branch `dev/IC1`, clone `league_lab_i0a`)

Andrew: "We need to make this more dynamic to accommodate more league types and scoring settings", and "I think
there's some issue between scoring and settings with my two leagues too". Design and contract: docs/METRICS.md §
"Scoring spec"; docs/ANY_LEAGUE.md § "Scoring".

* **The spec.** `scoring.ScoringSpec`: per position `rates`, `bands` (flat once in a range), `distance` (per play by
  its length: TDs, FG), `steps` (MFL's `a/b`, whole units), `premiums`; `unpriced` with the platform's code and name;
  JSON round trip; `rules_for` (units: TMQB → QB, TMPK → K, TMDEF / Def → DEF); `readback()` in plain words. Compilers
  `from_sleeper` (every key the app has seen; the rest unpriced by key) and `from_mfl` (`*x`, `a/b`, `thresholdPoints`,
  plain `n` in a range, the TD families PS RS RC PR KO DR FR (IR BF MF BP for the defense), FG bands and by the yard,
  TPA bands, FC / IC / SK / SF / FF / BLK, position groups). 70587 compiles with nothing unpriced.
* **Pricing on the spec.** `price_detail` / `compute_points_spec` (actual lines: exact; TD lengths from play-by-play,
  else exact at 40 / 50 and the < 40 split approximated and said); `expected_frame` / `expected_points` (projected:
  linear rates, MFL's whole units at their expectation, bands at their probability, distance by the share of TDs that
  long; M2's `scoring_ev` imported guarded, the marked fallback tested). `anyleague` (marked `IC-1` blocks):
  `league_scoring` carries the spec, `league_spec`, `price_lines` (Sleeper spec: the flat path bit for bit; MFL: in
  expectation), `kd_values` (`kd_flat`), `_mapped` / `_scoring_key` (an MFL spec never borrows an exact reference),
  `scoring_report` (+ `priced`, `approximated`, `unpriced`); `mfl_client.scoring` adds `spec` to its report and fills
  the flat summary; `why.weights` reads the position's rules for a non-Sleeper spec; `kdef.price` takes a spec
  (`kd_flat`), so the rest-of-season K / DEF path prices an MFL league's kickers and defenses by its rules too.
* **Checks.** ruff clean; root 884 passed, 2 skipped; API 325 passed, 2 skipped; live on :8741 (app role): Scrubs
  week 2 144 / 144 (111 ms), dynasty week 1 219 / 219, Test League week 2 144 / 144, `mfl:70587` weeks 1 / 2
  162 / 163 and 156 / 156 (100–150 ms). Web untouched.
* **The scoring check.** `scoring_audit.check` and `GET /api/league/scoring-check?league=&week=` (cached a day).
  Weeks 1–2 of 2026 (the clone's complete weeks; week 3 is Thursday only and answers `n: 0` with the sentence):

  | League | Week 1 within 1 / n (within 0.1) | Week 2 | SQL macro agrees |
  |---|---|---|---|
  | League of Scrubs (Sleeper) | 146 / 146 (146) | 144 / 144 (144) | 136 / 136, 133 / 133 |
  | Forever Unclean Dynasty (Sleeper) | 219 / 219 (219) | 228 / 228 (228) | 219 / 219, 228 / 228 |
  | Test League (fixture, by construction) | 151 / 151 (151) | 144 / 144 (144) | — |
  | MFL 70587 "Make Football Great Again" | 162 / 163 (161) | 156 / 156 (155) | — |

  The one 70587 miss: Kansas City's defense, MFL 14 vs ours 12, `likely_rule` "count:sacks" (one sack more in MFL's
  count than nflverse's team line). The two 0.6 gaps: a defensive TD's distance (priced at its expected 9.6; no
  length for return TDs). Every 70587 player, TMQB (22 a week) and TMPK (12) line is exact — the spec reads dad's
  rules right: no PPR, whole tens (`floor(v / 10)` from 0, not from the range's low), 6 / 9 / 12 by length, the
  position thresholds, FC = fumbles recovered.
* **Andrew's two leagues.** The actual points are right to the cent in both, for every rostered player, and the SQL
  macro agrees with the spec everywhere. What does not follow the settings is the **projection** of the dynasty's
  bonuses: its long-TD bonuses (+2 at 40+ yards) price 0 on a projected line and its yardage bonuses are
  all-or-nothing on the projected mean. Priced in expectation (`LEAGUE_LAB_EV_PRICING=1` with M2's curves and shares,
  week 4): the dynasty's top 24 move QB +1.09, RB +0.53, WR +0.76, TE +0.20 a week (Josh Allen 30.24 → 31.68, Bijan
  Robinson 26.72 → 25.52: his 100-yard bonus was all-or-nothing). Scrubs has no bonuses: identical.
* **Tests.** `tests/test_scoring_audit.py` 5 (the check's counts, misses, `likely_rule`, words, unit sums);
  `tests/test_scoring_spec.py` 32 (70587 hand-computed: RB 120 yards + a 45-yard TD = 43, QB 45, WR / TE
  thresholds, K 36, DEF; 21861 TE 1.5 and FG by the yard; IDP / unknown events unpriced; thresholdPoints; parity on
  `tests/test_scoring.py`'s rows and 2,000 random lines × 3 scorings; JSON; read-back; EV monotone; the fallback with
  M2 absent; the 10-yard cut; Sleeper keys beyond the flat engine — completions, attempts, carries, first downs,
  25+ completions — priced on actual lines and shown as SQL disagreements, never silently). `api/tests/test_ic1.py` 11 (the route for both house leagues weeks 1–2 with the SQL
  twin, default week, week 3, the Test League, 70587 weeks 1–2, 404, the MFL league's spec and report, `price_lines`
  on the MFL spec + house parity). Both files also pass with M2's `scoring_ev.py` copied in (not committed).
* **Fixtures.** `api/tests/fixtures/mfl/70587/` and `mfl/players.json` copied from IC-3's worktree unchanged;
  `fixtures/ic1/db_playerids_70587.csv` (the id table trimmed to 70587's 147 mapped players); the Test League's week 1–2
  matchups gain `players_points` (`fixtures/make_ic1_fixtures.py`: the pre-spec flat engine on `fct_player_game`).

### IC-2 2026-10-03 — slots as eligibility sets, team units as players (branch `dev/IC2`, clone `league_lab_i0b`)

Dad's league (MFL 70587) starts `TMQB ×1, RB ×2, WR+TE ×3, TMPK ×1, Def ×1`; the translation kept `RB` and `Def`, so
the app read "2 RB, DEF", seated a started TE at RB2, called every WR and both team units "Can't play".

- **Slots** (`lineup.py`, `# ---- IC-2`): `Slot(label, type, elig, order)`; `slot_eligibility(name)` reads Sleeper's
  names, generic `A+B[+C]` (the union of the parts; an IDP part = not modelled, reported), `TMQB` {TMQB}, `TMPK`
  {TMPK}, `TMDEF` {DEF}; `SLOT_ELIGIBILITY` answers any of them on lookup, so waivers / trades / availability / the
  Team Hub read MFL slot types unchanged. The solver uses `slot.elig`. A player no slot admits: reason "No slot for a
  K in this league" (was "no K slot in this lineup"), role still `unplayable`, `Lineup.no_slot` / `cannot_play`,
  not counted in `n_unplayable`; listed as "No slot" (`cards.no_slot_or_cant`, My Week's full list).
  `align_starters`: MFL's starters seated by a maximum matching in the narrowest slot that admits them (Sleeper's
  `starters` array order), so the lock rule reads the right slot.
- **MFL translation** (`mfl_client.slot_name` / `slots`): the league's own words (`TMQB`, `WR+TE`, `TMPK`; `PK` → `K`,
  `Def` → `DEF`); note gains `units`. `platforms.MFLLeagues`: a rostered `TMQB` / `TMPK` id → a directory row
  `mfl:<id>` (position, Sleeper team code, "Cincinnati Bengals QB", `unit: true`, no gsis; `mfl_mapped_by.unit`);
  every other team's unit registered as `mfl:TMQB-<team>` for the free agents; `scoring_spec` carried for IC-1.
- **Pricing** (`anyleague.py`, `# ---- IC-2`): `kd_starts` / `unit_starts` from the slots' sets; `price_units` →
  `Priced.units`: TMQB = the line of the team's best-projected quarterback who can play, priced through `price_lines`
  with `position = "TMQB"` (IC-1's spec: QB's rules), range = the starter's shifted; TMPK = the team's kicker from
  `kd_values`. `LineupInputs.unit_proj`; `_proposed_player`: a unit is valued by (unit, team), can't play only on a
  bye. `free_agents` keeps units (one per unit and team); Waivers prices them (`decisions._free_agents`, IC-2 block).
  `_cards_frame`: a unit's team and range.
- **Web / app**: `cards.slot_label` "WR/TE 1", "team QB", "team K"; `cards.slot_elig` (the solver-free copy);
  `LineupTable.svelte` shows a unit's team badge.
- **Evidence** (70587 fixture from IC-3, week 4, availability overlay off as in the tests; scoring = I0-B's compiler,
  IC-1 replaces it): team 1 "Knight Train" before (base `7cd51b9`) 3 slots RB / RB / DEF, Fannin (TE) locked at RB2,
  5 WR / TE and 3 units "Can't play", 13.34; after 8 slots: team QB Cincinnati Bengals QB 8.48 (= Joe Burrow's line
  alone, 8.48), RB Jadarian Price 3.02, Breece Hall 2.97, WR/TE Egbuka 2.44, Burden 1.40, Fannin 1.10 (locked), team K
  Los Angeles Chargers K 10.02 (= the LAC kicker's 10.02), DEF Detroit 9.22 = 38.65; bench TB QB unit 7.72, Hubbard,
  Ferguson, Robinson, Mumpfield; can't play Lane (NFL IR) only. Free agents: 30 units (64 − 34 rostered). TMQB rule:
  the backups' lines are not near 0 on the week-4 board (KC summed 29.24 vs Mahomes 22.78; ATL 30.35 vs Penix 17.22),
  so the default is the starter's line (`UNIT_QB_RULE`), the sum available as `unit_lines(rule="sum")`.
- **Tests**: `tests/test_lineup_ic2.py` (31: parse_slots for 70587 → 8 slots, eligibility table, solve seats the
  units / RBs / WR+TE / DEF, no WR without a slot, no-slot words, Sleeper names unchanged, locks, align_starters, MFL
  slot names, the cards copy and words); `api/tests/test_ic2.py` (8: the translation, units as players, free units,
  My Week 8 slots with the units priced, Waivers' units, the rosters route and the Team Hub, a house league unchanged,
  every route on 70587). `tests/test_lineup.py`: the no-slot reason's new words (3 lines).

## Wave I-D (Iteration 17, part D)

### PO merge — Wave I-D, 2026-10-03 (Saturday, 16:00–17:45 ET)

* **Why**: Wave I-C left three threads: expected-value pricing proven but off for Sleeper leagues because the
  nightly still priced flat (two numbers for one player otherwise); the team units half-done past My Week; the
  player news line from Andrew's first review. Andrew: "keep plowing forward".
* **Delivered** (three Opus devs in parallel, 40–80 min each): **M3** one pricing entry point for projected lines,
  `scoring.price_projected(stats, scoring, position, *, ev=None)` (`pricing_engine` → `flat` / `ev` / `spec`): the
  nightly's `projections.price` (every `proj_` path: `predict_position`, `_oof_lines`, `_line_points`, `house_rows`,
  `calibration.oof_rows`, signals' what-ifs) and the request side's `anyleague.price_lines` call it, so the flag
  moves both at once — pinned bit for bit on 500 week-4 lines for the dynasty, Scrubs and the Test League under
  either flag state (`tests/test_projections_ev.py`, 19); actual (`out_`) lines stay exact; `projected_view(flat)`
  keeps the flat engine's keys so only *how* a bonus is priced changes. The harness both ways (`oof_rows`, 2023–2025,
  17.5 min a run): flag off reproduces all 432 stored v3.0 backtest cells to 0.0; flag on leaves Scrubs identical to
  the bit and moves the dynasty — season-total MAE QB 24.1 → 23.3, RB 17.6 → 16.9, WR 18.4 → 18.3, TE 12.8 → 12.6;
  top-6 weekly bias RB +1.34 → +0.36, WR +1.65 → +0.74; coverage unchanged; weekly MAE +0.007 … +0.041
  (METRICS § "Expected-value pricing" → "On the nightly"). **IC-4** units everywhere: rest-of-season rows per unit and
  NFL team (`unit_window`, each week priced by that week's starter; 32 + 32 rows; "Value to my lineup" against the 30
  free units), a unit's card = its starter's card named as the unit ("Cincinnati Bengals QB — priced from Joe
  Burrow's line"), the Team Hub's slot strength with the unit's team and badge, the League screen's matchups with
  both games of a double header (all-play counts a team once a week; the record every game; `/api/record` for MFL
  = the league's results + records, equal to MFL's standings for all 12 teams), MFL manager names when the export
  carries `owner_name` (70587 / 21861 / 10015 do not: null, not the team name repeated), Waivers' Help now puts the
  claim that fills an empty starting slot first ("Fills your empty RB2 this week."). **N1** the news line:
  `news_feed.py` on ESPN's public fantasy news endpoint (`site.api.espn.com/apis/fantasy/v2/games/ffl/news/players?
  playerId=`; headline / date / source / url only, cached an hour or 15 min on game days, 60/min, `LEAGUE_LAB_NEWS=off`,
  an outage = no line) → `/api/player` `news` (≤ 3, ≤ 14 days) → one line under Availability on the page and in the
  pane ("**News** · 2 h ago · *headline* · RotoWire via ESPN ›", link out to espn.com); `docs/ESPN_TERMS.md`.
* **PO**: merges M3 → IC4 → N1 (doc conflicts kept both; `api.ts` both blocks). dbt's
  `assert_projection_ranges_price_the_lines` now re-prices `scrubs` only — the dynasty's bonuses are priced at their
  probability under the flag, which the SQL macro cannot express (the Python parity test covers it). Checks: **root
  987 passed** (968 before), **API 380** (353), **web lint / typecheck / build clean, 150 fixture e2e** (134), ruff
  clean. QA walk (fixtures, overlay on): Jefferson's pane shows the news line with the 110-character cut and the
  source; `/api/ros?position=TMQB` on 70587 = 32 team-QB rows with "Priced from Dak Prescott's line"; Waivers' top 3
  for Knight Train leads with "Fills your empty RB2 this week."; the League screen's week 4 = 12 games, Knight
  Train's two first.
* **The flag stays off this weekend.** `LEAGUE_LAB_EV_PRICING` flips **Monday** (never the morning of a game day),
  in this order so the two sides never disagree for more than the length of one nightly run: (1) add
  `LEAGUE_LAB_EV_PRICING: "1"` to the nightly's env in `.github/workflows/nightly.yml` and run it by hand
  (`workflow_dispatch`; ~20 min: the board is re-priced and published); (2) add the same env var to the Render API
  service (`render.yaml` `envVars`, a redeploy); week 4 is frozen and keeps its flat rows, so **week 5 is the
  record's first EV-priced week**. Expected: Scrubs, the Test League and every bonus-free league unchanged to the
  bit (0 of 8,134 player-weeks move); MFL unchanged (already in expectation); the dynasty's top 24 +0.66 a week
  (QB +1.01, RB +0.71, WR +0.73, TE +0.18), rest of season +8 to +12 for the top 24 (Josh Allen 30.24 → 31.68, ROS
  281 → 291; Puka Nacua 18.22 → 19.65; a line already past a threshold drops: Bijan Robinson 26.72 → 25.52, Derrick
  Henry 21.25 → 19.95). Rollback: unset both, re-run the nightly. M3's proposal for the record — a nullable
  `pricing` column (`flat` / `ev`) on `ops.projections`, `ops.projection_ranges`, `ops.projection_backtest`, carried
  by `mart_projection_record` — goes with the flip.
* **Decisions kept**: "RotoWire via ESPN" as the source name (most items are RotoWire's); RotoWire items link to the
  player's ESPN page (they carry no web link); the news bucket is its own 60/min next to the injuries' 2/min; the
  first open of a card each hour fetches inline (≤ 3 s); the news line ships **on** (Andrew asked for it; the terms
  doc records what is and is not known — ESPN's Terms of Use were not readable from the sandbox); a unit's ROS
  rows are keyed by the league's directory (`mfl:0656`, `mfl:TMQB-KC`) so ownership and the trade board find them.
* **Open**: the residual (range) models' target carries no long-TD bonus (ranges 0.01–0.3 a game low, both flag
  states; v3.1); `why.py`'s "Sleeper's projection" and the record's market line still price all or nothing;
  `scoring_ev`'s curves are in-sample for 2023–25 (they match M2's walk-forward within 0.1); DEF slot-strength top
  has `team: null` (predates); four Knight Train lineup-view week counts moved by one when units entered the board
  past the horizon (Fannin 12 → 11 weeks, 0.28 points — not investigated); the IC-3 recording replays pre-IC-4
  answers (still passes); a shared ESPN bucket and a background news refresh.


### M3 2026-10-03 — the nightly on the spec (branch `dev/M3`, clone `league_lab_m1`)

* **Why**: Wave I-C measured expected-value pricing (M2) and kept it off for Sleeper leagues because the nightly priced
  projected lines with the flat engine and the request side re-priced them: one flag on one side only would have
  shown the same player at two numbers (IB-0's trust bug).
* **Delivered**: `scoring.price_projected(stats, scoring, position=None, *, ev=None)` — the one function that prices a
  projected line, called by `projections.price(..., "proj_")` (every nightly path: `predict_position`, `_oof_lines`,
  `_line_points`, `house_rows`, `calibration.oof_rows`, signals' what-ifs) and by `anyleague.price_lines` (IC-1's own
  branch folded in) and the on-demand larger-role what-if (`decisions._scenario_on_demand`). Flag off (default): the
  flat engine, bit for bit as before; flag on: a Sleeper scoring with a yardage or long-TD bonus prices them in
  expectation (`expected_frame(ev=True)` on `projected_view(scoring)`: the flat engine's keys, sorted), a scoring
  without one keeps the flat engine; an MFL spec: the expectation, always. Actual lines (`out_`) stay exact.
  `compute_points_frame` moved from `anyleague` to `scoring` (re-exported). `pricing_engine(scoring)` says which.
* **Evidence**: the harness both ways (`calibration.oof_rows`, ranges + lines, 2023–2025, both house leagues, one run
  per flag state): flag off reproduces all 432 stored v3.0 cells of `ops.projection_backtest`; flag on, Scrubs is
  identical to the bit in every column (projection, P10–P90, actual); the dynasty's season-total MAE per player
  improves at every position (QB 24.1 → 23.3, RB 17.6 → 16.9, WR 18.4 → 18.3, TE 12.8 → 12.6; 11 of 12 top-24
  buckets), the top-6 weekly bias RB +1.34 → +0.36, WR +1.65 → +0.74, TE +0.91 → +0.65 (QB +0.07 → −1.29: the QB
  line's own over-projection), coverage holds (80% ±0.004, 50% ±0.008), Spearman ±0.002, weekly MAE +0.007–0.041.
  Tables: docs/METRICS.md § "Expected-value pricing" → "On the nightly". On the clone's board: Scrubs moves 0 of
  8,134 player-weeks; the dynasty's top 24 move +0.66 a week on average in week 5 (QB +1.01, RB +0.71, WR +0.73, TE
  +0.18), rest of season +2.4 (TE) to +11.9 (QB); Josh Allen week 4 30.24 → 31.68.
* **Tests**: `tests/test_projections_ev.py` (19: the flag's default and values; the engine per scoring; nightly =
  request side bit for bit for the dynasty, Scrubs and the Test League, flag on and off, on synthetic lines and on 500
  `ops.projection_lines` rows of week 4; flag off = the pre-change `compute_points`; actual lines untouched; flag on =
  the expectation of the bonus keys; `house_rows` and `price_week` agree under either flag; the Scrubs pins, Josh
  Allen 24.42 / 30.24 → 31.68, the dynasty's top-24 move per position within +0.2 … +1.6 and down only past a
  threshold; the references without bonuses never move). `api/tests/test_m3.py` (2: the on-demand what-if).
  `api/tests/test_ic1.py`: "equals the pre-spec frame" is now "with the flag off" (+ flag on: Scrubs unchanged, MFL
  unchanged, the dynasty moves).
* **Checks** (clone `league_lab_m1`): root **986 passed**, 2 skipped (968 + 19 new); API 350 passed, 4 skipped, 3 failed —
  `test_ic1` dad's league weeks 1–2 and `test_ic_po`'s ten-yard cut fail identically on base `042f199`: the clone's
  `fct_player_game` predates the PO's `*_tds_10p` columns (122 / 156 within a point, the approximated split); ruff clean.
* **Open (PO)**: flip `LEAGUE_LAB_EV_PRICING=1` in the nightly's `.env` and on Render together, then run the nightly
  (the first EV-priced week in the record is the first week not yet kicked off); limit dbt's
  `assert_projection_ranges_price_the_lines` to the scorings `ev_moves` leaves flat; how the record names the engine
  (proposal: a `pricing` column, below in the hand-back); the residual models' actual has no 40+ TD bonus (v3.1).


### IC-4 2026-10-03 — the units and the double header, finished (branch `dev/IC4`, database `league_lab_i0b`)

* **Rest of season with the team units** (`anyleague.py` `# ---- IC-4`: `unit_window`, `units_priced_frame`,
  `unit_directory`, `unit_keys`; `_ros_table` marked lines): 70587's `/api/ros` has 32 TMQB + 32 TMPK rows, each week
  priced by the week's rule (the week's best-projected playable QB through `price_lines` as TMQB; the team's best K),
  byes off, keyed `mfl:0656` / `mfl:TMQB-KC`. Knight Train before: 11 rows, no unit; after: 14 — Buccaneers QB 368.98
  (#9 of 32 team QBs, bye 10), Bengals QB 325.42 (#24, bye 6, week 4 = 29.00 = My Week), Chargers K 162.67 (#5, bye 7).
  "Value to my lineup": Chargers K 2.75, Buccaneers QB 1.52 (starts 13 of 15 weeks), Bengals QB 0.00 (starts weeks 4
  and 10 only); 30 free units counted as the waiver wire. `ondemand.py`: `unit` / `priced_from` / `priced_from_words`,
  the QB pieces for a TMQB's "why", `position=TMQB|TMPK`, "team QB" in the lineup sentences; `unit_card`
  (`/api/player/mfl:0656`). Web `Ros.svelte`: the team badge where the face goes, Team QB / Team K chips, the "Priced
  from" line, a unit links to its card; `ros.ts` says "team QB" in the answer line.
* **Team Hub** (`decisions.units_named`): the slot strength names a unit with its team ("team QB · [CIN] Bengals QB",
  next man up "Buccaneers QB"); roster rows carry the unit's team. `decisions.ts` `slotLabel`: "team QB" / "team K".
* **Manager names**: MFL's public league export has no `owner_name` (70587 / 21861 / 10015 checked live through the
  pane; the fixture is unchanged, it equals the live export's franchise keys). `mfl_client.franchise_owners`;
  `MFLLeagues.users` gives the owner as `display_name` or None; `team_names` → `manager_name` null for MFL (was the
  team name repeated); the rosters route, `mfl_league` and My Week's summary carry it when it exists (tested with a
  synthetic `owner_name`).
* **Double headers**: `decisions.double_header_weeks` / `week_matchups` (`od_league_marts`: all-play once a week —
  Klaby Crew 57-9 → 27-6; `games` per team-week; the record from every game); `/api/league` `matchups` (week 4: 12
  games, double header; week 3 results: 6); `League.svelte` lists them (yours first, highlighted). `/api/record` for an
  MFL league: `results` + `records` (= MFL's standings for all 12 teams). Matchups names NFL opponents only: unchanged.
* **Waivers**: an empty starting slot's fill leads Help now and `top3` ("Fills your empty RB2 this week."; before,
  top3 led with a team K and a DEF); unit slots in words in the reasons.
* **Checks**: `api/tests/test_ic4.py` 10 passed; API suite 358 passed, 4 skipped, 3 failed — the three scoring-check
  tests of 70587 (`test_ic1` ×2, `test_ic_po` ×1), which fail identically on base `042f199` here: `league_lab_i0b` (the
  09-26 snapshot) has no `*_tds_10p` columns; `test_f3::test_ros_route` gains the `unit` key. Root 967 passed, 2
  skipped; ruff clean; web lint / typecheck 0 / 0, build ok; fixture e2e 140 passed (134 + 6). `web/e2e/ic4/` (6: phone at 375, desktop 1300) on `web/fixtures/mfl/api_70587_ic4.json` (recorded from
  this branch's API with `IC4_RECORD`, the ESPN overlay on).

### N1 2026-10-03 — the news line on the card (branch `dev/N1`, clone `league_lab_ia3`)

* **Why**: Andrew's first review asked for the player's news next to the numbers.
* **The feed, found through the browser pane** (read-only, no key): `site.api.espn.com/apis/fantasy/v2/games/ffl/news/
  players?playerId=<espn_id>&limit=5` — newest first, RotoWire's per-player blurbs (`type: "Rotowire"`, no web link)
  and ESPN's stories naming him (`Story` / `HeadlineNews` / `Media`, `links.web.href`); unknown id → `feed: []`. The
  brief's candidates failed: `common/v3/.../athletes/<id>/news` 404 on both hosts, `site/v2/.../news?athletes=` ignores
  the filter, `site/v2/.../athletes/<id>/news` always empty, `common/v3/.../overview` 241 KB a call. Recorded in
  `docs/ESPN_TERMS.md` (with what the answer says about use: nothing; ESPN's Terms of Use not readable from here).
  Fixtures `api/tests/fixtures/espn/news_4262921.json` (Jefferson, 5 items, newest 2026-10-03 13:33 UTC) and
  `news_3045147.json` (Conner, newest 2026-08-30), bodies / images / video emptied.
* **Feed client** `src/league_lab/news_feed.py` (injury_feed's pattern): keeps `{headline, date, source, url}` only
  (source "RotoWire via ESPN" / "ESPN"; url = the story's https espn.com page, else his ESPN player page; any other
  host is never passed on), per-athlete cache `LEAGUE_LAB_CACHE_DIR/espn_news/<id>.json` an hour / 15 minutes on game
  days, bucket 60 a minute (`LEAGUE_LAB_ESPN_NEWS_PER_MIN`), fixtures `LEAGUE_LAB_ESPN_FIXTURES/news_<id>.json` (age
  measured from the recorded answer's `timestamp`), a failure serves the last copy or nothing, `LEAGUE_LAB_NEWS=off`.
* **API** `api/league_lab_api/news.py` + `# ---- N1` blocks in `player.py` (`news` top-level on every card: house,
  on demand, MFL) and `main.py` (`/api/status` → `news`): at most 3, newest first, none older than 14 days; `[]` when
  off / out / no ESPN id. ESPN id: the id table read backwards (`availability.espn_to_gsis`), else Sleeper's
  directory. Off in fixture mode unless the ESPN fixtures are set (as the overlay).
* **Web**: `components/NewsLine.svelte` — "**News** · 2 h ago · *headline* · RotoWire via ESPN ›" as the last line of
  the Availability section on the page (`player-news`) and in the pane (`pane-news`); newest only, cut at a word to
  110 characters (full headline in `title` / the link's label), link `target=_blank rel="noopener noreferrer"`.
  `lib/card.ts` `ago` / `shortHeadline` / `newsLine`, `lib/api.ts` `NewsItem` (marked blocks). About gains one
  sentence under the model cards (`about-news-source`).
* **Tests**: `api/tests/test_n1.py` 15 (parse keeps 4 keys and drops the body; 3 / newest first / 14 days incl.
  Conner stale; bad answers; cache 59 min hit, 61 min miss, 16 min on a game day; disk copy holds only the line and
  survives a restart; outage → [] or the last copy; bucket; off switch; fixture clock; card: 3 items in order with
  sources and https links, stale → [], outage → [] and 200, off → [] and 0 calls, fixture mode without ESPN → [],
  Waivers + Trends → 0 news calls). `web/e2e/n1/` 5 × phone (375) / desktop: the line on the page and in the pane,
  no line without news, ESPN's own story, About's sentence.


## Wave I-E (Iteration 17, part E)

### PO merge — Wave I-E, 2026-10-03 (Saturday, 18:30–20:30 ET)

* **Why**: the third outside review (`docs/reviews/2026-10-03-mfl-70587-usability-review.md`: a casual manager's
  walk of dad's league on `042f199`, plan § 17 "Fourth"). Andrew: "just incorporate that … squeeze it in" without
  losing the other waves. One round, three devs, the review as the specification.
* **Delivered**: **IE-0 (P0)** — the trade calculator keeps every asset: `parseIds` had rejected the colon in a
  provider key (`mfl:0682`, Houston Texans QB) and the picker silently filtered the rest, so the review's two-for-one
  ran as Tuten-for-Rice; keys are opaque now, the URL / request / answer / summary / before-after lineups describe
  one package (the review's own link: give `["mfl:0682","12490"]` → −8.6 this week, −2.4 over weeks 4–7 for Big Mac
  Attack; them −2.0 / +23.2; "you open a spot"; the Bears QB in at team QB), an asset the analysis cannot price
  answers 400 with its name and the calculator shows "Can't analyse X: why" with "Take out of the trade"; Waivers'
  bye words come from the candidate's own evaluated move ("Starts at WR/TE 3 in week 7, when McConkey is on a bye";
  a team QB can no longer "fill the empty DEF"); platform words ("on the bench in MFL", no Sleeper market line on an
  MFL league, both platforms in the setup heading and the league menu), one points-per-game statement with its source,
  `TeamBadge` never says "Free agent" for a missing NFL team. **IE-1 (P1)** — My Week is a weekly action list:
  `GET /api/my-week` gains `actions` (≤ 3, by urgency: a change the submitted lineup needs → a close call with an
  injury in it → the waiver claim that raises this week's starters), each in three layers (the sentence; the reason,
  whether it is already in the submitted lineup, the lock time; "Why? The numbers behind it" = the old cards),
  related calls combined ("Keep Addison and Nabers ahead of McConkey for now … McConkey's questionable status breaks
  the tie. Check his status again before kickoff." — one action where there were two cards), `set_line` ("The rest
  of your lineup is set — nothing to change"), `edit_link` ("Open MFL to edit your lineup" →
  `<host>/<year>/options?L=<id>&O=02`, the franchise's Submit Lineup page behind MFL's login; Sleeper's league
  page), `nothing_submitted` ("League Lab never changes your lineup or claims; it tells you what to do in your
  league's app"); Scrubs roster 2: one **Change needed** action ("Start Wilson at FLEX … in place of Jefferson.
  Jefferson is out … → Not in your Sleeper lineup yet"); Waivers' top three lead with this week's gain (the four-week
  total second, "in total"), the hero sentence is not a card's, Help now starts after the three, alternatives are
  labelled, "two claims do not add up beyond your 1 open roster spot"; the dial is **"Effect on their starters"**
  (Makes their lineup weaker · About even · Improves their lineup · Improves it a lot, with the need it fills; no
  0–100, no "interest"); the Finder leads with the cheaper package ("Same gain for you without RJ Harvey"; the extra
  asset's cost in season points). **IE-2 (P1/P2)** — the trade result through the starting lineup (`trade_story`:
  `starters_in` / `starters_out` by membership — a starter who only changes slot number is in neither —, the cut,
  `effect_words`, `lineup_words` "Rice starts at WR/TE; McConkey to the bench", `backup_words`, `their_change`,
  `window_words`, `hold_words` with the best free agent for the same need, `how` behind "How we calculated this";
  the lineup rows' `change` is the player's own, null for a slot move: Nabers' "+0.23" for WR/TE 2 → 3 is gone, the
  row changes add up to the total's change), the dictionary (`docs/WORDS.md` § "The dictionary": "Projected points
  this week", "about 10 more in total over weeks 4–7", "Improvement to your starting lineup", "Points suggested by
  his past opportunities", "Projected value above available replacements", "Typical range (the middle 50%)",
  "Low-end / high-end outcome", "Share of team passes thrown to him", "Backup coverage", the unit words) on the card,
  the pane, the calculator and the Finder; the setup screen with the team picker first and the scoring collapsed to
  "Custom MFL scoring — some pieces are estimated ›"; supporting-text contrast 4.4–4.9 → 5.3–5.9 (light) and
  4.8–5.8 → 5.3–6.5 (dark), small labels 11 → 12 px.
* **PO**: merges IE0 → IE2 → IE1 (`api.ts` and `TradeCalc.svelte` conflicts: all three blocks kept; the dial's
  "How to read this" bullet from IE-2 with IE-1's labels). Then: (1) **the trade verdict's words** — `trades.verdict`
  said "expect a no" / "worth offering" / "a rebuilding team might take it" / "skip it", the acceptance guesses the
  review asks to remove; it now says what each starting lineup gains and what the season value says ("Helps your
  lineup +4.2 this week (+10.3 over weeks 4–7), costs their lineup 1.1 (3.0 over weeks 4–7); you give up more season
  value: a lineup loss for them; the value is on their side"); (2) **the three strongest claims are ordered by this
  week's gain** (they lead with it now — Schultz +3.0 first on team 8, the Falcons' bye cover +1.2 / +12.8 third);
  (3) **the lineup table says what the call says**: when an injury tiebreak keeps the healthy player, the table (still
  the best lineup on paper) read as the opposite — McConkey's row now says "Questionable — the call above keeps
  Addison here for now" and Addison's bench row "starts for McConkey by the call above" (`myweek.annotate_swaps`,
  `swaps` on the answer, `key` on every lineup row); (4) the e2e recordings for 70587 / IE re-recorded from the merged
  API; `api/tests/test_ie_po.py` (2). Checks: **root 987**, **API 406** (380 before), **web lint / typecheck / build
  clean, 172 fixture e2e** (150), ruff clean. QA walk (fixtures, overlay on): team 8's My Week = one close-call action
  with both receivers, "✓ Already in your MFL lineup", the waiver claim, the set line, the green "Open MFL to edit your
  lineup ↗" button and the nothing-submitted line (`ie1-team8-week-phone.png`); the review's trade link = a
  two-for-one with the lineup story; `mfl:9999` → "Can't analyse mfl:9999: not a player League Lab knows in this
  league."; Waivers' top three in this week's order.
* **Decisions kept**: IE-1's 0.5-point bar for a "change" (a coin flip worth half a point with nobody hurt is a
  change — a higher bar is a one-constant change, `ACTION_MIN_GAIN`); the waiver action priced on the best lineup
  (it may say "over McConkey" while the close call keeps him off); the MFL edit link is MFL's login-gated Submit
  Lineup page (verified: `O=02` redirects to the league's login; the public menu's own codes are O=01 franchise, 03
  transactions, 06 starting lineups, 07 rosters, 09 rules) — dad confirms it lands on Submit Lineup once signed in;
  "RotoWire via ESPN" unchanged; old e2e recordings that carry no `actions` still render the old cards (the layout
  switch is by the answer's shape).
* **Not done from the review (P2, next time)**: the compact schedule table on the card; injury / bye status next to
  the name on every row; "Updated 2:51 PM ET" with the exact time behind it and a separate MFL roster freshness line;
  the My Week footer note on estimated scoring pieces; the dictionary on Waivers / Compare / Receivers / Trends /
  About and in the console's card words (`app/lib/cards.py` keeps "Most weeks:" for parity); the Trades buy-low /
  sell-high "Fit" labels; a waiver deadline (unknown per league); the game-log chart's sentence does not say
  "reconstructed"; MFL's official per-player scores (`weeklyResults`) are not read for points per game.


### IE-0 2026-10-03 — MFL correct before a casual user relies on it (the review's P0 1–3; branch `dev/IE0`, clone `league_lab_i0b`)

* **Why**: the third outside review (`docs/reviews/2026-10-03-mfl-70587-usability-review.md`, on dad's league MFL 70587,
  Big Mac Attack) found the calculator dropping an MFL team-QB asset, a Waivers card saying a team QB "fills the empty
  DEF slot", and Sleeper words on an MFL roster.
* **P0 #1, the cause (reproduced before the fix)**: `web/src/lib/decisions.ts` `parseIds` kept only `/^[\w-]+$/`, so
  `give=mfl:0682,12490` became `["12490"]`, and `TradeCalc.svelte` then filtered the keys to the rosters — silently.
  The new e2e replayed on the base code: the review's link opens with Houston Texans QB unticked (`toBeChecked` fails),
  the Finder's `mfl:0671,12490 → mfl:0675` opens with nothing on the get side (no verdict); the request carried
  `give: ["12490"]`. The API itself always handled the key (`trades.parse_ids` splits on commas only).
* **Delivered**: asset keys are opaque end to end (contract in the wave's INTERFACES.md § IE-0): `parseIds` accepts any
  key without a comma or space (≤ 64), keeps order, drops repeats; the calculator keeps every key of the link, sends
  all of them, names them in the summary ("Houston Texans QB + Bhayshul Tuten", the bar's "Texans QB + Tuten → Rice");
  `POST /api/trades/evaluate` answers **400 with `unavailable: [{key, side, name, why}]`** for a key not on that side's
  roster, unknown, or an IDP ("Can't analyse Malik Nabers: on Big Mac Attack's roster, not Madeyes Revenge's") and the
  calculator shows that in place of the dial, with "Take out of the trade"; the answer's unit rows carry `team` and
  `unit` (the Finder's too). **P0 #2**: `_bye_reason` is the candidate's own — "Fills your empty X" only when X's slot
  type admits his position, "Starts at <slot> in week N, when <starter> is on a bye" only for a decision-week starter
  whose slot he can play, else no bye words ("Would not start for you this week; helps in week 7."); this week's slot in
  the league's words (`cards.slot_label`: "WR/TE 2", was "WR+TE2"); a team unit never "No games this season yet".
  **P0 #3**: the card says "on the bench in MFL" / "starting in his MFL lineup", no "(None)" for a manager MFL does not
  share, no Sleeper market line on an MFL card, the ROS list or My Week's rows (no "not in yet" either), `platform` on
  the card; an on-demand card states points per game once — the chart's own number with its source ("10.5 over 2 games,
  reconstructed in this league's MFL scoring from his stat lines"; was "not shown yet" beside a chart showing it);
  `TeamBadge` shows no chip for a missing NFL team (was "FA", titled "Free agent") and is named for screen readers
  ("Houston Texans"); the setup heading and the league menu name both platforms.
* **Evidence (fixtures, overlay on)**: the review's package, team 8 ↔ 12, weeks 4–7 — **before** (what the calculator
  asked): Tuten for Rice, you +3.36 this week / +9.52 over the window, them −2.05 / −2.67, "No deal" 14, "Roster size: no
  change (1 for 1)", Houston Texans QB still at team QB; **after**: Houston Texans QB + Tuten for Rice, you −8.58 / −2.42,
  them −2.05 / +23.15, "Hard to say no" 100, "you open a spot", team QB = Chicago Bears QB, "Out of the lineup after
  the trade: Houston Texans QB (team QB, 30.40, traded)"; the Finder's `package_gains` on the same board −8.58 / −2.42 /
  −2.05 / +23.15 (equal; the review's live +0.7 / +9.5 was another day's data). Waivers on team 8: every Help-now and
  top-3 card names the slot of its solved move ("Starts at WR/TE 2 this week over McConkey (6.9)."); the review's
  "Arizona Cardinals QB … fills the empty DEF in week 7" on the fixture's week-7 shape now reads "Would not start for
  you this week; helps in week 7." Tuten's card: "Rostered by **Big Mac Attack**, on the bench in MFL", market none,
  points per game 10.5 = the chart's (8.8, 12.2).
* **Tests**: `api/tests/test_ie0.py` (8: opaque keys; the two-for-one end to end = the Finder; unit teams on the Finder;
  unknown / wrong-side keys named; Help-now slots eligible and taken; no QB-to-DEF; Tuten's card; no MFL market).
  `test_ib2::test_one_reason_is_one_fact` updated (its bye case had no position and expected the DEF words — the
  review's bug; now a DEF, plus a QB in the same week that gets none); `test_f3::test_player_card_any_league` (points
  per game is either shown or listed missing, never both). `web/e2e/ie0/` (3 × phone 375 / desktop 1300; recorded
  into `web/fixtures/mfl/api_70587_ie0.json`, the POSTs keyed by body: `IE0_RECORD=…`). Checks: **API 385 passed, 3
  failed** (the three clone scoring-check tests: `test_ic1` × 2, `test_ic_po` × 1), 2 skipped; **web lint / typecheck /
  build clean, fixture e2e 156 passed** (150 + 6); ruff clean.
* **Open**: the game-log chart's own sentence still says "in <league> scoring" without "reconstructed" (IE-2's
  `Player.svelte` / `GameLog`); MFL's official per-player scores (`weeklyResults`) are not read for points per game —
  the reconstruction is labelled as such; a given player whose game has kicked off stays in this week's lineup (the
  engine's lock rule) — the words do not say so yet.


### IE-2 2026-10-03 — trades through lineup changes, the dictionary, the setup order, less effort

* **Trade answer** (`decisions.trade_story`, `# ---- IE-2` block; `evaluate` calls it once): `starters_in` /
  `starters_out` by starter membership (this week's lineups before / after), `cut`, `effect_words`, `lineup_words`,
  `backup_words`, `their_change`, `window_words`, `hold_words` (+ `hold`: standing pat; the best free agent at the
  incoming positions by `trades.best_fill` on today's roster), `how`. `lineups.<side>.slots[].change` is the player's
  own (null for a starter who only changed slot number), `lineups.<side>.out` the starters who left (their value as a
  negative change), `reshuffled` the slot moves (detail, no points), `total`. The changes add up to the lineup total's
  change. No number moved: Tuten for Rice (70587, 8 ↔ 12) is +3.36 this week / +9.52 weeks 4–7, them −2.05 / −2.67,
  before and after. Before: Nabers (WR/TE 2 → WR/TE 3) +0.23 and Rice +3.13 on the slot rows; after: Rice +10.24,
  McConkey −6.88 (to the bench), Nabers none.
* **Calculator** (`TradeCalc.svelte`, under the verdict in the result card): You give / You get (+ the cut) → the effect
  sentence → "Your starters this week" (In / Out by name, the total before → after) → backup coverage → their side →
  the alternatives; "Why?" is now "How we calculated this" (the improvement line, value above replacements, rest of
  season, ranks, roster size, week by week); the lineup detail shows the starters who left and the slot moves.
* **Dictionary**: `docs/WORDS.md` § "The dictionary" (the review's table with the meaning column; the trade in words;
  freshness). Applied: the trade answer's `fit.words` / `market.words` labels (`decisions.dictionary_words`, the
  console's sentence functions unchanged), the calculator's labels and "How to read this", the player card / pane tiles
  (`card.ts` `CARD_WORDS`: Projected points this week, Typical range, Low-end / High-end outcome, From past
  opportunities, Share of team passes) and the card's "How to read this" (`howtoWords`). The API's player card keeps the
  console's labels (`test_parity` pins them).
* **Setup** (`Leagues.svelte`): the MFL card shows the league, then "Which team is yours?", then the read-back
  collapsed to one status line ("Custom MFL scoring — some pieces are estimated" / "… scoring, read exactly"); open,
  the read-back and the check, the check one line, its misses behind "The misses (n)". Team picker y = 483 px at 1300
  (status line 788), 519 px at 375.
* **Less effort**: `--ll-ink-3` light #687186 → #5c6579, dark #838da0 → #8b95a8: ink-3 on page / surface / raised /
  sunken = 5.30 / 5.85 / 5.45 / 4.97 light (was 4.44 / 4.89 / 4.56 / 4.16), 6.45 / 5.95 / 5.34 / 6.27 dark (was
  5.82 / 5.37 / 4.82 / 5.66); `text-label` 11 → 12 px; the player page's scoring pieces under "How we calculated this".
* **Tests**: `api/tests/test_ie2.py` (6: the answer's fields on the review's case, no gain from slot renumbering on the
  fixture and on a constructed board, the dictionary in the trade words, the full package's lineup story, the
  this-week window); `test_decisions.py` (the parity compares through `dictionary_words`); `web/e2e/ie2/` (3 × 375 /
  1300: the result's order, the lineup detail, the setup order, the contrast from the CSS variables), recorded in
  `web/fixtures/mfl/api_70587_ie2.json`. API 383 passed, 3 clone failures (`test_ic1` ×2, `test_ic_po` ×1), 2 skipped;
  web lint / typecheck / build clean; fixture e2e 156 passed.
* **Open**: the compact schedule table (week · opponent · projected), status next to the name on every row, "Updated
  2:51 PM ET" and the MFL roster's freshness line, the My Week footer limitation line, the dictionary on the console
  cards (`app/lib/cards.py` "Most weeks:", IE-1's) / Waivers / Compare / Receivers / Trends / About.


### IE-1 2026-10-03 — the weekly action list, Waivers this week first, the effect dial, the cheaper package

* **Why**: the third outside review (`docs/reviews/2026-10-03-mfl-70587-usability-review.md`, § P1 "weekly action
  list", "waiver horizons", "interest dial", "unnecessary extra assets"): a manager who does not enjoy analytics must
  see what to do, why, who starts instead and whether anything is submitted, without the methodology.
* **My Week** (`myweek.build_actions`, both paths; `GET /api/my-week` gains `actions`, `set_line`, `next_lock`,
  `edit_link`, `nothing_submitted`, `platform_name`; each card gains `key`, `alt_key`, `tiebreak`, `action`): at most
  three actions, the most urgent first — `change` (the submitted lineup — Sleeper's `starters`, MFL's through the
  translation — differs from the suggested one by ≥ 0.5 projected points or starts a player who cannot play), `close`
  (a coin flip with an injury status in it), `move` (Waivers' new `home_action`: the claim that adds most to this
  week's starters, ≥ 0.5, added by the page when there is room). Cards that share a player are ONE action
  (union-find over the keys; the submitted lineup's differences join them). The suggested lineup is the best lineup
  except where a coin flip's tiebreaker is an injury (`cards.tiebreak`, the same pieces as the card's sentence): the
  healthy player starts. A clear / lean call already in the lineup, and a difference under 0.5 with nobody hurt, are
  not actions: the `set_line` says the rest is set. Nothing at all submitted → one action ("Set your MFL lineup").
  The page: the action (one sentence, players linked), the reason and what could change it, "Already in your MFL
  lineup — nothing to change." / "Not in your Sleeper lineup yet …", the lock ("before Sun 4:05 PM ET": the first
  kickoff among the players the action swaps), "Why? The numbers behind it" (the old cards' sentences and small print,
  Compare), then the set line, **Open MFL to edit your lineup ↗** (`<host>/<year>/options?L=<id>&O=02`) / **Open
  Sleeper …** (`sleeper.com/leagues/<id>`), and "League Lab never changes your lineup or claims; it tells you what to
  do in your league's app." An answer without `actions` (recorded before this wave) still renders the old cards.
* **Waivers** (`decisions._ie1_present` at the end of `waiver_views`): every card gains `lead` ("Falcons defense instead
  of Jaguars: about 1 more starter point this week"), `total_words` ("+12.8 over weeks 4–7 in total") and
  `alternative_to` (an earlier card that takes the same spot this week: "Instead of Devaughn Vele:"); the claim card's
  big number is this week's gain, labelled "this week", the window's total the second line; the screen's answer is
  `answer` ("The three strongest claims are below, each with what it adds this week.") — not the first card again;
  Help now lists what the three do not already show; `not_additive` under the three.
* **The dial** (`decisions.interest` → `effect_label`, `need_words`; `Dial.svelte`): "Effect on their starters" —
  Makes their lineup weaker (< −0.05) · About even (−0.05–2) · Improves their lineup (2–6) · Improves it a lot (> 6),
  the need it fills ("It starts at their WR/TE over Wan'Dale Robinson."); no 0–100 on screen, no "interest", no "hard
  to say no". Same number, same thresholds, same needle. METRICS § renamed (ti1.1).
* **The Finder** (`decisions._ie1_cheaper`): a two-for-one whose single-player sub-package reaches the same gain for
  you (< 0.05) and still raises both lineups is led by that one-for-one (`is_best`, the headline, `cheaper_than`); the
  two-for-one names the extra player `optional` with his rest-of-season points.
* **Evidence — the review's roster, MFL 70587 team 8 (overlay on).** Before: three cards — "WR/TE 3: McConkey or
  Addison — a coin flip (Go with Addison: McConkey is questionable)", "WR/TE 2: Nabers or Addison — a coin flip (Go
  with Nabers on the matchup)", "RB2: Keep McCaffrey over Tuten (clear)". After: **1 lineup action** — "≈ Close call ·
  WR/TE 2 · WR/TE 3 · before Sun 4:05 PM ET — Keep Addison and Nabers ahead of McConkey for now. Their projections are
  close (within 0.5 points); McConkey's questionable status breaks the tie. Check his status again before kickoff. ✓
  Already in your MFL lineup — nothing to change." (both cards behind its Why?), then "+ Waiver claim · WR/TE 2 — Claim
  Dalton Schultz: about 3 more starter points this week." (+8.1 over weeks 4–7 in total), "✓ The rest of your lineup
  is set — nothing to change.", the MFL link, the nothing-submitted line. Cards' numbers unchanged (6.88 / 6.60 / 0.28,
  7.11 / 6.60 / 0.51, 15.45 / 9.72 / 5.73; lineup 30.40 … 10.81).
* **Evidence — League of Scrubs roster 2 (overlay on).** Before: three cards — "FLEX2: Wilson or Croskey-Merritt — a
  coin flip", "FLEX1: Keep Tuten over Croskey-Merritt", "RB2: Keep Hampton over Croskey-Merritt" — none said that
  Sleeper's lineup still starts Justin Jefferson (Out). After: "⚠︎ Change needed · FLEX2 · before Sun 9:30 AM ET —
  Start Wilson at FLEX (or Croskey-Merritt: a coin flip) in place of Jefferson. Jefferson is out; the change is worth
  about 9 more projected points this week. Wilson and Croskey-Merritt are level by the projection; the matchup leans
  Croskey-Merritt. → Not in your Sleeper lineup yet: make the change in Sleeper." (the three cards behind its Why?),
  the set line, the Sleeper link. Waivers' claim (Reichard for McLaughlin, about 2 more starter points this week) is
  not added: it drops Croskey-Merritt, whom the action names (a claim is added only when it neither adds nor drops a
  player an action names).
* **The review's package** (`give=[mfl:0682, 12490] get=[10229]`, team 8 ↔ 12, on the fixture): −8.58 this week and
  −2.42 over weeks 4–7 for Big Mac Attack with Tuten and without him (+23.15 / +21.35 for Madeyes Revenge): Tuten is the
  optional asset. On the Finder (team 12 → Knight Train): "Rashee Rice for Cincinnati Bengals QB" (+19.8) now leads,
  "Adding RJ Harvey does not change your gain; it costs you RB depth (RJ Harvey: 97 season points)" on the two-for-one.
* **Tests**: `api/tests/test_ie1.py` (10: both rosters' actions, the rules on hand-built frames — set lineup, tiny
  difference, an Out starter first and at most three, unknown submitted lineup — Waivers this week first / cumulative
  / no triple copy / alternatives / `home_action`, the dial's words and need, the cheaper package on 70587 team 12, the
  review's own package); `test_ia2.py` dial buckets and caption updated (the words changed, the numbers did not);
  `test_ic4.py`'s RB2 claim read from the top three (Help now starts after them). `web/e2e/ie1/` 5 × phone (375) /
  desktop (1300) on answers recorded from the API (`web/fixtures/ie1/api_ie1.json`); `e2e/ia2` no longer reads the
  0–100 text. Root `uv run pytest` 986 passed (cards.py: the tiebreaker as data, the card text unchanged).

## The rename — isuckatfantasy (2026-10-04, 00:20–00:50 ET)

* Andrew: "we need to rename the app effective immediately. I want to call this, isuckatfantasy. I'm working on
  the domain now." Done as a PO change on `main`: one constant on each side (`web/src/lib/brand.ts` `APP_NAME` /
  `APP_MARK`; `api/league_lab_api/settings.py` `APP_NAME`), every user-facing sentence reads from it (sign-in, the
  top bar's wordmark, About, the League / Leagues / Ros screens' error lines, `NOTHING_SUBMITTED`, the calculator's
  "not a player … knows", the card's "Not in the lineup … solves", the About model answer, the usage notice), the
  page title and the manifest, the icons regenerated with the mark "isaf" (`web/scripts/make-icons.py`), the e2e
  assertions and the recorded answers, What's new ("A new name"). Not renamed, on purpose: the package, the
  `LEAGUE_LAB_*` variables, the roles, the repository, the Render service, the workflows, the console, the docs'
  prose (README says so at the top). Checks: the renamed-word API tests 74 passed, the e2e that assert the name 64
  passed, lint / typecheck / build clean. The domain: Andrew; the steps are in HANDOFF § "Where things stand".
* **Follow-up (2026-10-04, morning)**: the `image` workflow's run for the rename (`95e354f`) failed at the
  "Start the image once" smoke step — it grepped the served page for `<title>League Lab</title>`, the one assertion
  the rename missed (the image was never pushed, so Render had nothing to autodeploy; Andrew deployed by hand). Fixed
  to the product name (`.github/workflows/image.yml`; the image's OCI description names both), and the same check in
  `scripts/smoke.sh`. Nothing else in `.github/` or the ops scripts asserts the old name.
* **N2 merged by the PO (2026-10-04, 02:00–02:40 ET)**: Andrew's Mac had `git merge playerwire-integration` stopped
  on five conflicts (the branch left `16e4657`, before I-E, I-F and the rename). Resolved here and fast-forwarded there:
  `news.py` — N2's `for_card` (PlayerWire first, ESPN fills) over IF-4's `ordered` / `about` / `recent` (ESPN's items
  keep IF-4's order; a brief is `about: "player"`; every item has `kind`); `test_n1` pins both keys; `test_n2`'s three
  pinned ESPN orders moved to IF-4's (his blurbs first, the inactives story last) and expect `about`; the N2 e2e's About
  sentence reads the product name; CHANGELOG / HANDOFF / STATUS keep both sides (N2's section below I-F's). The web
  side merged clean: IF-4's "League news" label and N2's summary / verification tag coexist on `NewsLine`. Checks: API
  478 passed / 3 skipped (the N2 16 included), root `test_playerwire_sync` 36 + trades + matchups, ruff, svelte-check,
  eslint, build, e2e n1 + n2 + if4 36 passed. **Found on the way**: `research._load_matchups` loaded `app/lib/matchups.py`
  as `league_lab_api._applib_matchups`, so the PO's I-F `from .cards import rank_words` raised `ModuleNotFoundError`
  — Compare answered 500 whenever both players had an adjusted rank (`test_if3::test_williams_compare…` caught it; the
  I-F QA ran before that PO edit). Loaded as `league_lab_api._applib.matchups` now. Live had this from `8f80c96` until
  this deploy. `hosted_relations.py` does not list schema `playerwire` (the sync never publishes or drops it; the app's
  SQL joins `analytics.player_id_map`, already published). N2's set-up steps (`docs/PLAYERWIRE.md`; HOSTING § 5
  "one writer per schema") stay Andrew's.

## Wave I-F (Iteration 17, part F)

### PO merge — Wave I-F, 2026-10-03 (Saturday night, 22:00–00:10 ET)

* **Why**: the fourth outside review (`docs/reviews/2026-10-03-decision-quality-review.md`; plan § 17 "Fifth") —
  decision quality on `f6315ae`: four engine-level findings (the free drop, the trade that loses to a waiver claim,
  the matchup rank used as a tiebreaker while the corners changed, the hidden coin flip) and a table of language
  fixes. Andrew: "next wave plus see this too" — the planned usage tracking rode along.
* **Delivered** (five Opus devs in parallel, 55–65 min each): **IF-1** a drop's cost in pieces (`waivers.drop_cost`:
  lineup loss over the horizon; depth lost = his margin over the best free agent at the position × the position's
  absence rate; starts after the horizon above a replacement; season points above the best free agent
  (`trades.price_by_player`'s rule); a role scenario's upside — the **max**, never the sum), the best drop per claim
  the cheapest with the incumbent first on a tie, net gain = lineup gain − (cost − lineup loss), a claim worthwhile at
  net ≥ 1 this week or ≥ 3 over the horizon, "no claim is worth a roster spot this week", stashes a watchlist
  (`watch`, no drop, what would change it); one `choose_drops` for the nightly writer, the on-demand sweep and the
  API reading an older mart (14 cost columns on `ops.waiver_moves`). GoodGameBuddy: "Claim Carlson, drop Marvin
  Harrison Jr." → "Drop McPherson: Carlson replaces him at K. Dropping Harrison Jr. instead gives the same gain: he
  projects 79 season points, 43 fewer than the best free-agent WR …"; the roster's claims drop {McPherson, Cousins,
  Harrison} instead of {Harrison}; no gain number moved. **IF-2** the ladder per objective — standing pat, the best
  legal waiver move (IF-1's `best_waiver_move`, else `trades.best_fill`), the trade — and the finder ranked by **gain
  beyond the best alternative** ("+14.6 over weeks 4–7: 1.8 more than your best waiver move (the Atlanta Falcons
  defense claim gives +12.8 for an open spot)"; a trade below it is demoted and keeps a reason only when the numbers
  give one), the headline = the first card, the ordering said in one line, the value concepts named and kept apart
  (projected points · starter points · backup coverage · season value above replacement = the fairness test, package-
  size aware · rest-of-season projected points "all positions added up — not a fairness test"), `WeekStrip.svelte`
  (both sides' weeks). **IF-3** `research.matchup_evidence` — history (the rank in words with games, period, scoring,
  "not adjusted"), what changed (the depth-chart corners vs the season's coverage-snap regulars; a missing regular's
  status from the overlay with source and date; the replacements' rank or "unranked"), the implication, and an
  honest `forecast_treatment` ("contextual only; not in the forecast" — a test parses `projections.BASE_FEATURES` and
  fails if an opponent-personnel input appears); on Compare, the card / pane (under "Next:"), Matchups' corner rows;
  the coin flip's matchup tiebreak is gone when the corners changed ("the matchup rank does not settle it this week:
  Carolina's starting corners changed (Jackson and Horn are on injured reserve)"); the `ops.events` design in the
  hand-back. **IF-4** `review` lines on My Week ("Tuten or Williams at FLEX: a coin flip, 0.3 points apart; your
  lineup has Williams — no clear upgrade. Compare ›"; `set_line` "No clear upgrade elsewhere."), "What changed" (the
  overlay's moves + the starters' news of the last 24 h, "Nothing has changed since the morning build."), the pane
  trimmed to the decision parts with the ledger / schedule / game log behind expanders, every table row (bench-only
  expander; "Margin" → "4.63 over Lloyd" / "no eligible reserve"; one rank direction in words — "12th-fewest WR
  points allowed"; Compare bolds points rows only; the duplicated three-game sections collapsed; "Typical range (the
  middle 50%)" everywhere incl. the console; metric-tile definitions; "not enough games to say" / "role steady over
  N games"; the observed gap instead of "expect him to pick up"; the player-specific news item first, "League news"
  second), the I-E leftovers (the Schedule table, "Updated 7 d ago ›" with the exact time, the dictionary on
  Receivers / Trends / Compare / About / Waivers). **U-1** usage tracking: `usage.events` (at · screen · league key ·
  team number · platform · version · a daily random session id; database checks refuse anything else; no name,
  username or IP), `scripts/hosted_usage.sql` (idempotent, run by the sync after the restore; the `usage` schema is
  never dropped), the app role keeps `default_transaction_read_only` — the insert runs `BEGIN; SET TRANSACTION READ
  WRITE; INSERT; COMMIT` on its own connection from a queue + one writer thread (a failure never fails a page),
  `POST /api/usage` (204, cookie `ll_usage` to New York midnight, a 1/s bucket with bursts of 5, `LEAGUE_LAB_USAGE=off`),
  `GET /api/usage/summary`, `lib/usage.ts` (`sendBeacon`), About's notice, the console's Usage page.
* **PO**: merges U1 → IF1 → IF3 → IF2 → IF4 (`api.ts` four blocks kept; `player.py`: IF-3's evidence and IF-4's
  schedule on the same card). Then: (1) `mart_waiver_moves` carries IF-1's 14 cost columns (pre_hook `alter table …
  add column if not exists`, the select) — rebuilt here; the rows fill at the next nightly (`choose_drops` in the
  writer), the API re-ranks older rows on read (the parity test's "built before the cost" check now also covers an
  empty column); (2) the Compare verdict's adjusted ranks in words with one direction ("9th-most WR points allowed by
  his defense once the offenses it faced are counted, 9th-fewest … by Worthy's"); (3) the pane's matchup sentences
  ride in the projection section's blocks (IF-3's `matchupBlocks` under "Next:"; IF-4's placeholder noted); (4)
  three registry rows (`drop_cost`, `trade_beyond_alternative`, `matchup_personnel`). Checks: **root 995** (987
  before), **API 462** (406), **web lint / typecheck / build clean, 192 fixture e2e** (172), ruff clean; the hosted
  closure gains `mart_matchup_cb_context` (the next nightly carries it) and nothing heavy. QA walk (the merged API on
  the main database and the fixtures): GoodGameBuddy's Waivers = "Stroud instead of Cousins … Drop Cousins" and
  "Carlson instead of McPherson … Drop McPherson" with Harrison's season value named; team 8's finder = the headline
  is card 1 with "+1.8 beyond the Atlanta Falcons defense claim", cards 2–3 demoted; the Williams / Tuten compare
  carries the evidence object; GoodGameBuddy's My Week (IF-4's recording): the "No clear upgrade" review card, "No
  clear upgrade elsewhere.", "Open Sleeper to edit your lineup", "What changed", the margin words on every starter.
* **Decisions kept**: IF-1's absence rates are documented constants, not fitted; the 1 / 3-point worthwhile bar also
  hides small no-drop claims; IF-2 leaves the finder's own raw-total sanity filter (changing it changes which trades
  are suggested — next time, with the season-value test); team units have no season value on demand (named "Not
  counted"); IF-3's "one missing regular = less representative" with no threshold; receivers only; U-1's grant is
  INSERT + SELECT (the summary reads), the row keeps the team number (a league + team is a known manager, no name is
  stored — About says "which league and team"), the bucket not a strict 1/s.
* **Open**: the Carlson / McPherson case on the live server shows the new drop at the next nightly for the house path
  (the API re-ranks the old rows meanwhile: Harrison's season value is 0 on the clone, so McPherson wins on the
  tie-break); the nightly stash writer's drop rule (the API decides claim / watch on read); the raw-total finder
  filter; team units' season value; the separate MFL roster-freshness line; a bench player projected 0.00 shows
  "0.00" (Jacobs on GoodGameBuddy's bench — "unknown is not zero" wants a dash: next pass); `ops.events` (designed);
  usage retention; the console Home's page guide lacks the Usage page.


### U-1 2026-10-03 — usage tracking (plan § 17 E; branch `dev/U1`, clone `league_lab_m1`)

* **The store.** `scripts/hosted_usage.sql` (new, plain SQL, idempotent): schema `usage`, table `usage.events (at
  timestamptz, screen text, league_key text, roster_id int, platform text, version text, session text)` with checks
  that refuse anything but a route word, a league key, a team number, `sleeper`/`mfl`, a release stamp and a 32-hex
  id; an index on `at`; `USAGE` on the schema and `INSERT, SELECT` on the table for `league_lab_app` (no update /
  delete). The sync's marked block runs it after the restore, in its own transaction, on the same owner connection —
  no new secret — and a failure only warns. The sync drops `analytics`, `analytics_seeds`, `ops` only: in a rolled-back
  transaction on the clone, the three `drop schema … cascade` left `usage.events` and its row in place.
* **The write.** `POST /api/usage {screen, league, roster_id}` → 204 always (gated; `LEAGUE_LAB_USAGE=off` writes
  nothing and sets no cookie). The server adds the time, the platform (`platforms.platform`), `/api/health`'s version
  and the day's session (`ll_usage`: random 32-hex, HttpOnly, SameSite=Lax, path `/api/usage`, Max-Age = seconds to
  midnight New York). The row goes on a bounded queue (1,000) that one writer thread drains: `db.write_one` = `BEGIN;
  SET TRANSACTION READ WRITE; INSERT; COMMIT` on its own connection (`application_name` `league-lab-usage`), one
  retry on a dropped connection; the role keeps `default_transaction_read_only = on` (a plain INSERT as the role still
  fails: `ReadOnlySqlTransaction`). Limits: a token bucket per session (1 a second, bursts of 5 — a strict 1/s dropped
  the About view after My Week on the live server: 2 beacons, 1 row) and 20 a second in all.
* **The web.** `web/src/lib/usage.ts` `countView` (sendBeacon, `text/plain`; keepalive fetch otherwise; the same
  screen + league + team twice in a row counts once), one marked `$effect` in `App.svelte` (after sign-in only); the
  notice at the foot of About (one marked line in IF-4's file).
* **Reading it.** `GET /api/usage/summary?days=7` (gated, `no-store`): views per screen per day, views / leagues /
  sessions per day, by screen, totals, the process counters; `ready: false` before the table exists. The console's
  page `app/pages/99_Usage.py` (the same questions, 7 / 14 / 30 days, the answer first).
* **Evidence.** The live API on :8754 (gate on, fixtures): no beta cookie → 401; signed in, a `text/plain` POST →
  204 + `Set-Cookie: ll_usage=…; HttpOnly; Max-Age=17420; Path=/api/usage; SameSite=lax` at 19:09 ET (4 h 50 min to
  midnight); the rows carry `waivers · 1389709692405551104 · 6 · sleeper · 19d01fab9735 · <id>` and `trades ·
  mfl:70587 · 8 · mfl`, the `x-forwarded-for` IP nowhere. The built web app against it (Playwright, 375 and 1300): sign in → My Week → About →
  Back = 3 beacons (`ping`), 3 rows, 0 limited, 0 failed. Size: 168 bytes a row with its index (10,000 rows = 1.6 MB).
* **Tests.** `api/tests/test_u1.py` (21; the database ones apply the SQL file themselves, twice, and delete their
  rows); `web/e2e/u1/` 2 × phone (375) / desktop (1300) on fixtures. `cd api && uv run pytest`: 423 passed, 2
  skipped, 3 failed — the three clone scoring checks (`test_ic1` × 2, `test_ic_po`: no `*_tds_10p` columns);
  `npm run e2e:fixtures` 176 passed (172 + 4); lint / typecheck / build clean; ruff clean. Local setup: `docs/HOSTING.md` § "Usage",
  `docs/SETUP_RUNBOOK.md` (one optional line). The clone `league_lab_m1` is owned by `postgres`: the pipeline role was
  granted `CREATE` on it (as on the Mac, where it owns the database) so the test can apply the file.

### IF-1 2026-10-03 — value the bench before prescribing drops (review § Priority 2)

- **Engine** (`src/league_lab/waivers.py`): `DropCost` / `drop_cost` / `drop_pieces` / `choose_drops`. A drop costs the
  most (never the sum) of `lineup_loss` (with the add on the roster), `depth_lost`, `future_starts` (above the wire),
  `season_value` (`price_by_player`'s rule, against the best free agent at his position) and `upside`; the best drop
  per claim is the cheapest (ties: the starter the claim replaces, then the fewest points); moves ordered by net gain;
  `is_worthwhile` = net ≥ 1 this week or ≥ 3 over the horizon. `sweep_roster` (nightly + on demand) writes 14 new
  columns (`COST_COLUMNS`; `_write` adds them with `alter table … add column if not exists`; `MOVE_COLUMNS` = the
  base DDL, unchanged). Definitions: `docs/METRICS.md` § "Drop cost".
- **API** (`decisions.py`, `# ---- IF-1` blocks): every move carries `drop_cost` (pieces), `net_weekly_gain`,
  `net_horizon_gain`, `is_worthwhile`, `alternative_drop`, `drop_why`; `no_worthwhile_move` ("No claim is worth a
  roster spot this week"); stash rows `stash_action` / `watch_words`; a mart without the cost columns is re-ranked on
  read (season value + upside); `best_waiver_move(league, team)` for IF-2. "He sits anyway" is gone.
- **Roster 6 (GoodGameBuddy), before → after** (clone 2026-09-26): Carlson's best drop Harrison → **McPherson**
  ("Drop McPherson: Carlson replaces him at K. Dropping Harrison Jr. instead gives the same gain: he projects 79
  season points, 43 fewer than the best free-agent WR (0 above the waiver wire); McPherson goes first …"); the best drops
  of the listed claims {Harrison} → {McPherson, Cousins, Harrison}; the three strongest 3 → 2 (the Falcons defense,
  +0.44 over weeks 4–7, is under the worthwhile bar); the home action "Claim C.J. Stroud,
  drop Marvin Harrison Jr." → "…, drop Kirk Cousins"; every stash "drop Harrison" → "watch" (no drop: the scenario
  adds +0.0 over weeks 4–7). Gains unchanged (13.46 / 9.82 …): only the drop, the order and the words moved.
- **Tests**: `tests/test_waivers_if1.py` (8, synthetic), `api/tests/test_if1.py` (6, needs_db on roster 6 — the engine
  in memory, read-only, the API's rows monkeypatched); `test_ib2.py` words updated ("he sits anyway" → the cost words);
  `test_decisions.py`'s mart-vs-on-demand parity re-ranks a pre-IF-1 mart with the on-demand pieces.
- **Not done**: the mart's select (PO, `mart_waiver_moves.sql`: add the 14 columns) and the nightly re-run; the nightly
  stash writer (`upside_for_roster`) still picks its drop by B3's rule (the API decides claim / watch on read);
  absence rates are documented constants, not fitted; no `web/e2e/if1/` (the screen changes are the cost line's
  words and the stash's watch line).

### IF-3 2026-10-03 — historical matchup evidence connected to current personnel (review § Priority 1)

* **Why**: the decision-quality review (`docs/reviews/2026-10-03-decision-quality-review.md` § Priority 1): Williams vs
  Tuten (Scrubs roster 6, week 4) showed Carolina's WR rank with no word that its starting corners Jaycee Horn and Mike
  Jackson had gone on injured reserve (Panthers, Sept 30), while Matchups listed the replacements as unranked.
* **What**: `research.matchup_evidence` (the object in `INTERFACES.md` § IF-3; `docs/METRICS.md` § Matchups "Current
  personnel"): `history` (rank, games, period, scoring, not opponent-adjusted, the adjusted rank beside it), `changed`
  (`cards.corner_personnel`: the regulars — ≥ 50% of the leading corner's coverage snaps this season — vs the depth
  chart as of the game; a listed starter who cannot play per the overlay gives his spot to the next corner on the same
  depth chart; missing regulars with status, source and date), `implication` (less representative / stands / unknown /
  unchecked), `forecast_treatment` "contextual only; not in the forecast" (the projection's opponent inputs are
  `opp_allowed_std`, `opp_allowed_l4`, `opp_rank_std`, `f_opp_allowed_diff`, `league_allowed_avg` and the betting lines;
  the `pn_*` personnel inputs are the player's own team — a test parses `BASE_FEATURES`), two sentences. On
  `/api/compare` (both sides; the verdict drops a matchup lean from a less representative rank), the player card
  (`matchup_evidence`, shown under "Next:" by `lib/card.ts`), `/api/matchups/cb` rows (WR). The cards: a changed
  defense's matchup piece scores 0 under its own kind, `_tiebreak` never picks the matchup then, the coin flip says "the
  matchup rank does not settle it this week: Carolina's starting corners changed (…)", and `decision_cards`' frame
  carries `matchup_uncertain` (IF-4's "No clear upgrade" words). The API sets `cards.STATUSES = availability.now`; the
  console reads the depth chart only. Web: `components/MatchupEvidence.svelte` (the two sentences, a "Corners changed"
  badge, "The evidence" behind a disclosure) on Compare ("The matchups this week") and Matchups' cornerback rows (when
  changed); "· corners changed" beside the rank under each compare card. No number moves.
* **The review's case** (main-database clone 2026-09-26 + the as-of overlay fixture `api/tests/fixtures/espn_if3`:
  Horn and Jackson IR, ESPN, Sep 30): before — "Williams projects 0.26 more (9.98 vs 9.72); the matchup leans Williams:
  his defense ranks #17 vs WRs once the offenses it faced are counted, Tuten's #24 vs RBs."; after — "Williams projects
  0.26 more (9.98 vs 9.72); the matchup rank does not settle it this week: Carolina's starting corners changed (Jackson
  and Horn are on injured reserve)." with Evans (left, for Jackson), Lee (right) and Smith-Wade (slot, for Horn)
  expected, Evans and Lee "unranked (insufficient snaps)". Without the overlay the clone's depth chart still starts
  Jackson and Horn: "the historical rank stands: the same corners". Projections unchanged (9.98 / 9.72).
* **Tests**: `api/tests/test_if3.py` 10 (the forecast's feature list; the coin flip before / after on the review's live
  numbers; the matchup piece as a fact, not a reason; the words; the compare / card / cornerback rows / cards' flag on
  the clone with the fixture overlay; the "stands" case; the depth-chart-already-moved path on stand-in SQL). API suite
  410 passed, 3 failed (the three known clone scoring checks: `test_ic1` ×2, `test_ic_po` ×1), 4 skipped.
  `web/e2e/if3/` 4 (Compare and the pane's matchup section, phone 375 / desktop 1300) on answers recorded from the API
  (`web/fixtures/if3/api_if3.json`, team and manager names replaced).
* **Not done / for the PO**: the `ops.events` store is a design (the hand-back), not built; the hosted copy gets
  `mart_matchup_cb_context` (read for the first time) on the next nightly publish (until then the replacement corners
  are not named; the depth chart diff still works); receivers only (no front-seven check for running backs).

### IF-2 2026-10-03 — trades compete with the simpler alternatives (branch `dev/IF2`, clone `league_lab_i0b`)

* **Why**: the decision-quality review § Priority 3 (`docs/reviews/2026-10-03-decision-quality-review.md`): the
  Finder's headline (+9.8 over weeks 4–7 live) lost to a free claim for an open spot (+11.4) and nothing said so; the
  headline and the first card were different trades; the calculator said "you get more season value" next to "492
  rest-of-season points for 164" without naming either concept.
* **Delivered**: one ladder per roster and window (`decisions.best_alternative`: standing pat, the best legal waiver
  move — IF-1's `best_waiver_move` when merged, guarded; today the open-spot fill / best add-drop on `ctx.fa_pool`);
  the Finder ranks trades by `beyond_alternative` (those that beat it first), `rank` 1 = the headline = the first card,
  `demoted` + "the trade does not beat it on starter points" + a reason only from the numbers (`other_objective`),
  `ordering.words`, a week strip per card (`strip`: both sides, `trades.package_weeks`); the calculator carries
  `alternative`, `beyond_alternative`, `alternative_words`, `strip`, `values` (the five concepts,
  `trades.VALUE_CONCEPTS`), the raw rest-of-season line labelled "all positions added up — not a fairness test", the
  warning on season value above replacement (`calc_sanity`). Web: `Trades.svelte` (the first card is the headline,
  the alternative line, the ordering line, the mark, the strip), `TradeCalc.svelte` result (the alternative, the
  strip, the labels), `decisions/WeekStrip.svelte` (new).
* **Evidence** (70587 team 8, fixtures + ESPN overlay, `api/tests/test_if2.py` 13 passed): best alternative = the
  Atlanta Falcons defense for the open spot, +12.81 over weeks 4–7 (1.20 / 0.80 / 0.48 / 10.33) = the Waivers
  screen's top claim. Finder top three **before**: Houston Texans QB → Kansas City Chiefs QB (+1.76 / +5.53; the first
  card), Chicago Bears QB → Kansas City Chiefs QB + Rice (+5.12 / +14.59; the headline), Corum → Downs (+1.43 / +5.80).
  **After**: Bears QB → KC QB + Rice (+14.59, beyond +1.78; headline = first card), McCaffrey → Achane + Coker (+7.99,
  beyond −4.82, below the claim; "more season value above replacement: 121 for 61"), Corum → Downs + Johnston (+6.66,
  −6.15). The review's headline trade (Houston QB → Rice + Carolina QB) on the fixture: +1.70 / +7.86 (live +1.0 /
  +9.8) → "the trade does not beat it on starter points" (−4.95). "Houston QB + Tuten for Rice": the warning was "you
  give 493 rest-of-season points for 134: 359 more, over 25% of what you give"; now none (Houston QB has no season
  value: not judged), the raw line labelled, "Season value above replacement: you give 14, you get 7 (about even). You
  give 2 players for 1: 1 roster spot freed. Not counted (no season projection): Houston Texans QB." Trade gains
  unchanged everywhere. `web/e2e/if2/` 2 × phone (375) / desktop on answers recorded from the API
  (`web/fixtures/if2/api_if2.json`).
* **Open**: team units (TMQB / TMPK) have no season value on demand (no `market` row), so the verdict's "season value"
  clause and the warning leave them out (the words now say so); the Finder's sanity rule (a) is still the raw
  rest-of-season totals (a PO call: switch it to season value above replacement — it would change which trades are
  suggested); IF-1's `best_waiver_move` covers the next four weeks only (the other windows use the fill).


### IF-4 2026-10-03 — clarity that exposes the difficult decisions (the decision-quality review § Priority 4 and its table; branch `dev/IF4`, clone `league_lab_i0a`, read only)

* **Why**: the fourth outside review (`docs/reviews/2026-10-03-decision-quality-review.md` § Priority 4): GoodGameBuddy's
  home said "nothing to change" while Williams vs Tuten at FLEX was 0.22 apart — "No clear upgrade" is the accurate
  conclusion; a correct optimizer output does not remove the uncertainty. Plus the table of language fixes and the
  I-E leftovers.
* **My Week** (`myweek.build_actions`, both paths): `review` — one **No clear upgrade** line per coin-flip card with
  nobody hurt that the submitted lineup already follows (or differs from by under half a point), smallest margin
  first, at most 3: "Tuten or Williams at FLEX: a coin flip, 0.3 points apart; your lineup has Williams — no clear
  upgrade." + Compare ›; IF-3's `matchup_uncertain` (read from `cards.decision_cards`' column or the tiebreak) adds
  "the matchup rank does not settle it". `set_line`: "No clear upgrade elsewhere." when review lines exist, "The rest
  of your lineup is set." (the "— nothing to change" tail dropped) with actions, "Your lineup is set — nothing to
  change." only when there is neither. `changed` — **What changed**: the overlay's moves since the build (source,
  checked time) then the news of the week's players (the best lineup's starters and the submitted lineup) from the
  last 24 hours, the item about him first (`news.recent`: the feed's cache and bucket, reads side by side, a 1 s
  budget), at most five; "Nothing has changed since the morning build." otherwise. Each starter row gains
  `margin_vs` / `margin_words` ("over Lloyd" from `cards.alternative`; "no eligible reserve: the slot would be empty").
  `/api/status` gains `updated_at`.
* **Web**: My Week renders the review lines after the actions, the set line, What changed under the edit link, the
  starters' table with the margin and its comparator, the bench expander with the bench and who can't play only, the
  footer "Updated 7 d ago ›" (the exact ET time and the feed names on tap); the lineup card no longer repeats the
  overlay's moves (What changed carries them; an answer recorded before keeps them there). The **pane** leads with projection,
  availability (+ news), signals, usage, the value's lineup line; "Week by week and season numbers", "Schedule" and
  "Game by game this season" behind expanders (`card.ts paneSplit`). The **player page** gains "Schedule"
  (`ScheduleTable.svelte`: week · opponent · projected, from the card's new `schedule`, the board's own numbers).
  **Compare**: bold only where it bears on the call (points rows always, usage rows only between two players of the
  same position; the legend says so), "Typical range 9–16", "Low-end / High-end outcome", "Share of team passes", "This season
  (2 games)" with the duplicated "Last 3 games" section dropped when it is the same games. **About / Waivers / decisions.ts / the console's
  cards**: "Typical range (the middle 50%)" for "Most weeks". The card's role line (`card.ts roleWords`, on the web:
  the API's card is pinned to the console page): "not enough games to say — 2 games so far …" before game 4, "role
  steady over N games" after; empty metric tiles defined ("Not available for this player …", first-read and red-zone
  denominators). The news line shows the item about him first (`news.ordered`: RotoWire, or the headline names him);
  an article-level headline is labelled "League news". The game log and Trends: "1.2 below what his opportunities
  suggest: an observed gap, not a forecast" (no "expect him to pick up", no "buy him while he is cheap"). The matchup
  rank in words: `cards.rank_words` / `lib/words.ts rankWords` ("12th-fewest WR points allowed"); applied to the
  console cards' small print and the schedule table — Compare's and Matchups' `#` lines are IF-3's (INTERFACES.md).
  Receivers / Trends: the dictionary's "Share of team passes", "Points suggested by his past opportunities".
* **Evidence — the review's case** (Scrubs roster 6 on the clone, built from its own rows: on 2026-09-26 Tuten was on
  roster 2, so his real row takes CeeDee Lamb's FLEX slot; Sleeper's lineup = the optimizer's). **Before** (`19d01fa`'s
  `build_actions` on the same frame): actions none, set line "Your lineup is set — nothing to change.", no review.
  **After**: actions none, review "Tuten or Williams at FLEX: a coin flip, 0.3 points apart; your lineup has Williams —
  no clear upgrade.", set line "No clear upgrade elsewhere.". Cards before = after: FLEX2 Jameson Williams 9.98 /
  Tuten 9.72 / 0.26 coin flip; RB1 Javonte Williams 12.65 / Lloyd 8.02 / 4.63; FLEX1 Olave 15.16 / Tuten 9.72 / 5.18
  (on the clone Williams projects above Tuten; on the review's day it was Tuten 10.02 / Williams 9.80 — the line names
  whoever the lineup has). Roster 6's real lineup: QB Cousins 14.74 "no eligible reserve" (was "Margin 14.74"), RB1
  "4.63 over Lloyd". Roster 2 with the ESPN fixture: What changed = "Justin Jefferson is out (ankle) — Michael Wilson
  starts at FLEX2", "Terrance Ferguson is on injured reserve (ankle) …" (Injury report (ESPN)), then "Justin
  Jefferson: Jefferson (ankle) has been already been ruled out … · RotoWire via ESPN". Jefferson's card news: the
  inactives story ("… DeVonta to sit …", newest-but-one) moves behind his two RotoWire items and reads "league". No
  number moved.
* **Tests**: `api/tests/test_if4.py` (7: the roster-6 case end to end (needs_db), the review rules on hand-built frames,
  What changed from the overlay fixture (needs_db), the empty words, the news order, `for_card` / `recent` on the
  fixture, the recorder of the e2e answers (skipped unless `IF4_RECORD=1`)); `test_ie1.py` set-line words updated
  (3 asserts: the tail; the tiny-difference case now has its review line). `web/e2e/if4/` (3 × 375 / 1300: the review
  line + set line + nothing changed + margins + bench-only + Updated; What changed; the pane's expanders, role words,
  schedule; Compare's bold rule, Typical range, the season once) on `web/fixtures/if4/api_if4.json`;
  `e2e/ib1`'s pane test opens the game log's expander first. Checks: **API 409 passed, 3 failed** (the three clone
  scoring-check tests: `test_ic1` ×2, `test_ic_po` ×1), 3 skipped (the recorder +2 as before); `test_n1`'s card order
  updated (the item about him first, `about` on each item); **root 986 passed, 2 skipped**; ruff clean; web lint /
  typecheck / build clean; **fixture e2e 180** (172 + 8: the full run 177 + the one IB-1 selector fix, then `if4` /
  `ib1` / `i0a` / `ie1` / `ia1` re-run green on the final build).
* **Open**: the MFL roster's own freshness line (I-E leftover) — not done; "status next to the name on every row" is
  the existing flag line under the name (OUT / IR chip, Questionable, locked, bye reason) — unchanged; Compare's and
  Matchups' `#21` / "#2 toughest" lines and the card's "Next: … ranks **#21** of 32" are IF-3's matchup lines (they
  take `rankWords` / `history.words`); IF-3's `MatchupEvidence` goes into the pane's projection section (a marked
  comment shows where); the What changed news reads up to ~10 ESPN copies on a cold My Week (the feed's bucket and
  cache; at most 1 s waited).

## N2 (Iteration 17) — PlayerWire briefs on the news line

### N2 2026-10-03 — PlayerWire first, ESPN fills (branch `playerwire-integration`)

* **Task**: N2 (plan § Iteration 17, "Still after: … the news feed"). Plan sections touched: § Iteration 17; HOSTING.md
  § 5 (a proposed extension, below); ANY_LEAGUE.md § "News". Design and operations: `docs/PLAYERWIRE.md`.
* **The § 5 question (Andrew)**: *a second writer on Neon — the Mac's `playerwire_sync.py`, as role
  `playerwire_writer`, writing only schema `playerwire` — next to GitHub Actions as the only writer of `analytics`,
  `analytics_seeds` and `ops` ("one writer per schema")?* Nothing is installed on Neon or the Mac until he says yes;
  the API shows ESPN only while the schema does not exist.
* **Schema + role** `scripts/init_playerwire_schema.sql` (`make playerwire-schema` = `playerwire_sync.py init-schema`,
  psql with the password read by `\getenv`, never on argv): `playerwire.briefs` (PK `brief_id`; `version`, `status`,
  `pw_player_id`, `primary_sleeper_id`, `primary_gsis_id`, `category`, `headline`, `news`, `analysis`,
  `verification_status`, `published_at`, `updated_at`, `evidence_url`, `evidence_publisher`, `evidence_published_at`,
  `payload` jsonb, `synced_at`, `deleted`, `deleted_reason`, `deleted_at`; check `briefs_withdrawn_text_gone`),
  `playerwire.brief_players` (`brief_id`, `pw_player_id`, `sleeper_id`, `gsis_id`, `role`), `playerwire.sync_state`
  (`id = 1`, cursor, watermarks, last sync / error). Owner `playerwire_writer`; `league_lab_app` gets USAGE + SELECT
  + default privileges. Idempotent (run three times on the stand-in: notices only).
* **Sync** `scripts/playerwire_sync.py` (stdlib HTTP + League Lab's own `psycopg` 3 and `python-dotenv` from
  `uv.lock`; no new dependency): PlayerWire's reference consumer on Postgres — bootstrap from a pinned snapshot
  (every page, then one transaction with the cursor; live rows the snapshot lacks → withdrawn
  `absent_from_snapshot`), change pages (each with its cursor), version guards (never over a newer version, never
  reviving a tombstone of the same or newer version), tombstones that keep the row and clear headline / news /
  analysis / evidence (payload = the tombstone), 410 / 409 → bootstrap again (on a later snapshot page: restart the
  snapshot), 429 / 503 → `Retry-After` (1–120 s, 5 tries), synthetic briefs skipped, an advisory lock, refuses any
  role but `playerwire_writer`. `sync --once` (launchd), `--dry-run` (a scratch copy in memory), `status`,
  `init-schema`. `scripts/launchd/com.leaguelab.playerwire-sync.plist` (every 900 s, `RunAtLoad`, the refresh plist's
  `__ROOT__` convention, `logs/playerwire-sync.log`). Make: `playerwire-schema`, `playerwire-sync` (`DRY=1`),
  `playerwire-status`; `make lint` now also lints `scripts/playerwire_sync.py`.
* **API** `api/league_lab_api/playerwire.py` + `news.py`: `news` = PlayerWire's items first (his briefs and the briefs
  naming him as related, mapped through `analytics.player_id_map` by Sleeper id, else gsis id, a disagreement shown to
  nobody; live, published, 14 days, newest first, ≤ 3; `{headline, date, source: "<publisher> via PlayerWire", url,
  summary, kind: "playerwire", verification, related}`), then ESPN's (`kind: "espn"`) to fill 3; ESPN not called when
  PlayerWire fills all three. `LEAGUE_LAB_PLAYERWIRE=off`; `LEAGUE_LAB_NEWS=off` still turns the whole line off;
  fixture mode off unless `LEAGUE_LAB_PLAYERWIRE_FIXTURES`. No schema / no grant / marts mid-restore → ESPN only, one
  warning, a 60 s pause. Cached 60 s (`db.query` gained an optional `ttl`). `/api/status` → `news.playerwire`
  (`rows`, `withdrawn`, `newest_published_at`, `unmapped`, `conflicting`, `last_sync_at`, `last_error`). The hosted
  relation audit is unchanged (`playerwire` is not one of its schemas; `analytics.player_id_map` was already named).
* **Web**: `NewsLine.svelte` — a brief's news under the headline (muted, full width, ≤ 220 characters at a word, the
  whole text in `title`) and a verification tag after the source (`bg-accent-soft`; disputed `bg-warn-soft`); ESPN
  items unchanged. `lib/api.ts` `NewsItem` (+ `kind`, `summary`, `verification`, `related`), `lib/card.ts`
  `newsLine` (+ `summary`, `summaryFull`, `verification`, `SUMMARY_MAX`). About: one sentence
  (`about-news-playerwire`). No "What's new" line yet: PlayerWire has no real source, so nobody sees a brief yet — add
  it with the first real brief.
* **Tests**: root `make pytest` **963 → 982 passed** (25 → 26 skipped: the Postgres end-to-end test without
  `LEAGUE_LAB_PLAYERWIRE_TEST_DSN`), `make lint` green. `tests/test_playerwire_sync.py` 19 (+1 on Postgres): payload →
  row and players; bootstrap in one commit; synthetic skipped; changes in order, stale versions, idempotent replay;
  tombstone keeps the row with no text, cannot be revived by the same version, revived by a newer; tombstone for an
  unseen brief; cursor only with a committed page (an injected failure on page 2); a failed bootstrap writes nothing;
  410 → bootstrap and `absent_from_snapshot`; 409; 410 on a later snapshot page restarts it; wrong filter signature;
  429 / 503 Retry-After (7, 120 cap, 1); 401 / outage errors; unreachable API; writer URL template carries no secret;
  config errors; `--dry-run`; the schema SQL never names the marts and the nightly never names `playerwire`. API
  (`cd api && uv run pytest`, no database here) **156 → 173 passed**, 224 → 223 skipped, the same 2 failures as
  before this change (`test_ic3.py::test_user_leagues_carry_cards` / `test_check_route_wired` need a database and
  lack `needs_db`); `api/tests/test_n2.py` 15 (+1 `needs_db` card test): PlayerWire first / newest first / ESPN not
  asked at 3; ESPN fills to 3; no brief → ESPN as before; 14-day cutoff and bad dates; withdrawn hidden; unmapped and
  conflicting hidden but counted; the identity rule; `LEAGUE_LAB_PLAYERWIRE=off` → ESPN only; `LEAGUE_LAB_NEWS=off` →
  nothing; fixture mode never reads a database; the status block; the database path through a stand-in `query`
  (one per brief, own over related, http link dropped, params and TTL); missing schema → ESPN only, logged once, the
  pause, recovery; database status counts; the audit does not see `playerwire`. `test_n1.py`'s card-shape test now
  expects `kind`. Web: `npm run lint` (eslint + svelte-check + tsc) green; `npm run e2e:fixtures` **160 passed** (150 at Wave I-D)
  (`web/e2e/n2/` 5 × phone / desktop; N1's 10 unchanged).
* **Evidence on real servers (this sandbox)**: a Postgres 16 cluster standing in for Neon (a non-superuser
  `neondb_owner` with CREATEROLE, as on Neon): the schema SQL as that owner — exit 3 without the password, then
  "playerwire schema ready: 3 tables, owner playerwire_writer", then again (notices only). Isolation:
  `playerwire_writer` → `permission denied for schema analytics` (read and create) and `… schema public`;
  `league_lab_app` insert → `cannot execute INSERT in a read-only transaction`. **PlayerWire's own server** (read-only
  use of `/home/claude/playerwire`, its demo database in the scratch directory): preview mode — dry run (1 brief, 0
  with ids, nothing written), real run without `--allow-synthetic` (0 written, 1 synthetic skipped), with it (1),
  then a second brief published + the first withdrawn → `upserts 1, deletes 1`: the withdrawn row `version 2,
  withdrawn, deleted, headline / news / evidence NULL, payload without the player's name`; the new one with its
  related player in `brief_players`. Production mode on another port: no key → `HTTP 401 missing_credentials`
  (recorded in `sync_state.last_error`); with the key → `409 cursor_filter_mismatch` (the preview cursor) →
  bootstrap again, 0 eligible briefs, the synthetic one marked `absent_from_snapshot`. The API's SQL on the stand-in
  as `league_lab_app`: Jefferson's card = his own brief, a related mention (`related: true`) and a Sleeper-only brief;
  a 16-day-old, a conflicting, an unmapped and a withdrawn brief hidden; status `rows 6, withdrawn 1, unmapped 2,
  conflicting 1`. The nightly's `drop schema analytics cascade` left the 7 brief rows; during the gap the card
  answered [] from PlayerWire with one warning (`DataNotReady: relation "analytics.player_id_map" does not exist`).
* **Data touched**: none of Andrew's. Neon, Render, GitHub Actions and the Mac are unchanged until Andrew runs
  `docs/PLAYERWIRE.md` § "Set up".
* **Limitations**: freshness bound by the Mac being awake and PlayerWire's server running (≤ ~16 minutes when it is);
  a withdrawal leaves the card on the next sync (+ ≤ 1 minute); only published, hand-reviewed, non-synthetic briefs
  (none exist yet: PlayerWire has no real source); PlayerWire first even when ESPN is newer, no de-duplication across
  the two; unmapped players' briefs invisible; no retention (≈ 5 MB per thousand briefs, outside the nightly's
  480 MB budget, inside Neon's 0.5 GB).
* **Next**: Andrew's answer on § 5, then § "Set up" (five steps); after the first real brief, a "What's new" line.

## Wave I-G (Iteration 17, part G)

### PO merge — Wave I-G, 2026-10-04 (Sunday, 03:00–07:00 ET, overnight; Andrew asleep)

* **Why**: Andrew (02:50 ET): "You've got time for a big push iteration-wise overnight while I sleep. Let's take
  advantage and knock out a big chunk of the roadmap/backlog." The backlog after I-F, all of it but Wave J (the
  licence): the brief is `scratchpad/waveIG/BRIEF.md` (six Opus devs; M4 ran first alone — the PO's mistake, a
  blocking spawn — then M5 / IG-1 / IG-2 / V-1 / IG-3 in parallel, 75–100 min each).
* **Delivered** (the hand-backs below; integration branch `integ/IG`, merged into `main`): **M4** the record's
  `pricing` column (`flat` | `ev`) on the three writers and `mart_projection_record` / `mart_player_week_projections`;
  `scoring.ev_pricing()` is a mode — the nightly writer pins the env (default flat), a request follows **the record's
  own label per week** (`ev_for_week`; the env overrides either way), so My Week, Waivers, Trades and the card can
  no longer disagree with Trends and the record over the bonuses (IB-0's class of bug closed by construction);
  "Sleeper's projection" and the market line priced the same way; `/api/record` `pricing` and About / the console's
  sentence; a `signals.scenarios` bug found on the way (the scenario base priced without the position — the first EV
  nightly would have failed its dbt test); **the flip commit shipped** (`LEAGUE_LAB_EV_PRICING: "1"` on the nightly's
  `project` step only — **Render stays untouched**: an env there would price a frozen week by the env instead of its
  label). **M5** v3.1 measured, every switch **off**: the ranges' target on graded points (QB keep is marginal: −0.0066
  interval score, 2 of 3 seasons; RB / WR / TE no change), the fringe level **drops** (its sign flips by era), the
  cold-start prior **keeps** at RB / WR / TE (cold rows' MAE −0.16 / −0.31 / −0.30; 4–5 of 5 seasons) but as wired it
  moves `ops.projections` and not the stat line — on-demand requests would show the unblended number (IB-0 again), so
  it waits for the line move (v3.2 lead, with "veterans on a new team are over-projected like rookies, WR −0.95").
  104 harness rows in `feature_experiments.csv`. **IG-1** team units' season value (`decisions.unit_market`: a unit
  against the best free unit of its kind, never a player — Houston QB 355 vs the free Arizona QB 378 = 0 above
  replacement; the verdict and the warning count units), the Finder's rule (a) on **season value above replacement**
  (`trades.value_gap`, ti1.2; before / after lists for Scrubs 6 and 70587 team 8 in the hand-back — the headline
  trades did not move), **unknown is not zero** (`value: null` + `no_projection` from the API, a dash and "no
  projection" on every screen and the console, My Week's `unvalued_words`; nine coercions to 0 removed, listed).
  **IG-2** the event store `events.events` (the review's § Engineering requirements: kind / player / team / game keys,
  source URL, published / effective / ingested, status, `superseded_by`, a unique fingerprint; the `usage` pattern:
  `scripts/hosted_events.sql` run by the sync, never dropped; U-1's writer thread), written by the overlay (each
  status move, with the report's time), the ESPN news items a screen showed and PlayerWire's briefs; read by "What
  changed" (a brief shows there now, each line with its source and `event_id`) and by `matchup_evidence.changed`
  (the missing corner's event, URL and date); `/api/status` `events`, `GET /api/events` for QA. **V-1** the
  validation harness: `ops.lineup_record` (the app's lineup per roster-week frozen at the week's first kickoff —
  the projections' freeze rule; 2026 weeks 1–4 rebuilt from the frozen projections and labelled `reconstructed`),
  `mart_decision_record` / `mart_decision_calls`, `league-lab validate`, `/api/record` `decisions`, About's block and
  the console's Record section: **the app's edge** (our lineup − the submitted), **regret** (the hindsight optimum −
  the submitted), the coin flips' calibration, news-affected cases apart. **IG-3** the stash writer's drop follows
  `choose_drops` (`ops.waiver_upside` + 5 columns; the API shows the writer's call; roster 6's drops {Harrison} →
  {McPherson, Cousins, Harrison}; all 83 stashes are "watch"), MFL's own roster-freshness line, **the waiver
  deadline** under Waivers' title (Sleeper's `waiver_type` / day / hour read as Pacific — one constant,
  `SLEEPER_WAIVER_TZ`; MFL "see MFL" when the export has no time), the MFL grade's qualification next to the headline
  grade, usage retention 180 days, the console Home guide's Usage page.
* **PO, on the merge**: five doc conflicts and two `api.ts` end-of-file blocks (keep both; `WORDS.md` theirs first so
  IG-3's rows stay in their table); the ruff B010 in `research._load_matchups` (the PO's own, from the N2 merge);
  `metric_registry.csv` rows `decision_edge`, `decision_regret`, `call_calibration` (dr1.0), `unit_season_value`;
  the main database migrated (`db migrate`: `ops.lineup_record`, the `pricing` columns), `league-lab validate`,
  `league-lab waivers` (the stash call), the wave's seeds and models built (`PASS=74`), `hosted_events.sql` applied
  locally; the hosted copy gains `analytics.mart_decision_record` (56 kB), `mart_decision_calls` (88 kB),
  `ops.lineup_record` (576 kB) and the `events` schema (~500 B a row). **Checks on the merge**: root **1082 passed /
  2 skipped**, API **548 passed / 5 skipped** (test_ic1 included, on the main database), e2e **222 passed**, ruff /
  svelte-check / eslint / build clean; the fixture API on the main database with the store on: 151 events on the
  overlay's first copy, Jefferson's news as events, `/api/events` lists them; `/api/waivers` "Claims run Wednesday
  3:00 AM ET (rolling waivers); players lock at their own kickoff — the next game starts Sunday 9:30 AM ET"; the
  MFL grade note; Jacobs `value: null`.
* **Decisions the PO took (Andrew may reverse)**: (1) **the flip ships with the wave** — the Monday 07:37 nightly
  prices weeks 5–18 at their odds; if the push lands before Sunday's 07:37 run, Sunday's does (week 4 is frozen and
  keeps its flat rows either way: M4's clone build moved 0 week-4 rows); nothing to set on Render; rollback = delete
  the line and re-run. (2) **v3.1 stays off**: the QB range keep is marginal and the cold-start prior needs the line
  move first. (3) **ESPN headlines are kept** in `events` (headline, date, source, link — the four fields the cache
  file already holds; `LEAGUE_LAB_EVENTS_ESPN_NEWS=off` on Render holds them back; ESPN's terms are still unread —
  `docs/ESPN_TERMS.md`). (4) The decision record's **first numbers are unflattering and small-sample**: on the
  rebuilt weeks 1–2 our lineups would have scored **1.2 points a team a week less** than what Scrubs' managers
  started (−23.5 over 20 team-weeks; the hindsight optimum beat the started lineups by 15.7 a team a week), the
  dynasty −148 in week 1 (Andrew's own roster −35: three starters differed) and +30 in week 2; the coin flips landed
  59% our way (52% expected, 34 calls). Week 1's board is the model's weakest (no in-season data) and the rebuilt
  weeks read the final injury report; the real record starts at week 5's kickoff. Nobody should quote "the app's
  edge" before saying so — About says it in those words.
* **The nightly's trigger (2026-10-04, 09:45 ET; Andrew: "sounds like we have a major issue if github just starts and
  stops at its own convenience")**: it does — every scheduled nightly since 2026-09-30 started 3.5–6 hours late and
  today's had not started by 09:45 ET. `ops/nightly-trigger/` is a Cloudflare Worker that dispatches the workflow at
  07:37 America/New_York and re-checks at 09:37 / 11:37 (HOSTING § 5 "The trigger"); tested offline against a mocked
  GitHub API (EDT, EST, midnight, the three paths). Needs Andrew's fine-grained token (Actions: read and write, one
  repository) as the Worker's secret; the PO creates the Worker in the dashboard on his yes.
* **Not done / next**: the cold-start prior onto the stat line (v3.2), `validation._news_starters` on IG-2's events,
  a per-team decision view and MFL leagues in the record, Waivers' drop cost on units, the console's stash words on
  `stash_action`, the Team page's MFL freshness line, `daily_waivers_days`, events retention (30–80k rows a season;
  prune superseded news after 120 days), `game_key` / a depth-chart writer, the record's Sleeper side priced at the
  odds (`ops.market_record` proposal), `why.weights` reading the week's mode. Then Wave J on the licence.

### M4 2026-10-04 — the record's pricing column, and the request side follows the record (branch `dev/M4`, clone `league_lab_m1`)

* **Task**: Wave I-G M4 (plan § 17, "Monday's flip of `LEAGUE_LAB_EV_PRICING` with M3's `pricing` column"); METRICS
  § "Expected-value pricing" → "The record's pricing column" (new); INTERFACES.md § M4.
* **Why**: M3 made one pricing entry point, but the flag still had to be set on two machines (the nightly and Render).
  For the length of a deploy, one side would have priced the bonuses at their odds and the other all or nothing:
  IB-0's trust bug coming back through the flag. Now the record says how it was priced, and every request prices
  the same way.
* **Delivered**:
  * **The column.** `pricing` (`flat` | `ev`; NULL = flat, every row before Wave I-G) on `ops.projections`,
    `ops.projection_ranges` and `ops.projection_backtest`. It is written by `project` / `backtest` from
    `pricing_engine` (`spec` → `ev`). K / DEF rows are `flat`. A range unit copied from the record keeps the record's
    label. The column is added by the writers' DDL, `db migrate` and the two marts' pre-hooks.
    `mart_projection_record.pricing` holds one label per league-week (`flat` | `ev` | `mixed`; season rows: the
    scored weeks'). `mart_player_week_projections.pricing` holds the row's label. Both have schema tests (not null,
    accepted values).
  * **The mode** (`scoring.pricing_mode` / `ev_pricing` / `ev_for_week`), in this order:
    1. the nightly writer's pinned mode: `@pinned_writer` on `project` and `backtest`, the env alone, default flat;
    2. `LEAGUE_LAB_EV_PRICING` when it is set and non-empty (an override in either direction);
    3. the newest build's label in `ops.projections` (Sleeper leagues, QB–TE; one query, cached ten minutes; a
       failure gives flat);
    4. flat.

    Per week, a week the record holds is priced by its own label, so a frozen week keeps the label it was priced
    with. `anyleague.price_lines` uses the mode per row (the frame's season / week, or the board's week from
    `price_board`). `price_week`'s cache key carries the mode. The API reads the record through its read-only
    `db.query` (`ondemand._pricing_rows`). The console and the CLI read it through `league_lab`'s connection, app
    role first.
  * **"Sleeper's projection"** (`why.market_points`: the card, rest of season, My Week, the Finder's market sanity
    bound) is priced with `price_projected` in the week's mode instead of `compute_points`. A K stays flat.
  * **The record says which.** `/api/record` gives every week row a `pricing` and adds `pricing: {now, by_week,
    sentence}`. About shows the sentence under the record's answer, e.g. "Weeks 1–4 were priced flat; from week 5
    the bonuses are priced at their odds." Nothing is shown for a league without a bonus. The console's Record page
    shows the same sentence (`scoring.record_pricing_sentence`, one source for both).
  * **Fixed on the way.** `signals.scenarios` priced the scenario base without the position. Under EV the base used
    the pooled curves and missed the stored projection by 0.04, so the scenario step failed and kept yesterday's
    flat rows. `scenario_base_is_the_projection` then failed in the projection-marts step. **The flip would have
    turned the first nightly red.** The position now rides along. Under EV the base is 0.00e+00 from the stored
    projection on 14 rows; in flat mode nothing moves.
* **Interfaces**: INTERFACES.md § M4 (the column, `pricing_mode`, `pinned_pricing`, `set_record_reader`, the
  `/api/record` keys; for V-1: `ops.lineup_record.pricing` = the league-week's label).
* **Evidence** (clone `league_lab_m1`; `league-lab project` run three times: EV, EV again after the scenario fix, then
  flat with the env unset while the record said EV):
  * **The flat rebuild reproduces the pre-M4 board to the bit**: 19,822 of 19,822 player-weeks and 396 of 396 lineup
    totals, max |Δ| 0.0. The writer did not follow the EV record.
  * **EV build against flat:**
    * Scrubs: 0 of 9,911 player-weeks moved, 0 of 180 lineup totals.
    * The dynasty: 7,464 of 9,911 player-weeks moved, all in weeks 5–18, by −1.26 to +1.63. Frozen week 4 did not
      move.
    * Lineup totals in weeks 5–18: +4.97 per roster-week on average. Andrew's roster 12: week 4 111.15 → 111.15
      (frozen), week 5 118.12 → 123.24, week 6 107.51 → 111.93. Scrubs roster 2: unchanged.
    * Labels: dynasty weeks 5–18 `ev`, weeks 1–4 NULL; Scrubs and every K / DEF row `flat`. The dynasty reference's
      ranges carry the dynasty board's label week by week, and the other references are `flat`.
  * **M3's numbers under the record's mode** (env unset, the record saying week 4 flat and the newest build EV):
    week 5's top 24 by QB +1.01, RB +0.71, WR +0.73, TE +0.18; 96 players, +0.66, none down. Scrubs is identical to
    the bit. Josh Allen's week 4 stays at 30.24 (its frozen label) and is 31.68 when week 4 is labelled EV (Scrubs
    24.42). His week 5 goes 22.85 → 23.76.
  * **Josh Allen's "Sleeper's projection"**, week 4 (the Sleeper projections fixture's invented line: 267.3 passing
    yards, 2.01 passing TDs, 0.78 rushing TDs), dynasty: **31.58 flat → 33.20 at the odds** (+1.62). The card reads
    "Sleeper has him at 31.6." → "Sleeper has him at 33.2." Ours goes 30.24 → 31.68, so the ratio barely moves
    (0.958 → 0.954) and the "well under / well over" words do not change. Scrubs: 25.50 both ways. Flat mode gives
    the old `compute_points` number to the cent. The fixture was loaded into the clone's `raw.sleeper_projections`
    (fetched 12 h before week 4's kickoff) for the record and market marts, then removed again; the API test uses a
    stand-in row.
  * **My Week = the record**, under the record's mode, in both clone states. The on-demand lineup total (NFL-wide
    board, lines priced now) equals `ops.lineup_totals` for the dynasty and Scrubs in weeks 4 and 5, to 0.005.
    Forced to the other mode, the dynasty's moves away (the bug the mode prevents) and Scrubs' does not.
* **Tests**:
  * `tests/test_m4.py`, 19 passed. It covers the DDL; the label per scoring; the backtest writer's label in the
    writer's own mode; the mode following the record; the env overriding it either way; the writer pinning the env;
    a frozen week keeping its label and a rollback; an unreadable record giving flat, cached a minute and then ten;
    `price_lines` per week, by board week and by window; the sentence (7 cases); and, on the clone, the label
    invariants in either state and M3's pins under the record's mode.
  * `api/tests/test_m4.py`, 8 passed in both clone states: `/api/record` `pricing` for the dynasty and Scrubs; the
    record without the column; My Week = the record ×4; Sleeper's projection.
  * `web/e2e/m4/` (4: the sentence on phone 375 / desktop 1300; none for Scrubs).
  * Edited elsewhere: `tests/conftest.py` (autouse: every root test starts with an empty record, so no root test
    follows a database's pricing state by accident); `api/tests/test_anyleague.py` (passes the board's week to
    `price_lines`); `api/tests/test_h1.py` (pins the flat engine: it is a flat-engine parity test).
* **Checks** (flat clone, the end state):
  * Root: **1032 passed**, 3 skipped.
  * API: **482 passed**, 3 skipped, 4 failed. Three are the known `*_tds_10p` scoring checks (`test_ic1` ×2,
    `test_ic_po`), the same on base. The fourth is `test_if1::test_the_engine_drops_mcpherson_for_carlson`, which
    pins the pre-IF-1 mart ("before: Harrison"). Any `project` run with IF-1's writer rewrites that mart, and Scrubs
    did not move by a cent here, so the failure is the clone's state, not this change.
  * Web: lint and typecheck 0 / 0, build ok. Fixture e2e `fixtures.spec.ts` + `m4` + `u1`: 42 passed.
  * ruff: one error, `api/league_lab_api/research.py:61` B010, already on `main` (`7222f98`, the PO's N2-merge fix).
  * dbt: `mart_player_week_projections+ mart_projection_record mart_market_line`, PASS=60.
  * The API suite on the **EV** clone: 11 failed. They are the 4 above; `test_ia3` ×4 and `test_ia2` ×1, which
    assume the clone has no market mart (it held the fixture then); and `test_anyleague` / `test_h1` (both now fixed:
    a frame without a week, priced as the newest build).
* **What moved and why**: only the pricing mode, and only for a league with a yardage or long-TD bonus, from the
  first build with the env on. Every number in flat mode is unchanged to the bit (above).
* **Not done**:
  * The record's Sleeper side (`mart_projection_record.sl_priced`) is still the SQL macro, all or nothing. In an EV
    week ours is priced at the odds and Sleeper's is not. M2's measurements put the effect at about ±0.02 on MAE
    and ±0.002 on Spearman, and a few close calls could flip. Proposal: below.
  * `why.weights` (the "why this number" pieces) reads the newest mode, not the week's, so on the half-and-half
    morning a frozen week's pieces carry the difference in their "rest" line.
  * `ops.projection_backtest` keeps its v3.0 rows NULL (= flat) until the model version changes. That is true: they
    were priced flat.
* **Next**: the PO ships or holds "M4: the flip". Then the record's Sleeper side, priced in Python for EV weeks.
* **For the PO**:
  1. **Merge.** M4 touches the following shared places:
     * `ondemand.record()`'s return: now `out = {…}; out.update(record_pricing(…)); return out`. V-1 adds
       `decisions` at the same spot; keep both.
     * About's record section: one `<p>` under the answer card. V-1 and IG-3 add blocks nearby.
     * `lib/api.ts`: an end-of-file block that merges into `RecordAnswer` / `RecordRow`.
     * `projections.py`: the import line, the `@pinned_writer` decorators, a label block after `_with_kd_rows`,
       `_ranges_from_record`'s select, the ranges' `_replace` columns. M5 works in the same file.
     * `CHANGELOG`'s `## 2026-10-04 — Wave I-G` heading: every dev adds it; keep one.
  2. **dbt**: the nightly's projection-marts step rebuilds both marts. The pre-hooks add the column on a database that
     has not run `project` yet. No `sources.yml` change.
  3. **`signals.py`'s one-line fix is required before the flip.** Without it, the first EV nightly fails the marts'
     `scenario_base_is_the_projection` test.
  4. **The flip** ("M4: the flip", the last commit): `LEAGUE_LAB_EV_PRICING: "1"` on the nightly step's env plus a
     HOSTING note. **Render gets nothing.** Do not do M3's step (2): a Render override would price a frozen week by
     the env instead of its label. Run the nightly by hand on Monday after merging, never on a game-day morning.
     Rollback: drop the line and re-run; the weeks that kicked off under EV keep `ev`.
  5. **Decisions Andrew may reverse**:
     * An empty `LEAGUE_LAB_EV_PRICING` now means "unset" (the record decides). In M3 it meant off.
     * The nightly writer never follows the record. Otherwise a rollback would need an explicit "0".
     * In EV mode, a long TD on Sleeper's line is priced by our measured share × Sleeper's projected TDs, not by
       Sleeper's own `*_tds_40p`. That is the same rule as ours.
     * The About sentence's words are "priced flat" / "at their odds" (a WORDS row).
  6. **Proposal (not built)**: `ops.market_record` (league_id, season, week, sleeper_id, fetched_at, sleeper_points,
     pricing), written by `project` for the league-weeks labelled `ev`. The last pre-kickoff snapshot exists by the
     first build after kickoff. `sl_priced` would read `coalesce(mr.sleeper_points, league_points(…))`. That needs a
     `sources.yml` row (PO).
  7. `test_if1::test_the_engine_drops_mcpherson_for_carlson` fails on any clone after a `project` run (its "before"
     is the pre-IF-1 mart). IG-3 rewrites the writer's drop rule and may want to re-pin it.

### M5 2026-10-04 — v3.1: the ranges' target, the fringe level, cold starts, each behind the harness (branch `dev/M5`, database `league_lab` read only)

Plan § 17 (v3.1 in "Next"); the brief's § M5. Andrew: "knock out a big chunk of the roadmap/backlog." Three model
candidates from M1's and M3's lists, measured walk-forward, each judged by a rule fixed before the verdicts were read,
each behind its own switch, **all off**; `MODEL_VERSION` stays `v3.0`; nothing was written to `league_lab`
(every session `read_only`; the suites ran with `PGOPTIONS=-c default_transaction_read_only=on`).

**The harness table** (the PO reads this first; Δ = candidate − v3.0, leagues averaged per season unless a league is
named; "seasons" = seasons better of n; interval score = (pinball 10 + pinball 90) / 2, points, lower is better):

| Group (switch) | Position | Δ Spearman | Δ MAE | Δ interval score | coverage 80% (v3.0 → cand.) | Seasons | Decision |
|---|---|---|---|---|---|---|---|
| ranges' target (`LEAGUE_LAB_RANGE_TARGET=graded`), 2023–25, graded actual | QB | 0 | 0 | dynasty −0.0066 / Scrubs −0.0036 | 0.751 → 0.756 / 0.761 → 0.761 (50%: 0.460 → 0.472 / 0.474 → 0.478) | 2 / 2 of 3 | **keep** (dynasty; Scrubs no change) |
| | RB | 0 | 0 | +0.0002 / +0.0017 | 0.799 → 0.802 / 0.806 → 0.804 | 1 / 2 | drop (no change) |
| | WR | 0 | 0 | **+0.0055** / +0.0013 | 0.805 → 0.805 / 0.805 → 0.808 | 0 / 2 | drop |
| | TE | 0 | 0 | +0.0001 / −0.0007 | 0.813 → 0.814 / 0.806 → 0.812 | 1 / 3 | drop (no change) |
| fringe level (`LEAGUE_LAB_FRINGE_LEVEL`), 2021–25 | QB | 0 | **+0.084** | +0.0031 | 0.760 → 0.760 | 0 of 5 | drop (hurts) |
| | RB | 0 | −0.005 | −0.0003 | 0.804 → 0.827 | 2 of 5 | drop |
| | WR | 0 | −0.021 | −0.0028 | 0.806 → 0.859 | 3 of 5 | drop |
| | TE | 0 | +0.022 | +0.0009 | 0.809 → 0.833 | 1 of 5 | drop |
| cold-start prior (`LEAGUE_LAB_COLD_START`), 2021–25; MAE on the cold rows / the whole board | QB | 0 | 0 / 0 | 0 | — | 0 of 5 | drop (the fit keeps the model) |
| | RB | +0.0018 | **−0.159** / −0.009 | −0.0006 | — | 4 of 5 | **keep** |
| | WR | +0.0034 | **−0.314** / −0.018 | −0.0008 | — | 5 of 5 | **keep** |
| | TE | +0.0037 | **−0.298** / −0.017 | −0.0007 | — | 5 of 5 | **keep** |

The rules. *Ranges* (`experiments.decide_ranges`, per league × position, on the graded actual): mean Δ interval
score ≤ −0.005 and lower in ceil(2n/3) seasons, and coverage holds (78–82% / 48–52%, or — QB, already at 73–76% —
no farther from nominal than v3.0 + 0.005; that clause was added on the first season's QB rows, before any verdict
was read); |Δ| < 0.005 is "no change" (a drop). *Fringe*: `experiments.decide` (MAE −0.05 / Spearman +0.005 in
ceil(2n/3) seasons) and the top-24 bias may not grow by > 0.02 in either league. *Cold start*: the cold rows' MAE
falls by ≥ 0.05 in ceil(2n/3) seasons and `decide`'s "hurts" is false on the whole board.

* **1. The ranges' target.** The residual models were fitted on the 12 components' price; the record grades
  `fct_player_game_league.points`, which adds the 2-point conversions, the 40+ / 50+ TD bonuses, fumble-recovery and
  special-teams TDs: per game QB +0.44 / RB +0.07 / WR +0.12 / TE +0.04 in the dynasty, +0.12 / +0.03 / +0.04 /
  +0.03 in Scrubs (2024; M3's "0.01–0.3" was the long-TD part alone). `projections.graded_actual` reproduces
  `fct_player_game_league.points` on all 5,735 played 2024 rows of each house league, to the cent. Under the switch
  `load_frame` joins the outcome columns (`join_graded_extras`) and `fit_position` takes the residuals against the
  graded actual (`range_actual`), the conformal widening too; the point projection is unchanged (asserted on every
  harness fit). Result: a wash at RB / TE, worse at the dynasty's WR (its range 0.4 wider for no gain), better at
  the dynasty's QB (the 80% range 1.1 points wider, interval score −0.0066, both coverages closer to nominal; per
  season +0.0039 / −0.0069 / −0.0168). Kept at QB: `RANGE_TARGET_POSITIONS = ("QB",)`, so `=graded` applies at QB
  only (`graded-all` everywhere — the harness's setting). A marginal keep (0.4% of the score; 2 of 3 seasons).
* **2. The fringe level** (`calibration.fit_fringe`, fr1.0): weekly-rank tiers 25–36 / 37–60 / 61+, each tier's
  shrunk, player-clustered mean residual, anchored at 0 at the top-24 cut, monotone (slope ≥ −0.5, floor at half the
  line), fitted on the 3 seasons before. Order never changes (Spearman Δ = 0 exactly), the top 24 do not move
  (top-24 bias within 0.02 everywhere). **Dropped everywhere**: the fringe's miss changes sign by era — fitted on
  2018–2020 the levels are positive (QB +2.1, WR +0.3–0.6, TE +0.8), in 2021–2025 the 25+ bucket is QB +0.43 / +0.58
  and RB / WR / TE −0.09 to −0.32. M1's over-projected fringe (2023–2025) is real for those seasons and not a stable
  property a walk-forward can fit.
* **3. Cold starts** (`calibration.fit_cold_prior`, cs1.0). Measured (2021–2025, dynasty, bias = actual − projected):
  a player's first three career games RB −0.65, WR −0.85, TE −1.06, QB −0.35; the debut alone RB −1.79, WR −2.25,
  TE −1.49 (a WR with no history projects about 6). Veterans' first three games on a new team: RB −0.51, WR −0.95,
  TE −0.44 (not addressed: a lead). The fix: fewer than 3 played regular-season games (any listed position; a career
  before 2016 is never cold) → w·model + (1 − w)·the position × draft-slot mean of cold starts (picks 1–32 / 33–64 /
  65–128 / 129+ / undrafted, shrunk n / (n + 30)), w fitted per games-played step on the seasons before over a
  0–1 grid; identity at 3 games. The fitted weights (2018–2024, dynasty): RB 0.0 / 1.0 / 0.8, WR 0.0 / 0.5 / 0.6,
  TE 0.0 / 0.2 / 0.3, QB 1.0 — the model is worth nothing on a debut. Cold-row bias after: RB −0.35, WR −0.19,
  TE −0.12. **Kept at RB / WR / TE** (`COLD_POSITIONS`).
* **What the kept cold start would do as wired** (the main database's 2026 board, read only, weeks 5–18; weeks 1–4
  are frozen): 2,754 of 19,822 QB–TE rows move, 120 players; dynasty mean RB −1.63 / TE −0.92 / WR −1.83 a week
  (−8.58 to +5.48), Scrubs −1.42 / −0.83 / −1.51. Week 5, dynasty: Germie Bernard (WR, pick 47, one game) 9.93 →
  4.85, Chip Trayanum (RB) 6.20 → 2.58, rookie TEs 3.7–3.8 → 2.7, Jordyn Tyson (WR, pick 8, no game
  yet) 6.08 → 8.42, Omar Cooper Jr. (pick 30, one game) 3.09 → 7.89. Nothing was written.
* **Not ready to switch on as wired** (the reason the switch stays off although kept): like cal1.0, the prior moves
  the house leagues' `ops.projections` rows and their reference ranges, not the stat line, so on-demand requests
  (priced from `ops.projection_lines`) would show the unblended number for exactly these players — IB-0's
  two-numbers bug — and dbt's `assert_projection_ranges_price_the_lines` (warn) would flag them. It belongs on the
  line (below, "For the PO").

**Delivered.** `projections.py` (one M5 block after `TIER_MIN_ROWS`: the switch, `GRADED_EXTRAS`,
`join_graded_extras`, `graded_actual`, `range_actual`, `RANGE_TARGET_POSITIONS`, the names of the other two
switches; one line in `load_frame`, one in `fit_position` — away from M4's import / decorator / `pricing` / DDL
spots). `calibration.py` (`calibrate_outputs` runs cal1.0 under its flag — body moved unchanged to `_cal10_outputs`
— then `v31_outputs`; the fringe and cold-start fits, `career_games_before`, `cold_columns`; bands are written back
column by column, `_put_bands` — cal1.0's `apply_maps` too: the cold blend's first version moved the point and not
its range because the raw line was a view the write changed, found by the production-path test). `experiments.py`
(an M5 block: `v31_rows`, `shared_component_fits`, `score_v31`, `paired_v31`, `decide_ranges`, `coverage_holds`).
`tests/test_m5.py` (17). `dbt/seeds/feature_experiments.csv` +104 rows (`range_target_graded` 24, `fringe_level` 40,
`cold_start_prior` 40; per-position decisions; `range_target_graded` scored on the graded actual, the other two on the
harness's). METRICS § "Calibration of the top" → "v3.1"; CHANGELOG; `.gitignore` `scratch/`; INTERFACES § M5.
No table, API, web or dbt-model change.

**Commands.** `scratch/run_v31.py ranges 2023,2024,2025` and `points 2018..2025` (per-row walk-forward, rows to
`scratch/rows/*.parquet`; ranges 5–40 min a season-position under load 10–20 — an `OMP_NUM_THREADS=2` process stalled
23 min on one fit and was replaced by single-threaded ones), `scratch/analyze_v31.py` (tables → `scratch/tables`),
`scratch/demo_cold.py RB,TE,WR` (the board, read only). Tests: `uv run pytest -q tests/test_m5.py` **17 passed**;
root suite (read-only guard) **1029 passed, 3 skipped, 1 failed** — `test_experiments::test_no_peek_check_catches_
planted_leaks` creates a temp table, which the guard refuses; run alone without it: passed (so 1030 / 3);
API suite (read-only guard) **465 passed, 16 skipped**; `uv run ruff check src app tests api`: one error, B010 in
`api/league_lab_api/research.py:61`, present on `main` 7222f98 (not M5's file).

**Not done.** The ranges' target on 2021–2022 (the quantile refits did not fit the time box on the shared sandbox;
2023–2025 is the harness's default). The cold-start prior on the stat line. New-team veterans. A dbt build of the
seed (writes; not on `league_lab`).

**Next.** v3.1 = the cold-start prior moved onto the line + the QB graded target, one bump, the record labelled.

**For the PO.**
1. **Merge**: independent of M4 (different spots in `projections.py`; no shared file otherwise). `calibration.py`'s
   restructure keeps cal1.0 bit for bit (its 13 tests pass). The seed rows append to the end of
   `feature_experiments.csv` (CRLF kept).
2. **Nothing changes on merge**: three switches, all off. A kept change is a `MODEL_VERSION` note, not a bump: if you
   take v3.1, it is (a) `LEAGUE_LAB_RANGE_TARGET=graded` in the nightly's `project` env (QB ranges, every reference
   scoring; needs no table) and (b) the cold-start prior — **only after it moves onto the stat line** (scale the
   line's components by blended / raw points in a reference scoring before `nfl_lines`, so `ops.projection_lines`,
   `price_lines` and the record agree; ~a day's work, my estimate), plus `calibration.run_build_oof()` once where the
   nightly runs (`ops.calibration_oof`, 3 seasons; the nightly restores `ops` from the hosted copy — check it travels).
3. **Decisions you may want to reverse**: the ranges' QB keep is marginal (−0.0066 on 1.73, 2 of 3 seasons) — leaving
   it off is defensible; the cold-start weights put ~0 on the model for a debut, which pulls a high-usage rookie hard
   toward his draft slot (Bernard 9.93 → 4.85 after one game) — the harness says that is right on average, Andrew may
   not like it for the player he just picked up; QB is excluded by the fit itself.
4. **Leads for v3.2**: veterans on a new team are over-projected as much as rookies (WR −0.95); the point projection
   itself prices none of the 2-point / long-TD points it is graded on (dynasty QB 0.44 a game; EV pricing covers the
   long TDs in expectation, not 2-point conversions).

### IG-1 2026-10-04 — team units' season value, the finder on season value, unknown is not zero (branch `dev/IG1`, clone `league_lab_i0b`, read only)

* **Task / plan**: Wave I-G brief § IG-1; plan § 17 (the backlog after I-F: "team units' season value", "the finder's
  raw-total filter", "unknown is not zero"); STATUS § "Wave I-F" PO "Open" and IF-2's "Open".
* **Why**: MFL's team units (team QB / team kicker) had no `market` row, so "Houston Texans QB + Tuten for Rice" said
  "Not counted (no season projection): Houston Texans QB." and the warning could not judge it; the Finder still set
  trades aside on the raw rest-of-season totals (a volume gap: "you give 484 rest-of-season points for 141"); a bench
  player with no projection showed "0.00" (Jacobs on GoodGameBuddy's bench).
* **Delivered**
  1. **Units' season value** (`decisions.unit_market`, `# ---- IG-1`; merged into `TradeContext.points` /
     `replacement` / `repl_name` on demand): season points = IC-4's per-week unit rows (`lw.priced[w].units`) summed
     over `market_points`' window (this week → the last regular-season week; a bye adds nothing), keyed as the board /
     free-agent frame key them (`mfl:0682`); replacement = the best **free unit of the same kind**, never a player; a
     unit with no priced week has no row. The verdict, `values.season_value`, `season_value_line`, `calc_sanity` and the
     Finder count units. House leagues: unchanged (no units).
  2. **The Finder's rule (a)** = `trades.value_gap` (via `trades.sanity(..., values=)`; `ros=` kept for callers without
     values): season value above replacement given − received > 25% of given **and not about even** (a warning never
     contradicts "about even by season value"); one rule for the Finder and the calculator (`calc_sanity` delegates).
     `/api/trades/partners` `sanity` gains `rule: "season_value"`, `value_players`, `words` (the "left out" sentence, now
     from the API); the three named examples show the first of each rule first (`rejected_examples`).
  3. **Unknown is not zero**: the API sends `null` + `no_projection: true` for a player with no projection row (the
     solver's `value_source = 'unvalued'`, carried at 0): My Week `lineup` / `lineup_full` (value and margin), Team's
     roster, the trade answers (`this_week`, the lineups' slots, starters in / out and their change), a Waivers drop
     with no rest-of-season row; My Week gains `n_unvalued` (starters the total counts at 0) and `unvalued_words`
     ("1 starter has no projection and counts as 0 in this total."); a package side with an unvalued player has no
     season-value sum (`known_value`: the Finder rows' `price_out` / `price_in`, the calculator's other-objective
     words). Web: `LineupTable` (a dash titled "No projection for him this week: unknown, not 0", "no projection" under
     the name), My Week (the total's line), Team (row words), TradeCalc (title), the card / pane label ("Week 4 · no
     projection"), Trades ("left out" words from the API). Console: `cards.lineup_table` blank + the flag "no
     projection" (was "no value yet" + 0.00).
* **Interfaces**: INTERFACES.md § IG-1 (units' market rows, the value rule's `values=`, the null contract).
* **Evidence**
  - Houston Texans QB + Tuten for Rice (MFL 70587 team 8 → 12, fixtures + ESPN overlay): **before** "Season value above
    replacement: you give 14, you get 7 (about even). You give 2 players for 1: 1 roster spot freed. Not counted (no
    season projection): Houston Texans QB." (Houston QB `market_price` / `season_points` null; `market.unknown`
    ["mfl:0682"]); **after** Houston QB 355 season points, the best free team QB Arizona Cardinals QB 378 → 0 above;
    "Season value above replacement: you give 14, you get 7 (about even). You give 2 players for 1: 1 roster spot
    freed."; `market.replacement` gains TMQB (378, Arizona Cardinals QB) and TMPK (169, New Orleans Saints K); no
    warning either way (14 for 7: about even). "Houston QB for Rice + Carolina QB": "you give 0, you get 7", nothing
    "Not counted". A unit's season points = its rest-of-season rows (`weeks_json`) over the same weeks (tested).
  - **The Finder, Scrubs roster 6** (clone, next four weeks) — before: 5 cards, 2 left out (raw rule): Williams → Purdy;
    Lloyd + Boston → Mahomes; Judkins → Mahomes; Warren → Andrews + Purdy; Lamb → Allen + Golden · left out: Lamb +
    Javonte Williams → Taylor ("321 rest-of-season points for 213"), Williams → Kyler Murray ("112 for 75"). After: 7
    cards, 10 left out: Williams → Purdy + Likely; Williams → Purdy; Lloyd + Boston → Mahomes; Lamb → Allen + Chase;
    Judkins → Mahomes; Williams → Kyler Murray; Lamb + Javonte Williams → Taylor · left out (value gap): Williams +
    Judkins → Lamar Jackson ("32 season value above replacement for 6"), Williams + Boston → Jackson ("35 for 6"),
    Warren → Andrews + Purdy ("20 for 3"), Lamb → Allen + Golden ("69 for 35"), … All cards stay below the best
    waiver move (Carlson, +13.5); no gain moved.
  - **The Finder, MFL 70587 team 8** (fixtures) — before: 15 cards, 11 left out: Bears QB → KC QB + Rice (headline);
    McCaffrey → Achane + Coker; Corum → Downs + Johnston; Corum → Downs; Houston QB → KC QB; Tuten → Kincaid; Watson →
    Chase + Wilson; Houston K → Higgins + Packers K; Corum → Kraft; Bears QB + Tuten → Bucs QB; Tuten → Evans; Corum →
    Wan'Dale Robinson; Houston K → Smith + Chiefs K; Corum → McLaurin; McConkey → McLaurin + Hockenson · left out
    (raw): Tuten → Robinson ("138 for 98"), Corum → Hockenson ("127 for 83"), Bears QB + Tuten → Coker ("484 for
    141"). After: 17 cards, 12 left out: Bears QB → KC QB + Rice (headline, unchanged, now "0 for 29"); Bears QB →
    Tyler Warren; Corum → Downs + Johnston; Bears QB → Coker; Bears QB + Tuten → Coker; Corum → Downs; Houston QB → KC
    QB; Corum → Kincaid; Watson → Chase + Wilson; Houston K → Higgins + Packers K; Corum → Kraft; Bears QB + Corum →
    Bucs QB; Corum → Robinson; Houston K → Smith + Chiefs K; Corum → McLaurin; McConkey → McLaurin + Hockenson; Corum
    → Shakir · left out (value gap): Tuten → Robinson, Bears QB + Tuten → Bucs QB, Tuten → Kincaid ("14 season value
    above replacement for 0"). Why the team-QB cards: a team QB below the best free team QB is worth 0 above
    replacement — giving it costs no season value (the waiver wire has a better one).
  - **No projection**: Scrubs roster 6 My Week — Jacobs `value` 0.0 → null, `no_projection` true; Team roster 0.0 →
    null; a trade giving Jacobs: `this_week` 0.0 → null; his card `proj_points` null (unchanged) with the label "Week 4
    · no projection"; `n_unvalued` 0 (the bench is not in the total).
  - Commands: `cd api && PYTHONPATH=. uv run pytest -q tests/test_ig1.py` **13 passed**; trade / week neighbours
    (`test_if2 test_ia2 test_ic4 test_ie0 test_ie1 test_ie2 test_ic_po`) green except `test_ic_po`'s scoring check
    (the clone has no `*_tds_10p`: known); root `tests/test_cards.py test_trades.py test_trade_finder_page.py
    test_my_week.py test_decisions.py test_app_guards.py` **70 passed**; **whole suites**: API **476 passed, 4 failed, 14 skipped** (the three scoring checks the clones cannot pass — `test_ic1` dad's league weeks 1–2, `test_ic_po` ten-yard cut: no `*_tds_10p` columns; and `test_if1::test_the_engine_drops_mcpherson_for_carlson`, which passed on the first run and fails since IG-3 rewrote `ops.waiver_moves` on `league_lab_i0b` at 05:00 ET — IG-3 re-pins it; skips: `test_u1`'s hosted SQL needs a superuser, IC-3's flat path, IF-4's recorder) + `test_myweek test_parity test_i0a test_ib0 test_if4 test_ig1` re-run after the last commit: 78 passed, 1 skipped; root **1013 passed, 3 skipped**;
    `uv run ruff check src app tests api`: 1 error, `api/league_lab_api/research.py:61` B010 — on `main` too, not
    this branch's; web `npm run lint` (eslint + svelte-check + tsc) clean, `npm run build` clean, **fixture e2e 206
    passed** (`web/e2e/ig1/` 2 × phone / desktop on answers recorded from the API on the fixtures + the clone,
    `web/fixtures/ig1/api_ig1.json`: Jacobs' dash, title, words and his card; the team QB counted on the calculator;
    the Finder's "left out" words on season value).
* **What moved and why**: the Finder's suggestions (rule (a) on value — the brief's allowed move, lists above); the
  partner rows' `price_out` / `price_in` (null when a side has an unvalued player; the team units now priced); the
  calculator's season-value line and `market` for packages with a unit; the console's starter flag "no value yet" →
  "no projection". No projection, lineup total or gain moved.
* **Every place that coerced a missing projection to 0** — fixed (now null): (1) `myweek._lineup_row` `value:
  _num(r.get("value"))` (the solver's 0.0 for `unvalued`; both paths) and its margin; (2) `myweek.cards_from_rows`
  `alt_value`; (3) `decisions.team` roster `value: _num(r["player_value"])`; (4) `TradeContext.week_value` →
  `ctx.player()['this_week']` (every trade answer's players); (5) `decisions.evaluate` lineups' `slots[].value` (the
  page's `lineup_frame`: `(s.value or 0.0)`); (6) `decisions._membership` `T._r2(s.value or 0.0)` ×2 and `trade_story`
  `row["change"] = T._r2(s.value or 0.0)`, `lu["out"]` `change: -x["value"]`; (7) `decisions._move` drop `projection` /
  `season_points_left` (the writer stores `drop_value` 0 and `ros.get(m.drop, 0.0)` — `waivers._write`); (8)
  `decisions.partners` `price_out` / `price_in` = `T.season_value(...)[0]` (0 or a partial sum when a side has an
  unvalued player) and the calculator's other-objective prices; (9) the console's `cards.lineup_table`. Left (named,
  not changed): `app/pages/6_Trade_Finder.py` `lineup_frame` `(s.value or 0.0)` and its notes' `{value or 0.0:.2f}`
  (PO-only page; the API's `lineups.*.notes` carry those words); `trades.verdict` / `fairness_line` /
  `season_value_line` `price_out or 0` (sums of the counted players — the lines name the uncounted, the verdict's lean
  does not); `waivers._write`'s stored zeros (IG-3's writer; nulled on read); ordering keys only (`_ie1_cheaper`
  `pts.get(x) or 0`, `myweek.build_actions.val`); `ondemand.lineup_values` adds 0 for a week with no value (a sum over
  weeks of projected players); `lineup.solve` carries an unvalued player at 0 by design (the total's caveat is
  `n_unvalued`).
* **Not done**: Waivers' drop cost (IF-1, `_moves_on_demand`) does not read the units' season value — its unit
  baseline loop is there but `market_points` has no unit rows; `points.update(unit_market(lw, fa)[0])` there would
  price a dropped unit's season value (moves MFL Waivers numbers: a PO call). The verdict's value lean with an
  uncounted player (above). The console's Trade Finder page's 0.00 (PO-only file).
* **Next**: the PO's merge; then the drop cost on units (one line, above) with its before / after.
* **For the PO**
  1. Merge: marked blocks in `decisions.py` (IG-1 blocks + marked lines in `evaluate`, `team`, `_move`, `partners`,
     `calc_alternatives`), `myweek.py` (after `_lineup_row`; `my_week`'s two lines; `alt_value`), `ondemand.py`
     (`my_week`'s block) — IG-2 / IG-3 touch other blocks of the same files; `web/src/lib/api.ts` one IG-1 block +
     the `Partners.sanity` line; `MyWeek.svelte` (one line under the lineup), `Trades.svelte` (the "left out" text).
  2. Two other developers' tests re-pinned (marked `IG-1`): `api/tests/test_if2.py` (Houston QB is counted now: no
     "Not counted"; the warning's comment), `api/tests/test_ia2.py` (the route test checks the value rule, `rule ==
     "season_value"`). `test_ia2`'s rule (b) example now relies on `rejected_examples` showing the market refusal first.
  3. Registry (dbt seed, PO): the sanity bound `ti1.1` → `ti1.2` (rule (a) on season value above replacement), and a
     row for the units' season value if you keep one per concept (METRICS § "Value to my lineup" › "Team units and the
     value rule").
  4. Decisions Andrew may reverse: (a) the value rule also requires "not about even" (a 9-point gap never warns; a
     25% gap on small values would otherwise flag 3-for-0 packages); (b) no free unit priced → baseline 0 (the
     players' rule); (c) a team unit below the best free unit is worth 0 above replacement, so the Finder now offers
     "Chicago Bears QB → …" packages (giving him costs no season value: the waiver wire's team QB is better); (d) the
     card label "Week 4 · no projection" when the card has no number.
  5. The e2e recording reads the clone `league_lab_i0b` of 2026-09-26 (Jacobs has no projection there); re-record with
     the header's command if the clone changes.
  6. Parity: the console now shows a blank (NaN) where the API sends null for a player with no projection, and both
     flag him "no projection" (a bench row's flag mirrored in `myweek.lineup`). `api/tests/test_parity.py` compares
     values with `==` (NaN ≠ None): fine for its cases (Andrew's rosters have no unvalued player on the clone); a case
     with one (Scrubs 6) needs `nan_ok`-style matching there.

### IG-2 2026-10-04 — the event store (the decision-quality review § "Engineering requirements"; branch `dev/IG2`, clone `league_lab_ia3`)

**Plan sections**: PROJECT_PLAN § 17 (the backlog's "`ops.events` (the decision-quality review's event store)"); the
review § Priority 1 "Engineering requirements", § "Model validation and release gates" (news-affected cases: the store
V-1 reads). **Branch** `dev/IG2` from `main` 7222f98. **Interfaces**: INTERFACES.md § IG-2 (+ "final shape").

**Files.** New: `scripts/hosted_events.sql`, `api/league_lab_api/events.py`, `api/tests/test_ig2.py`,
`web/e2e/ig2/fixtures.spec.ts`, `web/fixtures/ig2/api_ig2.json`. Marked blocks (`IG-2`): `scripts/sync_to_hosted.sh`,
`scripts/init_db.sql`, `api/league_lab_api/{availability,news,playerwire,research,myweek,main}.py`,
`api/tests/conftest.py` (one line), `web/src/routes/About.svelte`. Edited pins: `web/e2e/{n1,n2}/fixtures.spec.ts`
(About's N1 sentence). Docs: `docs/HOSTING.md` § "Events" (new), `docs/ANY_LEAGUE.md` § "Events" (new),
`docs/METRICS.md` § Matchups "Current personnel" (the URL now carried), `docs/ESPN_TERMS.md` § "What we keep",
`CHANGELOG.md`, this section. **Data touched**: `league_lab_ia3` only (the pipeline role was granted `CREATE` on it,
as on the Mac where it owns the database; `events` created there; the tests' rows removed); `league_lab` never written.
**Commands**: `cd api && PYTHONPATH=. uv run pytest -q tests/` (and `tests/test_ig2.py`, `IG2_RECORD=1 … -k record`),
`uv run pytest -q tests/test_app_guards.py tests/test_nightly_relations.py tests/test_playerwire_sync.py`,
`uv run ruff check src app tests api`, `cd web && npm run lint && npm run build && FIXTURES_PORT=8604 npx playwright
test --config playwright.fixtures.config.ts e2e/ig2 e2e/n1 e2e/n2 e2e/if4`, `psql -f scripts/hosted_events.sql` (3×),
`scripts/init_db.sql` on a scratch database (2×, dropped).

* **The store.** `scripts/hosted_events.sql` (new, plain SQL, idempotent): schema `events`, table `events.events (id
  bigserial, kind, player_key, gsis_id, team, game_key, status, headline, summary, source, source_url, published_at,
  effective_at, ingested_at, superseded_by, fingerprint unique)`; checks on `kind` (`availability` | `news` | `brief` |
  `depth_chart`), the key shapes (`00-0000000`, `espn:` / `sleeper:` / `mfl:` / `pw:` ids, 2–3 letter teams, nflverse
  game ids), https URLs, lengths, a sha256 fingerprint, at least one of gsis / team; indexes `(gsis_id, ingested_at)`,
  `(team, ingested_at)`, the live rows by `(kind, gsis_id)`. Grants: `league_lab_app` gets `USAGE` on the schema,
  `SELECT, INSERT`, `UPDATE (superseded_by)` and the id sequence's `USAGE` — no delete, no other column. The sync's
  marked block (`scripts/sync_to_hosted.sh`, "IG-2", after U-1, its own transaction on the owner connection, a warning
  on failure — the publish stands); `scripts/init_db.sql`'s marked block runs the same file as the pipeline role.
* **The writers** (`api/league_lab_api/events.py`, U-1's pattern): rows go on a bounded queue (500 batches) that one
  daemon thread drains, each batch in `BEGIN; SET TRANSACTION READ WRITE; …; COMMIT` on its own connection
  (`application_name` `league-lab-events`, one retry on a dropped connection); a failure is counted and logged, never
  raised; a fingerprint the process already queued is not queued again. (1) **The overlay** (`availability.snapshot`,
  marked lines: the ESPN / Sleeper ids on the entries, the feed's timestamp, `events.observe_availability(s)`): the
  writer thread diffs each new merged copy against the one before — the first copy of a process against the store's
  live statuses — per player (the overlay's own newer-of-two rule), one event per move, off both lists = `ACTIVE`;
  only when both sources loaded (ESPN failing to load is not 300 players turning healthy). `published_at` = the copy's
  time (ESPN's feed `timestamp`), `effective_at` = the report's (the entry's `date`, Sleeper's `news_updated`),
  `source_url` = the player's ESPN page (ESPN's injuries feed carries no story link; a Sleeper report has none).
  (2) **The card's news line** (`news.for_card`, marked lines): every item it shows — ESPN's as `news` (`status` = IF-4's
  `about`), PlayerWire's as `brief` (`status` = the verification, `summary` = the brief's text, the first evidence
  link). (3) **My Week's "What changed"** writes the items it shows the same way. **Supersede**: availability — the new
  row supersedes the player's older live rows (insertion order: the overlay's current status is always the newest);
  news / brief — by time (a late older item is stored already superseded). **Dedupe**: the fingerprint (sha256 of
  kind, gsis or team, status, URL, effective-or-published time) is unique, `on conflict do nothing`; a status that
  returns to a report already stored (a copy that dropped him a while) is re-inserted with `|after:<live id>` salted in.
* **The readers**: `events.for_player(gsis, since)`, `events.for_team(team, since)` (a corner's IR is an availability
  event of his team), `events.recent(gsis_ids, hours)`, `events.cite(ev)`, `events.info()` — the read-only pool,
  cached a minute, `[]` when the store is off / missing / unreachable (one warning). **"What changed"** (`myweek`
  marked block): a status line cites its stored event — `source` "Injury report (ESPN)" or "(Sleeper)" as the overlay
  entry says (it was always "ESPN"), `at` = the report's time (it was the time the feed was checked), `url` = the ESPN
  page, `event_id`; without an event the overlay entry's own source and time (`meta.cites`, a marked addition to
  `apply_to_rows`, aligned with `meta.changes`). News lines: ESPN's items + PlayerWire's briefs of the last 24 hours
  (`playerwire.recent`, one query for the week's players, the card's identity rule), merged with the store's live
  news / brief events by fingerprint, one line per player — his own brief, then a brief naming him, then ESPN's item
  about him, then league news — with `event_id`, `origin` (`espn` | `playerwire`), `verification`. A brief is a `news`
  line, so the web needed no change. **The matchup evidence** (`research._cite_missing`): each missing regular's
  newest live availability event that says he cannot play (the opponent's events first — `for_team` — then his own,
  60 days) → `changed.missing[].event` / `.url`, `changed.events`; no event: null, the overlay's words stay.
* **Routes.** `/api/status` → `events: {enabled, ready, rows, live, newest, process}`; `GET
  /api/events?league=&team=&hours=72` (gated, `no-store`, 1–720 h): the roster's players' events, live and
  superseded, with names (any league: `availability.roster_context` — house, Sleeper on demand, MFL). About: one
  sentence (`about-events`), and N1's "keeps none of it" became "keeps only the headline, its date, the source and the
  link" (it was no longer true; N1's and N2's e2e pins follow).
* **Switches.** `LEAGUE_LAB_EVENTS=off` (0 / false / no): nothing written, nothing read — the screens are IF-4's.
  **Off in fixture mode** unless `LEAGUE_LAB_EVENTS=on`, and off in every API test (`conftest.py`) unless the test
  turns it on (no suite writes made-up rows into a developer's store). `LEAGUE_LAB_EVENTS_ESPN_NEWS=off`: ESPN's
  headlines stay out of the store (moves and briefs kept).

**Evidence.**
* `api/tests/test_ig2.py` — **19 passed, 1 skipped** (the recorder, `IG2_RECORD=1`): the row's checks and fingerprint;
  the diff on hand-built copies (no move = nothing, a move = one row, a missing source = nothing, off the lists =
  ACTIVE); off / fixture mode write nothing; a 1.5 s failing writer returns to the caller in < 0.5 s and the row is
  retried next time; the hosted SQL applied 3× is idempotent and leaves `usage.events` (rows, columns, constraints,
  ACL) identical; the app role's grants (insert, `superseded_by` only, no delete / truncate / other column; a plain
  insert still `ReadOnlySqlTransaction`; a bad gsis `CheckViolation`); **a status move**: ESPN's fixture copy through
  `availability.snapshot` writes Jefferson's `OUT` (effective 2026-10-02 18:35Z, published 2026-10-03 03:58:44Z, his
  ESPN page) once; the same copy again writes nothing; the next copy (Questionable) writes one row and supersedes the
  first; off both lists → `ACTIVE`, superseding; `for_player` newest first with `live`; a new process (no memory)
  diffs against the store and writes the one difference; **news and briefs**: the card's ESPN items and PlayerWire's
  three briefs write one row each; shown again — nothing (process memory); a new process — nothing (fingerprint:
  `duplicate` = the item count); one live row per kind; `LEAGUE_LAB_EVENTS_ESPN_NEWS=off` keeps ESPN's out; **What
  changed** (Scrubs roster 2, overlay + PlayerWire fixtures): the status line `Injury report (ESPN)` · 2026-10-02T18:35Z
  · his ESPN page · `event_id`; his line is the Vikings' brief ("Jefferson (ankle) ruled out for Sunday", `official`,
  the vikings.com link, `event_id`); with ESPN and PlayerWire both silent the store's live brief still shows; off = IF-4's
  lines; **matchup evidence** (IF-3's as-of case): Horn's and Jackson's IR events (team CAR) → each missing corner
  carries `event` (ESPN, IR, 2026-09-30T20:15Z) and its URL, IF-3's sentence unchanged; off → null, the overlay stays;
  a store that raises on read and write → My Week and the card 200, `/api/status` `events.ready: false`; `/api/status`
  and `/api/events` (720 h cap, `no-store`, the gate: 401); the sync and init_db blocks.
* The overlay's first copy on an empty store (the `espn_if3` fixtures): 248 players listed, **151 rows** (the non-active
  ones), 0 failed. Row size: **~500 bytes with the indexes** (10,000 rows = 5.1 MB, measured in a rolled-back
  transaction); the empty table 48 kB. `scripts/init_db.sql` run twice on a scratch database (dropped after): `events`
  owned by `league_lab_pipeline`, the app role's grants as above.
* Related suites unchanged: `test_if4 test_if3 test_i0a test_n1 test_n2 test_u1 test_myweek` 94 passed, 1 skipped.
* **The whole API suite** (`cd api && uv run pytest tests/`): **494 passed, 4 skipped, 3 failed** (16 min) — the three
  known clone scoring checks (`test_ic1` × 2, `test_ic_po`: no `*_tds_10p` columns). A first full run (37 min, the box
  shared with the root suite) had 3 more failures, all in `test_ig2`, from rows an earlier run of mine left behind (a
  run killed at its time-out before its teardown); the tests now read their own rows only. That rerun then showed
  `test_n2`'s database-path test (it leaves fixture mode) writing its made-up brief and ESPN items into the clone's
  store — so `api/tests/conftest.py`'s autouse fixture now sets `LEAGUE_LAB_EVENTS=off` for every test (one marked
  line; `test_ig2` turns it on itself). After it: `test_ig2 test_if4 test_n1 test_n2` 56 passed, 2 skipped, and the
  store empty after the run.
* Root suite: my change touches no `src/`, `app/`, `tests/` or `dbt/` file; the root tests that read files I changed
  (`test_app_guards`, `test_nightly_relations`, `test_playerwire_sync`) 26 passed, 1 skipped. The whole root suite
  did not finish on this box (2 CPUs, load 11–14: `test_kdef` fits models; 7% in 32 minutes) — not run in full.
* Web: `npm run lint` (eslint + svelte-check + tsc) 0 errors; `npm run build` clean; e2e on fixtures
  (`FIXTURES_PORT=8604`, `e2e/ig2 e2e/n1 e2e/n2 e2e/if4`) **32 passed** — `web/e2e/ig2/` 2 × phone (375) / desktop
  (1300): the status line's "Injury report (ESPN) ↗" links to his ESPN page with the report's time, the brief's
  "Minnesota Vikings via PlayerWire ↗" link, About's sentence, no sideways scroll (recorded answers:
  `web/fixtures/ig2/api_ig2.json`). Ruff: one finding, `research.py:62` B010 — on `main` already, not in my block.

**What moved.** No number: projections, lineups, gains and the cards' words are untouched. "What changed" status lines
now name the source that reported the status and the report's time (before: "Injury report (ESPN)" and the time ESPN
was checked, even when Sleeper's entry won) and link to the player's ESPN page; a PlayerWire brief can be a player's
news line there (before: ESPN only).

**Not done / limits.**
* `game_key` is empty and no `depth_chart` writer exists (no feed gives a dated depth-chart move yet; the check allows
  the kind).
* Availability moves are recorded only while a server process runs and reads the overlay (Render's one process;
  between restarts, the next copy's diff against the store catches up — moves that came and went in between are
  lost). The first copy after the merge writes every listed player once (a few hundred to ~1,500 rows).
* A Questionable designation on a starter that moves no lineup is stored but not a "What changed" line (IF-4's rule:
  the lines are the lineup's moves and the news).
* Team announcements (the Panthers' release) are not read: the URL is ESPN's player page, the date the report's.
* No retention yet (an estimate: 30,000–80,000 rows a season, 15–40 MB).
* The sandbox's proxy log shows `site.api.espn.com` refused at 07:20Z / 07:33Z / 08:14Z (UTC) — two of them before this
  task started: some API test (not test_ig2) reaches for ESPN outside fixture mode; not traced.

**Next**: V-1's news-affected cases read the store once merged (INTERFACES § IG-2 "For V-1"); a retention rule; a
dated depth-chart writer (Sleeper's `depth_chart_order` moves between copies) for `for_team`.

**For the PO** (review first):
1. **The sync block** (`scripts/sync_to_hosted.sh`, "# ---- IG-2", 12 lines after U-1) — its own `psql -f
   scripts/hosted_events.sql` on `LEAGUE_LAB_HOSTED_ADMIN_URL`, a warning on failure; no new secret, variable or
   workflow change. The next nightly creates the schema; until then every write fails quietly (`process.failed`).
2. **ESPN's headlines are now kept** in the hosted database (headline, date, source, link — the cache file's four
   fields; never the body). `docs/ESPN_TERMS.md` § "What we keep" says so; ESPN's terms are still unread. To hold it:
   `LEAGUE_LAB_EVENTS_ESPN_NEWS=off` on Render (status moves and briefs stay), or `LEAGUE_LAB_EVENTS=off` for all.
3. **Decision taken** (the brief said `(kind, gsis_id, status)`): supersede by `(kind, gsis_id)` — its acceptance
   ("supersedes it on the next move") needs the status out of the key. The fingerprint uses the report's time for a
   status move (the brief's "published_at" is the copy's time there, which would make every copy a new row).
4. **About**: N1's sentence changed ("keeps only the headline, its date, the source and the link"); N1's / N2's e2e pins
   updated with it. About.svelte is also M4's / V-1's / IG-3's file — my two marked blocks are next to N1's.
5. Merge order: independent of M4 / IG-1 / IG-3 / M5. V-1 reads the store; `myweek.py` / `research.py` / `main.py`
   carry other developers' marked blocks too — mine are `# ---- IG-2`. `api/tests/conftest.py` gains one marked line
   (`LEAGUE_LAB_EVENTS=off` in the autouse fixture) — shared, outside my list, needed so no test writes into a store.
6. Retention: none (a proposal: drop superseded `news` rows after 120 days; keep availability and briefs for the
   record).

### V-1 2026-10-04 — the validation harness: the decision record, graded (branch `dev/V1`, clone `league_lab_i0a`)

* **Task**: Wave I-G V-1 (plan § 17 "the validation harness the review asks for": frozen as-of inputs, decision
  regret, news-affected cases); the review § "Model validation and release gates"; METRICS § "Projection record" →
  "The decision record" (dr1.0, new); INTERFACES.md § V-1.
* **Why**: `lineups()` re-solves and overwrites `ops.lineups` every run, so nothing kept what the app recommended
  before kickoff, and nothing graded whether following it would have helped. The record against Sleeper grades the
  numbers; this grades the lineups.
* **Delivered**:
  * **`ops.lineup_record`** (`lineup.py` V-1 block). Per league × week it follows the `ops.projections` freeze rule.
    The **next** week to kick off is replaced by every build: the last build before its first kickoff wins
    (`record_source = 'kickoff'`). A week that has kicked off is never rewritten. A kicked-off week with no rows is
    **rebuilt once** from its frozen projections, solved as of one second before its first kickoff (no locks), and
    labelled `reconstructed` (2026 weeks 1–4). The table holds one row per player of the proposed lineup, the lineup
    total, `model_version` and `pricing` (M4's label when the column exists, else `flat`). A starter's row also
    carries the cards' call: `call_rank` 1–3, the bench player who would come in, `p_win` on the frozen ranges, and
    `is_coin_flip`. `lineup.close_calls` = `cards.decisions` (tested on 12 random rosters). It is written by every
    `lineups()` run (so every `project`; never fatal there) and by `league-lab validate`. `db migrate` creates it
    (`lineup.DDL`).
  * **`league_lab.validation`**: `grade_roster_weeks` (submitted, ours, the hindsight optimum, regret = optimum −
    submitted, edge = ours − submitted, `n_changed`, news-affected), `grade_calls` (outcome 1 / ½ / 0),
    `calibration` (`decisions.coverage_table` + `brier` + the coin flips), `summary` (the `decisions` block with
    the sentences), `validate`. Unknown is not zero: a K / DEF with no number makes the roster-week's `app_points`
    NULL (`n_app_unknown`). An unscored week has no point at all.
  * **dbt twins** `mart_decision_record` (roster-week) and `mart_decision_calls` (call), with
    `decision_record.yml`: the source `ops_decisions.lineup_record` (its own source name, so `sources.yml` is
    untouched) and 15 tests (unique keys, accepted values, in-play rows carry no points, regret ≥ 0, edge +
    app_regret = regret). The marts equal the Python on the clone: 110 roster-weeks and 330 calls, 0 differences.
  * **`/api/record` `decisions`** (`ondemand.py` V-1 block, above `record()`): `validation.summary` over the two marts;
    `{"available": false, "why": …}` (never an error) before they exist. The key is added by a wrapper,
    `@_with_decisions` on `record()`, rather than a line beside M4's `out.update(record_pricing(…))`. That line
    conflicted in a trial merge (`git merge-tree dev/M4 dev/V1`). With the wrapper, the trial merges with dev/M4,
    IG1, IG2, IG3 and M5 are all clean.
  * **About** (record section, V-1 block between the Sleeper calls table and "Projections by position"): "Our lineups
    against the ones started". It shows the edge sentence and three tiles (our lineups would have added · best lineup
    in hindsight · coin flips landed), then a week table (Started · Ours · Best · Added; rebuilt weeks starred), the
    calls line, the news line, the rebuilt-weeks note, and "How to read our lineups' record". `lib/api.ts`:
    `RecordDecisions` / `RecordDecisionWeek` and `RecordAnswer.decisions` (declaration merge, V-1 block after
    `RecordAnswer`).
  * **Console Record page** (new section before "How to read this"): the same sentences, three `st.metric`s, the
    week table and the calls' calibration table with the Brier score.
  * **`league-lab validate`** (`cli.py` V-1 block; `--season`, `--league`, `--no-write`): writes the record, then
    prints the weeks, the season, the calibration table and the sentences.
  * **`scripts/nightly.sh`** (three V-1 blocks): `ops.lineup_record` joins `STATE_TABLES` / `RECORD_TABLES` (restored
    from the hosted copy, saved to the archive). A soft `validate` step runs after `project`, and a soft
    `decision-marts` dbt build runs after `drift`.
* **Interfaces**: INTERFACES.md § V-1 (updated ~04:10 for the wrapper). Shapes are in METRICS § "The decision record".
* **Commands**: `league-lab validate --season 2026` (clone); `league-lab lineups` (the hook: 451 record rows for week
  5; weeks 1–4 kept); `league-lab dbt build --select mart_decision_record mart_decision_calls source:ops_decisions`
  (PASS=17); `uv run pytest -q tests/test_v1.py`; `cd api && PYTHONPATH=. uv run pytest -q tests/test_v1.py`;
  `cd web && npm run lint && npm run build`; `FIXTURES_PORT=8605 npx playwright test --config
  playwright.fixtures.config.ts e2e/v1` (recorded with `V1_RECORD=http://localhost:8705`, API on the clone).
* **Evidence**:
  * Tests: `tests/test_v1.py` **23 passed**: the freeze (two builds before kickoff → the second wins; a build after →
    nothing changes; the next week becomes the written one), regret / edge on a synthetic week, unknown and unscored
    weeks, weeks summing to the season, the calibration table on 400 synthetic coin flips, calls = `cards.decisions`
    ×12, the DDL = the dbt pre-hooks, and the console page (AppTest). `api/tests/test_v1.py` **6 passed** (needs_db,
    `league_lab_i0a`): Scrubs weeks 1–2 graded; submitted = `fct_league_matchup`; weeks sum to the season and
    roster-weeks to the week; the calls line and table; the API = the Python twin on the source tables; a league we
    do not keep has no `decisions`; marts missing → unavailable. `web/e2e/v1` **2 passed** (phone 375 / desktop
    1300, no sideways scroll). Web lint + typecheck 0 / 0. Ruff: one finding, `api/league_lab_api/research.py:61`
    B010, which is on main and not in this branch's diff. **Whole suites** on the clone: root **1036 passed, 3
    skipped** (8 min, `OMP_NUM_THREADS=1`: the box was at load 17–20 with six suites); API **470 passed, 14 skipped,
    3 failed**. The 3 failures are the brief's known scoring-check ones: `test_ic1` dad's league weeks 1–2 and
    `test_ic_po` ten-yard cut, which fail because the clone has no `*_tds_10p` columns.
  * The record on the clone: 2,235 rows. Weeks 1–4 are rebuilt for both leagues; week 5 is `kickoff`. The rebuilt
    weeks 1–2 match `ops.lineups`' proposed starters exactly (392 of 392). 330 calls, every QB–TE pair with odds
    (one Scrubs week-4 and one week-5 call without: a K / DEF).
  * **Graded, League of Scrubs, weeks 1–2** (both rebuilt from the refit v2.0 board):

    | Week | Teams | Started | Ours | Best | Added (ours − started) | Best − started |
    |---|---|---|---|---|---|---|
    | 1 | 10 | 1242.28 | 1221.40 | 1417.78 | −20.88 | 175.50 |
    | 2 | 10 | 1126.70 | 1124.04 | 1264.90 | −2.66 | 138.20 |
    | season | 20 | 2368.98 | 2345.44 | 2682.68 | −23.54 (−1.2 a team a week) | 313.70 |

    Calls: 60 graded, the starter won 39.0 against 33.44 expected, Brier 0.235. The coin flips landed **59%** for the
    side we leaned (52% expected, 34 calls). News-affected: 0, because rebuilt weeks cannot tell.
  * Forever Unclean Dynasty, same weeks: Added −148.05 / +29.95 → −118.10 (−4.9 a team a week); best − started
    677.90. Coin flips 49% (52% expected, 42 calls); Brier 0.251.
* **What moved**: no projection, lineup total or gain changes. `lineups()` now also writes `ops.lineup_record` (the whole
  `league-lab lineups` run took 4.2 s on the clone with it; the record's cost is mostly the calls' odds). `lineup.DDL` gains the record table.
* **Not done / limits**:
  * The rebuilt weeks are kinder to us than a real Thursday call: they read the final injury report. For weeks 1–3
    they also use the refit board: trained 2016–2025, so no 2026 outcome is in it, but it is not the board managers
    saw. A rebuilt week 3 / 4 that Sleeper had not scored yet reads IR / taxi from today's roster.
  * News-affected cases are measurable only on `kickoff` weeks (from week 5). The flag is a change in the injury
    report, not IG-2's events. When `events.events` merges, the flag can also count an availability event with
    `published_at` between `run_at` and the player's kickoff (a `validation._news_starters` hook; not built).
  * No baseline other than the managers' own lineups: Sleeper's projections as a lineup-maker would be the next
    one (the projection record already compares the calls).
  * No per-team view (About is league-wide). Nothing for MFL leagues: no record is kept for them, and IG-3 owns
    that qualification.
  * Two weeks are a small sample; the page says the weeks were rebuilt.
* **Next**: the PO applies the dbt models and lets the nightly write week 5's record before Thursday's kickoff; after
  week 5 is scored, the first `kickoff` week and its news-affected cases appear. A per-team line on My Week ("our
  lineups would have added X for you") once a few `kickoff` weeks exist.
* **For the PO**:
  1. **dbt to apply**: `dbt/models/marts/edge/mart_decision_record.sql`, `mart_decision_calls.sql`,
     `decision_record.yml` (new source `ops_decisions` + tests). Run `uv run league-lab db migrate` (creates
     `ops.lineup_record`), then `uv run league-lab validate` (rebuilds weeks 1–4, writes the next week), then `uv
     run league-lab dbt build --select source:ops_decisions mart_decision_record mart_decision_calls`. The sync
     publishes both marts: the API names them, and `ops` goes whole. `scripts/hosted_relations.py` against main's
     checkout: the API and the console gain exactly `analytics.mart_decision_record`, `analytics.mart_decision_calls`
     and `ops.lineup_record` (nothing heavier: the grade's other inputs were already published).
  2. **The nightly step (proposal)**: no workflow change. `.github/workflows/nightly.yml` runs `scripts/nightly.sh`,
     and the three V-1 blocks there are the wiring: (a) `ops.lineup_record` in `STATE_TABLES` / `RECORD_TABLES`; (b)
     `soft validate uv run league-lab validate` right after `project`, before `save-record`, so the archive carries
     tonight's rows; (c) `soft decision-marts dbt_step decision-marts build --select mart_decision_record
     mart_decision_calls` after `drift`. Keep (a) in any case: without it a fresh CI database would rebuild every
     played week as `reconstructed` each night and never keep a `kickoff` week. (b) is a safety net: `project`
     already writes the record. Optional: add the two marts to the Makefile's `project` selection (line 41).
  3. **`metric_registry.csv` rows** (dbt seed, PO-owned): `decision_edge, dr1.0, our recorded lineups' points −
     submitted points, —, league-roster-week, available, "Sleeper's points; a K/DEF with no number = NULL"`;
     `decision_regret, dr1.0, hindsight optimum − submitted points, —, league-roster-week, available, "ops.lineup_totals
     is_realised"`; `call_calibration, dr1.0, calls the starter won (tie = ½), calls with odds, league-season,
     available, "Brier + coverage_table"`.
  4. **Merge order**: any. The `ondemand.py` block sits above `record()`, so it does not touch M4's lines. `lib/api.ts`
     sits after `RecordAnswer`, not at the end of the file (where M4 appended). About sits between the calls table
     and "Projections by position" (M4's line is above the calls table). STATUS and CHANGELOG conflict only in the
     usual way: both open a `Wave I-G` heading.
  5. **Decisions Andrew may want to reverse**:
     * the record freezes at the week's **first** kickoff, Thursday, as the brief says. The lineups served on Sunday
       morning are graded only through the news-affected cases;
     * weeks 1–4 are shown, rebuilt and starred, rather than hidden;
     * a starter with no stat row counts 0 (Sleeper's rule) but a K / DEF with no number makes the lineup unknown;
     * About shows the coin-flip line, not the full calibration table, which is on the console only;
     * the weeks so far are unflattering: our lineups would have scored fewer points than the ones started in 3 of
       the 4 league-weeks. That is what the record is for. Say so before "the app's edge" is quoted anywhere.

### IG-3 2026-10-04 — the small opens: the stash writer's drop, MFL's roster freshness, the waiver deadline, the MFL grade's qualification, usage retention (branch `dev/IG3`, database `league_lab_i0b`)

* **Task**: IG-3 (brief § "IG-3"; plan § 17 "I-F delivered … Next": the nightly stash writer's drop rule, the MFL
  roster-freshness line, the waiver deadline, the MFL grade's qualification, usage retention, the console Home guide).
  Plan sections: § 17 (Iteration 17, part G); METRICS § "Drop cost"; WORDS § "Decision quality"; HOSTING § "Usage".
* **1. The stash writer follows `choose_drops`** (`src/league_lab/waivers.py`, `# ---- IG-3` blocks). The moves'
  writer already ranked by IF-1's cost (`sweep_roster` → `choose_drops`); the **stash writer** (`upside_for_roster`)
  still named B3's drop (the least lineup loss, ties to the fewest rest-of-season points) and the API decided claim /
  watch on read. Now each stash add is paired with every legal drop (none on an open spot) at the scenario's
  projection; each pairing is an `ops.waiver_moves`-shaped row (the lineup loss with the add + the drop's pieces) and
  `choose_drops` names the cheapest. The pieces come from the same sweep: `load_and_sweep(pieces_out=…)` computes
  `drop_pieces` for **every droppable player** (a player's pieces do not depend on the add, so no move row's number
  changes) and `waiver_moves` hands them to `upside_after_waivers(conn, season, pieces)`; run alone, the stash writer
  reads them back from `ops.waiver_moves` (`stored_pieces`). `ops.waiver_upside` gains `stash_action` ('claim' when the
  pairing is worthwhile if the role holds — net ≥ 1 this week or ≥ 3 over the horizon, the claims' bar — else
  'watch'), `drop_cost`, `drop_cost_piece`, `net_weekly_gain`, `net_horizon_gain` (`UPSIDE_COST_DDL`, `alter table …
  add column if not exists`; `UPSIDE_DDL` / `UPSIDE_COLUMNS` unchanged so the view's pre-hook copy still matches). A
  watch row keeps the drop a claim would take (the legality tests and the console read it); the screen shows no drop.
  **API** (`decisions.py`, `# ---- IG-3`): `ig3_with_call` joins the writer's call onto the stash rows (`SG.UPSIDE_SQL`
  is the console's and lists its columns; a cached `information_schema` check skips the join on a mart without
  them), `ig3_stash_fields` / `ig3_watch_words`; `ig3_apply_call` applies the call where the stashes are built (`_upside`:
  a roster with no claim never reaches `if1_stashes`) and `if1_stashes` re-decides only rows written before Wave I-G. **Proposed for the PO** (separate commit `a1fc04a`): `mart_waiver_upside.sql` gains the
  five columns (pre_hook `alter table … add column if not exists`, the select).
* **2. MFL's roster freshness** (`mfl_client.MFL.fetched_at(type, league)` — the wall-clock time each cached export
  was read, kept with the cache entry: a stale answer served on an MFL failure keeps its own time; `ondemand.
  mfl_roster_freshness`): `/api/my-week` for an `mfl:` league gains `roster_updated_at` (ISO UTC, to the second) and
  `roster_source` "MFL"; Sleeper answers unchanged. My Week's footer (`MyWeek.svelte`, `# ---- IG-3`): "MFL rosters
  updated 4:05 AM ET ›" → "Rosters and lineups read from MyFantasyLeague Sun, Oct 4, 4:05 AM ET (1 min ago);
  isuckatfantasy reads them again after 10 minutes. The projections are the morning build's." — above IF-4's line,
  which stays the morning build's.
* **3. The waiver deadline** (`decisions.waiver_deadline` / `waivers_deadline_for`; `/api/waivers` → `deadline`,
  INTERFACES § IG-3): Sleeper's `waiver_type` (0 rolling / 1 reverse standings / 2 FAAB), `daily_waivers`,
  `waiver_day_of_week`, `daily_waivers_hour`, `waiver_clear_days` from the league's settings (the client's cache; a
  house league falls back to `dim_league_season.waiver_type` with "see Sleeper" when Sleeper cannot be read); MFL's
  `currentWaiverType` from the league export ("see MFL": the export carries no time); the week's next kickoff from
  `dim_game` ("players lock at their own kickoff — the next game starts Sunday 1:00 PM ET"). Waivers: one line under
  the title (`data-testid="waiver-deadline"`, a `<time>` when the run time is known); the how-to gains "When claims
  run" and the drop's cost words. Scrubs: "Claims run Wednesday 3:00 AM ET (rolling waivers); …"; the dynasty "Claims
  run every day at 5:00 AM ET (FAAB blind bids); …"; dad's league "Free agents are first come, first served on MFL: a
  claim is yours as soon as MFL takes it; …"; 21861 "Claims run on MFL's schedule for this league (blind bids, then
  first come, first served): see MFL for the time; …".
* **4. The MFL grade's qualification** next to the headline grade: `/api/about` gains `grade_note` (`about.grade_note`,
  a small `# ---- IG-3` block in `about.py` — the grades' answer comes from `/api/about`, not `/api/record`); About
  shows it right under "How the model is doing"'s answer, above the grade cards (`grades-qualification`): "These grades
  use Forever Unclean Dynasty's scoring, not Make Football Great Again's, and there is no direct projection record for
  this MyFantasyLeague league: read them as how the model does in general." A non-house Sleeper league: "…
  isuckatfantasy keeps no projection record for <league> yet …". The older `about-why` line below stays (it also
  explains the importance). M4's sentence and V-1's block untouched.
* **5. Usage retention**: `scripts/hosted_usage.sql` ends with `delete from usage.events where at < now() - interval
  '180 days'` (the sync's U-1 block runs it every night as the owner; the app role still has no DELETE); the console's
  Usage page and HOSTING § "Usage" (new paragraph "Retention") say so; `app/Home.py`'s page guide gains "Which screens of
  the web app get used? · Usage".
* **Interfaces**: INTERFACES.md § IG-3 (+ the 05:01 update): `/api/waivers` `deadline {platform, kind, kind_words,
  daily, runs_at, runs_words, clear_days, lock {kickoff, words}, words, source}`; `/api/my-week` (MFL) `roster_updated_at`,
  `roster_source`; `/api/about` `grade_note`; `ops.waiver_upside` + `stash_action`, `drop_cost`, `drop_cost_piece`,
  `net_weekly_gain`, `net_horizon_gain`; `mfl_client.MFL.fetched_at(type, league)`; `waivers.load_and_sweep(pieces_out=)`,
  `upside_for_roster(…, pieces)`, `upside_stashes(…, pieces=)`, `upside_after_waivers(conn, season, pieces=None)`,
  `stored_pieces`, `STASH_PIECE_KEYS`, `UPSIDE_COST_COLUMNS` / `UPSIDE_COST_DDL` / `UPSIDE_ALL_COLUMNS`.
* **Files**: `src/league_lab/waivers.py`, `src/league_lab/mfl_client.py`, `api/league_lab_api/{decisions,ondemand,about}.py`,
  `web/src/lib/api.ts` (one marked block at the end), `web/src/routes/{Waivers,MyWeek,About}.svelte` (marked blocks),
  `scripts/hosted_usage.sql`, `app/Home.py` (one line), `app/pages/99_Usage.py` (one sentence), `dbt/models/marts/edge/
  mart_waiver_upside.sql` (the PO's call, its own commit), `tests/test_waivers_ig3.py` (new, 9), `api/tests/test_ig3.py`
  (new, 24 + the recorder), `api/tests/test_if1.py` (re-pinned), `web/e2e/ig3/fixtures.spec.ts` (new, 3 × phone /
  desktop), `web/fixtures/ig3/api_ig3.json` (the recording, 0.5 MB), `docs/{METRICS,WORDS,HOSTING,STATUS}.md`, `CHANGELOG.md`.
* **Commands**: `uv run league-lab waivers` and `uv run league-lab dbt build --select mart_waiver_moves mart_waiver_upside`
  on `league_lab_i0b` (05:00 ET, as INTERFACES said: 14.6 s; dbt PASS=22, `assert_waiver_upside_is_legal` and
  `upside_drop_or_open_spot` included); `scripts/hosted_usage.sql` twice on the clone as its owner (`postgres`: the
  pipeline role cannot create a schema there) — idempotent, the app role still has no DELETE; `uv run pytest -q tests`;
  `cd api && PYTHONPATH=. uv run pytest -q tests`; `uv run ruff check src app tests api`; `cd web && npm run typecheck &&
  npx eslint . && npm run build`; `FIXTURES_PORT=8606 npx playwright test --config playwright.fixtures.config.ts e2e/ig3
  e2e/if4 e2e/u1 e2e/ib2`.
* **Evidence — the writer's drops, before → after on `league_lab_i0b`** (before = the clone's rows of 2026-10-02, B3's
  rule; after = the writer of this branch):
  `ops.waiver_moves` 3,660 → 3,660 rows, every weekly / horizon gain identical; the best drop per claim changed on
  **44 of 617** Scrubs claims and **3 of 13** dynasty claims; distinct best drops summed over rosters Scrubs 15 → 26
  (roster 6 {Harrison} → {McPherson, Cousins, Harrison}; Carlson's drop Harrison → McPherson, +13.46 both), dynasty
  5 → 5; worthwhile best claims after: 335 of 617 / 3 of 13. `choose_drops` re-run on the written rows of each of the
  22 rosters changes nothing (the API's re-rank finds nothing to change).
  `ops.waiver_upside` 83 → 83 rows (47 Scrubs, 36 dynasty), the stash case and every gain unchanged; `stash_action`
  83 × **watch**, 0 × claim (the scenarios add +0.0 to these lineups over weeks 4–7); the drop a claim would take moved
  on **6** dynasty rows (rosters 9 and 10: Jordan Mason → DeeJay Dallas, Carson Beck → Greg Dulcich — the cheaper by
  season value), 0 on Scrubs. **The screen**: before, 15 dynasty stash cards on rosters with no claim (e.g. roster 12)
  still showed B3's drop (they never reached IF-1's on-read decision); after, 0 cards show a drop — every one says
  watch, as the mart does.
* **Evidence — tests**: root **1,022 passed, 3 skipped** (`tests/test_waivers_ig3.py` 9 new). API **487 passed, 4
  failed, 15 skipped** on the full run after the writer: the three known clone scoring checks (`test_ic1` × 2,
  `test_ic_po`: no `*_tds_10p` columns) and `test_h1::test_waivers_upside_is_mart_waiver_upside[dynasty]` — a real
  catch (a watch with a drop on roster 12), fixed in `b5f22d6`; `test_h1` + `test_ig3` + `test_if1` again: 44 passed,
  1 skipped (the recorder). The 15 skips: the U-1 database tests (the pipeline role cannot apply the usage SQL on this
  clone), IC-3's two flat-settings tests, the IF-4 / IG-3 recorders. Web: typecheck 0 errors / 0 warnings, eslint
  clean, build clean; e2e `ig3` 6 passed (phone 375 / desktop 1300: the MFL line and its exact time on tap, the
  deadline line under the title on both leagues, the qualification between the headline grade and the first grade
  card, no sideways scroll) and with `if4`, `u1`, `ib2` 32 passed. Ruff clean on everything touched
  (`api/league_lab_api/research.py:61` B010 is on `main`, not this branch).
* **Decisions** (nobody to ask): (1) a stash says **claim** only when the cheapest pairing is worthwhile if the role
  holds — the same 1 / 3-point bar as every claim (IF-1's on-read rule compared the scenario's lineup gain with the
  drop's own cost); (2) a watch row **keeps** the drop a claim would take in the table (the dbt legality tests and the
  console's Waiver Wire page read it; `app/lib/signals.upside_detail` would otherwise say "You have an open roster
  spot" on a full roster) — the API hides it; (3) Sleeper's `waiver_day_of_week` read as 0 = Monday … 6 = Sunday
  (2 = Wednesday is Sleeper's default and the one value seen in the leagues here) and `daily_waivers_hour` as an hour in
  **Pacific** time (Sleeper's default 0 = midnight PT = the 3:00 AM ET everyone knows); daily waivers say "every day"
  (`daily_waivers_days`, a bitmask, is not decoded); (4) the lock half names the week's **next kickoff** ("players lock
  at their own kickoff — the next game starts Sunday 9:30 AM ET"), not "the lineup locks Sunday 1 PM" (Sleeper locks per
  player); (5) MFL's export has no claim time: FCFS says a claim is yours when MFL takes it, any other type "see MFL";
  (6) the grade's qualification lives in `about.py` (the grades come from `/api/about`), shown under the headline
  grade; the older line below the metrics stays (it also qualifies the importance); (7) retention 180 days, a plain
  delete in the nightly's SQL file; (8) the moves' writer was already on `choose_drops` (IF-1's `sweep_roster`): the
  only change there is that the sweep also prices every droppable player for the stash writer — no move row's number
  changes.
* **Not done**: the console's Waiver Wire stash region (`app/lib/signals.py`, PO-owned) still words every stash with
  its drop ("Drop X: …") and does not read `stash_action`; the Team page has no freshness line at all (only My Week
  shows IF-4's and now MFL's); `daily_waivers_days` (which days daily waivers run) is not decoded; MFL waiver times
  (the export does not carry them).
* **Next**: the PO's view change and a nightly; then the console's stash wording on `stash_action`.

**For the PO**
1. **dbt** (commit `a1fc04a`, apply or re-make): `mart_waiver_upside.sql` — five `alter table ops.waiver_upside add
   column if not exists …` pre-hooks and the five columns in the select. Until it is applied the API joins nothing
   (a cached `information_schema` check) and keeps IF-1's on-read decision, so the merge order does not matter; after
   it, the next nightly's rows carry the writer's call. The view's tests (`upside_drop_or_open_spot`,
   `assert_waiver_upside_is_legal`) pass unchanged because watch rows keep their drop.
2. **The nightly** needs nothing new: `project` → `waivers_after_project` → `waiver_moves` → `upside_after_waivers` with
   the sweep's pieces. The hosted sync runs `scripts/hosted_usage.sql` as before; its last statement now deletes views
   older than 180 days (the first run deletes nothing: the table is a day old).
3. **Merge notes**: `decisions.py` gains one line in `waivers()` (the deadline), one in `_upside`, a block in
   `if1_stashes` and two blocks at the end of the file; `ondemand.py` one line at the end of `my_week` + a block after
   it; `About.svelte` a block right under `grades-answer` (not in the record section — no overlap with M4 / V-1);
   `api.ts` one block at the end (adds `Waivers.deadline`, `MyWeek.roster_updated_at` / `roster_source`,
   `AboutAnswer.grade_note`). `api/tests/test_if1.py` is re-pinned to the rule: it passes on a mart written before
   IF-1's cost and after.
4. **Decisions Andrew may want to reverse**: the stash's claim bar (the claims' 1 / 3 points, not "any gain over the
   drop's cost"); Sleeper's hour read as Pacific (if his leagues' Wednesday run is not 3:00 AM ET, it is one constant,
   `SLEEPER_WAIVER_TZ`); 180 days of usage.
5. **Clone state**: `league_lab_i0b`'s `ops.waiver_moves` / `ops.waiver_upside` were rewritten at 05:00 and the two
   views rebuilt (IG-1 was told in INTERFACES); the `usage` schema was created there (empty).

## Wave I-H (Iteration 18)

### PO merge — Wave I-H, 2026-10-04 (Sunday, 11:50–14:30 ET)

* **Why**: Andrew: "Proceed with the next waves." (and: Wave J is parked by his choice — no Sleeper licence request;
  "a prototype I would love to commercialize, the odds impossibly slim"). The brief is `scratchpad/waveIH/BRIEF.md`;
  five Opus devs in parallel (spawned in one message this time), 65–125 min each.
* **Delivered** (the hand-backs below; integration branch `integ/IH` → `main`): **M6** v3.2 — the cold-start prior
  lives on the stat line (`calibration.blend_lines` before `nfl_lines`: every component scaled by blended ÷ raw, so
  `ops.projections`, `_lines`, `_ranges` and every on-demand request agree to the cent; **on by default**,
  `LEAGUE_LAB_COLD_START=0` to turn off; re-measured on the line it still keeps at RB / WR / TE: flagged MAE −0.09 /
  −0.31 / −0.34, 4–5 of 5 seasons, the board a hair better), `ensure_oof` in the nightly (`ops.calibration_oof`
  travels), veterans on a new team measured three ways and **not kept** (the MAE-fitted scale wins by projecting the
  median — rejected; a mean-unbiased WR scale is a v3.3 lead), `why.weights` per week, the record's Sleeper side at
  the odds (`ops.market_record`, `sl_priced` coalesced in EV weeks). 2026 board: 1,014 of 9,911 stat lines move
  (78 players, weeks 5–18 only; undrafted rookies with no game fall from the model's 5–6 to ~2.1–2.6; Jordyn Tyson
  6.08 → 8.62; Germie Bernard unchanged); 37 of 440 lineup totals move, Andrew's rosters not. `MODEL_VERSION` stays
  v3.0 (M6's call). **V-2** the decision record personal and live — news-affected cases from the event store
  (`validation.news_overrides`), `decisions.team` on `/api/record?team=` + the Team page's "Your calls this season"
  (started / ours / best / Sleeper's lineup per week, the close calls graded), **MFL leagues** (`record_mfl.py`: the
  on-demand lineup frozen at the week's first kickoff for `LEAGUE_LAB_RECORD_MFL`, graded on MFL's weekly scores;
  dad's league on the fixture: our lineups −3.8 a team a week, the coin flips 57%), "Sleeper's projections as a
  lineup" as a comparator (`ops.decision_market`); the writers moved to `record_mfl` / `record_run` so
  `hosted_relations.py` does not publish raw tables. **IH-1** the stale state (`freshness.py`, 30 h; `/api/health`
  `stale` / `age_hours`, `/api/status` `nightly`, the console's Data Status page), **error states** the app never had
  (`ErrorCard`: the API down with Try again, a 500 naming `/api/status`, "Still waiting" after 25 s, "Signed out —
  sign in again" after a 401), events retention (120 d superseded news / briefs, 400 d availability), the failure
  summary `scripts/nightly_failure_summary.sh`, the Worker's status page reports the last dispatch when a KV binding
  exists. **IH-2** units' drop cost on Waivers (dad's league team 2: the Saints K claim drops the Jaguars K, not Cooper
  Kupp; team 8's screen unchanged — an open spot), the console's stash words on `stash_action`, the Team page's MFL
  freshness, `daily_waivers_days` ("every day except Saturday"), the Questionable line in "What changed", `game_key`
  on availability events, "when QB and QB are on a bye" fixed. **IH-3** the week's win probability
  (`decisions.lineup_win_probability`: per-player distributions from the ranges centred on the projection, paired
  draws, teammates / opponents correlated, a logit shrink of 0.60 fitted on 2024 and tested on 2025; calibration on
  308 house-league matchups: Brier 0.2395, the favourite predicted 58.0% / won 57.5%), the line under the opponent on
  My Week ("You're a slight favorite this week: 64%, 120 to 104 expected."), `GET /api/league/week-odds` on the
  League screen; information only, never a pick.
* **PO, on the merge**: nine doc / `api.ts` / `Team.svelte` conflicts (keep both); **Andrew (14:05 ET): "DO NOT TELL
  PEOPLE THAT THE DATA IS STALE... MAKE IT ROBUST SO IT DOESNT FAIL"** — IH-1's My Week banner and footer suffix are
  **off** (`staleWords` is null in `MyWeek.svelte`; the markup stays, one line turns it back on); the stale state stays
  on `/api/health`, `/api/status` and the console for the operator; the robustness is the trigger (HOSTING § 5), with
  GitHub's own schedule as the fallback (it fired twice today, 11:57 and 13:33 ET, both green) and the failure summary
  + GitHub's failure email. Wired: the `notify` step (`if: failure()`) and `LEAGUE_LAB_RECORD_MFL: "mfl:70587"` on the
  nightly; registry rows `decision_market_edge` (dr1.1), `week_win_probability`; HOSTING's `game_key` line; the main
  database migrated (`calibration_oof`, `market_record`, `decision_market`), `validate --mfl mfl:70587` (Scrubs /
  dynasty weeks 1–5 recorded: the dynasty −4.9 a team a week on weeks 1–2, 42 coin flips 49%), the wave's dbt models
  and seeds built (`PASS=73`). **Checks**: root **1118 passed** (+2 Sunday-clock failures identical on `main`), API
  **518 passed / 3 xfail** (+45 Sunday-clock failures — every one re-run on `main`'s code at the same hour fails the
  same way: the on-demand path locks players as games kick off; `test_u1` / `test_ig2` deselected because they write
  to the main database's schemas), e2e **271 passed**; ruff / svelte-check / eslint / build clean; the merged API on
  the main database answers `win`, `decisions.team`, `week-odds`, `nightly`, the dynasty's deadline words.
* **Decisions the PO took (Andrew may reverse)**: the stale words never reach a league-mate (his call); the cold-start
  prior **on by default** (M6's call, kept); IH-2's three on-demand MFL pins are `xfail(strict=False)` until the
  API's fixture tests get a pinned clock — **the next PO item**: a `league_lab.clock.now()` read by the six wall-clock
  sites (`anyleague` ×3, `decisions` ×3) with `LEAGUE_LAB_NOW` for tests, so the suites stop going red on Sunday
  afternoons; IH-3's shrink 0.60 and the opponent's *best* lineup; V-2's "a status change counts as news whenever it
  differs from what the build saw".
* **Not done / next**: the pinned clock (above); the error card on the remaining screens (one line each); the Worker's
  KV binding for the last-dispatch line (optional); live in-game points in the win probability (a game in progress
  counts as its full range); MFL live points; a DEF's range on the house path; the mean-unbiased new-team scale at WR
  (v3.3); the re-grade of the win probability after weeks 4–6; `MODEL_VERSION` bump when the record should tell
  blended weeks apart.

### M6 2026-10-04 — v3.2: the cold-start prior on the stat line, veterans on a new team, the market at the odds (branch `dev/M6`, clone `league_lab_m1`)

* **Task**: Wave I-H M6 (`scratchpad/waveIH/BRIEF.md` § M6; plan § 17 "v3.1 → v3.2"); METRICS § "Calibration of the
  top" → "v3.2" (new) and § "The record's pricing column" (the market record, built); INTERFACES.md § M6.
* **Why**: M5 measured the cold-start prior and kept it at RB / WR / TE. But as wired it moved the house leagues'
  points and not the stat line. Every request prices the line, so the house board and an on-demand league would have
  shown two numbers for the same rookie (IB-0's bug). That is why it shipped off.

**The harness table** (the PO reads this first). Δ = candidate − v3.0. "Flagged rows" are the cold starts (or the
new-team veterans). MAE is the leagues' average per season. "Seasons" = seasons better, of 5 (2021–2025). Both house
scorings. The rule is M5's: the flagged rows' MAE at least 0.05 lower in ceil(2n/3) seasons, and `decide` not
"hurts" on the board.

| Group (switch) | Position | flagged rows (a league) | Δ MAE flagged (seasons) | flagged bias before → after | Δ MAE board | Δ Spearman board | Decision |
|---|---|---|---|---|---|---|---|
| **cold start on the line** (`LEAGUE_LAB_COLD_START`, cs1.1; priors on the 3 seasons before = production) | RB | 461 | **−0.092** (4 of 5) | −0.62 → −0.33 | −0.006 | +0.0012 | **keep** |
| | WR | 690 | **−0.314** (5 of 5) | −0.80 → −0.12 | −0.018 | +0.0030 | **keep** |
| | TE | 347 | **−0.341** (5 of 5) | −0.98 → +0.06 | −0.019 | +0.0028 | **keep** |
| cold start on the line, priors on 2018..S−1 (M5's harness window) | RB / WR / TE | 461 / 690 / 347 | −0.159 (4) / −0.320 (5) / −0.291 (5) | −0.62 → −0.32 / −0.80 → −0.15 / −0.98 → −0.05 | −0.009 / −0.018 / −0.016 | +0.0018 / +0.0034 / +0.0034 | keep |
| M5's wiring (points per scoring), re-run on the same rows | RB / WR / TE | 461 / 690 / 347 | −0.159 (4) / −0.314 (5) / −0.298 (5) | −0.62 → −0.33 / −0.80 → −0.17 / −0.98 → −0.08 | −0.009 / −0.018 / −0.017 | +0.0018 / +0.0034 / +0.0037 | (= M5's table: the harness is the same) |
| new team: the cold blend keyed on games with the team (the brief's design) | RB | 542 | +0.028 (2) | −0.52 → −0.47 | +0.002 | +0.0002 | drop |
| | WR | 943 | +0.011 (0) | −0.94 → −0.94 | +0.001 | +0.0002 | drop |
| | TE | 389 | +0.030 (2) | −0.45 → −0.51 | +0.002 | −0.0005 | drop |
| new team: a scale on the line fitted on MAE | RB | 542 | −0.283 (4) | −0.52 → **+1.00** | −0.020 | −0.0006 | **not kept** (the rule says keep; it projects the median: k at the 0.70 floor, the bias flips sign) |
| | WR | 943 | −0.438 (5) | −0.94 → **+0.50** | −0.034 | −0.0006 | not kept (same) |
| | TE | 389 | −0.242 (5) | −0.45 → **+0.47** | −0.015 | −0.0017 | not kept (same) |
| new team: a mean-unbiased scale (Σ actual / Σ projected per step) | RB | 542 | −0.023 (3) | −0.52 → −0.39 | −0.001 | +0.0003 | drop |
| | WR | 943 | −0.102 (4) | −0.94 → −0.65 | −0.008 | +0.0004 | not kept (passes; the third shape tried — a v3.3 lead) |
| | TE | 389 | +0.031 (1) | −0.45 → −0.49 | +0.002 | −0.0008 | drop |

* **Delivered**:
  * **The blend on the line** (`calibration.blend_lines`, called by `projections.project` in a `# ---- M6` block
    right before `nfl_lines`).
    * For each cold RB / WR / TE player-week, one scale `k` = blended / raw points in the anchor scoring (the
      reference league's), set from M5's prior and weights (`line_scales`).
    * Every component of the model's line is multiplied by `k`. The scaled line is then priced and ranged by the
      same models (`predict_position(..., lines=)`, the frozen-line path).
    * So `ops.projection_lines`, `ops.projections`, `ops.projection_ranges` and every request agree to the cent, in
      any scoring and either pricing mode.
    * `calibrate_outputs` no longer blends points; M5's wiring stays reachable as `v31_outputs(..., cold_on_points=True)`
      for the comparison.
    * `signals.scenarios` follows the scaled line (`rescale_to_stored`; `run_signals` reads the stored line). Without
      that, a rookie with a live role alert would fail `scenario_base_is_the_projection`, the class of bug M4 found
      before the flip.
  * **The switch**: `LEAGUE_LAB_COLD_START` defaults **on** (`COLD_DEFAULT = True`; `0` / `off` turns it off; only
    the nightly writer reads it). The blend is the identity at 3 games, and for a line under half a point.
  * **The fitting rows where the nightly runs**:
    * `calibration.ensure_oof` rebuilds `ops.calibration_oof` (`run_build_oof`) only when the table does not hold the
      newest 3 completed seasons of this `MODEL_VERSION`. It checks a new `model_version` column.
    * The nightly's `calibration-oof` step (soft, before `project`; `scripts/nightly.sh` `# ---- M6`).
    * `ops.calibration_oof` is in `STATE_TABLES`; `db migrate` creates it.
  * **Veterans on a new team**:
    * `team_games_before` (games with the current team in the current stint), `is_new_team`, `blend_frame`.
    * Measured three ways, none kept (`NEW_TEAM_POSITIONS = ()`). The wiring is there for a kept position.
  * **`why.weights` / `why.explain` per week**: `season` / `week` keyword arguments; the mode is
    `scoring.ev_for_week`. `player.py`'s card passes them (one line, `# ---- M6`). A frozen flat week's "why this
    number" pieces stay flat on the morning after the flip. The rest-of-season pieces (`ondemand.py`, not mine) keep
    the newest mode, which is right for future weeks.
  * **The record's Sleeper side at the odds** (M4's proposal):
    * `projections.market_record` writes `ops.market_record` at the end of `project` (soft). For each house
      league-week labelled `ev`, it stores Sleeper's last pre-kickoff line priced with `price_projected(ev=True)`
      (`price_market`).
    * `mart_projection_record.sl_priced` reads `coalesce(mr.sleeper_points, league_points(…))` on the same snapshot,
      only in an `ev` week.
    * A `sources.yml` row (with a uniqueness test). The mart's pre-hook and `db migrate` create the table.
* **Interfaces**: INTERFACES.md § M6. There are no new columns on `ops.projection_lines` / `ops.projections` /
  `ops.projection_ranges`. The moved columns, for a blended row: `proj_*`, `proj_points`, `p10..p90`. New:
  * `ops.calibration_oof.model_version`;
  * `ops.market_record`;
  * `calibration.LAST_LINE_BLEND`, the last run's scaled player-weeks.

* **Evidence**. Unless named, everything is on the clone `league_lab_m1`, flat mode (the env unset, as M4 left it).
  * **The harness**:
    * Rows: `scratchpad/m6/oof_lines.py`, the walk-forward of 2018–2025 with the stat line kept; RB / WR / TE;
      8 seasons in 4 min.
    * Tables: `harness.py` / `seed.py`, read only.
    * Re-running M5's wiring reproduces M5's table to the third decimal.
    * The seed: `feature_experiments.csv` +120 rows (`cold_start_line`, `new_team_blend`, `new_team_scale_mae`,
      `new_team_scale_mean`, 30 each).
  * **`ensure_oof`**: the first call rebuilt `ops.calibration_oof` to 2023–2025 (34,592 rows) in **598 s** on this
    sandbox (load 5–10 on 2 CPUs; about 2–3 min alone). The second call took **2 s** and wrote nothing ("current").
    Unit test: twice = once, `force` rewrites, a model bump rebuilds.
  * **A full `project` with the switch at its default (on)**:
    * Exit 0 in 1,478 s (load 14–16; the first try with `OMP_NUM_THREADS=2` stalled, as M5 saw, and was restarted
      single-threaded).
    * Log: "cs1.1 on the line: 1374 player-weeks scaled". That count includes weeks 1–4, which the writer then keeps
      as frozen.
    * Weights in the reference league, 2023–2025: RB 0.0 / 0.1 / 0.6, WR 0.0 / 1.0 / 1.0, TE 0.0 / 0.7 / 0.4.
    * Scenarios: "base = stored projection to 0.00e+00 on 14 rows". No scenario player was a cold start on the
      clone; `rescale_to_stored` has a unit test.
  * **dbt on the clone**: the nightly's projection-marts selection plus `assert_projection_ranges_price_the_lines`,
    `assert_house_projections_are_the_nfl_wide_rows`, `assert_frozen_nfl_wide_precede_kickoff`, the `ops.market_record`
    source test and the seed: **PASS=155, WARN=0** (the warn test that would have flagged M5's wiring passes).
  * **The 2026 board, before → after** (before = M4's flat build of this morning, which a switch-off build on this
    code reproduces to the bit; after = the switch on):
    * **Stat lines**: 1,014 of 9,911 moved (78 players; RB 260 / WR 260 / TE 494 player-weeks), weeks 5–18 only.
      Frozen weeks 1–4 moved **0**. Every scaled line has every component × k (max |ratio − k| = 2.2e-16).
    * **House rows**: 2,007 of 19,822 moved. The other 21 blended player-weeks have k within 0.002 of 1 and round
      to the same cent.
    * **Mean change a row**: the dynasty RB −1.22, WR −2.26, TE −0.97; Scrubs RB −1.08, WR −1.86, TE −0.79. The
      range is −3.53 to +2.78.
    * **The five biggest moves of week 5**: undrafted WRs with no game, the model's "no history" 5–6 points pulled to
      the undrafted prior.
      * The dynasty: Malik McClain 6.12 → 2.59, Brock Rechsteiner 6.08 → 2.60, Cole Burgess 6.05 → 2.58, Montorie
        Foster Jr 5.85 → 2.59, Camden Brown 5.84 → 2.58.
      * Scrubs: McClain 5.00 → 2.12, Burgess 4.97 → 2.12, Rechsteiner 4.95 → 2.12, Adam Randall (RB, pick 174)
        5.38 → 2.62, Chip Trayanum (RB) 5.42 → 2.70.
    * **M5's examples**, week 5:
      * **Jordyn Tyson** (WR, pick 8, no game) 6.08 → **8.62** in the dynasty and 4.95 → **7.02** in Scrubs (P90
        14.28 → 15.60).
      * **Germie Bernard** (WR, pick 47, one game) **9.93 → 9.93**: the 2023–2025 fit keeps the model from a WR's
        first game on. M5's 9.93 → 4.85 came from the 2018–2024 weights and does not happen.
      * Omar Cooper Jr. (pick 30, one game) 3.09, unchanged.
      * Chip Trayanum 6.20 → 3.09.
    * **Rostered rookies, week 5**: 23 roster rows move.
      * Jeremiyah Love (RB, pick 3): 11.65 → 9.48 in the dynasty, 10.35 → 8.43 in Scrubs.
      * Jadarian Price (RB, pick 32): 10.70 → 8.86 / 9.71 → 8.04.
      * Kaelon Black (RB, pick 90): 8.24 → 7.05.
      * Andrew's dynasty roster 12: Adam Randall 6.14 → 2.99, Jonah Coleman 8.00 → 7.00 (bench). Week 4–6 totals
        unchanged (111.15 / 118.12 / 107.51).
      * Scrubs roster 2: unchanged (117.02 / 100.63 / 112.30).
    * **Lineup totals** (the same code, switch off → on): 37 of 440 moved, all in weeks 5–18. The dynasty: 17, mean
      −1.52 (−2.50 to −0.35). Scrubs: 20, mean −1.35 (−1.93 to −0.02). The largest is dynasty roster 9, week 10,
      107.74 → 105.24.
  * **One number everywhere**:
    * `api/tests/test_m6.py` (needs_db, post-run clone): every week-5 rookie RB / WR / TE starter's line, priced on
      request, equals his `ops.projections.proj_points` (abs 1e-9), in both leagues.
    * **My Week = the record** (M4's parity, abs 0.005) for every roster starting a rookie: dynasty 7 (Kaelon Black,
      blended), 9 (Jadarian Price, blended), 12 (Denzel Boston), and Scrubs 6 (Boston).
    * `tests/test_m6.py`: the house rows and the request side's price of the line are equal **bit for bit**, switch
      on and off × flat and EV, in a linear and a bonus scoring.
  * **The record's Sleeper side**, demo on the clone, then reverted:
    * Setup: the Sleeper projections fixture planted 12 h before week 4's kickoff and the dynasty's week 4 labelled
      `ev`. `market_record` wrote 29 rows.
    * The compiled mart's `sl_priced` equals `ops.market_record` on every QB–TE row. 28 of 29 moved off the macro,
      mean +0.81. Josh Allen 31.58 → **33.20**, the card's "Sleeper's projection" at the odds (M4's number).
      The K stays on the macro.
    * Reverted: 581 labels back to NULL, the snapshot removed, `ops.market_record` empty.
  * **Tests**:
    * `tests/test_m6.py`: **15 passed**. Identity at N games; the scaled line toward the draft slot; parity bit for
      bit × 4; the default; the points path no longer blends; no rows / no position; the anchor; the stint counter;
      `ensure_oof` twice = once; the week's mode; the market pricing; the scenario rescale.
    * `api/tests/test_m6.py`: **6 passed**.
    * `tests/test_m5.py`: 17 passed (one test re-pointed).
    * `api/tests/test_m4.py`: 8 passed.
  * **Suites**:
    * **Root**: 1,093 passed, 4 skipped, 2 failed. With the `test_m4` pin below, 1,094 pass and 1 fails. The failure is
      `test_my_week::test_my_week_is_the_mart[Scrubs-2]` ("2 <= len(cards)"): Scrubs roster 2 has one card in
      week 5 on this clone (one playable bench player; Coleman, Kelce, McMillan and Mahomes are unplayable). It
      fails the same way with the switch off. `test_m4::test_m3_numbers_under_the_record_mode` pinned RB 0.71, and
      the blend moves it to 0.72 (Love and Price are in the RB top 24). The pin now holds either build of the clone
      to the cent.
    * **API**: 505 passed, 11 skipped, 43 failed. All 43 are this clone's state, not M6:
      * they fail identically with `main`'s code (`ad4040e`, a scratch worktree) on the same database;
      * they fail identically after a **switch-off** `project` on the same code.
      * They are pins on the main database's state (IF-1's McPherson / Carlson, IG-1's Finder pairs, IB-2's DEF
        wording, MFL fixture leagues, `test_ic1`'s `*_tds_10p`). M4 saw 4 of them on this clone; I-G's merge added
        the rest.
  * **Switch off = v3.0 to the bit**: a `project` with `LEAGUE_LAB_COLD_START=0` (340 s, the box idle)
    reproduces M4's board exactly: 0 of 20,718 house rows and 0 of 9,911 lines differ.
  * **Same code, off → on**: the 37 lineup totals above, weeks 5–18 only. Against M4's morning build, 15 week-4
    totals moved as well. That was the lineup service on today's code, not the blend: off → on moves none in week 4.
  * **The clone ends on**: a third `project` with the default (336 s with the marts; dbt PASS=145, WARN=0). It
    equals the first on-run to the bit (0 of 20,718 rows differ). On it, `api/tests/test_m6.py` + `test_m4.py` pass
    14 / 14 and the root `test_m4.py` + `test_m5.py` + `test_m6.py` pass 51 / 51.
  * **Lint**: `uv run ruff check src app tests api`: clean.

* **Not done**:
  * Ranges are not re-scored on the line. The harness rows are the component-only walk-forward; the scaled line's
    range is the model's own range for that line.
  * `MODEL_VERSION` stays `v3.0` (see For the PO 3).
  * The mean-unbiased new-team scale at WR is a lead, not wired.
  * The record's Sleeper side for a K stays the macro (flat, as ours).
* **Next**: the PO merges and runs the nightly once by hand (the first night builds `ops.calibration_oof`, about
  2–3 min on the runner). Then v3.3: the new-team WR scale with a rule fixed first, and the QB graded range target
  (M5's marginal keep, still off).

**For the PO**
1. **Merge.** The files outside M6's list, each a marked block:
   * `src/league_lab/signals.py` (`# ---- M6`, two blocks). Without them a rookie with a live role alert fails
     `scenario_base_is_the_projection` on the first nightly.
   * `src/league_lab/db.py` (`migrate` creates `ops.calibration_oof` and `ops.market_record`).
   * `api/league_lab_api/player.py` (one line: the card passes the week to `why.explain`).
   * `tests/test_m5.py` (one test points at M5's points path, `cold_on_points=True`).

   `projections.py`: one block before `nfl_lines`, one line after `waivers_after_project`, and a block at the end of
   the file; M4's and M5's spots are untouched. `feature_experiments.csv` gains 120 rows at the end (CRLF kept).
   `CHANGELOG` adds a `## 2026-10-04 — Wave I-H` heading, as every dev will; keep one.
2. **dbt**, in the nightly's projection-marts step:
   * `mart_projection_record` (the `sl_priced` coalesce, one more pre-hook);
   * the `sources.yml` row `ops.market_record` (**yours to accept**: the brief let me add it);
   * the seed `feature_experiments`.

   Nothing to apply by hand: `db migrate` and the mart's pre-hook create the tables.
3. **`MODEL_VERSION` stays `v3.0`** (my call; reversible). The blend is a post-hoc correction with its own version
   (`cs1.1`, logged every run), like cal1.0. A bump to `v3.2` would rerun `backtest-v2` in the nightly (minutes; it
   would not measure the blend anyway), refit the importance and rebuild `ops.calibration_oof` (about 2–3 min). The
   cost of not bumping: the record cannot tell blended weeks from unblended ones by `model_version`. If you want that
   label, it is one constant plus `tests/test_personnel.py`'s pin.
4. **The nightly**:
   * Nothing to set: the switch defaults on, on the nightly writer only. Render gets nothing; the API never reads the
     switch.
   * The first run after the merge builds `ops.calibration_oof` (about 2–3 min on the runner, 10 min on this loaded
     sandbox). Every later run reads two rows (2 s here).
   * The hosted copy gains `ops.calibration_oof` (about 35k rows, ~3 MB) and `ops.market_record` (QB–TE × EV
     league-weeks, about 600 rows a week for the dynasty).
   * Rollback: `LEAGUE_LAB_COLD_START: "0"` on the `project` step's env (`.github/workflows/nightly.yml`, yours),
     then re-run. Weeks that kicked off blended keep their rows (B5).
   * The nightly prices at the odds (M4's flip). The blend is the same under EV: the parity tests cover both modes,
     and only the anchor's scale is set in flat Scrubs, which EV does not move.
   * `HOSTING.md`'s "What stops a night" table has no row for the new soft step (not my file). A proposed row:
     `| calibration-oof | the cold-start prior's fitting rows could not be built | Nothing urgent: project publishes
     the model's own lines for cold starts (v3.0's numbers) and logs "stat lines unchanged"; reproduce with uv run
     python -c "from league_lab.calibration import ensure_oof; ensure_oof()" |`.
5. **What moves on the first nightly**: weeks 5–18; week 4 is frozen. The numbers are in "Evidence" (the clone's
   board).
6. **Decisions Andrew may want to reverse**:
   * **On by default**, now that the line carries it.
   * **A debut is the draft slot's average.** The model gets weight 0 at career game 0. A first-round WR rookie with
     no game goes up, an undrafted one goes down to about 2. From the first game on, the 2023–2025 fit keeps the
     model at WR (weights 1.0 / 1.0 at games 1 / 2), so a rookie who played is not pulled back after one game.
     That differs from M5's 2018–2024 example (Bernard 9.93 → 4.85, which does not happen now).
   * **One scale per player-week**, set in the reference league's scoring and used by every league.
   * Lines under half a point are not scaled.
   * **The new-team MAE scale is rejected on principle** (it projects the median).
7. **Clone state** (`league_lab_m1`):
   * three `project` runs on today's code (on, off, on again); it ends on, in flat mode, with the projection marts
     rebuilt;
   * `ops.calibration_oof` rebuilt to 2023–2025 with `model_version`;
   * `ops.market_record` created, 0 rows;
   * the market demo's planted snapshot and week-4 labels reverted (581 rows back to NULL; `raw.sleeper_projections`
     back to 0 rows).

### V-2 2026-10-04 — the decision record, personal and live: the event store's news flag, one team's calls, MFL leagues, Sleeper's projections as a lineup (branch `dev/V2`, clone `league_lab_i0a`)

* **Task**: Wave I-H V-2 (brief `scratchpad/waveIH/BRIEF.md` § V-2; V-1's "Not done"): METRICS § "The decision record"
  → "Personal and live" (dr1.1, appended); WORDS § "The decision record, personal"; INTERFACES.md § V-2 (draft 12:00,
  final 12:50).
* **Delivered**:
  1. **News from the event store** (`validation.news_by_starter`, `news_overrides`, `apply_news`). A `kickoff`
     record's starter is news-affected when `events.events` has an availability event for him after the record's
     `run_at` and before **his own** kickoff (his game in `dim_game`; unknown → the week's first kickoff + 4 days)
     whose status differs from the one the build saw (none = ACTIVE). The store answers for a league-week only when it
     was running across it (first availability event ≤ the first kickoff, newest ≥ `run_at`); otherwise V-1's report
     rule is the fallback. `news_source` = events | report on every roster-week, `decisions.news.source`, the
     sentence names the count and the net ("2 lineups had a starter's injury status change between our build and his
     kickoff; there our lineups scored −4.1 against the ones started. They are graded apart: we could not have
     known."). The store lives on the hosted copy and the marts are built in the nightly's database, so the marts
     keep the report rule and **the API applies the store's flags on the request** (`ondemand.event_news`; the store
     off / missing / unreadable = the marts' flags, never an error); `league-lab validate` reads the store itself where
     the database has one.
  2. **One team's view**: `/api/record?league=&team=` → `decisions.team` (`validation.team_summary`): the roster's
     graded weeks (started / ours / best / Sleeper's / the edge / the regret / `n_changed` / the news flag / its close
     calls with words), the season sums (they reconcile with the league's to the cent), the calls' calibration, the
     news-affected weeks and the sentences ("Weeks 1–2: you started 265.0; our lineup would have scored 253.9; the
     best possible was 281.7."). **Team page "Your calls this season"** (`Team.svelte` V-2 block, end of the left
     column): the sentence, a short table (Week · You · Ours · Best · Sleeper when we have it; rebuilt weeks starred;
     the season row), the calls line, "The close calls, week by week" (each with "(we gave it 64%)" and how it landed),
     the rebuilt-weeks footnote, "The whole league's record" link. Nothing when the team has no graded week. **About**
     links to it ("Your team's calls this season ›") and shows Sleeper's line; **the console's Record page** shows the
     picked team's sentences and table.
  3. **MFL leagues in the record** (new module `league_lab.record_mfl`): the on-demand lineup (`anyleague._solve_roster`,
     My Week's own frame) frozen under the same rule — the next week written before its first kickoff from the current
     rosters (`kickoff`); a played week rebuilt once from the rosters MFL's `weeklyResults` lists for it, on that week's
     frozen projection lines, as of a second before kickoff (`reconstructed`); a week MFL has not scored waits. Rows in
     `ops.lineup_record` with `league_id = 'mfl:<id>'` (written by `league-lab validate` for `LEAGUE_LAB_RECORD_MFL` /
     `--mfl`). The grade (`record_mfl.mfl_load`; `/api/record` on request): submitted = the franchise's starters at MFL's
     scores, optimum = MFL's `opt_pts`, ours = the record's starters at MFL's player scores; a double header once; a
     starter on no franchise = unknown. `/api/record?league=mfl:…` keeps IC-4's `results` and gains `decisions`
     (`platform: "mfl"`); About shows dad's league's record with the rebuilt weeks starred.
  4. **"Had you started Sleeper's projections"** (`ops.decision_market`, `record_run.write_market`, every `validate`):
     the best lineup of the roster the record saw at Sleeper's last pre-kickoff projection, priced in the league's
     scoring like ours (a K flat; a DEF keeps our value — Sleeper's DEF line is not priced); graded like ours
     (`mart_decision_record.market_points`, `market_edge`, `n_market_unknown`; a dbt test holds market_edge = market −
     submitted); `decisions.weeks[].market`, `season_totals.market`, `sentences.market`; the Team table's Sleeper
     column. Scrubs / dynasty only.
  5. **Modules** (decided on the way): the writers that reach outside the database live in two new modules —
     `record_mfl` (anyleague / MFL; the API imports it lazily) and `record_run` (`validate`, the Sleeper-lineup writer
     and its `raw.sleeper_projections` read; only the CLI imports it). `scripts/hosted_relations.py` follows every
     import of a reader's modules: with the code in `validation`, the console's closure had gained `raw.sleeper_projections`
     and eight more relations (the sync would have tried to publish raw). Now the API and console closures gain exactly
     `ops.decision_market` (diffed against main). `validation.validate` moved to `record_run.validate` (only the CLI
     called it).
* **Files**: `src/league_lab/validation.py` (V-1 code + V-2 block), `src/league_lab/record_mfl.py` (new),
  `src/league_lab/record_run.py` (new), `src/league_lab/lineup.py` (V-2 block: `MARKET_DDL`, `mfl_record_keys`),
  `src/league_lab/cli.py` (validate: `--mfl`, the market sentence, the import), `api/league_lab_api/ondemand.py` (V-1 block:
  `record_decisions(team)`, `_with_decisions(team)`; V-2 block: `event_news`, `decisions_team`, `mfl_decisions`),
  `api/league_lab_api/main.py` (the record route's `team`), `dbt/models/marts/edge/mart_decision_record.sql`,
  `mart_decision_calls.sql`, `decision_record.yml`, `app/pages/13_Record.py` (V-2 section), `web/src/lib/api.ts` (V-2
  block after V-1's), `web/src/routes/Team.svelte` (V-2 block), `web/src/routes/About.svelte` (V-2 lines in the V-1
  block, `team` destructured), `tests/test_v2.py`, `api/tests/test_v2.py`, `web/e2e/v2/fixtures.spec.ts`,
  `web/fixtures/v2/record_decisions_1389709692405551104_6.json`, `web/fixtures/v2/record_decisions_mfl70587_8.json`,
  `docs/METRICS.md`, `docs/WORDS.md`, `CHANGELOG.md`, this section.
* **Commands**: `league-lab validate --season 2026 --mfl mfl:70587` on the clone with the MFL fixtures
  (`LEAGUE_LAB_SLEEPER_FIXTURES` / `LEAGUE_LAB_MFL_FIXTURES`; 17 s); `league-lab dbt build --select source:ops_decisions
  mart_decision_record mart_decision_calls` (**PASS=19**); `uv run pytest -q tests/test_v2.py tests/test_v1.py`; `cd api
  && PYTHONPATH=. uv run pytest -q tests/test_v2.py tests/test_v1.py`; `cd web && npm run lint && npm run build`;
  `FIXTURES_PORT=8612 npx playwright test --config playwright.fixtures.config.ts e2e/v2 e2e/v1 e2e/ig3` (recorded with
  `V2_RECORD=http://localhost:8712`, the fixture API on the clone); `uv run python scripts/hosted_relations.py` (diffed
  with main's checkout); the whole root and API suites.
* **Evidence**:
  * `tests/test_v2.py` **12 passed** (the news flag on synthetic events: a move after the build and before his game
    flags, the same status / before the build / after his own kickoff do not, a Friday return to ACTIVE does; no
    store across the week → the report rule; rebuilt weeks never; the grade's count and net and the request-side
    overrides; the teams add up to the league; the MFL grade on the 70587 fixture's weeks 1–2 — every franchise's
    submitted = MFL's score, regret = `opt_pts` − score, a swapped starter moves the edge by the difference, a starter
    on no franchise is unknown; a double header once; Sleeper's lineup on a synthetic roster; the env; the DDL = the
    dbt pre-hook; the console page). `tests/test_v1.py` 23 passed (unchanged numbers).
  * `api/tests/test_v2.py` **7 passed** (needs_db, `league_lab_i0a`): Scrubs roster 6's `decisions.team`; all ten
    rosters' weeks add up to the league's to the cent; a team with no record says why; the event flag reaches the
    answer; dad's league from the fixtures (record rows built in memory by `record_mfl.mfl_record_rows` through the
    API's read-only role — nothing written; plan weeks 1–4 reconstruct, 5 write; graded weeks 1–3, 12 teams each,
    submitted = the fixtures' franchise scores); Knight Train's weeks; an MFL league without rows says so.
    `api/tests/test_v1.py` 6 passed.
  * `web/e2e/v2` **10 passed** (5 tests × phone 375 / desktop 1300; no sideways scroll): the Team block from the
    recording, the Sleeper column with planted numbers (the clone has no snapshot), no block for a team without
    calls, About → Team link, dad's league on About. The whole fixtures e2e: **232 passed** (14 min). Lint + typecheck 0 / 0, build ok.
  * **Whole suites** on the clone (Sunday ~12:30–13:00 ET, the box shared with four suites): root **1090 passed, 1
    failed, 5 skipped** (run twice, before and after the module move) — the failure (`test_my_week.py::test_my_week_is_the_mart[Scrubs-2]`) fails identically with
    main's checkout (`ad4040e`) on the same clone; API **508 passed, 18 failed, 34 skipped** — 3 are the brief's known
    scoring-check ones (`test_ic1` ×2, `test_ic_po`), and the other 15 (`test_decisions` ×6, `test_h1`, `test_i0a`,
    `test_ib0` ×3, `test_ib2` ×2, `test_ic4`, `test_ie1`) fail identically with main's checkout on the same clone at
    the same hour (re-run: 18 failed) — the clone's state on a Sunday afternoon (e.g. "max() iterable argument is
    empty", a change before the first lock that Sunday's clock no longer allows), not this branch. (The API suite ran
    before the module move; after it `tests/test_v1.py` + `tests/test_v2.py` re-ran: 13 passed.)
  * **The numbers** (the clone, weeks rebuilt; no number moved for Scrubs or the dynasty: Scrubs −23.54 / 313.70 /
    coin flips 59% as V-1):
    * **Scrubs roster 6 (GoodGameBuddy)**, weeks 1–2: started **265.0** (151.8 + 113.2), ours **253.9** (151.7 +
      102.2), best **281.7** (160.6 + 121.1): our lineups −11.1, 16.7 left on the bench; the closest calls landed 3 of
      6 (3.3 expected; Brier 0.262); coin flips 2 of 4 (2.06 expected). Sleeper's lineup: none (no snapshot on the clone).
    * **Dad's league (MFL 70587)**, the fixtures' weeks 1–3, all rebuilt:

      | Week | Teams | Started | Ours | Best | Added |
      |---|---|---|---|---|---|
      | 1 | 12 | 1471 | 1422 | 1711 | −49 |
      | 2 | 12 | 1325 | 1315 | 1557 | −10 |
      | 3 | 12 | 1401 | 1322 | 1612 | −79 |
      | season | 36 | 4197 | 4059 | 4880 | −138 (−3.8 a team a week) |

      The best lineups beat the ones started by 683 (19.0 a team a week); coin flips 57% (52% expected, 27 calls); 100
      calls with odds, Brier 0.225. Knight Train (team 1): started 224, ours 223, best 331. Big Mac Attack (team 8):
      336, 328, 396; calls 6 of 9 (4.2 expected).
* **What moved**: no projection, lineup, total or V-1 grade. New: `ops.decision_market`; `mart_decision_record`'s four
  columns at the end (`news_source`, `market_points`, `market_edge`, `n_market_unknown`); both marts leave `mfl:` rows out;
  `/api/record` gains `decisions.team`, `market`, `news_source`, and `decisions` for MFL leagues; `validation.validate`
  is `record_run.validate`.
* **Not done / limits**:
  * Nothing graded on real events yet: the clone has no `events` schema and no scored `kickoff` week. On the hosted
    copy the store started 2026-10-04 09:46 UTC, so week 5 (Thursday's build) is covered: its news cases will come
    from the store once week 5 is scored.
  * Sleeper's lineup has no number anywhere locally (no `raw.sleeper_projections` rows on the clone or the main
    database); the nightly has the archived snapshots, so it starts with the first week that has one before its kickoff.
  * MFL's record starts its `kickoff` weeks only once the nightly has `LEAGUE_LAB_RECORD_MFL` (For the PO 2). Until then
    `/api/record` for dad's league says "we have not kept a lineup record for this league yet".
  * The MFL grade calls MFL on each `/api/record` (one `weeklyResults` per scored week, the client's cache and token
    bucket apply); the Team block for an MFL league is answered by the API but not covered by an e2e (no `/api/team`
    recording for 70587).
  * The close-call odds of an MFL record leave the opponent out of the pair's correlation (teammates still count).
  * No My Week line ("our lineups would have added X for you") yet; dad's other fixture league (21861) not proposed.
* **Next**: after week 5 is scored, read `/api/record` on the hosted copy: `news.source` should say `events` and
  `weeks[].market` should have Sleeper's lineup; then the My Week line per team once a few `kickoff` weeks exist.
* **For the PO**:
  1. **dbt**: `uv run league-lab dbt build --select source:ops_decisions mart_decision_record mart_decision_calls` (the
     new source `ops_decisions.decision_market`, four new columns, the test `decision_record_market_edge_adds_up`; the
     pre-hook creates `ops.decision_market`). `league-lab db migrate` also creates it (`lineup.DDL`). Then `league-lab
     validate` (writes it; on the main database: 0 rows until Sleeper snapshots exist).
  2. **The nightly (proposal; `nightly.yml` is yours)**: add `LEAGUE_LAB_RECORD_MFL: "mfl:70587"` to the nightly job's
     env (or the step that runs `scripts/nightly.sh`). Nothing else: `nightly.sh`'s soft `validate` step (after
     `project`, before `save-record`) already runs `league-lab validate`, which now also writes the MFL record and
     Sleeper's lineup (~5 s per MFL league, MFL and Sleeper's player directory fetched once; a failure is logged and
     skipped, never fatal), and the soft `decision-marts` dbt step after `drift` builds the new columns.
     `ops.lineup_record` is already record state (STATE / RECORD tables), so the MFL rows travel; `ops.decision_market`
     is recomputed every night (not record state, nothing to add). Without the env, dad's league simply has no record.
  3. **`metric_registry.csv`** (seed, yours): `decision_market_edge, dr1.1, Sleeper's projections as a lineup − submitted
     points, —, league-roster-week, available, "ops.decision_market: the record's roster at Sleeper's last pre-kickoff
     snapshot; a DEF keeps ours"`; and note on `decision_edge` "dr1.1: MFL leagues graded on request from MFL's results".
  4. **Hosted copy**: `scripts/hosted_relations.py` — the API and the console gain exactly `ops.decision_market` (ops goes
     whole anyway). The API reads `events.events`, `ops.lineup_record`, `analytics.dim_game`,
     `analytics.mart_player_week_features` — all already published / granted.
  5. **Merge order**: any. Touch points: `ondemand.py` (the V-1 block's `record_decisions` / `_with_decisions` gained
     `team`; the V-2 block sits right above `@_with_decisions` — IH-3's block is in `my_week`, far away), `main.py` (one
     line: the record route; IH-1's blocks are `/api/health` / `/api/status`), `lib/api.ts` (my block right after
     V-1's, not at the end), `Team.svelte` (two import lines after the TeamBadge import + a block at the end of the left
     column — IH-2's MFL freshness block may sit nearby: keep both), `About.svelte` (the props line destructures `team`;
     lines inside the V-1 block), WORDS / METRICS / CHANGELOG / STATUS as usual (I opened the `## Wave I-H` heading).
  6. **Decisions Andrew may want to reverse**: (a) a status move counts when it differs from what the build saw —
     a return to ACTIVE too; (b) the store answers only for weeks it ran across, else the report rule; (c) Sleeper's
     DEF line is not priced, so a DEF keeps our pick in Sleeper's lineup; (d) MFL's optimum is MFL's own `opt_pts`
     (its lineup rules), not our solver; (e) an MFL starter on no franchise that week is unknown (the roster-week
     leaves the sums), a listed player with no score is 0 (MFL's count); (f) the Team block shows only with a graded
     week; (g) each call names our odds, also when under 50% (a starter picked on value whose odds were under half).
  7. **Clone state** (`league_lab_i0a`): `ops.decision_market` created (empty); the two marts rebuilt with the new
     columns; `ops.lineup_record` week 5 rewritten by `validate` (451 rows, as V-1); the `mfl:70587` rows written from
     the MFL fixtures for the evidence were deleted at the end (re-create: the `validate --mfl` command above with the
     two fixture variables).

### IH-1 2026-10-04 — the product says when it is stale; the operator hears when the nightly fails (branch `dev/IH1`, clone `league_lab_ia3`)

* **Task**: IH-1 of the Wave I-H brief (`scratchpad/waveIH/BRIEF.md`): the stale state (API, My Week, the footer, the
  console), the web app's error states, the nightly's failure → someone knows, the trigger's last dispatch, events
  retention. Plan sections: HOSTING § 5 (appended "When the nightly is late or fails"), HOSTING § Events (appended
  "Retention (events)"), WORDS (new table "The stale state and the error states"). Branch `dev/IH1` from `ad4040e`.
* **Interfaces** (INTERFACES.md § IH-1): `league_lab/freshness.py` — `STALE_AFTER_HOURS = 30`, `STALE_WORDS`,
  `nightly_state(as_of, now=None, *, console=False, live_injuries=True) → {as_of, age_hours, stale, limit_hours,
  words}` (`stale` null when `as_of` is unknown). `/api/health` + `stale`, `age_hours`. `/api/status` + **`nightly`**
  (the brief's "freshness block": `/api/status.freshness` is already the footer's caption string, so the block got
  its own key; nothing else on `/api/status` or `/api/my-week` changes shape). Web: `Status.nightly?: Nightly`,
  `forget(path)` (`lib/api.ts` block), `failureOf` / `Failure` / `SLOW_MS` / `Remote.failure` / `Remote.retry()`
  (`lib/remote.svelte.ts`), `components/ErrorCard.svelte` (`failure`, `onretry`, `compact`), `Login notice=`.
* **What it does**
  1. **Stale**: `as_of` = the newest `ops.projections.fitted_at` (what `/api/health` has always reported: the morning
     update refits and publishes it); stale when older than 30 hours (a normal night lands ~08:00 ET → a missed
     morning shows ~14:00 ET, after the trigger's 09:37 / 11:37 re-checks). `/api/health`'s age is computed at the
     answer (the hourly `as_of` cache never hides a missed morning); `/api/status` reads `as_of` on the pool each call
     and hands it to the health state. Words by New York's calendar: "Yesterday's numbers: the morning update did
     not run. Injury statuses are still live." (the brief's, exactly, in production) — two or more missed mornings
     "Numbers from Friday, Oct 2: the morning update has not run since. …"; the tail claims live injuries only when
     the availability overlay is on (off → "Injury statuses are from that update too."; the console → "This
     console's injury tags are from that update too.": it has no live overlay). **My Week**: one line above the
     actions (`stale-banner`, `role=status`, warn tokens); the footer: "Updated 1 d ago · the morning update did not
     run ›", the sentence on tap. The app reads `/api/status` again on coming back on screen after 10 minutes and
     every 15 minutes on screen (a tab left open overnight). **Console** Data Status page: the same line as a warning.
  2. **Error states** (`failureOf`): no answer at all, or the host's own 502 / 503 / 504 page → **down** ("Cannot reach
     isuckatfantasy right now. Check your connection, then try again." / "… is not answering right now (error 502).
     It is usually back within a few minutes."); a 500 → **server** (titled "Something broke on our side", names the
     status page `/api/status`); our own 502 / 503 keep their words (MFL named for an MFL league; "busy" said as
     busy); **slow**: an empty screen still loading after 25 s says "Still waiting" (the request keeps going; its
     answer still shows). Every card has **Try again**, which really asks again (`forget` drops the cached / in-flight
     request). On My Week, the first screen (App's boot error), Trends, Receivers, Players and Compare; every other
     screen gets the same words through `errorWords` (and `lib/decisions.ts errorWords`, its 404 words kept). A 401
     after this browser was signed in (the app was on screen, or a league is remembered) → the password screen with
     **"Signed out — sign in again."**; signing in returns to the same screen; a first visit sees no such line. The
     API's own 500 is now the contract's plain words naming `/api/status` (an `Exception` handler; never the
     exception's text).
  3. **The nightly fails → someone knows** (HOSTING § 5 "When the nightly is late or fails"): (a) the product's own
     line and `/api/health` `stale` (a free keyword monitor on `"stale":false` is the one alarm that also catches a
     night that never started); (b) GitHub's failure email goes to the run's actor — for the trigger's
     `workflow_dispatch` runs the token's owner, **Andrew**, from `notifications@github.com`, "Run failed: nightly -
     main (<sha>)" (Settings → Notifications → Actions, email ticked: the default); (c) **`scripts/nightly_failure_summary.sh`**
     for a `notify` step the PO wires (`if: failure()`): the failing stage (an aborted night's step / the first failed
     step / "before scripts/nightly.sh"), whether this night published (its own `step sync-hosted: ok`, never an older
     sync.log), the next move, the last 40 lines of `logs/nightly.log` with password-like strings blanked, one
     `::error` annotation; always exits 0.
  4. **The trigger's page** reports the last dispatch (ok / the HTTP error, when, why) through an **optional** Workers
     KV binding `STATE` (free; ≤ 3 writes a day); without it, as before, and the page says "not recorded". A failed
     dispatch is recorded then re-thrown (Cloudflare's log marks it); no token at a trigger hour is recorded too.
  5. **Events retention** (`scripts/hosted_events.sql`, block IH-1, every sync): superseded `news` / `brief` rows
     ingested > 120 days ago; `availability` rows ingested > 400 days ago (live or superseded). A player's live news
     item is kept however old (one per player). Readers only test `superseded_by is null`, so a dangling pointer to a
     pruned row is harmless.
* **Commands**: `cd api && PYTHONPATH=. uv run pytest -q tests/test_ih1.py tests/test_h0.py` · `uv run pytest -q tests/test_ih1.py` · `node ops/nightly-trigger/test.mjs` · `cd web && npm run lint && npm run build && FIXTURES_PORT=8613 npx playwright test --config playwright.fixtures.config.ts e2e/ih1` (and the whole fixtures suite) · `psql <pipeline dsn of league_lab_ia3> -f scripts/hosted_events.sql` (twice, rows planted) · Streamlit `AppTest` on `app/pages/12_Data_Status.py` · the whole API and root suites (and their failures re-run on a clean export of `ad4040e`). No dbt, no migration, no write to `league_lab`.
* **Evidence**
  - `api/tests/test_ih1.py` **15 passed** (the rule: 30.0 h not stale, 30.1 h stale, unknown → null; the words —
    yesterday, a named day, the console's, the overlay-off tail; `/api/health` stale at 40 h, not at 29.5 h, null
    for unknown, the age growing under the cache; `/api/status.nightly` on the clone with `as_of` 40 h before a fixed
    clock = `{as_of, age_hours: 40.0, stale: true, limit_hours: 30, words}`; the clone read as it is; a failed read
    falls back; the 500 shape; **retention**: nine rows planted on `league_lab_ia3`, the file applied twice — pruned
    once, the kept set exact). `api/tests/test_h0.py` 3 passed (its pinned body gained the two keys).
  - By hand on the clone: rows planted, `hosted_events.sql` applied twice → `DELETE 2` / `DELETE 2`, then `DELETE 0` /
    `DELETE 0`; the kept four were the ones the rule keeps.
  - `tests/test_ih1.py` **4 passed** (the summary script on four logs). `node ops/nightly-trigger/test.mjs`: **7 checks
    passed** (no binding; a 204 recorded; a 401 recorded, shown FAILED, re-thrown; a re-check with a success dispatches
    nothing; a re-check after a failure dispatches; no token; a broken binding).
  - `web/e2e/ih1/` **21 passed, 1 skipped** (phone at 375 and desktop at 1300: the banner above the actions and the
    footer's words; nothing when fresh; the status read again after 15 minutes on screen; the API down at the first
    screen and on My Week with Try again; a 500 naming `/api/status`; the host's own 502 = down; our 502 keeps
    "Sleeper did not answer"; Trends' card; signed out mid-session and in an open tab; still waiting after 25 s —
    desktop only, 27 s). Screenshots: `web/e2e/.out/ih1-*.png`. The whole fixtures suite: **241 passed, 1 skipped**
    (before the last IH-1 test was added; `e2e/if4` and `e2e/ig3` re-run after the last footer change: 8 + 2 passed).
  - The console: Streamlit's `AppTest` on `12_Data_Status.py` against the clone — no exception; the warning "Numbers
    from Friday, Oct 2: the morning update has not run since. This console's injury tags are from that update too.
    (The projections were last refit 59 hours ago; this note shows after 30 hours.)" (the clone is a Sep 26 snapshot
    refit Oct 2).
  - **Whole suites**: API **531 passed, 19 failed, 18 skipped** — the 19 fail identically on `main` `ad4040e` against
    the same clone (re-run from a clean export of `ad4040e`: 19 failed): the clone's 2026-09-26 snapshot (the scoring
    check, the overlay / on-demand parity tests, `test_u1::test_the_summary`), none touches this task's code. Root:
    **1080 passed, 2 failed, 6 skipped** (47 min on a shared 2-CPU box) — the 2 (`test_my_week.py::test_my_week_is_the_mart`, both leagues) fail identically on `ad4040e` against the same clone. `ruff check src app tests api` clean; `npm run lint` (eslint + svelte-check 0 / 0) and `npm run
    build` clean.
* **What moved**: no number (rule 2). Words: a 500 / the API down / Render's 502 page no longer read "Sleeper did not
  answer" or "Failed to fetch"; an MFL league's 502 names MyFantasyLeague; our 503 "busy" says busy (was "not ready").
  `/api/health`'s body gained two keys (`test_h0` updated).
* **Decisions** (written down, reversible): `nightly` not `freshness` (the key exists); the stale clock is the
  projections' fit (`/api/health`'s `as_of`), not `mart_data_status` (a night whose `project` failed but synced also
  shows stale — "the morning update did not run" is then a little strong, but the numbers are yesterday's); `>` 30 h;
  the banner on My Week only (not the TopBar on every screen: the screen opened daily; one line, not noise
  everywhere); slow at 25 s (an MFL league's first on-demand load can take 10–20 s); "signed in before" = the app was
  on screen or a league is remembered on this browser; retention by `ingested_at`, live news kept, availability
  pruned live or superseded at 400 days.
* **Not done**: the card on Waivers / Trades / Team / League / the trade calculator / Matchups / About / Rest of season /
  the player page and pane (they show the improved words in their own line; the swap is one line each, as in
  Trends); the TopBar banner on other screens; the off-season edge (`project` may refit nothing in the off-season, so
  the line would show — an exemption for "no game this week" before the off-season); a monitor on `/api/health`
  (needs an account: Andrew's choice); `app/whats_new.md` (PO only).
* **Next**: the PO wires the notify step; Andrew checks his GitHub notification setting; optionally the KV binding and
  a keyword monitor.

**For the PO**
1. **Wire the `notify` step** in `.github/workflows/nightly.yml`, last in the `nightly` job (after "Upload dbt run
   results"; no permission, no secret):
   ```yaml
         # Wave I-H (IH-1): a failed night's summary - the failing stage, published or not, the last 40 log lines
         # (GitHub's failure email to the run's actor links here; docs/HOSTING.md § 5 "When the nightly is late or fails")
         - name: Notify (the failing stage and the last 40 log lines)
           if: ${{ failure() }}
           run: ./scripts/nightly_failure_summary.sh logs
   ```
2. **Andrew**: GitHub → Settings → Notifications → **Actions**: email ticked ("Only notify for failed workflows" keeps
   successes out). That email is the alarm for a run that started and failed; a run that never starts (the trigger's
   token expired) sends nothing — the product's line at 30 h, the trigger's page and (optional) a keyword monitor on
   `https://isuckatfantasy.io/api/health` for `"stale":false` cover that.
3. **The Worker** (optional, Andrew's dashboard steps as before): paste the new `ops/nightly-trigger/src/index.js`
   (works unchanged without a binding); for the last dispatch on its page, KV → Create namespace
   `isuckatfantasy-nightly-state` → the Worker → Settings → Bindings → KV namespace `STATE` (README).
4. **Merge notes**: `main.py` — three IH-1 blocks (an `Exception` handler before `require_auth`, the health body's two
   keys + `_status_nightly` right after the health block, one line in `status()`); `myweek.py` is untouched (the
   status block lives in `main.py`). `MyWeek.svelte` — the banner sits just before `{#if data.week !== null}`, the
   footer edits are inside IF-4's footer; IH-2 / IH-3 add their own blocks there (keep all). `lib/api.ts` — an
   end-of-file block (keep every wave's). `WORDS.md` — a new table before "## Adding to it" (keep the others').
   `CHANGELOG.md` — I created `## 2026-10-04 — Wave I-H`; `STATUS.md` — I created `## Wave I-H (Iteration 18)`
   (merge the others' sections under one heading). `api/tests/test_h0.py` — the pinned health body gained `stale` /
   `age_hours`.
5. **Rollout**: nothing to set on Render; `hosted_events.sql`'s deletes run with the next sync (they delete nothing
   until rows are 120 / 400 days old). After the push: `/api/health` → `"stale": false` (with `age_hours` under 30
   after a good morning); `/api/status` → `nightly`.
6. **Docs for the PO's pen**: `app/whats_new.md` — proposed: "**The app says when the numbers are a day old.** If the
   morning update did not run, My Week says so in one line (injury statuses still update live), and a screen that
   cannot reach the server says so with a Try again button instead of loading forever." `docs/DESIGN.md` — add
   `ErrorCard` to the components list (`<ErrorCard failure={r.failure} onretry={() => r.retry()} />`: a screen's
   error state; `Remote.failure` / `retry()`).
7. **Andrew may reverse**: 30 hours; the words; 120 / 400 days; the banner on My Week only.

### IH-2 2026-10-04 — the small opens from I-G: units' drop cost, the console's stash words, MFL freshness on Team, the waiver days, the Questionable line, `game_key` (branch `dev/IH2`, database `league_lab_i0b`)

* **Task / plan**: Wave I-H brief § IH-2 (items 1–5); the I-G hand-backs' "Not done": IG-1 (the drop cost on units, the
  verdict's lean), IG-3 (the console's stash words, the Team page's freshness, `daily_waivers_days`), IG-2 (`game_key`,
  the Questionable designation). Plan § 17 (Iteration 18). Branch `dev/IH2` from `main` `ad4040e`.
* **Delivered**
  1. **Waivers' drop cost on team units** (`decisions._moves_on_demand`, `# ---- IH-2` in IF-1's block): `points.update`
     + `repl.update` from IG-1's `unit_market(lw, fa)` — a dropped MFL team unit (TMQB / TMPK) has season points and a
     replacement (the best **free unit of its kind**), and its later starts are measured against that unit (before:
     against a free unit worth 0, so a unit's drop always cost its whole future). **The verdict's lean**
     (`trades.verdict`, `# ---- IH-2`): a side with a player the season value cannot count says "season value not
     compared (1 player in it has no season projection)" and leans nowhere (it leaned on the counted players' partial
     sum; units are counted since IG-1).
  2. **The console's stash words read `stash_action`** (`app/lib/signals.py`, `# ---- IH-2`): `upside_detail` names no
     drop on a watch (the API hides it too — and the API's `lines` come from this same function, so the web's watch
     cards lose the "Drop X: …" line they still carried under IG-3's watch box); the Waiver Wire card's caption says
     "Upside stash · watch, no claim yet: …" / "· claim: …" and an `st.info` line says the call — the watch line is
     **one source**: `signals.watch_words`, which `decisions.ig3_watch_words` now calls; the expander's drop column is
     empty on a watch. A row written before IG-3's call keeps the older words.
  3. **MFL's roster freshness on Team** (`decisions.team_roster_freshness` → `ondemand.mfl_roster_freshness`, My Week's
     fields): `/api/team` for an `mfl:` league gains `roster_updated_at` / `roster_source`; `Team.svelte` (`<!-- ---- IH-2
     -->`) shows "MFL rosters updated 12:16 PM ET ›" right under the roster, the exact day and time on tap.
     **`daily_waivers_days` decoded** (`decisions.waiver_days`, `daily_days_words`, `deadline_days`; `_sleeper_runs`'
     daily path skips the days off): "Claims run every day except Saturday at 5:00 AM ET (FAAB blind bids)" for the
     dynasty; `deadline` gains `days` / `days_mask`.
  4. **"What changed": a Questionable tag** (`myweek.questionable_lines`, `# ---- IH-2`, one call line in
     `what_changed`): a week's player (the best lineup's starters + the submitted ones) tagged Questionable gets one
     line — "Questionable: Flowers (hamstring) — your lineup is unchanged" — when the tag is news since the morning
     build: a live QUESTIONABLE availability event of the last 24 hours (cited by it: source, time, URL, `event_id`),
     else the overlay's own flag (a copy newer than the build moved him; cited by the overlay entry). A tag the build
     knew is not a change; never a second line for a player who has one. No web change (a status line renders).
  5. **`game_key` on availability events** (`events.week_games` / `game_key_for`, `# ---- IH-2`): the player's team's
     nflverse `game_id` in the week in play — the week of the first kickoff no more than 12 hours ago (a Monday-night
     status is still that week's; Tuesday's is the next week's); a bye, an unknown team or an unreadable schedule:
     null. Read on the writer thread, cached an hour (a failed read: not retried for 5 minutes). The fingerprint is
     unchanged (no duplicate rows from the new column).
  6. **Found on the way**: dad's league team 12's Waivers said "Fills your empty team QB in week 5, when QB and QB are
     on a bye." (`_name_list` → `_last` reads "Houston Texans QB" as "QB"); team units are named by their team there now
     ("Texans QB", IC-4's `unit_short`; `_unit_name`, a marked line).
* **Interfaces**: INTERFACES.md § IH-2 (11:58), as built: no new keys on the moves (the numbers move); `deadline.days`,
  `deadline.days_mask`; `/api/team` `roster_updated_at`, `roster_source` (MFL only); `changed.lines[]` `flag:
  "questionable"` (+ `player_name`); `events.events.game_key`; `signals.with_call / stash_call / stash_call_words /
  watch_words / short_name / STASH_CAPTION / UPSIDE_CALL_SQL`; `lib/api.ts` one `// ---- IH-2` block.
* **Files**: `api/league_lab_api/{decisions,myweek,events}.py`, `src/league_lab/trades.py`, `app/lib/signals.py`,
  `web/src/routes/Team.svelte`, `web/src/lib/api.ts`, `api/tests/test_ih2.py` (new, 22 with the recorder), `api/tests/twin_ih2.py` (new:
  the console twin of the stash card, `streamlit_twin.py`'s pattern), `api/tests/test_ig3.py` (one re-pin, marked),
  `web/e2e/ih2/fixtures.spec.ts` (new, 4 × phone / desktop), `web/fixtures/ih2/api_ih2.json` (the recording),
  `docs/{WORDS,STATUS}.md`, `CHANGELOG.md`.
* **Evidence — MFL 70587 (dad's league), Waivers before → after** (fixtures; `_moves_on_demand` and `/api/waivers`, the
  code before = `ad4040e`):
  - **Team 8 "Big Mac Attack"**: the answer **does not move** — the team has an open roster spot, so every best claim is
    "no drop needed" (41 moves, all `drop: null`; the first stays the Atlanta Falcons defense, +1.2 this week, +12.81
    over weeks 4–7); only `move_rank` (each move's place in the full table) changes, on 24 of the 41. The table behind
    it moves on its **35 unit-drop rows** (of 288): dropping the **Chicago Bears QB** (29 claims) cost **28.22 → about
    4** (season points 345.93 against the best free team QB's 378.22 = 0 above replacement; his later starts 28.22 →
    0.20), e.g. "Falcons defense, drop the Bears QB": drop cost 28.22 → 4.09, net horizon gain **−15.41 → +8.72**, and
    **24 of the 29 claims become worthwhile** with that drop (still below the same claim with no drop: +12.81);
    **Houston Texans K** 118.55 → about 5 (2.14 for the Saints kicker claim; 166.01 season points against the best free
    kicker's 169.47); **Houston Texans QB** 29.15 → about 9.
  - **Where the screen moves** (12 teams, every move compared): teams 1, 3, 5, 7, 8, 11 unchanged; on **2, 4, 6, 9, 10,
    12** a kicker (or team QB) claim's drop changes from a player to the unit it replaces, the gains unchanged (cost 0
    either way): team 2 "New Orleans Saints K" drop Cooper Kupp → **Jacksonville Jaguars K** (+2.55 / +17.06; also the
    third of its three top moves), team 4 Jonathon Brooks → Detroit Lions K, team 6 Jakobi Meyers → Los Angeles Rams K
    (and "Arizona Cardinals QB": → Philadelphia Eagles QB), team 9 Kenny Gainwell → Green Bay Packers K, team 10 Quentin
    Johnston → Seattle Seahawks K / Denver Broncos QB, team 12 RJ Harvey → Baltimore Ravens K. Why: both drops now cost
    0, and IF-1's tie-break prefers the starter the claim pushes out (`choose_drops`: `drop_is_incumbent`) — before,
    the unit's drop carried its whole future (no replacement) and a bench player won. House leagues: no units, nothing
    moves.
* **Evidence — the rest**: dynasty deadline "Claims run every day except Saturday at 5:00 AM ET (FAAB blind bids); …"
  (Sunday 3:50 AM ET → the next run Sunday 5 AM; Friday 11 PM ET → Sunday, Saturday skipped); Scrubs (weekly) unchanged.
  Dad's league Team 8: `roster_source` "MFL", read just now; Scrubs roster 6: no MFL keys. Scrubs roster 3 with the
  ESPN fixtures' overlay: "Questionable: Flowers (hamstring) — your lineup is unchanged · Injury report (ESPN)" (once;
  McLaurin, also flagged, is on the bench: no line); with the overlay on, Scrubs rosters 3, 4, 5, 8, 9 and dynasty 2, 3,
  6 get one (Andrew's Scrubs 2 / dynasty 12: none). `game_key` on the clone's schedule: Saturday of week 4 →
  `2026_04_MIA_MIN` for MIN; Tuesday after → week 5 (byes absent); Thursday night → `2026_04_PIT_CLE`. The console twin
  (Scrubs roster 6, the clone: every stash a watch) and the API's first stash: the same lines, no drop named, the same
  watch line word for word.
* **Tests**: `api/tests/test_ih2.py` **21 passed, 1 skipped** (the recorder); with `test_ig3 test_ig1 test_if1 test_ig2
  test_if4 test_h1`: 72 passed, 12 skipped, 1 failed — `test_h1::test_waivers_trade_lists_on_demand_equal_the_house_path`,
  which fails identically on `ad4040e`'s code against this clone (below). Whole suites: see "Full runs" below. Ruff
  `src app tests api` clean; web `npm run lint` (eslint + svelte-check + tsc) 0 errors, `npm run build` clean; e2e
  `FIXTURES_PORT=8614 … e2e/ih2` **8 passed** (phone 375 / desktop 1300: the Team MFL line under the roster and its
  exact time on tap, no line on a Sleeper Team page, the dynasty's waiver days, the Questionable line once; no sideways
  scroll).
* **Full runs** (the box shared with four other developers' suites: 2 CPUs, load 12–14).
  - **API** (`cd api && PYTHONPATH=. uv run pytest -q tests/`, 50 min): **516 passed, 20 failed, 38 skipped**. Every
    failure reproduces on `ad4040e`'s own code against this clone today (a scratch worktree of `main`, the same `.env`)
    or passes on a re-run — none is this branch's: the three known scoring checks (`test_ic1` × 2, `test_ic_po`: no
    `*_tds_10p` columns on the 09-26 clones), and **fifteen that read the wall clock** — it is Sunday of week 4 and
    its games are being played (the London game kicked off 9:30 AM ET, the rest at 1 PM): the on-demand path locks
    started players while the clone's marts (built 09-26) do not, and the ESPN fixture's Jefferson is now locked —
    `test_decisions` × 6 (house vs on-demand: Team's `bench_value` 33.16 vs 42.35, the partners, the trade evaluation),
    `test_h1` trade lists, `test_i0a` Jefferson out, `test_ib0` × 3, `test_ib2` × 2, `test_ic4` RB2 claim, `test_ie1`
    "a change before the first lock"; plus `test_parity` player card ×2 (00-0038797 fails on `main` too; 00-0036963
    passed on re-run on both).
  - **Root** (`uv run pytest -q tests/`, 69 min): **1076 passed, 2 failed, 6 skipped** — the two are
    `test_my_week::test_my_week_is_the_mart` (dynasty 12, Scrubs 2), failing identically on `ad4040e` today (the same
    clock). The root tests of the modules touched (`test_signals test_trades test_waivers test_waivers_if1
    test_waivers_ig3 test_app_guards test_trade_finder_page`): 160 passed.
  - **e2e** (fixtures, `FIXTURES_PORT=8614`, the whole suite): **230 passed** (10.6 min; 222 on I-G's merge + `ih2`'s 8).
  - The last commit's `_name_list` change ran after the full API run: `test_ib2 test_ie0 test_ih2` again — the bye
    words pass; `test_ie0::test_review_package_is_a_two_for_one_end_to_end` is red on `main` too since the 1 PM ET
    kickoffs ("Houston Texans QB (locked)"): the clock-dependent list grows through the afternoon.
* **What moved and why** (the brief's allowed move: MFL Waivers numbers when units get a drop cost): the drop cost,
  season value, future starts, net gains and worthwhile flag of every move that drops an MFL team unit (lists above);
  the best drop of a unit-position claim on 6 of dad's league's 12 teams; `move_rank` order. Words: the dynasty's
  deadline ("every day except Saturday"); the web's watch-stash lines lose "Drop X: …" (the API's `lines` come from
  the console's `upside_detail`); a trade verdict with an uncounted player; MFL bye words ("Texans QB", was "QB").
  No projection, lineup, house-league waiver number or trade gain moved.
* **Decisions** (nobody to ask): (1) **`daily_waivers_days` = two bits a day, the low bit = claims run that day,
  Monday first** — Sleeper's default 5461 sets the low bit of all seven pairs; the raw values of Andrew's two leagues
  2021–2026 (`raw.sleeper_league`: 5461, 729, 6484, 15356, 15359) read consistently that way (the dynasty's 2022–2024
  values 15356 and 6484 differ only in the high bits and give the same days: Monday and Saturday off; 2025–2026's 15359:
  Saturday off), while reading the high bit would make 2023 a one-day-a-week league. The high bit is not read. The day
  order follows IG-3's `waiver_day_of_week` reading (0 = Monday). **Andrew can check in one look**: if his dynasty's
  waiver settings do not skip Saturday, the order is one constant (`WAIVER_DAYS_FIRST`). (2) The Questionable line
  only when the tag is news since the morning build (a live event of the last 24 hours, or a copy newer than the
  build) — a tag the build knew stays a chip, not a "change"; one line per player, never a second one. (3) The week
  in play for `game_key` = the week of the first kickoff no more than 12 hours ago. (4) A watch stash names no drop in
  its detail lines on both surfaces (the drop stays in the table for the legality tests, as IG-3 decided). (5) The
  verdict says "season value not compared" rather than leaning on a partial sum. (6) Team units in bye words by team
  ("Texans QB") — found on the way (dad's league team 12: "when QB and QB are on a bye").
* **Not done**: the Waivers screen shows a unit's drop cost only through the existing drop words (no new UI —
  `Waivers.svelte` unchanged: the deadline line already reads `words`); MFL waiver times (the export has none);
  `game_key` for news / brief rows (only availability: a headline is not tied to a game); a depth-chart writer; the
  console's Trade Finder page's `0.00` (PO-only file, IG-1's note); the fifteen clock-dependent tests (below).
* **Next**: pin a clock in the API tests that read "now" against a fixed week (they fail every Sunday afternoon until
  the clones are rebuilt); then V-2's news flag on `game_key` if it wants the game.

**For the PO**
1. **Merge** (all marked `IH-2`): `decisions.py` — two lines in IF-1's block of `_moves_on_demand`, three lines in
   `_sleeper_runs`' daily path, one in `waiver_deadline`'s return, one in `team()`, `ig3_watch_words`' body (now
   `SG.watch_words`), `_name_list`'s first line, and one block after IG-3's end (`waiver_days`, `daily_days_words`,
   `deadline_days`, `team_roster_freshness`, `_unit_name`); `myweek.py` — one call line in `what_changed` + a block after
   IG-2's (IH-3 adds `win` in another block of the same file); `events.py` — two `make(...)` arguments, a block before
   "news and briefs", one docstring line; `trades.py` — one block in `verdict`; `app/lib/signals.py` — one line in
   `upside_detail`, four in `upside_cards`, a block at the end; `Team.svelte` — two imports, a function, a block under
   the roster card (V-2 adds "Your calls this season" to the same file: keep both); `lib/api.ts` — a block at the end
   (keep every wave's block). `api/tests/test_ig3.py`: one re-pin (the dynasty's words), marked.
2. **Nothing to apply**: no dbt, workflow, `render.yaml` or hosted-SQL change. `events.events.game_key` exists since
   IG-2 (its check accepts nflverse ids); the writer fills it from the next server start. HOSTING § "Events" still says
   `game_key` is empty — one line for whoever edits HOSTING next (IH-1 owns § 5).
3. **Decision Andrew may want to check**: the dynasty's waiver days ("every day except Saturday at 5:00 AM ET") —
   decoded from Sleeper's undocumented mask (above); if his Sleeper settings say another day, flip
   `WAIVER_DAYS_FIRST`. And dad's league: a kicker claim now drops the kicker it replaces (teams 2, 4, 6, 9, 10, 12).
4. **Re-recordings**: the web's watch-stash cards lose their "Drop X: …" line on the next recording (`web/e2e/h1`
   compares the first line only: unaffected); `web/fixtures/ih2/api_ih2.json` was recorded from the fixtures + the
   clone `league_lab_i0b` with the ESPN fixtures' overlay (the header has the command).
5. **The suites on a Sunday**: fifteen API tests (and root `test_my_week::test_my_week_is_the_mart` × 2) fail on
   `main` itself this afternoon — they compare the on-demand path, which locks the players whose games have started,
   with marts built on 09-26. Not a regression; worth a pinned clock before the next wave's full runs.

### IH-3 2026-10-04 — the week's win probability: the game objective, as information (branch `dev/IH3`, database `league_lab` read only)

* **Task**: IH-3 (brief § "IH-3"; the decision-quality review § "The analytics worth building next" item 5: "compare
  expected points with matchup win probability … Do not turn 'underdog' into an automatic instruction to chase the
  player with the highest individual ceiling"). Plan sections: § 17 (Iteration 18); METRICS § "Ranges and decisions"
  (new subsection "Win probability — the week"); WORDS § "The week's win probability".
* **1. `decisions.lineup_win_probability(mine, theirs)`** (`src/league_lab/decisions.py`, block `# ---- IH-3` at the
  end; nothing above it changed). Each starter: D6's `Predictive` through his P10 … P90 (three knots without the 50%
  range; a K / DEF row with P10 / P90 only takes its projection as the median), **centred on his projection** (the
  shape kept, floored at 0 — so the number agrees with the expected totals printed beside it); one Gaussian copula over
  **both** lineups with `pair_rho` for every same-game pair on either side (my WR and their QB move together); pairs in
  different games independent; K / DEF / team units independent of everyone (not measured); an inconsistent matrix
  repaired (eigenvalues floored, unit diagonal). 20,000 joint draws, fixed seed, ties half, the draws assigned in key
  order (swapping the sides gives exactly 1 − p, so My Week and the League screen agree). A starter whose game is in
  (`actual`) is a point mass; one without a range a point at his value. Returns `p` (calibrated: `shrink_week`, logit ×
  `WEEK_SHRINK = 0.60`), `p_raw`, `mine` / `theirs` (the projections, actual points where in), the simulated means,
  the counts. `week_words(p)`: "a coin flip" / "a slight favorite (underdog)" / "a clear favorite (underdog)" on D6's
  55 / 65 cut points. A finished week is 1 / 0 / ½.
* **2. On My Week** (`myweek.py` block `# ---- IH-3`: `win`, `win_answer`, `win_starters`, `with_actuals`, `week_line`;
  one call line at the end of `my_week`; `ondemand.py` block: `win_on_demand`, `week_points`, one call line). `win` =
  `{p, percent, words, side, line, note, assumptions, early, mine, theirs, n_played, n_starters, opp_n_played,
  opp_n_starters, n_no_range, opp_n_no_range, played_words, opponent_roster_id, also}` (INTERFACES § IH-3). The lineups:
  our proposed lineup (its total = `lineup_value`) against the opponent's best lineup (the opponent line's number),
  both through the availability overlay — the same rows the page's totals come from. A game is **in** when the nightly
  has scored it (his team has rows in `fct_player_game_league` for the week); his points are then the league's own
  (`league_player_week.points_observed` on the house path, Sleeper's matchups `players_points` on demand; missing = 0;
  **no points at all for the week = unknown**, the line steps aside); a game in progress still counts as his range. MFL:
  no live points read — before the first game the line is there; after it, `note` "the week has started and this
  league's live scores are not read yet" and no line. No range (ranges carry under half a side's expected points): `note`
  "no range for this league yet", no line. The words follow the printed percent (64.96% prints 65%: "clear").
  **The screen** (`MyWeek.svelte` block): one line under the opponent line, `text-sm text-ink-2`, the assumption on
  hover; a double header names each opponent ("Big Mac Attack: You're a clear underdog this week: …").
* **3. Calibration** (METRICS § "Win probability — the week"; `scratchpad/waveIH/ih3/calib.py`, `oof.py`): the house
  leagues' 2024–2025 regular-season matchups with the starters each manager **actually** started, every QB–TE
  starter's walk-forward range (`calibration.oof_rows(ranges=True)`: the production fit on the seasons before, 2024 and
  2025, both house scorings; 7 CPU-min, read only), K / DEF one distribution per league-season, the outcome
  `fct_league_matchup.result`; 2026 weeks 1–2 from the frozen `ops.projections` rows. The raw number was overconfident
  (the favourite predicted 62.7%, won 57.5%) → a logit shrink, fitted on one season and tested on the other (2025
  0.2436 → 0.2403, 2024 0.2424 → 0.2387, 2026 w1–2 0.2451 → 0.2410). **As shipped**:

  | | Matchups | Brier (coin flip 0.25) | Favourite predicted | Favourite won | Higher projection won |
  |---|---|---|---|---|---|
  | 2024–2025 | 308 | **0.2395** | 58.0% | 57.5% | 57.1% |
  | 2024 / 2025 | 154 / 154 | 0.2387 / 0.2403 | 58.4% / 57.6% | 57.8% / 57.1% | |
  | 2026 weeks 1–2 | 22 | 0.2410 | 58.6% | 63.6% | 63.6% |

  Fifths (2024–2025): predicted 51.2 / 53.8 / 56.5 / 60.7 / 68.1%, won 50.0 / 56.5 / 53.2 / 55.7 / 72.1%. By word: coin
  flip 123 (52.5 / 53.7%), slight 141 (59.2 / 54.6%), clear 44 (69.7 / 77.3%). Not badly off → the percentage is shown
  (`WIN_EARLY` False; the "Early: 2 weeks graded" wording is kept behind it). Honest reading: a week is close to a coin
  flip; the number is a little better than 50% and calibrated on average, not a forecast to bet on.
* **4. The League screen** (`/api/league/week-odds?league=`, `myweek.week_odds`, main.py block `# ---- IH-3` before the
  web-app section; `League.svelte` block): this week's games, both teams' chance (`a.percent + b.percent = 100`) and
  expected totals. **Asked after the screen shows** — cold it costs one lineup per team: 1.8 s (Scrubs, 10 rosters) /
  2.0 s (dynasty, 12) / 4.9 s (MFL 70587, 12 on demand) here under load; cached in process after. On demand the
  numbers sit inside IC-4's "Week N matchups" card (one marked line per side + a note); a house league has no such card,
  so the odds bring their own (`league-odds`). No favourite in bold (a pick, by WORDS).
* **Scrubs roster 6 "GoodGameBuddy"** (week 4, the main database, the opponent from the Sleeper fixtures' week-4
  matchups): **"This week is a coin flip: 53%, 120 to 117 expected."** (vs MacZaddy; 10 starters a side, 0 played;
  the PIT defense has no range — `LINEUP_SQL` joins ranges by gsis id — and counts at its 9.35). League screen: MacZaddy
  47% · 117, GoodGameBuddy 53% · 120. Week 3 as the main database has it (Thursday's ATL–GB scored, the rest not):
  Run Bijan Run (roster 3) vs PSYCHO SILVERBACKS "You're a clear favorite this week: 84%, 140 to 104 expected. 2 of
  your 10 have played, 1 of theirs." (the two Falcons at Sleeper's points; `test_a_played_game_on_the_main_database`).
  Dad's league, Knight Train (team 1) at 12:10 ET: "Big Mac Attack: You're a clear underdog this week: 34%, 96 to 115
  expected." / "Klaby Crew: … 37%, 96 to 111"; after the 1 PM kickoffs (locked lineups) the recording says 3% / 4%, 47
  to 115 / 111.
* **Interfaces**: INTERFACES.md § IH-3 (draft 12:08 + final): `win` on `/api/my-week` (both paths); `GET
  /api/league/week-odds`; Python `decisions.lineup_win_probability`, `week_words`, `shrink_week`, `WEEK_ASSUMPTIONS`,
  `WEEK_SHRINK`, `WEEK_DRAWS`; web `WinProbability`, `WeekOdds*`, `weekOddsPath` (`lib/api.ts` block).
* **Files**: `src/league_lab/decisions.py` (block at the end), `api/league_lab_api/myweek.py` (block at the end + one
  line in `my_week`), `api/league_lab_api/ondemand.py` (block at the end + one line in `my_week`),
  `api/league_lab_api/main.py` (one route block), `api/README.md` (one row), `web/src/lib/api.ts` (block at the end),
  `web/src/routes/MyWeek.svelte` (two marked blocks), `web/src/routes/League.svelte` (marked blocks; two marked lines
  inside IC-4's card), `tests/test_ih3.py` (new, 7), `api/tests/test_ih3.py` (new, 11 + the recorder),
  `web/e2e/ih3/fixtures.spec.ts` (new, 5 × phone / desktop), `web/fixtures/ih3/api_ih3.json` (the recording),
  `docs/{METRICS,WORDS,STATUS}.md`, `CHANGELOG.md`.
* **Commands**: `uv run pytest -q tests` (in two parts, `OMP_NUM_THREADS=1`: the machine ran at load 12–15);
  `cd api && PYTHONPATH=. uv run pytest -q tests --ignore=tests/test_u1.py --ignore=tests/test_ig2.py` (those two apply
  the hosted SQL and write rows with the pipeline role — not on the main database); the failing ones again on `main`
  (`/home/claude/league-lab`, `ad4040e`); `uv run ruff check src app tests api`; `cd web && npm run lint && npm run
  build`; `FIXTURES_PORT=8615 npx playwright test --config playwright.fixtures.config.ts e2e/ih3 e2e/ic4 e2e/if4
  e2e/fixtures.spec.ts e2e/decisions`; `IH3_RECORD=1 … pytest tests/test_ih3.py -k record`; the calibration scripts.
  Nothing written to `league_lab` (reads only; the calibration's frame and rows went to the scratchpad).
* **Evidence — tests**: root **1,086 passed, 3 skipped, 2 failed** (`tests/test_ih3.py` 7 new: identical lineups →
  exactly 50%; every starter higher → > 50% and the closed form for normal sums within 0.02; teammates' correlation
  moves the spread both ways (my QB–WR stack lowers a favourite's chance, my WRs with *their* QB raise it, teammate RBs
  narrow); played games use the actual points; a kicker with P10 / P90 only; the shrink symmetric; inconsistent
  correlations repaired, fixed seed). The 2 failures (`test_my_week.py::test_my_week_is_the_mart` × 2) fail the same on
  `main` (`ad4040e`) at this hour. API (without `test_u1` / `test_ig2`, which write to the database with the pipeline
  role) **471 passed, 45 failed, 7 skipped**; **every one of the 45 fails the same on `main`** run against the same
  database minutes later (45 failed in 118 s): pinned pre-kickoff numbers against Sunday-afternoon locks (e.g.
  `test_ie1::test_scrubs_roster2_a_change_before_the_first_lock`, the on-demand vs house totals of locked rosters,
  `test_i0a`'s Jefferson-out lineups) — nothing IH-3 touches. `api/tests/test_ih3.py` alone after the last commit: 11
  passed, 1 skipped (the recorder). Web: `npm run lint` (eslint + svelte-check 0 errors / 0 warnings) and build clean;
  e2e `ih3` **10 passed** (phone 375 / desktop 1300: the line under the opponent line and above the league line, its
  hover text, no imperative words, the double header's two lines naming their opponents, no line without `win`, the
  League card for a house league with my game's two numbers = My Week's, the odds inside IC-4's card for MFL, none on
  last week's results, no sideways scroll); with `ic4`, `if4`: 24 passed; `fixtures.spec.ts` + `decisions`: 52 passed.
  Ruff clean.
* **What moved**: no existing number (only new keys, a new route and new lines on two screens). The page's existing
  totals are untouched; the line's expected totals are those totals.
* **Decisions** (nobody to ask): (1) **centred ranges** — each range moved so its mean is the projection: calibration is
  a wash (raw Brier 0.2430 vs 0.2432) and the line's percentage then agrees with its own "120 to 117" (as stored, a
  lineup's range means sat 3.5 points above its projection on the walk-forward and either way by several points on
  week 4; Scrubs roster 6 read 50% next to "120 to 117"). (2) **The shrink** (0.60) is applied in `decisions`, not on the
  screen: every reader gets the calibrated number; `p_raw` stays in the function's result. (3) **The opponent's best
  lineup**, not his submitted one (the opponent line's number; the submitted lineup is only known for Sleeper's roster
  `starters`, and the brief's "expected totals" are the page's). (4) **A game is in when the nightly scored it**, not at
  kickoff: a game in progress counts as its full range (no live partial scores: no outside calls during a request
  beyond Sleeper's cached matchups). (5) **Points from the league itself** (Sleeper's number in its own scoring) rather
  than our recomputation; no points at all for an in week = unknown, the line steps aside (never 0). (6) **MFL after the
  first game**: no line (no live points read) rather than a stale pre-week number. (7) **Words follow the printed
  percent** (64.96% → "65%: clear"), D6's 55 / 65 cut points read either side. (8) The League screen's odds are a
  **separate route asked after the screen shows** (1–5 s cold) instead of a key on `/api/league` (which would have
  slowed the screen for everyone); on demand they sit in IC-4's card, a house league gets its own card. (9) 20,000
  draws (±0.4 points at 50%; whole percent on the page) and the draws assigned in key order so My Week and League agree
  exactly. (10) "Early: N weeks graded" is built but off: the calibration is not badly off.
* **Not done**: live (in-game) scores — a game in progress is its full range; MFL's live points (MFL's `liveScoring`
  export would serve it; the line steps aside after the first kickoff); a DEF has no range on the house path
  (`cards.LINEUP_SQL` joins ranges by gsis id: the defense counts at its projection — the console's SQL, PO-owned); the
  console (Home) shows no win line (PO-owned pages); the inactive-starter risk (the ranges are "if he plays"); the
  calibration on the 2026 frozen record rows with the 50% range (weeks 4+, once scored) and per league; a metric
  registry row (`dbt/seeds`, PO).
* **Next**: re-grade after weeks 4–6 (the frozen rows carry P25 / P75 from week 4: the five-knot ranges) and refit the
  shrink on 2024–2026; MFL live points; the defense's range in `LINEUP_SQL`.

**For the PO**
1. **No dbt, no workflow, no render.yaml change.** The API reads `analytics.league_player_week` (already on the hosted
   copy: the console names it) and `analytics.fct_player_game_league` (already slim-published); `hosted_relations.py`
   lists both for `api` now.
2. **Merge notes**: `myweek.py` — one line at the end of `my_week` (`out["win"] = win(...)`) + a block at the end of the
   file (IH-1 and IH-2 add blocks there too: keep all three); `ondemand.py` — one line after the movers in `my_week` + a
   block at the end; `main.py` — one route block right before "the web app" section (it must stay above the
   `/api/{rest:path}` catch-all); `MyWeek.svelte` — a derived block after `versus` and a block right after the
   `opponent-line` paragraph (IH-1's banner sits above the actions: no overlap); `League.svelte` — an import line, a
   script block before `allPlay`, one marked line inside IC-4's side span and one after its list, a card after IC-4's
   block; `api.ts` — one block at the end; `api/README.md` one row. `src/league_lab/decisions.py` — a block at the end
   (M6 does not touch this file).
3. **Running the API suite on the main database writes**: `test_u1` and `test_ig2` apply `hosted_usage.sql` /
   `hosted_events.sql` and insert / delete rows with the pipeline role (the main `league_lab` has both schemas, owned
   by the pipeline role). IH-3 ran the suite with both ignored; the PO's own run on main is as before.
4. **The 45 API / 2 root failures** are the clock (Sunday after the 1 PM kickoffs) against pinned pre-kickoff numbers;
   they fail identically on `main` — expect them on any run between Sunday 1 PM and the next build.
5. **Decisions Andrew may want to reverse**: the line is on My Week by default (information; a one-line removal); the
   centring of the ranges on the projections; the shrink (0.60; `WEEK_SHRINK`); the opponent's best lineup rather than
   his submitted one.

## Wave I-I (Iteration 19)

### II-0 2026-10-04 — the calculation audit: one metric per comparison, legal replacement chains, one story per frame (branch `dev/II0`, clone `league_lab_i0a`)

* **Task**: II-0 (brief § "II-0"; the fifth review § 1 "Fix calculation and explanation inconsistencies", P0). Plan
  sections: § 19 (Iteration 19); METRICS § "Roster value" (new subsections "Strength by slot, fixed", "The legal
  replacement chain", "One frame, one story"); WORDS § "The calculation audit (Wave I-I, II-0)". Interfaces:
  INTERFACES.md § II-0 (written in the first 15 minutes; unchanged since).
* **1. Strength by slot — the cause.** Team's bar was the roster's best starter at a slot type, **his projected points**
  (`slot_strength[].top.value`); the "League average x, best y" under it and the rank were every roster's
  `starter_strength` — that starter's **margin** over his replacement (`decisions.team` `_slot_league`). Points against
  margins: a unit mismatch, not a population or horizon one (both were this week, both every roster's best starter at
  the type). It also drew one bar per slot *type* (RB2, WR2, FLEX2 invisible). **The fix** (`decisions.py` block
  `# ---- II-0`: `SLOT_POPULATION_SQL`, `_slot_population`, `_seats`, `_league_line`, `strength_by_slot`,
  `_units_on_slots`; one call in `team()`): `/api/team` gains `strength_by_slot` — every starting slot apart (each
  slot type's starters ranked best first: RB1 ≥ RB2, FLEX1 ≥ FLEX2), the value = this week's projected points of the
  player the roster starts there, the league's average / best / worst / rank over **every roster's value at the same
  slot**; an empty slot is 0 and counted (`n_empty`), an unvalued starter is unknown (left out, "—"); `groups` (a slot
  type's starters added up, ranked) and `depth` (`usable` = `bench_value`, the bench's own best legal lineup, beside
  `raw_bench`, the bench projections added up) are the secondary lines. The population is the mart's this-week rows
  (house) or the solved frame (on demand), with the overlay's moved rosters swapped in (IB-0's rule). The old
  `slot_strength[].league` is re-based on `top_value` (the bar's metric): it equals the first slot of each type.
  **Team.svelte** (block `<!-- ---- II-0 -->`): one bar per slot ("RB1 · Kyren Williams — 12.8 · 8th of 10", "League
  average 16.5, best 21.8 at RB1."), the card's sentence, "By position, starters added up: …", the usable-depth line;
  an answer without `strength_by_slot` (the recorded fixtures) keeps the old card. "How to read this" says so.
* **Before → after, League of Scrubs roster 2 (MacZaddy), the clone, week 4** (bar · league average / best · rank):

  | Slot | Before (bar vs margins) | After (one metric, one population) |
  |---|---|---|
  | QB Mahomes | 20.26 · 9.63 / **18.48** · 9th (a best below the bar) | 20.26 · 18.32 / 24.42 · 3rd of 10 |
  | RB | 12.80 · 8.66 / 14.76 · 10th | RB1 Kyren 12.80 · 16.52 / 21.81 · 8th; RB2 Hampton 11.28 · 12.94 / 17.73 · 8th |
  | WR | 12.75 · **4.13 / 6.83** · 6th | WR1 McMillan 12.75 · 13.02 / 15.55 · 6th; WR2 Jefferson 12.68 · 10.82 / 12.68 · 1st |
  | TE | 10.14 · 5.63 / 11.19 · 5th | 10.14 · 9.58 / 12.45 · 5th |
  | FLEX | 12.16 · **2.50 / 5.18** · 4th | FLEX1 P. Washington 12.16 · 11.42 / 15.16 · 4th; FLEX2 Tuten 9.72 · 10.03 / 13.47 · 7th |
  | K | 8.07 · 8.17 / 8.93 · 7th | the same (a lone K's margin is his value) |
  | DEF | 7.16 · 6.79 / 10.54 · 4th (n 9) | 7.16 · 7.73 / 10.54 · 6th (n 10) |

  Groups: RB 24.08 (9th of 10, average 29.47), WR 25.43 (3rd), FLEX 21.88 (4th). Usable depth 42.35 (4th of 10) beside a
  raw bench of 59.60. The review's Puka 14.8 vs 5.0 / 7.3 and Wilson 11.7 vs 2.5 / 4.3 are this same mismatch on the
  live data (WR and FLEX).
* **2. Legal replacement chains** (`src/league_lab/lineup.py` block `# ---- II-0`: `replacement_chain(players, slots,
  player_id, *, current=None)`, `chain_words`, `chain_slot_word`, `_reseat`). The re-solved legal lineup without him
  (locks kept: a locked starter keeps his very slot, a locked bench player never enters; eligibility the slots':
  FLEX, Superflex, MFL's "WR+TE" and team units), seated to move as few players as possible, read from the slot he
  leaves; returns `{cost, total_with, total_without, chain: [{kind: slides | enters | empty | benched, player_id,
  position, from_slot, to_slot, move}], enters, empty_slot, words}`. On a lineup frame: `cards.replacement_chain_rows`
  (`app/lib/cards.py` block; `locked_now` respected; `named_words` with full names), `cards.chain_alternative`,
  `cards.chain_cost`, `cards.locks_since_solve`, `cards.chain_words_linked`. **`cards.alternative` reads the chain**
  (the old value-matching search stays as the fallback when the chain cannot be read), so the cards, the player card
  (`player.py` block), My Week's margins (`myweek.margin_comparator` block) and Team's closest call
  (`decisions._weakest_chain_words`) say one chain. The review's case on the clone's numbers: Kyren sits → "Bhayshul
  Tuten (RB) moves from FLEX to RB; Michael Wilson (WR) fills the open FLEX", cost 3.60 (was "(Michael Wilson, 9.20,
  would come in)" with no move). Tuten locked at FLEX (his game started): he stays; "an RB comes off the bench into RB"
  (Croskey-Merritt), cost **3.61**. **Numbers that move** (the named bug): only after a lock since the solve (a game
  kicked off after the nightly solved the lineup: `locked_now` and not `is_locked`) — the stored margin assumed a
  now-locked player could move or come in, so the cards' and the player card's cost becomes the chain's. My Week's
  lineup table keeps the build's margin (the mart's and the console's: `test_myweek` / `test_parity` pin it) and adds
  `margin_now` with the words: on the clone at Sunday 15:45 ET (1 PM games locked) Hampton 2.08 / now 11.28, McMillan
  3.55 / 12.75, Jefferson 3.48 / 12.68, Kelce 4.35 / 10.14 — "no eligible reserve now (games kicked off since the
  build): sitting him costs 11.28" (every bench RB / WR / TE is locked). Before the kickoffs nothing moves.
* **3. Full names on a surname collision**: `cards.display_name(name, roster, position=None)` — the last name, or the
  full name when another player of the same roster shares it. `cards.decisions()` rows carry `short_name` /
  `alt_short_name`; `reason_line` / `tiebreak` and My Week's "over …" use them (the console shares `cards`).
* **4. One frame, one story** (`src/league_lab/trades.py` block: `week_story(weeks, by_week, span, *, this_week)`).
  The partner card's "Nothing changes this week" was `web/src/lib/decisions.ts` `partnerReason` treating any week
  under +0.05 as no change — beside the strip's own −1.5. Partner rows gain `story` (`decisions.row_story`, from the
  row's strip), the calculator's answer gains `story` (from its `strip`); `partnerReason` (marked line) says a losing
  week from the story (an older answer: from `you_gain_week`). On the clone every top Scrubs-2 package loses this week:
  "Nothing changes this week; your lineup gains +7.2 over weeks 4–7." → "Your lineup loses 0.5 this week but gains 7.2
  over weeks 4–7 in total (week 6 loses 0.6)." The calculator's `effect_words` already read the strip's numbers when
  the window starts this week (`now is trade`): now a test.
* **Files**: `src/league_lab/lineup.py`, `src/league_lab/trades.py`, `app/lib/cards.py`, `api/league_lab_api/
  decisions.py`, `myweek.py`, `player.py`, `web/src/routes/Team.svelte`, `web/src/lib/api.ts` (block at the end),
  `web/src/lib/decisions.ts` (marked lines), `tests/test_lineup_ii0.py` (new, 16), `tests/test_cards.py` (one assertion:
  the chain's words), `api/tests/test_ii0.py` (new, 7: 6 + the recorder), `web/e2e/ii0/fixtures.spec.ts` (new, 2 × 2),
  `web/fixtures/ii0/api_ii0.json` (recorded from the clone), `web/e2e/decisions/fixtures.spec.ts` (marked: either Team
  answer shape), `docs/METRICS.md`, `docs/WORDS.md`, this section, `CHANGELOG.md`.
* **Commands / evidence**: `uv run pytest -q tests/test_lineup_ii0.py tests/test_cards.py tests/test_lineup.py
  tests/test_lineup_ic2.py` (all pass); `cd api && PYTHONPATH=. uv run pytest -q tests/test_ii0.py` 6 passed (+1
  recorder, skipped without `II0_RECORD=1`); `FIXTURES_PORT=8621 npx playwright test --config
  playwright.fixtures.config.ts e2e/ii0` 4 passed (phone 375, desktop 1300; screenshots `e2e/.out/ii0-*`); `npm run
  lint` (eslint + svelte-check, 0 errors) and `npm run build`; `uv run ruff check src app tests api` clean.
* **Whole suites, Sunday afternoon, load average 40–50 on 2 CPUs (seven developers)** — run in shards on the clone;
  `wt-base` is at `ad4040e` (behind `main`), so the base is a scratch worktree of `94ed33c` (this branch's base) on
  the same clone, and every failure was re-run there. **Root**: 394 of 1,138 ran before the machine thrashed (393 passed,
  1 skipped, 0 failed); the II-0-relevant files (`test_lineup_ii0`, `test_cards`, `test_lineup`, `test_lineup_ic2`)
  were run whole beforehand (all pass). **API**: ~490 of 581 ran (round 1: 38 failed / 218 passed / 7 skipped / 3
  xfailed; round 2: 30 failed / 208 passed / 4 skipped, `test_decisions` counted twice). Of the 68 failures, 56 fail
  identically on `94ed33c` (the clock: locked players, as on `main`); 6 were the load (statement timeouts, latency
  bounds: all 6 pass on a re-run on this branch); 4 were mine — `test_myweek::test_my_week_matches_the_lineup_mart` ×2
  and `test_parity::test_my_week_is_the_home_page` ×2 (My Week's margin moved after a lock) — **fixed** by keeping the
  build's margin in the table and adding `margin_now` (re-run: pass, with `test_parity::test_my_week_is_the_home_page`
  ×2); `test_decisions::test_latency_cold_and_warm` and `test_research::test_trends_route[dynasty]` failed here under
  load and pass on a re-run (17:45 ET). **Delta against the base: 0.** Not run: ~90 API tests (`test_ie2`, `test_if3`, `test_m3`,
  `test_ic4` partly, `test_ig1` partly, `test_ih3`, `test_m6`, `test_parity` partly) — the PO's integration run covers
  them.
* **Not done**: the console's Team Hub (`app/pages/1_Team_Hub.py`, PO only) keeps its slot table — it labels value and
  strength as separate columns, so it has no mismatch, but it shows one row per slot type; Team's roster rows on the
  house path keep the stored margins (they carry no live lock: `TEAM_ROWS_SQL` reads the mart's `is_locked`), so on a
  Sunday afternoon My Week's re-solved margin can differ from Team's roster row (the words beside each are right);
  `ondemand.lineup_values` (Season) is II-4's.
* **Next**: re-record `web/fixtures/team_*.json` once the PO merges (the decisions e2e reads either shape); feed
  `strength_by_slot` to the console if Andrew wants the bars there.

**For the PO**
1. **Merge order**: II-0 touches shared files only in marked blocks — `decisions.py` (the Team block before IC-4's,
   `_weakest_chain_words` above `team_words`, `row_story` above `strip`, one line after `rank_partners` in `partners`,
   one in `calc_alternatives`, the `_slot_league` re-base), `trades.py` (a block at the end, after `__all__`),
   `cards.py`, `myweek.margin_comparator`, `player.py`'s starter sentence, `Team.svelte`'s slot card and its "How to
   read" line (II-4 edits other Team lines), `decisions.ts` `partnerReason` (II-1 may rewrite the partner card — keep
   `story`), `api.ts` (end block). Merge II-0 before II-1 if II-1 rebuilds partner rows, so the `story` line lands once.
2. **No dbt, no workflow, no render.yaml change.** One more read per `/api/team` (`SLOT_POPULATION_SQL`, the mart).
3. **Clock**: every II-0 test compares answers with each other, not pinned numbers; INF-1's pinned clock changes
   nothing here. The margins move on a Sunday afternoon by design (above).
4. **Decisions Andrew may want to reverse**: an empty slot counts 0 in the league population (it scores 0); the slot
   ranking within a type is by value (RB1 = the better RB starter), not Sleeper's slot order; the stored margin
   stands unless a game kicked off since the solve (no cent-level re-rounding).

### II-1 2026-10-04 — credible trades: both teams' alternatives, the K / DEF guardrail, "No compelling trade found" (branch `dev/II1`, clone `league_lab_i0b`)

* **Task**: II-1 of the Wave I-I brief (`scratchpad/waveII/BRIEF.md`; the fifth review § 2, "Make trade recommendations
  credible"). Plan sections: METRICS § Trades (appended "Credible trades", ct1.0), WORDS (new table "Credible trades").
  Branch `dev/II1` from `94ed33c`.
* **Interfaces** (INTERFACES.md § II-1): every Finder row and the calculator's answer carry **`card`** — `give`, `get`,
  `drops {mine, theirs}`, `your_effect` / `their_effect` `{this_week, window, by_week, raw_window, words}`,
  `depth_cost {mine, theirs, roster_spots, season_value, horizon}`, `waiver_alternative {mine, theirs, words}` (each IF-2's
  alternative + `covered_window` / `covered_by_week` / `availability` "guaranteed" | "claim" / `availability_words`),
  `beyond {mine, theirs, margin}`, `why_consider[]`, `why_refuse[]`, `plausibility {key, label, reasons}` (plausible /
  roster_fit / implausible), `guardrails[]`, `legal {ok, notes, checks}`, `credible`. The Finder: each row `tier`
  ("credible" | "explore") and `credible_rank`; top level `verdict {kind: "compelling" | "none", headline, reason}`,
  `credible_count`, `explore_count`, `headline_rank`, `guard_positions`, `margin`. **IF-2's row order and `rank` are
  unchanged** (pinned by IF-2 / IE-1 / IG-1 tests); the headline is the first credible row, or "**No compelling trade
  found.**" + the reason. Web: `TradeCard.svelte` (full / `compact`), the `lib/api.ts` II-1 block.
* **What it does** (METRICS § "Credible trades" has the rules in full)
  1. **The covered frame** (`trades.fill_empty`, `covered_side`): each roster-week valued with every EMPTY starting slot
     filled from that week's free pool, for both teams, before and after — bye coverage priced against the best free
     fill, never zero. The old gain stays beside it (`raw_window`), and the card says when the difference is bye cover.
  2. **Both teams' alternatives** (`decisions.ii1_alternative`): IF-2's `best_alternative` called for each roster (the
     same function both ways), re-priced on the covered frame (`trades.covered_move`), never below standing pat;
     "guaranteed" vs "a claim that might be lost" from the league's waiver setting.
  3. **Legality** (`card.legal`): ownership (`trades.clean_package` / `_owner`), roster limits and required cuts
     (`trades._after`, B3's rule), locked players (`RosterBoard.is_locked`), position requirements (the solver; a slot the
     trade empties is named and covered), the trade deadline (Sleeper settings / `dim_league_season`; MFL not read — said).
  4. **The K / DEF guardrail** (`trades.guard_positions`, `streamable_for_starter`): guard positions derived per league
     (not a skill position, no multi-position slot admits it, the free pool's best ≥ the league's weakest starter there);
     a package sending only guard-position players for a **starter** at another position is implausible unless the
     receiver has nobody at that position all window. No names.
  5. **Plausibility** (`trades.plausibility`): implausible (the guardrail; rule (a) from their side — they give much more
     season value above replacement than they get); a roster-fit idea (no season value or no market line for a player);
     else a plausible offer. **Threshold** (`trades.credible`): legal, both `beyond` ≥ 1.0 starter point over the window,
     not implausible, and not a trade IF-2's own line marks "below your best waiver move" (`ii1_same_story`); at most
     three promoted, the rest behind "Explore alternatives".
  6. **Web**: Trades — the headline is the first credible trade or "No compelling trade found." with the reason (no "Try
     this trade" then); credible rows with the full card; the rest in an "Explore alternatives" expander with the compact
     card; "How to read this" says the rule. The calculator: a "Worth proposing?" box with the full card.
* **Evidence**
  - **The Folk package** (`api/tests/test_ii1.py::test_folk_package_is_not_promoted`; the Scrubs clone with Nick Folk on
    roster 2 for Chase McLaughlin, Will Reichard on Run Bijan Run for Trey Smack, MacZaddy's backup QBs off as when the
    review ran): before (raw, unchanged) MacZaddy +0.5 / **+17.7** / **−8.4** / +0.5 (Mahomes's week-5 bye: the QB slot at
    zero; Reichard's week-6 bye), Run Bijan Run −17.5 / −17.7 / −8.3 / −17.0 (no QB left, at zero). Now (covered)
    MacZaddy +0.5 / −0.5 / +0.8 / +0.5 = **+1.2**, Run Bijan Run −2.8 / +0.5 / +0.9 / +0.2 = **−1.2** (beyond their own
    alternative −1.7); **Implausible** — "A K for a starter (Matthew Stafford): they have a K and the free pool holds one
    about as good, so a K is not worth a starter to them."; `credible` false; in the Finder it is an "explore" row. Reasons
    they might refuse: "Their starters lose 2.8 this week." · "It does not improve their starters over weeks 4–7 (-1.2)."
    · the guardrail. With the clone's own rosters (backup QBs kept): the same verdict.
  - **Scrubs roster 2 on the clone** (`/api/trades/partners?league=1389709692405551104&team=2`, the fixture API with the
    ESPN overlay, Sunday afternoon): "**No compelling trade found.** None of the 18 trades that raise both starting
    lineups over weeks 4–7 is worth proposing: 16 do not beat your own best alternative by a point, 11 do not beat the
    other team's and 1 is not a plausible offer. Your best move: the Tyler Allgeier claim gives +9.8 over weeks 4–7 (drop
    Jacory Croskey-Merritt)." — **0 credible, 18 behind "Explore alternatives"**. Before: "Best partner: PSYCHO
    SILVERBACKS … Tuten for Corum, +7.2" — on the covered frame that trade is −2.7 for MacZaddy (its +8.6 in week 7 was
    an empty slot at zero). The clone has no `mart_market_line`, so every card there is "A roster-fit idea" (17) or
    "Implausible" (1).
  - **The Test League team 1** (Sleeper fixtures, on demand): 2 credible of 8 — "Best partner: Team 10 … Skattebo for
    Ja'Marr Chase and Justin Herbert: +4.7 over weeks 4–7, them +3.0" (beyond: you 4.7, them 3.0).
  - **MFL 70587 team 8** (fixtures, Sunday): 0 credible of 17 ("3 do not beat your own best alternative, 16 do not beat
    the other team's, 3 are not a plausible offer"); the IF-2 headline "Chicago Bears QB for KC QB + Rice" is −15.2 for
    the other side on the covered frame.
  - **K for a starter on the clone**: McLaughlin for Dak Prescott (GIBB ME ANOTA ONE, Brandon Aubrey their kicker) —
    Implausible.
  - Tests: `tests/test_trades_ii1.py` 9 (covered frame; guard positions by format; the guardrail both directions and its
    exception; Superflex K-for-QB and QB scarcity; a 1-QB lost QB priced against the free pool; a legitimate 2-for-1
    consolidation with a required cut — plausible and credible; plausibility labels and the threshold; symmetry);
    `api/tests/test_ii1.py` 5 (the Folk package twice; the Finder never headlines it; Scrubs roster 2's card fields, the
    headline never below its own waiver comparison; the symmetric card); `web/e2e/ii1/` 3 × phone 375 / desktop 1300
    (Scrubs: No compelling + Explore; the Test League: the credible trade's full card; the calculator: K for a starter
    labelled Implausible), recorded from the fixture API on :8722 into `web/fixtures/ii1/api_ii1.json`.
  - Suites (Sunday afternoon, the machine at load 40–60 with seven developers' suites at once): `tests/test_trades_ii1.py`
    9 passed; `api/tests/test_ii1.py` 5 passed (twice: before and after the guardrail's narrowing); `uv run ruff check
    src app tests api` clean; web `npm run lint` (eslint + svelte-check + tsc: 160 files, 0 errors, 0 warnings) and
    `npm run build` clean; root `tests/test_trades.py tests/test_trades_ii1.py tests/test_trade_finder_page.py` 47 passed.
    **Latency** (`test_decisions.py::test_latency_cold_and_warm`, the Test League on demand, same minute): the Finder cold
    **10.1 s on `wt-base` → 17.7 s on `dev/II1`** (each partner's own best waiver move is computed once per context), warm
    0.40 → 0.57 s (the cards are kept on the context's frame); the budget (cold < 20 s) holds, narrowly on a loaded
    machine (one run at load ~20 measured 20.5 s and failed it — as did `/api/waivers`' 16 s). **The whole API and root suites did not finish inside the time box** (each got
    ~6% of a CPU: the API suite reached 12% in 55 minutes; the PO's `base94` run of `main` on `league_lab_i0a`, started
    27 minutes earlier, was at 60%). On the first 72 API tests both runs share: `main` 8 failures, `dev/II1` the same 8
    plus 3: `test_anyleague.py::test_latency_cold_and_warm[1389709692405551104]` and `test_decisions.py::
    test_latency_cold_and_warm` (latency budgets at load 40–60; the second passes when re-run at load ~15, above) and
    `test_f3.py::test_opponent_on_demand_reproduces_the_nightly[1321941740235550720-borrow]` (the on-demand opponent vs
    the nightly — no trade code; `dev/II1`'s run started 16:08 ET after the 4:05 PM kickoffs, `base94`'s at 15:41: the
    brief's clock failures, not re-run on `wt-base`). **The PO's integration run on INF-1's pinned clock is the delta that
    counts.** `api/tests/test_if2.py` fails on `wt-base` at the same assertion
    (`test_finder_ranks_trades_against_the_best_waiver_move`: Cincinnati Bengals vs Atlanta Falcons, the clock).
  - e2e: `web/e2e/ii1/fixtures.spec.ts` — recorded from the fixture API on :8722 into `web/fixtures/ii1/api_ii1.json`
    (recording merges into the file, one test at a time with `-g` on a slow machine), re-recorded on the final code:
    **6/6 passed** on replay, phone 375 + desktop 1300 (the phone Scrubs run once timed out on its full-page screenshot at
    load ~40 after every assertion had passed; re-run alone: passed). Screenshots `ii1-*-{phone,desktop}.png` in
    `scratchpad/ii1/shots`.
* **Changed tests outside mine** (behaviour moved where the review names the bug): `api/tests/test_if2.py` (the headline
  is the first credible row or "No compelling trade found"; the IF-2 order assertions untouched), `api/tests/
  test_decisions.py` (the headline may start "**No compelling trade found.**").
* **Not done / limits**: the free pool's contention (two teams wanting the same free kicker) is not modelled; the cover's
  roster spot is not charged; per-player waiver state (on waivers vs a free agent) is not read — the league's setting
  decides "claim"; no trade-market source exists (Sleeper's projection line is the only market input — production has
  `mart_market_line`, the clones do not); dynasty / keeper horizons are disclosed, not valued; the Finder's first answer
  costs more on a cold on-demand league (each partner's alternative is computed once, then kept on the context).
* **Next**: a real market input (a trade-value feed) would turn roster-fit ideas into offers; waiver state per player
  (Sleeper's transactions) for "guaranteed" vs "claim".
* **For the PO**
  1. Merge order: II-1 touches `trades.py` / `decisions.py` only in `# ---- II-1` blocks plus three marked lines in
     `partners()` / `evaluate()` (the headline, `words.alternative`, the card hook); II-0 edits `trade_story` / `team()` —
     no overlap expected. `lib/api.ts`: one block at the end.
  2. **A decision Andrew may want to reverse**: the guardrail's exception is "they have nobody at that position" only —
     the brief's "or worse than the free pool" is not applied (the free pool's best kicker beats nearly every rostered
     kicker by ~1 point, so it let every kicker-for-starter package through). One line in `streamable_for_starter`.
  3. **A decision Andrew may want to reverse**: a trade must beat the OTHER team's own best waiver move too (the brief's
     threshold) — on the house league that leaves "No compelling trade found" most days; the margin is 1.0 starter point
     (`CREDIBLE_MARGIN`).
  4. **Cost**: the Finder's first (cold) answer on an on-demand league is ~7 s slower (each partner's own best waiver move,
     once per context; 10.1 → 17.7 s on the Test League); warm is unchanged. If Render's cold Finder matters more than the
     other team's alternative on every card, compute theirs only for rows that pass your side (one condition in
     `ii1_card`).
  5. No dbt, workflow or render.yaml change. No acceptance probability anywhere (the old dial's "Effect on their
     starters" words are unchanged).

### II-2 2026-10-04 — one shared player viewer: the drawer (branch `dev/II2`, clone `league_lab_ia3`, read only)

* **Task / plan**: II-2 of the Wave I-I brief (`scratchpad/waveII/BRIEF.md`), the fifth review § 3 ("Use one shared
  player viewer everywhere"). DESIGN § "The drawer" (appended). Branch `dev/II2` from `94ed33c`.
* **Interfaces** (INTERFACES.md § II-2, with its 16:50 update): `web/src/lib/player-drawer.svelte.ts` — `openPlayer(key,
  {origin?, from?, context?, returnFocus?})`, `closePlayer()`, `playerLink(key, opts)` (attachment), `drawer` (`key`,
  `from`, `context`, `origin`, `expanded`, `section`), `DRAWER_SECTIONS`, `setSection`, `setExpanded`, `restoreFocus`,
  `openFullPage`, `loadCard` / `cachedCard` / `cardKey`, `addToCompare` / `compareTray` / `removeFromCompare`,
  `onPlayerOpen(fn)` → `{content_type: "player", item_id, origin, league_key, roster_id}` (ids only; INF-1 chose to send
  `select_content` from the URL's `pane=` instead, so nothing subscribes today). `lib/router.svelte.ts` `setLinkHook(fn)`
  (marked block). IB-1's `lib/pane.svelte.ts` keeps every export (`openPane`, `closePane`, `paneLink`, `pane`,
  `openFullPage`, `paneActions`, `lineupPane`) and delegates to the drawer. URL unchanged: `?pane=<key>&from=<from>`.
* **What it does**
  1. **Every player link opens the drawer.** The router's link hook takes a plain tap on any `<a href="/player/<key>…">`
     on a league screen and opens the drawer instead of the page (Cmd / Ctrl / middle click still open the page; on the
     player page itself links still navigate; `data-full-page` opts a link out). So Waivers, Receivers, Team and Season
     rows, the Trades lists, League, Matchups, My Week, Compare and the names inside sentences ("Michael Wilson, 9.20,
     would come in") all open it with **no change in those routes** — which keeps II-3's and II-4's files free of my
     edits. The one route edit: **Waivers** passes the claim's context on its three name links (the free-agent list,
     its detail card, the stashes: `pane={{ from: "waiver", … }}`, one line each, marked) so the drawer offers
     **Evaluate add / drop** — the review's own path (All available → WR → a free agent).
  2. **A compact first view in four sections** — Overview (the card unit with this week's projection, the one-line
     reason, the actions, the projection tiles with the typical range and low- / high-end outcomes, availability and
     the news line, his lineup value, his role; the week-by-week ledger, the stat line — the same pieces as the one-line
     reason — and the schedule behind expanders), Usage, Game log, News (status + every item, sourced, dated, linked
     out). ARIA tabs (arrows, Home / End). The league and its scoring in the head ("League of Scrubs scoring · week 4").
  3. **Expand** (⤢): a modal `<dialog>` lightbox with every section open in two columns; Escape or "Back to the panel"
     collapses it to the drawer and focus returns to Expand.
  4. **Add to compare** (a pair: the first waits for the second, the screen stays; the second opens Compare with both,
     league and team kept) and **Full player page** (league and team kept; Back lands on the screen without the drawer).
  5. **History and focus**: the first open is one history entry — browser Back closes the drawer before it leaves the
     screen; a swap adds none; the drawer takes focus on open; ×, Escape and Back return focus to the name that opened
     it (a name inside the drawer swaps it without losing that), never scrolling the screen.
  6. **Phone**: a full-height sheet (was 88 dvh from the bottom).
  7. **Cache and the stale guard**: the card is cached by player + league + team + data version (`/api/status`
     `updated_at`; a new build drops every cached card and the API module's copy), five minutes at most; a request
     token makes an older, slower answer resolve to nothing, so it never overwrites a newer pick.
  8. **State kept under it — a fix in `App.svelte`** (marked): the lazy screens (Trends, Matchups, Players, Receivers,
     Compare, About) were awaited through a fresh `import()` promise on every route change, so opening the drawer (or
     any `?param` change) re-mounted the screen: Receivers lost its "Show all", its pick and the focused name. One
     promise per screen now; the screen stays mounted under the drawer.
* **Files**: `web/src/lib/player-drawer.svelte.ts` (new), `web/src/components/PlayerPane.svelte`, `web/src/lib/pane.svelte.ts`
  (II-2 block: delegates), `web/src/lib/router.svelte.ts` (II-2 block: `setLinkHook`), `web/src/App.svelte` (II-2 block:
  one promise per lazy screen), `web/src/routes/Waivers.svelte` (three marked lines), `web/e2e/ii2/fixtures.spec.ts`
  (new), `web/e2e/ib1/fixtures.spec.ts` + `web/e2e/if4/fixtures.spec.ts` (one line each: the game log is the drawer's
  Game log section now, not an expander), `web/e2e/fixtures.spec.ts` (two lines: a name → the drawer → Full player page), `web/fixtures/player/1389709692405551104_{00-0038117,00-0039880,00-0038544}.json`
  + `web/fixtures/save_ii2_fixtures.py` (three Scrubs free agents' cards — Wan'Dale Robinson, Malik Washington, Quentin
  Johnston — recorded from a fixture API on port 8723: the API's test fixtures for Sleeper / ESPN / MFL, this clone,
  events off; their projections equal the Waivers fixture's 8.30 / 8.21 / 8.12), `docs/DESIGN.md` (§ "The drawer").
* **Commands**: `cd web && npm run lint` (eslint + svelte-check + tsc: 0 errors, 0 warnings; there is no `npm run check`
  script — `lint` runs `typecheck`), `npm run build`, `FIXTURES_PORT=8623 npx playwright test --config
  playwright.fixtures.config.ts e2e/ii2` (**14 passed**: 7 tests × phone 375 / desktop 1300); the suites that open the
  pane — `e2e/ib1 if4 n1 n2 if3 ig1` — **46 passed** (4 failed on the first run: the two `pane-gamelog` lines, fixed
  in ib1 / if4 and re-run green); `e2e/fixtures.spec.ts` "a stranger…", "a house league through the picker…", "Trends…"
  **6 passed** (the last two tapped a name and expected the page: now name → drawer → Full player page);
  `e2e/fixtures.spec.ts h1 decisions ib2` **72 passed**; `uv run ruff check
  web/fixtures/save_ii2_fixtures.py` (clean). No Python under `src app tests api` touched.
* **Whole e2e** (`FIXTURES_PORT=8623 npx playwright test --config playwright.fixtures.config.ts --workers 3`, after the
  load on the shared machine dropped): **285 passed, 1 skipped, 0 failed** (286 tests; `e2e/ii2` adds 14). Two
  earlier full runs stalled when `vite preview` stopped answering under load 40–112 (seven developers' suites, no
  swap); the chunks above were run in between.
* **Numbers**: none moved (a web-only task; no API, no model).
* **Not done**: the phone sheet does not make the page behind it `inert` (a keyboard on a phone could tab behind the
  sheet; the desktop drawer is nonmodal by design); no prefetch on hover; Compare is still a pair (II-3's 2–4 selection
  opens the first two); `onPlayerOpen` has no subscriber (INF-1 reads `pane=` from the URL).
* **Next**: after II-3's merge, re-run `e2e/ii2` — its Players test uses `players-table` / `players-search` and
  `position=WR&sort=target_share`; its Receivers tests use `/receivers?view=cards` (II-3 redirects bare `/receivers` to
  the Stats preset; the role-card view stays at `view=cards`).
* **For the PO**
  1. **Merge order**: anywhere; conflicts are unlikely — `App.svelte` (II-2 block near `LAZY`; INF-1 also edits App for
     `page_view`), `Waivers.svelte` (three lines inside the free-agent / stash `PlayerRow` / `PlayerCard` tags; II-4
     edits the top-three intro), `router.svelte.ts` (`interceptLinks`, one line + the hook block).
  2. II-3's Players links keep IB-1's `paneLink` line: it delegates to the drawer, so nothing to swap there.
  3. Two older e2e lines changed on purpose (ib1, if4): the game log left the Overview for its own section.
  4. `web/e2e/app.spec.ts` (the live-API suite, not run here; IB-1's lineup names already broke its "one tap → the page"
     lines) still expects a My Week name to open the page in one tap (~lines 58–80, 85–92, 186): with the drawer a name
     opens the drawer and `pane-full` opens the page. Not edited blind.
  5. **Decisions Andrew may want to reverse**: every player link opens the drawer, including names inside sentences
     and on Compare (the full page is one tap away; Cmd-click opens it); the drawer takes focus on every open; Add to
     compare waits for a second player instead of opening Compare at once; the stat line sits behind the expander in
     the drawer (the one-line reason says the same).

### II-3 2026-10-04 — the Stats Explorer and the data inventory (the fifth review § 4, § 10)

- **Task**: II-3 (brief `scratchpad/waveII/BRIEF.md` § II-3; review § 4 "Consolidate Players and Receivers into a Stats
  Explorer", § 10 "Audit and expand the advanced-data layer"). Branch `dev/II3` from `94ed33c`; clone `league_lab_m1`
  (read only — **no new mart, no scratch schema**: the frame is aggregated on request from `analytics.fct_player_game`,
  already on the hosted copy).
- **Files**: `api/league_lab_api/stats.py` (new: the column catalogue, presets, windows, the aggregation),
  `research.py` (marked II-3 blocks: `players(..., window=, basis=, weeks=, who=, team=, nfl=)` → `stats_frame`; the
  legacy answer gains `catalogue` / `presets`), `main.py` (the route's params, marked), `web/src/routes/Players.svelte`
  (Players · Stats), `web/src/components/TopBar.svelte` (Players tab = **Stats · Trends · Matchups · Compare**, marked),
  `web/src/App.svelte` (marked: `/receivers` → `/players?position=WRTE`; role cards at `/receivers?view=cards`),
  `web/src/lib/api.ts` (II-3 block: `StatsColumn`, `StatsPreset`, `StatsWindow`, `StatsRow`, `StatsFrame`, `statsPath`),
  `web/e2e/fixtures.ts` (marked: the Stats frame served from the recording), `web/e2e/fixtures.spec.ts` + `web/e2e/ib1`
  (marked: the Players / Receivers tests and the tab list follow the new screen), `web/e2e/ii3/fixtures.spec.ts`,
  `web/fixtures/ii3/api_ii3.json`, `api/tests/test_ii3.py`, **`docs/DATA_INVENTORY.md` (new)**, `docs/METRICS.md`
  § "The Stats Explorer", `dbt/seeds/metric_registry.csv` (+8 rows: `stats_window`, `rb_carry_share`,
  `inside_5_carry_share`, `red_zone_opportunities`, `catchable_rate`, `snap_share_window`, `cpoe_weighted`,
  `ngs_ryoe_time_to_throw`).
- **Interfaces** (INTERFACES.md § II-3): `GET /api/players?window=season|last3|last5|weeks&basis=games|weeks&weeks=lo-hi
  &who=all|mine|fa|others&team=&nfl=&position=ALL|QB|RB|WR|TE|WR,TE&min_games=&sort=&dir=&limit≤1000` → `{window:
  {key, basis, weeks, through_week, label, note}, total, players: [identity + games + first_week/last_week + points /
  points_per_game + counts with `<count>_per_game` + shares / rates + their samples], catalogue: [{id, label, short, kind,
  format, per_game, definition, numerator, denominator, aggregation, source, status, available, reason, coverage,
  positions}], presets: [{key: wrte|rb|qb, label, positions, columns, extra, sort}], howto}`. Without `window` the
  answer is the old season table (pinned by the old tests) + `catalogue` / `presets`.
- **Columns shipped by status** (the catalogue = the inventory; 48 columns): **verified present** 15 — games, targets,
  receptions, receiving yards / TDs, carries, rushing yards / TDs, pass attempts, completions, passing yards / TDs,
  interceptions, sacks, snap share; **derived** 29 — fantasy points (league scoring), expected points per game, target
  share, catch rate, yards per target, air-yard share, aDOT, YAC per reception, red-zone targets / target share,
  first-read target share, catchable-target rate, charted targets, route participation / TPRR / YPRR (estimates,
  completed seasons only), carry share, backfield (RB-only) carry share, yards per carry, red-zone carries / carry
  share, inside-5 carries / share, red-zone opportunities, completion %, yards per attempt, dropbacks, scrambles, CPOE
  (nflfastR, attempt-weighted); **planned** 2 — NGS rushing yards over expected per attempt, NGS time to throw
  (ingested to `staging.stg_nflverse__ngs_*` 2016 → 2026 week 3, no mart); **unavailable** 2 — licensed routes run,
  pressure splits. **Routes run / route participation / per-route metrics are unavailable in-season** (participation
  is published after the postseason; `bridge_play_participation` ends at 2025): in 2026 those cells are null with that
  reason, and the picker offers them disabled.
- **Presets** (the review's defaults; extras only where present / derived): WR / TE — G, Pts/G, Tgt/G, Tgt %, Rec yds/G,
  Snap % (sort target share); RB — G, Pts/G, Car/G, Car %, Tgt/G, Snap %, Rush yds/G, Rec yds/G (sort carry share);
  QB — G, Pts/G, Att/G, Pass yds/G, Car/G, Rush yds/G (sort points). All — G, Pts/G, Tgt/G, Tgt %, Car/G, Car %, Snap %.
- **The screen**: Players · Stats — search, position (All / WR / TE / WR+TE / RB / QB), whose (Everyone / Yours / Free
  agents / Other teams), NFL team, the window (Season / Last 3 or 5 games played / Last 3 or 5 calendar weeks / Week
  range), Per game ↔ Totals (counts switch; shares keep their denominators), minimum games and minimum opportunities
  (targets + carries, + pass attempts for a QB), the window stated under the
  controls ("Last 3 calendar weeks (weeks 1–3) · … the G column says how many"), the column picker (definitions on
  hover; planned / unavailable disabled with the reason; coverage for charting), saved views (localStorage, this
  browser only), the role cards link on WR / TE, 2–4 players side by side (+ "Open … in Compare" for the first two),
  the table scrolling inside its box with a **sticky header and player column** (no page sideways scroll at 375), —
  with the reason on hover, a cell's sample on hover ("23 of 57 team carries in his 2 games"), sorting over the full
  filtered set before "Show more", the definitions of the shown columns under "How to read this". Player links keep
  the existing `paneLink` line unchanged (II-2's drawer had not landed in this worktree; `pane.svelte.ts` delegates to
  it once merged — the PO merges II-2's one-line swap).
- **Kyren Williams's carry share** — card and table are one arithmetic: the card's `mart_player_availability.carry_share`
  (= `mart_player_recent_form.carry_share_std`) and the table's season window are summed carries / summed team carries
  in his games. Clone (weeks 1–2): 11/29 + 12/28 → **23 / 57 = 40.4%** on both (`test_kyren_carry_share_card_and_table_agree`,
  e2e "Kyren Williams: the table's carry share is the card's"); on the main database with week 3 the card's **47.5%**
  is the table's number by the same test. The carry share includes QB scrambles and kneel-downs in the team total
  (nflverse carries) — said in its definition; the backfield share (RBs + FBs only) is a separate column.
- **Evidence**: `api/tests/test_ii3.py` **17 passed, 1 skipped** (the recorder) — the season window equals
  `mart_player_season` column by column for every QB / RB / WR / TE in 2025 and 2026; summed ratio vs weekly mean; a
  missed game not widening the denominator; Postgres rounding; windows; ownership partition; NFL team; the review's
  question in one call; sorted before the page; routes null in season; bad params 400; the legacy answer unchanged;
  the inventory lists every catalogue column with its status. e2e `web/e2e/ii3` **10 / 10** (phone 375 + desktop 1300);
  the shared specs the new screen touches (`e2e/fixtures.spec.ts` Players · Stats, Receivers, Compare, Matchups, every
  screen light + dark; `e2e/ib1` four tabs) **14 / 14**. Root `tests/test_nightly_relations.py` 6 / 6 (the hosted
  relation audit picks up nothing new). Ruff clean; eslint + svelte-check clean (159 files, 0 warnings); build ok.
- **The whole API suite vs `wt-base`** (both on `league_lab_m1`, `LEAGUE_LAB_DB_NAME` overriding wt-base's `.env`;
  wt-base is at `ad4040e`, not `94ed33c`; `test_u1` / `test_ig2` ignored): the machine sat at load 15–60 (seven
  developers' suites and builds), so neither whole run could finish in the time box. Run twice side by side and stopped
  at the same point; the second, quieter run: **the first 191 tests identical outcome by outcome — 176 passed, 13
  failed, 2 skipped on both** (delta 0; the failures are the Sunday-afternoon locks the brief names). The files that
  read `/api/players` run whole on II-3 at lower load: `test_research.py` + `test_i0b.py` + `test_n2.py` **62 / 62**
  (wt-base on the same files under peak load: 56 passed, 6 `QueryCanceled: statement timeout` — load, not code); the
  two heaviest II-3 tests that once timed out under peak load pass alone. The PO's full run on a quiet machine is the
  number to trust.
- **What moved**: no number moved. The Players screen is redesigned (its old G3 assertions — "Most points: …",
  three visible headers on a phone — are replaced in `e2e/fixtures.spec.ts`, marked); the Players tab opens Stats
  (it opened Trends); `/receivers` redirects.
- **Not done**: NGS columns (planned: a small mart over `stg_nflverse__ngs_*` with NGS's qualification rules); a team
  snap total for a ratio-of-sums snap share (nflverse publishes the rounded per-game share only); Compare with 3–4
  players (the side-by-side panel shows up to 4; Compare opens the first two); CSV export (none exists; the API is the
  export and agrees with the card).
- **Next**: the NGS mart; the review's "role changes" analytics on the same frame (window vs earlier window).

**For the PO**
- **No dbt model to build** on the main database or the hosted copy: the frame reads `analytics.fct_player_game`
  (already published) and the league marts the old screen read; `scripts/hosted_relations.py` picks up nothing new
  (`stats.py` names only `analytics.fct_player_game`). Run `dbt seed --select metric_registry` for the 8 new rows.
- Merge with II-2: `Players.svelte` was rewritten; its player link line (`{@attach paneLink(...)}`) is kept verbatim —
  apply II-2's one-line swap there by hand if git does not. `Receivers.svelte` is untouched (II-2's line applies
  cleanly). II-4's sweep may touch the Stats labels: the catalogue's `label` / `definition` are the words (stats.py).
- Decisions Andrew may reverse: snap share stays the mean of per-game shares (the card's number); carry share keeps
  scrambles and kneels in the team total (the card's number) with the RB-only share beside it; the Players tab opens
  Stats first; the recording `web/fixtures/ii3/api_ii3.json` is 3 MB (compact JSON; the dynasty's All frame is most
  of it).
- Kyren's 47.5% on the main database: `PYTHONPATH=. uv run pytest -q api/tests/test_ii3.py -k kyren` there confirms it
  (I did not touch `league_lab`).

### II-5 2026-10-04 — one setup flow, what each platform gives, the ESPN / Yahoo verdicts, the account design (branch `dev/II5`, database `league_lab_i0b`, read only)

* **Task / plan**: Wave I-I brief § II-5; the fifth review § 9 ("Simplify onboarding and add accounts/profiles", the
  provider plan) and § 11 item 5 ("an account/provider capability matrix and an explicit ESPN feasibility outcome").
  Plan § 17 (Iteration 19). Branch `dev/II5` from `main` `94ed33c`.
* **Delivered**
  1. **One setup flow** at `/leagues` (also what `/` shows with no league) — `Leagues.svelte` `<!-- ---- II-5 -->`
     blocks: the steps "Platform › League › Team › My Week" (the current one marked, `aria-current="step"`); one
     **Fantasy platform** choice (Sleeper / MyFantasyLeague — native radios styled as two buttons; `?platform=` deep
     link; remembered on the device, `prefs.platform`); then that platform's box only: **Sleeper** takes a username **or
     a league link / id** (a link goes to the new `GET /api/leagues?sleeper=` — the league, "Which team is yours?", the
     read-back card); **MFL** keeps I0-C's one box (link, id or name). "Where do I find these?" / "Where do I find the
     league id?" with an example each (`sleeper.com/leagues/1389709692405551104/team`,
     `www45.myfantasyleague.com/2026/home/70587`). A username row with no team of yours gets "Pick the team to see" on
     the setup screen (it said "after you open it"). "ESPN or Yahoo?" says not supported yet, and why, in two sentences.
     "No account needed: isuckatfantasy remembers your leagues on this device." (guest exploration kept). The password
     screen (`Login.svelte`) says what comes next and that it is not a Sleeper / MFL password.
  2. **Specific recoverable errors** (`ondemand.py` `# ---- II-5`: `SetupError(NotFound)` with `code` / `fix`;
     `main.py`'s NotFound handler passes them through; 502 gains `code: "provider_down"`, 503 `code: "busy"`):
     `sleeper_user_unknown` "That Sleeper username does not exist: “nobody_here”." · `sleeper_username_invalid` ·
     `sleeper_league_unknown` "Sleeper has no football league 1234567890123456." · `sleeper_link_invalid` ·
     `mfl_league_private` "MFL league 99999999 is private or does not exist. Ask the commissioner to allow API access to
     the league's data (MFL's league setup, the privacy option)." · `mfl_link_invalid` — each with a `fix` line (where
     the id is). MFL answers a private and a missing league with the same error body, so the sentence says both. The web
     reads them through `providers.setupGet` (keeps the error body; `api.get` drops it) and shows the words, the fix
     (`setup-fix`) and `data-code`; an older answer without a code keeps the old words.
  3. **`platforms.capabilities(provider)`** (`platforms.py` `# ---- II-5`): eight features — scoring, roster slots,
     matchups, players, waivers, transactions, team assets, news — each `yes` / `partial` / `no` with its words and, for
     `no`, the sentence a screen says (`unavailable(provider, feature)` → "Transactions: not available for MFL leagues
     yet"); `capabilities_for(league_key)`, `all_capabilities()`; `GET /api/providers`; the username and MFL answers
     carry `capabilities`. The setup screen lists them ("What isuckatfantasy reads from MFL leagues — 1 not available
     yet"; Yes / Partly / Not yet). **The one substitution found and fixed**: League's "Latest moves" on an MFL league said
     "No completed moves yet this season" (MFL's transactions are never read: `MFLLeagues.transactions` answers `[]`) —
     it now says "Transactions: not available for MFL leagues yet." (`League.svelte` `# ---- II-5`, from
     `lib/providers.gapLine`).
  4. **`docs/PROVIDERS.md`** (new): the matrix (Sleeper / MFL as built, ESPN / Yahoo as researched), what was read and
     quoted (WebFetch, 2026-10-04: docs.sleeper.com, ESPN support's public-league article, Disney's terms, the community
     ESPN clients' docs, Yahoo's developer access / docs / API terms, ffscrapr's MFL connection; MFL's own `api_info` is
     robots-blocked), **the ESPN verdict** and the Yahoo note. **`docs/ACCOUNTS.md`** (new, design only): the model
     (sign-in identity apart from provider connections; stable external ids; `league_key` = provider + season + id;
     scoped preferences; disconnect / expiry / idempotent per-league sync; public caches never hold account data) and the
     sign-in recommendation with costs and what it needs on Render / Neon / Cloudflare.
  5. **Found on the way**: the switcher would have called a Sleeper league opened by its link "· MFL"
     (`leagues.leagueOptions`, a marked line); `docs/ESPN_TERMS.md` said Disney's terms were not read — they are now,
     and they bear on the shipped news line and injury overlay too (For the PO).
* **The ESPN verdict**: we would support, at most, **ESPN public leagues, read-only, by league id**, labelled an
  unofficial read, free beta only — **not built now**. We would **not** support pasting `espn_s2` / `SWID` login cookies
  (not as the normal path, not hidden), any ESPN write, or ESPN in a paid product without ESPN's written permission
  (Disney's terms forbid automated access and commercial use; no ESPN developer program exists).
* **Sign-in recommendation**: a passwordless **emailed link** built in our FastAPI (three tables in a new `accounts`
  schema on Neon, a separate read-write role, Resend for mail — free to 3,000 a month / 100 a day, then $20), Google as a
  second button later; ~$0 at beta scale. Needs on Render `LEAGUE_LAB_RESEND_API_KEY`, `LEAGUE_LAB_MAIL_FROM`,
  `LEAGUE_LAB_SESSION_SECRET`, `LEAGUE_LAB_ACCOUNTS_DB_URL`; SPF / DKIM on `isuckatfantasy.io`; a `hosted_accounts.sql`
  the nightly never drops.
* **Interfaces**: INTERFACES.md § II-5 (15:30), as built: route `/leagues` (+ `?platform=sleeper|mfl`); `GET
  /api/providers` → `{providers: [capabilities], features}`; `GET /api/leagues?sleeper=<link or id>` → `{platform,
  league, teams, roster_id: null, card, capabilities}`; `capabilities` on `?username=` / `?mfl=` / `?mfl_search=` (a link)
  answers; `capabilities(provider)` = `{provider, name, short, status, connect: {kind, label, example, where}, features:
  {<8>: {label, status, words, unavailable}}}`; error keys `ondemand.SETUP_CODES`; web `lib/providers.ts` (`gapLine(league,
  feature)`, `setupGet`, `setupError`, `platformOf`, `looksLikeSleeperLeague`); `prefs.platform / setPlatform`; testids
  `setup-steps`, `platform-sleeper` / `platform-mfl`, `other-platforms`, `setup-help`, `setup-fix`, `provider-caps` /
  `cap`, `setup-guest`, `sleeper-card`, `team-pick`, `team-option`, `team-pick-open`, `moves-unavailable`, `login-next`.
* **Files**: `src/league_lab/platforms.py`, `api/league_lab_api/{ondemand,main}.py`, `api/tests/test_ii5.py` (new, 18),
  `api/tests/test_f3.py` (two re-pins, marked: the unknown user's words, the 503's `code`), `web/src/routes/{Leagues,League}.svelte`,
  `web/src/components/Login.svelte`, `web/src/lib/{providers.ts (new), prefs.ts, leagues.ts}`, `web/e2e/ii5/fixtures.spec.ts`
  (new, 6 × phone 375 / desktop 1300), `web/fixtures/ii5/*.json` (8 recordings), the platform click in ten older e2e specs
  that open the MFL box (`i0b`, `i0c`, `ic3`, `ic4`, `ie0`, `ie2`, `ig3`, `ih2`, `ih3`, `v2` — one marked line each; `i0b`'s
  label line re-pinned), `docs/{PROVIDERS,ACCOUNTS}.md` (new), `docs/{WORDS,ANY_LEAGUE,ESPN_TERMS,STATUS}.md`,
  `CHANGELOG.md`.
* **Recordings** (`web/fixtures/ii5/`): from a fixture API on :8726 (`api_po.sh`'s env, this worktree, `league_lab_i0b`):
  `curl :8726/api/providers`, `/api/leagues?username=nobody_here`, `?sleeper=9000000000000000001`,
  `?sleeper=1234567890123456`, `?mfl_search=70587`, `?mfl_search=99999999`, `?mfl_search=https%3A%2F%2Fexample.com%2Fx`,
  `/api/my-week?league=mfl%3A70587&team=8`. The League test reuses IC-4's recording (`fixtures/mfl/api_70587_ic4.json`).
* **Commands and evidence** (Sunday afternoon; the machine's load average was 35–50 on 2 cores for the last hour, so the
  long runs below were cut — said plainly):
  - `api/tests/test_ii5.py` **18 passed**; with `test_f3.py`: 44 passed, 1 failed —
    `test_fictional_league_prices_and_solves_with_k_and_def[nfl_wide]`, which fails the same on `wt-base` (the Sunday
    lock). `test_ii5` + `test_i0b` + `test_i0c` + `test_f3::test_leagues_by_username`: 62 passed (before the load).
    The targeted set (`test_ii5, f3, auth, i0b, i0c, ic3, ih1, myweek, ig3, ic2`) under load: 113 passed, 51 skipped, 2
    failed — both `PoolTimeout` (Postgres had stopped); re-run with it up: green.
  - **The whole API suite** (`cd api && PYTHONPATH=. uv run pytest -q --deselect tests/test_u1.py --deselect
    tests/test_ig2.py`, 589 collected): **cut at 372 of 589 (63%) by the hand-back time** (a first run under load 35–50
    was abandoned at 12%). Through those 372: 317 passed, 6 skipped, **49 failed — every one run by id on `wt-base`**:
    46 fail there too — the Sunday-afternoon locks (`test_anyleague` 1, `test_decisions` 7, `test_f3` 1, `test_h1` 1,
    `test_i0a` 2, `test_ib0` 8, `test_ib2` 2, `test_ic2` 2, `test_ic4` 3, `test_ie0` 1, `test_ie1` 5, `test_ie2` 5,
    `test_ie_po` 1, `test_if2` 5, `test_if4` 2); the other 3 (`test_ic1.py::test_dads_league_week_1_units_and_the_named_miss`,
    `::test_dads_league_week_2`, `test_ic_po.py::test_scoring_check_without_play_by_play_is_exact_on_the_ten_yard_cut`)
    pass on `wt-base`'s `league_lab` and are the brief's three known clone failures (no `*_tds_10p` columns on
    `league_lab_i0b`). **Delta against `wt-base`: 0** through 63%; the last 217 tests were not run (none is II-5's).
  - Root suite: not run (load). II-5's root change is one additive block in `platforms.py`; no root test imports it.
  - Lint: `ruff check` on every Python file II-5 touched — clean (the tree-wide run was cut by the load after reporting
    only test_ii5's import order, fixed). Web: `npm run typecheck` (svelte-check + tsc) 0 errors, 0 warnings; `eslint`
    on the nine changed web files clean (the full `npm run lint` passed at 15:50, before the last two small edits);
    `npm run build` ok.
  - e2e (`FIXTURES_PORT=8626`): **`e2e/ii5` 12 passed** (6 × phone at 375 / desktop at 1300), with `e2e/i0b` + `e2e/ic4`:
    20 passed. The other specs with the platform click (`i0c, ic3, ie0, ie2, ig3, ih2, ih3, v2, fixtures.spec.ts`): 81
    passed, 7 failed under load (60 s test timeouts, a browser launch over 180 s) — **the 7 re-run: 7 passed**.
    Screenshots: `web/e2e/.out/ii5-*.png` (the Sleeper error, the Sleeper link card, the MFL error, the MFL team picker;
    phone and desktop).
* **What moved and why**: no number moves. Words: the unknown-username sentence (API and web), the MFL private-league
  sentence (keeps "Ask the commissioner to allow API access"), the MFL label ("Find your MyFantasyLeague league"), the
  Sleeper label ("…, or a league link"), the no-team row ("pick the team to see below"), League's moves on MFL.
  Behaviour: the MFL box shows only after choosing MyFantasyLeague (one more tap than before; a device with saved MFL
  leagues and no Sleeper username opens on MFL).
* **Not done**: accounts (design only, by the brief); ESPN / Yahoo adapters (verdicts only); MFL's per-league API key as a
  private-league path (documented in PROVIDERS, not built); the capability lines on screens other than League's moves
  (My Week's win line — "this league's live scores are not read yet" — and Waivers' claim time on MFL already state their
  gaps in their own words; not rewired to `gapLine`); the whole API and root suites to the end (load; see the evidence).
* **Next task**: when Andrew wants saved leagues across devices — build ACCOUNTS.md's option A (the email link, the
  `accounts` schema, the import of a device's guest picks); then Yahoo (apply, OAuth connection) if there is demand.

**For the PO**
1. **Merge order**: anywhere after INF-1. Conflicts to expect: `main.py` (II-5's NotFound handler line and `?sleeper=`
   param; the 502 / 503 handlers gain `code`), `League.svelte` (one import, one effect, the moves card's first branch —
   II-4 edits other lines there), the ten e2e specs (one added line each, near the start of an MFL test).
2. **INF-1's GA**: the setup screen's events are INF-1's (`login` etc.); `platform` is already an event param there. No
   username or league id is sent by II-5.
3. **ESPN's terms bear on what is shipped**: Disney's terms (read today, quoted in `docs/ESPN_TERMS.md` and
   `PROVIDERS.md`) forbid automated access and commercial use; the news line and the injury overlay read ESPN's public
   feeds. Fine to keep for the free beta as a known risk; a decision before anything is charged for (`LEAGUE_LAB_NEWS=off`,
   `LEAGUE_LAB_AVAILABILITY=off` switch them off).
4. **Decisions Andrew may want to reverse**: ESPN and Yahoo are named on the setup screen as "not supported yet" (rather
   than hidden); the platform choice gates the MFL box (one more tap for MFL users; remembered after the first time);
   the sign-in recommendation (email link over Google first).
5. Nothing for dbt, workflows, render.yaml or Neon in this package.

### II-4 2026-10-04 — the copy standard, Season's three views, news as a decision-impact feed, the presentation (branch `dev/II4`, database `league_lab_ia3`, read only)

* **Task / plan**: Wave I-I brief § II-4; the fifth review (`docs/reviews/2026-10-04-product-and-analytics-handoff.md`)
  § 5 (metric dictionary and copy standard), § 6 (Season), § 7 (news), § 8 (home, Waivers, Team, League, the card).
  Branch `dev/II4` from `main` `94ed33c`.
* **Delivered**
  1. **The copy standard** — `docs/WORDS.md` § "The copy standard" (II-4 owns it): rates say **per game / per target /
     per route run / per attempt / per carry / per week**; every rate names its denominator and aggregation (summed ÷
     summed over the same games); windows say games played vs calendar weeks; the help layer carries sample, source,
     coverage, refresh; shares say share of what; expected vs projected points. The review's table, each label with
     its numerator ÷ denominator, how it adds up, and **what we have** (verified present / proxy, unavailable
     in-season / derived / planned — RB backfield carry share is planned, route metrics are the participation proxy
     ending 2025). **The sweep**: `scripts/copy_standard.py` (idempotent; `--check` exits 1 while any rate phrasing is
     left; a line can opt out with `<!-- copy-standard: keep -->`, used only by WORDS.md's "Never" examples) rewrote
     106 lines in 47 files — headings, labels, tooltips, captions, generated sentences (the API, the console, the web)
     and the tests that pin those words (`api/tests/test_ia1/ia2/ia3/research`, `tests/test_matchups/m5/waivers*`,
     `web/e2e/fixtures.spec.ts`, `ia1`, `ia3`, `if4`). **Kyren's "Carry share"** tile has its definition on the card
     (`lib/card.ts` TILE_DEFS, marked: his rush attempts ÷ the team's, summed over his games, every rusher, kneel-downs
     not removed; "Target share" and "Passes / game" too).
  2. **Season: three named views** (`ondemand.season_view`, `# ---- II-4`; `Ros.svelte` + `lib/ros.ts` marked blocks).
     **My roster outlook** (default with a team; `view=outlook`), **Potential upgrades** (`view=upgrades`, before
     acquisition cost; `who` = all / fa / others), **Rest-of-season projections** (`view=projections`). Each answer has
     `season_view = {key, label, counterfactual, costs_included, costs_not_included}`; the page says the counterfactual
     under the answer and, for upgrades, "Not included: the drop a free agent needs, the players a trade sends, a
     waiver claim that might be lost." **The arithmetic is IB-3's / F2's unchanged** (a test compares every row).
     Outlook rows gain **contingent injury cover** (`cover`: his bench weeks' edge over the best free agent at his
     position, per week; never added to the value; null when unknown); upgrades rows gain `acquire` (a free agent →
     `/waivers?add=`; a rostered player → `/trade-calc?partner=&get=`), so a hypothetical starter-point gain is never
     called trade value. Projections show **per game** (from 640 px), games, range, playoffs. `view=lineup` / `points`
     answer as before. The web's projections tab asks the plain `/api/ros` path (cache and every saved answer keep
     working) and says the API's words from `PROJECTIONS_VIEW` (a test pins them equal).
  3. **News as a decision-impact feed** (`myweek.decision_feed` / `decision_parts` / `clocks`, `# ---- II-4`; one
     marked line each in `my_week` and `ondemand`'s My Week). Every "What changed" line gains `what_changed` {text,
     source, event_at, published_at, checked_at}, `why_here`, `decision_status` (changed / watch / none, with
     `decision_words`), `forecast_status` (included / contextual / pending, with `forecast_words`), `next_step`,
     `item_kind` (development / recap) and `priority`; lines are ranked changed → watch → none, recaps after every
     development, the same event once. **"Included" only with a recorded update**: the overlay's applied status change
     (`availability` `changes`) — or the report already in the rows (an unplayable player's injury item is reflected,
     never counted twice); a headline, a brief, a Questionable tag, a recap are **context only** (IF-3's
     `forecast_treatment` model: the projection reads no news); an injury item published after the last injury check
     is **update pending**. The defensive-personnel rule is IF-3's, untouched. **The clocks** (`/api/my-week` `clocks`
     = data_built / injuries_checked / news): the footer reads "Data built 1 d ago · Injuries checked 3:45 PM ET · News
     1 d ago ›" with the exact times on tap — stamps, never a warning; the header's "⚠️ Injury news may be stale"
     (`/api/status` `warning`) is off too (`SHOW_STALE = false`, the PO's I-H call extended). The card's news line says
     "· context only, not in the projection" (`NewsLine.svelte`).
  4. **The home's order** (`MyWeek.svelte`, `<!-- ---- II-4 -->`): the decisions (actions, "No clear upgrade") → What
     changed (each item: the decision chip, the sourced fact with its time and a "More" for the rest, why it matters
     here · the forecast status, the next step; game recaps under their own heading) → the lineup's status (the set
     line, where to change it) → the lineup. A long action explanation (the alternative drops) shows its first sentence;
     the rest is behind "More" (`lib/feed.ts splitLead`).
  5. **Waivers** (`Waivers.svelte` marked block, `lib/feed.ts`): each top claim carries its horizon — **Helps this week
     (+8.3)** / **Covers a bye in week 7** / **Helps from week N** / **Upside stash: no lineup gain yet**; the intro is
     built from them ("The three strongest claims below: 2 help this week, 1 covers a bye (week 7). Each card's total is
     its gain over weeks 4–7." — the API's "each with what it adds this week" is no longer shown when top claims
     exist); claims that drop the same player (or the API's `alternative_to`) are named: "Wan'Dale Robinson and Tyler
     Allgeier compete for the same roster spot (each drops Jacory Croskey-Merritt): claim one of them."
  6. **§ 8's words**: Team "Depth (bench lineup)" with "best legal lineup from the bench" and the how-to's definition
     (usable depth, not raw bench points), "per week left on the bench (hindsight)"; League "Past luck says nothing about
     the weeks left: they depend on your points and the schedule ahead." (was "It evens out over a season") and "Points
     left on the bench (hindsight)" with its how-to line; the card's role line "Upside: no additional modeled upside
     scenario available." (`player.py`, marked, and the console's `0_Player.py`); the console's Team Hub and League
     how-to lines the same (marked).
* **Interfaces** (INTERFACES.md § II-4, 15:40, as built): `/api/ros?view=outlook|upgrades|projections` + `season_view`;
  rows `lineup_start_weeks`, `cover`, `acquire`, `lineup_sid`, `lineup_owner`, `ros_per_game`; `changed.lines[]`'s
  five parts + `item_kind` / `priority`; `/api/my-week` `clocks`. `lib/api.ts` one `// ---- II-4` block (+ the
  `RosList.view` union widened on IB-3's line, marked).
* **Files**: `api/league_lab_api/{ondemand,myweek,player}.py` (marked blocks / lines), the sweep's lines in
  `api/league_lab_api/{about,decisions,research,why}.py`, `app/Home.py`, `app/lib/{charts,matchups}.py`,
  `app/pages/{0_Player,1_Team_Hub,3_Trends,4_Rankings,5_Matchups,6_Trade_Finder,8_League,9_Players,10_Receivers,
  11_Kickers}.py`, `app/whats_new.md`, `src/league_lab/{scoring,signals,validation}.py` (comments / sentences only);
  `web/src/lib/{feed.ts (new),ros.ts,card.ts,api.ts,research.ts,about.ts}`, `web/src/routes/{Ros,MyWeek,Waivers,Team,
  League,Compare,Trends,Receivers,Players,Trades,About}.svelte`, `web/src/components/{NewsLine,GameLog}.svelte`;
  `api/tests/test_ii4.py` (new), `web/e2e/ii4/fixtures.spec.ts` (new), `web/fixtures/ii4/api_ii4.json` (new, recorded),
  `web/e2e/fixtures.ts` (marked: outlook / upgrades served from IB-3's saved lineup lists), `web/e2e/{fixtures.spec,
  ib3/fixtures.spec}.ts` (the new view names), `web/fixtures/mfl/api_70587{,_ic4}.json` (one alias key each:
  `view=outlook` = the recorded `view=lineup` answer, yours only); `scripts/copy_standard.py` (new);
  `docs/{WORDS,METRICS,DESIGN}.md`.
* **Commands and evidence** (the sandbox ran at a load average of 35–52 from 16:00 — seven developers' suites at once
  on 8 GB — so the whole-suite runs could not finish inside the time box; what ran is listed as it ran):
  * `api/tests/test_ii4.py` — **12 passed, 1 skipped** (the recorder) at 15:45, before the Sunday 4:05 PM kickoff of
    Jefferson's game. After 16:05 ET `test_my_week_feed_on_the_overlay_fixture` fails exactly as IF-4's
    `test_what_changed_from_the_overlay_fixture` does on `main`: Jefferson's game has started, the overlay never moves a
    locked player, so the fixture's "Jefferson is out" status line is not produced (the Sunday-afternoon clock; INF-1's
    pinned clock — Saturday 16:00Z — restores both). The rest of the file does not read the clock.
  * **The API files my changes reach** (`test_ii4 if4 ih2 ib3 ia3 ia1 ia2 research myweek player n1 n2 ic4 i0a f3`,
    16:36–17:17 at load ~40): **222 passed, 15 failed, 3 skipped, 3 xfailed**. The 14 failures that are not mine,
    re-run on a `main` worktree (`94ed33c`, same database, 17:10–17:24): **all 14 fail on `main` identically**
    (`test_if4` ×2, `test_ih2::test_the_console_twin_says_what_the_api_says`, `test_myweek` ×3, `test_player` ×2,
    `test_ic4` ×3 — incl. `test_value_to_my_lineup_counts_units_against_the_wire`, the same `{'mfl:0675','mfl:0714'}`
    on both —, `test_i0a` ×2, `test_f3[nfl_wide]`); the 15th is `test_ii4`'s overlay test (the clock, above).
    **Delta against `main`: 0 regressions.**
  * The whole API suite (`--ignore test_u1 test_ig2`) was started on this branch and on a `main` worktree
    (`94ed33c`, the same database `league_lab_ia3` — `wt-base` is 66 commits behind `main` and reads `league_lab`, not a
    like-for-like base) at 15:58; `main`'s run was stopped at 16:28 after 34 tests, this branch's at 16:36 after 50.
    In the 34 both ran: the same two failures (`test_anyleague::test_latency_cold_and_warm` ×2 — a timing test at a
    load of 40) plus, on `main` only, `test_decisions::test_waivers_on_demand_reproduce_every_mart_move[dynasty]`
    (passed here), and `test_decisions::test_waivers_route_on_demand_matches_the_house_route` on both. Tests 35–50,
    reached on this branch only, failed in `test_decisions` (`trade_evaluate_reproduces_the_trade_finder` ×2,
    `partners_are_the_pages_sweep` ×2, `team_reproduces_the_roster_marts[&source=sleeper]` ×2, `latency_cold_and_warm`)
    — the on-demand-vs-house reproductions that the kickoff locks break (the brief's ~45); this branch changes no
    decision arithmetic (two f-string words in `decisions.py`, and the console's twin the same). **Those ids on the
    `main` worktree at 17:10: all 7 fail there too** (with IF-4's two overlay / roster-6 tests: 9 failed, 6 passed —
    the same as this branch). **No full-suite delta against `main` could be measured in the time box — the PO's
    integration run (with INF-1's clock) is the count of record.**
  * Every failure seen on this branch, checked on `main` (same database, same hour): `test_ih2::
    test_the_console_twin_says_what_the_api_says` fails on `main` too (the console caption "Upside stash: his role is
    growing …" vs the expected "Upside stash · watch, no claim yet" — pre-existing); `test_if4` ×2 and `test_decisions`
    ×7 above fail on `main` too; `test_ii4`'s overlay test is the new member of the clock class. **Delta on the ids
    checked: 0 new failures, +1 clock-dependent test of my own.**
  * Root: `tests/test_matchups.py test_waivers.py test_waivers_if1.py test_waivers_ig3.py` — **152 passed**
    (`test_m5.py`, whose only change is a docstring, did not finish under the load). `uv run ruff check src app tests
    api` — clean (before the last commits; the later ones touch no Python but `scripts/`).
  * Web: `npm run typecheck` (svelte-check, `--fail-on-warnings`) — **0 errors, 0 warnings, 160 files**; `npm run build`
    — ok; `eslint` on the 23 touched files — clean after one fix (an unused argument in the new spec); the full
    `eslint .` did not finish under the load. **`e2e/ii4` — 8 passed** (phone 375 / desktop 1300: the three views and
    their words, the feed's five parts and the order, the clocks, Waivers' horizons and competing claims, Team / League
    words; screenshots `e2e/.out/ii4-*`). The older specs that pin Season's names were updated (`fixtures.spec.ts`,
    `ib3`) and re-run with `ia3 ic3 ic4 if4 ig2 ih1 ih2 i0a ie1 ib2 n1 n2 ig3`: 14 passed before the batch was stopped
    for load; `fixtures.spec.ts` "a stranger …" failed on the projections table's new **Per game** header (fixed in
    the spec: the header list gains "Per game"; its re-run at 17:25 timed out at the sign-in step, before the Season
    step — load); "every screen in light / dark" and `i0a` hit the 60 s test timeout at that load (1.2 / 3.2 / 2.0 min)
    — **not re-verified quietly: the PO's e2e run is the check** (`fixtures.spec.ts`, `ib3`, `ic3`, `ic4` read the new
    Season names / keys).
  * The acceptance grep — no rate phrasing left in headings, tooltips or generated text:
    `uv run python scripts/copy_standard.py --check` → exit 0 (nothing left); and
    `grep -rniE "\b(points|targets|carries|yards|touchdowns|times|catches|receptions|expected) a (game|target)\b|[}0-9)%] a (game|target)\b|a team a week" --include=*.py --include=*.svelte --include=*.ts api/league_lab_api app src/league_lab web/src | wc -l` → **0**.
    (Before the sweep the check listed 106 lines in 47 files.)
* **What moved and why**: **no number** — Season's three views read IB-3's and F2's values (`test_ii4` compares every
  row of outlook / upgrades with `view=lineup` and projections with `view=points`); `ros_per_game` is a new derived
  column (ros_points ÷ ros_games), `cover` a new contingent number kept apart. Words moved: the copy standard (106
  lines), Season's labels and counterfactuals, the feed's statuses, the Waivers intro (the API's "each with what it
  adds this week" is no longer shown when the top claims exist — Scrubs roster 2's third claim, Allgeier, adds 0 this
  week and covers the week-7 bye), Team / League / card words. The order of "What changed" lines can move (changed →
  watch → none; recaps last; IF-4's order kept within each).
* **Not done**: a RB backfield carry share (planned in the table, not computed); the help layer's sample / coverage /
  refresh on every rate (the rule is written; the Stats Explorer — II-3 — is where the columns get them); the console's
  Season page has no three views (the console has no "Value to my lineup" either); the drawer call on the feed's "next
  step" link (it links the full player page / Compare — II-2's swap is one line at `changed-next`); the news item's
  `next_step.kind = "matchup"` is defined but not produced yet (no item is about a defense today).
* **Next task**: with INF-1's clock, re-run the whole API / root / e2e suites for the count of record; give the feed's
  "Inspect" link II-2's `openPlayer`; let II-3's Stats columns carry the WORDS.md table's definitions as their tooltips.

**For the PO**

1. **Merge order**: after II-2 (the drawer swaps touch `MyWeek` / `Ros` / `Waivers` / `Team` / `League` at the player
   links — my edits there are marked `<!-- II-4 -->` blocks away from the link markup) and after II-0 / II-1 / II-3.
   **Then run `uv run python scripts/copy_standard.py`** — it rewrites any "points a game" a merged branch brought in
   (idempotent; `--check` for the grep). If my sweep commit (`0eb4045`) conflicts, drop its hunks and re-run the script:
   it is the whole sweep.
2. **Re-records**: `web/fixtures/ii4/api_ii4.json` (`II4_RECORD=1 … -k record_e2e`, before a Sunday 4:05 PM kickoff or
   with INF-1's clock). Two MFL recordings gained one alias key each (`view=outlook`); IC4 / IC3 re-records would
   produce them for real.
3. **The clock**: `test_ii4::test_my_week_feed_on_the_overlay_fixture` joins IF-4's overlay test in the Sunday-afternoon
   class (Jefferson locked after 4:05 PM ET); INF-1's pinned clock fixes both.
4. **The API's Waivers `answer`** (`decisions.py`, IE-1's block, not mine) still says "each with what it adds this week";
   the web no longer shows it when top claims exist. A one-line API change (or reading `lib/feed.ts topIntro`'s rule)
   would make the console and the API say the same.
5. **Decisions Andrew may want to reverse**: My roster outlook is Season's default (Value to my lineup over everyone
   is gone as one list); the header's "⚠️ Injury news may be stale" is off with the stale banner (`SHOW_STALE`, one
   line); the card's news line says "· context only, not in the projection" on every item; Waivers' intro replaces
   the API's sentence on the web.

### Integration 2026-10-04 — II-0…II-5 into integ/II

* **Branch** `integ/II` from `main` `94ed33c` (worktree `/home/claude/wt-integ`; `.env` → the main database `league_lab`,
  read only: nothing written, no dbt run, `api/tests/test_u1.py` and `test_ig2.py` deselected in every API run). INF-1
  (`dev/INF1`, the pinned clock and GA) is **not** in this branch.
* **Merge order** (`git merge --no-ff` each, the merge commit renamed "integ: merge dev/IIx (…)"; `uv run ruff check src
  app tests api` and `npm run lint` (eslint + svelte-check + tsc; the package has no `check` script — `lint` runs the
  typecheck) green after every merge): **II-0** `80306a9` → **II-1** `9ea7b92` → **II-2** `93e7238` → **II-3** `fe6553a`
  → **II-5** `64002dc` → **II-4** `8f0550f` (last: the sweep), then three fix commits (`159f847`, `2f852c2`, `48ff411`).
  All six dev tips are ancestors of `integ/II`; nothing rebased, nothing force-pushed, `main` untouched.

**Conflicts and how they were resolved**

| Merge | File | Resolution |
|---|---|---|
| II-0 | — | clean |
| II-1 | `src/league_lab/trades.py` (`__all__`) | II-1's names kept in the list; II-0's `week_story` block after it (its own `__all__ += ["week_story"]`) |
| II-1 | `api/league_lab_api/decisions.py` (`partners()`) | II-0's `story` loop, then II-1's card / threshold block: every Finder row carries both `story` and `card`; IF-2's order and `rank` unchanged |
| II-1 | `web/src/lib/api.ts` | both end blocks (the two `PartnerRow` declarations merge in TypeScript) |
| II-1 | `docs/WORDS.md` | both sections (II-0's "The calculation audit", II-1's "Credible trades") |
| II-1, II-2, II-3, II-5, II-4 | `docs/STATUS.md`, `CHANGELOG.md` | `keepboth.py` (one `## Wave I-I` heading, one CHANGELOG heading, six sections / bullets) |
| II-3 | `web/src/lib/api.ts` | II-0 + II-1 blocks, then II-3's |
| II-5 | `docs/WORDS.md` | both (II-5's "The setup flow and the platforms" after II-1's) |
| II-4 | `web/src/routes/Team.svelte` ("How to read") | II-4's "Depth (bench lineup)" line + II-0's "By slot" line |
| II-4 | `web/src/routes/Players.svelte` (2 hunks), `web/e2e/fixtures.spec.ts` (1) | II-3's rewritten Stats screen and its assertion kept (they already say "per game"); II-4's three edits were to the old screen's lines |
| II-4 | `web/src/lib/api.ts`, `docs/WORDS.md` | both (II-4's copy standard after the II-0 / II-1 / II-5 sections) |

Checks after the last merge: `scripts/copy_standard.py --check` → 0 lines left (no re-sweep needed); every branch's
`II-x` markers survive in every file it touched; every line any branch added is in the result verbatim except II-4's
three superseded `Players` / `fixtures.spec` lines; `dbt/` changed only by II-3's 8 seed rows (70 rows, 7 columns, no
duplicates); `render.yaml`, `Dockerfile`, `.github/` untouched (`app/pages/*` changed only by II-4's console sweep).
Interfaces held: `/receivers` → the WR/TE preset with the role cards at `/receivers?view=cards` (II-3's redirect beside
II-2's one-promise lazy screens in `App.svelte`); II-3's Players links keep IB-1's `paneLink` line, which opens II-2's
drawer, and every other `/player/` link goes through II-2's router hook (incl. II-4's feed "Inspect" link); II-0's
`strength_by_slot` / `week_story` and II-1's `card` on the same partner rows (`partnerReason` still reads `story`).

**Fix commits** (each the smallest change; the failures exist on the dev branch alone except where said)
1. `159f847` `src/league_lab/lineup.py` `replacement_chain` (II-0's block, one line): `enters` is None when his slot's
   chain ends empty. **dev/II0 alone fails** `tests/test_v1.py::test_close_calls_are_the_cards_decisions[0…11]` (12;
   II-0's root run reached 394 of 1,138, so it was never run): with two players tied at 0.0 (two DEFs) the re-solve
   swaps them, the "second path" loop recorded the swap as an `enters`, and `cards.decisions` offered the other DEF as
   the RB's / Superflex's alternative (a starter nobody can replace is not a decision). 12/12 pass; `test_lineup_ii0`,
   `test_ii0` unchanged.
2. `2f852c2` three older e2e re-pinned to II-4's words — **dev/II4 alone fails them the same** (8: `decisions`
   waivers light / dark, `ie1` Waivers, `n2` ESPN item; phone + desktop): the Waivers answer is II-4's `topIntro`
   ("The three strongest claims below: 2 help this week, 1 covers a bye (week 7). Each card's total is its gain over
   weeks 4–7."), the card news line ends "· context only, not in the projection".
3. `48ff411` `e2e/ii2` Players — **dev/II2 alone fails the URL check the same** (the 250 ms search debounce lands
   after the drawer's history entry, and closing goes Back to the entry before it); the test now waits for `q=n`
   before the first open. Merge interaction: on II-3's taller Stats screen the names are scrolled to and the screen
   beside the drawer is narrower, so the exact pixel scroll is not kept on close (528 → 461); the test now asserts
   the row you opened from is in view.

**Suites** (Sunday 19:27–19:50 ET; the base is `/home/claude/wt-integ-base`, a fresh detached checkout of `main`
`94ed33c` with the same `.env` — `/home/claude/wt-base` is at `ad4040e`, 66 commits behind `main`, so I did not
compare against it)

| Suite | integ/II | main `94ed33c` |
|---|---|---|
| root `uv run pytest -q tests` | **2 failed**, 1,142 passed, 3 skipped | **2 failed**, 1,117 passed, 3 skipped (the same two ids) |
| API `PYTHONPATH=. uv run pytest -q --deselect …u1 --deselect …ig2` (same minutes) | **55 failed**, 561 passed, 13 skipped, 3 xfailed | **54 failed**, 506 passed, 11 skipped, 3 xfailed |
| ruff | clean | clean |
| web `npm run lint` (eslint + svelte-check + tsc) | 0 errors, 0 warnings (163 files) | 0 / 0 (159 files) |
| web `npm run build` | ok (188 modules) | ok (184 modules) |
| e2e fixtures, the whole set (`FIXTURES_PORT=8630`) | **325 passed, 0 failed**, 1 skipped (`ih1` phone, by design) | 271 passed, 0 failed, 1 skipped (the same) |

* **Failing ids not in main's set**: API — one, `tests/test_ii4.py::test_my_week_feed_on_the_overlay_fixture` (new in
  II-4). The clock: dev/II4 alone fails it at the same hour on the same database (19:02 ET, beside IF-4's
  `test_if4.py::test_what_changed_from_the_overlay_fixture`, which fails on `main` too): Jefferson is locked after his
  4:05 PM ET kickoff, so no "changed" status line is produced — II-4's hand-back names it in this class.
  Root — none (both `test_my_week.py::test_my_week_is_the_mart[…]` fail on `main` the same). Main's 54 API failures
  all fail on `integ/II` too (none fixed, none new beyond the one). Before the fix commits: root 14 failed (the 12
  above), e2e 10 failed (the 8 + 2 above).
* The new tests: API +55 passed / +2 skipped (the branches' `test_ii*`; `test_ii0` skips "every starter is locked or
  has no reserve this hour" and its record mode), root +25 passed, e2e +54 passed (`e2e/ii0`…`ii5`).

**For the PO**
1. **Not resolved, noted** (each is the developer's, left as built):
   * II-0: the replacement chain's re-solve is not anchored to the lineup shown on ties — with two tied players the
     chain's *words* can still carry a phantom swap ("no legal move: RB goes empty; Rams (DEF) fills the open DEF;
     Chiefs (DEF) goes to the bench") on the player card / Team; fix 1 only stops it becoming the alternative. A
     follow-up: prefer the current seat on equal value in `_reseat` / the second-path loop.
   * II-2: closing the drawer goes Back to the entry before it opened, so any URL parameter written while it was open
     is dropped — Players' search typed less than 250 ms before tapping a name stays in the box but leaves the URL
     (a shared link then lacks it). `web/e2e/app.spec.ts` (live API, not run) still expects one tap → the full page.
   * II-4: the API's Waivers `answer` still says "each with what it adds this week" while the web shows `topIntro` —
     console / API and web say different things until one line changes; `web/fixtures/ii4/api_ii4.json` wants a
     re-record with INF-1's clock.
2. **dbt / hosted copy**: no model to build. II-3: `dbt seed --select metric_registry` (8 new rows) on the main database
   and for the nightly's hosted copy. Nothing for workflows, `render.yaml` or Neon from any branch.
3. **Env vars**: none new on the request path. II-5's `docs/ACCOUNTS.md` (design only, nothing built) names four for a
   future sign-in (`LEAGUE_LAB_RESEND_API_KEY`, `LEAGUE_LAB_MAIL_FROM`, `LEAGUE_LAB_SESSION_SECRET`,
   `LEAGUE_LAB_ACCOUNTS_DB_URL`). II-5: ESPN's terms bear on the shipped news line and injury overlay
   (`LEAGUE_LAB_NEWS=off`, `LEAGUE_LAB_AVAILABILITY=off` switch them off) — a decision before anything is charged for.
4. **INF-1 next**: merge `dev/INF1` onto `integ/II`, then re-run the whole API / root / e2e suites for the count of
   record — its pinned clock should turn the clock class green (main's 54 and `test_ii4`'s overlay test). A dry run
   of `dev/INF1` (`a9de549`) onto `integ/II` (aborted) conflicts only in STATUS / CHANGELOG; the II branches add no
   new `datetime.now` / `now()` read in Python for its sweep to miss. II-5 asked to go after INF-1; it went before it
   here with no conflict on its side.
5. **Decisions Andrew may want to reverse** (from the hand-backs): II-0 — an empty slot counts 0 in the league
   population; RB1 = the better RB starter, not Sleeper's slot order. II-1 — the K / DEF guardrail's exception is
   "they have nobody there" only; a trade must beat the other team's best waiver move too (margin 1.0), so the house
   league shows "No compelling trade found" most days; the cold on-demand Finder is ~7 s slower (10.1 → 17.7 s).
   II-2 — every player link opens the drawer (names in sentences and Compare too); Add to compare waits for a second
   player. II-3 — snap share is the mean of per-game shares; carry share keeps scrambles / kneels; Players opens on
   Stats. II-4 — My roster outlook is Season's default; the stale header line is off with the banner; every card news
   line says "context only"; Waivers' intro replaces the API's sentence on the web. II-5 — ESPN / Yahoo shown as "not
   supported yet"; the platform choice gates the MFL box; the email-link sign-in recommendation.

### INF-1 2026-10-04 — the pinned clock for the suites; Google Analytics 4 (branch `dev/INF1`, database `league_lab` read only)

* **Task**: INF-1 (brief § "INF-1"; two PO items riding with the fifth review: "Sunday afternoons turn ~45 API tests
  red on any branch" and Andrew's "I logged into my google analytics for you to create tracking on this"). Plan
  sections: § 17 (Iteration 19); HOSTING § "Usage" → "Google Analytics" (new).
* **1. The clock** — `src/league_lab/clock.py` (new): `now()` = an in-process `pin(...)`, else `LEAGUE_LAB_NOW` (ISO
  8601; `Z`, any offset converted, naive taken as UTC; read on every call), else `datetime.now(UTC)`; always aware UTC.
  `pin(when)`, `unpin()`, `with pinned(when):` (restores the previous pin, also after an error), `is_pinned()`,
  `parse(s)`, `now_floored(step_minutes=5)` (for a value inside a cached SQL query: kickoffs sit on five-minute marks).
  **Call sites moved to it** (each a marked `# ---- INF-1` line): `anyleague.lineup_rows` / `opponent` /
  `league_weeks` (the brief's three), `decisions._moves_on_demand` / `_house_fa_pool` / `waiver_deadline` (the brief's
  three), `player.player_card`'s lock line and its console twin `app/pages/0_Player.py` (parity test), `lineup.build`'s
  `as_of` default, `events.clock`, PlayerWire's `for_card` / `recent` defaults, `app/lib/ui.first_open_week` (the
  decision week), `app/lib/cards.LINEUP_SQL` (`kicked_off` was the database's `now()`; now a parameter,
  `now_floored()`). **Kept on real time**: `freshness.py` (IH-1's stale rule keeps its own injectable `now`; its
  tests pass unchanged), `availability.checked_at` and every fetch stamp, `usage`, `auth`, `run_at` of the writers,
  the nightly writers (`lineup.lineups`, `write_record`), Streamlit's `freshness_banner`, the poll interval.
* **2. The suites pinned** — `tests/conftest.py` and `api/tests/conftest.py` (`# ---- INF-1` blocks): `PINNED_NOW =
  "2026-10-03T16:00:00Z"` (the PO's guess, kept: Saturday, week 4's Thursday game played, nothing else) set with
  `os.environ.setdefault("LEAGUE_LAB_NOW", …)` at import, so the Streamlit twin (a subprocess) reads the same moment
  and a shell that sets it wins; an autouse fixture unpins after every test; `real_clock` fixture (no pin, no env) for
  a test that needs the wall clock. Tests' own SQL that used the database's `now()` takes `clock.now()` as a parameter
  (`api/tests/test_anyleague._kicked_off_since`, `api/tests/test_myweek.current_week` / `mart`,
  `tests/test_my_week.test_my_week_is_the_mart`). IH-2's three `xfail(strict=False)` MFL pins (`api/tests/test_ih2.py`)
  are plain tests again — they pass. No test needed a moment of its own beyond the suite's: `test_inf1` pins Sunday
  17:30Z / Thursday 00:00Z inside `with clock.pinned(...)` to prove the routes follow the clock.
* **3. Google Analytics 4** — `web/src/lib/analytics.ts` (new), `GA_MEASUREMENT_ID = "G-HJWGHZ79BG"` and `GA_HOSTS` in
  `lib/brand.ts`. gtag.js is injected at runtime once, on first use, only after sign-in (never in `index.html`, never
  on the sign-in screen; GA's own `ga-disable-<id>` is on while the sign-in screen shows again);
  `config` with `send_page_view: false`, `allow_google_signals: false`, `allow_ad_personalization_signals: false`.
  Events (every one carries `league_key`, `roster_id`, `platform`, `release` = `/api/health` `version`, fetched once —
  the web held it nowhere): `page_view` per route change (path / league / team; `page_location` keeps only `league`
  and `team`), `screen_view` beside `countView` (App.svelte, the same dedup), `login` (App.svelte `signedIn`, i.e. the
  password accepted — `method: "password"`, never the password), `select_content` (the URL's `pane=`: IB-1's pane and
  II-2's drawer; or II-2's `openPlayer` calling `track(...)` — one open counts once), `edit_link_click` (a delegated
  click on `a[data-testid="edit-link"]`), `compare_open` / `waiver_view` (the route names), `trade_evaluate`
  (`lib/api.ts postEvaluate`: partner number, package sizes). **No PII**: ids only; never a username, team or manager
  name, a manager's player names, a password, a search box's text, another query parameter. **The switch**:
  `LEAGUE_LAB_GA` at build time (`vite.config.ts` `define` → `__LL_GA__`): `off` = dead code (no gtag URL in the
  bundle), `on` = always, unset = auto: only on isuckatfantasy.io / www and never under automation
  (`navigator.webdriver`) — dev, `vite preview`, the fixture e2e and the measure runs send nothing; an e2e forces it
  with `window.__llGa = "on"`. `web/public/sw.js` passes Google's requests through (same-origin GETs only); the API
  sends no CSP. About's usage sentence names Google Analytics and what it is sent (U-1's e2e text updated);
  HOSTING § "Usage" → "Google Analytics" (property 557285408, stream, events table, the switch, no PII, consent, the GA
  admin steps).
* **Decisions** (written down, not asked): (a) the product events are sent from code that exists on main in **shared
  places** (App.svelte, `postEvaluate`, a delegated click, the route names) instead of marked lines inside
  `Login.svelte` / `Trades.svelte` / `Waivers.svelte` / `Compare*` — those are II-5's, II-1's and II-4's files this
  wave, so the PO's merge touches none of them; the events are the same. (b) The env name is `LEAGUE_LAB_GA`, not
  `VITE_LEAGUE_LAB_GA`: only that one value reaches the bundle through `define`. (c) `playwright.fixtures.config.ts`
  is unchanged: it serves a prebuilt `dist/` with `vite preview`, where a build-time switch is a no-op; fixture runs
  are off by the auto rule, proven by `e2e/inf1`. (d) No cookie banner (PO call): the beta is password-gated and About
  discloses GA; a public launch needs Consent Mode and a banner. (e) `wt-base` is not a checkout of `main` (detached
  at `ad4040e`, 66 commits behind): the baseline below is a fresh detached checkout of `94ed33c` in the scratchpad
  (`scratchpad/inf1/wt-main`, same `.env`, same database), run in the same minutes.
* **Interfaces**: INTERFACES.md § INF-1 (the clock; the fixture names; the pinned moment; the analytics exports;
  `LEAGUE_LAB_GA`; the final note with the one line for II-2's `openPlayer`).
* **Files**: `src/league_lab/clock.py` (new), `src/league_lab/anyleague.py`, `src/league_lab/lineup.py`,
  `api/league_lab_api/{decisions,player,events,playerwire}.py`, `app/lib/{cards,ui}.py`, `app/pages/0_Player.py` (one
  marked line, the parity twin), `tests/conftest.py`, `api/tests/conftest.py`, `tests/test_clock.py` (new, 22),
  `api/tests/test_inf1.py` (new, 7), `api/tests/{test_ih2,test_anyleague,test_myweek}.py`, `tests/test_my_week.py`,
  `web/src/lib/analytics.ts` (new), `web/src/lib/{brand,api}.ts`, `web/src/App.svelte`, `web/src/routes/About.svelte`,
  `web/vite.config.ts`, `web/e2e/inf1/fixtures.spec.ts` (new, 5 × phone / desktop), `web/e2e/u1/fixtures.spec.ts`
  (the notice's text), `docs/HOSTING.md`, `docs/STATUS.md`, `CHANGELOG.md`.
* **Commands**: `cd api && PYTHONPATH=. uv run pytest -q --deselect tests/test_u1.py --deselect tests/test_ig2.py`
  and `uv run pytest -q tests --deselect …` on `dev/INF1` and on the `94ed33c` checkout, side by side, Sunday
  2026-10-04 22:42–22:56Z (6:42–6:56 PM ET: the 1 PM games final, the late games in progress);
  `uv run ruff check src app tests api`; `cd web && npm run lint && npm run build`; `FIXTURES_PORT=8627 npx
  playwright test --config playwright.fixtures.config.ts e2e/inf1 e2e/u1` (and the whole fixture suite). Nothing
  written to `league_lab` (reads only; `test_u1` / `test_ig2` deselected: they write).
* **Evidence — the suites on the main database, Sunday evening during games**:

  | Suite | `dev/INF1` (pinned) | `main` `94ed33c` (wall clock), same minutes |
  |---|---|---|
  | API (581 / 574 collected, 41 deselected) | **575 passed, 6 skipped, 0 failed** (592 s) | 506 passed, **54 failed**, 11 skipped, 3 xfailed (575 s) |
  | root | **1,141 passed, 3 skipped, 0 failed** (124 s) | 1,117 passed, **2 failed**, 3 skipped (125 s) |

  `main`'s 54 API failures (ib0 8, decisions 7, if2 5, ie2 5, ie1 5, myweek 3, ic4 3, player 2, ig1 2, if4 2, ic2 2,
  ib2 2, i0a 2, ih3 / ie_po / ie0 / h1 / f3 / anyleague 1 each) and its 3 xfails (IH-2's MFL pins) all pass on
  `dev/INF1`; 3 tests that **skip** on `main` while games are in (`test_anyleague::test_route_serves_the_same_week_on_demand`
  ×2, `test_ie_po::test_lineup_rows_say_what_the_call_says`) run and pass pinned (`main`'s other two skips are
  `test_static` without a `web/dist` in that checkout). `dev/INF1`'s 6 skips: four `test_record_e2e_answers` recorders
  (env-gated) and `test_ic3`'s two scoring read-backs (as on main). Root: `main`'s 2 failures are
  `test_my_week.py::test_my_week_is_the_mart` ×2 (the console's week vs the mart after the kickoffs). The three
  `*_tds_10p` scoring checks pass on `league_lab` (they fail only on the 2026-09-26 clones). The new tests:
  `tests/test_clock.py` 22 (pin / unpin / `pinned` restores after an error, ISO with `Z` / offsets / naive / bad,
  the env read on every call, blank env = unset, real UTC when unset, the stale rule not pinned, `now_floored`),
  `api/tests/test_inf1.py` 7 (the suite is pinned; `/api/waivers` `deadline` answers the pinned moment — Saturday:
  the claim run Wed 2026-10-07 07:00Z and the next kickoff Sunday's London game 13:30Z; pinned at 2026-10-08 00:00Z:
  the next Wednesday's run — and `/api/player`'s lock line: "not locked yet" Saturday, "Locked for week 4" pinned at Sunday 17:30Z;
  `/api/health` `age_hours` stays the real age; unpinned = the wall clock).
* **Evidence — web**: `npm run lint` (eslint + svelte-check + tsc) 0 errors / 0 warnings; `npm run build` ok;
  `ruff` clean; `e2e/inf1` **10 passed** (phone + desktop: `page_view` on navigation and Back with `page_location`
  stripped to league / team; `screen_view` with `league_key` 9000000000000000001, `roster_id` 3, `platform`, `release`;
  every parameter on an allow-list and no team / user names; gtag.js requested once; nothing — not even gtag.js — on
  the sign-in screen while the password is typed, wrong and right, then exactly `login`, `page_view`, `screen_view`;
  `select_content` from a lineup name (Back is not a new open), `edit_link_click`, `compare_open`, `trade_evaluate`
  (partner 1, 1-for-1), `waiver_view`; fixture mode by default: no gtag.js, no `dataLayer`; a `LEAGUE_LAB_GA=off`
  build has no gtag URL and sends nothing even with the override on); `e2e/u1` 4 passed; the whole fixture suite
  **281 passed, 1 skipped** (282, 6.1 min — GA is inert under automation, nothing else moved). No request leaves for
  Google in any test (every Google host intercepted, gtag.js a stub).
* **What moved**: no number. The clock changes which moment a test sees, not any arithmetic; in production
  `LEAGUE_LAB_NOW` is unset and `now()` is `datetime.now(UTC)` (a test).
* **Not done**: marked GA lines inside other devs' screens (decision (a)); the Dockerfile `ARG LEAGUE_LAB_GA`
  (PO-owned; only needed to switch GA off in production); GA custom dimensions and the enhanced-measurement settings
  (Andrew, in GA — below); a consent banner (decision (d)). `wt-base` was left as it is (others may rely on it).
* **Next**: once INF-1 is merged, every branch's suites are green at any hour on the main database; a new test that
  needs another moment uses `with clock.pinned(...)` — never the database's `now()` in its SQL.

**For the PO**
1. **Merge INF-1 first** (or early): every other branch's API suite turns green on a Sunday only with the clock.
   Conflicts to expect: `web/src/App.svelte` — II-3 adds an `$effect` right after the `countView` line, as INF-1 does:
   keep both blocks; `lib/api.ts` — INF-1's import at the top and one line inside `postEvaluate` (others append at the
   end); `About.svelte` — II-4 changes two StatTile captions, INF-1 the usage notice: no overlap; STATUS / CHANGELOG
   append-only.
2. **II-2's drawer** (optional, one line + import, `lib/player-drawer.svelte.ts` inside `openPlayer`, right after
   `emit(key, origin);`): `track("select_content", { content_type: "player", item_id: key, origin }); // INF-1` with
   `import { track } from "./analytics"; // INF-1`. Without it the URL's `pane=` already sends `select_content`; with
   it the drawer's origin (`drawer` for a swap from inside) wins and the URL path skips the same open. Nothing to add
   on II-0 / II-1 / II-3 / II-4 / II-5: `edit-link`, `postEvaluate` and the route names survive on their branches
   (checked).
3. **Andrew, in GA (once, Admin on property 557285408)**: Data streams → isuckatfantasy web → Enhanced measurement →
   turn off "Page changes based on browser history events" (else every route change counts twice), Form interactions
   and Site search; Custom definitions → event-scoped dimensions `league_key`, `roster_id`, `platform`, `release`,
   `origin`, `from`, `link_platform`, `screen_name`; Data retention → 14 months. Then DebugView after the deploy.
4. **Render**: nothing to set. GA sends from `isuckatfantasy.io` on the first load after the deploy. To switch it
   off: `ARG LEAGUE_LAB_GA` above `RUN npm run build` in the Dockerfile's web stage + `LEAGUE_LAB_GA=off` on Render.
5. **Decisions Andrew may reverse**: no cookie banner for the password-gated beta (About discloses GA); the pinned
   moment (Saturday 16:00Z: change `PINNED_NOW` in both conftests together, and only with a full run on `league_lab`).
6. `wt-base` is detached at `ad4040e` (66 commits behind `main`): refresh it before the next wave relies on it.
