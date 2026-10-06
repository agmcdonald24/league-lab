"""IM-5 (Wave I-M): DFS — the sites' scoring rules, the two salary-file parsers, matching, the value line, the exact
lineup optimiser (against brute force on small slates), the upload CSV. No database: ``league_lab.dfs`` is pure."""

from __future__ import annotations

import itertools
import random

import numpy as np
import pandas as pd
import pytest

from league_lab import dfs as D
from league_lab import kdef
from league_lab.scoring import compute_points, price_projected

DK, FD = D.SCORING["dk"], D.SCORING["fd"]


# ------------------------------------------------------------------------------------------------ scoring: one test a rule
@pytest.mark.parametrize("site,stats,points", [
    ("dk", {"passing_yards": 25}, 1.0),            # 0.04 per passing yard
    ("dk", {"passing_tds": 1}, 4.0),
    ("dk", {"passing_interceptions": 1}, -1.0),
    ("dk", {"rushing_yards": 10}, 1.0),            # 0.1 per rushing yard
    ("dk", {"rushing_tds": 1}, 6.0),
    ("dk", {"receptions": 1}, 1.0),                # full PPR
    ("dk", {"receiving_yards": 10}, 1.0),
    ("dk", {"receiving_tds": 1}, 6.0),
    ("dk", {"fumbles_lost_total": 1}, -1.0),
    ("dk", {"passing_2pt_conversions": 1}, 2.0),
    ("dk", {"rushing_2pt_conversions": 1}, 2.0),
    ("dk", {"receiving_2pt_conversions": 1}, 2.0),
    ("dk", {"special_teams_tds": 1}, 6.0),         # a punt / kick / FG return TD
    ("dk", {"fumble_recovery_tds": 1}, 6.0),       # an offensive fumble recovery TD
    ("fd", {"passing_yards": 25}, 1.0),
    ("fd", {"passing_tds": 1}, 4.0),
    ("fd", {"passing_interceptions": 1}, -1.0),
    ("fd", {"rushing_yards": 10}, 1.0),
    ("fd", {"rushing_tds": 1}, 6.0),
    ("fd", {"receptions": 1}, 0.5),                # half PPR
    ("fd", {"receiving_yards": 10}, 1.0),
    ("fd", {"receiving_tds": 1}, 6.0),
    ("fd", {"fumbles_lost_total": 1}, -2.0),
    ("fd", {"passing_2pt_conversions": 1}, 2.0),
    ("fd", {"rushing_2pt_conversions": 1}, 2.0),
    ("fd", {"receiving_2pt_conversions": 1}, 2.0),
    ("fd", {"special_teams_tds": 1}, 6.0),
    ("fd", {"fumble_recovery_tds": 1}, 6.0),
])
def test_player_rule(site, stats, points):
    assert compute_points(stats, D.SCORING[site]) == pytest.approx(points)


@pytest.mark.parametrize("stat,value,dk_bonus", [
    ("passing_yards", 299, 0.0), ("passing_yards", 300, 3.0), ("passing_yards", 450, 3.0),
    ("rushing_yards", 99, 0.0), ("rushing_yards", 100, 3.0), ("rushing_yards", 230, 3.0),
    ("receiving_yards", 99, 0.0), ("receiving_yards", 100, 3.0), ("receiving_yards", 210, 3.0),
])
def test_dk_yardage_bonus_paid_once(stat, value, dk_bonus):
    """DraftKings: +3 at 300 passing / 100 rushing / 100 receiving yards, once (a 450-yard game is +3, not +6);
    FanDuel has no yardage bonus."""
    rate = 0.04 if stat == "passing_yards" else 0.1
    assert compute_points({stat: value}, DK) == pytest.approx(round(value * rate + dk_bonus, 2))
    assert compute_points({stat: value}, FD) == pytest.approx(round(value * rate, 2))


