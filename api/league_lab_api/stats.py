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

import numpy as np
import pandas as pd
from league_lab import memo
from league_lab import research as LR  # IM-1: the rushing share is priced like the league's points

from .db import missing_relations, query

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
            "scrambles", "dropbacks",
            # ---- IM-1 (Wave I-M): EPA, first downs, deep / inside-10 looks, the rushing line's priced pieces
            "receiving_epa", "rushing_epa", "receiving_first_downs", "rushing_first_downs", "deep_targets",
            "inside_10_targets", "inside_10_carries", "rushing_2pt_conversions", "rush_tds_40p", "rush_tds_50p"]
# skill players + anyone with a carry (the team's inside-5 carries count every rusher; defenders' rows are not read)
FCT_SQL = f"""select {", ".join(FCT_COLS)} from analytics.fct_player_game
              where season = %s and season_type = %s and week between %s and %s
                and (position in ('QB', 'RB', 'WR', 'TE', 'FB') or coalesce(carries, 0) > 0)"""

# ---- IL-1 (Wave I-L): Next Gen Stats from analytics.mart_player_ngs_week, merged onto his game row of the same week
# (regular season only). NGS's weekly values are per-player aggregates: a window is the mean of the weekly values
# weighted by the denominator NGS states (never a mean of means); a week NGS did not publish (under its minimum) is
# not in the window's value, and a window with no published week is null with the reason.
NGS_REL = "mart_player_ngs_week"
NGS_SQL = """select gsis_id, week, ngs_pass_attempts, avg_time_to_throw, completion_percentage_above_expectation,
                    ngs_rush_attempts, rush_yards_over_expected_per_att, ngs_targets, ngs_receptions, avg_separation,
                    avg_yac_above_expectation,
                    aggressiveness, pass_avg_intended_air_yards, rush_efficiency, percent_attempts_gte_eight_defenders,
                    avg_time_to_los, avg_cushion, rec_avg_intended_air_yards
             from analytics.mart_player_ngs_week
             where season = %s and week between 1 and 18 and not is_season_aggregate"""
# column id -> (NGS's weekly value, the weight NGS states, the sample family)
NGS_METRICS = {
    "time_to_throw": ("avg_time_to_throw", "ngs_pass_attempts", "pass"),
    "ngs_cpoe": ("completion_percentage_above_expectation", "ngs_pass_attempts", "pass"),
    "ryoe_per_attempt": ("rush_yards_over_expected_per_att", "ngs_rush_attempts", "rush"),
    "separation": ("avg_separation", "ngs_targets", "rec"),
    "yac_over_expected": ("avg_yac_above_expectation", "ngs_receptions", "rec"),
    # ---- IM-1 (Wave I-M): the remaining NGS fields (each weighted by the denominator NGS states for it)
    "aggressiveness": ("aggressiveness", "ngs_pass_attempts", "pass"),
    "ngs_pass_intended_air_yards": ("pass_avg_intended_air_yards", "ngs_pass_attempts", "pass"),
    "rush_efficiency": ("rush_efficiency", "ngs_rush_attempts", "rush"),
    "stacked_box_rate": ("percent_attempts_gte_eight_defenders", "ngs_rush_attempts", "rush"),
    "time_to_los": ("avg_time_to_los", "ngs_rush_attempts", "rush"),
    "cushion": ("avg_cushion", "ngs_targets", "rec"),
    "ngs_intended_air_yards": ("rec_avg_intended_air_yards", "ngs_targets", "rec"),
}
NGS_SCALE = {"aggressiveness": 0.01, "stacked_box_rate": 0.01}   # IM-1: NGS states these in percent; we keep fractions
NGS_VALUES = sorted({v for v, _, _ in NGS_METRICS.values()})
NGS_WEIGHTS = ["ngs_pass_attempts", "ngs_rush_attempts", "ngs_targets", "ngs_receptions"]
NGS_FIRST = {"ryoe_per_attempt": 2018}        # NGS publishes rushing yards over expected from 2018
# ---- end IL-1

# ---- IM-1 (Wave I-M): analytics.mart_player_game_advanced (play-by-play efficiency + PFR's weekly advanced stats),
# merged onto his game row (gsis_id + game_id). Numerators only; a PFR count is divided only by the denominator of
# the games PFR covered (has_pfr_*), so a game PFR has no row for is out of both — never a 0.
ADV_REL = "mart_player_game_advanced"
ADV_PBP = ["target_successes", "carry_successes", "scramble_yards", "dropback_successes", "dropback_epa",
           "team_deep_targets"]
ADV_PFR = ["pfr_drops", "pfr_carries", "pfr_rush_yards_before_contact", "pfr_rush_yards_after_contact",
           "pfr_broken_tackles", "pfr_bad_throws", "pfr_times_pressured"]   # the mart has more; the frame reads these
# the PFR family behind each PFR column: which file's row must exist for his game to count
PFR_FAMILY = {"drops": "rec", "drop_rate": "rec", "broken_tackles": "touch", "broken_tackle_rate": "touch",
              "yards_before_contact_per_carry": "rush", "yards_after_contact_per_carry": "rush",
              "bad_throw_rate": "pass", "times_pressured": "pass", "pressure_rate": "pass"}
ADV_FLAGS = ["has_pfr_rec", "has_pfr_rush", "has_pfr_pass"]
ADV_SQL = f"""select gsis_id, game_id, {", ".join(ADV_PBP + ADV_PFR + ADV_FLAGS)}
             from analytics.mart_player_game_advanced where season = %s and season_type = %s"""
PFR_FIRST = 2018                               # nflverse publishes PFR's advanced stats from 2018
POINT_COLS = {"points", "points_over_expected"}   # their per-game twins come from points(), not aggregate()
NO_FIELD = {"pressure_splits", "rec_yards_after_contact", "on_target_rate"}   # unavailable: no row field at all
RUSH_LINE = ["rushing_yards", "rushing_tds", "rushing_2pt_conversions", "rush_tds_40p", "rush_tds_50p"]
# ---- end IM-1

# counts summed over every game row of the player in the window (mart_player_season's sum(...))
SUMS = ["completions", "attempts", "passing_yards", "passing_tds", "passing_interceptions", "sacks_suffered", "carries",
        "rushing_yards", "rushing_tds", "targets", "receptions", "receiving_yards", "receiving_tds", "receiving_air_yards",
        "receiving_yards_after_catch", "routes_proxy", "routes", "charted_targets", "first_read_targets", "catchable_targets",
        "red_zone_targets", "red_zone_carries", "inside_5_carries", "scrambles", "dropbacks",
        # ---- IM-1
        "receiving_epa", "rushing_epa", "receiving_first_downs", "rushing_first_downs", "deep_targets",
        "inside_10_targets", "inside_10_carries", "target_successes", "carry_successes", "scramble_yards",
        "dropback_successes", "dropback_epa", *ADV_PFR]
# the team's denominators summed over the games he played (mart_player_season's `sum(...) filter (where played)`)
TEAM_SUMS = ["team_targets", "team_carries", "team_air_yards", "team_first_read_targets", "team_charted_targets",
             "team_red_zone_targets", "team_red_zone_carries", "team_rb_carries", "team_inside_5_carries",
             "team_deep_targets"]                                                                  # IM-1: + deep


# ---------------------------------------------------------------------------------------------- the column catalogue
def _c(id_, label, short, kind, fmt, definition, numerator=None, denominator=None, aggregation=None, *, source,
       status, positions=SKILL, per_game=False, needs=None, reason=None, minimum=None) -> dict:
    out = {"id": id_, "label": label, "short": short, "kind": kind, "format": fmt, "per_game": per_game,
           "definition": definition, "numerator": numerator, "denominator": denominator, "aggregation": aggregation,
           "source": source, "status": status, "positions": list(positions), "needs": needs, "reason": reason}
    if minimum:                                    # ---- IM-1: the sample below which the screen greys a rate
        out["minimum"] = {"field": minimum[0], "n": minimum[1]}
    return out


NFLV = "nflverse weekly player stats"
RECV = ("RB", "WR", "TE")          # IM-1: receiving columns apply to the positions that run routes
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
# ---- IL-1: Next Gen Stats (mart_player_ngs_week): the source, the qualification words, the reasons for a dash
NGS = "NFL Next Gen Stats via nflverse (mart_player_ngs_week)"
NGS_AGG = ("mean of NGS's weekly values weighted by the denominator NGS states, over his weeks in the window that NGS "
           "published (never a mean of means)")
NGS_QUAL = {"pass": "15+ pass attempts", "rush": "10+ carries, running backs only",
            "rec": "5+ targets, receivers and tight ends only"}
NGS_REASON = ("No Next Gen Stats week in this window: NGS publishes a week only when he clears its minimum ({q}), so "
              "this is unknown, not zero.")
NGS_OFF = "Next Gen Stats here cover the regular season, 2016 onward; none for this selection."
NGS_NOT_BUILT = "Next Gen Stats arrive with the nightly update; they are not on this copy yet."
# ---- end IL-1
# ---- IM-1 (Wave I-M): the advanced mart's sources and reasons
ADV_SRC = "nflverse play-by-play (fct_play, via mart_player_game_advanced)"
PFR = "Pro Football Reference advanced stats, weekly, via nflverse (mart_player_game_advanced)"
ADV_REASON = "no dropback turned into a run"
PFR_REASON = ("Pro Football Reference has no row for his games in this window (it lists a player once he has a target, "
              "carry or pass), so this is unknown, not zero.")
