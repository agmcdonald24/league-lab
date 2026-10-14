"""IZ-1 (Wave I-Z): us against Sleeper on the weeks Sleeper still serves — hh1.0 and the blend bl1.0 (docs/METRICS.md
§ "Us against Sleeper on the weeks Sleeper still serves", the rule committed before any number).

* ``build_ours`` -> ``ops.h2h_ours``: the live model (``projections.MODEL_VERSION``) run on 2023-2025, each season
  fitted only on the seasons before it, with every step the live board applies to next week's line (pt1.0 on the QB
  line; the cold-start and WR new-team scales fitted on the model's own out-of-sample rows of the three seasons before),
  priced in each house league's scoring. Built once per model version (``ensure_ours``); the fallback is
  ``ops.calibration_oof`` (the component projection before those steps), labelled so on every surface.
* ``grade`` -> ``ops.sleeper_h2h``: by position (error, order, top-N hit rate; ours − Sleeper per week, pooled, a 95%
  interval by resampling weeks), start / sit (the close calls the two disagree on; all startable pairs), the verdict
  words, and the blend measured on 2024 and 2025 (never shipped).
* ``summary_text`` -> the nightly's one table (``league-lab h2h --md logs/sleeper_h2h.md``).

Sleeper's rows are ``ops.sleeper_history`` (``ingest.sleeper_history``: served after the week, never the record's
input), priced with ``scoring.compute_points`` (the record's flat pricing), matched by id only.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd
import psycopg

log = logging.getLogger(__name__)

RULE = "hh1.0"
BLEND_RULE = "bl1.0"
POSITIONS = ("QB", "RB", "WR", "TE")
TOP_N = {"QB": 12, "RB": 24, "WR": 36, "TE": 12}          # the record's hit-rate N
STARTABLE = {"QB": 24, "RB": 48, "WR": 60, "TE": 24}      # startable by either projection
CLOSE_POINTS = 3.0
MIN_PLAYERS = 8
DRAWS = 2000
SEED = 20261011
W_GRID = tuple(round(0.05 * i, 2) for i in range(21))
BLEND_TESTS = ((2024, (2023,)), (2025, (2023, 2024)))
BLEND_MIN_GAIN = 0.01         # the blend's error at least 1% below ours alone ...
BLEND_MAX_ORDER_LOSS = 0.002  # ... and its order no more than 0.002 below
HISTORY_SEASONS = (2023, 2024, 2025)

OURS_TABLE = "ops.h2h_ours"
GRADE_TABLE = "ops.sleeper_h2h"
OURS_DDL = f"""create table if not exists {OURS_TABLE} (
    gsis_id text, season integer, week integer, position text, league_id text, proj_points double precision,
    actual double precision, model_version text, train_seasons text, built_at timestamptz)"""
GRADE_COLUMNS: list[tuple[str, str]] = [
    ("league_id", "text"), ("league_name", "text"), ("headline", "boolean"), ("kind", "text"), ("position", "text"),
    ("season", "integer"),            # NULL = pooled over every graded week
    ("measure", "text"), ("n_weeks", "integer"), ("n_rows", "integer"),
    ("ours", "double precision"), ("sleeper", "double precision"), ("blend", "double precision"),
    ("diff", "double precision"), ("diff_lo", "double precision"), ("diff_hi", "double precision"),
    ("verdict", "text"), ("w", "double precision"), ("seasons", "text"), ("ours_source", "text"), ("ours_version", "text"),
    ("rule", "text"), ("built_at", "timestamptz"),
]
GRADE_DDL = f"create table if not exists {GRADE_TABLE} ({', '.join(f'{c} {t}' for c, t in GRADE_COLUMNS)})"

SOURCE_WORDS = {
    "live_walk_forward": "our live model ({v}) re-run on each past season, fitted only on the seasons before it",
    "stored_walk_forward": "our model re-run on past seasons, before the live board's adjustments ({v})",
    "kickoff_board": "our board as published before kickoff",
}
CAVEAT = ("Sleeper's numbers for past weeks are the ones its site serves now, written after the games, so this favours "
          "Sleeper; the record above, from week 5 of 2026, compares numbers saved before kickoff.")


def ensure_tables(conn: psycopg.Connection) -> None:
    # ---- JB-1: gp1.0's table (ops.sleeper_h2h_gap)
    from . import h2h_gap

    with conn.cursor() as cur:
        cur.execute(OURS_DDL)
        cur.execute(GRADE_DDL)
    conn.commit()
    h2h_gap.ensure_tables(conn)


# ------------------------------------------------------------------------------ ours: the live model, walk-forward
def _priced_rows(line: pd.DataFrame, target: pd.DataFrame, leagues: Mapping[str, tuple[str, dict[str, float]]],
                 prefix: str = "proj_", keep_lines: bool = False) -> pd.DataFrame:
    """One row per house league x player-week of ``line`` (gsis_id, week, position, proj_*): the line priced in the
    league's scoring and the league's actual points (the outcome columns priced; NaN when he did not play)."""
    from . import projections as P

    keys = ["gsis_id", "week"]
    tgt = target.drop_duplicates(keys)
    rows = line[[*keys, "position", *[f"{prefix}{c}" for c in P.ALL_COMPONENTS]]].merge(
        tgt[[*keys, "season", "played", *[f"out_{c}" for c in P.ALL_COMPONENTS]]], on=keys, how="left", validate="one_to_one")
    ok = rows[[f"out_{c}" for c in P.ALL_COMPONENTS]].notna().all(axis=1) & rows["played"].fillna(False).astype(bool)
    out = []
    for lid, (_name, scoring) in leagues.items():
        o = rows[["gsis_id", "season", "week", "position"]].copy()
        if keep_lines:      # ---- JB-1: the stat line and the outcome, for gp1.0's by-component family
            for c in P.ALL_COMPONENTS:
                o[f"proj_{c}"] = rows[f"{prefix}{c}"].to_numpy(dtype=float)
                o[f"out_{c}"] = rows[f"out_{c}"].to_numpy(dtype=float)
        o["league_id"] = lid
        o["proj_points"] = P.price(rows, scoring, prefix).to_numpy(dtype=float)
        act = pd.Series(np.nan, index=rows.index)
        if ok.any():
            act[ok] = P.price(rows[ok], scoring, "out_").to_numpy(dtype=float)
        o["actual"] = act.to_numpy()
        out.append(o)
    return pd.concat(out, ignore_index=True)


def build_ours(conn: psycopg.Connection, seasons: Iterable[int] = HISTORY_SEASONS, keep_lines: bool = False) -> pd.DataFrame:
    """The live model's walk-forward next-week rows of ``seasons`` (played rows with an actual), every house scoring.

    Per season S: the production models fitted on 2016 .. S-1 (``fit_position``, one reference scoring for the ranges:
    the line does not depend on it), predicted on S as of each week; then ``pass_td_lines`` and ``blend_lines`` (the
    cold-start and new-team scales read the out-of-sample rows of the three seasons before S: the component rows of
    those seasons, computed here — seasons before the first graded one by ``oof_rows``, later ones from this loop —
    never ``ops.calibration_oof``, which holds only the newest three). ``future_inputs`` and ``horizon_blend_lines``
    change only weeks after the market week: not next week's line, so not here."""
    from . import calibration as cal
    from . import projections as P

    t0 = time.time()
    leagues = P.league_scorings(conn)
    references = P.reference_scorings(conn)
    alls = P.available_seasons(conn)
    first = min(alls)
    seasons = sorted(s for s in seasons if s in alls and s < max(alls))
    if not seasons:
        return pd.DataFrame()
    window = [s for s in range(min(seasons) - cal.WINDOW, min(seasons)) if s > first]
    frame = P.load_frame(conn, [s for s in alls if s <= max(seasons)])
    ref = next(iter(references))
    fit = {ref: references[ref]}
    raw = cal.oof_rows(frame, window, leagues, first, ranges=False) if window else pd.DataFrame()
    raw = raw[raw["actual"].notna()][["gsis_id", "season", "week", "position", "league_id", "proj_points", "actual"]] \
        if len(raw) else pd.DataFrame(columns=["gsis_id", "season", "week", "position", "league_id", "proj_points", "actual"])
    log.info("h2h ours: window rows %s (%s) in %.0f s", len(raw), window, time.time() - t0)
    out = []
    real_load = cal.load_oof
    for s in seasons:
        ts = time.time()
        train = frame[frame["season"] < s]
        target = frame[frame["season"] == s]
        models, preds = {}, []
        for pos in P.POSITIONS:
            models[pos] = m = P.fit_position(train, pos, fit)
            preds.append(P.predict_position(m, target[target["position"] == pos], fit))
        every = pd.concat(preds, ignore_index=True)
        every["model_version"], every["fitted_at"], every["train_seasons"] = P.MODEL_VERSION, datetime.now(UTC), f"{first}-{s - 1}"
        before = _priced_rows(every[every["league_id"] == ref], target, leagues)
        every = cal.pass_td_lines(s, every, models, target, train, fit)
        hist = raw.copy()

        def _oof(_conn, before_season, _h=hist):
            return _h[_h["season"] < before_season].astype({"proj_points": float, "actual": float})

        cal.load_oof = _oof            # the scales read the rows of the seasons before s computed here
        try:
            every = cal.blend_lines(conn, s, every, models, target, fit, leagues)
            # ---- JB-1: gp1.0's C2 / C3 when LEAGUE_LAB_GP_FIX says so; else ``every`` itself
            from . import gp_fix
            every = gp_fix.apply(conn, s, every, models, target, frame, fit, leagues)
        finally:
            cal.load_oof = real_load
        rows = _priced_rows(every[every["league_id"] == ref], target, leagues, keep_lines=keep_lines)
        rows = rows[rows["actual"].notna()].copy()
        rows["train_seasons"] = f"{first}-{s - 1}"
        out.append(rows)
        raw = pd.concat([raw, before[before["actual"].notna()]], ignore_index=True)
        keys = ["league_id", "gsis_id", "week"]
        moved = rows[keys + ["proj_points"]].merge(before[keys + ["proj_points"]], on=keys, suffixes=("", "_raw"))
        log.info("h2h ours: season %s: %s rows (%s player-week-scorings moved by the steps) in %.0f s", s, len(rows),
                 int((np.abs(moved["proj_points"] - moved["proj_points_raw"]) > 1e-9).sum()), time.time() - ts)
    res = pd.concat(out, ignore_index=True)
    res["model_version"], res["built_at"] = P.MODEL_VERSION, datetime.now(UTC)
    log.info("h2h ours: %s rows in %.0f s", len(res), time.time() - t0)
    return res