def test_dk_bonus_priced_at_its_odds_on_a_projected_line():
    """A projected 100-yard back: the bonus is 3 x P(100+ yards), between 0 and 3, rising with the projection — never
    the all-or-nothing step at 100.0 (D.BONUS_AT_ODDS)."""
    lines = pd.DataFrame({"rushing_yards": [60.0, 99.0, 101.0, 140.0], "position": ["RB"] * 4})
    flat = price_projected(lines, DK, ev=False)
    odds = price_projected(lines, DK, ev=True)
    base = lines["rushing_yards"].to_numpy() * 0.1
    bonus = odds - base
    assert all(0 < b < 3 for b in bonus)
    assert list(bonus) == sorted(bonus)
    assert abs(bonus[2] - bonus[1]) < 0.5                      # no 3-point step between 99 and 101
    assert flat[2] - flat[1] == pytest.approx(3.2, abs=0.01)   # the flat engine's step (what we avoid)


def _def_line(**kw) -> pd.DataFrame:
    base = {f"proj_{c}": 0.0 for c in kdef.DEF_LINE}
    base.update({f"proj_{k}": v for k, v in kw.items()})
    return pd.DataFrame([base])


@pytest.mark.parametrize("site", ["dk", "fd"])
@pytest.mark.parametrize("stat,points", [
    ("sacks", 1.0), ("interceptions", 2.0), ("fumble_recoveries", 2.0), ("def_tds", 6.0), ("st_tds", 6.0),
    ("safeties", 2.0), ("blocked_kicks", 2.0),
])
def test_defense_rule(site, stat, points):
    assert kdef.price(_def_line(**{stat: 1.0}), "DEF", D.SCORING[site], "proj_")[0] == pytest.approx(points)


@pytest.mark.parametrize("site", ["dk", "fd"])
@pytest.mark.parametrize("bucket,points", [("pa_0", 10.0), ("pa_1_6", 7.0), ("pa_7_13", 4.0), ("pa_14_20", 1.0),
                                           ("pa_21_27", 0.0), ("pa_28_34", -1.0), ("pa_35p", -4.0)])
def test_defense_points_allowed(site, bucket, points):
    assert kdef.price(_def_line(**{bucket: 1.0}), "DEF", D.SCORING[site], "proj_")[0] == pytest.approx(points)


@pytest.mark.parametrize("col,points", [("fg_made_0_19", 3.0), ("fg_made_20_29", 3.0), ("fg_made_30_39", 3.0),
                                        ("fg_made_40_49", 4.0), ("fg_made_50p", 5.0), ("pat_made", 1.0),
                                        ("fg_missed", 0.0), ("pat_missed", 0.0)])
def test_dk_kicker_rule(col, points):
    """DraftKings showdown's kicker: 3 to 39 yards, 4 for 40-49, 5 for 50+, 1 per extra point, no miss penalty."""
    line = pd.DataFrame([{f"proj_{c}": 0.0 for c in kdef.K_LINE} | {f"proj_{col}": 1.0}])
    assert kdef.price(line, "K", DK, "proj_")[0] == pytest.approx(points)


def test_contests_as_data():
    dk, sd, fd = D.CONTESTS["dk_classic"], D.CONTESTS["dk_showdown"], D.CONTESTS["fd_full"]
    assert (dk.cap, dk.size, dk.min_games, dk.max_per_team) == (50_000, 9, 2, None)
    assert [g.label for g in dk.groups for _ in range(g.count)] == list(dk.upload_header)
    assert (sd.cap, sd.size, sd.groups[0].multiplier) == (50_000, 6, 1.5)
    assert (fd.cap, fd.size, fd.max_per_team) == (60_000, 9, 4)
    assert [g.label for g in fd.groups for _ in range(g.count)] == list(fd.upload_header)


