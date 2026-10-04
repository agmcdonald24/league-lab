"""The Stats Explorer (Wave I-I, II-3; the fifth review § 4 and § 10): every skill player's numbers over a window you
choose — the season, his last 3 / 5 games played, the last 3 / 5 calendar weeks, or a week range — with the column
catalogue that says what each number is, how it is aggregated and whether this app has it.

Rules (docs/METRICS.md § "The Stats Explorer", docs/DATA_INVENTORY.md):
* one source: ``analytics.fct_player_game`` (player x game; already on the hosted copy), aggregated here per request
  exactly as ``mart_player_season`` aggregates a season — counts summed over his game rows in the window, the team's
  denominators summed over the games he **played** in it, then divided (a test: the season window equals the mart);
* a share or rate over several games is **summed numerator / summed denominator**, never a mean of weekly
  percentages (a test). The one exception is snap share: nflverse publishes each game's snap share, not the team's
  snap total, so the window's snap share is the mean of his per-game shares over games with snap counts — the card's
  number, said so in its definition;
* points are this league's scoring (``research.league_games``: the league mart for a house league, priced on request
  otherwise); a per-game number divides by the games he played in the window;
* unknown is ``null`` (the screen shows —, the catalogue's ``reason`` on hover), never 0: a zero denominator, a season
  without participation (routes: nflverse publishes it after the season) or before FTN charting (2022) is null.
"""

from __future__ import annotations

import re
import time

import numpy as np
import pandas as pd

from .db import query

WINDOWS = ("season", "last3", "last5", "weeks")
BASES = ("games", "weeks")
STATS_LIMIT = 1000
TTL_S = 600
SKILL = ("QB", "RB", "WR", "TE")
BACKFIELD = ("RB", "FB")

# every column of fct_player_game the frame reads (all positions: the team's RB carries and inside-5 carries are
# summed over every player of the team in the game)
FCT_COLS = ["gsis_id", "game_id", "season", "season_type", "week", "team", "position", "player_name", "played", "snaps_known",
            "offense_snap_pct", "completions", "attempts", "passing_yards", "passing_tds", "passing_interceptions",
            "sacks_suffered", "passing_cpoe", "carries", "rushing_yards", "rushing_tds", "targets", "receptions",
            "receiving_yards", "receiving_tds", "receiving_air_yards", "receiving_yards_after_catch", "team_targets",
            "team_carries", "team_air_yards", "routes_proxy", "team_dropbacks_with_participation", "routes",
            "charted_targets", "first_read_targets", "team_first_read_targets", "team_charted_targets", "catchable_targets",
            "red_zone_targets", "red_zone_carries", "inside_5_carries", "team_red_zone_targets", "team_red_zone_carries",
            "scrambles", "dropbacks"]
FCT_SQL = f"""select {", ".join(FCT_COLS)} from analytics.fct_player_game
              where season = %s and season_type = %s and week between %s and %s"""

# counts summed over every game row of the player in the window (mart_player_season's sum(...))
SUMS = ["completions", "attempts", "passing_yards", "passing_tds", "passing_interceptions", "sacks_suffered", "carries",
        "rushing_yards", "rushing_tds", "targets", "receptions", "receiving_yards", "receiving_tds", "receiving_air_yards",
        "receiving_yards_after_catch", "routes_proxy", "routes", "charted_targets", "first_read_targets", "catchable_targets",
        "red_zone_targets", "red_zone_carries", "inside_5_carries", "scrambles", "dropbacks"]
# the team's denominators summed over the games he played (mart_player_season's `sum(...) filter (where played)`)
TEAM_SUMS = ["team_targets", "team_carries", "team_air_yards", "team_first_read_targets", "team_charted_targets",
             "team_red_zone_targets", "team_red_zone_carries", "team_rb_carries", "team_inside_5_carries"]


# ---------------------------------------------------------------------------------------------- the column catalogue
def _c(id_, label, short, kind, fmt, definition, numerator=None, denominator=None, aggregation=None, *, source,
       status, positions=SKILL, per_game=False, needs=None, reason=None) -> dict:
    return {"id": id_, "label": label, "short": short, "kind": kind, "format": fmt, "per_game": per_game,
            "definition": definition, "numerator": numerator, "denominator": denominator, "aggregation": aggregation,
            "source": source, "status": status, "positions": list(positions), "needs": needs, "reason": reason}


