"""Plan F3: the Sleeper fixtures the API-for-any-league tests read (run once; the outputs are committed).

    cd api && uv run python tests/fixtures/make_f3_fixtures.py

1. **Pseudonymises every Sleeper user id** in the house leagues' fixtures (``rosters_*`` owner / co-owners,
   ``users_*``): the real ids map to ``91000000000000000NN`` in sorted order (idempotent: an id already fictional is
   kept). Names were already "Manager n" / "Team n" (``anyleague.write_fixtures``).
2. **A fictional Sleeper user** ``test_manager`` (``user_test_manager.json``) who owns house-league roster 2 (League of
   Scrubs) and roster 12 (the dynasty) — the acceptance rosters — plus roster 1 of a third, fictional league
   ``9000000000000000001`` "Test League": 10 teams, full PPR, 4-pt pass TD, QB/RB/RB/WR/WR/TE/FLEX/K/DEF + 6 bench,
   kicking and defense keys that differ from League of Scrubs' (sack 2, fgm_50p 6, pts_allow_0 12), so its scoring
   matches no house league exactly. Its rosters are the Scrubs players dealt round-robin by position (no new player
   ids; every team gets a K and a DEF).
   ``user_leagues_<user_id>.json`` lists the three leagues as Sleeper's ``/user/<id>/leagues/nfl/<season>`` does.
3. **Matchups** ``matchups_<league>_<week>.json`` for weeks 4 and 5: the house leagues use their week-3 pairings
   (from ``raw.sleeper_matchup``; Sleeper has not been asked for week 4 in this database), the Test League pairs
   1-2, 3-4, ... No points (the week is not played).
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).with_name("sleeper")
DYNASTY, SCRUBS, TEST = "1321941740235550720", "1389709692405551104", "9000000000000000001"
USERNAME = "test_manager"
# week-3 pairings, roster_id -> matchup_id (raw.sleeper_matchup, 2026-10-02)
PAIRS = {DYNASTY: {1: 6, 2: 1, 3: 4, 4: 2, 5: 4, 6: 2, 7: 3, 8: 5, 9: 1, 10: 5, 11: 3, 12: 6},
         SCRUBS: {1: 3, 2: 4, 3: 2, 4: 3, 5: 1, 6: 4, 7: 2, 8: 5, 9: 1, 10: 5},
         TEST: {r: (r + 1) // 2 for r in range(1, 11)}}
ACCEPTANCE = {SCRUBS: 2, DYNASTY: 12, TEST: 1}


def load(name: str):
    return json.loads((HERE / name).read_text())


def dump(name: str, data, indent: int | None = 1) -> None:
    (HERE / name).write_text(json.dumps(data, indent=indent, sort_keys=True) + "\n")


def fictional(i: int) -> str:
    return f"91{i:017d}"


def main() -> None:
    # 1. pseudonymise user ids (the acceptance rosters' owner gets index 1: the test user)
    ids: set[str] = set()
    for lid in (DYNASTY, SCRUBS):
        for r in load(f"rosters_{lid}.json"):
            ids |= {str(x) for x in [r.get("owner_id"), *(r.get("co_owners") or [])] if x}
        ids |= {str(u["user_id"]) for u in load(f"users_{lid}.json")}
    owner = {str(r["owner_id"]) for lid, rid in ((SCRUBS, 2), (DYNASTY, 12))
             for r in load(f"rosters_{lid}.json") if r["roster_id"] == rid}
    assert len(owner) == 1, owner
    me_real = owner.pop()
    mapping = {i: i for i in ids if i.startswith("91") and len(i) == 19}
    if me_real not in mapping:
        mapping[me_real] = fictional(1)
    n = 2
    for i in sorted(ids):
        if i not in mapping:
            mapping[i] = fictional(n)
            n += 1
    me = mapping[me_real]
    for lid in (DYNASTY, SCRUBS):
        rosters = load(f"rosters_{lid}.json")
        for r in rosters:
            r["owner_id"] = mapping.get(str(r["owner_id"]), r["owner_id"]) if r.get("owner_id") else r.get("owner_id")
            if r.get("co_owners"):
                r["co_owners"] = [mapping.get(str(x), x) for x in r["co_owners"]]
        dump(f"rosters_{lid}.json", rosters)
        users = load(f"users_{lid}.json")
        for u in users:
            u["user_id"] = mapping.get(str(u["user_id"]), u["user_id"])
        dump(f"users_{lid}.json", sorted(users, key=lambda u: u["user_id"]))

    # 2. the Test League: Scrubs' payload as the template, its own scoring and slots
    scrubs = load(f"league_{SCRUBS}.json")
    lg = json.loads(json.dumps(scrubs))
    lg.update({"league_id": TEST, "name": "Test League", "previous_league_id": None, "draft_id": "9000000000000000002",
               "total_rosters": 10, "status": "in_season",
               "roster_positions": ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "K", "DEF"] + ["BN"] * 6})
    sc = dict(scrubs["scoring_settings"])
    sc.update({"rec": 1.0, "pass_td": 4.0, "sack": 2.0, "fgm_50p": 6.0, "pts_allow_0": 12.0})
    lg["scoring_settings"] = sc
    lg["settings"] = {**scrubs["settings"], "num_teams": 10, "type": 0, "playoff_week_start": 15, "playoff_teams": 6,
                      "playoff_round_type": 0}
    dump(f"league_{TEST}.json", lg)
    pool = [p for r in load(f"rosters_{SCRUBS}.json") for p in (r.get("players") or [])]
    directory = load("players_nfl.json")
    by_pos: dict[str, list[str]] = {}
    for p in pool:                                  # every team gets a K and a DEF when Scrubs has ten of each
        by_pos.setdefault((directory.get(p) or {}).get("position") if p in directory else "DEF", []).append(p)
    dealt = [p for pos in sorted(by_pos) for p in by_pos[pos]]
    rosters = []
    for rid in range(1, 11):
        players = dealt[rid - 1::10]
        rosters.append({"league_id": TEST, "roster_id": rid, "owner_id": me if rid == 1 else fictional(100 + rid),
                        "co_owners": None, "players": players, "starters": [], "reserve": [], "taxi": [],
                        "settings": {"wins": 2 if rid % 3 else 1, "losses": 1 if rid % 3 else 2, "fpts": 300 + rid,
                                     "fpts_decimal": 0}})
    dump(f"rosters_{TEST}.json", rosters)
    dump(f"users_{TEST}.json", [{"user_id": me if rid == 1 else fictional(100 + rid), "display_name": f"Manager {rid}",
                                 "league_id": TEST, "is_owner": rid == 1, "metadata": {"team_name": f"Team {rid}"}}
                                for rid in range(1, 11)])

    # the user and their leagues (Sleeper's league objects: the league payload's fields)
    dump(f"user_{USERNAME}.json", {"user_id": me, "username": USERNAME, "display_name": "Test Manager", "avatar": None})
    leagues = [load(f"league_{lid}.json") for lid in (SCRUBS, DYNASTY, TEST)]
    dump(f"user_leagues_{me}.json", leagues)

    # 3. matchups, weeks 4 and 5
    for lid in (DYNASTY, SCRUBS, TEST):
        for week in (4, 5):
            ms = [{"roster_id": rid, "matchup_id": mid, "points": 0.0, "custom_points": None, "starters": [],
                   "players": []} for rid, mid in sorted(PAIRS[lid].items())]
            dump(f"matchups_{lid}_{week}.json", ms)
    print({"user_id": me, "ids_mapped": len(mapping), "test_league_rosters": len(rosters)})


if __name__ == "__main__":
    main()
