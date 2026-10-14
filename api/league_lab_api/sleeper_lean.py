"""JB-2 (Wave J-B): a close call on My Week says when Sleeper's numbers lean the other way.

On a close call (the screen's own rule: the card's status "close" or strength "coin flip"), when Sleeper's line for the
week — priced in the league's scoring (`why.market_points`, the `market_points` the lineup rows already carry) from a
snapshot fetched BEFORE BOTH players' own kickoffs (sl1.1) — has the other player higher, the call gains one line:
"Sleeper's numbers lean to <name>." and, once at least TALLY_MIN disagreements are graded this season, the record's
tally: "This season, on the N close calls where we have disagreed, Sleeper was right M times, we K." (the record's
season row: N = `pairs_disagree`, K = `pairs_ours_right_disagree`, M = `pairs_sleeper_right` − `pairs_both_right`, the
count About says). Nothing when the snapshot was fetched after either player's kickoff, nothing for a call whose game
has started, nothing when either player has no Sleeper number. No number on the call moves; nor does their order.
Never raises: a lean that cannot be read is no line. docs/METRICS.md § "Sleeper's lean on a close call (sl1.1)".
"""

from __future__ import annotations

import logging

import pandas as pd

from .db import missing_relations, query

log = logging.getLogger(__name__)

TALLY_MIN = 10               # graded disagreements before the tally sentence is said (fewer: the lean alone)
LEAN_MIN = 0.05              # Sleeper's two numbers must differ by at least this (points) to "lean"
# ---- JB-2b (sl1.1): the snapshot that prices each player, and his own game's kickoff that week
SNAPSHOT_SQL = """select gsis_id, team, fetched_at from analytics.mart_market_line
                  where season = %s and week = %s and gsis_id = any(%s)"""
GAMES_SQL = """select home_team, away_team, kickoff_at from analytics.dim_game
               where season = %s and week = %s and season_type = 'REG'"""
TALLY_SQL = """select pairs_disagree, pairs_ours_right_disagree, pairs_sleeper_right, pairs_both_right
               from analytics.mart_projection_record
               where league_id = %s and season = %s and scope = 'season' and position = 'ALL' limit 1"""


def snapshots(season: int, week: int, gsis_ids: list[str]) -> dict[str, dict]:
    """{gsis: {fetched_at, kickoff_at}} — when the Sleeper line that prices him (`mart_market_line`, the week's newest
    snapshot) was fetched, and when his own game kicks off that week (`dim_game`, his line's team; one spelling of a
    team code). A player with no line or no game is absent. Raises when it cannot be read (the caller says nothing)."""
    from .provenance import _team
    ids = sorted({str(g) for g in gsis_ids if g})
    if not ids or missing_relations(("mart_market_line", "dim_game")):
        return {}
    lines = query(SNAPSHOT_SQL, (int(season), int(week), ids))
    games = query(GAMES_SQL, (int(season), int(week)))
    kick: dict[str, pd.Timestamp] = {}
    for g in games.itertuples():
        for t in (g.home_team, g.away_team):
            if isinstance(t, str) and g.kickoff_at is not None and not pd.isna(g.kickoff_at):
                kick[_team(t)] = pd.Timestamp(g.kickoff_at)
    out = {}
    for r in lines.itertuples():
        k = kick.get(_team(r.team))
        if k is None or r.fetched_at is None or pd.isna(r.fetched_at):
            continue
        out[str(r.gsis_id)] = {"fetched_at": pd.Timestamp(r.fetched_at), "kickoff_at": k}
    return out


def pair_ok(snap: dict[str, dict], a: str, b: str, now: pd.Timestamp) -> dict | None:
    """sl1.1: the two players' lines were fetched before BOTH players' own kickoffs, and neither game has started at
    ``now``. {fetched_at, kickoff_at (the earlier of the two)} or None."""
    sa, sb = snap.get(str(a)), snap.get(str(b))
    if sa is None or sb is None:
        return None
    first = min(sa["kickoff_at"], sb["kickoff_at"])
    fetched = max(sa["fetched_at"], sb["fetched_at"])
    if not fetched < first or not now < first:
        return None
    return {"fetched_at": fetched.isoformat(), "kickoff_at": first.isoformat()}


def season_tally(league_id: str, season: int) -> dict | None:
    """{n, ours, sleeper} — the season's graded close calls where the two disagreed (None: no record for the league,
    or it cannot be read)."""
    if missing_relations(("mart_projection_record",)):
        return None
    df = query(TALLY_SQL, (str(league_id), int(season)))
    if df.empty or pd.isna(df.iloc[0]["pairs_disagree"]):
        return None
    r = df.iloc[0]

    def i(c) -> int:
        return 0 if pd.isna(r[c]) else int(r[c])
    # Sleeper right where the two disagreed = Sleeper's right calls minus the ones both got right (About's own line,
    # `record.ts`); a disagreement where Sleeper had the two level is neither's (13 = 4 + 8 + 1 in the live week 5)
    return {"n": i("pairs_disagree"), "ours": i("pairs_ours_right_disagree"),
            "sleeper": i("pairs_sleeper_right") - i("pairs_both_right")}


def _times(n: int) -> str:
    return f"{n} time{'s' if n != 1 else ''}"


def tally_words(t: dict | None) -> str | None:
    """"This season, on the 13 close calls where we have disagreed, Sleeper was right 8 times, we 4." — None under
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
        # ---- JB-2b (sl1.1): each pair on its own — the line fetched before BOTH players' kickoffs (was: before the
        # week's first kickoff, which hid every lean from Thursday night to Sunday, when most calls are made)
        from league_lab import clock
        now = pd.Timestamp(clock.now())
        now = now.tz_localize("UTC") if now.tzinfo is None else now.tz_convert("UTC")
        snap = snapshots(int(season), int(week), [g for i, ln in found.items() for g in (cards[i]["gsis_id"], ln["to"])])
        found = {i: {**ln, "snapshot": ok} for i, ln in found.items()
                 if (ok := pair_ok(snap, cards[i]["gsis_id"], ln["to"], now)) is not None}
        if not found:                                      # fetched after a kickoff, a game started, or unreadable
            return ans
        tally = season_tally(league_id, int(season)) if house else None
        for i, ln in found.items():
            cards[i]["sleeper_lean"] = {**ln, "words": lean_words(ln["name"], tally), "tally": tally}
        for d in (ans.get("actions") or []) + (ans.get("more_actions") or []) + (ans.get("review") or []):
            hit = next((cards[i]["sleeper_lean"] for i in d.get("cards") or [] if i in found), None)
            if hit:
                d["sleeper_lean"] = hit["words"]
    except Exception:  # noqa: BLE001 - a lean that cannot be read is no line, never a broken My Week
        log.warning("sleeper_lean.apply failed", exc_info=True)
    return ans
