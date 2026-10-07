# IO-4 — the fix list and two things left twice (Wave I-O, 2026-10-06)

**Task**: Wave I-O package IO-4 (`/home/claude/waveIO/BRIEF.md` § "IO-4"). **Branch** `dev/IO4` from `main` `cf8e743`.
Worktree `/home/claude/wt-io4`, database `league_lab` (read only — nothing written). Dev IO-4.

## Done, against the numbered list

1. **Two players, one last name** (`api/league_lab_api/myweek.py`, marked `IO-4`). `short_name(full, position,
   roster)`: the last name; when another player on the roster shares it (`cards.display_name` decides the collision —
   the one roster-aware rule), the first initial ("M. Washington"); when the two share the initial too, the full name;
   a defense or team unit keeps its name. Used by every name My Week says: the actions and reasons (`build_actions`'
   `name` / `plain`), the review lines, the news feed's "Inspect …" (`decision_parts`) and the questionable line. Every
   name in an action comes from the roster's rows, so a collision "in that sentence" is a collision on the roster.
   * Before (Andrew's live roster has Malik and Parker Washington): "Start Washington ahead of Jefferson and
     Croskey-Merritt for now." / "Start Washington at FLEX in place of Croskey-Merritt." / "Washington or
     Croskey-Merritt at FLEX: a coin flip …"
   * After (the IN-5 morning frame + Malik Washington): "Start P. Washington ahead of Croskey-Merritt for now." ·
     "Start P. Washington at FLEX in place of Croskey-Merritt." · "P. Washington or Croskey-Merritt at FLEX: a coin
     flip, 0.1 points apart; your lineup has Croskey-Merritt — no clear upgrade." Mahomes, Jefferson, Croskey-Merritt
     unchanged. The database's League of Scrubs roster 2 (both Washingtons): no bare "Washington" in any action,
     reason or review line (`test_his_roster_from_the_database_has_both_washingtons`).
2. **A lineup holding a player who is gone** (`myweek.gone_actions`). A key of the submitted lineup with no roster row
   is taken out of the pairing; each such spot is one roster alert (kind `change`, urgency 1, `gone: true`, the slot
   label): "A player in your Sleeper lineup is no longer on your roster — set that spot again." (the platform's name
   from `platform_name`); the reason names the best lineup's player left without a spot, if one fits the slot
   ("Our lineup starts Washington there (your FLEX spot).") else "Start someone from your bench there (your RB spot),
   or add a player."; "Not in your Sleeper lineup yet: set that spot in Sleeper.". Before: "Take player no longer on
   your roster out of your lineup." (`last_name` of the placeholder "a player no longer on your roster"). After, on
   the fixtures' finished week 4 (League of Scrubs 2): "A player in your Sleeper lineup is no longer on your roster —
   set that spot again." + "Start someone from your bench there (your RB spot), or add a player." — once per spot.
3. **The matchup board** (`api/league_lab_api/matchup_board.py`, `web/src/components/matchups/Board.svelte`).
   (a) `game_state(kickoff, is_final, now)` from `clock.now()`: None / "started" / "final" (the database's final flag
   counts only for a game that has kicked off by the clock; 4 hours after kickoff is final anyway). Rows of kicked-off
   games go below the games still to come under every sort; `show=to_play|all` (400 otherwise); the default is
   `to_play` once any game of the week has started, `all` when a game is picked (its players, marked) or none has
   started. The answer carries `show`, `started_games`, `started_players`, each row's `game_state`, each game's
   `state`. The screen: **Still to play · All games** chips (only once a game has started; `bshow=` in the URL), a
   **Started** / **Final** badge on the row (phone: on the line under the name; desktop: in place of the kickoff),
   "· Final" in the game list, "… still to play" in the count. (b) In a real league the defense read comes from
   `research.league_dvp` (the heatmap's own frame: `league_defense`), the tone recombined with the same corner call
   (`combine_tone`), the sentence rebuilt, and the opened row's evidence (its defense history) in the league's scoring too (kept per
   league scoring in the board's region); `defense_source` = `league` / `reference`; browsing keeps the reference
   mart (and `matchup_context`, read by the home and DFS, is unchanged). (c) `projection_words()` imports IO-1's
   `context_record` lazily: when `summary()["corner"]["graded"]` is true its `words` replace the last sentence ("Whether
   a tough corner lowers a receiver's points has not been graded yet."); absent, ungraded or raising → today's
   sentence (`PROJECTION_WORDS`, unchanged).
4. **The role-change columns on Stats**. DFS's role trend moved to **`src/league_lab/role_trend.py`** (one
   implementation): `_ratio` / `_parts` (numpy, one player), `shares(games)` (every player of a frame, each a slice of
   the arrays), `role_trend(games, position)` (DFS's call — same words, same thresholds), `change_columns(games,
   positions)` (Stats). Three catalogue columns in a new group **Role change** (after Snaps and routes):
   `target_share_change`, `carry_share_change` (RB only, as on DFS), `snap_share_change` — recent (his last 2 games
   played in the window) minus before (his games before them in the window, at least 2), each part a summed numerator
   over a summed denominator, signed, in points of share on the screen ("+5.2 pts"); definition, numerator,
   denominator, aggregation, reason-when-null; the samples behind them (`_recent`, `_before`, `role_games_*`) on the
   row; in the WR / TE and RB presets' picker (`extra`) and the Full table; sortable (nulls last). DATA_INVENTORY rows.
   `stats.FCT_COLS` reads `offense_snaps` too (DFS's snap share: snaps / (snaps ÷ published share)).
5. **Each client's own share of the providers' budget** (`src/league_lab/provider_share.py`; SECURITY_PUBLIC § 13):
   the limiter's middleware sets `provider_share.CLIENT` (its `client_group`) once a request is admitted; `Sleeper._get`
   and `MFL._get` take the client's share before the global bucket; no client (nightly, CLI, tests — the limiter is
   off there) → unlimited by it. A refusal is `SleeperBusy` / `MFLBusy` (a cached answer first) → 503 "busy, try again
   in a minute". `anyleague.user_leagues`' thread pool hands the context on. SECURITY_PUBLIC's "left" row is now § 13.

## Files

* New: `src/league_lab/role_trend.py`, `src/league_lab/provider_share.py`, `api/tests/test_io4.py`,
  `web/e2e/io4/fixtures.spec.ts`, `web/fixtures/io4/api_io4.json` (2.4 MB: the Stats frames are most of it),
  `docs/handbacks/IO-4.md`, `docs/handbacks/io4/*.png`.
* Mine, edited: `api/league_lab_api/myweek.py`, `api/league_lab_api/matchup_board.py`, `api/league_lab_api/stats.py`,
  `api/league_lab_api/ratelimit.py`, `src/league_lab/sleeper_client.py`, `src/league_lab/mfl_client.py`,
  `web/src/components/matchups/Board.svelte`, `web/src/components/stats/columns.ts`, `docs/SECURITY_PUBLIC.md`
  (§ 13, the "left" row), `docs/DATA_INVENTORY.md` (3 rows).
* **Edits outside my files**:
  * `src/league_lab/dfs.py` (IO-1's): **lines 1214–1273 of `cf8e743`** (the role-trend block: `ROLE_RECENT` …
    `role_trend`'s last line) replaced by **one line, 1214**: `from .role_trend import role_trend  # noqa:
    E402,F401,I001 IO-4: moved, one implementation with Stats`. The comment line 1213 above it and everything else are
    untouched. Nothing else in the repository read `dfs.ROLE_*` or `dfs._ratio` (grep). If IO-1 also edited that block,
    take IO-1's edit into `role_trend.py` and keep the one import line.
  * `src/league_lab/anyleague.py` (unowned): `user_leagues` — `import contextvars` and `ctx = contextvars.copy_context()`,
    `ex.map(lambda lg: ctx.copy().run(one, lg), leagues)` (3 lines, marked).
  * `web/src/lib/api.ts`: a marked block at the end (interfaces merged with IN-3's `BoardRow` / `BoardGame` /
    `MatchupBoard`: `game_state`, `state`, `show`, `started_*`, `defense_source`; `boardShowPath`).
  * `api/tests/test_im1.py`: **changed on purpose** — `ST.GROUPS` gains "Role change", the catalogue 101 → 104.
  * `docs/WORDS.md` (§ "The fix list"), `CHANGELOG.md` (the `## 2026-10-06 — Wave I-O` heading created, one bullet).
* No `main.py` / `router` / `App.svelte` edit, no new route (the board gains the `show` parameter; its bucket is
  unchanged).

## Schema

In: `dim_game.is_final` (exists), `fct_player_game.offense_snaps` (exists, hosted too — DFS reads it). Out: no
relation, no table, nothing written. On a database without this wave's relations: nothing of mine needs one; the
context record's absence keeps today's sentence (tested with a fake module and with none).

## Evidence

* `api/tests/test_io4.py` **23 tests** (My Week 5 incl. the database roster; the board 4 incl. the record; Stats 4 incl.
  the old-vs-new role trend on 1,500 random players — identical answers, 347 trends said; the share 10).
* DFS's tests untouched: `tests/test_in4_dfs.py` + `tests/test_im5_dfs.py` **223 passed**; `api/tests/test_in4.py`
  in the module run below. `role_trend` per call: **0.56 ms** (a first pandas-groupby version took 43 ms a call and was
  thrown away — ~400 players would have made DFS's context ~17 s).
* Module test files — the 44 API files that read myweek / the board / stats / ratelimit (`grep -l`), one run: **726
  passed, 53 failed, 12 skipped** (574 s). 50 failures are on `known_api_failures.txt` by name; the other 3 are
  `test_ig2.py` (`test_what_changed_lists_a_brief_with_its_source`, `test_what_changed_without_the_store_is_if4s`,
  `test_the_matchup_evidence_cites_the_event`): the availability overlay's status lines are empty — IN-5's hand-back
  reports the same three failing on `main`'s code; nothing of mine builds those lines. **Said plainly**: four of those
  existing files write to the database with the pipeline role through their own fixtures — `test_ig2.py` (applies
  `hosted_events.sql`, idempotent; inserts and then deletes its rows in `events.events`), `test_ik4.py`
  (`hosted_accounts.sql`, idempotent; its test rows), `test_ig3.py` / `test_ik3.py` (temporary tables / a rolled-back
  transaction) — so this run touched `league_lab` through them, as the PO's merge run does. Nothing in my code writes.
  I noticed after the run and did not run them again.
* `/home/claude/waveIO/check_root.sh` (I edited `src/`): **1,537 passed, 4 failed — the 4 known, 0 new** (117 s).
* `test_in3.py` 55, `test_in5.py` + `test_in0.py` 20, `test_im3.py` (limiter) 63, `test_ii3.py` + `test_im1.py` 37 +
  1 skipped — all pass. `ruff check src app tests api` clean; `copy_standard.py --check` clean; `npm run lint` (189
  files, 0 errors / warnings) and `npm run build` clean.
* **e2e** `web/e2e/io4` **4 passed** (375 and 1300), on the recordings and against the live fixture API on :8864:
  the board opens on "Still to play" (Thursday's game final under the suite's Saturday clock), All games, the
  Thursday game picked → every row Final; Stats Full table sorted by Target share change (first cell "+17.9 pts",
  Jakobi Meyers), its hover, the dash on a 3-game window with its reason. Screenshots `docs/handbacks/io4/`.
* **The board**, week 4 clock Sunday 2:30 PM ET: 10 of 16 games started, 136 of 219 WRs in them; Saturday: 1 game
  final, 13 WRs, default "Still to play" 206. League of Scrubs WR: every row's defense rank = the heatmap's (100 rows), and its evidence's history rank too;
  on this database the reference and league ranks agree at WR for Scrubs (0 differences) — the change matters where
  the scorings differ.
* **Stats**: 2026 season window, RB / WR / TE, 423 players: target share change for **185**, carry share change for
  **55** running backs, snap share change for **184**; **157** of DFS's week-5 role-trend measures equal the Stats
  columns (±0.0006). `/api/players` (ref:half, season, RB+WR+TE, limit 1,000): **3.2 s cold** (a fresh process: the
  season frame, the league's points), **0.27 s warm**; the role columns inside `stats.aggregate` (once per window, then cached): **24 ms** of 175 ms on
  2026 (1,414 game rows), **34 ms** of 212 ms on 2025 (6,037 rows) (the aggregate itself was already ~150–180 ms).
* **The share**: one unknown Sleeper league cold (My Week, Team, League, outlook) = **11 calls** on the fixtures;
  three in 45 s → 33 calls, **0 refused**; fifty in a minute → refused from the **16th**, 140 of 200 answers 503
  "busy", never a 500; another visitor not refused. MFL `mfl:70587` cold = **14 calls**; three → 0 refused. At a live
  league's 25 / 35 calls, fifty → 6 / 4 built in full.

## Limitations (said straight)

* The fixture league's outlook stops at its missing week 3, so the fixtures under-count a live league's calls; the
  numbers are sized from the PO's live measurement (12–20 outlook calls), not measured live here.
* Many addresses together can still spend the global provider budget (now a Low row in SECURITY_PUBLIC).
* The role-change columns take the window's games: "Last 3 games" cannot hold 2 + 2 and is always a dash (said in the
  reason). The snap share change is summed snaps (DFS's), not the Snap share column's mean of per-game shares (said
  in the definition).
* The board's Started / Final reads `dim_game.kickoff_at` and the nightly's `is_final` (a game is "final" 4 hours
  after kickoff if the nightly has not run).
* `margin_comparator` (the card's "over X" words) keeps `display_name`'s full name on a collision (not an action
  sentence; unchanged).

## The PO lines I need

* None in `scripts/nightly.sh`, `scripts/sync_to_hosted.sh`, `render.yaml`, `api/Dockerfile`. New env variables
  (optional, unset on Render): `LEAGUE_LAB_PROVIDER_SHARE` [`60,150`; `off`], `LEAGUE_LAB_PROVIDER_SHARE_MFL` [`12,50`].
* `dbt/seeds/metric_registry.csv` (IO-1's file this wave) — one row, if the PO wants the columns registered:
  `role_share_change,rt1.0,"his targets / carries / snaps over the team's in his last 2 games played (summed numerator over summed denominator)","the same over his games before them (2+), minus",player-window,available,"IO-4: league_lab.role_trend (DFS's role trend, one implementation); Stats columns target_share_change / carry_share_change (RB) / snap_share_change; null under 2 + 2 games or 20 team targets / carries, 60 team snaps per 2 games"`
* `app/whats_new.md` (optional): "My Week tells your two Washingtons apart (M. Washington, P. Washington); the
  matchup board shows the games still to play first and marks the ones that have started; Stats has a Role change
  group: each player's target, carry and snap share in his last two games against his games before them."

## Seen, not mine

* On the fixtures' finished week 4, League of Scrubs 2: "Start Folk at K in place of Jefferson." — a kicker paired
  with an outgoing receiver; the fixture's Sleeper lineup is older than the database's roster (its slots do not line
  up), so `pair_moves` reads a K slot for Jefferson. Probably a fixture artefact; worth a look with a live lineup.
* `myweek.pair_moves` pairs an incoming receiver with an outgoing tight end through the slot chain while the TE spot
  is reported open ("Start Washington at FLEX in place of Kelce." beside "Your tight end spot is open"), seen on a
  hand-built frame — IN-5's.
* `src/league_lab/roles.py` (IL-1's "role change", registry `role_change`) is a third measure of a role change, with
  per-game counts and a standard-deviation rule: two different "role change" ideas now have screens.

## Commands

`OMP_NUM_THREADS=1 uv run pytest tests/test_io4.py -q` (api/) · `uv run pytest tests/test_in4_dfs.py
tests/test_im5_dfs.py -q` · `uv run ruff check src app tests api` · `uv run python scripts/copy_standard.py --check` ·
`npm run lint && npm run build` (web/) · `FIXTURES_PORT=8840 SHOTS_IO4=../docs/handbacks/io4 npx playwright test
--config playwright.fixtures.config.ts e2e/io4` · re-record: the fixture API on 8864 serving `web/dist`, then
`IO4_LIVE=http://localhost:8864 …`.

## Next

Measure one live unknown league's calls (the share's numbers rest on the PO's 12–20); a per-/48 share if many-address
spending is ever seen; the role-change columns on the player card.

## Fix round (branch `fix/IO4` from `integ/IO` `72d959b`)

1. **The corner moves nothing** (the PO's decision on IO-1's grade). `combine_tone` = the defense's tone (signature
   kept); `cb.tone` always None, `cb.tier` added (the quarter, so DFS's graded chip can still find its tier — IO-1's
   `dfs.py:801` reads `cb.get("tone")`: it should read `{"shutdown": "difficult", "target": "favorable", "solid":
   "neutral"}.get(cb.get("tier"))`, else the chip loses its graded words for ranked corners); `context.words` the
   defense's sentence; the corner's words in plain quarters ("a top-quarter corner, #3 of 74"). Board: "top-quarter
   corner" in grey (no red badge); My players' corner card: a neutral chip (Top-quarter / Middle-half / Bottom-quarter /
   Unranked corner, Either corner, No call) + the certainty; How to read this and the caption reworded; the home's line
   = the defense's sentence (`home.ts`, marked); the best-corners split carries a note (`research.COVER_SPLIT_NOTE`).
   Honesty line without the record: "What the projection counts: … Who plays cornerback is not in it: the corner call
   is a lean from where his targets go, shown for context."; with it: the same + IO-1's sentence. METRICS mb1.1,
   INTERFACES § IN-3, the registry row `matchup_tone` → mb1.1, WORDS.
2. **Review L3**: `availability.contexts` carries the context; every pool listed in SECURITY_PUBLIC § 13;
   `test_every_pool_carries_the_client_or_says_why_not`, `test_the_roster_contexts_pool_carries_the_client`,
   `test_starlettes_threadpool_carries_the_client`.
3. Changed on purpose: `test_in3.py` (the 42-case tone table: the four a likely corner moved now the defense's; CB_KEYS
   + tier; the not-expected corner's words in `cb.words`), `web/e2e/in1` (homeWords: the defense's only), `web/e2e/ib3`
   (the corner card's `cb-info` chip, no `tone-chip`). Re-recorded: `web/fixtures/io4/api_io4.json`,
   `web/fixtures/in3/api_in3.json` (live from the fixture API on the merged tree), the five board answers in
   `web/fixtures/in1/api_in1.json`.
