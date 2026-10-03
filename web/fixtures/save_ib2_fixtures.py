"""Wave I-B (IB-2): Waivers short — the waivers fixtures gain GET /api/waivers' `top3`, `views`, `default_view` and, on
every move, `drop_starts` / `keep_alternative`. MERGED into the saved answers (the rest of each file is left as saved,
so the other screens' tests read the same numbers), from the API in-process (FastAPI's TestClient on this worktree's
database; the Test League on demand from the Sleeper fixtures), the availability overlay ON with the ESPN fixture
(Jefferson Out, Mayfield Out: `api/tests/fixtures/espn`), set here explicitly — popping the variable, as the earlier
savers do, is undone by `settings.py`'s `load_dotenv(override=False)` when a worktree's .env sets it:

* waivers_<league>_<team>_<pos>.json          + top3 / views / default_view; moves[] and cards[].move + the two fields
* waivers_9000000000000000001_9_ALL.json       saved whole: a Test League roster whose claims drop a starter (C.J. Stroud
                                               drops one), for the "best alternative" e2e on demand

    cd api && LEAGUE_LAB_SLEEPER_FIXTURES=$PWD/tests/fixtures/sleeper uv run python ../web/fixtures/save_ib2_fixtures.py
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
os.environ["LEAGUE_LAB_ESPN_FIXTURES"] = str(OUT.parents[1] / "api" / "tests" / "fixtures" / "espn")   # the overlay on
os.environ.pop("LEAGUE_LAB_AVAILABILITY", None)

from fastapi.testclient import TestClient  # noqa: E402
from league_lab_api.main import app  # noqa: E402

c = TestClient(app)
EXTRA = {sdf.TEST: [9]}                                   # rosters saved whole (ALL only)


def get(path: str, **params):
    r = c.get(path, params=params)
    r.raise_for_status()
    return r.json()


def key(m: dict) -> str:
    return f"{(m.get('add') or {}).get('sleeper_id')}|{(m.get('drop') or {}).get('sleeper_id')}"


def main() -> None:
    for league, me in sdf.MINE.items():
        for pos in ["ALL", *sdf.POSITIONS[league]]:
            f = OUT / f"waivers_{league}_{me}_{pos}.json"
            saved = json.loads(f.read_text())
            fresh = sdf.strip(get("/api/waivers", league=league, team=me, position=pos))
            if league == sdf.TEST:
                fresh = sdf.rename(fresh)
            for k in ("top3", "views", "default_view"):
                saved[k] = fresh.get(k)
            ann = {key(m): m for m in fresh.get("moves") or []} | {key(cd["move"]): cd["move"] for cd in fresh.get("cards") or []}
            for m in [*saved.get("moves", []), *[cd["move"] for cd in saved.get("cards", [])]]:
                src = ann.get(key(m)) or {}
                m["drop_starts"], m["keep_alternative"] = src.get("drop_starts"), src.get("keep_alternative")
            f.write_text(json.dumps(saved, indent=1, ensure_ascii=False) + "\n")
            print(f.name, "top3", [x["move"]["add"]["player_name"] for x in saved["top3"] or []])
        for team in EXTRA.get(league, []):
            name = f"waivers_{league}_{team}_ALL.json"
            sdf.save(league, name, get("/api/waivers", league=league, team=team))
            print(name, "saved whole")


if __name__ == "__main__":
    main()
