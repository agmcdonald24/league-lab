"""Player signals (plan R-10 role alerts, R-12 scenario upside). docs/METRICS.md § Role alerts / § Scenario upside.

Role alerts (R-10, rule ``SIGNALS_VERSION``)
--------------------------------------------
Per player x week: has his **role** changed in the last one to three games, and why? Read from
``intermediate.int_player_game_role`` (every QB / RB / WR / TE on a team's roster for every played
regular-season game, with the reason when he missed it), per position:

* **snap share** (all positions) and **route share** (the routes proxy: on the field for a dropback;
  completed seasons only, the NFL publishes it after the season) are *structural*: they move when a
  coach changes who plays;
* **target share** (RB / WR / TE) and **carry share** (RB) move with the game plan as well: supporting
  evidence, never an alert on their own (an RB's carry share excepted, with a named reason or two games).

For the latest game ``W`` and ``k`` = 1, 2, 3 (the games it has held) the window ``N`` = his last ``k``
games and the prior ``P`` = up to ``PRIOR_GAMES`` games before it (injury absences are skipped, a
healthy scratch counts as 0). A metric has **changed** when

* the window level (mean share; targets / team targets for the target and carry share) is at least
  ``STEP`` above (or below) the prior level (the median of the prior games, so a short injury fill-in
  inside the prior does not become the baseline), every game of the window is past it and the game
  before the window was not;
* the new level (an up alert) or the old one (a down alert) is a fantasy-relevant role (``FLOOR``);
* the change is bigger than noise: ``z = change / (SIGMA x sqrt(1/k + 1/n_prior)) >= Z_MIN``, with
  ``SIGMA`` the typical game-to-game swing of that share at his position (median within-player sd,
  2016-2025). With a named reason ``Z_MIN_TRIGGER`` is enough: the reason is evidence too.

One game (k = 1) is an alert only when a structural metric changed (not in a ``BLOWOUT``) or a reason
explains it; a one-game drop needs a reason and is skipped when he is on the next week's report (Out /
Doubtful / IR: he got hurt). A bigger role is never read from a missed game or a return from injury, and
an up change whose window held an injured starter's absence that has already ended is expired. The alert
keeps the longest ``k`` with a named reason, else the longest ``k``; after three games the change is his
role, and the projection's last-3 inputs have caught up.

**Reasons** (``find_triggers``) and **kind** (``alert_kind``): his own team changed (traded -> new_team);
a starter of his position group missed every window game (out injured / traded / released ->
absence_beneficiary; inactive while healthy or < 10% of the snaps -> a benching, depth_move); his own
depth-chart rank crossed the starter line (nflverse depth charts, 2025 on -> depth_move); a new starter
took over (the label of a down alert -> depth_move); a missing teammate came back (-> role_down); none
(role_up / role_down, "the coaches changed his role"). Each alert carries the evidence (before -> after
per share), the games held, the cause in words and an expiry (three weeks; an absence alert also ends
when the teammate is back on the report: ``mart_player_role_alerts.trigger_ended``).

Scenario upside (R-12)
----------------------
For every QB / RB / WR / TE with a live **up** alert, a *larger-role* scenario next to the *base* (the
projection as stored): the same component models (refitted here on the same rows as
``projections.project``: deterministic, checked against the stored projection) re-predict the stat line
with his last-3-games inputs set to the level of the games since the change, each capped at the
position's 90th percentile (``input_caps``); catches, yards and touchdowns follow the volume at his own
last-3 rate (a larger role, not better hands); priced in each league's scoring. ``with_alert`` weighs the
gap by the historical hold rate. It lapses (``expires_after_week``) three weeks after the alert, or
earlier when the injured teammate is expected back (re-read every night). Calibrated before any
probability is shown (``scenario_backtest``, constants ``HOLD_RATE`` / ``BACKTEST`` / ``SCENARIO_SHIP``):
on 2023-2025 neither line beat the projection more often than not, so the pages show a "what if" with its
hit rate.

Outputs: ``ops.player_role_alerts`` (every season), ``ops.player_scenarios`` (the projected season);
views ``mart_player_role_alerts`` and ``mart_player_scenarios``. The waiver upside list is
``waivers.upside_after_waivers`` (``ops.waiver_upside``).
"""

from __future__ import annotations

import logging
import math
import statistics
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np
import pandas as pd
import psycopg

from . import league_status as LS  # ---- IS-2

log = logging.getLogger(__name__)

# ra1.2 (projection v3, 2026-10-01): same rule; int_player_game_role now keeps the Raiders 2016-19 and the Chargers
# 2016 (one code per franchise), so every season is recomputed once under the new version
SIGNALS_VERSION = "ra1.2"

# ------------------------------------------------------------------------------ the alert rule (fixed constants: a change is a new version)
POSITION_METRICS: dict[str, tuple[str, ...]] = {
    "QB": ("snap_share",),
    "RB": ("snap_share", "route_share", "carry_share", "target_share"),
    "WR": ("snap_share", "route_share", "target_share"),
    "TE": ("snap_share", "route_share", "target_share"),
}
STRUCTURAL = frozenset({"snap_share", "route_share"})
# a practical minimum change (share points, 0-1 scale) and the role level that makes it matter
STEP = {"snap_share": 0.20, "route_share": 0.20, "target_share": 0.08, "carry_share": 0.15}
STEP_QB = {"snap_share": 0.30}
FLOOR = {"snap_share": 0.45, "route_share": 0.45, "target_share": 0.12, "carry_share": 0.30}
FLOOR_QB = {"snap_share": 0.50}
# typical game-to-game swing (median within-player sd over player-seasons with 6+ games and 30%+ snaps,
# 2016-2025, int_player_game_role; rounded)
SIGMA: dict[tuple[str, str], float] = {
    ("QB", "snap_share"): 0.12,
    ("RB", "snap_share"): 0.14, ("RB", "route_share"): 0.15, ("RB", "target_share"): 0.055, ("RB", "carry_share"): 0.15,
    ("WR", "snap_share"): 0.17, ("WR", "route_share"): 0.20, ("WR", "target_share"): 0.072,
    ("TE", "snap_share"): 0.14, ("TE", "route_share"): 0.19, ("TE", "target_share"): 0.055,
}
Z_MIN = 2.0            # without a trigger: a clear change for him
Z_MIN_TRIGGER = 1.5    # with a named reason (ra1.1: 1.0 -> 1.5; 2025 first detections at z <= 1.5 held 44% of the time)
PRIOR_GAMES = 8
MAX_HELD = 3
BLOWOUT = 20           # a one-game snap jump in a game decided by 20+ is garbage time unless a trigger explains it
STARTER = {"QB": 0.50, "RB": 0.40, "WR": 0.50, "TE": 0.50}
ABSENT_SNAP = 0.10
GROUP = {"QB": "QB", "RB": "RB", "WR": "REC", "TE": "REC"}
CONFIDENCE = {1: "one game", 2: "two games", 3: "three games"}
METRIC_WORDS = {"snap_share": "snap share", "route_share": "routes", "target_share": "target share", "carry_share": "carry share"}
# depth chart (nflverse, daily snapshots from 2025): the best rank at his position that makes him a starter
STARTER_RANK = {"QB": 1, "RB": 1, "WR": 3, "TE": 1}
# what the alert is (plan R-10), from the direction and the named reason (``alert_kind``)
KINDS = ("role_up", "role_down", "absence_beneficiary", "depth_move", "new_team")

ALERT_COLUMNS = [
    "season", "week", "game_id", "gsis_id", "player_name", "position", "team", "direction", "games_held", "since_week",
    "confidence", "primary_metric", "metrics_changed", "z", "snap_from", "snap_to", "route_from", "route_to",
    "target_from", "target_to", "carry_from", "carry_to", "trigger_kind", "trigger_gsis_id", "trigger_name",
    "trigger_status", "trigger_text", "change_text", "prior_games", "kind", "cause_text", "expires_after_week", "expiry_rule",
    "signals_version", "run_at",
]


def _is_num(v) -> bool:
    return v is not None and not (isinstance(v, float) and math.isnan(v))


def pct(v: float | None) -> str:
    return "—" if not _is_num(v) else f"{100 * float(v):.0f}%"


@dataclass(frozen=True)
class Game:
    """One player x team-game of int_player_game_role (the fields the rule reads)."""
    gsis_id: str
    season: int
    week: int
    team: str
    position: str
    player_name: str
    status: str                       # played / out_injured / inactive
    snap_share: float | None
    route_share: float | None
    targets: float
    team_targets: float | None
    carries: float
    team_carries: float | None
    team_margin: float | None = None
    report_status: str | None = None
    roster_status: str | None = None
    game_id: str | None = None

    def share(self, metric: str) -> float | None:
        if metric == "snap_share":
            return self.snap_share
        if metric == "route_share":
            return self.route_share
        if metric == "target_share":
            return self.targets / self.team_targets if self.team_targets else None
        if metric == "carry_share":
            return self.carries / self.team_carries if self.team_carries else None
        raise KeyError(metric)

    @property
    def absent(self) -> bool:
        """Missing from the game as a player of consequence (out, inactive, or a token snap count)."""
        return self.status != "played" or (self.snap_share is not None and self.snap_share < ABSENT_SNAP)


