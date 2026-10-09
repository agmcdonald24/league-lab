"""IU-5 (Wave I-U): the horizon grade that counts a missed week (hg1.0, docs/METRICS.md § "The horizon grade that counts
a missed week (IU-5)"; the grade was written and committed before any number on it). Read only on the database.

v3.6, "the starter keeps the job", rf1.0 and the oracle (IT-5's lines, ``it5_role.py`` unchanged) scored on hg1.0:
the horizon study's QB rows, the outcome in week T by case (played: his points; injured or exempt: excluded; healthy on
a roster, cut or retired with a row: 0), MAE and Spearman per cell, pooled over h = 2-8 as the old board.

usage: OMP_NUM_THREADS=1 uv run python scripts/analysis/iu5_grade.py --cache q.parquet
"""
from __future__ import annotations

import argparse
import importlib.util
import logging
import os
import sys
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import psycopg  # noqa: E402

from league_lab.config import get_settings  # noqa: E402

_spec = importlib.util.spec_from_file_location("it5_role", Path(__file__).with_name("it5_role.py"))
M = importlib.util.module_from_spec(_spec)
sys.modules["it5_role"] = M
_spec.loader.exec_module(M)
Q = M.Q

log = logging.getLogger("iu5")
INJURED_REPORT = {"Out", "Doubtful", "Questionable"}
INJURED_ROSTER = {"RES"}
ZERO_ROSTER = {"ACT", "INA", "DEV", "CUT", "RET"}
STATUS_SQL = """select r.gsis_id, r.season, r.week, r.roster_status, i.report_status
                from staging.stg_nflverse__rosters_weekly r
                left join staging.stg_nflverse__injuries i
                  on i.gsis_id = r.gsis_id and i.season = r.season and i.week = r.week and i.season_type = 'REG'
                where r.position = 'QB' and r.season_type = 'REG' and r.season between %s and %s"""


def case_of(played: bool, ok: bool, roster: str | None, report: str | None) -> str:
    """hg1.0's case for one row in week T (the bye has no row)."""
    if played:
        return "played" if ok else "played, an outcome unknown"
    if (report in INJURED_REPORT) or (roster in INJURED_ROSTER):
        return "injured"
    if roster in ZERO_ROSTER:
        return "healthy, not playing" if roster in ("ACT", "INA", "DEV") else "cut or retired"
    return "other"


ZERO_CASES = {"healthy, not playing", "cut or retired"}


def hg_outcome(d: pd.DataFrame, status: pd.DataFrame) -> pd.DataFrame:
    """Per cache row (horizon, h >= 2): the case and whether it is graded; board and h = 1 rows: not graded here."""
    hz = (d["kind"] == "horizon").to_numpy() & (d["h"].fillna(0).to_numpy() >= 2)
    key = d[["gsis_id", "season", "target_week"]].copy()
    key["season"], key["target_week"] = key["season"].astype(int), key["target_week"].fillna(0).astype(int)
    st = status.rename(columns={"week": "target_week"})
    st["season"], st["target_week"] = st["season"].astype(int), st["target_week"].astype(int)
    m = key.reset_index().merge(st, on=["gsis_id", "season", "target_week"], how="left").set_index("index").reindex(d.index)
    played = d["played"].fillna(False).astype(bool).to_numpy()
    ok = Q.scored(d)
    cases = np.array([case_of(p, o, r if isinstance(r, str) else None, q if isinstance(q, str) else None)
                      for p, o, r, q in zip(played, ok, m["roster_status"], m["report_status"])], dtype=object)
    cases[~hz] = "not a later-week row"
    graded = np.isin(cases, ["played", *ZERO_CASES])
    return pd.DataFrame({"case": cases, "graded": graded, "zero": np.isin(cases, list(ZERO_CASES))}, index=d.index)


def run(cache_path: Path) -> None:
    d, leagues = M.v36_lines(cache_path)
    hz = M.role_frame(d)
    priors = M.role_priors(d)
    p0 = M.role_probs(hz, conditional=False)
    keep = pd.Series(np.where(hz["mkt_start"], 1.0, 0.0), index=hz.index)
    oracle = pd.Series(hz["t_start"].astype(float).to_numpy(), index=hz.index)
    d = M.mix_lines(d, hz, keep, "keep", priors)
    d = M.mix_lines(d, hz, p0, "rf0", priors)
    d = M.mix_lines(d, hz, oracle, "orc", priors)
    with psycopg.connect(get_settings().pipeline_dsn()) as conn:
        conn.read_only = True
        status = pd.DataFrame(conn.execute(STATUS_SQL, (min(M.TESTS), max(M.TESTS))).fetchall(),
                              columns=["gsis_id", "season", "week", "roster_status", "report_status"])
    o = hg_outcome(d, status)
    tests = d["season"].isin(M.TESTS).to_numpy()
    later = o["case"].to_numpy() != "not a later-week row"
    print("\n### hg1.0's cases on the later-week QB rows of 2021-2025 (rows; each house scoring grades the same rows)\n")
    print(o.loc[tests & later, "case"].value_counts().to_string())
    by_role = pd.crosstab(o.loc[tests & later, "case"], hz.reindex(d.index).loc[tests & later, "mkt_start"])
    print("\nby the market week's role (True = listed starter):\n" + by_role.to_string())
    names = {"v3.6": "hb0", "keeps the job": "keep", "rf1.0": "rf0", "oracle": "orc"}
    r = M.priced_frame(d, leagues, names)
    n = len(d)
    g = np.tile(o["graded"].to_numpy(), len(leagues))
    z = np.tile(o["zero"].to_numpy(), len(leagues))
    hzr = r["kind"].eq("horizon").to_numpy() & r["h"].fillna(0).ge(2).to_numpy()
    assert len(r) == n * len(leagues)
    r.loc[hzr, "ok"] = g[hzr]
    r.loc[hzr & z, "actual"] = 0.0
    print("\n### hg1.0, 2-8 weeks pooled, both house scorings (MAE / Spearman by season; mean = pooled)\n")
    print(Q.table({k: Q.horizon_seasons(r, k) for k in names}))
    print("\n### hg1.0 by horizon (seasons averaged, both scorings)\n")
    print(pd.concat({k: Q.by_h(r, k) for k in names}, axis=1).round(3).to_string())
    for lid in leagues:
        print(f"\n### hg1.0, league {lid[-6:]} only\n")
        print(Q.table({k: Q.horizon_seasons(r, k, league=lid) for k in names}))
    base = Q.horizon_seasons(r, "v3.6")
    print("\n### What hg1.0 would have decided (against v3.6: MAE lower pooled and in >= 4 of 5, Spearman not lower)\n")
    for k in ("keeps the job", "rf1.0", "oracle"):
        c = Q.horizon_seasons(r, k)
        dm, ds = c["mae"] - base["mae"], c["spearman"] - base["spearman"]
        better = bool(c["mae"].mean() < base["mae"].mean() and int((dm < 0).sum()) >= 4 and c["spearman"].mean() >= base["spearman"].mean())
        print(f"{k}: MAE {c['mae'].mean():.3f} vs {base['mae'].mean():.3f} (lower in {int((dm < 0).sum())} of 5; "
              f"Δ {np.round(dm.to_numpy(), 3).tolist()}), Spearman {c['spearman'].mean():.4f} vs {base['spearman'].mean():.4f} "
              f"(Δ {np.round(ds.to_numpy(), 4).tolist()}) -> {'better' if better else 'not better'}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", type=Path, required=True)
    a = ap.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(message)s")
    run(a.cache)


if __name__ == "__main__":
    main()
