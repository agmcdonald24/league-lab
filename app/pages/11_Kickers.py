"""Kicker streaming comparison — realized outcomes only."""

import streamlit as st
from lib.charts import bar_chart, color_map, line_chart
from lib.db import query
from lib.table import Col, howto, show
from lib.ui import (
    freshness_banner,
    league_slots,
    perspective,
    player_link,
    season_picker,
    setup,
    unavailable,
)

setup("Kickers")
freshness_banner()

current_league_id, my_roster, _ = perspective(require_team=False)
if "K" not in league_slots(current_league_id):
    st.info("This league does not start a kicker, so there is no kicker streaming to review. Pick another league in the sidebar.")
    st.stop()


# ---- C3 (R-13): next week's kicker projection, the same number the lineup and the waiver list use
def kicker_projection_section(league_id: str, roster_id: int | None) -> None:
    wk = query("""select p.season, p.week from analytics.mart_player_week_projections p
                    join analytics.dim_game g on g.season = p.season and g.week = p.week and g.season_type = 'REG'
                    where p.league_id = %s and p.position = 'K'
                    group by 1, 2 having max(g.kickoff_at) > now() order by 1, 2 limit 1""", (league_id,))
    st.subheader("Next week's kickers")
    if wk.empty:
        st.caption("No kicker projection for an upcoming week yet (the nightly refresh writes it).")
        return
    season, week = int(wk["season"].iloc[0]), int(wk["week"].iloc[0])
    ks = query("""select p.gsis_id, p.player_name, p.team, p.opponent, p.is_home, p.proj_points, p.p10, p.p90, p.report_status,
                           p.is_rankable, p.rank_pos, a.rostered_by_roster_id, a.rostered_by_team, a.is_free_agent
                    from analytics.mart_player_week_projections p
                    left join analytics.mart_player_availability a on a.league_id = p.league_id and a.gsis_id = p.gsis_id
                    where p.league_id = %s and p.season = %s and p.week = %s and p.position = 'K'
                    order by p.proj_points desc""", (league_id, season, week))
    if ks.empty:
        st.caption(f"No kicker projection for week {week} yet.")
        return
    mine = query("""select r.gsis_id, r.player_name, r.player_value, r.value_source, m.nfl_team
                      from analytics.mart_lineup_recommendation r
                      left join analytics.mart_league_roster_membership m
                             on m.league_id = r.league_id and m.sleeper_player_id = r.sleeper_player_id
                      where r.league_id = %s and r.season = %s and r.week = %s and r.roster_id = %s and r.slot_type = 'K'""",
                 (league_id, season, week, roster_id)) if roster_id is not None else None
    ks["matchup"] = ks.apply(lambda r: f"{r['team']} {'vs' if r['is_home'] else '@'} {r['opponent']}", axis=1)
    is_fa = ks["is_free_agent"].astype("boolean").fillna(False).astype(bool)
    ks["who_has_him"] = ks["rostered_by_team"].fillna("").where(~is_fa, "Free agent")
    ks["range"] = ks.apply(lambda r: f"{r['p10']:.0f}–{r['p90']:.0f}", axis=1)
    healthy = ks[ks["is_rankable"].astype("boolean").fillna(True).astype(bool)]
    fa = healthy[is_fa[healthy.index]]
    best_fa = fa.iloc[0] if not fa.empty else None
    with st.container(border=True):
        if mine is not None and not mine.empty and isinstance(mine["player_name"].iloc[0], str):
            m = mine.iloc[0]
            row = ks[ks["gsis_id"] == m["gsis_id"]]
            if row.empty and isinstance(m["nfl_team"], str):   # a kicker Sleeper cannot map to an NFL id: his team's kicker
                row = ks[ks["team"] == {"LAR": "LA"}.get(m["nfl_team"], m["nfl_team"])]
                row = row if len(row) == 1 else row.iloc[0:0]
            where = f" ({row['matchup'].iloc[0]}, likely {row['range'].iloc[0]})" if not row.empty else ""
            st.markdown(f"**Week {week}: your kicker {player_link(m['gsis_id'], m['player_name'])} projects "
                        f"{float(m['player_value']):.1f} points**{where}.")
            if best_fa is not None:
                gap = float(best_fa["proj_points"]) - float(m["player_value"])
                if gap > 0.05:
                    st.markdown(f"Best free agent: **{player_link(best_fa['gsis_id'], best_fa['player_name'])}** "
                                f"({best_fa['matchup']}) projects {float(best_fa['proj_points']):.1f}: **+{gap:.1f}** over yours.")
                else:
                    st.markdown(f"No free-agent kicker projects more than yours (best: {best_fa['player_name']}, "
                                f"{float(best_fa['proj_points']):.1f}).")
        else:
            top = healthy.iloc[0] if not healthy.empty else ks.iloc[0]
            st.markdown(f"**Week {week}: the top projected kicker is {player_link(top['gsis_id'], top['player_name'])}** "
                        f"({top['matchup']}), {float(top['proj_points']):.1f} points.")
            if best_fa is not None:
                st.markdown(f"Best free agent: **{player_link(best_fa['gsis_id'], best_fa['player_name'])}** "
                            f"({best_fa['matchup']}), {float(best_fa['proj_points']):.1f}.")
    with st.expander(f"All kickers, week {week}"):
        show(ks, ["player_name", "matchup", "proj_points", "range", "who_has_him"],
             overrides={"matchup": Col("Game"), "proj_points": Col("Proj", "num1", "Projected points in this league's scoring"),
                        "range": Col("Likely range", help="Eight weeks in ten land inside this range"),
                        "who_has_him": Col("Rostered by")})
    howto(
        "A kicker's week depends mostly on his team: how many points it is expected to score (the betting line), how often "
        "its drives stall in field-goal range, how many touchdowns it scores (extra points), the other team's defense, a dome, "
        "and the kicker's own accuracy from each distance over his career.",
        "The projection is his expected field goals by distance, misses and extra points, priced in this league's scoring, "
        "so a 50-yard kicker is worth more here where 50+ pays 5. The same number values him in your lineup and on the waiver list.",
        "**Likely range**: eight weeks in ten land inside it. Kicking is noisy: a projection of 8 often ends at 3 or 14.",
        "Is it better than just using points per game? Tested on each of the 2021–2025 seasons with only earlier seasons to learn "
        "from, it put kickers in a better order than their points per game so far in all five, and missed by 3.7 points a week "
        "on average against 4.1. The edge is real but small: kickers are close to each other, so do not chase half a point.",
        title="How to read this",
    )


