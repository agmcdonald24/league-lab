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
import re
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


# ---- IE-0 (Wave I-E): a package with an asset the analysis cannot use answers 400 with every such asset named
# (`unavailable`: key, side, name, why) — never a silent one-for-one (the review's P0 #1)
IDP_POSITIONS = frozenset({"DL", "LB", "DB", "DT", "DE", "CB", "S", "IDP"})


class Unavailable(BadRequest):
    def __init__(self, items: list[dict]):
        self.items = items
        super().__init__("Can't analyse " + "; ".join(f"{i['name'] or i['key']}: {i['why']}" for i in items) + ".")
# ---- end IE-0


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
    # ---- IB-0: one availability truth - this week's part of every move re-solved on the roster's context (the
    # overlay), so a player who starts because Jefferson is out is never "would not start" and the totals are My Week's
    rctx = _waiver_context(league_id, team, int(week), is_house)
    if rctx is not None and rctx.changed:
        mv = availability.moves_on_context(mv, rctx)
    # ---- end IB-0
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
    _waivers_on_context(out, rctx)                  # ---- IB-0: the total, the weakest starter, the drops' words
    # ---- IB-2: the three strongest moves with one reason each, the views, the best alternative before a drop
    out.update(waiver_views(league_id, team, season, int(week), mv, out, is_house, od_info, ros))
    # ---- end IB-2
    if not is_house:
        out["on_demand"] = {k: v for k, v in od_info.items() if k not in ("lw", "fa")}
    out["timings_ms"] = {"request_total": round((time.perf_counter() - t0) * 1000, 1)}
    return out


# ---- IB-0 (Wave I-B): Waivers on the roster's context (availability.roster_context): the lineup total, the weakest
# starter (what a claim has to beat) and each drop's "starts this week" are the context's; the moves' numbers are
# re-solved on it (availability.moves_on_context) before the page's sentences are written.
def _waiver_context(league_id: str, team: int | None, week: int, is_house: bool):
    if team is None:
        return None
    try:
        return availability.roster_context(league_id, int(team), int(week), house=is_house)
    except (A.SleeperBusy, A.SleeperUnavailable, A.LeagueNotFound):
        return None


def context_weakest(rctx) -> dict | None:
    """The waivers' ``weakest`` block from the context: the weakest slot's starter, his margin, who comes in."""
    if rctx is None or rctx.rows is None or rctx.rows.empty or not rctx.weakest_slot:
        return None
    st = rctx.rows[(rctx.rows["role"] == "starter") & (rctx.rows["slot"] == rctx.weakest_slot)]
    if st.empty:
        return None
    w = st.iloc[0]
    rep = rctx.replacement(w)
    return {"slot": w["slot"], "player": _player(w["sleeper_player_id"], w["gsis_id"], w["player_name"], w["position"], None,
                                                 bio([w["gsis_id"]])),
            "value": _num(w["value"]), "margin": _num(w["margin"]),
            "replacement_name": None if rep is None else _str(rep["player_name"]),
            "replacement_value": None if rep is None else _num(rep["value"])}


def _waivers_on_context(out: dict, rctx) -> None:
    if rctx is None:
        return
    for m in [*(out.get("moves") or []), *[c.get("move") or {} for c in out.get("cards") or []]]:
        availability.drop_words(m, rctx)
    out["roster_context"] = rctx.summary()
    if rctx.changed:
        out["lineup_value"] = rctx.lineup_value
        out["weakest"] = context_weakest(rctx) or out.get("weakest")
# ---- end IB-0


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
            # ---- IC-2: a team unit (MFL's TMQB / TMPK) is priced by its team (A.price_units), not by an id
            m = df["position"].isin(A.LU.UNITS)
            for i in df.index[m]:
                u = A.unit_value(pr, df.at[i, "position"], df.at[i, "nfl_team"]) or {}
                for c in ("proj_points", "p10", "p25", "p75", "p90"):
                    df.at[i, c] = u.get(c, np.nan)
            # ---- end IC-2
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
            self.directory = players                     # ---- IE-0: a unit's team, an unknown key's name
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
        # ---- IB-0: this week's lineup on the board = each roster's context (the rosters the overlay moved): the roster
        # view (who starts, where, his value) is My Week's; the board re-solves to the same total
        self.horizon, self.contexts = board_on_context(self.league_id, self.is_house, self.horizon, self.this_week)
        # ---- end IB-0
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
        # ---- IE-0: a team unit (MFL's TMQB / TMPK) carries its NFL team (the badge) and `unit`: a missing team is
        # never read as "FA" on a rostered unit
        if p.get("position") in UNIT_POSITIONS:
            p["unit"] = True
            p["team"] = p.get("team") or (self.directory_row(pid) or {}).get("team")
        # ---- end IE-0
        return p

    # ---- IE-0 (Wave I-E): asset keys are opaque ("mfl:0682", "12490", "HOU"); one the analysis cannot use is named
    def directory_row(self, pid) -> dict | None:
        d = getattr(self, "directory", None) or {}
        row = d.get(str(pid)) if isinstance(d, dict) else None
        return row if isinstance(row, dict) else None

    def known_name(self, pid) -> str | None:
        """His name from the board, else the league's directory (a player on no roster), else None (an unknown key)."""
        if pid in self.info.index:
            return self.name(pid)
        row = self.directory_row(pid) or {}
        name = row.get("player_name") or row.get("full_name") or " ".join(
            x for x in (row.get("first_name"), row.get("last_name")) if x)
        return str(name) if name else None

    def unavailable(self, team: int, partner: int, give: list[str], get: list[str]) -> list[dict]:
        """The keys the trade cannot be analysed with, each with its side, name and why (never a silent drop): not on
        that side's roster, a key nobody knows, or a defensive player (IDP: the lineup solver does not price them)."""
        out = []
        for side, keys, rid in (("give", give, int(team)), ("get", get, int(partner))):
            for k in keys:
                name, owner = self.known_name(k), self.board.owner(k)
                pos = self.pos(k) if k in self.info.index else str((self.directory_row(k) or {}).get("position") or "")
                if owner == rid and pos in IDP_POSITIONS:
                    why = f"League Lab does not price defensive players ({pos}) yet"
                elif owner == rid:
                    continue
                elif name is None:
                    why = "not a player League Lab knows in this league"
                elif owner is not None:
                    why = f"on {self.team(owner)}'s roster, not {self.team(rid)}'s"
                else:
                    why = f"not on {self.team(rid)}'s roster"
                out.append({"key": str(k), "side": side, "name": name, "why": why})
        return out
    # ---- end IE-0

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


# ---- IB-0 (Wave I-B): the trade board's this-week rows on the roster contexts (availability.roster_context)
def board_on_context(league_id: str, is_house: bool, horizon: pd.DataFrame, this_week: int) -> tuple[pd.DataFrame, dict]:
    """(the board's rows with this week's rows of every roster the overlay moved replaced by its context's — role, slot,
    value, margin, lock, reason; the rest of each row as the board had it —, {roster id: context})."""
    if horizon is None or horizon.empty or not availability.enabled():
        return horizon, {}
    wk = horizon["week"] == int(this_week)
    tw = horizon[wk & horizon["gsis_id"].notna() & horizon["role"].isin(["starter", "bench"])]
    by_roster = {int(r): list(g) for r, g in tw.groupby("roster_id")["gsis_id"]}
    try:
        ctxs = availability.contexts(league_id, availability.touched(by_roster), int(this_week), house=is_house)
    except (A.SleeperBusy, A.SleeperUnavailable, A.LeagueNotFound):
        return horizon, {}
    ctxs = {rid: c for rid, c in ctxs.items() if c is not None and c.changed and not c.rows.empty}
    if not ctxs:
        return horizon, ctxs
    keep = horizon[~(wk & horizon["roster_id"].isin(list(ctxs)))]
    add = []
    for rid, c in ctxs.items():
        old = horizon[wk & (horizon["roster_id"] == rid)]
        if old.empty:
            continue
        by_sid = {str(r["sleeper_player_id"]): r.to_dict() for _, r in old.iterrows() if isinstance(r["sleeper_player_id"], str)}
        template = {k: v for k, v in old.iloc[0].to_dict().items()}
        for _, r in c.rows.iterrows():
            empty = bool(r["is_empty_slot"])
            sid = r["sleeper_player_id"] if isinstance(r["sleeper_player_id"], str) else None
            base = dict(by_sid.get(str(sid), template)) if not empty else dict(template)
            if empty or sid not in by_sid:
                base.update({"sleeper_player_id": sid, "gsis_id": r["gsis_id"], "player_name": r["player_name"],
                             "position": r["position"], "value_source": r["value_source"]})
            base.update({"role": "empty" if empty else r["role"], "slot": r["slot"], "slot_type": r["slot_type"],
                         "player_value": r["value"], "lineup_margin": r["margin"],
                         "is_locked": bool(r.get("is_locked")) and r["role"] == "starter", "reason": r["reason"]})
            for col, v in (("slot_order", r["slot_order"]), ("bench_rank", r["bench_rank"]), ("report_status", r["report_status"])):
                if col in base:
                    base[col] = v
            add.append(base)
    out = pd.concat([keep, pd.DataFrame(add, columns=horizon.columns)], ignore_index=True)
    for col in ("player_value", "lineup_margin"):
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out["is_locked"] = out["is_locked"].fillna(False).astype(bool)
    return out, ctxs
# ---- end IB-0


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
    label = effect_label(g)                                           # ---- IE-1: an outcome, not an acceptance claim
    pts = INTEREST_POINTS
    if g <= pts[0][0]:
        score = pts[0][1]
    elif g >= pts[-1][0]:
        score = pts[-1][1]
    else:
        score = next(y0 + (g - x0) * (y1 - y0) / (x1 - x0) for (x0, y0), (x1, y1) in zip(pts, pts[1:], strict=False)
                     if x0 <= g <= x1)
    return {"score": int(round(score)), "label": label, "their_gain": round(g, 2),
            "you": None if my_gain is None else round(float(my_gain), 2), "caption": f"their starters over {span}, by our numbers",
            "title": EFFECT_TITLE, "need": None}                                                  # ---- IE-1


# ---- IE-1 (Wave I-E, the casual-user review § "replace the interest dial's implied acceptance prediction"): the dial is
# the EFFECT ON THEIR STARTERS - the partner's best-lineup gain over the window, by our numbers - in outcome words; it
# says nothing about whether the other manager would accept. Same number, same thresholds (0.05 / 2 / 6), same needle.
EFFECT_TITLE = "Effect on their starters"
EFFECT_LABELS = ("Makes their lineup weaker", "About even", "Improves their lineup", "Improves it a lot")


def effect_label(g: float) -> str:
    return EFFECT_LABELS[0] if g < -0.05 else EFFECT_LABELS[1] if g < 2 else EFFECT_LABELS[2] if g <= 6 else EFFECT_LABELS[3]


def need_words(side: T.Side, ctx) -> str | None:
    """The need the trade fills for that side, in one phrase, from its lineup this week by starter MEMBERSHIP (a starter
    who only moves between numbered slots is not a change): "fills their empty RB", "starts at their WR/TE over
    Egbuka" (who goes to the bench), "takes over their team QB from Kansas City Chiefs QB" (whom they trade away);
    None when nobody it gets starts this week."""
    lb, la = side.lineup_before, side.lineup_after
    if lb is None or la is None:
        return None
    before = {s.player.id for s in lb.starts if s.player is not None}
    gets = set(side.gets)
    new = [s for s in la.starts if s.player is not None and s.player.id in gets and s.player.id not in before]
    if not new:
        return None
    slot = re.sub(r"\s*\d+$", "", cards.slot_label(new[0].slot.label))
    if any(s.player is None and s.slot.type == new[0].slot.type for s in lb.starts):
        return f"fills their empty {slot}"
    out = list(side.sits)
    benched = [x for x in out if x not in set(side.gives)]
    if benched:
        return f"starts at their {slot} over {ctx.name(benched[0])}"
    if out:
        return f"takes over their {slot} from {ctx.name(out[0])}"
    return f"starts at their {slot}"
