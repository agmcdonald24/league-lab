### IT-4 — publication: a decision never straddles one; the pool does not depend on the pooler's kindness

Branch `dev/IT4` from `main` `7341acc`; worktree `/home/claude/wt-ip3`; `league_lab` read only; the scratch database
`league_lab_it4_pub` (235 MB) was created for item 3 and dropped. **Nothing here is read by the nightly** except
`scripts/post_deploy_check.py` (the post-publish step runs it; the new `--expect-publication` is off unless passed).
`db.py`, `ready.py`, `main.py`, `events.py` are the API's; `sync_to_hosted.sh` is untouched.

#### 1. Done, not done, cut

* **Item 1 — done.** `prepare_threshold=None` (psycopg 3: `None` disables prepared statements on the connection; the
  extended protocol's unnamed statement is used, which a transaction pooler passes through) on every connection the
  API opens: the pool (`db.pool` kwargs), the usage writer, the read-write connection (`_rw_conn`), the events
  connection (`events.py`), the health `as_of` read (`main.py`), the readiness probe. The client setting, not a
  pooler setting: Neon keeps prepared statements today, nothing obliges a pooler to. `scripts/pooler_check.sh` runs
  **both modes** by default (kept 1000, kept 0) and passes both. Cost: none measurable on the fixtures (below).
* **Item 2 — done for the trade evaluation.** `db.one_publication(fn)` reads the publication id before and after; when
  it changed it drops the published caches and computes once more; a second change raises `PublicationChanged` (a
  `DataNotReady`: 503 "The numbers are being replaced right now; try again in a minute."), never a mixed answer.
  Detect-and-retry, not pinning: pinning needs one REPEATABLE READ transaction for every query of a decision on one
  connection, and the cached frames come from other transactions — they cannot be pinned; a drop-path publication
  removes the tables mid-request anyway. Wired: `POST /api/trades/evaluate`. **Cut:** rankings (`rankings_api.py`) and
  the lineup (`myweek`), their owners' files — one line each, `db.one_publication(<their compute>, …)`.
* **Item 3 — done** (below): no 500 in the gap.
* **Item 4 — the CI job as a diff** (section 6; it cannot run today: no fixture dump in the repository).
* **Item 5 — partly:** `post_deploy_check.py --expect-publication <id> --wait 150` waits until `/api/ready` names the
  new publication (bounded; a FAIL line "the server still names X after 150 s" otherwise). **Cut:** `--trade` built
  from the nightly's own database.
* **The PO's ten published caches:** none is wrong to drop (dropping costs one recompute — the trade route's 4.36 s
  cold after the drop). Probably missing (read their sources before registering): `stats` / `stats_agg`
  (`api/stats.py`: frames of the published per-game tables), `outlook` (the house outlook prices the boards),
  `availability`'s `contexts`. Right not to drop: `dfs_published` (a published slate is kept), `outlook_card*`,
  `blog*` (their own schemas, not the publication).

#### 2. Commits — `git log 7341acc..dev/IT4`.

#### 3. Evidence

