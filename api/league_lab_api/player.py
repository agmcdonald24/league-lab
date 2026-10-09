"""The player card (`app/pages/0_Player.py`) as JSON: header + Usage, Projection, Availability, Value, Signals.

The page keeps its queries and sentences inline (not in app/lib), so they are copied here VERBATIM — the five
card queries (decision week, profile, projection, schedule, the roster's lineup via `cards.lineup_rows`) and the
signals query, and every sentence the page writes. The lineup sentence uses `cards.alternative`, `cards.bench_gap`,
`cards.verdict` and `cards.slot_label`; the signals sentences use `signals.alert_headline` / `alert_lines` /
`scenario_phrase` (the same functions the page imports). tests/test_parity.py renders the real page with
Streamlit's AppTest and compares every metric and sentence, so a change to the page that is not carried here fails.
"""

from __future__ import annotations

import pandas as pd
from league_lab import availability_gate as AGATE  # ---- PO (Wave I-S): the week's own report through the gate
from league_lab import clock

from . import availability as AV
from . import league_gate as LG  # ---- IS-2
from .applib import cards, links, signals, ui
from .applib import ros as ROS
from .db import missing_relations, query
from .myweek import NotFound, league_row

ET = "America/New_York"
pct = ui.pct
player_link = ui.player_link


def is_num(v) -> bool:
    return v is not None and not (isinstance(v, float) and pd.isna(v)) and pd.notna(v)


def yes(v) -> bool:
    return v is True or (not isinstance(v, float) and v is not None and pd.notna(v) and bool(v))


def _metric(label: str, value: str, delta: str | None = None, trend: str | None = None, help: str | None = None) -> dict:
    return {"label": label, "value": value, "delta": delta, "trend": trend, "help": help}


MISSING_WORDS = {   # what a card leaves out for a league the nightly does not score, in plain words (QA, Wave F)
    "value.points_per_game": "his points per game in this league",
    "signals.upside": "the what-if line when a teammate is out",
}


def _section(title: str) -> dict:
    """One bordered box of the page: its title, then its blocks in the page's order —
    {kind: "metrics", metrics: [...]}, {kind: "markdown" | "caption", text}, {kind: "unavailable", text}."""
    return {"title": title, "blocks": []}


def md(sec: dict, text: str) -> None:
    sec["blocks"].append({"kind": "markdown", "text": links(text)})


def cap(sec: dict, text: str | None) -> None:
    sec["blocks"].append({"kind": "caption", "text": links(text or "")})


def unav(sec: dict, why: str) -> None:
    """The page's `unavailable(why)`: st.caption(f"unavailable: {why}")."""
    sec["blocks"].append({"kind": "unavailable", "text": f"unavailable: {why}"})


def metrics(sec: dict, items: list[dict]) -> None:
    sec["blocks"].append({"kind": "metrics", "metrics": items})


SEARCH_SQL = """select gsis_id, player_name, position, nfl_team, rostered_by_team, is_free_agent
           from analytics.mart_player_availability
           where league_id = %s
             and regexp_replace(lower(player_name), '[^a-z]', '', 'g') like '%%' || regexp_replace(lower(%s), '[^a-z]', '', 'g') || '%%'
           order by ppg_std desc nulls last, player_name limit 25"""


def search(league_id: str, q: str) -> list[dict]:
    league_row(league_id)
    q = (q or "").strip()
    if len(q) < 2:
        return []
    hits = query(SEARCH_SQL, (league_id, q))
    return [{"gsis_id": r.gsis_id, "player_name": r.player_name, "position": r.position, "nfl_team": r.nfl_team,
             "rostered_by_team": r.rostered_by_team, "is_free_agent": bool(r.is_free_agent),
             "label": f"{r.player_name} · {r.position} · {r.nfl_team or 'no team'} · "
                      + ("free agent" if r.is_free_agent else f"{r.rostered_by_team}")}
            for r in hits.itertuples()]


PROFILE_SQL = """select dp.gsis_id, coalesce(a.player_name, dp.player_name) as player_name, coalesce(a.position, dp.position) as position,
              dp.headshot_url,
              coalesce(a.nfl_team, dp.latest_team) as team, a.gsis_id is not null as in_pool, a.roster_status,
              a.rostered_by_roster_id, a.rostered_by_team, a.rostered_by_manager, a.is_free_agent, a.is_current_starter, a.is_on_ir,
              a.injury_status, a.injury, a.practice_status, a.depth_rank, a.depth_pos,
              nmx.injury_week, nmx.next_week as report_for_week,
              a.games_played, a.attempts, a.target_share, a.target_share_l3, a.carry_share, a.carry_share_l3,
              a.avg_offense_snap_pct, a.snap_pct_l3, a.first_read_share_std, a.first_read_share_l3,
              s.red_zone_target_share, s.red_zone_carry_share, s.fg_made, s.fg_att, s.fg_long, s.pat_made, s.pat_att,
              s.games_played as nfl_games, t.tags, t.opportunity_trend,
              v.ppg, v.expected_per_game, v.diff_per_game, v.position_rank_ppg, v.games_played as league_games,
              pv.ppg as prev_ppg, pv.position_rank_ppg as prev_rank, pv.games_played as prev_games
       from analytics.dim_player dp
       left join analytics.mart_player_availability a on a.gsis_id = dp.gsis_id and a.league_id = %s
       left join analytics.mart_player_next_matchup nmx on nmx.gsis_id = dp.gsis_id
       left join analytics.mart_player_season s on s.gsis_id = dp.gsis_id and s.season = %s and s.season_type = 'REG'
       left join analytics.mart_player_trend_tags t on t.gsis_id = dp.gsis_id and t.season = %s
       left join analytics.mart_league_player_season v on v.gsis_id = dp.gsis_id and v.league_id = %s and v.season = %s
       left join analytics.mart_league_player_season pv on pv.gsis_id = dp.gsis_id and pv.league_id = %s and pv.season = %s - 1
       where dp.gsis_id = %s"""

