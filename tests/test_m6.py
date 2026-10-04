"""Wave I-H (M6): v3.2 -- the cold-start prior on the stat line, veterans on a new team, the out-of-sample rows where
the nightly runs, "why this number" in the week's mode.

* ``calibration.blend_lines`` scales a cold start's stat line (every component x ``k`` = blended / raw points in the
  anchor scoring) BEFORE anything is priced, and prices / ranges the scaled line with the same models -- so the house
  rows, the NFL-wide line and the request side's price of that line are one number, bit for bit, in either pricing mode.
* The blend is the identity at ``COLD_N`` games (and for any veteran).
* ``ensure_oof`` twice = once (the second call reads two rows and writes nothing).
* ``why.weights`` reads the week's mode (``api/tests/test_m6.py`` has the API side; here: ``scoring.ev_for_week``'s
  contract the pieces rely on).

No database: the history queries and ``ops.calibration_oof`` are played by stand-ins; ``predict_position`` by a
stand-in that prices with the real ``projections.price`` (the line -> points path under test) and bands at +-3 / 6.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from league_lab import anyleague as A
from league_lab import calibration as C
from league_lab import projections as P
from league_lab import scoring as S

COMPS = [f"proj_{c}" for c in P.ALL_COMPONENTS]
REF = {"rec": 0.5, "rec_yd": 0.1, "rec_td": 6.0, "rush_yd": 0.1, "rush_td": 6.0, "fum_lost": -2.0}          # half PPR
BONUS = {"rec": 1.0, "rec_yd": 0.1, "rec_td": 6.0, "rush_yd": 0.1, "rush_td": 6.0, "fum_lost": -2.0,
         "bonus_rec_yd_100": 3.0, "bonus_rush_yd_100": 3.0}                                                   # full PPR + bonuses
LEAGUES = {"L1": ("Ref league", REF), "L2": ("Bonus league", BONUS)}
FIT = {"L1": ("Ref league", REF), "L2": ("Bonus league", BONUS)}       # what project fits: the keys are the scorings


class _FakeConn:
    """Answers ``_history``'s two queries (games with team, draft slots)."""

    def __init__(self, games, draft):
        self.games, self.draft = games, draft

    def cursor(self):
        conn = self

        class Cur:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def execute(self, sql, params=None):
                self.rows = conn.games if "fct_player_game" in sql else conn.draft

            def fetchall(self):
                return self.rows

        return Cur()


def _fake_predict(m, rows, scorings, lines=None):
    """``predict_position``'s shape: one row per scoring per input row, the line (given, else the model's ``m_*``
    columns), priced by the real ``projections.price``; bands around it."""
    out = rows[["gsis_id", "season", "week", "position"]].copy().reset_index(drop=True)
    src = lines.reset_index(drop=True) if lines is not None else rows.reset_index(drop=True).rename(
        columns=lambda c: "proj_" + c[2:] if c.startswith("m_") else c)
    for c in COMPS:
        out[c] = pd.to_numeric(src[c], errors="coerce").fillna(0.0).to_numpy(dtype=float) if c in src else 0.0
    frames = []
    for lid, (_, sc) in scorings.items():
        o = out.copy()
        o["league_id"] = lid
        o["proj_points"] = P.price(o, sc, "proj_")
        o["p10"], o["p25"], o["p50"] = np.clip(o["proj_points"] - 6, 0, None), np.clip(o["proj_points"] - 3, 0, None), o["proj_points"]
        o["p75"], o["p90"] = o["proj_points"] + 3, o["proj_points"] + 6
        frames.append(o)
    return pd.concat(frames, ignore_index=True)


