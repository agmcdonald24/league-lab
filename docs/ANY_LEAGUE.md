# Any league: how League Lab serves a Sleeper league it has never seen (plan E3, 2026-10-01)

## In plain words

Today League Lab works for two leagues because they are written into a setting and the nightly run prepares
everything for each of them: the projections in each league's scoring, the ranges, every team's best lineup, the
waiver moves. That does not stretch to strangers: a new customer's league would need its own nightly work, and
1,000 leagues would need 1,000 times the work and the storage.

It does not have to work that way. **Our projection of a player is a stat line** (catches, yards, touchdowns...),
and that stat line is the same in every league: we checked all 8,134 projections of the 2026 season, and the two
leagues' stat lines are identical. Only the price differs (half PPR or full PPR, 4 or 6 points a passing TD,
yardage bonuses). Pricing a stat line takes microseconds. So:

* **Stored once, for the whole NFL**: the stat lines, the ranges, the players, the schedule, the injury report,
  the matchup context. The nightly prepares these and nothing per league.
* **Done when someone opens the app**: read their league from Sleeper (settings, rosters, team names), price the
  stat lines in their scoring, find their best lineup, write the cards. **About a quarter of a second** here with the
  league already fetched (measured with fixtures; a live Sleeper read adds roughly 100–300 ms, see the table
  below), of which a quarter is the cards' "how often he outscores him" calculation.
* **Kept for a few minutes**: what Sleeper told us about the league (rosters change; scoring almost never).

**This works today.** The spike answers `My Week` for any Sleeper league id, and for the two leagues we know it
gives **exactly** the nightly's answer: the same starters in the same slots, the same values to the cent, the
same lineup total (111.46 for dynasty team 12, 117.02 for Scrubs team 2, week 4), the same bench, the same cards.
One honest footnote: the Scrubs kicker and defense (15.23 of the 117.02) are valued from Scrubs' own kicking and
defense fit, because no other fitted league has those keys — a new league whose K / DEF scoring differs from every
fitted one gets its K and DEF **unvalued** until a reference scoring with its keys exists (Risks, below).

**The one thing that is not free is the range** ("most weeks 6–14", "a bad week to a good week 3–19"). Our ranges
are fitted per league today. For a new league we take the range of the nearest league we did fit and stretch it
by how much more (or less) the new scoring pays for the same stat line. Tested on our two leagues (each one
rebuilt from the other, as if it were new): over all positions the ends of the ranges land **0.2 to 0.8 points**
from the fitted ones on average and the ranges are within 1–2% as wide; at quarterback, the position the two
scorings differ on most (6-pt pass TD), the top end is off by **1.2–1.5 points** and the width by 7%; on Andrew's
own dynasty roster the top end is off by 1.1 points. They cover what really happened as often (78.0% vs 79.2% and
78.0% vs 78.2% for the 80% range on weeks 1–3, where the actual points are known). Good enough to ship for a
scoring close to one we fit; the fix for the rest is a few more "reference scorings" (below).

**For Andrew to check before selling**: Sleeper's terms for commercial use of their API (it is free, read-only,
needs no key, asks for under 1,000 calls a minute — but the terms, not the docs, decide whether a paid product
may build on it, and whether we may say "for Sleeper leagues").

## What is stored NFL-wide (no per-league rows)

| What | Where today | Rows | Refreshed |
|---|---|---|---|
| Stat-line projections, QB–TE (12 components per player-week) | `ops.projections` — today **once per league** (identical copies) | ~550 per week; 8,134 for weeks 4–18 | nightly `project`, frozen at kickoff (B5) |
| Range parameters per *reference scoring* (P10/P25/P50/P75/P90 and the priced line in that scoring) | `ops.projections.p10…p90` per league | ~550 per week × reference scorings | nightly `project` |
| K / DEF stat lines (FG by distance, PAT, sacks, takeaways, points-allowed bucket probabilities) | **not stored**: `kdef.predict_kd` returns them, `project` drops them | ~64 per week | nightly `project` |
| Players (Sleeper directory: position, eligibility, NFL team, status) | `raw.sleeper_player` (12,229 players; ~16 MB of payload) | ~12k | once a day (Sleeper asks for at most one call a day) |
| Sleeper id ↔ NFL id | `analytics.player_id_map` | 8,063 | nightly |
| Schedule, kickoffs, byes | `analytics.dim_game` | 272 a season | nightly |
| Injury report, roster status, team this week | `mart_player_week_features` → `mart_player_week_projections` (per league today) | ~550 per week | nightly |
| Opponent context (rank vs position, trend tags) | `mart_defense_vs_position_current`, `mart_player_trend_tags` | small | nightly |

## What is computed per request

| Step | Code | Time (warm / cold, this sandbox) |
|---|---|---|
| Read the league, rosters, users from Sleeper (cache hit after the first) | `anyleague.Sleeper` | 0 / 1 ms here (fixtures); 100–300 ms live, 3 calls in parallel |
| Read the week's NFL-wide board | `anyleague.load_board` | 11–15 / 34–91 ms (one query, cached 10 min, shared by every league) |
| Price ~580 stat lines in the league's scoring (bonuses included) | `scoring.compute_points` | 12–18 ms |
| Ranges from the nearest reference scoring | `anyleague.approximate_ranges` | 11–17 ms |
| Map Sleeper ids → NFL ids, the roster's statuses, locks, byes | `player_id_map`, `lineup.LineupInputs` | 5–19 ms |
| The best lineup and every starter's margin (re-solved) | `lineup.build` → `lineup.solve` | 1.4–2.7 ms |
| The cards (three closest calls; "outscores him x% of the time": 40,000 draws each) | `app/lib/cards.py` unchanged | 61–72 ms |
| **Whole request** | `GET /api/my-week` | **141–158 ms warm, 259–331 ms cold** |

What dominates: cold, the board query (one round trip to the database, then cached for everyone); warm, the cards'
Monte Carlo (3 × 40,000 draws). On Neon add one network round trip per uncached query (4 queries a cold request).
Nothing here grows with the number of leagues except the Sleeper calls.

## What is cached, and for how long

| Data | Cache | TTL | Why |
|---|---|---|---|
| League settings (scoring, roster slots, name) | in-process (`Sleeper._cache`) | spike: 15 min; product: 24 h, and refreshed when the user taps "refresh" | changes a few times a season |
| Rosters (who owns whom, starters, IR, taxi) | in-process | 5–15 min | waivers and trades; Sunday morning matters |
| Users (team names) | in-process | 24 h | cosmetic |
| Username → user id → their leagues this season | in-process | 24 h | the league picker in the customer app (`Sleeper.user_leagues`) |
| Sleeper player directory | in-process / a nightly table | 24 h | Sleeper's request |
| The NFL-wide board and context queries | the API's query cache | 10 min | the data changes once a night |
| A rendered My Week | not cached in the spike | — | product: key on (league, roster, week, board version, roster hash) |

With several API processes the in-process caches become one shared cache (Postgres `unlogged` table or a small
Redis); nothing needs to survive a restart.

## The ranges: how a league the model never saw gets a calibrated range

**How they are made today** (`projections.fit_position`): per league and position, five quantile regressors
(`QUANTILES` 0.1 / 0.5 / 0.9 and `QUANTILES_50` 0.25 / 0.75) learn the *residual* of the league's actual points
around the out-of-fold priced line, then a split-conformal widening per projection tier (`TIER_QUANTILES`, a tier
needs `TIER_MIN_ROWS` = 200 calibration rows) makes 80% and 50% hold out of sample. Everything after the stat line
is in the league's points, so it is per league.

**Candidates considered**

| Approach | What it needs | Verdict |
|---|---|---|
| (a) Quantiles of the stat-line components, combined by pricing | component quantile models (12 × 4 positions × 5) plus their joint distribution (yards, catches and TDs move together; bonuses are thresholds), so a simulation per player | right in principle for exotic scoring; weeks of modelling; not needed for the common scorings (below) |
| (b) Scale a reference league's range by the ratio of the two prices of the same stat line | the reference league's five numbers and its price, per player-week | **chosen**: measured below |
| (b′) The same with one scale per position-week | as (b) | slightly worse than (b) everywhere |
| (c) A fixed set of "reference scorings" (half PPR, full PPR, 6-pt pass TD + bonuses, standard, TE premium) fitted nightly; a league uses the nearest | today's fitting code with a fixed list of scorings instead of the env var's leagues | **chosen together with (b)**: (c) picks the reference, (b) stretches it |
| (d) The reference's offsets unscaled | as (b) | wrong: covers 60% instead of 80% when the new scoring pays more |

