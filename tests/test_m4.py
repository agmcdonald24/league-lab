"""Wave I-G (M4): the record's pricing column, and the request side follows the record.

* ``ops.projections``, ``ops.projection_ranges`` and ``ops.projection_backtest`` carry ``pricing`` (``flat`` | ``ev``;
  NULL = flat, every row written before the column), written by the nightly from ``pricing_engine`` (``spec`` → ``ev``).
* ``scoring.ev_pricing()`` is a MODE: the nightly writer's pinned mode (the env alone, default flat) → the env
  ``LEAGUE_LAB_EV_PRICING`` when set (an override, either way) → the newest build's label in ``ops.projections`` → flat.
  ``ev_for_week`` prices a week the record holds as its rows were priced (a frozen week keeps its label).
* Under the record's mode, ``price_projected`` / ``price_lines`` reproduce M3's numbers: the dynasty's top 24 +0.66 a
  week in week 5 when the record says EV, Scrubs identical to the bit; Josh Allen week 4 30.24 (frozen flat) / 31.68.

The synthetic tests need no database (a stand-in reader plays the record); the ``ops.*`` ones read the M4 clone
(skipped without it).
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from league_lab import anyleague as A
from league_lab import db as DB
from league_lab import projections as P
from league_lab import scoring as S

ROOT = Path(__file__).resolve().parents[1]
SLEEPER_FX = ROOT / "api" / "tests" / "fixtures" / "sleeper"
DYNASTY, SCRUBS = "1321941740235550720", "1389709692405551104"
FLAG = "LEAGUE_LAB_EV_PRICING"
COMPS = [f"proj_{c}" for c in P.ALL_COMPONENTS]
ALLEN = "00-0034857"
T0 = datetime(2026, 9, 26, 23, 53, tzinfo=UTC)          # the refit of weeks 1-3
T4 = datetime(2026, 10, 1, 19, 25, tzinfo=UTC)          # week 4's kickoff board
T5 = datetime(2026, 10, 4, 7, 0, tzinfo=UTC)            # the newest build


def _fixture_scoring(league_id: str) -> S.LeagueScoring:
    league = json.loads((SLEEPER_FX / f"league_{league_id}.json").read_text())
    return A.league_scoring(league)[0]


def _rows(labels: dict[int, tuple[str, datetime]], season: int = 2026) -> list[tuple]:
    """RECORD_PRICING_SQL's rows: (season, week, fitted_at, ev) per week."""
    return [(season, w, at, lab == "ev") for w, (lab, at) in sorted(labels.items())]


@pytest.fixture
def record(monkeypatch):
    """The record, played by a stand-in reader (``state["rows"]``; ``state["calls"]`` counts the reads)."""
    monkeypatch.delenv(FLAG, raising=False)
    state: dict = {"rows": [], "calls": 0, "raise": False}

    def read():
        state["calls"] += 1
        if state["raise"]:
            raise RuntimeError("no database")
        return state["rows"]
    S.set_record_reader(read)
    yield state
    S.set_record_reader(None)


def _flip_week5(state: dict) -> None:
    """Monday's record: weeks 1-3 refit (flat), week 4 frozen flat, weeks 5-18 written by the newest (EV) build."""
    state["rows"] = _rows({**{w: ("flat", T0) for w in (1, 2, 3)}, 4: ("flat", T4),
                           **{w: ("ev", T5) for w in range(5, 19)}})
    S.clear_pricing_cache()


# ------------------------------------------------------------------------------ 1. the column, on the three writers
def test_the_three_writers_and_migrate_add_the_column():
    for ddl in (P.DDL["ops.projections"], P.DDL["ops.projection_backtest"], P.NFL_DDL["ops.projection_ranges"]):
        assert "add column if not exists pricing text" in ddl
    assert DB.OPS_DDL.count("add column if not exists pricing text") == 2       # ops.projections, ops.projection_backtest


