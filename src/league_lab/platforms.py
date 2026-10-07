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

import hashlib  # ---- IL-2: a stable id for an MFL transaction
import html
import importlib  # ---- IK-3: the ESPN / Yahoo adapters, imported when first used
import json  # ---- IL-2
import os  # ---- IK-3
import re
import threading
from collections.abc import Callable
from typing import Any

from . import mfl_client as M
from . import player_ids as PI
from . import provider_trouble  # ---- IP-5 fix round: a refusal is raised, never a default
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


# ---- IK-3 (Wave I-K): four providers by key prefix — Sleeper ids bare, ``mfl:<id>``, ``espn:<id>`` (or
# ``espn:<season>:<id>``, a past season), ``yahoo:<game>.l.<id>`` (Yahoo's league key, ``461.l.4242``). ``provider_of``
# is the one place a key's provider is read; ``platform`` / ``is_mfl`` stay (every older caller).
ESPN_PREFIX = "espn:"
YAHOO_PREFIX = "yahoo:"
_ESPN_KEY = re.compile(r"^(?:(\d{4}):)?(\d{1,12})$")
_YAHOO_KEY = re.compile(r"^(\d{1,4}|nfl)\.l\.(\d{1,10})$")    # "nfl": this season's game (IK-2 resolves it)
SHORT = {"sleeper": "Sleeper", "mfl": "MFL", "espn": "ESPN", "yahoo": "Yahoo", "reference": "Any league"}   # IM-3; IN-2
LONG = {"sleeper": "Sleeper", "mfl": "MyFantasyLeague", "espn": "ESPN", "yahoo": "Yahoo", "reference": "Any league"}
# ---- IM-3 (Wave I-M): reference league keys `ref:ppr` / `ref:half` / `ref:std` — no platform, no rosters: the NFL-wide
# research priced in a reference scoring. The API installs the object that answers them (REFERENCE:
# api/league_lab_api/refleague.py); until it does, a `ref:` key is LeagueNotFound like any unknown key.
REF_PREFIX = "ref:"
REFERENCE: Any = None


def is_reference(key: Any) -> bool:
    return str(key or "").strip().lower().startswith(REF_PREFIX)
# ---- end IM-3


# ---- IN-2 (Wave I-N): the reference key grows from three scorings to a small closed family, canonical and strictly
# parsed: ``ref:<scoring>[.sf][.tep][.p6][.t8|.t10|.t14]`` — the scoring (ppr, half, std, espn = ESPN's default, yahoo
# = Yahoo's default), then the options in this order: superflex, TE premium (+0.5 a tight-end catch), 6-point passing
# touchdowns, the league size (12 teams unless it says 8, 10 or 14). Lower case; any other spelling (another order,
# ``.t12``, a repeat, an unknown part) is not a key. 5 x 2 x 2 x 2 x 4 = 160 keys (``REF_KEYS``); ``ref:half`` stays
# the default and ``ref:ppr`` / ``ref:half`` / ``ref:std`` mean what they meant.
REF_BASES = ("ppr", "half", "std", "espn", "yahoo")
REF_TEAMS = (8, 10, 12, 14)
REF_TEAMS_DEFAULT = 12
_REF_KEY = re.compile(r"^ref:(ppr|half|std|espn|yahoo)(\.sf)?(\.tep)?(\.p6)?(?:\.t(8|10|14))?$")


def ref_key(base: str, sf: bool = False, tep: bool = False, p6: bool = False, teams: int = REF_TEAMS_DEFAULT) -> str:
    """The canonical key of a reference shape (ValueError for a scoring or size outside the family)."""
    if base not in REF_BASES or int(teams) not in REF_TEAMS:
        raise ValueError(f"no reference shape {base!r} / {teams!r}")
    return (REF_PREFIX + base + (".sf" if sf else "") + (".tep" if tep else "") + (".p6" if p6 else "")
            + ("" if int(teams) == REF_TEAMS_DEFAULT else f".t{int(teams)}"))


REF_KEYS = tuple(ref_key(b, sf, tep, p6, t) for b in REF_BASES for sf in (False, True) for tep in (False, True)
                 for p6 in (False, True) for t in REF_TEAMS)
_REF_SET = frozenset(REF_KEYS)


def parse_reference(key: Any) -> tuple[str, bool, bool, bool, int] | None:
    """(scoring, superflex, TE premium, 6-pt pass TD, teams) of a canonical reference key, else None. Strict: only the
    160 spellings ``REF_KEYS`` holds (case aside), so a key built from user input is always one of a countable set."""
    s = str(key or "").strip().lower()
    if len(s) > 32 or s not in _REF_SET:
        return None
    m = _REF_KEY.match(s)
    if m is None:                                   # never: REF_KEYS is built by ref_key, which the pattern matches
        return None
    return m.group(1), bool(m.group(2)), bool(m.group(3)), bool(m.group(4)), int(m.group(5) or REF_TEAMS_DEFAULT)