PFR_OFF = "Pro Football Reference's advanced stats start in 2018; none for this selection."
ADV_NOT_BUILT = "These columns arrive with the nightly update; they are not on this copy yet."
# ---- end IM-1

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
       source=NFLV, status="present", per_game=True, positions=RECV),
    _c("target_share", "Target share", "Tgt %", "share", "pct",
       "His targets / his team's targets in the games he played (a game he missed is not counted against him).",
       "targets", "team targets in the games he played", SHARE_AGG, source=NFLV + " (team totals: fct_team_game)",
       status="derived", reason="no team targets in his games", positions=RECV),
    _c("receptions", "Receptions", "Rec", "count", "int", "Catches.", "receptions", None, GAMES_AGG, source=NFLV,
       status="present", per_game=True, positions=RECV),
    _c("receiving_yards", "Receiving yards", "Rec yds", "count", "int", "Receiving yards.", "receiving yards", None,
       GAMES_AGG, source=NFLV, status="present", per_game=True, positions=RECV),
    _c("receiving_tds", "Receiving touchdowns", "Rec TD", "count", "int", "Receiving touchdowns.", "receiving TDs", None,
       GAMES_AGG, source=NFLV, status="present", per_game=True, positions=RECV),
    _c("catch_rate", "Catch rate", "Catch %", "rate", "pct", "Receptions per target.", "receptions", "targets", RATE_AGG,
       source=NFLV, status="derived", reason="no targets", positions=RECV),
    _c("yards_per_target", "Receiving yards per target", "Yds/Tgt", "rate", "dec1", "Receiving yards per target.",
       "receiving yards", "targets", RATE_AGG, source=NFLV, status="derived", reason="no targets", positions=RECV),
    _c("air_yards_share", "Air-yard share", "Air %", "share", "pct",
       "His receiving air yards / his team's passing air yards in the games he played. Signed: can be negative or "
       "pass 100% when the team's total is small.", "receiving air yards", "team passing air yards in the games he played",
       SHARE_AGG, source=NFLV, status="derived", reason="his team's air yards in his games are zero", positions=RECV),
    _c("adot", "Average depth of target", "aDOT", "rate", "dec1",
       "How far past the line of scrimmage his targets travel, on average (air yards per target).",
       "receiving air yards", "targets", RATE_AGG, source=NFLV, status="derived", reason="no targets", positions=RECV),
    _c("yac_per_reception", "Yards after the catch per reception", "YAC/Rec", "rate", "dec1",
       "Yards after the catch per reception.", "yards after the catch", "receptions", RATE_AGG, source=NFLV,
       status="derived", reason="no receptions", positions=RECV),
    _c("red_zone_targets", "Red-zone targets", "RZ Tgt", "count", "int",
       "Targets with the ball at the opponent's 20 or closer (penalty-nullified plays and two-point tries excluded).",
       "red-zone targets", None, GAMES_AGG, source=PBP, status="derived", per_game=True, positions=RECV),
    _c("red_zone_target_share", "Red-zone target share", "RZ Tgt %", "share", "pct",
       "His red-zone targets / his team's red-zone targets in the games he played (targets only, not carries).",
       "red-zone targets", "team red-zone targets in the games he played", SHARE_AGG, source=PBP, status="derived",
       reason="no team red-zone targets in his games", positions=RECV),
    _c("first_read_target_share", "First-read target share", "1st-read %", "share", "pct",
       "Of his team's charted targets thrown to the quarterback's first read, the share thrown to him — in the charted "
       "games he played. Built from charted targeted plays: it does not know every play's first-read assignment, only "
       "where the ball went when the first read was thrown to.",
       "his charted targets marked first read", "team charted first-read targets in the charted games he played",
       SHARE_AGG, source=FTN, status="derived", reason=CHART_REASON, positions=RECV),
    _c("catchable_rate", "Catchable-target rate", "Catchable %", "rate", "pct",
       "Charted targets FTN marks catchable / his charted targets.", "catchable charted targets", "charted targets",
       RATE_AGG, source=FTN, status="derived", reason=CHART_REASON, positions=RECV),
    _c("charted_targets", "Charted targets", "Charted", "count", "int",
       "His targets on plays FTN charted (the sample behind first-read share and catchable rate).", "charted targets",
       None, GAMES_AGG, source=FTN, status="derived", reason=CHART_REASON, positions=RECV),
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
    # ---- IL-1: NFL Next Gen Stats, receiving
    _c("separation", "Average separation (yards)", "Sep", "rate", "dec1",
       "NFL Next Gen Stats' average distance, in yards, between him and the nearest defender when the pass arrives (a "
       "catch or an incompletion), per target. A context number, not a talent score. NGS publishes a week only for a "
       "receiver or tight end with 5+ targets; over several weeks it is the mean of his weekly values weighted by NGS's targets — never a mean "
       "of means.", "weekly separation x NGS targets", "NGS targets in his qualifying weeks", NGS_AGG, source=NGS,
       status="derived", positions=("WR", "TE"), reason=NGS_REASON.format(q=NGS_QUAL["rec"])),
    _c("yac_over_expected", "Yards after the catch over expected per reception", "YACOE", "rate", "dec1",
       "NFL Next Gen Stats' yards after the catch minus what its tracking model expected at the catch, per reception. "
       "NGS publishes a week only for a receiver or tight end with 5+ targets; over several weeks it is the mean of "
       "his weekly values weighted by NGS's receptions — never a mean of means.", "weekly YAC over expected x NGS receptions",
       "NGS receptions in his qualifying weeks", NGS_AGG, source=NGS, status="derived", positions=("WR", "TE"),
       reason=NGS_REASON.format(q=NGS_QUAL["rec"])),
    # ---- end IL-1
    _c("routes", "Routes run", "Routes", "count", "int",
       "Routes run from a licensed charting feed. None is connected (FTN and PFF sell one; see docs/DATA_INVENTORY.md).",
       "routes run", None, GAMES_AGG, source="licensed routes feed (routes_feed): not connected",
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
    # ---- IL-1: NFL Next Gen Stats (was planned: staging only)
    _c("ryoe_per_attempt", "Rushing yards over expected per carry", "RYOE/Car", "rate", "dec2",
       "NFL Next Gen Stats' rushing yards over expected per carry: his yards minus what NGS's tracking model expected "
       "from the blockers and defenders around him at the handoff. A context number, not a talent score. NGS publishes "
       "a week only for a running back with 10+ carries (from 2018); over several weeks it is the mean of his weekly values "
       "weighted by NGS's carries — never a mean of means.",
       "weekly RYOE per carry x NGS carries", "NGS carries in his qualifying weeks", NGS_AGG, source=NGS,
       status="derived", positions=("RB",), reason=NGS_REASON.format(q=NGS_QUAL["rush"])),
    # ---- end IL-1
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
    # ---- IL-1: NFL Next Gen Stats (time to throw was planned: staging only)
    _c("time_to_throw", "Time to throw (seconds)", "TTT", "rate", "dec2",
       "NFL Next Gen Stats' average time from the snap to his throw, in seconds. NGS publishes a week only when he has "
       "15+ pass attempts; over several weeks it is the mean of his weekly values weighted by NGS's pass attempts — "
       "never a mean of means.", "weekly time to throw x NGS pass attempts", "NGS pass attempts in his qualifying weeks",
       NGS_AGG, source=NGS, status="derived", positions=("QB",), reason=NGS_REASON.format(q=NGS_QUAL["pass"])),
    _c("ngs_cpoe", "Completion % over expected (Next Gen Stats)", "CPOE (NGS)", "rate", "dec1",
       "NFL Next Gen Stats' completion percentage over expected, in points of percentage: NGS's tracking model sets "
       "each throw's expected completion (separation, depth, pressure). Not the play-by-play CPOE beside it. NGS "
       "publishes a week only when he has 15+ pass attempts; over several weeks it is the mean of his weekly values "
       "weighted by NGS's pass attempts — never a mean of means.",
       "weekly CPOE x NGS pass attempts", "NGS pass attempts in his qualifying weeks", NGS_AGG, source=NGS,
       status="derived", positions=("QB",), reason=NGS_REASON.format(q=NGS_QUAL["pass"])),
    # ---- end IL-1
    _c("pressure_splits", "Pressure splits", "Press.", "rate", "pct",
       "Results under pressure. Needs a licensed charting feed (PFF / FTN pressure); not available.", None, None, None,
       source="licensed charting: not connected", status="unavailable", positions=("QB",),
       reason="Results under pressure need play-by-play pressure charting, which is licensed data; none is connected. "
              "How often he is pressured is in Pressured per dropback (Pro Football Reference)."),
    # snaps
    _c("snap_share", "Snap share", "Snap %", "share", "pct",
       "His share of his team's offensive snaps. nflverse publishes each game's share (rounded to the percent), not the "
       "team's snap total, so several games are the mean of his per-game shares over games with snap counts (each game "
       "weighted equally) — the card's Snap share.", "per-game offensive snap %", "games with snap counts",
       "mean of per-game snap share over games with snap counts", source="nflverse snap counts", status="present",
       reason="no snap counts recorded for his games"),
    # ---- IM-1 (Wave I-M): more metrics, every one with its numerator, denominator, aggregation and reason
    # receiving / rushing / passing lines
    _c("yards_per_reception", "Receiving yards per reception", "Yds/Rec", "rate", "dec1",
       "Receiving yards per catch.", "receiving yards", "receptions", RATE_AGG, source=NFLV, status="derived",
       positions=RECV, reason="no receptions", minimum=("receptions", 10)),
    _c("receiving_first_downs", "Receiving first downs", "Rec 1D", "count", "int",
       "Catches that gained a first down (touchdowns included, as nflverse counts them).", "receiving first downs",
       None, GAMES_AGG, source=NFLV, status="present", positions=RECV, per_game=True),
    _c("rushing_first_downs", "Rushing first downs", "Rush 1D", "count", "int",
       "Carries that gained a first down (touchdowns included).", "rushing first downs", None, GAMES_AGG, source=NFLV,
       status="present", per_game=True),
    _c("yards_per_touch", "Yards per touch", "Yds/Tch", "rate", "dec1",
       "Rushing yards + receiving yards per carry or catch.", "rushing yards + receiving yards",
       "carries + receptions", RATE_AGG, source=NFLV, status="derived", positions=RECV,
       reason="no carries or catches", minimum=("touches", 20)),
    _c("adjusted_yards_per_attempt", "Adjusted yards per attempt", "AY/A", "rate", "dec1",
       "Passing yards + 20 per touchdown pass − 45 per interception, per pass attempt (Pro Football Reference's "
       "formula; sacks are not in it).", "passing yards + 20 × passing TDs − 45 × interceptions", "pass attempts",
       RATE_AGG, source=NFLV, status="derived", positions=("QB",), reason="no pass attempts",
       minimum=("attempts", 50)),
    _c("td_rate", "Touchdown passes per attempt", "TD %", "rate", "pct", "Touchdown passes per pass attempt.",
       "passing TDs", "pass attempts", RATE_AGG, source=NFLV, status="derived", positions=("QB",),
       reason="no pass attempts", minimum=("attempts", 50)),
    _c("int_rate", "Interceptions per attempt", "Int %", "rate", "pct", "Interceptions per pass attempt.",
       "interceptions", "pass attempts", RATE_AGG, source=NFLV, status="derived", positions=("QB",),
       reason="no pass attempts", minimum=("attempts", 50)),
    _c("sack_rate", "Sacks per dropback", "Sack %", "rate", "pct",
       "Times sacked per pass attempt or sack (scrambles are not in this denominator, as the official sack rate).",
       "sacks", "pass attempts + sacks", RATE_AGG, source=NFLV, status="derived", positions=("QB",),
       reason="no pass attempts or sacks", minimum=("attempts", 50)),
    _c("scramble_yards", "Scramble yards", "Scr yds", "count", "int",
       "Rushing yards on his scrambles (a dropback he turned into a run).", "rushing yards on scrambles", None,
       GAMES_AGG, source=ADV_SRC, status="derived", positions=("QB",), per_game=True, reason=ADV_REASON),
    _c("rushing_points_share", "Share of his fantasy points from rushing", "Rush pts %", "share", "pct",
       "The fantasy points his rushing line is worth (yards, touchdowns, two-point runs and the league's rushing "
       "bonuses) / all his fantasy points, both in this league's scoring over the games he played. Fumbles stay in "
       "the total, not in the rushing part. Signed: above 100% when his passing points are below zero (interceptions).",
       "points from his rushing line", "his fantasy points", RATE_AGG, source="this league's scoring over " + NFLV,
       status="derived", positions=("QB",), reason="no fantasy points above zero in the window",
       minimum=("points", 20)),
    # air yards
    _c("wopr", "Weighted opportunity rating (WOPR)", "WOPR", "rate", "dec2",
       "1.5 × target share + 0.7 × air-yard share, both over the window (each summed numerator / summed "
       "denominator first). Weighs how much of his team's passing he draws, deep looks counting more.",
       "1.5 × target share + 0.7 × air-yard share", "—", "the window's two shares, then combined", source=NFLV,
       status="derived", positions=RECV, reason="no team targets or air yards in his games",
       minimum=("team_targets", 60)),
    _c("racr", "Receiver air conversion ratio (RACR)", "RACR", "rate", "dec2",
       "Receiving yards per air yard thrown his way: above 1 he gains more than the throws' depth (yards after the "
       "catch), below 1 less (incompletions, deep misses).", "receiving yards", "receiving air yards", RATE_AGG,
       source=NFLV, status="derived", positions=RECV,
       reason="his air yards in the window are zero or negative, so the ratio means nothing",
       minimum=("receiving_air_yards", 100)),
    _c("deep_targets", "Deep targets (20+ air yards)", "Deep Tgt", "count", "int",
       "Targets travelling 20 or more yards past the line of scrimmage (two-point tries and wiped-out plays left "
       "out).", "deep targets", None, GAMES_AGG, source=PBP, status="derived", positions=RECV, per_game=True),
    _c("deep_target_share", "Deep-target share (of his team's deep targets)", "Deep %", "share", "pct",
       "His deep targets (20+ air yards) / his team's deep targets in the games he played.", "deep targets",
       "team deep targets in the games he played", SHARE_AGG, source=ADV_SRC, status="derived", positions=RECV,
       reason="his team threw no deep pass in his games", minimum=("team_deep_targets", 10)),
    _c("deep_target_rate", "Deep targets, share of his targets", "Deep of Tgt", "rate", "pct",
       "Of his targets, the share that travelled 20+ air yards.", "deep targets", "targets", RATE_AGG, source=PBP,
       status="derived", positions=RECV, reason="no targets", minimum=("targets", 20)),
    # red zone
    _c("inside_10_targets", "Targets inside the 10", "In-10 Tgt", "count", "int",
       "Targets with the ball at the opponent's 10 or closer.", "targets inside the 10", None, GAMES_AGG, source=PBP,
       status="derived", positions=RECV, per_game=True),
    _c("inside_10_carries", "Carries inside the 10", "In-10 Car", "count", "int",
       "Carries with the ball at the opponent's 10 or closer.", "carries inside the 10", None, GAMES_AGG, source=PBP,
       status="derived", per_game=True),
    # efficiency
    _c("receiving_epa", "Receiving EPA", "Rec EPA", "count", "dec1",
       "Expected points added on the plays he was targeted: how much each target moved his team's expected score "
       "(nflfastR's model: down, distance, field position), added up. Negative when the targets hurt.",
       "EPA on his targets", None, GAMES_AGG, source=NFLV + " (nflfastR EPA)", status="derived", positions=RECV,
       per_game=True, reason="no targets"),
    _c("epa_per_target", "EPA per target", "EPA/Tgt", "rate", "dec2",
       "Receiving EPA per target.", "EPA on his targets", "targets", RATE_AGG, source=NFLV + " (nflfastR EPA)",
       status="derived", positions=RECV, reason="no targets", minimum=("targets", 20)),
    _c("receiving_success_rate", "Receiving success rate", "Rec SR", "rate", "pct",
       "Targets on which the play gained expected points (nflfastR's success: EPA above 0) per target.",
       "successful targets", "targets", RATE_AGG, source=ADV_SRC, status="derived", positions=RECV,
       reason="no targets", minimum=("targets", 20)),
    _c("first_downs_per_target", "First downs per target", "1D/Tgt", "rate", "pct",
       "Receiving first downs per target.", "receiving first downs", "targets", RATE_AGG, source=NFLV,
       status="derived", positions=RECV, reason="no targets", minimum=("targets", 20)),
    _c("receiving_td_rate", "Touchdowns per target", "TD/Tgt", "rate", "pct", "Receiving touchdowns per target.",
       "receiving TDs", "targets", RATE_AGG, source=NFLV, status="derived", positions=RECV, reason="no targets",
       minimum=("targets", 20)),
    _c("rushing_epa", "Rushing EPA", "Rush EPA", "count", "dec1",
       "Expected points added on his carries (scrambles included for quarterbacks), added up.", "EPA on his carries",
       None, GAMES_AGG, source=NFLV + " (nflfastR EPA)", status="derived", per_game=True, reason="no carries"),
    _c("epa_per_carry", "EPA per carry", "EPA/Car", "rate", "dec2", "Rushing EPA per carry.", "EPA on his carries",
       "carries", RATE_AGG, source=NFLV + " (nflfastR EPA)", status="derived", reason="no carries",
       minimum=("carries", 20)),
    _c("rushing_success_rate", "Rushing success rate", "Rush SR", "rate", "pct",
       "Carries that gained expected points (EPA above 0) per carry.", "successful carries", "carries", RATE_AGG,
       source=ADV_SRC, status="derived", reason="no carries", minimum=("carries", 20)),
    _c("first_downs_per_carry", "First downs per carry", "1D/Car", "rate", "pct", "Rushing first downs per carry.",
       "rushing first downs", "carries", RATE_AGG, source=NFLV, status="derived", reason="no carries",
       minimum=("carries", 20)),
    _c("rushing_td_rate", "Touchdowns per carry", "TD/Car", "rate", "pct", "Rushing touchdowns per carry.",
       "rushing TDs", "carries", RATE_AGG, source=NFLV, status="derived", reason="no carries",
       minimum=("carries", 20)),
    _c("dropback_epa", "EPA on dropbacks", "DB EPA", "count", "dec1",
       "Expected points added on his dropbacks (passes, sacks and scrambles), added up. The play's EPA, so a "
       "receiver's fumble after the catch counts here too.", "EPA on his dropbacks", None, GAMES_AGG,
       source=ADV_SRC, status="derived", positions=("QB",), per_game=True, reason="no dropbacks"),
    _c("epa_per_dropback", "EPA per dropback", "EPA/DB", "rate", "dec2", "EPA on dropbacks per dropback.",
       "EPA on his dropbacks", "dropbacks", RATE_AGG, source=ADV_SRC, status="derived", positions=("QB",),
       reason="no dropbacks", minimum=("dropbacks", 50)),
    _c("passing_success_rate", "Dropback success rate", "DB SR", "rate", "pct",
       "Dropbacks that gained expected points (EPA above 0) per dropback.", "successful dropbacks", "dropbacks",
       RATE_AGG, source=ADV_SRC, status="derived", positions=("QB",), reason="no dropbacks",
       minimum=("dropbacks", 50)),
    # expected points
    _c("expected_points", "Expected fantasy points", "xPts", "count", "pts",
       "What his targets and carries were worth on average (an opportunity-based estimate of past games, not next "
       "week's projection), in this league's scoring, added up over his games with an expected value.",
       "expected points in the window", None, GAMES_AGG,
       source="mart_player_expected_points (play-by-play opportunity model)", status="derived",
       reason="no expected value for his games (a kicker, or games before the opportunity model)"),
    _c("points_over_expected", "Points over expected", "Pts vs xPts", "count", "pts",
       "His fantasy points minus his expected fantasy points, over the same games (the games he played with an "
       "expected value), in this league's scoring. Positive: he scored more than his opportunities usually bring.",
       "fantasy points − expected points, same games", None, "summed over the games with an expected value; per game "
       "divides by those games", source="this league's scoring + mart_player_expected_points", status="derived",
       per_game=True, reason="no expected value for his games (a kicker, or games before the opportunity model)"),
    # Next Gen Stats (the rest of what nflverse's NGS files carry)
    _c("cushion", "Average cushion (yards)", "Cush", "rate", "dec1",
       "NFL Next Gen Stats' average distance, in yards, between him and the nearest defender at the snap, per "
       "target. NGS publishes a week only for a receiver or tight end with 5+ targets; over several weeks it is the "
       "mean of his weekly values weighted by NGS's targets — never a mean of means.", "weekly cushion x NGS targets",
       "NGS targets in his qualifying weeks", NGS_AGG, source=NGS, status="derived", positions=("WR", "TE"),
       reason=NGS_REASON.format(q=NGS_QUAL["rec"])),
    _c("ngs_intended_air_yards", "Intended air yards per target (Next Gen Stats)", "IAY", "rate", "dec1",
       "NFL Next Gen Stats' average distance the ball was thrown past the line of scrimmage on his targets "
       "(tracking, so catchable and uncatchable throws alike). NGS publishes a week only for a receiver or tight "
       "end with 5+ targets; over several weeks it is the mean of his weekly values weighted by NGS's targets — "
       "never a mean of means.", "weekly intended air yards x NGS targets", "NGS targets in his qualifying weeks",
       NGS_AGG, source=NGS, status="derived", positions=("WR", "TE"), reason=NGS_REASON.format(q=NGS_QUAL["rec"])),
    _c("rush_efficiency", "Rushing efficiency (Next Gen Stats)", "Eff", "rate", "dec2",
       "NFL Next Gen Stats' distance he travelled per rushing yard gained: lower is more north–south. NGS "
       "publishes a week only for a running back with 10+ carries; over several weeks it is the mean of his weekly "
       "values weighted by NGS's carries — never a mean of means.", "weekly efficiency x NGS carries",
       "NGS carries in his qualifying weeks", NGS_AGG, source=NGS, status="derived", positions=("RB",),
       reason=NGS_REASON.format(q=NGS_QUAL["rush"])),
    _c("stacked_box_rate", "Carries against 8+ defenders in the box", "8+ Box %", "rate", "pct",
       "NFL Next Gen Stats' share of his carries with eight or more defenders in the box. NGS publishes a week "
       "only for a running back with 10+ carries; over several weeks it is the mean of his weekly values weighted "
       "by NGS's carries — never a mean of means.", "weekly 8+ box % x NGS carries",
       "NGS carries in his qualifying weeks", NGS_AGG, source=NGS, status="derived", positions=("RB",),
       reason=NGS_REASON.format(q=NGS_QUAL["rush"])),
    _c("time_to_los", "Time to the line of scrimmage (seconds)", "TLOS", "rate", "dec2",
       "NFL Next Gen Stats' average time from the handoff to crossing the line of scrimmage, in seconds. NGS "
       "publishes a week only for a running back with 10+ carries; over several weeks it is the mean of his weekly "
       "values weighted by NGS's carries — never a mean of means.", "weekly time to the line x NGS carries",
       "NGS carries in his qualifying weeks", NGS_AGG, source=NGS, status="derived", positions=("RB",),
       reason=NGS_REASON.format(q=NGS_QUAL["rush"])),
    _c("aggressiveness", "Aggressiveness (throws into tight windows)", "Aggr %", "rate", "pct",
       "NFL Next Gen Stats' share of his pass attempts thrown with a defender within a yard of the receiver. NGS "
       "publishes a week only when he has 15+ pass attempts; over several weeks it is the mean of his weekly values "
       "weighted by NGS's pass attempts — never a mean of means.", "weekly aggressiveness x NGS pass attempts",
       "NGS pass attempts in his qualifying weeks", NGS_AGG, source=NGS, status="derived", positions=("QB",),
       reason=NGS_REASON.format(q=NGS_QUAL["pass"])),
    _c("ngs_pass_intended_air_yards", "Intended air yards per attempt (Next Gen Stats)", "IAY/Att", "rate", "dec1",
       "NFL Next Gen Stats' average distance his passes travelled past the line of scrimmage, per attempt. NGS "
       "publishes a week only when he has 15+ pass attempts; over several weeks it is the mean of his weekly values "
       "weighted by NGS's pass attempts — never a mean of means.", "weekly intended air yards x NGS pass attempts",
       "NGS pass attempts in his qualifying weeks", NGS_AGG, source=NGS, status="derived", positions=("QB",),
       reason=NGS_REASON.format(q=NGS_QUAL["pass"])),
    # Pro Football Reference, weekly (nflverse pfr_advstats)
    _c("drops", "Drops", "Drops", "count", "int",
       "Catchable passes he dropped, as Pro Football Reference's charters mark them.", "drops", None,
       GAMES_AGG + " (the games PFR covered)", source=PFR, status="derived", positions=RECV, per_game=True,
       reason=PFR_REASON),
    _c("drop_rate", "Drops per target", "Drop %", "rate", "pct",
       "Pro Football Reference's drops / his targets in the games PFR covered (a game PFR has no row for is out "
       "of both).", "drops", "targets in the games PFR covered", RATE_AGG, source=PFR, status="derived",
       positions=RECV, reason=PFR_REASON, minimum=("targets_pfr", 20)),
    _c("broken_tackles", "Broken tackles", "BTkl", "count", "int",
       "Tackles he broke or made a defender miss, running and after the catch (Pro Football Reference's charting).",
       "broken tackles", None, GAMES_AGG + " (the games PFR covered)", source=PFR, status="derived", positions=RECV,
       per_game=True, reason=PFR_REASON),
    _c("broken_tackle_rate", "Broken tackles per touch", "BTkl/Tch", "rate", "pct",
       "Broken tackles / his carries + catches in the games PFR covered.", "broken tackles",
       "carries + receptions in the games PFR covered", RATE_AGG, source=PFR, status="derived", positions=RECV,
       reason=PFR_REASON, minimum=("touches_pfr", 20)),
    _c("yards_before_contact_per_carry", "Yards before contact per carry", "YBC/Car", "rate", "dec1",
       "Rushing yards gained before the first defender touched him, per carry (Pro Football Reference's yards and "
       "carries, the same games): mostly the blocking.", "yards before contact", "PFR carries", RATE_AGG,
       source=PFR, status="derived", positions=("QB", "RB"), reason=PFR_REASON, minimum=("pfr_carries", 20)),
    _c("yards_after_contact_per_carry", "Yards after contact per carry", "YAC/Car", "rate", "dec1",
       "Rushing yards gained after the first contact, per carry (Pro Football Reference): mostly the runner.",
       "yards after contact", "PFR carries", RATE_AGG, source=PFR, status="derived", positions=("QB", "RB"),
       reason=PFR_REASON, minimum=("pfr_carries", 20)),
    _c("rec_yards_after_contact", "Receiving yards after contact", "Rec YACon", "rate", "dec1",
       "Receiving yards after the first contact. Pro Football Reference publishes it per season only, not per game, "
       "so no window here can use it.", None, None, None, source=PFR + ": season file only", status="unavailable",
       positions=RECV, reason="Pro Football Reference publishes receiving yards after contact per season, not per "
                              "game, so a window cannot use it."),
    _c("bad_throw_rate", "Bad throws per attempt", "Bad %", "rate", "pct",
       "Throws Pro Football Reference's charters mark off target or uncatchable / his pass attempts in the games "
       "PFR covered. PFR's own rate leaves spikes and throwaways out of the attempts; this one keeps them, so it "
       "reads a little lower.", "bad throws", "pass attempts in the games PFR covered", RATE_AGG, source=PFR,
       status="derived", positions=("QB",), reason=PFR_REASON, minimum=("attempts_pfr", 50)),
    _c("times_pressured", "Times pressured", "Press", "count", "int",
       "Dropbacks on which Pro Football Reference's charters saw him hurried, hit or sacked.", "pressures", None,
       GAMES_AGG + " (the games PFR covered)", source=PFR, status="derived", positions=("QB",), per_game=True,
       reason=PFR_REASON),
    _c("pressure_rate", "Pressured per dropback", "Press %", "rate", "pct",
       "Pro Football Reference's pressures (hurried, hit or sacked) / his dropbacks in the games PFR covered "
       "(attempts + sacks + scrambles from the play-by-play).", "pressures", "dropbacks in the games PFR covered",
       RATE_AGG, source=PFR, status="derived", positions=("QB",), reason=PFR_REASON,
       minimum=("dropbacks_pfr", 50)),
    _c("on_target_rate", "On-target throws per attempt", "On-tgt %", "rate", "pct",
       "Accurate throws per attempt. Pro Football Reference publishes it in its season file only (not per game, "
       "and not for this season yet), so no window here can use it.", None, None, None,
       source=PFR + ": season file only", status="unavailable", positions=("QB",),
       reason="Pro Football Reference publishes on-target throws per season only, so a window cannot use it."),
    # ---- end IM-1
]

