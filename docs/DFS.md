# DFS: the week's board with its context, published slates, values and stacked lineups (IM-5, rewritten for IN-4)

Andrew (2026-10-05): "dfs recomendations/undervalues"; (2026-10-06): "I don't think making somebody upload the DFS
salaries is a very solid user experience … a way to find value, people who might be undervalued … things that might
even be beyond what the model can provide for. Like cornerback matchups don't necessarily play into the projections."
The screen is **DFS** (`/dfs`, its own tab); it works with no league and no team. Code: `src/league_lab/dfs.py` (pure:
sites, scoring, parsers, matching, value, the context signals, the optimiser with stacks, upload CSV, published-slate
names), `api/league_lab_api/dfs.py` (five routes), `web/src/routes/Dfs.svelte` + `web/src/components/dfs/`. Tests:
`tests/test_im5_dfs.py` (148), `tests/test_in4_dfs.py` (72), `api/tests/test_im5.py` (19), `api/tests/test_in4.py` (24),
`web/e2e/im5/fixtures.spec.ts` (6) and `web/e2e/in4/fixtures.spec.ts` (6), phone 375 and desktop 1300.

## What it does (the flow since IN-4)

1. **It opens useful, with no file.** `/dfs` shows the week's board at once: every player priced in the chosen site's
   scoring (DraftKings or FanDuel) with his low-end to high-end outcome, the opponent, and **the context the projection
   does not hold** as chips beside him (§ Context): the matchup (the defense against his position and, for a receiver,
   the cornerback), his **role trend**, the **betting line**. Tap a player for the sentences, each saying "In the
   projection" or "Not in the projection". **Worth a look** per position lists the players with the signals in their
   favour (§ Context), ordered by projection — labelled as context, not a graded forecast.
2. **Published slates: nobody has to upload.** When the site's salary file for the week is in the repo
   (`dfs/slates/<season>-w<ww>-<dk|fd>[-<label>].csv`, § Published slates), `/dfs` opens on its values: points per
   $1,000, undervalued / overpriced against the slate's salary line, Worth a look ordered by points per $1,000, the
   context beside every number. **"Use a different contest's file"** keeps the upload as the second path (another
   contest has other salaries), in a quieter place; with nothing published the upload box sits beside the board.
3. **An uploaded file** (a file, a drop or a paste) is parsed in one request, matched to our players, valued, and kept
   **in that browser tab only** (memory and `sessionStorage`, one slate per site; "Remove file" drops it and goes back
   to the published slate when there is one). The server stores nothing and logs nothing of it.
4. **Value**: for every matched player — projection, range, points per $1,000, high-end outcome per $1,000, the slate's
   salary line at his position, his gap to it (points, and rank), and the call **undervalued** / **overpriced** with one
   plain reason. Lists of the top 8 each (by position chip) and the full sortable table, with a Context column.
5. **Lineups**: an exact optimiser for the site's slots and cap on projected points (cash) or the high-end outcome
   (tournament), with players set to "Always in" / "Leave out", the site's team rules, **stacks** (the quarterback with
   one or two of his pass catchers, a bring-back from his opponent, no defense against him) and a **maximum exposure**
   per player across the lineups, 1–20 lineups each different by at least one player; each card with its players and
   their context chips, the salary left, the projected total and its range; **Copy**, and **Download for upload** in
   the site's lineup-upload CSV with the file's own player ids.

## Context beyond the projection (IN-4)

Each signal is **shown beside the projection, never folded into it**, and says whether the projection already holds it.
That label is not written by hand: `dfs.SIGNAL_INPUTS` lists the columns each signal is made of and `dfs.in_projection`
checks them against the model's own input list, `projections.FEATURES_BY_POSITION` (v3.3);
`tests/test_in4_dfs.py::test_each_label_is_read_from_the_models_input_list` asserts every (signal, position).