# ---- end IN-2


def provider_of(key: Any) -> str:
    """sleeper | mfl | espn | yahoo, by the key's prefix (case-insensitive); a bare key is Sleeper's. IM-3: ``reference``
    for a ``ref:`` key."""
    s = str(key or "").strip().lower()
    if s.startswith(REF_PREFIX):                      # ---- IM-3
        return "reference"
    if s.startswith(PREFIX):
        return "mfl"
    if s.startswith(ESPN_PREFIX):
        return "espn"
    if s.startswith(YAHOO_PREFIX):
        return "yahoo"
    return "sleeper"


def is_espn(key: Any) -> bool:
    return provider_of(key) == "espn"


def is_yahoo(key: Any) -> bool:
    return provider_of(key) == "yahoo"


def is_sleeper(key: Any) -> bool:
    return provider_of(key) == "sleeper"


def provider_short(key: Any) -> str:
    """"Sleeper" / "MFL" / "ESPN" / "Yahoo" for a league key (the words a screen puts after a league's name)."""
    return SHORT[provider_of(key)]


def check_espn(key: Any) -> str:
    """``espn:<id>`` / ``espn:<season>:<id>`` (lower-cased prefix) or LeagueNotFound."""
    s = str(key or "").strip()
    m = _ESPN_KEY.match(s[len(ESPN_PREFIX):] if s.lower().startswith(ESPN_PREFIX) else s)
    if not m:
        raise LeagueNotFound(f"not an ESPN league id: {key!r}")
    return ESPN_PREFIX + (f"{m.group(1)}:" if m.group(1) else "") + m.group(2)


def check_yahoo(key: Any) -> str:
    """``yahoo:<game>.l.<id>`` (lower-cased prefix and ``.l.``) or LeagueNotFound."""
    s = str(key or "").strip()
    m = _YAHOO_KEY.match((s[len(YAHOO_PREFIX):] if s.lower().startswith(YAHOO_PREFIX) else s).lower())
    if not m:
        raise LeagueNotFound(f"not a Yahoo league key: {key!r}")
    return f"{YAHOO_PREFIX}{m.group(1)}.l.{m.group(2)}"


def espn_id(key: str) -> str:
    """``espn:4242`` / ``espn:2025:4242`` -> ``4242``."""
    return check_espn(key).rsplit(":", 1)[-1]


def yahoo_key(key: str) -> str:
    """``yahoo:461.l.4242`` -> ``461.l.4242`` (Yahoo's own league key)."""
    return check_yahoo(key)[len(YAHOO_PREFIX):]
# ---- end IK-3


def platform(key: Any) -> str:
    return provider_of(key)          # ---- IK-3: was "mfl" if is_mfl(key) else "sleeper"