# ---- IM-1 (Wave I-M): every column's group; the catalogue's order is the display order inside a group (IM-2's screen
# draws a group header over each run of columns, so the catalogue is kept in these groups' order)
GROUPS = ["Games and points", "Receiving", "Rushing", "Passing", "Air yards", "Red zone", "Efficiency", "Expected points",
          "Next Gen Stats", "Charting", "Snaps and routes", "Advanced (PFR)"]
GROUP_ORDER: dict[str, list[str]] = {
    "Games and points": ["games", "points"],
    "Receiving": ["targets", "receptions", "receiving_yards", "receiving_tds", "target_share", "catch_rate",
                  "yards_per_target", "yards_per_reception", "yac_per_reception", "receiving_first_downs"],
    "Rushing": ["carries", "rushing_yards", "rushing_tds", "carry_share", "rb_carry_share", "yards_per_carry",
                "rushing_first_downs", "yards_per_touch"],
    "Passing": ["attempts", "completions", "completion_rate", "passing_yards", "yards_per_attempt",
                "adjusted_yards_per_attempt", "passing_tds", "td_rate", "passing_interceptions", "int_rate",
                "sacks_suffered", "sack_rate", "dropbacks", "scrambles", "scramble_yards", "rushing_points_share"],
    "Air yards": ["adot", "air_yards_share", "wopr", "racr", "deep_targets", "deep_target_share", "deep_target_rate"],
    "Red zone": ["red_zone_targets", "red_zone_target_share", "inside_10_targets", "red_zone_carries",
                 "red_zone_carry_share", "inside_10_carries", "inside_5_carries", "inside_5_carry_share",
                 "red_zone_opportunities"],
    "Efficiency": ["receiving_epa", "epa_per_target", "receiving_success_rate", "first_downs_per_target",
                   "receiving_td_rate", "rushing_epa", "epa_per_carry", "rushing_success_rate", "first_downs_per_carry",
                   "rushing_td_rate", "dropback_epa", "epa_per_dropback", "passing_success_rate", "cpoe"],
    "Expected points": ["expected_points", "expected_points_per_game", "points_over_expected"],
    "Next Gen Stats": ["separation", "cushion", "ngs_intended_air_yards", "yac_over_expected", "ryoe_per_attempt",
                       "rush_efficiency", "stacked_box_rate", "time_to_los", "time_to_throw", "ngs_cpoe",
                       "aggressiveness", "ngs_pass_intended_air_yards"],
    "Charting": ["first_read_target_share", "catchable_rate", "charted_targets", "pressure_splits"],
    "Snaps and routes": ["snap_share", "route_participation", "tprr_proxy", "yprr_proxy", "routes"],
    "Advanced (PFR)": ["drops", "drop_rate", "broken_tackles", "broken_tackle_rate", "yards_before_contact_per_carry",
                       "yards_after_contact_per_carry", "rec_yards_after_contact", "bad_throw_rate", "times_pressured",
                       "pressure_rate", "on_target_rate"],
}
_BY_ID = {c["id"]: c for c in CATALOGUE}
CATALOGUE = [{**_BY_ID[cid], "group": g} for g in GROUPS for cid in GROUP_ORDER[g]]
assert len(CATALOGUE) == len(_BY_ID), sorted(set(_BY_ID) - {c["id"] for c in CATALOGUE})
# ---- end IM-1
CAT = {c["id"]: c for c in CATALOGUE}

