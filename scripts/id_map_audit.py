"""The id-map audit (Wave I-K, IK-3): can an ESPN / Yahoo / MFL roster be read as Sleeper ids?

League Lab values players by Sleeper id (and gsis id). A league opened from another provider names its players by that
provider's id; ``player_ids`` translates them through nflverse / dynastyprocess ``ff_playerids`` (``mfl_id``,
``espn_id``, ``yahoo_id`` -> ``gsis_id`` / ``sleeper_id``). This script measures, for the players that matter — this
season's QB / RB / WR / TE — how many carry each provider's id, read-only:

* **dim_player**: ``analytics.dim_player``, skill positions, ``last_season`` = the season (joined to ff by ``gsis_id``);
* **Sleeper directory**: ``staging.stg_sleeper__players``, skill positions, active with an NFL team (joined to ff by
  ``sleeper_id``) — Sleeper's own ``espn_id`` / ``yahoo_id`` fields are counted too (a second source);
* **rostered**: the players on a roster in a house league this season (``analytics.mart_player_availability``), the
  ones a league screen actually shows.

ff_playerids comes from the database (``raw.nfl_ff_playerids``, the nightly's copy) or a CSV (``--csv``: the file the
API downloads, ``LEAGUE_LAB_CACHE_DIR/db_playerids.csv``). **Duplicates**: an external id on two or more ff rows that
name different players (gsis / sleeper) is listed as quarantined — the rule (docs/ANY_LEAGUE.md § "The id map"): a
quarantined id answers no match (never "the first row wins"); the adapter's next step (a unique name + position in
Sleeper's directory, reported as "name") or the unmapped row (``espn:<id>`` / ``yahoo:<id>``, listed, unvalued) takes it.

Usage (repository root; reads the database in .env):
    uv run python scripts/id_map_audit.py                    # the markdown table
    uv run python scripts/id_map_audit.py --season 2026 --json
    uv run python scripts/id_map_audit.py --csv path/to/db_playerids.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

SKILL = ("QB", "RB", "WR", "TE")
IDS = ("espn_id", "yahoo_id", "mfl_id")
NA = {"", "NA", "None", "none", "nan", "NaN", "NULL", "null"}


def clean(v) -> str | None:
    s = str(v).strip() if v is not None else ""
    if s in NA:
        return None
    return s[:-2] if s.endswith(".0") and s[:-2].isdigit() else s


def ff_rows(conn, csv_path: Path | None) -> list[dict]:
    cols = ("gsis_id", "sleeper_id", *IDS, "name", "position")
    if csv_path is not None:
        with csv_path.open(newline="", encoding="utf-8") as fh:
            return [{c: clean(r.get(c)) for c in cols} for r in csv.DictReader(fh)]
    with conn.cursor() as cur:
        cur.execute(f"select {', '.join(cols)} from raw.nfl_ff_playerids")
        return [{c: clean(v) for c, v in zip(cols, row, strict=True)} for row in cur.fetchall()]


def duplicates(rows: list[dict]) -> dict[str, dict[str, list[dict]]]:
    """id column -> {external id: [the rows]} for ids on rows naming two or more different players."""
    out: dict[str, dict[str, list[dict]]] = {}
    for col in IDS:
        by: dict[str, list[dict]] = defaultdict(list)
        for r in rows:
            if r[col]:
                by[r[col]].append(r)
        out[col] = {k: v for k, v in by.items()
                    if len({(x["gsis_id"], x["sleeper_id"]) for x in v}) > 1}
    return out


def population(conn, kind: str, season: int) -> list[dict]:
    """[{gsis_id, sleeper_id, name, position, sl_espn, sl_yahoo}] for one population."""
    sql = {
        "dim_player": """select d.gsis_id, d.sleeper_id, d.player_name, d.position, s.espn_id, s.yahoo_id
                         from analytics.dim_player d
                         left join staging.stg_sleeper__players s on s.sleeper_player_id = d.sleeper_id
                         where d.position = any(%s) and d.last_season = %s""",
        "sleeper": """select s.gsis_id, s.sleeper_player_id, s.full_name, s.position, s.espn_id, s.yahoo_id
                      from staging.stg_sleeper__players s
                      where s.position = any(%s) and s.active and s.team is not null and %s = %s""",
        "rostered": """select distinct on (a.gsis_id) a.gsis_id, a.sleeper_id, a.player_name, a.position, s.espn_id, s.yahoo_id
                       from analytics.mart_player_availability a
                       left join staging.stg_sleeper__players s on s.sleeper_player_id = a.sleeper_id
                       where a.position = any(%s) and a.season = %s and a.rostered_by_roster_id is not null""",
    }[kind]
    params = (list(SKILL), season) if kind != "sleeper" else (list(SKILL), season, season)
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return [{"gsis_id": clean(g), "sleeper_id": clean(s), "name": n, "position": p, "sl_espn": clean(e),
                 "sl_yahoo": clean(y)} for g, s, n, p, e, y in cur.fetchall()]


def measure(pop: list[dict], rows: list[dict], quarantined: dict[str, set[str]]) -> dict:
    by_gsis = {r["gsis_id"]: r for r in rows if r["gsis_id"]}
    by_sleeper = {r["sleeper_id"]: r for r in rows if r["sleeper_id"]}
    n = len(pop)
    out = {"players": n, "in_ff": 0, **{c: 0 for c in IDS}, **{f"{c}_usable": 0 for c in IDS},
           "sleeper_espn_id": 0, "sleeper_yahoo_id": 0, "espn_either": 0, "yahoo_either": 0,
           "espn_disagree": 0, "yahoo_disagree": 0}
    for p in pop:
        r = by_gsis.get(p["gsis_id"] or "") or by_sleeper.get(p["sleeper_id"] or "")
        if r:
            out["in_ff"] += 1
        for c in IDS:
            v = (r or {}).get(c)
            if v:
                out[c] += 1
                if v not in quarantined[c]:
                    out[f"{c}_usable"] += 1
        for c, sl in (("espn_id", "sl_espn"), ("yahoo_id", "sl_yahoo")):
            short = c.split("_")[0]
            if p[sl]:
                out[f"sleeper_{c}"] += 1
            if p[sl] or (r or {}).get(c):
                out[f"{short}_either"] += 1
            if p[sl] and (r or {}).get(c) and p[sl] != r[c]:
                out[f"{short}_disagree"] += 1
    return out


def pct(k: int, n: int) -> str:
    return f"{k:,} ({100 * k / n:.1f}%)" if n else "0"


def table(res: dict) -> str:
    pops = [("dim_player", "dim_player 2026 QB–TE"), ("sleeper", "Sleeper directory, active QB–TE"),
            ("rostered", "rostered in a house league")]
    head = "| measure | " + " | ".join(lbl for k, lbl in pops if k in res["populations"]) + " |"
    sep = "|---|" + "---|" * sum(1 for k, _ in pops if k in res["populations"])
    lines = [head, sep]
    rows = [("players", "players"), ("in_ff", "a row in ff_playerids"), ("espn_id", "espn_id in ff"),
            ("espn_id_usable", "espn_id usable (not quarantined)"), ("sleeper_espn_id", "espn_id in Sleeper's directory"),
            ("espn_either", "espn_id in either"), ("espn_disagree", "ff and Sleeper disagree (espn)"),
            ("yahoo_id", "yahoo_id in ff"), ("yahoo_id_usable", "yahoo_id usable (not quarantined)"),
            ("sleeper_yahoo_id", "yahoo_id in Sleeper's directory"), ("yahoo_either", "yahoo_id in either"),
            ("yahoo_disagree", "ff and Sleeper disagree (yahoo)"), ("mfl_id", "mfl_id in ff"),
            ("mfl_id_usable", "mfl_id usable (not quarantined)")]
    for key, label in rows:
        cells = []
        for k, _ in pops:
            if k not in res["populations"]:
                continue
            m = res["populations"][k]
            cells.append(f"{m[key]:,}" if key == "players" else pct(m[key], m["players"]))
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    q = res["quarantine"]
    lines.append("")
    lines.append(f"ff_playerids: {res['ff_rows']:,} rows ({res['ff_source']}). Quarantined (one id, two or more players): "
                 + ", ".join(f"{c} {len(q[c])}" for c in IDS) + ".")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--csv", type=Path, default=None, help="read ff_playerids from this CSV instead of the database")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--list-quarantine", action="store_true")
    a = ap.parse_args(argv)
    from league_lab.db import connect
    with connect(autocommit=True) as conn:
        conn.read_only = True
        rows = ff_rows(conn, a.csv)
        dups = duplicates(rows)
        quarantined = {c: set(dups[c]) for c in IDS}
        res = {"season": a.season, "ff_rows": len(rows), "ff_source": str(a.csv) if a.csv else "raw.nfl_ff_playerids",
               "populations": {}, "quarantine": {c: sorted(dups[c]) for c in IDS}}
        for kind in ("dim_player", "sleeper", "rostered"):
            try:
                res["populations"][kind] = measure(population(conn, kind, a.season), rows, quarantined)
            except Exception as exc:  # noqa: BLE001 - a population this database cannot answer is left out, said so
                print(f"(left out: {kind}: {exc.__class__.__name__})", file=sys.stderr)
    if a.json:
        print(json.dumps(res, indent=2))
    else:
        print(table(res))
        if a.list_quarantine:
            for c in IDS:
                for k, v in sorted(dups[c].items()):
                    print(f"  {c} {k}: " + "; ".join(f"{x['name']} {x['position']} gsis={x['gsis_id']} sleeper={x['sleeper_id']}"
                                                     for x in v))
    return 0


if __name__ == "__main__":
    sys.exit(main())
