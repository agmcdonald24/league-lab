"""IZ-1 (Wave I-Z): `/api/record`'s `history` block — us against Sleeper on the weeks Sleeper still serves (hh1.0,
docs/METRICS.md § "Us against Sleeper on the weeks Sleeper still serves"), read from `ops.sleeper_h2h` (`league-lab
h2h`, nightly).

Three honest states, never an empty record:

* the table cannot be read (not there yet — the hours between a deploy and the refresh that brings it — or a read that
  fails): ``{"available": false, "status": "unavailable", "sentence": "… not available right now."}``;
* the table is there and holds no row of the league: ``{"available": false, "status": "none"}`` with no sentence
  (nothing until the table has rows);
* rows: ``available: true``, the positions with their words, the start / sit calls, by season, the blend measured
  (never shipped), one sentence built from the rows and the caveat beside it.

Served on the house leagues' record (and so on ``ref:*``, which is the reference house league's): a league we do not
score gets no block (the sentence does not name a scoring). ``block`` falls back to the headline league's rows when a
league has none of its own, and says so (``scored_in``).
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

from .db import query

POSITIONS = ("QB", "RB", "WR", "TE")
UNAVAILABLE = "The comparison with Sleeper on past weeks is not available right now."
CAVEAT = ("Sleeper's numbers for past weeks are the ones its site serves now, written after the games, so this favours "
          "Sleeper; the record above, from week 5 of 2026, compares numbers saved before kickoff.")
OURS_WORDS = {
    "live_walk_forward": "our model as it runs today, re-run on each past season with only the seasons before it",
    "stored_walk_forward": "our model re-run on each past season, without the live board's latest adjustments",
    "kickoff_board": "our projections as published before kickoff",
}

EXISTS_SQL = "select to_regclass('ops.sleeper_h2h') is not null as present"
ROWS_SQL = """
select league_id, league_name, headline, kind, position, season, measure, n_weeks, n_rows, ours, sleeper, blend, diff,
       diff_lo, diff_hi, verdict, w, seasons, ours_source, ours_version, rule, built_at
from ops.sleeper_h2h
"""


def _n(x: Any) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) else v


def _i(x: Any) -> int | None:
    v = _n(x)
    return None if v is None else int(v)


def _s(x: Any) -> str | None:
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else str(x)


def _read() -> pd.DataFrame | None:
    """The grade's rows; None when they cannot be read (absent table, failed read)."""
    try:
        present = query(EXISTS_SQL)
        if present.empty or not bool(present.iloc[0]["present"]):
            return None
        return query(ROWS_SQL)
    except Exception:  # noqa: BLE001 - "cannot read" is said as such, never as an empty record
        return None


def _measure(r: pd.Series | None) -> dict | None:
    if r is None:
        return None
    return {"ours": _n(r["ours"]), "sleeper": _n(r["sleeper"]), "diff": _n(r["diff"]), "diff_lo": _n(r["diff_lo"]),
            "diff_hi": _n(r["diff_hi"]), "word": _s(r["verdict"]), "weeks": _i(r["n_weeks"]), "n": _i(r["n_rows"])}


def _pick(g: pd.DataFrame, kind: str, measure: str) -> pd.Series | None:
    x = g[(g["kind"] == kind) & (g["measure"] == measure)]
    return x.iloc[0] if len(x) else None


