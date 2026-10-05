"""My Week for ANY Sleeper league (plan E3 spike): served without that league in the database.

`/api/my-week?league=<id>&team=<roster_id>` falls through to here when the league is not a current-season league of
the database (or `source=sleeper` asks for this path). `league_lab.anyleague` fetches the league, its rosters and
users from Sleeper (`LEAGUE_LAB_SLEEPER_FIXTURES=<dir>` reads fixtures instead), prices the NFL-wide stat lines in
the league's scoring, approximates the ranges from the nearest fitted league, and solves the lineup with the
nightly's own code (`lineup.build`); it returns the frame `cards.lineup_rows` returns, so the cards, the lineup
table and "How to read this" come from `app/lib/cards.py` exactly as on the database path (`myweek.cards_from_rows`).

Same JSON shape as `myweek.my_week`, plus `source: "sleeper"` and `on_demand`: the range reference (a reference
scoring on F1's NFL-wide board, a fitted house league on the borrowed one), the players Sleeper has that
`player_id_map` does not (unvalued), the scoring keys the projection cannot price, where K / DEF values came from,
the board source and the timings. The week's opponent comes from Sleeper's matchups call (plan F3) with his best
lineup value solved the same way. Not served here (they need the league's history in the database): the league
rank in the league line, Sleeper's weekly lineup lists (the nightly prefers them for a week Sleeper has opened).

Plan F3 adds the league picker by username (`leagues_for_user`), rest of season for any league (`ros`) and the
record (`record`, house leagues only).
"""

from __future__ import annotations

import functools  # ---- V-1 (Wave I-G): record()'s decisions wrapper
import re  # ---- II-5: the setup flow's Sleeper link
import time
from datetime import UTC, datetime  # IG-3

import numpy as np
import pandas as pd
from league_lab import anyleague as A
from league_lab import scoring as S  # ---- M4 (Wave I-G): the pricing mode (record_pricing)
from league_lab.lineup import UNVALUED, Player  # ---- IB-3

from . import availability, db, why
from .applib import cards, ui
from .db import query
from .myweek import (  # IE-1 (+ annotate_swaps, PO I-E)
    NOTHING_SUBMITTED,
    NotFound,
    _num,
    _str,
    annotate_swaps,
    build_actions,
    cards_from_rows,
    clocks,  # ---- II-4
    current_starters,
    edit_link,
    howto,
    lineup,
    what_changed,
)
from .settings import APP_NAME

# ---- INF-2 (Wave I-J): a Board / a window is kept as built (anyleague's ``boards`` / ``ros`` regions), not its raw rows
db.not_kept(*A.BOARD_INPUT_SQL)

MOVERS_SQL = """select t.gsis_id, t.player_name, t.position, t.tags, t.momentum
                from analytics.mart_player_trend_tags t
                where t.season = %s and t.gsis_id = any(%s) and t.opportunity_trend in ('rising', 'falling')
                order by abs(t.momentum) desc limit 9"""


class SleeperDown(RuntimeError):
    pass


def opponent_safe(league_id: str, roster_id: int, week: int, *, query_fn=query, as_of=None,
                  exclude_reference: str | None = None, solve: bool = True) -> tuple[dict | None, str | None]:
    """(the week's opponent from Sleeper's matchups call, a note when Sleeper could not say). The opponent is a
    nicety: Sleeper down or our budget spent leaves it null instead of failing the page."""
    try:
        return A.opponent(query_fn if solve else None, league_id, int(roster_id), int(week), as_of=as_of,
                          exclude_reference=exclude_reference, solve=solve), None
    except A.SleeperBusy:
        return None, "busy"
    except A.SleeperUnavailable:
        return None, "sleeper_unavailable"


def my_week(league_id: str, roster_id: int, *, as_of=None, exclude_reference: str | None = None) -> dict:
    t0 = time.perf_counter()
    try:
        league_id = A.check_id(league_id)
        client = A.sleeper()
        league = client.league(league_id)
        season = int(league["season"])
        week = cards.decision_week(season)
        if week is None:
            return {"league_id": league_id, "league_name": league.get("name"), "season": season, "roster_id": int(roster_id),
                    "week": None, "source": "sleeper", "cards": [], "lineup": [], "lineup_full": [],
                    "notice": "The regular season is over: no lineup decisions left."}
        # ---- I0-A + IB-0: the roster's context (the on-demand rows + the availability overlay: the board's statuses
        # are the nightly's, newer news re-solves the lineup) - the rows Waivers, Team and the player card read too
        ctx = availability.roster_context(league_id, int(roster_id), week, house=False, as_of=as_of,
                                          exclude_reference=exclude_reference, client=client)
        od = ctx.od
        # ---- end I0-A + IB-0
        rosters, users = client.rosters(league_id), client.users(league_id)
    except A.LeagueNotFound as exc:
        raise NotFound(str(exc)) from exc
    except A.SleeperUnavailable as exc:
        raise SleeperDown(str(exc)) from exc
    names = A.team_names(rosters, users).get(int(roster_id), {})
    rec = A.records(rosters).get(int(roster_id))
    rows, avail = ctx.rows, ctx.meta
    t_opp = time.perf_counter()
    # ---- IB-0: the opponent's total through the same overlay (his roster's context)
    opp, opp_note = opponent_safe(league_id, int(roster_id), week, as_of=as_of, exclude_reference=exclude_reference,
                                  solve=False)
    if opp is not None:
        try:
            for o in (opp, *opp.get("also", [])):          # I-C: a double header's second opponent too
                octx = availability.roster_context(league_id, int(o["roster_id"]), week, house=False, as_of=as_of,
                                                   exclude_reference=exclude_reference, client=client)
                o["lineup_value"] = octx.lineup_value
                o["changes"] = octx.changes
        except (A.SleeperBusy, A.SleeperUnavailable, A.LeagueNotFound):
            opp_note = opp_note or "sleeper_unavailable"
    # ---- end IB-0
    t_opp = round((time.perf_counter() - t_opp) * 1000, 1)
    out: dict = {"league_id": league_id, "league_name": league.get("name"), "season": season,
                 "scoring_label": A.scoring_label(league),
                 "roster_id": int(roster_id), "team_name": names.get("team_name"), "manager_name": _str(names.get("manager_name")),
                 "week": week, "record": rec, "opponent": opp, "source": "sleeper"}
    out["availability"] = avail                      # ---- I0-A
    bits = [f"**{out['team_name']}**"]
    if out["manager_name"] and A.platforms.is_mfl(league_id):     # ---- IC-4: "Knight Train · <owner>" when MFL shares it
        bits.append(out["manager_name"])
    if rec:
        bits.append(f"{rec['wins']}-{rec['losses']}, #{rec['standing']} in the league")
    if opp and opp.get("team_name"):
        bits.append(f"week {week} vs **{opp['team_name']}**")
    out["summary"] = " · ".join(bits)
    out["league_line"] = cards.league_line(league_id, int(roster_id), week, rows) if not rows.empty else ""
    lv = rows.loc[rows["role"] == "starter", "lineup_value"].dropna() if not rows.empty else pd.Series(dtype=float)
    out["lineup_value"] = None if lv.empty else float(lv.iloc[0])
    # ---- IG-1: the starters the total counts at 0 (no projection), as the database path says it
    from .myweek import n_unvalued, unvalued_words
    out["n_unvalued"] = n_unvalued(rows)
    out["unvalued_words"] = unvalued_words(out["n_unvalued"])
    # ---- end IG-1
    t1 = time.perf_counter()
    cur = current_starters(league_id, int(roster_id), house=False)                                        # ---- IB-0
    out["notice"], out["cards"] = cards_from_rows(league_id, int(roster_id), week, season, rows, current=cur)
    # ---- IE-1: the actions (at most three), the set line, where to make the change, nothing is submitted from here
    out.update(build_actions(rows, out["cards"], cur, league_id))
    out.update({"edit_link": edit_link(league_id, league), "nothing_submitted": NOTHING_SUBMITTED})
    # ---- end IE-1
    out["changed"] = what_changed(avail, rows, cur)                                  # ---- IF-4: what changed (myweek)
    out["clocks"] = clocks(avail, out["changed"])                                    # ---- II-4: the home's three stamps
    t2 = time.perf_counter()
    out["lineup"], out["lineup_full"] = lineup(rows)
    annotate_swaps(out["lineup"], out["lineup_full"], out.get("swaps") or [])                              # ---- PO I-E
    out["howto"] = howto()
    gs = sorted({g for g in rows["gsis_id"].dropna()}) if not rows.empty else []
    mv = query(MOVERS_SQL, (season, gs)) if gs else pd.DataFrame()
    out["movers"] = [{"gsis_id": _str(r.gsis_id), "player_name": r.player_name, "position": r.position,
                      "tags": _str(r.tags), "momentum": _num(r.momentum)} for r in mv.itertuples()]
    out["win"] = win_on_demand(client, league_id, int(roster_id), season, week, rows, opp, as_of=as_of,      # ---- IH-3
                               exclude_reference=exclude_reference)
    t3 = time.perf_counter()
    timings = dict(od.timings_ms)
    timings.update({"opponent": t_opp, "cards": round((t2 - t1) * 1000, 1), "rest": round((t3 - t2) * 1000, 1),
                    "request_total": round((t3 - t0) * 1000, 1)})
    out["on_demand"] = {
        "range_method": A.RANGE_METHOD, "range_reference_league": od.reference_league,
        "unmapped_players": od.unmapped_players, "unmapped_scoring_keys": od.scoring.get("unmapped", []),
        "not_projected_keys": od.scoring.get("not_projected", []), "kd_value_source": od.kd_sources,
        "stat_line_mismatches": od.mismatched_lines, "sleeper_calls": od.sleeper_calls, "timings_ms": timings,
        "board_source": od.board_source, "opponent_note": opp_note,
    }
    if A.platforms.is_mfl(league_id):              # I0-B: what the MyFantasyLeague translation could not carry
        out["platform"] = "mfl"
        out["on_demand"].update(mfl_extras(league_id, league))
        out.update(mfl_roster_freshness(client, league_id))                                       # ---- IG-3
    elif not A.platforms.is_sleeper(league_id):    # ---- IK-3: an ESPN / Yahoo league's notes (provider_extras)
        out["platform"] = A.platforms.provider_of(league_id)
        out["on_demand"].update(provider_extras(league_id, league))
    return out


# ---- IG-3 (Wave I-G): an MFL league's own freshness line — when the rosters export this answer was built from was read
# from MyFantasyLeague (the client's cache: rosters live 10 minutes). IF-4's "Updated …" line is the morning build's.
def mfl_roster_freshness(client, league_id: str) -> dict:
    """{roster_updated_at: ISO UTC | None, roster_source: 'MFL'} for an ``mfl:`` league; {} for a Sleeper one."""
    if not A.platforms.is_mfl(league_id):
        return {}
    try:
        t = client.mfl.client.fetched_at("rosters", A.platforms.mfl_id(league_id))
    except Exception:  # noqa: BLE001 - a status line, never a failure
        t = None
    iso = None if t is None else datetime.fromtimestamp(float(t), UTC).replace(microsecond=0).isoformat()
    return {"roster_updated_at": iso, "roster_source": "MFL"}
# ---- end IG-3


# ---------------------------------------------------------------- plan F3: the league picker by Sleeper username
def leagues_for_user(username: str) -> dict:
    from .myweek import known_league
    season = ui.current_season()
    try:
        answer = with_cards(A.user_leagues(username, int(season), in_database=known_league))  # ---- IC-3: the cards
    except A.LeagueNotFound as exc:
        raise sleeper_user_error(username) from exc                    # ---- II-5: the specific words
    except A.SleeperUnavailable as exc:
        raise SleeperDown(str(exc)) from exc
    answer["capabilities"] = A.platforms.capabilities("sleeper")     # ---- II-5
    return answer


def rosters_for_league(league_id: str) -> list[dict]:
    """The team picker's options for a league the database does not have (F2's request): Sleeper's rosters
    and users, named the way dim_league_member names them (team name, else display name)."""
    sl = A.sleeper()
    try:
        league_id = A.check_id(league_id)         # I0-B: a Sleeper id or an mfl:<id> key
        sl.league(league_id)                      # 404 for an id Sleeper does not have (before the rosters call)
        rosters, users = sl.rosters(league_id), sl.users(league_id)
    except A.LeagueNotFound as exc:
        raise NotFound(str(exc) if not A.platforms.is_sleeper(league_id) else f"no Sleeper league {league_id}") from exc  # IK-3
    except A.SleeperUnavailable as exc:
        raise SleeperDown(str(exc)) from exc
    names = A.team_names(rosters, users)
    # IC-4: MFL's owner name when its league export shares it (team_names), else None (I0-B: was always None)
    out = [{"roster_id": rid, "team_name": n["team_name"], "manager_name": n["manager_name"]} for rid, n in names.items()]
    return sorted(out, key=lambda r: (r["team_name"] or "", r["roster_id"]))


# ---------------------------------------------------------------- plan F3: rest of season
ROS_MART_SQL = """select {cols}, a.rostered_by_roster_id, a.rostered_by_team
                   from analytics.mart_player_ros_projection r
                   left join analytics.mart_player_availability a
                          on a.league_id = r.league_id
                         and ((r.gsis_id is not null and a.gsis_id = r.gsis_id)
                              or (r.gsis_id is null and a.sleeper_id = r.player_key))   -- a defense: its Sleeper id is the team code (QA, Wave F)
                   where r.league_id = %s and (%s = 'ALL' or r.position = %s)
                   order by r.ros_points desc, r.player_key limit %s"""
POSITIONS = ("QB", "RB", "WR", "TE", "K", "DEF", "TMQB", "TMPK", "ALL")   # IC-4: the team units
POS_RANK_NOTE = ("pos_rank is the player's rank at his position among every projected player on an active NFL roster "
                 "in this league's scoring, rostered or not (mart_player_ros_projection's population)")


