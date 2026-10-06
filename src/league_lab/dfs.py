"""Daily fantasy (DFS): values, undervalued players and lineups from the site's own salary file (Wave I-M, IM-5).

Nothing here fetches a salary. DraftKings and FanDuel forbid automated collection and the PO's tools cannot open
either site, so the user brings the salary file the contest's draft page exports ("Export to CSV" on DraftKings,
"Download players list" on FanDuel) and gets the analysis back. The file is parsed in memory and never stored or
logged. docs/DFS.md is the contract (scoring tables, matching rules, the value definition, what is approximate).

The pieces, all pure (no database; the API passes the week's ``anyleague.Board`` and the schedule):

* **Sites as data** (``CONTESTS``): DraftKings classic and showdown, FanDuel full roster — slots, cap, team rules,
  the lineup-upload header. **Scoring** (``SCORING``) in Sleeper's keys, so ``scoring.price_projected`` /
  ``kdef.price`` price a stat line exactly as every other screen does.
* **Parsers** (``parse``): either site's file, tolerant of a BOM, quoted fields, extra columns, any column order and
  leading blank rows / columns; the site and contest from the header and the roster positions; anything else is
  refused in words. 1 MB and 2,000 rows at most.
* **Matching** (``match``): the site's team code to ours, then a UNIQUE normalised name + position + team (a team
  defense by its team); unmatched and ambiguous players are listed with the reason and never valued.
* **The numbers** (``price_site``, ``value``): the stored stat lines priced in the site's scoring, the range from the
  nearest reference scoring, points per $1,000, the slate's salary line per position and each player's gap to it.
* **Lineups** (``solve_lineups``): an exact MILP (``scipy.optimize.milp``, HiGHS) for the slots and the cap, cash
  (projection) or tournament (high-end outcome), locks / excludes, the site's team rules, the next N distinct lineups.
* **Upload CSV** (``upload_csv``): the site's lineup-upload shape with the file's own ids; a cell that could be read
  as a formula (``= + - @``, tab, CR) is neutralised.

Wave I-N (IN-4) adds: **context beyond the projection** (``role_trend``, ``game_environment``, ``weather_flag``,
``signals``, ``worth_a_look``) — each signal says whether it is an input of the projection, read from
``projections.FEATURES_BY_POSITION`` (``SIGNAL_INPUTS``); **stacks and exposure** in ``solve_lineups``; the
**published-slate names** (``slate_name``).
"""

from __future__ import annotations

import csv
import functools
import io
import math
import re
import time
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# ------------------------------------------------------------------------------------------------ limits
MAX_BYTES = 1_000_000          # the file's size cap (a real slate file is 20-120 KB)
MAX_ROWS = 2_000               # rows after the header (a full Sunday main slate is ~600 on DraftKings)
MAX_COLS = 200                 # columns in a row (a salary file has 9-16; DraftKings' entry template ~30)
MAX_CELL = 300                 # characters in a cell (a name, "BUF@MIA 10/11/2026 01:00PM ET")
MAX_LINEUPS = 20
MAX_PLAYERS = 800              # players in one lineups request: a full Sunday main slate is ~600 rows on DraftKings
MAX_GAMES, MAX_TEAMS = 16, 32  # an NFL week has at most 16 games
SOLVE_SECONDS = 5.0            # the time box for ALL the lineups of one request (HiGHS' time_limit, shared)
# HiGHS stops when the lineup is within this share of the best possible: 1e-5 of a 150-point lineup is 0.0015 points,
# under the 0.005 step every total moves in (projections to the hundredth; a captain's x1.5) — so "proven" here is
# proven best, and the search does not spend its second closing a gap no lineup could fill
MIP_GAP = 1e-5

# ------------------------------------------------------------------------------------------------ scoring
# As each site publishes it (checked against the sites' rules pages as remembered, October 2026 — docs/DFS.md says
# which details are unverified). Sleeper's keys: ``scoring.SLEEPER_STAT_MAP`` / ``SLEEPER_BONUS_MAP`` for players,
# ``kdef.DEF_STAT_MAP`` / ``PTS_ALLOW_BUCKETS`` for a team defense, the FG keys for a kicker (DraftKings showdown).
_DST = {"sack": 1.0, "int": 2.0, "fum_rec": 2.0, "def_td": 6.0, "def_st_td": 6.0, "safe": 2.0, "blk_kick": 2.0,
        "pts_allow_0": 10.0, "pts_allow_1_6": 7.0, "pts_allow_7_13": 4.0, "pts_allow_14_20": 1.0,
        "pts_allow_21_27": 0.0, "pts_allow_28_34": -1.0, "pts_allow_35p": -4.0}
SCORING: dict[str, dict[str, float]] = {
    "dk": {
        "pass_yd": 0.04, "pass_td": 4.0, "pass_int": -1.0, "pass_2pt": 2.0,
        "rush_yd": 0.1, "rush_td": 6.0, "rush_2pt": 2.0,
        "rec": 1.0, "rec_yd": 0.1, "rec_td": 6.0, "rec_2pt": 2.0,
        "fum_lost": -1.0, "fum_rec_td": 6.0, "st_td": 6.0,
        # +3 at 300+ passing / 100+ rushing / 100+ receiving yards, paid once: Sleeper's bands are exclusive
        # (300-399, 400+), so both carry the 3
        "bonus_pass_yd_300": 3.0, "bonus_pass_yd_400": 3.0, "bonus_rush_yd_100": 3.0, "bonus_rush_yd_200": 3.0,
        "bonus_rec_yd_100": 3.0, "bonus_rec_yd_200": 3.0,
        # the kicker (showdown only): 3 to 39 yards, 4 for 40-49, 5 for 50+, 1 per extra point
        "fgm_0_19": 3.0, "fgm_20_29": 3.0, "fgm_30_39": 3.0, "fgm_40_49": 4.0, "fgm_50p": 5.0, "xpm": 1.0,
        **_DST,
    },
    "fd": {
        "pass_yd": 0.04, "pass_td": 4.0, "pass_int": -1.0, "pass_2pt": 2.0,
        "rush_yd": 0.1, "rush_td": 6.0, "rush_2pt": 2.0,
        "rec": 0.5, "rec_yd": 0.1, "rec_td": 6.0, "rec_2pt": 2.0,
        "fum_lost": -2.0, "fum_rec_td": 6.0, "st_td": 6.0,
        **_DST,
    },
}
SITE_NAMES = {"dk": "DraftKings", "fd": "FanDuel"}
# DraftKings' +3 bonuses are priced at their odds (``scoring.price_projected(ev=True)``: P(yards >= 100) x 3 from M2's
# curves) whatever the record's mode: an all-or-nothing bonus on a projected mean puts a 3-point step between a back
# projected 99 and one projected 101 yards, and a salary comparison cannot carry that. FanDuel has no bonus: the flag
# changes nothing there (the flat engine, bit for bit).
BONUS_AT_ODDS = True
CAPTAIN = 1.5                   # DraftKings showdown: the captain scores 1.5x (his salary is in the file)


@dataclass(frozen=True)
class SlotGroup:
    label: str                  # the upload header's word ("RB", "FLEX", "CPT")
    count: int
    elig: frozenset[str]        # our positions (QB RB WR TE K DEF)
    multiplier: float = 1.0     # points (and the captain's salary, which the file states)


@dataclass(frozen=True)
class Contest:
    key: str                    # "dk_classic" | "dk_showdown" | "fd_full"
    site: str                   # "dk" | "fd"
    label: str
    cap: int
    groups: tuple[SlotGroup, ...]
    max_per_team: int | None = None
    min_games: int | None = None
    min_teams: int | None = None
    upload_header: tuple[str, ...] = ()

    @property
    def size(self) -> int:
        return sum(g.count for g in self.groups)


