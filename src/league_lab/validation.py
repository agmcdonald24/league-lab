"""The validation harness (V-1, Wave I-G; docs/reviews/2026-10-03-decision-quality-review.md § "Model validation and
release gates"): grade what the app recommended before kickoff against what the managers started and what happened.

Inputs (never anything after the outcome inside the record: the record is written before kickoff, the grade reads
actual points only for weeks Sleeper has scored):

* the **decision record** ``ops.lineup_record`` (``league_lab.lineup`` V-1 block): the app's proposed lineup per
  roster-week as of the last build before the week's first kickoff (``record_source = 'kickoff'``), or rebuilt once
  from the frozen projections for a week played before the record existed (``'reconstructed'``), with the decision
  cards' closest calls and their odds;
* the **submitted** lineups and Sleeper's points (``analytics.league_player_week``: ``is_starter``,
  ``points_observed``);
* the **hindsight optimum** (``ops.lineup_totals`` ``is_realised``: the best lineup the roster Sleeper listed that
  week could have started, at Sleeper's points);
* the week's final injury report (``analytics.mart_player_week_features``) for the news-affected cases.

Per roster-week (``grade_roster_weeks``; the dbt twin is ``mart_decision_record``, a needs_db test holds them equal):

* ``submitted_points`` = Sleeper's starters' points (= the matchup score);
* ``app_points`` = the record's starters at the points they scored that week (Sleeper's count for the league; a
  starter on no roster that week: his points in the league's scoring, ``fct_player_game_league``; no stat row = he
  did not play = 0, Sleeper's own rule; a K / DEF with no number = unknown -> the roster-week's ``app_points`` is NULL
  and it is left out of the sums, counted in ``n_app_unknown``);
* ``optimum_points`` = the hindsight optimum; **regret** = optimum − submitted (>= 0 on the same roster); **the
  app's edge** = app − submitted (what following the recommendation would have added); ``app_regret`` = optimum −
  app (may be negative when the record's roster held a player dropped before kickoff who then scored);
* ``is_news_affected``: a starter of a ``kickoff`` record whose injury report changed after the build (the week's
  final ``report_status`` differs from the one the build saw, or he went to NFL injured reserve). A reconstructed
  week read the final report, so it is never news-affected (it cannot be measured there).

Close calls (``grade_calls``): each card call (starter vs the bench player who would come in) graded by the outcome
(1 = the starter outscored him, ½ = equal, 0 = not); with the predicted P(starter wins) that is the calibration
table (``decisions.coverage_table``) and the Brier score (``decisions.brier``); the coin flips (the card's own rule:
under 55%) are the line "the coin flips landed 54% for the side we leaned (52% expected, 31 calls)".

``summary`` makes the season-to-date block `/api/record` (``decisions``), the About page and the console's Record page
show; ``validate`` (``league-lab validate``) writes the record and prints the grade.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import decisions as D

log = logging.getLogger(__name__)

UNPLAYABLE_STATUS = ("Out", "Doubtful")

# ------------------------------------------------------------------------------ loading (the CLI and the parity test)
RECORD_SQL = """select league_id, season, week, roster_id, record_source, run_at, model_version, pricing, role, slot,
                       sleeper_player_id, gsis_id, player_name, position, value, margin, report_status, lineup_value,
                       call_rank, alt_sleeper_player_id, alt_gsis_id, alt_player_name, alt_value, p_win, is_coin_flip
                from ops.lineup_record where season = %s and league_id = any(%s) and role = 'starter'"""
WEEKLY_SQL = """select league_id, week, roster_id, sleeper_player_id, gsis_id, is_starter, points_observed, is_scored_week
                from analytics.league_player_week where season = %s and league_id = any(%s)"""
OPTIMUM_SQL = """select league_id, week, roster_id, lineup_value as optimum_points
                 from ops.lineup_totals where season = %s and league_id = any(%s) and is_realised"""
FALLBACK_SQL = """select league_id, week, gsis_id, sum(points) as points from analytics.fct_player_game_league
                  where season = %s and league_id = any(%s) and season_type = 'REG' group by 1, 2, 3"""
STATUS_SQL = """select week, gsis_id, report_status, roster_status from analytics.mart_player_week_features
                where season = %s and gsis_id = any(%s)"""


def _f(v) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if np.isnan(x) else x


def _r2(x) -> float | None:
    x = _f(x)
    return None if x is None else round(x + 0.0, 2) + 0.0


@dataclass
class GradeInputs:
    record: pd.DataFrame       # RECORD_SQL rows (starters)
    weekly: pd.DataFrame       # WEEKLY_SQL rows
    optimum: pd.DataFrame      # OPTIMUM_SQL rows
    fallback: pd.DataFrame     # FALLBACK_SQL rows
    status: pd.DataFrame       # STATUS_SQL rows (the week's final injury report)


def load_inputs(query: Callable[[str, tuple], pd.DataFrame], season: int, league_ids: Iterable[str]) -> GradeInputs:
    """The grade's inputs through ``query(sql, params) -> DataFrame`` (a psycopg connection: ``frame_query(conn)``)."""
    ids = list(league_ids)
    rec = query(RECORD_SQL, (season, ids))
    gsis = sorted({g for g in rec.get("gsis_id", pd.Series(dtype=object)).dropna()})
    return GradeInputs(rec, query(WEEKLY_SQL, (season, ids)), query(OPTIMUM_SQL, (season, ids)),
                       query(FALLBACK_SQL, (season, ids)),
                       query(STATUS_SQL, (season, gsis)) if gsis else pd.DataFrame(columns=["week", "gsis_id", "report_status", "roster_status"]))