def write_ours(conn: psycopg.Connection, rows: pd.DataFrame) -> int:
    cols = ["gsis_id", "season", "week", "position", "league_id", "proj_points", "actual", "model_version", "train_seasons",
            "built_at"]
    with conn.cursor() as cur:
        cur.execute(OURS_DDL)
        cur.execute(f"truncate {OURS_TABLE}")
        with cur.copy(f"copy {OURS_TABLE} ({', '.join(cols)}) from stdin") as cp:
            for rec in rows[cols].itertuples(index=False):
                cp.write_row([None if (isinstance(v, float) and np.isnan(v)) else v for v in rec])
    conn.commit()
    return len(rows)


def ours_current(conn: psycopg.Connection) -> bool:
    from . import projections as P

    with conn.cursor() as cur:
        cur.execute(f"select distinct season, model_version from {OURS_TABLE}")
        held = cur.fetchall()
    return {int(s) for s, _ in held} == set(HISTORY_SEASONS) and {m for _, m in held} == {P.MODEL_VERSION}


def ensure_ours(conn: psycopg.Connection) -> str:
    """Build ``ops.h2h_ours`` when it does not hold 2023-2025 of the live model version (once per version). A failure
    is logged and the grade falls back to the stored rows (labelled)."""
    from . import projections as P

    ensure_tables(conn)
    if ours_current(conn):
        return f"the live model ({P.MODEL_VERSION}) re-run on each season: kept from an earlier night"
    t0 = time.time()
    try:
        n = write_ours(conn, build_ours(conn))
    except Exception as exc:  # noqa: BLE001 - the grade falls back to ops.calibration_oof, labelled
        conn.rollback()
        log.exception("h2h ours: the live model's rows could not be built: %s", exc)
        return f"the live model's rows could NOT be built ({type(exc).__name__}): graded on the stored rows, labelled"
    return f"the live model ({P.MODEL_VERSION}) re-run on each season: built tonight ({n:,} rows in {time.time() - t0:.0f} s)"


