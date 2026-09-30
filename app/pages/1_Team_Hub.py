"""Team Hub: one roster, answer first (plan B2). Cards: this week's best lineup and its closest call,
the 4-week outlook and depth against the league, and how the starters were acquired; then the roster as
one table (player, slot, value, margin, acquired). Everything comes from the exact lineup service (B1)
priced in this league's scoring; the season's record, usage and keeper facts sit in expanders below."""

import pandas as pd
import streamlit as st
from lib.charts import line_chart
from lib.db import query, require_relations
from lib.table import Col, howto, show
from lib.ui import (
    align_opponents,
    current_season,
    current_week,
    freshness_banner,
    league_seasons,
    perspective,
    setup,
)

setup("Team Hub")
freshness_banner()
league_id, roster_id, members = perspective(require_team=True)
team = members.set_index("roster_id").loc[roster_id]
require_relations("mart_league_roster_value", "mart_league_roster_rankings", "mart_league_roster_horizon",
                  "mart_league_roster_slot_strength", "mart_league_acquisitions")
st.subheader(f"{team['team_name']} · {team['manager_name']}")


def ordinal(n) -> str:
    n = int(n)
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def pos_name(name, pos) -> str:
    return f"{name} ({pos})" if isinstance(pos, str) and pos else str(name)


def narrow_table(df: pd.DataFrame, cols: list[str], overrides: dict, widths: dict[str, str | int], height: int | None = None,
                 links: dict | None = None) -> None:
    """A phone-first table (plan B2, round-2 convention 2): lib.table.show with the first column pinned and narrow
    widths, so the numbers stay on screen at 390 px; `links` makes a name column open the player card (C1)."""
    show(df, cols, height=height, overrides=overrides, widths=widths, pin=True, links=links)


# ---------------------------------------------------------------- the answer: cards
rv = query("select * from analytics.mart_league_roster_value where league_id = %s and roster_id = %s", (league_id, roster_id))
rk = query(
    """select measure, horizon, value, league_rank, n_rosters from analytics.mart_league_roster_rankings
       where league_id = %s and roster_id = %s""",
    (league_id, roster_id),
)
rows = query(
    """select week, role, slot, slot_type, slot_order, bench_rank, gsis_id, player_name, position, player_value, value_source, lineup_margin,
              is_locked, report_status, reason, acquired_label, acquired_how_by_manager
       from analytics.mart_league_roster_horizon
       where league_id = %s and roster_id = %s and is_this_week""",
    (league_id, roster_id),
)

if rv.empty:
    st.info("No lineup for the weeks ahead yet (the season is over, or `league-lab project` has not run since the last build).")
