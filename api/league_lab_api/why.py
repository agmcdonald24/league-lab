"""Wave I-A (IA-3): "why this number" and the market line, for the rest-of-season list and the player card.

* **The pieces** (``explain``): a projection is a stat line (one small model per stat: targets, catches, yards,
  touchdowns …) counted the league's way. ``explain`` lists the line's pieces with what each is worth in this league's
  scoring (``weights``: the per-unit value of every scoring key that prices one of the line's stats, a position
  premium included), so "4.1 catches × 0.5 = 2.1 · 52 yards × 0.1 = 5.2 …" adds up to the points. What a per-unit
  price cannot show (a yardage bonus: a projected 100-yard game pays extra in some leagues; each week's rounding to
  the cent) is the remainder, said as its own line — so the list always sums to the number shown.
* **The market** (``market_points``): Sleeper's own projection for the week, priced in the league's scoring, from
  ``analytics.mart_market_line`` (proposed by IA-3, built by the PO: one row per player-week, Sleeper's projected
  stat line from the latest snapshot, league-free, so any league can price it). Until it exists, or for a player it
  has no row for, the market is ``None`` — never an exception, never 0.
* **What the model leans on** (``leans_on``): the top three inputs for the position, About's rows
  (``about.importance``) in About's words.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping

import numpy as np
import pandas as pd
from league_lab import anyleague as A
from league_lab import scoring as S

from .db import missing_relations, query

# the 12 projected stats (ops.projections' proj_* names -> scoring.py's stat names), as anyleague prices them
STAT_LINE = dict(A.STAT_LINE)
LABELS = {"targets": "targets", "receptions": "catches", "receiving_yards": "receiving yards",
          "receiving_tds": "receiving TDs", "carries": "carries", "rushing_yards": "rushing yards",
          "rushing_tds": "rushing TDs", "attempts": "passes", "passing_yards": "passing yards",
          "passing_tds": "passing TDs", "passing_interceptions": "interceptions", "fumbles_lost_total": "fumbles lost"}
SHORT = {"targets": "targets", "receptions": "catches", "receiving_yards": "yards", "receiving_tds": "TDs",
         "carries": "carries", "rushing_yards": "rush yards", "rushing_tds": "rush TDs", "attempts": "passes",
         "passing_yards": "pass yards", "passing_tds": "pass TDs", "passing_interceptions": "INTs",
         "fumbles_lost_total": "fumbles lost"}
# the order a position's line is read in (the chain "targets → catches → yards → TDs → points")
ORDER = {
    "QB": ("attempts", "passing_yards", "passing_tds", "passing_interceptions", "carries", "rushing_yards", "rushing_tds",
           "fumbles_lost_total"),
    "RB": ("carries", "rushing_yards", "rushing_tds", "targets", "receptions", "receiving_yards", "receiving_tds",
           "fumbles_lost_total"),
    "WR": ("targets", "receptions", "receiving_yards", "receiving_tds", "carries", "rushing_yards", "rushing_tds",
           "fumbles_lost_total"),
}
ORDER["TE"] = ORDER["WR"]
# the table's columns per position (per game, projected): the brief's lists; "tds" = rushing + receiving TDs
COLUMNS = {
    "QB": ("attempts", "passing_yards", "passing_tds", "passing_interceptions"),
    "RB": ("carries", "rushing_yards", "targets", "receptions", "receiving_yards", "tds"),
    "WR": ("targets", "receptions", "receiving_yards", "tds"),
    "TE": ("targets", "receptions", "receiving_yards", "tds"),
}
MIN_SHOWN = 0.05          # a piece under this (per game, in units and in points) is left out of the list, not the sum


def weights(scoring: Mapping[str, float], position: str | None, *, season: int | None = None,
            week: int | None = None) -> dict[str, float]:
    """stat -> points per unit in this scoring, for the projected stats: every stat key whose expression is one of
    them (``rec`` -> receptions …), plus a position premium for his position (``bonus_rec_te`` for a TE).
    M6 (Wave I-H): a Sleeper scoring's per-unit values follow the WEEK's pricing mode (``scoring.ev_for_week``: a frozen
    flat week keeps flat pieces on the morning after the flip); no week = the newest build's mode, as before."""
    out = dict.fromkeys(STAT_LINE.values(), 0.0)
    # ---- IC-1 (Wave I-C): the pieces follow the league's ScoringSpec. A Sleeper spec keeps the flat reading below
    # (the same per-unit values as before, bit for bit); any other (MFL's per-position rules) reads the position's
    # rules: rates and premiums, "1/10" yards at a tenth a yard, a touchdown by distance at its expected points.
    spec = S.spec_of(scoring) if scoring is not None else None
    ev = S.ev_for_week(season, week) if week is not None else S.ev_pricing()     # ---- M6: the week's own mode
    if spec is not None and (spec.flat is None or ev):
        r = spec.rules_for(position)
        if r is None:
            return out
        for stat, w in [*r.rates.items(), *r.premiums.items()]:
            if stat in out:
                out[stat] += float(w)
        for stat, sts in r.steps.items():
            if stat in out:
                out[stat] += sum(st.per / st.unit for st in sts if not st.base)
        for fam, bs in r.distance.items():
            if fam in out:
                out[fam] += sum(b[2] * S._band_share(fam, position, b) for b in bs)
        return out
    # ---- /IC-1
    for key, w in (scoring or {}).items():
        try:
            w = float(w or 0)
        except (TypeError, ValueError):
            continue
        if not w:
            continue
        if key in S.SLEEPER_STAT_MAP:
            cols = S._PY_EXPR[key]
            if len(cols) == 1 and cols[0] in out:
                out[cols[0]] += w
        elif key in S.SLEEPER_POSITION_MAP and S.SLEEPER_POSITION_MAP[key][1] == position:
            out[S.SLEEPER_POSITION_MAP[key][0]] += w
    return out


