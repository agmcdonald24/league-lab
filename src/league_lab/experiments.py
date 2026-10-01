"""Feature-group harness (plan D1, Wave D / projection v3).

A *feature group* is a table of as-of inputs at the projection's grain, ``(gsis_id, season, week)``,
plus the columns to try. The harness answers one question per group and position: does projection v2
get better when it can also see these columns? It fits the v2 model exactly as ``backtest-v2`` does
(``projections.walk_forward``: per position, components + interval models + conformal widening, trained
on the seasons before each test season) twice, with the production inputs (``FEATURES_BY_POSITION``, the
*baseline*, cached) and with those + the group's columns, scores both with ``projections.score_predictions`` on the same played
player-weeks, and applies a paired decision rule across the test seasons.

Registering a group
-------------------
Add a module under ``league_lab/feature_groups/`` (one per group family, so parallel branches never edit
the same lines) that defines ``GROUPS = {name: spec}``::

    GROUPS = {
        "weather": {
            "table": "intermediate.int_player_week_weather",   # schema.table at (gsis_id, season, week) grain
            "columns": ["wx_wind_mph", "wx_temp_f"],            # numeric or boolean; added to FEATURES
            "positions": ["QB", "WR", "TE"],                     # optional, default all four
            "in_season": [],                                     # optional: columns built from this season's games
                                                                 # (must be NULL in week 1: the no-peek check)
            "label": "Weather",                                  # optional: plain words for the Rankings page
            "note": "wind and temperature by stadium and kickoff hour",
        },
    }

A group whose table is derived from the model itself (plan E4's ``player_prior``: the production model's
out-of-fold residuals) adds ``"build": callable(conn)`` to its spec: ``get_group`` calls it first, and it
(re)builds the table when it is missing or stale; the table is then checked and joined like any other.

The no-peek check (``no_peek_check``) runs on the group's table before anything is fitted; a group that
fails it is refused. See ``docs/METRICS.md`` § "Feature experiments" for the rule and the checks.

Outputs: ``ops.feature_experiments`` (one row per run x group x position x league x test season; the
baseline's rows are ``feature_group = 'baseline'``), published by ``analytics.mart_feature_experiments``.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import logging
import math
import pkgutil
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime

import numpy as np
import pandas as pd
import psycopg
from psycopg import sql

from . import projections as P

log = logging.getLogger(__name__)

HARNESS_VERSION = "fx1.0"
DEFAULT_TEST_SEASONS = (2023, 2024, 2025)
BASELINE = "baseline"
UNIVERSE = "intermediate.int_player_week_universe"

# The decision rule (docs/METRICS.md § "Feature experiments"): per position, paired across test seasons.
KEEP_SPEARMAN = 0.005     # mean ΔSpearman at least this ...
KEEP_MAE = -0.05          # ... or mean ΔMAE at most this (points) ...
# ... AND better in at least ceil(2/3 of the test seasons) of them (2 of 3).

# The outcome probe of the no-peek check. Calibrated on the production inputs (mart_player_week_features,
# 2016-2026, per position): the largest excess of |corr with this week's points| over |corr with the
# adjacent weeks' points| is 0.047 (opp_allowed_std, QB); the game's own stats score 0.11 (QB carries) to
# 0.52 (WR receiving yards), the week's own points 0.52-0.66.
PROBE_MIN_ROWS = 500
PROBE_EXCESS = 0.10

FEATURE_GROUPS: dict[str, dict] = {}


class GroupError(ValueError):
    """A group that cannot be evaluated (unknown, malformed, or its table / columns are missing)."""


class NoPeekError(GroupError):
    """The group's table failed the no-peek check: refused."""


