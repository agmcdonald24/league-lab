### IS-4 — publication and release: what only the hosted setup can break (continues IR-3)

Branch `dev/IS4` from `main` `76b98df`, worktree `/home/claude/wt-ip1`, database `league_lab_im1` read only; no
scratch database was created. PgBouncer 1.22.0 installed (`apt-get install -y pgbouncer`, under a minute).

#### 1. Done, not done, cut

* **Item 1 — done.** `scripts/pooler_check.sh [--ready-from <commit>]`: a local PgBouncer in transaction mode (pool 2, no
  startup parameters ignored, protocol-level prepared statements kept as Neon's pooler keeps them; `POOLER_PREPARED=0`
  for a pooler that keeps none), and through it the readiness probe (this tree, and another commit's), the API's
  pool past psycopg's prepare threshold on 6 threads, the usage writer's connection and transaction, the sync's
  read-only verification queries, and the post-deploy check against an API started on the pooled address. **It fails
  on `748ff76`'s `ready.py` and passes on this tree's (the PO's fix is right).**
* **Item 3 — done.** `QueryCanceled` (a statement timeout; a subclass of `OperationalError`) is `query` ("A readiness
  query took longer than 5 s"), not "the database does not answer".
* **Item 2 — partly.** Built: `memo.region(..., published=True)` (a region registers itself) and
  `memo.drop_published()`; `db.query` reads the publication id on the pool at most every 30 s and, when it changes,
  drops every published region and runs `db.on_publication` callbacks (the health check's `as_of` is re-read at
  its next call). Registered: the API's SQL cache (`sql`). **Cut for the clock:** registering the gate's
  stored-record cache and `provenance`'s board cache (one keyword, `published=True`, on their `memo.region` call —
  their owners' files); the straddle guard (re-run a decision once when the id changed during it); the measured
  publish-on-a-scratch-database timing (the switch is proven by test only: before, up to 600 s; after, at most 30 s
  plus the request that reads it).
* **Item 4 — the PO's lines below.** The Worker's `todaysRuns` is edited (mine): the New York morning.
* **Item 5** — nothing built of it.

#### 2. Commits — see `git log 76b98df..dev/IS4`.

#### 3. Evidence

The old `ready.py` (`scripts/pooler_check.sh --ready-from 748ff76`, exit 1):

```
pooler check: PgBouncer 1.22.0 in transaction mode on 127.0.0.1:6439 -> league_lab_im1 (pool 2, prepared statements kept: 1000, startup parameters ignored: none)
ok   ready probe (this tree): ready: The published numbers can be served.
FAIL ready probe (748ff76): database: The database does not answer (OperationalError).
     pooler log for 748ff76's probe: unsupported startup parameter in options: statement_timeout=5000
ok   pool: 24 queries on 6 threads, each statement run 8 times (past the prepare threshold): 3 distinct answers
ok   usage writer: connect (application_name), BEGIN; SET TRANSACTION READ WRITE; a statement; COMMIT
ok   sync verification: analytics tables: 80;published through: 2026-10-05 12:25:32+00;4141 MB;no publication comment
     post-deploy: FAIL rankings   200  0.47s  ranked though they cannot play: #18 Breece Hall (OUT)
     post-deploy: FAILED: 1 check(s).
ok   post-deploy check on the pooled API: every route answered through the pooler (1 content check(s) failed on the data, not the connection: the lines above)
ok   pooler / API logs: no prepared-statement or startup-parameter errors
POOLER CHECK FAILED: 1
```

This tree (`scripts/pooler_check.sh`, exit 0; the post-deploy "ok" lines left out):

```
pooler check: PgBouncer 1.22.0 in transaction mode on 127.0.0.1:6439 -> league_lab_im1 (pool 2, prepared statements kept: 1000, startup parameters ignored: none)
ok   ready probe (this tree): ready: The published numbers can be served.
ok   pool: 24 queries on 6 threads, each statement run 8 times (past the prepare threshold): 3 distinct answers
ok   usage writer: connect (application_name), BEGIN; SET TRANSACTION READ WRITE; a statement; COMMIT
ok   sync verification: analytics tables: 80;published through: 2026-10-05 12:25:32+00;4141 MB;no publication comment
     post-deploy: FAIL rankings   200  0.45s  ranked though they cannot play: #18 Breece Hall (OUT)
     post-deploy: FAILED: 1 check(s).
ok   post-deploy check on the pooled API: every route answered through the pooler (1 content check(s) failed on the data, not the connection: the lines above)
ok   pooler / API logs: no prepared-statement or startup-parameter errors
POOLER CHECK PASSED
```

The rankings content failure is the data in `league_lab_im1` at the pinned week 4 (Breece Hall "Out", RB18), not the
connection; the check counts only 5xx / no answer / database failures as the pooler's.

**What else it found**: with a pooler that keeps no prepared statements (`POOLER_PREPARED=0`) **the API's pool breaks**
— psycopg prepares a statement after 5 runs on a connection (`prepare_threshold=5`) and the next transaction lands on
another server connection:

```
FAIL pool: DuplicatePreparedStatement: prepared statement "_pg3_0" already exists
ok   post-deploy check on the pooled API: every route answered through the pooler (1 content check(s) failed on the data, not the connection: the lines above)
ok   pooler / API logs: no prepared-statement or startup-parameter errors
POOLER CHECK FAILED: 1
```

The live site works, so Neon's pooler keeps them today; if it ever does not, `db.py`'s pool needs
`kwargs={"prepare_threshold": None}`. Session state: no session-level `SET` on pooled connections (`ready.py` uses
`set local`; the usage writer uses `SET TRANSACTION`), no advisory locks, `LISTEN` or temp tables on the API's
routes (grep of `api/` and the `src/league_lab` modules it imports); `application_name` is a parameter PgBouncer
tracks and passed everywhere.

#### 4. Tests

`api/tests/test_is4.py` 4 passed (timeout → query; no startup options and `set local` inside the transaction; a new
publication drops published regions only and refreshes `as_of`; no comment = today's behaviour). With
`test_ir3`, `test_ir0`, `test_h0`, `test_inf2`: 34 passed; `tests/test_memo.py` 9 passed. `scripts/gate.sh python`:
GATE PASSED, 809 ran (780 + 29; `test_is4` added to `API_GATE`). ruff clean, copy standard clean, `bash -n` clean,
`node ops/nightly-trigger/test.mjs`: 7 + the New York morning checks passed. No `web/` change.
`check_root.sh` (memo.py edited): 1,668 passed, 4 failed — all on the known list, 0 new. The pooler check re-run on
the committed tree (with the publication watcher in `db.query`): the same lines as above.

#### 5. Edits outside my files

`api/league_lab_api/main.py` (`# ---- IS-4` after H0 health: registers the `as_of` refresh), `CHANGELOG.md`.

#### 6. The PO's lines

`.github/workflows/image.yml` — a change to the gate or its tests runs the gate (and builds the image, as any push):

```diff
       - "web/**"
+      - "tests/**"
+      - "scripts/gate.sh"
+      - "scripts/post_deploy_check.py"
       - ".dockerignore"
```

`.github/workflows/nightly.yml` (the `gate` job) — "today" is New York's morning:

```diff
-          today="$(date -u +%Y-%m-%d)"
-          n="$(gh api "repos/${GITHUB_REPOSITORY}/actions/workflows/nightly.yml/runs?status=success&created=>=${today}T00:00:00Z&per_page=10" \
+          since="$(date -u -d "TZ=\"America/New_York\" $(TZ=America/New_York date +%F) 07:30" +%Y-%m-%dT%H:%M:%SZ)"
+          n="$(gh api "repos/${GITHUB_REPOSITORY}/actions/workflows/nightly.yml/runs?status=success&created=>=${since}&per_page=10" \
```

(the 13:07 UTC backup cron fires at 09:07 EDT / 08:07 EST, after 07:30 New York either way). The Worker
(`ops/nightly-trigger/src/index.js`) is changed the same way here (`morningSince`); deploy it with Andrew.

**The post-publish step becoming a failing step** — first: (a) this `ready.py` deployed and `/api/ready` 200 on the live
site for a few mornings (the pooler check passes it here; only the live site confirms it); (b) the rankings check
green on the live site for a few mornings (IS-1's Doubtful rule decides it); (c) the check run after the API has
seen the new publication (with item 2 that is within 30 s: a `sleep 45` before it), or it compares yesterday's
cached numbers; (d) the house-league trade's players still on those rosters (else `--trade` from the nightly's own
database).

#### 7. Found, not mine

* The API depends on the hosted pooler keeping prepared statements (above).
* `api/league_lab_api/ready.py`'s import block was unsorted on `main` (ruff I001 — the gate's ruff step failed on it);
  fixed here.

#### 8. Next

Register the gate's and `provenance`'s caches as `published=True`; the straddle guard; the measured switch on a
scratch publication; run `scripts/pooler_check.sh` in the PO's merge routine.