def _target() -> pd.DataFrame:
    """Week 5 of 2026: a first-round rookie WR (no game), a WR with exactly 3 games, a veteran WR, a QB rookie, a
    cold WR whose line is under half a point. ``m_*`` = the model's line."""
    base = {"targets": 6.0, "receptions": 4.0, "receiving_yards": 55.0, "receiving_tds": 0.3, "carries": 0.2,
            "rushing_yards": 1.0, "rushing_tds": 0.0, "fumbles_lost_total": 0.05}
    rows = []
    for gid, pos, team, scale in (("rook", "WR", "AAA", 0.6), ("three", "WR", "BBB", 0.6), ("vet", "WR", "CCC", 1.0),
                                  ("qbrook", "QB", "DDD", 1.0), ("tiny", "WR", "EEE", 0.01)):
        r = {"gsis_id": gid, "season": 2026, "week": 5, "position": pos, "team": team}
        r |= {f"m_{c}": base.get(c, 0.0) * scale for c in P.ALL_COMPONENTS}
        rows.append(r)
    return pd.DataFrame(rows)


def _history():
    games = [("three", 2026, w, "BBB") for w in (1, 2, 3)] + [("vet", 2025, w, "CCC") for w in range(1, 18)]
    draft = [(f"r{s}_{i}", 10, s) for s in (2023, 2024, 2025) for i in range(60)] + [
        ("rook", 8, 2026), ("three", 9, 2026), ("vet", 40, 2019), ("qbrook", 3, 2026), ("tiny", 20, 2026)]
    return games, draft


def _oof() -> pd.DataFrame:
    """3 seasons of cold WR rows in each league: first-round rookies score 9 (L1) / 12 (L2); the model said 5 / 7."""
    rng = np.random.default_rng(5)
    fit = []
    for s in (2023, 2024, 2025):
        for i in range(60):
            for lid, (p, a) in {"L1": (5.0, 9.0), "L2": (7.0, 12.0)}.items():
                fit.append({"gsis_id": f"r{s}_{i}", "season": s, "week": 1, "position": "WR", "league_id": lid,
                            "proj_points": p, "actual": a + rng.normal(0, 1)})
    return pd.DataFrame(fit)


@pytest.fixture
def blend(monkeypatch):
    """Everything ``blend_lines`` reads, played by stand-ins; returns run(switch) -> (every, out)."""
    monkeypatch.delenv("LEAGUE_LAB_EV_PRICING", raising=False)
    monkeypatch.setattr(C, "load_oof", lambda conn, season: _oof())
    monkeypatch.setattr(C, "anchor_league", lambda oof, leagues: "L1")
    monkeypatch.setattr(C, "COLD_POSITIONS", ("RB", "WR", "TE"))
    monkeypatch.setattr(P, "predict_position", _fake_predict)
    games, draft = _history()
    conn = _FakeConn(games, draft)
    target = _target()

    def run(switch: str | None):
        if switch is None:
            monkeypatch.delenv(C.COLD_START_FLAG, raising=False)
        else:
            monkeypatch.setenv(C.COLD_START_FLAG, switch)
        every = pd.concat([_fake_predict(None, target[target["position"] == pos], FIT) for pos in ("QB", "WR")],
                          ignore_index=True)
        every["model_version"], every["fitted_at"], every["train_seasons"] = P.MODEL_VERSION, pd.Timestamp("2026-10-05", tz="UTC"), "2016-2025"
        return every, C.blend_lines(conn, 2026, every, {"WR": None, "QB": None}, target, FIT, LEAGUES)
    return run


def _row(df, gid, lid="L1"):
    return df[(df["gsis_id"] == gid) & (df["league_id"] == lid)].iloc[0]


# ------------------------------------------------------------------------------ 1. the blend on the line
def test_the_blend_is_the_identity_at_n_games_and_for_veterans(blend):
    assert C.blend_identity_at(C.COLD_N)
    every, out = blend("1")
    for gid in ("three", "vet", "qbrook", "tiny"):     # 3 games; a veteran; QB is not a kept position; a line < 0.5 pt
        for lid in ("L1", "L2"):
            a, b = _row(every, gid, lid), _row(out, gid, lid)
            assert [b[c] for c in [*COMPS, "proj_points", "p10", "p90"]] == [a[c] for c in [*COMPS, "proj_points", "p10", "p90"]]
    assert C.line_scale(np.array([0.3, 5.0, 5.0, np.nan]), np.array([9.0, 5.0, 8.0, 9.0])).tolist() == [1.0, 1.0, 1.6, 1.0]


