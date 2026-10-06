"""IM-5: SYNTHETIC DraftKings / FanDuel salary files from the database's week-5 players (no salary was fetched).

The files have the columns the two sites' exports are documented to have (docs/DFS.md § "The files"); the players,
teams and games are the database's week 5; the salaries are invented: a straight line in our own projection plus noise
(so the value screen has something to find) rounded to $100 and clipped to each site's usual range. A few rows are
made awkward on purpose (a player on the wrong team, a name we do not have, nickname spellings). The first line of
every file says it is synthetic. Run from api/ (read-only on the database):

    PYTHONPATH=. uv run python tests/fixtures/dfs/make_synthetic.py
"""

from __future__ import annotations

import csv
import random
from pathlib import Path

import pandas as pd

from league_lab_api.db import query  # it puts the repository's src/ on the path: league_lab is imported after it

A = D = None  # league_lab.anyleague / league_lab.dfs, imported in main()

OUT = Path(__file__).resolve().parent
SEASON, WEEK = 2026, 5
HEAD = "# SYNTHETIC salary file for tests (IM-5, Wave I-M): week-5 players from the database, invented salaries — not a {site} export"
# per site and position: (salary at 0 points, $ per point, noise sd, min, max)
SAL = {
    "dk": {"QB": (4300, 190, 450, 4800, 8600), "RB": (3700, 250, 500, 4000, 9500), "WR": (2900, 280, 500, 3000, 9800),
           "TE": (2400, 260, 400, 2500, 8000), "DEF": (2000, 180, 300, 2000, 4500), "K": (3800, 120, 300, 3600, 5600)},
    "fd": {"QB": (5800, 160, 450, 6000, 9600), "RB": (4600, 240, 500, 4500, 10000), "WR": (4300, 270, 500, 4500, 9800),
           "TE": (4000, 240, 400, 4000, 8500), "DEF": (3000, 160, 300, 3000, 5200)},
}
DK_TEAM = {"LA": "LAR", "WAS": "WAS", "JAX": "JAX"}
FD_TEAM = {"LA": "LAR", "JAX": "JAC"}
DK_DST = {"ARI": "Cardinals", "ATL": "Falcons", "BAL": "Ravens", "BUF": "Bills", "CAR": "Panthers", "CHI": "Bears",
          "CIN": "Bengals", "CLE": "Browns", "DAL": "Cowboys", "DEN": "Broncos", "DET": "Lions", "GB": "Packers",
          "HOU": "Texans", "IND": "Colts", "JAX": "Jaguars", "KC": "Chiefs", "LA": "Rams", "LAC": "Chargers",
          "LV": "Raiders", "MIA": "Dolphins", "MIN": "Vikings", "NE": "Patriots", "NO": "Saints", "NYG": "Giants",
          "NYJ": "Jets", "PHI": "Eagles", "PIT": "Steelers", "SEA": "Seahawks", "SF": "49ers", "TB": "Buccaneers",
          "TEN": "Titans", "WAS": "Commanders"}


def _salary(rng: random.Random, site: str, pos: str, proj: float) -> int:
    a, b, sd, lo, hi = SAL[site][pos]
    return int(min(hi, max(lo, round((a + b * proj + rng.gauss(0, sd)) / 100) * 100)))


def _games() -> pd.DataFrame:
    g = query("select home_team, away_team, kickoff_at from analytics.dim_game where season = %s and week = %s "
              "and season_type = 'REG' order by kickoff_at, home_team", (SEASON, WEEK))
    g["kickoff_et"] = pd.to_datetime(g["kickoff_at"], utc=True).dt.tz_convert("America/New_York")
    return g


def _players() -> pd.DataFrame:
    b = A.load_board(query, SEASON, WEEK)
    df = D.price_site(b, "dk")
    return df[df["proj"].notna()].copy()


def _game_of(games: pd.DataFrame, team: str):
    m = games[(games["home_team"] == team) | (games["away_team"] == team)]
    return None if m.empty else m.iloc[0]


def dk_classic(players: pd.DataFrame, games: pd.DataFrame, rng: random.Random) -> list[list[str]]:
    rows = []
    pid = 41_000_000
    sel = players[players["position"] != "K"].sort_values(["position", "proj"], ascending=[True, False])
    for r in sel.itertuples():
        g = _game_of(games, r.team)
        if g is None:
            continue
        pid += 1
        team = DK_TEAM.get(r.team, r.team)
        name = DK_DST[r.team] if r.position == "DEF" else r.player_name
        pos = "DST" if r.position == "DEF" else r.position
        rp = pos if pos in ("QB", "DST") else f"{pos}/FLEX"
        info = (f"{DK_TEAM.get(g.away_team, g.away_team)}@{DK_TEAM.get(g.home_team, g.home_team)} "
                f"{g.kickoff_et.strftime('%m/%d/%Y %I:%M%p')} ET")
        sal = _salary(rng, "dk", r.position, float(r.proj))
        rows.append([pos, f"{name} ({pid})", name, str(pid), rp, str(sal), info, team, f"{max(0, r.proj + rng.gauss(0, 3)):.2f}"])
    # awkward rows: spellings the sites use (no suffix, no periods), a player on the wrong team, a name we do not have
    for row in rows:
        if row[2].endswith(" Jr.") and row[2].startswith(("Marvin Harrison", "Brian Thomas")):
            row[2] = row[2].removesuffix(" Jr.")
            row[1] = f"{row[2]} ({row[3]})"
        if row[2] in ("A.J. Brown", "C.J. Stroud", "T.J. Hockenson"):
            row[2] = row[2].replace(".", "")
            row[1] = f"{row[2]} ({row[3]})"
    wr = next(r for r in rows if r[0] == "WR" and r[7] != "MIA")
    wr[7] = "MIA"                                                   # "traded": the file and our data disagree
    pid += 1
    rows.append(["WR", f"Zzyzx Notaplayer ({pid})", "Zzyzx Notaplayer", str(pid), "WR/FLEX", "3000",
                 rows[0][6], rows[0][7], "0.00"])
    return rows


