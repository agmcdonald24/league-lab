"""Matchups: this week's lineup decisions (B4), then — each as a one-line answer with its table in an expander —
the start/sit board, two players side by side (R-11), the cornerbacks your receivers face (R-14) and defense vs
position as a chart (R-15) (plan U-13: nothing wider than five columns outside an expander)."""

import pandas as pd
import streamlit as st
from lib.cards import (
    decision_cards,
    decision_week,
    decisions,
    howto_cards,
    lineup_rows,
    lineup_table,
)
from lib.charts import dvp_bars, dvp_heatmap
from lib.db import missing_relations, query
from lib.matchups import (
    cb_line,
    comparison_rows,
    comparison_verdict,
    cover_split,
    dvp_heat_frame,
    dvp_selection,
    lean_text,
)
from lib.table import Col, detail_level, howto, show
from lib.ui import (
    align_opponents,
    current_leagues,
    current_season,
    current_week,
    freshness_banner,
    league_slots,
    perspective,
    reference_scoring_note,
    setup,
    week_first_kickoff,
)

setup("Matchups")
freshness_banner()
league_id, roster_id, members = perspective(require_team=False)
# one week rule (C1): the week every page means by "this week" (lib.ui.current_week), not mart_nfl_calendar
season = current_season(league_id)
next_week = current_week(league_id)
if season is None or next_week is None:
    st.info("The regular season is over: no matchups left to play.")
    st.stop()
first_kick = week_first_kickoff(season, next_week)
kick = first_kick.tz_convert("America/New_York") if first_kick is not None else None
st.caption(f"NFL {season} · week {next_week}" + (f" · first kickoff {kick:%a %b %-d, %-I:%M %p} ET" if kick is not None else ""))

# ------------------------------------------------------------- lineup decisions, then the start/sit board (plan B4)
if roster_id is not None:
    # the same cards as Home's My Week (lib/cards.py): the closest calls of the best lineup (B1), for the
    # first week with a game still to kick off
    lu_season = int(current_leagues().set_index("league_id").loc[league_id, "season"])
    lu_week = decision_week(lu_season)
    if lu_week is not None:
        st.subheader(f"Your lineup decisions — week {lu_week}")
        lu_rows = lineup_rows(league_id, lu_season, lu_week, roster_id)
        decision_cards(league_id, roster_id, lu_week, lu_season, rows=lu_rows)
        with st.expander("Your best lineup this week"):
            lineup_table(lu_rows, full=True)
        howto_cards()

    board = query(
        """select gsis_id, player_name, position, nfl_team, is_current_starter, injury_status, practice_status, is_bye,
                  opponent, is_home, opp_rank_std, opp_rank_l4, opp_points_allowed_pg_std,
                  ppg_std, points_per_game_l3, expected_per_game, target_share_l3, snap_pct_l3, depth_rank
           from analytics.mart_player_availability
           where league_id = %s and rostered_by_roster_id = %s
           order by array_position(array['QB','RB','WR','TE','K'], position), coalesce(expected_per_game, ppg_std) desc nulls last""",
        (league_id, roster_id),
    )
    board = align_opponents(board, season, next_week)      # this week's opponents (the mart keys them to the calendar week)
    with st.expander("Start / sit board: every player with his matchup"):
        st.markdown(
            "- Every player on your roster with next week's opponent. **Opp rank** 1 = the defense that gives up the most to his "
            "position (the matchup you want), 32 = the fewest; **(L4)** uses only its last 4 games.\n"
            "- Weigh the matchup against his work: **xPPG** (expected points per game) is what his targets and carries are usually "
            "worth. A great matchup for a player nobody throws to is still a bad start.\n"
            "- **Injury** and **Practice** are the latest official report: Questionable with a full practice is usually fine, "
            "Questionable with no practice is a real risk.\n"
            "- **BYE** means no game: he scores zero if you start him."
        )
        show(board, ["player_name", "position", "nfl_team", "is_current_starter", "injury_status", "practice_status", "opponent", "is_home", "is_bye",
                     "opp_rank_std", "opp_rank_l4", "opp_points_allowed_pg_std", "ppg_std", "points_per_game_l3", "expected_per_game",
                     "target_share_l3", "snap_pct_l3", "depth_rank"], height=520,
             phone_cols=["player_name", "position", "opponent", "opp_rank_std", "expected_per_game"])
