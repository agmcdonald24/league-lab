"""League: the whole league on one page (plan U-16 folds League Intel in). Answer first: one line on your
schedule luck and your bench, then three charts with every team — schedule luck, points left on the bench,
weekly scoring rank — then every roster's lineup value ranked (B2), then standings, manager profiles, weekly
scores, matchups and lineups, transactions, the draft and past seasons, each in an expander."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from lib.charts import CATEGORICAL, GRID, SURFACE, TEXT, TEXT_SECONDARY
from lib.db import missing_relations, query
from lib.table import Col, howto, prepare, show
from lib.ui import freshness_banner, league_slots, perspective, season_picker, setup

setup("League")
freshness_banner()

current_league_id, roster_id, members = perspective(require_team=False)   # which league (sidebar); the season below walks its chain
league = season_picker(current_league_id)
league_id = league["league_id"]
season = int(league["season"])
is_current = league_id == current_league_id
me = roster_id if is_current else None     # roster ids are slots: a past season's slot may have had another manager
PLOT_CONFIG = {"displayModeBar": False, "scrollZoom": False}


def ordinal(n) -> str:
    n = int(n)
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def nth(k: int, word: str) -> str:
    """'the unluckiest', 'the 3rd-unluckiest'."""
    return f"the {word}" if k == 1 else f"the {ordinal(k)}-{word}"


def short(name, n: int = 18) -> str:
    name = str(name)
    return name if len(name) <= n else name[: n - 1] + "…"


def team_label(team: str, rid) -> str:
    """Axis label: short team name; yours in bold with a marker, so it does not rest on color alone."""
    return f"<b>{short(team)} ◀</b>" if me is not None and rid == me else short(team)


def ranked_bars(df: pd.DataFrame, value: str, title: str, x_title: str, fmt: str, hover_extra: str = "") -> go.Figure:
    """Every team as one horizontal bar, largest first; your team solid, the others lighter (and labelled in bold)."""
    d = df.sort_values(value, ascending=False).reset_index(drop=True)
    labels = [team_label(t, r) for t, r in zip(d["team_name"], d["roster_id"], strict=True)]
    mine = [me is not None and r == me for r in d["roster_id"]]
    colors = [CATEGORICAL[0] if m else "rgba(42,120,214,0.45)" for m in mine]
    fig = go.Figure(go.Bar(
        x=pd.to_numeric(d[value], errors="coerce"), y=labels, orientation="h",
        marker=dict(color=colors, line=dict(width=2, color=SURFACE)),
        customdata=d[["team_name"]].to_numpy(),
        hovertemplate=f"%{{customdata[0]}}: %{{x:{fmt}}}{hover_extra}<extra></extra>",
    ))
    fig.update_layout(
        title=dict(text=title, font=dict(size=15, color=TEXT)), paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        font=dict(color=TEXT_SECONDARY, size=12), margin=dict(l=8, r=12, t=44, b=36), showlegend=False,
        height=90 + 26 * len(d), dragmode=False, hovermode="closest",
        xaxis=dict(title=x_title, gridcolor=GRID, zeroline=True, zerolinecolor=GRID, fixedrange=True),
        yaxis=dict(title="", showgrid=False, autorange="reversed", automargin=True, fixedrange=True),
    )
    return fig


def rank_heatmap(apw: pd.DataFrame) -> go.Figure:
    """Weekly scoring rank, every team (rows, best average first) × week: 1 = the week's top score, darker = better."""
    order = apw.groupby(["roster_id", "team_name"])["week_points_rank"].mean().sort_values().reset_index()
    weeks = sorted(apw["week"].astype(int).unique().tolist())
    z, text, hover = [], [], []
    for r in order.itertuples():
        row = apw[apw["roster_id"] == r.roster_id].set_index("week")
        zr, tr, hr = [], [], []
        for w in weeks:
            if w in row.index:
                x = row.loc[w]
                zr.append(float(x["week_points_rank"]))
                tr.append(str(int(x["week_points_rank"])))
                res = f", {x['result']}" if isinstance(x["result"], str) and x["result"] else ""
                hr.append(f"{r.team_name} · week {w}: {float(x['points']):.1f} pts, rank {int(x['week_points_rank'])}{res}")
            else:
                zr.append(None)
                tr.append("")
                hr.append(f"{r.team_name} · week {w}: no score")
        z.append(zr)
        text.append(tr)
        hover.append(hr)
    n = int(apw["week_points_rank"].max()) if not apw.empty else 1
    fig = go.Figure(go.Heatmap(
        z=z, x=[f"Wk {w}" for w in weeks], y=[team_label(t, rid) for t, rid in zip(order["team_name"], order["roster_id"], strict=True)],
        text=text, texttemplate="%{text}", textfont=dict(size=12), customdata=hover,
        hovertemplate="%{customdata}<extra></extra>", zmin=1, zmax=max(n, 2),
        colorscale=[[0.0, "#2a78d6"], [1.0, "#eef4fb"]], showscale=False, xgap=2, ygap=2,
    ))
    fig.update_layout(
        title=dict(text="Weekly scoring rank", font=dict(size=15, color=TEXT)),
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE, font=dict(color=TEXT_SECONDARY, size=12),
        margin=dict(l=8, r=12, t=44, b=36), height=100 + 26 * len(order), dragmode=False,
        xaxis=dict(side="bottom", showgrid=False, fixedrange=True, title="1 = the week's top score"),
        yaxis=dict(autorange="reversed", showgrid=False, automargin=True, fixedrange=True, title=""),
    )
    return fig


