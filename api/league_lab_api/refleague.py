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

IN-2 (Wave I-N): the key is a small closed family (``platforms.parse_reference``: ``ref:<scoring>[.sf][.tep][.p6]
[.t8|.t10|.t14]`` — PPR, Half PPR, Standard, ESPN's default, Yahoo's default; superflex, TE premium, 6-pt passing
touchdowns; 8 / 10 / 12 / 14 teams: 160 keys). ``league(key)`` builds the shape's scoring and slots; the league's name
is the scoring in words ("Half PPR", never "No league"); ``value_table(key)`` is every player's value in a *typical
league of that shape* (docs/METRICS.md § "Value without a league"); ``card(out, key)`` turns a player card into the
browsing one (no ownership lines, the value block, one line at the foot).
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
    """The key in words: "Half PPR", "PPR · superflex · 10 teams" (IN-2: every key of the family)."""
    return shape(key).words


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
    """The Sleeper-shaped league of a reference key (LeagueNotFound for anything else). IN-2: the shape's scoring,
    slots and size; the name is the scoring in words."""
    sh = shape(key)
    scoring = scoring_of(sh)
    return {"league_id": sh.key, "name": sh.words, "season": str(_season()), "status": "in_season",
            "sport": "nfl", "scoring_settings": scoring, "roster_positions": slots_of(sh),
            "total_rosters": sh.teams, "settings": {"num_teams": sh.teams, "playoff_week_start": 15, "type": 0},
            "reference": True, "reference_scoring": SCORINGS[sh.base][0], "scoring_label": sh.words}


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


FREE_AGENT_LABEL = " · free agent"     # IN-2: a search hit's label ("Puka Nacua · WR · LAR · free agent")


def public(out: Any) -> Any:
    """The answer with every ownership field taken out, at any depth (a reference key has no rosters). IN-2: a label's
    " · free agent" too (an ownership word, absent while browsing)."""
    if isinstance(out, dict):
        return {k: (v.removesuffix(FREE_AGENT_LABEL) if k == "label" and isinstance(v, str) else public(v))
                for k, v in out.items() if k not in OWNERSHIP}
    if isinstance(out, list):
        return [public(v) for v in out]
    return out


def needs_league_body() -> dict:
    return {"error": NEEDS_LEAGUE, "detail": NEEDS_LEAGUE, "code": "needs_league"}


def needs_league() -> JSONResponse:
    return JSONResponse(needs_league_body(), status_code=404, headers={"Cache-Control": "no-store"})


RECORD_NOTE = ("Our record is kept in Half PPR scoring (4 points per passing touchdown): the scoring of the league we "
               "project every morning.")


def record(key: str) -> dict:
    """``/api/record`` for a reference key: the model's record as the reference house league keeps it (Half PPR — the
    league the nightly projects every morning), without its lineup record (``decisions``: those are managers' teams);
    for ``ref:ppr`` / ``ref:std`` the answer says it is kept in Half PPR. ``available: false`` when no house league."""
    from .applib import ui
    from .myweek import NotFound
    from .ondemand import record as league_record
    k = str(key).strip().lower()
    if platforms.parse_reference(k) is None:                                   # ---- IN-2: the whole family
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


# ---- IN-2 (Wave I-N): the lab without a league — the scoring choices, a value for every player, the browsing card ----
from dataclasses import dataclass  # noqa: E402 - the block stays self-contained

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from league_lab import memo  # noqa: E402

