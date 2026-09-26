"""Weekly data packs: the facts and tables behind a newsletter, as Markdown + CSV.

No prose is generated — the writer writes. Two packs:

* ``league_recap`` — league-facing facts for a given week (results, standings, luck, lineup
  decisions, top performers, moves, kickers).
* ``team_brief``  — one roster's private view (roster health, start/sit context, waiver targets,
  buy-low/sell-high, trade fits, keeper facts).

Everything is read from ``analytics`` marts with the read-only role, so the pack is exactly what
the explorer shows.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg

from .config import PROJECT_ROOT, get_settings


# ------------------------------------------------------------------------------ helpers
def _rows(conn: psycopg.Connection, sql: str, params: tuple = ()) -> tuple[list[str], list[tuple]]:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        cols = [d.name for d in cur.description]
        return cols, cur.fetchall()


def _fmt(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, bool):
        return "yes" if v else ""
    if isinstance(v, float):
        return f"{v:.2f}".rstrip("0").rstrip(".") if abs(v) < 1000 else f"{v:,.0f}"
    if hasattr(v, "quantize"):  # Decimal
        return _fmt(float(v))
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M")
    return str(v)


def md_table(cols: list[str], rows: list[tuple], limit: int | None = None) -> str:
    if not rows:
        return "_no rows_\n"
    body = rows[:limit] if limit else rows
    out = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for r in body:
        out.append("| " + " | ".join(_fmt(v).replace("|", "\\|") for v in r) + " |")
    if limit and len(rows) > limit:
        out.append(f"\n_{len(rows) - limit} more rows in the CSV_")
    return "\n".join(out) + "\n"


def write_csv(path: Path, cols: list[str], rows: list[tuple]) -> None:
    import csv

    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        w.writerows(rows)


class Pack:
    def __init__(self, out_dir: Path, title: str):
        self.out_dir = out_dir
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.sections: list[str] = [f"# {title}", f"_generated {datetime.now(UTC):%Y-%m-%d %H:%M} UTC · facts only, no prose_"]

    def add(self, heading: str, cols: list[str], rows: list[tuple], note: str | None = None, limit: int | None = 25,
            csv_name: str | None = None) -> None:
        self.sections.append(f"\n## {heading}\n")
        if note:
            self.sections.append(f"_{note}_\n")
        self.sections.append(md_table(cols, rows, limit))
        if csv_name and rows:
            write_csv(self.out_dir / f"{csv_name}.csv", cols, rows)

    def add_text(self, heading: str, lines: list[str]) -> None:
        self.sections.append(f"\n## {heading}\n")
        self.sections.extend(f"- {ln}" for ln in lines)
        self.sections.append("")

    def write(self, name: str) -> Path:
        path = self.out_dir / f"{name}.md"
        path.write_text("\n".join(self.sections))
        return path


# ------------------------------------------------------------------------------ league recap
def league_recap(conn: psycopg.Connection, league_id: str, week: int, out_dir: Path) -> Path:
    cols, rows = _rows(conn, "select league_name, season, playoff_week_start, last_scored_leg from analytics.dim_league_season where league_id = %s", (league_id,))
    league_name, season, playoff_start, last_scored = rows[0]
    pack = Pack(out_dir, f"{league_name} {season} — week {week} recap pack")

    c, r = _rows(conn, """
        select m.week, d.team_name, m.points, o.team_name as opponent, m.opponent_points, m.result, m.margin
        from analytics.fct_league_matchup m
        join analytics.dim_league_member d using (league_id, roster_id)
        left join analytics.dim_league_member o on o.league_id = m.league_id and o.roster_id = m.opponent_roster_id
        where m.league_id = %s and m.week = %s and m.is_scored order by m.matchup_id, m.points desc""", (league_id, week))
    pack.add(f"Week {week} results", c, r, csv_name="results")
    if r:
        hi = max(r, key=lambda x: x[2])
        lo = min(r, key=lambda x: x[2])
        closest = min((x for x in r if x[6] is not None and x[6] >= 0), key=lambda x: x[6], default=None)
        blow = max((x for x in r if x[6] is not None), key=lambda x: x[6], default=None)
        facts = [f"High score: {hi[1]} {_fmt(hi[2])}", f"Low score: {lo[1]} {_fmt(lo[2])}"]
        if closest:
            facts.append(f"Closest: {closest[1]} over {closest[3]} by {_fmt(closest[6])}")
        if blow:
            facts.append(f"Biggest margin: {blow[1]} over {blow[3]} by {_fmt(blow[6])}")
        pack.add_text("Week facts", facts)

    c, r = _rows(conn, """
        select week_points_rank as pts_rank, team_name, points, all_play_wins, all_play_losses, result,
               round(week_median_others::numeric, 2) as median_of_others
        from analytics.mart_league_all_play_week where league_id = %s and week = %s order by week_points_rank""", (league_id, week))
    pack.add("Who actually scored (all-play this week)", c, r, note="all_play_wins = how many rosters you would have beaten this week", csv_name="all_play_week")

    c, r = _rows(conn, """
        select standing, team_name, wins, losses, points_for, points_against, avg_points, lineup_efficiency
        from analytics.mart_league_standings where league_id = %s order by standing""", (league_id,))
    pack.add("Standings", c, r, csv_name="standings")

    c, r = _rows(conn, """
        select all_play_rank, team_name, wins, losses, all_play_wins, all_play_losses, all_play_win_pct, expected_wins, luck_wins, top_half_weeks
        from analytics.mart_league_all_play where league_id = %s order by all_play_rank""", (league_id,))
    pack.add("Season all-play and luck", c, r, note="luck_wins = actual wins minus all-play expected wins", csv_name="all_play_season")

    c, r = _rows(conn, """
        select team_name, points_started, points_optimal, bench_points_left, lineup_efficiency
        from analytics.mart_league_optimal_lineup where league_id = %s and week = %s order by bench_points_left desc""", (league_id, week))
    pack.add("Lineup decisions this week (bench points left)", c, r, csv_name="lineups")

    c, r = _rows(conn, """
        select l.slot, l.player_name, l.position, l.nfl_team, d.team_name, l.points_observed as points
        from analytics.league_player_week l join analytics.dim_league_member d using (league_id, roster_id)
        where l.league_id = %s and l.week = %s and l.is_starter order by l.points_observed desc limit 15""", (league_id, week))
    pack.add("Top started players", c, r, csv_name="top_started")

    c, r = _rows(conn, """
        select l.player_name, l.position, l.nfl_team, d.team_name, l.points_observed as points
        from analytics.league_player_week l join analytics.dim_league_member d using (league_id, roster_id)
        where l.league_id = %s and l.week = %s and not l.is_starter order by l.points_observed desc limit 10""", (league_id, week))
    pack.add("Best players left on benches", c, r, csv_name="bench_stars")

    c, r = _rows(conn, """
        select l.player_name, l.position, l.nfl_team, d.team_name, l.slot, l.points_observed as points
        from analytics.league_player_week l join analytics.dim_league_member d using (league_id, roster_id)
        where l.league_id = %s and l.week = %s and l.is_starter and l.position in ('QB','RB','WR','TE') order by l.points_observed asc limit 10""", (league_id, week))
    pack.add("Worst starts (skill positions)", c, r, csv_name="worst_starts")

    c, r = _rows(conn, """
        select position, player_name, nfl_team, sum(points_observed) as points_this_week
        from (select distinct l.position, l.player_name, l.nfl_team, l.sleeper_player_id, l.points_observed
              from analytics.league_player_week l where l.league_id = %s and l.week = %s and l.position in ('QB','RB','WR','TE','K','DEF')) x
        group by 1, 2, 3 order by position, points_this_week desc""", (league_id, week))
    top_by_pos: dict[str, list[tuple]] = {}
    for row in r:
        top_by_pos.setdefault(row[0], []).append(row)
    pack.add("Top 3 by position (rostered players)", c, [x for pos in ("QB", "RB", "WR", "TE", "K", "DEF") for x in top_by_pos.get(pos, [])[:3]], limit=None)

    c, r = _rows(conn, """
        select week, transaction_type, action, team_name, player_name, position, waiver_bid
        from analytics.mart_league_transactions where league_id = %s and week = %s and status = 'complete'
        order by transaction_type, team_name, action""", (league_id, week))
    pack.add("Moves this week", c, r, limit=60, csv_name="moves")

    c, r = _rows(conn, """
        select week_rank as rank, team_name, kicker_name, nfl_team, points, round(week_avg_started_k::numeric, 2) as week_avg, changed_kicker
        from analytics.mart_league_kicker_week where league_id = %s and week = %s order by week_rank""", (league_id, week))
    pack.add("Kicker corner", c, r, csv_name="kickers")

    # movers: role changes over the last three games, league-wide (rostered + free agents)
    c, r = _rows(conn, """
        select t.player_name, t.position, t.team as nfl_team, coalesce(a.team_name, 'free agent') as rostered_by, t.games,
               t.tags as trend, round(t.momentum::numeric, 2) as momentum,
               round((t.target_share_change * 100)::numeric, 1) as target_share_change_pct,
               round((t.snap_share_change * 100)::numeric, 1) as snap_share_change_pct,
               round(t.expected_points_change::numeric, 2) as expected_points_change
        from analytics.mart_player_trend_tags t
        left join analytics.mart_league_roster_membership a on a.gsis_id = t.gsis_id and a.league_id = %s
        where t.season = %s and t.opportunity_trend = 'rising' order by t.momentum desc limit 15""", (league_id, season))
    pack.add("Movers — opportunity rising (last 3 games vs before)", c, r,
             note="momentum = average strength across usage metrics (targets, snaps, carries, air yards, expected points); ±1 clears week-to-week noise, ±2 is a clear change. Needs 4 games.",
             csv_name="movers_up")
    c, r = _rows(conn, """
        select t.player_name, t.position, t.team as nfl_team, coalesce(a.team_name, 'free agent') as rostered_by, t.games,
               t.tags as trend, round(t.momentum::numeric, 2) as momentum,
               round((t.target_share_change * 100)::numeric, 1) as target_share_change_pct,
               round((t.snap_share_change * 100)::numeric, 1) as snap_share_change_pct,
               round(t.expected_points_change::numeric, 2) as expected_points_change
        from analytics.mart_player_trend_tags t
        left join analytics.mart_league_roster_membership a on a.gsis_id = t.gsis_id and a.league_id = %s
        where t.season = %s and t.opportunity_trend = 'falling' order by t.momentum asc limit 15""", (league_id, season))
    pack.add("Movers — opportunity falling", c, r, csv_name="movers_down")

    c, r = _rows(conn, """
        select defense, position, games, round(allowed_prior::numeric, 1) as allowed_before, round(allowed_l3::numeric, 1) as allowed_last3,
               round(change::numeric, 1) as change, round(z::numeric, 2) as strength, direction
        from analytics.mart_defense_trends where season = %s and direction in ('softer','stiffer') order by abs(z) desc limit 12""", (season,))
    pack.add("Defenses getting softer or stiffer", c, r, note="points allowed to the position, last 3 games vs before; softer = giving up more lately", csv_name="defense_trends")

    return pack.write(f"league_recap_week_{week:02d}")


# ------------------------------------------------------------------------------ team brief
def team_brief(conn: psycopg.Connection, league_id: str, roster_id: int, out_dir: Path) -> Path:
    cols, rows = _rows(conn, "select team_name, manager_name from analytics.dim_league_member where league_id = %s and roster_id = %s", (league_id, roster_id))
    team_name, manager = rows[0]
    c, r = _rows(conn, "select season, last_completed_week, next_week from analytics.mart_nfl_calendar")
    season, last_wk, next_wk = r[0]
    pack = Pack(out_dir, f"{team_name} — private brief (NFL week {next_wk})")

    c, r = _rows(conn, """
        select wins, losses, standing, all_play_win_pct, expected_wins, luck_wins, avg_bench_points_left, faab_spent, waiver_adds, trades
        from analytics.mart_league_manager_profile where league_id = %s and roster_id = %s""", (league_id, roster_id))
    pack.add("Where you stand", c, r)

    c, r = _rows(conn, """
        select player_name, position, nfl_team, is_current_starter as starter, injury_status, opponent, is_bye, opp_rank_std, opp_rank_l4,
               ppg_std, points_per_game_l3, expected_per_game, diff_per_game, target_share_l3, first_read_share_l3, carry_share_l3, snap_pct_l3
        from analytics.mart_player_availability where league_id = %s and rostered_by_roster_id = %s
        order by array_position(array['QB','RB','WR','TE','K'], position), coalesce(expected_per_game, ppg_std) desc nulls last""", (league_id, roster_id))
    pack.add(f"Roster and week {next_wk} matchups", c, r, note="opp_rank 1 = opponent allows the most points to the position", limit=None, csv_name="roster")

    c, r = _rows(conn, """
        select k.position, k.rank_pos as pos_rank, k.player_name, k.team, k.opponent, k.report_status, k.proj_points, k.c_form, k.c_usage, k.c_matchup, k.c_vegas,
               k.implied_team_total, k.xppg_l5, k.ppg_std, a.is_current_starter as starter
        from analytics.mart_player_week_rankings k
        join analytics.mart_player_availability a on a.gsis_id = k.gsis_id and a.league_id = %s
        where k.season = %s and k.week = %s and a.rostered_by_roster_id = %s
        order by array_position(array['QB','RB','WR','TE'], k.position), k.proj_points desc nulls last""", (league_id, season, next_wk, roster_id))
    pack.add(f"Week {next_wk} projections for your roster (baseline)", c, r,
             note="proj = form + usage + matchup + Vegas + home (+ intercept); pos_rank among all rankable players at the position. See the Rankings page backtest before trusting a single rank",
             limit=None, csv_name="projections")

    c, r = _rows(conn, """
        select k.position, k.rank_pos as pos_rank, k.player_name, k.team, k.opponent, k.report_status, k.proj_points, k.c_form, k.c_matchup, k.c_vegas, k.xppg_l5, k.ppg_std
        from analytics.mart_player_week_rankings k
        join analytics.mart_player_availability a on a.gsis_id = k.gsis_id and a.league_id = %s
        where k.season = %s and k.week = %s and a.is_free_agent and k.is_rankable and k.position in ('QB','RB','WR','TE')
        order by k.proj_points desc nulls last limit 20""", (league_id, season, next_wk))
    pack.add(f"Best projected free agents for week {next_wk}", c, r, csv_name="projections_free_agents")

    c, r = _rows(conn, """
        select a.player_name, a.position, a.nfl_team, t.games, t.tags as trend, round(t.momentum::numeric, 2) as momentum, t.opportunity_trend,
               round((t.target_share_change * 100)::numeric, 1) as target_share_change_pct,
               round((t.snap_share_change * 100)::numeric, 1) as snap_share_change_pct,
               round((t.carry_share_change * 100)::numeric, 1) as carry_share_change_pct,
               round(t.expected_points_change::numeric, 2) as expected_points_change, round(t.points_change::numeric, 2) as points_change
        from analytics.mart_player_availability a
        join analytics.mart_player_trend_tags t on t.gsis_id = a.gsis_id and t.season = %s
        where a.league_id = %s and a.rostered_by_roster_id = %s and a.position in ('QB','RB','WR','TE')
        order by t.momentum desc nulls last""", (season, league_id, roster_id))
    pack.add("Your roster's trends (last 3 games vs before)", c, r,
             note="trend lists which metrics moved beyond noise; momentum averages strength across usage metrics only. 'not enough games yet' before game 4.",
             limit=None, csv_name="roster_trends")

    c, r = _rows(conn, """
        select a.player_name, a.position, a.nfl_team, a.injury_status, t.games, t.tags as trend, round(t.momentum::numeric, 2) as momentum,
               a.target_share_l3, a.snap_pct_l3, a.expected_per_game, a.ppg_std, a.opponent, a.opp_rank_std
        from analytics.mart_player_availability a
        join analytics.mart_player_trend_tags t on t.gsis_id = a.gsis_id and t.season = %s
        where a.league_id = %s and a.is_free_agent and a.position in ('RB','WR','TE') and t.opportunity_trend = 'rising'
          and coalesce(a.injury_status,'') not in ('Out')
        order by t.momentum desc limit 15""", (season, league_id))
    pack.add("Free agents with rising opportunity", c, r, csv_name="waiver_targets_momentum")

    c, r = _rows(conn, """
        select player_name, position, nfl_team, injury_status, depth_rank, games_played, target_share_l3, target_share_trend, carry_share_l3,
               snap_pct_l3, expected_per_game, ppg_std, points_per_game_l3, diff_per_game, opponent, opp_rank_std
        from analytics.mart_player_availability
        where league_id = %s and is_free_agent and position in ('RB','WR','TE') and coalesce(games_played,0) >= 2
          and coalesce(injury_status,'') not in ('Out') and coalesce(roster_status,'') <> 'RES'
        order by coalesce(expected_per_game, 0) desc limit 20""", (league_id,))
    pack.add("Waiver targets — RB/WR/TE by expected points", c, r, csv_name="waiver_targets_skill")

    c, r = _rows(conn, """
        select player_name, position, nfl_team, injury_status, games_played, target_share_l3, target_share_trend, snap_pct_l3, expected_per_game, ppg_std, opponent, opp_rank_std
        from analytics.mart_player_availability
        where league_id = %s and is_free_agent and position in ('RB','WR','TE') and coalesce(games_played,0) >= 2
        order by target_share_trend desc nulls last limit 15""", (league_id,))
    pack.add("Waiver targets — rising target share (L3 vs season)", c, r,
             note="needs 4+ games to mean anything: before that the last-3 window is the whole season", csv_name="waiver_targets_trend")

    c, r = _rows(conn, """
        select player_name, position, nfl_team, injury_status, games_played, first_read_share_std, first_read_share_l3, target_share, target_share_l3,
               expected_per_game, ppg_std, opponent, opp_rank_std
        from analytics.mart_player_availability
        where league_id = %s and is_free_agent and position in ('RB','WR','TE') and coalesce(games_played,0) >= 2 and first_read_share_l3 is not null
        order by first_read_share_l3 desc limit 15""", (league_id,))
    pack.add("Waiver targets — first-read share (where the QB looks first, last 3)", c, r,
             note="first-read targets / team first-read targets from FTN charting; a rising first-read share with a flat target share is the earliest role signal", csv_name="waiver_targets_first_read")

    c, r = _rows(conn, """
        select player_name, position, nfl_team, games_played, expected_per_game, ppg_std, opponent, opp_rank_std, injury_status
        from analytics.mart_player_availability
        where league_id = %s and is_free_agent and position in ('QB','K') and coalesce(games_played,0) >= 1
        order by position, coalesce(expected_per_game, ppg_std) desc nulls last limit 12""", (league_id,))
    pack.add("Streaming options — QB and K", c, r, csv_name="waiver_targets_qb_k")

    c, r = _rows(conn, """
        select player_name, position, nfl_team, rostered_by_team, is_current_starter as their_starter, games_with_expected, ppg_std, expected_per_game, diff_per_game, target_share
        from analytics.mart_player_availability
        where league_id = %s and not is_free_agent and rostered_by_roster_id <> %s and coalesce(games_with_expected,0) >= 2 and position in ('QB','RB','WR','TE')
        order by diff_per_game asc limit 15""", (league_id, roster_id))
    pack.add("Buy-low targets on other rosters (production below opportunity)", c, r, csv_name="buy_low")

    c, r = _rows(conn, """
        select player_name, position, nfl_team, is_current_starter as starter, games_with_expected, ppg_std, expected_per_game, diff_per_game
        from analytics.mart_player_availability
        where league_id = %s and rostered_by_roster_id = %s and coalesce(games_with_expected,0) >= 2
        order by diff_per_game desc limit 8""", (league_id, roster_id))
    pack.add("Your sell-high candidates (production above opportunity)", c, r, csv_name="sell_high")

    c, r = _rows(conn, """
        select position, starter_ppg, league_median_starter_ppg, starter_ppg_vs_median, position_rank, best_bench_ppg, top_players
        from analytics.mart_league_positional_strength where league_id = %s and roster_id = %s
        order by array_position(array['QB','RB','WR','TE','K'], position)""", (league_id, roster_id))
    pack.add("Your positional strength", c, r)

    c, r = _rows(conn, """
        select p.team_name, p.position, p.starter_ppg_vs_median as partner_vs_median, p.best_bench_ppg as partner_best_bench,
               m.starter_ppg_vs_median as you_vs_median
        from analytics.mart_league_positional_strength p
        join analytics.mart_league_positional_strength m on m.league_id = p.league_id and m.position = p.position and m.roster_id = %s
        where p.league_id = %s and p.roster_id <> %s and p.starter_ppg_vs_median > 0 and m.starter_ppg_vs_median < 0
        order by p.starter_ppg_vs_median - m.starter_ppg_vs_median desc""", (roster_id, league_id, roster_id))
    pack.add("Trade fits — partners deep where you are thin", c, r, csv_name="trade_fits")

    c, r = _rows(conn, """
        select player_name, position, draft_round, draft_pick, undrafted_or_waiver, games_played, ppg_std, position_rank_std, expected_per_game
        from analytics.mart_league_keeper_candidates where league_id = %s and roster_id = %s order by ppg_std desc nulls last limit 10""", (league_id, roster_id))
    pack.add("Keeper facts", c, r)

    return pack.write(f"team_brief_{roster_id}")


def build_packs(league_id: str | None, week: int | None, roster_id: int | None, out_root: Path | None) -> list[Path]:
    s = get_settings()
    out: list[Path] = []
    with psycopg.connect(s.app_dsn(), autocommit=True) as conn:
        if league_id is None:
            _, rows = _rows(conn, "select league_id from analytics.dim_league_season where is_current_season order by league_name limit 1")
            if not rows:
                raise SystemExit("no current league season loaded")
            league_id = rows[0][0]
        _, rows = _rows(conn, "select league_name, season, last_scored_leg from analytics.dim_league_season where league_id = %s", (league_id,))
        league_name, season, last_scored = rows[0]
        week = week or int(last_scored or 1)
        slug = "".join(ch if ch.isalnum() else "_" for ch in f"{league_name}_{season}").strip("_").lower()
        out_dir = (out_root or PROJECT_ROOT / "reports") / slug / f"week_{week:02d}"
        out.append(league_recap(conn, league_id, week, out_dir))
        if roster_id is not None:
            out.append(team_brief(conn, league_id, roster_id, out_dir))
    return out
