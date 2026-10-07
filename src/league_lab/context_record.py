"""The context record (Wave I-O, IO-1): grade the context the app shows beside the projection, and keep it from now on.

Two kinds of context have been shown without a grade: the **cornerback call** (the matchup board, the home, DFS:
"faces a shutdown corner", "easy to throw on") and DFS's **"Worth a look"** list (``dfs.worth``). This module

* rebuilds both as they would have read each past week from **as-of inputs** (``rebuild_week``):

  - the corner call itself (``analytics.mart_cb_matchups``: the depth chart before kickoff, his target sides before
    the week) is clean, but the corner's **rank and quarter are not**: the mart joins ``mart_cb_rankings``' window
    ``two_seasons`` *of that season* — the season before plus the whole season as it stands now, the week itself and
    every later week included (look-ahead). ``cb_rank_asof`` recomputes the same ranking (the same pool, the same three
    z-scores, the same opponent adjustment) from the games **before** the week only; at the end of a season it equals
    the mart (``validate_asof_rank``);
  - the defense against his position: the screen's rank (``mart_defense_vs_position_current``: every defense's
    season-to-date points allowed per game to the position, ranked among all of them) computed from the games before
    the week (``defense_rank_asof``: each defense's latest row of ``mart_defense_vs_position`` before the week) — the
    same points allowed the projection reads as ``opp_allowed_std``;
  - the role trend: ``dfs.role_trend`` on his games of the season before the week (routes per dropback left out of
    a rebuilt week: the participation file arrives after the season, so the live screen never had it);
  - the betting line: ``dim_game``'s spread and total (nflverse keeps the closing line: later than a Thursday freeze
    for a Sunday game — the one input not strictly as-of);
  - the weather: the last forecast fetched before kickoff (``int_game_weather.forecast_*``), when one was kept (2026
    on); 2025 has none, so a rebuilt 2025 week has no weather signal (weather only ever removes a player from the
    list);
  - not rebuilt: the injury overlay that turns a call into "no call" when a named corner is not expected to play, and
    the "out" filter of the list (the report as it stood is not kept);

* grades them against the projection made before the game, in **Half PPR** (``ref:half``, the reference scoring the
  site opens on = the League of Scrubs' scoring): 2025 from the walk-forward rows of ``ops.calibration_oof`` (the
  production fit on 2016-2024), 2026 from ``ops.projections`` (weeks 1-3 the refit labelled ``refit``, week 4 the
  board frozen at kickoff); the miss = actual - projected, a bootstrap interval that resamples whole games;
* keeps ``ops.context_record`` from now on (``write_record``, under ``ops.lineup_record``'s freeze rule): the next week
  to kick off is written by every run before its first kickoff (``kickoff``) and never rewritten after it; a played
  week with nothing stored is rebuilt once from the as-of inputs above (``reconstructed``); every run grades the rows
  whose games are final (``actual_points``, ``miss``).

``league-lab context-record`` runs it (idempotent, safe every night). docs/METRICS.md § "The context record".

**Wave I-P (IP-3)** grades two more claims the same way (docs/METRICS.md § "Trends and the role trend, graded"):
Trends' "below / above expectation" (the season's points per game minus expected points per game; the mart keeps only
the season as it stands, so a past week's tag is rebuilt from the games before the week: ``asof_trend`` /
``trend_asof_week``) and the role chips' "role up / down" (``role_trend`` before the week, as above). The record keeps
the tag each week (``trend_games``, ``trend_ppg``, ``trend_gap``, ``trend_tag``, ``trend_reason``; rows written before
the columns are filled once from the games before their week: ``backfill_trend``) and the stored grade adds kinds
``trend`` / ``trend_raw`` / ``role`` and the sentences ``summary`` ``trend`` / ``trend_head`` / ``role``, the next game's
outcome read from the record itself. The long study (2021-2026, the share that holds) is ``study_frame`` +
``trend_grade`` / ``role_grade``: ``uv run python -m league_lab.context_record study`` prints its tables.
"""

from __future__ import annotations

import json
import logging
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from . import dfs as D

log = logging.getLogger(__name__)

TABLE = "ops.context_record"
ANCHOR_LEAGUE = "1389709692405551104"     # League of Scrubs: its scoring is the reference Half PPR (refleague "half")
SCORING_SEED = "scrubs"
SCORING_WORDS = "Half PPR"
FIRST_SEASON = 2025                      # mart_cb_matchups starts in 2025
TONE_EDGE = 10 / 32                      # = research.TONE_EDGE: 10 of 32 defenses at each end
N_DEFENSES = 32
LABEL_TONE = {"shutdown": "difficult", "solid": "neutral", "target": "favorable"}
TIER_WORDS = {"shutdown": "shutdown", "solid": "average", "target": "easy to throw on", "unranked": "unranked"}
TIERS = ("shutdown", "solid", "target", "unranked")
CERTAINTY = {"clear": "likely", "even": "unclear"}
LIST_TOP = D.LIST_TOP                     # the screen shows the top 8 per position
N_BOOT = 2000
SEED = 20261006
RECORD_SOURCES = ("kickoff", "reconstructed")

COLUMNS = ["run_at", "as_of", "first_kickoff_at", "record_source", "model_version", "scoring", "season", "week",
           "gsis_id", "player_name", "position", "team", "opponent", "game_id", "proj_points", "signals",
           "defense_tone", "corner_certainty", "corner_tier", "corner_rank", "corner_n", "role_trend", "game_tone",
           "weather_tone", "worth", "listed", "worth_corner", "listed_corner", "actual_points", "miss", "graded_at",
           "worth_two",
           # ---- IP-3: Trends' tag as it read before the week (games before it only) — graded over the next 1 / 2 / 4 games
           "trend_games", "trend_ppg", "trend_gap", "trend_tag", "trend_reason"]
DDL = """create table if not exists ops.context_record (
        run_at timestamptz, as_of timestamptz, first_kickoff_at timestamptz, record_source text, model_version text,
        scoring text, season integer, week integer, gsis_id text, player_name text, position text, team text,
        opponent text, game_id text, proj_points double precision, signals jsonb, defense_tone text,
        corner_certainty text, corner_tier text, corner_rank integer, corner_n integer, role_trend text, game_tone text,
        weather_tone text, worth boolean, listed boolean, worth_corner boolean, listed_corner boolean,
        actual_points double precision, miss double precision, graded_at timestamptz);
        create index if not exists context_record_idx on ops.context_record (season, week, gsis_id);
        alter table ops.context_record add column if not exists worth_two boolean;
        alter table ops.context_record add column if not exists trend_games integer,
            add column if not exists trend_ppg double precision, add column if not exists trend_gap double precision,
            add column if not exists trend_tag text, add column if not exists trend_reason text"""
# ---- IO-1 fix round: the candidate the PO wants graded out of sample from 2026 week 5 — at least two favourable signals
# other than the cornerback (all of them in the projection today). In-sample (2025 and 2026 weeks 1-4): 829 player-weeks,
# +0.43 against the rest (+0.03 to +0.81) — found on those weeks, so not adopted; the kickoff weeks answer it.
TWO_MIN_FAVOURABLE = 2
# the rows written before the column existed: derived from the signals they stored (what was shown is not changed)
TWO_BACKFILL_SQL = """update ops.context_record c set worth_two = (
        select count(*) from jsonb_array_elements(coalesce(c.signals, '[]'::jsonb)) as s
        where s ->> 'tone' = 'favorable' and s ->> 'signal' <> 'corner') >= %s
    where c.worth_two is null"""


def worth_two(sigs: Sequence[Mapping]) -> bool:
    """The candidate rule: at least ``TWO_MIN_FAVOURABLE`` favourable signals other than the cornerback call."""
    return sum(1 for x in sigs if x.get("tone") == "favorable" and x.get("signal") != "corner") >= TWO_MIN_FAVOURABLE


# ================================================================================================ the as-of corner rank
def _is_cb_game(cov: pd.DataFrame) -> pd.Series:
    sp, p = cov["snap_position"], cov["position"]
    return (sp == "CB") | ((sp == "DB") & p.isin(["CB", "DB"])) | (sp.isna() & (p == "CB"))


def _in_window(season: pd.Series, week: pd.Series, s: int, w: int) -> pd.Series:
    """The games of the window 'two_seasons' as of (s, w): season s-1, and season s before week w."""
    return (season == s - 1) | ((season == s) & (week < w))


def _exp_ypt(off: pd.DataFrame, s: int, w: int) -> pd.DataFrame:
    """Per (game, offense): the offense's WR + TE yards per target over the game's season and the one before, the game
    left out (mart_cb_rankings' ``off_exp``), counting only games before (s, w)."""
    o = off[(off["season"] < s) | ((off["season"] == s) & (off["week"] < w))]
    if o.empty:
        return pd.DataFrame(columns=["game_id", "offense", "exp_ypt"])
    tot = o.groupby(["season", "offense"], as_index=False)[["targets", "yards"]].sum()
    prev = tot.assign(season=tot["season"] + 1).rename(columns={"targets": "t_prev", "yards": "y_prev"})
    tot = tot.rename(columns={"targets": "t_cur", "yards": "y_cur"})
    g = o.merge(tot, on=["season", "offense"], how="left").merge(prev, on=["season", "offense"], how="left")
    t = g["t_cur"].fillna(0) + g["t_prev"].fillna(0) - g["targets"]
    y = g["y_cur"].fillna(0) + g["y_prev"].fillna(0) - g["yards"]
    g["exp_ypt"] = (y / t).where(t != 0)
    return g[["game_id", "offense", "exp_ypt"]]


def _passer_rating(c, t, y, td, i) -> pd.Series:
    def clamp(x):
        return x.clip(lower=0, upper=2.375)
    with np.errstate(divide="ignore", invalid="ignore"):
        r = 100.0 / 6 * (clamp((c / t - 0.3) * 5) + clamp((y / t - 3) * 0.25) + clamp(td / t * 20) + clamp(2.375 - i / t * 25))
    return r.where(t > 0)


def cb_rank_asof(cov: pd.DataFrame, off: pd.DataFrame, season: int, week: int) -> pd.DataFrame:
    """mart_cb_rankings' window 'two_seasons' computed from the games before ``week`` of ``season`` only (and the
    season before): gsis_id, is_ranked, quality_rank, quality_label, n_ranked. ``cov``: int_defender_game_coverage_snaps
    rows (REG); ``off``: per game and offense, the WR + TE targets and yards (game_id, season, week, offense, targets,
    yards). A game of ``week`` itself, or later, never enters (the as-of rule)."""
    cols = ["gsis_id", "is_ranked", "quality_rank", "quality_label", "n_ranked"]
    w = cov[_in_window(cov["season"], cov["week"], season, week)].copy()
    if w.empty:
        return pd.DataFrame(columns=cols)
    w["is_cb_game"] = _is_cb_game(w)
    w = w.merge(_exp_ypt(off, season, week).rename(columns={"offense": "opponent"}), on=["game_id", "opponent"], how="left")
    t = w["def_targets"]
    w["exp_w"] = (w["exp_ypt"] * t).where(w["exp_ypt"].notna())
    w["exp_t"] = t.where(w["exp_ypt"].notna())
    a = w.groupby("gsis_id").agg(
        games=("game_id", "size"), games_at_cb=("is_cb_game", "sum"), cov=("coverage_snaps", "sum"),
        targets=("def_targets", "sum"), comp=("def_completions_allowed", "sum"), yards=("def_yards_allowed", "sum"),
        tds=("def_receiving_td_allowed", "sum"), ints=("def_ints", "sum"), exp_w=("exp_w", "sum"),
        exp_t=("exp_t", "sum"))
    team_games = int(w.groupby("team")["game_id"].nunique().max())
    min_cov = 20 * team_games
    a["is_cb"] = a["games_at_cb"] * 2 >= a["games"]
    a = a[a["is_cb"]].copy()
    with np.errstate(divide="ignore", invalid="ignore"):
        a["tpcs"] = (a["targets"] / a["cov"]).where(a["cov"] > 0)
        a["ypt"] = (a["yards"] / a["targets"]).where(a["targets"] > 0)
        a["exp_faced"] = (a["exp_w"] / a["exp_t"]).where(a["exp_t"] > 0)
    a["rating"] = _passer_rating(a["comp"], a["targets"], a["yards"], a["tds"], a["ints"])
    a["is_ranked"] = a["is_cb"] & (a["cov"] >= min_cov) & (a["targets"] > 0) & a["exp_faced"].notna()
    r = a[a["is_ranked"]]
    if r.empty:
        a["quality_rank"], a["quality_label"], a["n_ranked"] = np.nan, None, 0
        return a.reset_index()[cols]
    pool_ypt = r["yards"].sum() / r["targets"].sum()
    pool_exp = (r["exp_faced"] * r["targets"]).sum() / r["targets"].sum()
    a["adj"] = ((a["ypt"] - a["exp_faced"] + pool_exp) * a["targets"] + pool_ypt * 30) / (a["targets"] + 30)
    r = a[a["is_ranked"]].copy()
    z = sum((r[c] - r[c].mean()) / r[c].std(ddof=1) for c in ("tpcs", "adj", "rating"))
    r["quality"] = -z / 3
    n = len(r)
    r["quality_rank"] = r["quality"].rank(method="min", ascending=False)
    q = math.ceil(n / 4.0)
    r["quality_label"] = np.where(r["quality_rank"] <= q, "shutdown", np.where(r["quality_rank"] > n - q, "target", "solid"))
    a = a.join(r[["quality_rank", "quality_label"]])
    a["n_ranked"] = n
    return a.reset_index()[cols]


