"""The context record on the site (Wave I-O, IO-1): how the cornerback calls and DFS's "Worth a look" have done.

``league-lab context-record`` (the nightly; ``src/league_lab/context_record.py``) keeps ``ops.context_record`` — every
player-week's context frozen before the week's first kickoff, the played weeks rebuilt once from as-of inputs — and
replaces ``ops.context_grade`` with its grade (n, the mean miss against the projection with a game-clustered bootstrap
interval, how many beat their projection, the difference from everyone else, and the sentences). This module only
reads that small table (≈20 rows):

* ``summary()`` — the interface fixed for the wave (IO-4's matchup board reads it lazily)::

      {"corner": {"graded": bool, "n": int, "words": str | None},
       "worth":  {"graded": bool, "n": int, "words": str | None}}

  plus ``worth["line"]`` (fix round: the DFS screen's one line now that the list is off — every number from the
  grade) and ``corner["tiers"]`` (certainty/tier -> the chip's graded words and whether the interval holds 0).
  **Wave I-P (IP-3)** adds, same shape: ``"trend"`` (what "below / above expectation" on Trends has meant for the next
  game: ``words``, ``head`` — Trends' line under its title — and ``tags`` below / above -> the next game's miss against
  the projection vs the rest and the raw change) and ``"role"`` (what "role up / down" has meant: ``words`` and
  ``trends`` up / down). A database with Wave I-O's grade only (no ``trend`` / ``role`` rows) answers them graded
  False and keeps ``corner`` and ``worth`` as they were. Never raises:
  without the table (the live site until the nightly applies it — rule 10), or on any failure, graded False and words
  None, and every reader keeps today's sentence.
* ``GET /api/context/record`` — the same, for the screens (``read`` bucket: a cached read of a ≈20-row table).

One memo region, ``context_record``: one entry (the grade), an hour (the grade changes once a night), ≈8 KB (Wave I-P:
the trend and role cells added ≈3 KB; the table ≈190 rows, 80 kB).
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
         "worth": {"graded": False, "n": 0, "words": None, "line": None},
         # ---- IP-3 (Wave I-P): Trends' tag and the role trend, graded (absent rows: graded False)
         "trend": {"graded": False, "n": 0, "words": None, "head": None, "tags": {}},
         "role": {"graded": False, "n": 0, "words": None, "trends": {}},
         # ---- end IP-3
         # ---- IR-4 (Wave I-R): the trade calculator's horizons by position and the useful-decision grade (kinds
         # `horizon` / `useful`; cells "<kind>:<position>/<window>" -> miss, order, the baseline's, the sentence)
         "horizon": {"graded": False, "n": 0, "words": None, "cells": {}}}
         # ---- end IR-4


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
        line = (summ.get("worth_off") or {}).get("words")
        out["worth"] = {"graded": True, "n": int(w.get("n") or 0), "words": str(w["words"]),
                        "line": str(line) if isinstance(line, str) and line else None}
    # ---- IP-3 (Wave I-P): Trends' tag and the role trend
    t, rl = summ.get("trend"), summ.get("role")
    if t and t.get("words"):
        head = (summ.get("trend_head") or {}).get("words")
        out["trend"] = {"graded": True, "n": int(t.get("n") or 0), "words": str(t["words"]),
                        "head": str(head) if isinstance(head, str) and head else None,
                        "tags": {tag: _cell(rows, "trend", f"{tag}/all/all/1", raw=True) for tag in ("below", "above")}}
    if rl and rl.get("words"):
        out["role"] = {"graded": True, "n": int(rl.get("n") or 0), "words": str(rl["words"]),
                       "trends": {tr: _cell(rows, "role", f"{tr}/all/all/1") for tr in ("up", "down")}}
    # ---- end IP-3
    # ---- IR-4 (Wave I-R): the horizons and the useful-decision grade
    hz = {f"{r['kind']}:{r['grp']}": {"miss": _num(r.get("mean_miss")), "order": _num(r.get("beat_share")),
                                      "base_order": _num(r.get("rest_beat_share")), "vs_base": _num(r.get("vs_rest")),
                                      "n": None if r.get("n") is None or not _num(r.get("n")) else int(r["n"]),
                                      "span": r.get("span") if isinstance(r.get("span"), str) else None,
                                      "words": r.get("words") if isinstance(r.get("words"), str) else None}
          for r in rows if r.get("kind") in ("horizon", "useful") and r.get("grp")}
    if hz:
        out["horizon"] = {"graded": True, "n": len(hz), "words": None, "cells": hz}
    # ---- end IR-4
    return out


# ---- IP-3 fix round (Wave I-P): the one line the Trades screen's "scoring below / above his work" lists carry
def _sg(x) -> str:
    """+0.5 / −0.9 (a true minus sign) / 0.0, as the record's sentences write an interval."""
    v = round(float(x or 0), 1)
    return "0.0" if v == 0 else f"{'+' if v > 0 else '−'}{abs(v):.1f}"


