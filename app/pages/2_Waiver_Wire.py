"""Waiver Wire: the adds worth a claim for your roster, then every free agent ranked by projection v2 or opportunity."""

import pandas as pd
import streamlit as st
from lib.db import query
from lib.table import howto, show
from lib.ui import freshness_banner, league_slots, next_week_info, perspective, setup

setup("Waiver Wire")
freshness_banner()
league_id, roster_id, members = perspective(require_team=False)
cal = next_week_info()
season = int(cal["season"]) if not cal.empty else None
next_week = int(cal["next_week"]) if not cal.empty and pd.notna(cal["next_week"]) else None
if not cal.empty:
    st.caption(f"NFL {season}: week {int(cal['last_completed_week'])} complete" + (f", week {next_week} next." if next_week else "."))

howto(
    "**Adds worth a claim** (pick a team in the sidebar) is the short answer: per position your league starts, the free agents who beat "
    "your weakest projected starter this week or your best bench player this season.",
    "**Proj (v2)** is projection v2 for next week in this league's scoring (the Rankings page's board) and the table's default rank. "
    "Kickers have no v2 projection, so they sort last on it.",
    "Waiver decisions are also about **opportunity**, because opportunity persists and touchdowns don't. Rank by the usage columns, then check the points.",
    "**Target % / Snap %** — the player's share of his team's targets and offensive snaps. A receiver at 20%+ targets on 80%+ snaps has a real role whatever his points say.",
    "**xPPG** prices that opportunity under this league's scoring. **PPG − xPPG** well below zero = he has been unlucky; the cheap add nobody else sees.",
    "**Trend / Momentum** (from the Trends page) name the usage metrics that moved over the last three games beyond the player's own noise. Blank until game four.",
    "**1st-read share** (season and last 3) is the player's share of his team's first-read targets — where the QB looks first, from FTN charting. "
    "A free agent whose first-read share is rising before his target share is the earliest role signal on this page.",
    "**Opp rank** is next week's matchup for his position (1 = the defense that gives up the most). **Depth** is his rank on the team's latest depth chart.",
    "Injured (Out / injured reserve) players are hidden by default.",
    title="How to use this page",
)

