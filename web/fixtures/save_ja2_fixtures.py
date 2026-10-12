"""Wave J-A (JA-2): the recordings for web/e2e/ja2 — Compare over the weeks (GET /api/compare/weeks) and Matchups over
the weeks (GET /api/matchups/defense with window / weeks / vs), from a fixture API on the shared database (2026 through
week 4).

    cd api && LEAGUE_LAB_NOW=2026-10-03T16:00:00Z LEAGUE_LAB_SLEEPER_FIXTURES=$PWD/tests/fixtures/sleeper … \
        uv run uvicorn league_lab_api.main:app --port 8920
    python web/fixtures/save_ja2_fixtures.py http://localhost:8920

Keys are the request's path + sorted query (as e2e/fixtures.ts keys II-3's).
"""

from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent / "ja2"
SCRUBS = "1389709692405551104"
PAIR = {"a": "00-0036322", "b": "00-0038606"}       # Justin Jefferson, Parker Washington (both in compare_<SCRUBS>.json)
ASK = [
    ("/api/compare/weeks", {"league": SCRUBS, **PAIR}),
    ("/api/compare/weeks", {"league": SCRUBS, **PAIR, "window": "weeks", "weeks": "3-4", "vs": "1-2"}),
    ("/api/matchups/defense", {"league": SCRUBS, "team": "2", "window": "season"}),
    ("/api/matchups/defense", {"league": SCRUBS, "team": "2", "window": "weeks", "weeks": "3-4", "vs": "1-2"}),
]


def main(base: str) -> None:
    OUT.mkdir(exist_ok=True)
    saved: dict[str, dict] = {}
    for path, q in ASK:
        key = path + "?" + urllib.parse.urlencode(sorted(q.items()))
        with urllib.request.urlopen(base + key) as r:  # noqa: S310 - localhost
            body = json.loads(r.read())
        saved[key] = {"status": 200, "body": body}
        print(key)
    (OUT / "api_ja2.json").write_text(json.dumps(saved, separators=(",", ":"), ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8920")
