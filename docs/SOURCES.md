# Source contracts and coverage

Plan §4. Every partition load records URL, source-provided update time (ETag / Last-Modified when
present), fetch time, scope, sha256, schema fingerprint, row count, status and code version in
`ops.load_manifest`. A 200 response with missing required columns or an empty dataset is a
`contract_failed` load and never replaces prior data.

## Sleeper (`api.sleeper.app/v1`, read-only, token-free)

| Endpoint | Partition | Raw table | Notes |
|---|---|---|---|
| `/league/{id}` | league | `sleeper_league` | chain followed via `previous_league_id` (2026 → 2025 → 2024; 2024 has none) |
| `/league/{id}/users`, `/rosters` | league | `sleeper_league_user`, `sleeper_roster` | roster = current/season-end state |
| `/league/{id}/matchups/{week}` | league, week | `sleeper_matchup` | completed season: weeks 1..`last_scored_leg`; live season: 1..`display_week`; future weeks return zero-point rows → `is_scored=false` |
| `/league/{id}/transactions/{round}` | league, week | `sleeper_transaction` | round = week (`leg`) |
| `/league/{id}/drafts`, `/draft/{id}/picks` | league / draft | `sleeper_draft`, `sleeper_draft_pick` | |
| `/league/{id}/traded_picks`, `/winners_bracket`, `/losers_bracket` | league | `sleeper_traded_pick`, `sleeper_bracket` | |
| `/players/nfl` (~5 MB) | all | `sleeper_player` | fetched at most every 20 h (plan: daily); otherwise replayed from archive |
| `/state/nfl` | all | `sleeper_state` | current week/season |

Sleeper sends no ETags; unchanged content is detected by sha256 against `ops.source_partition`.
IDs are stored as text (they exceed 2^53). Shapes were captured from the live league on
2026-09-25 and are mirrored by the synthetic fixture generator.

Observed on 2026-09-25: 10 teams, half-PPR (`rec` 0.5), 4-pt pass TD, two FLEX, K and DEF,
playoffs from week 15 with 4 teams, 2025 matchups contain `starters_points` and `players_points`,
starters use `"0"` for an empty slot.

## nflverse (`github.com/nflverse/nflverse-data/releases/download/…`)

| Dataset | File | Partition | Coverage used | Key | Required columns (contract) |
|---|---|---|---|---|---|
| player_stats_week | `stats_player/stats_player_week_{season}.parquet` | season | 2016–2026 | player_id, season, week (unique) | ids, season/week/type, game_id, team, passing/rushing/receiving/kicking core, fantasy_points* |
| team_stats_week | `stats_team/stats_team_week_{season}.parquet` | season | 2016–2026 | team, season, week | attempts, targets, carries, sacks_suffered, passing_air_yards … |
| rosters_weekly | `weekly_rosters/roster_weekly_{season}.parquet` | season | 2016–2026 | gsis_id, season, week (deduped downstream) | team, position, status, full_name, gsis_id |
| snap_counts | `snap_counts/snap_counts_{season}.parquet` | season | 2016–2026 | pfr_player_id, game_id | offense_snaps, offense_pct |
| schedules | `schedules/games.parquet` | all (filtered ≥ 2016) | 2016–2026 | game_id | teams, scores, gameday, gametime |
| players | `players/players.parquet` | all | — | gsis_id | pfr_id, esb_id, position, latest_team |
| teams | `teams/teams_colors_logos.parquet` | all | — | team_abbr | |
| ff_playerids | `raw.githubusercontent.com/dynastyprocess/data/master/files/db_playerids.csv` | all | — | — | gsis_id, sleeper_id, pfr_id, name, position |

Observed drift handled automatically: `roster_weekly` `height` is integer in 2025/2026 and float
in earlier seasons (column widened); `stats_player_week` has 22–218 rows per season with a NULL
`player_id` (team-level special-teams lines) — excluded in staging and counted in the quarantine.
Kickers are `PK` in ff_playerids but `K` in Sleeper/nflverse (handled where it matters).
nflverse `fantasy_points` columns exclude kicking, so League Lab's own scoring is the one to use
for kickers.