**The approximation** (`anyleague.approximate_ranges`): for player *i*, quantile *q*, new scoring *N*, reference *R*:
`p_q(N) = proj(N) + (p_q(R) − proj(R)) × proj(N) / proj(R)` (ratio clipped to [0.25, 4]; a reference price ≤ 0.05
uses the offsets unscaled), then the same floors and order as `predict_position` (P10 ≥ 0, P90 ≥ the projection,
P10 ≤ P25 ≤ P50 ≤ P75 ≤ P90). The reference is the fitted scoring whose prices of the week's stat lines are closest
(median |log ratio|), never the league itself.

**Measured** (`ops.projections` 2026, each known league rebuilt from the other; the script is in the hand-back):

| Rebuilt | Pos | Mean abs gap P10 / P25 / P50 / P75 / P90 (points) | 80% width fitted → rebuilt | 50% width fitted → rebuilt |
|---|---|---|---|---|
| dynasty from Scrubs, weeks 4–18 (8,134) | all | 0.23 / 0.26 / 0.32 / 0.59 / 0.84 | 13.96 → 13.78 | 6.99 → 7.05 |
| | QB | 0.42 / 0.30 / 0.61 / 1.17 / 1.49 | 18.79 → 17.41 | 9.42 → 9.42 |
| | RB | 0.21 / 0.26 / 0.23 / 0.60 / 0.58 | 14.66 → 14.81 | 7.16 → 7.02 |
| | WR | 0.25 / 0.30 / 0.25 / 0.37 / 0.80 | 14.45 → 14.19 | 7.06 → 7.26 |
| | TE | 0.08 / 0.19 / 0.33 / 0.55 / 0.71 | 9.48 → 9.89 | 5.17 → 5.24 |
| Scrubs from dynasty, weeks 4–18 (8,134) | all | 0.19 / 0.22 / 0.26 / 0.49 / 0.69 | 11.49 → 11.63 | 5.86 → 5.81 |
| | QB | 0.33 / 0.24 / 0.49 / 0.95 / 1.20 | 14.10 → 15.19 | 7.61 → 7.59 |
| | RB | 0.19 / 0.23 / 0.21 / 0.53 / 0.52 | 13.23 → 13.10 | 6.27 → 6.40 |
| | WR | 0.20 / 0.25 / 0.20 / 0.30 / 0.66 | 11.64 → 11.87 | 5.96 → 5.79 |
| | TE | 0.07 / 0.15 / 0.27 / 0.44 / 0.57 | 7.96 → 7.63 | 4.22 → 4.16 |

Unscaled (d) for comparison: dynasty from Scrubs P90 gap 1.63, 80% width 13.96 → 11.49. One scale per position (b′):
P90 gap 0.87 / 0.72.

**Coverage** (weeks 1–3, the v2.0 boards, 715 played player-weeks each; the 50% range did not exist yet): the 80%
range held **79.2% fitted vs 78.0% rebuilt** (dynasty from Scrubs; unscaled: 59.9%) and **78.2% vs 78.0%** (Scrubs
from dynasty; unscaled 88.5%). By position, rebuilt vs fitted: QB 71.8 vs 75.6% and 83.3 vs 76.9% (78 rows each:
±5 points of noise), RB 80.9 vs 81.4% and 80.9 vs 80.9%, WR 78.0 vs 79.4% and 78.0 vs 78.0%, TE 77.9 vs 77.9% and
72.2 vs 76.0%. The standard error at 715 rows is ±1.5 points: no difference overall.

**The error grows with the distance between the scorings** (players binned by |log(price ratio)|, P90 gap as a
share of the 80% width): ≤ 0.1 → 3.5%; 0.1–0.2 → 5.5%; 0.2–0.3 → 7.0% (both directions). Our two leagues are
0.11 (RB) to 0.21 (QB, TE) apart (median). So: **fit a handful of reference scorings, not one**. How far real
leagues' scorings sit from them is not measured yet (we have two leagues); measuring it on a sample of public
Sleeper leagues is Wave F's first check. The spike's acceptance test (`api/tests/test_anyleague.py`) bounds the roster's
gaps and the whole board's (week 4: P10 / P90 0.23 / 0.83 and 0.19 / 0.68 points; 80% width ratio 0.997 / 1.003).
On Andrew's rosters, week 4: dynasty 12 (25 players) P10 0.52, P25 0.36, P50 0.34, P75 0.65, P90 1.09; Scrubs 2
(16 players) 0.65 / 0.41 / 0.44 / 0.86 / 0.98. The cards' win probabilities move by less than 0.1 (tested).

**What would change in `projections.py`** (PO-owned; proposed, not done):

1. `league_scorings(conn)` → `reference_scorings()`: a seed `dbt/seeds/reference_scorings.csv` (name, scoring JSON)
   with 4–6 scorings — League of Scrubs (half PPR, 4-pt TD), dynasty (full PPR, 6-pt TD, bonuses), full PPR 4-pt,
   standard, TE premium (+0.5 per TE catch, once `bonus_rec_te` is mapped). `fit_position` / `predict_position`
   take that dict unchanged (`PositionModel.quantiles[(scoring_name, q)]`). Fitting cost is fixed, not per league;
   five scorings ≈ 2.5× today's two (the residual models are most of `project`'s 4–7 minutes).
2. The writer splits `ops.projections` into **`ops.projection_lines`** (one row per player-week: model version,
   the 12 components, freeze columns) and **`ops.projection_ranges`** (one row per scoring × player-week:
   `proj_points` in that scoring, P10–P90). The B5 freeze applies to both (a frozen week keeps both). `p25` / `p75`
   stay as they are.
3. `kdef.project_kd`: write the league-free lines `predict_kd` already returns (**`ops.kd_lines`**) and the fixed
   offsets per reference scoring, so a K / DEF prices in any scoring (today the spike values a K / DEF only when
   the league's kicking or defense keys equal a fitted league's).