def _ros_player(r, roster_of: dict | None = None, team_of: dict | None = None) -> dict:
    out = {"gsis_id": _str(r.get("gsis_id")), "player_key": _str(r.get("player_key")), "player_name": _str(r.get("player_name")),
           "position": _str(r.get("position")), "team": _str(r.get("team")), "ros_points": _num(r.get("ros_points")),
           "ros_games": None if _num(r.get("ros_games")) is None else int(r.get("ros_games")),
           "playoff_points": _num(r.get("playoff_points")), "p10": _num(r.get("ros_p10")), "p90": _num(r.get("ros_p90")),
           "pos_rank": None if _num(r.get("ros_rank_pos")) is None else int(r.get("ros_rank_pos")),
           "rostered_by_roster_id": None, "rostered_by_team": None}
    if roster_of is not None:
        rid = roster_of.get(out["player_key"])
        out["rostered_by_roster_id"] = rid
        out["rostered_by_team"] = (team_of or {}).get(rid, {}).get("team_name") if rid is not None else None
    else:
        rid = _num(r.get("rostered_by_roster_id"))
        out["rostered_by_roster_id"] = None if rid is None else int(rid)
        out["rostered_by_team"] = _str(r.get("rostered_by_team"))
    out.update(_unit_bits(r))                                                    # ---- IC-4
    return out


# ---- IC-4 (Wave I-D): a team unit's row in the rest of season (INTERFACES.md § IC-4): `unit`, the player its weeks are
# priced from (the decision week's starting QB / kicker) and that said in words
UNIT_WORDS = {"TMQB": "team QB", "TMPK": "team K"}


def _unit_bits(r) -> dict:
    unit = r.get("unit")
    if not (isinstance(unit, bool | np.bool_) and bool(unit)):
        return {"unit": False}
    pos, g, name = _str(r.get("position")), _str(r.get("starter_gsis")), _str(r.get("starter_name"))
    words = None
    if name:
        words = (f"Priced from {name}'s line (the team's starting QB each week)" if pos == "TMQB"
                 else f"Priced from {name}'s line (the team's kicker each week)")
    return {"unit": True, "priced_from": {"gsis_id": g, "player_name": name} if name else None,
            "priced_from_words": words}
# ---- end IC-4


def ros_card(r) -> dict:
    """The player card's `ros` block from a rest-of-season row (mart or on demand)."""
    return {"points": _num(r.get("ros_points")), "games": None if _num(r.get("ros_games")) is None else int(r.get("ros_games")),
            "p10": _num(r.get("ros_p10")), "p90": _num(r.get("ros_p90")),
            "pos_rank": None if _num(r.get("ros_rank_pos")) is None else int(r.get("ros_rank_pos")),
            "playoff_points": _num(r.get("playoff_points")),
            "from_week": None if _num(r.get("from_week")) is None else int(r.get("from_week")),
            "last_week": None if _num(r.get("last_week")) is None else int(r.get("last_week"))}


def ros_on_demand(league_id: str, *, exclude_reference: str | None = None) -> tuple[dict, pd.DataFrame]:
    """(the Sleeper league, rest of season for every projected player in its scoring): the window from this week
    (`cards.decision_week`) to the league's final (`anyleague.ros_window`: the mart's rule, with ceil(log2(playoff
    teams)) rounds since the bracket is not fetched), priced week by week on request."""
    try:
        league_id = A.check_id(league_id)
        league = A.sleeper().league(league_id)
    except A.LeagueNotFound as exc:
        raise NotFound(str(exc)) from exc
    except A.SleeperUnavailable as exc:
        raise SleeperDown(str(exc)) from exc
    season = int(league["season"])
    week = cards.decision_week(season)
    if week is None:
        return league, pd.DataFrame()
    last = query("select max(week) as w from analytics.dim_game where season = %s and season_type = 'REG'", (season,))
    first, last_week, pws = A.ros_window(league, week, int(last["w"].iloc[0]))
    return league, A.ros_table(query, league_id, league, first, last_week, pws, exclude_reference=exclude_reference)


def ros(league_id: str, position: str = "ALL", limit: int = 50, *, view: str = "points", team: int | None = None,
        who: str = "all") -> dict:
    from .applib import ros as ROS
    from .myweek import known_league
    if (view or "points").lower() in SEASON_VIEWS:                                              # ---- II-4
        return season_view(league_id, view.lower(), position, limit, team, who)                  # ---- II-4
    if (view or "points").lower() == "lineup":                                                  # ---- IB-3
        return ros_lineup_view(league_id, team, position, limit, who)                            # ---- IB-3
    if (view or "points").lower() not in VIEWS:                                                 # ---- IB-3
        raise BadView(f"no view {view} (points or lineup)")                                     # ---- IB-3
    position = (position or "ALL").upper()
    if position not in POSITIONS:
        raise NotFound(f"no position {position} (QB, RB, WR, TE, K, DEF or ALL)")
    limit = max(1, min(int(limit), 500))
    if known_league(league_id):
        cols = ", ".join(f"r.{c.strip()}" for c in ROS.ROS_COLUMNS.split(","))
        df = query(ROS_MART_SQL.format(cols=cols), (league_id, position, position, limit))
        head = df.iloc[0] if not df.empty else None
        return {"league_id": league_id, "source": "database", "position": position,
                "from_week": None if head is None else int(head["from_week"]),
                "last_week": None if head is None else int(head["last_week"]),
                "playoff_week_start": None if head is None or _num(head["playoff_week_start"]) is None else int(head["playoff_week_start"]),
                "lines_note": None if head is None else ROS.lines_note(head).replace("his usage", "usage"),   # QA: the betting-line caveat
                "pos_rank_note": POS_RANK_NOTE,
                **ros_more(league_id, None, df, house=True),                                       # ---- IA-3
                "players": ros_rows(league_id, None, df, availability.ros_overlay(                 # ---- IA-3
                    [_ros_player(r) for _, r in df.iterrows()]), house=True)}                      # ---- I0-A
    league, df = ros_on_demand(league_id)
    client = A.sleeper()
    rosters, users = client.rosters(league["league_id"]), client.users(league["league_id"])
    sids = sorted({str(p) for r in rosters for p in (r.get("players") or [])})
    idm = query("select sleeper_id, gsis_id from analytics.player_id_map where sleeper_id = any(%s)", (sids,))
    gsis_of = dict(zip(idm["sleeper_id"], idm["gsis_id"], strict=False)) if not idm.empty else {}
    roster_of = {}
    for r in rosters:
        for p in r.get("players") or []:
            roster_of[gsis_of.get(str(p), str(p))] = int(r["roster_id"])     # a defense's key is its Sleeper id
    names = A.team_names(rosters, users)
    if not df.empty and position != "ALL":
        df = df[df["position"] == position]
    df = df.sort_values(["ros_points", "player_key"], ascending=[False, True]).head(limit) if not df.empty else df
    return {"league_id": str(league["league_id"]), "source": "sleeper", "position": position,
            "from_week": None if df.empty else int(df["from_week"].iloc[0]),
            "last_week": None if df.empty else int(df["last_week"].iloc[0]),
            "playoff_week_start": None if df.empty or df["playoff_week_start"].iloc[0] is None else int(df["playoff_week_start"].iloc[0]),
            "lines_note": None if df.empty else ROS.lines_note(df.iloc[0]).replace("his usage", "usage"),
            "pos_rank_note": POS_RANK_NOTE + "; priced on request from the NFL-wide board (the same population as "
                             "the mart's for a house league: tested)",
            **ros_more(str(league["league_id"]), league, df, house=False),                         # ---- IA-3
            "players": ros_rows(str(league["league_id"]), league, df, availability.ros_overlay(     # ---- IA-3
                [_ros_player(r, roster_of, names) for _, r in df.iterrows()]), house=False)}       # ---- I0-A


# ---- IA-3 (Wave I-A): the rankings' pieces (the stat line per game over the window), "why this number" (the pieces
# x this league's scoring = the points), this week's market line (Sleeper's number, why.market_points), the headshot.
# House league: the window's per-week lines from mart_player_week_projections (the weeks weeks_json counts, so byes
# and the window are the mart's); any other league: anyleague._ros_table's ros_<stat> sums (the same priced frames).
WEEK_LINES_SQL = """select gsis_id, week, proj_targets, proj_receptions, proj_receiving_yards, proj_receiving_tds,
                           proj_carries, proj_rushing_yards, proj_rushing_tds, proj_attempts, proj_passing_yards,
                           proj_passing_tds, proj_passing_interceptions, proj_fumbles_lost
                    from analytics.mart_player_week_projections
                    where league_id = %s and season = %s and week between %s and %s and gsis_id = any(%s)"""
HEADSHOT_SQL = "select gsis_id, headshot_url from analytics.dim_player where gsis_id = any(%s)"
HOUSE_SCORING_SQL = """select season, scoring_settings from analytics.dim_league_season
                       where league_id = %s and is_current_season"""


def _scoring_of(league_id: str, league: dict | None, house: bool) -> tuple[int | None, dict[str, float]]:
    if house:
        r = query(HOUSE_SCORING_SQL, (league_id,))
        if r.empty:
            return None, {}
        sc = r["scoring_settings"].iloc[0] or {}
        return int(r["season"].iloc[0]), {k: float(v) for k, v in sc.items() if v is not None}
    scoring, _ = A.league_scoring(league or {})
    return (int(league["season"]) if league else None), scoring


def _house_lines(league_id: str, season: int, df: pd.DataFrame) -> dict[str, dict]:
    """gsis -> the window's stat line summed over the weeks his rest of season counts (weeks_json's weeks)."""
    from .applib import ros as ROS
    ids = [g for g in df["gsis_id"] if isinstance(g, str) and g]
    if not ids or df.empty:
        return {}
    wk = query(WEEK_LINES_SQL, (league_id, season, int(df["from_week"].min()), int(df["last_week"].max()), ids))
    if wk.empty:
        return {}
    counted = {str(r["gsis_id"]): {w for w, _ in ROS.weeks_list(r)} for _, r in df.iterrows() if isinstance(r["gsis_id"], str)}
    wk = wk[[int(w) in counted.get(str(g), set()) for g, w in zip(wk["gsis_id"], wk["week"], strict=True)]]
    comps = [c for c in wk.columns if c.startswith("proj_")]
    wk = wk.astype({c: float for c in comps}) if comps else wk
    sums = wk.groupby("gsis_id")[comps].sum(min_count=1)
    return {str(g): why.line_of(r) for g, r in sums.to_dict("index").items()}


def _od_lines(df: pd.DataFrame) -> dict[str, dict]:
    """player_key -> the window's stat line from anyleague's ros_<stat> sums."""
    if df.empty or "ros_targets" not in df:
        return {}
    out = {}
    for r in df.to_dict("records"):
        out[str(r["player_key"])] = {stat: _num(r.get(f"ros_{stat}")) for stat in why.STAT_LINE.values()}
    return out


def ros_rows(league_id: str, league: dict | None, df: pd.DataFrame, players: list[dict], *, house: bool) -> list[dict]:
    """Each row + headshot_url, bye_weeks, games-left words, ``per_game`` (the table's columns for his position),
    ``why`` (the pieces of his points per game, then x games = the total) and ``market_points`` (this week's)."""
    if not players:
        return players
    season, scoring = _scoring_of(league_id, league, house)
    try:
        lines = _house_lines(league_id, season, df) if house and season is not None else _od_lines(df)
    except Exception:  # noqa: BLE001 - a mart without the stat-line columns: the list stays, the pieces go
        lines = {}
    ids = [p["gsis_id"] for p in players if p.get("gsis_id")]
    heads = query(HEADSHOT_SQL, (ids,)) if ids else pd.DataFrame()
    head = dict(zip(heads["gsis_id"], heads["headshot_url"], strict=False)) if not heads.empty else {}
    recs = df.to_dict("records") if not df.empty else []
    byes = {str(r["player_key"]): [int(w) for w in (r.get("bye_weeks") or [])] for r in recs}
    week = cards.decision_week(season) if season is not None else None
    from .applib import ros as ROS
    this_week = {str(r["player_key"]): dict(ROS.weeks_list(r)).get(week) for r in recs} if week is not None else {}
    # ---- IE-0: the market line is Sleeper's number: an MFL league shows none (no "not in yet" either)
    market = {} if not A.platforms.is_sleeper(league_id) else why.market_points(season, week, ids, scoring)  # IK-3: Sleeper's only
    for p in players:
        key = p.get("player_key") or p.get("gsis_id")
        g = p.get("ros_games") or 0
        tot = lines.get(str(p.get("gsis_id") if house else key)) or {}
        per = {s: (None if v is None else v / g) for s, v in tot.items()} if g else {}
        ppg = (p["ros_points"] / g) if g and p.get("ros_points") is not None else None
        p["headshot_url"] = _str(head.get(p.get("gsis_id")))
        p["bye_weeks"] = byes.get(str(key), [])
        p["ros_points_per_game"] = None if ppg is None else round(ppg, 2)
        wpos = A.LU.UNIT_PRICES_AS.get(p.get("position"), p.get("position"))      # ---- IC-4: a TMQB's pieces = a QB's
        p["per_game"] = why.columns(per, wpos) if per else {}
        p["why"] = why.explain(per, ppg, scoring, wpos, games=g, total=p.get("ros_points")) if per else None
        p["market_points"] = market.get(str(p.get("gsis_id"))) if p.get("gsis_id") else None
        p["week_points"] = this_week.get(str(key))
        p["market_words"] = why.market_words(p["week_points"], p["market_points"])
    return players


def ros_more(league_id: str, league: dict | None, df: pd.DataFrame, *, house: bool) -> dict:
    """The response's IA-3 keys: the piece columns per position, what the model leans on, the week the market line is
    for, the scoring label the pieces are counted in."""
    season, _ = _scoring_of(league_id, league, house) if not df.empty else (None, {})
    name = (ui.current_leagues().set_index("league_id")["league_name"].get(league_id) if house
            else (league or {}).get("name"))
    from .about import RANKINGS_HOWTO
    return {"piece_columns": {k: list(v) for k, v in why.COLUMNS.items()}, "howto_rankings": RANKINGS_HOWTO,
            "leans_on": why.leans_on(league_id if house else None, name),
            "market_week": cards.decision_week(season) if season is not None else None,
            "market_note": (None if not A.platforms.is_sleeper(league_id) else  # IK-3: was is_mfl                    # ---- IE-0: Sleeper's only
                            "Sleeper's number is this week's, in this league's scoring, where Sleeper has one; "
                            "the list's totals are ours.")}
# ---- end IA-3


