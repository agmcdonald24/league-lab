"""League keys -> the client that serves them (Wave I-0, I0-B).

A league key is a Sleeper league id (bare digits, as before) or a platform-prefixed key: ``mfl:21861`` is
MyFantasyLeague league 21861. ``anyleague.sleeper()`` returns a ``Router`` that answers every call the rest of the
code makes (``league``, ``rosters``, ``users``, ``matchups``, ``season_matchups``, ``transactions``, ``players``, …)
in **Sleeper's shapes** whatever the platform, so the API, the lineup solver and every screen run unchanged:

* a Sleeper key goes to the ``Sleeper`` client untouched;
* an ``mfl:`` key goes to ``MFLLeagues``, which reads MFL through ``mfl_client.MFL`` (its own caches and budget) and
  translates: the league (slots, scoring keys, playoff week, the week MFL is on), franchises -> users and rosters
  (``roster_id`` 1..N in franchise order, players as **Sleeper ids**, starters from the week's live scoring, IR and
  taxi, the record from the standings), the schedule -> matchups.

Player ids: MFL id -> ``sleeper_id`` through the id table (``player_ids``), else MFL -> ``gsis_id`` -> Sleeper id
through ``GSIS_LOOKUP`` (the API installs ``analytics.player_id_map``), else a defense by its team code, else a
unique name + position match in Sleeper's directory (reported as such), else the player stays on the roster as
``mfl:<id>`` with his MFL name and position (unvalued, reported in ``unmapped``) — a starter is never dropped.
"""

from __future__ import annotations

import html
import re
import threading
from collections.abc import Callable
from typing import Any

from . import mfl_client as M
from . import player_ids as PI
from .sleeper_client import LeagueNotFound, Sleeper
from .sleeper_client import check_id as sleeper_check_id

PREFIX = "mfl:"
# ---- IC-2 (Wave I-C): MFL's team units. A rostered TMQB / TMPK is a "player" (one per NFL team) with no gsis id:
# a directory row under ``mfl:<id>`` with its NFL team (Sleeper's code), valued from the team's quarterbacks / kicker
# (anyleague prices it); a TMDEF is a team defense, mapped like ``Def`` (its Sleeper id is the team code).
UNIT_POSITIONS = frozenset({"TMQB", "TMPK"})
UNIT_WORDS = {"TMQB": "QB", "TMPK": "K"}


def unit_name(name: str | None, position: str, team: str | None) -> str:
    """"Kansas City Chiefs QB": MFL's name ("Chiefs, Kansas City" or "Kansas City Chiefs TMQB") as first-last, the
    unit word (QB / K) in place of MFL's code."""
    base = _first_last(str(name or "")).strip()
    base = re.sub(rf"\s*\b(?:{position}|TM\w+)\b\s*$", "", base, flags=re.I).strip()
    if not base:
        base = team or "Team"
    word = UNIT_WORDS.get(position, position)
    return base if base.upper().endswith(f" {word}") else f"{base} {word}"


# the 32 NFL teams (Sleeper's codes) and their names: an unrostered unit (a free agent) is listed under
# ``mfl:<TMQB|TMPK>-<team>`` (its MFL id is only known once a roster carries it)
NFL_TEAMS = {"ARI": "Arizona Cardinals", "ATL": "Atlanta Falcons", "BAL": "Baltimore Ravens", "BUF": "Buffalo Bills",
             "CAR": "Carolina Panthers", "CHI": "Chicago Bears", "CIN": "Cincinnati Bengals", "CLE": "Cleveland Browns",
             "DAL": "Dallas Cowboys", "DEN": "Denver Broncos", "DET": "Detroit Lions", "GB": "Green Bay Packers",
             "HOU": "Houston Texans", "IND": "Indianapolis Colts", "JAX": "Jacksonville Jaguars", "KC": "Kansas City Chiefs",
             "LAC": "Los Angeles Chargers", "LAR": "Los Angeles Rams", "LV": "Las Vegas Raiders", "MIA": "Miami Dolphins",
             "MIN": "Minnesota Vikings", "NE": "New England Patriots", "NO": "New Orleans Saints", "NYG": "New York Giants",
             "NYJ": "New York Jets", "PHI": "Philadelphia Eagles", "PIT": "Pittsburgh Steelers", "SEA": "Seattle Seahawks",
             "SF": "San Francisco 49ers", "TB": "Tampa Bay Buccaneers", "TEN": "Tennessee Titans", "WAS": "Washington Commanders"}