4. The two house leagues keep their batch rows until the Streamlit pages read the new tables (the research console
   is the batch's only reader).

## What changes elsewhere

* **`scripts/nightly.sh`** (done in Wave F, F1): `project` writes the NFL-wide tables — `ops.projection_lines` (the
  stat line per player-week), `ops.projection_ranges` (per reference scoring of `dbt/seeds/reference_scorings.csv`:
  `scrubs`, `dynasty`, `ppr`, `standard`, `te_premium`), `ops.kd_lines` / `ops.kd_ranges` (K / DEF lines and the
  per-scoring offsets) — under the same B5 freeze, and derives the house leagues' `ops.projections` from them (the
  research console's reader; `assert_house_projections_are_the_nfl_wide_rows`). The four tables are restored as
  state (`STATE_TABLES`); not yet in `RECORD_TABLES` (a first night whose hosted copy lacks them would stop; their
  frozen QB–TE weeks re-seed from `ops.projections`, which is). No per-league fitting remains unless a house
  league's scoring stops being a reference. `fetch-sleeper` keeps loading the house leagues (the research console)
  and fetches the player directory once. A new step could pre-warm the board query; nothing else.
* **The hosted sync**: drops, for customers, the per-league relations: `ops.lineups` / `ops.lineup_totals`
  (3.3 MB for two leagues), `ops.waiver_moves` (3.7 MB), `mart_player_week_projections` (8 MB: per league ×
  player × week), `mart_lineup_recommendation`, `mart_league_roster_*`, `mart_player_availability`,
  `fct_player_game_league` (52 MB: every historical game priced in each league), `mart_league_player_season`
  (8 MB). The hosted copy then grows with the NFL, not with customers.
* **The API** (plan F3, done 2026-10-02): `/api/my-week` falls through to Sleeper for an unknown league and names
  the week's opponent (`/league/{id}/matchups/{week}`, his lineup solved the same way); `/api/leagues?username=`
  (`anyleague.user_leagues`); the player card and `/api/ros` in the user's scoring (rest of season priced week by
  week: the same players, totals and ranks as `mart_player_ros_projection` for a house league); `/api/record`
  (house leagues). The board reads F1's NFL-wide tables when they hold the week (`anyleague.NFL_WIDE`), else
  borrows; Sleeper's calls go through one cached, rate-limited client (`sleeper_client.py`, `docs/SLEEPER_TERMS.md`).
  **Wave G (G2, done 2026-10-02): the decisions on demand** — `/api/waivers`, `POST /api/trades/evaluate`,
  `/api/trades/partners`, `/api/team`, `/api/league` (`api/league_lab_api/decisions.py`). Every roster of the league is
  solved for the horizon on ONE `LineupInputs` (`anyleague.league_weeks`: the nightly's cost per league, rosters × 4
  lineups, ~0.1–0.2 s of solving after the board is priced), the free agents are Sleeper's directory minus every roster
  (`anyleague.free_agents`: `player_id_map`, the nightly's filter) valued by `lineup._proposed_player`, the waiver sweep
  is the nightly's own per-roster step (`waivers.sweep_roster`), trades run `trades.evaluate` / `partners` on a
  `RosterBoard` of the solved rows (`anyleague.horizon_frame`: `mart_league_roster_horizon`'s columns and rules), and the
  league's standings / all-play / transactions come from Sleeper's played weeks (`Sleeper.season_matchups`, 1 h) and
  `/transactions/{round}` (`Sleeper.transactions`, 1 h). A house league on this path reproduces every row of
  `mart_waiver_moves`, the Trade Finder's numbers, the roster marts and the standings (api/tests/test_decisions.py).
  Calls per league: league + rosters + users (+ the daily directory) for waivers / trades / team; + one per played
  week and one per round for the league page (cached an hour). Next: search on demand, the draft / keeper facts for
  an unknown league (they need its history).

## Sleeper's API

Read-only, no key, documented limit: stay under **1,000 calls a minute** or the IP may be blocked. Calls we need:

| Call | When | Size |
|---|---|---|
| `GET /v1/user/{username}` → user id | sign-in / league picker | < 1 KB |
| `GET /v1/user/{user_id}/leagues/nfl/{season}` | league picker | a few KB |
| `GET /v1/league/{league_id}` | first open, then daily | 3 KB |
| `GET /v1/league/{league_id}/rosters` | every 5–15 min while someone looks | 10–20 KB |
| `GET /v1/league/{league_id}/users` | daily | 2–5 KB |
| `GET /v1/league/{league_id}/matchups/{week}` | the opponent; Sleeper's weekly lineup | 10–30 KB |
| `GET /v1/league/{league_id}/transactions/{round}` | the league page's transactions (Wave G), hourly | 5–60 KB |
| `GET /v1/players/nfl` | once a day, for everyone | ~15 MB (12k players) |
| `GET /v1/state/nfl` | hourly | < 1 KB |

Budget at the limit: with rosters cached 15 minutes, about one call per active league per 15 minutes →
**~15,000 leagues active in the same quarter hour** before the limit binds. Sunday at noon is the peak; a 5-minute
roster TTL that morning halves it. One process holds the budget (a shared token bucket when there are several).

## Storage and cost at 100 / 1,000 / 10,000 leagues

Today (two leagues) the per-league tables above are ~45 MB per league (89 MB for two; half of it the priced
history `fct_player_game_league`) and `project` fits five residual models × 4 positions per league.

| | 100 leagues | 1,000 leagues | 10,000 leagues |
|---|---|---|---|
| Per-league rows, today's design | ~4.5 GB, 100 × the fitting | ~45 GB | ~450 GB (Neon free holds 512 MB) |
| NFL-wide store, this design | ~15 MB (lines + 5 reference scorings + K/DEF + context) | same | same |
| Accounts and their leagues | < 1 MB | ~1 MB | ~10 MB |
| Requests (20 a league a week) | 2,000 / week | 20,000 / week | 200,000 / week ≈ 30,000 a day ≈ 2.5 CPU-hours a day at 0.3 s |
| Sleeper calls (15-min roster cache) | trivial | ≤ 1,000 an hour typical | peaks need the 5-min TTL rule and the token bucket |
| Hosting | free tier | one $7 service | one or two $7–25 services; a paid Neon plan for connections |

Nothing per league is stored, so the database stays inside the free tier's 512 MB at any size; the cost that grows
is CPU per request (the cards' Monte Carlo is the largest part: 10,000 draws instead of 40,000 would cut it by
three-quarters; the probabilities were calibrated at 40,000).

## Risks

1. **Sleeper's terms for commercial use** — Andrew checks (developer docs + terms of service); also whether the name
   "Sleeper" may appear in our marketing. Mitigation if it is a no: the same design works on ESPN / Yahoo / MFL
   reads, which have their own terms.
2. **A scoring key we do not map** (`scoring.unmapped_keys`): first downs (`*_fd`), TE / RB / WR catch premiums
   (`bonus_rec_te` …), IDP. The spike reports them (`on_demand.unmapped_scoring_keys`) and prices them 0; the card
   must say so. Keys mapped but not in the projected line (long-TD bonuses, 2-point conversions, return TDs —
   `not_projected_keys`) are 0 in the projection for every league today too. A TE premium needs the position-
   conditional keys mapped and a reference scoring with it.
3. **IDP leagues** (`IDP_FLEX`, `DL`, `LB`, `DB`): the slots are ignored and reported, as the nightly does.
4. **Players Sleeper has and `player_id_map` does not** (rookies before nflverse lists them): unvalued, seated
   only where nobody valued can play, listed in `on_demand.unmapped_players` (none on the two rosters).
5. **K / DEF in a new scoring**: unvalued until `ops.kd_lines` exists (above); a league that weights only skill
   positions is unaffected.
6. **Ranges far from every reference scoring** (a 1-point-per-carry league): the error grows with the distance
   (above); the response says which reference was used, and the coverage can be measured on played weeks per
   reference with the existing drift job.
7. **Sleeper downtime**: the last good league payload can be kept (stale-while-revalidate); the spike answers 502
   with a sentence.
8. **Load**: the board query and the cards' Monte Carlo are the CPU; both cache per (week, board version).

## Order of work for Wave F (the customer app), given the spike

1. **`projections.py` / `kdef.py` NFL-wide outputs** (PO): `ops.projection_lines`, `ops.projection_ranges` per
   reference scoring, `ops.kd_lines`; the house leagues keep their rows. Without this the API reads one league's
   copy (works, but it ties customers to the house leagues' scorings for ranges and K / DEF).
2. **League picker by Sleeper username** (`/api/leagues?username=`) and the on-demand My Week as the web app's
   first screen; the opponent from the matchups call.
3. **Player card in the user's league** (price + range on request; the sentences move into `app/lib` first, per
   the port rule in `docs/FRONTEND_DECISION.md`).
4. **Waiver wire on request** (free agents = directory − rosters).
5. **Accounts, payments, the shared cache, rate limiting** (Wave G), then Trade Finder.

## Availability

*(Wave I-0, I0-A — `api/league_lab_api/availability.py`, `src/league_lab/injury_feed.py`.)* The nightly build takes
who can play from the NFL injury report via nflverse, once a day; nflverse lags the report by hours (Justin Jefferson
was ruled Out at 2:35 PM ET Friday 2026-10-02; the 5:29 PM build still had nothing). The API now overlays two fresher
sources at request time, on the house leagues and on any league alike:

- **ESPN's public injuries feed** (`site.api.espn.com/apis/site/v2/sports/football/nfl/injuries`, no key): read every
  15 minutes on a game day (a game that day in `analytics.dim_game`), hourly otherwise; the parsed entries (not the
  8.7 MB body) cached in `LEAGUE_LAB_CACHE_DIR/espn_injuries.json` with `fetched_at`; a failed read keeps the last copy;
  a token bucket of 2 reads a minute per process. The athlete id is in the entry's links (`/id/4262921/`), not a field.
- **Sleeper's player directory** (already cached a day; its terms ask for one call a day — unchanged): `injury_status`
  and `status`, dated by `news_updated`.

ESPN athletes map to gsis through the directory's `espn_id` first, then the id table (`db_playerids.csv`:
`LEAGUE_LAB_PLAYER_IDS_CSV`, else `LEAGUE_LAB_CACHE_DIR/db_playerids.csv`; I0-B's `player_ids.py` replaces the reader).
Measured 2026-10-03 on the live feed: Sleeper's `espn_id` maps only 118 of ESPN's 400 skill-position entries (Sleeper
has an `espn_id` on 223 of 866 skill players on a team) — the id table is not optional; it maps all 158 of the fixture's.

**The rule**: per player the newer source wins (ESPN's `date`, Sleeper's `news_updated`; a Sleeper entry without
`news_updated` never beats ESPN). Cannot play = Out, Doubtful, IR, PUP, NFI, Suspended, Inactive; Questionable plays
and is flagged; Sleeper's `NA` is ignored (its meaning is unclear). In the lineup, a status from a copy read before the
nightly build ran is ignored (the build saw that news or newer).

**Where**: My Week (the lineup re-solved with `lineup.solve` from the rows' own values and slots when a starter or bench
player can no longer play, or a player the build sat as Out can play again; the row gets chip OUT / DOUBTFUL / IR and
a reason; `availability.changes` says who moved in a sentence; the cards follow the new rows), Trends (no Out / IR / PUP
/ suspended player; `availability.left_out` says how many), Waivers (no claim or free agent who cannot play this week;
a drop who cannot play this week costs 0 this week; never two QBs of one NFL team — Sleeper's `depth_chart_order`
decides, else the better-ranked claim), trades (this week's board: an Out player is worth 0, `cannot_play` carries the
status), rest of season (`injury_status`), `/api/status` (`availability`: stamp, source ages, how many cannot play; the
stale-injury warning goes when ESPN was read within the hour). Web: "Injuries checked 2:40 PM" on My Week, the
sentences under "Your lineup", the chip on the player row.

**Switches**: `LEAGUE_LAB_AVAILABILITY=off` turns it off; in fixture mode (`LEAGUE_LAB_SLEEPER_FIXTURES`) it is off
unless `LEAGUE_LAB_ESPN_FIXTURES` points at a feed file — no test and no sandbox run calls ESPN.

**One context (Wave I-B, IB-0, 2026-10-03).** The second review caught My Week saying "start Croskey-Merritt
(Jefferson is out)" while Waivers said "drop him: he would not start", with two lineup totals: the overlay re-solved My
Week only. Now `availability.roster_context(league, roster, week)` is the one read of a roster's week — the nightly's
rows (`cards.lineup_rows`; any other league `anyleague.lineup_rows`) with the overlay applied by `apply_to_rows` (the
lineup re-solved by `lineup.solve` when a status changed since the build) — kept in process for the overlay's interval
(at most the query cache's 10 minutes; 2 on demand), keyed by league, roster, week, the overlay's stamp and the build.
It carries every rostered player's `status` (OUT / DOUBTFUL / IR / Q / ok), `can_play`, `starter`, `slot`, `value`,
`locked`, and `lineup_value`, `changes`, `checked_at`, `as_of_build`. Readers: My Week (both paths) and the
opponent's projected total (his own context); Waivers (the total, the weakest starter, and every move's this-week part
re-solved on the context — `availability.moves_on_context`: the week gain, the seat, the displaced starter, the drop's
cost; the later weeks keep the build's; moves that no longer gain go, the ranks are re-run — and a drop who starts this
week is never "would not start": `starts_this_week` / `slot_this_week` on the drop); the Team Hub (lineup / bench /
horizon values, the weakest starter, the slot strengths, the roster, this week's league comparison and ranks — every
roster the overlay moved is re-read, `availability.touched`); the player card (its lineup sentence reads the context;
the Availability section says "Justin Jefferson is out (ankle): he starts at FLEX2 this week" or "Not in this week's
lineup: …", and the injury line shows the overlay's status when it is newer than the build); the trade board (this
week's rows of every roster the overlay moved are the context's, so the calculator's "before" is My Week's total).
Pinned by `api/tests/test_ib0.py`: My Week = Waivers = Team = the calculator's "before" for both house leagues, the
Test League, the on-demand path and MFL, with the fixture feed on and off. Not covered: a free agent who only becomes
worth a claim because of the overlay (the build's move list is re-priced, not re-searched — the next nightly finds him).

## News

*(Wave I-D, N1, 2026-10-03 — `src/league_lab/news_feed.py`, `api/league_lab_api/news.py`; terms and the feed's shape
in `docs/ESPN_TERMS.md`.)* Andrew asked in his first review for the player news next to the numbers. The card now
carries ESPN's latest headlines for the player, on the house leagues and on any league alike (Sleeper, MFL; a team
unit's card is its starter's):

- **The feed**: ESPN's public fantasy player news (`site.api.espn.com/apis/fantasy/v2/games/ffl/news/players?playerId=
  <espn_id>&limit=5`, no key): RotoWire's per-player blurbs and ESPN's own stories, newest first. Read **on demand,
  one athlete per card opened**, never in bulk (Trends' and Waivers' rows do not read it); cached per athlete an hour
  (15 minutes on a game day) in `LEAGUE_LAB_CACHE_DIR/espn_news/<espn_id>.json`, holding only the headline, date,
  source and link; a token bucket of 60 reads a minute per process; a failed read serves the last copy, or no line.
- **His ESPN id**: the id table (`db_playerids.csv`, read backwards: the same table the availability overlay maps ESPN
  athletes with), else Sleeper's directory `espn_id`. No id: no line.
- **On the card**: `news: [{headline, date, source, url}]` on `/api/player/{gsis}` — at most 3, newest first, none
  older than 14 days (so no line when the newest is older); `[]` when the feed is off or out (never an error). The
  page and the pane show one line under the availability lines: "**News** · 2 h ago · *headline* · RotoWire via ESPN ›"
  (`web/src/components/NewsLine.svelte`; the newest only, cut at a word to 110 characters, linked out in a new tab).
- **Switches**: `LEAGUE_LAB_NEWS=off` (default on); off in fixture mode unless `LEAGUE_LAB_ESPN_FIXTURES` is set
  (`news_<espn_id>.json`, age measured from the recorded answer's `timestamp`). `/api/status` → `news` (calls,
  failures, cached athletes).

**PlayerWire first (N2, 2026-10-03 — `docs/PLAYERWIRE.md`).** The line now leads with Andrew's own PlayerWire briefs:
hand-reviewed, sourced news replicated every 15 minutes from PlayerWire's loopback API on the Mac into the hosted
database's own schema `playerwire` (role `playerwire_writer`, never the nightly; HOSTING.md § 5 extended to "one writer
per schema", awaiting Andrew's yes). `news.for_card(gsis)`:

- **PlayerWire's items first**: his own briefs and the briefs naming him as a related player (`related: true`), mapped
  through `analytics.player_id_map` by Sleeper id, else gsis id (a disagreement shows to nobody), live and published,
  newest first, none older than 14 days, at most 3 — each `{headline, date (published_at), source ("<first evidence
  publisher> via PlayerWire"), url (its https link), summary (the brief's news), kind: "playerwire", verification
  (official / reported / corroborated / disputed), related}`.
- **ESPN fills the slots left** exactly as above, with `kind: "espn"` added; ESPN is not asked when PlayerWire fills all
  three. The shape is backward compatible (N1's four keys on every item; the rest are new keys).
- **The card**: when the first item has a `summary`, the brief's news goes under the headline (muted, full width, cut
  at a word to 220 characters) and a small verification tag after the source; an ESPN item renders as before.
- **Switches**: `LEAGUE_LAB_PLAYERWIRE=off` (ESPN only); `LEAGUE_LAB_NEWS=off` still turns the whole line off. No schema
  or the marts mid-restore → ESPN only, one log warning, a minute's pause. Fixture mode: off unless
  `LEAGUE_LAB_PLAYERWIRE_FIXTURES` names a rows file (`api/tests/fixtures/playerwire/briefs.json`). `/api/status` →
  `news.playerwire` (`rows`, `withdrawn`, `newest_published_at`, `unmapped`, `conflicting`, `last_sync_at`,
  `last_error`).

## MyFantasyLeague (Wave I-0, I0-B, 2026-10-03)

**Design.** The rest of the code only sees Sleeper shapes. A league key with a platform prefix (`mfl:21861`; Sleeper
ids stay bare) goes through `anyleague.sleeper()`, now a `platforms.Router`: Sleeper keys reach the Sleeper client
untouched, `mfl:` keys reach `platforms.MFLLeagues`, which reads MFL (`mfl_client.MFL`: caches by kind, 60 calls a
minute, redirects to the league's `www4N.` host followed and remembered, fixture mode `LEAGUE_LAB_MFL_FIXTURES`) and
answers `league` / `users` / `rosters` / `matchups` / `season_matchups` / `transactions` / `players` in Sleeper's
shapes. `anyleague.check_id` accepts both keys; `myweek.known_league` is false for `mfl:` (always on demand). Every
on-demand route then serves the league unchanged: My Week, the player card, rest of season, waivers, trades, Team
Hub, League, search, About, the research screens. `/api/record` answers as for any league we do not keep (200,
`available: false`, the existing sentence).

**Translation.**
* *Lineup*: MFL's starter limits ("1", "2-4") → each position at its minimum, the rest of the starters as `FLEX`
  (RB/WR/TE), `SUPER_FLEX` when QB has a range; `PK` → `K`, `Def` → `DEF`; bench = roster size − starters. IDP
  positions are left out and said so.
* *Scoring*: per-unit rules map to Sleeper keys (`#P` pass_td, `PY` pass_yd, `IN`, `P2`, `#R`, `RY`, `R2`, `#C`, `CY`,
  `C2`, `CC` rec — a position's different `CC` rate is a premium on top: `bonus_rec_te`; `EP` xpm, `#FR` fum_rec_td,
  defense `FC` ff, `IC` int, `SK` sack, `SF` safe, `#T` def / special-teams TD). Approximated and said so: `FG` by the
  yard (each Sleeper distance band at its middle: 17, 24.5, 34.5, 44.5, 55 yards), points-allowed bands (the average
  of MFL's points over each Sleeper band: MFL 7-10 = 5, 11+ = 0 → Sleeper 7-13 = 2.857), yardage bands with
  `thresholdPoints` (→ `bonus_*_yd_*`), touchdowns scored by length (`PS` / `RS` / `RC` → the TD plus a `_40p` bonus).
  Anything else (return yards, IDP tackles, …) is listed by name in the scoring note as "not counted".
* *Teams*: franchise → user (`user_id` = franchise id, the franchise name as both display and team name; MFL shares
  no manager names) and roster (`roster_id` 1..N in franchise order; starters from the week's live scoring, else last
  week's results; IR and taxi from the roster statuses; wins / losses / points from the standings).
* *Players*: MFL id → Sleeper id through the id table (`player_ids.py`), else → gsis → `analytics.player_id_map`,
  else a defense by its team code (MFL `KCC` → `KC`…), else a unique name + position match in Sleeper's directory
  (counted as `name` in `mfl_mapped_by`), else the player stays on the roster as `mfl:<id>` with his MFL name
  (unvalued, listed in `unmapped`). League 21861 on 2026-10-03: 216 of 216 rostered players mapped (202 by the
  table, 14 defenses by team code).

**Routes.** `GET /api/leagues?mfl=<league link or id>` → `{platform: "mfl", league: {league_id: "mfl:21861", name,
season, total_rosters, scoring_label, url}, teams: [{roster_id, team_name, manager_name: null}], roster_id (the
team an `F=0004` in the link names), unmapped: [{mfl_id, name, position}], players, mapped, scoring_note}`. My Week
adds `platform: "mfl"` and `on_demand.mfl_unmapped`, `mfl_mapped_by`, `mfl_scoring_note`. A league MFL will not
share → 404 with the sentence in `docs/MFL_TERMS.md`; MFL down → 502 "MyFantasyLeague did not answer".

**Web.** The Leagues screen: under the Sleeper username box, "On MyFantasyLeague? Paste your league link" → the
league card (name, size, scoring, the note) with its teams → My Week. The pick is remembered on the phone
(`ll.mflLeagues`) and the league switcher shows "· MFL" after the name.

**Find a league by its name (I0-C, 2026-10-03).** MFL's phone app shows a league's name, not its link, so the one MFL
box takes a link, an id **or the name**. `GET /api/leagues?mfl_search=<text>`: a link, an id or an `mfl:` key answers
exactly as `?mfl=` does (the league card); a name goes to MFL's public search (`mfl_client.MFL.league_search`:
`TYPE=leagueSearch&SEARCH=<text>` on the `api.` host, no login, cached 10 minutes, the same 60-a-minute bucket) and
answers `{platform: "mfl", query, season, matches: [{league_id: "mfl:<id>", name, year, home_url}], total, note}` —
this season only, at most 25, best first (the exact name, then names that start with the text, then a word that does,
then the rest), fewer than 3 characters → no call and a note asking for more. MFL writes every `homeURL` as
`https//www45…` (no colon): it is never passed on — `home_url` is rebuilt from the id on the `www4N` host the
`homeURL` names (remembered for the league's next calls), else `www`. Web: the box's copy is "Paste your league link,
or type your league's name as it appears in the MFL app."; a name lists the matches (name + "MFL · 2026"); tapping one
loads the league card and the team picker ("‹ Not this league" goes back to the list); the pick is remembered as before.
A private league is listed by the search like any other; opening it gives the existing "Ask the commissioner…" 404.

**Not done.** MFL transactions (the League screen shows none), playoff brackets (the rest-of-season window assumes
2^(weeks after the regular season) playoff teams), keeper / dynasty detection (every MFL league reads as redraft in
the scoring label), MFL's own injury report (the availability overlay reads ESPN and Sleeper by player).

## Scoring (Wave I-C, IC-1, 2026-10-03)

**Why.** Dad's MFL league 70587 scores by position group, touchdowns by distance (6 / 9 / 12), yards "1/10" (QB
passing "1/20"), +10 at the league's own thresholds (75 / 100 / 250 by position), no points per catch, FG by distance
3 / 5 / 10 / 15, and team QB / kicker units. The I0-B translation into Sleeper keys came back with nothing for the
offense; every projection priced the touchdowns and the yards at 0.

**What.** `scoring.ScoringSpec` (docs/METRICS.md § "Scoring spec"): the rules per position, compiled from Sleeper's
settings (`from_sleeper`) or MFL's rules (`from_mfl`), every unknown event listed as unpriced with its code and name.
`anyleague.league_scoring(league)` carries it (`LeagueScoring.spec`; `league_spec(league)` reads
`league["scoring_spec"]`, else the MFL report's `spec`, else compiles the Sleeper settings). Pricing reads the spec:
`price_lines` (a Sleeper spec through the flat path, so the house leagues reproduce the nightly to the bit; any other
in expectation, per row position, units through `rules_for`), `kd_values` (`kd_flat`), `scoring_report` (+ `priced`
= the read-back, `approximated` in words, `unpriced`), `why.weights` (the pieces from the position's rules).

**The check.** `GET /api/league/scoring-check?league=<id or mfl:id>&week=<n>` (default: the last complete week of our
NFL stats) → `{league, week, n, within_0_1, within_1, misses: [{player, position, theirs, ours, gap, likely_rule,
pieces}], suspect_rules, sql, unmatched, theirs_from, spec_unpriced, spec_approximated, words}`. A week our stats do
not hold yet answers `n: 0` with the sentence. Cached a day in process.

**The 10-yard split (PO, at integration).** `fct_player_game` (and `fct_player_game_league`, `league_player_week`,
from `int_player_game_pbp`) now carry `pass/rush/rec_tds_10p` next to `_40p` / `_50p`, so MFL's 0–9 / 10–39 / 40+
bands are exact on actual lines and the check reads no play-by-play (IC-1's `analytics.fct_play` lengths query is
gone: 233 MB whole, it would have broken the hosted copy's 480 MB budget). A copy built before this change has no
`*_tds_10p` column, and the check approximates the < 40-yard split with M2's shares and says so (70587: 128 / 163
and 122 / 156 within 1 point instead of 162 / 163 and 156 / 156; the house leagues are unaffected — their long-TD
bonuses start at 40). Return yards, IDP, and the defense's distance on a return TD (priced at its expected points)
are not priced from actual lines.

**One entry point for a projected line (Wave I-D, M3, 2026-10-03).** `scoring.price_projected(stats, scoring,
position=None, *, ev=None)` is the only function that prices a projected stat line, on both sides: the nightly
(`projections.price(..., "proj_")` → `predict_position`, `house_rows`, the ranges' anchor, the harness, signals'
what-ifs) and the request side (`price_lines` → My Week, Waivers, Trades, rest of season, the team units; the
on-demand larger-role what-if in `decisions`). An actual line (`out_`, the scoring check) stays on the exact engine
(`compute_points` / `price_detail`): its bonus happened or it did not. The engine:

| Scoring | `LEAGUE_LAB_EV_PRICING` off (default) | on |
|---|---|---|
| Sleeper, no yardage / long-TD bonus (Scrubs, the Test League, the plain references) | flat engine | flat engine (unchanged to the bit) |
| Sleeper with a yardage or long-TD bonus (the dynasty) | flat engine: bonus all or nothing on the mean, long TDs 0 | `expected_frame(ev=True)`: bonus × P(in band), long-TD bonus × projected TDs × share that long |
| MFL spec | expectation | expectation |

Under the flag only the bonus keys change price; which keys count does not (`scoring.projected_view`: a key the flat
engine leaves off a projected line — `pass_att`, `rush_att`, `rec_tgt`, `pass_inc`, the count bonuses — stays off).
The flag is read at call time in each process, so the nightly (GitHub Actions) and the API (Render) must carry the
same value; a house league then reproduces its nightly `proj_points` to the bit under either value
(`tests/test_projections_ev.py`). K / DEF (`kdef.price`) stay flat.

## Slots and team units (Wave I-C, IC-2, 2026-10-03)

**Why.** Dad's league (MFL 70587, "Make Football Great Again") starts `TMQB ×1, RB ×2, WR+TE ×3, TMPK ×1, Def ×1`.
`lineup.py` knew Sleeper's slot names only, so the translation kept `RB` and `Def` and dropped the rest: the app read
the lineup as "2 RB, DEF", seated a TE at RB2 (MFL's starters, in no slot order, were zipped onto the slots), called
every WR and both team units "Can't play", and priced team 1 at 13.34 (week 4, fixture). Now: 8 slots, both units
seated and priced, 38.65 (with the scoring I0-B compiled; IC-1's spec changes the numbers, not the seating).

**Slots are eligibility sets** (`lineup.Slot(label, type, elig, order)`, `lineup.slot_eligibility(name)`):
* Sleeper's names as before (`QB … DEF`, `FLEX`, `SUPER_FLEX`, `REC_FLEX`, `WRRB_FLEX`; `IDP_FLEX` / `DL` / `LB` / `DB`
  reported, not solved);
* generic combined names `A+B[+C]` = the union of the parts (`WR+TE` {WR, TE}, `RB+WR+TE`, `QB+RB+WR+TE`; `PK` = K,
  `Def` = DEF). Sleeper never emits them; the MFL translation writes the league's own names (`mfl_client.slot_name`).
  A combined name with an IDP or unknown part (`DT+DE`) is reported, not solved;
* the team units `TMQB` (admits only a TMQB), `TMPK` (only a TMPK), `TMDEF` (= a team defense, DEF).

The label is the league's own word ("WR+TE1", "TMQB"); `cards.slot_label` says it ("WR/TE 1", "team QB", "team K").
`lineup.SLOT_ELIGIBILITY` answers any of these names on lookup (`SLOT_ELIGIBILITY["WR+TE"]`, `.get("TMQB")`), so every
reader of slot types (waivers, the trade board, availability, the Team Hub's slot strength) works unchanged on an MFL
league; `app/lib/cards.slot_elig` is the solver-free copy (a test keeps them equal).

**"No slot" is not "can't play".** A player no starting slot of the league admits (a plain K in dad's league, a QB, a
team unit in a Sleeper league) reads **"No slot for a K in this league"**, listed as "No slot" (My Week's full list,
the Streamlit table); "Can't play" is kept for injury, bye, IR, a locked bench player. The rows keep `role =
"unplayable"` (every reader leaves him out of the lineup), `Lineup.no_slot` / `Lineup.cannot_play` split them, and
`ops.lineup_totals.n_unplayable` counts only the can't-play ones. The reason was "no K slot in this lineup" before.

**MFL's starters, seated.** Sleeper's `starters` array is ordered like the starting slots ("0" = empty); MFL lists
ids. `MFLLeagues.rosters` seats each starter in the narrowest slot that admits him (`lineup.align_starters`: a maximum
matching), so the lock rule reads the slot a started player really holds (Fannin, Thursday night: WR+TE3, not RB2).

**Team units are players.** A rostered MFL `TMQB` / `TMPK` id (`0651`… / `0701`…; MFL numbers them as its defenses
`05xx` + 150 / + 200) becomes a directory row `{player_key: "mfl:0656", position: "TMQB", team: "CIN", player_name:
"Cincinnati Bengals QB", unit: true}` (team = MFL's code in Sleeper's spelling, name = MFL's name + the unit word), with
no gsis id and counted as `unit` in `mfl_mapped_by` (never "unmapped"). A `TMDEF` is a defense, as `Def` was.

**Pricing** (`anyleague.price_units`, carried in `Priced.units`, one row per (unit, nflverse team)):
* `TMQB` = the line of the team's best-projected quarterback who can play (Out / Doubtful / NFL IR skipped unless
  none is left), priced through `price_lines` like every stat line with `position = "TMQB"` (`lineup.UNIT_PRICES_AS`
  maps it to the QB rules for IC-1's spec); its range is the starter's, shifted onto the unit's points. The brief's
  "sum of the team's quarterbacks' lines" is `unit_lines(rule="sum")`: on the week-4 board the backups' lines are not
  near 0 (KC 29.24 summed vs Mahomes 22.78 alone, ATL 30.35 vs Penix 17.22, BUF 29.28 vs Allen 26.99 in a 4-pt pass
  TD scoring) — each line is projected on its own, so the sum counts a team's passing more than once. Default
  `UNIT_QB_RULE = "starter"`.
* `TMPK` = the team's kicker from `kd_values(scoring, "K")` (the best projected when a team has two); his p10 / p90.
* `TMDEF` = DEF as today.
* A unit can't play only on a bye (the solver's bye rule by its team); a game kicked off locks it as any starter.

**Free agents.** A league with unit slots lists every NFL team's units in the directory: the rostered ones under their
MFL id, the others as `mfl:TMQB-KC` (the MFL id is known only once a roster carries the unit), one per (unit, team).
`free_agents` keeps them (no gsis needed) and Waivers prices them by team (`unit_value`). 70587: 64 − 34 rostered = 30.

**The web.** The slot words come from the API; a unit's row shows its team's badge (`TeamBadge`) where a player shows
his face (`LineupTable.svelte`).

**Not done.** Rest of season and the trade board value a unit through the solver's rows only (the ROS table has no
unit rows yet); the Team Hub's slot-strength "top" carries the unit's name, not its team; `scoring_report` reads
`"DEF" in slots` (a `TMDEF`-only league would list the defense keys as unmapped — IC-1's function).

### Finished (Wave I-D, IC-4, 2026-10-03)

**Rest of season has the units.** A league whose slots admit `TMQB` / `TMPK` gets one rest-of-season row per (unit,
NFL team): 32 team QBs and 32 team kickers in dad's league. Each week of the window is priced by the week's own rule
(`anyleague.unit_window` on the NFL-wide window, `units_priced_frame` on a week priced by `price_week`): the line of the
team's best-projected quarterback who can play *that week* (`unit_lines(rule="starter")`, priced through `price_lines`
as TMQB, so `UNIT_PRICES_AS` gives it the QB rules), or the team's best-projected kicker that week; the range is the
starter's. A team's bye is a week off (the table's rule). Week 4 of the Bengals QB = My Week's 29.00, for every team and
week (`test_ros_units_equal_the_weeks_unit_prices`). The rows are keyed by the league's directory — `mfl:0656` for a unit
a roster carries, `mfl:TMQB-KC` for one on the waiver wire (`anyleague.unit_directory`) — so whose it is, the trade
board's weeks past the horizon and "Value to my lineup" find them under the rosters' keys. In "Value to my lineup" a
unit is counted against the units of its position on the waiver wire (the 30 unrostered), as a kicker is against the
free kickers. The answer's row: `unit: true`, `priced_from` (the decision week's starter), `priced_from_words`
("Priced from Joe Burrow's line (the team's starting QB each week)"); `?position=TMQB` / `TMPK`; the table shows the
team's badge where a face goes, the chips say "Team QB" / "Team K".

**A unit's card** (`/api/player/mfl:0656?league=mfl:70587`) is its starter's card — the quarterback (kicker) whose line
prices it this week — named as the unit ("Cincinnati Bengals QB"; `unit.header` "Cincinnati Bengals QB — priced from
Joe Burrow's line"), with the unit's roster ("on **Knight Train**") and the unit's rest of season.

**The Team Hub names a unit with its team**: the slot strength's best starter carries `unit`, the team (the badge) and
`short_name` ("Bengals QB"); the roster rows carry the unit's team; the slot reads "team QB" / "team K".

**Manager names**: MFL's `league` export lists a franchise's `owner_name` only to a caller the league shows it to; the
public export League Lab reads has none for 70587, 21861 or 10015 (checked live through the browser pane, 2026-10-03).
`team_names` returns it as the manager name when it is there (`mfl_client.franchise_owners`) and **null** otherwise —
never the team name repeated (the League screen's standings showed "Knight Train / Knight Train"). The picker and My
Week's header ("**Knight Train** · <owner> · 1-3, #11") show it when it exists.

**Double headers everywhere.** A double-header week is one score and two games for a team: the League screen's
all-play counts each other team once a week (it counted a double-header week's teams twice: Klaby Crew 57-9 all-play
over 3 weeks of 11 opponents, now 27-6), each team-week carries `games` (both opponents, "L/L"), the record comes from
every game; `/api/league` lists this week's matchups and the last scored week's results (`matchups`, each game once:
week 4 of 70587 = 12 games, Knight Train's two first). `/api/record` for an MFL league still keeps no projection record
(`available: false`) and now answers the league's own results: every played week's games (MFL's schedule; its
`weeklyResults` carry the same scores), two a team in a double-header week, and each team's record — equal to MFL's own
standings for all 12 teams. The Matchups screen names NFL opponents only (no fantasy opponent): nothing to change.

**Waivers with an empty starting slot**: the claim that fills it this week leads Help now and the three strongest
(70587 week 4, the ESPN fixture overlay: Hall and Price Out → "Claim Jacory Croskey-Merritt (RB) … Fills your empty RB2
this week."); a unit slot reads "team K" in the claim's reason ("Starts at team K this week over Chargers K (10.0).").

## Usage (Wave I-F, U-1, 2026-10-03)

Which screens get used, for any league the app serves — a house league, any Sleeper league, an MFL league alike: one
row per screen view in `usage.events` on the hosted copy (`docs/HOSTING.md` § "Usage": the row, the write path, the
rollout). The league is its key (`1389709692405551104`, `mfl:70587`) and the team its number in that league; the
platform comes from the key. No name, username or IP address is kept, so a league the database has never seen adds
nothing about its managers — only that its key was opened, on which screens, and how many browser-days.

Per-league questions it answers on the console's Usage page or `GET /api/usage/summary`: how many leagues were opened
each day (`leagues`) and which screens a day's views went to; the console also says how many of the window's leagues
were MyFantasyLeague ones. Storage: 168 bytes a view with its index (measured) — at 10,000 leagues × 20 views a week
≈ 34 MB a week, which is when the table needs a retention rule (a monthly roll-up into counts per screen per day,
then delete the rows; not built — at the beta's size it is kilobytes).

## Events (Wave I-G, IG-2, 2026-10-04)

The event store (`events.events` on the hosted copy; `docs/HOSTING.md` § "Events": the row, the write path, the
rollout) is **per player and per team, never per league**: an injury-report move, an ESPN item or a PlayerWire brief
is the same fact for every league that rosters the player, so a league the database has never seen (any Sleeper key,
an MFL league) reads the same events as the house leagues and adds no rows of its own — the overlay writes its moves
once per copy whatever was opened, and a news item or brief one row however many leagues' screens showed it.

- **Keys**: `gsis_id` (the overlay maps ESPN athletes and Sleeper players to it, AGENTS.md rule 3 — ids only), `team`
  (nflverse abbreviations: Sleeper's `LAR` and ESPN's `WSH` are stored as `LA` and `WAS`), `player_key` (the source's
  own id). An MFL team unit (TMQB / TMPK / TMDEF) has no gsis id and no events of its own; its starter's are his.
- **Which roster**: `GET /api/events?league=&team=` reads the roster through `availability.roster_context` — the
  house path for the house leagues, Sleeper on demand, MFL from the league's export — then the store by its players'
  gsis ids. So "What changed" and the QA route work the same for `mfl:70587` team 8 as for Scrubs roster 2.
- **Defensive events**: a corner's IR is an `availability` event with his team (`CAR`); the matchup evidence reads
  them by the opponent (`events.for_team`), for any league's receiver.
- **Cost per league**: none — the rows grow with the NFL's news, not with the leagues (an estimate: 30,000–80,000 rows
  a season, ~500 bytes each). The readers are one cached query per screen (a minute).

## The setup flow and the provider matrix (Wave I-I, II-5, 2026-10-04)

**One setup flow** at `/leagues` (also what `/` shows with no league): **Fantasy platform** (Sleeper / MyFantasyLeague;
`?platform=` and remembered on the device) → the identifier (Sleeper: a username, or a league link / id — the new
`GET /api/leagues?sleeper=<link or id>` answers the MFL card's shape: the league, its teams, `roster_id: null`, the card)
→ the league → the team (pre-selected when the username owns one; a picker on the card otherwise, and on a username row
with no team of yours) → My Week. Inline "where to find it" with an example per platform; specific errors with a fix
(`code` / `error` / `fix` on the 404s — `ondemand.SETUP_CODES`; 502 `provider_down`, 503 `busy`); no account.
**Capabilities**: `platforms.capabilities(provider)` — eight features (scoring, roster slots, matchups, players,
waivers, transactions, team assets, news), each `yes` / `partial` / `no` with words; `GET /api/providers`; the setup
answers carry their provider's. A screen says `unavailable` instead of an empty list (League's moves on MFL). The
matrix, the ESPN verdict and the Yahoo note: `docs/PROVIDERS.md`; the account design: `docs/ACCOUNTS.md`.


## Four providers: the seam (Wave I-K, IK-3, 2026-10-05)

`platforms.provider_of(key)` is the one place a league key's provider is read: Sleeper ids bare, `mfl:<id>`,
`espn:<id>` (or `espn:<season>:<id>` for a past season), `yahoo:<game>.l.<id>` (Yahoo's league key, `yahoo:461.l.4242`;
`yahoo:nfl.l.<id>` means this season's game and is resolved to the number before a key is remembered). The old names
stay (`platform(key)` = `provider_of`, `is_mfl`, `check_key`); new `is_espn`, `is_yahoo`, `is_sleeper`,
`provider_short` ("Sleeper" / "MFL" / "ESPN" / "Yahoo"). **The Router** (`anyleague.sleeper()`) dispatches every
Sleeper-shaped call by prefix: Sleeper's client, `MFLLeagues`, IK-1's `ESPNLeagues(espn_client.ESPN(), directory)`,
IK-2's `YahooLeagues(yahoo_client.Yahoo(), directory)` — the last two built on first use from the environment (fixture
dirs `LEAGUE_LAB_ESPN_LEAGUE_FIXTURES` / `LEAGUE_LAB_YAHOO_FIXTURES`; the Router is rebuilt when one changes). A provider
whose module is missing or whose client cannot be built — or whose read says the server is not set up (IK-2's
`YahooNotConfigured`) — answers `ProviderNotConfigured` (a `LeagueNotFound`, code `<provider>_not_configured`): every
route says it in words, never a 500. `players()` merges each built adapter's `extra_players` (`espn:<id>` / `yahoo:<id>`
rows); `stats()` and `calls` add each client's. A Sleeper or MFL answer does not move (`test_ik3`
`test_router_sleeper_and_mfl_answers_unchanged`; the whole suites unchanged).

Screen by screen, a prefixed key is "not Sleeper": no Sleeper market line (IE-0's rule, now `not is_sleeper`), the
league's own app named ("Open ESPN to edit your lineup ↗" → the league's page), the waiver line "Claims run on ESPN's
schedule for this league: see ESPN for the time" (the claim time is not read), a manager with no shared name has none
(not "unknown"). `known_league` is false for every prefixed key (always on demand).

**Private data and the caches.** The memo regions key by league id, so a private ESPN league read with one user's
cookies must never be served from a cache to another: `main.require_auth` (which every data route depends on) runs
`provider_gate` — for an `espn:` key the Router runs IK-1's `ESPNLeagues.require_access` (a known-private league whose
cookies this request does not carry → `espn_league_private`) **before** the route and its memo; the trade POST checks its
body's league. Yahoo's client keys its own cache by who read (a hash of the refresh token).

## ESPN (Wave I-K, IK-1 adapter + IK-3 setup, 2026-10-05)

`GET /api/leagues?espn=<id or link>` answers the `?mfl=` shape (`ondemand.espn_league`): the league (`league_id`
`espn:4242`, name, season, size, scoring label, the league's ESPN page), the teams to pick from, the team a link names
(`fantasy.espn.com/football/team?leagueId=4242&teamId=3` → that team pre-selected, through IK-1's `roster_id_of` — ESPN
team ids can skip numbers), the players with no Sleeper id (`unmapped`), the card (lineup and scoring read-back), the
capabilities, `espn_private`. Links: IK-1's `espn_client.parse_link` (a bare id, `espn:4242`, `…/league?leagueId=`,
`…/team?leagueId=&teamId=&seasonId=`, `…/league/standings?leagueId=`). Errors (II-5's `SetupError`, IK-1's words through
`espn_client.setup_words`): `espn_link_invalid` ("That is not an ESPN league link or id."), `espn_league_unknown` ("ESPN
has no league 777 in 2026."), `espn_league_private` ("ESPN league 5150 is private. ESPN has no sign-in for other apps; a
public league works by its id (Settings → Basic Settings → League Visibility in ESPN)"), `espn_not_configured`; ESPN down
→ 502 "ESPN did not answer". **The private switch**: with `LEAGUE_LAB_ESPN_PRIVATE=on` (and `LEAGUE_LAB_API_SECRET`),
`/api/providers.espn_private` is true and a private-league error carries `private_form: true`: the setup screen opens
**Private league?** — "Your ESPN cookies stay in your browser; isuckatfantasy reads your league with them and never
stores them." — two password fields (`espn_s2`, `SWID`) posted to IK-1's `POST /api/espn/connect` (the sealed `ll_espn`
cookie), then the league is asked again. Off (the default), the form never shows and the fix line says to ask the
commissioner to make the league public. The setup screen's line: "Unofficial: ESPN has no public API for fantasy
leagues. isuckatfantasy reads what a public league shows anyone, read-only. New: not verified on a live league yet."

## Yahoo (Wave I-K, IK-2 adapter + IK-3 setup, 2026-10-05)

Yahoo shares no league without a signed-in Yahoo user (IK-2's reading of the OAuth guide: the authorization-code grant
only, no app-only token), so the setup is **Connect with Yahoo → your leagues → the team**: the button is a link to
IK-2's `GET /api/yahoo/connect` (Yahoo's consent page, back to `/leagues?platform=yahoo` with the sealed `ll_yahoo`
cookie); `GET /api/leagues?yahoo_me=1` (`ondemand.yahoo_me`, never cached, always 200) answers `{configured, connected,
season, leagues: [{league_id, name, season, total_rosters, scoring_label, roster_id, team_name, url, card}], note}` from
IK-2's `YahooLeagues.my_leagues()` — each row opens My Week on the user's own team. A league link works too once
connected: `GET /api/leagues?yahoo=<link, key or id>` (`football.fantasysports.yahoo.com/f1/12345` and `…/f1/12345/3` →
team 3 pre-selected; `461.l.12345`, `461.l.12345.t.3`, `yahoo:461.l.12345`; a bare id) → the `?mfl=` shape. Without
`LEAGUE_LAB_YAHOO_CLIENT_ID` / `_SECRET` the server says **"Connect with Yahoo — coming soon"** (`/api/providers.
yahoo_configured: false`; `?yahoo=` → `yahoo_not_configured` before any read). Errors are IK-2's codes and words
(`yahoo_client.setup_parts`): `yahoo_sign_in_required`, `yahoo_session_expired`, `yahoo_league_unknown`,
`yahoo_link_invalid`, `yahoo_not_configured`. "Disconnect Yahoo" posts IK-2's `POST /api/yahoo/disconnect`.

## The id map (Wave I-K, IK-3 audit, 2026-10-05)

`scripts/id_map_audit.py` (read-only; the database in `.env`, or `--csv <db_playerids.csv>`) measures how many of this
season's QB–TE carry each provider's id in nflverse / dynastyprocess `ff_playerids` (`raw.nfl_ff_playerids`, the
nightly's copy) and in Sleeper's own directory (`staging.stg_sleeper__players.espn_id` / `yahoo_id`). On `league_lab_m1`
(the 2026-09-26 snapshot; ff 12,508 rows):

| measure | dim_player 2026 QB–TE | Sleeper directory, active QB–TE | rostered in a house league |
|---|---|---|---|
| players | 772 | 817 | 286 |
| a row in ff_playerids | 713 (92.4%) | 735 (90.0%) | 286 (100.0%) |
| `espn_id` in ff | 713 (92.4%) | 734 (89.8%) | 286 (100.0%) |
| `espn_id` in Sleeper's directory | 161 (20.9%) | 201 (24.6%) | 73 (25.5%) |
| `espn_id` in either | 713 (92.4%) | 741 (90.7%) | 286 (100.0%) |
| ff and Sleeper disagree (espn) | 1 | 0 | 0 |
| `yahoo_id` in ff | 459 (59.5%) | 495 (60.6%) | 188 (65.7%) |
| `yahoo_id` in Sleeper's directory | 161 (20.9%) | 208 (25.5%) | 73 (25.5%) |
| `yahoo_id` in either | 459 (59.5%) | 509 (62.3%) | 188 (65.7%) |
| `mfl_id` in ff | 713 (92.4%) | 735 (90.0%) | 286 (100.0%) |

**What it means.** ESPN and MFL ids cover every rostered skill player. **Yahoo does not**: of the 98 rostered QB–TE
without a `yahoo_id`, 50 are 2026 rookies (50 of 50), 47 are 2025 rookies (47 of 47), 1 is from 2023 — nflverse has not
filled `yahoo_id` for the last two draft classes, and Sleeper's directory fills none of them. A Yahoo league's rookies
(Jeanty, Cam Ward, Hampton, Skattebo …) are matched by IK-2's second step — a unique name + position in Sleeper's
directory, reported as "name" — or listed unvalued as `yahoo:<id>`. The players outside ff (7–10% of the wider lists)
are deep reserves no house roster carries.

**The quarantine rule (duplicates).** An external id (`espn_id`, `yahoo_id`, `mfl_id`) that sits on two or more ff rows
naming different players (different gsis / Sleeper ids) is **quarantined**: the lookup answers no match — never "the
first row wins" or "the last row wins" — and the adapter's next step takes the player (the unique name + position match,
reported, else the unmapped row, listed and unvalued). AGENTS.md rule 3 (identity never through a name) is kept: the
name step is the adapters' reported fallback, not a join. Today: 6 `espn_id`s are duplicated (none on a 2026 QB–TE:
safeties, a punter, and RB / TE depth players of 2015–2016), 0 `yahoo_id`, 0 `mfl_id` (`--list-quarantine` lists them).
`player_ids.read` applies it to `yahoo_id` (IK-2) but not yet to `espn_id` (the last row wins) or `mfl_id` — a few lines
for whoever next owns the loader; with no current skill player affected it moves no answer.

## Reference league keys — browsing without a league (Wave I-M, IM-3, 2026-10-06)

`ref:ppr`, `ref:half` and `ref:std` are leagues that exist nowhere: `api/league_lab_api/refleague.py` resolves them (the
one place) to a Sleeper-shaped league with the reference scoring's `scoring_settings` (`ppr`, `scrubs` — half PPR, 4-pt
pass TD —, `standard` in `analytics_seeds.reference_scorings`), standard slots (QB, 2 RB, 2 WR, TE, FLEX, K, DEF), the
current season, no rosters, no users, no matchups; `platforms.REFERENCE` answers the Router's calls for a `ref:` key
(`provider_of` → `reference`), so every research route that serves an unknown league on request serves it unchanged,
priced in that scoring. The API takes ownership out of the answer (`refleague.public`: absent, not empty) and answers the
decision routes with 404 `{"code": "needs_league"}`. `/api/record` for a reference key is the reference house league's
model record (Half PPR) without its lineup record, and says so for PPR / Standard. A reference key is never remembered
on the device (`lib/refleague.ts`); GA's `platform` is `none`.

### The family of reference keys (Wave I-N, IN-2, 2026-10-06)

The key grew from three scorings to a small closed family, canonical and strictly parsed in **one place**
(`platforms.parse_reference`; the web's `lib/refleague.ts` `parseRef` is the same grammar):

    ref:<scoring>[.sf][.tep][.p6][.t8|.t10|.t14]

| part | values | what it changes |
|---|---|---|
| scoring | `ppr` (PPR) · `half` (Half PPR, the default) · `std` (Standard) · `espn` (ESPN's default) · `yahoo` (Yahoo's default) | the points: `ppr` / `half` / `std` are the seed's `ppr` / `scrubs` / `standard`; `espn` = `ppr` with −2 per interception; `yahoo` = `scrubs` (−1 per interception: Yahoo's offense *is* Half PPR's — help.yahoo.com/kb/SLN6489 as the brief verified it: 1 per 25 passing yards, 4 per passing TD, 1 per 10 rushing / receiving yards, 6 per TD, 2 per two-point conversion, −2 per fumble lost) |
| `.sf` | superflex | a `SUPER_FLEX` slot (the value's replacement level; not the points) |
| `.tep` | TE premium | `bonus_rec_te` 0.5 (+0.5 per tight-end catch) |
| `.p6` | 6-point passing touchdowns | `pass_td` 6 |
| `.tN` | 8 · 10 · 14 teams (12 when absent) | `total_rosters` (the value's replacement level; not the points) |

Options come in that order, lower case; any other spelling — another order, `.t12`, a repeat, an unknown part, more
than 32 characters — is not a key (404, never a cache entry: `api/tests/test_in2.py`). **5 × 2 × 2 × 2 × 4 = 160
keys** (`platforms.REF_KEYS`); `ref:ppr` / `ref:half` / `ref:std` mean what they meant and `ref:half` stays the default.
Sleeper has no single default (a Sleeper league picks PPR, Half PPR or Standard when it is made), so there is no
"Sleeper" preset: the picker says so in one line. Kickers and defenses use the kicking and defense rules of the seed the
scoring starts from (ESPN's and Yahoo's own K / DEF tables are not modelled: their points-allowed buckets differ from
Sleeper's keys and a K / DEF outside a fitted reference would be unvalued — Risks above).

**How a key is priced.** `refleague.league(key)` is the Sleeper-shaped league (the shape's scoring, slots and size;
its `name` is the key in words — "Half PPR", "PPR · superflex · 10 teams" — never "No league"). Five of the 20 distinct
scorings are a fitted reference exactly (`ref:half`, `ref:yahoo` = `scrubs`; `ref:ppr`; `ref:std`; `ref:ppr.tep` =
`te_premium`; with `.sf` / `.tN` they price the same) and take the nightly's ranges as they are; every other is
priced on request with the nearest reference's range stretched (`anyleague.approximate_ranges`, § "The ranges"
above) — the answers' `pricing` ("how this is priced") says which. **Caches**: a priced week and a rest of season are
keyed by the scoring (`Shape.scoring_key`: the key without `.sf` / `.tN`), so the 160 keys hold at most 20 priced
scorings in `anyleague`'s `priced` / `ros` regions; the value tables (`refleague._values`, region `ref_values`) keep
the 24 most recent keys for 10 minutes (~600 rows each). Nothing is keyed by user text: `shape()` refuses everything
outside `REF_KEYS` before any cache is read.

**What browsing shows** (`refleague.card`, `refleague.public`): the player card for a reference key drops every
ownership line (the header's "free agent in this league", Availability's "Free agent — nobody in this league has him",
Value's "Free agent: the Waiver Wire page…", a search hit's "· free agent"), says the scoring where it said "this
league's scoring", gains `ref_value` (the value without a league, docs/METRICS.md § "Value without a league") and the
foot line "Open your league to see who has him and what he is worth to your team." The trade calculator without a
league is `GET /api/trade-calc/free?league=ref:…&give=&get=` (`api/league_lab_api/freetrade.py`; `research` bucket):
gsis ids only (`^00-\d{7}$`), six a side at most, a player on one side only.
