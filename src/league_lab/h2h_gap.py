"""JB-1 (Wave J-B): where we lose to Sleeper — gp1.0 (docs/METRICS.md § "Where we lose to Sleeper", the rule committed
before any number).

* ``population`` — hh1.0's population (``h2h.load_inputs``) in League of Scrubs' scoring (the headline league), with
  the columns every slice reads, joined by id: the feature row (home, the total, his team's QB change), the previous
  feature row of his season (first game back), the role alerts raised in W−3 … W−1, the rookie season, the played
  games before the week; optionally the walk-forward's stat line (``lines``: ``scripts/analysis/jb1_gap.py run``) and
  Sleeper's, for the by-component family.
* ``assign`` — the slices (pure, on any frame with those columns; tested on constructed rows).
* ``family_table`` / ``diagnose`` — per slice: n, gap (mean excess), share of the summed excess, both with a 95%
  interval by resampling weeks (one set of draws for a whole family), the signed errors, the close calls.
* ``ship_rule`` — gp1.0's rule for a candidate fix against the baseline run.
* ``summary_rows`` / ``summary_lines`` — the six largest slices for the run's summary and ``/api/record``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd
import psycopg

RULE = "gp1.0"
SEED = 20261014
DRAWS = 2000
POSITIONS = ("QB", "RB", "WR", "TE")
TIERS = ((1, 12, "top-12"), (13, 24, "13-24"), (25, 36, "25-36"), (37, 10_000, "37+"))
HISTORY_BINS = ((0, 2, "0-2 games"), (3, 7, "3-7 games"), (8, 10**6, "8+ games"))
COMPONENTS = {   # component -> League of Scrubs' scoring key (its points per unit)
    "passing_yards": "pass_yd", "passing_tds": "pass_td", "passing_interceptions": "pass_int",
    "rushing_yards": "rush_yd", "rushing_tds": "rush_td", "receptions": "rec", "receiving_yards": "rec_yd",
    "receiving_tds": "rec_td", "fumbles_lost_total": "fum_lost"}
FAMILIES = ("position × tier", "first game back", "role", "QB change", "experience", "history", "season stage", "venue",
            "game total", "season")
FAMILY_WORDS = {"position × tier": "position and our rank", "first game back": "first game back after a missed game",
                "role": "role alert before the week", "QB change": "his team's starting QB changed",
                "experience": "experience", "history": "games played before the week", "season stage": "weeks",
                "venue": "home or away", "game total": "the game's betting total", "season": "season",
                "component": "part of the stat line"}


# ------------------------------------------------------------------------------ the population
def _q(conn: psycopg.Connection, sql: str, params: tuple = ()) -> pd.DataFrame:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])


def sleeper_rows(conn: psycopg.Connection) -> pd.DataFrame:
    """Sleeper's history rows matched by id (gsis_id, season, week), priced in the headline league's scoring, with the
    line's components."""
    from . import h2h
    from . import projections as P

    leagues = P.league_scorings(conn)
    scoring = next(iter(leagues.values()))[1]
    hist = _q(conn, "select * from ops.sleeper_history where position = any(%s)", (list(POSITIONS),))
    idmap = _q(conn, "select sleeper_id, gsis_id from analytics.player_id_map where sleeper_id is not null")
    idmap = idmap[~idmap["sleeper_id"].duplicated(keep=False)]
    hist = hist.merge(idmap, left_on="player_id", right_on="sleeper_id", how="inner")
    for c in hist.columns:
        if c not in ("player_id", "position", "team", "opponent", "company", "served", "gsis_id", "sleeper_id",
                     "updated_at", "fetched_at"):
            hist[c] = pd.to_numeric(hist[c], errors="coerce")
    hist["sleeper"] = h2h.price_sleeper(hist, scoring)
    keep = ["gsis_id", "season", "week", "sleeper", *[c for c in COMPONENTS if c in hist.columns]]
    out = hist[keep].copy()
    out["season"], out["week"] = out["season"].astype(int), out["week"].astype(int)
    return out