else:
    board = pd.DataFrame()

# ===================================================================== C5 (Wave C round 2): R-11, R-14, R-15
# the roster's players this week: the proposed lineup (B1) when there is one, else Sleeper's current lineup
my_rows = lu_rows if roster_id is not None and lu_week is not None else pd.DataFrame()
if not my_rows.empty:
    my_players = my_rows[my_rows["gsis_id"].notna()][["gsis_id", "player_name", "position", "role", "slot"]].copy()
    my_players["is_starter"] = my_players["role"] == "starter"
elif not board.empty:
    my_players = board[board["gsis_id"].notna()][["gsis_id", "player_name", "position", "is_current_starter"]].rename(
        columns={"is_current_starter": "is_starter"}).assign(role=None, slot=None)
    my_players["is_starter"] = my_players["is_starter"].fillna(False).astype(bool)
else:
    my_players = pd.DataFrame(columns=["gsis_id", "player_name", "position", "role", "slot", "is_starter"])
phone = detail_level() == "phone"

# the new marts reach the hosted copy with the nightly after this code: until then those sections say so and
# the rest of the page renders (query() would stop the page on a missing table)
c5_missing = set(missing_relations(("mart_defense_position_profile", "mart_cb_matchups", "mart_cb_rankings",
                                    "mart_receiver_vs_cb")))
REFRESH_NOTE = "This section arrives with the next data refresh."

# ------------------------------------------------------------- R-11: two players side by side
st.subheader("Two players side by side")
proj = pd.DataFrame() if "mart_defense_position_profile" in c5_missing else query(
    """select pr.gsis_id, pr.player_name, pr.position, pr.team, pr.opponent, pr.is_home, pr.proj_points, pr.p10, pr.p90,
              pr.report_status, f.games, f.points_allowed_pg, f.rank_points, f.opps_allowed_pg, f.rank_opportunity,
              f.targets_allowed_pg, f.rank_targets, f.carries_allowed_pg, f.rank_carries,
              f.yards_per_opp_allowed, f.rank_efficiency, f.td_rate_allowed, f.rank_td_rate, f.adjusted_points_pg,
              f.rank_adjusted, f.gives_up, f.n_defenses
       from analytics.mart_player_week_projections pr
       left join analytics.mart_defense_position_profile f
              on f.season = pr.season and f.week = pr.week and f.defense = pr.opponent and f.position = pr.position
       where pr.league_id = %s and pr.season = %s and pr.week = %s and pr.position in ('QB', 'RB', 'WR', 'TE')
       order by pr.proj_points desc nulls last""",
    (league_id, int(season), int(next_week)),
)
if "mart_defense_position_profile" in c5_missing:
    st.caption(REFRESH_NOTE)
elif proj.empty:
    st.info(f"No projections for week {next_week} yet (the nightly refresh writes them), so nothing to compare.")
