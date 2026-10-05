"""Yahoo leagues in Sleeper's shapes (Wave I-K, IK-2) — ``MFLLeagues``'s method set for ``yahoo:`` keys.

A key is ``yahoo:<game_key>.l.<league_id>`` (``yahoo:461.l.4242``). ``YahooLeagues`` reads through
``yahoo_client.Yahoo`` (its own caches and budget; every read as the request's signed-in manager — Yahoo has no
app-only token, so even a public league needs a connected Yahoo account) and translates:

* the league: ``roster_positions`` (W/R/T -> FLEX, Q/W/R/T -> SUPER_FLEX, W/R -> WRRB_FLEX, W/T -> REC_FLEX, IR counted
  in ``settings.reserve_slots``, IDP slots left out and reported), ``scoring_settings`` on Sleeper's keys
  (``yahoo_client.STAT_KEYS``; the unpriced stats by the league's own names), the playoffs, the week Yahoo is on
  (``current_week``), FAAB -> ``waiver_type`` 2;
* teams -> users and rosters: ``roster_id`` = Yahoo's team id (1..N), ``owner_id`` = the same id as a string (the
  manager's Yahoo guid in ``metadata.yahoo_guid``), players as **Sleeper ids**, ``starters`` seated exactly where Yahoo
  has them this week (``selected_position``; "0" for an empty slot), IR in ``reserve``, the record and points from
  the standings;
* the scoreboard -> matchups (``matchup_id`` 1..6 in Yahoo's order, points as Yahoo totals them);
* transactions -> Sleeper's transaction dicts (``free_agent`` / ``waiver`` / ``trade``; the round is the Yahoo game week
  whose dates hold the transaction's time; ``settings.waiver_bid`` from a FAAB claim).

Player ids: Yahoo's player id (``461.p.30121`` -> ``30121``) -> ``sleeper_id`` through nflverse's ``yahoo_id``
(``player_ids``), else -> ``gsis_id`` -> Sleeper through ``platforms.GSIS_LOOKUP``, else a team defense by its team
(Sleeper's DEF id is the team code), else a unique name + position match in Sleeper's directory (two of the name: the
one on Yahoo's NFL team) — load-bearing: nflverse gives no 2025 or 2026 rookie a ``yahoo_id`` (IK-3's audit) —, else the
player stays
on the roster as ``yahoo:<id>`` with Yahoo's name and position (unvalued, reported in ``unmapped``).
"""

from __future__ import annotations

import datetime as dt
import math
import threading
from collections.abc import Callable, Mapping
from typing import Any

from . import player_ids as PI
from . import yahoo_client as Y
from .sleeper_client import LeagueNotFound

PREFIX = "yahoo:"


def is_yahoo(key: Any) -> bool:
    return str(key or "").strip().lower().startswith(PREFIX)


def check_key(key: Any) -> str:
    """``yahoo:461.l.4242`` (any case, spaces) -> itself, lower-cased; anything else is ``YahooLinkInvalid``."""
    s = str(key or "").strip()
    if not is_yahoo(s):
        raise Y.YahooLinkInvalid(f"not a Yahoo league key: {key!r}")
    return PREFIX + Y.check_league_key(s[len(PREFIX):])


def league_key(key: str) -> str:
    """``yahoo:461.l.4242`` -> ``461.l.4242``."""
    return check_key(key)[len(PREFIX):]


def _norm(name: str) -> str:
    from .platforms import _norm as norm
    return norm(name)


def _settings(points: float) -> dict:
    return {"fpts": int(math.floor(points)), "fpts_decimal": int(round((points - math.floor(points)) * 100))}


