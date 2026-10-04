"""Sleeper scoring keys -> nflverse weekly stat columns.

This is the single definition of how League Lab recomputes fantasy points from NFL statistics
under a league's ``scoring_settings``. The dbt seed ``scoring_stat_map.csv`` is generated from
this table (``league-lab`` never edits the seed by hand) and the ``league_points`` macro reads it.

Two kinds of key:

* ``stat`` — a count or yardage the weekly stats carry directly (``rec`` -> ``receptions``).
  The expression is a ``+``-joined list of columns of the ``stg_nflverse__player_stats_week``
  shape. The long-touchdown keys (``pass_td_40p`` ...) are counts too, derived from
  play-by-play (``int_player_game_pbp``) and joined onto the stats row.
* ``bonus`` — a per-game threshold (``bonus_rec_yd_100`` = a 100-199 receiving-yard game). The
  expression is ``column:low:high`` (``high`` empty = no upper bound); it pays the weight once
  when ``low <= column < high``. Sleeper's yardage buckets are exclusive ranges: a 210-yard game
  pays ``bonus_rec_yd_200`` and not ``bonus_rec_yd_100``. The long-touchdown counts are filed
  as ``bonus`` too (plain column expression) so one switch leaves every bonus out.

Only offensive player and kicker keys are mapped. Team-defense keys (``sack``, ``int``,
``pts_allow_*`` ...) are intentionally unmapped: individual/team defense projection is out of
MVP1 scope, and observed DEF points still arrive from Sleeper's own ``players_points``.

Known approximations (documented in docs/METRICS.md):
* ``fgmiss``/``xpmiss``: Sleeper charges blocked kicks as misses; nflverse separates them, so the
  expression adds ``*_blocked``. The distance buckets ``fgmiss_0_19`` ... map to nflverse's
  ``fg_missed_*`` buckets, which do not include blocked kicks (nflverse has no per-distance
  blocked buckets) — a blocked FG scores 0 there instead of the bucket's penalty.
* ``fgm_50p`` / ``fgmiss_50p`` = 50-59 + 60+ buckets.
* ``fum`` (any fumble) uses ``fumbles_total``; ``fum_lost`` uses ``fumbles_lost_total``.
* Long-touchdown keys count plays with ``yards_gained >= 40`` (``>= 50``) that scored, by the
  passer / rusher / receiver on the play (laterals credit the first receiver).
* Position-conditional catch premiums (``bonus_rec_te``, ``bonus_rec_rb``, ``bonus_rec_wr``:
  ``SLEEPER_POSITION_MAP``, plan F1) are priced by ``compute_points`` when the stats row carries the
  player's ``position`` (the projection's ``price`` passes it), and only then. They stay OUT of
  ``MAPPED_KEYS`` and of the seed: the SQL ``league_points`` macro has no position to condition on,
  so ``unmapped_keys`` keeps reporting them and dbt's reconciliation test still flags a league that
  enables one instead of silently under-counting. The ``*_fd`` first-down keys are unmapped.
* Expected points (``int_expected_points_week``) apply the ``stat`` keys only: a threshold on an
  expected yardage would pay a bonus deterministically at 100.0 expected yards and not at 99.9.
"""

from __future__ import annotations

import json as _json
import math as _math
import os as _os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass as _dataclass
from dataclasses import field as _field

# sleeper_key -> (sql expression over stg_nflverse__player_stats_week columns, description)
SLEEPER_STAT_MAP: dict[str, tuple[str, str]] = {
    "pass_yd": ("passing_yards", "passing yards"),
    "pass_td": ("passing_tds", "passing touchdowns"),
    "pass_int": ("passing_interceptions", "interceptions thrown"),
    "pass_2pt": ("passing_2pt_conversions", "2-pt conversions passed"),
    "rush_yd": ("rushing_yards", "rushing yards"),
    "rush_td": ("rushing_tds", "rushing touchdowns"),
    "rush_2pt": ("rushing_2pt_conversions", "2-pt conversions rushed"),
    "rec": ("receptions", "receptions"),
    "rec_yd": ("receiving_yards", "receiving yards"),
    "rec_td": ("receiving_tds", "receiving touchdowns"),
    "rec_2pt": ("receiving_2pt_conversions", "2-pt conversions received"),
    "fum": ("fumbles_total", "fumbles (any)"),
    "fum_lost": ("fumbles_lost_total", "fumbles lost"),
    "fum_rec_td": ("fumble_recovery_tds", "fumble recovery touchdowns"),
    "st_td": ("special_teams_tds", "special teams touchdowns"),
    "fgm_0_19": ("fg_made_0_19", "FG made 0-19"),
    "fgm_20_29": ("fg_made_20_29", "FG made 20-29"),
    "fgm_30_39": ("fg_made_30_39", "FG made 30-39"),
    "fgm_40_49": ("fg_made_40_49", "FG made 40-49"),
    "fgm_50p": ("fg_made_50_59 + fg_made_60_", "FG made 50+"),
    "fgmiss": ("fg_missed + fg_blocked", "FG missed incl. blocked"),
    "fgmiss_0_19": ("fg_missed_0_19", "FG missed 0-19 (blocked kicks not bucketed by nflverse)"),
    "fgmiss_20_29": ("fg_missed_20_29", "FG missed 20-29"),
    "fgmiss_30_39": ("fg_missed_30_39", "FG missed 30-39"),
    "fgmiss_40_49": ("fg_missed_40_49", "FG missed 40-49"),
    "fgmiss_50p": ("fg_missed_50_59 + fg_missed_60_", "FG missed 50+"),
    "xpm": ("pat_made", "PAT made"),
    "xpmiss": ("pat_missed + pat_blocked", "PAT missed incl. blocked"),
}

# Long-touchdown keys: counts derived from play-by-play (int_player_game_pbp), joined onto the
# stats row by the models that score. kind = bonus so expected points leave them out.
SLEEPER_LONG_TD_MAP: dict[str, tuple[str, str]] = {
    "pass_td_40p": ("pass_tds_40p", "passing TDs of 40+ yards (play-by-play)"),
    "pass_td_50p": ("pass_tds_50p", "passing TDs of 50+ yards (play-by-play)"),
    "rush_td_40p": ("rush_tds_40p", "rushing TDs of 40+ yards (play-by-play)"),
    "rush_td_50p": ("rush_tds_50p", "rushing TDs of 50+ yards (play-by-play)"),
    "rec_td_40p": ("rec_tds_40p", "receiving TDs of 40+ yards (play-by-play)"),
    "rec_td_50p": ("rec_tds_50p", "receiving TDs of 50+ yards (play-by-play)"),
}

# Per-game yardage bonuses: sleeper_key -> (column, low, high_exclusive | None, description).
# Sleeper's buckets are exclusive ranges (100-199, 200+), so exactly one pays for a given game.
SLEEPER_BONUS_MAP: dict[str, tuple[str, int, int | None, str]] = {
    "bonus_pass_yd_300": ("passing_yards", 300, 400, "300-399 passing yard game"),
    "bonus_pass_yd_400": ("passing_yards", 400, None, "400+ passing yard game"),
    "bonus_rush_yd_100": ("rushing_yards", 100, 200, "100-199 rushing yard game"),
    "bonus_rush_yd_200": ("rushing_yards", 200, None, "200+ rushing yard game"),
    "bonus_rec_yd_100": ("receiving_yards", 100, 200, "100-199 receiving yard game"),
    "bonus_rec_yd_200": ("receiving_yards", 200, None, "200+ receiving yard game"),
}

# Position-conditional per-catch premiums (plan F1, the TE-premium reference scoring): sleeper_key ->
# (stat column, position, description). Priced by compute_points only for a stats row that carries
# ``position``; not in MAPPED_KEYS / the seed (the SQL macro cannot condition on position).
SLEEPER_POSITION_MAP: dict[str, tuple[str, str, str]] = {
    "bonus_rec_te": ("receptions", "TE", "per catch by a tight end (TE premium)"),
    "bonus_rec_rb": ("receptions", "RB", "per catch by a running back"),
    "bonus_rec_wr": ("receptions", "WR", "per catch by a wide receiver"),
}

# Every key League Lab can recompute, with its kind.
MAPPED_KEYS: dict[str, str] = (
    {k: "stat" for k in SLEEPER_STAT_MAP}
    | {k: "bonus" for k in SLEEPER_LONG_TD_MAP}
    | {k: "bonus" for k in SLEEPER_BONUS_MAP}
)

# Python evaluation of the same expressions (used by tests and the synthetic fixture generator).
_PY_EXPR: dict[str, tuple[str, ...]] = {
    k: tuple(part.strip() for part in expr.split("+"))
    for k, (expr, _) in {**SLEEPER_STAT_MAP, **SLEEPER_LONG_TD_MAP}.items()
}


def bonus_hit(stats: Mapping[str, float | int | None], key: str) -> int:
    """1 when a yardage-bonus key pays for this stat row, else 0."""
    column, low, high = SLEEPER_BONUS_MAP[key][:3]
    value = float(stats.get(column) or 0)
    return int(value >= low and (high is None or value < high))


def compute_points(
    stats: Mapping[str, float | int | None], scoring: Mapping[str, float], *, include_bonuses: bool = True
) -> float:
    """Fantasy points for one player-game row under a Sleeper ``scoring_settings`` dict.

    ``include_bonuses=False`` scores the ``stat`` keys only (what expected points use). A position-
    conditional premium (``SLEEPER_POSITION_MAP``) counts when ``stats["position"]`` is its position
    (a per-catch value, so it counts with or without bonuses); a row without ``position`` prices it 0.
    """
    total = 0.0
    for key, weight in scoring.items():
        if not weight:
            continue
        kind = MAPPED_KEYS.get(key)
        if kind is None:
            pk = SLEEPER_POSITION_MAP.get(key)
            if pk is not None and stats.get("position") == pk[1]:
                total += float(stats.get(pk[0]) or 0) * float(weight)
            continue
        if kind == "bonus" and not include_bonuses:
            continue
        if key in SLEEPER_BONUS_MAP:
            value = float(bonus_hit(stats, key))
        else:
            value = sum(float(stats.get(c) or 0) for c in _PY_EXPR[key])
        total += value * float(weight)
    return round(total, 2)


