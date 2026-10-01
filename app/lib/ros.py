"""Rest of season (plan E2, Wave E): the words and the one query the Player card, Rankings and Trade Finder share.

The numbers come from ``analytics.mart_player_ros_projection`` (one row per league x player): the projected points
over the weeks left in the league's season (from this week to the league's final), byes excluded, the playoff
subtotal, a range (the weeks combined as if independent: docs/METRICS.md § Rest of season) and the rank by position
and overall within the league. Every page reads the same row, so a player's total and rank are the same everywhere.
The page code stays thin: the sentences are built here, pure, and tested in tests/test_ros.py.
"""

from __future__ import annotations

import json
import math

import pandas as pd

RELATION = "mart_player_ros_projection"

# the columns every surface reads (player_key = gsis_id; a team defense's Sleeper id). The pages spell out
# `analytics.mart_player_ros_projection` in their own SQL (the hosted sync publishes what the page code names).
ROS_COLUMNS = ("player_key, gsis_id, player_name, position, team, is_ranked, roster_status, from_week, last_week, "
               "playoff_week_start, ros_games, ros_points, ros_points_per_game, ros_p10, ros_p90, playoff_games, "
               "playoff_points, ros_rank_pos, ros_rank_all, bye_weeks, weeks_with_lines, weeks_json")


def _num(v) -> float | None:
    if v is None or isinstance(v, str):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def whole(v) -> int | None:
    """Round half up to a whole point (as the trade engine's market does); None stays None."""
    f = _num(v)
    return None if f is None else int(math.floor(f + 0.5))


def weeks_span(first, last) -> str:
    """'weeks 4–16' / 'week 16'."""
    a, b = int(first), int(last)
    return f"week {a}" if a == b else f"weeks {a}–{b}"


def rank_label(r) -> str | None:
    """'RB8' (the rank at his position in this league), None when he is not ranked (injured reserve, inactive)."""
    k = _num(r.get("ros_rank_pos"))
    return None if k is None else f"{r.get('position')}{int(k)}"


def range_words(r) -> str | None:
    """'118–166' (whole points), None without a range."""
    lo, hi = whole(r.get("ros_p10")), whole(r.get("ros_p90"))
    return None if lo is None or hi is None else f"{lo}–{hi}"


def playoff_window(r) -> str | None:
    """'weeks 15–16' (the part of the league's playoffs still ahead), None once the playoffs are over."""
    start, last, first = _num(r.get("playoff_week_start")), _num(r.get("last_week")), _num(r.get("from_week"))
    if start is None or last is None:
        return None
    begin = max(int(start), int(first)) if first is not None else int(start)
    return None if begin > int(last) else weeks_span(begin, last)


def card_line(r) -> str:
    """The Player card's one line: 'Rest of season: **142 points** over 13 games (likely 118–166), **RB8** in this
    league · playoffs (weeks 15–17): 31'."""
    pts, games = whole(r.get("ros_points")), int(_num(r.get("ros_games")) or 0)
    rng = range_words(r)
    out = f"Rest of season: **{pts} points** over {games} game{'s' if games != 1 else ''}"
    if rng:
        out += f" (likely {rng})"
    rk = rank_label(r)
    if rk:
        out += f", **{rk}** in this league"
    else:
        out += ", not ranked (" + ("on injured reserve" if r.get("roster_status") == "RES" else "not on an active NFL roster") + ")"
    po = playoff_window(r)
    if po:
        out += f" · playoffs ({po}): {whole(r.get('playoff_points'))}"
    return out


def weeks_list(r) -> list[tuple[int, float]]:
    """[(week, points), ...] from weeks_json (a JSON array of [week, points] pairs)."""
    raw = r.get("weeks_json")
    if raw is None or (isinstance(raw, float) and math.isnan(raw)):
        return []
    data = json.loads(raw) if isinstance(raw, str) else raw
    return [(int(w), float(p)) for w, p in data]


def weeks_words(r) -> str:
    """The sparkline in words: 'wk 4 10.1 · 5 9.4 · 6 bye · 7 9.4 …' over the window, byes named."""
    pts = dict(weeks_list(r))
    first, last = _num(r.get("from_week")), _num(r.get("last_week"))
    if first is None or last is None:
        return ""
    byes = {int(b) for b in (r.get("bye_weeks") or [])}
    bits = []
    for w in range(int(first), int(last) + 1):
        if w in pts:
            bits.append(f"{w} {pts[w]:.1f}")
        elif w in byes:
            bits.append(f"{w} bye")
        else:
            bits.append(f"{w} none")       # no projection that week (unknown, not 0)
    return "wk " + " · ".join(bits) if bits else ""


def lines_note(r, league_name: str | None = None) -> str:
    """Why the later weeks are flatter: only the weeks with a betting line know it."""
    first = _num(r.get("from_week"))
    n = int(_num(r.get("weeks_with_lines")) or 0)
    scoring = f" in {league_name} scoring" if league_name else ""
    if n <= 0:
        lead = "No week has betting lines yet"
    elif n == 1 and first is not None:
        lead = f"Only week {int(first)} has betting lines yet"
    else:
        lead = f"{n} of these weeks have betting lines"
    return f"{lead}: the later weeks lean on his usage and the schedule{scoring}."


def package_points(rows: pd.DataFrame, keys) -> tuple[int, int, list[str]]:
    """(rest-of-season points, games, keys with no row) for a set of player keys: each player rounded half up to a
    whole point first, so the total is the sum of the numbers the tables show (the trade engine's rule)."""
    keys = list(keys)
    have = rows.set_index("player_key") if not rows.empty else pd.DataFrame()
    total, games, missing = 0, 0, []
    for k in keys:
        if have.empty or k not in have.index:
            missing.append(k)
            continue
        total += whole(have.at[k, "ros_points"]) or 0
        games += int(have.at[k, "ros_games"])
    return total, games, missing


def package_sentence(give_pts: int, get_pts: int, window: str, missing_names: list[str] | None = None) -> str:
    """'Rest of season (weeks 4–16, through this league's final): you give **142** points, you get **171** (+29).'"""
    diff = get_pts - give_pts
    out = (f"Rest of season ({window}, through this league's final): you give **{give_pts}** points, "
           f"you get **{get_pts}** ({diff:+d}) — the players' plain totals, before the roster spot a lopsided trade frees "
           f"or fills and before your lineup is re-solved (the verdict above counts both). "
           f"Only this week has betting lines; later weeks lean on usage and the schedule.")
    if missing_names:
        out += " No projection yet for " + ", ".join(missing_names) + " (left out, not counted as 0)."
    return out
