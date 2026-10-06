# Hand-back — IM-5 (Wave I-M): DFS — values, undervalued players and lineups from the site's own salary file

**Branch** `dev/IM5` (from `main` `ab50682`), worktree `/home/claude/wt-im5`. Database `league_lab`, **read only**
(nothing written). Plan sections: the wave brief § IM-5 (items 1–6). The contract: `docs/DFS.md`.

## Done / not done (the brief's numbered list)

| # | Item | State |
|---|---|---|
| 1 | `src/league_lab/dfs.py`: sites as data (DK classic, DK showdown, FD full roster), scoring through Sleeper keys (`scoring.price_projected`, `kdef.price`) with a test per rule, both parsers (BOM, quotes, extra columns, any order, header search + column offset, site / contest detection, refusal in words, 1 MB / 2,000 rows), matching (team codes, unique normalised name + position + team, first-initial step, defense by team; unmatched / ambiguous listed with the reason, never valued), re-pricing + range (nearest reference, scaled), points per $1,000, the slate's straight line per position (≥ 8 or none), gap / z / rank, undervalued / overpriced, ceiling per $1,000, reasons (the app's `cards.reason_pieces`, else `why.explain`'s chain), exact optimiser (MILP, cash / tournament, locks / excludes, DK ≥ 2 games, showdown both teams, FD ≤ 4 a team, next N ≤ 20 distinct, out players excluded and listed, 1 s a lineup with a stated timeout), upload CSV with formula neutralisation | **done** |
| 2 | `api/league_lab_api/dfs.py`: `POST /api/dfs/slate`, `POST /api/dfs/lineups`, `GET /api/dfs/projections` — no league, no team, never stored or logged, one memo region (`dfs`), `RATE_BUCKETS` constant (`heavy` for the POSTs) | **done** |
| 3 | `web/src/routes/Dfs.svelte` + `components/dfs/`: the DFS tab, site switch, projections before a file + the three-step how-to, file / drop / paste, tab memory + `sessionStorage` + Remove file, the slate header with "See unmatched", Undervalued / Overpriced (top 8, position chips, reason), the full sortable value table, Build lineups (cash / tournament, Always in / Leave out, 1–20), lineup cards (players, salary left, total, range, Copy), Download for upload; names open the drawer when a league is open; 375 and 1300, dark and light | **done** (see "approximate" for names with no league) |
| 4 | The words (on the screen and in WORDS): estimates + the record on About (link); "against this slate's salaries, not a promise"; the footer line verbatim; no "lock" / "guaranteed" / "free money" / "beat" (the e2e checks the screen's own text; a player named Drew Lock is a name, not a word) | **done** |
| 5 | Fixtures: synthetic DK classic / DK showdown / FD full from the database's week-5 players (first line says SYNTHETIC), two hostile files, the 3 MB file built in the test; tests `tests/test_im5_dfs.py`, `api/tests/test_im5.py`, `web/e2e/im5/` | **done** |
| 6 | `docs/DFS.md`: what it does, the scoring tables ("as of October 2026 — check the site's rules page"), matching, the value with a worked example, what is approximate / unverified, why salaries are not fetched and what fetching would need, the limitations | **done** |

## Files

New: `src/league_lab/dfs.py`, `api/league_lab_api/dfs.py`, `web/src/routes/Dfs.svelte`, `web/src/components/dfs/{dfs.ts,
FileBox.svelte, HowTo.svelte, LineupCard.svelte}`, `docs/DFS.md`, `docs/handbacks/IM-5.md`, `docs/handbacks/im5/*.png`
(10 screenshots, 0.6 MB), `tests/test_im5_dfs.py`, `api/tests/test_im5.py`, `api/tests/fixtures/dfs/` (generator + 5
CSVs, 140 KB), `web/e2e/im5/fixtures.spec.ts`, `web/fixtures/im5/*.json` (recorded answers, 0.7 MB).
Changed: `docs/WORDS.md` (§ "DFS"), `CHANGELOG.md` (the Wave I-M heading + one bullet).
**Edits outside my files** (IM-3's, each in an `IM-5` block):
* `api/league_lab_api/main.py` (before "the web app"): `from . import dfs as dfs_mod  # noqa: E402 …` and
  `app.include_router(dfs_mod.router, dependencies=[Depends(require_auth)])` between `# ---- IM-5 …` / `# ---- end IM-5`.
* `web/src/lib/router.svelte.ts`: `| "dfs";` added to `RouteName` (after `"watchlist"`), `"/dfs": "dfs", // ---- IM-5` in `NAMED`.
* `web/src/App.svelte`: `dfs: () => import("./routes/Dfs.svelte"),` in `LAZY`; and before `{:else if r.name === "leagues"
  || !league}` a 4-line branch `{:else if r.name === "dfs" && !league}` rendering the screen alone (no frame: TopBar
  needs a league today). With IM-3's no-league mode the PO can drop that branch and let `/dfs?league=ref:half` render in
  the frame (the screen takes `league = null` or any key; it never sends the league to the API).
* `web/src/components/TopBar.svelte`: `| "dfs"` in `Section`; `{ key: "dfs", label: "DFS", screens: [{ name: "dfs",
  label: "DFS", path: "/dfs" }] }` at the end of `SECTIONS`; an icon branch (a price tag) in `icon`. On a phone the bottom
  bar holds five tabs (78 px each at 390).

## Schema in / out

In (read only): `ops.projection_lines`, `ops.projection_ranges`, `ops.kd_lines`, `ops.kd_ranges`,
`analytics_seeds.reference_scorings`, `analytics.mart_player_week_projections` (status), `analytics.mart_kd_week`,
`analytics.dim_game`, `analytics.dim_player` (the "no projection" reason), `analytics.mart_defense_vs_position_current`,
`analytics.mart_player_week_features` + `analytics.fct_player_game` + `analytics.dim_team` (the reasons, `cards.REASON_SQL`).
Every one is already published to Neon. Out: nothing stored; **no new relation, nothing for the sync**.

## Commands

```bash
OMP_NUM_THREADS=1 uv run pytest -q tests/test_im5_dfs.py -p no:cacheprovider                       # 142 passed
cd api && OMP_NUM_THREADS=1 PYTHONPATH=. uv run pytest -q tests/test_im5.py -p no:cacheprovider     # 15 passed
cd api && PYTHONPATH=. uv run python tests/fixtures/dfs/make_synthetic.py                          # the synthetic files (read-only)
cd web && npm run lint && npm run build && FIXTURES_PORT=8650 npx playwright test --config playwright.fixtures.config.ts e2e/im5   # 6 passed
uv run ruff check src app tests api                                                                 # clean
uv run python scripts/copy_standard.py --check                                                      # exit 0
/home/claude/waveIM/check_root.sh /home/claude/wt-im5 ; /home/claude/waveIM/check_api.sh /home/claude/wt-im5
```

## Evidence (numbers)

* **Tests added**: 142 root (`tests/test_im5_dfs.py`: 28 player rules, 9 bonus edges, 1 bonus-at-its-odds, 28 defense
  rules, 8 kicker rules, 1 contests-as-data, parsers 15, matching 15, value 3, optimiser 24 brute-force cases + 9, the
  week 1), 15 API, 6 e2e (3 × phone / desktop).
* **Brute force**: the MILP's best lineup equals exhaustive enumeration on 24 small slates (DK classic, FD full, DK
  showdown × 4 seeds × cash / tournament) and agrees on an infeasible FD slate.
* **Matching, synthetic week 5**: DK classic **597 of 599** (567 by name, 30 defenses by team; the 2 unmatched are the
  planted ones: "Zzyzx Notaplayer" not found, Puka Nacua listed on MIA → "we have that name as WR on LA"); the sites'
  spellings planted (Marvin Harrison, Brian Thomas without "Jr.", AJ Brown, CJ Stroud, TJ Hockenson) all matched; FD
  full **598 of 598** (568 + 30); DK showdown (BUF@LAR) **40 of 40**. 0 matched by the initial step on these files.
* **The value lists** (DK classic): 89 undervalued, 97 overpriced of 597 (z ≥ 1 / ≤ −1 and ≥ 1 point); the screen shows 8.
  Lines: QB 5.21, RB 3.57, WR 2.99, TE 3.12, DST 2.95 points per $1,000 (n 89 / 135 / 206 / 137 / 30). **These say
  nothing about usefulness: the synthetic salaries are made from our own projections.**
* **Solve times** (this sandbox, 2 cores shared by five devs; the 597-player DK slate): the first lineup 0.08–0.3 s;
  3 cash lineups 0.18 / 0.20 / 0.37 s; 20 cash 4–13 s in all (median 0.36–0.68 s, max 1.0 s, 16–20 of 20 proven); 20
  tournament 13–18 s (7–18 proven); FD tournament: lineups 3–5 reach the 1-s box (best found, `proven: false`, the card
  says so); showdown 5 tournament lineups 0.23–0.52 s each. Before the one-variable-per-player change (`5562651`) 20 DK
  lineups took 18 s with a 1.8 s maximum.
* **Route timings** (fixture API, this box): `GET /api/dfs/projections` 0.37 s cold, 0.10 s warm; `POST /api/dfs/slate`
  (DK, 599 rows) 0.93 s; pricing a site-week 34 ms (FD) – 434 ms (DK, first call: M2's curves).
* **Memory**: one region `dfs`, at most 8 entries, 10 minutes: **0.35 MB** a site-week (DK 628 rows, FD 598).
* **Check scripts**: see the final message (verbatim "NEW failures" sections).

## What is approximate or unverified

* **The file formats** (DK and FD headers, defense names / team codes, FD's id shape and defense word, DK's showdown
  pairing) and **the upload headers** are from documentation and memory: unverified until Andrew uploads a real file
  (docs/DFS.md lists each). The parser is tolerant, so a different column order or an extra column does not matter; a
  renamed required column is refused in words.
* **The scoring tables** as remembered for October 2026 — DK's points allowed on the field only, FD's 2-point return
  not projected.
* **The range**: borrowed from the nearest reference scoring (DK → `ppr`, FD → `scrubs`) and scaled — ends ~0.2–0.8
  points off a fitted range on the house leagues, more at QB; DK's +3 bonuses widen the true high end a little more.
* **DK's bonuses are priced at their odds** regardless of the record's mode (`dfs.BONUS_AT_ODDS`; on this clone the
  week-5 record is `flat`): the PO's call to keep or flip.
* **A lineup's range** assumes independent weeks (the card says the real range is wider).
* **No league open**: player names are plain text (the drawer and the player page need a league today); with a league
  in the URL every name opens the drawer and every link keeps `league` / `team`. After IM-3's `ref:` keys the
  no-league screen could link names with `league=ref:half` (a one-line change in `Dfs.svelte`'s `href`).
* The phone hides the table's salary / projection columns (they read under the name), so sorting by salary is a
  640 px+ control.

## The PO lines I need

* **IM-3's limiter**: `POST /api/dfs/slate` and `POST /api/dfs/lineups` in the `heavy` bucket, `GET /api/dfs/projections`
  in `read` (`league_lab_api.dfs.RATE_BUCKETS` holds exactly that map).
* `app/whats_new.md` (PO-owned), newest on top: "**DFS (new tab)**: add your DraftKings or FanDuel salary file and see
  this week's projections in the site's scoring, who is undervalued against the slate's salaries, and lineups you can
  download for the site's upload. The file stays in your browser."
* `docs/STATUS.md` / `docs/HANDOFF.md`: one line pointing at `docs/DFS.md` and this hand-back.
* Optional (IM-1 owns them tonight): `docs/METRICS.md` / `dbt/seeds/metric_registry.csv` rows for the on-request DFS
  numbers (points per $1,000, the slate's line and gap) if the PO wants them registered — they are defined in
  `docs/DFS.md`; nothing in the warehouse computes them.

## New env variables, dependencies

None. (`scipy` was already a dependency of both projects; no npm package added; `web/node_modules` still the symlink.)

## Next

Andrew uploads a real DraftKings and FanDuel file (any slate): check the header words, the defense names and team
codes, FD's defense word and id shape, the showdown pairing, then a real upload of the produced CSV; fix any word in
`dfs._DK_REQUIRED` / `_FD_REQUIRED` / `POSITION` / `TEAM_ALIASES` / `CONTESTS[...].upload_header` and mark them verified in
docs/DFS.md. Then: late swap (kick-off times are in DK's file), a stack rule, FD single game.
