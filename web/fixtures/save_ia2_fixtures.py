"""Wave I-A (IA-2): the decisions screens' fixtures after the window, the dial, the sanity bound and the move of buy low /
sell high to Trades. SAVED from the API in-process (FastAPI's TestClient on this worktree's database; the Test League on
demand from the Sleeper fixtures), names mapped as save_decision_fixtures.py does:

* trades_partners_<league>_<team>_<want>.json             re-saved (the default window: the sanity bound, `interest`)
* trades_partners_<league>_<team>_ALL_<window>.json       the other windows (week, ros, playoffs)
* trades_lists_<league>_<team>.json                       GET /api/trades/lists (buy low / sell high, moved from Waivers)
* waivers_<league>_<team>_<pos>.json                      `trade_lists` removed (the route no longer sends it)
* trades_evaluate_<league>_<team>_<partner>_<give>_<get>.json            the best package and the by-hand one (next 4)
* trades_evaluate_<window>_<league>_<team>_<partner>_<give>_<get>.json   the same packages over the other windows
* trades_evaluate_..._<give>_<get>.json for one more package per league: the best one with a player ticked or unticked,
  whose dial label differs (the calculator's "tick → the dial moves" test); its name is in ia2_packages.json.

    cd api && LEAGUE_LAB_SLEEPER_FIXTURES=$PWD/tests/fixtures/sleeper uv run python ../web/fixtures/save_ia2_fixtures.py
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
os.environ.pop("LEAGUE_LAB_ESPN_FIXTURES", None)        # the overlay off, as the API suite has it (I-0)

from fastapi.testclient import TestClient  # noqa: E402

from league_lab_api.main import app  # noqa: E402

c = TestClient(app)
WINDOWS = ("week", "ros", "playoffs")


def get(path: str, **params):
    r = c.get(path, params=params)
    r.raise_for_status()
    return r.json()


def post(path: str, body: dict):
    r = c.post(path, json=body)
    r.raise_for_status()
    return r.json()


def name(league: str, me: int, partner: int, give: list[str], get_: list[str], window: str | None = None) -> str:
    w = f"{window}_" if window else ""
    return f"trades_evaluate_{w}{league}_{me}_{partner}_{'-'.join(sorted(give))}_{'-'.join(sorted(get_))}.json"


def main() -> None:
    packages_out: dict = {}
    for league, me in sdf.MINE.items():
        for pos in ["ALL", *sdf.POSITIONS[league]]:
            f = OUT / f"waivers_{league}_{me}_{pos}.json"
            saved = json.loads(f.read_text())
            saved.pop("trade_lists", None)
            f.write_text(json.dumps(saved, indent=1, ensure_ascii=False) + "\n")
        best = None
        for want in ["ALL", "QB", "RB", "WR", "TE"]:
            p = get("/api/trades/partners", league=league, team=me, **({} if want == "ALL" else {"want": want}))
            sdf.save(league, f"trades_partners_{league}_{me}_{want}.json", p)
            if want == "ALL":
                best = p
        for w in WINDOWS:
            sdf.save(league, f"trades_partners_{league}_{me}_ALL_{w}.json", get("/api/trades/partners", league=league, team=me, window=w))
        sdf.save(league, f"trades_lists_{league}_{me}.json", get("/api/trades/lists", league=league, team=me))
        for old in OUT.glob(f"trades_evaluate_*{league}_{me}_*.json"):
            old.unlink()
        rosters = sorted({r["roster_id"] for r in json.loads((OUT / f"team_{league}_{me}.json").read_text())["league"]})
        teams = {rid: json.loads((OUT / f"team_{league}_{rid}.json").read_text()) for rid in rosters}
        top = next((x for x in best["partners"] if x.get("is_best")), best["partners"][0] if best["partners"] else None)
        packages = []
        if top:
            packages.append((top["partner"], [x["sleeper_id"] for x in top["give"]], [x["sleeper_id"] for x in top["get"]]))
        other = next(r for r in rosters if r != me and (not top or r != top["partner"]))
        mine = sorted([r for r in teams[me]["roster"] if r.get("sleeper_id") and r["role"] != "empty"], key=lambda r: -(r.get("value") or -1))
        theirs = sorted([r for r in teams[other]["roster"] if r.get("sleeper_id") and r["role"] != "empty"], key=lambda r: -(r.get("value") or -1))
        packages.append((other, [mine[0]["sleeper_id"]], [theirs[1]["sleeper_id"]]))
        for partner, give, get_ in packages:
            body = {"league": league, "team": me, "partner": partner, "give": give, "get": get_}
            ev = post("/api/trades/evaluate", body)
            sdf.save(league, name(league, me, partner, give, get_), ev)
            for w in WINDOWS:
                sdf.save(league, name(league, me, partner, give, get_, w), post("/api/trades/evaluate", {**body, "window": w}))
            print(league, partner, give, get_, ev["interest"]["label"], ev.get("verdict"))
        # the tick: from the best package, one more of their players (or one less), the dial's label changes
        if top:
            partner, give, get_ = packages[0]
            base = json.loads((OUT / name(league, me, partner, give, get_)).read_text())["interest"]["label"]
            pool = sorted([r for r in teams[partner]["roster"] if r.get("sleeper_id") and r["role"] != "empty" and r["sleeper_id"] not in get_],
                          key=lambda r: -(r.get("value") or -1))
            cands = [(give, get_[:-1]) for _ in [0] if len(get_) > 1] + [(give[:-1], get_) for _ in [0] if len(give) > 1]
            cands += [(give, [*get_, r["sleeper_id"]]) for r in pool[:6]]
            for g2, t2 in cands:
                r = c.post("/api/trades/evaluate", json={"league": league, "team": me, "partner": partner, "give": g2, "get": t2})
                if r.status_code != 200 or r.json()["interest"]["label"] == base:
                    continue
                sdf.save(league, name(league, me, partner, g2, t2), r.json())
                packages_out[league] = {"partner": partner, "from": {"give": give, "get": get_, "label": base},
                                        "to": {"give": g2, "get": t2, "label": r.json()["interest"]["label"]}}
                print(league, "tick", base, "→", r.json()["interest"]["label"], g2, t2)
                break
        print(league, "saved")
    (OUT / "ia2_packages.json").write_text(json.dumps(packages_out, indent=1) + "\n")


if __name__ == "__main__":
    main()