# ------------------------------------------------------------- U-11: adds worth a claim
# One query. Bars per position the league starts (N = starting slots, SUPER_FLEX counts as a QB slot,
# FLEX-type slots ignored): (a) the roster's weakest projected starter = its N-th best playable v2
# projection for next week (Out / Doubtful / IR are not playable, the Rankings rule; IR-slot players
# excluded); (b) its best bench PPG = the (N+1)-th best PPG. Every free agent (not Out / IR) is compared
# with both; at most 3 per position that clear at least one bar. Players join on gsis_id; unknown stays NULL.
SHORTLIST_SQL = """
with prm as (select %s::text as league_id, %s::int as roster_id, %s::int as season, %s::int as week),
slots as (
    select case rp.slot when 'SUPER_FLEX' then 'QB' else rp.slot end as position, count(*)::int as n
    from analytics.dim_league_season as ls
    join prm on prm.league_id = ls.league_id
    cross join lateral jsonb_array_elements_text(ls.roster_positions) as rp(slot)
    where rp.slot in ('QB', 'RB', 'WR', 'TE', 'K', 'SUPER_FLEX')
    group by 1
),
proj as (
    select p.gsis_id, p.position, round(p.proj_points, 1) as proj, p.p10, p.p90, p.is_rankable
    from analytics.mart_player_week_projections as p
    join prm on p.league_id = prm.league_id and p.season = prm.season and p.week = prm.week
),
mine as (
    select a.position, a.player_name, round(a.ppg_std, 1) as ppg,
           case when p.is_rankable then p.proj end as proj,
           row_number() over (partition by a.position order by case when p.is_rankable then p.proj end desc nulls last, a.gsis_id) as proj_rn,
           row_number() over (partition by a.position order by a.ppg_std desc nulls last, a.gsis_id) as ppg_rn
    from analytics.mart_player_availability as a
    join prm on a.league_id = prm.league_id and a.rostered_by_roster_id = prm.roster_id
    left join proj as p on p.gsis_id = a.gsis_id
    where not coalesce(a.is_on_ir, false)
),
bars as (
    select s.position, s.n,
           exists (select 1 from proj where proj.position = s.position) as modeled,
           w.proj as weak_proj, case when w.proj is not null then w.player_name end as weak_name,
           b.ppg as bench_ppg, case when b.ppg is not null then b.player_name end as bench_name
    from slots as s
    left join mine as w on w.position = s.position and w.proj_rn = s.n
    left join mine as b on b.position = s.position and b.ppg_rn = s.n + 1
),
cmp as (
    select b.position, a.gsis_id, a.player_name, a.nfl_team, a.injury_status, a.games_played,
           round(a.ppg_std, 1) as ppg_std, p.proj as proj_v2, p.p10, p.p90,
           case when p.is_rankable then p.proj - b.weak_proj end as week_diff,
           -- fewer playable players than slots: the N-th slot is open this week (flex slots are not counted)
           coalesce(p.is_rankable and p.proj is not null and b.modeled and b.weak_proj is null, false) as week_open,
           -- the season bar needs two games: a one-game PPG is a box score, not a rate (PO decision, wave A)
           case when coalesce(a.games_played, 0) >= 2 then round(a.ppg_std, 1) - b.bench_ppg end as season_diff
    from analytics.mart_player_availability as a
    join prm on a.league_id = prm.league_id
    join bars as b on b.position = a.position
    left join proj as p on p.gsis_id = a.gsis_id
    where a.is_free_agent
      and a.injury_status is distinct from 'Out' and a.injury_status is distinct from 'IR' and a.roster_status is distinct from 'RES'
),
cleared as (
    select c.*, row_number() over (
               partition by c.position
               order by (coalesce(c.week_diff > 0, false) or c.week_open)::int + coalesce(c.season_diff > 0, false)::int desc,
                        c.proj_v2 desc nulls last, c.ppg_std desc nulls last, c.gsis_id) as pick
    from cmp as c
    where coalesce(c.week_diff > 0, false) or c.week_open or coalesce(c.season_diff > 0, false)
)
select b.position as bar_position, b.n, b.modeled, b.weak_proj, b.weak_name, b.bench_ppg, b.bench_name,
       c.pick, c.gsis_id, c.player_name, c.position, c.nfl_team, c.injury_status, c.games_played, c.ppg_std, c.proj_v2, c.p10, c.p90,
       c.week_diff, c.week_open, c.season_diff
from bars as b
left join cleared as c on c.position = b.position and c.pick <= 3
order by b.position, c.pick
"""


def _claim_week(r: pd.Series) -> str:
    slot = f"{r['bar_position']}{int(r['n'])}"
    if r["week_open"]:
        return f"fills your open {slot} slot this week (Proj {r['proj_v2']:.1f}; no playable {slot} on your roster)"
    if pd.isna(r["week_diff"]):
        return ""
    d = round(float(r["week_diff"]), 1)
    nums = f"(Proj {r['proj_v2']:.1f} vs {r['weak_proj']:.1f})"
    if d > 0:
        return f"+{d:.1f} over your {slot} this week {nums}"
    return f"{abs(d):.1f} below your {slot} this week {nums}" if d < 0 else f"level with your {slot} this week {nums}"


def _claim_season(r: pd.Series) -> str:
    pos = r["bar_position"]
    if pd.isna(r["ppg_std"]):
        return ""
    if pd.isna(r["bench_ppg"]):
        return f"no bench {pos} with a PPG to compare"
    games = int(r["games_played"]) if pd.notna(r["games_played"]) else 0
    if pd.isna(r["season_diff"]):
        return f"only {games} game this season — not compared" if games == 1 else "no season comparison yet"
    d = round(float(r["season_diff"]), 1)
    nums = f"({r['ppg_std']:.1f} vs {r['bench_ppg']:.1f}, {games} games)"
    if d > 0:
        return f"+{d:.1f} PPG over your best bench {pos} {nums}"
    return f"{abs(d):.1f} PPG below your best bench {pos} {nums}" if d < 0 else f"level with your best bench {pos} {nums}"