def window_level(games: list[Game], metric: str) -> float | None:
    """The window's level: the mean share (snaps, routes) or targets / team targets (carries likewise)."""
    if metric in ("target_share", "carry_share"):
        num = sum(g.targets if metric == "target_share" else g.carries for g in games)
        den = sum((g.team_targets if metric == "target_share" else g.team_carries) or 0 for g in games)
        return num / den if den > 0 else None
    vals = [g.share(metric) for g in games]
    vals = [v for v in vals if _is_num(v)]
    return sum(vals) / len(vals) if len(vals) == len(games) and vals else None


def prior_level(games: list[Game], metric: str) -> tuple[float | None, int]:
    vals = [g.share(metric) for g in games]
    vals = [float(v) for v in vals if _is_num(v)]
    return (float(statistics.median(vals)), len(vals)) if vals else (None, 0)


@dataclass
class MetricChange:
    metric: str
    before: float
    after: float
    z: float
    held: bool       # every window game shows the step, and the game before the window did not


def metric_change(position: str, metric: str, window: list[Game], prior: list[Game], direction: str) -> MetricChange | None:
    """The change of one share between the prior games and the window, or None when unknown."""
    before, n_p = prior_level(prior, metric)
    after = window_level(window, metric)
    if before is None or after is None or n_p == 0:
        return None
    step = (STEP_QB if position == "QB" else STEP)[metric]
    sign = 1 if direction == "up" else -1
    per_game = [g.share(metric) for g in window]
    last = prior[-1].share(metric)
    held = (all(_is_num(v) and sign * (float(v) - before) >= step for v in per_game)
            # the change starts with the window: the game before it was still at the old level
            and not (_is_num(last) and sign * (float(last) - before) >= step))
    sigma = SIGMA[(position, metric)]
    z = (after - before) / (sigma * math.sqrt(1 / len(window) + 1 / n_p))
    return MetricChange(metric, before, after, z, held)


def changed(position: str, c: MetricChange | None, direction: str, z_min: float) -> bool:
    if c is None or not c.held:
        return False
    floor = (FLOOR_QB if position == "QB" else FLOOR)[c.metric]
    sign = 1 if direction == "up" else -1
    level = c.after if direction == "up" else c.before
    return level >= floor and sign * c.z >= z_min


# ------------------------------------------------------------------------------ triggers
@dataclass(frozen=True)
class Trigger:
    kind: str                 # teammate_out / teammate_back / teammate_up / teammate_returned / traded / depth_up / depth_down
    gsis_id: str | None
    name: str | None
    status: str | None        # out_injured / inactive / gone / traded_away / barely_played / back / took_over / <team> / <rank>
    level: float              # the teammate's snap share (for ordering)

    def text(self) -> str:
        if self.kind == "traded":
            return f"traded to {self.status}"
        if self.kind == "teammate_back":
            return f"{self.name} back"
        if self.kind == "teammate_up":
            return f"{self.name} took over"
        if self.kind == "teammate_returned":
            return f"{self.name} returned"
        if self.kind in ("depth_up", "depth_down"):
            return f"{'up' if self.kind == 'depth_up' else 'down'} to {self.status} on the depth chart"
        return {"out_injured": f"{self.name} out", "inactive": f"{self.name} benched", "gone": f"{self.name} gone from the team",
                "traded_away": f"{self.name} traded", "barely_played": f"{self.name} benched"}.get(self.status or "", f"{self.name} out")


class TeamIndex:
    """Per season: every team-game's player rows (for teammates), each player's last-season level and
    (2025 on) his depth-chart rank at his position in the last snapshot before each of his team's games."""

    def __init__(self, games: list[Game], prev_level: dict[str, float], depth: dict[tuple[str, int], dict[str, int]] | None = None,
                 reports: dict[tuple[str, int], str] | None = None):
        self.by_team_week: dict[tuple[str, int], dict[str, Game]] = defaultdict(dict)
        self.by_week: dict[int, set[str]] = defaultdict(set)
        for g in games:
            self.by_team_week[(g.team, g.week)][g.gsis_id] = g
            self.by_week[g.week].add(g.gsis_id)
        self.prev_level = prev_level
        self.depth = depth or {}
        self.reports = reports or {}

    def hurt_after(self, team: str, week: int, gsis_id: str) -> bool:
        """He is on the next week's injury report (Out / Doubtful / IR) or missed his team's next game injured:
        a game he barely played was an injury, not a benching."""
        if self.reports.get((gsis_id, week + 1)) in ("Out", "Doubtful", "IR"):
            return True
        later = sorted(w for (t, w) in self.by_team_week if t == team and w > week)
        nxt = self.row(team, later[0], gsis_id) if later else None
        return nxt is not None and nxt.status == "out_injured"

    def teammates(self, team: str, weeks: list[int], group: str, exclude: str) -> set[str]:
        out = set()
        for w in weeks:
            for gid, g in self.by_team_week.get((team, w), {}).items():
                if gid != exclude and GROUP.get(g.position) == group:
                    out.add(gid)
        return out

    def row(self, team: str, week: int, gsis_id: str) -> Game | None:
        return self.by_team_week.get((team, week), {}).get(gsis_id)

    def rank(self, team: str, week: int, gsis_id: str) -> int | None:
        """His depth-chart rank before that game (None: no snapshot that season, or not on the chart)."""
        chart = self.depth.get((team, week))
        return None if not chart else chart.get(gsis_id, 99)


def _absence(idx: TeamIndex, team: str, week: int, gsis_id: str) -> str | None:
    """Why he was missing from his team's game that week (None: he played a real part)."""
    g = idx.row(team, week, gsis_id)
    if g is None:
        return "traded_away" if gsis_id in idx.by_week.get(week, ()) else "gone"
    if g.status == "out_injured":
        return "out_injured"
    if g.status == "inactive":
        return "inactive"
    if g.snap_share is not None and g.snap_share < ABSENT_SNAP:
        return "barely_played"
    return None


def depth_trigger(idx: TeamIndex, p: Game, window: list[Game], prior: list[Game]) -> Trigger | None:
    """A depth-chart move that brackets the change: a starter's rank (``STARTER_RANK``) before the latest
    window game and not before the last prior game (depth_up), or the reverse (depth_down). Needs a
    snapshot before both games (nflverse publishes them from 2025)."""
    team = window[-1].team
    if not prior or prior[-1].team != team:
        return None
    thr = STARTER_RANK.get(p.position)
    before, after = idx.rank(team, prior[-1].week, p.gsis_id), idx.rank(team, window[-1].week, p.gsis_id)
    if thr is None or before is None or after is None:
        return None
    label = f"{p.position}{after}" if after < 99 else "off the chart"
    if before > thr >= after:
        return Trigger("depth_up", p.gsis_id, p.player_name, label, 1.0)
    if after > thr >= before:
        return Trigger("depth_down", p.gsis_id, p.player_name, label, 1.0)
    return None


def find_triggers(idx: TeamIndex, p: Game, window: list[Game], prior: list[Game]) -> list[Trigger]:
    """Named reasons for a change in p's role between ``prior`` and ``window`` (strongest first).

    * traded: p's own team changed between the prior games and the window;
    * teammate_out: a teammate of his group who started in the prior games (median snap share >=
      STARTER; last season's level when he has fewer than two prior games) played a real part in the
      last prior game and is missing from every window game;
    * teammate_back: one missing from the last prior game who starts every window game;
    * teammate_up: one who did not start in the prior games and starts every window game (a new
      starter: a benching's other side);
    * teammate_returned: a starter missing from some window games who is back for the latest one (the
      bigger role such a window shows has already ended: it suppresses an up alert);
    * depth_up / depth_down: his own depth-chart move (``depth_trigger``)."""
    out: list[Trigger] = []
    team = window[-1].team
    if prior and prior[-1].team != team and all(g.team == team for g in window):
        out.append(Trigger("traded", None, None, team, 1.0))
    group = GROUP.get(p.position)
    wweeks = [g.week for g in window]
    pweeks = [g.week for g in prior if g.team == team]
    if (dt := depth_trigger(idx, p, window, prior)) is not None:
        out.append(dt)
    if not pweeks or group is None:
        return out
    last_p = pweeks[-1]
    for q in sorted(idx.teammates(team, pweeks + wweeks, group, p.gsis_id)):
        rows = [r for w in pweeks + wweeks if (r := idx.row(team, w, q)) is not None]
        name, pos = rows[0].player_name, rows[0].position
        start = STARTER.get(pos, 0.5)
        q_prior = [r for w in pweeks if (r := idx.row(team, w, q)) is not None and r.status == "played" and r.snap_share is not None]
        lvl = float(statistics.median([r.snap_share for r in q_prior])) if q_prior else 0.0
        if len(q_prior) < 2:
            lvl = max(lvl, idx.prev_level.get(q, 0.0))
        why = [_absence(idx, team, w, q) for w in wweeks]
        in_window = [idx.row(team, w, q) for w in wweeks]
        starts_window = all(r is not None and r.status == "played" and (r.snap_share or 0) >= start for r in in_window)
        if q_prior and lvl >= start and all(why) and _absence(idx, team, last_p, q) is None:
            status = why[-1]
            if status == "barely_played" and idx.hurt_after(team, wweeks[-1], q):
                status = "out_injured"        # left early hurt, then out: an injury, not a benching
            out.append(Trigger("teammate_out", q, name, status, lvl))
        elif _absence(idx, team, last_p, q) in ("out_injured", "inactive", "gone", "traded_away") and starts_window:
            out.append(Trigger("teammate_back", q, name, "back", sum(r.snap_share for r in in_window) / len(in_window)))
        elif len(q_prior) >= 2 and lvl < start and starts_window:
            out.append(Trigger("teammate_up", q, name, "took_over", sum(r.snap_share for r in in_window) / len(in_window)))
        elif (q_prior and lvl >= start and any(why[:-1]) and why[-1] is None
              and _absence(idx, team, last_p, q) is None and why[0] is not None):
            out.append(Trigger("teammate_returned", q, name, "back", lvl))
    order = {"traded": 0, "teammate_out": 1, "teammate_back": 1, "teammate_up": 2, "depth_up": 3, "depth_down": 3, "teammate_returned": 4}
    return sorted(out, key=lambda t: (order[t.kind], -t.level, t.name or ""))