else:
    proj["label"] = proj["player_name"] + " · " + proj["position"] + " · " + proj["team"].fillna("")
    mine_ids = [g for g in my_players["gsis_id"] if g in set(proj["gsis_id"])]
    anyone = st.toggle("Pick from every player, not just your roster", value=not mine_ids, key=f"cmp_any_{league_id}_{roster_id}",
                       disabled=not mine_ids)
    pool = proj if anyone or not mine_ids else proj[proj["gsis_id"].isin(mine_ids)]
    labels = pool["label"].tolist()
    by_id = pool.set_index("gsis_id")["label"]
    # default: this week's closest lineup call with two comparable players (the first decision card, unless it
    # is a kicker or a defense): the starter and who would replace him, with the lineup's margin
    default_a, default_b = (labels[0] if labels else None), (labels[1] if len(labels) > 1 else None)
    decision = None
    if not my_rows.empty:
        for d in decisions(my_rows, 3).to_dict("records"):
            if d.get("gsis_id") in by_id.index and d.get("alt_gsis_id") in by_id.index:
                decision = d
                default_a, default_b = by_id[d["gsis_id"]], by_id[d["alt_gsis_id"]]
                break
    if len(labels) < 2:
        st.caption("Fewer than two players with a projection this week.")
    else:
        pick_a = st.selectbox("Player", labels, index=labels.index(default_a), key=f"cmp_a_{league_id}_{roster_id}_{anyone}")
        rest = [x for x in labels if x != pick_a]
        pick_b = st.selectbox("Against", rest, index=rest.index(default_b) if default_b in rest else 0,
                              key=f"cmp_b_{league_id}_{roster_id}_{anyone}")
        a = pool[pool["label"] == pick_a].iloc[0].to_dict()
        b = pool[pool["label"] == pick_b].iloc[0].to_dict()
        with st.container(border=True):
            st.markdown(f"**{comparison_verdict(a, b, decision)}**")
            # a static table: its cells wrap at phone width (a grid would scroll sideways)
            st.table(comparison_rows(a, b).set_index("What").rename_axis(None))
            st.caption(f"Week {next_week}. The projection decides: it already counts the opponent, and the lineup above is "
                       "built on it. The defense rows are context: what each opponent allowed to the position in its games "
                       "before this week, one scale for every league; (#1) = gives up the most of 32.")
        howto(
            "**Use it for a close call**: the two players open on your closest lineup decision; pick any two.",
            "**Projection** is the same number as your lineup cards and the Rankings board; the lineup's margin (\"by 0.15\") "
            "is what your lineup loses if you swap them. **Floor – ceiling** is the range 8 weeks in 10 land in: take the "
            "higher floor when you only need a steady game, the higher ceiling when you need a big one.",
            "**Targets / carries allowed** say whether a defense lets the position get the ball a lot (volume). **Yards per "
            "target or carry** and **touchdown rate** say whether it gives up big plays. A volume defense suits a player who "
            "lives on catches; a big-play defense suits one who needs one long gain.",
            "**Vs the offenses faced**: points it allowed beyond what the same offenses score against everyone else, shrunk "
            "toward zero early in the season. A soft rank earned against strong offenses is not soft. \"The matchup leans\" "
            "uses this rank: 6 or more places apart, else the matchups are about even.",
            "Matchups move a projection less than role does: when the lineup and the matchup disagree, go with the lineup.",
            title="How to read this",
        )

# ------------------------------------------------------------- R-14: cornerbacks
if roster_id is not None and c5_missing & {"mart_cb_matchups", "mart_cb_rankings", "mart_receiver_vs_cb"}:
    st.subheader("Cornerbacks your receivers face")
    st.caption(REFRESH_NOTE)