# ------------------------------------------------------------------------------ the inputs
@dataclass
class Inputs:
    pop: pd.DataFrame                 # league_id, season, week, position, gsis_id, ours, sleeper, actual, ours_source, ours_version
    leagues: dict[str, str]           # league_id -> name, headline first
    counts: dict[str, Any]            # the pull's and the match's counts


def _q(conn: psycopg.Connection, sql: str, params: tuple = ()) -> pd.DataFrame:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])


def _exists(conn: psycopg.Connection, rel: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("select to_regclass(%s) is not null", (rel,))
        return bool(cur.fetchone()[0])


def price_sleeper(hist: pd.DataFrame, scoring: Mapping[str, float]) -> np.ndarray:
    """Sleeper's history lines (the weekly-stats columns) priced in a league's scoring (``compute_points``: the
    record's flat pricing; the position rides along for a position premium)."""
    from .ingest.sleeper_projections import LINE_COLUMNS
    from .scoring import compute_points

    cols = [c for c in LINE_COLUMNS if c in hist.columns]
    recs = hist[[*cols, "position"]].to_dict("records")
    out = np.empty(len(recs))
    for i, r in enumerate(recs):
        stats = {k: (None if (v is None or (isinstance(v, float) and np.isnan(v))) else float(v)) if k != "position" else v
                 for k, v in r.items()}
        out[i] = compute_points(stats, scoring)
    return np.round(out, 2)


def load_inputs(conn: psycopg.Connection) -> Inputs:
    from . import projections as P

    leagues = P.league_scorings(conn)
    names = {lid: name for lid, (name, _) in leagues.items()}
    counts: dict[str, Any] = {}
    hist = _q(conn, "select * from ops.sleeper_history where position = any(%s)", (list(POSITIONS),)) \
        if _exists(conn, "ops.sleeper_history") else pd.DataFrame()
    allh = _q(conn, "select position, count(*) as n from ops.sleeper_history group by 1") \
        if _exists(conn, "ops.sleeper_history") else pd.DataFrame(columns=["position", "n"])
    counts["lines_by_position"] = {str(r.position): int(r.n) for r in allh.itertuples()}
    if hist.empty:
        return Inputs(pd.DataFrame(), names, {**counts, "lines": 0, "matched": 0})
    idmap = _q(conn, "select sleeper_id, gsis_id from analytics.player_id_map where sleeper_id is not null")
    idmap = idmap[~idmap["sleeper_id"].duplicated(keep=False)]
    hist = hist.merge(idmap, left_on="player_id", right_on="sleeper_id", how="left")
    counts["lines"] = len(hist)
    counts["matched"] = int(hist["gsis_id"].notna().sum())
    counts["unmatched_ids"] = sorted(hist.loc[hist["gsis_id"].isna(), "player_id"].astype(str).unique().tolist())[:20]
    hist = hist[hist["gsis_id"].notna()]
    for c in hist.columns:
        if c not in ("player_id", "position", "team", "opponent", "company", "served", "gsis_id", "sleeper_id", "season",
                     "week", "updated_at", "fetched_at"):
            hist[c] = pd.to_numeric(hist[c], errors="coerce")
    sl = []
    for lid, (_name, scoring) in leagues.items():
        o = hist[["season", "week", "gsis_id", "position"]].copy()
        o["league_id"] = lid
        o["sleeper"] = price_sleeper(hist, scoring)
        sl.append(o)
    sl = pd.concat(sl, ignore_index=True)

    # ours, 2023-2025: the live model's rows when they are this version's, else the stored component rows (labelled)
    ours, src, ver = pd.DataFrame(), None, None
    if _exists(conn, OURS_TABLE):
        o = _q(conn, f"select gsis_id, season, week, position, league_id, proj_points, actual, model_version from {OURS_TABLE} "
                     "where model_version = %s", (P.MODEL_VERSION,))
        if not o.empty:
            ours, src, ver = o, "live_walk_forward", P.MODEL_VERSION
    if ours.empty and _exists(conn, "ops.calibration_oof"):
        o = _q(conn, "select gsis_id, season, week, position, league_id, proj_points, actual, model_version "
                     "from ops.calibration_oof where season = any(%s)", (list(HISTORY_SEASONS),))
        if not o.empty:
            ours, src = o, "stored_walk_forward"
            ver = ", ".join(sorted({str(v) for v in o["model_version"].dropna()})) or "unknown version"
    if not ours.empty:
        ours = ours.assign(ours_source=src, ours_version=ver)
    # ours, the current season: the board frozen at the first kickoff (flat-priced weeks), actual from the mart
    cur_season = int(hist["season"].max())
    kb = pd.DataFrame()
    if cur_season not in HISTORY_SEASONS and _exists(conn, "analytics.mart_player_week_projections"):
        kb = _q(conn, """
            select p.gsis_id, p.season, p.week, p.position, p.league_id, p.proj_points, m.points_actual as actual,
                   p.model_version, coalesce(p.pricing, 'flat') as pricing
            from ops.projections as p
            join analytics.mart_player_week_projections as m
              on m.league_id = p.league_id and m.season = p.season and m.week = p.week and m.gsis_id = p.gsis_id
            where p.season = %s and p.frozen_source = 'kickoff' and p.position = any(%s)
              and m.played and m.is_rankable and m.points_actual is not null""", (cur_season, list(POSITIONS)))
        if not kb.empty:
            counts["kickoff_weeks_ev_left_out"] = sorted(kb.loc[kb["pricing"] != "flat", "week"].unique().tolist())
            kb = kb[kb["pricing"] == "flat"].drop(columns="pricing")
            kb = kb.assign(ours_source="kickoff_board", ours_version=kb["model_version"].astype(str))
    ours = pd.concat([x for x in (ours, kb) if not x.empty], ignore_index=True) if (not ours.empty or not kb.empty) else pd.DataFrame()
    if ours.empty:
        return Inputs(pd.DataFrame(), names, counts)
    ours = ours.rename(columns={"proj_points": "ours"})
    ours["ours"] = pd.to_numeric(ours["ours"], errors="coerce").round(2)
    ours["actual"] = pd.to_numeric(ours["actual"], errors="coerce")
    ours["season"], ours["week"] = ours["season"].astype(int), ours["week"].astype(int)
    sl["season"], sl["week"] = sl["season"].astype(int), sl["week"].astype(int)
    pop = ours.merge(sl.drop(columns="position"), on=["league_id", "season", "week", "gsis_id"], how="inner")
    pop = pop[pop["ours"].notna() & pop["sleeper"].notna() & pop["actual"].notna() & pop["league_id"].isin(names)]
    counts["sleeper_weeks"] = sorted({(int(s), int(w)) for s, w in sl[["season", "week"]].itertuples(index=False)})
    return Inputs(pop.reset_index(drop=True), names, counts)


# ------------------------------------------------------------------------------ the measures
def _avg_rank(x: np.ndarray) -> np.ndarray:
    return pd.Series(x).rank(method="average").to_numpy()


def spearman(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) < MIN_PLAYERS:
        return np.nan
    ra, rb = _avg_rank(a), _avg_rank(b)
    if ra.std() == 0 or rb.std() == 0:
        return np.nan
    return float(np.corrcoef(ra, rb)[0, 1])


def hit_rate(proj: np.ndarray, actual: np.ndarray, ids: np.ndarray, n: int) -> float:
    """|top n by projection ∩ top n by actual| / min(n, players); ties broken by id (the mart's row_number)."""
    if len(proj) < MIN_PLAYERS:
        return np.nan
    order_p = np.lexsort((ids, -proj))[:n]
    order_a = np.lexsort((ids, -actual))[:n]
    return len(set(order_p) & set(order_a)) / min(n, len(proj))


def startable_mask(ours: np.ndarray, sleeper: np.ndarray, ids: np.ndarray, n: int) -> np.ndarray:
    k = np.zeros(len(ours), dtype=bool)
    k[np.lexsort((ids, -ours))[:n]] = True
    k[np.lexsort((ids, -sleeper))[:n]] = True
    return k


def pair_counts(ours: np.ndarray, sleeper: np.ndarray, actual: np.ndarray, blend: np.ndarray | None = None) -> dict[str, float]:
    """Over every pair of the given (startable) players: the close calls the two disagree on, and every pair.

    close: |ours diff| <= 3 or |sleeper diff| <= 3, the two rank them the other way round (no tie in either), actual
    differs -> ``close_n``, ``close_ours`` (the player we ranked higher scored more); a push is ``close_push``.
    all: every pair whose actual differs -> ``all_n``; ``all_ours`` / ``all_sleeper`` (/ ``all_blend``) = pairs that
    side orders right, a tie in that side's projection counting half."""
    i, j = np.triu_indices(len(ours), k=1)
    do, ds, da = ours[i] - ours[j], sleeper[i] - sleeper[j], actual[i] - actual[j]
    close = ((np.abs(do) <= CLOSE_POINTS) | (np.abs(ds) <= CLOSE_POINTS)) & (np.sign(do) * np.sign(ds) < 0)
    graded = da != 0
    right_o = np.sign(do) == np.sign(da)
    out = {"close_n": float((close & graded).sum()), "close_ours": float((close & graded & right_o).sum()),
           "close_push": float((close & ~graded).sum()), "all_n": float(graded.sum())}

    def score(d: np.ndarray) -> float:
        return float(((np.sign(d) == np.sign(da)) & graded & (d != 0)).sum() + 0.5 * ((d == 0) & graded).sum())

    out["all_ours"], out["all_sleeper"] = score(do), score(ds)
    if blend is not None:
        out["all_blend"] = score(blend[i] - blend[j])
    return out


def weekly(pop: pd.DataFrame, blend_w: Mapping[tuple[str, str], float] | None = None) -> pd.DataFrame:
    """One row per league x season x week x position: n, the three measures for each side, the pair counts."""
    rows = []
    for (lid, s, w, pos), g in pop.groupby(["league_id", "season", "week", "position"], sort=True):
        o, sl, a = g["ours"].to_numpy(float), g["sleeper"].to_numpy(float), g["actual"].to_numpy(float)
        ids = g["gsis_id"].astype(str).to_numpy()
        r = {"league_id": lid, "season": int(s), "week": int(w), "position": pos, "n": len(g),
             "mae_o": float(np.mean(np.abs(o - a))), "mae_s": float(np.mean(np.abs(sl - a))),
             "sp_o": spearman(o, a), "sp_s": spearman(sl, a),
             "hit_o": hit_rate(o, a, ids, TOP_N[pos]), "hit_s": hit_rate(sl, a, ids, TOP_N[pos])}
        k = startable_mask(o, sl, ids, STARTABLE[pos])
        b = None
        if blend_w is not None and (lid, pos) in blend_w:
            wt = blend_w[(lid, pos)]
            b = (1 - wt) * o + wt * sl
            r["mae_b"], r["sp_b"] = float(np.mean(np.abs(b - a))), spearman(b, a)
        r.update(pair_counts(o[k], sl[k], a[k], b[k] if b is not None else None))
        rows.append(r)
    return pd.DataFrame(rows)


def boot_mean(d: np.ndarray, rng: np.random.Generator) -> tuple[float, float, float]:
    d = d[~np.isnan(d)]
    if len(d) == 0:
        return np.nan, np.nan, np.nan
    idx = rng.integers(0, len(d), size=(DRAWS, len(d)))
    m = d[idx].mean(axis=1)
    return float(d.mean()), float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))