def unmapped_keys(scoring: Mapping[str, float]) -> list[str]:
    """Scoring keys with a non-zero weight that the stat map (and so the SQL macro) cannot recompute (DEF,
    first downs...). The position-conditional premiums are listed too: only a stats row that carries the
    player's position prices them (``priced_keys`` is the projection's view)."""
    return sorted(k for k, w in scoring.items() if w and k not in MAPPED_KEYS)


def priced_keys(scoring: Mapping[str, float], columns: Iterable[str] | None = None) -> dict[str, float]:
    """The non-zero keys ``compute_points`` prices (``MAPPED_KEYS`` + the position premiums), as floats; with
    ``columns``, only the keys whose stat columns are all among them (the projected QB-TE line: kicking, 2-pt
    and long-TD keys price 0 on it). Two scorings with the same ``priced_keys(..., line columns)`` price every
    projected line identically (plan F1: how a league is matched to a reference scoring)."""
    keep = None if columns is None else set(columns)
    out: dict[str, float] = {}
    for k, w in scoring.items():
        if not w:
            continue
        if k in SLEEPER_POSITION_MAP:
            cols = {SLEEPER_POSITION_MAP[k][0]}
        elif k in SLEEPER_BONUS_MAP:
            cols = {SLEEPER_BONUS_MAP[k][0]}
        elif k in _PY_EXPR:
            cols = set(_PY_EXPR[k])
        else:
            continue
        if keep is None or cols <= keep:
            out[k] = float(w)
    return out


def seed_rows() -> list[dict[str, str]]:
    rows = [
        {"sleeper_key": k, "kind": "stat", "stat_expression": expr, "description": desc}
        for k, (expr, desc) in SLEEPER_STAT_MAP.items()
    ]
    rows += [
        {"sleeper_key": k, "kind": "bonus", "stat_expression": expr, "description": desc}
        for k, (expr, desc) in SLEEPER_LONG_TD_MAP.items()
    ]
    rows += [
        {
            "sleeper_key": k,
            "kind": "bonus",
            "stat_expression": f"{column}:{low}:{'' if high is None else high}",
            "description": desc,
        }
        for k, (column, low, high, desc) in SLEEPER_BONUS_MAP.items()
    ]
    return rows