# ------------------------------------------------------------------------------------------------ parsers
DK_HEAD = "Position,Name + ID,Name,ID,Roster Position,Salary,Game Info,TeamAbbrev,AvgPointsPerGame"
DK_ROWS = [
    'QB,Josh Allen (40001),Josh Allen,40001,QB,7900,BUF@MIA 10/11/2026 01:00PM ET,BUF,24.1',
    'RB,"De\'Von Achane (40002)","De\'Von Achane",40002,RB/FLEX,"$7,200",BUF@MIA 10/11/2026 01:00PM ET,MIA,19.5',
    'WR,D.J. Moore (40003),D.J. Moore,40003,WR/FLEX,5100,CHI@JAX 10/11/2026 01:00PM ET,CHI,12.2',
    'TE,Brevyn Spann-Ford (40004),Brevyn Spann-Ford,40004,TE/FLEX,2500,DAL@NYG 10/11/2026 04:25PM ET,DAL,1.0',
    'DST,Jaguars (40005),Jaguars,40005,DST,3100,CHI@JAX 10/11/2026 01:00PM ET,JAX,7.0',
]


def test_dk_classic_parses_with_bom_quotes_and_dollar_salaries():
    s = D.parse("﻿" + "\n".join([DK_HEAD, *DK_ROWS]))
    assert (s.site, s.contest) == ("dk", "dk_classic")
    assert [p.salary for p in s.players] == [7900, 7200, 5100, 2500, 3100]
    achane = s.players[1]
    assert (achane.name, achane.team, achane.opponent, achane.game) == ("De'Von Achane", "MIA", "BUF", "BUF@MIA")
    assert achane.roster_positions == ("RB", "FLEX")
    assert s.players[4].position == "DEF" and s.players[4].team == "JAX"
    assert s.games == ["BUF@MIA", "CHI@JAX", "DAL@NYG"]


def test_dk_parses_any_column_order_and_extra_columns():
    cols = DK_HEAD.split(",")
    order = [7, 5, 0, 3, 2, 4, 1, 6, 8]
    head = ",".join([cols[i] for i in order] + ["Some New Column"])
    rows = [",".join([next(csv_cells(r))[i] for i in order] + ["x"]) for r in DK_ROWS[:3]]
    s = D.parse("\n".join([head, *rows]))
    assert [p.name for p in s.players] == ["Josh Allen", "De'Von Achane", "D.J. Moore"]


def csv_cells(line: str):
    import csv
    yield [c if "," not in c else f'"{c}"' for c in next(csv.reader([line]))]


def test_dk_entry_template_with_a_column_offset():
    """DraftKings' entry template puts the player list to the right of blank / instruction columns, a few rows down."""
    lines = [",,,,", "Entry ID,Contest Name,,Instructions", ",,,", ",,," + DK_HEAD] + [",,," + r for r in DK_ROWS]
    s = D.parse("\n".join(lines))
    assert s.contest == "dk_classic" and len(s.players) == 5


SD_HEAD = DK_HEAD
SD_ROWS = [
    "QB,Josh Allen (50001),Josh Allen,50001,CPT,16500,BUF@MIA 10/12/2026 08:15PM ET,BUF,24.1",
    "QB,Josh Allen (50002),Josh Allen,50002,FLEX,11000,BUF@MIA 10/12/2026 08:15PM ET,BUF,24.1",
    "WR,Jaylen Waddle (50003),Jaylen Waddle,50003,CPT,13500,BUF@MIA 10/12/2026 08:15PM ET,MIA,14.0",
    "WR,Jaylen Waddle (50004),Jaylen Waddle,50004,FLEX,9000,BUF@MIA 10/12/2026 08:15PM ET,MIA,14.0",
    "K,Jason Sanders (50005),Jason Sanders,50005,FLEX,4000,BUF@MIA 10/12/2026 08:15PM ET,MIA,8.0",
]


def test_dk_showdown_pairs_captain_and_flex_rows():
    s = D.parse("\n".join([SD_HEAD, *SD_ROWS]))
    assert s.contest == "dk_showdown"
    allen = next(p for p in s.players if p.name == "Josh Allen")
    assert (allen.key, allen.salary, allen.cpt_id, allen.cpt_salary) == ("50002", 11000, "50001", 16500)
    sanders = next(p for p in s.players if p.name == "Jason Sanders")
    assert sanders.cpt_id is None and any("no captain row" in n for n in s.notes)


