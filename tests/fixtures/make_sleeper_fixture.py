"""Generate a synthetic Sleeper archive that `league-lab ingest sleeper --offline` can replay.

Why: the Sleeper API is free and read-only, but development sandboxes (and CI) may not reach it.
The fixture uses *real* NFL players and their *real* weekly statistics (from the nflverse archive
already on disk) with *fake* league, user and roster identities, so every downstream join,
scoring reconciliation and metric test exercises realistic data without shipping anyone's
private league details in the repository.

Usage (after `league-lab ingest nfl --seasons 2024-2026`):
    uv run python tests/fixtures/make_sleeper_fixture.py --seasons 2024,2025,2026
    LEAGUE_LAB_SLEEPER_LEAGUE_ID=9000000000000002026 uv run league-lab ingest sleeper --offline

The generated archive lives under $LEAGUE_LAB_DATA_DIR/raw/sleeper (git-ignored).
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import random
from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from league_lab.config import get_settings
from league_lab.scoring import compute_points

ROSTER_POSITIONS = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "FLEX", "K", "DEF", "BN", "BN", "BN", "BN", "BN"]
SCORING = {  # half-PPR, 4-pt pass TD (matches League of Scrubs as fetched 2026-09-25)
    "pass_yd": 0.04, "pass_td": 4.0, "pass_int": -1.0, "pass_2pt": 2.0,
    "rush_yd": 0.1, "rush_td": 6.0, "rush_2pt": 2.0,
    "rec": 0.5, "rec_yd": 0.1, "rec_td": 6.0, "rec_2pt": 2.0,
    "fum": 0.0, "fum_lost": -2.0, "fum_rec_td": 6.0, "st_td": 6.0,
    "fgm_0_19": 3.0, "fgm_20_29": 3.0, "fgm_30_39": 3.0, "fgm_40_49": 4.0, "fgm_50p": 5.0, "fgmiss": -1.0,
    "xpm": 1.0, "xpmiss": -1.0,
    "sack": 1.0, "int": 2.0, "ff": 1.0, "fum_rec": 2.0, "def_td": 6.0, "safe": 2.0, "blk_kick": 2.0,
    "pts_allow_0": 10.0, "pts_allow_1_6": 7.0, "pts_allow_7_13": 4.0, "pts_allow_14_20": 1.0,
    "pts_allow_21_27": 0.0, "pts_allow_28_34": -1.0, "pts_allow_35p": -4.0,
}
NUM_TEAMS = 10
LEAGUE_ID_BASE = 9000000000000000000
NFL_TEAMS = ["ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE", "DAL", "DEN", "DET", "GB", "HOU", "IND", "JAX", "KC",
             "LAC", "LAR", "LV", "MIA", "MIN", "NE", "NO", "NYG", "NYJ", "PHI", "PIT", "SEA", "SF", "TB", "TEN", "WAS"]


def league_id_for(season: int) -> str:
    return str(LEAGUE_ID_BASE + season)


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(obj, separators=(",", ":")).encode()
    with gzip.open(path, "wb") as fh:
        fh.write(data)
    meta = {"url": f"fixture://{path.name}", "etag": None, "last_modified": None,
            "fetched_at": datetime.now(UTC).isoformat(), "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data)}
    path.with_name(path.name + ".meta.json").write_text(json.dumps(meta, indent=2))


def load_players(raw: Path) -> pl.DataFrame:
    ff = pl.read_csv(raw / "nflverse/ff_playerids/db_playerids.csv", infer_schema_length=0, null_values=["NA", ""])
    # dynastyprocess labels kickers "PK"; Sleeper and nflverse use "K"
    ff = ff.with_columns(pl.when(pl.col("position") == "PK").then(pl.lit("K")).otherwise(pl.col("position")).alias("position"))
    return ff.filter(pl.col("sleeper_id").is_not_null() & pl.col("gsis_id").is_not_null()
                     & pl.col("position").is_in(["QB", "RB", "WR", "TE", "K"]))


def season_stats(raw: Path, season: int) -> pl.DataFrame:
    df = pl.read_parquet(raw / f"nflverse/player_stats_week/stats_player_week_{season}.parquet")
    return df.filter(pl.col("season_type") == "REG")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", default="2024,2025,2026")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--current-week", type=int, default=3, help="weeks scored in the newest season")
    args = ap.parse_args()
    seasons = sorted(int(s) for s in args.seasons.split(","))
    rng = random.Random(args.seed)
    s = get_settings()
    raw = s.raw_dir
    out = raw / "sleeper"
    players = load_players(raw)
    by_sleeper = {r["sleeper_id"]: r for r in players.to_dicts()}

    users = [{"user_id": str(700000000000000000 + i), "display_name": f"manager_{i:02d}", "is_owner": i == 1,
              "avatar": None, "metadata": {"team_name": f"Synthetic Team {i:02d}"}, "settings": None, "is_bot": False}
             for i in range(1, NUM_TEAMS + 1)]

    prev_league_id = None
    for season in seasons:
        lid = league_id_for(season)
        stats = season_stats(raw, season)
        is_current = season == seasons[-1]
        weeks_scored = args.current_week if is_current else (16 if season == 2024 else 17)
        playoff_start = 15
        # --- draft pool: top players by prior-season PPR points (falls back to this season) --------------
        pool_src = season - 1
        try:
            pool_stats = season_stats(raw, pool_src)
        except FileNotFoundError:
            pool_stats = stats
        pool_pts = [(r["player_id"], r["position"], compute_points(r, SCORING)) for r in pool_stats.to_dicts()
                    if r["position"] in ("QB", "RB", "WR", "TE", "K") and r["player_id"]]
        totals = (pl.DataFrame(pool_pts, schema=["player_id", "position", "pts"], orient="row")
                  .group_by(["player_id", "position"]).agg(pl.col("pts").sum()).sort("pts", descending=True))
        gsis_to_sleeper = {r["gsis_id"]: r["sleeper_id"] for r in players.to_dicts()}
        ranked = [(gsis_to_sleeper[r["player_id"]], r["position"]) for r in totals.to_dicts() if r["player_id"] in gsis_to_sleeper]
        needs = {"QB": 2, "RB": 4, "WR": 4, "TE": 2, "K": 1}
        rosters_players: dict[int, list[str]] = {i: [] for i in range(1, NUM_TEAMS + 1)}
        picks = []
        order = list(range(1, NUM_TEAMS + 1)); rng.shuffle(order)
        pick_no = 0
        counts = {i: {p: 0 for p in needs} for i in rosters_players}
        avail = ranked[:]
        for rnd in range(1, 14):
            seq = order if rnd % 2 == 1 else order[::-1]
            for slot, rid in enumerate(seq, 1):
                for idx, (sid, pos) in enumerate(avail):
                    if counts[rid][pos] < needs[pos]:
                        avail.pop(idx); counts[rid][pos] += 1; rosters_players[rid].append(sid); pick_no += 1
                        meta = by_sleeper[sid]
                        picks.append({"draft_id": f"{lid}1", "draft_slot": slot, "is_keeper": None, "pick_no": pick_no,
                                      "picked_by": users[rid - 1]["user_id"], "player_id": sid, "reactions": None,
                                      "roster_id": rid, "round": rnd,
                                      "metadata": {"first_name": meta["name"].split(" ")[0], "last_name": " ".join(meta["name"].split(" ")[1:]),
                                                   "position": pos, "team": meta["team"], "player_id": sid, "sport": "nfl"}})
                        break
        for rid in rosters_players:  # team defense
            rosters_players[rid].append(NFL_TEAMS[(rid * 3 + season) % len(NFL_TEAMS)])

        # --- weekly points from real stats ------------------------------------------------------------------
        wk_stats = {(r["player_id"], r["week"]): r for r in stats.to_dicts()}
        def pts(sid: str, week: int) -> float | None:
            meta = by_sleeper.get(sid)
            if meta is None:  # DEF
                return round(rng.uniform(-2, 18), 2)
            row = wk_stats.get((meta["gsis_id"], week))
            if row is None:
                return 0.0
            return compute_points(row, SCORING)

        matchups: dict[int, list] = {}
        results = {rid: {"wins": 0, "losses": 0, "ties": 0, "fpts": 0.0, "fpts_against": 0.0} for rid in rosters_players}
        for week in range(1, weeks_scored + 1):
            pairs = list(rosters_players); rng.shuffle(pairs)
            week_rows = []
            for m_id, (a, b) in enumerate(zip(pairs[0::2], pairs[1::2]), 1):
                for rid in (a, b):
                    plist = rosters_players[rid]
                    scored = {sid: pts(sid, week) for sid in plist}
                    starters = []
                    used = set()
                    for slot in ROSTER_POSITIONS:
                        if slot == "BN":
                            continue
                        elig = {"FLEX": ["RB", "WR", "TE"], "DEF": ["DEF"]}.get(slot, [slot])
                        cands = [sid for sid in plist if sid not in used and (by_sleeper[sid]["position"] if sid in by_sleeper else "DEF") in elig]
                        cands.sort(key=lambda x: scored[x], reverse=True)
                        # sub-optimal lineups: 30% of the time start the second-best option
                        choice = cands[1] if len(cands) > 1 and rng.random() < 0.3 else (cands[0] if cands else "0")
                        starters.append(choice); used.add(choice)
                    sp = [scored.get(x, 0.0) for x in starters]
                    week_rows.append({"roster_id": rid, "matchup_id": m_id, "starters": starters, "starters_points": sp,
                                      "players": plist, "players_points": scored, "points": round(sum(sp), 2), "custom_points": None})
                ra, rb = week_rows[-2], week_rows[-1]
                results[a]["fpts"] += ra["points"]; results[b]["fpts"] += rb["points"]
                results[a]["fpts_against"] += rb["points"]; results[b]["fpts_against"] += ra["points"]
                if week < playoff_start:
                    if ra["points"] > rb["points"]: results[a]["wins"] += 1; results[b]["losses"] += 1
                    elif ra["points"] < rb["points"]: results[b]["wins"] += 1; results[a]["losses"] += 1
                    else: results[a]["ties"] += 1; results[b]["ties"] += 1
            matchups[week] = week_rows
        # future weeks in the current season come back with zero points and empty players_points
        if is_current:
            for week in range(weeks_scored + 1, 18):
                matchups[week] = []

        # --- transactions: 1-3 waiver moves per week + one trade in week 6 ---------------------------------
        tx_by_week: dict[int, list] = {w: [] for w in range(1, 18)}
        free_agents = [sid for sid, _ in avail[:200]]
        tid = 1
        for week in range(1, weeks_scored + 1):
            for _ in range(rng.randint(1, 3)):
                rid = rng.randint(1, NUM_TEAMS)
                bench = [sid for sid in rosters_players[rid] if sid in by_sleeper]
                drop = rng.choice(bench); add = rng.choice(free_agents)
                tx_by_week[week].append({"type": rng.choice(["waiver", "free_agent"]), "transaction_id": f"{lid}{tid:04d}",
                                         "status": "complete", "status_updated": 1700000000000 + week * 604800000,
                                         "created": 1700000000000 + week * 604800000 - 3600000, "creator": users[rid - 1]["user_id"],
                                         "roster_ids": [rid], "consenter_ids": [rid], "adds": {add: rid}, "drops": {drop: rid},
                                         "draft_picks": [], "waiver_budget": [], "settings": {"seq": tid}, "metadata": None, "leg": week})
                tid += 1
            if week == 6:
                a, b = 1, 2
                pa = rosters_players[a][0]; pb = rosters_players[b][0]
                tx_by_week[week].append({"type": "trade", "transaction_id": f"{lid}{tid:04d}", "status": "complete",
                                         "status_updated": 1700000000000 + week * 604800000, "created": 1700000000000 + week * 604800000 - 7200000,
                                         "creator": users[a - 1]["user_id"], "roster_ids": [a, b], "consenter_ids": [a, b],
                                         "adds": {pa: b, pb: a}, "drops": {pa: a, pb: b}, "draft_picks": [], "waiver_budget": [],
                                         "settings": None, "metadata": None, "leg": week})
                tid += 1

        # --- league, users, rosters, drafts, brackets -------------------------------------------------------------
        league = {
            "league_id": lid, "name": "Synthetic League of Scrubs", "season": str(season), "season_type": "regular",
            "status": "in_season" if is_current else "complete", "sport": "nfl", "total_rosters": NUM_TEAMS,
            "previous_league_id": prev_league_id, "draft_id": f"{lid}1", "roster_positions": ROSTER_POSITIONS,
            "scoring_settings": SCORING, "avatar": None, "bracket_id": None, "loser_bracket_id": None,
            "settings": {"num_teams": NUM_TEAMS, "playoff_week_start": playoff_start, "playoff_teams": 4, "leg": weeks_scored,
                         "last_scored_leg": weeks_scored, "start_week": 1, "trade_deadline": 11, "waiver_type": 0,
                         "waiver_budget": 100, "max_keepers": 1, "type": 0, "draft_rounds": 3, "reserve_slots": 2},
            "metadata": {"auto_continue": "on"},
        }
        rosters = []
        for rid, plist in rosters_players.items():
            r = results[rid]
            rosters.append({"roster_id": rid, "owner_id": users[rid - 1]["user_id"], "co_owners": None, "league_id": lid,
                            "players": plist, "starters": matchups[weeks_scored][0]["starters"] if False else [sid for sid in plist[:10]],
                            "reserve": None, "taxi": None, "keepers": None, "player_map": None,
                            "settings": {"wins": r["wins"], "losses": r["losses"], "ties": r["ties"],
                                         "fpts": int(r["fpts"]), "fpts_decimal": int(round((r["fpts"] % 1) * 100)),
                                         "fpts_against": int(r["fpts_against"]), "fpts_against_decimal": int(round((r["fpts_against"] % 1) * 100)),
                                         "waiver_position": rid, "waiver_budget_used": 0, "total_moves": 0},
                            "metadata": {"record": "W" * r["wins"] + "L" * r["losses"]}})
        drafts = [{"draft_id": f"{lid}1", "league_id": lid, "season": str(season), "season_type": "regular", "sport": "nfl",
                   "type": "snake", "status": "complete", "start_time": 1690000000000,
                   "settings": {"rounds": 13, "teams": NUM_TEAMS, "slots_qb": 1, "slots_rb": 2, "slots_wr": 2, "slots_te": 1,
                                "slots_flex": 2, "slots_k": 1, "slots_def": 1, "slots_bn": 5},
                   "draft_order": {users[rid - 1]["user_id"]: slot for slot, rid in enumerate(order, 1)},
                   "slot_to_roster_id": {str(slot): rid for slot, rid in enumerate(order, 1)},
                   "metadata": {"name": "Synthetic League of Scrubs", "scoring_type": "half_ppr"}, "creators": None, "created": 1690000000000}]
        standings = sorted(results, key=lambda rid: (results[rid]["wins"], results[rid]["fpts"]), reverse=True)[:4]
        winners = [] if is_current else [
            {"m": 1, "r": 1, "t1": standings[0], "t2": standings[3], "w": standings[0], "l": standings[3]},
            {"m": 2, "r": 1, "t1": standings[1], "t2": standings[2], "w": standings[1], "l": standings[2]},
            {"m": 3, "r": 2, "p": 1, "t1": standings[0], "t2": standings[1], "w": standings[0], "l": standings[1],
             "t1_from": {"w": 1}, "t2_from": {"w": 2}},
            {"m": 4, "r": 2, "p": 3, "t1": standings[3], "t2": standings[2], "w": standings[2], "l": standings[3],
             "t1_from": {"l": 1}, "t2_from": {"l": 2}},
        ]

        base = out / lid
        write_json(base / "league.json.gz", league)
        write_json(base / "users.json.gz", [dict(u, league_id=lid) for u in users])
        write_json(base / "rosters.json.gz", rosters)
        for week, rows in matchups.items():
            write_json(base / "matchups" / f"week_{week:02d}.json.gz", rows)
        for week, rows in tx_by_week.items():
            write_json(base / "transactions" / f"week_{week:02d}.json.gz", rows)
        write_json(base / "drafts.json.gz", drafts)
        write_json(base / f"draft_{lid}1_picks.json.gz", picks)
        write_json(base / "traded_picks.json.gz", [])
        write_json(base / "winners_bracket.json.gz", winners)
        write_json(base / "losers_bracket.json.gz", [])
        prev_league_id = lid
        print(f"season {season}: league {lid}, {weeks_scored} scored weeks, {len(picks)} picks, {sum(len(v) for v in tx_by_week.values())} transactions")

    # --- state + player directory (real players; shape mirrors /players/nfl) ------------------------------------------
    newest = seasons[-1]
    write_json(out / "state" / "nfl.json.gz", {"week": args.current_week, "leg": args.current_week, "season": str(newest),
                                               "season_type": "regular", "league_season": str(newest), "previous_season": str(newest - 1),
                                               "season_start_date": f"{newest}-09-09", "display_week": args.current_week,
                                               "league_create_season": str(newest), "season_has_scores": True})
    directory = {}
    for r in players.to_dicts():
        first, *rest = r["name"].split(" ")
        directory[r["sleeper_id"]] = {
            "player_id": r["sleeper_id"], "first_name": first, "last_name": " ".join(rest), "full_name": r["name"],
            "position": r["position"], "fantasy_positions": [r["position"]], "team": None if r["team"] in (None, "FA") else r["team"],
            "status": "Active", "active": True, "injury_status": None, "number": None, "years_exp": None, "age": None,
            "birth_date": r.get("birthdate"), "gsis_id": r["gsis_id"], "espn_id": r.get("espn_id"), "yahoo_id": r.get("yahoo_id"),
            "sportradar_id": r.get("sportradar_id"), "rotowire_id": r.get("rotowire_id"), "sport": "nfl",
        }
    for t in NFL_TEAMS:
        directory[t] = {"player_id": t, "first_name": t, "last_name": "Defense", "full_name": f"{t} Defense", "position": "DEF",
                        "fantasy_positions": ["DEF"], "team": t, "status": "Active", "active": True, "sport": "nfl"}
    write_json(out / "players" / "nfl.json.gz", directory)
    print(f"player directory: {len(directory)} entries; newest league id = {league_id_for(newest)}")


if __name__ == "__main__":
    main()