# ------------------------------------------------------------- the answer, then the three charts (every team)
prof = query(
    """select roster_id, team_name, manager_name, standing, wins, losses, points_for, points_against,
              all_play_win_pct, expected_wins, luck_wins, all_play_rank,
              avg_bench_points_left, total_bench_points_left, weeks_left_10_plus,
              waiver_adds, free_agent_adds, trades, failed_waiver_claims, faab_spent,
              n_qb, n_rb, n_wr, n_te, n_k, n_def, n_ir
       from analytics.mart_league_manager_profile where league_id = %s order by standing nulls last""",
    (league_id,),
)
apw = query(
    """select week, roster_id, team_name, points, week_points_rank, all_play_wins, result
       from analytics.mart_league_all_play_week where league_id = %s order by week, team_name""",
    (league_id,),
)
scored = prof[prof["luck_wins"].notna()].copy()
if scored.empty or apw.empty:
    st.info(f"No scored weeks yet in {season}: the luck, bench and weekly-rank charts fill in after week 1.")
else:
    scored["luck_wins"] = pd.to_numeric(scored["luck_wins"], errors="coerce")
    scored["total_bench_points_left"] = pd.to_numeric(scored["total_bench_points_left"], errors="coerce")
    n_teams, n_weeks = len(scored), int(apw["week"].nunique())
    weeks_txt = f"{n_weeks} week{'s' if n_weeks != 1 else ''}"
    mine = scored[scored["roster_id"] == me] if me is not None else scored.iloc[0:0]
    with st.container(border=True):
        if not mine.empty:
            m = mine.iloc[0]
            luck, bench = float(m["luck_wins"]), float(m["total_bench_points_left"] or 0)
            if abs(luck) < 0.05:
                luck_txt = "Your record is exactly what your points deserve"
            elif luck < 0:
                k = int((scored["luck_wins"] < luck).sum()) + 1
                luck_txt = f"You've been {nth(k, 'unluckiest')} team by schedule ({luck:+.1f} wins)"
            else:
                k = int((scored["luck_wins"] > luck).sum()) + 1
                luck_txt = f"You've been {nth(k, 'luckiest')} team by schedule ({luck:+.1f} wins)"
            kb = int((scored["total_bench_points_left"] > bench).sum()) + 1
            bench_rank = ("the most in the league" if kb == 1 else "the fewest in the league" if kb == n_teams
                          else f"the {ordinal(kb)} most of {n_teams}")
            st.markdown(f"**{luck_txt}; your bench has left {bench:.0f} points unstarted** ({bench_rank}, {weeks_txt}).")
        else:
            lk = scored.sort_values("luck_wins", ascending=False)
            bn = scored.sort_values("total_bench_points_left", ascending=False).iloc[0]
            st.markdown(f"**Luckiest by schedule: {lk.iloc[0]['team_name']} ({lk.iloc[0]['luck_wins']:+.1f} wins); unluckiest: "
                        f"{lk.iloc[-1]['team_name']} ({lk.iloc[-1]['luck_wins']:+.1f}). Most points left on the bench: "
                        f"{bn['team_name']} ({bn['total_bench_points_left']:.0f})** — {season}, {weeks_txt}.")
        st.caption("Luck = wins minus the wins your points deserve (your record if you had played every team every week).")
    st.plotly_chart(ranked_bars(scored, "luck_wins", "Schedule luck", "wins above what the points deserve", "+.2f"),
                    width="stretch", config=PLOT_CONFIG)
    st.plotly_chart(ranked_bars(scored, "total_bench_points_left", "Points left on the bench", f"points, {weeks_txt}", ".1f",
                                hover_extra=" left on the bench"),
                    width="stretch", config=PLOT_CONFIG)
    st.plotly_chart(rank_heatmap(apw), width="stretch", config=PLOT_CONFIG)
    howto("**Schedule luck**: each roster's win rate if it had played every other roster every week is the record its points deserve; "
          "luck is actual wins minus those expected wins. A 2-0 team with a big negative luck number is scoring like a 1-1 team and has been "
          "getting favourable draws.",
          "**Points left on the bench (hindsight)** is how much the best lineup knowing the final scores would have added: hindsight, "  # II-4
          "not an avoidable mistake. High numbers over many weeks mark managers who don't sweat start/sit — useful when trading with them.",
          "**Weekly scoring rank**: each cell is where the roster's score ranked that week (1 = top scorer, darker = better). A roster that keeps "
          "landing in the top half but keeps losing is unlucky; the opposite is riding a soft schedule.",
          title="How to read this")

