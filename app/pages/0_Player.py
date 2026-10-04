"""Player card (plan B4): usage, projection, availability and value for one player, in this league's scoring.

Reached as /Player?id=<gsis_id> (every player name in every table links here, carrying the league and
team) or through the search box. Card queries (the page chrome — banner, perspective — aside), counted in
docs/STATUS.md: decision week (dim_game), profile (one join: availability, season shares, trend tags,
league PPG this and last season), projection (next week), schedule (his games + opponent ranks), and for a
rostered player his roster's lineup (lib.cards.lineup_rows) — five at most.
"""

import pandas as pd
import streamlit as st
from lib import ros as ROS
from lib.cards import (
    TOL,
    alternative,
    bench_gap,
    decision_week,
    lineup_rows,
    slot_label,
    verdict,
    win_probability,
)
from lib.db import missing_relations, query, require_relations
from lib.signals import alert_headline, alert_lines, scenario_phrase
from lib.ui import current_leagues, freshness_banner, pct, perspective, player_link, setup

from league_lab import clock as league_clock  # ---- INF-1
from league_lab import decisions as D

setup("Player")
freshness_banner()
require_relations("mart_player_availability", "mart_player_week_projections", "mart_league_player_season", "dim_game")
league_id, viewer_roster, members = perspective(require_team=False)
leagues = current_leagues()
lrow = leagues.set_index("league_id").loc[league_id]
season, league_name = int(lrow["season"]), str(lrow["league_name"])
ET = "America/New_York"


def unavailable(why: str) -> None:
    st.caption(f"unavailable: {why}")


def is_num(v) -> bool:
    return v is not None and not (isinstance(v, float) and pd.isna(v)) and pd.notna(v)


def yes(v) -> bool:
    """True only for a real true (a left join's missing boolean is None or NaN, and bool(NaN) is True)."""
    return v is True or (not isinstance(v, float) and v is not None and pd.notna(v) and bool(v))


# ------------------------------------------------------------------ search
qp = st.query_params
gsis = qp.get("id")
name_hint = qp.get("name") if not gsis else None
typed = st.text_input("Find a player", value=name_hint or "", placeholder="Find another player" if gsis else "Type a name, e.g. St. Brown",
                      help="Any QB, RB, WR, TE or K in this season's player pool.")
if typed and len(typed.strip()) >= 2:
    hits = query(
        """select gsis_id, player_name, position, nfl_team, rostered_by_team, is_free_agent
           from analytics.mart_player_availability
           where league_id = %s
             and regexp_replace(lower(player_name), '[^a-z]', '', 'g') like '%%' || regexp_replace(lower(%s), '[^a-z]', '', 'g') || '%%'
           order by ppg_std desc nulls last, player_name limit 25""",
        (league_id, typed.strip()),
    )
    if hits.empty:
        st.caption(f"No QB, RB, WR, TE or K named like “{typed}” in this season's pool (team defenses have no card).")
    else:
        labels = {r.gsis_id: f"{r.player_name} · {r.position} · {r.nfl_team or 'no team'} · "
                             + ("free agent" if r.is_free_agent else f"{r.rostered_by_team}") for r in hits.itertuples()}
        pick = st.selectbox("Players", list(labels), format_func=labels.get, index=None,
                            placeholder=f"{len(labels)} match{'es' if len(labels) > 1 else ''} — pick one")
        if pick and pick != gsis:
            st.query_params["id"] = pick
            if "name" in st.query_params:
                del st.query_params["name"]
            st.rerun()
if not gsis:
    st.info("Pick a player above, or tap a player's name in any table.")
    st.stop()

