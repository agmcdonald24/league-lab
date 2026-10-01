"""My Week for ANY Sleeper league (plan E3 spike): served without that league in the database.

`/api/my-week?league=<id>&team=<roster_id>` falls through to here when the league is not a current-season league of
the database (or `source=sleeper` asks for this path). `league_lab.anyleague` fetches the league, its rosters and
users from Sleeper (`LEAGUE_LAB_SLEEPER_FIXTURES=<dir>` reads fixtures instead), prices the NFL-wide stat lines in
the league's scoring, approximates the ranges from the nearest fitted league, and solves the lineup with the
nightly's own code (`lineup.build`); it returns the frame `cards.lineup_rows` returns, so the cards, the lineup
table and "How to read this" come from `app/lib/cards.py` exactly as on the database path (`myweek.cards_from_rows`).

Same JSON shape as `myweek.my_week`, plus `source: "sleeper"` and `on_demand`: the range reference league, the
players Sleeper has that `player_id_map` does not (unvalued), the scoring keys the projection cannot price, where
K / DEF values came from, and the timings. Not served here (they need the league's history in the database): the
league rank in the league line, the week's opponent (Sleeper's matchups endpoint; next step), Sleeper's weekly
lineup lists (the nightly prefers them for a week Sleeper has opened).
"""

from __future__ import annotations

import time

import pandas as pd
from league_lab import anyleague as A

from .applib import cards
from .db import query
from .myweek import NotFound, _num, _str, cards_from_rows, howto, lineup

MOVERS_SQL = """select t.gsis_id, t.player_name, t.position, t.tags, t.momentum
                from analytics.mart_player_trend_tags t
                where t.season = %s and t.gsis_id = any(%s) and t.opportunity_trend in ('rising', 'falling')
                order by abs(t.momentum) desc limit 9"""


class SleeperDown(RuntimeError):
    pass


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
        od = A.lineup_rows(query, league_id, int(roster_id), week, as_of=as_of, client=client,
                           exclude_reference=exclude_reference)
        rosters, users = client.rosters(league_id), client.users(league_id)
    except A.LeagueNotFound as exc:
        raise NotFound(str(exc)) from exc
    except A.SleeperUnavailable as exc:
        raise SleeperDown(str(exc)) from exc
    names = A.team_names(rosters, users).get(int(roster_id), {})
    rec = A.records(rosters).get(int(roster_id))
    rows = od.rows
    out: dict = {"league_id": league_id, "league_name": league.get("name"), "season": season, "scoring_label": None,
                 "roster_id": int(roster_id), "team_name": names.get("team_name"), "manager_name": _str(names.get("manager_name")),
                 "week": week, "record": rec, "opponent": None, "source": "sleeper"}
    bits = [f"**{out['team_name']}**"]
    if rec:
        bits.append(f"{rec['wins']}-{rec['losses']}, #{rec['standing']} in the league")
    out["summary"] = " · ".join(bits)
    out["league_line"] = cards.league_line(league_id, int(roster_id), week, rows) if not rows.empty else ""
    lv = rows.loc[rows["role"] == "starter", "lineup_value"].dropna() if not rows.empty else pd.Series(dtype=float)
    out["lineup_value"] = None if lv.empty else float(lv.iloc[0])
    t1 = time.perf_counter()
    out["notice"], out["cards"] = cards_from_rows(league_id, int(roster_id), week, season, rows)
    t2 = time.perf_counter()
    out["lineup"], out["lineup_full"] = lineup(rows)
    out["howto"] = howto()
    gs = sorted({g for g in rows["gsis_id"].dropna()}) if not rows.empty else []
    mv = query(MOVERS_SQL, (season, gs)) if gs else pd.DataFrame()
    out["movers"] = [{"gsis_id": _str(r.gsis_id), "player_name": r.player_name, "position": r.position,
                      "tags": _str(r.tags), "momentum": _num(r.momentum)} for r in mv.itertuples()]
    t3 = time.perf_counter()
    timings = dict(od.timings_ms)
    timings.update({"cards": round((t2 - t1) * 1000, 1), "rest": round((t3 - t2) * 1000, 1),
                    "request_total": round((t3 - t0) * 1000, 1)})
    out["on_demand"] = {
        "range_method": A.RANGE_METHOD, "range_reference_league": od.reference_league,
        "unmapped_players": od.unmapped_players, "unmapped_scoring_keys": od.scoring.get("unmapped", []),
        "not_projected_keys": od.scoring.get("not_projected", []), "kd_value_source": od.kd_sources,
        "stat_line_mismatches": od.mismatched_lines, "sleeper_calls": od.sleeper_calls, "timings_ms": timings,
    }
    return out