| Signal | What it reads | Tone | In the projection? (how we know) |
|---|---|---|---|
| **Defense vs his position** | `matchup_board.matchup_context(...)["defense"]` (IN-3: the marts' standard rank, `defense_tone`) | IN-3's | **In the projection**: `opp_rank_std`, `opp_allowed_std`, `opp_allowed_l4`, `f_opp_allowed_diff` are inputs at every position |
| **Cornerback** (WR only) | `matchup_context(...)["cb"]` (`mart_cb_matchups`: the likely corner, his rank, shutdown, the certainty) | IN-3's; **only a "likely" call carries a tone** (an unclear call is said, never counted) | **Not in the projection**: no model input is made of the corner call |
| **Role trend** (RB, WR, TE) | `analytics.fct_player_game`, his **last 2 games played against his games before them** (at least 2): target share, carry share (RB), snap share — each the summed numerator over the summed denominator; team snaps = his snaps ÷ his snap share; a measure moved at ±5 points (targets) or ±10 (carries, snaps); "role up" when one moved up and none down, "role down" the other way, else nothing; a game without the measure makes it unknown, not 0 | favourable / difficult | **In the projection**: the model reads his share over the last 3 games and the season (`target_share_l3`, `_std`, `carry_share_*`, `snap_pct_*`). Routes run per dropback would not be (`route_participation_l3` is not an input), but routes are not available during the season (the participation file arrives after it), so it never shows |
| **Game environment** | `analytics.dim_game` `spread_line` (> 0: the home team favoured), `total_line`; the team's implied total = (total ± spread) ÷ 2, `int_player_week_universe`'s formula | favourable at 26+ expected points, difficult at 18 or fewer (the cards' marks) | **In the projection**: `implied_team_total`, `spread_line`, `total_line` are inputs. 2026 week 5: lines for **15 of 15** games |
| **Weather** | — | — | **Not shown.** The forecast is in the database (`intermediate.int_game_weather`, Open-Meteo; week 5: 9 outdoor games with a forecast, 6 domes) but the site's database role reads `analytics` and `ops` only and no analytics relation carries it; this wave ships no new relation. `dfs.weather_flag` (wind 15+ mph, snow, rain 0.1 in+, below freezing; difficult for a passer or receiver) is built and tested for the day a mart publishes it. It is **not in the projection** (plan D3 tested it; not kept) |

**Worth a look.** The brief's rule was "at least two favourable signals that are not in the projection". Read from the
model, only the corner call is both outside the projection and able to be favourable — so that rule could never fire.
The rule used: **at least 2 favourable signals, at least 1 of them not in the projection, and no difficult signal
outside it** (`dfs.WORTH_MIN_FAVOURABLE`, `WORTH_MIN_OUTSIDE`: one line to change). In practice: receivers likely
facing a soft corner with another signal for them. Without IN-3's module the list is empty and the screen says why.
Ordered by projection on the board, by points per $1,000 on a slate; who cannot play is left off. **There is no
backtest behind it** and the screen says so.

Week 5 (2026, the clone): of the 402 backs, receivers and tight ends with a game this season, **65 read "role up" and
45 "role down"** (on the DraftKings board: WR 30 / 24, RB 16 / 13, TE 13 / 6); the rest have nothing said (flat, mixed,
or fewer than 4 games). Betting lines for all 30 teams playing.

## Published slates (IN-4)

* **The folder**: `dfs/slates/` in the repo (`LEAGUE_LAB_DFS_SLATES` overrides; `/srv/dfs/slates` in the image — the
  Dockerfile copies it). How to publish: `dfs/slates/README.md`. **No real salary file ships with the code** (we have
  none); the tests publish the synthetic fixtures into a temporary folder.
* **The name**: `<season>-w<ww>-<dk|fd>[-<label>].csv` (`dfs.SLATE_FILE_RE`; label: lower-case letters and digits, up
  to 20; default `main`). The id is the name without `.csv`, label always written: `2026-w05-dk-main`.
* **Read once** per process (the folder ships with the image: a new file is a new deploy), at most 32 files, each
  parsed by the same parser with the same limits as an upload (1 MB, 2,000 rows, 200 columns, 300-character cells); a
  link is refused. **Unreadable** — a name off the pattern, a second file for one id, a parse refusal, a DraftKings file
  named FanDuel — is listed with its reason (`GET /api/dfs/slates` → `unreadable`) and **never served**.
* **Offered**: this week's and next week's files only (the app's week rule); any other week is listed under
  `not_offered` with the reason — a past week's slate is never offered as this week's.
* **The id is never a path**: `GET /api/dfs/slate/{id}` matches `dfs.SLATE_ID_RE`, then looks the id up in what was
  read; anything else is 404 "No published slate by that name for this week." (tested with `../`, an encoded slash,
  `.csv`, capitals, 300 characters).
* **The answer** is exactly `POST /api/dfs/slate`'s for that file (tested field by field) plus `slate_id`, `published`,
  `label`; built once and kept in the `dfs_published` region (4 entries, ~1.4 MB each, 10 minutes).
* **Lineups by id**: `POST /api/dfs/lineups` with `slate_id` in place of `players`: the server takes the slate's own
  players (who can play, or are set always in; the highest projected first past 800).
* **Terms**: a person downloads the file by hand from the contest page (no automated collection); whether republishing
  a site's salaries on a public page is within each site's terms is **Andrew's call** before the first file is pushed.

## Why salaries are not fetched (and what fetching would need)

DraftKings and FanDuel both forbid automated collection in their terms; the PO's tools cannot open either site and
this sandbox cannot reach them. So **nothing fetches salaries**: every site gives its players a salary file on the
contest's page, the user brings it, the analysis comes back. Fetching would need, at least: a licensed data feed (a
paid DFS data provider) or each site's written permission, a store for the salaries (Neon has room for a slate:
~600 rows a slate), and a nightly or hourly job. **A decision for Andrew; not built.**

## The files (as the sites export them — the formats are from documentation and memory, **unverified** against a real file)

| Site | Columns we read | Detected by |
|---|---|---|
| DraftKings (`DKSalaries.csv`, "Export to CSV" on the contest's draft page) | `Position`, `Name + ID`, `Name`, `ID`, `Roster Position`, `Salary`, `Game Info` (`BUF@MIA 10/11/2026 01:00PM ET`), `TeamAbbrev`, `AvgPointsPerGame` | `Salary` + (`Name + ID` or `Roster Position`) + `TeamAbbrev` |
| FanDuel ("Download players list" on the contest's lineup page) | `Id`, `Position`, `First Name`, `Nickname`, `Last Name`, `FPPG`, `Played`, `Salary`, `Game` (`BUF@MIA`), `Team`, `Opponent`, `Injury Indicator`, `Injury Details`, `Tier`, … | `Salary` + `Id` + (`Nickname` or `First Name` and `Last Name`) |

* **Tolerant of**: a byte-order mark, quoted fields, `$7,200` salaries, extra columns, any column order, header names in
  any case, leading blank or instruction rows (the header is searched in the first 15 rows) and a column offset
  (DraftKings' entry template puts the player list to the right of the entries).
* **Contest type**: DraftKings — a `CPT` roster position → **showdown** (each player twice: a CPT row and a FLEX row,
  own id, own salary; paired by name + position + team), else **classic**; anything else ("Tiers", "Snake") is refused
  in words. FanDuel — **full roster**; a file with kickers or an `MVP` position is FanDuel's single-game contest and is
  refused in words.
* **Refused in words** (`dfs.SlateError`, HTTP 400; 413 for size): not a salary file ("That does not look like a
  DraftKings or FanDuel salary file: expected a column named Salary and either Name + ID and TeamAbbrev (DraftKings) or
  First Name and Last Name (FanDuel). The first row has: …"), a missing column, over **1 MB**, over **2,000 rows**, not
  text, no player readable. A row with an id that is not a site id (`=1+1`), an unknown position or a salary that is
  not a number is **skipped and listed** with its row number and reason.
* **Bounded work (the security review, IM-5 fix)**: before parsing, a line with over 400 commas is refused; after it, a
  row over **200 columns** (`MAX_COLS`) or a cell over **300 characters** (`MAX_CELL`); the header is searched in the
  first 15 rows, a block tried only where a known header word (`HEADER_WORDS`) follows an empty cell — linear in the
  file. The review's body (`"a,,"` repeated to 1 MB) is refused in milliseconds (it took ~1,000 s before).
  A body over the server's Guard limit (`LEAGUE_LAB_MAX_UPLOAD_KB`, 2 MB on `/api/dfs/`) is refused by the Guard (413
  "That is more than this server takes in one request."); between 1 MB and that limit, by the route (413 "… under 1
  MB"); the screen shows one sentence for either: "That file is too big: a salary file is under 1 MB. …" (and refuses a
  file or a paste over 1 MB before sending it).
* **Formulas**: a cell like `=cmd|' /C calc'!A0` is text to us, never evaluated; the CSV we **produce** prefixes any
  cell starting with `=`, `+`, `-`, `@`, a tab or a carriage return with an apostrophe (`dfs.safe_cell`, OWASP's rule).
* **Unverified until Andrew uploads a real file**: the exact header spellings; whether DraftKings' `Name` for a
  defense is the nickname ("Bills") and whether its `TeamAbbrev` uses `JAX` / `LAR` / `WAS`; FanDuel's defense position
  word (`D` assumed; `DST` / `DEF` also read), its team codes (`JAC`, `LAR`, `WSH` all mapped), whether its file has a
  `Roster Position` column, its id shape (`<slate>-<player>` assumed; any letters, digits, `-`, `_` up to 40 are read);
  DraftKings' showdown CPT salary being exactly 1.5× (we use the file's number, never compute it); the lineup-upload
  headers (`QB,RB,RB,WR,WR,WR,TE,FLEX,DST`, `CPT,FLEX×5`, FanDuel `QB,RB,RB,WR,WR,WR,TE,FLEX,DEF`) and that ids alone
  are accepted there (DraftKings is documented to take an id or "Name (id)"; we write the id).

The fixtures are **SYNTHETIC** (`api/tests/fixtures/dfs/make_synthetic.py`, first line of every file says so): the
database's week-5 players, teams and games with invented salaries — a straight line in our own projection plus noise,
rounded to $100 and clipped to each site's usual range — plus awkward rows (no suffix, no periods, a "traded" player, a
name we do not have) and two hostile files. **Because the salaries are made from our own projections, the synthetic
slates cannot say whether the value calls are useful** — only that the arithmetic is right.

## Scoring — as of October 2026, check the site's rules page

In Sleeper's keys (`dfs.SCORING`), so the stored stat lines are priced by the house engine (`scoring.price_projected`,
`kdef.price`). One test per rule in `tests/test_im5_dfs.py`.

| Rule | DraftKings | FanDuel |
|---|---|---|
| Passing yard | 0.04 (1 per 25) | 0.04 (1 per 25) |
| Passing TD | 4 | 4 |
| Interception thrown | −1 | −1 |
| Rushing / receiving yard | 0.1 (1 per 10) | 0.1 (1 per 10) |
| Rushing / receiving TD | 6 | 6 |
| Reception | 1 (full PPR) | 0.5 (half PPR) |
| Fumble lost | −1 | −2 |
| 2-point conversion (pass, rush, catch) | 2 | 2 |
| Punt / kick / FG return TD; offensive fumble recovery TD | 6 | 6 |
| 300+ passing yards | +3 (once: a 450-yard game is +3) | — |
| 100+ rushing yards / 100+ receiving yards | +3 each (once) | — |
| Defense: sack / interception / fumble recovery | 1 / 2 / 2 | 1 / 2 / 2 |
| Defense: return or defensive TD / safety / blocked kick | 6 / 2 / 2 | 6 / 2 / 2 |
| Points allowed 0 / 1–6 / 7–13 / 14–20 / 21–27 / 28–34 / 35+ | 10 / 7 / 4 / 1 / 0 / −1 / −4 | 10 / 7 / 4 / 1 / 0 / −1 / −4 |
| Kicker (DraftKings showdown only): FG 0–39 / 40–49 / 50+ / extra point | 3 / 4 / 5 / 1 | — (no kicker) |

**Not projected (priced 0, as on every screen)**: 2-point conversions, return and fumble-recovery TDs for players, the
defense's 2-point return. **Approximate**: the sites count points allowed only while the defense is on the field (a
pick-six thrown by its own offense does not count); kd1.0 projects the points the team allows, all of them.

**The +3 bonuses are priced at their odds** on DraftKings (`dfs.BONUS_AT_ODDS`): 3 × P(yards ≥ 100) from M2's
threshold curves (`scoring_ev`), whatever the record's pricing mode — an all-or-nothing bonus on a projected mean puts a
3-point step between a back projected 99 yards and one projected 101, which a salary comparison cannot carry
(`test_dk_bonus_priced_at_its_odds_on_a_projected_line`). FanDuel has no bonus: the flat engine, bit for bit.

## The range

The model's ranges are fitted per **reference scoring** (`ops.projection_ranges`: `scrubs` half PPR, `dynasty`, `ppr`,
`standard`, `te_premium`). A site's scoring is not one of them, so the range is borrowed exactly as an unseen league's
is (`anyleague.reference_for` → `approximate_ranges`, docs/ANY_LEAGUE.md § "The ranges"): the reference whose prices of
the week's stat lines are closest (median |log ratio|) — **DraftKings → `ppr`, FanDuel → `scrubs`** (week 5 on the
clone) — and each of its offsets scaled by the ratio of the two prices of the same line. Measured on the two house
leagues, this approximation lands the ends of the 80% range 0.2–0.8 points from a fitted one on average (1.2–1.5 at
QB). **Approximate**: DraftKings' +3 bonuses widen the true high end a little beyond the scaled `ppr` range. K and DEF:
the nearest reference's fixed offsets (kd1.0), no 50% range. Low-end = P10, high-end = P90 (WORDS § dictionary).