else:
    v = rv.iloc[0]
    ranks = rk.set_index("measure") if not rk.empty else pd.DataFrame()

    def rank_text(measure: str) -> str:
        if measure not in ranks.index:
            return ""
        r = ranks.loc[measure]
        return f"{ordinal(r['league_rank'])} of {int(r['n_rosters'])} in the league ({r['horizon']})"

    week = int(v["week"])
    starters = rows[rows["role"] == "starter"]
    with st.container(border=True):
        st.markdown(f"**Week {week}: your best lineup projects {v['lineup_value']:.1f}** — {rank_text('lineup_value')}.")
        if pd.notna(v["weakest_slot"]):
            who = pos_name(v["weakest_player_name"], v["weakest_position"])
            if isinstance(v["weakest_replacement_name"], str):
                st.markdown(f"Your closest call: **{v['weakest_slot']}, {v['weakest_player_name']} over "
                            f"{v['weakest_replacement_name']} by {v['weakest_margin']:.2f}**.")
            else:
                st.markdown(f"Your closest call: **{v['weakest_slot']}, {who}** — nobody on the bench can fill in for him "
                            f"(he is worth {v['weakest_margin']:.1f} to the lineup).")
        elif int(v["n_locked"] or 0):
            st.markdown("Every starter's game has kicked off: no lineup calls left this week.")
        notes = []
        if isinstance(v["empty_slots"], str) and v["empty_slots"]:
            notes.append(f"nobody can play **{v['empty_slots']}** this week")
        if int(v["n_unvalued"] or 0):
            unv = starters[starters["value_source"] == "unvalued"]
            notes.append(f"{', '.join(unv['player_name'].astype(str))} {'has' if len(unv) == 1 else 'have'} no projection yet (counted as 0)")
        if int(v["n_questionable"] or 0):
            q = starters[starters["report_status"] == "Questionable"]
            notes.append(f"questionable: {', '.join(q['player_name'].astype(str))}")
        if notes:
            st.caption("Heads-up: " + "; ".join(notes) + ".")
    with st.container(border=True):
        st.markdown(f"**{v['horizon_label'].capitalize()}: {v['horizon_value']:.1f} projected** — {rank_text('horizon_value')}.")
        if pd.notna(v["worst_week"]) and int(v["horizon_weeks"]) > 1:
            st.markdown(f"Toughest week: week {int(v['worst_week'])} ({v['worst_week_value']:.1f}).")
        st.markdown(f"**Depth: your bench alone would field {v['bench_value']:.1f}** in week {week} — {rank_text('bench_value')}.")
    with st.container(border=True):
        if not starters.empty:
            how = starters["acquired_how_by_manager"].fillna("unknown").replace({"free_agent": "waiver"})
            # the most common way in; on a tie the one that says most about the manager (trade first)
            priority = {"trade": 0, "draft": 1, "inherited": 2, "waiver": 3, "commissioner": 4}
            counts = how.value_counts()
            counts = counts.loc[sorted(counts.index, key=lambda k: (-counts[k], priority.get(k, 9)))]
            n = len(starters)
            top = counts.index[0]
            names = ", ".join(starters.loc[how == top, "player_name"].astype(str).tolist())
            phrase = {"trade": "came by trade", "draft": "are your own draft picks", "waiver": "came off waivers or free agency",
                      "inherited": "came with the team when it changed hands", "commissioner": "were placed by the commissioner"}.get(top, "have no recorded move")
            st.markdown(f"**{counts.iloc[0]} of {n} starters {phrase}**: {names}.")
            label = {"trade": "trade", "draft": "draft", "waiver": "waiver / free agent", "inherited": "inherited", "commissioner": "commissioner"}
            st.caption("Your week-" + str(week) + " starters: " + " · ".join(f"{c} {label.get(k, k)}" for k, c in counts.items()) + ".")

    howto(
        "**Lineup value** is the projected points of the best lineup you can start this week, in your league's scoring, with FLEX "
        "and superflex filled by whoever is worth most there. The rank next to it is where that puts you in the league.",
        "**Margin** is how much your lineup loses without that starter. The smallest one is your **closest call**: check the news "
        "on those two players before kickoff.",
        "**Next 4 weeks** adds up your best lineup for each of the next four weeks, byes and injuries included. Low here but high "
        "this week? Look for cover now.",
        "**Depth** is the lineup your bench alone could put out. Low depth means one injury hurts: a trade or a claim for a starter "
        "matters more to you than to most.",
        "**Acquired** is how each player joined your team: draft pick, trade (and with whom), waivers or free agency. Dynasty "
        "rosters read the whole league history.",
        title="How to read this",
    )

# ---------------------------------------------------------------- the roster, one table
REASON = {"IR slot": "IR", "taxi squad": "Taxi", "bye": "Bye", "NFL injured reserve": "NFL IR", "game started (bench)": "Locked · bench",
          "no NFL team": "No NFL team"}
if not rows.empty:
    tbl = rows.copy()
    order = {"starter": 0, "empty": 0, "bench": 1, "unplayable": 2}
    tbl["_o"] = tbl["role"].map(order)
    tbl = tbl.sort_values(["_o", "slot_order", "bench_rank", "player_value"], ascending=[True, True, True, False], na_position="last")
    tbl["player"] = [
        ("—" if r.role == "empty" else pos_name(r.player_name, r.position)) + (" · Q" if r.report_status == "Questionable" else "")
        for r in tbl.itertuples()]
    tbl["where"] = [
        (str(r.slot).replace("SUPER_FLEX", "Superflex") + (" · locked" if r.is_locked else "")) if r.role in ("starter", "empty")
        else "Bench" if r.role == "bench" else REASON.get(r.reason, r.reason or "Out")
        for r in tbl.itertuples()]
    tbl["acquired"] = tbl["acquired_label"]
    with st.expander(f"Roster · week {int(rows['week'].iloc[0])} lineup ({(rows['role'] != 'empty').sum()} players)", expanded=False):
        narrow_table(tbl, ["player", "where", "player_value", "lineup_margin", "acquired"], height=min(80 + 35 * len(tbl), 980),
             links={"player": ("gsis_id", "player_name")},
             widths={"player": 150, "where": 72, "player_value": 56, "lineup_margin": 60, "acquired": "large"},
             overrides={"player": Col("Player"), "where": Col("Slot", help="Starting slot this week, Bench, or why he cannot play (IR, Taxi, Bye, Out)"),
                        "player_value": Col("Value", "num1", "This week's projection in this league's scoring (K: points per game this season; DEF: points per game Sleeper scored)"),
                        "lineup_margin": Col("Margin", "num2", "What the lineup loses without him, the whole lineup re-picked. Small = a close call"),
                        "acquired": Col("Acquired", help="How he joined this roster: draft round.pick, trade (from whom), waiver / free agent, with the season")})