# ---- IB-3 (Wave I-B): "Value to my lineup" — the rest-of-season list ranked by what each player is worth to ONE roster's
# best lineup over the weeks left (GET /api/ros?view=lineup&team=). The trade engine's rest-of-season board
# (decisions.window_board(ctx, "ros"): every roster's rows week by week — the next four from the lineup horizon, the
# weeks after from the rest-of-season board; byes, the IR slot, NFL injured reserve as there), solved per week with the
# waiver engine's machinery (waivers.prepare / entry_bar / _what_if on lineup.solve's matching):
#   * one of yours: what your lineup loses without him, week by week (his margin over the next-best who would take
#     his place) — a backup QB behind a healthy starter in a one-QB league is 0 every week but his starter's bye;
#   * anyone else (a free agent, or a player on another roster): what he would add, week by week, if he were on your
#     roster (max(0, his value − the entry bar of the slots he can play): nobody dropped — a bench spot is assumed;
#     a free agent's weeks are his rest-of-season projection, Out this week / injured reserve as the overlay says).
# The sum is `lineup_points`; `lineup_weeks` counts the weeks he starts (or would); `lineup_why` says it in a line.
VIEWS = ("points", "lineup")
WHO = ("all", "mine", "fa", "others")
UNPLAYABLE_NOW = frozenset({"OUT", "DOUBTFUL", "IR", "PUP", "SUSPENDED", "INACTIVE"})


class BadView(ValueError):
    """A view / team the lineup view cannot answer (400)."""


def _weeks_words(ws: list[int]) -> str:
    return f"week {ws[0]}" if len(ws) == 1 else "weeks " + ", ".join(str(w) for w in ws[:-1]) + f" and {ws[-1]}"


def lineup_why(kind: str, pos: str | None, starts: list[int], n: int, pts: float, *, team_name: str | None = None,
               starter: str | None = None, one_qb: bool = True) -> str:
    """One line: why he ranks where he does for this roster (`starter`: the QB who starts for you, in a one-QB league)."""
    k = len(starts)
    p = f"{pts:.0f}" if pts >= 9.5 else f"{pts:.1f}"
    pos_w = UNIT_WORDS.get(pos or "", pos)                                       # ---- IC-4: "team QB", not TMQB
    if kind == "mine":
        if k == 0:
            if pos == "QB" and starter and one_qb:
                return f"Your backup QB never starts for you behind {starter}: he adds nothing to your lineup (insurance only)."
            return f"On your bench in all {n} weeks left: he adds nothing to your lineup unless someone gets hurt."
        nothing = pts < 0.05
        if k <= 3 and k < n:
            role = "QB2" if pos == "QB" and one_qb else f"bench {pos_w}"
            if nothing:
                return (f"Your {role} only plays in {_weeks_words(starts)}, and the best free agent would score as much "
                        "then: he adds nothing to your lineup.")
            return f"Your {role} only plays in {_weeks_words(starts)}: {p} points over your next-best there."
        every = f"all {n} weeks left" if k == n else f"{k} of {n} weeks left"
        if nothing:
            return (f"Starts for you in {every}, but the best free agent at {pos_w} projects as much: he adds nothing over "
                    "the waiver wire.")
        return f"Starts for you in {every}: {p} points more than your next-best option."
    where = "Free agent" if kind == "fa" else f"On {team_name or 'another team'}"
    if k == 0 or pts < 0.05:
        return f"{where}: would not crack your lineup in any week left (your starters project more)."
    every = f"all {n} weeks left" if k == n else f"{k} of {n} weeks left"
    return f"{where}: would start for you in {every}, +{p} points to your lineup."


def lineup_values(league_id: str, team: int, frame: pd.DataFrame, *, house: bool) -> tuple[dict[str, dict], dict]:
    """player_key -> {lineup_points, lineup_weeks, kind, lineup_why} for every row of a rest-of-season frame, and the
    window ({first, last, weeks}). `frame`: player_key, gsis_id, position, (rostered_by_roster_id), weeks_json /
    ros_weeks' weeks."""
    from league_lab import waivers as W

    from . import decisions as D
    ctx = D.trade_context(league_id, None if house else "sleeper")
    me = int(team)
    if me not in ctx.board.rosters:
        raise NotFound(f"no team {team} in league {league_id}")
    board, weeks, span = D.window_board(ctx, "ros")
    rw = D.ros_weeks(ctx)
    preps = [W.prepare(board.pool(me, w), board.slots) for w in weeks]
    bars: list[dict] = [{} for _ in weeks]
    sid_of = {}
    for r in ctx.horizon[["sleeper_player_id", "gsis_id"]].dropna().itertuples():
        sid_of[str(r.gsis_id)] = str(r.sleeper_player_id)
    # the QB who starts most weeks for me (the backup's sentence)
    qb_starts: dict[str, int] = {}
    for pr in preps:
        for st in pr.lineup.starts:
            if st.player is not None and st.player.position == "QB":
                qb_starts[st.player.id] = qb_starts.get(st.player.id, 0) + 1
    top_qb = max(qb_starts, key=qb_starts.get) if qb_starts else None
    one_qb = sum(1 for x in board.slots if str(x).upper() in ("QB", "SUPER_FLEX")) == 1
    # the best free agent per position and week (rest-of-season board): who would fill the slot one of yours leaves
    # empty (a lone kicker or defense is worth his edge over the waiver wire, not his whole projection)
    pos_of = {}
    try:
        rf = D._ros_frame(ctx.league_id, ctx.is_house)
        pos_of = dict(zip(rf["player_key"].astype(str), rf["position"], strict=True)) if not rf.empty else {}
    except Exception:  # noqa: BLE001 - no positions: no replacement (the margin over the bench alone)
        pos_of = {}
    owned_keys = {str(g) for g, sd in sid_of.items() if board.owner(sd) is not None} | {
        str(k) for k in pos_of if board.owner(str(k)) is not None}
    repl: dict[tuple[str, int], float] = {}
    for k, wk in rw["weeks"].items():
        ps = pos_of.get(str(k))
        if ps is None or str(k) in owned_keys:
            continue
        for w, v in wk.items():
            if v is not None and v > repl.get((ps, int(w)), 0.0):
                repl[(ps, int(w))] = float(v)
    out: dict[str, dict] = {}
    status = {}
    if "injury_status" in frame:
        status = {str(k): str(v).upper() for k, v in zip(frame["player_key"], frame["injury_status"], strict=True) if isinstance(v, str)}
    for r in frame.to_dict("records"):
        key = str(r["player_key"])
        gs = r.get("gsis_id") if isinstance(r.get("gsis_id"), str) else None
        sid = sid_of.get(gs, key) if gs else key
        owner = board.owner(sid)
        pos = r.get("position")
        per: list[float] = []
        starts: list[int] = []
        cover: list[float | None] = []                                           # ---- II-4: bench weeks' edge
        if owner == me:
            kind = "mine"
            for w, pr in zip(weeks, preps, strict=True):
                if sid in pr.index:
                    without, _ = W._what_if(pr, None, sid)
                    rv = repl.get((str(pos), int(w)))
                    if rv:
                        fill = W._norm(Player(id="__replacement__", position=pos, value=rv, value_source="proj_points"))
                        without = max(without, W._what_if(pr, fill, sid)[0])
                    loss = max(0.0, pr.total - without)
                    if sid not in pr.starters:                                   # ---- II-4
                        mv = float(pr.vals[pr.index[sid]])                       # ---- II-4
                        cover.append(None if rv is None or not np.isfinite(mv) else max(0.0, mv - float(rv)))  # II-4
                else:
                    loss = 0.0
                per.append(loss)
                if sid in pr.starters:
                    starts.append(w)
        else:
            kind = "others" if owner is not None else "fa"
            st = status.get(key, "")
            by_week = rw["weeks"].get(gs or key, {}) if owner is None else {}
            for h, (w, pr) in enumerate(zip(weeks, preps, strict=True)):
                if owner is not None:
                    row = board.row(sid, w)
                    p = incoming(row)
                else:
                    v = by_week.get(w)
                    out_now = (h == 0 and st in UNPLAYABLE_NOW) or st in {"IR", "PUP", "SUSPENDED"}
                    p = None if v is None or out_now else Player(id=sid, position=pos, value=float(v), value_source="proj_points")
                if p is None or p.value is None or p.value_source == UNVALUED:
                    per.append(0.0)
                    continue
                c = bars[h]
                if p.positions not in c:
                    c[p.positions] = W.entry_bar(pr, p.positions)
                bar = c[p.positions]
                g = 0.0 if bar is None else max(0.0, float(p.value) - bar)
                per.append(g)
                if g > 0.004:
                    starts.append(w)
        pts = round(sum(per), 2)
        team_name = ctx.team(owner) if owner is not None and owner != me else None
        starter = None
        if kind == "mine" and pos == "QB" and top_qb and top_qb != sid:
            starter = cards.last_name(ctx.name(top_qb))
        out[key] = {"lineup_points": pts, "lineup_weeks": len(starts), "lineup_kind": kind,
                    "lineup_why": lineup_why(kind, pos, starts, len(weeks), pts, team_name=team_name, starter=starter,
                                             one_qb=one_qb)}
        out[key].update({"lineup_start_weeks": [int(w) for w in starts], "lineup_sid": sid,               # ---- II-4
                         "lineup_owner": None if owner is None else int(owner),                           # ---- II-4
                         "cover": cover_of(pos, cover) if kind == "mine" else None})                      # ---- II-4
    return out, {"first": weeks[0], "last": weeks[-1], "weeks": len(weeks), "span": span}


def incoming(row):
    from league_lab.roster_value import incoming_player
    return incoming_player(row) if row is not None else None


def ros_lineup_view(league_id: str, team: int | None, position: str = "ALL", limit: int = 50, who: str = "all", *,
                    kinds: frozenset[str] | None = None) -> dict:                                 # ---- II-4: kinds
    """GET /api/ros?view=lineup&team=: the rest-of-season answer, its rows ranked by `lineup_points` for the team."""
    from .applib import ros as ROS
    from .myweek import known_league
    if team is None:
        raise BadView("pick your team: the lineup view ranks players for one roster")
    who = (who or "all").lower()
    if who not in WHO:
        raise BadView(f"no who={who} (all, mine, fa or others)")
    position = (position or "ALL").upper()
    if position not in POSITIONS:
        raise NotFound(f"no position {position} (QB, RB, WR, TE, K, DEF or ALL)")
    limit = max(1, min(int(limit), 500))
    house = known_league(league_id)
    if house:
        cols = ", ".join(f"r.{c.strip()}" for c in ROS.ROS_COLUMNS.split(","))
        df = query(ROS_MART_SQL.format(cols=cols), (league_id, position, position, 5000))
        league = None
        players = [_ros_player(r) for _, r in df.iterrows()]
    else:
        league, df = ros_on_demand(league_id)
        client = A.sleeper()
        rosters, users = client.rosters(league["league_id"]), client.users(league["league_id"])
        sids = sorted({str(p) for r in rosters for p in (r.get("players") or [])})
        idm = query("select sleeper_id, gsis_id from analytics.player_id_map where sleeper_id = any(%s)", (sids,))
        gsis_of = dict(zip(idm["sleeper_id"], idm["gsis_id"], strict=False)) if not idm.empty else {}
        roster_of = {gsis_of.get(str(p), str(p)): int(r["roster_id"]) for r in rosters for p in (r.get("players") or [])}
        names = A.team_names(rosters, users)
        if not df.empty and position != "ALL":
            df = df[df["position"] == position]
        df = df.sort_values(["ros_points", "player_key"], ascending=[False, True]) if not df.empty else df
        players = [_ros_player(r, roster_of, names) for _, r in df.iterrows()]
    head = df.iloc[0] if not df.empty else None
    players = availability.ros_overlay(players)
    frame = pd.DataFrame([{"player_key": p.get("player_key") or p.get("gsis_id"), "gsis_id": p.get("gsis_id"),
                           "position": p.get("position"), "injury_status": p.get("injury_status")} for p in players])
    vals, window = lineup_values(str(league["league_id"]) if league else league_id, int(team), frame, house=house) \
        if not frame.empty else ({}, {"first": None, "last": None, "weeks": 0, "span": None})
    for p in players:
        p.update(vals.get(str(p.get("player_key") or p.get("gsis_id")), {"lineup_points": None, "lineup_weeks": None,
                                                                           "lineup_kind": None, "lineup_why": None}))
    if kinds is not None:                                                                        # ---- II-4
        players = [p for p in players if p.get("lineup_kind") in kinds]                          # ---- II-4
    elif who != "all":
        players = [p for p in players if p.get("lineup_kind") == who]
    # value first; among equals (a starter a free agent could replace is worth 0 too) the one who starts more weeks,
    # then the rest-of-season points
    order = sorted(range(len(players)), key=lambda i: (-round(players[i].get("lineup_points") or 0.0, 2),
                                                       -(players[i].get("lineup_weeks") or 0),
                                                       -(players[i].get("ros_points") or 0.0), i))
    for rank, i in enumerate(order, start=1):
        players[i]["lineup_rank"] = rank
    keep = [players[i] for i in order[:limit]]
    keys = {str(p.get("player_key") or p.get("gsis_id")) for p in keep}
    sub = df[[str(k) in keys for k in df["player_key"]]] if not df.empty else df
    keep = ros_rows(str(league["league_id"]) if league else league_id, league, sub, keep, house=house)
    return {"league_id": str(league["league_id"]) if league else league_id, "source": "database" if house else "sleeper",
            "position": position, "view": "lineup", "team": int(team), "who": who,
            "from_week": None if head is None else int(head["from_week"]),
            "last_week": None if head is None else int(head["last_week"]),
            "playoff_week_start": None if head is None or _num(head["playoff_week_start"]) is None else int(head["playoff_week_start"]),
            "lines_note": None if head is None else ROS.lines_note(head).replace("his usage", "usage"),
            "pos_rank_note": POS_RANK_NOTE, "window": window, "lineup_note": LINEUP_NOTE,
            **ros_more(str(league["league_id"]) if league else league_id, league, sub, house=house),
            "players": keep}


LINEUP_NOTE = ("Value to your lineup: what each player adds to your best lineup over the weeks left, week by week. "
               "For one of yours, what your lineup loses without him (his edge over the next-best who would start "
               "instead); for anyone else, what he would add if he were on your roster, nobody dropped. A backup "
               "who never starts adds nothing, however many points he scores somewhere else.")
# ---- end IB-3


