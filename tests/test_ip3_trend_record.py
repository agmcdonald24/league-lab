"""IP-3 (Wave I-P): grade what Trends ("below / above expectation") and the role chips ("role up / down") claim — the
as-of tag (a week's own game never enters its own tag), the next-k outcomes, the grade on hand-built rows (a known mean
and interval), the sentences, the record's freeze and backfill (idempotent), and a record of Wave I-O's shape."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from league_lab import context_record as C


def _games(pid="p1", pos="WR", acts=(10.0, 4.0, 6.0, 20.0, 8.0), xps=(8.0, 9.0, 9.0, 9.0, 9.0), tds=(0, 0, 0, 2, 0),
           rz=(1, 1, 1, 1, 0), shares=(0.20, 0.20, 0.21, 0.22, 0.20)):
    n = len(acts)
    return pd.DataFrame({"gsis_id": pid, "week": list(range(1, n + 1)), "position": pos, "actual": list(acts),
                         "points_expected": list(xps), "expected_known": True, "tds": list(tds), "passing_tds": 0,
                         "red_zone_targets": list(rz), "red_zone_carries": 0, "target_share": list(shares),
                         "carry_share": np.nan})


# ------------------------------------------------------------------------------------------------ the tag, as of
def test_tag_words_follow_the_screen():
    assert C.TREND_NEAR == 0.5
    assert C.trend_tag(-0.51) == "below" and C.trend_tag(0.51) == "above"
    assert C.trend_tag(0.5) == "near" and C.trend_tag(-0.5) == "near" and C.trend_tag(0.0) == "near"
    assert C.trend_tag(None) is None and C.trend_tag(float("nan")) is None


def test_a_weeks_own_game_never_enters_its_own_tag():
    g = _games()
    t = C.asof_trend(g).set_index("week")
    # week 1: no game before it — unknown, never 0
    assert t.loc[1, "trend_games"] == 0 and pd.isna(t.loc[1, "trend_gap"])
    assert pd.isna(t.loc[1, "trend_tag"])
    # week 3: weeks 1-2 only: (10 - 8 + 4 - 9) / 2 = -1.5 -> below; ppg 7.0
    assert t.loc[3, "trend_gap"] == pytest.approx(-1.5) and t.loc[3, "trend_tag"] == "below"
    assert t.loc[3, "ppg_before"] == pytest.approx(7.0) and t.loc[3, "trend_games"] == 2
    # change week 3's game and every later one: week 3's tag does not move
    g2 = g.copy()
    g2.loc[g2["week"] >= 3, "actual"] = 99.0
    assert C.asof_trend(g2).set_index("week").loc[3, "trend_gap"] == pytest.approx(-1.5)
    # the record's freeze reads the same thing for the week, with or without the week's own game in the frame
    w3 = C.trend_asof_week(g, 3)["p1"]
    assert w3[0] == 2 and w3[3] == pytest.approx(-1.5) and w3[4] == "below"
    assert C.trend_asof_week(g2, 3)["p1"][3] == pytest.approx(-1.5)
    assert C.trend_asof_week(g, 1) == {}


def test_reasons_follow_the_screens_rules():
    # below: no touchdowns on 2+ red-zone chances
    assert C.trend_reason("WR", -2.0, 3, 0, 3, 0, 0.2, 0.2, False) == "touchdowns"
    # below: his quarterback changed (not for a quarterback)
    assert C.trend_reason("WR", -2.0, 3, 1, 1, 0, 0.2, 0.2, True) == "quarterback"
    assert C.trend_reason("QB", -2.0, 3, 0, 0, 3, None, None, True) == "none"
    # below: his share fell 6 points or more
    assert C.trend_reason("TE", -2.0, 3, 1, 1, 0, 0.25, 0.18, False) == "share"
    # above: 2+ touchdowns at 0.6 per game; a QB with 2 touchdown passes per game
    assert C.trend_reason("RB", 2.0, 3, 2, 2, 0, 0.5, 0.5, False) == "touchdowns"
    assert C.trend_reason("QB", 2.0, 2, 0, 0, 4, None, None, False) == "touchdowns"
    # above: the share rose; nothing stands out; near: no reason at all
    assert C.trend_reason("WR", 2.0, 4, 1, 1, 0, 0.15, 0.25, False) == "share"
    assert C.trend_reason("WR", 2.0, 4, 1, 1, 0, 0.20, 0.21, False) == "none"
    assert C.trend_reason("WR", 0.3, 4, 0, 5, 0, 0.2, 0.2, False) is None


# ------------------------------------------------------------------------------------------------ the outcomes
def test_next_k_outcomes_start_with_the_weeks_own_game():
    g = pd.DataFrame({"gsis_id": "p", "week": [1, 2, 3, 5], "actual": [10.0, 12.0, 8.0, 14.0],
                      "proj_points": [9.0, 10.0, np.nan, 10.0]})
    o = C.outcomes(g, ks=(1, 2)).set_index("week")
    assert o.loc[1, "miss1"] == pytest.approx(1.0) and o.loc[1, "miss2"] == pytest.approx(1.5)
    assert np.isnan(o.loc[2, "miss2"])          # week 3 has no projection: the two-game window is not graded
    assert np.isnan(o.loc[5, "miss2"])          # one game left
    assert o.loc[5, "pts1"] == pytest.approx(14.0)


def test_grade_on_hand_built_rows_a_known_mean_and_interval():
    rows = []
    for p in range(20):
        for w in range(1, 4):
            below = p < 10
            rows.append({"gsis_id": f"p{p}", "season": 2025, "week": w, "position": "WR", "player": f"p{p}:2025",
                         "trend_tag": "below" if below else "near", "trend_gap": -2.0 - p / 10 if below else 0.0,
                         "trend_reason": "none" if below else None, "ppg_before": 5.0,
                         "miss1": 1.0 if below else 0.0, "pts1": 7.0 if below else 5.0})
    T = pd.DataFrame(rows)
    g = C.trend_grade(T, ks=(1,))
    r = next(x for x in g if x["tag"] == "below" and x["by"] == "all" and x["k"] == 1)
    assert (r["n"], r["players"]) == (30, 10)
    assert (r["mean"], r["lo"], r["hi"]) == (1.0, 1.0, 1.0)               # a constant: no spread
    assert (r["vs_rest"], r["vs_rest_lo"], r["vs_rest_hi"]) == (1.0, 1.0, 1.0)
    assert r["above"] == 1.0 and r["rest_above"] == 0.0
    assert (r["raw_mean"], r["raw_vs_rest"]) == (2.0, 2.0)
    sizes = [x for x in g if x["by"] == "size" and x["k"] == 1]
    assert [x["grp"] for x in sizes] == ["small", "middle", "large"] and sum(x["n"] for x in sizes) == 30


def test_the_interval_resamples_whole_players():
    # two players, each with many identical rows: the interval spans the two players' values, not a row-level sliver
    v = [0.0] * 50 + [2.0] * 50
    mean, lo, hi = C.bootstrap_mean(v, ["a"] * 50 + ["b"] * 50, n_boot=2000, seed=3)
    assert mean == pytest.approx(1.0) and lo == pytest.approx(0.0) and hi == pytest.approx(2.0)


def test_role_trend_rebuilt_before_the_week_and_its_share_followed():
    weeks = list(range(1, 8))
    tgt = [3, 3, 3, 3, 9, 9, 6]
    g = pd.DataFrame({"gsis_id": "r1", "week": weeks, "position": "WR", "targets": tgt, "team_targets": [30] * 7,
                      "carries": 0, "team_carries": [25] * 7, "offense_snaps": [40] * 7, "offense_snap_pct": [0.6] * 7})
    R = C.asof_role(g).set_index("week")
    assert pd.isna(R.loc[5, "role_trend"]) and R.loc[5, "role_games"] == 4      # weeks 1-4: nothing moved
    assert R.loc[7, "role_trend"] == "up" and R.loc[7, "measure"] == "target_share"   # weeks 5-6 against 1-4
    assert R.loc[7, "before"] == pytest.approx(0.1) and R.loc[7, "recent"] == pytest.approx(0.3)
    assert R.loc[7, "next1"] == pytest.approx(0.2) and pd.isna(R.loc[7, "next2"])
    # week 7's own game never enters week 7's trend: change it, the trend stays
    g2 = g.copy()
    g2.loc[g2["week"] == 7, "targets"] = 0
    assert C.asof_role(g2).set_index("week").loc[7, "recent"] == pytest.approx(0.3)


def test_role_priced_compares_with_the_games_that_could_have_had_a_call():
    rows = [{"player": f"u{i}", "week": 6, "position": "TE", "role_trend": "up", "role_games": 5, "miss1": 1.0}
            for i in range(5)]
    rows += [{"player": f"n{i}", "week": 6, "position": "TE", "role_trend": None, "role_games": 5, "miss1": 0.0}
             for i in range(5)]
    rows += [{"player": f"e{i}", "week": 3, "position": "TE", "role_trend": None, "role_games": 2, "miss1": 9.0}
             for i in range(5)]                                  # too early for a call: not the rest
    r = C.role_priced(pd.DataFrame(rows), ks=(1,))[0]
    assert (r["trend"], r["n"], r["rest_n"], r["vs_rest"]) == ("up", 5, 5, 1.0)


# ------------------------------------------------------------------------------------------------ the words
def _cell(tag, vs, lo, hi, n, raw):
    return {"tag": tag, "by": "all", "grp": "all", "k": 1, "n": n, "vs_rest": vs, "vs_rest_lo": lo, "vs_rest_hi": hi,
            "raw_mean": raw}


def test_sentences_say_what_the_grade_says():
    rows = [_cell("below", 0.17, -0.15, 0.49, 2467, 1.54), _cell("above", -0.15, -0.45, 0.15, 1815, -1.91)]
    w = C.trend_sentence(rows, "2025 and 2026 weeks 1–4")
    assert w.startswith("Graded on 2025 and 2026 weeks 1–4 (Half PPR), in their next game: players below expectation "
                        "scored 1.5 points more than their points per game before and finished 0.2 points above the other "
                        "players against their projection (−0.1 to +0.5; 2,467 games) — no measurable difference;")
    assert "not a reason to buy or sell on its own" in w
    h = C.trend_head(rows, "2025 and 2026 weeks 1–4")
    assert h == ("Graded on 2025 and 2026 weeks 1–4 (Half PPR): in their next game, players below expectation scored 1.5 points more "
                 "than their average before and players above it 1.9 less — and their projections already expected that "
                 "(no measurable difference against them; 4,282 games).")
    # a measured effect changes the words (never "no measurable difference" when the interval is clear of 0)
    rows[0] = _cell("below", -0.27, -0.43, -0.12, 11129, 1.19)
    assert "less than their projection gave them" in C.trend_sentence(rows, "2021–2025")
    assert "those below expectation finished 0.3 points below the rest" in C.trend_head(rows, "2021–2025")
    assert C.trend_sentence([], "x") is None and C.trend_head(rows[:1], "x") is None
    r = C.role_sentence([{"trend": "up", "by": "all", "grp": "all", "k": 1, "n": 1022, "vs_rest": 0.22,
                          "vs_rest_lo": -0.21, "vs_rest_hi": 0.64}], "2025 weeks 5–18")
    assert r == ("Graded on 2025 weeks 5–18 (Half PPR), in their next game: after \"role up\" players finished 0.2 "
                 "points above the other players against their projection (−0.2 to +0.6; 1,022 games) — no measurable "
                 "difference.")


# ------------------------------------------------------------------------------------------------ the record
def test_grade_of_a_record_without_the_trend_columns_keeps_wave_io_rows():
    h = pd.DataFrame([{"season": 2025, "week": 1, "game_id": "g", "position": "WR", "proj_points": 10.0, "miss": 1.0,
                       "corner_certainty": "likely", "corner_tier": "shutdown", "defense_tone": None, "role_trend": None,
                       "game_tone": None, "worth": False, "listed": False, "worth_corner": False, "listed_corner": False,
                       "worth_two": False, "record_source": "reconstructed"}])
    rows = C.grade_rows(h)
    assert {r["kind"] for r in rows} >= {"corner", "summary"}
    assert not [r for r in rows if r["kind"] in ("trend", "trend_raw", "role")]


def test_grade_of_the_record_reads_the_next_games_from_the_record():
    rows = []
    for p in range(15):
        for w in range(1, 7):
            below, above = p < 6, p >= 12
            rows.append({"season": 2025, "week": w, "game_id": f"g{w}", "position": "WR", "gsis_id": f"p{p}",
                         "proj_points": 10.0, "actual_points": 11.0 if below else 10.0, "miss": 1.0 if below else 0.0,
                         "corner_certainty": None, "corner_tier": None, "defense_tone": None,
                         "role_trend": "up" if (below and w >= 5) else None, "game_tone": None, "worth": False,
                         "listed": False, "worth_corner": False, "listed_corner": False, "worth_two": False,
                         "record_source": "reconstructed", "trend_games": w - 1, "trend_ppg": 9.0 if w > 1 else None,
                         "trend_gap": (-2.0 if below else 0.0) if w > 1 else None,
                         "trend_tag": ("below" if below else "above" if above else "near") if w > 1 else None,
                         "trend_reason": "none" if below and w > 1 else None})
    out = C.grade_rows(pd.DataFrame(rows))
    t = {r["grp"]: r for r in out if r["kind"] == "trend"}
    assert t["below/all/all/1"]["n"] == 30 and t["below/all/all/1"]["vs_rest"] == 1.0
    assert t["below/all/all/4"]["n"] == 12                # weeks 2-3 of six players have four graded games left
    raw = {r["grp"]: r for r in out if r["kind"] == "trend_raw"}
    assert raw["below/all/all/1"]["mean_miss"] == 2.0 and raw["below/all/all/1"]["beat_share"] is None
    s = {r["grp"]: r["words"] for r in out if r["kind"] == "summary"}
    assert s["trend"].startswith("Graded on 2025 weeks 1–6 (Half PPR), in their next game:")
    assert s["trend_head"] and "role" in s and "after \"role up\"" in s["role"]


K = {1: datetime(1999, 9, 9, 0, 20, tzinfo=UTC), 2: datetime(1999, 9, 16, 0, 15, tzinfo=UTC)}


class _NoCommit:
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


def test_the_freeze_keeps_the_tag_and_the_backfill_is_idempotent(monkeypatch):
    conn = _db()
    if conn is None:
        pytest.skip("no database")
    season = 1999                                          # a season no real row has
    games = pd.DataFrame([{"week": w, "kickoff_at": K[w], "game_id": f"g{w}", "home_team": "A", "away_team": "B"} for w in K])
    si = C.SeasonInputs(season, games, pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(),
                        pd.DataFrame(columns=["gsis_id", "week", "game_id", "played", "actual"]))

    def fake_rebuild(conn_, si_, week, live=False):
        return pd.DataFrame([{"season": season, "week": week, "gsis_id": "p0", "player_name": "P", "position": "WR",
                              "team": "A", "opponent": "B", "game_id": f"g{week}", "proj_points": 10.0, "model_version": "t",
                              "signals": [], "worth": False, "listed": False, "worth_corner": False, "listed_corner": False,
                              "actual_points": None, "miss": None,
                              **C.trend_fields((3, 7.0, 9.0, -2.0, "below", "none"))}])
    monkeypatch.setattr(C, "load_season", lambda conn_, s: si)
    monkeypatch.setattr(C, "rebuild_week", fake_rebuild)
    monkeypatch.setattr(C, "load_trend_games", lambda conn_, s, actual=None: (_games("p9"), {}))
    nc = _NoCommit(conn)
    try:
        with conn.cursor() as cur:
            cur.execute(C.DDL)
        C._write_season(nc, season, K[2] - timedelta(hours=10))
        C._write_season(nc, season, K[2] - timedelta(hours=9))        # the same night again
        with conn.cursor() as cur:
            cur.execute("select week, record_source, trend_games, trend_gap, trend_tag, trend_reason from ops.context_record "
                        "where season = %s order by week", (season,))
            assert cur.fetchall() == [(1, "reconstructed", 3, -2.0, "below", "none"), (2, "kickoff", 3, -2.0, "below", "none")]
            # a row written before the columns existed (Wave I-O's shape): filled once from the games before its week
            cur.execute("insert into ops.context_record (season, week, gsis_id, record_source) values (%s, 3, 'p9', 'kickoff'), "
                        "(%s, 3, 'nobody', 'kickoff')", (season, season))
        assert C.backfill_trend(nc) >= 2
        assert C.backfill_trend(nc) == 0                                 # idempotent: nothing left to fill
        with conn.cursor() as cur:
            cur.execute("select gsis_id, trend_games, trend_gap, trend_tag from ops.context_record where season = %s and week = 3 "
                        "order by gsis_id", (season,))
            got = cur.fetchall()
        assert got[0] == ("nobody", 0, None, None)                       # no game before: 0 games, unknown gap
        assert got[1][0] == "p9" and got[1][1] == 2 and got[1][2] == pytest.approx(-1.5) and got[1][3] == "below"
    finally:
        conn.rollback()
        conn.close()


def test_migrate_creates_the_record_tables_on_a_fresh_database():
    """The nightly restores ops.context_record / ops.context_grade into a fresh database right after `db migrate`
    (restore-state counts every state table first): migrate must create both, with the trend columns."""
    import inspect

    from league_lab import db
    src = inspect.getsource(db.migrate)
    assert "context_record.DDL" in src and "context_record.GRADE_DDL" in src
    for col in ("trend_games", "trend_ppg", "trend_gap", "trend_tag", "trend_reason"):
        assert col in C.DDL and col in C.COLUMNS
    conn = _db()
    if conn is None:
        pytest.skip("no database")
    try:
        with conn.cursor() as cur:
            # inside a rolled-back transaction: the DDL as migrate runs it, then the columns it leaves
            cur.execute(C.DDL)
            cur.execute(C.GRADE_DDL)
            cur.execute("""select column_name from information_schema.columns
                           where table_schema = 'ops' and table_name = 'context_record'""")
            cols = {r[0] for r in cur.fetchall()}
        assert set(C.COLUMNS) <= cols
    finally:
        conn.rollback()
        conn.close()