def _status_words(n: dict) -> str:
    """IU-3: after the status line, the reason when he sits, else the flag's measured rate ("Questionable: about 2 in 3
    play.", his position's — the Rankings row's words); "" for neither."""
    if n.get("sits") and n.get("words"):
        return f" {n['words']}"
    return f" {n['rate_words']}." if n.get("rate_words") else ""


def status_note(p, gsis, season, week) -> tuple[dict | None, bool]:
    """(the note a screen reads — ``league_gate.note`` — or None, whether it came from the week's own injury report).
    IS-2: the one definition's block (the stored record + Sleeper + ESPN). PO (Wave I-S): when those say nothing, THIS
    week's own injury report still counts — the mart's row only when it is the report for the coming week
    (``injury_week = next_week``; the newest row of another week is last week's game status, which is what IS-2
    removed) — asked through the same gate. The card and the watchlist's lean row both call this."""
    blk = LG.blocks([gsis], season, week).get(gsis) if isinstance(gsis, str) and week is not None else None
    # ---- IT-2 (Wave I-T): the gate's own third source is the week's report — the same word as the fallback below, so
    # the card keeps its report line (the injury and the practice status) when that is where the word came from
    from_report = bool(blk) and blk.get("source") == AGATE.REPORT_SOURCE
    # ---- end IT-2
    if blk is None and isinstance(p.get("injury_status"), str) and p.get("injury_status") \
            and pd.notna(p.get("injury_week")) and pd.notna(p.get("report_for_week")) \
            and int(p["injury_week"]) == int(p["report_for_week"]):
        blk = AGATE.report_block(p["injury_status"])
        from_report = blk is not None
    return LG.note(blk, position=p.get("position")), from_report          # ---- IU-3: the position's rate


PROJ_SQL = """select proj_points, p10, p25, p75, p90, proj_targets, proj_receptions, proj_receiving_yards, proj_receiving_tds,
              proj_carries, proj_rushing_yards, proj_rushing_tds, proj_attempts, proj_passing_yards, proj_passing_tds,
              proj_passing_interceptions, opponent, is_home
       from analytics.mart_player_week_projections
       where league_id = %s and gsis_id = %s and season = %s and week = %s"""

SCHED_SQL = """select g.week, g.kickoff_at, g.home_team = %s as is_home,
              case when g.home_team = %s then g.away_team else g.home_team end as opponent, d.rank_std as opp_rank
       from analytics.dim_game g
       left join analytics.mart_defense_vs_position_current d
              on d.defense = case when g.home_team = %s then g.away_team else g.home_team end and d.position = %s
       where g.season = %s and g.season_type = 'REG' and %s in (g.home_team, g.away_team)
       order by g.week"""

SIGNALS_SQL = """select r.direction, r.kind, r.cause_text, r.since_week, r.week as alert_week, r.games_held, r.change_text,
                      r.trigger_name, r.trigger_status, r.trigger_ended, r.expires_after_week,
                      s.week, s.base_points, s.larger_points, s.points_gain, s.with_alert_points, s.presentation,
                      s.backtest_n, s.backtest_hit_rate
               from analytics.mart_player_role_alerts r
               left join analytics.mart_player_scenarios s
                      on s.gsis_id = r.gsis_id and s.season = r.season and s.league_id = %s
                     and s.week = (select min(x.week) from analytics.mart_player_scenarios x
                                   where x.gsis_id = r.gsis_id and x.season = r.season and x.league_id = %s and x.week >= %s)
               where r.gsis_id = %s and r.season = %s and r.is_latest"""

HOWTO = (
    "- **Usage** is the work he gets: his share of his team's targets or carries, of its plays, of the quarterback's "
    "first looks and of the red-zone chances. The arrow is the last 3 games: up means a growing role.\n"
    "- **Projection** is this week's projected points in {league} scoring. **Most weeks** is the range half "
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
    # ---- IP-3 fix round (Wave I-P): graded — the gap is what happened and the projection already counts it
    "- **Value** compares what he scores with what his work is usually worth (above or below it is what happened: his "
    "projection already counts it, and graded on past weeks it was no reason to buy or sell on its own), and "
    "says where he sits in his team's best lineup this week and how much that lineup would lose without him."
)


VALUE_FIELDS = ("ppg", "expected_per_game", "diff_per_game", "position_rank_ppg", "league_games", "prev_ppg", "prev_rank",
                "prev_games")