def unit_row(mfl_player_id: str, position: str, info: dict) -> dict:
    """The directory row of a team unit (INTERFACES.md § IC-2): player_id / player_key ``mfl:<id>``, position TMQB /
    TMPK, the Sleeper team code, the unit's name; ``unit`` True; no gsis id."""
    key = f"{PREFIX}{mfl_player_id}"
    team = M.defense_sleeper_id(info.get("team")) if info.get("team") else None
    name = unit_name(info.get("name"), position, team)
    return {"player_id": key, "player_key": key, "full_name": name, "player_name": name, "position": position,
            "fantasy_positions": [position], "team": team, "status": "Active", "active": True, "injury_status": None,
            "mfl_id": str(mfl_player_id), "unit": True}
# ---- end IC-2
# gsis ids -> Sleeper ids (the API sets it to read analytics.player_id_map); None: that step is skipped
GSIS_LOOKUP: Callable[[list[str]], dict[str, str]] | None = None


def is_mfl(key: Any) -> bool:
    return str(key or "").strip().lower().startswith(PREFIX)


def platform(key: Any) -> str:
    return "mfl" if is_mfl(key) else "sleeper"


def check_key(key: Any) -> str:
    """A league key: Sleeper digits, or ``mfl:<digits>`` (lower-cased prefix). Anything else is LeagueNotFound."""
    s = str(key or "").strip()
    if is_mfl(s):
        return PREFIX + M.check_league(s[len(PREFIX):])
    return sleeper_check_id(s)


def mfl_id(key: str) -> str:
    return M.check_league(str(key).strip()[len(PREFIX):])


_SUFFIX = re.compile(r"\b(jr|sr|ii|iii|iv|v)\b")


def _norm(name: str) -> str:
    s = html.unescape(name or "").lower()
    if "," in s:                                   # MFL: "Last, First"
        last, first = s.split(",", 1)
        s = f"{first} {last}"
    s = _SUFFIX.sub(" ", re.sub(r"[^a-z ]", " ", s.replace("'", "").replace(".", "")))
    return " ".join(s.split())


def _first_last(name: str) -> str:
    s = html.unescape(name or "").strip()
    if "," in s:
        last, first = s.split(",", 1)
        return f"{first.strip()} {last.strip()}"
    return s