elif roster_id is not None:
    st.subheader("Cornerbacks your receivers face")
    rec = my_players[my_players["position"].isin(["WR", "TE"])]
    cbm = query(
        """select * from analytics.mart_cb_matchups where season = %s and week = %s and gsis_id = any(%s)""",
        (int(season), int(next_week), list(rec["gsis_id"])),
    ) if not rec.empty else pd.DataFrame()
    if not cbm.empty:
        order = {g: i for i, g in enumerate(rec.sort_values("is_starter", ascending=False)["gsis_id"])}
        cbm = cbm.assign(_o=cbm["gsis_id"].map(order), is_starter=cbm["gsis_id"].isin(rec.loc[rec["is_starter"], "gsis_id"]))
        cbm = cbm.sort_values(["_o"])
    starters_cb = cbm[cbm["is_starter"]] if not cbm.empty else cbm
    with st.container(border=True):
        if starters_cb.empty:
            st.markdown("None of your starting receivers has a game this week." if not rec.empty
                        else "No receivers on your roster.")
        else:
            st.markdown("\n".join(f"- {cb_line(r)}" for _, r in starters_cb.iterrows()))
            n_cb = starters_cb["cb_n_ranked"].dropna()
            st.caption("Likely across from him = the outside corner on the side more of his targets go: a lean, not an "
                       "assignment (nobody publishes who covers whom). "
                       + (f"#1 of {int(n_cb.iloc[0])} = the starting corner hardest to throw on since the start of "
                          f"{int(season) - 1}; shutdown = the top quarter, target = the bottom quarter." if not n_cb.empty else ""))
    with st.expander("Cornerbacks, receiver by receiver"):
        if cbm.empty:
            st.caption("Nothing to show yet.")
        else:
            names = cbm["player_name"].tolist()
            pick = st.selectbox("Receiver", names, key=f"cb_pick_{league_id}_{roster_id}")
            r = cbm[cbm["player_name"] == pick].iloc[0]
            st.markdown(cb_line(r))
            if r["call_status"] not in ("tight end",):
                st.caption(lean_text(r))
            ids = [x for x in (r["lcb_gsis_id"], r["rcb_gsis_id"], r["nb_gsis_id"]) if isinstance(x, str) and x]
            if ids:
                corners = query(
                    """select gsis_id, window_label, defender_name, quality_rank, quality_label, n_ranked, targets_per_coverage_snap,
                              adj_yards_per_target, yards_per_target_allowed, passer_rating_allowed, round(coverage_snaps)::int as coverage_snaps, targets, is_ranked
                       from analytics.mart_cb_rankings where season = %s and gsis_id = any(%s)""",
                    (int(season), ids),
                )
                two = corners[corners["window_label"] == "two_seasons"].drop(columns="window_label")
                for w, col in (("season", "rank_this_season"), ("last_4", "rank_last_4")):
                    two = two.merge(corners.loc[corners["window_label"] == w, ["gsis_id", "quality_rank"]]
                                    .rename(columns={"quality_rank": col}), on="gsis_id", how="left")
                slots = pd.DataFrame({"gsis_id": [r["lcb_gsis_id"], r["rcb_gsis_id"], r["nb_gsis_id"]],
                                      "depth_position": ["Left", "Right", "Slot"],
                                      "listed_name": [r["lcb_name"], r["rcb_name"], r["nb_name"]]}).dropna(subset=["gsis_id"])
                corners = slots.merge(two, on="gsis_id", how="left")
                corners["defender_name"] = corners["defender_name"].fillna(corners["listed_name"])
                st.markdown(f"**{r['opponent']}'s starting corners** (rank of {int(r['cb_n_ranked'] or 0)} corners since the "
                            f"start of {int(season) - 1}, 1 = hardest to throw on)")
                show(corners, overrides={"depth_position": Col("Side", help="Where the depth chart lists him: left or right outside, or the slot (nickel)")},
                     cols=["defender_name", "depth_position", "quality_rank", "quality_label", "targets_per_coverage_snap",
                           "adj_yards_per_target", "passer_rating_allowed", "rank_this_season", "rank_last_4",
                           "yards_per_target_allowed", "coverage_snaps", "targets"],
                     phone_cols=["defender_name", "depth_position", "quality_rank", "quality_label", "passer_rating_allowed"])
            faced = query(
                """select defender_name, defense, games, targets, receptions, receiving_yards, receiving_tds, defender_snap_share,
                          share_of_targets, evidence
                   from analytics.mart_receiver_vs_cb where receiver_gsis_id = %s and season = %s
                   order by defense, defender_snap_share desc nulls last, targets desc""",
                (r["gsis_id"], int(season)),
            )
            st.markdown(f"**Corners he has faced in {int(season)}**")
            if faced.empty:
                st.caption("No games yet this season.")
            else:
                st.caption("His totals in each game that corner played (share of his defense's snaps). Who was on the field "
                           "play by play is published after the season.")
                show(faced, ["defender_name", "defense", "targets", "receptions", "receiving_yards", "receiving_tds",
                             "defender_snap_share", "games"],
                     phone_cols=["defender_name", "defense", "targets", "receptions", "receiving_yards"])
            last = query(
                """select defender_name, defense, games, targets, receptions, receiving_yards, receiving_tds, share_of_targets
                   from analytics.mart_receiver_vs_cb where receiver_gsis_id = %s and season = %s and evidence = 'on_field'
                   order by defense, share_of_targets desc""",
                (r["gsis_id"], int(season) - 1),
            )
            if not last.empty:
                st.markdown(f"**Corners on the field for his targets in {int(season) - 1}**")
                st.caption("On the field for that share of his targets against that defense: not necessarily covering him.")
                show(last, ["defender_name", "defense", "share_of_targets", "targets", "receptions", "receiving_yards",
                            "receiving_tds", "games"],
                     phone_cols=["defender_name", "defense", "share_of_targets", "targets", "receiving_yards"])
            if isinstance(r["likely_cover_gsis_id"], str):
                hist = query(
                    """select season, defense, games, targets, receptions, receiving_yards, receiving_tds, evidence, defender_snap_share
                       from analytics.mart_receiver_vs_cb where receiver_gsis_id = %s and defender_gsis_id = %s order by season desc""",
                    (r["gsis_id"], r["likely_cover_gsis_id"]),
                )
                st.markdown(f"**Against {r['likely_cover_name']} before**")
                if hist.empty:
                    st.caption("Never on the field together since 2022.")
                else:
                    st.caption("Past seasons: plays with him on the field (not necessarily covering). This season: games he played.")
                    show(hist, ["season", "defense", "targets", "receptions", "receiving_yards", "receiving_tds", "games"],
                         phone_cols=["season", "defense", "targets", "receptions", "receiving_yards"])
    with st.expander("His points against the best corners"):
        wr_ids = list(rec.loc[rec["position"] == "WR", "gsis_id"])
        split_games = query(
            """select m.gsis_id, m.player_name, m.season, m.week, m.opponent, m.likely_cover_name, m.cover_rank, m.cover_label,
                      l.points
               from analytics.mart_cb_matchups m
               join analytics.fct_player_game_league l
                 on l.league_id = %s and l.gsis_id = m.gsis_id and l.game_id = m.game_id and l.played
               where m.gsis_id = any(%s) and m.call_status = 'called' and m.season >= %s and (m.season < %s or m.week < %s)
               order by m.gsis_id, m.season, m.week""",
            (league_id, wr_ids, int(season) - 1, int(season), int(next_week)),
        ) if wr_ids else pd.DataFrame()
        split = cover_split(split_games)
        if split.empty:
            st.caption("No games with a named corner since last season.")
        else:
            st.markdown("His points per game (this league's scoring) since the start of last season, in games where the "
                        "corner we named across from him was a **shutdown** corner (top quarter) vs every other game. "
                        "Evidence, not a projection change: the samples are small.")
            show(split, ["player_name", "ppg_vs_shutdown", "games_vs_shutdown", "ppg_vs_rest", "games_vs_rest"])
            with st.popover("Every game behind it"):
                show(split_games, ["player_name", "season", "week", "opponent", "likely_cover_name", "cover_rank", "cover_label", "points"],
                     phone_cols=["player_name", "week", "likely_cover_name", "cover_label", "points"])
    with st.expander("Every starting corner, ranked"):
        wins = {"Since last season": "two_seasons", "This season": "season", "Last 4 games": "last_4"}
        wl = st.radio("Window", list(wins), horizontal=True, key=f"cb_win_{league_id}")
        ranks = query(
            """select quality_rank, defender_name, latest_team, quality_label, targets_per_coverage_snap, adj_yards_per_target,
                      yards_per_target_allowed, passer_rating_allowed, round(coverage_snaps)::int as coverage_snaps, targets, games, n_ranked
               from analytics.mart_cb_rankings where season = %s and window_label = %s and is_ranked order by quality_rank""",
            (int(season), wins[wl]),
        )
        if ranks.empty:
            st.caption("No corner has enough pass plays in this window yet.")
        else:
            st.caption(f"{len(ranks)} corners with at least 20 pass plays in coverage per team game in the window "
                       "(80 over the last 4 games).")
            show(ranks, ["quality_rank", "defender_name", "latest_team", "quality_label", "targets_per_coverage_snap",
                         "adj_yards_per_target", "passer_rating_allowed", "yards_per_target_allowed", "coverage_snaps", "targets", "games"],
                 phone_cols=["quality_rank", "defender_name", "latest_team", "quality_label", "passer_rating_allowed"], height=420)
    howto(
        "**Start the receiver whose likely corner ranks lower** when two options are close; don't bench a star for a "
        "tough corner: his targets matter more, and the projection already counts the defense.",
        "**Likely across from him** is a guess from where his targets go (to the offense's left or right): the outside "
        "corner on that side (throws to the offense's left meet the defense's right corner). Public data has no receiver "
        "alignment and no coverage assignments. Checked on last season: when a receiver's targets leaned clearly to one "
        "side (15 points or more), the corner we named was charged with about 1 in 5 of his targets and the other outside "
        "corner about 1 in 7, no more than any other throw; with a closer split it was about 1 in 5 against 1 in 6 — "
        "either could be across from him, so the card names both.",
        "**What public data can't tell you**: who covered whom on a play, whether a corner follows the top receiver around "
        "(our best test for that caught 1 of 6 well-known shadow corners last season, so we don't flag it), or who "
        "lines up in the slot.",
        "**CB rank** = among starting corners since the start of last season (at least 20 pass plays in coverage a team "
        "game), on three numbers weighed equally: how often he is thrown at per pass play, yards per throw at him "
        "adjusted for the offenses he faced, and the quarterback rating on those throws. Shutdown = the top quarter, "
        "target = the bottom quarter, solid = the middle half.",
        "Tight ends mostly draw linebackers and safeties, so they get no cornerback call. Coverage numbers come from "
        "Pro-Football-Reference's charting (2018 on), a few days after each game.",
        title="How to read this",
    )

