### IR-3 — releases and publication that cannot quietly break (the review's P1 4 and 5)

Branch `dev/IR3` from `main` `3dfa01d`; worktree `/home/claude/wt-ip1`; database `league_lab_im1` read only; the
scratch database `league_lab_ir3_sim` (the hosted stand-in, 198–433 MB during the drills, dropped at hand-back).

#### What is done

1. **The release gate.** `scripts/gate.sh` (python | web | all) and a `gate` job in `.github/workflows/image.yml`
   that the `image` job `needs:` — a red gate builds, pushes and deploys nothing (Render deploys only a commit whose
   checks pass). The decision suite runs with every database address pointed at a closed port and **fails on a
   skip**; at least 750 tests must run (798 do). Root (780): `test_trades`, `test_trades_ii1`, `test_roster_value`,
   `test_lineup`, `test_lineup_ic2`, `test_lineup_ii0`, `test_ir3_gate` (new: every solved lineup legal on 450 seeded
   rosters × the Scrubs / dynasty / MFL-style slot lists; a surplus QB never in FLEX in one-QB, in SUPER_FLEX in
   superflex), `test_scoring`, `test_scoring_spec`, `test_scoring_ev`, `test_kdef`, `test_mfl_il2`, `test_waivers`,
   `test_waivers_if1`, `test_waivers_ig3`, `test_decisions`, `test_cards`, `test_projection_freeze`, `test_memo`,
   `test_clock`, `test_ir3_post_deploy` (new). API (18): `test_ir3` (bar its one database test), `test_build_context`.
   Then `ruff check src app tests api scripts/post_deploy_check.py`, `npm run lint` (eslint + svelte-check + tsc),
   `npm run build`.
2. **Liveness and readiness apart.** `/api/health` unchanged. New `GET /api/ready` (`api/league_lab_api/ready.py`,
   router registered in `main.py`, `read` bucket in `ratelimit.py`, no password, no secrets, `Cache-Control:
   no-store`).
3. **The post-deploy journey.** `scripts/post_deploy_check.py` (standard library only, read only, exit 0 / 1 / 2).
4. **Publication without the destructive gap.** `scripts/sync_to_hosted.sh`: `LEAGUE_LAB_HOSTED_PUBLISH=drop|swap|auto`,
   `--rollback`, the publication id, the publishing marker. Drilled on `league_lab_ir3_sim`.
5. **The nightly's three modes**: proposed below (exact lines); nothing built in `nightly.sh` / `nightly.yml`.

#### The gate's proof

Scratch commit `8db7001` ("a FLEX that admits a QB": `src/league_lab/lineup.py:87`
`"FLEX": frozenset({"QB", "RB", "WR", "TE"})`), then `scripts/gate.sh python`, then the commit dropped
(`git reset --hard a0817d7`):

```
FAILED tests/test_ir3_gate.py::test_a_surplus_qb_never_fills_a_flex_in_a_one_qb_league_and_does_in_superflex
21 failed, 759 passed in 73.14s (0:01:13)
gate FAIL decision suite (src, no database) (exit 1, 75 s)
  root: 780 ran, 0 skipped, 21 failed
gate ok   decision suite (api, no database) (4 s)
gate ok   ruff (0 s)
GATE FAILED: decision suite (src, no database) - this commit must not be published
```

(the 21 include `test_lineup::test_one_qb_flex_takes_the_best_leftover`, `test_lineup_ii0::test_the_review_case_a_cascade_through_flex`,
`test_trades_ii1::test_guard_positions_follow_the_league_slots`, `test_roster_value::test_superflex_is_eligibility_not_a_qb_slot`.)
Clean tree: `GATE PASSED`, 798 ran, 0 skipped; everything 72 s (root 40 s, api 2 s, ruff 0 s, web lint 26 s, build
4 s) on the last run and 210 s on a busier one (two shared cores, four developers). The python part also passed in a `git archive` export with no `.env` and no `data/` (CI's
condition). In CI add `uv sync` × 2 and `npm ci` (cached): about 4–5 minutes.

#### `/api/ready` — the rule and its answers