# ------------------------------------------------------------------ the card's data (queries 1-5)
week = decision_week(season)                                                          # 1: dim_game
prof = query(                                                                         # 2: profile
    """select dp.gsis_id, coalesce(a.player_name, dp.player_name) as player_name, coalesce(a.position, dp.position) as position,
              coalesce(a.nfl_team, dp.latest_team) as team, a.gsis_id is not null as in_pool, a.roster_status,
              a.rostered_by_roster_id, a.rostered_by_team, a.rostered_by_manager, a.is_free_agent, a.is_current_starter, a.is_on_ir,
              a.injury_status, a.injury, a.practice_status, a.depth_rank, a.depth_pos,
              a.games_played, a.attempts, a.target_share, a.target_share_l3, a.carry_share, a.carry_share_l3,
              a.avg_offense_snap_pct, a.snap_pct_l3, a.first_read_share_std, a.first_read_share_l3,
              s.red_zone_target_share, s.red_zone_carry_share, s.fg_made, s.fg_att, s.fg_long, s.pat_made, s.pat_att,
              s.games_played as nfl_games, t.tags, t.opportunity_trend,
              v.ppg, v.expected_per_game, v.diff_per_game, v.position_rank_ppg, v.games_played as league_games,
              pv.ppg as prev_ppg, pv.position_rank_ppg as prev_rank, pv.games_played as prev_games
       from analytics.dim_player dp
       left join analytics.mart_player_availability a on a.gsis_id = dp.gsis_id and a.league_id = %s
       left join analytics.mart_player_season s on s.gsis_id = dp.gsis_id and s.season = %s and s.season_type = 'REG'
       left join analytics.mart_player_trend_tags t on t.gsis_id = dp.gsis_id and t.season = %s
       left join analytics.mart_league_player_season v on v.gsis_id = dp.gsis_id and v.league_id = %s and v.season = %s
       left join analytics.mart_league_player_season pv on pv.gsis_id = dp.gsis_id and pv.league_id = %s and pv.season = %s - 1
       where dp.gsis_id = %s""",
    (league_id, season, season, league_id, season, league_id, season, gsis),
)
if prof.empty:
    st.warning(f"No player with id `{gsis}`. Search for him above.")
    st.stop()
p = prof.iloc[0]
pos, team = p["position"], p["team"]
proj = query(                                                                         # 3: projection
    """select proj_points, p10, p25, p75, p90, proj_targets, proj_receptions, proj_receiving_yards, proj_receiving_tds,
              proj_carries, proj_rushing_yards, proj_rushing_tds, proj_attempts, proj_passing_yards, proj_passing_tds,
              proj_passing_interceptions, opponent, is_home
       from analytics.mart_player_week_projections
       where league_id = %s and gsis_id = %s and season = %s and week = %s""",
    (league_id, gsis, season, week if week is not None else -1),
)
sched = query(                                                                        # 4: schedule
    """select g.week, g.kickoff_at, g.home_team = %s as is_home,
              case when g.home_team = %s then g.away_team else g.home_team end as opponent, d.rank_std as opp_rank
       from analytics.dim_game g
       left join analytics.mart_defense_vs_position_current d
              on d.defense = case when g.home_team = %s then g.away_team else g.home_team end and d.position = %s
       where g.season = %s and g.season_type = 'REG' and %s in (g.home_team, g.away_team)
       order by g.week""",
    (team, team, team, pos, season, team),
) if isinstance(team, str) and team else pd.DataFrame()
rostered = is_num(p["rostered_by_roster_id"])
rows = lineup_rows(league_id, season, week, int(p["rostered_by_roster_id"])) if rostered and week else pd.DataFrame()   # 5

# ------------------------------------------------------------------ header
st.subheader(p["player_name"])
where = (f"on **{p['rostered_by_team']}** ({p['rostered_by_manager']})" if rostered
         else "**free agent** in this league" if yes(p["is_free_agent"]) else "not in this season's player pool")
depth = f" · {p['depth_pos']}{int(p['depth_rank'])} on the depth chart" if is_num(p["depth_rank"]) and isinstance(p["depth_pos"], str) else ""
st.markdown(f"{pos} · {team or 'no NFL team'}{depth} · {where}")
game = sched[sched["week"] == week] if week is not None and not sched.empty else pd.DataFrame()

