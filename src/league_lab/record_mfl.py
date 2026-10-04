"""The decision record for MyFantasyLeague leagues (V-2, Wave I-H; docs/METRICS.md § "The decision record" → "Personal
and live"). An MFL league has no ``ops.lineups`` rows (the nightly does not price it), so its record is the ON-DEMAND
lineup (``anyleague._solve_roster``: the frame My Week serves), frozen under ``lineup.record_plan``: the next week to kick
off is written by every run before its first kickoff (``kickoff``) from the league's current rosters; a played week
with no rows is rebuilt once (``reconstructed``) from the rosters MFL's ``weeklyResults`` lists for it (every
franchise's starters and bench), priced on that week's frozen ``ops.projection_lines`` in the league's scoring, as of
one second before its first kickoff; a week MFL has not scored yet waits. Rows: ``ops.lineup_record`` with
``league_id = 'mfl:<id>'``; the calls' odds from the on-demand ranges. Written by ``league-lab validate`` for the keys
in ``LEAGUE_LAB_RECORD_MFL`` (or ``--mfl``). The grade (``mfl_load``) reads MFL's results through the league's own
translation; the API grades on request with it.

Its own module (not ``lineup`` / ``validation``, which the console imports): it reaches ``anyleague`` and MFL, and
``scripts/hosted_relations.py`` follows every import of a reader's modules.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

import pandas as pd
import psycopg

from . import anyleague as A
from . import lineup as LU
from . import platforms as PL
from . import scoring as S
from . import validation as V
from .mfl_client import _as_list
from .validation import frame_query

log = logging.getLogger(__name__)

KICKOFFS_SQL = """select week, home_team, away_team, kickoff_at from analytics.dim_game
                  where season = %s and season_type = 'REG'"""


def _season_games(query, season: int) -> dict[int, dict[str, datetime | None]]:
    g = query(KICKOFFS_SQL, (season,))
    games: dict[int, dict[str, datetime | None]] = defaultdict(dict)
    for r in g.itertuples(index=False):
        k = None if r.kickoff_at is None or pd.isna(r.kickoff_at) else pd.Timestamp(r.kickoff_at).to_pydatetime()
        games[int(r.week)][r.home_team] = k
        games[int(r.week)][r.away_team] = k
    return games


def mfl_week_rosters(router, key: str, week: int) -> list[dict] | None:
    """The league's rosters as MFL's ``weeklyResults`` list them for a played week (starters + nonstarters of every
    franchise, once each), Sleeper-shaped with no starters (the record is solved as of before kickoff). None when MFL
    has no results for the week."""
    lid = PL.mfl_id(key)
    try:
        res = router.mfl.client.weekly_results(lid, int(week))
    except Exception:  # noqa: BLE001 - MFL down / no such week: the week waits for the next run
        return None
    franchises = [f for m in _as_list(res.get("matchup")) for f in _as_list(m.get("franchise"))] + _as_list(res.get("franchise"))
    if not franchises:
        return None
    rid_of = router.mfl._rid_of(lid)                                      # noqa: SLF001 - the league's own roster ids
    by_f: dict[str, list[str]] = {}
    for f in franchises:
        fid = str(f.get("id"))
        if fid in rid_of and fid not in by_f:
            by_f[fid] = [str(p.get("id")) for p in _as_list(f.get("player"))]
    tr = router.mfl.translate(lid, sorted({i for ids in by_f.values() for i in ids}))
    return [{"league_id": key, "roster_id": rid_of[fid], "owner_id": fid, "players": [tr[i][0] for i in ids if i in tr],
             "starters": [], "reserve": None, "taxi": None} for fid, ids in sorted(by_f.items(), key=lambda x: rid_of[x[0]])]


def _priced_quantiles(pr) -> dict[str, dict]:
    """gsis -> p10..p90, team, opponent from an on-demand ``Priced`` (the card's odds inputs)."""
    out: dict[str, dict] = {}
    rg = getattr(pr, "ranges", None)
    if rg is None or rg.empty or not set(LU.QUANTILES) <= set(rg.columns):
        return out
    st = pr.board.status if getattr(pr.board, "status", None) is not None else pd.DataFrame()
    for g, r in rg.iterrows():
        team = st.loc[g].get("team") if g in st.index else None
        # the opponent is left out: the odds then treat the two players' weeks as unrelated unless teammates
        out[str(g)] = {**{q: LU._num(r[q]) for q in LU.QUANTILES}, "team": team, "opponent": None}
    return out


def mfl_record_rows(query, key: str, as_of: datetime, stored: Iterable[tuple[str, int]] = (), *, router=None) -> tuple[list[dict], dict]:
    """(``ops.lineup_record`` rows, the plan) for one MFL league under the freeze rule — reads only (the writer is
    ``write_mfl_record``; a test passes a stand-in ``query`` and the fixture router)."""
    router = router or A.sleeper()
    league = router.league(key)
    season = int(league["season"])
    scoring, slots = A.league_scoring(league)
    st = league.get("settings") or {}
    last_scored = int(st.get("last_scored_leg") or 0)
    po = int(st.get("playoff_week_start") or 0)
    games = _season_games(query, season)
    kickoffs = LU.first_kickoffs(games)
    reg = [w for w in sorted(kickoffs) if not po or w < po]
    plan = LU.record_plan({key: reg}, stored, kickoffs, as_of)
    router.rosters(key)                 # registers the league's team units and translates its players (My Week's order)
    out: list[dict] = []
    for (_lg, week), act in sorted(plan.items()):
        if act == "write":
            rosters, at, source = router.rosters(key), as_of, "kickoff"
        elif act == "reconstruct" and week <= last_scored:
            rosters, at, source = mfl_week_rosters(router, key, week), kickoffs[week] - timedelta(seconds=1), "reconstructed"
        else:
            continue
        if not rosters:
            continue
        players = router.players()      # after the translation: the directory carries this league's MFL-only rows
        pr = A.price_week(query, key, scoring, slots, season, week, cache=False)
        rows, totals = [], []
        for ro in rosters:
            r_, t_, *_ = A._solve_roster(query, key, ro, players, pr, slots, at)      # noqa: SLF001 - My Week's own solve
            rows += r_
            totals += t_
        mv = ",".join(sorted(set(pr.board.line["model_version"].dropna()))) if "model_version" in pr.board.line else None
        meta = {(key, week): {"first_kickoff_at": kickoffs[week], "model_version": mv,
                              "pricing": "ev" if S.ev_for_week(season, week) else "flat"}}
        out += LU.record_rows(rows, totals, meta, {(key, week): _priced_quantiles(pr)}, source, at)
    return out, plan


def write_mfl_record(conn: psycopg.Connection, keys: Iterable[str], as_of: datetime | None = None) -> dict[str, int]:
    """Write the MFL leagues' record (``mfl_record_rows``) in one transaction per league; a league that fails is
    logged and skipped (never fatal: MFL may be down). Returns key -> rows written."""
    as_of = as_of or datetime.now(UTC)
    q = frame_query(conn)
    done: dict[str, int] = {}
    for key in keys:
        try:
            with conn.cursor() as cur:
                cur.execute(LU.RECORD_DDL)
                cur.execute("select distinct league_id, week from ops.lineup_record where league_id = %s", (key,))
                stored = [(lg, int(w)) for lg, w in cur.fetchall()]
            rows, plan = mfl_record_rows(q, key, as_of, stored)
            write = sorted(w for (_, w), a in plan.items() if a == "write")
            for r in rows:
                r["run_at"] = as_of
            with conn.cursor() as cur:
                cur.execute("delete from ops.lineup_record where league_id = %s and week = any(%s)", (key, write))
                with cur.copy(f"copy ops.lineup_record ({', '.join(LU.RECORD_COLUMNS)}) from stdin") as cp:
                    for d in rows:
                        cp.write_row([d.get(c) for c in LU.RECORD_COLUMNS])
            conn.commit()
            done[key] = len(rows)
            log.info("decision record for %s: %s rows (%s)", key, len(rows),
                     {a: sorted(w for (_, w), b in plan.items() if b == a) for a in ("write", "reconstruct", "keep")})
        except Exception:
            conn.rollback()
            log.exception("decision record for %s failed (skipped)", key)
    return done


def run_mfl_record(keys: Iterable[str] | None = None, as_of: datetime | None = None) -> dict[str, int]:
    from .config import get_settings
    keys = list(keys) if keys is not None else LU.mfl_record_keys()
    if not keys:
        return {}
    with psycopg.connect(get_settings().pipeline_dsn(), autocommit=False) as conn:
        return write_mfl_record(conn, keys, as_of)


def mfl_load(key: str, record: pd.DataFrame, router=None) -> V.GradeInputs:
    """An MFL league's grade inputs: its record rows (RECORD_SQL's starters) and MFL's results for the recorded weeks it
    has scored (``last_scored_leg``), through the league's own translation (``anyleague.sleeper()``)."""
    router = router or A.sleeper()
    lid = PL.mfl_id(key)
    lg = router.league(key)
    last = int((lg.get("settings") or {}).get("last_scored_leg") or 0)
    weeks = sorted({int(w) for w in record["week"]}) if not record.empty else []
    results = {}
    for w in weeks:
        if w <= last:
            results[w] = router.mfl.client.weekly_results(lid, w)
    weekly, opt = V.mfl_weekly(key, results, lambda ids: router.mfl.translate(lid, ids),
                             router.mfl._rid_of(lid), range(1, last + 1))            # noqa: SLF001
    return V.mfl_inputs(record, weekly, opt)