# ------------------------------------------------------------- R-15: defense vs position, the answer line then the picture
st.subheader("Defense vs position")
dvp = query(
    """select defense, position, games, points_allowed_per_game_std, rank_std, points_allowed_per_game_l4, rank_l4
       from analytics.mart_defense_vs_position_current order by position, rank_std""",
)
dvp_positions = [p for p in league_slots(league_id) if p in ("QB", "RB", "WR", "TE", "K")]
with st.container(border=True):
    lineup = board[board["is_current_starter"].fillna(False).astype(bool) & board["opp_rank_std"].notna()] if not board.empty else pd.DataFrame()
    if not lineup.empty:
        lu = lineup.assign(_r=pd.to_numeric(lineup["opp_rank_std"], errors="coerce")).sort_values("_r")
        b, w = lu.iloc[0], lu.iloc[-1]
        st.markdown(f"**Best matchup in your lineup: {b['player_name']} ({b['position']}) vs {b['opponent']}, #{int(b['_r'])} vs {b['position']}; "
                    f"toughest: {w['player_name']} ({w['position']}) vs {w['opponent']}, #{int(w['_r'])} vs {w['position']}.**")
    else:
        top = dvp[dvp["rank_std"] == 1].drop_duplicates("position").set_index("position")
        parts = [f"{p}s: {top.loc[p, 'defense']} ({float(top.loc[p, 'points_allowed_per_game_std']):.1f}/game)" for p in dvp_positions if p in top.index]
        st.markdown("**Gives up the most so far — " + " · ".join(parts) + ".**")
    st.caption("Rank 1 = the defense that gives up the most points to the position this season (the matchup you want), 32 = the fewest.")

