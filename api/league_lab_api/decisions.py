"""Wave G (G2): the decisions, on demand — waivers, trades, the Team Hub and the league, for ANY Sleeper league.

`ondemand.py`'s pattern: a house league (a current-season league of the database) is served from the marts the nightly
writes (the numbers the Streamlit pages show); any other league — or `source=sleeper` for a house league — is computed
on request from Sleeper (`league_lab.anyleague`), with the nightly's own engines:

* **Waivers** (`/api/waivers`): `mart_waiver_moves`; on demand, every roster solved for the horizon (this week and the
  next three) on ONE `LineupInputs` (`anyleague.league_weeks`, `lineup.build`), the free agents = Sleeper's directory
  minus every roster (`anyleague.free_agents`: mapped by `player_id_map`, the nightly's filter) valued by
  `lineup._proposed_player`, and `waivers.sweep_roster` — the per-roster step of the nightly's `load_and_sweep`
  (the same function: the claim vs the weakest starter / the best bench, the drop, the ranks).
* **Trades** (`POST /api/trades/evaluate`, `/api/trades/partners`): `trades.evaluate` / `trades.partners` on a
  `RosterBoard` — the Trade Finder page's own calls on `mart_league_roster_horizon` (house), or on the rows solved on
  demand (`anyleague.horizon_frame`: the mart's columns and rules); market = rest-of-season points (MARKET_SQL's sum,
  priced week by week on demand) above the best free agent at the position.
* **Team Hub** (`/api/team`): `mart_league_roster_value` / `_rankings` / `_slot_strength` / `_horizon`; on demand the
  same numbers from every roster solved (the league ranks need every roster: the nightly's cost, per request).
* **League** (`/api/league`): `mart_league_standings` / `_all_play` / `_all_play_week` / `_manager_profile` /
  `_transactions` / `_draft`; on demand from Sleeper's played weeks (`Sleeper.season_matchups`) and transactions
  (`Sleeper.transactions`), the marts' SQL rules in Python.

Words: the Waiver Wire's card and table sentences (`_headline`, `_card`, `_why` ...) and the Trade Finder's
`size_words` / `closest` / `lineup_frame` are functions inside the pages, which cannot be imported (they run Streamlit
at import): `page_functions` compiles just those function definitions from the page file (the `ast` of the page,
nothing else runs) with the API's Streamlit stand-in, so a wording change in the page reaches the API unchanged. The
Team Hub's and League's card sentences are top-level page code: they are quoted here (`words`, marked "quoted from
app/pages/…"). `trades.verdict` / `fit_line` / `fairness_line` and `app/lib/ros.py` are called directly.
"""

from __future__ import annotations

import ast
import math
import time
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd
from league_lab import anyleague as A
from league_lab import trades as T
from league_lab import waivers as W
from league_lab.lineup import UNVALUED, Player
from league_lab.roster_value import RosterBoard

from . import availability
from .applib import _StreamlitStandIn, blocks, capture, cards, links, ui
from .applib import ros as ROS
from .db import query
from .myweek import NotFound, _num, _str, known_league
from .ondemand import SleeperDown, ros_on_demand
from .settings import ROOT

PAGES = ROOT / "app" / "pages"
POSITIONS = ("QB", "RB", "WR", "TE", "K", "DEF")


class BadRequest(ValueError):
    """A request the engines cannot answer as asked (a package with a player on neither roster ...): 400."""


# ------------------------------------------------------------------------------ the pages' own sentence functions
_page_code: dict[tuple[str, tuple[str, ...]], Any] = {}


def page_functions(page: str, names: tuple[str, ...], **glob) -> dict:
    """The named top-level function definitions of `app/pages/<page>`, compiled from the page's source (its `ast`:
    nothing else in the page runs) into a fresh namespace holding `pd`, the Streamlit stand-in as `st` and `glob`
    (the page globals those functions read, e.g. `name` / `span_words`). Fresh per call: requests run in threads."""
    key = (page, names)
    if key not in _page_code:
        tree = ast.parse((PAGES / page).read_text(), filename=str(PAGES / page))
        defs = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
        missing = set(names) - {d.name for d in defs}
        if missing:
            raise RuntimeError(f"app/pages/{page} has no {sorted(missing)} any more (the API reads its sentences)")
        _page_code[key] = compile(ast.Module(body=defs, type_ignores=[]), str(PAGES / page), "exec")
    ns: dict = {"pd": pd, "st": _StreamlitStandIn(), "T": T, "__name__": f"league_lab_api.page.{page}", **glob}
    exec(_page_code[key], ns)  # noqa: S102 - the repository's own page file, function definitions only
    return ns


WAIVER_FUNCS = ("_f", "_span", "_weeks_helped", "_weeks_text", "_seat_text", "_notes", "_headline", "_card", "_why")
TRADE_FUNCS = ("rank_words", "lineup_frame", "closest", "size_words")


# ------------------------------------------------------------------------------ small helpers
def _int(v) -> int | None:
    f = _num(v)
    return None if f is None else int(f)


def _bool(v) -> bool | None:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    return bool(v)


def house(league_id: str, source: str | None) -> bool:
    """Served from the marts: a current-season league of the database, unless `source=sleeper` asks for the
    on-demand path (the parity tests use it on the house leagues)."""
    return source != "sleeper" and known_league(str(league_id))


def _season_week(league_id: str, sleeper_league: dict | None = None) -> tuple[int, int | None]:
    season = int(sleeper_league["season"]) if sleeper_league is not None else int(cards.league_season(league_id))
    return season, cards.decision_week(season)


BIO_SQL = "select gsis_id, headshot_url, latest_team, position from analytics.dim_player where gsis_id = any(%s)"


def bio(gsis_ids) -> dict[str, dict]:
    """gsis_id -> headshot_url / team / position (dim_player): every player row carries them (the contract)."""
    gs = sorted({g for g in gsis_ids if isinstance(g, str) and g})
    if not gs:
        return {}
    df = query(BIO_SQL, (gs,))
    return {r.gsis_id: {"headshot_url": _str(r.headshot_url), "team": _str(r.latest_team), "position": _str(r.position)}
            for r in df.itertuples()}


def _player(sid, gsis, name, position, team=None, b: dict | None = None) -> dict:
    """One player object: ids, name, position, team, headshot (a team defense: its code is its team, no headshot)."""
    g = _str(gsis)
    info = (b or {}).get(g, {}) if g else {}
    pos = _str(position) or info.get("position")
    tm = _str(team) or info.get("team") or (str(sid) if pos == "DEF" and sid else None)
    return {"sleeper_id": _str(None if sid is None else str(sid)), "gsis_id": g, "player_name": _str(name),
            "position": pos, "team": tm, "headshot_url": info.get("headshot_url")}


def _od(fn, *args, **kwargs):
    """Run an on-demand step: Sleeper's errors become the API's (404 / 502)."""
    try:
        return fn(*args, **kwargs)
    except A.LeagueNotFound as exc:
        raise NotFound(str(exc)) from exc
    except A.SleeperUnavailable as exc:
        raise SleeperDown(str(exc)) from exc


def _sleeper_league(league_id: str) -> tuple[dict, list[dict], list[dict]]:
    def get():
        lid = A.check_id(league_id)
        sl = A.sleeper()
        league = sl.league(lid)
        return league, sl.rosters(lid), sl.users(lid)
    return _od(get)


def _team_check(names: dict[int, dict], team: int | None) -> None:
    if team is not None and int(team) not in names:
        raise NotFound(f"no team {team} in this league")


def _members(league_id: str) -> dict[int, dict]:
    m = query("select roster_id, team_name, manager_name from analytics.dim_league_member where league_id = %s", (league_id,))
    return {int(r.roster_id): {"team_name": r.team_name, "manager_name": _str(r.manager_name)} for r in m.itertuples()}


_memo_cache: dict[tuple, tuple[float, Any]] = {}
MEMO_TTL_S = {"house": 600, "sleeper": 120}      # the marts change once a night; Sleeper's rosters every 10 minutes


def _memo(key: tuple, is_house: bool, fn):
    """A computed answer kept a while (the partner search and the league solve cost a second or two): 10 minutes on a
    house league (the page's own st.cache_data(ttl=600)), 2 minutes on demand (rosters move with claims and trades)."""
    now = time.monotonic()
    hit = _memo_cache.get(key)
    if hit is not None and hit[0] > now:
        return hit[1]
    out = fn()
    if len(_memo_cache) > 256:
        _memo_cache.clear()
    _memo_cache[key] = (now + MEMO_TTL_S["house" if is_house else "sleeper"], out)
    return out


def clear_memo() -> None:
    _memo_cache.clear()


def _page(rows: list, limit: int, offset: int) -> list:
    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))
    return rows[offset: offset + limit]


# ================================================================================== waivers
MOVES_SQL = """select * from analytics.mart_waiver_moves
               where league_id = %s and roster_id = %s
                 and season = (select max(season) from analytics.mart_waiver_moves where league_id = %s)
               order by move_rank nulls first"""
WEAKEST_SQL = """select weakest_slot, weakest_player_name, weakest_gsis_id, weakest_position, weakest_value, weakest_margin,
                        weakest_replacement_name, weakest_replacement_value, lineup_value, bench_value
                 from analytics.mart_league_roster_value where league_id = %s and roster_id = %s"""
WEEK_PROJ_SQL = """select gsis_id, proj_points, p10, p25, p75, p90 from analytics.mart_player_week_projections
                   where league_id = %s and season = %s and week = %s and gsis_id = any(%s)"""
ROS_SQL = """select player_key, ros_points, ros_games, ros_rank_pos, position, from_week, last_week
             from analytics.mart_player_ros_projection where league_id = %s"""
# the Waiver Wire page's "Browse every free agent" (its columns that make the free agent's card), priced this week
FA_SQL = """select a.sleeper_id, a.gsis_id, a.player_name, a.position, a.nfl_team, a.roster_status, a.injury_status,
                   a.games_played, a.ppg_std, a.expected_per_game, a.diff_per_game, a.target_share_l3, a.snap_pct_l3,
                   pr.proj_points, pr.p10, pr.p25, pr.p75, pr.p90
            from analytics.mart_player_availability a
            left join analytics.mart_player_week_projections pr
                   on pr.league_id = a.league_id and pr.gsis_id = a.gsis_id and pr.season = %s and pr.week = %s
            where a.league_id = %s and a.is_free_agent and a.position = any(%s)
              and a.injury_status is distinct from 'Out' and a.injury_status is distinct from 'IR'
              and a.roster_status is distinct from 'RES'"""
# a house league's K / DEF values this week: its own priced rows (the nightly's ops.projections, what the lineups use)
KD_WEEK_SQL = """select gsis_id as unit_id, round(proj_points::numeric, 2)::double precision as proj_points,
                        round(p10::numeric, 2)::double precision as p10, round(p90::numeric, 2)::double precision as p90
                 from ops.projections where league_id = %s and season = %s and week = %s and position = %s"""


def _ros_frame(league_id: str, is_house: bool) -> pd.DataFrame:
    if is_house:
        return query(ROS_SQL, (league_id,))
    return _memo(("ros", str(league_id)), False, lambda: ros_on_demand(league_id)[1])


def _ros_of(ros: pd.DataFrame) -> dict[str, dict]:
    if ros is None or ros.empty:
        return {}
    return {str(r.player_key): {"ros_points": _num(r.ros_points), "ros_games": _int(r.ros_games),
                                "ros_rank_pos": _int(r.ros_rank_pos)} for r in ros.itertuples()}


def waiver_words(row: pd.Series, week: int) -> dict:
    """The Waiver Wire page's sentences for one move (its `_card` and `_why`, run on the row)."""
    ns = page_functions("2_Waiver_Wire.py", WAIVER_FUNCS)
    _, calls = capture(ns["_card"], "", row, week)
    md = [b["text"] for b in blocks(calls) if b["kind"] == "markdown"]
    return {"headline": ns["_headline"](row), "lines": md[1].split("  \n") if len(md) > 1 else [], "why": ns["_why"](row),
            "source": "app/pages/2_Waiver_Wire.py (_card, _headline, _why)"}


def _move(r: pd.Series, week: int, b: dict, proj: dict, ros: dict) -> dict:
    add = _player(r.get("add_sleeper_id"), r.get("add_gsis_id"), r.get("add_name"), r.get("add_position"), r.get("add_team"), b)
    key = add["gsis_id"] or add["sleeper_id"]
    p = proj.get(key, {})
    add.update({"projection": _num(r.get("add_value")), "value_source": _str(r.get("add_value_source")),
                "p10": p.get("p10"), "p25": p.get("p25"), "p75": p.get("p75"), "p90": p.get("p90"),
                "report_status": _str(r.get("add_report_status")), "reason": _str(r.get("add_reason")),
                "games_played": _int(r.get("add_games_played")), "is_no_evidence": _bool(r.get("is_no_evidence")),
                "ros_points": (ros.get(key) or {}).get("ros_points"), "ros_rank_pos": (ros.get(key) or {}).get("ros_rank_pos"),
                "season_points_left": _num(r.get("add_ros_points"))})
    drop = None
    if isinstance(r.get("drop_sleeper_id"), str):
        drop = _player(r.get("drop_sleeper_id"), r.get("drop_gsis_id"), r.get("drop_name"), r.get("drop_position"), None, b)
        dk = drop["gsis_id"] or drop["sleeper_id"]
        drop.update({"projection": _num(r.get("drop_value")), "is_starter": _bool(r.get("drop_is_starter")),
                     "horizon_loss": _num(r.get("drop_horizon_loss")), "season_points_left": _num(r.get("drop_ros_points")),
                     "ros_points": (ros.get(dk) or {}).get("ros_points")})
    gains = r.get("week_gains")
    return {"move_rank": _int(r.get("move_rank")), "add_rank": _int(r.get("add_rank")), "list_kind": r.get("list_kind"),
            "is_best_drop": _bool(r.get("is_best_drop")), "add": add, "drop": drop,
            "weekly_gain": _num(r.get("weekly_gain")), "horizon_gain": _num(r.get("horizon_gain")),
            "week_gains": [_num(g) for g in gains] if isinstance(gains, list | tuple | np.ndarray) else None,
            "add_horizon_gain": _num(r.get("add_horizon_gain")), "lineup_before": _num(r.get("lineup_before")),
            "lineup_after": _num(r.get("lineup_after")), "add_slot": _str(r.get("add_slot")),
            "fills_empty_slot": _bool(r.get("fills_empty_slot")),
            "displaced": None if not isinstance(r.get("displaced_name"), str) else {
                "player_name": r.get("displaced_name"), "position": _str(r.get("displaced_position")),
                "projection": _num(r.get("displaced_value")), "slot": _str(r.get("displaced_slot")),
                "sleeper_id": _str(r.get("displaced_sleeper_id")), "gsis_id": _str(r.get("displaced_gsis_id"))},
            "open_roster_spots": _int(r.get("open_roster_spots")), "words": waiver_words(r, week)}