# ---------------------------------------------------------------- starter strength vs depth
ss = query(
    """select slot_type, slots, first_slot_order, top_gsis_id, top_player_name, top_position, top_value, starter_strength, replacement_name, replacement_value,
              empty_slots, top_is_locked
       from analytics.mart_league_roster_slot_strength where league_id = %s and roster_id = %s order by first_slot_order""",
    (league_id, roster_id),
)
if not ss.empty:
    with st.expander("Starter strength vs depth, by slot", expanded=False):
        st.caption("Your best starter at each slot, and what the lineup loses if he sits (the whole lineup re-picked). "
                   "A big number with a weak replacement is a slot one injury away from trouble.")
        s2 = ss.copy()
        s2["slot"] = s2["slot_type"].replace({"SUPER_FLEX": "Superflex"}) + s2["slots"].map(lambda n: f" ×{int(n)}" if n > 1 else "")
        s2["best"] = [pos_name(r.top_player_name, r.top_position) if isinstance(r.top_player_name, str) else "—" for r in s2.itertuples()]
        s2["next_up"] = [(f"{r.replacement_name} ({r.replacement_value:.1f})" if isinstance(r.replacement_name, str)
                          else ("locked" if r.top_is_locked else "nobody")) for r in s2.itertuples()]
        narrow_table(s2, ["slot", "best", "top_value", "starter_strength", "next_up"], links={"best": ("top_gsis_id", "top_player_name")},
             widths={"slot": 80, "best": 150, "top_value": 56, "starter_strength": 70, "next_up": "medium"},
             overrides={"slot": Col("Slot"), "best": Col("Best starter"), "top_value": Col("Value", "num1"),
                        "starter_strength": Col("Strength", "num2", "The best lineup minus the best lineup without him: what he is worth over the next man up"),
                        "next_up": Col("Next man up", help="Who comes into the lineup if he sits (a FLEX player may slide over; this is who joins the lineup)")})

# ---------------------------------------------------------------- season so far (compact)
prof = query("select * from analytics.mart_league_manager_profile where league_id = %s and roster_id = %s", (league_id, roster_id))
if not prof.empty:
    p = prof.iloc[0]
    parts = [f"Record **{int(p['wins'] or 0)}-{int(p['losses'] or 0)}**"]
    if pd.notna(p["standing"]):
        parts.append(f"standing **{int(p['standing'])}**")
    if pd.notna(p["all_play_win_pct"]):
        parts.append(f"all-play **{p['all_play_win_pct']:.0%}**")
    if pd.notna(p["luck_wins"]):
        parts.append(f"luck **{p['luck_wins']:+.2f}** wins")
    if pd.notna(p["avg_bench_points_left"]):
        parts.append(f"left on the bench **{p['avg_bench_points_left']:.1f}**/wk")
    parts.append(f"FAAB spent **{int(p['faab_spent'] or 0)}**")
    st.markdown("Season so far: " + " · ".join(parts))
    st.caption("All-play = the win rate if you had played every roster every week. Luck = actual wins minus the wins your points deserve.")