def population(conn: psycopg.Connection, lines: pd.DataFrame | None = None, inp: Any = None) -> pd.DataFrame:
    """gp1.0's population with every slice's inputs (League of Scrubs' scoring). ``inp``: ``h2h.load_inputs``'s answer
    when the caller has it already."""
    from . import calibration as cal
    from . import h2h

    inp = inp if inp is not None else h2h.load_inputs(conn)
    if inp.pop.empty:
        return pd.DataFrame()
    head = next(iter(inp.leagues))
    pop = inp.pop[inp.pop["league_id"] == head].copy()
    pop["league_name"] = inp.leagues[head]
    feats = _q(conn, """select gsis_id, season, week, team, is_home, total_line, pn_qb_changed, played
                        from analytics.mart_player_week_features where season = any(%s)""",
               (sorted({int(s) for s in pop["season"]}),))
    feats = feats.sort_values(["gsis_id", "season", "week"])
    feats["prev_played"] = feats.groupby(["gsis_id", "season"])["played"].shift(1)
    pop = pop.merge(feats.drop(columns="played"), on=["gsis_id", "season", "week"], how="left")
    alerts = _q(conn, "select season, week, gsis_id, direction from ops.player_role_alerts where season = any(%s)",
                (sorted({int(s) for s in pop["season"]}),))
    pop["role"] = role_before(pop, alerts)
    games, draft = cal._history(conn)
    pop["career_games_before"] = cal.career_games_before(pop, games[["gsis_id", "season", "week"]])
    dr = draft.drop_duplicates("gsis_id").set_index("gsis_id")
    pop["rookie_season"] = pd.to_numeric(pop["gsis_id"].map(dr["rookie_season"]), errors="coerce")
    if lines is not None and not lines.empty:
        ln = lines[lines["league_id"] == head]
        cols = [c for c in ln.columns if c.startswith(("proj_", "out_")) and c != "proj_points"]
        pop = pop.merge(ln[["gsis_id", "season", "week", *cols]], on=["gsis_id", "season", "week"], how="left")
        sl = sleeper_rows(conn).drop(columns="sleeper")
        pop = pop.merge(sl.rename(columns={c: f"sl_{c}" for c in COMPONENTS}), on=["gsis_id", "season", "week"], how="left")
    return assign(pop.reset_index(drop=True))


def role_before(pop: pd.DataFrame, alerts: pd.DataFrame) -> list[str]:
    """Per row: the role alerts for him raised in weeks W−3 … W−1 of the season — 'role up' / 'role down' / 'both or
    other' / 'none'."""
    if alerts.empty:
        return ["none"] * len(pop)
    a = alerts.copy()
    a["season"], a["week"] = a["season"].astype(int), a["week"].astype(int)
    by = {k: g for k, g in a.groupby(["gsis_id", "season"])}
    out = []
    for g, s, w in pop[["gsis_id", "season", "week"]].itertuples(index=False):
        x = by.get((g, int(s)))
        if x is None:
            out.append("none")
            continue
        d = set(x.loc[(x["week"] >= int(w) - 3) & (x["week"] <= int(w) - 1), "direction"].astype(str))
        out.append("none" if not d else "role up" if d == {"up"} else "role down" if d == {"down"} else "both or other")
    return out


# ------------------------------------------------------------------------------ the slices (pure)
def tier_of(rank: int) -> str:
    return next(label for lo, hi, label in TIERS if lo <= rank <= hi)


