"""IX-6 (Wave I-X), item 0: does `project` say the same thing twice? Runs the compute half of
``projections.project`` (the frame, the fits, the predictions, the QB pass-TD, horizon and market blends: everything
up to the priced line, no writes) and saves the lines; two runs in two processes at one database state are compared
cell by cell.

    uv run python scripts/analysis/ix6_determinism.py run OUT.pkl
    uv run python scripts/analysis/ix6_determinism.py compare A.pkl B.pkl
"""

from __future__ import annotations

import sys

import pandas as pd


def run(out: str) -> None:
    from league_lab import calibration as cal
    from league_lab import projections as P
    from league_lab.db import connect

    with connect() as conn:
        leagues = P.league_scorings(conn)
        references = P.reference_scorings(conn)
        fit, _source = P.fit_scorings(leagues, references)
        seasons = P.available_seasons(conn)
        season = max(seasons)
        frame = P.load_frame(conn, seasons)
        train = frame[frame["season"] < season]
        target = cal.future_inputs(frame[frame["season"] == season])
        preds, models = [], {}
        for pos in P.POSITIONS:
            models[pos] = m = P.fit_position(train, pos, fit)
            preds.append(P.predict_position(m, target[target["position"] == pos], fit))
        every = pd.concat(preds, ignore_index=True)
        every = cal.pass_td_lines(season, every, models, target, train, fit)
        every = cal.horizon_blend_lines(season, every, models, target, train, fit, leagues)
        every = cal.blend_lines(conn, season, every, models, target, fit, leagues)
    frame.to_pickle(out + ".frame")
    every.to_pickle(out)


def compare(a: str, b: str) -> None:
    for kind, x, y in (("frame", pd.read_pickle(a + ".frame"), pd.read_pickle(b + ".frame")),
                       ("every", pd.read_pickle(a), pd.read_pickle(b))):
        keys = [k for k in ("league_id", "gsis_id", "season", "week") if k in x.columns]
        x = x.sort_values(keys).reset_index(drop=True)
        y = y.sort_values(keys).reset_index(drop=True)
        if len(x) != len(y):
            print(f"{kind}: rows {len(x)} vs {len(y)}")
            continue
        diff = {}
        for c in x.columns:
            if c in ("fitted_at",):
                continue
            u, v = x[c], y[c]
            ne = ~((u == v) | (u.isna() & v.isna()))
            if ne.any():
                diff[c] = int(ne.sum())
        print(f"{kind}: {len(x)} rows; columns differing: {diff or 'none'}; cells differing: {sum(diff.values())}")


if __name__ == "__main__":
    {"run": lambda: run(sys.argv[2]), "compare": lambda: compare(sys.argv[2], sys.argv[3])}[sys.argv[1]]()