FD_HEAD = ('"Id","Position","First Name","Nickname","Last Name","FPPG","Played","Salary","Game","Team","Opponent",'
           '"Injury Indicator","Injury Details","Tier","",""')
FD_ROWS = [
    '"118000-1001","QB","Josh","Josh Allen","Allen","24.1","4","9200","BUF@MIA","BUF","MIA","","","","",""',
    '"118000-1002","RB","De\'Von","De\'Von Achane","Achane","19.5","4","8400","BUF@MIA","MIA","BUF","Q","Hamstring","","",""',
    '"118000-1003","D","Jacksonville","Jacksonville Jaguars","Jaguars","7.0","4","3800","CHI@JAC","JAC","CHI","","","","",""',
    '"118000-1004","WR","Puka","Puka Nacua","Nacua","17.0","4","8000","LAR@SF","LAR","SF","","","","",""',
]


def test_fd_full_roster_parses_teams_and_injuries():
    s = D.parse("\n".join([FD_HEAD, *FD_ROWS]))
    assert (s.site, s.contest) == ("fd", "fd_full")
    by = {p.name: p for p in s.players}
    assert by["De'Von Achane"].injury == "Q"
    assert (by["Jacksonville Jaguars"].position, by["Jacksonville Jaguars"].team) == ("DEF", "JAX")   # JAC -> JAX
    assert (by["Puka Nacua"].team, by["Puka Nacua"].opponent) == ("LA", "SF")                         # LAR -> LA


def test_fd_single_game_is_refused_in_words():
    row = '"118000-1009","K","Jason","Jason Sanders","Sanders","8","4","4000","BUF@MIA","MIA","BUF","","","","",""'
    with pytest.raises(D.SlateError, match="single-game"):
        D.parse("\n".join([FD_HEAD, *FD_ROWS, row]))


@pytest.mark.parametrize("text,words", [
    ("Player,Team,Cost\nJosh Allen,BUF,7900", "does not look like a DraftKings or FanDuel salary file: expected a column named Salary"),
    ("Name,Salary\nJosh Allen,7900", "does not look like a DraftKings or FanDuel salary file"),
    ("", "does not look like"),
    ("Position,Name + ID,Name,ID,Roster Position,Salary,TeamAbbrev\n", "a header and no players"),
    ("Position,Name + ID,ID,Roster Position,Salary,TeamAbbrev\nQB,X (1),1,QB,5000,BUF", "column is missing: Name"),
])
def test_wrong_files_are_refused_in_words(text, words):
    with pytest.raises(D.SlateError, match=words.replace("(", r"\(").replace(")", r"\)")):
        D.parse(text)


def test_three_megabytes_is_refused():
    big = DK_HEAD + "\n" + (DK_ROWS[0] + "\n") * 40_000
    assert len(big.encode()) > 3_000_000
    with pytest.raises(D.SlateError) as e:
        D.parse(big)
    assert e.value.code == "too_large" and "under 1 MB" in str(e.value)
    with pytest.raises(D.SlateError):
        D.parse(big.encode())


def test_too_many_rows_is_refused():
    rows = [f"WR,P{i} (9{i:05d}),P{i},9{i:05d},WR/FLEX,3000,BUF@MIA,BUF,1" for i in range(D.MAX_ROWS + 1)]
    with pytest.raises(D.SlateError, match="at most 2,000"):
        D.parse("\n".join([DK_HEAD, *rows]))


def test_formula_cells_are_text_and_a_bad_id_skips_the_row():
    rows = ['WR,"=cmd|\' /C calc\'!A0 (40010)","=cmd|\' /C calc\'!A0",40010,WR/FLEX,3000,BUF@MIA,BUF,1',
            'WR,"Evil (=1+1)","Evil","=1+1",WR/FLEX,3000,BUF@MIA,BUF,1', DK_ROWS[0]]
    s = D.parse("\n".join([DK_HEAD, *rows]))
    assert s.players[0].name.startswith("=cmd")             # kept as text, never evaluated
    assert [k["reason"] for k in s.skipped] == ["its ID is not a DraftKings player id"]


