"""The grading harness for the week's win probability and the ranges (IL-3, Wave I-L; docs/METRICS.md § "Odds grades").

IH-3 calibrated the week's win probability once, by hand, on 2024–2025 and 2026 weeks 1–2. This module re-grades it
every night on the **decision record** (``ops.lineup_record``: the lineup the app proposed for every roster, frozen
before the week's first kickoff — ``kickoff`` — or rebuilt once from the frozen projections — ``reconstructed``), so the
number on My Week is graded on the rows it was shown from, week by week, as the season goes.

**Inputs** (read only, all frozen before kickoff except the outcomes):

* the record's starters per roster-week (Sleeper leagues; an MFL league's outcomes are MFL's and are not read here);
* each starter's range in the league's scoring from the frozen board (``ops.projections`` for the same league-week:
  ``proj_points``, P10 / P50 / P90, and P25 / P75 where the row carries them — the five-knot ranges from 2026 week 4);
  a starter with no range row (a DEF on the house path, a K before week 4) counts at his record value, as IH-3's line
  counts him;
* his NFL team and opponent that week (``analytics.league_player_week``) for the same-game correlations;
* the outcomes, only for scored weeks: the matchup's result (``analytics.fct_league_matchup``, ``is_scored``) and the
  starter's points in the league (``validation._points_lookup``: Sleeper's count; no stat row = 0, Sleeper's rule).

**The win probability graded** is the number My Week shows before kickoff: ``decisions.lineup_win_probability`` of the
roster's record lineup against its opponent's record lineup (the opponent's best lineup — IH-3's choice), every range
centred on the record value, calibrated (``shrink_week``). It is graded against the matchup's real result (the lineups
the managers submitted: the result a manager reads).

**Per league × week** (``scope = 'week'``) and **season to date** (``scope = 'to_date'``, per league and pooled as
``league_id = 'all'``, ``week`` = the last week graded):

* ``brier`` — mean (p − outcome)², one row per matchup (a tie = ½); a coin flip scores 0.25;
* ``log_loss`` — mean −[y ln p + (1 − y) ln(1 − p)], p clipped to [1e-6, 1 − 1e-6]; a coin flip scores ln 2 = 0.693;
* ``favourite_won`` — the share of matchups the side with p > 50 % won (a tie ½; p = 50 % exactly is left out), with
  ``detail.predicted`` the mean favourite's p;
* ``calibration`` (to date only) — ten fixed-width deciles of the predicted p (0–10 %, …, 90–100 %), **each matchup
  from both sides** (p and 1 − p), so the table is symmetric: per decile the count, the mean predicted and the observed
  rate in ``detail.deciles``; ``value`` = the count-weighted mean |predicted − observed| (the expected calibration
  error);
* ``coverage_80`` — the share of starters whose points fell inside P10–P90; ``coverage_50`` — inside P25–P75, **only
  the rows that carry P25 / P75** (``n`` says how many);
* ``mae_median`` per position (``detail.position``; one metric row per position as ``mae_median_<POS>``) — mean
  |P50 − points| (P50 is the range's median; a starter without a range: his record value); ``mae_projection_<POS>`` the
  same for the record value (the projection: the mean).

``n`` on every row is what it was measured on (matchups, starter rows). ``graded_at`` is the real time of the run (a
writer's stamp, not the league's clock). A week with no scored outcome is not graded (no row): never a zero.
"""

from __future__ import annotations

import json
import logging
import math
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from . import decisions as D
from . import validation as V

log = logging.getLogger(__name__)

GRADE_VERSION = "og1.0"
TABLE = "analytics.odds_grades"
DECILES = 10
EPS = 1e-6
POSITIONS = ("QB", "RB", "WR", "TE", "K", "DEF")
COLUMNS = ["league_id", "season", "week", "scope", "metric", "value", "n", "detail", "through_week", "grade_version",
           "graded_at"]
DDL = f"""create table if not exists {TABLE} (
    league_id text not null, season integer not null, week integer not null, scope text not null, metric text not null,
    value double precision, n integer, detail jsonb, through_week integer, grade_version text,
    graded_at timestamptz not null,
    primary key (league_id, season, week, scope, metric))"""

RECORD_SQL = """select league_id, season, week, roster_id, record_source, gsis_id, sleeper_player_id, player_name,
                       position, value, pricing
                from ops.lineup_record
                where season = %s and week <= %s and role = 'starter' and league_id not like 'mfl:%%'"""
RANGES_SQL = """select league_id, week, gsis_id, proj_points, p10, p25, p50, p75, p90
                from ops.projections where season = %s and week <= %s"""