PRESETS = [
    # ---- IM-1 (Wave I-M): the columns a manager reads first (10–14), `extra` for the picker, `full` = every column that
    # applies to the position and is available, in catalogue order (presets() recomputes it from the season's
    # availability; the module-level one counts every present / derived column)
    {"key": "wrte", "label": "WR / TE", "positions": ["WR", "TE"],
     "columns": ["games", "points", "targets", "target_share", "receptions", "receiving_yards", "receiving_tds", "adot",
                 "air_yards_share", "wopr", "epa_per_target", "snap_share", "separation", "yac_over_expected"],
     "extra": ["route_participation", "tprr_proxy", "yprr_proxy", "routes", "first_read_target_share",
               "red_zone_targets", "catchable_rate", "deep_targets", "racr", "receiving_success_rate", "drop_rate",
               "expected_points_per_game", "points_over_expected"],
     "sort": "target_share"},
    {"key": "rb", "label": "RB", "positions": ["RB"],
     "columns": ["games", "points", "carries", "carry_share", "rushing_yards", "yards_per_carry", "rushing_tds",
                 "targets", "target_share", "receiving_yards", "snap_share", "inside_10_carries", "epa_per_carry",
                 "ryoe_per_attempt"],
     "extra": ["rb_carry_share", "inside_5_carries", "inside_5_carry_share", "red_zone_opportunities", "route_participation",
               "tprr_proxy", "rushing_success_rate", "yards_after_contact_per_carry", "broken_tackle_rate",
               "yards_per_touch", "expected_points_per_game", "points_over_expected"],
     "sort": "carry_share"},
    {"key": "qb", "label": "QB", "positions": ["QB"],
     "columns": ["games", "points", "attempts", "completion_rate", "passing_yards", "passing_tds", "passing_interceptions",
                 "adjusted_yards_per_attempt", "epa_per_dropback", "carries", "rushing_yards", "rushing_points_share",
                 "time_to_throw", "cpoe"],
     "extra": ["ngs_cpoe", "scrambles", "scramble_yards", "pressure_rate", "bad_throw_rate", "sack_rate",
               "passing_success_rate", "aggressiveness", "pressure_splits"],
     "sort": "points"},
]