200 only when, in order: the database answers (`select 1`, own connection, 5 s connect, 5 s statement timeout);
`ops.projections`, `analytics.dim_game`, `analytics.mart_player_week_projections`,
`analytics.mart_player_ros_projection` exist; `max(ops.projections.fitted_at)` is not null; the week of the next
regular-season kickoff after now (`league_lab.clock`) has rows in `ops.projections` (the boards) and in
`mart_player_week_projections` (the lists) — "season over" passes; `mart_player_ros_projection` is not empty.
Else 503 with `code` and `reason` (docs/WORDS.md § IR-3). The publication's age is reported, never a 503 (a missed
nightly is `/api/health`'s `stale`). Kept 60 s after a success, 15 s after a failure, one probe at a time.

Local answer (fixture API, im1, pinned clock):

```json
{"ready":true,"code":"ready","checks":{"database":"ok","publication":null,"as_of":"2026-10-08T12:17:47.964029+00:00",
 "age_hours":2.8,"week":{"season":2026,"week":4,"board":true,"lists":true},"rest_of_season":true},
 "reason":"The published numbers can be served."}
```

Without a database: `503 {"ready": false, "code": "database", "reason": "The database does not answer (OperationalError)."}`;
during a drop-path publication: `503 … "code": "publishing", "reason": "The numbers are being replaced: a new
publication started at 2026-10-08T14:56:08Z and is not in place yet."`

**Render's health check: keep `/api/health`.** Pointed at `/api/ready`, a Neon wake-up (the free compute suspends)
or the nightly's drop-path window (8 s in the drill, a minute or two on Neon) fails the check, Render restarts a
healthy process, and that fixes nothing while dropping every cache and the Sleeper directory (one more call). The
risk of staying on `/api/health`: a process that runs but cannot serve decisions stays in rotation — covered by the
post-deploy check and an outside monitor on `/api/ready` that alerts a person, not a restart.

#### The post-deploy check on the local API (`python3 scripts/post_deploy_check.py http://localhost:8963 --expect-version 3dfa01d`)

```
post-deploy check: http://localhost:8963
ok   health     200  0.08s  version 3dfa01d35312, as_of 2026-10-08T12:17:47.964029+00:00, database ok, stale False
ok   ready      200  0.44s  publication not recorded, as_of 2026-10-08T12:17:47.964029+00:00, week 4 of 2026
ok   web app    200  0.02s  the page is served
FAIL rankings   200  1.66s  ranked though they cannot play: #18 Breece Hall (OUT)
ok   trade      200  2.30s  yours +19.8 this week, +11.8 over Next 4; theirs -0.8 / +6.5; reconciles, the verdict carries them
ok   reversed   200  0.31s  each team's change is the same from either side
FAILED: 1 check(s).
```

The one FAIL is real and is IR-1's defect on `main`'s code (face validity, Half PPR RB, week 4 of 2026, pinned):

| # | Player | Team | Proj | Report status |
|---|---|---|---|---|
| 1 | Jahmyr Gibbs | DET | 23.15 | — |
| 2 | Bijan Robinson | ATL | 21.84 | — |
| 3 | Christian McCaffrey | SF | 18.79 | — |
| 4 | Jonathan Taylor | IND | 17.80 | — |
| 5 | James Cook | BUF | 17.74 | — |
| … | … | … | … | … |
| 17 | Jaylen Warren | PIT | 11.95 | — |
| **18** | **Breece Hall** | NYJ | 11.85 | **Out** |
| 19 | Travis Etienne | NO | 11.62 | — |

Also ranked while Out on that list: #32 Jadarian Price, #40 Rachaad White, #41 Rico Dowdle, #49 Zach Charbonnet. The
check reads IR-1's `availability.cannot_play` / `cannot_play` and the report status (Out, IR, PUP, NFI, Suspended;
Questionable and Doubtful pass), so after IR-1 merges it should go green. Unreachable server: six `FAIL … no answer`
lines, exit 1. A server on another commit: `FAIL health … version 52ff88eb5b92 … — expected version 3dfa01d`.

