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

import time

import pandas as pd
from league_lab import anyleague as A

from . import availability, why
from .applib import cards, ui
from .db import query
from .myweek import NotFound, _num, _str, cards_from_rows, current_starters, howto, lineup

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
            octx = availability.roster_context(league_id, int(opp["roster_id"]), week, house=False, as_of=as_of,
                                               exclude_reference=exclude_reference, client=client)
            opp["lineup_value"] = octx.lineup_value
            opp["changes"] = octx.changes
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
    if rec:
        bits.append(f"{rec['wins']}-{rec['losses']}, #{rec['standing']} in the league")
    if opp and opp.get("team_name"):
        bits.append(f"week {week} vs **{opp['team_name']}**")
    out["summary"] = " · ".join(bits)
    out["league_line"] = cards.league_line(league_id, int(roster_id), week, rows) if not rows.empty else ""
    lv = rows.loc[rows["role"] == "starter", "lineup_value"].dropna() if not rows.empty else pd.Series(dtype=float)
    out["lineup_value"] = None if lv.empty else float(lv.iloc[0])
    t1 = time.perf_counter()
    out["notice"], out["cards"] = cards_from_rows(league_id, int(roster_id), week, season, rows,         # ---- IB-0
                                                  current=current_starters(league_id, int(roster_id), house=False))
    t2 = time.perf_counter()
    out["lineup"], out["lineup_full"] = lineup(rows)
    out["howto"] = howto()
    gs = sorted({g for g in rows["gsis_id"].dropna()}) if not rows.empty else []
    mv = query(MOVERS_SQL, (season, gs)) if gs else pd.DataFrame()
    out["movers"] = [{"gsis_id": _str(r.gsis_id), "player_name": r.player_name, "position": r.position,
                      "tags": _str(r.tags), "momentum": _num(r.momentum)} for r in mv.itertuples()]
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
    return out


# ---------------------------------------------------------------- plan F3: the league picker by Sleeper username
def leagues_for_user(username: str) -> dict:
    from .myweek import known_league
    season = ui.current_season()
    try:
        return A.user_leagues(username, int(season), in_database=known_league)
    except A.LeagueNotFound as exc:
        raise NotFound("no such Sleeper user") from exc
    except A.SleeperUnavailable as exc:
        raise SleeperDown(str(exc)) from exc


def rosters_for_league(league_id: str) -> list[dict]:
    """The team picker's options for a league the database does not have (F2's request): Sleeper's rosters
    and users, named the way dim_league_member names them (team name, else display name)."""
    sl = A.sleeper()
    try:
        league_id = A.check_id(league_id)         # I0-B: a Sleeper id or an mfl:<id> key
        sl.league(league_id)                      # 404 for an id Sleeper does not have (before the rosters call)
        rosters, users = sl.rosters(league_id), sl.users(league_id)
    except A.LeagueNotFound as exc:
        raise NotFound(str(exc) if A.platforms.is_mfl(league_id) else f"no Sleeper league {league_id}") from exc
    except A.SleeperUnavailable as exc:
        raise SleeperDown(str(exc)) from exc
    names = A.team_names(rosters, users)
    mfl = A.platforms.is_mfl(league_id)           # I0-B: MFL shares no manager names (the franchise name only)
    out = [{"roster_id": rid, "team_name": n["team_name"], "manager_name": None if mfl else n["manager_name"]}
           for rid, n in names.items()]
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
POSITIONS = ("QB", "RB", "WR", "TE", "K", "DEF", "ALL")
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
    return out


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


def ros(league_id: str, position: str = "ALL", limit: int = 50) -> dict:
    from .applib import ros as ROS
    from .myweek import known_league
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
    ``why`` (the pieces of his points a game, then x games = the total) and ``market_points`` (this week's)."""
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
    market = why.market_points(season, week, ids, scoring)
    for p in players:
        key = p.get("player_key") or p.get("gsis_id")
        g = p.get("ros_games") or 0
        tot = lines.get(str(p.get("gsis_id") if house else key)) or {}
        per = {s: (None if v is None else v / g) for s, v in tot.items()} if g else {}
        ppg = (p["ros_points"] / g) if g and p.get("ros_points") is not None else None
        p["headshot_url"] = _str(head.get(p.get("gsis_id")))
        p["bye_weeks"] = byes.get(str(key), [])
        p["ros_points_per_game"] = None if ppg is None else round(ppg, 2)
        p["per_game"] = why.columns(per, p.get("position")) if per else {}
        p["why"] = why.explain(per, ppg, scoring, p.get("position"), games=g, total=p.get("ros_points")) if per else None
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
            "market_note": ("Sleeper's number is this week's, in this league's scoring, where Sleeper has one; "
                            "the list's totals are ours.")}