def test_the_label_per_scoring():
    dyn, scr = _fixture_scoring(DYNASTY), _fixture_scoring(SCRUBS)
    mfl = S.ScoringSpec(positions={"*": S.Rules(rates={"receptions": 1.0})}, source="mfl", flat=None)
    with S.pinned_pricing("ev"):
        assert [S.record_pricing_label(x) for x in (dyn, scr, dict(dyn), mfl)] == ["ev", "flat", "ev", "ev"]
    with S.pinned_pricing("flat"):
        assert [S.record_pricing_label(x) for x in (dyn, scr, mfl)] == ["flat", "flat", "ev"]   # an MFL spec: always EV


def test_backtest_writes_the_label_in_the_writers_own_mode(monkeypatch, record, tmp_path):
    """``backtest`` labels each league's rows; the writer prices in the env's mode, never the record's."""
    dyn, scr = _fixture_scoring(DYNASTY), _fixture_scoring(SCRUBS)
    seen: dict = {}
    monkeypatch.setattr(P, "league_scorings", lambda conn: {DYNASTY: ("Dynasty", dict(dyn)), SCRUBS: ("Scrubs", dict(scr))})
    monkeypatch.setattr(P, "available_seasons", lambda conn: [2024, 2025])
    monkeypatch.setattr(P, "load_frame", lambda conn, seasons: pd.DataFrame())
    monkeypatch.setattr(P, "load_baseline", lambda conn, seasons: pd.DataFrame())

    def walk_forward(frame, test_seasons, scorings, first, baseline, importance_ref=None):
        seen["mode"] = S.pricing_mode()
        return pd.DataFrame({"league_id": [DYNASTY, SCRUBS], "season": [2025, 2025], "week": [1, 1]}), []
    monkeypatch.setattr(P, "walk_forward", walk_forward)
    monkeypatch.setattr(P, "report", lambda res, scorings, imp: "")
    monkeypatch.setattr(P, "_write", lambda conn, table, df, where, params: seen.setdefault(table, df.copy()))
    _flip_week5(record)                                    # the record says EV ...
    P.backtest(None, [2025], tmp_path)                     # ... the env is unset: the writer prices flat
    assert seen["mode"] == {"mode": "flat", "source": "pinned", "built_at": None}
    assert seen["ops.projection_backtest"]["pricing"].tolist() == ["flat", "flat"]
    seen.clear()
    monkeypatch.setenv(FLAG, "1")
    P.backtest(None, [2025], tmp_path)
    assert seen["mode"]["mode"] == "ev" and seen["ops.projection_backtest"]["pricing"].tolist() == ["ev", "flat"]


# ------------------------------------------------------------------------------ 2. the mode
def test_the_mode_follows_the_record_when_the_env_is_unset(record):
    _flip_week5(record)
    assert S.pricing_mode() == {"mode": "ev", "source": "record", "built_at": T5} and S.ev_pricing() is True
    record["rows"] = _rows({4: ("flat", T4), 5: ("flat", T5)})
    S.clear_pricing_cache()
    assert S.pricing_mode()["mode"] == "flat" and S.ev_pricing() is False
    record["rows"] = []                                    # no build at all: flat
    S.clear_pricing_cache()
    assert S.pricing_mode() == {"mode": "flat", "source": "default", "built_at": None}


def test_the_env_overrides_the_record_either_way(record, monkeypatch):
    _flip_week5(record)
    monkeypatch.setenv(FLAG, "0")
    assert S.pricing_mode()["source"] == "env" and S.ev_pricing() is False and S.ev_for_week(2026, 5) is False
    record["rows"] = _rows({5: ("flat", T5)})
    S.clear_pricing_cache()
    monkeypatch.setenv(FLAG, "1")
    assert S.ev_pricing() is True and S.ev_for_week(2026, 4) is True
    monkeypatch.setenv(FLAG, " ")                          # set but empty: the record decides
    assert S.env_pricing() is None and S.ev_pricing() is False


