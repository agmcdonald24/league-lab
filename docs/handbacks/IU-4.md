### IU-4 — the gap-free publish on the free plan (continues IT-4)

Branch `dev/IU4` from `main` `99fb216`; worktree `/home/claude/wt-ip3`; `league_lab` read only; the scratch database
`league_lab_iu4_pub` (235 MB → 456 MB at a swap's peak) was created for the drills and dropped. The sync was pointed
only at it, through a local transaction-mode PgBouncer, with `LEAGUE_LAB_HOSTED_SKIP_ROLE=1` and the worktree's
existing app password (never a throwaway). **Read by the nightly:** `scripts/sync_to_hosted.sh` (it is the publish);
`ready.py` / `db.py` are the API's.

#### 1. Done, not done, cut

* **Item 1 — done.** `auto` swaps when the hosted database's size + 1.2 × the copy's estimate ≤ `LEAGUE_LAB_HOSTED_CAP_MB`
  (default **800**, was 500). **A swap that stops before its commit for any reason** (the database refusing the space,
  a lost connection, a failed check) changed nothing — one transaction — and with `auto` **the same run publishes by
  the drop path**. An explicit `swap` still stops (it never drops). The drop path's code is byte-for-byte unchanged
  (diffed against `99fb216`). Proven on scratch: a swap that fits; a refused swap → the fallback in the same run.
  **The refusal was injected**, not a real quota: `LEAGUE_LAB_HOSTED_DRILL_REFUSE=1` (honoured only for a local target)
  raises SQLSTATE `53100 disk_full` "could not extend file: project size limit exceeded" after the whole restore, at
  the end of the swap's transaction — where a real space refusal hurts most (the most written, nothing committed).
* **Item 2 — done.** The previous copy is kept as `_prev` only when the next swap would still fit beside it
  (`after + copy ≤ cap`); otherwise it is dropped at once ("nothing to roll back to until the next swap").
  `--rollback` with nothing kept: exit 9, "nothing to roll back to - no previous publication is kept (… the last
  publish used the drop path, or its previous copy did not fit beside the next swap and was dropped). Nothing was
  touched; to replace a bad publication, run the nightly again."
* **Item 3 — done** (drill A below): no 503, no 500 during a swap.
* **Item 4 — done, differently from "15 s while publishing":** a request that finds a published table missing
  (`UndefinedTable` → `DataNotReady`) now makes the next `/api/ready` probe at once (`db.on_tables_away` → `ready`), and
  a failure is kept 15 s — so a drop-path gap shows `publishing` from its first affected request (drill B: at once).
  A shorter success cache alone would still miss a 5 s gap. After the gap, `/api/ready` keeps saying `publishing` for
  up to 15 s (its failure cache) while the screens already answer.
