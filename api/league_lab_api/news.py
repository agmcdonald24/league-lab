"""The news line on the player card (Wave I-D, N1; N2): ``news`` on ``/api/player/{gsis}``.

``for_card(gsis)`` -> at most 3 items: **PlayerWire's briefs first** (``playerwire.for_card``: his hand-reviewed briefs
from the hosted ``playerwire`` schema, newest first, none older than 14 days, ``kind: "playerwire"`` with ``summary`` /
``verification`` / ``related``), then **ESPN's headlines** fill the slots left (newest first, none older than 14 days,
``kind: "espn"``; ESPN is not asked at all when PlayerWire fills all three). Every item keeps N1's four keys
``{headline, date, source, url}``; the others are new keys only. [] when there is nothing to show. ESPN's feed (cache,
bucket, fixtures, what is kept) is ``league_lab.news_feed``; this module maps the player and decides what is on.

**Switches**: ``LEAGUE_LAB_NEWS=off`` turns the whole line off; ``LEAGUE_LAB_PLAYERWIRE=off`` PlayerWire only (ESPN as
in N1). PlayerWire unreachable (no schema yet, the marts mid-restore): ESPN only, never an error.

**ESPN on** unless ``LEAGUE_LAB_NEWS=off``; in fixture mode (``LEAGUE_LAB_SLEEPER_FIXTURES``) only when the ESPN fixtures
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
from . import playerwire as PW
from .db import query

_rev: tuple[int, int, dict[str, str]] | None = None
_rev_lock = threading.Lock()


def espn_enabled() -> bool:
    if NF.switched_off():
        return False
    return bool(os.environ.get(NF.FIXTURES_ENV)) or not os.environ.get(A.FIXTURES_ENV)


def playerwire_enabled() -> bool:
    return not NF.switched_off() and PW.enabled()


def enabled() -> bool:
    """Is there a news line at all (ESPN's or PlayerWire's)."""
    return espn_enabled() or playerwire_enabled()


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


def _espn(gsis: str) -> list[dict]:
    try:
        eid = espn_id(gsis)
        return [{**it, "kind": "espn"} for it in (NF.feed().latest(eid) if eid else [])]
    except Exception:  # noqa: BLE001 - an outage is no line
        return []


def for_card(gsis: str) -> list[dict]:
    """The card's ``news`` (never raises: the card never fails for its news)."""
    out: list[dict] = []
    if playerwire_enabled():
        out = PW.for_card(str(gsis))[: NF.MAX_ITEMS]
    if len(out) < NF.MAX_ITEMS and espn_enabled():
        out += _espn(gsis)[: NF.MAX_ITEMS - len(out)]
    return out


def info() -> dict:
    """/api/status's block: ESPN's feed at the top level (N1), PlayerWire's replica under ``playerwire`` (N2)."""
    if not enabled():
        return {"enabled": False}
    espn = NF.feed().stats() if espn_enabled() else {"espn": "off"}
    return {"enabled": True, **espn, "playerwire": PW.info()}


def reset() -> None:
    global _rev
    _rev = None
    NF.reset()
    PW.reset()
