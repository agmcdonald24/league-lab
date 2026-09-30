"""Kicker and team-defense (D/ST) projections (plan R-13, model ``kd1.0``).

What it does
------------
* **Components, priced per league** - like projection v2 for QB-TE: per unit-week a stat line, then
  each league's own scoring applied to it.
  - K: FG made by distance (0-19, 20-29, 30-39, 40-49, 50+), FG missed (blocked counted as missed,
    like Sleeper's ``fgmiss``), PAT made, PAT missed. The per-distance misses a league could price
    (``fgmiss_0_19`` ...) are FG missed split by the training seasons' distance shares. Priced with the
    same Sleeper-key -> nflverse-column map as every player (``scoring.SLEEPER_STAT_MAP``).
  - DEF: sacks, interceptions, opponent fumbles recovered, forced fumbles, defensive TDs (INT and
    fumble returns), special-teams TDs, safeties, blocked kicks, and **points allowed as a
    distribution**: a point forecast plus the out-of-fold forecast errors give the probability of each
    ``pts_allow_*`` bucket, and the bucket points are the probability-weighted sum. The defense keys
    are not in ``scoring_stat_map`` (a player-key seed); ``DEF_STAT_MAP`` / ``PTS_ALLOW_BUCKETS`` here
    and the dbt macro ``def_points`` are the one definition, reconciled against Sleeper's own D/ST
    points (docs/METRICS.md).
* **The model**: one ``HistGradientBoostingRegressor`` per component (Poisson loss for counts,
  squared error for points allowed), the same family as the skill positions, on as-of features only
  (games before the week): the team's scoring, FG and PAT attempts, red-zone plays and EPA per play
  (K), the defense's takeaway / sack / TD / points-allowed rates and the opposing offense's sacks
  taken, giveaways, points and EPA (DEF) - each season-to-date, last 3 and last season - plus the
  game (Vegas implied totals, home, dome, week) and, for K, the kicker's own career accuracy by
  distance (shrunk to a prior). Why boosting rather than a hand rates model: the inputs interact
  (implied total x dome x the kicker's range) and have holes (week 1, a new kicker, a team with
  no line yet) that the trees handle natively, and the stat-line machinery is shared with v2.
* **An interval**: the out-of-fold residuals of the league's points (components fitted on the odd
  training seasons predict the even ones and vice versa) give P10 / P50 / P90 as fixed offsets
  from the projection per position and league - a calibrated interval, not quantile models (K and
  D/ST errors barely depend on the level; a few thousand rows do not support a conditional one).
  The floor is clipped at 0 like the skill path (a D/ST can finish below 0; METRICS says how often).
* **Keys**: K rows carry the kicker's ``gsis_id``; DEF rows carry the Sleeper defense id ('KC', 'LAR')
  in ``ops.projections.gsis_id`` (a team defense has no NFL player id; the mart shows it as NULL).
* **Where they go**: ``project()`` (projections.py) appends these rows to the v2 rows and writes
  them through the one B5 writer (``_write_projections``): the freeze applies to them unchanged.
  ``model_version = 'kd1.0'``; the v2 backtest / drift bookkeeping keyed on ``MODEL_VERSION``
  never sees them (drift reads QB-TE only, the v2 backtest counts ``v2.0`` rows).
* **Backtest** (``league-lab backtest-kd``): walk-forward 2021-2025 in League of Scrubs scoring,
  Spearman / MAE / top-10 hit rate per week against season-to-date PPG and last-3 PPG on the same
  unit-weeks; written to ``ops.projection_backtest`` tagged ``kd1.0`` (scorers ``kd_points``,
  ``season_ppg``, ``last3_ppg``). ``KD_SHIP`` records the ship decision per position that backtest
  supports; a position whose model does not beat season PPG ships season PPG as its projection.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg

from .rankings import _hit_rate, _spearman
from .scoring import MAPPED_KEYS, SLEEPER_STAT_MAP

log = logging.getLogger(__name__)

KD_MODEL_VERSION = "kd1.0"
KD_POSITIONS = ("K", "DEF")
QUANTILES = (0.1, 0.5, 0.9)
TOP_N = 10          # a 10-team league starts ten of each
# Fixed hyperparameters (a change is a new KD_MODEL_VERSION): shallow trees and a large leaf minimum;
# a few thousand unit-weeks per position and very noisy weekly outcomes.
KD_HGB = dict(max_iter=150, learning_rate=0.04, max_leaf_nodes=7, min_samples_leaf=80, l2_regularization=1.0, random_state=0)
# What ships per position (decided by the 2021-2025 walk-forward backtest, docs/STATUS.md § Wave C C3):
# "model" = the kd1.0 components; "season_ppg" = the season-to-date PPG baseline carried as the projection.
KD_SHIP: dict[str, str] = {"K": "model", "DEF": "model"}

# ------------------------------------------------------------------------------ stat lines and pricing
K_COMPONENTS = ["fg_made_0_19", "fg_made_20_29", "fg_made_30_39", "fg_made_40_49", "fg_made_50p", "fg_missed", "pat_made", "pat_missed"]
K_MISS_BUCKETS = ["fg_missed_0_19", "fg_missed_20_29", "fg_missed_30_39", "fg_missed_40_49", "fg_missed_50p"]
K_LINE = K_COMPONENTS + K_MISS_BUCKETS
# K line column -> the nflverse weekly-stat column the scoring map prices (50+ = 50-59 + 60+; the
# blocked kicks are already inside fg_missed / pat_missed, so fg_blocked / pat_blocked price as 0)
K_STAT_COLUMN = {
    "fg_made_0_19": "fg_made_0_19", "fg_made_20_29": "fg_made_20_29", "fg_made_30_39": "fg_made_30_39",
    "fg_made_40_49": "fg_made_40_49", "fg_made_50p": "fg_made_50_59", "fg_missed": "fg_missed",
    "fg_missed_0_19": "fg_missed_0_19", "fg_missed_20_29": "fg_missed_20_29", "fg_missed_30_39": "fg_missed_30_39",
    "fg_missed_40_49": "fg_missed_40_49", "fg_missed_50p": "fg_missed_50_59", "pat_made": "pat_made", "pat_missed": "pat_missed",
}

DEF_COUNTS = ["sacks", "interceptions", "fumble_recoveries", "forced_fumbles", "def_tds", "st_tds", "safeties", "blocked_kicks"]
# Sleeper D/ST key -> DEF line column (the SQL twin is dbt/macros/def_points.sql)
DEF_STAT_MAP: dict[str, str] = {
    "sack": "sacks", "int": "interceptions", "fum_rec": "fumble_recoveries", "ff": "forced_fumbles",
    "def_td": "def_tds", "def_st_td": "st_tds", "safe": "safeties", "blk_kick": "blocked_kicks",
}
# Sleeper points-allowed buckets: (key, low, high inclusive; None = no upper bound)
PTS_ALLOW_BUCKETS: list[tuple[str, int, int | None]] = [
    ("pts_allow_0", 0, 0), ("pts_allow_1_6", 1, 6), ("pts_allow_7_13", 7, 13), ("pts_allow_14_20", 14, 20),
    ("pts_allow_21_27", 21, 27), ("pts_allow_28_34", 28, 34), ("pts_allow_35p", 35, None),
]
PA_COLUMNS = ["pa_" + k.removeprefix("pts_allow_") for k, _, _ in PTS_ALLOW_BUCKETS]
DEF_LINE = DEF_COUNTS + ["points_allowed"] + PA_COLUMNS
# D/ST keys a league may weight that kd1.0 does not project (they price 0, and the log names them)
DEF_KEY_PREFIXES = ("def_", "st_", "yds_allow", "pts_allow", "blk_", "sack", "int", "ff", "fum_rec", "safe", "qb_hit", "tkl")


def k_coefficients(scoring: Mapping[str, float]) -> dict[str, float]:
    """Points one unit of each K line column is worth under ``scoring`` (every kicking key is a
    linear ``stat`` key of the scoring map, so the price of a line is a dot product)."""
    to_line = {v: k for k, v in K_STAT_COLUMN.items()}
    coef = dict.fromkeys(K_LINE, 0.0)
    for key, w in scoring.items():
        if not w or MAPPED_KEYS.get(key) != "stat":
            continue
        for part in SLEEPER_STAT_MAP[key][0].split("+"):
            c = to_line.get(part.strip())
            if c is not None:
                coef[c] += float(w)
    return coef


def price_k(df: pd.DataFrame, scoring: Mapping[str, float], prefix: str) -> np.ndarray:
    """League points of the K lines held in ``<prefix><component>`` (missing columns = 0)."""
    coef = k_coefficients(scoring)
    x = np.column_stack([pd.to_numeric(df[prefix + c], errors="coerce").fillna(0).to_numpy(dtype=float)
                         if prefix + c in df else np.zeros(len(df)) for c in K_LINE])
    return np.round(x @ np.array([coef[c] for c in K_LINE]) + 0.0, 2)


def pa_indicators(points_allowed: np.ndarray) -> np.ndarray:
    """(n, 7) one-hot of the points-allowed bucket (NaN -> all 0)."""
    pa = np.asarray(points_allowed, dtype=float)
    out = np.zeros((len(pa), len(PTS_ALLOW_BUCKETS)))
    for j, (_, lo, hi) in enumerate(PTS_ALLOW_BUCKETS):
        out[:, j] = (pa >= lo) & ((pa <= hi) if hi is not None else True)
    return out


def pa_probabilities(mu: np.ndarray, residuals: np.ndarray) -> np.ndarray:
    """(n, 7) probability of each points-allowed bucket for forecasts ``mu`` when the outcome is
    ``mu + r`` with r drawn from the out-of-fold forecast errors ``residuals``; points are whole
    numbers, so a bucket [lo, hi] is the interval [lo - 0.5, hi + 0.5) and anything below 0.5 is a
    shutout."""
    r = np.sort(np.asarray(residuals, dtype=float))
    mu = np.asarray(mu, dtype=float)
    edges = [0.5, 6.5, 13.5, 20.5, 27.5, 34.5]
    cdf = np.column_stack([np.searchsorted(r, e - mu, side="left") / len(r) for e in edges])
    cdf = np.column_stack([np.zeros(len(mu)), cdf, np.ones(len(mu))])
    return np.diff(cdf, axis=1)


def price_def(df: pd.DataFrame, scoring: Mapping[str, float], prefix: str) -> np.ndarray:
    """League points of the DEF lines in ``<prefix><column>``: counts x weights plus the bucket
    weights x the bucket probabilities ``<prefix>pa_*`` (for an outcome: add them with
    ``with_pa_buckets``)."""
    total = np.zeros(len(df))
    for key, col in DEF_STAT_MAP.items():
        w = float(scoring.get(key) or 0)
        if w:
            total += w * pd.to_numeric(df[prefix + col], errors="coerce").fillna(0).to_numpy(dtype=float)
    for (key, _, _), col in zip(PTS_ALLOW_BUCKETS, PA_COLUMNS, strict=True):
        w = float(scoring.get(key) or 0)
        if w:
            total += w * pd.to_numeric(df[prefix + col], errors="coerce").fillna(0).to_numpy(dtype=float)
    return np.round(total + 0.0, 2)


def with_pa_buckets(df: pd.DataFrame, prefix: str) -> pd.DataFrame:
    """``df`` plus ``<prefix>pa_*`` one-hot columns of ``<prefix>points_allowed`` (an outcome line)."""
    d = df.copy()
    ind = pa_indicators(pd.to_numeric(d[prefix + "points_allowed"], errors="coerce").to_numpy(dtype=float))
    for j, c in enumerate(PA_COLUMNS):
        d[prefix + c] = ind[:, j]
    return d


def price(df: pd.DataFrame, position: str, scoring: Mapping[str, float], prefix: str) -> np.ndarray:
    return price_k(df, scoring, prefix) if position == "K" else price_def(df, scoring, prefix)


def unmodelled_def_keys(scoring: Mapping[str, float]) -> list[str]:
    """Non-zero D/ST-looking keys the scoring weights that kd1.0 does not project (they price 0)."""
    handled = set(DEF_STAT_MAP) | {k for k, _, _ in PTS_ALLOW_BUCKETS} | set(MAPPED_KEYS)
    return sorted(k for k, w in scoring.items() if w and k not in handled and k.startswith(DEF_KEY_PREFIXES))


# ------------------------------------------------------------------------------ features (as of the week: games before it)
TEAM_STATS = ["points_for", "points_allowed", "fg_att", "fg_made", "pat_att", "red_zone_plays", "epa_per_play", "plays",
              "sacks", "interceptions", "fumble_recoveries", "forced_fumbles", "def_tds", "st_tds", "blocked_kicks",
              "sacks_suffered", "giveaways", "fg_att_allowed"]
K_TEAM = ["points_for", "fg_att", "fg_made", "pat_att", "red_zone_plays", "epa_per_play"]
K_OPP = ["points_allowed", "fg_att_allowed"]
DEF_TEAM = ["sacks", "interceptions", "fumble_recoveries", "forced_fumbles", "def_tds", "st_tds", "blocked_kicks", "points_allowed"]
DEF_OPP = ["sacks_suffered", "giveaways", "points_for", "epa_per_play", "plays"]
WINDOWS = ("std", "l3", "prev")
GAME_FEATURES = ["week", "is_home", "is_dome", "implied_team_total", "opp_implied_total", "total_line", "spread_line"]
KICKER_FEATURES = ["k_games", "k_att_short", "k_acc_short", "k_acc_mid", "k_acc_long", "k_share_long", "k_pat_acc"]
FEATURES: dict[str, list[str]] = {
    "K": GAME_FEATURES + ["team_games_std"] + [f"{w}_{s}" for s in K_TEAM for w in WINDOWS]
         + [f"opp_{w}_{s}" for s in K_OPP for w in WINDOWS] + KICKER_FEATURES,
    "DEF": GAME_FEATURES + ["team_games_std"] + [f"{w}_{s}" for s in DEF_TEAM for w in WINDOWS]
           + [f"opp_{w}_{s}" for s in DEF_OPP for w in WINDOWS],
}
# Kicker accuracy priors (made / attempted) and their weight in attempts: a kicker with few kicks
# reads as league-typical, not as 100% or 0%. Fixed constants (a change is a new model version).
K_PRIOR = {"short": 0.93, "mid": 0.80, "long": 0.66, "pat": 0.94}
K_PRIOR_ATT = 10.0


def team_game_stats(tg: pd.DataFrame) -> pd.DataFrame:
    """Per team-game: the ``TEAM_STATS`` values (NaN unless played), incl. EPA per play and the FG
    attempts the defense allowed (the opponent's attempts in the same game)."""
    t = tg.copy()
    for c in ("points_for", "points_allowed", "fg_att", "fg_made", "pat_att", "red_zone_plays", "offense_epa", "plays",
              "sacks", "interceptions", "fumble_recoveries", "forced_fumbles", "def_tds", "st_tds", "blocked_kicks",
              "sacks_suffered", "giveaways"):
        t[c] = pd.to_numeric(t[c], errors="coerce").astype(float)
    t["played"] = t["played"].fillna(False).astype(bool)
    t["epa_per_play"] = np.where(t["plays"] > 0, t["offense_epa"] / t["plays"].where(t["plays"] > 0), np.nan)
    opp = t[["game_id", "team", "fg_att"]].rename(columns={"team": "opponent", "fg_att": "fg_att_allowed"})
    t = t.merge(opp, on=["game_id", "opponent"], how="left")
    t.loc[~t["played"], TEAM_STATS] = np.nan
    return t


def team_asof(tg: pd.DataFrame) -> pd.DataFrame:
    """(team, season, week) for every scheduled team-week -> the team's ``TEAM_STATS`` per game over
    the games it played before that week: season to date (``std_``), last three this season
    (``l3_``), last season (``prev_``), and ``team_games_std``. Nothing from the week itself or later."""
    t = team_game_stats(tg).sort_values(["team", "season", "week"]).reset_index(drop=True)
    p = t[t["played"]].reset_index(drop=True)
    g = p.groupby(["team", "season"], sort=False)
    after = p[["team", "season", "week"]].copy()
    after["team_games_std"] = g.cumcount() + 1
    std = g[TEAM_STATS].expanding().mean().reset_index(level=[0, 1], drop=True).sort_index()
    l3 = g[TEAM_STATS].rolling(3, min_periods=1).mean().reset_index(level=[0, 1], drop=True).sort_index()
    after = pd.concat([after, std.add_prefix("std_"), l3.add_prefix("l3_")], axis=1)
    target = t[["team", "season", "week"]].drop_duplicates()
    out = pd.merge_asof(target.sort_values("week"), after.sort_values("week"), on="week", by=["team", "season"],
                        allow_exact_matches=False, direction="backward")
    prev = p.groupby(["team", "season"])[TEAM_STATS].mean().add_prefix("prev_").reset_index()
    prev["season"] = prev["season"] + 1
    out = out.merge(prev, on=["team", "season"], how="left")
    out["team_games_std"] = out["team_games_std"].fillna(0.0)
    return out.sort_values(["team", "season", "week"]).reset_index(drop=True)


def kicker_asof(k: pd.DataFrame) -> pd.DataFrame:
    """(unit_id, season, week) for every K unit row -> the kicker's career kicking before that week:
    games, short (0-39) attempts, accuracy short / 40-49 / 50+ / PAT shrunk to ``K_PRIOR`` with
    ``K_PRIOR_ATT`` pseudo-attempts, and the share of his FG attempts from 50+."""
    k = k.copy()
    k["played"] = k["played"].fillna(False).astype(bool)
    k["t"] = k["season"].astype(int) * 100 + k["week"].astype(int)
    h = k[k["played"]].copy()
    num = {c: pd.to_numeric(h[f"out_{c}"], errors="coerce").fillna(0).astype(float)
           for c in ("fg_made_0_19", "fg_made_20_29", "fg_made_30_39", "fg_made_40_49", "fg_made_50p", "fg_missed_0_19",
                     "fg_missed_20_29", "fg_missed_30_39", "fg_missed_40_49", "fg_missed_50p", "pat_made", "pat_missed")}
    per = pd.DataFrame({
        "unit_id": h["unit_id"].to_numpy(), "t": h["t"].to_numpy(), "games": 1.0,
        "made_s": (num["fg_made_0_19"] + num["fg_made_20_29"] + num["fg_made_30_39"]).to_numpy(),
        "att_s": (num["fg_made_0_19"] + num["fg_made_20_29"] + num["fg_made_30_39"] + num["fg_missed_0_19"]
                  + num["fg_missed_20_29"] + num["fg_missed_30_39"]).to_numpy(),
        "made_m": num["fg_made_40_49"].to_numpy(), "att_m": (num["fg_made_40_49"] + num["fg_missed_40_49"]).to_numpy(),
        "made_l": num["fg_made_50p"].to_numpy(), "att_l": (num["fg_made_50p"] + num["fg_missed_50p"]).to_numpy(),
        "pat_m": num["pat_made"].to_numpy(), "pat_a": (num["pat_made"] + num["pat_missed"]).to_numpy(),
    }).sort_values(["unit_id", "t"]).reset_index(drop=True)
    cols = ["games", "made_s", "att_s", "made_m", "att_m", "made_l", "att_l", "pat_m", "pat_a"]
    cum = per.groupby("unit_id", sort=False)[cols].cumsum()
    cum[["unit_id", "t"]] = per[["unit_id", "t"]]
    target = k[["unit_id", "season", "week", "t"]].drop_duplicates()
    out = pd.merge_asof(target.sort_values("t"), cum.sort_values("t"), on="t", by="unit_id",
                        allow_exact_matches=False, direction="backward")
    out[cols] = out[cols].fillna(0.0)

    def shrunk(made: str, att: str, prior: float) -> pd.Series:
        return (out[made] + K_PRIOR_ATT * prior) / (out[att] + K_PRIOR_ATT)

    fg_att = out["att_s"] + out["att_m"] + out["att_l"]
    res = pd.DataFrame({
        "unit_id": out["unit_id"], "season": out["season"], "week": out["week"],
        "k_games": out["games"], "k_att_short": out["att_s"],
        "k_acc_short": shrunk("made_s", "att_s", K_PRIOR["short"]), "k_acc_mid": shrunk("made_m", "att_m", K_PRIOR["mid"]),
        "k_acc_long": shrunk("made_l", "att_l", K_PRIOR["long"]), "k_pat_acc": shrunk("pat_m", "pat_a", K_PRIOR["pat"]),
        "k_share_long": (out["att_l"] + 1.0) / (fg_att + 6.0),   # prior: 1 in 6 attempts from 50+
    })
    return res


def build_features(units: pd.DataFrame, tg: pd.DataFrame) -> pd.DataFrame:
    """``units`` (mart_kd_week rows) with every feature of ``FEATURES`` for their position."""
    u = units.copy()
    for c in ("is_home", "is_dome"):
        u[c] = u[c].astype("boolean").astype(float)
    for c in ("implied_team_total", "opp_implied_total", "total_line", "spread_line", "week"):
        u[c] = pd.to_numeric(u[c], errors="coerce").astype(float)
    for c in [c for c in u.columns if c.startswith("out_")]:
        u[c] = pd.to_numeric(u[c], errors="coerce").astype(float)
    u["played"] = u["played"].fillna(False).astype(bool)
    ta = team_asof(tg)
    u = u.merge(ta, on=["team", "season", "week"], how="left")
    opp = ta.drop(columns=["team_games_std"]).rename(columns={"team": "opponent"})
    opp = opp.rename(columns={c: f"opp_{c}" for c in opp.columns if c not in ("opponent", "season", "week")})
    u = u.merge(opp, on=["opponent", "season", "week"], how="left")
    ks = u["position"] == "K"
    if ks.any():
        ka = kicker_asof(u[ks][["unit_id", "season", "week", "played", *[c for c in u.columns if c.startswith("out_")]]])
        u = u.merge(ka, on=["unit_id", "season", "week"], how="left")
    else:
        for c in KICKER_FEATURES:
            u[c] = np.nan
    return u.sort_values(["position", "unit_id", "season", "week"]).reset_index(drop=True)


def _matrix(d: pd.DataFrame, position: str) -> np.ndarray:
    x = d[FEATURES[position]].to_numpy(dtype=float).copy()
    x[:, np.isnan(x).all(axis=0)] = 0.0      # an entirely unknown column (binner needs something)
    return x


# ------------------------------------------------------------------------------ data
UNIT_COLUMNS = ["position", "unit_id", "gsis_id", "sleeper_id", "player_name", "team", "opponent", "game_id", "is_home", "is_dome",
                "spread_line", "total_line", "implied_team_total", "opp_implied_total", "season", "week", "roster_status",
                "report_status", "played", *[f"out_{c}" for c in K_COMPONENTS[:-2] + K_MISS_BUCKETS + ["pat_made", "pat_missed"]],
                *[f"out_{c}" for c in DEF_COUNTS + ["points_allowed"]]]
TEAM_GAME_COLUMNS = ["team", "game_id", "season", "week", "opponent", "played", "points_for", "points_allowed", "fg_att", "fg_made",
                     "pat_att", "red_zone_plays", "offense_epa", "plays", "sacks", "interceptions", "fumble_recoveries",
                     "forced_fumbles", "def_tds", "st_tds", "blocked_kicks", "sacks_suffered", "giveaways"]


def _frame(cur: psycopg.Cursor, sql: str, params: tuple) -> pd.DataFrame:
    cur.execute(sql, params)
    return pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])