_FLEX = frozenset({"RB", "WR", "TE"})
_ANY = frozenset({"QB", "RB", "WR", "TE", "K", "DEF"})
CONTESTS: dict[str, Contest] = {
    "dk_classic": Contest(
        "dk_classic", "dk", "DraftKings classic", 50_000,
        (SlotGroup("QB", 1, frozenset({"QB"})), SlotGroup("RB", 2, frozenset({"RB"})), SlotGroup("WR", 3, frozenset({"WR"})),
         SlotGroup("TE", 1, frozenset({"TE"})), SlotGroup("FLEX", 1, _FLEX), SlotGroup("DST", 1, frozenset({"DEF"}))),
        min_games=2, upload_header=("QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "DST")),
    "dk_showdown": Contest(
        "dk_showdown", "dk", "DraftKings showdown", 50_000,
        (SlotGroup("CPT", 1, _ANY, CAPTAIN), SlotGroup("FLEX", 5, _ANY)),
        min_teams=2, upload_header=("CPT", "FLEX", "FLEX", "FLEX", "FLEX", "FLEX")),
    "fd_full": Contest(
        "fd_full", "fd", "FanDuel full roster", 60_000,
        (SlotGroup("QB", 1, frozenset({"QB"})), SlotGroup("RB", 2, frozenset({"RB"})), SlotGroup("WR", 3, frozenset({"WR"})),
         SlotGroup("TE", 1, frozenset({"TE"})), SlotGroup("FLEX", 1, _FLEX), SlotGroup("DEF", 1, frozenset({"DEF"}))),
        max_per_team=4, upload_header=("QB", "RB", "RB", "WR", "WR", "WR", "TE", "FLEX", "DEF")),
}

# ------------------------------------------------------------------------------------------------ teams
# the sites' codes -> nflverse's (ours: LA = the Rams, WAS, JAX, LV, LAC)
TEAM_ALIASES = {"JAC": "JAX", "LAR": "LA", "WSH": "WAS", "OAK": "LV", "LVR": "LV", "SD": "LAC", "STL": "LA",
                "ARZ": "ARI", "BLT": "BAL", "CLV": "CLE", "HST": "HOU", "KCC": "KC", "NOS": "NO", "NEP": "NE",
                "GBP": "GB", "TBB": "TB", "SFO": "SF", "NOR": "NO", "NWE": "NE", "GNB": "GB", "TAM": "TB", "KAN": "KC",
                "SFX": "SF"}
NFL_TEAMS = frozenset({"ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE", "DAL", "DEN", "DET", "GB", "HOU", "IND",
                       "JAX", "KC", "LA", "LAC", "LV", "MIA", "MIN", "NE", "NO", "NYG", "NYJ", "PHI", "PIT", "SEA",
                       "SF", "TB", "TEN", "WAS"})


def team_code(t: str | None) -> str | None:
    """A site's team code in nflverse's spelling (``JAC`` -> ``JAX``, ``LAR`` -> ``LA``, ``WSH`` -> ``WAS``); None
    when it is not an NFL team."""
    if not t:
        return None
    t = str(t).strip().upper()
    t = TEAM_ALIASES.get(t, t)
    return t if t in NFL_TEAMS else None


# the sites' position words -> ours
POSITION = {"QB": "QB", "RB": "RB", "WR": "WR", "TE": "TE", "K": "K", "PK": "K", "DST": "DEF", "D": "DEF",
            "DEF": "DEF", "D/ST": "DEF", "FB": "RB"}


# ------------------------------------------------------------------------------------------------ parsing
class SlateError(ValueError):
    """A file we refuse, with the words the screen shows."""

    def __init__(self, words: str, code: str = "bad_file"):
        super().__init__(words)
        self.code = code


@dataclass
class SlatePlayer:
    key: str                          # unique on the slate: the site's id (DraftKings showdown: the FLEX row's id)
    site_id: str
    name: str
    position: str                     # ours (QB RB WR TE K DEF)
    site_position: str
    roster_positions: tuple[str, ...]
    salary: int
    team: str | None                  # ours (nflverse)
    site_team: str
    opponent: str | None = None
    game: str | None = None           # "BUF@MIA" (the site's codes as written)
    kickoff: str | None = None        # DraftKings' "10/11/2026 01:00PM ET" when the file has it
    name_id: str | None = None        # DraftKings' "Name (ID)"
    injury: str | None = None         # FanDuel's indicator (Q, D, O, IR …)
    site_avg: float | None = None     # the site's own points per game (AvgPointsPerGame / FPPG)
    cpt_id: str | None = None         # DraftKings showdown: the captain row's id and salary
    cpt_salary: int | None = None
    cpt_name_id: str | None = None


@dataclass
class Slate:
    site: str
    contest: str
    players: list[SlatePlayer]
    skipped: list[dict] = field(default_factory=list)      # rows we could not read, with the reason
    games: list[str] = field(default_factory=list)          # "BUF@MIA", in file order
    notes: list[str] = field(default_factory=list)


_DK_REQUIRED = ("position", "name", "id", "roster position", "salary", "teamabbrev")
_FD_REQUIRED = ("id", "position", "salary", "team")
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$")
_GAME_RE = re.compile(r"^\s*([A-Za-z]{2,4})\s*@\s*([A-Za-z]{2,4})(?:\s+(.*))?$")


def _norm_header(h: str) -> str:
    return re.sub(r"\s+", " ", str(h or "").replace("﻿", "").strip().strip('"').lower())


# the words a salary file's header is made of: a block of columns is tried only where one of them starts it
HEADER_WORDS = frozenset({"position", "name + id", "name", "id", "roster position", "salary", "game info", "teamabbrev",
                          "avgpointspergame", "first name", "nickname", "last name", "fppg", "played", "game", "team",
                          "opponent", "injury indicator", "injury details", "tier"})


def _kind(header: list[str]) -> str | None:
    hs = set(header)
    if "salary" not in hs:
        return None
    if ("name + id" in hs or "roster position" in hs) and "teamabbrev" in hs:
        return "dk"
    if "id" in hs and ("nickname" in hs or ("first name" in hs and "last name" in hs)):
        return "fd"
    return None


def _refuse_header(rows: list[list[str]]) -> SlateError:
    seen = next((r for r in rows if any(c.strip() for c in r)), [])
    have = ", ".join(c.strip() for c in seen[:8] if c.strip()) or "nothing"
    return SlateError("That does not look like a DraftKings or FanDuel salary file: expected a column named Salary "
                      "and either Name + ID and TeamAbbrev (DraftKings) or First Name and Last Name (FanDuel). "
                      f"The first row has: {have[:160]}.", "not_a_salary_file")


def _salary(v: str) -> int | None:
    s = re.sub(r"[\s$,]", "", str(v or ""))
    if not re.fullmatch(r"\d{1,6}(\.0+)?", s):
        return None
    return int(float(s))


def _float(v: str) -> float | None:
    try:
        x = float(str(v).strip())
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _game(v: str | None) -> tuple[str | None, str | None, str | None]:
    """'BUF@MIA 10/11/2026 01:00PM ET' -> ('BUF', 'MIA', '10/11/2026 01:00PM ET')."""
    m = _GAME_RE.match(str(v or ""))
    if not m:
        return None, None, None
    return m.group(1).upper(), m.group(2).upper(), (m.group(3) or "").strip() or None


def parse(text: str | bytes) -> Slate:
    """A DraftKings or FanDuel salary file -> a ``Slate`` (or ``SlateError`` with the words). Never stores it."""
    if isinstance(text, bytes):
        if len(text) > MAX_BYTES:
            raise SlateError(f"That file is {len(text) / 1e6:.1f} MB: a salary file is under 1 MB. Export the "
                             "contest's player list again and add that file.", "too_large")
        try:
            text = text.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = text.decode("latin-1")
    if len(text.encode("utf-8")) > MAX_BYTES:
        raise SlateError(f"That file is {len(text.encode('utf-8')) / 1e6:.1f} MB: a salary file is under 1 MB. "
                         "Export the contest's player list again and add that file.", "too_large")
    text = text.lstrip("﻿")
    if "\x00" in text:
        raise SlateError("That file is not text: a salary file is a CSV (comma-separated text).", "not_text")
    # bounded before any parsing (linear, no row held whole): a row of hundreds of columns, a giant cell
    for i, line in enumerate(text.splitlines()[: MAX_ROWS + 20], start=1):
        if line.count(",") > 2 * MAX_COLS:
            raise SlateError(f"Row {i} of that file has over {MAX_COLS} columns: a salary file has about 10. Export the "
                             "contest's player list again and add that file unchanged.", "too_many_columns")
    try:
        rows = list(csv.reader(io.StringIO(text)))
    except csv.Error as exc:
        raise SlateError(f"That file could not be read as a CSV ({exc}).", "not_csv") from exc
    for i, r in enumerate(rows, start=1):
        if len(r) > MAX_COLS:
            raise SlateError(f"Row {i} of that file has {len(r)} columns: a salary file has about 10. Export the "
                             "contest's player list again and add that file unchanged.", "too_many_columns")
        if any(len(c) > MAX_CELL for c in r):
            raise SlateError(f"Row {i} of that file has a cell over {MAX_CELL} characters: not a salary file's. Export "
                             "the contest's player list again and add that file unchanged.", "cell_too_long")
    # the header: the first row (of the first 15) that names a known site's columns; a column offset is allowed
    # (DraftKings' entry template puts the player list to the right of the entries)
    hdr_i, kind, offset = None, None, 0
    for i, r in enumerate(rows[:15]):
        norm = [_norm_header(c) for c in r]
        for off in range(len(norm)):
            # a block starts here: a known header word after an empty cell (or the row's start) — linear in the row
            if norm[off] in HEADER_WORDS and (off == 0 or not norm[off - 1]):
                k = _kind(norm[off:])
                if k:
                    hdr_i, kind, offset = i, k, off
                    break
        if kind:
            break
    if kind is None or hdr_i is None:
        raise _refuse_header(rows)
    header = [_norm_header(c) for c in rows[hdr_i][offset:]]
    col = {}
    for j, h in enumerate(header):
        col.setdefault(h, j)
    need = _DK_REQUIRED if kind == "dk" else _FD_REQUIRED
    missing = [n for n in need if n not in col]
    if kind == "fd" and "nickname" not in col and not ("first name" in col and "last name" in col):
        missing.append("nickname")
    if missing:
        site = SITE_NAMES[kind]
        raise SlateError(f"That looks like a {site} file but a column is missing: "
                         f"{', '.join(m.title() for m in missing)}. Export the player list again from the contest's "
                         "page and add that file unchanged.", "missing_column")
    body = [r[offset:] for r in rows[hdr_i + 1:] if any(c.strip() for c in r[offset:])]
    if len(body) > MAX_ROWS:
        raise SlateError(f"That file has {len(body):,} players: a slate has at most {MAX_ROWS:,}. Export one "
                         "contest's player list.", "too_many_rows")
    if not body:
        raise SlateError("That file has a header and no players.", "empty")

    def cell(r: list[str], name: str) -> str:
        j = col.get(name)
        return (r[j] if j is not None and j < len(r) else "").strip()

    return _parse_dk(body, cell) if kind == "dk" else _parse_fd(body, cell)


def _skip(out: list[dict], i: int, name: str, why: str) -> None:
    out.append({"row": i, "name": name[:80], "reason": why})


def _parse_dk(body: list[list[str]], cell) -> Slate:
    skipped: list[dict] = []
    rows = []
    for i, r in enumerate(body, start=2):
        name, pid, rp = cell(r, "name"), cell(r, "id"), cell(r, "roster position")
        pos = POSITION.get(cell(r, "position").upper())
        sal = _salary(cell(r, "salary"))
        if not _ID_RE.match(pid):
            _skip(skipped, i, name, "its ID is not a DraftKings player id")
            continue
        if pos is None:
            _skip(skipped, i, name, f"position “{cell(r, 'position')[:12]}” is not one we value")
            continue
        if sal is None:
            _skip(skipped, i, name, "its salary is not a number")
            continue
        away, home, when = _game(cell(r, "game info"))
        site_team = cell(r, "teamabbrev").upper()
        rows.append({"i": i, "name": name, "id": pid, "rp": tuple(x.strip().upper() for x in rp.split("/") if x.strip()),
                     "pos": pos, "site_pos": cell(r, "position").upper(), "salary": sal, "site_team": site_team,
                     "away": away, "home": home, "when": when, "name_id": cell(r, "name + id") or None,
                     "avg": _float(cell(r, "avgpointspergame"))})
    rps = {p for r in rows for p in r["rp"]}
    if "CPT" in rps:
        contest = "dk_showdown"
    elif rps & {"RB", "WR", "TE", "QB", "DST", "FLEX"}:
        contest = "dk_classic"
    else:
        raise SlateError("This DraftKings contest type is not one we read yet (roster positions "
                         f"{', '.join(sorted(rps))[:80] or 'none'}): classic and showdown only.", "unsupported_contest")
    if contest == "dk_showdown" and rps - {"CPT", "FLEX"}:
        raise SlateError("This DraftKings showdown file has roster positions other than CPT and FLEX "
                         f"({', '.join(sorted(rps - {'CPT', 'FLEX'}))[:60]}): not one we read yet.", "unsupported_contest")
    players: list[SlatePlayer] = []
    seen: dict[str, SlatePlayer] = {}
    if contest == "dk_showdown":
        # each player twice: a CPT row and a FLEX row (own id, own salary); one player, the two kept
        by: dict[tuple, dict] = {}
        for r in rows:
            k = (_name_key(r["name"]), r["pos"], r["site_team"])
            by.setdefault(k, {})["CPT" if "CPT" in r["rp"] else "FLEX"] = r
        for d in by.values():
            f, c = d.get("FLEX"), d.get("CPT")
            if f is None:
                _skip(skipped, c["i"], c["name"], "a captain row with no FLEX row for him")
                continue
            p = _player(f)
            if c is not None:
                p.cpt_id, p.cpt_salary, p.cpt_name_id = c["id"], c["salary"], c["name_id"]
            if p.key in seen:
                _skip(skipped, f["i"], f["name"], "his ID is on the file twice")
                continue
            seen[p.key] = p
            players.append(p)
    else:
        for r in rows:
            p = _player(r)
            if p.key in seen:
                _skip(skipped, r["i"], r["name"], "his ID is on the file twice")
                continue
            seen[p.key] = p
            players.append(p)
    return _finish(Slate("dk", contest, players, skipped))


def _player(r: dict) -> SlatePlayer:
    team = team_code(r["site_team"])
    opp = None
    if r.get("away") and r.get("home"):
        a, h = r["away"].upper(), r["home"].upper()
        opp = team_code(h if r["site_team"] == a else a if r["site_team"] == h else None)
    game = f"{r['away']}@{r['home']}" if r.get("away") and r.get("home") else None
    return SlatePlayer(key=r["id"], site_id=r["id"], name=r["name"], position=r["pos"], site_position=r["site_pos"],
                       roster_positions=r["rp"], salary=r["salary"], team=team, site_team=r["site_team"],
                       opponent=opp, game=game, kickoff=r.get("when"), name_id=r.get("name_id"),
                       injury=r.get("injury"), site_avg=r.get("avg"))


def _parse_fd(body: list[list[str]], cell) -> Slate:
    skipped: list[dict] = []
    players: list[SlatePlayer] = []
    seen: set[str] = set()
    rps: set[str] = set()
    for i, r in enumerate(body, start=2):
        name = cell(r, "nickname") or " ".join(x for x in (cell(r, "first name"), cell(r, "last name")) if x)
        pid = cell(r, "id")
        site_pos = cell(r, "position").upper()
        pos = POSITION.get(site_pos)
        sal = _salary(cell(r, "salary"))
        rp = tuple(x.strip().upper() for x in cell(r, "roster position").split("/") if x.strip()) or (site_pos,)
        rps.update(rp)
        if not _ID_RE.match(pid):
            _skip(skipped, i, name, "its Id is not a FanDuel player id")
            continue
        if pos is None:
            _skip(skipped, i, name, f"position “{site_pos[:12]}” is not one we value")
            continue
        if sal is None:
            _skip(skipped, i, name, "its salary is not a number")
            continue
        if pid in seen:
            _skip(skipped, i, name, "his Id is on the file twice")
            continue
        away, home, _ = _game(cell(r, "game"))
        site_team = cell(r, "team").upper()
        opp_cell = team_code(cell(r, "opponent"))
        p = _player({"id": pid, "name": name, "pos": pos, "site_pos": site_pos, "rp": rp, "salary": sal,
                     "site_team": site_team, "away": away, "home": home, "when": None, "name_id": None,
                     "injury": cell(r, "injury indicator") or None, "avg": _float(cell(r, "fppg"))})
        if p.opponent is None and opp_cell:
            p.opponent = opp_cell
        seen.add(pid)
        players.append(p)
    if any(p.position == "K" for p in players) or "MVP" in rps:
        raise SlateError("That looks like a FanDuel single-game file (it lists kickers or an MVP slot): only the "
                         "full-roster contest is read yet.", "unsupported_contest")
    return _finish(Slate("fd", "fd_full", players, skipped))


def _finish(s: Slate) -> Slate:
    if not s.players:
        raise SlateError("No player on that file could be read: " + "; ".join(
            f"row {k['row']}: {k['reason']}" for k in s.skipped[:3]) + ".", "no_players")
    games = []
    for p in s.players:
        if p.game and p.game not in games:
            games.append(p.game)
    s.games = games
    if s.contest == "dk_showdown":
        teams = {p.team for p in s.players if p.team}
        if len(teams) > 2:
            s.notes.append(f"A showdown file normally holds one game; this one has {len(teams)} teams.")
        missing = [p.name for p in s.players if p.cpt_id is None]
        if missing:
            s.notes.append(f"{len(missing)} players have no captain row: they can only be a FLEX.")
    return s


# ------------------------------------------------------------------------------------------------ matching
_SUFFIX = re.compile(r"\s+(jr|sr|ii|iii|iv|v)\.?$", re.I)


def _name_key(name: str | None) -> str:
    """'D.J. Moore' == 'DJ Moore', 'Amon-Ra St. Brown' == 'Amon Ra St Brown', 'Marvin Harrison Jr.' == 'Marvin Harrison',
    'De'Von Achane' == 'DeVon Achane', accents dropped: lower-case letters and digits only, a generational suffix cut."""
    s = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode()
    s = re.sub(r"\s+", " ", s.replace(".", " ").strip())
    s = _SUFFIX.sub("", s)
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _initial_key(name: str | None) -> str:
    """'Gabe Davis' -> 'g|davis' (first initial + last name key): the second, reported step for nicknames."""
    s = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode()
    s = _SUFFIX.sub("", re.sub(r"\s+", " ", s.replace(".", " ").strip()))
    parts = s.split(" ")
    if len(parts) < 2:
        return ""
    return f"{re.sub(r'[^a-z]', '', parts[0].lower())[:1]}|{_name_key(' '.join(parts[1:]))}"


def match(players: Sequence[SlatePlayer], pool: pd.DataFrame,
          directory: pd.DataFrame | None = None) -> tuple[dict[str, str], list[dict], dict[str, int]]:
    """({slate key: our key}, unmatched, counts by how). ``pool``: the players we VALUE this week (``key``,
    ``player_name``, ``position``, ``team`` — a skill player's and a kicker's key is his gsis id, a defense's
    ``DEF:<team>``); ``directory`` (optional, same columns): everyone else we know, so a player we know but do not
    project reads "no projection" rather than "not found".

    Steps, each needing ONE candidate: (1) a defense by its team; (2) the normalised whole name + position + team;
    (3) first initial + last name + position + team (a nickname: "Gabe" for Gabriel). Two candidates = ambiguous;
    none = not found (with the team and position we have him at, when the name exists elsewhere). Never guessed."""
    pool = pool.copy()
    pool["nk_"] = pool["player_name"].map(_name_key)
    pool["ik_"] = pool["player_name"].map(_initial_key)
    by_name: dict[tuple, list[str]] = {}
    by_init: dict[tuple, list[str]] = {}
    by_key = {}
    for r in pool.itertuples():
        by_name.setdefault((r.nk_, r.position, r.team), []).append(r.key)
        by_init.setdefault((r.ik_, r.position, r.team), []).append(r.key)
        by_key[r.key] = r
    loose: dict[str, list[tuple[str, str | None]]] = {}
    for src in (pool, directory if directory is not None else pool.iloc[0:0]):
        for r in src.itertuples():
            loose.setdefault(_name_key(r.player_name), []).append((r.position, r.team))
    dir_keys: dict[tuple, list[str]] = {}
    if directory is not None and not directory.empty:
        for r in directory.itertuples():
            dir_keys.setdefault((_name_key(r.player_name), r.position, r.team), []).append(r.key)
    out: dict[str, str] = {}
    unmatched: list[dict] = []
    counts = {"team": 0, "name": 0, "initial": 0}
    for p in players:
        base = {"key": p.key, "name": p.name, "position": p.position, "team": p.team or p.site_team,
                "salary": p.salary}
        if p.team is None:
            unmatched.append({**base, "reason": f"“{p.site_team}” is not an NFL team code we know"})
            continue
        if p.position == "DEF":
            k = f"DEF:{p.team}"
            if k in by_key:
                out[p.key] = k
                counts["team"] += 1
            else:
                unmatched.append({**base, "reason": f"no projection for the {p.team} defense this week"})
            continue
        nk = _name_key(p.name)
        cands = by_name.get((nk, p.position, p.team), [])
        how = "name"
        if not cands:
            cands = by_init.get((_initial_key(p.name), p.position, p.team), [])
            how = "initial"
        if len(cands) == 1:
            out[p.key] = cands[0]
            counts[how] += 1
            continue
        if len(cands) > 1:
            names = ", ".join(sorted(str(by_key[c].player_name) for c in cands))
            unmatched.append({**base, "reason": f"ambiguous: {len(cands)} of our {p.position}s on {p.team} match "
                                                f"({names}); not valued"})
            continue
        if dir_keys.get((nk, p.position, p.team)):
            unmatched.append({**base, "reason": "no projection for him this week (unknown, not 0)"})
            continue
        elsewhere = [f"{pos} on {t}" if t else pos for pos, t in loose.get(nk, [])
                     if (pos, t) != (p.position, p.team)]
        if elsewhere:
            unmatched.append({**base, "reason": f"listed as {p.position} on {p.team}; we have that name as "
                                                f"{' and '.join(sorted(set(elsewhere))[:3])}"})
        else:
            unmatched.append({**base, "reason": f"no {p.position} of that name on {p.team} in our players"})
    return out, unmatched, counts


# ------------------------------------------------------------------------------------------------ pricing
QUANTILES = ("p10", "p25", "p50", "p75", "p90")


def price_site(board, site: str) -> pd.DataFrame:
    """The week's players priced in the site's scoring: one row per player we value — ``key`` (gsis id; a defense
    ``DEF:<team>``), ``gsis_id``, ``player_name``, ``position``, ``team``, ``proj``, ``p10`` … ``p90``, ``report_status``,
    ``implied_team_total``, ``reference`` (the scoring whose range was borrowed) and the stat line (``targets`` …).

    The skill lines: ``scoring.price_projected`` on the stored stat line (``BONUS_AT_ODDS``); the range: the nearest
    reference scoring's (``anyleague.reference_for``: the fitted scoring whose prices of the week's lines are closest),
    each offset scaled by the ratio of the two prices (``anyleague.approximate_ranges``) — approximate, docs/DFS.md.
    K / DEF: ``anyleague.kd_values`` (``kdef.price`` on the kd1.0 line; the range = the nearest reference's fixed
    offsets; no 50% range)."""
    from . import anyleague as A
    from .scoring import price_projected
    scoring = SCORING[site]
    line = board.line
    stats = line[list(A.STAT_LINE)].rename(columns=A.STAT_LINE).apply(pd.to_numeric, errors="coerce").fillna(0.0)
    stats["position"] = line["position"].to_numpy()
    proj = pd.Series(price_projected(stats, scoring, ev=True if BONUS_AT_ODDS else None), index=line.index, dtype=float)
    ref = A.reference_for(proj, board, scoring, f"dfs:{site}")
    if ref is None:
        ranges = pd.DataFrame(np.nan, index=proj.index, columns=list(QUANTILES))
    else:
        ranges = A.approximate_ranges(proj, board.fitted[ref])
    st = board.status.reindex(proj.index) if not board.status.empty else pd.DataFrame(index=proj.index)
    sk = pd.DataFrame({"key": proj.index, "gsis_id": proj.index, "position": line["position"].to_numpy(),
                       "proj": proj.round(2).to_numpy()})
    for q in QUANTILES:
        sk[q] = ranges[q].to_numpy()
    for c in ("team", "player_name", "report_status", "implied_team_total"):
        sk[c] = st[c].to_numpy() if c in st else None
    for c in A.STAT_LINE.values():
        sk[c] = stats[c].round(2).to_numpy()
    sk["reference"] = ref
    frames = [sk]
    for pos in ("K", "DEF") if site == "dk" else ("DEF",):      # a kicker plays in DraftKings showdown only
        src, kd = A.kd_values(scoring, pos, board)
        if kd.empty:
            continue
        kd = kd.copy()
        team = kd["team"].where(kd["team"].notna(), kd["unit_id"]).map(team_code)
        kd["key"] = [f"DEF:{t}" for t in team] if pos == "DEF" else kd["unit_id"].astype(str)
        kd["gsis_id"] = None if pos == "DEF" else kd["unit_id"].astype(str)
        kd["team"] = team
        kd["position"] = pos
        kd = kd.rename(columns={"proj_points": "proj"})
        kd["reference"] = src
        # the line's few numbers a reason reads ("2.4 sacks, 1.1 takeaways, 19.5 points allowed")
        raw = board.kd[board.kd["position"] == pos].drop_duplicates("unit_id").set_index("unit_id")

        def num(c: str, _raw=raw, _kd=kd) -> np.ndarray:
            return pd.to_numeric(_raw[c], errors="coerce").reindex(_kd["unit_id"]).to_numpy(dtype=float) \
                if c in _raw else np.full(len(_kd), np.nan)
        if pos == "DEF":
            kd["sacks"] = num("proj_sacks")
            kd["takeaways"] = num("proj_interceptions") + num("proj_fumble_recoveries")
            kd["points_allowed"] = num("proj_points_allowed")
        else:
            kd["field_goals"] = sum(num(c) for c in raw.columns if c.startswith("proj_fg_made_"))
            kd["extra_points"] = num("proj_pat_made")
        frames.append(kd[["key", "gsis_id", "position", "proj", "p10", "p90", "team", "player_name", "report_status",
                          "implied_team_total", "reference",
                          *(["sacks", "takeaways", "points_allowed"] if pos == "DEF" else ["field_goals", "extra_points"])]])
    out = pd.concat([f for f in frames if not f.empty], ignore_index=True)
    out = out[out["team"].notna() & out["proj"].notna()]
    return out.drop_duplicates("key").reset_index(drop=True)


# ------------------------------------------------------------------------------------------------ value
FIT_MIN_PLAYERS = 8            # fewer priced players at a position: no line (the screen says so)
FIT_MIN_POINTS = 1.0           # players projected under 1 point do not set the line (inactive backups at the minimum)
VALUE_Z = 1.0                  # undervalued / overpriced: at least one typical miss of the line away from it
VALUE_MIN_GAP = 1.0            # … and at least a point
LIST_TOP = 8


def fit_line(salary: Sequence[float], points: Sequence[float]) -> dict | None:
    """The straight line salary -> projected points by least squares: ``{slope_per_1000, intercept, n, rmse}``;
    None with fewer than ``FIT_MIN_PLAYERS`` points or no salary spread."""
    x, y = np.asarray(salary, dtype=float), np.asarray(points, dtype=float)
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    if len(x) < FIT_MIN_PLAYERS or np.ptp(x) <= 0:
        return None
    slope, icpt = np.polyfit(x, y, 1)
    res = y - (icpt + slope * x)
    rmse = float(np.sqrt(np.sum(res ** 2) / max(1, len(x) - 2)))
    return {"slope_per_1000": round(float(slope) * 1000, 3), "intercept": round(float(icpt), 3), "n": int(len(x)),
            "rmse": round(rmse, 3), "_slope": float(slope), "_icpt": float(icpt)}


def value(df: pd.DataFrame, contest: str) -> tuple[pd.DataFrame, dict]:
    """Per player: ``pts_per_k`` (projection per $1,000), ``ceil_per_k`` (high-end outcome per $1,000), ``line_points``
    (what his salary buys at his position on this slate), ``value_gap`` (projection − line, points), ``value_z`` (the gap
    in the line's typical misses), ``value_rank`` (1 = the most undervalued at his position), ``value_call``
    (undervalued / overpriced / None). Showdown: one line over the whole slate (every player competes for the same
    FLEX spots). ``df`` needs ``position``, ``salary``, ``proj``, ``p90``, ``out`` (cannot play)."""
    d = df.copy()
    k = d["salary"].astype(float) / 1000.0
    d["pts_per_k"] = (d["proj"] / k).round(2)
    d["ceil_per_k"] = (d["p90"] / k).round(2)
    for c in ("line_points", "value_gap", "value_z"):
        d[c] = np.nan
    d["value_rank"] = pd.Series([None] * len(d), dtype=object)
    d["value_call"] = pd.Series([None] * len(d), dtype=object)
    groups = {"ALL": d.index} if contest == "dk_showdown" else {p: g.index for p, g in d.groupby("position")}
    fits: dict[str, dict | None] = {}
    for pos, idx in groups.items():
        g = d.loc[idx]
        use = g[(g["proj"] >= FIT_MIN_POINTS) & ~g["out"].astype(bool)]
        f = fit_line(use["salary"], use["proj"])
        fits[pos] = None if f is None else {k2: v for k2, v in f.items() if not k2.startswith("_")}
        if f is None:
            continue
        line = f["_icpt"] + f["_slope"] * g["salary"].astype(float)
        gap = g["proj"] - line
        d.loc[idx, "line_points"] = line.round(2)
        d.loc[idx, "value_gap"] = gap.round(2)
        d.loc[idx, "value_z"] = (gap / f["rmse"]).round(2) if f["rmse"] > 0 else np.nan
        d.loc[idx, "value_rank"] = gap.rank(ascending=False, method="min").astype(int).astype(object)
        floor = g["salary"].min()
        und = (gap >= VALUE_MIN_GAP) & (gap / max(f["rmse"], 1e-9) >= VALUE_Z) & ~g["out"].astype(bool)
        ovr = ((gap <= -VALUE_MIN_GAP) & (gap / max(f["rmse"], 1e-9) <= -VALUE_Z) & ~g["out"].astype(bool)
               & (g["salary"] > floor))
        d.loc[idx[und.to_numpy()], "value_call"] = "undervalued"
        d.loc[idx[ovr.to_numpy()], "value_call"] = "overpriced"
    return d, fits


# ------------------------------------------------------------------------------------------------ lineups
@dataclass
class LineupResult:
    lineups: list[dict]
    notes: list[str]
    solve_ms: list[float]


def _range_total(ps: Iterable[Mapping], mult: Iterable[float]) -> tuple[float | None, float | None]:
    """The lineup's low-end / high-end outcome (P10 / P90 of the total) assuming the players' weeks are independent:
    each player's spread from his own P10-P90 (as a normal: (P90 - P10) / 2.563 = one sd), the total's from the sum of
    the variances. Teammates and opponents are not independent (a shootout lifts both): a stack's real range is wider."""
    var, tot = 0.0, 0.0
    for p, m in zip(ps, mult, strict=True):
        lo, hi = p.get("p10"), p.get("p90")
        if lo is None or hi is None or not (math.isfinite(lo) and math.isfinite(hi)):
            return None, None
        sd = (hi - lo) / 2.563 * m
        var += sd * sd
        tot += float(p["proj"]) * m
    s = math.sqrt(var)
    return round(max(0.0, tot - 1.2816 * s), 1), round(tot + 1.2816 * s, 1)


@dataclass(frozen=True)
class Stack:
    """IN-4: how people build a roster. ``with_qb``: at least this many of the quarterback's own pass catchers (WR / TE
    of his team; 0 = no stack); ``bring_back``: at least one RB / WR / TE from his opponent; ``no_def_vs_qb``: no team
    defense that plays against the lineup's quarterback. Classic and full-roster contests (one QB slot) only."""
    with_qb: int = 0
    bring_back: bool = False
    no_def_vs_qb: bool = False

    @property
    def any(self) -> bool:
        return bool(self.with_qb or self.bring_back or self.no_def_vs_qb)

    def rules(self) -> list[tuple[str, str]]:
        """(rule id, the rule in words) for each rule set."""
        out = []
        if self.with_qb:
            out.append(("with_qb", f"the quarterback with at least {'one' if self.with_qb == 1 else self.with_qb} of "
                                   "his own pass catchers (WR or TE)"))
        if self.bring_back:
            out.append(("bring_back", "a bring-back: at least one RB, WR or TE from the quarterback's opponent"))
        if self.no_def_vs_qb:
            out.append(("no_def_vs_qb", "no defense playing against the quarterback"))
        return out


PASS_CATCHERS = frozenset({"WR", "TE"})
BRING_BACK = frozenset({"RB", "WR", "TE"})


def _stack_rows(pool: list[Mapping], var: list[tuple[int, int]], stack: Stack, only: str | None = None
                ) -> list[tuple[list[int], list[float], float, float]]:
    """The stack rules as rows (cols, vals, lb, ub) over the flat model's variables (one per player), ONE row per team
    (``Q_t`` = the sum of the team's quarterbacks, at most 1 since the lineup has one QB): with Q_t in, k of the team's
    pass catchers are in (``sum - k Q_t >= 0``), one of its opponent's RB / WR / TE (``sum - Q_t >= 0``), and no defense
    that plays against it (``x_d + Q_t <= 1``). A team-level row is the sum of the per-quarterback rows, so it is the
    tighter one (a backup QB adds a column, not a row). ``only``: one rule's rows (to name the rule a slate cannot meet)."""
    col = {i: j for j, (i, _g) in enumerate(var)}
    rows: list[tuple[list[int], list[float], float, float]] = []
    qbs_by_team: dict[str, list[int]] = {}
    opp_of: dict[str, str | None] = {}
    for i in col:
        if pool[i]["position"] == "QB" and pool[i].get("team"):
            t = str(pool[i]["team"])
            qbs_by_team.setdefault(t, []).append(col[i])
            opp_of[t] = opp_of.get(t) or pool[i].get("opponent")
    for team, qcols in sorted(qbs_by_team.items()):
        opp = opp_of.get(team)
        if stack.with_qb and only in (None, "with_qb"):
            mates = [col[i] for i in col if pool[i]["position"] in PASS_CATCHERS and pool[i].get("team") == team]
            rows.append(([*mates, *qcols], [1.0] * len(mates) + [-float(stack.with_qb)] * len(qcols), 0.0, np.inf))
        if stack.bring_back and only in (None, "bring_back"):
            back = [col[i] for i in col if pool[i]["position"] in BRING_BACK and opp and pool[i].get("team") == opp]
            rows.append(([*back, *qcols], [1.0] * len(back) + [-1.0] * len(qcols), 0.0, np.inf))
        if stack.no_def_vs_qb and only in (None, "no_def_vs_qb"):
            for i in col:
                if pool[i]["position"] == "DEF" and pool[i].get("opponent") == team:
                    rows.append(([*qcols, col[i]], [1.0] * (len(qcols) + 1), 0.0, 1.0))
    return rows


def solve_lineups(players: Sequence[Mapping], contest: str, *, mode: str = "cash", n: int = 1,
                  locks: Iterable[str] = (), excludes: Iterable[str] = (), time_limit: float = SOLVE_SECONDS,
                  stack: Stack | None = None, max_exposure: float | None = None) -> LineupResult:
    """The best lineup (and the next ``n`` - 1, each different by at least one player) for the site's slots and cap.

    IN-4: ``stack`` (``Stack``: the QB with his pass catchers, a bring-back, no defense against the QB) adds linear
    rules — the objective is unchanged; a rule the slate cannot meet is named in the notes. ``max_exposure`` (0-1]: across
    the ``n`` lineups a player appears in at most ``max(1, floor(max_exposure * n))`` of them (a player set to always in
    is exempt — he is in every lineup by request).

    ``players``: dicts with ``key``, ``position`` (ours), ``salary``, ``team``, ``game`` (any id of his game),
    ``proj``, ``p90``, ``p10``, ``out`` (cannot play: left out unless locked) and, in showdown, ``cpt_salary`` (no
    captain row: FLEX only). ``mode``: ``cash`` maximises the projection, ``tournament`` the high-end outcome (a player
    without one is left out). Exact: an integer program solved to optimality (HiGHS, ``MIP_GAP``: exact at the inputs'
    hundredths). ``time_limit`` (``SOLVE_SECONDS``, 5) is the budget for ALL the lineups: a solve cut short returns its
    best lineup with ``proven: false``; the lineups found before the budget ran out are returned and the notes say so.
    At most ``MAX_PLAYERS`` players, ``MAX_GAMES`` games, ``MAX_TEAMS`` teams (refused in words before any solve)."""
    from scipy import sparse
    from scipy.optimize import Bounds, LinearConstraint, milp
    t_start = time.perf_counter()
    c = CONTESTS[contest]
    n = max(1, min(int(n), MAX_LINEUPS))
    locks, excludes = set(map(str, locks)), set(map(str, excludes))
    notes: list[str] = []
    obj_key = "p90" if mode == "tournament" else "proj"
    if len(players) > MAX_PLAYERS:
        return LineupResult([], [f"Too many players for one build: at most {MAX_PLAYERS:,}."], [])
    pool = []
    for p in players:
        k = str(p["key"])
        if k in excludes and k not in locks:
            continue
        v = p.get(obj_key)
        if v is None or not math.isfinite(float(v)):
            if k in locks:
                notes.append(f"{p.get('name') or k} is set to always in but has no "
                             f"{'high-end outcome' if obj_key == 'p90' else 'projection'}: left out.")
            continue
        if p.get("out") and k not in locks:
            continue
        pool.append(p)
    n_games = len({str(p.get("game") or p.get("team")) for p in pool})
    n_teams = len({str(p.get("team")) for p in pool})
    if n_games > MAX_GAMES or n_teams > MAX_TEAMS:
        return LineupResult([], [f"That is {n_games} games and {n_teams} teams: an NFL slate has at most {MAX_GAMES} games."], [])
    # variables. Classic / full roster (no multiplier): ONE per player (in the lineup or not), each position's count
    # between its own slots and its own + the FLEX slots that admit it — the same lineups as a slot-by-slot model
    # without its symmetry (an RB at RB2 or at FLEX is one lineup); the slots are assigned after the solve
    # (``_assign``). Showdown: (player, CPT | FLEX), a captain needing a captain row. The constraint matrix is built
    # ONCE, sparse (a few nonzeros a row); each next lineup adds one sparse row.
    flat = all(g.multiplier == 1.0 for g in c.groups)
    var: list[tuple[int, int]] = []
    elig_all = frozenset().union(*(g.elig for g in c.groups))
    for i, p in enumerate(pool):
        if flat:
            if p["position"] in elig_all:
                var.append((i, -1))
            continue
        for gi, g in enumerate(c.groups):
            if p["position"] not in g.elig:
                continue
            if g.multiplier != 1.0 and p.get("cpt_salary") is None:
                continue
            var.append((i, gi))
    nv = len(var)
    if nv == 0:
        return LineupResult([], ["No player can fill a slot."], [])

    def mult(gi: int) -> float:
        return 1.0 if gi < 0 else c.groups[gi].multiplier

    def sal(i: int, gi: int) -> float:
        return float(pool[i]["cpt_salary"] if mult(gi) != 1.0 else pool[i]["salary"])

    by_player: dict[int, list[int]] = {}
    by_pos: dict[str, list[int]] = {}
    by_group: dict[int, list[int]] = {}
    teams: dict[str, list[int]] = {}
    games: dict[str, list[int]] = {}
    for j, (i, gi) in enumerate(var):
        by_player.setdefault(i, []).append(j)
        by_pos.setdefault(pool[i]["position"], []).append(j)
        by_group.setdefault(gi, []).append(j)
        teams.setdefault(str(pool[i].get("team")), []).append(j)
        games.setdefault(str(pool[i].get("game") or pool[i].get("team")), []).append(j)
    spread: list[tuple[dict[str, list[int]], int, str]] = []
    if c.min_games:
        spread.append((games, c.min_games, "game"))
    if c.min_teams:
        spread.append(({t: js for t, js in teams.items() if t != "None"}, c.min_teams, "team"))
    for groups, need, word in spread:
        if len(groups) < need:
            notes.append(f"The slate has {len(groups)} {word}{'s' if len(groups) != 1 else ''} we value: "
                         f"{SITE_NAMES[c.site]} needs players from {need}.")
            return LineupResult([], notes, [])
    extra = sum(len(g) for g, _n, _w in spread)
    width = nv + extra
    rr: list[int] = []
    cc: list[int] = []
    vv: list[float] = []
    lo: list[float] = []
    hi: list[float] = []

    def add(cols: Sequence[int], vals: Sequence[float] | float, lb: float, ub: float) -> None:
        r = len(lo)
        vals = [float(vals)] * len(cols) if isinstance(vals, (int, float)) else vals
        rr.extend([r] * len(cols))
        cc.extend(cols)
        vv.extend(vals)
        lo.append(lb)
        hi.append(ub)

    lb_var = np.zeros(width)
    if flat:
        for pos in sorted(elig_all):
            own = sum(g.count for g in c.groups if g.elig == frozenset({pos}))
            flex = sum(g.count for g in c.groups if pos in g.elig and len(g.elig) > 1)
            add(by_pos.get(pos, []), 1.0, float(own), float(own + flex))
        add(list(range(nv)), 1.0, float(c.size), float(c.size))
        for i, js in by_player.items():                    # "always in": the player's variable fixed at 1
            if str(pool[i]["key"]) in locks:
                lb_var[js] = 1.0
    else:
        for gi, g in enumerate(c.groups):
            add(by_group.get(gi, []), 1.0, float(g.count), float(g.count))
        for i, js in by_player.items():                    # a player is the captain or a FLEX, not both
            add(js, 1.0, 1.0 if str(pool[i]["key"]) in locks else 0.0, 1.0)
    for k in locks:
        if not any(str(pool[i]["key"]) == k for i in by_player):
            name = next((p.get("name") for p in players if str(p["key"]) == k), k)
            notes.append(f"{name} is set to always in but cannot fill a slot in this contest: left out.")
    add(list(range(nv)), [sal(i, gi) for i, gi in var], 0.0, float(c.cap))
    if c.max_per_team:
        for _t, js in teams.items():
            add(js, 1.0, 0.0, float(c.max_per_team))
    # ---- IN-4: stacks (flat contests: one QB slot). Rows only — the objective is never changed by a rule
    stack = stack if stack is not None and stack.any else None
    if stack is not None and not flat:
        notes.append("Stacks apply to classic and full-roster contests (one quarterback slot): not to showdown.")
        stack = None
    stack_span = (len(lo), len(lo))
    if stack is not None:
        for cols, vals, lb_, ub_ in _stack_rows(pool, var, stack):
            add(cols, vals, lb_, ub_)
        stack_span = (stack_span[0], len(lo))
    cap_each = None
    if max_exposure is not None and n > 1:
        cap_each = max(1, math.floor(float(max_exposure) * n + 1e-9))
    used: dict[int, int] = {}
    # ---- end IN-4
    # "players from at least N games" (DraftKings classic) / "… N teams" (showdown): one binary y per game (team) after
    # the x's, y_k <= the sum of game k's x's, sum y >= N
    at = nv
    for groups, need, _w in spread:
        first = at
        for _g, js in groups.items():
            add([*js, at], [-1.0] * len(js) + [1.0], -np.inf, 0.0)
            at += 1
        add(list(range(first, at)), 1.0, float(need), float(at - first))
    base = sparse.csr_matrix((vv, (rr, cc)), shape=(len(lo), width))
    pts = np.concatenate([np.array([float(pool[i][obj_key]) * mult(gi) for i, gi in var]), np.zeros(extra)])
    integrality = np.ones(width)
    ub_var = np.ones(width)
    cut_rows: list[list[int]] = []
    lineups: list[dict] = []
    times: list[float] = []
    deadline = t_start + float(time_limit)
    for _k in range(n):
        left = deadline - time.perf_counter()
        if left < 0.05:
            notes.append(f"The {time_limit:g}-second budget ran out after {len(lineups)} lineup"
                         f"{'s' if len(lineups) != 1 else ''}: those are the ones shown.")
            break
        if cut_rows:
            cuts = sparse.csr_matrix((np.ones(sum(len(r) for r in cut_rows)),
                                      ([k for k, r in enumerate(cut_rows) for _ in r], [j for r in cut_rows for j in r])),
                                     shape=(len(cut_rows), width))
            a_ = sparse.vstack([base, cuts], format="csr")
        else:
            a_ = base
        lo_ = lo + [-np.inf] * len(cut_rows)
        hi_ = hi + [float(c.size - 1)] * len(cut_rows)
        t0 = time.perf_counter()
        res = milp(-pts, constraints=LinearConstraint(a_, lo_, hi_), integrality=integrality,
                   bounds=Bounds(lb_var, np.maximum(ub_var, lb_var)),
                   options={"time_limit": max(0.05, left), "mip_rel_gap": MIP_GAP, "disp": False})
        times.append(round((time.perf_counter() - t0) * 1000, 1))
        if res.x is None:
            if res.status == 1:
                notes.append(f"The {time_limit:g}-second budget ran out before lineup {len(lineups) + 1} was found: "
                             "stopped there.")
            elif not lineups and stack is not None:
                notes.append(_stack_infeasible(pool, var, stack, (rr, cc, vv, lo, hi), stack_span, width, lb_var,
                                               deadline))
            elif not lineups:
                notes.append("No lineup fits the cap and the rules with these players set to always in and left out.")
            elif cap_each is not None:
                notes.append(f"Only {len(lineups)} different lineup{'s' if len(lineups) != 1 else ''} fit the cap, the "
                             f"rules and the exposure limit (each player in at most {cap_each} of {n}).")
            else:
                notes.append(f"Only {len(lineups)} different lineup{'s' if len(lineups) != 1 else ''} fit the cap and the rules.")
            break
        x = np.round(res.x[:nv]).astype(int)
        chosen = [var[j] for j in range(nv) if x[j] == 1]
        if flat:
            chosen = _assign(c, pool, [i for i, _g in chosen])
        lineups.append(_lineup(c, pool, chosen, proven=res.status == 0, mode=mode))
        cut_rows.append(sorted(j for i in {i for i, _gi in chosen} for j in by_player[i]))
        if cap_each is not None:                         # ---- IN-4: a player at his exposure cap sits out the rest
            for i in {i for i, _gi in chosen}:
                used[i] = used.get(i, 0) + 1
                if used[i] >= cap_each and str(pool[i]["key"]) not in locks:
                    ub_var[by_player[i]] = 0.0
    if stack is not None and lineups:
        notes.append("Stacks: every lineup has " + "; ".join(t for _r, t in stack.rules()) + ".")
    if cap_each is not None and lineups:
        notes.append(f"Exposure: each player in at most {cap_each} of the {n} lineups"
                     f"{' (players set to always in are in every one)' if locks else ''}.")
    return LineupResult(lineups, notes, times)


def _stack_infeasible(pool: list[Mapping], var: list[tuple[int, int]], stack: Stack, model: tuple, span: tuple[int, int],
                      width: int, lb_var: np.ndarray, deadline: float) -> str:
    """No lineup with the stack rules: which rule. The model's rows without the stack rows (``span``), then each rule
    alone on top of them (bounded by what is left of the time budget); the first rule that alone has no lineup is
    named."""
    from scipy import sparse
    from scipy.optimize import Bounds, LinearConstraint, milp
    rr, cc, vv, lo_all, hi_all = model
    a, b = span
    keep_rows = [r for r in range(len(lo_all)) if not a <= r < b]
    new_id = {r: k for k, r in enumerate(keep_rows)}
    nz = [k for k, r in enumerate(rr) if r in new_id]
    base = sparse.csr_matrix(([vv[k] for k in nz], ([new_id[rr[k]] for k in nz], [cc[k] for k in nz])),
                             shape=(len(keep_rows), width))
    lo = [lo_all[r] for r in keep_rows]
    hi = [hi_all[r] for r in keep_rows]
    keep = len(keep_rows)
    words = dict(stack.rules())
    for rule, text in stack.rules():
        if deadline - time.perf_counter() < 0.05:
            break
        extra = _stack_rows(pool, var, stack, only=rule)
        if not extra:
            continue                                     # no row: the rule cannot be what is in the way
        m = sparse.csr_matrix(([v for _c, vs, _l, _u in extra for v in vs],
                               ([k for k, (cs, _v, _l, _u) in enumerate(extra) for _ in cs],
                                [j for cs, _v, _l, _u in extra for j in cs])), shape=(len(extra), width))
        a_ = sparse.vstack([base, m], format="csr")
        res = milp(np.zeros(width), constraints=LinearConstraint(a_, lo[:keep] + [e[2] for e in extra],
                                                                    hi[:keep] + [e[3] for e in extra]),
                   integrality=np.ones(width), bounds=Bounds(lb_var, np.ones(width)),
                   options={"time_limit": max(0.05, deadline - time.perf_counter()), "disp": False})
        if res.x is None and res.status != 1:
            return (f"No lineup can meet {text} on this slate with these players set to always in and left out. "
                    "Turn that rule off or change who is in.")
    return ("No lineup meets all the stack rules together (" + "; ".join(words.values()) + ") with these players set "
            "to always in and left out. Turn one off.")


def _assign(c: Contest, pool: list[Mapping], ids: list[int]) -> list[tuple[int, int]]:
    """The chosen players into the site's slots: each position's own slots first (the higher projections), the rest to
    the FLEX (kick-off times are not read: late swap is not handled, docs/DFS.md)."""
    left = sorted(ids, key=lambda i: (-float(pool[i]["proj"] or 0), str(pool[i]["key"])))
    out: list[tuple[int, int]] = []
    for single in (True, False):
        for gi, g in enumerate(c.groups):
            if (len(g.elig) == 1) != single:
                continue
            take = [i for i in left if pool[i]["position"] in g.elig][: g.count]
            out += [(i, gi) for i in take]
            left = [i for i in left if i not in take]
    return out


def _lineup(c: Contest, pool: list[Mapping], chosen: list[tuple[int, int]], *, proven: bool, mode: str) -> dict:
    slots = []
    for gi, g in enumerate(c.groups):
        mine = sorted((pool[i] for i, g2 in chosen if g2 == gi), key=lambda p: (-float(p["proj"]), str(p["key"])))
        for p in mine:
            slots.append({"slot": g.label, "multiplier": g.multiplier, "player": p})
    # the FLEX of a classic contest: the RB / WR / TE that sits there (the upload's order: QB RB RB WR WR WR TE FLEX DST)
    salary = sum(int(s["player"]["cpt_salary"] if s["multiplier"] != 1.0 else s["player"]["salary"]) for s in slots)
    proj = sum(float(s["player"]["proj"]) * s["multiplier"] for s in slots)
    ceil = [s["player"].get("p90") for s in slots]
    lo, hi = _range_total([s["player"] for s in slots], [s["multiplier"] for s in slots])
    return {"slots": [{"slot": s["slot"], "key": str(s["player"]["key"]), "multiplier": s["multiplier"],
                       "salary": int(s["player"]["cpt_salary"] if s["multiplier"] != 1.0 else s["player"]["salary"]),
                       "proj": round(float(s["player"]["proj"]) * s["multiplier"], 2),
                       "upload_id": str(s["player"].get("cpt_id") if s["multiplier"] != 1.0 else
                                        s["player"].get("site_id") or s["player"]["key"])}
                      for s in slots],
            "salary": salary, "salary_left": c.cap - salary, "proj": round(proj, 2),
            "ceiling_sum": None if any(v is None for v in ceil) else round(sum(float(v) * s["multiplier"]
                                                                                for v, s in zip(ceil, slots, strict=True)), 2),
            "low": lo, "high": hi, "proven": proven, "mode": mode}


# ------------------------------------------------------------------------------------------------ the upload file
_FORMULA = ("=", "+", "-", "@", "\t", "\r")


def safe_cell(v) -> str:
    """A CSV cell a spreadsheet will not run: a leading = + - @ (or tab / CR) gets a leading apostrophe (OWASP)."""
    s = "" if v is None else str(v)
    return "'" + s if s.startswith(_FORMULA) else s


def upload_csv(contest: str, lineups: Sequence[Mapping]) -> str:
    """The site's lineup-upload CSV: the header row of slot words, one row per lineup of the file's own ids, in the
    header's order (DraftKings classic QB, RB, RB, WR, WR, WR, TE, FLEX, DST; showdown CPT then 5 FLEX; FanDuel QB, RB,
    RB, WR, WR, WR, TE, FLEX, DEF). Every cell through ``safe_cell``."""
    c = CONTESTS[contest]
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow([safe_cell(h) for h in c.upload_header])
    for lu in lineups:
        w.writerow([safe_cell(s["upload_id"]) for s in lu["slots"]])
    return buf.getvalue()


# ------------------------------------------------------------------------------------------------ the week
def detect_week(games: Iterable[str], schedule: pd.DataFrame) -> int | None:
    """The regular-season week whose games the file lists: ``schedule`` has ``week``, ``home_team``, ``away_team``
    (nflverse codes); each "AWY@HOM" of the file (site codes) is looked up; the week holding the most of them wins
    (None when none is found)."""
    hits: dict[int, int] = {}
    for g in games:
        a, h, _ = _game(g)
        a, h = team_code(a), team_code(h)
        if not a or not h:
            continue
        m = schedule[((schedule["away_team"] == a) & (schedule["home_team"] == h))
                     | ((schedule["away_team"] == h) & (schedule["home_team"] == a))]
        for w in set(m["week"].astype(int)):
            hits[w] = hits.get(w, 0) + 1
    if not hits:
        return None
    best = max(hits.values())
    return min(w for w, k in hits.items() if k == best)


# ------------------------------------------------------------------------------------------------ published slates (IN-4)
# One salary file per site per week, published by the site's owner in the repo (``dfs/slates/``), so a visitor does not
# upload one: ``<season>-w<ww>-<dk|fd>[-<label>].csv`` (label: lower-case letters and digits, default ``main``). The id
# the API serves is the name without ``.csv`` and with the label always written (``2026-w05-dk-main``) — matched against
# a strict pattern, never used as a path.
SLATE_FILE_RE = re.compile(r"^(?P<season>20\d\d)-w(?P<week>\d\d)-(?P<site>dk|fd)(?:-(?P<label>[a-z0-9]{1,20}))?\.csv$")
SLATE_ID_RE = re.compile(r"^(?P<season>20\d\d)-w(?P<week>\d\d)-(?P<site>dk|fd)-(?P<label>[a-z0-9]{1,20})$")
MAX_PUBLISHED = 32                     # files read from the folder at most (two sites x a few contests x two weeks)


def slate_name(filename: str) -> dict | None:
    """``2026-w05-dk.csv`` -> ``{id: 2026-w05-dk-main, season: 2026, week: 5, site: dk, label: main}``; None for any
    other name (it is listed as unreadable, never served)."""
    m = SLATE_FILE_RE.match(filename or "")
    if not m:
        return None
    week = int(m["week"])
    if not 1 <= week <= 22:
        return None
    label = m["label"] or "main"
    return {"id": f"{m['season']}-w{m['week']}-{m['site']}-{label}", "season": int(m["season"]), "week": week,
            "site": m["site"], "label": label}


def slate_id_ok(slate_id: str | None) -> bool:
    """A published slate's id as the API takes it: the strict pattern, nothing else (never a path)."""
    return bool(SLATE_ID_RE.match(str(slate_id or ""))) and len(str(slate_id)) <= 40


# ------------------------------------------------------------------------------------------------ context (IN-4)
# Andrew (2026-10-06): "a way to find value … looking at things that might even be beyond what the model can provide for.
# Like cornerback matchups don't necessarily play into the projections." Each signal is shown as context beside the
# projection, never folded into it, and says whether the projection already holds it. That label is not a claim
# written by hand: it is read from the model's own input list (``projections.FEATURES_BY_POSITION``) through
# ``SIGNAL_INPUTS`` — the columns each signal is made of. tests/test_in4_dfs.py asserts every label against the list.
SIGNAL_INPUTS: dict[str, tuple[str, ...]] = {
    # the defense against his position: the marts' standard rank and points allowed (what the projection reads as-of
    # the week: opp_rank_std, opp_allowed_*)
    "defense": ("opp_rank_std", "opp_allowed_std", "opp_allowed_l4", "f_opp_allowed_diff"),
    # the cornerback call (mart_cb_matchups): the likely corner, his rank, shutdown — no projection input is made of it
    "corner": ("cb_corner_rank", "cb_shutdown", "cb_certainty"),
    # his share of the team's targets / carries / snaps: the projection reads the last 3 games and the season
    "role": ("target_share_l3", "target_share_std", "carry_share_l3", "carry_share_std", "snap_pct_l3", "snap_pct_std"),
    # routes run per dropback: not an input (the participation file arrives after the season; projections.py says why)
    "routes": ("route_participation_l3",),
    # the betting line: implied team total, spread, over/under
    "game": ("implied_team_total", "spread_line", "total_line"),
    # game-day weather (plan D3: tested by the harness, not kept in the model)
    "weather": ("wx_wind_mph", "wx_gust_mph", "wx_precip_in", "wx_temp_f", "wx_dome", "wx_snow", "wx_windy", "wx_cold"),
}
SIGNAL_LABEL = {"defense": "Defense vs his position", "corner": "Cornerback", "role": "Role trend",
                "routes": "Role trend (routes)", "game": "Game environment", "weather": "Weather"}
IN_WORDS, OUT_WORDS = "In the projection", "Not in the projection"
TONES = ("favorable", "neutral", "difficult")
SKILL = ("QB", "RB", "WR", "TE")


@functools.lru_cache(maxsize=8)
def model_inputs(position: str) -> frozenset[str]:
    """The projection's inputs at the position (``projections.FEATURES_BY_POSITION``: the model that prices the board;
    the positions are a closed set, so the cache is too)."""
    from .projections import FEATURES_BY_POSITION
    return frozenset(FEATURES_BY_POSITION.get(position, ()))


def in_projection(signal: str, position: str) -> bool:
    """True when any column the signal is made of is an input of the projection at that position."""
    return bool(set(SIGNAL_INPUTS[signal]) & model_inputs(position))


def projection_table() -> dict[str, dict[str, bool]]:
    """{signal: {position: in the projection}} — the screen's "what the projection holds" line, from the model."""
    return {s: {p: in_projection(s, p) for p in SKILL} for s in SIGNAL_INPUTS}


# ---- role trend: his last two games against his season before them (summed numerator over summed denominator)
ROLE_RECENT = 2                 # the recent window: his last 2 games played
ROLE_MIN_BEFORE = 2             # … against at least 2 games before them (else: too small a sample, nothing said)
ROLE_MEASURES: dict[str, dict] = {
    # measure: numerator, denominator, the change that counts (share points), positions, the signal it belongs to, words
    "target_share": {"num": "targets", "den": "team_targets", "move": 0.05, "pos": {"RB", "WR", "TE"},
                     "signal": "role", "words": "of the targets"},
    "carry_share": {"num": "carries", "den": "team_carries", "move": 0.10, "pos": {"RB"}, "signal": "role",
                    "words": "of the carries"},
    "snap_share": {"num": "offense_snaps", "den": "team_snaps", "move": 0.10, "pos": {"RB", "WR", "TE"},
                   "signal": "role", "words": "of the snaps"},
    "route_rate": {"num": "routes", "den": "team_dropbacks_with_participation", "move": 0.10, "pos": {"RB", "WR", "TE"},
                   "signal": "routes", "words": "routes run per dropback"},
}
ROLE_MIN_DEN = {"team_targets": 20.0, "team_carries": 20.0, "team_snaps": 60.0, "team_dropbacks_with_participation": 30.0}


def _ratio(g: pd.DataFrame, num: str, den: str) -> float | None:
    if num not in g or den not in g:
        return None
    ok = g[num].notna() & g[den].notna() & (pd.to_numeric(g[den], errors="coerce") > 0)
    if not ok.any() or ok.sum() < len(g):            # a game without the measure: unknown, not zero
        return None
    d = float(pd.to_numeric(g.loc[ok, den]).sum())
    if d < ROLE_MIN_DEN.get(den, 1.0) * len(g) / ROLE_RECENT:
        return None
    return float(pd.to_numeric(g.loc[ok, num]).sum()) / d


def role_trend(games: pd.DataFrame, position: str) -> dict | None:
    """``games``: one player's games this season BEFORE this week, played only (``week``, ``targets``, ``team_targets``,
    ``carries``, ``team_carries``, ``offense_snaps``, ``team_snaps``, ``routes``, ``team_dropbacks_with_participation``).
    His last ``ROLE_RECENT`` games against the ones before them (at least ``ROLE_MIN_BEFORE``): each measure as the
    summed numerator over the summed denominator; a measure moved when it changed by its ``move`` or more. "role up"
    when at least one moved up and none down, "role down" the other way, else None (nothing said; mixed or too small)."""
    if position not in ("RB", "WR", "TE") or games is None or games.empty:
        return None
    g = games.sort_values("week")
    recent, before = g.tail(ROLE_RECENT), g.iloc[: max(0, len(g) - ROLE_RECENT)]
    if len(recent) < ROLE_RECENT or len(before) < ROLE_MIN_BEFORE:
        return None
    moved = []
    for name, m in ROLE_MEASURES.items():
        if position not in m["pos"]:
            continue
        a, b = _ratio(recent, m["num"], m["den"]), _ratio(before, m["num"], m["den"])
        if a is None or b is None:
            continue
        if abs(a - b) >= m["move"] - 1e-9:
            moved.append({"measure": name, "recent": round(a, 3), "before": round(b, 3), "change": round(a - b, 3),
                          "signal": m["signal"], "words": m["words"]})
    ups, downs = [x for x in moved if x["change"] > 0], [x for x in moved if x["change"] < 0]
    if not moved or (ups and downs):
        return None
    up = bool(ups)
    parts = [f"{x['recent']:.0%} {x['words']} ({x['before']:.0%})" for x in moved]
    signals = {x["signal"] for x in moved}
    return {"trend": "up" if up else "down", "tone": "favorable" if up else "difficult",
            "words": (f"Role {'up' if up else 'down'} in his last two games (the {len(before)} before in brackets): "
                      + ", ".join(parts) + "."), "measures": moved,
            "signal": "role" if "role" in signals else "routes", "games": [len(recent), len(before)]}


# ---- game environment: the betting line (nflverse: spread_line > 0 = the home team favoured by that many)
GAME_HIGH, GAME_LOW = 26.0, 18.0       # the cards' own marks (cards.reason_pieces): a team expected to score 26+ / 18-


def implied_total(total: float | None, spread: float | None, home: bool | None) -> float | None:
    """The team's implied points: (over/under ± spread) / 2 — int_player_week_universe's formula."""
    if total is None or spread is None or home is None or not (math.isfinite(total) and math.isfinite(spread)):
        return None
    return (total + spread) / 2.0 if home else (total - spread) / 2.0


def game_environment(team: str | None, total: float | None, spread: float | None, home: bool | None) -> dict | None:
    """The game's over/under, the spread from his team's side and the team's implied total, with a tone for a skill
    player: favourable at ``GAME_HIGH``+ points expected, difficult at ``GAME_LOW`` or fewer; None without a line."""
    imp = implied_total(total, spread, home)
    if imp is None or not team:
        return None
    mine = spread if home else -spread           # > 0: his team favoured
    side = (f"{team} favoured by {abs(mine):g}" if mine > 0 else f"{team} underdogs by {abs(mine):g}" if mine < 0
            else "a pick'em")
    tone = "favorable" if imp >= GAME_HIGH else "difficult" if imp <= GAME_LOW else "neutral"
    return {"total": float(total), "spread": float(mine), "implied": round(imp, 1), "tone": tone,
            "words": f"Over/under {total:g}, {side}: Vegas expects {team} to score {imp:.1f}."}


# ---- weather: only an outdoor game with a forecast loaded, and only a flag that matters (wind, snow, rain, cold)
WIND_MPH = 15.0                        # int_game_weather's wx_windy mark
RAIN_IN = 0.1                          # forecast precipitation over the game's first hours
COLD_F = 32.0


def weather_flag(source: str | None, dome: int | None, wind: float | None, precip: float | None, temp: float | None,
                 snow: int | None, position: str) -> dict | None:
    """``int_game_weather`` for his game -> a flag or None. Dome / no forecast (``source`` other than ``forecast``) /
    nothing unusual: None. Wind, snow or rain is difficult for a passer or a receiver and said, without a tone, for a
    back; cold alone is said without a tone."""
    if source != "forecast" or (dome is not None and int(dome) == 1):
        return None
    bits, bad = [], False
    if wind is not None and math.isfinite(float(wind)) and float(wind) >= WIND_MPH:
        bits.append(f"wind {float(wind):.0f} mph")
        bad = True
    if snow is not None and int(snow) == 1:
        bits.append("snow")
        bad = True
    elif precip is not None and math.isfinite(float(precip)) and float(precip) >= RAIN_IN:
        bits.append(f"rain ({float(precip):.2f} in)")
        bad = True
    if temp is not None and math.isfinite(float(temp)) and float(temp) < COLD_F:
        bits.append(f"{float(temp):.0f}°F")
    if not bits:
        return None
    tone = "difficult" if bad and position in ("QB", "WR", "TE") else None
    return {"tone": tone, "words": "Forecast at kickoff (outdoors): " + ", ".join(bits) + "."}


# ---- the signals together, and "Worth a look"
# The brief's rule was "at least two favourable signals that are not in the projection". Read from the model, only the
# corner call is both outside the projection and able to be favourable (role shares, the defense rank and the betting
# line are inputs; weather only ever warns; routes per dropback is outside but unknown this season) — so that rule could
# never fire. "Worth a look" is therefore: at least WORTH_MIN_FAVOURABLE favourable signals, at least WORTH_MIN_OUTSIDE
# of them outside the projection, and no difficult signal outside it. docs/DFS.md § Context says so.
WORTH_MIN_FAVOURABLE = 2
WORTH_MIN_OUTSIDE = 1


def signals(position: str, matchup: Mapping | None, role: Mapping | None, game: Mapping | None,
            weather: Mapping | None) -> list[dict]:
    """The player's context signals, each ``{signal, label, tone, words, in_projection, projection_words}``. ``matchup``
    is ``matchup_board.matchup_context``'s entry for him (``defense``, ``cb``); a corner call that is not "likely" is
    said but carries no tone (IN-3's rule: an unclear call never moves anything)."""
    out: list[dict] = []

    def put(sig: str, tone: str | None, words: str | None, **extra) -> None:
        if not words:
            return
        inp = in_projection(sig, position) if position in SKILL else False
        out.append({"signal": sig, "label": SIGNAL_LABEL[sig], "tone": tone if tone in TONES else None, "words": words,
                    "in_projection": inp, "projection_words": IN_WORDS if inp else OUT_WORDS, **extra})

    if matchup:
        d = matchup.get("defense") or {}
        put("defense", d.get("tone"), d.get("words"), rank=d.get("tough_rank"), n_ranked=d.get("n_ranked"))
        cb = matchup.get("cb") if position == "WR" else None
        if cb:
            sure = cb.get("certainty") == "likely"
            put("corner", cb.get("tone") if sure else None, cb.get("words"), shutdown=bool(cb.get("shutdown")) and sure,
                certainty=cb.get("certainty"), corner=cb.get("corner"), corner_rank=cb.get("corner_rank"))
    if role:
        put(role.get("signal", "role"), role.get("tone"), role.get("words"), trend=role.get("trend"))
    if game:
        put("game", game.get("tone"), game.get("words"), total=game.get("total"), spread=game.get("spread"),
            implied=game.get("implied"))
    if weather:
        put("weather", weather.get("tone"), weather.get("words"))
    return out


def worth(sigs: Sequence[Mapping]) -> tuple[bool, list[str]]:
    """(worth a look, the reasons in words): the rule above; the reasons are the favourable signals, outside ones first."""
    fav = [s for s in sigs if s.get("tone") == "favorable"]
    out_fav = [s for s in fav if not s.get("in_projection")]
    out_bad = [s for s in sigs if s.get("tone") == "difficult" and not s.get("in_projection")]
    ok = len(fav) >= WORTH_MIN_FAVOURABLE and len(out_fav) >= WORTH_MIN_OUTSIDE and not out_bad
    ordered = sorted(fav, key=lambda s: bool(s.get("in_projection")))
    return ok, [f"{s['words']} ({s['projection_words'].lower()})" for s in ordered] if ok else []


def worth_a_look(rows: Sequence[Mapping], by: str = "proj", per_position: int = 8) -> dict[str, list[str]]:
    """{position: [keys]} of the players worth a look (``row["worth"]``), who can play, ordered by ``by`` (projection;
    points per $1,000 when salaries are present), then key."""
    out: dict[str, list[str]] = {}
    for r in rows:
        if not r.get("worth") or r.get("out"):
            continue
        out.setdefault(str(r.get("position")), []).append(r)
    return {p: [str(r["key"]) for r in sorted(v, key=lambda r: (-(r.get(by) if _finite(r.get(by)) else -1e9),
                                                                   str(r["key"])))[:per_position]]
            for p, v in out.items()}


def _finite(v) -> bool:
    try:
        return v is not None and math.isfinite(float(v))
    except (TypeError, ValueError):
        return False
