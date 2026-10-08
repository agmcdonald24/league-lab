"""Wave H (H1): `GET /api/about?league=` — "About the numbers": the model explanation the About screen shows, what the
projection leans on most (`mart_projection_importance`) and its grades (`mart_projection_drift`: this season's played
weeks next to the backtest; `mart_projection_backtest`: each past season), in the words of the Streamlit Rankings page
(`app/pages/4_Rankings.py`, "The model" expander and "How the model is doing this season": quoted, marked).

Importance and grades are measured once per house league's scoring by the nightly (the model is NFL-wide; the points
are a league's). A house league reads its own rows; any other league reads the house league whose scoring is closest
(`research.expected_ref`: the same interception / fumble / 2-point weights first) and says which one (`scored_in`).
"""

from __future__ import annotations

import time

import pandas as pd
from league_lab import memo as budget

from . import research
from .db import query
from .myweek import _num, _str, known_league
from .settings import APP_NAME

POSITIONS = ("QB", "RB", "WR", "TE")

# quoted from app/pages/4_Rankings.py ("The model" expander), cut into the About screen's cards (web/src/lib/about.ts)
MODEL_ANSWER = (f"**{APP_NAME} trains its own model**: these are not Sleeper's or ESPN's projections. It predicts each player's "
                "stat line from what was known before kickoff, then your league's scoring turns the line into points.")


def sections(league_name: str) -> list[dict]:
    return [
        {"key": "learned", "title": "What it learned from",
         "text": "The regular-season games QBs, RBs, WRs and TEs played from 2016 to last season (over 50,000 of them), each with "
                 "only what was known before kickoff: his season and last-3-game numbers, his share of his team's targets, "
                 "carries and snaps, how often he was the quarterback's first look, last season, the opponent's defense against "
                 "his position, the Vegas line, home or away, the injury report, who starts at quarterback and whether his "
                 "team's top target is out."},
        {"key": "predicts", "title": "What it predicts",
         "text": "The stat line, not points. For each position there is one small model per stat: targets, catches, receiving "
                 "yards and touchdowns, carries, rushing yards and touchdowns, and for quarterbacks pass attempts, passing yards, "
                 "touchdowns and interceptions. Each is a gradient-boosted model: a few hundred small decision trees, each one "
                 f"fixing the mistakes of the ones before it. Then **{league_name}**'s scoring turns the stat line into points, "
                 "which is why the same player projects differently in each league."},
        {"key": "ranges", "title": "The ranges",
         # IF-4: the dictionary's words (was "Most weeks", "floor", "ceiling")
         "text": "The **typical range** (the middle 50% of outcomes) and the **low-end** and **high-end outcomes** come from "
                 "separate models that learned how far off the projection usually is for a player like this one, then widened "
                 "or narrowed until they held on seasons they had never seen: half his weeks land in the typical range (a "
                 "quarter below it, a quarter above), 8 in 10 between the low-end outcome (1 week in 10 lands below it) and "
                 "the high-end outcome (1 week in 10 lands above it)."},
        {"key": "graded", "title": "How it was graded",
         "text": "Trained on the past, graded on seasons it never saw: each season from 2021 to 2025 was predicted by a model "
                 "trained only on the seasons before it. The grade is the **order score** (Spearman: how well the projected "
                 "order of players matched the order they really finished in, 1 = perfect, 0 = no better than random) and the "
                 "**average miss** in points."},
        {"key": "unknown", "title": "What it does not know",
         "text": "Injury news after the morning refresh, the weather, how the game actually goes (a blowout sends starters to "
                 "the bench early), and coaching decisions made during the week. Check the news before kickoff."},
    ]


# ---- IA-3 (Wave I-A): the rankings' honesty line ("How to read the rankings"): the ROS screen's top paragraph
# (/api/ros `howto_rankings`) and About's (`rankings_howto`). Andrew's examples are its test: Dak #1 and Kyler #3 in a
# superflex 6-point league, Brissett top-8 in the dynasty — understandable from it, not defended by it.
RANKINGS_HOWTO = (
    "**How to read the rankings.** We project each player from his work, not his name: his targets, carries and "
    "passes, his role, how fast his offense plays and the defenses left on his schedule. A star whose targets are "
    "down reads lower than his name; a quarterback who starts and throws 35 times per game counts like any starter "
    "while he starts. In a superflex league, or one that pays 6 points for a passing touchdown, quarterbacks lead the"
    " list by design, and among them volume beats reputation. Sleeper's own number is there to compare: where ours is"
    " far from it, open his card and read why before you trade on it."
)
# ---- end IA-3