TEAMS_SQL = """select league_id, week, gsis_id, sleeper_player_id, nfl_team as team, nfl_opponent as opponent
               from analytics.league_player_week where season = %s and week <= %s"""
MATCHUP_SQL = """select league_id, week, roster_id, opponent_roster_id, result
                 from analytics.fct_league_matchup
                 where season = %s and week <= %s and is_scored and opponent_roster_id is not null
                   and roster_id < opponent_roster_id and result is not null"""
BANDS = ("p10", "p25", "p50", "p75", "p90")


# ------------------------------------------------------------------------------ the scores (pure)
def outcome(result: str | None) -> float | None:
    """W / L / T → 1 / 0 / ½ (anything else: unknown)."""
    return {"W": 1.0, "L": 0.0, "T": 0.5}.get(str(result).upper()) if result is not None else None


def brier(p: Sequence[float], y: Sequence[float]) -> float:
    p, y = np.asarray(p, dtype=float), np.asarray(y, dtype=float)
    return float(np.mean((p - y) ** 2))


def log_loss(p: Sequence[float], y: Sequence[float]) -> float:
    p = np.clip(np.asarray(p, dtype=float), EPS, 1 - EPS)
    y = np.asarray(y, dtype=float)
    return float(np.mean(-(y * np.log(p) + (1 - y) * np.log(1 - p))))


def favourite(p: Sequence[float], y: Sequence[float]) -> tuple[float | None, float | None, int]:
    """(mean p of the favourite, the share the favourite won, matchups with a favourite): p = ½ exactly has none."""
    p, y = np.asarray(p, dtype=float), np.asarray(y, dtype=float)
    has = p != 0.5
    if not has.any():
        return None, None, 0
    fav = p[has] > 0.5
    pf = np.where(fav, p[has], 1 - p[has])
    won = np.where(fav, y[has], 1 - y[has])
    return float(pf.mean()), float(won.mean()), int(has.sum())


def calibration_deciles(p: Sequence[float], y: Sequence[float], both_sides: bool = True) -> tuple[list[dict], float | None]:
    """Ten fixed-width deciles of the predicted probability: [{decile, lo, hi, n, predicted, observed}] for the deciles
    that hold a prediction, and the count-weighted mean |predicted − observed| (None without rows). ``both_sides``:
    each pair also enters as (1 − p, 1 − y), the matchup seen from the other side."""
    p, y = np.asarray(p, dtype=float), np.asarray(y, dtype=float)
    if both_sides:
        p, y = np.concatenate([p, 1 - p]), np.concatenate([y, 1 - y])
    if not len(p):
        return [], None
    idx = np.minimum((p * DECILES).astype(int), DECILES - 1)
    out, err, n = [], 0.0, 0
    for k in range(DECILES):
        sel = idx == k
        if not sel.any():
            continue
        pr, ob = float(p[sel].mean()), float(y[sel].mean())
        out.append({"decile": k + 1, "lo": k / DECILES, "hi": (k + 1) / DECILES, "n": int(sel.sum()),
                    "predicted": round(pr, 4), "observed": round(ob, 4)})
        err += sel.sum() * abs(pr - ob)
        n += int(sel.sum())
    return out, float(err / n)


def coverage(actual: Sequence[float], lo: Sequence[float], hi: Sequence[float]) -> tuple[float | None, int]:
    """The share of rows with ``lo`` <= actual <= ``hi`` among the rows that carry both bounds and an actual."""
    a, lo, hi = (np.asarray(x, dtype=float) for x in (actual, lo, hi))
    ok = np.isfinite(a) & np.isfinite(lo) & np.isfinite(hi)
    if not ok.any():
        return None, 0
    return float(((a[ok] >= lo[ok]) & (a[ok] <= hi[ok])).mean()), int(ok.sum())


def _row(league_id, season, week, scope, metric, value, n, detail=None, through=None) -> dict:
    return {"league_id": str(league_id), "season": int(season), "week": int(week), "scope": scope, "metric": metric,
            "value": None if value is None or (isinstance(value, float) and math.isnan(value)) else float(value),
            "n": int(n), "detail": detail, "through_week": through}