# ---- end IE-1


SCORING_SQL = "select scoring_settings from analytics.dim_league_season where league_id = %s order by season desc limit 1"


def market_week(ctx: TradeContext) -> dict[str, float]:
    """Sleeper id -> Sleeper's projection this week in this league's scoring. PO merge (Wave I-A): read through IA-3's
    ``why.market_points`` — ``analytics.mart_market_line`` (built by dbt from raw.sleeper_projections, on the hosted
    copy too) priced with ``scoring.compute_points`` — instead of ``raw`` directly, which the hosted copy never holds.
    Empty when the mart has no row for the week; rule (b) is then not applied and the response says so."""
    if "market_week" in ctx.window_cache:
        return ctx.window_cache["market_week"]
    out: dict[str, float] = {}
    try:
        from . import why as _why
        if ctx.lw is not None:
            scoring = dict(ctx.lw.scoring)
        else:
            sc = query(SCORING_SQL, (ctx.league_id,))
            raw = sc["scoring_settings"].iloc[0] if not sc.empty else {}
            raw = json.loads(raw) if isinstance(raw, str) else (raw or {})
            scoring = {k: float(v) for k, v in raw.items() if v is not None}
        gs = {str(sid): ctx.gsis(sid) for sid in ctx.info.index}
        pts = _why.market_points(ctx.season, ctx.this_week, [g for g in gs.values() if g], scoring)
        out = {sid: float(pts[str(g)]) for sid, g in gs.items() if g and str(g) in pts}
    except Exception:  # noqa: BLE001 - no mart / no rows: rule (b) is not applied, the response says so
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
    # ---- IE-0: every key kept as sent (opaque: "mfl:0682" is a key like "12490"); one the analysis cannot use is named
    gave, got = T.parse_ids(list(give)), T.parse_ids(list(get))
    missing = ctx.unavailable(int(team), int(partner), gave, got)
    if missing:
        raise Unavailable(missing)
    g, t, bad = T.clean_package(ctx.board, int(team), int(partner), gave, got)
    # ---- end IE-0
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
           "interest": {**interest(th.gain_horizon, me.gain_horizon, span), "need": need_words(now.theirs, ctx)},  # IE-1
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
    out.update(trade_story(ctx, out, now, trade, board, weeks, window))      # ---- IE-2: through the starting lineup
    calc_alternatives(ctx, out, now, trade, board, weeks, window, (g, t), (ros, ours, mkt), source=source, as_of=as_of)  # IF-2
    t3 = time.perf_counter()
    out["timings_ms"] = {"context": round((t1 - t0) * 1000, 1), "evaluate": round((t2 - t1) * 1000, 1),
                         "words": round((t3 - t2) * 1000, 1), "total": round((t3 - t0) * 1000, 1)}
    if ctx.lw is not None:
        out["timings_ms"].update({f"league.{k}": v for k, v in ctx.lw.timings_ms.items()})
    return out


# ---- IE-1 (Wave I-E, the casual-user review § "avoid unnecessary extra assets"): when a partner's two-for-one gives
# two of yours for one of theirs and ONE of the two alone reaches the same gain for you (within 0.05) and still raises
# their lineup, the cheaper package leads (is_best, the headline, "Try this trade") and the two-for-one names the extra
# asset as optional: "Adding Tuten does not change your gain; it costs you RB depth (Tuten: 88 season points)". A bench
# player's cost is his rest-of-season points, never 0. Numbers unchanged: both packages keep their own gains.
SAME_GAIN = 0.05


def _ie1_cheaper(ctx, board, weeks, found, rows: list[dict], starts_now: bool, span: str) -> dict[int, T.Package]:
    out: dict[int, T.Package] = {}
    for p in found:
        two = p.two_for_one
        if two is None or len(two.give) != 2 or len(two.get) != 1:
            continue
        pts = {a: T.season_value(ctx.market, [a])[0] for a in two.give}
        best_one = None
        for a in sorted(two.give, key=lambda x: (pts.get(x) is None, pts.get(x) or 0)):
            try:
                pk = T.package_gains(board, (a,), two.get, weeks)
            except ValueError:
                continue
            if pk.mutual and abs(pk.my_horizon - two.my_horizon) < SAME_GAIN:
                best_one = pk
                break
        if best_one is None:
            continue
        extra = next(x for x in two.give if x not in best_one.give)
        out[p.roster_id] = best_one
        sp = pts.get(extra)
        pos = ctx.pos(extra) if hasattr(ctx, "pos") else None
        cost = f"{pos} depth" if pos else "depth"
        words = (f"Adding {ctx.name(extra)} does not change your gain; it costs you {cost}"
                 + (f" ({ctx.name(extra)}: {sp} season points)." if sp is not None else "."))
        two_row = next((r for r in rows if r["partner"] == p.roster_id and r["kind"] == "2-for-1"), None)
        if two_row is None:
            continue
        two_row["optional"] = {"sleeper_id": extra, "player_name": ctx.name(extra), "season_points": sp, "words": words}
        two_row["is_best"] = False
        same = next((r for r in rows if r["partner"] == p.roster_id and r["kind"] == "1-for-1"
                     and [x["sleeper_id"] for x in r["give"]] == list(best_one.give)
                     and [x["sleeper_id"] for x in r["get"]] == list(best_one.get)), None)
        for r in rows:
            if r["partner"] == p.roster_id:
                r["is_best"] = False
        if same is None:
            same = {"partner": p.roster_id, "partner_team": ctx.team(p.roster_id), "shape": best_one.shape, "kind": "1-for-1",
                    "is_best": True, "give": [ctx.player(x) for x in best_one.give], "get": [ctx.player(x) for x in best_one.get],
                    "you_gain_week": best_one.my_week if starts_now else None, "you_gain_horizon": best_one.my_horizon,
                    "they_gain_week": best_one.their_week if starts_now else None, "they_gain_horizon": best_one.their_horizon,
                    "interest": interest(best_one.their_horizon, best_one.my_horizon, span),
                    "price_out": T.season_value(ctx.prices, best_one.give)[0], "price_in": T.season_value(ctx.prices, best_one.get)[0]}
        else:
            rows.remove(same)
        rows.insert(next(i for i, r in enumerate(rows) if r["partner"] == p.roster_id), same)   # the partner's first row
        same["is_best"] = True
        same["cheaper_than"] = {"give": [ctx.name(x) for x in two.give], "words": f"Same gain for you without {ctx.name(extra)}."}
    return out
# ---- end IE-1


# ---- IF-2 (Wave I-F, the decision-quality review § Priority 3 "make trade recommendations compete with simpler
# alternatives"): one ladder per roster and window — standing pat (0), the best legal waiver move, the trade — under the
# same weeks and scoring. The finder ranks trades by the gain BEYOND the best alternative (starter points over the
# window) and says it; a trade that does not beat the waiver move is demoted below those that do and keeps a reason only
# when the numbers name another objective (this week, season value above replacement). The best waiver move is IF-1's
# `best_waiver_move` (net of the drop's cost) when it is in this module, over the next four weeks; otherwise (and for the
# other windows) the open-spot fill on today's free agents (`ctx.fa_pool` + `trades.best_fill`), and with no open spot
# the best add for each droppable player, his lineup loss netted out (today's drop rule). Numbers of the trades unchanged.
VALUE_CONCEPTS = T.VALUE_CONCEPTS
STAND_PAT = "stand_pat"


def _alt_player(ctx: TradeContext, meta: dict, sid) -> dict | None:
    if sid is None:
        return None
    m = meta.get(sid) or {}
    if not m and ctx.board.owner(sid) is not None:
        return {"sleeper_id": str(sid), "gsis_id": _str(ctx.gsis(sid)), "player_name": ctx.name(sid), "position": ctx.pos(sid)}
    return {"sleeper_id": str(sid), "gsis_id": _str(m.get("gsis_id")), "player_name": m.get("player_name") or str(sid),
            "position": m.get("position")}


def _claim_name(alt: dict) -> str:
    p = alt.get("player") or {}
    n = p.get("player_name") or "a free agent"
    if p.get("position") == "DEF" and not n.endswith(("defense", "D/ST")):
        n = f"{n} defense"
    return n


def alternative_words(alt: dict, span: str, window: str) -> str:
    """"the Atlanta Falcons defense claim gives +12.8 over weeks 4–7 for an open spot" / "… (drop Tuten) …" /
    "no waiver claim improves your lineup over weeks 4–7"."""
    when = "this week" if window == "week" else f"over {span}"
    if alt.get("kind") == STAND_PAT:
        return f"no waiver claim improves your starting lineup {when}"
    g = alt["gain_week"] if window == "week" else alt["gain_window"]
    how = "for an open spot" if alt.get("open_spot") else (f"(drop {(alt.get('drop') or {}).get('player_name')})"
                                                          if alt.get("drop") else "")
    return f"the {_claim_name(alt)} claim gives {g:+.1f} {when} {how}".strip()


def _stand_pat(weeks, span: str, source: str, note: str | None = None) -> dict:
    return {"kind": STAND_PAT, "player": None, "drop": None, "open_spot": False, "gain_week": 0.0, "gain_window": 0.0,
            "by_week": [0.0 for _ in weeks], "weeks": list(weeks), "span": span, "source": source, "note": note,
            "words": "standing pat: your lineup as it is (0)"}


def _fill_alternative(ctx: TradeContext, board: RosterBoard, weeks: tuple[int, ...], team: int, span: str) -> dict:
    """The best legal waiver move on today's free agents over ``weeks`` (see the block's comment)."""
    from league_lab.lineup import solve
    src = "fa_pool fill"
    try:
        pool, meta = ctx.fa_pool(tuple(weeks))
    except Exception:  # noqa: BLE001 - no free agents to read: standing pat is the only alternative we can name
        return _stand_pat(weeks, span, src, "the free agents could not be read")
    team = int(team)
    open_spots = T.roster_limit(board.slots) - board.active_count(team)
    best = None                      # (window gain, this week's, add, drop, by week)
    if open_spots > 0:
        f = T.best_fill(board, weeks, [board.pool(team, w) for w in weeks], pool)
        if f is not None:
            best = (f.horizon_gain, f.week_gain, f.player_id, None, [T._r2(x) for x in f.week_gains])
    else:
        for d in board.roster(team):
            if not board.is_active(d) or board.is_locked(d, weeks[0]) or not board.has_value(d, weeks):
                continue
            pools = [board.pool_with(team, w, [] if board.is_locked(d, w) else [d]) for w in weeks]
            loss = [board.lineup_value(team, w) - solve(ps, board.slots, margins=False).total for w, ps in zip(weeks, pools, strict=True)]
            f = T.best_fill(board, weeks, pools, pool)
            if f is None:
                continue
            by = [T._r2(g - x) for g, x in zip(f.week_gains, loss, strict=True)]
            key = (T._r2(sum(by)), by[0] if by else 0.0)
            if best is None or key > (best[0], best[1]):
                best = (key[0], key[1], f.player_id, d, by)
    if best is None or best[0] < 0.05:
        return _stand_pat(weeks, span, src)
    gw, g0, add, drop, by = best
    return {"kind": "waiver", "player": _alt_player(ctx, meta, add), "drop": _alt_player(ctx, meta, drop),
            "open_spot": drop is None, "gain_week": T._r2(g0), "gain_window": T._r2(gw), "by_week": by, "weeks": list(weeks),
            "span": span, "source": src, "note": None}