**Both pooler modes** (`scripts/pooler_check.sh`, exit 0; the post-deploy "ok" lines left out; the rankings content
FAIL is the fixtures' Breece Hall "Out" at the pinned week 4, not the connection):

```
=== pooler mode: prepared statements kept: 1000
ok   ready probe (this tree): ready: The published numbers can be served.
ok   pool: 24 queries on 6 threads, each statement run 8 times (past the prepare threshold): 3 distinct answers
ok   usage writer: connect (application_name), BEGIN; SET TRANSACTION READ WRITE; a statement; COMMIT
ok   sync verification: analytics tables: 79;published through: 2026-10-05 12:25:32+00;4099 MB;no publication comment
ok   post-deploy check on the pooled API: every route answered through the pooler (1 content check(s) failed on the data, not the connection)
ok   pooler / API logs: no prepared-statement or startup-parameter errors
POOLER CHECK PASSED
=== pooler mode: prepared statements kept: 0
(the same six ok lines)
POOLER CHECK PASSED
POOLER CHECK PASSED IN BOTH MODES
```

Before (IS-4, `POOLER_PREPARED=0` on the old pool): `FAIL pool: DuplicatePreparedStatement: prepared statement
"_pg3_0" already exists`.

**Route timings** (fixture API on `league_lab`, direct connection, seconds; first / second call in a fresh process;
"before" = psycopg's default `prepare_threshold=5` put back on the pool by a scratch launcher):

| Route | before (cold / warm) | after (cold / warm) |
|---|---|---|
| `/api/rankings?league=ref:half&position=RB` | 0.717 / 0.015 | 0.767 / 0.019 |
| `/api/rankings?league=ref:half&position=QB&view=season` | 0.397 / 0.017 | 0.419 / 0.018 |
| `/api/rankings?league=ref:ppr&position=WR` | 0.124 / 0.015 | 0.132 / 0.018 |
| `/api/ros?league=1389709692405551104&position=ALL` | 0.143 / 0.034 | 0.158 / 0.043 |
| `/api/my-week?league=1389709692405551104&team=2` | 0.535 / 0.070 | 0.485 / 0.087 |
| `/api/waivers?league=1389709692405551104&team=2` | 0.352 / 0.067 | 0.331 / 0.077 |
| `/api/player/00-0039139?league=1389709692405551104&team=2` | 0.398 / 0.067 | 0.312 / 0.077 |
| `/api/matchups/board?league=ref:half` | 0.106 / 0.034 | 0.103 / 0.032 |
| `/api/trends?league=ref:half` | 1.360 / 0.053 | 0.509 / 0.056 |
| `/api/players?league=ref:half` | 0.058 / 0.032 | 0.060 / 0.034 |
| `/api/team?league=1389709692405551104&team=2` | 0.495 / 0.309 | 0.449 / 0.288 |
| `/api/trades/partners?league=1389709692405551104&team=2` | 3.805 / 0.075 | 3.376 / 0.055 |
| `POST /api/trades/evaluate` (Folk) | 0.267 / 0.076 | 0.279 / 0.099 |

A second "before" run (same launcher): trades/evaluate 0.279 / 0.099, my-week 0.367 / 0.059, trends 0.420 / 0.044,
partners 3.233 / 0.070 — the spread between two "before" runs is as large as before vs after: no measurable cost.
Twelve routes plus the trade, not the twenty slowest (cut for the clock).

**The switch on a real publication** (`sync_to_hosted.sh`'s drop path; `LEAGUE_LAB_HOSTED_ADMIN_URL` through a local
transaction-mode PgBouncer keeping no prepared statements, onto `league_lab_it4_pub`; the API on the same pooled
address; a poller every 0.5 s; the source's newest `fitted_at` moved to now just before the publish, so the stored
`as_of` changes on screen only when the API lets go of its cache):

```
03:08:16.4 source changed (as_of moved to now) - the API's caches still hold the old one
03:08:16   sync start … publishing: dropping the previous marts … restored in 5 s … verified: all 89 relations
03:08:12.2 ready 200 ready pub=it4-before                  | health as_of=None (not read yet)      | rankings 200 #1=20.55
03:08:43.6 ready 200 ready pub=it4-before                  | health as_of=2026-10-09T07:08:16+00:00 | rankings 200 #1=20.55
03:08:59.8 ready 200 ready pub=20261009T0708Z-117061a6ec49 | health as_of=2026-10-09T07:08:16+00:00 | rankings 200 #1=20.55
```

From the publication comment (about 03:08:28) to the screen's stored `as_of` changing: **about 15 s** (the 30 s
watcher in `db.query`; before IS-4 up to an hour for `as_of`, 600 s for a list). `/api/ready` named the new
publication 31 s later (its own 60 s answer cache).

**What a request sees in the gap** (a second publish; a poller asking for a different player's card and his games
every 0.25 s — reads no cache can answer): 158 × 200, **34 × 503** `{"error":"the numbers are not ready yet",
"detail":"This table is not on this database right now. …"}` from 03:09:47.3 to 03:09:51.9 (4.6 s), **0 × 500**, no
traceback in the API's log. Cached screens (Rankings) answered 200 with the previous numbers through the gap.
**Found:** `/api/ready` said 200 through the gap — its 60 s answer cache hides a 5 s publish; `publishing` shows only
on a longer gap (Neon: a minute or two).

#### 4. Tests

`api/tests/test_it4.py` 5 passed (the same publication: computed once; **a fake id that flips between the decision's
two reads: computed again, wholly on the new one, the published cache dropped**; a second flip: 503 in words; no
comment: today's; the pool and every one-off connection with `prepare_threshold=None`). With `test_is4`, `test_ir3`,
`test_ir0`, `test_h0`: 34 passed. `scripts/gate.sh python`: GATE PASSED, 815 ran (781 + 34; `test_it4` added to
`API_GATE`). ruff clean.

#### 5. Edits outside my files

`api/league_lab_api/main.py` (`trades_evaluate`: the call through `db.one_publication`; the health `as_of` connection:
`prepare_threshold=None`), `api/league_lab_api/events.py` (its connection: `prepare_threshold=None`).

#### 6. The PO's lines

`.github/workflows/image.yml` — the pooler check as an advisory job. It needs a database holding the published
relations; the repository has no such fixture dump today, so it cannot run there yet. The smallest: the closure with
the per-game tables windowed to one season (~40–60 MB as a compressed dump), restored into a service container:

```diff
+  pooler:
+    runs-on: ubuntu-24.04
+    continue-on-error: true          # advisory first
+    services:
+      postgres:
+        image: postgres:18
+        env: { POSTGRES_PASSWORD: postgres }
+        ports: ["5432:5432"]
+        options: --health-cmd "pg_isready -U postgres" --health-interval 5s --health-retries 30
+    steps:
+      - uses: actions/checkout@v7
+      - uses: astral-sh/setup-uv@c18668ad3cf93ea998bef934396af7bb5c839dc7 # v10.2.0
+      - run: sudo apt-get install -y pgbouncer postgresql-client
+      - run: uv sync --locked && (cd api && uv sync --locked)
+      - name: The fixture database (roles league_lab_pipeline / league_lab_app, the published closure; writes .env)
+        run: scripts/bootstrap_fixture_db.sh      # to write, with the fixture dump
+      - run: scripts/pooler_check.sh
```

`scripts/nightly.sh` — the post-publish step waits for the publication it just made:

```diff
-    soft post-publish-check python3 scripts/post_deploy_check.py https://isuckatfantasy.io
+    pub_id="$(grep -ao '"publication": "[^"]*"' logs/sync.log | tail -1 | cut -d'"' -f4)"
+    soft post-publish-check python3 scripts/post_deploy_check.py https://isuckatfantasy.io ${pub_id:+--expect-publication "$pub_id"} --wait 150
```

and `scripts/sync_to_hosted.sh`, after the drop path's stamp (the id is not printed today):

```diff
   psql "$LEAGUE_LAB_HOSTED_ADMIN_URL" -q -c "comment on schema analytics is \$pub\$$(pub_json drop)\$pub\$;" \
     || echo "WARNING: could not record the publication's id (the publish itself is fine)" >&2
+  echo "publication: $(pub_json drop)"
```

#### 7. Found, not mine

* None beyond the above (the `/api/ready` cache hiding a short gap is mine: next).

#### 8. Next

`/api/ready`'s cache 15 s while the publishing marker is set; `one_publication` in rankings and the lineup; register
`stats` / `outlook` after reading them; `--trade` from the nightly's database; the fixture dump for the CI job.