def full_columns(positions: list[str], cat: list[dict] | None = None) -> list[str]:
    """IM-1: every column that applies to these positions and is available, in catalogue order. Without a season's
    catalogue, every present / derived column (what the season can have)."""
    rows = cat if cat is not None else [{**c, "available": c["status"] in ("present", "derived")} for c in CATALOGUE]
    return [c["id"] for c in rows if c.get("available") and set(c["positions"]) & set(positions)]


def presets(cat: list[dict] | None = None) -> list[dict]:
    """The presets with ``full`` for this season's catalogue (IM-2's Full table)."""
    return [{**p, "full": full_columns(p["positions"], cat)} for p in PRESETS]


for _p in PRESETS:
    _p["full"] = full_columns(_p["positions"])
# ---- end IM-1


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
        elif c["source"] == NGS:                                        # ---- IL-1
            fam = NGS_METRICS[c["id"]][0]
            has = bool(frame is not None and not frame.empty and fam in frame and frame[fam].notna().any())
            c["available"] = has and season >= NGS_FIRST.get(c["id"], 2016)
            if not c["available"]:
                c["reason"] = (NGS_NOT_BUILT if frame is not None and not frame.empty and frame.attrs.get("ngs") == "missing"
                               else NGS_OFF if c["id"] not in NGS_FIRST or season >= NGS_FIRST[c["id"]]
                               else f"NGS publishes this from {NGS_FIRST[c['id']]}; none for {season}.")
            elif frame is not None:
                weeks = sorted({int(w) for w in frame.loc[frame[fam].notna(), "week"]})
                c["coverage"] = f"NGS weeks {weeks[0]}–{weeks[-1]}" if weeks else None
        elif c["source"] in (ADV_SRC, PFR):                              # ---- IM-1
            adv = frame.attrs.get("adv") if frame is not None else None
            if c["source"] == ADV_SRC:
                c["available"] = bool(frame is not None and not frame.empty and "target_successes" in frame
                                      and frame["target_successes"].notna().any())
                pfr_weeks = None
            else:
                fam = PFR_FAMILY[c["id"]]
                flags = ["has_pfr_rec", "has_pfr_rush"] if fam == "touch" else [f"has_pfr_{fam}"]
                hit = (frame[flags].any(axis=1) if frame is not None and not frame.empty and set(flags) <= set(frame)
                       else pd.Series(dtype=bool))
                c["available"] = bool(hit.any()) and season >= PFR_FIRST
                pfr_weeks = sorted({int(w) for w in frame.loc[hit, "week"]}) if c["available"] else None
            if not c["available"]:
                c["reason"] = (ADV_NOT_BUILT if adv == "missing" else PFR_OFF if c["source"] == PFR
                               else c["reason"])
            elif pfr_weeks:
                c["coverage"] = f"PFR weeks {pfr_weeks[0]}–{pfr_weeks[-1]}"
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