def best_alternative(ctx: TradeContext, board: RosterBoard, weeks: tuple[int, ...], team: int, span: str, window: str, *,
                     source: str | None = None, as_of: datetime | None = None) -> dict:
    """The best alternative to trading over the window: IF-1's best waiver move (next four weeks), else the fill."""
    key = ("if2_alternative", int(team), window)
    if as_of is None and key in ctx.window_cache:
        return ctx.window_cache[key]
    alt = None
    fn = globals().get("best_waiver_move")                   # IF-1 (Wave I-F): net of the drop's cost
    if fn is not None and window == "next4":
        try:
            alt = fn(ctx.league_id, int(team), source=source, as_of=as_of)
        except Exception:  # noqa: BLE001 - IF-1's move is the better number; the fill is the fallback, never a failure
            alt = None
        if alt is not None and list(alt.get("weeks") or []) != list(weeks):
            alt = None                                       # not the same weeks: not comparable
    if alt is None:
        alt = _fill_alternative(ctx, board, weeks, team, span)
    alt = {**alt, "words": alternative_words(alt, span, window)}
    if as_of is None:
        ctx.window_cache[key] = alt
    return alt


def beyond(gain_week: float | None, gain_window: float, alt: dict, window: str) -> float:
    """The trade's starter points beyond the best alternative over the window (this week's for the one-week window)."""
    mine = (gain_week or 0.0) if window == "week" else gain_window
    other = alt["gain_week"] if window == "week" else alt["gain_window"]
    return T._r2(mine - other)


def _other_objective(gain_week: float | None, price_out, price_in, alt: dict, window: str, *,
                     bench: tuple[float | None, float | None] | None = None) -> dict | None:
    """Why a trade that does not beat the waiver move may still be worth a look — from the numbers only, never
    invented: more this week than the claim (a four-week loss hides a this-week gain, or the reverse), more season
    value above replacement coming in, or more backup coverage (the calculator)."""
    if window != "week" and gain_week is not None and gain_week - alt["gain_week"] >= 0.5:
        return {"kind": "this_week", "words": f"It gives more this week: {gain_week:+.1f} against the claim's "
                                              f"{alt['gain_week']:+.1f}."}
    if price_out is not None and price_in is not None and price_in > price_out and not T.about_even(price_out, price_in):
        return {"kind": "season_value", "words": f"It brings in more season value above replacement: {price_in} for "
                                                 f"{price_out} — the season beyond these weeks."}
    if bench is not None and bench[0] is not None and bench[1] is not None and bench[1] - bench[0] >= 2:
        return {"kind": "depth", "words": f"It adds backup coverage: your bench's best lineup {bench[0]:.1f} → "
                                          f"{bench[1]:.1f} this week."}
    return None


def trade_vs_alternative(gain_week: float | None, gain_window: float, alt: dict, span: str, window: str, *,
                         price_out=None, price_in=None, bench=None, spots_used: int = 0) -> dict:
    """{beyond_alternative, beats_alternative, alternative_words, other_objective} for one trade."""
    b = beyond(gain_week, gain_window, alt, window)
    mine = (gain_week or 0.0) if window == "week" else gain_window
    when = "this week" if window == "week" else f"over {span}"
    beats = b >= 0.05
    if alt.get("kind") == STAND_PAT:
        words = f"{mine:+.1f} {when}; {alt['words']}: the trade {'beats' if beats else 'does not beat'} standing pat."
    elif beats:
        words = f"{mine:+.1f} {when}: {b:.1f} more than your best waiver move ({alt['words']})."
    else:
        words = f"{mine:+.1f} {when}; {alt['words']}: the trade does not beat it on starter points."
    other = None if beats else _other_objective(gain_week, price_out, price_in, alt, window, bench=bench)
    if not beats and other is not None:
        words += f" {other['words']}"
    if alt.get("open_spot") and spots_used > 0:
        words += " The trade also takes the open roster spot the claim would use."
    return {"beyond_alternative": b, "beats_alternative": beats, "alternative_words": words, "other_objective": other}


def strip(weeks, mine, theirs) -> dict:
    """The week-by-week starter points gained, both sides (this week · next · …): a four-week win can hide a loss."""
    return {"weeks": [int(w) for w in weeks], "mine": [T._r2(x) for x in mine], "theirs": [T._r2(x) for x in theirs]}


def rank_partners(ctx: TradeContext, board: RosterBoard, weeks: tuple[int, ...], rows: list[dict], alt: dict, span: str,
                  window: str) -> list[dict]:
    """Each row gains IF-2's fields; the rows are ordered by the gain beyond the alternative (the trades that beat it
    first), the bigger package never above its cheaper equal (IE-1); `rank` 1 is the headline."""
    for r in rows:
        r.update(trade_vs_alternative(r["you_gain_week"], r["you_gain_horizon"], alt, span, window, price_out=r.get("price_out"),
                                      price_in=r.get("price_in"), spots_used=len(r["get"]) - len(r["give"])))
        try:
            m, t = T.package_weeks(board, [x["sleeper_id"] for x in r["give"]], [x["sleeper_id"] for x in r["get"]], weeks)
        except ValueError:
            m, t = (), ()
        r["strip"] = strip(weeks, m, t)
    lead = {r["partner"]: r["beyond_alternative"] for r in rows if r.get("cheaper_than")}

    def key(ir):
        i, r = ir
        b = r["beyond_alternative"]
        if r.get("optional") and r["partner"] in lead:
            b = min(b, lead[r["partner"]] - 0.001)       # the extra asset never ranks its package above the cheaper one
        return (not r["beats_alternative"], -b, i)
    out = [r for _, r in sorted(enumerate(rows), key=key)]
    for i, r in enumerate(out, 1):
        r["rank"] = i
        r["demoted"] = not r["beats_alternative"]
    return out


def calc_sanity(give: list[str], get: list[str], prices: dict, ours: dict, mkt: dict, name) -> str | None:
    """The calculator's warning: the market rule (b) as before; the value rule on SEASON VALUE ABOVE REPLACEMENT (the
    fairness test), never on the raw rest-of-season totals — given more than ``T.ROS_GAP_SHARE`` over what comes back,
    every player of the package priced (unknown is not zero: not judged)."""
    why = T.sanity(give, get, ros={}, ours=ours, market=mkt, name=name)
    if why or not give or not get or not all(p in prices for p in (*give, *get)):
        return why
    po, pi = T.season_value(prices, give)[0] or 0, T.season_value(prices, get)[0] or 0
    if po > 0 and po - pi > T.ROS_GAP_SHARE * po:
        return (f"you give {po} season value above replacement for {pi}: {po - pi} more, over "
                f"{round(T.ROS_GAP_SHARE * 100)}% of what you give")
    return None


def calc_alternatives(ctx: TradeContext, out: dict, now: T.Trade, trade: T.Trade, board: RosterBoard, weeks, window: str,
                      package: tuple[list[str], list[str]], inputs: tuple[dict, dict, dict], *, source=None, as_of=None) -> None:
    """The calculator's IF-2 fields: the alternative and the gain beyond it, the week strip for both sides, the value
    concepts named and kept apart (`values`), the raw rest-of-season line labelled, the warning on season value."""
    g, t = package
    _, ours, mkt = inputs
    me, th = trade.mine, trade.theirs
    span = out["span"]
    alt = best_alternative(ctx, board, tuple(weeks), int(out["roster_id"]), span, window, source=source, as_of=as_of)
    starts_now = tuple(weeks)[0] == ctx.this_week
    out["alternative"] = alt
    out.update(trade_vs_alternative(now.mine.gain_week if starts_now else None, me.gain_horizon, alt, span, window,
                                    price_out=me.price_out, price_in=me.price_in, spots_used=len(t) - len(g),
                                    bench=(now.mine.bench_before, now.mine.bench_after)))
    out["strip"] = strip(trade.weeks, [a - b for a, b in zip(me.after, me.before, strict=True)],
                         [a - b for a, b in zip(th.after, th.before, strict=True)])
    unknown = [*me.unknown_out, *me.unknown_in]
    ros = out.get("ros") or {}
    ros_words = None
    if ros.get("give") is not None and ros.get("get") is not None:
        ros_words = (f"{VALUE_CONCEPTS['ros_points']} ({ros.get('window') or 'rest of season'}), {T.ROS_NOT_FAIRNESS}: "
                     f"you give {ros['give']}, you get {ros['get']}.")
        out["ros"] = {**ros, "words": ros_words, "label": VALUE_CONCEPTS["ros_points"], "fairness": False}
    out["values"] = {
        "projected_points": {"label": VALUE_CONCEPTS["projected_points"],
                             "words": "One player's forecast for one week, in this league's scoring (the lineup tables)."},
        "starter_points": {"label": VALUE_CONCEPTS["starter_points"], "mine": me.gain_horizon, "theirs": th.gain_horizon,
                           "this_week": {"mine": now.mine.gain_week, "theirs": now.theirs.gain_week},
                           "words": out.get("effect_words")},
        "depth": {"label": VALUE_CONCEPTS["depth"],
                  "mine": {"before": now.mine.bench_before, "after": now.mine.bench_after},
                  "theirs": {"before": now.theirs.bench_before, "after": now.theirs.bench_after},
                  "words": out.get("backup_words")},
        "season_value": {"label": VALUE_CONCEPTS["season_value"], "give": me.price_out, "get": me.price_in,
                         "unknown": [ctx.name(p) for p in unknown], "fairness": True,
                         "words": T.season_value_line(me.price_out, me.price_in, len(g), len(t), unknown, ctx.name)},
        "ros_points": {"label": VALUE_CONCEPTS["ros_points"], "give": ros.get("give"), "get": ros.get("get"),
                       "window": ros.get("window"), "fairness": False, "words": ros_words},
    }
    out["sanity"] = calc_sanity(g, t, ctx.prices, ours, mkt, ctx.name)
    if isinstance(out.get("how"), dict):
        out["how"]["ros"] = ros_words
        out["how"]["season_value"] = out["values"]["season_value"]["words"]


def ordering_words(alt: dict, span: str, window: str) -> str:
    when = "this week" if window == "week" else f"over {span}"
    if alt.get("kind") == STAND_PAT:
        return f"Ranked by what each trade adds to your starting lineup {when}: no waiver claim improves it."
    return (f"Ranked by gain beyond your best waiver move {when} ({_claim_name(alt)}, {alt['gain_week' if window == 'week' else 'gain_window']:+.1f}); "
            "trades that do not beat it come last.")
# ---- end IF-2


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


# ---- IE-2 (Wave I-E): the trade explained through the starting lineup (review § "explain trades through starting-
# lineup changes"). The answer leads with who enters your starters and who leaves — by MEMBERSHIP: a starter who only
# slides from WR/TE 2 to WR/TE 3 is in neither list and shows no change of his own —, the required cut, the backup
# coverage the trade takes, the other side in the same words, the window named, and the comparison with standing pat
# and with the best free agent for the same need. Every number here is one the evaluation already made (the lineups'
# totals, the sides' gains, `trades.best_fill` on today's roster); nothing is re-priced. The arithmetic (the market,
# rest of season, ranks, roster size) moves under "How we calculated this" on the page; `how` lists it.
DICTIONARY = (("**Fit** (what the best lineups gain)", "**Improvement to your starting lineup** (best lineup each week)"),
              ("**Market** (season points above the best free agent at the position)",
               "**Projected value above available replacements** (season points above the best free agent at the position)"))