def player_card(league_id: str, gsis: str, od=None) -> dict:
    """The card for a house league (the database path), or — ``od``: an ``ondemand.PlayerContext`` — for any Sleeper
    league (plan F3): the NFL-wide parts (usage, injury, role alerts) from the database, the league's own parts
    (projection and range priced in its scoring, rest of season, whose team he is on, his lineup spot) on demand,
    and what needs the league's scored history (points per game, the what-if in its scoring) listed in ``missing``."""
    missing: list[str] = []
    if od is None:
        lrow = league_row(league_id)
        season, league_name, prof_league = int(lrow["season"]), str(lrow["league_name"]), league_id
    else:
        season, league_name, prof_league = od.season, od.league_name, od.profile_league
    week = cards.decision_week(season)                                                   # 1
    prof = query(PROFILE_SQL, (prof_league, season, season, prof_league, season, prof_league, season, gsis))   # 2
    if prof.empty:
        raise NotFound(f"No player with id `{gsis}`. Search for him above.")
    p = prof.iloc[0]
    if od is not None:                       # this league's rosters, not the profile league's; no league-scored history
        p = p.copy()
        for k, v in od.availability(gsis).items():
            p[k] = v
        for k in VALUE_FIELDS:
            p[k] = None
    pos, team = p["position"], p["team"]
    proj = (query(PROJ_SQL, (league_id, gsis, season, week if week is not None else -1)) if od is None    # 3
            else od.projection(gsis, pos, week))
    # ---- IS-2: the one definition's block, read before the projection: a player who sits this week is not shown a
    # projection the stored mart may still hold (the marts are rebuilt after project; the deploy lands before it)
    gate_note, from_report = status_note(p, gsis, season, week)      # ---- IS-2 + PO: one definition, two sources
    sits_now = bool(gate_note and gate_note["sits"])
    # ---- end IS-2
    sched = query(SCHED_SQL, (team, team, team, pos, season, team)) if isinstance(team, str) and team else pd.DataFrame()   # 4
    rostered = is_num(p["rostered_by_roster_id"])
    # ---- IB-0: the roster's context (the nightly's rows + the availability overlay), the rows My Week shows   # 5
    rctx = None
    if od is None:
        rctx = AV.roster_context(league_id, int(p["rostered_by_roster_id"]), week, house=True) if rostered and week else None
        rows = rctx.rows if rctx is not None else pd.DataFrame()
    else:
        rows = od.lineup(int(p["rostered_by_roster_id"]), week) if rostered and week else pd.DataFrame()
        rctx = getattr(od, "context", None)
    # ---- end IB-0

    # ---------------------------------------------------------- header
    # ---- IE-0 (Wave I-E): the league's platform in the words ("in his MFL lineup"), no "(None)" for a manager MFL
    # does not share
    plat = platform_word(league_id)
    mgr = f" ({p['rostered_by_manager']})" if isinstance(p["rostered_by_manager"], str) and p["rostered_by_manager"] else ""
    # ---- end IE-0
    where = (f"on **{p['rostered_by_team']}**{mgr}" if rostered
             else "**free agent** in this league" if yes(p["is_free_agent"]) else "not in this season's player pool")
    depth = f" · {p['depth_pos']}{int(p['depth_rank'])} on the depth chart" if is_num(p["depth_rank"]) and isinstance(p["depth_pos"], str) else ""
    header = f"{pos} · {team or 'no NFL team'}{depth} · {where}"
    game = sched[sched["week"] == week] if week is not None and not sched.empty else pd.DataFrame()

    # ---------------------------------------------------------- 1. usage
    usage = _section("**Usage** — " + ("his kicks this season" if pos == "K" else "his share of the team's opportunities"))
    if pos == "K":
        if is_num(p["fg_att"]) and p["nfl_games"]:
            fg_long = f", long {int(p['fg_long'])}" if is_num(p["fg_long"]) else ""
            md(usage, f"Field goals **{int(p['fg_made'])} of {int(p['fg_att'])}**{fg_long} · extra points "
                                  f"**{int(p['pat_made'] or 0)} of {int(p['pat_att'] or 0)}** in {int(p['nfl_games'])} games this season.")
        else:
            unav(usage, "no kicks recorded this season.")
    elif not yes(p["in_pool"]) or not is_num(p["games_played"]) or int(p["games_played"]) == 0:
        unav(usage, "no games this season yet." if yes(p["in_pool"]) else "he is not in this season's player pool.")
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
        ms = []
        for label, val, season_v, l3 in items:
            delta = trend = None
            if is_num(l3) and is_num(season_v) and int(p["games_played"]) > 3:
                up = float(l3) - float(season_v)
                delta, trend = f"{pct(l3)} last 3", ("up" if up > 0.0005 else "down" if up < -0.0005 else "off")
            ms.append(_metric(label, val or "—", delta, trend))
        metrics(usage, ms)
        tags = p["tags"] if isinstance(p["tags"], str) and p["tags"] else None
        gp = int(p["games_played"])
        cap(usage, f"Season to date, {gp} game{'s' if gp != 1 else ''}" + ("; the arrow is the last 3 games. " if gp > 3 else ". ")
                            + (f"Trend: {tags}." if tags else "Trend: none called.")
                            + (" Trends are called from a player's fourth game." if p["opportunity_trend"] == "insufficient" else ""))

    # ---------------------------------------------------------- 2. projection
    projection = _section(f"**Projection** — week {week}, {league_name} scoring" if week else "**Projection**")
    if week is None:
        unav(projection, "the regular season is over.")
    elif sits_now:                                                                         # ---- IS-2
        unav(projection, f"{gate_note['why']} — {gate_note['words'] or 'he is left out this week'}")
    elif not proj.empty:
        r = proj.iloc[0]
        mid = ([_metric("Most weeks", f"{float(r['p25']):.0f}–{float(r['p75']):.0f}",
                        help="Half his weeks land in this range: a quarter below it, a quarter above")]
               if is_num(r["p25"]) and is_num(r["p75"]) else [])      # the 50% range (plan D6); NULL on weeks frozen before it
        metrics(projection, [_metric("Projected", f"{float(r['proj_points']):.1f}"), *mid,
                             _metric("Floor", f"{float(r['p10']):.1f}", help="One week in ten he scores less"),
                             _metric("Ceiling", f"{float(r['p90']):.1f}", help="One week in ten he scores more")])
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
            md(projection, "Stat line: " + " · ".join(parts))
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
        unav(projection, why)
    # plan E2: rest of season, one line after the stat line (the page's block, same query, same sentences)
    ros_out = None
    ros_weeks: dict[int, float] = {}                                                       # ---- IF-4 (the schedule table)
    if week is not None and (od is not None or not missing_relations((ROS.RELATION,))):
        ros = (query(f"select {ROS.ROS_COLUMNS} from analytics.mart_player_ros_projection where league_id = %s and gsis_id = %s",
                     (league_id, gsis)) if od is None else od.ros(gsis, pos))
        # ---- IR-1 (Wave I-R): out indefinitely (IR, PUP, NFI, suspended) = no rest-of-season number, the reason instead
        try:
            gate = AV.statuses([gsis], season, week).get(gsis) or {}
        except Exception:  # noqa: BLE001 - the card stands without it
            gate = {}
        if gate.get("out_indefinitely"):
            md(projection, f"Rest of season: — {gate.get('ros_words')} ({gate.get('why')})")
        # ---- end IR-1
        elif not ros.empty:
            rr = ros.iloc[0]
            from .ondemand import ros_card
            ros_out = ros_card(rr)
            ros_weeks = dict(ROS.weeks_list(rr))                                               # ---- IF-4
            md(projection, ROS.card_line(rr))
            cap(projection, f"Week by week ({ROS.weeks_span(rr['from_week'], rr['last_week'])}, through this league's final): "
                            f"{ROS.weeks_words(rr)}. {ROS.lines_note(rr)}")
        elif yes(p["in_pool"]):
            cap(projection, "Rest of season: no projection yet.")
    if not game.empty:
        g = game.iloc[0]
        rank = f" — {g['opponent']} ranks **#{int(g['opp_rank'])}** of 32 vs {pos} (1 = gives up the most)" if is_num(g["opp_rank"]) else ""
        md(projection, f"Next: week {week} {'vs' if g['is_home'] else '@'} {g['opponent']}{rank}")
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
        cap(projection, "Next 4: " + " · ".join(x for x in nxt if x))
    elif week is not None:
        unav(projection, "no schedule for his team.")

    # ---------------------------------------------------------- 3. availability
    availability = _section("**Availability**")
    lines: list[str] = []
    if rostered:
        slot = (f"starting in his {plat} lineup" if yes(p["is_current_starter"])                       # ---- IE-0
                else ("on the IR slot" if yes(p["is_on_ir"]) else f"on the bench in {plat}"))
        lines.append(f"Rostered by **{p['rostered_by_team']}**{mgr}, {slot}.")
    elif yes(p["is_free_agent"]):
        lines.append("**Free agent** — nobody in this league has him.")
    else:
        lines.append("Not in this season's player pool for this league.")
    # ---- IS-2: the status line is the one definition's block (league_gate: the stored record + Sleeper + ESPN), with
    # its source and date and, when he sits, the reason — was the mart's injury_status (nflverse's newest report row:
    # midweek, last week's game status) and the older overlay's own set of codes
    inj = gate_note["status"] if gate_note else None
    if gate_note and from_report:      # ---- PO: the report's own line, with the injury and the practice status
        detail = f" ({p['injury']})" if isinstance(p["injury"], str) and p["injury"] else ""
        prac = f"; practice: {p['practice_status']}" if isinstance(p["practice_status"], str) and p["practice_status"] else ""
        words = _status_words(gate_note)
        lines.append(f"⚠️ **{gate_note['status']}**{detail}{prac}.{words}")
    elif gate_note:
        words = _status_words(gate_note)
        lines.append(f"⚠️ **{gate_note['why']}**.{words}")
    elif yes(p["in_pool"]):
        lines.append("No injury designation.")
    # ---- end IS-2
    if not sched.empty:
        weeks = set(sched["week"].astype(int))
        byes = [w for w in range(1, max(18, max(weeks)) + 1) if w not in weeks]
        if byes:
            b = byes[0]
            lines.append(f"Bye: week {b}" + (" (done)." if week is not None and b < week else "."))
    locked = False
    if week is not None and not game.empty:
        k = pd.Timestamp(game.iloc[0]["kickoff_at"])
        kick = k.tz_convert(ET)
        if k <= pd.Timestamp(clock.now()):  # ---- INF-1: the league's now
            locked = True
            lines.append(f"🔒 **Locked** for week {week}: his game kicked off {kick:%a %b %-d, %-I:%M %p} ET.")
        else:
            lines.append(f"Week {week} kickoff {kick:%a %b %-d, %-I:%M %p} ET — not locked yet.")
    elif week is not None and not sched.empty:
        lines.append(f"No game in week {week} (bye).")
    lines += overlay_lines(rctx, gsis, p["player_name"])                               # ---- IB-0
    md(availability, "  \n".join(lines))

    # ---------------------------------------------------------- 4. value
    value = _section(f"**Value** — {league_name} scoring")
    od_ppg = od_points_per_game(league_id, gsis, season) if od is not None else None      # ---- IE-0
    if od is not None and od_ppg is not None:
        # ---- IE-0: one statement — the game-log chart's own number (his stat lines priced in this league's scoring),
        # with its source; never "not shown yet" beside a chart that shows it
        metrics(value, [_metric("Points / game", f"{od_ppg['ppg']:.1f}",
                                help=f"This season, {od_ppg['games']} games: {od_ppg['source']}")])
        cap(value, f"Points per game: {od_ppg['ppg']:.1f} over {od_ppg['games']} games, {od_ppg['source']}.")
    elif od is not None:
        missing.append("value.points_per_game")        # needs this league's scored games: not kept for a new league
    elif is_num(p["ppg"]) and is_num(p["league_games"]) and int(p["league_games"]) > 0:
        vm: list[dict] = []
        vm.append(_metric("Points / game", f"{float(p['ppg']):.1f}",
                                        help=f"This season, {int(p['league_games'])} games, {league_name} scoring"))
        if is_num(p["expected_per_game"]):
            d = float(p["diff_per_game"]) if is_num(p["diff_per_game"]) else float(p["ppg"]) - float(p["expected_per_game"])
            vm.append(_metric("Expected", f"{float(p['expected_per_game']):.1f}", delta=f"{d:+.1f}",
                                            trend="up" if d > 0 else "down" if d < 0 else "off",
                                            help="Expected points per game: what his targets and carries were worth on average (depth, field "
                                                 "position). The arrow is points per game above or below that: above = he beat his opportunity"))
        if is_num(p["position_rank_ppg"]):
            vm.append(_metric("Rank", f"{pos}{int(p['position_rank_ppg'])}",
                                            help="By points per game among all players at the position"))
        if is_num(p["prev_ppg"]) and is_num(p["prev_games"]) and int(p["prev_games"]) > 0:
            vm.append(_metric("Last season", f"{float(p['prev_ppg']):.1f}",
                                            help=f"Points per game in {season - 1}, {int(p['prev_games'])} games, this league's scoring"
                                                 + (f"; {pos}{int(p['prev_rank'])}" if is_num(p["prev_rank"]) else "")))
        metrics(value, vm)
    elif is_num(p["prev_ppg"]) and is_num(p["prev_games"]) and int(p["prev_games"]) > 0:
        md(value, f"No games this season yet. Last season: **{float(p['prev_ppg']):.1f}** points per game over {int(p['prev_games'])} games.")
    else:
        unav(value, "no games this season or last in this league's scoring.")

    lineup_line: str | None = None
    lineup_unavailable: str | None = None
    if not rostered:
        cap(value, "Free agent: the Waiver Wire page shows what he would add to your lineup." if yes(p["is_free_agent"]) else "")
    elif week is None:
        lineup_unavailable = "no lineup: the regular season is over."
    elif rows.empty:
        lineup_unavailable = f"no proposed lineup for week {week} yet (the nightly refresh writes it)."
    else:
        me = rows[rows["gsis_id"] == gsis]
        team_name = p["rostered_by_team"]
        if me.empty:
            lineup_unavailable = f"he is not in {team_name}'s week-{week} lineup data (roster changed since the last refresh?)."
        else:
            m = me.iloc[0]
            if m["role"] == "starter":
                where_slot = cards.slot_label(m["slot"])
                if yes(m["locked_now"]):
                    lineup_line = f"Week {week}: **locked in at {where_slot}** for {team_name} (his game has started)."
                elif m["value_source"] == "unvalued":
                    lineup_line = f"Week {week}: **starts at {where_slot}** for {team_name} with no value yet (counted as 0 until {plat} scores him here)."
                else:
                    a = cards.alternative(m, rows)
                    alt = a["alt"]
                    src = {"season_ppg": " (his points per game this season)", "observed_ppg": f" (points per game {plat} scored)"}.get(m["value_source"], "")
                    head = f"Week {week}: **starts at {where_slot}** for {team_name}, {float(m['value']):.2f}{src}"
                    # ---- II-0: the cost and the words are the re-solved legal lineup's (locks kept), the chain said
                    ch = a.get("chain")
                    cost = cards.chain_cost(m, a, rows)
                    if alt is not None and ch is not None and a.get("mover") is not None:
                        linked = cards.chain_words_linked(ch, player_link)
                        lineup_line = (f"{head} — without him the lineup loses **{cost:.2f}**: {linked} "
                                       f"(worth {float(alt['value']):.2f}): {cards.verdict(cost)}.")
                    elif alt is not None:
                        lineup_line = (f"{head} — without him the lineup loses **{cost:.2f}** "
                                       f"({player_link(alt['gsis_id'], alt['player_name'])}, {float(alt['value']):.2f}, would come in): "
                                       f"{cards.verdict(cost)}.")
                    else:
                        lineup_line = f"{head} — {a['how']}: he is a must-start."
                    # ---- end II-0
            elif m["role"] == "bench":
                rival = cards.bench_gap(m, rows)
                n_bench = int((rows["role"] == "bench").sum())
                head = f"Week {week}: **on {team_name}'s bench** ({int(m['bench_rank'])} of {n_bench}), {float(m['value']):.2f}"
                if m["value_source"] == "unvalued":
                    lineup_line = (f"Week {week}: **on {team_name}'s bench** ({int(m['bench_rank'])} of {n_bench}) with no value this week "
                                   "(no projection): he starts only where nobody else can play.")
                elif yes(m["locked_now"]):
                    lineup_line = head + " — his game has started, he stays benched."
                elif rival is not None:
                    gap = float(rival["value"]) - float(m["value"])
                    lineup_line = (f"{head}. To start at {cards.slot_label(rival['slot'])} he would have to beat "
                                   f"{player_link(rival['gsis_id'], rival['player_name'])} ({float(rival['value']):.2f})"
                                   + (f", {gap:.2f} more." if gap > cards.TOL else "."))
                else:
                    lineup_line = head + "."
            else:
                lineup_line = f"Week {week}: **not in {team_name}'s lineup** — {m['reason'] or 'cannot play'}."
    if lineup_line:
        md(value, lineup_line)
    if lineup_unavailable:
        unav(value, lineup_unavailable)

    # ---------------------------------------------------------- 5. signals
    sig_sec = _section("**Signals** — has his role changed lately?")
    if pos not in ("QB", "RB", "WR", "TE"):
        unav(sig_sec, "role alerts cover quarterbacks, running backs, receivers and tight ends (a kicker's work is his team's).")
    elif missing_relations(("mart_player_role_alerts", "mart_player_scenarios")):
        unav(sig_sec, "role alerts arrive with the nightly update; they are not on this copy yet.")
    else:
        sig = query(SIGNALS_SQL, (prof_league, prof_league, week if week is not None else 0, gsis, season))
        if sig.empty:
            md(sig_sec, "Role: **no role change detected** in his last three games: his share of the snaps, targets and "
                                    "carries is where it has been.  \nUpside: no additional modeled upside scenario available.")  # ---- II-4
        else:
            r = sig.iloc[0]
            md(sig_sec, f"Role: **{signals.alert_headline(r, p['player_name'])}**. {signals.alert_lines(r)}")
            if od is not None:
                missing.append("signals.upside")       # the what-if is priced per house league in the nightly
            elif r["direction"] == "up" and gate_note and gate_note.get("sits"):          # ---- IT-3
                md(sig_sec, f"Upside: none this week — {gate_note['why']}.")
            elif r["direction"] == "up" and is_num(r["larger_points"]):
                md(sig_sec, "Upside: " + signals.scenario_phrase(r, league_name))
            elif r["direction"] == "up":
                md(sig_sec, "Upside: no what-if for the coming weeks (no game to project, or the reason has ended).")
            else:
                md(sig_sec, "Upside: none: his role shrank, and the projection above already leans on his last three games.")
        cap(sig_sec, "A role alert needs his share of the snaps, targets or carries to jump (or fall) well past his usual swing, "
                              "in every one of his last one to three games." + (
                              " The what-if re-runs the same projection with his last three "
                              f"games at the new level, in {league_name} scoring." if od is None else ""))

    extra = why_block(league_id, gsis, pos, season, week, proj, od, league_name)        # ---- IA-3
    if sits_now:          # ---- IS-2: no "why this number" (the mart's 11.4) under a 0 he gets because he sits
        extra = {**extra, "why": None, "market": None, "leans_on": None}
    role_sec = role_section(league_id, gsis, pos, team, season, week, league_name)        # ---- IL-1
    return {
        **extra,                                                                           # ---- IA-3
        "gsis_id": p["gsis_id"], "player_name": p["player_name"], "position": pos, "team": team if isinstance(team, str) else None,
        # ---- hotfix 2026-10-07: the card's own picture (dim_player; the contract since Wave G, never sent: the page
        # and the drawer showed a silhouette for every player). None = a silhouette.
        "headshot_url": p["headshot_url"] if isinstance(p.get("headshot_url"), str) and p["headshot_url"] else None,
        "header": header, "league_id": league_id, "league_name": league_name, "season": season, "week": week,
        "rostered_by_roster_id": int(p["rostered_by_roster_id"]) if rostered else None,
        "is_free_agent": yes(p["is_free_agent"]), "injury_status": inj, "locked": locked,
        "availability": gate_note,                                                         # ---- IS-2
        "proj_points": 0.0 if sits_now else (float(proj.iloc[0]["proj_points"]) if not proj.empty else None),   # IS-2
        "sections": {"usage": usage, "projection": projection, "availability": availability, "value": value, "signals": sig_sec,
                     "role": role_sec},                                                    # ---- IL-1: the Role block
        "howto": HOWTO.format(league=league_name),
        "ros": ros_out, "missing": [MISSING_WORDS.get(k, k) for k in missing], "missing_keys": missing,
        "source": "database" if od is None else "sleeper",
        "platform": provider_of_league(league_id),           # ---- IE-0; IK-3: espn / yahoo too (was mfl | sleeper)
        **({} if od is None else {"on_demand": od.meta()}),
        "news": news_block(p["gsis_id"]),                                                  # ---- N1
        "matchup_evidence": card_matchup_evidence(league_id, p, pos, team, league_name, season, week),   # ---- IF-3
        # ---- IF-4: the schedule table behind "Schedule" (week · opponent · projected, the card's own numbers) and the
        # games he has played this season (the role words: "not enough games to say" / "role steady over N games")
        "schedule": schedule_rows(sched, ros_weeks, week),
        "games_played": int(p["games_played"]) if is_num(p["games_played"]) else None,
        # ---- end IF-4
    }


