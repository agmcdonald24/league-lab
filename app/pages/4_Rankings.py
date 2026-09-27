"""Rankings: weekly projections per position — the transparent baseline formula and projection v2 (a projected
stat line priced in this league's scoring, with a floor and a ceiling) — and the backtests that say how far to trust each."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from lib.charts import SURFACE, bar_chart, base_layout
from lib.db import query, require_relations
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
    "**Two projections, same as-of rule** (a week-N projection sees only games before week N — the backtests depend on that):",
    "**Projection v2** projects the *stat line* — targets, receptions, yards, touchdowns, carries, attempts, interceptions — with a gradient-boosted "
    "model per position, then prices that line in **this league's** scoring. Two leagues with different scoring get different boards. "
    "It also gives a **floor (P10)** and a **ceiling (P90)**: about 80% of outcomes land between them (the backtest reports the real share).",
    "**Baseline** is one weighted sum per position — form, usage, matchup, Vegas, home — fitted once on 2019–2022 and printed at the bottom. "
    "It is priced in the reference league's scoring only. v2 is the default wherever the backtest shows it ahead; the baseline stays as the check.",
    "**Trust** is measured, not asserted: the *Backtest* section scores each projection on seasons the model never saw "
    "(v2 walk-forward: a season is scored by a model trained only on the seasons before it). A rank correlation around 0.6 means the order "
    "is right more often than not and wrong plenty.",
    "**Out / Doubtful / IR** are excluded from the ranked list. **Questionable** stays in and is flagged; check the news before kickoff.",
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
if season == cur_season and week == cur_week:
    st.caption(f"NFL {season} week {week} is the next week to be played: this is the live board. "
               "Lines and injury reports update through the week; refresh on Sunday morning.")
elif season < cur_season or week < cur_week:
    st.caption(f"Week {week} has been played: the table shows what the projection said *before* the games, next to what happened.")

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
        f"**Proj** is the projected stat line put through **{league_name}**'s scoring map. "
        "**Floor** and **Ceiling** are the 10th and 90th percentiles of the week's points: about 80% of outcomes land between them, "
        "one week in ten below the floor, one in ten above the ceiling. The wider the range, the less the projection should be trusted.",
        "The stat-line columns are what the projection is made of: expected targets, receptions, yards and touchdowns (a TD of 0.45 means "
        "a 45% chance of one, roughly).",
        "**xPPG (L5)**, **PPG**, **Prev PPG** are the as-of inputs in the reference league's scoring. **Opp rank** 1 = the defense that gives up the most to this position.",
        "When the week has been played, **Actual** (this league's scoring), **Actual rank** and **In range** appear.",
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
        "**Proj** is the projection in the reference league's scoring; the five columns after it are its parts and add up to it (plus a small intercept). "
        "A player can be #3 on form and #12 overall because his implied team total is low and the opponent is stiff — that is the point.",
        "**xPPG (L5)** = expected points over the last five games (opportunity); **PPG** season / last 3; **Prev PPG** last season. "
        "**Opp allowed** = points the opponent gives up per game to this position so far, next to the league average. "
        "**Implied total** = the team's Vegas-implied points.",
        "When the week has been played, **Actual** and **Actual rank** appear so you can see where the projection was right and wrong.",
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

# ---------------------------------------------------------------- backtest
st.subheader("Backtest — how much to trust this")
if model == "v2":
    howto(
        "**Walk-forward**: each held-out season is scored by a model trained only on the seasons before it (2021 by 2016–2020, … 2025 by 2016–2024), "
        f"in **{league_name}** scoring, on players who played. **Spearman** = rank correlation between the projected order and actual points "
        "(1 = perfect, 0 = coin flip); **Top-N hit rate** = of the week's actual top-N scorers (QB/TE 12, RB/WR 24), the share the projection's "
        "top-N caught; **MAE** = average miss in points; **Coverage** = share of actuals that landed inside P10–P90 (target 80%); **Range** = mean P90 − P10.",
        "Three rows per position: the v2 projection (priced line), the v2 P50 (projection plus the median residual, shown for completeness), "
        "and the baseline formula scored against the same actuals. "
        "If the baseline wins a position in a season, that is a finding, not a bug — the page shows it either way. `make backtest-v2` refreshes this.",
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
        "The weights were fitted on 2019–2022. Each held-out season (2023 on) is scored week by week, position by position, on players who played: "
        "**Spearman** = rank correlation between the projected order and the actual points (1 = perfect, 0 = coin flip); "
        "**Top-N hit rate** = of the week's actual top-N scorers (QB/TE 12, RB/WR 24), the share the projection's top-N caught; "
        "**MAE** = average miss in points. The three naive rows are what you would get by sorting on one column.",
        "Read the gaps, not the levels: weekly fantasy scoring is mostly noise, so 0.6 is good. If a naive scorer beats the baseline for a position "
        "in a season, that is a finding, not a bug — the page shows it either way. `make backtest` refreshes this after the season ends.",
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

# ---------------------------------------------------------------- the formula / the model
if model == "v2":
    with st.expander("The model (projection v2)"):
        meta = rk[["model_version", "train_seasons"]].dropna().head(1) if "model_version" in rk.columns else pd.DataFrame()
        trained = f"trained on {meta['train_seasons'].iloc[0]}" if not meta.empty else "not fitted yet"
        st.markdown(
            f"**{meta['model_version'].iloc[0] if not meta.empty else 'v2'}**, {trained}. Per position: one gradient-boosted regressor per stat-line component "
            "(Poisson loss for counts and touchdowns, squared error for yards) over ~75 as-of features — season-to-date and last-3 per-game rates for every "
            "component, snap and target/carry shares, first-read share, expected points, last season's rates, the opponent's points allowed to the position, "
            "the closing line's implied total and spread, home/away, the injury report, and how many games the season has (so last season fades out as this "
            "one accumulates). Points = the projected line put through this league's scoring map. Floor and ceiling are quantile models of the miss "
            "around that projection (learned on out-of-fold misses), widened on the newest training season so that 80% of outcomes land inside "
            "(split-conformal). Hyperparameters are fixed "
            "constants in `league_lab.projections`; a change is a new model version. Refit once a season (`make project`)."
        )
        imp = query("""select position, feature, round(importance::numeric, 3) as importance from ops.projection_importance
                       where position = %s order by importance desc limit 12""", (position,))
        if not imp.empty:
            st.caption("What the interval model leans on (permutation importance of the median-miss model on the newest held-out season).")
            st.dataframe(imp[["feature", "importance"]], hide_index=True, width="stretch")
else:
    with st.expander("The formula (seed `ranking_weights.csv`)"):
        wts = query("select position, feature, weight, train_seasons, n_rows, r2_train, fitted_at from analytics_seeds.ranking_weights where position = %s order by feature", (position,))
        st.caption(f"Fitted on {wts['train_seasons'].iloc[0]} ({int(wts['n_rows'].iloc[0])} player-weeks, R² {float(wts['r2_train'].iloc[0]):.2f}) on {wts['fitted_at'].iloc[0]}. "
                   "proj = intercept + Σ weight × feature. f_sample runs 0 → 1 over the first six games so last season fades out.")
        st.dataframe(wts[["feature", "weight"]], hide_index=True, width="stretch")
