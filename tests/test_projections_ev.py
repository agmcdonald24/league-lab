"""Wave I-D (M3): the nightly on the scoring spec — ONE pricing entry point for a projected line.

``scoring.price_projected`` is what ``projections.price(..., "proj_")`` (the nightly: ``predict_position``,
``house_rows``, the harness) and ``anyleague.price_lines`` (the request side: My Week, Waivers, Trades, rest of season)
both call, so under either state of ``LEAGUE_LAB_EV_PRICING`` a player is one number everywhere:

* flag off (the default): the flat engine, bit for bit the pre-Wave-I-D numbers;
* flag on: a Sleeper scoring with a yardage or long-TD bonus prices those bonuses in expectation (M2's curves and
  shares); a scoring without one (Scrubs, the plain references, the Test League) is unchanged to the bit;
* an MFL spec: the expectation, always.

The synthetic tests need no database; the ``ops.projection_lines`` ones read the experiment clone's week 4 (skipped
without it).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from league_lab import anyleague as A
from league_lab import projections as P
from league_lab import scoring as S

ROOT = Path(__file__).resolve().parents[1]
SLEEPER_FX = ROOT / "api" / "tests" / "fixtures" / "sleeper"
DYNASTY, SCRUBS, TEST = "1321941740235550720", "1389709692405551104", "9000000000000000001"
FLAG = "LEAGUE_LAB_EV_PRICING"
COMPS = [f"proj_{c}" for c in P.ALL_COMPONENTS]


def _fixture_scoring(league_id: str) -> S.LeagueScoring:
    """The league's settings as the request side sees them (``anyleague.league_scoring``: a ``LeagueScoring``)."""
    league = json.loads((SLEEPER_FX / f"league_{league_id}.json").read_text())
    return A.league_scoring(league)[0]


def _old_price(df: pd.DataFrame, scoring) -> np.ndarray:
    """``projections.price`` before Wave I-D: ``compute_points`` row by row (the reference the flat path equals)."""
    rows = df[COMPS].rename(columns=lambda c: c[5:])
    rows["position"] = df["position"].to_numpy()
    return np.array([S.compute_points(r, scoring) for r in rows.to_dict("records")], dtype=float)


def _board_shape(df: pd.DataFrame) -> pd.DataFrame:
    """The request side's ``Board.line``: indexed by gsis_id, ``position`` + the ``proj_*`` stat line."""
    return df.set_index("gsis_id")[["position", *COMPS]]


