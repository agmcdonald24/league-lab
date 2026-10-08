"""IQ-2 (Wave I-Q): who starts at quarterback -- the candidate sources for an unplayed game's starter, judged on
identification (docs/METRICS.md § "Who starts": the keep rule, written at 19:36 ET before any number was read). Read only.

* ``asof``: the as-of proof -- how long before kickoff the newest depth-chart snapshot was taken, and how often the
  snapshot before a game names a different first quarterback from the first snapshot after it (a chart rebuilt after
  the fact would never differ);
* ``study``: per played team-game 2021 - 2026 week 4, the truth (the team's dropback leader), the listing and each
  candidate's pick (S1 depth QB1, S2 depth first available, S3 listing unless ruled out, S4 two sources agree); per
  candidate and window: accuracy, on the stale listings, fixed / newly broken / still wrong, the rule's verdict; and the
  ``starters.unclear`` triggers U0 - U3 (flags, stale listings caught).

The pure part (``picks``, ``score``, ``triggers``) takes plain frames: tests/test_iq2_starter_source.py.

usage: OMP_NUM_THREADS=1 uv run python scripts/analysis/iq2_starter_source.py asof|study [--csv out.csv]
"""
from __future__ import annotations

import argparse
import os
import sys

os.environ.setdefault("OMP_NUM_THREADS", "1")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

SEASONS = (2021, 2026)
DEPTH_FROM = 2025                      # the first season with stored depth charts (nflverse daily snapshots)
OUT_REPORT = {"Out", "Doubtful"}
AVAILABLE_ROSTER = {"ACT", "INA", "DEV"}   # INA (game-day inactive, 90 minutes before kickoff) is never read as out
CANDIDATES = ("S1", "S2", "S3", "S4")
NAMES = {"S0": "listing (base)", "S1": "depth chart QB1", "S2": "depth chart, first available",
         "S3": "listing unless ruled out", "S4": "two sources agree (own)"}

GAMES_SQL = """
select g.season, g.week, g.game_id, g.kickoff_at, t.team, nullif(t.qb, '') as listed_id
from analytics.dim_game as g
cross join lateral (values (g.home_team, g.home_qb_id), (g.away_team, g.away_qb_id)) as t(team, qb)
where g.season_type = 'REG' and g.season between %(a)s and %(b)s"""
DROPBACKS_SQL = """
select p.game_id, p.team, p.gsis_id, p.dropbacks::float8 as dropbacks
from analytics.fct_player_game as p
where p.season_type = 'REG' and p.season between %(a)s and %(b)s and coalesce(p.dropbacks, 0) > 0"""
DEPTH_SQL = """
select d.team, d.snapshot_at, d.gsis_id, d.pos_rank, d.pos_slot
from staging.stg_nflverse__depth_charts as d where d.pos_abb = 'QB'"""
REPORT_SQL = """
select i.season, i.week, i.gsis_id, i.report_status
from staging.stg_nflverse__injuries as i
where i.game_type = 'REG' and i.season between %(a)s and %(b)s and i.report_status in ('Out', 'Doubtful')"""
ROSTER_SQL = """
select r.season, r.week, r.gsis_id, r.roster_status
from staging.stg_nflverse__rosters_weekly as r
where r.position = 'QB' and r.season between %(a)s and %(b)s"""


def _ns(t: pd.Series) -> np.ndarray:
    """Timestamps (any tz) -> int64 nanoseconds UTC (NaT -> min int)."""
    x = pd.to_datetime(t, utc=True).dt.tz_localize(None).to_numpy().astype("datetime64[ns]")
    return x.astype("int64")


def kd(team: pd.Series) -> pd.Series:
    return team.replace({"OAK": "LV", "SD": "LAC", "STL": "LA", "LAR": "LA"})