def tier_of(label: str | None, rank) -> str:
    """The corner's quarter as the grade groups it: shutdown / solid / target, or unranked."""
    if label in LABEL_TONE and rank is not None and not (isinstance(rank, float) and math.isnan(rank)):
        return str(label)
    return "unranked"


# ================================================================================================ the grade
@dataclass
class Grade:
    group: str
    n: int
    games: int
    mean_miss: float | None
    lo: float | None
    hi: float | None
    beat: int
    beat_share: float | None
    extra: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"group": self.group, "n": self.n, "games": self.games, "mean_miss": _r(self.mean_miss), "lo": _r(self.lo),
                "hi": _r(self.hi), "beat": self.beat, "beat_share": _r(self.beat_share, 3), **self.extra}


def _r(x, k: int = 2):
    return None if x is None or (isinstance(x, float) and not math.isfinite(x)) else round(float(x), k)


def bootstrap_mean(miss: Sequence[float], clusters: Sequence[str] | None = None, n_boot: int = N_BOOT,
                   seed: int = SEED) -> tuple[float | None, float | None, float | None]:
    """(mean, 2.5th, 97.5th percentile) of the mean of ``miss``: resample the clusters (games) with replacement — every
    receiver-game of a drawn game comes along — else the rows. Fewer than 2 clusters: the mean, no interval."""
    m = np.asarray(miss, dtype=float)
    if m.size == 0:
        return None, None, None
    mean = float(m.mean())
    keys = np.asarray(clusters if clusters is not None else np.arange(m.size)).astype(str)
    uniq, inv = np.unique(keys, return_inverse=True)
    if uniq.size < 2:
        return mean, None, None
    s = np.bincount(inv, weights=m, minlength=uniq.size)
    c = np.bincount(inv, minlength=uniq.size).astype(float)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, uniq.size, size=(n_boot, uniq.size))
    means = s[idx].sum(axis=1) / c[idx].sum(axis=1)
    return mean, float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def bootstrap_diff(a_miss, a_games, b_miss, b_games, n_boot: int = N_BOOT, seed: int = SEED):
    """(mean A - mean B, interval): resample whole games (a game's rows of both groups come along together)."""
    a_miss, b_miss = np.asarray(a_miss, float), np.asarray(b_miss, float)
    if a_miss.size == 0 or b_miss.size == 0:
        return None, None, None
    keys = np.unique(np.concatenate([np.asarray(a_games).astype(str), np.asarray(b_games).astype(str)]))
    ia = np.searchsorted(keys, np.asarray(a_games).astype(str))
    ib = np.searchsorted(keys, np.asarray(b_games).astype(str))
    k = keys.size
    sa, ca = np.bincount(ia, weights=a_miss, minlength=k), np.bincount(ia, minlength=k).astype(float)
    sb, cb = np.bincount(ib, weights=b_miss, minlength=k), np.bincount(ib, minlength=k).astype(float)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, k, size=(n_boot, k))
    with np.errstate(divide="ignore", invalid="ignore"):
        d = sa[idx].sum(1) / ca[idx].sum(1) - sb[idx].sum(1) / cb[idx].sum(1)
    d = d[np.isfinite(d)]
    point = float(a_miss.mean() - b_miss.mean())
    if d.size < 10:
        return point, None, None
    return point, float(np.percentile(d, 2.5)), float(np.percentile(d, 97.5))


def grade(df: pd.DataFrame, group: str = "all") -> Grade:
    """One row of the grade over ``df`` (``miss``, ``game_id``): n, games, the mean miss with its game-clustered
    bootstrap interval, how many beat their projection (miss > 0)."""
    d = df[df["miss"].notna()]
    mean, lo, hi = bootstrap_mean(d["miss"].to_numpy(), d["game_id"].to_numpy())
    beat = int((d["miss"] > 0).sum())
    return Grade(group, len(d), int(d["game_id"].nunique()), mean, lo, hi, beat, beat / len(d) if len(d) else None)


def grade_by(df: pd.DataFrame, keys: Sequence[str], order: Mapping[str, Sequence] | None = None) -> list[dict]:
    """``grade`` per group of ``keys`` (a key's values in ``order`` first)."""
    out = []
    for k, g in df.groupby(list(keys), dropna=False):
        k = k if isinstance(k, tuple) else (k,)
        row = grade(g, " / ".join(str(x) for x in k)).as_dict()
        row.update(dict(zip(keys, k, strict=True)))
        out.append(row)
    if order:
        def pos(r):
            return tuple(list(order.get(c, [])).index(r[c]) if r[c] in order.get(c, []) else 99 for c in keys)
        out.sort(key=pos)
    return out


# ================================================================================================ the signals of a week
def defense_tone(rank_most, n: int = N_DEFENSES) -> str | None:
    """= research.defense_tone: rank 1 = gives up the most; the 10 (of 32) at each end are favorable / difficult."""
    if rank_most is None or (isinstance(rank_most, float) and math.isnan(rank_most)) or not n:
        return None
    e = max(1, round(n * TONE_EDGE))
    r = int(rank_most)
    return "favorable" if r <= e else "difficult" if r >= n + 1 - e else "neutral"


def _ordinal(k: int) -> str:
    return f"{k}{'th' if 10 <= k % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(k % 10, 'th')}"


def defense_words(rank_most, n: int = N_DEFENSES) -> str | None:
    if rank_most is None or (isinstance(rank_most, float) and math.isnan(rank_most)):
        return None
    r = int(rank_most)
    if r <= (n + 1) / 2:
        return "gives up the most points to the position" if r == 1 else f"gives up the {_ordinal(r)}-most points to the position"
    k = n + 1 - r
    return "gives up the fewest points to the position" if k == 1 else f"gives up the {_ordinal(k)}-fewest points to the position"


def corner_context(call: Mapping | None, rank_of: Mapping[str, Mapping]) -> dict | None:
    """A wide receiver's cornerback call in matchup_context's ``cb`` shape (tone, certainty, corner, corner_rank,
    shutdown, words) + ``tier`` and ``n``, from a mart_cb_matchups row and the as-of ranks (gsis -> quality_rank,
    quality_label, n_ranked). research.cb_meaning's tone rule: likely -> the first named corner's quarter; unclear ->
    a tone only when every named corner is ranked and they agree, else neutral; no ranked corner -> no tone."""
    if call is None or call.get("call_status") != "called":
        return None
    certainty = CERTAINTY.get(str(call.get("call_strength")), "unclear")
    ids = [call.get("likely_cover_gsis_id")]
    names = [call.get("likely_cover_name")]
    if certainty != "likely" and call.get("other_cover_gsis_id"):
        ids.append(call.get("other_cover_gsis_id"))
        names.append(call.get("other_cover_name"))
    named = []
    for g, nm in zip(ids, names, strict=True):
        r = rank_of.get(str(g)) if g else None
        rank = r.get("quality_rank") if r else None
        rank = None if rank is None or (isinstance(rank, float) and math.isnan(rank)) else int(rank)
        label = r.get("quality_label") if r and rank is not None else None
        named.append({"name": nm, "rank": rank, "label": label, "tone": LABEL_TONE.get(str(label)) if rank else None})
    first = named[0]
    n = next((int(rank_of[str(g)]["n_ranked"]) for g in ids if g and str(g) in rank_of), None)
    tones = {c["tone"] for c in named if c["tone"]}
    if not tones:
        tone = None
    elif certainty == "likely":
        tone = first["tone"]
    else:
        tone = next(iter(tones)) if len(tones) == 1 and all(c["tone"] for c in named) else "neutral"

    def tag(c):
        if c["rank"] is None:
            return "unranked"
        kind = {"shutdown": "a shutdown corner", "target": "easy to throw on", "solid": "an average corner"}[c["label"]]
        return f"{kind}, #{c['rank']}{f' of {n}' if n else ''}"
    who = str(first["name"] or "an unnamed corner")
    if certainty == "likely":
        words = f"{who} ({tag(first)}) is likely across from him"
    else:
        words = "either " + " or ".join(f"{c['name']} ({tag(c)})" for c in named) + " could be across from him"
    return {"tone": tone, "certainty": certainty, "corner": first["name"], "corner_rank": first["rank"],
            "shutdown": all(c["label"] == "shutdown" for c in named), "words": words,
            "tier": tier_of(first["label"], first["rank"]), "n": n}


def defense_rank_asof(dvp: pd.DataFrame, week: int) -> dict[tuple[str, str], tuple[int, int]]:
    """(defense, position) -> (rank, n) as the screen ranks them (mart_defense_vs_position_current: rank 1 = gives up
    the most points per game this season, among every defense with a game), from each defense's latest row of
    ``mart_defense_vs_position`` BEFORE ``week`` (a week's own games never enter its rank)."""
    d = dvp[(dvp["week"] < int(week)) & dvp["points_allowed_per_game_std"].notna()]
    if d.empty:
        return {}
    latest = d.sort_values("week").groupby(["defense", "position"]).tail(1).copy()
    latest["rank"] = latest.groupby("position")["points_allowed_per_game_std"].rank(method="min", ascending=False)
    latest["n"] = latest.groupby("position")["defense"].transform("count")
    return {(r.defense, r.position): (int(r.rank), int(r.n)) for r in latest.itertuples()}


def signals_for(position: str, defense_rank, corner: Mapping | None, role: Mapping | None, game: Mapping | None,
                weather: Mapping | None, n_defenses: int = N_DEFENSES) -> tuple[list[dict], bool, bool]:
    """The DFS screen's signals and its "Worth a look" verdicts for one player-week (``dfs.signals`` / ``dfs.worth``,
    the same functions the screen calls), from the as-of parts: (signals, worth under today's rule, worth under Wave
    I-N's rule — the cornerback counting)."""
    dt = defense_tone(defense_rank, n_defenses)
    dw = defense_words(defense_rank, n_defenses)
    matchup = {"defense": {"tone": dt, "words": dw, "tough_rank": None if dt is None else n_defenses + 1 - int(defense_rank),
                           "n_ranked": n_defenses if dt else None},
               "cb": corner}
    sig = D.signals(position, matchup, role, game, weather)
    return sig, D.worth(sig)[0], D.worth(sig, ignore=())[0]


# ================================================================================================ the database
WEEK_SQL = """select f.gsis_id, f.position, f.team, f.opponent, f.spread_line, f.total_line,
                     coalesce(p.player_name, f.gsis_id) as player_name
              from analytics.mart_player_week_features f
              left join analytics.dim_player p on p.gsis_id = f.gsis_id
              where f.season = %s and f.week = %s and f.position in ('QB', 'RB', 'WR', 'TE')"""
