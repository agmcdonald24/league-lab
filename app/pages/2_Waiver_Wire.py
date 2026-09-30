"""Waiver Wire: the claims that improve your lineup (plan B3), then every free agent to browse."""

import pandas as pd
import streamlit as st
from lib.db import missing_relations, query
from lib.table import howto, show
from lib.ui import (
    align_opponents,
    current_season,
    current_week,
    freshness_banner,
    league_slots,
    perspective,
    setup,
)

setup("Waiver Wire")
freshness_banner()
league_id, roster_id, members = perspective(require_team=False)
# one week rule (C1): lib.ui.current_week, the week My Week and the cards use (not mart_nfl_calendar)
season = current_season(league_id)
next_week = current_week(league_id)

# ------------------------------------------------------------- B3: the moves (precomputed nightly)
# One query. mart_waiver_moves holds, per roster, every legal add/drop that raises the roster's best
# lineup this week or over the next four weeks (the lineup solver re-run after the move minus before,
# on the same projections mart_lineup_recommendation shows), ranked; or one 'nothing' row.
MOVES_SQL = """
select week, horizon_last_week, list_kind, move_rank, add_rank, is_best_drop, add_gsis_id, add_name, add_position, add_team,
       add_value, add_value_source, add_reason, add_report_status, add_games_played, is_no_evidence,
       drop_gsis_id, drop_name, drop_position, drop_value, drop_is_starter, drop_horizon_loss, drop_ros_points, add_ros_points,
       weekly_gain, horizon_gain, week_gains, lineup_before, lineup_after, lineup_value, add_slot, fills_empty_slot,
       displaced_name, displaced_position, displaced_value, displaced_slot, open_roster_spots,
       inputs_current, on_current_lineup, as_of
from analytics.mart_waiver_moves
where league_id = %s and roster_id = %s and season = (select max(season) from analytics.mart_waiver_moves where league_id = %s)
order by move_rank nulls first
"""


def _f(v: float) -> str:
    return f"{float(v):.1f}"


def _span(r: pd.Series) -> str:
    """ "the next 4 weeks" (fewer at the end of the season)."""
    n = int(r["horizon_last_week"]) - int(r["week"]) + 1
    return f"the next {n} weeks" if n > 1 else "this week only"


def _weeks_helped(r: pd.Series) -> list[tuple[int, float]]:
    gains = list(r["week_gains"]) if isinstance(r["week_gains"], list | tuple) else []
    return [(int(r["week"]) + i, float(g)) for i, g in enumerate(gains) if g is not None and float(g) > 0.005]


def _weeks_text(r: pd.Series) -> str:
    helped = [w for w, _ in _weeks_helped(r)]
    if not helped:
        return ""
    return ("week " if len(helped) == 1 else "weeks ") + ", ".join(str(w) for w in helped)


def _seat_text(r: pd.Series) -> str:
    """Where he plays this week and who makes way, in plain words (the numbers the lineup uses)."""
    slot = r["add_slot"]
    if not isinstance(slot, str):
        return ""
    if r["fills_empty_slot"]:
        return f"He fills your empty {slot} slot (nobody on your roster can play it this week)."
    if isinstance(r["displaced_name"], str):
        if r["displaced_name"] == r["drop_name"]:
            return f"He starts at {slot}; {r['drop_name']} ({_f(r['drop_value'])} this week) leaves your lineup."
        where = f", from {r['displaced_slot']}" if isinstance(r["displaced_slot"], str) and r["displaced_slot"] != slot else ""
        return (f"He starts at {slot}; **{r['displaced_name']}** ({r['displaced_position']}{where}, projected "
                f"{_f(r['displaced_value'])}) goes to your bench.")
    return f"He starts at {slot}."


