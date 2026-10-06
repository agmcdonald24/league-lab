# IN-4 hand-back — DFS without the homework: no upload to start, context beyond the projection, stacks

**Task**: Wave I-N (Iteration 24), IN-4. **Branch**: `dev/IN4` from `main` `967b2d9`. **Docs touched**: `docs/DFS.md`
(rewritten for the new flow: § What it does, § Context, § Published slates, § Lineups — stacks / exposure, § The API,
§ Limitations), `docs/WORDS.md` (§ "DFS without the homework"), `CHANGELOG.md` (one bullet under Wave I-N),
`dfs/slates/README.md` (new). Screenshots: `docs/handbacks/in4/` (375 and 1300).

## Done, against the numbered list

1. **DFS opens useful with no file — done.** `/dfs` shows the board at once with context chips (dashed = not in the
   projection), the sentences one tap away, "What the projection already holds" (one line a signal), and **Worth a
   look** per position. Signals: **matchup** (defense vs position + the WR's corner, from IN-3's `matchup_context`,
   imported lazily; "Matchup: not available here." without it); **role trend** (last 2 games played vs the games
   before, ≥ 2; target / carry / snap share, summed ÷ summed; ±5 / ±10 share points; "role up", "role down" or
   nothing); **game environment** (over/under, spread, implied team total). **Weather: not built into the screen** —
   see "in the projection" below and the PO line.
2. **Published slates — done.** `dfs/slates/<season>-w<ww>-<dk|fd>[-<label>].csv`, read once (`LEAGUE_LAB_DFS_SLATES`,
   default `<repo>/dfs/slates`), same parser and limits, ≤ 16 files; `GET /api/dfs/slates` (offered: this week and
   next; `not_offered` with the reason; `unreadable` with the reason, never served), `GET /api/dfs/slate/{id}` (strict
   pattern, then a lookup — never a path; the same answer as `POST /api/dfs/slate`, tested field by field),
   `POST /api/dfs/lineups` takes `slate_id`. `/dfs` opens on the published slate's values; the upload is under "Use a
   different contest's file"; an upload over it has "Back to the published slate". **No real salary file ships.**
3. **Stacks and exposure — done.** `dfs.Stack(with_qb 0/1/2, bring_back, no_def_vs_qb)`: rows only, one per team
   (`Q_t` = its QBs), the objective unchanged; showdown says stacks do not apply; an impossible rule is named (each rule
   tried alone on the base rows). `max_exposure` 10–100 %: each player in at most max(1, ⌊share·N⌋) lineups (always-in
   players exempt). Same 5-second budget, n ≤ 20, one solve at a time. Context chips beside each lineup's players.
4. **Tests and docs — done.** `tests/test_in4_dfs.py` (72), `api/tests/test_in4.py` (24), `web/e2e/in4` (3 tests × phone
   375 / desktop 1300 = 6). `docs/DFS.md` rewritten (it still says the parsers are unverified against real exports).

**Not done / deviations (said plainly)**
* **Weather column**: the forecast is loaded (`intermediate.int_game_weather`: week 5 has 9 outdoor games with a
  forecast, 6 domes) but the API's role (`league_lab_app`) is refused on `intermediate` and `raw`
  (`InsufficientPrivilege`, checked) and no `analytics` relation carries it; this wave ships no new relation, so there
  is no weather column. `dfs.weather_flag` is built and tested for when a mart publishes it (PO decision).
* **"Worth a look" rule changed** from "≥ 2 favourable signals not in the projection" (it can never fire: only the corner
  call is both outside the projection and able to be favourable) to "**≥ 2 favourable, ≥ 1 of them outside the
  projection, no difficult signal outside it**" — `dfs.WORTH_MIN_FAVOURABLE` / `WORTH_MIN_OUTSIDE`, one line to change.
  Without IN-3's module the list is empty and the screen says why.
* A stacked build of 20 lineups often stops at the 5-second budget on this loaded box (numbers below); notes say so.

## Each signal: in the projection or not, and how that was established

Read from `projections.FEATURES_BY_POSITION` (model v3.3) through `dfs.SIGNAL_INPUTS`; asserted for every (signal,
position) in `test_each_label_is_read_from_the_models_input_list`.
* Defense vs his position — **in** (`opp_rank_std`, `opp_allowed_std`, `opp_allowed_l4`, `f_opp_allowed_diff`).
* Cornerback call — **not in** (no input is made of `mart_cb_matchups`).
* Role trend (target / carry / snap share) — **in** (`target_share_l3/_std`, `carry_share_*`, `snap_pct_*`; the model
  reads last 3 games and the season). Routes per dropback — **not in** (`route_participation_l3` excluded), and NULL in
  2026 (0 of ~1,300 game rows have routes), so never shown.