def load_frame(conn: psycopg.Connection, seasons: list[int]) -> pd.DataFrame:
    """Unit-weeks of ``seasons`` with their features (team history reaches one season further back)."""
    back = sorted({*seasons, *(s - 1 for s in seasons)})
    with conn.cursor() as cur:
        units = _frame(cur, f"""select {', '.join(dict.fromkeys(UNIT_COLUMNS))} from analytics.mart_kd_week
                                where season = any(%s) order by position, unit_id, season, week""", (back,))
        tg = _frame(cur, f"""select {', '.join(TEAM_GAME_COLUMNS)} from analytics.mart_kd_team_game
                             where season = any(%s) order by team, season, week""", (back,))
    f = build_features(units, tg)
    return f[f["season"].isin(seasons)].reset_index(drop=True)


def kd_leagues(conn: psycopg.Connection) -> dict[str, dict[str, tuple[str, dict[str, float]]]]:
    """position -> {league_id: (name, scoring)} for the current leagues that start that position."""
    with conn.cursor() as cur:
        cur.execute("""select league_id, league_name, scoring_settings, roster_positions from analytics.dim_league_season
                       where is_current_season order by is_reference_league desc, league_name""")
        rows = cur.fetchall()
    out: dict[str, dict[str, tuple[str, dict[str, float]]]] = {p: {} for p in KD_POSITIONS}
    for lid, name, scoring, slots in rows:
        for p in KD_POSITIONS:
            if p in [str(s).upper() for s in (slots or [])]:
                out[p][lid] = (name, {k: float(v) for k, v in (scoring or {}).items()})
    return out


