"""The news line on the player card (Wave I-D, N1): ``news`` on ``/api/player/{gsis}`` from ESPN's player news.

``for_card(gsis)`` -> ``[{headline, date, source, url}]``: at most 3, newest first, none older than 14 days; [] when
there is nothing to show (no ESPN id for him, no news, the feed off or out). The feed itself (cache, bucket, fixtures,
what is kept) is ``league_lab.news_feed``; this module maps the player and decides whether the line is on.

**On** unless ``LEAGUE_LAB_NEWS=off``; in fixture mode (``LEAGUE_LAB_SLEEPER_FIXTURES``) only when the ESPN fixtures
are set too (``LEAGUE_LAB_ESPN_FIXTURES``), as the availability overlay: a test or this sandbox never calls ESPN.

**His ESPN id**: the id table (``db_playerids.csv``: ``availability.espn_to_gsis`` read backwards — the fixture copy
next to the ESPN fixtures in tests, ``player_ids.table()`` on the server), else Sleeper's directory (``espn_id`` of
his Sleeper id). Ids only, never a name (AGENTS.md rule 3).
"""

from __future__ import annotations

import os
import re
import threading
from datetime import timedelta

from league_lab import anyleague as A
from league_lab import news_feed as NF

from . import availability as AV
from .db import query

_rev: tuple[int, int, dict[str, str]] | None = None
_rev_lock = threading.Lock()


def enabled() -> bool:
    if NF.switched_off():
        return False
    return bool(os.environ.get(NF.FIXTURES_ENV)) or not os.environ.get(A.FIXTURES_ENV)


def _gsis_to_espn() -> dict[str, str]:
    """The id table read backwards (rebuilt when the table changes)."""
    global _rev
    t = AV.espn_to_gsis()
    with _rev_lock:
        if _rev is not None and _rev[0] == id(t) and _rev[1] == len(t):
            return _rev[2]
        rev: dict[str, str] = {}
        for e, g in t.items():
            rev.setdefault(str(g), str(e))
        _rev = (id(t), len(t), rev)
        return rev


def _from_sleeper(gsis: str) -> str | None:
    try:
        m = query("select sleeper_id from analytics.player_id_map where gsis_id = %s and sleeper_id is not null", (gsis,))
        if m.empty:
            return None
        p = A.sleeper().players().get(str(m["sleeper_id"].iloc[0])) or {}
        return NF.clean_id(p.get("espn_id"))
    except Exception:  # noqa: BLE001 - no database / Sleeper busy: no id, no line
        return None


def espn_id(gsis: str) -> str | None:
    if not isinstance(gsis, str) or not gsis:
        return None
    return NF.clean_id(_gsis_to_espn().get(gsis)) or _from_sleeper(gsis)


def for_card(gsis: str, name: str | None = None) -> list[dict]:
    """The card's ``news`` (never raises: the card never fails for its news). IF-4: the item about him first (each
    item carries ``about``: "player" | "league")."""
    if not enabled():
        return []
    try:
        eid = espn_id(gsis)
        items = NF.feed().latest(eid) if eid else []
        return ordered(items, name if name is not None else _name(gsis)) if items else []
    except Exception:  # noqa: BLE001 - an outage is no line
        return []


# ---- IF-4 (Wave I-F, the decision-quality review's table: "News on Williams's card uses a broad headline about DeVonta
# Smith"): the item about HIM first — RotoWire's per-player blurb (the feed's ``type: "Rotowire"``, kept as the source
# "RotoWire via ESPN"), or an ESPN story whose headline names him (his last name, a whole word); an article-level
# headline that does not is second and labelled "league news" on the card. The headline check is display only (which
# item to show first), never an identity join: the feed is already his by ESPN id.
SUFFIXES = {"jr", "jr.", "sr", "sr.", "ii", "iii", "iv", "v"}


def _name(gsis: str) -> str | None:
    try:
        df = query("select player_name from analytics.dim_player where gsis_id = %s", (gsis,))
        return None if df.empty else str(df["player_name"].iloc[0])
    except Exception:  # noqa: BLE001 - no name: the source decides alone
        return None


def _last(name: str | None) -> str | None:
    parts = [p for p in str(name or "").split() if p.lower() not in SUFFIXES]
    return parts[-1] if len(parts) >= 2 else None


def about(item: dict, name: str | None) -> str:
    """"player" (RotoWire's blurb on him, or the headline names him) or "league" (an article-level headline)."""
    if str(item.get("source") or "").lower().startswith("rotowire"):
        return "player"
    last = _last(name)
    head = str(item.get("headline") or "")
    if last and re.search(rf"(?<![\w'-]){re.escape(last)}(?![\w-])", head, flags=re.IGNORECASE):
        return "player"
    return "league"


def ordered(items: list[dict], name: str | None) -> list[dict]:
    """The items with ``about``, the ones about him first (newest first within each)."""
    tagged = [{**it, "about": about(it, name)} for it in items]
    return [x for x in tagged if x["about"] == "player"] + [x for x in tagged if x["about"] != "player"]


RECENT_HOURS = 24
RECENT_BUDGET_S = 1.0          # My Week waits at most this long for uncached news (the rest lands in the cache)


def recent(gsis_ids: list[str], *, names: dict[str, str] | None = None, hours: int = RECENT_HOURS,
           budget_s: float = RECENT_BUDGET_S) -> list[tuple[str, dict]]:
    """My Week's "What changed": per player (this week's starters) the newest item of the last ``hours`` about him (a
    league item only when nothing about him is that recent), newest first. The feed's own cache and bucket apply; the
    reads run side by side and whatever has not answered within ``budget_s`` is left for the next visit (its copy lands
    in the cache). [] when the feed is off. Never raises."""
    if not enabled() or not gsis_ids:
        return []
    names = names or {}
    try:
        from concurrent.futures import ThreadPoolExecutor, wait
        f = NF.feed()
        ids = {g: espn_id(g) for g in gsis_ids}
        ids = {g: e for g, e in ids.items() if e}
        if not ids:
            return []
        pool = ThreadPoolExecutor(max_workers=min(8, len(ids)))
        futs = {pool.submit(f.copy, e): g for g, e in ids.items()}
        done, _ = wait(futs, timeout=budget_s)
        pool.shutdown(wait=False)
        out: list[tuple[str, dict]] = []
        for fu in done:
            g = futs[fu]
            d = fu.result() if fu.exception() is None else None
            if not d:
                continue
            now = f.now_for(d)
            items = NF.fresh(d.get("items") or [], now, max_age=timedelta(hours=hours))
            best = ordered(items, names.get(g) or _name(g))
            if best:
                out.append((g, best[0]))
        # newest first within each kind: the about-him items lead
        mine = sorted((x for x in out if x[1].get("about") == "player"), key=lambda x: x[1].get("date") or "", reverse=True)
        rest = sorted((x for x in out if x[1].get("about") != "player"), key=lambda x: x[1].get("date") or "", reverse=True)
        return mine + rest
    except Exception:  # noqa: BLE001 - an outage is no line
        return []
# ---- end IF-4


def info() -> dict:
    """/api/status's block."""
    if not enabled():
        return {"enabled": False}
    return {"enabled": True, **NF.feed().stats()}


def reset() -> None:
    global _rev
    _rev = None
    NF.reset()