GAMES_SQL = """select game_id, week, home_team, away_team, kickoff_at, spread_line, total_line
               from analytics.dim_game where season = %s and season_type = 'REG'"""
CALLS_SQL = """select gsis_id, week, game_id, opponent, call_status, call_strength, likely_cover_gsis_id, likely_cover_name,
                      other_cover_gsis_id, other_cover_name, cover_rank, cover_label
               from analytics.mart_cb_matchups where season = %s and position = 'WR'"""
COVERAGE_SQL = """select gsis_id, game_id, season, week, team, opponent, position, snap_position, coverage_snaps::float8 as coverage_snaps,
                         def_targets, def_completions_allowed, def_yards_allowed, def_receiving_td_allowed, def_ints
                  from intermediate.int_defender_game_coverage_snaps
                  where season_type = 'REG' and season between %s and %s"""
OFF_SQL = """select game_id, season, week, team as offense, sum(coalesce(targets, 0))::float8 as targets,
                    sum(coalesce(receiving_yards, 0))::float8 as yards
             from analytics.fct_player_game
             where season_type = 'REG' and position in ('WR', 'TE') and season between %s and %s
             group by 1, 2, 3, 4"""
ROLE_SQL = """select gsis_id, position, week, targets, team_targets, carries, team_carries, offense_snaps, offense_snap_pct,
                     routes, team_dropbacks_with_participation
              from analytics.fct_player_game
              where season = %s and season_type = 'REG' and week < %s and played and position in ('RB', 'WR', 'TE')"""
WX_SQL = """select game_id, wx_source, wx_dome, wx_wind_mph::float8 as wx_wind_mph, wx_precip_in::float8 as wx_precip_in,
                   wx_temp_f::float8 as wx_temp_f, wx_snow, forecast_wind_mph, forecast_precip_in, forecast_temp_f
            from intermediate.int_game_weather where season = %s and week = %s"""
DVP_SQL = """select defense, position, week, points_allowed_per_game_std::float8 as points_allowed_per_game_std
             from analytics.mart_defense_vs_position where season = %s"""
OOF_SQL = """select gsis_id, week, position, proj_points, actual, model_version
             from ops.calibration_oof where season = %s and league_id = %s"""
PROJ_SQL = """select gsis_id, week, position, proj_points, model_version, frozen_source
              from ops.projections
              where season = %s and league_id = %s and position in ('QB', 'RB', 'WR', 'TE') and model_version not like 'kd%%'"""
ACTUAL_SQL = """select gsis_id, week, position, game_id, played, targets, receptions, receiving_yards, receiving_tds, carries,
                       rushing_yards, rushing_tds, attempts, passing_yards, passing_tds, passing_interceptions, fumbles_lost_total
                from analytics.fct_player_game
                where season = %s and season_type = 'REG' and position in ('QB', 'RB', 'WR', 'TE')"""
SCORING_SQL = "select scoring_settings from analytics_seeds.reference_scorings where name = %s"


def _df(conn, sql: str, params: tuple = ()) -> pd.DataFrame:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        cols = [c.name for c in cur.description]
        return pd.DataFrame(cur.fetchall(), columns=cols)


def _num(df: pd.DataFrame, cols: Iterable[str]) -> pd.DataFrame:
    for c in cols:
        if c in df:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def _scoring(conn) -> dict[str, float]:
    with conn.cursor() as cur:
        cur.execute(SCORING_SQL, (SCORING_SEED,))
        row = cur.fetchone()
    s = row[0] if row else None
    s = json.loads(s) if isinstance(s, str) else dict(s or {})
    return {k: float(v) for k, v in s.items() if v is not None}


def actual_points(conn, season: int) -> pd.DataFrame:
    """gsis_id, week, game_id, played, actual (Half PPR, priced from the stat line exactly as the projection's
    ``actual`` is: the projected components, no 2-point conversions)."""
    from .projections import ALL_COMPONENTS, price
    a = _num(_df(conn, ACTUAL_SQL, (int(season),)), ALL_COMPONENTS)
    if a.empty:
        return a.assign(actual=[])
    out = a[["gsis_id", "week", "position"]].copy()
    for c in ALL_COMPONENTS:
        out[f"out_{c}"] = a[c].fillna(0.0)
    a["actual"] = price(out, _scoring(conn), "out_")
    a.loc[~a["played"].astype(bool), "actual"] = np.nan
    return a[["gsis_id", "week", "game_id", "played", "actual"]]


@dataclass
class SeasonInputs:
    season: int
    games: pd.DataFrame
    calls: pd.DataFrame
    cov: pd.DataFrame
    off: pd.DataFrame
    proj: pd.DataFrame          # gsis_id, week, proj_points, model_version, source
    actual: pd.DataFrame
    dvp: pd.DataFrame | None = None
    role_games: pd.DataFrame | None = None
    weeks: dict = field(default_factory=dict)
    trend_games: pd.DataFrame | None = None       # ---- IP-3: the season's played QB-TE games (load_trend_games)
    qb_changed: dict = field(default_factory=dict)


def load_season(conn, season: int) -> SeasonInputs:
    s = int(season)
    games = _df(conn, GAMES_SQL, (s,))
    calls = _df(conn, CALLS_SQL, (s,))
    cov = _num(_df(conn, COVERAGE_SQL, (s - 1, s)), ["coverage_snaps", "def_targets", "def_completions_allowed",
                                                       "def_yards_allowed", "def_receiving_td_allowed", "def_ints"])
    off = _num(_df(conn, OFF_SQL, (s - 2, s)), ["targets", "yards"])
    oof = _df(conn, OOF_SQL, (s, ANCHOR_LEAGUE))
    if not oof.empty:
        proj = oof.rename(columns={"actual": "oof_actual"}).assign(source="walk-forward")
    else:
        proj = _df(conn, PROJ_SQL, (s, ANCHOR_LEAGUE))
        proj = proj.assign(source=proj["frozen_source"].fillna("live")).drop(columns=["frozen_source"])
    proj = _num(proj, ["proj_points"])
    dvp = _num(_df(conn, DVP_SQL, (s,)), ["points_allowed_per_game_std", "week"])
    act = actual_points(conn, s)
    tg, qbc = load_trend_games(conn, s, act)          # ---- IP-3
    return SeasonInputs(s, games, calls, cov, off, proj, act, dvp=dvp, trend_games=tg, qb_changed=qbc)


def first_kickoffs(games: pd.DataFrame) -> dict[int, datetime]:
    g = games.dropna(subset=["kickoff_at"])
    return {int(w): k for w, k in g.groupby("week")["kickoff_at"].min().items()}


def _role(conn, season: int, week: int, routes: bool) -> dict[str, dict | None]:
    g = _df(conn, ROLE_SQL, (int(season), int(week)))
    if g.empty:
        return {}
    g = _num(g, ["targets", "team_targets", "carries", "team_carries", "offense_snaps", "offense_snap_pct", "routes",
                 "team_dropbacks_with_participation"])
    pct = g["offense_snap_pct"]
    g["team_snaps"] = (g["offense_snaps"] / pct).where(pct > 0).round()
    if not routes:                  # the live screen never had the participation file during the season
        g["routes"] = np.nan
    return {str(k): D.role_trend(v, str(v["position"].iloc[-1])) for k, v in g.groupby("gsis_id")}


def _weather(conn, season: int, week: int, kept_forecast_only: bool) -> dict[str, dict]:
    """game_id -> the weather_flag inputs. A rebuilt week reads the last forecast kept from before kickoff (else none);
    the live freeze reads int_game_weather as the screen does."""
    try:
        wx = _df(conn, WX_SQL, (int(season), int(week)))
    except Exception:  # noqa: BLE001 - no weather model on this database: no weather signal
        conn.rollback()
        return {}
    out = {}
    for r in wx.to_dict("records"):
        if kept_forecast_only:
            if r.get("wx_source") == "dome":
                continue
            if r.get("forecast_wind_mph") is None and r.get("forecast_temp_f") is None:
                continue
            out[r["game_id"]] = {"wx_source": "forecast", "wx_dome": 0, "wx_wind_mph": r.get("forecast_wind_mph"),
                                 "wx_precip_in": r.get("forecast_precip_in"), "wx_temp_f": r.get("forecast_temp_f"),
                                 "wx_snow": None}
        else:
            out[r["game_id"]] = r
    return out


def _f(v) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def rebuild_week(conn, si: SeasonInputs, week: int, *, live: bool = False) -> pd.DataFrame:
    """Every QB / RB / WR / TE of ``week`` with a game and a signal: the signals as the DFS screen shows them (from the
    as-of inputs; ``live``: the freeze of the next week, whose marts are as-of by construction), Worth a look, listed
    (the top ``LIST_TOP`` per position by projection), the Half PPR projection, the actual where the game is final."""
    w = int(week)
    players = _num(_df(conn, WEEK_SQL, (si.season, w)), ["spread_line", "total_line"])
    if players.empty:
        return pd.DataFrame(columns=COLUMNS)
    g = si.games[si.games["week"] == w]
    home = g.rename(columns={"home_team": "team", "away_team": "opp"}).assign(is_home=True)
    away = g.rename(columns={"away_team": "team", "home_team": "opp"}).assign(is_home=False)
    sides = pd.concat([home, away], ignore_index=True)[["team", "game_id", "is_home", "kickoff_at", "spread_line", "total_line"]]
    players = players.drop(columns=["spread_line", "total_line"]).merge(sides, on="team", how="inner")
    # the corner's rank from the games before the week (for the next week to kick off this IS the mart's rank)
    asof = cb_rank_asof(si.cov, si.off, si.season, w)
    rank_of = {str(r["gsis_id"]): r for r in asof.to_dict("records")}
    calls = {str(r["gsis_id"]): r for r in si.calls[si.calls["week"] == w].to_dict("records")}
    dranks = defense_rank_asof(si.dvp, w) if si.dvp is not None and not si.dvp.empty else {}
    role = _role(conn, si.season, w, routes=live)
    tw = trend_asof_week(si.trend_games, w, si.qb_changed)      # ---- IP-3: Trends' tag before the week
    wx = _weather(conn, si.season, w, kept_forecast_only=not live)
    pj = si.proj[si.proj["week"] == w].drop_duplicates("gsis_id").set_index("gsis_id")
    act = si.actual[si.actual["week"] == w].drop_duplicates("gsis_id").set_index("gsis_id")
    rows = []
    for p in players.to_dict("records"):
        gid, pos = str(p["gsis_id"]), str(p["position"])
        c = corner_context(calls.get(gid), rank_of) if pos == "WR" else None
        rl = role.get(gid)
        game = D.game_environment(p["team"], _f(p.get("total_line")), _f(p.get("spread_line")), bool(p["is_home"]))
        wr = wx.get(p["game_id"])
        wf = None if wr is None else D.weather_flag(wr.get("wx_source"), wr.get("wx_dome"), _f(wr.get("wx_wind_mph")),
                                                    _f(wr.get("wx_precip_in")), _f(wr.get("wx_temp_f")),
                                                    wr.get("wx_snow"), pos)
        dr, dn = dranks.get((p["opponent"], pos), (None, N_DEFENSES))
        sig, ok, ok_corner = signals_for(pos, dr, c, rl, game, wf, dn)
        if not sig:
            continue
        tone = {s["signal"]: s.get("tone") for s in sig}
        proj = pj.loc[gid] if gid in pj.index else None
        a = act.loc[gid] if gid in act.index else None
        actual = None
        if proj is not None and "oof_actual" in proj.index and _f(proj.get("oof_actual")) is not None:
            actual = _f(proj.get("oof_actual"))
        elif a is not None:
            actual = _f(a.get("actual"))
        pp = None if proj is None else _f(proj.get("proj_points"))
        rows.append({
            "season": si.season, "week": w, "gsis_id": gid, "player_name": p.get("player_name"), "position": pos,
            "team": p["team"], "opponent": p["opponent"], "game_id": p["game_id"], "kickoff_at": p["kickoff_at"],
            "proj_points": pp, "model_version": None if proj is None else proj.get("model_version"),
            "proj_source": None if proj is None else proj.get("source"),
            "signals": [{k: s.get(k) for k in ("signal", "tone", "words", "in_projection")} for s in sig],
            "defense_tone": tone.get("defense"), "corner_certainty": c["certainty"] if c else None,
            "corner_tier": c["tier"] if c else None, "corner_rank": c["corner_rank"] if c else None,
            "corner_n": c["n"] if c else None, "corner_tone": c["tone"] if c else None,
            "role_trend": rl.get("trend") if rl else None, "game_tone": tone.get("game"),
            "weather_tone": tone.get("weather"), "worth": bool(ok), "worth_corner": bool(ok_corner),
            "worth_two": worth_two(sig),
            "actual_points": actual,
            **trend_fields(tw.get(gid)),
        })
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out = out[out["proj_points"].notna()].copy()          # the DFS board lists priced players only
    if out.empty:
        return out
    for flag, listed in (("worth", "listed"), ("worth_corner", "listed_corner")):
        out[listed] = False
        for _pos, grp in out[out[flag]].groupby("position"):
            top = grp.assign(_p=grp["proj_points"].fillna(-1e9)).sort_values(["_p", "gsis_id"], ascending=[False, True]).head(LIST_TOP)
            out.loc[top.index, listed] = True
    out["miss"] = out["actual_points"] - out["proj_points"]
    return out