_frames = memo.region("stats", ttl=TTL_S)   # INF-2 (Wave I-J): in the memory budget (was cleared past 8 seasons)


def season_rows(season: int, season_type: str) -> pd.DataFrame:
    """Every fct_player_game row of the season (all positions), + the team's RB carries and inside-5 carries per game.
    Cached 10 minutes (NFL-wide: the same for every league)."""
    key = (int(season), season_type)
    hit = _frames.get(key)
    if hit is not None:
        return hit
    lo, hi = (19, 22) if season_type == "POST" else (1, 18)
    df = query(FCT_SQL, (int(season), season_type, lo, hi))
    if not df.empty:
        for c in [c for c in SUMS if c in df] + RUSH_LINE + [   # IM-1: the advanced mart's columns arrive below
                "team_targets", "team_carries", "team_air_yards", "team_first_read_targets", "team_charted_targets",
                "team_red_zone_targets", "team_red_zone_carries", "team_dropbacks_with_participation",
                "offense_snap_pct", "passing_cpoe", "week"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df["played"] = df["played"].fillna(False).astype(bool)
        df["snaps_known"] = df["snaps_known"].fillna(False).astype(bool)
        rb = df[df["position"].isin(BACKFIELD)].groupby(["team", "game_id"])["carries"].sum(min_count=1).rename("team_rb_carries")
        i5 = df.groupby(["team", "game_id"])["inside_5_carries"].sum(min_count=1).rename("team_inside_5_carries")
        df = df.merge(rb.reset_index(), on=["team", "game_id"], how="left").merge(i5.reset_index(), on=["team", "game_id"],
                                                                                     how="left")
        df = with_advanced(df, int(season), season_type)               # ---- IM-1
        df = with_ngs(df, int(season), season_type)                    # ---- IL-1
    return _frames.put(key, df, ttl=TTL_S)


# ---- IL-1: NGS's weekly row onto his game row of the same week (regular season; one game a week per player)
def with_ngs(df: pd.DataFrame, season: int, season_type: str) -> pd.DataFrame:
    state = "off"
    if season_type == "REG":
        try:
            state = "missing" if missing_relations((NGS_REL,)) else "ok"
        except Exception:  # noqa: BLE001 - the Stats frame never fails for its NGS columns: they show — with the reason
            state = "missing"
    ngs = query(NGS_SQL, (int(season),)) if state == "ok" else pd.DataFrame()
    if ngs.empty:
        out = df.assign(**{c: np.nan for c in NGS_VALUES + NGS_WEIGHTS})
    else:
        for c in NGS_VALUES + NGS_WEIGHTS + ["week"]:
            ngs[c] = pd.to_numeric(ngs[c], errors="coerce")
        # his first row of the week carries NGS's numbers (a second row the same week would double the weights)
        first = ~df.duplicated(["gsis_id", "week"])
        out = df.merge(ngs, on=["gsis_id", "week"], how="left")
        for c in NGS_VALUES + NGS_WEIGHTS:
            out[c] = out[c].where(first.to_numpy())
    out.attrs = {**df.attrs, "ngs": state}                             # IM-1: keep the advanced mart's state
    return out
# ---- end IL-1


# ---- IM-1 (Wave I-M): the advanced mart's row onto his game row (gsis_id + game_id; one row per player-game)
def with_advanced(df: pd.DataFrame, season: int, season_type: str) -> pd.DataFrame:
    try:
        state = "missing" if missing_relations((ADV_REL,)) else "ok"
    except Exception:  # noqa: BLE001 - the Stats frame never fails for these columns: they show — with the reason
        state = "missing"
    adv = query(ADV_SQL, (int(season), season_type)) if state == "ok" else pd.DataFrame()
    if adv.empty:
        out = df.assign(**{c: np.nan for c in ADV_PBP + ADV_PFR}, **{c: False for c in ADV_FLAGS})
    else:
        for c in ADV_PBP + ADV_PFR:
            adv[c] = pd.to_numeric(adv[c], errors="coerce")
        out = df.merge(adv, on=["gsis_id", "game_id"], how="left")
        for c in ADV_FLAGS:
            out[c] = out[c].astype("boolean").fillna(False).astype(bool)
    out.attrs = {**df.attrs, "adv": state}
    return out
# ---- end IM-1


def clear() -> None:
    _frames.clear()
    _aggs.clear()


# ---- IM-1 (Wave I-M): the window's aggregate is NFL-wide (no league in it: the league's points merge after), so it is
# kept per window — every league and every position preset of the same window reuses it (101 columns made the
# aggregate the request's largest cost). Keyed by the season frame's identity, so a reloaded season starts afresh.
_aggs = memo.region("stats_agg", ttl=TTL_S, max_entries=8)   # ≤ 8 windows x ~0.6–0.8 MB


def aggregate_window(mine: pd.DataFrame, key: tuple) -> pd.DataFrame:
    """``aggregate(mine)`` for the window ``key`` (season, season type, window, basis, weeks, the frame's id and size)."""
    hit = _aggs.get(key)
    if hit is None:
        hit = _aggs.put(key, aggregate(mine))
    return hit.copy()
# ---- end IM-1


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
    # ---- IL-1: NGS — the value x NGS's weight over the weeks NGS published, and the weight alone (the same weeks)
    ngs_cols = []
    for cid, (val, wt, _fam) in NGS_METRICS.items():
        if val in g:
            v = pd.to_numeric(g[val], errors="coerce")
            n = pd.to_numeric(g[wt], errors="coerce").where(v.notna())
            g[f"_{cid}_w"], g[f"_{cid}_n"] = v * n, n
            ngs_cols += [f"_{cid}_w", f"_{cid}_n"]
    for fam, (val, wt) in {"pass": ("avg_time_to_throw", "ngs_pass_attempts"), "rush": ("rush_yards_over_expected_per_att",
                           "ngs_rush_attempts"), "rec": ("avg_separation", "ngs_targets")}.items():
        if val in g:
            g[f"ngs_{fam}_week"] = pd.to_numeric(g[val], errors="coerce").notna()
            g[f"_ngs_{fam}_den"] = pd.to_numeric(g[wt], errors="coerce").where(g[f"ngs_{fam}_week"])
            ngs_cols += [f"ngs_{fam}_week", f"_ngs_{fam}_den"]
    if "ngs_receptions" in g:
        g["_ngs_rec_receptions"] = pd.to_numeric(g["ngs_receptions"], errors="coerce").where(g.get("ngs_rec_week", False))
        ngs_cols.append("_ngs_rec_receptions")
    # ---- end IL-1
    # ---- IM-1: touches; PFR's counts divide only by the denominators of the games PFR covered (has_pfr_*)
    flags = {c: (g[c].astype("boolean").fillna(False).astype(bool) if c in g else pd.Series(False, index=g.index))
             for c in ADV_FLAGS}
    g["touches"] = g["carries"].add(g["receptions"], fill_value=0)
    g["targets_pfr"] = g["targets"].where(flags["has_pfr_rec"])
    g["touches_pfr"] = g["touches"].where(flags["has_pfr_rec"] | flags["has_pfr_rush"])
    g["attempts_pfr"] = g["attempts"].where(flags["has_pfr_pass"])
    g["dropbacks_pfr"] = g["dropbacks"].where(flags["has_pfr_pass"])
    g["pfr_rec_games"], g["pfr_pass_games"] = flags["has_pfr_rec"], flags["has_pfr_pass"]
    im1_sums = ["touches", "targets_pfr", "touches_pfr", "attempts_pfr", "dropbacks_pfr"]
    for c in SUMS:                     # a hand-built frame (tests) may lack the advanced mart's columns: unknown
        if c not in g:
            g[c] = np.nan
    # ---- end IM-1
    by = g.groupby("gsis_id", sort=False)
    # position = mode() within group (order by position): the most frequent, ties to the first alphabetically
    cnt = g.dropna(subset=["position"]).groupby(["gsis_id", "position"]).size().reset_index(name="n")
    pos = cnt.sort_values(["gsis_id", "n", "position"], ascending=[True, False, True]).drop_duplicates("gsis_id")
    out = pd.DataFrame({
        "player_name": by["player_name"].max(),
        "games": by["played"].sum().astype(int),
        "first_week": by["week"].min().astype(int),
        "last_week": by["week"].max().astype(int),
        **by[SUMS + TEAM_SUMS + im1_sums].sum(min_count=1).to_dict("series"),   # IM-1: one pass (was one per column)
        "team_dropbacks_with_participation": by["team_dropbacks_with_participation"].sum(min_count=1),
        "targets_in_participation_games": by["targets_in_participation_games"].sum(min_count=1),
        "receiving_yards_in_participation_games": by["receiving_yards_in_participation_games"].sum(min_count=1),
        "games_with_participation": by["games_with_participation"].sum().astype(int),
        "charted_games": by["charted_game"].sum().astype(int),
        "snap_games": by["_snap"].count().astype(int),
        "snap_share": by["_snap"].mean(),
        "_cpoe_w": by["_cpoe_w"].sum(min_count=1),
        "_cpoe_n": by["_cpoe_n"].sum(min_count=1),
        **{c: (by[c].sum().astype(int) if c.endswith("_week") else by[c].sum(min_count=1)) for c in ngs_cols},  # IL-1
        "pfr_rec_games": by["pfr_rec_games"].sum().astype(int), "pfr_pass_games": by["pfr_pass_games"].sum().astype(int),
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
    # ---- IM-1 (Wave I-M): every rate is summed numerator / summed denominator over the window; 0 denominator -> null
    # (built apart and joined once: ~40 inserts one by one fragment the frame)
    n: dict[str, pd.Series] = {}
    n["yards_per_reception"] = ratio(out["receiving_yards"], out["receptions"], 2)
    n["yards_per_touch"] = ratio(out["rushing_yards"].add(out["receiving_yards"], fill_value=0), out["touches"], 2)
    ay = out["passing_yards"] + 20 * out["passing_tds"].fillna(0) - 45 * out["passing_interceptions"].fillna(0)
    n["adjusted_yards_per_attempt"] = ratio(ay, out["attempts"], 2)
    n["td_rate"] = ratio(out["passing_tds"], out["attempts"])
    n["int_rate"] = ratio(out["passing_interceptions"], out["attempts"])
    n["sack_rate"] = ratio(out["sacks_suffered"], out["attempts"].add(out["sacks_suffered"], fill_value=0))
    n["wopr"] = (1.5 * out["target_share"] + 0.7 * out["air_yards_share"]).round(4)
    n["racr"] = ratio(out["receiving_yards"], out["receiving_air_yards"].where(out["receiving_air_yards"] > 0), 2)
    n["deep_target_share"] = ratio(out["deep_targets"], out["team_deep_targets"])
    n["deep_target_rate"] = ratio(out["deep_targets"], out["targets"])
    out[["receiving_epa", "rushing_epa", "dropback_epa"]] = out[["receiving_epa", "rushing_epa", "dropback_epa"]].round(2)
    n["epa_per_target"] = ratio(out["receiving_epa"], out["targets"], 3)
    n["receiving_success_rate"] = ratio(out["target_successes"], out["targets"])
    n["first_downs_per_target"] = ratio(out["receiving_first_downs"], out["targets"])
    n["receiving_td_rate"] = ratio(out["receiving_tds"], out["targets"])
    n["epa_per_carry"] = ratio(out["rushing_epa"], out["carries"], 3)
    n["rushing_success_rate"] = ratio(out["carry_successes"], out["carries"])
    n["first_downs_per_carry"] = ratio(out["rushing_first_downs"], out["carries"])
    n["rushing_td_rate"] = ratio(out["rushing_tds"], out["carries"])
    n["epa_per_dropback"] = ratio(out["dropback_epa"], out["dropbacks"], 3)
    n["passing_success_rate"] = ratio(out["dropback_successes"], out["dropbacks"])
    # Pro Football Reference: its counts over the games it covered, divided by those games' denominators
    n["drops"], n["broken_tackles"], n["times_pressured"] = (out["pfr_drops"], out["pfr_broken_tackles"],
                                                             out["pfr_times_pressured"])
    n["drop_rate"] = ratio(out["pfr_drops"], out["targets_pfr"])
    n["broken_tackle_rate"] = ratio(out["pfr_broken_tackles"], out["touches_pfr"])
    n["yards_before_contact_per_carry"] = ratio(out["pfr_rush_yards_before_contact"], out["pfr_carries"], 2)
    n["yards_after_contact_per_carry"] = ratio(out["pfr_rush_yards_after_contact"], out["pfr_carries"], 2)
    n["bad_throw_rate"] = ratio(out["pfr_bad_throws"], out["attempts_pfr"])
    n["pressure_rate"] = ratio(out["pfr_times_pressured"], out["dropbacks_pfr"])
    out = pd.concat([out, pd.DataFrame(n, index=out.index)], axis=1)
    # ---- end IM-1
    # the routes columns stay null without a licensed feed (routes = sum of nulls = null)
    out = pd.concat([out, pd.DataFrame({f"{c}_per_game": ratio(out[c], out["games"], 2)          # IM-1: joined once
                                        for c in [c["id"] for c in CATALOGUE if c["per_game"] and c["id"] not in POINT_COLS]},
                                       index=out.index)], axis=1)
    # ---- IL-1: NGS over the window = sum(value x weight) / sum(weight), the weeks NGS published only; none → null
    for cid in NGS_METRICS:
        if f"_{cid}_w" in out:
            v = out[f"_{cid}_w"] / out[f"_{cid}_n"].where(out[f"_{cid}_n"] > 0)
            out[cid] = (v * NGS_SCALE[cid]).round(4) if cid in NGS_SCALE else v.round(2)        # IM-1: % -> share
    renames = {"ngs_pass_week": "ngs_pass_weeks", "ngs_rush_week": "ngs_rush_weeks", "ngs_rec_week": "ngs_rec_weeks",
               "_ngs_pass_den": "ngs_pass_attempts", "_ngs_rush_den": "ngs_rush_attempts", "_ngs_rec_den": "ngs_targets",
               "_ngs_rec_receptions": "ngs_receptions"}
    out = out.rename(columns={k: v for k, v in renames.items() if k in out})
    out = out.drop(columns=[c for c in out.columns if c.startswith("_") and c.endswith(("_w", "_n"))])
    # ---- end IL-1
    out = out.drop(columns=["_cpoe_w", "_cpoe_n"], errors="ignore")
    return out.copy().reset_index()                                     # IM-1: one block per dtype again


def points(league_rows: pd.DataFrame, g: pd.DataFrame, scoring: dict | None = None) -> pd.DataFrame:
    """points, points_per_game (this league's scoring, cents-exact like mart_league_player_season), expected points per
    game over the same game rows; IM-1: the expected total, points over expected (the same games: played with an
    expected value) and, with the league's ``scoring``, a quarterback's rushing share of his points."""
    keys = g[["gsis_id", "game_id"]].drop_duplicates()
    lp = keys.merge(league_rows[["gsis_id", "game_id", "points", "points_expected", "expected_known"]],
                    on=["gsis_id", "game_id"], how="left")
    lp = lp.merge(g[["gsis_id", "game_id", "played", "position"]].drop_duplicates(["gsis_id", "game_id"]),
                  on=["gsis_id", "game_id"], how="left")
    lp["played"] = lp["played"].fillna(False).astype(bool)
    lp["pc"] = _cents(lp["points"])
    lp["xc"] = _cents(lp["points_expected"]).where(lp["expected_known"].fillna(False).astype(bool) & lp["played"])
    lp["pcx"] = lp["pc"].where(lp["xc"].notna())                     # IM-1: his points in the games with an expected value
    by = lp.groupby("gsis_id")
    lp["_pp"] = lp["played"] & lp["pc"].notna()   # the mart's games: played with a points row
    out = pd.DataFrame({"_pc": by["pc"].sum(min_count=1), "games_p": lp.groupby("gsis_id")["_pp"].sum(),
                        "_xc": by["xc"].sum(min_count=1), "games_with_expected": by["xc"].count()})
    out["points"] = out["_pc"] / 100
    out["points_per_game"] = ratio(out["_pc"], out["games_p"] * 100, 2)
    out["expected_points_per_game"] = ratio(out["_xc"], out["games_with_expected"] * 100, 2)
    # ---- IM-1: totals in cents, then points; over expected = his points − expected on the same games
    poe = by["pcx"].sum(min_count=1) - out["_xc"]
    out["expected_points"] = out["_xc"] / 100
    out["points_over_expected"] = poe / 100
    out["points_over_expected_per_game"] = ratio(poe, out["games_with_expected"] * 100, 2)
    cols = ["points", "points_per_game", "expected_points_per_game", "games_with_expected", "expected_points",
            "points_over_expected", "points_over_expected_per_game"]
    out["rushing_points"], out["rushing_points_share"] = np.nan, np.nan
    if scoring is not None and "position" in g and set(RUSH_LINE) <= set(g.columns):
        q = g[(g["position"] == "QB") & g["played"].fillna(False).astype(bool)].drop_duplicates(["gsis_id", "game_id"])
        if not q.empty:
            line = q[RUSH_LINE].apply(pd.to_numeric, errors="coerce").assign(position="QB")  # the league's pricing
            try:
                rc = (LR.price_games(line, scoring) * 100).round().to_numpy()
            except Exception:  # noqa: BLE001 - a scoring the flat pricer cannot read: the share is unknown, never a 500
                rc = np.full(len(q), np.nan)
            q = q[["gsis_id", "game_id"]].assign(rc=rc)
            q = q.merge(lp[["gsis_id", "game_id", "pc"]], on=["gsis_id", "game_id"], how="inner")
            q = q[q["pc"].notna()]                                  # the games with a points row, both sides
            rs = q.groupby("gsis_id")[["rc", "pc"]].sum(min_count=1)       # an unpriced line stays unknown
            out.loc[rs.index, "rushing_points"] = rs["rc"] / 100
            out.loc[rs.index, "rushing_points_share"] = ratio(rs["rc"], rs["pc"].where(rs["pc"] > 0))
    cols += ["rushing_points", "rushing_points_share"]
    # ---- end IM-1
    return out[cols].reset_index()


def parse_weeks(weeks: str | None) -> tuple[int, int] | None:
    if not weeks:
        return None
    m = re.fullmatch(r"\s*(\d{1,2})\s*-\s*(\d{1,2})\s*", weeks)
    if not m:
        return None
    lo, hi = int(m.group(1)), int(m.group(2))
    return (lo, hi) if 1 <= lo <= hi <= 22 else None


IDENTITY = ["gsis_id", "player_name", "position", "team", "headshot_url", "rostered_by_roster_id", "rostered_by_team", "games",
            "first_week", "last_week", "points", "points_per_game"]
# the sample behind a column (shown on hover: "12 of 57 team carries")
SAMPLE = {"target_share": ["team_targets"], "carry_share": ["team_carries"], "rb_carry_share": ["team_rb_carries"],
          "air_yards_share": ["receiving_air_yards", "team_air_yards"], "adot": ["receiving_air_yards"],
          "red_zone_target_share": ["team_red_zone_targets"], "red_zone_carry_share": ["team_red_zone_carries"],
          "inside_5_carry_share": ["team_inside_5_carries"],
          "first_read_target_share": ["first_read_targets", "team_first_read_targets", "charted_games"],
          "catchable_rate": ["catchable_targets", "charted_targets", "charted_games"],
          "route_participation": ["routes_proxy", "team_dropbacks_with_participation", "games_with_participation"],
          "tprr_proxy": ["routes_proxy", "games_with_participation"], "yprr_proxy": ["routes_proxy", "games_with_participation"],
          "snap_share": ["snap_games"], "expected_points_per_game": ["games_with_expected"],
          "yac_per_reception": ["receiving_yards_after_catch"],
          # ---- IL-1: the NGS weeks and NGS's own denominator behind each NGS column
          "time_to_throw": ["ngs_pass_weeks", "ngs_pass_attempts"], "ngs_cpoe": ["ngs_pass_weeks", "ngs_pass_attempts"],
          "ryoe_per_attempt": ["ngs_rush_weeks", "ngs_rush_attempts"], "separation": ["ngs_rec_weeks", "ngs_targets"],
          "yac_over_expected": ["ngs_rec_weeks", "ngs_receptions"],
          # ---- IM-1 (Wave I-M): the sample behind each new column (the catalogue's `minimum` names one of them)
          "yards_per_reception": ["receptions"], "yards_per_touch": ["touches"],
          "adjusted_yards_per_attempt": ["attempts"], "td_rate": ["attempts"], "int_rate": ["attempts"],
          "sack_rate": ["attempts", "sacks_suffered"], "rushing_points_share": ["rushing_points"],
          "wopr": ["team_targets", "team_air_yards"], "racr": ["receiving_air_yards"],
          "deep_target_share": ["deep_targets", "team_deep_targets"], "deep_target_rate": ["deep_targets", "targets"],
          "epa_per_target": ["targets"], "receiving_success_rate": ["targets"], "first_downs_per_target": ["targets"],
          "receiving_td_rate": ["targets"], "epa_per_carry": ["carries"], "rushing_success_rate": ["carries"],
          "first_downs_per_carry": ["carries"], "rushing_td_rate": ["carries"], "epa_per_dropback": ["dropbacks"],
          "passing_success_rate": ["dropbacks"], "expected_points": ["games_with_expected"],
          "points_over_expected": ["games_with_expected"],
          "cushion": ["ngs_rec_weeks", "ngs_targets"], "ngs_intended_air_yards": ["ngs_rec_weeks", "ngs_targets"],
          "rush_efficiency": ["ngs_rush_weeks", "ngs_rush_attempts"], "stacked_box_rate": ["ngs_rush_weeks", "ngs_rush_attempts"],
          "time_to_los": ["ngs_rush_weeks", "ngs_rush_attempts"], "aggressiveness": ["ngs_pass_weeks", "ngs_pass_attempts"],
          "ngs_pass_intended_air_yards": ["ngs_pass_weeks", "ngs_pass_attempts"],
          "drops": ["targets_pfr", "pfr_rec_games"], "drop_rate": ["targets_pfr", "pfr_rec_games"],
          "broken_tackles": ["touches_pfr"], "broken_tackle_rate": ["touches_pfr"],
          "yards_before_contact_per_carry": ["pfr_carries"], "yards_after_contact_per_carry": ["pfr_carries"],
          "bad_throw_rate": ["attempts_pfr", "pfr_pass_games"], "times_pressured": ["dropbacks_pfr", "pfr_pass_games"],
          "pressure_rate": ["dropbacks_pfr", "pfr_pass_games"]}


def fields(positions: list[str]) -> list[str]:
    """The row's fields for these positions: identity, the catalogue's columns that apply, their per-game twins and
    the samples behind them (a WR row carries no passing columns)."""
    out = list(IDENTITY)
    for c in CATALOGUE:
        if c["id"] in ("games", "points") or not set(c["positions"]) & set(positions):
            continue
        if c["status"] in ("planned",) or c["id"] in NO_FIELD:          # IM-1: NO_FIELD (was pressure_splits)
            continue
        out.append(c["id"])
        if c["per_game"]:
            out.append(f"{c['id']}_per_game")
        out += SAMPLE.get(c["id"], [])
    return list(dict.fromkeys(out))


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


# ---- IM-1 (Wave I-M): GET /api/players.csv — the Stats table as a file, from the same frame as /api/players?window=
CSV_IDENTITY = [("player_name", "Player"), ("position", "Position"), ("team", "NFL team"),
                ("rostered_by_team", "Rostered by"), ("games", "Games played")]
_CSV_RISKY = ("=", "+", "-", "@", "\t", "\r")


def _csv_cell(v) -> str:
    """One cell: unknown is an empty cell (never 0); numbers as they are; text that a spreadsheet would run as a formula
    (a leading = + - @) gets a leading apostrophe."""
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return ""
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, (int, float, np.integer, np.floating)):
        f = float(v)
        return repr(round(f, 4)) if not f.is_integer() else str(int(f))
    s = str(v)
    if s.startswith(_CSV_RISKY):
        s = "'" + s
    return '"' + s.replace('"', '""') + '"' if any(ch in s for ch in ',"\n') else s


def csv_columns(d: dict, preset: str | None = None, cols: str | None = None, view: str | None = None) -> list[str]:
    """The request's columns: ``cols=`` (ids, comma-separated, unknown ids refused), else the preset's — the one named
    by ``preset=`` or the one whose positions are the request's — Key stats (``columns``) or, with ``view=full``,
    the Full table; with no matching preset, every available column that applies. Games stays an identity column."""
    cat = {c["id"]: c for c in d["catalogue"]}
    if cols:
        ids = [x.strip() for x in cols.split(",") if x.strip()]
        bad = [x for x in ids if x not in cat]
        if bad:
            raise ValueError(f"unknown column {', '.join(bad[:5])}")
        out = ids
    else:
        ps = d.get("presets") or presets(d["catalogue"])
        p = next((p for p in ps if p["key"] == preset), None) if preset else None
        p = p or next((p for p in ps if p["positions"] == d["positions"]), None)
        if p is None:
            out = full_columns(d["positions"], d["catalogue"])
        else:
            out = p["full"] if (view or "").lower() == "full" else p["columns"]
    return [c for c in out if c != "games" and c in cat and cat[c].get("available", True) and c not in NO_FIELD]


def csv_filename(d: dict) -> str:
    w = d.get("window") or {}
    key = w.get("key") or "season"
    weeks = w.get("weeks") or []
    span = f"-weeks-{weeks[0]}-{weeks[1]}" if len(weeks) == 2 and weeks[0] is not None else ""
    pos = "-".join(p.lower() for p in d.get("positions") or []) or "all"
    st = "" if d.get("season_type", "REG") == "REG" else "-playoffs"
    return f"isuckatfantasy-stats-{d['season']}{st}-{pos}-{key}{span}.csv"


def csv_lines(d: dict, columns: list[str], per_game: bool = False):
    """The header row of labels, then one row per player (the frame's own order). ``per_game`` swaps a count that has a
    per-game twin for that twin ("Targets per game")."""
    cat = {c["id"]: c for c in d["catalogue"]}
    # a league without rosters (IM-3's reference leagues) has no ownership field: the column is absent, not empty
    ident = [(k, lab) for k, lab in CSV_IDENTITY
             if k != "rostered_by_team" or any("rostered_by_team" in p for p in d["players"]) or not d["players"]]
    fields_, labels = [k for k, _ in ident], [lab for _, lab in ident]
    for cid in columns:
        c = cat[cid]
        if per_game and c.get("per_game"):
            fields_.append(f"{cid}_per_game")
            labels.append(f"{c['label']} per game")
        else:
            fields_.append(cid)
            labels.append(c["label"])
    yield ",".join(_csv_cell(x) for x in labels) + "\r\n"
    for p in d["players"]:
        yield ",".join(_csv_cell(p.get(f)) for f in fields_) + "\r\n"
# ---- end IM-1