def _waiver_cards(best: pd.DataFrame, mv: pd.DataFrame, week: int) -> tuple[list[dict], str | None]:
    """The page's cards (quoted from app/pages/2_Waiver_Wire.py: top claim, best cover, the flyer), or its "nothing"
    sentence."""
    if mv.empty:
        return [], None
    lineup_now = _num(mv["lineup_value"].iloc[0]) if "lineup_value" in mv and _num(mv["lineup_value"].iloc[0]) is not None \
        else _num(mv["lineup_before"].iloc[0])
    if (mv["list_kind"] == "nothing").all():
        r = mv.iloc[0]
        why = (" Your roster is over the limit, so no single claim is legal." if _num(r.get("open_roster_spots")) is not None
               and int(r["open_roster_spots"]) < 0 else "")
        n = int(r["horizon_last_week"]) - week + 1
        return [], (f"**Nothing beats what you have.**  \nNo free agent improves your lineup this week or over the next "
                    f"{n} weeks (week-{week} lineup {lineup_now:.1f}).{why}")
    start, cover = best[best["list_kind"] == "start_now"], best[best["list_kind"] == "cover"]
    out, notice = [], None
    if not start.empty:
        out.append(("Top claim", start.iloc[0]))
    else:
        notice = (f"**Nothing on the wire beats this week's lineup** ({lineup_now:.1f} for week {week}).  \n"
                  "The claims below help in a later week: a bye or an injury you can cover now.")
    shown = set(start.head(1)["add_name"])
    if not cover.empty:
        out.append(("Best cover for a coming week", cover.iloc[0]))
        shown.add(cover.iloc[0]["add_name"])
    flyer = best[best["is_no_evidence"].fillna(False).astype(bool) & ~best["add_name"].isin(shown)]
    if not flyer.empty:
        out.append(("Flyer: no games this season yet", flyer.iloc[0]))
    return [{"title": t, "add_sleeper_id": r["add_sleeper_id"], "drop_sleeper_id": _str(r.get("drop_sleeper_id")),
             "move_rank": _int(r["move_rank"])} for t, r in out], notice


def _moves_on_demand(league_id: str, team: int, *, as_of: datetime | None = None) -> tuple[pd.DataFrame, dict]:
    """mart_waiver_moves' rows for one roster of any league, computed now (see the module docstring)."""
    league, rosters, _ = _sleeper_league(league_id)
    season, week = _season_week(league_id, league)
    if week is None:
        return pd.DataFrame(), {"week": None}
    players = _od(A.sleeper().players)
    t0 = time.perf_counter()
    fa = A.free_agents(query, league["league_id"], rosters, players, A.league_scoring(league)[1])
    lw = _od(A.league_weeks, query, league["league_id"], week, as_of=as_of, rest=True, extra_sids=list(fa["sleeper_id"]))
    _team_check(lw.names, team)
    t1 = time.perf_counter()
    lid = lw.league_id
    adds, fa_meta = {}, {}
    slot_types = {s.type for s in W.parse_slots(lw.slots)[0]}
    for r in fa.itertuples():
        row = lw.player_row(r.sleeper_id, gsis=_str(r.gsis_id), position=r.position)
        sp = lw.inp.sleeper.get(r.sleeper_id) or {}
        positions = frozenset(sp.get("fantasy_positions") or [r.position])
        if not any(positions & W.SLOT_ELIGIBILITY[t] for t in slot_types):
            continue
        adds[r.sleeper_id] = [lw.value(r.sleeper_id, w, row) for w in lw.weeks]
        fa_meta[r.sleeper_id] = {"gsis_id": _str(r.gsis_id), "player_name": r.player_name, "position": r.position,
                                 "games_played": _int(r.games_played), "nfl_team": _str(r.nfl_team), "_row": row}
    names = {g: n for g, n in zip(lw.dp.index, lw.dp["player_name"], strict=True)} if not lw.dp.empty else {}

    def named(rows):
        return [{**x, "player_name": names.get(x.get("gsis_id"), x.get("player_name"))} for x in rows]
    week_rows = [named([x for x in lw.roster_rows(team, w) if x["role"] != "empty"]) for w in lw.weeks]
    # each roster player's projected points over the rest of the season, weeks he can play (the nightly reads them
    # from ops.lineups' starter / bench rows; a player is a starter or on the bench exactly when he can play)
    today = {x["sleeper_player_id"]: x for x in lw.inp.current[lid][int(team)]}
    slot_of = A.LU.starter_slots(lw.slots, lw.inp.starters.get((lid, int(team))))
    rest_rows = []
    for w in lw.rest_weeks:
        for sid, cur in today.items():
            row = {**cur, "is_starter": sid in slot_of, "slot": slot_of.get(sid)}
            p = A.LU._proposed_player(lw.inp, lid, w, row, row, {}, True, lw.as_of)
            rest_rows.append({"sleeper_player_id": sid, "value": None if p.value is None else round(float(p.value), 2),
                              "role": "bench" if p.playable else "unplayable", "value_source": p.value_source})
    add_ros: dict[str, float] = {}

    def add_ros_of(sid: str) -> float:
        if sid not in add_ros:
            ps = [lw.value(sid, w, fa_meta[sid]["_row"]) for w in lw.rest_weeks]
            add_ros[sid] = sum(p.value for p in ps if p.playable and not _unvalued(p))
        return add_ros[sid]

    tot0 = lw.total(team, lw.weeks[0])
    key = {"run_at": datetime.now(UTC), "as_of": lw.as_of, "model_version": lw.inp.model_version, "league_id": lid,
           "season": season, "week": lw.weeks[0], "roster_id": int(team), "horizon_weeks": len(lw.weeks),
           "horizon_last_week": lw.weeks[-1], "inputs_fingerprint": None}
    stats: dict = {}
    rows = W.sweep_roster(lw.slots, week_rows, lw.inp.current[lid][int(team)], adds, fa_meta, rest_rows, len(lw.rest_weeks),
                          add_ros_of, key, lw.inp.sleeper, lineup_value=tot0.get("lineup_value"), stats=stats)
    t2 = time.perf_counter()
    df = pd.DataFrame(rows, columns=W.MOVE_COLUMNS)
    if not df.empty:
        df["add_team"] = df["add_sleeper_id"].map(lambda s: (fa_meta.get(s) or {}).get("nfl_team") if isinstance(s, str) else None)
        df["lineup_value"] = tot0.get("lineup_value")
        df["team_name"] = lw.names.get(int(team), {}).get("team_name")
        df["on_current_lineup"], df["inputs_current"] = True, True
    info = {"week": lw.weeks[0], "weeks": lw.weeks, "free_agents": len(adds), "survivors": stats.get("survivors"),
            "timings_ms": {**{f"league.{k}": v for k, v in lw.timings_ms.items()},
                           "free_agents": round((t1 - t0) * 1000 - lw.timings_ms.get("total", 0), 1),
                           "sweep": round((t2 - t1) * 1000, 1), "total": round((t2 - t0) * 1000, 1)},
            "lw": lw, "fa": fa}
    return df, info


def _unvalued(p: Player) -> bool:
    return p.value is None or not math.isfinite(p.value) or p.value_source == UNVALUED


def waivers(league_id: str, team: int | None = None, position: str | None = None, limit: int = 50, offset: int = 0, *,
            source: str | None = None, as_of: datetime | None = None) -> dict:
    t0 = time.perf_counter()
    position = (position or "ALL").upper()
    if position not in (*POSITIONS, "ALL"):
        raise NotFound(f"no position {position} (QB, RB, WR, TE, K, DEF or ALL)")
    is_house = house(league_id, source)
    out: dict = {"league_id": str(league_id), "source": "database" if is_house else "sleeper", "roster_id": team,
                 "position": position, "week": None, "weakest": None, "moves": [], "total_moves": 0, "cards": [],
                 "notice": None, "free_agents": []}
    od_info: dict = {}
    if is_house:
        season, week = _season_week(league_id)
        members = _members(league_id)
        _team_check(members, team)
        mv = query(MOVES_SQL, (league_id, int(team), league_id)) if team is not None else pd.DataFrame()
        if not mv.empty:
            week = int(mv["week"].iloc[0])
        out["team_name"] = members.get(int(team), {}).get("team_name") if team is not None else None
    else:
        league, rosters, users = _sleeper_league(league_id)
        season, week = _season_week(league_id, league)
        names = A.team_names(rosters, users)
        _team_check(names, team)
        out["team_name"] = names.get(int(team), {}).get("team_name") if team is not None else None
        if team is None:
            mv, od_info = pd.DataFrame(), {}
        elif as_of is not None:
            mv, od_info = _moves_on_demand(league_id, int(team), as_of=as_of)
        else:
            mv, od_info = _memo(("moves", str(league_id), int(team)), False, lambda: _moves_on_demand(league_id, int(team)))
        if od_info.get("week"):
            week = od_info["week"]
    out["week"] = week
    if week is None:
        out["notice"] = "The regular season is over: no waiver claims left."
        return out
    # the weakest starter: what a claim has to beat
    if team is not None:
        if is_house:
            wk = query(WEAKEST_SQL, (league_id, int(team)))
            if not wk.empty and isinstance(wk["weakest_slot"].iloc[0], str):
                w = wk.iloc[0]
                out["weakest"] = {"slot": w["weakest_slot"], "player": _player(None, w["weakest_gsis_id"], w["weakest_player_name"],
                                                                               w["weakest_position"], None, bio([w["weakest_gsis_id"]])),
                                  "value": _num(w["weakest_value"]), "margin": _num(w["weakest_margin"]),
                                  "replacement_name": _str(w["weakest_replacement_name"]),
                                  "replacement_value": _num(w["weakest_replacement_value"])}
        elif od_info.get("lw") is not None:
            lw = od_info["lw"]
            tot = lw.total(team, lw.weeks[0])
            if tot.get("weakest_slot"):
                hf = A.horizon_frame(lw)
                s = hf[(hf["roster_id"] == int(team)) & hf["is_this_week"] & (hf["slot"] == tot["weakest_slot"])]
                if not s.empty:
                    s = s.iloc[0]
                    out["weakest"] = {"slot": tot["weakest_slot"],
                                      "player": _player(s["sleeper_player_id"], s["gsis_id"], s["player_name"], s["position"], None,
                                                        bio([s["gsis_id"]])),
                                      "value": _num(s["player_value"]), "margin": _num(tot.get("weakest_margin")),
                                      "replacement_name": _str(s["replacement_name"]), "replacement_value": _num(s["replacement_value"])}
    ros = _ros_of(_ros_frame(league_id, is_house))
    if not mv.empty:
        best = mv[mv["is_best_drop"].fillna(False).astype(bool)].sort_values("add_rank") if "is_best_drop" in mv else mv.iloc[0:0]
        out["cards"], out["notice"] = _waiver_cards(best, mv, int(week))
        shown = best[best["list_kind"] != "nothing"]
        if position != "ALL":
            shown = shown[shown["add_position"] == position]
        out["total_moves"] = int(len(shown))
        page = shown.iloc[max(0, int(offset)): max(0, int(offset)) + max(1, min(int(limit), 500))]
        b = bio(list(page["add_gsis_id"]) + list(page.get("drop_gsis_id", pd.Series(dtype=object))))
        proj = _week_ranges(league_id, season, int(week), page, is_house, od_info)
        out["moves"] = [_move(r, int(week), b, proj, ros) for _, r in page.iterrows()]
        for c in out["cards"]:
            r = mv[(mv["add_sleeper_id"] == c["add_sleeper_id"]) & (mv["move_rank"] == c["move_rank"])].iloc[0]
            c["move"] = _move(r, int(week), bio([r.get("add_gsis_id"), r.get("drop_gsis_id")]), proj, ros)
        out["horizon_last_week"] = _int(mv["horizon_last_week"].iloc[0])
        out["lineup_value"] = _num(mv["lineup_value"].iloc[0]) if "lineup_value" in mv else None
        out["as_of"] = mv["as_of"].iloc[0] if "as_of" in mv else None
        out["inputs_current"] = _bool(mv["inputs_current"].iloc[0]) if "inputs_current" in mv else None
    out["free_agents"] = _free_agents(league_id, season, int(week), position, limit, is_house, od_info, ros)
    out.update(waiver_extras(league_id, team, int(week), is_house, od_info, position))      # H1 (Wave H)
    out = availability.waivers_overlay(out)         # ---- I0-A: no claims of players who cannot play; one QB per team
    if not is_house:
        out["on_demand"] = {k: v for k, v in od_info.items() if k not in ("lw", "fa")}
    out["timings_ms"] = {"request_total": round((time.perf_counter() - t0) * 1000, 1)}
    return out


def _week_ranges(league_id: str, season: int, week: int, page: pd.DataFrame, is_house: bool, od_info: dict) -> dict:
    """player key (gsis; a defense's Sleeper id) -> this week's projection range in the league's scoring."""
    gs = [g for g in page["add_gsis_id"] if isinstance(g, str)] if not page.empty else []
    out: dict[str, dict] = {}
    if is_house:
        if gs:
            for r in query(WEEK_PROJ_SQL, (league_id, season, week, gs)).itertuples():
                out[r.gsis_id] = {"proj_points": _num(r.proj_points), "p10": _num(r.p10), "p25": _num(r.p25),
                                  "p75": _num(r.p75), "p90": _num(r.p90)}
        return out
    lw = od_info.get("lw")
    if lw is None or week not in lw.priced:
        return out
    pr = lw.priced[week]
    for g in gs:
        if g in pr.ranges.index:
            rg = pr.ranges.loc[g]
            out[g] = {q: _num(rg.get(q)) for q in ("p10", "p25", "p75", "p90")}
    for kd in pr.kd.values():
        for r in kd.itertuples():
            out.setdefault(str(r.unit_id), {"p10": _num(r.p10), "p90": _num(r.p90)})
    return out


def _free_agents(league_id: str, season: int, week: int, position: str, limit: int, is_house: bool, od_info: dict,
                 ros: dict) -> list[dict]:
    """The priced free-agent list for the position (all the league starts when ALL), best projection first."""
    limit = max(1, min(int(limit), 500))
    if is_house:
        slots = ui.league_slots(league_id) if hasattr(ui, "league_slots") else list(POSITIONS)
        pos = [p for p in POSITIONS if p in slots] if position == "ALL" else [position]
        df = query(FA_SQL, (season, week, league_id, pos))
        for kd_pos in ("K", "DEF"):
            if kd_pos in pos and not df.empty:
                kd = query(KD_WEEK_SQL, (league_id, season, week, kd_pos)).drop_duplicates("unit_id").set_index("unit_id")
                key = df["gsis_id"].where(df["gsis_id"].notna(), df["sleeper_id"])
                m = df["position"] == kd_pos
                for c in ("proj_points", "p10", "p90"):
                    df.loc[m, c] = key[m].map(kd[c]) if not kd.empty else np.nan
    else:
        lw, fa = od_info.get("lw"), od_info.get("fa")
        if lw is None:
            league, rosters, _ = _sleeper_league(league_id)
            fa = A.free_agents(query, league["league_id"], rosters, _od(A.sleeper().players), A.league_scoring(league)[1])
            pr = A.price_week(query, league["league_id"], *A.league_scoring(league), season, week)
        else:
            pr = lw.priced.get(week)
        df = fa.copy() if fa is not None else pd.DataFrame()
        if not df.empty and position != "ALL":
            df = df[df["position"] == position]
        if not df.empty and pr is not None:
            key = df["gsis_id"].where(df["gsis_id"].notna(), df["sleeper_id"])
            proj = pr.proj.round(2)
            rg = pr.ranges
            df["proj_points"] = key.map(proj)
            for q in ("p10", "p25", "p75", "p90"):
                df[q] = key.map(rg[q]) if q in rg else np.nan
            for kd_pos, kd in pr.kd.items():
                m = df["position"] == kd_pos
                k = kd.set_index("unit_id")
                for c in ("proj_points", "p10", "p90"):
                    df.loc[m, c] = key[m].map(pd.to_numeric(k[c], errors="coerce"))
    if df.empty:
        return []
    df = df.assign(_p=pd.to_numeric(df["proj_points"], errors="coerce")).sort_values(["_p", "player_name"], ascending=[False, True],
                                                                                    na_position="last").head(limit)
    b = bio(df["gsis_id"])
    out = []
    for _, r in df.iterrows():
        k = r["gsis_id"] if isinstance(r["gsis_id"], str) else r["sleeper_id"]
        p = _player(r["sleeper_id"], r["gsis_id"], r["player_name"], r["position"], r.get("nfl_team"), b)
        p.update({"projection": _num(r.get("proj_points")), "p10": _num(r.get("p10")), "p25": _num(r.get("p25")),
                  "p75": _num(r.get("p75")), "p90": _num(r.get("p90")), "injury_status": _str(r.get("injury_status")),
                  "games_played": _int(r.get("games_played")), "ros_points": (ros.get(k) or {}).get("ros_points"),
                  "ros_rank_pos": (ros.get(k) or {}).get("ros_rank_pos")})
        for c in ("ppg_std", "expected_per_game", "diff_per_game", "target_share_l3", "snap_pct_l3"):
            if c in r:
                p[c] = _num(r.get(c))
        out.append(p)
    return out


