"""PlayerWire's briefs on the player card's news line (plan N2; docs/PLAYERWIRE.md).

The briefs live in the hosted database's own schema ``playerwire`` (written every 15 minutes by the Mac's
``scripts/playerwire_sync.py``, never by the nightly); this module reads them with the API's read-only role.

``for_card(gsis)`` -> at most 3 items, newest first, none older than 14 days:
``{headline, date, source, url, summary, kind: "playerwire", verification, related}`` — ``source`` is the first
evidence item's publisher + " via PlayerWire", ``url`` its https link, ``summary`` the brief's news text,
``verification`` PlayerWire's ``verification_status`` (official / reported / corroborated / disputed), ``related``
true when he is a related player of the brief rather than its subject. Only live, published briefs (``deleted`` is
false): a withdrawn brief has no text left to show anyway.

**Identity** (AGENTS.md rule 3, ids only): a brief belongs to the player its Sleeper id maps to in
``analytics.player_id_map``; without a mapped Sleeper id, to the player its gsis id maps to there. A brief whose
Sleeper id maps to one player and whose gsis id names another is a conflict and is shown to neither. A brief that maps
to nobody is kept (the replica holds every brief) and only counted: ``/api/status`` -> ``news.playerwire.unmapped``.
Related players (``playerwire.brief_players``) map the same way.

**On** unless ``LEAGUE_LAB_PLAYERWIRE=off`` (or the whole news line is off, ``LEAGUE_LAB_NEWS=off``: news.py). In
fixture mode (``LEAGUE_LAB_SLEEPER_FIXTURES``) only when ``LEAGUE_LAB_PLAYERWIRE_FIXTURES`` names a JSON file of rows
(``{as_of, player_id_map, briefs, brief_players, sync_state}``; ages measured from ``as_of``): a test never reads a
database for this. No schema, no grant, the marts mid-restore: no PlayerWire items (the card falls back to ESPN), one
warning in the log per outage, a minute's pause before the next try. Answers are cached a minute.
"""

from __future__ import annotations

import json
import logging
import math
import os
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from league_lab import anyleague as A

from .db import query

SWITCH_ENV = "LEAGUE_LAB_PLAYERWIRE"
FIXTURES_ENV = "LEAGUE_LAB_PLAYERWIRE_FIXTURES"
MAX_ITEMS = 3
MAX_AGE = timedelta(days=14)
CACHE_TTL_S = 60            # the sync runs every 15 minutes; a withdrawal reaches the card within a minute of it
BACKOFF_S = 60.0            # after a failed read, the card skips PlayerWire this long
VERIFICATION = ("official", "reported", "corroborated", "disputed")

_log = logging.getLogger("league_lab_api.playerwire")
_lock = threading.Lock()
_warned = False
_down_until = 0.0
_last_error: str | None = None
_fx_cache: tuple[str, float, dict] | None = None

# Candidates for one player: his own briefs (by the primary player's ids) and the briefs that name him as a related
# player, each with what both of the row's ids map to. The 14-day rule and the identity rule are applied in Python
# (`select`) so the SQL text and its parameters stay the same all day (the query cache keys on them).
CANDIDATES_SQL = """
select b.brief_id, b.version, b.status, b.deleted, b.headline, b.news, b.verification_status, b.published_at,
       b.evidence_url, b.evidence_publisher, 'primary' as role, b.primary_sleeper_id as sleeper_id,
       b.primary_gsis_id as gsis_id, ms.gsis_id as via_sleeper, mg.gsis_id as via_gsis
from playerwire.briefs b
left join analytics.player_id_map ms on ms.sleeper_id = b.primary_sleeper_id
left join analytics.player_id_map mg on mg.gsis_id = b.primary_gsis_id
where not b.deleted and b.status = 'published' and b.published_at >= now() - interval '15 days'
  and (ms.gsis_id = %s or mg.gsis_id = %s)
union all
select b.brief_id, b.version, b.status, b.deleted, b.headline, b.news, b.verification_status, b.published_at,
       b.evidence_url, b.evidence_publisher, 'related' as role, p.sleeper_id, p.gsis_id,
       ms.gsis_id as via_sleeper, mg.gsis_id as via_gsis
from playerwire.brief_players p
join playerwire.briefs b on b.brief_id = p.brief_id
left join analytics.player_id_map ms on ms.sleeper_id = p.sleeper_id
left join analytics.player_id_map mg on mg.gsis_id = p.gsis_id
where p.role = 'related' and not b.deleted and b.status = 'published'
  and b.published_at >= now() - interval '15 days'
  and (ms.gsis_id = %s or mg.gsis_id = %s)
"""

