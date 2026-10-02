"""Wave H (H1): add the upside stash and buy low / sell high (`upside`, `trade_lists`) to the saved /api/waivers
fixtures, and save /api/about for the three fixture leagues (web/fixtures/about_<league>.json). SAVED from the API
in-process (FastAPI's TestClient on this worktree's database; the Test League on demand from the Sleeper fixtures), the
rest of each waivers fixture left as G4 saved it; the Test League's team names mapped as save_decision_fixtures.py does.

    cd api && LEAGUE_LAB_SLEEPER_FIXTURES=$PWD/tests/fixtures/sleeper uv run python ../web/fixtures/save_h1_fixtures.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("save_decision_fixtures", OUT / "save_decision_fixtures.py")
sdf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sdf)
sys.path.insert(0, str(OUT.parents[1] / "api"))
os.environ.pop("LEAGUE_LAB_APP_PASSWORD", None)
os.environ.pop("LEAGUE_LAB_API_SECRET", None)

from fastapi.testclient import TestClient  # noqa: E402

from league_lab_api.main import app  # noqa: E402

c = TestClient(app)


def get(path: str, **params):
    r = c.get(path, params=params)
    r.raise_for_status()
    return r.json()


def main() -> None:
    for league, me in sdf.MINE.items():
        for pos in ["ALL", *sdf.POSITIONS[league]]:
            f = OUT / f"waivers_{league}_{me}_{pos}.json"
            saved = json.loads(f.read_text())
            w = sdf.strip(get("/api/waivers", league=league, team=me, position=pos))
            extra = {k: w[k] for k in ("upside", "trade_lists")}
            if league == sdf.TEST:
                extra = sdf.rename(extra)
            saved.update(extra)
            f.write_text(json.dumps(saved, indent=1, ensure_ascii=False) + "\n")
        sdf.save(league, f"about_{league}.json", get("/api/about", league=league))
        print(league, "saved")


if __name__ == "__main__":
    main()
