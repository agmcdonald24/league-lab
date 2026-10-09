"""Wave I-R (IR-2 fix round): RE-SAVE every saved trade-calculator answer (POST /api/trades/evaluate) so it carries the
`decision` object the calculator reads (and IR-4's provenance / caveats, the starter rule). The same requests as before —
each top-level `trades_evaluate_*.json` is re-asked from its own content (league, team, partner, give, get, window); each
recorded map (`*/api_*.json`) re-asks its own `/api/trades/evaluate` keys — in-process (FastAPI's TestClient) on the
fixtures' database at the suites' pinned moment, the Test League on demand from the Sleeper fixtures, MFL 70587 from the
MFL fixtures. Nothing else is re-saved. A request that no longer answers 200 keeps its old answer and is printed.

    cd api && uv run python ../web/fixtures/save_ir2_fixtures.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

OUT = Path(__file__).resolve().parent
API = OUT.parents[1] / "api"
os.environ.update({"LEAGUE_LAB_NOW": "2026-10-03T16:00:00Z", "LEAGUE_LAB_SLEEPER_FIXTURES": str(API / "tests/fixtures/sleeper"),
                   "LEAGUE_LAB_MFL_FIXTURES": str(API / "tests/fixtures/mfl"), "LEAGUE_LAB_MFL_YEAR": "2026",
                   "LEAGUE_LAB_PLAYER_IDS_CSV": str(API / "tests/fixtures/ff/db_playerids.csv"), "LEAGUE_LAB_GATE": "open",
                   "LEAGUE_LAB_AVAILABILITY": "off", "LEAGUE_LAB_USAGE": "off", "LEAGUE_LAB_NEWS": "off",
                   "LEAGUE_LAB_RATE_LIMIT": "off"})
for k in ("LEAGUE_LAB_APP_PASSWORD", "LEAGUE_LAB_API_SECRET", "LEAGUE_LAB_ESPN_FIXTURES"):
    os.environ.pop(k, None)
spec = importlib.util.spec_from_file_location("save_decision_fixtures", OUT / "save_decision_fixtures.py")
sdf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sdf)
sys.path.insert(0, str(API))

from fastapi.testclient import TestClient  # noqa: E402

from league_lab_api.main import app  # noqa: E402

c = TestClient(app)


def top_level() -> None:
    for f in sorted(OUT.glob("trades_evaluate_*.json")):
        old = json.loads(f.read_text())
        body = {"league": old["league_id"], "team": old["roster_id"], "partner": old["partner"],
                "give": [p["sleeper_id"] for p in old["give"]], "get": [p["sleeper_id"] for p in old["get"]]}
        if old.get("window") and old["window"] != "next4":
            body["window"] = old["window"]
        r = c.post("/api/trades/evaluate", json=body)
        if r.status_code != 200:
            print("KEPT (", r.status_code, ")", f.name, r.text[:200])
            continue
        sdf.save(str(old["league_id"]), f.name, r.json())
        print("saved", f.name, r.json()["decision"]["dial"]["label"])


def recorded() -> None:
    for f in sorted(OUT.glob("*/api_*.json")):
        if f.parent.name in ("ir2", "ir4"):
            continue
        saved = json.loads(f.read_text())
        keys = [k for k in saved if k.startswith(("/api/trades/evaluate", "POST /api/trades/evaluate"))]
        if not keys:
            continue
        for k in keys:
            path, _, body = k.removeprefix("POST ").partition(" ")
            u = urlsplit(path)
            r = c.post(u.path, params=dict(parse_qsl(u.query)), json=json.loads(body) if body else None)
            if r.status_code != 200 and saved[k].get("status") == 200:
                print("KEPT (", r.status_code, ")", f.name, k[:120], r.text[:200])
                continue
            try:
                saved[k] = {"status": r.status_code, "body": r.json()}
            except ValueError:
                saved[k] = {"status": r.status_code, "body": r.text}
            print("saved", f.parent.name, k[:100], r.status_code)
        f.write_text(json.dumps(saved, indent=1) + "\n")


# ---- IS-3 (Wave I-S): League of Scrubs' tick package for e2e/ia2 (tick a player: the dial's label changes) and e2e/ib2.
# The one saved in ia2_packages.json (team 2 ↔ 9, Tuten for …) is no longer a legal trade on the fixtures' database.
# The replacement was found by the same rule as save_ia2_fixtures.py on today's rosters (players on the same roster in
# the saved team fixtures and in the database): MacZaddy's Kyren Williams for Christian McCaffrey (team 1), then
# ticking Cam Skattebo as well changes the dial's label.
SCRUBS_TICK = {"partner": 1, "from": {"give": ["8150"], "get": ["4034"]}, "to": {"give": ["8150"], "get": ["4034", "12481"]}}


def scrubs_package() -> None:
    lg, me = sdf.SCRUBS, 2
    pk = json.loads((OUT / "ia2_packages.json").read_text())
    entry = {"partner": SCRUBS_TICK["partner"]}
    for side in ("from", "to"):
        give, get_ = SCRUBS_TICK[side]["give"], SCRUBS_TICK[side]["get"]
        body = {"league": lg, "team": me, "partner": SCRUBS_TICK["partner"], "give": give, "get": get_}
        stem = f"{lg}_{me}_{SCRUBS_TICK['partner']}_{'-'.join(sorted(give))}_{'-'.join(sorted(get_))}.json"
        for w in (None, "week", "ros", "playoffs"):
            r = c.post("/api/trades/evaluate", json={**body, **({"window": w} if w else {})})
            r.raise_for_status()
            sdf.save(lg, f"trades_evaluate_{w + '_' if w else ''}{stem}", r.json())
            if w is None:
                entry[side] = {"give": give, "get": get_, "label": r.json()["decision"]["dial"]["label"]}
    assert entry["from"]["label"] != entry["to"]["label"], "the tick must change the dial's label"
    pk[lg] = entry
    (OUT / "ia2_packages.json").write_text(json.dumps(pk, indent=1) + "\n")
    print("scrubs tick", entry["from"]["label"], "->", entry["to"]["label"])


# ---- IT-1 (Wave I-T): the Trade Finder's answers on the calculator's basis. Every saved `trades_partners_*.json` is
# re-asked with its own league, team, `want` and window (from its name); every recording's `/api/trades/partners` key
# with its own query; and the package each saved Finder answer leads to ("Try it": its first row and its first
# credible row) is saved for the calculator over the four windows, so the calculator opens on a saved answer. The old
# Scrubs package that is no longer a legal trade (`…_2_9_12490_…`) is removed.
def evaluate_name(league: str, me: int, partner: int, give, get_, window: str | None = None) -> str:
    w = f"{window}_" if window and window != "next4" else ""
    return f"trades_evaluate_{w}{league}_{me}_{partner}_{'-'.join(sorted(give))}_{'-'.join(sorted(get_))}.json"


def finder() -> None:
    for old in OUT.glob("trades_evaluate_*1389709692405551104_2_9_12490_*.json"):
        old.unlink()
        print("removed", old.name)
    leads: set[tuple] = set()
    for f in sorted(OUT.glob("trades_partners_*.json")):
        parts = f.stem.split("_")             # trades partners <league> <team> <want> [window]
        league, team, want = parts[2], int(parts[3]), parts[4]
        window = parts[5] if len(parts) > 5 else None
        params = {"league": league, "team": team, **({} if want == "ALL" else {"want": want}),
                  **({"window": window} if window else {})}
        r = c.get("/api/trades/partners", params=params)
        if r.status_code != 200:
            print("KEPT (", r.status_code, ")", f.name, r.text[:200])
            continue
        ans = r.json()
        sdf.save(league, f.name, ans)
        rows = ans.get("partners") or []
        if want == "ALL" and window is None:
            for row in [rows[0]] if rows else []:
                leads.add((league, team, row["partner"], tuple(x["sleeper_id"] for x in row["give"]),
                           tuple(x["sleeper_id"] for x in row["get"])))
            cred = next((x for x in rows if x.get("tier") == "credible"), None)
            if cred is not None:
                leads.add((league, team, cred["partner"], tuple(x["sleeper_id"] for x in cred["give"]),
                           tuple(x["sleeper_id"] for x in cred["get"])))
        print("saved", f.name, len(rows), "rows,", ans.get("credible_count"), "credible")
    for league, team, partner, give, get_ in sorted(leads):
        body = {"league": league, "team": team, "partner": partner, "give": list(give), "get": list(get_)}
        for w in (None, "week", "ros", "playoffs"):
            r = c.post("/api/trades/evaluate", json={**body, **({"window": w} if w else {})})
            if r.status_code == 200:
                sdf.save(league, evaluate_name(league, team, partner, give, get_, w), r.json())
        print("saved the calculator's answers for", league, team, partner, give, get_)
    for f in sorted(OUT.glob("*/api_*.json")):
        if f.parent.name in ("ir2", "ir4"):
            continue
        saved = json.loads(f.read_text())
        keys = [k for k in saved if k.split(" ")[-1].startswith("/api/trades/partners") or k.startswith("/api/trades/partners")]
        if not keys:
            continue
        for k in keys:
            path = k.removeprefix("GET ")
            u = urlsplit(path)
            r = c.get(u.path, params=dict(parse_qsl(u.query)))
            saved[k] = {"status": r.status_code, "body": r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text}
            print("saved", f.parent.name, k[:100], r.status_code)
        f.write_text(json.dumps(saved, indent=1) + "\n")


def package_labels() -> None:
    """ia2_packages.json's labels from the re-saved answers (the tick's from / to: the dial's label must change)."""
    pk = json.loads((OUT / "ia2_packages.json").read_text())
    for lg, v in pk.items():
        me = sdf.MINE[lg]
        for side in ("from", "to"):
            d = json.loads((OUT / evaluate_name(lg, me, v["partner"], v[side]["give"], v[side]["get"])).read_text())
            v[side]["label"] = d["decision"]["dial"]["label"]
        print("tick", lg, v["from"]["label"], "->", v["to"]["label"], "" if v["from"]["label"] != v["to"]["label"] else "SAME")
    (OUT / "ia2_packages.json").write_text(json.dumps(pk, indent=1) + "\n")


if __name__ == "__main__":
    if "--finder" in sys.argv:
        finder()
        top_level()
        recorded()
        package_labels()
        sys.exit(0)
    if "--scrubs" in sys.argv:
        scrubs_package()
        sys.exit(0)
    if "--recorded" not in sys.argv:
        top_level()
    recorded()
