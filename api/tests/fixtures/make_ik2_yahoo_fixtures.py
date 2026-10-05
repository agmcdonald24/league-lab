"""IK-2 (Wave I-K): build the SYNTHETIC Yahoo Fantasy Sports fixtures in ``api/tests/fixtures/yahoo/``.

Nothing here came from Yahoo (unreachable from the sandbox): every file is **synthetic**, shaped like the Fantasy
Sports API v2's ``?format=json`` answers as Yahoo's docs (sports.yahoo.com/developer/docs/) and the open-source clients
``yfpy`` / ``yahoo_fantasy_api`` document them — the nested ``{"0": …, "count": n}`` collections, the resource lists of
a metadata list plus sub-resources, ``transaction_data`` as a list for an add and an object for a drop. The players are
real (Sleeper fixture directory, with nflverse's real ``yahoo_id``), the league, teams, managers, points and moves are
invented. Each file carries a ``_comment`` saying so.

League ``461.l.4242`` "Synthetic Superflex League": 12 teams, QB / 2 RB / 3 WR / TE / W/R/T / Q/W/R/T / K / DEF,
6 BN, 1 IR, half-PPR, week 4 current (weeks 1–3 played), the fixture user (guid FIXTUREGUID3) manages team 3. The game
key 461 is the brief's example; live, the season's key is read from ``game/nfl``. League ``461.l.5151`` has no files: it
answers as Yahoo does for a private league the user is not in.

Run: ``python api/tests/fixtures/make_ik2_yahoo_fixtures.py`` (deterministic; rewrites the directory's JSON files).
"""

from __future__ import annotations

import csv
import json
import random
import re
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "yahoo"
GK = "461"
LK = f"{GK}.l.4242"
URL = "https://football.fantasysports.yahoo.com/f1/4242"
COMMENT = ("SYNTHETIC fixture (IK-2, Wave I-K): shaped like Yahoo Fantasy Sports API v2 ?format=json from Yahoo's docs "
           "and yfpy / yahoo_fantasy_api; not read from Yahoo. Real players (nflverse yahoo_id), invented league.")
WEEK = 4
N = 12
ME = 3
# Yahoo's NFL team ids (a team defense's player id is 100000 + this) and its abbreviations
YTEAM = {"Atl": 1, "Buf": 2, "Chi": 3, "Cin": 4, "Cle": 5, "Dal": 6, "Den": 7, "Det": 8, "GB": 9, "Ten": 10,
         "Ind": 11, "KC": 12, "LV": 13, "LAR": 14, "Mia": 15, "Min": 16, "NE": 17, "NO": 18, "NYG": 19, "NYJ": 20,
         "Phi": 21, "Ari": 22, "Pit": 23, "LAC": 24, "SF": 25, "Sea": 26, "TB": 27, "Was": 28, "Car": 29, "Jax": 30,
         "Bal": 33, "Hou": 34}
TEAM_NAME = {"Atl": "Atlanta Falcons", "Buf": "Buffalo Bills", "Chi": "Chicago Bears", "Cin": "Cincinnati Bengals",
             "Cle": "Cleveland Browns", "Dal": "Dallas Cowboys", "Den": "Denver Broncos", "Det": "Detroit Lions",
             "GB": "Green Bay Packers", "Ten": "Tennessee Titans", "Ind": "Indianapolis Colts", "KC": "Kansas City Chiefs",
             "LV": "Las Vegas Raiders", "LAR": "Los Angeles Rams", "Mia": "Miami Dolphins", "Min": "Minnesota Vikings",
             "NE": "New England Patriots", "NO": "New Orleans Saints", "NYG": "New York Giants", "NYJ": "New York Jets",
             "Phi": "Philadelphia Eagles", "Ari": "Arizona Cardinals", "Pit": "Pittsburgh Steelers",
             "LAC": "Los Angeles Chargers", "SF": "San Francisco 49ers", "Sea": "Seattle Seahawks",
             "TB": "Tampa Bay Buccaneers", "Was": "Washington Commanders", "Car": "Carolina Panthers",
             "Jax": "Jacksonville Jaguars", "Bal": "Baltimore Ravens", "Hou": "Houston Texans"}
