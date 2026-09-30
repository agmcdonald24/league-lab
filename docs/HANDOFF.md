# Handoff — League Lab, 2026-09-29

For the next agent (Claude Code or any other) picking this repo up. Read in this order:
`AGENTS.md` (rules) → this file → `docs/PROJECT_PLAN.md` § Iteration 9 (the tasks) →
`docs/STATUS.md` (evidence) → `docs/METRICS.md` and `docs/DATA_MODEL.md` when touching a metric or mart.

## Where things stand

* Everything through **Wave A of Iteration 9** is built, tested and committed: two Sleeper leagues side by
  side (`LEAGUE_LAB_SLEEPER_LEAGUE_ID=<reference>,<other>`), the Phase 2 play-by-play layer, the
  OLS baseline rankings with backtest, and **Projection v2** (per-league stat-line projections with
  a calibrated floor/ceiling, walk-forward validated 2021–2025). The app is live on Streamlit
  Community Cloud against a Neon Postgres that `make sync-hosted` refreshes; the Mac runs the
  nightly refresh (launchd 08:00) which now ends with `league-lab project` and the hosted sync.
* Two leagues: **League of Scrubs** (reference; 10 teams, half PPR, K + DEF) and **Forever Unclean
  Dynasty** (12 teams, superflex, full PPR, 6-pt pass TD, yardage and long-TD bonuses, no K/DEF).
  Since **S-01a** (done 2026-09-27) league pages price every player in the selected league's own
  current scoring (`fct_player_game_league` → `mart_league_player_season` → availability, keeper
  facts, positional strength, league draft); the NFL research pages, defense vs position (and the
  Opp rank columns), the baseline formula and the projection features stay in the reference
  league's scoring (`points_current_scoring`) and say so.
* Test agents walked every page on both leagues on 2026-09-26; every finding is fixed, the
  per-league pricing last (S-01a; evidence in `docs/STATUS.md` § "S-01a").

## The tasks, in order (details and acceptance in `docs/PROJECT_PLAN.md` § Iteration 9b)

Wave A (S-01a, U-10, U-11, M-06) is delivered. **Wave B** builds the decision engine from
`docs/league-lab-next-iteration-2026-09-29.md`:

Round 1 (independent, in parallel): **B1** exact lineup service · **B5** decision record (frozen
projections, published drift) · **B6** GitHub Actions nightly — **delivered 2026-09-29** (`ba2c9c5`,
STATUS § "Wave B / PO merge and QA — round 1").
Round 2 (all consume B1): **B2** roster value and rankings · **B3** waiver engine · **B4** player
card + My Week — with the acceptance amended by Andrew's mobile review (plan § "Round 1 status and
Andrew's mobile review": answer-first cards, phone width, one projection, plain words). Then
Iteration 10, where the review added U-13 mobile pass, U-14 plain-language pass, U-15 model
explainer + honest importance, U-16 League consolidation, U-17 Receivers/Kickers context, R-14 CB
matchups, R-15 defense-vs-position picture, T-02 trade simulator, P-01 profiles + any league.

Do one task per handoff. Update `docs/STATUS.md` and `CHANGELOG.md` in the same change, add the
dbt/unit tests named in the acceptance column, and cite the task ID in the commit.

## How to work here

```bash
make sync                                   # uv, from uv.lock
make pytest && make lint                    # no database needed
make build                                  # dbt seed + run + test (migrate first)
make project                                # projection v2 for this season, then its marts
make backtest-v2                            # only when the model or its features change (~12 min)
make app                                    # http://127.0.0.1:8501
make sync-hosted                            # publish to Neon (drop-then-restore; ~2 min window)
```

Headless page check that catches most regressions before a browser does:

```python
# every page on both leagues; exceptions=0 everywhere or you are not done
import sys, pathlib; sys.path.insert(0, "app")
from streamlit.testing.v1 import AppTest
for league, team in (("1321941740235550720", "1"), ("1389709692405551104", "2")):
    for page in ["Home.py", *sorted(str(p.relative_to("app")) for p in pathlib.Path("app/pages").glob("*.py"))]:
        at = AppTest.from_file(f"app/{page}", default_timeout=180)
        at.query_params["league"], at.query_params["team"] = league, team
        at.run(); assert not at.exception, (page, league, [e.value for e in at.exception])
```

## Things that will bite you (each cost real time once)

* **Two leagues share seasons.** Never key anything on `season` alone; `dim_league_season` has
  `league_id` (one per league-season), `chain_id` (the newest season's id, for "this league's
  seasons") and `is_reference_league`. Pages get the league from `perspective()` in the sidebar
  and seasons from `season_picker(league_id)`; positions from `league_slots(league_id)` — the
  dynasty league has no K/DEF, hard-coded `["QB","RB","WR","TE","K"]` breaks it.
* **Streamlit drops `?league=&team=` on page navigation.** `perspective()` keeps the choice in
  `st.session_state` (URL > session > reference league). Any new page must call it.
* **`require_relations("x")` must name only relations the page reads as `analytics.x`.** The
  hosted sync derives what to publish from those references; `tests/test_app_guards.py` enforces it.
* **Missing cells**: `show()` passes `placeholder=""`; do not print NaN/None yourself.
* **Two scoring scales.** A league page reads points from `mart_league_player_season` /
  `mart_player_availability` / `fct_player_game_league` (the league's own scoring) — never
  `points_current_scoring`. The NFL-wide marts (`fct_player_game`, `mart_player_season`,
  `mart_player_recent_form`, `mart_player_expected_*`) stay reference-scored because the projection
  features read them; do not re-key them. `assert_reference_league_matches_nfl_marts` fails if the
  two sets of arithmetic drift apart. Do not name `analytics.fct_player_game_league` in page code
  unless a page reads it: the hosted sync publishes every relation the code names (≈52 MB more; `mart_league_player_season` is ≈8 MB).
* **Seeds are generated.** `scoring_stat_map.csv` comes from `league_lab.scoring.write_seed()`;
  `tests/test_scoring.py` fails if they diverge. Seeds always full-refresh (`+full_refresh: true`).
  Pricing anywhere in SQL goes through the `league_points(scoring_jsonb, alias, include_bonuses)`
  macro, with `zero_stat_columns(have)` to fill columns a relation lacks.
* **Projection v2 rules** (`src/league_lab/projections.py`): features must be available
  *in-season* (the routes proxy is not — the participation file arrives after the postseason);
  a quantile model on raw points collapses at P10 because a fifth of played weeks score 0 — the
  interval is a quantile of the *out-of-fold* miss around the priced line, conformally widened;
  hyperparameters are constants and a change is a new `MODEL_VERSION`; anything new must beat the
  baseline on `make backtest-v2` before the page prefers it.
* **Rules that never bend** (AGENTS.md): join players by `player_id_map`, never by name;
  denominators from `fct_team_game`, never summed players; unknown is NULL, never 0; raw payloads
  are kept; nothing keyed to Andrew's username; Andrew writes the newsletter — data packs only.
* **Hosted copy budget**: Neon free tier is 0.5 GB and the sync cannot hold two copies; today
  ≈ 300 MB. A new mart the pages read must be small or slimmed.
* **On the Mac**: Postgres 17 via Homebrew; `.env` holds the Neon owner URL (never commit it);
  `make sync-hosted` from the repo root; the launchd job logs to `logs/`.

## What Andrew wants from a handoff (AGENTS.md § handoff format)

Task ID, plan sections touched, exact files changed, commands run, validation evidence (test
output, row counts, reconciliation numbers, the headless page check, a browser walk on both
leagues), data partitions touched, unresolved limitations, next task. Honest, no varnish: if a
number is worse, say so and show it.
