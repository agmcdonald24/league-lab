"""The player card's ratings and its chart of past projections (Wave I-P, IP-4).

``GET /api/player/{gsis}/ratings?league=`` — six to eight numbers that matter at his position, each as his
**percentile among the players at his position this season who clear a stated minimum sample**, on a 0–99 scale, with
the raw value beside it. Built on the Stats frame (``stats.season_rows`` + ``stats.aggregate_window``, the season
window: the same cached aggregate the Stats table reads — no new relation, no new cache). NFL-wide: the same in every
league and scoring (``league`` is accepted and not used). Rules (docs/DESIGN.md § "The player card (Wave I-P, IP-4)"):

* **the population**: his position's players this season with the position's minimum sample (``POPULATION``:
  quarterbacks 50+ dropbacks, running backs 20+ touches, receivers 15+ targets, tight ends 10+ targets);
* **each rating** ranks him among the population players who also clear that column's own minimum (the catalogue's
  ``minimum``, e.g. EPA per target needs 20 targets) and have a value: ``percentile = (players below him + half the
  players tied with him) / (others ranked)``, ``rating = round(99 x percentile)`` (0 = the lowest, 99 = the highest);
  a column where less is better (sacks, interceptions per attempt) ranks the other way and says so;
* **unknown is not a low rating**: a player under the minimum, a column without a value (no charting, no Pro Football
  Reference row) or a population of one gets ``rating: null`` and the reason in ``words``;
* **the overall** is the plain mean of the ratings shown (at least ``OVERALL_MIN`` of them), labelled as exactly that —
  where he ranks in usage and efficiency this season, **not a projection**.

``GET /api/player/{gsis}/projections?league=`` — the projection made before each game this season (the frozen board,
``frozen_source``), for the chart "points against the projection": a house league's own rows
(``mart_player_week_projections``), a reference key's from the NFL-wide ranges (``ops.projection_ranges``) when the key
prices exactly a stored scoring; any other league gets ``weeks: []`` and the reason (its past boards are not kept).
"""

from __future__ import annotations

import math
import re

import numpy as np
import pandas as pd
from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse

from . import refleague
from . import stats as ST
from .db import missing_relations, query

router = APIRouter()

GSIS = re.compile(r"^00-\d{7}$")          # the id pattern freetrade.py and events.py validate with
LEAGUE_MAX = 64
FIRST_SEASON = 2016
OVERALL_MIN = 3                           # the overall is shown with at least three ratings to average
CACHE = {"Cache-Control": "private, max-age=120"}
NO_STORE = {"Cache-Control": "no-store"}

# position -> (sample column, minimum, the words): who is ranked at all
POPULATION: dict[str, tuple[str, int, str]] = {
    "QB": ("dropbacks", 50, "50+ dropbacks"),
    "RB": ("touches", 20, "20+ touches"),
    "WR": ("targets", 15, "15+ targets"),
    "TE": ("targets", 10, "10+ targets"),
}
PLURAL = {"QB": "quarterbacks", "RB": "running backs", "WR": "receivers", "TE": "tight ends"}

# position -> the ratings: (catalogue column, the card's label, less is better). Usage first, then efficiency.
RECEIVING = [("target_share", "Target share", False), ("air_yards_share", "Air-yard share", False),
             ("first_read_target_share", "First-read share", False), ("red_zone_target_share", "Red-zone target share", False),
             ("snap_share", "Snap share", False), ("yards_per_target", "Yards per target", False),
             ("epa_per_target", "EPA per target", False), ("catch_rate", "Catch rate", False)]