def boot_ratio(num: np.ndarray, den: np.ndarray, rng: np.random.Generator) -> tuple[float, float, float]:
    keep = den > 0
    num, den = num[keep], den[keep]
    if den.sum() == 0:
        return np.nan, np.nan, np.nan
    idx = rng.integers(0, len(den), size=(DRAWS, len(den)))
    r = num[idx].sum(axis=1) / np.maximum(den[idx].sum(axis=1), 1e-12)
    return float(num.sum() / den.sum()), float(np.percentile(r, 2.5)), float(np.percentile(r, 97.5))


def word(lo: float, hi: float, lower_is_better: bool) -> str | None:
    """ahead / behind when the interval of ours − Sleeper lies entirely on one side of zero; level otherwise."""
    if np.isnan(lo) or np.isnan(hi):
        return None
    if lower_is_better:
        lo, hi = -hi, -lo
    return "ahead" if lo > 0 else "behind" if hi < 0 else "level"


def headline_word(error: str | None, order: str | None) -> str | None:
    ws = [x for x in (error, order) if x is not None]
    if not ws:
        return None
    if "ahead" in ws and "behind" not in ws:
        return "ahead"
    if "behind" in ws and "ahead" not in ws:
        return "behind"
    return "level"


def grade_rows(wk: pd.DataFrame, rng: np.random.Generator) -> list[dict[str, Any]]:
    """The pooled and by-season rows of one league x position (``wk``: its weekly rows)."""
    out: list[dict[str, Any]] = []
    scopes = [(None, wk), *[(int(s), g) for s, g in wk.groupby("season")]]
    for season, g in scopes:
        base = {"season": season, "n_weeks": int(len(g)), "seasons": ", ".join(str(s) for s in sorted(g["season"].unique()))}
        words = {}
        for measure, a, b, low in (("error", "mae_o", "mae_s", True), ("order", "sp_o", "sp_s", False),
                                   ("hit_rate", "hit_o", "hit_s", False)):
            d = (g[a] - g[b]).to_numpy(float)
            mean, lo, hi = boot_mean(d, rng)
            words[measure] = word(lo, hi, low)
            out.append({**base, "kind": "position", "measure": measure, "n_rows": int(g["n"].sum()),
                        "n_weeks": int((~np.isnan(d)).sum()),
                        "ours": float(np.nanmean(g[a])) if g[a].notna().any() else None,
                        "sleeper": float(np.nanmean(g[b])) if g[b].notna().any() else None,
                        "diff": mean, "diff_lo": lo, "diff_hi": hi, "verdict": words[measure]})
        out.append({**base, "kind": "position", "measure": "verdict", "n_rows": int(g["n"].sum()),
                    "verdict": headline_word(words["error"], words["order"])})
        # the close calls they disagree on: our share right (Sleeper's is the rest); diff = ours − Sleeper = 2·share − 1
        share, lo, hi = boot_ratio(g["close_ours"].to_numpy(float), g["close_n"].to_numpy(float), rng)
        out.append({**base, "kind": "close_calls", "measure": "share", "n_rows": int(g["close_n"].sum()),
                    "ours": share, "sleeper": None if np.isnan(share) else 1 - share,
                    "diff": None if np.isnan(share) else 2 * share - 1, "diff_lo": None if np.isnan(lo) else 2 * lo - 1,
                    "diff_hi": None if np.isnan(hi) else 2 * hi - 1, "verdict": word(2 * lo - 1, 2 * hi - 1, False),
                    "blend": float(g["close_push"].sum())})          # blend column = pushes (counted, left out)
        num = (g["all_ours"] - g["all_sleeper"]).to_numpy(float)
        dshare, lo, hi = boot_ratio(num, g["all_n"].to_numpy(float), rng)
        n_all = float(g["all_n"].sum())
        out.append({**base, "kind": "startable_pairs", "measure": "share", "n_rows": int(n_all),
                    "ours": float(g["all_ours"].sum() / n_all) if n_all else None,
                    "sleeper": float(g["all_sleeper"].sum() / n_all) if n_all else None,
                    "diff": dshare, "diff_lo": lo, "diff_hi": hi, "verdict": word(lo, hi, False)})
    return out