# ---- IF-3 (Wave I-F): the card's matchup section carries the matchup evidence (research.matchup_evidence): the history
# as the card's "Next:" line ranks it (mart_defense_vs_position_current, the reference league's scoring), the corners
# now, the implication and the forecast's treatment, in two sentences (lib/card.ts puts them under "Next:").
def card_matchup_evidence(league_id: str, p, pos, team, league_name: str, season: int, week: int | None) -> dict | None:
    if week is None or pos not in ("QB", "RB", "WR", "TE") or not isinstance(team, str) or not team:
        return None
    from . import research as RS
    try:
        ctx = RS.Ctx(league_id, int(season), league_name, True, {}, [], int(week))
        ref = query("""select defense, position, games, through_week, points_allowed_per_game_std, rank_std
                       from analytics.mart_defense_vs_position_current where season = %s and position = %s""", (int(season), pos))
        return RS.matchup_evidence(ctx, str(p["gsis_id"]), int(week), dvp=ref,
                                   head={"gsis_id": p["gsis_id"], "player_name": p["player_name"], "position": pos, "team": team},
                                   scoring=f"{RS.reference_name()} scoring")
    except Exception:  # noqa: BLE001 - context on the card is never load-bearing: the rest of the card stands
        return None
# ---- end IF-3