RATINGS: dict[str, list[tuple[str, str, bool]]] = {
    "WR": RECEIVING,
    "TE": RECEIVING,
    "RB": [("carry_share", "Carry share", False), ("target_share", "Target share", False), ("snap_share", "Snap share", False),
           ("inside_5_carry_share", "Goal-line carry share", False),
           ("yards_after_contact_per_carry", "Yards after contact per carry", False),
           ("rushing_success_rate", "Rushing success rate", False), ("yards_per_touch", "Yards per touch", False)],
    "QB": [("epa_per_dropback", "EPA per dropback", False), ("passing_success_rate", "Dropback success rate", False),
           ("adjusted_yards_per_attempt", "Adjusted yards per attempt", False),
           ("cpoe", "Completion % over expected", False), ("ngs_pass_intended_air_yards", "Air yards per attempt", False),
           ("carry_share", "Carry share", False), ("sack_rate", "Sacks per dropback", True),
           ("int_rate", "Interceptions per attempt", True)],
}
# the sample words of a column's own minimum ("targets" -> "20+ targets")
SAMPLE_WORDS = {"targets": "targets", "carries": "carries", "dropbacks": "dropbacks", "attempts": "pass attempts",
                "touches": "touches", "pfr_carries": "carries charted by Pro Football Reference",
                "touches_pfr": "touches charted by Pro Football Reference", "dropbacks_pfr": "dropbacks charted by Pro Football Reference"}
LABEL = "Usage and efficiency, 0–99: where he ranks among {plural} this season — not a projection"
HOW = ("Each rating is his percentile among {plural} with {pop} this season ({n} of them): 99 = the highest, 0 = the "
       "lowest, 50 = the middle. A rating needs its own sample too (shown under it); under it, a dash and the reason, "
       "never a low number. The overall is the plain average of the ratings shown. These describe the season so far; "
       "they are not a forecast — the projection is.")
NOT_RATED = "Ratings cover quarterbacks, running backs, receivers and tight ends."
PLAYER_SQL = "select gsis_id, player_name, position from analytics.dim_player where gsis_id = %s"


class Bad(ValueError):
    pass


def _season(season: int | None) -> int:
    cur = refleague._season()
    if season is None:
        return cur
    if not FIRST_SEASON <= int(season) <= cur:
        raise Bad(f"season is {FIRST_SEASON}–{cur}")
    return int(season)


def check_id(gsis: str) -> str:
    if not isinstance(gsis, str) or not GSIS.fullmatch(gsis):
        raise Bad("not a player id (00-0000000)")
    return gsis


def check_league(league: str | None) -> str | None:
    if league is not None and (len(league) > LEAGUE_MAX or not league.strip()):
        raise Bad("league is a league id or a scoring key")
    return league


# --------------------------------------------------------------------------------------------- the arithmetic
def fmt_value(v: float | None, fmt: str | None) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    if fmt == "pct":
        return f"{v * 100:.1f}%"
    if fmt == "dec2":
        return f"{v:+.2f}" if v < 0 else f"{v:.2f}"
    if fmt == "dec1":
        return f"{v:.1f}"
    return f"{v:g}"


def rank_of(values: pd.Series, me: float, lower_better: bool = False) -> tuple[float, int]:
    """(percentile in [0, 1], players ranked) of ``me`` among ``values`` (him included): the players below him plus
    half the players tied with him (himself not counted), over the others. Needs two or more."""
    v = values.dropna().to_numpy(dtype=float)
    n = len(v)
    if n < 2:
        return math.nan, n
    if lower_better:
        v, me = -v, -me
    below = int((v < me).sum())
    tied = int((v == me).sum()) - 1
    return (below + 0.5 * max(0, tied)) / (n - 1), n


def rating_of(p: float) -> int | None:
    return None if p is None or math.isnan(p) else int(math.floor(99 * p + 0.5))


def ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def ratings_from(agg: pd.DataFrame, gsis: str, position: str, cat: dict[str, dict] | None = None) -> dict:
    """The ratings of ``gsis`` at ``position`` from a season aggregate (``stats.aggregate`` rows). Pure (tests)."""
    cat = cat if cat is not None else {c["id"]: c for c in ST.catalogue(0)}
    col, need, pop_words = POPULATION[position]
    plural = PLURAL[position]
    at = agg[agg["position"] == position] if not agg.empty else agg
    sample = pd.to_numeric(at[col], errors="coerce") if col in at else pd.Series(dtype=float)
    pop = at[sample >= need] if len(at) else at
    mine = agg[agg["gsis_id"] == gsis] if not agg.empty else agg
    me = mine.iloc[0] if len(mine) else None
    his_n = float(pd.to_numeric(pd.Series([me[col]]), errors="coerce").iloc[0]) if me is not None and col in mine else math.nan
    qualified = me is not None and not math.isnan(his_n) and his_n >= need
    out = []
    for cid, label, lower in RATINGS[position]:
        c = cat.get(cid, {})
        raw = float(me[cid]) if me is not None and cid in mine and pd.notna(me[cid]) else None
        item = {"key": cid, "label": label, "value": raw, "display": fmt_value(raw, c.get("format")),
                "percentile": None, "rating": None, "n": None, "lower_is_better": lower,
                "definition": c.get("definition"), "source": c.get("source")}
        mn = c.get("minimum")
        own = f"{mn['n']}+ {SAMPLE_WORDS.get(mn['field'], mn['field'].replace('_', ' '))}" if mn else None
        item["minimum"] = own
        if me is None:
            item["words"] = "No games this season yet."
        elif not qualified:
            have = "no" if math.isnan(his_n) else f"{int(his_n)}"
            item["words"] = f"Not rated: {have} {pop_words.split(' ', 1)[1]} so far; ratings start at {pop_words}."
        elif raw is None:
            item["words"] = f"No value for him: {c.get('reason') or 'not available this season'}."
        elif mn and (mn["field"] not in mine or pd.isna(me[mn["field"]]) or float(me[mn["field"]]) < mn["n"]):
            have = me[mn["field"]] if mn["field"] in mine and pd.notna(me[mn["field"]]) else 0
            item["words"] = f"Not rated: {int(have)} so far; this rating needs {own}."
        else:
            ok = pop[cid].notna()
            if mn and mn["field"] in pop:
                ok &= pd.to_numeric(pop[mn["field"]], errors="coerce") >= mn["n"]
            p, n = rank_of(pd.to_numeric(pop.loc[ok, cid], errors="coerce"), raw, lower)
            item["n"] = n
            if math.isnan(p):
                item["words"] = f"Not rated: too few {plural} with a value to rank ({n})."
            else:
                item["percentile"] = round(p * 100, 1)
                item["rating"] = rating_of(p)
                v = pd.to_numeric(pop.loc[ok, cid], errors="coerce").to_numpy(dtype=float)
                place = int(((v < raw) if lower else (v > raw)).sum()) + 1
                item["words"] = (f"{ordinal(place)} of {n} {plural}" + (" (fewer is better)" if lower else "")
                                 + (f" · {own}" if own else ""))
        out.append(item)
    shown = [r["rating"] for r in out if r["rating"] is not None]
    overall = int(round(sum(shown) / len(shown))) if len(shown) >= OVERALL_MIN else None
    return {"position": position, "n_ranked": int(len(pop)), "population": pop_words, "qualified": bool(qualified),
            "ratings": out, "overall": overall, "overall_n": len(shown),
            "overall_words": (f"The plain average of his {len(shown)} ratings shown." if overall is not None
                              else f"Shown with {OVERALL_MIN} or more ratings; he has {len(shown)}."),
            "label": LABEL.format(plural=plural),
            "how": HOW.format(plural=plural, pop=pop_words, n=int(len(pop)))}


def season_aggregate(season: int) -> tuple[pd.DataFrame, int | None, list[dict]]:
    """The season window's aggregate (the Stats table's cached one: same key), the last week in it, the catalogue."""
    rows = ST.season_rows(season, "REG")
    frame, desc = ST.window_rows(rows, "season", "games", None)
    cat = ST.catalogue(season, rows)
    mine = frame[frame["position"].isin(ST.SKILL)] if not frame.empty else frame
    if mine.empty:
        return pd.DataFrame(columns=["gsis_id", "position"]), None, cat
    agg = ST.aggregate_window(mine, (season, "REG", "season", "games", None, id(rows), len(mine)))
    return agg, desc.get("through_week"), cat