# ------------------------------------------------------------------------------ registry
def load_registry() -> dict[str, dict]:
    """Collect ``GROUPS`` from every module of ``league_lab.feature_groups`` (idempotent)."""
    from . import feature_groups

    found: dict[str, dict] = {}
    for mod in sorted(pkgutil.iter_modules(feature_groups.__path__), key=lambda m: m.name):
        groups = getattr(importlib.import_module(f"{feature_groups.__name__}.{mod.name}"), "GROUPS", {})
        for name, spec in groups.items():
            if name in found:
                raise GroupError(f"feature group {name!r} is registered twice (feature_groups/{mod.name}.py and another module)")
            found[name] = dict(spec, module=mod.name)
    FEATURE_GROUPS.clear()
    FEATURE_GROUPS.update(found)
    return FEATURE_GROUPS


@dataclass
class GroupSpec:
    name: str
    table: str
    columns: list[str]
    positions: tuple[str, ...] = P.POSITIONS
    in_season: list[str] = field(default_factory=list)
    label: str = ""
    note: str = ""


def check_spec(name: str, spec: dict, table_columns: dict[str, str] | None) -> GroupSpec:
    """Validate a registry entry against the table's columns (``{column: data_type}``, None = no such
    table). Raises ``GroupError`` with a message that says what to fix."""
    if name == BASELINE:
        raise GroupError(f"{BASELINE!r} is reserved for the no-extra-features run")
    for key in ("table", "columns"):
        if not spec.get(key):
            raise GroupError(f"group {name!r}: '{key}' is required (table = 'schema.table', columns = [...])")
    table = spec["table"]
    if not isinstance(table, str) or table.count(".") != 1:
        raise GroupError(f"group {name!r}: table must be 'schema.table', got {table!r}")
    cols = list(spec["columns"])
    if len(set(cols)) != len(cols):
        raise GroupError(f"group {name!r}: duplicate columns {sorted({c for c in cols if cols.count(c) > 1})}")
    positions = tuple(spec.get("positions") or P.POSITIONS)
    bad = [p for p in positions if p not in P.POSITIONS]
    if bad:
        raise GroupError(f"group {name!r}: unknown positions {bad} (allowed: {list(P.POSITIONS)})")
    # v3: a column that is already a production input at one of the group's positions (FEATURES_BY_POSITION) is a clash
    shipped = {f for p in positions for f in P.FEATURES_BY_POSITION[p]}
    clash = [c for c in cols if c in shipped or c in ("gsis_id", "season", "week", "position", "played", "points_actual")]
    if clash:
        raise GroupError(f"group {name!r}: {clash} are already model inputs or keys; prefix the group's columns (gc_, wx_, ts_ ...)")
    in_season = list(spec.get("in_season") or [])
    stray = [c for c in in_season if c not in cols]
    if stray:
        raise GroupError(f"group {name!r}: in_season columns {stray} are not in its columns")
    if table_columns is None:
        raise GroupError(f"group {name!r}: table {table} does not exist (build it: league-lab dbt build --select <model>)")
    missing_keys = [k for k in ("gsis_id", "season", "week") if k not in table_columns]
    if missing_keys:
        raise GroupError(f"group {name!r}: {table} lacks the grain columns {missing_keys}")
    missing = [c for c in cols if c not in table_columns]
    if missing:
        raise GroupError(f"group {name!r}: {table} has no columns {missing}")
    numeric = ("smallint", "integer", "bigint", "numeric", "real", "double precision", "boolean")
    wrong = [f"{c} ({table_columns[c]})" for c in cols if table_columns[c] not in numeric]
    if wrong:
        raise GroupError(f"group {name!r}: columns must be numeric or boolean: {wrong}")
    return GroupSpec(name, table, cols, positions, in_season, spec.get("label") or name, spec.get("note", ""))


def describe_table(conn: psycopg.Connection, table: str) -> dict[str, str] | None:
    """``{column: type}`` of a table or view (``pg_temp.x`` too), None when it does not exist."""
    with conn.cursor() as cur:
        cur.execute("""select a.attname, format_type(a.atttypid, null) from pg_attribute as a
                       where a.attrelid = to_regclass(%s) and a.attnum > 0 and not a.attisdropped order by a.attnum""",
                    (str(_ident(table).as_string(conn)),))
        rows = cur.fetchall()
    return {r[0]: r[1] for r in rows} if rows else None