# ------------------------------------------------------------------------------ the rule over one player
@dataclass
class Alert:
    game: Game
    direction: str
    k: int
    changes: list[MetricChange]
    trigger: Trigger | None
    n_prior: int
    all_changes: dict[str, MetricChange]
    window: list[Game]

    @property
    def since_week(self) -> int:
        return self.window[0].week


def _trigger_for(triggers: list[Trigger], direction: str) -> Trigger | None:
    """The reason that lowers the bar (a teammate out / back, a trade, his own depth-chart move)."""
    kinds = {"up": ("traded", "teammate_out", "depth_up"), "down": ("traded", "teammate_back", "depth_down")}[direction]
    return next((t for t in triggers if t.kind in kinds), None)


def evaluate(p_games: list[Game], i: int, idx: TeamIndex, next_report: str | None = None,
             after_injury: list[bool] | None = None) -> Alert | None:
    """The alert for the player's game ``p_games[i]`` (his role-relevant games, week order), or None.
    ``after_injury[j]``: he missed games injured just before ``p_games[j]`` (a return is not a role change).

    Every window length k = 3, 2, 1 that shows a change is a candidate; the alert keeps the longest
    one with a named reason, else the longest one (so the week a teammate went out is the start of
    the story, not a drift that began a game earlier)."""
    g = p_games[i]
    pos = g.position
    metrics = POSITION_METRICS.get(pos)
    if not metrics:
        return None
    after_injury = after_injury or [False] * len(p_games)
    found: list[Alert] = []
    for k in range(min(MAX_HELD, i), 0, -1):          # needs >= 1 prior game
        window = p_games[i - k + 1:i + 1]
        prior = p_games[max(0, i - k + 1 - PRIOR_GAMES):i - k + 1]
        back_from_injury = after_injury[i - k + 1]
        for direction in ("up", "down"):
            if direction == "up" and (back_from_injury or any(w.status != "played" for w in window)):
                continue                               # a bigger role is played, not inferred; a return is not a change
            if direction == "down" and k == 1 and (back_from_injury or next_report in ("Out", "Doubtful", "IR")):
                continue                               # eased back in, or he got hurt: the injury report's story
            cands = {m: metric_change(pos, m, window, prior, direction) for m in metrics}
            loose = [m for m, c in cands.items() if changed(pos, c, direction, Z_MIN_TRIGGER)]
            if not loose:
                continue
            triggers = find_triggers(idx, g, window, prior)
            reason = _trigger_for(triggers, direction)
            z_min = Z_MIN_TRIGGER if reason is not None else Z_MIN
            hits = [cands[m] for m in loose if changed(pos, cands[m], direction, z_min)]
            if k == 1 and reason is None and direction == "down":
                continue       # ra1.1: a one-game drop without a named reason held 32% of the time in 2025 (an off day)
            if k == 1 and reason is None:
                hits = [c for c in hits if c.metric in STRUCTURAL]   # one game of target / carry share alone: noise
                if abs(g.team_margin or 0) >= BLOWOUT:
                    hits = []                                        # garbage time
            if not any(c.metric in STRUCTURAL or (pos == "RB" and c.metric == "carry_share" and (k >= 2 or reason is not None))
                       for c in hits):
                continue       # ra1.1: a share of the ball alone (no snap / route change) is supporting evidence, not an alert
            if direction == "up" and reason is None and any(t.kind == "teammate_returned" for t in triggers):
                continue       # ra1.1: the bigger role came with a teammate's absence that has ended: expired, not news
            label = reason or next((t for t in triggers if t.kind == "teammate_up" and direction == "down"), None)
            hits.sort(key=lambda c: (c.metric not in STRUCTURAL, -abs(c.z)))
            found.append(Alert(g, direction, k, hits, label, len(prior), {m: c for m, c in cands.items() if c is not None}, window))
    if not found:
        return None
    named = [a for a in found if a.trigger is not None and a.trigger.kind != "teammate_up"]
    return (named or found)[0]


def change_text(a: Alert) -> str:
    return ", ".join(f"{METRIC_WORDS[c.metric]} {pct(c.before)} → {pct(c.after)}" for c in a.changes)


def alerts_for_season(games: list[Game], prev_level: dict[str, float], next_reports: dict[tuple[str, int], str] | None = None,
                      depth: dict[tuple[str, int], dict[str, int]] | None = None) -> list[Alert]:
    """Every alert of one season. ``games``: that season's int_player_game_role rows; ``prev_level``:
    gsis_id -> last season's median snap share; ``next_reports``: (gsis_id, week) -> injury report
    status for that week (or 'IR'); ``depth``: (team, week) -> {gsis_id: depth-chart rank at his
    position before that game} (2025 on)."""
    idx = TeamIndex(games, prev_level, depth, next_reports)
    by_player: dict[str, list[Game]] = defaultdict(list)
    for g in games:
        by_player[g.gsis_id].append(g)
    out = []
    next_reports = next_reports or {}
    for gid in sorted(by_player):
        full = sorted(by_player[gid], key=lambda g: g.week)
        seq = [g for g in full if g.status != "out_injured"]
        hurt = [g.week for g in full if g.status == "out_injured"]
        after_injury = [j > 0 and any(seq[j - 1].week < w < seq[j].week for w in hurt) for j in range(len(seq))]
        for i in range(1, len(seq)):
            g = seq[i]
            if g.status != "played" and seq[i - 1].status != "played":
                continue                               # a run of inactive weeks: one alert at most (its first week)
            a = evaluate(seq, i, idx, next_reports.get((gid, g.week + 1)), after_injury)
            if a is not None:
                out.append(a)
    return out


EXPIRY_WEEKS = 3        # an alert (and its scenario) covers the three weeks after it; by then his last-3 inputs are the new role


def alert_kind(direction: str, trigger: Trigger | None) -> str:
    """role_up / role_down (no named reason, or a teammate back), absence_beneficiary (a starter
    teammate out injured, traded or gone), depth_move (a benching, a new starter, a depth-chart move),
    new_team (he was traded)."""
    t = trigger.kind if trigger else "none"
    if t == "traded":
        return "new_team"
    if t == "teammate_out":
        return "depth_move" if (trigger.status in ("inactive", "barely_played")) else "absence_beneficiary"
    if t in ("teammate_up", "depth_up", "depth_down"):
        return "depth_move"
    return "role_up" if direction == "up" else "role_down"


def cause_text(a: Alert) -> str:
    """The cause in words (always set: no named reason is said as such)."""
    if a.trigger is not None:
        t = a.trigger.text()
        if a.trigger.kind == "teammate_out" and a.trigger.status == "out_injured":
            t += " injured"
        return t
    return "no teammate out, no trade: the coaches changed his role"


def expiry(a: Alert) -> tuple[int, str]:
    """(expires_after_week, rule): three weeks after the alert, earlier for an absence when the teammate returns."""
    last = a.game.week + EXPIRY_WEEKS
    if a.trigger is not None and a.trigger.kind == "teammate_out" and a.trigger.status == "out_injured" and a.direction == "up":
        return last, f"ends when {a.trigger.name} returns, and after week {last} at the latest"
    if a.direction == "up":
        return last, f"after week {last} his projection has caught up if the role holds"
    return last, f"after week {last} his projection has caught up if the smaller role holds"


def _lv(changes: dict[str, MetricChange], m: str, which: str) -> float | None:
    x = changes.get(m)
    return None if x is None else round(float(getattr(x, which)), 4)


def alert_rows(alerts: list[Alert], run_at: datetime | None = None) -> pd.DataFrame:
    run_at = run_at or datetime.now(UTC)
    rows = []
    for a in alerts:
        g = a.game
        c = a.all_changes
        rows.append({
            "season": g.season, "week": g.week, "game_id": g.game_id, "gsis_id": g.gsis_id, "player_name": g.player_name,
            "position": g.position, "team": g.team, "direction": a.direction, "games_held": a.k, "since_week": a.since_week,
            "confidence": CONFIDENCE[a.k], "primary_metric": a.changes[0].metric,
            "metrics_changed": [x.metric for x in a.changes], "z": round(float(a.changes[0].z), 2),
            "snap_from": _lv(c, "snap_share", "before"), "snap_to": _lv(c, "snap_share", "after"),
            "route_from": _lv(c, "route_share", "before"), "route_to": _lv(c, "route_share", "after"),
            "target_from": _lv(c, "target_share", "before"), "target_to": _lv(c, "target_share", "after"),
            "carry_from": _lv(c, "carry_share", "before"), "carry_to": _lv(c, "carry_share", "after"),
            "trigger_kind": a.trigger.kind if a.trigger else "none",
            "trigger_gsis_id": a.trigger.gsis_id if a.trigger else None,
            "trigger_name": a.trigger.name if a.trigger else None,
            "trigger_status": a.trigger.status if a.trigger else None,
            "trigger_text": a.trigger.text() if a.trigger else None,
            "change_text": change_text(a), "prior_games": a.n_prior, "kind": alert_kind(a.direction, a.trigger),
            "cause_text": cause_text(a), "expires_after_week": expiry(a)[0], "expiry_rule": expiry(a)[1],
            "signals_version": SIGNALS_VERSION, "run_at": run_at,
        })
    return pd.DataFrame(rows, columns=ALERT_COLUMNS)