class YahooLeagues:
    """Yahoo leagues in Sleeper's shapes (see the module docstring). ``directory``: Sleeper's player directory."""

    def __init__(self, client: Y.Yahoo, directory: Callable[[], dict],
                 ids: Callable[[], PI.IdTable] = PI.table) -> None:
        self.client = client
        self.directory = directory
        self.ids = ids                                 # the id table (IK-3 passes ``player_ids.table``)
        self.extra_players: dict[str, dict] = {}       # "yahoo:<id>" -> a directory-shaped row (unmapped players)
        self.mapping: dict[str, dict] = {}             # league key -> {yahoo id: (sleeper id, how)}
        self._name_index: tuple[int, dict[tuple[str, str], list[str]]] | None = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ keys
    def _lk(self, key: str) -> str:
        """The numeric league key of a ``yahoo:`` key (``nfl.l.4242`` resolved to this season's game)."""
        return self.client.resolve(league_key(key))

    # ------------------------------------------------------------------ ids
    def _index(self) -> dict[tuple[str, str], list[str]]:
        d = self.directory()
        if self._name_index is None or self._name_index[0] != id(d):
            idx: dict[tuple[str, str], list[str]] = {}
            for sid, p in d.items():
                nm = p.get("full_name") or " ".join(x for x in (p.get("first_name"), p.get("last_name")) if x)
                if nm and p.get("position"):
                    idx.setdefault((_norm(nm), str(p["position"])), []).append(str(sid))
            self._name_index = (id(d), idx)
        return self._name_index[1]

    def translate(self, lk: str, players: Mapping[str, Mapping] | list[str]) -> dict[str, tuple[str, str]]:
        """Yahoo player ids -> (Sleeper id or ``yahoo:<id>``, how: table | gsis | defense | name | unmapped).
        ``players``: ``{yahoo id: player_row}`` (the name / position / team the later steps need), or bare ids."""
        info = {str(k): dict(v) for k, v in players.items()} if isinstance(players, Mapping) \
            else {str(i): {} for i in players}
        out: dict[str, tuple[str, str]] = {}
        tab = self.ids()
        gsis_need: dict[str, str] = {}
        for i, p in info.items():
            if p.get("position") == "DEF":                 # a team defense: Sleeper's DEF id is the team code
                if p.get("team"):
                    out[i] = (str(p["team"]), "defense")
                continue
            sid = tab.yahoo_to_sleeper(i)
            if sid:
                out[i] = (sid, "table")
                continue
            g = tab.yahoo_to_gsis(i)
            if g:
                gsis_need[i] = g
        from . import platforms
        if gsis_need and platforms.GSIS_LOOKUP is not None:
            try:
                got = platforms.GSIS_LOOKUP(sorted(set(gsis_need.values()))) or {}
            except Exception:  # noqa: BLE001 - the database fallback is a nicety: the next steps still run
                got = {}
            for i, g in gsis_need.items():
                if got.get(g):
                    out[i] = (str(got[g]), "gsis")
        rest = [i for i in info if i not in out]
        idx = self._index() if rest else {}
        for i in rest:
            p = info[i]
            pos = p.get("position")
            hits = idx.get((_norm(str(p.get("name") or "")), str(pos))) if p.get("name") and pos else None
            if hits and len(hits) > 1 and p.get("team"):      # two of the name: the one on Yahoo's NFL team
                d = self.directory()
                hits = [h for h in hits if str((d.get(h) or {}).get("team") or "") == str(p["team"])]
            if hits and len(hits) == 1:
                out[i] = (hits[0], "name")
                continue
            key = f"{PREFIX}{i}"
            self.extra_players[key] = {"player_id": key, "full_name": p.get("name") or f"Yahoo player {i}",
                                       "position": pos, "fantasy_positions": [pos] if pos else None,
                                       "team": p.get("team"), "status": "Active", "active": True,
                                       "injury_status": p.get("injury_status"), "yahoo_id": i}
            out[i] = (key, "unmapped")
        with self._lock:
            self.mapping.setdefault(lk, {}).update(out)
        return out

    def unmapped(self, key: str) -> list[dict]:
        """The rostered Yahoo players with no Sleeper id (``{yahoo_id, name, position}``)."""
        lk = league_key(key)
        rows = []
        for i, (sid, how) in sorted(self.mapping.get(lk, {}).items()):
            if how == "unmapped":
                p = self.extra_players.get(sid) or {}
                rows.append({"yahoo_id": i, "name": p.get("full_name"), "position": p.get("position")})
        return rows

    def mapped_by(self, key: str) -> dict[str, int]:
        out: dict[str, int] = {}
        for _sid, how in self.mapping.get(league_key(key), {}).values():
            out[how] = out.get(how, 0) + 1
        return out

    # ------------------------------------------------------------------ Sleeper-shaped calls
    def week(self, key: str) -> int:
        st = self.client.settings(self._lk(key) if is_yahoo(key) else Y.check_league_key(key))
        try:
            return max(1, int(st.get("current_week") or 1))
        except (TypeError, ValueError):
            return 1

    def league(self, key: str) -> dict:
        lk = self._lk(key)
        st = self.client.settings(lk)
        s = st.get("settings") or {}
        slot_list, slot_note = Y.slots(s)
        sc, report = Y.scoring(s)
        week = self.week(PREFIX + lk)
        n = int(Y._f(st.get("num_teams"), 0)) or len(self.client.teams(lk))
        playoff_start = int(Y._f(s.get("playoff_start_week"), 0)) if str(s.get("uses_playoff") or "1") != "0" else 0
        return {"league_id": PREFIX + lk, "name": str(st.get("name") or f"Yahoo league {lk}").strip(),
                "season": str(st.get("season") or ""), "season_type": "regular", "sport": "nfl",
                "status": "complete" if str(st.get("is_finished") or "0") == "1" else "in_season",
                "total_rosters": n, "roster_positions": slot_list, "scoring_settings": sc,
                "settings": {"playoff_week_start": playoff_start,
                             "playoff_teams": int(Y._f(s.get("num_playoff_teams"), 0)) if playoff_start else 0,
                             "playoff_round_type": 0, "leg": week, "last_scored_leg": max(0, week - 1),
                             "num_teams": n, "start_week": int(Y._f(st.get("start_week"), 1)) or 1, "type": 0,
                             "taxi_slots": 0, "reserve_slots": slot_note["ir"],
                             "waiver_type": 2 if str(s.get("uses_faab") or "0") == "1" else 0},
                "platform": "yahoo",
                "yahoo": {"league_key": lk, "url": st.get("url") or None, "slots": slot_note, "scoring": report,
                          "public": str(st.get("league_type") or "") == "public",
                          "trade_end_date": s.get("trade_end_date") or None}}

    def _teams(self, lk: str) -> list[dict]:
        return sorted(self.client.teams(lk), key=lambda t: int(Y._f(t.get("team_id"), 0)))

    @staticmethod
    def _managers(team: Mapping) -> list[dict]:
        return [m for m in Y.items(team.get("managers"), "manager") if isinstance(m, dict)]

    def users(self, key: str) -> list[dict]:
        lk = self._lk(key)
        out = []
        for t in self._teams(lk):
            mg = self._managers(t)
            first = mg[0] if mg else {}
            out.append({"user_id": str(t.get("team_id")), "display_name": first.get("nickname") or None,
                        "metadata": {"team_name": t.get("name"), "yahoo_guid": first.get("guid"),
                                     "yahoo_team_key": t.get("team_key")},
                        "is_owner": any(str(m.get("is_commissioner") or "0") == "1" for m in mg),
                        "league_id": PREFIX + lk, "platform": "yahoo"})
        return out

    def _records(self, lk: str) -> dict[int, dict]:
        out: dict[int, dict] = {}
        try:
            rows = self.client.standings(lk)
        except (Y.YahooUnavailable, Y.YahooBusy, Y.YahooLeagueNotFound):
            return out
        for t in rows:
            ts = t.get("team_standings") or {}
            ot = ts.get("outcome_totals") or {}
            pf = Y._f(ts.get("points_for"), Y._f((t.get("team_points") or {}).get("total")))
            out[int(Y._f(t.get("team_id"), 0))] = {"wins": int(Y._f(ot.get("wins"))), "losses": int(Y._f(ot.get("losses"))),
                                                   "ties": int(Y._f(ot.get("ties"))), **_settings(pf),
                                                   "rank": int(Y._f(ts.get("rank"))) or None}
        return out

    def rosters(self, key: str) -> list[dict]:
        lk = self._lk(key)
        week = self.week(PREFIX + lk)
        teams = self._teams(lk)
        rows: dict[int, list[dict]] = {}
        info: dict[str, dict] = {}
        for t in teams:
            tid = int(Y._f(t.get("team_id"), 0))
            ps = [Y.player_row(p) for p in self.client.roster(Y.team_key(lk, tid), week)]
            rows[tid] = [p for p in ps if p["yahoo_id"]]
            for p in rows[tid]:
                info[p["yahoo_id"]] = p
        tr = self.translate(lk, info)
        slot_list = self.league(PREFIX + lk)["roster_positions"]
        starting = [s for s in slot_list if s not in ("BN", "IR", "TAXI")]
        records = self._records(lk)
        out = []
        for t in teams:
            tid = int(Y._f(t.get("team_id"), 0))
            ps = rows.get(tid, [])
            sid = [tr[p["yahoo_id"]][0] for p in ps if p["yahoo_id"] in tr]
            starters = ["0"] * len(starting)
            for p in ps:
                slot = Y.SLOT.get(str(p.get("selected") or ""))
                if not slot or slot in ("BN", "IR") or p["yahoo_id"] not in tr:
                    continue
                for i, s in enumerate(starting):
                    if s == slot and starters[i] == "0":
                        starters[i] = tr[p["yahoo_id"]][0]
                        break
            reserve = [tr[p["yahoo_id"]][0] for p in ps if p.get("selected") == "IR" and p["yahoo_id"] in tr]
            rec = records.get(tid, {"wins": 0, "losses": 0, "ties": 0, "fpts": 0, "fpts_decimal": 0})
            out.append({"league_id": PREFIX + lk, "roster_id": tid, "owner_id": str(tid), "co_owners": None,
                        "players": sid, "starters": starters if any(x != "0" for x in starters) else [],
                        "reserve": reserve or None, "taxi": None,
                        "settings": {k: v for k, v in rec.items() if k != "rank"},
                        "metadata": {"yahoo_team_key": t.get("team_key"), "faab_balance": t.get("faab_balance"),
                                     "waiver_priority": t.get("waiver_priority")}})
        return sorted(out, key=lambda r: r["roster_id"])

    def matchups(self, key: str, week: int) -> list[dict]:
        lk = self._lk(key)
        out = []
        for i, m in enumerate(self.client.scoreboard(lk, int(week)), 1):
            for t in Y.items(m.get("teams"), "team"):
                pts = Y._f((t.get("team_points") or {}).get("total"))
                out.append({"roster_id": int(Y._f(t.get("team_id"), 0)) or Y.team_id_of(str(t.get("team_key"))),
                            "matchup_id": i, "points": pts, "starters": [], "players": [],
                            "projected": Y._f((t.get("team_projected_points") or {}).get("total")) or None})
        return out

    def season_matchups(self, key: str, through_week: int) -> dict[int, list[dict]]:
        return {w: self.matchups(key, w) for w in range(1, int(through_week) + 1)}

    # ------------------------------------------------------------------ transactions
    def _week_of(self, lk: str, ts: float) -> int:
        """The Yahoo game week whose dates hold ``ts`` (epoch seconds, US Eastern days); before week 1: 1."""
        try:
            weeks = self.client.game_weeks(lk.split(".l.")[0])
        except (Y.YahooUnavailable, Y.YahooBusy, LeagueNotFound):
            weeks = []
        day = (dt.datetime.fromtimestamp(ts, dt.UTC) - dt.timedelta(hours=5)).date().isoformat()
        best = 1
        for w in weeks:
            if str(w.get("start") or "") <= day:
                best = max(best, int(Y._f(w.get("week"), 1)))
        return best

    def transactions(self, key: str, round_: int) -> list[dict]:
        lk = self._lk(key)
        txs = self.client.transactions(lk)
        info: dict[str, dict] = {}
        for t in txs:
            for p in Y.items(t.get("players"), "player"):
                r = Y.player_row(p)
                if r["yahoo_id"]:
                    info[r["yahoo_id"]] = r
        tr = self.translate(lk, info) if info else {}
        out = []
        for t in txs:
            if str(t.get("status") or "successful") != "successful":
                continue
            ts = Y._f(t.get("timestamp"))
            leg = self._week_of(lk, ts)
            if leg != int(round_):
                continue
            adds: dict[str, int] = {}
            drops: dict[str, int] = {}
            rids: list[int] = []
            source = None
            for p in Y.items(t.get("players"), "player"):
                r = Y.player_row(p)
                d = p.get("transaction_data") or {}
                if isinstance(d, list):
                    d = d[0] if d and isinstance(d[0], dict) else {}
                sid = tr.get(r["yahoo_id"], (None, ""))[0]
                if not sid:
                    continue
                if d.get("destination_team_key"):
                    rid = Y.team_id_of(str(d["destination_team_key"]))
                    adds[sid] = rid
                    rids.append(rid)
                    source = source or d.get("source_type")
                if d.get("source_team_key"):
                    rid = Y.team_id_of(str(d["source_team_key"]))
                    drops[sid] = rid
                    rids.append(rid)
            kind = str(t.get("type") or "")
            typ = "trade" if kind == "trade" else ("waiver" if source == "waivers" else "free_agent")
            bid = t.get("faab_bid")
            out.append({"transaction_id": str(t.get("transaction_id") or t.get("transaction_key")), "type": typ,
                        "status": "complete", "leg": leg, "created": int(ts * 1000), "status_updated": int(ts * 1000),
                        "roster_ids": sorted(set(rids)), "adds": adds or None, "drops": drops or None,
                        "creator": None, "consenter_ids": sorted(set(rids)), "draft_picks": [], "waiver_budget": [],
                        "settings": {"waiver_bid": int(Y._f(bid))} if bid not in (None, "") else None,
                        "metadata": {"yahoo_type": kind}})
        return out

    # ------------------------------------------------------------------ Yahoo's own extras
    def free_agents(self, key: str) -> list[str]:
        """Yahoo's free agents (``status=FA``, Yahoo's rank order, the first 25) as Sleeper ids."""
        lk = self._lk(key)
        rows = [Y.player_row(p) for p in self.client.free_agents(lk)]
        tr = self.translate(lk, {r["yahoo_id"]: r for r in rows if r["yahoo_id"]})
        return [tr[r["yahoo_id"]][0] for r in rows if r["yahoo_id"] in tr]

    def standings(self, key: str) -> list[dict]:
        lk = self._lk(key)
        return [{"roster_id": rid, **rec} for rid, rec in sorted(self._records(lk).items())]

    def my_leagues(self, session: Y.YahooSession | None = None) -> list[dict]:
        """The signed-in manager's NFL leagues this season: ``[{key, name, season, num_teams, scoring_type, public,
        url, team_key, team_id, team_name, roster_id}]`` (``session``: the request's by default)."""
        token = Y.request_session.set(session) if session is not None else None
        try:
            games = self.client.my_games()
        finally:
            if token is not None:
                Y.request_session.reset(token)
        out = []
        for g in games:
            mine = {str(t.get("team_key") or "").rsplit(".t.", 1)[0]: t for t in g.get("teams") or []}
            for lg in g.get("leagues") or []:
                lk = str(lg.get("league_key") or "")
                if not lk:
                    continue
                t = mine.get(lk) or {}
                tid = Y.team_id_of(str(t["team_key"])) if t.get("team_key") else None
                out.append({"key": PREFIX + lk, "league_key": lk, "name": lg.get("name"),
                            "season": str(lg.get("season") or g.get("season") or ""),
                            "num_teams": int(Y._f(lg.get("num_teams"), 0)) or None,
                            "scoring_type": lg.get("scoring_type"), "public": lg.get("league_type") == "public",
                            "url": lg.get("url"), "team_key": t.get("team_key"), "team_id": tid,
                            "team_name": t.get("name"), "roster_id": tid, "platform": "yahoo"})
        return out
