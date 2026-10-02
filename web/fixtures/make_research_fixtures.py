"""Build the research screens' fixtures (Wave G, G3): web/fixtures/{trends,matchups_defense,matchups_cb,players,
receivers,compare,games}_*.json, one answer per route of the G1 contract (docs/PROJECT_PLAN.md § Iteration 15; the
shapes are listed in web/README.md § "Fixtures"), from the marts in a clone — real numbers, the API's field names.

    PGPASSWORD=localsim uv run python web/fixtures/make_research_fixtures.py        # DB=league_lab_g3

* The house leagues (dynasty roster 12, Scrubs roster 2) read their own league marts: points in the league's scoring
  (fct_player_game_league, mart_player_availability, mart_player_week_projections, mart_player_ros_projection),
  rostered_by from mart_player_availability. NFL-wide numbers (shares, defense vs position, corners) are one scale.
* The Test League (9000000000000000001, no database) reuses Scrubs' numbers (the same half-PPR scoring) with its own
  rosters: team 3's players from its My Week fixture, everyone Scrubs rosters spread over the Test League's teams.
* Sentences come from app/lib where they exist (cb_line, lean_text, kind_label), as the API sends them.
* Week 4 is the week (the clone is frozen there); season 2026; game logs carry 2025 and 2026.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "app"))
from lib.matchups import cb_line, lean_text  # noqa: E402
from lib.signals import kind_label  # noqa: E402

DB = os.environ.get("DB", "league_lab_g3")
OUT = Path(__file__).resolve().parent
DYN, SCRUBS, TEST = "1321941740235550720", "1389709692405551104", "9000000000000000001"
TEAM = {DYN: 12, SCRUBS: 2, TEST: 3}
WEEK, SEASON = 4, 2026
SKILL = ("QB", "RB", "WR", "TE")


def sql(q: str):
    out = subprocess.run(
        ["psql", "-U", "postgres", "-h", "localhost", "-d", DB, "-At", "-c", f"select coalesce(json_agg(t), '[]') from ({q}) t"],
        check=True, capture_output=True, text=True,
    ).stdout
    return json.loads(out)


def save(name: str, data, compact: bool = False) -> None:
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":")) if compact else json.dumps(data, indent=1, ensure_ascii=False)
    (OUT / name).write_text(text + "\n")


def lineup(league: str) -> list[dict]:
    return json.loads((OUT / f"my-week_{league}_{TEAM[league]}.json").read_text())["lineup_full"]


# ---- the Test League's owners: team 3 = its My Week roster; Scrubs' other owners spread over its 10 teams
TEST_ROSTERS = {r["roster_id"]: r["team_name"] for r in json.loads((OUT / f"rosters_{TEST}.json").read_text())}
TEST_MINE = {r["gsis_id"] for r in lineup(TEST) if r["gsis_id"]}


def owners(league: str) -> dict[str, tuple[int | None, str | None]]:
    src = SCRUBS if league == TEST else league
    rows = sql(f"""select gsis_id, rostered_by_roster_id, rostered_by_team from analytics.mart_player_availability
                   where league_id = '{src}' and rostered_by_roster_id is not null""")
    out = {r["gsis_id"]: (r["rostered_by_roster_id"], r["rostered_by_team"]) for r in rows}
    if league == TEST:
        moved = {}
        for g, (rid, _) in out.items():
            t = 4 if rid == 3 else rid  # Scrubs' team 3 is not the Test League's team 3
            moved[g] = (t, TEST_ROSTERS.get(t))
        for g in TEST_MINE:
            moved[g] = (3, TEST_ROSTERS[3])
        out = moved
    return out


def own(row: dict, own_map) -> dict:
    rid, name = own_map.get(row["gsis_id"], (None, None))
    row["rostered_by_roster_id"] = rid
    row["rostered_by_team"] = name
    return row


def scored(league: str) -> str:
    return SCRUBS if league == TEST else league


# ---------------------------------------------------------------- /api/trends
def trends(league: str) -> dict:
    src = scored(league)
    rows = sql(f"""
        select a.gsis_id, a.player_name, a.position, coalesce(a.nfl_team, t.team) as team, d.headshot_url,
               t.games, t.latest_week, t.tags, round(t.momentum, 2)::float as momentum, t.opportunity_trend, t.n_up, t.n_down,
               round(t.target_share_l3, 3)::float as target_share_l3, round(t.target_share_change, 3)::float as target_share_change,
               round(t.snap_share_l3, 3)::float as snap_share_l3, round(t.snap_share_change, 3)::float as snap_share_change,
               round(t.carry_share_change, 3)::float as carry_share_change,
               round(t.expected_points_l3, 2)::float as expected_points_l3, round(t.expected_points_change, 2)::float as expected_points_change,
               round(t.points_l3, 2)::float as points_l3, round(t.points_change, 2)::float as points_change,
               a.games_with_expected, round(a.ppg_std, 2)::float as ppg, round(a.expected_per_game, 2)::float as xppg,
               round(a.diff_per_game, 2)::float as gap
        from analytics.mart_player_availability a
        join analytics.dim_player d using (gsis_id)
        left join analytics.mart_player_trend_tags t on t.gsis_id = a.gsis_id and t.season = {SEASON}
        where a.league_id = '{src}' and a.position in {SKILL} and a.games_with_expected >= 2 and a.expected_per_game is not null
          and a.expected_per_game >= 4
        order by abs(a.diff_per_game) desc nulls last
        limit 120""")
    alerts = {a["gsis_id"]: a for a in sql(f"""select gsis_id, direction, kind, direction_label, change_text, cause_text, games_held
                                                 from analytics.mart_player_role_alerts where season = {SEASON} and is_live""")}
    o = owners(league)
    for r in rows:
        r["direction"] = "over" if r["gap"] > 0.5 else "under" if r["gap"] < -0.5 else "even"
        a = alerts.get(r["gsis_id"])
        r["role_alert"] = ({**a, "label": kind_label(a)} if a else None)
        if a:
            r["role_alert"].pop("gsis_id", None)
        own(r, o)
    return {"league_id": league, "season": SEASON, "week": WEEK, "players": rows}


# ---------------------------------------------------------------- /api/matchups/defense
def defense(league: str) -> dict:
    positions = ["QB", "RB", "WR", "TE"] + ([] if league == DYN else ["K"])
    rows = sql(f"""
        select defense, position, games, round(points_allowed_per_game_std, 2)::float as points_allowed_pg, rank_std as rank,
               round(points_allowed_per_game_l4, 2)::float as points_allowed_pg_l4, rank_l4,
               case when rank_l4 < rank_std - 3 then 'up' when rank_l4 > rank_std + 3 then 'down' else 'steady' end as trend
        from analytics.mart_defense_vs_position_current
        where season = {SEASON} and position in ({",".join(f"'{p}'" for p in positions)})
        order by defense, position""")
    weeks = sql(f"select max(through_week) as w from analytics.mart_defense_vs_position_current where season = {SEASON}")[0]["w"]
    ids = [r["gsis_id"] for r in lineup(league) if r["role"] == "starter" and r["gsis_id"]]
    src = scored(league)
    starters = sql(f"""
        select p.gsis_id, p.player_name, p.position, p.team, d.headshot_url, p.opponent, p.is_home
        from analytics.mart_player_week_projections p join analytics.dim_player d using (gsis_id)
        where p.league_id = '{src}' and p.season = {SEASON} and p.week = {WEEK} and p.gsis_id in ({",".join(f"'{g}'" for g in ids)})""")
    order = {g: i for i, g in enumerate(ids)}
    starters.sort(key=lambda s: order.get(s["gsis_id"], 99))
    slots = {r["gsis_id"]: r["slot"] for r in lineup(league)}
    for s in starters:
        s["slot"] = slots.get(s["gsis_id"])
    return {"league_id": league, "season": SEASON, "week": WEEK, "weeks_used": weeks, "positions": positions, "teams": rows,
            "starters": starters}


# ---------------------------------------------------------------- /api/matchups/cb
def cb(league: str) -> dict:
    mine = [r for r in lineup(league) if r["gsis_id"] and r["position"] in ("WR", "TE") and r["role"] != "unplayable"]
    ids = [r["gsis_id"] for r in mine]
    starters = {r["gsis_id"] for r in mine if r["role"] == "starter"}
    rows = sql(f"""select m.*, d.headshot_url, k.shadow_flag
                   from analytics.mart_cb_matchups m join analytics.dim_player d using (gsis_id)
                   left join analytics.mart_cb_rankings k on k.gsis_id = m.likely_cover_gsis_id and k.season = m.season and k.window_label = 'two_seasons'
                   where m.season = {SEASON} and m.week = {WEEK} and m.gsis_id in ({",".join(f"'{g}'" for g in ids)})""")
    proj = {p["gsis_id"]: p for p in sql(f"""select gsis_id, proj_points, p25, p75 from analytics.mart_player_week_projections
                                              where league_id = '{scored(league)}' and season = {SEASON} and week = {WEEK}""")}
    o = owners(league)
    keep = ["gsis_id", "player_name", "position", "team", "headshot_url", "opponent", "is_home", "call_status", "call_strength",
            "alignment_lean", "located_targets", "left_share", "middle_share", "right_share", "side_share", "other_side_share",
            "likely_cover_gsis_id", "likely_cover_name", "likely_cover_slot", "cover_rank", "cover_label", "other_cover_name",
            "other_cover_slot", "cb_n_ranked", "shadow_flag", "games_vs_cover", "targets_vs_cover", "receptions_vs_cover",
            "yards_vs_cover", "tds_vs_cover"]
    out = []
    order = {g: i for i, g in enumerate(ids)}
    for r in sorted(rows, key=lambda r: (r["gsis_id"] not in starters, order[r["gsis_id"]])):
        row = {k: r.get(k) for k in keep}
        row["line"] = cb_line(r)
        row["lean"] = lean_text(r) if r["call_status"] != "tight end" else None
        p = proj.get(r["gsis_id"], {})
        row.update({"proj_points": p.get("proj_points"), "p25": p.get("p25"), "p75": p.get("p75"), "is_starter": r["gsis_id"] in starters})
        out.append(own(row, o))
    return {"league_id": league, "season": SEASON, "week": WEEK, "matchups": out}


# ---------------------------------------------------------------- /api/players (one season, every skill player)
def players(league: str) -> dict:
    src = scored(league)
    rows = sql(f"""
        with pts as (select gsis_id, count(*) filter (where played) as g, sum(points) as points
                     from analytics.fct_player_game_league where league_id = '{src}' and season = {SEASON} and season_type = 'REG' group by 1)
        select s.gsis_id, s.player_name, s.position, coalesce(d.latest_team, split_part(s.teams, ',', 1)) as team, d.headshot_url,
               s.games_played, round(pts.points, 2)::float as points, round(pts.points / nullif(pts.g, 0), 2)::float as points_per_game,
               s.targets, round(s.target_share, 3)::float as target_share, s.receptions, s.receiving_yards, s.receiving_tds,
               s.carries, round(s.carry_share, 3)::float as carry_share, s.rushing_yards, s.rushing_tds,
               s.attempts, s.passing_yards, s.passing_tds, s.passing_interceptions,
               round(s.avg_offense_snap_pct::numeric, 3)::float as avg_offense_snap_pct, round(s.adot, 1)::float as adot,
               round(s.first_read_target_share, 3)::float as first_read_target_share, round(s.route_participation, 3)::float as route_participation
        from analytics.mart_player_season s join analytics.dim_player d using (gsis_id) left join pts using (gsis_id)
        where s.season = {SEASON} and s.season_type = 'REG' and s.position in {SKILL} and s.games_played >= 1
        order by pts.points desc nulls last, s.player_name""")
    o = owners(league)
    for r in rows:
        own(r, o)
    return {"league_id": league, "season": SEASON, "total": len(rows), "players": rows}


# ---------------------------------------------------------------- /api/receivers
YS = ["target_share", "targets_per_game", "air_yards_share", "adot", "first_read_target_share", "route_participation", "tprr_proxy",
      "yprr_proxy", "avg_offense_snap_pct"]


def receivers(league: str) -> dict:
    src = scored(league)
    rows = sql(f"""
        with pts as (select gsis_id, count(*) filter (where played) as g, sum(points) as points
                     from analytics.fct_player_game_league where league_id = '{src}' and season = {SEASON} and season_type = 'REG' group by 1),
             f as (select distinct on (gsis_id) gsis_id, target_share_l3, target_share_l5, snap_pct_l3, route_participation_l3, first_read_share_l3,
                          points_per_game_l3
                   from analytics.mart_player_recent_form where season = {SEASON} and season_type = 'REG' order by gsis_id, week desc)
        select s.gsis_id, s.player_name, s.position, coalesce(d.latest_team, split_part(s.teams, ',', 1)) as team, d.headshot_url,
               s.games_played, round(pts.points / nullif(pts.g, 0), 2)::float as ppg,
               {", ".join(f"round(s.{m}::numeric, 3)::float as {m}" for m in YS)},
               round(f.target_share_l3, 3)::float as target_share_l3, round(f.target_share_l5, 3)::float as target_share_l5,
               round(f.snap_pct_l3::numeric, 3)::float as snap_pct_l3, round(f.route_participation_l3, 3)::float as route_participation_l3,
               round(f.first_read_share_l3, 3)::float as first_read_share_l3
        from analytics.mart_player_season s join analytics.dim_player d using (gsis_id) left join pts using (gsis_id) left join f using (gsis_id)
        where s.season = {SEASON} and s.season_type = 'REG' and s.position in ('WR', 'TE') and s.games_played >= 2 and s.targets >= 5
        order by pts.points desc nulls last
        limit 150""")
    yard = {}
    for pos in ("WR", "TE"):
        top = sorted([r for r in rows if r["position"] == pos and r["ppg"] is not None], key=lambda r: -r["ppg"])[:12]
        vals = {m: [r[m] for r in top if r[m] is not None] for m in YS + ["ppg"]}
        yard[pos] = {m: (round(sum(v) / len(v), 3) if v else None) for m, v in vals.items()}
    o = owners(league)
    for r in rows:
        own(r, o)
    return {"league_id": league, "season": SEASON, "through_week": 3, "yardsticks": yard, "receivers": rows}


# ---------------------------------------------------------------- /api/compare sides + /api/player/{gsis}/games
def subjects(league: str, extra: list[str]) -> list[str]:
    ids = [r["gsis_id"] for r in lineup(league) if r["gsis_id"]]
    return list(dict.fromkeys(ids + extra))


def compare_sides(league: str, ids: list[str]) -> dict:
    src = scored(league)
    q = ",".join(f"'{g}'" for g in ids)
    heads = {r["gsis_id"]: r for r in sql(f"""select gsis_id, player_name, position, latest_team as team, headshot_url
                                               from analytics.dim_player where gsis_id in ({q})""")}
    wk = {}
    for r in sql(f"""select gsis_id, week, opponent, is_home, round(proj_points, 2)::float as proj_points, round(p10, 1)::float as p10,
                            round(p25, 1)::float as p25, round(p75, 1)::float as p75, round(p90, 1)::float as p90, opp_rank_std as opp_rank, team
                     from analytics.mart_player_week_projections
                     where league_id = '{src}' and season = {SEASON} and week between {WEEK} and {WEEK + 3} and gsis_id in ({q}) order by week"""):
        wk.setdefault(r["gsis_id"], []).append(r)
    av = {r["gsis_id"]: r for r in sql(f"""select gsis_id, games_played, round(ppg_std, 2)::float as ppg, round(expected_per_game, 2)::float as xppg,
                                                 round(targets_per_game, 2)::float as targets_per_game, round(carries_per_game, 2)::float as carries_per_game,
                                                 round(target_share, 3)::float as target_share, round(carry_share, 3)::float as carry_share,
                                                 round(air_yards_share, 3)::float as air_yards_share, round(avg_offense_snap_pct::numeric, 3)::float as snap_pct,
                                                 games_l3, round(points_per_game_l3, 2)::float as ppg_l3, round(target_share_l3, 3)::float as target_share_l3,
                                                 round(carry_share_l3, 3)::float as carry_share_l3, round(snap_pct_l3::numeric, 3)::float as snap_pct_l3,
                                                 round(first_read_share_std, 3)::float as first_read_target_share, injury_status
                                          from analytics.mart_player_availability where league_id = '{src}' and gsis_id in ({q})""")}
    seas = {r["gsis_id"]: r for r in sql(f"""select gsis_id, round(receiving_yards::numeric / nullif(games_played, 0), 1)::float as receiving_yards_pg,
                                                   round(rushing_yards::numeric / nullif(games_played, 0), 1)::float as rushing_yards_pg,
                                                   round(passing_yards::numeric / nullif(games_played, 0), 1)::float as passing_yards_pg,
                                                   round((receiving_tds + rushing_tds + passing_tds)::numeric / nullif(games_played, 0), 2)::float as tds_pg,
                                                   round(route_participation, 3)::float as route_participation
                                            from analytics.mart_player_season where season = {SEASON} and season_type = 'REG' and gsis_id in ({q})""")}
    ros = {r["gsis_id"]: r for r in sql(f"""select gsis_id, round(ros_points, 1)::float as points, ros_games as games, round(ros_p10, 1)::float as p10,
                                                  round(ros_p90, 1)::float as p90, ros_rank_pos as pos_rank, round(playoff_points, 1)::float as playoff_points
                                           from analytics.mart_player_ros_projection where league_id = '{src}' and gsis_id in ({q})""")}
    o = owners(league)
    out = {}
    for g in ids:
        h = heads.get(g)
        if not h or h["position"] not in SKILL:
            continue
        weeks = wk.get(g, [])
        this = next((w for w in weeks if w["week"] == WEEK), None)
        a, s = av.get(g, {}), seas.get(g, {})
        side = {
            **h,
            "team": (this or {}).get("team") or h["team"],
            "week": WEEK,
            "proj_points": (this or {}).get("proj_points"), "p10": (this or {}).get("p10"), "p25": (this or {}).get("p25"),
            "p75": (this or {}).get("p75"), "p90": (this or {}).get("p90"),
            "opponent": (this or {}).get("opponent"), "opp_rank": (this or {}).get("opp_rank"), "injury_status": a.get("injury_status"),
            "season_stats": {"games_played": a.get("games_played"), "ppg": a.get("ppg"), "xppg": a.get("xppg"),
                             "targets_per_game": a.get("targets_per_game"), "carries_per_game": a.get("carries_per_game"),
                             "receiving_yards_pg": s.get("receiving_yards_pg"), "rushing_yards_pg": s.get("rushing_yards_pg"),
                             "passing_yards_pg": s.get("passing_yards_pg"), "tds_pg": s.get("tds_pg")},
            "form": {"games_l3": a.get("games_l3"), "ppg_l3": a.get("ppg_l3"), "target_share_l3": a.get("target_share_l3"),
                     "carry_share_l3": a.get("carry_share_l3"), "snap_pct_l3": a.get("snap_pct_l3")},
            "usage": {"target_share": a.get("target_share"), "carry_share": a.get("carry_share"), "snap_pct": a.get("snap_pct"),
                      "route_participation": s.get("route_participation"), "first_read_target_share": a.get("first_read_target_share"),
                      "air_yards_share": a.get("air_yards_share")},
            "ros": ros.get(g) and {k: v for k, v in ros[g].items() if k != "gsis_id"},
            "next4": [{"week": w["week"], "opponent": w["opponent"], "is_home": w["is_home"], "opp_rank": w["opp_rank"]} for w in weeks],
        }
        out[g] = own(side, o)
    return out


def games(league: str, ids: list[str]) -> dict:
    src = scored(league)
    q = ",".join(f"'{g}'" for g in ids)
    rows = sql(f"""
        select g.gsis_id, g.season, g.week, g.opponent_team as opponent, g.is_home, g.played, g.offense_snap_pct, g.targets, g.receptions,
               g.receiving_yards, g.receiving_tds, g.carries, g.rushing_yards, g.rushing_tds, g.attempts, g.passing_yards, g.passing_tds,
               g.passing_interceptions, round(l.points, 2)::float as points,
               case when l.expected_known then round(l.points_expected, 2)::float end as expected_points
        from analytics.fct_player_game g
        join analytics.fct_player_game_league l on l.league_id = '{src}' and l.gsis_id = g.gsis_id and l.game_id = g.game_id
        where g.season in ({SEASON - 1}, {SEASON}) and g.season_type = 'REG' and g.gsis_id in ({q})
        order by g.gsis_id, g.season, g.week""")
    out: dict[str, list] = {}
    for r in rows:
        g = r.pop("gsis_id")
        out.setdefault(g, []).append(r)
    return out


def main() -> None:
    for league in (DYN, SCRUBS, TEST):
        t = trends(league)
        save(f"trends_{league}.json", t)
        save(f"matchups_defense_{league}_{TEAM[league]}.json", defense(league))
        save(f"matchups_cb_{league}_{TEAM[league]}.json", cb(league))
        p = players(league)
        save(f"players_{league}.json", p, compact=True)
        save(f"receivers_{league}.json", receivers(league))
        top = [r["gsis_id"] for r in p["players"][:60]] + [r["gsis_id"] for r in t["players"][:30]]
        ids = subjects(league, top)
        save(f"compare_{league}.json", compare_sides(league, ids), compact=True)
        save(f"games_{league}.json", games(league, ids), compact=True)
        print(league, len(t["players"]), len(p["players"]), len(ids))


if __name__ == "__main__":
    main()
