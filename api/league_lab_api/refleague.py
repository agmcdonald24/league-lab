"""Reference league keys (Wave I-M, IM-3): browse the lab without a league.

``ref:ppr``, ``ref:half`` and ``ref:std`` are leagues that do not exist anywhere: the NFL-wide research priced in one of
the reference scorings the nightly already fits the ranges for (``analytics_seeds.reference_scorings``,
``projections.reference_scorings()``; docs/ANY_LEAGUE.md):

| key        | reference scoring | words      |
|------------|-------------------|------------|
| ``ref:ppr``  | ``ppr``           | PPR        |
| ``ref:half`` | ``scrubs``        | Half PPR   |
| ``ref:std``  | ``standard``      | Standard   |

This module is **the one place that resolves them**: ``league(key)`` is a Sleeper-shaped league dict — the reference's
``scoring_settings``, standard slots (QB, 2 RB, 2 WR, TE, FLEX, K, DEF and a bench), the current season, no
rosters, no users, no matchups. ``install()`` hands an object answering those calls to ``platforms.REFERENCE``, so every
research route that already serves "any league" on request (Stats, Trends, Matchups, Compare, a player's page and
games, search, the receivers, About, the record) serves a reference key unchanged — priced in its scoring, the way an
unknown Sleeper league is.

What a reference key never has: an owner. ``public(out)`` takes every ownership field out of an answer (absent, not
empty: "rostered by" would read "free agent" for every player otherwise), and the decision routes (My Week, Waivers,
Trades, Team, League, ``/api/ros?view=lineup``, the league's odds, its scoring check, its rosters, its events) answer
``needs_league()``: 404 ``{"code": "needs_league", "error": "Open your league to see this."}`` — the web shows an
invitation card, never an error.
"""

from __future__ import annotations

import csv
import json
import threading
from typing import Any

from fastapi.responses import JSONResponse
from league_lab import platforms
from league_lab.sleeper_client import LeagueNotFound

from .settings import ROOT

# key -> (reference scoring's seed name, the words a screen shows)
KEYS: dict[str, tuple[str, str]] = {"ref:ppr": ("ppr", "PPR"), "ref:half": ("scrubs", "Half PPR"),
                                    "ref:std": ("standard", "Standard")}
DEFAULT = "ref:half"
SLOTS = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "K", "DEF", "BN", "BN", "BN", "BN", "BN", "BN"]
TEAMS = 12
NEEDS_LEAGUE = "Open your league to see this."
SEED = ROOT / "dbt" / "seeds" / "reference_scorings.csv"
REFERENCES_SQL = "select name, label, scoring_settings from analytics_seeds.reference_scorings order by name"
# ownership: whose team a player is on in "this league" — never part of a reference key's answer
OWNERSHIP = frozenset({
    "rostered_by_roster_id", "rostered_by_team", "rostered_by_manager", "is_free_agent", "is_current_starter",
    "is_on_ir", "viewer_roster_id", "on_my_team", "mine", "owner", "owner_team", "owned_by", "roster_id",
    "my_team", "team_name", "manager_name", "rostered", "rostered_pct",
})


def is_reference(key: Any) -> bool:
    return platforms.is_reference(key)


def label(key: str) -> str:
    return KEYS[str(key).strip().lower()][1]


_scorings: dict[str, dict[str, float]] = {}
_lock = threading.Lock()


def _load_scorings() -> dict[str, dict[str, float]]:
    """name -> scoring_settings of the reference scorings: the database's seed table, else the seed file."""
    with _lock:
        if _scorings:
            return _scorings
        rows: list[tuple[str, Any]] = []
        try:
            from .db import query
            df = query(REFERENCES_SQL)
            rows = [(str(r.name), r.scoring_settings) for r in df.itertuples()]
        except Exception:  # noqa: BLE001 - a fresh database: the seed file below
            rows = []
        if not rows:
            with open(SEED, newline="") as fh:
                rows = [(r["name"], r["scoring_settings"]) for r in csv.DictReader(fh)]
        for name, settings in rows:
            d = json.loads(settings) if isinstance(settings, str) else dict(settings or {})
            _scorings[name] = {k: float(v) for k, v in d.items() if v is not None}
        return _scorings