def test_the_writer_pins_the_env_alone(record, monkeypatch):
    _flip_week5(record)
    with S.pinned_pricing():
        assert S.pricing_mode() == {"mode": "flat", "source": "pinned", "built_at": None}   # never the record it writes
        assert S.ev_for_week(2026, 5) is False
    monkeypatch.setenv(FLAG, "1")
    with S.pinned_pricing():
        assert S.ev_pricing() is True
        with S.pinned_pricing("flat"):
            assert S.ev_pricing() is False
        assert S.ev_pricing() is True
    assert S.pricing_mode()["source"] == "env"


def test_a_frozen_week_keeps_its_label_and_the_newest_build_wins(record):
    _flip_week5(record)
    assert [S.ev_for_week(2026, w) for w in (1, 4, 5, 18)] == [False, False, True, True]
    assert S.ev_for_week(2026, 19) is True and S.ev_for_week(None, None) is True     # not on the record: the newest
    # a rollback: the newest build is flat again; weeks 5-6 kicked off under EV and keep it
    record["rows"] = _rows({4: ("flat", T4), 5: ("ev", T4 + timedelta(days=7)), 6: ("ev", T4 + timedelta(days=14)),
                            **{w: ("flat", T5 + timedelta(days=14)) for w in range(7, 19)}})
    S.clear_pricing_cache()
    assert S.ev_pricing() is False and [S.ev_for_week(2026, w) for w in (4, 5, 6, 7)] == [False, True, True, False]


def test_a_record_that_cannot_be_read_is_flat_and_is_cached(record, monkeypatch):
    record["raise"] = True
    S.clear_pricing_cache()
    assert S.pricing_mode() == {"mode": "flat", "source": "default", "built_at": None}
    assert S.record_pricing()["ok"] is False and record["calls"] == 1
    S.ev_pricing()
    assert record["calls"] == 1                            # a failure is cached a minute
    clock = [time.monotonic()]
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    record["raise"] = False
    _flip_week5(record)
    calls = record["calls"]
    assert S.ev_pricing() is True and record["calls"] == calls + 1
    clock[0] += S.RECORD_TTL_S - 1
    assert S.ev_pricing() is True and record["calls"] == calls + 1      # one query per ten minutes
    clock[0] += 2
    S.ev_pricing()
    assert record["calls"] == calls + 2


def test_the_reader_accepts_a_frame(record):
    record["rows"] = pd.DataFrame({"season": [2026, 2026], "week": [4, 5], "ev": [False, True],
                                   "fitted_at": [pd.Timestamp(T4), pd.Timestamp(T5)]})
    S.clear_pricing_cache()
    assert S.ev_pricing() is True and S.ev_for_week(2026, 4) is False