def has_bonuses(scoring: Mapping[str, float]) -> bool:
    sp = getattr(scoring, "spec", None)          # ---- IC-1: an MFL spec's flat yardage bands
    if sp is not None and sp.flat is None:
        return any(s.endswith("_yards") for r in sp.positions.values() for s in r.bands)
    return any(float((scoring or {}).get(k) or 0) for k in S.SLEEPER_BONUS_MAP)


def _f(v) -> float | None:
    if v is None or isinstance(v, str):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def _fmt(v: float) -> str:
    """A piece as people say it: whole yards, one decimal for counts, two for a fraction of a touchdown."""
    a = abs(v)
    if a >= 20:
        return f"{v:.0f}"
    if a >= 1:
        return f"{v:.1f}"
    return f"{v:.2f}"


def line_of(row: Mapping) -> dict[str, float | None]:
    """stat -> value from a row carrying ``proj_targets`` … (``proj_fumbles_lost`` is the per-week mart's name)."""
    out: dict[str, float | None] = {}
    for comp, stat in STAT_LINE.items():
        v = row.get(comp)
        if v is None and comp == "proj_fumbles_lost_total":
            v = row.get("proj_fumbles_lost")
        out[stat] = _f(v)
    return out


def explain(line: Mapping[str, float | None], points: float | None, scoring: Mapping[str, float], position: str | None,
            *, games: int | None = None, total: float | None = None, season: int | None = None,
            week: int | None = None) -> dict | None:
    """The pieces of ``points`` (per game when ``games`` is given: ``line`` and ``points`` are then per game, and
    ``total`` the whole window's points). None without a stat line (a kicker, a defense, no projection).
    ``season`` / ``week`` (M6): the week the line is for, so the pieces are priced in that week's mode."""
    pos = position if position in ORDER else None
    if pos is None or points is None or not any(_f(line.get(s)) for s in STAT_LINE.values()):
        return None
    w = weights(scoring, pos, season=season, week=week)
    pieces, listed = [], 0.0
    for stat in ORDER[pos]:
        v = _f(line.get(stat)) or 0.0
        pts = v * w.get(stat, 0.0)
        if (abs(pts) < MIN_SHOWN) if w.get(stat) else (abs(v) < 0.5):
            continue                    # a piece worth almost nothing here (0.2 carries, 0.4 yards): the remainder holds it
        listed += round(pts, 2)
        pieces.append({"stat": stat, "label": LABELS[stat], "value": round(v, 2), "each": round(w.get(stat, 0.0), 4),
                       "points": round(pts, 2), "words": f"{_fmt(v)} {LABELS[stat]}"
                       + (f" × {w[stat]:g} = {pts:+.1f}" if w.get(stat) else " (no points on their own)")})
    rest = round(float(points) - listed, 2)        # so the list adds up to the number shown, to the cent
    if abs(rest) >= MIN_SHOWN:
        label = ("yardage bonuses (a big game pays extra in this league)" if has_bonuses(scoring) and rest > 0.2
                 else "the small pieces and rounding")
        pieces.append({"stat": "rest", "label": label, "value": None, "each": None, "points": rest,
                       "words": f"{label}: {rest:+.1f}"})
    chain = [f"{_fmt(_f(line.get(s)) or 0.0)} {SHORT[s]}" for s in COLUMNS[pos if pos != "TE" else "WR"]
             if s != "tds" and (_f(line.get(s)) or 0.0) >= MIN_SHOWN]
    tds = (_f(line.get("rushing_tds")) or 0.0) + (_f(line.get("receiving_tds")) or 0.0)
    if pos != "QB" and tds >= 0.01:
        chain.append(f"{tds:.2f} TDs")
    per = "per game" if games else "this week"
    sentence = " → ".join([*chain, f"{float(points):.1f} points {per}"])
    if games and total is not None:
        sentence += f" × {games} game{'s' if games != 1 else ''} = {float(total):.0f}"
    return {"per": "game" if games else "week", "points": round(float(points), 2), "pieces": pieces,
            "sentence": sentence, "games": games, "total": None if total is None else round(float(total), 2)}


