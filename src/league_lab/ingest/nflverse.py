"""nflverse ingestion: release Parquet/CSV files -> ``data/raw/nflverse`` archive -> ``raw.nfl_*``.

Datasets (plan §4, trimmed MVP1):
    player_stats_week   game-level passing/rushing/receiving/kicking per player   (by season)
    team_stats_week     team totals per game = opportunity denominators          (by season)
    rosters_weekly      historical team affiliation + status per player-week     (by season)
    snap_counts         offensive snaps / snap % (PFR ids)                       (by season)
    schedules           all games with kickoff, teams, scores                    (single file)
    players             nflverse player identity (gsis/pfr/esb ids)              (single file)
    teams               team abbreviations, names, colors                        (single file)
    ff_playerids        dynastyprocess crosswalk incl. sleeper_id <-> gsis_id    (single file)
    ff_opportunity      ffverse expected points / expected stats per player-week (by season)
    injuries            weekly injury reports (report + practice status)         (by season)
    depth_charts        team depth chart snapshots (many per season)             (by season, recent only)
    ngs_receiving/rushing/passing  Next Gen Stats per player-week (week 0 = season) (single files)
    pfr_advstats_def/rec/pass/rush PFR advanced stats per player-game, 2018+     (by season)
    pbp                 play-by-play (nflfastR), core column subset by default     (by season)
    pbp_participation   players on the field per play (NGS/FTN), 2016 -> last completed season
    ftn_charting        FTN play charting incl. read_thrown, 2022+                 (by season)

Each partition is downloaded with a conditional request (ETag), checksum-compared with the
last successful load, contract-checked (required columns, non-empty, key uniqueness), then
replaced in one transaction. Column DDL is derived from the file schema; new upstream
columns are added, never dropped.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field
from datetime import date

import polars as pl
import psycopg

from ..config import get_settings
from ..db import downcast_to_existing, ensure_table, pg_type_for, replace_partition
from ..http import FetchError, fetch_to_archive
from ..manifest import LoadRecord, get_partition_state, record_manifest, schema_fingerprint

log = logging.getLogger(__name__)
SOURCE = "nflverse"


def current_nfl_season(today: date | None = None) -> int:
    """NFL season year != calendar year: a season starting in Sept runs into the next calendar year."""
    today = today or date.today()
    return today.year if today.month >= 3 else today.year - 1


@dataclass(frozen=True)
class Dataset:
    name: str
    table: str
    path: str  # release path relative to nflverse base URL, may contain {season}
    partitioned: bool
    required: tuple[str, ...]
    key: tuple[str, ...] = ()  # enforced unique when non-empty
    min_season: int = 2016
    fmt: str = "parquet"
    url: str | None = None  # absolute URL/template override ("__settings__" = ff_playerids_url)
    season_filter: bool = False  # single-file dataset filtered to seasons >= settings.seasons_start
    extra_index: tuple[tuple[str, ...], ...] = field(default_factory=tuple)
    columns: tuple[str, ...] | None = None  # parquet column subset (missing columns tolerated); None = all
    season_lag: int = 0  # dataset is published this many seasons behind (participation: after the postseason)


# Play-by-play ships ~370 columns; this core subset (~190) drops running EPA/WPA totals, tackle /
# assist / return player name columns and kickoff/punt detail flags. The archived parquet keeps
# everything, and LEAGUE_LAB_PBP_COLUMNS=all loads every column (plan P2-01: subset configurable).
PBP_CORE_COLUMNS: tuple[str, ...] = (
    "play_id", "game_id", "old_game_id", "home_team", "away_team", "season_type", "week", "season", "posteam",
    "posteam_type", "defteam", "side_of_field", "yardline_100", "game_date", "quarter_seconds_remaining",
    "half_seconds_remaining", "game_seconds_remaining", "game_half", "quarter_end", "drive", "sp", "qtr", "down",
    "goal_to_go", "time", "yrdln", "ydstogo", "ydsnet", "desc", "play_type", "yards_gained", "shotgun", "no_huddle",
    "qb_dropback", "qb_kneel", "qb_spike", "qb_scramble", "pass_length", "pass_location", "air_yards",
    "yards_after_catch", "run_location", "run_gap", "field_goal_result", "kick_distance", "extra_point_result",
    "two_point_conv_result", "timeout", "timeout_team", "td_team", "td_player_name", "td_player_id",
    "posteam_timeouts_remaining", "defteam_timeouts_remaining", "total_home_score", "total_away_score",
    "posteam_score", "defteam_score", "score_differential", "posteam_score_post", "defteam_score_post",
    "score_differential_post", "ep", "epa", "air_epa", "yac_epa", "comp_air_epa", "comp_yac_epa", "wp", "def_wp",
    "home_wp", "away_wp", "wpa", "vegas_wp", "vegas_wpa", "vegas_home_wp", "first_down_rush", "first_down_pass",
    "first_down_penalty", "third_down_converted", "third_down_failed", "fourth_down_converted", "fourth_down_failed",
    "incomplete_pass", "interception", "fumble_forced", "fumble_not_forced", "fumble_out_of_bounds", "safety",
    "penalty", "tackled_for_loss", "fumble_lost", "qb_hit", "rush_attempt", "pass_attempt", "sack", "touchdown",
    "pass_touchdown", "rush_touchdown", "return_touchdown", "extra_point_attempt", "two_point_attempt",
    "field_goal_attempt", "kickoff_attempt", "punt_attempt", "fumble", "complete_pass", "lateral_reception",
    "lateral_rush", "passer_player_id", "passer_player_name", "passing_yards", "receiver_player_id",
    "receiver_player_name", "receiving_yards", "rusher_player_id", "rusher_player_name", "rushing_yards",
    "lateral_receiver_player_id", "lateral_receiver_player_name", "lateral_receiving_yards",
    "lateral_rusher_player_id", "lateral_rusher_player_name", "lateral_rushing_yards", "interception_player_id",
    "interception_player_name", "kicker_player_id", "kicker_player_name", "punter_player_id", "sack_player_id",
    "sack_player_name", "half_sack_1_player_id", "half_sack_2_player_id", "fumbled_1_player_id", "fumbled_1_team",
    "fumble_recovery_1_team", "fumble_recovery_1_player_id", "penalty_team", "penalty_player_id",
    "penalty_player_name", "penalty_yards", "penalty_type", "replay_or_challenge", "replay_or_challenge_result",
    "defensive_two_point_attempt", "defensive_two_point_conv", "cp", "cpoe", "series", "series_success",
    "series_result", "order_sequence", "start_time", "time_of_day", "stadium", "weather", "play_clock",
    "play_deleted", "play_type_nfl", "special_teams_play", "st_play_type", "end_clock_time", "end_yard_line",
    "fixed_drive", "fixed_drive_result", "drive_play_count", "drive_time_of_possession", "drive_first_downs",
    "drive_inside20", "drive_ended_with_score", "drive_start_transition", "drive_end_transition", "away_score",
    "home_score", "location", "result", "total", "spread_line", "total_line", "div_game", "roof", "surface", "temp",
    "wind", "aborted_play", "success", "passer", "rusher", "receiver", "pass", "rush", "first_down", "special",
    "play", "passer_id", "rusher_id", "receiver_id", "name", "id", "fantasy_player_name", "fantasy_player_id",
    "fantasy", "fantasy_id", "out_of_bounds", "home_opening_kickoff", "qb_epa", "xyac_epa", "xyac_mean_yardage",
    "xyac_median_yardage", "xyac_success", "xyac_fd", "xpass", "pass_oe",
)


DATASETS: dict[str, Dataset] = {
    "player_stats_week": Dataset(
        "player_stats_week", "nfl_player_stats_week", "stats_player/stats_player_week_{season}.parquet", True,
        required=("player_id", "player_display_name", "position", "season", "week", "season_type", "game_id", "team",
                  "opponent_team", "attempts", "completions", "passing_yards", "passing_tds", "carries", "rushing_yards",
                  "targets", "receptions", "receiving_yards", "receiving_air_yards", "fg_att", "fg_made", "pat_made",
                  "fantasy_points", "fantasy_points_ppr"),
        key=("player_id", "season", "week"),
    ),
    "team_stats_week": Dataset(
        "team_stats_week", "nfl_team_stats_week", "stats_team/stats_team_week_{season}.parquet", True,
        required=("team", "season", "week", "season_type", "game_id", "opponent_team", "attempts", "completions",
                  "passing_yards", "carries", "rushing_yards", "targets", "receptions", "sacks_suffered",
                  "passing_air_yards"),
        key=("team", "season", "week"),
    ),
    "rosters_weekly": Dataset(
        "rosters_weekly", "nfl_rosters_weekly", "weekly_rosters/roster_weekly_{season}.parquet", True,
        required=("season", "week", "game_type", "team", "position", "status", "full_name", "gsis_id"),
    ),
    "snap_counts": Dataset(
        "snap_counts", "nfl_snap_counts", "snap_counts/snap_counts_{season}.parquet", True,
        required=("game_id", "season", "game_type", "week", "player", "pfr_player_id", "position", "team",
                  "opponent", "offense_snaps", "offense_pct"),
        key=("pfr_player_id", "game_id"),
    ),
    "schedules": Dataset(
        "schedules", "nfl_schedules", "schedules/games.parquet", False,
        required=("game_id", "season", "game_type", "week", "gameday", "gametime", "away_team", "home_team",
                  "away_score", "home_score"),
        key=("game_id",), season_filter=True,
    ),
    "players": Dataset(
        "players", "nfl_players", "players/players.parquet", False,
        required=("gsis_id", "display_name", "position", "latest_team", "pfr_id", "esb_id"),
        key=("gsis_id",),
    ),
    "teams": Dataset(
        "teams", "nfl_teams", "teams/teams_colors_logos.parquet", False,
        required=("team_abbr", "team_name", "team_conf", "team_division"), key=("team_abbr",),
    ),
    "ff_playerids": Dataset(
        "ff_playerids", "nfl_ff_playerids", "db_playerids.csv", False,
        required=("gsis_id", "sleeper_id", "pfr_id", "name", "position", "team"), fmt="csv",
        url="__settings__",
    ),
    "ff_opportunity": Dataset(
        "ff_opportunity", "nfl_ff_opportunity", "ep_weekly_{season}.parquet", True,
        required=("season", "week", "game_id", "player_id", "full_name", "position", "posteam", "rec_attempt",
                  "rush_attempt", "pass_attempt", "receptions_exp", "rec_yards_gained_exp", "rec_touchdown_exp",
                  "rush_yards_gained_exp", "rush_touchdown_exp", "pass_yards_gained_exp", "pass_touchdown_exp",
                  "total_fantasy_points_exp"),
        url="https://github.com/ffverse/ffopportunity/releases/download/latest-data/ep_weekly_{season}.parquet",
    ),
    "injuries": Dataset(
        "injuries", "nfl_injuries", "injuries/injuries_{season}.parquet", True,
        required=("season", "week", "team", "gsis_id", "full_name", "position", "report_status", "practice_status"),
        # a handful of duplicate (gsis_id, week) rows exist upstream; deduplicated in staging
    ),
    "depth_charts": Dataset(
        "depth_charts", "nfl_depth_charts", "depth_charts/depth_charts_{season}.parquet", True,
        required=("dt", "team", "player_name", "gsis_id", "pos_abb", "pos_rank"),
        min_season=2025,  # ~550k snapshot rows per season; only recent seasons are useful (matchup context)
    ),
    "ngs_receiving": Dataset(
        "ngs_receiving", "nfl_ngs_receiving", "nextgen_stats/ngs_receiving.parquet", False,
        required=("season", "season_type", "week", "player_gsis_id", "avg_separation", "avg_cushion", "targets"),
        key=("player_gsis_id", "season", "week", "season_type"), season_filter=True,
    ),
    "ngs_rushing": Dataset(
        "ngs_rushing", "nfl_ngs_rushing", "nextgen_stats/ngs_rushing.parquet", False,
        required=("season", "season_type", "week", "player_gsis_id", "rush_yards_over_expected", "efficiency"),
        key=("player_gsis_id", "season", "week", "season_type"), season_filter=True,
    ),
    "ngs_passing": Dataset(
        "ngs_passing", "nfl_ngs_passing", "nextgen_stats/ngs_passing.parquet", False,
        required=("season", "season_type", "week", "player_gsis_id", "avg_time_to_throw", "aggressiveness"),
        key=("player_gsis_id", "season", "week", "season_type"), season_filter=True,
    ),
    "pfr_advstats_def": Dataset(
        "pfr_advstats_def", "nfl_pfr_advstats_def", "pfr_advstats/advstats_week_def_{season}.parquet", True,
        required=("game_id", "season", "week", "team", "opponent", "pfr_player_name", "pfr_player_id", "def_targets",
                  "def_completions_allowed", "def_yards_allowed", "def_passer_rating_allowed"),
        key=("pfr_player_id", "game_id"), min_season=2018,
    ),
    "pfr_advstats_rec": Dataset(
        "pfr_advstats_rec", "nfl_pfr_advstats_rec", "pfr_advstats/advstats_week_rec_{season}.parquet", True,
        required=("game_id", "season", "week", "team", "pfr_player_id", "receiving_drop", "receiving_broken_tackles"),
        key=("pfr_player_id", "game_id"), min_season=2018,
    ),
    "pfr_advstats_pass": Dataset(
        "pfr_advstats_pass", "nfl_pfr_advstats_pass", "pfr_advstats/advstats_week_pass_{season}.parquet", True,
        required=("game_id", "season", "week", "team", "pfr_player_id"),
        key=("pfr_player_id", "game_id"), min_season=2018,
    ),
    "pfr_advstats_rush": Dataset(
        "pfr_advstats_rush", "nfl_pfr_advstats_rush", "pfr_advstats/advstats_week_rush_{season}.parquet", True,
        required=("game_id", "season", "week", "team", "pfr_player_id"),
        key=("pfr_player_id", "game_id"), min_season=2018,
    ),
    "pbp": Dataset(
        "pbp", "nfl_pbp", "pbp/play_by_play_{season}.parquet", True,
        required=("game_id", "play_id", "season", "week", "season_type", "posteam", "defteam", "play_type", "desc",
                  "qb_dropback", "qb_scramble", "qb_kneel", "qb_spike", "pass_attempt", "rush_attempt", "sack",
                  "two_point_attempt", "passer_player_id", "receiver_player_id", "rusher_player_id",
                  "score_differential", "game_half", "down", "ydstogo", "air_yards", "complete_pass"),
        key=("game_id", "play_id"), columns=PBP_CORE_COLUMNS,
    ),
    "pbp_participation": Dataset(
        "pbp_participation", "nfl_pbp_participation", "pbp_participation/pbp_participation_{season}.parquet", True,
        required=("nflverse_game_id", "play_id", "possession_team", "offense_players", "defense_players", "n_offense"),
        key=("nflverse_game_id", "play_id"), season_lag=1,  # a season's file is published after its postseason
    ),
    "ftn_charting": Dataset(
        "ftn_charting", "nfl_ftn_charting", "ftn_charting/ftn_charting_{season}.parquet", True,
        required=("nflverse_game_id", "nflverse_play_id", "season", "week", "read_thrown", "is_throw_away", "is_drop",
                  "is_play_action", "is_screen_pass", "is_rpo", "is_motion"),
        key=("nflverse_game_id", "nflverse_play_id"), min_season=2022,
    ),
}
DEFAULT_DATASETS = tuple(DATASETS)


class ContractError(ValueError):
    pass


def _read_frame(ds: Dataset, content: bytes) -> pl.DataFrame:
    if ds.fmt == "csv":
        df = pl.read_csv(io.BytesIO(content), infer_schema_length=0, null_values=["NA", "", "NULL"])
    else:
        columns = None
        if ds.columns and get_settings().pbp_columns != "all":
            present = set(pl.read_parquet_schema(io.BytesIO(content)))
            columns = [c for c in ds.columns if c in present]  # upstream files drift between seasons
        df = pl.read_parquet(io.BytesIO(content), columns=columns)
    # Normalize a few exotic dtypes to what Postgres can hold, and make season/week/play ids integers
    # everywhere (ffopportunity ships season as text and week as float; pbp/participation ship play_id
    # as float in some seasons and int in others).
    casts = []
    for c, t in zip(df.columns, df.dtypes, strict=True):
        if isinstance(t, (pl.Struct, pl.Object)):
            casts.append(pl.col(c).cast(pl.Utf8))
        elif isinstance(t, pl.Datetime) and t.time_zone is None:
            casts.append(pl.col(c).dt.replace_time_zone("UTC"))
        elif c in ("season", "week", "play_id", "nflverse_play_id") and t not in (pl.Int32, pl.Int64, pl.Int16):
            casts.append(pl.col(c).cast(pl.Float64, strict=False).cast(pl.Int32).alias(c))
    if casts:
        df = df.with_columns(casts)
    return df


def check_contract(ds: Dataset, df: pl.DataFrame, partition_key: str) -> None:
    missing = [c for c in ds.required if c not in df.columns]
    if missing:
        raise ContractError(f"{ds.name} {partition_key}: missing required columns {missing}")
    if df.height == 0:
        raise ContractError(f"{ds.name} {partition_key}: empty dataset")
    if ds.key:
        dupes = df.select(list(ds.key)).drop_nulls().group_by(list(ds.key)).len().filter(pl.col("len") > 1).height
        if dupes:
            raise ContractError(f"{ds.name} {partition_key}: {dupes} duplicate keys on {ds.key}")


def _columns_for(df: pl.DataFrame) -> list[tuple[str, str]]:
    return [(c, pg_type_for(t)) for c, t in zip(df.columns, df.dtypes, strict=True)]


def load_dataset(
    conn: psycopg.Connection,
    ds: Dataset,
    season: int | None,
    *,
    offline: bool = False,
    force: bool = False,
) -> LoadRecord:
    s = get_settings()
    partition_key = str(season) if ds.partitioned else "all"
    if ds.url == "__settings__":
        url = s.ff_playerids_url
    elif ds.url:
        url = ds.url.format(season=season)
    else:
        url = f"{s.nflverse_base_url}/{ds.path.format(season=season)}"
    archive_name = ds.path.format(season=season).split("/")[-1]
    archive_path = s.raw_dir / "nflverse" / ds.name / archive_name
    rec = LoadRecord(source=SOURCE, dataset=ds.name, partition_key=partition_key, source_url=url)

    try:
        fetched = fetch_to_archive(url, archive_path, conditional=not force, offline=offline)
    except FetchError as exc:
        rec.status, rec.error = "failed", str(exc)
        record_manifest(conn, rec)
        conn.commit()
        log.warning("%s %s: %s", ds.name, partition_key, exc)
        return rec

    rec.fetched_at, rec.checksum_sha256 = fetched.fetched_at, fetched.checksum
    rec.source_etag, rec.source_last_modified, rec.file_path = fetched.etag, fetched.last_modified, str(fetched.path)
    prior = get_partition_state(conn, SOURCE, ds.name, partition_key)
    if prior and prior["checksum_sha256"] == fetched.checksum and not force:
        rec.status, rec.row_count = "skipped_unchanged", prior["row_count"]
        record_manifest(conn, rec)
        conn.commit()
        return rec

    try:
        df = _read_frame(ds, fetched.content)
        if ds.partitioned and "season" not in df.columns:
            df = df.with_columns(pl.lit(season, dtype=pl.Int32).alias("season"))  # e.g. depth chart snapshots
        if ds.season_filter and "season" in df.columns:
            df = df.filter(pl.col("season") >= s.seasons_start)
        check_contract(ds, df, partition_key)
        df = df.with_columns(pl.lit(fetched.fetched_at).alias("_fetched_at"))
        rec.schema_fingerprint = schema_fingerprint(df.drop("_fetched_at"))
        with conn.transaction():
            df = downcast_to_existing(conn, "raw", ds.table, df)
            ensure_table(conn, "raw", ds.table, _columns_for(df))
            where = {"season": season} if ds.partitioned else {}
            rec.row_count = replace_partition(conn, "raw", ds.table, df, where)
            record_manifest(conn, rec)
        conn.commit()
        log.info("%s %s: loaded %s rows", ds.name, partition_key, rec.row_count)
    except ContractError as exc:
        conn.rollback()
        rec.status, rec.error = "contract_failed", str(exc)
        record_manifest(conn, rec)
        conn.commit()
        log.error("%s", exc)
    except Exception as exc:
        conn.rollback()
        rec.status, rec.error = "failed", f"{type(exc).__name__}: {exc}"
        record_manifest(conn, rec)
        conn.commit()
        log.exception("load failed for %s %s", ds.name, partition_key)
    return rec


def ingest_nflverse(
    conn: psycopg.Connection,
    seasons: list[int] | None = None,
    datasets: list[str] | None = None,
    *,
    offline: bool = False,
    force: bool = False,
) -> list[LoadRecord]:
    s = get_settings()
    seasons = seasons or list(range(s.seasons_start, current_nfl_season() + 1))
    names = datasets or list(DEFAULT_DATASETS)
    results: list[LoadRecord] = []
    for name in names:
        ds = DATASETS[name]
        if ds.partitioned:
            for season in seasons:
                if season < ds.min_season or season > current_nfl_season() - ds.season_lag:
                    continue
                results.append(load_dataset(conn, ds, season, offline=offline, force=force))
        else:
            results.append(load_dataset(conn, ds, None, offline=offline, force=force))
    return results