def _synthetic(n: int = 400, seed: int = 4) -> pd.DataFrame:
    """Projected lines that straddle every yardage-bonus threshold (receiving / rushing 100 and 200, passing 300 / 400)
    and carry TDs (the long-TD bonuses), for every skill position."""
    rng = np.random.default_rng(seed)
    pos = np.array(["QB", "RB", "WR", "TE"] * (n // 4), dtype=object)
    out = pd.DataFrame({"gsis_id": [f"p{i:04d}" for i in range(len(pos))], "position": pos})
    for c in P.ALL_COMPONENTS:
        out[f"proj_{c}"] = 0.0
    qb, rb, wr, te = (pos == p for p in ("QB", "RB", "WR", "TE"))
    out.loc[qb, "proj_attempts"] = rng.uniform(20, 42, qb.sum())
    out.loc[qb, "proj_passing_yards"] = rng.uniform(150, 420, qb.sum())
    out.loc[qb, "proj_passing_tds"] = rng.uniform(0.5, 2.8, qb.sum())
    out.loc[qb, "proj_passing_interceptions"] = rng.uniform(0.3, 1.2, qb.sum())
    out.loc[qb | rb, "proj_carries"] = rng.uniform(2, 24, (qb | rb).sum())
    out.loc[qb | rb | wr, "proj_rushing_yards"] = np.where(rb[qb | rb | wr], rng.uniform(10, 215, (qb | rb | wr).sum()),
                                                           rng.uniform(0, 40, (qb | rb | wr).sum()))
    out.loc[qb | rb | wr, "proj_rushing_tds"] = rng.uniform(0, 1.1, (qb | rb | wr).sum())
    rec = rb | wr | te
    out.loc[rec, "proj_targets"] = rng.uniform(1, 11, rec.sum())
    out.loc[rec, "proj_receptions"] = out.loc[rec, "proj_targets"] * 0.65
    out.loc[rec, "proj_receiving_yards"] = rng.uniform(5, 215, rec.sum())
    out.loc[rec, "proj_receiving_tds"] = rng.uniform(0, 1.0, rec.sum())
    out["proj_fumbles_lost_total"] = rng.uniform(0, 0.2, len(out))
    return out


# ------------------------------------------------------------------------------ the entry point (no database)
def test_the_flag_is_off_by_default(monkeypatch):
    monkeypatch.delenv(FLAG, raising=False)
    assert S.ev_pricing() is False
    for v, on in (("1", True), ("true", True), ("on", True), ("yes", True), ("0", False), ("", False), ("off", False)):
        monkeypatch.setenv(FLAG, v)
        assert S.ev_pricing() is on


def test_which_engine():
    dyn, scr, ppr = _fixture_scoring(DYNASTY), _fixture_scoring(SCRUBS), _fixture_scoring(TEST)
    assert [S.pricing_engine(x, ev=False) for x in (dyn, scr, ppr)] == ["flat"] * 3
    assert [S.pricing_engine(x, ev=True) for x in (dyn, scr, ppr)] == ["ev", "flat", "flat"]
    assert S.pricing_engine(dict(dyn), ev=True) == "ev"                       # a flat dict: the same rule
    mfl = S.ScoringSpec(positions={"*": S.Rules(rates={"receptions": 1.0})}, source="mfl", flat=None)
    assert S.pricing_engine(mfl, ev=False) == S.pricing_engine(mfl, ev=True) == "spec"
    # only the bonus keys move a Sleeper scoring; keys the flat engine leaves off a projected line stay off
    assert not S.ev_moves({"rec": 1.0, "pass_att": 0.1, "pass_inc": -0.5, "bonus_rush_att_20": 2.0})
    assert S.projected_view({"rec": 1.0, "pass_att": 0.1, "pass_inc": -0.5, "bonus_rec_te": 0.5, "zz": 0.0}) == \
        {"bonus_rec_te": 0.5, "rec": 1.0}


@pytest.mark.parametrize("league", [DYNASTY, SCRUBS, TEST])
@pytest.mark.parametrize("flag", ["0", "1"])
def test_nightly_equals_request_side_on_synthetic_lines(monkeypatch, league, flag):
    monkeypatch.setenv(FLAG, flag)
    df = _synthetic()
    for sc in (_fixture_scoring(league), dict(_fixture_scoring(league))):
        nightly = P.price(df, sc, "proj_").to_numpy()
        request = A.price_lines(_board_shape(df), sc).to_numpy()
        assert np.array_equal(nightly, request)
        if flag == "0" or league != DYNASTY:
            assert np.array_equal(nightly, _old_price(df, sc))                 # the pre-change engine, to the bit


def test_actual_lines_stay_on_the_exact_engine(monkeypatch):
    """``out_`` lines are facts: the flag never touches them (a 104-yard game pays the full 100-yard bonus)."""
    df = _synthetic().rename(columns=lambda c: c.replace("proj_", "out_"))
    sc = _fixture_scoring(DYNASTY)
    monkeypatch.setenv(FLAG, "0")
    off = P.price(df, sc, "out_").to_numpy()
    monkeypatch.setenv(FLAG, "1")
    assert np.array_equal(P.price(df, sc, "out_").to_numpy(), off)
    rows = df[[f"out_{c}" for c in P.ALL_COMPONENTS]].rename(columns=lambda c: c[4:]).assign(position=df["position"])
    assert np.array_equal(off, [S.compute_points(r, sc) for r in rows.to_dict("records")])


def test_ev_on_is_the_expectation_of_the_bonus_keys(monkeypatch):
    """Flag on, the dynasty: the flat price minus the all-or-nothing bonuses plus their expectation (M2's curves) plus
    the expected 40+ TD bonus; equal to ``expected_frame`` on the full Sleeper spec (IC-1's request-side path) for the
    house scoring, whose keys are all on the flat engine's list."""
    monkeypatch.setenv(FLAG, "1")
    df = _synthetic()
    sc = _fixture_scoring(DYNASTY)
    on = P.price(df, sc, "proj_").to_numpy()
    stats = df[COMPS].rename(columns=lambda c: c[5:])
    ic1 = S.expected_frame(stats, S.from_sleeper(dict(sc)), df["position"].to_numpy(), ev=True)
    assert np.abs(on - ic1).max() <= 0.010001            # the same terms; only the order of the float sums differs
    nob = {k: v for k, v in sc.items() if k not in S.SLEEPER_BONUS_MAP and k not in S.SLEEPER_LONG_TD_MAP}
    base = _old_price(df, nob)                           # every rate, no bonus
    extra = on - base
    assert (extra >= -0.010001).all()                    # a bonus in expectation is never negative
    # a projected line far below every threshold, with almost no TDs, gets almost nothing (a gamma tail: a few hundredths)
    low = (df["proj_rushing_yards"] < 30) & (df["proj_receiving_yards"] < 30) & (df["proj_passing_yards"] < 120)
    low &= (df["proj_rushing_tds"] + df["proj_receiving_tds"] + df["proj_passing_tds"]) < 0.05
    assert low.sum() > 0 and (np.abs(extra[low.to_numpy()]) <= 0.05).all()


def test_house_rows_and_price_week_agree_under_either_flag(monkeypatch):
    """``project``-shaped pricing (``predict_position``'s rows in the reference scoring, then ``house_rows``) and
    ``price_week`` on the same lines (an NFL-wide board) give the same ``proj_points``, flag on and off."""
    df = _synthetic(200)
    house = {DYNASTY: ("Forever Unclean Dynasty", dict(_fixture_scoring(DYNASTY))),
             SCRUBS: ("League of Scrubs", dict(_fixture_scoring(SCRUBS)))}
    # the references ARE the house leagues (the seed holds both), keys in another order (a JSON round trip, sorted)
    refs = {"dynasty": ("dyn", dict(sorted(house[DYNASTY][1].items()))), "scrubs": ("scr", dict(sorted(house[SCRUBS][1].items())))}
    source = {DYNASTY: "dynasty", SCRUBS: "scrubs"}
    seen = {}
    for flag in ("0", "1"):
        monkeypatch.setenv(FLAG, flag)
        frames = []
        for name, (_, sc) in refs.items():
            o = df.assign(league_id=name, season=2026, week=4)
            o["proj_points"] = P.price(o, sc, "proj_")
            for q, k in zip(("p10", "p25", "p50", "p75", "p90"), (0.5, 0.75, 1.0, 1.25, 1.5), strict=True):
                o[q] = o["proj_points"] * k
            o["model_version"], o["fitted_at"], o["train_seasons"] = P.MODEL_VERSION, None, "2016-2025"
            frames.append(o)
        every = pd.concat(frames, ignore_index=True)
        pred = P.house_rows(every, house, source)          # raises when a house league prices away from its reference
        line = _board_shape(df).assign(model_version=P.MODEL_VERSION)
        fitted = {n: g.set_index("gsis_id")[["proj_points", "p10", "p25", "p50", "p75", "p90"]] for n, g in every.groupby("league_id")}
        b = A.Board(2026, 4, line, fitted, pd.DataFrame(columns=["team"]), pd.DataFrame(), {n: sc for n, (_, sc) in refs.items()},
                    0, "nfl_wide", {n: lab for n, (lab, _) in refs.items()}, {})
        for lid, (_, sc) in house.items():
            pr = A.price_week(None, lid, sc, ["QB", "RB", "WR", "TE", "FLEX"], 2026, 4, board=b, cache=False)
            mine = pred[pred["league_id"] == lid].set_index("gsis_id")["proj_points"]
            assert np.array_equal(pr.proj.reindex(mine.index).to_numpy(), mine.to_numpy()), (lid, flag)
            assert pr.reference == source[lid]
            assert np.array_equal(pr.ranges["p90"].reindex(mine.index).to_numpy(),
                                  fitted[source[lid]]["p90"].reindex(mine.index).round(2).to_numpy())
            seen[(lid, flag)] = mine
    assert seen[(SCRUBS, "0")].equals(seen[(SCRUBS, "1")])                # no bonus rules: unchanged to the bit
    moved = seen[(DYNASTY, "1")] - seen[(DYNASTY, "0")]
    assert moved.max() > 0.5 and not moved.equals(moved * 0)


# ------------------------------------------------------------------------------ against the clone's week 4
@pytest.fixture(scope="module")
def week4():
    psycopg = pytest.importorskip("psycopg")
    from league_lab.config import get_settings

    try:
        c = psycopg.connect(get_settings().pipeline_dsn(), connect_timeout=3, autocommit=True)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"no database: {exc}")
    with c:
        if not c.execute("select to_regclass('ops.projection_lines')").fetchone()[0]:
            pytest.skip("ops.projection_lines not built")
        cur = c.execute(f"""select distinct on (gsis_id) gsis_id, position, {', '.join(COMPS)}
                            from ops.projection_lines where season = 2026 and week = 4
                            order by gsis_id, (frozen_source is not null) desc, fitted_at desc nulls last limit 500""")
        df = pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])
        leagues = P.league_scorings(c)
        refs = P.reference_scorings(c)
    if len(df) < 400 or DYNASTY not in leagues or SCRUBS not in leagues:
        pytest.skip("the clone's week 4 / house leagues are not there")
    for col in COMPS:
        df[col] = pd.to_numeric(df[col]).astype(float)
    return df, leagues, refs