def fit_w(fit_wk_pop: pd.DataFrame) -> float:
    """w minimising the error (the mean over weeks of the weekly MAE) on the fitting seasons' population."""
    best, best_err = 0.0, np.inf
    o, sl, a = (fit_wk_pop[c].to_numpy(float) for c in ("ours", "sleeper", "actual"))
    weeks = fit_wk_pop[["season", "week"]].astype(str).agg("-".join, axis=1).to_numpy()
    codes, inv = np.unique(weeks, return_inverse=True)
    for w in W_GRID:
        err = np.abs((1 - w) * o + w * sl - a)
        per_week = np.bincount(inv, weights=err) / np.bincount(inv)
        e = float(per_week.mean()) if len(codes) else np.inf
        if e < best_err - 1e-12:
            best, best_err = w, e
    return best


def blend_rows(pop: pd.DataFrame, lid: str, pos: str) -> list[dict[str, Any]]:
    """bl1.0 for one league x position: w fitted on the earlier seasons, measured on the test season."""
    out: list[dict[str, Any]] = []
    p = pop[(pop["league_id"] == lid) & (pop["position"] == pos) & pop["season"].isin(HISTORY_SEASONS)
            & (pop["ours_source"] != "kickoff_board")]
    gains = []
    for test, fits in BLEND_TESTS:
        tr, te = p[p["season"].isin(fits)], p[p["season"] == test]
        if tr.empty or te.empty:
            gains.append(None)
            continue
        w = fit_w(tr)
        wk = weekly(te, {(lid, pos): w})
        e_o, e_s, e_b = wk["mae_o"].mean(), wk["mae_s"].mean(), wk["mae_b"].mean()
        s_o, s_s, s_b = wk["sp_o"].mean(), wk["sp_s"].mean(), wk["sp_b"].mean()
        n_all = wk["all_n"].sum()
        g = bool(e_b <= (1 - BLEND_MIN_GAIN) * e_o and s_b >= s_o - BLEND_MAX_ORDER_LOSS)
        gains.append(g)
        base = {"kind": "blend", "season": test, "n_weeks": int(len(wk)), "n_rows": int(wk["n"].sum()), "w": w,
                "seasons": ", ".join(str(s) for s in fits)}
        out.append({**base, "measure": "error", "ours": e_o, "sleeper": e_s, "blend": e_b, "diff": e_b - e_o})
        out.append({**base, "measure": "order", "ours": s_o, "sleeper": s_s, "blend": s_b, "diff": s_b - s_o})
        out.append({**base, "measure": "share", "n_rows": int(n_all), "ours": wk["all_ours"].sum() / n_all if n_all else None,
                    "sleeper": wk["all_sleeper"].sum() / n_all if n_all else None,
                    "blend": wk["all_blend"].sum() / n_all if n_all else None})
    verdict = None if any(x is None for x in gains) or not gains else ("gains" if all(gains) else "no gain")
    out.append({"kind": "blend", "season": None, "measure": "verdict", "verdict": verdict,
                "seasons": ", ".join(str(t) for t, _ in BLEND_TESTS)})
    return out