def write_seed(path: str) -> None:
    """Regenerate ``dbt/seeds/scoring_stat_map.csv`` (rule 8 in AGENTS.md)."""
    import csv

    rows = seed_rows()
    with open(path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


# ================================================================================================ the scoring spec
# Wave I-C (IC-1): a league's rules as data, per position — what Sleeper's flat ``scoring_settings`` and MFL's
# position-grouped rules both compile to. docs/METRICS.md § "Scoring spec" is the contract.
#
# Stats are ``fct_player_game`` column names for players and kd1.0's DEF line names for a defense
# (``sacks``, ``interceptions``, ``fumble_recoveries``, ``forced_fumbles``, ``def_tds``, ``st_tds``, ``safeties``,
# ``blocked_kicks``, ``points_allowed``). A band is ``(low, high, points)``: it pays when ``low <= v < high + 1``
# (MFL's inclusive whole-number ranges; continuous for a fractional projected value), ``high`` None = no top.
Band = tuple[float, float | None, float]

# distance families: the TD (or kick) count they refine on a stat line, and the long-play count columns it carries
DISTANCE_FAMILIES: dict[str, dict] = {
    # the 10-yard cut (``*_tds_10p``) is used when the row carries it (proposed for int_player_game_pbp, Wave I-C)
    "passing_tds": {"count": "passing_tds", "cuts": {10: "pass_tds_10p", 40: "pass_tds_40p", 50: "pass_tds_50p"}},
    "rushing_tds": {"count": "rushing_tds", "cuts": {10: "rush_tds_10p", 40: "rush_tds_40p", 50: "rush_tds_50p"}},
    "receiving_tds": {"count": "receiving_tds", "cuts": {10: "rec_tds_10p", 40: "rec_tds_40p", 50: "rec_tds_50p"}},
    "return_tds": {"count": "special_teams_tds", "cuts": {}},
    "fumble_recovery_tds": {"count": "fumble_recovery_tds", "cuts": {}},
    "def_tds": {"count": "def_tds", "cuts": {}},
    "st_tds": {"count": "st_tds", "cuts": {}},
    "fg_made": {"count": "fg_made", "buckets": [(0, 19, "fg_made_0_19"), (20, 29, "fg_made_20_29"),
                                                 (30, 39, "fg_made_30_39"), (40, 49, "fg_made_40_49"),
                                                 (50, 59, "fg_made_50_59"), (60, None, "fg_made_60_")]},
    "fg_missed": {"count": "fg_missed", "buckets": [(0, 19, "fg_missed_0_19"), (20, 29, "fg_missed_20_29"),
                                                     (30, 39, "fg_missed_30_39"), (40, 49, "fg_missed_40_49"),
                                                     (50, 59, "fg_missed_50_59"), (60, None, "fg_missed_60_")]},
}
# Share of a family's touchdowns at least 10 / 40 yards long, by position: PLACEHOLDERS until M2's measured shares
# (``scoring_ev.td_distance_share``) land — the brief's constants, not measured here.
TD_SHARE_FALLBACK: dict[str, dict[int, float]] = {
    "receiving_tds": {10: 0.55, 40: 0.12, 50: 0.07}, "rushing_tds": {10: 0.35, 40: 0.06, 50: 0.04},
    "passing_tds": {10: 0.60, 40: 0.14, 50: 0.09}, "return_tds": {10: 0.98, 40: 0.85, 50: 0.75},
    "def_tds": {10: 0.80, 40: 0.40, 50: 0.30}, "st_tds": {10: 0.95, 40: 0.75, 50: 0.65},
    "fumble_recovery_tds": {10: 0.30, 40: 0.10, 50: 0.07},
}
# One game's spread of a stat around its projected mean (sd = a + b * mean): PLACEHOLDERS for the normal fallback
# until M2's ``scoring_ev.prob_at_least`` lands (M1 fitted isotonic curves, not a spread; these are round numbers).
SPREAD_FALLBACK: dict[str, tuple[float, float]] = {
    "passing_yards": (25.0, 0.22), "rushing_yards": (8.0, 0.55), "receiving_yards": (8.0, 0.65),
    "receptions": (1.0, 0.40), "points_allowed": (4.0, 0.35),
}

# our distance families -> M2's (``scoring_ev.TD_FAMILIES``)
EV_FAMILY = {"return_tds": "kick_return_tds", "def_tds": "int_return_tds", "st_tds": "punt_return_tds",
             "fumble_recovery_tds": "fumble_return_tds"}

try:  # M2's distributions (Wave I-C); absent in this worktree until the PO merges them
    from . import scoring_ev as _EV  # type: ignore[attr-defined]
except Exception:  # pragma: no cover - the fallback below is the tested path until then
    _EV = None


@_dataclass(frozen=True)
class Step:
    """MFL's ``a/b`` over a range: ``base + per * floor((v - origin) / unit)`` while ``low <= v <= high``."""
    low: float
    high: float | None
    per: float
    unit: float
    base: float = 0.0
    origin: float = 0.0


@_dataclass
class Rules:
    rates: dict[str, float] = _field(default_factory=dict)
    bands: dict[str, list[Band]] = _field(default_factory=dict)
    distance: dict[str, list[Band]] = _field(default_factory=dict)
    steps: dict[str, list[Step]] = _field(default_factory=dict)
    premiums: dict[str, float] = _field(default_factory=dict)

    def empty(self) -> bool:
        return not (self.rates or self.bands or self.distance or self.steps or self.premiums)

    def to_json(self) -> dict:
        return {"rates": dict(self.rates), "bands": {k: [list(b) for b in v] for k, v in self.bands.items()},
                "distance": {k: [list(b) for b in v] for k, v in self.distance.items()},
                "steps": {k: [[s.low, s.high, s.per, s.unit, s.base, s.origin] for s in v] for k, v in self.steps.items()},
                "premiums": dict(self.premiums)}

    @classmethod
    def from_json(cls, d: Mapping) -> Rules:
        return cls(rates={k: float(v) for k, v in (d.get("rates") or {}).items()},
                   bands={k: [tuple(b) for b in v] for k, v in (d.get("bands") or {}).items()},
                   distance={k: [tuple(b) for b in v] for k, v in (d.get("distance") or {}).items()},
                   steps={k: [Step(*s) for s in v] for k, v in (d.get("steps") or {}).items()},
                   premiums={k: float(v) for k, v in (d.get("premiums") or {}).items()})


UNIT_PRICES_AS = {"TMQB": "QB", "TMPK": "K", "TMDEF": "DEF", "PK": "K", "Def": "DEF", "D/ST": "DEF", "DST": "DEF",
                  "TMRB": "RB", "TMWR": "WR", "TMTE": "TE"}


@_dataclass
class ScoringSpec:
    positions: dict[str, Rules] = _field(default_factory=dict)
    source: str = "sleeper"
    unpriced: list[dict] = _field(default_factory=list)
    approximated: list[str] = _field(default_factory=list)
    flat: dict[str, float] | None = None       # the Sleeper settings it came from (parity path); None for MFL

    def rules_for(self, position: str | None) -> Rules | None:
        if position is None:
            return self.positions.get("*")
        p = str(position)
        return self.positions.get(p) or self.positions.get(UNIT_PRICES_AS.get(p, p)) or self.positions.get("*")

    def to_json(self) -> dict:
        return {"version": 1, "source": self.source, "positions": {p: r.to_json() for p, r in self.positions.items()},
                "unpriced": list(self.unpriced), "approximated": list(self.approximated), "flat": self.flat}

    @classmethod
    def from_json(cls, d: Mapping | str) -> ScoringSpec:
        if isinstance(d, str):
            d = _json.loads(d)
        return cls(positions={p: Rules.from_json(r) for p, r in (d.get("positions") or {}).items()},
                   source=str(d.get("source") or "sleeper"), unpriced=list(d.get("unpriced") or []),
                   approximated=list(d.get("approximated") or []),
                   flat=({k: float(v) for k, v in d["flat"].items()} if d.get("flat") is not None else None))

    def key(self) -> str:
        return _json.dumps(self.to_json(), sort_keys=True)

    def readback(self) -> list[str]:
        return readback(self)


class LeagueScoring(dict):
    """A league's flat ``scoring_settings`` (every old reader keeps working) carrying its ``ScoringSpec``."""
    spec: ScoringSpec | None = None


def spec_of(scoring: Mapping[str, float] | ScoringSpec) -> ScoringSpec:
    if isinstance(scoring, ScoringSpec):
        return scoring
    sp = getattr(scoring, "spec", None)
    return sp if isinstance(sp, ScoringSpec) else from_sleeper(scoring)


def _fmt(x: float) -> str:
    return f"{x:g}".replace("-", "−")


def _band_text(b: Band) -> str:
    lo, hi = b[0], b[1]
    return f"{int(lo)}+" if hi is None else (f"{int(lo)}" if lo == hi else f"{int(lo)}–{int(hi)}")


YARD_WORDS = {"passing_yards": "passing", "rushing_yards": "rushing", "receiving_yards": "receiving"}
YARD_HOME = {"passing_yards": ("QB",), "rushing_yards": ("RB", "QB"), "receiving_yards": ("WR", "TE", "RB")}
TD_WORDS = {"passing_tds": "pass", "rushing_tds": "rush", "receiving_tds": "catch"}


def _yard_rule(spec: ScoringSpec, stat: str) -> str | None:
    """How ``stat`` pays, from the position that owns it: ``"1 pt per 10"`` (a rate of 0.1, or a whole-unit step
    of 1 per 10), ``"1.5 a yard"`` (a rate above 1), or None when nothing pays it."""
    for pos in (*YARD_HOME[stat], "*"):
        r = spec.positions.get(pos)
        if r is None:
            continue
        st = (r.steps.get(stat) or [None])[0]
        if st is not None:
            return f"{_fmt(st.per)} pt per {_fmt(st.unit)}"
        y = r.rates.get(stat)
        if y:
            return f"1 pt per {_fmt(round(1 / y, 2))}" if y < 1 else f"{_fmt(y)} a yard"
    return None


def _td_rule(spec: ScoringSpec, fam: str) -> tuple[str, str] | None:
    """(kind, text) for a touchdown family: ``("flat", "6")``, ``("distance", "6 / 9 / 12")`` or
    ``("bonus", "6, +2 at 40 yards")``."""
    for pos in (*YARD_HOME[fam.replace("_tds", "_yards")], "*"):
        r = spec.positions.get(pos)
        if r is None:
            continue
        td, flat = r.distance.get(fam), r.rates.get(fam)
        if td and all(b[0] > 0 for b in td):
            return "bonus", f"{_fmt(flat or 6)}, +{_fmt(td[0][2])} at {int(td[0][0])} yards"
        if td:
            edges = [_band_text((b[0], None if (b[1] is None or b[1] >= 99) else b[1], b[2])) for b in td]
            return "distance", " / ".join(_fmt(b[2]) for b in td) + " (" + " / ".join(edges) + " yards)"
        if flat:
            return "flat", _fmt(flat)
    return None


def _td_head(kind: str, text: str) -> str:
    if kind == "flat":
        return f"{text}-pt TDs"
    if kind == "distance":
        return f"TDs by distance {text}"
    base, bonus = text.split(",", 1)
    return f"{base}-pt TDs, long-TD bonus{bonus}"


def readback(spec: ScoringSpec) -> list[str]:
    """The league's scoring in a few plain pieces (the Leagues card's one line): catches, touchdowns, yards, the
    flat yardage bonuses (which stat, which positions), turnovers, then K and DEF. Every number is the league's."""
    pieces: list[str] = []
    skill = [p for p in ("QB", "RB", "WR", "TE") if p in spec.positions] or (["*"] if "*" in spec.positions else [])
    off = next((spec.positions[p] for p in ("WR", "RB", "TE", "QB", "*") if p in spec.positions), None)
    if off is None:
        return pieces
    rec = off.rates.get("receptions", 0.0)
    te = spec.positions.get("TE")
    te_rec = (te.rates.get("receptions", 0.0) + te.premiums.get("receptions", 0.0)) if te else rec
    if rec:
        pieces.append(f"{_fmt(rec)} per catch" + (f" (TE {_fmt(te_rec)})" if te_rec != rec else ""))
    # touchdowns: one piece when every family reads the same, else each family
    tds = {fam: v for fam in ("rushing_tds", "receiving_tds", "passing_tds") if (v := _td_rule(spec, fam))}
    if tds:
        if len(set(tds.values())) == 1:
            pieces.append(_td_head(*next(iter(tds.values()))))
        elif tds.get("rushing_tds") and tds.get("rushing_tds") == tds.get("receiving_tds"):
            pv = tds.get("passing_tds")
            pieces.append(_td_head(*tds["rushing_tds"]) + (f" (pass {pv[1]})" if pv else ""))
        else:
            pieces.append(" · ".join(f"{TD_WORDS[f]} TD {v[1]}" for f, v in tds.items()))
    # yards: rushing / receiving together when they agree, passing on its own when it differs
    yr = {st: _yard_rule(spec, st) for st in ("rushing_yards", "receiving_yards", "passing_yards")}
    if yr["rushing_yards"] and yr["rushing_yards"] == yr["receiving_yards"]:
        same_pass = yr["passing_yards"] == yr["rushing_yards"]
        pieces.append(yr["rushing_yards"] + (" yards" if same_pass else " rushing / receiving yards"))
        if yr["passing_yards"] and not same_pass:
            pieces.append(yr["passing_yards"] + " passing yards")
    else:
        for st, v in yr.items():
            if v:
                pieces.append(f"{v} {YARD_WORDS[st]} yards")
    # flat yardage bonuses: by threshold and points, naming the stat, and the positions when not all of them pay it
    bon: dict[tuple[int, float], dict[str, list[str]]] = {}
    for pos in skill:
        for st, bs in spec.positions[pos].bands.items():
            if st in YARD_WORDS:
                for b in bs:
                    bon.setdefault((int(b[0]), float(b[2])), {}).setdefault(st, []).append(pos)
    if bon:
        words = []
        for (lo, pts), stats in sorted(bon.items()):
            parts = []
            for st in ("rushing_yards", "receiving_yards", "passing_yards"):
                if st not in stats:
                    continue
                carriers = [p for p in skill if p in YARD_HOME[st]]
                tag = "" if set(stats[st]) >= set(carriers) else f" ({'/'.join(stats[st])})"
                parts.append(YARD_WORDS[st] + tag)
            words.append(f"+{_fmt(pts)} at {lo} " + " / ".join(parts))
        pieces.append(" · ".join(words[:5]))
    qb = spec.positions.get("QB") or spec.positions.get("*")
    if qb is not None and qb.rates.get("passing_interceptions"):
        pieces.append(f"INT {_fmt(qb.rates['passing_interceptions'])}")
    fl = off.rates.get("fumbles_lost_total") or off.rates.get("fumbles_lost")
    if fl:
        pieces.append(f"fumble lost {_fmt(fl)}")
    k = spec.positions.get("K")
    if k is not None and k.distance.get("fg_made"):
        pieces.append("FG by distance " + " / ".join(_fmt(b[2]) for b in k.distance["fg_made"]))
    d = spec.positions.get("DEF")
    if d is not None and d.bands.get("points_allowed"):
        pieces.append("DEF points allowed " + ", ".join(f"{_band_text(b)} → {_fmt(b[2])}" for b in d.bands["points_allowed"][:3]))
    return pieces


# ------------------------------------------------------------------------------------------- Sleeper -> spec
SLEEPER_TO_STAT = {k: v[0] for k, v in SLEEPER_STAT_MAP.items() if "+" not in v[0] and not k.startswith(("fgm", "fgmiss"))}
SLEEPER_TO_STAT.update({"fgmiss": "fg_missed+fg_blocked", "xpmiss": "pat_missed+pat_blocked",
                        # stat keys the flat engine (and the SQL macro) leave out but an actual line carries: priced
                        # on actual lines by the spec; the check shows them as SQL disagreements, never silently
                        "pass_fd": "passing_first_downs", "rush_fd": "rushing_first_downs",
                        "rec_fd": "receiving_first_downs", "pass_cmp": "completions", "pass_att": "attempts",
                        "rush_att": "carries", "rec_tgt": "targets", "pass_sack": "sacks_suffered"})
SLEEPER_FG = {"fgm_0_19": ("fg_made", 0, 19), "fgm_20_29": ("fg_made", 20, 29), "fgm_30_39": ("fg_made", 30, 39),
              "fgm_40_49": ("fg_made", 40, 49), "fgm_50p": ("fg_made", 50, None),
              "fgmiss_0_19": ("fg_missed", 0, 19), "fgmiss_20_29": ("fg_missed", 20, 29),
              "fgmiss_30_39": ("fg_missed", 30, 39), "fgmiss_40_49": ("fg_missed", 40, 49),
              "fgmiss_50p": ("fg_missed", 50, None)}
SLEEPER_LONG_TD = {"pass_td_40p": ("passing_tds", 40), "pass_td_50p": ("passing_tds", 50),
                   "rush_td_40p": ("rushing_tds", 40), "rush_td_50p": ("rushing_tds", 50),
                   "rec_td_40p": ("receiving_tds", 40), "rec_td_50p": ("receiving_tds", 50)}
SLEEPER_DEF = {"sack": "sacks", "int": "interceptions", "fum_rec": "fumble_recoveries", "ff": "forced_fumbles",
               "def_td": "def_tds", "def_st_td": "st_tds", "safe": "safeties", "blk_kick": "blocked_kicks"}
SLEEPER_PA = {"pts_allow_0": (0, 0), "pts_allow_1_6": (1, 6), "pts_allow_7_13": (7, 13), "pts_allow_14_20": (14, 20),
              "pts_allow_21_27": (21, 27), "pts_allow_28_34": (28, 34), "pts_allow_35p": (35, None)}
# keys a Sleeper league may weight that no stat line carries (kept in ``unpriced`` with Sleeper's own key)
# flat once-a-game bonuses on a count the actual line carries (not in the flat engine / the SQL macro)
SLEEPER_COUNT_BONUS = {"bonus_pass_cmp_25": ("completions", 25), "bonus_rush_att_20": ("carries", 20)}
SLEEPER_UNPRICED_WORDS = {
    "def_2pt": "defensive 2-pt return", "def_st_fum_rec": "fumble recovered on special teams",
    "bonus_rush_rec_yd_100": "100+ rushing and receiving yards combined",
    "bonus_rush_rec_yd_200": "200+ rushing and receiving yards combined",
    "st_fum_rec": "special-teams fumble recovery", "st_ff": "special-teams forced fumble",
    "def_st_ff": "special-teams forced fumble", "yds_allow_0_100": "yards allowed", "qb_hit": "QB hits",
    "tkl": "tackles", "tkl_loss": "tackles for loss", "kr_yd": "kick return yards",
    "pr_yd": "punt return yards", "idp_tkl": "IDP tackles",
}


def from_sleeper(scoring: Mapping[str, float]) -> ScoringSpec:
    """Sleeper's flat ``scoring_settings`` -> a spec. Sleeper applies every key to every player, so QB RB WR TE K
    and ``*`` (a row whose position is unknown) share one rule set; ``bonus_rec_te/rb/wr`` land on that position's
    premiums; the D/ST keys make DEF's rules. Keys no stat line carries are ``unpriced`` (Sleeper's key)."""
    sc = {k: float(v) for k, v in (scoring or {}).items() if v is not None}
    player, dfn = Rules(), Rules()
    prem: dict[str, float] = {}
    unpriced: list[dict] = []
    for key, w in sc.items():
        if not w:
            continue
        if key in SLEEPER_BONUS_MAP:
            col, lo, hi, _ = SLEEPER_BONUS_MAP[key]
            player.bands.setdefault(col, []).append((float(lo), None if hi is None else float(hi - 1), w))
        elif key in SLEEPER_LONG_TD:
            fam, lo = SLEEPER_LONG_TD[key]
            player.distance.setdefault(fam, []).append((float(lo), None, w))
        elif key in SLEEPER_FG:
            fam, lo, hi = SLEEPER_FG[key]
            player.distance.setdefault(fam, []).append((float(lo), None if hi is None else float(hi), w))
        elif key in SLEEPER_POSITION_MAP:
            col, pos, _ = SLEEPER_POSITION_MAP[key]
            prem[pos] = prem.get(pos, 0.0) + w
        elif key in SLEEPER_TO_STAT:
            for col in SLEEPER_TO_STAT[key].split("+"):
                player.rates[col] = player.rates.get(col, 0.0) + w
        elif key in SLEEPER_COUNT_BONUS:
            col, lo = SLEEPER_COUNT_BONUS[key]
            player.bands.setdefault(col, []).append((float(lo), None, w))
        elif key == "pass_inc":                  # an incompletion = an attempt that was not completed
            player.rates["attempts"] = player.rates.get("attempts", 0.0) + w
            player.rates["completions"] = player.rates.get("completions", 0.0) - w
        elif key in SLEEPER_DEF:
            dfn.rates[SLEEPER_DEF[key]] = dfn.rates.get(SLEEPER_DEF[key], 0.0) + w
        elif key in SLEEPER_PA:
            lo, hi = SLEEPER_PA[key]
            dfn.bands.setdefault("points_allowed", []).append((float(lo), None if hi is None else float(hi), w))
        elif key not in MAPPED_KEYS:
            unpriced.append({"event": key, "name": SLEEPER_UNPRICED_WORDS.get(key) or key.replace("_", " ")})
    for bs in list(player.bands.values()) + list(player.distance.values()) + list(dfn.bands.values()):
        bs.sort(key=lambda b: b[0])
    positions: dict[str, Rules] = {"*": player}
    for p in ("QB", "RB", "WR", "TE", "K"):
        r = Rules(rates=player.rates, bands=player.bands, distance=player.distance, steps=player.steps,
                  premiums=({"receptions": prem[p]} if p in prem else {}))
        positions[p] = r
    if not dfn.empty():
        positions["DEF"] = dfn
    return ScoringSpec(positions=positions, source="sleeper", unpriced=unpriced, flat=sc)


# ------------------------------------------------------------------------------------------- MFL -> spec
# MFL event -> (stat, kind): "count" = a per-unit stat; "dist" = a touchdown (kick) family priced by length
MFL_PLAYER_EVENTS: dict[str, tuple[str, str]] = {
    "#P": ("passing_tds", "count"), "PY": ("passing_yards", "count"), "IN": ("passing_interceptions", "count"),
    "P2": ("passing_2pt_conversions", "count"), "#R": ("rushing_tds", "count"), "RY": ("rushing_yards", "count"),
    "R2": ("rushing_2pt_conversions", "count"), "#C": ("receiving_tds", "count"), "CY": ("receiving_yards", "count"),
    "C2": ("receiving_2pt_conversions", "count"), "CC": ("receptions", "count"), "FL": ("fumbles_lost_total", "count"),
    "FU": ("fumbles_total", "count"), "#FR": ("fumble_recovery_tds", "count"), "EP": ("pat_made", "count"),
    "EM": ("pat_missed", "count"), "MG": ("fg_missed", "count"), "PA": ("attempts", "count"),
    "PC": ("completions", "count"), "RA": ("carries", "count"), "TA": ("targets", "count"),
    "#UT": ("return_tds", "count"), "#KT": ("return_tds", "count"), "#T": ("return_tds", "count"),
    "PS": ("passing_tds", "dist"), "RS": ("rushing_tds", "dist"), "RC": ("receiving_tds", "dist"),
    "PR": ("return_tds", "dist"), "KO": ("return_tds", "dist"), "DR": ("fumble_recovery_tds", "dist"),
    "FR": ("fumble_recovery_tds", "dist"),
    "FG": ("fg_made", "dist"),
}
# events that never happen to an offensive player or a kicker (defensive returns): no stat, no points, not a gap
MFL_PLAYER_NEVER = {"IR", "BF", "MF", "BP"}
MFL_DEF_EVENTS: dict[str, tuple[str, str]] = {
    "SK": ("sacks", "count"), "IC": ("interceptions", "count"), "FC": ("fumble_recoveries", "count"),
    "FF": ("forced_fumbles", "count"), "SF": ("safeties", "count"), "BLK": ("blocked_kicks", "count"),
    "FR": ("fumble_recoveries", "count"),
    "#T": ("def_tds", "count"), "#IR": ("def_tds", "count"), "#FR": ("def_tds", "count"),
    "#UT": ("st_tds", "count"), "#KT": ("st_tds", "count"), "#ST": ("st_tds", "count"),
    "TPA": ("points_allowed", "band"),
    "DR": ("def_tds", "dist"), "IR": ("def_tds", "dist"), "BF": ("st_tds", "dist"), "MF": ("st_tds", "dist"),
    "BP": ("st_tds", "dist"), "PR": ("st_tds", "dist"), "KO": ("st_tds", "dist"),
}
MFL_EVENT_NAMES = {
    "UY": "punt return yards", "KY": "kickoff return yards", "BLF": "blocked field goal", "BLP": "blocked punt",
    "BLE": "blocked extra point", "TK": "tackles", "AS": "assisted tackles", "PD": "passes defended",
    "YA": "yards allowed", "TYA": "total yards allowed", "PYA": "passing yards allowed", "RYA": "rushing yards allowed",
    "FD": "first downs", "TPF": "team points scored", "W": "team win", "L": "team loss", "T": "team tie",
    "2R": "2-pt return", "TO": "turnovers", "XPA": "extra points allowed", "FGA": "field goals allowed",
    "OT": "overtime", "PDT": "pass defended", "TKL": "tackles for loss", "QH": "quarterback hits",
}
MFL_POS = {"QB": "QB", "RB": "RB", "WR": "WR", "TE": "TE", "PK": "K", "K": "K", "Def": "DEF", "DEF": "DEF",
           "TMQB": "TMQB", "TMPK": "TMPK", "TMDEF": "DEF", "TMRB": "TMRB", "TMWR": "TMWR", "TMTE": "TMTE", "ST": "DEF"}
MFL_IDP = {"DT", "DE", "LB", "CB", "S", "DL", "DB", "Off", "Coach", "TMDL", "TMLB", "TMDB"}
_DIST_KICK_BUCKETS = [(0, 19), (20, 29), (30, 39), (40, 49), (50, 59), (60, None)]


def _mt(x) -> str | None:
    if isinstance(x, Mapping):
        x = x.get("$t")
    return None if x is None else str(x)


def _mlist(x) -> list:
    return [] if x is None else (list(x) if isinstance(x, list) else [x])


def _mrange(s: str | None) -> tuple[float, float | None]:
    import re
    m = re.match(r"^\s*(-?\d+(?:\.\d+)?)\s*-\s*(-?\d+(?:\.\d+)?)\s*$", s or "")
    if not m:
        try:
            v = float(s) if s else 0.0
        except ValueError:
            v = 0.0
        return v, v
    lo, hi = float(m.group(1)), float(m.group(2))
    return lo, (None if hi >= 999 else hi)


def from_mfl(rules: Mapping) -> ScoringSpec:
    """MFL's ``rules`` export -> a spec, one ``Rules`` per listed position (``positions: "QB|RB|WR"``; ``PK`` -> K,
    ``Def`` -> DEF; the units keep their names and fall back to QB / K / DEF). Every rule for an event adds:
    ``*x`` = x per unit; ``a/b`` = a per whole b over the range (``thresholdPoints`` t: t at the range's low, then a
    per b beyond it); a plain ``n`` = n once when the stat is in the range — for a touchdown family (PS RS RC PR KO
    DR IR BF MF BP) and FG, n per play of that length. Unknown events -> ``unpriced`` with MFL's code and name."""
    root = rules.get("rules", rules) if isinstance(rules, Mapping) else {}
    groups = _mlist(root.get("positionRules"))
    out: dict[str, Rules] = {}
    unpriced: dict[str, dict] = {}
    approx: list[str] = []
    idp: list[str] = []
    for g in groups:
        poss = [p for p in str(g.get("positions") or "").split("|") if p]
        mine = [MFL_POS[p] for p in poss if p in MFL_POS]
        idp += [p for p in poss if p not in MFL_POS]
        if not mine:
            continue
        for p in mine:
            out.setdefault(p, Rules())
        is_def = all(p == "DEF" for p in mine)
        table = MFL_DEF_EVENTS if is_def else MFL_PLAYER_EVENTS
        for r in _mlist(g.get("rule")):
            ev = _mt(r.get("event")) or ""
            pts = (_mt(r.get("points")) or "0").strip()
            thr = _mt(r.get("thresholdPoints"))
            lo, hi = _mrange(_mt(r.get("range")))
            hit = table.get(ev)
            if hit is None:
                if not is_def and ev in MFL_PLAYER_NEVER:
                    continue
                unpriced.setdefault(ev, {"event": ev, "name": MFL_EVENT_NAMES.get(ev, ev), "positions": "|".join(poss)})
                continue
            stat, kind = hit
            try:
                if pts.startswith("*"):
                    form, a, b = "rate", float(pts[1:] or 0), 1.0
                elif "/" in pts:
                    x, y = pts.split("/", 1)
                    form, a, b = "per", float(x or 0), float(y or 1)
                else:
                    form, a, b = "flat", float(pts or 0), 0.0
            except ValueError:
                unpriced.setdefault(ev, {"event": ev, "name": f"{MFL_EVENT_NAMES.get(ev, ev)} ({pts})", "positions": "|".join(poss)})
                continue
            for p in mine:
                R = out[p]
                if kind == "dist" and form == "flat":
                    R.distance.setdefault(stat, []).append((lo, hi, a))
                elif kind == "dist" and stat == "fg_made" and form == "per":
                    # FG by the yard: our lines bucket kicks by 10 yards -> each bucket priced at its middle
                    base = float(thr) if thr else 0.0
                    for blo, bhi in _DIST_KICK_BUCKETS:
                        mid = (blo + (bhi if bhi is not None else 64)) / 2.0
                        if mid < lo or (hi is not None and mid > hi):
                            continue
                        val = base + a / b * (mid - lo) if thr else a / b * mid
                        R.distance.setdefault("fg_made", []).append((float(blo), None if bhi is None else float(bhi), round(val, 3)))
                    msg = "field goals scored by the yard are priced at the middle of each 10-yard band (24.5, 34.5, 44.5 … yards)"
                    if msg not in approx:
                        approx.append(msg)
                elif kind == "dist" and form == "rate":     # "*6" on a TD family: per touchdown, any length
                    col = DISTANCE_FAMILIES.get(stat, {}).get("count", stat)
                    R.rates[col] = R.rates.get(col, 0.0) + a
                elif kind == "band" or (form == "flat" and stat in ("points_allowed",)):
                    R.bands.setdefault(stat, []).append((lo, hi, a))
                elif form == "rate":
                    col = "special_teams_tds" if stat == "return_tds" and p != "DEF" else stat
                    R.rates[col] = R.rates.get(col, 0.0) + a
                elif form == "per":
                    origin = lo if thr else 0.0
                    R.steps.setdefault(stat, []).append(Step(lo, hi, a, b, float(thr) if thr else 0.0, origin))
                else:  # a flat amount once the stat is in the range (MFL's yardage bonuses)
                    R.bands.setdefault(stat, []).append((lo, hi, a))
    for R in out.values():   # zero-point bands change nothing; PR and KO (punt / kick returns) share one TD count
        R.bands = {k: sorted(dict.fromkeys(b for b in v if b[2]), key=lambda t: t[0]) for k, v in R.bands.items()}
        R.bands = {k: v for k, v in R.bands.items() if v}
        R.distance = {k: sorted(dict.fromkeys(b for b in v if b[2]), key=lambda t: t[0]) for k, v in R.distance.items()}
        R.distance = {k: v for k, v in R.distance.items() if v}
    # what the K / DEF projection (kd1.0 on Sleeper's buckets, ``kd_flat``) approximates — the actual lines are exact
    pa = (out.get("DEF") or Rules()).bands.get("points_allowed") or []
    if pa and sorted((int(b[0]), None if b[1] is None else int(b[1])) for b in pa) != \
            [(lo, hi) for lo, hi in SLEEPER_PA.values()][:len(pa)]:
        approx.append("points allowed on a projection: the league's bands (" + ", ".join(_band_text(b) for b in pa)
                      + ") are spread over the defense projection's (0, 1–6, 7–13 …) by the average over each")
    fg = (out.get("K") or Rules()).distance.get("fg_made") or []
    p50 = [b[2] for b in fg if _in_band(55, b)]
    p60 = [b[2] for b in fg if _in_band(62, b)]
    if p50 and p60 and p50 != p60:
        approx.append(f"kicks of 50+ yards on a projection: priced at the 50–59 band ({_fmt(p50[0])}); the projection "
                      "does not split off 60+")
    # what no projection carries: return touchdowns (kick / punt returns by a skill player) and 2-point conversions
    # are priced on actual lines (the scoring check) but a projected line has none
    if any(any(k in r.distance or k in r.rates for k in ("return_tds", "special_teams_tds", "st_tds"))
           for p, r in out.items() if p in ("QB", "RB", "WR", "TE", "*")):
        approx.append("return touchdowns are not projected (they count on actual lines)")
    if any(k.endswith("_2pt_conversions") for r in out.values() for k in r.rates):
        approx.append("2-point conversions are not projected")
    if idp:
        unpriced["IDP"] = {"event": "IDP", "name": "individual defensive players (" + ", ".join(sorted(set(idp))) + ")",
                           "positions": "|".join(sorted(set(idp)))}
    return ScoringSpec(positions=out, source="mfl", unpriced=sorted(unpriced.values(), key=lambda d: d["event"]),
                       approximated=approx, flat=None)


# ------------------------------------------------------------------------------------------- pricing on the spec
def _in_band(v: float, b: Band) -> bool:
    return v >= b[0] and (b[1] is None or v < b[1] + 1)


def _share_at_least(family: str, position: str | None, length: float) -> float:
    """P(a TD of this family is at least ``length`` yards): M2's measured shares when present, else the
    placeholder constants (``TD_SHARE_FALLBACK``) interpolated linearly between 0 / 10 / 40 / 50 / 100 yards."""
    if length <= 0:
        return 1.0
    if _EV is not None and hasattr(_EV, "td_distance_share"):
        try:
            return float(_EV.td_distance_share(EV_FAMILY.get(family, family), position, int(round(length)), None))
        except Exception:  # noqa: BLE001 - M2's table lacks the family / position: the placeholder
            pass
    f = TD_SHARE_FALLBACK.get(family, TD_SHARE_FALLBACK["rushing_tds"])
    pts = [(0.0, 1.0), (10.0, f[10]), (40.0, f[40]), (50.0, f[50]), (100.0, 0.0)]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:], strict=False):
        if x0 <= length <= x1:
            return y0 + (y1 - y0) * (length - x0) / (x1 - x0)
    return 0.0