# ------------------------------------------------------------------------------ 3. price_lines follows the record
def _synthetic_lines(n: int = 200, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    pos = np.array(["QB", "RB", "WR", "TE"] * (n // 4), dtype=object)
    df = pd.DataFrame({"gsis_id": [f"p{i:04d}" for i in range(len(pos))], "position": pos})
    for c in COMPS:
        df[c] = 0.0
    qb, rb = pos == "QB", pos == "RB"
    df.loc[qb, "proj_passing_yards"] = rng.uniform(220, 330, qb.sum())
    df.loc[qb, "proj_passing_tds"] = rng.uniform(1, 2.5, qb.sum())
    df.loc[rb, "proj_rushing_yards"] = rng.uniform(40, 110, rb.sum())
    df.loc[rb, "proj_rushing_tds"] = rng.uniform(0.2, 0.9, rb.sum())
    rec = ~qb
    df.loc[rec, "proj_receptions"] = rng.uniform(1, 7, rec.sum())
    df.loc[rec, "proj_receiving_yards"] = rng.uniform(10, 105, rec.sum())
    df.loc[rec, "proj_receiving_tds"] = rng.uniform(0, 0.8, rec.sum())
    return df


def test_price_lines_prices_each_week_as_the_record_does(record):
    _flip_week5(record)
    dyn, scr = _fixture_scoring(DYNASTY), _fixture_scoring(SCRUBS)
    base = _synthetic_lines()
    two = pd.concat([base.assign(season=2026, week=4), base.assign(season=2026, week=5)], ignore_index=True)
    got = A.price_lines(two, dyn).to_numpy()
    flat = S.price_projected(base[COMPS].rename(columns=lambda c: c[5:]).assign(position=base["position"]), dyn, ev=False)
    ev = S.price_projected(base[COMPS].rename(columns=lambda c: c[5:]).assign(position=base["position"]), dyn, ev=True)
    assert np.array_equal(got[: len(base)], flat) and np.array_equal(got[len(base):], ev)     # week 4 frozen flat
    assert not np.array_equal(flat, ev)
    s = A.price_lines(two, scr).to_numpy()
    assert np.array_equal(s[: len(base)], s[len(base):])                                     # Scrubs: no bonus to price
    assert np.array_equal(A.price_lines(base.set_index("gsis_id"), dyn).to_numpy(), ev)      # no week: the newest build
    board = base.set_index("gsis_id")                      # the board's frame (no week column): the caller says the week
    assert np.array_equal(A.price_lines(board, dyn, season=2026, week=4).to_numpy(), flat)
    assert np.array_equal(A.price_lines(board, dyn, season=2026, week=5).to_numpy(), ev)
    window = base.assign(week=4)                           # a rest-of-season window: weeks, no season (the record's)
    assert np.array_equal(A.price_lines(window, dyn).to_numpy(), flat)


# ------------------------------------------------------------------------------ 4. the record's sentence
@pytest.mark.parametrize(("by_week", "now", "words"), [
    ({}, "flat", None),
    ({1: "flat", 2: "flat"}, "flat", None),
    ({1: "flat", 2: "flat", 3: "flat", 4: "flat"}, "ev",
     "Weeks 1–4 were priced flat; from week 5 the bonuses are priced at their odds."),
    ({4: "flat", 5: "ev", 6: "ev"}, "ev", "Week 4 was priced flat; from week 5 the bonuses are priced at their odds."),
    ({5: "ev", 6: "ev"}, "ev", "Every week on the record priced the bonuses at their odds."),
    ({4: "flat", 5: "ev", 6: "flat"}, "flat",
     "Week 4 priced flat; week 5 priced the bonuses at their odds; week 6 priced flat."),
    ({4: "flat", 5: "mixed"}, "ev", "Week 4 priced flat; week 5 priced partly flat; now at their odds."),
])
def test_the_record_sentence(by_week, now, words):
    assert S.record_pricing_sentence(by_week, now) == words


# ------------------------------------------------------------------------------ 5. against the M4 clone
@pytest.fixture(scope="module")
def clone():
    psycopg = pytest.importorskip("psycopg")
    from league_lab.config import get_settings

    try:
        c = psycopg.connect(get_settings().pipeline_dsn(), connect_timeout=3, autocommit=True)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"no database: {exc}")
    with c:
        has = c.execute("""select count(*) from information_schema.columns where table_schema = 'ops'
                           and table_name in ('projections', 'projection_ranges') and column_name = 'pricing'""").fetchone()[0]
        if has < 2 or not c.execute("select to_regclass('ops.projection_lines')").fetchone()[0]:
            pytest.skip("the clone's tables carry no pricing column yet (run `league-lab project`)")
        cur = c.execute(f"""select distinct on (week, gsis_id) season, week, gsis_id, position, {', '.join(COMPS)}
                            from ops.projection_lines where season = 2026 and week in (4, 5)
                            order by week, gsis_id, fitted_at desc nulls last""")
        lines = pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])
        cur = c.execute("""select league_id, season, week, position, pricing, count(*) as n
                           from ops.projections where season = 2026 group by 1, 2, 3, 4, 5""")
        labels = pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])
        cur = c.execute("""select r.scoring_name, r.week, r.pricing as ranges, p.pricing as board
                           from (select distinct scoring_name, week, pricing from ops.projection_ranges where season = 2026) r
                           join (select distinct week, pricing from ops.projections
                                 where season = 2026 and league_id = %s and position in ('QB', 'RB', 'WR', 'TE')) p
                             using (week) where r.scoring_name = 'dynasty'""", (DYNASTY,))
        dyn_ranges = pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])
        leagues = P.league_scorings(c)
    if DYNASTY not in leagues or SCRUBS not in leagues or len(lines) < 400:
        pytest.skip("the clone's house leagues / weeks 4-5 are not there")
    for col in COMPS:
        lines[col] = pd.to_numeric(lines[col]).astype(float)
    return lines, labels, dyn_ranges, leagues


