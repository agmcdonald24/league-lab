# Handoff — League Lab, 2026-09-27

For the next agent (Claude Code or any other) picking this repo up. Read in this order:
`AGENTS.md` (rules) → this file → `docs/PROJECT_PLAN.md` § Iteration 9 (the tasks) →
`docs/STATUS.md` (evidence) → `docs/METRICS.md` and `docs/DATA_MODEL.md` when touching a metric or mart.

## Where things stand

* Everything through **Iteration 8** is built, tested and committed: two Sleeper leagues side by
  side (`LEAGUE_LAB_SLEEPER_LEAGUE_ID=<reference>,<other>`), the Phase 2 play-by-play layer, the
  OLS baseline rankings with backtest, and **Projection v2** (per-league stat-line projections with
  a calibrated floor/ceiling, walk-forward validated 2021–2025). The app is live on Streamlit
  Community Cloud against a Neon Postgres that `make sync-hosted` refreshes; the Mac runs the
  nightly refresh (launchd 08:00) which now ends with `league-lab project` and the hosted sync.
* Two leagues: **League of Scrubs** (reference; 10 teams, half PPR, K + DEF) and **Forever Unclean
  Dynasty** (12 teams, superflex, full PPR, 6-pt pass TD, yardage and long-TD bonuses, no K/DEF).
  The reference league's scoring prices every NFL-wide mart (`points_current_scoring`); only
  Rankings v2 and the observed league points are per league. Closing that gap is task **S-01a**,
  and it goes first.
* Test agents walked every page on both leagues on 2026-09-26; every finding is fixed except the
  per-league pricing above (see `docs/STATUS.md` § "First live use with two leagues").

## The tasks, in order (details and acceptance in `docs/PROJECT_PLAN.md` § Iteration 9)

1. **S-01a** per-league observed points for the league pages (`fct_player_game_league`, re-key the
   per-game marts on `league_id`).
2. **U-10** scoring summary line (`dim_league_season.scoring_label`), raw diff in an expander.
3. **U-11** waiver shortlist ("adds worth a claim" vs your weakest starter / best bench, priced by v2).
4. **U-12** player card — usage, projection, availability, value on one screen; names link to it.
5. **M-05** start/sit on v2 with floor/ceiling tags; rest-of-season sums.
6. **M-06** drift strip on the Rankings page.
Then Iteration 10 (GitHub Actions nightly, publication contract, backup drill).

Do one task per handoff. Update `docs/STATUS.md` and `CHANGELOG.md` in the same change, add the
dbt test named in the acceptance column, and cite the task ID in the commit.

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