IMPORTANCE_SQL = """select i.position, i.feature_label, i.importance, i.importance_rank, i.baseline_mae, i.eval_season,
                           i.fit_seasons, i.model_version, i.league_id
                    from analytics.mart_projection_importance as i
                    where i.model = 'component' and i.component = 'total' and i.importance_rank <= 10
                      and i.league_id = %s
                      and i.model_version = (select max(model_version) from analytics.mart_projection_importance
                                             where model = 'component' and league_id = %s)
                    order by i.position, i.importance_rank"""
IMPORTANCE_LEAGUES_SQL = "select distinct league_id from analytics.mart_projection_importance where model = 'component'"
DRIFT_SQL = """select season, position, weeks_scored, first_week, last_week, week_in_progress, spearman, backtest_spearman,
                      mae, backtest_mae, coverage_80, backtest_coverage_80, backtest_seasons, model_version
               from analytics.mart_projection_drift where league_id = %s
                 and season = (select max(season) from analytics.mart_projection_drift where league_id = %s)"""
BACKTEST_SQL = """select season, position, train_seasons, weeks, spearman, mae, coverage_80, model_version
                  from analytics.mart_projection_backtest
                  where league_id = %s and is_current and scorer = 'v2_points' and position = any(%s)
                  order by position, season"""
NAMES_SQL = "select league_id, league_name from analytics.dim_league_season where is_current_season"

# quoted from app/pages/4_Rankings.py ("What it leans on most": the caption and the per-position sentence)
HOW_MEASURED = ("How we measured it: a copy of the model trained on {fit} projected the {season} season, which it had never "
                "seen. Then we scrambled one input at a time (shuffled it between players, so it tells the model nothing) and "
                "counted how much bigger the average miss got, in points per player per game ({scored_in} scoring). Bigger = "
                "the model leans on it more. Inputs that move together (targets and catches, a season and its last 3 games) "
                "share the credit, so each looks a little smaller than it is.")
IMPORTANCE_UNIT = "Points of error added per player per game when that input is scrambled."
GRADES_HOWTO = (
    "**Order score** (Spearman): how well the projected order of players matched the order they really finished in, 1 = "
    "perfect, 0 = no better than random. Around 0.5–0.6 is good for one week of fantasy football.",
    "**Average miss** (MAE): how many points the projection missed by, on average, per player per game.",
    "**Inside the range** (coverage): how often the real score landed between the floor and the ceiling. The aim is 8 "
    "weeks in 10.",
    "**This season** scores the weeks already played on the board as it stood before kickoff; **backtest** is the same score "
    "on 2021 to 2025, each season predicted by a model trained only on the seasons before it. A few weeks are a small "
    "sample: one odd Sunday moves them a lot.",
)

TTL_S = 600
_cache = budget.region("about", ttl=TTL_S)        # INF-2 (Wave I-J): in the memory budget (was cleared past 100)


def _lower_first(s: str) -> str:
    return s[0].lower() + s[1:] if s else s


def _measured_in(ctx: research.Ctx) -> tuple[str | None, str | None]:
    """(house league id whose rows answer, its name): the league itself, else the closest house scoring."""
    names = {str(r.league_id): str(r.league_name) for r in query(NAMES_SQL, ()).itertuples()}
    if ctx.house:
        return ctx.league_id, names.get(ctx.league_id, ctx.league_name)
    ref, _ = research.expected_ref(ctx)
    return (ref, names.get(ref)) if ref else (None, None)