# ================================================================================== trades
HORIZON_SQL = """select roster_id, week, this_week, horizon_first_week, horizon_last_week, role, slot, slot_type, sleeper_player_id,
                        gsis_id, player_name, position, fantasy_positions, player_value, value_source, lineup_margin, is_locked, reason
                 from analytics.mart_league_roster_horizon where league_id = %s"""
RANKS_SQL = """select roster_id, measure, value from analytics.mart_league_roster_rankings
               where league_id = %s and measure in ('lineup_value', 'horizon_value', 'bench_value')"""
# copied from app/pages/6_Trade_Finder.py free_agent_pool(): the open-spot fill's free agents (house leagues)
FA_POOL_SQL = """select a.sleeper_id, a.gsis_id, a.player_name, a.position, p.week,
                  round(p.proj_points::numeric, 2)::double precision as value, f.report_status, f.roster_status,
                  coalesce(f.team, case when a.position = 'DEF' then a.sleeper_id else a.nfl_team end) as team
           from analytics.mart_player_availability a
           join ops.projections p
             on p.league_id = a.league_id and p.season = %s and p.week = any(%s) and p.gsis_id = coalesce(a.gsis_id, a.sleeper_id)
           left join analytics.mart_player_week_features f on f.gsis_id = a.gsis_id and f.season = p.season and f.week = p.week
           where a.league_id = %s and a.is_free_agent and a.roster_status = 'ACT' and a.sleeper_id is not null
             and a.injury_status is distinct from 'Out' and a.injury_status is distinct from 'IR'"""


class TradeContext:
    """What the Trade Finder page holds before it evaluates: the board (every roster's horizon rows), the market (rest-
    of-season points) and the prices (above the best free agent), the replacement per position, the names, the rest-of-
    season rows, the week and the span words. A house league: the page's own queries; any other: solved on demand."""

    def __init__(self, league_id: str, source: str | None = None, *, as_of: datetime | None = None, market: bool = True):
        self.league_id = str(league_id)
        self.is_house = house(league_id, source)
        self.free_agent_pool = None
        self.window_cache: dict = {}        # ---- IA-2: the windows' boards, the ROS board, Sleeper's week
        if self.is_house:
            members = _members(self.league_id)
            self.names = members
            horizon = query(HORIZON_SQL, (self.league_id,))
            if horizon.empty:
                raise NotFound("no lineups for the weeks ahead yet (the season is over, or the nightly has not run)")
            ls = ui.league_seasons(self.league_id)
            lrow = ls.loc[ls["league_id"] == self.league_id].iloc[0]
            self.slots = list(lrow["roster_positions"] or [])
            self.season = int(lrow["season"])
            self.horizon = horizon
            self.this_week = int(horizon["this_week"].iloc[0])
            first, last = int(horizon["horizon_first_week"].iloc[0]), int(horizon["horizon_last_week"].iloc[0])
            self.points = self.replacement = self.repl_name = {}
            if market:
                mr = query(T.MARKET_SQL, (self.league_id, self.season, self.this_week))
                self.points = dict(zip(mr["player_key"], mr["season_points"], strict=True)) if not mr.empty else {}
                rr = query(T.REPLACEMENT_SQL, (self.league_id, self.season, self.this_week, self.league_id))
                self.replacement = dict(zip(rr["position"], rr["replacement"], strict=True)) if not rr.empty else {}
                self.repl_name = dict(zip(rr["position"], rr["replacement_name"], strict=True)) if not rr.empty else {}
            self.lw = None
        else:
            league, rosters, users = _sleeper_league(self.league_id)
            self.names = A.team_names(rosters, users)
            self.season, week = _season_week(self.league_id, league)
            if week is None:
                raise NotFound("the regular season is over: no trades to evaluate")
            players = _od(A.sleeper().players)
            fa = A.free_agents(query, league["league_id"], rosters, players, A.league_scoring(league)[1]) if market else None
            self.lw = _od(A.league_weeks, query, league["league_id"], week, as_of=as_of, rest=market,
                          extra_sids=list(fa["sleeper_id"]) if fa is not None else ())
            self.slots = self.lw.slots
            self.horizon = A.horizon_frame(self.lw)
            self.this_week = self.lw.weeks[0]
            first, last = self.lw.weeks[0], self.lw.weeks[-1]
            self.points, self.replacement, self.repl_name = {}, {}, {}
            if market:
                self.points = market_points(self.lw)
                self.replacement, self.repl_name = replacement_level(self.lw, fa, self.points)
            self.fa = fa
        # ---- I0-A: this week's availability on the board (an Out player is worth 0 this week; the board re-solves)
        self.horizon, self.out_now = availability.horizon_overlay(self.horizon, self.this_week)
        # ---- end I0-A
        self.first_w, self.last_w = first, last
        self.span_words = f"weeks {first}–{last}" if last > first else f"week {first}"
        self.board = RosterBoard(self.horizon.to_dict("records"), tuple(self.slots))
        self.market = T.market_by_player(self.board, self.points)
        self.prices = T.price_by_player(self.board, self.market, self.replacement)
        h = self.horizon
        self.info = h.sort_values("week").drop_duplicates("sleeper_player_id").set_index("sleeper_player_id")
        self.now_rows = h[h["week"] == self.this_week].set_index("sleeper_player_id")
        self._bio = bio(h["gsis_id"])

    # the page's helpers (app/pages/6_Trade_Finder.py: name / gsis / pos / link / week_value)
    def name(self, pid) -> str:
        i = self.info
        return str(i.at[pid, "player_name"]) if pid in i.index and pd.notna(i.at[pid, "player_name"]) else str(pid)

    def gsis(self, pid):
        i = self.info
        return i.at[pid, "gsis_id"] if pid in i.index and pd.notna(i.at[pid, "gsis_id"]) else None

    def pos(self, pid) -> str:
        i = self.info
        return str(i.at[pid, "position"]) if pid in i.index and pd.notna(i.at[pid, "position"]) else ""

    def link(self, pid) -> str:
        return ui.player_link(self.gsis(pid), self.name(pid))

    def week_value(self, pid):
        if pid not in self.now_rows.index:
            return None, None
        r = self.now_rows.loc[pid]
        if isinstance(r, pd.DataFrame):
            r = r.iloc[0]
        if r["role"] == "unplayable":
            return None, (r["reason"] or "can't play")
        return (float(r["player_value"]) if pd.notna(r["player_value"]) else None), None

    def team(self, rid) -> str:
        return (self.names.get(int(rid)) or {}).get("team_name") or f"Team {rid}"

    def player(self, pid) -> dict:
        p = _player(pid, self.gsis(pid), self.name(pid), self.pos(pid), None, self._bio)
        v, why = self.week_value(pid)
        p.update({"this_week": v, "cannot_play": why, "market_price": T.whole(self.prices[pid]) if pid in self.prices else None,
                  "season_points": T.whole(self.market[pid]) if pid in self.market else None, "roster_id": self.board.owner(pid)})
        if str(pid) in getattr(self, "out_now", {}):      # ---- I0-A: worth 0 this week, the status says why
            p["this_week"], p["cannot_play"] = 0.0, self.out_now[str(pid)]
        return p

    def resolve(self, ids) -> list[str]:
        """Sleeper ids as the board keys them; a gsis id is accepted too (mapped through the board's rows)."""
        by_gsis = {str(g): s for s, g in zip(self.info.index, self.info["gsis_id"], strict=True) if isinstance(g, str)}
        return [str(i) if self.board.owner(str(i)) is not None else by_gsis.get(str(i), str(i)) for i in (ids or [])]

    def fa_pool(self, weeks: tuple[int, ...]) -> tuple[dict, dict]:
        """The open-spot fill's free agents per week (the page's free_agent_pool; on demand: the same rule on the
        free agents valued by lineup._proposed_player)."""
        if self.is_house:
            return _house_fa_pool(self.league_id, self.season, weeks)
        pool: dict[str, dict[int, Player]] = {}
        meta: dict[str, dict] = {}
        for r in (self.fa.itertuples() if self.fa is not None else []):
            row = self.lw.player_row(r.sleeper_id, gsis=_str(r.gsis_id), position=r.position)
            for w in weeks:
                p = self.lw.value(r.sleeper_id, w, row)
                if p.value is not None and p.value_source != UNVALUED:
                    pool.setdefault(r.sleeper_id, {})[int(w)] = p
            meta[r.sleeper_id] = {"player_name": r.player_name, "position": r.position, "gsis_id": r.gsis_id}
        return pool, meta


def _house_fa_pool(league_id: str, season: int, weeks: tuple[int, ...]) -> tuple[dict, dict]:
    """Copied from app/pages/6_Trade_Finder.py free_agent_pool() (the open-spot fill on a house league)."""
    fa = query(FA_POOL_SQL, (season, list(weeks), league_id))
    games = query("""select home_team, away_team, kickoff_at from analytics.dim_game
                     where season = %s and week = %s and season_type = 'REG'""", (season, weeks[0]))
    kick = {}
    for g in games.itertuples():
        kick[g.home_team] = kick[g.away_team] = pd.Timestamp(g.kickoff_at)
    now = pd.Timestamp(datetime.now(UTC))
    pool: dict[str, dict[int, Player]] = {}
    meta: dict[str, dict] = {}
    for r in fa.itertuples():
        t = {"LAR": "LA"}.get(r.team, r.team)
        why = ("Out" if r.report_status in ("Out", "Doubtful") else "NFL injured reserve" if r.roster_status == "RES"
               else "game started" if int(r.week) == weeks[0] and t in kick and kick[t] <= now else None)
        pool.setdefault(r.sleeper_id, {})[int(r.week)] = Player(
            id=r.sleeper_id, position=r.position, value=r.value, value_source="proj_points", playable=why is None, reason=why)
        meta[r.sleeper_id] = {"player_name": r.player_name, "position": r.position, "gsis_id": r.gsis_id}
    return pool, meta


def market_points(lw: A.LeagueWeeks) -> dict[str, float]:
    """MARKET_SQL on demand: per player key (gsis; a defense's Sleeper id) Σ over this week to the last regular-season
    week of his projection rounded to the cent (every projected week, injured or benched)."""
    pts: dict[str, float] = {}
    for w in lw.rest_weeks:
        pr = lw.priced[w]
        for g, v in pr.proj.round(2).items():
            if pd.notna(v):
                pts[g] = pts.get(g, 0.0) + float(v)
        for kd in pr.kd.values():
            for r in kd.itertuples():
                v = _num(r.proj_points)
                if v is not None:
                    pts[str(r.unit_id)] = pts.get(str(r.unit_id), 0.0) + round(v, 2)
    return {k: round(v, 2) for k, v in pts.items()}


def replacement_level(lw: A.LeagueWeeks, fa: pd.DataFrame | None, points: dict[str, float]) -> tuple[dict, dict]:
    """REPLACEMENT_SQL on demand: per position the most season points of a free agent (active NFL roster or a
    defense, not Out / IR — `anyleague.free_agents`' filter), and his name."""
    best: dict[str, tuple[float, str, str]] = {}
    for r in (fa.itertuples() if fa is not None else []):
        if r.position not in POSITIONS:
            continue                                   # REPLACEMENT_SQL's positions (mart_player_availability's)
        k = r.gsis_id if isinstance(r.gsis_id, str) else r.sleeper_id
        v = points.get(k)
        if v is None:
            continue
        cur = best.get(r.position)
        if cur is None or (v, ) > (cur[0], ) or (v == cur[0] and r.sleeper_id < cur[2]):
            best[r.position] = (v, r.player_name, r.sleeper_id)
    return {p: v[0] for p, v in best.items()}, {p: v[1] for p, v in best.items()}


def _side(ctx: TradeContext, side: T.Side) -> dict:
    return {"roster_id": side.roster_id, "team_name": ctx.team(side.roster_id), "gives": [ctx.player(p) for p in side.gives],
            "gets": [ctx.player(p) for p in side.gets], "weeks": list(side.weeks),
            "before": {"this_week": T._r2(side.before[0]), "horizon": side.before_horizon, "bench": side.bench_before,
                       "by_week": [T._r2(x) for x in side.before]},
            "after": {"this_week": T._r2(side.after[0]), "horizon": side.after_horizon, "bench": side.bench_after,
                      "by_week": [T._r2(x) for x in side.after]},
            "gain_week": side.gain_week, "gain_horizon": side.gain_horizon,
            "cuts": [{"player": ctx.player(c.player_id), "horizon_loss": c.horizon_loss,
                      "season_points": None if c.market is None else T.whole(c.market)} for c in side.cuts],
            "limit": side.limit, "size_before": side.size_before, "size_after": side.size_after, "opened": side.opened,
            "fill": None if side.fill is None else {"sleeper_id": side.fill.player_id, "week_gains": list(side.fill.week_gains),
                                                     "horizon_gain": side.fill.horizon_gain},
            "price_out": side.price_out, "price_in": side.price_in, "points_out": side.points_out, "points_in": side.points_in,
            "starts": [ctx.player(p) for p in side.starts], "sits": [ctx.player(p) for p in side.sits]}


def _ros_package(ctx: TradeContext, give: list[str], get: list[str]) -> dict | None:
    """The page's ros_line: the package's rest of season (app/lib/ros.py: package_points, package_sentence)."""
    try:
        rows = _ros_frame(ctx.league_id, ctx.is_house)
    except Exception:  # noqa: BLE001 - rest of season is a side line, never the evaluation's failure
        return None
    if rows is None or rows.empty:
        return None
    window = ROS.weeks_span(rows["from_week"].iloc[0], rows["last_week"].iloc[0])

    def key(pid) -> str:
        return str(ctx.gsis(pid) or pid)
    out, _, miss_o = ROS.package_points(rows, [key(x) for x in give])
    inc, _, miss_i = ROS.package_points(rows, [key(x) for x in get])
    by_key = {key(x): x for x in [*give, *get]}
    words = ROS.package_sentence(out, inc, window, [ctx.name(by_key[k]) for k in [*miss_o, *miss_i]])
    return {"give": out, "get": inc, "window": window, "words": words}


