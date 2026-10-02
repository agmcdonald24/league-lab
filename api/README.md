# League Lab API (plan D7 spike; the API for any league: plan F3)

A read-only JSON API over the same marts the Streamlit app reads, plus the phone web app (`web/`) served as
static files: **one process, one deploy**. It exists to let Andrew compare My Week and the player card on a
phone-first stack with the Streamlit pages (`docs/FRONTEND_DECISION.md`). Nothing in `app/`, `src/` or `dbt/`
depends on it; the nightly does not change.

## What it serves

| Endpoint | What | Source |
|---|---|---|
| `GET /api/session` | `{gate, signed_in}` | — |
| `POST /api/login` `{password}` | sets the `ll_auth` cookie (180 days) and returns the token | `LEAGUE_LAB_APP_PASSWORD` |
| `POST /api/logout` | clears the cookie | — |
| `GET /api/leagues` | current-season leagues (the house leagues), unchanged | `ui.current_leagues()` |
| `GET /api/leagues?username=` (F3) | a Sleeper user's NFL leagues this season and their own team in each (below) | Sleeper `/user/<name>`, `/user/<id>/leagues/nfl/<season>`, each league's rosters + users |
| `GET /api/leagues/{league_id}/rosters` | the team picker's options | the query in `ui.perspective()` |
| `GET /api/my-week?league=&team=` | Home's My Week: the record line, the league line, the cards (numbers **and** the cards' own text), the lineup (4 columns), the full lineup (+ bench, can't play), "How to read this", movers | `cards.lineup_rows` / `decisions` / `decision_cards` / `league_line` / `lineup_frame` / `howto_cards`; Home's two inline queries copied |
| `GET /api/my-week?league=<any Sleeper id>&team=` (plan E3) | **a league the database does not have** is served on demand: Sleeper's league / rosters / users, the NFL-wide stat lines priced in its scoring, ranges from the nearest fitted scoring, the lineup solved per request; same JSON plus `source: "sleeper"` and `on_demand` (range reference, unmapped players and scoring keys, K / DEF source, timings). `source=sleeper` forces it for a known league. 404 for a league Sleeper does not have, 502 when Sleeper does not answer | `league_lab.anyleague` (`lineup.build`, `scoring.compute_points`), `ondemand.py`, the cards via `myweek.cards_from_rows`; design `docs/ANY_LEAGUE.md` |
| `GET /api/player/{gsis}?league=&team=` | the player card: header + Usage, Projection, Availability, Value, Signals as ordered blocks, + `ros`, `missing`, `source` (F3). Any Sleeper league: built on demand (`source=sleeper` forces it for a house league) | `pages/0_Player.py`'s queries and sentences, copied verbatim; `cards.alternative` / `bench_gap`, `signals.*`; on demand `ondemand.PlayerContext` |
| `GET /api/ros?league=&position=QB\|RB\|WR\|TE\|K\|DEF\|ALL&limit=50` (F3) | rest of season, sorted by points | `mart_player_ros_projection` (house league) or `anyleague.ros_table` (priced on request) |
| `GET /api/record?league=` (F3) | our record vs Sleeper's projections, week by week + the season | `mart_projection_record` (house leagues; `available: false` elsewhere) |
| `GET /api/search?league=&q=` | the player card's search box (25 hits) | the page's query |
| `GET /api/status` | the freshness line, the stale-injury warning, + `sleeper` (cache ages, the call budget) and `board_source` (F3) | `ui.freshness_banner()`, `Sleeper.stats()` |
| `GET /api/docs` | OpenAPI page | — |
| anything else | the web app (`web/dist`): a real file, else `index.html` | — |

**Reuse, not a re-derivation.** `league_lab_api/applib.py` loads `app/lib/cards.py`, `ui.py` and `signals.py`
**unchanged** as a private package whose `db` module is this API's (same `query()` contract, no Streamlit) and
whose `streamlit` is a stand-in that records what a function would have drawn. So the numbers come from the
same SQL and pure functions, and the card text is what `render_decision` writes — a wording change in
`cards.py` (D6 is changing it this round) appears in both front ends with no change here. The player page keeps
its logic inline in the page file, so `player.py` copies it (marked); `tests/test_parity.py` renders the real
Streamlit pages headlessly and fails on any difference.

Every query is cached 10 minutes (the app's `st.cache_data(ttl=600)`); JSON is `Cache-Control: private,
max-age=120`; hashed web assets are immutable; responses are gzipped. A missing mart (a sync in progress)
answers 503 with the app's sentence.

## The JSON of the plan-F3 routes

Errors everywhere: `{"error": "<plain words>", "detail": …}` — 404 an unknown league / team / player / user, 502
`{"error": "Sleeper did not answer"}`, 503 `{"error": "the numbers are not ready yet"}` (a mart missing) or
`{"error": "busy, try again in a minute"}` (our Sleeper budget spent; `Retry-After: 60`).

```jsonc
// GET /api/leagues?username=test_manager            (404 {"error": "no such Sleeper user"})
{"user": {"user_id": "9100000000000000001", "username": "test_manager", "display_name": "Test Manager", "avatar": null},
 "season": 2026,
 "leagues": [   // sorted by name
   {"league_id": "1321941740235550720", "name": "Forever Unclean Dynasty", "season": 2026, "total_rosters": 12,
    "scoring_label": "12-team superflex dynasty · full PPR · 6‑pt pass TD · yardage bonuses", "roster_id": 12,
    "team_name": "Team 11", "status": "in_season", "in_database": true}, …]}
// roster_id / team_name: the user's own (owner_id or co_owners); null in a league they only run.
// scoring_label: dim_league_season.scoring_label's rule (anyleague.scoring_label; equal for the house leagues: tested).

// GET /api/my-week?league=&team=  — as before, plus:
{"source": "database" | "sleeper",
 "opponent": {"roster_id": 6, "team_name": "…", "manager": "…", "matchup_id": 4, "lineup_value": 120.31} | null,
 "scoring_label": "…",                       // on demand too now
 "on_demand": {…, "board_source": "nfl_wide" | "borrow", "opponent_note": null | "busy" | "sleeper_unavailable"}}
// opponent: the roster sharing the matchup_id in Sleeper's /league/<id>/matchups/<week> (cached 5 min); a house
// league falls back to fct_league_matchup when Sleeper is down. lineup_value = his best lineup this week: the
// nightly's (ops.lineup_totals) for a house league, solved on request (lineup.build) otherwise — equal to the cent.

// GET /api/player/{gsis}?league=&team=  — as before, plus:
{"ros": {"points": 236.25, "games": 12, "p10": 196.5, "p90": 276.0, "pos_rank": 1, "playoff_points": 39.18,
         "from_week": 4, "last_week": 16} | null,
 "missing": [],                                // on demand: ["value.points_per_game", "signals.upside"] where they apply
 "source": "database" | "sleeper",
 "on_demand": {"range_method": "ratio", "range_reference": "…", "profile_league": "…", "scoring_label": "…"}}  // on demand only

// GET /api/ros?league=&position=RB&limit=50
{"league_id": "…", "source": "database" | "sleeper", "position": "RB", "from_week": 4, "last_week": 16,
 "playoff_week_start": 15, "pos_rank_note": "…",
 "players": [{"gsis_id", "player_key", "player_name", "position", "team", "ros_points", "ros_games",
              "playoff_points", "p10", "p90", "pos_rank", "rostered_by_roster_id", "rostered_by_team"}, …]}
// player_key = gsis_id, or a team defense's Sleeper id (gsis_id null). pos_rank: among every projected player at
// the position on an active NFL roster, rostered or not — on demand the same population as the mart (tested).

// GET /api/record?league=
{"league_id": "…", "available": true, "season": 2026, "from_week": 4 | null,
 "weeks": [/* mart_projection_record rows, scope = 'week' */], "summary": {/* the season ALL row */, "by_position": […]} | null,
 "notice": null | "No week on the record yet: …"}
{"league_id": "9000000000000000001", "available": false, "why": "the record is kept for the leagues the nightly scores"}

// GET /api/status  — as before, plus:
{"sleeper": {"mode": "live" | "fixtures", "calls": 7, "stale_served": 0,
             "bucket": {"tokens": 293.0, "capacity": 300.0, "per_minute": 300.0, "refused": 0},
             "cache": {"rosters": {"entries": 2, "fresh": 2, "oldest_s": 41.2, "newest_s": 3.0, "ttl_s": 600}, …},
             "players_file_age_s": 5120.4},
 "board_source": "auto" | "nfl_wide" | "borrow"}
```

**Sleeper** (`src/league_lab/sleeper_client.py`; terms and budget: `docs/SLEEPER_TERMS.md`): one client per process,
caches by kind of call (player directory a day, on disk under `LEAGUE_LAB_CACHE_DIR`; league settings and users a
day; rosters 10 min; matchups 5 min; username lookups and league lists an hour), the last good answer served when
Sleeper fails, and a token bucket of `LEAGUE_LAB_SLEEPER_PER_MIN` (300) calls a minute.

**The board** (`anyleague.load_board`): F1's NFL-wide tables (`ops.projection_lines`, `ops.projection_ranges`,
`ops.kd_lines`, the seed `reference_scorings`; their names live in `anyleague.NFL_WIDE`, the one place) when they
hold the week, else E3's borrowing from `ops.projections`. A league's ranges come from the reference scoring whose
mapped keys equal its own, else the nearest by median |log(price ratio)|; K / DEF are priced from their stat lines
in the league's own scoring. `LEAGUE_LAB_BOARD_SOURCE=borrow|nfl_wide` forces one (a kill switch).

## Research (G1)

Plan G1 (Wave G): the research pages of the Streamlit console (`3_Trends.py`, `5_Matchups.py`, `9_Players.py`,
`10_Receivers.py`) as JSON for **any** Sleeper league — `league_lab_api/research.py`, helpers in
`src/league_lab/research.py`, tests in `tests/test_research.py`. Every route takes `league=` (+ `source=sleeper` to serve
a house league through the on-demand path), sits behind the beta gate, and answers errors as above plus **400**
`{"error": "<plain words>"}` for a parameter it cannot use (`sort=nope`, `view=sideways`, `weeks=x`).

**The rules.** A row carries the mart's columns under the mart's names (`docs/DATA_MODEL.md`), plus `headshot_url`,
`team`, `position` (`dim_player`; the mart's own team / position when it has one) and `rostered_by_roster_id` /
`rostered_by_team` in this league (house league: `mart_player_availability`; else Sleeper's rosters via
`player_id_map`). **Points are this league's scoring** wherever a point appears: a house league reads
`fct_player_game_league` / `mart_league_player_season` / `mart_player_week_projections`; any other league prices
`fct_player_game`'s stat columns per request with `scoring.compute_points` (position passed) — equal to the house
league's marts to the cent on every 2025 and 2026 game (tested). The NFL research marts are scored in the **reference
league's** scoring (League of Scrubs): such a field is renamed `<column>_ref`, and this league's number sits next to it
under the plain name. Every response opens with the league block:

```jsonc
{"league_id": "1321941740235550720", "league_name": "Forever Unclean Dynasty", "season": 2026, "week": 4,
 "source": "database" | "sleeper", "points_source": "league marts" | "priced on request (scoring.compute_points)",
 // on demand only: the house league whose expected points this league's are priced from, and whether exactly
 "expected_points_reference": "1389709692405551104", "expected_points_exact": true,
 "howto": "- **…** markdown bullets: the page's \"How to read this\"", "scoring_note": "Fields ending in `_ref` …"}
```

**Expected points on demand.** The published expected line (`mart_player_expected_points`) carries 7 expected stats
(receptions, receiving / rushing / passing yards and TDs). A league's expected points = a house league's
(`fct_player_game_league.points_expected`, the full line) + the difference of the two scorings on those 7 columns:
exact when the two agree on interceptions, fumbles and 2-point tries (`expected_points_exact`; the Test League and any
half-PPR-style league with −1 per interception match Scrubs), otherwise off by that weight × the expected count
(dynasty priced from Scrubs, 2025: 0.60 a game for QBs on average, at most 2.03; 0.3% of the other rows off by more than 0.01).

**Not re-priced (reference scoring only, `_ref`):** `mart_player_trends` values of the metrics `points` /
`expected_points` (flagged `ref_scored: true` in `metrics`), `mart_player_trend_tags.expected_points_z`,
`mart_defense_position_profile`'s `points_allowed_pg_ref`, `offense_baseline_pg_ref`, `adjusted_points_pg_ref`,
`league_points_pg_ref` and the ranks on them (`rank_points_ref`, `rank_adjusted_ref`: the comparison verdict reads
these, as on the page), `mart_cb_matchups` has no points; the cornerback "best corners" split is re-priced.

```jsonc
// GET /api/trends?league=&position=ALL|QB|RB,WR…&view=all|over|under&season=&who=all|fa|rostered|team&team=
//                &min_games=1&sort=&dir=&limit=50&metrics=moved|all
// default order: view=over → gap desc, under → gap asc, all → momentum desc
{… league block, "trend_season": 2026, "view": "over", "positions": ["QB","RB","WR","TE"], "total": 167,
 "early_read": true, "notice": "No player in this list has four games yet (NFL 2026). …",   // null from game four
 "players": [{
   // mart_player_trend_tags (reference-scored points renamed _ref)
   "gsis_id": "00-0038543", "player_name": "Jaxon Smith-Njigba", "position": "WR", "team": "SEA", "games": 2,
   "latest_week": 2, "tags": "not enough games yet", "momentum": null, "opportunity_trend": "insufficient",
   "target_share_l3": 0.44, "snap_share_l3": 0.785, …, "points_l3_ref": 30.1, "points_change_ref": null,
   "expected_points_l3_ref": 16.51, "expected_points_change_ref": null, "expected_points_z": null,
   // over- vs under-performing, this league's scoring (mart_league_player_season: ppg, expected_per_game, diff_per_game)
   "league_games": 2, "ppg": 39.35, "xppg": 20.01, "gap": 19.35, "gap_direction": "over", "games_with_expected": 2,
   // the trend windows re-priced in this league's scoring (mart_player_trends' rule: last 3 appearances vs before)
   "points_l3": 39.35, "points_prior": null, "points_change": null, "expected_points_l3": 20.01, …,
   "headshot_url": "https://static.www.nfl.com/…", "rostered_by_roster_id": 9, "rostered_by_team": "…", "is_free_agent": false,
   "metrics": [{"metric": "adot", "metric_label": "aDOT", "display_kind": "num1", "games_with_metric": 2, "value_prior": null,
                "value_l3": 8.95, "value_season": 8.95, "value_latest": 11.0, "change": null, "z": null,
                "slope_per_game": 4.09, "direction": "insufficient", "confidence": null, "ref_scored": false}, …],
                // mart_player_trends: the moved metrics (or every metric while he has < 4 games; metrics=all: always)
   "role_alert": null | {"direction": "up", "kind": "absence_beneficiary", "kind_label": "Filling in", "headline": "…",
                         "lines": "Why: …", "cause_text": "…", "change_text": "…", "games_held": 1, "since_week": 2, …}}],
 "role_alerts": [   // the page's first section: this week's live alerts (mart_player_role_alerts.is_live) in this league
   {"gsis_id": "00-0041489", "player_name": "Germie Bernard", "position": "WR", "team": "PIT", "direction": "up",
    "kind_label": "Filling in", "headline": "Filling in: Germie Bernard — snap share 4% → 79%, …",
    "lines": "Why: Michael Pittman out injured. It ends when …", "who": "on <team>" | "free agent" | "on your team", …}],
 "howto_sections": [{"title": "How to read role alerts", "text": "- …"}]}

// GET /api/matchups/defense?league=&position=ALL|QB|…   (ALL = the positions the league starts, of QB RB WR TE K)
{… league block, "dvp_season": 2026, "profile_week": 4, "positions": ["QB","RB","WR","TE"], "n_defenses": 32,
 "weeks_used": [1, 2, 3],
 "teams": [{   // one row per defense × position, sorted by position then rank_std: the heatmap's cells
   "defense": "CAR", "position": "RB", "season": 2026, "games": 2, "through_week": 2, "games_l4": 2,
   // mart_defense_vs_position_current's columns in THIS league's scoring (+ the mart's own as _ref)
   "points_allowed_per_game_std": 40.3, "rank_std": 1, "points_allowed_per_game_l4": 40.3, "rank_l4": 1,
   "points_allowed_per_game_std_ref": 34.3, "rank_std_ref": 1, "points_allowed_per_game_l4_ref": 34.3, "rank_l4_ref": 1,
   // mart_defense_trends' rule in this league's scoring (+ the mart's own as _ref): softer / stiffer / steady / insufficient
   "allowed_l3": 40.3, "allowed_prior": null, "allowed_season": 40.3, "change": null, "z": null, "direction": "insufficient",
   "allowed_l3_ref": 34.3, "allowed_prior_ref": null, "change_ref": null, "z_ref": null, "direction_ref": "insufficient",
   // mart_defense_position_profile as of this week (games before it)
   "opps_allowed_pg": 32.0, "targets_allowed_pg": 4.5, "carries_allowed_pg": 27.5, "yards_per_opp_allowed": 6.34,
   "td_rate_allowed": 0.0625, "gives_up": "volume and big plays", "rank_opportunity": 7, "rank_efficiency": 1,
   "rank_td_rate": 4, "rank_targets": 22, "rank_carries": 4, "points_allowed_pg_ref": 34.3,
   "offense_baseline_pg_ref": 25.64, "adjusted_points_pg_ref": 4.33, "league_points_pg_ref": 18.99,
   "rank_points_ref": 1, "rank_adjusted_ref": 5}]}

// GET /api/matchups/cb?league=&team=<roster_id>&limit=50   (no team: every rostered WR / TE of the league)
{… league block, "team": 12,
 "summary": ["**Amon-Ra St. Brown** vs CAR: no clear side (…): **Mike Jackson (left corner, #37 of 74, solid)** or …"],
 "caption": "Likely across from him = …",
 "matchups": [{   // every mart_cb_matchups column for the week (lcb_*, rcb_*, nb_*, likely_cover_*, cover_rank, side_share …)
   "gsis_id": "00-0036963", "player_name": "Amon-Ra St. Brown", "position": "WR", "team": "DET", "week": 4, "opponent": "CAR",
   "call_status": "called", "call_strength": "even", "likely_cover_name": "Mike Jackson", "cover_rank": 37, …,
   "is_starter": true,                                   // Sleeper's current starters (house: mart_player_availability)
   "proj_points": 15.2, "p10": 6.1, "p25": 9.6, "p75": 20.0, "p90": 25.3,       // this league's scoring (the card's numbers)
   "line": "**Amon-Ra St. Brown** vs CAR: …",          // app/lib/matchups.cb_line
   "lean": "Since the start of 2025, 199 of his targets had a direction: …",   // lean_text (null for a tight end)
   "corners": [{"gsis_id": "…", "defender_name": "Mike Jackson", "depth_position": "Left", "quality_rank": 37,
                "quality_label": "solid", "rank_this_season": 41, "rank_last_4": 30, "passer_rating_allowed": 88.1, …}],
   "faced": [{"defender_name": "…", "defense": "ATL", "games": 1, "targets": 10, "receptions": 5, "receiving_yards": 101,
              "defender_snap_share": 1.0, "share_of_targets": null, "evidence": "same_game"}],   // mart_receiver_vs_cb, this season
   "cover_split": {"ppg_vs_shutdown": 8.3, "games_vs_shutdown": 3, "ppg_vs_rest": 10.7, "games_vs_rest": 14,
                   "text": "vs shutdown corners 8.3 a game (3 games), vs the rest 10.7 a game (14 games)"} | null,  // WRs, league scoring
   "headshot_url": "…", "rostered_by_roster_id": 12, "rostered_by_team": "…"}]}

// GET /api/players?league=&season=&position=ALL|QB|RB|WR|TE|K&season_type=REG|POST&min_games=1&q=&sort=points&dir=desc
//                 &limit=50&offset=0          (sort = any returned column; limit ≤ 500)
{… league block, "players_season": 2025, "season_type": "REG", "positions": ["RB"], "total": 145, "offset": 0,
 "columns": ["carries", "carry_share", …],      // the page's stat columns for the position(s), in its order
 "players": [{"gsis_id": "00-0033280", "player_name": "Christian McCaffrey", "position": "RB", "teams": "SF", "games_played": 17,
              "carries": 311, "carry_share": 0.6466, …,                                   // mart_player_season
              "points": 416.6, "ppg": 24.51, "expected_per_game": 25.51, "diff_per_game": -1.01, "position_rank_ppg": 1,
              "points_current_scoring_ref": 365.6, "points_current_scoring_per_game_ref": 21.51,
              "headshot_url": "…", "team": "SF", "rostered_by_roster_id": 5, "rostered_by_team": "Team 5"}]}

// GET /api/receivers?league=&season=&season_type=REG&weeks=1-18&limit=50&players=<gsis,gsis>&context=half|score_state|
//                   down_distance|field_zone|qb|none        (no players: the page's candidates, 10+ targets, most first)
{… league block, "receivers_season": 2026, "season_type": "REG", "weeks": [1, 18], "context_type": "half",
 "yardsticks": {"WR": {"target_share": 0.27, "targets_per_game": 9.1, …}, "TE": {…}},   // the season's top-12 averages
 "receivers": [{"gsis_id": "…", "player_name": "…", "position": "WR", "team": "…",
   // the window (app/pages/10_Receivers.py summarize(): numerators and denominators summed over the same games)
   "games": 3, "targets": 30, "team_targets": 120, "target_share": 0.25, "air_yards_share": 0.39, "adot": 13.9,
   "receptions": 15, "receiving_yards": 253, "yac_per_rec": 6.5, "receiving_tds": 1, "snap_pct": 0.93, "targets_per_game": 10,
   "points_per_game": 16.43, "points_per_game_ref": 12.93,                       // league scoring / reference
   "first_read_target_share": 0.31, "first_read_rate_of_targets": 0.83, "route_participation": null, "tprr_proxy": null, …,
   // mart_player_recent_form at his latest game in the window
   "form_week": 3, "target_share_l3": 0.25, "target_share_l5": 0.25, "target_share_std": 0.25, "snap_pct_l3": 0.93,
   "points_per_game_l3": 16.43, "points_per_game_l3_ref": 12.93, "points_per_game_std_ref": 12.93,
   "context": [{"bucket": "H1", "bucket_label": "1st half", "games": 3, "targets": 14, "target_share": 0.24, …}],  // mart_player_context
   "rostered_by_roster_id": 3, "rostered_by_team": "…", "headshot_url": "…"}]}

// GET /api/compare?league=&a=<gsis>&b=<gsis>      (404 for an unknown player)
{… league block,
 "a": {"gsis_id": "00-0036900", "player_name": "Ja'Marr Chase", "position": "WR", "team": "CIN", "headshot_url": "…",
       "rostered_by_roster_id": 8, "rostered_by_team": "Taco Corp.",
       "projection": {"proj_points": 15.19, "p10": 5.75, "p25": 8.69, "p75": 21.44, "p90": 29.16},   // = /api/player's
       "season": {"games_played": 2, "targets_per_game": 6.5, "catch_rate": 0.69, …, "ppg": 14.85, "xppg": 12.1, "gap": 2.75,
                  "position_rank_ppg": 21, "ppg_ref": 12.6},
       "usage": {"target_share": 0.2, "carry_share": 0.0, "air_yards_share": 0.29, "first_read_target_share": 0.24,
                 "avg_offense_snap_pct": 0.91, "red_zone_target_share": 0.29, "red_zone_carry_share": 0.0, "route_participation": null},
       "last3": {"target_share_l3": 0.2, "snap_pct_l3": 0.91, "games_l3": 2, …, "points_per_game_l3": 14.85, "points_per_game_l3_ref": 12.6},
       "ros": {"points": 193.65, "games": 13, "p10": 152.2, "p90": 235.1, "pos_rank": 12, …},          // = /api/player's
       "next4": [{"week": 4, "bye": false, "opponent": "JAX", "is_home": true, "kickoff_at": "…", "opp_rank": 15, "opp_rank_ref": 18}, …],
       "matchup": {"games": 2, "targets_allowed_pg": 15.5, "gives_up": "big plays", "rank_targets": 24, …,
                   "points_allowed_pg_ref": 24.45, "rank_points_ref": 18, "adjusted_points_pg_ref": 1.95, "rank_adjusted_ref": 12}},
 "b": {… the same keys …},
 "verdict": "Chase projects 5.08 more (15.19 vs 10.11); the matchups are about even.",   // matchups.comparison_verdict
 "table": [{"what": "Projection", "a": "15.19", "b": "10.11"}, …],                       // matchups.comparison_rows
 "caption": "Week 4. The projection decides: …"}

// GET /api/player/{gsis}/games?league=&season=2026&season_type=ALL|REG|POST     (404 for an unknown player)
{… league block, "player": {"gsis_id", "player_name", "position", "team", "headshot_url", "rostered_by_roster_id", "rostered_by_team"},
 "games_season": 2026, "season_type": "ALL",
 "games": [{"game_id": "2026_01_TB_CIN", "season": 2026, "season_type": "REG", "week": 1, "game_date": "2026-09-13", "team": "CIN",
            "opponent": "TB", "is_home": true, "played": true, "roster_status": "ACT",
            "targets": 7, "receptions": 5, "receiving_yards": 51, …, "offense_snap_pct": 0.93,   // fct_player_game's stat columns
            "points": 12.1, "expected_points": 11.3,               // this league's scoring (null expected: no ffverse row)
            "points_ref": 9.6, "expected_points_ref": 9.1}]}
```

Latency (cold = every cache emptied, warm = the second call; TestClient, the sandbox's two shared cores):
`docs/STATUS.md` § Wave G, G1.

## Run it locally

```bash
cd api
uv sync                                                        # its own environment (api/.venv), Python 3.13
uv run uvicorn league_lab_api.main:app --port 8581             # reads the repository's .env (read-only role)
(cd ../web && npm ci && npm run build)                         # the web app at http://localhost:8581/
```

For front-end work, `cd web && npm run dev` (port 8582) proxies `/api` to 8581 and hot-reloads.

## Environment

| Variable | Meaning |
|---|---|
| `LEAGUE_LAB_APP_DB_URL` | the read-only role's connection string (hosted: the same value as the Streamlit secret) |
| `LEAGUE_LAB_APP_DB_USER` / `_PASSWORD`, `LEAGUE_LAB_DB_HOST` / `_PORT` / `_NAME` | used when the URL is not set (the local `.env`) |
| `LEAGUE_LAB_APP_PASSWORD` | the beta password; unset = open, like the app |
| `LEAGUE_LAB_API_SECRET` | optional signing key for the cookie; unset = derived from the password (changing the password signs everyone out) |
| `LEAGUE_LAB_WEB_DIST` | where the built web app is (default `web/dist`) |
| `LEAGUE_LAB_SLEEPER_FIXTURES` | plan E3: read Sleeper from `<dir>/league_<id>.json`, `rosters_<id>.json`, `users_<id>.json`, `players_nfl.json` instead of the network (tests, sandboxes); `python -m league_lab.anyleague fixtures <dir> <id> …` builds them from `raw.sleeper_*` |
| `LEAGUE_LAB_SLEEPER_API` | the Sleeper host (default `https://api.sleeper.app/v1`) |
| `LEAGUE_LAB_SLEEPER_PER_MIN` | plan F3: the Sleeper call budget of this process (default 300 a minute; Sleeper's limit is 1,000) |
| `LEAGUE_LAB_CACHE_DIR` | plan F3: where the Sleeper player directory is kept for a day (default `<repo>/.cache/`, git-ignored; the image: `/srv/cache`) |
| `LEAGUE_LAB_BOARD_SOURCE` | plan F3: `auto` (default: F1's NFL-wide tables when they hold the week), `nfl_wide`, `borrow` |
| `PORT` | the container's port (hosts set it) |

## Tests

```bash
cd api
uv run pytest -q              # 83 tests (see docs/STATUS.md § Wave F for the count on this data); the parity tests render the Streamlit pages: LL_SKIP_PARITY=1 skips them
uv run ruff check .
```

`test_myweek.py` / `test_player.py` check every endpoint against the marts with independent SQL (dynasty roster
12 and Scrubs roster 2, the current week); `test_parity.py` compares with the rendered Streamlit pages (it runs
`tests/streamlit_twin.py` in the repository's environment with `uv run --project ..`); `test_auth.py` the gate;
`test_static.py` the web app's files and headers; `test_anyleague.py` (plan E3) the on-demand path against the
marts with the two leagues' own Sleeper payloads as fixtures (`tests/fixtures/sleeper/`): the lineup to the cent,
the range error, an unknown league through the route, cold / warm latency (pinned to the borrowed board).
`test_f3.py` (plan F3): the Sleeper client with a fake clock (TTLs, the bucket, stale answers, the directory on
disk), the league picker, the opponent against `ops.lineup_totals`, the NFL-wide board against the marts (exact),
the fictional Test League with a K and a DEF, rest of season on demand against `mart_player_ros_projection`, the
player card on demand, the record, the status line, error shapes, the static app from a placeholder `dist`. The
fixtures: `tests/fixtures/make_f3_fixtures.py` (a fictional user `test_manager`; every Sleeper user id
pseudonymised); the NFL-wide tables in a clone: `psql … -f tests/fixtures/f1_tables.sql` (the NFL-wide tests skip
without them).

## Deploy (one service, the static app included)

`api/Dockerfile` builds the web app and the API into one image; build it from the repository root:

```bash
docker build -f api/Dockerfile -t league-lab-web .
docker run -p 8000:8000 -e LEAGUE_LAB_APP_DB_URL='postgresql://league_lab_app:…@…neon.tech/neondb?sslmode=require' \
           -e LEAGUE_LAB_APP_PASSWORD='…' league-lab-web
```

* **Render** (free web service: 512 MB, sleeps after 15 minutes without traffic, ~1 minute to wake; $7/month
  for always on): New → Web Service → the GitHub repo → Runtime *Docker*, Dockerfile path `api/Dockerfile`,
  build context `.` → Environment: the two variables above → health check path `/api/health`.
* **Fly.io** (no free allowance; a shared-cpu-1x 256 MB machine ≈ $2–3/month always on, less with
  auto-stop): `fly launch --dockerfile api/Dockerfile` from the repository root, `fly secrets set
  LEAGUE_LAB_APP_DB_URL=… LEAGUE_LAB_APP_PASSWORD=…`.
* **Railway** (Hobby $5/month including $5 of usage; a free plan of 0.5 GB RAM and one project): New project →
  Deploy from GitHub → set `RAILWAY_DOCKERFILE_PATH=api/Dockerfile` and the two variables.
* **Cloud Run** (2 million requests, 180,000 vCPU-seconds and 360,000 GiB-seconds free a month; scales to
  zero, a cold start of a few seconds): `gcloud run deploy league-lab --source .` with the Dockerfile path set.

Neon does not change: the API reads the same published marts with the same read-only role. The nightly does
not change either (it publishes marts; the API has no state of its own). A push to GitHub redeploys the
service; there is no restart stamp to bump (`app/requirements.txt`'s rule is Streamlit Community Cloud's).

If `app/lib/cards.py` ever imports from `league_lab.*` (the `src/` package), copy `src/` into the image too
(the stand-in already puts `src/` on the path) and add that module's dependencies to `api/pyproject.toml`.