def frame_query(conn) -> Callable[[str, tuple], pd.DataFrame]:
    def q(sql: str, params: tuple = ()) -> pd.DataFrame:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])
    return q


# ------------------------------------------------------------------------------ grading
def _points_lookup(weekly: pd.DataFrame, fallback: pd.DataFrame):
    """(league, week, sleeper id, gsis) -> the points a player scored that week in the league (see the module docstring)."""
    obs: dict[tuple[str, int, str], float] = {}
    for r in weekly.itertuples(index=False):
        v = _f(r.points_observed)
        if v is not None:
            obs[(r.league_id, int(r.week), str(r.sleeper_player_id))] = v
    fb = {(r.league_id, int(r.week), r.gsis_id): _f(r.points) for r in fallback.itertuples(index=False)}

    def points(league_id: str, week: int, sid, gsis) -> float | None:
        v = obs.get((league_id, int(week), str(sid))) if sid is not None else None
        if v is not None:
            return v
        if isinstance(gsis, str) and gsis:
            v = fb.get((league_id, int(week), gsis))
            return 0.0 if v is None else v           # no stat row: he did not play, 0 (Sleeper's rule)
        return None
    return points


def _scored_weeks(weekly: pd.DataFrame) -> set[tuple[str, int]]:
    if weekly.empty:
        return set()
    g = weekly.assign(s=weekly["is_scored_week"].fillna(False).astype(bool)).groupby(["league_id", "week"])["s"].all()
    return {(lg, int(w)) for (lg, w), s in g.items() if s}


def _news_starters(rec: pd.DataFrame, status: pd.DataFrame) -> pd.Series:
    """Per record starter row: True when the week's final injury report differs from the one the build saw (or he went
    to NFL injured reserve) — only for ``kickoff`` records (a reconstructed week read the final report)."""
    if rec.empty:
        return pd.Series(dtype=bool)
    st = {(int(r.week), r.gsis_id): (r.report_status, r.roster_status) for r in status.itertuples(index=False)}
    out = []
    for r in rec.itertuples(index=False):
        if r.record_source != "kickoff" or not isinstance(r.gsis_id, str):
            out.append(False)
            continue
        final = st.get((int(r.week), r.gsis_id))
        if final is None:
            out.append(False)
            continue
        seen = r.report_status if isinstance(r.report_status, str) else None
        now = final[0] if isinstance(final[0], str) else None
        out.append(seen != now or final[1] == "RES")
    return pd.Series(out, index=rec.index, dtype=bool)


RW_COLUMNS = ["league_id", "season", "week", "roster_id", "record_source", "model_version", "pricing", "status",
              "submitted_points", "app_points", "optimum_points", "regret", "app_edge", "app_regret", "n_starters",
              "n_changed", "n_app_unknown", "n_news_starters", "is_news_affected"]