def check_key(key: Any) -> str:
    """A league key: Sleeper digits, ``mfl:<digits>``, ``espn:<digits>``, ``yahoo:<game>.l.<id>`` (lower-cased
    prefix). Anything else is LeagueNotFound."""
    s = str(key or "").strip()
    if is_reference(s):              # ---- IM-3
        if parse_reference(s) is None:                        # ---- IN-2: the closed family (REF_KEYS)
            raise LeagueNotFound(f"not a reference league: {key!r}")
        return s.lower()
    if is_mfl(s):
        return PREFIX + M.check_league(s[len(PREFIX):])
    if is_espn(s):                   # ---- IK-3
        return check_espn(s)
    if is_yahoo(s):                  # ---- IK-3
        return check_yahoo(s)
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

    def translate(self, lid: str, ids: list[str], *, record: bool = True) -> dict[str, tuple[str, str]]:
        """MFL ids -> (Sleeper id or ``mfl:<id>``, how: table | gsis | defense | name | unmapped). IL-2: ``record``
        False (a transaction's players) keeps them out of the league's rostered-player report (``unmapped``)."""
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
            except LeagueNotFound:     # ---- IP-5: refused / failed raises (busy), never "unmapped" (an empty roster spot)
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
        if record:                                                                          # ---- IL-2
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
                             # ---- IL-2: MFL's export has no playoff team count; 2 ** rounds, never more than the league
                             "playoff_teams": min(2 ** rounds, n or 2 ** rounds) if rounds else 0, "playoff_round_type": 0,
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
        gaps: list[Exception] = []          # ---- IP-5 fix round: a refused / failed read, never "no starters" / 0-0
        try:
            starters_mfl = M.starters_by_franchise(self.client.live_scoring(lid, week), None)
        except LeagueNotFound:
            pass
        except (M.MFLUnavailable, M.MFLBusy) as exc:
            if not provider_trouble.fixture_gap(exc):
                gaps.append(exc)
        if len(starters_mfl) < len(fr) and week > 1:
            try:
                prev = M.starters_by_franchise(None, self.client.weekly_results(lid, week - 1))
                for fid, s in prev.items():
                    starters_mfl.setdefault(fid, s)
            except LeagueNotFound:
                pass
            except (M.MFLUnavailable, M.MFLBusy) as exc:
                if not provider_trouble.fixture_gap(exc):
                    gaps.append(exc)
        if gaps and not starters_mfl:       # neither this week's nor last week's starters: busy, not "nothing set"
            raise gaps[-1]
        ids = sorted(set(ids) | {i for s in starters_mfl.values() for i in s})
        tr = self.translate(lid, ids)
        try:
            settings = M.standings_settings(self.client.standings(lid))
        except LeagueNotFound:
            settings = {}
        except (M.MFLUnavailable, M.MFLBusy) as exc:   # ---- IP-5 fix round: refused → raised, never 0-0 records
            if not provider_trouble.fixture_gap(exc):
                raise
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
        rows = M.weekly_matchups(self.client.schedule(lid), int(week), self._rid_of(lid))
        return self._with_live(key, int(week), rows)                     # ---- IL-2

    # ---- IL-2 (Wave I-L): this week's rows carry MFL's live scores the way Sleeper's matchups call does during a week —
    # ``points`` = the franchise's score so far, ``players_points`` = its listed players' (Sleeper ids). Another week, or
    # MFL's live scoring not answering, leaves the schedule's rows as they were.
    def _with_live(self, key: str, week: int, rows: list[dict]) -> list[dict]:
        if not rows:
            return rows
        lid = mfl_id(key)
        try:
            if week != self.week(lid):
                return rows
            live = self.client.live_scoring(lid, week)
        except LeagueNotFound:
            return rows
        except (M.MFLUnavailable, M.MFLBusy) as exc:   # ---- IP-5 fix round: refused → raised (the schedule's 0 is no
            if not provider_trouble.fixture_gap(exc):  # live score)
                raise
            return rows
        players = M.live_players(live)
        tr = self.translate(lid, sorted(players), record=False) if players else {}
        rid_of = self._rid_of(lid)
        per: dict[int, dict[str, float]] = {}
        for i, p in players.items():
            rid = rid_of.get(p["franchise"])
            if rid is not None and i in tr and p["score"] is not None:
                per.setdefault(rid, {})[tr[i][0]] = p["score"]
        fr = {rid_of[f]: v for f, v in M.live_franchises(live).items() if f in rid_of}
        out = []
        for r in rows:
            f = fr.get(int(r["roster_id"]))
            if f is not None and f.get("score") is not None:
                r = {**r, "points": float(f["score"]), "players_points": per.get(int(r["roster_id"]), {})}
            out.append(r)
        return out
    # ---- end IL-2

    def season_matchups(self, key: str, through_week: int) -> dict[int, list[dict]]:
        lid = mfl_id(key)
        sched, rid_of = self.client.schedule(lid), self._rid_of(lid)
        return {w: M.weekly_matchups(sched, w, rid_of) for w in range(1, int(through_week) + 1)}

    # ---- IL-2 (Wave I-L): MFL's transactions export in Sleeper's ``/transactions/<round>`` shape (``round_`` = MFL's
    # week ``W``): free agents -> ``free_agent``, waivers and blind-bid waivers -> ``waiver`` (the bid in
    # ``settings.waiver_bid``), trades -> ``trade`` (future draft picks in ``draft_picks``); players as Sleeper ids through
    # the league's id mapping (``translate``, not recorded as rostered). MFL has no transaction id: ``transaction_id`` is
    # ``mfl-<timestamp>-<franchise>-<hash>`` of the row (stable across reads). A past week is cached a day.
    # ---- PO 2026-10-05 (the live check on 70587): MFL files a move made once a week's games have begun under the
    # NEXT week (``W`` + 1: a Saturday add in week 4 is in ``W=5`` while MFL's own week is still 4), so MFL's current
    # week also lists the next week's file — under the week in progress, the week the move was made in. A round past
    # MFL's current week is empty (its moves are already listed), so a caller whose clock turns before MFL's (Monday
    # night to Tuesday) lists nothing twice. The next file not answering leaves the week's own moves.
    def transactions(self, key: str, round_: int) -> list[dict]:
        lid = mfl_id(key)
        week = int(round_)
        try:
            current = self.week(lid)
        except LeagueNotFound:
            current = week
        if week > current:
            return []
        rows = self.client.transactions(lid, week, settled=week < current)
        if week == current:
            try:
                rows = [*rows, *self.client.transactions(lid, week + 1)]
            except (M.MFLUnavailable, M.MFLBusy, LeagueNotFound):
                pass
        moves = [(r, m) for r in rows if (m := M.transaction_moves(r)) is not None]
        if not moves:
            return []
        rid_of = self._rid_of(lid)
        ids = sorted({i for _, m in moves for i in (*m["adds"], *m["drops"])})
        tr = self.translate(lid, ids, record=False) if ids else {}
        out = []
        for raw, m in moves:
            adds = {tr[i][0]: rid_of.get(f) for i, f in m["adds"].items() if i in tr}
            drops = {tr[i][0]: rid_of.get(f) for i, f in m["drops"].items() if i in tr}
            picks = [{"season": str(y), "round": r, "roster_id": rid_of.get(o), "previous_owner_id": rid_of.get(g),
                      "owner_id": rid_of.get(t)} for g, t, o, y, r in m["picks"]]
            rids = sorted({x for x in (*adds.values(), *drops.values(), rid_of.get(m["franchise"]),
                                       *(p["owner_id"] for p in picks), *(p["previous_owner_id"] for p in picks))
                           if x is not None})
            created = m["timestamp"] * 1000 if m["timestamp"] else None
            digest = hashlib.sha1(json.dumps(raw, sort_keys=True).encode()).hexdigest()[:8]
            out.append({"transaction_id": f"mfl-{m['timestamp'] or 0}-{m['franchise']}-{digest}", "type": m["kind"],
                        "status": "complete", "leg": week, "roster_ids": rids, "adds": adds or None,
                        "drops": drops or None, "draft_picks": picks, "waiver_budget": [], "creator": None,
                        "created": created, "status_updated": created,
                        "settings": ({"waiver_bid": int(m["bid"]) if float(m["bid"]).is_integer() else m["bid"]}
                                     if m["bid"] is not None else None),          # MFL bids can carry cents ($12.50)
                        "metadata": {"mfl_type": m["type"]}, "consenter_ids": rids})
        return sorted(out, key=lambda x: (x["created"] or 0, x["transaction_id"]))

    def live_points(self, key: str, week: int) -> dict:
        """IL-2: MFL's live scoring for the week, keyed by Sleeper id: ``{"points": {sid: score}, "done": {sid, ...},
        "teams_done": {NFL team, ...}, "franchises": {roster_id: {score, seconds_left, yet_to_play, playing}}}``. A
        player is done when MFL lists him with 0 game seconds left (his game is over, or he has no game); a game in
        progress is not done (the week's odds keep his full range)."""
        lid = mfl_id(key)
        live = self.client.live_scoring(lid, int(week))
        players = M.live_players(live)
        tr = self.translate(lid, sorted(players), record=False) if players else {}
        d = self.directory()
        points: dict[str, float] = {}
        done: set[str] = set()
        teams: set[str] = set()
        for i, p in players.items():
            if i not in tr or p["score"] is None:
                continue
            sid = tr[i][0]
            points[sid] = p["score"]
            if p["seconds_left"] == 0:
                done.add(sid)
                row = self.extra_players.get(sid) or d.get(sid) or {}
                if row.get("team"):
                    teams.add(str(row["team"]))
        rid_of = self._rid_of(lid)
        franchises = {rid_of[f]: v for f, v in M.live_franchises(live).items() if f in rid_of}
        return {"points": points, "done": done, "teams_done": teams, "franchises": franchises}
    # ---- end IL-2