if dvp.empty or not dvp_positions:
    st.caption("No defense has played a game yet this season.")
else:
    # your starters' opponents, by position (the marks on both pictures)
    starters_pos = my_players[my_players["is_starter"]] if not my_players.empty else my_players
    opp_of = board.set_index("gsis_id")["opponent"].to_dict() if not board.empty else {}
    marks: dict[str, dict[str, str]] = {}
    for _, p in starters_pos[starters_pos["position"].isin(dvp_positions)].iterrows():
        o = opp_of.get(p["gsis_id"])
        if isinstance(o, str) and o:
            cell = marks.setdefault(o, {})
            cell[p["position"]] = (cell[p["position"]] + ", " if p["position"] in cell else "") + str(p["player_name"])
    views = ["Every position", "One position"]
    view = st.segmented_control("Show", views, default=views[0], key=f"dvp_view_{league_id}") or views[0]
    c_l4, c_mine = st.columns(2)
    last4 = c_l4.toggle("Last 4 games only", value=False, key=f"dvp_l4_{league_id}")
    only_mine = c_mine.toggle("Only your opponents", value=phone and bool(marks), disabled=not marks,
                              key=f"dvp_mine_{league_id}_{roster_id}")
    value, rank_col = ("points_allowed_per_game_l4", "rank_l4") if last4 else ("points_allowed_per_game_std", "rank_std")
    window = "last 4 games" if last4 else "this season"
    n_def = int(dvp.groupby("position")["defense"].nunique().max())
    if view == "Every position":
        frame = dvp_heat_frame(dvp, dvp_positions, value, rank_col, marks, only_marked=only_mine)
        fig = dvp_heatmap(frame, dvp_positions, f"Points allowed per game, {window}", n_total=n_def)
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False, "scrollZoom": False})
        st.caption((("◀ and a ringed cell = where your starters play this week: "
                     + "; ".join(f"{t} ({', '.join(f'{who} at {p}' for p, who in cells.items())})" for t, cells in marks.items()) + ". ")
                    if marks else "No starter of yours has a game at these positions this week. ")
                   + "Darker = gives up more to that position (its rank of " + str(n_def) + "); the number is points per game. "
                   + ("Your opponents only; switch it off for every defense." if only_mine else "Your opponents first, then the defenses that give up the most across positions."))
    else:
        default_pos = next((p for p in ("WR", "RB", "QB", "TE", "K") if p in dvp_positions), dvp_positions[0])
        pos = st.segmented_control("Position", dvp_positions, default=default_pos, key=f"dvp_pos_{league_id}") or default_pos
        sub = dvp[dvp["position"] == pos].copy()
        mine = {t: cells[pos] for t, cells in marks.items() if pos in cells}
        if only_mine:
            sub = sub[sub["defense"].isin(list(mine))]
        sel = dvp_selection(sub, value, mine, n=len(sub))   # every defense, ranked (the phone filter keeps yours)
        avg = float(pd.to_numeric(dvp.loc[dvp["position"] == pos, value], errors="coerce").mean())
        if sel.empty:
            st.caption(f"None of your starters plays {pos} this week: switch off \"Only your opponents\".")
        else:
            fig = dvp_bars(sel, value, f"Points allowed to {pos}s per game, {window}", "fantasy points per game",
                           league_avg=avg, rank_col=rank_col, n_total=n_def)
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False, "scrollZoom": False})
            marked = ", ".join(f"{t} ({who})" for t, who in mine.items())
            st.caption((f"◀ = your starters' opponents this week: {marked}. " if mine else f"No starter of yours plays {pos} this week. ")
                       + "Most allowed at the top; the line is the league average.")

