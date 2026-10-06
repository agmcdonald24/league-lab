"""IO-1 (Wave I-O): the context record — the grade on hand-built rows, the as-of corner rank, the freeze rule, the
signals rebuilt through the DFS screen's own functions, the weather label read from the model."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from league_lab import context_record as C
from league_lab import dfs as D


# ------------------------------------------------------------------------------------------------ the grade
def test_bootstrap_known_mean_and_interval():
    miss = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    mean, lo, hi = C.bootstrap_mean(miss, [f"g{i}" for i in range(10)], n_boot=4000, seed=1)
    assert mean == pytest.approx(5.5)
    # the standard error of the mean is 2.87 / sqrt(10) = 0.91: a 95% interval of about 5.5 +- 1.8
    assert 3.5 < lo < 4.2 and 6.8 < hi < 7.5
    # a constant has no spread
    assert C.bootstrap_mean([2.0] * 5, list("abcde")) == (2.0, 2.0, 2.0)
    assert C.bootstrap_mean([], []) == (None, None, None)
    assert C.bootstrap_mean([1.0, 3.0], ["g", "g"])[1:] == (None, None)        # one game: no interval


def test_bootstrap_resamples_whole_games():
    # two games: every receiver of a drawn game comes along, so a resampled mean is 0, 5 or 10 — never 2.5 or 7.5
    miss = [0.0, 0.0, 10.0, 10.0]
    games = ["a", "a", "b", "b"]
    rng_means = set()
    for seed in range(40):
        _m, lo, hi = C.bootstrap_mean(miss, games, n_boot=50, seed=seed)
        rng_means.update({lo, hi})
    assert rng_means <= {0.0, 5.0, 10.0}


def test_grade_counts_and_beat_share():
    df = pd.DataFrame({"miss": [2.0, -1.0, 0.0, 3.0, np.nan], "game_id": ["a", "a", "b", "c", "c"]})
    g = C.grade(df, "x")
    assert (g.n, g.games, g.beat) == (4, 3, 2)                                 # NaN is not graded; 0 did not beat
    assert g.mean_miss == pytest.approx(1.0) and g.beat_share == pytest.approx(0.5)


def test_difference_holds_zero_when_the_groups_are_alike():
    rng = np.random.default_rng(3)
    a = rng.normal(0, 5, 300)
    b = rng.normal(0, 5, 900)
    ga = [f"g{i % 100}" for i in range(300)]
    gb = [f"g{i % 100}" for i in range(900)]
    d, lo, hi = C.bootstrap_diff(a, ga, b, gb)
    assert lo < 0 < hi and lo < d < hi
    d2, lo2, _hi2 = C.bootstrap_diff(a + 3, ga, b, gb)
    assert lo2 > 0 and d2 == pytest.approx(d + 3)


def test_sentences_say_what_the_grade_says():
    row = {"n": 58, "beat": 31, "beat_share": 31 / 58, "vs_rest": 0.42, "vs_rest_lo": -0.9, "vs_rest_hi": 1.7,
           "rest_beat_share": 0.35}
    s = C.worth_sentence(row, "2026 weeks 5–8", corner=False)
    assert s == ("Since 2026 weeks 5–8, listed players scored above their projection in 31 of 58 games (53%; everyone else at "
                 "the position 35%) and finished 0.4 points better than everyone else against it (−0.9 to +1.7) — not "
                 "distinguishable from chance.")
    assert C.verdict(0.1, 2.0) == "more than chance would give" and C.verdict(-2, -0.1) == "less than chance would give"
    assert C.worth_sentence({"n": 0}, "x") is None
    sh = {"corner_certainty": "likely", "corner_tier": "shutdown", "n": 99, "vs_rest": -0.39, "vs_rest_lo": -1.39, "vs_rest_hi": 0.72}
    ez = {"corner_certainty": "likely", "corner_tier": "target", "n": 79, "vs_rest": -0.02, "vs_rest_lo": -1.11, "vs_rest_hi": 1.22}
    c = C.corner_sentence([sh, ez], "2025")
    assert "0.4 points below the other receivers" in c and c.endswith("no measurable effect either way.")
    assert C.tier_sentence(sh).startswith("Graded: no measurable effect (−0.4 points")
    assert C.tier_sentence({**sh, "vs_rest_lo": -2.0, "vs_rest_hi": -0.2}).startswith("Graded: measurably below")


# ------------------------------------------------------------------------------------------------ the as-of rank
def _cov(rows):
    base = {"position": "CB", "snap_position": "CB", "def_completions_allowed": 3.0, "def_yards_allowed": 40.0,
            "def_receiving_td_allowed": 0.0, "def_ints": 0.0}
    return pd.DataFrame([{**base, **r} for r in rows])


def _league(season: int, weeks: range, bad_week: int | None = None):
    """Eight corners on eight teams, one game a week each; corner c7 is torched in ``bad_week`` only."""
    cov, off = [], []
    for w in weeks:
        for i in range(8):
            team, opp = f"T{i}", f"T{(i + 1) % 8}"
            gid = f"{season}_{w:02d}_{team}"
            torched = bad_week == w and i == 7
            cov.append({"gsis_id": f"c{i}", "game_id": gid, "season": season, "week": w, "team": team, "opponent": opp,
                        "coverage_snaps": 35.0, "def_targets": 5.0 + i * 0.1,
                        "def_yards_allowed": 300.0 if torched else 30.0 + i * 3,
                        "def_completions_allowed": 5.0 if torched else 3.0,
                        "def_receiving_td_allowed": 3.0 if torched else 0.0})
            off.append({"game_id": gid, "season": season, "week": w, "offense": opp, "targets": 30.0, "yards": 240.0})
    return _cov(cov), pd.DataFrame(off)


def test_asof_rank_never_reads_the_week_itself_or_later():
    cov_a, off_a = _league(2025, range(1, 9))
    cov_b, off_b = _league(2025, range(1, 9), bad_week=5)        # the same league, c7 torched in week 5
    prev_a, prev_off = _league(2024, range(1, 9))
    a = C.cb_rank_asof(pd.concat([prev_a, cov_a]), pd.concat([prev_off, off_a]), 2025, 5)
    b = C.cb_rank_asof(pd.concat([prev_a, cov_b]), pd.concat([prev_off, off_b]), 2025, 5)
    pd.testing.assert_frame_equal(a.sort_values("gsis_id").reset_index(drop=True),
                                  b.sort_values("gsis_id").reset_index(drop=True))  # week 5 never enters week 5's rank
    after = C.cb_rank_asof(pd.concat([prev_a, cov_b]), pd.concat([prev_off, off_b]), 2025, 6)
    r = after.set_index("gsis_id")
    assert r.loc["c7", "quality_label"] == "target" and r.loc["c7", "quality_rank"] == 8   # week 6 sees week 5
    assert set(a["n_ranked"]) == {8}


def test_tier_and_corner_context():
    assert C.tier_of("shutdown", 3) == "shutdown" and C.tier_of("target", None) == "unranked"
    assert C.tier_of(None, None) == "unranked"
    call = {"call_status": "called", "call_strength": "clear", "likely_cover_gsis_id": "c1", "likely_cover_name": "A. One",
            "other_cover_gsis_id": "c2", "other_cover_name": "B. Two"}
    ranks = {"c1": {"quality_rank": 2, "quality_label": "shutdown", "n_ranked": 64},
             "c2": {"quality_rank": 60, "quality_label": "target", "n_ranked": 64}}
    c = C.corner_context(call, ranks)
    assert (c["certainty"], c["tone"], c["tier"], c["corner_rank"], c["n"]) == ("likely", "difficult", "shutdown", 2, 64)
    u = C.corner_context({**call, "call_strength": "even"}, ranks)
    assert u["certainty"] == "unclear" and u["tone"] == "neutral" and u["words"].startswith("either A. One")
    assert C.corner_context({"call_status": "tight end"}, ranks) is None


def test_rebuilt_signals_go_through_the_screens_functions():
    corner = C.corner_context({"call_status": "called", "call_strength": "clear", "likely_cover_gsis_id": "c9",
                               "likely_cover_name": "Easy"}, {"c9": {"quality_rank": 60, "quality_label": "target", "n_ranked": 64}})
    sig, ok, ok_corner = C.signals_for("WR", 3, corner, None, D.game_environment("KC", 50.5, 3.5, True), None)
    by = {s["signal"]: s for s in sig}
    assert by["defense"]["tone"] == "favorable" and by["corner"]["tone"] == "favorable"
    assert ok is False and ok_corner is True            # today's rule ignores the corner; Wave I-N's counted it
    assert C.defense_tone(1) == "favorable" and C.defense_tone(32) == "difficult" and C.defense_tone(16) == "neutral"
    assert C.defense_tone(None) is None


def test_defense_rank_asof_is_the_screens_rank_before_the_week():
    dvp = pd.DataFrame([
        {"defense": "A", "position": "WR", "week": 1, "points_allowed_per_game_std": 30.0},
        {"defense": "B", "position": "WR", "week": 1, "points_allowed_per_game_std": 20.0},
        {"defense": "C", "position": "WR", "week": 2, "points_allowed_per_game_std": 25.0},   # C's bye in week 1
        {"defense": "A", "position": "WR", "week": 2, "points_allowed_per_game_std": 18.0},
        {"defense": "B", "position": "WR", "week": 3, "points_allowed_per_game_std": 99.0},   # week 3 itself
    ])
    r = C.defense_rank_asof(dvp, 3)
    assert r == {("C", "WR"): (1, 3), ("B", "WR"): (2, 3), ("A", "WR"): (3, 3)}   # latest before week 3, all ranked
    assert C.defense_rank_asof(dvp, 2) == {("A", "WR"): (1, 2), ("B", "WR"): (2, 2)}
    assert C.defense_rank_asof(dvp, 1) == {}


def test_weather_is_not_in_the_projection():
    from league_lab.projections import FEATURES_BY_POSITION
    for pos in ("QB", "RB", "WR", "TE"):
        assert not any(f.startswith("wx_") for f in FEATURES_BY_POSITION[pos])
        assert D.in_projection("weather", pos) is False


# ------------------------------------------------------------------------------------------------ the freeze
K = {w: datetime(2026, 9, 10, 0, 15, tzinfo=UTC) + timedelta(days=7 * (w - 1)) for w in range(1, 6)}


def test_record_plan_freezes_and_never_rewrites():
    now = K[3] - timedelta(hours=10)                      # before week 3's first kickoff
    assert C.record_plan([], K, now) == {1: "reconstruct", 2: "reconstruct", 3: "write"}
    assert C.record_plan([1, 2, 3], K, now) == {1: "keep", 2: "keep", 3: "write"}       # idempotent: 3 replaced
    later = K[3] + timedelta(minutes=1)
    assert C.record_plan([1, 2, 3], K, later) == {1: "keep", 2: "keep", 3: "keep", 4: "write"}
    assert C.record_plan([1, 2], K, later)[3] == "reconstruct"     # missed before kickoff: rebuilt, labelled
    assert C.record_plan([], {}, now) == {}


class _NoCommit:
    """A connection whose commits do nothing: the whole test is one transaction, rolled back at the end."""

    def __init__(self, conn):
        self._c = conn

    def cursor(self, *a, **k):
        return self._c.cursor(*a, **k)

    def commit(self):
        return None

    def rollback(self):
        return None


def _db():
    try:
        import psycopg

        from league_lab.config import get_settings
        return psycopg.connect(get_settings().pipeline_dsn(), autocommit=False, connect_timeout=3)
    except Exception:  # noqa: BLE001
        return None


def test_write_record_is_idempotent_and_keeps_frozen_weeks(monkeypatch):
    conn = _db()
    if conn is None:
        pytest.skip("no database")
    season = 1999                                          # a season no real row has
    games = pd.DataFrame([{"week": w, "kickoff_at": K[w], "game_id": f"g{w}", "home_team": "A", "away_team": "B"} for w in K])
    si = C.SeasonInputs(season, games, pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(),
                        pd.DataFrame(columns=["gsis_id", "week", "game_id", "played", "actual"]))
    proj = {"value": 10.0}

    def fake_rebuild(conn_, si_, week, live=False):
        return pd.DataFrame([{"season": season, "week": week, "gsis_id": f"p{i}", "player_name": f"P{i}", "position": "WR",
                              "team": "A", "opponent": "B", "game_id": f"g{week}", "proj_points": proj["value"],
                              "model_version": "t", "signals": [{"signal": "defense", "tone": "favorable"}],
                              "defense_tone": "favorable", "worth": False, "listed": False, "worth_corner": False,
                              "listed_corner": False, "actual_points": None, "miss": None} for i in range(2)])
    monkeypatch.setattr(C, "load_season", lambda conn_, s: si)
    monkeypatch.setattr(C, "rebuild_week", fake_rebuild)
    nc = _NoCommit(conn)
    try:
        with conn.cursor() as cur:
            cur.execute(C.DDL)
        now = K[3] - timedelta(hours=10)
        r1 = C._write_season(nc, season, now)
        assert (r1.written, r1.reconstructed, r1.rows) == ([3], [1, 2], 6)
        r2 = C._write_season(nc, season, now)                 # the same night again: week 3 replaced, 1-2 kept
        assert (r2.written, r2.reconstructed) == ([3], [])
        proj["value"] = 99.0                                   # the model moves after kickoff …
        r3 = C._write_season(nc, season, K[3] + timedelta(minutes=5))
        assert (r3.written, r3.reconstructed) == ([4], [])
        with conn.cursor() as cur:
            cur.execute("select week, record_source, count(*), min(proj_points), max(proj_points) from ops.context_record "
                        "where season = %s group by 1, 2 order by 1", (season,))
            got = cur.fetchall()
        # … and the frozen weeks keep what they said before it: one copy each, never rewritten
        assert got == [(1, "reconstructed", 2, 10.0, 10.0), (2, "reconstructed", 2, 10.0, 10.0),
                       (3, "kickoff", 2, 10.0, 10.0), (4, "kickoff", 2, 99.0, 99.0)]
    finally:
        conn.rollback()
        conn.close()