# ---- IK-3 (Wave I-K): the ESPN and Yahoo adapters (IK-1's ``espn_leagues.ESPNLeagues``, IK-2's
# ``yahoo_leagues.YahooLeagues``: ``MFLLeagues``'s method set, Sleeper's shapes). Each is built on first use from its
# client (``espn_client.ESPN()`` / ``yahoo_client.Yahoo()``, configured by env); a module that is not in the tree or a
# client that cannot be built answers ``ProviderNotConfigured`` — a clean "not set up" error, never a crash.
# ``LEAGUE_LAB_PROVIDER_STUBS=1`` (tests / e2e only) serves both from ``provider_stubs`` (clearly synthetic).
STUBS_ENV = "LEAGUE_LAB_PROVIDER_STUBS"
ADAPTERS = {"espn": ("espn_client", "ESPN", "espn_leagues", "ESPNLeagues"),
            "yahoo": ("yahoo_client", "Yahoo", "yahoo_leagues", "YahooLeagues")}
# the env settings the adapters are built from: anyleague.sleeper() rebuilds the Router when one changes (tests)
ADAPTER_ENV = ("LEAGUE_LAB_ESPN_LEAGUE_FIXTURES", "LEAGUE_LAB_ESPN_SEASON", "LEAGUE_LAB_YAHOO_FIXTURES", STUBS_ENV)


