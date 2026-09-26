"""Rankings: a transparent weekly projection per position, with every term visible and a backtest that says how far to trust it."""

import pandas as pd
import streamlit as st
from lib.charts import bar_chart
from lib.db import query, require_relations
from lib.table import howto, show
from lib.ui import freshness_banner, next_week_info, perspective, setup

setup("Rankings")
freshness_banner()
require_relations("mart_player_week_rankings", "mart_player_week_features", "mart_backtest_summary")
league_id, roster_id, members = perspective(require_team=False)
cal = next_week_info()
cur_season = int(cal["season"]) if not cal.empty else None
cur_week = int(cal["next_week"]) if not cal.empty and pd.notna(cal["next_week"]) else 1

howto(
    "**Projection** is one weighted sum per position — no black box: *form* (expected points over the last five games, season and last-3 PPG, "
    "last season fading out as this one accumulates), *usage* (snap share and whether the last-3 target/carry share sits above the season share), "
    "*matchup* (opponent's points allowed to the position vs the league average, as of the games played so far), *Vegas* (implied team total "
    "from the closing line) and *home*. The weights were fitted once on 2019–2022 and never touched since; the seed is printed at the bottom.",
    "**Every number is as-of the week**: a week-N projection sees only games before week N — the backtest depends on that.",
    "**Trust** is measured, not asserted: the *Backtest* section scores this projection against three naive rankings (season PPG, last-3 PPG, expected "
    "points) on seasons the weights never saw. A rank correlation around 0.6 means the order is right more often than not and wrong plenty; "
    "if a naive scorer ever wins, use that instead.",
    "**Out / Doubtful / IR** are excluded from the ranked list. **Questionable** stays in and is flagged; check the news before kickoff.",
    title="How to use this page",
)

# ---------------------------------------------------------------- controls
seasons = query("select distinct season from analytics.mart_player_week_rankings order by season desc")["season"].astype(int).tolist()
c0, c1, c2, c3, c4 = st.columns([0.8, 0.8, 1, 1.4, 1])
season = c0.selectbox("Season", seasons, index=seasons.index(cur_season) if cur_season in seasons else 0)
weeks = query("select distinct week from analytics.mart_player_week_rankings where season = %s order by week", (season,))["week"].astype(int).tolist()
default_week = cur_week if season == cur_season and cur_week in weeks else weeks[-1]
week = c1.selectbox("Week", weeks, index=weeks.index(default_week))
position = c2.selectbox("Position", ["QB", "RB", "WR", "TE"], index=2)
scope_options = {"all": "Everyone", "fa": "Free agents in this league", "rostered": "Rostered in this league", "team": "Selected team only"}
scope = c3.selectbox("Who", list(scope_options), format_func=lambda k: scope_options[k], index=0)
top_n = c4.number_input("Show", 10, 80, 36)
if season == cur_season and week == cur_week:
    st.caption(f"NFL {season} week {week} is the next week to be played: this is the live board. "
               "Lines and injury reports update through the week; refresh on Sunday morning.")
elif season < cur_season or week < cur_week:
    st.caption(f"Week {week} has been played: the table shows what the projection said *before* the games, next to what happened.")

avail = query(
    """select gsis_id, rostered_by_roster_id, rostered_by_team, is_free_agent from analytics.mart_player_availability where league_id = %s""",
    (league_id,),
)
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
howto(
    "**Proj** is the projection in this league's scoring; the five columns after it are its parts and add up to it (plus a small intercept). "
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

# ---------------------------------------------------------------- why: contribution chart for the top group
if not ranked.empty:
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
        show(mine, ["rank_pos", "player_name", "team", "opponent", "report_status", "proj_points", "c_form", "c_matchup", "c_vegas", "xppg_l5", "ppg_std", "implied_team_total"] + (["points_actual", "actual_rank_pos"] if played_week else []))

# ---------------------------------------------------------------- backtest
st.subheader("Backtest — how much to trust this")
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

# ---------------------------------------------------------------- the formula
with st.expander("The formula (seed `ranking_weights.csv`)"):
    wts = query("select position, feature, weight, train_seasons, n_rows, r2_train, fitted_at from analytics_seeds.ranking_weights where position = %s order by feature", (position,))
    st.caption(f"Fitted on {wts['train_seasons'].iloc[0]} ({int(wts['n_rows'].iloc[0])} player-weeks, R² {float(wts['r2_train'].iloc[0]):.2f}) on {wts['fitted_at'].iloc[0]}. "
               "proj = intercept + Σ weight × feature. f_sample runs 0 → 1 over the first six games so last season fades out.")
    st.dataframe(wts[["feature", "weight"]], hide_index=True, width="stretch")