def trade_context(league_id: str, source: str | None = None, *, as_of: datetime | None = None) -> TradeContext:
    """The Trade Finder's inputs for a league, kept a while (`_memo`): the board, the market, the names."""
    if as_of is not None:
        return TradeContext(league_id, source, as_of=as_of)
    is_house = house(league_id, source)
    return _memo(("trade_context", str(league_id), is_house), is_house, lambda: TradeContext(league_id, source))


# ---- IA-2 (Wave I-A): the window, the interest dial, the sanity bound ---------------------------------------------
# "Why weeks 4–7?" had no answer on the page. A trade is now priced over a window the user picks: this week, the next
# four (the default: far enough to matter, near enough to trust), the rest of the season or the playoffs. The board
# holds the next four weeks (mart_league_roster_horizon / the on-demand solve); a longer window adds a row per player
# and week past them from the rest-of-season board (mart_player_ros_projection.weeks_json for a house league,
# `anyleague.ros_table` - load_window + skill_window, one round of queries - on demand): his projection that week in
# this league's scoring, on the bench (the solver picks the starters), or unplayable on a bye; a player in the IR
# slot, on the taxi squad, on NFL injured reserve or with no NFL team stays so (his state in the board's last week:
# the rest of season does not guess a return). The trade engine is the same; the gains are the window's.
WINDOWS = ("week", "next4", "ros", "playoffs")
WINDOW_LABELS = {"week": "This week", "next4": "Next 4", "ros": "Rest of season", "playoffs": "Playoffs"}
WINDOW_WHY = {"week": "this week only: the lineup you set for Sunday",
              "next4": "the next four weeks: far enough to matter, near enough to trust",
              "ros": "every week left to this league's final, playoffs included: the longest view, the least sure",
              "playoffs": "the weeks of this league's playoffs: what the trade does when it counts most"}
CARRY_REASONS = frozenset({"IR slot", "taxi squad", "NFL injured reserve", "no NFL team"})
ROS_WEEKS_SQL = """select player_key, ros_points, weeks_json, from_week, last_week, playoff_week_start
                   from analytics.mart_player_ros_projection where league_id = %s"""


def check_window(window: str | None) -> str:
    w = (window or "next4").lower()
    if w not in WINDOWS:
        raise BadRequest(f"no window {window} (week, next4, ros or playoffs)")
    return w


def _weeks_json(v) -> list:
    if isinstance(v, str):
        import json as _json
        v = _json.loads(v)
    return list(v) if isinstance(v, list | tuple | np.ndarray) else []


def ros_weeks(ctx: TradeContext) -> dict:
    """The rest-of-season board for the context's league: {"points": key -> ros points, "weeks": key -> {week: pts},
    "first", "last", "playoff_start"} (empty dicts / None when there is no board). Kept on the context."""
    if "ros_weeks" in ctx.window_cache:
        return ctx.window_cache["ros_weeks"]
    try:
        df = query(ROS_WEEKS_SQL, (ctx.league_id,)) if ctx.is_house else _ros_frame(ctx.league_id, False)
    except Exception:  # noqa: BLE001 - no rest-of-season board: the longer windows say so, the others carry on
        df = pd.DataFrame()
    out: dict = {"points": {}, "weeks": {}, "first": None, "last": None, "playoff_start": None}
    if df is not None and not df.empty:
        head = df.iloc[0]
        out["first"], out["last"] = _int(head.get("from_week")), _int(head.get("last_week"))
        out["playoff_start"] = _int(head.get("playoff_week_start"))
        for r in df.itertuples():
            k = str(r.player_key)
            if _num(r.ros_points) is not None:
                out["points"][k] = float(r.ros_points)
            out["weeks"][k] = {int(w): float(v) for w, v in _weeks_json(getattr(r, "weeks_json", None)) if v is not None}
    ctx.window_cache["ros_weeks"] = out
    return out


def window_board(ctx: TradeContext, window: str) -> tuple[RosterBoard, tuple[int, ...], str]:
    """(the board, the window's weeks, its span words: "weeks 4–16") for a window (see the block's comment)."""
    window = check_window(window)
    key = ("board", window)
    if key in ctx.window_cache:
        return ctx.window_cache[key]
    weeks = list(ctx.board.weeks)
    board = ctx.board
    if window == "week":
        weeks = [ctx.this_week]
    elif window in ("ros", "playoffs"):
        rw = ros_weeks(ctx)
        if rw["last"] is None:
            raise BadRequest("the rest-of-season board is not ready for this league yet: try the next four weeks")
        last = int(rw["last"])
        if window == "playoffs" and rw["playoff_start"] is None:
            raise BadRequest("this league has no playoffs on Sleeper: try the rest of the season")
        extra_weeks = [w for w in range(max(weeks) + 1, last + 1)]
        rows = ctx.horizon.to_dict("records")
        if extra_weeks:
            lastw = max(weeks)
            ident = {str(r["sleeper_player_id"]): r for r in rows
                     if r.get("sleeper_player_id") is not None and int(r["week"]) == lastw}
            for r in rows:                     # a player with no row in the last board week: his latest row
                sid = r.get("sleeper_player_id")
                if sid is not None and str(sid) not in ident:
                    ident[str(sid)] = r
            for sid, r in ident.items():
                gs = r.get("gsis_id")
                pk = str(gs) if isinstance(gs, str) and gs else sid
                carry = r.get("reason") if r.get("role") == "unplayable" and r.get("reason") in CARRY_REASONS else None
                by_week = rw["weeks"].get(pk, {})
                for w in extra_weeks:
                    v = by_week.get(w)
                    base = {"roster_id": int(r["roster_id"]), "week": w, "sleeper_player_id": sid, "gsis_id": gs,
                            "player_name": r.get("player_name"), "position": r.get("position"),
                            "fantasy_positions": r.get("fantasy_positions"), "slot": None, "slot_type": None,
                            "is_locked": False, "lineup_margin": None}
                    if carry is not None or v is None:
                        rows.append({**base, "role": "unplayable", "player_value": None, "value_source": None,
                                     "reason": carry or "bye"})
                    else:
                        rows.append({**base, "role": "bench", "player_value": round(float(v), 2),
                                     "value_source": "proj_points", "reason": None})
            board = RosterBoard(rows, tuple(ctx.slots))
        weeks = list(range(ctx.this_week, last + 1))
        if window == "playoffs":
            weeks = [w for w in weeks if w >= int(rw["playoff_start"])]
            if not weeks:
                raise BadRequest("this league's playoffs are over")
    span = f"weeks {weeks[0]}–{weeks[-1]}" if len(weeks) > 1 else f"week {weeks[0]}"
    out = (board, tuple(int(w) for w in weeks), span)
    ctx.window_cache[key] = out
    return out


INTEREST_POINTS = ((-6.0, 0.0), (0.0, 25.0), (2.0, 50.0), (6.0, 75.0), (12.0, 100.0))


def interest(their_gain: float | None, my_gain: float | None, span: str) -> dict:
    """The dial: the other manager's interest 0-100 from his lineup gain over the window, by our numbers. "No deal" when
    his side loses or gains nothing he would see (under 0.05, shown "+0.0"), "Maybe" under 2 points, "Likely" 2-6,
    "Hard to say no" over 6. The needle: piecewise linear through (-6, 0) (0, 25) (2, 50) (6, 75) (12, 100), so each
    label owns a quarter of the dial."""
    g = float(their_gain or 0.0)
    label = "No deal" if g < 0.05 else "Maybe" if g < 2 else "Likely" if g <= 6 else "Hard to say no"
    pts = INTEREST_POINTS
    if g <= pts[0][0]:
        score = pts[0][1]
    elif g >= pts[-1][0]:
        score = pts[-1][1]
    else:
        score = next(y0 + (g - x0) * (y1 - y0) / (x1 - x0) for (x0, y0), (x1, y1) in zip(pts, pts[1:], strict=False)
                     if x0 <= g <= x1)
    return {"score": int(round(score)), "label": label, "their_gain": round(g, 2),
            "you": None if my_gain is None else round(float(my_gain), 2), "caption": f"by our numbers over {span}"}


SLEEPER_LINE_COLS = ("attempts", "completions", "carries", "targets", "passing_yards", "passing_tds", "passing_interceptions",
                     "passing_2pt_conversions", "rushing_yards", "rushing_tds", "rushing_2pt_conversions", "receptions",
                     "receiving_yards", "receiving_tds", "receiving_2pt_conversions", "fumbles_total", "fumbles_lost_total",
                     "fumble_recovery_tds", "special_teams_tds", "pass_tds_40p", "pass_tds_50p", "rush_tds_40p",
                     "rush_tds_50p", "rec_tds_40p", "rec_tds_50p")
# Sleeper's own projection this week (the source of mart_projection_record's Sleeper side: its per-player prices are a
# CTE of that mart, not a column): the latest snapshot of the week, skill players with a stat line, by Sleeper id
SLEEPER_PROJ_SQL = f"""select distinct on (player_id) player_id, position, {', '.join(SLEEPER_LINE_COLS)}
                      from raw.sleeper_projections
                      where season = %s and week = %s and season_type = 'regular' and position in ('QB','RB','WR','TE')
                        and player_id ~ '^[0-9]+$'
                        and coalesce(attempts, carries, targets, passing_yards, rushing_yards, receiving_yards, receptions,
                                     passing_tds, rushing_tds, receiving_tds) is not null
                      order by player_id, fetched_at desc"""
SCORING_SQL = "select scoring_settings from analytics.dim_league_season where league_id = %s order by season desc limit 1"


def market_week(ctx: TradeContext) -> dict[str, float]:
    """Sleeper id -> Sleeper's projection this week in this league's scoring (mart_projection_record's pricing:
    league_points = compute_points on the stat line). Empty when the database holds no snapshot for the week."""
    if "market_week" in ctx.window_cache:
        return ctx.window_cache["market_week"]
    out: dict[str, float] = {}
    try:
        rows = query(SLEEPER_PROJ_SQL, (int(ctx.season), int(ctx.this_week)))
        if not rows.empty:
            if ctx.lw is not None:
                scoring = dict(ctx.lw.scoring)
            else:
                sc = query(SCORING_SQL, (ctx.league_id,))
                raw = sc["scoring_settings"].iloc[0] if not sc.empty else {}
                raw = json.loads(raw) if isinstance(raw, str) else (raw or {})
                scoring = {k: float(v) for k, v in raw.items() if v is not None}
            for r in rows.to_dict("records"):
                line = {k: (0.0 if r.get(k) is None or (isinstance(r.get(k), float) and math.isnan(r[k])) else float(r[k]))
                        for k in SLEEPER_LINE_COLS}
                out[str(r["player_id"])] = round(float(_compute_points({**line, "position": r["position"]}, scoring)), 2)
    except Exception:  # noqa: BLE001 - no snapshot table / no rows: rule (b) is not applied, the response says so
        out = {}
    ctx.window_cache["market_week"] = out
    return out


def sanity_inputs(ctx: TradeContext) -> tuple[dict, dict, dict]:
    """(ros, ours, market) keyed by Sleeper id for `trades.sanity`: rest-of-season points (the ROS board), our
    projection this week (the board's value; a player who cannot play this week is not judged), Sleeper's."""
    rw = ros_weeks(ctx)
    ros, ours = {}, {}
    for sid in ctx.info.index:
        g = ctx.gsis(sid)
        k = str(g) if g else str(sid)
        if k in rw["points"]:
            ros[str(sid)] = rw["points"][k]
        v, why = ctx.week_value(sid)
        if v is not None and why is None and str(sid) not in getattr(ctx, "out_now", {}):
            ours[str(sid)] = float(v)
    return ros, ours, market_week(ctx)
# ---- end IA-2 (block 1)


def evaluate(league_id: str, team: int, partner: int | None, give, get, *, source: str | None = None,
             as_of: datetime | None = None, window: str | None = None) -> dict:
    t0 = time.perf_counter()
    window = check_window(window)                                    # ---- IA-2: the window (default next4)
    ctx = trade_context(league_id, source, as_of=as_of)
    t1 = time.perf_counter()
    if int(team) not in ctx.board.rosters:
        raise NotFound(f"no team {team} in this league")
    give, get = ctx.resolve(give), ctx.resolve(get)
    if partner is None and get:
        partner = ctx.board.owner(get[0])
    if partner is None or int(partner) not in ctx.board.rosters or int(partner) == int(team):
        raise BadRequest("pick a trade partner: another team of this league")
    g, t, bad = T.clean_package(ctx.board, int(team), int(partner), give, get)
    if bad:
        raise BadRequest(f"not on these rosters: {', '.join(bad)} (give: your players; get: theirs)")
    if not g or not t:
        raise BadRequest("a trade needs at least one player on each side")
    board, weeks, span = window_board(ctx, window)
    try:
        trade = T.evaluate(board, g, t, weeks, market=ctx.market, prices=ctx.prices)
        fa_meta: dict = {}
        if trade.mine.opened or trade.theirs.opened:
            pool, fa_meta = ctx.fa_pool(weeks)
            trade = T.evaluate(board, g, t, weeks, market=ctx.market, prices=ctx.prices, free_agents=pool)
        # this week's lineups and gains: the window's first week, or (the playoffs) this week evaluated on its own
        now = trade if weeks[0] == ctx.this_week else T.evaluate(board, g, t, (ctx.this_week,), market=ctx.market,
                                                                  prices=ctx.prices)
    except ValueError as exc:
        raise BadRequest(str(exc)) from exc
    t2 = time.perf_counter()
    me, th = trade.mine, trade.theirs
    view = trade if now is trade else _View(now, trade)              # fit / verdict: this week + the window
    # the page's own sentence functions (size_words, closest, lineup_frame) with its globals bound to this league
    ns = page_functions("6_Trade_Finder.py", TRADE_FUNCS, name=ctx.name, gsis=ctx.gsis, pos=ctx.pos, link=ctx.link,
                        player_link=ui.player_link, span_words=span, slot_label=cards.slot_label)
    lineups = {}
    for who, side in (("mine", now.mine), ("theirs", now.theirs)):
        frame, notes = ns["lineup_frame"](side)
        lineups[who] = {"slots": [{"slot": r["slot"], "player_name": _str(r["player_name"]), "gsis_id": _str(r["gsis_id"]),
                                   "value": _num(r["trade_value"]),
                                   "change": None if _num(r["trade_change"]) is None else round(float(r["trade_change"]), 2)}
                                  for _, r in frame.iterrows()],
                        "notes": [links(x) for x in notes], "closest_call": links(ns["closest"](side))}
    size = ns["size_words"](me, fa_meta, "you", "") + ns["size_words"](th, fa_meta, "they", "")
    size_words = ("Roster size: " + "; ".join(size) + ".") if size else f"Roster size: no change ({len(g)} for {len(t)})."
    # league rank before / after (the page: mart_league_roster_rankings with the two rosters' values replaced); the
    # horizon rank compares the next four weeks only (the league's other rosters are valued over those)
    rank = _rank_change(ctx, int(team), int(partner), now.mine, now.theirs, ns["rank_words"],
                        horizon=(me, th) if window == "next4" else None)
    moving = [{**ctx.player(x), "goes_to": ctx.team(partner) if x in g else "You"} for x in [*g, *t]]
    repl = {p: {"season_points": T.whole(v), "player_name": ctx.repl_name.get(p)} for p, v in sorted(ctx.replacement.items())}
    sides = {"mine": _side(ctx, me), "theirs": _side(ctx, th)}
    state = {k: {w: {"this_week": T._r2(sn.before[0] if w == "before" else sn.after[0]),
                     "horizon": s.before_horizon if w == "before" else s.after_horizon,
                     "bench": sn.bench_before if w == "before" else sn.bench_after,
                     "by_week": [T._r2(x) for x in (s.before if w == "before" else s.after)]}
                 for w in ("before", "after")}
             for k, s, sn in (("mine", me, now.mine), ("theirs", th, now.theirs))}
    ros, ours, mkt = sanity_inputs(ctx)
    out = {"league_id": ctx.league_id, "source": "database" if ctx.is_house else "sleeper", "roster_id": int(team),
           "partner": int(partner), "partner_team": ctx.team(partner), "week": ctx.this_week, "weeks": list(trade.weeks),
           "span": span, "window": window, "window_label": WINDOW_LABELS[window], "window_why": WINDOW_WHY[window],
           "give": [ctx.player(x) for x in g], "get": [ctx.player(x) for x in t],
           "before": {"mine": state["mine"]["before"], "theirs": state["theirs"]["before"]},
           "after": {"mine": state["mine"]["after"], "theirs": state["theirs"]["after"]},
           "fit": {"this_week": {"mine": now.mine.gain_week, "theirs": now.theirs.gain_week},
                   "window": {"mine": me.gain_horizon, "theirs": th.gain_horizon},
                   "next_4": {"mine": me.gain_horizon, "theirs": th.gain_horizon},     # the window's (its name before IA-2)
                   "words": links(T.fit_line(view, span))},
           "interest": interest(th.gain_horizon, me.gain_horizon, span),
           "sanity": T.sanity(g, t, ros=ros, ours=ours, market=mkt, name=ctx.name),
           "market": {"give": me.price_out, "get": me.price_in, "season_points_give": me.points_out,
                      "season_points_get": me.points_in, "unknown": [*me.unknown_out, *me.unknown_in],
                      "replacement": repl, "words": links(T.fairness_line(trade)), "players": moving},
           "verdict": links(T.verdict(view, span)),
           "headline": links(f"**You give {_names(ctx, g)}; you get {_names(ctx, t)}.** {T.verdict(view, span)}"),
           "ros": _ros_package(ctx, g, t), "ranks": rank, "size_words": links(size_words),
           "sides": sides, "lineups": lineups,
           "fill_players": {k: {**v, "sleeper_id": k} for k, v in fa_meta.items()
                            if k in {s.fill.player_id for s in (me, th) if s.fill is not None}},
           "words_source": "trades.verdict / fit_line / fairness_line; app/pages/6_Trade_Finder.py (size_words, closest, "
                           "lineup_frame); app/lib/ros.py (package_sentence)"}
    t3 = time.perf_counter()
    out["timings_ms"] = {"context": round((t1 - t0) * 1000, 1), "evaluate": round((t2 - t1) * 1000, 1),
                         "words": round((t3 - t2) * 1000, 1), "total": round((t3 - t0) * 1000, 1)}
    if ctx.lw is not None:
        out["timings_ms"].update({f"league.{k}": v for k, v in ctx.lw.timings_ms.items()})
    return out