with st.expander("Defense vs position: every defense, by position (the table behind the pictures)"):
    howto(
        "**Start players against the defenses at the top** of the \"gives up the most\" list; be wary of the bottom one.",
        "**Pts allowed/G** is the fantasy points each defense gives up to that position per game this season, on one scale for every "
        "league. **Rank** 1 = gives up the most (the matchup you want), 32 = the stingiest.",
        "The **(L4)** columns use only the defense's last 4 games: they catch an injury or a new scheme sooner.",
        "Early in the season these ranks jump around; from about week 6 they settle.",
    )
    reference_scoring_note("Points allowed and ranks in this section")
    if not dvp.empty and dvp_positions:
        pos_t = st.radio("Position", dvp_positions, horizontal=True, key=f"dvp_tbl_{league_id}")
        sub_t = dvp[dvp["position"] == pos_t].sort_values("rank_std")
        show(sub_t, ["defense", "games", "points_allowed_per_game_std", "rank_std", "points_allowed_per_game_l4", "rank_l4"],
             phone_cols=["defense", "points_allowed_per_game_std", "rank_std", "points_allowed_per_game_l4", "rank_l4"], height=420)

# ------------------------------------------------------------- any player lookup
with st.expander("Look up any player's next matchup"):
    name = st.text_input("Player name contains", "")
    if name:
        res = query(
            """select gsis_id, player_name, position, team, roster_status, opponent, is_home, is_bye, kickoff_at,
                      opp_rank_std, opp_rank_l4, opp_points_allowed_pg_std, injury_status, injury, practice_status, depth_rank
               from analytics.mart_player_next_matchup where player_name ilike %s order by player_name limit 30""",
            (f"%{name}%",),
        )
        res = align_opponents(res, season, next_week, team_col="team")
        show(res, [c for c in res.columns if c != "gsis_id"],
             phone_cols=["player_name", "position", "opponent", "opp_rank_std", "kickoff_at"])