# ---- IF-4 (Wave I-F; the I-E review's leftover "the compact schedule table on the card"): one row a week from this week
# to the season's last regular week: the opponent (home / away; None = bye), the matchup rank (1 = gives up the most to
# his position) and the projection the rest-of-season board holds for that week (None = no projection: unknown, not 0)
def schedule_rows(sched: pd.DataFrame, ros_weeks: dict[int, float], week: int | None) -> list[dict]:
    if week is None or sched is None or sched.empty:
        return []
    last = max(ros_weeks) if ros_weeks else int(sched["week"].max())        # the league's final when the board has it
    out = []
    for w in range(int(week), last + 1):
        gw = sched[sched["week"] == w]
        g = None if gw.empty else gw.iloc[0]
        out.append({"week": w, "opponent": None if g is None else str(g["opponent"]),
                    "is_home": None if g is None else bool(g["is_home"]),
                    "opp_rank": int(g["opp_rank"]) if g is not None and is_num(g["opp_rank"]) else None,
                    "proj": round(float(ros_weeks[w]), 2) if w in ros_weeks else None})
    return out
# ---- end IF-4


# ---- IB-0 (Wave I-B): the Availability section under the overlay. When the overlay re-solved his roster's week and
# he is in it, the section says what changed for him, in the context's words: "Justin Jefferson is out (ankle): he
# starts at FLEX2 this week" (he came in), "Not in this week's lineup: Out (ankle) · ESPN, Oct 2 2:35 PM ET" (he went
# out). Nothing is added when the overlay did not move his roster (the page's words stand: tests/test_parity.py).
def overlay_status(gsis: str, nightly: str | None) -> dict | None:
    """The overlay's entry for him when it says something the build did not (he cannot play, or he is questionable,
    and the build had another status): "Out (ankle) · ESPN, Oct 2 2:35 PM ET". None when the overlay is off."""
    if not AV.enabled():
        return None
    a = AV.now([gsis]).get(gsis)
    if a is None or not (a["cannot_play"] or a["flagged"]) or a["status"] == nightly:
        return None
    return a