# base -> (the fitted reference scoring it starts from, its words, what it changes in that scoring)
SCORINGS: dict[str, tuple[str, str, dict[str, float]]] = {
    "ppr": ("ppr", "PPR", {}),
    "half": ("scrubs", "Half PPR", {}),
    "std": ("standard", "Standard", {}),
    # ESPN's default (PPR since 2019): 1 per catch, 1 per 25 passing yards, 4 a passing TD, -2 per interception, -2 a
    # fumble lost, 1 per 10 rushing / receiving yards, 6 a TD, 2 a two-point conversion
    "espn": ("ppr", "ESPN default", {"pass_int": -2.0}),
    # Yahoo's default (help.yahoo.com/kb/SLN6489, as the brief verified it): half a point per catch, 1 per 25 passing
    # yards, 4 a passing TD, -1 per interception, 1 per 10 rushing / receiving yards, 6 a TD, 2 a two-point conversion,
    # -2 a fumble lost — the Half PPR seed's offense exactly
    "yahoo": ("scrubs", "Yahoo default", {"pass_int": -1.0}),
}
SCORING_ORDER = ("ppr", "half", "std", "espn", "yahoo")
SCORING_RULES = {
    "ppr": "1 point per catch, 4 per passing touchdown, −1 per interception.",
    "half": "Half a point per catch, 4 per passing touchdown, −1 per interception.",
    "std": "No points for a catch, 4 per passing touchdown, −1 per interception.",
    "espn": "ESPN's default: 1 point per catch, 4 per passing touchdown, −2 per interception.",
    "yahoo": "Yahoo's default: half a point per catch, 4 per passing touchdown, −1 per interception (the same points as "
             "Half PPR).",
}
SLEEPER_WORDS = "Sleeper has no single default: a Sleeper league picks PPR, Half PPR or Standard when it is made."
OPTION_WORDS = {"sf": "superflex", "tep": "TE premium", "p6": "6-pt pass TD"}
TEP = {"bonus_rec_te": 0.5}          # +0.5 per tight-end catch (the te_premium seed's key)
P6 = {"pass_td": 6.0}
BENCH = 6                            # the typical league's bench, every size (stated wherever the value is)
KD_WORDS = "Kickers and defenses use the kicking and defense rules of the scoring it starts from."
FOOT = "Open your league to see who has him and what he is worth to your team."
VALUE_POSITIONS = ("QB", "RB", "WR", "TE", "K", "DEF")
BENCH_POSITIONS = ("QB", "RB", "WR", "TE")       # a typical bench holds no kicker or defense
FLEX_ELIG = ("RB", "WR", "TE")
SUPERFLEX_ELIG = ("QB", "RB", "WR", "TE")
SINGLE = {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "K": 1, "DEF": 1}
LAST_REG_SQL = "select max(week) as w from analytics.dim_game where season = %s and season_type = 'REG'"
# 160 keys, but the value tables of one scoring share one priced rest of season (`anyleague`'s `ros` region): a table
# here is ~600 rows; the region keeps the 24 most recent (memo LRU) for 10 minutes
_values = memo.region("ref_values", ttl=600.0, max_entries=24)


@dataclass(frozen=True)
class Shape:
    key: str
    base: str
    sf: bool
    tep: bool
    p6: bool
    teams: int

    @property
    def scoring_key(self) -> str:
        """The key without the roster's shape (superflex, size): every shape of one scoring prices the same lines."""
        return "ref:" + self.base + (".tep" if self.tep else "") + (".p6" if self.p6 else "")

    @property
    def scoring_words(self) -> str:
        bits = [SCORINGS[self.base][1]] + [OPTION_WORDS[o] for o, on in (("tep", self.tep), ("p6", self.p6)) if on]
        return " · ".join(bits)

    @property
    def words(self) -> str:
        bits = [SCORINGS[self.base][1]] + [OPTION_WORDS[o] for o, on in (("sf", self.sf), ("tep", self.tep),
                                                                          ("p6", self.p6)) if on]
        if self.teams != platforms.REF_TEAMS_DEFAULT:
            bits.append(f"{self.teams} teams")
        return " · ".join(bits)

    @property
    def assumes(self) -> str:
        """The one line a screen prints under a value: "Value in a 12-team Half PPR league, one quarterback"."""
        qbs = "two quarterbacks (superflex)" if self.sf else "one quarterback"
        art = "an" if self.teams == 8 else "a"
        return f"Value in {art} {self.teams}-team {self.scoring_words} league, {qbs}"


def shape(key: Any) -> Shape:
    """The shape of a reference key (LeagueNotFound for anything outside the family)."""
    p = platforms.parse_reference(key)
    if p is None:
        raise LeagueNotFound(f"not a reference league: {str(key)[:40]!r}")
    base, sf, tep, p6, teams = p
    return Shape(platforms.ref_key(base, sf, tep, p6, teams), base, sf, tep, p6, teams)