# ------------------------------------------------------------------------------------------------ the pure part
def team_games(games: pd.DataFrame, dropbacks: pd.DataFrame) -> pd.DataFrame:
    """Played team-games with the truth (the dropback leader), whether the listed QB dropped back, and the team's
    newest played game's leader before the week (this season): ``last_id``."""
    g = games.copy()
    g["team"] = kd(g["team"])
    d = dropbacks.copy()
    d["team"] = kd(d["team"])
    lead = (d.sort_values(["game_id", "team", "dropbacks", "gsis_id"], ascending=[True, True, False, True])
             .drop_duplicates(["game_id", "team"])[["game_id", "team", "gsis_id"]].rename(columns={"gsis_id": "truth_id"}))
    g = g.merge(lead, on=["game_id", "team"], how="left")
    dropped = set(zip(d["game_id"], d["team"], d["gsis_id"], strict=False))
    g["listed_dropped"] = [(a, b, c) in dropped for a, b, c in zip(g["game_id"], g["team"], g["listed_id"], strict=False)]
    g = g.sort_values(["team", "season", "week"]).reset_index(drop=True)
    # the newest played game before W this season (W's own game never counts)
    prev = g[g["truth_id"].notna()][["team", "season", "week", "truth_id"]].rename(
        columns={"week": "last_week", "truth_id": "last_id"})
    out = []
    for (team, season), grp in g.groupby(["team", "season"], sort=False):
        p = prev[(prev["team"] == team) & (prev["season"] == season)].sort_values("last_week")
        p = p.assign(last_week=p["last_week"].astype(float))
        x = grp.sort_values("week").copy()
        if len(p):
            m = pd.merge_asof(x[["week"]].assign(w=x["week"].astype(float) - 0.5).sort_values("w"), p[["last_week", "last_id"]],
                              left_on="w", right_on="last_week", direction="backward")
            x["last_week"], x["last_id"] = m["last_week"].to_numpy(), m["last_id"].to_numpy()
        else:
            x["last_week"], x["last_id"] = np.nan, None
        out.append(x)
    g = pd.concat(out, ignore_index=True)
    g["played"] = g["truth_id"].notna()
    g["stale"] = g["played"] & g["listed_id"].notna() & ~g["listed_dropped"]
    g["in_game_change"] = g["played"] & g["listed_dropped"] & (g["listed_id"] != g["truth_id"])
    return g


def depth_before(g: pd.DataFrame, depth: pd.DataFrame) -> pd.Series:
    """Per team-game: the quarterbacks (ordered) of the team's newest depth-chart snapshot taken before kickoff;
    None without one (no stored chart)."""
    dp = depth.copy()
    dp["team"] = kd(dp["team"])
    dp["snapshot_at"] = _ns(dp["snapshot_at"])
    order = (dp.sort_values(["team", "snapshot_at", "pos_rank", "pos_slot", "gsis_id"])
               .groupby(["team", "snapshot_at"], sort=True)["gsis_id"].agg(list).reset_index())
    out = pd.Series([None] * len(g), index=g.index, dtype=object)
    has_k = pd.to_datetime(g["kickoff_at"], utc=True).notna()
    k = pd.Series(np.where(has_k, _ns(g["kickoff_at"].where(has_k, pd.Timestamp("2000-01-01", tz="UTC"))), 0), index=g.index)
    for team, snaps in order.groupby("team"):
        idx = g.index[(g["team"] == team) & has_k]
        if not len(idx):
            continue
        times = snaps["snapshot_at"].to_numpy()
        pos = np.searchsorted(times, k.loc[idx].to_numpy(), side="left") - 1     # strictly before kickoff
        lists = snaps["gsis_id"].tolist()
        for i, p in zip(idx, pos, strict=False):
            out.loc[i] = lists[p] if p >= 0 else None
    return out


def ruled_out(g: pd.DataFrame, report: pd.DataFrame, roster: pd.DataFrame):
    """A function (season, week, gsis_id) -> True when week W's injury report says Out / Doubtful or his week-W
    weekly-roster status is outside ACT / INA / DEV (a missing row is unknown, never out)."""
    report = report[report["report_status"].isin(OUT_REPORT)]          # Out / Doubtful only (Questionable never)
    rep = set(zip(report["season"], report["week"], report["gsis_id"], strict=False))
    ros = {(s, w, q): st for s, w, q, st in zip(roster["season"], roster["week"], roster["gsis_id"], roster["roster_status"], strict=False)}

    def f(season, week, q) -> bool:
        if q is None or (isinstance(q, float) and np.isnan(q)):
            return False
        if (season, week, q) in rep:
            return True
        st = ros.get((season, week, q))
        return st is not None and st not in AVAILABLE_ROSTER
    return f


def picks(g: pd.DataFrame, out_fn) -> pd.DataFrame:
    """Each candidate's pick per team-game (``depth``: the ordered pre-kickoff chart or None)."""
    s1, s2, s3, s4 = [], [], [], []
    for r in g.itertuples():
        L, dq, last = r.listed_id, r.depth, r.last_id
        avail = [q for q in (dq or []) if not out_fn(r.season, r.week, q)]
        p1 = dq[0] if dq else None
        p2 = avail[0] if avail else L
        L_out = L is not None and out_fn(r.season, r.week, L)
        if not L_out:
            p3 = L
        elif dq:
            p3 = p2
        elif isinstance(last, str) and last != L and not out_fn(r.season, r.week, last):
            p3 = last
        else:
            p3 = L
        if dq is None:
            p4 = None
        elif L_out:
            p4 = p2
        elif avail and isinstance(last, str) and avail[0] == last and last != L:
            p4 = last
        else:
            p4 = L
        s1.append(p1)
        s2.append(p2 if dq is not None else None)
        s3.append(p3)
        s4.append(p4)
    out = g.copy()
    out["S0"], out["S1"], out["S2"], out["S3"], out["S4"] = g["listed_id"], s1, s2, s3, s4
    return out