## Matching to our players (`dfs.match`)

A site's player has no id we hold (nflverse's id table has no DraftKings or FanDuel id), so the match is by name —
**the last resort AGENTS.md allows, under its rule**: unique on name + position + team, never guessed.

1. The site's team code → nflverse's (`JAC`→`JAX`, `LAR`→`LA`, `WSH`→`WAS`, `OAK`/`LVR`→`LV`, `SD`→`LAC`, `ARZ`→`ARI`,
   … `dfs.TEAM_ALIASES`); an unknown code → unmatched.
2. A team defense → our defense of that team (`DEF:<team>`).
3. The **normalised whole name** + position + team, among the players we project that week: accents dropped, periods,
   apostrophes, hyphens and spaces removed, a generational suffix cut (`D.J. Moore` = `DJ Moore`, `Marvin Harrison Jr.`
   = `Marvin Harrison`, `Amon-Ra St. Brown` = `Amon Ra St Brown`, `Ja'Marr` = `JaMarr`).
4. Else **first initial + last name** + position + team (a nickname: "Gabe Davis" for Gabriel Davis) — reported as
   `initial` in `matched_by`.

Each step needs **exactly one** candidate. Two → "ambiguous: 2 of our WRs on PIT match (…); not valued". None → "no
projection for him this week (unknown, not 0)" when we know him but do not project him, "listed as WR on MIA; we have
that name as WR on LA" when the file and our data disagree (a trade, a position), else "no WR of that name on MIN in our
players". **Unmatched players are listed with the reason, not valued, never in a lineup.** Synthetic week 5: DraftKings
classic 597 of 599 (567 by name, 30 defenses; the two unmatched are the planted ones), FanDuel 598 of 598, DraftKings
showdown 40 of 40.

