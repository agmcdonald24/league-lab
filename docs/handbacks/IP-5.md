# IP-5 hand-back — robustness and reach (Wave I-P, 2026-10-07)

**Task**: BRIEF § "IP-5 — robustness and reach" (`/home/claude/waveIP/BRIEF.md`). **Branch** `dev/IP5` from `main`
`e4b5eec` (worktree `wt-ip5`; database `league_lab`, read only — nothing written anywhere). Security notes:
docs/SECURITY_PUBLIC.md § 15. Words: docs/WORDS.md § "Player pages that share, and "busy" for a refused read".

## 1. A refused provider read is never remembered as "nothing there" — done

`src/league_lab/provider_trouble.py` (new): the Sleeper and MFL clients `note()` a read that raises (refused or failed
with nothing held); a cache builds inside `watch()` (a context variable holding mutable counters: pools that carry the
request's context — § 13's rule — count into it); a troubled build is not kept; `kept(region, key, build, ttl, stamp)`
keeps `(stamp, fresh_until, value)` and serves the last good value for a troubled or refused rebuild, else
`SleeperBusy` (503 "busy, try again in a minute"; the web retries). A held value served is taken back off the outer
watches, so the cache around it still keeps its answer. The full table, every cache with before / after, is
SECURITY_PUBLIC § 15. In short:

| Cache | Before (refused / failed / nonsense) | Now |
|---|---|---|
| Sleeper client per path | held or raised / held or raised / **an empty body kept as data** (rosters `[]` 10 min, users a day, the directory `{}` a day) | the same + noted / the same + noted / a failure (held, else raised) |
| Sleeper directory on disk | read only under a day old | any age answers a refusal or failure |
| MFL client per URL | held or raised; **a 429 raised past a held answer** / held or raised / **an empty body kept a day** | 429 serves the held answer; all noted; an empty body is a failure |
| MFL id mapping (`MFLLeagues.translate`) | refused → ids recorded as "MFL player <id>", no position (a defense lost) | busy, nothing recorded |
| injury report copy | held / held / **0 entries replaced the held copy** (and the disk copy) | the held copy stays (counted failed) |
| ESPN news per athlete | held / held / **`{}` replaced the held items** | a failure, held kept |
| roster contexts (`contexts`; My Week, Team, Waivers, card, trades) | a swallowed refusal **kept 10 / 2 min** under a key without the directory's stamp | never kept; the roster's last good context (≤ 1 h) with its stamps, else busy |
| decision memos (`decisions`) | swallowed → kept 10 / 2 min | not kept, busy |
| `league_weeks`, `ros` (anyleague) | swallowed → kept 5 / 10 min (`ros`: units renamed `TMQB-KC` when the directory read was refused) | not kept (`ros`: busy) |
| outlook (IO-2) | refusals not kept; **a failure counted as clean** (MFL standings down → 0-0 records kept 2 min) | failures counted too: not kept |
| ESPN / Yahoo clients | ESPN sound; **Yahoo raised a 429 / 999 past a held answer** | ESPN unchanged; Yahoo serves the held answer (`tests/test_ip5_providers.py`) |
| il4 free agents, outlook cards / store, scoring checks, research, matchup board, priced weeks, boards | sound as built or no provider read | unchanged |

Behaviour change to know: an MFL league whose standings or live-scoring export **fails with nothing held** (cold) now
answers busy where it showed 0-0 records or last week's starters; a held copy answers as before.

Tests (`api/tests/test_ip5.py`, one per cache, each refuses or breaks the read and then proves the next reader gets
the real answer): the Sleeper empty directory, null rosters (held served), refusal noted; the directory's disk copy of
any age; MFL's empty body, its 429; MFL's id lookup (unit: nothing recorded; route: My Week 503 busy then the full
roster, no "MFL player"); the watch across a pool and nested; `kept` (busy with nothing held, then kept, then the held
value with the outer cache clean); the decisions memo; the roster contexts (not kept, then kept, then the held one for
a troubled rebuild under a new stamp); `league_weeks` and `ros_table`; My Week refused → 503 busy → the lineup; the
injury and news feeds; the outlook with a failed MFL export (503, nothing kept, then the 12-team answer kept).

## 2. MFL's League screen — the same numbers, ~20 % less CPU; about 2 s cold (not reliably under)

Profiled on the fixtures, `LEAGUE_LAB_AVAILABILITY` off and on (on = the ESPN fixtures): power part 1.95 s off / 2.03 s
on, the whole answer after it 0.70 / 0.82 s (load avg 2.7; on `main` the whole answer with the overlay on was the 500
in item 1). The power part = the lineups' board (`_context`: the rosters solved for the horizon, MFL's EV pricing of
every line) + the rest-of-season board (`ros_table`: every week to the final). Fixed, numbers unchanged:

* `unit_lines`' starter rule in one pass (was 32 teams × 15 weeks of `.loc`; ~1.0 s under load → 0.15 s);
* the window's TMQB lines priced in one `price_lines` call (was one a week) and its unit rows read as plain dicts
  (TMQB and TMPK; ~0.67 → ~0.2 s profiled);
