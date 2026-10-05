"""Wave I-K (IK-1): the synthetic ESPN leagues (run once, from the repository root; deterministic):

    uv run python api/tests/fixtures/make_ik1_fixtures.py

Writes ``espn_leagues/4242/`` — "Synthetic Public League": public, 10 teams, season 2026, ESPN's current scoring period
4 (weeks 1–3 scored, week 4's Thursday game played), half-PPR with a half-point TE premium, ESPN's default lineup
(QB, RB×2, WR×2, TE, FLEX, D/ST, K, bench 7, IR 1) — and ``espn_leagues/5150/`` — "Synthetic Private League", the same
league marked private (``_private``: 401 without the manager's cookies).

**Synthetic, built from the documented shapes** (no ESPN call: ESPN is unreachable from this sandbox): the JSON field
names and nesting follow cwendt94/espn-api's football modules and its unit-test data (a real 2018 response,
``tests/football/unit/data/league_2018_data.json``); the ids follow its ``constant.py``. Every file says so in its
``_synthetic`` key. The rosters mirror the Sleeper fixtures' Test League (``sleeper/rosters_9000000000000000001.json``)
with each player's ESPN id from ``ff/db_playerids.csv``, plus three made-up cases: an ESPN id the id table lacks and no
name matches (``99990001`` "Synthetic Rookie", a bench WR on team 1; ``99990002`` "Practice Squad Callup", team 2's
FLEX starter) — both stay ``espn:<id>`` — and an ESPN id the table lacks whose name and position match one Sleeper
player (``99990003``, the Test League's kicker 13545). Team ids skip 10 (1–9, 11), as real ESPN leagues can.
"""

from __future__ import annotations

import csv
import json
import random
import shutil
from pathlib import Path

FX = Path(__file__).resolve().parent
OUT = FX / "espn_leagues"
SEASON, WEEK, TEAMS = 2026, 4, 10
NOTE = ("SYNTHETIC — built for League Lab's tests from the documented shapes (cwendt94/espn-api: football modules, "
        "constant.py, tests/football/unit/data/league_2018_data.json); not an ESPN answer. "
        "api/tests/fixtures/make_ik1_fixtures.py writes it.")
PRO = {"ATL": 1, "BUF": 2, "CHI": 3, "CIN": 4, "CLE": 5, "DAL": 6, "DEN": 7, "DET": 8, "GB": 9, "TEN": 10, "IND": 11,
       "KC": 12, "LV": 13, "LAR": 14, "MIA": 15, "MIN": 16, "NE": 17, "NO": 18, "NYG": 19, "NYJ": 20, "PHI": 21,
       "ARI": 22, "PIT": 23, "LAC": 24, "SF": 25, "SEA": 26, "TB": 27, "WAS": 28, "CAR": 29, "JAX": 30, "BAL": 33,
       "HOU": 34}
NICK = {"PHI": "Eagles", "NE": "Patriots", "KC": "Chiefs", "BAL": "Ravens", "CAR": "Panthers", "LAR": "Rams",
        "SF": "49ers", "PIT": "Steelers", "MIN": "Vikings", "CIN": "Bengals", "SEA": "Seahawks", "DAL": "Cowboys",
        "DEN": "Broncos", "GB": "Packers", "BUF": "Bills", "DET": "Lions"}
POS_ID = {"QB": 1, "RB": 2, "WR": 3, "TE": 4, "K": 5, "DEF": 16}
ELIG = {"QB": [0, 7, 20, 21], "RB": [2, 3, 23, 7, 20, 21], "WR": [3, 4, 5, 23, 7, 20, 21], "TE": [5, 6, 23, 7, 20, 21],
        "K": [17, 20, 21], "DEF": [16, 20, 21]}
INJ = {None: "ACTIVE", "Questionable": "QUESTIONABLE", "Doubtful": "DOUBTFUL", "Out": "OUT", "IR": "INJURY_RESERVE"}
TEAM_IDS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 11]
NAMES = [("name", "Gridiron Gurus"), ("name", "Fourth and Long"), ("loc", ("Mighty", "Ducks")),
         ("name", "The Waiver Wire"), ("name", "Bye Week Blues"), ("loc", ("Taco", "Tuesday")),
         ("name", "Red Zone Rascals"), ("name", "Hail Mary Heroes"), ("name", "Punt Formation"),
         ("name", "Synthetic Sharks")]
T0 = 1788000000000                 # 2026-08-29 (ms): the synthetic draft
DAY = 86400000
FAKE = {99990001: ("Synthetic Rookie", "WR", "NYJ"), 99990002: ("Practice Squad Callup", "RB", "TEN")}
NAME_MATCH = 99990003


