"""Wave I-M (IM-2): the Stats table's recordings for web/e2e/im2 — today's GET /api/players answers (no `group` on the
catalogue rows, no `full` on the presets), recorded from a fixture API on the shared database (2026 through week 4).

    cd api && LEAGUE_LAB_NOW=2026-10-03T16:00:00Z LEAGUE_LAB_SLEEPER_FIXTURES=$PWD/tests/fixtures/sleeper … \
        uv run uvicorn league_lab_api.main:app --port 8752
    python web/fixtures/save_im2_fixtures.py http://localhost:8752

Keys are the request's path + sorted query (as e2e/fixtures.ts keys II-3's). IM-1's shape (`group`, `full`) is NOT
recorded here: `im2/im1_shape.json` is the hand-added map the spec lays over these answers.
"""

from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent / "im2"
SCRUBS = "1389709692405551104"
ASK = [
    {"league": SCRUBS, "limit": "1000", "position": "WR,TE", "window": "season"},  # the WR / TE tables (> 25 columns)
    {"league": SCRUBS, "limit": "1000", "position": "ALL", "window": "season"},  # 450+ rows x 45+ columns: the timing
]


def main(base: str) -> None:
    OUT.mkdir(exist_ok=True)
    saved: dict[str, dict] = {}
    for q in ASK:
        key = "/api/players?" + urllib.parse.urlencode(sorted(q.items()))
        with urllib.request.urlopen(base + key) as r:  # noqa: S310 - localhost
            body = json.loads(r.read())
        assert "group" not in body["catalogue"][0] and "full" not in body["presets"][0], "today's shape expected"
        saved[key] = {"status": 200, "body": body}
        avail = [c for c in body["catalogue"] if c["available"]]
        print(f"{key}: {body['total']} players, {len(avail)} available columns, {body['window']['label']}")
    (OUT / "api_im2.json").write_text(json.dumps(saved, separators=(",", ":"), ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8752")
