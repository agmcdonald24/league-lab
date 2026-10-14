"""JB-2 (Wave J-B): a close call on My Week says when Sleeper's numbers lean the other way.

On a close call (the screen's own rule: the card's status "close" or strength "coin flip"), when Sleeper's line for the
week — the snapshot fetched BEFORE the week's first kickoff, priced in the league's scoring (`why.market_points`, the
numbers `market_points` already carries on the lineup rows) — has the other player higher, the call gains one line:
"Sleeper's numbers lean to <name>." and, once at least TALLY_MIN disagreements are graded this season, the record's
tally: "This season, on the N close calls where we have disagreed, Sleeper was right M times, we K." (the record's
season row: `pairs_disagree`, `pairs_ours_right_disagree`; M = N − K). Nothing when the snapshot was fetched after the
first kickoff (a stale or a mid-week number), nothing for a call whose game has started (a call exists only before it),
nothing when either player has no Sleeper number. No number on the call moves; the order of the calls does not either.
Never raises: a lean that cannot be read is no line. docs/METRICS.md § "Sleeper's lean on a close call (sl1.0)".
"""

from __future__ import annotations

import logging

import pandas as pd

from .db import missing_relations, query

log = logging.getLogger(__name__)

TALLY_MIN = 10               # graded disagreements before the tally sentence is said (fewer: the lean alone)
LEAN_MIN = 0.05              # Sleeper's two numbers must differ by at least this (points) to "lean"
SNAPSHOT_SQL = """select max(m.fetched_at) as fetched_at,
                         (select min(g.kickoff_at) from analytics.dim_game g
                          where g.season = %s and g.week = %s and g.season_type = 'REG') as first_kickoff_at
                  from analytics.mart_market_line m where m.season = %s and m.week = %s"""
TALLY_SQL = """select pairs_disagree, pairs_ours_right_disagree from analytics.mart_projection_record
               where league_id = %s and season = %s and scope = 'season' and position = 'ALL' limit 1"""


def snapshot_before_kickoff(season: int, week: int) -> dict | None:
    """{fetched_at, first_kickoff_at} when the week's Sleeper line (the snapshot `market_points` prices) was fetched
    before the week's first kickoff; None otherwise or when it cannot be read."""
    if missing_relations(("mart_market_line", "dim_game")):
        return None
    df = query(SNAPSHOT_SQL, (int(season), int(week), int(season), int(week)))
    if df.empty:
        return None
    f, k = df.iloc[0]["fetched_at"], df.iloc[0]["first_kickoff_at"]
    if f is None or k is None or pd.isna(f) or pd.isna(k) or not pd.Timestamp(f) < pd.Timestamp(k):
        return None
    return {"fetched_at": pd.Timestamp(f).isoformat(), "first_kickoff_at": pd.Timestamp(k).isoformat()}


def season_tally(league_id: str, season: int) -> dict | None:
    """{n, ours, sleeper} — the season's graded close calls where the two disagreed (None: no record for the league,
    or it cannot be read)."""
    if missing_relations(("mart_projection_record",)):
        return None
    df = query(TALLY_SQL, (str(league_id), int(season)))
    if df.empty or pd.isna(df.iloc[0]["pairs_disagree"]):
        return None
    n = int(df.iloc[0]["pairs_disagree"])
    k = int(df.iloc[0]["pairs_ours_right_disagree"]) if not pd.isna(df.iloc[0]["pairs_ours_right_disagree"]) else 0
    return {"n": n, "ours": k, "sleeper": n - k}


def _times(n: int) -> str:
    return f"{n} time{'s' if n != 1 else ''}"


def tally_words(t: dict | None) -> str | None:
    """"This season, on the 13 close calls where we have disagreed, Sleeper was right 9 times, we 4." — None under
    TALLY_MIN graded disagreements (the lean then stands alone)."""
    if not t or t["n"] < TALLY_MIN:
        return None
    return (f"This season, on the {t['n']} close calls where we have disagreed, Sleeper was right {_times(t['sleeper'])}, "
            f"we {t['ours']}.")


def lean_words(name: str, tally: dict | None) -> str:
    tw = tally_words(tally)
    return f"Sleeper's numbers lean to {name}." + (f" {tw}" if tw else "")


def is_close(card: dict) -> bool:
    return card.get("status") == "close" or card.get("strength") == "coin flip"


def leans(cards: list[dict], market: dict[str, float]) -> dict[int, dict]:
    """{card index: {to, name, sleeper}} for the close calls whose other player Sleeper has higher."""
    out = {}
    for i, c in enumerate(cards or []):
        a, b = c.get("gsis_id"), c.get("alt_gsis_id")
        if not is_close(c) or not a or not b or not c.get("alt_name"):
            continue
        ma, mb = market.get(str(a)), market.get(str(b))
        if ma is None or mb is None or mb - ma < LEAN_MIN:
            continue
        out[i] = {"to": b, "name": c["alt_name"], "sleeper": {"player": ma, "alt": mb}}
    return out


def apply(ans: dict, league_id: str, *, house: bool) -> dict:
    """My Week (both paths): `sleeper_lean` on each close card Sleeper reads the other way, and on the action / review
    line that shows that card (`words`). Run after `market_points` is on the lineup rows."""
    try:
        cards = ans.get("cards") or []
        week, season = ans.get("week"), ans.get("season")
        if not cards or week is None or season is None:
            return ans
        market = {str(r["gsis_id"]): r["market_points"] for r in ans.get("lineup_full") or []
                  if r.get("gsis_id") and r.get("market_points") is not None}
        found = leans(cards, market)
        if not found:
            return ans
        snap = snapshot_before_kickoff(int(season), int(week))
        if snap is None:                                   # fetched after the first kickoff, or unreadable: nothing
            return ans
        tally = season_tally(league_id, int(season)) if house else None
        for i, ln in found.items():
            cards[i]["sleeper_lean"] = {**ln, "words": lean_words(ln["name"], tally), "tally": tally,
                                        "snapshot": snap}
        for d in (ans.get("actions") or []) + (ans.get("more_actions") or []) + (ans.get("review") or []):
            hit = next((cards[i]["sleeper_lean"] for i in d.get("cards") or [] if i in found), None)
            if hit:
                d["sleeper_lean"] = hit["words"]
    except Exception:  # noqa: BLE001 - a lean that cannot be read is no line, never a broken My Week
        log.warning("sleeper_lean.apply failed", exc_info=True)
    return ans