def test_a_cold_start_line_is_scaled_toward_his_draft_slot(blend):
    every, out = blend("1")
    a, b = _row(every, "rook"), _row(out, "rook")
    k = b["proj_targets"] / a["proj_targets"]
    assert k > 1.3                                                     # pulled up toward the first-round rookies' 9
    assert all(b[c] == pytest.approx(a[c] * k, rel=1e-12) for c in COMPS)   # every component by the same factor
    assert b["proj_points"] == pytest.approx(a["proj_points"] * k, abs=0.011)   # L1 is linear: its points by k (to the cent)
    assert b["p90"] - b["proj_points"] == pytest.approx(6.0)              # the range is the scaled line's range
    plan = C.LAST_LINE_BLEND
    assert plan["gsis_id"].tolist() == ["rook"] and plan["kind"].tolist() == ["cold"]
    assert len(out) == len(every) and set(out.columns) == set(every.columns)


@pytest.mark.parametrize("mode", ["flat", "ev"])
@pytest.mark.parametrize("switch", ["1", "0"])
def test_a_blended_line_prices_to_his_blended_points_bit_for_bit(blend, mode, switch):
    """ops.projections (house_rows of the blended rows) = the request side's price of ops.projection_lines (nfl_lines),
    in a linear scoring and a bonus scoring, flat and at the odds, switch on and off."""
    with S.pinned_pricing(mode):
        every, out = blend(switch)
        lines = P.nfl_lines(out)
        house = P.house_rows(out, LEAGUES, {"L1": "L1", "L2": "L2"})
        for lid, (_, sc) in LEAGUES.items():
            h = house[house["league_id"] == lid].set_index("gsis_id")
            req = A.price_lines(lines, sc).set_axis(lines["gsis_id"])
            assert (h.loc[req.index, "proj_points"].to_numpy() == req.to_numpy()).all()      # bit for bit
    moved = (_row(out, "rook", "L2")["proj_points"] != _row(every, "rook", "L2")["proj_points"])
    assert moved == (switch == "1")


def test_the_switch_defaults_to_the_harness_verdict(monkeypatch):
    monkeypatch.delenv(C.COLD_START_FLAG, raising=False)
    assert C.cold_start_enabled() is C.COLD_DEFAULT is True
    for v, on in (("", True), ("0", False), ("off", False), ("1", True), ("on", True)):
        monkeypatch.setenv(C.COLD_START_FLAG, v)
        assert C.cold_start_enabled() is on


def test_the_points_path_no_longer_blends(monkeypatch):
    """M5's points blend is gone from calibrate_outputs (it moved to the line): switch on, the house rows untouched."""
    monkeypatch.setenv(C.COLD_START_FLAG, "1")
    for f in (C.FLAG, C.FRINGE_FLAG):
        monkeypatch.delenv(f, raising=False)
    pred, ranges = pd.DataFrame({"position": ["WR"], "proj_points": [10.0]}), pd.DataFrame()
    out, rng = C.calibrate_outputs(None, 2026, pred, ranges, {})
    assert out is pred and rng is ranges


def test_no_oof_rows_or_no_kept_position_leaves_the_line(blend, monkeypatch):
    monkeypatch.setattr(C, "load_oof", lambda conn, season: None)
    every, out = blend("1")
    assert out is every
    monkeypatch.setattr(C, "load_oof", lambda conn, season: _oof())
    monkeypatch.setattr(C, "COLD_POSITIONS", ())
    every, out = blend("1")
    assert out is every