# ---- II-4 (Wave I-I; the product and analytics review § 6): Season's three named views, each with its counterfactual
# stated — the arithmetic is IB-3's and F2's, unchanged (no number moves; only the labels and the split):
#   * `outlook`  — My roster outlook (the default with a team): your players only; what your best lineup loses without
#     each one (his edge over whoever would start instead: your next-best, or the best free agent at his position).
#     Contingent injury cover (`cover`) is apart and never added to that number.
#   * `upgrades` — Potential upgrades, before acquisition cost: everyone else; what he would add to your best lineup if
#     he were on your roster with nobody dropped and nothing sent. Never trade value: a free agent leads to the add /
#     drop comparison (Waivers), a rostered player to the trade calculator (what you send is subtracted there).
#   * `projections` — Rest-of-season projections: the research ranking (points, per game, games, range, playoffs).
# `lineup` / `points` stay as they were (old links, pinned tests). docs/METRICS.md § "Value to my lineup" → "The three
# views"; INTERFACES.md § II-4.
SEASON_VIEWS = ("outlook", "upgrades", "projections")
SEASON_LABELS = {"outlook": "My roster outlook", "upgrades": "Potential upgrades",
                 "projections": "Rest-of-season projections"}
COUNTERFACTUAL = {
    "outlook": ("Your players only. Each number is what your best lineup loses over the weeks left without him: his "
                "edge over whoever would start instead (your next-best player, or the best free agent at his "
                "position). A reserve who never starts adds nothing here; his injury cover is shown apart and is not "
                "added in."),
    "upgrades": ("Before acquisition cost: what each player would add to your best lineup over the weeks left if he were "
                 "on your roster, with nobody dropped and nothing sent. A free agent costs a roster spot (the add / "
                 "drop on Waivers prices it); a player on another team costs what you send (the trade calculator "
                 "subtracts it). This is not his trade value."),
    "projections": ("Projected points in this league's scoring over the weeks left, whoever rosters him: no roster, "
                    "no lineup and no cost considered."),
}
COSTS_INCLUDED = {"outlook": ["the player who would start in his place (your next-best, or the best free agent)"],
                  "upgrades": [], "projections": []}
COSTS_NOT_INCLUDED = {"outlook": [],
                      "upgrades": ["the drop a free agent needs", "the players a trade sends",
                                   "a waiver claim that might be lost"],
                      "projections": ["your roster", "your lineup", "any acquisition cost"]}
UPGRADE_WHO = {"all": frozenset({"fa", "others"}), "fa": frozenset({"fa"}), "others": frozenset({"others"})}


def cover_of(pos: str | None, bench_edges: list[float | None]) -> dict | None:
    """Contingent injury cover for one of yours (his bench weeks: his projection over the best free agent at his
    position that week, averaged per week) — what he is worth if a starter there misses time. None: he starts every
    week, or no free-agent bar is known for any of his bench weeks (unknown is not zero)."""
    known = [e for e in bench_edges if e is not None]
    if not known:
        return None
    pw = round(sum(known) / len(known), 2)
    pos_w = UNIT_WORDS.get(pos or "", pos or "his position")
    if pw < 0.05:
        words = (f"Injury cover: none over the waiver wire — the best free agent at {pos_w} projects as much in his "
                 f"{len(known)} bench week{'s' if len(known) != 1 else ''}.")
    else:
        p = f"{pw:.1f}"
        words = (f"Injury cover: if a starting {pos_w} misses a week, he projects +{p} per week over the best free agent "
                 f"({len(known)} bench week{'s' if len(known) != 1 else ''}; not counted in his value above).")
    return {"points": pw, "weeks": len(known), "words": words}


def acquire_of(p: dict, league_id: str) -> dict | None:
    """Where a potential upgrade leads: a free agent → the add / drop comparison on Waivers; a rostered player → the
    trade calculator with him asked for (what you send and any drop subtracted there)."""
    sid, owner = p.get("lineup_sid"), p.get("lineup_owner")
    if not sid:
        return None
    if p.get("lineup_kind") == "fa":
        return {"kind": "add_drop", "words": "Free agent: compare the add / drop on Waivers (the drop is the cost)",
                "path": f"/waivers?add={sid}"}
    if p.get("lineup_kind") == "others" and owner is not None:
        return {"kind": "trade", "words": f"On {p.get('rostered_by_team') or 'another team'}: price a trade (what you "
                                          "send is subtracted)",
                "path": f"/trade-calc?partner={int(owner)}&get={sid}"}
    return None


def season_view(league_id: str, view: str, position: str = "ALL", limit: int = 50, team: int | None = None,
                who: str = "all") -> dict:
    """GET /api/ros?view=outlook|upgrades|projections — the three named Season views (same numbers as before)."""
    view = view.lower()
    if view == "projections":
        out = ros(league_id, position, limit, view="points", team=team, who=who)
        for p in out.get("players") or []:
            pts, g = p.get("ros_points"), p.get("ros_games")
            p["ros_per_game"] = round(pts / g, 1) if pts is not None and g else None
    elif view == "outlook":
        if team is None:
            raise BadView("pick your team: My roster outlook is one roster's")
        out = ros_lineup_view(league_id, team, position, limit, "mine")
    else:
        if team is None:
            raise BadView("pick your team: Potential upgrades are measured against one roster's lineup")
        w = (who or "all").lower()
        if w not in UPGRADE_WHO:
            raise BadView(f"no who={who} (all, fa or others)")
        out = ros_lineup_view(league_id, team, position, limit, "all", kinds=UPGRADE_WHO[w])
        out["who"] = w
        for p in out.get("players") or []:
            p["acquire"] = acquire_of(p, league_id)
    out["view"] = view
    out["season_view"] = {"key": view, "label": SEASON_LABELS[view], "counterfactual": COUNTERFACTUAL[view],
                          "costs_included": COSTS_INCLUDED[view], "costs_not_included": COSTS_NOT_INCLUDED[view]}
    return out
# ---- end II-4


# ---------------------------------------------------------------- plan F3: our record (house leagues)
RECORD_SQL = """select * from analytics.mart_projection_record where league_id = %s and season = %s
                order by scope, week, position"""
RECORD_WHY = "we keep the record for the leagues we score every morning; yours is not one of them yet"


# ---- V-1 (Wave I-G): the decision record on /api/record — what the app's lineups would have added, the regret, the
# close calls' calibration, the news-affected cases (league_lab.validation.summary over the two dbt marts;
# docs/METRICS.md § "The decision record"; INTERFACES.md § V-1). Unavailable (never an error) before the marts exist.
# `record()` gains the `decisions` key through `_with_decisions` (a wrapper, so this block never touches the lines
# M4's `pricing` block changed: the two merge cleanly in either order).
DECISIONS_SQL = """select * from analytics.mart_decision_record where league_id = %s and season = %s
                   order by week, roster_id"""
DECISION_CALLS_SQL = """select * from analytics.mart_decision_calls where league_id = %s and season = %s
                        order by week, roster_id, call_rank"""


def record_decisions(league_id: str, season: int, team: int | None = None) -> dict:
    from league_lab import validation as V

    from .db import missing_relations
    if missing_relations(("mart_decision_record", "mart_decision_calls")):
        return {"available": False, "season": season, "why": "the decision record is not built here yet"}
    try:
        rw = query(DECISIONS_SQL, (league_id, season))
        calls = query(DECISION_CALLS_SQL, (league_id, season))
    except Exception:  # noqa: BLE001 - a mart from an older build: say so, never fail the record
        return {"available": False, "season": season, "why": "the decision record could not be read"}
    for c in ("submitted_points", "app_points", "optimum_points", "regret", "app_edge", "app_regret",
              "market_points", "market_edge"):                                                  # ---- V-2: market
        if c in rw:
            rw[c] = pd.to_numeric(rw[c], errors="coerce")
    for c in ("p_win", "outcome", "starter_points", "alt_points", "value", "alt_value", "margin"):
        if c in calls:
            calls[c] = pd.to_numeric(calls[c], errors="coerce")
    rw = V.apply_news(rw, event_news(league_id, season))                                         # ---- V-2
    out = {"season": season, **V.summary(rw, calls)}
    out["team"] = decisions_team(rw, calls, team)                                                # ---- V-2
    return out


def _with_decisions(fn):
    """``record``'s answer + ``decisions`` for a league we keep the record for (``available``); V-2: + an MFL league's
    record (graded from MFL's results) and ``decisions.team`` when a team is asked."""
    @functools.wraps(fn)
    def wrapped(league_id: str, team: int | None = None) -> dict:
        out = fn(league_id)
        if out.get("available") and out.get("season") is not None:
            out["decisions"] = record_decisions(out["league_id"], int(out["season"]), team)
        elif A.platforms.is_mfl(out.get("league_id") or "") and "results" in out:                # ---- V-2
            out["decisions"] = mfl_decisions(out["league_id"], team)
        return out
    return wrapped
# ---- end V-1


# ---- V-2 (Wave I-H): the decision record, personal and live (INTERFACES.md § V-2; docs/METRICS.md § "The decision
# record" → "Personal and live"): the event store's news flag on the request side (the store lives on the hosted copy,
# the marts are built where it is not), one team's view (`/api/record?league=&team=` -> `decisions.team`), and an MFL
# league's record graded from MFL's own results (its rows in ops.lineup_record are written by `league-lab validate`
# for the keys in LEAGUE_LAB_RECORD_MFL).
KICKOFF_STARTERS_SQL = """select league_id, season, week, roster_id, record_source, run_at, first_kickoff_at, gsis_id,
                                 report_status
                          from ops.lineup_record where league_id = %s and season = %s and role = 'starter'
                            and record_source = 'kickoff' and gsis_id is not null"""
EVENTS_KICKOFF_SQL = """select f.week, f.gsis_id, min(g.kickoff_at) as kickoff_at
                        from analytics.mart_player_week_features as f
                        join analytics.dim_game as g on g.season = f.season and g.week = f.week and g.season_type = 'REG'
                         and f.team in (g.home_team, g.away_team)
                        where f.season = %s and f.gsis_id = any(%s) group by 1, 2"""
MFL_RECORD_SQL = """select league_id, season, week, roster_id, record_source, run_at, first_kickoff_at, model_version,
                           pricing, role, slot, sleeper_player_id, gsis_id, player_name, position, value, margin,
                           report_status, lineup_value, call_rank, alt_sleeper_player_id, alt_gsis_id, alt_player_name,
                           alt_value, p_win, is_coin_flip
                    from ops.lineup_record where league_id = %s and season = %s and role = 'starter'"""
MFL_NO_RECORD = "we have not kept a lineup record for this league yet"


def event_news(league_id: str, season: int) -> dict[tuple[str, int, int], int]:
    """(league, week, roster) -> news-affected starters where the event store answers (``validation.news_overrides``);
    {} when the store is off, missing or unreadable — the marts' report rule stands (never an error)."""
    from league_lab import validation as V

    from . import events as EV
    if not EV.enabled():
        return {}
    try:
        rec = query(KICKOFF_STARTERS_SQL, (league_id, int(season)))
        if rec.empty:
            return {}
        gsis = sorted({g for g in rec["gsis_id"] if isinstance(g, str)})
        ev = query(V.EVENTS_SQL, (gsis,), ttl=60)
        sp = query(V.EVENTS_SPAN_SQL, (), ttl=60)
        kick = query(EVENTS_KICKOFF_SQL, (int(season), gsis))
    except Exception:  # noqa: BLE001 - the store is a nicety here
        return {}
    span = None if sp.empty or pd.isna(sp.iloc[0]["first"]) else (sp.iloc[0]["first"], sp.iloc[0]["last"])
    return V.news_overrides(rec, ev, kick, span)


def decisions_team(rw: pd.DataFrame, calls: pd.DataFrame, team: int | None, team_name: str | None = None) -> dict | None:
    """``decisions.team`` (None when no team is asked)."""
    from league_lab import validation as V
    if team is None:
        return None
    if team_name is None and not rw.empty and "team_name" in rw:
        names = rw.loc[pd.to_numeric(rw["roster_id"]) == int(team), "team_name"].dropna()
        team_name = str(names.iloc[0]) if len(names) else None
    return V.team_summary(rw, calls, int(team), team_name)


def mfl_decisions(league_id: str, team: int | None = None) -> dict:
    """An MFL league's decision record: its ops.lineup_record rows graded from MFL's weeklyResults
    (``record_mfl.mfl_load``); unavailable (never an error) without rows or when MFL cannot answer."""
    from league_lab import validation as V
    try:
        cl = A.sleeper()
        season = int(cl.league(league_id)["season"])
        rec = query(MFL_RECORD_SQL, (league_id, season))
    except Exception:  # noqa: BLE001 - no table yet / MFL down: the record is simply not there
        return {"available": False, "platform": "mfl", "why": MFL_NO_RECORD}
    if rec.empty:
        return {"available": False, "platform": "mfl", "season": season, "why": MFL_NO_RECORD}
    for c in ("value", "margin", "alt_value", "p_win", "lineup_value"):
        rec[c] = pd.to_numeric(rec[c], errors="coerce")
    try:
        from league_lab.record_mfl import mfl_load
        g = mfl_load(league_id, rec, router=cl)
    except Exception:  # noqa: BLE001 - MFL down / busy: say so, never fail the record
        return {"available": False, "platform": "mfl", "season": season, "why": "MyFantasyLeague did not answer"}
    rw, calls = V.grade_roster_weeks(g), V.grade_calls(g)
    rw = V.apply_news(rw, event_news(league_id, season))          # the event store answers for MFL starters too
    names = {int(k): v.get("team_name") for k, v in A.team_names(cl.rosters(league_id), cl.users(league_id)).items()}
    rw["team_name"] = [names.get(int(r)) for r in rw["roster_id"]] if not rw.empty else []
    out = {"season": season, "platform": "mfl", **V.summary(rw, calls)}
    out["team"] = decisions_team(rw, calls, team, names.get(int(team)) if team is not None else None)
    return out
# ---- end V-2