class ProviderNotConfigured(LeagueNotFound):
    """This server cannot read the provider's leagues (its module or its settings are missing): ``code`` is
    ``<provider>_not_configured``."""

    def __init__(self, provider: str, why: str | None = None) -> None:
        self.provider = provider
        self.code = f"{provider}_not_configured"
        super().__init__(why or ("Yahoo sign-in is not set up on this server yet" if provider == "yahoo"
                                 else f"{LONG.get(provider, provider)} leagues are not set up on this server yet"))


def adapter_env() -> tuple:
    return tuple(os.environ.get(k) or "" for k in ADAPTER_ENV)


def build_adapter(provider: str, client: Any, directory: Callable[[], dict]) -> Any:
    """The provider's adapter in Sleeper's shapes (see ADAPTERS), or ProviderNotConfigured."""
    if os.environ.get(STUBS_ENV) == "1":
        from . import provider_stubs  # STUB (tests / e2e only)
        return provider_stubs.adapter(provider, client, directory)
    cmod, ccls, amod, acls = ADAPTERS[provider]
    try:
        cm = importlib.import_module(f"{__package__}.{cmod}")
        am = importlib.import_module(f"{__package__}.{amod}")
    except ImportError as exc:
        raise ProviderNotConfigured(provider) from exc
    try:
        return getattr(am, acls)(client if client is not None else getattr(cm, ccls)(), directory)
    except (AttributeError, TypeError, ValueError, OSError) as exc:
        raise ProviderNotConfigured(provider, f"{LONG[provider]} leagues are not set up on this server ({exc})") from exc
# ---- end IK-3