def score(df: pd.DataFrame, cand: str) -> dict:
    """Identification on the played team-games where ``cand`` has a pick: the rule's numbers and verdict."""
    d = df[df["played"] & df[cand].notna()]
    right_l = d["listed_id"] == d["truth_id"]
    right_c = d[cand] == d["truth_id"]
    fixed, broken = int((~right_l & right_c).sum()), int((right_l & ~right_c).sum())
    stale = d["stale"]
    fixed_stale = int((stale & right_c).sum())
    n_stale = int(stale.sum())
    acc_l, acc_c = float(right_l.mean()) if len(d) else np.nan, float(right_c.mean()) if len(d) else np.nan
    a = bool(acc_c >= acc_l)
    b = bool(n_stale > 0 and fixed_stale >= 0.6 * n_stale)
    c = bool(broken <= fixed / 6.0)
    return {"candidate": cand, "name": NAMES[cand], "team_games": int(len(d)), "acc_listing": acc_l, "acc": acc_c,
            "stale": n_stale, "stale_fixed": fixed_stale,
            "acc_on_stale": float(right_c[stale].mean()) if n_stale else np.nan,
            "fixed": fixed, "newly_broken": broken, "still_wrong": int((~right_l & ~right_c).sum()),
            "in_game_changes": int(d["in_game_change"].sum()),
            "a_acc": a, "b_fix60": b, "c_break_1_in_6": c, "passes_abc": a and b and c}


def triggers(df: pd.DataFrame) -> pd.DataFrame:
    """starters.unclear's triggers per played team-week: U0 (su1.0: the listed QB took no dropback in the team's newest
    played game while another led it -- read as: that game's leader is someone else and the listed QB is not among its
    dropbacks), U1 (the listing differs from S2's pick), U2 = U0 or U1, U3 = U0 and U1."""
    d = df.copy()
    d["U0"] = d["listed_id"].notna() & d["last_id"].notna() & ~d["listed_last_dropped"]
    d["U1"] = d["listed_id"].notna() & d["S2"].notna() & (d["S2"] != d["listed_id"])
    d["U2"] = d["U0"] | d["U1"]
    d["U3"] = d["U0"] & d["U1"]
    return d


def trigger_table(d: pd.DataFrame) -> pd.DataFrame:
    rows = []
    p = d[d["played"]]
    for u in ("U0", "U1", "U2", "U3"):
        f = p[u]
        rows.append({"trigger": u, "flags": int(f.sum()), "stale_caught": int((f & p["stale"]).sum()),
                     "stale": int(p["stale"].sum()), "flags_not_stale": int((f & ~p["stale"]).sum())})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------------------------------------ the database part
def _read(sql: str, params: dict | None = None) -> pd.DataFrame:
    import psycopg

    from league_lab.config import get_settings
    with psycopg.connect(get_settings().pipeline_dsn()) as con:
        cur = con.execute(sql, params or {})
        cols = [c.name for c in cur.description]
        return pd.DataFrame(cur.fetchall(), columns=cols)


def load() -> pd.DataFrame:
    prm = {"a": SEASONS[0], "b": SEASONS[1]}
    games, dbk = _read(GAMES_SQL, prm), _read(DROPBACKS_SQL, prm)
    g = team_games(games, dbk)
    # did the listed QB drop back in the team's newest played game? (U0 reads it)
    d = dbk.copy()
    d["team"] = kd(d["team"])
    dropped = set(zip(d["team"], d["gsis_id"], d["game_id"], strict=False))
    gid = g[g["played"]].set_index(["team", "season", "week"])["game_id"].to_dict()
    g["listed_last_dropped"] = [
        (t, L, gid.get((t, s, lw))) in dropped if isinstance(L, str) and lw == lw else False
        for t, L, s, lw in zip(g["team"], g["listed_id"], g["season"], g["last_week"], strict=False)]
    depth = _read(DEPTH_SQL)
    g["depth"] = depth_before(g, depth)
    g.loc[g["season"] < DEPTH_FROM, "depth"] = None
    out_fn = ruled_out(g, _read(REPORT_SQL, prm), _read(ROSTER_SQL, prm))
    return triggers(picks(g, out_fn))