def get_group(conn: psycopg.Connection, name: str) -> GroupSpec:
    reg = load_registry()
    if name not in reg:
        raise GroupError(f"unknown feature group {name!r}; registered: {sorted(reg) or 'none'} (league-lab experiment --list)")
    spec = reg[name]
    if callable(spec.get("build")):
        # plan E4: a group derived from the model itself (player_prior: its out-of-fold residuals) is not a dbt model;
        # its ``build(conn)`` (re)builds the table when it is missing or stale, before the table is read or checked
        spec["build"](conn)
    table = spec.get("table")
    cols = describe_table(conn, table) if isinstance(table, str) and table.count(".") == 1 else None
    return check_spec(name, spec, cols)


# ------------------------------------------------------------------------------ the no-peek check
@dataclass
class NoPeekReport:
    group: str
    failures: list[str] = field(default_factory=list)   # any -> refused
    warnings: list[str] = field(default_factory=list)
    probe: pd.DataFrame | None = None

    @property
    def ok(self) -> bool:
        return not self.failures


def _ident(table: str) -> sql.Composed:
    schema, name = table.split(".", 1)
    return sql.SQL("{}.{}").format(sql.Identifier(schema), sql.Identifier(name))


def judge_probe(probe: pd.DataFrame) -> list[str]:
    """The outcome probe's verdict. ``probe``: one row per position x column with ``n``, ``r_same``
    (corr with the same week's points), ``r_prev`` / ``r_next`` (with the player's previous / next played
    week in the season). An input known before kickoff tracks this week's points barely more than the
    neighbouring weeks' (a week-specific input, the opponent or the Vegas line, earns a few hundredths); one
    built from the game itself jumps. Refused: |r_same| - max(|r_prev|, |r_next|) >= PROBE_EXCESS."""
    out = []
    for r in probe.itertuples(index=False):
        if r.n < PROBE_MIN_ROWS or r.r_same is None or (isinstance(r.r_same, float) and math.isnan(r.r_same)):
            continue
        same = abs(r.r_same)
        adj = max(abs(r.r_prev) if pd.notna(r.r_prev) else 0.0, abs(r.r_next) if pd.notna(r.r_next) else 0.0)
        if same - adj >= PROBE_EXCESS:
            out.append(f"{r.column} ({r.position}): corr with the same week's points {r.r_same:+.2f} vs "
                       f"{adj:.2f} with the adjacent weeks (n={r.n}): it looks built from the game itself")
    return out


def outcome_probe(conn: psycopg.Connection, spec: GroupSpec) -> pd.DataFrame:
    """Per position x column: corr of the input with the player's points this week, his previous and his
    next played week (same rows for all three; reference scoring, ``mart_player_week_features.points_actual``)."""
    t = _ident(spec.table)
    types = describe_table(conn, spec.table) or {}
    sels, names = [], []
    for c in spec.columns:
        ci = sql.Identifier(c)
        x = sql.SQL("f.{c}::int::float8" if types.get(c) == "boolean" else "f.{c}::float8").format(c=ci)   # boolean -> 0/1
        sels += [sql.SQL("count(f.{c})").format(c=ci),
                 sql.SQL("corr({x}, o.y)").format(x=x),
                 sql.SQL("corr({x}, o.y_prev)").format(x=x),
                 sql.SQL("corr({x}, o.y_next)").format(x=x)]
        names.append(c)
    q = sql.SQL("""
        with o as (
            select gsis_id, season, week, position, points_actual::float8 as y,
                   lag(points_actual::float8) over w as y_prev, lead(points_actual::float8) over w as y_next
            from analytics.mart_player_week_features
            where played and points_actual is not null and position = any(%s)
            window w as (partition by gsis_id, season order by week))
        select o.position, {sels}
        from o join {t} as f using (gsis_id, season, week)
        where o.y_prev is not null and o.y_next is not null
        group by o.position order by o.position""").format(sels=sql.SQL(", ").join(sels), t=t)
    with conn.cursor() as cur:
        cur.execute(q, (list(spec.positions),))
        rows = cur.fetchall()
    out = []
    for r in rows:
        for i, c in enumerate(names):
            n, rs, rp, rn = r[1 + 4 * i: 5 + 4 * i]
            out.append({"position": r[0], "column": c, "n": int(n),
                        "r_same": None if rs is None else float(rs), "r_prev": None if rp is None else float(rp),
                        "r_next": None if rn is None else float(rn)})
    return pd.DataFrame(out, columns=["position", "column", "n", "r_same", "r_prev", "r_next"])