def _odds_rows(m: pd.DataFrame, league_id, season, week, scope, through) -> list[dict]:
    if m.empty:
        return []
    p, y = m["p"].to_numpy(dtype=float), m["outcome"].to_numpy(dtype=float)
    out = [_row(league_id, season, week, scope, "brier", brier(p, y), len(m), through=through),
           _row(league_id, season, week, scope, "log_loss", log_loss(p, y), len(m), through=through)]
    pf, won, nf = favourite(p, y)
    if nf:
        out.append(_row(league_id, season, week, scope, "favourite_won", won, nf, {"predicted": round(pf, 4)}, through))
    if scope == "to_date":
        table, ece = calibration_deciles(p, y)
        out.append(_row(league_id, season, week, scope, "calibration", ece, 2 * len(m), {"deciles": table}, through))
    return out


def _range_rows(s: pd.DataFrame, league_id, season, week, scope, through) -> list[dict]:
    s = s[s["actual"].notna()]
    if s.empty:
        return []
    out = []
    for metric, lo, hi in (("coverage_80", "p10", "p90"), ("coverage_50", "p25", "p75")):
        c, n = coverage(s["actual"], s[lo], s[hi])
        if n:
            out.append(_row(league_id, season, week, scope, metric, c, n, through=through))
    for pos in POSITIONS:
        g = s[s["position"] == pos]
        if g.empty:
            continue
        med = g["p50"].where(g["p50"].notna(), g["value"]).astype(float)
        ok = med.notna()
        if ok.any():
            out.append(_row(league_id, season, week, scope, f"mae_median_{pos}",
                            float((med[ok] - g.loc[ok, "actual"]).abs().mean()), int(ok.sum()), {"position": pos}, through))
        ok = g["value"].notna()
        if ok.any():
            out.append(_row(league_id, season, week, scope, f"mae_projection_{pos}",
                            float((g.loc[ok, "value"].astype(float) - g.loc[ok, "actual"]).abs().mean()), int(ok.sum()),
                            {"position": pos}, through))
    return out


def grade_rows(matchups: pd.DataFrame, starters: pd.DataFrame, season: int) -> pd.DataFrame:
    """The grade table (``COLUMNS`` without the stamps) from the graded inputs:

    * ``matchups``: one row per scored matchup — ``league_id``, ``week``, ``p`` (the first roster's win probability),
      ``outcome`` (1 / ½ / 0 for the first roster);
    * ``starters``: one row per record starter in a scored week — ``league_id``, ``week``, ``position``, ``value``,
      ``p10`` … ``p90`` (NaN where none), ``actual`` (his points; NaN = unknown, left out).

    Per league × week, then to date per league and pooled (``league_id = 'all'``). Empty inputs: an empty frame."""
    rows: list[dict] = []
    m = matchups[matchups["p"].notna() & matchups["outcome"].notna()] if not matchups.empty else matchups
    weeks = sorted({(str(lg), int(w)) for lg, w in pd.concat([m[["league_id", "week"]],
                                                               starters[["league_id", "week"]]]).itertuples(index=False)}) \
        if not (m.empty and starters.empty) else []
    if not weeks:
        return pd.DataFrame(columns=COLUMNS[:-2])
    through = max(w for _, w in weeks)
    for lg, w in weeks:
        rows += _odds_rows(m[(m["league_id"].astype(str) == lg) & (m["week"] == w)], lg, season, w, "week", w)
        rows += _range_rows(starters[(starters["league_id"].astype(str) == lg) & (starters["week"] == w)], lg, season, w,
                            "week", w)
    for lg in sorted({lg for lg, _ in weeks}):
        last = max(w for x, w in weeks if x == lg)
        rows += _odds_rows(m[m["league_id"].astype(str) == lg], lg, season, last, "to_date", last)
        rows += _range_rows(starters[starters["league_id"].astype(str) == lg], lg, season, last, "to_date", last)
    rows += _odds_rows(m, "all", season, through, "to_date", through)
    rows += _range_rows(starters, "all", season, through, "to_date", through)
    return pd.DataFrame(rows, columns=COLUMNS[:-2])


# ------------------------------------------------------------------------------ the inputs (the database)
def load(query: Callable[[str, tuple], pd.DataFrame], season: int, through: int) -> dict[str, pd.DataFrame]:
    """The frames ``build_inputs`` reads, through ``query(sql, params)`` (``validation.frame_query(conn)``)."""
    rec = query(RECORD_SQL, (season, through))
    ids = sorted(rec["league_id"].astype(str).unique()) if not rec.empty else []
    return {"record": rec,
            "ranges": query(RANGES_SQL, (season, through)),
            "teams": query(TEAMS_SQL, (season, through)),
            "matchups": query(MATCHUP_SQL, (season, through)),
            "weekly": query(V.WEEKLY_SQL, (season, ids)) if ids else pd.DataFrame(columns=["league_id", "week", "roster_id", "sleeper_player_id", "gsis_id", "is_starter", "points_observed", "is_scored_week"]),
            "fallback": query(V.FALLBACK_SQL, (season, ids)) if ids else pd.DataFrame(columns=["league_id", "week", "gsis_id", "points"])}


