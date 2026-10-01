"""Plan E4 (Wave E): the four feature groups' rules - rookie_prior, oline_quality, qb_x_offense (dbt tables) and
player_prior (built from the model's out-of-fold predictions). Each rule's Python twin is pinned on a fixture, the SQL
is checked to hard-code the same constants, the registries validate, and (with a database) the twins reproduce the
tables on every 2025 row from the upstream tables on their own path."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest
import yaml

from league_lab import experiments as E
from league_lab import projections as P
from league_lab.feature_groups import oline_quality as OQ
from league_lab.feature_groups import personnel as PN
from league_lab.feature_groups import player_prior as PP
from league_lab.feature_groups import qb_x_offense as QX
from league_lab.feature_groups import rookie_prior as RK
from league_lab.feature_groups.oline_quality import Starter as S

ROOT = Path(__file__).resolve().parents[1]
FEATURES_DIR = ROOT / "dbt/models/intermediate/features"
ROOKIE_SQL = (FEATURES_DIR / "int_e4_player_week_rookie_prior.sql").read_text()
STARTER_SQL = (FEATURES_DIR / "int_e4_ol_starter_week.sql").read_text()
OLQ_SQL = (FEATURES_DIR / "int_e4_player_week_oline_quality.sql").read_text()
QBX_SQL = (FEATURES_DIR / "int_e4_player_week_qb_x_offense.sql").read_text()
YML = yaml.safe_load((FEATURES_DIR / "int_e4_feature_groups.yml").read_text())


# ------------------------------------------------------------------------------ rookie_prior
def test_draft_tier_years_in_and_age():
    assert [RK.draft_tier(True, r) for r in (1, 2, 3, 4, 7, None)] == [3, 2, 2, 1, 1, 0]
    assert RK.draft_tier(False, None) is None                    # not in the players table: unknown, not undrafted
    assert RK.years_in(2025, 2025, 2025) == 0                     # a 2025 draftee in 2025: rookie
    assert RK.years_in(2025, 2023, 2023) == 2
    assert RK.years_in(2025, None, 2022) == 3                     # undrafted: his rookie season
    assert RK.years_in(2025, None, 2026) == 0                     # a practice-squad season before nflverse's rookie season
    assert RK.years_in(2025, None, None) is None
    # 2025 week 1 fixtures (the table's values): Bijan Robinson (1.08, 2023), Puka Nacua (5.177, 2023), Brock Purdy (7.262, 2022)
    assert RK.age_on_sep1(2025, date(2002, 1, 30)) == 23.6
    assert RK.age_on_sep1(2025, date(2001, 5, 29)) == 24.3
    assert RK.age_on_sep1(2025, date(1999, 12, 27)) == 25.7
    assert RK.age_on_sep1(2025, None) is None


def test_rookie_sql_hard_codes_the_twins_rules():
    sql = " ".join(ROOKIE_SQL.split())
    assert "when p.draft_round = 1 then 3 when p.draft_round <= 3 then 2 else 1 end" in sql
    assert "when p.draft_round is null then 0" in sql
    assert "greatest(0, u.season - coalesce(p.draft_year, p.rookie_season))" in sql
    assert "make_date(u.season, 9, 1) - p.birth_date) / 365.25" in sql
    # rookie_prior_early: the same seven columns, weeks 1-4 only
    assert RK.EARLY == [c.replace("rk_", "rk_early_", 1) for c in RK.COLUMNS]
    for c, e in zip(RK.COLUMNS, RK.EARLY, strict=True):
        assert f"case when week <= {RK.EARLY_WEEKS} then {c} end as {e}" in sql


# ------------------------------------------------------------------------------ oline_quality
MIN_2025_W5 = [   # the five starters of Minnesota, 2025 week 5 (the D5 hand check: O'Neill, Jackson, Jurgens Out)
    S("00-0036483", 0.9498, False, 36, 7, 0.2731),    # Will Fries
    S("00-0040661", 0.6653, True, 3, 1, 0.0),         # Donovan Jackson (2025 1st round)
    S("00-0039419", 0.5272, True, 3, 7, 0.0),         # Michael Jurgens
    S("00-0034158", 0.6778, True, 109, 2, 0.9865),    # Brian O'Neill
    S("00-0034989", 0.6527, False, 20, 6, 0.3496),    # Justin Skule
]


def test_oline_quality_on_minnesota_2025_week_5():
    assert OQ.quality_ranks(MIN_2025_W5) == {"00-0034158": 1, "00-0034989": 2, "00-0036483": 3, "00-0040661": 4, "00-0039419": 5}
    assert OQ.oline_quality_out(MIN_2025_W5) == {
        "pn_olq_starters_out": 3, "pn_olq_career_starts_out": 109 + 3 + 3, "pn_olq_draft_capital_out": 2 + 3 + 1,
        "pn_olq_best_out": 1, "pn_olq_prev_season_share_out": 0.9865}


def test_oline_quality_nobody_out_unknown_and_ties():
    healthy = [S(f"p{i}", 0.9, False, 10, 1, 0.5) for i in range(5)]
    assert OQ.oline_quality_out(healthy) == {"pn_olq_starters_out": 0, "pn_olq_career_starts_out": 0,
                                             "pn_olq_draft_capital_out": 0, "pn_olq_best_out": 0, "pn_olq_prev_season_share_out": 0}
    assert OQ.oline_quality_out(healthy, report_known=False) is None      # the report is not out: unknown, not "nobody"
    assert OQ.oline_quality_out([]) is None                                # week 1: no window
    # ties on last season's snaps: the window share, then gsis_id
    tied = [S("b", 0.8, True, 0, None, 0.5), S("a", 0.8, False, 0, None, 0.5), S("c", 0.9, False, 0, None, 0.5)]
    assert OQ.quality_ranks(tied) == {"c": 1, "a": 2, "b": 3}
    assert OQ.oline_quality_out(tied)["pn_olq_best_out"] == 3
    assert [OQ.draft_score(r) for r in (1, 2, 3, 4, 7, None)] == [3, 2, 2, 1, 1, 0]


def test_oline_sql_hard_codes_the_twins_rules():
    s = " ".join(STARTER_SQL.split())
    assert "where rn <= 5" in s and "order by snap_share desc nulls last, gsis_id" in s     # D5's five starters
    assert s.count(f"snap_share >= {OQ.START_SHARE}") == 2                                  # a start
    assert "order by coalesce(ps.share, 0) desc, s.snap_share desc nulls last, s.gsis_id" in s
    assert "when pl.draft_round = 1 then 3 when pl.draft_round <= 3 then 2 when pl.draft_round <= 7 then 1 else 0 end" in s
    assert "ps.season = s.season - 1" in s and "(s.season, s.week)" not in s.split("career as")[0]
    assert "case when u.pn_ol_starters_out is not null" in OLQ_SQL                           # D5's NULL rule


# ------------------------------------------------------------------------------ qb_x_offense
def test_qb_x_offense_products():
    assert QX.product(-9.79, 23.5) == -230.065
    assert QX.product(None, 23.5) is None and QX.product(1.0, None) is None
    assert QX.product(0.0, 23.5) == 0.0          # the same QB: gap 0, product 0
    for col, a, b in (("qbx_gap_x_implied", "pn_qb_prev_ppg_diff", "implied_team_total"),
                      ("qbx_gap_x_total", "pn_qb_prev_ppg_diff", "total_line"),
                      ("qbx_gap_x_prev_ppg", "pn_qb_prev_ppg_diff", "prev_team_ppg"),
                      ("qbx_backup_x_implied", "pn_qb_is_rookie_or_backup", "implied_team_total"),
                      ("qbx_gap_x_prev_epa", "pn_qb_prev_ppg_diff", "prev_team_epa_play")):
        assert col in QX.INTERACTIONS and f"{a} * " in QBX_SQL and f"as {col}" in QBX_SQL and b in QBX_SQL
    assert QX.COLUMNS == [*QX.INTERACTIONS, "qbx_gap_bucket"]


def test_qb_gap_bucket():
    # a starter replaced by a backup 9.8 points per start worse: big drop; -4: some drop; the usual QB (0) or a
    # backup for a backup (+1.5): like for like; the starter back from injury (+7): upgrade
    assert [QX.gap_bucket(g) for g in (-9.8, -6.0, -5.99, -2.0, -1.99, 0.0, 1.5, 1.99, 2.0, 7.0)] == [2, 2, 1, 1, 0, 0, 0, 0, -1, -1]
    assert QX.gap_bucket(None) is None
    sql = " ".join(QBX_SQL.split())
    assert (f"when pn.pn_qb_prev_ppg_diff <= {QX.BIG_DROP:g} then 2 when pn.pn_qb_prev_ppg_diff <= -{QX.LIKE_FOR_LIKE:g} then 1 "
            f"when pn.pn_qb_prev_ppg_diff < {QX.LIKE_FOR_LIKE:g} then 0 else -1 end as qbx_gap_bucket") in sql
    assert "(attempts, 0) + coalesce(sacks_suffered, 0) + coalesce(carries, 0)" in sql


# ------------------------------------------------------------------------------ player_prior
def test_ewm_residual_is_asof_and_weighted():
    games = pd.DataFrame({"gsis_id": ["a", "a", "a", "b"], "season": [2024, 2024, 2025, 2025], "week": [1, 3, 2, 1],
                          "resid": [2.0, -1.0, 4.0, 1.0]})
    rows = pd.DataFrame({"gsis_id": ["a", "a", "a", "a", "b", "b", "c"], "season": [2024, 2024, 2025, 2025, 2025, 2025, 2025],
                         "week": [1, 4, 2, 3, 1, 2, 1]})
    out = PP.ewm_residual_asof(games, rows, decay=0.5)
    assert list(out["gsis_id"]) == list(rows["gsis_id"])                        # row order kept
    ewm = out["pp_resid_ewm"].tolist()
    assert pd.isna(ewm[0]) and pd.isna(ewm[4]) and pd.isna(ewm[6])            # nothing before: unknown
    assert ewm[1] == pytest.approx((-1 + 0.5 * 2) / 1.5)                        # newest weighs 1, the one before 0.5
    assert ewm[2] == pytest.approx(0.0)                                         # 2025 week 2 does not see its own game
    assert ewm[3] == pytest.approx((4 - 0.5 + 0.25 * 2) / 1.75)                 # across seasons
    assert ewm[5] == pytest.approx(1.0)
    assert out["pp_resid_games"].tolist() == [0, 2, 2, 3, 0, 1, 0]
    assert [None if pd.isna(v) else int(v) for v in out["pp_asof_week"]] == [None, 3, None, 2, None, 1, None]
    # planting a huge residual in the row's own week (or later) changes nothing: as of the week
    leak = pd.concat([games, pd.DataFrame({"gsis_id": ["a", "a"], "season": [2025, 2025], "week": [3, 9], "resid": [99.0, 99.0]})])
    assert PP.ewm_residual_asof(leak, rows, decay=0.5)["pp_resid_ewm"].tolist()[3] == pytest.approx(ewm[3])
    assert PP.DECAY ** PP.HALF_LIFE == pytest.approx(0.5)


# ------------------------------------------------------------------------------ registries and the harness hook
def test_groups_validate_and_every_column_is_documented():
    reg = E.load_registry()
    assert {"rookie_prior", "rookie_prior_early", "oline_quality", "qb_x_offense", "player_prior"} <= set(reg)
    documented = {c["name"] for m in YML["models"] for c in m.get("columns", []) if c.get("description")}
    for mod in (RK, OQ, QX):
        for name, spec in mod.GROUPS.items():
            assert set(spec["columns"]) <= documented, f"{name}: undocumented columns"
            types = {c: "double precision" for c in spec["columns"]} | {"gsis_id": "text", "season": "integer", "week": "integer"}
            g = E.check_spec(name, spec, types)
            assert g.table == mod.TABLE and not set(g.columns) & set(P.ALL_FEATURES)
    spec = PP.GROUPS["player_prior"]
    assert callable(spec["build"]) and spec["table"] == PP.TABLE
    E.check_spec("player_prior", spec, {"gsis_id": "text", "season": "integer", "week": "integer", "pp_resid_ewm": "double precision",
                                         "pp_resid_games": "integer", "pp_asof_week": "integer"})
    assert set(OQ.GROUPS["oline_quality"]["in_season"]) == set(OQ.COLUMNS)     # NULL in week 1: the no-peek check 4
    assert not set(OQ.COLUMNS) & set(PN.OLINE)                                 # copies, renamed: no join clash with D5's oline


def test_get_group_runs_a_groups_build_hook_first(monkeypatch):
    calls = []
    spec = {"table": "ops.x", "columns": ["pp_x"], "build": lambda conn: calls.append(conn)}
    monkeypatch.setattr(E, "load_registry", lambda: {"derived": spec})
    monkeypatch.setattr(E, "describe_table", lambda conn, t: {"gsis_id": "text", "season": "integer", "week": "integer", "pp_x": "double precision"})
    g = E.get_group("CONN", "derived")
    assert calls == ["CONN"] and g.columns == ["pp_x"]


# ------------------------------------------------------------------------------ the twins reproduce the tables (database)
@pytest.fixture(scope="module")
def conn():
    psycopg = pytest.importorskip("psycopg")
    from league_lab.config import get_settings

    try:
        c = psycopg.connect(get_settings().pipeline_dsn(), connect_timeout=3, autocommit=True)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"no database: {exc}")
    with c:
        if not c.execute("select to_regclass('intermediate.int_e4_player_week_oline_quality')").fetchone()[0]:
            pytest.skip("the int_e4_* tables are not built (league-lab dbt build --select '*int_e4_*+')")
        yield c


def test_sql_matches_the_rookie_twins_on_2025(conn):
    players = {r[0]: r[1:] for r in conn.execute("select gsis_id, draft_year, draft_round, draft_pick, rookie_season, birth_date::date "
                                                 "from raw.nfl_players where gsis_id is not null")}
    rows = conn.execute("""select gsis_id, rk_draft_round, rk_draft_pick, rk_draft_tier, rk_undrafted, rk_years_in, rk_is_rookie, rk_age
                           from intermediate.int_e4_player_week_rookie_prior where season = 2025""").fetchall()
    early = conn.execute(f"""select count(*) filter (where week > {RK.EARLY_WEEKS} and num_nonnulls({', '.join(RK.EARLY)}) > 0),
                                    count(*) filter (where week <= {RK.EARLY_WEEKS} and ({', '.join(RK.EARLY)})
                                                     is distinct from ({', '.join(RK.COLUMNS)}))
                             from intermediate.int_e4_player_week_rookie_prior""").fetchone()
    assert early == (0, 0)
    assert len(rows) > 9000
    bad = []
    for gid, rnd, pick, tier, undrafted, yrs, rookie, age in rows:
        p = players.get(gid)
        want_tier = RK.draft_tier(p is not None, p[1] if p else None)
        want_yrs = RK.years_in(2025, p[0], p[3]) if p else None
        want = (p[1] if p else None, p[2] if p else None, want_tier, None if p is None else int(p[1] is None), want_yrs,
                None if want_yrs is None else int(want_yrs == 0), RK.age_on_sep1(2025, p[4]) if p else None)
        got = (rnd, pick, tier, undrafted, yrs, rookie, None if age is None else float(age))
        if got != want:
            bad.append((gid, got, want))
    assert not bad, bad[:5]


def test_sql_matches_the_oline_quality_twin_on_2025(conn):
    """Independent path: D5's twin picks the five from the window, careers and last season's snaps are re-counted
    from int_pn_player_game, the draft from raw.nfl_players."""
    draft = dict(conn.execute("select gsis_id, draft_round from raw.nfl_players where gsis_id is not null").fetchall())
    games = conn.execute("""select gsis_id, season, week, played, snap_share from intermediate.int_pn_player_game
                            where pos_group = 'OL' or gsis_id in (select gsis_id from intermediate.int_pn_window_player
                                                                  where season = 2025 and pos_group = 'OL')""").fetchall()
    starts: dict[str, list[tuple[int, int]]] = {}
    prev_share: dict[str, float] = {}
    for gid, s, w, played, share in games:
        if played and share is not None and float(share) >= OQ.START_SHARE:
            starts.setdefault(gid, []).append((s, w))
        if s == 2024:
            prev_share[gid] = prev_share.get(gid, 0.0) + float(share or 0)
    window: dict[tuple[str, int], list[PN.WindowLineman]] = {}
    for team, week, gid, share, rep, ros, ros_team in conn.execute(
            """select team, week, gsis_id, snap_share, report_status, roster_status, roster_team
               from intermediate.int_pn_window_player where season = 2025 and pos_group = 'OL'"""):
        window.setdefault((team, week), []).append(PN.WindowLineman(gid, float(share), rep, ros, ros_team == team))
    rows = conn.execute("""select distinct pn.team, q.week, q.pn_olq_starters_out, q.pn_olq_career_starts_out, q.pn_olq_draft_capital_out,
                                  q.pn_olq_best_out, q.pn_olq_prev_season_share_out
                           from intermediate.int_e4_player_week_oline_quality as q
                           join intermediate.int_player_week_personnel as pn using (gsis_id, season, week)
                           where q.season = 2025 and q.pn_olq_starters_out is not null""").fetchall()
    assert len(rows) > 400
    bad = []
    for team, week, *got in rows:
        five = [S(p.gsis_id, p.snap_share, PN.is_out_injured(p), sum(1 for sw in starts.get(p.gsis_id, []) if sw < (2025, week)),
                  draft.get(p.gsis_id), round(prev_share.get(p.gsis_id, 0.0) / 17, 4))
                for p in PN.ol_starters(window.get((team, week), []))]
        want = OQ.oline_quality_out(five)
        got_d = dict(zip(["pn_olq_starters_out", "pn_olq_career_starts_out", "pn_olq_draft_capital_out", "pn_olq_best_out",
                          "pn_olq_prev_season_share_out"], [float(g) for g in got], strict=True))
        if want is None or any(abs(got_d[k] - want[k]) > 1e-3 for k in want):
            bad.append((team, week, got_d, want))
    assert not bad, bad[:5]


def test_sql_matches_the_qbx_products_on_2025(conn):
    prev = {}
    for home, away, hs, as_ in conn.execute("""select home_team, away_team, home_score, away_score from analytics.dim_game
                                               where season = 2024 and season_type = 'REG' and home_score is not null"""):
        for t, pts in ((home, hs), (away, as_)):
            t = {"OAK": "LV", "SD": "LAC", "STL": "LA"}.get(t, t)
            prev.setdefault(t, []).append(float(pts))
    rows = conn.execute("""select pn.team, pn.pn_qb_prev_ppg_diff, pn.pn_qb_is_rookie_or_backup, u.implied_team_total, u.total_line,
                                  q.qbx_gap_x_implied, q.qbx_gap_x_total, q.qbx_gap_x_prev_ppg, q.qbx_backup_x_implied,
                                  q.qbx_gap_bucket
                           from intermediate.int_e4_player_week_qb_x_offense as q
                           join intermediate.int_player_week_personnel as pn using (gsis_id, season, week)
                           join intermediate.int_player_week_universe as u using (gsis_id, season, week)
                           where q.season = 2025""").fetchall()
    assert len(rows) > 9000

    def f(v):
        return None if v is None else float(v)

    bad = []
    for team, gap, backup, implied, total, *got in rows:
        ppg = round(sum(prev[team]) / len(prev[team]), 2) if team in prev else None
        want = [QX.product(f(gap), f(implied)), QX.product(f(gap), f(total)), QX.product(f(gap), ppg), QX.product(f(backup), f(implied)),
                QX.gap_bucket(f(gap))]
        if any((a is None) != (b is None) or (a is not None and abs(float(a) - b) > 2e-3) for a, b in zip(got, want, strict=True)):
            bad.append((team, got, want))
    assert not bad, bad[:5]


def test_player_prior_table_is_asof_and_reproduces_from_the_oof_projections(conn):
    if not conn.execute("select to_regclass(%s)", (PP.TABLE,)).fetchone()[0]:
        pytest.skip("ops.player_prior_oof not built (league-lab experiment player_prior builds it)")
    assert conn.execute(f"select count(*) from {PP.TABLE} where pp_asof_week >= week").fetchone()[0] == 0     # noqa: S608
    ref = next(iter(P.league_scorings(conn)))
    pred = pd.DataFrame(conn.execute(f'select gsis_id, season, week, played, "proj_{ref}", "actual_{ref}" from {PP.PRED_TABLE} '   # noqa: S608
                                     "where season between 2024 and 2025").fetchall(),
                        columns=["gsis_id", "season", "week", "played", "proj", "actual"])
    assert pred["season"].min() == 2024
    g = pred[pred["played"] & pred["actual"].notna()].assign(resid=lambda d: d["actual"] - d["proj"])
    rows = pd.DataFrame(conn.execute(f"select gsis_id, season, week, pp_resid_ewm, pp_resid_games from {PP.TABLE} where season = 2025")  # noqa: S608
                        .fetchall(), columns=["gsis_id", "season", "week", "ewm", "n"])
    # 2025 rows from 2024-2025 games only: a row whose history starts in 2024 (n = his 2024 + 2025 games) reproduces exactly
    want = PP.ewm_residual_asof(g[["gsis_id", "season", "week", "resid"]], rows[["gsis_id", "season", "week"]])
    n24 = g[g["season"] == 2024].groupby("gsis_id").size()
    full = conn.execute(f"select gsis_id, count(*) from {PP.PRED_TABLE} where played and season < 2024 group by 1").fetchall()  # noqa: S608
    older = {r[0] for r in full}
    m = rows.merge(want, on=["gsis_id", "season", "week"])
    m = m[~m["gsis_id"].isin(older) & m["gsis_id"].isin(n24.index)]
    assert len(m) > 500
    assert (m["n"] == m["pp_resid_games"]).all()
    assert (m["ewm"].astype(float) - m["pp_resid_ewm"]).abs().max() < 1e-9