def columns(line: Mapping[str, float | None], position: str | None) -> dict[str, float | None]:
    """The table's per-game columns for his position (``COLUMNS``): ``tds`` = rushing + receiving touchdowns."""
    if position not in COLUMNS:
        return {}
    out: dict[str, float | None] = {}
    for c in COLUMNS[position]:
        if c == "tds":
            r, c2 = _f(line.get("rushing_tds")), _f(line.get("receiving_tds"))
            out[c] = None if r is None and c2 is None else round((r or 0.0) + (c2 or 0.0), 2)
        else:
            v = _f(line.get(c))
            out[c] = None if v is None else round(v, 2)
    return out


# ------------------------------------------------------------------------------------------------- the market
MARKET_RELATION = "mart_market_line"
MARKET_SQL = """select * from analytics.mart_market_line where season = %s and week = %s and gsis_id = any(%s)"""
MARKET_WHY = "Sleeper's number for this week is not in yet."
FAR_UNDER, FAR_OVER = 0.70, 1.40


def _market_lines(season: int, week: int, gsis_ids: list[str]) -> pd.DataFrame:
    """The market's stat lines for these players (empty when the mart is not built or has nothing for the week)."""
    if not gsis_ids or missing_relations((MARKET_RELATION,)):
        return pd.DataFrame()
    try:
        return query(MARKET_SQL, (int(season), int(week), list(gsis_ids)))
    except Exception:  # noqa: BLE001 - a mart whose columns moved: no market line, never a broken page
        return pd.DataFrame()