def grade(inp: Inputs, built_at: datetime | None = None) -> pd.DataFrame:
    """``ops.sleeper_h2h``'s rows from the inputs (empty frame when nothing is graded)."""
    built_at = built_at or datetime.now(UTC)
    rng = np.random.default_rng(SEED)
    if inp.pop.empty:
        return pd.DataFrame(columns=[c for c, _ in GRADE_COLUMNS])
    wk = weekly(inp.pop)
    headline = next(iter(inp.leagues))
    rows = []
    for lid in inp.leagues:
        for pos in POSITIONS:
            g = wk[(wk["league_id"] == lid) & (wk["position"] == pos)]
            if g.empty:
                continue
            src = inp.pop[(inp.pop["league_id"] == lid) & (inp.pop["position"] == pos)]
            hist = src[src["ours_source"] != "kickoff_board"]
            label = (hist if not hist.empty else src)[["ours_source", "ours_version"]].iloc[0]
            for r in [*grade_rows(g, rng), *blend_rows(inp.pop, lid, pos)]:
                rows.append({"league_id": lid, "league_name": inp.leagues[lid], "headline": lid == headline, "position": pos,
                             "ours_source": label["ours_source"], "ours_version": label["ours_version"], "rule": RULE,
                             "built_at": built_at, **r})
    df = pd.DataFrame(rows)
    for c, _ in GRADE_COLUMNS:
        if c not in df:
            df[c] = None
    return df[[c for c, _ in GRADE_COLUMNS]]


