"""IQ-4 (Wave I-Q): what we know about the rest of the season — the one place for the numbers every screen that shows a
rest-of-season number says (Rankings' "Rest of season", ``/ros``, the free trade calculator's values); WORDS.md
§ "IQ-4". Read by ``rankings_api`` (the season view), ``ondemand.ros`` (``/api/ros``) and ``freetrade`` (each answer's
``ros_grade``).

The numbers (docs/METRICS.md § "v3.5: rest-of-season quarterbacks (IQ-1)", the horizon evaluation: 2021–2025, as of
weeks 3 / 5 / 7 / 9, both house scorings; v3.5 is candidate *ad*): a quarterback projection one week ahead (the market
week, with its betting line) misses by 6.44 points per game; two to eight weeks ahead (no line yet) by 7.56. Running
backs, receivers and tight ends lose about 0.2 between the two (pooled 2–8 minus next week, v3.5: RB 4.70 − 4.52,
WR 4.60 − 4.44, TE 3.41 − 3.25). Kickers and defenses (§ "Kickers and defenses beyond next week", IQ-4): their order two
to eight weeks ahead is no better than chance (rank correlation 0.03 and 0.04 with what they scored). As of 2026-10-07.
"""

from __future__ import annotations

import os

GRADED_ON = "2021–2025"
AS_OF = "2026-10-07"
SOURCE = "docs/METRICS.md § v3.5: rest-of-season quarterbacks (IQ-1); § Kickers and defenses beyond next week (IQ-4)"
QB_NEXT_WEEK_MAE = 6.44
QB_LATER_MAE = 7.56
OTHER_EXTRA_MAE = 0.2
KD_LATER_SPEARMAN = {"K": 0.03, "DEF": 0.04}

WORDS = (f"Beyond next week there is no betting line yet. Graded on {GRADED_ON}, a quarterback projection two to eight "
         f"weeks ahead misses by about {QB_LATER_MAE:.1f} points per game ({QB_NEXT_WEEK_MAE:.1f} for next week); "
         f"running backs, receivers and tight ends miss by about {OTHER_EXTRA_MAE:.1f} more than next week.")
KD_WORDS = (f"Kickers and defenses: graded on {GRADED_ON}, their order two to eight weeks ahead is no better than "
            "chance, so they have no rest-of-season ranking here.")
KD_CALC_WORDS = (f"Kickers and defenses: graded on {GRADED_ON}, their order two to eight weeks ahead is no better than "
                 "chance; read their numbers as a rough guide.")      # /ros and the calculator keep them

# ---- the K / DEF rest-of-season list on the public screens (METRICS § "Kickers and defenses beyond next week"):
# unset or "off" = not shown (the grade's recommendation; the PO decides), "on" = shown as before
KD_ROS_ENV = "LEAGUE_LAB_KD_ROS"


def kd_ros_shown() -> bool:
    return (os.environ.get(KD_ROS_ENV) or "off").strip().lower() in ("on", "1", "true", "yes")


def block(positions: tuple[str, ...] | list[str] | None = None, *, calc: bool = False) -> dict:
    """The answer's ``ros_grade``: the sentence, the K / DEF sentence when those positions are asked for, the source."""
    kd = bool(positions) and any(p in ("K", "DEF", "ALL") for p in positions)
    return {"words": WORDS, "kd_words": (KD_CALC_WORDS if calc else KD_WORDS) if kd else None, "graded_on": GRADED_ON, "as_of": AS_OF,
            "source": SOURCE, "qb_next_week_mae": QB_NEXT_WEEK_MAE, "qb_later_mae": QB_LATER_MAE,
            "other_extra_mae": OTHER_EXTRA_MAE, "kd_shown": kd_ros_shown()}