def grade_roster_weeks(g: GradeInputs) -> pd.DataFrame:
    """One row per record roster-week (``RW_COLUMNS``; the mart's columns)."""
    rec = g.record[g.record["role"] == "starter"] if "role" in g.record else g.record
    if rec.empty:
        return pd.DataFrame(columns=RW_COLUMNS)
    points = _points_lookup(g.weekly, g.fallback)
    scored = _scored_weeks(g.weekly)
    rec = rec.assign(_news=_news_starters(rec, g.status))
    sub: dict[tuple[str, int, int], float] = {}
    started: dict[tuple[str, int, int], set] = {}
    for r in g.weekly.itertuples(index=False):
        k = (r.league_id, int(r.week), int(r.roster_id))
        started.setdefault(k, set())
        sub.setdefault(k, 0.0)
        if bool(r.is_starter):
            started[k].add(str(r.sleeper_player_id))
            sub[k] += _f(r.points_observed) or 0.0
    opt = {(r.league_id, int(r.week), int(r.roster_id)): _f(r.optimum_points) for r in g.optimum.itertuples(index=False)}
    out = []
    for (lg, season, week, roster), grp in rec.groupby(["league_id", "season", "week", "roster_id"], sort=True):
        k = (lg, int(week), int(roster))
        is_scored = (lg, int(week)) in scored
        pts = [points(lg, week, r.sleeper_player_id, r.gsis_id) for r in grp.itertuples(index=False)]
        unknown = sum(p is None for p in pts)
        app = _r2(sum(p for p in pts if p is not None)) if is_scored and not unknown else None
        submitted = _r2(sub[k]) if is_scored and k in sub else None
        optimum = _r2(opt.get(k)) if is_scored else None
        n_news = int(grp["_news"].sum())
        out.append({
            "league_id": lg, "season": int(season), "week": int(week), "roster_id": int(roster),
            "record_source": grp["record_source"].iloc[0], "model_version": grp["model_version"].iloc[0],
            "pricing": grp["pricing"].iloc[0] if "pricing" in grp else "flat",
            "status": "scored" if is_scored else "in_play",
            "submitted_points": submitted, "app_points": app, "optimum_points": optimum,
            "regret": _r2(optimum - submitted) if optimum is not None and submitted is not None else None,
            "app_edge": _r2(app - submitted) if app is not None and submitted is not None else None,
            "app_regret": _r2(optimum - app) if optimum is not None and app is not None else None,
            "n_starters": len(grp),
            "n_changed": int(sum(str(s) not in started.get(k, set()) for s in grp["sleeper_player_id"])) if k in started else None,
            "n_app_unknown": unknown if is_scored else None,
            "n_news_starters": n_news, "is_news_affected": n_news > 0,
        })
    return pd.DataFrame(out, columns=RW_COLUMNS)


CALL_COLUMNS = ["league_id", "season", "week", "roster_id", "record_source", "call_rank", "slot", "sleeper_player_id",
                "player_name", "value", "margin", "alt_sleeper_player_id", "alt_player_name", "alt_value", "p_win",
                "is_coin_flip", "status", "starter_points", "alt_points", "outcome"]


def grade_calls(g: GradeInputs) -> pd.DataFrame:
    """One row per card call of the record (``CALL_COLUMNS``): both players' points and the outcome for the starter
    (1 / 0.5 / 0; NULL until the week is scored or when either number is unknown)."""
    rec = g.record
    calls = rec[rec["call_rank"].notna()] if "call_rank" in rec and not rec.empty else rec.iloc[0:0]
    if calls.empty:
        return pd.DataFrame(columns=CALL_COLUMNS)
    points = _points_lookup(g.weekly, g.fallback)
    scored = _scored_weeks(g.weekly)
    out = []
    for r in calls.itertuples(index=False):
        is_scored = (r.league_id, int(r.week)) in scored
        a = points(r.league_id, r.week, r.sleeper_player_id, r.gsis_id) if is_scored else None
        b = points(r.league_id, r.week, r.alt_sleeper_player_id, r.alt_gsis_id) if is_scored else None
        outcome = None if a is None or b is None else (1.0 if a > b + 1e-9 else 0.0 if b > a + 1e-9 else 0.5)
        out.append({"league_id": r.league_id, "season": int(r.season), "week": int(r.week), "roster_id": int(r.roster_id),
                    "record_source": r.record_source, "call_rank": int(r.call_rank), "slot": r.slot,
                    "sleeper_player_id": r.sleeper_player_id, "player_name": r.player_name, "value": _f(r.value),
                    "margin": _f(r.margin), "alt_sleeper_player_id": r.alt_sleeper_player_id,
                    "alt_player_name": r.alt_player_name, "alt_value": _f(r.alt_value), "p_win": _f(r.p_win),
                    "is_coin_flip": bool(r.is_coin_flip) if r.is_coin_flip is not None and not pd.isna(r.is_coin_flip) else None,
                    "status": "scored" if is_scored else "in_play", "starter_points": a, "alt_points": b, "outcome": outcome})
    return pd.DataFrame(out, columns=CALL_COLUMNS).sort_values(["league_id", "week", "roster_id", "call_rank"]).reset_index(drop=True)