# ------------------------------------------------------------- roster rankings (plan B2), this season only
if is_current:
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
            hz = rk.drop_duplicates("measure").set_index("measure")["horizon"]
            top = rk[rk["league_rank"] == 1].drop_duplicates("measure").set_index("measure")
            n = int(rk["n_rosters"].max())
            lines = [f"Strongest lineup ({hz['lineup_value']}): **{top.loc['lineup_value', 'team_name']}** ({top.loc['lineup_value', 'value']:.1f})",
                     f"best over {hz['horizon_value']}: **{top.loc['horizon_value', 'team_name']}** ({top.loc['horizon_value', 'value']:.1f})",
                     f"deepest bench ({hz['bench_value']}): **{top.loc['bench_value', 'team_name']}** ({top.loc['bench_value', 'value']:.1f})"]
            st.markdown(" · ".join(lines) + ".")
            if me is not None:
                mine_rk = rk[rk["roster_id"] == me].set_index("measure")
                if not mine_rk.empty:
                    st.markdown(f"Yours: {ordinal(mine_rk.loc['lineup_value', 'league_rank'])} in {hz['lineup_value']}, "
                                f"{ordinal(mine_rk.loc['horizon_value', 'league_rank'])} over {hz['horizon_value']}, "
                                f"{ordinal(mine_rk.loc['bench_value', 'league_rank'])} in depth (of {n}).")
            wide = rk.pivot_table(index=["roster_id", "team_name"], columns="measure", values=["value", "league_rank"]).reset_index()
            wide.columns = ["_".join(str(x) for x in c if x) for c in wide.columns]
            wide = wide.merge(rv, on="roster_id", how="left").sort_values("league_rank_lineup_value")
            for m in ("lineup_value", "horizon_value", "bench_value"):
                wide[m] = [f"{v:.1f} · {ordinal(r)}" for v, r in zip(wide[f"value_{m}"], wide[f"league_rank_{m}"], strict=True)]
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