* **Item 5 — the diffs below.** **Item 6 — cut** (the `--trade` from the nightly's database; the CI fixture dump).
* **The 38 MB** (281 console − 243 ours): the repository's docs do not break it down. What I can say: an empty
  Postgres database is 7.4 MB here (a Neon project has two: `neondb` and `postgres`), plus the `usage` / `events` /
  `accounts` / `outlook` / `blog` state; the rest is the plan's own accounting. **Why 800**: today's peak during a swap
  is about 281 + 1.2 × 243 ≈ 573 MB; 800 leaves 224 MB of the 1,024 for growth, the state and the plan's history.
  Both paths write the same restore (the same write-ahead log); the swap adds only the old copy, held until its
  commit. If the cap is wrong, the fallback publishes anyway.

#### 2. Commits — `git log 99fb216..dev/IU4`.

#### 3. Evidence

**Drill A — the swap fits** (`LEAGUE_LAB_HOSTED_PUBLISH=auto`, default cap, seasons 2024+):

```
publication id: 20261009T1736Z-99fb216285fe
publication mode: swap (the hosted database holds 350 MB; + this copy ~262 MB (218.7 × 1.2) = 612 MB <= the 800 MB cap)
the swap checks 89 relations and the rows of 85 tables before it commits
publishing: restoring beside the live publication, checking, then switching in one transaction (pages keep the previous numbers until the commit) ...
switched in 6 s: publication 20261009T1736Z-99fb216285fe is live
the previous publication is kept as analytics_prev / analytics_seeds_prev / ops_prev until the next run (455 MB in all; the next swap would need 717 MB <= 800; …)
verified: all 89 relations the pages and the API read are on the hosted copy (the API's 77 included; 456 MB on the hosted database; …)
```

The reader (an uncached read — a different player's card — and `/api/ready`, every 0.25 s, the API on the pooled
address, 13:36:04–13:37:19): **172 × card 200, 172 × ready 200; 0 × 503, 0 × 500.** The publication id the reader saw:
`iu4-before` until 13:36:59.9, then `20261009T1736Z-…` (the swap committed about 13:36:27; `/api/ready` keeps a success
60 s). No mixed answer is possible on the card: each of its statements reads one committed state, and the swap
changes every table in one commit (the trade evaluation's two-publication guard, IT-4, covers multi-read decisions).

**Drill B — the swap refused, the fallback publishes in the same run** (`auto` + the injected refusal; the run's own
lines with their times):

```
13:37:58 publication id: 20261009T1737Z-99fb216285fe
13:37:58 publication mode: swap (the hosted database holds 354 MB; + this copy ~262 MB (218.5 × 1.2) = 616 MB <= the 800 MB cap)
13:37:58 publishing: restoring beside the live publication, checking, then switching in one transaction ...
13:38:04 ERROR:  could not extend file: project size limit exceeded (a drill: LEAGUE_LAB_HOSTED_DRILL_REFUSE=1)
13:38:04 the swap stopped before its commit (exit 3): nothing of it was kept, the previous publication is untouched; publishing by the drop path instead (fallback)
13:38:04 publishing: dropping the previous marts, then restoring (pages show 'not built yet' meanwhile; ops swaps atomically) ...
13:38:09 restored in 5 s
13:38:10 verified: all 89 relations … (241 MB on the hosted database …)
sync exit 0
```

The reader: 13:37:43–13:38:04 card 200 and ready 200 on the previous publication (`20261009T1736Z`) **through the
whole refused swap**; 13:38:04.6–13:38:09.7 the fallback's drop gap: 18 × card 503 `{"error":"the numbers are not ready
yet",…}`, ready 503 `publishing` from the first affected request; 13:38:09.7–13:38:24.5 card 200 on the new tables while
ready still said `publishing` (its 15 s failure cache); from 13:38:24.6 ready 200 with `20261009T1737Z`. **0 × 500**, no
traceback in the API's log. Totals: card 176 × 200 / 18 × 503; ready 140 × 200 / 54 × 503.

`--rollback` after drill B (nothing kept): exit 9 with the sentence in item 2.

#### 4. Tests

`api/tests/test_iu4.py` 2 passed (a missing table makes the next ready probe at once and it says `publishing`; the hook
registered once). With `test_it4`, `test_is4`, `test_ir3`, `test_ir0`: 33 passed. `scripts/gate.sh python`: GATE
PASSED, 819 ran (783 + 36; `test_iu4` added). `scripts/pooler_check.sh`: **POOLER CHECK PASSED IN BOTH MODES** (every
post-deploy check ok in both; its probe loader now also rewrites `from . import`, since `ready.py` imports `db` for the
hook). ruff, copy standard, `bash -n` clean. No `src/` edit.

#### 5. Edits outside my files — none (`CHANGELOG.md` one bullet).

#### 6. The PO's lines

`.github/workflows/nightly.yml` (the `Nightly pipeline` step's `env:`):

```diff
           LEAGUE_LAB_HOSTED_APP_PASSWORD: ${{ secrets.LEAGUE_LAB_HOSTED_APP_PASSWORD }}
+          # IU-4: publish by swapping when two copies fit the plan (Neon Free: 1 GB; cap 800 MB); if the swap stops before
+          # its commit, the same run publishes by the drop path. Rollback = delete these two lines (the drop path).
+          LEAGUE_LAB_HOSTED_PUBLISH: auto
+          LEAGUE_LAB_HOSTED_CAP_MB: "800"
```

`scripts/nightly.sh` (line 163, the summary — how tonight's publication replaced the last one):

```diff
       while IFS= read -r line; do printf '\n`%s`\n' "$line"; done < <(grep -h "^verified: all" logs/sync.log 2>/dev/null | tail -1)
+      # ---- IU-4: swap / refused → fallback / drop, from this run's part of the log
+      while IFS= read -r line; do printf '\n`%s`\n' "$line"; done < <(awk '/=== .* sync start/ { n = NR } { l[NR] = $0 } END { for (i = n; i <= NR; i++) print l[i] }' logs/sync.log 2>/dev/null | grep -E "^(publication mode:|switched in|the swap stopped|the previous publication is|ERROR: +could not extend)")
```

(tested on both drills' logs: it prints the lines quoted below.)

**What tonight's summary will say**:

* **The swap fits**: `publication mode: swap (the hosted database holds ~2xx MB; + this copy ~29x MB (24x × 1.2) = ~5xx MB
  <= the 800 MB cap)` · `switched in N s: publication 20261010T…Z-<sha> is live` · and either `the previous publication
  is kept as … (… the next swap would need N MB <= 800 …)` or — likelier on Neon (about 520 + 290 > 800) — `the previous
  publication is dropped (kept, the next swap would need N MB of the 800 MB cap): … nothing to roll back to until the
  next swap`.
* **The swap is refused and the fallback publishes**: `publication mode: swap (…)` · `ERROR:  could not extend file
  because project size limit (… MB) has been exceeded` (Neon's words; not seen here) · `the swap stopped before its
  commit (exit 3): nothing of it was kept, the previous publication is untouched; publishing by the drop path instead
  (fallback)` — then the usual `verified: all …` line. The run is green either way.
* **The cap says no before trying**: `publication mode: drop (auto: … over the 800 MB cap - two copies do not fit)`.
* In every case the post-publish check's `picked up … publication … is served` names tonight's id.

#### 7. Found, not mine — none.

#### 8. Next

Tonight's summary decides the cap (raise it if Neon's measure stays near ours; lower it if the refusal fires); the
`--trade` from the nightly's database; the CI pooler job's fixture dump.