@_with_decisions                                                     # ---- V-1 (Wave I-G)
def record(league_id: str) -> dict:
    from .db import missing_relations
    from .myweek import known_league, league_row
    try:
        league_id = A.check_id(league_id)
    except A.LeagueNotFound as exc:
        raise NotFound(str(exc)) from exc
    if not known_league(league_id):
        try:
            A.sleeper().league(league_id)             # 404 for an id Sleeper does not have (the contract)
        except A.LeagueNotFound as exc:
            raise NotFound(str(exc) if not A.platforms.is_sleeper(league_id) else f"no Sleeper league {league_id}") from exc  # IK-3
        except A.SleeperUnavailable:
            pass                                      # Sleeper down: still an honest "not kept" answer
        if A.platforms.is_mfl(league_id):             # ---- IC-4: the league's own results, both games of a double header
            return {"league_id": league_id, "available": False, "why": RECORD_WHY, **mfl_results(league_id)}
        return {"league_id": league_id, "available": False, "why": RECORD_WHY}
    season = int(league_row(league_id)["season"])
    rec = query(RECORD_SQL, (league_id, season)) if not missing_relations(("mart_projection_record",)) else pd.DataFrame()
    weeks = rec[rec["scope"] == "week"] if not rec.empty else rec
    season_rows = rec[rec["scope"] == "season"] if not rec.empty else rec

    def row(r) -> dict:
        return dict(r)                     # main.clean() makes it JSON (NaN -> null, timestamps -> ISO)

    allr = season_rows[season_rows["position"] == "ALL"] if not season_rows.empty else season_rows
    summary = None
    if not season_rows.empty:
        summary = row(allr.iloc[0].to_dict()) if not allr.empty else {}
        summary["by_position"] = [row(r.to_dict()) for _, r in season_rows[season_rows["position"] != "ALL"].iterrows()]
    first = None if weeks.empty else int(weeks["week"].min())
    out = {"league_id": league_id, "available": True, "season": season, "from_week": first,
           "weeks": [row(r.to_dict()) for _, r in weeks.iterrows()], "summary": summary,
           "notice": None if not rec.empty else ("No week on the record yet: the record starts the first week Sleeper's "
                                                "projections are archived before kickoff.")}
    out.update(record_pricing(league_id, season, out["weeks"]))       # ---- M4 (Wave I-G)
    return out


# ---- M4 (Wave I-G): the record says how each week was priced, and the request side prices as the record does.
# `scoring.ev_pricing()` is a mode (the env overrides; else the newest build's `pricing` in ops.projections), read here
# through this API's read-only query (INTERFACES.md § M4; docs/METRICS.md § "The record's pricing column").
def _pricing_rows():
    return query(S.RECORD_PRICING_SQL, (), ttl=60)


S.set_record_reader(_pricing_rows)

def record_pricing(league_id: str, season: int, weeks: list[dict]) -> dict:
    """``pricing`` on every week row (the mart's label: flat / ev / mixed; NULL or a mart without the column = flat)
    and the answer's ``pricing`` block: ``now`` (this league's newest build), ``by_week``, ``sentence``."""
    by_week: dict[int, set] = {}
    for w in weeks:
        lab = w.get("pricing")
        lab = lab if isinstance(lab, str) and lab in ("flat", "ev", "mixed") else "flat"
        w["pricing"] = lab
        by_week.setdefault(int(w["week"]), set()).add(lab)
    labels = {wk: (next(iter(s)) if len(s) == 1 else "mixed") for wk, s in by_week.items()}
    try:
        df = query(S.LEAGUE_PRICING_SQL, (league_id, league_id))
        now = "ev" if (not df.empty and bool(df.iloc[0]["ev"])) else "flat"
    except Exception:  # noqa: BLE001 - no column yet (before the first I-G nightly): flat, as every row then was
        now = "flat"
    return {"pricing": {"now": now, "by_week": {str(k): v for k, v in sorted(labels.items())},
                        "sentence": S.record_pricing_sentence(labels, now)}}
# ---- end M4


# ---- IC-4 (Wave I-D): an MFL league's results on /api/record. We keep no projection record for a league we do not price
# every night, but its own results are MFL's: every played week's games from the schedule (MFL's weeklyResults carry
# the same scores), each game once — two per team in a double-header week — and each team's record from them.
def mfl_results(league_id: str) -> dict:
    from .decisions import week_matchups
    try:
        cl = A.sleeper()
        lg = cl.league(league_id)
        last = int((lg.get("settings") or {}).get("last_scored_leg") or 0)
        names = A.team_names(cl.rosters(league_id), cl.users(league_id))
        weeks = cl.season_matchups(league_id, last) if last > 0 else {}
    except (A.LeagueNotFound, A.SleeperUnavailable, A.SleeperBusy):
        return {"results": [], "records": []}
    results = [m for w in sorted(weeks) if (m := week_matchups(w, weeks[w], names, played=True)) is not None]
    rec: dict[int, dict] = {}
    for m in results:
        for g in m["games"]:
            for sd in (g["a"], g["b"]):
                r = rec.setdefault(sd["roster_id"], {"roster_id": sd["roster_id"], "team_name": sd["team_name"],
                                                     "wins": 0, "losses": 0, "ties": 0, "games": 0})
                r["games"] += 1
                r[{"W": "wins", "L": "losses", "T": "ties"}[sd["result"]]] += 1
    return {"results": results, "records": sorted(rec.values(), key=lambda r: (-r["wins"], r["losses"], r["roster_id"])),
            "results_note": ("MyFantasyLeague's own results, week by week: each game once, two for every team in a "
                             "double-header week.")}
# ---- end IC-4


# ---------------------------------------------------------------- plan F3: the player card for any league
class PlayerContext:
    """What `player.player_card(od=...)` needs for a league the database does not have: the league's name and
    season, a house league whose marts carry the NFL-wide columns (usage, injury report, role alerts), this league's
    rosters (whose team he is on), his projection and range priced in this league's scoring, his rest of season,
    and the on-demand lineup of the team that has him."""

    def __init__(self, league_id: str, *, exclude_reference: str | None = None) -> None:
        try:
            self.league_id = A.check_id(league_id)
            self.client = A.sleeper()
            self.league = self.client.league(self.league_id)
            self.rosters, self.users = self.client.rosters(self.league_id), self.client.users(self.league_id)
        except A.LeagueNotFound as exc:
            raise NotFound(str(exc)) from exc
        except A.SleeperUnavailable as exc:
            raise SleeperDown(str(exc)) from exc
        self.season = int(self.league["season"])
        self.league_name = str(self.league.get("name") or f"League {self.league_id}")
        cur = ui.current_leagues()
        self.profile_league = str(cur["league_id"].iloc[0]) if not cur.empty else None
        self.scoring, self.slots = A.league_scoring(self.league)
        self.exclude_reference = exclude_reference
        self.names = A.team_names(self.rosters, self.users)
        self._reference: str | None = None
        self._ros: pd.DataFrame | None = None

    def _sleeper_id(self, gsis: str) -> str:
        m = query("select sleeper_id from analytics.player_id_map where gsis_id = %s", (gsis,))
        return str(m["sleeper_id"].iloc[0]) if not m.empty and m["sleeper_id"].iloc[0] else str(gsis)

    def availability(self, gsis: str) -> dict:
        sid = self._sleeper_id(gsis)
        for r in self.rosters:
            if sid in [str(x) for x in (r.get("players") or [])]:
                rid = int(r["roster_id"])
                n = self.names.get(rid, {})
                return {"rostered_by_roster_id": rid, "rostered_by_team": n.get("team_name"),
                        "rostered_by_manager": n.get("manager_name"), "is_free_agent": False,
                        "is_current_starter": sid in [str(x) for x in (r.get("starters") or [])],
                        "is_on_ir": sid in [str(x) for x in (r.get("reserve") or [])]}
        return {"rostered_by_roster_id": None, "rostered_by_team": None, "rostered_by_manager": None,
                "is_free_agent": True, "is_current_starter": False, "is_on_ir": False}

    def projection(self, gsis: str, position: str, week: int | None) -> pd.DataFrame:
        """PROJ_SQL's columns for this league: the stat line priced in its scoring, the range from the reference
        (docs/ANY_LEAGUE.md § The ranges), the opponent from the schedule."""
        cols = ["proj_points", "p10", "p25", "p75", "p90", *A.STAT_LINE, "opponent", "is_home"]
        if week is None:
            return pd.DataFrame(columns=cols)
        pr = A.price_week(query, self.league_id, self.scoring, self.slots, self.season, int(week),
                          exclude_reference=self.exclude_reference)
        self._reference = pr.reference
        row: dict | None = None
        if gsis in pr.proj.index:
            rg = pr.ranges.loc[gsis]
            row = {"proj_points": round(float(pr.proj[gsis]), 2), **{q: rg[q] for q in ("p10", "p25", "p75", "p90")},
                   **pr.board.line.loc[gsis, list(A.STAT_LINE)].to_dict()}
        elif position in pr.kd and gsis in set(pr.kd[position]["unit_id"]):
            k = pr.kd[position].set_index("unit_id").loc[gsis]
            row = {"proj_points": k["proj_points"], "p10": k["p10"], "p25": None, "p75": None, "p90": k["p90"],
                   **dict.fromkeys(A.STAT_LINE)}
        if row is None:
            return pd.DataFrame(columns=cols)
        team = pr.board.status["team"].get(gsis) if "team" in pr.board.status else None
        g = query(A.GAMES_SQL, (self.season, int(week)))
        opp = home = None
        for r in g.itertuples():
            if team == r.home_team:
                opp, home = r.away_team, True
            elif team == r.away_team:
                opp, home = r.home_team, False
        row.update({"opponent": opp, "is_home": home})
        return pd.DataFrame([row], columns=cols)

    def ros(self, gsis: str, position: str) -> pd.DataFrame:
        if self._ros is None:
            _, self._ros = ros_on_demand(self.league_id, exclude_reference=self.exclude_reference)
        df = self._ros
        return df[df["player_key"] == gsis] if not df.empty else df

    def lineup(self, roster_id: int, week: int) -> pd.DataFrame:
        try:                                     # ---- IB-0: the roster's context (the overlay applied), as My Week
            self.context = availability.roster_context(self.league_id, int(roster_id), int(week), house=False,
                                                       client=self.client, exclude_reference=self.exclude_reference)
            return self.context.rows if self.context is not None else pd.DataFrame()
        except A.LeagueNotFound:
            return pd.DataFrame()

    def meta(self) -> dict:
        return {"range_method": A.RANGE_METHOD, "range_reference": self._reference,
                "profile_league": self.profile_league, "scoring_label": A.scoring_label(self.league)}


def player_card(league_id: str, gsis: str, *, exclude_reference: str | None = None) -> dict:
    from . import player
    if A.platforms.is_mfl(league_id) and A.platforms.is_mfl(gsis):          # ---- IC-4: a team unit's card
        return unit_card(league_id, gsis, exclude_reference=exclude_reference)
    return player.player_card(league_id, gsis, od=PlayerContext(league_id, exclude_reference=exclude_reference))


# ---- IC-4 (Wave I-D): a team unit (`mfl:0656`, `mfl:TMQB-KC`) answers with its starter's card — the quarterback (kicker)
# whose line prices the unit this week (the rest of season's decision week) — named as the unit, with the unit's roster
def unit_card(league_id: str, key: str, *, exclude_reference: str | None = None) -> dict:
    from . import player
    ctx = PlayerContext(league_id, exclude_reference=exclude_reference)
    row = ctx.client.players().get(key) or {}
    if not row.get("unit"):
        raise NotFound(f"No player with id `{key}`. Search for him above.")
    r = ctx.ros(key, str(row.get("position")))
    g = _str(r["starter_gsis"].iloc[0]) if not r.empty and "starter_gsis" in r else None
    if not g:
        raise NotFound(f"No line prices {row.get('full_name') or key} this week (a bye, or no starter on the board).")
    starter = _str(r["starter_name"].iloc[0]) or g
    out = player.player_card(league_id, g, od=ctx)
    name = row.get("full_name") or key
    who = ctx.availability(key)
    words = f"priced from {starter}'s line"
    out["unit"] = {"key": key, "position": row.get("position"), "team": out.get("team") or row.get("team"), "name": name,
                   "starter_gsis": g, "starter_name": starter, "words": words, "header": f"{name} — {words}"}
    out.update({"player_name": name, "starter_name": starter, **{k: who[k] for k in ("rostered_by_roster_id", "is_free_agent")}})
    rost = f"on **{who['rostered_by_team']}**" if who.get("rostered_by_team") else "**free agent** in this league"
    out["header"] = " · ".join([UNIT_WORDS.get(str(row.get("position")), str(row.get("position"))), words, rost])
    out["ros"] = ros_card(r.iloc[0]) if not r.empty else out.get("ros")
    return out
# ---- end IC-4


# ---- I0-B (Wave I-0): MyFantasyLeague leagues (league_lab.platforms / mfl_client). The key is `mfl:<id>`; every
# route above serves it unchanged (the translation answers in Sleeper's shapes). Here: the Leagues screen's card
# (`/api/leagues?mfl=<link or id>`), the notes My Week adds, and the gsis -> Sleeper step of the id mapping.
MFL_IDMAP_SQL = "select gsis_id, sleeper_id from analytics.player_id_map where gsis_id = any(%s) and sleeper_id is not null"


def _gsis_to_sleeper(gsis_ids: list[str]) -> dict[str, str]:
    df = query(MFL_IDMAP_SQL, (list(gsis_ids),))
    return {} if df.empty else {str(g): str(s) for g, s in zip(df["gsis_id"], df["sleeper_id"], strict=False)}


A.platforms.GSIS_LOOKUP = _gsis_to_sleeper

_SLOT_WORDS = {"QB": "QB", "RB": "RB", "WR": "WR", "TE": "TE", "FLEX": "FLEX", "SUPER_FLEX": "superflex", "K": "K",
               "DEF": "DEF"}


def _slot_word(slot: str) -> str:
    if slot in _SLOT_WORDS:
        return _SLOT_WORDS[slot]
    try:  # IC-2: the league's own names ("WR+TE" -> "WR/TE", "TMQB" -> "team QB")
        from .applib import cards
        return str(cards.slot_label(slot)).rstrip("0123456789 ") or slot
    except Exception:  # noqa: BLE001 - words only
        return slot


def mfl_scoring_note(league: dict) -> str:
    """The plain-words note under an MFL league's card: how its lineup and scoring were read."""
    m = league.get("mfl") or {}
    slots = [x for x in league.get("roster_positions") or [] if x != "BN"]
    counts: dict[str, int] = {}
    for x in slots:
        counts[x] = counts.get(x, 0) + 1
    lineup = ", ".join(f"{n} {_slot_word(k)}" if n > 1 else _slot_word(k) for k, n in counts.items())
    bits = [f"Lineup read as {lineup}."]
    sn = m.get("slots") or {}
    if sn.get("ranges"):
        rng = ", ".join(f"{v} {k}s" for k, v in sn["ranges"].items())
        bits.append(f"Your league lets you start {rng}: the spots beyond each minimum count as FLEX.")
    if sn.get("idp"):
        bits.append("Defensive players (" + ", ".join(sn["idp"]) + ") are not projected here; those spots are left out.")
    rep = m.get("scoring") or {}
    # Wave I-C: the spec's words when the translation carries them (the flat compiler's `approximated` / `unpriced`
    # describe the Sleeper-shaped copy, which no longer prices the league)
    approx = rep.get("spec_approximated") if "spec_approximated" in rep else rep.get("approximated")
    unpriced = rep.get("spec_unpriced") if "spec_unpriced" in rep else rep.get("unpriced")
    for a in approx or []:
        bits.append(a[:1].upper() + a[1:] + ".")
    if unpriced:
        bits.append("Not counted in the projections: " + ", ".join(str(u.get("name") or u.get("code") or u) if isinstance(u, dict) else str(u) for u in unpriced) + ".")
    return " ".join(bits)