NFLV = "nflverse weekly player stats"
PBP = "nflverse play-by-play (fct_play)"
FTN = "FTN charting via nflverse (CC BY-SA 4.0)"
PART = "nflverse participation (bridge_play_participation)"
GAMES_AGG = "summed over his game rows in the window"
SHARE_AGG = "summed numerator / summed denominator over the games he played in the window (never a mean of weekly %)"
RATE_AGG = "summed numerator / summed denominator over the window"
PG_AGG = "the window's total / games he played in the window"
ROUTES_REASON = ("Routes: nflverse publishes participation after the season (2025 is the last season with it), so this "
                 "season is blank until then; no licensed routes feed is connected.")
CHART_REASON = "FTN charting starts in 2022 and covers only the games charted so far this season."

CATALOGUE: list[dict] = [
    _c("games", "Games played", "G", "games", "int",
       "Games he played in the window: a game counts when he had an offensive snap or a pass, carry, target or kick.",
       "games with an appearance", None, "count of games played", source=NFLV + " + snap counts", status="present",
       reason="no game in the window"),
    _c("points", "Fantasy points", "Pts", "count", "pts",
       "Fantasy points in this league's scoring.", "points in this league's scoring", None, GAMES_AGG,
       source="this league's scoring over " + NFLV, status="derived", per_game=True),
    _c("expected_points_per_game", "Expected fantasy points per game", "xPts/G", "rate", "pts",
       "What his targets and carries were worth on average (an opportunity-based estimate of past games, not next "
       "week's projection), in this league's scoring.", "expected points in the window", "games with an expected value",
       RATE_AGG, source="mart_player_expected_points (play-by-play opportunity model)", status="derived",
       reason="no expected value for his games (a kicker, or games before the opportunity model)"),
    # receiving
    _c("targets", "Targets", "Tgt", "count", "int", "Passes thrown to him.", "targets", None, GAMES_AGG,
       source=NFLV, status="present", per_game=True),
    _c("target_share", "Target share", "Tgt %", "share", "pct",
       "His targets / his team's targets in the games he played (a game he missed is not counted against him).",
       "targets", "team targets in the games he played", SHARE_AGG, source=NFLV + " (team totals: fct_team_game)",
       status="derived", reason="no team targets in his games"),
    _c("receptions", "Receptions", "Rec", "count", "int", "Catches.", "receptions", None, GAMES_AGG, source=NFLV,
       status="present", per_game=True),
    _c("receiving_yards", "Receiving yards", "Rec yds", "count", "int", "Receiving yards.", "receiving yards", None,
       GAMES_AGG, source=NFLV, status="present", per_game=True),
    _c("receiving_tds", "Receiving touchdowns", "Rec TD", "count", "int", "Receiving touchdowns.", "receiving TDs", None,
       GAMES_AGG, source=NFLV, status="present", per_game=True),
    _c("catch_rate", "Catch rate", "Catch %", "rate", "pct", "Receptions per target.", "receptions", "targets", RATE_AGG,
       source=NFLV, status="derived", reason="no targets"),
    _c("yards_per_target", "Receiving yards per target", "Yds/Tgt", "rate", "dec1", "Receiving yards per target.",
       "receiving yards", "targets", RATE_AGG, source=NFLV, status="derived", reason="no targets"),
    _c("air_yards_share", "Air-yard share", "Air %", "share", "pct",
       "His receiving air yards / his team's passing air yards in the games he played. Signed: can be negative or "
       "pass 100% when the team's total is small.", "receiving air yards", "team passing air yards in the games he played",
       SHARE_AGG, source=NFLV, status="derived", reason="his team's air yards in his games are zero"),
    _c("adot", "Average depth of target", "aDOT", "rate", "dec1",
       "How far past the line of scrimmage his targets travel, on average (air yards per target).",
       "receiving air yards", "targets", RATE_AGG, source=NFLV, status="derived", reason="no targets"),
    _c("yac_per_reception", "Yards after the catch per reception", "YAC/Rec", "rate", "dec1",
       "Yards after the catch per reception.", "yards after the catch", "receptions", RATE_AGG, source=NFLV,
       status="derived", reason="no receptions"),
    _c("red_zone_targets", "Red-zone targets", "RZ Tgt", "count", "int",
       "Targets with the ball at the opponent's 20 or closer (penalty-nullified plays and two-point tries excluded).",
       "red-zone targets", None, GAMES_AGG, source=PBP, status="derived", per_game=True),
    _c("red_zone_target_share", "Red-zone target share", "RZ Tgt %", "share", "pct",
       "His red-zone targets / his team's red-zone targets in the games he played (targets only, not carries).",
       "red-zone targets", "team red-zone targets in the games he played", SHARE_AGG, source=PBP, status="derived",
       reason="no team red-zone targets in his games"),
    _c("first_read_target_share", "First-read target share", "1st-read %", "share", "pct",
       "Of his team's charted targets thrown to the quarterback's first read, the share thrown to him — in the charted "
       "games he played. Built from charted targeted plays: it does not know every play's first-read assignment, only "
       "where the ball went when the first read was thrown to.",
       "his charted targets marked first read", "team charted first-read targets in the charted games he played",
       SHARE_AGG, source=FTN, status="derived", reason=CHART_REASON),
    _c("catchable_rate", "Catchable-target rate", "Catchable %", "rate", "pct",
       "Charted targets FTN marks catchable / his charted targets.", "catchable charted targets", "charted targets",
       RATE_AGG, source=FTN, status="derived", reason=CHART_REASON),
    _c("charted_targets", "Charted targets", "Charted", "count", "int",
       "His targets on plays FTN charted (the sample behind first-read share and catchable rate).", "charted targets",
       None, GAMES_AGG, source=FTN, status="derived", reason=CHART_REASON),
    _c("route_participation", "Route participation (estimate)", "Route %", "share", "pct",
       "Dropbacks he was on the field for (a receiver, back or tight end) / his team's dropbacks with participation, in "
       "the games he played. An estimate: being on the field for a dropback is not a route run (runs ~10–15% low).",
       "dropbacks on the field", "team dropbacks with participation in his games", SHARE_AGG, source=PART,
       status="derived", positions=("RB", "WR", "TE"), reason=ROUTES_REASON),
    _c("tprr_proxy", "Targets per route run (estimate)", "TPRR", "rate", "pct",
       "Targets / dropbacks he was on the field for, in games with participation.", "targets in games with participation",
       "dropbacks on the field", RATE_AGG, source=PART, status="derived", positions=("RB", "WR", "TE"),
       reason=ROUTES_REASON),
    _c("yprr_proxy", "Yards per route run (estimate)", "YPRR", "rate", "dec2",
       "Receiving yards / dropbacks he was on the field for, in games with participation.",
       "receiving yards in games with participation", "dropbacks on the field", RATE_AGG, source=PART, status="derived",
       positions=("RB", "WR", "TE"), reason=ROUTES_REASON),
    _c("routes", "Routes run", "Routes", "count", "int",
       "Routes run from a licensed charting feed. None is connected (FTN and PFF sell one; see docs/DATA_INVENTORY.md).",
       "routes run", None, GAMES_AGG, source="licensed routes feed (raw.routes_feed): not connected",
       status="unavailable", positions=("RB", "WR", "TE"), per_game=True,
       reason="No licensed routes feed is connected; nflverse participation is published after the season."),
    # rushing
    _c("carries", "Carries", "Car", "count", "int",
       "Rush attempts (nflverse carries: scrambles and kneel-downs included, two-point tries excluded).", "carries", None,
       GAMES_AGG, source=NFLV, status="present", per_game=True),
    _c("carry_share", "Carry share", "Car %", "share", "pct",
       "His carries / his team's carries in the games he played. The team's carries include quarterback scrambles and "
       "kneel-downs (nflverse carries); two-point tries are excluded. The card's Carry share is this number.",
       "carries", "team carries in the games he played", SHARE_AGG, source=NFLV + " (team totals: fct_team_game)",
       status="derived", reason="no team carries in his games"),
    _c("rb_carry_share", "Backfield carry share (RBs only)", "RB Car %", "share", "pct",
       "His carries / the carries of his team's running backs and fullbacks in the games he played — quarterback runs "
       "and kneel-downs and receivers' carries left out. Kept apart from Carry share.",
       "carries", "team RB + FB carries in the games he played", SHARE_AGG, source=NFLV, status="derived",
       positions=("RB",), reason="no running-back carries for his team in his games"),
    _c("rushing_yards", "Rushing yards", "Rush yds", "count", "int", "Rushing yards.", "rushing yards", None, GAMES_AGG,
       source=NFLV, status="present", per_game=True),
    _c("rushing_tds", "Rushing touchdowns", "Rush TD", "count", "int", "Rushing touchdowns.", "rushing TDs", None,
       GAMES_AGG, source=NFLV, status="present", per_game=True),
    _c("yards_per_carry", "Rushing yards per carry", "Yds/Car", "rate", "dec1", "Rushing yards per carry.",
       "rushing yards", "carries", RATE_AGG, source=NFLV, status="derived", reason="no carries"),
    _c("red_zone_carries", "Red-zone carries", "RZ Car", "count", "int",
       "Carries with the ball at the opponent's 20 or closer.", "red-zone carries", None, GAMES_AGG, source=PBP,
       status="derived", per_game=True),
    _c("red_zone_carry_share", "Red-zone carry share", "RZ Car %", "share", "pct",
       "His red-zone carries / his team's red-zone carries in the games he played (carries only, not targets).",
       "red-zone carries", "team red-zone carries in the games he played", SHARE_AGG, source=PBP, status="derived",
       reason="no team red-zone carries in his games"),
    _c("inside_5_carries", "Carries inside the 5", "In-5 Car", "count", "int",
       "Carries with the ball at the opponent's 5 or closer.", "carries inside the 5", None, GAMES_AGG, source=PBP,
       status="derived", per_game=True),
    _c("inside_5_carry_share", "Inside-the-5 carry share", "In-5 %", "share", "pct",
       "His carries inside the 5 / every carry inside the 5 by his team in the games he played.", "carries inside the 5",
       "team carries inside the 5 in the games he played", SHARE_AGG, source=PBP, status="derived",
       reason="his team had no carries inside the 5 in his games"),
    _c("red_zone_opportunities", "Red-zone opportunities", "RZ Opp", "count", "int",
       "Red-zone carries + red-zone targets (a count; no combined percentage).", "red-zone carries + red-zone targets",
       None, GAMES_AGG, source=PBP, status="derived", per_game=True),
    _c("ryoe_per_attempt", "Rushing yards over expected per attempt", "RYOE/Att", "rate", "dec2",
       "NFL Next Gen Stats' rushing yards over expected per attempt. Not ingested: nflverse publishes it (planned).",
       "rushing yards over expected", "carries (NGS-qualified)", "NGS's own season aggregate", source="NFL Next Gen "
       "Stats via nflverse: not ingested", status="planned", positions=("RB",),
       reason="Next Gen Stats are not ingested yet (planned)."),
    # passing
    _c("attempts", "Pass attempts", "Att", "count", "int", "Pass attempts (spikes included, sacks excluded).",
       "pass attempts", None, GAMES_AGG, source=NFLV, status="present", positions=("QB",), per_game=True),
    _c("completions", "Completions", "Cmp", "count", "int", "Completed passes.", "completions", None, GAMES_AGG,
       source=NFLV, status="present", positions=("QB",), per_game=True),
    _c("completion_rate", "Completion percentage", "Cmp %", "rate", "pct", "Completions per pass attempt.",
       "completions", "pass attempts", RATE_AGG, source=NFLV, status="derived", positions=("QB",),
       reason="no pass attempts"),
    _c("passing_yards", "Passing yards", "Pass yds", "count", "int", "Passing yards.", "passing yards", None,
       GAMES_AGG, source=NFLV, status="present", positions=("QB",), per_game=True),
    _c("yards_per_attempt", "Passing yards per attempt", "Yds/Att", "rate", "dec1", "Passing yards per attempt.",
       "passing yards", "pass attempts", RATE_AGG, source=NFLV, status="derived", positions=("QB",),
       reason="no pass attempts"),
    _c("passing_tds", "Passing touchdowns", "Pass TD", "count", "int", "Passing touchdowns.", "passing TDs", None,
       GAMES_AGG, source=NFLV, status="present", positions=("QB",), per_game=True),
    _c("passing_interceptions", "Interceptions", "Int", "count", "int", "Interceptions thrown.", "interceptions", None,
       GAMES_AGG, source=NFLV, status="present", positions=("QB",), per_game=True),
    _c("sacks_suffered", "Sacks taken", "Sk", "count", "int", "Times sacked.", "sacks", None, GAMES_AGG, source=NFLV,
       status="present", positions=("QB",), per_game=True),
    _c("dropbacks", "Dropbacks", "DB", "count", "int", "Pass attempts + sacks + scrambles (spikes excluded).",
       "dropbacks", None, GAMES_AGG, source=PBP, status="derived", positions=("QB",), per_game=True),
    _c("scrambles", "Scrambles", "Scr", "count", "int",
       "Dropbacks he turned into a run (nflfastR's scramble flag). Designed runs are not split out yet.", "scrambles",
       None, GAMES_AGG, source=PBP, status="derived", positions=("QB",), per_game=True),
    _c("cpoe", "Completion % over expected (play-by-play)", "CPOE", "rate", "dec1",
       "nflfastR's completion percentage over expected, in points of percentage. Aggregated as the mean of his per-game "
       "CPOE weighted by pass attempts (nflverse publishes the per-game mean, not the per-throw sum): close to the "
       "per-throw mean, not identical. Not Next Gen Stats' CPOE.", "per-game CPOE x pass attempts", "pass attempts",
       "attempt-weighted mean of per-game CPOE", source=NFLV + " (nflfastR CPOE)", status="derived", positions=("QB",),
       reason="no pass attempts with a CPOE"),
    _c("time_to_throw", "Time to throw", "TTT", "rate", "dec2",
       "NFL Next Gen Stats' average time to throw. Not ingested: nflverse publishes it (planned).", None, None,
       "NGS's own season aggregate", source="NFL Next Gen Stats via nflverse: not ingested", status="planned",
       positions=("QB",), reason="Next Gen Stats are not ingested yet (planned)."),
    _c("pressure_splits", "Pressure splits", "Press.", "rate", "pct",
       "Results under pressure. Needs a licensed charting feed (PFF / FTN pressure); not available.", None, None, None,
       source="licensed charting: not connected", status="unavailable", positions=("QB",),
       reason="Pressure charting is licensed data; none is connected."),
    # snaps
    _c("snap_share", "Snap share", "Snap %", "share", "pct",
       "His share of his team's offensive snaps. nflverse publishes each game's share (rounded to the percent), not the "
       "team's snap total, so several games are the mean of his per-game shares over games with snap counts (each game "
       "weighted equally) — the card's Snap share.", "per-game offensive snap %", "games with snap counts",
       "mean of per-game snap share over games with snap counts", source="nflverse snap counts", status="present",
       reason="no snap counts recorded for his games"),
]
CAT = {c["id"]: c for c in CATALOGUE}

