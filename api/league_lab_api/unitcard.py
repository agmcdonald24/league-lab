"""A team defense's card (Wave I-P fix round, IP-4): ``GET /api/player/{code}`` for a team code answered with the card
shape the web renders for a kicker — the head (this week's projection and its range, the opponent and kickoff), the
Projection and Availability sections, the schedule, and his points by week (no ratings: they cover QB / RB / WR / TE).

Search returns a defense as ``gsis_id: "DEN"`` and Team / lineup rows link units to ``/player/<code>``; before this the
API answered 404 for every one. The numbers are the ones the app already prices a DEF with: this week's projection and
range from the league's own rows (a house league's ``mart_player_week_projections``) or the K / DEF board priced in its
scoring on request (``ondemand.PlayerContext.projection`` — My Week's and the waivers' path); his points by week are
``mart_kd_week``'s outcomes priced in the league's scoring (``kdef.unit_points``, the kd model's own pricing). Codes are a
closed set (the 32 Sleeper defense codes, plus ``LA``).
"""

from __future__ import annotations

import pandas as pd
from league_lab import clock, kdef

from .db import missing_relations, query

# Sleeper's defense codes (unit_id in the K / DEF tables) -> nflverse's team code (dim_game, the marts' `team`)
UNIT_TEAM = {c: c for c in ("ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE", "DAL", "DEN", "DET", "GB", "HOU",
                            "IND", "JAX", "KC", "LAC", "LV", "MIA", "MIN", "NE", "NO", "NYG", "NYJ", "PHI", "PIT", "SEA",
                            "SF", "TB", "TEN", "WAS")} | {"LAR": "LA"}
ALIASES = {"LA": "LAR"}                     # nflverse's Rams code, as a link may carry it
NAMES = {"ARI": "Arizona Cardinals", "ATL": "Atlanta Falcons", "BAL": "Baltimore Ravens", "BUF": "Buffalo Bills",
         "CAR": "Carolina Panthers", "CHI": "Chicago Bears", "CIN": "Cincinnati Bengals", "CLE": "Cleveland Browns",
         "DAL": "Dallas Cowboys", "DEN": "Denver Broncos", "DET": "Detroit Lions", "GB": "Green Bay Packers",
         "HOU": "Houston Texans", "IND": "Indianapolis Colts", "JAX": "Jacksonville Jaguars", "KC": "Kansas City Chiefs",
         "LAR": "Los Angeles Rams", "LAC": "Los Angeles Chargers", "LV": "Las Vegas Raiders", "MIA": "Miami Dolphins",
         "MIN": "Minnesota Vikings", "NE": "New England Patriots", "NO": "New Orleans Saints", "NYG": "New York Giants",
         "NYJ": "New York Jets", "PHI": "Philadelphia Eagles", "PIT": "Pittsburgh Steelers", "SEA": "Seattle Seahawks",
         "SF": "San Francisco 49ers", "TB": "Tampa Bay Buccaneers", "TEN": "Tennessee Titans",
         "WAS": "Washington Commanders"}
ET = "America/New_York"

HOUSE_PROJ_SQL = """select week, proj_points, p10, p90, opponent, is_home, frozen_source
                    from analytics.mart_player_week_projections
                    where league_id = %s and position = 'DEF' and team = %s and season = %s and week <= %s
                    order by week"""
REF_PROJ_SQL = """select distinct on (week) week, proj_points, p10, p90, frozen_source
                  from ops.kd_ranges
                  where scoring_name = %s and season = %s and week <= %s and unit_id = %s and position = 'DEF'
                  order by week, (frozen_source is not null) desc, fitted_at desc nulls last"""
GAMES_SQL = "select * from analytics.mart_kd_week where position = 'DEF' and unit_id = %s and season = %s"
SCHED_SQL = """select g.week, g.kickoff_at, g.home_team = %s as is_home,
                      case when g.home_team = %s then g.away_team else g.home_team end as opponent
               from analytics.dim_game g
               where g.season = %s and g.season_type = 'REG' and %s in (g.home_team, g.away_team)
               order by g.week"""
