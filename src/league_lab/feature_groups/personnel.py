"""Feature group ``personnel`` (plan D5, Wave D round 2 / projection v3): who plays next to him this week.

Andrew: "certain injuries might make an impact ... quarterback, that's a big one, but offensive line injuries".
Round 1 found that game context, weather and team style add nothing beyond the betting lines; personnel is the
one family with a mechanism the lines may not carry at the player level: a receiver's history was built with
one quarterback and the board prices him with another; a back runs behind a line missing two starters; the top
target is out and the shares move.

The table is ``intermediate.int_player_week_personnel`` (dbt, ``dbt/models/intermediate/features/``, helpers
``int_pn_*``): one row per ``int_player_week_universe`` row, every column as of the week (history: played games
with week < W; availability: week W's injury report and the reserve lists; the quarterback: the schedule's
projected starter). Definitions and evidence: ``docs/METRICS.md`` § "Personnel".

Sub-groups for the harness (``league-lab experiment personnel qb oline teammates own_injury``):

* ``qb`` - the projected starter vs the QB his last four games were played with, their games together, the
  quality gap, a starter with fewer than 8 career starts, and (QB rows) whether he is the projected starter;
* ``oline`` - the line's starters (top five by snaps over the last four games) out this week, their snap share,
  games since the starting five last changed;
* ``teammates`` - the leading teammate by target / carry share (last four games) out, the target share of the
  absent pass-catchers, a live absence alert (C6, ``ops.player_role_alerts``) for him;
* ``own_injury`` - games he missed injured (this season, last season), consecutive weeks Questionable, his
  first game back after two or more, this week's designation and practice participation.

This module also holds the Python twins of the two rules the SQL hard-codes (``tests/test_personnel.py`` pins
them on fixtures and checks the SQL uses the same constants): ``usual_qb`` / ``qb_changed`` (the QB-change rule)
and ``ol_starters`` / ``ol_starters_out`` (the offensive-line count).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

TABLE = "intermediate.int_player_week_personnel"

# ------------------------------------------------------------------------------ the rules (Python twins of the SQL)
USUAL_QB_GAMES = 4          # int_player_week_personnel: var('pn_usual_qb_games', 4): his newest four played games
TOGETHER_SNAP_SHARE = 0.5   # pn_qb_games_together: both on the field for >= 50% of the offensive snaps
ROOKIE_STARTS = 8           # pn_qb_is_rookie_or_backup: fewer than 8 career starts (since 2016)
PPG_STARTS = 17             # pn_qb_prev_ppg_diff: points per start over his newest 17 starts ...
PPG_SEASONS_BACK = 2        # ... of the last two seasons and this one
WINDOW_GAMES = 4            # int_pn_window_player: the team's last four played games before the week
OL_STARTERS = 5             # the five linemen with the most snaps over the window
OUT_STATUSES = ("Out", "Doubtful")                      # this week's report ...
RESERVE_STATUSES = ("RES", "PUP", "SUS", "EXE", "NON")  # ... or a reserve list (weekly roster) with this team


def usual_qb(games: Iterable[tuple[int, int, str | None]], season: int, week: int, n: int = USUAL_QB_GAMES) -> str | None:
    """The QB his history was built with: the schedule's starting QB of the majority of his newest ``n`` played
    games before (season, week) - this season before the week, or last season (ties: the more recent).

    ``games``: (season, week, starting_qb_id) of the games he PLAYED (any team). None when there are none."""
    hist = sorted(((s, w, q) for s, w, q in games
                   if q is not None and (s == season - 1 or (s == season and w < week))), reverse=True)[:n]
    if not hist:
        return None
    counts = Counter(q for _, _, q in hist)
    recency = {}
    for i, (_, _, q) in enumerate(hist):
        recency.setdefault(q, i)
    return min(counts, key=lambda q: (-counts[q], recency[q]))


def qb_changed(projected: str | None, usual: str | None) -> int | None:
    """1 when this week's projected starter is not the QB his history was built with; None when either is unknown."""
    if projected is None or usual is None:
        return None
    return int(projected != usual)


@dataclass(frozen=True)
class WindowLineman:
    gsis_id: str
    snap_share: float                 # his offensive snaps over the window / the team's
    report_status: str | None = None  # week W's injury report
    roster_status: str | None = None  # week W's weekly roster
    roster_team_is_team: bool = True  # that roster row is with this team


def is_out_injured(p: WindowLineman) -> bool:
    """Out or Doubtful on this week's report, or on a reserve list with this team (the weekly roster's ACT / INA
    split is never read: INA is the game-day inactive list)."""
    return p.report_status in OUT_STATUSES or (p.roster_team_is_team and p.roster_status in RESERVE_STATUSES)


def ol_starters(window: Sequence[WindowLineman], k: int = OL_STARTERS) -> list[WindowLineman]:
    """The line's starters: the ``k`` linemen with the largest snap share over the window (ties: gsis_id)."""
    return sorted(window, key=lambda p: (-p.snap_share, p.gsis_id))[:k]


def ol_starters_out(window: Sequence[WindowLineman], report_known: bool = True) -> tuple[int, float] | None:
    """(pn_ol_starters_out, pn_ol_snap_share_out); None when the week's report is not out or there is no window."""
    if not report_known or not window:
        return None
    out = [p for p in ol_starters(window) if is_out_injured(p)]
    return len(out), round(sum(p.snap_share for p in out), 4)


# ------------------------------------------------------------------------------ the columns
QB = ["pn_qb_changed", "pn_qb_games_together", "pn_qb_prev_ppg_diff", "pn_qb_is_rookie_or_backup", "pn_qb_starting"]
OLINE = ["pn_ol_starters_out", "pn_ol_snap_share_out", "pn_ol_games_since_change"]
TEAMMATES = ["pn_top_target_out", "pn_top_rusher_out", "pn_teammate_share_out", "pn_absence_beneficiary"]
OWN_INJURY = ["pn_games_missed_season", "pn_games_missed_prev", "pn_q_streak", "pn_returning", "pn_report_status_ord",
              "pn_practice_ord"]
# built from this season's games: NULL in week 1 (the harness's no-peek check 4)
IN_SEASON = [*OLINE, *TEAMMATES]

GROUPS = {
    "personnel": {
        "table": TABLE, "columns": [*QB, *OLINE, *TEAMMATES, *OWN_INJURY], "in_season": IN_SEASON,
        "label": "Personnel: all of it",
        "note": "D5: starting QB change and quality, offensive-line starters out, top teammate out, own injury history",
    },
    "qb": {
        "table": TABLE, "columns": QB,
        "label": "Starting quarterback",
        "note": "D5 sub-group: projected starter vs the QB of his last 4 games, games together, points-per-start gap, "
                "starter with < 8 career starts, (QB) is he the projected starter",
    },
    "oline": {
        "table": TABLE, "columns": OLINE, "in_season": OLINE,
        "label": "Offensive line out",
        "note": "D5 sub-group: line starters (top 5 by snaps, last 4 games) Out / Doubtful / reserve this week, their "
                "snap share, games since the starting five changed",
    },
    "teammates": {
        "table": TABLE, "columns": TEAMMATES, "in_season": TEAMMATES,
        "label": "Teammates out",
        "note": "D5 sub-group: leading teammate by target / carry share (last 4 games) out, target share of absent "
                "pass-catchers, live absence alert",
    },
    "own_injury": {
        "table": TABLE, "columns": OWN_INJURY,
        "label": "His injury history",
        "note": "D5 sub-group: games missed injured this / last season, weeks Questionable in a row, first game back "
                "after 2+, this week's designation and practice",
    },
}