@pytest.mark.parametrize("league", [DYNASTY, SCRUBS, TEST])
@pytest.mark.parametrize("flag", ["0", "1"])
def test_nightly_equals_request_side_on_projection_lines(monkeypatch, week4, league, flag):
    df, leagues, _ = week4
    monkeypatch.setenv(FLAG, flag)
    forms = [_fixture_scoring(league)] + ([leagues[league][1]] if league in leagues else [])
    for sc in forms:
        nightly = P.price(df, sc, "proj_").to_numpy()
        assert np.array_equal(nightly, A.price_lines(_board_shape(df), sc).to_numpy()), (league, flag)
        if flag == "0" or league != DYNASTY:
            assert np.array_equal(nightly, _old_price(df, sc))


def test_scrubs_pins_and_dynasty_moves(monkeypatch, week4):
    df, leagues, _ = week4
    scr, dyn = leagues[SCRUBS][1], leagues[DYNASTY][1]
    monkeypatch.setenv(FLAG, "0")
    s0, d0 = P.price(df, scr, "proj_"), P.price(df, dyn, "proj_")
    monkeypatch.setenv(FLAG, "1")
    s1, d1 = P.price(df, scr, "proj_"), P.price(df, dyn, "proj_")
    assert s0.equals(s1) and np.array_equal(s0.to_numpy(), _old_price(df, scr))
    by = df.assign(s=s0, d0=d0, d1=d1).set_index("gsis_id")
    if "00-0034857" in by.index:                       # Josh Allen, week 4 (IC-1's number): 30.24 -> 31.68
        assert (by.at["00-0034857", "s"], by.at["00-0034857", "d0"], by.at["00-0034857", "d1"]) == (24.42, 30.24, 31.68)
    by["rank"] = by.groupby("position")["d0"].rank(ascending=False, method="first")
    top = by[by["rank"] <= 24]
    move = top["d1"] - top["d0"]
    mean = move.groupby(top["position"]).mean()
    assert ((mean >= 0.2) & (mean <= 1.6)).all(), mean.round(3).to_dict()       # M2's measured range, per position
    assert move.max() <= 1.6
    # a top-24 line moves DOWN only when the all-or-nothing price paid a bonus it reached on the mean
    down = top[move < -0.05]
    reached = ((down["proj_rushing_yards"] >= 100) | (down["proj_receiving_yards"] >= 100)
               | (down["proj_passing_yards"] >= 300))
    assert reached.all(), down.index.tolist()


def test_reference_scorings_without_bonuses_never_move(monkeypatch, week4):
    df, leagues, refs = week4
    for name, (_, sc) in refs.items():
        monkeypatch.setenv(FLAG, "0")
        off = P.price(df, sc, "proj_").to_numpy()
        monkeypatch.setenv(FLAG, "1")
        on = P.price(df, sc, "proj_").to_numpy()
        if S.ev_moves(sc):
            assert name == "dynasty" and not np.array_equal(on, off)
            assert np.array_equal(on, P.price(df, leagues[DYNASTY][1], "proj_").to_numpy())   # the house league IS it
        else:
            assert np.array_equal(on, off), name
