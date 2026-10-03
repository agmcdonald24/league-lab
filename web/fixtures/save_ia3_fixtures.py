"""Wave I-A (IA-3): add the rankings' new fields to the saved /api/ros and /api/player fixtures, in place.

The fixture files keep every number they have (other screens' e2e read them); each row gains what IA-3's API now
sends for the same player — `headshot_url`, `bye_weeks`, `ros_points_per_game`, `per_game`, `why`, `market_points`,
`week_points`, `market_words` on /api/ros rows (+ `piece_columns`, `leans_on`, `market_week`, `market_note`,
`howto_rankings` on the answer); `why`, `market`, `leans_on` on a player card — taken from the API's own answer
(in process, on this worktree's database), and only where the API's number equals the fixture's (a row whose total
moved keeps no pieces: the list must add up to the number the screen shows). The Test League's files are
hand-written from League of Scrubs' numbers (make_fixtures.py), so its rows are matched against Scrubs' answer.
The market is null everywhere (no market mart in the clone); the e2e adds one by hand where it checks the line.

    cd api && uv run python ../web/fixtures/save_ia3_fixtures.py
"""

from __future__ import annotations

import json
from pathlib import Path

from league_lab_api import ondemand, player

OUT = Path(__file__).resolve().parent
DYN, SCRUBS, TEST = "1321941740235550720", "1389709692405551104", "9000000000000000001"
ROW_KEYS = ("headshot_url", "bye_weeks", "ros_points_per_game", "per_game", "why", "market_points", "week_points",
            "market_words")
TOP_KEYS = ("piece_columns", "leans_on", "market_week", "market_note", "howto_rankings")
CARD_KEYS = ("why", "market", "leans_on")


def clean(v):
    return json.loads(json.dumps(v, default=str, allow_nan=False).replace("NaN", "null"))


def ros_files() -> None:
    answers: dict[tuple[str, str], dict] = {}
    for f in sorted(OUT.glob("ros_*_*.json")):
        _, lg, pos = f.stem.split("_")
        src = SCRUBS if lg == TEST else lg
        if (src, pos) not in answers:
            answers[(src, pos)] = ondemand.ros(src, pos, 500)
        ans = answers[(src, pos)]
        by = {(p.get("gsis_id") or p.get("player_key")): p for p in ans["players"]}
        fx = json.loads(f.read_text())
        n = 0
        for row in fx["players"]:
            a = by.get(row.get("gsis_id") or row.get("player_key"))
            same = a is not None and abs((a.get("ros_points") or 0) - (row.get("ros_points") or 0)) < 0.01
            for k in ROW_KEYS:
                row[k] = clean(a.get(k)) if same else (clean(a.get(k)) if a is not None and k == "headshot_url" else None)
            n += same
        for k in TOP_KEYS:
            fx[k] = clean(ans.get(k))
        f.write_text(json.dumps(fx, indent=1, ensure_ascii=False) + "\n")
        print(f"{f.name}: {n} of {len(fx['players'])} rows with their pieces")


def player_files() -> None:
    for f in sorted((OUT / "player").glob("*.json")):
        lg, gsis = f.stem.split("_", 1)
        src = SCRUBS if lg == TEST else lg
        fx = json.loads(f.read_text())
        try:
            card = player.player_card(src, gsis)
        except Exception as exc:  # noqa: BLE001 - a player the clone no longer has: the file stays as it is
            print(f"{f.name}: skipped ({exc})")
            continue
        same = abs((card.get("proj_points") or 0) - (fx.get("proj_points") or 0)) < 0.01
        for k in CARD_KEYS:
            fx[k] = clean(card.get(k)) if same or k == "leans_on" else None
        if not same and fx.get("proj_points") is not None:
            fx["market"] = None
        f.write_text(json.dumps(fx, indent=1, ensure_ascii=False) + "\n")
        print(f"{f.name}: why {'added' if same and fx.get('why') else 'left out'}")


if __name__ == "__main__":
    ros_files()
    player_files()
