"""IZ-4 (Wave I-Z; the review's Pass 2: "surface sourced injury / personnel changes beside the affected decision").

A news item about a player in one of My Week's decisions sits on that decision — its words, source, time and what the
projection does with it — instead of in a separate feed the manager has to match up himself. The feed keeps only the
items that touch no decision (and is not drawn without them: IX-4's rule). The trade calculator's section 5 gets the
same line per player.

Nothing is inferred from news text: this module only MOVES lines the feed already built (`myweek.what_changed` /
`decision_feed`: the same words, source, time and forecast status) onto the decisions, or, for a trade, reads the same
feed (`news.recent`, its cache and its one-second budget) for the players involved. No number, verdict or order reads
it (`api/tests/test_iz4.py` checks the answer is identical with the feed on and off).
"""

from __future__ import annotations

import logging

import pandas as pd

log = logging.getLogger(__name__)

MAX_ON_DECISION = 2          # news lines shown on a decision; the rest under its "Why"


def _at(line: dict) -> str:
    return str(line.get("at") or "")


def _gsis_of_keys(rows: pd.DataFrame | None) -> dict[str, str]:
    if rows is None or rows.empty or "sleeper_player_id" not in rows or "gsis_id" not in rows:
        return {}
    out = {}
    for k, g in zip(rows["sleeper_player_id"], rows["gsis_id"], strict=False):
        if isinstance(k, str) and k and isinstance(g, str) and g:
            out[k] = g
    return out


def _players(dec: dict, key_gsis: dict[str, str]) -> set[str]:
    """The gsis ids of a decision's players: an action's start / sit (roster keys → ids; the claim's drop too), a
    review line's two players."""
    gs: set[str] = set()
    lists = [x for x in (dec.get("start"), dec.get("sit")) if isinstance(x, list)]
    for p in [q for x in lists for q in x] + ([dec["drop"]] if isinstance(dec.get("drop"), dict) else []):
        if isinstance(p, dict):
            g = p.get("gsis_id") or key_gsis.get(str(p.get("key") or ""))
            if g:
                gs.add(str(g))
    for side in ("start", "other"):
        p = dec.get(side)
        if isinstance(p, dict) and (p.get("gsis_id") or key_gsis.get(str(p.get("key") or ""))):
            gs.add(str(p.get("gsis_id") or key_gsis.get(str(p.get("key") or ""))))
    return gs


def attach(out: dict, rows: pd.DataFrame | None) -> dict:
    """My Week: each decision (`actions`, `more_actions`, `review`) gains `news` (at most two lines, the newest first)
    and `news_more` (the rest, for its "Why"); `changed.lines` keeps the lines no decision took (`changed.on_decisions`:
    how many moved). A line about a player in two decisions sits on both. Never raises."""
    try:
        ch = out.get("changed")
        lines = list(ch.get("lines") or []) if isinstance(ch, dict) else []
        decisions = [d for d in (out.get("actions") or []) + (out.get("more_actions") or []) + (out.get("review") or [])
                     if isinstance(d, dict)]
        for d in decisions:
            d["news"], d["news_more"] = [], []
        if not lines or not decisions:
            if isinstance(ch, dict):
                ch["on_decisions"] = 0
            return out
        key_gsis = _gsis_of_keys(rows)
        taken: set[int] = set()
        for d in decisions:
            gs = _players(d, key_gsis)
            hits = [(i, ln) for i, ln in enumerate(lines) if ln.get("gsis_id") and str(ln["gsis_id"]) in gs]
            hits.sort(key=lambda x: _at(x[1]), reverse=True)              # the newest first (ISO times sort as text)
            d["news"] = [ln for _, ln in hits[:MAX_ON_DECISION]]
            d["news_more"] = [ln for _, ln in hits[MAX_ON_DECISION:]]
            taken |= {i for i, _ in hits}
        ch["lines"] = [ln for i, ln in enumerate(lines) if i not in taken]
        ch["on_decisions"] = len(taken)
    except Exception:  # noqa: BLE001 - a news line must never cost the screen
        log.warning("decision_news.attach failed", exc_info=True)
    return out