def assign(pop: pd.DataFrame) -> pd.DataFrame:
    """The gap and one column per family (``slice_<family>``) on a population frame."""
    d = pop.copy()
    d["excess"] = (d["ours"] - d["actual"]).abs() - (d["sleeper"] - d["actual"]).abs()
    d["err_ours"], d["err_sleeper"] = d["ours"] - d["actual"], d["sleeper"] - d["actual"]
    d["wk"] = d["season"].astype(int) * 100 + d["week"].astype(int)
    d = d.sort_values(["league_id", "season", "week", "position", "ours", "gsis_id"],
                      ascending=[True, True, True, True, False, True]).reset_index(drop=True)
    d["our_rank"] = d.groupby(["league_id", "season", "week", "position"]).cumcount() + 1
    d["slice_position × tier"] = d["position"] + " " + d["our_rank"].map(tier_of)
    pp = d.get("prev_played")
    d["slice_first game back"] = np.where(pp.isna(), "not back (no earlier game this season)",
                                          np.where(pp.astype(object) == False, "first game back", "not back"))  # noqa: E712
    d["slice_role"] = d["role"] if "role" in d else "none"
    q = d.get("pn_qb_changed")
    d["slice_QB change"] = np.where(q.isna(), "unknown", np.where(q.astype(object) == True, "QB changed", "same QB"))  # noqa: E712
    rk = pd.to_numeric(d.get("rookie_season"), errors="coerce")
    yrs = d["season"].astype(float) - rk
    d["slice_experience"] = np.select([rk.isna(), yrs <= 0, yrs == 1], ["unknown", "rookie", "second year"], "veteran")
    cg = pd.to_numeric(d.get("career_games_before"), errors="coerce").fillna(0)
    early = rk < 2016
    hist = np.where(early, "8+ games", cg.map(lambda n: next(lab for lo, hi, lab in HISTORY_BINS if lo <= n <= hi)))
    d["slice_history"] = hist
    d["slice_season stage"] = np.where(d["week"].astype(int) <= 4, "weeks 1-4", "weeks 5-18")
    h = d.get("is_home")
    d["slice_venue"] = np.where(h.isna(), "unknown", np.where(h.astype(object) == True, "home", "away"))  # noqa: E712
    tot = pd.to_numeric(d.get("total_line"), errors="coerce")
    held = tot.dropna()
    if len(held) >= 3:
        lo, hi = np.quantile(held, [1 / 3, 2 / 3])
        d["slice_game total"] = np.select([tot.isna(), tot <= lo, tot <= hi], ["not held", f"low (≤ {lo:g})",
                                                                               f"middle (≤ {hi:g})"], f"high (> {hi:g})")
    else:
        d["slice_game total"] = np.where(tot.isna(), "not held", "held")
    d["slice_season"] = d["season"].astype(int).astype(str)
    return d