def overlay_lines(rctx, gsis: str, name: str | None) -> list[str]:
    if rctx is None or not rctx.changed:
        return []
    r = rctx.row_of(gsis)
    if r is None:
        return []
    before = rctx.starters(rctx.base)
    sid = str(r["sleeper_player_id"]) if isinstance(r["sleeper_player_id"], str) else None
    out = []
    if r["role"] == "starter" and sid not in before:
        slot = cards.slot_label(r["slot"])
        why = next((c.split(" — ")[0] for c in rctx.changes if f" — {name} starts at " in c), None)
        out.append(f"**{why}: he starts at {slot} this week.**" if why else f"**He starts at {slot} this week** "
                   "(the lineup was re-solved with the latest injury news).")
    elif r["role"] == "unplayable" and sid in before:
        why = next((c for c in rctx.changes if name and c.startswith(f"{name} ")), None)
        out.append(f"**Not in this week's lineup**: {why}." if why else "**Not in this week's lineup**: he cannot play.")
    elif r["role"] == "bench" and sid in before:
        out.append(f"**On the bench this week**: the lineup was re-solved with the latest injury news "
                   f"({'; '.join(rctx.changes)}).")
    return out
# ---- end IB-0


# ---- IA-3 (Wave I-A): "why this number" on the card — top-level keys, so the sections stay the page's (test_parity):
# `why` (this week's stat line x this league's scoring = the projection), `market` (Sleeper's number for the week in
# this league's scoring, the gap in words; None and the reason when there is none), `leans_on` (the three inputs the
# model leans on most for his position: About's rows, About's words).
WEEK_LINE_SQL = """select proj_points, proj_targets, proj_receptions, proj_receiving_yards, proj_receiving_tds, proj_carries,
                          proj_rushing_yards, proj_rushing_tds, proj_attempts, proj_passing_yards, proj_passing_tds,
                          proj_passing_interceptions, proj_fumbles_lost
                   from analytics.mart_player_week_projections
                   where league_id = %s and gsis_id = %s and season = %s and week = %s"""