class _View:
    """A trade read by `trades.fit_line` / `verdict` with this week's gains from one evaluation and the window's from
    another (the playoffs window starts after this week): each side answers gain_week, gain_horizon and the prices."""

    class _S:
        def __init__(self, now: T.Side, win: T.Side):
            self.gain_week, self.gain_horizon = now.gain_week, win.gain_horizon
            self.price_out, self.price_in = win.price_out, win.price_in
            self.unknown_out, self.unknown_in = win.unknown_out, win.unknown_in

    def __init__(self, now: T.Trade, win: T.Trade):
        self.mine, self.theirs = self._S(now.mine, win.mine), self._S(now.theirs, win.theirs)


def _names(ctx: TradeContext, ids) -> str:
    parts = [ctx.link(p) for p in ids]
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


def _rank_change(ctx: TradeContext, me: int, them: int, ms: T.Side, ts: T.Side, rank_words, *,
                 horizon: tuple[T.Side, T.Side] | None = None) -> dict:
    """League rank before / after for this week, the horizon and depth (the page's rank lines). IA-2: ``ms`` / ``ts``
    are this week's sides; ``horizon`` the next-four-weeks sides (None: another window, no horizon rank)."""
    if ctx.is_house:
        rk = query(RANKS_SQL, (ctx.league_id,))
        vals_by = {m: {int(r.roster_id): float(r.value) for r in rk[rk["measure"] == m].itertuples()}
                   for m in ("lineup_value", "horizon_value", "bench_value")}
    else:
        vals_by = _od_values(ctx.lw)
    out, bits = {}, []
    measures = [("lineup_value", ms.after[0], ts.after[0], f"week {ctx.this_week}")]
    if horizon is not None:
        measures.append(("horizon_value", horizon[0].after_horizon, horizon[1].after_horizon, ctx.span_words))
    measures.append(("bench_value", ms.bench_after, ts.bench_after, "depth"))
    for measure, a_me, a_th, when in measures:
        vals = vals_by.get(measure, {})
        if me in vals and them in vals and a_me is not None and a_th is not None:
            ch = T.rank_change(vals, {me: a_me, them: a_th})
            out[measure] = {"mine": list(ch[me]), "theirs": list(ch[them]), "n": len(vals)}
            bits.append(f"{when}: you {rank_words(ch[me][0])} → **{rank_words(ch[me][1])}** of {len(vals)}, "
                        f"{ctx.team(them)} {rank_words(ch[them][0])} → {rank_words(ch[them][1])}")
    out["words"] = ("League rank, " + "; ".join(bits) + ".") if bits else None
    return out


def _od_values(lw: A.LeagueWeeks) -> dict[str, dict[int, float]]:
    """Every roster's lineup value this week, the horizon sum and the bench (mart_league_roster_value's columns)."""
    lv, hv, bv = {}, {}, {}
    for rid in lw.roster_ids:
        t0 = lw.total(rid, lw.weeks[0])
        if t0.get("lineup_value") is None:
            continue
        lv[rid] = float(t0["lineup_value"])
        bv[rid] = float(t0["bench_value"]) if t0.get("bench_value") is not None else None
        hv[rid] = round(sum(float(lw.total(rid, w).get("lineup_value") or 0.0) for w in lw.weeks), 2)
    return {"lineup_value": lv, "horizon_value": hv, "bench_value": {k: v for k, v in bv.items() if v is not None}}


def partners(league_id: str, team: int, want: str | None = None, *, source: str | None = None,
             as_of: datetime | None = None, window: str | None = None) -> dict:
    """The partner finder (the page's partner_sweep: `trades.partners`, the best 1-for-1 and 2-for-1 per team that raise
    both lineups over the window), best partner first; `want` keeps the packages that bring you that position.
    IA-2: `window` (week | next4 | ros | playoffs, default next4) and the sanity bound (`trades.sanity`: a package that
    gives away much more rest-of-season value than it brings back, or that works only because our number for a player
    you give is far under Sleeper's, is set aside - `rejected` names three, `rejected_count` counts them)."""
    t0 = time.perf_counter()
    window = check_window(window)
    want = (want or "").upper() or None
    if want is not None and want not in POSITIONS:
        raise NotFound(f"no position {want} (QB, RB, WR, TE, K or DEF)")
    is_house = house(league_id, source)

    def search():
        ctx = trade_context(league_id, source, as_of=as_of)
        if int(team) not in ctx.board.rosters:
            raise NotFound(f"no team {team} in this league")
        board, weeks, span = window_board(ctx, window)
        ros, ours, mkt = sanity_inputs(ctx)
        stats: dict = {}
        rejected: list = []
        found = T.partners(board, int(team), weeks=weeks, stats=stats, want=want, rejected=rejected,
                           allow=lambda pk: T.sanity(pk.give, pk.get, ros=ros, ours=ours, market=mkt, name=ctx.name))
        return ctx, found, stats, (board, weeks, span), rejected, (ros, mkt)
    ctx, found, stats, (board, weeks, span), rejected, (ros, mkt) = (
        search() if as_of is not None else _memo(("partners", str(league_id), int(team), want, is_house, window), is_house, search))
    starts_now = weeks[0] == ctx.this_week
    rows = []
    for p in found:
        for shape, pk in (("1-for-1", p.one_for_one), ("2-for-1", p.two_for_one)):
            if pk is None:
                continue
            rows.append({"partner": p.roster_id, "partner_team": ctx.team(p.roster_id), "shape": pk.shape, "kind": shape,
                         "is_best": pk == p.best, "give": [ctx.player(x) for x in pk.give],
                         "get": [ctx.player(x) for x in pk.get],
                         "you_gain_week": pk.my_week if starts_now else None, "you_gain_horizon": pk.my_horizon,
                         "they_gain_week": pk.their_week if starts_now else None, "they_gain_horizon": pk.their_horizon,
                         "interest": interest(pk.their_horizon, pk.my_horizon, span),
                         "price_out": T.season_value(ctx.prices, pk.give)[0], "price_in": T.season_value(ctx.prices, pk.get)[0]})
    ranked = [p for p in found if p.best is not None]
    head = None
    if ranked:
        pk = ranked[0].best
        m = ctx.names.get(ranked[0].roster_id, {}).get("manager_name")
        who = f"{ctx.team(ranked[0].roster_id)} ({m})" if m else ctx.team(ranked[0].roster_id)
        # quoted from app/pages/6_Trade_Finder.py (the first card); a window that starts later has no "this week"
        if starts_now and len(weeks) > 1:
            head = (f"**Best partner: {who}.** Your {_names(ctx, pk.give)} for their {_names(ctx, pk.get)}: you "
                    f"**{pk.my_week:+.1f}** this week and **{pk.my_horizon:+.1f}** over {span}, them "
                    f"**{pk.their_week:+.1f}** and **{pk.their_horizon:+.1f}**.")
        else:
            head = (f"**Best partner: {who}.** Your {_names(ctx, pk.give)} for their {_names(ctx, pk.get)}: you "
                    f"**{pk.my_horizon:+.1f}** over {span}, them **{pk.their_horizon:+.1f}**.")
    else:
        head = (f"**No trade raises both lineups.** Nobody in the league has a player who would improve your lineup over "
                f"{span} and also needs one of yours. Try a trade you have in mind below.")
    examples = []
    for pk, why in rejected[:3]:
        examples.append({"partner_team": ctx.team(pk.partner), "give": [ctx.name(x) for x in pk.give],
                         "get": [ctx.name(x) for x in pk.get], "why": why})
    return {"league_id": ctx.league_id, "source": "database" if ctx.is_house else "sleeper", "roster_id": int(team),
            "want": want, "week": ctx.this_week, "span": span, "weeks": list(weeks), "window": window,
            "window_label": WINDOW_LABELS[window], "window_why": WINDOW_WHY[window], "partners": rows,
            "no_trade_with": [ctx.team(p.roster_id) for p in found if p.best is None],
            "rejected": examples, "rejected_count": len(rejected),
            "sanity": {"ros_gap_share": T.ROS_GAP_SHARE, "market_share": T.MARKET_SHARE, "ros_players": len(ros),
                       "market_players": len(mkt),
                       "market_note": None if mkt else (f"Sleeper's week-{ctx.this_week} projections are not in the database: "
                                                        "the market check is not applied")},
            "words": {"headline": links(head), "source": "quoted from app/pages/6_Trade_Finder.py (the best-partner card)"},
            "search": {k: (round(v, 3) if isinstance(v, float) else v) for k, v in stats.items()},
            "timings_ms": {"total": round((time.perf_counter() - t0) * 1000, 1)}}


# ================================================================================== the Team Hub
VALUE_SQL = "select * from analytics.mart_league_roster_value where league_id = %s"
RANKINGS_SQL = """select roster_id, team_name, measure, measure_label, horizon, value, league_rank, n_rosters, rank_label
                  from analytics.mart_league_roster_rankings where league_id = %s"""
SLOT_SQL = """select roster_id, slot_type, slots, empty_slots, first_slot_order, top_slot, top_gsis_id, top_player_name,
                     top_position, top_value, top_is_locked, starter_strength, replacement_name, replacement_value
              from analytics.mart_league_roster_slot_strength where league_id = %s"""
TEAM_ROWS_SQL = """select week, role, slot, slot_type, slot_order, bench_rank, sleeper_player_id, gsis_id, player_name, position,
                          player_value, value_source, lineup_margin, is_locked, report_status, reason, acquired_label,
                          acquired_how_by_manager
                   from analytics.mart_league_roster_horizon where league_id = %s and roster_id = %s and is_this_week"""
WEEKLY_SQL = """select distinct on (week) week, lineup_value, bench_value from ops.lineup_totals
                where league_id = %s and season = %s and roster_id = %s and week between %s and %s and not is_realised
                order by week, run_at desc"""
WEEKLY_LEAGUE_SQL = """select distinct on (week, roster_id) week, roster_id, lineup_value from ops.lineup_totals
                       where league_id = %s and season = %s and week between %s and %s and not is_realised
                       order by week, roster_id, run_at desc"""


def _week_league(allw: pd.DataFrame, week: int, mine) -> dict | None:
    """The league behind a week's lineup value: median, best, the roster's rank (1 = best) and the count."""
    if allw is None or allw.empty or mine is None:
        return None
    g = pd.to_numeric(allw.loc[allw["week"] == int(week), "lineup_value"], errors="coerce").dropna()
    if g.empty:
        return None
    return {"median": round(float(g.median()), 2), "best": round(float(g.max()), 2), "n": int(g.size),
            "rank": int((g > float(mine)).sum()) + 1}


PROFILE_SQL = "select * from analytics.mart_league_manager_profile where league_id = %s"
KEEPER_SQL = """select k.sleeper_player_id, k.gsis_id, k.player_name, k.position, a.acquired_label as acquired, k.games_played,
                       k.ppg_std, k.position_rank_ppg, k.expected_per_game, k.diff_per_game
                from analytics.mart_league_keeper_candidates k
                left join analytics.mart_league_acquisitions a
                       on a.league_id = k.league_id and a.roster_id = k.roster_id and a.sleeper_player_id = k.sleeper_player_id
                where k.league_id = %s and k.roster_id = %s order by k.ppg_std desc nulls last"""


def _ordinal(n) -> str:
    n = int(n)
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _rank(values: dict[int, float]) -> dict[int, int]:
    """rank() over value desc (ties share a rank: the mart's)."""
    return T.ranks(values)