def scoring_of(sh: Shape) -> dict[str, float]:
    seed, _w, change = SCORINGS[sh.base]
    sc = _load_scorings().get(seed)
    if sc is None:
        raise LeagueNotFound(f"the reference scoring {seed!r} is not on this database")
    out = {**sc, **change}
    if sh.tep:
        out.update(TEP)
    if sh.p6:
        out.update(P6)
    return out


def slots_of(sh: Shape) -> list[str]:
    starters = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX"] + (["SUPER_FLEX"] if sh.sf else []) + ["K", "DEF"]
    return starters + ["BN"] * BENCH


def fitted_name(sh: Shape) -> str | None:
    """The fitted reference scoring this shape's scoring IS (exactly), else None (priced on request)."""
    mine = scoring_of(sh)
    for name, sc in _load_scorings().items():
        if {k: v for k, v in sc.items() if v} == {k: v for k, v in mine.items() if v}:
            return name
    return None


REF_LABELS = {"scrubs": "Half PPR", "ppr": "PPR", "standard": "Standard", "te_premium": "PPR with TE premium",
              "dynasty": "PPR, 6-pt pass TD and yardage bonuses"}


def pricing(sh: Shape, references: list[str] | None = None) -> dict:
    """How this key's numbers are priced, in one line (the screen's "how this is priced")."""
    fit = fitted_name(sh)
    if fit is not None:
        return {"fitted": True, "reference": fit,
                "words": f"Priced in {sh.scoring_words}: the ranges are fitted for this scoring every night."}
    refs = [r for r in (references or []) if r] or [SCORINGS[sh.base][0]]
    ref = REF_LABELS.get(refs[0], refs[0])
    return {"fitted": False, "reference": refs[0],
            "words": (f"Priced on request in {sh.scoring_words}: the same projected stat lines, this scoring's points; "
                      f"the ranges are the nearest scoring we fit every night ({ref}), stretched by how much more or "
                      "less this one pays for the same line.")}


def options() -> dict:
    """What the picker offers (GET /api/scoring/options): the scorings with their rules, the options, the sizes."""
    return {"default": DEFAULT, "keys": len(platforms.REF_KEYS),
            "scorings": [{"id": b, "label": SCORINGS[b][1], "rules": SCORING_RULES[b]} for b in SCORING_ORDER],
            "options": [{"id": o, "label": w} for o, w in OPTION_WORDS.items()],
            "teams": list(platforms.REF_TEAMS), "teams_default": platforms.REF_TEAMS_DEFAULT,
            "bench": BENCH, "sleeper": SLEEPER_WORDS, "kd": KD_WORDS}


# ------------------------------------------------------------------ the value of a player without a league
def starter_counts(points: dict[str, list[float]], teams: int, superflex: bool) -> dict[str, int]:
    """How many players of each position a typical league of this shape starts: each team's QB, 2 RB, 2 WR, TE, K and
    DEF from the top of each position; then FLEX (RB / WR / TE) and SUPER_FLEX (QB / RB / WR / TE), ``teams`` spots
    each, to the best players left, one at a time. ``points``: each position's season points, best first."""
    take = {p: min(SINGLE[p] * teams, len(points.get(p, []))) for p in VALUE_POSITIONS}
    for elig in (FLEX_ELIG,) + ((SUPERFLEX_ELIG,) if superflex else ()):
        for _ in range(teams):
            best, best_v = None, None
            for p in elig:
                lst = points.get(p, [])
                if take[p] < len(lst) and (best_v is None or lst[take[p]] > best_v):
                    best, best_v = p, lst[take[p]]
            if best is None:
                break
            take[best] += 1
    return take


def rostered_counts(points: dict[str, list[float]], teams: int, superflex: bool, bench: int = BENCH) -> dict[str, int]:
    """Starters plus the bench (``teams`` x ``bench`` spots shared by QB, RB, WR and TE in proportion to their starting
    spots, the largest remainders first; no kicker or defense on a bench), never more than the position holds."""
    st = starter_counts(points, teams, superflex)
    total = sum(st[p] for p in BENCH_POSITIONS)
    spots = teams * bench
    share = {p: spots * st[p] / total if total else 0.0 for p in BENCH_POSITIONS}
    base = {p: int(np.floor(share[p])) for p in BENCH_POSITIONS}
    left = spots - sum(base.values())
    for p in sorted(BENCH_POSITIONS, key=lambda x: (-(share[x] - base[x]), BENCH_POSITIONS.index(x)))[:max(0, left)]:
        base[p] += 1
    return {p: min(st[p] + base.get(p, 0), len(points.get(p, []))) for p in VALUE_POSITIONS}