def _draws(weeks: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Week-resampling weights: (DRAWS, n weeks) counts of each week in each draw."""
    idx = rng.integers(0, len(weeks), size=(DRAWS, len(weeks)))
    w = np.zeros((DRAWS, len(weeks)))
    np.add.at(w, (np.repeat(np.arange(DRAWS), len(weeks)), idx.ravel()), 1)
    return w


def family_table(d: pd.DataFrame, col: str, values: str = "excess", rng: np.random.Generator | None = None,
                 weights: np.ndarray | None = None) -> pd.DataFrame:
    """Per slice of ``col``: n, row share, gap (mean of ``values``) and share of the summed ``values``, each with a 95%
    week-resampling interval (the same draws for every slice), the signed errors and the close calls."""
    rng = rng or np.random.default_rng(SEED)
    weeks, wi = np.unique(d["wk"].to_numpy(), return_inverse=True)
    W = weights if weights is not None else _draws(weeks, rng)
    labels = d[col].astype(str).to_numpy()
    v = d[values].to_numpy(dtype=float)
    tot_w = np.bincount(wi, weights=v, minlength=len(weeks))
    total_draw = W @ tot_w
    rows = []
    for lab in sorted(set(labels)):
        m = labels == lab
        s_w = np.bincount(wi[m], weights=v[m], minlength=len(weeks))
        n_w = np.bincount(wi[m], minlength=len(weeks)).astype(float)
        sd, nd = W @ s_w, W @ n_w
        with np.errstate(invalid="ignore", divide="ignore"):
            gap_d, share_d = sd / nd, sd / total_draw
        r = {"family": col.removeprefix("slice_"), "slice": lab, "n": int(m.sum()), "row_share": float(m.mean()),
             "gap": float(v[m].mean()), "gap_lo": float(np.nanpercentile(gap_d, 2.5)),
             "gap_hi": float(np.nanpercentile(gap_d, 97.5)), "share": float(v[m].sum() / v.sum()) if v.sum() else np.nan,
             "share_lo": float(np.nanpercentile(share_d, 2.5)), "share_hi": float(np.nanpercentile(share_d, 97.5))}
        if "err_ours" in d:
            r["bias_ours"], r["bias_sleeper"] = float(d.loc[m, "err_ours"].mean()), float(d.loc[m, "err_sleeper"].mean())
            r["mae_ours"] = float(d.loc[m, "err_ours"].abs().mean())
            r["mae_sleeper"] = float(d.loc[m, "err_sleeper"].abs().mean())
        rows.append(r)
    return pd.DataFrame(rows).sort_values("share", ascending=False).reset_index(drop=True)


def close_calls(d: pd.DataFrame, col: str) -> pd.DataFrame:
    """hh1.0's close calls (startable by either, within 3 points by either, ranked the other way, actual differs) per
    slice of the player WE rank higher: n and our share right."""
    from .h2h import CLOSE_POINTS, STARTABLE, startable_mask

    out: dict[str, list[int]] = {}
    for (_lid, _s, _w, pos), g in d.groupby(["league_id", "season", "week", "position"], sort=False):
        o, sl, a = (g[c].to_numpy(float) for c in ("ours", "sleeper", "actual"))
        ids = g["gsis_id"].astype(str).to_numpy()
        k = startable_mask(o, sl, ids, STARTABLE[pos])
        o, sl, a, lab = o[k], sl[k], a[k], g[col].astype(str).to_numpy()[k]
        i, j = np.triu_indices(len(o), k=1)
        do, ds, da = o[i] - o[j], sl[i] - sl[j], a[i] - a[j]
        close = ((np.abs(do) <= CLOSE_POINTS) | (np.abs(ds) <= CLOSE_POINTS)) & (np.sign(do) * np.sign(ds) < 0) & (da != 0)
        hi = np.where(do > 0, i, j)                       # the player we rank higher
        right = np.sign(do) == np.sign(da)
        for x, rr in zip(lab[hi[close]], right[close], strict=True):
            c = out.setdefault(x, [0, 0])
            c[0] += 1
            c[1] += int(rr)
    return pd.DataFrame([{"slice": k, "calls": v[0], "calls_ours_right": v[1] / v[0] if v[0] else np.nan}
                         for k, v in out.items()], columns=["slice", "calls", "calls_ours_right"])


def component_table(d: pd.DataFrame, scoring: Mapping[str, float], rng: np.random.Generator | None = None) -> pd.DataFrame:
    """The by-component family: excess_c = |w_c| × (|ours_c − actual_c| − |Sleeper_c − actual_c|), shares of the
    components' summed excess (rows with all three lines; 2023–2025)."""
    rng = rng or np.random.default_rng(SEED)
    have = [c for c in COMPONENTS if {f"proj_{c}", f"out_{c}", f"sl_{c}"} <= set(d.columns)]
    x = d.dropna(subset=[f"proj_{c}" for c in have] + [f"out_{c}" for c in have]).copy()
    if x.empty or not have:
        return pd.DataFrame()
    long = []
    for c in have:
        w = abs(float(scoring.get(COMPONENTS[c], 0.0)))
        if w == 0:
            continue
        sl = x[f"sl_{c}"].fillna(0.0)          # Sleeper gives no key for a stat it projects at 0 (e.g. a WR's passing)
        e = w * ((x[f"proj_{c}"] - x[f"out_{c}"]).abs() - (sl - x[f"out_{c}"]).abs())
        long.append(pd.DataFrame({"wk": x["wk"].to_numpy(), "slice_component": c, "excess": e.to_numpy(),
                                  "position": x["position"].to_numpy()}))
    lg = pd.concat(long, ignore_index=True)
    return family_table(lg, "slice_component", rng=rng)


def diagnose(pop: pd.DataFrame, scoring: Mapping[str, float] | None = None) -> dict[str, pd.DataFrame]:
    """Every family's table (the study's run; 2023–2025 + 2026 week 4)."""
    out = {}
    for fam in FAMILIES:
        col = f"slice_{fam}"
        t = family_table(pop, col)
        cc = close_calls(pop, col)
        out[fam] = t.merge(cc, on="slice", how="left")
    if scoring is not None:
        out["component"] = component_table(pop[pop["season"].astype(int) <= 2025], scoring)
    return out


def leaders(tables: Mapping[str, pd.DataFrame], k: int = 2) -> pd.DataFrame:
    """gp1.0's "holds most of the gap": the k position × tier cells with the largest share."""
    t = tables.get("position × tier")
    return t.head(k) if t is not None else pd.DataFrame()


def summary_rows(tables: Mapping[str, pd.DataFrame], k: int = 6) -> pd.DataFrame:
    """The k largest position × tier cells by share (the partition whose shares compare), for the run's summary and
    the API; the other families are the study's (a broad slice such as weeks 5–18 holds most of any total)."""
    t = tables.get("position × tier")
    if t is None or t.empty:
        return pd.DataFrame()
    return t.assign(family="position × tier").sort_values("share", ascending=False).head(k).reset_index(drop=True)


# ------------------------------------------------------------------------------ the nightly's table
GAP_TABLE = "ops.sleeper_h2h_gap"
GAP_COLUMNS: list[tuple[str, str]] = [
    ("league_id", "text"), ("family", "text"), ("slice", "text"), ("rank", "integer"), ("n", "integer"),
    ("row_share", "double precision"), ("gap", "double precision"), ("gap_lo", "double precision"),
    ("gap_hi", "double precision"), ("share", "double precision"), ("share_lo", "double precision"),
    ("share_hi", "double precision"), ("bias_ours", "double precision"), ("bias_sleeper", "double precision"),
    ("mae_ours", "double precision"), ("mae_sleeper", "double precision"), ("calls", "integer"),
    ("calls_ours_right", "double precision"), ("n_population", "integer"), ("excess_total", "double precision"),
    ("rule", "text"), ("built_at", "timestamptz")]
GAP_DDL = f"create table if not exists {GAP_TABLE} ({', '.join(f'{c} {t}' for c, t in GAP_COLUMNS)})"


def ensure_tables(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute(GAP_DDL)
    conn.commit()


def gap_frame(tables: Mapping[str, pd.DataFrame], league_id: str, n_population: int, excess_total: float) -> pd.DataFrame:
    """Every family's rows for ``ops.sleeper_h2h_gap`` (rank = the order by share within the family)."""
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    parts = []
    for fam, t in tables.items():
        if t is None or t.empty:
            continue
        x = t.sort_values("share", ascending=False).reset_index(drop=True).copy()
        x["family"], x["rank"] = fam, np.arange(1, len(x) + 1)
        parts.append(x)
    if not parts:
        return pd.DataFrame(columns=[c for c, _ in GAP_COLUMNS])
    df = pd.concat(parts, ignore_index=True)
    df["league_id"], df["n_population"], df["excess_total"] = league_id, n_population, excess_total
    df["rule"], df["built_at"] = RULE, now
    for c, _ in GAP_COLUMNS:
        if c not in df:
            df[c] = None
    return df[[c for c, _ in GAP_COLUMNS]]


def write_gap(conn: psycopg.Connection, df: pd.DataFrame) -> int:
    from .h2h import _cell

    kinds = [t for _, t in GAP_COLUMNS]
    with conn.cursor() as cur:
        cur.execute(GAP_DDL)
        cur.execute(f"truncate {GAP_TABLE}")
        with cur.copy(f"copy {GAP_TABLE} ({', '.join(c for c, _ in GAP_COLUMNS)}) from stdin") as cp:
            for rec in df[[c for c, _ in GAP_COLUMNS]].itertuples(index=False):
                cp.write_row([_cell(v, k) for v, k in zip(rec, kinds, strict=True)])
    conn.commit()
    return len(df)


def nightly(conn: psycopg.Connection, inp: Any = None) -> list[str]:
    """``league-lab h2h``'s part: every family (no by-component: the nightly keeps no walk-forward line) into
    ``ops.sleeper_h2h_gap``, and the summary's lines (the six largest position × tier cells)."""
    pop = population(conn, inp=inp)
    if pop.empty:
        write_gap(conn, gap_frame({}, "", 0, 0.0))
        return []
    tables = diagnose(pop)
    total = float(pop["excess"].sum())
    write_gap(conn, gap_frame(tables, str(pop["league_id"].iloc[0]), len(pop), total))
    return summary_lines(summary_rows(tables), len(pop), total)


# ------------------------------------------------------------------------------ the ship rule
def _per(d: pd.DataFrame, col: str) -> pd.DataFrame:
    from .h2h import spearman

    rows = []
    for (s, pos), g in d.groupby(["season", "position"]):
        sp = [spearman(w[col].to_numpy(float), w["actual"].to_numpy(float)) for _, w in g.groupby("week")]
        rows.append({"season": int(s), "position": pos, "error": float((g[col] - g["actual"]).abs().mean()),
                     "order": float(np.nanmean(sp)) if np.isfinite(sp).any() else np.nan, "n": len(g)})
    return pd.DataFrame(rows)


def ship_rule(base: pd.DataFrame, cand: pd.DataFrame, sleeper: pd.DataFrame, target: str | None = None,
              league_id: str | None = None) -> dict[str, Any]:
    """gp1.0's rule: on the population (rows Sleeper also projected, 2023–2025, the headline league), at ``target``:
    error lower than the baseline in every season and order no more than 0.002 lower in any; at the other positions,
    pooled, error no more than 0.005 worse and order no more than 0.002 lower."""
    lid = league_id or str(base["league_id"].iloc[0])
    keys = ["gsis_id", "season", "week"]
    b = base[base["league_id"].astype(str) == lid][[*keys, "position", "proj_points", "actual"]]
    c = cand[cand["league_id"].astype(str) == lid][[*keys, "proj_points"]].rename(columns={"proj_points": "cand"})
    d = b.merge(c, on=keys, how="inner").merge(sleeper[[*keys, "sleeper"]], on=keys, how="inner")
    d = d[d["actual"].notna() & d["season"].astype(int).between(2023, 2025)].rename(columns={"proj_points": "base"})
    pb, pc, ps = _per(d, "base"), _per(d, "cand"), _per(d, "sleeper")
    t = pb.merge(pc, on=["season", "position", "n"], suffixes=("_base", "_cand")).merge(
        ps.rename(columns={"error": "error_sleeper", "order": "order_sleeper"}), on=["season", "position", "n"])
    pooled = {}
    for pos, g in d.groupby("position"):
        wk = g.groupby(["season", "week"])
        pooled[pos] = {k: float((g[k] - g["actual"]).abs().mean()) for k in ("base", "cand", "sleeper")}
        from .h2h import spearman
        for k in ("base", "cand"):
            pooled[pos][f"order_{k}"] = float(np.nanmean([spearman(w[k].to_numpy(float), w["actual"].to_numpy(float))
                                                           for _, w in wk]))
    moved = int((np.abs(d["cand"] - d["base"]) > 1e-9).sum())
    if target is None:     # the position the candidate moved most
        target = d.assign(m=(d["cand"] - d["base"]).abs()).groupby("position")["m"].sum().idxmax() if moved else "RB"
    tt = t[t["position"] == target]
    a = bool(len(tt) == 3 and (tt["error_cand"] < tt["error_base"]).all()
             and (tt["order_cand"] >= tt["order_base"] - 0.002).all())
    others = [p for p in POSITIONS if p != target and p in pooled]
    b_ok = all(pooled[p]["cand"] <= pooled[p]["base"] + 0.005 and pooled[p]["order_cand"] >= pooled[p]["order_base"] - 0.002
               for p in others)
    return {"target": target, "a": a, "b": b_ok, "ships": a and b_ok, "by_season": t, "pooled": pooled,
            "rows_moved": moved, "rows": len(d)}


def ship_markdown(name: str, r: Mapping[str, Any]) -> str:
    t = r["by_season"]
    lines = [f"### {name}: target {r['target']} — (a) {'pass' if r['a'] else 'fail'}, (b) {'pass' if r['b'] else 'fail'}"
             f" → {'SHIPS' if r['ships'] else 'does not ship'} ({r['rows_moved']:,} of {r['rows']:,} rows moved)", "",
             "| season | pos | n | error base / cand / Sleeper | order base / cand / Sleeper |", "|---|---|---:|---|---|"]
    for x in t.sort_values(["position", "season"]).itertuples():
        lines.append(f"| {x.season} | {x.position} | {x.n:,} | {x.error_base:.4f} / {x.error_cand:.4f} / {x.error_sleeper:.4f} | "
                     f"{x.order_base:.4f} / {x.order_cand:.4f} / {x.order_sleeper:.4f} |")
    lines += ["", "Pooled 2023–2025: " + "; ".join(
        f"{p} error {v['base']:.4f} → {v['cand']:.4f} (Sleeper {v['sleeper']:.4f}; gap {v['base'] - v['sleeper']:+.4f} → "
        f"{v['cand'] - v['sleeper']:+.4f}), order {v['order_base']:.4f} → {v['order_cand']:.4f}"
        for p, v in r["pooled"].items())]
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------------------ words
def _f(x: Any, d: int = 2) -> str:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "–"
    return "–" if np.isnan(v) else f"{v:.{d}f}"


def _pct(x: Any) -> str:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "–"
    return "–" if np.isnan(v) else f"{100 * v:.0f}%"


def summary_lines(top: pd.DataFrame, n_rows: int, total_excess: float) -> list[str]:
    """The run summary's gap table (markdown)."""
    if top is None or top.empty:
        return []
    out = ["", f"**Where the gap is** ({RULE}; League of Scrubs' scoring; {n_rows:,} player-weeks; we miss by "
               f"{total_excess / max(n_rows, 1):+.2f} points a player-week more than Sleeper; share = the slice's part of "
               "that excess, 95% interval from resampling weeks):", "",
           "| slice | player-weeks | gap a player-week [95%] | share of the gap [95%] | our bias / Sleeper's |",
           "|---|---:|---|---|---|"]
    for r in top.itertuples():
        out.append(f"| {FAMILY_WORDS.get(r.family, r.family)}: {r.slice} | {r.n:,} | {_f(r.gap)} [{_f(r.gap_lo)}, "
                   f"{_f(r.gap_hi)}] | {_pct(r.share)} [{_pct(r.share_lo)}, {_pct(r.share_hi)}] | "
                   f"{_f(getattr(r, 'bias_ours', None))} / {_f(getattr(r, 'bias_sleeper', None))} |")
    return out


def study_markdown(tables: Mapping[str, pd.DataFrame], pop: pd.DataFrame) -> str:
    lines = [f"## gp1.0 diagnosis: {len(pop):,} player-weeks, summed excess {pop['excess'].sum():+.1f} "
             f"(mean {pop['excess'].mean():+.3f}); seasons {sorted(pop['season'].astype(int).unique().tolist())}"]
    for fam, t in tables.items():
        if t is None or t.empty:
            continue
        lines += ["", f"### {fam}", "",
                  "| slice | n | rows | gap [95%] | share [95%] | MAE ours / Sleeper | bias ours / Sleeper | close calls (ours right) |",
                  "|---|---:|---:|---|---|---|---|---|"]
        for r in t.itertuples():
            cc = (f"{int(r.calls):,} ({_pct(r.calls_ours_right)})" if hasattr(r, "calls") and pd.notna(getattr(r, "calls", np.nan))
                  else "–")
            lines.append(f"| {r.slice} | {r.n:,} | {_pct(r.row_share)} | {_f(r.gap, 3)} [{_f(r.gap_lo, 3)}, {_f(r.gap_hi, 3)}] | "
                         f"{_pct(r.share)} [{_pct(r.share_lo)}, {_pct(r.share_hi)}] | "
                         f"{_f(getattr(r, 'mae_ours', None))} / {_f(getattr(r, 'mae_sleeper', None))} | "
                         f"{_f(getattr(r, 'bias_ours', None))} / {_f(getattr(r, 'bias_sleeper', None))} | {cc} |")
    return "\n".join(lines) + "\n"