# ------------------------------------------------------------------ 1. usage
with st.container(border=True):
    st.markdown("**Usage** — " + ("his kicks this season" if pos == "K" else "his share of the team's opportunities"))
    if pos == "K":
        if is_num(p["fg_att"]) and p["nfl_games"]:
            fg_long = f", long {int(p['fg_long'])}" if is_num(p["fg_long"]) else ""
            st.markdown(f"Field goals **{int(p['fg_made'])} of {int(p['fg_att'])}**{fg_long} · extra points "
                        f"**{int(p['pat_made'] or 0)} of {int(p['pat_att'] or 0)}** in {int(p['nfl_games'])} games this season.")
        else:
            unavailable("no kicks recorded this season.")
    elif not yes(p["in_pool"]) or not is_num(p["games_played"]) or int(p["games_played"]) == 0:
        unavailable("no games this season yet." if yes(p["in_pool"]) else "he is not in this season's player pool.")
    else:
        if pos == "QB":
            att = float(p["attempts"]) / int(p["games_played"]) if is_num(p["attempts"]) else None
            items = [("Passes / game", f"{att:.1f}" if att is not None else "—", None, None),
                     ("Carry share", pct(p["carry_share"]), p["carry_share"], p["carry_share_l3"]),
                     ("Snap share", pct(p["avg_offense_snap_pct"]), p["avg_offense_snap_pct"], p["snap_pct_l3"]),
                     ("Red-zone share", pct(p["red_zone_carry_share"]), None, None)]
        elif pos == "RB":
            items = [("Carry share", pct(p["carry_share"]), p["carry_share"], p["carry_share_l3"]),
                     ("Target share", pct(p["target_share"]), p["target_share"], p["target_share_l3"]),
                     ("Snap share", pct(p["avg_offense_snap_pct"]), p["avg_offense_snap_pct"], p["snap_pct_l3"]),
                     ("Red-zone share", pct(p["red_zone_carry_share"]), None, None)]
        else:
            items = [("Target share", pct(p["target_share"]), p["target_share"], p["target_share_l3"]),
                     ("First-read share", pct(p["first_read_share_std"]), p["first_read_share_std"], p["first_read_share_l3"]),
                     ("Snap share", pct(p["avg_offense_snap_pct"]), p["avg_offense_snap_pct"], p["snap_pct_l3"]),
                     ("Red-zone share", pct(p["red_zone_target_share"]), None, None)]
        with st.container(horizontal=True, wrap=True, gap="medium"):
            for label, val, season_v, l3 in items:
                kw = {}
                if is_num(l3) and is_num(season_v) and int(p["games_played"]) > 3:   # with 3 games or fewer L3 is the season
                    up = float(l3) - float(season_v)
                    kw = {"delta": f"{pct(l3)} last 3", "delta_arrow": "up" if up > 0.0005 else "down" if up < -0.0005 else "off",
                          "delta_color": "green" if up > 0.0005 else "red" if up < -0.0005 else "gray"}
                st.metric(label, val or "—", width="content", **kw)
        tags = p["tags"] if isinstance(p["tags"], str) and p["tags"] else None
        gp = int(p["games_played"])
        st.caption(f"Season to date, {gp} game{'s' if gp != 1 else ''}" + ("; the arrow is the last 3 games. " if gp > 3 else ". ")
                   + (f"Trend: {tags}." if tags else "Trend: none called.")
                   + (" Trends are called from a player's fourth game." if p["opportunity_trend"] == "insufficient" else ""))

