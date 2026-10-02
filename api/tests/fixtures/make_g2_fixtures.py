"""Wave G (G2): the Sleeper fixtures the decisions on demand read (run once; the output is committed).

    uv run python api/tests/fixtures/make_g2_fixtures.py        # from the repository (reads raw.*: pipeline role)

1. ``players_nfl.json`` gains every player the house leagues' ``mart_player_availability`` lists as a free agent
   (their ``raw.sleeper_player`` payloads, trimmed to ``anyleague.PLAYER_FIELDS``), so "Sleeper's directory minus
   the rosters" holds the nightly's free-agent pool for the two house leagues (the on-demand waiver parity test).
2. ``matchups_<house>_<week>.json`` for the played weeks (1 .. ``last_scored_leg``) from ``raw.sleeper_matchup``
   (points, matchup_id, roster_id; no player lists), and ``transactions_<house>_<round>.json`` from
   ``raw.sleeper_transaction`` (type, status, rosters, adds / drops, the waiver bid; no user ids, no notes).
3. The fictional Test League (``9000000000000000001``, 10 teams): hand-made, plausible weeks 1-2 (scores 85-150,
   seeded) and three rounds of transactions (claims with bids, free-agent adds, drops, one trade, one failed claim)
   on players of its own fixture rosters and the directory.
Existing files (weeks 4 and 5, the F3 fixtures) are left alone.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import psycopg
from league_lab.anyleague import PLAYER_FIELDS
from league_lab.config import get_settings

OUT = Path(__file__).with_name("sleeper")
HOUSE = ("1389709692405551104", "1321941740235550720")
TEST = "9000000000000000001"
TX_FIELDS = ("transaction_id", "type", "status", "created", "status_updated", "leg", "roster_ids", "consenter_ids",
             "adds", "drops", "draft_picks", "waiver_budget", "settings")


def dump(name: str, data) -> None:
    (OUT / name).write_text(json.dumps(data, indent=1, sort_keys=True))


def main() -> None:
    with psycopg.connect(get_settings().pipeline_dsn()) as conn, conn.cursor() as cur:
        # 1. the free agents into the directory
        players = json.loads((OUT / "players_nfl.json").read_text())
        cur.execute("""select distinct sleeper_id from analytics.mart_player_availability
                       where league_id = any(%s) and is_free_agent and sleeper_id is not null""", (list(HOUSE),))
        fa = sorted(r[0] for r in cur.fetchall())
        cur.execute("select player_id, payload from raw.sleeper_player where player_id = any(%s)", (fa,))
        added = 0
        for pid, p in cur.fetchall():
            if pid not in players:
                players[pid] = {k: p.get(k) for k in PLAYER_FIELDS if k in p}
                added += 1
        (OUT / "players_nfl.json").write_text(json.dumps(players, indent=0, sort_keys=True))
        print(f"players_nfl.json: +{added} free agents ({len(players)} players)")
        # 2. the house leagues' played weeks and transactions
        for lid in HOUSE:
            cur.execute("select (payload->'settings'->>'last_scored_leg')::int from raw.sleeper_league where league_id = %s", (lid,))
            last = int(cur.fetchone()[0] or 0)
            for w in range(1, last + 1):
                cur.execute("""select roster_id, matchup_id, points, custom_points from raw.sleeper_matchup
                               where league_id = %s and week = %s order by roster_id""", (lid, w))
                dump(f"matchups_{lid}_{w}.json", [{"roster_id": r, "matchup_id": m, "points": p, "custom_points": c,
                                                   "players": [], "starters": []} for r, m, p, c in cur.fetchall()])
            cur.execute("select week, payload from raw.sleeper_transaction where league_id = %s order by week, transaction_id", (lid,))
            by_round: dict[int, list] = {}
            for w, p in cur.fetchall():
                t = {k: p.get(k) for k in TX_FIELDS}
                t["settings"] = {"waiver_bid": (p.get("settings") or {}).get("waiver_bid")} if (p.get("settings") or {}).get("waiver_bid") is not None else None
                t["creator"] = None
                t["metadata"] = None
                by_round.setdefault(int(w or p.get("leg") or 0), []).append(t)
            for w, ts in by_round.items():
                dump(f"transactions_{lid}_{w}.json", ts)
            print(f"{lid}: matchups weeks 1-{last}, transactions rounds {sorted(by_round)}")
    # 3. the Test League
    rnd = random.Random(9000)
    rosters = json.loads((OUT / f"rosters_{TEST}.json").read_text())
    rids = sorted(int(r["roster_id"]) for r in rosters)
    for w in (1, 2):
        order = rids[:]
        rnd.shuffle(order)
        ms = []
        for i in range(0, len(order), 2):
            for rid in order[i:i + 2]:
                ms.append({"roster_id": rid, "matchup_id": i // 2 + 1, "points": round(rnd.uniform(85, 150), 2),
                           "custom_points": None, "players": [], "starters": []})
        dump(f"matchups_{TEST}_{w}.json", sorted(ms, key=lambda m: m["roster_id"]))
    by_rid = {int(r["roster_id"]): [str(p) for p in r.get("players") or []] for r in rosters}
    taken = {p for ps in by_rid.values() for p in ps}
    free = sorted(p for p, v in players.items() if p not in taken and isinstance(v, dict) and v.get("position") in ("RB", "WR", "TE"))
    base = 1_757_000_000_000                      # 2025-09-04 in Sleeper's milliseconds; + days below
    txs: dict[int, list] = {1: [], 2: [], 3: []}
    n = 0
    for rnd_ in (1, 2, 3):
        for rid in rids[: 4 + rnd_]:
            n += 1
            add, drop = free.pop(rnd.randrange(len(free))), by_rid[rid][-1 - (n % 3)]
            kind = "waiver" if n % 2 else "free_agent"
            txs[rnd_].append({"transaction_id": f"90000000000{n:04d}", "type": kind, "status": "complete",
                              "created": base + (rnd_ * 7 + n % 3) * 86_400_000, "status_updated": None, "leg": rnd_,
                              "roster_ids": [rid], "consenter_ids": [rid], "adds": {add: rid}, "drops": {drop: rid},
                              "draft_picks": [], "waiver_budget": [],
                              "settings": {"waiver_bid": 3 + (n * 7) % 20} if kind == "waiver" else None,
                              "creator": None, "metadata": None})
    n += 1
    txs[2].append({"transaction_id": f"90000000000{n:04d}", "type": "waiver", "status": "failed",
                   "created": base + 15 * 86_400_000, "status_updated": None, "leg": 2, "roster_ids": [rids[1]],
                   "consenter_ids": [rids[1]], "adds": {free[0]: rids[1]}, "drops": None, "draft_picks": [], "waiver_budget": [],
                   "settings": {"waiver_bid": 11}, "creator": None, "metadata": None})
    n += 1
    a, b = rids[2], rids[5]
    pa, pb = by_rid[a][3], by_rid[b][4]
    txs[3].append({"transaction_id": f"90000000000{n:04d}", "type": "trade", "status": "complete",
                   "created": base + 22 * 86_400_000, "status_updated": None, "leg": 3, "roster_ids": [a, b],
                   "consenter_ids": [a, b], "adds": {pa: b, pb: a}, "drops": {pa: a, pb: b}, "draft_picks": [],
                   "waiver_budget": [], "settings": None, "creator": None, "metadata": None})
    for r, ts in txs.items():
        dump(f"transactions_{TEST}_{r}.json", ts)
    print(f"{TEST}: matchups weeks 1-2, {sum(len(t) for t in txs.values())} transactions in rounds 1-3")


if __name__ == "__main__":
    main()