def _band_share(family: str, position: str | None, b: Band) -> float:
    hi = _share_at_least(family, position, b[1] + 1) if b[1] is not None else 0.0
    return max(0.0, _share_at_least(family, position, b[0]) - hi)


def _n_at_least(stats: Mapping, family: str, length: float, position: str | None) -> tuple[float, bool]:
    """(how many of the row's plays of ``family`` were at least ``length`` long, approximated?): exact from
    ``<family>_lengths`` or a known cut (``*_tds_40p/_50p``, the kick buckets), else interpolated with the shares."""
    lens = stats.get(f"{family}_lengths")
    if lens is not None:
        return float(sum(1 for x in lens if x >= length)), False
    fam = DISTANCE_FAMILIES.get(family, {"count": family, "cuts": {}})
    n = float(stats.get(fam["count"]) or 0)
    if "buckets" in fam:
        tot, exact = 0.0, True
        for blo, bhi, col in fam["buckets"]:
            c = float(stats.get(col) or 0)
            if blo >= length:
                tot += c
            elif bhi is not None and bhi >= length:
                tot += c * (bhi + 1 - length) / (bhi + 1 - blo)
                exact = False
            elif bhi is None and length > blo:
                exact = False
        return tot, not exact
    if length <= 0 or n == 0:
        return (n if length <= 0 else 0.0), False
    cuts = {0.0: n} | {float(k): float(stats.get(c) or 0) for k, c in fam["cuts"].items() if c in stats}
    if length in cuts:
        return cuts[length], False
    below = max(k for k in cuts if k < length)
    above = min((k for k in cuts if k > length), default=None)
    n_a, n_b = cuts[below], (cuts[above] if above is not None else 0.0)
    if n_a == n_b or (above is None and length > 100):    # none between the known cuts / longer than a field
        return n_b, False
    s_a = _share_at_least(family, position, below)
    s_b = _share_at_least(family, position, above) if above is not None else 0.0
    s_l = _share_at_least(family, position, length)
    frac = (s_l - s_b) / (s_a - s_b) if s_a > s_b else 0.0
    return n_b + (n_a - n_b) * frac, True


