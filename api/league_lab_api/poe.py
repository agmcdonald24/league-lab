"""JB-4 (Wave J-B): the card explains "points over expected" in one sentence.

Season to date, over his played regular-season games that have an expected value, summed (AGENTS rule 4: the sum of
the numerators over the same games): "His 44 targets usually bring about 64 points; he has 44. Depth of target is
already allowed for." The points are the Stats catalogue's own — ``research.league_games`` (the league mart for a
house league; priced in the scoring otherwise), so the sentence and the "Points over expected" column agree.

The rule (docs/WORDS.md § JB-4): a receiver (WR, TE) counts targets, a back (RB) carries + targets; under
``MIN_TOUCHES`` (20) of them: nothing. A quarterback: nothing (his expected points are mostly his passing, which a count
of targets or carries does not describe). No game with an expected value (``expected_known`` false), or a game whose
expected or actual points are unknown: that game is left out; none left: nothing — never 0. The sentence never says
why the two differ (the How-to-read line carries the one caveat)."""

from __future__ import annotations

import math

import pandas as pd

from .db import query

MIN_TOUCHES = 20
RECEIVERS = ("WR", "TE")
BACKS = ("RB",)
DEPTH_WORDS = {"rec": "Depth of target is already allowed for.",
               "back": "Depth of target and field position are already allowed for."}

COUNTS_SQL = """select game_id, coalesce(targets, 0) as targets, coalesce(carries, 0) as carries
    from analytics.fct_player_game where gsis_id = %s and season = %s and season_type = 'REG' and played"""


def _num(x) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) else v


def _whole(v: float) -> int:
    """Whole points, halves up (63.5 → 64), the same both ways for the two numbers."""
    return int(math.floor(v + 0.5))


def sentence(games: pd.DataFrame, counts: pd.DataFrame, position: str | None) -> dict | None:
    """{words, kind, targets, carries, expected, actual, games} from his priced games and his counts, or None.

    ``games``: research.league_games' rows (game_id, season_type, played, points, points_expected, expected_known);
    ``counts``: game_id, targets, carries for his played regular-season games."""
    pos = str(position or "").upper()
    if pos not in RECEIVERS + BACKS or games is None or games.empty or counts is None or counts.empty:
        return None
    g = games[(games["season_type"] == "REG") & games["played"].fillna(False).astype(bool)
              & games["expected_known"].fillna(False).astype(bool)].copy()
    g["x"] = pd.to_numeric(g["points_expected"], errors="coerce")
    g["a"] = pd.to_numeric(g["points"], errors="coerce")
    g = g[g["x"].notna() & g["a"].notna()].merge(counts, on="game_id", how="inner")   # the same games for all four
    if g.empty:
        return None
    t, c = int(g["targets"].sum()), int(g["carries"].sum())
    n = t if pos in RECEIVERS else t + c
    if n < MIN_TOUCHES:
        return None
    x, a = float(g["x"].sum()), float(g["a"].sum())
    if pos in RECEIVERS:
        what, depth = f"His {t} target{'s' if t != 1 else ''}", DEPTH_WORDS["rec"]
    else:
        what = f"His {c} carr{'ies' if c != 1 else 'y'} and {t} target{'s' if t != 1 else ''}"
        depth = DEPTH_WORDS["back"]
    words = f"{what} usually bring about {_whole(x)} points; he has {_whole(a)}. {depth}"
    return {"kind": "receiver" if pos in RECEIVERS else "back", "words": words, "targets": t, "carries": c,
            "expected": round(x, 1), "actual": round(a, 1), "games": int(len(g))}


def card_line(league_id: str, gsis: str, season, position, *, source: str | None = None) -> dict | None:
    """The card's sentence for this league (or reference scoring): his priced games and his counts, then ``sentence``.
    A failure to read either is no sentence (the card stands), never a zero."""
    from . import research as RS
    if season is None or str(position or "").upper() not in RECEIVERS + BACKS:
        return None
    ctx = RS.context(league_id, source)
    games = RS.league_games(ctx, int(season), [gsis])
    counts = query(COUNTS_SQL, (gsis, int(season)))
    return sentence(games, counts, position)