## The value, with a worked example

* **Points per $1,000** = projection ÷ (salary ÷ 1,000); **high-end per $1,000** = the high-end outcome ÷ (salary ÷
  1,000) (for tournaments).
* **The slate's line**: per position, a **straight line** salary → projected points by least squares over the
  position's players on this slate who project at least 1 point and can play; **at least 8** such players or no line
  (the screen says so). Showdown: one line over the whole slate (every player competes for the same FLEX spots, and the
  sites price showdown on one scale). Why a straight line: salaries are set roughly linearly in expected points, a line
  is readable ("each $1,000 buys 3.0 points at WR"), and a monotone (isotonic) fit puts the most expensive player on his
  own projection — he could never be called over- or underpriced.
* **The gap** = projection − the line at his salary (points); its **rank** within the position (1 = the most
  undervalued); **z** = the gap ÷ the line's typical miss (its root-mean-square residual).
* **Undervalued**: gap ≥ +1 point **and** z ≥ 1 (a typical miss above the line), and he can play. **Overpriced**: gap ≤
  −1 and z ≤ −1, he can play, and his salary is above the position's minimum on the slate (nobody can pay less). The
  screen shows the top 8 of each by gap, by position chip; the answer carries all.
* **The reason**: the app's own pieces (`cards.reason_pieces`: an injury tag, the matchup rank, the betting line, his
  share of the team's targets / carries), the strongest in the direction of the call; else "Why this number" — the
  projection's chain (`why.explain`) or, for a defense, its projected sacks, takeaways and points allowed. Nothing else.

