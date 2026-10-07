"""ESPN leagues in Sleeper's shapes (Wave I-K, IK-1): ``ESPNLeagues`` — the method set of ``platforms.MFLLeagues``.

A league key is ``espn:<league id>`` (this season) or ``espn:<season>:<league id>``. The Router (IK-3) sends every
``espn:`` call here; the rest of League Lab sees Sleeper's league / users / rosters / matchups / transactions dicts:

* **league**: ``roster_positions`` from ESPN's lineup slot counts (``espn_client.slots``: IDP / P / HC slots left out
  and said so), ``scoring_settings`` on Sleeper's keys (``espn_client.scoring``: what is approximated or unpriced is
  on the league card), ``settings`` (the week, playoffs, IR slots, the waiver type and FAAB budget),
  ``platform: "espn"``, ``espn: {league_id, season, url, slots, scoring, unofficial: True}``.
* **users / rosters**: one user and one roster per ESPN team, ``roster_id`` 1..N in ESPN team id order (ESPN's team
  ids can skip numbers), ``owner_id`` = the ESPN team id, ``display_name`` = the owner's ESPN display name, players as
  **Sleeper ids**, ``starters`` seated in the slot ESPN has each one in (Sleeper's array: one id per starting slot,
  "0" for an empty slot), ``reserve`` = ESPN's IR slot, the record and points from ESPN's standings.
* **matchups**: ESPN's schedule (``mMatchupScore``): each matchup period's pairs and the points of the week.
* **transactions**: ESPN's executed adds, drops and trades of a week (``mTransactions2``), Sleeper's shape.
* **free agents**: as for every provider, the Waivers screen takes the players no roster carries
  (``anyleague.free_agents``); ``free_agents(key)`` also gives ESPN's own list (``kona_player_info``) mapped.

Player ids: a D/ST (ESPN id ``-16000 - proTeamId``) is the team's Sleeper defense (its team code); else ESPN id ->
``gsis_id`` through the id table (``player_ids.espn_to_gsis``) -> the Sleeper id of that gsis in the same table, else
through ``platforms.GSIS_LOOKUP`` (the API's ``analytics.player_id_map``); else a unique name + position match in
Sleeper's directory (reported as "name"); else the player stays as ``espn:<id>`` with ESPN's name, position and team
(unvalued, listed in ``unmapped``) — a starter is never dropped. Kickers are players like any other.
"""

from __future__ import annotations

import math
import threading
from collections.abc import Callable
from typing import Any

from . import espn_client as E
from . import player_ids as PI
from . import provider_trouble  # ---- IP-5 fix round
from .sleeper_client import LeagueNotFound

PREFIX = E.PREFIX
TX_TYPES = {"FREEAGENT": "free_agent", "WAIVER": "waiver", "TRADE_ACCEPT": "trade"}


def _norm(name: str) -> str:
    from .platforms import _norm as norm  # MFL's name normaliser (the same rule for both providers)
    return norm(name)