# ================================================================================================ the grade of the past
def history(conn, seasons: Iterable[int], weeks: Mapping[int, Iterable[int]] | None = None) -> pd.DataFrame:
    """Every rebuilt player-week of ``seasons`` (the as-of inputs), with the actual where the game is final."""
    frames = []
    for s in seasons:
        si = load_season(conn, int(s))
        ws = sorted(set(weeks.get(int(s), ())) if weeks else set(si.games["week"].dropna().astype(int)))
        for w in ws:
            f = rebuild_week(conn, si, w)
            if not f.empty:
                frames.append(f)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _vs(a: pd.DataFrame, b: pd.DataFrame) -> dict:
    diff, lo, hi = bootstrap_diff(a["miss"], a["game_id"], b["miss"], b["game_id"])
    bs = float((b["miss"] > 0).mean()) if len(b) else None
    return {"vs_rest": _r(diff), "vs_rest_lo": _r(lo), "vs_rest_hi": _r(hi), "rest_n": len(b), "rest_beat_share": _r(bs, 3)}


def grade_corners(h: pd.DataFrame) -> dict:
    """The corner calls: every receiver-game with a call, a projection and a final game, by tier and by certainty x
    tier; each against the other called receivers (``vs_rest``: the difference of the mean misses, game-clustered
    interval — the projection's own bias at WR cancels)."""
    d = h[(h["position"] == "WR") & h["corner_tier"].notna() & h["miss"].notna() & h["proj_points"].notna()].copy()
    allwr = h[(h["position"] == "WR") & h["miss"].notna() & h["proj_points"].notna()]
    out = {"all_wr": grade(allwr, "every WR with a projection").as_dict(),
           "called": grade(d, "every called WR").as_dict(),
           "by_tier": grade_by(d, ["corner_tier"], {"corner_tier": TIERS}),
           "by_tier_certainty": grade_by(d, ["corner_certainty", "corner_tier"],
                                         {"corner_certainty": ("likely", "unclear"), "corner_tier": TIERS})}
    for row in out["by_tier_certainty"] + out["by_tier"]:
        mask = d["corner_tier"] == row["corner_tier"]
        if "corner_certainty" in row:
            mask &= d["corner_certainty"] == row["corner_certainty"]
        row.update(_vs(d[mask], d[~mask]))
    return out


def grade_worth(h: pd.DataFrame) -> dict:
    """"Worth a look": the listed players (top 8 per position) vs everyone else at the position (and vs everyone else
    projected 6+ points), under Wave I-N's rule (the cornerback counting: ``listed_corner``) and today's (``listed``)."""
    d = h[h["miss"].notna() & h["proj_points"].notna()].copy()
    out: dict = {}
    if "worth_two" not in d:
        d["worth_two"] = False
    for label, flag, listed in (("listed_corner", "worth_corner", "listed_corner"), ("flagged_corner", "worth_corner", "worth_corner"),
                                ("listed", "worth", "listed"), ("two", "worth_two", "worth_two")):
        a = d[d[listed].fillna(False).astype(bool)]
        row = grade(a, label).as_dict()
        if not a.empty:
            rest = d[~d[flag].fillna(False).astype(bool) & d["position"].isin(a["position"].unique())]
            row.update(_vs(a, rest))
            r6 = _vs(a, rest[rest["proj_points"] >= 6])
            row.update({f"{k}_6": v for k, v in r6.items()})
            row["positions"] = sorted(a["position"].unique().tolist())
        out[label] = row
    f = d[d["worth_corner"].fillna(False).astype(bool)]
    out["reasons"] = {
        "corner_easy": int(((f["corner_tier"] == "target") & (f["corner_certainty"] == "likely")).sum()),
        "defense_favorable": int((f["defense_tone"] == "favorable").sum()),
        "role_up": int((f["role_trend"] == "up").sum()), "game_favorable": int((f["game_tone"] == "favorable").sum())}
    return out


def span_words(h: pd.DataFrame) -> str | None:
    """'2025 and 2026 weeks 1-4': the graded weeks in words (a whole season by its year)."""
    d = h[h["miss"].notna()]
    if d.empty:
        return None
    parts = []
    for s, g in d.groupby("season"):
        ws = sorted(set(int(w) for w in g["week"]))
        parts.append(str(int(s)) if ws[0] == 1 and ws[-1] >= 17 else f"{int(s)} week{'s' if len(ws) > 1 else ''} "
                     f"{ws[0]}{f'–{ws[-1]}' if len(ws) > 1 else ''}")
    return " and ".join(parts)


def verdict(lo: float | None, hi: float | None) -> str:
    if lo is None or hi is None:
        return "too few games to tell"
    if lo > 0:
        return "more than chance would give"
    if hi < 0:
        return "less than chance would give"
    return "not distinguishable from chance"


def no_effect(row: Mapping | None) -> bool:
    """A grade row whose interval against the rest holds 0 (or has none): no measurable effect."""
    if not row or row.get("vs_rest") is None:
        return True
    lo, hi = row.get("vs_rest_lo"), row.get("vs_rest_hi")
    return lo is None or hi is None or lo <= 0 <= hi


def _signed(x: float) -> str:
    """+0.8 / −1.3 (a true minus sign) / 0.0."""
    v = round(float(x), 1)
    return "0.0" if v == 0 else f"{'+' if v > 0 else '−'}{abs(v):.1f}"


def _pts(x: float) -> str:
    return f"{abs(x):.1f} point{'' if round(abs(x), 1) == 1 else 's'}"


def corner_sentence(rows: Sequence[Mapping], span: str | None) -> str | None:
    """How corner calls have done, one sentence (the likely calls: shutdown and easy to throw on)."""
    by = {(r.get("corner_certainty"), r.get("corner_tier")): r for r in rows}
    sh, ez = by.get(("likely", "shutdown")), by.get(("likely", "target"))
    if not sh or not ez or not sh.get("n") or not ez.get("n") or sh.get("vs_rest") is None or ez.get("vs_rest") is None:
        return None
    both = no_effect(sh) and no_effect(ez)

    def part(r, full: bool):
        v = r["vs_rest"]
        ci = f"{_signed(r['vs_rest_lo'])} to {_signed(r['vs_rest_hi'])}; " if r.get("vs_rest_lo") is not None else ""
        where = ("level with them" if round(v, 1) == 0 else f"{_pts(v)} {'above' if v > 0 else 'below'}")
        return f"{where}{' the other receivers against their projection' if full else ''} ({ci}{r['n']} games)"
    tail = "no measurable effect either way" if both else "a measurable difference: see the table"
    return (f"Graded on {span} ({SCORING_WORDS}): receivers with a likely shutdown corner finished {part(sh, True)}, "
            f"those with a likely easy one {part(ez, False)} — {tail}.")


def tier_sentence(r: Mapping | None) -> str | None:
    """The chip's graded words for one certainty x tier: "Graded: no measurable effect (−0.4 points against the
    projection vs other receivers, −1.4 to +0.7, 99 games)."."""
    if not r or not r.get("n") or r.get("vs_rest") is None:
        return None
    ci = f", {_signed(r['vs_rest_lo'])} to {_signed(r['vs_rest_hi'])}" if r.get("vs_rest_lo") is not None else ""
    lead = "no measurable effect" if no_effect(r) else ("measurably above" if r["vs_rest"] > 0 else "measurably below")
    return f"Graded: {lead} ({_signed(r['vs_rest'])} points against the projection vs other receivers{ci}, {r['n']} games)."


def worth_sentence(r: Mapping | None, span: str | None, corner: bool = True) -> str | None:
    """How "Worth a look" has done, one sentence: "Since 2026 week 5, listed players scored above their projection in
    15 of 38 games (39%; everyone else at the position 35%) and finished 0.7 points better than everyone else against it
    (−1.1 to +2.6) — not distinguishable from chance."."""
    if not r or not r.get("n") or r.get("vs_rest") is None:
        return None
    v = r["vs_rest"]
    ci = f" ({_signed(r['vs_rest_lo'])} to {_signed(r['vs_rest_hi'])})" if r.get("vs_rest_lo") is not None else ""
    base = f"; everyone else at the position {r['rest_beat_share']:.0%}" if r.get("rest_beat_share") is not None else ""
    # the old rule's grade: rebuilt weeks (before 2026 week 5) and frozen ones alike; the date never goes stale
    lead = (f"Graded on {span} with the cornerback counting (the rule until 6 October 2026), listed players"
            if corner else f"Since {span}, listed players")
    return (f"{lead} scored above their projection in {r['beat']} of {r['n']} games ({r['beat'] / r['n']:.0%}{base}) and finished "
            f"{_pts(v)} {'better' if v >= 0 else 'worse'} than everyone else against it{ci} — "
            f"{verdict(r.get('vs_rest_lo'), r.get('vs_rest_hi'))}.")


def worth_off_line(r: Mapping | None, span: str | None) -> str | None:
    """The DFS screen's one line now that "Worth a look" is off (PO, Wave I-O fix round), every number from the grade:
    "We tried a "Worth a look" list and graded it on 2025 and 2026 weeks 1–4: it listed a receiver 37 times (in 29
    games), and they finished 0.7 points better than everyone else against their projection (−1.1 to +2.7) — not
    distinguishable from chance. It is off until a rule earns its place in the record; the context chips stay beside
    each player." None without a graded listing."""
    if not r or not r.get("n") or r.get("vs_rest") is None or not span:
        return None
    v = r["vs_rest"]
    ci = f" ({_signed(r['vs_rest_lo'])} to {_signed(r['vs_rest_hi'])})" if r.get("vs_rest_lo") is not None else ""
    pos = r.get("positions") or []
    who = "a receiver" if pos == ["WR"] else "a player"
    v_words = verdict(r.get("vs_rest_lo"), r.get("vs_rest_hi"))
    games = f" (in {r['games']} games)" if r.get("games") else ""
    tail = ("It is off until a rule earns its place in the record" if v_words != "more than chance would give"
            else "It stays off until the record has more weeks")
    return (f"We tried a \"Worth a look\" list and graded it on {span}: it listed {who} {r['n']} times{games}, and they "
            f"finished {_pts(v)} {'better' if v >= 0 else 'worse'} than everyone else against their projection{ci} — "
            f"{v_words}. {tail}; the context chips stay beside each player.")