SLEEPER_TO_Y = {k.upper(): k for k in YTEAM} | {"JAX": "Jax", "WAS": "Was"}
ROSTER = [("QB", 1, "O"), ("WR", 3, "O"), ("RB", 2, "O"), ("TE", 1, "O"), ("W/R/T", 1, "O"), ("Q/W/R/T", 1, "O"),
          ("K", 1, "K"), ("DEF", 1, "DT"), ("BN", 6, None), ("IR", 1, None)]
STATS = [  # (id, name, display, position type, value, bonuses)
    (4, "Passing Yards", "Pass Yds", "O", "0.04", [(300, 2), (400, 2)]), (5, "Passing Touchdowns", "Pass TD", "O", "4", None),
    (6, "Interceptions", "Int", "O", "-1", None), (9, "Rushing Yards", "Rush Yds", "O", "0.1", None),
    (10, "Rushing Touchdowns", "Rush TD", "O", "6", None), (11, "Receptions", "Rec", "O", "0.5", None),
    (12, "Receiving Yards", "Rec Yds", "O", "0.1", None), (13, "Receiving Touchdowns", "Rec TD", "O", "6", None),
    (15, "Return Touchdowns", "Ret TD", "O", "6", None), (16, "2-Point Conversions", "2-PT", "O", "2", None),
    (18, "Fumbles Lost", "Fum Lost", "O", "-2", None), (57, "Offensive Fumble Return TD", "Fum Ret TD", "O", "6", None),
    (19, "Field Goals 0-19 Yards", "FG 0-19", "K", "3", None), (20, "Field Goals 20-29 Yards", "FG 20-29", "K", "3", None),
    (21, "Field Goals 30-39 Yards", "FG 30-39", "K", "3", None), (22, "Field Goals 40-49 Yards", "FG 40-49", "K", "4", None),
    (23, "Field Goals 50+ Yards", "FG 50+", "K", "5", None), (29, "Point After Attempt Made", "PAT Made", "K", "1", None),
    (32, "Sack", "Sack", "DT", "1", None), (33, "Interception", "Int", "DT", "2", None),
    (34, "Fumble Recovery", "Fum Rec", "DT", "2", None), (35, "Touchdown", "TD", "DT", "6", None),
    (36, "Safety", "Safe", "DT", "2", None), (37, "Block Kick", "Blk Kick", "DT", "2", None),
    (49, "Kickoff and Punt Return Touchdowns", "Ret TD", "DT", "6", None),
    (50, "Points Allowed 0 points", "Pts Allow 0", "DT", "10", None), (51, "Points Allowed 1-6 points", "Pts Allow 1-6", "DT", "7", None),
    (52, "Points Allowed 7-13 points", "Pts Allow 7-13", "DT", "4", None), (53, "Points Allowed 14-20 points", "Pts Allow 14-20", "DT", "1", None),
    (54, "Points Allowed 21-27 points", "Pts Allow 21-27", "DT", "0", None), (55, "Points Allowed 28-34 points", "Pts Allow 28-34", "DT", "-1", None),
    (56, "Points Allowed 35+ points", "Pts Allow 35+", "DT", "-4", None), (82, "Extra Point Returned", "XPR", "DT", "2", None),
]

def _week_dates() -> list[tuple[int, str, str]]:
    import datetime as dt
    out = [(1, "2026-09-10", "2026-09-14")]
    start = dt.date(2026, 9, 15)
    for w in range(2, 19):
        out.append((w, start.isoformat(), (start + dt.timedelta(days=6)).isoformat()))
        start += dt.timedelta(days=7)
    return out


def coll(name: str, members: list) -> dict:
    d: dict = {str(i): {name: m} for i, m in enumerate(members)}
    d["count"] = len(members)
    return d