def dictionary_words(text: str | None) -> str | None:
    """The review's metric dictionary on a sentence the shared trade functions wrote (docs/WORDS.md § "The
    dictionary"): the label changes, the numbers stay."""
    if not text:
        return text
    for old, new in DICTIONARY:
        text = text.replace(old, new)
    return text


def _who(ctx: TradeContext, pid) -> str:
    """'Rice'; a team unit by its short name ('Texans QB'); a defense keeps its name."""
    n = ctx.name(pid)
    return unit_short(n) if ctx.pos(pid) in ("TMQB", "TMPK", "TMDEF") or n.endswith((" QB", " K")) else _last(n)


def _and(parts: list[str]) -> str:
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


def _membership(ctx: TradeContext, side: T.Side) -> dict:
    """This week's starters in / out by membership, and the slot moves (detail only, no points)."""
    if side.lineup_before is None or side.lineup_after is None:
        return {"in": [], "out": [], "moved": []}
    before = {s.player.id: s for s in side.lineup_before.starts if s.player is not None}
    after = {s.player.id: s for s in side.lineup_after.starts if s.player is not None}
    cut = {c.player_id for c in side.cuts}
    ins = [{"player": ctx.player(p), "slot": cards.slot_label(s.slot.type), "value": T._r2(s.value or 0.0),
            "how": "trade" if p in side.gets else "bench"} for p, s in after.items() if p not in before]
    outs = [{"player": ctx.player(p), "slot": cards.slot_label(s.slot.type), "value": T._r2(s.value or 0.0),
             "why": "traded" if p in side.gives else "cut" if p in cut else "to the bench"}
            for p, s in before.items() if p not in after]
    moved = [f"{_who(ctx, p)} {cards.slot_label(before[p].slot.label)} → {cards.slot_label(s.slot.label)}"
             for p, s in after.items() if p in before and before[p].slot.label != s.slot.label]
    return {"in": ins, "out": outs, "moved": moved}


def _lineup_words(ctx: TradeContext, m: dict, partner_team: str) -> str:
    ins = [f"{_who(ctx, x['player']['sleeper_id'])} starts at {x['slot']}" for x in m["in"]]
    why = {"traded": f"goes to {partner_team}", "cut": "is cut", "to the bench": "to the bench"}
    outs = [f"{_who(ctx, x['player']['sleeper_id'])} {why[x['why']]}" for x in m["out"]]
    if not ins and not outs:
        return "The same players start this week."
    return "; ".join(p for p in (_and(ins) if ins else "", _and(outs) if outs else "") if p) + "."


def _more(x: float | None, when: str, *, whole: bool = False) -> str:
    """'about 3.4 more points this week' / 'about 10 fewer in total over weeks 4–7' / 'no change this week'."""
    if x is None:
        return f"not known {when}"
    if abs(x) < 0.05:
        return f"no change {when}"
    n = f"{abs(x):.0f}" if whole and abs(x) >= 0.5 else f"{abs(x):.1f}"
    return f"about {n} {'more' if x > 0 else 'fewer'} {'points ' if not whole else ''}{when}".replace("  ", " ")


def _effect(whose: str, week_gain: float, window_gain: float, window: str, span: str) -> str:
    if window == "week":
        return f"{whose} starting lineup: {_more(week_gain, 'this week')}."
    return (f"{whose} starting lineup: {_more(week_gain, 'this week')}, "
            f"{_more(window_gain, f'in total over {span}', whole=True)}.")


def _backup(ctx: TradeContext, side: T.Side) -> str | None:
    """The backup coverage the trade takes (players who sat on your bench this week and leave the roster) or adds."""
    if side.lineup_before is None or side.lineup_after is None:
        return None
    gone = set(side.gives) | {c.player_id for c in side.cuts}
    before_bench = [p for p in side.lineup_before.bench]
    after_bench = [p for p in side.lineup_after.bench]
    lost = [p for p in before_bench if p.id in gone]
    added = [p for p in after_bench if p.id in set(side.gets)]
    bits = []
    for p in lost:
        left = [q for q in after_bench if q.position == p.position]
        rest = (f"{len(left)} {p.position} left on your bench" if left else f"no {p.position} left on your bench")
        bits.append(f"you lose {_who(ctx, p.id)}, a backup {p.position} ({rest})")
    for p in added:
        bits.append(f"{_who(ctx, p.id)} joins your bench as a backup {p.position}")
    return ("Backup coverage: " + "; ".join(bits) + ".") if bits else None


def _hold(ctx: TradeContext, board: RosterBoard, weeks: tuple[int, ...], team: int, need: list[str], my_gain: float,
          window: str, span: str, now_total: float) -> dict:
    """Standing pat, and the best free agent at the positions the trade brings in (`trades.best_fill` on today's
    roster: what he adds to your best lineup each week; a claim also needs a roster spot)."""
    when = "this week" if window == "week" else f"in total over {span}"
    out = {"hold": f"Standing pat keeps your starting lineup at {now_total:.1f} projected points "
                   f"this week.", "waiver": None, "waiver_gain": None}
    try:
        pool, meta = ctx.fa_pool(weeks)
    except Exception:  # noqa: BLE001 - the comparison is a side line, never the evaluation's failure
        return out
    pool = {k: v for k, v in pool.items() if not need or (meta.get(k, {}).get("position") in need)}
    if not pool:
        return out
    fill = T.best_fill(board, weeks, [board.pool(team, w) for w in weeks], pool)
    if fill is None:
        out["waiver"] = f"No free agent at {_and(sorted(need))} improves your starting lineup {when}."
        out["waiver_gain"] = 0.0
        return out
    g = fill.horizon_gain if window != "week" else fill.week_gain
    name = (meta.get(fill.player_id) or {}).get("player_name") or str(fill.player_id)
    cmp = ("about as much as this trade" if abs(g - my_gain) < 0.5 else
           "more than this trade, without giving anyone up" if g > my_gain else "less than this trade")
    n = f"{g:.1f}" if window == "week" or g < 0.5 else f"{g:.0f}"
    out["waiver"] = (f"The best free agent for the same need, {name} ({(meta.get(fill.player_id) or {}).get('position')}), "
                     f"adds about {n} points to your starting lineup {when}: {cmp} (a claim also needs a roster spot).")
    out["waiver_gain"] = T._r2(g)
    out["waiver_player"] = {"sleeper_id": fill.player_id, **(meta.get(fill.player_id) or {})}
    return out


def trade_story(ctx: TradeContext, out: dict, now: T.Trade, trade: T.Trade, board: RosterBoard, weeks: tuple[int, ...],
                window: str) -> dict:
    """The answer's IE-2 fields (INTERFACES.md § IE-2) and the lineups' per-player change."""
    span, partner_team = out["span"], out["partner_team"]
    mine, theirs = _membership(ctx, now.mine), _membership(ctx, now.theirs)
    # the lineups: each row's change is the PLAYER's own (new starter: his value; a starter who changed slot: none);
    # the starters who left are their own rows; the changes add up to the lineup total's change
    for who, side, m in (("mine", now.mine, mine), ("theirs", now.theirs, theirs)):
        lu = out["lineups"].get(who)
        if lu is None or side.lineup_before is None or side.lineup_after is None:
            continue
        before = {s.player.id for s in side.lineup_before.starts if s.player is not None}
        for row, s in zip(lu["slots"], side.lineup_after.starts, strict=False):
            pid = s.player.id if s.player is not None else None
            row["change"] = None if pid is None or pid in before else T._r2(s.value or 0.0)
            row["status"] = "new" if pid is not None and pid in side.gets else "in" if pid is not None and pid not in before else None
        lu["out"] = [{"slot": x["slot"], "player_name": x["player"]["player_name"], "gsis_id": x["player"]["gsis_id"],
                      "value": x["value"], "change": -x["value"], "why": x["why"]} for x in m["out"]]
        lu["reshuffled"] = m["moved"]
        lu["total"] = {"before": T._r2(side.lineup_before.total), "after": T._r2(side.lineup_after.total),
                       "change": T._r2(side.lineup_after.total - side.lineup_before.total)}
    me, th = trade.mine, trade.theirs
    need = sorted({x["player"]["position"] for x in mine["in"] if x["how"] == "trade"} or {ctx.pos(p) for p in me.gets})
    hold = _hold(ctx, board, tuple(weeks), int(out["roster_id"]), [p for p in need if p], me.gain_horizon if window != "week"
                 else now.mine.gain_week, window, span, now.mine.before[0])
    cuts = [{"player": ctx.player(c.player_id), "season_points": None if c.market is None else T.whole(c.market),
             "words": f"You must cut {ctx.name(c.player_id)} to make room"
                      + (f" (he costs your lineup {c.horizon_loss:.1f} over {span})." if c.horizon_loss >= 0.05 else
                         " (he does not start for you: no lineup points lost).")} for c in me.cuts]
    effect = _effect("Your", now.mine.gain_week, me.gain_horizon, window, span)
    their_effect = _effect(f"{partner_team}'s", now.theirs.gain_week, th.gain_horizon, window, span)
    out["fit"]["words"] = dictionary_words(out["fit"]["words"])
    out["market"]["words"] = dictionary_words(out["market"]["words"])
    return {
        "starters_in": mine["in"], "starters_out": mine["out"], "cut": cuts,
        "effect_words": effect, "lineup_words": _lineup_words(ctx, mine, partner_team), "backup_words": _backup(ctx, now.mine),
        "their_change": {"gain_week": now.theirs.gain_week, "gain_window": th.gain_horizon, "starters_in": theirs["in"],
                         "starters_out": theirs["out"], "effect_words": their_effect,
                         "lineup_words": _lineup_words(ctx, theirs, "you")},
        "window_words": "this week" if window == "week" else f"over {span} in total",
        "hold_words": " ".join(x for x in (hold["hold"], hold["waiver"]) if x),
        "hold": hold,
        "how": {"fit": out["fit"]["words"], "market": out["market"]["words"], "ros": (out.get("ros") or {}).get("words"),
                "size": out["size_words"], "ranks": (out.get("ranks") or {}).get("words")},
    }