class Router:
    """``anyleague.sleeper()``: the Sleeper client for Sleeper keys, ``MFLLeagues`` for ``mfl:`` keys, IK-3: the ESPN /
    Yahoo adapters for ``espn:`` / ``yahoo:`` keys (``provider_of``); anything else (``bucket``, ``cache_path``,
    ``stale_served``…) is the Sleeper client's."""

    def __init__(self, sleeper: Sleeper | None = None, mfl: M.MFL | None = None, espn: Any = None,
                 yahoo: Any = None) -> None:
        self.sleeper = sleeper or Sleeper()
        self._mfl_client = mfl
        self._mfl: MFLLeagues | None = None
        self._espn_client, self._yahoo_client = espn, yahoo          # ---- IK-3: None = built from env on first use
        self._espn: Any = None
        self._yahoo: Any = None
        self.env = adapter_env()                                     # ---- IK-3: what the adapters were built from
        self._lock = threading.Lock()

    @property
    def mfl(self) -> MFLLeagues:
        with self._lock:
            if self._mfl is None:
                self._mfl = MFLLeagues(self._mfl_client or M.MFL(), self.sleeper.players)
            return self._mfl

    # ---- IK-3
    @property
    def espn(self) -> Any:
        with self._lock:
            if self._espn is None:
                self._espn = build_adapter("espn", self._espn_client, self.sleeper.players)
            return self._espn

    @property
    def yahoo(self) -> Any:
        with self._lock:
            if self._yahoo is None:
                self._yahoo = build_adapter("yahoo", self._yahoo_client, self.sleeper.players)
            return self._yahoo

    def adapters(self) -> list[tuple[str, Any]]:
        """The non-Sleeper adapters built so far (name, adapter) — players(), stats() and calls read them."""
        return [(n, a) for n, a in (("mfl", self._mfl), ("espn", self._espn), ("yahoo", self._yahoo)) if a is not None]

    def serving(self, key: str) -> Any:
        """The object that answers a key's Sleeper-shaped calls. An ESPN key passes the adapter's access check first
        (IK-1's ``require_access``: a private league read with one user's cookies is never served to another)."""
        p = provider_of(key)
        if p == "sleeper":
            return self.sleeper
        if p == "reference":                                          # ---- IM-3
            if REFERENCE is None:
                raise LeagueNotFound(f"not a league: {key!r}")
            return REFERENCE
        if p == "mfl":
            return self.mfl
        ad = self.espn if p == "espn" else self.yahoo
        check = getattr(ad, "require_access", None)
        if check is not None:
            check(key)
        return ad
    # ---- end IK-3

    @property
    def mfl_fixtures(self) -> str:
        return str((self._mfl_client.fixtures if self._mfl_client else None) or "")

    def __getattr__(self, name: str) -> Any:     # only for what Router does not define
        if name in ("sleeper", "_mfl", "_mfl_client", "_lock", "_espn", "_yahoo", "_espn_client", "_yahoo_client", "env"):
            raise AttributeError(name)
        return getattr(self.sleeper, name)

    @property
    def fixtures(self):
        return self.sleeper.fixtures

    @property
    def calls(self) -> int:
        return self.sleeper.calls + sum(int(getattr(getattr(a, "client", None), "calls", 0) or 0)
                                        for _n, a in self.adapters())      # IK-3: every provider's client

    def _call(self, key: str, name: str, *args: Any) -> Any:
        """IK-3: one Sleeper-shaped call. A provider error that says the server is not set up for it (IK-2's
        ``YahooNotConfigured``, a RuntimeError with ``code`` ``<provider>_not_configured``) becomes
        ``ProviderNotConfigured`` — a LeagueNotFound every route already answers in words, never a 500."""
        target = self.serving(key)
        try:
            return getattr(target, name)(key, *args)
        except RuntimeError as exc:
            code = str(getattr(exc, "code", "") or "")
            if code.endswith("_not_configured"):
                raise ProviderNotConfigured(provider_of(key)) from exc
            raise

    def league(self, key: str) -> dict:
        return self._call(key, "league")

    def rosters(self, key: str) -> list[dict]:
        return self._call(key, "rosters")

    def users(self, key: str) -> list[dict]:
        return self._call(key, "users")

    def matchups(self, key: str, week: int) -> list[dict]:
        return self._call(key, "matchups", week)

    def season_matchups(self, key: str, through_week: int) -> dict[int, list[dict]]:
        return self._call(key, "season_matchups", through_week)

    def transactions(self, key: str, round_: int) -> list[dict]:
        return self._call(key, "transactions", round_)

    def players(self) -> dict[str, dict]:
        d = self.sleeper.players()
        extras = [getattr(a, "extra_players", None) or {} for _n, a in self.adapters()]    # IK-3: every adapter's
        if not any(extras):
            return d
        merged = dict(d)
        for extra in extras:
            merged.update(extra)
        return merged

    def stats(self) -> dict:
        out = self.sleeper.stats()
        for n, a in self.adapters():                                          # IK-3: every adapter's client
            st = getattr(getattr(a, "client", None), "stats", None)
            if callable(st):
                out[n] = st()
        return out


# ---- II-5 (Wave I-I): what each provider gives League Lab — explicit, so a screen says "not available for MFL leagues
# yet" instead of showing an empty list as if the league had none (review § 9: "Unsupported data should be clearly
# unavailable rather than silently substituted"). Sleeper and MFL as built; ESPN and Yahoo are not supported (the
# research and the verdict: docs/PROVIDERS.md). One status per feature: "yes" (read and used as the provider has it),
# "partial" (read, with a stated gap), "no" (not read: the screen says the `unavailable` line). Served at
# `GET /api/providers` and on the setup answers (`capabilities`); `api/tests/test_ii5.py` pins the matrix.
FEATURES = ("scoring", "roster_slots", "matchups", "players", "waivers", "transactions", "team_assets", "news")
FEATURE_WORDS = {"scoring": "Scoring", "roster_slots": "Lineup slots", "matchups": "Matchups", "players": "Players",
                 "waivers": "Waivers", "transactions": "Transactions", "team_assets": "Team assets", "news": "News"}
PROVIDERS = ("sleeper", "mfl", "espn", "yahoo")
_NEWS = "ESPN's player news (most items RotoWire's), by player — the same on every platform"