# ------------------------------------------------------------- the rest, tight: one expander each
st.subheader(f"{season} in detail")

with st.expander("Standings"):
    howto("The regular-season table from the weeks Sleeper has scored.",
          "**Lineup eff.** is the points a team started as a share of its best possible lineup each week (Sleeper's \"max points\"). "
          "Low means the manager keeps leaving points on the bench.",
          "**Std dev** is how much a team's score swings week to week. A big swing makes a team dangerous in a one-week playoff game "
          "and shaky before it.")
    standings = query(
        """select standing, team_name, manager_name, wins, losses, ties, points_for, points_against,
                  avg_points, stddev_points, best_week, worst_week, lineup_efficiency, is_champion
           from analytics.mart_league_standings where league_id = %s order by standing""",
        (league_id,),
    )
    show(standings, phone_cols=["standing", "team_name", "wins", "losses", "points_for"], pin=True)

with st.expander("Manager profiles: luck, bench, moves, roster shape"):
    howto(
        "**Luck** is wins above (+) or below (−) what a team's points deserve. **All-play %** is its record if it had played every "
        "team every week; **Expected W** turns that into wins. A lucky team is weaker than its record: a good trade partner to sell to.",
        "**Bench pts left/wk** is what a better lineup would have added each week. A manager who leaves a lot on the bench is not "
        "watching start/sit closely, which is worth knowing before you trade with him.",
        "**Waiver adds**, **FA adds**, **Trades** and **FAAB spent** show who is active and who sits still; **Failed claims** shows "
        "who is chasing the same players as you.",
        "The position columns (**QB / RB / WR / TE**, plus **K / DEF** where the league starts them) and **IR** count how many of each the roster currently holds.",
    )
    slots = league_slots(current_league_id)
    prof_cols = [c for c in prof.columns if c not in {"roster_id", "total_bench_points_left"}
                 and c not in {f"n_{p.lower()}" for p in ("QB", "RB", "WR", "TE", "K", "DEF") if p not in slots}]
    show(prof, prof_cols, height=420, phone_cols=["team_name", "wins", "luck_wins", "avg_bench_points_left", "trades"], pin=True)

with st.expander("Weekly scores and high scores"):
    weekly = query(
        """select m.week, d.team_name, m.points, m.opponent_points, m.result, m.week_type
           from analytics.fct_league_matchup m
           join analytics.dim_league_member d using (league_id, roster_id)
           where m.league_id = %s and m.is_scored order by m.week, d.team_name""",
        (league_id,),
    )
    if weekly.empty:
        st.caption("No scored weeks yet for this season.")
    else:
        hi = weekly.sort_values("points", ascending=False).head(5)
        st.markdown("High scores: " + " · ".join(f"**{r.team_name}** {float(r.points):.1f} (wk {int(r.week)})" for r in hi.itertuples()) + ".")
        pivot = weekly.pivot_table(index="team_name", columns="week", values="points").round(1)
        pivot.columns = [f"Wk {int(c)}" for c in pivot.columns]
        pivot = pivot.reset_index()
        week_cols = [c for c in pivot.columns if c != "team_name"]
        show(pivot, ["team_name", *week_cols], phone_cols=["team_name", *week_cols[-4:]], pin=True,
             overrides={c: Col(c, "num1") for c in week_cols})