def no_peek_check(conn: psycopg.Connection, spec: GroupSpec) -> NoPeekReport:
    """The harness's version of ``dbt/tests/assert_features_never_peek.sql``, generic over a group's table.

    Refused (failures):
      1. grain: duplicate ``(gsis_id, season, week)`` rows;
      2. rows outside the projection universe (``int_player_week_universe``): a feature for a player-week
         the model never sees is a join error;
      3. as-of marker: any column named ``*asof_week`` must be < week (the dbt test's first clause);
      4. week 1: the group's ``in_season`` columns (built from this season's games) must be NULL in week 1
         (the dbt test's second clause: nothing in-season is known before the first game);
      5. the outcome probe (``judge_probe``): an input that tracks the same week's points 0.10 more than the
         adjacent weeks' was built from the game itself (a planted ``points_actual`` is caught at r = 1.0).
    Warned (recorded, not refused):
      6. coverage: universe rows the table lacks (their features are NULL);
      7. serve gap: on the newest season, a column known on most played weeks but on none of the rows of
         the next unplayed week is only known after the game (observed weather): training sees something
         the live board will not.
    """
    rep = NoPeekReport(spec.name)
    t = _ident(spec.table)
    with conn.cursor() as cur:
        cur.execute(sql.SQL("select count(*) from (select 1 from {t} group by gsis_id, season, week having count(*) > 1) d").format(t=t))
        dup = cur.fetchone()[0]
        if dup:
            rep.failures.append(f"grain: {dup} duplicate (gsis_id, season, week) keys")
        cur.execute(sql.SQL("""select count(*) filter (where u.gsis_id is null), count(*) from {t} as f
                               left join {u} as u using (gsis_id, season, week)""").format(t=t, u=_ident(UNIVERSE)))
        outside, total = cur.fetchone()
        if outside:
            rep.failures.append(f"universe: {outside} of {total} rows are not player-weeks of {UNIVERSE}")
        cur.execute(sql.SQL("""select count(*) from {u} as u where u.season >= (select min(season) from {t})
                               and not exists (select 1 from {t} as f where (f.gsis_id, f.season, f.week) = (u.gsis_id, u.season, u.week))""")
                    .format(t=t, u=_ident(UNIVERSE)))
        missing = cur.fetchone()[0]
        if missing:
            rep.warnings.append(f"coverage: {missing} universe player-weeks have no row (their features are NULL)")
        cols = describe_table(conn, spec.table) or {}
        for c in [c for c in cols if c.endswith("asof_week")]:
            cur.execute(sql.SQL("select count(*) from {t} where {c} >= week").format(t=t, c=sql.Identifier(c)))
            n = cur.fetchone()[0]
            if n:
                rep.failures.append(f"as-of: {n} rows with {c} >= week (a week-N row may only use games before week N)")
        if spec.in_season:
            cond = sql.SQL(" or ").join(sql.SQL("{} is not null").format(sql.Identifier(c)) for c in spec.in_season)
            cur.execute(sql.SQL("select count(*) from {t} where week = 1 and ({cond})").format(t=t, cond=cond))
            n = cur.fetchone()[0]
            if n:
                rep.failures.append(f"week 1: {n} rows carry in-season values ({', '.join(spec.in_season)}) before any game was played")
        # 7. serve gap on the newest season: the first week nobody has played yet
        cur.execute("""select max(season) from analytics.mart_player_week_features""")
        season = cur.fetchone()[0]
        cur.execute("""select min(week) from (select week from analytics.mart_player_week_features where season = %s
                       group by week having not bool_or(played)) w""", (season,))
        next_week = cur.fetchone()[0]
        if next_week is not None:
            share = sql.SQL(", ").join(
                sql.SQL("avg(({c} is not null)::int) filter (where m.played), avg(({c} is not null)::int) filter (where f.week = %s)")
                .format(c=sql.SQL("f.") + sql.Identifier(c)) for c in spec.columns)
            cur.execute(sql.SQL("""select {share} from {t} as f
                                   left join analytics.mart_player_week_features as m using (gsis_id, season, week)
                                   where f.season = %s""").format(share=share, t=t),
                        (*[next_week] * len(spec.columns), season))
            r = cur.fetchone()
            for i, c in enumerate(spec.columns):
                played, upcoming = r[2 * i], r[2 * i + 1]
                if played is not None and float(played) >= 0.5 and (upcoming is None or float(upcoming) == 0.0):
                    rep.warnings.append(f"serve gap: {c} is known on {float(played):.0%} of {season}'s played rows but on none of "
                                        f"week {next_week}'s (not played yet): known only after the game")
    rep.probe = outcome_probe(conn, spec)
    rep.failures += judge_probe(rep.probe)
    return rep