*Example* (synthetic DraftKings classic, week 5): at WR the line is **2.99 points per $1,000** − 7.52 (206 priced
receivers; a typical receiver sits 1.58 points off it). Chris Olave, $6,800, projected **18.58** in DraftKings scoring
(range 8.5–31.0): the line at $6,800 is 12.80, so his gap is **+5.78** (z 3.65, rank 1 of the WRs): **undervalued**, 2.73
points per $1,000, 4.55 high-end per $1,000. Reason: "Olave's share of the targets has climbed three games running (25%
→ 32%)." (The salary was invented; on a real file the same arithmetic runs on the site's own price.)

## Lineups (`dfs.solve_lineups`)

* **The program** (`scipy.optimize.milp`, HiGHS): classic and full roster — one binary per player, each position's
  count between its own slots and its own + the FLEX slots that admit it (DraftKings QB 1, RB 2–3, WR 3–4, TE 1–2, DST 1,
  9 in all), the slots assigned after the solve (each position's own slots take its higher projections, the rest goes
  to FLEX); showdown — a binary per (player, CPT / FLEX), CPT at 1.5× points and the **file's** captain salary. The cap
  (DraftKings $50,000, FanDuel $60,000). **DraftKings classic**: players from at least 2 games; **showdown**: from both
  teams; **FanDuel**: at most 4 from one NFL team (and so at least 3 teams). Objective: projected points (cash) or the
  high-end outcome (tournament; a player without one is left out).