_CAPS: dict[str, dict] = {
    "sleeper": {
        "name": "Sleeper", "short": "Sleeper", "status": "supported",
        "connect": {"kind": "username", "label": "Your Sleeper username, or a league link",
                    "example": "sleeper.com/leagues/1389709692405551104/team",
                    "where": "Your username is the name you sign in to Sleeper with, not your team's name. A league's "
                             "link is in the address bar of the league's page on sleeper.com: the long number after "
                             "/leagues/ is the league id."},
        "features": {
            "scoring": ("yes", "the league's own scoring settings; a setting not priced here is listed on the league card"),
            "roster_slots": ("yes", "every offensive slot, superflex included; IDP slots are left out and said so"),
            "matchups": ("yes", "this week's opponent and every played week's points, in the league's scoring"),
            "players": ("yes", "Sleeper's player directory, matched to nflverse ids for the projections"),
            "waivers": ("yes", "free agents, and the claim type and time from the league's settings"),
            "transactions": ("yes", "adds, drops and trades, from Sleeper's transactions"),
            "team_assets": ("partial", "team defenses are players; draft picks and waiver budgets are not read for a league opened on demand"),
            "news": ("yes", _NEWS),
        },
    },
    "mfl": {
        "name": "MyFantasyLeague", "short": "MFL", "status": "supported",
        "connect": {"kind": "league_link", "label": "Your MFL league link, id or name",
                    "example": "www45.myfantasyleague.com/2026/home/70587",
                    "where": "Open your league on the MFL website: the number after /home/ in the address is the league "
                             "id (70587 in the example). In the MFL app, type the league's name as the app shows it."},
        "features": {
            "scoring": ("partial", "MFL's rules read into the projections' scoring; any piece estimated or not priced is listed on the league card"),
            "roster_slots": ("partial", "starter ranges (2–4 WR) read as the minimum plus FLEX; IDP spots are left out and said so"),
            "matchups": ("yes", "the schedule, each week's opponent and every played week's points; this week's live points from MFL's live scoring (a game in progress counts as its full range)"),  # ---- IL-2
            "players": ("partial", "MFL ids matched to Sleeper's; a player with no match is listed by name and not valued"),
            "waivers": ("partial", "free agents are the players no team rosters; MFL's waiver type, waiver order and blind-bid balances are read; MFL does not share the claim time"),  # ---- IL-2
            "transactions": ("yes", "adds, drops, trades and waiver claims from MFL's transactions export"),  # ---- IL-2; verified live 2026-10-05 (docs/PROVIDERS.md)
            "team_assets": ("partial", "team QBs, kickers and defenses are priced as players; draft picks and blind-bid budgets are not read"),
            "news": ("yes", _NEWS),
        },
    },
    # ---- IK-3 (Wave I-K): ESPN (IK-1) and Yahoo (IK-2) as built, **not verified on a live league yet**: every feature
    # "partial" with the words saying so, status "unverified". After the deploy the PO opens a live league of each and
    # flips what held (the status to "supported", a feature's words without UNVERIFIED) — docs/PROVIDERS.md.
    "espn": {
        "name": "ESPN", "short": "ESPN", "status": "unverified",
        "note": "Unofficial: ESPN has no public API for fantasy leagues. isuckatfantasy reads what a public league shows "
                "anyone, read-only.",
        "connect": {"kind": "league_link", "label": "Your ESPN league link or id",
                    "example": "fantasy.espn.com/football/league?leagueId=4242",
                    "where": "Open your league on fantasy.espn.com: the number after leagueId= in the address is the "
                             "league id (4242 in the example). A public league works by its id alone; ESPN has no "
                             "sign-in for other apps."},
        "features": {
            "scoring": ("partial", "ESPN's scoring items read into the projections' scoring; any item not priced is listed on the league card"),
            "roster_slots": ("partial", "ESPN's lineup slots read as ours (OP as superflex, D/ST as DEF); IDP slots are left out and said so"),
            "matchups": ("partial", "the schedule and each week's points from ESPN's matchups"),
            "players": ("partial", "ESPN ids matched to Sleeper's through nflverse's id table; a player with no match is listed by name and not valued"),
            "waivers": ("partial", "free agents are the players no team rosters; ESPN's waiver order and budget are not read"),
            "transactions": ("partial", "adds, drops and trades from ESPN's transactions"),
            "team_assets": ("partial", "D/ST as team defenses; draft picks and waiver budgets are not read"),
            "news": ("partial", _NEWS + ", for the players matched to our ids"),
        },
    },
    "yahoo": {
        "name": "Yahoo", "short": "Yahoo", "status": "unverified",
        "note": "Through Yahoo's official Fantasy Sports API, read-only, after you allow it with your Yahoo sign-in.",
        "connect": {"kind": "oauth", "label": "Connect with Yahoo",
                    "example": "football.fantasysports.yahoo.com/f1/12345",
                    "where": "Connect with Yahoo: Yahoo asks you to allow read-only access to your fantasy leagues, then "
                             "your leagues are listed here to pick from. A league's link (the number after /f1/) works "
                             "too once you are connected."},
        "features": {
            "scoring": ("partial", "Yahoo's stat modifiers read into the projections' scoring; any stat not priced is listed on the league card"),
            "roster_slots": ("partial", "Yahoo's positions read as ours (W/R/T as FLEX, Q/W/R/T as superflex); IDP slots are left out and said so"),
            "matchups": ("partial", "each week's opponent and points from Yahoo's scoreboard"),
            "players": ("partial", "Yahoo ids matched to Sleeper's through nflverse's id table; a player with no match is listed by name and not valued"),
            "waivers": ("partial", "free agents from Yahoo's player list; waiver priority and budgets are not read"),
            "transactions": ("partial", "adds, drops and trades from Yahoo's transactions"),
            "team_assets": ("partial", "DEF as team defenses; draft picks and waiver budgets are not read"),
            "news": ("partial", _NEWS + ", for the players matched to our ids"),
        },
    },
    # ---- end IK-3
}