def replacement_levels(points: dict[str, list[float]], rostered: dict[str, int]) -> dict[str, float]:
    """Per position the season points of the best player such a league leaves free (the one right after the last
    rostered); 0 when the league rosters every one of them."""
    return {p: (float(points[p][rostered[p]]) if rostered.get(p, 0) < len(points.get(p, [])) else 0.0)
            for p in VALUE_POSITIONS if p in points}


def values_from(frame: pd.DataFrame, teams: int, superflex: bool, bench: int = BENCH) -> tuple[pd.DataFrame, dict]:
    """The value of every player of ``frame`` (player_key, position, ros_points, is_ranked): season points above the
    replacement level of a typical league of this shape — the one function behind every value a reference key shows."""
    f = frame[frame["position"].isin(VALUE_POSITIONS) & frame["ros_points"].notna()].copy()
    ranked = f[f["is_ranked"].fillna(False).astype(bool)].sort_values(["ros_points", "player_key"], ascending=[False, True])
    points = {p: [float(v) for v in g["ros_points"]] for p, g in ranked.groupby("position", sort=False)}
    names = {p: list(g["player_name"]) for p, g in ranked.groupby("position", sort=False)} if "player_name" in ranked else {}
    rostered = rostered_counts(points, teams, superflex, bench)
    repl = replacement_levels(points, rostered)
    f["replacement"] = f["position"].map(repl).fillna(0.0)
    f["value"] = (f["ros_points"] - f["replacement"]).clip(lower=0).round(1)
    f = f.sort_values(["value", "ros_points", "player_key"], ascending=[False, False, True])
    f["value_rank_pos"] = f.groupby("position").cumcount() + 1
    who = {p: (names.get(p, [None] * (rostered[p] + 1))[rostered[p]] if rostered[p] < len(points.get(p, [])) else None)
           for p in repl}
    return f, {"rostered": rostered, "replacement": repl, "replacement_name": who,
               "starters": starter_counts(points, teams, superflex)}


def _window() -> tuple[int, int | None, int | None]:
    from .applib import cards
    from .db import query
    season = _season()
    week = cards.decision_week(season)
    if week is None:
        return season, None, None
    last = query(LAST_REG_SQL, (season,))
    lw = int(last["w"].iloc[0]) if not last.empty and pd.notna(last["w"].iloc[0]) else int(week)
    return season, int(week), lw


def value_table(key: str) -> tuple[pd.DataFrame, dict]:
    """(every player's value for the key, the facts behind it) — kept 10 minutes in the ``ref_values`` region. The
    season points are the league path's (this week to the last regular-season week, byes out, each week in this
    scoring: ``anyleague.ros_table``, the trade calculator's market window); the replacement is the typical league's."""
    from league_lab import anyleague as A

    from .db import query
    sh = shape(key)
    season, first, last = _window()
    ck = (sh.key, season, first, last, A.board_source())
    hit = _values.get(ck)
    if hit is not None:
        return hit
    if first is None or last is None or last < first:
        out = (pd.DataFrame(columns=["player_key", "gsis_id", "position", "ros_points", "value"]),
               {"why": "the regular season is over", "from_week": None, "last_week": None})
        return out
    lg = {"league_id": sh.scoring_key, "season": str(season), "scoring_settings": scoring_of(sh),
          "roster_positions": slots_of(Shape(sh.scoring_key, sh.base, False, sh.tep, sh.p6, 12)), "settings": {}}
    frame = A.ros_table(query, sh.scoring_key, lg, first, last, None)
    table, facts = values_from(frame, sh.teams, sh.sf)
    facts.update({"from_week": first, "last_week": last, "season": season, "teams": sh.teams, "superflex": sh.sf,
                  "bench": BENCH, "references": list(frame.attrs.get("references") or []),
                  "assumes": sh.assumes, "words": value_words(sh, first, last)})
    cols = ["player_key", "gsis_id", "player_name", "position", "team", "ros_points", "ros_games", "ros_p10",
            "ros_p90", "ros_rank_pos", "replacement", "value", "value_rank_pos", "weeks_json"]
    table = table[[c for c in cols if c in table]].reset_index(drop=True)
    return _values.put(ck, (table, facts))


