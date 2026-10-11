"""IX-1 (Wave I-X), lf1.0: the grade of the on-field share estimate and of the left-early rule (docs/METRICS.md § "A
game left early"; the rule and its pick were committed before this script ran: 01a4f3a).

    uv run python scripts/analysis/ix1_left_early.py          # prints the tables

(a) the estimate (snaps) against the exact share (participation): mean absolute difference, all player-games and the
truly-left-early ones; (b) LE-A, LE-B (and the reference LE-0) against the participation truth: precision, recall, F1.
Reads ``intermediate.int_player_game_on_field`` on its own connection.
"""

from __future__ import annotations

import pandas as pd

from league_lab.db import connect

SQL = """
with f as (
    select o.*
    from intermediate.int_player_game_on_field as o
    where o.season between 2016 and 2025 and o.season_type = 'REG' and o.position in ('QB', 'RB', 'WR', 'TE')
),
team_games as (     -- each team's regular-season games in order
    select g.season, g.week, g.game_id, t.team,
           lead(g.game_id) over (partition by g.season, t.team order by g.week) as next_game_id,
           lead(g.week)    over (partition by g.season, t.team order by g.week) as next_week
    from analytics.dim_game as g
    cross join lateral (values (g.home_team), (g.away_team)) as t(team)
    where g.season between 2016 and 2025 and g.season_type = 'REG'
),
played as (
    select gsis_id, game_id from analytics.fct_player_game
    where season between 2016 and 2025 and season_type = 'REG' and played
),
report as (
    select distinct gsis_id, season, week from staging.stg_nflverse__injuries
    where report_status in ('Out', 'Doubtful', 'Questionable')
)
select f.*, tg.next_week,
       (tg.next_game_id is not null and pl.gsis_id is null) as missed_next,
       (rp.gsis_id is not null)                             as report_next
from f
left join team_games as tg on tg.game_id = f.game_id and tg.team = f.team
left join played as pl on pl.gsis_id = f.gsis_id and pl.game_id = tg.next_game_id
left join report as rp on rp.gsis_id = f.gsis_id and rp.season = f.season and rp.week = tg.next_week
"""


def prf(pred: pd.Series, truth: pd.Series) -> dict:
    tp = int((pred & truth).sum())
    fp = int((pred & ~truth).sum())
    fn = int((~pred & truth).sum())
    p = tp / (tp + fp) if tp + fp else float("nan")
    r = tp / (tp + fn) if tp + fn else float("nan")
    return {"flagged": tp + fp, "true_pos": tp, "precision": round(p, 3), "recall": round(r, 3),
            "f1": round(2 * p * r / (p + r), 3) if p + r else float("nan")}


def main() -> None:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(SQL)
        df = pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])
    for c in ("on_field_target_share_exact", "on_field_target_share_est", "on_field_carry_share_exact",
              "on_field_carry_share_est", "offense_snap_pct", "usual_snap_pct"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    covered = df["plays_on_field"].notna()
    hurt = df["injury_note"] | df["missed_next"].fillna(False) | df["report_next"].fillna(False)
    df["truth"] = covered & (df["last_qtr"] <= 3) & (df["team_plays_after"] >= 15) & hurt
    print(f"player-games 2016-2025 REG QB/RB/WR/TE played: {len(df)}; with participation: {int(covered.sum())}; "
          f"truly left early: {int(df['truth'].sum())}")
    print("\n(a) the estimate against the exact share — mean absolute difference (share points, 0-1)")
    rows = []
    for kind, ex, es in (("target", "on_field_target_share_exact", "on_field_target_share_est"),
                         ("carry", "on_field_carry_share_exact", "on_field_carry_share_est")):
        both = df[ex].notna() & df[es].notna()
        for label, m in (("all", both), ("left early (truth)", both & df["truth"])):
            d = (df.loc[m, es] - df.loc[m, ex]).abs()
            rows.append({"share": kind, "rows": label, "n": int(m.sum()), "mad": round(d.mean(), 4),
                         "median": round(d.median(), 4), "p90": round(d.quantile(0.9), 4),
                         "whole_game_mad": round((df.loc[m, ex] - (df.loc[m, "targets" if kind == "target" else "carries"]
                                                  / df.loc[m, "team_targets" if kind == "target" else "team_carries"])).abs().mean(), 4)})
    print(pd.DataFrame(rows).to_string(index=False))
    print("\n(b) the rule against the truth — player-games with participation and two previous games (the snap drop known)")
    ev = df[covered & df["snap_drop_known"]]
    t = ev["truth"]
    out = []
    for name, pred in (("LE-A snap drop + injury note", ev["left_early_a"]),
                       ("LE-B snap drop + (note or no touch after half-time)", ev["left_early_b"]),
                       ("LE-0 snap drop alone (reference)", ev["snap_drop"])):
        out.append({"candidate": name, "n": len(ev), "truth": int(t.sum()), **prf(pred.astype(bool), t.astype(bool))})
    res = pd.DataFrame(out)
    print(res.to_string(index=False))
    a, b = res.iloc[0]["f1"], res.iloc[1]["f1"]
    print(f"\npick (higher F1; a tie ships LE-A): {'LE-A' if a >= b else 'LE-B'}")
    print("\nper season (LE-A):")
    print(ev.groupby("season").apply(lambda g: pd.Series(prf(g["left_early_a"].astype(bool), g["truth"].astype(bool))),
                                     include_groups=False).to_string())


if __name__ == "__main__":
    main()