def _notes(r: pd.Series) -> list[str]:
    out = []
    if r["is_no_evidence"]:
        out.append("No games this season yet: the projection rests on last season and his role, not on anything he has shown this year.")
    if r["add_value_source"] == "season_ppg":
        out.append("Kickers are valued at their points per game so far this season.")
    if r["add_report_status"] == "Questionable":
        out.append("He is Questionable this week.")
    if isinstance(r["add_reason"], str):
        out.append(f"He cannot play this week ({r['add_reason']}).")
    if isinstance(r["drop_name"], str):
        loss = float(r["drop_horizon_loss"] or 0)
        out.append(f"Dropping {r['drop_name']} costs your lineup {_f(loss)} over {_span(r)} (already counted)."
                   if loss > 0.05 else f"{r['drop_name']} would not start for you in {_span(r)}.")
        if pd.notna(r["drop_ros_points"]) and pd.notna(r["add_ros_points"]) and float(r["drop_ros_points"]) > float(r["add_ros_points"]):
            out.append(f"Careful: {r['drop_name']} projects more than {r['add_name']} over the rest of the season "
                       f"({float(r['drop_ros_points']):.0f} vs {float(r['add_ros_points']):.0f} points).")
    elif r["list_kind"] != "nothing":
        out.append("You have an open roster spot, so nobody has to go.")
    return out


def _headline(r: pd.Series) -> str:
    """The card's answer in one sentence: "Claim A, drop B: +2.9 this week at TE, +6.1 over the next 4 weeks"."""
    who = f"{r['add_name']} ({r['add_position']})"
    claim = f"Claim {who}, drop {r['drop_name']}" if isinstance(r["drop_name"], str) else f"Claim {who}, no drop needed"
    wk, hz = float(r["weekly_gain"]), float(r["horizon_gain"])
    if wk > 0:
        at = f" at {r['add_slot']}" if isinstance(r["add_slot"], str) else ""
        return f"{claim}: {wk:+.1f} this week{at}, {hz:+.1f} over {_span(r)}"
    when = f", all in {_weeks_text(r)}" if _weeks_text(r) and abs(wk) < 0.05 else (f" ({_weeks_text(r)})" if _weeks_text(r) else "")
    this_week = "" if abs(wk) < 0.05 else f", {wk:+.1f} this week"
    return f"{claim}: {hz:+.1f} over {_span(r)}{when}{this_week}"


def _card(title: str, r: pd.Series, week: int) -> None:
    with st.container(border=True):
        st.caption(title)
        st.markdown(f"**{_headline(r)}**")
        lines = []
        if pd.notna(r["add_value"]) and not isinstance(r["add_reason"], str):
            lines.append(f"{r['add_name']} projects {_f(r['add_value'])} for week {week} in your league's scoring. {_seat_text(r)}".strip())
        if float(r["weekly_gain"]) > 0:
            lines.append(f"Your week-{week} lineup: {_f(r['lineup_before'])} → {_f(r['lineup_after'])}.")
        elif _weeks_text(r):
            lines.append(f"It helps in {_weeks_text(r)}, not this week, so there is time: claim him before then.")
        lines += _notes(r)
        st.markdown("  \n".join(lines))


def _why(r: pd.Series) -> str:
    """The table's reason column: short, the card's words."""
    parts = [] if isinstance(r["drop_name"], str) else ["open roster spot, no drop"]
    if r["list_kind"] == "start_now" and isinstance(r["add_slot"], str):
        if r["fills_empty_slot"]:
            parts.append(f"fills empty {r['add_slot']}")
        elif isinstance(r["displaced_name"], str):
            parts.append(f"{r['add_slot']} over {r['displaced_name']} ({_f(r['displaced_value'])})")
    later = [w for w, _ in _weeks_helped(r) if w != int(r["week"])]
    if later and (r["list_kind"] == "cover" or float(r["horizon_gain"]) > float(r["weekly_gain"]) + 0.05):
        parts.append("helps wk " + ", ".join(str(w) for w in later))
    if r["is_no_evidence"]:
        parts.append("no games yet")
    if r["add_report_status"] == "Questionable":
        parts.append("Q")
    if isinstance(r["drop_name"], str) and float(r["drop_horizon_loss"] or 0) > 0.05:
        parts.append(f"drop costs {_f(r['drop_horizon_loss'])}")
    if (isinstance(r["drop_name"], str) and pd.notna(r["drop_ros_points"]) and pd.notna(r["add_ros_points"])
            and float(r["drop_ros_points"]) > float(r["add_ros_points"])):
        parts.append("drop projects more for the season")
    return "; ".join(parts)