# ------------------------------------------------------------------------------ loading
ROLE_SQL = """
select gsis_id, season, week, game_id, team, position, player_name, status, report_status, roster_status,
       snap_share::float8, route_share::float8, targets::float8, team_targets::float8, carries::float8, team_carries::float8,
       team_margin::float8
from intermediate.int_player_game_role where season = any(%s) order by season, gsis_id, week"""

PREV_SQL = """
select gsis_id, season, percentile_cont(0.5) within group (order by snap_share)::float8 as level
from intermediate.int_player_game_role where status = 'played' and snap_share is not null and season = any(%s)
group by 1, 2"""

# the injury report of the following week (Out / Doubtful), or injured reserve on the weekly roster
NEXT_REPORT_SQL = """
select gsis_id, season, week, max(case when report_status in ('Out', 'Doubtful') then report_status end) as report
from staging.stg_nflverse__injuries where season = any(%s) and game_type = 'REG' and gsis_id is not null group by 1, 2, 3
union all
select gsis_id, season, week, 'IR' from intermediate.int_player_week_team
where season = any(%s) and season_type = 'REG' and roster_status in ('RES', 'PUP')"""


# his best depth-chart rank at his own position in the team's last snapshot before each played game
# (nflverse depth charts: daily snapshots from 2025; earlier seasons have none, so no depth reasons)
DEPTH_SQL = """
with d as (
    select season, snapshot_at, team, gsis_id, pos_abb, min(pos_rank) as pos_rank
    from staging.stg_nflverse__depth_charts
    where season = any(%s) and pos_abb in ('QB', 'RB', 'WR', 'TE')
    group by 1, 2, 3, 4, 5
),
snaps as (select distinct season, team, snapshot_at from d),
g as (select distinct season, week, team, kickoff_at from intermediate.int_player_game_role where season = any(%s)),
pick as (
    select g.season, g.week, g.team, max(s.snapshot_at) as snapshot_at
    from g join snaps as s on s.season = g.season and s.team = g.team and s.snapshot_at < g.kickoff_at
    group by 1, 2, 3
)
select p.season, p.week, p.team, d.gsis_id, min(d.pos_rank) as pos_rank
from pick as p
join d on d.season = p.season and d.team = p.team and d.snapshot_at = p.snapshot_at
join analytics.dim_player as dp on dp.gsis_id = d.gsis_id and dp.position = d.pos_abb
group by 1, 2, 3, 4"""


def load_depth(conn: psycopg.Connection, seasons: list[int]) -> dict[int, dict[tuple[str, int], dict[str, int]]]:
    """season -> (team, week) -> {gsis_id: rank} (empty without depth charts)."""
    out: dict[int, dict[tuple[str, int], dict[str, int]]] = defaultdict(lambda: defaultdict(dict))
    with conn.cursor() as cur:
        cur.execute("select to_regclass('staging.stg_nflverse__depth_charts') is not null")
        if not cur.fetchone()[0]:
            return out
        cur.execute(DEPTH_SQL, (seasons, seasons))
        for season, week, team, gid, rank in cur.fetchall():
            out[int(season)][(team, int(week))][gid] = int(rank)
    return out


def _none(v):
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else v


def load_games(conn: psycopg.Connection, seasons: list[int], routes: bool = True
               ) -> tuple[dict[int, list[Game]], dict[tuple[str, int], float], dict[tuple[str, int, int], str]]:
    """The rule's inputs. ``routes=False`` drops the route share: the rule as it runs in season (the NFL
    publishes participation after the season), for the calibration and the precision numbers."""
    with conn.cursor() as cur:
        cur.execute(ROLE_SQL if routes else ROLE_SQL.replace("route_share::float8", "null::float8 as route_share"), (seasons,))
        names = [d.name for d in cur.description]
        by_season: dict[int, list[Game]] = defaultdict(list)
        for r in cur.fetchall():
            d = dict(zip(names, r, strict=True))
            by_season[int(d["season"])].append(Game(
                gsis_id=d["gsis_id"], season=int(d["season"]), week=int(d["week"]), team=d["team"], position=d["position"],
                player_name=d["player_name"], status=d["status"], snap_share=_none(d["snap_share"]), route_share=_none(d["route_share"]),
                targets=float(d["targets"] or 0), team_targets=_none(d["team_targets"]), carries=float(d["carries"] or 0),
                team_carries=_none(d["team_carries"]), team_margin=_none(d["team_margin"]), report_status=d["report_status"],
                roster_status=d["roster_status"], game_id=d["game_id"]))
        cur.execute(PREV_SQL, ([s - 1 for s in seasons],))
        prev = {(g, int(s) + 1): float(v) for g, s, v in cur.fetchall() if v is not None}
        cur.execute(NEXT_REPORT_SQL, (seasons, seasons))
        reports: dict[tuple[str, int, int], str] = {}
        for g, s, w, rep in cur.fetchall():
            if rep is None:
                continue
            key = (g, int(s), int(w))
            if reports.get(key) != "IR":
                reports[key] = rep
    return by_season, prev, reports


def role_alerts(conn: psycopg.Connection, seasons: list[int]) -> pd.DataFrame:
    """Every alert of ``seasons`` (pure rule over the loaded rows)."""
    by_season, prev, reports = load_games(conn, seasons)
    depth = load_depth(conn, seasons)
    run_at = datetime.now(UTC)
    frames = []
    for s in sorted(by_season):
        prev_level = {g: v for (g, ps), v in prev.items() if ps == s}
        nxt = {(g, w): r for (g, ss, w), r in reports.items() if ss == s}
        frames.append(alert_rows(alerts_for_season(by_season[s], prev_level, nxt, depth.get(s)), run_at))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=ALERT_COLUMNS)


# ------------------------------------------------------------------------------ persistence
DDL = {
    "ops.player_role_alerts": """create table if not exists ops.player_role_alerts (
        season integer, week integer, game_id text, gsis_id text, player_name text, position text, team text,
        direction text, games_held integer, since_week integer, confidence text, primary_metric text,
        metrics_changed text[], z double precision, snap_from double precision, snap_to double precision,
        route_from double precision, route_to double precision, target_from double precision, target_to double precision,
        carry_from double precision, carry_to double precision, trigger_kind text, trigger_gsis_id text, trigger_name text,
        trigger_status text, trigger_text text, change_text text, prior_games integer, kind text, cause_text text,
        expires_after_week integer, expiry_rule text, signals_version text, run_at timestamptz)""",
    "ops.player_scenarios": """create table if not exists ops.player_scenarios (
        run_at timestamptz, model_version text, signals_version text, league_id text, season integer, week integer,
        gsis_id text, position text, alert_week integer, since_week integer, games_held integer, confidence text, kind text,
        trigger_kind text, trigger_gsis_id text, trigger_name text, cause_text text, change_text text,
        base_points double precision, larger_points double precision, points_gain double precision,
        with_alert_points double precision, hold_rate double precision, backtest_n integer, backtest_hit_rate double precision,
        presentation text, presentation_note text, base_targets double precision, larger_targets double precision,
        base_receptions double precision, larger_receptions double precision, base_receiving_yards double precision,
        larger_receiving_yards double precision, base_carries double precision, larger_carries double precision,
        base_rushing_yards double precision, larger_rushing_yards double precision, base_attempts double precision,
        larger_attempts double precision, base_passing_yards double precision, larger_passing_yards double precision,
        base_tds double precision, larger_tds double precision, base_line jsonb, larger_line jsonb, features_set jsonb,
        expires_after_week integer, expiry_rule text)""",
}
SCENARIO_COLUMNS = [
    "run_at", "model_version", "signals_version", "league_id", "season", "week", "gsis_id", "position", "alert_week",
    "since_week", "games_held", "confidence", "kind", "trigger_kind", "trigger_gsis_id", "trigger_name", "cause_text",
    "change_text", "base_points", "larger_points", "points_gain", "with_alert_points", "hold_rate", "backtest_n",
    "backtest_hit_rate", "presentation", "presentation_note", "base_targets", "larger_targets", "base_receptions",
    "larger_receptions", "base_receiving_yards", "larger_receiving_yards", "base_carries", "larger_carries",
    "base_rushing_yards", "larger_rushing_yards", "base_attempts", "larger_attempts", "base_passing_yards",
    "larger_passing_yards", "base_tds", "larger_tds", "base_line", "larger_line", "features_set", "expires_after_week",
    "expiry_rule",
]