def _top(lid: int) -> dict:
    return {"_synthetic": NOTE, "gameId": 1, "id": lid, "scoringPeriodId": WEEK, "seasonId": SEASON, "segmentId": 0}


def _player(pid: int, name: str, pos: str, team: str | None, injury: str | None = None) -> dict:
    first, _, last = name.partition(" ")
    return {"active": True, "defaultPositionId": POS_ID[pos], "droppable": True, "eligibleSlots": ELIG[pos],
            "firstName": first, "fullName": name, "id": pid, "injured": injury not in (None, "Questionable"),
            "injuryStatus": INJ.get(injury, "ACTIVE"), "lastName": last, "proTeamId": PRO.get(team or "", 0),
            "ownership": {"percentOwned": 50.0, "percentStarted": 25.0}, "universeId": 1}


def _dst(team: str) -> dict:
    pid = -16000 - PRO[team]
    nick = NICK.get(team, team)
    return {"active": True, "defaultPositionId": 16, "droppable": True, "eligibleSlots": ELIG["DEF"], "firstName": nick,
            "fullName": f"{nick} D/ST", "id": pid, "injured": False, "injuryStatus": "ACTIVE", "lastName": "D/ST",
            "proTeamId": PRO[team], "ownership": {"percentOwned": 60.0, "percentStarted": 40.0}, "universeId": 1}


def _entry(p: dict, slot: int, on_team: int) -> dict:
    return {"acquisitionDate": T0, "acquisitionType": "DRAFT", "injuryStatus": "NORMAL", "lineupSlotId": slot,
            "pendingTransactionIds": None, "playerId": p["id"],
            "playerPoolEntry": {"appliedStatTotal": 0.0, "id": p["id"], "keeperValue": 0, "keeperValueFuture": 0,
                                "lineupLocked": False, "onTeamId": on_team, "player": p, "rosterLocked": False,
                                "status": "ONTEAM", "tradeLocked": False},
            "status": "NORMAL"}


def _settings(name: str, public: bool) -> dict:
    counts = {str(i): 0 for i in range(25)}
    counts.update({"0": 1, "2": 2, "4": 2, "6": 1, "16": 1, "17": 1, "20": 7, "21": 1, "23": 1})

    def item(sid: int, pts: float, dst: float | None = None, **over) -> dict:
        o = {} if dst is None else {"16": dst}
        o.update({str(k[1:]): v for k, v in over.items()})
        d = {"isReverseItem": False, "leagueRanking": 0.0, "leagueTotal": 0.0, "points": pts, "statId": sid}
        if o:
            d["pointsOverrides"] = o
        return d
    items = [item(3, 0.04), item(4, 4.0), item(19, 2.0), item(20, -2.0), item(24, 0.1), item(25, 6.0), item(26, 2.0),
             item(42, 0.1), item(43, 6.0), item(44, 2.0), item(53, 0.5, s6=1.0), item(63, 6.0), item(72, -2.0),
             item(74, 5.0), item(77, 4.0), item(80, 3.0), item(85, -1.0), item(86, 1.0), item(88, -1.0),
             item(89, 0.0, 5.0), item(90, 0.0, 4.0), item(91, 0.0, 3.0), item(92, 0.0, 1.0), item(121, 0.0, 0.0),
             item(122, 0.0, 0.0), item(123, 0.0, -1.0), item(124, 0.0, -3.0), item(125, 0.0, -5.0),
             item(95, 0.0, 2.0), item(96, 0.0, 2.0), item(97, 0.0, 2.0), item(98, 0.0, 2.0), item(99, 0.0, 1.0),
             item(93, 6.0, 6.0), item(101, 6.0, 6.0), item(102, 6.0, 6.0), item(103, 0.0, 6.0), item(104, 0.0, 6.0),
             item(128, 0.0, 5.0), item(129, 0.0, 3.0), item(130, 0.0, 2.0), item(131, 0.0, 0.0), item(132, 0.0, -1.0),
             item(133, 0.0, -3.0), item(134, 0.0, -5.0), item(135, 0.0, -6.0), item(136, 0.0, -7.0)]
    return {"acquisitionSettings": {"acquisitionBudget": 100, "acquisitionLimit": -1, "acquisitionType": "WAIVERS_TRADITIONAL",
                                    "isUsingAcquisitionBudget": True, "minimumBid": 0, "waiverHours": 24,
                                    "waiverOrderReset": False, "waiverProcessDays": ["WEDNESDAY"], "waiverProcessHour": 3},
            "draftSettings": {"keeperCount": 0, "type": "SNAKE", "pickOrder": TEAM_IDS},
            "isCustomizable": True, "isPublic": public, "name": name, "restrictionType": "NONE",
            "rosterSettings": {"isBenchUnlimited": False, "lineupLocktimeType": "INDIVIDUAL_GAME",
                               "lineupSlotCounts": counts, "moveLimit": -1, "rosterLocktimeType": "INDIVIDUAL_GAME"},
            "scheduleSettings": {"divisions": [{"id": 0, "name": "East", "size": 5}, {"id": 1, "name": "West", "size": 5}],
                                 "matchupPeriodCount": 14, "matchupPeriodLength": 1,
                                 "matchupPeriods": {str(i): [i] for i in range(1, 18)}, "periodTypeId": 1,
                                 "playoffMatchupPeriodLength": 1, "playoffSeedingRule": "TOTAL_POINTS_SCORED",
                                 "playoffSeedingRuleBy": 0, "playoffTeamCount": 4},
            "scoringSettings": {"allowOutOfPositionScoring": False, "homeTeamBonus": 0, "matchupTieRule": "NONE",
                                "playerRankType": "PPR", "playoffMatchupTieRule": "NONE", "scoringItems": items,
                                "scoringType": "H2H_POINTS"},
            "size": TEAMS, "tradeSettings": {"deadlineDate": 1795000000000, "max": -1, "revisionHours": 24,
                                             "vetoVotesRequired": 4}}