# ------------------------------------------------------------------------------ the model
@dataclass
class KDModel:
    position: str
    components: dict[str, object] = field(default_factory=dict)
    miss_shares: dict[str, float] = field(default_factory=dict)          # K: FG missed split by distance
    pa_residuals: np.ndarray | None = None                               # DEF: out-of-fold points-allowed errors
    offsets: dict[str, tuple[float, float, float]] = field(default_factory=dict)  # league -> P10/P50/P90 offsets
    n_rows: int = 0
    train_seasons: str = ""


def _regressor(loss: str):
    from sklearn.ensemble import HistGradientBoostingRegressor

    return HistGradientBoostingRegressor(loss=loss, **KD_HGB)


def _targets(position: str) -> list[str]:
    return K_COMPONENTS if position == "K" else [*DEF_COUNTS, "points_allowed"]


def training_rows(frame: pd.DataFrame, position: str) -> pd.DataFrame:
    d = frame[(frame["position"] == position) & frame["played"]]
    return d.dropna(subset=[f"out_{c}" for c in _targets(position)]).reset_index(drop=True)


def _fit_components(x: np.ndarray, d: pd.DataFrame, position: str) -> dict[str, object]:
    models: dict[str, object] = {}
    for c in _targets(position):
        y = d[f"out_{c}"].to_numpy(dtype=float)
        loss = "squared_error" if c == "points_allowed" else "poisson"
        models[c] = _regressor(loss).fit(x, np.clip(y, 0, None))
    return models


