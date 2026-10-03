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
import threading

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


def for_card(gsis: str) -> list[dict]:
    """The card's ``news`` (never raises: the card never fails for its news)."""
    if not enabled():
        return []
    try:
        eid = espn_id(gsis)
        return NF.feed().latest(eid) if eid else []
    except Exception:  # noqa: BLE001 - an outage is no line
        return []


def info() -> dict:
    """/api/status's block."""
    if not enabled():
        return {"enabled": False}
    return {"enabled": True, **NF.feed().stats()}


def reset() -> None:
    global _rev
    _rev = None
    NF.reset()