# ------------------------------------------------------------------------------ the decision rule
def seasons_needed(n_seasons: int) -> int:
    """'At least 2 of 3': ceil(2/3 of the test seasons)."""
    return max(1, math.ceil(2 * n_seasons / 3))


def decide(per_season: pd.DataFrame) -> pd.DataFrame:
    """Per position, from one row per position x test season with ``delta_spearman`` and ``delta_mae``
    (group - baseline, averaged over the leagues: the season is the paired unit).

    * helps: mean ΔSpearman >= +0.005 and better (Δ > 0) in >= ceil(2n/3) seasons, OR mean ΔMAE <= -0.05
      and better (Δ < 0) in >= ceil(2n/3) seasons;
    * hurts: the mirror image (mean ΔSpearman <= -0.005 and worse in >= ceil(2n/3), or mean ΔMAE >= +0.05 ...);
    * decision: keep = helps and not hurts; mixed = both (better order, bigger miss, or the reverse);
      drop = otherwise (no consistent gain is a drop: the group costs inputs for nothing).
    """
    rows = []
    for pos, g in per_season.groupby("position", sort=False):
        n = len(g)
        need = seasons_needed(n)
        ds, dm = g["delta_spearman"].astype(float), g["delta_mae"].astype(float)
        better_s, worse_s = int((ds > 0).sum()), int((ds < 0).sum())
        better_m, worse_m = int((dm < 0).sum()), int((dm > 0).sum())
        helps = (ds.mean() >= KEEP_SPEARMAN and better_s >= need) or (dm.mean() <= KEEP_MAE and better_m >= need)
        hurts = (ds.mean() <= -KEEP_SPEARMAN and worse_s >= need) or (dm.mean() >= -KEEP_MAE and worse_m >= need)
        decision = "mixed" if helps and hurts else "keep" if helps else "drop"
        rows.append({"position": pos, "n_seasons": n, "delta_spearman": float(ds.mean()), "delta_mae": float(dm.mean()),
                     "seasons_better_spearman": better_s, "seasons_better_mae": better_m,
                     "helps": bool(helps), "hurts": bool(hurts), "decision": decision})
    return pd.DataFrame(rows, columns=["position", "n_seasons", "delta_spearman", "delta_mae", "seasons_better_spearman",
                                       "seasons_better_mae", "helps", "hurts", "decision"])


def group_verdict(decisions: pd.DataFrame) -> str:
    """keep: helps at least one position and hurts none; mixed: helps one, hurts another (the PO decides
    per position); drop: helps none."""
    helps, hurts = bool(decisions["helps"].any()), bool(decisions["hurts"].any())
    if helps and hurts:
        return "mixed"
    return "keep" if helps else "drop"


# ------------------------------------------------------------------------------ running it
METRICS = ["spearman", "hit_rate", "mae", "coverage_80", "interval_width", "interval_score"]

