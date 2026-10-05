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


def row(league: str, key: str, team: int | None) -> dict:
    try:
        c = card(league, key)
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
    for key, _from in items[:LIMIT]:
        if not lg:
            out["players"].append({"player_key": key, "read": False, "words": "pick a league to see him in it"})
            continue
        r = row(lg, key, team)
        name = r.pop("_league_name", None)
        if r.get("read") and out["league_name"] is None:
            out["league_name"], out["week"] = name, r.get("week")
        out["players"].append(r)
    return out


@router.get("/watchlist")
def watchlist_route(request: Request, league: str | None = None, team: int | None = None) -> JSONResponse:
    uid, _email, _sid = accounts._user(request)
    return JSONResponse(answer(uid, league, team), headers=accounts.NO_STORE)
