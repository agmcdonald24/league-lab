"""``league-lab validate`` (V-1, Wave I-G; V-2, Wave I-H): write the decision record, Sleeper's projections as a lineup
(``ops.decision_market``) and the MFL leagues' record, then grade it (``league_lab.validation``). Its own module: it
reads ``raw.sleeper_projections`` and reaches MFL, and the readers (the API, the console) import ``validation`` —
``scripts/hosted_relations.py`` would otherwise count the raw snapshots as theirs.

**Sleeper's projections as a lineup** (``write_market``; docs/METRICS.md § "The decision record" → "Personal and
live"): per record roster-week of a Sleeper league, the best lineup of the roster the record saw at Sleeper's
projection — the last snapshot fetched before the week's first kickoff — priced in the league's scoring the way the
record priced ours (``price_sleeper_lines``: ``scoring.price_projected`` in the week's ``pricing``, a K flat). Rebuilt
every run (recomputable from the archive's snapshots, so not record state).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime

import numpy as np
import pandas as pd
import psycopg

from . import scoring as S
from . import validation as V

log = logging.getLogger(__name__)

SLEEPER_LINES_SQL = """with k as (select season, week, min(kickoff_at) as first_kickoff_at from analytics.dim_game
                                  where season = %s and season_type = 'REG' group by 1, 2),
                       s as (select p.season, p.week, max(p.fetched_at) as fetched_at
                             from raw.sleeper_projections as p join k using (season, week)
                             where p.season_type = 'regular' and p.fetched_at < k.first_kickoff_at group by 1, 2)
                       select m.gsis_id, p.*
                       from raw.sleeper_projections as p join s using (season, week, fetched_at)
                       join analytics.player_id_map as m on m.sleeper_id = p.player_id
                       where p.season_type = 'regular' and p.position in ('QB', 'RB', 'WR', 'TE', 'K')"""
LEAGUES_SQL = """select league_id, scoring_settings, roster_positions from analytics.dim_league_season
                 where season = %s and league_id = any(%s)"""
ROSTER_SQL = """select league_id, season, week, roster_id, record_source, role, slot, sleeper_player_id, gsis_id,
                       player_name, position, value, value_source, reason, pricing
                from ops.lineup_record where season = %s and league_id = any(%s) and role in ('starter', 'bench', 'unplayable')"""
_LINE_META = ("gsis_id", "player_id", "sleeper_id", "position", "team", "opponent", "game_id", "company", "category",
              "proj_date", "fetched_at", "season", "season_type", "week", "pts_ppr", "pts_half_ppr", "pts_std")


def price_sleeper_lines(lines: pd.DataFrame, scoring: Mapping[str, float], ev: bool) -> dict[str, float]:
    """gsis -> Sleeper's line in this scoring (``why.market_points``' rule: ``scoring.price_projected``, QB-TE in the
    week's mode, a K flat)."""
    if lines is None or lines.empty:
        return {}
    df = lines.drop_duplicates("gsis_id", keep="first").reset_index(drop=True)
    cols = [c for c in df.columns if c not in _LINE_META]
    stats = df[cols].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    stats["position"] = df["position"].to_numpy()
    skill = stats["position"].isin(["QB", "RB", "WR", "TE"]).to_numpy()
    pts = np.zeros(len(stats))
    if skill.any():
        pts[skill] = S.price_projected(stats[skill], scoring, ev=ev)
    if (~skill).any():
        pts[~skill] = S.price_projected(stats[~skill], scoring, ev=False)
    return {str(g): round(float(p), 2) for g, p in zip(df["gsis_id"].to_numpy(), pts, strict=True)}