def test_the_board_labels_hold_in_either_state(clone):
    """Whatever the clone's last build was: one label per league-week; Scrubs (no bonus) and K / DEF never 'ev'; the
    dynasty reference's ranges carry the dynasty board's label week by week (the reference IS the league)."""
    _, labels, dyn_ranges, _ = clone
    lab = labels.assign(pricing=labels["pricing"].fillna("flat"))
    skill = lab[lab["position"].isin(["QB", "RB", "WR", "TE"])]
    assert (skill.groupby(["league_id", "week"])["pricing"].nunique() == 1).all()
    assert set(lab.loc[lab["league_id"] == SCRUBS, "pricing"]) == {"flat"}
    assert set(lab.loc[lab["position"].isin(["K", "DEF"]), "pricing"]) == {"flat"}
    assert set(lab["pricing"]) <= {"flat", "ev"}
    d = dyn_ranges.fillna("flat")
    assert len(d) and (d["ranges"] == d["board"]).all()


def test_m3_numbers_under_the_record_mode(record, clone):
    """The record says week 4 flat (frozen) and the newest build EV: week 5's top 24 per position move as M3 measured
    (QB +1.01, RB +0.71, WR +0.73, TE +0.18; 96 players +0.66; none down), Scrubs identical to the bit, Josh Allen's
    week 4 stays 30.24 (its label) and is 31.68 had week 4 been priced at the odds."""
    lines, _, _, leagues = clone
    scr, dyn = leagues[SCRUBS][1], leagues[DYNASTY][1]
    wk5 = lines[lines["week"] == 5].set_index("gsis_id")
    record["rows"] = _rows({4: ("flat", T4), 5: ("flat", T5)})
    S.clear_pricing_cache()
    d0, s0 = A.price_lines(wk5, dyn), A.price_lines(wk5, scr)
    _flip_week5(record)
    d1, s1 = A.price_lines(wk5, dyn), A.price_lines(wk5, scr)
    assert np.array_equal(s0.to_numpy(), s1.to_numpy())
    by = wk5.assign(d0=d0, d1=d1)
    by["rank"] = by.groupby("position")["d0"].rank(ascending=False, method="first")
    top = by[by["rank"] <= 24]
    move = top["d1"] - top["d0"]
    mean = move.groupby(top["position"]).mean().round(2).to_dict()
    # ---- M6 (Wave I-H): a clone built with the cold-start blend on the line (Love, Price scaled in the RB top 24) moves
    # the RB mean by 0.01 (0.71 -> 0.72); either build of the clone holds M3's numbers to that cent
    want = {"QB": 1.01, "RB": 0.71, "TE": 0.18, "WR": 0.73}
    assert mean.keys() == want.keys() and all(abs(mean[k] - v) <= 0.0101 for k, v in want.items()), mean
    assert abs(round(float(move.mean()), 2) - 0.66) <= 0.0101 and len(top) == 96 and (move >= -0.005).all()
    wk4 = lines[lines["week"] == 4].set_index("gsis_id")
    if ALLEN in wk4.index:
        assert float(A.price_lines(wk4.loc[[ALLEN]], dyn).iloc[0]) == 30.24       # week 4 is frozen flat
        record["rows"] = _rows({4: ("ev", T4), 5: ("ev", T5)})
        S.clear_pricing_cache()
        assert float(A.price_lines(wk4.loc[[ALLEN]], dyn).iloc[0]) == 31.68
        assert float(A.price_lines(wk4.loc[[ALLEN]], scr).iloc[0]) == 24.42