def _line(models: Mapping[str, object], x: np.ndarray, position: str, miss_shares: Mapping[str, float],
          pa_residuals: np.ndarray | None) -> pd.DataFrame:
    """The projected stat line (``proj_<column>``) for a feature matrix."""
    out = {f"proj_{c}": np.clip(models[c].predict(x), 0, None) for c in _targets(position)}
    if position == "K":
        for b in K_MISS_BUCKETS:
            out[f"proj_{b}"] = out["proj_fg_missed"] * miss_shares.get(b, 0.0)
    else:
        probs = pa_probabilities(out["proj_points_allowed"], pa_residuals if pa_residuals is not None and len(pa_residuals) else np.zeros(1))
        for j, c in enumerate(PA_COLUMNS):
            out[f"proj_{c}"] = probs[:, j]
    return pd.DataFrame(out)


def _outcome(d: pd.DataFrame, position: str) -> pd.DataFrame:
    return with_pa_buckets(d, "out_") if position == "DEF" else d


def fit_kd(frame: pd.DataFrame, position: str, scorings: Mapping[str, tuple[str, dict[str, float]]]) -> KDModel:
    """Fit one position on every played unit-week of ``frame`` (the caller passes training seasons)."""
    d = training_rows(frame, position)
    x = _matrix(d, position)
    seasons = sorted(d["season"].unique())
    m = KDModel(position, n_rows=len(d), train_seasons=f"{min(seasons)}-{max(seasons)}" if seasons else "")
    if position == "K":
        tot = {b: float(d[f"out_{b}"].sum()) for b in K_MISS_BUCKETS}
        s = sum(tot.values())
        m.miss_shares = {b: (v / s if s else 1.0 / len(K_MISS_BUCKETS)) for b, v in tot.items()}
    # out-of-fold lines: components fitted on the odd training seasons predict the even ones and vice
    # versa, so the errors the interval (and the points-allowed distribution) learn from are real ones
    fold = d["season"].map({s: i % 2 for i, s in enumerate(seasons)}).to_numpy()
    oof_models: dict[int, dict[str, object]] = {}
    for k in (0, 1):
        tr = fold != k
        if tr.sum() >= 200 and (fold == k).sum() > 0:
            oof_models[k] = _fit_components(x[tr], d[tr], position)
    if position == "DEF":
        oof_pa = np.full(len(d), np.nan)
        for k, mk in oof_models.items():
            oof_pa[fold == k] = np.clip(mk["points_allowed"].predict(x[fold == k]), 0, None)
        ok = ~np.isnan(oof_pa)
        m.pa_residuals = np.sort(d["out_points_allowed"].to_numpy(dtype=float)[ok] - oof_pa[ok])
    oof = pd.DataFrame(index=range(len(d)), columns=[f"proj_{c}" for c in (K_LINE if position == "K" else DEF_LINE)], dtype=float)
    for k, mk in oof_models.items():
        idx = np.flatnonzero(fold == k)
        oof.iloc[idx] = _line(mk, x[idx], position, m.miss_shares, m.pa_residuals).reindex(columns=oof.columns).to_numpy()
    have = oof.notna().all(axis=1).to_numpy()
    actual = _outcome(d, position)
    for league_id, (_, scoring) in scorings.items():
        r = price(actual, position, scoring, "out_")[have] - price(oof[have], position, scoring, "proj_")
        m.offsets[league_id] = tuple(float(q) for q in np.quantile(r, QUANTILES)) if len(r) else (0.0, 0.0, 0.0)
    m.components = _fit_components(x, d, position)
    log.info("kd fit %s: %s rows (%s), P10/P50/P90 offsets %s", position, len(d), m.train_seasons,
             {k[-6:]: tuple(round(v, 2) for v in o) for k, o in m.offsets.items()})
    return m