def write_market(conn, season: int, league_ids: Iterable[str]) -> int:
    """``ops.decision_market`` for the season's Sleeper leagues of the record, rebuilt (it is recomputable every night
    from ``raw.sleeper_projections``): delete the leagues' rows, insert. Returns the rows written."""
    ids = [str(x) for x in league_ids if not str(x).startswith("mfl:")]
    q = V.frame_query(conn)
    from .lineup import MARKET_DDL
    with conn.cursor() as cur:
        cur.execute(MARKET_DDL)
    if not ids:
        return 0
    lg = q(LEAGUES_SQL, (season, ids))
    leagues = {r.league_id: {"scoring": {k: float(v) for k, v in (V._json(r.scoring_settings) or {}).items() if v is not None},
                             "slots": [str(x) for x in (V._json(r.roster_positions) or [])]} for r in lg.itertuples(index=False)}
    lines = q(SLEEPER_LINES_SQL, (season,)) if V._has(q, "raw.sleeper_projections") else pd.DataFrame()
    rows = V.market_rows(q(ROSTER_SQL, (season, ids)), lines, leagues, datetime.now(UTC), price=price_sleeper_lines)
    with conn.cursor() as cur:
        cur.execute("delete from ops.decision_market where season = %s and league_id = any(%s)", (season, ids))
        with cur.copy(f"copy ops.decision_market ({', '.join(V.MARKET_COLUMNS)}) from stdin") as cp:
            for d in rows:
                cp.write_row([d.get(c) for c in V.MARKET_COLUMNS])
    conn.commit()
    log.info("Sleeper's lineup (ops.decision_market) for %s: %s rows", season, len(rows))
    return len(rows)


def validate(season: int | None = None, league_ids: Iterable[str] | None = None, write: bool = True,
             mfl: Iterable[str] | None = None) -> V.Validation | None:
    """``league-lab validate``: write the decision record (``lineup.run_record``: the next week's lineup before kickoff,
    reconstructed weeks once), then grade it on the scored weeks. V-2: also the MFL leagues' record (``mfl`` or
    ``LEAGUE_LAB_RECORD_MFL``), Sleeper's projections as a lineup (``ops.decision_market``) and, where this database
    has the event store, the news flag from it."""
    from . import lineup
    from .config import get_settings
    from .record_mfl import mfl_load, run_mfl_record

    run = lineup.run_record(season) if write else None
    mfl_keys = list(mfl) if mfl is not None else lineup.mfl_record_keys()          # ---- V-2
    if write and mfl_keys:
        run_mfl_record(mfl_keys)
    with psycopg.connect(get_settings().pipeline_dsn(), autocommit=False) as conn:
        q = V.frame_query(conn)
        if season is None:
            s = q("select max(season) as s from ops.lineup_record", ())
            season = None if s.empty or pd.isna(s.iloc[0]["s"]) else int(s.iloc[0]["s"])
        if season is None:
            log.warning("validate: the decision record is empty")
            return None
        ids = list(league_ids) if league_ids else q("select distinct league_id from ops.lineup_record where season = %s",
                                                   (season,))["league_id"].tolist()
        sl_ids = [i for i in ids if not str(i).startswith("mfl:")]
        if write:
            try:                                                                       # ---- V-2: never fatal
                write_market(conn, int(season), sl_ids)
            except Exception:
                conn.rollback()
                log.exception("Sleeper's lineup (ops.decision_market) failed; the grade goes on without it")
        g = V.load_inputs(q, int(season), sl_ids, events=True)
        mfl_rec = q(V.RECORD_SQL, (season, [i for i in ids if str(i).startswith("mfl:")])) if len(sl_ids) < len(ids) else None
        conn.commit()
    rw, calls = V.grade_roster_weeks(g), V.grade_calls(g)
    for key in [i for i in ids if str(i).startswith("mfl:")]:                          # ---- V-2: MFL leagues
        try:
            gm = mfl_load(key, mfl_rec[mfl_rec["league_id"] == key])
        except Exception:
            log.exception("validate: %s could not be graded (MFL unreachable?)", key)
            continue
        rw = pd.concat([rw, V.grade_roster_weeks(gm)], ignore_index=True)
        calls = pd.concat([calls, V.grade_calls(gm)], ignore_index=True)
    by_league = {lg: V.summary(rw[rw["league_id"] == lg], calls[calls["league_id"] == lg]) for lg in ids}
    return V.Validation(int(season), run, rw, calls, by_league)