# ------------------------------------------------------------------ 2. projection
with st.container(border=True):
    st.markdown(f"**Projection** — week {week}, {league_name} scoring" if week else "**Projection**")
    if week is None:
        unavailable("the regular season is over.")
    elif not proj.empty:
        r = proj.iloc[0]
        with st.container(horizontal=True, wrap=True, gap="medium"):
            st.metric("Projected", f"{float(r['proj_points']):.1f}", width="content")
            if is_num(r["p25"]) and is_num(r["p75"]):      # the 50% range (plan D6); NULL on weeks frozen before it existed
                st.metric("Most weeks", f"{float(r['p25']):.0f}–{float(r['p75']):.0f}", width="content",
                          help="Half his weeks land in this range: a quarter below it, a quarter above")
            st.metric("Floor", f"{float(r['p10']):.1f}", width="content", help="One week in ten he scores less")
            st.metric("Ceiling", f"{float(r['p90']):.1f}", width="content", help="One week in ten he scores more")
        parts = []
        if pos == "QB" and is_num(r["proj_attempts"]):
            parts.append(f"{float(r['proj_attempts']):.0f} passes for {float(r['proj_passing_yards']):.0f} yds, "
                         f"{float(r['proj_passing_tds']):.1f} TD, {float(r['proj_passing_interceptions']):.1f} INT")
        if is_num(r["proj_carries"]) and float(r["proj_carries"]) >= 0.5:
            parts.append(f"{float(r['proj_carries']):.1f} carries for {float(r['proj_rushing_yards']):.0f} yds, {float(r['proj_rushing_tds']):.2f} TD")
        if pos != "QB" and is_num(r["proj_targets"]) and float(r["proj_targets"]) >= 0.5:
            parts.append(f"{float(r['proj_targets']):.1f} targets, {float(r['proj_receptions']):.1f} catches for "
                         f"{float(r['proj_receiving_yards']):.0f} yds, {float(r['proj_receiving_tds']):.2f} TD")
        if parts:
            st.markdown("Stat line: " + " · ".join(parts))
    else:
        if pos == "K":
            why = "the model projects QB, RB, WR and TE; a kicker's lineup value is his points per game this season in this league (Value below)."
        elif not yes(p["in_pool"]):
            why = "he is not in this season's player pool."
        elif game.empty and not sched.empty:
            why = f"{team} is on bye in week {week}."
        else:
            status = {"RES": "he is on injured reserve", "DEV": "he is on the practice squad", "CUT": "he is not on an NFL roster",
                      "RET": "he has retired", "EXE": "he is on the exempt list", "INA": "he is inactive",
                      "SUS": "he is suspended"}.get(p["roster_status"], "the model has no projection for him this week")
            why = f"{status}."
        unavailable(why)
    # plan E2: rest of season, one line after the stat line (the same row Rankings and Trade Finder read). Its own
    # query, skipped on a copy published before the mart existed.
    if week is not None and not missing_relations((ROS.RELATION,)):
        ros = query(f"select {ROS.ROS_COLUMNS} from analytics.mart_player_ros_projection where league_id = %s and gsis_id = %s",
                    (league_id, gsis))
        if not ros.empty:
            rr = ros.iloc[0]
            st.markdown(ROS.card_line(rr))
            st.caption(f"Week by week ({ROS.weeks_span(rr['from_week'], rr['last_week'])}, through this league's final): "
                       f"{ROS.weeks_words(rr)}. {ROS.lines_note(rr)}")
        elif yes(p["in_pool"]):
            st.caption("Rest of season: no projection yet.")
    if not game.empty:
        g = game.iloc[0]
        rank = f" — {g['opponent']} ranks **#{int(g['opp_rank'])}** of 32 vs {pos} (1 = gives up the most)" if is_num(g["opp_rank"]) else ""
        st.markdown(f"Next: week {week} {'vs' if g['is_home'] else '@'} {g['opponent']}{rank}")
    if week is not None and not sched.empty:
        nxt = []
        for w in range(week, week + 4):
            gw = sched[sched["week"] == w]
            if gw.empty:
                nxt.append(f"wk {w} BYE" if w <= max(18, int(sched["week"].max())) else "")
            else:
                g = gw.iloc[0]
                rk = f" (#{int(g['opp_rank'])})" if is_num(g["opp_rank"]) else ""
                nxt.append(f"wk {w} {'vs' if g['is_home'] else '@'} {g['opponent']}{rk}")
        st.caption("Next 4: " + " · ".join(x for x in nxt if x))
    elif week is not None:
        unavailable("no schedule for his team.")

