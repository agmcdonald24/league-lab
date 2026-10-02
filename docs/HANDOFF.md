# Handoff — League Lab, 2026-10-02

For the next agent (Claude Code or any other) picking this repo up. Read in this order:
`AGENTS.md` (rules) → this file → `docs/PROJECT_PLAN.md` § Iteration 9 (the tasks) →
`docs/STATUS.md` (evidence) → `docs/METRICS.md` and `docs/DATA_MODEL.md` when touching a metric or mart.

## Where things stand

* Everything through **Wave A of Iteration 9** is built, tested and committed: two Sleeper leagues side by
  side (`LEAGUE_LAB_SLEEPER_LEAGUE_ID=<reference>,<other>`), the Phase 2 play-by-play layer, the
  OLS baseline rankings with backtest, and **Projection v2** (per-league stat-line projections with
  a calibrated floor/ceiling, walk-forward validated 2021–2025). The app is live on Streamlit
  Community Cloud against a Neon Postgres copy that **GitHub Actions' nightly** publishes (Wave H: the one
  writer); the Mac's launchd refresh (08:00) builds the local copy and no longer syncs to Neon.
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
card + My Week — **delivered 2026-09-30** (STATUS § "PO merge and QA — round 2"), with the acceptance amended by Andrew's mobile review (plan § "Round 1 status and
Andrew's mobile review": answer-first cards, phone width, one projection, plain words). Then
Iteration 10 as Wave C: round 1 (U-13 mobile pass + U-16 League consolidation, U-14 plain-language
pass + U-15 model explainer, R-13 kicker and defense projections) **delivered 2026-09-30**; round 2 (**C4** T-01 trade
evaluator + T-02 simulator · **C5** R-14 cornerback matchups + R-15 defense-vs-position picture + R-11 matchup
comparison · **C6** R-10 role alerts + R-12 scenario upside + U-17 Receivers/Kickers context) **delivered
2026-09-30**. Iteration 10 is complete apart from P-01 (profiles + any league), which needs a design note first.
**Iteration 12 (Wave D) delivered 2026-10-01: projection v3.0** (starting-QB inputs at QB, teammate-out inputs
at RB/WR/TE — every other candidate group was tested through the feature harness and dropped), the 50% range,
per-tier calibration, the win probability on the decision cards, and the front-end spike with its decision note
(`docs/FRONTEND_DECISION.md`). Next: Andrew's decisions on the front end and P-01; the weather backfill and
kicker-wind re-test; the Iteration 11 operations rows.

**Iteration 13 (Wave E) delivered 2026-10-02 — from a lab to a product** (Andrew's direction: a $4–5/month
tool the fantasy population would pay for): "Our record" (Sleeper's own projections archived before kickoff
and scored against ours — the record starts the first week the nightly pulls them; `make sleeper-projections`),
rest-of-season projections on Player / Rankings / Trade Finder, the any-league design and spike
(`docs/ANY_LEAGUE.md`: stat lines stored once, scoring applied per request; `/api/my-week` for any Sleeper
league id), and four more model tests (all dropped; two v3.1 leads in STATUS). **Next: Wave F**, the customer
app on the D7 stack (FastAPI + Svelte; Streamlit stays as the research console) — first step E3's proposal:
reference scorings + `ops.projection_lines` / `ops.projection_ranges`; then Wave G (accounts, payments, hosting,
one nightly writer). Andrew checks Sleeper's commercial terms before anything is sold.

**Iteration 14 (Wave F) delivered 2026-10-02 — the customer app, phase 1**: NFL-wide model outputs (`ops.projection_lines`
/ `_ranges` per reference scoring, `ops.kd_lines` / `_ranges`), the API for any Sleeper league (`/api/leagues?username=`,
on-demand My Week with the opponent, player card, rest of season, record; Sleeper client with caches + token bucket;
Dockerfile serving `web/dist`), the web app (username → picker → My Week → player → rest of season → record). Sleeper's
API terms: free for non-commercial use, a licence for commercial use — Andrew has asked; **Wave G** (accounts, Stripe,
hosting, one nightly writer) waits for the answer. Run it: `cd web && npm ci && npm run build`, then
`cd api && uv sync && uv run uvicorn league_lab_api.main:app --port 8581` → http://localhost:8581/.

**Iteration 15 (Wave G) delivered 2026-10-02 — the lab in the app**: the research (trends, matchups, players, receivers,
compare, game logs) and the decisions (waivers, trades, team hub, league) for any Sleeper league on demand, a design system
(`docs/DESIGN.md`: dark-first, team colors, the player card as the unit, an inline-SVG chart kit), every screen in the
web app, "About the numbers" (the model explanation + the record). Same run commands as Wave F.

**Iteration 16 (Wave H) delivered 2026-10-02 — the beta on a server**: the deploy kit (`render.yaml`, the Dockerfile,
`image.yml`, `scripts/smoke.sh`, `docs/DEPLOY.md`), the gaps (upside stash, buy low / sell high, About's "what it leans
on most", one-query rest of season, search for any league), one writer (GitHub Actions publishes the hosted copy; the
Mac's launchd builds locally only), the NFL-wide boards in the record, the hosted relation closure in
`scripts/hosted_relations.py`. **Next: Andrew deploys** (`docs/DEPLOY.md`); Wave I (accounts, Stripe) on Sleeper's licence.

Do one task per handoff. Update `docs/STATUS.md` and `CHANGELOG.md` in the same change, add the
dbt/unit tests named in the acceptance column, and cite the task ID in the commit. A release a
league-mate would notice also gets a plain-words entry in `app/whats_new.md` (Home's "What's new"), and
page copy follows `docs/WORDS.md`.

## How to work here

```bash
make sync                                   # uv, from uv.lock
make pytest && make lint                    # no database needed
make build                                  # dbt seed + run + test (migrate first)
make project                                # projection v2 for this season, then its marts
make backtest-v2                            # only when the model or its features change (~12 min)
make app                                    # http://127.0.0.1:8501
make sync-hosted                            # refuses on the Mac since Wave H (Actions publishes); LEAGUE_LAB_MAC_WRITES_HOSTED=1 overrides
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