PRESETS = [
    {"key": "wrte", "label": "WR / TE", "positions": ["WR", "TE"],
     "columns": ["games", "points", "targets", "target_share", "receiving_yards", "snap_share"],
     "extra": ["route_participation", "tprr_proxy", "yprr_proxy", "routes", "air_yards_share", "adot",
               "first_read_target_share", "red_zone_targets", "catchable_rate"],
     "sort": "target_share"},
    {"key": "rb", "label": "RB", "positions": ["RB"],
     "columns": ["games", "points", "carries", "carry_share", "targets", "snap_share", "rushing_yards", "receiving_yards"],
     "extra": ["rb_carry_share", "inside_5_carries", "inside_5_carry_share", "red_zone_opportunities", "route_participation",
               "tprr_proxy", "ryoe_per_attempt"],
     "sort": "carry_share"},
    {"key": "qb", "label": "QB", "positions": ["QB"],
     "columns": ["games", "points", "attempts", "passing_yards", "carries", "rushing_yards"],
     "extra": ["cpoe", "time_to_throw", "scrambles", "pressure_splits"],
     "sort": "points"},
]


def catalogue(season: int, frame: pd.DataFrame | None = None, through: int | None = None) -> list[dict]:
    """The catalogue with ``available`` for this season (routes estimates need participation; charting needs FTN)."""
    has_part = bool(frame is not None and not frame.empty and frame["routes_proxy"].notna().any())
    has_chart = bool(frame is not None and not frame.empty and (pd.to_numeric(frame["team_charted_targets"],
                                                                                errors="coerce") > 0).any())
    out = []
    for c in CATALOGUE:
        c = dict(c)
        if c["status"] in ("planned", "unavailable"):
            c["available"] = False
        elif c["source"] == PART:
            c["available"] = has_part
            if not has_part:
                c["reason"] = ROUTES_REASON
        elif c["source"] == FTN:
            c["available"] = has_chart and season >= 2022
            if c["available"] and frame is not None:
                weeks = sorted({int(w) for w in frame.loc[pd.to_numeric(frame["team_charted_targets"], errors="coerce") > 0,
                                                          "week"]})
                c["coverage"] = f"charted weeks {weeks[0]}–{weeks[-1]}" if weeks else None
        else:
            c["available"] = True
        out.append(c)
    return out