def _num(v) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) else x


def build_inputs(f: Mapping[str, pd.DataFrame], *, draws: int = D.WEEK_DRAWS) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(matchups with ``p`` and ``outcome``, starters with their range and ``actual``) for the scored weeks of the
    record (``grade_rows``' inputs). A scored week = Sleeper scored it (``league_player_week.is_scored_week``)."""
    rec = f["record"]
    if rec.empty:
        return (pd.DataFrame(columns=["league_id", "week", "roster_id", "opponent_roster_id", "p", "outcome"]),
                pd.DataFrame(columns=["league_id", "week", "roster_id", "position", "value", *BANDS, "actual"]))
    rec = rec.assign(league_id=rec["league_id"].astype(str), week=rec["week"].astype(int), roster_id=rec["roster_id"].astype(int))
    rng = f["ranges"].assign(league_id=lambda d: d["league_id"].astype(str), week=lambda d: d["week"].astype(int))
    rng = rng.drop_duplicates(["league_id", "week", "gsis_id"])
    st = rec.merge(rng[["league_id", "week", "gsis_id", *BANDS]], on=["league_id", "week", "gsis_id"], how="left")
    tm = f["teams"].assign(league_id=lambda d: d["league_id"].astype(str), week=lambda d: d["week"].astype(int))
    by_gsis = tm.dropna(subset=["gsis_id"]).drop_duplicates(["league_id", "week", "gsis_id"]).set_index(["league_id", "week", "gsis_id"])
    by_sid = tm.dropna(subset=["sleeper_player_id"]).drop_duplicates(["league_id", "week", "sleeper_player_id"]).set_index(
        ["league_id", "week", "sleeper_player_id"])
    team, opp = [], []
    for r in st.itertuples(index=False):
        hit = None
        if isinstance(r.gsis_id, str) and (r.league_id, r.week, r.gsis_id) in by_gsis.index:
            hit = by_gsis.loc[(r.league_id, r.week, r.gsis_id)]
        elif r.sleeper_player_id is not None and (r.league_id, r.week, str(r.sleeper_player_id)) in by_sid.index:
            hit = by_sid.loc[(r.league_id, r.week, str(r.sleeper_player_id))]
        team.append(None if hit is None else hit["team"])
        opp.append(None if hit is None else hit["opponent"])
    st = st.assign(team=team, opponent=opp)
    scored = V._scored_weeks(f["weekly"])
    points = V._points_lookup(f["weekly"], f["fallback"])
    st = st[[(lg, w) in scored for lg, w in zip(st["league_id"], st["week"], strict=True)]].reset_index(drop=True)
    st["actual"] = [points(r.league_id, r.week, r.sleeper_player_id, r.gsis_id) for r in st.itertuples(index=False)]
    st["actual"] = pd.to_numeric(st["actual"], errors="coerce")
    for b in (*BANDS, "value"):
        st[b] = pd.to_numeric(st[b], errors="coerce")

    def side(lg: str, w: int, roster: int) -> list[dict]:
        g = st[(st["league_id"] == lg) & (st["week"] == w) & (st["roster_id"] == roster)]
        out = []
        for r in g.itertuples(index=False):
            key = r.gsis_id if isinstance(r.gsis_id, str) and r.gsis_id else (str(r.sleeper_player_id) if r.sleeper_player_id else None)
            out.append({"key": key, "position": r.position, "team": r.team, "opponent": r.opponent, "value": _num(r.value),
                        **{b: _num(getattr(r, b)) for b in BANDS}})
        return out

    mt = f["matchups"]
    res = []
    for r in mt.itertuples(index=False):
        lg, w = str(r.league_id), int(r.week)
        if (lg, w) not in scored:
            continue
        a, b = side(lg, w, int(r.roster_id)), side(lg, w, int(r.opponent_roster_id))
        if not a or not b:
            continue
        wp = D.lineup_win_probability(a, b, n=draws)
        res.append({"league_id": lg, "week": w, "roster_id": int(r.roster_id), "opponent_roster_id": int(r.opponent_roster_id),
                    "p": wp["p"], "outcome": outcome(r.result), "mine": wp["mine"], "theirs": wp["theirs"]})
    return pd.DataFrame(res, columns=["league_id", "week", "roster_id", "opponent_roster_id", "p", "outcome", "mine", "theirs"]), st


# ------------------------------------------------------------------------------ the writer and the CLI's entry
def latest_scored_week(query: Callable[[str, tuple], pd.DataFrame], season: int) -> int | None:
    df = query("select max(week) as w from analytics.league_player_week where season = %s and is_scored_week", (season,))
    return None if df.empty or pd.isna(df["w"].iloc[0]) else int(df["w"].iloc[0])


def write(conn, season: int, grades: pd.DataFrame, graded_at: datetime | None = None) -> int:
    """Replace the season's rows of ``analytics.odds_grades`` with ``grades`` (one transaction). Returns rows written."""
    at = graded_at or datetime.now(UTC)          # a writer's stamp: the real time of the run, never the league's clock
    with conn.cursor() as cur:
        cur.execute(DDL)
        if _role_exists(cur, "league_lab_app"):          # the API's read-only role (the hosted copy's grants are the sync's)
            cur.execute(f"grant select on {TABLE} to league_lab_app")
        cur.execute(f"delete from {TABLE} where season = %s", (season,))
        if not grades.empty:
            with cur.copy(f"copy {TABLE} ({', '.join(COLUMNS)}) from stdin") as cp:
                for r in grades.itertuples(index=False):
                    cp.write_row([r.league_id, r.season, r.week, r.scope, r.metric, r.value, r.n,
                                  None if r.detail is None else json.dumps(r.detail), r.through_week, GRADE_VERSION, at])
    conn.commit()
    return len(grades)


def _role_exists(cur, role: str) -> bool:
    cur.execute("select 1 from pg_roles where rolname = %s", (role,))
    return cur.fetchone() is not None


def run(season: int | None = None, through: int | None = None, write_rows: bool = True,
        draws: int = D.WEEK_DRAWS) -> tuple[pd.DataFrame, pd.DataFrame]:
    """``league-lab grade-odds``: grade the record of ``season`` through week ``through`` (default: the newest season on
    the record, through its newest scored week), write ``analytics.odds_grades`` and return (grades, matchups)."""
    import psycopg

    from .config import get_settings

    with psycopg.connect(get_settings().pipeline_dsn(), autocommit=False) as conn:
        q = V.frame_query(conn)
        if season is None:
            s = q("select max(season) as s from ops.lineup_record", ())
            season = None if s.empty or pd.isna(s.iloc[0]["s"]) else int(s.iloc[0]["s"])
        if season is None:
            log.warning("grade-odds: the decision record is empty")
            return pd.DataFrame(columns=COLUMNS), pd.DataFrame()
        if through is None:
            through = latest_scored_week(q, season)
        if through is None:
            log.warning("grade-odds: no scored week in %s yet", season)
            conn.rollback()
            return pd.DataFrame(columns=COLUMNS), pd.DataFrame()
        frames = load(q, season, through)
        conn.rollback()
        matchups, starters = build_inputs(frames, draws=draws)
        grades = grade_rows(matchups, starters, season)
        if write_rows:
            n = write(conn, season, grades)
            log.info("%s: %s rows for %s through week %s (%s matchups, %s starter rows)", TABLE, n, season, through,
                     len(matchups), int(starters["actual"].notna().sum()) if not starters.empty else 0)
    return grades, matchups


def status(query: Callable[..., pd.DataFrame]) -> dict | None:
    """``/api/status`` ``odds_grades``: the newest season-to-date pooled row set — {season, through_week, brier,
    coverage_50, coverage_80, graded_at}; None when the table does not exist or holds nothing."""
    t = query("select to_regclass(%s) as t", (TABLE,))
    if t.empty or t["t"].iloc[0] is None or pd.isna(t["t"].iloc[0]):
        return None
    df = query(f"""select season, week, metric, value, n, graded_at from {TABLE}
                   where scope = 'to_date' and league_id = 'all'
                     and (season, week) = (select season, max(week) from {TABLE}
                                           where scope = 'to_date' and league_id = 'all'
                                             and season = (select max(season) from {TABLE}) group by season)""")
    if df.empty:
        return None
    v = {r.metric: (None if pd.isna(r.value) else round(float(r.value), 4)) for r in df.itertuples(index=False)}
    at = pd.Timestamp(df["graded_at"].max())
    at = at.tz_localize("UTC") if at.tzinfo is None else at.tz_convert("UTC")
    return {"season": int(df["season"].iloc[0]), "through_week": int(df["week"].iloc[0]), "brier": v.get("brier"),
            "coverage_50": v.get("coverage_50"), "coverage_80": v.get("coverage_80"), "graded_at": at.isoformat()}