def od_team_marts(lw: A.LeagueWeeks) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """(mart_league_roster_value, _rankings, _slot_strength, _horizon) for every roster of a league solved on demand:
    the marts' rules on `anyleague.horizon_frame` and the solved totals."""
    hf = A.horizon_frame(lw)
    w0, w1 = lw.weeks[0], lw.weeks[-1]
    week_label = f"week {w0}"
    horizon_label = f"week {w0}" if w0 == w1 else f"weeks {w0}–{w1}"
    vals = []
    for rid in lw.roster_ids:
        t0 = lw.total(rid, w0)
        if not t0:
            continue
        lvs = [(w, float(lw.total(rid, w).get("lineup_value") or 0.0)) for w in lw.weeks if lw.total(rid, w)]
        worst = min(lvs, key=lambda x: (x[1], x[0])) if lvs else (None, None)
        wk = hf[(hf["roster_id"] == rid) & hf["is_this_week"] & (hf["role"] == "starter") & (hf["slot"] == t0.get("weakest_slot"))]
        w = wk.iloc[0] if not wk.empty else None
        n = lw.names.get(rid, {})
        vals.append({"roster_id": rid, "team_name": n.get("team_name"), "manager_name": n.get("manager_name"), "week": w0,
                     "horizon_first_week": w0, "horizon_last_week": w1, "horizon_weeks": len(lw.weeks),
                     "week_label": week_label, "horizon_label": horizon_label, "lineup_value": t0.get("lineup_value"),
                     "bench_value": t0.get("bench_value"), "slots_total": t0.get("slots_total"), "slots_filled": t0.get("slots_filled"),
                     "empty_slots": t0.get("empty_slots"), "n_unvalued": t0.get("n_unvalued"), "n_locked": t0.get("n_locked"),
                     "n_questionable": t0.get("n_questionable"), "weakest_slot": t0.get("weakest_slot"),
                     "weakest_margin": t0.get("weakest_margin"),
                     "weakest_player_name": None if w is None else w["player_name"],
                     "weakest_gsis_id": None if w is None else w["gsis_id"],
                     "weakest_position": None if w is None else w["position"],
                     "weakest_value": None if w is None else w["player_value"],
                     "weakest_replacement_name": None if w is None else w["replacement_name"],
                     "weakest_replacement_value": None if w is None else w["replacement_value"],
                     "horizon_value": round(sum(v for _, v in lvs), 2), "horizon_lineups": len(lvs),
                     "worst_week": worst[0], "worst_week_value": worst[1]})
    value = pd.DataFrame(vals)
    rk = []
    for measure, label, hz in (("lineup_value", "Lineup value", week_label), ("horizon_value", "Lineup value, next 4 weeks", horizon_label),
                               ("bench_value", "Depth (bench lineup)", week_label)):
        vv = {int(r["roster_id"]): float(r[measure]) for r in vals if r[measure] is not None}
        ranks = _rank(vv)
        for r in vals:
            if r[measure] is None:
                continue
            k = ranks[int(r["roster_id"])]
            rk.append({"roster_id": r["roster_id"], "team_name": r["team_name"], "measure": measure, "measure_label": label,
                       "horizon": hz, "value": float(r[measure]), "league_rank": k, "n_rosters": len(vv),
                       "rank_label": f"{k}/{len(vv)}"})
    rankings = pd.DataFrame(rk)
    tw = hf[hf["is_this_week"]]
    ss = []
    for (rid, stype), g in tw[tw["role"].isin(["starter", "empty"])].groupby(["roster_id", "slot_type"]):
        top = tw[(tw["roster_id"] == rid) & (tw["slot_type"] == stype) & tw["is_top_at_slot_type"]]
        t = top.iloc[0] if not top.empty else None
        ss.append({"roster_id": int(rid), "slot_type": stype, "slots": len(g), "empty_slots": int((g["role"] == "empty").sum()),
                   "first_slot_order": int(g["slot_order"].min()), "top_slot": None if t is None else t["slot"],
                   "top_gsis_id": None if t is None else t["gsis_id"], "top_player_name": None if t is None else t["player_name"],
                   "top_position": None if t is None else t["position"], "top_value": None if t is None else t["player_value"],
                   "top_is_locked": None if t is None else bool(t["is_locked"]),
                   "starter_strength": None if t is None else t["lineup_margin"],
                   "replacement_name": None if t is None else t["replacement_name"],
                   "replacement_value": None if t is None else t["replacement_value"]})
    slots = pd.DataFrame(ss).sort_values(["roster_id", "first_slot_order"]) if ss else pd.DataFrame()
    return value, rankings, slots, hf


def team(league_id: str, team_id: int, *, source: str | None = None, as_of: datetime | None = None) -> dict:
    t0 = time.perf_counter()
    is_house = house(league_id, source)
    if is_house:
        members = _members(league_id)
        _team_check(members, team_id)
        season = int(cards.league_season(league_id))
        value, rankings, slots = query(VALUE_SQL, (league_id,)), query(RANKINGS_SQL, (league_id,)), query(SLOT_SQL, (league_id,))
        rows = query(TEAM_ROWS_SQL, (league_id, int(team_id)))
        prof = query(PROFILE_SQL, (league_id,))
        keeper = query(KEEPER_SQL, (league_id, int(team_id)))
        names = members
        lw = None
    else:
        league, rosters, users = _sleeper_league(league_id)
        names = A.team_names(rosters, users)
        _team_check(names, team_id)
        season, week = _season_week(league_id, league)
        if week is None:
            return {"league_id": str(league_id), "source": "sleeper", "roster_id": int(team_id), "week": None,
                    "notice": "The regular season is over: no lineups ahead."}
        lw = _od(A.league_weeks, query, league["league_id"], week, as_of=as_of)
        if "team_marts" not in lw.cache:
            lw.cache["team_marts"] = od_team_marts(lw)
        value, rankings, slots, hf = lw.cache["team_marts"]
        rows = hf[(hf["roster_id"] == int(team_id)) & hf["is_this_week"]].copy()
        rows["acquired_label"] = None
        rows["acquired_how_by_manager"] = None
        prof, keeper = pd.DataFrame(), pd.DataFrame()
    t1 = time.perf_counter()
    mine = value[value["roster_id"] == int(team_id)] if not value.empty else value
    out: dict = {"league_id": str(league_id), "source": "database" if is_house else "sleeper", "roster_id": int(team_id),
                 "team_name": names.get(int(team_id), {}).get("team_name"),
                 "manager_name": names.get(int(team_id), {}).get("manager_name"), "week": None, "value": None,
                 "ranks": {}, "league": [], "slot_strength": [], "roster": [], "weekly": [], "season": None, "keeper": None,
                 "words": None}
    if mine.empty:
        out["notice"] = "No lineup for the weeks ahead yet (the season is over, or the nightly has not run since the last build)."
        return out
    v = mine.iloc[0]
    out["week"] = int(v["week"])
    out["value"] = {c: (v[c].item() if hasattr(v[c], "item") else v[c]) for c in value.columns}
    rk_mine = rankings[rankings["roster_id"] == int(team_id)].set_index("measure") if not rankings.empty else pd.DataFrame()
    out["ranks"] = {m: {"value": _num(r["value"]), "league_rank": _int(r["league_rank"]), "n_rosters": _int(r["n_rosters"]),
                        "horizon": r["horizon"], "rank_label": r["rank_label"]} for m, r in rk_mine.iterrows()}
    wide = rankings.pivot_table(index=["roster_id"], columns="measure", values="value") if not rankings.empty else pd.DataFrame()
    rkw = rankings.pivot_table(index=["roster_id"], columns="measure", values="league_rank") if not rankings.empty else pd.DataFrame()
    out["league"] = sorted([{"roster_id": int(rid), "team_name": names.get(int(rid), {}).get("team_name"), "is_me": int(rid) == int(team_id),
                             **{m: _num(wide.at[rid, m]) for m in wide.columns},
                             **{f"{m}_rank": _int(rkw.at[rid, m]) for m in rkw.columns}} for rid in wide.index],
                           key=lambda r: (r.get("lineup_value_rank") or 99, r["roster_id"]))
    ss = slots[slots["roster_id"] == int(team_id)] if not slots.empty else slots
    b = bio(list(rows["gsis_id"]) + (list(ss["top_gsis_id"]) if not ss.empty else []))
    # the league behind each slot (G4's screen: "· 3rd", "League average x, best y"): every roster's starter strength
    def _slot_league(slot_type: str, mine_value) -> dict | None:
        if slots.empty or "starter_strength" not in slots:
            return None
        g = pd.to_numeric(slots.loc[slots["slot_type"] == slot_type, "starter_strength"], errors="coerce").dropna()
        if g.empty or mine_value is None:
            return None
        return {"avg": round(float(g.mean()), 2), "best": round(float(g.max()), 2), "n": int(g.size),
                "rank": int((g > float(mine_value)).sum()) + 1}
    out["slot_strength"] = [{"slot_type": r["slot_type"], "slots": _int(r["slots"]), "empty_slots": _int(r["empty_slots"]),
                             "top": None if not isinstance(r["top_player_name"], str) else
                             {**_player(None, r["top_gsis_id"], r["top_player_name"], r["top_position"], None, b),
                              "slot": r["top_slot"], "value": _num(r["top_value"]), "is_locked": _bool(r["top_is_locked"])},
                             "starter_strength": _num(r["starter_strength"]), "replacement_name": _str(r["replacement_name"]),
                             "replacement_value": _num(r["replacement_value"]),
                             "league": _slot_league(r["slot_type"], _num(r["starter_strength"]))} for _, r in ss.iterrows()]
    order = {"starter": 0, "empty": 0, "bench": 1, "unplayable": 2}
    rows = rows.assign(_o=rows["role"].map(order)).sort_values(["_o", "slot_order", "bench_rank", "player_value"],
                                                               ascending=[True, True, True, False], na_position="last")
    out["roster"] = [{**_player(r["sleeper_player_id"], r["gsis_id"], r["player_name"], r["position"], None, b),
                      "role": r["role"], "slot": _str(r["slot"]), "slot_type": _str(r["slot_type"]), "bench_rank": _int(r["bench_rank"]),
                      "value": _num(r["player_value"]), "value_source": _str(r["value_source"]), "margin": _num(r["lineup_margin"]),
                      "is_locked": _bool(r["is_locked"]), "report_status": _str(r["report_status"]), "reason": _str(r["reason"]),
                      "acquired": _str(r["acquired_label"]), "acquired_how": _str(r["acquired_how_by_manager"])}
                     for _, r in rows.iterrows()]
    if is_house:
        wk = query(WEEKLY_SQL, (league_id, season, int(team_id), int(v["horizon_first_week"]), int(v["horizon_last_week"])))
        allw = query(WEEKLY_LEAGUE_SQL, (league_id, season, int(v["horizon_first_week"]), int(v["horizon_last_week"])))
        out["weekly"] = [{"week": int(r.week), "lineup_value": _num(r.lineup_value), "bench_value": _num(r.bench_value),
                          "league": _week_league(allw, int(r.week), _num(r.lineup_value))}
                         for r in wk.itertuples()]
        p = prof[prof["roster_id"] == int(team_id)] if not prof.empty else prof
        if not p.empty:
            out["season"] = {c: (p.iloc[0][c].item() if hasattr(p.iloc[0][c], "item") else p.iloc[0][c]) for c in p.columns}
        out["keeper"] = {"rows": [{**_player(r["sleeper_player_id"], r["gsis_id"], r["player_name"], r["position"], None, bio(keeper["gsis_id"])),
                                   "acquired": _str(r["acquired"]), "games_played": _int(r["games_played"]),
                                   "ppg_std": _num(r["ppg_std"]), "position_rank_ppg": _int(r["position_rank_ppg"]),
                                   "expected_per_game": _num(r["expected_per_game"]), "diff_per_game": _num(r["diff_per_game"])}
                                  for _, r in keeper.iterrows()]} if not keeper.empty else None
    else:
        allw = pd.DataFrame([{"week": w, "roster_id": rid, "lineup_value": _num(lw.total(rid, w).get("lineup_value"))}
                             for w in lw.weeks for rid in lw.roster_ids])
        out["weekly"] = [{"week": w, "lineup_value": _num(lw.total(team_id, w).get("lineup_value")),
                          "bench_value": _num(lw.total(team_id, w).get("bench_value")),
                          "league": _week_league(allw, w, _num(lw.total(team_id, w).get("lineup_value")))} for w in lw.weeks]
        rec = A.records(lw.rosters).get(int(team_id))
        out["season"] = rec
        out["keeper"] = None
        out["keeper_why"] = "how each player joined the roster needs the league's history in the database (house leagues)"
        out["on_demand"] = {"cost": f"every roster solved for {len(lw.weeks)} weeks: {len(lw.roster_ids)} x {len(lw.weeks)} "
                                    f"= {len(lw.roster_ids) * len(lw.weeks)} lineups (the ranks need the whole league)",
                            "timings_ms": lw.timings_ms}
    out["words"] = team_words(out, rows)
    out["timings_ms"] = {"data": round((t1 - t0) * 1000, 1), "total": round((time.perf_counter() - t0) * 1000, 1)}
    return out


def team_words(out: dict, rows: pd.DataFrame) -> dict:
    """The Team Hub's card sentences (quoted from app/pages/1_Team_Hub.py: top-level page code, not importable)."""
    v = out["value"]
    ranks = out["ranks"]

    def rank_text(measure: str) -> str:
        if measure not in ranks:
            return ""
        r = ranks[measure]
        return f"{_ordinal(r['league_rank'])} of {int(r['n_rosters'])} in the league ({r['horizon']})"
    week = int(v["week"])
    lines = [f"**Week {week}: your best lineup projects {v['lineup_value']:.1f}** — {rank_text('lineup_value')}."]
    if isinstance(v.get("weakest_slot"), str):
        who = f"{v['weakest_player_name']} ({v['weakest_position']})" if isinstance(v.get("weakest_position"), str) else str(v["weakest_player_name"])
        if isinstance(v.get("weakest_replacement_name"), str):
            lines.append(f"Your closest call: **{v['weakest_slot']}, {v['weakest_player_name']} over "
                         f"{v['weakest_replacement_name']} by {v['weakest_margin']:.2f}**.")
        else:
            lines.append(f"Your closest call: **{v['weakest_slot']}, {who}** — nobody on the bench can fill in for him "
                         f"(he is worth {v['weakest_margin']:.1f} to the lineup).")
    elif int(v.get("n_locked") or 0):
        lines.append("Every starter's game has kicked off: no lineup calls left this week.")
    horizon = [f"**{str(v['horizon_label']).capitalize()}: {v['horizon_value']:.1f} projected** — {rank_text('horizon_value')}."]
    if v.get("worst_week") is not None and not (isinstance(v.get("worst_week"), float) and math.isnan(v["worst_week"])) \
            and int(v["horizon_weeks"]) > 1:
        horizon.append(f"Toughest week: week {int(v['worst_week'])} ({v['worst_week_value']:.1f}).")
    horizon.append(f"**Depth: your bench alone would field {v['bench_value']:.1f}** in week {week} — {rank_text('bench_value')}.")
    return {"lineup": lines, "horizon": horizon, "source": "quoted from app/pages/1_Team_Hub.py (the first two cards)"}


# ================================================================================== the league
STANDINGS_SQL = "select * from analytics.mart_league_standings where league_id = %s order by standing, roster_id"
ALL_PLAY_SQL = "select * from analytics.mart_league_all_play where league_id = %s order by all_play_rank, roster_id"
ALL_PLAY_WEEK_SQL = "select * from analytics.mart_league_all_play_week where league_id = %s order by week, roster_id"
TX_SQL = """select t.*, m.gsis_id from analytics.mart_league_transactions t
            left join analytics.player_id_map m on m.sleeper_id = t.sleeper_player_id
            where t.league_id = %s order by t.created_at desc, t.transaction_id, t.action, t.sleeper_player_id"""