def write(path: str, content: dict) -> None:
    name = re.sub(r"[^A-Za-z0-9.]+", "_", path).strip("_") + ".json"
    body = {"_comment": COMMENT, "fantasy_content": {"xml:lang": "en-US", "yahoo:uri": f"/fantasy/v2/{path}",
                                                     **content, "time": "21.4ms", "copyright": "Data synthetic",
                                                     "refresh_rate": "60"}}
    (OUT / name).write_text(json.dumps(body, indent=1, ensure_ascii=False) + "\n")


def league_meta() -> dict:
    return {"league_key": LK, "league_id": "4242", "name": "Synthetic Superflex League", "url": URL, "logo_url": False,
            "draft_status": "postdraft", "num_teams": N, "edit_key": str(WEEK), "weekly_deadline": "",
            "league_update_timestamp": "1790900000", "scoring_type": "head", "league_type": "public",
            "renew": "", "renewed": "", "short_invitation_url": "", "allow_add_to_dl_extra_pos": 0,
            "is_pro_league": "0", "is_cash_league": "0", "current_week": WEEK, "start_week": "1",
            "start_date": "2026-09-10", "end_week": "17", "end_date": "2026-12-28", "game_code": "nfl", "season": "2026"}


def team_meta(t: int, faab: int = 100) -> list:
    me = t == ME
    mgr = {"manager_id": str(t), "nickname": f"Manager {t}", "guid": f"FIXTUREGUID{t}",
           "image_url": "https://s.yimg.com/ag/images/default_user_profile_pic_64sq.jpg", "felo_score": "650",
           "felo_tier": "silver"}
    if t == 1:
        mgr["is_commissioner"] = "1"
    if me:
        mgr["is_current_login"] = "1"
    return [{"team_key": f"{LK}.t.{t}"}, {"team_id": str(t)}, {"name": f"Synthetic Team {t}"}, [],
            {"url": f"{URL}/{t}"}, {"team_logos": [{"team_logo": {"size": "large", "url": "https://s.yimg.com/cv/x.png"}}]},
            [], {"waiver_priority": (t + 4) % N + 1}, {"faab_balance": str(faab)}, {"number_of_moves": t % 4},
            {"number_of_trades": 1 if t in (2, 7) else 0},
            {"roster_adds": {"coverage_type": "week", "coverage_value": WEEK, "value": "0"}}, [],
            {"league_scoring_type": "head"}, [], [], {"has_draft_grade": 0}, [], [],
            {"managers": [{"manager": mgr}]}]


def player_meta(p: dict) -> list:
    pos = p["pos"]
    elig = {"QB": ["QB", "Q/W/R/T"], "RB": ["RB", "W/R/T", "Q/W/R/T"], "WR": ["WR", "W/R/T", "Q/W/R/T"],
            "TE": ["TE", "W/R/T", "Q/W/R/T"], "K": ["K"], "DEF": ["DEF"]}[pos]
    first, _, last = p["name"].partition(" ")
    meta = [{"player_key": f"{GK}.p.{p['yid']}"}, {"player_id": str(p["yid"])},
            {"name": {"full": p["name"], "first": first, "last": last, "ascii_first": first, "ascii_last": last}}]
    if p.get("status"):
        meta += [{"status": p["status"]}, {"status_full": {"Q": "Questionable", "O": "Out", "IR": "Injured Reserve"}[p["status"]]},
                 {"injury_note": "Hamstring"}]
    meta += [{"editorial_player_key": f"nfl.p.{p['yid']}"}, {"editorial_team_key": f"nfl.t.{YTEAM.get(p['team'], 0)}"},
             {"editorial_team_full_name": TEAM_NAME.get(p["team"], "")}, {"editorial_team_abbr": p["team"]},
             {"editorial_team_url": ""}, {"bye_weeks": {"week": str(5 + YTEAM.get(p["team"], 1) % 10)}},
             {"is_keeper": {"status": False, "cost": False, "kept": False}}, {"uniform_number": "" if pos == "DEF" else "1"},
             {"display_position": pos},
             {"headshot": {"url": "https://s.yimg.com/iu/x.png", "size": "small"}, "image_url": "https://s.yimg.com/iu/x.png"},
             {"is_undroppable": "0"}, {"position_type": {"K": "K", "DEF": "DT"}.get(pos, "O")},
             {"primary_position": pos}, {"eligible_positions": [{"position": e} for e in elig]},
             {"has_player_notes": 1}, {"player_notes_last_timestamp": 1790000000}]
    return meta