def test_anchor_is_the_reference_league_when_held(monkeypatch):
    from league_lab import config

    class _S:
        reference_league_id = "L2"
    monkeypatch.setattr(config, "get_settings", lambda: _S())
    oof = pd.DataFrame({"league_id": ["L1", "L2"]})
    assert C.anchor_league(oof, LEAGUES) == "L2"
    assert C.anchor_league(oof[oof["league_id"] == "L1"], LEAGUES) == "L1"
    assert C.anchor_league(pd.DataFrame({"league_id": ["X"]}), LEAGUES) is None


# ------------------------------------------------------------------------------ 2. veterans on a new team (measured, not kept)
def test_team_games_count_the_current_stint():
    games = pd.DataFrame([("a", 2025, w, "NYJ") for w in range(1, 10)] + [("a", 2025, w, "LV") for w in (11, 12)]
                         + [("b", 2025, w, "KC") for w in range(1, 5)], columns=["gsis_id", "season", "week", "team"])
    rows = pd.DataFrame({"gsis_id": ["a", "a", "a", "b", "c"], "season": [2025, 2025, 2026, 2026, 2026],
                         "week": [11, 13, 1, 1, 1], "team": ["LV", "LV", "DEN", "KC", "KC"]})
    assert C.team_games_before(rows, games).tolist() == [0.0, 2.0, 0.0, 4.0, 0.0]
    new = C.is_new_team([0, 2, 0, 4], [9, 11, 11, 4], [False, False, False, False])
    assert new.tolist() == [True, True, True, False]
    assert not C.is_new_team([0], [1], [True])[0]                       # a cold start is not a "new-team veteran"
    assert C.NEW_TEAM_POSITIONS == ()                                   # the harness dropped it (STATUS § M6)
    f = pd.DataFrame({"career_games_before": [9], "cold": [False], "team_games_before": [1], "new_team": [True]})
    assert C.blend_frame(f, "new_team")[["career_games_before", "cold"]].iloc[0].tolist() == [1, True]
    assert C.blend_frame(f, "cold") is f


# ------------------------------------------------------------------------------ 3. the out-of-sample rows: twice = once
class _OOFConn:
    """An in-memory ``ops.calibration_oof`` for ``write_oof`` / ``oof_current``."""

    def __init__(self):
        self.exists, self.rows, self.writes, self.commits = False, [], 0, 0

    def commit(self):
        self.commits += 1

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def cursor(self):
        conn = self

        class Copy:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def write_row(self, rec):
                conn.rows.append(rec)

        class Cur:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def execute(self, sql, params=None):
                s = " ".join(sql.split()).lower()
                if s.startswith("create table"):
                    conn.exists = True
                elif s.startswith("truncate"):
                    conn.rows, conn.writes = [], conn.writes + 1
                self.result = ([("ops.calibration_oof" if conn.exists else None,)] if "to_regclass" in s
                               else sorted({(r[1], r[-1]) for r in conn.rows}) if "select distinct season" in s else [])

            def fetchone(self):
                return self.result[0]

            def fetchall(self):
                return self.result

            def copy(self, sql):
                return Copy()

        return Cur()


def test_ensure_oof_twice_is_once(monkeypatch):
    import psycopg

    conn = _OOFConn()
    monkeypatch.setattr(psycopg, "connect", lambda *a, **k: conn)
    monkeypatch.setattr(P, "available_seasons", lambda c: list(range(2016, 2027)))
    built: list[list[int]] = []

    def build(seasons=None):
        built.append(list(seasons))
        rows = pd.DataFrame([{"gsis_id": f"p{i}", "season": s, "week": 1, "position": "WR", "league_id": "L1",
                              "proj_points": 5.0, "actual": 6.0, "train_seasons": f"2016-{s - 1}"}
                             for s in seasons for i in range(3)])
        return C.write_oof(conn, rows)
    monkeypatch.setattr(C, "run_build_oof", build)
    assert C.oof_target_seasons(conn) == [2023, 2024, 2025]
    assert C.ensure_oof() == 9 and conn.writes == 1
    first = list(conn.rows)
    assert C.ensure_oof() == 0 and conn.writes == 1 and conn.rows == first        # the second call writes nothing
    assert C.ensure_oof(force=True) == 9 and conn.writes == 2
    monkeypatch.setattr(P, "MODEL_VERSION", "v9.9")                                # a model bump rebuilds
    assert C.ensure_oof() == 9 and conn.writes == 3 and built[-1] == [2023, 2024, 2025]