# /api/status: what the replica holds and how much of it maps to a player (resolved as `resolve` does).
STATUS_SQL = """
with r as (
  select b.deleted, b.status, b.published_at,
         case when ms.gsis_id is not null then
                case when b.primary_gsis_id is null or b.primary_gsis_id = ms.gsis_id then ms.gsis_id end
              else mg.gsis_id end as resolved,
         ms.gsis_id is not null and b.primary_gsis_id is not null and b.primary_gsis_id <> ms.gsis_id as conflicting
  from playerwire.briefs b
  left join analytics.player_id_map ms on ms.sleeper_id = b.primary_sleeper_id
  left join analytics.player_id_map mg on mg.gsis_id = b.primary_gsis_id
)
select count(*) filter (where not deleted) as rows,
       count(*) filter (where deleted) as withdrawn,
       max(published_at) filter (where not deleted and status = 'published') as newest_published_at,
       count(*) filter (where not deleted and resolved is null) as unmapped,
       count(*) filter (where not deleted and conflicting) as conflicting
from r
"""
SYNC_STATE_SQL = "select last_sync_at, last_error, last_error_at, high_watermark from playerwire.sync_state where id = 1"


# ------------------------------------------------------------------------------------------------ switches
def switched_off() -> bool:
    return (os.environ.get(SWITCH_ENV) or "").strip().lower() in ("off", "0", "false", "no")


def fixtures_path() -> Path | None:
    v = os.environ.get(FIXTURES_ENV)
    return Path(v) if v else None


def enabled() -> bool:
    if switched_off():
        return False
    return fixtures_path() is not None or not os.environ.get(A.FIXTURES_ENV)


# ------------------------------------------------------------------------------------------------ pure rules
def _s(v: Any) -> str | None:
    """A text cell (None / NaN / blank -> None)."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    s = str(v).strip()
    return s or None


def _when(v: Any) -> datetime | None:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    if hasattr(v, "to_pydatetime"):
        try:
            v = v.to_pydatetime()
        except (ValueError, TypeError):
            return None
    if isinstance(v, str):
        try:
            v = datetime.fromisoformat(v.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(v, datetime):
        return None
    return v if v.tzinfo else v.replace(tzinfo=UTC)


def _iso(d: datetime) -> str:
    return d.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resolve(sleeper_id: Any, gsis_id: Any, via_sleeper: Any, via_gsis: Any) -> str | None:
    """The gsis id a brief's player maps to through analytics.player_id_map: by his Sleeper id first (the gsis id the
    brief carries must then agree), else by his gsis id; None when neither maps or the two disagree."""
    by_sleeper, own_gsis = _s(via_sleeper), _s(gsis_id)
    if by_sleeper:
        return by_sleeper if own_gsis is None or own_gsis == by_sleeper else None
    return _s(via_gsis)


def item(r: dict) -> dict | None:
    """One row -> the card's item; None without a headline, a date or an https link."""
    head, when, url = _s(r.get("headline")), _when(r.get("published_at")), _s(r.get("evidence_url"))
    if not head or when is None or not url or not url.lower().startswith("https://"):
        return None
    publisher = _s(r.get("evidence_publisher"))
    verification = (_s(r.get("verification_status")) or "").lower()
    return {"headline": " ".join(head.split()), "date": _iso(when),
            "source": f"{publisher} via PlayerWire" if publisher else "PlayerWire", "url": url,
            "summary": _s(r.get("news")), "kind": "playerwire",
            "verification": verification if verification in VERIFICATION else None,
            "related": r.get("role") == "related"}


def select(rows: list[dict], gsis: str, now: datetime, *, n: int = MAX_ITEMS, max_age: timedelta = MAX_AGE) -> list[dict]:
    """The card's rule: rows that map to ``gsis``, live and published, dated within ``max_age`` of ``now`` (more than a
    day ahead is a bad date), one per brief (his own over a mention), newest first, at most ``n``."""
    best: dict[str, tuple[datetime, dict]] = {}
    for r in rows:
        if r.get("deleted") or (_s(r.get("status")) or "") != "published":
            continue
        if resolve(r.get("sleeper_id"), r.get("gsis_id"), r.get("via_sleeper"), r.get("via_gsis")) != gsis:
            continue
        it = item(r)
        if it is None:
            continue
        when = _when(r.get("published_at"))
        if when is None or when < now - max_age or when > now + timedelta(days=1):
            continue
        bid = str(r.get("brief_id"))
        if bid not in best or (best[bid][1]["related"] and not it["related"]):
            best[bid] = (when, it)
    return [it for _w, it in sorted(best.values(), key=lambda x: x[0], reverse=True)[:n]]


# ------------------------------------------------------------------------------------------------ fixtures
def _fixture() -> dict:
    global _fx_cache
    p = fixtures_path()
    assert p is not None
    st = p.stat()
    with _lock:
        if _fx_cache is not None and _fx_cache[0] == str(p) and _fx_cache[1] == st.st_mtime:
            return _fx_cache[2]
    d = json.loads(p.read_text())
    with _lock:
        _fx_cache = (str(p), st.st_mtime, d)
    return d


