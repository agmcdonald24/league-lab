"""Offline fitting for ``scoring_ev`` (Wave I-C, M2; split out by the PO): the SQL and the database round trip live
here so the server's module names no play-level table — ``scripts/hosted_relations.py`` derives the hosted copy's
closure from the API's imports, and ``analytics.fct_play`` (233 MB) must never land in it. ``run_fit`` returns the
constants block to paste into ``scoring_ev`` (``CURVES`` / ``TD_SHARES``); ``scoring_ev.write_seed`` then regenerates
``dbt/seeds/scoring_distributions.csv``. About 6 CPU-minutes with ``OMP_NUM_THREADS=1``.
"""

from __future__ import annotations

import logging

from .scoring_ev import (
    FG_BUCKETS,
    constants_block,
    fit_curves,
    measure_fg_shares,
    measure_td_shares,
    td_distances,
)

log = logging.getLogger(__name__)

TD_PLAYS_SQL = """
select p.season, p.week, p.play_type, p.description, p.yards_gained, p.pass_touchdown, p.rush_touchdown,
       p.is_interception, p.fumble, pp.position as passer_position, rp.position as receiver_position,
       rr.position as rusher_position
from analytics.fct_play p
left join analytics.fct_player_game pp on pp.gsis_id = p.passer_player_id and pp.game_id = p.game_id
left join analytics.fct_player_game rp on rp.gsis_id = p.receiver_player_id and rp.game_id = p.game_id
left join analytics.fct_player_game rr on rr.gsis_id = p.rusher_player_id and rr.game_id = p.game_id
where p.touchdown and p.season between %s and %s and p.season_type = 'REG' and not coalesce(p.is_two_point, false)
"""
FG_SQL = f"""select {', '.join(f'sum({c})' for c, _ in FG_BUCKETS)} from analytics.fct_player_game
             where season between %s and %s and season_type = 'REG'"""


def run_fit(seasons: tuple[int, int] = (2019, 2025), scoring_league: str | None = None) -> str:
    """Offline: the walk-forward out-of-sample rows with the projected line (``calibration.oof_rows(lines=True)``,
    about 45 CPU-seconds per season with ``OMP_NUM_THREADS=1``) -> the curves; ``analytics.fct_play`` -> the TD
    shares. Returns the constants block (and logs it); the module is not rewritten in place."""
    import pandas as pd
    import psycopg

    from . import projections as P
    from .calibration import oof_rows
    from .config import get_settings

    lo, hi = seasons
    with psycopg.connect(get_settings().pipeline_dsn()) as conn:
        scorings = P.league_scorings(conn)
        alls = P.available_seasons(conn)
        frame = P.load_frame(conn, [s for s in alls if s <= hi])
        with conn.cursor() as cur:
            cur.execute(TD_PLAYS_SQL, (lo, hi))
            plays = pd.DataFrame(cur.fetchall(), columns=[c.name for c in cur.description])
            cur.execute(FG_SQL, (lo, hi))
            fg = dict(zip([c for c, _ in FG_BUCKETS], [float(v or 0) for v in cur.fetchone()], strict=True))
    lid = scoring_league or next(iter(scorings))
    rows = oof_rows(frame, list(range(lo, hi + 1)), {lid: scorings[lid]}, min(alls), ranges=False, lines=True)
    shares = measure_td_shares(td_distances(plays))
    shares[("fg_made", "ALL")] = measure_fg_shares(fg)
    block = constants_block(fit_curves(rows[rows["actual"].notna()]), shares)
    log.info("scoring_ev constants:\n%s", block)
    return block