# ------------------------------------------------------------------------------ 4. the week's mode (what why.weights reads)
def test_a_frozen_flat_week_keeps_its_mode_after_the_flip(monkeypatch):
    from datetime import UTC, datetime

    monkeypatch.delenv("LEAGUE_LAB_EV_PRICING", raising=False)
    t4, t5 = datetime(2026, 10, 1, tzinfo=UTC), datetime(2026, 10, 5, tzinfo=UTC)
    S.set_record_reader(lambda: [(2026, 4, t4, False), *[(2026, w, t5, True) for w in range(5, 19)]])
    try:
        assert S.ev_for_week(2026, 4) is False and S.ev_for_week(2026, 5) is True and S.ev_pricing() is True
    finally:
        S.set_record_reader(list)


# ------------------------------------------------------------------------------ 5. the record's Sleeper side at the odds
def test_the_market_record_prices_sleepers_line_like_the_card():
    """``projections.price_market`` (what ops.market_record stores) = ``price_projected(ev=True)`` (what the card's
    "Sleeper's projection" shows in an EV week); in a bonus league it differs from the all-or-nothing price."""
    from league_lab.ingest import sleeper_projections as SP

    cols = list(SP.LINE_COLUMNS)
    line = {c: 0.0 for c in cols} | {"targets": 8.0, "receptions": 6.0, "receiving_yards": 95.0, "receiving_tds": 0.6}
    df = pd.DataFrame([line | {"position": "WR"}, line | {"position": "TE", "receiving_yards": 40.0}])
    ev = P.price_market(df, cols, BONUS)
    stats = df[cols].assign(position=df["position"])
    assert ev.tolist() == list(S.price_projected(stats, BONUS, ev=True))
    flat = S.price_projected(stats, BONUS, ev=False)
    assert ev[0] != flat[0]                        # 95 yards: all or nothing pays 0; at the odds about 40% of 3 points
    assert P.price_market(df, cols, REF).tolist() == list(S.price_projected(stats, REF, ev=False))   # no bonus: the same
    assert "market_record" in P.MARKET_RECORD_DDL and "primary key" in P.MARKET_RECORD_DDL


def test_the_scenario_base_follows_a_scaled_line():
    """signals.scenarios refits the models (the unscaled line): a cold start's base becomes the stored (scaled) line,
    the larger role moves by the same k; an unscaled row and a pred without the line are left as they were."""
    model = {c: 0.0 for c in COMPS} | {"proj_targets": 5.0, "proj_receptions": 3.0, "proj_receiving_yards": 40.0}
    comp_b = pd.DataFrame([model, model])
    comp_s = pd.DataFrame([{c: v * 1.2 for c, v in model.items()}] * 2)
    stored = [{"gsis_id": "rook", "week": 5, **{c: v * 1.5 for c, v in model.items()}},
              {"gsis_id": "vet", "week": 5, **model}]
    pred = pd.DataFrame(stored + [{**stored[0], "league_id": "L2"}])
    b, s = C.rescale_to_stored(comp_b, comp_s, [("rook", 5), ("vet", 5)], pred)
    assert b.iloc[0][COMPS].tolist() == [v * 1.5 for v in model.values()]
    assert s.iloc[0]["proj_receiving_yards"] == pytest.approx(40.0 * 1.2 * 1.5)
    assert b.iloc[1].tolist() == comp_b.iloc[1].tolist() and s.iloc[1].tolist() == comp_s.iloc[1].tolist()
    b2, s2 = C.rescale_to_stored(comp_b, comp_s, [("rook", 5)], pred[["gsis_id", "week"]])
    assert b2 is comp_b and s2 is comp_s