#### Publication — the design and the drill

Default **`drop`** (the pre-IR-3 path, its restore transaction unchanged) plus two new statements, both ON by
default and never fatal: the marker `comment on database … '{"publishing_since": …}'` before the drop (cleared after
the restore) and the stamp `comment on schema analytics '{"publication": "<UTC>-<commit>", "published_at", "code",
"mode", "seasons_from"}'` after it. **`swap`** and **`auto`** are behind `LEAGUE_LAB_HOSTED_PUBLISH`, **OFF**:
the swap renames the live schemas `_prev` and restores under the live names in ONE transaction with grants, a revoke
on `_prev`, the stamp, and the checks (92 relations named by readers; the row counts of 89 tables against the local
copy; the readiness rule) — a failure anywhere rolls the whole publication back. Room: refused with **exit 8**
(nothing published) when the hosted database + the new copy > `LEAGUE_LAB_HOSTED_CAP_MB` (500). `_prev` kept for
`--rollback` until the next run (dropped at its start) or dropped at once when over the cap. docs/HOSTING.md §
"Publishing without the gap".

**Does old + new fit 0.5 GB?** No. One publication as a database: **246 MB** (`league_lab_ir3_sim` filled with the
published closure, seasons 2024+; 238.6 MB over an empty database's 7.4 MB; the sync's own estimate 254.0 MB). Two:
**~485 MB** before `usage` / `events` / `accounts` / `outlook` / `blog`, the catalog growth and WAL — at Neon's
512 MB limit. The swap needs a paid tier (its price is the PO's question to Andrew); on the free tier `auto` chooses
`drop`.

Drill (the sim published from itself; `LEAGUE_LAB_HOSTED_ALLOW_LOCAL=1 LEAGUE_LAB_HOSTED_SKIP_ROLE=1
LEAGUE_LAB_HOSTED_SEASONS=2 LEAGUE_LAB_HOSTED_CAP_MB=600`; a reader every 1.5 s as `league_lab_app`: `ready.check`
uncached, and a decision's three reads on one long-lived connection with server-side prepared statements):

*Interrupted swap* (terminated the moment the restoring session ran `COPY analytics.…`):

```
publication mode: swap (the hosted database holds 273 MB; + this copy ~187.6 MB = 461 MB <= the 600 MB cap)
the swap checks 92 relations and the rows of 89 tables before it commits
publishing: restoring beside the live publication, checking, then switching in one transaction (pages keep the previous numbers until the commit) ...
10:52:55 interrupting the restore: pg_terminate_backend on the restoring session (a lost connection)
FATAL:  terminating connection due to administrator command
CONTEXT:  COPY league_player_week, line 6312: …
sync exit 2
10:52:56 after: schemas analytics analytics_seeds ops, publication 20261008T1451Z-a0817d7e0623, analytics relations 71, database 201 MB
reader, 10:52:36 → 10:54:01, 88 lines, every one:
  ready=200 ready pub=20261008T1451Z-a0817d7e0623 | prepared reads: publication 20261008T1451Z-a0817d7e0623, ros 1282 rows, per-game from 2025 (23775 rows)
```

*Successful swap* (the first run; the readers switched at the commit, prepared statements included):

```
publication mode: swap (the hosted database holds 313 MB; + this copy ~182.9 MB = 496 MB <= the 600 MB cap)
switched in 6 s: publication 20261008T1451Z-a0817d7e0623 is live
the previous publication is kept as analytics_prev / analytics_seeds_prev / ops_prev until the next run (432 MB in all; …)
verified: all 92 relations the pages and the API read are on the hosted copy (the API's 79 included; 433 MB …)
reader: 12 × "ready=200 pub=sim-initial-copy | … per-game from 2024 (42736 rows)" (10:51:44–10:52:01)
     then "ready=200 pub=20261008T1451Z-a0817d7e0623 | … per-game from 2025 (23775 rows)" (10:52:02 on)
```

*Swap then `--rollback`* (re-run after the last script edit): `switched in 7 s: publication 20261008T1500Z-… is
live`; the app role on `analytics_prev`: `permission denied for schema analytics_prev`; `--rollback` → `rollback
done: the previous publication is live (20261008T1456Z-…)`, schemas `analytics analytics_seeds ops`, 198 MB; a second
`--rollback` → exit 9 "no previous publication is kept … nothing was touched". Reader: 13 × 1456Z, 6 × 1500Z, 11 ×
1456Z, 0 failed reads, readiness 200 throughout.

*Swap that does not fit* (`LEAGUE_LAB_HOSTED_CAP_MB=300`): exit 8, "… = 452 MB is over the 300 MB cap: nothing was
published (the hosted copy keeps the last publication)"; the live publication unchanged.

*The default `drop` path* (no switch): reader 11 × `ready=200`, then 5 × `ready=503 publishing` + "prepared reads
FAILED: UndefinedTable" (10:56:16–10:56:22, the gap the swap removes), 1 × 200 with `pub=None` (the stamp is written
just after the restore), then `pub=20261008T1456Z-a0817d7e0623`.

**Rollback steps**: docs/HOSTING.md § "Publishing without the gap" → Rollback (Actions idle; `scripts/sync_to_hosted.sh
--rollback` as the one writer; the post-deploy check; the decision record goes back with `ops`). After a `drop`
publication there is nothing to roll back to: run the nightly again.

#### The PO lines (files I may not edit)

`render.yaml` — no change of value; a comment above `healthCheckPath: /api/health`:

```yaml
    # IR-3: liveness only. /api/ready (readiness) is for the post-deploy check and outside monitors: pointed here, a
    # Neon wake-up or a nightly publish would restart a healthy process (docs/DEPLOY.md § "Readiness").
    healthCheckPath: /api/health
```

`scripts/nightly.sh` — (1) a hard step that fails the same way three times: the backtests soft when this model's
old one exists (replace line 492 `hard backtests backtests`):

```bash
if [ -z "${NIGHTLY_BACKTESTS:-}" ] && [ "$(q 'select count(*) from ops.projection_backtest')" -gt 0 ]; then
  SOFT_WHY="the scoreboards keep the last model's backtest; the next night computes this model's" soft backtests backtests
else
  hard backtests backtests
fi
```

(3) the publish retried on a lost connection, never on a deterministic refusal (replace line 560
`hard sync-hosted ./scripts/sync_to_hosted.sh`; safe with both modes: a failed swap changed nothing, a failed drop is
re-run whole):

```bash
sync_with_retry() {  # IR-3: a lost connection (psql exit 2) is retried twice, 60 s then 120 s; exits 5/6/7/8/64 are not
  local i rc
  for i in 1 2 3; do
    ./scripts/sync_to_hosted.sh && return 0
    rc=$?
    case "$rc" in 5|6|7|8|64) return "$rc" ;; esac
    [ "$i" -lt 3 ] && { echo "sync-hosted: attempt $i failed (exit $rc); again in $((i * 60)) s"; sleep $((i * 60)); }
  done
  return "$rc"
}
  hard sync-hosted sync_with_retry
```

and, after IR-1 merges (its rankings check is red on `main`'s code), the site's own answer after the publish, soft:

```bash
  if in_ci; then
    SOFT_WHY="the publication is live; the failing check's line says what the site answered" soft post-publish-check python3 scripts/post_deploy_check.py https://isuckatfantasy.io
  fi
```

The hosted size is already in the run summary (nightly.sh line 163 copies the sync's `verified: … MB on the hosted
database` line). The `dbt-build` retry excluding the failing node's descendants is not proposed as lines: it needs
`run_results.json` parsing and a decision on which marts may go out a day old — next wave.

`.github/workflows/nightly.yml` (2) — "today" counted from this morning's 07:30 New York, not 00:00 UTC (the `gate`
job; the Cloudflare Worker's `todaysRuns` needs the same change, `ops/nightly-trigger/`):

```bash
          since="$(date -u -d "TZ=\"America/New_York\" $(TZ=America/New_York date +%F) 07:30" +%Y-%m-%dT%H:%M:%SZ)"
          n="$(gh api "repos/${GITHUB_REPOSITORY}/actions/workflows/nightly.yml/runs?status=success&created=>=${since}&per_page=10" \
```

(checked here: `2026-10-08T11:30:00Z` on 2026-10-08, EDT.) To publish with the swap on a paid tier, its `Nightly
pipeline` step's `env:` gains `LEAGUE_LAB_HOSTED_PUBLISH: auto` and `LEAGUE_LAB_HOSTED_CAP_MB: "<plan limit − 30>"`.

A post-deploy workflow triggered by `workflow_run` of `image` is **not** added: Render's `checksPass` would wait for
it while it waits for Render's deploy (a deadlock I cannot test from here). Run the script by hand after a deploy, or
from the nightly as above.

#### Files

Mine: `api/league_lab_api/ready.py` (new), `api/tests/test_ir3.py` (new, 15), `scripts/post_deploy_check.py` (new),
`tests/test_ir3_post_deploy.py` (new, 11), `tests/test_ir3_gate.py` (new, 4), `scripts/gate.sh` (new), this file.
Handed to me: `.github/workflows/image.yml` (the `gate` job, `needs: gate`, a header line), `scripts/sync_to_hosted.sh`
(+ IR-3 blocks; two lines extended: the mode list, the one-writer rule now also covers `--rollback`),
`docs/HOSTING.md` (§ "Publishing without the gap"), `docs/DEPLOY.md` (step 2, § "The release gate", § "Readiness and
the post-deploy check", two "When it breaks" rows). Edits outside my files (marked IR-3): `api/league_lab_api/main.py`
(the router), `api/league_lab_api/ratelimit.py` (`/api/ready` → `read`), `docs/WORDS.md`, `CHANGELOG.md`.

New relations: none. Schema in/out: two comments (on the `analytics` schema and on the database) — a database
without them answers as before. New env variables (the sync only): `LEAGUE_LAB_HOSTED_PUBLISH` (drop),
`LEAGUE_LAB_HOSTED_CAP_MB` (500), `LEAGUE_LAB_HOSTED_KEEP_PREV` (1), `LEAGUE_LAB_HOSTED_SKIP_ROLE` (honoured only for
a local target). New dependencies: none (the gate job uses `actions/setup-node@v4`). Size on Neon: +2 short comments.

#### Checks

`api/tests/test_ir3.py` 15 passed; `tests/test_ir3_post_deploy.py` 11, `tests/test_ir3_gate.py` 4 passed. Edited
modules' tests: `test_h0`, `test_im3`, `test_ih1`, `test_static` (+ test_ir3) 98 passed; every test naming
`bucket_for` (`-k "bucket or limit or ratelimit"` over 13 files) 24 passed. `scripts/gate.sh` (everything) passed:
`GATE PASSED` (above). ruff clean; the copy standard clean; `bash -n` clean on `gate.sh` and `sync_to_hosted.sh`;
actionlint 1.7.12 clean on both workflows (from PyPI's `actionlint-py`, whose build fetched the binary from
actionlint's release page; no shellcheck here, so the `run:` scripts were not shell-linted by it). No `src/` edit
(no check_root), no screen (no e2e, no screenshots).

#### Not run here

Anything on GitHub (the gate job itself, `uv sync` / `npm ci` / `setup-node` there, its timing), Render (the health
check choice, the deploy after a green gate), Neon (the swap's size behaviour at the 512 MB limit, whether its owner
role may `comment on database`, a long transaction under the free compute, plan invalidation through Neon's pooler —
shown here on a direct connection only). The post-deploy check against the live site.

#### Found, not mine

* `main` ranks Out players (above): IR-1.
* The API's database pool has a fixed 30 s timeout, so an API test without a database waits 30–120 s per test (the
  first trial of the gate took 9 m 47 s for 15 files). Why the API's route suites cannot be gated as they are.
* `image.yml`'s `paths:` (= `render.yaml`'s `buildFilter`) leave out `tests/**` and `scripts/gate.sh`: a push that
  only changes a test runs no gate until the next push that deploys (it is then gated). Left as is.