def predict_kd(m: KDModel, rows: pd.DataFrame, scorings: Mapping[str, tuple[str, dict[str, float]]]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(one row per league x unit-week: proj_points, p10, p50, p90; the league-free stat line per unit-week)."""
    rows = rows.reset_index(drop=True)
    line = _line(m.components, _matrix(rows, m.position), m.position, m.miss_shares, m.pa_residuals)
    keys = rows[["position", "unit_id", "season", "week"]].astype({"season": int, "week": int})
    lines = pd.concat([keys, line], axis=1)
    frames = []
    for league_id, (_, scoring) in scorings.items():
        o = keys.copy()
        o["league_id"] = league_id
        o["proj_points"] = price(line, m.position, scoring, "proj_")
        lo, mid, hi = m.offsets.get(league_id, (0.0, 0.0, 0.0))
        qs = np.sort(np.column_stack([o["proj_points"] + lo, o["proj_points"] + mid, o["proj_points"] + hi]), axis=1)
        o["p10"], o["p50"], o["p90"] = np.clip(qs[:, 0], 0, None), qs[:, 1], qs[:, 2]
        o["p90"] = np.maximum(o["p90"], o["proj_points"])
        o["p50"] = np.clip(o["p50"], o["p10"], o["p90"])
        frames.append(o)
    return pd.concat(frames, ignore_index=True), lines


# ------------------------------------------------------------------------------ baselines (the yardsticks and the fallback)
def unit_points(frame: pd.DataFrame, position: str, scoring: Mapping[str, float]) -> pd.DataFrame:
    """Played unit-weeks of a position with their league points (``points``)."""
    d = training_rows(frame, position)
    d = d.assign(points=price(_outcome(d, position), position, scoring, "out_"))
    return d[["position", "unit_id", "season", "week", "points"]]


def ppg_baselines(frame: pd.DataFrame, position: str, scoring: Mapping[str, float]) -> pd.DataFrame:
    """(unit_id, season, week) for every unit row of ``position`` -> ``season_ppg`` (league points per
    game over his games this season before the week; before his first game of a season, last
    season's) and ``last3_ppg`` (his last three games before the week, across seasons)."""
    pts = unit_points(frame, position, scoring).sort_values(["unit_id", "season", "week"]).reset_index(drop=True)
    pts["t"] = pts["season"].astype(int) * 100 + pts["week"].astype(int)
    after = pd.DataFrame({
        "unit_id": pts["unit_id"], "t": pts["t"], "std_season": pts["season"].astype(int),
        "season_ppg": pts.groupby(["unit_id", "season"], sort=False)["points"].expanding().mean()
                         .reset_index(level=[0, 1], drop=True).sort_index(),
        "last3_ppg": pts.groupby("unit_id", sort=False)["points"].rolling(3, min_periods=1).mean()
                        .reset_index(level=0, drop=True).sort_index(),
    })
    target = frame[frame["position"] == position][["unit_id", "season", "week"]].drop_duplicates().copy()
    target["t"] = target["season"].astype(int) * 100 + target["week"].astype(int)
    out = pd.merge_asof(target.sort_values("t"), after.sort_values("t"), on="t", by="unit_id",
                        allow_exact_matches=False, direction="backward")
    out.loc[out["std_season"] != out["season"], "season_ppg"] = np.nan      # last game was in an earlier season
    prev = pts.groupby(["unit_id", "season"])["points"].mean().rename("prev_ppg").reset_index()
    prev["season"] = prev["season"] + 1
    out = out.merge(prev, on=["unit_id", "season"], how="left")
    out["season_ppg"] = out["season_ppg"].fillna(out["prev_ppg"])
    return out[["unit_id", "season", "week", "season_ppg", "last3_ppg"]]


# ------------------------------------------------------------------------------ production
PROJECTION_COLUMNS = ["model_version", "fitted_at", "train_seasons", "league_id", "season", "week", "gsis_id", "position",
                      "proj_points", "p10", "p50", "p90"]


def project_kd(conn: psycopg.Connection, season: int, seasons: list[int] | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """K and DEF rows for ``ops.projections`` (every unit-week of ``season``, per league that starts
    the position) and their league-free stat lines. Fitted on every season before ``season``."""
    leagues = kd_leagues(conn)
    if not any(leagues.values()):
        return pd.DataFrame(columns=PROJECTION_COLUMNS), pd.DataFrame()
    with conn.cursor() as cur:
        cur.execute("select distinct season from analytics.mart_kd_week where played order by 1")
        have = [int(r[0]) for r in cur.fetchall()]
    train_seasons = [s for s in (seasons or have) if s < season]
    frame = load_frame(conn, [*train_seasons, season])
    target = frame[frame["season"] == season]
    preds, lines = [], []
    for pos in KD_POSITIONS:
        scorings = leagues[pos]
        if not scorings:
            continue
        for lid, (name, scoring) in scorings.items():
            if pos == "DEF" and (miss := unmodelled_def_keys(scoring)):
                log.info("kd %s (%s): D/ST keys not projected (price 0): %s", name, lid[-6:], ", ".join(miss))
        rows = target[target["position"] == pos]
        if KD_SHIP.get(pos, "model") == "model":
            m = fit_kd(frame[frame["season"] < season], pos, scorings)
            p, ln = predict_kd(m, rows, scorings)
            p["train_seasons"] = m.train_seasons
        else:
            p, ln = ppg_projection(frame, rows, pos, scorings, season)
        preds.append(p)
        lines.append(ln)
    pred = pd.concat(preds, ignore_index=True)
    pred["gsis_id"] = pred["unit_id"]
    pred["model_version"], pred["fitted_at"] = KD_MODEL_VERSION, datetime.now(UTC)
    log.info("kd projections: %s rows for %s (%s)", len(pred), season,
             ", ".join(f"{p}: {n}" for p, n in pred.groupby("position").size().items()))
    return pred[PROJECTION_COLUMNS], pd.concat(lines, ignore_index=True)


def ppg_projection(frame: pd.DataFrame, rows: pd.DataFrame, position: str, scorings: Mapping[str, tuple[str, dict[str, float]]],
                   season: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The fallback a no-ship decision uses: season-to-date PPG in the league's scoring as the
    projection, with the same kind of calibrated interval (residuals of that baseline in the training
    seasons)."""
    frames = []
    keys = rows[["position", "unit_id", "season", "week"]].astype({"season": int, "week": int}).reset_index(drop=True)
    for league_id, (_, scoring) in scorings.items():
        b = ppg_baselines(frame, position, scoring)
        hist = b[b["season"] < season].merge(unit_points(frame, position, scoring), on=["unit_id", "season", "week"])
        r = (hist["points"] - hist["season_ppg"]).dropna().to_numpy()
        lo, mid, hi = (float(q) for q in np.quantile(r, QUANTILES)) if len(r) else (0.0, 0.0, 0.0)
        o = keys.merge(b, on=["unit_id", "season", "week"], how="left")
        o["league_id"] = league_id
        o["proj_points"] = o["season_ppg"].round(2)
        o["p10"], o["p50"], o["p90"] = (o["proj_points"] + lo).clip(lower=0), o["proj_points"] + mid, o["proj_points"] + hi
        o["p90"] = np.maximum(o["p90"], o["proj_points"])
        o["p50"] = np.clip(o["p50"], o["p10"], o["p90"])
        o["train_seasons"] = "season-to-date PPG"
        frames.append(o.dropna(subset=["proj_points"]).drop(columns=["season_ppg", "last3_ppg"]))
    return pd.concat(frames, ignore_index=True), keys.iloc[0:0]


def rows_after_project(conn: psycopg.Connection, season: int) -> pd.DataFrame:
    """Called by ``projections.project``: the K / DEF rows to write with the v2 rows. A failure is
    logged and yields no rows (the lineups then value K / DEF by PPG as before) - never fatal."""
    try:
        with conn.cursor() as cur:
            cur.execute("select to_regclass('analytics.mart_kd_week') is not null and to_regclass('analytics.mart_kd_team_game') is not null")
            if not cur.fetchone()[0]:
                log.warning("kd: analytics.mart_kd_week is not built (run `make build`); no K / DEF projections this run")
                return pd.DataFrame(columns=PROJECTION_COLUMNS)
        pred, _ = project_kd(conn, season)
        return pred
    except Exception:
        conn.rollback()
        log.exception("K / DEF projections failed (the v2 rows are written without them)")
        return pd.DataFrame(columns=PROJECTION_COLUMNS)


# ------------------------------------------------------------------------------ walk-forward backtest
SCORERS = ("kd_points", "season_ppg", "last3_ppg")


def score_weeks(p: pd.DataFrame, min_units: int = 8) -> list[dict]:
    """Per season-week: each scorer (``SCORERS`` columns) on the same unit-weeks (all scorers known)."""
    out = []
    p = p.dropna(subset=[*SCORERS, "points"])
    for (season, week), g in p.groupby(["season", "week"]):
        if len(g) < min_units:
            continue
        y = g["points"]
        inside = float(((y >= g["p10"]) & (y <= g["p90"])).mean())
        for s in SCORERS:
            out.append({"season": int(season), "week": int(week), "scorer": s, "n_players": int(len(g)),
                        "spearman": _spearman(g[s], y), "top_n": TOP_N, "hit_rate": _hit_rate(g[s], y, TOP_N),
                        "mae": float((g[s] - y).abs().mean()),
                        "coverage_80": inside if s == "kd_points" else None,
                        "interval_width": float((g["p90"] - g["p10"]).mean()) if s == "kd_points" else None})
    return out


def backtest_kd(conn: psycopg.Connection, test_seasons: list[int], out_dir: Path | None = None) -> pd.DataFrame:
    """Walk-forward: for each season N, fit on every season before N, project N's unit-weeks, score
    in each K/DEF league's scoring against season-to-date and last-3 PPG. Replaces the ``kd1.0`` rows
    of ``ops.projection_backtest`` and writes a report."""
    from .config import PROJECT_ROOT
    from .projections import _write

    leagues = kd_leagues(conn)
    with conn.cursor() as cur:
        cur.execute("select distinct season from analytics.mart_kd_week where played order by 1")
        have = [int(r[0]) for r in cur.fetchall()]
    first = min(have)
    frame = load_frame(conn, [s for s in have if s <= max(test_seasons)])
    rows: list[dict] = []
    for n in test_seasons:
        train = frame[frame["season"] < n]
        test = frame[(frame["season"] == n) & frame["played"]]
        for pos in KD_POSITIONS:
            scorings = leagues[pos]
            if not scorings or test[test["position"] == pos].empty:
                continue
            m = fit_kd(train, pos, scorings)
            pred, _ = predict_kd(m, test[test["position"] == pos], scorings)
            for league_id, (_, scoring) in scorings.items():
                base = ppg_baselines(frame[frame["season"] <= n], pos, scoring)
                p = (pred[pred["league_id"] == league_id].rename(columns={"proj_points": "kd_points"})
                     .merge(unit_points(test, pos, scoring), on=["position", "unit_id", "season", "week"])
                     .merge(base, on=["unit_id", "season", "week"], how="left"))
                for r in score_weeks(p):
                    rows.append({**r, "league_id": league_id, "position": pos, "train_seasons": f"{first}-{n - 1}"})
            log.info("kd backtest %s %s scored", n, pos)
    res = pd.DataFrame(rows)
    run_id = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    res["run_id"], res["run_at"], res["model_version"] = run_id, datetime.now(UTC), KD_MODEL_VERSION
    _write(conn, "ops.projection_backtest", res, "model_version = %s", (KD_MODEL_VERSION,))
    out_dir = out_dir or PROJECT_ROOT / "reports" / "backtests"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"projection_kd_{min(test_seasons)}_{max(test_seasons)}_{run_id}.md"
    path.write_text(report(res, leagues))
    log.info("kd report written to %s", path)
    return res


def summarize(res: pd.DataFrame, by: tuple[str, ...] = ("league_id", "position", "scorer")) -> pd.DataFrame:
    return res.groupby(list(by)).agg(weeks=("week", "count"), n=("n_players", "mean"), spearman=("spearman", "mean"),
                                     hit_rate=("hit_rate", "mean"), mae=("mae", "mean"), coverage_80=("coverage_80", "mean"),
                                     interval_width=("interval_width", "mean")).reset_index()


def verdict(res: pd.DataFrame) -> dict[tuple[str, str], dict[str, float]]:
    """(league, position) -> mean Spearman per scorer and the ship rule: the model ships only if it
    beats season PPG on Spearman averaged over the held-out season-weeks."""
    s = summarize(res)
    out = {}
    for (lid, pos), g in s.groupby(["league_id", "position"]):
        sp = g.set_index("scorer")["spearman"].to_dict()
        out[(lid, pos)] = {**sp, "ships": "model" if sp.get("kd_points", -1) > sp.get("season_ppg", 1) else "season_ppg"}
    return out


def report(res: pd.DataFrame, leagues: Mapping[str, Mapping[str, tuple[str, dict]]]) -> str:
    names = {lid: name for pos in leagues.values() for lid, (name, _) in pos.items()}
    lines = [f"# K and D/ST projection backtest ({KD_MODEL_VERSION})",
             f"_generated {datetime.now(UTC):%Y-%m-%d %H:%M} UTC · walk-forward: train on seasons before N, test N · "
             "every kicker / team defense that played, regular season, scored on the unit-weeks all three scorers know_", "",
             "`kd_points` = the kd1.0 stat line priced in the league's scoring; `season_ppg` = season-to-date points per game "
             "(last season's before the first game); `last3_ppg` = the last three games. Top-N = 10. `coverage_80` = share inside "
             "[P10, P90].", ""]
    for (lid, pos), g in res.groupby(["league_id", "position"]):
        lines += [f"## {names.get(lid, lid)} · {pos}", "", "| Season | Scorer | Weeks | Units/wk | Spearman | Top-10 hit | MAE | Coverage 80 | Width |",
                  "|---|---|---|---|---|---|---|---|---|"]
        for r in summarize(g, ("season", "scorer")).sort_values(["season", "scorer"]).itertuples():
            cov = "" if pd.isna(r.coverage_80) else f"{r.coverage_80:.1%}"
            wid = "" if pd.isna(r.interval_width) else f"{r.interval_width:.1f}"
            lines.append(f"| {r.season} | `{r.scorer}` | {r.weeks} | {r.n:.0f} | {r.spearman:.3f} | {r.hit_rate:.1%} | {r.mae:.2f} | {cov} | {wid} |")
        for r in summarize(g, ("scorer",)).itertuples():
            cov = "" if pd.isna(r.coverage_80) else f"{r.coverage_80:.1%}"
            lines.append(f"| **all** | `{r.scorer}` | {r.weeks} | {r.n:.0f} | {r.spearman:.3f} | {r.hit_rate:.1%} | {r.mae:.2f} | {cov} | |")
        lines.append("")
    lines += ["## Ship rule", ""]
    for (lid, pos), v in verdict(res).items():
        lines.append(f"- **{names.get(lid, lid)} {pos}**: kd_points {v.get('kd_points', float('nan')):.3f} vs season_ppg "
                     f"{v.get('season_ppg', float('nan')):.3f} vs last3_ppg {v.get('last3_ppg', float('nan')):.3f} -> ships **{v['ships']}**")
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------------------ entry points
def run_backtest(seasons: str, out: Path | None = None) -> pd.DataFrame:
    from .config import get_settings
    from .rankings import parse_seasons

    with psycopg.connect(get_settings().pipeline_dsn(), autocommit=False) as conn:
        return backtest_kd(conn, parse_seasons(seasons), out)


__all__ = ["DEF_STAT_MAP", "KD_MODEL_VERSION", "KD_POSITIONS", "KD_SHIP", "PTS_ALLOW_BUCKETS", "backtest_kd", "build_features",
           "fit_kd", "kicker_asof", "pa_probabilities", "ppg_baselines", "predict_kd", "price_def", "price_k", "project_kd",
           "rows_after_project", "team_asof", "verdict"]