def _season() -> int:
    try:
        from .applib import ui
        s = ui.current_season()
        if s:
            return int(s)
    except Exception:  # noqa: BLE001 - the clock's season below
        pass
    from league_lab import clock
    now = clock.now()
    return now.year if now.month >= 3 else now.year - 1


def league(key: str) -> dict:
    """The Sleeper-shaped league of a reference key (LeagueNotFound for anything else)."""
    k = str(key or "").strip().lower()
    if k not in KEYS:
        raise LeagueNotFound(f"not a reference league: {key!r}")
    name, words = KEYS[k]
    scoring = _load_scorings().get(name)
    if scoring is None:
        raise LeagueNotFound(f"the reference scoring {name!r} is not on this database")
    return {"league_id": k, "name": f"No league · {words}", "season": str(_season()), "status": "in_season",
            "sport": "nfl", "scoring_settings": dict(scoring), "roster_positions": list(SLOTS),
            "total_rosters": TEAMS, "settings": {"num_teams": TEAMS, "playoff_week_start": 15, "type": 0},
            "reference": True, "reference_scoring": name, "scoring_label": words}


class References:
    """What ``platforms.Router`` asks a provider for, answered for a reference key: the league, and nothing else."""

    def league(self, key: str) -> dict:
        return league(key)

    def rosters(self, key: str) -> list[dict]:
        league(key)
        return []

    def users(self, key: str) -> list[dict]:
        league(key)
        return []

    def matchups(self, key: str, week: int) -> list[dict]:
        league(key)
        return []

    def season_matchups(self, key: str, through_week: int) -> dict[int, list[dict]]:
        league(key)
        return {}

    def transactions(self, key: str, round_: int) -> list[dict]:
        league(key)
        return []


def install() -> None:
    platforms.REFERENCE = References()


def public(out: Any) -> Any:
    """The answer with every ownership field taken out, at any depth (a reference key has no rosters)."""
    if isinstance(out, dict):
        return {k: public(v) for k, v in out.items() if k not in OWNERSHIP}
    if isinstance(out, list):
        return [public(v) for v in out]
    return out


def needs_league_body() -> dict:
    return {"error": NEEDS_LEAGUE, "detail": NEEDS_LEAGUE, "code": "needs_league"}


def needs_league() -> JSONResponse:
    return JSONResponse(needs_league_body(), status_code=404, headers={"Cache-Control": "no-store"})


RECORD_NOTE = ("Our record is kept in Half PPR scoring (4 points a passing touchdown): the scoring of the league we "
               "project every morning.")


def record(key: str) -> dict:
    """``/api/record`` for a reference key: the model's record as the reference house league keeps it (Half PPR — the
    league the nightly projects every morning), without its lineup record (``decisions``: those are managers' teams);
    for ``ref:ppr`` / ``ref:std`` the answer says it is kept in Half PPR. ``available: false`` when no house league."""
    from .applib import ui
    from .ondemand import record as league_record
    from .myweek import NotFound
    k = str(key).strip().lower()
    if k not in KEYS:
        raise NotFound(f"not a reference league: {key!r}")
    cur = ui.current_leagues()
    ref = cur[cur["is_reference_league"].astype(bool)] if not cur.empty and "is_reference_league" in cur else cur
    if ref is None or ref.empty:
        return {"league_id": k, "available": False, "why": "the record is not on this database yet"}
    out = league_record(str(ref["league_id"].iloc[0]))
    out.pop("decisions", None)
    out["league_id"] = k
    out["reference"] = True
    out["scoring_note"] = None if k == DEFAULT else RECORD_NOTE
    return out


class NeedsLeague(Exception):
    """A decision route was asked about a reference key (main.py answers ``needs_league()``)."""