def test_upload_csv_neutralises_formulas():
    lu = {"slots": [{"upload_id": v} for v in ("=cmd|' /C calc'!A0", "+1", "-2", "@SUM(A1)", "\tx", "123")]}
    out = D.upload_csv("dk_showdown", [lu])
    first, row = out.splitlines()[:2]
    assert first == "CPT,FLEX,FLEX,FLEX,FLEX,FLEX"
    cells = next(__import__("csv").reader([row]))
    assert cells == ["'=cmd|' /C calc'!A0", "'+1", "'-2", "'@SUM(A1)", "'\tx", "123"]


# ------------------------------------------------------------------------------------------------ matching
POOL = pd.DataFrame([
    ("00-1", "D.J. Moore", "WR", "CHI"), ("00-2", "Marvin Harrison Jr.", "WR", "ARI"),
    ("00-3", "Amon-Ra St. Brown", "WR", "DET"), ("00-4", "Ja'Marr Chase", "WR", "CIN"),
    ("00-5", "Gabriel Davis", "WR", "BUF"), ("00-6", "Mike Williams", "WR", "PIT"),
    ("00-7", "Mike Williams", "WR", "PIT"), ("00-8", "Kenneth Walker III", "RB", "SEA"),
    ("00-9", "Puka Nacua", "WR", "LA"), ("00-10", "Travis Etienne Jr.", "RB", "JAX"),
    ("00-11", "Tyreek Hill", "WR", "MIA"), ("00-12", "Taysom Hill", "QB", "NO"),
    ("DEF:JAX", "Jacksonville Jaguars", "DEF", "JAX"), ("00-13", "Cam Ward", "QB", "TEN"),
    ("00-14", "Brian Thomas Jr.", "WR", "JAX"), ("00-15", "Chig Okonkwo", "TE", "WAS"),
], columns=["key", "player_name", "position", "team"])
DIRECTORY = pd.DataFrame([("00-99", "Deep Backup", "RB", "BUF")], columns=["key", "player_name", "position", "team"])


def _p(name, pos, team, key=None):
    return D.SlatePlayer(key=key or name, site_id=key or name, name=name, position=pos, site_position=pos,
                         roster_positions=(pos,), salary=3000, team=D.team_code(team), site_team=team)


@pytest.mark.parametrize("name,pos,team,want", [
    ("DJ Moore", "WR", "CHI", "00-1"),                 # D.J. / DJ
    ("D. J. Moore", "WR", "CHI", "00-1"),
    ("Marvin Harrison", "WR", "ARI", "00-2"),          # the suffix
    ("Amon Ra St Brown", "WR", "DET", "00-3"),         # hyphen and period
    ("JaMarr Chase", "WR", "CIN", "00-4"),             # apostrophe
    ("Gabe Davis", "WR", "BUF", "00-5"),               # a nickname: first initial + last name, unique on BUF WR
    ("Kenneth Walker", "RB", "SEA", "00-8"),           # III
    ("Puka Nacua", "WR", "LAR", "00-9"),               # the team code LAR -> LA
    ("Travis Etienne Jr.", "RB", "JAC", "00-10"),      # JAC -> JAX
    ("Brian Thomas", "WR", "JAX", "00-14"),
    ("Chig Okonkwo", "TE", "WSH", "00-15"),            # WSH -> WAS
    ("Câm Wärd", "QB", "TEN", "00-13"),                # accents
    ("Jaguars", "DEF", "JAC", "DEF:JAX"),              # a defense by its team
])
def test_awkward_real_names_match(name, pos, team, want):
    got, un, _ = D.match([_p(name, pos, team)], POOL)
    assert got == {name: want}, un