def price_detail(stats: Mapping, spec: ScoringSpec, position: str | None = None) -> tuple[dict[str, float], bool]:
    """An ACTUAL stat line's points under the spec, piece by piece (``rate:<stat>``, ``premium:<stat>``,
    ``band:<stat>:<low>``, ``step:<stat>``, ``distance:<family>``) and whether any piece was approximated."""
    pos = position if position is not None else stats.get("position")
    r = spec.rules_for(pos)
    pieces: dict[str, float] = {}
    approx = False
    if r is None:
        return pieces, False
    for s, w in r.rates.items():
        v = float(stats.get(s) or 0)
        if v:
            pieces[f"rate:{s}"] = pieces.get(f"rate:{s}", 0.0) + v * w
    for s, w in r.premiums.items():
        v = float(stats.get(s) or 0)
        if v:
            pieces[f"premium:{s}"] = v * w
    for s, bs in r.bands.items():
        v = float(stats.get(s) or 0)
        for b in bs:
            if _in_band(v, b) and b[2]:
                pieces[f"band:{s}:{int(b[0])}"] = pieces.get(f"band:{s}:{int(b[0])}", 0.0) + b[2]
    for s, sts in r.steps.items():
        v = float(stats.get(s) or 0)
        tot = 0.0
        for st in sts:
            if v >= st.low and (st.high is None or v <= st.high):
                tot += st.base + st.per * _math.floor((v - st.origin) / st.unit + 1e-9)
        if tot:
            pieces[f"step:{s}"] = tot
    for fam, bs in r.distance.items():
        tot = 0.0
        for b in bs:
            n_lo, a1 = _n_at_least(stats, fam, b[0], pos)
            n_hi, a2 = (_n_at_least(stats, fam, b[1] + 1, pos) if b[1] is not None else (0.0, False))
            cnt = max(0.0, n_lo - n_hi)
            if cnt:
                approx = approx or a1 or a2
                tot += cnt * b[2]
        if tot:
            pieces[f"distance:{fam}"] = tot
    return pieces, approx


