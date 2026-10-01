"""Feature group ``oline_quality`` (plan E4, Wave E): WHO on the offensive line is out, not just how many.

Andrew: "are you treating everything equal? ... a really good lineman vs a replacement-level one". D5's ``oline``
(dropped at every position) counted the line's starters out this week and summed their snap share over the last
four games: a ten-year left tackle and a second-year guard weighed the same. This group adds how good the absent
starters are, as of the week:

* ``pn_olq_career_starts_out`` - the out starters' career starts before the week (games with >= 50% of the
  offensive snaps, any team, since 2016: a veteran from before 2016 is undercounted, as D5's QB starts are);
* ``pn_olq_draft_capital_out`` - the sum of their draft score (1st round 3, day 2 2, day 3 1, undrafted 0);
* ``pn_olq_best_out`` - the rank, among the five starters, of the best one out by last season's snaps
  (1 = the line's most-used lineman last season ... 5; 0 = nobody out);
* ``pn_olq_prev_season_share_out`` - the sum of their last-season snaps in season-equivalents (1 = every snap);
* plus D5's count and window snap share (``pn_olq_starters_out`` / ``pn_olq_snap_share_out``, copies of
  ``pn_ol_starters_out`` / ``pn_ol_snap_share_out``) so the trees can weigh count against quality.

The table is ``intermediate.int_e4_player_week_oline_quality`` (dbt; helper ``int_e4_ol_starter_week``: the five
starters per team-week, D5's rule, with each one's quality). NULL exactly where D5's count is NULL (week 1, or the
week's injury report not out). Definitions: ``docs/METRICS.md`` § "Feature experiments" -> "Wave E groups".
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

TABLE = "intermediate.int_e4_player_week_oline_quality"
START_SHARE = 0.5      # a start: >= 50% of the team's offensive snaps in the game


def draft_score(draft_round: int | None) -> int:
    """1st round 3, day 2 (rounds 2-3) 2, day 3 (rounds 4-7) 1, undrafted / unknown 0."""
    if draft_round is None:
        return 0
    return 3 if draft_round == 1 else 2 if draft_round <= 3 else 1 if draft_round <= 7 else 0


@dataclass(frozen=True)
class Starter:
    gsis_id: str
    window_share: float          # snap share over the team's last four played games (D5: picks the five)
    out: bool                    # Out / Doubtful / reserve this week (D5's rule)
    career_starts: int           # starts before the week
    draft_round: int | None
    prev_season_share: float     # last season's snaps in season-equivalents


def quality_ranks(five: Sequence[Starter]) -> dict[str, int]:
    """1-5 among the five by last season's snaps (ties: window share, then gsis_id): 1 = the most-used."""
    order = sorted(five, key=lambda s: (-s.prev_season_share, -s.window_share, s.gsis_id))
    return {s.gsis_id: i + 1 for i, s in enumerate(order)}


def oline_quality_out(five: Sequence[Starter], report_known: bool = True) -> dict[str, float] | None:
    """The group's columns for one team-week from its five starters; None when the week's report is not out or
    there is no window (week 1)."""
    if not report_known or not five:
        return None
    ranks = quality_ranks(five)
    out = [s for s in five if s.out]
    return {
        "pn_olq_starters_out": len(out),
        "pn_olq_career_starts_out": sum(s.career_starts for s in out),
        "pn_olq_draft_capital_out": sum(draft_score(s.draft_round) for s in out),
        "pn_olq_best_out": min((ranks[s.gsis_id] for s in out), default=0),
        "pn_olq_prev_season_share_out": round(sum(s.prev_season_share for s in out), 4),
    }


COLUMNS = ["pn_olq_starters_out", "pn_olq_snap_share_out", "pn_olq_career_starts_out", "pn_olq_draft_capital_out",
           "pn_olq_best_out", "pn_olq_prev_season_share_out"]

GROUPS = {
    "oline_quality": {
        "table": TABLE, "columns": COLUMNS, "in_season": COLUMNS,
        "label": "Offensive line out, weighted by quality",
        "note": "E4: the line's starters out this week (D5's count and snap share) plus how good they are - career "
                "starts, draft capital, last season's snaps, the rank of the best one out",
    },
}