# ---- the stored grade (ops.context_grade: what the site reads; recomputed from the record every run)
GRADE_COLUMNS = ["kind", "grp", "corner_certainty", "corner_tier", "n", "games", "mean_miss", "lo", "hi", "beat",
                 "beat_share", "vs_rest", "vs_rest_lo", "vs_rest_hi", "rest_n", "rest_beat_share", "span", "scoring",
                 "words", "graded_at"]
GRADE_DDL = """create table if not exists ops.context_grade (
        kind text, grp text, corner_certainty text, corner_tier text, n integer, games integer, mean_miss double precision,
        lo double precision, hi double precision, beat integer, beat_share double precision, vs_rest double precision,
        vs_rest_lo double precision, vs_rest_hi double precision, rest_n integer, rest_beat_share double precision,
        span text, scoring text, words text, graded_at timestamptz)"""
RECORD_GRADE_SQL = """select season, week, game_id, position, proj_points, miss, corner_certainty, corner_tier, defense_tone,
                             role_trend, game_tone, worth, listed, worth_corner, listed_corner, worth_two, record_source,
                             gsis_id, actual_points, trend_games, trend_ppg, trend_gap, trend_tag, trend_reason
                      from ops.context_record where miss is not null and proj_points is not null"""


def grade_rows(h: pd.DataFrame, graded_at: datetime | None = None) -> list[dict]:
    """The grade of the record as rows of ``ops.context_grade`` (kind ``corner`` per certainty x tier, ``corner_all``
    per tier, ``worth`` per rule, ``summary`` the two sentences)."""
    span = span_words(h)
    c = grade_corners(h)
    w = grade_worth(h)
    out = []

    def put(kind, grp, r, words=None):
        out.append({**{k: r.get(k) for k in GRADE_COLUMNS if k in r}, "kind": kind, "grp": grp, "span": span,
                    "scoring": SCORING_WORDS, "words": words, "graded_at": graded_at})
    for r in c["by_tier_certainty"]:
        put("corner", f"{r['corner_certainty']}/{r['corner_tier']}", r, tier_sentence(r))
    for r in c["by_tier"]:
        put("corner_all", r["corner_tier"], r)
    put("corner_all", "called", c["called"])
    put("corner_all", "every_wr", c["all_wr"])
    put("summary", "corner", {"n": c["called"]["n"]}, corner_sentence(c["by_tier_certainty"], span))
    for k in ("listed_corner", "flagged_corner", "listed"):
        put("worth", k, w[k])
    put("worth", "two", w["two"])
    lc, today = w["listed_corner"], w["listed"]
    words = worth_sentence(today, span, corner=False) if today.get("n") else worth_sentence(lc, span, corner=True)
    put("summary", "worth", {"n": today.get("n") or lc.get("n") or 0}, words)
    put("summary", "worth_off", {"n": lc.get("n") or 0}, worth_off_line(lc, span))
    # ---- IO-1 fix round: out of sample — only the weeks frozen before kickoff (2026 week 5 on), nothing rebuilt
    live = h[h["record_source"] == "kickoff"] if "record_source" in h else h.iloc[0:0]
    if not live.empty:
        lspan = span_words(live)
        lw = grade_worth(live)
        for k in ("listed_corner", "two"):
            out.append({**{c_: lw[k].get(c_) for c_ in GRADE_COLUMNS if c_ in lw[k]}, "kind": "worth_live", "grp": k,
                        "span": lspan, "scoring": SCORING_WORDS, "words": None, "graded_at": graded_at})
        lc_ = grade_corners(live)
        for r in lc_["by_tier_certainty"]:
            out.append({**{c_: r.get(c_) for c_ in GRADE_COLUMNS if c_ in r}, "kind": "corner_live",
                        "grp": f"{r['corner_certainty']}/{r['corner_tier']}", "span": lspan, "scoring": SCORING_WORDS,
                        "words": tier_sentence(r), "graded_at": graded_at})
    out += trend_grade_rows(h, graded_at)             # ---- IP-3: Trends' tag and the role trend, graded
    return out


def write_grade(conn, now: datetime) -> int:
    """Replace ``ops.context_grade`` with the grade of ``ops.context_record`` as it stands."""
    h = _df(conn, RECORD_GRADE_SQL)
    h = _num(h, ["proj_points", "miss", "actual_points", "trend_ppg", "trend_gap", "trend_games"])
    rows = grade_rows(h, now) if not h.empty else []
    with conn.cursor() as cur:
        cur.execute(GRADE_DDL)
        cur.execute("delete from ops.context_grade")
        if rows:
            with cur.copy(f"copy ops.context_grade ({', '.join(GRADE_COLUMNS)}) from stdin") as cp:
                for r in rows:
                    cp.write_row([None if (isinstance(r.get(k), float) and not math.isfinite(r[k])) else r.get(k)
                                  for k in GRADE_COLUMNS])
    conn.commit()
    return len(rows)


def validate_asof_rank(conn, season: int) -> dict:
    """At the end of ``season`` the as-of rank must be the mart's (the same games): the share of corners whose rank
    and quarter agree with mart_cb_rankings' 'two_seasons' window."""
    si = load_season(conn, season)
    mine = cb_rank_asof(si.cov, si.off, season, 99)
    mart = _df(conn, """select gsis_id, quality_rank, quality_label from analytics.mart_cb_rankings
                        where season = %s and window_label = 'two_seasons' and is_ranked""", (int(season),))
    m = mine[mine["is_ranked"]].merge(mart, on="gsis_id", how="outer", suffixes=("", "_mart"))
    same_rank = int((m["quality_rank"] == pd.to_numeric(m["quality_rank_mart"])).sum())
    same_label = int((m["quality_label"] == m["quality_label_mart"]).sum())
    return {"season": int(season), "ranked_mine": int(mine["is_ranked"].sum()), "ranked_mart": len(mart),
            "same_rank": same_rank, "same_label": same_label}


def lookahead(conn, season: int, weeks: Iterable[int]) -> dict:
    """How often the mart's quarter of a called corner differs from the as-of quarter (the look-ahead's size)."""
    si = load_season(conn, season)
    n = differ = 0
    for w in weeks:
        asof = {str(r["gsis_id"]): r for r in cb_rank_asof(si.cov, si.off, season, w).to_dict("records")}
        c = si.calls[(si.calls["week"] == w) & (si.calls["call_status"] == "called")]
        for r in c.to_dict("records"):
            a = asof.get(str(r["likely_cover_gsis_id"]))
            mine = tier_of(a.get("quality_label") if a else None, a.get("quality_rank") if a else None)
            mart = tier_of(r.get("cover_label"), r.get("cover_rank"))
            n += 1
            differ += int(mine != mart)
    return {"season": int(season), "calls": n, "tier_differs": differ}


# ================================================================================================ the record
def record_plan(stored: Iterable[int], kickoffs: Mapping[int, datetime], now: datetime) -> dict[int, str]:
    """week -> ``write`` (the next week to kick off), ``keep`` (kicked off, stored), ``reconstruct`` (kicked off,
    nothing stored) — ``lineup.record_plan``'s rule for one season."""
    have = {int(w) for w in stored}
    plan: dict[int, str] = {}
    started = sorted(w for w, k in kickoffs.items() if k <= now)
    ahead = sorted(w for w, k in kickoffs.items() if k > now)
    for w in started:
        plan[w] = "keep" if w in have else "reconstruct"
    if ahead:
        plan[ahead[0]] = "write"
    return plan


def _rows_for_db(f: pd.DataFrame, source: str, as_of: datetime, first_kickoff: datetime | None, run_at: datetime,
                 graded_at: datetime | None) -> list[list]:
    out = []
    for r in f.to_dict("records"):
        d = {**r, "run_at": run_at, "as_of": as_of, "first_kickoff_at": first_kickoff, "record_source": source,
             "scoring": SCORING_WORDS, "signals": json.dumps(r.get("signals") or []),
             "actual_points": _f(r.get("actual_points")) if source == "reconstructed" else None,
             "miss": _f(r.get("miss")) if source == "reconstructed" else None,
             "graded_at": graded_at if source == "reconstructed" and _f(r.get("actual_points")) is not None else None}
        for k in ("corner_rank", "corner_n", "trend_games"):
            d[k] = None if d.get(k) is None or (isinstance(d[k], float) and math.isnan(d[k])) else int(d[k])
        d["proj_points"] = _f(d.get("proj_points"))
        out.append([None if isinstance(d.get(c), float) and not math.isfinite(d[c]) else d.get(c) for c in COLUMNS])
    return out


@dataclass
class RecordRun:
    season: int
    plan: dict[int, str]
    written: list[int]
    reconstructed: list[int]
    rows: int
    graded: int


def write_record(conn, season: int | None = None, now: datetime | None = None, first_season: int = FIRST_SEASON) -> list[RecordRun]:
    """Freeze, rebuild and grade ``ops.context_record`` (one transaction per season). Idempotent: a week that has
    kicked off and is stored is never rewritten (only its ``actual_points`` / ``miss`` filled once the game is final)."""
    from . import clock
    now = now or clock.now()
    with conn.cursor() as cur:
        cur.execute(DDL)
        cur.execute(TWO_BACKFILL_SQL, (TWO_MIN_FAVOURABLE,))
    conn.commit()
    backfill_trend(conn)                         # ---- IP-3: rows written before the trend columns existed
    with conn.cursor() as cur:
        if season is None:
            cur.execute("select max(season) from analytics.dim_game where season_type = 'REG' and kickoff_at <= %s", (now,))
            season = cur.fetchone()[0]
    conn.commit()
    if season is None:
        return []
    runs = []
    for s in range(int(first_season), int(season) + 1):
        runs.append(_write_season(conn, s, now))
    return runs


def _write_season(conn, season: int, now: datetime) -> RecordRun:
    si = load_season(conn, season)
    kick = first_kickoffs(si.games)
    with conn.cursor() as cur:
        cur.execute("select distinct week from ops.context_record where season = %s", (season,))
        stored = [int(r[0]) for r in cur.fetchall()]
    plan = record_plan(stored, kick, now)
    written, rebuilt, rows = [], [], []
    for w, act in sorted(plan.items()):
        if act == "write":
            f = rebuild_week(conn, si, w, live=True)
            if not f.empty:
                rows += _rows_for_db(f, "kickoff", now, kick.get(w), now, None)
                written.append(w)
        elif act == "reconstruct":
            f = rebuild_week(conn, si, w)
            if not f.empty:
                rows += _rows_for_db(f, "reconstructed", kick[w] - timedelta(seconds=1), kick.get(w), now, now)
                rebuilt.append(w)
    graded = 0
    with conn.cursor() as cur:
        if written:
            cur.execute("delete from ops.context_record where season = %s and week = any(%s) and record_source = 'kickoff' "
                        "and first_kickoff_at > %s", (season, written, now))
        if rows:
            with cur.copy(f"copy ops.context_record ({', '.join(COLUMNS)}) from stdin") as cp:
                for r in rows:
                    cp.write_row(r)
        # grade the frozen rows whose games are final (once; a stat correction later is not chased)
        a = si.actual[si.actual["actual"].notna()]
        if not a.empty:
            cur.execute("""create temp table if not exists _ctx_actual (gsis_id text, week integer, actual double precision)
                           on commit drop""")
            with cur.copy("copy _ctx_actual (gsis_id, week, actual) from stdin") as cp:
                for r in a[["gsis_id", "week", "actual"]].itertuples(index=False):
                    cp.write_row([r.gsis_id, int(r.week), float(r.actual)])
            cur.execute("""update ops.context_record c set actual_points = a.actual, miss = a.actual - c.proj_points,
                                  graded_at = %s
                           from _ctx_actual a
                           where c.season = %s and c.gsis_id = a.gsis_id and c.week = a.week and c.actual_points is null
                             and c.first_kickoff_at <= %s""", (now, season, now))
            graded = cur.rowcount
    conn.commit()
    log.info("context record %s: written %s, reconstructed %s, %s rows, %s graded", season, written or "none",
             rebuilt or "none", len(rows), graded)
    return RecordRun(season, plan, written, rebuilt, len(rows), graded)