decision_week = None
have_moves = not missing_relations(("mart_waiver_moves",))
if have_moves:   # the week the claims are for (the next week with a game still to kick off)
    wk = query("select week from analytics.mart_waiver_moves where league_id = %s order by season desc, week desc limit 1", (league_id,))
    decision_week = int(wk["week"].iloc[0]) if not wk.empty and pd.notna(wk["week"].iloc[0]) else None
if roster_id is None:
    st.info("Pick your team under **Team perspective** in the sidebar: this page then opens with the claims that improve "
            "that roster's lineup, each with the player to drop.", icon="👈")
elif not have_moves:
    st.caption("The waiver moves are computed with the nightly update and are not on this copy yet. The free-agent list is below.")
else:
    mv = query(MOVES_SQL, (league_id, roster_id, league_id))
    if mv.empty:
        st.caption("No waiver moves for this team yet: they are computed with the nightly update (after the projections).")
    else:
        decision_week = int(mv["week"].iloc[0])
        team = members.set_index("roster_id").loc[roster_id, "team_name"]
        st.subheader(f"Best claims for {team} · week {decision_week}")
        best = mv[mv["is_best_drop"].fillna(False).astype(bool)].sort_values("add_rank")
        start = best[best["list_kind"] == "start_now"]
        cover = best[best["list_kind"] == "cover"]
        lineup_now = float(mv["lineup_value"].iloc[0]) if pd.notna(mv["lineup_value"].iloc[0]) else float(mv["lineup_before"].iloc[0])
        if (mv["list_kind"] == "nothing").all():
            with st.container(border=True):
                r = mv.iloc[0]
                why = (" Your roster is over the limit, so no single claim is legal." if pd.notna(r["open_roster_spots"])
                       and int(r["open_roster_spots"]) < 0 else "")
                n = int(r["horizon_last_week"]) - decision_week + 1
                st.markdown(f"**Nothing beats what you have.**  \nNo free agent improves your lineup this week or over the next "
                            f"{n} weeks (week-{decision_week} lineup {_f(lineup_now)}).{why}")
        else:
            if not start.empty:
                _card("Top claim", start.iloc[0], decision_week)
            else:
                with st.container(border=True):
                    st.markdown(f"**Nothing on the wire beats this week's lineup** ({_f(lineup_now)} for week {decision_week}).  \n"
                                "The claims below help in a later week: a bye or an injury you can cover now.")
            shown = set(start.head(1)["add_name"])
            if not cover.empty:
                _card("Best cover for a coming week", cover.iloc[0], decision_week)
                shown.add(cover.iloc[0]["add_name"])
            flyer = best[best["is_no_evidence"].fillna(False).astype(bool) & ~best["add_name"].isin(shown)]
            if not flyer.empty:
                _card("Flyer: no games this season yet", flyer.iloc[0], decision_week)
        st.caption("Upside stashes (a player whose role is growing before his points do) arrive with the role alerts in a later release.")
        stale = []
        if not bool(mv["inputs_current"].iloc[0]):
            stale.append("rosters or injury reports have changed since, so a player may already be gone")
        if not bool(mv["on_current_lineup"].iloc[0]):
            stale.append("your best lineup has been recomputed since, so the gains may have moved")
        if stale:
            asof = pd.to_datetime(mv["as_of"].iloc[0], utc=True).tz_convert("America/New_York")
            st.warning(f"These claims were computed {asof:%a %b %-d, %-I:%M %p} ET; " + " and ".join(stale)
                       + ". They refresh with the nightly update.", icon="⏱️")

        moves = best[best["list_kind"] != "nothing"].copy()
        if not moves.empty:
            with st.expander(f"All {len(moves)} claims that help, best first"):
                moves["waiver_claim"] = moves["add_name"] + " " + moves["add_position"]
                moves["waiver_drop"] = moves["drop_name"]     # blank = an open roster spot (the Why column says so)
                moves["waiver_why"] = moves.apply(_why, axis=1)
                # both players open the player card (C1): the claim and the drop carry their own gsis ids
                show(moves, ["waiver_claim", "waiver_drop", "weekly_gain", "horizon_gain", "waiver_why"], height=420, pin=True,
                     links={"waiver_claim": ("add_gsis_id", "add_name"), "waiver_drop": ("drop_gsis_id", "drop_name")})
                st.caption("One row per player: the drop that costs your lineup least (among equals, the player projected "
                           "to score least the rest of the season). Start-now claims gain this week; the others help later.")
        howto(
            "**What a claim is worth.** For every free agent on an active NFL roster (not Out or on injured reserve) and every "
            "player you could drop (not in your IR slot or on your taxi squad, and not already playing this week), we rebuild your "
            "best legal lineup with the swap and subtract the lineup you have now. The lineup is the one your team page shows: every "
            "slot filled at once, FLEX and superflex included, with the same projections.",
            f"**Week {decision_week}** is the gain in this week's lineup; **weeks {decision_week}–{int(mv['horizon_last_week'].iloc[0])}** add up this week "
            "and the next three, so a bye you can cover and the games the dropped player would have started all count. "
            "*Start now* claims improve this week; the *cover* claims only help a coming week.",
            "**Who to drop.** The player whose loss costs your lineup least over the four weeks; among equals, the one projected to "
            "score least over the rest of the season. We never suggest dropping a player we have no projection for yet "
            "(a kicker or defense your league has not scored, an injured player with no projection): unknown is not zero.",
            "**Only the next four weeks count.** In a dynasty league a young player's future is not in these numbers: look twice before "
            "dropping one. Kickers are valued at their points per game so far this season; free-agent defenses are not valued yet.",
            "**No games yet** marks a player who has not played this season: his projection rests on last season and his role only.",
            title="How to read this",
        )

