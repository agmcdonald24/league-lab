"""Build the decision screens' fixtures (plan G4, Wave G): web/fixtures/{waivers,trades_evaluate,trades_partners,team,league}_*.json.

    PGPASSWORD=… uv run python web/fixtures/make_decision_fixtures.py          # DB=league_lab_g4 (the clone)

None of G2's routes exist when this runs, so every file is written FROM THE MARTS in the contract's shape (the brief's
"API contract", G2 — decisions): a route returns the mart's rows with the mart's column names, plus the sentences the
Streamlit page writes, plus `headshot_url`, `team` and `position` on every player row (dim_player).

* House leagues: Forever Unclean Dynasty roster 12 and League of Scrubs roster 2 (week 4 on the clone), every roster's
  Team Hub (the Trade Finder's partner picker reads the partner's roster from /api/team).
* Trades: the evaluator's numbers are league_lab.trades.evaluate on the board the Streamlit Trade Finder builds
  (mart_league_roster_horizon + ops.projections' market + the replacement level), so they equal the page's; the partner
  finder is league_lab.trades.partners (best package per team), filtered by the position you want.
* The Test League (9000000000000000001, fictional): League of Scrubs retold — its 10 rosters renamed to the Test
  League's teams (Scrubs roster 2 → Test roster 3, "Fixture Falcons"), `source: "sleeper"`, no draft (Sleeper's draft is
  "where known"). Its My Week fixture keeps its own made-up roster (F2); the decision screens show Scrubs roster 2's.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "app")]

from league_lab import trades as T  # noqa: E402
from league_lab.roster_value import RosterBoard  # noqa: E402

OUT = Path(__file__).resolve().parent
DB = os.environ.get("DB", "league_lab_g4")
DYN, SCRUBS, TEST = "1321941740235550720", "1389709692405551104", "9000000000000000001"
SEASON = 2026
MINE = {DYN: 12, SCRUBS: 2}
POSITIONS = ["QB", "RB", "WR", "TE"]

conn = psycopg.connect(f"host=localhost dbname={DB} user=postgres password={os.environ.get('PGPASSWORD', '')}", row_factory=dict_row)


def q(sql: str, params=()) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return [clean(r) for r in cur.fetchall()]


def clean(v):
    if isinstance(v, dict):
        return {k: clean(x) for k, x in v.items()}
    if isinstance(v, list | tuple):
        return [clean(x) for x in v]
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, float):
        return round(v, 4)
    if isinstance(v, datetime | date):
        return v.isoformat()
    return v


def save(name: str, data) -> None:
    (OUT / name).write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")


def f1(x) -> str:
    return f"{float(x):.1f}"


# ------------------------------------------------------------------ league facts
def league_info(lid: str) -> dict:
    r = q("""select league_id, league_name, season, roster_positions, league_type from analytics.dim_league_season
             where league_id = %s""", (lid,))
    return r[0]


def teams(lid: str) -> dict[int, dict]:
    rows = q("select roster_id, team_name, manager_name from analytics.mart_league_standings where league_id = %s", (lid,))
    return {int(r["roster_id"]): r for r in rows}


def heads(ids: list[str]) -> dict[str, dict]:
    ids = [i for i in ids if i]
    if not ids:
        return {}
    rows = q("""select gsis_id, headshot_url, latest_team as team, position from analytics.dim_player where gsis_id = any(%s)""", (ids,))
    return {r["gsis_id"]: r for r in rows}


def ros_rows(lid: str) -> dict[str, dict]:
    rows = q("""select player_key, gsis_id, ros_points, ros_games, ros_p10, ros_p90, ros_rank_pos, playoff_points, from_week, last_week
                from analytics.mart_player_ros_projection where league_id = %s""", (lid,))
    return {r["player_key"]: r for r in rows}


# ------------------------------------------------------------------ waivers (mart_waiver_moves, the page's words)
def span(r) -> str:
    n = int(r["horizon_last_week"]) - int(r["week"]) + 1
    return f"the next {n} weeks" if n > 1 else "this week only"


def weeks_text(r) -> str:
    gains = r.get("week_gains") or []
    helped = [int(r["week"]) + i for i, g in enumerate(gains) if g is not None and float(g) > 0.005]
    return "" if not helped else ("week " if len(helped) == 1 else "weeks ") + ", ".join(str(w) for w in helped)


def headline(r) -> str:
    who = f"{r['add_name']} ({r['add_position']})"
    claim = f"Claim {who}, drop {r['drop_name']}" if r["drop_name"] else f"Claim {who}, no drop needed"
    wk, hz = float(r["weekly_gain"]), float(r["horizon_gain"])
    if wk > 0:
        at = f" at {r['add_slot']}" if r["add_slot"] else ""
        return f"{claim}: {wk:+.1f} this week{at}, {hz:+.1f} over {span(r)}"
    wt = weeks_text(r)
    when = f", all in {wt}" if wt and abs(wk) < 0.05 else (f" ({wt})" if wt else "")
    this_week = "" if abs(wk) < 0.05 else f", {wk:+.1f} this week"
    return f"{claim}: {hz:+.1f} over {span(r)}{when}{this_week}"


def seat(r) -> str:
    slot = r["add_slot"]
    he = "It" if r["add_position"] == "DEF" else "He"
    if not slot:
        return ""
    if r["fills_empty_slot"]:
        return f"{he} fills your empty {slot} slot (nobody on your roster can play it this week)."
    if r["displaced_name"]:
        if r["displaced_name"] == r["drop_name"]:
            return f"{he} starts at {slot}; {r['drop_name']} ({f1(r['drop_value'])} this week) leaves your lineup."
        where = f", from {r['displaced_slot']}" if r["displaced_slot"] and r["displaced_slot"] != slot else ""
        return (f"{he} starts at {slot}; **{r['displaced_name']}** ({r['displaced_position']}{where}, projected "
                f"{f1(r['displaced_value'])}) goes to your bench.")
    return f"{he} starts at {slot}."


def notes(r) -> list[str]:
    out = []
    if r["is_no_evidence"]:
        out.append("No games this season yet: the projection rests on last season and his role, not on anything he has shown this year.")
    if r["add_value_source"] == "season_ppg":
        out.append("Kickers are valued at their points per game so far this season.")
    if r["add_report_status"] == "Questionable":
        out.append("He is Questionable this week.")
    if r["add_reason"]:
        out.append(f"He cannot play this week ({r['add_reason']}).")
    if r["drop_name"]:
        loss = float(r["drop_horizon_loss"] or 0)
        out.append(f"Dropping {r['drop_name']} costs your lineup {f1(loss)} over {span(r)} (already counted)."
                   if loss > 0.05 else f"{r['drop_name']} would not start for you in {span(r)}.")
        if r["drop_ros_points"] is not None and r["add_ros_points"] is not None and float(r["drop_ros_points"]) > float(r["add_ros_points"]):
            out.append(f"Careful: {r['drop_name']} projects more than {r['add_name']} over the rest of the season "
                       f"({float(r['drop_ros_points']):.0f} vs {float(r['add_ros_points']):.0f} points).")
    elif r["list_kind"] != "nothing":
        out.append("You have an open roster spot, so nobody has to go.")
    return out


def card_lines(r) -> list[str]:
    week = int(r["week"])
    lines = []
    if r["add_value"] is not None and not r["add_reason"]:
        lines.append(f"{r['add_name']} projects {f1(r['add_value'])} for week {week} in your league's scoring. {seat(r)}".strip())
    if float(r["weekly_gain"]) > 0:
        lines.append(f"Your week-{week} lineup: {f1(r['lineup_before'])} → {f1(r['lineup_after'])}.")
    elif weeks_text(r):
        lines.append(f"It helps in {weeks_text(r)}, not this week, so there is time: claim him before then.")
    return lines + notes(r)


MOVE_COLS = """week, horizon_last_week, list_kind, move_rank, add_rank, is_best_drop, add_sleeper_id, add_gsis_id, add_name, add_position,
  add_team, add_value, add_value_source, add_reason, add_report_status, add_games_played, is_no_evidence, drop_sleeper_id, drop_gsis_id,
  drop_name, drop_position, drop_value, drop_is_starter, drop_horizon_loss, drop_ros_points, add_ros_points, weekly_gain, horizon_gain,
  week_gains, lineup_before, lineup_after, lineup_value, add_slot, fills_empty_slot, displaced_gsis_id, displaced_name,
  displaced_position, displaced_value, displaced_slot, open_roster_spots, inputs_current, on_current_lineup, as_of"""

WAIVER_HOWTO = [
    "**What a claim is worth**: we try every free agent against every player you could drop, rebuild your best lineup each time, "
    "and show how many points it adds. Same projections and same lineup as the rest of the app.",
    "**This week** is what the claim adds this week; **the next 4 weeks** add up this week and the next three, so covering a bye "
    "counts, and so do the games the dropped player would have started.",
    "**Who to drop**: the player your lineup misses least over those four weeks. We never suggest dropping someone we have no "
    "projection for yet: unknown is not zero.",
    "**Only the next four weeks count.** In a dynasty league, a young player's future is not in these numbers: look twice before "
    "dropping one.",
    "**The free agents** are ranked by this week's projection in your league's scoring; **most weeks** is the range half his "
    "weeks land in, and **rest of season** adds up every week left to your league's final.",
]


def mv_team(lid: str, roster: int) -> str:
    return teams(lid)[roster]["team_name"]


def waivers(lid: str, roster: int, info: dict) -> dict[str, dict]:
    mv = q(f"""select {MOVE_COLS} from analytics.mart_waiver_moves where league_id = %s and roster_id = %s and season = %s
               order by move_rank nulls first""", (lid, roster, SEASON))
    week = int(mv[0]["week"])
    best = [r for r in mv if r["list_kind"] == "nothing" or r["is_best_drop"]]
    best.sort(key=lambda r: (r["list_kind"] != "start_now", r["list_kind"] != "cover", r["add_rank"] or 0))
    start = [r for r in best if r["list_kind"] == "start_now"]
    cover = [r for r in best if r["list_kind"] == "cover"]
    flyer = [r for r in best if r["is_no_evidence"] and r["list_kind"] != "nothing"]
    ordered = (start[:1] + cover[:1] + [r for r in flyer if r not in start[:1] + cover[:1]][:1])
    rest = [r for r in start[1:] + cover[1:] if r not in ordered]
    rest.sort(key=lambda r: (-float(r["horizon_gain"]), -float(r["weekly_gain"])))
    moves = ordered + rest[:9] if best and best[0]["list_kind"] != "nothing" else best[:1]
    ids = [r["add_gsis_id"] for r in moves] + [r["drop_gsis_id"] for r in moves]
    hs = heads(ids)
    rng = {r["gsis_id"]: r for r in q("""select gsis_id, p10, p25, p75, p90 from analytics.mart_player_week_projections
                                        where league_id = %s and season = %s and week = %s""", (lid, SEASON, week))}
    out_moves = []
    for r in moves:
        r = dict(r)
        tag = ("Top claim" if r in start[:1] else "Best cover for a coming week" if r in cover[:1]
               else "Flyer: no games this season yet" if r in flyer else None) if r["list_kind"] != "nothing" else None
        a, d = hs.get(r["add_gsis_id"] or "", {}), hs.get(r["drop_gsis_id"] or "", {})
        pr = rng.get(r["add_gsis_id"] or r["add_sleeper_id"] or "", {})
        r.update({"add_headshot_url": a.get("headshot_url"), "drop_headshot_url": d.get("headshot_url"), "drop_team": d.get("team"),
                  "add_p10": pr.get("p10"), "add_p25": pr.get("p25"), "add_p75": pr.get("p75"), "add_p90": pr.get("p90"),
                  "card_title": tag})
        if r["list_kind"] != "nothing":
            r["headline"] = headline(r)
            r["lines"] = card_lines(r)
        out_moves.append(r)
    v = q("""select lineup_value, weakest_slot, weakest_margin, weakest_player_name, weakest_gsis_id, weakest_position, weakest_value,
                    weakest_replacement_name, weakest_replacement_value, horizon_value, horizon_label
             from analytics.mart_league_roster_value where league_id = %s and roster_id = %s""", (lid, roster))[0]
    wh = heads([v["weakest_gsis_id"]]).get(v["weakest_gsis_id"] or "", {})
    weakest = {"slot": v["weakest_slot"], "player_name": v["weakest_player_name"], "gsis_id": v["weakest_gsis_id"],
               "position": v["weakest_position"], "team": wh.get("team"), "headshot_url": wh.get("headshot_url"),
               "value": v["weakest_value"], "margin": v["weakest_margin"], "replacement_name": v["weakest_replacement_name"],
               "replacement_value": v["weakest_replacement_value"]}
    slots = info["roster_positions"] or []
    positions = [p for p in ["QB", "RB", "WR", "TE", "K", "DEF"] if p in slots or (p in ("RB", "WR", "TE") and any("FLEX" in s for s in slots))]
    ros = ros_rows(lid)
    fa_all = q("""select a.gsis_id, a.sleeper_id, a.player_name, a.position, a.nfl_team as team, d.headshot_url, a.injury_status,
                         a.games_played, a.ppg_std, a.expected_per_game, a.target_share_l3, a.snap_pct_l3, a.opponent, a.opp_rank_std,
                         p.proj_points, p.p10, p.p25, p.p75, p.p90, t.tags
                  from analytics.mart_player_availability a
                  left join analytics.dim_player d on d.gsis_id = a.gsis_id
                  left join analytics.mart_player_trend_tags t on t.gsis_id = a.gsis_id and t.season = a.season
                  join analytics.mart_player_week_projections p
                    on p.league_id = a.league_id and p.gsis_id = coalesce(a.gsis_id, a.sleeper_id) and p.season = %s and p.week = %s
                  where a.league_id = %s and a.is_free_agent and p.proj_points is not null
                    and coalesce(a.injury_status, '') not in ('Out', 'IR') and coalesce(a.roster_status, 'ACT') <> 'RES'
                  order by p.proj_points desc""", (SEASON, week, lid))
    for r in fa_all:
        rr = ros.get(r["gsis_id"] or r["sleeper_id"] or "", {})
        r.update({"ros_points": rr.get("ros_points"), "ros_games": rr.get("ros_games"), "ros_rank_pos": rr.get("ros_rank_pos")})
    base = {"league_id": lid, "league_name": info["league_name"], "season": SEASON, "week": week,
            "horizon_last_week": int(mv[0]["horizon_last_week"]), "roster_id": roster, "team_name": mv_team(lid, roster), "lineup_value": v["lineup_value"],
            "weakest": weakest, "moves": out_moves, "positions": positions, "inputs_current": mv[0]["inputs_current"],
            "on_current_lineup": mv[0]["on_current_lineup"], "as_of": mv[0]["as_of"], "howto": WAIVER_HOWTO}
    files = {}
    for pos in ["ALL", *positions]:
        fa = [r for r in fa_all if pos == "ALL" or r["position"] == pos]
        files[pos] = {**base, "position": pos, "free_agents": fa[: 25 if pos != "ALL" else 30]}
    return files


# ------------------------------------------------------------------ team hub
TEAM_HOWTO = [
    "**Lineup value** is the projected points of the best lineup you can start this week, in your league's scoring, with FLEX and "
    "superflex filled by whoever is worth most there. The rank next to it is where that puts you in the league.",
    "**Margin** is how much your lineup loses without that starter. The smallest one is your **closest call**: check the news on "
    "those two players before kickoff.",
    "**Next 4 weeks** adds up your best lineup for each of the next four weeks, byes and injuries included. Low here but high this "
    "week? Look for cover now.",
    "**Depth** is the lineup your bench alone could put out. Low depth means one injury hurts: a trade or a claim for a starter "
    "matters more to you than to most.",
    "**By slot**: your best starter at each slot against the league's best and its average. A short bar is where a claim or a "
    "trade helps most.",
]


def team(lid: str, roster: int, info: dict, all_teams: dict) -> dict:
    v = q("select * from analytics.mart_league_roster_value where league_id = %s and roster_id = %s", (lid, roster))[0]
    rk = q("""select measure, measure_label, horizon, value, league_rank, n_rosters, rank_label from analytics.mart_league_roster_rankings
              where league_id = %s and roster_id = %s order by measure""", (lid, roster))
    lg = q("""select roster_id, team_name, max(value) filter (where measure = 'lineup_value') as lineup_value,
                     max(value) filter (where measure = 'horizon_value') as horizon_value,
                     max(value) filter (where measure = 'bench_value') as bench_value
              from analytics.mart_league_roster_rankings where league_id = %s group by 1, 2 order by 3 desc""", (lid,))
    ss_all = q("""select roster_id, slot_type, slots, empty_slots, first_slot_order, top_slot, top_player_name, top_gsis_id, top_position,
                         top_value, top_is_locked, starter_strength, replacement_name, replacement_value
                  from analytics.mart_league_roster_slot_strength where league_id = %s order by first_slot_order""", (lid,))
    mine_ss = [r for r in ss_all if r["roster_id"] == roster]
    hs = heads([r["top_gsis_id"] for r in mine_ss])
    for r in mine_ss:
        same = [x["top_value"] for x in ss_all if x["slot_type"] == r["slot_type"] and x["top_value"] is not None]
        r["league_avg_top_value"] = round(sum(same) / len(same), 2) if same else None
        r["league_best_top_value"] = max(same) if same else None
        r["league_rank_top_value"] = 1 + sum(1 for x in same if r["top_value"] is not None and x > r["top_value"]) if r["top_value"] is not None else None
        r["n_rosters"] = len(same)
        h = hs.get(r["top_gsis_id"] or "", {})
        r["top_headshot_url"], r["top_team"] = h.get("headshot_url"), h.get("team")
        del r["roster_id"]
    wk = q("""select roster_id, week, round(sum(player_value)::numeric, 2)::float as lineup_value
              from analytics.mart_league_roster_horizon where league_id = %s and role = 'starter' group by 1, 2""", (lid,))
    weeks = sorted({r["week"] for r in wk})
    weekly = []
    for w in weeks:
        vals = sorted((r["lineup_value"] for r in wk if r["week"] == w), reverse=True)
        mine = next((r["lineup_value"] for r in wk if r["week"] == w and r["roster_id"] == roster), None)
        mid = len(vals) // 2
        median = round((vals[mid] + vals[~mid]) / 2, 2)
        weekly.append({"week": w, "lineup_value": mine, "league_median": median, "league_best": vals[0],
                       "league_rank": 1 + sum(1 for x in vals if mine is not None and x > mine), "n_rosters": len(vals)})
    roster_rows = q("""select h.role, h.slot, h.slot_type, h.slot_order, h.bench_rank, h.sleeper_player_id, h.gsis_id, h.player_name,
                              h.position, d.latest_team as team, d.headshot_url, h.player_value, h.value_source, h.lineup_margin,
                              h.is_locked, h.report_status, h.reason, h.acquired_label, h.acquired_how_by_manager
                       from analytics.mart_league_roster_horizon h left join analytics.dim_player d on d.gsis_id = h.gsis_id
                       where h.league_id = %s and h.roster_id = %s and h.is_this_week
                       order by case h.role when 'starter' then 0 when 'empty' then 0 when 'bench' then 1 else 2 end,
                                h.slot_order nulls last, h.bench_rank nulls last, h.player_value desc nulls last""", (lid, roster))
    ros = ros_rows(lid)
    for r in roster_rows:
        rr = ros.get(r["gsis_id"] or r["sleeper_player_id"] or "", {})
        r["ros_points"], r["ros_rank_pos"] = rr.get("ros_points"), rr.get("ros_rank_pos")
    prof = q("""select wins, losses, standing, all_play_win_pct, luck_wins, avg_bench_points_left, faab_spent, points_for
                from analytics.mart_league_manager_profile where league_id = %s and roster_id = %s""", (lid, roster))
    t = all_teams[roster]
    return {"league_id": lid, "league_name": info["league_name"], "season": SEASON, "week": v["week"], "roster_id": roster,
            "team_name": t["team_name"], "manager_name": t["manager_name"], "league_type": info["league_type"],
            "value": {k: v[k] for k in ("week", "horizon_first_week", "horizon_last_week", "horizon_weeks", "week_label", "horizon_label",
                                        "lineup_value", "bench_value", "slots_total", "slots_filled", "empty_slots", "n_unvalued", "n_locked",
                                        "n_questionable", "weakest_slot", "weakest_margin", "weakest_player_name", "weakest_gsis_id",
                                        "weakest_position", "weakest_value", "weakest_replacement_name", "weakest_replacement_value",
                                        "horizon_value", "worst_week", "worst_week_value")},
            "rankings": rk, "league": lg, "slots": mine_ss, "weeks": weekly, "roster": roster_rows,
            "profile": prof[0] if prof else None, "howto": TEAM_HOWTO}


# ------------------------------------------------------------------ league
def league(lid: str, info: dict) -> dict:
    standings = q("""select standing, roster_id, team_name, manager_name, wins, losses, ties, games, win_pct, points_for, points_against,
                            avg_points, best_week, worst_week, lineup_efficiency, is_champion
                     from analytics.mart_league_standings where league_id = %s order by standing""", (lid,))
    all_play = q("""select roster_id, team_name, manager_name, games, wins, losses, all_play_wins, all_play_losses, all_play_win_pct,
                           expected_wins, luck_wins, top_half_weeks, avg_points_rank, all_play_rank
                    from analytics.mart_league_all_play where league_id = %s order by luck_wins desc""", (lid,))
    profiles = q("""select roster_id, team_name, manager_name, avg_bench_points_left, total_bench_points_left, avg_lineup_efficiency,
                           waiver_adds, free_agent_adds, trades, faab_spent
                    from analytics.mart_league_manager_profile where league_id = %s order by standing nulls last""", (lid,))
    weeks = q("""select week, roster_id, team_name, points, opponent_points, result, all_play_wins, all_play_losses, week_points_rank
                 from analytics.mart_league_all_play_week where league_id = %s order by week, week_points_rank""", (lid,))
    tx = q("""select t.created_at, t.week, t.transaction_type, t.status, t.action, t.roster_id, t.team_name, t.sleeper_player_id,
                     m.gsis_id, t.player_name, t.position, d.latest_team as team, d.headshot_url, t.waiver_bid, t.transaction_id
              from analytics.mart_league_transactions t
              left join analytics.player_id_map m on m.sleeper_id = t.sleeper_player_id
              left join analytics.dim_player d on d.gsis_id = m.gsis_id
              where t.league_id = %s and t.status = 'complete' order by t.created_at desc, t.transaction_id, t.action limit 40""", (lid,))
    draft = q("""select d.pick_no, d.round, d.draft_slot, d.roster_id, d.team_name, d.player_name, d.position, d.drafted_team, d.is_keeper,
                        d.gsis_id, p.headshot_url, d.nfl_reg_games_played, d.nfl_reg_points_current_scoring, d.position_rank_by_pick,
                        d.position_rank_by_points
                 from analytics.mart_league_draft d left join analytics.dim_player p on p.gsis_id = d.gsis_id
                 where d.league_id = %s order by d.pick_no""", (lid,))
    return {"league_id": lid, "league_name": info["league_name"], "season": SEASON, "league_type": info["league_type"],
            "weeks_played": len({r["week"] for r in weeks}), "standings": standings, "all_play": all_play, "profiles": profiles,
            "weeks": weeks, "transactions": tx, "draft": draft or None}


# ------------------------------------------------------------------ trades (league_lab.trades on the page's board)
class Board:
    def __init__(self, lid: str, info: dict):
        self.lid = lid
        self.rows = q("""select roster_id, week, this_week, horizon_first_week, horizon_last_week, role, slot, slot_type, sleeper_player_id,
                                gsis_id, player_name, position, fantasy_positions, player_value, value_source, lineup_margin, is_locked, reason
                         from analytics.mart_league_roster_horizon where league_id = %s""", (lid,))
        self.this_week = int(self.rows[0]["this_week"])
        first, last = int(self.rows[0]["horizon_first_week"]), int(self.rows[0]["horizon_last_week"])
        self.span = f"weeks {first}–{last}" if last > first else f"week {first}"
        self.board = RosterBoard(self.rows, tuple(info["roster_positions"] or []))
        pts = q(T.MARKET_SQL.replace("%s", "%s"), (lid, SEASON, self.this_week))
        points = {r["player_key"]: r["season_points"] for r in pts}
        repl = q(T.REPLACEMENT_SQL, (lid, SEASON, self.this_week, lid))
        self.replacement = {r["position"]: r["replacement"] for r in repl}
        self.market = T.market_by_player(self.board, points)
        self.prices = T.price_by_player(self.board, self.market, self.replacement)
        self.info = {}
        for r in sorted(self.rows, key=lambda r: r["week"]):
            self.info.setdefault(r["sleeper_player_id"], r)
        self.now = {r["sleeper_player_id"]: r for r in self.rows if r["week"] == self.this_week}
        self.ros = ros_rows(lid)
        self.hs = heads([r["gsis_id"] for r in self.info.values()])

    def player(self, pid: str) -> dict:
        r = self.info.get(pid, {})
        g = r.get("gsis_id")
        h = self.hs.get(g or "", {})
        now = self.now.get(pid, {})
        rr = self.ros.get(g or pid, {})
        return {"sleeper_id": pid, "gsis_id": g, "player_name": r.get("player_name"), "position": r.get("position"),
                "team": h.get("team"), "headshot_url": h.get("headshot_url"),
                "value": None if now.get("role") == "unplayable" else now.get("player_value"),
                "reason": now.get("reason") if now.get("role") == "unplayable" else None,
                "market_price": T.whole(self.prices[pid]) if pid in self.prices else None,
                "season_points": T.whole(self.market[pid]) if pid in self.market else None,
                "ros_points": rr.get("ros_points"), "ros_rank_pos": rr.get("ros_rank_pos")}

    def name(self, pid: str) -> str:
        return self.info.get(pid, {}).get("player_name") or pid


def side_json(b: Board, s: T.Side) -> dict:
    return {"roster_id": s.roster_id, "week_before": s.before[0], "week_after": s.after[0], "horizon_before": s.before_horizon,
            "horizon_after": s.after_horizon, "gain_week": s.gain_week, "gain_horizon": s.gain_horizon,
            "bench_before": s.bench_before, "bench_after": s.bench_after,
            "closest_after": (None if s.weakest_after is None else
                              {"player_name": b.name(s.weakest_after.player.id), "slot": s.weakest_after.slot.label,
                               "margin": round(s.weakest_after.margin, 2)}),
            "cuts": [{**b.player(c.player_id), "horizon_loss": c.horizon_loss} for c in s.cuts],
            "opened": s.opened, "price_out": s.price_out, "price_in": s.price_in,
            "lineup": lineup_rows(b, s)}


def lineup_rows(b: Board, s: T.Side) -> list[dict]:
    before = {x.slot.label: x for x in s.lineup_before.starts}
    out = []
    for x in s.lineup_after.starts:
        bx = before.get(x.slot.label)
        bv = (bx.value or 0.0) if bx is not None and bx.player is not None else 0.0
        pid = x.player.id if x.player is not None else None
        av = (x.value or 0.0) if pid is not None else None
        ch = (av or 0.0) - bv
        p = b.player(pid) if pid else {}
        out.append({"slot": x.slot.label, "sleeper_id": pid, "gsis_id": p.get("gsis_id"), "player_name": p.get("player_name"),
                    "position": p.get("position"), "headshot_url": p.get("headshot_url"), "is_new": bool(pid and pid in s.gets),
                    "value": None if av is None else round(av, 2), "change": round(ch, 2) if abs(ch) >= 0.005 else None})
    return out


def evaluate(b: Board, lid: str, me: int, partner: int, give: list[str], get: list[str], names: dict) -> dict:
    t = T.evaluate(b.board, give, get, market=b.market, prices=b.prices)
    m, th = t.mine, t.theirs
    ros_give = sum(T.whole(b.ros[k]["ros_points"]) for k in (b.info[x]["gsis_id"] or x for x in give) if k in b.ros)
    ros_get = sum(T.whole(b.ros[k]["ros_points"]) for k in (b.info[x]["gsis_id"] or x for x in get) if k in b.ros)
    any_ros = next(iter(b.ros.values()))
    window = f"weeks {any_ros['from_week']}–{any_ros['last_week']}"
    lnk = lambda ids: " and ".join(b.name(x) for x in ids) if len(ids) < 3 else ", ".join(b.name(x) for x in ids[:-1]) + " and " + b.name(ids[-1])  # noqa: E731
    return {"league_id": lid, "team": me, "partner": partner, "partner_team_name": names[partner]["team_name"],
            "week": b.this_week, "weeks": list(t.weeks), "span": b.span,
            "give": [b.player(x) for x in give], "get": [b.player(x) for x in get],
            "before": {"mine": {"week": m.before[0], "horizon": m.before_horizon, "bench": m.bench_before},
                       "theirs": {"week": th.before[0], "horizon": th.before_horizon, "bench": th.bench_before}},
            "after": {"mine": {"week": m.after[0], "horizon": m.after_horizon, "bench": m.bench_after},
                      "theirs": {"week": th.after[0], "horizon": th.after_horizon, "bench": th.bench_after}},
            "fit": {"mine": {"week": m.gain_week, "horizon": m.gain_horizon}, "theirs": {"week": th.gain_week, "horizon": th.gain_horizon},
                    "line": T.fit_line(t, b.span)},
            "market": {"give": m.price_out, "get": m.price_in, "about_even": T.about_even(m.price_out or 0, m.price_in or 0),
                       "unknown": [b.name(x) for x in (*m.unknown_out, *m.unknown_in)], "line": T.fairness_line(t),
                       "replacement": {p: T.whole(v) for p, v in sorted(b.replacement.items())}},
            "ros": {"give": ros_give, "get": ros_get, "window": window},
            "verdict": T.verdict(t, b.span),
            "headline": f"**You give {lnk(give)}; you get {lnk(get)}.**",
            "sides": {"mine": side_json(b, m), "theirs": side_json(b, th)},
            "weekly": [{"week": w, "you_before": m.before[i], "you_after": m.after[i], "them_before": th.before[i], "them_after": th.after[i]}
                       for i, w in enumerate(t.weeks)]}


def partners(b: Board, lid: str, me: int, names: dict) -> dict[str, dict]:
    found = T.partners(b.board, me)
    rows = []
    for p in found:
        for pk in (p.one_for_one, p.two_for_one):
            if pk is None:
                continue
            rows.append({"roster_id": p.roster_id, "team_name": names[p.roster_id]["team_name"], "manager_name": names[p.roster_id]["manager_name"],
                         "shape": pk.shape, "give": [b.player(x) for x in pk.give], "get": [b.player(x) for x in pk.get],
                         "my_week": pk.my_week, "my_horizon": pk.my_horizon, "their_week": pk.their_week, "their_horizon": pk.their_horizon,
                         "market_out": T.season_value(b.prices, pk.give)[0], "market_in": T.season_value(b.prices, pk.get)[0],
                         "is_best": pk is p.best})
    rows.sort(key=lambda r: (-min(r["my_horizon"], r["their_horizon"]), -(r["my_horizon"] + r["their_horizon"])))
    none = [names[p.roster_id]["team_name"] for p in found if p.best is None]
    out = {}
    for want in ["ALL", *POSITIONS]:
        keep = [r for r in rows if want == "ALL" or any(x["position"] == want for x in r["get"])]
        out[want] = clean({"league_id": lid, "team": me, "week": b.this_week, "span": b.span, "want": want, "partners": keep, "none": none})
    return out, found


# ------------------------------------------------------------------ the Test League: Scrubs retold
def retell(obj, names_map: dict[int, dict], roster_map: dict[int, int], lid_from: str, lid_to: str, name_from: str, name_to: str):
    """Rename teams / managers and renumber rosters (Scrubs → Test League)."""
    by_team = {v["from_team"]: v for v in names_map.values()}
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k in ("roster_id", "team", "partner", "owner") and isinstance(v, int):
                out[k] = roster_map.get(v, v)
            elif k == "league_id" and v == lid_from:
                out[k] = lid_to
            elif k == "league_name" and v == name_from:
                out[k] = name_to
            elif k in ("team_name", "partner_team_name") and v in by_team:
                out[k] = by_team[v]["team_name"]
            elif k == "manager_name" and isinstance(v, str):
                hit = next((x for x in names_map.values() if x["from_manager"] == v), None)
                out[k] = hit["manager_name"] if hit else v
            else:
                out[k] = retell(v, names_map, roster_map, lid_from, lid_to, name_from, name_to)
        return out
    if isinstance(obj, list):
        return [retell(x, names_map, roster_map, lid_from, lid_to, name_from, name_to) for x in obj]
    if isinstance(obj, str):
        for v in names_map.values():
            if v["from_team"] in obj:
                obj = obj.replace(v["from_team"], v["team_name"])
        return obj
    return obj


def main() -> None:
    test_rosters = json.loads((OUT / "rosters_9000000000000000001.json").read_text())
    test_by_id = {r["roster_id"]: r for r in test_rosters}
    for lid in (DYN, SCRUBS):
        info = league_info(lid)
        names = teams(lid)
        me = MINE[lid]
        # Scrubs → Test League: roster 2 ↔ 3 swap, the rest keep their number
        rmap = {2: 3, 3: 2} if lid == SCRUBS else {}
        nmap = {}
        if lid == SCRUBS:
            for rid, t in names.items():
                to = test_by_id[rmap.get(rid, rid)]
                nmap[rid] = {"from_team": t["team_name"], "from_manager": t["manager_name"], "team_name": to["team_name"],
                             "manager_name": to["manager_name"]}

        def emit(name: str, data, test_name: str | None = None) -> None:
            save(name, data)
            if lid == SCRUBS and test_name:
                told = retell(data, nmap, rmap, SCRUBS, TEST, info["league_name"], "Test League")
                if isinstance(told, dict):
                    told["source"] = "sleeper"
                    if "draft" in told:
                        told["draft"] = None
                    if "transactions" in told:
                        told["transactions"] = told["transactions"][:24]
                save(test_name, told)

        for pos, data in waivers(lid, me, info).items():
            emit(f"waivers_{lid}_{me}_{pos}.json", data, f"waivers_{TEST}_{rmap.get(me, me)}_{pos}.json")
        for rid in names:
            emit(f"team_{lid}_{rid}.json", team(lid, rid, info, names), f"team_{TEST}_{rmap.get(rid, rid)}.json")
        emit(f"league_{lid}.json", league(lid, info), f"league_{TEST}.json")

        b = Board(lid, info)
        by_want, found = partners(b, lid, me, names)
        for want, data in by_want.items():
            emit(f"trades_partners_{lid}_{me}_{want}.json", data, f"trades_partners_{TEST}_{rmap.get(me, me)}_{want}.json")
        # two packages per league: the best partner's best trade, and a one-for-one of the two teams' best-valued players
        # with the second partner (usually a no)
        evals = []
        ranked = [p for p in found if p.best is not None]
        if ranked:
            pk = ranked[0].best
            evals.append((ranked[0].roster_id, list(pk.give), list(pk.get)))
        other = next((p.roster_id for p in found if not ranked or p.roster_id != ranked[0].roster_id), None)
        mine_ids = sorted(b.board.roster(me), key=lambda x: -(b.now.get(x, {}).get("player_value") or -1))
        theirs_ids = sorted(b.board.roster(other), key=lambda x: -(b.now.get(x, {}).get("player_value") or -1))
        evals.append((other, mine_ids[:1], theirs_ids[1:2]))
        for partner_id, give, get in evals:
            data = clean(evaluate(b, lid, me, partner_id, give, get, names))
            key = f"{partner_id}_{'-'.join(sorted(give))}_{'-'.join(sorted(get))}"
            tkey = f"{rmap.get(partner_id, partner_id)}_{'-'.join(sorted(give))}_{'-'.join(sorted(get))}"
            emit(f"trades_evaluate_{lid}_{me}_{key}.json", data, f"trades_evaluate_{TEST}_{rmap.get(me, me)}_{tkey}.json")
            print(lid, "evaluate", key, data["verdict"])
        print(lid, "done")


if __name__ == "__main__":
    main()