* **Exact**: HiGHS stops within 1e-5 of the bound — under the 0.005-point step every lineup total moves in — so a
  "proven" lineup is the best one. **Checked against brute force** on small slates for all three contests in both modes
  (24 cases, `test_optimiser_matches_brute_force`), plus an infeasible slate.
* **The next N** (1–20): after each lineup, a cut "at most 8 of these 9 players again" (5 of 6 in showdown): each
  lineup differs from every earlier one by at least one player. The totals come out non-increasing.
* **Always in / Leave out** from the table (the brief's locks and excludes; the screen never says "lock"). **Players
  who cannot play** (the availability overlay, else the nightly's injury report, else the file's own FanDuel indicator:
  O, IR, D, NA) are left out unless set to "Always in", and listed under the lineups.
* **Time box (IM-5 fix)**: **5 seconds for all the lineups of one request** (`SOLVE_SECONDS`, shared by the solves:
  each gets what is left). A solve cut short returns its best lineup with `proven: false` (the card: "The solver's
  budget ran out: the best lineup it found, not proven the best."); the lineups found before the budget ran out are
  returned and the notes say "The 5-second budget ran out after 14 lineups: those are the ones shown." The matrix is
  built once as `scipy.sparse` (a few nonzeros a row); each next lineup adds one sparse row.
* **Limits, checked before any solve** (`api/league_lab_api/dfs.py` `_lineups_in`; `dfs.MAX_*`): at most **800 players**
  (a full Sunday main slate is ~600 rows on DraftKings; 800 leaves room for a Sunday-to-Monday slate), **16 games and 32
  teams** (a showdown: 1 game, 2 teams), ids and keys ≤ 40 characters, names ≤ 80, salaries in (0, 100,000], captain
  salaries in (0, 150,000], projections / low-end / high-end finite and in [−20, 150], ≤ 9 players always in. The
  screen sends only the players who can play (or are set always in), the highest projected first past 800.
* **One at a time, off the event loop**: both POSTs run in the thread pool behind a process-wide semaphore of one. A
  second DFS request waits up to 2 seconds, then answers **429** `{"code": "busy", "error": "Another lineup is being
  built right now. Try again in a few seconds.", "retry_after_s": 5}` (`Retry-After: 5`); the screen shows the words.
* **Measured (IM-5 fix, this sandbox under load)**: 800 players × 16 games, 1 lineup: 0.12 s, +8 MB peak RSS; 600
  players, 20 lineups: DraftKings 4.81 s (20 of 20, all proven), +13.5 MB; FanDuel 5.00 s (the budget: 14 lineups, 13
  proven), +31 MB; the review's 2,000-player request: refused in 7 ms before any solve (it took 42 s and 437 MB before).
  A maximal legitimate upload (2,000 rows, 0.2 MB): 0.49 s of CPU cold, 0.27 s warm, +28 MB (matching is dictionary
  lookups, the fit a least-squares line per position: both linear).
* **Stacks (IN-4)** (`dfs.Stack`; classic and full roster — one QB slot; showdown says it does not apply): rows only,
  the objective never changes. Per team t, `Q_t` = the sum of its quarterbacks (≤ 1): **the QB with k of his pass
  catchers** (k = 1 or 2; WR and TE of his team): Σ pass catchers − k·Q_t ≥ 0; **a bring-back**: Σ RB / WR / TE of his
  opponent − Q_t ≥ 0; **no defense against my QB**: x_DEF + Q_t ≤ 1 for each defense whose opponent is t. (One row per
  team, not per quarterback: it is the sum of the per-QB rows, so the tighter one; measured 4 → 7 stacked lineups in the
  budget on a loaded box.) A rule the slate cannot meet is named: with no lineup, each rule is tried alone on the base
  rows and the first one with no lineup is said ("No lineup can meet the quarterback with at least 2 of his own pass
  catchers (WR or TE) on this slate with these players set to always in and left out. Turn that rule off or change who
  is in."); else "No lineup meets all the stack rules together (…)". `test_an_impossible_stack_names_its_rule`.
* **Maximum exposure (IN-4)**: a share in [10%, 100%] of the N lineups; each player in at most max(1, ⌊share × N⌋) —
  after each lineup a player at his cap gets an upper bound of 0. A player set to always in is exempt (in every lineup
  by request). Notes: "Exposure: each player in at most 6 of the 20 lineups."; when the cap leaves fewer distinct
  lineups the note says how many fit ("Only N different lineups fit the cap, the rules and the exposure limit …").
* **Measured (IN-4, this sandbox with six developers on two cores)**: the published DraftKings slate (597 players), 20
  lineups — no stack 4.83 s (20 of 20, all proven); QB + 2, bring-back, no DEF vs QB 5.04 s (the budget: 7 lineups, 6
  proven); QB + 1 with 30% exposure 5.03 s (18, 17 proven); FanDuel (598) QB + 2 + bring-back 5.20 s (12, 11 proven).
  The 5-second budget and its notes are unchanged: a stacked build of 20 often stops early and says so.
* **The lineup's range**: the low-end / high-end outcome of the total if the players' weeks were independent (each
  player's spread from his own P10–P90 as a normal, the variances added). Teammates and opponents are not independent
  (a shootout lifts both): the real range is wider, and the card says so.

## The upload CSV (`dfs.upload_csv`)

Header row of slot words, one row per lineup of the file's own ids in the header's order: DraftKings classic `QB, RB,
RB, WR, WR, WR, TE, FLEX, DST`; showdown `CPT, FLEX, FLEX, FLEX, FLEX, FLEX` (the captain's own CPT id); FanDuel `QB,
RB, RB, WR, WR, WR, TE, FLEX, DEF`. Every cell through `safe_cell`. Built on the server (tested), downloaded from the
browser (`isuckatfantasy-<contest>-<n>-lineups.csv`).

## The API

| Route | In | Out | Limiter (IM-3's terms; `dfs.RATE_BUCKETS`) |
|---|---|---|---|
| `GET /api/dfs/projections?site=dk\|fd&week=&position=&limit=` (week: this week or the next only, else 400 `bad_week`) | — | `{site, site_name, season, week, players: [{key, gsis_id, player_name, position, team, opponent, proj, p10, p25, p75, p90, status, out, matchup, context: [signal], worth, worth_reasons}], reference, scoring, bonus_at_odds, worth_a_look: {position: [keys]}, context_meta}` (a team on a bye left out; default week: the app's week rule). A signal: `{signal, label, tone, words, in_projection, projection_words, …}`; `context_meta`: `{matchup, matchup_words, lines, forecast, projection: {signal: {position: bool}}, in_words, out_words, words, worth_rule}` | `research` (ratelimit's table; IM-5's `RATE_BUCKETS` said read) |
| `GET /api/dfs/slates?site=` (IN-4) | — | `{season, week, slates: [{id, site, site_name, label, season, week, contest, contest_label, on_file, matched, unmatched}], not_offered: [{id, reason}], unreadable: [{file, reason}]}` | `research` |
| `GET /api/dfs/slate/{id}` (IN-4; `id` from `dfs.SLATE_ID_RE`, 404 otherwise) | — | the `POST /api/dfs/slate` answer for that file + `slate_id`, `published: true`, `label` | `research` |
| `POST /api/dfs/slate?week=` | the file's text (`text/csv`, or JSON `{"text": …}`) | `{site, contest, contest_label, cap, season, week, games, players: [... + context, worth, worth_reasons], unmatched, skipped, matched_by, counts, fit: {position: {slope_per_1000, intercept, n, rmse, words} \| null}, undervalued: [keys], overpriced: [keys], notes, scoring, bonus_at_odds, worth_a_look, context_meta, published: false, slate_id: null}`; the week = `?week=`, else the one whose games the file lists (`dfs.detect_week`), else this week — this week or the next only (else 400 "That file's games are week 11's: DFS shows this week (week 4) and next week (week 5) only.") | `heavy` |
| `POST /api/dfs/lineups` | `{contest, players (as returned)` **or** `slate_id` (IN-4), `locks, excludes, mode: cash \| tournament, n: 1–20, stack: {with_qb: 0\|1\|2, bring_back, no_def_vs_qb} (IN-4, a closed set; else 400 bad_stack), max_exposure: 0.1–1 (IN-4; else 400 bad_exposure)}` | `{lineups: [{slots: [{slot, key, multiplier, salary, proj, upload_id, name, position, team, gsis_id, opponent}], salary, salary_left, proj, ceiling_sum, low, high, proven, mode}], notes, solve_ms, left_out, upload_csv, filename, slate_id, stack, max_exposure}` | `heavy` |

No league and no team on any route; `require_auth` like every data route (the gate keeps working either way).
`Cache-Control: no-store` on both POSTs. **Never stored or logged**: no logging call in the module, the text is dropped
after parsing (`test_the_file_is_never_logged`). One memory region, `dfs` (the week's board priced per site, kept 10
minutes, at most 8 entries): **0.35 MB** per site-week (DraftKings 628 rows, FanDuel 598). IN-4 adds two: `dfs_context`
(the week's role trends and lines, 4 entries, **0.13 MB** each) and `dfs_published` (a built published slate, 4 entries,
**1.4 MB** each). No new table, nothing new published to Neon (the context reads `analytics.fct_player_game` and
`analytics.dim_game`, already there).

**Measured (IN-4, the clone, loaded box)**: the board with its context — the context's reads cold 1.41 s (once per week
and 10 minutes), the projections answer warm 0.06–0.15 s (348 KB before gzip, 520 KB with the matchup signal); `GET
/api/dfs/slates` cold 0.69 s (reads the folder, builds two slates), warm 0.01 s; `GET /api/dfs/slate/{id}` cold 0.60 s,
warm 0.05–0.13 s (583 KB before gzip).

## Limitations (said plainly)

* **No ownership projections**: nobody's guess of how many entrants pick a player; a tournament lineup here is the
  highest high-end outcome, not a contrarian one.
* **No correlation model**: stacks are rules (IN-4), not a model of how teammates' weeks move together — a stacked
  lineup's range is still figured as if the players were independent, and the card says the real one is wider.
* **Context is not graded**: the role trend, the corner call and "Worth a look" have no backtest; the screen says so.
  The weather is not shown (§ Context).
* **The salary files are unverified against a real export** (§ The files): the parsers were built from the sites'
  documentation and memory; the first published file is the first real test (`GET /api/dfs/slates` lists it as
  unreadable, with the reason, if a header differs).
* **Kick-off times and late swap are not handled**: the FLEX is not chosen to be the latest game; a player locked by
  his game's start is not known to us; the projections are the morning build's (injury statuses from the overlay).
* **Contests**: DraftKings classic and showdown, FanDuel full roster only (no FanDuel single game, DraftKings Tiers,
  Snake, Pick'em, Yahoo DFS).
* **The scoring tables** are as remembered and documented, October 2026; the formats are unverified until a real file
  is uploaded (above).
* The value line assumes the site priced the position on one straight line; a slate with very few priced players at a
  position has no line and says so.