def compute_points_spec(stats: Mapping, spec: ScoringSpec | Mapping[str, float], position: str | None = None) -> float:
    """An actual stat line's points under a spec (a flat Sleeper dict is compiled first)."""
    sp = spec if isinstance(spec, ScoringSpec) else spec_of(spec)
    pieces, _ = price_detail(stats, sp, position)
    return round(sum(pieces.values()), 2)


# ---- M4 (Wave I-G): the pricing MODE. The record decides; the env overrides; the nightly writer pins the env.
# docs/METRICS.md § "Expected-value pricing" → "The record's pricing column". Every reader of the mode (``ev_pricing``,
# ``ev_for_week``) goes through ``pricing_mode`` / ``record_pricing``: one query, cached ten minutes per process.
RECORD_TTL_S, RECORD_FAIL_TTL_S = 600.0, 60.0
# per season × week: the newest fitted_at and whether any Sleeper league's row of it says 'ev' (an MFL spec is always
# expected value, so it says nothing about the build's mode and is left out); NULL pricing = flat (rows before I-G)
RECORD_PRICING_SQL = """select season, week, max(fitted_at) as fitted_at, coalesce(bool_or(pricing = 'ev'), false) as ev
                        from ops.projections
                        where not starts_with(league_id, 'mfl:') and position in ('QB', 'RB', 'WR', 'TE')
                        group by season, week"""
_PINNED: list[str] = []                       # the nightly writer's mode (a stack: ``pinned_pricing``)
_RECORD: dict = {}                            # {"at": monotonic expiry, "weeks": {(season, week): bool}, "newest": ...}
_RECORD_READER = None                         # () -> rows of RECORD_PRICING_SQL; None = league_lab.db (pipeline role)


def _truthy(v: str) -> bool:
    return v.strip().lower() in ("1", "true", "yes", "on")


def env_pricing() -> str | None:
    """``LEAGUE_LAB_EV_PRICING`` when set and non-empty (an override, either way): ``ev`` for 1 / true / yes / on,
    ``flat`` for anything else; None when unset (the record decides)."""
    v = _os.environ.get("LEAGUE_LAB_EV_PRICING")
    if v is None or not v.strip():
        return None
    return "ev" if _truthy(v) else "flat"


def set_record_reader(fn) -> None:
    """Swap how the record is read: ``fn()`` returns the rows of ``RECORD_PRICING_SQL`` (a DataFrame or a list of
    dicts / tuples ``(season, week, fitted_at, ev)``). The API registers its read-only ``db.query``; None = the
    pipeline connection (``league_lab.db``). Clears the cache."""
    global _RECORD_READER
    _RECORD_READER = fn
    clear_pricing_cache()


def clear_pricing_cache() -> None:
    _RECORD.clear()


def _read_record_rows():
    if _RECORD_READER is not None:
        return _RECORD_READER()
    import psycopg

    from .config import get_settings
    st, err = get_settings(), None
    for dsn in (st.app_dsn, st.pipeline_dsn):      # the read-only role first (the console on Streamlit Cloud has only it)
        try:
            with psycopg.connect(dsn(), connect_timeout=3) as conn, conn.cursor() as cur:
                cur.execute(RECORD_PRICING_SQL)
                return [(r[0], r[1], r[2], r[3]) for r in cur.fetchall()]
        except Exception as exc:  # noqa: BLE001 - the next role, then the caller's flat
            err = exc
    raise err if err is not None else RuntimeError("no database")


def record_pricing() -> dict:
    """The record's labels: ``{"weeks": {(season, week): "ev" | "flat"}, "newest": "ev" | "flat" | None,
    "built_at": datetime | None, "ok": bool}`` — cached ten minutes (a failure, e.g. a database without the column:
    nothing known, cached a minute; the caller then prices flat)."""
    import time as _time
    now = _time.monotonic()
    if _RECORD and _RECORD["at"] > now:
        return _RECORD["value"]
    try:
        rows = _read_record_rows()
        recs = rows.to_dict("records") if hasattr(rows, "to_dict") else [
            r if isinstance(r, Mapping) else dict(zip(("season", "week", "fitted_at", "ev"), r, strict=False)) for r in rows]
        weeks = {(int(r["season"]), int(r["week"])): ("ev" if bool(r["ev"]) else "flat") for r in recs
                 if r.get("season") is not None and r.get("week") is not None}
        dated = [r for r in recs if r.get("fitted_at") is not None and str(r["fitted_at"]) not in ("NaT", "nan")]
        built_at = max((r["fitted_at"] for r in dated), default=None)
        newest = None
        if built_at is not None:   # the newest build: the weeks it wrote carry its fitted_at
            newest = "ev" if any(bool(r["ev"]) for r in dated if r["fitted_at"] == built_at) else "flat"
        value, ttl = {"weeks": weeks, "newest": newest, "built_at": built_at, "ok": True}, RECORD_TTL_S
    except Exception:  # noqa: BLE001 - no database, no table, no column (before the first I-G nightly): flat
        value, ttl = {"weeks": {}, "newest": None, "built_at": None, "ok": False}, RECORD_FAIL_TTL_S
    _RECORD.clear()
    _RECORD.update({"at": now + ttl, "value": value})
    return value


class pinned_pricing:
    """``with pinned_pricing("ev" | "flat" | None):`` — the nightly writer's mode for the build (None = the env, else
    flat): the writer never follows the record it is writing, so a rollback is "unset the env, re-run the nightly"."""

    def __init__(self, mode: str | None = None):
        self.mode = mode if mode in ("ev", "flat") else (env_pricing() or "flat")

    def __enter__(self):
        _PINNED.append(self.mode)
        return self.mode

    def __exit__(self, *exc):
        _PINNED.pop()
        return False


def pinned_writer(fn):
    """Decorator for a nightly writer (``projections.project`` / ``backtest``): the whole call runs ``pinned_pricing()``."""
    import functools

    @functools.wraps(fn)
    def run(*args, **kwargs):
        with pinned_pricing():
            return fn(*args, **kwargs)
    return run


def pricing_mode() -> dict:
    """``{"mode": "flat" | "ev", "source": "pinned" | "env" | "record" | "default", "built_at": …}``: a pinned mode
    (the nightly writer), else ``LEAGUE_LAB_EV_PRICING`` when set, else the newest build's label in
    ``ops.projections``, else flat."""
    if _PINNED:
        return {"mode": _PINNED[-1], "source": "pinned", "built_at": None}
    env = env_pricing()
    if env is not None:
        return {"mode": env, "source": "env", "built_at": None}
    rec = record_pricing()
    if rec["newest"] is not None:
        return {"mode": rec["newest"], "source": "record", "built_at": rec["built_at"]}
    return {"mode": "flat", "source": "default", "built_at": None}


def ev_pricing() -> bool:
    """Is a projected line's flat band priced at its probability? M3's flag, now a MODE (``pricing_mode``): the
    nightly writer's pinned mode; else ``LEAGUE_LAB_EV_PRICING`` when set (an override, either way); else the newest
    build in the record (``ops.projections.pricing``); else flat."""
    return pricing_mode()["mode"] == "ev"


def ev_for_week(season: int | None, week: int | None) -> bool:
    """The mode for pricing one week's lines: pinned / env as ``ev_pricing``; else the label of that week's rows in
    the record (a frozen week keeps the label it was priced with); a week the record has no rows for: the newest
    build's."""
    if _PINNED or env_pricing() is not None or season is None or week is None:
        return ev_pricing()
    lab = record_pricing()["weeks"].get((int(season), int(week)))
    return lab == "ev" if lab is not None else ev_pricing()