def gap_line(trend: dict | None = None) -> str | None:
    """"Their projections already expect the gap to close part-way: no edge in buying or selling on it — graded on 4,282
    games (2025 and 2026 weeks 1–4, Half PPR)." from ``summary()["trend"]`` (a measured side says its number instead);
    None without the record."""
    t = trend if trend is not None else summary()["trend"]
    if not t or not t.get("graded"):
        return None
    tags = t.get("tags") or {}
    b, a = tags.get("below") or {}, tags.get("above") or {}
    span = b.get("span") or a.get("span")
    where = f" ({span}, Half PPR)" if span else " (Half PPR)"
    n = int(t.get("n") or 0)
    if b.get("effect") != "measured" and a.get("effect") != "measured":
        return (f"Their projections already expect the gap to close part-way: no edge in buying or selling on it — "
                f"graded on {n:,} games{where}.")
    parts = []
    for word, c in (("below", b), ("above", a)):
        v = c.get("vs_rest")
        if c.get("effect") == "measured" and v is not None:
            parts.append(f"players {word} their work finished {abs(v):.1f} points {'above' if v > 0 else 'below'} the rest "
                         f"against their projection ({_sg(c.get('lo'))} to {_sg(c.get('hi'))})")
    return (f"Their projections already expect the gap to close part-way; graded on {n:,} games{where}, "
            + " and ".join(parts) + ". The lists are ordered by lineup fit, not by the gap.")


# ---- IP-3 (Wave I-P)
def _cell(rows: list[dict], kind: str, grp: str, raw: bool = False) -> dict | None:
    """One graded group as the screens read it: n, the miss against the projection vs the rest with its interval,
    ``effect`` none / measured, and (``raw``) the change in points per game against before."""
    r = next((x for x in rows if x.get("kind") == kind and x.get("grp") == grp), None)
    if not r:
        return None
    lo, hi = _num(r.get("vs_rest_lo")), _num(r.get("vs_rest_hi"))
    out = {"n": int(r.get("n") or 0), "vs_rest": _num(r.get("vs_rest")), "lo": lo, "hi": hi,
           "effect": None if lo is None or hi is None else ("none" if lo <= 0 <= hi else "measured"),
           "span": r["span"] if isinstance(r.get("span"), str) else None}
    if raw:
        x = next((y for y in rows if y.get("kind") == f"{kind}_raw" and y.get("grp") == grp), None)
        out["raw"] = _num(x.get("mean_miss")) if x else None
    return out
# ---- end IP-3


def summary() -> dict:
    """{"corner": {"graded", "n", "words", "tiers"}, "worth": {"graded", "n", "words"}, "trend": {…}, "role": {…}} —
    never raises; without the record: graded False, words None."""
    try:
        hit = _cache.get("grade")
        if hit is None:
            hit = _build()
            # no grade yet (the table appears with the nightly): look again in 10 minutes, not an hour
            _cache.put("grade", hit, ttl=TTL_S if any(hit[k]["graded"] for k in hit) else 600.0)
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
    """How the context has done: the corner calls, "Worth a look", Trends' tag and the role trend (``summary()``)."""
    return summary()