class MFLLeagues:
    """MyFantasyLeague leagues in Sleeper's shapes (see the module docstring). ``directory``: Sleeper's player
    directory (the name fallback and the names of the players it maps)."""

    def __init__(self, client: M.MFL, directory: Callable[[], dict]) -> None:
        self.client = client
        self.directory = directory
        self.extra_players: dict[str, dict] = {}       # "mfl:<id>" -> a directory-shaped row (unmapped players)
        self.mapping: dict[str, dict] = {}             # league id -> {mfl id: (sleeper id, how)}
        self._name_index: tuple[int, dict[tuple[str, str], list[str]]] | None = None
        self._lock = threading.Lock()

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

    def translate(self, lid: str, ids: list[str]) -> dict[str, tuple[str, str]]:
        """MFL ids -> (Sleeper id or ``mfl:<id>``, how: table | gsis | defense | name | unmapped)."""
        out: dict[str, tuple[str, str]] = {}
        need_info: list[str] = []
        gsis_need: dict[str, str] = {}
        tab = PI.table()
        for i in ids:
            sid = tab.mfl_to_sleeper(i)
            if sid:
                out[i] = (sid, "table")
                continue
            g = tab.mfl_to_gsis(i)
            if g:
                gsis_need[i] = g
            need_info.append(i)
        if gsis_need and GSIS_LOOKUP is not None:
            try:
                got = GSIS_LOOKUP(sorted(set(gsis_need.values()))) or {}
            except Exception:  # noqa: BLE001 - the database fallback is a nicety: the next steps still run
                got = {}
            for i, g in gsis_need.items():
                if got.get(g):
                    out[i] = (str(got[g]), "gsis")
        rest = [i for i in need_info if i not in out]
        if rest:
            try:
                info = {str(p.get("id")): p for p in self.client.players(rest)}
            except (M.MFLUnavailable, M.MFLBusy, LeagueNotFound):
                info = {}
            idx = self._index() if any(str((info.get(i) or {}).get("position")) not in ("Def", "TMDEF", *UNIT_POSITIONS)
                                       for i in rest) else {}
            for i in rest:
                p = info.get(i) or {}
                pos = M.POS.get(str(p.get("position") or ""), str(p.get("position") or "") or None)
                if pos in UNIT_POSITIONS:          # ---- IC-2: a team unit (TMQB / TMPK) is a player of its own
                    key = f"{PREFIX}{i}"
                    self.extra_players[key] = unit_row(i, pos, p)
                    out[i] = (key, "unit")
                    continue
                if pos == "DEF":
                    tid = M.defense_sleeper_id(p.get("team"))
                    if tid:
                        out[i] = (tid, "defense")
                        continue
                hits = idx.get((_norm(str(p.get("name") or "")), str(pos))) if p.get("name") and pos else None
                if hits and len(hits) == 1:
                    out[i] = (hits[0], "name")
                    continue
                key = f"{PREFIX}{i}"
                self.extra_players[key] = {"player_id": key, "full_name": _first_last(str(p.get("name") or f"MFL player {i}")),
                                           "position": pos, "fantasy_positions": [pos] if pos else None,
                                           "team": M.defense_sleeper_id(p.get("team")) if p.get("team") else None,
                                           "status": "Active", "active": True, "injury_status": None, "mfl_id": i}
                out[i] = (key, "unmapped")
        with self._lock:
            self.mapping.setdefault(lid, {}).update(out)
        return out

    def register_units(self, positions: set[str] | frozenset[str]) -> int:
        """IC-2: every NFL team's unit of each position the league starts (TMQB / TMPK) in the directory, so the free
        agents include the unrostered ones; a team whose unit a roster carries keeps that row (its MFL id). Returns
        how many were added."""
        have = {(r.get("position"), r.get("team")) for r in self.extra_players.values() if r.get("unit")}
        n = 0
        for pos in sorted(set(positions) & UNIT_POSITIONS):
            for team, name in NFL_TEAMS.items():
                if (pos, team) in have:
                    continue
                key = f"{PREFIX}{pos}-{team}"
                if key not in self.extra_players:
                    row = unit_row(f"{pos}-{team}", pos, {"name": name, "team": team})
                    row["mfl_id"] = None
                    self.extra_players[key] = row
                    n += 1
        return n

    def unmapped(self, key: str) -> list[dict]:
        """The rostered MFL players with no Sleeper id (``{mfl_id, name, position}``), and those matched by name."""
        lid = mfl_id(key)
        rows = []
        for i, (sid, how) in sorted(self.mapping.get(lid, {}).items()):
            if how == "unmapped":
                p = self.extra_players.get(sid) or {}
                rows.append({"mfl_id": i, "name": p.get("full_name"), "position": p.get("position")})
        return rows

    def mapped_by(self, key: str) -> dict[str, int]:
        out: dict[str, int] = {}
        for _sid, how in self.mapping.get(mfl_id(key), {}).values():
            out[how] = out.get(how, 0) + 1
        return out

    # ------------------------------------------------------------------ Sleeper-shaped calls
    def week(self, lid: str) -> int:
        fr = self.client.rosters(lid)
        w = next((f.get("week") for f in fr if f.get("week")), None)
        return int(w) if w else 1

    def league(self, key: str) -> dict:
        lid = mfl_id(key)
        lg = self.client.league(lid)
        rules = self.client.rules(lid)
        slots, slot_note = M.slots(lg)
        sc, report = M.scoring(rules)
        try:
            week = self.week(lid)
        except LeagueNotFound:
            week = 1
        n = len(M.franchise_ids(lg))
        last_reg = int(lg.get("lastRegularSeasonWeek") or 0)
        end = int(lg.get("endWeek") or 0)
        rounds = max(0, end - last_reg) if last_reg and end else 0
        host = self.client.hosts.get(lid) or str(lg.get("baseURL") or "https://www.myfantasyleague.com").rstrip("/")
        return {"league_id": PREFIX + lid, "name": html.unescape(str(lg.get("name") or f"MFL league {lid}")).strip(),
                "season": str(self.client.year), "season_type": "regular", "sport": "nfl", "status": "in_season",
                "total_rosters": n, "roster_positions": slots, "scoring_settings": sc,
                # ---- IC-2 for IC-1 (INTERFACES.md): the league's ScoringSpec as JSON when the compiler gives one
                **({"scoring_spec": report["spec"]} if isinstance(report, dict) and report.get("spec") else {}),
                "settings": {"playoff_week_start": (last_reg + 1) if last_reg and rounds else 0,
                             "playoff_teams": 2 ** rounds if rounds else 0, "playoff_round_type": 0,
                             "leg": week, "last_scored_leg": max(0, week - 1), "num_teams": n,
                             "start_week": int(lg.get("startWeek") or 1), "type": 0,
                             "taxi_slots": int(lg.get("taxiSquad") or 0), "reserve_slots": int(lg.get("injuredReserve") or 0)},
                "platform": "mfl",
                "mfl": {"league_id": lid, "url": f"{host}/{self.client.year}/home/{lid}", "slots": slot_note,
                        "scoring": report}}

    def users(self, key: str) -> list[dict]:
        lid = mfl_id(key)
        lg = self.client.league(lid)
        try:
            st = self.client.standings(lid)
        except (M.MFLUnavailable, M.MFLBusy, LeagueNotFound):
            st = []
        names = M.franchise_names(lg, st)
        owners = M.franchise_owners(lg)          # ---- IC-4: the manager's name when MFL shares it, else None
        return [{"user_id": fid, "display_name": owners.get(fid), "metadata": {"team_name": names.get(fid)},
                 "league_id": PREFIX + lid, "platform": "mfl"} for fid in M.franchise_ids(lg)]

    def _rid_of(self, lid: str) -> dict[str, int]:
        return {fid: i for i, fid in enumerate(M.franchise_ids(self.client.league(lid)), 1)}

    def rosters(self, key: str) -> list[dict]:
        lid = mfl_id(key)
        rid_of = self._rid_of(lid)
        fr = self.client.rosters(lid)
        week = self.week(lid)
        ids = sorted({str(p.get("id")) for f in fr for p in M._as_list(f.get("player"))})
        starters_mfl: dict[str, list[str]] = {}
        try:
            starters_mfl = M.starters_by_franchise(self.client.live_scoring(lid, week), None)
        except (M.MFLUnavailable, M.MFLBusy, LeagueNotFound):
            pass
        if len(starters_mfl) < len(fr) and week > 1:
            try:
                prev = M.starters_by_franchise(None, self.client.weekly_results(lid, week - 1))
                for fid, s in prev.items():
                    starters_mfl.setdefault(fid, s)
            except (M.MFLUnavailable, M.MFLBusy, LeagueNotFound):
                pass
        ids = sorted(set(ids) | {i for s in starters_mfl.values() for i in s})
        tr = self.translate(lid, ids)
        try:
            settings = M.standings_settings(self.client.standings(lid))
        except (M.MFLUnavailable, M.MFLBusy, LeagueNotFound):
            settings = {}
        # ---- IC-2: Sleeper's starters array is ordered like the starting slots ("0" = empty); MFL's lists ids only, so
        # each starter is seated in the narrowest slot that admits him (the lock rule reads the slot from it)
        from .lineup import align_starters, parse_slots
        slot_list, _ = M.slots(self.client.league(lid))
        d = self.directory()
        unit_pos = set().union(*(x.elig for x in parse_slots(slot_list)[0])) & UNIT_POSITIONS
        if unit_pos:
            self.register_units(unit_pos)

        def positions_of(sid: str) -> list[str]:
            row = self.extra_players.get(sid) or d.get(sid) or {}
            return list(row.get("fantasy_positions") or ([row["position"]] if row.get("position") else []))
        # ---- end IC-2
        out = []
        for f in fr:
            fid = str(f.get("id"))
            if fid not in rid_of:
                continue
            players = M._as_list(f.get("player"))
            sid = [tr[str(p.get("id"))][0] for p in players]
            reserve = [tr[str(p.get("id"))][0] for p in players if str(p.get("status")) == "INJURED_RESERVE"]
            taxi = [tr[str(p.get("id"))][0] for p in players if str(p.get("status")) == "TAXI_SQUAD"]
            on = set(str(p.get("id")) for p in players)
            starters = [tr[i][0] for i in starters_mfl.get(fid, []) if i in on and i in tr]
            if starters:                                                     # IC-2
                starters = align_starters(slot_list, [(x, positions_of(x)) for x in starters])
            out.append({"league_id": PREFIX + lid, "roster_id": rid_of[fid], "owner_id": fid, "co_owners": None,
                        "players": sid, "starters": starters, "reserve": reserve or None, "taxi": taxi or None,
                        "settings": settings.get(fid, {"wins": 0, "losses": 0, "ties": 0, "fpts": 0, "fpts_decimal": 0})})
        return sorted(out, key=lambda r: r["roster_id"])

    def matchups(self, key: str, week: int) -> list[dict]:
        lid = mfl_id(key)
        return M.weekly_matchups(self.client.schedule(lid), int(week), self._rid_of(lid))

    def season_matchups(self, key: str, through_week: int) -> dict[int, list[dict]]:
        lid = mfl_id(key)
        sched, rid_of = self.client.schedule(lid), self._rid_of(lid)
        return {w: M.weekly_matchups(sched, w, rid_of) for w in range(1, int(through_week) + 1)}

    def transactions(self, key: str, round_: int) -> list[dict]:
        mfl_id(key)
        return []                        # not read from MFL yet (the League screen shows no transactions)