def importance(league_id: str | None, scored_in: str | None) -> dict | None:
    """Top 10 inputs per position, the house league's own rows (or the first league measured when it has none)."""
    measured = [str(r.league_id) for r in query(IMPORTANCE_LEAGUES_SQL, ()).itertuples()]
    if not measured:
        return None
    lid = league_id if league_id in measured else sorted(measured)[0]
    if lid != league_id:
        scored_in = query("select league_name from analytics.dim_league_season where league_id = %s order by season desc limit 1",
                          (lid,))["league_name"].iloc[0]
    imp = query(IMPORTANCE_SQL, (lid, lid))
    if imp.empty:
        return None
    imp["importance"] = pd.to_numeric(imp["importance"], errors="coerce")
    r0 = imp.iloc[0]
    fit = str(r0["fit_seasons"]).replace("-", " to ") if isinstance(r0["fit_seasons"], str) else "the seasons before"
    positions = []
    for pos in POSITIONS:
        t = imp[imp["position"] == pos]
        if t.empty:
            continue
        names = [_lower_first(str(n)) for n in t["feature_label"]]
        base = _num(t["baseline_mae"].iloc[0])
        lead = (f"For {pos}s the model leans most on **{names[0]}**."
                + (" Next: " + " · ".join(f"*{n}*" for n in names[1:3]) + "." if len(names) > 1 else "")
                + (f" It misses a {pos} by {base:.1f} points per game on average; scrambling the top input adds "
                   f"{float(t['importance'].iloc[0]):.2f} to that." if base is not None else ""))
        positions.append({"position": pos, "baseline_mae": base, "top": str(t["feature_label"].iloc[0]), "lead": lead,
                          "features": [{"rank": int(r.importance_rank), "feature_label": str(r.feature_label),
                                        "importance": _num(r.importance)} for r in t.itertuples()]})
    return {"model_version": _str(r0["model_version"]), "eval_season": int(r0["eval_season"]),
            "fit_seasons": _str(r0["fit_seasons"]), "scored_in": scored_in, "scored_in_league_id": lid,
            "how_measured": HOW_MEASURED.format(fit=fit, season=int(r0["eval_season"]), scored_in=scored_in),
            "unit": IMPORTANCE_UNIT, "positions": positions,
            "source": "app/pages/4_Rankings.py (What it leans on most)"}


def grades(league_id: str | None, scored_in: str | None) -> dict | None:
    """This season's played weeks next to the backtest (mart_projection_drift), and each past season (mart_projection_backtest:
    the projection's row, the current model)."""
    if league_id is None:
        return None
    dr = query(DRIFT_SQL, (league_id, league_id))
    bt = query(BACKTEST_SQL, (league_id, list(POSITIONS)))
    if dr.empty and bt.empty:
        return None
    rows = []
    for pos in POSITIONS:
        d = dr[dr["position"] == pos]
        b = bt[bt["position"] == pos]
        if d.empty and b.empty:
            continue
        d0 = d.iloc[0] if not d.empty else None
        w = pd.to_numeric(b["weeks"], errors="coerce").fillna(0)

        def wavg(col: str, b=b, w=w):
            v = pd.to_numeric(b[col], errors="coerce")
            ok = v.notna() & (w > 0)
            return round(float((v[ok] * w[ok]).sum() / w[ok].sum()), 3) if ok.any() else None
        played = d0 is not None and (_num(d0["weeks_scored"]) or 0) > 0
        rows.append({
            "position": pos,
            "season": {"weeks_scored": int(_num(d0["weeks_scored"]) or 0) if d0 is not None else 0,
                       "spearman": _num(d0["spearman"]) if played else None, "mae": _num(d0["mae"]) if played else None,
                       "coverage_80": _num(d0["coverage_80"]) if played else None},
            "backtest": {"spearman": _num(d0["backtest_spearman"]) if d0 is not None else wavg("spearman"),
                         "mae": _num(d0["backtest_mae"]) if d0 is not None else wavg("mae"),
                         "coverage_80": _num(d0["backtest_coverage_80"]) if d0 is not None else wavg("coverage_80")},
            "by_season": [{"season": int(r.season), "weeks": int(_num(r.weeks) or 0), "spearman": _num(r.spearman),
                           "mae": _num(r.mae), "coverage_80": _num(r.coverage_80)} for r in b.itertuples()],
        })
    played = dr[pd.to_numeric(dr["weeks_scored"], errors="coerce").fillna(0) > 0] if not dr.empty else dr
    first = int(played["first_week"].min()) if not played.empty else None
    last = int(played["last_week"].max()) if not played.empty else None
    span = None if first is None else (f"week {first}" if first == last else f"weeks {first}–{last}")
    season = int(dr["season"].iloc[0]) if not dr.empty else None
    in_prog = pd.to_numeric(dr["week_in_progress"], errors="coerce").max() if not dr.empty else float("nan")
    bt_seasons = (_str(dr["backtest_seasons"].dropna().iloc[0]) if not dr.empty and dr["backtest_seasons"].notna().any()
                  else (f"{int(bt['season'].min())}–{int(bt['season'].max())}" if not bt.empty else None))
    if span:
        answer = (f"The board scored like the backtest on NFL {season}'s complete {span} ({scored_in} scoring, players who "
                  f"played), next to the walk-forward backtest ({bt_seasons}).")
    else:
        answer = (f"No week of the {season or 'current'} season is complete yet, so there is nothing to score the board "
                  f"against; the backtest ({bt_seasons}) is below.")
    if pd.notna(in_prog):
        answer += f" Week {int(in_prog)} is still being played; it counts once its last game is in."
    return {"scored_in": scored_in, "scored_in_league_id": league_id, "season": season, "weeks": span,
            "backtest_seasons": bt_seasons,
            "season_model_version": _str(dr["model_version"].dropna().iloc[0]) if not dr.empty and dr["model_version"].notna().any() else None,
            "backtest_model_version": _str(bt["model_version"].dropna().iloc[0]) if not bt.empty and bt["model_version"].notna().any() else None,
            "answer": answer, "positions": rows, "howto": list(GRADES_HOWTO),
            "source": "app/pages/4_Rankings.py (How the model is doing this season; Backtest)"}