# ---------------------------------------------------------------------------------------------- arithmetic
def ratio(num: pd.Series, den: pd.Series, places: int = 4) -> pd.Series:
    """round(num / den, places) half away from zero (Postgres numeric's rounding) in exact integer arithmetic when both
    are whole numbers; NULL where the denominator is 0 or missing. Index-aligned."""
    n = pd.to_numeric(num, errors="coerce")
    d = pd.to_numeric(den, errors="coerce").reindex(n.index)
    ok = n.notna() & d.notna() & (d != 0)
    out = pd.Series(np.nan, index=n.index, dtype=float)
    if not ok.any():
        return out
    a, b = n[ok].to_numpy(dtype=float), d[ok].to_numpy(dtype=float)
    if np.all(a == np.round(a)) and np.all(b == np.round(b)) and np.all(np.abs(a) < 2**40):
        ai, bi = a.astype(np.int64), b.astype(np.int64)
        sign = np.sign(ai) * np.sign(bi)
        scale = 10 ** places
        q = (2 * np.abs(ai) * scale + np.abs(bi)) // (2 * np.abs(bi))
        out[ok] = sign * q / scale
    else:
        out[ok] = np.round(a / b, places)
    return out


def _cents(v) -> pd.Series:
    return (pd.to_numeric(v, errors="coerce") * 100).round()