def _write(conn: psycopg.Connection, table: str, df: pd.DataFrame, columns: list[str], where: str, params: tuple) -> None:
    import json

    with conn.cursor() as cur:
        cur.execute(DDL[table])
        cur.execute(f"delete from {table} where {where}", params)
        with cur.copy(f"copy {table} ({', '.join(columns)}) from stdin") as cp:
            for r in df[columns].itertuples(index=False, name=None):
                cp.write_row([None if (isinstance(v, float) and math.isnan(v)) else (json.dumps(v) if isinstance(v, dict) else v) for v in r])
    conn.commit()


def write_alerts(conn: psycopg.Connection, alerts: pd.DataFrame, seasons: list[int]) -> None:
    """Replace ``seasons``' rows of ops.player_role_alerts (sorted: a rerun writes the same rows in the same order)."""
    df = alerts.sort_values(["season", "week", "gsis_id"]).reset_index(drop=True)
    _write(conn, "ops.player_role_alerts", df, ALERT_COLUMNS, "season = any(%s)", (seasons,))


# ------------------------------------------------------------------------------ scenario upside (R-12)
SCENARIO_POSITIONS = ("QB", "RB", "WR", "TE")
SCENARIO_WEEKS = EXPIRY_WEEKS   # the scenario covers the three weeks after the alert, then lapses (re-read every night)
# his last-3-games inputs moved to the level of the games since the change (projections.FEATURES names)
OPPORTUNITY_L3 = ("snap_pct_l3", "target_share_l3", "carry_share_l3", "air_yards_share_l3", "first_read_share_l3",
                  "targets_pg_l3", "carries_pg_l3", "attempts_pg_l3", "red_zone_targets_pg_l3", "red_zone_carries_pg_l3", "xppg_l3")
RECEIVING_L3 = ("receptions_pg_l3", "receiving_yards_pg_l3", "receiving_tds_pg_l3")                # scale with targets
RUSHING_L3 = ("rushing_yards_pg_l3", "rushing_tds_pg_l3")                                          # scale with carries
PASSING_L3 = ("passing_yards_pg_l3", "passing_tds_pg_l3", "passing_interceptions_pg_l3")           # scale with attempts
VOLUME_OUTCOMES = (("targets_pg_l3", RECEIVING_L3), ("carries_pg_l3", RUSHING_L3), ("attempts_pg_l3", PASSING_L3))
CAP_QUANTILE = 0.90       # a moved input stops at the position's 90th percentile (or at his own level when that is higher)

# Calibration (`league-lab signals-backtest --seasons 2023-2025`, 2026-09-30, rule ra1.1 run as it runs in season: no
# routes): every bigger-role alert at QB-TE of 2023-2025 whose next game exists (an absence alert whose teammate played
# that game is dropped: it had lapsed), the as-of row for his next game re-priced as the scenario with component models
# fitted on the seasons before, against his points per game over his next three games (reference scoring).
# ``HOLD_RATE``: share of the bigger-role alerts of 2016-2022 whose change was still there three games later, by games
# held (``alert_outcomes``) — the weight of the "with the alert" line. ``BACKTEST``: games held -> (alerts whose
# scenario moved the projection, share of them whose next three games landed nearer the larger role than the
# projection, the same for the "with the alert" line, mean miss of the projection, of the larger role, of the "with
# the alert" line). Neither beat the projection more often than not (45.6% / 47.4% nearer at one / two games held;
# the mean miss moved by under 0.04 points), so SCENARIO_SHIP is False: the pages show the larger role as a "what if"
# with its hit rate, never a probability. (On average those players did outscore the projection by about the
# scenario's gap: +1.1 vs +1.0 points per game at one game held — the gap is the right size on average, but single
# outcomes are too noisy for the scenario to be the nearer number; docs/METRICS.md § Scenario upside.)
HOLD_RATE: dict[int, float] = {1: 0.695, 2: 0.764, 3: 0.814}
BACKTEST: dict[int, tuple[int, float, float, float, float, float]] = {
    1: (285, 0.456, 0.470, 3.341, 3.370, 3.312),
    2: (266, 0.474, 0.481, 3.303, 3.293, 3.286),
    3: (18, 0.722, 0.722, 2.696, 2.526, 2.558),
}
BACKTEST_SEASONS = "2023-2025"
SCENARIO_SHIP = False

WINDOW_SQL = """
select gsis_id, season, week, snap_share::float8, targets::float8, team_targets::float8, carries::float8, team_carries::float8,
       attempts::float8, receiving_air_yards::float8, team_air_yards::float8, first_read_targets::float8,
       team_first_read_targets::float8, red_zone_targets::float8, red_zone_carries::float8, points_expected::float8
from intermediate.int_player_game_role where season = %s and gsis_id = any(%s) and status = 'played'"""


def window_inputs(games: pd.DataFrame) -> dict[str, float]:
    """The opportunity inputs over the games since the change (the same definitions as the as-of
    features: mean snap share, shares as sums over sums, per-game counts)."""
    g = games
    out: dict[str, float] = {}

    def ratio(num: str, den: str) -> float | None:
        d = g[den].sum(skipna=True)
        return float(g[num].sum(skipna=True) / d) if pd.notna(d) and d > 0 else None
    if g["snap_share"].notna().all():
        out["snap_pct_l3"] = float(g["snap_share"].mean())
    for k, (n, d) in {"target_share_l3": ("targets", "team_targets"), "carry_share_l3": ("carries", "team_carries"),
                      "air_yards_share_l3": ("receiving_air_yards", "team_air_yards"),
                      "first_read_share_l3": ("first_read_targets", "team_first_read_targets")}.items():
        v = ratio(n, d) if g[d].notna().all() else None
        if v is not None:
            out[k] = v
    for k, c in {"targets_pg_l3": "targets", "carries_pg_l3": "carries", "attempts_pg_l3": "attempts",
                 "red_zone_targets_pg_l3": "red_zone_targets", "red_zone_carries_pg_l3": "red_zone_carries"}.items():
        if c in g:
            out[k] = float(g[c].mean())
    if g["points_expected"].notna().all():
        out["xppg_l3"] = float(g["points_expected"].mean())
    # rounded as mart_player_week_features rounds them (shares 4 decimals, per-game rates 3), so an input
    # that did not move stays byte-identical and the scenario equals the base when nothing changed
    return {k: round(v, 4 if k.endswith("share_l3") or k == "snap_pct_l3" else 3) for k, v in out.items()}


def input_caps(train: pd.DataFrame, position: str) -> dict[str, float]:
    """The position's 90th percentile of each opportunity input over its training player-weeks (played)."""
    d = train[(train["position"] == position) & train["played"]]
    return {f: float(d[f].quantile(CAP_QUANTILE)) for f in OPPORTUNITY_L3 if f in d and d[f].notna().any()}


def larger_role_row(base: pd.Series, win: dict[str, float], ref_scoring: dict[str, float],
                    caps: dict[str, float] | None = None) -> tuple[pd.Series, dict[str, list]]:
    """One feature row with his last-3 inputs at the window's level (see the module docstring), each
    capped at the position's 90th percentile unless his own level is already above it.
    Returns the new row and {feature: [base, scenario]} for the features that moved."""
    from .projections import ALL_COMPONENTS
    from .scoring import compute_points

    row = base.copy()
    caps = caps or {}
    for f in OPPORTUNITY_L3:
        if f in win:
            v = float(win[f])
            if f in caps:
                own = float(base[f]) if _is_num(base.get(f)) else -math.inf
                v = min(v, max(caps[f], own))
            row[f] = v
    # outcomes follow the volume at his own last-3 efficiency (a larger role, not better hands)
    for vol, feats in VOLUME_OUTCOMES:
        old, new = base.get(vol), row.get(vol)
        if not (_is_num(old) and _is_num(new)):
            continue
        std_vol = base.get(vol.replace("_l3", "_std"))
        for f in feats:
            if f not in base.index:
                continue
            if old and old > 0:
                row[f] = float(base[f]) * float(new) / float(old) if _is_num(base[f]) else base[f]
            elif _is_num(std_vol) and std_vol > 0 and _is_num(base.get(f.replace("_l3", "_std"))):
                row[f] = float(base[f.replace("_l3", "_std")]) / float(std_vol) * float(new)    # season rate per target / carry / attempt
    # points per game, last 3: moved by the priced change of the last-3 line (reference scoring)

    def line(r: pd.Series) -> dict[str, float]:
        return {c: float(r[f"{c}_pg_l3"]) if _is_num(r.get(f"{c}_pg_l3")) else 0.0 for c in ALL_COMPONENTS}
    if _is_num(base.get("ppg_l3")):
        row["ppg_l3"] = float(base["ppg_l3"]) + compute_points(line(row), ref_scoring) - compute_points(line(base), ref_scoring)
    moved = {}
    for f in (*OPPORTUNITY_L3, *RECEIVING_L3, *RUSHING_L3, *PASSING_L3, "ppg_l3"):
        a, b = base.get(f), row.get(f)
        if _is_num(b) and (not _is_num(a) or float(a) != float(b)):
            moved[f] = [None if not _is_num(a) else round(float(a), 4), round(float(b), 4)]
    return row, moved


def with_alert(base: float, larger: float, games_held: int) -> float:
    """The probability-weighted line: the projection plus the historical hold rate (``HOLD_RATE``) of the gap."""
    return base + HOLD_RATE.get(int(games_held), 0.0) * (larger - base)