def record_pricing_label(scoring) -> str:
    """The ``pricing`` column's value for rows priced in this scoring now: ``pricing_engine`` with ``spec`` → ``ev``
    (an MFL spec is always expected value)."""
    e = pricing_engine(scoring)
    return "flat" if e == "flat" else "ev"


# one league's newest build: "now" in the record's sentence (the API's /api/record, the console's Record page)
LEAGUE_PRICING_SQL = """select coalesce(bool_or(pricing = 'ev'), false) as ev from ops.projections
                        where league_id = %s and position in ('QB', 'RB', 'WR', 'TE')
                          and fitted_at = (select max(fitted_at) from ops.projections where league_id = %s)"""


# the record's one sentence (About on the web, the console's Record page): GET /api/record `pricing.sentence`
PRICING_WORDS = {"flat": "priced flat", "ev": "priced the bonuses at their odds", "mixed": "priced partly flat"}


def _pricing_weeks(ws: list[int]) -> str:
    return f"Week {ws[0]}" if len(ws) == 1 else f"Weeks {ws[0]}–{ws[-1]}"


def record_pricing_sentence(by_week: dict[int, str], now: str) -> str | None:
    """One sentence for the record: "Weeks 1–4 were priced flat; from week 5 the bonuses are priced at their odds."
    None when every week is flat and so is now (nothing to say: a league without a bonus is always flat)."""
    weeks = sorted(by_week)
    if not weeks:
        return None if now == "flat" else "The bonuses are priced at their odds (their chance of happening × the points)."
    labels = [by_week[w] for w in weeks]
    if all(lab == "flat" for lab in labels) and now == "flat":
        return None
    if all(lab == "ev" for lab in labels) and now == "ev":
        return "Every week on the record priced the bonuses at their odds."
    runs: list[tuple[str, list[int]]] = []
    for w, lab in zip(weeks, labels, strict=True):
        if runs and runs[-1][0] == lab and runs[-1][1][-1] == w - 1:
            runs[-1][1].append(w)
        else:
            runs.append((lab, [w]))
    if len(runs) == 1 and runs[0][0] == "flat" and now == "ev":
        ws = runs[0][1]
        return (f"{_pricing_weeks(ws)} {'was' if len(ws) == 1 else 'were'} priced flat; from week {ws[-1] + 1} the "
                "bonuses are priced at their odds.")
    if len(runs) == 2 and runs[0][0] == "flat" and runs[1][0] == "ev" and now == "ev":
        ws = runs[0][1]
        return (f"{_pricing_weeks(ws)} {'was' if len(ws) == 1 else 'were'} priced flat; from week {runs[1][1][0]} the "
                "bonuses are priced at their odds.")
    parts = [f"{_pricing_weeks(ws).lower() if i else _pricing_weeks(ws)} {PRICING_WORDS[lab]}" for i, (lab, ws) in enumerate(runs)]
    return "; ".join(parts) + (f"; now {'at their odds' if now == 'ev' else 'flat'}." if runs[-1][0] != now else ".")
# ---- /M4


def _norm_sf(z):
    import numpy as np
    from scipy.special import ndtr
    return 1.0 - ndtr(np.asarray(z, dtype=float))


def prob_at_least(stat: str, position: str | None, mean, threshold: float):
    """P(stat >= threshold | projected mean): M2's fitted curves (``scoring_ev.prob_at_least``) when present, else a
    normal with the placeholder spread ``SPREAD_FALLBACK`` (continuity-corrected by half a unit). Vectorised."""
    import numpy as np
    m = np.asarray(mean, dtype=float)
    if _EV is not None and hasattr(_EV, "prob_at_least"):
        try:
            return np.asarray(_EV.prob_at_least(stat, position, m, threshold), dtype=float)
        except Exception:  # noqa: BLE001 - outside M2's table: the fallback
            pass
    a, b = SPREAD_FALLBACK.get(stat, (1.0, 0.5))
    sd = a + b * np.clip(m, 0, None)
    return np.where(m > 0, _norm_sf((threshold - 0.5 - m) / sd), 0.0)


def expected_floor_units(stat: str, position: str | None, mean, per: float, start: float = 0.0):
    """E[floor((X - start) / per)] (0 below ``start``) for a projected mean: what MFL's ``a/b`` pays per ``a`` in
    expectation. M2's ``scoring_ev.expected_floor_units`` when present, else the sum over whole units of
    ``prob_at_least`` (the normal fallback); a stat with no spread: linear."""
    import numpy as np
    m = np.asarray(mean, dtype=float)
    if _EV is not None and hasattr(_EV, "expected_floor_units"):
        try:
            return np.asarray(_EV.expected_floor_units(stat, position, m, per, start), dtype=float)
        except Exception:  # noqa: BLE001 - the fallback below
            pass
    if stat not in SPREAD_FALLBACK or per <= 0:
        return np.clip((m - start) / per, 0, None) if per > 0 else np.zeros_like(m)
    a, b = SPREAD_FALLBACK[stat]
    top = float(np.nanmax(m, initial=0.0))
    n_units = int(max(1, _math.ceil((top + 6 * (a + b * top) - start) / per)))
    out = np.zeros_like(m)
    for j in range(1, n_units + 1):
        out = out + prob_at_least(stat, position, m, start + j * per)
    return out


def expected_frame(stats, spec: ScoringSpec, positions, *, ev: bool | None = None):
    """Projected lines (a DataFrame of stat columns, one position per row) -> expected points (ndarray): rates and
    premiums linear; MFL's ``a/b`` steps (paid per WHOLE unit) at the expected whole units with ``ev`` (M2 measured
    linear 0.3-0.5 a game too high per yardage stat), linear without; a flat band = its points x P(in band) with
    ``ev`` (else all-or-nothing on the mean); a distance band = the TD count x the band's points x the share of TDs
    that long (M2's measured shares, else the placeholders)."""
    import numpy as np
    ev = ev_pricing() if ev is None else ev
    n = len(stats)
    pos = np.asarray(positions, dtype=object) if positions is not None else np.array([None] * n, dtype=object)
    total = np.zeros(n)

    def col(c: str) -> np.ndarray:
        return stats[c].to_numpy(dtype=float) if c in stats else np.zeros(n)
    for p in dict.fromkeys(pos.tolist()):
        sel = pos == p
        r = spec.rules_for(p)
        if r is None or not sel.any():
            continue
        t = np.zeros(int(sel.sum()))
        for s, w in r.rates.items():
            t = t + col(s)[sel] * w
        for s, w in r.premiums.items():
            t = t + col(s)[sel] * w
        for s, sts in r.steps.items():
            v = col(s)[sel]
            for st in sts:
                if st.base:
                    t = t + np.where(v >= st.low, st.base + st.per / st.unit * (v - st.origin), 0.0)
                elif ev:      # the expected whole units (M2: linear is ~0.3-0.5 a game too high per yardage stat)
                    t = t + st.per * expected_floor_units(s, p, v, st.unit, st.origin)
                else:
                    t = t + st.per / st.unit * v
        for s, bs in r.bands.items():
            v = col(s)[sel]
            for b in bs:
                if ev and s in SPREAD_FALLBACK:
                    pa = prob_at_least(s, p, v, b[0])
                    pb = prob_at_least(s, p, v, b[1] + 1) if b[1] is not None else 0.0
                    t = t + b[2] * np.clip(pa - pb, 0, 1)
                else:
                    t = t + b[2] * ((v >= b[0]) & ((v < b[1] + 1) if b[1] is not None else True))
        for fam, bs in r.distance.items():
            famd = DISTANCE_FAMILIES.get(fam, {"count": fam})
            if "buckets" in famd:          # kicks: the projected K line has the buckets (kd_values prices K)
                for blo, bhi, c in famd["buckets"]:
                    v = col(c)[sel]
                    for b in bs:
                        if b[0] <= blo and (b[1] is None or (bhi is not None and bhi <= b[1])):
                            t = t + v * b[2]
                continue
            v = col(famd["count"])[sel]
            per_td = sum(b[2] * _band_share(fam, p, b) for b in bs)
            t = t + v * per_td
        total[sel] = t
    return np.array([round(x, 2) for x in total.tolist()], dtype=float)


def expected_points(line: Mapping, spec: ScoringSpec, position: str | None = None, dist=None, *, ev: bool | None = True) -> float:
    """One projected line's expected points under the spec (``expected_frame`` on one row; ``ev`` on by default
    here: the probability-weighted bands). ``dist`` is accepted for M2's interface (unused: the module is read)."""
    import pandas as pd
    df = pd.DataFrame([{k: v for k, v in line.items() if isinstance(v, (int, float)) and not isinstance(v, bool)}])
    return float(expected_frame(df, spec, [position if position is not None else line.get("position")], ev=ev)[0])


# ---- M3 (Wave I-D): ONE pricing entry point for a projected stat line — the nightly (``projections.price``, prefix
# ``proj_``) and the request side (``anyleague.price_lines``) both call it, so a player is one number everywhere under
# either state of ``LEAGUE_LAB_EV_PRICING``. Actual lines never come here: a bonus on an actual line is a fact.
def compute_points_frame(stats, scoring: Mapping[str, float]):
    """``[compute_points(r, scoring) for r in stats.to_dict("records")]`` for every row at once (Wave H, H1; moved here
    from ``anyleague`` in Wave I-D): each scoring key's term added to the running total in ``scoring``'s order, as
    ``compute_points`` adds it, then Python's ``round(…, 2)`` per row — the same floating-point operations, so the same
    numbers bit for bit (tested), about 100x faster on a week's board."""
    import numpy as np
    n = len(stats)
    pos = stats["position"].to_numpy() if "position" in stats else None

    def col(c: str):
        return stats[c].to_numpy(dtype=float) if c in stats else np.zeros(n)
    total = np.zeros(n)
    for key, weight in scoring.items():
        if not weight:
            continue
        kind = MAPPED_KEYS.get(key)
        if kind is None:
            pk = SLEEPER_POSITION_MAP.get(key)
            if pk is not None and pos is not None:
                hit = pos == pk[1]
                total = np.where(hit, total + col(pk[0]) * float(weight), total)
            continue
        if key in SLEEPER_BONUS_MAP:
            c, low, high = SLEEPER_BONUS_MAP[key][:3]
            v = col(c)
            value = ((v >= low) & ((v < high) if high is not None else True)).astype(float)
        else:
            cols = _PY_EXPR[key]
            value = col(cols[0])
            for c in cols[1:]:
                value = value + col(c)
        total = total + value * float(weight)
    return np.array([round(x, 2) for x in total.tolist()], dtype=float)