def mfl_extras(league_id: str, league: dict) -> dict:
    mf = A.sleeper().mfl
    return {"mfl_unmapped": mf.unmapped(league_id), "mfl_mapped_by": mf.mapped_by(league_id),
            "mfl_scoring_note": mfl_scoring_note(league)}


def mfl_league(text: str) -> dict:
    """`/api/leagues?mfl=<link or id>`: the league card (name, size, scoring), its teams for the picker (MFL has no
    username lookup without a login), the team an `F=0004` in the link names, the players without a Sleeper id."""
    from league_lab.mfl_client import parse_link
    lid = None
    try:
        lid, fid, _year = parse_link(text)
        key = A.check_id(f"mfl:{lid}")
        sl = A.sleeper()
        league = sl.league(key)
        rosters, users = sl.rosters(key), sl.users(key)
    except A.LeagueNotFound as exc:
        raise mfl_error(lid, str(exc)) from exc                       # ---- II-5: the specific words
    except A.SleeperUnavailable as exc:
        raise SleeperDown(str(exc)) from exc
    names = A.team_names(rosters, users)
    teams = [{"roster_id": rid, "team_name": n["team_name"], "manager_name": n["manager_name"]}   # IC-4
             for rid, n in sorted(names.items())]
    pick = next((r["roster_id"] for r in rosters if fid is not None and str(r.get("owner_id")) == fid), None)
    lg = {"league_id": key, "name": league.get("name"), "season": int(league["season"]),
          "total_rosters": league.get("total_rosters"), "scoring_label": A.scoring_label(league),
          "url": (league.get("mfl") or {}).get("url"), "platform": "mfl"}
    n_players = sum(len(r.get("players") or []) for r in rosters)
    unmapped = sl.mfl.unmapped(key)
    return {"platform": "mfl", "league": lg, "teams": teams, "roster_id": pick, "unmapped": unmapped,
            "players": n_players, "mapped": n_players - len(unmapped), "scoring_note": mfl_scoring_note(league),
            "card": league_card(key, league),  # ---- IC-3: the read-backs
            "capabilities": A.platforms.capabilities("mfl")}  # ---- II-5


# I0-C: one box, a link / an id / the league's name. `/api/leagues?mfl_search=<text>`: a link, an id or an `mfl:` key
# answers exactly as `?mfl=` (mfl_league); a name answers MFL's public league search, this season only, at most 25.
def mfl_search(text: str) -> dict:
    from league_lab import mfl_client as M
    t = " ".join(str(text or "").split())
    if M.looks_like_link(t):
        return mfl_league(t)
    client = A.sleeper().mfl.client
    base = {"platform": "mfl", "query": t, "season": client.year}
    if len(t) < M.SEARCH_MIN:
        return {**base, "matches": [], "total": 0,
                "note": f"Type at least {M.SEARCH_MIN} letters of your league's name, or paste the league link."}
    try:
        rows = client.league_search(t)
    except A.SleeperUnavailable as exc:
        raise SleeperDown(str(exc)) from exc
    shown = rows[:M.SEARCH_MAX]
    matches = [{"league_id": f"mfl:{r['id']}", "name": r["name"], "year": r["year"], "home_url": r["home_url"]}
               for r in shown]
    if not rows:
        note = (f"No MyFantasyLeague league this season has “{t}” in its name. Check the spelling as it appears in "
                "the MFL app, or paste the league link.")
    elif len(rows) > len(shown):
        note = f"The first {len(shown)} of {len(rows)} leagues with “{t}” in the name: type more of it to narrow the list."
    else:
        note = f"{len(rows)} {'league has' if len(rows) == 1 else 'leagues have'} “{t}” in the name. Tap yours."
    return {**base, "matches": matches, "total": len(rows), "note": note}
# ---- end I0-B


# ---- II-5 (Wave I-I): the setup flow's errors — specific and recoverable (review § 9: "Validate and show specific
# recoverable errors"). A setup 404 carries `code` (the key the web keys its help on), `error` (the sentence) and `fix`
# (what to do next); main.py's NotFound handler passes `code` / `fix` through. The keys (INTERFACES.md § II-5):
SETUP_CODES = ("sleeper_user_unknown", "sleeper_username_invalid", "sleeper_league_unknown", "sleeper_link_invalid",
               "mfl_league_private", "mfl_link_invalid", "provider_down", "busy")
SLEEPER_WHERE = "the long number after /leagues/ in the league's address on sleeper.com (sleeper.com/leagues/1389709692405551104/team)"
MFL_WHERE = "the number after /home/ in your league's address on the MFL website (www45.myfantasyleague.com/2026/home/70587)"


class SetupError(NotFound):
    """A setup lookup that failed in a way the user can fix: `code` (SETUP_CODES), the sentence, `fix`."""

    def __init__(self, code: str, words: str, fix: str | None = None) -> None:
        super().__init__(words)
        self.code = code
        self.fix = fix


def sleeper_user_error(username: str) -> SetupError:
    u = " ".join(str(username or "").split())[:40]
    from league_lab.sleeper_client import check_username
    try:
        check_username(u)
    except A.LeagueNotFound:
        return SetupError("sleeper_username_invalid", f"“{u}” cannot be a Sleeper username: they are letters, numbers and _ . - only.",
                          "Type the name you sign in to Sleeper with, or paste your league's link.")
    return SetupError("sleeper_user_unknown", f"That Sleeper username does not exist: “{u}”.",
                      "Check the spelling: it is the name you sign in to Sleeper with, not your team's name. "
                      "Or paste your league's link instead.")


def mfl_error(league_id: str | None, cause: str) -> SetupError:
    if league_id is None or "look like" in cause or "not a MyFantasyLeague" in cause:
        return SetupError("mfl_link_invalid", "That is not a MyFantasyLeague league link or id.",
                          f"Paste your league's address, or the league id alone: {MFL_WHERE}. In the MFL app, type the "
                          "league's name instead.")
    return SetupError("mfl_league_private", f"MFL league {league_id} is private or does not exist. Ask the commissioner to "
                      "allow API access to the league's data (MFL's league setup, the privacy option).",
                      f"Check the id first: it is {MFL_WHERE}.")


_SLEEPER_LINK = re.compile(r"sleeper\.(?:com|app)/leagues/(\d{10,24})", re.I)
_SLEEPER_ID = re.compile(r"^\d{10,24}$")


def sleeper_league_id(text: str) -> str | None:
    """A Sleeper league link or id -> the id; None when the text is neither (a username)."""
    t = str(text or "").strip()
    m = _SLEEPER_LINK.search(t)
    if m:
        return m.group(1)
    return t if _SLEEPER_ID.match(t) else None


def sleeper_league(text: str) -> dict:
    """`/api/leagues?sleeper=<league link or id>`: the MFL answer's shape for a Sleeper league — the league, its teams for
    the picker (a league id says nothing about which team is yours), the card, the capabilities."""
    lid = sleeper_league_id(text)
    if lid is None:
        raise SetupError("sleeper_link_invalid", "That is not a Sleeper league link or id.",
                         f"Copy {SLEEPER_WHERE}, or type your Sleeper username instead.")
    sl = A.sleeper()
    try:
        league = sl.league(lid)
        rosters, users = sl.rosters(lid), sl.users(lid)
    except A.LeagueNotFound as exc:
        raise SetupError("sleeper_league_unknown", f"Sleeper has no football league {lid}.",
                         f"Check the number: it is {SLEEPER_WHERE}.") from exc
    except A.SleeperUnavailable as exc:
        raise SleeperDown(str(exc)) from exc
    names = A.team_names(rosters, users)
    teams = sorted(({"roster_id": rid, "team_name": n["team_name"], "manager_name": n["manager_name"]}
                    for rid, n in names.items()), key=lambda r: r["roster_id"])
    lg = {"league_id": lid, "name": league.get("name"), "season": int(league.get("season") or ui.current_season()),
          "total_rosters": league.get("total_rosters"), "scoring_label": A.scoring_label(league),
          "url": f"https://sleeper.com/leagues/{lid}", "platform": "sleeper"}
    return {"platform": "sleeper", "league": lg, "teams": teams, "roster_id": None, "card": league_card(lid, league),
            "capabilities": A.platforms.capabilities("sleeper")}
# ---- end II-5


# ---- IC-3 (Wave I-C): the Leagues card tells the truth. After a pick (an MFL league's card, each Sleeper league row)
# the card reads back, in the league's own words, the lineup League Lab will solve ("Your lineup: TMQB · 2 RB · 3 WR/TE ·
# TMPK · DEF"), the scoring it will price ("TDs by distance 6 / 9 / 12 · 1 pt per 10 yards · +10 at 100 yards · INT −3"),
# what it does not price, and where the scoring check lives (IC-1's `/api/league/scoring-check`; the web loads it, so
# the card never waits on it). The scoring words come from IC-1's `ScoringSpec.readback()` when the spec is there
# (guarded import), else from the flat `scoring_settings` (today's readers); the slots from `lineup.parse_slots`
# (IC-2's eligibility sets or today's names: both carry `.type`).
MINUS = "−"
_CARD_SLOT_WORDS = {"SUPER_FLEX": "superflex", "REC_FLEX": "WR/TE flex", "WRRB_FLEX": "RB/WR flex", "IDP_FLEX": "IDP flex",
                    "FLEX": "FLEX", "PK": "K", "TMDEF": "DEF"}
_UNPRICED_WORDS = {"pass_fd": "passing first downs", "rush_fd": "rushing first downs", "rec_fd": "receiving first downs",
                   "pass_att": "pass attempts", "pass_cmp": "completions", "pass_inc": "incompletions",
                   "rush_att": "carries", "pass_sack": "sacks taken", "kr_yd": "kick return yards",
                   "pr_yd": "punt return yards", "rec_tgt": "targets", "pass_int_td": "pick-sixes thrown",
                   "fum": "fumbles (any)"}


def _num_words(v: float) -> str:
    s = f"{abs(float(v)):.2f}".rstrip("0").rstrip(".")
    return (MINUS if float(v) < 0 else "") + s


def slot_word(name: str) -> str:
    """A slot in plain words, the league's own name kept: WR+TE -> "WR/TE", SUPER_FLEX -> "superflex", TMQB stays."""
    n = str(name).upper()
    if n in _CARD_SLOT_WORDS:
        return _CARD_SLOT_WORDS[n]
    if "+" in n:
        return "/".join(_CARD_SLOT_WORDS.get(p, p) for p in n.split("+"))
    return n


def lineup_readback(league: dict) -> dict:
    """The starting lineup League Lab solves for this league, in its own words, grouped in order ("2 RB"); the
    slots it does not solve (IDP, or an MFL starter the translation could not read) are named, never dropped."""
    from league_lab.lineup import NOT_SLOTS, parse_slots
    positions = [str(x) for x in league.get("roster_positions") or []]
    slots, ignored = parse_slots(positions)
    groups: list[list] = []
    for s in slots:
        w = slot_word(getattr(s, "type", s))
        if groups and groups[-1][0] == w:
            groups[-1][1] += 1
        else:
            groups.append([w, 1])
    parts = [f"{n} {w}" if n > 1 else w for w, n in groups]
    unread = list(dict.fromkeys(slot_word(x) for x in ignored))
    m = league.get("mfl") or {}
    for x in ((m.get("slots") or {}).get("idp") or []):                 # MFL starters the slot translation dropped
        if slot_word(x) not in unread:
            unread.append(slot_word(x))
    text = "Your lineup: " + (" · ".join(parts) if parts else "no starting spots read")
    out = {"text": text, "slots": [getattr(s, "label", str(s)) for s in slots], "unread": unread,
           "bench": sum(1 for x in positions if x.upper() in NOT_SLOTS)}
    if unread:
        out["unread_text"] = f"Not in the lineup {APP_NAME} solves: " + ", ".join(unread) + "."
    return out


def _league_spec(league: dict):
    """IC-1's ScoringSpec for the league (guarded: None until that module is in the tree)."""
    try:
        from league_lab import anyleague as _A
        if hasattr(_A, "league_spec"):
            return _A.league_spec(league)
        from league_lab.scoring import ScoringSpec, from_sleeper  # type: ignore[attr-defined]
        if league.get("scoring_spec"):
            return ScoringSpec.from_json(league["scoring_spec"])
        return from_sleeper(league.get("scoring_settings") or {})
    except (ImportError, AttributeError, KeyError, TypeError, ValueError):
        return None


def _per(v: float) -> str:
    """0.1 -> "1 pt per 10", 0.04 -> "1 pt per 25", 0.5 -> "0.5 per"."""
    v = float(v)
    if 0 < v < 1 and abs(1 / v - round(1 / v)) < 1e-6:
        return f"1 pt per {round(1 / v)}"
    return f"{_num_words(v)} per"


