"""Feature group ``qb_x_offense`` (plan E4, Wave E): the quarterback gap times how good the offense is.

Andrew: "are you treating everything equal? an elite QB going down on an elite offense vs a bad QB on a bad
offense". v3.0's QB inputs already weigh the starter's quality: ``pn_qb_prev_ppg_diff`` = points per start of this
week's projected starter minus the usual QB's (D5), and the gradient-boosted trees can split on it and on the
Vegas implied total together. Whether they do is the question; this group hands them the products explicitly:

* ``qbx_gap_x_implied`` = ``pn_qb_prev_ppg_diff`` x ``implied_team_total``;
* ``qbx_gap_x_total`` = ``pn_qb_prev_ppg_diff`` x ``total_line``;
* ``qbx_gap_x_prev_ppg`` = ``pn_qb_prev_ppg_diff`` x the team's points per game last regular season;
* ``qbx_backup_x_implied`` = ``pn_qb_is_rookie_or_backup`` x ``implied_team_total``;
* ``qbx_gap_x_prev_epa`` = the gap x the team's EPA per play last regular season (``fct_team_game``);
* ``qbx_gap_bucket`` = the gap in four steps (``gap_bucket``): big drop / some drop / like for like / upgrade.

The group is the five products and the bucket, at every position: at QB the factors are already inputs (a pure interaction
test); at RB / WR / TE the gap is not a v3 input (D5's ``qb`` dropped there, +0.001 at WR over five seasons), and a
product carries it scaled by the offense - which is the hypothesis. The table also keeps the factors
``qbx_qb_gap`` (a copy of ``pn_qb_prev_ppg_diff``), ``qbx_prev_team_ppg`` and ``qbx_prev_team_epa_play`` for hand checks; they are not in the
group (last season's team points alone would be a new team-strength input, a different question).

The table is ``intermediate.int_e4_player_week_qb_x_offense`` (dbt; the harness joins a group from one table, so
the products are materialized there). Definitions: ``docs/METRICS.md`` § "Feature experiments" -> "Wave E groups".
"""

from __future__ import annotations

TABLE = "intermediate.int_e4_player_week_qb_x_offense"


def product(a: float | None, b: float | None) -> float | None:
    """NULL when either factor is unknown (rounded to 3 decimals, as the SQL)."""
    return None if a is None or b is None else round(a * b, 3)


def gap_bucket(gap: float | None) -> int | None:
    """2 = big drop (<= -6 points per start: a good starter replaced by a much worse one), 1 = some drop (-6, -2],
    0 = like for like (-2, +2): the usual QB, or a backup for a backup), -1 = upgrade (>= +2); None = unknown."""
    if gap is None:
        return None
    return 2 if gap <= BIG_DROP else 1 if gap <= -LIKE_FOR_LIKE else 0 if gap < LIKE_FOR_LIKE else -1


BIG_DROP = -6.0          # points per start
LIKE_FOR_LIKE = 2.0      # |gap| below this: the same quality of quarterback
INTERACTIONS = ["qbx_gap_x_implied", "qbx_gap_x_total", "qbx_gap_x_prev_ppg", "qbx_backup_x_implied", "qbx_gap_x_prev_epa"]
COLUMNS = [*INTERACTIONS, "qbx_gap_bucket"]

GROUPS = {
    "qb_x_offense": {
        "table": TABLE, "columns": COLUMNS,
        "label": "Quarterback change times the offense",
        "note": "E4: the starting-QB quality gap (points per start, projected starter minus usual QB) times the "
                "implied team total, the game total and last season's team points per game; a rookie / backup "
                "starter times the implied total",
    },
}
