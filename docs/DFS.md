# DFS: values, undervalued players and lineups from the site's own salary file (Wave I-M, IM-5)

Andrew (2026-10-05): "dfs recomendations/undervalues". The screen is **DFS** (`/dfs`, its own tab); it works with no
league and no team. Code: `src/league_lab/dfs.py` (pure: sites, scoring, parsers, matching, value, optimiser, upload
CSV), `api/league_lab_api/dfs.py` (three routes), `web/src/routes/Dfs.svelte` + `web/src/components/dfs/`. Tests:
`tests/test_im5_dfs.py` (142), `api/tests/test_im5.py` (15), `web/e2e/im5/fixtures.spec.ts` (6, phone 375 and desktop
1300, light and dark).

## What it does

1. **Before a file**: this week's players ranked by projected points **in the site's scoring** (DraftKings or
   FanDuel), by position, with the low-end to high-end outcome, the opponent and the matchup words — and "Add the salary
   file to see value" with the three steps to find the file on each site.
2. **The file**: the user adds the contest's salary file (a file, a drop or a paste). It is parsed in one request,
   matched to our players, valued, and the answer is kept **in that browser tab only** (memory and `sessionStorage`,
   one slate per site; "Remove file" drops it). The server stores nothing and logs nothing of it.
3. **Value**: for every matched player — projection, range, points per $1,000, high-end outcome per $1,000, the slate's
   salary line at his position, his gap to it (points, and rank), and the call **undervalued** / **overpriced** with one
   plain reason. Lists of the top 8 each (by position chip) and the full sortable table.
4. **Lineups**: an exact optimiser for the site's slots and cap on projected points (cash) or the high-end outcome
   (tournament), with players set to "Always in" / "Leave out", the site's team rules, 1–20 lineups each different by at
   least one player; each card with its players, the salary left, the projected total and its range; **Copy**, and
   **Download for upload** in the site's lineup-upload CSV with the file's own player ids.

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
* **Time box**: 1 second per lineup (`SOLVE_SECONDS`, HiGHS' `time_limit`). On timeout the best lineup found so far is
  returned with `proven: false` and the card says "The solver's 1-second budget ran out: the best lineup it found, not
  proven the best."; if none was found the search stops and says so. Measured on this sandbox (2 cores, five devs
  building at once; the synthetic 597-player DraftKings slate): the first lineup 0.1–0.3 s; 20 cash lineups 4–13 s in
  all (median 0.4–0.7 s each, 16–20 of 20 proven), 20 tournament lineups ~13–18 s (7–18 of 20 proven); FanDuel's
  four-per-team rule makes the 3rd–5th tournament lineups reach the 1-second box. Render's Starter has half a CPU:
  expect about twice that — the reason both POSTs are `heavy` in IM-3's limiter.
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
| `GET /api/dfs/projections?site=dk\|fd&week=&position=&limit=` | — | `{site, site_name, season, week, players: [{key, gsis_id, player_name, position, team, opponent, proj, p10, p25, p75, p90, status, out, matchup}], reference, scoring, bonus_at_odds}` (a team on a bye left out; default week: the app's week rule) | `read` |
| `POST /api/dfs/slate?week=` | the file's text (`text/csv`, or JSON `{"text": …}`) | `{site, contest, contest_label, cap, season, week, games, players: [...], unmatched, skipped, matched_by, counts, fit: {position: {slope_per_1000, intercept, n, rmse, words} \| null}, undervalued: [keys], overpriced: [keys], notes, scoring, bonus_at_odds}`; the week = the one whose games the file lists (`dfs.detect_week`), else `?week=`, else this week | `heavy` |
| `POST /api/dfs/lineups` | `{contest, players (as returned), locks, excludes, mode: cash \| tournament, n: 1–20}` | `{lineups: [{slots: [{slot, key, multiplier, salary, proj, upload_id, name, position, team, gsis_id}], salary, salary_left, proj, ceiling_sum, low, high, proven, mode}], notes, solve_ms, left_out, upload_csv, filename}` | `heavy` |

No league and no team on any route; `require_auth` like every data route (the gate keeps working either way).
`Cache-Control: no-store` on both POSTs. **Never stored or logged**: no logging call in the module, the text is dropped
after parsing (`test_the_file_is_never_logged`). One memory region, `dfs` (the week's board priced per site, kept 10
minutes, at most 8 entries): **0.35 MB** per site-week (DraftKings 628 rows, FanDuel 598). No new table, nothing published to Neon.

## Limitations (said plainly)

* **No ownership projections**: nobody's guess of how many entrants pick a player; a tournament lineup here is the
  highest high-end outcome, not a contrarian one.
* **No correlation or stacking model**: a quarterback and his receivers are scored as if independent; the lineup's
  range says the real one is wider. No "stack" rules (QB + 2 receivers, bring-backs).
* **Kick-off times and late swap are not handled**: the FLEX is not chosen to be the latest game; a player locked by
  his game's start is not known to us; the projections are the morning build's (injury statuses from the overlay).
* **Contests**: DraftKings classic and showdown, FanDuel full roster only (no FanDuel single game, DraftKings Tiers,
  Snake, Pick'em, Yahoo DFS).
* **The scoring tables** are as remembered and documented, October 2026; the formats are unverified until a real file
  is uploaded (above).
* The value line assumes the site priced the position on one straight line; a slate with very few priced players at a
  position has no line and says so.
