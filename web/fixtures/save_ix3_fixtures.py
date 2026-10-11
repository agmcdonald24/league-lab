"""Wave I-X (IX-3): the Stats table's recordings for web/e2e/ix3 — GET /api/players answers with the named views
(`views`) and the situation filter (`situation`), recorded from a fixture API on the shared database (2026 through
week 4).

    cd api && LEAGUE_LAB_NOW=2026-10-03T16:00:00Z LEAGUE_LAB_SLEEPER_FIXTURES=$PWD/tests/fixtures/sleeper … \
        uv run uvicorn league_lab_api.main:app --port 8920
    python web/fixtures/save_ix3_fixtures.py http://localhost:8920

Keys are the request's path + sorted query (as e2e/fixtures.ts keys II-3's).
"""

from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent / "ix3"
SCRUBS = "1389709692405551104"
BASE = {"league": SCRUBS, "limit": "1000", "window": "season"}
ASK = [{**BASE, "position": "WR,TE"}, {**BASE, "position": "WR,TE", "situation": "trailing"}, {**BASE, "position": "RB"}]


def main(base: str) -> None:
    OUT.mkdir(exist_ok=True)
    saved: dict[str, dict] = {}
    for q in ASK:
        key = "/api/players?" + urllib.parse.urlencode(sorted(q.items()))
        with urllib.request.urlopen(base + key) as r:  # noqa: S310 - localhost
            body = json.loads(r.read())
        assert "views" in body, "IX-3's shape expected"
        saved[key] = {"status": 200, "body": body}
        print(f"{key}: {body['total']} players, situation {(body.get('situation') or {}).get('label', 'all plays')}")
    (OUT / "api_ix3.json").write_text(json.dumps(saved, separators=(",", ":"), ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8920")