# ------------------------------------------------------------------ 3. availability
with st.container(border=True):
    st.markdown("**Availability**")
    lines = []
    if rostered:
        slot = "starting in his Sleeper lineup" if yes(p["is_current_starter"]) else ("on the IR slot" if yes(p["is_on_ir"]) else "on the bench in Sleeper")
        lines.append(f"Rostered by **{p['rostered_by_team']}** ({p['rostered_by_manager']}), {slot}.")
    elif yes(p["is_free_agent"]):
        lines.append("**Free agent** — nobody in this league has him.")
    else:
        lines.append("Not in this season's player pool for this league.")
    inj = p["injury_status"] if isinstance(p["injury_status"], str) and p["injury_status"] else None
    if inj:
        detail = f" ({p['injury']})" if isinstance(p["injury"], str) and p["injury"] else ""
        prac = f"; practice: {p['practice_status']}" if isinstance(p["practice_status"], str) and p["practice_status"] else ""
        lines.append(f"⚠️ **{inj}**{detail}{prac}.")
    elif yes(p["in_pool"]):
        lines.append("No injury designation.")
    if not sched.empty:
        weeks = set(sched["week"].astype(int))
        byes = [w for w in range(1, max(18, max(weeks)) + 1) if w not in weeks]
        if byes:
            b = byes[0]
            lines.append(f"Bye: week {b}" + (" (done)." if week is not None and b < week else "."))
    if week is not None and not game.empty:
        k = pd.Timestamp(game.iloc[0]["kickoff_at"])
        kick = k.tz_convert(ET)
        if k <= pd.Timestamp(league_clock.now()):  # ---- INF-1: the league's now (the API's player.py twin)
            lines.append(f"🔒 **Locked** for week {week}: his game kicked off {kick:%a %b %-d, %-I:%M %p} ET.")
        else:
            lines.append(f"Week {week} kickoff {kick:%a %b %-d, %-I:%M %p} ET — not locked yet.")
    elif week is not None and not sched.empty:
        lines.append(f"No game in week {week} (bye).")
    st.markdown("  \n".join(lines))