# ---- IG-3 (Wave I-G, the decision-quality review): the grades' qualification next to the headline grade, not below the
# metrics — a league we do not score every night is graded in another league's scoring and has no projection record
def grade_note(league_id: str, league_name: str | None, measured_in: str | None, house: bool) -> str | None:
    """The one line under "How the model is doing" for a league we do not score (None for a house league)."""
    if house:
        return None
    mine = league_name or "this league"
    where = f"{measured_in}'s scoring" if measured_in else "another league's scoring"
    if str(league_id or "").lower().startswith("mfl:"):
        return (f"These grades use {where}, not {mine}'s, and there is no direct projection record for this "
                "MyFantasyLeague league: read them as how the model does in general.")
    return (f"These grades use {where}, not {mine}'s, and {APP_NAME} keeps no projection record for {mine} yet: read "
            "them as how the model does in general.")
# ---- end IG-3


def about(league_id: str, source: str | None = None) -> dict:
    t0 = time.perf_counter()
    house = source != "sleeper" and known_league(str(league_id))
    key = (str(league_id), house)
    hit = _cache.get(key)
    if hit is not None:
        out = dict(hit)
    else:
        ctx = research.context(str(league_id), source)
        lid, name = _measured_in(ctx)
        out = {"league_id": ctx.league_id, "league_name": ctx.league_name, "source": ctx.source,
               "model": {"answer": MODEL_ANSWER, "sections": sections(ctx.league_name)},
               "importance": importance(lid, name), "grades": grades(lid, name),
               "rankings_howto": RANKINGS_HOWTO}                                                   # ---- IA-3
        out["grade_note"] = grade_note(ctx.league_id, ctx.league_name, name, ctx.house)                 # ---- IG-3
        if not ctx.house:
            out["why"] = (f"The importance and the grades are measured once per house league's scoring each night. "
                          f"{ctx.league_name} reads {name or 'the closest league'}'s: the closest scoring {APP_NAME} measures."
                          if name else "The importance and the grades are measured per house league's scoring; none is close.")
        _cache.put(key, out)
    from . import provenance  # ---- IR-4
    out.update(provenance.about_block())                                                           # ---- IR-4: versions, checks
    out["timings_ms"] = {"request_total": round((time.perf_counter() - t0) * 1000, 1)}
    return out


def clear() -> None:
    _cache.clear()