# ------------------------------------------------------------- browse every free agent
with st.expander("Browse every free agent"):
    week_for_proj = decision_week or next_week
    c1, c2 = st.columns(2)
    league_pos = [p for p in league_slots(league_id) if p in ("QB", "RB", "WR", "TE", "K")]   # no K in a league without a kicker slot
    positions = c1.multiselect("Positions", league_pos, default=[p for p in ("RB", "WR", "TE") if p in league_pos])
    min_games = c2.number_input("Min games played", 0, 17, 2)
    hide_injured = c1.checkbox("Hide Out / IR", value=True)
    sort_labels = {
        "proj_v2": f"Projection (week {week_for_proj})" if week_for_proj else "Projection (next week)",
        "expected_per_game": "Expected PPG (opportunity)", "momentum": "Momentum (role trend, needs 4+ games)", "target_share_l3": "Target % (last 3)", "target_share_trend": "Target trend",
        "first_read_share_l3": "1st-read share (last 3)",
        "carry_share_l3": "Carry % (last 3)", "snap_pct_l3": "Snap % (last 3)", "points_per_game_l3": "PPG (last 3)", "ppg_std": "PPG (season)",
        "diff_per_game": "Most unlucky (PPG − xPPG)",
    }
    sort_by = c2.selectbox("Rank by", list(sort_labels), format_func=lambda k: sort_labels[k])
    fa = query(
        """select a.gsis_id, a.player_name, a.position, a.nfl_team, a.roster_status, a.injury_status, a.depth_rank,
                  a.games_played, a.targets_per_game, a.carries_per_game, a.target_share, a.target_share_l3, a.target_share_trend,
                  a.carry_share, a.carry_share_l3, a.avg_offense_snap_pct, a.snap_pct_l3, a.first_read_share_std, a.first_read_share_l3,
                  a.ppg_std, a.points_per_game_l3, a.expected_per_game, a.diff_per_game,
                  a.opponent, a.is_bye, a.opp_rank_std, t.tags, t.momentum, pr.proj_points as proj_v2
           from analytics.mart_player_availability a
           left join analytics.mart_player_trend_tags t on t.gsis_id = a.gsis_id and t.season = a.season
           left join analytics.mart_player_week_projections pr
                  on pr.league_id = a.league_id and pr.gsis_id = a.gsis_id and pr.season = %s and pr.week = %s
           where a.league_id = %s and a.is_free_agent and a.position = any(%s) and coalesce(a.games_played, 0) >= %s""",
        (season, week_for_proj, league_id, positions, int(min_games)),
    )
    fa = align_opponents(fa, season, week_for_proj)    # the opponent of the projected week
    if hide_injured:
        fa = fa[~fa["injury_status"].isin(["Out", "IR"]) & (fa["roster_status"] != "RES")]
    fa = fa.sort_values(sort_by, ascending=(sort_by == "diff_per_game"), na_position="last")
    st.caption(f"{len(fa)} free agents. **Proj** is the projection for week {week_for_proj} in this league's scoring, the same number "
               "the claims above use. Waiver decisions are also about opportunity: target, carry and snap shares persist; touchdowns don't.")
    rec_cols = ["player_name", "position", "nfl_team", "injury_status", "depth_rank", "games_played", "proj_v2", "tags", "momentum", "targets_per_game", "target_share",
                "target_share_l3", "first_read_share_std", "first_read_share_l3", "avg_offense_snap_pct", "snap_pct_l3", "ppg_std", "points_per_game_l3",
                "expected_per_game", "diff_per_game", "opponent", "is_bye", "opp_rank_std"]
    rb_cols = ["player_name", "position", "nfl_team", "injury_status", "depth_rank", "games_played", "proj_v2", "tags", "momentum", "carries_per_game", "carry_share",
               "carry_share_l3", "targets_per_game", "target_share", "first_read_share_l3", "avg_offense_snap_pct", "snap_pct_l3", "ppg_std", "points_per_game_l3",
               "expected_per_game", "diff_per_game", "opponent", "is_bye", "opp_rank_std"]
    qbk_cols = ["player_name", "position", "nfl_team", "injury_status", "depth_rank", "games_played", "proj_v2", "tags", "momentum", "ppg_std", "points_per_game_l3",
                "expected_per_game", "diff_per_game", "opponent", "is_bye", "opp_rank_std"]
    if set(positions) <= {"RB"}:
        cols = rb_cols
    elif set(positions) <= {"QB", "K"}:
        cols = qbk_cols
    else:
        cols = rec_cols
    if fa["injury_status"].isin(["Healthy"]).all() or fa["injury_status"].isna().all():
        cols = [c for c in cols if c != "injury_status"]            # injury is a filter, not a column, unless someone is hurt
    if sort_by not in cols:          # the column the list is ranked by is always shown
        cols = cols[:7] + [sort_by] + cols[7:]
    if not fa.empty and fa[sort_by].isna().all():
        st.info(f"**{sort_labels[sort_by]}** has no values yet for these players (it needs more games this season), so the list is not ranked by it.")
    phone = ["player_name", "position", "proj_v2", sort_by if sort_by != "proj_v2" else "expected_per_game", "opp_rank_std"]
    show(fa, cols, height=480, phone_cols=phone)
    howto(
        "**Target % / Snap %**: the player's share of his team's targets and offensive snaps. A receiver at 20%+ targets on 80%+ snaps has a real role whatever his points say.",
        "**xPPG** prices that opportunity in this league's scoring. **PPG − xPPG** well below zero = he has been unlucky: the cheap add nobody else sees.",
        "**Trend / Momentum** (from the Trends page) name the usage metrics that moved over the last three games beyond the player's own noise. Blank until game four.",
        "**1st-read share** is the player's share of his team's first-read targets (where the QB looks first, from FTN charting).",
        "**Opp rank** is next week's matchup for his position (1 = the defense that gives up the most). **Depth** is his rank on the team's latest depth chart.",
    )

# ------------------------------------------------------------- recent league moves
with st.expander("Recent league moves"):
    tx = query(
        """select t.created_at, t.week, t.transaction_type, t.action, t.team_name, t.player_name, t.position, t.waiver_bid, m.gsis_id
           from analytics.mart_league_transactions t
           left join analytics.player_id_map m on m.sleeper_id = t.sleeper_player_id
           where t.league_id = %s and t.status = 'complete'
           order by t.created_at desc limit 40""",
        (league_id,),
    )
    st.caption("Completed waiver claims, free-agent adds, drops and trades, newest first: who is chasing the same positions and what bids clear.")
    show(tx, [c for c in tx.columns if c != "gsis_id"], phone_cols=["player_name", "action", "team_name", "week", "waiver_bid"])
