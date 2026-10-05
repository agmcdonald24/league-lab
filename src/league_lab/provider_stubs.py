"""STUB — IK-3 (Wave I-K): stand-ins for IK-1's ESPN and IK-2's Yahoo adapters, for tests and e2e recordings only.

Enabled only by ``LEAGUE_LAB_PROVIDER_STUBS=1`` (``platforms.build_adapter``); never on a deployed server. They answer
the documented interface (INTERFACES.md § IK-1 / § IK-2: ``MFLLeagues``'s method set in Sleeper's shapes) for two
synthetic keys by re-keying the Sleeper fixture "Test League" (``9000000000000000001``, ``api/tests/fixtures/sleeper``):

* ``espn:4242`` — a public ESPN league (synthetic; IK-1's fixture league has the same id);
* ``espn:5150`` — a private ESPN league (``LeaguePrivate``, code ``espn_league_private``);
* ``yahoo:461.l.4242`` — a Yahoo league; ``my_leagues(token)`` lists it for any token, refuses without one.

Every other id is ``LeagueNotFound`` (code ``<provider>_league_unknown``). The players, scoring and slots are the Sleeper
fixture's: these stubs prove the seam (Router dispatch, the setup answers, the screens on a prefixed key), not a
provider's translation — that is IK-1's / IK-2's code and tests.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

from .sleeper_client import LeagueNotFound

SOURCE = "9000000000000000001"          # the Sleeper fixture league the stubs re-key
ESPN_PUBLIC, ESPN_PRIVATE, YAHOO_KEY = "4242", "5150", "461.l.4242"


class StubPrivate(LeagueNotFound):
    """STUB: IK-1's ``LeaguePrivate`` (a private ESPN league read without the user's cookies)."""

    def __init__(self, league_id: str) -> None:
        self.code = "espn_league_private"
        self.fix = ("Check the id first: it is the number after leagueId= in your league's address "
                    "(fantasy.espn.com/football/league?leagueId=4242).")
        super().__init__(f"ESPN league {league_id} is private. ESPN has no sign-in for other apps; a public league works "
                         "by its id (Settings → Basic Settings → League Visibility in ESPN)")


class StubNotConnected(LeagueNotFound):
    """STUB: a Yahoo read that needs the user's Yahoo connection."""

    def __init__(self) -> None:
        self.code = "yahoo_not_connected"
        super().__init__("Connect with Yahoo first: Yahoo shows a league's data only to an app its member allowed.")


class StubClient:
    """STUB: the client half (``calls``, ``stats()``) — no network, no cache."""

    def __init__(self, provider: str) -> None:
        self.provider = provider
        self.calls = 0
        self.fixtures = "stub"

    def stats(self) -> dict:
        return {"stub": True, "calls": self.calls}


class StubLeagues:
    """STUB: ESPN / Yahoo leagues in Sleeper's shapes, from the Sleeper fixture league (see the module docstring)."""

    def __init__(self, provider: str, client: Any, directory: Callable[[], dict]) -> None:
        self.provider = provider
        self.client = client if isinstance(client, StubClient) else StubClient(provider)
        self.directory = directory
        self.extra_players: dict[str, dict] = {}
        self._sleeper = getattr(directory, "__self__", None)   # the Router's Sleeper client (directory = its .players)
        if self._sleeper is None:
            from . import anyleague as A
            self._sleeper = A.sleeper().sleeper

    # ------------------------------------------------------------------ ids
    def _source(self, key: str) -> str:
        from . import platforms as P
        k = P.check_key(key)
        if self.provider == "espn":
            lid = P.espn_id(k)
            if lid == ESPN_PRIVATE:
                raise StubPrivate(lid)
            ok = lid == ESPN_PUBLIC
        else:
            ok = P.yahoo_key(k) == YAHOO_KEY
        if not ok:
            e = LeagueNotFound(f"{'ESPN' if self.provider == 'espn' else 'Yahoo'} has no league {k.split(':', 1)[1]} this season.")
            e.code = f"{self.provider}_league_unknown"       # type: ignore[attr-defined]
            raise e
        self.client.calls += 1
        return SOURCE

    def require_access(self, key: str) -> None:
        self._source(key)

    # ------------------------------------------------------------------ the method set
    def league(self, key: str) -> dict:
        src = self._source(key)
        d = copy.deepcopy(self._sleeper.league(src))
        lid = key.split(":", 1)[1]
        d["league_id"] = key
        d["name"] = "Synthetic ESPN League (stub)" if self.provider == "espn" else "Synthetic Yahoo League (stub)"
        d["platform"] = self.provider
        url = (f"https://fantasy.espn.com/football/league?leagueId={lid}" if self.provider == "espn"
               else f"https://football.fantasysports.yahoo.com/f1/{lid.rsplit('.', 1)[-1]}")
        d[self.provider] = {"league_id": lid, "season": int(d.get("season") or 2026), "url": url, "stub": True,
                            "slots": {"idp": [], "unknown": []}, "scoring": {"unpriced": [], "approximated": []}}
        return d

    def users(self, key: str) -> list[dict]:
        src = self._source(key)
        return [dict(u, league_id=key, platform=self.provider) for u in self._sleeper.users(src)]

    def rosters(self, key: str) -> list[dict]:
        src = self._source(key)
        return [dict(r, league_id=key) for r in self._sleeper.rosters(src)]

    def matchups(self, key: str, week: int) -> list[dict]:
        return self._sleeper.matchups(self._source(key), week)

    def season_matchups(self, key: str, through_week: int) -> dict[int, list[dict]]:
        return self._sleeper.season_matchups(self._source(key), through_week)

    def transactions(self, key: str, round_: int) -> list[dict]:
        return self._sleeper.transactions(self._source(key), round_)

    def translate(self, lid: str, ids: list[str]) -> dict[str, tuple[str, str]]:
        return {str(i): (str(i), "table") for i in ids}

    def unmapped(self, key: str) -> list[dict]:
        self._source(key)
        return []

    def mapped_by(self, key: str) -> dict[str, int]:
        n = sum(len(r.get("players") or []) for r in self.rosters(key))
        return {"table": n}

    def week(self, lid: str) -> int:
        st = self._sleeper.state() if hasattr(self._sleeper, "state") else {}
        return int((st or {}).get("week") or 1)

    # ------------------------------------------------------------------ Yahoo: the signed-in user's leagues
    def my_leagues(self, token: str | None) -> list[dict]:
        if self.provider != "yahoo":
            return []
        if not token:
            raise StubNotConnected()
        lg = self.league(f"yahoo:{YAHOO_KEY}")
        return [{"league_key": YAHOO_KEY, "name": lg["name"], "season": int(lg.get("season") or 2026),
                 "num_teams": lg.get("total_rosters"), "team_key": f"{YAHOO_KEY}.t.3", "team_id": 3,
                 "team_name": None, "url": lg["yahoo"]["url"]}]


def adapter(provider: str, client: Any, directory: Callable[[], dict]) -> StubLeagues:
    return StubLeagues(provider, client, directory)