def why_block(league_id: str, gsis: str, pos: str, season: int, week: int | None, proj: pd.DataFrame, od,
              league_name: str) -> dict:
    from . import why
    try:
        if od is None:
            sc = query("select scoring_settings from analytics.dim_league_season where league_id = %s and is_current_season",
                       (league_id,))
            scoring = {k: float(v) for k, v in ((sc["scoring_settings"].iloc[0] or {}) if not sc.empty else {}).items()
                       if v is not None}
            line = query(WEEK_LINE_SQL, (league_id, gsis, season, week)) if week is not None else pd.DataFrame()
        else:
            scoring, line = od.scoring, proj
        r = line.iloc[0].to_dict() if not line.empty else {}
        ours = float(r["proj_points"]) if is_num(r.get("proj_points")) else None
        explained = why.explain(why.line_of(r), ours, scoring, pos, season=season, week=week) if r else None   # ---- M6
        market = why.market_points(season, week, [gsis], scoring).get(gsis)
        if provider_of_league(league_id) != "sleeper":  # ---- IE-0: the market line is Sleeper's (IK-3: not ESPN / Yahoo)
            return {"why": explained, "market": None, "leans_on": why.leans_on(
                od.profile_league if od is not None else league_id, None).get(pos)}
        lean = why.leans_on(league_id if od is None else od.profile_league, league_name if od is None else None).get(pos)
    except Exception:  # noqa: BLE001 - the card never fails for its extras
        return {"why": None, "market": None, "leans_on": None}
    return {"why": explained, "market": why.market_block(ours, market, week) if week is not None and pos in why.ORDER else None,
            "leans_on": lean}
# ---- end IA-3