# ---- end IA-3


# ---------------------------------------------------------------- plan F3: our record (house leagues)
RECORD_SQL = """select * from analytics.mart_projection_record where league_id = %s and season = %s
                order by scope, week, position"""
RECORD_WHY = "we keep the record for the leagues we score every morning; yours is not one of them yet"


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
            raise NotFound(str(exc) if A.platforms.is_mfl(league_id) else f"no Sleeper league {league_id}") from exc
        except A.SleeperUnavailable:
            pass                                      # Sleeper down: still an honest "not kept" answer
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
    return {"league_id": league_id, "available": True, "season": season, "from_week": first,
            "weeks": [row(r.to_dict()) for _, r in weeks.iterrows()], "summary": summary,
            "notice": None if not rec.empty else ("No week on the record yet: the record starts the first week Sleeper's "
                                                 "projections are archived before kickoff.")}


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
    return player.player_card(league_id, gsis, od=PlayerContext(league_id, exclude_reference=exclude_reference))


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


def mfl_scoring_note(league: dict) -> str:
    """The plain-words note under an MFL league's card: how its lineup and scoring were read."""
    m = league.get("mfl") or {}
    slots = [x for x in league.get("roster_positions") or [] if x != "BN"]
    counts: dict[str, int] = {}
    for x in slots:
        counts[x] = counts.get(x, 0) + 1
    lineup = ", ".join(f"{n} {_SLOT_WORDS.get(k, k)}" if n > 1 else _SLOT_WORDS.get(k, k) for k, n in counts.items())
    bits = [f"Lineup read as {lineup}."]
    sn = m.get("slots") or {}
    if sn.get("ranges"):
        rng = ", ".join(f"{v} {k}s" for k, v in sn["ranges"].items())
        bits.append(f"Your league lets you start {rng}: the spots beyond each minimum count as FLEX.")
    if sn.get("idp"):
        bits.append("Defensive players (" + ", ".join(sn["idp"]) + ") are not projected here; those spots are left out.")
    rep = m.get("scoring") or {}
    for a in rep.get("approximated") or []:
        bits.append(a[:1].upper() + a[1:] + ".")
    if rep.get("unpriced"):
        bits.append("Not counted in the projections: " + ", ".join(rep["unpriced"]) + ".")
    return " ".join(bits)


def mfl_extras(league_id: str, league: dict) -> dict:
    mf = A.sleeper().mfl
    return {"mfl_unmapped": mf.unmapped(league_id), "mfl_mapped_by": mf.mapped_by(league_id),
            "mfl_scoring_note": mfl_scoring_note(league)}


def mfl_league(text: str) -> dict:
    """`/api/leagues?mfl=<link or id>`: the league card (name, size, scoring), its teams for the picker (MFL has no
    username lookup without a login), the team an `F=0004` in the link names, the players without a Sleeper id."""
    from league_lab.mfl_client import parse_link
    try:
        lid, fid, _year = parse_link(text)
        key = A.check_id(f"mfl:{lid}")
        sl = A.sleeper()
        league = sl.league(key)
        rosters, users = sl.rosters(key), sl.users(key)
    except A.LeagueNotFound as exc:
        raise NotFound(str(exc)) from exc
    except A.SleeperUnavailable as exc:
        raise SleeperDown(str(exc)) from exc
    names = A.team_names(rosters, users)
    teams = [{"roster_id": rid, "team_name": n["team_name"], "manager_name": None} for rid, n in sorted(names.items())]
    pick = next((r["roster_id"] for r in rosters if fid is not None and str(r.get("owner_id")) == fid), None)
    lg = {"league_id": key, "name": league.get("name"), "season": int(league["season"]),
          "total_rosters": league.get("total_rosters"), "scoring_label": A.scoring_label(league),
          "url": (league.get("mfl") or {}).get("url"), "platform": "mfl"}
    n_players = sum(len(r.get("players") or []) for r in rosters)
    unmapped = sl.mfl.unmapped(key)
    return {"platform": "mfl", "league": lg, "teams": teams, "roster_id": pick, "unmapped": unmapped,
            "players": n_players, "mapped": n_players - len(unmapped), "scoring_note": mfl_scoring_note(league)}


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
