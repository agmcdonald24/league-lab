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