Timing (plan §7): stats files update through the week; the current-season partition is re-fetched
every refresh and replaced only when its checksum changes. Historical seasons are re-checked with
`league-lab refresh --full` (monthly audit).

## Added 2026-09-26 (Manager's Edge)

| Dataset | File | Partition | Coverage | Key | Notes |
|---|---|---|---|---|---|
| ff_opportunity | `github.com/ffverse/ffopportunity/releases/download/latest-data/ep_weekly_{season}.parquet` | season | 2016–2026 | (player_id, season, week); team rows have NULL player_id and are dropped in staging | `season` ships as text and `week` as float → cast to integers at load; expected stats used, the model's own fantasy-point columns kept for reference only |
| injuries | `injuries/injuries_{season}.parquet` | season | 2016–2026 | (gsis_id, season, week) — 1–2 duplicates per season upstream, deduped in staging (most severe wins) | report_status (Out/Doubtful/Questionable) + practice status |
| depth_charts | `depth_charts/depth_charts_{season}.parquet` | season | **2025+ only** (~550k snapshot rows per season) | snapshot `dt` × team × slot | file has no `season` column; the loader adds it. Only the latest snapshot per team is modelled |
| ngs_receiving / ngs_rushing / ngs_passing | `nextgen_stats/ngs_{type}.parquet` | single file each | 2016–2026 | (player_gsis_id, season, week, season_type); week 0 = season aggregate | |
| pfr_advstats_def / rec / pass / rush | `pfr_advstats/advstats_week_{type}_{season}.parquet` | season | **2018+** | (pfr_player_id, game_id) | PFR ids → gsis via `int_pfr_gsis_map` (only unambiguous PFR ids) |

## Open-Meteo — game-day weather (plan D3, Wave D, 2026-10-01)

nflverse's schedules carry `temp` / `wind` only after a game is played (1,814 of 2,145 open-air games
2016–2025 have them; 2022: 107 of 198) and no precipitation, so the board needs a forecast and
training a history with one definition. `league-lab ingest weather` (`src/league_lab/ingest/weather.py`)
fetches both from Open-Meteo by stadium latitude / longitude, free and without a key.

| Endpoint | Request | Partition (manifest `open_meteo`) | Archive file | Raw rows |
|---|---|---|---|---|
| `archive-api.open-meteo.com/v1/archive` (ERA5 / ERA5-Land reanalysis, ~5 days behind real time) | one per **stadium × season**: `start_date` = the first game, `end_date` = the last one the archive can answer (kickoff + 3 h + 5 days before now) | `archive` · `<season>:<stadium_id>` | `data/raw/open_meteo/archive/<season>/<stadium_id>.json.gz` | `raw.nfl_weather` source `archive`, one per game (replaced when the stadium-season is re-fetched) |
| `api.open-meteo.com/v1/forecast` (16-day horizon) | one per **stadium** with an open-air game kicking off in the next 16 days, its game dates only; not again within 6 h | `forecast` · `<season>:<stadium_id>` (= every forecast file of that stadium-season) | `data/raw/open_meteo/forecast/<season>/<stadium_id>/<YYYYmmddTHHMMZ>.json.gz` | source `forecast`, one per game **per fetch**, never deleted (`forecast_hours_ahead` = kickoff − fetch) |

Parameters (both): `hourly=temperature_2m,precipitation,rain,snowfall,weather_code,wind_speed_10m,wind_gusts_10m`
(+ `precipitation_probability` for the forecast), `temperature_unit=fahrenheit`, `wind_speed_unit=mph`,
`precipitation_unit=inch`, `timezone=GMT` (times are UTC; kickoff = nflverse `gameday` + `gametime` in
US Eastern, which is how nflverse records every game, London included). Only games open to the
weather are requested: an outdoor venue, or a retractable roof that is open or not yet decided. Fixed
domes and closed roofs never cost a call.