# ---- end IE-2


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
    _ie1_cheaper(ctx, board, weeks, found, rows, starts_now, span)                     # ---- IE-1: least costly first
    # ---- IF-2: the ladder (standing pat, the best waiver move, the trades), the rows ranked by the gain beyond it; the
    # headline is the first card, always
    alt = best_alternative(ctx, board, tuple(weeks), int(team), span, window, source=source, as_of=as_of)
    rows = rank_partners(ctx, board, tuple(weeks), rows, alt, span, window)
    head = None
    if rows:
        r0 = rows[0]
        give0, get0 = [x["sleeper_id"] for x in r0["give"]], [x["sleeper_id"] for x in r0["get"]]
        m = ctx.names.get(r0["partner"], {}).get("manager_name")
        who = f"{ctx.team(r0['partner'])} ({m})" if m else ctx.team(r0["partner"])
        # quoted from app/pages/6_Trade_Finder.py (the first card); a window that starts later has no "this week"
        if starts_now and len(weeks) > 1:
            head = (f"**Best partner: {who}.** Your {_names(ctx, give0)} for their {_names(ctx, get0)}: you "
                    f"**{r0['you_gain_week']:+.1f}** this week and **{r0['you_gain_horizon']:+.1f}** over {span}, them "
                    f"**{r0['they_gain_week']:+.1f}** and **{r0['they_gain_horizon']:+.1f}**.")
        else:
            head = (f"**Best partner: {who}.** Your {_names(ctx, give0)} for their {_names(ctx, get0)}: you "
                    f"**{r0['you_gain_horizon']:+.1f}** over {span}, them **{r0['they_gain_horizon']:+.1f}**.")
    # ---- end IF-2
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
            "words": {"headline": links(head), "source": "quoted from app/pages/6_Trade_Finder.py (the best-partner card)",
                      "alternative": rows[0]["alternative_words"] if rows else None},                       # ---- IF-2
            "best_alternative": alt, "alternatives": [_stand_pat(weeks, span, "stand pat"), alt] if alt["kind"] != STAND_PAT
            else [alt], "ordering": {"key": "beyond_alternative", "words": ordering_words(alt, span, window)},  # IF-2
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
    # ---- IB-0: one availability truth - this week's lineup value, the weakest starter, the slot strengths and the
    # roster are the roster context's (the overlay); the league's ranks are re-run on every roster the overlay moved
    ctxs = _team_contexts(league_id, int(team_id), is_house, None if is_house else hf)
    moved = {rid: c for rid, c in ctxs.items() if c is not None and c.changed}
    if moved and not value.empty:
        value, rankings, slots, rows = _team_on_context(int(team_id), moved, value, rankings, slots, rows)
    # ---- end IB-0
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
    if not is_house:
        units_named(out)                                                          # ---- IC-4
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
    if moved:                                                                         # ---- IB-0
        _weekly_on_context(out, moved, allw, int(team_id))
    if ctxs.get(int(team_id)) is not None:
        out["roster_context"] = ctxs[int(team_id)].summary()
    out["words"] = team_words(out, rows)
    out["timings_ms"] = {"data": round((t1 - t0) * 1000, 1), "total": round((time.perf_counter() - t0) * 1000, 1)}
    return out


# ---- IB-0 (Wave I-B): the Team Hub on the roster contexts. The marts (and the on-demand solve) carry the build's
# lineups; the overlay can move this week's. Mine is always read; another roster only when the overlay says one of its
# players cannot play (availability.touched): its lineup value and bench value move, so the league's ranks do too.
HORIZON_THIS_WEEK_SQL = """select roster_id, gsis_id from analytics.mart_league_roster_horizon
                           where league_id = %s and is_this_week and gsis_id is not null and role in ('starter', 'bench')"""


def _team_contexts(league_id: str, team_id: int, is_house: bool, hf: pd.DataFrame | None) -> dict:
    if not availability.enabled():
        return {}                                   # the build's lineups are the truth: the marts / the solve as they are
    try:
        if is_house:
            ids = query(HORIZON_THIS_WEEK_SQL, (league_id,))
        else:
            ids = (hf[hf["is_this_week"] & hf["gsis_id"].notna() & hf["role"].isin(["starter", "bench"])][["roster_id", "gsis_id"]]
                   if hf is not None else pd.DataFrame())
        by_roster = ({int(r): list(g) for r, g in ids.groupby("roster_id")["gsis_id"]} if not ids.empty else {})
        return availability.contexts(league_id, availability.touched(by_roster) | {int(team_id)}, house=is_house)
    except (A.SleeperBusy, A.SleeperUnavailable, A.LeagueNotFound):
        return {}