DDL = """create table if not exists ops.feature_experiments (
    run_id text, run_at timestamptz, model_version text, harness_version text, feature_group text, group_table text,
    group_columns text, test_seasons text, train_seasons text, data_key text, position text, league_id text,
    test_season integer, n_weeks integer, n_player_weeks integer,
    spearman double precision, hit_rate double precision, mae double precision, coverage_80 double precision,
    interval_width double precision, interval_score double precision,
    baseline_spearman double precision, baseline_hit_rate double precision, baseline_mae double precision,
    baseline_coverage_80 double precision, baseline_interval_width double precision, baseline_interval_score double precision,
    delta_spearman double precision, delta_hit_rate double precision, delta_mae double precision,
    delta_coverage_80 double precision, delta_interval_width double precision, delta_interval_score double precision,
    decision text, group_verdict text, runtime_s double precision, no_peek_warnings text, label text, note text)"""


def summarize_scores(res: pd.DataFrame) -> pd.DataFrame:
    """Per league x test season x position: the mean over the season's weeks of the priced line's scores
    (scorer ``v2_points``, what the board ranks by) and of the interval's (interval score = mean pinball
    loss at 0.1 and 0.9, in points: lower is a sharper range at the same honesty)."""
    r = res[res["scorer"] == "v2_points"].copy()
    r["interval_score"] = (r["pinball_10"].astype(float) + r["pinball_90"].astype(float)) / 2
    g = r.groupby(["league_id", "season", "position"])
    out = g.agg(n_weeks=("week", "count"), n_player_weeks=("n_players", "sum"), train_seasons=("train_seasons", "first"),
                **{m: (m, "mean") for m in METRICS}).reset_index()
    return out.rename(columns={"season": "test_season"})


def data_key(frame: pd.DataFrame, test_seasons: tuple[int, ...], scorings: dict) -> str:
    """What the cached baseline depends on: the model (version, inputs, hyperparameters), the test seasons,
    the leagues' scoring and the training data (rows and points), so a rebuilt mart invalidates it."""
    payload = json.dumps({"mv": P.MODEL_VERSION, "hv": HARNESS_VERSION, "features": P.FEATURES, "features_by_position": P.FEATURES_BY_POSITION, "hgb": P.HGB,
                          "seasons": list(test_seasons), "scorings": {k: v[1] for k, v in sorted(scorings.items())},
                          "rows": len(frame), "points": round(float(frame["points_actual"].fillna(0).sum()), 2),
                          "played": int(frame["played"].fillna(False).sum())}, sort_keys=True, default=str)
    return hashlib.md5(payload.encode()).hexdigest()[:16]


def _seasons_label(test_seasons: tuple[int, ...]) -> str:
    return ",".join(str(s) for s in sorted(test_seasons))


def _scorings(conn: psycopg.Connection, leagues: list[str] | None) -> dict[str, tuple[str, dict[str, float]]]:
    scorings = P.league_scorings(conn)
    if leagues:
        unknown = [lg for lg in leagues if lg not in scorings]
        if unknown:
            raise GroupError(f"leagues {unknown} are not current leagues ({list(scorings)})")
        scorings = {k: v for k, v in scorings.items() if k in leagues}
    return scorings


def _write_rows(conn: psycopg.Connection, df: pd.DataFrame, group: str, mv: str, seasons: str, leagues: list[str]) -> None:
    with conn.cursor() as cur:
        cur.execute(DDL)
        cur.execute("select column_name from information_schema.columns where table_schema = 'ops' and table_name = 'feature_experiments'")
        cols = [r[0] for r in cur.fetchall() if r[0] in df.columns]
        cur.execute("""delete from ops.feature_experiments where feature_group = %s and model_version = %s and test_seasons = %s
                       and league_id = any(%s)""", (group, mv, seasons, leagues))
        with cur.copy(sql.SQL("copy ops.feature_experiments ({}) from stdin").format(sql.SQL(", ").join(sql.Identifier(c) for c in cols))) as cp:
            for r in df[cols].itertuples(index=False, name=None):
                cp.write_row(tuple(None if (isinstance(v, float) and np.isnan(v)) else v for v in r))
    conn.commit()


