# AGENTS.md — working agreement for League Lab

Read this, then `docs/HANDOFF.md` (the current handoff: state, task order, the traps),
`docs/PROJECT_PLAN.md` (what is built, what is next), `docs/STATUS.md` (current state and
evidence), and the task you were given. `docs/MVP1_PLAN.md` is the original
specification and remains the contract for scope, metric definitions and acceptance.

## Ground rules

1. **Verify before mutating.** Check the live schema (`league-lab status`, `psql`) and the actual
   source file columns before changing a loader or model. Upstream files drift between seasons.
2. **One writer.** Never run two ingestions or two `dbt build`s against the same database at once.
   `scripts/refresh.sh` takes a lock; respect it.
3. **Never join players by name.** Identity goes through `analytics.player_id_map`
   (gsis_id ↔ sleeper_id ↔ pfr_id). Ambiguities land in `player_id_quarantine`, not in a join.
4. **Denominators are independent.** Team totals come from `fct_team_game`, never from summing
   player rows. Numerator and denominator always share the same game window. Zero denominator → NULL.
5. **Unknown is not zero.** Missing snaps, missing charting, unsupported seasons: show
   NULL/"unavailable". The explorer must never display an unavailable metric as 0.
6. **Original events are preserved.** Raw tables keep full payloads (`payload jsonb`) and all
   upstream columns; analytical exclusions happen in dbt, never in the loader.
7. **Secrets and data stay out of git.** `.env`, `data/`, `backups/`, `logs/`, `.state/` are ignored.
   Check in placeholders only. Never paste secrets into handoffs.
8. **The seed `scoring_stat_map.csv` is generated** from `src/league_lab/scoring.py`
   (`tests/test_scoring.py` enforces it). Change the Python, regenerate the seed.
9. **Deprecations are deletions.** If a column or model is renamed, update every consumer
   (models, tests, app pages, docs) in the same change.

## How to make a change

```bash
make sync                      # deps from uv.lock (do not edit uv.lock by hand; use `uv add`/`uv lock`)
make pytest && make lint       # unit tests + ruff, no database needed
make build                     # dbt seed+run+test against your local database
make app                       # look at the pages you touched
```

Add a dbt test for every new key or rate. Add a row to `dbt/seeds/metric_registry.csv` for every
new metric (name, version, numerator, denominator, grain, status, notes). Update
`docs/METRICS.md` when a definition changes and bump the metric version.

## Handoff format (plan §10)

Every handoff includes: task ID (from `docs/PROJECT_PLAN.md`), plan sections touched, branch or
commit, exact files changed, input/output schema, commands executed, validation evidence
(test output, row counts, reconciliation numbers), data partitions touched, unresolved
limitations, and the next task. Update `docs/STATUS.md` in the same change.

## Suggested continuation prompt

> Read AGENTS.md, docs/MVP1_PLAN.md, docs/PROJECT_PLAN.md, docs/SETUP_RUNBOOK.md and
> docs/STATUS.md, then the assigned task's dependencies. Implement task ID __ only within the
> agreed contract. Verify current environment/source schemas before mutation. Preserve other
> workers' changes and existing data. Report changed files, tests, evidence, unresolved issues and
> next steps; update STATUS.md. Do not expand scope or claim completion without the acceptance
> evidence in plan §9.