* tried and dropped: building the rest-of-season board in a thread beside the lineups' board (no measurable gain on a
  loaded box; not shipped).

| `GET /api/league/outlook?league=mfl:70587&team=1&part=power` (this box, 2 cores shared by five devs) | main `e4b5eec` | `dev/IP5` |
|---|---|---|
| cold process (load avg 3.3–4.2): wall | 2.56 s, 3.11 s | 1.96 s, 1.96 s, 1.99 s (one 4.85 s at load 3.9) |
| cold process: CPU of the process | 2.10–2.31 s | 1.68–1.86 s |
| a warm process, the league cold (another league opened first): CPU | 1.86 s | 1.44–1.55 s (wall 1.58 s at load 2.7) |
| **the live-like path**: a fresh `uvicorn` on the fixtures (port 8965), `curl` the power part first (load 1.6) | 2.56 s | 1.99 s, 2.21 s |
| … then `/api/league`, then the whole outlook | 0.12 s, 0.80 s | 0.09–0.11 s, 0.75–0.80 s |

So: about 2 s cold (−0.4 to −0.6 s), **not reliably under 2 s** on this box; the CPU is ~20 % lower everywhere.

Where the rest goes (thread CPU, warm): rest-of-season board 0.70 s (skill lines 0.25, units 0.19, the window's read
0.18), lineups' board 0.55 s (four weeks priced 0.35: MFL's per-threshold yardage odds), league inputs 0.07 s. Next
(not done): weeks 4–7 are priced twice (the horizon board and the window) — one price cache for both.

**Equality** (`<scratchpad>/ip5/capture.py`; run on `main` `e4b5eec`'s code, on this branch after item 1, after
each item-2 step and on the final code): 18 answers — the outlook's power part and whole answer, `/api/league`,
`/api/ros` (points, `source=sleeper` / Team for MFL, the lineup view) for `mfl:70587` (team 1), League of Scrubs
(team 2) and Forever Unclean Dynasty (team 12) — **150,736 numbers, byte-identical JSON** (7.57 MB) apart from MFL's
`roster_updated_at` (the fetch time); `main` against the final branch included.

## 3. The "best corners" split — removed

As-of it would be honest only as a description of noise: 184 receivers have a split (2025 + 2026 weeks 1–4); the
median receiver has **3** games against a top-quarter corner (90th percentile 6, at most 9), a per-game mean with a
95 % interval of about ±8 points, beside a call IO-1 graded on 2,190 receiver-games as no measurable effect. The web
never showed it (only `/api/matchups/cb`'s `cover_split` and the Streamlit console); the answer keeps the key, always
null, and two queries per request are gone. The console's own copy is the PO's file (line below).

## 4. Player pages that share — done

`api/league_lab_api/player_share.py` (new), marked blocks in `main.web` and `blog.sitemap`. Example (the fixtures,
pinned to 2026-10-03): title **"Josh Allen (QB, BUF): 23.8 projected this week, 14–35 · isuckatfantasy"**, description
**"Week 4, Half PPR: vs NE, Sun 1 PM ET; the highest projection of 93 quarterbacks this week. 8 in 10 weeks like this
land between 14 and 35 points."** Only from the matchup board's frame this process holds for Half PPR (a crawler's hit:
0 queries, 0 provider calls, nothing built — tested); cold → the default card, no players in the sitemap. The sitemap
lists the 200 highest projections. `?league=` anywhere → `X-Robots-Tag: noindex` + the robots meta tag.

## 5. The nightly: three ways it leaves the site on yesterday's numbers (read only; the PO's files)

1. **A hard step fails the same way three times.** `migrate`, `restore-state`, `dbt-build`, **`backtests`**,
   `projection-marts` and `sync-hosted` stop the night before the sync; the Worker's re-checks (09:37, 11:37) and the
   13:07 cron rerun the same commit and fail the same way. Tonight's risk: a `MODEL_VERSION` bump (IP-1) makes
   Wednesday's night run `backtest-v2` for the first time (~15 extra minutes) as a **hard** step. Self-healing: run
   the backtests soft (or after the sync) when an older model's backtest exists; on a `dbt-build` failure, build again
   with the failing node's descendants excluded and publish the rest (their hosted tables stay as they were).