def projected_view(flat: Mapping[str, float]) -> dict[str, float]:
    """The keys the flat engine prices on a projected line (``MAPPED_KEYS`` + the position premiums), non-zero, in key
    order. Expected-value pricing changes HOW a bonus is priced, never WHICH keys count: a key the flat engine leaves
    off a projected line (``pass_att``, ``rush_att``, ``rec_tgt``, ``pass_inc`` — the line projects no completions —
    the count bonuses) stays off. Sorted so two scorings with the same keys compile to the same arithmetic (a house
    league and the reference it IS price a line identically, ``projections.house_rows``)."""
    return {k: float(flat[k]) for k in sorted(flat) if flat[k] and (k in MAPPED_KEYS or k in SLEEPER_POSITION_MAP)}


def ev_moves(flat: Mapping[str, float]) -> bool:
    """Does expected-value pricing change this Sleeper scoring's projected prices? Only a yardage bonus
    (``SLEEPER_BONUS_MAP``) or a long-TD bonus (``SLEEPER_LONG_TD_MAP``) does; every other key on a projected line is a
    rate, priced exactly by the mean."""
    return any(w and (k in SLEEPER_BONUS_MAP or k in SLEEPER_LONG_TD_MAP) for k, w in flat.items())


_EV_SPECS: dict[str, ScoringSpec] = {}


def _ev_spec(flat: Mapping[str, float]) -> ScoringSpec:
    view = projected_view(flat)
    key = _json.dumps(view)
    sp = _EV_SPECS.get(key)
    if sp is None:
        if len(_EV_SPECS) > 256:
            _EV_SPECS.clear()
        sp = _EV_SPECS[key] = from_sleeper(view)
    return sp


def pricing_engine(scoring: Mapping[str, float] | ScoringSpec, *, ev: bool | None = None) -> str:
    """Which engine ``price_projected`` uses for this scoring: ``flat`` (the flat engine, all or nothing on the mean),
    ``ev`` (a Sleeper scoring with bonuses, the flag on) or ``spec`` (an MFL spec: always the expectation)."""
    spec = scoring if isinstance(scoring, ScoringSpec) else getattr(scoring, "spec", None)
    if isinstance(spec, ScoringSpec) and spec.flat is None:
        return "spec"
    flat = spec.flat if isinstance(spec, ScoringSpec) else scoring
    on = ev_pricing() if ev is None else bool(ev)
    return "ev" if on and ev_moves(flat) else "flat"


def price_projected(stats, scoring: Mapping[str, float] | ScoringSpec, position=None, *, ev: bool | None = None):
    """Points of every PROJECTED stat line (an ndarray, rounded to 2 per row). ``stats``: a frame of the flat engine's
    stat columns (``targets`` … ``fumbles_lost_total``), optionally ``position``; ``position`` (a scalar or one per row)
    overrides that column. ``scoring``: a flat Sleeper dict, a ``LeagueScoring`` (its ``spec``) or a ``ScoringSpec``.

    * an MFL spec (``flat is None``): ``expected_frame(..., ev=True)``, always (unchanged since IC-1);
    * a Sleeper scoring, ``ev`` off (``LEAGUE_LAB_EV_PRICING`` unset, the default): ``compute_points_frame`` — the
      pre-Wave-I-D numbers, bit for bit;
    * a Sleeper scoring, ``ev`` on: ``expected_frame(..., ev=True)`` on the spec of ``projected_view`` — a yardage bonus
      at its probability, a long-TD bonus at the projected TDs × the share that long (M2's curves and shares) — when
      the scoring has such a bonus (``ev_moves``); a scoring without one (Scrubs, the plain reference scorings) keeps
      the flat engine, so it is unchanged to the bit by construction."""
    import numpy as np
    n = len(stats)
    if position is None:
        pos = stats["position"].to_numpy() if "position" in stats else None
    elif np.ndim(position) == 0:
        pos = np.array([position] * n, dtype=object)
    else:
        pos = np.asarray(position, dtype=object)
    engine = pricing_engine(scoring, ev=ev)
    spec = scoring if isinstance(scoring, ScoringSpec) else getattr(scoring, "spec", None)
    if engine == "spec":
        return expected_frame(stats, spec, pos, ev=True)
    flat = spec.flat if isinstance(spec, ScoringSpec) else scoring
    if engine == "ev":
        return expected_frame(stats, _ev_spec(flat), pos, ev=True)
    if pos is not None and (position is not None or "position" not in stats):
        stats = stats.assign(position=pos)
    return compute_points_frame(stats, flat)
# ---- /M3


# ------------------------------------------------------------------------------------------- spec -> flat (old readers)
_FLAT_RATE = {"passing_yards": "pass_yd", "passing_tds": "pass_td", "passing_interceptions": "pass_int",
              "passing_2pt_conversions": "pass_2pt", "rushing_yards": "rush_yd", "rushing_tds": "rush_td",
              "rushing_2pt_conversions": "rush_2pt", "receptions": "rec", "receiving_yards": "rec_yd",
              "receiving_tds": "rec_td", "receiving_2pt_conversions": "rec_2pt", "fumbles_total": "fum",
              "fumbles_lost_total": "fum_lost", "fumble_recovery_tds": "fum_rec_td", "special_teams_tds": "st_td",
              "pat_made": "xpm", "pat_missed": "xpmiss", "fg_missed": "fgmiss"}
_FLAT_TD = {"passing_tds": "pass_td", "rushing_tds": "rush_td", "receiving_tds": "rec_td",
            "fumble_recovery_tds": "fum_rec_td", "return_tds": "st_td"}


def _per_td(r: Rules, fam: str, position: str | None) -> float:
    return sum(b[2] * _band_share(fam, position, b) for b in r.distance.get(fam, []))


def kd_flat(spec: ScoringSpec, position: str) -> dict[str, float]:
    """A Sleeper-shaped K (or DEF) dict for kd1.0's ``kdef.price``: the Sleeper settings themselves for a Sleeper
    spec; for MFL: FG by distance onto Sleeper's buckets (50+ = the 50–59 band), points-allowed bands onto Sleeper's
    by the average over each bucket's points, defensive / return TDs by distance at the expected points per TD."""
    if spec.flat is not None:
        return dict(spec.flat)
    r = spec.rules_for(position)
    out: dict[str, float] = {}
    if r is None:
        return out
    if position == "K":
        for key, (fam, lo, hi) in SLEEPER_FG.items():
            mid = lo + 2 if hi is None else (lo + hi) / 2.0
            for b in r.distance.get(fam, []):
                if _in_band(mid, b):
                    out[key] = out.get(key, 0.0) + b[2]
        for s, w in r.rates.items():
            if s in _FLAT_RATE:
                out[_FLAT_RATE[s]] = w
        return out
    inv = {v: k for k, v in SLEEPER_DEF.items()}
    for s, w in r.rates.items():
        if s in inv:
            out[inv[s]] = out.get(inv[s], 0.0) + w
    for fam in ("def_tds", "st_tds"):
        if r.distance.get(fam):
            out[inv[fam]] = out.get(inv[fam], 0.0) + round(_per_td(r, fam, "DEF"), 3)
    pa = r.bands.get("points_allowed", [])
    for key, (lo, hi) in SLEEPER_PA.items():
        top = hi if hi is not None else 45
        vals = [sum(b[2] for b in pa if _in_band(float(x), b)) for x in range(lo, top + 1)]
        if any(vals):
            out[key] = round(sum(vals) / len(vals), 3)
    return out


def flat_from_spec(spec: ScoringSpec) -> dict[str, float]:
    """An approximate Sleeper ``scoring_settings`` for the readers that still take one (labels, the K / DEF line
    pricing): the WR rules (else the first skill position's), QB's passing keys, ``kd_flat`` for K and DEF. The spec
    is the truth; this dict is only ever a summary of it."""
    if spec.flat is not None:
        return dict(spec.flat)
    out: dict[str, float] = {}
    for p in ("TE", "RB", "WR", "QB"):            # later positions win: QB for passing, WR for the rest
        r = spec.rules_for(p)
        if r is None:
            continue
        for s, w in r.rates.items():
            if s in _FLAT_RATE and (p != "QB" or s.startswith("passing")):
                out[_FLAT_RATE[s]] = w
        for s, sts in r.steps.items():
            if s in _FLAT_RATE and sts and (p != "QB" or s.startswith("passing")):
                out[_FLAT_RATE[s]] = round(sts[0].per / sts[0].unit, 6)
        for fam, key in _FLAT_TD.items():
            if r.distance.get(fam) and (p != "QB" or fam == "passing_tds"):
                out[key] = r.distance[fam][0][2] if r.distance[fam][0][0] <= 0 else out.get(key, 0.0)
    for p in ("TE", "RB", "WR"):
        r = spec.rules_for(p)
        if r is not None and p != "WR" and "receptions" in (r.rates or {}):
            d = r.rates["receptions"] + r.premiums.get("receptions", 0.0) - out.get("rec", 0.0)
            if round(d, 6):
                out[f"bonus_rec_{p.lower()}"] = round(d, 6)
    if "K" in spec.positions:
        out.update({k: v for k, v in kd_flat(spec, "K").items() if k.startswith(("fgm", "fgmiss", "xpm"))})
    if "DEF" in spec.positions:
        out.update(kd_flat(spec, "DEF"))
    return out
