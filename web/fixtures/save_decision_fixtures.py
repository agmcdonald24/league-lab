"""Save the decision screens' fixtures (plan G4) from G2's API: web/fixtures/{waivers,team,league,trades_partners,trades_evaluate}_*.json.

    # G2's routes (dev/G2) on a clone, the Test League from the Sleeper fixtures:
    LEAGUE_LAB_SLEEPER_FIXTURES=$PWD/api/tests/fixtures/sleeper uv run uvicorn league_lab_api.main:app --port 8694   # in api/
    uv run python web/fixtures/save_decision_fixtures.py                                   # API=http://localhost:8694

SAVED, not hand-written: the house leagues (dynasty roster 12, Scrubs roster 2; every roster's /api/team, the Trade
Finder's partner picker reads the partner's roster there) from their marts, the fictional Test League (team 3) on demand
(Sleeper fixtures: G2's on-demand path). Two changes on top, both said here and in web/README.md:
* REQUESTED of G2 (computed here from the saved responses, so the numbers are G2's): on /api/team,
  `slot_strength[].league` = {avg, best, rank, n} of every roster's best starter at that slot, and `weekly[].league` =
  {median, best, rank, n} of every roster's lineup that week (the screen's "vs the league" bars); on /api/waivers,
  `positions` = the positions the league starts (the free-agent tabs: K and DEF only when it has them).
* The Test League's Sleeper fixtures name its teams "Team 3" / "Manager 3"; the web fixtures (F2) call them "Fixture
  Falcons" … (rosters_9000000000000000001.json): renamed here so every screen of the web app tells one story.
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from pathlib import Path

API = os.environ.get("API", "http://localhost:8694")
OUT = Path(__file__).resolve().parent
DYN, SCRUBS, TEST = "1321941740235550720", "1389709692405551104", "9000000000000000001"
MINE = {DYN: 12, SCRUBS: 2, TEST: 3}
POSITIONS = {DYN: ["QB", "RB", "WR", "TE"], SCRUBS: ["QB", "RB", "WR", "TE", "K", "DEF"], TEST: ["QB", "RB", "WR", "TE", "K", "DEF"]}
DROP = ("timings_ms",)  # changes on every call: not part of the shape


def get(path: str):
    with urllib.request.urlopen(API + path, timeout=300) as r:
        return json.load(r)


def post(path: str, body: dict):
    req = urllib.request.Request(API + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.load(r)


def strip(o):
    if isinstance(o, dict):
        return {k: strip(v) for k, v in o.items() if k not in DROP}
    if isinstance(o, list):
        return [strip(x) for x in o]
    return o


TEST_NAMES = {r["roster_id"]: r for r in json.loads((OUT / "rosters_9000000000000000001.json").read_text())}


def rename(o):
    """The Test League's Sleeper-fixture names → the web fixtures' (F2) names."""
    if isinstance(o, dict):
        return {k: rename(v) for k, v in o.items()}
    if isinstance(o, list):
        return [rename(x) for x in o]
    if isinstance(o, str):
        o = re.sub(r"\bTeam (\d+)\b", lambda m: TEST_NAMES.get(int(m.group(1)), {}).get("team_name", m.group(0)), o)
        return re.sub(r"\bManager (\d+)\b", lambda m: TEST_NAMES.get(int(m.group(1)), {}).get("manager_name", m.group(0)), o)
    return o


def save(league: str, name: str, data) -> None:
    data = strip(data)
    if league == TEST:
        data = rename(data)
    (OUT / name).write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")


def augment_teams(teams: dict[int, dict]) -> None:
    """The requested league comparison on every roster's Team Hub, from the saved responses themselves."""
    by_slot: dict[str, list[float]] = {}
    by_week: dict[int, list[float]] = {}
    for t in teams.values():
        for s in t.get("slot_strength") or []:
            v = (s.get("top") or {}).get("value")
            if v is not None:
                by_slot.setdefault(s["slot_type"], []).append(v)
        for w in t.get("weekly") or []:
            if w.get("lineup_value") is not None:
                by_week.setdefault(w["week"], []).append(w["lineup_value"])
    for t in teams.values():
        for s in t.get("slot_strength") or []:
            vals, v = by_slot.get(s["slot_type"], []), (s.get("top") or {}).get("value")
            s["league"] = {"avg": round(sum(vals) / len(vals), 2) if vals else None, "best": max(vals) if vals else None,
                           "rank": None if v is None else 1 + sum(1 for x in vals if x > v), "n": len(vals)}
        for w in t.get("weekly") or []:
            vals = sorted(by_week.get(w["week"], []), reverse=True)
            v = w.get("lineup_value")
            mid = len(vals) // 2
            w["league"] = {"median": round((vals[mid] + vals[~mid]) / 2, 2) if vals else None, "best": vals[0] if vals else None,
                           "rank": None if v is None else 1 + sum(1 for x in vals if x > v), "n": len(vals)}


def main() -> None:
    for league, me in MINE.items():
        rosters = sorted({r["roster_id"] for r in get(f"/api/team?league={league}&team={me}")["league"]})
        teams = {rid: get(f"/api/team?league={league}&team={rid}") for rid in rosters}
        augment_teams(teams)
        for rid, t in teams.items():
            save(league, f"team_{league}_{rid}.json", t)
        save(league, f"league_{league}.json", get(f"/api/league?league={league}"))
        save(league, f"league_{league}_{me}.json", get(f"/api/league?league={league}&team={me}"))
        for pos in ["ALL", *POSITIONS[league]]:
            w = get(f"/api/waivers?league={league}&team={me}&position={pos}")
            w["positions"] = POSITIONS[league]
            save(league, f"waivers_{league}_{me}_{pos}.json", w)
        best = None
        for want in ["ALL", "QB", "RB", "WR", "TE"]:
            p = get(f"/api/trades/partners?league={league}&team={me}" + ("" if want == "ALL" else f"&want={want}"))
            save(league, f"trades_partners_{league}_{me}_{want}.json", p)
            if want == "ALL":
                best = p
        packages = []
        top = next((x for x in best["partners"] if x.get("is_best")), best["partners"][0] if best["partners"] else None)
        if top:
            packages.append((top["partner"], [x["sleeper_id"] for x in top["give"]], [x["sleeper_id"] for x in top["get"]]))
        # by hand: your most valuable player this week for the second-best player of another team
        other = next(r for r in rosters if r != me and (not top or r != top["partner"]))
        mine = sorted(teams[me]["roster"], key=lambda r: -(r.get("value") or -1))
        theirs = sorted(teams[other]["roster"], key=lambda r: -(r.get("value") or -1))
        packages.append((other, [mine[0]["sleeper_id"]], [theirs[1]["sleeper_id"]]))
        for partner, give, get_ in packages:
            ev = post("/api/trades/evaluate", {"league": league, "team": me, "partner": partner, "give": give, "get": get_})
            save(league, f"trades_evaluate_{league}_{me}_{partner}_{'-'.join(sorted(give))}_{'-'.join(sorted(get_))}.json", ev)
            print(league, partner, give, get_, ev.get("verdict"))
        print(league, "saved", len(teams), "teams")


if __name__ == "__main__":
    main()