def _and(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def sentence(by_position: list[dict], weeks: int | None, seasons: str | None, close: dict | None) -> str | None:
    """About's one sentence, from the rows only (never a hard-coded number). None when no position has a word."""
    groups: dict[str, list[str]] = {}
    for p in by_position:
        if p.get("word"):
            groups.setdefault(p["word"], []).append(p["position"])
    if not groups or not weeks:
        return None
    parts = [f"{w} at {_and(groups[w])}" for w in ("ahead", "level", "behind") if w in groups]
    out = (f"Against Sleeper's free projections on {weeks} past weeks ({seasons}), on the weekly miss and the order of "
           f"players: {'; '.join(parts)}.")
    if close and close.get("n") and close.get("share") is not None:
        out += (f" On the close start / sit calls the two disagreed on, ours was right {round(100 * close['share'])}% of "
                f"{close['n']:,} times.")
    return out


def block(df: pd.DataFrame, league_id: str | None) -> dict:
    """The `history` block of one league (or the headline league's when ``league_id`` has no rows of its own)."""
    own = df[df["league_id"].astype(str) == str(league_id)] if league_id is not None else df.iloc[0:0]
    rows = own if len(own) else df[df["headline"].fillna(False).astype(bool)]
    if rows.empty:
        return {"available": False, "status": "none", "sentence": None, "caveat": None}
    pooled = rows[rows["season"].isna()]
    by_position, close_n, close_right = [], 0, 0.0
    weeks = 0
    for pos in POSITIONS:
        g = pooled[pooled["position"] == pos]
        if g.empty:
            continue
        v, e, o, h = (_pick(g, "position", m) for m in ("verdict", "error", "order", "hit_rate"))
        cc, sp_ = _pick(g, "close_calls", "share"), _pick(g, "startable_pairs", "share")
        bl = _pick(g, "blend", "verdict")
        weeks = max(weeks, _i(e["n_weeks"]) or 0) if e is not None else weeks
        c = _measure(cc)
        if c is not None:
            c["share"] = c.pop("ours")
            close_n += c["n"] or 0
            close_right += (c["share"] or 0) * (c["n"] or 0)
        by_position.append({"position": pos, "word": _s(v["verdict"]) if v is not None else None,
                            "error": _measure(e), "order": _measure(o), "hit_rate": _measure(h), "close_calls": c,
                            "startable_pairs": _measure(sp_), "blend": _s(bl["verdict"]) if bl is not None else None})
    seas = rows[rows["season"].notna() & (rows["kind"] == "position") & (rows["measure"] == "verdict")]
    by_season = [{"season": _i(r.season), "position": r.position, "word": _s(r.verdict)} for r in seas.itertuples()]
    blend = [{"position": r.position, "season": _i(r.season), "w": _n(r.w), "fitted_on": _s(r.seasons),
              "error": {"ours": _n(r.ours), "sleeper": _n(r.sleeper), "blend": _n(r.blend)}}
             for r in rows[(rows["kind"] == "blend") & (rows["measure"] == "error")].itertuples()]
    first = rows.iloc[0]
    hist = pooled[(pooled["kind"] == "position") & (pooled["measure"] == "error")]
    seasons = _s(hist["seasons"].iloc[0]) if len(hist) else None
    close = {"n": close_n, "share": close_right / close_n} if close_n else None
    src = _s(first["ours_source"])
    return {"available": True, "status": "graded", "rule": _s(first["rule"]), "league_id": _s(first["league_id"]),
            "scored_in": None if len(own) else _s(first["league_name"]), "league_name": _s(first["league_name"]),
            "ours": OURS_WORDS.get(src or "", None), "ours_source": src, "ours_version": _s(first["ours_version"]),
            "weeks": weeks or None, "seasons": seasons, "by_position": by_position, "close_calls": close,
            "by_season": by_season, "blend": blend, "built_at": first["built_at"],
            "sentence": sentence(by_position, weeks, seasons, close), "caveat": caveat(src, seasons)}


def caveat(source: str | None, seasons: str | None) -> str:
    """What our side is, and the history's caveat, in plain words (beside the sentence, every time)."""
    ours = OURS_WORDS.get(source or "")
    if ours is None:
        return CAVEAT
    current = [s for s in (seasons or "").split(", ") if s and s not in ("2023", "2024", "2025")]
    tail = f" ({', '.join(current)}: {OURS_WORDS['kickoff_board']})" if current and source != "kickoff_board" else ""
    return f"Ours: {ours}{tail}. {CAVEAT}"


def history(league_id: str | None) -> dict:
    """`/api/record`'s `history`: never raises (the record must answer without it)."""
    df = _read()
    if df is None:
        return {"available": False, "status": "unavailable", "sentence": UNAVAILABLE, "caveat": None}
    try:
        if df.empty:
            return {"available": False, "status": "none", "sentence": None, "caveat": None}
        return block(df, league_id)
    except Exception:  # noqa: BLE001 - a malformed table (an older build): "not available", never empty, never a 500
        return {"available": False, "status": "unavailable", "sentence": UNAVAILABLE, "caveat": None}