* Game environment — **in** (`implied_team_total`, `spread_line`, `total_line`).
* Weather — **not in** (plan D3's `wx_*` groups are not in the list).

**Betting lines for 2026 week 5: yes** — `analytics.dim_game` has `spread_line` and `total_line` for 15 of 15 games
(weeks 3–4: 16 / 16; weeks 6–7: none yet).

## Numbers (this sandbox, six devs on two cores)

* Coverage, week 5 (DraftKings board): role trend read for 402 backs / receivers / tight ends with a game → 65 up, 45
  down (board: WR 30 / 24, RB 16 / 13, TE 13 / 6); lines for all 30 teams; published synthetic DK file 597 of 599
  matched (FanDuel 598 / 598).
* Timings: context reads cold 1.41 s (once per week, 10 min); projections warm 0.06–0.15 s (348 KB; **32 KB gzipped**;
  520 KB with the matchup signal); `GET /api/dfs/slates` cold 0.69 s, warm 0.01 s; `GET /api/dfs/slate/{id}` cold
  0.60 s, warm 0.05–0.13 s (583 KB, **67 KB gzipped**).
* Lineups, 20 asked, published DK slate: no stack 4.83 s (20/20 proven); QB+2 + bring-back + no DEF vs QB 5.04 s (7, 6
  proven); QB+1 + 30 % exposure 5.03 s (18, 17 proven); FanDuel QB+2 + bring-back 5.20 s (12, 11 proven). Per-QB rows
  gave 4 / 11 / 8 in the same budget; team-level rows are the tighter LP.
* Memory: `dfs_context` 0.13 MB a week (4 entries); `dfs_published` 1.4 MB a built slate (4 entries); a parsed published
  file 0.42 MB (≤ 16 files read).

## Commands run (all green)

`uv run pytest tests/test_in4_dfs.py tests/test_im5_dfs.py` → 220 passed · `cd api && uv run pytest tests/test_in4.py
tests/test_im5.py` → 43 passed; `tests/test_im3.py` (+ im5) 82 passed; `tests/test_ik4.py tests/test_im4.py` 43 passed
· `uv run ruff check src app tests api` clean · `uv run python scripts/copy_standard.py --check` clean · `cd web && npm
run lint && npm run build` clean · `FIXTURES_PORT=8740 npx playwright test --config playwright.fixtures.config.ts e2e/in4
e2e/im5` → 12 passed · `/home/claude/waveIN/check_root.sh /home/claude/wt-in4` → no new failures (4 known) · a live
smoke on :8764 (published list, slate, gzip sizes, a FanDuel stacked build, `/dfs` 200).

## The PO lines I need

* `api/Dockerfile`, after `COPY src/league_lab /srv/src/league_lab`: `COPY dfs/slates /srv/dfs/slates` (the default
  path is `ROOT/dfs/slates` = `/srv/dfs/slates` in the image; `LEAGUE_LAB_DFS_SLATES` overrides).
* Optional (a decision): a weather column needs the forecast in an `analytics` relation (or a grant on
  `intermediate.int_game_weather` to `league_lab_app` and the hosted sync) — not done, by the "no new relation" rule.

## Edits outside my files

`api/league_lab_api/ratelimit.py` — a 4-line marked block `# ---- IN-4` at the top of `bucket_for`: `/api/dfs/slates`
and `/api/dfs/slate/…` (GETs) are `research` (IM-5's `HEAVY_PREFIX = "/api/dfs/slate"` would otherwise make them heavy).
`CHANGELOG.md` (one bullet; created the Wave I-N heading at the top), `docs/WORDS.md` (a new section + one parenthesis in
IM-5's head row). No edit to `main.py` (the new routes ride on IM-5's router), `lib/api.ts`, router or App.

**New env**: `LEAGUE_LAB_DFS_SLATES` (optional; default `<repo>/dfs/slates`). **New dependencies**: none. **New
relations**: none (reads `analytics.fct_player_game`, `analytics.dim_game`, both already on the hosted copy).

## Interfaces

* Reads IN-3's `matchup_board.matchup_context(season, week, gsis_ids)` lazily (`try/except`); tests fake it with the
  brief's exact shape (`sys.modules`). The e2e recordings `projections_dk_matchup.json` / `slate_published_dk.json`
  carry that **test fake's** matchup words (said in the spec's header) — re-record after the merge if wanted.
* New answer fields: players `context` / `worth` / `worth_reasons`; `worth_a_look`, `context_meta` on the projections
  and slate answers; `published`, `slate_id`, `label` on slates; lineups take `slate_id`, `stack`, `max_exposure`.

## Seen, not mine

* The TopBar still says "No league ·" beside the scoring picker (IN-2's file; rule 9).
* `dfs.RATE_BUCKETS` (IM-5) says `/api/dfs/projections` is `read`; `ratelimit.py` puts it in `research` (the limiter is
  right; the dict is stale — `test_im5.py` pins it, so left).
* Republishing a site's salary file on a public page: a person downloads it by hand (no automated collection), but
  whether showing it publicly is within each site's terms is Andrew's call before the first file is pushed.

## Next

Re-record the in4 fixtures on the merged tree (IN-3's real matchup words); a weather mart (PO); a backtest of "Worth a
look" once a few weeks of published slates exist (the record should say whether it helps before it is dressed as one).
