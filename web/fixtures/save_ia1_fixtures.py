"""Wave I-A (IA-1): bring the saved My Week and Trends fixtures to the new answers, in place, without re-saving them
whole (the other screens' tests read the same files):

* My Week (`my-week_*.json` here and `web/e2e/i0a/`): every lineup row gets `headshot_url` and `team` (dim_player); every
  card gets its reason sentence (`why`) and the new block order — the call, the reason, then the small print (how often
  he outscores the other player, the numbers, the ranges, the matchups). A card the API answers today with the same
  pair (slot, starter, other player) is copied from the API (in-process, this worktree's database; the house leagues);
  any other card (the fictional Test League, an older Scrubs board) is rebuilt from its own saved numbers with
  `cards.reason_line` — the matchup read back from its saved caption ("CeeDee Lamb vs HOU (#1 vs WR)"), his team from
  dim_player, his share of the work from the database (`cards.reason_facts`).
* Trends (`trends_*.json`): every player row gets the work a game (`targets_pg_l3` … `snap_pct_l3`), `why` and `cause`
  (`research.trend_work` / `trend_why`, the API's own functions).

    cd api && LEAGUE_LAB_SLEEPER_FIXTURES=$PWD/tests/fixtures/sleeper uv run python ../web/fixtures/save_ia1_fixtures.py
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import pandas as pd

OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(OUT.parents[1] / "api"))
os.environ.pop("LEAGUE_LAB_APP_PASSWORD", None)
os.environ.pop("LEAGUE_LAB_API_SECRET", None)

from fastapi.testclient import TestClient  # noqa: E402
from league_lab_api import research  # noqa: E402
from league_lab_api.applib import cards, links  # noqa: E402
from league_lab_api.db import query  # noqa: E402
from league_lab_api.main import app  # noqa: E402

DYN, SCRUBS, TEST = "1321941740235550720", "1389709692405551104", "9000000000000000001"
SEASON, WEEK = 2026, 4
MATCHUP = re.compile(r"^(.+?) vs ([A-Z]{2,3}) \(#(\d+) vs ([A-Z]+)\)$")
FLAG = re.compile(r"^⚠️ (.+?) is (.+)\.$")
c = TestClient(app)


def save(path: Path, d: dict, compact: bool = False) -> None:
    """In the file's own format: My Week indented (make_fixtures.py), the research answers compact (make_research_fixtures.py)."""
    text = json.dumps(d, ensure_ascii=False, separators=(",", ":")) if compact else json.dumps(d, indent=1, ensure_ascii=False)
    path.write_text(text + "\n")


def dim(ids: list[str]) -> dict[str, dict]:
    df = query("select gsis_id, headshot_url, latest_team, position from analytics.dim_player where gsis_id = any(%s)", (ids,))
    return {r["gsis_id"]: r for r in df.to_dict("records")}


def rebuild(card: dict, people: dict) -> dict:
    """A saved card in the new block order, its reason from its own numbers (see the module docstring)."""
    blocks = card["blocks"]
    head, rest = blocks[0], blocks[1:]
    caption = next((b["text"] for b in rest if b["kind"] == "caption"), "")
    lines = caption.split("  \n") if caption else []
    d = {k: card.get(k) for k in ("slot", "gsis_id", "player_name", "alt_gsis_id", "alt_name", "margin", "p_win", "value", "alt_value")}
    for line in lines:
        for part in line.split(" · "):
            m = MATCHUP.match(part)
            if m:
                side = "" if m.group(1) == card["player_name"] else "alt_"
                d[side + "opponent"], d[side + "opp_rank"], d[side + "position"] = m.group(2), int(m.group(3)), m.group(4)
        f = FLAG.match(line)
        if f:
            d[("" if f.group(1) == card["player_name"] else "alt_") + "report_status"] = f.group(2)
    for side, gid in (("", card["gsis_id"]), ("alt_", card["alt_gsis_id"])):
        p = people.get(gid) or {}
        d[side + "team"] = p.get("latest_team")
        d.setdefault(side + "position", p.get("position"))
    facts, nicks = cards.reason_facts(pd.DataFrame([d]), SEASON, WEEK)
    why = links(cards.reason_line(d, facts, nicks))
    odds = [b["text"].replace("**", "") for b in rest if b["kind"] == "markdown"]
    odds = [re.sub(r" Too close to lose sleep over — .*$", "", t) for t in odds]
    small = " ".join(odds)
    new_caption = "  \n".join([small, *lines] if small else lines)
    card["why"] = why
    card["blocks"] = [head, {"kind": "markdown", "text": why}, {"kind": "caption", "text": new_caption}]
    return card


def my_week(path: Path, league: str, team: int) -> None:
    saved = json.loads(path.read_text())
    if any(card.get("why") for card in saved["cards"]):
        print(path.name, "already has reasons")
        return
    live = {}
    if league != TEST:
        a = c.get("/api/my-week", params={"league": league, "team": team}).json()
        live = {(x["slot"], x["gsis_id"], x["alt_gsis_id"]): x for x in a.get("cards", [])}
    ids = sorted({g for r in saved["lineup_full"] + saved["lineup"] for g in [r.get("gsis_id")] if g}
                 | {g for x in saved["cards"] for g in (x["gsis_id"], x["alt_gsis_id"]) if g})
    people = dim(ids)
    for r in saved["lineup"] + saved["lineup_full"]:
        p = people.get(r.get("gsis_id") or "") or {}
        r["headshot_url"] = p.get("headshot_url")
        r["team"] = p.get("latest_team") if r.get("position") != "DEF" else r.get("team")
    out = []
    for card in saved["cards"]:
        hit = live.get((card["slot"], card["gsis_id"], card["alt_gsis_id"]))
        if hit is not None:
            card["why"], card["blocks"] = hit["why"], hit["blocks"]
            out.append(card)
        else:
            out.append(rebuild(card, people))
    saved["cards"] = out
    save(path, saved)
    print(path.name, [("api" if (x["slot"], x["gsis_id"], x["alt_gsis_id"]) in live else "rebuilt", x["why"]) for x in out])


def trends(league: str) -> None:
    path = OUT / f"trends_{league}.json"
    saved = json.loads(path.read_text())
    ids = [p["gsis_id"] for p in saved["players"]]
    work = {r["gsis_id"]: r for r in research.trend_work(saved.get("season") or SEASON, WEEK, ids).to_dict("records")}
    for p in saved["players"]:
        w = work.get(p["gsis_id"], {})
        for col in research.WORK_COLS:
            v = research._f(w.get(col))
            p[col] = None if v is None else (round(v, 2) if col == "snap_pct_l3" else round(v, 1) if col.endswith(("_pg", "_l3")) else int(v))
        p["why"] = research.trend_why({**p, **w})
        p["cause"] = research.trend_cause({**p, **w})
    save(path, saved, compact=True)
    print(path.name, sum(1 for p in saved["players"] if p["cause"]), "of", len(saved["players"]), "with a reason")


def main() -> None:
    my_week(OUT / f"my-week_{DYN}_12.json", DYN, 12)
    my_week(OUT / f"my-week_{SCRUBS}_2.json", SCRUBS, 2)
    my_week(OUT / f"my-week_{TEST}_3.json", TEST, 3)
    my_week(OUT.parent / "e2e" / "i0a" / f"my-week_{SCRUBS}_2.json", SCRUBS, 2)
    for league in (DYN, SCRUBS, TEST):
        trends(league)


if __name__ == "__main__":
    main()
