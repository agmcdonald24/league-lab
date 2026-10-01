"""Plan D4: team volume and style — the shrinkage, what a play and a neutral situation are, and the group's
registration. The rules live in SQL (int_team_game_style / int_team_week_style / macro ts_shrink); their Python
twins (league_lab.feature_groups.team_style) are pinned here on fixtures, and the SQL is checked to hard-code the
same constants. No database."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from league_lab import experiments as E
from league_lab import projections as P
from league_lab.feature_groups import team_style as T

ROOT = Path(__file__).resolve().parents[1]
FEATURES_DIR = ROOT / "dbt/models/intermediate/features"
GAME_SQL = (FEATURES_DIR / "int_team_game_style.sql").read_text()
WEEK_SQL = (FEATURES_DIR / "int_team_week_style.sql").read_text()
PLAYER_SQL = (FEATURES_DIR / "int_player_week_team_style.sql").read_text()
MACRO_SQL = (ROOT / "dbt/macros/team_style.sql").read_text()
YML = yaml.safe_load((FEATURES_DIR / "team_style.yml").read_text())


# ------------------------------------------------------------------------------ the shrinkage
def test_shrink_moves_from_last_season_to_this_season():
    prior = 65.0                                                     # last season: 60 and 70 plays a game
    assert T.shrink(None, 0, prior) == 65.0                          # week 1: last season
    assert T.shrink(80.0, 1, prior) == pytest.approx(68.75)          # (1 x 80 + 3 x 65) / 4
    assert T.shrink(67.0, 6, prior) == pytest.approx(597 / 9)        # week 7: (6 x 67 + 195) / 9 = 66.33
    assert T.shrink(68.0, 6, prior) == pytest.approx(67.0)           # last 4 = 68 weighs by the season's 6 games
    # week 10 after 9 games is mostly this season: 3/4 of the weight
    w = T.shrink(1.0, 9, 0.0)
    assert w == pytest.approx(0.75)


def test_shrink_without_a_prior_or_without_a_value():
    assert T.shrink(60.0, 1, None) == 60.0                           # 2016: nothing to shrink toward
    assert T.shrink(None, 0, None) is None                           # 2016 week 1: unknown, not 0
    assert T.shrink(None, 3, 0.5) == 0.5                             # no denominator in the window -> the prior
    assert T.shrink(0.0, 2, 0.5) == pytest.approx(0.3)               # a real 0 is a value, not a missing one


def test_sql_shrinkage_is_the_twin():
    assert f"set prior_games = {T.SHRINK_GAMES}" in WEEK_SQL
    assert "ts_shrink(x ~ '.' ~ m ~ '_' ~ w, x ~ '.games', x ~ '.' ~ m ~ '_prev', prior_games)" in WEEK_SQL   # both windows, the season's n
    assert "({{ n }} * {{ window }} + {{ k }} * {{ prior }}) / ({{ n }} + {{ k }})" in MACRO_SQL
    assert "when {{ prior }} is null then {{ window }}" in MACRO_SQL
    assert "when {{ n }} = 0 or {{ window }} is null then {{ prior }}" in MACRO_SQL
    assert "s.season = k.season and s.week < k.week" in WEEK_SQL      # as of: games before the week only
    assert "where season_type = 'REG'" in WEEK_SQL                    # playoffs never count


def test_dbt_unit_test_expectations_follow_the_twin():
    """The dbt unit test's expected rows (team_style.yml) are what the documented rule gives on its given rows."""
    ut = next(u for u in YML["unit_tests"] if u["model"] == "int_team_week_style")
    games = next(g["rows"] for g in ut["given"] if g["input"] == "ref('int_team_game_style')")
    reg = [g for g in games if g["season_type"] == "REG"]

    def side_rows(team, side, season, before=None):
        key = "team" if side == "off" else "opponent"
        return [g for g in reg if g[key] == team and g["season"] == season and (before is None or g["week"] < before)]

    def plays_pg(rows):
        return sum(g["plays"] for g in rows) / len(rows) if rows else None

    checked = 0
    for row in ut["expect"]["rows"]:
        for side in ("off", "def"):
            cur = sorted(side_rows(row["team"], side, row["season"], row["week"]), key=lambda g: -g["week"])
            prev = side_rows(row["team"], side, row["season"] - 1)
            prior = plays_pg(prev) if prev else plays_pg([g for g in reg if g["season"] == row["season"] - 1])
            want_std = T.shrink(plays_pg(cur), len(cur), prior)
            want_l4 = T.shrink(plays_pg(cur[:4]), len(cur), prior)
            got_std, got_l4 = row[f"{side}_plays_pg_std"], row[f"{side}_plays_pg_l4"]
            assert (got_std is None) == (want_std is None), row
            if want_std is not None:
                assert float(got_std) == pytest.approx(want_std, abs=5e-5), row
                assert float(got_l4) == pytest.approx(want_l4, abs=5e-5), row
            assert row[f"{side}_games"] == len(cur)
            checked += 1
    assert checked == 2 * len(ut["expect"]["rows"]) >= 40


