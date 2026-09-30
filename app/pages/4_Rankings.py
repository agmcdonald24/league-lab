"""Rankings: weekly projections per position — the transparent baseline formula and projection v2 (a projected
stat line priced in this league's scoring, with a floor and a ceiling) — and the backtests that say how far to trust each."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from lib.charts import SURFACE, bar_chart, base_layout
from lib.db import missing_relations, query, require_relations
from lib.table import Col, howto, show
from lib.ui import freshness_banner, next_week_info, perspective, setup

setup("Rankings")
freshness_banner()
require_relations("mart_player_week_rankings", "mart_backtest_summary", "mart_player_week_projections", "mart_projection_backtest")
league_id, roster_id, members = perspective(require_team=False)
cal = next_week_info()
cur_season = int(cal["season"]) if not cal.empty else None
cur_week = int(cal["next_week"]) if not cal.empty and pd.notna(cal["next_week"]) else 1

v2_available = not query("select 1 from analytics.mart_player_week_projections where league_id = %s limit 1", (league_id,)).empty
league_name = query("select league_name from analytics.dim_league_season where league_id = %s", (league_id,))["league_name"].iloc[0]

howto(
    "**Pick a position and a week.** The list is who should score the most, in your league's scoring. Tap a name for his page.",
    "**Floor and ceiling** are his bad week and his good week: 8 weeks in 10 land between them. A wide gap means boom or bust.",
    "**Two projections.** The default is League Lab's own model: it predicts targets, catches, yards and touchdowns, then counts "
    "them your league's way. The other is the old, simpler formula (one scale for every league), kept as a check.",
    "**How much to trust it**: the sections below grade the projections on weeks they had not seen. They get the order right more "
    "often than not, and still miss plenty. \"The model\" at the bottom says what it is and what it leans on.",
    "**Out and Doubtful** players are left off. **Questionable** players stay on with a flag: check the news before kickoff.",
    title="How to use this page",
)

# ---------------------------------------------------------------- controls
model_options = {"v2": f"Projection v2 · {league_name} scoring", "baseline": "Baseline formula · reference scoring"}
if not v2_available:
    model_options.pop("v2")
seasons = query("select distinct season from analytics.mart_player_week_rankings order by season desc")["season"].astype(int).tolist()
c0, c1, c2, c3, c4, c5 = st.columns([1.6, 0.8, 0.8, 0.9, 1.4, 0.9])
model = c0.selectbox("Projection", list(model_options), format_func=lambda k: model_options[k])
if model == "v2":
    seasons = query("select distinct season from analytics.mart_player_week_projections where league_id = %s order by season desc",
                    (league_id,))["season"].astype(int).tolist()
season = c1.selectbox("Season", seasons, index=seasons.index(cur_season) if cur_season in seasons else 0)
if model == "v2":
    weeks = query("select distinct week from analytics.mart_player_week_projections where league_id = %s and season = %s order by week",
                  (league_id, season))["week"].astype(int).tolist()
else:
    weeks = query("select distinct week from analytics.mart_player_week_rankings where season = %s order by week", (season,))["week"].astype(int).tolist()
if season == cur_season:
    # only played weeks and the next one: later weeks have no lines or injury reports yet, so a board would be form only
    weeks = [w for w in weeks if w <= cur_week] or weeks
default_week = cur_week if season == cur_season and cur_week in weeks else weeks[-1]
week = c2.selectbox("Week", weeks, index=weeks.index(default_week))
position = c3.selectbox("Position", ["QB", "RB", "WR", "TE"], index=2)
scope_options = {"all": "Everyone", "fa": "Free agents in this league", "rostered": "Rostered in this league", "team": "Selected team only"}
scope = c4.selectbox("Who", list(scope_options), format_func=lambda k: scope_options[k], index=0)
top_n = c5.number_input("Show", 10, 80, 36)
# B5 decision record: a week's v2 board is frozen at its first kickoff. to_jsonb keeps the page working on a
# copy whose mart predates the label (it reads as unlabelled there).
freeze = query("""select to_jsonb(p) ->> 'frozen_source' as frozen_source, to_jsonb(p) ->> 'frozen_at' as frozen_at
                  from analytics.mart_player_week_projections as p where league_id = %s and season = %s and week = %s limit 1""",
               (league_id, season, week)) if model == "v2" else pd.DataFrame()
frozen_source = freeze["frozen_source"].iloc[0] if not freeze.empty else None
if frozen_source == "kickoff":
    frozen_when = pd.to_datetime(freeze["frozen_at"].iloc[0], utc=True).tz_convert("America/New_York")
    st.caption(f"Week {week}'s games have started: the table shows the board as published before the first kickoff "
               f"({frozen_when:%a %b %-d, %-I:%M %p} ET), frozen since, next to what happened.")
elif frozen_source == "refit":
    st.caption(f"Week {week} was already under way when boards started being frozen at kickoff, so its projections are **refit values** "
               "from a later run of the same model (same as-of rule), not the exact board shown before the games.")
elif season == cur_season and week == cur_week:
    st.caption(f"NFL {season} week {week} is the next week to be played: this is the live board. "
               + ("Lines and injury reports update with each refresh until the week's first game kicks off; from then on the board is "
                  "frozen, and that frozen board is what the season scoreboard below is scored on." if model == "v2" else
                  "Lines and injury reports update through the week; refresh on Sunday morning."))
elif season < cur_season or week < cur_week:
    st.caption(f"Week {week} has been played: the table shows " + ("the projection next to what happened." if model == "v2" else
               "what the projection said *before* the games, next to what happened."))

avail = query(
    """select gsis_id, rostered_by_roster_id, rostered_by_team, is_free_agent from analytics.mart_player_availability where league_id = %s""",
    (league_id,),
)
if model == "v2":
    rk = query(
        """select gsis_id, rank_pos, player_name, team, opponent, is_home, implied_team_total, spread_line, report_status, practice_status,
                  games_to_date, no_history, is_rankable, proj_points, p10, p50, p90, interval_width,
                  proj_targets, proj_receptions, proj_receiving_yards, proj_receiving_tds, proj_carries, proj_rushing_yards, proj_rushing_tds,
                  proj_attempts, proj_passing_yards, proj_passing_tds, proj_passing_interceptions,
                  xppg_l5, ppg_std, ppg_l3, prev_ppg, opp_rank_std, target_share_l3, carry_share_l3, snap_pct_l3, first_read_share_l3,
                  points_actual, played, actual_rank_pos, actual_inside_interval, model_version, train_seasons
           from analytics.mart_player_week_projections
           where league_id = %s and season = %s and week = %s and position = %s
           order by rank_pos""",
        (league_id, season, week, position),
    )
else:
    rk = query(
        """select gsis_id, rank_pos, player_name, team, opponent, is_home, implied_team_total, spread_line, report_status, practice_status,
                  games_to_date, no_history, is_rankable, proj_points, c_form, c_usage, c_matchup, c_vegas, c_home,
                  xppg_l5, ppg_std, ppg_l3, prev_ppg, opp_allowed_std, league_allowed_avg, opp_rank_std, target_share_l3, target_share_std,
                  carry_share_l3, carry_share_std, snap_pct_l3, first_read_share_l3, points_actual, played, actual_rank_pos
           from analytics.mart_player_week_rankings
           where season = %s and week = %s and position = %s
           order by rank_pos""",
        (season, week, position),
    )
rk = rk.merge(avail, on="gsis_id", how="left")
if scope == "fa":
    rk = rk[rk["is_free_agent"].fillna(True)]
elif scope == "rostered":
    rk = rk[rk["rostered_by_roster_id"].notna()]
elif scope == "team" and roster_id is not None:
    rk = rk[rk["rostered_by_roster_id"] == roster_id]

ranked = rk[rk["is_rankable"]].head(int(top_n))
played_week = rk["points_actual"].notna().mean() > 0.5  # most of the week is in (not just Thursday night)

st.subheader(f"{position} · NFL {season} week {week}")
if model == "v2":
    howto(
        f"**Proj** is his projected points in **{league_name}** scoring: the stat line in the next columns, counted your league's way.",
        "**Floor** and **Ceiling** are a bad week and a good week: 1 week in 10 lands below the floor, 1 in 10 above the ceiling. "
        "The wider the gap (**Range**), the less sure the projection is.",
        "The stat columns are what the projection is made of. A touchdown number like 0.45 means roughly a 45% chance he scores one.",
        "**xPPG (L5)** is what his targets and carries were worth over his last 5 games (expected points per game), **PPG** what he "
        "actually scored. **Opp rank** 1 = the defense that gives up the most to his position: the matchup you want. These use one "
        "scale for every league.",
        "Once the week is played, **Actual**, **Actual rank** and **In range** (did he land between floor and ceiling?) show up.",
    )
    line_cols = {"QB": ["proj_attempts", "proj_passing_yards", "proj_passing_tds", "proj_passing_interceptions", "proj_carries", "proj_rushing_yards", "proj_rushing_tds"],
                 "RB": ["proj_carries", "proj_rushing_yards", "proj_rushing_tds", "proj_targets", "proj_receptions", "proj_receiving_yards", "proj_receiving_tds"],
                 "WR": ["proj_targets", "proj_receptions", "proj_receiving_yards", "proj_receiving_tds", "proj_carries", "proj_rushing_yards"],
                 "TE": ["proj_targets", "proj_receptions", "proj_receiving_yards", "proj_receiving_tds"]}[position]
    cols = ["rank_pos", "player_name", "team", "opponent", "rostered_by_team", "report_status", "proj_points", "p10", "p90", "interval_width",
            *line_cols, "xppg_l5", "ppg_std", "ppg_l3", "prev_ppg", "games_to_date", "opp_rank_std", "implied_team_total", "is_home",
            "target_share_l3" if position != "QB" else "carry_share_l3", "snap_pct_l3"]
    if position in ("WR", "TE", "RB"):
        cols.append("first_read_share_l3")
    if played_week:
        cols += ["points_actual", "actual_rank_pos", "actual_inside_interval"]
    show(ranked, cols, height=min(80 + 36 * len(ranked), 900),
         overrides={"proj_points": Col("Proj", "num1", "The projected stat line put through this league's scoring map")})
else:
    howto(
        "**Proj** is the old formula's projection, on one scale for every league. The five columns after it (form, usage, matchup, "
        "Vegas, home) are its parts and add up to it, plus a small constant.",
        "Use the parts to see *why*: a player can be #3 on form and #12 overall because Vegas expects his team to score little and "
        "the defense is tough.",
        "**xPPG (L5)** is what his targets and carries were worth over his last 5 games; **PPG** is what he scored; **Opp allows** is "
        "what the defense gives up to his position, next to the league average; **Implied total** is the points Vegas expects his team to score.",
        "Once the week is played, **Actual** and **Actual rank** show where the formula was right and wrong.",
    )
    cols = ["rank_pos", "player_name", "team", "opponent", "rostered_by_team", "report_status", "proj_points", "c_form", "c_usage", "c_matchup", "c_vegas", "c_home",
            "xppg_l5", "ppg_std", "ppg_l3", "prev_ppg", "games_to_date", "opp_allowed_std", "league_allowed_avg", "implied_team_total", "is_home",
            "target_share_l3" if position != "QB" else "carry_share_l3", "snap_pct_l3"]
    if position in ("WR", "TE", "RB"):
        cols.append("first_read_share_l3")
    if played_week:
        cols += ["points_actual", "actual_rank_pos"]
    show(ranked, cols, height=min(80 + 36 * len(ranked), 900))

excluded = rk[~rk["is_rankable"] & rk["report_status"].isin(["Out", "Doubtful"])]
if not excluded.empty:
    st.caption("Not ranked (Out / Doubtful): " + ", ".join(excluded["player_name"].head(20)) + (" …" if len(excluded) > 20 else ""))

# ---------------------------------------------------------------- why: range chart (v2) or contribution chart (baseline)
if not ranked.empty and model == "v2":
    top = ranked.head(min(20, len(ranked))).copy()
    for c in ("p10", "proj_points", "p90", "points_actual"):
        top[c] = pd.to_numeric(top[c], errors="coerce")
    fig = go.Figure()
    fig.add_trace(go.Bar(x=top["player_name"], y=top["p90"] - top["p10"], base=top["p10"], name="Floor to ceiling (P10–P90)",
                         marker=dict(color="#2a78d6", opacity=0.25), hovertemplate="P10 %{base:.1f} · P90 %{y:.1f}<extra></extra>"))
    fig.add_trace(go.Scatter(x=top["player_name"], y=top["proj_points"], mode="markers", name="Projection",
                             marker=dict(size=10, color="#2a78d6", line=dict(width=2, color=SURFACE)), hovertemplate="proj %{y:.1f}<extra></extra>"))
    if played_week:
        fig.add_trace(go.Scatter(x=top["player_name"], y=top["points_actual"], mode="markers", name="Actual",
                                 marker=dict(size=9, symbol="diamond", color="#eb6834", line=dict(width=1, color=SURFACE)),
                                 hovertemplate="actual %{y:.1f}<extra></extra>"))
    layout = base_layout("Floor, projection and ceiling — top of the board", f"points ({league_name})", x_title="")
    layout["xaxis"] = dict(title="", showgrid=False, zeroline=False, tickangle=-35)
    layout["hovermode"] = "x"
    fig.update_layout(**layout, barmode="overlay")
    st.plotly_chart(fig, width="stretch")
elif not ranked.empty:
    top = ranked.head(min(15, len(ranked)))
    parts = top.melt(id_vars=["player_name"], value_vars=["c_form", "c_usage", "c_matchup", "c_vegas", "c_home"], var_name="part", value_name="points")
    parts["part"] = parts["part"].map({"c_form": "Form", "c_usage": "Usage", "c_matchup": "Matchup", "c_vegas": "Vegas", "c_home": "Home"})
    parts["points"] = pd.to_numeric(parts["points"], errors="coerce")
    fig = bar_chart(parts, "player_name", "points", "What the projection is made of (top of the board)", "points", series="part", y_format=".1f", x_title="")
    fig.update_layout(barmode="relative")
    st.plotly_chart(fig, width="stretch")

# ---------------------------------------------------------------- your roster vs the board
if roster_id is not None and scope != "team":
    mine = rk[(rk["rostered_by_roster_id"] == roster_id)]
    if not mine.empty:
        st.subheader("Your players on this board")
        if model == "v2":
            show(mine, ["rank_pos", "player_name", "team", "opponent", "report_status", "proj_points", "p10", "p90", "xppg_l5", "ppg_std", "opp_rank_std", "implied_team_total"]
                 + (["points_actual", "actual_rank_pos", "actual_inside_interval"] if played_week else []))
        else:
            show(mine, ["rank_pos", "player_name", "team", "opponent", "report_status", "proj_points", "c_form", "c_matchup", "c_vegas", "xppg_l5", "ppg_std", "implied_team_total"]
                 + (["points_actual", "actual_rank_pos"] if played_week else []))

# ---------------------------------------------------------------- drift (M-06): this season's played weeks vs the backtest
if model == "v2":
    st.subheader("How the model is doing this season")
    if missing_relations(("mart_projection_drift",)):
        st.caption("The season scoreboard is not built on this database yet (`make build`, then `league-lab drift`).")
    else:
        dr = query(
            """select season, position, weeks_scored, first_week, last_week, week_in_progress, spearman, backtest_spearman,
                      coverage_80, backtest_coverage_80, backtest_seasons,
                      to_jsonb(d) ->> 'frozen_share' as frozen_share, to_jsonb(d) ->> 'refit_weeks' as refit_weeks
               from analytics.mart_projection_drift as d where league_id = %s""",
            (league_id,),
        )
        dr["frozen_share"] = pd.to_numeric(dr["frozen_share"], errors="coerce")
        dr_season = cur_season if cur_season in dr["season"].tolist() else (int(dr["season"].max()) if not dr.empty else cur_season)
        dr = dr[dr["season"] == dr_season].copy()
        dr["position"] = pd.Categorical(dr["position"], ["QB", "RB", "WR", "TE"], ordered=True)
        dr = dr.sort_values("position")
        in_progress = pd.to_numeric(dr["week_in_progress"], errors="coerce").max() if not dr.empty else float("nan")
        pending = f" Week {int(in_progress)} is still being played; it counts once its last game is in." if pd.notna(in_progress) else ""
        scored = dr[pd.to_numeric(dr["weeks_scored"], errors="coerce").fillna(0) > 0]
        if scored.empty:
            st.caption(f"No week of the {dr_season or 'current'} season is complete yet, so there is nothing to score the live board against.{pending}"
                       if pending else
                       f"No week of the {dr_season or 'current'} season has been played yet: this fills in once week 1 is complete.")
        else:
            first, last = int(scored["first_week"].min()), int(scored["last_week"].max())
            n_weeks = int(pd.to_numeric(scored["weeks_scored"]).max())
            span = f"week {first}" if first == last else f"weeks {first}–{last}"
            bt_span = f" ({scored['backtest_seasons'].dropna().iloc[0]})" if scored["backtest_seasons"].notna().any() else ""
            small = (f" {['One', 'Two', 'Three', 'Four', 'Five'][n_weeks - 1]} week{'s' if n_weeks > 1 else ''} is a small sample: "
                     "one odd Sunday moves these a lot." if n_weeks < 6 else "")
            # B5: which board was scored — the one published before each week's first kickoff, or refit values
            refit_weeks = max(scored["refit_weeks"].dropna().tolist(), key=len, default="")   # e.g. "1, 2, 3"
            refit_span = (("weeks " + " and ".join(refit_weeks.rsplit(", ", 1)) if "," in refit_weeks else "week " + refit_weeks)
                          if refit_weeks else "some weeks")
            if scored["frozen_share"].isna().all():
                board = ""   # a copy whose drift view predates B5
            elif scored["frozen_share"].min() >= 0.999:
                board = " Scored on the board as shown before kickoff: each week's projections are frozen when its first game starts."
            elif scored["frozen_share"].max() <= 0.001:
                board = (f" Scored on **refit values**: {refit_span} {'were' if ',' in refit_weeks else 'was'} played before boards were "
                         "frozen at kickoff, so the projections come from a later run of the same model, not the exact board shown before the games.")
            else:
                board = (f" {refit_span.capitalize()} (played before boards were frozen at kickoff) are scored on **refit values**, "
                         "the other weeks on the board as shown before kickoff.")
            st.caption(f"The board scored like the backtest on NFL {dr_season}'s complete {span} ({league_name} scoring, players who played), "
                       f"next to the walk-forward backtest{bt_span}.{small}{board}{pending}")
            show(scored, ["position", "weeks_scored", "spearman", "backtest_spearman", "coverage_80", "backtest_coverage_80"]
                 + (["frozen_share"] if scored["frozen_share"].notna().any() else []),
                 overrides={"spearman": Col("Spearman · this season", "num2", "Rank correlation between the projected order and actual points, "
                                                                          "averaged over this season's complete weeks; 1 = perfect, 0 = coin flip"),
                            "coverage_80": Col("Coverage · this season", "pct", "Share of this season's actuals that landed inside P10–P90 "
                                                                                "(target 80%)")})

# ---------------------------------------------------------------- backtest
st.subheader("Backtest — how much to trust this")
if model == "v2":
    howto(
        "**What this is**: each past season (2021–2025) predicted by a model trained only on the seasons before it, then graded on "
        f"what happened, in **{league_name}** scoring. It is the fairest test we have of how the projections will do this year.",
        "**Spearman** (the order score): how well the projected order matched the real order of scorers, 1 = perfect, 0 = no better "
        "than random. Around 0.5–0.6 is good for one week of fantasy football. **Top-N hit rate**: of the week's real top 12 (QB, TE) "
        "or top 24 (RB, WR), how many the projection had in its own top group.",
        "**MAE** is the average miss in points. **Coverage** is how often the real score landed between floor and ceiling (the aim "
        "is 8 weeks in 10); **Range** is the average gap between them.",
        "Three rows per position: the projection, its middle outcome (the floor–ceiling model's centre, for completeness) and the old "
        "formula on the same games. If the old formula wins somewhere, that is shown, not hidden.",
    )
    bt = query(
        """select season, position, scorer, scorer_label, train_seasons, weeks, top_n, spearman, hit_rate, mae, coverage_80, interval_width
           from analytics.mart_projection_backtest where league_id = %s order by season desc, position, spearman desc""",
        (league_id,),
    )
    if bt.empty:
        st.caption("No v2 backtest for this league yet (`make backtest-v2`).")
    else:
        b1, b2 = st.columns([1, 1])
        bt_season = b1.selectbox("Backtest season", sorted(bt["season"].unique().tolist(), reverse=True))
        bt_pos = b2.selectbox("Backtest position", ["QB", "RB", "WR", "TE"], index=["QB", "RB", "WR", "TE"].index(position))
        sel = bt[(bt["season"] == bt_season) & (bt["position"] == bt_pos)]
        show(sel, ["scorer_label", "train_seasons", "weeks", "top_n", "spearman", "hit_rate", "mae", "coverage_80", "interval_width"])
        allp = bt[bt["scorer"].isin(["v2_points", "baseline"])]
        piv = allp.pivot_table(index=["season", "position"], columns="scorer", values="spearman").reset_index()
        if {"v2_points", "baseline"} <= set(piv.columns):
            piv["edge"] = pd.to_numeric(piv["v2_points"]) - pd.to_numeric(piv["baseline"])
            piv["label"] = piv["season"].astype(str) + " " + piv["position"]
            st.plotly_chart(bar_chart(piv, "label", "edge", "v2 minus baseline (Spearman, per held-out season)", "Spearman gap",
                                      y_format="+.3f", x_title=""), width="stretch")
        cov = bt[bt["scorer"] == "v2_points"].copy()
        cov["coverage_80"] = pd.to_numeric(cov["coverage_80"], errors="coerce")
        cov["label"] = cov["season"].astype(str) + " " + cov["position"]
        st.plotly_chart(bar_chart(cov, "label", "coverage_80", "Share of actuals inside the floor–ceiling range (target 0.80)", "coverage",
                                  y_format=".2f", x_title=""), width="stretch")
else:
    howto(
        "**What this is**: the old formula was fitted on 2019–2022, then graded week by week on 2023 onward, seasons it never saw.",
        "**Spearman** (the order score): how well the projected order matched the real order of scorers, 1 = perfect, 0 = no better "
        "than random. **Top-N hit rate**: of the week's real top 12 (QB, TE) or top 24 (RB, WR), how many it had in its top group. "
        "**MAE**: the average miss in points.",
        "The simple rows (\"Season PPG to date\" and the like) are what you would get by sorting on one column. Compare the formula "
        "with them, not with 1.0: one week of fantasy football is mostly luck, so 0.6 is good.",
        "If a simple sort beats the formula somewhere, that is shown, not hidden.",
    )
    bt = query(
        """select season, position, scorer_label, weeks, top_n, spearman, hit_rate, mae, top_n_picked_ppg, top_n_ceiling_ppg
           from analytics.mart_backtest_summary order by season desc, position, spearman desc"""
    )
    if bt.empty:
        st.caption("No backtest has been run yet (`make backtest`).")
    else:
        b1, b2 = st.columns([1, 1])
        bt_season = b1.selectbox("Backtest season", sorted(bt["season"].unique().tolist(), reverse=True))
        bt_pos = b2.selectbox("Backtest position", ["QB", "RB", "WR", "TE"], index=["QB", "RB", "WR", "TE"].index(position))
        sel = bt[(bt["season"] == bt_season) & (bt["position"] == bt_pos)]
        show(sel, ["scorer_label", "weeks", "top_n", "spearman", "hit_rate", "mae", "top_n_picked_ppg", "top_n_ceiling_ppg"])
        allp = bt[bt["scorer_label"].isin(["League Lab baseline", "Season PPG to date"])]
        piv = allp.pivot_table(index=["season", "position"], columns="scorer_label", values="spearman").reset_index()
        if {"League Lab baseline", "Season PPG to date"} <= set(piv.columns):
            piv["edge"] = piv["League Lab baseline"] - piv["Season PPG to date"]
            piv["label"] = piv["season"].astype(str) + " " + piv["position"]
            st.plotly_chart(bar_chart(piv, "label", "edge", "Baseline minus 'sort by season PPG' (Spearman, per held-out season)", "Spearman gap",
                                      y_format="+.3f", x_title=""), width="stretch")

# ---------------------------------------------------------------- the formula / the model (plan U-15: plain words, honest importance)
if model == "v2":
    with st.expander("The model: where these projections come from"):
        meta = rk[["model_version", "train_seasons"]].dropna().head(1) if "model_version" in rk.columns else pd.DataFrame()
        span = str(meta["train_seasons"].iloc[0]).replace("-", " to ") if not meta.empty else "2016 to last season"
        st.markdown(
            "**Is this a model you trained?** Yes. League Lab trains its own model; these are not Sleeper's or ESPN's projections.\n\n"
            f"- **What it learned from**: the regular-season games QBs, RBs, WRs and TEs played from {span} (over 50,000 of them), "
            "each with only what was known before kickoff: his season and last-3-game numbers, his share of his team's targets, "
            "carries and snaps, how often he was the quarterback's first look, last season, the opponent's defense against his "
            "position, the Vegas line, home or away, and the injury report.\n"
            "- **What it predicts**: the stat line, not points. For each position there is one small model per stat: targets, "
            "catches, receiving yards and TDs, carries, rushing yards and TDs, and for quarterbacks pass attempts, passing yards, "
            "TDs and interceptions. Each is a *gradient-boosted* model: a few hundred small decision trees, each one fixing the "
            f"mistakes of the ones before it. Then **{league_name}**'s scoring turns the stat line into points, which is why the "
            "same player projects differently in each league.\n"
            "- **Floor and ceiling** come from separate models that learned how far off the projection usually is for a player "
            "like this one: 8 weeks in 10 land between them, and the grades above check that they do.\n"
            "- **How it was graded**: trained on the past, graded on seasons it never saw. Each season from 2021 to 2025 was "
            "predicted by a model trained only on the seasons before it (the Backtest section).\n"
            "- **Spearman** is the order score in both grade tables: how well the projected order of players matched the order they "
            "really finished in, 1 = perfect, 0 = no better than random. *This season* scores this year's finished weeks; "
            "*backtest* is the same score on 2021 to 2025.\n"
            "- **Kickoff board**: the projections as they stood when each week's first game kicked off. They are locked from then "
            "on, so this season's grades score what you actually saw, not a later re-run.\n"
            "- **What it does not know**: injury news after the morning refresh, the weather, how the game actually goes (a "
            "blowout sends starters to the bench early), and coaching decisions made during the week. Check the news before kickoff.\n"
            "- **Refreshed** every morning with the newest games; its recipe stays the same all season."
        )
        # What drives the projection: the component models' permutation importance (ops.projection_importance,
        # model = 'component', component = 'total'), in points of error of the priced line. The old table here
        # was the interval model's (its main input is the projection itself); those rows stay in the mart,
        # labelled model = 'quantile_p50', and are not shown.
        st.markdown("**What it leans on most**")
        if missing_relations(("mart_projection_importance",)):
            st.caption("Not measured on this database yet: it is written by the next projection refresh.")
        else:
            mv = meta["model_version"].iloc[0] if not meta.empty else None
            imp = query(
                """select i.position, i.feature_label, i.importance, i.importance_rank, i.baseline_mae, i.eval_season, i.fit_seasons,
                          (select d.league_name from analytics.dim_league_season as d
                           where d.league_id = i.league_id order by d.season desc limit 1) as scored_in
                   from analytics.mart_projection_importance as i
                   where i.model = 'component' and i.component = 'total' and i.importance_rank <= 10
                     and i.model_version = coalesce(%s, (select max(model_version) from analytics.mart_projection_importance
                                                         where model = 'component'))
                   order by i.position, i.importance_rank""",
                (mv,),
            )
            if imp.empty:
                st.caption("Not measured for this model yet: it is written by the next projection refresh.")
            else:
                imp["importance"] = pd.to_numeric(imp["importance"], errors="coerce")
                tops = imp[imp["importance_rank"] == 1].set_index("position")["feature_label"]
                order = [p for p in ["QB", "RB", "WR", "TE"] if p in tops.index]
                st.markdown(" · ".join(f"**{p}**: {tops[p][0].lower() + tops[p][1:]}" for p in order))
                r0 = imp.iloc[0]
                fit = str(r0["fit_seasons"]).replace("-", " to ") if isinstance(r0["fit_seasons"], str) else "the seasons before"
                st.caption(
                    f"How we measured it: a copy of the model trained on {fit} projected the {int(r0['eval_season'])} season, which "
                    "it had never seen. Then we scrambled one input at a time (shuffled it between players, so it tells the model "
                    "nothing) and counted how much bigger the average miss got, in points per player per game "
                    f"({r0['scored_in']} scoring). Bigger = the model leans on it more. Inputs that move together (targets and "
                    "catches, a season and its last 3 games) share the credit, so each looks a little smaller than it is. The "
                    "projection itself (the \"price line\" an older table here showed) is the answer, not an input."
                )
                tab_order = ([position] if position in order else []) + [p for p in order if p != position]   # the board's position first
                for tab, pos in zip(st.tabs(tab_order), tab_order, strict=True):
                    with tab:
                        t = imp[imp["position"] == pos]
                        names = [n[0].lower() + n[1:] for n in t["feature_label"]]
                        base = float(t["baseline_mae"].iloc[0])
                        st.markdown(
                            f"For {pos}s the model leans most on **{names[0]}**."
                            + (" Next: " + " · ".join(f"*{n}*" for n in names[1:3]) + "." if len(names) > 1 else "")
                            + f" It misses a {pos} by {base:.1f} points a game on average; scrambling the top input adds "
                            f"{float(t['importance'].iloc[0]):.2f} to that."
                        )
                        # a list, not a grid: it wraps at phone width and the number stays on screen
                        st.markdown("\n".join(f"{int(r.importance_rank)}. {r.feature_label} · **{float(r.importance):+.2f}**"
                                               for r in t.itertuples()))
                        st.caption("Points of error added per player per game when that input is scrambled.")
else:
    with st.expander("The old formula: its weights"):
        wts = query("select position, feature, weight, train_seasons, n_rows, r2_train, fitted_at from analytics_seeds.ranking_weights where position = %s order by feature", (position,))
        st.caption(f"One weighted sum per position, fitted on {wts['train_seasons'].iloc[0]} ({int(wts['n_rows'].iloc[0])} player-games). "
                   "The projection is a constant plus each input times its weight. Last season's numbers fade out over a player's "
                   "first six games of this season.")
        st.dataframe(wts[["feature", "weight"]], hide_index=True, width="stretch")