class ESPNLeagues:
    """ESPN leagues in Sleeper's shapes (see the module docstring). ``directory``: Sleeper's player directory."""

    def __init__(self, client: E.ESPN, directory: Callable[[], dict]) -> None:
        self.client = client
        self.directory = directory
        self.extra_players: dict[str, dict] = {}       # "espn:<id>" -> a directory-shaped row (unmapped players)
        self.mapping: dict[str, dict] = {}             # "<lid>@<season>" -> {espn id: (sleeper id, how)}
        self.info: dict[str, dict] = {}                # espn id -> {name, position, team, injury} as ESPN gave it
        self._name_index: tuple[int, dict[tuple[str, str], list[str]]] | None = None
        self._gsis_sleeper: tuple[int, dict[str, str]] | None = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ keys
    def ids(self, key: str) -> tuple[str, int]:
        """(ESPN league id, season) of a key (``espn:4242`` -> this season)."""
        lid, season = E.parse_key(key)
        return lid, self.client.season_of(season)

    def _slot(self, key: str) -> str:
        lid, season = self.ids(key)
        return f"{lid}@{season}"

    def _key(self, lid: str, season: int) -> str:
        return E.make_key(lid, None if season == self.client.season else season)

    def require_access(self, key: str) -> None:
        """``LeaguePrivate`` when the league is known private and this request's cookies did not read it."""
        lid, season = self.ids(key)
        self.client.require_access(lid, season)

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

    def _sleeper_of_gsis(self, tab: PI.IdTable) -> dict[str, str]:
        if self._gsis_sleeper is None or self._gsis_sleeper[0] != id(tab):
            inv: dict[str, str] = {}
            dup: set[str] = set()
            for sid, g in tab.sleeper_gsis.items():
                if g in inv and inv[g] != sid:
                    dup.add(g)
                inv.setdefault(g, sid)
            for g in dup:                                  # one gsis, two Sleeper ids: not decided here
                inv.pop(g, None)
            self._gsis_sleeper = (id(tab), inv)
        return self._gsis_sleeper[1]

    def _remember(self, player: dict | None, pid: Any = None) -> None:
        if not isinstance(player, dict):
            return
        i = str(player.get("id") if player.get("id") is not None else pid)
        if not i or i == "None":
            return
        team = E.PRO_TEAMS.get(int(player.get("proTeamId") or 0)) if str(player.get("proTeamId") or "0").lstrip("-").isdigit() else None
        self.info[i] = {"name": player.get("fullName") or " ".join(x for x in (player.get("firstName"), player.get("lastName")) if x),
                        "position": E.player_position(player), "team": team,
                        "injury": E.INJURY.get(str(player.get("injuryStatus") or "").upper())}

    def translate(self, lid: str, ids: list[str], season: int | None = None, *,
                  record: bool = True) -> dict[str, tuple[str, str]]:
        """ESPN player ids -> (Sleeper id or ``espn:<id>``, how: defense | table | gsis | name | unmapped).
        ``record``: count them in the league's ``mapped_by`` / ``unmapped`` (the rostered players; free agents and
        transactions' players get their directory rows without being counted)."""
        from . import platforms
        season = self.client.season_of(season)
        out: dict[str, tuple[str, str]] = {}
        tab = PI.table()
        g2s = self._sleeper_of_gsis(tab)
        need_db: dict[str, str] = {}
        rest: list[str] = []
        for raw in ids:
            i = str(raw)
            team = E.dst_team(i)
            if team:
                out[i] = (team, "defense")
                continue
            g = tab.espn_to_gsis(i)
            if g and g2s.get(g):
                out[i] = (g2s[g], "table")
                continue
            if g:
                need_db[i] = g
            rest.append(i)
        if need_db and platforms.GSIS_LOOKUP is not None:
            try:
                got = platforms.GSIS_LOOKUP(sorted(set(need_db.values()))) or {}
            except Exception:  # noqa: BLE001 - the database step is a nicety: the next steps still run
                got = {}
            for i, g in need_db.items():
                if got.get(g):
                    out[i] = (str(got[g]), "gsis")
        rest = [i for i in rest if i not in out]
        idx = self._index() if rest else {}
        for i in rest:
            p = self.info.get(i) or {}
            pos = p.get("position")
            hits = idx.get((_norm(str(p.get("name") or "")), str(pos))) if p.get("name") and pos else None
            if hits and len(hits) == 1:
                out[i] = (hits[0], "name")
                continue
            key = f"{PREFIX}{i}"
            self.extra_players[key] = {"player_id": key, "player_key": key,
                                       "full_name": p.get("name") or f"ESPN player {i}", "position": pos,
                                       "fantasy_positions": [pos] if pos else None, "team": p.get("team"),
                                       "status": "Active", "active": True, "injury_status": p.get("injury"),
                                       "espn_id": i}
            out[i] = (key, "unmapped")
        if record:
            with self._lock:
                self.mapping.setdefault(f"{E.check_league(lid)}@{season}", {}).update(out)
        return out

    def unmapped(self, key: str) -> list[dict]:
        """The rostered ESPN players with no Sleeper id: ``{espn_id, name, position}``."""
        rows = []
        for i, (sid, how) in sorted(self.mapping.get(self._slot(key), {}).items()):
            if how == "unmapped":
                p = self.extra_players.get(sid) or {}
                rows.append({"espn_id": i, "name": p.get("full_name"), "position": p.get("position")})
        return rows

    def mapped_by(self, key: str) -> dict[str, int]:
        out: dict[str, int] = {}
        for _sid, how in self.mapping.get(self._slot(key), {}).values():
            out[how] = out.get(how, 0) + 1
        return out

    # ------------------------------------------------------------------ helpers
    def _settings(self, lid: str, season: int) -> dict:
        return dict((self.client.settings(lid, season) or {}).get("settings") or {})

    def week(self, lid_or_key: str) -> int:
        """ESPN's current scoring period (the NFL week), capped at the league's final one; 1 before the season."""
        if E.is_espn(lid_or_key):
            lid, season = self.ids(lid_or_key)
        else:
            lid, season = E.check_league(lid_or_key), self.client.season
        st = self.client.status(lid, season) or {}
        status = st.get("status") or {}
        w = st.get("scoringPeriodId") or status.get("currentMatchupPeriod") or status.get("latestScoringPeriod") or 1
        try:
            w = int(w)
        except (TypeError, ValueError):
            w = 1
        final = status.get("finalScoringPeriod")
        if isinstance(final, int) and final > 0:
            w = min(w, final)
        return max(1, w)

    def _team_ids(self, lid: str, season: int) -> list[int]:
        teams = (self.client.teams(lid, season) or {}).get("teams") or []
        return sorted(int(t["id"]) for t in teams if isinstance(t, dict) and str(t.get("id", "")).lstrip("-").isdigit())

    def _rid_of(self, lid: str, season: int) -> dict[int, int]:
        return {tid: i for i, tid in enumerate(self._team_ids(lid, season), 1)}

    def roster_id_of(self, key: str, espn_team_id: Any) -> int | None:
        """The roster id of an ESPN team id (a link's ``teamId``), None when the league has no such team."""
        lid, season = self.ids(key)
        try:
            return self._rid_of(lid, season).get(int(espn_team_id))
        except (TypeError, ValueError):
            return None

    def team_id_of(self, key: str, roster_id: int) -> int | None:
        lid, season = self.ids(key)
        return {r: t for t, r in self._rid_of(lid, season).items()}.get(int(roster_id))

    @staticmethod
    def team_name(t: dict) -> str:
        name = str(t.get("name") or "").strip()
        if not name:
            name = " ".join(str(x).strip() for x in (t.get("location"), t.get("nickname")) if x).strip()
        return name or f"Team {t.get('abbrev') or t.get('id')}"

    def league_name(self, key: str) -> str:
        lid, season = self.ids(key)
        return str(self._settings(lid, season).get("name") or f"ESPN league {lid}").strip()

    def url(self, key: str, team_id: int | None = None) -> str:
        lid, season = self.ids(key)
        if team_id is not None:
            return f"https://fantasy.espn.com/football/team?leagueId={lid}&teamId={int(team_id)}&seasonId={season}"
        return f"https://fantasy.espn.com/football/league?leagueId={lid}&seasonId={season}"

    # ------------------------------------------------------------------ Sleeper-shaped calls
    def league(self, key: str) -> dict:
        lid, season = self.ids(key)
        raw = self.client.settings(lid, season) or {}
        st = dict(raw.get("settings") or {})
        slots, slot_note = E.slots(st)
        sc, report = E.scoring(st)
        if slot_note.get("unknown"):           # not IDP (the card says those): a punter / head coach / team-QB spot
            report = {**report, "approximated": [*report.get("approximated", []),
                                                 "lineup: ESPN's " + ", ".join(slot_note["unknown"])
                                                 + " spots are left out (not projected here)"]}
        try:
            week = self.week(key)
        except LeagueNotFound:
            week = 1
        except (E.ESPNUnavailable, E.ESPNBusy) as exc:     # ---- IP-5 fix round: refused → raised, never "week 1"
            if not provider_trouble.fixture_gap(exc):
                raise
            week = 1
        sched = st.get("scheduleSettings") or {}
        acq = st.get("acquisitionSettings") or {}
        try:
            status = (self.client.status(lid, season) or {}).get("status") or {}
        except LeagueNotFound:
            status = {}
        except (E.ESPNUnavailable, E.ESPNBusy) as exc:     # ---- IP-5 fix round
            if not provider_trouble.fixture_gap(exc):
                raise
            status = {}
        n = int(st.get("size") or 0) or len(self._team_ids(lid, season))
        reg = int(sched.get("matchupPeriodCount") or 0)
        periods = sched.get("matchupPeriods") or {}
        playoff_start = 0
        if reg and str(reg + 1) in periods and periods[str(reg + 1)]:
            playoff_start = int(min(periods[str(reg + 1)]))
        elif reg:
            playoff_start = reg * int(sched.get("matchupPeriodLength") or 1) + 1
        faab = bool(acq.get("isUsingAcquisitionBudget"))
        waiver_type = 2 if faab else (1 if acq.get("waiverOrderReset") else 0)
        out = {"league_id": self._key(lid, season),
               "name": str(st.get("name") or f"ESPN league {lid}").strip(), "season": str(season),
               "season_type": "regular", "sport": "nfl", "status": "in_season", "total_rosters": n,
               "roster_positions": slots, "scoring_settings": sc,
               "settings": {"playoff_week_start": playoff_start, "playoff_teams": int(sched.get("playoffTeamCount") or 0),
                            "playoff_round_type": 0, "leg": week, "last_scored_leg": max(0, week - 1), "num_teams": n,
                            "start_week": int(status.get("firstScoringPeriod") or 1), "type": 0, "taxi_slots": 0,
                            "reserve_slots": int(slot_note.get("ir") or 0), "waiver_type": waiver_type,
                            **({"waiver_budget": int(acq.get("acquisitionBudget") or 0)} if faab else {}),
                            "trade_deadline": None},
               "platform": "espn",
               "espn": {"league_id": lid, "season": season, "url": self.url(key), "unofficial": True,
                        "public": (st.get("isPublic") if isinstance(st.get("isPublic"), bool) else None),
                        "slots": slot_note, "scoring": report,
                        "waivers": {"type": acq.get("acquisitionType"), "faab": faab,
                                    "days": list(acq.get("waiverProcessDays") or []),
                                    "hour": acq.get("waiverProcessHour")}}}
        return out

    def users(self, key: str) -> list[dict]:
        lid, season = self.ids(key)
        data = self.client.teams(lid, season) or {}
        members = {str(m.get("id")): m for m in data.get("members") or [] if isinstance(m, dict)}
        out = []
        for t in sorted((t for t in data.get("teams") or [] if isinstance(t, dict)), key=lambda t: int(t.get("id") or 0)):
            owner = members.get(str(t.get("primaryOwner") or (t.get("owners") or [None])[0]))
            display = str((owner or {}).get("displayName") or "").strip() or None
            out.append({"user_id": str(t.get("id")), "display_name": display,
                        "metadata": {"team_name": self.team_name(t)}, "league_id": self._key(lid, season),
                        "platform": "espn"})
        return out

    def rosters(self, key: str) -> list[dict]:
        lid, season = self.ids(key)
        rid_of = self._rid_of(lid, season)
        teams = {int(t["id"]): t for t in (self.client.teams(lid, season) or {}).get("teams") or []
                 if isinstance(t, dict) and str(t.get("id", "")).lstrip("-").isdigit()}
        data = self.client.rosters(lid, season) or {}
        lg = self.league(key)
        slot_list = [s for s in lg["roster_positions"] if s not in ("BN", "IR", "TAXI")]
        entries_by: dict[int, list[dict]] = {}
        ids: list[str] = []
        for t in data.get("teams") or []:
            if not isinstance(t, dict) or not str(t.get("id", "")).lstrip("-").isdigit():
                continue
            ents = [e for e in ((t.get("roster") or {}).get("entries") or []) if isinstance(e, dict)]
            entries_by[int(t["id"])] = ents
            for e in ents:
                pid = e.get("playerId", (e.get("playerPoolEntry") or {}).get("id"))
                self._remember((e.get("playerPoolEntry") or {}).get("player"), pid)
                ids.append(str(pid))
        tr = self.translate(lid, sorted(set(ids)), season)
        out = []
        for tid, rid in rid_of.items():
            ents = entries_by.get(tid, [])
            players, reserve = [], []
            seated: dict[str, list[str]] = {}
            for e in ents:
                pid = str(e.get("playerId", (e.get("playerPoolEntry") or {}).get("id")))
                sid = tr[pid][0]
                players.append(sid)
                slot = E.slot_name(e.get("lineupSlotId"))
                if slot == "IR":
                    reserve.append(sid)
                elif slot not in (None, "BN"):
                    seated.setdefault(slot, []).append(sid)
            starters = [seated[s].pop(0) if seated.get(s) else "0" for s in slot_list]
            if not any(x != "0" for x in starters):
                starters = []
            rec = (((teams.get(tid) or {}).get("record") or {}).get("overall") or {})
            pf, pa = float(rec.get("pointsFor") or 0), float(rec.get("pointsAgainst") or 0)
            tc = (teams.get(tid) or {}).get("transactionCounter") or {}
            out.append({"league_id": self._key(lid, season), "roster_id": rid, "owner_id": str(tid), "co_owners": None,
                        "players": players, "starters": starters, "reserve": reserve or None, "taxi": None,
                        "settings": {"wins": int(rec.get("wins") or 0), "losses": int(rec.get("losses") or 0),
                                     "ties": int(rec.get("ties") or 0), "fpts": int(math.floor(pf)),
                                     "fpts_decimal": int(round((pf - math.floor(pf)) * 100)),
                                     "fpts_against": int(math.floor(pa)),
                                     "fpts_against_decimal": int(round((pa - math.floor(pa)) * 100)),
                                     "waiver_position": (teams.get(tid) or {}).get("waiverRank"),
                                     "waiver_budget_used": int(tc.get("acquisitionBudgetSpent") or 0),
                                     "total_moves": int(tc.get("acquisitions") or 0)},
                        "espn_team_id": tid})
        return out

    def _period_of(self, lid: str, season: int, week: int) -> int:
        periods = (self._settings(lid, season).get("scheduleSettings") or {}).get("matchupPeriods") or {}
        for p, weeks in periods.items():
            if int(week) in [int(w) for w in weeks or []]:
                return int(p)
        return int(week)

    def matchups(self, key: str, week: int) -> list[dict]:
        lid, season = self.ids(key)
        rid_of = self._rid_of(lid, season)
        period = self._period_of(lid, season, int(week))
        sched = [m for m in (self.client.schedule(lid, season) or {}).get("schedule") or []
                 if isinstance(m, dict) and int(m.get("matchupPeriodId") or 0) == period]
        out = []
        for i, m in enumerate(sorted(sched, key=lambda m: int(m.get("id") or 0)), 1):
            sides = [m.get(s) for s in ("home", "away") if isinstance(m.get(s), dict)]
            for side in sides:
                rid = rid_of.get(int(side.get("teamId") or -1))
                if rid is None:
                    continue
                by = side.get("pointsByScoringPeriod") or {}
                pts = by.get(str(int(week)), side.get("totalPoints") if not by else 0.0)
                try:
                    pts = float(pts or 0.0)
                except (TypeError, ValueError):
                    pts = 0.0
                out.append({"roster_id": rid, "matchup_id": i if len(sides) == 2 else None, "points": pts,
                            "starters": [], "players": []})
        return sorted(out, key=lambda r: r["roster_id"])

    def season_matchups(self, key: str, through_week: int) -> dict[int, list[dict]]:
        return {w: self.matchups(key, w) for w in range(1, int(through_week) + 1)}

    def transactions(self, key: str, round_: int) -> list[dict]:
        """A week's executed adds, drops and trades in Sleeper's transaction shape."""
        lid, season = self.ids(key)
        rid_of = self._rid_of(lid, season)
        data = self.client.transactions(lid, season, int(round_)) or {}
        txs = [t for t in data.get("transactions") or [] if isinstance(t, dict)
               and str(t.get("status") or "").upper() == "EXECUTED" and str(t.get("type") or "").upper() in TX_TYPES]
        ids = sorted({str(it.get("playerId")) for t in txs for it in t.get("items") or [] if isinstance(it, dict)
                      and str(it.get("type") or "").upper() in ("ADD", "DROP", "TRADE") and it.get("playerId") is not None})
        tr = self.translate(lid, ids, season, record=False) if ids else {}
        out = []
        for t in txs:
            adds: dict[str, int | None] = {}
            drops: dict[str, int | None] = {}
            for it in t.get("items") or []:
                kind = str(it.get("type") or "").upper()
                pid = it.get("playerId")
                if pid is None or kind not in ("ADD", "DROP", "TRADE"):
                    continue
                sid = tr[str(pid)][0]
                to, frm = rid_of.get(int(it.get("toTeamId") or -1)), rid_of.get(int(it.get("fromTeamId") or -1))
                if kind in ("ADD", "TRADE") and to is not None:
                    adds[sid] = to
                if kind in ("DROP", "TRADE") and frm is not None:
                    drops[sid] = frm
            if not adds and not drops:
                continue
            rids = sorted({r for r in (*adds.values(), *drops.values()) if r is not None}
                          | ({rid_of[int(t["teamId"])]} if str(t.get("teamId", "")).isdigit() and int(t["teamId"]) in rid_of else set()))
            when = t.get("processDate") or t.get("acceptedDate") or t.get("proposedDate")
            typ = TX_TYPES[str(t.get("type")).upper()]
            out.append({"transaction_id": str(t.get("id")), "type": typ, "status": "complete",
                        "leg": int(t.get("scoringPeriodId") or round_), "roster_ids": rids, "adds": adds or None,
                        "drops": drops or None, "draft_picks": [], "waiver_budget": [], "creator": None,
                        "created": int(when) if when else None, "status_updated": int(when) if when else None,
                        "settings": ({"waiver_bid": int(t["bidAmount"])} if typ == "waiver" and t.get("bidAmount") else None),
                        "metadata": None, "consenter_ids": rids})
        return sorted(out, key=lambda x: (x["created"] or 0, x["transaction_id"]))

    def free_agents(self, key: str, limit: int = E.FREE_AGENT_LIMIT) -> list[str]:
        """ESPN's own free agents and waiver players (most owned first), as Sleeper ids / ``espn:<id>``."""
        lid, season = self.ids(key)
        data = self.client.free_agents(lid, season, self.week(key), limit) or {}
        ids = []
        for p in data.get("players") or []:
            if not isinstance(p, dict):
                continue
            pl = p.get("player") if isinstance(p.get("player"), dict) else None
            pid = p.get("id", (pl or {}).get("id"))
            if pid is None:
                continue
            self._remember(pl, pid)
            ids.append(str(pid))
        tr = self.translate(lid, ids, season, record=False) if ids else {}
        return [tr[i][0] for i in ids]
