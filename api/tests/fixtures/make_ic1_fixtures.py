"""Wave I-C (IC-1): the fictional Test League's per-player points, by construction (run once, from the repository root):

    uv run python api/tests/fixtures/make_ic1_fixtures.py

Adds ``players_points`` to ``sleeper/matchups_9000000000000000001_<1|2>.json``: every rostered player's points in the
Test League's own scoring, computed with the flat engine as it was before the ScoringSpec (``scoring.compute_points``
on the 2026 ``analytics.fct_player_game`` row, ``kdef.price`` on the ``analytics.mart_kd_week`` defense line). The
scoring check (``scoring_audit``) must then match 100% within 0.1 — the spec reproduces the old engine on real lines.
Nothing else in the files changes (the team totals stay the hand-made ones).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import psycopg
from league_lab import kdef
from league_lab.scoring import compute_points

FX = Path(__file__).with_name("sleeper")
TEST = "9000000000000000001"


def _dsn() -> str:
    env = {}
    for line in (Path(__file__).resolve().parents[3] / ".env").read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    g = lambda k: os.environ.get(k) or env.get(k)  # noqa: E731
    return (f"host={g('LEAGUE_LAB_DB_HOST')} port={g('LEAGUE_LAB_DB_PORT') or 5432} dbname={g('LEAGUE_LAB_DB_NAME')} "
            f"user={g('LEAGUE_LAB_DB_USER')} password={g('LEAGUE_LAB_DB_PASSWORD')}")


def main() -> None:
    league = json.loads((FX / f"league_{TEST}.json").read_text())
    scoring = {k: float(v) for k, v in league["scoring_settings"].items() if v is not None}
    rosters = json.loads((FX / f"rosters_{TEST}.json").read_text())
    with psycopg.connect(_dsn()) as conn:
        def q(sql, params):
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return pd.DataFrame(cur.fetchall(), columns=[c.name for c in cur.description])
        ids = sorted({str(p) for r in rosters for p in r["players"] if not str(p).isalpha()})
        idmap = q("select sleeper_id, gsis_id from analytics.player_id_map where sleeper_id = any(%s)", (ids,))
        to_gsis = dict(zip(idmap["sleeper_id"], idmap["gsis_id"], strict=False))
        for week in (1, 2):
            g = q("select * from analytics.fct_player_game where season = 2026 and week = %s and season_type = 'REG' "
                  "and gsis_id = any(%s)", (week, list(to_gsis.values())))
            by = {r["gsis_id"]: r for r in g.to_dict("records")}
            d = q("select * from analytics.mart_kd_week where season = 2026 and week = %s and position = 'DEF' and played",
                  (week,))
            d = kdef.with_pa_buckets(d, "out_")
            d["pts"] = kdef.price(d, "DEF", scoring, "out_")
            dpts = {("LAR" if t == "LA" else t): float(p) for t, p in zip(d["team"], d["pts"], strict=True)}
            path = FX / f"matchups_{TEST}_{week}.json"
            ms = json.loads(path.read_text())
            by_roster = {r["roster_id"]: r for r in rosters}
            for m in ms:
                pp = {}
                for pid in by_roster[m["roster_id"]]["players"]:
                    pid = str(pid)
                    if pid.isalpha():
                        if pid in dpts:
                            pp[pid] = round(dpts[pid], 2)
                        continue
                    row = by.get(to_gsis.get(pid))
                    if row is not None:
                        stats = {k: (0 if v is None else v) for k, v in row.items()}
                        pp[pid] = compute_points(stats, scoring)
                m["players_points"] = pp
            path.write_text(json.dumps(ms, indent=1) + "\n")
            print(week, sum(len(m["players_points"]) for m in ms), "players")


if __name__ == "__main__":
    main()