class Router:
    """``anyleague.sleeper()``: the Sleeper client for Sleeper keys, ``MFLLeagues`` for ``mfl:`` keys; anything
    else (``bucket``, ``cache_path``, ``stale_served``…) is the Sleeper client's."""

    def __init__(self, sleeper: Sleeper | None = None, mfl: M.MFL | None = None) -> None:
        self.sleeper = sleeper or Sleeper()
        self._mfl_client = mfl
        self._mfl: MFLLeagues | None = None
        self._lock = threading.Lock()

    @property
    def mfl(self) -> MFLLeagues:
        with self._lock:
            if self._mfl is None:
                self._mfl = MFLLeagues(self._mfl_client or M.MFL(), self.sleeper.players)
            return self._mfl

    @property
    def mfl_fixtures(self) -> str:
        return str((self._mfl_client.fixtures if self._mfl_client else None) or "")

    def __getattr__(self, name: str) -> Any:     # only for what Router does not define
        if name in ("sleeper", "_mfl", "_mfl_client", "_lock"):
            raise AttributeError(name)
        return getattr(self.sleeper, name)

    @property
    def fixtures(self):
        return self.sleeper.fixtures

    @property
    def calls(self) -> int:
        return self.sleeper.calls + (self._mfl.client.calls if self._mfl is not None else 0)

    def league(self, key: str) -> dict:
        return self.mfl.league(key) if is_mfl(key) else self.sleeper.league(key)

    def rosters(self, key: str) -> list[dict]:
        return self.mfl.rosters(key) if is_mfl(key) else self.sleeper.rosters(key)

    def users(self, key: str) -> list[dict]:
        return self.mfl.users(key) if is_mfl(key) else self.sleeper.users(key)

    def matchups(self, key: str, week: int) -> list[dict]:
        return self.mfl.matchups(key, week) if is_mfl(key) else self.sleeper.matchups(key, week)

    def season_matchups(self, key: str, through_week: int) -> dict[int, list[dict]]:
        return self.mfl.season_matchups(key, through_week) if is_mfl(key) else self.sleeper.season_matchups(key, through_week)

    def transactions(self, key: str, round_: int) -> list[dict]:
        return self.mfl.transactions(key, round_) if is_mfl(key) else self.sleeper.transactions(key, round_)

    def players(self) -> dict[str, dict]:
        d = self.sleeper.players()
        extra = self._mfl.extra_players if self._mfl is not None else {}
        if not extra:
            return d
        merged = dict(d)
        merged.update(extra)
        return merged

    def stats(self) -> dict:
        out = self.sleeper.stats()
        if self._mfl is not None:
            out["mfl"] = self._mfl.client.stats()
        return out