# ------------------------------------------------------------------ 4. value
with st.container(border=True):
    st.markdown(f"**Value** — {league_name} scoring")
    if is_num(p["ppg"]) and is_num(p["league_games"]) and int(p["league_games"]) > 0:
        with st.container(horizontal=True, wrap=True, gap="medium"):
            st.metric("Points / game", f"{float(p['ppg']):.1f}", width="content",
                      help=f"This season, {int(p['league_games'])} games, {league_name} scoring")
            if is_num(p["expected_per_game"]):
                d = float(p["diff_per_game"]) if is_num(p["diff_per_game"]) else float(p["ppg"]) - float(p["expected_per_game"])
                st.metric("Expected", f"{float(p['expected_per_game']):.1f}", delta=f"{d:+.1f}", width="content",
                          help="Expected points per game: what his targets and carries were worth on average (depth, field "
                               "position). The arrow is points per game above or below that: above = he beat his opportunity")
            if is_num(p["position_rank_ppg"]):
                st.metric("Rank", f"{pos}{int(p['position_rank_ppg'])}", width="content", help="By points per game among all players at the position")
            if is_num(p["prev_ppg"]) and is_num(p["prev_games"]) and int(p["prev_games"]) > 0:
                st.metric("Last season", f"{float(p['prev_ppg']):.1f}", width="content",
                          help=f"Points per game in {season - 1}, {int(p['prev_games'])} games, this league's scoring"
                               + (f"; {pos}{int(p['prev_rank'])}" if is_num(p["prev_rank"]) else ""))
    elif is_num(p["prev_ppg"]) and is_num(p["prev_games"]) and int(p["prev_games"]) > 0:
        st.markdown(f"No games this season yet. Last season: **{float(p['prev_ppg']):.1f}** points per game over {int(p['prev_games'])} games.")
    else:
        unavailable("no games this season or last in this league's scoring.")

    # where he sits in his roster's lineup this week (B1)
    if not rostered:
        st.caption("Free agent: the Waiver Wire page shows what he would add to your lineup." if yes(p["is_free_agent"]) else "")
    elif week is None:
        unavailable("no lineup: the regular season is over.")
    elif rows.empty:
        unavailable(f"no proposed lineup for week {week} yet (the nightly refresh writes it).")
    else:
        me = rows[rows["gsis_id"] == gsis]
        team_name = p["rostered_by_team"]
        if me.empty:
            unavailable(f"he is not in {team_name}'s week-{week} lineup data (roster changed since the last refresh?).")
        else:
            m = me.iloc[0]
            if m["role"] == "starter":
                where = slot_label(m["slot"])
                if yes(m["locked_now"]):
                    st.markdown(f"Week {week}: **locked in at {where}** for {team_name} (his game has started).")
                elif m["value_source"] == "unvalued":
                    st.markdown(f"Week {week}: **starts at {where}** for {team_name} with no value yet (counted as 0 until Sleeper scores him here).")
                else:
                    a = alternative(m, rows)
                    alt = a["alt"]
                    src = {"season_ppg": " (his points per game this season)", "observed_ppg": " (points per game Sleeper scored)"}.get(m["value_source"], "")
                    head = f"Week {week}: **starts at {where}** for {team_name}, {float(m['value']):.2f}{src}"
                    if alt is not None:
                        # the same words as the decision cards (plan D6): from the win probability when both have a
                        # range, else from the margin
                        pw = win_probability(m, alt)
                        call = verdict(float(m["margin"])) if pw is None else D.words(pw)
                        st.markdown(f"{head} — without him the lineup loses **{float(m['margin']):.2f}** "
                                    f"({player_link(alt['gsis_id'], alt['player_name'])}, {float(alt['value']):.2f}, would come in): "
                                    f"{call}.")
                    else:
                        st.markdown(f"{head} — {a['how']}: he is a must-start.")
            elif m["role"] == "bench":
                rival = bench_gap(m, rows)
                n_bench = int((rows["role"] == "bench").sum())
                head = f"Week {week}: **on {team_name}'s bench** ({int(m['bench_rank'])} of {n_bench}), {float(m['value']):.2f}"
                if m["value_source"] == "unvalued":
                    st.markdown(f"Week {week}: **on {team_name}'s bench** ({int(m['bench_rank'])} of {n_bench}) with no value this week "
                                "(no projection): he starts only where nobody else can play.")
                elif yes(m["locked_now"]):
                    st.markdown(head + " — his game has started, he stays benched.")
                elif rival is not None:
                    gap = float(rival["value"]) - float(m["value"])
                    st.markdown(f"{head}. To start at {slot_label(rival['slot'])} he would have to beat "
                                f"{player_link(rival['gsis_id'], rival['player_name'])} ({float(rival['value']):.2f})"
                                + (f", {gap:.2f} more." if gap > TOL else "."))
                else:
                    st.markdown(head + ".")
            else:
                st.markdown(f"Week {week}: **not in {team_name}'s lineup** — {m['reason'] or 'cannot play'}.")