HOWTO = ("- **Projection** is this week's projected points for the team defense in {league} scoring: its sacks, "
         "takeaways, touchdowns and points allowed as the K / DEF model projects them, priced in this scoring. The "
         "**low-end** and **high-end outcomes** are a modeled bad week and good week (one week in ten below / above).\n"
         "- **Points by week** are what the defense scored in this scoring: its sacks, interceptions, fumble "
         "recoveries, touchdowns, safeties, blocked kicks and points allowed, priced like the league prices them.\n"
         "- Ratings cover quarterbacks, running backs, receivers and tight ends.")


def unit_code(key: str | None) -> str | None:
    """The Sleeper defense code for ``key`` (``DEN``, ``LAR``; ``LA`` -> ``LAR``), or None: a closed set."""
    if not isinstance(key, str) or not 2 <= len(key) <= 3:
        return None
    k = ALIASES.get(key.upper(), key.upper())
    return k if k in UNIT_TEAM else None


def _num(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else round(f, 2)


def _metric(label: str, value: str, help: str | None = None) -> dict:
    return {"label": label, "value": value, "delta": None, "trend": None, "help": help}


def week_points(code: str, season: int, scoring: dict) -> list[dict]:
    """His points by week this season in ``scoring`` (played weeks), the opponent and home / away."""
    if missing_relations(("mart_kd_week",)):
        return []
    g = query(GAMES_SQL, (code, int(season)))
    if g.empty:
        return []
    g["played"] = g["played"].fillna(False).astype(bool)
    try:
        pts = kdef.unit_points(g, "DEF", scoring)
    except Exception:  # noqa: BLE001 - a scoring the K / DEF pricer cannot read: no points (unknown), never a 500
        return []
    meta = g[["week", "opponent", "is_home"]].drop_duplicates("week").set_index("week")
    out = []
    for r in pts.sort_values("week").itertuples(index=False):
        m = meta.loc[int(r.week)] if int(r.week) in meta.index else None
        out.append({"season": int(season), "season_type": "REG", "week": int(r.week), "played": True,
                    "points": _num(r.points), "expected_points": None,
                    "opponent": m["opponent"] if m is not None else None,
                    "is_home": bool(m["is_home"]) if m is not None and pd.notna(m["is_home"]) else None})
    return out


def past_projections(code: str, league: str, ctx, week: int) -> list[dict]:
    """The projection made before each week (the frozen board), a house league's rows or a reference scoring's."""
    from . import refleague
    rows = pd.DataFrame()
    try:
        if ctx.house:
            rows = query(HOUSE_PROJ_SQL, (league, UNIT_TEAM[code], ctx.season, int(week)))
        elif refleague.is_reference(league):
            from .ratings import _ref_scoring
            seed = _ref_scoring(league)
            if seed:
                rows = query(REF_PROJ_SQL, (seed, ctx.season, int(week), code))
    except Exception:  # noqa: BLE001 - no board on this copy: the points alone
        rows = pd.DataFrame()
    return [{"week": int(r.week), "proj_points": _num(r.proj_points), "p10": _num(r.p10), "p25": None, "p75": None,
             "p90": _num(r.p90), "source": r.frozen_source if isinstance(r.frozen_source, str) else None}
            for r in rows.itertuples(index=False)]


def defense_card(league: str, key: str, team: int | None = None) -> dict:
    from . import ondemand, refleague, research
    code = unit_code(key)
    if code is None:
        raise research.NotFound(f"No player with id `{key}`. Search for him above.")
    ctx = research.context(league)
    season, week = ctx.season, ctx.week
    nfl = UNIT_TEAM[code]
    name = NAMES.get(code, code)
    # this week's projection and range: the league's own row (house) or the K / DEF board priced in its scoring
    proj = None
    if week is not None:
        if ctx.house:
            r = query(HOUSE_PROJ_SQL, (league, nfl, season, int(week)))
            r = r[r["week"] == int(week)]
            proj = r.iloc[0].to_dict() if not r.empty else None
        else:
            try:
                r = ondemand.PlayerContext(league).projection(code, "DEF", int(week))
                proj = r.iloc[0].to_dict() if not r.empty else None
            except Exception:  # noqa: BLE001 - no board for this league right now: no projection (a dash), never a 500
                proj = None
    sched = query(SCHED_SQL, (nfl, nfl, season, nfl))
    projection = {"title": f"**Projection** — week {week}, {ctx.league_name} scoring" if week else "**Projection**",
                  "blocks": []}
    pp = _num(proj.get("proj_points")) if proj else None
    if week is None:
        projection["blocks"].append({"kind": "unavailable", "text": "the regular season is over."})
    elif pp is not None:
        ms = [_metric("Projected", f"{pp:.1f}")]
        if _num(proj.get("p10")) is not None and _num(proj.get("p90")) is not None:
            ms += [_metric("Floor", f"{float(proj['p10']):.1f}", "One week in ten it scores less"),
                   _metric("Ceiling", f"{float(proj['p90']):.1f}", "One week in ten it scores more")]
        projection["blocks"].append({"kind": "metrics", "metrics": ms})
    else:
        bye = not sched.empty and int(week) not in set(sched["week"].astype(int))
        projection["blocks"].append({"kind": "unavailable", "text": f"{nfl} is on bye in week {week}." if bye else
                                     "no projection for this defense this week (this league's lineup has no DEF spot, "
                                     "or the board has no line for it)."})
    game = sched[sched["week"] == week] if week is not None and not sched.empty else pd.DataFrame()
    if not game.empty:
        g = game.iloc[0]
        projection["blocks"].append({"kind": "markdown", "text": f"Next: week {week} {'vs' if g['is_home'] else '@'} {g['opponent']}"})
    lines, locked = [], False
    if not sched.empty:
        byes = [w for w in range(1, max(18, int(sched["week"].max())) + 1) if w not in set(sched["week"].astype(int))]
        if byes:
            lines.append(f"Bye: week {byes[0]}" + (" (done)." if week is not None and byes[0] < week else "."))
    if not game.empty:
        k = pd.Timestamp(game.iloc[0]["kickoff_at"])
        kick = k.tz_convert(ET)
        if k <= pd.Timestamp(clock.now()):
            locked = True
            lines.append(f"🔒 **Locked** for week {week}: its game kicked off {kick:%a %b %-d, %-I:%M %p} ET.")
        else:
            lines.append(f"Week {week} kickoff {kick:%a %b %-d, %-I:%M %p} ET — not locked yet.")
    owner = None
    if not refleague.is_reference(league) and not ctx.house:
        try:
            owner = ondemand.PlayerContext(league).availability(code)
        except Exception:  # noqa: BLE001 - whose team it is: left out when the provider does not answer
            owner = None
    if owner and owner.get("rostered_by_team"):
        lines.insert(0, f"Rostered by **{owner['rostered_by_team']}**.")
    elif owner and owner.get("is_free_agent"):
        lines.insert(0, "**Free agent** — nobody in this league has it.")
    availability = {"title": "**Availability**", "blocks": [{"kind": "markdown", "text": "  \n".join(lines)}] if lines else []}
    out = {
        "gsis_id": code, "player_name": name, "position": "DEF", "team": nfl, "headshot_url": None, "unit": True,
        "header": f"DEF · {nfl}", "league_id": league, "league_name": ctx.league_name, "season": season, "week": week,
        "rostered_by_roster_id": (owner or {}).get("rostered_by_roster_id"), "is_free_agent": bool((owner or {}).get("is_free_agent")),
        "injury_status": None, "locked": locked, "proj_points": pp,
        "sections": {"projection": projection, "availability": availability},
        "howto": HOWTO.format(league=ctx.league_name), "ros": None, "missing": [], "missing_keys": [], "news": [],
        "schedule": [{"week": int(r.week), "opponent": r.opponent, "is_home": bool(r.is_home), "opp_rank": None, "proj": None}
                     for r in sched.itertuples(index=False)],
        "games_played": None, "viewer_roster_id": team,       # his points by week: GET /api/player/{code}/projections
    }
    if refleague.is_reference(league):
        out["foot"] = "Open your league to see who has this defense and what it is worth to your team."
    return out
