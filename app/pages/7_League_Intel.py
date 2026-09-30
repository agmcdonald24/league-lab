"""League Intel: how every manager plays — luck, lineup discipline, activity, and (plan B2) every roster's
lineup value, 4-week outlook and depth ranked in the league."""

import pandas as pd
import streamlit as st
from lib.charts import bar_chart, color_map, heat_style, line_chart
from lib.db import missing_relations, query
from lib.table import Col, howto, prepare, show
from lib.ui import freshness_banner, league_slots, perspective, setup

setup("League Intel")
freshness_banner()
league_id, roster_id, members = perspective(require_team=False)

st.subheader("Manager profiles")
howto(
    "**Luck** is wins above (+) or below (−) what a team's points deserve. **All-play %** is its record if it had played every "
    "team every week; **Expected W** turns that into wins. A lucky team is weaker than its record: a good trade partner to sell to.",
    "**Bench pts left/wk** is what a better lineup would have added each week. A manager who leaves a lot on the bench is not "
    "watching start/sit closely, which is worth knowing before you trade with him.",
    "**Waiver adds**, **FA adds**, **Trades** and **FAAB spent** show who is active and who sits still; **Failed claims** shows "
    "who is chasing the same players as you.",
    "The position columns (and **IR**) count how many of each the team holds now: a team thin at a position is a buyer there.",
)
prof = query(
    """select team_name, manager_name, standing, wins, losses, points_for, points_against,
              all_play_win_pct, expected_wins, luck_wins, all_play_rank,
              avg_bench_points_left, weeks_left_10_plus,
              waiver_adds, free_agent_adds, trades, failed_waiver_claims, faab_spent,
              n_qb, n_rb, n_wr, n_te, n_k, n_def, n_ir
       from analytics.mart_league_manager_profile where league_id = %s order by standing nulls last""",
    (league_id,),
)
slots = league_slots(league_id)
prof_cols = [c for c in prof.columns if c not in {f"n_{p.lower()}" for p in ("QB", "RB", "WR", "TE", "K", "DEF") if p not in slots}]
show(prof, prof_cols, height=420)

c1, c2 = st.columns(2)
c1.plotly_chart(bar_chart(prof.sort_values("luck_wins"), "team_name", "luck_wins", "Schedule luck (wins above what the points deserve)", "wins", horizontal=True, y_format="+.2f"), width="stretch")
c2.plotly_chart(bar_chart(prof.sort_values("avg_bench_points_left", ascending=False), "team_name", "avg_bench_points_left", "Points left on the bench per week", "points", horizontal=True, y_format=".1f"), width="stretch")

# ------------------------------------------------------------- all-play by week
st.subheader("Weekly scoring rank")
howto("Each cell is where the team's score ranked that week: 1 = the week's top scorer, darker = better.",
      "A team that keeps landing in the top half but keeps losing has been unlucky and should climb. One that wins while "
      "scoring in the bottom half has had a soft schedule and should fall back.",
      "Use it before a trade: a strong team with a bad record may be happy to deal, a weak one on a hot streak may overrate its roster.")
apw = query(
    """select week, team_name, points, week_points_rank, all_play_wins, result
       from analytics.mart_league_all_play_week where league_id = %s order by week, team_name""",
    (league_id,),
)
if not apw.empty:
    pv = apw.pivot_table(index="team_name", columns="week", values="week_points_rank")
    pv.index.name = "Team"
    pv.columns = [f"Wk {int(c)}" for c in pv.columns]
    st.dataframe(heat_style(pv), width="stretch")
    teams = sorted(apw["team_name"].unique().tolist())
    sel = st.multiselect("Teams on the chart", teams, default=teams[:5], max_selections=8)
    st.plotly_chart(line_chart(apw[apw["team_name"].isin(sel)], "week", "points", "team_name", "Points by week", "points", y_format=".1f", colors=color_map(teams)), width="stretch")

# ------------------------------------------------------------- roster rankings (plan B2)
st.subheader("Roster rankings")
if missing_relations(("mart_league_roster_rankings", "mart_league_roster_value")):
    st.info("Roster rankings appear after the next build publishes the roster-value marts.")