def value_words(sh: Shape, first: int, last: int) -> str:
    span = f"weeks {first}–{last}" if last > first else f"week {first}"
    return (f"{sh.assumes}: his projected points over {span} (this week to the end of the regular season) above the "
            f"best player at his position that such a league leaves free. The league is typical, not real: each team "
            f"starts QB, 2 RB, 2 WR, TE, FLEX{', superflex' if sh.sf else ''}, K and DEF, and keeps {BENCH} on the "
            "bench (quarterbacks, backs, receivers and tight ends, in proportion to the starting spots).")


def value_of(key: str, gsis_ids: list[str]) -> dict[str, dict]:
    """gsis id -> {value, ros_points, replacement, position, value_rank_pos, pos_rank, ...} for the players given."""
    table, _facts = value_table(key)
    if table.empty:
        return {}
    t = table[table["gsis_id"].isin(set(gsis_ids))]
    return {str(r["gsis_id"]): r for r in t.to_dict("records")}


# ------------------------------------------------------------------ the player card while browsing
_OWN_HEADER = ("free agent", "player pool", "rostered", " on **")
_OWN_LINES = ("**Free agent**", "Not in this season's player pool", "Rostered by", "Free agent:")


def _words(text: Any, words: str, full: str | None = None) -> Any:
    """A card's sentence for a reference key: "this league's scoring" says the scoring; the shape's full label never
    reads as a scoring ("Half PPR · superflex · 10 teams scoring" → "Half PPR scoring")."""
    if not isinstance(text, str):
        return text
    if full and full != words:
        text = text.replace(f"{full} scoring", f"{words} scoring")
    for house, plain in HOUSE_SCORING.items():   # the house league the research is kept in, by its scoring's name
        text = text.replace(f"{house} scoring", f"{plain} scoring")
    return (text.replace("this league's scoring", f"{words} scoring").replace("this league's season", "the season")
            .replace("in this league", f"in {words}").replace("this league's final", "a typical league's final"))


HOUSE_SCORING = {"League of Scrubs": "Half PPR"}      # the reference house league (Half PPR, 4-pt pass TD)
HOWTO_BROWSING = {
    "- **Availability**": "- **Availability** says his injury status, his bye and whether his game has started.",
    "- **Value**": ("- **Value** is his projected points from this week to the end of the regular season above the best "
                    "player at his position that a typical league of this shape leaves free (the size and superflex "
                    "you picked, a bench of six); points per game is what he has scored, priced in this scoring."),
}


def _howto(text: Any, words: str, full: str) -> Any:
    """The card's "How to read this" while browsing: no owner in Availability, the value without a league."""
    if not isinstance(text, str):
        return text
    lines = []
    for ln in text.split("\n"):
        hit = next((v for k, v in HOWTO_BROWSING.items() if ln.startswith(k)), None)
        lines.append(hit if hit is not None else ln)
    return _words("\n".join(lines), words, full)


def _deep_words(v: Any, words: str, full: str) -> Any:
    if isinstance(v, str):
        return _words(v, words, full)
    if isinstance(v, dict):
        return {k: _deep_words(x, words, full) for k, x in v.items()}
    if isinstance(v, list):
        return [_deep_words(x, words, full) for x in v]
    return v


def _strip(sec: dict, words: str, full: str | None = None) -> dict:
    blocks = []
    for b in sec.get("blocks") or []:
        t = b.get("text")
        if isinstance(t, str):
            keep = [ln for ln in t.split("  \n") if not ln.strip().startswith(_OWN_LINES)]
            if not keep or not "".join(keep).strip():
                continue
            b = {**b, "text": _words("  \n".join(keep), words, full)}
        if b.get("kind") == "metrics":
            b = {**b, "metrics": [{**m, "help": _words(m.get("help"), words, full)} for m in b.get("metrics") or []]}
        blocks.append(b)
    return {**sec, "title": _words(sec.get("title"), words, full), "blocks": blocks}