def _compared_with(r: pd.Series) -> str:
    parts = []
    if isinstance(r["weak_name"], str):
        parts.append(f"{r['bar_position']}{int(r['n'])}: {r['weak_name']}")
    if isinstance(r["bench_name"], str):
        parts.append(f"best bench: {r['bench_name']}")
    return " · ".join(parts)


st.subheader("Adds worth a claim")
if roster_id is None:
    st.caption("Pick a team under **Team perspective** in the sidebar to see which free agents beat what that roster already has.")
else:
    howto(
        "For each position your league starts, up to three free agents (not Out / IR) who beat what you already have. A player is listed when he clears "
        "at least one bar; players clearing both come first, then the higher projection.",
        f"**This week vs your starter**: his projection v2 for week {next_week or 'next'} in this league's scoring against your *weakest projected starter* "
        "there — your RB2 when the league starts two RBs; a superflex slot counts as a second QB, FLEX slots are left out. Out, Doubtful and IR players "
        "don't count as starters (the Rankings rule), and players in your IR slot are left out.",
        "**Season vs your bench**: his PPG this season against the best PPG on your bench at the position (bench = your players beyond the top N by PPG). "
        "A player needs two games this season before his PPG counts (one game is a box score, not a rate). The two bars rank your players differently (next week's projection vs season PPG), "
        "so one player can be both your weakest projected starter and your best bench player.",
        "**Floor / Ceiling** are the projection's P10 / P90: one week in ten lands below the floor, one in ten above the ceiling. "
        "Kickers have no v2 projection, so K is compared on season PPG only.",
        title="How the shortlist is built",
    )
    sl = query(SHORTLIST_SQL, (league_id, roster_id, season, next_week))
    shortlist_positions = [p for p in league_slots(league_id) if p != "DEF"]   # K only where the league starts one
    sl = sl[sl["bar_position"].isin(shortlist_positions)]
    if not sl.empty and not sl.loc[sl["bar_position"] != "K", "modeled"].any():
        st.info(f"Projection v2 has no week {next_week or '(next)'} board for this league yet (it is written by `make project`), "
                "so the shortlist compares season PPG only.", icon="ℹ️")
    picks = sl[sl["gsis_id"].notna()].copy()
    if not picks.empty:
        picks["claim_week"] = picks.apply(_claim_week, axis=1)
        picks["claim_season"] = picks.apply(_claim_season, axis=1)
        picks["compared_with"] = picks.apply(_compared_with, axis=1)
        picks["_order"] = picks["bar_position"].map({p: i for i, p in enumerate(shortlist_positions)})
        picks = picks.sort_values(["_order", "pick"])
        show(picks, ["player_name", "position", "nfl_team", "injury_status", "claim_week", "proj_v2", "p10", "p90",
                     "claim_season", "ppg_std", "compared_with"])
    for pos in shortlist_positions:
        bar = sl[sl["bar_position"] == pos]
        if bar.empty or bar["gsis_id"].notna().any():
            continue
        b = bar.iloc[0]
        if not b["modeled"] and pd.isna(b["bench_ppg"]):
            why = "projection v2 does not project kickers" if pos == "K" else f"projection v2 has no {pos} board for this week"
            st.caption(f"Nothing to compare at {pos}: {why} and your bench has no {pos} with a PPG.")
        else:
            st.caption(f"Nothing on the wire beats what you have at {pos}.")