# ---------------------------------------------------------------- usage and production (wide: in an expander)
with st.expander("Usage and production, every player", expanded=False):
    howto(
        "**PPG** is what he has scored per game in your league's scoring. **xPPG** (expected points per game) is what his targets "
        "and carries are usually worth, given where they happened on the field.",
        "**PPG − xPPG** below zero: he has been unlucky for the work he gets, so expect more. Above zero: he is scoring more than "
        "his work supports, so expect less. Hold the first, think about selling the second.",
        "**Target %** (his share of the team's targets) and **Snap %** (share of plays he is on the field) are the work that drives "
        "points. **(L3)** means the last 3 games: a jump there is the first sign of a bigger role.",
        "**Opp rank**: next week's defense against his position, 1 = gives up the most (the matchup you want), 32 = the fewest.",
    )
    roster = query(
        """select a.gsis_id, a.player_name, a.position, a.nfl_team, a.injury_status, a.games_played, a.ppg_std, a.points_per_game_l3,
                  a.expected_per_game, a.diff_per_game, a.target_share, a.target_share_l3, a.first_read_share_std, a.first_read_share_l3,
                  a.carry_share, a.carry_share_l3, a.avg_offense_snap_pct, a.snap_pct_l3, a.opponent, a.opp_rank_std, a.opp_rank_l4,
                  t.tags, t.momentum
           from analytics.mart_player_availability a
           left join analytics.mart_player_trend_tags t on t.gsis_id = a.gsis_id and t.season = a.season
           where a.league_id = %s and a.rostered_by_roster_id = %s
           order by array_position(array['QB','RB','WR','TE','K'], a.position), a.ppg_std desc nulls last""",
        (league_id, roster_id),
    )
    # one week rule (C1): the opponent of the week every page means by "this week" (lib.ui.current_week)
    roster = align_opponents(roster, current_season(league_id), current_week(league_id))
    injured = st.toggle("Only players on the injury report", value=False, key="th_injured")
    if injured:
        roster = roster[roster["injury_status"].notna() & (roster["injury_status"] != "")]
    cols = ["player_name", "position", "nfl_team", "games_played", "tags", "momentum", "ppg_std", "points_per_game_l3", "expected_per_game",
            "diff_per_game", "target_share", "target_share_l3", "first_read_share_std", "first_read_share_l3", "carry_share", "carry_share_l3",
            "avg_offense_snap_pct", "snap_pct_l3", "opponent", "opp_rank_std", "opp_rank_l4"]
    if roster["injury_status"].notna().any() and (roster["injury_status"].fillna("") != "").any():
        cols.insert(3, "injury_status")   # only when somebody is not healthy (round-2 convention)
    show(roster, cols, height=min(80 + 36 * len(roster), 640), phone_cols=["player_name", "position", "ppg_std", "expected_per_game", "opponent"])

# ---------------------------------------------------------------- lineup discipline
with st.expander("Started vs best possible lineup, by week", expanded=False):
    st.caption("Best possible = the highest-scoring lineup you could have set from your roster that week, at Sleeper's own points "
               "(hindsight). Left on bench = the gap; these totals match Sleeper's max points.")
    lu = query(
        """select week, points_started, points_optimal, bench_points_left, lineup_efficiency
           from analytics.mart_league_optimal_lineup where league_id = %s and roster_id = %s order by week""",
        (league_id, roster_id),
    )
    if not lu.empty:
        long = pd.concat([
            lu[["week", "points_started"]].rename(columns={"points_started": "points"}).assign(series="started"),
            lu[["week", "points_optimal"]].rename(columns={"points_optimal": "points"}).assign(series="best possible"),
        ])
        st.plotly_chart(line_chart(long, "week", "points", "series", "Started vs best possible", "points", y_format=".1f"), width="stretch")
        show(lu, ["week", "points_started", "points_optimal", "bench_points_left", "lineup_efficiency"])

# ---------------------------------------------------------------- production and acquisition (keeper facts)
ls = league_seasons(league_id)
league_type = ls["league_type"].iloc[0] if not ls.empty else "redraft"
title = "Production and acquisition" if league_type == "dynasty" else "Keeper facts"
with st.expander(title, expanded=False):
    if league_type == "dynasty":
        st.caption("A dynasty keeps everyone: how each player joined this roster (across every season of the league), what he has "
                   "produced, and where that ranks among all NFL players at his position this season.")
    else:
        st.caption("How each player was acquired this season, what he has produced, and where that ranks among all NFL players at his "
                   "position. Apply your league's keeper rule yourself: League Lab supplies the facts.")
    kc = query(
        """select k.gsis_id, k.player_name, k.position, a.acquired_label as acquired, k.games_played, k.ppg_std, k.position_rank_ppg,
                  k.expected_per_game, k.diff_per_game
           from analytics.mart_league_keeper_candidates k
           left join analytics.mart_league_acquisitions a
                  on a.league_id = k.league_id and a.roster_id = k.roster_id and a.sleeper_player_id = k.sleeper_player_id
           where k.league_id = %s and k.roster_id = %s
           order by k.ppg_std desc nulls last""",
        (league_id, roster_id),
    )
    show(kc, ["player_name", "position", "acquired", "games_played", "ppg_std", "position_rank_ppg", "expected_per_game", "diff_per_game"],
         phone_cols=["player_name", "position", "acquired", "ppg_std", "diff_per_game"], overrides={"acquired": Col("Acquired", help="How he joined this roster, read across the whole league history")})
