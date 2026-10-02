"""Save the research screens' fixtures (Wave G: G3's screens on G1's routes) from the research API:
web/fixtures/{trends,matchups_defense,matchups_cb,players,receivers,compare,games}_*.json.

    # the integrated API, the Test League from the Sleeper fixtures:
    LEAGUE_LAB_SLEEPER_FIXTURES=$PWD/api/tests/fixtures/sleeper uv run uvicorn league_lab_api.main:app --port 8690   # in api/
    python3 web/fixtures/make_research_fixtures.py                                        # API=http://localhost:8690

SAVED, not hand-written (as save_decision_fixtures.py does for the decision screens): the answers of G1's routes for the
house leagues (dynasty roster 12, Scrubs roster 2, their marts) and the fictional Test League (team 3, on demand from
the Sleeper fixtures), on exactly the paths the screens ask (lib/api.ts researchPaths). The screens read them through
lib/shapes.ts, as they read the live API. On top, said here and in web/README.md:
* Two nested lists no screen reads are left out to keep the files small: trends' `players[].metrics` and receivers'
  `receivers[].context` (the rest of every answer is as sent).
* /api/compare answers one pair; the fixture server (e2e/fixtures.ts) composes any pair, so compare_<league>.json holds
  every saved side by gsis_id (from real /api/compare answers, two subjects a call) plus `_meta`, the answer's league
  block (week, league_name …). The subjects: the roster's My Week lineup, the top 40 by points, the top 30 trends rows.
* games_<league>.json: /api/player/{gsis}/games for the same subjects, 2025 and 2026, rows by gsis_id.
* The Test League's Sleeper fixtures name its teams "Team 3" / "Manager 3"; renamed to the web fixtures' (F2) names.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

API = os.environ.get("API", "http://localhost:8690")
OUT = Path(__file__).resolve().parent
DYN, SCRUBS, TEST = "1321941740235550720", "1389709692405551104", "9000000000000000001"
TEAM = {DYN: 12, SCRUBS: 2, TEST: 3}
SEASONS = (2025, 2026)
DROP = {"timings_ms"}
DROP_IN = {"players": {"metrics"}, "receivers": {"context"}}  # list key → row keys no screen reads


def get(path: str):
    with urllib.request.urlopen(API + path, timeout=300) as r:
        return json.load(r)


TEST_NAMES = {r["roster_id"]: r for r in json.loads((OUT / f"rosters_{TEST}.json").read_text())}


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


def strip(o):
    if isinstance(o, dict):
        out = {}
        for k, v in o.items():
            if k in DROP:
                continue
            if k in DROP_IN and isinstance(v, list):
                v = [{kk: vv for kk, vv in x.items() if kk not in DROP_IN[k]} if isinstance(x, dict) else x for x in v]
            out[k] = strip(v)
        return out
    if isinstance(o, list):
        return [strip(x) for x in o]
    return o


def save(league: str, name: str, data) -> None:
    data = strip(data)
    if league == TEST:
        data = rename(data)
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n")


def q(s: str) -> str:
    return urllib.request.quote(s, safe="")


def main() -> None:
    for league, team in TEAM.items():
        t = get(f"/api/trends?league={league}&view=all&limit=200")
        save(league, f"trends_{league}.json", t)
        save(league, f"matchups_defense_{league}_{team}.json", get(f"/api/matchups/defense?league={league}&team={team}"))
        save(league, f"matchups_cb_{league}_{team}.json", get(f"/api/matchups/cb?league={league}&team={team}"))
        p = get(f"/api/players?league={league}&sort=points&dir=desc&limit=500")
        save(league, f"players_{league}.json", p)
        save(league, f"receivers_{league}.json", get(f"/api/receivers?league={league}&limit=150"))
        week = json.loads((OUT / f"my-week_{league}_{team}.json").read_text())
        ids = [r["gsis_id"] for r in week["lineup_full"] if r.get("gsis_id")]
        ids += [r["gsis_id"] for r in p["players"][:40]] + [r["gsis_id"] for r in t["players"][:30]]
        ids = list(dict.fromkeys(ids))
        sides: dict = {}
        for a, b in zip(ids[::2], ids[1::2] + ids[:1], strict=False):
            c = get(f"/api/compare?league={league}&a={q(a)}&b={q(b)}")
            sides.setdefault("_meta", {k: v for k, v in c.items() if k not in ("a", "b", "verdict", "table")})
            sides[a], sides[b] = c["a"], c["b"]
        save(league, f"compare_{league}.json", sides)
        games: dict = {}
        for g in ids:
            for s in SEASONS:
                try:
                    games.setdefault(g, []).extend(get(f"/api/player/{q(g)}/games?league={league}&season={s}")["games"])
                except urllib.error.HTTPError as e:   # 404: no games that season
                    if e.code != 404:
                        raise
        save(league, f"games_{league}.json", games)
        print(league, len(t["players"]), len(p["players"]), len(ids), "subjects")


if __name__ == "__main__":
    main()
