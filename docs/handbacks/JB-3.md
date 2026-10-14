### JB-3 — Sunday keeps answering

Start 10:17 ET, end 10:47 ET (2026-10-14). Branch `dev/JB3` from `integ/JB` (`main` `06d27a4`), worktree
`/home/claude/wt-iq4`, database `league_lab_iq4` (written: only the `analytics` schema's comment for the simulated
publication, set back to none). The fixture API on 8930 through a PgBouncer in transaction mode on 8931; a slowed
database = every statement +0.15 s while its connection is held (JA-3's method: Neon after a publish).

#### 1. Done, not done, cut

* **1. A request waiting on the database holds no CPU slot — done.** Measured first: in the slowed busy minute the
  four slots spent **213 of their 240 slot-seconds inside database statements** (the pool trace by route: cards 81.9 s,
  My Week 43.4 s, the trade evaluation 36.7 s, Waivers 27.8 s, Stats 16.2 s, Trades partners 7.6 s). Now
  `db.connection()` gives the request's slot back while its statement runs (`ratelimit.Lease.pause`) and takes one
  again after (`resume` → `Slots.take_back`): **a request coming back goes ahead of every new one and is never
  refused** (past 3 × the wait it goes over the ceiling by one rather than answer "busy" mid-request). The trade: a
  request may wait twice — to start, and after a statement while four others compute (the longest such wait in the
  minute: 1.8–3.9 s). A slot's hold is CPU time now. A request that fails mid-statement or ends while its statement
  still runs never keeps or retakes a slot (tested). `/api/status` `slots` keeps every key and adds
  `released_for_statements`, `longest_retake_wait_s`, `longest_retake_route`.
* **2. The after-publish check picks a live trade — done as a module + the PO's diff.** `scripts/post_deploy_trade.py`:
  the house league's teams in order, the first two with a bench player who has a projection this week (QB / RB / WR / TE,
  not in an IR slot; the highest projection, ties by key); one for one; the ids printed; the `reversed` check runs on
  it. The Folk trade stays a pytest regression (`api/tests/test_ix5.py`).
* **3. Warm after a publish — done.** What the first requests after a publication wait on: every published cache is
  dropped at once (IS-4) and the first visitors each rebuild the same boards. Now a new publication seen by the watcher
  **or by `/api/ready`'s probe** (the check waits on it) drops the caches and starts **one** warm-up pass in a daemon
  thread (`api/league_lab_api/warm.py`): the reference Rankings, the league list, and for the two house leagues their
  first team's My Week, Team, Trades partners and Waivers — 16 requests at most, 240 s at most, **one at a time and
  only while two CPU slots are free** (a visitor is never queued behind it), as ordinary requests to this process's own
  address (`PORT`, which Render sets; none → off). `/api/status` `warm` says whether it ran.
* **Cut**: a warm-up of per-player cards (a card is per player: there is no "the" card to warm).

#### 2. Commits — `git log integ/JB..dev/JB3`.

#### 3. Evidence

**The busy minute on a slowed database** (16 visitors, 60 s, a fresh process; n / 503 / p95 s):

| Route | before | after |
|---|---|---|
| blog list | 12 / 0 / 0.07 | 32 / 0 / 0.20 |
| blog post | 12 / 0 / 0.04 | 34 / 0 / 0.15 |
| card | 17 / **8** / 44.23 | 36 / 0 / 19.76 |
| My Week (house) | 10 / **3** / 22.46 | 29 / 0 / 12.13 |
| My Week (MFL) | 11 / **3** / 40.64 | 31 / 0 / 18.64 |
| Stats, a stretch vs another | 13 / **7** / 20.05 | 29 / 0 / 15.26 |
| trade evaluate | 10 / **2** / 35.77 | 31 / 0 / 13.65 |
| Trades partners | 13 / **4** / 20.05 | 32 / 0 / 35.41 |
| Waivers | 12 / **4** / 30.38 | 33 / 0 / 15.99 |
| **slots**: busy answers · longest wait · peak | **31** · 20.05 s · 4/4 | **0** · 8.04 s · 4/4 |
| **pool**: peak · waits over 1 s | 4/10 · 0 | 10/10 · 0 |

Requests answered: 110 → 287. **No route answers "busy" that did not before** (none does). Trades partners' p95 rose
because before most of its requests were refused at 20 s; now they finish.

**After a publication** (a fresh process, the statements slowed, the publication simulated by changing the analytics
schema's comment as the sync writes it, the after-publish check with `--expect-publication` from the PO's diff, then 8
visitors for 30 s):