def test_ambiguous_and_missing_are_listed_never_guessed():
    players = [_p("Mike Williams", "WR", "PIT"), _p("Tyreek Hill", "WR", "KC"), _p("Taysom Hill", "TE", "NO"),
               _p("Nobody Atall", "WR", "BUF"), _p("Deep Backup", "RB", "BUF"), _p("Some One", "WR", "XXX"),
               _p("Bills", "DEF", "BUF")]
    got, un, _ = D.match(players, POOL, DIRECTORY)
    assert got == {}
    why = {u["name"]: u["reason"] for u in un}
    assert why["Mike Williams"].startswith("ambiguous: 2 of our WRs on PIT match")
    assert "we have that name as WR on MIA" in why["Tyreek Hill"]          # traded / the file disagrees: not guessed
    assert "we have that name as QB on NO" in why["Taysom Hill"]
    assert why["Nobody Atall"] == "no WR of that name on BUF in our players"
    assert why["Deep Backup"] == "no projection for him this week (unknown, not 0)"
    assert "not an NFL team code" in why["Some One"]
    assert why["Bills"] == "no projection for the BUF defense this week"


def test_initial_step_needs_a_unique_candidate():
    pool = pd.concat([POOL, pd.DataFrame([("00-50", "Gary Davis", "WR", "BUF")], columns=POOL.columns)])
    got, un, _ = D.match([_p("Gabe Davis", "WR", "BUF")], pool)
    assert got == {} and un[0]["reason"].startswith("ambiguous: 2")


# ------------------------------------------------------------------------------------------------ the value line
def _priced(n=10, pos="WR", slope=2.0, icpt=1.0, bump=None):
    sal = np.linspace(3000, 9000, n).round(-2)
    proj = icpt + slope * sal / 1000
    if bump:
        for i, v in bump.items():
            proj[i] += v
    return pd.DataFrame({"position": pos, "salary": sal.astype(int), "proj": proj, "p90": proj * 1.6,
                         "out": False})


def test_value_line_and_calls():
    df = _priced(bump={4: 5.0, 7: -5.0})
    out, fits = D.value(df, "dk_classic")
    assert fits["WR"]["n"] == 10
    assert out.loc[4, "value_call"] == "undervalued" and out.loc[4, "value_rank"] == 1
    assert out.loc[7, "value_call"] == "overpriced" and out.loc[7, "value_rank"] == 10
    assert out.loc[0, "pts_per_k"] == pytest.approx(round(out.loc[0, "proj"] / 3.0, 2))
    assert out.loc[0, "ceil_per_k"] == pytest.approx(round(out.loc[0, "p90"] / 3.0, 2))
    assert out["value_call"].isna().sum() == 8


def test_no_line_under_eight_priced_players():
    out, fits = D.value(_priced(n=7), "dk_classic")
    assert fits["WR"] is None and out["value_gap"].isna().all() and out["value_call"].isna().all()


def test_out_players_and_tiny_projections_do_not_set_the_line():
    df = _priced(n=10)
    extra = pd.DataFrame({"position": "WR", "salary": [3000, 3000, 8000], "proj": [0.2, 0.0, 0.0], "p90": [1, 0, 0],
                          "out": [False, False, True]})
    out, fits = D.value(pd.concat([df, extra], ignore_index=True), "dk_classic")
    assert fits["WR"]["n"] == 10 and fits["WR"]["rmse"] == pytest.approx(0, abs=1e-6)
    assert out.loc[12, "value_call"] is None                  # out: never on a list
    assert out.loc[10, "value_call"] is None                  # at the position's minimum salary: never "overpriced"


