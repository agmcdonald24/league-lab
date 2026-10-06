"""The role trend: a player's last two games against his games before them (Wave I-N IN-4's DFS measure; moved here in
Wave I-O, IO-4, so DFS and the Stats Explorer read ONE implementation).

Each measure is a share — target share, carry share, snap share, routes per dropback — taken as the **summed
numerator over the summed denominator** of the games in each part (never a mean of weekly shares):

* the recent part is his last ``ROLE_RECENT`` (2) games played, the part before is every earlier game he played in the
  frame, and nothing is said unless there are at least ``ROLE_MIN_BEFORE`` (2) games before;
* a part where any game lacks the measure (no numerator, no denominator, a zero denominator) is unknown — never 0;
* a part whose summed denominator is under ``ROLE_MIN_DEN`` per ``ROLE_RECENT`` games (20 team targets / carries,
  60 team snaps, 30 dropbacks with participation for two games) is too small a sample: unknown.

``shares(games)`` is the arithmetic for every player of a frame at once (vectorised: the Stats Explorer reads ~600
players per request); ``role_trend(games, position)`` is DFS's call on one player's games (the threshold and the words:
"role up" when at least one measure moved by its ``move`` or more and none the other way).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

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


def _arr(games: pd.DataFrame, col: str) -> np.ndarray:
    return pd.to_numeric(games[col], errors="coerce").to_numpy(dtype=float)


def _ratio(num: np.ndarray, den: np.ndarray, den_name: str) -> float | None:
    """One part's summed numerator / summed denominator: None when the part is empty, a game lacks the measure (or has
    a zero denominator), or the summed denominator is under the minimum for that many games."""
    n = len(num)
    if n == 0 or not (~np.isnan(num) & ~np.isnan(den) & (den > 0)).all():
        return None
    d = float(den.sum())
    if d < ROLE_MIN_DEN.get(den_name, 1.0) * n / ROLE_RECENT:
        return None
    return float(num.sum()) / d


def _parts(week: np.ndarray, cols: dict[str, tuple[np.ndarray, np.ndarray] | None]) -> dict:
    """One player's games (as arrays): his last ROLE_RECENT by week against the ones before, each measure's two parts."""
    order = np.argsort(week, kind="stable")
    n = len(order)
    k = min(ROLE_RECENT, n)
    rec, bef = order[n - k:], order[: n - k]
    out: dict = {"games_recent": k, "games_before": n - k}
    for name, xd in cols.items():
        if xd is None:
            out[f"{name}_recent"] = out[f"{name}_before"] = None
            continue
        x, d = xd
        den = ROLE_MEASURES[name]["den"]
        out[f"{name}_recent"] = _ratio(x[rec], d[rec], den)
        out[f"{name}_before"] = _ratio(x[bef], d[bef], den)
    return out


def _columns(games: pd.DataFrame) -> dict[str, tuple[np.ndarray, np.ndarray] | None]:
    return {name: ((_arr(games, m["num"]), _arr(games, m["den"])) if m["num"] in games and m["den"] in games else None)
            for name, m in ROLE_MEASURES.items()}


def shares(games: pd.DataFrame, key: str = "gsis_id") -> pd.DataFrame:
    """One row per ``key`` (the index): ``games_recent``, ``games_before`` and, per measure, ``<measure>_recent`` /
    ``<measure>_before`` (NaN = unknown, the rules in the module's docstring). ``games``: played games only, with
    ``week`` and the measures' columns (a missing column makes its measure unknown). Every column is read once; each
    player is a slice of the arrays (the Stats Explorer: ~600 players in a few tens of milliseconds)."""
    names = ["games_recent", "games_before"] + [f"{m}_{p}" for m in ROLE_MEASURES for p in ("recent", "before")]
    if games is None or games.empty:
        return pd.DataFrame(columns=names)
    g = games.sort_values(key, kind="mergesort")
    keys = g[key].to_numpy()
    week = _arr(g, "week")
    cols = _columns(g)
    cut = np.flatnonzero(keys[1:] != keys[:-1]) + 1
    bounds = zip(np.r_[0, cut], np.r_[cut, len(keys)], strict=True)
    rows, idx = [], []
    for a, b in bounds:
        sl = slice(int(a), int(b))
        rows.append(_parts(week[sl], {n: (None if xd is None else (xd[0][sl], xd[1][sl])) for n, xd in cols.items()}))
        idx.append(keys[a])
    return pd.DataFrame(rows, index=pd.Index(idx, name=key), columns=names).astype(float)


def role_trend(games: pd.DataFrame, position: str) -> dict | None:
    """``games``: one player's games this season BEFORE this week, played only (``week``, ``targets``, ``team_targets``,
    ``carries``, ``team_carries``, ``offense_snaps``, ``team_snaps``, ``routes``, ``team_dropbacks_with_participation``).
    His last ``ROLE_RECENT`` games against the ones before them (at least ``ROLE_MIN_BEFORE``): each measure as the
    summed numerator over the summed denominator; a measure moved when it changed by its ``move`` or more. "role up"
    when at least one moved up and none down, "role down" the other way, else None (nothing said; mixed or too small)."""
    if position not in ("RB", "WR", "TE") or games is None or games.empty:
        return None
    r = _parts(_arr(games, "week"), _columns(games))
    n_recent, n_before = int(r["games_recent"]), int(r["games_before"])
    if n_recent < ROLE_RECENT or n_before < ROLE_MIN_BEFORE:
        return None
    moved = []
    for name, m in ROLE_MEASURES.items():
        if position not in m["pos"]:
            continue
        a, b = r[f"{name}_recent"], r[f"{name}_before"]
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
            "words": (f"Role {'up' if up else 'down'} in his last two games (the {n_before} before in brackets): "
                      + ", ".join(parts) + "."), "measures": moved,
            "signal": "role" if "role" in signals else "routes", "games": [n_recent, n_before]}


def change_columns(games: pd.DataFrame, positions: pd.Series | None = None) -> pd.DataFrame:
    """The Stats Explorer's three columns per player (index ``gsis_id``): ``target_share_change``,
    ``carry_share_change``, ``snap_share_change`` (recent minus before, a share's difference: 0.05 = 5 points of share,
    signed, 4 places), their ``_recent`` / ``_before`` and the games in each part; NaN where the measure is unknown,
    the sample too small, or the measure does not apply to his position (``positions``: gsis_id -> position; carry share
    is a running back's measure, as on DFS)."""
    s = shares(games)
    cols = {}
    for name in ("target_share", "carry_share", "snap_share"):
        enough = (s["games_recent"] >= ROLE_RECENT) & (s["games_before"] >= ROLE_MIN_BEFORE)
        a, b = s[f"{name}_recent"].where(enough), s[f"{name}_before"].where(enough)
        if positions is not None:
            applies = pd.Series(positions).reindex(s.index).isin(ROLE_MEASURES[name]["pos"])
            a, b = a.where(applies), b.where(applies)
        cols[f"{name}_change"] = (a - b).round(4)
        cols[f"{name}_recent"] = a.round(4)
        cols[f"{name}_before"] = b.round(4)
    cols["role_games_recent"] = s["games_recent"]
    cols["role_games_before"] = s["games_before"]
    return pd.DataFrame(cols, index=s.index)
