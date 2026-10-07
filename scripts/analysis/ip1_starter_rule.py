"""IP-1 fix round (Wave I-P): st1.1 -- who starts at quarterback, judged on identification accuracy
(docs/METRICS.md § "st1.1: the listed starter unless the evidence says it is stale"). Read only.

Needs ``int_pn_team_game`` built with the rule on (``uv run league-lab dbt build --select int_pn_team_game+
--vars '{pn_starter_stale_rule: true}'``): its ``listed_qb_id`` is the schedule's listing, ``starting_qb_id`` the pick.

* the confusion table: played team-weeks 2022 .. 2026 week 4 where the listing is not the QB with the team's most
  dropbacks in the game, or the pick is not the listing -- fixed / still wrong / newly broken, by season;
* the week to come (``--week``): every team whose pick is not its listing, with who and why;
* the QB board (``--harness rows.parquet``): the walk-forward of 2021-2025 with the features as built (training and
  test), the v3.0 baseline rows of ``ip1_qb_diagnosis.py``; pooled MAE change over every scored QB player-week.

usage: OMP_NUM_THREADS=1 uv run python scripts/analysis/ip1_starter_rule.py [--week 2026 5] [--harness rows.parquet]
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import psycopg  # noqa: E402

from league_lab import projections as P  # noqa: E402
from league_lab.config import get_settings  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ip1_qb_candidates as K  # noqa: E402

log = logging.getLogger("ip1")
SEASONS = (2022, 2026)        # evaluated: 2022 .. 2026 (2026 through the newest played week)

TEAM_GAME_SQL = """select season, week, game_id, team, listed_qb_id, starting_qb_id, is_played
                   from intermediate.int_pn_team_game where season between %s and %s"""
DROPBACKS_SQL = """select game_id, posteam as team, coalesce(passer_player_id, rusher_player_id) as gsis_id, count(*) as dropbacks
                   from analytics.fct_play
                   where season_type = 'REG' and is_dropback and not is_no_play and season between %s and %s
                     and coalesce(passer_player_id, rusher_player_id) is not null
                   group by 1, 2, 3"""
NAMES_SQL = "select gsis_id, player_name from analytics.dim_player"
AVAIL_SQL = """select r.gsis_id, r.season, r.week, r.team, r.roster_status, i.report_status
               from intermediate.int_player_week_team as r
               left join staging.stg_nflverse__injuries as i
                 on i.gsis_id = r.gsis_id and i.season = r.season and i.week = r.week and i.game_type = 'REG'
               where r.season_type = 'REG' and r.season = %s and r.gsis_id = any(%s)"""


def kd(team: pd.Series) -> pd.Series:
    """kd_team: one code per franchise (dbt/macros/kd_team.sql)."""
    return team.replace({"OAK": "LV", "SD": "LAC", "STL": "LA"})


def classify(tg: pd.DataFrame, dbk: pd.DataFrame) -> pd.DataFrame:
    """Played team-weeks with: truth (most dropbacks), whether the listed QB took a dropback, and the class."""
    d = dbk.assign(team=kd(dbk["team"]))
    top = d.sort_values(["game_id", "team", "dropbacks", "gsis_id"], ascending=[True, True, False, True]) \
           .drop_duplicates(["game_id", "team"]).rename(columns={"gsis_id": "truth"})[["game_id", "team", "truth"]]
    played = tg[tg["is_played"]].merge(top, on=["game_id", "team"], how="left")
    took = set(zip(d["game_id"], d["team"], d["gsis_id"], strict=True))
    played["listed_dropback"] = [(g, t, q) in took for g, t, q in zip(played["game_id"], played["team"], played["listed_qb_id"], strict=True)]
    listed_ok = played["listed_qb_id"] == played["truth"]
    stale = ~listed_ok & ~played["listed_dropback"]
    in_game = ~listed_ok & played["listed_dropback"]
    changed = played["starting_qb_id"] != played["listed_qb_id"]
    pick_ok = played["starting_qb_id"] == played["truth"]
    played["cls"] = np.select(
        [stale & pick_ok, stale & ~pick_ok, (listed_ok | in_game) & changed, in_game],
        ["fixed", "still wrong", "newly broken", "in-game change (kept)"], default="")
    return played[played["truth"].notna() & (~listed_ok | changed)]


def confusion(ev: pd.DataFrame) -> pd.DataFrame:
    t = ev.groupby(["season", "cls"]).size().unstack(fill_value=0)
    for c in ("fixed", "still wrong", "newly broken", "in-game change (kept)"):
        if c not in t:
            t[c] = 0
    t = t[["fixed", "still wrong", "newly broken", "in-game change (kept)"]]
    t.loc["all"] = t.sum()
    t["stale listings"] = t["fixed"] + t["still wrong"]
    return t


def unclear_flag(tg: pd.DataFrame, dbk: pd.DataFrame) -> pd.DataFrame:
    """The alternative for the screen (not built): a team-week is 'starter unclear' when its listed QB took no dropback in
    the team's newest played game of the season while another QB led its dropbacks. Per played team-week 2022 .. : the
    flag (as of the week) against whether the listing turned out right (precision) and how many stale listings it flags."""
    d = dbk.assign(team=kd(dbk["team"]))
    top = d.sort_values(["game_id", "team", "dropbacks", "gsis_id"], ascending=[True, True, False, True]) \
           .drop_duplicates(["game_id", "team"]).rename(columns={"gsis_id": "lead"})[["game_id", "team", "lead"]]
    took = set(zip(d["game_id"], d["team"], d["gsis_id"], strict=True))
    g = tg.merge(top, on=["game_id", "team"], how="left").sort_values(["team", "season", "week"])
    out = []
    for (_team, _season), x in g.groupby(["team", "season"], sort=False):
        prev_game = prev_lead = None
        for r in x.itertuples():
            flag = (r.listed_qb_id is not None and prev_game is not None and prev_lead is not None
                    and prev_lead != r.listed_qb_id and (prev_game, r.team, r.listed_qb_id) not in took)
            out.append({"season": r.season, "week": r.week, "team": r.team, "game_id": r.game_id, "is_played": r.is_played,
                        "unclear": bool(flag)})
            if r.is_played:
                prev_game, prev_lead = r.game_id, r.lead
    return pd.DataFrame(out)


def week_changes(conn, tg: pd.DataFrame, dbk: pd.DataFrame, season: int, week: int, names: dict) -> pd.DataFrame:
    w = tg[(tg["season"] == season) & (tg["week"] == week) & (tg["starting_qb_id"] != tg["listed_qb_id"])]
    if w.empty:
        return w
    d = dbk.assign(team=kd(dbk["team"]))
    played = tg[(tg["season"] == season) & tg["is_played"] & (tg["week"] < week)]
    av = pd.DataFrame(conn.execute(AVAIL_SQL, (season, w["listed_qb_id"].tolist())).fetchall(),
                      columns=["gsis_id", "season", "week", "team", "roster_status", "report_status"])
    out = []
    for r in w.itertuples():
        g = played[played["team"] == r.team].sort_values("week", ascending=False).head(2)
        why = []
        for x in g.itertuples():
            led = d[(d["game_id"] == x.game_id) & (d["team"] == r.team)].sort_values("dropbacks", ascending=False)
            lead = led.iloc[0] if len(led) else None
            st = av[(av["gsis_id"] == r.listed_qb_id) & (av["week"] == x.week)]
            why.append(f"wk {x.week}: listed {names.get(x.listed_qb_id, x.listed_qb_id)}, "
                       f"{names.get(lead['gsis_id'], '?') if lead is not None else '?'} {int(lead['dropbacks']) if lead is not None else 0} dropbacks, "
                       f"{names.get(r.listed_qb_id, r.listed_qb_id)} 0 and "
                       f"{(st['roster_status'].iloc[0] if len(st) else 'not on the roster')}"
                       f"{'' if not len(st) or not isinstance(st['report_status'].iloc[0], str) else ' / ' + st['report_status'].iloc[0]}")
        out.append({"team": r.team, "listed": names.get(r.listed_qb_id, r.listed_qb_id),
                    "pick": names.get(r.starting_qb_id, r.starting_qb_id), "why": "; ".join(why)})
    return pd.DataFrame(out)


def harness(rows_path: Path) -> None:
    """The QB board: the walk-forward 2021-2025 on the features as built now (st1.1 in training and test) against the
    v3.0 baseline rows (the features before)."""
    rows = pd.read_parquet(rows_path)
    rows["season"], rows["week"] = rows["season"].astype(int), rows["week"].astype(int)
    with psycopg.connect(get_settings().pipeline_dsn()) as conn:
        conn.read_only = True
        leagues = P.league_scorings(conn)
        alls = P.available_seasons(conn)
        frame = P.load_frame(conn, [x for x in alls if x <= 2025])
    first, feats = min(alls), list(P.FEATURES_BY_POSITION["QB"])
    preds = []
    for s in K.TESTS:
        t0 = time.monotonic()
        train = frame[(frame["season"] >= first) & (frame["season"] < s)]
        d = train[(train["position"] == "QB") & train["played"] & ~train["no_history"]]
        d = d.dropna(subset=[f"out_{c}" for c in P.COMPONENTS["QB"]]).reset_index(drop=True)
        models = P._fit_components(P._matrix(d, feats), d, "QB")
        test = frame[(frame["season"] == s) & (frame["position"] == "QB")].reset_index(drop=True)
        x = P._matrix(test, feats)
        out = test[["gsis_id", "season", "week", "played", *[f"out_{c}" for c in P.ALL_COMPONENTS]]].copy()
        out["season"], out["week"] = out["season"].astype(int), out["week"].astype(int)
        for c in P.ALL_COMPONENTS:
            out[f"st_{c}"] = np.clip(models[c].predict(x), 0, None) if c in models else 0.0
        preds.append(out)
        log.info("st1.1 board %s: %.0f s", s, time.monotonic() - t0)
    cand = pd.concat(preds, ignore_index=True)
    base = K.priced(rows[(rows["position"] == "QB") & rows["season"].isin(K.TESTS)], "v3_", leagues)
    alt = K.priced(cand, "st_", leagues)
    m = base.merge(alt, on=["league_id", "gsis_id", "season", "week"], suffixes=("_b", "_a"))
    pooled = float((m["proj_a"] - m["actual_a"]).abs().mean() - (m["proj_b"] - m["actual_b"]).abs().mean())
    print(f"\nQB board, pooled MAE change over {len(m) // len(leagues)} QB player-weeks a scoring (both scorings): {pooled:+.4f}"
          f" (rule (c): <= +0.01)")
    K.report("st1.1 on the QB board (information: decide is the model rule, not this one's)", K.paired(base, alt), base, alt)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", nargs=2, type=int, default=None)
    ap.add_argument("--harness", type=Path, default=None)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    with psycopg.connect(get_settings().pipeline_dsn()) as conn:
        conn.read_only = True
        tg = pd.DataFrame(conn.execute(TEAM_GAME_SQL, SEASONS).fetchall(),
                          columns=["season", "week", "game_id", "team", "listed_qb_id", "starting_qb_id", "is_played"])
        if (tg["starting_qb_id"].fillna("") == tg["listed_qb_id"].fillna("")).all():
            raise SystemExit("int_pn_team_game picks the listing everywhere: build it with --vars '{pn_starter_stale_rule: true}'")
        dbk = pd.DataFrame(conn.execute(DROPBACKS_SQL, SEASONS).fetchall(), columns=["game_id", "team", "gsis_id", "dropbacks"])
        names = dict(conn.execute(NAMES_SQL).fetchall())
        ev = classify(tg, dbk)
        t = confusion(ev)
        print("### st1.1: the confusion table (played team-weeks 2022 .. 2026 where the listing missed or the pick moved)\n")
        print(t.to_string())
        a = t.loc["all"]
        fixed, stale, broken = int(a["fixed"]), int(a["stale listings"]), int(a["newly broken"])
        print(f"\n(a) fixed / stale = {fixed} / {stale} = {fixed / stale:.0%} (needs >= 60%)")
        print(f"(b) newly broken {broken} <= fixed / 6 = {fixed / 6:.1f}: {'pass' if broken <= fixed / 6 else 'FAIL'}")
        print("\nevery changed pick and every stale listing:")
        show = ev[ev["cls"] != "in-game change (kept)"].assign(
            listed=lambda x: x["listed_qb_id"].map(names), pick=lambda x: x["starting_qb_id"].map(names),
            truth_name=lambda x: x["truth"].map(names))
        print(show[["season", "week", "team", "listed", "pick", "truth_name", "cls"]].sort_values(["season", "team", "week"]).to_string(index=False))
        fl = unclear_flag(tg, dbk)
        cl = classify(tg, dbk)[["game_id", "team", "cls"]]
        pl = fl[fl["is_played"]].merge(cl, on=["game_id", "team"], how="left")
        stale_rows = pl["cls"].isin(["fixed", "still wrong"])
        print("\n### the alternative ('starter unclear', not built): played team-weeks flagged, by season")
        print(pl.assign(stale=stale_rows).groupby("season").agg(flagged=("unclear", "sum"),
              flagged_stale=("stale", lambda s_: int((s_ & pl.loc[s_.index, "unclear"]).sum())),
              stale=("stale", "sum"), team_weeks=("unclear", "size")).to_string())
        if args.week:
            w = fl[(fl["season"] == args.week[0]) & (fl["week"] == args.week[1]) & fl["unclear"]]
            print(f"flagged in {args.week[0]} week {args.week[1]}: {', '.join(w['team'])}")
        if args.week:
            print(f"\n### {args.week[0]} week {args.week[1]}: the picks that are not the listing\n")
            print(week_changes(conn, tg, dbk, args.week[0], args.week[1], names).to_string(index=False))
    if args.harness:
        harness(args.harness)


if __name__ == "__main__":
    main()