def _cell(v: Any, kind: str) -> Any:
    """One value as the column's type (pandas makes an integer column with a gap float: 2024.0 is not an integer)."""
    if v is None or (isinstance(v, (float, np.floating)) and np.isnan(v)) or v is pd.NaT:
        return None
    if kind == "integer":
        return int(v)
    if kind == "double precision":
        return float(v)
    if kind == "boolean":
        return bool(v)
    if isinstance(v, pd.Timestamp):
        return v.to_pydatetime()
    return v


def rows_for_copy(df: pd.DataFrame) -> list[list[Any]]:
    kinds = [t for _, t in GRADE_COLUMNS]
    return [[_cell(v, k) for v, k in zip(rec, kinds, strict=True)]
            for rec in df[[c for c, _ in GRADE_COLUMNS]].itertuples(index=False)]


def write_grade(conn: psycopg.Connection, df: pd.DataFrame) -> int:
    cols = [c for c, _ in GRADE_COLUMNS]
    with conn.cursor() as cur:
        cur.execute(GRADE_DDL)
        cur.execute(f"truncate {GRADE_TABLE}")
        with cur.copy(f"copy {GRADE_TABLE} ({', '.join(cols)}) from stdin") as cp:
            for row in rows_for_copy(df):
                cp.write_row(row)
    conn.commit()
    return len(df)


# ------------------------------------------------------------------------------ the summary (one table)
def _f(x: Any, d: int = 2) -> str:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "–"
    return "–" if np.isnan(v) else f"{v:.{d}f}"


def _ci(lo: Any, hi: Any, d: int = 2) -> str:
    return f"[{_f(lo, d)}, {_f(hi, d)}]"


def _pct(x: Any) -> str:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "–"
    return "–" if np.isnan(v) else f"{100 * v:.1f}%"


def read_weeks(conn: psycopg.Connection) -> pd.DataFrame | None:
    """``ops.sleeper_history_weeks`` (None when the table does not exist)."""
    if not _exists(conn, "ops.sleeper_history_weeks"):
        return None
    return _q(conn, "select season, week, status, n_objects, n_lines, attempts, error from ops.sleeper_history_weeks")


def pull_lines(wk: pd.DataFrame | None, inp: Inputs | None) -> list[str]:
    """The pull's and the match's counts (loud: how many weeks of how many, how many lines matched by id)."""
    out = []
    if wk is None:
        return ["Sleeper's past weeks: not pulled yet (no table)."]
    if wk.empty:
        return ["Sleeper's past weeks: none pulled yet."]
    ok = wk[wk["status"] == "ok"]
    by = ", ".join(f"{int(s)} {int((g['status'] == 'ok').sum())}/{len(g)}" for s, g in wk.groupby("season"))
    out.append(f"Sleeper's past weeks held: {len(ok)} of {len(wk)} asked ({by}); "
               f"{int(pd.to_numeric(ok['n_objects']).sum()):,} objects, {int(pd.to_numeric(ok['n_lines']).sum()):,} with a line.")
    bad = wk[wk["status"] != "ok"]
    if len(bad):
        out.append(f"NOT held (asked again next night): {len(bad)} weeks — "
                   + "; ".join(f"{int(r.season)} wk {int(r.week)} ({str(r.error)[:60]})" for r in bad.head(6).itertuples()))
    if inp is not None and inp.counts.get("lines"):
        c = inp.counts
        out.append(f"Matched by id (QB–TE lines): {c['matched']:,} of {c['lines']:,}"
                   + (f"; unmatched ids e.g. {', '.join(c['unmatched_ids'][:5])}" if c.get("unmatched_ids") else "") + ".")
    return out