# ---- N1 (Wave I-D): the news line — ESPN's latest headlines for him (league_lab_api/news.py): at most 3, newest
# first, none older than 14 days; [] when the feed is off or out. A top-level key, so the sections stay the page's.
def news_block(gsis: str) -> list[dict]:
    try:
        from . import news
        return news.for_card(str(gsis))
    except Exception:  # noqa: BLE001 - the card never fails for its news
        return []
# ---- end N1


# ---- IE-0 (Wave I-E): the league's platform in the card's words (the review's P0 #3: "On the bench in Sleeper" on an
# MFL roster), and the one points-per-game statement of an on-demand league (the chart's number, with its source)
def is_mfl_league(league_id) -> bool:
    from league_lab import platforms
    return platforms.is_mfl(league_id)


def platform_word(league_id) -> str:
    from league_lab import platforms
    return platforms.provider_short(league_id)          # ---- IK-3: "ESPN" / "Yahoo" too (was MFL | Sleeper)


def provider_of_league(league_id) -> str:              # ---- IK-3
    from league_lab import platforms
    return platforms.provider_of(league_id)


def od_points_per_game(league_id: str, gsis: str, season: int) -> dict | None:
    """{ppg, games, source} from his played games this regular season, priced in this league's scoring exactly as the
    game-log chart prices them (`research.league_games`), or None when there is nothing to price."""
    try:
        from . import research as R
        g = R.league_games(R.context(league_id, None), int(season), [gsis])
        fg = query("""select game_id from analytics.fct_player_game where gsis_id = %s and season = %s
                      and season_type = 'REG' and played""", (gsis, int(season)))
        pts = g[g["game_id"].isin(set(fg["game_id"]))]["points"].dropna()
    except Exception:  # noqa: BLE001 - the card never fails for this line: it is then listed as not shown
        return None
    if pts.empty:
        return None
    src = ("reconstructed in this league's MFL scoring from his stat lines" if is_mfl_league(league_id)
           else "counted in this league's scoring from his stat lines")
    return {"ppg": round(float(pts.mean()), 1), "games": int(len(pts)), "source": src}
# ---- end IE-0


# ---- IL-1 (Wave I-L; the fifth review § 10): the Role block — his recent role against his earlier one, his share of
# his position group's opportunities against its points (this league's scoring), and the games a positional teammate
# missed (league_lab.roles; the words and thresholds are there). A section of its own, after "Why this number" on the
# web (lib/card.ts); the console's page does not draw it (test_parity compares the page's five sections only).
ROLE_CAPTION = ("Recent role = his last 2 games with a snap; earlier = his games before them this season (3 or more). A "
                "change is named only when it is larger than his usual game-to-game swing (one standard deviation of "
                "the earlier games). What happened, not a forecast: this block does not move the projection.")


def role_section(league_id: str, gsis: str, pos: str, team, season: int, week: int | None, league_name: str) -> dict:
    sec = _section("**Role** — his recent role, his share of the work, games without a teammate")
    if pos not in ("QB", "RB", "WR", "TE"):
        unav(sec, "role numbers cover quarterbacks, running backs, receivers and tight ends.")
        return sec
    try:
        _role_blocks(sec, league_id, gsis, pos, team, season, week, league_name)
    except Exception:  # noqa: BLE001 - the card never fails for its role block: it says so instead
        sec["blocks"] = []
        unav(sec, "role numbers are not available for him right now.")
    return sec


def _role_blocks(sec: dict, league_id: str, gsis: str, pos: str, team, season: int, week: int | None,
                 league_name: str) -> None:
    from league_lab import roles

    from . import research as RS
    through = int(week) if week is not None else 18
    mine = query(roles.PLAYER_SEASON_SQL, (gsis, int(season), through))
    rc = roles.role_change(mine, pos)
    md(sec, f"**{rc['headline']}**")
    if rc["status"] != "too_early":
        cap(sec, " ".join(m["words"] for m in rc["metrics"]))
    if not isinstance(team, str) or not team:
        unav(sec, "he has no NFL team now: no team share or teammate scenario.")
        cap(sec, ROLE_CAPTION)
        return
    ctx = RS.context(league_id, None)
    group = query(roles.TEAM_SEASON_SQL, (team, int(season), through, roles.group_positions(pos)))
    if not group.empty:
        pts = RS.league_games(ctx, int(season), sorted(set(group["gsis_id"])))[["gsis_id", "game_id", "points"]]
        group = group.merge(pts, on=["gsis_id", "game_id"], how="left")
    his = group[group["gsis_id"] == gsis] if not group.empty else group
    md(sec, roles.opportunity_vs_production(his, group, pos, scoring=league_name, team=team)["words"])
    mate = roles.pick_teammate(group, gsis, pos) if not group.empty else None
    if mate is None:
        md(sec, roles.contingent_upside(pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), None, pos)["words"])
    else:
        span = (roles.CONTINGENT_FROM, int(season), int(season), through)
        pair = query(roles.PAIR_SQL, (team, *span, [gsis, mate["gsis_id"]]))
        me = pair[pair["gsis_id"] == gsis]
        if not me.empty:
            priced = pd.concat([RS.league_games(ctx, int(s), [gsis])[["gsis_id", "game_id", "points"]]
                                for s in sorted(set(me["season"]))], ignore_index=True)
            me = me.merge(priced, on=["gsis_id", "game_id"], how="left")
        roster = query(roles.ROSTER_SQL, (mate["gsis_id"], team, *span, list(roles.ON_ROSTER)))
        md(sec, roles.contingent_upside(me, pair[pair["gsis_id"] == mate["gsis_id"]], roster, mate, pos,
                                        scoring=league_name)["words"])
    cap(sec, ROLE_CAPTION)
# ---- end IL-1