def _team_rows(ctx, old: pd.DataFrame) -> pd.DataFrame:
    """The roster's this-week rows (TEAM_ROWS_SQL's columns) from its context; how each player joined, from the old."""
    acq = {}
    if old is not None and not old.empty and "acquired_label" in old:
        acq = {str(r["sleeper_player_id"]): (r.get("acquired_label"), r.get("acquired_how_by_manager")) for _, r in old.iterrows()}
    out = []
    for _, r in ctx.rows.iterrows():
        empty = bool(r["is_empty_slot"])
        sid = r["sleeper_player_id"] if isinstance(r["sleeper_player_id"], str) else None
        a = acq.get(str(sid), (None, None))
        out.append({"week": ctx.week, "role": "empty" if empty else r["role"], "slot": r["slot"], "slot_type": r["slot_type"],
                    "slot_order": r["slot_order"], "bench_rank": r["bench_rank"], "sleeper_player_id": sid,
                    "gsis_id": r["gsis_id"], "player_name": r["player_name"], "position": r["position"],
                    "player_value": r["value"], "value_source": r["value_source"], "lineup_margin": r["margin"],
                    "is_locked": bool(r.get("locked_now")), "report_status": r["report_status"], "reason": r["reason"],
                    "acquired_label": a[0], "acquired_how_by_manager": a[1]})
    df = pd.DataFrame(out)
    for c in ("player_value", "lineup_margin", "slot_order", "bench_rank"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def _slot_strength(ctx, team_id: int) -> list[dict]:
    """mart_league_roster_slot_strength's rows for one roster from its context (the best-valued starter of each slot
    type, his margin, the bench player worth value - margin)."""
    st = ctx.rows[ctx.rows["role"] == "starter"]
    out = []
    for stype, g in st.groupby("slot_type"):
        filled = g[~g["is_empty_slot"].astype(bool)].assign(_v=lambda x: pd.to_numeric(x["value"], errors="coerce").fillna(-1e18))
        t = filled.sort_values(["_v", "slot_order"], ascending=[False, True]).iloc[0] if not filled.empty else None
        rep = ctx.replacement(t) if t is not None else None
        out.append({"roster_id": team_id, "slot_type": stype, "slots": len(g), "empty_slots": int(g["is_empty_slot"].astype(bool).sum()),
                    "first_slot_order": int(g["slot_order"].min()), "top_slot": None if t is None else t["slot"],
                    "top_gsis_id": None if t is None else t["gsis_id"], "top_player_name": None if t is None else t["player_name"],
                    "top_position": None if t is None else t["position"], "top_value": None if t is None else _num(t["value"]),
                    "top_is_locked": None if t is None else bool(t.get("locked_now")),
                    "starter_strength": None if t is None else _num(t["margin"]),
                    "replacement_name": None if rep is None else rep["player_name"],
                    "replacement_value": None if rep is None else _num(rep["value"])})
    return out


def _team_on_context(team_id: int, moved: dict, value: pd.DataFrame, rankings: pd.DataFrame, slots: pd.DataFrame,
                     rows: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    value = value.copy()
    for rid, c in moved.items():
        m = value["roster_id"] == rid
        if not m.any() or c.lineup_value is None:
            continue
        old = _num(value.loc[m, "lineup_value"].iloc[0]) or 0.0
        value.loc[m, "horizon_value"] = round((_num(value.loc[m, "horizon_value"].iloc[0]) or 0.0) - old + c.lineup_value, 2)
        value.loc[m, "lineup_value"] = c.lineup_value
        value.loc[m, "bench_value"] = c.bench_value
        if rid == team_id:
            w = context_weakest(c)
            value.loc[m, "weakest_slot"] = c.weakest_slot
            value.loc[m, "weakest_margin"] = c.weakest_margin
            for k, v in (("weakest_player_name", None if w is None else w["player"]["player_name"]),
                         ("weakest_gsis_id", None if w is None else w["player"]["gsis_id"]),
                         ("weakest_position", None if w is None else w["player"]["position"]),
                         ("weakest_value", None if w is None else w["value"]),
                         ("weakest_replacement_name", None if w is None else w["replacement_name"]),
                         ("weakest_replacement_value", None if w is None else w["replacement_value"])):
                value[k] = value[k].astype(object)
                value.loc[m, k] = v
    if not rankings.empty:
        rankings = rankings.copy()
        for measure in ("lineup_value", "horizon_value", "bench_value"):
            vv = {int(r): float(v) for r, v in zip(value["roster_id"], value[measure], strict=True) if _num(v) is not None}
            ranks = _rank(vv)
            m = rankings["measure"] == measure
            for i in rankings.index[m]:
                rid = int(rankings.at[i, "roster_id"])
                if rid in vv:
                    rankings.at[i, "value"], rankings.at[i, "league_rank"] = vv[rid], ranks[rid]
                    rankings.at[i, "n_rosters"] = len(vv)
                    rankings.at[i, "rank_label"] = f"{ranks[rid]}/{len(vv)}"
    if team_id in moved:
        c = moved[team_id]
        rows = _team_rows(c, rows)
        new = pd.DataFrame(_slot_strength(c, team_id))
        slots = pd.concat([slots[slots["roster_id"] != team_id], new], ignore_index=True) if not slots.empty else new
        slots = slots.sort_values(["roster_id", "first_slot_order"])
    return value, rankings, slots, rows


def _weekly_on_context(out: dict, moved: dict, allw: pd.DataFrame, team_id: int) -> None:
    """This week's entry of the weekly list (and the league behind it) from the contexts; the toughest week after."""
    allw = allw.copy() if allw is not None else pd.DataFrame()
    for rid, c in moved.items():
        if not allw.empty and c.lineup_value is not None:
            allw.loc[(allw["week"] == c.week) & (allw["roster_id"] == rid), "lineup_value"] = c.lineup_value
    me = moved.get(team_id)
    for w in out.get("weekly") or []:
        if me is not None and int(w["week"]) == me.week:
            w["lineup_value"], w["bench_value"] = me.lineup_value, me.bench_value
        w["league"] = _week_league(allw, int(w["week"]), w["lineup_value"])
    v = out.get("value") or {}
    lvs = [(int(w["week"]), w["lineup_value"]) for w in out.get("weekly") or [] if w["lineup_value"] is not None]
    if me is not None and lvs and v:
        worst = min(lvs, key=lambda x: (x[1], x[0]))
        v["worst_week"], v["worst_week_value"] = worst[0], worst[1]
# ---- end IB-0


# ---- IC-4 (Wave I-D): a team unit is named with its team. The roster rows and the slot strength's best starter carry
# the unit's team (the directory's Sleeper code: the badge), `unit: true` and the short name "Bengals QB".
UNIT_POSITIONS = ("TMQB", "TMPK")


def unit_short(name: str | None) -> str | None:
    """"Cincinnati Bengals QB" -> "Bengals QB" (the nickname + the unit word)."""
    parts = str(name or "").split()
    return " ".join(parts[-2:]) if len(parts) >= 2 else (name or None)


def units_named(out: dict) -> dict:
    try:
        d = A.sleeper().players()
    except Exception:  # noqa: BLE001 - no directory: the rows keep their names
        return out
    by_name: dict[str, tuple[str, dict]] = {}
    for r in out.get("roster") or []:
        if r.get("position") in UNIT_POSITIONS and r.get("sleeper_id"):
            row = d.get(str(r["sleeper_id"])) or {}
            r["team"] = r.get("team") or row.get("team")
            r["unit"], r["short_name"] = True, unit_short(r.get("player_name"))
            by_name[str(r.get("player_name"))] = (str(r["sleeper_id"]), r)
    for s in out.get("slot_strength") or []:
        top = s.get("top")
        if top and top.get("position") in UNIT_POSITIONS:
            sid, r = by_name.get(str(top.get("player_name")), (None, {}))
            top.update({"sleeper_id": top.get("sleeper_id") or sid, "team": top.get("team") or r.get("team"), "unit": True,
                        "short_name": unit_short(top.get("player_name"))})
        if s.get("replacement_name") and s.get("slot_type") in UNIT_POSITIONS:
            s["replacement_short"] = unit_short(s["replacement_name"])
    return out
# ---- end IC-4


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
            fm.append({"week": int(w), "roster_id": int(m["roster_id"]), "points": pts, "opponent_points": op, "result": res,
                       "opponent_roster_id": None if opp is None else int(opp["roster_id"])})          # ---- IC-4
    f = pd.DataFrame(fm, columns=["week", "roster_id", "points", "opponent_points", "result", "opponent_roster_id"])
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
        pts = g.drop_duplicates("roster_id").set_index("roster_id")["points"]   # IC-4: a double header scores once
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
    apw = double_header_weeks(apw, f, names)                                      # ---- IC-4
    ap = []
    for rid, g in apw.groupby("roster_id"):
        tot = int(g["all_play_wins"].sum() + g["all_play_losses"].sum() + g["all_play_ties"].sum())
        fg = f[f["roster_id"] == rid]                         # IC-4: the games (two in a double-header week)
        wins = int((fg["result"] == "W").sum())
        pct = g["all_play_wins"].sum() / tot if tot else None
        games = len(fg)
        ap.append({"roster_id": int(rid), "team_name": names.get(int(rid), {}).get("team_name"),
                   "manager_name": names.get(int(rid), {}).get("manager_name"), "games": games, "wins": wins,
                   "losses": int((fg["result"] == "L").sum()), "all_play_wins": int(g["all_play_wins"].sum()),
                   "all_play_losses": int(g["all_play_losses"].sum()), "all_play_ties": int(g["all_play_ties"].sum()),
                   "all_play_win_pct": None if pct is None else round(float(pct), 4),
                   "expected_wins": None if pct is None else round(games * float(pct), 2),
                   "luck_wins": None if pct is None else round(wins - games * float(pct), 2),
                   "top_half_weeks": int((g["week_points_rank"] <= g["rosters_in_week"] / 2.0).sum()),
                   "avg_points_rank": round(float(g["week_points_rank"].mean()), 2)})
    all_play = pd.DataFrame(ap)
    all_play["all_play_rank"] = all_play["all_play_wins"].rank(method="min", ascending=False).astype(int)
    all_play = all_play.sort_values(["all_play_rank", "roster_id"]).reset_index(drop=True)
    return standings, all_play, apw.drop(columns=["all_play_ties", "rosters_in_week"])


# ---- IC-4 (Wave I-D): double headers (MFL 70587 plays twice in weeks 2, 4, 6-9, 11 and 13). A team's week is one
# score (all-play counts it once) and one or two games: `games` on its all-play row, its record from every game; the
# League screen lists the matchups of this week and of the last scored week, each game once (both of a double header).
def double_header_weeks(apw: pd.DataFrame, f: pd.DataFrame, names: dict) -> pd.DataFrame:
    """Each (week, roster) all-play row gets `games` (opponent, scores, result per game) and, in a double-header week,
    `result` "W/L"-style and `opponent_points` = the first game's."""
    if apw.empty:
        return apw
    by = {(int(w), int(r)): g for (w, r), g in f.groupby(["week", "roster_id"])}
    games, res, opp = [], [], []
    for w, r in zip(apw["week"], apw["roster_id"], strict=True):
        g = by.get((int(w), int(r)))
        rows = [] if g is None else [{"opponent_roster_id": None if pd.isna(x.opponent_roster_id) else int(x.opponent_roster_id),
                                      "opponent_team_name": names.get(int(x.opponent_roster_id), {}).get("team_name")
                                      if not pd.isna(x.opponent_roster_id) else None,
                                      "points": x.points, "opponent_points": x.opponent_points, "result": x.result}
                                     for x in g.itertuples()]
        games.append(rows)
        res.append("/".join(str(x["result"]) for x in rows if x["result"]) or None)
        opp.append(rows[0]["opponent_points"] if rows else None)
    return apw.assign(games=games, result=res, opponent_points=opp)


def week_matchups(week: int | None, ms: list[dict], names: dict, *, played: bool, me: int | None = None) -> dict | None:
    """One week's games, each once: [{a, b}] with each side's roster_id, team_name, points (None before the games),
    result; `double_header` when a team plays twice; `mine` = my games."""
    if week is None or not ms:
        return None
    by: dict = {}
    for m in ms:
        if m.get("matchup_id") is not None:
            by.setdefault(m["matchup_id"], []).append(m)
    games = []
    for mid, g in by.items():
        if len(g) != 2:
            continue
        sides = []
        for x, o in ((g[0], g[1]), (g[1], g[0])):
            p, q = float(x.get("points") or 0.0), float(o.get("points") or 0.0)
            sides.append({"roster_id": int(x["roster_id"]), "team_name": names.get(int(x["roster_id"]), {}).get("team_name"),
                          "points": round(p, 2) if played else None,
                          "result": ("W" if p > q else "L" if p < q else "T") if played else None})
        games.append({"matchup_id": mid, "a": sides[0], "b": sides[1],
                      "mine": me is not None and me in (sides[0]["roster_id"], sides[1]["roster_id"])})
    games.sort(key=lambda x: (not x["mine"], x["matchup_id"]))
    count: dict[int, int] = {}
    for x in games:
        for sd in (x["a"], x["b"]):
            count[sd["roster_id"]] = count.get(sd["roster_id"], 0) + 1
    return {"week": int(week), "played": played, "double_header": any(v > 1 for v in count.values()), "games": games}
# ---- end IC-4


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
        # ---- IC-4: this week's games and the last scored week's (each game once; both games of a double header)
        try:
            this = _od(A.sleeper().matchups, lg["league_id"], int(cur)) if cur else []
        except Exception:  # noqa: BLE001 - the matchups are a nicety on this screen
            this = []
        out["matchups"] = [m for m in (week_matchups(cur, this, names, played=False, me=team) if cur and cur != last else None,
                                       week_matchups(last, weeks.get(last) or [], names, played=True, me=team) if last else None)
                           if m is not None]
        # ---- end IC-4
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

from league_lab.scoring import price_projected as _price_projected  # noqa: E402 - M3 (Wave I-D)

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
        # ---- M3 (Wave I-D): a projected what-if prices like every projected line (``scoring.price_projected``: the flat
        # engine, or expected bonuses under LEAGUE_LAB_EV_PRICING; an MFL spec in expectation) — flag off, the same
        # number ``compute_points`` gave, to the bit
        num = None if line is None else {c: float(x or 0) for c, x in line.items() if x is None or isinstance(x, (int, float))}
        lines[k] = None if num is None else round(float(_price_projected(pd.DataFrame([num]), scoring, r.get("position"))[0]), 2)
        # ---- /M3
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


# ---- IB-2 (Wave I-B): Waivers short — the three strongest moves with one reason each, the views (Help now · Bye
# coverage · Stashes · All available), the best waiver alternative before a drop of a player who starts.
# One answer carries every view (the screen switches chips without asking again: instant on a phone, one cached answer
# per position, the on-demand league solved once); `top3` and the views read the full move table (every add × drop),
# so the alternative "keep him, drop someone who sits" is found among the moves the sweep already priced.
VIEWS = ("help", "bye", "stash", "all")
VIEW_LABELS = {"help": "Help now", "bye": "Bye coverage", "stash": "Stashes", "all": "All available"}
VIEW_CAP = 8                                      # moves a view lists (the rest are in All available's free agents)
GAIN_EPS = 0.05                                   # a gain under this is "+0.0": no gain (decisions.ts s1)


NICKNAMES = frozenset("Cardinals Falcons Ravens Bills Panthers Bears Bengals Browns Cowboys Broncos Lions Packers Texans Colts "
                      "Jaguars Chiefs Raiders Chargers Rams Dolphins Vikings Patriots Saints Giants Jets Eagles Steelers "
                      "49ers Seahawks Buccaneers Titans Commanders".split())


def _last(name: str | None) -> str:
    """'Croskey-Merritt' from 'Jacory Croskey-Merritt'; a team defense keeps its name ('Kansas City Chiefs')."""
    n = (name or "").strip()
    if not n or len(n.split()) < 2 or n.split()[-1] in NICKNAMES:
        return n
    parts = n.split()
    return " ".join(parts[1:]) if parts[-1] in ("Jr.", "Sr.", "II", "III", "IV") and len(parts) > 2 else parts[-1]


def _name_list(ns: list[str], k: int = 2) -> str:
    ns = [_last(n) for n in ns if n]
    if len(ns) <= k:
        return " and ".join(ns) if len(ns) <= 2 else ", ".join(ns[:-1]) + " and " + ns[-1]
    return ", ".join(ns[:k]) + f" and {len(ns) - k} more"


def _span_words(week: int, last: int) -> str:
    return f"weeks {week}–{last}" if last > week else f"week {week}"


def _horizon_rows(league_id: str, team: int, is_house: bool, od_info: dict) -> pd.DataFrame:
    """The roster's solved lineup for this week and the next three (mart_league_roster_horizon; on demand the same
    rows from the league solve): who starts, who is on a bye, which slot is left empty."""
    if is_house:
        return query(HORIZON_SQL + " and roster_id = %s", (league_id, int(team)))
    lw = od_info.get("lw")
    if lw is None:
        return pd.DataFrame(columns=["week", "role", "slot", "sleeper_player_id", "player_name", "reason"])
    hf = A.horizon_frame(lw)
    return hf[hf["roster_id"] == int(team)]


def _starts_soon(league_id: str, team: int, season: int, week: int, is_house: bool, h: pd.DataFrame) -> dict[str, dict]:
    """sleeper id -> {weeks: [the weeks of this one and the next he starts], slot} for this roster. This week: the
    lineup My Week shows (the nightly's rows, or the on-demand solve, with the availability overlay re-solved by
    `availability.apply_to_rows` — so a player who starts because a teammate is Out counts as a starter); next week: the
    horizon's solved lineup. Integration: IB-0's `availability.roster_context` is the same answer for this week."""
    out: dict[str, dict] = {}
    rows = None
    try:
        # PO merge (Wave I-B): this week = IB-0's one roster context (the same rows My Week, Team and the calculator
        # read, cached for the overlay's interval), instead of a second overlay pass of our own
        rc = availability.roster_context(league_id, int(team), int(week), house=is_house)
        rows = rc.rows if rc is not None else None
    except (NotFound, SleeperDown, A.SleeperBusy):
        rows = None
    if rows is not None and not rows.empty:
        st = rows[(rows["role"] == "starter") & ~rows["is_empty_slot"].fillna(False).astype(bool)]
        for sid, slot in zip(st["sleeper_player_id"], st["slot"], strict=True):
            if isinstance(sid, str):
                out.setdefault(sid, {"weeks": [], "slot": slot})["weeks"].append(int(week))
    elif not h.empty:
        st = h[(h["week"] == int(week)) & (h["role"] == "starter")]
        for sid, slot in zip(st["sleeper_player_id"], st["slot"], strict=True):
            if isinstance(sid, str):
                out.setdefault(sid, {"weeks": [], "slot": slot})["weeks"].append(int(week))
    if not h.empty:
        nx = h[(h["week"] == int(week) + 1) & (h["role"] == "starter")]
        for sid, slot in zip(nx["sleeper_player_id"], nx["slot"], strict=True):
            if isinstance(sid, str):
                out.setdefault(sid, {"weeks": [], "slot": slot})["weeks"].append(int(week) + 1)
    return out


def _when(weeks: list[int], week: int) -> str:
    ws = sorted(set(weeks))
    if ws == [week]:
        return "this week"
    if ws == [week + 1]:
        return f"next week (week {week + 1})"
    return "this week and next"


def _drop_starts(m: dict, soon: dict[str, dict], week: int) -> dict | None:
    d = m.get("drop") or {}
    s = soon.get(str(d.get("sleeper_id"))) if d.get("sleeper_id") else None
    if s is None:
        return None
    return {"weeks": sorted(set(s["weeks"])), "slot": _str(s.get("slot")),
            "text": f"{d.get('player_name')} starts for you {_when(s['weeks'], week)}"}


def _alternative(m: dict, mv: pd.DataFrame, soon: dict[str, dict], blocked: set[str], week: int, last: int) -> dict:
    """The best claim at the same position that keeps the drop (its own drop sits, or no drop is needed): the line a
    card shows before it suggests giving up a starter. None found: the line says so (never a starter's drop without it)."""
    add, drop = m.get("add") or {}, m.get("drop") or {}
    pos = add.get("position")
    c = mv[(mv["add_position"] == pos) & (mv["list_kind"] != "nothing")] if not mv.empty else mv
    if not c.empty:
        keep = c["drop_sleeper_id"].map(lambda s: not isinstance(s, str) or s not in soon)
        ok = c["add_gsis_id"].map(lambda g: not (isinstance(g, str) and g in blocked))
        c = c[keep & ok]
        c = c[pd.to_numeric(c["horizon_gain"], errors="coerce") >= GAIN_EPS]
    keepname = _last(drop.get("player_name"))
    span = _span_words(week, last)
    if c.empty:
        return {"move": None, "line": f"No free agent at {pos} helps without dropping a starter: keeping {keepname} "
                                      f"costs nothing, so claim only if the gain is worth his spot."}
    r = c.sort_values(["horizon_gain", "add_rank"], ascending=[False, True]).iloc[0]
    alt = {"add": _player(r.get("add_sleeper_id"), r.get("add_gsis_id"), r.get("add_name"), r.get("add_position"),
                          r.get("add_team"), bio([r.get("add_gsis_id"), r.get("drop_gsis_id")])),
           "drop": None if not isinstance(r.get("drop_sleeper_id"), str) else {
               "sleeper_id": r.get("drop_sleeper_id"), "gsis_id": _str(r.get("drop_gsis_id")),
               "player_name": _str(r.get("drop_name")), "position": _str(r.get("drop_position"))},
           "weekly_gain": _num(r.get("weekly_gain")), "horizon_gain": _num(r.get("horizon_gain"))}
    g = alt["horizon_gain"] or 0.0
    who = alt["drop"]["player_name"] if alt["drop"] else None
    if alt["add"]["sleeper_id"] == add.get("sleeper_id"):
        line = f"Or drop {_last(who)} instead (he sits) and keep {keepname}: +{g:.1f} over {span}."
    else:
        tail = f" (drop {_last(who)}, who sits)" if who else " (no drop: an open spot)"
        line = f"Or: add {alt['add']['player_name']} for a +{g:.1f} gain over {span} and keep {keepname}{tail}."
    return {"move": alt, "line": line}


def _byes(h: pd.DataFrame) -> tuple[dict, dict[int, list[str]]]:
    """{week: names on a bye — those who could play a slot left empty first}, {week: starting slots left empty} from
    the horizon rows."""
    if h.empty:
        return {}, {}
    by = h[(h["role"] == "unplayable") & (h["reason"] == "bye")]
    em = h[h["role"] == "empty"]
    empty = {int(w): [str(s) for s in g["slot"].dropna()] for w, g in em.groupby("week")}
    types = {int(w): {str(t) for t in g["slot_type"].dropna()} for w, g in em.groupby("week")}
    byes = {}
    for w, g in by.groupby("week"):
        ok = set().union(*(W.SLOT_ELIGIBILITY.get(t, frozenset()) for t in types.get(int(w), set()))) if types.get(int(w)) else set()
        fit = [n for n, p in zip(g["player_name"], g["position"], strict=True) if isinstance(n, str) and p in ok]
        byes[int(w)] = fit + [n for n in g["player_name"] if isinstance(n, str) and n not in fit]
        byes[("fit", int(w))] = fit
        byes[("pos", int(w))] = {n: p for n, p in zip(g["player_name"], g["position"], strict=True) if isinstance(n, str)}
    # ---- IE-0: what an explanation needs to be the evaluated move's own — each empty slot's type that week, and the
    # slot each player on a bye holds in the decision week (he is the starter the candidate would stand in for)
    for w, g in em.groupby("week"):
        byes[("empty_types", int(w))] = {str(s): str(t) for s, t in zip(g["slot"], g["slot_type"], strict=True)
                                         if isinstance(s, str) and isinstance(t, str)}
    first = int(h["week"].min())
    st = h[(h["week"] == first) & (h["role"] == "starter")]
    byes["starter_slot"] = {str(n): (str(s), str(t)) for n, s, t in zip(st["player_name"], st["slot"], st["slot_type"], strict=True)
                            if isinstance(n, str) and isinstance(s, str) and isinstance(t, str)}
    # ---- end IE-0
    return byes, empty


def _bye_reason(m: dict, w: int, byes: dict, empty: dict, strict: bool = False) -> str | None:
    """IE-0 (Wave I-E, the review's P0 #2): the bye words come from the evaluated move, never from the team's need alone
    ("Arizona Cardinals QB fills the empty DEF in week 7" is impossible). The candidate fills an empty slot only when
    that slot's type admits his position; he covers a bye only for a starter who holds a slot he can play; otherwise
    there is no bye reason (None) and the card says when he helps. ``strict`` is kept for the callers (always strict)."""
    del strict
    pos = (m.get("add") or {}).get("position")
    if not pos:
        return None
    elig = W.SLOT_ELIGIBILITY
    g = (m.get("week_gains") or [None] * 99)[w - int(m.get("_week") or w)] if m.get("_week") else None
    tail = f" (+{g:.1f} that week)" if isinstance(g, int | float) and g >= GAIN_EPS else ""
    on_bye = byes.get(w) or []
    bpos = byes.get(("pos", w)) or {}
    types = byes.get(("empty_types", w)) or {}
    held = byes.get("starter_slot") or {}

    def be(ns: list[str]) -> str:
        return "is" if len(ns) == 1 else "are"
    # 1. an empty starting slot he is eligible for: he fills it; the bye named is of a player who could have filled it
    for hole in empty.get(w) or []:
        t = types.get(hole)
        ok = elig.get(t) if t else None
        if ok and pos in ok:
            who = [n for n in on_bye if bpos.get(n) in ok] or on_bye
            words = cards.slot_label(hole)
            return (f"Fills your empty {words} in week {w}, when {_name_list(who)} {be(who)} on a bye{tail}."
                    if who else f"Fills your empty {words} in week {w}{tail}.")
    # 2. a starter on a bye whose slot he can play: he stands in at that slot
    cover = [(n, held[n]) for n in on_bye if n in held and pos in (elig.get(held[n][1]) or frozenset())]
    if cover:
        who = [n for n, _ in cover]
        words = cards.slot_label(cover[0][1][0])
        return f"Starts at {words} in week {w}, when {_name_list(who)} {be(who)} on a bye{tail}."
    return None


def _reason(m: dict, week: int, byes: dict, empty: dict, stash: dict) -> str:
    """One fact for a claim (My Week's `why` style): the role, the bye, the slot — not the whole paragraph."""
    add = m.get("add") or {}
    s = stash.get(add.get("gsis_id") or "")
    if s and s.get("change_text"):
        return f"His role grew: {s['change_text']}" + (f" since week {s['since_week']}." if s.get("since_week") else ".")
    gains = m.get("week_gains") or []
    helped = [week + i for i, g in enumerate(gains) if g is not None and g > 0.005]
    slot = m.get("add_slot")
    slot = cards.slot_label(slot) if slot else slot          # ---- IE-0: the league's words ("WR/TE 2", "team QB")
    if (m.get("weekly_gain") or 0) >= GAIN_EPS and slot:
        if m.get("fills_empty_slot"):
            return f"Fills your empty {slot} this week."
        d = m.get("displaced") or {}
        if d.get("player_name"):
            p = d.get("projection")
            who = unit_short(d["player_name"]) if d.get("position") in UNIT_POSITIONS else _last(d["player_name"])   # IC-4
            return f"Starts at {slot} this week over {who}" + (f" ({p:.1f})." if p is not None else ".")
        return f"Starts at {slot} this week."
    for w in helped:
        if w in byes and w != week:
            r = _bye_reason(m, w, byes, empty, strict=True)
            if r:
                return r
    unit = add.get("position") in UNIT_POSITIONS          # ---- IE-0: a team unit is priced from its starter's games
    if add.get("is_no_evidence") and not unit:
        return "No games this season yet: a flyer on his role."
    if helped:
        now = "" if (m.get("weekly_gain") or 0) >= GAIN_EPS else "Would not start for you this week; "   # ---- IE-0
        ws = f"week{'s' if len(helped) > 1 else ''} {', '.join(str(w) for w in helped)}"
        return f"{now}helps in {ws}." if now else f"Helps in {ws}."
    return "Adds to your lineup over the next weeks."


def _cost(m: dict, week: int, last: int, starts: dict | None) -> str:
    d = m.get("drop")
    if not d:
        return "No drop: you have an open roster spot."
    name = d.get("player_name")
    if starts:
        return f"Drop {name}: he starts for you {_when(starts['weeks'], week)}."
    loss = d.get("horizon_loss")
    if loss is not None and loss > GAIN_EPS:
        return f"Drop {name}: costs your lineup {loss:.1f} over {_span_words(week, last)}."
    return f"Drop {name}: he sits anyway."


def waiver_views(league_id: str, team: int | None, season: int, week: int, mv: pd.DataFrame, out: dict,
                 is_house: bool, od_info: dict, ros: dict) -> dict:
    """/api/waivers' `top3`, `views` and `default_view`; every move object in the answer that drops a player who starts
    this week or next gets `drop_starts` and `keep_alternative` (the best claim that keeps him, or the line that none
    does)."""
    t0 = time.perf_counter()
    last = _int(out.get("horizon_last_week")) or int(week)
    span = _span_words(int(week), last)
    stashes = (out.get("upside") or {}).get("stashes") or []
    res: dict = {"top3": [], "default_view": "help", "views": {
        "help": {"label": VIEW_LABELS["help"], "line": None, "moves": []},
        "bye": {"label": VIEW_LABELS["bye"], "line": None, "week": None, "on_bye": [], "empty_slots": [], "moves": []},
        "stash": {"label": VIEW_LABELS["stash"], "count": len(stashes)},
        "all": {"label": VIEW_LABELS["all"], "count": len(out.get("free_agents") or [])}}}
    if team is None or mv is None or mv.empty or (mv["list_kind"] == "nothing").all():
        res["views"]["help"]["line"] = out.get("notice") or "No free agent improves your lineup."
        res["views"]["bye"]["line"] = "No free agent improves your lineup in a bye week either."
        res["views_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        return res
    h = _horizon_rows(league_id, int(team), is_house, od_info)
    soon = _starts_soon(league_id, int(team), int(season), int(week), is_house, h)
    byes, empty = _byes(h)
    stash = {(s.get("add") or {}).get("gsis_id"): s for s in stashes if (s.get("add") or {}).get("gsis_id")}
    gs = {g for g in mv["add_gsis_id"] if isinstance(g, str)}
    blocked = set(availability.cannot_play(gs)) if gs else set()
    best = mv[mv["is_best_drop"].fillna(False).astype(bool) & (mv["list_kind"] != "nothing")]
    best = best[~best["add_gsis_id"].map(lambda g: isinstance(g, str) and g in blocked)]
    proj = _week_ranges(league_id, season, int(week), best, is_house, od_info)
    b = bio(list(best["add_gsis_id"]) + list(best["drop_gsis_id"]))
    memo: dict[tuple, dict] = {}

    def move_of(r: pd.Series) -> dict:
        k = (r.get("add_sleeper_id"), _str(r.get("drop_sleeper_id")))
        if k not in memo:
            memo[k] = annotate(_move(r, int(week), b, proj, ros))
        return memo[k]

    def annotate(m: dict) -> dict:
        st = _drop_starts(m, soon, int(week))
        m["drop_starts"] = st
        m["keep_alternative"] = _alternative(m, mv, soon, blocked, int(week), last) if st else None
        return m

    def qb_once(ms: list[dict]) -> list[dict]:
        return availability.one_qb_per_team(ms)[0]

    # the three strongest: the lineup gain over the horizon, one claim per position (two DEFs compete for one slot)
    ranked = best.sort_values(["horizon_gain", "add_rank"], ascending=[False, True])
    top, seen = [], set()
    for _, r in ranked.iterrows():
        if (_num(r.get("horizon_gain")) or 0) < GAIN_EPS or r.get("add_position") in seen:
            continue
        top.append(move_of(r))
        seen.add(r.get("add_position"))
        if len(top) >= 3:
            break
    top = qb_once(top)
    # ---- IC-4 (Wave I-D): an empty starting slot first — the claim that fills it this week leads the three and Help now
    # (70587, overlay on: Hall and Price Out leave RB2 empty; "Fills your empty RB2 this week" comes before a kicker's +4)
    fills = best[best["fills_empty_slot"].fillna(False).astype(bool)
                 & (pd.to_numeric(best["weekly_gain"], errors="coerce") >= GAIN_EPS)] if "fills_empty_slot" in best else best.iloc[0:0]
    fills = fills.sort_values(["weekly_gain", "horizon_gain"], ascending=[False, False])
    if not fills.empty:
        first = move_of(fills.iloc[0])
        pos0 = (first.get("add") or {}).get("position")
        top = [first, *[m for m in top if m is not first and (m.get("add") or {}).get("position") != pos0]][:3]
    # ---- end IC-4

    def card(m: dict, reason: str | None = None, **extra) -> dict:
        return {"move": m, "reason": reason or _reason(m, int(week), byes, empty, stash),
                "cost": _cost(m, int(week), last, m.get("drop_starts")), "gain": m.get("horizon_gain"), "gain_label": span,
                "this_week": m.get("weekly_gain"), **extra}
    res["top3"] = [card(m) for m in top]
    # Help now: this week's lineup gain, most first
    now_rows = best[pd.to_numeric(best["weekly_gain"], errors="coerce") >= GAIN_EPS]
    now_rows = now_rows.assign(_fill=now_rows["fills_empty_slot"].fillna(False).astype(bool)          # ---- IC-4
                               if "fills_empty_slot" in now_rows else False).sort_values(
        ["_fill", "weekly_gain", "horizon_gain"], ascending=[False, False, False])
    help_moves = qb_once([move_of(r) for _, r in now_rows.head(VIEW_CAP * 2).iterrows()])[:VIEW_CAP]
    lv = _num(out.get("lineup_value"))
    res["views"]["help"].update({"moves": [card(m) for m in help_moves], "line": (
        f"Claims that raise this week's lineup{f' ({lv:.1f})' if lv is not None else ''}, the biggest gain first."
        if help_moves else f"No free agent beats this week's lineup{f' ({lv:.1f})' if lv is not None else ''}: "
                           "the claims that help come later (Bye coverage).")})
    # Bye coverage: the next week a bye leaves a starting slot empty (the roster cannot cover it)
    later = sorted(w for w in empty if isinstance(w, int) and w > int(week) and byes.get(w))
    bye = res["views"]["bye"]
    if later:
        w = later[0]
        i = w - int(week)
        cov = best.assign(_g=best["week_gains"].map(lambda g: _num(g[i]) if isinstance(g, list | tuple | np.ndarray)
                                                     and len(g) > i else None))
        cov = cov[pd.to_numeric(cov["_g"], errors="coerce") >= GAIN_EPS].sort_values(["_g", "horizon_gain"], ascending=False)
        bye_moves = qb_once([move_of(r) for _, r in cov.head(VIEW_CAP * 2).iterrows()])[:VIEW_CAP]
        slots = empty[w]
        who = byes[w]
        items = []
        for m in bye_moves:
            g = _num((m.get("week_gains") or [None] * (i + 1))[i])
            items.append(card(m, _bye_reason({**m, "_week": int(week)}, w, byes, empty), week_gain=g, week_gain_label=f"week {w}"))
        bye.update({"week": w, "on_bye": who, "empty_slots": slots, "moves": items,
                    "line": f"Week {w}: {_name_list(who, 3)} on a bye, and nobody on your bench can fill your "
                            f"{' and '.join(slots)}." + ("" if bye_moves else " No free agent fills it.")})
    else:
        cover = best[(best["list_kind"] == "cover")].sort_values(["horizon_gain", "add_rank"], ascending=[False, True])
        bye_moves = qb_once([move_of(r) for _, r in cover.head(VIEW_CAP * 2).iterrows()])[:VIEW_CAP]
        bye.update({"moves": [card(m) for m in bye_moves], "line": f"Your bench covers every bye through week {last}."
                    + (" These claims still help in a later week." if bye_moves else "")})
    res["default_view"] = "help" if help_moves or not bye["moves"] else "bye"
    # every move object already in the answer: the same two fields (the old cards and the paged list)
    for m in [*(out.get("moves") or []), *[c.get("move") or {} for c in out.get("cards") or []]]:
        if m.get("add"):
            annotate(m)
    _ie1_present(res, league_id, int(week), last, span)                  # ---- IE-1: this week first, no triple copy
    res["views_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    return res
# ---- end IB-2


# ---- IE-1 (Wave I-E, the casual-user review § "make waiver horizons visually unambiguous"): each card leads with THIS
# week's starter gain ("Bears defense instead of Jaguars: about 2 more starter points this week"), the window's total
# second and said to be cumulative ("+12.4 over weeks 4–7 in total"); the screen's answer is not the first card's move
# again, and Help now lists what the three strongest do not already show; a claim that takes the same spot this week
# as an earlier card is labelled an alternative ("Instead of Vele: …"); claims are not additive. `home_action` is My
# Week's third action (a claim that changes this week's starters). Numbers unchanged: the same moves and gains.
def _who_short(p: dict | None) -> str:
    p = p or {}
    n = str(p.get("player_name") or "")
    if p.get("position") == "DEF" and n.split():
        return f"{n.split()[-1]} defense"
    if p.get("position") in UNIT_POSITIONS:
        return unit_short(n) or n
    return n


def _about(x: float) -> str:
    k = int(round(x))
    return "under 1 more starter point" if k < 1 else f"about {k} more starter point{'s' if k != 1 else ''}"


def claim_lead(m: dict) -> str:
    """The card's first sentence: this week's starter gain (or that he does not start this week)."""
    add = _who_short(m.get("add"))
    g = _num(m.get("weekly_gain")) or 0.0
    slot = {"TMQB": "team QB", "TMPK": "team K"}.get(str(m.get("add_slot")), cards.slot_label(m.get("add_slot")))
    if g < GAIN_EPS:
        return f"{add}: no change to this week's starters"
    if m.get("fills_empty_slot"):
        return f"{add} fills your empty {slot}: {_about(g)} this week"
    d = m.get("displaced") or {}
    if d.get("player_name"):
        who = str(d.get("player_name") or "").split()[-1] if d.get("position") == "DEF" else _who_short(d)
        return f"{add} instead of {who}: {_about(g)} this week"
    return f"{add} starts at {slot}: {_about(g)} this week"


def _ie1_present(res: dict, league_id: str, week: int, last: int, span: str) -> None:
    def total(c: dict) -> str | None:
        g = _num(c.get("gain"))
        return None if g is None or last <= week else f"{g:+.1f} over {span} in total"

    def dress(cs: list[dict]) -> None:
        taken: dict[tuple, str] = {}
        for c in cs:
            m = c.get("move") or {}
            c["lead"] = claim_lead(m)
            c["total_words"] = total(c) if c.get("week_gain") is None else None   # Bye coverage: its week's own number
            d = m.get("displaced") or {}
            spot = (d.get("sleeper_id") or d.get("player_name"), m.get("add_slot")) if (_num(m.get("weekly_gain")) or 0) >= GAIN_EPS else None
            c["alternative_to"] = taken.get(spot) if spot and spot[0] else None
            if spot and spot[0] and spot not in taken:
                taken[spot] = _who_short(m.get("add"))
    def one(c: dict) -> tuple:
        m = c.get("move") or {}
        return (m.get("add") or {}).get("sleeper_id"), (m.get("drop") or {}).get("sleeper_id")
    help_all = list(res["views"]["help"]["moves"])
    # My Week's third action: the claim that raises this week's starters most (before the list drops the top three)
    res["home_action"] = None
    first = next((c for c in help_all if (_num(c.get("this_week")) or 0.0) >= 0.5), None)
    if first is not None:
        m = first["move"]
        dress([first])
        pname = "MFL" if str(league_id).lower().startswith("mfl:") else "Sleeper"
        drop = (m.get("drop") or {}).get("player_name")
        d = m.get("displaced") or {}
        res["home_action"] = {
            "kind": "move", "urgency": 3, "slot_label": cards.slot_label(m.get("add_slot")), "slots": [m.get("add_slot")],
            "action": f"Claim {(m.get('add') or {}).get('player_name')}" + (f", drop {drop}" if drop else "") + f": {_about(first['this_week'])} this week.",
            "reason": " ".join(x for x in (first.get("reason"), (first["total_words"] + ".") if first.get("total_words") else None,
                                           first.get("cost")) if x),
            "start": [{"key": (m.get("add") or {}).get("sleeper_id"), "name": _who_short(m.get("add"))}],
            "sit": [{"key": d.get("sleeper_id"), "name": _who_short(d)}] if d.get("player_name") else [],
            "drop": {"key": (m.get("drop") or {}).get("sleeper_id"), "name": drop} if drop else None,
            "submitted": False, "submitted_words": f"Nothing is claimed from here: put the claim in on {pname}.",
            "lock": None, "cards": [], "gain": _num(first.get("this_week")), "href": "/waivers"}
    # PO (I-E): the three strongest claims lead with this week's gain, so they are ordered by it (the window total
    # second) — the review's "the current-week view should emphasize the current-week improvement"
    res["top3"] = sorted(res["top3"], key=lambda c: (-(_num(c.get("this_week")) or 0.0), -(_num(c.get("gain")) or 0.0)))
    dress(res["top3"])
    dress(help_all)
    shown = {one(c) for c in res["top3"]}
    rest = [c for c in help_all if one(c) not in shown]
    res["views"]["help"]["moves"] = rest
    res["views"]["help"]["also_in_top3"] = len(help_all) - len(rest)
    if help_all and not rest:
        res["views"]["help"]["line"] = "The claims that raise this week's lineup are the ones above."
    elif help_all and len(rest) < len(help_all):
        res["views"]["help"]["line"] = "More claims that raise this week's lineup (beyond the ones above), the biggest gain this week first."
    dress(res["views"]["bye"]["moves"])
    n = len(res["top3"])
    opens = [_int((c.get("move") or {}).get("open_roster_spots")) for c in [*res["top3"], *help_all]]
    k = max((o for o in opens if o is not None), default=None)
    res["answer"] = (("The strongest claim is below." if n == 1 else f"The {'two' if n == 2 else 'three'} strongest claims are below,"
                      " each with what it adds this week.") if n else None)
    res["not_additive"] = ("Each claim is weighed on its own against your roster today: two claims do not add up"
                           + (f" beyond your {k} open roster spot{'s' if k != 1 else ''}" if k else "")
                           + ", and two claims for the same spot help only once.")
# ---- end IE-1