def player_ratings(gsis: str, season: int | None = None) -> dict:
    gsis = check_id(gsis)
    season = _season(season)
    who = query(PLAYER_SQL, (gsis,))
    if who.empty:
        raise LookupError(f"No player with id {gsis}.")
    pos = str(who.iloc[0]["position"] or "")
    base = {"gsis_id": gsis, "player_name": who.iloc[0]["player_name"], "season": season, "position": pos}
    if pos not in POPULATION:
        return {**base, "through_week": None, "n_ranked": 0, "ratings": [], "overall": None, "words": NOT_RATED}
    agg, through, cat = season_aggregate(season)
    out = ratings_from(agg, gsis, pos, {c["id"]: c for c in cat})
    return {**base, "through_week": through, **out,
            "words": None if out["qualified"] else f"Rated from {out['population']} this season."}


# ------------------------------------------------------------------------------ the projection made before each game
HOUSE_SQL = """select week, proj_points, p10, p25, p75, p90, frozen_source
               from analytics.mart_player_week_projections
               where league_id = %s and gsis_id = %s and season = %s and week <= %s
               order by week"""
REF_SQL = """select distinct on (week) week, proj_points, p10, p25, p75, p90, frozen_source
             from ops.projection_ranges
             where scoring_name = %s and season = %s and week <= %s and gsis_id = %s
             order by week, (frozen_source is not null) desc, fitted_at desc nulls last"""
KD_SQL = """select distinct on (week) week, proj_points, p10, null::numeric as p25, null::numeric as p75, p90, frozen_source
            from ops.kd_ranges
            where scoring_name = %s and season = %s and week <= %s and unit_id = %s and position = 'K'
            order by week, (frozen_source is not null) desc, fitted_at desc nulls last"""   # a kicker's board (F1)
SOURCE_WORDS = {
    "kickoff": "the projection shown before kickoff",
    "refit": "rebuilt after that week kicked off (before projections were frozen at kickoff), not the one shown then",
    None: "this week's live projection",
}
NOT_KEPT = ("Past weeks' projections are kept for the house leagues and the default scorings (Half PPR, PPR, "
            "Standard); for this scoring the chart shows his points alone.")


def _ref_scoring(key: str) -> str | None:
    """The stored scoring a reference key prices exactly (its base without a change, no TE premium, 4-point passing
    TDs), else None."""
    try:
        sh = refleague.shape(key)
    except Exception:  # noqa: BLE001 - not a reference key
        return None
    seed, _label, change = refleague.SCORINGS[sh.base]
    return seed if not change and not sh.tep and not sh.p6 else None


UNIT_NONE = "No projection for a defense in this league (its lineup has no DEF spot): the chart shows its points alone."


def unit_projections(code: str, league: str) -> dict:
    """A team defense (fix round): the projection made before each week and its points by week (``games``, the game
    log's shape: the chart's bars), both in the league's scoring (league_lab_api/unitcard.py)."""
    from . import research
    from . import unitcard as U
    ctx = research.context(league)
    week = ctx.week or 18
    weeks = U.past_projections(code, league, ctx, week)
    srcs = sorted({w["source"] or "live" for w in weeks})
    return {"gsis_id": code, "season": ctx.season, "through_week": int(week), "weeks": weeks,
            "why": None if weeks else (UNIT_NONE if ctx.house else NOT_KEPT.replace("his points", "its points")),
            "games": U.week_points(code, ctx.season, ctx.scoring),
            "notes": [f"{_span([w['week'] for w in weeks if (w['source'] or 'live') == s])}: "
                      f"{SOURCE_WORDS[None if s == 'live' else s]}." for s in srcs]}