kicker_projection_section(current_league_id, my_roster)
# ---- end C3
league = season_picker(current_league_id, "League season")
league_id = league["league_id"]
season = int(league["season"])

st.subheader("Season summary")
howto(
    "Did streaming kickers actually pay? This compares what each roster's *started* kicker scored.",
    "**Common weeks** are the weeks in which every roster started a kicker, so totals compare like with like. "
    "**vs week avg** is the roster's kicker minus the league's average started kicker that week.",
    "**Kickers used**, **Changes** and **Acquired** show how much churn it took. A roster with one kicker all year and a top-3 total didn't need to stream.",
    "This reports what happened. It does not reconstruct who was on waivers or simulate the alternative.",
)
summary = query(
    """select roster_id, team_name, manager_name, weeks_started_k, common_weeks, total_points_common_weeks,
              avg_points_common_weeks, stddev_points_common_weeks, avg_points_vs_week_avg,
              distinct_kickers_started, kicker_changes, kicker_acquisitions, rank_common_weeks
       from analytics.mart_league_kicker_summary where league_id = %s order by rank_common_weeks""",
    (league_id,),
)
with st.container(border=True):     # the answer first (U-13); the table behind it
    if summary.empty:
        st.markdown("**No started kickers scored yet this season.**")
    else:
        best = summary.sort_values("rank_common_weeks").iloc[0]
        line = (f"**Most started-kicker points: {best['team_name']}, {float(best['total_points_common_weeks'] or 0):.1f} "
                f"in {int(best['common_weeks'] or 0)} common weeks.**")
        mine = summary[summary["roster_id"] == my_roster] if my_roster is not None and league_id == current_league_id else summary.iloc[0:0]
        if not mine.empty and mine.iloc[0]["team_name"] != best["team_name"]:
            m = mine.iloc[0]
            line += f" Yours: {int(m['rank_common_weeks'])} of {len(summary)} ({float(m['total_points_common_weeks'] or 0):.1f})."
        st.markdown(line)
with st.expander("Every roster's kickers, every column"):
    show(summary, [c for c in summary.columns if c != "roster_id"],
         phone_cols=["team_name", "total_points_common_weeks", "avg_points_vs_week_avg", "kicker_changes", "rank_common_weeks"])
if not summary.empty:
    st.plotly_chart(bar_chart(summary, "team_name", "total_points_common_weeks", "Started-kicker points, common weeks", "points", horizontal=True), width="stretch")

weekly = query(
    """select week, team_name, gsis_id, kicker_name, nfl_team, points, round(week_avg_started_k::numeric, 2) as week_avg,
              week_rank, changed_kicker
       from analytics.mart_league_kicker_week where league_id = %s order by week, team_name""",
    (league_id,),
)
st.subheader("Week by week")
teams = sorted(weekly["team_name"].dropna().unique().tolist())
pick = st.multiselect("Teams", teams, default=teams[:6], max_selections=8)
sub = weekly[weekly["team_name"].isin(pick)]
if not sub.empty:
    st.plotly_chart(line_chart(sub, "week", "points", "team_name", "Started kicker points by week", "points", y_format=".1f", colors=color_map(teams)), width="stretch")
with st.expander("Every started kicker, week by week"):
    show(weekly, [c for c in weekly.columns if c != "gsis_id"], height=420, phone_cols=["week", "team_name", "kicker_name", "points", "week_rank"])

unavailable("Streaming counterfactuals", "Reconstructed waiver availability and 'best available kicker' simulations are later work; "
            "only started points are compared here.")