DRAFT_SQL = """select pick_no, round, draft_slot, roster_id, team_name, sleeper_player_id, gsis_id, player_name, position,
                      drafted_team, is_keeper, nfl_reg_games_played, nfl_reg_points_current_scoring, position_rank_by_pick,
                      position_rank_by_points, points_started_for_any_roster
               from analytics.mart_league_draft where league_id = %s order by pick_no"""


def _records(df: pd.DataFrame) -> list[dict]:
    return [] if df is None or df.empty else [{k: (v.item() if hasattr(v, "item") else v) for k, v in r.items()}
                                              for r in df.to_dict("records")]


def od_league_marts(league: dict, rosters: list[dict], users: list[dict], weeks: dict[int, list[dict]]) -> tuple[pd.DataFrame, ...]:
    """(mart_league_standings, mart_league_all_play, mart_league_all_play_week) from Sleeper's played weeks: the marts'
    SQL in Python (fct_league_matchup's rules: a played week is one Sleeper has scored, a regular-season week is before
    the playoffs, a bye has no matchup_id; standings rank wins then points for, ties share; all-play counts every
    other roster's score that week; luck = wins - games x all-play win rate)."""
    st = league.get("settings") or {}
    pws = int(st.get("playoff_week_start") or 99) or 99
    names = A.team_names(rosters, users)
    fm = []
    for w, ms in weeks.items():
        if int(w) >= pws:
            continue
        by_mid: dict = {}
        for m in ms:
            by_mid.setdefault(m.get("matchup_id"), []).append(m)
        for m in ms:
            if m.get("matchup_id") is None:
                continue                                   # a bye
            opp = next((o for o in by_mid.get(m["matchup_id"], []) if o["roster_id"] != m["roster_id"]), None)
            pts = round(float(m.get("points") or 0.0), 2)
            op = None if opp is None else round(float(opp.get("points") or 0.0), 2)
            res = None if op is None else ("W" if pts > op else "L" if pts < op else "T")
            fm.append({"week": int(w), "roster_id": int(m["roster_id"]), "points": pts, "opponent_points": op, "result": res})
    f = pd.DataFrame(fm, columns=["week", "roster_id", "points", "opponent_points", "result"])
    if f.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    srows = []
    sleeper = {}
    for r in rosters:
        s = r.get("settings") or {}
        sleeper[int(r["roster_id"])] = {"sleeper_wins": s.get("wins"), "sleeper_losses": s.get("losses"),
                                        "sleeper_points_for": round(float(s.get("fpts") or 0) + float(s.get("fpts_decimal") or 0) / 100, 2),
                                        "sleeper_potential_points": round(float(s.get("ppts") or 0) + float(s.get("ppts_decimal") or 0) / 100, 2)}
    for rid, g in f.groupby("roster_id"):
        pf = round(float(g["points"].sum()), 2)
        sp = sleeper.get(int(rid), {})
        ppts = sp.get("sleeper_potential_points") or 0
        srows.append({"roster_id": int(rid), "manager_name": names.get(int(rid), {}).get("manager_name"),
                      "team_name": names.get(int(rid), {}).get("team_name"), "wins": int((g["result"] == "W").sum()),
                      "losses": int((g["result"] == "L").sum()), "ties": int((g["result"] == "T").sum()), "games": len(g),
                      "win_pct": round(int((g["result"] == "W").sum()) / len(g), 3) if len(g) else None,
                      "points_for": pf, "points_against": round(float(g["opponent_points"].sum()), 2),
                      "avg_points": round(float(g["points"].mean()), 2),
                      "stddev_points": round(float(g["points"].std(ddof=1)), 2) if len(g) > 1 else None,
                      "best_week": float(g["points"].max()), "worst_week": float(g["points"].min()), **sp,
                      "lineup_efficiency": round(pf / ppts, 4) if ppts and ppts > 0 else None, "is_champion": False})
    standings = pd.DataFrame(srows)
    standings["standing"] = standings[["wins", "points_for"]].apply(tuple, axis=1).rank(method="min", ascending=False).astype(int)
    standings = standings.sort_values(["standing", "roster_id"]).reset_index(drop=True)
    wk = []
    for w, g in f.groupby("week"):
        pts = g.set_index("roster_id")["points"]
        for rid, p in pts.items():
            others = pts.drop(rid)
            r = g[g["roster_id"] == rid].iloc[0]
            wk.append({"week": int(w), "roster_id": int(rid), "team_name": names.get(int(rid), {}).get("team_name"),
                       "points": float(p), "opponent_points": r["opponent_points"], "result": r["result"],
                       "all_play_wins": int((p > others).sum()), "all_play_losses": int((p < others).sum()),
                       "all_play_ties": int((p == others).sum()),
                       "week_points_rank": int(1 + (pts > p).sum()), "rosters_in_week": len(pts),
                       "week_median_others": float(others.median()) if len(others) else None})
    apw = pd.DataFrame(wk)
    ap = []
    for rid, g in apw.groupby("roster_id"):
        tot = int(g["all_play_wins"].sum() + g["all_play_losses"].sum() + g["all_play_ties"].sum())
        wins = int((g["result"] == "W").sum())
        pct = g["all_play_wins"].sum() / tot if tot else None
        ap.append({"roster_id": int(rid), "team_name": names.get(int(rid), {}).get("team_name"),
                   "manager_name": names.get(int(rid), {}).get("manager_name"), "games": len(g), "wins": wins,
                   "losses": int((g["result"] == "L").sum()), "all_play_wins": int(g["all_play_wins"].sum()),
                   "all_play_losses": int(g["all_play_losses"].sum()), "all_play_ties": int(g["all_play_ties"].sum()),
                   "all_play_win_pct": None if pct is None else round(float(pct), 4),
                   "expected_wins": None if pct is None else round(len(g) * float(pct), 2),
                   "luck_wins": None if pct is None else round(wins - len(g) * float(pct), 2),
                   "top_half_weeks": int((g["week_points_rank"] <= g["rosters_in_week"] / 2.0).sum()),
                   "avg_points_rank": round(float(g["week_points_rank"].mean()), 2)})
    all_play = pd.DataFrame(ap)
    all_play["all_play_rank"] = all_play["all_play_wins"].rank(method="min", ascending=False).astype(int)
    all_play = all_play.sort_values(["all_play_rank", "roster_id"]).reset_index(drop=True)
    return standings, all_play, apw.drop(columns=["all_play_ties", "rosters_in_week"])


def od_transactions(league_id: str, rounds: int, rosters: list[dict], users: list[dict], players: dict) -> pd.DataFrame:
    """mart_league_transactions from Sleeper's `/transactions/<round>` (one row per player moved: adds and drops)."""
    names = A.team_names(rosters, users)
    sl = A.sleeper()
    out = []
    for rnd in range(1, int(rounds) + 1):
        for t in sl.transactions(league_id, rnd):
            for action, moves in (("add", t.get("adds") or {}), ("drop", t.get("drops") or {})):
                for sid, rid in moves.items():
                    sp = players.get(str(sid)) or {}
                    rid = None if rid is None else int(rid)
                    out.append({"league_id": str(league_id), "week": t.get("leg") or rnd, "transaction_id": str(t.get("transaction_id")),
                                "transaction_type": t.get("type"), "status": t.get("status"),
                                "created_at": pd.Timestamp(int(t["created"]), unit="ms", tz="UTC") if t.get("created") else None,
                                "action": action, "roster_id": rid, "team_name": names.get(rid, {}).get("team_name"),
                                "manager_name": names.get(rid, {}).get("manager_name"), "sleeper_player_id": str(sid),
                                "player_name": (sp.get("full_name") or (f"{sp.get('first_name', '')} {sp.get('last_name', '')}".strip()
                                                if sp.get("position") == "DEF" else None) or str(sid)),
                                "position": sp.get("position"),
                                "waiver_bid": (t.get("settings") or {}).get("waiver_bid"), "notes": None})
    df = pd.DataFrame(out)
    if df.empty:
        return df
    return df.sort_values(["created_at", "transaction_id", "action", "sleeper_player_id"],
                          ascending=[False, True, True, True]).reset_index(drop=True)


def league_words(standings: pd.DataFrame, all_play: pd.DataFrame, me: int | None, n_weeks: int, season: int,
                 bench: dict[int, float] | None = None) -> str | None:
    """The League page's first line (quoted from app/pages/8_League.py: top-level page code): your schedule luck and
    your bench, or the league's luckiest / unluckiest when no team is picked."""
    if all_play.empty:
        return None
    scored = all_play[all_play["luck_wins"].notna()].copy()
    scored["luck_wins"] = pd.to_numeric(scored["luck_wins"])
    weeks_txt = f"{n_weeks} week{'s' if n_weeks != 1 else ''}"
    n_teams = len(scored)

    def nth(k: int, word: str) -> str:
        return f"the {word}" if k == 1 else f"the {_ordinal(k)}-{word}"
    mine = scored[scored["roster_id"] == me] if me is not None else scored.iloc[0:0]
    if not mine.empty:
        luck = float(mine.iloc[0]["luck_wins"])
        if abs(luck) < 0.05:
            luck_txt = "Your record is exactly what your points deserve"
        elif luck < 0:
            luck_txt = f"You've been {nth(int((scored['luck_wins'] < luck).sum()) + 1, 'unluckiest')} team by schedule ({luck:+.1f} wins)"
        else:
            luck_txt = f"You've been {nth(int((scored['luck_wins'] > luck).sum()) + 1, 'luckiest')} team by schedule ({luck:+.1f} wins)"
        if bench and me in bench:
            b = float(bench[me])
            kb = sum(1 for v in bench.values() if v > b) + 1
            rank = ("the most in the league" if kb == 1 else "the fewest in the league" if kb == n_teams
                    else f"the {_ordinal(kb)} most of {n_teams}")
            return f"**{luck_txt}; your bench has left {b:.0f} points unstarted** ({rank}, {weeks_txt})."
        return f"**{luck_txt}** ({weeks_txt})."
    lk = scored.sort_values("luck_wins", ascending=False)
    return (f"**Luckiest by schedule: {lk.iloc[0]['team_name']} ({lk.iloc[0]['luck_wins']:+.1f} wins); unluckiest: "
            f"{lk.iloc[-1]['team_name']} ({lk.iloc[-1]['luck_wins']:+.1f})** — {season}, {weeks_txt}.")


def league(league_id: str, team: int | None = None, limit: int = 50, offset: int = 0, *, source: str | None = None) -> dict:
    t0 = time.perf_counter()
    is_house = house(league_id, source)
    out: dict = {"league_id": str(league_id), "source": "database" if is_house else "sleeper", "roster_id": team}
    if is_house:
        members = _members(league_id)
        _team_check(members, team)
        season = int(cards.league_season(league_id))
        standings, all_play = query(STANDINGS_SQL, (league_id,)), query(ALL_PLAY_SQL, (league_id,))
        apw = query(ALL_PLAY_WEEK_SQL, (league_id,))
        prof = query(PROFILE_SQL, (league_id,))
        tx = query(TX_SQL, (league_id,))
        draft = query(DRAFT_SQL, (league_id,))
        bench = {int(r.roster_id): float(r.total_bench_points_left) for r in prof.itertuples()
                 if _num(r.total_bench_points_left) is not None} if not prof.empty else {}
        out["season"] = season
        out["profiles"] = _records(prof)
        out["draft"] = _records(draft)
        try:
            rk = query(RANKINGS_SQL, (league_id,))
        except Exception:  # noqa: BLE001 - the roster rankings appear after the build publishes them
            rk = pd.DataFrame()
        out["roster_rankings"] = _records(rk)
    else:
        lg, rosters, users = _sleeper_league(league_id)
        names = A.team_names(rosters, users)
        _team_check(names, team)
        season = int(lg["season"])
        last = int((lg.get("settings") or {}).get("last_scored_leg") or 0)
        weeks = _od(A.sleeper().season_matchups, lg["league_id"], last) if last > 0 else {}
        standings, all_play, apw = od_league_marts(lg, rosters, users, weeks)
        players = _od(A.sleeper().players)
        cur = cards.decision_week(season) or last
        tx = _od(od_transactions, lg["league_id"], max(last, int(cur or 0)), rosters, users, players)
        if not tx.empty:
            idm = query("select sleeper_id, gsis_id from analytics.player_id_map where sleeper_id = any(%s)",
                        (sorted(set(tx["sleeper_player_id"])),))
            tx["gsis_id"] = tx["sleeper_player_id"].map(dict(zip(idm["sleeper_id"], idm["gsis_id"], strict=False)))
        bench = None
        out["season"] = season
        out["profiles"] = None
        out["draft"] = None
        out["roster_rankings"] = None
        out["not_on_demand"] = ("manager profiles (bench points left, FAAB), the draft review and the roster rankings need the "
                                "league's history in the database (house leagues); the roster rankings are on /api/team")
        out["on_demand"] = {"weeks_fetched": sorted(weeks), "transaction_rounds": max(last, int(cur or 0))}
    n_weeks = int(apw["week"].nunique()) if not apw.empty else 0
    out["weeks_scored"] = n_weeks
    out["standings"] = _records(standings)
    out["all_play"] = _records(all_play)
    out["all_play_week"] = _records(apw)
    if not tx.empty:
        b = bio(tx["gsis_id"].dropna())
        tx_rows = []
        for r in tx.to_dict("records"):
            r = {k: (v.item() if hasattr(v, "item") else v) for k, v in r.items()}
            info = b.get(r.get("gsis_id")) or {}
            r["headshot_url"] = info.get("headshot_url")
            r["team"] = info.get("team") or (r.get("sleeper_player_id") if r.get("position") == "DEF" else None)
            tx_rows.append(r)
    else:
        tx_rows = []
    out["transactions_total"] = len(tx_rows)
    out["transactions"] = _page(tx_rows, limit, offset)
    out["words"] = {"headline": league_words(standings, all_play, team, n_weeks, season, bench),
                    "source": "quoted from app/pages/8_League.py (the first line)"}
    out["timings_ms"] = {"total": round((time.perf_counter() - t0) * 1000, 1)}
    return out


# ================================================================================== Wave H (H1): the upside stash, buy low / sell high
# /api/waivers carries two more regions the Streamlit pages show: the upside stash (the Waiver Wire's third card region,
# app/lib/signals.py upside_cards: mart_waiver_upside) and buy low / sell high (the Trade Finder's two lists,
# roster_value.trade_candidates on the league's horizon board, the candidates' PPG - xPPG in the league's scoring).
import json  # noqa: E402 - the H1 block stays self-contained

from league_lab.scoring import compute_points as _compute_points  # noqa: E402

from . import research as RS  # noqa: E402
from .applib import signals as SG  # noqa: E402
from .db import missing_relations  # noqa: E402

UPSIDE_TITLE = "Upside stash: his role is growing before his points do"
UPSIDE_SQL = SG.UPSIDE_SQL
# the Trade Finder's candidates (app/pages/6_Trade_Finder.py `avail`): rostered QB-TE with two games of expected points
CANDIDATES_SQL = """select sleeper_id as sleeper_player_id, gsis_id, player_name, position, rostered_by_roster_id, games_with_expected,
                           ppg_std, expected_per_game, diff_per_game
                    from analytics.mart_player_availability
                    where league_id = %s and not is_free_agent and position in ('QB','RB','WR','TE')
                      and coalesce(games_with_expected, 0) >= 2 and diff_per_game is not null"""