def _fmt_pts(v: Any) -> str:
    return "—" if v is None or (isinstance(v, float) and np.isnan(v)) else f"{float(v):.0f}"


def value_block(key: str, gsis: str) -> dict | None:
    """The player's value without a league (the answer's ``ref_value``), or None when he has no rest of season."""
    sh = shape(key)
    table, facts = value_table(key)
    row = value_of(key, [gsis]).get(gsis)
    if row is None:
        return None
    pos = str(row["position"])
    return {"value": None if pd.isna(row["value"]) else float(row["value"]),
            "ros_points": None if pd.isna(row["ros_points"]) else float(row["ros_points"]),
            "replacement": float(row["replacement"]), "replacement_name": facts.get("replacement_name", {}).get(pos),
            "position": pos, "value_rank_pos": int(row["value_rank_pos"]),
            "pos_rank": None if pd.isna(row.get("ros_rank_pos")) else int(row["ros_rank_pos"]),
            "from_week": facts.get("from_week"), "last_week": facts.get("last_week"),
            "teams": sh.teams, "superflex": sh.sf, "bench": BENCH, "assumes": sh.assumes,
            "words": facts.get("words"), "pricing": pricing(sh, facts.get("references"))}


def card(out: dict, key: str) -> dict:
    """A player card for a reference key: the scoring in the head, no ownership line, the value block, the foot line."""
    sh = shape(key)
    words, full = sh.scoring_words, sh.words
    out = dict(out)
    out["league_name"] = full
    head = out.get("header")
    if isinstance(head, str):
        out["header"] = " · ".join(p for p in head.split(" · ") if not any(w in p for w in _OWN_HEADER))
    secs = {k: _strip(v, words, full) for k, v in (out.get("sections") or {}).items() if isinstance(v, dict)}
    try:
        vb = value_block(key, str(out.get("gsis_id") or ""))
    except Exception:  # noqa: BLE001 - no rest of season on this database: the card without a value, said so
        vb = None
    if "value" in secs:
        v = secs["value"]
        first = []
        if vb is not None and vb["value"] is not None:
            pos = vb["position"]
            first.append({"kind": "metrics", "metrics": [
                {"label": "Value", "value": _fmt_pts(vb["value"]), "delta": None, "trend": None,
                 "help": f"Season points above the best free {pos} in a typical league of this shape"},
                {"label": f"Points, wk {vb['from_week']}–{vb['last_week']}", "value": _fmt_pts(vb["ros_points"]),
                 "delta": None, "trend": None,
                 "help": f"Projected points from this week to the end of the regular season, {sh.scoring_words}"},
                {"label": "Rank", "value": f"{pos}{vb['value_rank_pos']}", "delta": None, "trend": None,
                 "help": f"By value among every {pos}"}]})
            repl = (f" ({vb['replacement_name']}, {_fmt_pts(vb['replacement'])} points)" if vb.get("replacement_name")
                    else f" ({_fmt_pts(vb['replacement'])} points)")
            first.append({"kind": "caption", "text": f"{vb['assumes']}: his points above the best free {pos}{repl}."})
        else:
            first.append({"kind": "unavailable", "text": "unavailable: no rest-of-season projection for him"})
        secs["value"] = {**v, "title": f"**Value** — {sh.assumes.removeprefix('Value ')}",
                         "blocks": first + list(v.get("blocks") or [])}
    out["sections"] = secs
    out["howto"] = _howto(out.get("howto"), words, full)
    if out.get("matchup_evidence") is not None:
        out["matchup_evidence"] = _deep_words(out["matchup_evidence"], words, full)
    out["ref_value"] = vb
    out["foot"] = FOOT
    out["scoring"] = {"key": sh.key, "label": words, "pricing": pricing(sh, (vb or {}).get("pricing", {}).get(
        "reference") and [vb["pricing"]["reference"]])}
    return out
# ---- end IN-2