**Which games / what changes.** Completed seasons cost nothing after their first fetch (the archived
file covers every game; `--force` re-fetches). In season, a stadium's archive file is re-fetched about
once per home game (when a played game falls outside it), and each forecast run is one call per
stadium with an open-air game in the next 16 days (23 on 2026-10-01, for 26 games). Backfill
2016–2026 as planned on 2026-10-01: **280 archive calls for 1,991 games** (18–30 stadium-seasons a
season, the international one-offs included); Open-Meteo counts a call as roughly `variables / 10 ×
days / 14`, so the backfill weighs ~1,300 calls, well under the free tier's 10,000 a day; live calls are
spaced 1.5 s apart (its 600-a-minute ceiling), ~8 minutes.

**Stadium reference** (`src/league_lab/ingest/reference/stadiums.csv` → `raw.nfl_stadiums`, reloaded by
`db migrate` when it changes): every venue of a game 2016–2026 — the 47 nflverse `stadium_id`s plus
Croke Park (`DUB00`) and Berlin's Olympiastadion (`BER00`), which nflverse does not have — with latitude,
longitude, IANA time zone, roof type (outdoors / dome / retractable), tenants (team and seasons) and
the names nflverse has used. **Coordinates**: each stadium's Wikipedia infobox (GeoHack) coordinates,
transcribed to 4 decimals (Open-Meteo's grid is ~11 km for ERA5-Land, ~25 km for ERA5, so a
transcription error well under a kilometre does not change the answer); they could not be checked
against a live map from the development sandbox — `tests/test_weather.py` checks each against its time
zone and hemisphere. The CSV is the authority on fixed roofs: nflverse records the MCG, Stade de France
and the Munich stadium as `dome` (they are open-air). `stadium_game_venues.csv` (→
`raw.nfl_stadium_game_venues`) corrects the seven 2025 international games nflverse records at the home
team's stadium (São Paulo, Dublin, London ×3, Berlin, Madrid); a stadium name that belongs to another
venue resolves there (2026_05_PHI_JAX: `JAX00` "Tottenham Hotspur Stadium" → `LON02`).

**Not verified yet** (the sandbox cannot reach open-meteo.com): the loader is tested on fixtures
hand-built from the documented response format (`tests/fixtures/open_meteo/`); the first real run
(`league-lab ingest weather --forecast` on the Mac or in Actions) is the first contact with the live API.

## Deferred sources (Phase 2)

| Dataset | File | From | Notes |
|---|---|---|---|
| play-by-play | `pbp/play_by_play_{season}.parquet` | 1999 (use 2016+) | ~370 columns; keep a configurable subset |
| FTN charting | `ftn_charting/ftn_charting_{season}.parquet` | 2022 | CC-BY-SA 4.0, attribute **FTN Data via nflverse**; strict first-read coding from 2023; ~48 h charting lag |
| participation | `pbp_participation/pbp_participation_{season}.parquet` | 2016 | from 2023 published after the postseason, not during the season |
| routes | — | — | no verified free source |

## Licensing

* nflverse data: see the nflverse-data release terms; attribution "nflverse" in exports.
* FTN charting subset: CC-BY-SA 4.0, attribution "FTN Data via nflverse".
* dynastyprocess crosswalk: MIT-licensed repository.
* Open-Meteo weather (plan D3): data under CC BY 4.0 — attribute "Weather data by Open-Meteo.com"
  (with a link) wherever weather is shown or exported; ERA5 history is Copernicus Climate Change Service
  data (Hersbach et al., 2020; "Contains modified Copernicus Climate Change Service information").
  The free API is for non-commercial use (under 10,000 calls a day); a commercial League Lab needs an
  Open-Meteo subscription.
* Sleeper API: public and read-only; league content belongs to the league. A private repository
  does not grant redistribution rights — review before any public data distribution (Phase 4).