def _schedule() -> list[list[tuple[int, int]]]:
    """14 weeks of pairs (circle method, 9 rounds, then the first five again)."""
    ids = list(TEAM_IDS)
    rounds = []
    for _ in range(TEAMS - 1):
        rounds.append([(ids[i], ids[TEAMS - 1 - i]) for i in range(TEAMS // 2)])
        ids = [ids[0], ids[-1], *ids[1:-1]]
    return (rounds + rounds)[:14]


def build(lid: int, name: str, public: bool) -> None:
    rows = list(csv.DictReader((FX / "ff" / "db_playerids.csv").open()))
    by_sleeper = {r["sleeper_id"]: r for r in rows if r["espn_id"] not in ("", "NA")}
    directory = json.loads((FX / "sleeper" / "players_nfl.json").read_text())
    test = json.loads((FX / "sleeper" / "rosters_9000000000000000001.json").read_text())
    rng = random.Random(4242)
    d = OUT / str(lid)
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    if not public:
        (d / "_private").write_text("This synthetic league answers 401 without the manager's cookies (IK-1).\n")

    def espn_of(sid: str) -> dict | None:
        sp = directory.get(sid) or {}
        if sp.get("position") == "DEF":
            return _dst(sid)
        if sid == "13545":                      # the name-match case
            return _player(NAME_MATCH, sp.get("full_name") or "", "K", sp.get("team"))
        r = by_sleeper.get(sid)
        if not r:
            return None
        pos = {"PK": "K"}.get(r["position"], r["position"])
        if pos not in POS_ID:
            return None
        return _player(int(r["espn_id"]), sp.get("full_name") or r["name"], pos, sp.get("team"), sp.get("injury_status"))

    rosters: dict[int, list[dict]] = {}
    for tid, r in zip(TEAM_IDS, sorted(test, key=lambda x: x["roster_id"]), strict=True):
        ps = [p for p in (espn_of(str(s)) for s in r["players"]) if p]
        if tid == 1:
            ps.append(_player(99990001, *FAKE[99990001]))
        if tid == 2:
            ps.append(_player(99990002, *FAKE[99990002]))
        need = {"QB": [0], "RB": [2, 2], "WR": [4, 4], "TE": [6], "K": [17], "DEF": [16]}
        order = [p for p in ps if p["id"] != 99990002]
        slot_of: dict[int, int] = {}
        for p in order:
            pos = {v: k for k, v in POS_ID.items()}[p["defaultPositionId"]]
            if need.get(pos):
                slot_of[p["id"]] = need[pos].pop(0)
        flex = next((p for p in order if p["id"] not in slot_of and p["defaultPositionId"] in (2, 3, 4)), None)
        if tid == 2:                            # the made-up RB plays FLEX (a starter the id table cannot map)
            flex = next(p for p in ps if p["id"] == 99990002)
        if flex is not None:
            slot_of[flex["id"]] = 23
        ir = next((p for p in ps if p["id"] not in slot_of and p["injuryStatus"] in ("OUT", "INJURY_RESERVE")), None)
        if ir is not None:
            slot_of[ir["id"]] = 21
        rosters[tid] = [_entry(p, slot_of.get(p["id"], 20), tid) for p in ps]
    # week 3's trade: team 3's last bench WR for team 5's last bench WR (each now on the other's roster)
    def bench_wr(tid: int) -> dict:
        return [e for e in rosters[tid] if e["lineupSlotId"] == 20 and e["playerPoolEntry"]["player"]["defaultPositionId"] == 3][-1]
    a, b = bench_wr(3), bench_wr(5)
    rosters[3].remove(a)
    rosters[5].remove(b)
    a["playerPoolEntry"]["onTeamId"], b["playerPoolEntry"]["onTeamId"] = 5, 3
    a["acquisitionType"] = b["acquisitionType"] = "TRADE"
    rosters[5].append(a)
    rosters[3].append(b)

    rostered = {e["playerId"] for es in rosters.values() for e in es}
    pool = [r for r in rows if r["espn_id"] not in ("", "NA") and r["sleeper_id"] in directory
            and int(r["espn_id"]) not in rostered and r["position"] in ("QB", "RB", "WR", "TE", "PK")]
    pool.sort(key=lambda r: -int(r["espn_id"]))          # the newest ESPN ids first: this season's players

    def pool_player(r: dict) -> dict:
        sp = directory.get(r["sleeper_id"]) or {}
        return _player(int(r["espn_id"]), sp.get("full_name") or r["name"], {"PK": "K"}.get(r["position"], r["position"]),
                       sp.get("team"), sp.get("injury_status"))

    # ---- schedule and points (weeks 1-3 scored, week 4 under way: the Thursday game)
    sched, totals = [], {t: [] for t in TEAM_IDS}
    mid = 0
    for w, pairs in enumerate(_schedule(), 1):
        for h, aw in pairs:
            m = {"id": mid, "matchupPeriodId": w, "playoffTierType": "NONE"}
            for side, t in (("home", h), ("away", aw)):
                if w < WEEK:
                    pts = round(rng.uniform(78, 152), 2)
                elif w == WEEK:
                    pts = round(rng.choice([0.0, 0.0, 6.4, 11.2, 17.9]), 2)
                else:
                    pts = 0.0
                m[side] = {"gamesPlayed": 0, "pointsByScoringPeriod": ({str(w): pts} if w <= WEEK else {}),
                           "teamId": t, "totalPoints": pts}
                if w < WEEK:
                    totals[t].append(pts)
            if w < WEEK:
                m["winner"] = "HOME" if m["home"]["totalPoints"] > m["away"]["totalPoints"] else "AWAY"
            else:
                m["winner"] = "UNDECIDED"
            sched.append(m)
            mid += 1
    record = {t: {"wins": 0, "losses": 0, "ties": 0, "pointsFor": 0.0, "pointsAgainst": 0.0} for t in TEAM_IDS}
    for m in sched:
        if m["winner"] == "UNDECIDED":
            continue
        h, aw = m["home"], m["away"]
        for me, op in ((h, aw), (aw, h)):
            rec = record[me["teamId"]]
            rec["pointsFor"] = round(rec["pointsFor"] + me["totalPoints"], 2)
            rec["pointsAgainst"] = round(rec["pointsAgainst"] + op["totalPoints"], 2)
            won = (m["winner"] == "HOME") == (me is h)
            rec["wins" if won else "losses"] += 1
    seed = sorted(TEAM_IDS, key=lambda t: (-record[t]["wins"], -record[t]["pointsFor"]))

    members = [{"displayName": f"espn_manager_{i:02d}", "id": f"{{{0x42420000 + i:08X}-0000-4000-8000-{i:012X}}}",
                "isLeagueManager": i == 1} for i in range(1, TEAMS + 1)]
    teams = []
    for i, tid in enumerate(TEAM_IDS):
        kind, nm = NAMES[i]
        owner = members[i]["id"]
        t = {"abbrev": f"T{tid:02d}", "currentProjectedRank": i + 1, "divisionId": i % 2, "id": tid,
             "logo": "", "logoType": "VECTOR", "owners": [owner], "primaryOwner": owner,
             "playoffSeed": seed.index(tid) + 1, "points": record[tid]["pointsFor"], "pointsAdjusted": 0.0,
             "rankCalculatedFinal": 0, "rankFinal": 0,
             "record": {"overall": {**record[tid], "gamesBack": 0.0, "percentage": record[tid]["wins"] / 3,
                                    "streakLength": 1, "streakType": "WIN"}},
             "transactionCounter": {"acquisitionBudgetSpent": 0, "acquisitions": 0, "drops": 0, "moveToIR": 0,
                                    "trades": 0},
             "waiverRank": TEAMS - seed.index(tid)}
        if kind == "name":
            t["name"] = nm
        else:
            t["location"], t["nickname"] = nm
        teams.append(t)

    # ---- transactions (weeks 1-4): FAAB claims and free-agent adds of players now rostered, a trade in week 3,
    # a cancelled claim (ignored) and a lineup move (ignored)
    tx: dict[int, list[dict]] = {w: [] for w in range(1, WEEK + 1)}
    n = 0

    def add_tx(w: int, typ: str, tid: int, items: list[dict], bid: int = 0, status: str = "EXECUTED") -> None:
        nonlocal n
        n += 1
        when = T0 + (w * 7 + 2) * DAY + n * 60000
        tx[w].append({"bidAmount": bid, "executionType": "EXECUTE", "id": f"{n:08x}-4242-4000-8000-{n:012x}",
                      "isActingAsTeamOwner": False, "isLeagueManager": False, "isPending": False, "items": items,
                      "memberId": members[TEAM_IDS.index(tid)]["id"], "processDate": when, "proposedDate": when - 3600000,
                      "rating": 0, "scoringPeriodId": w, "skipTransactionCounter": False, "status": status,
                      "subOrder": 0, "teamId": tid, "type": typ})

    def item(kind: str, pid: int, frm: int, to: int) -> dict:
        return {"fromLineupSlotId": -1 if frm == 0 else 20, "fromTeamId": frm, "isKeeper": False, "overallPickNumber": 0,
                "playerId": pid, "toLineupSlotId": -1 if to == 0 else 20, "toTeamId": to, "type": kind}
    dropped = iter(pool[:6])
    for w, tid in ((1, 1), (2, 4), (2, 7), (4, 9)):
        added = [e for e in rosters[tid] if e["lineupSlotId"] == 20][0]
        added["acquisitionType"] = "ADD"
        drop = next(dropped)
        add_tx(w, "WAIVER" if w != 4 else "FREEAGENT", tid,
               [item("ADD", added["playerId"], 0, tid), item("DROP", int(drop["espn_id"]), tid, 0)],
               bid=(7 if w == 2 else 3) if w != 4 else 0)
    add_tx(3, "TRADE_ACCEPT", 3, [item("TRADE", a["playerId"], 3, 5), item("TRADE", b["playerId"], 5, 3)])
    add_tx(2, "WAIVER", 6, [item("ADD", int(pool[10]["espn_id"]), 0, 6)], bid=12, status="CANCELED")
    lineup = [e for e in rosters[8] if e["lineupSlotId"] == 20][0]
    add_tx(3, "ROSTER", 8, [{**item("LINEUP", lineup["playerId"], 8, 8), "toLineupSlotId": 23}])

    # ---- free agents (ESPN's own list): the pool's first 30 not dropped above, and one made-up player
    fas = [{"id": int(r["espn_id"]), "onTeamId": 0, "player": pool_player(r), "status": "FREEAGENT"}
           for r in pool[6:36]]
    fas.append({"id": 99990004, "onTeamId": 0, "player": _player(99990004, "Synthetic Free Agent", "TE", "ARI"),
                "status": "WAIVERS"})

    status = {"currentMatchupPeriod": WEEK, "finalScoringPeriod": 17, "firstScoringPeriod": 1, "isActive": True,
              "isExpired": False, "isFull": True, "isViewable": True, "latestScoringPeriod": WEEK,
              "previousSeasons": [2024, 2025], "teamsJoined": TEAMS, "transactionScoringPeriod": WEEK,
              "waiverLastExecutionDate": T0 + (WEEK * 7) * DAY}

    def dump(name: str, body: dict) -> None:
        (d / f"{name}.json").write_text(json.dumps({**_top(lid), **body}, indent=1) + "\n")
    dump("mSettings", {"settings": _settings(name, public)})
    dump("mStatus", {"status": status})
    dump("mTeam", {"members": members, "teams": teams})
    dump("mRoster", {"teams": [{"id": t, "roster": {"appliedStatTotal": 0.0, "entries": rosters[t]}} for t in TEAM_IDS]})
    dump("mMatchupScore", {"schedule": sched})
    for w in range(1, WEEK + 1):
        dump(f"mTransactions2_{w}", {"transactions": tx[w]})
    dump("kona_player_info", {"players": fas})


if __name__ == "__main__":
    build(4242, "Synthetic Public League", True)
    build(5150, "Synthetic Private League", False)
    print("wrote", sorted(str(p.relative_to(FX)) for p in OUT.rglob("*") if p.is_file()))