# ------------------------------------------------------------------ the Stats table's value column while browsing
VALUE_COLUMN = "ros_value"
VALUE_POS = ["QB", "RB", "WR", "TE"]


def value_column(sh: Shape) -> dict:
    """The Stats catalogue's entry for the value without a league (not a window stat: the rest of the season)."""
    return {"id": VALUE_COLUMN, "label": "Value (rest of season, above replacement)", "short": "Value", "kind": "count",
            "format": "int", "per_game": False,
            "definition": (f"{sh.assumes}: his projected points from this week to the end of the regular season above "
                           "the best player at his position that such a league leaves free. Not a window stat: the "
                           "same whatever window is picked."),
            "numerator": "projected points, this week to the last regular-season week, minus the replacement's",
            "denominator": None, "aggregation": "the rest of the season (projections), not the window's games",
            "source": "our projections in this scoring; a typical league of this shape", "status": "derived",
            "positions": list(VALUE_POS), "needs": None, "reason": "no rest-of-season projection for him (unknown, not zero)",
            "group": "Games and points", "available": True}


def stats_values(d: dict, key: str, sort: str | None = None, direction: str | None = None,
                 cut: tuple[int, int] | None = None) -> dict:
    """A Stats answer (``/api/players?window=…``, its CSV) for a reference key with the value column: each row's
    ``ros_value``, the catalogue's entry, the column right after the points in every preset. Sorted by the value, the
    answer was asked for every row and ``cut`` = (offset, limit) is applied after the sort (never the page first)."""
    sh = shape(key)
    rows = d.get("players") or []
    try:
        vals = value_of(sh.key, [str(r.get("gsis_id")) for r in rows if r.get("gsis_id")])
    except Exception:  # noqa: BLE001 - no rest of season on this database: the column says unknown, never 0
        vals = {}
    for r in rows:
        v = vals.get(str(r.get("gsis_id")))
        r[VALUE_COLUMN] = None if v is None or pd.isna(v.get("value")) else float(v["value"])
    if sort == VALUE_COLUMN:
        desc = (direction or "desc").lower() != "asc"
        known = sorted((r for r in rows if r[VALUE_COLUMN] is not None), key=lambda r: (r[VALUE_COLUMN], ), reverse=desc)
        d["players"] = known + [r for r in rows if r[VALUE_COLUMN] is None]
        if cut is not None:
            off, n = max(0, int(cut[0] or 0)), max(1, int(cut[1] or 1))
            d["players"], d["offset"] = d["players"][off: off + n], off
    cat = [c for c in (d.get("catalogue") or []) if c.get("id") != VALUE_COLUMN]
    at = next((i + 1 for i, c in enumerate(cat) if c.get("id") == "points"), len(cat))
    d["catalogue"] = cat[:at] + [value_column(sh)] + cat[at:]          # beside the points (the table's order)

    def _after_points(cols: list) -> list:
        cols = [c for c in cols if c != VALUE_COLUMN]
        i = cols.index("points") + 1 if "points" in cols else 0
        return cols[:i] + [VALUE_COLUMN] + cols[i:]
    d["presets"] = [{**p, **({"columns": _after_points(p["columns"])} if isinstance(p.get("columns"), list) else {}),
                     **({"full": _after_points(p["full"])} if isinstance(p.get("full"), list) else {})}
                    for p in (d.get("presets") or [])]
    return d
# ---- end IN-2 (the Stats value column)


def compare_values(d: dict, key: str) -> dict:
    """``/api/compare`` for a reference key: each side's value without a league (``ros_value``) and what it assumes."""
    sh = shape(key)
    ids = [str((d.get(k) or {}).get("gsis_id")) for k in ("a", "b") if isinstance(d.get(k), dict)]
    try:
        vals = value_of(sh.key, ids)
    except Exception:  # noqa: BLE001 - no rest of season: no value (unknown, not zero)
        vals = {}
    for k in ("a", "b"):
        side = d.get(k)
        if isinstance(side, dict):
            v = vals.get(str(side.get("gsis_id")))
            side["ros_value"] = None if v is None or pd.isna(v.get("value")) else float(v["value"])
    d["value_assumes"] = sh.assumes
    return d
# ---- end IN-2 (Compare)