else:
    rk = query(
        """select roster_id, team_name, measure, horizon, value, league_rank, n_rosters
           from analytics.mart_league_roster_rankings where league_id = %s""",
        (league_id,),
    )
    rv = query(
        """select roster_id, weakest_slot, weakest_margin from analytics.mart_league_roster_value where league_id = %s""",
        (league_id,),
    )
    if rk.empty:
        st.caption("No lineups for the weeks ahead yet.")
    else:
        def _ord(n) -> str:
            n = int(n)
            return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"

        hz = rk.drop_duplicates("measure").set_index("measure")["horizon"]
        top = rk[rk["league_rank"] == 1].drop_duplicates("measure").set_index("measure")
        n = int(rk["n_rosters"].max())
        lines = [f"Strongest lineup ({hz['lineup_value']}): **{top.loc['lineup_value', 'team_name']}** ({top.loc['lineup_value', 'value']:.1f})",
                 f"best over {hz['horizon_value']}: **{top.loc['horizon_value', 'team_name']}** ({top.loc['horizon_value', 'value']:.1f})",
                 f"deepest bench ({hz['bench_value']}): **{top.loc['bench_value', 'team_name']}** ({top.loc['bench_value', 'value']:.1f})"]
        st.markdown(" · ".join(lines) + ".")
        if roster_id is not None:
            mine = rk[rk["roster_id"] == roster_id].set_index("measure")
            if not mine.empty:
                st.markdown(f"Yours: {_ord(mine.loc['lineup_value', 'league_rank'])} in {hz['lineup_value']}, "
                            f"{_ord(mine.loc['horizon_value', 'league_rank'])} over {hz['horizon_value']}, "
                            f"{_ord(mine.loc['bench_value', 'league_rank'])} in depth (of {n}).")
        wide = rk.pivot_table(index=["roster_id", "team_name"], columns="measure", values=["value", "league_rank"]).reset_index()
        wide.columns = ["_".join(str(x) for x in c if x) for c in wide.columns]
        wide = wide.merge(rv, on="roster_id", how="left").sort_values("league_rank_lineup_value")
        for m in ("lineup_value", "horizon_value", "bench_value"):
            wide[m] = [f"{v:.1f} · {_ord(r)}" for v, r in zip(wide[f"value_{m}"], wide[f"league_rank_{m}"], strict=True)]
        wide["closest"] = [f"{s} · {mg:.2f}" if isinstance(s, str) and pd.notna(mg) else "—"
                           for s, mg in zip(wide["weakest_slot"], wide["weakest_margin"], strict=True)]
        wk_h, hz_h = hz["lineup_value"].capitalize(), hz["horizon_value"].capitalize()
        cols = ["team_name", "lineup_value", "horizon_value", "bench_value", "closest"]
        out, config = prepare(wide, cols, overrides={"team_name": Col("Team"),
                        "lineup_value": Col(wk_h, help=f"Best legal lineup, {hz['lineup_value']} (every slot solved together): value · league rank"),
                        "horizon_value": Col(hz_h, help=f"The best lineups of {hz['horizon_value']} added up: value · league rank"),
                        "bench_value": Col(f"Depth · {hz['bench_value']}", help="The lineup the bench alone would field if every starter sat: value · league rank"),
                        "closest": Col("Closest call", help="The starter with the smallest margin and what the lineup loses by benching him for the next man up")})
        # phone first: the team pinned, narrow value columns (the table is five columns wide)
        config["team_name"].update(width=130, pinned=True)
        for c in cols[1:]:
            config[c]["width"] = 92
        st.dataframe(out, column_config=config, hide_index=True, width="stretch", placeholder="")
        howto("**Lineup value** is the projected points of each team's best lineup, FLEX and superflex included, in this "
              "league's scoring. The rank after each number is its place in the league for the weeks named in the column.",
              "**Depth** is what a team's bench alone could put out. **Closest call** is the spot where its start/sit decision is tightest.",
              "A team ranked high on the next four weeks but low on depth is one injury from trouble: a natural trade partner "
              "if you are deep and need a starter.")

# ------------------------------------------------------------- historical luck
st.subheader("Past seasons — record vs what the points deserved")
hist = query(
    """select l.season, a.team_name, a.manager_name, a.wins, a.losses, a.all_play_win_pct, a.expected_wins, a.luck_wins, s.is_champion
       from analytics.mart_league_all_play a
       join analytics.dim_league_season l using (league_id)
       left join analytics.mart_league_standings s using (league_id, roster_id)
       where not l.is_current_season
         and l.chain_id = (select chain_id from analytics.dim_league_season where league_id = %s)
       order by l.season desc, a.luck_wins desc""",
    (league_id,),
)
show(hist)
