### JA-3 — a request never waits for a database connection it could have had

Start 01:33 ET, end 01:55 ET (2026-10-12). Branch `dev/JA3` from `integ/JA` (JA-2's finished branch), worktree
`/home/claude/wt-iq4`, database `league_lab_iq4` (read only for this package: nothing written). The measurements ran
through a standing PgBouncer in transaction mode on 8921 (pool 20 server connections, so the pooler is never the
bottleneck), the fixture API on 8920 (provider fixtures, news / availability / usage off), pool traced per checkout.

#### 1. Done, not done, cut

* **Measured** (section 3): every pooled checkout's wait and hold, by route, at pool 4, eight and sixteen visitors, at
  the sandbox's speed and with a slow database stood in (every statement +0.15 s / +0.3 s while its connection is
  held — Neon right after a publish, cold storage, no statistics yet).
* **What holds connections, and why.** Nothing holds a pooled connection across CPU work or a provider call: the only
  pooled callers are `db._run_pooled` (one statement and its fetch; the DataFrame is built after the connection is
  back — now tested) and the blog's reads (two or three short statements on one connection). The trace's longest
  holds are single statements: the board's inputs (`select a.sleeper_id, … p.week`, 1.39 s on a trade evaluation,
  1.09 s on Trades partners), `mart_waiver_moves` (0.78 s), the blog's first list read (1.10 s, three statements). The
  fault is the **count**: four CPU slots (`ratelimit.Slots`) let four research / heavy requests run at once, each
  holding a connection while its statement runs, and at **4 connections** every read outside a slot (the blog, a card's
  small reads, readiness / health reads, the post-publish check) waited behind them — with seconds-long statements
  after a publish, past the blog's 5 s and the rest's 12 s: Sunday's blog and Saturday's trade.
* **Fixed**: the pool is **10** (`LEAGUE_LAB_POOL_SIZE`, 2–32): the 4 slotted + 6 for reads. **One wait for every
  caller: 8 s** (`db.POOL_WAIT_S`; the blog's 5 s is gone — it goes through `db.connection()` like everything else):
  the longest single statement measured is 1.4 s, Neon's compute waking takes a few seconds, and a connection that has
  not come in 8 s with 10 in the pool means the database is stalled — 503 "busy" in words, the blog its last good
  answer, instead of hanging.
* **Never silent**: a wait over a second is one log line — `waited 1.2 s for a database connection (3 of 4 in use) on
  /api/players; the statement began: select gsis_id, game_id, season, season_type, week,` (the route with every segment
  that carries a digit as `*`; the statement's first six words; never the rest, never a DSN). `/api/status` gains
  `pool`: `size, wait_limit_s, in_use, waiting, peak_in_use, checkouts, waited_over_1s, longest_wait_s,
  longest_wait_route, longest_wait_at, longest_hold_s, longest_hold_route` (since the process started).
* **Not done**: the swap drill could not be re-run — this wave allows no new database (IU-4's `test_iu4` passes; what
  it proved depended on per-statement holds, which are unchanged). Not changed: `ratelimit.Slots` (section 7).

#### 2. Commits — `git log integ/JA..dev/JA3`.

#### 3. Evidence

**The busy minute, the sandbox's speed** (16 visitors at once, each walking My Week house + MFL, a card, Stats with a
stretch against another, Waivers, Trades partners, the trade evaluation, the blog list and a post; a fresh process each
run, so first visits; n / 503 / p95 s):

| Route | before: pool 4 | after: pool 10 |
|---|---|---|
| blog list | 54 / 0 / 0.15 | 50 / 0 / 0.13 |
| blog post | 51 / 0 / 0.16 | 50 / 0 / 0.12 |
| card | 53 / 0 / 8.42 | 51 / 2 / 13.15 |
| My Week (house) | 52 / 0 / 16.42 | 51 / 0 / 18.26 |
| My Week (MFL) | 51 / 0 / 11.46 | 53 / 1 / 11.46 |
| Stats, a stretch vs another | 50 / 0 / 11.29 | 49 / 1 / 16.36 |
| trade evaluate | 52 / 0 / 11.31 | 51 / 1 / 15.58 |
| Trades partners | 53 / 1 / 15.37 | 50 / 1 / 13.10 |
| Waivers | 52 / 0 / 14.09 | 52 / 1 / 7.46 |
| **pool**: peak in use · waits > 1 s · longest wait | 4 · 0 · 0.16 s | 4 · 0 · 0.21 s |

At the sandbox's speed the pool never ran out at 4: the p95s and every 503 are the CPU slots (20 s, then "busy" —
no `no pooled connection` line in either log) and move run to run on two shared cores. The pool matters when the
database is slow:

**A slow database** (every statement +0.3 s while its connection is held; 4 visitors on the slotted heavy routes and 4
on a small uncached read — a player's past projections — for 45 s):

| | pool 4 | pool 10 |
|---|---|---|
| reads served | 547 | 660 |
| read p95 / max | 0.77 / 5.04 s | 0.69 / 3.09 s |
| waits over 1 s | 4 (longest 1.22 s, "3 of 4 in use") | 0 (longest 0.11 s) |
| peak in use | 4 | 8 |

With +0.15 s statements and the 16-visitor minute, both sizes ended in the CPU slots' 503s (32 at 4, 28 at 10): the
slots, not the pool, bound the heavy routes.

**Cost**: 10 connections through the pooler: +0.2 MB RSS here (no TLS); with TLS to Neon a few hundred kB each —
a few MB of the 2 GB process. Database: through Neon's pooled endpoint the client connections are multiplexed — a
backend is used only while a statement runs (peak 8 here). The repository's docs only say to use the `-pooler` host
(DEPLOY.md step 1); Neon's own limit on pooled client connections is not in the repository and could not be read here.

`scripts/pooler_check.sh` (ports 8924 / 8925, API 8926): **POOLER CHECK PASSED IN BOTH MODES** (every post-deploy check
ok in both).

#### 4. Tests

`api/tests/test_ja3.py` 7 passed: the connection is back in the pool before the rows become a DataFrame; every pooled
caller takes the one wait (the blog's read included; no `pool().connection(` left in `blog_store`); a wait over a
second is one log line with the counts, the route and the first words only (no table name past them, no DSN); a short
wait is silent; `in_use` is given back when the statement fails; `/api/status` carries the pool and no DSN; the size's
bounds. Changed stand-ins (behaviour unchanged): `test_iu4`'s fake pool takes the wait argument; `test_iy3`'s broken
`db` hands `connection()` through its broken pool. With `test_iw0`, `test_iu4`, `test_it4`, `test_is4`, `test_ir3`,
`test_io3`, `test_iu6`, `test_iy3`, `test_h0`, `test_ih1`: 99 passed. `check_api.sh` on every test file that opens a
pooled connection (ik4, inf2, io3, iu4, iu6, iv1, iw0, ix1, iy3, ja3 + h0, ih1, im3, static): 172 passed, **0 new
failures**. `scripts/gate.sh` (last, everything): **GATE PASSED**, 823 ran, web lint + build ok. ruff, the copy standard clean.

#### 5. Edits outside my files

`api/league_lab_api/main.py` (a marked JA-3 middleware setting the route for the log line; `out["pool"]` in
`/api/status`), `api/league_lab_api/blog_store.py` (three `db.pool().connection(timeout=5)` → `db.connection("blog")`),
the two test stand-ins above, `CHANGELOG.md`.

#### 6. The PO's lines

`render.yaml`: nothing (the size is 10 in the code; `LEAGUE_LAB_POOL_SIZE` exists if it must move without a deploy).
`scripts/post_deploy_check.py`: worth one line, never a failure — the pool's longest wait since the process started
(the PO reads it after a publish without opening Render's logs):

```diff
     j.line(code == 200 and isinstance(b, dict) and b.get("ready") is True, "ready", code, secs, text)
+    code, secs, st = j.call("GET", "/api/status")
+    pool = st.get("pool") if isinstance(st, dict) else None
+    if isinstance(pool, dict):
+        print(f"info pool       {code:>3} {secs:5.2f}s  {pool.get('size')} connections, peak {pool.get('peak_in_use')} in use, "
+              f"longest wait {pool.get('longest_wait_s')} s on {pool.get('longest_wait_route')}, {pool.get('waited_over_1s')} over 1 s", flush=True)
```

#### 7. Found, not mine

* **The CPU slot is held across database statements** (`ratelimit.Slots`: four slots, 20 s, then 503 "busy"). A
  research request inside a slow statement keeps one of the four slots, so on a slow database the heavy routes 503
  while the CPU is idle (the +0.15 s and +0.3 s runs: every 503 was a slot, none the pool). Worth a look: a slot per
  CPU-bound step rather than per request.
* The pool checks each connection on checkout (`check=ConnectionPool.check_connection`): one more round trip per
  statement — a card is about 15 statements. Cheap in Neon's region; not changed.

#### 8. Next

The slot question above; the post-publish check's pool line; a look at the card's ~15 statements (one query could
carry most of them).