def flat_readback(sc: dict, roster_positions: list[str] | None = None) -> list[str]:
    """Today's flat Sleeper-shaped dict in plain words (the fallback until the spec is in the tree)."""
    from league_lab.scoring import SLEEPER_BONUS_MAP, SLEEPER_LONG_TD_MAP
    g = lambda k: round(float(sc.get(k) or 0), 3)  # noqa: E731
    out: list[str] = []
    rec = g("rec")
    out.append({0: "no points per catch", 0.5: "half PPR", 1: "full PPR"}.get(rec) or f"{_num_words(rec)} per catch")
    if g("bonus_rec_te"):
        out.append(f"TE +{_num_words(g('bonus_rec_te'))} per catch")
    if g("pass_td"):
        td = f"pass TD {_num_words(g('pass_td'))}"
        if g("rush_td") and g("rush_td") == g("rec_td"):
            td += f", rush / catch TD {_num_words(g('rush_td'))}"
        out.append(td)
    yd = []
    if g("pass_yd"):
        yd.append(f"{_per(g('pass_yd'))} passing yards")
    if g("rush_yd") and g("rush_yd") == g("rec_yd"):
        yd.append(f"{_per(g('rush_yd'))} rushing / receiving yards")
    else:
        yd += [f"{_per(g(k))} {w} yards" for k, w in (("rush_yd", "rushing"), ("rec_yd", "receiving")) if g(k)]
    out += yd
    bonus: dict[str, list[str]] = {}
    for k, (col, low, _high, _d) in SLEEPER_BONUS_MAP.items():
        if g(k):
            bonus.setdefault(col.replace("_yards", ""), []).append(f"+{_num_words(g(k))} at {low}")
    for col, bits in bonus.items():
        out.append(f"{', '.join(bits)} {col} yards")
    longs = {g(k) for k in SLEEPER_LONG_TD_MAP if k.endswith("_40p") and g(k)}
    if len(longs) == 1:
        out.append(f"+{_num_words(next(iter(longs)))} for a 40+ yard TD")
    elif longs:
        out.append("bonuses for 40+ yard TDs")
    if g("pass_int"):
        out.append(f"INT {_num_words(g('pass_int'))}")
    if g("fum_lost"):
        out.append(f"fumble lost {_num_words(g('fum_lost'))}")
    slots = [str(x).upper() for x in roster_positions or []]
    fg = [g(k) for k in ("fgm_0_19", "fgm_20_29", "fgm_30_39", "fgm_40_49", "fgm_50p")]
    if any(fg) and (not slots or "K" in slots):
        steps = [v for i, v in enumerate(fg) if v and (i == 0 or v != fg[i - 1])]
        out.append("FG " + " / ".join(_num_words(v) for v in steps) + " by distance" if len(steps) > 1 else f"FG {_num_words(steps[0])}")
    if (not slots or "DEF" in slots) and any(k.startswith("pts_allow") and g(k) for k in sc):
        out.append(f"DEF: sacks {_num_words(g('sack'))}, takeaways {_num_words(g('int'))}, points allowed by band"
                   if g("sack") else "DEF: points allowed by band")
    return out


def _projection_gaps(sc: dict) -> list[str]:
    """What today's projections leave out of a Sleeper-shaped scoring (the audit's finding; the spec's expected-value
    pricing closes these when it lands)."""
    from league_lab.scoring import SLEEPER_BONUS_MAP, SLEEPER_LONG_TD_MAP
    out = []
    if any(float(sc.get(k) or 0) for k in SLEEPER_LONG_TD_MAP):
        out.append("40+ yard touchdown bonuses are paid in your league but not in the projections")
    if any(float(sc.get(k) or 0) for k in SLEEPER_BONUS_MAP):
        out.append("yardage bonuses count in a projection only when the projected yards reach the line (all or nothing)")
    if any(float(sc.get(k) or 0) for k in ("pass_2pt", "rush_2pt", "rec_2pt")):
        out.append("2-point conversions are not projected")
    return out


def scoring_readback(league: dict) -> dict:
    """The scoring in one line of plain words + what is not priced. From IC-1's spec when present (source "spec"), else
    from the flat `scoring_settings` (source "settings": the projection's own view today)."""
    from league_lab.kdef import DEF_KEY_PREFIXES
    from league_lab.scoring import SLEEPER_POSITION_MAP, unmapped_keys
    spec = _league_spec(league)
    sc = {k: v for k, v in (league.get("scoring_settings") or {}).items() if v}
    if spec is not None and hasattr(spec, "readback"):
        pieces = list(spec.readback())
        not_priced = [str(u.get("name") or u.get("event")) if isinstance(u, dict) else str(u) for u in (spec.unpriced or [])]
        approximated = [str(a) for a in (getattr(spec, "approximated", None) or [])]
        source = "spec"
        # a Sleeper spec still prices projections on the flat path (all or nothing, no long-TD bonus) unless IC-1's
        # LEAGUE_LAB_EV_PRICING is on: the card keeps saying so until it is
        try:
            from league_lab.scoring import ev_pricing  # type: ignore[attr-defined]
            ev = bool(ev_pricing())
        except ImportError:
            ev = False
        if getattr(spec, "flat", None) is not None and not ev:
            approximated += [g for g in _projection_gaps(sc) if g not in approximated]
    else:
        pieces = flat_readback(sc, league.get("roster_positions"))
        is_def = lambda k: k.startswith(DEF_KEY_PREFIXES)  # noqa: E731
        not_priced = [_UNPRICED_WORDS.get(k, k.replace("_", " ")) for k in unmapped_keys(sc)
                      if k not in SLEEPER_POSITION_MAP and not is_def(k)]
        rep = (league.get("mfl") or {}).get("scoring") or {}
        not_priced += [str(x) for x in rep.get("unpriced") or [] if str(x) not in not_priced]
        approximated = list(dict.fromkeys(str(a) for a in rep.get("approximated") or []))
        approximated += [g for g in _projection_gaps(sc) if g not in approximated]
        source = "settings"
    not_priced = list(dict.fromkeys(not_priced))
    out = {"text": " · ".join(pieces) if pieces else "No scoring rules read for this league", "pieces": pieces,
           "not_priced": not_priced, "approximated": approximated, "source": source}
    if not_priced:
        out["not_priced_text"] = "Not counted in the projections: " + ", ".join(not_priced) + "."
    return out


def check_path(league_id: str) -> str:
    from urllib.parse import quote
    return f"/api/league/scoring-check?league={quote(str(league_id), safe='')}"


def league_card(league_id: str, league: dict) -> dict:
    """`card` on `/api/leagues?mfl=` and on each `/api/leagues?username=` row."""
    return {"lineup": lineup_readback(league), "scoring": scoring_readback(league), "check_path": check_path(league_id)}


def with_cards(answer: dict) -> dict:
    """`leagues_for_user`'s answer with a card per league (the league payload is cached a day: no extra call once
    the rows were read). A league Sleeper will not give us now keeps `card: null`."""
    sl = A.sleeper()
    for row in answer.get("leagues") or []:
        try:
            row["card"] = league_card(row["league_id"], sl.league(row["league_id"]))
        except (A.LeagueNotFound, A.SleeperUnavailable, KeyError, TypeError, ValueError):
            row["card"] = None
    return answer
# ---- end IC-3


# ---- IH-3 (Wave I-H): `win` on the on-demand answer — the database path's `myweek.win` with the on-demand rows. The
# ranges come with the priced board (`anyleague.lineup_rows` -> `_cards_frame`: the reference scoring's ranges shifted
# onto this league's points; none when the league's ranges are not priced -> "no range for this league yet"). The
# week's points for a starter whose game is in: Sleeper's matchups call (`players_points`, the league's own scoring,
# cached with the opponent's call); an MFL league's: MFL's live scoring (IL-2, `mfl_week_points`; was not read).
def week_points(client, league_id: str, week: int, roster_ids) -> dict[str, float] | None:
    if A.platforms.is_mfl(league_id):
        return mfl_week_points(client, league_id, week)        # ---- IL-2: MFL's live scoring (was None: not read)
    # ---- IK-3: an ESPN / Yahoo league's matchups carry `players_points` only when the adapter reads them (else {})
    try:
        ms = client.matchups(league_id, int(week))
    except (A.SleeperBusy, A.SleeperUnavailable):
        return None
    want = {int(r) for r in roster_ids}
    out: dict[str, float] = {}
    for m in ms or []:
        if int(m.get("roster_id", -1)) in want:
            for k, v in (m.get("players_points") or {}).items():
                if v is not None:
                    out[str(k)] = float(v)
    return out


def win_on_demand(client, league_id: str, roster_id: int, season: int, week: int, rows: pd.DataFrame, opp: dict | None,
                  *, as_of=None, exclude_reference: str | None = None) -> dict | None:
    from .myweek import win

    def ctx(rid: int):
        return availability.roster_context(league_id, int(rid), week, house=False, as_of=as_of,
                                           exclude_reference=exclude_reference, client=client)
    try:
        return win(league_id, int(roster_id), season, week, rows, opp, house=False, context_fn=ctx,
                   points_fn=lambda rids: week_points(client, league_id, week, rids))
    except (A.SleeperBusy, A.SleeperUnavailable, A.LeagueNotFound):
        return None
# ---- end IH-3


# ---- IK-3 (Wave I-K): ESPN (`espn:<id>`, IK-1) and Yahoo (`yahoo:<game>.l.<id>`, IK-2) leagues on demand. Every route
# above serves them unchanged (the Router answers in Sleeper's shapes); here the setup answers: `/api/leagues?espn=<id or
# link>`, `?yahoo=<league key, id or link>` (the `?mfl=` shape: the league, its teams, the card, the capabilities) and
# `?yahoo_me=1` (the signed-in user's Yahoo leagues through IK-2's `ll_yahoo` cookie), and their II-5-style errors.
# The provider modules are optional (guarded imports): a server without one answers `<provider>_not_configured`.
import contextvars  # noqa: E402 - the block stays self-contained
import importlib  # noqa: E402
import os  # noqa: E402

SETUP_CODES = SETUP_CODES + ("espn_link_invalid", "espn_league_unknown", "espn_league_private", "espn_not_configured",
                             "yahoo_link_invalid", "yahoo_league_unknown", "yahoo_sign_in_required",
                             "yahoo_session_expired", "yahoo_not_configured")      # the yahoo_* codes are IK-2's
ESPN_WHERE = ("the number after leagueId= in your league's address on fantasy.espn.com "
              "(fantasy.espn.com/football/league?leagueId=4242)")
YAHOO_WHERE = ("the number after /f1/ in your league's address on Yahoo "
               "(football.fantasysports.yahoo.com/f1/12345)")
# STUB-only: a token for the stand-in Yahoo adapter (main.py's IK-3 middleware sets it from the `ll_yahoo` cookie when
# `LEAGUE_LAB_PROVIDER_STUBS=1`). The real connection is IK-2's `yahoo_client.request_session` (its own middleware).
YAHOO_TOKEN: contextvars.ContextVar[str | None] = contextvars.ContextVar("ll_yahoo_token", default=None)


def _mod(name: str):
    """IK-1's / IK-2's module when it is in the tree, else None."""
    try:
        return importlib.import_module(f"league_lab.{name}")
    except ImportError:
        return None


def espn_private() -> bool:
    """`/api/providers.espn_private`: IK-1's switch (`LEAGUE_LAB_ESPN_PRIVATE=on` and a secret to seal the cookie)."""
    m = _mod("espn_client")
    if m is not None and hasattr(m, "private_enabled"):
        try:
            return bool(m.private_enabled())
        except Exception:  # noqa: BLE001 - a flag: off when it cannot be read
            return False
    return (os.environ.get("LEAGUE_LAB_ESPN_PRIVATE") or "").strip().lower() == "on" \
        and bool(os.environ.get("LEAGUE_LAB_API_SECRET"))


def yahoo_configured() -> bool:
    """`/api/providers.yahoo_configured`: Connect with Yahoo works on this server — IK-2's `yahoo_connect.configured()`
    (both Yahoo secrets and the API secret to seal the cookie, or fixture mode), else the client's check."""
    try:
        from . import yahoo_connect
        return bool(yahoo_connect.configured())
    except ImportError:
        pass
    except Exception:  # noqa: BLE001 - a flag: off when it cannot be read
        return False
    m = _mod("yahoo_client")
    for name in ("configured", "is_configured"):
        if m is not None and callable(getattr(m, name, None)):
            try:
                return bool(getattr(m, name)())
            except Exception:  # noqa: BLE001
                return False
    return bool(os.environ.get("LEAGUE_LAB_YAHOO_CLIENT_ID") and os.environ.get("LEAGUE_LAB_YAHOO_CLIENT_SECRET"))


def provider_flags() -> dict:
    return {"espn_private": espn_private(), "yahoo_configured": yahoo_configured()}


_ESPN_LEAGUE_ID = re.compile(r"[?&#]leagueId=(\d{1,12})", re.I)
_ESPN_TEAM_ID = re.compile(r"[?&#]teamId=(\d{1,4})", re.I)
_ESPN_SEASON = re.compile(r"[?&#]seasonId=(\d{4})", re.I)


def espn_parse(text: str) -> tuple[str, str | None]:
    """An ESPN league link, id or key -> (the key `espn:<id>` / `espn:<season>:<id>`, the team id the link names or
    None). IK-1's `espn_client.parse_link` when present; LeagueNotFound (code espn_link_invalid) otherwise."""
    t = " ".join(str(text or "").split())
    m = _mod("espn_client")
    if m is not None and hasattr(m, "parse_link"):
        lid, team, season = m.parse_link(t)
        return A.platforms.check_espn(f"espn:{season}:{lid}" if season else f"espn:{lid}"), (str(team) if team else None)
    if t.lower().startswith(A.platforms.ESPN_PREFIX) or re.fullmatch(r"\d{1,12}", t):
        return A.platforms.check_espn(t), None
    if "espn.com" in t.lower():
        lid = _ESPN_LEAGUE_ID.search(t)
        if lid:
            season, team = _ESPN_SEASON.search(t), _ESPN_TEAM_ID.search(t)
            key = f"espn:{season.group(1)}:{lid.group(1)}" if season else f"espn:{lid.group(1)}"
            return A.platforms.check_espn(key), team.group(1) if team else None
    raise A.LeagueNotFound(f"not an ESPN league link or id: {t[:80]!r}")


_YAHOO_LINK = re.compile(r"fantasysports\.yahoo\.com/(?:\d{4}/)?(?:f1|nfl)/(\d{1,10})(?:/(\d{1,3}))?", re.I)
_YAHOO_KEY_TEXT = re.compile(r"^(?:yahoo:)?(\d{1,4}|nfl)\.l\.(\d{1,10})(?:\.t\.(\d{1,3}))?$", re.I)


def yahoo_game_key() -> str:
    """This season's NFL game key: IK-2's client resolves Yahoo's code ``nfl`` (a read: needs the user's Yahoo
    connection — YahooSignInRequired otherwise); the stubs answer 461."""
    if os.environ.get(A.platforms.STUBS_ENV) == "1":
        return os.environ.get("LEAGUE_LAB_YAHOO_GAME_KEY") or "461"
    client = getattr(adapter_of("yahoo"), "client", None)
    if client is not None and callable(getattr(client, "game_key", None)):
        return str(client.game_key("nfl"))
    return os.environ.get("LEAGUE_LAB_YAHOO_GAME_KEY") or "nfl"