def player_projections(gsis: str, league: str, season: int | None = None, through: int | None = None) -> dict:
    from .unitcard import unit_code
    check_league(league)
    if unit_code(gsis) is not None:                                       # ---- fix round: a team defense
        return unit_projections(unit_code(gsis), league)
    gsis = check_id(gsis)
    season = _season(season)
    from .applib import cards  # the card's own week (lazy: cards imports the world)
    week = through if through is not None else (cards.decision_week(season) or 18)
    rows = pd.DataFrame()
    why = None
    if refleague.is_reference(league):
        seed = _ref_scoring(league)
        if seed is None:
            why = NOT_KEPT
        else:
            try:
                rows = query(REF_SQL, (seed, season, int(week), gsis))
                if rows.empty:                                    # a kicker's weeks are on the K / DEF board
                    rows = query(KD_SQL, (seed, season, int(week), gsis))
            except Exception:  # noqa: BLE001 - no NFL-wide ranges on this copy: the bars alone, never a 500
                rows, why = pd.DataFrame(), NOT_KEPT
    elif re.fullmatch(r"\d{6,24}", league or "") and not missing_relations(("mart_player_week_projections",)):
        rows = query(HOUSE_SQL, (league, gsis, season, int(week)))
        if rows.empty:
            why = NOT_KEPT
    else:
        why = NOT_KEPT
    weeks = []
    for r in rows.itertuples(index=False):
        src = r.frozen_source if isinstance(r.frozen_source, str) else None
        weeks.append({"week": int(r.week), "proj_points": _num(r.proj_points), "p10": _num(r.p10), "p25": _num(r.p25),
                      "p75": _num(r.p75), "p90": _num(r.p90), "source": src})
    srcs = sorted({w["source"] or "live" for w in weeks})
    return {"gsis_id": gsis, "season": season, "through_week": int(week), "weeks": weeks, "why": why,
            "notes": [f"{_span([w['week'] for w in weeks if (w['source'] or 'live') == s])}: {SOURCE_WORDS[None if s == 'live' else s]}."
                      for s in srcs]}


def _span(ws: list[int]) -> str:
    if not ws:
        return ""
    ws = sorted(ws)
    if len(ws) == 1:
        return f"Week {ws[0]}"
    if ws == list(range(ws[0], ws[-1] + 1)):
        return f"Weeks {ws[0]}–{ws[-1]}"
    return "Weeks " + ", ".join(str(w) for w in ws)


def _num(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else round(f, 2)


# ------------------------------------------------------------------------------------------------------- routes
def _clean(v):
    if isinstance(v, dict):
        return {k: _clean(x) for k, x in v.items()}
    if isinstance(v, list | tuple):
        return [_clean(x) for x in v]
    if isinstance(v, float):
        return None if math.isnan(v) or math.isinf(v) else v
    if isinstance(v, np.generic):
        return _clean(v.item())
    return v


def _answer(fn, *args) -> JSONResponse:
    try:
        out = fn(*args)
    except Bad as exc:
        return JSONResponse({"error": str(exc), "detail": str(exc)}, status_code=400, headers=NO_STORE)
    except LookupError as exc:
        return JSONResponse({"error": str(exc), "detail": str(exc)}, status_code=404, headers=NO_STORE)
    return JSONResponse(_clean(out), headers=CACHE)


@router.get("/api/player/{gsis}/ratings")
def ratings_route(gsis: str, response: Response, league: str | None = None, season: int | None = None):
    """Sync: FastAPI runs it in the threadpool (the season frame's first read is ~0.35 s, then cached 10 minutes)."""
    try:
        check_league(league)
    except Bad as exc:
        return JSONResponse({"error": str(exc), "detail": str(exc)}, status_code=400, headers=NO_STORE)
    return _answer(player_ratings, gsis, season)


@router.get("/api/player/{gsis}/projections")
def projections_route(gsis: str, league: str, response: Response, season: int | None = None):
    return _answer(player_projections, gsis, league, season)