def market_points(season: int | None, week: int | None, gsis_ids: Iterable[str | None], scoring: Mapping[str, float],
                  *, lines: pd.DataFrame | None = None) -> dict[str, float]:
    """gsis_id -> Sleeper's projection for ``week`` in this scoring (``scoring.price_projected``, the pricing of our
    own line, in the week's mode — M4); a player without a row is absent (the caller says None)."""
    ids = sorted({str(g) for g in gsis_ids if g})
    if season is None or week is None or not ids:
        return {}
    df = _market_lines(season, week, ids) if lines is None else lines
    if df is None or df.empty:
        return {}
    df = df[df["gsis_id"].isin(ids)].drop_duplicates("gsis_id", keep="first")
    # ---- M4 (Wave I-G): Sleeper's line is a projected line, so it is priced like ours — ``scoring.price_projected``
    # in the week's mode (``ev_for_week``: the record's label; a yardage bonus at its odds, a long TD at the projected
    # TDs × the share that long, in EV mode; all or nothing in flat mode, the pre-I-G number to the cent)
    if df.empty:
        return {}
    cols = [c for c in df.columns if c not in ("gsis_id", "sleeper_id", "position", "team", "opponent", "fetched_at",
                                               "season", "week", "pts_ppr", "pts_half_ppr", "pts_std")]
    stats = df[cols].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    stats["position"] = df["position"].to_numpy()
    stats = stats.reset_index(drop=True)
    skill = stats["position"].isin(["QB", "RB", "WR", "TE"]).to_numpy()   # a K stays flat, as ours does (kdef)
    pts = np.zeros(len(stats))
    if skill.any():
        pts[skill] = S.price_projected(stats[skill], scoring, ev=S.ev_for_week(season, week))
    if (~skill).any():
        pts[~skill] = S.price_projected(stats[~skill], scoring, ev=False)
    return {str(g): round(float(p), 2) for g, p in zip(df["gsis_id"].to_numpy(), pts, strict=True)}
    # ---- /M4


def market_words(ours: float | None, market: float | None, name: str | None = None) -> str | None:
    """'Sleeper has him at 16.2.' + the gap in words when ours is under 70% or over 140% of it."""
    if market is None:
        return None
    s = f"Sleeper has {name or 'him'} at {market:.1f}."
    if ours is None or market <= 0.5:
        return s
    ratio = ours / market
    if ratio < FAR_UNDER:
        s += " We're well under the market: our number follows his recent usage. Treat it with care."
    elif ratio > FAR_OVER:
        s += " We're well over the market: our number follows his recent usage. Treat it with care."
    return s


def market_block(ours: float | None, market: float | None, week: int | None) -> dict:
    """The card's market line: the number, the ratio, the words, or why there is none."""
    ratio = None if market is None or ours is None or market <= 0.5 else round(ours / market, 2)
    return {"market_points": market, "ours": ours, "ratio": ratio, "week": week,
            "words": market_words(ours, market), "why": None if market is not None else MARKET_WHY,
            "far": ratio is not None and (ratio < FAR_UNDER or ratio > FAR_OVER)}


# ------------------------------------------------------------------------------------------------- leans on
def leans_on(league_id: str | None, league_name: str | None) -> dict[str, dict]:
    """position -> {"features": top three input labels, "words": About's sentence for them, "scored_in"}."""
    from . import about
    try:
        imp = about.importance(league_id, league_name)
    except Exception:  # noqa: BLE001 - no importance mart: nothing to say, never a broken page
        imp = None
    if not imp:
        return {}
    out = {}
    for p in imp.get("positions") or []:
        names = [about._lower_first(f["feature_label"]) for f in p["features"][:3]]
        if not names:
            continue
        words = (f"For {p['position']}s the model leans most on **{names[0]}**."
                 + (" Next: " + " · ".join(names[1:]) + "." if len(names) > 1 else ""))
        out[p["position"]] = {"features": names, "words": words, "scored_in": imp.get("scored_in")}
    return out