# ------------------------------------------------------------------ 5. signals (C6: R-10 role alert + R-12 scenario upside)
# One query (the card's sixth): his role alert from his team's latest game (mart_player_role_alerts.is_latest) and, for a
# bigger role, the larger-role scenario for the card's week in this league's scoring (mart_player_scenarios).
with st.container(border=True):
    st.markdown("**Signals** — has his role changed lately?")
    if pos not in ("QB", "RB", "WR", "TE"):
        unavailable("role alerts cover quarterbacks, running backs, receivers and tight ends (a kicker's work is his team's).")
    elif missing_relations(("mart_player_role_alerts", "mart_player_scenarios")):
        unavailable("role alerts arrive with the nightly update; they are not on this copy yet.")
    else:
        sig = query(
            """select r.direction, r.kind, r.cause_text, r.since_week, r.week as alert_week, r.games_held, r.change_text,
                      r.trigger_name, r.trigger_status, r.trigger_ended, r.expires_after_week,
                      s.week, s.base_points, s.larger_points, s.points_gain, s.with_alert_points, s.presentation,
                      s.backtest_n, s.backtest_hit_rate
               from analytics.mart_player_role_alerts r
               left join analytics.mart_player_scenarios s
                      on s.gsis_id = r.gsis_id and s.season = r.season and s.league_id = %s
                     and s.week = (select min(x.week) from analytics.mart_player_scenarios x
                                   where x.gsis_id = r.gsis_id and x.season = r.season and x.league_id = %s and x.week >= %s)
               where r.gsis_id = %s and r.season = %s and r.is_latest""",
            (league_id, league_id, week if week is not None else 0, gsis, season),
        )
        if sig.empty:
            st.markdown("Role: **no role change detected** in his last three games: his share of the snaps, targets and "
                        "carries is where it has been.  \nUpside: no additional modeled upside scenario available.")  # ---- II-4
        else:
            r = sig.iloc[0]
            st.markdown(f"Role: **{alert_headline(r, p['player_name'])}**. {alert_lines(r)}")
            if r["direction"] == "up" and is_num(r["larger_points"]):
                st.markdown("Upside: " + scenario_phrase(r, league_name))
            elif r["direction"] == "up":
                st.markdown("Upside: no what-if for the coming weeks (no game to project, or the reason has ended).")
            else:
                st.markdown("Upside: none: his role shrank, and the projection above already leans on his last three games.")
        st.caption("A role alert needs his share of the snaps, targets or carries to jump (or fall) well past his usual swing, "
                   "in every one of his last one to three games. The what-if re-runs the same projection with his last three "
                   f"games at the new level, in {league_name} scoring.")


with st.expander("How to read this"):
    st.markdown(
        "- **Usage** is the work he gets: his share of his team's targets or carries, of its plays, of the quarterback's "
        "first looks and of the red-zone chances. The arrow is the last 3 games: up means a growing role.\n"
        f"- **Projection** is this week's projected points in {league_name} scoring. **Most weeks** is the range half "
        "his weeks land in (a quarter below, a quarter above); the **floor** and **ceiling** are a bad week and a good "
        "week: 1 week in 10 lands below the floor, 1 in 10 above the ceiling. The opponent's rank is 1 for the "
        "defense that gives up the most to his position.\n"
        "- **Rest of season** adds up his projection for every week left in this league's season, up to its final: use it "
        "for trades and waivers, where the next four weeks are not the whole story. His bye is a week with no game, not a "
        "low score. *Likely* is the range 8 seasons in 10 would land in if every week were its own roll of the dice; a role "
        "change or an injury moves the weeks together, so the real range is wider. The rank is among every player at his "
        "position in this league, rostered or not. Only this week has betting lines yet: the later weeks lean on his usage "
        "and the schedule.\n"
        "- **Availability** says whose team he is on (or that he is a free agent), his injury status, and whether his "
        "game has started.\n"
        "- **Value** compares what he scores with what his work is usually worth (above = running hot, below = due), and "
        "says where he sits in his team's best lineup this week and how much that lineup would lose without him."
    )