2. **The re-check's "today" is UTC.** The Worker and the `gate` job count any success since 00:00 UTC; a manual run
   that succeeds after 20:00 EDT (tonight's merge, say) is "today" for the next morning, so if the 07:37 run fails,
   the 09:37 / 11:37 re-checks and the 13:07 cron all see a success and do nothing — a whole day on yesterday's
   numbers. Self-healing: count only runs created after this morning's 07:37 ET dispatch (Worker `todaysRuns`, the
   `gate` job's `created>=`).
3. **The hosted publish itself.** `sync_to_hosted.sh` drops the previous marts and restores the new copy; its header
   says the swap is not atomic on the free tier, so a connection lost mid-restore (Neon's free compute) leaves the
   marts missing ("the numbers are not ready yet") until a later run; a copy over the size budget exits 6 and keeps
   yesterday's (deterministic: every retry). Self-healing: retry the restore with backoff on a connection error, prune
   what can be pruned (old outlook snapshots, events) before the size check, and say the hosted size in the run
   summary each night so the budget is seen before it is hit.

## Files

Mine: `src/league_lab/provider_trouble.py` (new), `api/league_lab_api/player_share.py` (new), `api/tests/test_ip5.py`
(new, 30 tests), `tests/test_ip5_providers.py` (new, 1), `src/league_lab/anyleague.py`, `src/league_lab/mfl_client.py`,
`api/league_lab_api/availability.py`, `decisions.py` (`_memo` only), `research.py` (the split only), `outlook.py` (`_refusals` only), `blog.py` (the
sitemap only), SECURITY_PUBLIC § 15, this file. **Edits outside my files** (marked IP-5, smallest possible):
`src/league_lab/sleeper_client.py` (`_get`'s refusal / failure paths + `_held_or_raise`, `_players_from_disk(any_age)`),
`src/league_lab/platforms.py` (one `except` in `translate`), `src/league_lab/injury_feed.py` (an empty copy),
`src/league_lab/news_feed.py` (an empty body), `src/league_lab/yahoo_client.py` (one `except` in `get`),
`api/league_lab_api/main.py` (the shell's player case, `noindex`),
`api/tests/test_io2.py` (one assertion changed on purpose: the default League card now carries the robots tag),
`docs/WORDS.md`, `CHANGELOG.md`. `ratelimit.py` untouched: no new route.

New env variables: none. New dependencies: none. New relations: none (a database without anything new answers as
before). Sizes: 0 binary files; about +1,290 / −69 lines (78 KB of added text, docs and tests included).

## Checks

`test_ip5.py` 30 passed, `tests/test_ip5_providers.py` 1 passed. The test files of what I edited (availability, decisions, outlook, the MFL / Sleeper paths,
research, feeds: test_i0a, ib0, ib2, decisions, io2, in6, io4, i0b, ic2, ic4, il2, f3, research, n1, n2, ig2, if2,
h1, i0c, ia2, ie1, ie2, ig1, ig3, ii0, ii1, ii5, ik3, il4, in5): every failure on the known list **except three in
`test_ig2.py`** (`test_what_changed_lists_a_brief_with_its_source`, `…without_the_store_is_if4s`,
`test_the_matchup_evidence_cites_the_event`) — they fail identically on `main`'s code (checked out over the tree;
their answers carry today's real `checked_at`, so the date likely turned them red after midnight UTC); not mine. Root suite
(`check_root.sh`, at the end): 1,553 passed, 4 failed, 0 new. ruff clean; the copy standard clean; `npm run lint` (193 files, 0)
and `npm run build` clean (no web file changed). No e2e: no screen changed.

## The PO lines I need

* `app/pages/5_Matchups.py` (the console): delete the block `with st.expander("His points against the best
  corners"):` (lines 284–306) and `cover_split,` from the import (line 21) — the same look-ahead split.
* Nothing in `scripts/nightly.sh`, the workflow, `render.yaml` or the Dockerfile.

## Next

Note to `provider_trouble` in the ESPN / Yahoo clients and their adapters' four swallow sites; one price cache for
the horizon weeks the window prices again (MFL's power part ~0.3 s); the nightly's three self-healing changes above.

## Fix round (after the independent review; branch `fix/IP5` from `integ/IP` 3d1b76b)

* **M1** — a held answer served past its TTL is noted `stale` by the Sleeper, MFL, ESPN and Yahoo clients (not trouble:
  `TOTALS["stale_served"]`); a build that saw one is served to its requester and kept by nobody (`kept()`,
  `decisions._memo`, `league_weeks`, `ros_table`, the outlook); a cache's own held value counts stale for the caches
  around it; the caches' hold is 15 minutes. Age bound (`provider_trouble.STALE_MAX_S`): rosters 30 min, live scores
  15, standings / status an hour, schedules / settled weeks a day, settings / the directory / players 2 days; a game day
  (Thu / Sun / Mon) rosters 15 and live scores 10; older → busy. The reviewer's script as a test: attacker 16 players
  (stale, not kept), good-2 15 (Sleeper read again); 31 minutes on, the refused attacker gets busy. (The script itself
  now trips before step 1 on its fixed clock: 10,000 s is below this box's monotonic uptime, so the bucket refuses.)
* **M2** — `outlook()` judges a build by its own `watch()`, not the process's counters; test: X refused in its own
  thread during Y's build → Y's build kept.
* **L1** and the grep: fixed — week odds, `mfl_results`, three `decisions` context sites, `MFLLeagues.rosters`
  (standings; starters when both reads are refused) and `_with_live`, `ESPNLeagues.league` (week, status),
  `YahooLeagues._records` / `_week_of`; listed with reasons in SECURITY_PUBLIC § 15.
* The PO's call (listed Low): when everyone's budget is spent, every on-demand build is stale-only → uncached → CPU.