_frames: dict[tuple, tuple[float, pd.DataFrame]] = {}


def season_rows(season: int, season_type: str) -> pd.DataFrame:
    """Every fct_player_game row of the season (all positions), + the team's RB carries and inside-5 carries per game.
    Cached 10 minutes (NFL-wide: the same for every league)."""
    key = (int(season), season_type)
    now = time.monotonic()
    hit = _frames.get(key)
    if hit is not None and hit[0] > now:
        return hit[1]
    lo, hi = (19, 22) if season_type == "POST" else (1, 18)
    df = query(FCT_SQL, (int(season), season_type, lo, hi))
    if not df.empty:
        for c in SUMS + ["team_targets", "team_carries", "team_air_yards", "team_first_read_targets", "team_charted_targets",
                         "team_red_zone_targets", "team_red_zone_carries", "team_dropbacks_with_participation",
                         "offense_snap_pct", "passing_cpoe", "week"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df["played"] = df["played"].fillna(False).astype(bool)
        df["snaps_known"] = df["snaps_known"].fillna(False).astype(bool)
        rb = df[df["position"].isin(BACKFIELD)].groupby(["team", "game_id"])["carries"].sum(min_count=1).rename("team_rb_carries")
        i5 = df.groupby(["team", "game_id"])["inside_5_carries"].sum(min_count=1).rename("team_inside_5_carries")
        df = df.merge(rb.reset_index(), on=["team", "game_id"], how="left").merge(i5.reset_index(), on=["team", "game_id"],
                                                                                     how="left")
    if len(_frames) > 8:
        _frames.clear()
    _frames[key] = (now + TTL_S, df)
    return df


def clear() -> None:
    _frames.clear()


def window_rows(rows: pd.DataFrame, window: str, basis: str, weeks: tuple[int, int] | None) -> tuple[pd.DataFrame, dict]:
    """The game rows inside the window and the window's description (label, weeks, basis, note)."""
    if rows.empty:
        return rows, {"key": window, "basis": basis, "weeks": None, "label": "No games yet", "through_week": None}
    through = int(rows["week"].max())
    first = int(rows["week"].min())
    if window == "season":
        return rows, {"key": "season", "basis": "weeks", "weeks": [first, through], "through_week": through,
                      "label": f"Season (weeks {first}–{through})" if first != through else f"Season (week {through})"}
    if window == "weeks":
        lo, hi = weeks or (first, through)
        out = rows[(rows["week"] >= lo) & (rows["week"] <= hi)]
        return out, {"key": "weeks", "basis": "weeks", "weeks": [lo, hi], "through_week": through,
                     "label": f"Weeks {lo}–{hi} (calendar weeks)" if lo != hi else f"Week {lo}"}
    n = 3 if window == "last3" else 5
    if basis == "weeks":
        lo = max(first, through - n + 1)
        out = rows[rows["week"] >= lo]
        return out, {"key": window, "basis": "weeks", "n": n, "weeks": [lo, through], "through_week": through,
                     "label": f"Last {n} calendar weeks (weeks {lo}–{through})",
                     "note": "Calendar weeks: a bye or a missed game leaves fewer games — the G column says how many."}
    # his last n games played: the weeks of his last n appearances, his rows in those weeks
    pl = rows[rows["played"]].sort_values(["gsis_id", "week"], ascending=[True, False])
    pl = pl[pl.groupby("gsis_id").cumcount() < n]
    out = rows.merge(pl[["gsis_id", "week"]].drop_duplicates(), on=["gsis_id", "week"], how="inner")
    return out, {"key": window, "basis": "games", "n": n, "weeks": [first, through], "through_week": through,
                 "label": f"Last {n} games played",
                 "note": f"His last {n} games played; a player with fewer games shows fewer — the G column says how many."}


def aggregate(g: pd.DataFrame) -> pd.DataFrame:
    """mart_player_season's arithmetic over any set of game rows: one row per player (no points)."""
    cols = ["gsis_id", "player_name", "position", "games", "first_week", "last_week"]
    if g.empty:
        return pd.DataFrame(columns=cols)
    g = g.copy()
    for c in TEAM_SUMS:
        g[c] = g[c].where(g["played"])
    g["_snap"] = g["offense_snap_pct"].where(g["snaps_known"])
    part = g["routes_proxy"].notna()
    g["team_dropbacks_with_participation"] = g["team_dropbacks_with_participation"].where(part & g["played"])
    g["targets_in_participation_games"] = g["targets"].where(part)
    g["receiving_yards_in_participation_games"] = g["receiving_yards"].where(part)
    g["games_with_participation"] = part
    g["charted_game"] = g["played"] & (g["team_charted_targets"] > 0)
    g["_cpoe_w"] = g["passing_cpoe"] * g["attempts"].where(g["passing_cpoe"].notna())
    g["_cpoe_n"] = g["attempts"].where(g["passing_cpoe"].notna())
    by = g.groupby("gsis_id", sort=False)
    # position = mode() within group (order by position): the most frequent, ties to the first alphabetically
    cnt = g.dropna(subset=["position"]).groupby(["gsis_id", "position"]).size().reset_index(name="n")
    pos = cnt.sort_values(["gsis_id", "n", "position"], ascending=[True, False, True]).drop_duplicates("gsis_id")
    out = pd.DataFrame({
        "player_name": by["player_name"].max(),
        "games": by["played"].sum().astype(int),
        "first_week": by["week"].min().astype(int),
        "last_week": by["week"].max().astype(int),
        **{c: by[c].sum(min_count=1) for c in SUMS},
        **{c: by[c].sum(min_count=1) for c in TEAM_SUMS},
        "team_dropbacks_with_participation": by["team_dropbacks_with_participation"].sum(min_count=1),
        "targets_in_participation_games": by["targets_in_participation_games"].sum(min_count=1),
        "receiving_yards_in_participation_games": by["receiving_yards_in_participation_games"].sum(min_count=1),
        "games_with_participation": by["games_with_participation"].sum().astype(int),
        "charted_games": by["charted_game"].sum().astype(int),
        "snap_games": by["_snap"].count().astype(int),
        "snap_share": by["_snap"].mean(),
        "_cpoe_w": by["_cpoe_w"].sum(min_count=1),
        "_cpoe_n": by["_cpoe_n"].sum(min_count=1),
    })
    out = out.join(pos.set_index("gsis_id")["position"])
    out["red_zone_opportunities"] = out["red_zone_carries"].add(out["red_zone_targets"], fill_value=0).where(
        out["red_zone_carries"].notna() | out["red_zone_targets"].notna())
    # shares: summed numerator / summed denominator (4 places, the mart's rounding)
    out["target_share"] = ratio(out["targets"], out["team_targets"])
    out["carry_share"] = ratio(out["carries"], out["team_carries"])
    out["rb_carry_share"] = ratio(out["carries"], out["team_rb_carries"])
    out["air_yards_share"] = ratio(out["receiving_air_yards"], out["team_air_yards"])
    out["red_zone_target_share"] = ratio(out["red_zone_targets"], out["team_red_zone_targets"])
    out["red_zone_carry_share"] = ratio(out["red_zone_carries"], out["team_red_zone_carries"])
    out["inside_5_carry_share"] = ratio(out["inside_5_carries"], out["team_inside_5_carries"])
    out["first_read_target_share"] = ratio(out["first_read_targets"], out["team_first_read_targets"])
    out["catchable_rate"] = ratio(out["catchable_targets"], out["charted_targets"])
    out["route_participation"] = ratio(out["routes_proxy"], out["team_dropbacks_with_participation"])
    out["tprr_proxy"] = ratio(out["targets_in_participation_games"], out["routes_proxy"])
    out["yprr_proxy"] = ratio(out["receiving_yards_in_participation_games"], out["routes_proxy"], 2)
    # rates
    out["catch_rate"] = ratio(out["receptions"], out["targets"])
    out["yards_per_target"] = ratio(out["receiving_yards"], out["targets"], 2)
    out["adot"] = ratio(out["receiving_air_yards"], out["targets"], 2)
    out["yac_per_reception"] = ratio(out["receiving_yards_after_catch"], out["receptions"], 2)
    out["yards_per_carry"] = ratio(out["rushing_yards"], out["carries"], 2)
    out["completion_rate"] = ratio(out["completions"], out["attempts"])
    out["yards_per_attempt"] = ratio(out["passing_yards"], out["attempts"], 2)
    out["cpoe"] = (out["_cpoe_w"] / out["_cpoe_n"].where(out["_cpoe_n"] > 0)).round(2)
    # the routes columns stay null without a licensed feed (routes = sum of nulls = null)
    for c in [c["id"] for c in CATALOGUE if c["per_game"] and c["id"] != "points"]:
        out[f"{c}_per_game"] = ratio(out[c], out["games"], 2)
    out = out.drop(columns=["_cpoe_w", "_cpoe_n"])
    return out.reset_index()


def points(league_rows: pd.DataFrame, g: pd.DataFrame) -> pd.DataFrame:
    """points, points_per_game (this league's scoring, cents-exact like mart_league_player_season), expected points per
    game over the same game rows."""
    keys = g[["gsis_id", "game_id"]].drop_duplicates()
    lp = keys.merge(league_rows[["gsis_id", "game_id", "points", "points_expected", "expected_known"]],
                    on=["gsis_id", "game_id"], how="left")
    lp = lp.merge(g[["gsis_id", "game_id", "played", "position"]].drop_duplicates(["gsis_id", "game_id"]),
                  on=["gsis_id", "game_id"], how="left")
    lp["played"] = lp["played"].fillna(False).astype(bool)
    lp["pc"] = _cents(lp["points"])
    lp["xc"] = _cents(lp["points_expected"]).where(lp["expected_known"].fillna(False).astype(bool) & lp["played"])
    by = lp.groupby("gsis_id")
    lp["_pp"] = lp["played"] & lp["pc"].notna()   # the mart's games: played with a points row
    out = pd.DataFrame({"_pc": by["pc"].sum(min_count=1), "games_p": lp.groupby("gsis_id")["_pp"].sum(),
                        "_xc": by["xc"].sum(min_count=1), "games_with_expected": by["xc"].count()})
    out["points"] = out["_pc"] / 100
    out["points_per_game"] = ratio(out["_pc"], out["games_p"] * 100, 2)
    out["expected_points_per_game"] = ratio(out["_xc"], out["games_with_expected"] * 100, 2)
    return out[["points", "points_per_game", "expected_points_per_game", "games_with_expected"]].reset_index()


def parse_weeks(weeks: str | None) -> tuple[int, int] | None:
    if not weeks:
        return None
    m = re.fullmatch(r"\s*(\d{1,2})\s*-\s*(\d{1,2})\s*", weeks)
    if not m:
        return None
    lo, hi = int(m.group(1)), int(m.group(2))
    return (lo, hi) if 1 <= lo <= hi <= 22 else None


def owner_filter(df: pd.DataFrame, who: str, team: int | None) -> pd.DataFrame:
    rid = df["rostered_by_roster_id"]
    if who == "mine":
        return df[rid.notna() & (rid == team)] if team is not None else df.iloc[0:0]
    if who == "fa":
        return df[rid.isna()]
    if who == "others":
        return df[rid.notna() & ((rid != team) if team is not None else True)]
    if who == "rostered":
        return df[rid.notna()]
    return df