# ------------------------------------------------------------- every free agent
c1, c2, c3, c4 = st.columns([1.2, 1, 1, 1.4])
league_pos = [p for p in league_slots(league_id) if p in ("QB", "RB", "WR", "TE", "K")]   # no K in a league without a kicker slot
positions = c1.multiselect("Positions", league_pos, default=[p for p in ("RB", "WR", "TE") if p in league_pos])
min_games = c2.number_input("Min games played", 1, 17, 2)
hide_injured = c3.checkbox("Hide Out / IR", value=True)
sort_labels = {
    "proj_v2": f"Projection v2 (week {next_week})" if next_week else "Projection v2 (next week)",
    "expected_per_game": "Expected PPG (opportunity)", "momentum": "Momentum (role trend, needs 4+ games)", "target_share_l3": "Target % (last 3)", "target_share_trend": "Target trend",
    "first_read_share_l3": "1st-read share (last 3)",
    "carry_share_l3": "Carry % (last 3)", "snap_pct_l3": "Snap % (last 3)", "points_per_game_l3": "PPG (last 3)", "ppg_std": "PPG (season)",
    "diff_per_game": "Most unlucky (PPG − xPPG)",
}
sort_by = c4.selectbox("Rank by", list(sort_labels), format_func=lambda k: sort_labels[k])

fa = query(
    """select a.player_name, a.position, a.nfl_team, a.roster_status, a.injury_status, a.depth_rank,
              a.games_played, a.targets_per_game, a.carries_per_game, a.target_share, a.target_share_l3, a.target_share_trend,
              a.carry_share, a.carry_share_l3, a.avg_offense_snap_pct, a.snap_pct_l3, a.first_read_share_std, a.first_read_share_l3,
              a.ppg_std, a.points_per_game_l3, a.expected_per_game, a.diff_per_game,
              a.opponent, a.is_bye, a.opp_rank_std, t.tags, t.momentum, pr.proj_points as proj_v2
       from analytics.mart_player_availability a
       left join analytics.mart_player_trend_tags t on t.gsis_id = a.gsis_id and t.season = a.season
       left join analytics.mart_player_week_projections pr
              on pr.league_id = a.league_id and pr.gsis_id = a.gsis_id and pr.season = %s and pr.week = %s
       where a.league_id = %s and a.is_free_agent and a.position = any(%s) and coalesce(a.games_played, 0) >= %s""",
    (season, next_week, league_id, positions, int(min_games)),
)
if hide_injured:
    fa = fa[~fa["injury_status"].isin(["Out", "IR"]) & (fa["roster_status"] != "RES")]
fa = fa.sort_values(sort_by, ascending=(sort_by == "diff_per_game"), na_position="last")

st.subheader(f"Free agents · {len(fa)} players")
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
if sort_by not in cols:          # the column the list is ranked by is always shown
    cols = cols[:8] + [sort_by] + cols[8:]
if not fa.empty and fa[sort_by].isna().all():
    st.info(f"**{sort_labels[sort_by]}** has no values yet for these players (it needs more games this season), so the list is not ranked by it.")
show(fa, cols, height=560)

# ------------------------------------------------------------- your drop candidates
if roster_id is not None:
    st.subheader("Your bench, weakest first")
    howto("Sorted by expected PPG, then PPG. The bottom of this list is where a waiver add would come from. "
          "A player on a bye with low expected points is the usual first cut; an injured player with a strong role is not.")
    bench = query(
        """select player_name, position, nfl_team, injury_status, games_played, ppg_std, points_per_game_l3, expected_per_game,
                  target_share_l3, carry_share_l3, snap_pct_l3, opponent, is_bye, opp_rank_std
           from analytics.mart_player_availability
           where league_id = %s and rostered_by_roster_id = %s and not is_current_starter and not is_on_ir
           order by coalesce(expected_per_game, ppg_std, 0) asc""",
        (league_id, roster_id),
    )
    show(bench)

# ------------------------------------------------------------- recent league moves
st.subheader("Recent league moves")
howto("Completed waiver claims, free-agent adds, drops and trades, newest first. Useful for seeing who is chasing the same positions and what bids clear.")
tx = query(
    """select created_at, week, transaction_type, action, team_name, player_name, position, waiver_bid
       from analytics.mart_league_transactions where league_id = %s and status = 'complete'
       order by created_at desc limit 40""",
    (league_id,),
)
show(tx)