def yahoo_parse(text: str) -> tuple[str, str | None]:
    """A Yahoo league link, league key (`461.l.12345`, `yahoo:461.l.12345`, `461.l.12345.t.3`) or bare id -> (the key with
    a numeric game, the team id the link or a team key names, else None). A bare id or a link takes this season's game
    key (IK-2's `parse_link` gives `nfl.l.<id>`; resolved here so a remembered key names its season)."""
    t = " ".join(str(text or "").split())
    m = _mod("yahoo_client")
    if m is not None and hasattr(m, "parse_link") and not re.fullmatch(r"\d{1,10}", t):
        lk, team = m.parse_link(t)
        team = str(team) if team is not None else None
    else:
        k, ln = _YAHOO_KEY_TEXT.match(t), _YAHOO_LINK.search(t)
        if k:
            lk, team = f"{k.group(1)}.l.{k.group(2)}", k.group(3)
        elif ln:
            lk, team = f"nfl.l.{ln.group(1)}", ln.group(2)
        elif re.fullmatch(r"\d{1,10}", t):
            lk, team = f"nfl.l.{t}", None
        else:
            raise A.LeagueNotFound(f"not a Yahoo league link or key: {t[:80]!r}")
    gk, lid = str(lk).lower().split(".l.", 1)
    if not gk.isdigit():
        gk = yahoo_game_key()
    return A.platforms.check_yahoo(f"yahoo:{gk}.l.{lid}"), team


def provider_error(provider: str, league_id: str | None, exc: Exception) -> SetupError:
    """The setup error for an ESPN / Yahoo lookup: the adapter's own `code` / words / `fix` when it carries them (IK-1:
    `espn_client.setup_words`), else the words here. `private_form` rides on an ESPN private league when the switch
    is on (the web then offers "Private league?")."""
    short = A.platforms.SHORT[provider]
    code, words, fix = getattr(exc, "code", None), str(exc), getattr(exc, "fix", None)
    m = _mod("espn_client" if provider == "espn" else "yahoo_client")
    words_of = getattr(m, "setup_words" if provider == "espn" else "setup_parts", None) if m is not None else None
    if words_of is not None and not isinstance(exc, A.platforms.ProviderNotConfigured) and \
            (provider == "espn" or getattr(exc, "code", None)):
        try:                                            # IK-1's setup_words(exc, id) / IK-2's setup_parts(exc)
            code, words, fix = words_of(exc, league_id) if provider == "espn" else words_of(exc)
        except Exception:  # noqa: BLE001 - our own words below
            pass
    where = ESPN_WHERE if provider == "espn" else YAHOO_WHERE
    if isinstance(exc, A.platforms.ProviderNotConfigured) or code == f"{provider}_not_configured":
        if isinstance(exc, A.platforms.ProviderNotConfigured) or not words:    # the provider's own words otherwise
            words = (f"{A.platforms.LONG[provider]} leagues are not set up on this server yet." if provider == "espn"
                     else "Yahoo sign-in is not set up on this server yet.")    # (IK-1's kill switch says "switched off")
        code = f"{provider}_not_configured"
        fix = fix or "Coming soon. Sleeper and MyFantasyLeague leagues work today."
    elif code not in SETUP_CODES:
        if league_id is None:
            code, words = f"{provider}_link_invalid", f"That is not {'an ESPN' if provider == 'espn' else 'a Yahoo'} league link or id."
            fix = f"Paste your league's address, or the league id alone: {where}."
        else:
            code = f"{provider}_league_unknown"
            words = f"{short} has no league {league_id.split(':', 1)[-1]} this season."
            fix = f"Check the id: it is {where}."
    if not fix:                                                         # the fix line for a code that came without one
        fix = {f"{provider}_link_invalid": f"Paste your league's address, or the league id alone: {where}.",
               f"{provider}_league_unknown": f"Check the id: it is {where}.",
               "espn_league_private": f"Check the id first: it is {where}.",
               "yahoo_sign_in_required": "Connect with Yahoo, then pick the league from your list.",
               "yahoo_session_expired": "Connect with Yahoo again: your leagues come back."}.get(code)
    if code == "espn_league_private" and espn_private() and fix and "Private league?" not in fix:
        fix += " Or use “Private league?” to read it with your own ESPN cookies."
    se = SetupError(code, words if words.endswith((".", ")")) else words + ".", fix)
    se.provider = provider                                              # type: ignore[attr-defined]
    if code == "espn_league_private" and espn_private():
        se.private_form = True                                          # type: ignore[attr-defined]
    return se


def _mfl_view(league: dict, provider: str) -> dict:
    """The league with its provider block where the card's readers look for MFL's (`mfl`: slots, scoring report)."""
    return league if provider == "mfl" or "mfl" in league else {**league, "mfl": league.get(provider) or {}}


def provider_scoring_note(league: dict, provider: str) -> str:
    return mfl_scoring_note(_mfl_view(league, provider))


def adapter_of(provider: str):
    sl = A.sleeper()
    return sl.espn if provider == "espn" else sl.yahoo


def provider_league(provider: str, key: str, team: str | None = None) -> dict:
    """The `?mfl=` answer's shape for an ESPN / Yahoo league key: the league, its teams for the picker, the team the
    link names (by the provider's team id: the roster whose `owner_id` is it, else roster_id), the players without a
    Sleeper id, the card, the capabilities."""
    sl = A.sleeper()
    if provider == "yahoo" and not yahoo_configured() and os.environ.get(A.platforms.STUBS_ENV) != "1":
        raise provider_error("yahoo", key, A.platforms.ProviderNotConfigured("yahoo"))   # no keys: no Yahoo read at all
    try:
        league = sl.league(key)
        rosters, users = sl.rosters(key), sl.users(key)
        unmapped = list(adapter_of(provider).unmapped(key) or [])
    except A.LeagueNotFound as exc:
        raise provider_error(provider, key, exc) from exc
    except A.SleeperUnavailable as exc:
        down = SleeperDown(str(exc))
        down.who = A.platforms.SHORT[provider]                         # type: ignore[attr-defined]
        raise down from exc
    names = A.team_names(rosters, users)
    teams = [{"roster_id": rid, "team_name": n["team_name"], "manager_name": n["manager_name"]}
             for rid, n in sorted(names.items())]
    pick = None
    if team is not None:                     # the link's team: IK-1's roster_id_of (ESPN team id), else the owner id
        ad = adapter_of(provider)
        if callable(getattr(ad, "roster_id_of", None)):
            pick = ad.roster_id_of(key, team)
        if pick is None:
            pick = next((int(r["roster_id"]) for r in rosters if str(r.get("owner_id")) == str(team)), None)
        if pick is None and str(team).isdigit() and int(team) in names:
            pick = int(team)
    block = league.get(provider) or {}
    lg = {"league_id": key, "name": league.get("name"), "season": int(league.get("season") or ui.current_season()),
          "total_rosters": league.get("total_rosters"), "scoring_label": A.scoring_label(league),
          "url": block.get("url"), "platform": provider}
    n_players = sum(len(r.get("players") or []) for r in rosters)
    return {"platform": provider, "league": lg, "teams": teams, "roster_id": pick, "unmapped": unmapped,
            "players": n_players, "mapped": n_players - len(unmapped),
            "scoring_note": provider_scoring_note(league, provider), "card": league_card(key, _mfl_view(league, provider)),
            "capabilities": A.platforms.capabilities(provider), **provider_flags()}


def espn_league(text: str) -> dict:
    """`/api/leagues?espn=<id or link>`."""
    try:
        key, team = espn_parse(text)
    except A.LeagueNotFound as exc:
        raise provider_error("espn", None, exc) from exc
    return provider_league("espn", key, team)


def yahoo_league(text: str) -> dict:
    """`/api/leagues?yahoo=<league key, id or link>`."""
    if not yahoo_configured() and os.environ.get(A.platforms.STUBS_ENV) != "1":       # no keys: no Yahoo read at all
        raise provider_error("yahoo", None, A.platforms.ProviderNotConfigured("yahoo"))
    try:
        key, team = yahoo_parse(text)
    except A.LeagueNotFound as exc:                   # not a link; or this season's game needs the Yahoo connection
        raise provider_error("yahoo", None if getattr(exc, "code", None) in (None, "yahoo_link_invalid") else text,
                             exc) from exc
    except RuntimeError as exc:                       # IK-2's YahooNotConfigured (a RuntimeError with its code)
        if str(getattr(exc, "code", "")).endswith("_not_configured"):
            raise provider_error("yahoo", None, A.platforms.ProviderNotConfigured("yahoo")) from exc
        raise
    return provider_league("yahoo", key, team)


YAHOO_NOTES = {"not_configured": "Yahoo sign-in is not set up on this server yet: coming soon.",
               "not_connected": "Connect with Yahoo to list your leagues here.",
               "expired": "Your Yahoo connection has expired. Connect with Yahoo again.",
               "none": "Yahoo lists no football leagues for you this season."}


def yahoo_connected() -> bool:
    """This request carries a Yahoo connection: IK-2's ``request_session`` (its middleware reads ``ll_yahoo``); the stubs:
    any ``ll_yahoo`` cookie."""
    if os.environ.get(A.platforms.STUBS_ENV) == "1":
        return bool(YAHOO_TOKEN.get())
    m = _mod("yahoo_client")
    s = m.request_session.get() if m is not None and hasattr(m, "request_session") else None
    return s is not None and not getattr(s, "expired", False)


def yahoo_me() -> dict:
    """`/api/leagues?yahoo_me=1`: the signed-in user's Yahoo football leagues this season, their team in each (always 200:
    not set up / not connected are flags and a `note`, the web shows "coming soon" / "Connect with Yahoo")."""
    stub = os.environ.get(A.platforms.STUBS_ENV) == "1"
    base = {"platform": "yahoo", "configured": yahoo_configured(), "connected": False,
            "season": int(ui.current_season()), "leagues": [], "capabilities": A.platforms.capabilities("yahoo")}
    if not base["configured"] and not stub:
        return {**base, "note": YAHOO_NOTES["not_configured"]}
    if not yahoo_connected():
        return {**base, "note": YAHOO_NOTES["not_connected"]}
    try:
        ad = adapter_of("yahoo")
        rows = list(ad.my_leagues(YAHOO_TOKEN.get()) if stub else ad.my_leagues())
    except A.platforms.ProviderNotConfigured:
        return {**base, "configured": False, "note": YAHOO_NOTES["not_configured"]}
    except A.LeagueNotFound:                                   # IK-2's YahooSignInRequired / YahooSessionExpired
        return {**base, "note": YAHOO_NOTES["expired"]}
    except A.SleeperUnavailable as exc:
        down = SleeperDown(str(exc))
        down.who = "Yahoo"                                     # type: ignore[attr-defined]
        raise down from exc
    except RuntimeError as exc:                                # IK-2's YahooNotConfigured
        if str(getattr(exc, "code", "")).endswith("_not_configured"):
            return {**base, "configured": False, "note": YAHOO_NOTES["not_configured"]}
        raise
    sl = A.sleeper()
    leagues = []
    for r in rows:
        key = A.platforms.check_yahoo(r.get("key") or f"yahoo:{r.get('league_key')}")
        rid = r.get("roster_id") if r.get("roster_id") is not None else r.get("team_id")
        row = {"league_id": key, "name": r.get("name"), "season": int(r["season"]) if str(r.get("season") or "").isdigit() else None,
               "total_rosters": r.get("num_teams"), "scoring_label": None, "roster_id": int(rid) if rid is not None else None,
               "team_name": r.get("team_name"), "url": r.get("url"), "card": None}
        try:
            league = sl.league(key)
            row["scoring_label"] = A.scoring_label(league)
            row["total_rosters"] = row["total_rosters"] or league.get("total_rosters")
            row["card"] = league_card(key, _mfl_view(league, "yahoo"))
            if row["roster_id"] is not None and not row["team_name"]:
                names = A.team_names(sl.rosters(key), sl.users(key))
                row["team_name"] = (names.get(int(row["roster_id"])) or {}).get("team_name")
        except (A.LeagueNotFound, A.SleeperUnavailable, A.SleeperBusy, KeyError, TypeError, ValueError):
            pass                                               # the row still opens; its card says nothing
        leagues.append(row)
    return {**base, "connected": True, "leagues": leagues, "note": None if leagues else YAHOO_NOTES["none"]}


def provider_extras(league_id: str, league: dict) -> dict:
    """What My Week adds for an ESPN / Yahoo league (MFL's `mfl_extras` for the other providers): the players without a
    Sleeper id, how the rest were matched, the scoring note — under `<provider>_…` and the generic `provider_…` keys."""
    p = A.platforms.provider_of(league_id)
    try:
        ad = adapter_of(p)
        un, by = list(ad.unmapped(league_id) or []), dict(ad.mapped_by(league_id) or {})
    except A.LeagueNotFound:
        un, by = [], {}
    note = provider_scoring_note(league, p)
    return {f"{p}_unmapped": un, f"{p}_mapped_by": by, f"{p}_scoring_note": note,
            "provider_unmapped": un, "provider_mapped_by": by, "provider_scoring_note": note}
# ---- end IK-3


# ---- IK-3: STUB only — the stand-in Yahoo adapter takes any `ll_yahoo` cookie value as its token (main.py's IK-3
# middleware). The real connection is IK-2's sealed cookie and middleware (`yahoo_connect`, `yahoo_client.request_session`).
def yahoo_token_from(cookie: str | None) -> str | None:
    return cookie or None if os.environ.get(A.platforms.STUBS_ENV) == "1" else None
# ---- end IK-3


# ---- IL-2 (Wave I-L): an MFL league's live points — MFL's ``liveScoring`` export (``MFLLeagues.live_points``: each
# listed player's points so far, by Sleeper id). The week's odds read them for the starters whose game is over (a game in
# progress keeps its full range, IH-3's rule); ``myweek.live_scored`` adds the NFL teams MFL says are done to the
# nightly's. MFL down or busy: None (unknown, never 0) — the line steps aside once a game is in, as before.
def _mfl_adapter(client):
    c = client if client is not None else A.sleeper()
    return getattr(c, "mfl", None)


def mfl_week_points(client, league_id: str, week: int) -> dict[str, float] | None:
    mf = _mfl_adapter(client)
    if mf is None:
        return None
    try:
        return dict(mf.live_points(league_id, int(week))["points"]) or None
    except (A.SleeperBusy, A.SleeperUnavailable, A.LeagueNotFound):
        return None


def mfl_teams_done(client, league_id: str, week: int) -> set[str]:
    """The NFL teams whose game MFL's live scoring says is over this week (Sleeper's team codes); empty when unknown."""
    mf = _mfl_adapter(client)
    if mf is None:
        return set()
    try:
        return set(mf.live_points(league_id, int(week))["teams_done"])
    except (A.SleeperBusy, A.SleeperUnavailable, A.LeagueNotFound):
        return set()
# ---- end IL-2