def run(season: int | None = None) -> tuple[list[RecordRun], int]:
    """``league-lab context-record``: freeze / rebuild / grade the record, then replace the stored grade."""
    import psycopg

    from . import clock
    from .config import get_settings
    now = clock.now()
    with psycopg.connect(get_settings().pipeline_dsn(), autocommit=False) as conn:
        runs = write_record(conn, season, now=now)
        return runs, write_grade(conn, now)


# ================================================================================================ IP-3: Trends and the role
# ---- IP-3 (Wave I-P): grade what Trends ("below / above expectation") and the role chips ("role up / down") claim.
#
# Trends' gap = his points per game minus his expected points per game (what his targets and carries are usually worth,
# ffverse's per-game expected stats priced in the scoring) over the season's games so far (mart_league_player_season's
# ``diff_per_game``; the screen calls it below / above expectation past ``TREND_NEAR`` = research.NEAR = 0.5). The mart
# keeps only the season as it stands now, so a past week's tag is never stored anywhere: it is rebuilt here from the
# games BEFORE the week (``asof_trend``), in Half PPR, with the reason the screen gives (``trend_reason`` = the
# category of research.trend_cause). The role trend is ``role_trend.role_trend`` on the games before the week (as
# context_record already rebuilds it; routes per dropback left out). Each player-week is then followed over his next 1,
# 2 and 4 games played: (a) his points against the projection made before each game (``miss``); (b) his points per game
# against his points per game before the week (raw regression to the mean). Intervals: 95% bootstrap resampling whole
# players (a player-season's rows come along together — his overlapping next-k windows are not independent); every
# group against the rest (the other player-weeks with a tag at the same positions), never against 50%.
TREND_NEAR = 0.5                 # = api research.NEAR and web lib/research.ts NEAR (points per game)
TREND_KS = (1, 2, 4)
ROLE_KS = (1, 2, 4)
TREND_TAGS = ("below", "above")
TREND_REASONS = ("touchdowns", "quarterback", "share", "none")
REASON_WORDS = {"touchdowns": "touchdowns against red-zone chances", "quarterback": "a quarterback change",
                "share": "his share of the work moved", "none": "no reason named"}
TREND_GAMES_SQL = """select p.gsis_id, p.week, p.game_id, p.position, p.team, p.played, p.targets, p.team_targets, p.carries,
                            p.team_carries, p.offense_snaps, p.offense_snap_pct, p.red_zone_targets, p.red_zone_carries,
                            coalesce(p.receiving_tds, 0) + coalesce(p.rushing_tds, 0) as tds, p.passing_tds,
                            p.target_share::float8 as target_share, p.carry_share::float8 as carry_share,
                            e.points_expected::float8 as points_expected, coalesce(e.expected_known, false) as expected_known
                     from analytics.fct_player_game p
                     left join analytics.mart_player_expected_points e on e.gsis_id = p.gsis_id and e.game_id = p.game_id
                     where p.season = %s and p.season_type = 'REG' and p.position in ('QB', 'RB', 'WR', 'TE') and p.played"""
QB_CHANGED_SQL = """select gsis_id, week, pn_qb_changed from analytics.mart_player_week_features
                    where season = %s and pn_qb_changed is not null"""


def load_trend_games(conn, season: int, actual: pd.DataFrame | None = None) -> tuple[pd.DataFrame, dict]:
    """(the season's played QB-TE games with Half PPR ``actual`` and expected points, (gsis, week) -> his quarterback
    changed this week). ``actual``: ``actual_points`` when the caller has it."""
    s = int(season)
    g = _df(conn, TREND_GAMES_SQL, (s,))
    if g.empty:
        return g, {}
    g = _num(g, ["targets", "team_targets", "carries", "team_carries", "offense_snaps", "offense_snap_pct",
                 "red_zone_targets", "red_zone_carries", "tds", "passing_tds", "target_share", "carry_share",
                 "points_expected", "week"])
    g["week"] = g["week"].astype(int)
    a = actual_points(conn, s) if actual is None else actual
    a = a[a["actual"].notna()][["gsis_id", "week", "actual"]].copy()
    a["week"] = pd.to_numeric(a["week"]).astype(int)
    g = g.merge(a.drop_duplicates(["gsis_id", "week"]), on=["gsis_id", "week"], how="left")
    try:
        qb = _df(conn, QB_CHANGED_SQL, (s,))
    except Exception:  # noqa: BLE001 - no personnel inputs on this database: no quarterback reason
        conn.rollback()
        qb = pd.DataFrame(columns=["gsis_id", "week", "pn_qb_changed"])
    qbc = {(str(r.gsis_id), int(r.week)): bool(r.pn_qb_changed == 1) for r in qb.itertuples()}
    return g, qbc


def trend_fields(t: tuple | None) -> dict:
    """The record's five trend columns from ``trend_asof_week``'s tuple (no game before the week: 0 games, the rest
    unknown)."""
    if not t:
        return {"trend_games": 0, "trend_ppg": None, "trend_gap": None, "trend_tag": None, "trend_reason": None}
    games, ppg, _xppg, gap, tag, reason = t
    return {"trend_games": int(games), "trend_ppg": _f(ppg), "trend_gap": _f(gap), "trend_tag": tag, "trend_reason": reason}


def backfill_trend(conn) -> int:
    """Fill the trend columns of record rows written before they existed (Wave I-O's rows): the tag depends only on the
    games before the week, so it is what the freeze would have stored (a later stat correction aside)."""
    with conn.cursor() as cur:
        cur.execute("select distinct season, week from ops.context_record where trend_games is null order by 1, 2")
        todo = cur.fetchall()
    if not todo:
        return 0
    n = 0
    for s in sorted({int(r[0]) for r in todo}):
        g, qbc = load_trend_games(conn, s)
        rows = []
        for w in sorted(int(r[1]) for r in todo if int(r[0]) == s):
            for gid, t in trend_asof_week(g, w, qbc).items():
                f = trend_fields(t)
                rows.append([gid, w, f["trend_games"], f["trend_ppg"], f["trend_gap"], f["trend_tag"], f["trend_reason"]])
        with conn.cursor() as cur:
            cur.execute("""create temp table if not exists _ctx_trend (gsis_id text, week integer, trend_games integer,
                           trend_ppg double precision, trend_gap double precision, trend_tag text, trend_reason text)
                           on commit drop""")
            cur.execute("truncate _ctx_trend")
            with cur.copy("copy _ctx_trend from stdin") as cp:
                for r in rows:
                    cp.write_row(r)
            cur.execute("""update ops.context_record c set trend_games = coalesce(t.trend_games, 0), trend_ppg = t.trend_ppg,
                                  trend_gap = t.trend_gap, trend_tag = t.trend_tag, trend_reason = t.trend_reason
                           from (select c2.ctid as id, t.* from ops.context_record c2
                                 left join _ctx_trend t on t.gsis_id = c2.gsis_id and t.week = c2.week
                                 where c2.season = %s and c2.trend_games is null) t
                           where c.ctid = t.id""", (s,))
            n += cur.rowcount
        conn.commit()
    log.info("context record: trend columns filled on %s rows written before them", n)
    return n


def trend_tag(gap) -> str | None:
    """The screen's word for a gap (points per game): below / above past ``TREND_NEAR``, near inside it, None unknown."""
    g = _f(gap)
    if g is None:
        return None
    return "below" if g < -TREND_NEAR else "above" if g > TREND_NEAR else "near"


def trend_reason(position: str, gap, games, tds, rz, pass_tds, share_first, share_last, qb_changed) -> str | None:
    """The category of the reason Trends prints (research.trend_cause, the same order of rules): ``touchdowns``
    (none on 2+ red-zone chances / no touchdown pass in 2+ games below; 2+ and 0.6 per game / 2 passes per game above),
    ``quarterback`` (his quarterback changed this week), ``share`` (his share of the targets — carries for a running
    back — moved 6 points or more from his first game to his last), ``none`` (no reason named); None near or unknown."""
    g = _f(gap)
    if g is None or abs(g) <= TREND_NEAR:
        return None
    games, tds, rz, ptd = int(games or 0), int(tds or 0), int(rz or 0), int(pass_tds or 0)
    a, b = _f(share_first), _f(share_last)
    move = None if a is None or b is None or abs(b - a) < 0.06 else (b - a)
    qb = bool(qb_changed) and position != "QB"
    if g < 0:
        if position == "QB":
            if ptd == 0 and games >= 2:
                return "touchdowns"
        elif tds == 0 and rz >= 2:
            return "touchdowns"
        if qb:
            return "quarterback"
        if move is not None and move < 0:
            return "share"
        return "none"
    if position == "QB":
        if games and ptd >= 2 * games:
            return "touchdowns"
    elif tds >= 2 and games and tds / games >= 0.6:
        return "touchdowns"
    if move is not None and move > 0:
        return "share"
    if qb:
        return "quarterback"
    return "none"


def _player_arrays(g: pd.DataFrame) -> dict:
    """One player's played games of a season (sorted by week) as the arrays the tag reads."""
    pos = str(g["position"].iloc[-1])
    act = pd.to_numeric(g["actual"], errors="coerce").to_numpy(dtype=float)
    xp = pd.to_numeric(g["points_expected"], errors="coerce").to_numpy(dtype=float)
    rz = pd.to_numeric(g["red_zone_targets"], errors="coerce").fillna(0).to_numpy()
    if pos in ("RB", "QB"):
        rz = rz + pd.to_numeric(g["red_zone_carries"], errors="coerce").fillna(0).to_numpy()
    return {"pos": pos, "week": g["week"].astype(int).to_numpy(), "act": act, "xp": xp,
            "known": g["expected_known"].fillna(False).astype(bool).to_numpy() & ~np.isnan(xp) & ~np.isnan(act),
            "tds": pd.to_numeric(g["tds"], errors="coerce").fillna(0).to_numpy(),
            "ptd": pd.to_numeric(g["passing_tds"], errors="coerce").fillna(0).to_numpy(), "rz": rz,
            "share": pd.to_numeric(g["carry_share" if pos == "RB" else "target_share"], errors="coerce").to_numpy(dtype=float)}


def _tag_before(a: dict, i: int, qb_changed) -> tuple:
    """(games, ppg, xppg, gap, tag, reason) from the first ``i`` games of ``a`` only (the games before the week)."""
    k = a["known"][:i]
    n_x = int(k.sum())
    ppg = float(np.nansum(a["act"][:i]) / i) if i else None
    xppg = float(a["xp"][:i][k].mean()) if n_x else None
    gap = float((a["act"][:i][k] - a["xp"][:i][k]).mean()) if n_x else None
    sh = a["share"][:i][~np.isnan(a["share"][:i])]
    reason = trend_reason(a["pos"], gap, i, a["tds"][:i].sum(), a["rz"][:i].sum(), a["ptd"][:i].sum(),
                          sh[0] if sh.size >= 2 else None, sh[-1] if sh.size >= 2 else None, qb_changed)
    return i, ppg, xppg, gap, trend_tag(gap), reason


TREND_COLS = ["trend_games", "ppg_before", "xppg_before", "trend_gap", "trend_tag", "trend_reason"]


def asof_trend(games: pd.DataFrame, qb_changed: Mapping[tuple[str, int], bool] | None = None) -> pd.DataFrame:
    """One row per played game of ``games`` (one season: gsis_id, week, position, actual, points_expected,
    expected_known, tds, passing_tds, red_zone_targets, red_zone_carries, target_share, carry_share): the Trends tag as
    it would have read BEFORE that week — from his earlier games of the season only (a game never enters its own tag):
    ``trend_games`` (games before), ``ppg_before``, ``xppg_before``, ``trend_gap``, ``trend_tag``, ``trend_reason``."""
    cols = ["gsis_id", "week", *TREND_COLS]
    if games is None or games.empty:
        return pd.DataFrame(columns=cols)
    out = []
    qb_changed = qb_changed or {}
    for gid, g in games.sort_values(["gsis_id", "week"], kind="mergesort").groupby("gsis_id", sort=False):
        a = _player_arrays(g)
        for i, w in enumerate(a["week"]):
            out.append((str(gid), int(w), *_tag_before(a, i, qb_changed.get((str(gid), int(w))))))
    return pd.DataFrame(out, columns=cols)