# ------------------------------------------------------------------------------ calibration
def calibration(calls: pd.DataFrame, bins: int | None = None) -> dict:
    """The graded calls with odds: n, won (sum of outcomes), expected (sum of P), Brier, the coverage table
    (``decisions.coverage_table``; equal-count bins, 10 calls a bin at least, at most 10 bins) and the coin flips."""
    c = calls[calls["outcome"].notna() & calls["p_win"].notna()] if not calls.empty else calls
    pairs = [(float(p), float(o)) for p, o in zip(c["p_win"], c["outcome"], strict=True)] if not c.empty else []
    n = len(pairs)
    flips = c[c["is_coin_flip"].fillna(False).astype(bool)] if n else c
    k = bins if bins is not None else max(1, min(10, n // 10))
    return {
        "n": n, "won": _r2(sum(o for _, o in pairs)) if n else None, "expected": _r2(sum(p for p, _ in pairs)) if n else None,
        "brier": round(D.brier(pairs), 4) if n else None,
        "coin_flips": {"n": len(flips), "won": _r2(flips["outcome"].sum()) if len(flips) else None,
                       "expected": _r2(flips["p_win"].sum()) if len(flips) else None},
        "table": [{**row, "predicted": round(row["predicted"], 4), "observed": round(row["observed"], 4),
                   "p_lo": round(row["p_lo"], 4), "p_hi": round(row["p_hi"], 4)} for row in D.coverage_table(pairs, k)] if n else [],
    }


# ------------------------------------------------------------------------------ the season-to-date block
def _weeks_words(weeks: list[int]) -> str:
    if not weeks:
        return ""
    if len(weeks) == 1:
        return f"week {weeks[0]}"
    if weeks == list(range(weeks[0], weeks[-1] + 1)):
        return f"weeks {weeks[0]}–{weeks[-1]}"
    return "weeks " + ", ".join(str(w) for w in weeks[:-1]) + f" and {weeks[-1]}"


def _pct(x: float) -> int:
    return int(round(100 * x))


def summary(rw: pd.DataFrame, calls: pd.DataFrame) -> dict:
    """``/api/record``'s ``decisions`` (docs/INTERFACES V-1): per scored week the league's sums over the roster-weeks
    with every number known, the season to date (= the sum of the weeks, to the cent), the calls' calibration, the
    news-affected cases and the plain sentences. ``available`` is False until one week is graded."""
    rw = rw if rw is not None else pd.DataFrame(columns=RW_COLUMNS)
    calls = calls if calls is not None else pd.DataFrame(columns=CALL_COLUMNS)
    recon = sorted({int(w) for w, s in zip(rw.get("week", []), rw.get("record_source", []), strict=True) if s == "reconstructed"})
    g = rw[(rw["status"] == "scored") & rw["submitted_points"].notna() & rw["app_points"].notna() & rw["optimum_points"].notna()] \
        if not rw.empty else rw
    weeks = []
    for week, grp in (g.groupby("week", sort=True) if not g.empty else []):
        srcs = sorted(set(grp["record_source"]))
        weeks.append({"week": int(week), "record_source": srcs[0] if len(srcs) == 1 else "mixed", "rosters": len(grp),
                      "submitted": _r2(grp["submitted_points"].sum()), "app": _r2(grp["app_points"].sum()),
                      "optimum": _r2(grp["optimum_points"].sum()), "regret": _r2(grp["regret"].sum()),
                      "edge": _r2(grp["app_edge"].sum()), "news_rosters": int(grp["is_news_affected"].astype(bool).sum())})
    tot = None
    if weeks:
        tot = {"weeks": len(weeks), "roster_weeks": sum(w["rosters"] for w in weeks),
               **{k: _r2(sum(w[k] for w in weeks)) for k in ("submitted", "app", "optimum", "regret", "edge")}}
    news = g[g["is_news_affected"].astype(bool)] if not g.empty else g
    news_block = {"roster_weeks": len(news), "edge": _r2(news["app_edge"].sum()) if len(news) else None,
                  "regret": _r2(news["regret"].sum()) if len(news) else None}
    cal = calibration(grade_calls_scored(calls))
    sentences = {"edge": None, "calls": None, "news": None}
    if tot:
        ww = _weeks_words([w["week"] for w in weeks])
        per = tot["edge"] / tot["roster_weeks"]
        sentences["edge"] = (f"{ww.capitalize()}: had every team started our lineup, the league would have scored "
                             f"{abs(tot['edge']):.1f} points {'more' if tot['edge'] >= 0 else 'fewer'} than it did "
                             f"({per:+.1f} a team a week). The best lineups in hindsight beat the ones started by "
                             f"{tot['regret']:.1f} points ({tot['regret'] / tot['roster_weeks']:.1f} a team a week).")
    cf = cal["coin_flips"]
    if cf["n"]:
        sentences["calls"] = (f"The coin flips landed {_pct(cf['won'] / cf['n'])}% for the side we leaned "
                              f"({_pct(cf['expected'] / cf['n'])}% expected, {cf['n']} call{'s' if cf['n'] != 1 else ''}).")
    elif cal["n"]:
        sentences["calls"] = (f"No coin flip graded yet; the {cal['n']} closest calls landed {_pct(cal['won'] / cal['n'])}% "
                              f"for the side we leaned ({_pct(cal['expected'] / cal['n'])}% expected).")
    if tot:
        if news_block["roster_weeks"]:
            n = news_block["roster_weeks"]
            sentences["news"] = (f"{n} lineup{'s' if n != 1 else ''} had a starter's injury report change after our "
                                 f"morning build; there our lineup scored {news_block['edge']:+.1f} against the one started.")
        else:
            sentences["news"] = ("No graded lineup had a starter's injury report change after our build"
                                 + (" (the rebuilt weeks cannot tell: they read the final report)." if recon else "."))
    note = None
    if recon:
        note = (f"{_weeks_words(recon).capitalize()} were played before this record existed: their lineups were rebuilt "
                "after kickoff from the projections frozen then, with the final injury report.")
    return {"available": bool(weeks), "weeks": weeks, "season_totals": tot, "calls": cal, "news": news_block,
            "sentences": sentences, "reconstructed_weeks": recon, "note": note}


def grade_calls_scored(calls: pd.DataFrame) -> pd.DataFrame:
    return calls[calls["status"] == "scored"] if not calls.empty else calls


# ------------------------------------------------------------------------------ the command
@dataclass
class Validation:
    season: int
    record: object | None          # lineup.RecordRun
    roster_weeks: pd.DataFrame
    calls: pd.DataFrame
    summary: dict


def validate(season: int | None = None, league_ids: Iterable[str] | None = None, write: bool = True) -> Validation | None:
    """``league-lab validate``: write the decision record (``lineup.run_record``: the next week's lineup before kickoff,
    reconstructed weeks once), then grade it on the scored weeks."""
    import psycopg

    from . import lineup
    from .config import get_settings

    run = lineup.run_record(season) if write else None
    with psycopg.connect(get_settings().pipeline_dsn(), autocommit=True) as conn:
        q = frame_query(conn)
        if season is None:
            s = q("select max(season) as s from ops.lineup_record", ())
            season = None if s.empty or pd.isna(s.iloc[0]["s"]) else int(s.iloc[0]["s"])
        if season is None:
            log.warning("validate: the decision record is empty")
            return None
        ids = list(league_ids) if league_ids else q("select distinct league_id from ops.lineup_record where season = %s",
                                                   (season,))["league_id"].tolist()
        g = load_inputs(q, int(season), ids)
    rw, calls = grade_roster_weeks(g), grade_calls(g)
    by_league = {lg: summary(rw[rw["league_id"] == lg], calls[calls["league_id"] == lg]) for lg in ids}
    return Validation(int(season), run, rw, calls, by_league)
