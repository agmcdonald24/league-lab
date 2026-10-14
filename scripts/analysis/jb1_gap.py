"""JB-1 (Wave J-B): where we lose to Sleeper (gp1.0, docs/METRICS.md) and the first fix's walk-forward.

    uv run python scripts/analysis/jb1_gap.py run OUT.parquet        # h2h.build_ours with the stat line kept (the
                                                                      # switches in the environment decide the variant)
    uv run python scripts/analysis/jb1_gap.py diagnose BASE.parquet  # gp1.0's slices (markdown on stdout)
    uv run python scripts/analysis/jb1_gap.py compare BASE.parquet CAND.parquet [...]   # gp1.0's ship rule

OMP_NUM_THREADS=1, one run at a time (about 8.5 minutes each).
"""

from __future__ import annotations

import logging
import sys
import time


def run(out: str) -> None:
    import psycopg

    from league_lab import h2h
    from league_lab.config import get_settings

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    t0 = time.time()
    with psycopg.connect(get_settings().pipeline_dsn()) as conn:
        rows = h2h.build_ours(conn, keep_lines=True)
    rows.to_parquet(out)
    print(f"{out}: {len(rows)} rows in {time.time() - t0:.0f} s")


def diagnose(base: str) -> None:
    import pandas as pd
    import psycopg

    from league_lab import h2h_gap
    from league_lab import projections as P
    from league_lab.config import get_settings

    lines = pd.read_parquet(base)
    with psycopg.connect(get_settings().pipeline_dsn()) as conn:
        scoring = next(iter(P.league_scorings(conn).values()))[1]
        pop = h2h_gap.population(conn, lines=lines)
        # the walk-forward re-run's points against the stored rows the population graded (the same code and inputs?)
        x = pop[pop["season"] <= 2025].merge(
            lines[lines["league_id"] == pop["league_id"].iloc[0]][["gsis_id", "season", "week", "proj_points"]],
            on=["gsis_id", "season", "week"], how="left")
        diff = (x["proj_points"].round(2) - x["ours"]).abs()
        print(f"re-run vs stored ops.h2h_ours (2023-2025, {len(x):,} rows): identical to the cent {int((diff < 0.005).sum()):,}, "
              f"mean |diff| {diff.mean():.4f}, max {diff.max():.3f}, missing {int(x['proj_points'].isna().sum())}")
        res = h2h_gap.diagnose(pop, scoring)
    print(h2h_gap.study_markdown(res, pop))
    for r in h2h_gap.leaders(res).itertuples():
        cell = pop[pop["slice_position × tier"] == r.slice]
        sub = {f: h2h_gap.family_table(cell, f"slice_{f}") for f in h2h_gap.FAMILIES if f not in ("position × tier",)}
        sub["component"] = h2h_gap.component_table(cell[cell["season"] <= 2025], scoring)
        print(h2h_gap.study_markdown(sub, cell).replace("## gp1.0 diagnosis", f"## inside {r.slice}"))


def compare(base: str, *cands: str) -> None:
    import pandas as pd
    import psycopg

    from league_lab import h2h_gap
    from league_lab.config import get_settings

    with psycopg.connect(get_settings().pipeline_dsn()) as conn:
        sl = h2h_gap.sleeper_rows(conn)
    b = pd.read_parquet(base)
    for c in cands:
        print(h2h_gap.ship_markdown(c, h2h_gap.ship_rule(b, pd.read_parquet(c), sl)))


if __name__ == "__main__":
    cmd, *args = sys.argv[1:]
    {"run": run, "diagnose": diagnose, "compare": compare}[cmd](*args)