# ------------------------------------------------------------------------------------------------ the optimiser
def _slate(seed: int, contest: str):
    rng = random.Random(seed)
    if contest == "dk_showdown":
        teams = ["BUF", "MIA"]
        pos = ["QB", "QB", "RB", "WR", "WR", "TE", "K", "DEF"]
        ps = []
        for i, p in enumerate(pos):
            sal = rng.randrange(2000, 12000, 200)
            ps.append({"key": f"s{i}", "position": p, "team": teams[i % 2], "game": "BUF@MIA", "salary": sal,
                       "cpt_salary": int(sal * 1.5), "proj": round(rng.uniform(2, 25), 2), "out": False})
        for p in ps:
            p["p90"], p["p10"] = round(p["proj"] * 1.7, 2), round(p["proj"] * 0.4, 2)
        return ps
    spec = {"QB": 2, "RB": 4, "WR": 5, "TE": 2, "DEF": 2}
    games = [("BUF", "MIA"), ("CHI", "JAX"), ("DAL", "NYG")]
    ps = []
    for pos, k in spec.items():
        for j in range(k):
            g = games[rng.randrange(3)]
            # FanDuel: half the players on one team, so its four-per-team rule binds
            team = ("BUF" if rng.random() < 0.5 else rng.choice(["MIA", "CHI", "JAX"])) if contest == "fd_full" \
                else g[rng.randrange(2)]
            g = next((x for x in games if team in x), g)
            proj = round(rng.uniform(3, 26), 2)
            ps.append({"key": f"{pos}{j}", "position": pos, "team": team, "game": f"{g[0]}@{g[1]}",
                       "salary": rng.randrange(3000, 8000, 100) if contest == "dk_classic" else rng.randrange(4500, 8600, 100),
                       "proj": proj, "p90": round(proj * rng.uniform(1.3, 2.0), 2), "p10": round(proj * 0.4, 2),
                       "out": False})
    return ps


def _legal(c, combo, players):
    """combo: [(player index, group index)]"""
    if len({i for i, _ in combo}) != len(combo):
        return False
    sal = sum(players[i]["cpt_salary"] if c.groups[g].multiplier != 1 else players[i]["salary"] for i, g in combo)
    if sal > c.cap:
        return False
    teams = [players[i]["team"] for i, _ in combo]
    if c.max_per_team and max(teams.count(t) for t in set(teams)) > c.max_per_team:
        return False
    if c.min_games and len({players[i]["game"] for i, _ in combo}) < c.min_games:
        return False
    return not (c.min_teams and len(set(teams)) < c.min_teams)


def _brute(players, contest, key="proj"):
    c = D.CONTESTS[contest]
    best = -1e9
    slots = [gi for gi, g in enumerate(c.groups) for _ in range(g.count)]
    elig = [[i for i, p in enumerate(players) if p["position"] in c.groups[gi].elig] for gi in slots]
    seen = set()
    for pick in itertools.product(*elig):
        if len(set(pick)) != len(pick):
            continue
        combo = tuple(sorted(zip(pick, slots, strict=True)))
        if combo in seen:
            continue
        seen.add(combo)
        if not _legal(c, combo, players):
            continue
        v = sum(players[i][key] * c.groups[g].multiplier for i, g in combo)
        best = max(best, v)
    return best


@pytest.mark.parametrize("contest", ["dk_classic", "fd_full", "dk_showdown"])
@pytest.mark.parametrize("seed", [1, 2, 4, 5])
@pytest.mark.parametrize("mode", ["cash", "tournament"])
def test_optimiser_matches_brute_force(contest, seed, mode):
    ps = _slate(seed, contest)
    res = D.solve_lineups(ps, contest, mode=mode)
    want = _brute(ps, contest, "p90" if mode == "tournament" else "proj")
    assert want > 0, "the test slate must have a legal lineup"
    lu = res.lineups[0]
    key = "p90" if mode == "tournament" else "proj"
    by = {p["key"]: p for p in ps}
    got = sum(by[s["key"]][key] * s["multiplier"] for s in lu["slots"])
    assert got == pytest.approx(want, abs=1e-6)
    assert lu["proven"] is True and lu["salary"] <= D.CONTESTS[contest].cap
    assert len(lu["slots"]) == D.CONTESTS[contest].size


def test_fd_four_per_team_binds():
    ps = _slate(7, "fd_full")
    res = D.solve_lineups(ps, "fd_full")
    teams = [next(p["team"] for p in ps if p["key"] == s["key"]) for s in res.lineups[0]["slots"]]
    assert max(teams.count(t) for t in set(teams)) <= 4


