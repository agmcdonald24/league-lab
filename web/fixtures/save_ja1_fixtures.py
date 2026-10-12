"""Wave J-A (JA-1): the Stats table's recordings for web/e2e/ja1 — GET /api/players answers with a second stretch
(`vs`) and a stat week by week (`by`), recorded from a fixture API on the shared database (2026 through week 4) and
trimmed to the answer's first 120 rows (the API's own order: target share, highest first) to keep the file small.

    cd api && LEAGUE_LAB_NOW=2026-10-03T16:00:00Z LEAGUE_LAB_SLEEPER_FIXTURES=$PWD/tests/fixtures/sleeper … \
        uv run uvicorn league_lab_api.main:app --port 8920
    python web/fixtures/save_ja1_fixtures.py http://localhost:8920

Keys are the request's path + sorted query (as e2e/fixtures.ts keys II-3's).
"""

from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parent / "ja1"
SCRUBS = "1389709692405551104"
BASE = {"league": SCRUBS, "limit": "1000", "position": "WR,TE"}
ASK = [
    {**BASE, "window": "season"},
    {**BASE, "window": "weeks", "weeks": "3-4"},
    {**BASE, "window": "weeks", "weeks": "3-4", "vs": "1-2"},
    {**BASE, "window": "season", "by": "target_share"},
]
KEEP = 120


def trim(body: dict) -> dict:
    body["players"] = body["players"][:KEEP]
    ids = {p["gsis_id"] for p in body["players"]}
    if body.get("vs"):
        body["vs"]["players"] = {k: v for k, v in body["vs"]["players"].items() if k in ids}
    if body.get("byweek"):
        for k in ("values", "why", "trend"):
            body["byweek"][k] = {g: v for g, v in body["byweek"][k].items() if g in ids}
    return body


def main(base: str) -> None:
    OUT.mkdir(exist_ok=True)
    saved: dict[str, dict] = {}
    for q in ASK:
        key = "/api/players?" + urllib.parse.urlencode(sorted(q.items()))
        with urllib.request.urlopen(base + key) as r:  # noqa: S310 - localhost
            body = json.loads(r.read())
        saved[key] = {"status": 200, "body": trim(body)}
        print(f"{key}: {body['total']} players, kept {len(body['players'])}")
    (OUT / "api_ja1.json").write_text(json.dumps(saved, separators=(",", ":"), ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8920")
