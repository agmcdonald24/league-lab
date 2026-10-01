"""Write the Sleeper projections fixture tests/test_sleeper_projections.py replays (hand-built, never fetched).

Sleeper's projections endpoint (api.sleeper.com/projections/nfl/<season>/<week>?season_type=regular&position[]=...)
is blocked from the development sandbox, so this answer is built in the shape it is documented to have: a JSON
list, one object per player, with ``player_id``, ``week``, ``season`` (a string), ``season_type``, ``opponent``,
``team``, ``category`` ('proj'), ``company``, ``date``, ``game_id``, ``last_modified``, ``updated_at``, ``sport``,
``status``, a ``player`` object and ``stats`` (Sleeper's scoring keys, plus keys we never price: ``gp``,
``adp_dd_ppr``, ``rec_0_4``, ``rec_fd``, ``bonus_rec_te`` ...).

The 30 players are real Sleeper ids (week 4 of 2026: the top of League Lab's board in League of Scrubs, plus a
kicker and a defense); the stat lines are invented (League Lab's own week-4 line nudged by a fixed factor per
player, so they are plausible, not Sleeper's). ``pts_std`` / ``pts_half_ppr`` / ``pts_ppr`` are computed HERE
from Sleeper's own keys with Sleeper's default weights (``SLEEPER_DEFAULT``: never through League Lab's key
mapping), so the pricing test checks the mapping, not itself. Edge cases: an object without ``player_id``
(skipped), one whose ``stats`` is null (a row with an empty line), a non-numeric value (``rec_tgt: "n/a"``),
a DEF (``player_id`` = team; its ``pts_*`` are Sleeper's own, with points-allowed tiers we do not price).

Usage:  uv run python tests/fixtures/sleeper_projections/make_fixture.py   (rewrites projections_2026_w04.json)
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Sleeper's default (standard) weights, keyed by Sleeper's own stat keys; half PPR adds 0.5 a catch, PPR 1
SLEEPER_DEFAULT = {"pass_yd": 0.04, "pass_td": 4, "pass_int": -1, "pass_2pt": 2, "rush_yd": 0.1, "rush_td": 6,
                   "rush_2pt": 2, "rec_yd": 0.1, "rec_td": 6, "rec_2pt": 2, "fum_lost": -2,
                   "fgm_0_19": 3, "fgm_20_29": 3, "fgm_30_39": 3, "fgm_40_49": 4, "fgm_50p": 5, "fgmiss": -1,
                   "xpm": 1, "xpmiss": -1}

# sleeper_id, name, position, team, opponent, game_id, factor,
#   (pass_att, pass_yd, pass_td, pass_int, rush_att, rush_yd, rush_td, rec_tgt, rec, rec_yd, rec_td, fum_lost)
PLAYERS = [
    ("4984", "Josh Allen", "QB", "BUF", "NE", "2026_04_NE_BUF", 1.04, (28.6, 257.0, 1.93, 0.60, 5.8, 28.0, 0.75, 0, 0, 0, 0, 0.14)),
    ("4881", "Lamar Jackson", "QB", "BAL", "TEN", "2026_04_TEN_BAL", 1.07, (31.6, 247.5, 2.00, 0.66, 5.0, 25.7, 0.23, 0, 0, 0, 0, 0.10)),
    ("4046", "Patrick Mahomes", "QB", "KC", "LV", "2026_04_KC_LV", 0.97, (34.6, 252.3, 1.85, 0.95, 4.2, 23.2, 0.28, 0, 0, 0, 0, 0.13)),
    ("9758", "C.J. Stroud", "QB", "HOU", "DAL", "2026_04_DAL_HOU", 0.93, (33.2, 251.5, 1.71, 1.01, 4.6, 17.9, 0.33, 0, 0, 0, 0, 0.17)),
    ("11564", "Drake Maye", "QB", "NE", "BUF", "2026_04_NE_BUF", 1.02, (29.5, 249.0, 1.63, 0.44, 5.5, 24.0, 0.18, 0, 0, 0, 0, 0.25)),
    ("3294", "Dak Prescott", "QB", "DAL", "HOU", "2026_04_DAL_HOU", 1.05, (35.4, 261.5, 1.76, 0.86, 3.5, 17.7, 0.08, 0, 0, 0, 0, 0.21)),
    ("9221", "Jahmyr Gibbs", "RB", "DET", "CAR", "2026_04_DET_CAR", 0.98, (0, 0, 0, 0, 19.4, 89.5, 0.71, 6.5, 4.7, 49.1, 0.25, 0.09)),
    ("9509", "Bijan Robinson", "RB", "ATL", "NO", "2026_04_ATL_NO", 1.03, (0, 0, 0, 0, 19.8, 102.5, 0.51, 5.8, 4.8, 43.8, 0.24, 0.08)),
    ("6813", "Jonathan Taylor", "RB", "IND", "WAS", "2026_04_IND_WAS", 0.95, (0, 0, 0, 0, 19.2, 79.6, 0.84, 4.1, 3.3, 24.7, 0.14, 0.08)),
    ("8151", "Kenneth Walker III", "RB", "KC", "LV", "2026_04_KC_LV", 0.91, (0, 0, 0, 0, 17.9, 82.6, 0.55, 5.5, 4.3, 33.8, 0.14, 0.07)),
    ("8138", "James Cook", "RB", "BUF", "NE", "2026_04_NE_BUF", 1.08, (0, 0, 0, 0, 17.3, 92.4, 0.75, 3.2, 2.6, 20.9, 0.09, 0.10)),
    ("3198", "Derrick Henry", "RB", "BAL", "TEN", "2026_04_TEN_BAL", 1.06, (0, 0, 0, 0, 19.6, 102.8, 0.78, 2.5, 1.7, 13.3, 0.06, 0.07)),
    ("4034", "Christian McCaffrey", "RB", "SF", "DEN", "2026_04_DEN_SF", 1.10, (0, 0, 0, 0, 12.8, 61.9, 0.45, 6.2, 5.4, 39.0, 0.18, 0.05)),
    ("11584", "Bucky Irving", "RB", "TB", "GB", "2026_04_GB_TB", 0.96, (0, 0, 0, 0, 15.4, 67.3, 0.62, 4.4, 3.5, 24.3, 0.13, 0.11)),
    ("8130", "Trey McBride", "TE", "ARI", "NYG", "2026_04_ARI_NYG", 1.02, (0, 0, 0, 0, 0, 0, 0, 8.2, 6.1, 70.0, 0.41, 0.02)),
    ("12518", "Tyler Warren", "TE", "IND", "WAS", "2026_04_IND_WAS", 0.94, (0, 0, 0, 0, 0, 0, 0, 6.1, 4.4, 68.5, 0.36, 0.02)),
    ("10859", "Sam LaPorta", "TE", "DET", "CAR", "2026_04_DET_CAR", 1.01, (0, 0, 0, 0, 0, 0, 0, 6.5, 4.6, 59.8, 0.44, 0.02)),
    ("5001", "Dalton Schultz", "TE", "HOU", "DAL", "2026_04_DAL_HOU", 0.97, (0, 0, 0, 0, 0, 0, 0, 7.4, 5.4, 55.1, 0.35, 0.03)),
    ("1466", "Travis Kelce", "TE", "KC", "LV", "2026_04_KC_LV", 1.05, (0, 0, 0, 0, 0, 0, 0, 6.9, 4.6, 58.2, 0.34, 0.02)),
    ("10236", "Dalton Kincaid", "TE", "BUF", "NE", "2026_04_NE_BUF", 0.92, (0, 0, 0, 0, 0, 0, 0, 6.3, 3.8, 55.0, 0.37, 0.02)),
    ("9493", "Puka Nacua", "WR", "LA", "PHI", "2026_04_LA_PHI", 1.03, (0, 0, 0, 0, 0.5, 2.6, 0.08, 8.8, 5.3, 95.3, 0.45, 0.03)),
    ("8144", "Chris Olave", "WR", "NO", "ATL", "2026_04_ATL_NO", 0.95, (0, 0, 0, 0, 0.1, 0.4, 0.00, 9.7, 7.0, 80.1, 0.61, 0.02)),
    ("7547", "Amon-Ra St. Brown", "WR", "DET", "CAR", "2026_04_DET_CAR", 1.06, (0, 0, 0, 0, 0.1, 0.8, 0.01, 9.5, 6.3, 75.4, 0.71, 0.04)),
    ("9488", "Jaxon Smith-Njigba", "WR", "SEA", "LAC", "2026_04_LAC_SEA", 1.04, (0, 0, 0, 0, 0.3, 0.9, 0.01, 9.9, 6.6, 80.3, 0.56, 0.04)),
    ("7569", "Nico Collins", "WR", "HOU", "DAL", "2026_04_DAL_HOU", 0.99, (0, 0, 0, 0, 0.4, 2.8, 0.01, 8.8, 6.0, 75.9, 0.54, 0.03)),
    ("6786", "CeeDee Lamb", "WR", "DAL", "HOU", "2026_04_DAL_HOU", 1.09, (0, 0, 0, 0, 0.1, 0.6, 0.00, 9.3, 6.2, 78.8, 0.41, 0.02)),
    ("8112", "Drake London", "WR", "ATL", "NO", "2026_04_ATL_NO", 1.01, (0, 0, 0, 0, 0.2, 1.3, 0.01, 8.4, 5.6, 72.4, 0.44, 0.02)),
    ("12526", "Tetairoa McMillan", "WR", "CAR", "DET", "2026_04_DET_CAR", 0.9, (0, 0, 0, 0, 0.0, 0.4, 0.00, 7.8, 4.9, 72.0, 0.51, 0.03)),
]
KEYS = ("pass_att", "pass_yd", "pass_td", "pass_int", "rush_att", "rush_yd", "rush_td", "rec_tgt", "rec", "rec_yd",
        "rec_td", "fum_lost")


def points(stats: dict) -> dict:
    std = sum(w * float(stats.get(k) or 0) for k, w in SLEEPER_DEFAULT.items() if isinstance(stats.get(k), (int, float)))
    rec = float(stats.get("rec") or 0) if isinstance(stats.get("rec"), (int, float)) else 0.0
    return {"pts_std": round(std, 2), "pts_half_ppr": round(std + 0.5 * rec, 2), "pts_ppr": round(std + rec, 2)}


def obj(pid: str, name: str, pos: str, team: str, opp: str, game_id: str, stats: dict | None) -> dict:
    first, _, last = name.partition(" ")
    return {
        "status": None, "date": "2026-10-04", "category": "proj", "sport": "nfl", "season": "2026", "season_type": "regular",
        "week": 4, "player_id": pid, "team": team, "opponent": opp, "company": "rotowire", "game_id": game_id,
        "last_modified": 1759300000000, "updated_at": 1759300000000,
        "player": {"first_name": first, "last_name": last, "position": pos, "fantasy_positions": [pos], "team": team,
                   "injury_status": None, "years_exp": 5},
        "stats": stats,
    }


def build() -> list[dict]:
    out = []
    for i, (pid, name, pos, team, opp, game_id, f, line) in enumerate(PLAYERS):
        stats: dict = {k: round(v * f, 2 if k.endswith(("_td", "_int", "fum_lost")) else 1) for k, v in zip(KEYS, line, strict=True)
                       if v}
        if pos == "QB":
            stats["pass_cmp"] = round(stats["pass_att"] * 0.66, 1)
            stats["pass_2pt"] = 0.05                     # scored: 2 points a 2-pt conversion
        if pos == "TE":
            stats["bonus_rec_te"] = stats["rec"]         # a position bonus key: kept in the payload, not priced
        stats.update({"gp": 1.0, "adp_dd_ppr": 10 + i, "pos_adp_dd_ppr": f"{pos}{i}", "rec_0_4": 0.4, "rec_fd": 2.1,
                      "fum": round(stats.get("fum_lost", 0) * 2, 2)})
        if pid == "12526":
            stats["rec_tgt"] = "n/a"                     # a non-numeric value: NULL, never a crash
        stats.update(points(stats))
        out.append(obj(pid, name, pos, team, opp, game_id, stats))
    k = {"fga": 2.3, "fgm": 2.0, "fgm_20_29": 0.6, "fgm_30_39": 0.7, "fgm_40_49": 0.5, "fgm_50p": 0.2, "fgmiss": 0.3,
         "xpm": 2.6, "xpa": 2.7, "xpmiss": 0.1, "gp": 1.0}
    k.update(points(k))
    out.append(obj("11792", "Will Reichard", "K", "MIN", "MIA", "2026_04_MIA_MIN", k))
    d = {"sack": 3.1, "int": 0.9, "fum_rec": 0.6, "def_td": 0.2, "safe": 0.03, "pts_allow": 18.6, "yds_allow": 301.0,
         "gp": 1.0, "pts_std": 8.4, "pts_half_ppr": 8.4, "pts_ppr": 8.4}
    out.append(obj("MIN", "Minnesota Vikings", "DEF", "MIN", "MIA", "2026_04_MIA_MIN", d))
    out.append(obj("9999999", "Nobody Projected", "WR", "FA", None, None, None))         # stats null: an empty line
    nameless = obj("", "No Id", "WR", "FA", None, None, {"rec": 1.0, "pts_ppr": 1.0})
    del nameless["player_id"]
    out.append(nameless)                                                                 # no player_id: skipped
    return out


if __name__ == "__main__":
    path = HERE / "projections_2026_w04.json"
    path.write_text(json.dumps(build(), indent=1) + "\n")
    print(f"wrote {path} ({len(build())} objects)")