def component_models(train: pd.DataFrame, position: str) -> dict[str, object]:
    """The position's component models exactly as ``projections.fit_position`` fits them (same rows, same order,
    same seed: deterministic, so the base reproduces the stored projection)."""
    from .projections import COMPONENTS, FEATURES_BY_POSITION, _fit_components, _matrix

    d = train[(train["position"] == position) & train["played"] & ~train["no_history"]]
    d = d.dropna(subset=[f"out_{c}" for c in COMPONENTS[position]]).reset_index(drop=True)
    return _fit_components(_matrix(d, FEATURES_BY_POSITION[position]), d, position)   # v3: the position's inputs


def predict_lines(models: dict[str, object], rows: pd.DataFrame, ref_rows: pd.DataFrame, position: str) -> pd.DataFrame:
    """The component predictions for ``rows``. ``ref_rows`` = every row ``projections.predict_position`` predicts
    with them (the position's rows of the season): a feature that is unknown for ALL of those rows is 0 there
    (``projections._binnable``), so it must be 0 here too — not decided on this handful of rows."""
    from .projections import ALL_COMPONENTS, FEATURES_BY_POSITION

    feats = FEATURES_BY_POSITION[position]                      # v3: the inputs component_models fitted on
    x = np.array(rows[feats].to_numpy(dtype=float), dtype=float, copy=True)
    x[:, ref_rows[feats].isna().all(axis=0).to_numpy()] = 0.0
    return pd.DataFrame({f"proj_{c}": (np.clip(models[c].predict(x), 0, None) if c in models else 0.0) for c in ALL_COMPONENTS})


@dataclass
class ScenarioRun:
    alerts: int = 0
    live_up: int = 0
    scenarios: int = 0
    lapsed: int = 0
    base_max_diff: float = 0.0
    base_checked: int = 0
    seconds: float = 0.0


def live_alerts(alerts: pd.DataFrame, season: int, last_played: dict[str, int]) -> pd.DataFrame:
    """The season's alerts that are still news: the alert game is his team's latest game."""
    a = alerts[alerts["season"] == season].copy()
    if a.empty:
        return a
    a["team_last"] = a["team"].map(last_played)
    return a[a["week"] == a["team_last"]].drop(columns="team_last")


def presentation(games_held: int) -> tuple[str, str]:
    """(label, note) the pages use: 'with the alert' when the calibrated line beat the projection on the backtest,
    else 'what if', with the hit rate of the line shown (never a bare probability)."""
    bt = BACKTEST.get(int(games_held))
    label = "with the alert" if SCENARIO_SHIP else "what if"
    if not bt or not bt[0]:
        return "what if", "not tested on past seasons yet"
    n, hit = bt[0], (bt[2] if SCENARIO_SHIP else bt[1])
    line = "this line" if SCENARIO_SHIP else "this what-if"
    return label, (f"tested on {BACKTEST_SEASONS}: after {n} alerts like this, the next three games landed nearer {line} "
                   f"than the projection {100 * hit:.0f}% of the time")


def scenarios(conn: psycopg.Connection, season: int, train: pd.DataFrame, target: pd.DataFrame, pred: pd.DataFrame,
              scorings: dict[str, tuple[str, dict[str, float]]], alerts: pd.DataFrame, run: ScenarioRun,
              base_tol: float = 1e-6) -> pd.DataFrame:
    """Base vs larger-role for every QB / RB / WR / TE with a live up alert, over the weeks the scenario covers."""
    from .projections import ALL_COMPONENTS, MODEL_VERSION, price

    with conn.cursor() as cur:
        cur.execute("select team, max(week) from intermediate.int_player_game_role where season = %s group by 1", (season,))
        last_played = {t: int(w) for t, w in cur.fetchall()}
        cur.execute("select min(week) from analytics.dim_game where season = %s and season_type = 'REG' and kickoff_at > now()", (season,))
        first_open = cur.fetchone()[0]
    live = live_alerts(alerts, season, last_played)
    up = live[(live["direction"] == "up") & live["position"].isin(SCENARIO_POSITIONS)]
    run.live_up = len(up)
    if up.empty or first_open is None:
        return pd.DataFrame(columns=SCENARIO_COLUMNS)
    first_open = int(first_open)
    tgt = target.set_index(["gsis_id", "week"])
    # the trigger ends when the teammate is expected back: active on his NFL roster and not left out this week
    # ---- IS-2: "left out" is the one definition's (availability_gate.sits over Sleeper's directory copy and the stored
    # record, league_status.blocks) — was the mart's injury_status (nflverse's newest report row: midweek, last week's)
    with conn.cursor() as cur:
        cur.execute("""select gsis_id, max(roster_status) from analytics.mart_player_availability
                       where gsis_id = any(%s) group by 1""", (sorted(up["trigger_gsis_id"].dropna().unique().tolist()),))
        status_now = {g: r for g, r in cur.fetchall()}
    gate = LS.blocks(LS.conn_query(conn), season, first_open)
    keep = []
    for r in up.itertuples():
        if r.kind == "absence_beneficiary" and isinstance(r.trigger_gsis_id, str) and r.trigger_status == "out_injured":
            roster = status_now.get(r.trigger_gsis_id)
            if roster == "ACT" and not LS.sits(gate.get(r.trigger_gsis_id)):    # ---- end IS-2
                run.lapsed += 1
                continue                                   # the teammate is expected back: the scenario has lapsed
        keep.append(r)
    if not keep:
        return pd.DataFrame(columns=SCENARIO_COLUMNS)
    up = pd.DataFrame(keep).drop(columns="Index", errors="ignore")
    with conn.cursor() as cur:
        cur.execute(WINDOW_SQL, (season, sorted(up["gsis_id"].unique().tolist())))
        wg = pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])
    ref_scoring = next(iter(scorings.values()))[1]
    caps = {pos: input_caps(train, pos) for pos in SCENARIO_POSITIONS}
    rows, meta = [], []
    for a in up.itertuples():
        g = wg[(wg["gsis_id"] == a.gsis_id) & (wg["week"] >= a.since_week) & (wg["week"] <= a.week)]
        win = window_inputs(g)
        last = int(a.week) + SCENARIO_WEEKS
        for w in range(first_open, last + 1):
            if (a.gsis_id, w) not in tgt.index:
                continue                                   # a bye, or no projection row
            base = tgt.loc[(a.gsis_id, w)]
            new, moved = larger_role_row(base, win, ref_scoring, caps[a.position])
            rows.append(new.rename(None))
            meta.append({"gsis_id": a.gsis_id, "week": w, "position": a.position, "alert": a, "moved": moved, "expires": last})
    if not rows:
        return pd.DataFrame(columns=SCENARIO_COLUMNS)
    scen = pd.DataFrame(rows).reset_index(drop=True)
    base_rows = pd.DataFrame([tgt.loc[(m["gsis_id"], m["week"])].rename(None) for m in meta]).reset_index(drop=True)
    scen["week"] = base_rows["week"] = [float(m["week"]) for m in meta]   # the index level: back as the feature (float)
    out = []
    for pos in sorted({m["position"] for m in meta}):
        idx = [i for i, m in enumerate(meta) if m["position"] == pos]
        models = component_models(train, pos)             # = projections.fit_position's component models (same rows, same seed)
        ref = target[target["position"] == pos]
        comp_b = predict_lines(models, base_rows.iloc[idx], ref, pos)
        comp_s = predict_lines(models, scen.iloc[idx], ref, pos)
        # ---- M6 (Wave I-H): a cold start's stored line is the model's line x k (calibration.blend_lines): the base is
        # the stored line and the larger role moves by the same k, so the base still equals the stored projection
        from .calibration import rescale_to_stored
        comp_b, comp_s = rescale_to_stored(comp_b, comp_s, [(meta[i]["gsis_id"], int(meta[i]["week"])) for i in idx], pred)
        # ---- /M6
        for league_id, (_, scoring) in scorings.items():
            # ---- M4 (Wave I-G): the position rides along, as in predict_position — expected-value pricing reads the
            # position's curves (without it the pooled ones: the base missed the stored projection by 0.04 under
            # LEAGUE_LAB_EV_PRICING=1 and the nightly's scenarios failed, so the flip would have failed the marts' test)
            pb = price(comp_b, scoring, "proj_", position=pos).to_numpy()
            ps = price(comp_s, scoring, "proj_", position=pos).to_numpy()
            for j, i in enumerate(idx):
                out.append({"league_id": league_id, "i": i, "base_points": float(pb[j]), "larger_points": float(ps[j]),
                            **{f"b_{c}": float(comp_b[f"proj_{c}"].iloc[j]) for c in ALL_COMPONENTS},
                            **{f"s_{c}": float(comp_s[f"proj_{c}"].iloc[j]) for c in ALL_COMPONENTS}})
    res = pd.DataFrame(out)
    # the refitted models must reproduce the stored projection exactly (they are the production fit)
    stored = pred[pred["position"].isin(SCENARIO_POSITIONS)].set_index(["league_id", "gsis_id", "week"])["proj_points"]
    keys = [(r.league_id, meta[r.i]["gsis_id"], meta[r.i]["week"]) for r in res.itertuples()]
    diffs = [abs(float(stored.loc[k]) - b) for k, b in zip(keys, res["base_points"], strict=True) if k in stored.index]
    run.base_max_diff = max(diffs, default=0.0)
    run.base_checked = len(diffs)
    if run.base_max_diff > base_tol:
        raise RuntimeError(f"scenario base differs from the stored projection by {run.base_max_diff:.6f}: models not reproduced")
    run_at = datetime.now(UTC)
    rows_out = []
    for r in res.itertuples():
        m = meta[r.i]
        a = m["alert"]
        who = a.trigger_name if isinstance(a.trigger_name, str) else None
        rule = (f"lapses when {who} returns, and after week {m['expires']} at the latest"
                if a.kind == "absence_beneficiary" and who and a.trigger_status == "out_injured"
                else f"lapses after week {m['expires']} (by then the projection has caught up if the role holds)")
        b_tds = r.b_receiving_tds + r.b_rushing_tds + r.b_passing_tds
        s_tds = r.s_receiving_tds + r.s_rushing_tds + r.s_passing_tds
        k = int(a.games_held)
        bt = BACKTEST.get(k)
        label, note = presentation(k)
        rows_out.append({
            "run_at": run_at, "model_version": MODEL_VERSION, "signals_version": SIGNALS_VERSION, "league_id": r.league_id,
            "season": season, "week": m["week"], "gsis_id": m["gsis_id"], "position": m["position"], "alert_week": int(a.week),
            "since_week": int(a.since_week), "games_held": k, "confidence": a.confidence, "kind": a.kind,
            "trigger_kind": a.trigger_kind, "trigger_gsis_id": a.trigger_gsis_id if isinstance(a.trigger_gsis_id, str) else None,
            "trigger_name": who, "cause_text": a.cause_text, "change_text": a.change_text,
            "base_points": round(r.base_points, 2), "larger_points": round(r.larger_points, 2),
            "points_gain": round(r.larger_points - r.base_points, 2),
            "with_alert_points": round(with_alert(r.base_points, r.larger_points, k), 2),
            "hold_rate": HOLD_RATE.get(k), "backtest_n": bt[0] if bt else None,
            "backtest_hit_rate": (bt[2] if SCENARIO_SHIP else bt[1]) if bt else None,
            "presentation": label, "presentation_note": note,
            "base_targets": round(r.b_targets, 3), "larger_targets": round(r.s_targets, 3),
            "base_receptions": round(r.b_receptions, 3), "larger_receptions": round(r.s_receptions, 3),
            "base_receiving_yards": round(r.b_receiving_yards, 3), "larger_receiving_yards": round(r.s_receiving_yards, 3),
            "base_carries": round(r.b_carries, 3), "larger_carries": round(r.s_carries, 3),
            "base_rushing_yards": round(r.b_rushing_yards, 3), "larger_rushing_yards": round(r.s_rushing_yards, 3),
            "base_attempts": round(r.b_attempts, 3), "larger_attempts": round(r.s_attempts, 3),
            "base_passing_yards": round(r.b_passing_yards, 3), "larger_passing_yards": round(r.s_passing_yards, 3),
            "base_tds": round(b_tds, 3), "larger_tds": round(s_tds, 3),
            "base_line": {c: round(getattr(r, f"b_{c}"), 4) for c in ALL_COMPONENTS},
            "larger_line": {c: round(getattr(r, f"s_{c}"), 4) for c in ALL_COMPONENTS},
            "features_set": m["moved"], "expires_after_week": m["expires"], "expiry_rule": rule,
        })
    run.scenarios = len(rows_out)
    return pd.DataFrame(rows_out, columns=SCENARIO_COLUMNS).sort_values(["league_id", "week", "gsis_id"]).reset_index(drop=True)


