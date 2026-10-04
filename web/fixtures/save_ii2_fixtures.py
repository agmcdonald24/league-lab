"""Wave I-I (II-2): three League of Scrubs free agents' player cards for the drawer's Waivers e2e (web/e2e/ii2).

The Waivers fixture (waivers_1389709692405551104_2_WR.json) lists free agents none of whom had a saved card; the drawer
opens their cards from the WR list. Recorded from a fixture API (the API's own test fixtures for Sleeper / ESPN / MFL,
the worktree's database clone, events off) — the same numbers the Waivers fixture shows (projection checked below).

    LEAGUE_LAB_EVENTS=off LEAGUE_LAB_SLEEPER_FIXTURES=api/tests/fixtures/sleeper … uvicorn league_lab_api.main:app --port 8723
    python web/fixtures/save_ii2_fixtures.py http://localhost:8723
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent
SCRUBS = "1389709692405551104"
PLAYERS = ("00-0038117", "00-0039880", "00-0038544")  # Wan'Dale Robinson, Malik Washington, Quentin Johnston


def main(base: str) -> None:
    fas = {f["gsis_id"]: f for f in json.loads((OUT / f"waivers_{SCRUBS}_2_WR.json").read_text())["free_agents"]}
    for gsis in PLAYERS:
        with urllib.request.urlopen(f"{base}/api/player/{gsis}?league={SCRUBS}&team=2") as r:  # noqa: S310 - localhost
            card = json.loads(r.read())
        want = fas[gsis]["projection"]
        assert abs((card["proj_points"] or 0) - want) < 0.01, (gsis, card["proj_points"], want)
        (OUT / "player" / f"{SCRUBS}_{gsis}.json").write_text(json.dumps(card, indent=1, ensure_ascii=False) + "\n")
        print(f"{SCRUBS}_{gsis}.json: {card['player_name']} {card['proj_points']}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8723")