def test_dk_needs_two_games():
    ps = _slate(4, "dk_classic")
    for p in ps:
        p["game"] = "BUF@MIA"
    res = D.solve_lineups(ps, "dk_classic")
    assert res.lineups == [] and "needs players from 2" in res.notes[0]


def test_next_lineups_differ_and_do_not_improve():
    ps = _slate(5, "dk_classic")
    res = D.solve_lineups(ps, "dk_classic", n=5)
    sets = [frozenset(s["key"] for s in lu["slots"]) for lu in res.lineups]
    assert len(sets) == 5 and len(set(sets)) == 5
    totals = [lu["proj"] for lu in res.lineups]
    assert totals == sorted(totals, reverse=True)
    assert len(res.solve_ms) == 5


def test_locks_and_excludes():
    ps = _slate(6, "dk_classic")
    best = D.solve_lineups(ps, "dk_classic").lineups[0]
    first = next(s["key"] for s in best["slots"] if s["slot"] == "WR")
    worst_qb = min((p for p in ps if p["position"] == "QB"), key=lambda p: p["proj"])["key"]
    res = D.solve_lineups(ps, "dk_classic", locks=[worst_qb], excludes=[first])
    keys = {s["key"] for s in res.lineups[0]["slots"]}
    assert worst_qb in keys and first not in keys


def test_out_players_are_left_out_unless_locked():
    ps = _slate(8, "dk_classic")
    best = D.solve_lineups(ps, "dk_classic").lineups[0]
    star = max(best["slots"], key=lambda s: s["proj"])["key"]
    for p in ps:
        if p["key"] == star:
            p["out"] = True
    assert star not in {s["key"] for s in D.solve_lineups(ps, "dk_classic").lineups[0]["slots"]}
    assert star in {s["key"] for s in D.solve_lineups(ps, "dk_classic", locks=[star]).lineups[0]["slots"]}


def test_showdown_captain_counts_one_and_a_half():
    ps = _slate(9, "dk_showdown")
    lu = D.solve_lineups(ps, "dk_showdown").lineups[0]
    cpt = lu["slots"][0]
    assert cpt["slot"] == "CPT" and cpt["multiplier"] == 1.5
    p = next(x for x in ps if x["key"] == cpt["key"])
    assert cpt["proj"] == pytest.approx(round(p["proj"] * 1.5, 2)) and cpt["salary"] == p["cpt_salary"]
    assert len({next(x["team"] for x in ps if x["key"] == s["key"]) for s in lu["slots"]}) == 2


def test_impossible_cap_says_so():
    ps = _slate(10, "dk_classic")
    for p in ps:
        p["salary"] = 9000
    res = D.solve_lineups(ps, "dk_classic")
    assert res.lineups == [] and res.notes == ["No lineup fits the cap and the rules with these locks and excludes."]


def test_lineup_range_is_wider_than_none_and_ordered():
    ps = _slate(11, "dk_classic")
    lu = D.solve_lineups(ps, "dk_classic").lineups[0]
    assert lu["low"] < lu["proj"] < lu["high"]


# ------------------------------------------------------------------------------------------------ the week
def test_detect_week_from_the_games():
    sched = pd.DataFrame({"week": [4, 4, 5, 5], "home_team": ["MIA", "JAX", "BUF", "LA"],
                          "away_team": ["BUF", "CHI", "MIA", "SF"]})
    assert D.detect_week(["BUF@MIA", "CHI@JAC"], sched) == 4
    assert D.detect_week(["MIA@BUF", "SF@LAR"], sched) == 5
    assert D.detect_week(["XXX@YYY"], sched) is None


def test_optimiser_agrees_when_no_lineup_is_legal():
    ps = _slate(3, "fd_full")                     # this slate has no legal FanDuel lineup (four-per-team, the cap)
    assert _brute(ps, "fd_full") < 0
    res = D.solve_lineups(ps, "fd_full")
    assert res.lineups == [] and "No lineup fits" in res.notes[0]
