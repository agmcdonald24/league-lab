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
show; ``record_run.validate`` (``league-lab validate``) writes the record and prints the grade.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import decisions as D

log = logging.getLogger(__name__)

UNPLAYABLE_STATUS = ("Out", "Doubtful")

# ------------------------------------------------------------------------------ loading (the CLI and the parity test)
RECORD_SQL = """select league_id, season, week, roster_id, record_source, run_at, first_kickoff_at, model_version, pricing, role, slot,
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
    # ---- V-2 (Wave I-H): optional inputs (None = not read; every V-1 caller builds the first five only)
    events: pd.DataFrame | None = None      # EVENTS_SQL rows: availability events (gsis_id, status, at)
    events_span: tuple | None = None        # (first, last) ingested_at of the store's availability events; None = no store
    kickoffs: pd.DataFrame | None = None    # PLAYER_KICKOFF_SQL rows: (week, gsis_id, kickoff_at), the starter's own game
    market: pd.DataFrame | None = None      # MARKET_SQL rows: ops.decision_market, Sleeper's projections as a lineup
    unknown_off_roster: bool = False        # MFL: a starter on no franchise that week has no number (unknown, not 0)


def load_inputs(query: Callable[[str, tuple], pd.DataFrame], season: int, league_ids: Iterable[str], *,
                events: bool = False) -> GradeInputs:
    """The grade's inputs through ``query(sql, params) -> DataFrame`` (a psycopg connection: ``frame_query(conn)``).
    V-2: Sleeper's lineup (``ops.decision_market``) when the table exists; ``events``: the event store's availability
    events too (``league-lab validate`` on a database that has ``events.events``; the API reads them itself)."""
    ids = list(league_ids)
    rec = query(RECORD_SQL, (season, ids))
    gsis = sorted({g for g in rec.get("gsis_id", pd.Series(dtype=object)).dropna()})
    g = GradeInputs(rec, query(WEEKLY_SQL, (season, ids)), query(OPTIMUM_SQL, (season, ids)),
                    query(FALLBACK_SQL, (season, ids)),
                    query(STATUS_SQL, (season, gsis)) if gsis else pd.DataFrame(columns=["week", "gsis_id", "report_status", "roster_status"]))
    if _has(query, "ops.decision_market"):                                   # ---- V-2
        g.market = query(MARKET_SQL, (season, ids))
    if events and gsis and _has(query, "events.events"):                     # ---- V-2
        g.events, g.events_span = read_events(query, gsis)
        g.kickoffs = query(PLAYER_KICKOFF_SQL, (season, gsis))
    return g


def frame_query(conn) -> Callable[[str, tuple], pd.DataFrame]:
    def q(sql: str, params: tuple = ()) -> pd.DataFrame:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])
    return q


# ------------------------------------------------------------------------------ grading
def _points_lookup(weekly: pd.DataFrame, fallback: pd.DataFrame, zero_off_roster: bool = True):
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
        if isinstance(gsis, str) and gsis and zero_off_roster:
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
              "n_changed", "n_app_unknown", "n_news_starters", "is_news_affected",
              "news_source", "market_points", "market_edge", "n_market_unknown"]       # ---- V-2


def grade_roster_weeks(g: GradeInputs) -> pd.DataFrame:
    """One row per record roster-week (``RW_COLUMNS``; the mart's columns)."""
    rec = g.record[g.record["role"] == "starter"] if "role" in g.record else g.record
    if rec.empty:
        return pd.DataFrame(columns=RW_COLUMNS)
    points = _points_lookup(g.weekly, g.fallback, zero_off_roster=not g.unknown_off_roster)
    scored = _scored_weeks(g.weekly)
    news = news_by_starter(rec, g.status, g.events, g.kickoffs, g.events_span)          # ---- V-2: the event store first
    rec = rec.assign(_news=news["flag"].to_numpy(), _news_src=news["source"].to_numpy())
    mkt = market_points(g.market, points) if g.market is not None else {}             # ---- V-2: Sleeper's lineup
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
        srcs = set(grp.loc[grp["record_source"] == "kickoff", "_news_src"]) or {"report"}
        m_pts, m_unknown = mkt.get(k, (None, None))
        m_pts = m_pts if is_scored and not m_unknown else None
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
            "news_source": "events" if srcs == {"events"} else "report",
            "market_points": _r2(m_pts), "market_edge": _r2(m_pts - submitted) if m_pts is not None and submitted is not None else None,
            "n_market_unknown": m_unknown if is_scored else None,
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


def _signed(x: float) -> str:
    """+1.2 / −1.2 (the minus sign, as the page's tiles write it) / 0.0."""
    return f"{'+' if x > 0 else '−' if x < 0 else ''}{abs(x):.1f}"


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
        # ---- V-2: Sleeper's projections as a lineup (the week's sum only when every team has it) and the news source
        mk = pd.to_numeric(grp["market_points"], errors="coerce") if "market_points" in grp else pd.Series(dtype=float)
        ns = set(grp["news_source"]) if "news_source" in grp else {"report"}
        weeks.append({"week": int(week), "record_source": srcs[0] if len(srcs) == 1 else "mixed", "rosters": len(grp),
                      "submitted": _r2(grp["submitted_points"].sum()), "app": _r2(grp["app_points"].sum()),
                      "optimum": _r2(grp["optimum_points"].sum()), "regret": _r2(grp["regret"].sum()),
                      "edge": _r2(grp["app_edge"].sum()), "news_rosters": int(grp["is_news_affected"].astype(bool).sum()),
                      "market": _r2(mk.sum()) if len(mk) == len(grp) and mk.notna().all() else None,
                      "news_source": next(iter(ns)) if len(ns) == 1 else "mixed"})
    tot = None
    if weeks:
        tot = {"weeks": len(weeks), "roster_weeks": sum(w["rosters"] for w in weeks),
               **{k: _r2(sum(w[k] for w in weeks)) for k in ("submitted", "app", "optimum", "regret", "edge")}}
        mw = [w for w in weeks if w["market"] is not None]                                   # ---- V-2
        tot.update({"market": _r2(sum(w["market"] for w in mw)) if mw else None, "market_weeks": [w["week"] for w in mw],
                    "market_submitted": _r2(sum(w["submitted"] for w in mw)) if mw else None,
                    "market_app": _r2(sum(w["app"] for w in mw)) if mw else None})
    news = g[g["is_news_affected"].astype(bool)] if not g.empty else g
    nsrc = sorted(set(g["news_source"])) if not g.empty and "news_source" in g else ["report"]          # ---- V-2
    news_block = {"roster_weeks": len(news), "edge": _r2(news["app_edge"].sum()) if len(news) else None,
                  "regret": _r2(news["regret"].sum()) if len(news) else None,
                  "source": nsrc[0] if len(nsrc) == 1 else "mixed"}
    cal = calibration(grade_calls_scored(calls))
    sentences = {"edge": None, "calls": None, "news": None}
    if tot:
        ww = _weeks_words([w["week"] for w in weeks])
        per = tot["edge"] / tot["roster_weeks"]
        sentences["edge"] = (f"{ww.capitalize()}: had every team started our lineup, the league would have scored "
                             f"{abs(tot['edge']):.1f} points {'more' if tot['edge'] >= 0 else 'fewer'} than it did "
                             f"({_signed(per)} a team a week). The best lineups in hindsight beat the ones started by "
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
            if news_block["source"] == "events":                                    # ---- V-2: the event store's moves
                sentences["news"] = (f"{n} lineup{'s' if n != 1 else ''} had a starter's injury status change between our "
                                     f"build and his kickoff; there our lineups scored {_signed(news_block['edge'])} "
                                     "against the ones started. They are graded apart: we could not have known.")
            else:
                sentences["news"] = (f"{n} lineup{'s' if n != 1 else ''} had a starter's injury report change after our "
                                     f"morning build; there our lineups scored {_signed(news_block['edge'])} against the ones started.")
        else:
            sentences["news"] = ("No graded lineup had a starter's injury report change after our build"
                                 + (" (the rebuilt weeks cannot tell: they read the final report)." if recon else "."))
    sentences["market"] = market_sentence(tot)                                      # ---- V-2
    note = None
    if recon:
        note = (f"{_weeks_words(recon).capitalize()} were played before this record existed: their lineups were rebuilt "
                "after kickoff from the projections frozen then, with the final injury report.")
    return {"available": bool(weeks), "weeks": weeks, "season_totals": tot, "calls": cal, "news": news_block,
            "sentences": sentences, "reconstructed_weeks": recon, "note": note}


def grade_calls_scored(calls: pd.DataFrame) -> pd.DataFrame:
    return calls[calls["status"] == "scored"] if not calls.empty else calls


# ------------------------------------------------------------------------------ the command (league_lab.record_run.validate)
@dataclass
class Validation:
    season: int
    record: object | None          # lineup.RecordRun
    roster_weeks: pd.DataFrame
    calls: pd.DataFrame
    summary: dict


# ---- V-2 (Wave I-H): the decision record, personal and live — the event store's news flag, Sleeper's projections as a
# lineup, one team's view, MyFantasyLeague leagues (docs/METRICS.md § "The decision record" → "Personal and live").
#
# * **News from the event store.** ``events.events`` (IG-2) holds every injury-status move the server saw, with its
#   time. A ``kickoff`` record's starter is news-affected when the store has an availability event for him after the
#   record's ``run_at`` and before HIS kickoff (his game's ``dim_game.kickoff_at``; unknown -> the week's first kickoff
#   + 4 days) whose status differs from the one the build saw (``report_status``: none = ACTIVE). The store answers
#   for a league-week only when it was running across it (its first availability event at or before the week's first
#   kickoff, its newest at or after ``run_at``); otherwise the V-1 rule (the final report differs) is the fallback.
#   ``news_source`` says which ("events" | "report"). Reconstructed weeks are never flagged (V-1's reason).
# * **Sleeper's projections as a lineup** (``ops.decision_market``, written by ``league-lab validate``): for each
#   record roster-week of a Sleeper league, the best lineup of the SAME roster the record saw (starters + bench; the
#   unplayable stay out) valued by Sleeper's projection — the last snapshot fetched before the week's first kickoff
#   (``mart_projection_record``'s rule), priced in the league's scoring the way the record priced ours
#   (``scoring.price_projected`` in the week's ``pricing``; a K flat). Sleeper has no DEF line we price: a DEF keeps
#   our value, so the two lineups never differ there. A player Sleeper has no line for is unvalued (seated only where
#   nobody valued can play). Graded like ours: ``market_points``, ``market_edge`` = market − submitted.
# * **One team** (``team_summary``): the roster's graded weeks, their sums (they reconcile with the league's), its
#   close calls and how they landed, its news-affected weeks, and the sentences.
# * **MyFantasyLeague** (``mfl_weekly``): the grade's weekly / optimum frames from MFL's ``weeklyResults`` (the
#   franchise's starters and every rostered player's score; MFL's own ``opt_pts`` is the hindsight optimum; a
#   double-header franchise counted once a week); a record starter on no franchise that week has no number (unknown).
AVAILABILITY_CODE = {"Out": "OUT", "Doubtful": "DOUBTFUL", "Questionable": "QUESTIONABLE"}
NEWS_WINDOW_DAYS = 4            # a starter whose game time is unknown: the week's first kickoff + 4 days (Monday night)
EVENTS_SQL = """select gsis_id, status, coalesce(effective_at, published_at, ingested_at) as at
                from events.events where kind = 'availability' and gsis_id = any(%s)"""
EVENTS_SPAN_SQL = """select min(ingested_at) as first, max(ingested_at) as last from events.events where kind = 'availability'"""
PLAYER_KICKOFF_SQL = """select f.week, f.gsis_id, min(g.kickoff_at) as kickoff_at
                        from analytics.mart_player_week_features as f
                        join analytics.dim_game as g on g.season = f.season and g.week = f.week and g.season_type = 'REG'
                         and f.team in (g.home_team, g.away_team)
                        where f.season = %s and f.gsis_id = any(%s) group by 1, 2"""
MARKET_SQL = """select league_id, season, week, roster_id, slot, sleeper_player_id, gsis_id, player_name, position,
                       market_value, value_source, fetched_at, pricing
                from ops.decision_market where season = %s and league_id = any(%s)"""
MARKET_COLUMNS = ["league_id", "season", "week", "roster_id", "slot", "sleeper_player_id", "gsis_id", "player_name",
                  "position", "market_value", "value_source", "fetched_at", "pricing", "written_at"]
def _has(query: Callable[[str, tuple], pd.DataFrame], relation: str) -> bool:
    try:
        df = query("select to_regclass(%s) is not null as ok", (relation,))
    except Exception:  # noqa: BLE001 - no database answer: the input is simply not there
        return False
    return bool(not df.empty and df.iloc[0]["ok"])


def read_events(query: Callable[[str, tuple], pd.DataFrame], gsis: list[str]) -> tuple[pd.DataFrame, tuple | None]:
    """(the players' availability events, the store's span) — the store missing or empty: (empty frame, None)."""
    ev = query(EVENTS_SQL, (gsis,))
    sp = query(EVENTS_SPAN_SQL, ())
    span = None
    if not sp.empty and sp.iloc[0]["first"] is not None and not pd.isna(sp.iloc[0]["first"]):
        span = (pd.Timestamp(sp.iloc[0]["first"]), pd.Timestamp(sp.iloc[0]["last"]))
    return ev, span


def _ts(v) -> pd.Timestamp | None:
    if v is None:
        return None
    try:
        t = pd.Timestamp(v)
    except (TypeError, ValueError):
        return None
    if pd.isna(t):
        return None
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def news_by_starter(rec: pd.DataFrame, status: pd.DataFrame, events: pd.DataFrame | None = None,
                    kickoffs: pd.DataFrame | None = None, span: tuple | None = None) -> pd.DataFrame:
    """Per record starter row: ``flag`` (news-affected) and ``source`` ("events" | "report"), aligned to ``rec``'s
    index. The event store answers where it was running across the league-week (module block above); else V-1's
    report diff (``_news_starters``)."""
    report = _news_starters(rec, status) if not rec.empty else pd.Series(dtype=bool)
    out = pd.DataFrame({"flag": report.astype(bool), "source": "report"}, index=rec.index)
    if rec.empty or events is None or span is None:
        return out
    first, last = _ts(span[0]), _ts(span[1])
    by_player: dict[str, list[tuple[pd.Timestamp, str]]] = defaultdict(list)
    for e in events.itertuples(index=False):
        t = _ts(e.at)
        if t is not None and isinstance(e.gsis_id, str):
            by_player[e.gsis_id].append((t, str(e.status or "ACTIVE").upper()))
    kick = {} if kickoffs is None else {(int(r.week), r.gsis_id): _ts(r.kickoff_at) for r in kickoffs.itertuples(index=False)}
    for i, r in zip(rec.index, rec.itertuples(index=False), strict=True):
        if r.record_source != "kickoff" or not isinstance(r.gsis_id, str):
            continue
        run_at, k0 = _ts(getattr(r, "run_at", None)), _ts(getattr(r, "first_kickoff_at", None))
        if run_at is None or k0 is None or first is None or last is None or first > k0 or last < run_at:
            continue                                            # the store was not running across this week
        his = kick.get((int(r.week), r.gsis_id)) or (k0 + pd.Timedelta(days=NEWS_WINDOW_DAYS))
        seen = AVAILABILITY_CODE.get(r.report_status if isinstance(r.report_status, str) else "", "ACTIVE")
        moved = any(run_at < t < his and st != seen for t, st in by_player.get(r.gsis_id, []))
        out.at[i, "flag"], out.at[i, "source"] = moved, "events"
    return out


def news_overrides(rec: pd.DataFrame, events: pd.DataFrame | None, kickoffs: pd.DataFrame | None,
                   span: tuple | None) -> dict[tuple[str, int, int], int]:
    """(league, week, roster) -> news-affected starters, for the roster-weeks the event store answers (the API's use:
    the marts carry the report rule; the store lives on the hosted copy, so the request side applies it)."""
    if rec.empty or events is None or span is None:
        return {}
    nb = news_by_starter(rec, pd.DataFrame(columns=["week", "gsis_id", "report_status", "roster_status"]), events,
                         kickoffs, span)
    r = rec.assign(_f=nb["flag"].to_numpy(), _s=nb["source"].to_numpy())
    out = {}
    for (lg, w, ro), grp in r[r["record_source"] == "kickoff"].groupby(["league_id", "week", "roster_id"]):
        if set(grp["_s"]) == {"events"}:
            out[(str(lg), int(w), int(ro))] = int(grp["_f"].sum())
    return out


def apply_news(rw: pd.DataFrame, overrides: Mapping[tuple[str, int, int], int]) -> pd.DataFrame:
    """The graded roster-weeks with the event store's flags where it answered (``news_source`` = "events")."""
    if rw.empty or not overrides:
        if "news_source" not in rw:
            rw = rw.assign(news_source="report")
        return rw
    rw = rw.copy()
    if "news_source" not in rw:
        rw["news_source"] = "report"
    for i, r in rw.iterrows():
        k = (str(r["league_id"]), int(r["week"]), int(r["roster_id"]))
        if k in overrides:
            rw.at[i, "n_news_starters"] = overrides[k]
            rw.at[i, "is_news_affected"] = overrides[k] > 0
            rw.at[i, "news_source"] = "events"
    return rw


# ------------------------------------------------------------------------------ Sleeper's projections as a lineup
def _json(v) -> object:
    import json
    return json.loads(v) if isinstance(v, str) else v


def market_rows(roster: pd.DataFrame, lines: pd.DataFrame, leagues: Mapping[str, dict], written_at=None, *,
                price: Callable[[pd.DataFrame, Mapping[str, float], bool], Mapping[str, float]]) -> list[dict]:
    """``ops.decision_market`` rows: per record roster-week of a league in ``leagues`` (league -> {scoring, slots}) with a
    Sleeper snapshot for its week, the best lineup of the record's roster at Sleeper's numbers (module block above).
    ``price(lines, scoring, ev)`` -> gsis -> points (``record_run.price_sleeper_lines``)."""
    from . import lineup as LU
    if roster.empty or lines is None or lines.empty:
        return []
    out = []
    by_week = {int(w): grp for w, grp in lines.groupby("week")}
    priced: dict[tuple[str, int, str], dict[str, float]] = {}
    for (lg, season, week, rid), grp in roster.groupby(["league_id", "season", "week", "roster_id"], sort=True):
        if lg not in leagues or int(week) not in by_week:
            continue
        pricing = str(grp["pricing"].dropna().iloc[0]) if grp["pricing"].notna().any() else "flat"
        key = (lg, int(week), pricing)
        if key not in priced:
            priced[key] = price(by_week[int(week)], leagues[lg]["scoring"], pricing == "ev")
        mkt = priced[key]
        fetched = by_week[int(week)]["fetched_at"].iloc[0]
        players, meta = [], {}
        for r in grp.drop_duplicates("sleeper_player_id").itertuples(index=False):
            sid = str(r.sleeper_player_id)
            if r.position == "DEF":
                v, src = _f(r.value), "ours"
            else:
                v = mkt.get(r.gsis_id) if isinstance(r.gsis_id, str) else None
                src = "sleeper" if v is not None else LU.UNVALUED
            meta[sid] = (r.gsis_id, r.player_name, r.position, v, src)
            players.append(LU.Player(id=sid, position=r.position, value=v, playable=r.role != "unplayable",
                                     value_source=src if v is not None else LU.UNVALUED, reason=r.reason if r.role == "unplayable" else None))
        lu = LU.solve(players, leagues[lg]["slots"], margins=False)
        for st in lu.starts:
            if st.player is None:
                continue
            g, nm, pos, v, src = meta[st.player.id]
            out.append({"league_id": lg, "season": int(season), "week": int(week), "roster_id": int(rid),
                        "slot": st.slot.label, "sleeper_player_id": st.player.id, "gsis_id": g, "player_name": nm,
                        "position": pos, "market_value": v, "value_source": src, "fetched_at": fetched,
                        "pricing": pricing, "written_at": written_at})
    return out


def market_points(market: pd.DataFrame | None, points) -> dict[tuple[str, int, int], tuple[float | None, int]]:
    """(league, week, roster) -> (Sleeper's lineup at the points scored, starters with no number)."""
    out: dict[tuple[str, int, int], tuple[float | None, int]] = {}
    if market is None or market.empty:
        return out
    for (lg, w, rid), grp in market.groupby(["league_id", "week", "roster_id"]):
        pts = [points(lg, int(w), r.sleeper_player_id, r.gsis_id) for r in grp.itertuples(index=False)]
        unknown = sum(p is None for p in pts)
        out[(str(lg), int(w), int(rid))] = (None if unknown else float(sum(pts)), unknown)
    return out


def market_sentence(tot: Mapping | None) -> str | None:
    if not tot or tot.get("market") is None:
        return None
    ww = _weeks_words(tot["market_weeks"])
    vs_ours = tot["market"] - tot["market_app"]
    vs_started = tot["market"] - tot["market_submitted"]
    return (f"{ww.capitalize()}: had every team started Sleeper's projections, the league would have scored "
            f"{tot['market']:.1f} — {abs(vs_ours):.1f} {'more' if vs_ours >= 0 else 'fewer'} than our lineups and "
            f"{abs(vs_started):.1f} {'more' if vs_started >= 0 else 'fewer'} than the ones started.")


# ------------------------------------------------------------------------------ one team
def _call_words(c: Mapping) -> str:
    """"Chris Olave over Xavier Worthy (we gave it 64%): 18.6 to 11.0 — the right call." """
    a, b = c.get("player_name") or "our starter", c.get("alt_player_name") or "the bench player"
    p = _f(c.get("p_win"))
    head = f"{a} over {b}" + (f" (we gave it {_pct(p)}%)" if p is not None else "")
    if c.get("outcome") is None:
        return f"{head}: not scored yet."
    pts = f"{_f(c['starter_points']):.1f} to {_f(c['alt_points']):.1f}"
    o = float(c["outcome"])
    return f"{head}: {pts} — " + ("the right call." if o == 1 else "a tie." if o == 0.5 else f"{b} scored more.")


def team_summary(rw: pd.DataFrame, calls: pd.DataFrame, roster_id: int, team_name: str | None = None) -> dict:
    """``decisions.team`` (INTERFACES.md § V-2): one roster's graded weeks (the league's filter: scored, every number
    known — so the teams' weeks add up to the league's), their sums, its close calls and how they landed, its
    news-affected weeks and the sentences."""
    rid = int(roster_id)
    t = rw[pd.to_numeric(rw["roster_id"]) == rid] if not rw.empty else rw
    g = t[(t["status"] == "scored") & t["submitted_points"].notna() & t["app_points"].notna() & t["optimum_points"].notna()] \
        if not t.empty else t
    c = calls[pd.to_numeric(calls["roster_id"]) == rid] if not calls.empty else calls
    weeks = []
    for r in g.sort_values("week").itertuples(index=False):
        wc = c[c["week"] == r.week].sort_values("call_rank") if not c.empty else c
        cl = [{"call_rank": int(x.call_rank), "slot": x.slot, "player_name": x.player_name, "alt_player_name": x.alt_player_name,
               "p_win": _f(x.p_win), "is_coin_flip": None if x.is_coin_flip is None or pd.isna(x.is_coin_flip) else bool(x.is_coin_flip),
               "starter_points": _f(x.starter_points), "alt_points": _f(x.alt_points), "outcome": _f(x.outcome)}
              for x in wc.itertuples(index=False)]
        for x in cl:
            x["words"] = _call_words(x)
        mp = _f(getattr(r, "market_points", None))
        weeks.append({"week": int(r.week), "record_source": r.record_source, "submitted": _r2(r.submitted_points),
                      "app": _r2(r.app_points), "optimum": _r2(r.optimum_points), "market": _r2(mp),
                      "edge": _r2(r.app_edge), "regret": _r2(r.regret), "market_edge": _r2(getattr(r, "market_edge", None)),
                      "n_changed": None if r.n_changed is None or pd.isna(r.n_changed) else int(r.n_changed),
                      "news": bool(r.is_news_affected), "news_source": getattr(r, "news_source", None) or "report",
                      "calls": cl})
    out: dict = {"roster_id": rid, "team_name": team_name, "available": bool(weeks), "weeks": weeks,
                 "season_totals": None, "calls": None, "news": None, "sentences": {"season": None, "market": None,
                                                                                     "calls": None, "news": None}}
    if not weeks:
        out["why"] = ("no week of yours is graded yet" if not t.empty else "this team has no lineup on the record")
        return out
    tot = {"weeks": len(weeks), **{k: _r2(sum(w[k] for w in weeks)) for k in ("submitted", "app", "optimum", "edge", "regret")}}
    mw = [w for w in weeks if w["market"] is not None]
    tot.update({"market": _r2(sum(w["market"] for w in mw)) if mw else None, "market_weeks": [w["week"] for w in mw],
                "market_edge": _r2(sum(w["market_edge"] for w in mw if w["market_edge"] is not None)) if mw else None})
    out["season_totals"] = tot
    graded = c[(c["status"] == "scored") & c["week"].isin([w["week"] for w in weeks])] if not c.empty else c
    cal = calibration(graded)
    out["calls"] = {k: cal[k] for k in ("n", "won", "expected", "brier", "coin_flips")}
    nw = [w for w in weeks if w["news"]]
    out["news"] = {"weeks": [w["week"] for w in nw], "edge": _r2(sum(w["edge"] for w in nw)) if nw else None}
    ww = _weeks_words([w["week"] for w in weeks])
    out["sentences"]["season"] = (f"{ww.capitalize()}: you started {tot['submitted']:.1f}; our lineup would have scored "
                                  f"{tot['app']:.1f}; the best possible was {tot['optimum']:.1f}.")
    if mw:
        out["sentences"]["market"] = (f"Sleeper's projections as a lineup would have scored {tot['market']:.1f} in "
                                      f"{_weeks_words(tot['market_weeks'])}.")
    allc = graded[graded["outcome"].notna()] if not graded.empty else graded
    if len(allc):
        won = float(allc["outcome"].sum())
        out["sentences"]["calls"] = (f"Our closest calls for you landed {won:g} of {len(allc)}"
                                     + (f" ({cal['expected']:.1f} expected)." if cal["expected"] is not None else "."))
    if nw:
        out["sentences"]["news"] = (f"Week{'s' if len(nw) != 1 else ''} {', '.join(str(w['week']) for w in nw)}: a starter's "
                                    f"injury status changed after our build ({_signed(out['news']['edge'])} there).")
    return out


# ------------------------------------------------------------------------------ MyFantasyLeague
def mfl_weekly(league_id: str, results: Mapping[int, Mapping], translate: Callable[[list[str]], Mapping[str, tuple]],
               rid_of: Mapping[str, int], scored_weeks: Iterable[int]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(the WEEKLY_SQL-shaped frame, the OPTIMUM_SQL-shaped frame) of an MFL league from its ``weeklyResults`` per week
    (``mfl_client.weekly_results``): each franchise once a week (a double header lists it twice with one lineup),
    every rostered player's score, MFL's ``opt_pts`` as the optimum. ``translate``: MFL ids -> (Sleeper id or
    ``mfl:<id>``, how) — the league's own translation, so the ids match the record's."""
    scored = {int(w) for w in scored_weeks}
    weekly, opt = [], []
    for week, res in sorted(results.items()):
        seen = set()
        franchises = []
        for m in _as_list((res or {}).get("matchup")) + [{"franchise": (res or {}).get("franchise")}]:
            franchises += _as_list(m.get("franchise"))
        ids = sorted({str(p.get("id")) for f in franchises for p in _as_list(f.get("player"))})
        tr = translate(ids) if ids else {}
        for f in franchises:
            fid = str(f.get("id"))
            if fid in seen or fid not in rid_of:
                continue
            seen.add(fid)
            rid = rid_of[fid]
            for p in _as_list(f.get("player")):
                sid = (tr.get(str(p.get("id"))) or (f"mfl:{p.get('id')}",))[0]
                weekly.append({"league_id": league_id, "week": int(week), "roster_id": rid, "sleeper_player_id": sid,
                               "gsis_id": None, "is_starter": str(p.get("status") or "").lower() == "starter",
                               # a listed player with no score did not score: MFL counts him 0
                               "points_observed": _f(p.get("score")) or 0.0, "is_scored_week": int(week) in scored})
            opt.append({"league_id": league_id, "week": int(week), "roster_id": rid, "optimum_points": _f(f.get("opt_pts"))})
    cols_w = ["league_id", "week", "roster_id", "sleeper_player_id", "gsis_id", "is_starter", "points_observed", "is_scored_week"]
    return pd.DataFrame(weekly, columns=cols_w), pd.DataFrame(opt, columns=["league_id", "week", "roster_id", "optimum_points"])


def _as_list(v) -> list:
    if v is None:
        return []
    return list(v) if isinstance(v, list) else [v]


def mfl_inputs(record: pd.DataFrame, weekly: pd.DataFrame, optimum: pd.DataFrame) -> GradeInputs:
    """The grade's inputs for an MFL league: no fallback scoring (a starter on no franchise is unknown), no final
    injury report (MFL weeks are graded without the news flag unless the event store answers)."""
    return GradeInputs(record, weekly, optimum, pd.DataFrame(columns=["league_id", "week", "gsis_id", "points"]),
                       pd.DataFrame(columns=["week", "gsis_id", "report_status", "roster_status"]), unknown_off_roster=True)
# ---- end V-2
