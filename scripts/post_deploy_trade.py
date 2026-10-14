"""The after-publish check's trade, chosen from the league's current rosters (JB-3, Wave J-B).

``scripts/post_deploy_check.py`` imports ``live_trade`` when no ``--trade`` / ``POST_DEPLOY_TRADE`` is given, so the
check never fails because a known player left the league (run #47, 2026-10-14: "Can't analyse 650"). The rule, through
the API only (read only, the same calls a visitor makes):

* the teams: ``/api/leagues/<league>/rosters`` in its order; the first two (up to ``MAX_TEAMS`` tried) that each have a
  bench candidate;
* a team's candidate: from ``/api/my-week``'s ``lineup_full`` (else ``lineup``), a player who is **not a starter**, not
  in an injured-reserve slot, a QB / RB / WR / TE with a key and a projection this week above zero — the one with the
  highest projection (ties: the lower key, so the choice is stable);
* the trade: team A gives its candidate for team B's (one for one); the ``reversed`` check runs on it as on any trade.

Standard library only (the check runs anywhere with python3).
"""

from __future__ import annotations

from collections.abc import Callable

HOUSE_LEAGUE = "1389709692405551104"         # League of Scrubs (the check's league, as the Folk case was)
MAX_TEAMS = 4
POSITIONS = {"QB", "RB", "WR", "TE"}

Call = Callable[[str, str], tuple[int, float, object]]


def _num(v) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def candidate(week: object) -> dict | None:
    """The bench player a team would trade in the check (see the module's rule), or None."""
    if not isinstance(week, dict):
        return None
    rows = week.get("lineup_full") or week.get("lineup") or []
    best = None
    for r in rows if isinstance(rows, list) else []:
        if not isinstance(r, dict) or r.get("role") == "starter":
            continue
        flag = str(r.get("flag") or "").lower()
        slot = str(r.get("slot") or "").upper()
        v = _num(r.get("value"))
        key = r.get("key")
        if ("ir slot" in flag or slot == "IR" or r.get("no_projection") or v is None or v <= 0
                or str(r.get("position") or "").upper() not in POSITIONS or not key):
            continue
        k = (-v, str(key))
        if best is None or k < best[0]:
            best = (k, {"key": str(key), "name": r.get("player_name"), "position": r.get("position"), "value": v})
    return best[1] if best else None


def live_trade(call: Call, league: str = HOUSE_LEAGUE) -> tuple[dict | None, str]:
    """({league, team, partner, give, get, words}, words) or (None, why)."""
    code, _, teams = call("GET", f"/api/leagues/{league}/rosters")
    if code != 200 or not isinstance(teams, list) or len(teams) < 2:
        return None, f"no team list for league {league} ({code})"
    found: list[tuple[int, dict]] = []
    for t in teams[:MAX_TEAMS]:
        rid = t.get("roster_id") if isinstance(t, dict) else None
        if not isinstance(rid, int):
            continue
        code, _, week = call("GET", f"/api/my-week?league={league}&team={rid}")
        c = candidate(week) if code == 200 else None
        if c is not None:
            found.append((rid, c))
        if len(found) == 2:
            break
    if len(found) < 2:
        return None, f"no two of the first {MAX_TEAMS} teams have a bench player with a projection this week"
    (a, ca), (b, cb) = found
    words = (f"team {a} gives {ca['name']} ({ca['position']}, key {ca['key']}) for team {b}'s {cb['name']} "
             f"({cb['position']}, key {cb['key']})")
    return {"league": league, "team": a, "partner": b, "give": [ca["key"]], "get": [cb["key"]], "words": words}, words