def _fixture_rows(fx: dict, gsis: str) -> list[dict]:
    """CANDIDATES_SQL over the fixture's tables (the same joins, in Python)."""
    by_sleeper = {str(m["sleeper_id"]): str(m["gsis_id"]) for m in fx.get("player_id_map", [])}
    by_gsis = {str(m["gsis_id"]): str(m["gsis_id"]) for m in fx.get("player_id_map", [])}
    briefs = {str(b["brief_id"]): b for b in fx.get("briefs", [])}
    out: list[dict] = []
    for b in briefs.values():
        s, g = _s(b.get("primary_sleeper_id")), _s(b.get("primary_gsis_id"))
        out.append({**b, "role": "primary", "sleeper_id": s, "gsis_id": g,
                    "via_sleeper": by_sleeper.get(s or ""), "via_gsis": by_gsis.get(g or "")})
    for p in fx.get("brief_players", []):
        b = briefs.get(str(p.get("brief_id")))
        if b is None or p.get("role") != "related":
            continue
        s, g = _s(p.get("sleeper_id")), _s(p.get("gsis_id"))
        out.append({**b, "role": "related", "sleeper_id": s, "gsis_id": g,
                    "via_sleeper": by_sleeper.get(s or ""), "via_gsis": by_gsis.get(g or "")})
    return [r for r in out if gsis in (r["via_sleeper"], r["via_gsis"])]


# ------------------------------------------------------------------------------------------------ the database
def _ok() -> None:
    global _warned, _last_error
    with _lock:
        _warned, _last_error = False, None


def _failed(exc: Exception) -> None:
    global _warned, _down_until, _last_error
    msg = f"{exc.__class__.__name__}: {str(exc).splitlines()[0] if str(exc) else ''}".strip()
    with _lock:
        first = not _warned
        _warned, _down_until, _last_error = True, time.monotonic() + BACKOFF_S, msg[:200]
    if first:
        _log.warning("PlayerWire briefs unavailable (%s): the news line shows ESPN only until they are back", msg)


def _records(df: Any) -> list[dict]:
    return [] if df is None or df.empty else df.astype(object).where(df.notna(), None).to_dict("records")


def for_card(gsis: str, now: datetime | None = None) -> list[dict]:
    """His PlayerWire items (never raises: the card never fails for its news)."""
    if not enabled() or not isinstance(gsis, str) or not gsis:
        return []
    try:
        if fixtures_path() is not None:
            fx = _fixture()
            clock = now or _when(fx.get("as_of")) or datetime.now(UTC)
            return select(_fixture_rows(fx, gsis), gsis, clock)
        if time.monotonic() < _down_until:
            return []
        rows = _records(query(CANDIDATES_SQL, (gsis,) * 4, ttl=CACHE_TTL_S))
        _ok()
        return select(rows, gsis, now or datetime.now(UTC))
    except Exception as exc:  # noqa: BLE001 - no schema / no grant / the marts mid-restore: ESPN only
        _failed(exc)
        return []


def info() -> dict:
    """/api/status -> news.playerwire."""
    if not enabled():
        return {"enabled": False}
    try:
        if fixtures_path() is not None:
            fx = _fixture()
            by_sleeper = {str(m["sleeper_id"]): str(m["gsis_id"]) for m in fx.get("player_id_map", [])}
            gsis_ids = {str(m["gsis_id"]) for m in fx.get("player_id_map", [])}
            live = [b for b in fx.get("briefs", []) if not b.get("deleted")]
            resolved = [resolve(b.get("primary_sleeper_id"), b.get("primary_gsis_id"),
                                by_sleeper.get(str(b.get("primary_sleeper_id"))),
                                b.get("primary_gsis_id") if str(b.get("primary_gsis_id")) in gsis_ids else None) for b in live]
            dates = [d for d in (_when(b.get("published_at")) for b in live if b.get("status") == "published") if d]
            st = fx.get("sync_state") or {}
            return {"enabled": True, "source": "fixtures", "rows": len(live),
                    "withdrawn": sum(1 for b in fx.get("briefs", []) if b.get("deleted")),
                    "newest_published_at": _iso(max(dates)) if dates else None,
                    "unmapped": sum(1 for r in resolved if r is None),
                    "last_sync_at": st.get("last_sync_at"), "last_error": st.get("last_error")}
        counts = _records(query(STATUS_SQL, ttl=CACHE_TTL_S))
        state = _records(query(SYNC_STATE_SQL, ttl=CACHE_TTL_S))
        _ok()
        c = counts[0] if counts else {}
        s = state[0] if state else {}
        newest, last = _when(c.get("newest_published_at")), _when(s.get("last_sync_at"))
        return {"enabled": True, "source": "database", "rows": int(c.get("rows") or 0),
                "withdrawn": int(c.get("withdrawn") or 0), "newest_published_at": _iso(newest) if newest else None,
                "unmapped": int(c.get("unmapped") or 0), "conflicting": int(c.get("conflicting") or 0),
                "last_sync_at": _iso(last) if last else None, "last_error": _s(s.get("last_error"))}
    except Exception as exc:  # noqa: BLE001 - a status line, never a failure
        _failed(exc)
        return {"enabled": True, "available": False, "error": _last_error}


def reset() -> None:
    global _warned, _down_until, _last_error, _fx_cache
    with _lock:
        _warned, _down_until, _last_error, _fx_cache = False, 0.0, None, None