def _cached_baseline(conn: psycopg.Connection, key: str, seasons: str, leagues: list[str]) -> pd.DataFrame | None:
    with conn.cursor() as cur:
        cur.execute(DDL)
        cur.execute("""select * from ops.feature_experiments where feature_group = %s and model_version = %s and test_seasons = %s
                       and data_key = %s and league_id = any(%s)""", (BASELINE, P.MODEL_VERSION, seasons, key, leagues))
        df = pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])
    conn.commit()
    if df.empty:
        return None
    want = len(leagues) * len(seasons.split(",")) * len(P.POSITIONS)
    return df if len(df) == want else None


@dataclass
class Context:
    """One harness session: the frame (with every requested group's columns joined), the leagues, the
    baseline. Several groups share one Context so the data is read and the baseline fitted once."""
    test_seasons: tuple[int, ...]
    scorings: dict
    first: int
    frame: pd.DataFrame
    key: str
    baseline: pd.DataFrame | None = None
    baseline_seconds: float | None = None


def prepare(conn: psycopg.Connection, specs: list[GroupSpec], test_seasons: tuple[int, ...] = DEFAULT_TEST_SEASONS,
            leagues: list[str] | None = None) -> Context:
    scorings = _scorings(conn, leagues)
    all_seasons = P.available_seasons(conn)
    first = min(all_seasons)
    extra: dict[str, list[str]] = {}
    for s in specs:
        extra.setdefault(s.table, [])
        extra[s.table] += [c for c in s.columns if c not in extra[s.table]]
    frame = P.load_frame(conn, [s for s in all_seasons if s <= max(test_seasons)], extra_tables=extra or None)
    return Context(tuple(sorted(test_seasons)), scorings, first, frame, data_key(frame, tuple(sorted(test_seasons)), scorings))


def _fit_and_score(ctx: Context, features: list[str] | dict[str, list[str]] | None, positions: tuple[str, ...]) -> pd.DataFrame:
    res, _ = P.walk_forward(ctx.frame, list(ctx.test_seasons), ctx.scorings, ctx.first, None, features=features, positions=positions)
    return summarize_scores(res)


def baseline(conn: psycopg.Connection, ctx: Context, force: bool = False) -> pd.DataFrame:
    """The no-extra-features run of the harness (all four positions), cached in ops.feature_experiments
    under (MODEL_VERSION, test seasons, data_key): every group compares with the same numbers."""
    seasons, leagues = _seasons_label(ctx.test_seasons), list(ctx.scorings)
    if not force:
        cached = _cached_baseline(conn, ctx.key, seasons, leagues)
        if cached is not None:
            log.info("baseline: cached (%s rows, run_at %s, key %s)", len(cached), cached["run_at"].max(), ctx.key)
            ctx.baseline = cached
            return cached
    t0 = time.monotonic()
    s = _fit_and_score(ctx, None, P.POSITIONS)
    ctx.baseline_seconds = time.monotonic() - t0
    for m in METRICS:
        s[f"baseline_{m}"] = s[m]
        s[f"delta_{m}"] = 0.0
    s = s.assign(run_id=datetime.now(UTC).strftime("%Y%m%d%H%M%S"), run_at=datetime.now(UTC), model_version=P.MODEL_VERSION,
                 harness_version=HARNESS_VERSION, feature_group=BASELINE, group_table=None, group_columns="",
                 test_seasons=seasons, data_key=ctx.key, decision=None, group_verdict=None, runtime_s=ctx.baseline_seconds,
                 label="Nothing added (the current model)", note="the v2 inputs only: what every group is compared with")
    _write_rows(conn, s, BASELINE, P.MODEL_VERSION, seasons, leagues)
    log.info("baseline: fitted and cached in %.0f s (key %s)", ctx.baseline_seconds, ctx.key)
    ctx.baseline = s
    return s