def summary_text(weeks: pd.DataFrame | None, df: pd.DataFrame, inp: Inputs | None, ours_note: str = "") -> str:
    lines = [f"### Us against Sleeper on past weeks ({RULE}; Sleeper's numbers served after the games, so this favours Sleeper)", ""]
    lines += [f"- {x}" for x in pull_lines(weeks, inp)]
    if ours_note:
        lines.append(f"- Our side, 2023–2025: {ours_note}")
    if df is None or df.empty:
        lines += ["", "No player-week graded yet (no Sleeper week held, or nothing matched our side)."]
        return "\n".join(lines) + "\n"
    head = df[df["headline"].astype(bool)]
    other = df[~df["headline"].astype(bool)]
    lid_name = head["league_name"].iloc[0] if len(head) else ""
    src = head[head["kind"] == "position"][["ours_source", "ours_version"]].drop_duplicates()
    for r in src.itertuples():
        lines.append(f"- Ours: {SOURCE_WORDS.get(r.ours_source, r.ours_source).format(v=r.ours_version)}"
                     + ("; 2026 weeks: our board as published before kickoff" if inp is not None and
                        (inp.pop["ours_source"] == "kickoff_board").any() else "") + ".")
    if inp is not None and not inp.pop.empty:
        p = inp.pop[inp.pop["league_id"] == head["league_id"].iloc[0]] if len(head) else inp.pop
        cnt = p.groupby(["position", "season"]).size().unstack(fill_value=0)
        lines.append("- Player-weeks graded (" + lid_name + "): " + "; ".join(
            f"{pos} " + ", ".join(f"{s} {int(cnt.loc[pos, s]):,}" for s in cnt.columns) for pos in cnt.index) + ".")
    lines += ["", f"**{lid_name}** (pooled over weeks; ours − Sleeper with a 95% interval from resampling weeks):", "",
              "| pos | weeks | error ours / Sleeper | diff [95%] | order ours / Sleeper | diff [95%] | close calls we won | word | dynasty word |",
              "|---|---:|---|---|---|---|---|---|---|"]
    for pos in POSITIONS:
        g = head[(head["position"] == pos) & head["season"].isna()]
        if g.empty:
            continue

        def m(meas: str, kind: str = "position", _g=g) -> pd.Series:
            x = _g[(_g["kind"] == kind) & (_g["measure"] == meas)]
            return x.iloc[0] if len(x) else pd.Series(dtype=object)

        e, o, v, c = m("error"), m("order"), m("verdict"), m("share", "close_calls")
        dyn = other[(other["position"] == pos) & other["season"].isna() & (other["kind"] == "position")
                    & (other["measure"] == "verdict")]
        lines.append(f"| {pos} | {int(e.get('n_weeks') or 0)} | {_f(e.get('ours'))} / {_f(e.get('sleeper'))} | "
                     f"{_f(e.get('diff'))} {_ci(e.get('diff_lo'), e.get('diff_hi'))} | {_f(o.get('ours'), 3)} / {_f(o.get('sleeper'), 3)} | "
                     f"{_f(o.get('diff'), 3)} {_ci(o.get('diff_lo'), o.get('diff_hi'), 3)} | "
                     f"{_pct(c.get('ours'))} of {int(c.get('n_rows') or 0):,} ({c.get('verdict') or '–'}) | "
                     f"**{v.get('verdict') or '–'}** | {dyn['verdict'].iloc[0] if len(dyn) and dyn['verdict'].iloc[0] else '–'} |")
    # by season: the word per position
    seas = head[head["season"].notna() & (head["kind"] == "position") & (head["measure"] == "verdict")]
    if len(seas):
        lines += ["", "By season (word): " + "; ".join(
            f"{int(s)}: " + ", ".join(f"{r.position} {r.verdict or '–'}" for r in g.itertuples())
            for s, g in seas.groupby("season"))]
    bl = head[(head["kind"] == "blend") & (head["measure"] == "verdict")]
    if len(bl):
        lines += ["", f"Blend ({BLEND_RULE}, measured, not shipped): " + ", ".join(
            f"{r.position} {r.verdict or '–'}" for r in bl.itertuples())
            + " (w by test season: " + ", ".join(
                f"{r.position} {int(r.season)} w={_f(r.w)}" for r in head[(head['kind'] == 'blend') & (head['measure'] == 'error')].itertuples()) + ")"]
    return "\n".join(lines) + "\n"


def run(make_ours: bool = True) -> str:
    """``league-lab h2h``: the live model's rows when missing (once per version), the grade, the summary text."""
    from .config import get_settings

    with psycopg.connect(get_settings().pipeline_dsn()) as conn:
        ensure_tables(conn)
        note = ""
        if make_ours:
            note = ensure_ours(conn)
        inp = load_inputs(conn)
        df = grade(inp)
        n = write_grade(conn, df)
        if not inp.pop.empty:
            src = inp.pop[inp.pop["ours_source"] != "kickoff_board"]["ours_source"]
            if len(src) and src.iloc[0] == "stored_walk_forward":
                note = (note + "; " if note else "") + "the live model's rows are missing: graded on the stored rows, labelled"
        log.info("%s: %s rows written (%s player-weeks graded)", GRADE_TABLE, n, len(inp.pop))
        text = summary_text(read_weeks(conn), df, inp, note)
        # ---- JB-1 (Wave J-B): gp1.0, where the gap is (ops.sleeper_h2h_gap); never fails the grade above
        from . import h2h_gap
        try:
            gap = h2h_gap.nightly(conn, inp)
        except Exception as exc:  # noqa: BLE001 - the grade is written; the summary says the gap table is missing
            conn.rollback()
            log.exception("gp1.0: the gap table could not be built: %s", exc)
            gap = ["", f"**Where the gap is**: NOT built tonight ({type(exc).__name__}: {str(exc)[:120]})."]
        return text + ("\n".join(gap) + "\n" if gap else "")
        # ---- end JB-1