def pools() -> dict[str, list[dict]]:
    ids = {r["sleeper_id"]: r for r in csv.DictReader((HERE / "ff" / "db_playerids.csv").open(encoding="utf-8"))
           if r["yahoo_id"] not in ("NA", "") and r["sleeper_id"] not in ("NA", "")}
    d = json.loads((HERE / "sleeper" / "players_nfl.json").read_text())
    seen: Counter = Counter()
    for f in sorted((HERE / "sleeper").glob("rosters_*.json")):
        for r in json.loads(f.read_text()):
            seen.update(str(x) for x in (r.get("players") or []))
    out: dict[str, list[dict]] = {"QB": [], "RB": [], "WR": [], "TE": [], "K": []}
    for sid in sorted(ids, key=lambda s: (-seen[s], int(s) if s.isdigit() else 0)):
        p = d.get(sid)
        if not p or not p.get("team") or p.get("position") not in out:
            continue
        team = SLEEPER_TO_Y.get(str(p["team"]).upper())
        if team is None:
            continue
        out[p["position"]].append({"yid": int(ids[sid]["yahoo_id"]), "name": p.get("full_name") or ids[sid]["name"],
                                   "pos": p["position"], "team": team, "sleeper_id": sid})
    return out


def main() -> None:
    OUT.mkdir(exist_ok=True)
    for f in OUT.glob("*.json"):
        f.unlink()
    rnd = random.Random(4242)
    pl = pools()
    need = {"QB": 2, "RB": 5, "WR": 6, "TE": 2, "K": 1}
    rosters: dict[int, list[dict]] = {t: [] for t in range(1, N + 1)}
    for pos, n in need.items():
        for rnd_i in range(n):
            order = list(range(1, N + 1)) if rnd_i % 2 == 0 else list(range(N, 0, -1))
            for t in order:
                rosters[t].append(dict(pl[pos].pop(0)))
    defs = sorted(YTEAM)
    rnd.shuffle(defs)
    for t in range(1, N + 1):
        team = defs.pop()
        rosters[t].append({"yid": 100000 + YTEAM[team], "name": TEAM_NAME[team], "pos": "DEF", "team": team})
    # one player Yahoo has that the id table lacks (left as yahoo:99001) and one matched by name only
    rosters[ME].append({"yid": 99001, "name": "Synthetic Prospect", "pos": "WR", "team": "KC"})
    nm = pl["TE"].pop(0)
    rosters[5].append({**nm, "yid": 99002})
    free = [p for pos in ("QB", "RB", "WR", "TE", "K") for p in pl[pos][:6]]

    # week-4 lineups: QB, WR×3, RB×2, TE, W/R/T, Q/W/R/T, K, DEF; the 6th RB (or the last one) on IR
    for t, ps in rosters.items():
        by = {k: [p for p in ps if p["pos"] == k] for k in ("QB", "RB", "WR", "TE", "K", "DEF")}
        for p in ps:
            p["sel"] = "BN"
        def put(pos: str, slot: str, n: int = 1, by: dict = by) -> None:
            for p in [x for x in by[pos] if x["sel"] == "BN"][:n]:
                p["sel"] = slot
        put("QB", "QB")
        put("WR", "WR", 3)
        put("RB", "RB", 2)
        put("TE", "TE")
        put("K", "K")
        put("DEF", "DEF")
        put("RB" if t % 2 else "WR", "W/R/T")
        put("QB", "Q/W/R/T")
        ir = [x for x in by["RB"] if x["sel"] == "BN"][-1]
        ir["sel"], ir["status"] = "IR", "IR"
    rosters[ME][3]["status"] = "Q"

    write("game/nfl", {"game": [{"game_key": GK, "game_id": GK, "name": "Football", "code": "nfl", "type": "full",
                                 "url": "https://football.fantasysports.yahoo.com/f1", "season": "2026",
                                 "is_registration_over": 0, "is_game_over": 0, "is_offseason": 0}]})
    write(f"game/{GK}/game_weeks", {"game": [{"game_key": GK, "game_id": GK, "code": "nfl", "season": "2026"},
                                             {"game_weeks": coll("game_week", [{"week": str(w), "display_name": str(w),
                                                                                "start": s, "end": e}
                                                                               for w, s, e in _week_dates()])}]})
    settings = {"draft_type": "live", "is_auction_draft": "0", "scoring_type": "head", "persistent_url": URL,
                "uses_playoff": "1", "has_playoff_consolation_games": True, "playoff_start_week": "15",
                "uses_playoff_reseeding": 0, "uses_lock_eliminated_teams": 0, "num_playoff_teams": "6",
                "num_playoff_consolation_teams": 6, "has_multiweek_championship": 0, "waiver_type": "FR",
                "waiver_rule": "all", "uses_faab": "1", "draft_pick_time": "90", "post_draft_players": "W",
                "max_teams": "12", "waiver_time": "2", "trade_end_date": "2026-11-20", "trade_ratify_type": "commish",
                "trade_reject_time": "2", "player_pool": "ALL", "cant_cut_list": "yahoo", "draft_together": 0,
                "is_publicly_viewable": "1", "can_trade_draft_picks": "0",
                "roster_positions": [{"roster_position": {"position": p, **({"position_type": t} if t else {}), "count": n,
                                                          "is_starting_position": 0 if p in ("BN", "IR") else 1}}
                                     for p, n, t in ROSTER],
                "stat_categories": {"stats": [{"stat": {"stat_id": i, "enabled": "1", "name": nm, "display_name": dn,
                                                        "group": {"O": "offense", "K": "kicking", "DT": "defense"}[pt],
                                                        "abbr": dn, "sort_order": "1", "position_type": pt,
                                                        "stat_position_types": [{"stat_position_type": {"position_type": pt}}]}}
                                              for i, nm, dn, pt, _v, _b in STATS]},
                "stat_modifiers": {"stats": [{"stat": {"stat_id": i, "value": v,
                                                       **({"bonuses": [{"bonus": {"target": str(a), "points": str(b)}} for a, b in bon]}
                                                          if bon else {})}} for i, _n, _d, _p, v, bon in STATS]},
                "max_weekly_adds": "0", "uses_median_score": "", "league_premium_features": [],
                "min_games_played": 0, "week_has_enough_qualifying_days": []}
    write(f"league/{LK}/settings", {"league": [league_meta(), {"settings": [settings]}]})

    # scoreboards: weeks 1–3 played, week 4 under way (the Thursday game)
    pairs_by_week = {}
    for w in range(1, WEEK + 1):
        teams = list(range(1, N + 1))
        r = teams[1:]
        r = r[-(w - 1) % len(r):] + r[:-(w - 1) % len(r)] if w > 1 else r
        order = [teams[0]] + r
        pairs_by_week[w] = [(order[i], order[N - 1 - i]) for i in range(N // 2)]
    rec = {t: {"w": 0, "l": 0, "t": 0, "pf": 0.0, "pa": 0.0} for t in range(1, N + 1)}
    for w in range(1, WEEK + 1):
        ms = []
        for a, b in pairs_by_week[w]:
            if w < WEEK:
                pa, pb = round(rnd.uniform(85, 150), 2), round(rnd.uniform(85, 150), 2)
                status, winner = "postevent", (a if pa > pb else b)
            else:
                pa, pb = (round(rnd.uniform(0, 18), 2), round(rnd.uniform(0, 18), 2))
                status, winner = "midevent", None
            if w < WEEK:
                rec[a]["pf"] += pa
                rec[a]["pa"] += pb
                rec[b]["pf"] += pb
                rec[b]["pa"] += pa
                rec[winner]["w"] += 1
                rec[b if winner == a else a]["l"] += 1
            def side(t: int, pts: float, w: int = w) -> dict:
                return {"team": [team_meta(t), {"team_points": {"coverage_type": "week", "week": str(w), "total": f"{pts:.2f}"},
                                                "team_projected_points": {"coverage_type": "week", "week": str(w),
                                                                          "total": f"{rnd.uniform(95, 125):.2f}"}}]}
            m = {"week": str(w), "week_start": _week_dates()[w - 1][1], "week_end": _week_dates()[w - 1][2],
                 "status": status, "is_playoffs": "0", "is_consolation": "0", "is_matchup_of_the_week": "0",
                 "is_tied": 0, **({"winner_team_key": f"{LK}.t.{winner}"} if winner else {}),
                 "0": {"teams": {"0": side(a, pa), "1": side(b, pb), "count": 2}}}
            ms.append(m)
        write(f"league/{LK}/scoreboard;week={w}",
              {"league": [league_meta(), {"scoreboard": {"0": {"matchups": coll("matchup", ms)}, "week": str(w)}}]})
    write(f"league/{LK}/teams", {"league": [league_meta(), {"teams": coll("team", [team_meta(t) for t in range(1, N + 1)])}]})
    ranked = sorted(rec, key=lambda t: (-rec[t]["w"], -rec[t]["pf"]))
    write(f"league/{LK}/standings", {"league": [league_meta(), {"standings": [{"teams": coll("team", [
        [team_meta(t), {"team_points": {"coverage_type": "season", "season": "2026", "total": f"{rec[t]['pf']:.2f}"}},
         {"team_standings": {"rank": ranked.index(t) + 1, "playoff_seed": str(ranked.index(t) + 1),
                             "outcome_totals": {"wins": rec[t]["w"], "losses": rec[t]["l"], "ties": rec[t]["t"],
                                                "percentage": f"{rec[t]['w'] / max(1, WEEK - 1):.3f}"},
                             "streak": {"type": "win", "value": "1"},
                             "points_for": f"{rec[t]['pf']:.2f}", "points_against": f"{rec[t]['pa']:.2f}"}}]
        for t in range(1, N + 1)])}]}]})
    # transactions (newest first, as Yahoo lists them): an add/drop in week 2, a FAAB claim and a trade in week 3,
    # a drop and an add in week 4
    def tp(p: dict, data: dict | list) -> dict:
        return {"player": [player_meta(p)[:3] + [{"editorial_team_abbr": p["team"]}, {"display_position": p["pos"]},
                                                 {"position_type": "O"}], {"transaction_data": data}]}
    def bench(t: int, i: int) -> dict:
        return [p for p in rosters[t] if p["sel"] == "BN" and p["pos"] != "DEF"][i]
    a1, d1 = free.pop(), bench(4, 0)
    a2, d2 = free.pop(), bench(9, 1)
    tr_a, tr_b = bench(2, 0), bench(7, 0)
    d3, a3 = bench(11, 2), free.pop()
    txs = [
        {"transaction_key": f"{LK}.tr.31", "transaction_id": "31", "type": "add", "status": "successful",
         "timestamp": "1790988000", "players": coll("player", [])},
        {"transaction_key": f"{LK}.tr.30", "transaction_id": "30", "type": "drop", "status": "successful",
         "timestamp": "1790901000"},
        {"transaction_key": f"{LK}.tr.22", "transaction_id": "22", "type": "trade", "status": "successful",
         "timestamp": "1790380800", "trader_team_key": f"{LK}.t.2", "trader_team_name": "Synthetic Team 2",
         "tradee_team_key": f"{LK}.t.7", "tradee_team_name": "Synthetic Team 7"},
        {"transaction_key": f"{LK}.tr.21", "transaction_id": "21", "type": "add/drop", "status": "successful",
         "timestamp": "1790323200", "faab_bid": "14"},
        {"transaction_key": f"{LK}.tr.12", "transaction_id": "12", "type": "add/drop", "status": "successful",
         "timestamp": "1789732800"},
    ]
    plist = [
        [tp(a3, [{"type": "add", "source_type": "freeagents", "destination_type": "team",
                  "destination_team_key": f"{LK}.t.11", "destination_team_name": "Synthetic Team 11"}])],
        [tp(d3, {"type": "drop", "source_type": "team", "source_team_key": f"{LK}.t.11",
                 "source_team_name": "Synthetic Team 11", "destination_type": "waivers"})],
        [tp(tr_a, [{"type": "trade", "source_type": "team", "source_team_key": f"{LK}.t.2", "source_team_name": "Synthetic Team 2",
                    "destination_type": "team", "destination_team_key": f"{LK}.t.7", "destination_team_name": "Synthetic Team 7"}]),
         tp(tr_b, [{"type": "trade", "source_type": "team", "source_team_key": f"{LK}.t.7", "source_team_name": "Synthetic Team 7",
                    "destination_type": "team", "destination_team_key": f"{LK}.t.2", "destination_team_name": "Synthetic Team 2"}])],
        [tp(a2, [{"type": "add", "source_type": "waivers", "destination_type": "team",
                  "destination_team_key": f"{LK}.t.9", "destination_team_name": "Synthetic Team 9"}]),
         tp(d2, {"type": "drop", "source_type": "team", "source_team_key": f"{LK}.t.9",
                 "source_team_name": "Synthetic Team 9", "destination_type": "waivers"})],
        [tp(a1, [{"type": "add", "source_type": "freeagents", "destination_type": "team",
                  "destination_team_key": f"{LK}.t.4", "destination_team_name": "Synthetic Team 4"}]),
         tp(d1, {"type": "drop", "source_type": "team", "source_team_key": f"{LK}.t.4",
                 "source_team_name": "Synthetic Team 4", "destination_type": "waivers"})],
    ]
    # the week-4 rosters reflect the moves: the week-3 trade swapped tr_a / tr_b, the dropped players are gone
    for t, gone, came in ((4, d1, a1), (9, d2, a2), (11, d3, a3), (2, tr_a, tr_b), (7, tr_b, tr_a)):
        rosters[t] = [p for p in rosters[t] if p is not gone] + [{**came, "sel": "BN"}]
    tx = [[meta, {"players": coll("player", [x["player"] for x in ps])}] for meta, ps in zip(txs, plist, strict=True)]
    for meta in txs:
        meta.pop("players", None)
    write(f"league/{LK}/transactions", {"league": [league_meta(), {"transactions": coll("transaction", tx)}]})
    for t, ps in rosters.items():
        players = [[player_meta(p), {"selected_position": [{"coverage_type": "week", "week": str(WEEK)},
                                                           {"position": p["sel"]},
                                                           {"is_flex": 1 if "/" in p["sel"] else 0}]}] for p in ps]
        write(f"team/{LK}.t.{t}/roster;week={WEEK}/players",
              {"team": [team_meta(t), {"roster": {"coverage_type": "week", "week": str(WEEK), "is_prescoring": False,
                                                 "is_editable": 0, "0": {"players": coll("player", players)},
                                                 "outs": {"0": {"player": []}, "count": 0}}}]})
    write(f"league/{LK}/players;status=FA;sort=AR;start=0;count=25",
          {"league": [league_meta(), {"players": coll("player", [player_meta(p) for p in free[:25]])}]})


    # the signed-in user's game, leagues and teams
    game = {"game_key": GK, "game_id": GK, "name": "Football", "code": "nfl", "type": "full",
            "url": "https://football.fantasysports.yahoo.com/f1", "season": "2026", "is_registration_over": 0,
            "is_game_over": 0, "is_offseason": 0}
    write("users;use_login=1/games;game_keys=nfl/leagues",
          {"users": coll("user", [[{"guid": "FIXTUREGUID3"}, {"games": coll("game", [[game, {"leagues": coll("league", [[league_meta()]])}]])}]])})
    write("users;use_login=1/games;game_keys=nfl/teams",
          {"users": coll("user", [[{"guid": "FIXTUREGUID3"}, {"games": coll("game", [[game, {"teams": coll("team", [team_meta(ME)])}]])}]])})
    print(f"wrote {len(list(OUT.glob('*.json')))} files to {OUT}")


if __name__ == "__main__":
    main()