def for_trade(ans: dict) -> dict:
    """The trade calculator's section 5: {sleeper id: [line]} for the players given, received and cut — the feed's
    newest item about each from the last 24 hours (`news.recent`: its cache, at most one second for what is not cached),
    in the feed's line shape (`myweek.decision_feed`). {} when the feed is off or has nothing. Never raises."""
    try:
        from . import news
        from .myweek import decision_feed
        ps = []
        for side in ("give", "get"):
            v = ans.get(side)
            for p in (v.get("players") if isinstance(v, dict) else v) or []:
                if isinstance(p, dict):
                    ps.append(p)
        for c in ans.get("cut") or []:
            if isinstance(c, dict) and isinstance(c.get("player"), dict):
                ps.append(c["player"])
        names = {str(p["gsis_id"]): str(p.get("player_name") or "") for p in ps if p.get("gsis_id")}
        key_of = {str(p["gsis_id"]): str(p.get("sleeper_id") or p["gsis_id"]) for p in ps if p.get("gsis_id")}
        if not names:
            return {}
        items = news.recent(list(names), names=names)
        lines = [{"kind": "news", "gsis_id": g, "player_name": names.get(g) or None, "text": it.get("headline") or "",
                  "source": it.get("source"), "at": it.get("date"), "url": it.get("url"), "about": it.get("about")}
                 for g, it in items if it.get("about") == "player"]
        lines = decision_feed(lines, None, None, None) if lines else []
        for ln in lines:
            ln["why_here"] = None              # "Your lineup this week" is My Week's words; section 5 names the side
        out: dict[str, list[dict]] = {}
        for ln in lines:
            out.setdefault(key_of.get(str(ln.get("gsis_id")), str(ln.get("gsis_id"))), []).append(ln)
        return out
    except Exception:  # noqa: BLE001
        log.warning("decision_news.for_trade failed", exc_info=True)
        return {}


def with_trade(ans):
    if isinstance(ans, dict):
        ans["news"] = for_trade(ans)
    return ans


# ---- JA-4 (Wave J-A): the news line on Waivers' top claims, without making Waivers wait. The claims answer as before
# (`/api/waivers` reads no news); the screen then asks for the claim players' lines here — at most MAX_IDS players (the
# claims shown), the feed's own reader (`news.recent`: its per-player cache, at most one second for what is not cached),
# the `read` bucket. A line arrives or does not; nothing reads it.
import re  # noqa: E402 - the block stays self-contained

from fastapi import APIRouter, HTTPException  # noqa: E402

router = APIRouter()
MAX_IDS = 4                                  # the three strongest claims and the one in focus
GSIS = re.compile(r"^\d{2}-\d{7}$")


def lines_for(ids: list[str]) -> dict[str, list[dict]]:
    """{gsis: [line]} — the feed's newest item of the last 24 hours about each player, in the feed's line shape
    (`myweek.decision_feed`; `why_here` dropped: a free agent is in no lineup). {} when the feed is off or has nothing."""
    from . import news
    from .myweek import decision_feed
    items = news.recent(list(ids))
    lines = [{"kind": "news", "gsis_id": g, "player_name": None, "text": it.get("headline") or "", "source": it.get("source"),
              "at": it.get("date"), "url": it.get("url"), "about": it.get("about")}
             for g, it in items if it.get("about") == "player"]
    out: dict[str, list[dict]] = {}
    for ln in decision_feed(lines, None, None, None) if lines else []:
        ln["why_here"] = None
        out.setdefault(str(ln["gsis_id"]), []).append(ln)
    return out


@router.get("/api/news/players")
def news_players(ids: str = ""):
    want = list(dict.fromkeys(x.strip() for x in str(ids)[:200].split(",") if x.strip()))
    if not want or len(want) > MAX_IDS or not all(GSIS.match(x) for x in want):
        raise HTTPException(status_code=400, detail=f"ids: one to {MAX_IDS} player ids (00-0012345), comma-separated")
    from fastapi.responses import JSONResponse
    try:
        body = {"lines": lines_for(want)}
    except Exception:  # noqa: BLE001 - a news line never costs the screen: no line, and the screen says nothing
        log.warning("decision_news.news_players failed", exc_info=True)
        body = {"lines": {}}
    return JSONResponse(body, headers={"Cache-Control": "private, max-age=60"})
# ---- end JA-4
