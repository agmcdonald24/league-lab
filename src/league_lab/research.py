"""The research marts in any league's scoring (plan G1, Iteration 15, Wave G): pure helpers, no database.

The NFL research marts (`mart_player_season`, `mart_player_trends`, `mart_defense_vs_position`, `mart_player_recent_form`
…) carry fantasy points in ONE scoring, the reference league's (`fct_player_game.points_current_scoring`), so every
player and season compares on one scale. The app shows a league its own scoring. Two ways to get there:

* a **house league** (the nightly scores it): `fct_player_game_league` / `mart_league_player_season` already hold every
  NFL game priced in its current scoring (plan S-01a);
* **any other league**: the game's stat columns are priced on request with `scoring.compute_points` (the one
  definition of a Sleeper scoring; the position is passed, so a TE premium prices) — `price_games`.

For a house league the two agree to the cent (api/tests/test_research.py: every 2025 and 2026 game of both house
leagues). Everything a research screen derives from per-game points — a season's points per game, the last-3 /
prior windows of the trends, points allowed by a defense to a position — is then the same arithmetic over either
frame (`season_table`, `trend_windows`, `defense_allowed`), each a Python twin of its dbt model.

**Expected points** (`price_expected`). ffverse's expected stat line is in the published marts only for the seven
columns `mart_player_expected_points` carries (receptions, receiving / rushing / passing yards and TDs). A house
league's `fct_player_game_league.points_expected` prices the full line (interceptions, fumbles, 2-point tries too).
So a league's expected points = a house league's + this league's weights minus the house league's on the seven
columns we can see: exact when the two agree on every other expected-stat key (`expected_reference` picks such a
house league when there is one; the Test League and every half-PPR 4-pt league with −1 interceptions match the
reference league), an approximation otherwise (the hand-back measures it: dynasty from Scrubs).
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import ROUND_HALF_UP, Decimal

import numpy as np
import pandas as pd

from .scoring import _PY_EXPR, MAPPED_KEYS, SLEEPER_BONUS_MAP, SLEEPER_POSITION_MAP, compute_points

# the stat columns compute_points reads (fct_player_game has every one of them, long-TD counts included)
PRICE_COLUMNS: tuple[str, ...] = tuple(sorted(
    {c for cols in _PY_EXPR.values() for c in cols}
    | {v[0] for v in SLEEPER_BONUS_MAP.values()}
    | {v[0] for v in SLEEPER_POSITION_MAP.values()}
))

# ffverse's expected stat columns the published mart carries: stat column -> mart_player_expected_points column
EXPECTED_COLUMNS: dict[str, str] = {
    "receptions": "receptions_exp", "receiving_yards": "receiving_yards_exp", "receiving_tds": "receiving_tds_exp",
    "rushing_yards": "rushing_yards_exp", "rushing_tds": "rushing_tds_exp",
    "passing_yards": "passing_yards_exp", "passing_tds": "passing_tds_exp",
}
SKILL = ("QB", "RB", "WR", "TE")
# expected stats ffverse never sets (0 on all 11,874 rows of 2024–26: staging.stg_nflverse__ff_opportunity): a weight on
# them prices 0 expected points in any league, so it cannot make two leagues' expected points differ
NO_EXPECTED = {"special_teams_tds", "fumble_recovery_tds"}


def _cents(v) -> int | None:
    """A 2-decimal point value as integer cents (the marts' numeric arithmetic, without float drift)."""
    return None if v is None or pd.isna(v) else int(round(float(v) * 100))


def _div2(cents: int, n: int) -> float:
    """round(cents / 100 / n, 2) the way Postgres rounds numeric: half away from zero, exact."""
    q = (Decimal(int(cents)) / Decimal(100) / Decimal(int(n))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return float(q)


def _mean2(values) -> float | None:
    c = [x for x in (_cents(v) for v in values) if x is not None]
    return _div2(sum(c), len(c)) if c else None


def _cents_series(v: pd.Series) -> pd.Series:
    return (pd.to_numeric(v, errors="coerce") * 100).round().astype("Int64")


def _ratio2(cents: pd.Series, n: pd.Series) -> pd.Series:
    """round(cents / 100 / n, 2), half away from zero, in exact integer arithmetic (Postgres numeric's rounding);
    NULL where n is 0 or the sum is NULL. Index-aligned."""
    c, k = cents.astype("Int64"), n.reindex(cents.index).astype("Int64")
    ok = c.notna() & k.notna() & (k > 0)
    a, d = c[ok].astype("int64").to_numpy(), k[ok].astype("int64").to_numpy()
    q = (2 * np.abs(a) + d) // (2 * d) * np.sign(a)
    out = pd.Series(np.nan, index=cents.index, dtype=float)
    out[ok] = q / 100
    return out


def _w(scoring: Mapping[str, float], key: str) -> float:
    return round(float(scoring.get(key) or 0.0), 6)


def price_games(df: pd.DataFrame, scoring: Mapping[str, float]) -> pd.Series:
    """League points of every game row (`fct_player_game` columns): `compute_points(row, scoring)` with the row's
    position, bonuses included — what `fct_player_game_league.points` holds for a house league. A row without a
    stats row (`has_stat_row` false) is NULL, as in that table (it has no row for it)."""
    if df.empty:
        return pd.Series(dtype=float, index=df.index)
    cols = [c for c in PRICE_COLUMNS if c in df.columns]
    stats = df[cols].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    stats["position"] = df["position"].to_numpy() if "position" in df else None
    pts = pd.Series([compute_points(r, scoring) for r in stats.to_dict("records")], index=df.index, dtype=float)
    if "has_stat_row" in df:
        pts = pts.where(df["has_stat_row"].fillna(False).astype(bool))
    return pts


def unobserved_expected_keys(scoring: Mapping[str, float]) -> dict[str, float]:
    """The `stat` keys (expected points leave bonuses out) whose expected stat is NOT in the published mart, with
    their weights: interceptions, fumbles, 2-point tries, return TDs — what `price_expected` takes from the house league.
    Left out: kicking keys (expected points exist for QB–TE rows only) and the return / fumble-recovery TDs ffverse
    never projects (`NO_EXPECTED`)."""
    seen = set(EXPECTED_COLUMNS)
    out = {}
    for k, kind in MAPPED_KEYS.items():
        if kind != "stat":
            continue
        cols = set(_PY_EXPR[k])
        if cols <= seen or cols <= NO_EXPECTED or all(c.startswith(("fg_", "pat_")) for c in cols):
            continue
        w = _w(scoring, k)
        if w:
            out[k] = w
    return out


def expected_reference(scoring: Mapping[str, float], candidates: Mapping[str, Mapping[str, float]],
                       exclude: str | None = None) -> tuple[str | None, bool]:
    """(the house league whose expected points this league's are priced from, exact?): one whose weights on every
    unobserved expected key equal this league's (first by id) — then the price is exact — else the one with the
    smallest summed weight difference on those keys (an approximation, reported)."""
    mine = unobserved_expected_keys(scoring)
    best, best_d = None, None
    for lid in sorted(candidates):
        if lid == exclude:
            continue
        theirs = unobserved_expected_keys(candidates[lid])
        d = sum(abs(mine.get(k, 0.0) - theirs.get(k, 0.0)) for k in set(mine) | set(theirs))
        if best_d is None or d < best_d:
            best, best_d = lid, d
    return best, (best is not None and best_d == 0)


def price_expected(df: pd.DataFrame, scoring: Mapping[str, float], ref_scoring: Mapping[str, float]) -> pd.Series:
    """Expected points in `scoring` for rows carrying the seven `*_exp` columns and `ref_expected` (the reference
    house league's `points_expected`): ref + Σ (this league's weight − the reference's) × the expected stat, over the
    `stat` keys priced on those seven columns (compute_points' keys, no bonuses) and the position premiums — rounded once
    at the end, so two equal scorings (Sleeper stores float32: 0.04 is 0.03999999910593033) add exactly 0.
    NULL where the reference has none (no ffverse row)."""
    if df.empty:
        return pd.Series(dtype=float, index=df.index)
    obs = {stat: pd.to_numeric(df[col], errors="coerce").fillna(0.0).to_numpy(dtype=float) for stat, col in EXPECTED_COLUMNS.items()}
    delta = np.zeros(len(df))
    for k, kind in MAPPED_KEYS.items():
        cols = _PY_EXPR.get(k)
        if kind != "stat" or not cols or not set(cols) <= set(obs):
            continue
        dw = _w(scoring, k) - _w(ref_scoring, k)
        if dw:
            delta += dw * sum(obs[c] for c in cols)
    pos = df["position"].to_numpy()
    for k, (col, position, _) in SLEEPER_POSITION_MAP.items():
        dw = _w(scoring, k) - _w(ref_scoring, k)
        if dw and col in obs:
            delta += dw * obs[col] * (pos == position)
    base = pd.to_numeric(df["ref_expected"], errors="coerce")
    return (base + delta).round(2)


# ------------------------------------------------------------------------------ twins of the dbt models
def season_table(games: pd.DataFrame) -> pd.DataFrame:
    """`mart_league_player_season`'s arithmetic over one league's priced REG game rows (gsis_id, week, position,
    player_name?, played, points, points_expected, expected_known): games_played, points, ppg, points_per_game_l3/_l5,
    games_with_expected, points_expected, expected_per_game, diff_per_game, position_rank_points/_ppg (rank among the
    frame's players at the position — the whole NFL when the frame is the season)."""
    cols = ["gsis_id", "position", "games_played", "points", "ppg", "points_per_game_l3", "points_per_game_l5",
            "games_with_expected", "points_expected", "expected_per_game", "diff_per_game",
            "position_rank_points", "position_rank_ppg"]
    if games.empty:
        return pd.DataFrame(columns=cols)
    g = games[["gsis_id", "week", "position", "played", "points", "points_expected", "expected_known"]].copy()
    g["pc"] = _cents_series(g["points"])
    g["xc"] = _cents_series(g["points_expected"])
    g = g[g["pc"].notna()]          # the mart's rows: games with a stats row (fct_player_game_league has no other)
    g["played"] = g["played"].fillna(False).astype(bool)
    g["skill"] = g["position"].isin(SKILL)
    g["xs"] = g["skill"] & g["expected_known"].fillna(False).astype(bool)
    g["xsp"] = g["xs"] & g["played"]
    # position = mode() within group (order by position): the most frequent, ties to the first alphabetically
    cnt = g.dropna(subset=["position"]).groupby(["gsis_id", "position"]).size().reset_index(name="n")
    pos = cnt.sort_values(["gsis_id", "n", "position"], ascending=[True, False, True]).drop_duplicates("gsis_id")
    by = g.groupby("gsis_id", sort=False)
    df = pd.DataFrame({"games_played": by["played"].sum().astype(int), "pts_c": by["pc"].sum(min_count=1)})
    pl = g[g["played"]].sort_values(["gsis_id", "week"], ascending=[True, False])
    pl["ago"] = pl.groupby("gsis_id").cumcount() + 1
    for k in (3, 5):
        w = pl[pl["ago"] <= k].groupby("gsis_id")["pc"]
        df[f"points_per_game_l{k}"] = _ratio2(w.sum(min_count=1), w.count())
    df["ppg"] = _ratio2(df["pts_c"], df["games_played"])
    df["points"] = df["pts_c"] / 100
    df["games_with_expected"] = by["xsp"].sum().astype("Int64").where(by["skill"].any())
    xs = g[g["xs"]].groupby("gsis_id")["xc"]
    df["points_expected"] = xs.sum(min_count=1) / 100
    xsp = g[g["xsp"]]
    df["expected_per_game"] = _ratio2(xsp.groupby("gsis_id")["xc"].sum(min_count=1), xsp.groupby("gsis_id")["xc"].count())
    dc = (xsp["pc"] - xsp["xc"])
    df["diff_per_game"] = _ratio2(dc.groupby(xsp["gsis_id"]).sum(min_count=1), dc.groupby(xsp["gsis_id"]).count())
    df = df.reset_index().merge(pos[["gsis_id", "position"]], on="gsis_id", how="left")
    for c, src in (("position_rank_points", "points"), ("position_rank_ppg", "ppg")):
        v = pd.to_numeric(df[src], errors="coerce")
        # rank() over (… order by x desc nulls last): NULLs rank after every value, tied among themselves
        filled = v.fillna(-np.inf)
        df[c] = filled.groupby(df["position"]).rank(method="min", ascending=False).astype("Int64")
    return df[cols]


def trend_windows(games: pd.DataFrame) -> pd.DataFrame:
    """The trends' `points` and `expected_points` windows (`mart_player_trends`: REG games played, QB–TE) over one
    league's priced rows: points_l3 / points_prior / points_change, expected_points_l3 / _prior / _change, games.
    The last three games are the player's last three appearances; expected points count only the games ffverse has."""
    cols = ["gsis_id", "games", "points_l3", "points_prior", "points_change",
            "expected_points_l3", "expected_points_prior", "expected_points_change"]
    if games.empty:
        return pd.DataFrame(columns=cols)
    g = games[games["played"].fillna(False).astype(bool) & games["position"].isin(SKILL)].copy()
    g = g.sort_values(["gsis_id", "week"])
    g["game_no"] = g.groupby("gsis_id").cumcount() + 1
    g["games"] = g.groupby("gsis_id")["game_no"].transform("max")
    g["recent"] = (g["games"] - g["game_no"]) < 3
    g["points"] = pd.to_numeric(g["points"], errors="coerce")
    g["points_expected"] = pd.to_numeric(g["points_expected"], errors="coerce")
    out = pd.DataFrame({"games": g.groupby("gsis_id")["games"].max()})
    for name, col in (("points", "points"), ("expected_points", "points_expected")):
        out[f"{name}_l3"] = g[g["recent"]].groupby("gsis_id")[col].mean()
        out[f"{name}_prior"] = g[~g["recent"]].groupby("gsis_id")[col].mean()
        out[f"{name}_change"] = (out[f"{name}_l3"] - out[f"{name}_prior"]).round(4)
    return out.reset_index()[cols]


DEFENSE_POSITIONS = ("QB", "RB", "WR", "TE", "K")


def defense_allowed(games: pd.DataFrame, positions=DEFENSE_POSITIONS) -> pd.DataFrame:
    """Points allowed by each defense to each position in one season (`mart_defense_vs_position_current` + the
    `mart_defense_trends` windows) over one league's priced REG rows (opponent_team, game_id, week, position, points):
    games, through_week, points_allowed_per_game_std / _l4, games_l4, rank_std / rank_l4 (1 = gives up the most),
    allowed_l3, allowed_prior, allowed_season, change, z, direction (softer / stiffer / steady / insufficient)."""
    cols = ["defense", "position", "games", "through_week", "points_allowed_per_game_std", "points_allowed_per_game_l4",
            "games_l4", "rank_std", "rank_l4", "allowed_l3", "allowed_prior", "allowed_season", "change", "z", "direction"]
    if games.empty:
        return pd.DataFrame(columns=cols)
    g = games[games["position"].isin(list(positions))]
    pg = (g.assign(points=pd.to_numeric(g["points"], errors="coerce"))
          .groupby(["opponent_team", "week", "game_id", "position"], as_index=False)["points"].sum(min_count=1)
          .rename(columns={"opponent_team": "defense", "points": "allowed"}))
    out = []
    for (d, pos), p in pg.groupby(["defense", "position"], sort=False):
        p = p.sort_values("week")
        v = p["allowed"].astype(float)
        n = len(p)
        recent = (n - np.arange(1, n + 1)) < 3
        l3, prior = v[recent].dropna(), v[~recent].dropna()
        a, b = (float(l3.mean()) if len(l3) else None), (float(prior.mean()) if len(prior) else None)
        n_prior = int((~recent).sum())
        sd = float(v.std(ddof=1)) if v.notna().sum() > 1 else None
        change = round(a - b, 2) if a is not None and b is not None else None
        zz = None
        if sd and sd > 0 and n_prior >= 1 and change is not None:
            zz = (a - b) / (sd * np.sqrt(1.0 / 3 + 1.0 / n_prior))
        z = None if zz is None else round(zz, 2)
        if n < 4 or n_prior < 1:
            direction = "insufficient"
        elif round(a - b, 9) >= 3 and zz is not None and zz >= 1:
            direction = "softer"
        elif round(a - b, 9) <= -3 and zz is not None and zz <= -1:
            direction = "stiffer"
        else:
            direction = "steady"
        out.append({"defense": d, "position": pos, "games": n, "through_week": int(p["week"].max()),
                    "points_allowed_per_game_std": _mean2(v),
                    "points_allowed_per_game_l4": _mean2(v.tail(4)),
                    "games_l4": int(min(n, 4)), "allowed_l3": a, "allowed_prior": b,
                    "allowed_season": float(v.mean()) if v.notna().any() else None, "change": change, "z": z,
                    "direction": direction})
    df = pd.DataFrame(out)
    for c, src in (("rank_std", "points_allowed_per_game_std"), ("rank_l4", "points_allowed_per_game_l4")):
        df[c] = pd.to_numeric(df[src], errors="coerce").groupby(df["position"]).rank(method="min", ascending=False).astype("Int64")
    return df[cols]