def trend_asof_week(games: pd.DataFrame, week: int, qb_changed: Mapping[tuple[str, int], bool] | None = None) -> dict[str, tuple]:
    """gsis_id -> (games, ppg, xppg, gap, tag, reason) as Trends would have read before ``week`` (his games of the
    season before the week; the week's own game and later ones never enter). The record's freeze and its backfill."""
    if games is None or games.empty:
        return {}
    qb_changed = qb_changed or {}
    g0 = games[games["week"].astype(int) < int(week)]
    out = {}
    for gid, g in g0.sort_values(["gsis_id", "week"], kind="mergesort").groupby("gsis_id", sort=False):
        a = _player_arrays(g)
        out[str(gid)] = _tag_before(a, len(g), qb_changed.get((str(gid), int(week))))
    return out


def _team_snaps(g: pd.DataFrame) -> pd.Series:
    pct = pd.to_numeric(g["offense_snap_pct"], errors="coerce")
    return (pd.to_numeric(g["offense_snaps"], errors="coerce") / pct).where(pct > 0).round()


def asof_role(games: pd.DataFrame) -> pd.DataFrame:
    """One row per played game of an RB / WR / TE (one season): the role trend as it would have read BEFORE that week
    (``role_trend.role_trend`` on his earlier games of the season, routes left out as on the live screen) and, for each
    measure that moved, its share before, in the two recent games, and over his next 1 / 2 / 4 games from this one
    (summed numerator over summed denominator; None when a game lacks it)."""
    from .role_trend import ROLE_MEASURES, role_trend
    cols = ["gsis_id", "week", "role_games", "role_trend", "measure", "before", "recent", *[f"next{k}" for k in ROLE_KS]]
    if games is None or games.empty:
        return pd.DataFrame(columns=cols)
    g0 = games[games["position"].isin(["RB", "WR", "TE"])].copy()
    g0["team_snaps"] = _team_snaps(g0)
    g0["routes"] = np.nan
    g0["team_dropbacks_with_participation"] = np.nan
    out = []
    for gid, g in g0.sort_values(["gsis_id", "week"], kind="mergesort").groupby("gsis_id", sort=False):
        pos = str(g["position"].iloc[-1])
        g = g.reset_index(drop=True)
        arrs = {m: (pd.to_numeric(g[d["num"]], errors="coerce").to_numpy(dtype=float),
                    pd.to_numeric(g[d["den"]], errors="coerce").to_numpy(dtype=float)) for m, d in ROLE_MEASURES.items()}
        for i in range(len(g)):
            w = int(g["week"].iloc[i])
            rt = role_trend(g.iloc[:i], pos) if i >= 4 else None
            if not rt:
                out.append((str(gid), w, i, None, None, None, None, *[None] * len(ROLE_KS)))
                continue
            for m in rt["measures"]:
                num, den = arrs[m["measure"]]
                nxt = []
                for k in ROLE_KS:
                    if i + k > len(g):
                        nxt.append(None)
                        continue
                    x, d = num[i:i + k], den[i:i + k]
                    ok = (~np.isnan(x) & ~np.isnan(d) & (d > 0)).all()
                    nxt.append(float(x.sum() / d.sum()) if ok else None)
                out.append((str(gid), w, i, rt["trend"], m["measure"], m["before"], m["recent"], *nxt))
    return pd.DataFrame(out, columns=cols)


def _next_mean(v: np.ndarray, k: int) -> np.ndarray:
    """Per row i of one player's played games (in order): the mean of v[i .. i+k-1], NaN when fewer than k games are
    left or any of them is NaN (a game without a projection or a final)."""
    n = len(v)
    out = np.full(n, np.nan)
    for i in range(n - k + 1):
        w = v[i:i + k]
        if not np.isnan(w).any():
            out[i] = float(w.mean())
    return out


def outcomes(games: pd.DataFrame, ks: Sequence[int] = TREND_KS) -> pd.DataFrame:
    """Per played game (gsis_id, week): ``miss{k}`` = mean (actual - projection made before the game) over this game and
    his next k-1 played games, ``pts{k}`` = his mean points over them (NaN when fewer than k are left or a game has no
    projection). ``games``: gsis_id, week, actual, proj_points."""
    rows = []
    for gid, g in games.sort_values(["gsis_id", "week"], kind="mergesort").groupby("gsis_id", sort=False):
        act = pd.to_numeric(g["actual"], errors="coerce").to_numpy(dtype=float)
        prj = pd.to_numeric(g["proj_points"], errors="coerce").to_numpy(dtype=float)
        d = {"gsis_id": [str(gid)] * len(g), "week": g["week"].astype(int).to_numpy()}
        for k in ks:
            d[f"miss{k}"] = _next_mean(act - prj, k)
            d[f"pts{k}"] = _next_mean(np.where(np.isnan(prj), np.nan, act), k)
        rows.append(pd.DataFrame(d))
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=["gsis_id", "week"])


def study_projections(conn, season: int, extra: pd.DataFrame | None = None) -> pd.DataFrame:
    """gsis_id, week, proj_points (Half PPR, made before the game): ``ops.calibration_oof`` (walk-forward) where it holds
    the season, else ``ops.projections`` (2026: as context_record grades it), else ``extra`` (a caller's walk-forward rows
    for an older season, ``calibration.oof_rows``)."""
    oof = _df(conn, OOF_SQL, (int(season), ANCHOR_LEAGUE))
    if oof.empty and extra is not None and not extra.empty:
        oof = extra[(extra["season"] == int(season)) & (extra["league_id"] == ANCHOR_LEAGUE)]
    if oof.empty:
        oof = _df(conn, PROJ_SQL, (int(season), ANCHOR_LEAGUE))
    p = _num(oof[["gsis_id", "week", "proj_points"]].copy(), ["proj_points"])
    p["week"] = p["week"].astype(int)
    return p.drop_duplicates(["gsis_id", "week"])