@dataclass
class Result:
    spec: GroupSpec
    rows: pd.DataFrame            # per league x test season x position, with baseline_* and delta_*
    decisions: pd.DataFrame       # per position
    verdict: str
    seconds: float
    no_peek: NoPeekReport


def run_experiment(conn: psycopg.Connection, group: str | GroupSpec, test_seasons: tuple[int, ...] = DEFAULT_TEST_SEASONS,
                   leagues: list[str] | None = None, ctx: Context | None = None, write: bool = True,
                   no_peek: NoPeekReport | None = None) -> Result:
    """Check, fit, score and decide one group against the cached baseline; write ops.feature_experiments."""
    spec = group if isinstance(group, GroupSpec) else get_group(conn, group)
    rep = no_peek or no_peek_check(conn, spec)
    for w in rep.warnings:
        log.warning("no-peek %s: %s", spec.name, w)
    if not rep.ok:
        raise NoPeekError(f"group {spec.name!r} refused by the no-peek check:\n  - " + "\n  - ".join(rep.failures))
    ctx = ctx or prepare(conn, [spec], test_seasons, leagues)
    base = ctx.baseline if ctx.baseline is not None else baseline(conn, ctx)
    t0 = time.monotonic()
    # v3: each position's production inputs plus the group's (the baseline is the production model)
    s = _fit_and_score(ctx, {p: [*P.FEATURES_BY_POSITION[p], *spec.columns] for p in spec.positions}, spec.positions)
    seconds = time.monotonic() - t0
    keys = ["league_id", "test_season", "position"]
    s = s.merge(base[[*keys, *[f"baseline_{m}" for m in METRICS]]], on=keys, how="left")
    for m in METRICS:
        s[f"delta_{m}"] = s[m].astype(float) - s[f"baseline_{m}"].astype(float)
    per_season = s.groupby(["position", "test_season"], sort=False)[["delta_spearman", "delta_mae"]].mean().reset_index()
    dec = decide(per_season)
    verdict = group_verdict(dec)
    s = s.merge(dec[["position", "decision"]], on="position", how="left")
    s = s.assign(run_id=datetime.now(UTC).strftime("%Y%m%d%H%M%S"), run_at=datetime.now(UTC), model_version=P.MODEL_VERSION,
                 harness_version=HARNESS_VERSION, feature_group=spec.name, group_table=spec.table, group_columns=",".join(spec.columns),
                 test_seasons=_seasons_label(ctx.test_seasons), data_key=ctx.key, group_verdict=verdict, runtime_s=seconds,
                 no_peek_warnings="; ".join(rep.warnings) or None, label=spec.label, note=spec.note)
    if write:
        _write_rows(conn, s, spec.name, P.MODEL_VERSION, _seasons_label(ctx.test_seasons), list(ctx.scorings))
    log.info("group %s: %s in %.0f s", spec.name, verdict, seconds)
    return Result(spec, s, dec, verdict, seconds, rep)


def run_many(groups: list[str], test_seasons: tuple[int, ...] = DEFAULT_TEST_SEASONS, leagues: list[str] | None = None,
             force_baseline: bool = False) -> tuple[Context, list[Result]]:
    """The CLI entry: several groups in one session (data read once, baseline fitted at most once)."""
    from .config import get_settings

    with psycopg.connect(get_settings().pipeline_dsn(), autocommit=False) as conn:
        specs = [get_group(conn, g) for g in groups if g != BASELINE]
        reports = {}
        for spec in specs:     # refuse before any fitting
            reports[spec.name] = rep = no_peek_check(conn, spec)
            if not rep.ok:
                raise NoPeekError(f"group {spec.name!r} refused by the no-peek check:\n  - " + "\n  - ".join(rep.failures))
        ctx = prepare(conn, specs, test_seasons, leagues)
        baseline(conn, ctx, force=force_baseline or BASELINE in groups)
        return ctx, [run_experiment(conn, spec, test_seasons, leagues, ctx=ctx, no_peek=reports[spec.name]) for spec in specs]