| | warm-up off | warm-up on (the check waits for it) |
|---|---|---|
| the check: rankings / trade | 5.35 / 5.24 s | **0.01 / 1.75 s** |
| warm-up | — | `info warm-up 38.09s  10 routes warmed, 0 skipped in 32.4 s` |
| visitors' p95: trade evaluate / Waivers / My Week | 5.07 / 7.13 / 2.13 s | **1.73 / 2.90** / 2.04 s |
| visitors' p95: card / Stats / Trades partners (team 2) | 9.92 / 8.79 / 15.39 s | 11.53 / 13.53 / 15.99 s (not warmed) |
| `info load` | pool 1/10 · slots 1/4, 0 busy | pool 2/10 · slots 1/4, 0 busy |

(The `info load` line stays low in the sandbox: the check runs alone here; on run #47 other traffic ran with it.)

`scripts/pooler_check.sh` (ports 8934 / 8935, API 8936): **POOLER CHECK PASSED IN BOTH MODES.** The check run on the
local API with the PO's diff applied (a scratch copy): `ok trade pick … team 1 gives DK Metcalf (WR, key 5846) for team
6's Jameson Williams (WR, key 8148)` · `ok trade` · `ok reversed` · `All checks passed.`

#### 4. Tests

`api/tests/test_jb3.py` 12 passed: the slot given back during a statement and taken again after (another request
gets it meanwhile); a returning request ahead of a new one; a failed statement leaks no slot; a request that ended
mid-statement takes no slot after it; taking it back is never refused; no lease outside a slotted request; a research
request through the app ends with nothing held; one change path for a publication id; the warm-up off without a port
and never in the request; a pass bounded, one at a time, yielding to visitors; the pass's routes; `warm`'s status.
`tests/test_jb3_trade.py` 4 passed (the pick: not a starter, not IR, not a kicker, not zero; a team without one
skipped; ties stable; no two teams said, not guessed). `check_api.sh` on the 49 API test files that name the limiter,
`/api/status`, the pool, the blog's reads or readiness: 756 passed, 38 failed — 28 on the known list and **10 not on
it but failing identically on `integ/JB`'s code** (my four modules checked out from `integ/JB`, the same 10 red:
`test_in6` × 6, `test_io2` × 3, `test_io4` × 1 — the outlook's and the schedule's data state; not mine), 0 caused here.
`scripts/gate.sh` (last): **GATE PASSED**, 823 ran, web lint + build ok. ruff, the copy standard clean.

#### 5. Edits outside my files