def dk_showdown(players: pd.DataFrame, games: pd.DataFrame, rng: random.Random) -> list[list[str]]:
    g = games.iloc[-1]                                  # the week's last game (Monday night)
    teams = {g.home_team, g.away_team}
    sel = players[players["team"].isin(teams)].sort_values("proj", ascending=False)
    rows = []
    pid = 42_000_000
    info = (f"{DK_TEAM.get(g.away_team, g.away_team)}@{DK_TEAM.get(g.home_team, g.home_team)} "
            f"{g.kickoff_et.strftime('%m/%d/%Y %I:%M%p')} ET")
    for r in sel.itertuples():
        team = DK_TEAM.get(r.team, r.team)
        name = DK_DST[r.team] if r.position == "DEF" else r.player_name
        pos = "DST" if r.position == "DEF" else r.position
        flex = max(1000, min(15000, int(round((1000 + 520 * float(r.proj) + rng.gauss(0, 700)) / 200) * 200)))
        for rp, sal in (("CPT", int(flex * 1.5)), ("FLEX", flex)):
            pid += 1
            rows.append([pos, f"{name} ({pid})", name, str(pid), rp, str(sal), info, team, f"{r.proj:.2f}"])
    return rows


def fd_full(players: pd.DataFrame, games: pd.DataFrame, rng: random.Random) -> list[list[str]]:
    rows = []
    pid = 0
    sel = players[players["position"] != "K"].sort_values(["position", "proj"], ascending=[True, False])
    fd = D.price_site(A.load_board(query, SEASON, WEEK), "fd").set_index("key")["proj"]
    for r in sel.itertuples():
        g = _game_of(games, r.team)
        if g is None:
            continue
        pid += 1
        team = FD_TEAM.get(r.team, r.team)
        home, away = FD_TEAM.get(g.home_team, g.home_team), FD_TEAM.get(g.away_team, g.away_team)
        opp = away if team == home else home
        proj = float(fd.get(r.key, r.proj))
        if r.position == "DEF":
            first, nick, last = r.player_name.rsplit(" ", 1)[0], r.player_name, r.player_name.rsplit(" ", 1)[1]
            pos = "D"
        else:
            parts = str(r.player_name).split(" ", 1)
            first, nick, last = parts[0], r.player_name, parts[1] if len(parts) > 1 else ""
            pos = r.position
        inj = {"Questionable": "Q", "Doubtful": "D", "Out": "O"}.get(str(r.report_status or ""), "")
        sal = _salary(rng, "fd", r.position, proj)
        rows.append([f"125000-{70000 + pid}", pos, first, nick, last, f"{max(0, proj + rng.gauss(0, 3)):.1f}", "4",
                     str(sal), f"{away}@{home}", team, opp, inj, "", "", "", ""])
    return rows


DK_HEADER = ["Position", "Name + ID", "Name", "ID", "Roster Position", "Salary", "Game Info", "TeamAbbrev",
             "AvgPointsPerGame"]
FD_HEADER = ["Id", "Position", "First Name", "Nickname", "Last Name", "FPPG", "Played", "Salary", "Game", "Team",
             "Opponent", "Injury Indicator", "Injury Details", "Tier", "", ""]


def _write(path: Path, site: str, header: list[str], rows: list[list[str]]) -> None:
    with path.open("w", newline="") as fh:
        fh.write(HEAD.format(site=site) + "\n")
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


def main() -> None:
    global A, D
    from league_lab import anyleague as A
    from league_lab import dfs as D
    rng = random.Random(20261005)
    players, games = _players(), _games()
    _write(OUT / "dk_classic_week5.csv", "DraftKings", DK_HEADER, dk_classic(players, games, rng))
    _write(OUT / "dk_showdown_week5.csv", "DraftKings", DK_HEADER, dk_showdown(players, games, rng))
    _write(OUT / "fd_full_week5.csv", "FanDuel", FD_HEADER, fd_full(players, games, rng))
    # hostile: wrong headers; formulas in cells (the produced upload CSV must neutralise them)
    (OUT / "hostile_wrong_headers.csv").write_text("# SYNTHETIC hostile file (IM-5)\nPlayer,Team,Cost\nJosh Allen,BUF,7900\n")
    with (OUT / "hostile_formulas.csv").open("w", newline="") as fh:
        fh.write("# SYNTHETIC hostile file (IM-5): formulas in cells\n")
        w = csv.writer(fh)
        w.writerow(DK_HEADER)
        w.writerow(["WR", "=cmd|' /C calc'!A0 (43000001)", "=cmd|' /C calc'!A0", "43000001", "WR/FLEX", "3000",
                    "BUF@MIA 10/11/2026 01:00PM ET", "BUF", "0"])
        w.writerow(["WR", "@SUM(1+1) (43000002)", "@SUM(1+1)", "=1+1", "WR/FLEX", "3000",
                    "BUF@MIA 10/11/2026 01:00PM ET", "BUF", "0"])
        w.writerow(["QB", "+Josh Allen (43000003)", "+Josh Allen", "43000003", "QB", "-7900",
                    "BUF@MIA 10/11/2026 01:00PM ET", "BUF", "0"])
    print("written:", sorted(p.name for p in OUT.glob("*.csv")))


if __name__ == "__main__":
    main()