# ------------------------------------------------------------------------------ calibration (R-12: before a probability is shown)
def alert_outcomes(alerts: pd.DataFrame, games: list[Game], horizon: int = 3) -> pd.Series:
    """Was each alert still real ``horizon`` games later? 'real' = the mean of its primary share over his next
    ``horizon`` games (skipping games he missed injured; a bigger role counts played games only) stayed past
    the midpoint of before -> after; 'false' = it did not; 'expired' = an injured teammate's absence ended
    before his next game (the alert lapsed as designed); 'unresolved' = no later game. For an absence alert
    only the games the teammate still missed count."""
    by_player: dict[str, list[Game]] = defaultdict(list)
    missing: set[tuple[str, int]] = set()
    for g in games:
        by_player[g.gsis_id].append(g)
        if g.absent:
            missing.add((g.gsis_id, g.week))
    present = {(g.gsis_id, g.week) for g in games}
    for v in by_player.values():
        v.sort(key=lambda g: g.week)
    out = []
    for a in alerts.itertuples():
        fut = [g for g in by_player.get(a.gsis_id, []) if g.week > a.week and g.status != "out_injured"]
        if a.kind == "absence_beneficiary" and a.trigger_status == "out_injured" and isinstance(a.trigger_gsis_id, str):
            still = []
            for g in fut:
                gone = (a.trigger_gsis_id, g.week) in missing or (a.trigger_gsis_id, g.week) not in present
                if not gone:
                    break
                still.append(g)
            if fut and not still:
                out.append("expired")
                continue
            fut = still
        fut = fut[:horizon]
        if a.direction == "up":
            fut = [g for g in fut if g.status == "played"]
        vals = [g.share(a.primary_metric) for g in fut]
        vals = [float(v) for v in vals if _is_num(v)]
        if not vals:
            out.append("unresolved")
            continue
        m = a.primary_metric.split("_")[0]
        before, after = getattr(a, f"{m}_from"), getattr(a, f"{m}_to")
        mid = before + (after - before) / 2
        lvl = sum(vals) / len(vals)
        out.append("real" if (lvl >= mid if a.direction == "up" else lvl <= mid) else "false")
    return pd.Series(out, index=alerts.index, dtype=object)


def precision_table(alerts: pd.DataFrame, outcomes: pd.Series, by: list[str]) -> pd.DataFrame:
    t = alerts.assign(res=outcomes).groupby(by)["res"].value_counts().unstack(fill_value=0)
    for c in ("real", "false", "expired", "unresolved"):
        if c not in t:
            t[c] = 0
    t["precision"] = (t["real"] / (t["real"] + t["false"]).replace(0, np.nan)).round(3)
    return t[["real", "false", "expired", "unresolved", "precision"]].reset_index()


def first_detections(alerts: pd.DataFrame) -> pd.Series:
    """True on the first row of each change (a change is re-reported at two and three games)."""
    chain = alerts["gsis_id"] + "|" + alerts["season"].astype(str) + "|" + alerts["since_week"].astype(str) + alerts["direction"]
    return alerts["week"] == alerts.groupby(chain)["week"].transform("min")


@dataclass
class Calibration:
    rows: pd.DataFrame            # one row per tested bigger-role alert: base / larger / with-alert vs the next three games
    summary: pd.DataFrame         # by games held (alerts whose scenario moved the projection)
    hold: dict[int, float]        # bigger-role hold rates of the seasons before the tested ones (the weights)
    precision: pd.DataFrame       # first detections of the tested seasons: real / false / expired / unresolved by season x direction
    precision_kind: pd.DataFrame  # the same by season x kind