SCENARIO_SQL = """select s.league_id, s.week, s.gsis_id, s.position, s.base_points, s.larger_points, s.points_gain,
                         s.with_alert_points, s.presentation, s.alert_week, s.since_week, s.games_held, s.confidence, s.kind,
                         s.trigger_kind, s.trigger_name, s.cause_text, s.change_text, s.expires_after_week, s.expiry_rule,
                         s.backtest_n, s.backtest_hit_rate, s.base_line, s.larger_line
                  from ops.player_scenarios as s where s.season = %s and s.week >= %s order by s.week, s.league_id"""
TRADE_POSITIONS = ("QB", "RB", "WR", "TE")
# quoted from app/pages/6_Trade_Finder.py ("How to read the buy-low and sell-high lists")
TRADE_HOWTO = (
    "**Buy low**: players on other teams scoring *less* than their work is worth (**PPG − xPPG**, points minus expected points "
    "per game, below zero). Their manager sees a bad box score; the work says it should turn around. **Sell high**: your "
    "players scoring *more* than their work supports.",
    "**You gain** is how much your best lineup goes up with him (a WR who beats your FLEX counts; a QB who would sit on your "
    "bench adds nothing). **They lose** is how much their lineup drops without him, 0 if he sits on their bench. Both are for "
    "this week and the next four, in your league's scoring.",
    "**Fit** is what the new team gains minus what the old team loses. A big positive fit means he matters more to the other "
    "team than to his own: an easier ask when you buy, a better sale when you sell.",
    "These lists look at one player at a time. To see a whole offer, with what you send back and who gets cut, use the Trade "
    "Finder.",
)
UPSIDE_HOWTO = (
    "**Upside stash**: a free agent whose role grew in his last one to three games (more snaps, targets or carries: a "
    "teammate out, a new starter) before his points caught up. **If it holds** is his projection with the bigger role: a "
    "what-if, not a forecast.",
    "**Lineup gain if it holds** adds up this week and the next three in your lineup; most stashes add nothing yet, which is "
    "why they are stashes, not starters.",
)


def _nan_none(r: dict) -> dict:
    return {k: (None if isinstance(v, float) and math.isnan(v) else v) for k, v in r.items()}


def _stash(r: dict, b: dict) -> dict:
    """One mart_waiver_upside row as the screen's card: the player, the drop, the numbers, the page's sentences."""
    r = _nan_none(r)
    add = _player(r.get("add_sleeper_id"), r.get("add_gsis_id"), r.get("add_name"), r.get("add_position"), r.get("add_team"), b)
    drop = (_player(r.get("drop_sleeper_id"), r.get("drop_gsis_id"), r.get("drop_name"), r.get("drop_position"), None, b)
            if _str(r.get("drop_name")) else None)
    return {"rank": _int(r.get("upside_rank")), "add": add, "drop": drop, "base_value": _num(r.get("base_value")),
            "scenario_value": _num(r.get("scenario_value")), "points_gain": _num(r.get("points_gain")),
            "holds_weekly_gain": _num(r.get("holds_weekly_gain")), "holds_horizon_gain": _num(r.get("holds_horizon_gain")),
            "holds_slot": _str(r.get("holds_slot")), "drop_horizon_loss": _num(r.get("drop_horizon_loss")),
            "change_text": _str(r.get("change_text")), "cause_text": _str(r.get("cause_text")),
            "since_week": _int(r.get("since_week")), "games_held": _int(r.get("games_held")), "kind": _str(r.get("kind")),
            "headline": SG.stash_headline(r), "lines": SG.upside_detail(r)}


def _scenario_on_demand(r: dict, scoring: dict, league_name: str, week: int) -> dict:
    """An NFL-wide alert with its stat-line what-if priced in this league's scoring (compute_points on both lines)."""
    r = _nan_none(r)
    lines = {}
    for k in ("base_line", "larger_line"):
        v = r.get(k)
        line = v if isinstance(v, dict) else (json.loads(v) if isinstance(v, str) else None)
        lines[k] = None if line is None else round(float(_compute_points({**line, "position": r.get("position")}, scoring)), 2)
    base, big = lines["base_line"], lines["larger_line"]
    gain = None if base is None or big is None else round(big - base, 2)
    row = {**r, "base_points": base, "larger_points": big, "points_gain": gain, "presentation": None, "week": r.get("week")}
    return {"base_value": base, "scenario_value": big, "points_gain": gain, "week": _int(r.get("week")),
            "change_text": _str(r.get("change_text")), "cause_text": _str(r.get("cause_text")),
            "since_week": _int(r.get("since_week")), "games_held": _int(r.get("games_held")), "kind": _str(r.get("kind")),
            "headline": None, "lines": [x for x in (SG.scenario_phrase(row, league_name), SG.alert_lines(r)) if x]}


def _upside(league_id: str, team: int | None, week: int, is_house: bool, od_info: dict) -> dict:
    if team is None:
        return {"title": UPSIDE_TITLE, "stashes": [], "why": None, "howto": UPSIDE_HOWTO}
    if is_house:
        if missing_relations(("mart_waiver_upside",)):
            return {"title": UPSIDE_TITLE, "stashes": [], "howto": UPSIDE_HOWTO,
                    "why": "Upside stashes (a player whose role is growing before his points do) arrive with the nightly update."}
        up = query(UPSIDE_SQL, (league_id, int(team), int(week)))
        rows = up.to_dict("records")
        b = bio([r.get("add_gsis_id") for r in rows] + [r.get("drop_gsis_id") for r in rows])
        out = [_stash(r, b) for r in rows]
        why = None if out else (f"No upside stash for week {week}: no free agent's role grew in his last one to three games "
                                "without already making the lists above (see Trends for every role change).")
        return {"title": UPSIDE_TITLE, "stashes": out, "why": why, "howto": UPSIDE_HOWTO, "source": "mart_waiver_upside"}
    # any other league: the alert and the stat-line what-if are NFL-wide; the lineup gains are the nightly's per house league
    fa = od_info.get("fa")
    why = ("The role alert and the what-if are NFL-wide, priced here in your league's scoring; what claiming him adds to your "
           "lineup if the role holds is worked out each night for the leagues League Lab updates, not on request.")
    has = query("select to_regclass('ops.player_scenarios') is not null as ok", ())
    if fa is None or fa.empty or not bool(has["ok"].iloc[0]):
        return {"title": UPSIDE_TITLE, "stashes": [], "why": why, "howto": UPSIDE_HOWTO, "source": "on demand"}
    league, _, _ = _sleeper_league(league_id)
    scoring = A.league_scoring(league)[0]
    sc = query(SCENARIO_SQL, (int(league["season"]), int(week)))
    free = {g: s for g, s in zip(fa["gsis_id"], fa["sleeper_id"], strict=True) if isinstance(g, str)}
    seen, rows = set(), []
    for r in sc.to_dict("records"):
        if r["gsis_id"] in free and r["gsis_id"] not in seen:
            seen.add(r["gsis_id"])
            rows.append(r)
    name = str(league.get("name") or "your league")
    b = bio([r["gsis_id"] for r in rows])
    stashes = []
    for r in rows:
        s = _scenario_on_demand(r, scoring, name, int(week))
        meta = fa[fa["gsis_id"] == r["gsis_id"]].iloc[0]
        s["add"] = _player(free[r["gsis_id"]], r["gsis_id"], meta["player_name"], r["position"], _str(meta.get("nfl_team")), b)
        s["headline"] = SG.stash_headline({"add_name": meta["player_name"], "add_position": r["position"], **_nan_none(r)})
        s.update({"drop": None, "holds_weekly_gain": None, "holds_horizon_gain": None, "holds_slot": None})
        stashes.append(s)
    stashes.sort(key=lambda s: (-(s["points_gain"] or 0), -(s["scenario_value"] or 0), s["add"]["player_name"] or ""))
    for i, s in enumerate(stashes, 1):
        s["rank"] = i
    return {"title": UPSIDE_TITLE, "stashes": stashes, "why": why, "howto": UPSIDE_HOWTO, "source": "on demand"}


def _trade_lists(league_id: str, team: int, is_house: bool, od_info: dict) -> dict:
    """roster_value.trade_candidates for the roster: buy low (other rosters, PPG - xPPG < 0) and sell high (his own, > 0),
    each with the lineup gain / loss this week and over the horizon and the fit; the best per position."""
    if is_house:
        hz = query(HORIZON_SQL, (league_id,))
        if hz.empty:
            return {"buy_low": [], "sell_high": [], "why": "No lineups for the weeks ahead yet."}
        slots = list(ui.league_seasons(league_id).set_index("league_id").loc[league_id, "roster_positions"] or [])
        cands = query(CANDIDATES_SQL, (league_id,))
        names = _members(league_id)
    else:
        lw = od_info.get("lw")
        if lw is None:
            return {"buy_low": [], "sell_high": [], "why": None}
        hz = A.horizon_frame(lw)
        slots = list(lw.slots)
        ctx = RS.context(league_id, "sleeper")
        ls = RS.league_season(ctx, ctx.season)
        ls = ls[(ls["games_with_expected"].fillna(0) >= 2) & ls["diff_per_game"].notna()]
        who = hz.drop_duplicates("sleeper_player_id")[["sleeper_player_id", "gsis_id", "player_name", "position"]]
        who = who[who["position"].isin(TRADE_POSITIONS) & who["gsis_id"].notna()]
        cands = who.merge(ls[["gsis_id", "games_with_expected", "ppg", "expected_per_game", "diff_per_game"]], on="gsis_id")
        cands = cands.rename(columns={"ppg": "ppg_std"})
        names = lw.names
    board = RosterBoard(hz.to_dict("records"), tuple(slots))
    from league_lab.roster_value import trade_candidates
    buy, sell = trade_candidates(board, int(team), cands.to_dict("records"))
    weeks = board.weeks
    span = f"weeks {weeks[0]}–{weeks[-1]}" if len(weeks) > 1 else f"week {weeks[0]}" if weeks else ""
    b = bio([d.get("gsis_id") for d in buy + sell])

    def row(d: dict, other_key: str) -> dict:
        d = _nan_none(d)
        p = _player(d.get("sleeper_player_id"), d.get("gsis_id"), d.get("player_name"), d.get("position"), None, b)
        other = _int(d.get(other_key))
        return {"player": p, "roster_id": other, "team_name": (names.get(other) or {}).get("team_name") if other is not None else None,
                "ppg": _num(d.get("ppg_std")), "xppg": _num(d.get("expected_per_game")), "diff_per_game": _num(d.get("diff_per_game")),
                "gain_week": _num(d.get("gain_week")), "gain_horizon": _num(d.get("gain_horizon")),
                "loss_week": _num(d.get("loss_week")), "loss_horizon": _num(d.get("loss_horizon")),
                "fit_week": _num(d.get("fit_week")), "fit_horizon": _num(d.get("fit_horizon"))}
    buy_rows, sell_rows = [row(d, "owner") for d in buy], [row(d, "partner") for d in sell]
    best = {}
    for pos in TRADE_POSITIONS:          # the page's best_by_position: the first with a positive fit over the horizon
        top = next((r for r in buy_rows if r["player"]["position"] == pos and (r["fit_horizon"] or 0) > 0), None)
        if top is not None:
            best[pos] = top
    top_buy = max(best.values(), key=lambda r: (r["fit_horizon"], r["gain_horizon"]), default=None)
    top_sell = next((r for r in sell_rows if (r["fit_horizon"] or 0) > 0), None)
    wk = weeks[0] if weeks else None
    # quoted from app/pages/6_Trade_Finder.py (the buy-low / sell-high cards)
    if top_buy is None:
        buy_line = f"**Buy low:** nobody scoring below his usage would add more to your lineup than he is worth to his own over {span}."
    else:
        t = top_buy
        buy_line = (f"**Buy low: ask {t['team_name']} about {t['player']['player_name']} ({t['player']['position']}).** "
                    f"He scores {abs(t['diff_per_game']):.1f} a game below what his usage is worth, adds **{t['gain_week']:+.1f}** "
                    f"to your week-{wk} lineup and costs them **{t['loss_week']:.1f}** (fit **{t['fit_horizon']:+.1f}** over {span}).")
    if top_sell is None:
        sell_line = (f"**Sell high:** none of your players scoring above his usage is worth more to another lineup than to "
                     f"yours over {span}.")
    else:
        t = top_sell
        sell_line = (f"**Sell high: shop {t['player']['player_name']} ({t['player']['position']}) to {t['team_name']}.** "
                     f"He scores {t['diff_per_game']:.1f} a game above what his usage is worth. Their week-{wk} lineup "
                     f"gains **{t['gain_week']:+.1f}**, yours loses **{t['loss_week']:.1f}** (fit **{t['fit_horizon']:+.1f}** "
                     f"over {span}).")
    return {"buy_low": buy_rows, "sell_high": sell_rows, "best_buy_by_position": best, "buy_line": buy_line,
            "sell_line": sell_line, "weeks": span, "howto": TRADE_HOWTO,
            "source": "app/pages/6_Trade_Finder.py (roster_value.trade_candidates; the card sentences quoted)",
            "points_source": "mart_player_availability" if is_house else "priced on request (research.league_season)"}


def waiver_extras(league_id: str, team: int | None, week: int, is_house: bool, od_info: dict, position: str) -> dict:
    """The upside stash for /api/waivers (filtered to `position` when one is asked). IA-2: buy low / sell high left
    Waivers for Trades (`trade_lists`, GET /api/trades/lists)."""
    t0 = time.perf_counter()
    up = _upside(league_id, team, week, is_house, od_info)
    if position != "ALL":
        up["stashes"] = [s for s in up["stashes"] if s["add"]["position"] == position]
    return {"upside": up, "extras_ms": round((time.perf_counter() - t0) * 1000, 1)}


# ---- IA-2: buy low / sell high on the Trades screen (GET /api/trades/lists): Wave H's lists, moved from /api/waivers
def trade_lists(league_id: str, team: int, position: str | None = None, *, source: str | None = None) -> dict:
    """roster_value.trade_candidates for the roster (`_trade_lists`): a house league from its horizon mart, any other
    on the trade context's solve (the board the partner finder reads). Filtered to `position`, 25 rows a list."""
    t0 = time.perf_counter()
    position = (position or "ALL").upper()
    if position not in (*TRADE_POSITIONS, "ALL"):
        raise NotFound(f"no position {position} (QB, RB, WR, TE or ALL)")
    is_house = house(league_id, source)

    def build():
        if is_house:
            _team_check(_members(league_id), team)
            return _trade_lists(league_id, int(team), True, {})
        ctx = trade_context(league_id, source)
        _team_check(ctx.names, team)
        return _trade_lists(league_id, int(team), False, {"lw": ctx.lw})
    out = dict(_memo(("trade_lists", str(league_id), int(team), is_house), is_house, build))
    for k in ("buy_low", "sell_high"):
        rows = out.get(k, [])
        if position != "ALL":
            rows = [r for r in rows if r["player"]["position"] == position]
        out[k] = rows[:25]
    out.update({"league_id": str(league_id), "source": "database" if is_house else "sleeper", "roster_id": int(team),
                "position": position, "timings_ms": {"total": round((time.perf_counter() - t0) * 1000, 1)}})
    return out
# ---- end IA-2