def asof() -> None:
    games = _read(GAMES_SQL, {"a": DEPTH_FROM, "b": SEASONS[1]})
    dbk = _read(DROPBACKS_SQL, {"a": DEPTH_FROM, "b": SEASONS[1]})
    g = team_games(games, dbk)
    g = g[g["played"]].reset_index(drop=True)
    depth = _read(DEPTH_SQL)
    depth["team"] = kd(depth["team"])
    depth["snapshot_at"] = _ns(depth["snapshot_at"])
    snaps = depth.groupby("team")["snapshot_at"].apply(lambda s: np.sort(s.unique()))
    k = _ns(g["kickoff_at"])
    lag, before, after = [], [], []
    qb1 = (depth.sort_values(["team", "snapshot_at", "pos_rank", "pos_slot", "gsis_id"])
                .drop_duplicates(["team", "snapshot_at"]).set_index(["team", "snapshot_at"])["gsis_id"])
    for t, kk in zip(g["team"], k, strict=False):
        ts = snaps.get(t)
        i = np.searchsorted(ts, kk, side="left")
        b = ts[i - 1] if i > 0 else None
        a = ts[i] if i < len(ts) else None
        lag.append((kk - b) / 3.6e12 if b is not None else np.nan)
        before.append(qb1.get((t, b)) if b is not None else None)
        after.append(qb1.get((t, a)) if a is not None else None)
    g["lag_h"], g["qb1_before"], g["qb1_after"] = lag, before, after
    has = g["qb1_before"].notna() & g["qb1_after"].notna()
    print(f"team-games {DEPTH_FROM}-2026 played: {len(g)}; with a snapshot before kickoff: {int(g['qb1_before'].notna().sum())}")
    print(f"hours from the newest snapshot to kickoff: median {np.nanmedian(lag):.1f}, 90th percentile {np.nanpercentile(lag, 90):.1f}, max {np.nanmax(lag):.1f}")
    ch = g[has & (g["qb1_before"] != g["qb1_after"])]
    print(f"QB1 before kickoff != QB1 of the first snapshot after: {len(ch)} of {int(has.sum())}")
    print(f"  of which the post-game QB1 is the game's dropback leader: {int((ch['qb1_after'] == ch['truth_id']).sum())}; "
          f"the pre-game QB1 is: {int((ch['qb1_before'] == ch['truth_id']).sum())}")
    print(ch[["season", "week", "team", "qb1_before", "qb1_after", "truth_id"]].head(20).to_string(index=False))


def study(csv: str | None) -> None:
    d = load()
    windows = {"2025 - 2026 wk 4 (depth charts)": d[d["season"] >= DEPTH_FROM],
               "2021 - 2026 wk 4": d}
    rows = []
    for wname, w in windows.items():
        for c in CANDIDATES:
            if wname.startswith("2021") and c != "S3":
                continue
            r = score(w, c)
            r["window"] = wname
            rows.append(r)
    t = pd.DataFrame(rows)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 30)
    print(t[["window", "candidate", "name", "team_games", "acc_listing", "acc", "stale", "stale_fixed", "acc_on_stale",
             "fixed", "newly_broken", "still_wrong", "in_game_changes", "a_acc", "b_fix60", "c_break_1_in_6",
             "passes_abc"]].to_string(index=False, float_format=lambda x: f"{x:.4f}"))
    print()
    print("by season (2021 - 2026 wk 4): stale listings, in-game changes, team-games")
    p = d[d["played"]]
    print(p.groupby("season").agg(team_games=("played", "size"), stale=("stale", "sum"),
                                   in_game=("in_game_change", "sum")).to_string())
    print()
    print("starters.unclear's triggers, 2025 - 2026 wk 4 (played team-weeks):")
    print(trigger_table(d[d["season"] >= DEPTH_FROM]).to_string(index=False))
    print()
    print("for reference, U0 on 2022 - 2026 wk 4 (su1.0's window):")
    print(trigger_table(d[d["season"] >= 2022]).head(1).to_string(index=False))
    print()
    w = d[(d["season"] >= DEPTH_FROM) & d["played"]]
    for c in CANDIDATES:
        bad = w[(w["listed_id"] == w["truth_id"]) & (w[c] != w["truth_id"]) & w[c].notna()]
        good = w[(w["listed_id"] != w["truth_id"]) & (w[c] == w["truth_id"])]
        print(f"{c}: newly broken {len(bad)}: " + ", ".join(f"{r.team} {r.season} wk {r.week}" for r in bad.head(12).itertuples()))
        print(f"{c}: fixed {len(good)}: " + ", ".join(f"{r.team} {r.season} wk {r.week}" for r in good.head(12).itertuples()))
    if csv:
        d.drop(columns=["depth"]).to_csv(csv, index=False)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("what", choices=["asof", "study"])
    ap.add_argument("--csv")
    a = ap.parse_args(argv)
    if a.what == "asof":
        asof()
    else:
        study(a.csv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
