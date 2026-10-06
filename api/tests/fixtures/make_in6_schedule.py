"""IN-6 (Wave I-N): SYNTHETIC schedule fixtures for the rest of the regular season — `matchups_<league>_<week>.json`
for weeks 6 … playoff_week_start − 1 of the Sleeper fixture leagues, so the fixture API can show the season outlook.

They are NOT the leagues' real schedules (the sandbox cannot reach Sleeper): a round robin by the circle method over
the roster ids, one rotation per week, in Sleeper's future-week shape (matchup_id set, points 0, no starters). Weeks
1–5 are left as recorded. Run from the repo root: `uv run python api/tests/fixtures/make_in6_schedule.py`.
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent / "sleeper"
LEAGUES = ("1389709692405551104", "1321941740235550720", "9000000000000000001")
FIRST = 6


def round_robin(ids: list[int], k: int) -> list[tuple[int, int]]:
    """Round ``k`` of the circle method: the first id fixed, the others rotated ``k`` places."""
    fixed, rest = ids[0], ids[1:]
    k %= len(rest)
    rot = rest[k:] + rest[:k]
    line = [fixed, *rot]
    n = len(line)
    return [(line[i], line[n - 1 - i]) for i in range(n // 2)]


def main() -> None:
    for lid in LEAGUES:
        league = json.loads((HERE / f"league_{lid}.json").read_text())
        last = int(league["settings"]["playoff_week_start"]) - 1
        ids = sorted(int(r["roster_id"]) for r in json.loads((HERE / f"rosters_{lid}.json").read_text()))
        for w in range(FIRST, last + 1):
            rows = []
            for mid, (a, b) in enumerate(round_robin(ids, w), start=1):
                for rid in (a, b):
                    rows.append({"roster_id": rid, "matchup_id": mid, "points": 0.0, "custom_points": None,
                                 "starters": [], "players": []})
            rows.sort(key=lambda r: r["roster_id"])
            (HERE / f"matchups_{lid}_{w}.json").write_text(json.dumps(rows))


if __name__ == "__main__":
    main()
