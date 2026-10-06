"""The context record on the site (Wave I-O, IO-1): how the cornerback calls and DFS's "Worth a look" have done.

``league-lab context-record`` (the nightly; ``src/league_lab/context_record.py``) keeps ``ops.context_record`` — every
player-week's context frozen before the week's first kickoff, the played weeks rebuilt once from as-of inputs — and
replaces ``ops.context_grade`` with its grade (n, the mean miss against the projection with a game-clustered bootstrap
interval, how many beat their projection, the difference from everyone else, and the sentences). This module only
reads that small table (≈20 rows):

* ``summary()`` — the interface fixed for the wave (IO-4's matchup board reads it lazily)::

      {"corner": {"graded": bool, "n": int, "words": str | None},
       "worth":  {"graded": bool, "n": int, "words": str | None}}

  plus ``corner["tiers"]`` (certainty/tier -> the chip's graded words and whether the interval holds 0). Never raises:
  without the table (the live site until the nightly applies it — rule 10), or on any failure, graded False and words
  None, and every reader keeps today's sentence.
* ``GET /api/context/record`` — the same, for the screens (``read`` bucket: a cached read of a ≈20-row table).

One memo region, ``context_record``: one entry (the grade), an hour (the grade changes once a night), ≈5 KB.
"""

from __future__ import annotations

import copy
import math

from fastapi import APIRouter
from league_lab import memo

from .db import query

router = APIRouter()

TTL_S = 3600.0
_cache = memo.region("context_record", ttl=TTL_S, max_entries=1)
EXISTS_SQL = "select to_regclass('ops.context_grade') is not null as ok"
GRADE_SQL = """select kind, grp, corner_certainty, corner_tier, n, games, mean_miss, lo, hi, beat, beat_share, vs_rest,
                      vs_rest_lo, vs_rest_hi, rest_n, rest_beat_share, span, scoring, words
               from ops.context_grade"""
EMPTY = {"corner": {"graded": False, "n": 0, "words": None, "tiers": {}},
         "worth": {"graded": False, "n": 0, "words": None}}


def clear() -> None:
    _cache.clear()


def _num(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _build() -> dict:
    ok = query(EXISTS_SQL, ttl=600.0)
    if ok.empty or not bool(ok.iloc[0, 0]):
        return copy.deepcopy(EMPTY)
    g = query(GRADE_SQL, ttl=600.0)
    if g.empty:
        return copy.deepcopy(EMPTY)
    rows = g.to_dict("records")
    summ = {r["grp"]: r for r in rows if r.get("kind") == "summary"}
    tiers = {}
    for r in rows:
        if r.get("kind") != "corner" or not r.get("corner_certainty") or not r.get("corner_tier"):
            continue
        lo, hi = _num(r.get("vs_rest_lo")), _num(r.get("vs_rest_hi"))
        tiers[f"{r['corner_certainty']}/{r['corner_tier']}"] = {
            "n": int(r.get("n") or 0), "vs_rest": _num(r.get("vs_rest")), "lo": lo, "hi": hi,
            "effect": None if lo is None or hi is None else ("none" if lo <= 0 <= hi else "measured"),
            "words": r.get("words")}
    out = copy.deepcopy(EMPTY)
    c, w = summ.get("corner"), summ.get("worth")
    if c and c.get("words"):
        out["corner"] = {"graded": True, "n": int(c.get("n") or 0), "words": str(c["words"]), "tiers": tiers}
    if w and w.get("words"):
        out["worth"] = {"graded": True, "n": int(w.get("n") or 0), "words": str(w["words"])}
    return out


def summary() -> dict:
    """{"corner": {"graded", "n", "words", "tiers"}, "worth": {"graded", "n", "words"}} — never raises; without the
    record: graded False, words None."""
    try:
        hit = _cache.get("grade")
        if hit is None:
            hit = _build()
            # no grade yet (the table appears with the nightly): look again in 10 minutes, not an hour
            _cache.put("grade", hit, ttl=TTL_S if hit["corner"]["graded"] or hit["worth"]["graded"] else 600.0)
        return copy.deepcopy(hit)
    except Exception:  # noqa: BLE001 - the interface: never raises (a missing table, a closed pool, anything)
        return copy.deepcopy(EMPTY)


def corner_grade(certainty: str | None, tier: str | None) -> dict | None:
    """The graded effect of one certainty x tier ({n, vs_rest, lo, hi, effect, words}), or None."""
    if not certainty or not tier:
        return None
    return summary()["corner"].get("tiers", {}).get(f"{certainty}/{tier}")


@router.get("/api/context/record")
def record_route():
    """How the context has done: the corner calls and "Worth a look" (``summary()``)."""
    return summary()