UNVERIFIED = " — as built, not verified on a live league yet"   # ---- IK-3 (the PO removes it per provider once checked)


def unavailable(provider: str, feature: str) -> str | None:
    """The sentence a screen says where a feature is not read for this provider ("Transactions: not available for MFL
    leagues yet"); None when it is read ("yes" / "partial")."""
    p = _CAPS.get(str(provider).lower())
    if p is None or feature not in FEATURES:
        raise KeyError(f"unknown provider or feature: {provider!r} {feature!r}")
    status, _ = p["features"][feature]
    if status != "no":
        return None
    return f"{FEATURE_WORDS[feature]}: not available for {p['short']} leagues yet"


def capabilities(provider: str) -> dict:
    """``{provider, name, short, status, connect, features: {<FEATURES>: {status, words, unavailable}}}`` — a fresh
    dict each call (callers may add to it). ``provider``: sleeper | mfl | espn | yahoo (KeyError otherwise)."""
    key = str(provider).lower()
    p = _CAPS[key]
    status = provider_status(key)                                        # ---- IL-5: the verified flip, the kill switch
    tail = UNVERIFIED if status == "unverified" else ""                  # ---- IK-3: said on every unverified feature
    out = {"provider": key, "name": p["name"], "short": p["short"], "status": status, "connect": dict(p["connect"]),
           "features": {f: {"label": FEATURE_WORDS[f], "status": p["features"][f][0], "words": p["features"][f][1] + tail,
                            "unavailable": unavailable(key, f)} for f in FEATURES}}
    if p.get("note"):                                                    # ---- IK-3: ESPN's "unofficial", Yahoo's OAuth
        out["note"] = p["note"]
    if status == "off":                                                  # ---- IL-5
        out["off"] = f"{p['name']} leagues: {OFF_WORDS}"
    return out


# ---- IL-5 (Wave I-L): the two switches `/api/providers` follows, so a flip is a Render environment change, not a deploy.
# * LEAGUE_LAB_PROVIDER_VERIFIED=espn,yahoo (default empty): the providers the PO has checked on a live league — their
#   status goes from "unverified" to "supported" and the UNVERIFIED tail leaves every feature's words (the features keep
#   their own status: "partial" stays partial). A provider already "supported" (Sleeper, MFL) is unchanged by it.
# * LEAGUE_LAB_ESPN_LEAGUES=off (espn_client's kill switch): ESPN's status is "off" with OFF_WORDS; the setup screen
#   says so in place of the form. Yahoo without its secrets stays "unverified" and its button says "coming soon" (the
#   setup screen reads `yahoo_configured`): "coming soon" is the right word while the app is not registered.
VERIFIED_ENV = "LEAGUE_LAB_PROVIDER_VERIFIED"
ESPN_SWITCH_ENV = "LEAGUE_LAB_ESPN_LEAGUES"
OFF_WORDS = "not available right now"


def verified_providers() -> frozenset[str]:
    raw = os.environ.get(VERIFIED_ENV) or ""
    return frozenset(x for x in (w.strip().lower() for w in raw.split(",")) if x in PROVIDERS)


def switched_off(provider: str) -> bool:
    """The provider's kill switch is off (ESPN only today: ``LEAGUE_LAB_ESPN_LEAGUES``, default on)."""
    if provider == "espn":
        return str(os.environ.get(ESPN_SWITCH_ENV) or "on").strip().lower() in ("off", "0", "false", "no")
    return False


def provider_status(provider: str) -> str:
    """supported | unverified | not_supported | off — ``_CAPS``'s status with the two switches applied."""
    key = str(provider).lower()
    status = _CAPS[key]["status"]
    if switched_off(key):
        return "off"
    if status == "unverified" and key in verified_providers():
        return "supported"
    return status
# ---- end IL-5


def capabilities_for(key: Any) -> dict:
    """The capabilities of the provider serving a league key (``mfl:70587`` -> MFL, digits -> Sleeper)."""
    return capabilities(platform(key))


def all_capabilities() -> list[dict]:
    return [capabilities(p) for p in PROVIDERS]
# ---- end II-5