# ------------------------------------------------------------------------------ plays and the neutral situation
def _play(**kw):
    base = dict(is_dropback=False, is_rush_attempt=False, is_kneel=False, down=1, qtr=1, score_differential_pre=0)
    return base | kw


def test_what_a_play_is():
    assert T.is_play(True, False, False)                            # pass attempt / sack
    assert T.is_play(True, True, False)                             # a scramble counts once (one row)
    assert T.is_play(False, True, False)                            # designed run
    assert not T.is_play(False, True, True)                         # kneel
    assert not T.is_play(False, False, False)                       # spike, two-point try, nullified snap, punt


@pytest.mark.parametrize("down,qtr,diff,neutral", [
    (1, 1, 0, True), (2, 3, 7, True), (2, 3, -7, True),             # the edges are in
    (3, 1, 0, False), (4, 2, 0, False),                             # 3rd / 4th down: distance forces the call
    (1, 4, 0, False), (1, 5, 0, False),                             # 4th quarter and overtime: the clock forces it
    (1, 2, 8, False), (2, 1, -8, False),                            # more than a score either way
    (None, 1, 0, False), (1, 1, None, False),                       # unknown is not neutral
])
def test_neutral_situation(down, qtr, diff, neutral):
    assert T.is_neutral(down, qtr, diff) is neutral


def test_neutral_pass_rate_on_a_fixture():
    plays = [
        _play(is_dropback=True),                                    # neutral pass
        _play(is_dropback=True, is_rush_attempt=True, down=2),      # neutral scramble = a pass
        _play(is_rush_attempt=True),                                # neutral run
        _play(is_rush_attempt=True, down=2, score_differential_pre=-7),
        _play(is_dropback=True, down=3),                            # 3rd down: out
        _play(is_dropback=True, qtr=4),                             # 4th quarter: out
        _play(is_dropback=True, score_differential_pre=10),         # up 10: out
        _play(is_rush_attempt=True, is_kneel=True),                 # kneel: not a play
        _play(),                                                    # spike / punt: not a play
    ]
    assert T.neutral_pass_rate(plays) == pytest.approx(2 / 4)
    assert T.neutral_pass_rate([_play(is_dropback=True, down=3)]) is None   # no neutral plays: unknown, not 0


def test_sql_neutral_and_play_definitions_are_the_twin():
    assert ("down in (1, 2) and qtr <= 3 and abs(score_differential_pre) <= 7" in GAME_SQL
            and T.NEUTRAL_DOWNS == (1, 2) and T.NEUTRAL_LAST_QUARTER == 3 and T.NEUTRAL_SCORE == 7)
    assert ("coalesce(is_dropback, false) or (coalesce(is_rush_attempt, false) and not coalesce(is_kneel, false)) as is_play"
            in GAME_SQL)
    assert "count(*) filter (where is_play and is_neutral and is_dropback)" in GAME_SQL
    assert f"set max_gap = {T.MAX_CLOCK_GAP}" in GAME_SQL
    # pace counts only neutral-score snaps of quarters 1-3 (all downs)
    assert "where gap between 0 and {{ max_gap }} and qtr <= 3 and abs(score_differential_pre) <= 7" in GAME_SQL


# ------------------------------------------------------------------------------ the group
def _sql_list(sql: str, name: str) -> list[str]:
    m = re.search(r"set " + name + r" = \[(.*?)\]", sql, re.S)
    return re.findall(r"'(\w+)'", m.group(1))


def test_metrics_match_the_sql():
    assert _sql_list(PLAYER_SQL, "metrics") == T.METRICS
    week_metrics = re.findall(r"^\s+'(\w+)':\s+'", WEEK_SQL, re.M)
    assert week_metrics == T.METRICS


def test_groups_are_well_formed():
    groups = T.GROUPS
    assert set(groups) == {"team_style", "team_style_volume", "team_style_pass_rate", "team_style_efficiency",
                           "team_style_defense_faced", "team_style_lean"}
    assert set(T.LEAN) <= set(T.ALL) and len(T.LEAN) == 3
    subs = T.VOLUME + T.PASS_RATE + T.EFFICIENCY + T.DEFENSE_FACED
    assert len(subs) == len(set(subs))                                      # the four sub-groups do not overlap
    assert set(subs) | {"ts_off_games", "ts_def_games"} == set(T.ALL)      # and cover the full group
    assert len(T.ALL) == 2 + 2 * 2 * len(T.METRICS) + 2 == 52
    for name, spec in groups.items():
        assert all(c.startswith("ts_") for c in spec["columns"]), name
        assert not set(spec["columns"]) & set(P.FEATURES), name
        assert not spec.get("in_season"), name                               # week 1 = last season, by design
        typed = {c: "numeric" for c in spec["columns"]} | {"gsis_id": "text", "season": "integer", "week": "integer"}
        s = E.check_spec(name, spec, typed)
        assert s.table == "intermediate.int_player_week_team_style" and s.positions == P.POSITIONS


def test_every_group_column_is_documented():
    model = next(m for m in YML["models"] if m["name"] == "int_player_week_team_style")
    documented = {c["name"] for c in model["columns"] if c.get("description")}
    missing = [c for c in T.ALL if c not in documented]
    assert not missing, missing