with st.expander("Matchups and lineups, by week"):
    last = int(max(league["last_scored_leg"] or 1, 1))
    wk = st.slider("Week", 1, last, int(league["last_scored_leg"] or 1)) if last > 1 else 1
    mu = query(
        """select m.matchup_id, d.team_name, m.points, m.result, m.week_type
           from analytics.fct_league_matchup m
           join analytics.dim_league_member d using (league_id, roster_id)
           where m.league_id = %s and m.week = %s order by m.matchup_id, m.points desc""",
        (league_id, wk),
    )
    show(mu)
    lineup_team = st.selectbox("Show a lineup", sorted(mu["team_name"].unique().tolist()) if not mu.empty else [])
    if lineup_team:
        howto("**Points** are what Sleeper scored. **Recomputed** is the same week worked out by League Lab from the NFL's stats "
              "with your league's scoring.",
              "The two match to the decimal, which is how you know every other page counts points the way Sleeper does.",
              "Blank for team defenses and for a player with no NFL stats that week (not on an NFL roster, or an empty slot).")
        lineup = query(
            """select l.gsis_id, l.slot, l.player_name, l.position, l.nfl_team, l.points_observed, l.points_recomputed, l.is_starter
               from analytics.league_player_week l
               join analytics.dim_league_member d using (league_id, roster_id)
               where l.league_id = %s and l.week = %s and d.team_name = %s
               order by l.is_starter desc, l.slot_index nulls last, l.points_observed desc""",
            (league_id, wk, lineup_team),
        )
        show(lineup, ["slot", "player_name", "position", "nfl_team", "points_observed", "points_recomputed", "is_starter"],
             phone_cols=["slot", "player_name", "position", "points_observed", "is_starter"])

with st.expander("Transactions"):
    tx = query(
        """select t.created_at, t.week, t.transaction_type, t.status, t.action, t.team_name, t.player_name, t.position, t.waiver_bid,
                  m.gsis_id
           from analytics.mart_league_transactions t
           left join analytics.player_id_map m on m.sleeper_id = t.sleeper_player_id
           where t.league_id = %s order by t.created_at desc, t.transaction_id, t.action""",
        (league_id,),
    )
    c1, c2 = st.columns(2)
    types = c1.multiselect("Type", sorted(tx["transaction_type"].dropna().unique().tolist()), default=None)
    only_complete = c2.checkbox("Completed only", value=True)
    view = tx if not types else tx[tx["transaction_type"].isin(types)]
    if only_complete:
        view = view[view["status"] == "complete"]
    show(view, ["created_at", "week", "transaction_type", "action", "team_name", "player_name", "position", "waiver_bid"], height=480,
         phone_cols=["player_name", "action", "team_name", "week", "waiver_bid"])

with st.expander("Draft review"):
    howto("Every pick, and what the player went on to do. Use it to see who drafts well, and which rounds paid off.",
          "**Pos rank by pick** vs **Pos rank by pts** is the hit-or-miss check: a WR taken 8th among WRs who finished 2nd was a steal.",
          "**Season pts** uses this league's current scoring, so drafts from different years compare. **Pts while started** is what "
          "he scored for whoever started him in this league.")
    draft = query(
        """select gsis_id, pick_no, round, team_name, player_name, position, drafted_team, is_keeper,
                  nfl_reg_games_played, nfl_reg_points_current_scoring, position_rank_by_pick, position_rank_by_points,
                  points_started_for_any_roster
           from analytics.mart_league_draft where league_id = %s order by pick_no""",
        (league_id,),
    )
    show(draft, [c for c in draft.columns if c != "gsis_id"], height=520,
         phone_cols=["pick_no", "player_name", "team_name", "position_rank_by_pick", "position_rank_by_points"])

with st.expander("Past seasons: record vs what the points deserved"):
    hist = query(
        """select l.season, a.team_name, a.manager_name, a.wins, a.losses, a.all_play_win_pct, a.expected_wins, a.luck_wins, s.is_champion
           from analytics.mart_league_all_play a
           join analytics.dim_league_season l using (league_id)
           left join analytics.mart_league_standings s using (league_id, roster_id)
           where not l.is_current_season
             and l.chain_id = (select chain_id from analytics.dim_league_season where league_id = %s)
           order by l.season desc, a.luck_wins desc""",
        (current_league_id,),
    )
    show(hist, phone_cols=["season", "team_name", "wins", "losses", "luck_wins"])
