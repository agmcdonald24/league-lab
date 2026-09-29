"""Plain-English tables.

Every column the explorer shows is registered here once with a label, a display kind and a
one-line explanation. Pages pass raw mart columns to ``show()`` and get readable headers,
percentages shown as percentages, booleans as words, and a hover tooltip on every header.
The Home page renders the same registry as a glossary.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import streamlit as st


@dataclass(frozen=True)
class Col:
    label: str
    kind: str = "auto"  # pct | signed_pct | num1 | num2 | signed1 | int | text | bool | yes | dt | pct100
    help: str = ""
    yes: str = "Yes"  # for bool kinds: text shown when true
    no: str = ""  # text shown when false


C = Col
COLUMNS: dict[str, Col] = {
    # ---- identity
    "player_name": C("Player"), "defender_name": C("Defender"), "kicker_name": C("Kicker"),
    "position": C("Pos"), "nfl_team": C("Team"), "team": C("Team"), "teams": C("Teams", help="Every NFL team the player appeared for this season"),
    "opponent": C("Opp", help="Next opponent (blank on a bye)"), "opponent_team": C("Opp"), "defense": C("Defense"),
    "season": C("Season", "int"), "week": C("Week", "int"), "next_week": C("Week", "int"),
    "team_name": C("Team"), "manager_name": C("Manager"), "rostered_by_team": C("Rostered by"), "rostered_by_manager": C("Manager"),
    "games_played": C("GP", "int", "Games played this season"), "games": C("G", "int"), "games_with_expected": C("GP (xPts)", "int", "Games with an expected-points estimate"),
    "games_with_qb": C("G w/ QB", "int"),
    # ---- status
    "is_current_starter": C("Lineup", "bool", "Whether the player is in the roster's current starting lineup", yes="Starter", no="Bench"),
    "their_starter": C("Their lineup", "bool", yes="Starter", no="Bench"), "starter": C("Lineup", "bool", yes="Starter", no="Bench"),
    "is_on_ir": C("IR", "bool", "On the roster's injured-reserve slot", yes="IR", no=""),
    "is_bye": C("Bye", "bool", "No NFL game next week", yes="BYE", no=""),
    "is_home": C("Site", "bool", yes="Home", no="Away"),
    "is_starter": C("Started", "bool", yes="Yes", no="No"), "is_champion": C("Champion", "bool", yes="Yes", no=""),
    "is_free_agent": C("Free agent", "bool", yes="Yes", no=""), "changed_kicker": C("New K", "bool", "Started a different kicker than the week before", yes="Yes", no=""),
    "coverage_known": C("Coverage data", "bool", yes="Yes", no="None"), "played": C("Played", "bool", yes="Yes", no="No"),
    "is_playoff_week": C("Playoffs", "bool", yes="Yes", no=""), "is_keeper": C("Keeper", "bool", yes="Yes", no=""),
    "has_nfl_stat_row": C("NFL stats", "bool", yes="Yes", no="None"), "complementary": C("Fit", "bool", "You are thin here and the partner is deep", yes="Yes", no=""),
    "injury_status": C("Injury", help="Latest official injury report status (Out / Doubtful / Questionable)"),
    "injury": C("Injury detail"), "practice_status": C("Practice", help="Latest practice participation from the injury report"),
    "roster_status": C("NFL status", help="ACT active, RES injured reserve, INA inactive, CUT, DEV practice squad"),
    "depth_rank": C("Depth", "int", "Rank on the team's latest depth chart at the player's position (1 = starter)"),
    "depth_pos": C("Depth slot"), "depth_position": C("Slot"), "acquired": C("Acquired", help="How the current roster got the player"),
    # ---- production
    "ppg_std": C("PPG", "num1", "Fantasy points per game this season, this league's scoring"),
    "points_per_game_l3": C("PPG (L3)", "num1", "Points per game over the last three games played"),
    "points_per_game_l5": C("PPG (L5)", "num1", "Points per game over the last five games played"),
    "expected_per_game": C("xPPG", "num1", "Expected points per game: this league's scoring applied to the opportunity the player got (targets, air yards, carries, field position) — pass/rush/receive only"),
    "diff_per_game": C("PPG − xPPG", "signed1", "Actual minus expected per game. Negative = producing below the opportunity (candidate to improve); positive = above it (candidate to cool off)"),
    "points_std": C("Points", "num1", "Season fantasy points, this league's scoring"), "points_current_scoring": C("Points", "num1"),
    "points": C("Points", "num1"), "points_observed": C("Points", "num1", "Points as Sleeper scored them"), "points_recomputed": C("Recomputed", "num1", "Points recomputed from NFL stats under this season's scoring (blank for DEF)"),
    "points_actual": C("Actual", "num1"), "points_expected": C("Expected", "num1"), "points_diff": C("Diff", "signed1"),
    "points_started": C("Started", "num1", "Points scored by the lineup actually started"),
    "points_optimal": C("Best possible", "num1", "Points of the best lineup available from the roster that week"),
    "bench_points_left": C("Left on bench", "num1", "Best possible minus started"),
    "lineup_efficiency": C("Lineup eff.", "pct", "Started points as a share of the best possible lineup"),
    "targets": C("Tgt", "int"), "carries": C("Car", "int"), "attempts": C("Att", "int"), "completions": C("Comp", "int"),
    "receptions": C("Rec", "int"), "receiving_yards": C("Rec yds", "int"), "rushing_yards": C("Rush yds", "int"),
    "passing_yards": C("Pass yds", "int"), "receiving_tds": C("Rec TD", "int"), "rushing_tds": C("Rush TD", "int"),
    "passing_tds": C("Pass TD", "int"), "passing_interceptions": C("INT", "int"), "sacks_suffered": C("Sacked", "int"),
    "receiving_air_yards": C("Air yds", "int"), "team_targets": C("Team tgt", "int", "The team's total targets in the same games"),
    "team_carries": C("Team car", "int"), "team_air_yards": C("Team air yds", "int"), "rec_yards": C("Rec yds", "int"),
    "targets_per_game": C("Tgt/G", "num1"), "carries_per_game": C("Car/G", "num1"),
    "target_share": C("Target %", "pct", "Player targets ÷ team targets, in the games the player appeared in"),
    "target_share_l3": C("Target % (L3)", "pct", "Target share over the last three games played"),
    "target_share_l5": C("Target % (L5)", "pct"), "target_share_std": C("Target % (season)", "pct"),
    "target_share_trend": C("Target trend", "signed_pct", "Last-three target share minus season target share (needs 4+ games)"),
    "target_share_in_qb_games": C("Target %", "pct"),
    "carry_share": C("Carry %", "pct", "Player carries ÷ team carries"), "carry_share_l3": C("Carry % (L3)", "pct"),
    "carry_share_trend": C("Carry trend", "signed_pct"), "carry_share_std": C("Carry % (season)", "pct"),
    "air_yards_share": C("Air-yard %", "pct", "Share of the team's intended air yards (can exceed 100% or go negative on odd game scripts)"),
    "air_yards_share_l3": C("Air-yard % (L3)", "pct"),
    "avg_offense_snap_pct": C("Snap %", "pct", "Average share of offensive snaps played (participation, not routes)"),
    "offense_snap_pct": C("Snap %", "pct"), "snap_pct_l3": C("Snap % (L3)", "pct"), "snap_pct": C("Snap %", "pct"),
    "adot": C("aDOT", "num1", "Average depth of target (air yards per target)"), "catch_rate": C("Catch %", "pct"),
    "yards_per_target": C("Y/Tgt", "num1"), "yac_per_reception": C("YAC/Rec", "num1"), "yac_per_rec": C("YAC/Rec", "num1"),
    "yards_per_carry": C("Y/Car", "num1"), "completion_rate": C("Comp %", "pct"), "yards_per_attempt": C("Y/Att", "num1"),
    "dropbacks_excl_scrambles": C("Dropbacks", "int", "Pass attempts + sacks (scrambles need play-by-play)"),
    "fg_att": C("FGA", "int"), "fg_made": C("FGM", "int"), "fg_pct": C("FG %", "pct"), "fg_made_under_40": C("FG <40", "int"),
    "fg_made_40_49": C("FG 40-49", "int"), "fg_made_50p": C("FG 50+", "int"), "fg_long": C("Long", "int"), "pat_att": C("XPA", "int"), "pat_made": C("XPM", "int"),
    "nflverse_ppr_per_game": C("PPR PPG", "num1"), "points_current_scoring_per_game": C("PPG", "num1"),
    # ---- matchup context
    "opp_rank_std": C("Opp rank", "int", "Where the next opponent ranks in points allowed to this position this season: 1 = allows the most (best matchup), 32 = the fewest. Reference league's scoring, the same for every league"),
    "opp_rank_l4": C("Opp rank (L4)", "int", "Same rank over the opponent's last four games"),
    "opp_points_allowed_pg_std": C("Opp pts allowed/G", "num1", "Points the next opponent has allowed to this position per game this season, reference league's scoring"), "kickoff_at": C("Kickoff", "dt"),
    "points_allowed_per_game_std": C("Pts allowed/G", "num1", "Points allowed to the position per game this season, reference league's scoring"),
    "points_allowed_per_game_l4": C("Pts allowed/G (L4)", "num1"), "rank_std": C("Rank", "int", "1 = allows the most points to the position"),
    "rank_l4": C("Rank (L4)", "int"),
    "completion_pct_allowed": C("Comp % allowed", "pct"), "yards_allowed": C("Yds allowed", "int"),
    "yards_per_target_allowed": C("Y/Tgt allowed", "num1"), "tds_allowed": C("TD allowed", "int"), "interceptions": C("INT", "int"),
    "avg_passer_rating_allowed_when_targeted": C("Rating allowed", "num1", "Average passer rating on throws at this defender (lower = better coverage)"),
    "adot_allowed": C("aDOT allowed", "num1"), "missed_tackles": C("Missed tackles", "int"),
    # ---- league
    "standing": C("Rank", "int"), "wins": C("W", "int"), "losses": C("L", "int"), "ties": C("T", "int"),
    "sleeper_wins": C("Sleeper W", "int"), "sleeper_losses": C("Sleeper L", "int"),
    "points_for": C("PF", "num1"), "points_against": C("PA", "num1"), "avg_points": C("Avg", "num1"), "stddev_points": C("Std dev", "num1"),
    "best_week": C("Best week", "num1"), "worst_week": C("Worst week", "num1"),
    "all_play_win_pct": C("All-play %", "pct", "Win rate if the roster had played every other roster every week"),
    "all_play_wins": C("All-play W", "int"), "all_play_losses": C("All-play L", "int"), "all_play_ties": C("All-play T", "int"),
    "all_play_rank": C("All-play rank", "int"), "expected_wins": C("Expected W", "num2", "Games × all-play win rate"),
    "luck_wins": C("Luck", "signed1", "Actual wins minus expected wins. Positive = the schedule has been kind"),
    "top_half_weeks": C("Top-half weeks", "int"), "avg_points_rank": C("Avg weekly rank", "num1"), "week_points_rank": C("Weekly rank", "int"),
    "week_median_others": C("Median of others", "num1"), "median_of_others": C("Median of others", "num1"),
    "avg_bench_points_left": C("Bench pts left/wk", "num1", "Average points per week the roster left on its bench"),
    "total_bench_points_left": C("Bench pts left", "num1"), "avg_lineup_efficiency": C("Lineup eff.", "pct"),
    "weeks_left_10_plus": C("Weeks left 10+", "int", "Weeks with at least 10 points left on the bench"),
    "waiver_adds": C("Waiver adds", "int"), "free_agent_adds": C("FA adds", "int"), "trades": C("Trades", "int"),
    "failed_waiver_claims": C("Failed claims", "int"), "faab_spent": C("FAAB spent", "int"), "sleeper_waiver_budget_used": C("FAAB used (Sleeper)", "int"),
    "kicker_adds": C("K adds", "int"), "defense_adds": C("DEF adds", "int"),
    "n_qb": C("QB", "int"), "n_rb": C("RB", "int"), "n_wr": C("WR", "int"), "n_te": C("TE", "int"), "n_k": C("K", "int"), "n_def": C("DEF", "int"), "n_ir": C("IR", "int"),
    "matchup_id": C("Matchup", "int"), "result": C("Result"), "week_type": C("Type"), "margin": C("Margin", "signed1"), "opponent_points": C("Opp points", "num1"),
    "starters_counted": C("Starters", "int"), "optimal_slots_filled": C("Slots", "int"),
    "starter_ppg": C("Starter PPG", "num1", "Sum of season PPG over the players who would start at this position"),
    "league_median_starter_ppg": C("League median", "num1"), "starter_ppg_vs_median": C("vs median", "signed1"),
    "position_rank": C("Rank", "int", "1 = strongest in the league at this position"), "best_bench_ppg": C("Best bench PPG", "num1"),
    "top_players": C("Top players"), "players": C("Rostered", "int"), "starter_avg_ppg": C("Avg starter PPG", "num1"), "bench_ppg": C("Bench PPG", "num1"),
    "you_vs_median": C("You vs median", "signed1"), "partner_vs_median": C("Partner vs median", "signed1"), "partner_best_bench_ppg": C("Partner best bench PPG", "num1"),
    "draft_round": C("Round", "int"), "draft_pick": C("Pick", "int"), "pick_no": C("Pick", "int"), "round": C("Round", "int"),
    "position_rank_std": C("Pos rank (pts)", "int", "Rank among all NFL players at the position by season points"),
    "position_rank_ppg": C("Pos rank (PPG)", "int"), "position_rank_by_pick": C("Pos rank by pick", "int"), "position_rank_by_points": C("Pos rank by pts", "int"),
    "drafted_team": C("NFL team at draft"), "nfl_reg_games_played": C("GP", "int"), "nfl_reg_points_current_scoring": C("Season pts", "num1", "Regular-season fantasy points under this league's current scoring"),
    "points_started_for_any_roster": C("Pts while started", "num1"), "points_rostered_any": C("Pts while rostered", "num1"),
    "transaction_type": C("Type"), "action": C("Add/Drop"), "waiver_bid": C("Bid", "int"), "created_at": C("When", "dt"), "status": C("Status"),
    "slot": C("Slot"), "week_avg": C("Week avg K", "num1"), "week_avg_started_k": C("Week avg K", "num1"), "week_rank": C("Rank", "int"),
    "weeks_started_k": C("Weeks", "int"), "common_weeks": C("Common weeks", "int", "Weeks in which every roster started a kicker"),
    "total_points_common_weeks": C("Pts (common)", "num1"), "avg_points_common_weeks": C("Avg (common)", "num1"),
    "stddev_points_common_weeks": C("Std dev", "num1"), "avg_points_vs_week_avg": C("vs week avg", "signed1"),
    "distinct_kickers_started": C("Kickers used", "int"), "kicker_changes": C("Changes", "int"), "kicker_acquisitions": C("Acquired", "int"),
    "rank_common_weeks": C("Rank", "int"), "total_points": C("Points", "num1"),
    "game_date": C("Date", "date"), "went_to_overtime": C("OT", "bool", yes="OT", no=""), "starting_qb": C("Starting QB"),
    "window": C("Window"), "game_no": C("Game #", "int"), "first_week": C("First wk", "int"), "last_week": C("Last wk", "int"),
    "team_count": C("Teams", "int"), "games_l3": C("G (L3)", "int"), "games_l5": C("G (L5)", "int"),
    "targets_l3": C("Tgt (L3)", "int"), "team_targets_l3": C("Team tgt (L3)", "int"), "targets_l5": C("Tgt (L5)", "int"), "team_targets_l5": C("Team tgt (L5)", "int"),
    "carries_l3": C("Car (L3)", "int"), "points_per_game_std": C("PPG (season)", "num1"),
    # ---- trends
    "tags": C("Trend", help="Metrics moving beyond the player's own week-to-week noise over his last three games (strongest first)"),
    "momentum": C("Momentum", "signed1", "Average trend strength across opportunity metrics (targets, snaps, carries, air yards, expected points). +1 or more = role growing; −1 or less = shrinking"),
    "opportunity_trend": C("Opportunity", help="rising / steady / falling, from momentum"),
    "metric_label": C("Metric"), "value_l3": C("Last 3", "num2"), "value_prior": C("Before that", "num2"), "value_season": C("Season", "num2"),
    "value_latest": C("Latest game", "num2"),
    "change": C("Change", "signed1", "Last three games minus the games before them"),
    "change_vs_minimum": C("Change vs minimum", "signed1", "Change divided by the metric's practical minimum (3 pts target share, 5 pts snap/carry share, 2 expected points): 2.0 = twice the bar. Lets shares and points be compared"),
    "z": C("Strength", "signed1", "Change in units of the player's own game-to-game noise. ±1 = worth noticing, ±2 = clear"),
    "slope_per_game": C("Slope / game", "signed1", "Least-squares trend per game over the season"),
    "direction": C("Direction"), "confidence": C("Confidence"), "games_with_metric": C("G", "int"),
    "n_up": C("# up", "int"), "n_down": C("# down", "int"),
    "target_share_change": C("Target % change", "signed_pct"), "target_share_z": C("Target strength", "signed1"),
    "snap_share_l3": C("Snap % (L3)", "pct"), "snap_share_change": C("Snap % change", "signed_pct"), "snap_share_z": C("Snap strength", "signed1"),
    "carry_share_change": C("Carry % change", "signed_pct"), "carry_share_z": C("Carry strength", "signed1"),
    "air_yards_share_change": C("Air-yard % change", "signed_pct"), "adot_change": C("aDOT change", "signed1"),
    "expected_points_l3": C("xPPG (L3)", "num1"), "expected_points_change": C("xPPG change", "signed1"), "expected_points_z": C("xPPG strength", "signed1"),
    "points_l3": C("PPG (L3)", "num1"), "points_change": C("PPG change", "signed1"),
    "allowed_l3": C("Allowed/G (L3)", "num1"), "allowed_prior": C("Allowed/G before", "num1"), "allowed_season": C("Allowed/G season", "num1"),
    "latest_week": C("Through wk", "int"),
    # ---- Phase 2: play-by-play, first reads, routes proxy, context
    "first_read_targets": C("1st-read tgt", "int", "Targets thrown to this player as the quarterback's first read (FTN charting, 2022+)"),
    "team_first_read_targets": C("Team 1st-read tgt", "int", "The team's first-read targets in the same games"),
    "first_read_target_share": C("1st-read share", "pct", "Player first-read targets ÷ team first-read targets over the same games. Where the QB looks first — a role signal that target share alone hides"),
    "first_read_share": C("1st-read share", "pct", "Player first-read targets ÷ team first-read targets over the same games"),
    "first_read_share_l3": C("1st-read % (L3)", "pct", "First-read target share over the last three games"),
    "first_read_share_std": C("1st-read % (season)", "pct", "First-read target share, season to date"),
    "first_read_rate_of_targets": C("1st read of own tgt", "pct", "Share of this player's charted targets that were first reads (a different question from first-read share)"),
    "designed_targets": C("Designed tgt", "int", "Targets on designed throws (screens, many RPOs) — kept separate from progression reads"),
    "designed_rate_of_targets": C("Designed of own tgt", "pct", "Share of this player's charted targets that were designed throws"),
    "checkdown_targets": C("Checkdown tgt", "int"), "later_read_targets": C("2nd+ read tgt", "int"), "scramble_drill_targets": C("Scramble-drill tgt", "int"),
    "charted_targets": C("Charted tgt", "int", "Targets that carry a read code. Coverage is not 100%; missing is never assumed to be a first read"),
    "charting_coverage": C("Charting coverage", "pct", "Share of the team's targets that carry a read code in these games. Treat rates built on low coverage with care"),
    "routes_proxy": C("Routes (proxy)", "int", "Dropbacks the player was on the field for (NFL participation data). A proxy: presence is not proof a route was run, so it runs ~10-15% above charted route counts"),
    "routes_proxy_per_game": C("Routes/G (proxy)", "num1"),
    "route_participation": C("Route %", "pct", "Routes proxy ÷ team dropbacks with participation data: how often the player is on the field when the QB drops back"),
    "route_participation_l3": C("Route % (L3)", "pct"),
    "tprr_proxy": C("TPRR (proxy)", "pct", "Targets per route run on the proxy denominator — a lower bound on the true rate. Earning targets when on the field is the stickiest receiver skill"),
    "yprr_proxy": C("YPRR (proxy)", "num2", "Receiving yards per route run on the proxy denominator (lower bound)"),
    "routes": C("Routes", "int", "Route count from a licensed provider file (league-lab import-routes)"), "routes_provider": C("Routes source"),
    "targets_per_route_run": C("TPRR", "pct", "Targets per route run (licensed routes)"), "yards_per_route_run": C("YPRR", "num2", "Yards per route run (licensed routes)"),
    "tprr": C("TPRR", "pct"), "yprr": C("YPRR", "num2"),
    "team_dropbacks": C("Team dropbacks", "int", "Pass attempts + sacks + scrambles (no spikes, kneels or two-point tries)"),
    "team_dropbacks_with_participation": C("Team dropbacks (part.)", "int"),
    "dropbacks": C("Dropbacks", "int", "Pass attempts + sacks + scrambles"), "dropbacks_per_game": C("Dropbacks/G", "num1"),
    "scrambles": C("Scrambles", "int"), "sacks_taken": C("Sacks", "int"),
    "dropback_rate": C("Dropback %", "pct", "Dropbacks ÷ offensive plays"),
    "red_zone_targets": C("RZ tgt", "int", "Targets inside the 20"), "red_zone_carries": C("RZ carries", "int"),
    "red_zone_target_share": C("RZ target %", "pct", "Red-zone targets ÷ team red-zone targets, same games"),
    "red_zone_carry_share": C("RZ carry %", "pct"),
    "inside_10_targets": C("Inside-10 tgt", "int"), "inside_10_carries": C("Inside-10 carries", "int"), "inside_5_carries": C("Inside-5 carries", "int"),
    "deep_targets": C("Deep tgt", "int", "Targets with 20+ air yards"),
    "drops": C("Drops", "int", "FTN-charted drops"), "catchable_targets": C("Catchable tgt", "int"), "contested_targets": C("Contested tgt", "int"),
    "context_type": C("Split"), "bucket": C("Situation"),
    "air_yards": C("Air yds", "int"),
    # ---- rankings
    "rank_pos": C("#", "int", "Projected rank at the position this week (Out / Doubtful / IR excluded)"),
    "actual_rank_pos": C("Actual rank", "int", "Where the player actually finished at the position that week"),
    "proj_points": C("Proj", "num1", "Projected points in this league's scoring = intercept + form + usage + matchup + Vegas + home"),
    "c_form": C("Form", "signed1", "Expected points (L5), season / last-3 PPG and last season, weighted; last season fades out over six games"),
    "c_usage": C("Usage", "signed1", "Snap share and whether the last-3 target/carry share sits above the season share (a hot L3 share partly reverts, so its weight is negative)"),
    "c_matchup": C("Matchup", "signed1", "Opponent's points allowed per game to this position vs the league average, as of the games played so far"),
    "c_vegas": C("Vegas", "signed1", "Implied team total from the closing line: (total ± spread) / 2"),
    "c_home": C("Home", "signed1"),
    "xppg_l5": C("xPPG (L5)", "num1", "Expected points per game over the last five games (opportunity)"),
    "ppg_l3": C("PPG (L3)", "num1"), "prev_ppg": C("Prev PPG", "num1", "Last season's points per game"),
    "games_to_date": C("G so far", "int", "Games played this season before this week"),
    "opp_allowed_std": C("Opp allows", "num1", "Points per game the opponent has allowed to this position so far"),
    "league_allowed_avg": C("League avg", "num1", "League-wide points allowed per game to this position, as of the same point"),
    "implied_team_total": C("Implied total", "num1", "Vegas-implied team points"),
    "report_status": C("Injury", help="Report status for the week (Out / Doubtful excluded from the rank; Questionable stays in)"),
    # ---- projection v2
    "p10": C("Floor (P10)", "num1", "10th percentile of this league's points: one week in ten lands below"),
    "p50": C("Median (P50)", "num1", "Median of this league's points: as likely above as below"),
    "p90": C("Ceiling (P90)", "num1", "90th percentile: one week in ten lands above"),
    "interval_width": C("Range", "num1", "P90 − P10 in points: how uncertain the week is"),
    "proj_targets": C("Tgt", "num1", "Projected targets"), "proj_receptions": C("Rec", "num1", "Projected receptions"),
    "proj_receiving_yards": C("Rec yds", "num1", "Projected receiving yards"), "proj_receiving_tds": C("Rec TD", "num2", "Projected receiving touchdowns (expected count)"),
    "proj_carries": C("Car", "num1", "Projected carries"), "proj_rushing_yards": C("Rush yds", "num1", "Projected rushing yards"),
    "proj_rushing_tds": C("Rush TD", "num2", "Projected rushing touchdowns (expected count)"),
    "proj_attempts": C("Att", "num1", "Projected pass attempts"), "proj_passing_yards": C("Pass yds", "num1", "Projected passing yards"),
    "proj_passing_tds": C("Pass TD", "num2", "Projected passing touchdowns (expected count)"), "proj_passing_interceptions": C("INT", "num2", "Projected interceptions (expected count)"),
    "proj_fumbles_lost": C("Fum lost", "num2"),
    "actual_inside_interval": C("In range", "bool", "Did the actual land inside P10–P90?", yes="yes", no="no"),
    "coverage_80": C("Coverage", "pct", "Share of actual outcomes that landed inside P10–P90 (target 80%)"),
    "league_name": C("League"), "train_seasons": C("Trained on"), "model_version": C("Model"),
    "scorer_label": C("Ranking"), "weeks": C("Weeks", "int"), "top_n": C("N", "int"),
    "spearman": C("Spearman", "num2", "Rank correlation between the ranking and actual points, averaged over weeks; 1 = perfect, 0 = coin flip"),
    "hit_rate": C("Top-N hit rate", "pct", "Share of the actual top-N scorers the ranking's top-N caught"),
    "mae": C("MAE", "num2", "Mean absolute error in points"),
    "top_n_picked_ppg": C("Top-N picked PPG", "num1", "Actual PPG of the players the ranking put in its top-N"),
    "top_n_ceiling_ppg": C("Top-N ceiling PPG", "num1", "Actual PPG of the true top-N that week (perfect foresight)"),
    # ---- U-11 waiver shortlist
    "proj_v2": C("Proj (v2)", "num1", "Projection v2 for the next NFL week in this league's scoring (the Rankings page's board). Blank = no projection: kickers, a bye, practice squad, cut or retired"),
    "claim_week": C("This week vs your starter", help="His v2 projection for next week against your weakest projected starter at the position (N-th best of N starting slots; superflex counts as a QB slot, FLEX slots are left out; Out / Doubtful / IR don't start)"),
    "claim_season": C("Season vs your bench", help="His PPG this season against the best PPG on your bench at the position (bench = your players beyond the top N by PPG; IR slot left out)"),
    "compared_with": C("Compared with", help="Your players behind the comparison: the weakest projected starter at the position and the best bench player by PPG"),
    # ---- M-06 drift
    "weeks_scored": C("Weeks scored", "int", "Complete weeks of this season the live board has been scored on (a week counts once its last game is in)"),
    "backtest_spearman": C("Spearman · backtest", "num2", "The same rank correlation on the walk-forward backtest's held-out seasons (v2 projection, this league's scoring)"),
    "backtest_coverage_80": C("Coverage · backtest", "pct", "Share of actuals inside P10–P90 on the walk-forward backtest's held-out seasons (target 80%)"),
    # ---- B1 lineups
    "slot_type": C("Slot type", help="The league's slot: QB, RB, WR, TE, FLEX (RB/WR/TE), SUPER_FLEX (QB/RB/WR/TE), K, DEF"),
    "slot_order": C("#", "int", "Position of the slot in the league's lineup"),
    "player_value": C("Value", "num1", "The points the lineup counts him for: projection v2 this week in this league's scoring; K = season points per game in this league; DEF = points per game Sleeper scored for it in this league"),
    "value_source": C("Value from", help="proj_points = projection v2 · season_ppg = the K's points per game this season in this league's scoring · observed_ppg = points per game Sleeper scored this season (DEF, or a K without an NFL id)"),
    "lineup_margin": C("Margin", "num1", "What the lineup loses without him: best lineup total minus the best total re-solved from the rest of the roster. Small = a close call; 0 = an equal option sits on the bench. Blank for a locked player"),
    "is_weakest_slot": C("Closest call", "bool", "The starter with the smallest margin: the lineup decision that matters most this week", yes="closest call", no=""),
    "is_empty_slot": C("Empty", "bool", "Nobody on the roster can fill this slot this week (bye, injury, no value yet)", yes="EMPTY", no=""),
    "is_locked": C("Locked", "bool", "His game has kicked off: he stays where Sleeper has him", yes="locked", no=""),
    "is_questionable": C("Q", "bool", "Questionable on the injury report: counted as playing", yes="Q", no=""),
    "lineup_value": C("Lineup", "num1", "Total value of the best legal lineup this roster can start (every slot solved together, FLEX and superflex included)"),
    "bench_value": C("Bench lineup", "num1", "The best legal lineup the bench alone could field if every starter sat: depth, in points"),
    "weakest_slot": C("Closest-call slot", help="The slot whose starter has the smallest margin"),
    "weakest_margin": C("Its margin", "num1", "Points the lineup would lose by benching the closest-call starter for the best alternative"),
    "empty_slots": C("Empty slots", help="Slots nobody on the roster can fill this week"),
    "realised_optimal": C("Best possible (actual)", "num1", "For a week Sleeper has scored: the best legal lineup this roster could have started at the points Sleeper counted (hindsight)"),
    # ---- B5 decision record
    "frozen_share": C("Kickoff board", "pct", "Share of the scored player-weeks whose projection is the board as published before that week's "
                                              "first kickoff (frozen since); the rest are refit values from a later run of the same model"),
}


# Columns hidden in "Essentials" mode (sidebar detail toggle): denominators, statistics of a
# statistic, coverage/provenance fields and fine-grained counts. Everything is one click away.
ADVANCED_PATTERNS = ("team_", "_z", "slope_per_game", "confidence", "charted_targets", "charting_coverage", "games_with_",
                     "nflverse_", "denominator", "c_intercept", "n_up", "n_down", "opp_games", "prev_games",
                     "asof_week", "later_read", "scramble_drill", "checkdown", "contested", "catchable", "inside_10", "inside_5",
                     "deep_targets", "two_point", "league_allowed_avg", "routes_provider", "points_current_scoring_league",
                     "value_prior", "value_latest", "change_vs_minimum", "practice_status", "spread_line", "total_line",
                     "first_read_rate_of_targets", "designed_rate", "designed_targets", "drops", "top_n_ceiling", "top_n_picked",
                     "games_l3", "targets_l3", "carries_l3", "week_avg", "yac_per", "receiving_air_yards", "air_yards")
ADVANCED_EXACT = {"opponent_points", "margin"}
ESSENTIAL_EXACT = {"team", "teams", "team_name", "nfl_team", "implied_team_total", "receptions", "team_dropbacks",
                   "red_zone_target_share", "red_zone_carry_share", "air_yards_share", "c_home"}


def is_advanced(column: str) -> bool:
    if column in ADVANCED_EXACT:
        return True
    if column in ESSENTIAL_EXACT:
        return False
    return any(pat in column for pat in ADVANCED_PATTERNS)


def detail_level() -> str:
    """'essentials' (default) or 'everything' - set by the sidebar toggle in setup()."""
    return st.session_state.get("detail_level", "essentials")


def _auto_kind(series: pd.Series) -> str:
    if pd.api.types.is_bool_dtype(series):
        return "bool"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "dt"
    if pd.api.types.is_integer_dtype(series):
        return "int"
    if pd.api.types.is_float_dtype(series):
        return "num1"
    return "text"


def _num(s: pd.Series) -> pd.Series:
    """Coerce to float64 (an all-None object column would otherwise render as the word None)."""
    return pd.to_numeric(s, errors="coerce").astype("float64")


def prepare(df: pd.DataFrame, cols: list[str] | None = None, overrides: dict[str, Col] | None = None):
    """Return (display_df, column_config) with readable labels and formats."""
    src = df[cols] if cols else df
    out = src.copy()
    config: dict = {}
    reg = {**COLUMNS, **(overrides or {})}
    for c in out.columns:
        spec = reg.get(c) or Col(c.replace("_", " ").capitalize(), "auto")
        kind = spec.kind if spec.kind != "auto" else _auto_kind(out[c])
        label, hlp = spec.label, spec.help or None
        if kind == "pct":
            out[c] = _num(out[c]) * 100
            config[c] = st.column_config.NumberColumn(label, help=hlp, format="%.1f%%")
        elif kind == "signed_pct":
            out[c] = _num(out[c]) * 100
            config[c] = st.column_config.NumberColumn(label, help=hlp, format="%+.1f%%")
        elif kind == "pct100":
            out[c] = _num(out[c])
            config[c] = st.column_config.NumberColumn(label, help=hlp, format="%.1f%%")
        elif kind == "num1":
            out[c] = _num(out[c])
            config[c] = st.column_config.NumberColumn(label, help=hlp, format="%.1f")
        elif kind == "num2":
            out[c] = _num(out[c])
            config[c] = st.column_config.NumberColumn(label, help=hlp, format="%.2f")
        elif kind == "signed1":
            out[c] = _num(out[c])
            config[c] = st.column_config.NumberColumn(label, help=hlp, format="%+.1f")
        elif kind == "int":
            out[c] = pd.to_numeric(out[c], errors="coerce").astype("Int64")
            config[c] = st.column_config.NumberColumn(label, help=hlp, format="%d")
        elif kind == "bool":
            out[c] = out[c].map(lambda v, y=spec.yes, n=spec.no: n if v is None or (isinstance(v, float) and pd.isna(v)) or not v else y)
            config[c] = st.column_config.TextColumn(label, help=hlp)
        elif kind == "dt":
            s = pd.to_datetime(out[c], errors="coerce", utc=True)
            out[c] = s.dt.tz_convert("America/New_York").dt.strftime("%a %b %-d, %-I:%M %p")
            config[c] = st.column_config.TextColumn(label, help=hlp)
        elif kind == "date":
            out[c] = pd.to_datetime(out[c], errors="coerce").dt.strftime("%Y-%m-%d")
            config[c] = st.column_config.TextColumn(label, help=hlp)
        else:
            out[c] = out[c].astype(object).where(out[c].notna(), "")
            config[c] = st.column_config.TextColumn(label, help=hlp)
    return out, config


def show(df: pd.DataFrame, cols: list[str] | None = None, height: int | None = None, overrides: dict[str, Col] | None = None,
         index: pd.Series | None = None) -> None:
    """Render a mart DataFrame as a readable table (labels, %, words instead of checkboxes)."""
    if df is None or df.empty:
        st.caption("Nothing to show yet.")
        return
    if detail_level() == "essentials":
        # a page's explicit override marks the column essential for that table
        keep = [c for c in (cols or list(df.columns)) if c in (overrides or {}) or not is_advanced(c)]
        cols = keep or cols
    out, config = prepare(df, cols, overrides)
    if index is not None:
        out.index = index
    kwargs = {"height": height} if height else {}
    # placeholder="": a missing value is an empty cell, not the word "None" (Streamlit's default)
    st.dataframe(out, column_config=config, hide_index=index is None, width="stretch", placeholder="", **kwargs)


def howto(*lines: str, title: str = "How to read this table") -> None:
    """A short, collapsible 'how to use this' next to a table."""
    with st.expander(title):
        st.markdown("\n".join(f"- {ln}" for ln in lines))


def glossary_rows() -> pd.DataFrame:
    rows = [(v.label, k, v.help) for k, v in COLUMNS.items() if v.help]
    df = pd.DataFrame(rows, columns=["Column", "Source field", "Meaning"]).sort_values(["Column", "Source field"])
    return df.drop_duplicates("Column", keep="first")