def study_frame(conn, seasons: Iterable[int], extra: pd.DataFrame | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(trend rows, role rows) for ``seasons``: every played QB-TE game with the as-of tag before it and his next-k
    outcomes; every RB / WR / TE game with the as-of role trend, its moved measures' shares and the same outcomes."""
    tf, rf = [], []
    for s in seasons:
        s = int(s)
        g, qbc = load_trend_games(conn, s)
        if g.empty:
            continue
        g = g.merge(study_projections(conn, s, extra), on=["gsis_id", "week"], how="left")
        oc = outcomes(g)
        base = g[["gsis_id", "week", "game_id", "position", "team", "proj_points", "actual"]]
        t = base.merge(asof_trend(g, qbc), on=["gsis_id", "week"]).merge(oc, on=["gsis_id", "week"], how="left")
        tf.append(t.assign(season=s))
        r = asof_role(g).merge(base, on=["gsis_id", "week"]).merge(oc, on=["gsis_id", "week"], how="left")
        rf.append(r.assign(season=s))
    T = pd.concat(tf, ignore_index=True) if tf else pd.DataFrame()
    R = pd.concat(rf, ignore_index=True) if rf else pd.DataFrame()
    for f in (T, R):
        if not f.empty:
            f["player"] = f["gsis_id"].astype(str) + ":" + f["season"].astype(str)
    return T, R


def _gk(a: pd.DataFrame, rest: pd.DataFrame, col: str, base: str | None = None) -> dict:
    """n, players, the mean of ``col`` (minus ``base`` when given) with its player-resampled interval, the share above 0,
    and the difference from ``rest`` with its interval."""
    def val(d):
        v = d[col] - (d[base] if base else 0)
        ok = v.notna()
        return v[ok].to_numpy(dtype=float), d.loc[ok, "player"].to_numpy()
    av, ap = val(a)
    bv, bp = val(rest)
    mean, lo, hi = bootstrap_mean(av, ap)
    diff, dlo, dhi = bootstrap_diff(av, ap, bv, bp)
    return {"n": int(av.size), "players": int(len(set(ap))), "mean": _r(mean), "lo": _r(lo), "hi": _r(hi),
            "above": _r(float((av > 0).mean()) if av.size else None, 3), "rest_n": int(bv.size),
            "rest_mean": _r(float(bv.mean()) if bv.size else None),
            "rest_above": _r(float((bv > 0).mean()) if bv.size else None, 3),
            "vs_rest": _r(diff), "vs_rest_lo": _r(dlo), "vs_rest_hi": _r(dhi)}


def trend_grade(T: pd.DataFrame, ks: Sequence[int] = TREND_KS) -> list[dict]:
    """The grade of "below / above expectation": per tag x k (and by gap tercile, position and reason), (a) the miss
    against the projection over the next k games against the rest (the other player-weeks with a known gap at the same
    positions), (b) the raw change: points per game over the next k minus his points per game before the week."""
    d = T[T["trend_tag"].notna()].copy()
    out = []
    for tag in TREND_TAGS:
        g = d[d["trend_tag"] == tag]
        if g.empty:
            continue
        cuts = np.quantile(g["trend_gap"].abs(), [1 / 3, 2 / 3])
        size = np.where(g["trend_gap"].abs() <= cuts[0], "small", np.where(g["trend_gap"].abs() <= cuts[1], "middle", "large"))
        g = g.assign(size=size)
        groups = [("all", "all", g)]
        groups += [("size", s, g[g["size"] == s]) for s in ("small", "middle", "large")]
        groups += [("position", p, g[g["position"] == p]) for p in ("QB", "RB", "WR", "TE")]
        groups += [("reason", r, g[g["trend_reason"] == r]) for r in TREND_REASONS]
        for by, grp, a in groups:
            if a.empty:
                continue
            rest = d[(d["trend_tag"] != tag) & d["position"].isin(a["position"].unique())]
            for k in ks:
                row = {"tag": tag, "by": by, "grp": grp, "k": k,
                       "gap_lo": _r(float(a["trend_gap"].min())), "gap_hi": _r(float(a["trend_gap"].max()))}
                row.update(_gk(a, rest, f"miss{k}"))
                raw = _gk(a, rest, f"pts{k}", "ppg_before")
                row.update({f"raw_{x}": raw[x] for x in ("n", "mean", "lo", "hi", "vs_rest", "vs_rest_lo", "vs_rest_hi")})
                if by == "size":
                    row["cuts"] = [_r(float(c)) for c in cuts]
                out.append(row)
    return out


def role_grade(R: pd.DataFrame, ks: Sequence[int] = ROLE_KS) -> dict:
    """"Role up / down": (1) does the share hold — per trend x measure, the share before, in the two recent games and
    over the next 1 / 2 / 4 games (what moved = recent - before; held = next - before, both in share points, with a
    player-resampled interval); (2) is it priced — the miss against the projection over the next k games, against the
    rest (every other RB / WR / TE game with four games before it and no trend called)."""
    share = []
    m = R[R["role_trend"].notna()]
    for (trend, measure), g in m.groupby(["role_trend", "measure"]):
        for k in ks:
            d = g[g[f"next{k}"].notna()]
            if d.empty:
                continue
            moved = (d["recent"] - d["before"]).to_numpy(dtype=float)
            held = (d[f"next{k}"] - d["before"]).to_numpy(dtype=float)
            hm, hlo, hhi = bootstrap_mean(held, d["player"].to_numpy())
            share.append({"trend": trend, "measure": measure, "k": k, "n": len(d), "players": int(d["player"].nunique()),
                          "before": _r(float(d["before"].mean()), 4), "recent": _r(float(d["recent"].mean()), 4),
                          "next": _r(float(d[f"next{k}"].mean()), 4), "moved": _r(float(moved.mean()), 4),
                          "held": _r(hm, 4), "held_lo": _r(hlo, 4), "held_hi": _r(hhi, 4),
                          "kept": _r(float(held.mean() / moved.mean()) if moved.mean() else None, 3)})
    return {"share": share, "priced": role_priced(R.drop_duplicates(["player", "week"]), ks)}


def role_priced(one: pd.DataFrame, ks: Sequence[int] = ROLE_KS) -> list[dict]:
    """Is "role up / down" priced: per trend (and position), the miss over the next k games against the rest — every
    other RB / WR / TE game with four games before it (a trend could have been called) and none called. ``one``: one
    row per player-week (role_trend, role_games, position, player, miss{k})."""
    called = one[one["role_trend"].notna()]
    priced = []
    for trend in ("up", "down"):
        a = called[called["role_trend"] == trend]
        if a.empty:
            continue
        # the rest: every other game with four games before it (a trend could have been called) and none called
        rest = one[one["role_trend"].isna() & (one["role_games"] >= 4)]
        for by, grp, sub in [("all", "all", a)] + [("position", p, a[a["position"] == p]) for p in ("RB", "WR", "TE")]:
            if sub.empty:
                continue
            r2 = rest[rest["position"].isin(sub["position"].unique())]
            for k in ks:
                row = {"trend": trend, "by": by, "grp": grp, "k": k}
                row.update(_gk(sub, r2, f"miss{k}"))
                priced.append(row)
    return priced
def record_frame(h: pd.DataFrame, ks: Sequence[int] = TREND_KS) -> pd.DataFrame:
    """The record's graded rows (one per player-week with a final game) with the next-k outcomes read from the record
    itself — his next k graded rows of the season, this week's first — in the study's shape (``player``,
    ``ppg_before``, ``role_games``, ``miss{k}``, ``pts{k}``)."""
    if h.empty:
        return h
    d = h[h["miss"].notna() & h["proj_points"].notna()].copy()
    d["actual"] = pd.to_numeric(d["actual_points"], errors="coerce")
    d["week"] = d["week"].astype(int)
    oc = []
    for s_, g in d.groupby("season"):
        oc.append(outcomes(g[["gsis_id", "week", "actual", "proj_points"]], ks).assign(season=s_))
    d = d.merge(pd.concat(oc, ignore_index=True), on=["season", "gsis_id", "week"], how="left")
    d["player"] = d["gsis_id"].astype(str) + ":" + d["season"].astype(str)
    d["ppg_before"] = pd.to_numeric(d["trend_ppg"], errors="coerce")
    d["trend_gap"] = pd.to_numeric(d["trend_gap"], errors="coerce")
    d["role_games"] = pd.to_numeric(d["trend_games"], errors="coerce")
    return d


def _tag_row(rows: Sequence[Mapping], tag: str, k: int = 1, by: str = "all", grp: str = "all") -> Mapping | None:
    return next((r for r in rows if r.get("tag", r.get("trend")) == tag and r["by"] == by and r["grp"] == grp
                 and r["k"] == k), None)


def _effect(r: Mapping | None) -> str | None:
    if not r or r.get("vs_rest") is None or r.get("vs_rest_lo") is None or r.get("vs_rest_hi") is None:
        return None
    return "none" if r["vs_rest_lo"] <= 0 <= r["vs_rest_hi"] else "above" if r["vs_rest"] > 0 else "below"


def _against(r: Mapping, who: str = "the other players") -> str:
    """'0.2 points above the other players against their projection (−0.1 to +0.5; 2,467 games)'."""
    v = r["vs_rest"]
    ci = f"{_signed(r['vs_rest_lo'])} to {_signed(r['vs_rest_hi'])}; " if r.get("vs_rest_lo") is not None else ""
    where = f"level with {who}" if round(v, 1) == 0 else f"{_pts(v)} {'above' if v > 0 else 'below'} {who}"
    return f"{where} against their projection ({ci}{r['n']:,} games)"


def _verdict(r: Mapping) -> str:
    eff = _effect(r)
    return ("no measurable difference" if eff in (None, "none")
            else "more than their projection gave them" if eff == "above" else "less than their projection gave them")


def _raw(r: Mapping, before: str = "their points per game before") -> str:
    raw = r.get("raw_mean")
    if raw is None:
        return ""
    return f"scored {_pts(raw)} {'more' if raw > 0 else 'less'} than {before} and "


def trend_sentence(rows: Sequence[Mapping], span: str | None) -> str | None:
    """What "below / above expectation" has meant for the next game, from the record's grade: the raw change (his
    points next against his points per game before) and the miss against the projection, against the rest."""
    b, a = _tag_row(rows, "below"), _tag_row(rows, "above")
    if not b or not a or not b.get("n") or not a.get("n") or b.get("vs_rest") is None or a.get("vs_rest") is None:
        return None
    return (f"Graded on {span} ({SCORING_WORDS}), in their next game: players below expectation {_raw(b)}finished "
            f"{_against(b)} — {_verdict(b)}; players above expectation {_raw(a, 'before')}finished "
            f"{_against(a, 'the others')} — {_verdict(a)}. The projection already counts a player's work and his "
            "points: a gap here is what happened, not a reason to buy or sell on its own.")


def trend_head(rows: Sequence[Mapping], span: str | None) -> str | None:
    """Trends' line under its title: "Graded on 2025 and 2026 weeks 1–4 (Half PPR): in their next game, players below expectation
    scored 1.5 points more than their average before and players above it 1.9 less — and their projections already
    expected that (no
    measurable difference against them; 4,282 games)." """
    b, a = _tag_row(rows, "below"), _tag_row(rows, "above")
    if not b or not a or b.get("raw_mean") is None or a.get("raw_mean") is None or b.get("vs_rest") is None \
            or a.get("vs_rest") is None:
        return None
    rb, ra = b["raw_mean"], a["raw_mean"]
    lead = (f"Graded on {span} ({SCORING_WORDS}): in their next game, players below expectation scored {_pts(rb)} "
            f"{'more' if rb > 0 else 'less'} than their average before and players above it {abs(ra):.1f} "
            f"{'more' if ra > 0 else 'less'}")
    eb, ea = _effect(b), _effect(a)
    n = int(b["n"]) + int(a["n"])
    if eb in (None, "none") and ea in (None, "none"):
        return f"{lead} — and their projections already expected that (no measurable difference against them; {n:,} games)."
    parts = []
    for r, word, e in ((b, "below", eb), (a, "above", ea)):
        if e in (None, "none"):
            parts.append(f"those {word} expectation level with their projection")
        else:
            parts.append(f"those {word} expectation finished {_against(r, 'the rest')}")
    return f"{lead}; " + " and ".join(parts) + "."


def role_sentence(rows: Sequence[Mapping], span: str | None) -> str | None:
    """What "role up / role down" has meant for the next game against the projection, one sentence."""
    up, dn = _tag_row(rows, "up"), _tag_row(rows, "down")
    if not up or not up.get("n") or up.get("vs_rest") is None:
        return None
    out = (f"Graded on {span} ({SCORING_WORDS}), in their next game: after \"role up\" players finished {_against(up)} "
           f"— {_verdict(up)}")
    if dn and dn.get("n") and dn.get("vs_rest") is not None:
        out += f"; after \"role down\" {_against(dn, 'the others')} — {_verdict(dn)}"
    return out + "."


def trend_grade_rows(h: pd.DataFrame, graded_at: datetime | None = None) -> list[dict]:
    """``ops.context_grade`` rows for Trends and the role trend from the record: kind ``trend`` (the miss against the
    projection over the next k games; grp ``tag/by/group/k``), ``trend_raw`` (points per game next minus before),
    ``role`` (grp ``trend/by/group/k``), and ``summary`` grp ``trend`` / ``role`` (the sentences)."""
    if h.empty or "trend_tag" not in h:
        return []
    d = record_frame(h)
    if d.empty:
        return []
    span = span_words(d)
    out = []

    def put(kind, grp, r, mean, lo, hi, vs=("vs_rest", "vs_rest_lo", "vs_rest_hi"), words=None, sp=None):
        out.append({"kind": kind, "grp": grp, "corner_certainty": None, "corner_tier": None, "n": r.get("n"),
                    "games": r.get("players"), "mean_miss": r.get(mean), "lo": r.get(lo), "hi": r.get(hi),
                    "beat": None if r.get("above") is None else int(round(r["above"] * r["n"])),
                    "beat_share": r.get("above"), "vs_rest": r.get(vs[0]), "vs_rest_lo": r.get(vs[1]),
                    "vs_rest_hi": r.get(vs[2]), "rest_n": r.get("rest_n"), "rest_beat_share": r.get("rest_above"),
                    "span": sp or span, "scoring": SCORING_WORDS, "words": words, "graded_at": graded_at})
    t = trend_grade(d[d["trend_tag"].notna()]) if d["trend_tag"].notna().any() else []
    for r in t:
        g = f"{r['tag']}/{r['by']}/{r['grp']}/{r['k']}"
        put("trend", g, r, "mean", "lo", "hi")
        put("trend_raw", g, {**r, "n": r.get("raw_n"), "above": None, "rest_above": None}, "raw_mean", "raw_lo", "raw_hi",
            ("raw_vs_rest", "raw_vs_rest_lo", "raw_vs_rest_hi"))
    rw = d[d["position"].isin(["RB", "WR", "TE"])].copy()
    rw["role_trend"] = rw["role_trend"].where(rw["role_trend"].isin(["up", "down"]), None)
    rp = role_priced(rw) if rw["role_trend"].notna().any() else []
    rspan = span_words(rw[rw["role_trend"].notna()]) if rp else None
    for r in rp:
        put("role", f"{r['trend']}/{r['by']}/{r['grp']}/{r['k']}", r, "mean", "lo", "hi", sp=rspan)
    tw = trend_sentence(t, span)
    if tw:
        n = (_tag_row(t, "below") or {}).get("n", 0) + (_tag_row(t, "above") or {}).get("n", 0)
        put("summary", "trend", {"n": n}, "x", "x", "x", words=tw)
        put("summary", "trend_head", {"n": n}, "x", "x", "x", words=trend_head(t, span))
    rwds = role_sentence(rp, rspan)
    if rwds:
        put("summary", "role", {"n": (_tag_row(rp, "up") or {}).get("n", 0) + (_tag_row(rp, "down") or {}).get("n", 0)},
            "x", "x", "x", words=rwds, sp=rspan)
    return out
# ---- end IP-3 (study)


# ---- IP-3: the study from the command line (docs/METRICS.md § "Trends and the role trend, graded" — every table)
def study(seasons: Sequence[int] = (2021, 2022, 2023, 2024, 2025, 2026), fit_missing: bool = True) -> dict:
    """The tables of the study. Seasons without stored walk-forward rows (``ops.calibration_oof`` holds 2023-2025 on
    the sandbox) are projected walk-forward in memory with ``calibration.oof_rows`` (the production fit on the seasons
    before each; ~80 s for 2021-2022 with ``OMP_NUM_THREADS=1``) when ``fit_missing``; nothing is written."""
    import psycopg

    from .config import get_settings
    with psycopg.connect(get_settings().pipeline_dsn()) as conn:
        extra = None
        have = {int(r[0]) for r in conn.execute("select distinct season from ops.calibration_oof where league_id = %s",
                                                 (ANCHOR_LEAGUE,)).fetchall()}
        missing = [int(s) for s in seasons if int(s) not in have and int(s) < max(int(x) for x in seasons)]
        if fit_missing and missing:
            from . import calibration as CAL
            from . import projections as P
            sc = {k: v for k, v in P.league_scorings(conn).items() if k == ANCHOR_LEAGUE}
            alls = P.available_seasons(conn)
            frame = P.load_frame(conn, [s for s in alls if s <= max(missing)])
            extra = CAL.oof_rows(frame, missing, sc, min(alls), ranges=False)
        T, R = study_frame(conn, seasons, extra)
    return {"trend": trend_grade(T), "role": role_grade(R), "rows": {"trend": len(T), "role": len(R)}}


if __name__ == "__main__":  # pragma: no cover - the reproducible study (prints JSON)
    import sys

    if sys.argv[1:2] == ["study"]:
        print(json.dumps(study(), indent=1, default=str))
# ---- end IP-3
