"""Plan D5: personnel features - the QB-change rule and the offensive-line count. The rules live in SQL
(``int_player_week_personnel`` / ``int_pn_window_player``); their Python twins (league_lab.feature_groups.personnel)
are pinned here on fixtures, the SQL is checked to hard-code the same constants, and (with a database) the twins
reproduce the table on every 2025 row."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from league_lab import experiments as E
from league_lab.feature_groups import personnel as PN
from league_lab.feature_groups.personnel import WindowLineman as L

ROOT = Path(__file__).resolve().parents[1]
FEATURES_DIR = ROOT / "dbt/models/intermediate/features"
PERSONNEL_SQL = (FEATURES_DIR / "int_player_week_personnel.sql").read_text()
WINDOW_SQL = (FEATURES_DIR / "int_pn_window_player.sql").read_text()
STATUS_SQL = (FEATURES_DIR / "int_pn_player_week_status.sql").read_text()
PLAYER_GAME_SQL = (FEATURES_DIR / "int_pn_player_game.sql").read_text()
YML = yaml.safe_load((FEATURES_DIR / "int_player_week_personnel.yml").read_text())

BURROW, BROWNING, FLACCO, GENO = "00-0036442", "00-0035100", "00-0026158", "00-0030565"


# ------------------------------------------------------------------------------ the QB-change rule
def test_usual_qb_is_the_majority_of_his_last_four_played_games():
    # a WR: three games with A, one with B -> A; the projected starter B is a change
    games = [(2025, 1, "A"), (2025, 2, "A"), (2025, 3, "B"), (2025, 4, "A")]
    assert PN.usual_qb(games, 2025, 5) == "A"
    assert PN.qb_changed("B", PN.usual_qb(games, 2025, 5)) == 1
    assert PN.qb_changed("A", PN.usual_qb(games, 2025, 5)) == 0
    # only the newest four count: an old run of C does not outvote the recent A's
    games = [(2025, 1, "C"), (2025, 2, "C"), (2025, 3, "C"), (2025, 5, "A"), (2025, 6, "A"), (2025, 7, "A"), (2025, 8, "B")]
    assert PN.usual_qb(games, 2025, 9) == "A"


def test_usual_qb_tie_goes_to_the_most_recent():
    games = [(2025, 1, "A"), (2025, 2, "A"), (2025, 3, "B"), (2025, 4, "B")]
    assert PN.usual_qb(games, 2025, 5) == "B"
    games = [(2025, 1, "B"), (2025, 2, "A"), (2025, 3, "B"), (2025, 4, "A")]
    assert PN.usual_qb(games, 2025, 5) == "A"


def test_usual_qb_reads_only_games_before_the_week():
    # the week's own game (and anything later) never counts: as of the week
    games = [(2025, 1, "A"), (2025, 2, "A"), (2025, 3, "B"), (2025, 4, "B"), (2025, 5, "B")]
    assert PN.usual_qb(games, 2025, 3) == "A"
    # week 1: last season's games (a receiver traded in the offseason: his old quarterback)
    games = [(2024, 15, "OLD"), (2024, 16, "OLD"), (2024, 17, "OLD"), (2025, 1, "NEW")]
    assert PN.usual_qb(games, 2025, 1) == "OLD"
    assert PN.qb_changed("NEW", PN.usual_qb(games, 2025, 1)) == 1
    # week 2: one game with NEW, three with OLD -> still OLD (his history is mostly with the old QB)
    assert PN.usual_qb(games, 2025, 2) == "OLD"
    # two seasons back is too old: unknown, not "no change"
    assert PN.usual_qb([(2023, 10, "X")], 2025, 1) is None
    assert PN.qb_changed("Y", None) is None
    assert PN.qb_changed(None, "X") is None


def test_cincinnati_2025_week_3_fixture():
    """Burrow started weeks 1-2 and was hurt in week 2; Browning is the projected starter of week 3."""
    chase = [(2024, w, BURROW) for w in range(14, 19)] + [(2025, 1, BURROW), (2025, 2, BURROW)]
    assert PN.usual_qb(chase, 2025, 2) == BURROW and PN.qb_changed(BURROW, PN.usual_qb(chase, 2025, 2)) == 0
    assert PN.usual_qb(chase, 2025, 3) == BURROW and PN.qb_changed(BROWNING, PN.usual_qb(chase, 2025, 3)) == 1
    # Noah Fant came from Seattle: his history was built with Geno Smith (week 2 is a change even with Burrow)
    fant = [(2024, 16, GENO), (2024, 17, GENO), (2024, 18, GENO), (2025, 1, BURROW)]
    assert PN.qb_changed(BURROW, PN.usual_qb(fant, 2025, 2)) == 1


# ------------------------------------------------------------------------------ the offensive-line count
WINDOW = [
    L("ol1", 1.00), L("ol2", 0.99, "Out"), L("ol3", 0.97, "Doubtful"), L("ol4", 0.95, "Questionable"),
    L("ol5", 0.60, roster_status="RES"), L("ol6", 0.45, "Out"), L("ol7", 0.05, roster_status="RES"),
]


def test_ol_starters_are_the_five_with_the_most_snaps():
    assert [p.gsis_id for p in PN.ol_starters(WINDOW)] == ["ol1", "ol2", "ol3", "ol4", "ol5"]
    # ties go to gsis_id, as the SQL orders them
    tied = [L("b", 0.9), L("a", 0.9), L("c", 0.8), L("d", 0.7), L("e", 0.6), L("f", 0.6)]
    assert [p.gsis_id for p in PN.ol_starters(tied)] == ["a", "b", "c", "d", "e"]


def test_ol_out_counts_out_doubtful_and_reserve_not_questionable():
    # ol2 Out, ol3 Doubtful, ol5 on injured reserve: 3 (ol4 Questionable plays; ol6 / ol7 are not starters)
    assert PN.ol_starters_out(WINDOW) == (3, round(0.99 + 0.97 + 0.60, 4))


def test_ol_out_ignores_the_game_day_inactive_list_and_other_teams_reserve():
    window = [L("a", 1.0, roster_status="INA"), L("b", 1.0, roster_status="ACT"), L("c", 0.9, roster_status="RES", roster_team_is_team=False),
              L("d", 0.9), L("e", 0.8, "Out")]
    assert PN.ol_starters_out(window) == (1, 0.8)


def test_ol_out_is_unknown_without_a_report_or_a_window():
    assert PN.ol_starters_out(WINDOW, report_known=False) is None
    assert PN.ol_starters_out([]) is None      # week 1: no game yet this season


def test_minnesota_2025_week_5_fixture():
    """The hand-checked case (docs/METRICS.md § Personnel): weeks 1-4 snap shares, week 5 report / roster."""
    window = [L("Fries", 0.9498), L("O'Neill", 0.6778, "Out", "INA"), L("Jackson", 0.6653, "Out", "INA"),
              L("Skule", 0.6527, None, "ACT"), L("Jurgens", 0.5272, "Out", "INA"), L("Darrisaw", 0.4770, None, "ACT"),
              L("Kelly", 0.4728, "Out", "RES"), L("Brandel", 0.4310)]
    assert PN.ol_starters_out(window) == (3, 1.8703)


# ------------------------------------------------------------------------------ the SQL uses the same rule
def test_sql_hard_codes_the_twins_constants():
    assert f"limit {{{{ var('pn_usual_qb_games', {PN.USUAL_QB_GAMES}) }}}}" in PERSONNEL_SQL
    assert "(p.season = u.season - 1 or (p.season = u.season and p.week < u.week))" in PERSONNEL_SQL   # as of the week
    assert "order by gsis_id, season, week, k desc, recent" in PERSONNEL_SQL                          # majority, then recency
    assert f"q.snap_share >= {PN.TOGETHER_SNAP_SHARE}" in PERSONNEL_SQL and f"a.snap_share >= {PN.TOGETHER_SNAP_SHARE}" in PERSONNEL_SQL
    assert f"coalesce(pa.career_starts, 0) < {PN.ROOKIE_STARTS}" in PERSONNEL_SQL
    assert f"c.career_starts - {PN.PPG_STARTS - 1} and c.career_starts" in PERSONNEL_SQL
    assert f"s.season >= c.season - {PN.PPG_SEASONS_BACK}" in PERSONNEL_SQL
    assert f"where rn <= {PN.OL_STARTERS}" in PERSONNEL_SQL
    assert f"between tw.n_before - {PN.WINDOW_GAMES - 1} and tw.n_before" in WINDOW_SQL
    assert "played_through - is_played::int as n_before" in WINDOW_SQL                                # games BEFORE the week
    out = "('" + "', '".join(PN.OUT_STATUSES) + "')"
    res = "('" + "', '".join(PN.RESERVE_STATUSES) + "')"
    assert f"s.report_status in {out}" in WINDOW_SQL and f"s.roster_status in {res}" in WINDOW_SQL
    assert "ACT vs INA" in STATUS_SQL                                                                  # documented: never read
    assert "r.roster_status in ('RES', 'PUP') then 'missed_injured'" in PLAYER_GAME_SQL


SHIPPED = {"personnel", "qb", "teammates"}


def test_v3_ships_qb_at_qb_and_teammates_at_rb_wr_te():
    from league_lab import projections as P

    assert P.MODEL_VERSION == "v3.0"
    assert P.FEATURES_BY_POSITION["QB"] == [*P.FEATURES, *PN.QB]
    for pos in ("RB", "WR", "TE"):
        assert P.FEATURES_BY_POSITION[pos] == [*P.FEATURES, *PN.TEAMMATES]
    assert not set(PN.OLINE + PN.OWN_INJURY) & set(P.ALL_FEATURES)     # dropped by the harness


def test_groups_validate_and_every_column_is_documented():
    reg = {**PN.GROUPS, **PN.SHIPPED_GROUPS}
    assert set(PN.GROUPS) == {"oline", "own_injury"} and set(PN.SHIPPED_GROUPS) == SHIPPED
    model = next(m for m in YML["models"] if m["name"] == "int_player_week_personnel")
    documented = {c["name"] for c in model["columns"] if c.get("description")}
    types = {c: "double precision" for c in documented} | {"gsis_id": "text", "season": "integer", "week": "integer"}
    for name, spec in reg.items():
        assert set(spec["columns"]) <= documented, f"{name}: undocumented columns"
        if name in SHIPPED:     # v3.0 ships qb (QB) and teammates (RB / WR / TE): the harness now refuses them
            with pytest.raises(E.GroupError, match="already model inputs"):
                E.check_spec(name, spec, types)
            continue
        g = E.check_spec(name, spec, types)
        assert g.table == PN.TABLE
        assert set(g.in_season) <= set(PN.IN_SEASON)
    sub = PN.QB + PN.OLINE + PN.TEAMMATES + PN.OWN_INJURY
    assert reg["personnel"]["columns"] == sub and len(set(sub)) == len(sub)
    assert all(c.startswith("pn_") for c in sub)


# ------------------------------------------------------------------------------ the twins reproduce the table (database)
@pytest.fixture(scope="module")
def conn():
    psycopg = pytest.importorskip("psycopg")
    from league_lab.config import get_settings

    try:
        c = psycopg.connect(get_settings().pipeline_dsn(), connect_timeout=3, autocommit=True)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"no database: {exc}")
    with c:
        if not c.execute("select to_regclass('intermediate.int_player_week_personnel')").fetchone()[0]:
            pytest.skip("int_player_week_personnel not built")
        yield c


def test_sql_matches_the_qb_twin_on_2025(conn):
    games: dict[str, list[tuple[int, int, str]]] = {}
    for gid, s, w, q in conn.execute("""select gsis_id, season, week, starting_qb_id from intermediate.int_pn_player_game
                                        where played and season in (2024, 2025) and starting_qb_id is not null"""):
        games.setdefault(gid, []).append((s, w, q))
    rows = conn.execute("""select gsis_id, week, proj_qb_id, usual_qb_id, pn_qb_changed from intermediate.int_player_week_personnel
                           where season = 2025""").fetchall()
    assert len(rows) > 9000
    bad = [r for r in rows
           if PN.usual_qb(games.get(r[0], []), 2025, r[1]) != r[3] or PN.qb_changed(r[2], r[3]) != r[4]]
    assert not bad, bad[:5]


def test_sql_matches_the_ol_twin_on_2025(conn):
    window: dict[tuple[str, int], list[L]] = {}
    for team, week, gid, share, rep, ros, ros_team in conn.execute(
            """select team, week, gsis_id, snap_share, report_status, roster_status, roster_team
               from intermediate.int_pn_window_player where season = 2025 and pos_group = 'OL'"""):
        window.setdefault((team, week), []).append(L(gid, float(share), rep, ros, ros_team == team))
    rows = conn.execute("""select distinct team, week, pn_ol_starters_out, pn_ol_snap_share_out
                           from intermediate.int_player_week_personnel where season = 2025 and pn_ol_starters_out is not null""").fetchall()
    assert len(rows) > 400
    bad = [r for r in rows if PN.ol_starters_out(window.get((r[0], r[1]), [])) != (r[2], float(r[3]))]
    assert not bad, bad[:5]