`api/league_lab_api/ratelimit.py` (marked JB-3: `Slots.take_back` / `given_back`, the returning priority, `Lease`,
the middleware's lease), `api/league_lab_api/main.py` (`warm.install()`, `out["warm"]`), `api/league_lab_api/ready.py`
(the probe's publication id to `db.note_publication`), `docs/DEPLOY.md` (two rows), `CHANGELOG.md`.

#### 6. The PO's lines

`scripts/post_deploy_check.py` (the trade from the current rosters when `--trade` / `POST_DEPLOY_TRADE` is not given;
after "picked up", wait — bounded, 180 s — for this publication's warm-up and print one `info warm-up` line):

```diff
--- scripts/post_deploy_check.py
+++ scripts/post_deploy_check.py
@@ -19,7 +19,8 @@
   reversed   the same trade from the partner's side: each team's change is the same number
 Writes nothing anywhere (the trade route only reads). Needs python3 (standard library only); no password unless the
 server has its gate on (--password, or POST_DEPLOY_PASSWORD). Exit: 0 all ok · 1 a check failed · 2 usage.
-A trade whose players have since moved answers 400 "on X's roster, not Y's": pass a current one with --trade.
+Without --trade the trade is chosen from the house league's current rosters (scripts/post_deploy_trade.py: two teams,
+a bench player each with a projection this week; the ids printed), so a roster move never fails the check.
 """
 
 from __future__ import annotations
@@ -160,8 +161,9 @@
 def main(argv: list[str] | None = None) -> int:
     ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
     ap.add_argument("base", help="the server's address, e.g. https://isuckatfantasy.io")
-    ap.add_argument("--trade", default=os.environ.get("POST_DEPLOY_TRADE", DEFAULT_TRADE),
-                    help="league:team:partner:give ids:get ids (comma-separated ids), default the review's Folk case")
+    ap.add_argument("--trade", default=os.environ.get("POST_DEPLOY_TRADE", ""),
+                    help="league:team:partner:give ids:get ids (comma-separated ids); default: chosen from the house "
+                         "league's current rosters (scripts/post_deploy_trade.py)")
     ap.add_argument("--expect-version", default=os.environ.get("POST_DEPLOY_VERSION", ""),
                     help="the version /api/health must report (a prefix of it is enough: a short commit)")
     ap.add_argument("--password", default=os.environ.get("POST_DEPLOY_PASSWORD", ""),
@@ -173,10 +175,14 @@
     ap.add_argument("--timeout", type=float, default=float(os.environ.get("POST_DEPLOY_TIMEOUT", "90")))
     a = ap.parse_args(argv)
     try:
+        if not a.trade:                     # JB-3: chosen below, from the current rosters
+            raise LookupError
         league, team, partner, give, get = a.trade.split(":")
         team_i, partner_i = int(team), int(partner)
         give_l, get_l = [x for x in give.split(",") if x], [x for x in get.split(",") if x]
         assert league and give_l and get_l
+    except LookupError:
+        league = None
     except (ValueError, AssertionError):
         print("--trade is league:team:partner:give ids:get ids, e.g. " + DEFAULT_TRADE, file=sys.stderr)
         return 2
@@ -202,6 +208,19 @@
         j.line(seen == a.expect_publication, "picked up", code, time.monotonic() - t0,
                f"publication {seen} is served" if seen == a.expect_publication
                else f"the server still names {seen or 'no publication'} after {a.wait:.0f} s (expected {a.expect_publication})")
+        # JB-3: the warm-up this publication started (bounded): the screens below are then what a visitor after it reads
+        if seen == a.expect_publication:
+            t1, warm = time.monotonic(), None
+            while time.monotonic() - t1 < 180:
+                _, _, st = j.call("GET", "/api/status")
+                warm = st.get("warm") if isinstance(st, dict) else None
+                done = isinstance(warm, dict) and (warm.get("last") or {}).get("publication") == a.expect_publication
+                if not isinstance(warm, dict) or not warm.get("enabled") or (done and not warm.get("running")):
+                    break
+                time.sleep(5)
+            last = (warm or {}).get("last") or {}
+            print(f"info warm-up     {time.monotonic() - t1:5.2f}s  " + (f"{last.get('warmed')} routes warmed, {last.get('skipped')} "
+                  f"skipped in {last.get('seconds')} s after {last.get('publication')}" if last else "none (off, or no port)"), flush=True)
     # ---- end IT-4
 
     code, secs, b = j.call("GET", "/api/health")
@@ -230,6 +249,16 @@
     ok, text = check_rankings(b) if code == 200 else (False, _why(b)[:160])
     j.line(ok, "rankings", code, secs, text)
 
+    if league is None:                      # JB-3: a live trade from the league's current rosters (the ids printed)
+        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
+        from post_deploy_trade import live_trade
+        picked, words = live_trade(lambda m, p: j.call(m, p))
+        j.line(picked is not None, "trade pick", 200 if picked else 0, 0.0, words)
+        if picked is None:
+            print("All checks passed." if j.fails == 0 else f"FAILED: {j.fails} check(s).")
+            return 1
+        league, team_i, partner_i, give_l, get_l = (picked["league"], picked["team"], picked["partner"],
+                                                    picked["give"], picked["get"])
     body = {"league": league, "team": team_i, "partner": partner_i, "give": give_l, "get": get_l}
     code, secs, b = j.call("POST", "/api/trades/evaluate", body)
     ok, text, fwd = check_trade(b) if code == 200 else (False, _why(b)[:200], None)
```

`scripts/nightly.sh`, `render.yaml`, the workflows: nothing (Render's `PORT` turns the warm-up on; the nightly's
check already passes `--expect-publication`).

**What tonight's summary will say**: `ok picked up …`, then `info warm-up  NN.NNs  N routes warmed, 0 skipped in N s
after <id>`, then the screens, `ok trade pick  …  team A gives <name> (<pos>, key K) for team B's <name> (…)`, `ok
trade`, `info load …`, `ok reversed`.

#### 7. Found, not mine

* The Folk trade's player (key 650) has left the League of Scrubs on the live site; the sandbox's fixtures still have
  him, so `scripts/pooler_check.sh`'s post-deploy step passes here with the old default until the PO's diff lands.

#### 8. Next

A per-player card is ~15 statements (the largest share of the slot time measured before the change); one query could
carry most of them.