def scenario_backtest(conn: psycopg.Connection, seasons: list[int]) -> Calibration:
    """Walk-forward test of the larger-role scenario (plan R-12): for every bigger-role alert of ``seasons`` at
    QB-TE (the rule as it runs in season: no routes), the as-of feature row for his next game, re-priced as
    the scenario with component models fitted on the seasons before, against his points per game over his
    next three games (reference scoring). Returns the rows (one per alert), the summary by games held, the hold
    rates used for the 'with the alert' line: bigger-role alerts of the seasons before the first tested one) and
    the precision of the tested seasons' first detections (``alert_outcomes``)."""
    from .projections import COMPONENTS, available_seasons, league_scorings, load_frame, price

    scorings = league_scorings(conn)
    ref_id, (_, ref_scoring) = next(iter(scorings.items()))
    avail = available_seasons(conn)
    frame = load_frame(conn, [s for s in avail if s <= max(seasons)])
    frame["actual_points"] = price(frame, ref_scoring, "out_")
    by_season, prev, reports = load_games(conn, sorted(set(avail) & set(range(min(avail), max(seasons) + 1))), routes=False)
    depth = load_depth(conn, list(by_season))
    alerts_by_season: dict[int, pd.DataFrame] = {}
    outcomes_by_season: dict[int, pd.Series] = {}
    run_at = datetime.now(UTC)
    for s, games in by_season.items():
        prev_level = {g: v for (g, ps), v in prev.items() if ps == s}
        nxt = {(g, w): r for (g, ss, w), r in reports.items() if ss == s}
        al = alert_rows(alerts_for_season(games, prev_level, nxt, depth.get(s)), run_at)
        alerts_by_season[s] = al
        outcomes_by_season[s] = alert_outcomes(al, games)
    hist = pd.concat([alerts_by_season[s].assign(res=outcomes_by_season[s]) for s in by_season if s < min(seasons)])
    hist = hist[hist["direction"] == "up"]
    hold = {}
    for k in (1, 2, 3):
        h = hist[hist["games_held"] == k]["res"]
        n = int(h.isin(["real", "false"]).sum())
        hold[k] = round(float((h == "real").sum() / n), 3) if n else 0.0
    rows = []
    for s in seasons:
        al = alerts_by_season.get(s)
        if al is None or al.empty:
            continue
        up = al[(al["direction"] == "up") & al["position"].isin(SCENARIO_POSITIONS)].copy()
        # an absence alert whose teammate is back for the next game has lapsed: production shows no scenario
        role = {(g.gsis_id, g.week): g for g in by_season[s]}
        train = frame[frame["season"] < s]
        test = frame[frame["season"] == s].sort_values(["gsis_id", "week"])
        with conn.cursor() as cur:
            cur.execute(WINDOW_SQL, (s, sorted(up["gsis_id"].unique().tolist())))
            wg = pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])
        by_gid = {g: d for g, d in test.groupby("gsis_id")}
        items = []
        for a in up.itertuples():
            d = by_gid.get(a.gsis_id)
            if d is None:
                continue
            nxt_rows = d[d["week"] > a.week]
            if nxt_rows.empty:
                continue
            base = nxt_rows.iloc[0]
            if a.kind == "absence_beneficiary" and a.trigger_status == "out_injured" and isinstance(a.trigger_gsis_id, str):
                tm = role.get((a.trigger_gsis_id, int(base["week"])))
                if tm is not None and tm.status == "played" and not tm.absent:
                    continue                                        # the teammate played the next game: lapsed
            fut = nxt_rows[nxt_rows["played"]].head(SCENARIO_WEEKS)
            if fut.empty:
                continue
            g = wg[(wg["gsis_id"] == a.gsis_id) & (wg["week"] >= a.since_week) & (wg["week"] <= a.week)]
            items.append((a, base, window_inputs(g), float(fut["actual_points"].mean()), len(fut)))
        for pos in SCENARIO_POSITIONS:
            its = [it for it in items if it[0].position == pos]
            if not its:
                continue
            caps = input_caps(train, pos)
            models = component_models(train, pos)
            b_rows = pd.DataFrame([it[1] for it in its]).reset_index(drop=True)
            s_rows = pd.DataFrame([larger_role_row(it[1], it[2], ref_scoring, caps)[0] for it in its]).reset_index(drop=True)
            ref = test[test["position"] == pos]
            pb = price(predict_lines(models, b_rows, ref, pos), ref_scoring, "proj_").to_numpy()
            ps = price(predict_lines(models, s_rows, ref, pos), ref_scoring, "proj_").to_numpy()
            for j, (a, _, _, actual, n_fut) in enumerate(its):
                rows.append({"season": s, "week": int(a.week), "gsis_id": a.gsis_id, "player_name": a.player_name, "position": pos,
                             "games_held": int(a.games_held), "kind": a.kind, "base": float(pb[j]), "larger": float(ps[j]),
                             "with_alert": float(pb[j]) + hold[int(a.games_held)] * (float(ps[j]) - float(pb[j])),
                             "actual_ppg": actual, "games_after": n_fut, "components": len(COMPONENTS[pos])})
            log.info("scenario backtest %s %s: %s alerts", s, pos, len(its))
    tested = pd.concat([alerts_by_season[s].assign(res=outcomes_by_season[s]) for s in seasons if s in alerts_by_season])
    first = tested[first_detections(tested)]
    prec = precision_table(first, first["res"], ["season", "direction"])
    prec_kind = precision_table(first, first["res"], ["season", "kind"])
    bt = pd.DataFrame(rows)
    if bt.empty:
        return Calibration(bt, pd.DataFrame(), hold, prec, prec_kind)
    bt["err_base"] = (bt["actual_ppg"] - bt["base"]).abs()
    bt["err_larger"] = (bt["actual_ppg"] - bt["larger"]).abs()
    bt["err_with"] = (bt["actual_ppg"] - bt["with_alert"]).abs()
    bt["gap"], bt["resid"] = bt["larger"] - bt["base"], bt["actual_ppg"] - bt["base"]
    bt["moved"] = bt["gap"].abs() > 0.05
    bt["larger_nearer"] = bt["err_larger"] < bt["err_base"]
    bt["with_nearer"] = bt["err_with"] < bt["err_base"]
    summary = (bt[bt["moved"]].groupby("games_held")
               .agg(n=("gsis_id", "size"), hit_larger=("larger_nearer", "mean"), hit_with=("with_nearer", "mean"),
                    mae_base=("err_base", "mean"), mae_larger=("err_larger", "mean"), mae_with=("err_with", "mean"),
                    mean_gap=("gap", "mean"), mean_actual_minus_base=("resid", "mean"))
               .round(3).reset_index())
    return Calibration(bt, summary, hold, prec, prec_kind)


# ------------------------------------------------------------------------------ entry points
def refresh_alerts(conn: psycopg.Connection, season: int) -> pd.DataFrame:
    """Recompute the alerts of ``season`` (and of every earlier season when the table has none of them:
    a fresh database), write them, and return ``season``'s rows."""
    with conn.cursor() as cur:
        cur.execute(DDL["ops.player_role_alerts"])
        cur.execute("select distinct season from ops.player_role_alerts where signals_version = %s", (SIGNALS_VERSION,))
        have = {int(r[0]) for r in cur.fetchall()}      # a season written by another rule version is recomputed
        cur.execute("select distinct season from intermediate.int_player_game_role order by 1")
        avail = [int(r[0]) for r in cur.fetchall()]
    conn.commit()
    todo = sorted({season} | {s for s in avail if s < season and s not in have})
    alerts = role_alerts(conn, todo)
    write_alerts(conn, alerts, todo)
    log.info("role alerts written: %s rows for seasons %s (%s this season: %s up, %s down)", len(alerts), todo,
             int((alerts["season"] == season).sum()), int(((alerts["season"] == season) & (alerts["direction"] == "up")).sum()),
             int(((alerts["season"] == season) & (alerts["direction"] == "down")).sum()))
    return alerts[alerts["season"] == season]


def signals_after_project(conn: psycopg.Connection, season: int, train: pd.DataFrame, target: pd.DataFrame, pred: pd.DataFrame,
                          scorings: dict[str, tuple[str, dict[str, float]]], base_tol: float = 1e-6) -> ScenarioRun | None:
    """Called once in ``projections.project`` after the projections are written (plan R-10 / R-12):
    the role alerts, then the scenarios on the same component models. Logged, never fatal: the
    previous rows are kept."""
    run = ScenarioRun()
    t0 = time.perf_counter()
    try:
        alerts = refresh_alerts(conn, season)
        run.alerts = len(alerts)
        # B5: a week whose first game has kicked off keeps the board it was published with (ops.projections,
        # frozen_source = 'kickoff'); a refit cannot reproduce that base, so no scenario is written for it (the
        # first `project` after week 4's freeze wrote 24 week-4 rows off the refit and failed the mart's
        # scenario_base_is_the_projection test on the Mac, 2026-10-02)
        with conn.cursor() as cur:
            cur.execute("select distinct week from ops.projections where season = %s and frozen_source = 'kickoff'", (season,))
            frozen_weeks = sorted(int(r[0]) for r in cur.fetchall())
        if frozen_weeks:
            target = target[~target["week"].isin(frozen_weeks)]
            pred = pred[~pred["week"].isin(frozen_weeks)]
            log.info("scenarios skip the frozen weeks %s (the board is locked at kickoff)", frozen_weeks)
        sc = scenarios(conn, season, train, target, pred, scorings, alerts, run, base_tol)
        _write(conn, "ops.player_scenarios", sc, SCENARIO_COLUMNS, "season = %s", (season,))
        run.seconds = time.perf_counter() - t0
        log.info("scenarios written: %s rows (%s live up alerts at QB-TE, %s lapsed: teammate back) in %.1f s; "
                 "base = stored projection to %.2e on %s rows", run.scenarios, run.live_up, run.lapsed, run.seconds,
                 run.base_max_diff, run.base_checked)
        return run
    except Exception:
        conn.rollback()
        log.exception("role alerts / scenarios failed (projections were written); the next `league-lab project` retries")
        return None


def run_signals(season: int | None = None) -> ScenarioRun | None:
    """Alerts + scenarios on their own (refits the QB-TE component models): `league-lab signals`."""
    from .config import get_settings
    from .projections import available_seasons, league_scorings, load_frame

    with psycopg.connect(get_settings().pipeline_dsn(), autocommit=False) as conn:
        seasons = available_seasons(conn)
        season = season or max(seasons)
        train_seasons = [s for s in seasons if s < season]
        frame = load_frame(conn, [*train_seasons, season])
        target = frame[frame["season"] == season]
        with conn.cursor() as cur:
            # ---- M6 (Wave I-H): the stored stat line rides along (a cold start's is the model's x k: rescale_to_stored)
            from .projections import ALL_COMPONENTS
            comps = [f"proj_{c}" for c in ALL_COMPONENTS]
            cur.execute(f"""select league_id, gsis_id, week, position, proj_points, {', '.join(comps)} from ops.projections
                           where season = %s and position = any(%s)""", (season, list(SCENARIO_POSITIONS)))
            pred = pd.DataFrame(cur.fetchall(), columns=["league_id", "gsis_id", "week", "position", "proj_points", *comps])
            pred[comps] = pred[comps].astype(float)
            # ---- /M6
        pred["proj_points"] = pred["proj_points"].astype(float)
        # ops.projections keeps two decimals: the refit reproduces it to the rounding (project() checks to 1e-6)
        return signals_after_project(conn, season, frame[frame["season"] < season], target, pred, league_scorings(conn), 0.0051)
