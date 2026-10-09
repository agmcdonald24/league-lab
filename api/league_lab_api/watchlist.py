"""The watchlist screen's answer (Wave I-L, IL-5): ``GET /api/account/watchlist?league=&team=``.

IK-4 stores the rows (``PUT`` / ``DELETE /api/account/watchlist``, ``accounts.watchlist``); this reads them back for one
league, each player as the drawer's card has him in that league — the same code path as ``/api/player/<key>`` (a house
league from the database, any other league on demand: Sleeper, MFL, ESPN, Yahoo), so the row and the drawer it opens
never disagree:

* ``player_name``, ``position``, ``team`` (NFL), ``status`` (the injury designation after the availability overlay —
  the card's ``injury_status``; None = no designation), ``proj_points`` this week in the league's scoring (None: not
  projected this week — a bye, or no line), ``owner``: ``{kind: yours | free_agent | rostered | not_in_pool, team_id,
  team_name, words}`` — the Waivers screen's league-relative note ("Free agent", "Rostered by Run Bijan Run", "On your
  team").
* The league: ``league`` when given (the league on screen), else the account's default league; no league at all → the
  rows with ``player_key`` only and ``league: null`` (the screen asks for a league).
* Each row is read the lean way (``Lean``: the card's first steps only — the same queries and overlay, not its
  sections); ``test_il5`` checks it against the full card.
* A player is a player whatever league he was saved from: a row saved with a league and one without are one row.
  At most ``LIMIT`` players are read per answer (the oldest first; ``count`` says how many are saved); a row that cannot
  be read says why in ``words`` and the others still answer.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from . import accounts, db

log = logging.getLogger("league_lab_api.watchlist")
LIMIT = 30
_ON_TEAM = re.compile(r"\bon \*\*(.+?)\*\*")

router = APIRouter(prefix="/api/account")


def saved(user_id: str) -> list[tuple[str, str | None]]:
    """[(player_key, the app's league key or None)] — one per player, in the order they were added."""
    rows = db.run_rw(lambda c: c.execute(
        "select player_key, league_key from accounts.watchlist where user_id = %s order by added_at, player_key",
        (user_id,)).fetchall())
    seen: dict[str, str | None] = {}
    for pk, lk in rows or []:
        if pk not in seen:
            seen[pk] = accounts.app_key(lk) if lk else None
    return list(seen.items())


def default_league(user_id: str) -> str | None:
    row = db.run_rw(lambda c: c.execute(
        "select league_key from accounts.user_leagues where user_id = %s and is_default and not hidden limit 1",
        (user_id,)).fetchone())
    return accounts.app_key(row[0]) if row else None


def card(league: str, key: str) -> dict:
    """The drawer's card (main.py's ``/api/player/<key>`` path, without the HTTP)."""
    from . import myweek, ondemand, player
    if myweek.known_league(league):
        return player.player_card(league, key)
    return ondemand.player_card(league, key)


class Lean:
    """The first steps of ``player.player_card`` and nothing else — the same SQL (``PROFILE_SQL``, ``PROJ_SQL``), the
    same on-demand context (built once for every row), the same overlay — so a row's name, status, projection and
    owner equal the drawer's card without building its sections (a card is ~1 s on a loaded machine; the list has up to
    ``LIMIT``). A team unit (``mfl:TMQB-KC``) takes the full card (its line is its starter's)."""

    def __init__(self, league: str) -> None:
        from . import myweek
        self.league, self.house, self._od = league, myweek.known_league(league), None

    def od(self):
        if self._od is None:
            from . import ondemand
            self._od = ondemand.PlayerContext(self.league)
        return self._od

    def card(self, key: str) -> dict:
        from league_lab import platforms

        from . import player
        from .applib import cards
        from .db import query
        if platforms.is_mfl(key):
            return card(self.league, key)
        if self.house:
            lrow = player.league_row(self.league)
            season, league_name, prof_league = int(lrow["season"]), str(lrow["league_name"]), self.league
        else:
            od = self.od()
            season, league_name, prof_league = od.season, od.league_name, od.profile_league
        week = cards.decision_week(season)
        prof = query(player.PROFILE_SQL, (prof_league, season, season, prof_league, season, prof_league, season, key))
        if prof.empty:
            raise player.NotFound(f"No player with id `{key}`. Search for him above.")
        p = prof.iloc[0]
        if not self.house:
            p = p.copy()
            for k, v in self.od().availability(key).items():
                p[k] = v
        pos, team = p["position"], p["team"]
        proj = (query(player.PROJ_SQL, (self.league, key, season, week if week is not None else -1)) if self.house
                else self.od().projection(key, pos, week))
        # ---- PO (Wave I-S): the card's own status (player.status_note: the one definition, then the week's own report)
        note, _from_report = player.status_note(p, key, season, week)
        inj = note["status"] if note else None
        sits = bool(note and note["sits"])
        # ---- end PO
        rostered = player.is_num(p["rostered_by_roster_id"])
        rteam = p.get("rostered_by_team")
        return {"player_name": p["player_name"], "position": pos, "team": team if isinstance(team, str) else None,
                "injury_status": inj, "week": week, "league_name": league_name,
                "proj_points": 0.0 if sits else (float(proj.iloc[0]["proj_points"]) if not proj.empty else None),
                "rostered_by_roster_id": int(p["rostered_by_roster_id"]) if rostered else None,
                "is_free_agent": player.yes(p["is_free_agent"]),
                "header": f"on **{rteam}**" if rostered and isinstance(rteam, str) and rteam else ""}


def owner(c: dict, team: int | None) -> dict:
    rid = c.get("rostered_by_roster_id")
    if rid is not None:
        m = _ON_TEAM.search(str(c.get("header") or ""))
        name = m.group(1) if m else None
        if team is not None and int(rid) == int(team):
            return {"kind": "yours", "team_id": int(rid), "team_name": name, "words": "On your team"}
        return {"kind": "rostered", "team_id": int(rid), "team_name": name,
                "words": f"Rostered by {name}" if name else "Rostered by another team"}
    if c.get("is_free_agent"):
        return {"kind": "free_agent", "team_id": None, "team_name": None, "words": "Free agent"}
    return {"kind": "not_in_pool", "team_id": None, "team_name": None, "words": "Not in this league's player pool"}


def row(league: str, key: str, team: int | None, lean: Lean | None = None) -> dict:
    try:
        c = lean.card(key) if lean is not None else card(league, key)
    except Exception as exc:  # noqa: BLE001 - one row says why; the rest of the list still answers
        log.info("watchlist: %s not read in %s (%s)", key, league, exc.__class__.__name__)
        words = str(exc) if exc.__class__.__name__ in ("NotFound", "LeagueNotFound") else "not read just now"
        return {"player_key": key, "player_name": None, "position": None, "team": None, "status": None,
                "proj_points": None, "week": None, "owner": None, "read": False, "words": words}
    unit = c.get("unit") or {}
    return {"player_key": key, "player_name": c.get("player_name"), "position": unit.get("position") or c.get("position"),
            "team": unit.get("team") or c.get("team"), "status": c.get("injury_status"),
            "proj_points": c.get("proj_points"), "week": c.get("week"), "owner": owner(c, team), "read": True,
            "words": None, "_league_name": c.get("league_name")}


def answer(user_id: str, league: str | None, team: int | None) -> dict:
    items = saved(user_id)
    lg = (league or "").strip() or default_league(user_id)
    out: dict[str, Any] = {"league": lg, "league_name": None, "week": None, "count": len(items),
                           "shown": min(len(items), LIMIT), "players": []}
    lean = Lean(lg) if lg else None
    for key, _from in items[:LIMIT]:
        if not lg:
            out["players"].append({"player_key": key, "read": False, "words": "pick a league to see him in it"})
            continue
        r = row(lg, key, team, lean)
        name = r.pop("_league_name", None)
        if r.get("read") and out["league_name"] is None:
            out["league_name"], out["week"] = name, r.get("week")
        out["players"].append(r)
    return out


@router.get("/watchlist")
def watchlist_route(request: Request, league: str | None = None, team: int | None = None) -> JSONResponse:
    uid, _email, _sid = accounts._user(request)
    return JSONResponse(answer(uid, league, team), headers=accounts.NO_STORE)
