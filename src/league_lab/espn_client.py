"""ESPN fantasy football leagues, read-only and unofficial (Wave I-K, IK-1): the client and ESPN's id tables.

ESPN publishes no developer API for fantasy leagues. The endpoints below are the ones ESPN's own web app calls; the
open-source client ``cwendt94/espn-api`` documents them (cited per table; read 2026-10-05):

* requests module — https://github.com/cwendt94/espn-api/blob/master/espn_api/requests/espn_requests.py (the views, the
  ``x-fantasy-filter`` header, 401 = private, 404 = no such league) and ``requests/constant.py`` (the host);
* football constants — https://github.com/cwendt94/espn-api/blob/master/espn_api/football/constant.py (the lineup slot
  ids ``POSITION_MAP``, the pro team ids ``PRO_TEAM_MAP``, the scoring stat ids ``SETTINGS_SCORING_FORMAT_MAP``);
* football league / settings / team / player / transaction modules (the JSON shapes: ``settings.rosterSettings
  .lineupSlotCounts``, ``settings.scoringSettings.scoringItems[]`` with ``pointsOverrides`` keyed by slot id,
  ``teams[].roster.entries[]``, ``schedule[]``, ``transactions[].items[]``);
* the unit-test data ``tests/football/unit/data/league_2018_data.json`` (a real 2018 response) for the field names.

**The one read**: ``GET https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/<season>/segments/0/leagues/
<id>?view=<view>[&scoringPeriodId=<week>]`` (seasons 2018 on; earlier seasons live under ``leagueHistory``, not
read here). Views, by method:

=================  ====================================================  =============================  ========
method             view (+ params)                                        what we read                    TTL
=================  ====================================================  =============================  ========
``settings``       ``mSettings``                                          name, size, slots, scoring,     a day
                                                                          schedule / acquisition settings
``status``         ``mStatus``                                            ``scoringPeriodId`` (the week), 10 min
                                                                          ``status`` (first / final week)
``teams``          ``mTeam``                                              teams (names, record, owners),  1 hour
                                                                          ``members`` (display names)
``rosters``        ``mRoster`` + ``scoringPeriodId``                      ``teams[].roster.entries[]``    10 min
                                                                          (player, ``lineupSlotId``)
``schedule``       ``mMatchupScore``                                      ``schedule[]`` (every matchup   5 min
                                                                          period, home / away points)
``transactions``   ``mTransactions2`` + ``scoringPeriodId`` + filter      adds, drops, trades of a week   10 min
``free_agents``    ``kona_player_info`` + ``scoringPeriodId`` + filter    ESPN's free agents / waivers    1 hour
=================  ====================================================  =============================  ========

The filters (JSON in the ``x-fantasy-filter`` request header, as espn-api sends them):

* transactions: ``{"transactions": {"filterType": {"value": ["FREEAGENT", "WAIVER", "TRADE_ACCEPT"]}}}``
* free agents: ``{"players": {"filterStatus": {"value": ["FREEAGENT", "WAIVERS"]}, "filterSlotIds": {"value":
  [0, 2, 4, 6, 16, 17, 23]}, "limit": 150, "sortPercOwned": {"sortPriority": 1, "sortAsc": false}}}``

**Public and private.** A public league answers anyone. A private league answers 401 unless the request carries the
manager's own ESPN cookies ``espn_s2`` and ``SWID``. The private path exists in this code but is **off** unless
``LEAGUE_LAB_ESPN_PRIVATE=on`` (and ``LEAGUE_LAB_API_SECRET`` is set: the cookie pair travels only inside the
encrypted ``ll_espn`` browser cookie, ``league_lab_api/espn_connect.py``). For one request the API puts the pair in
``AUTH`` (a ContextVar); this client sends it as cookies and **never logs or stores it**: the cache key of an
authenticated answer carries an HMAC digest of the pair (a per-process random key), never the pair, so another
visitor without the same cookies never gets a private league's cached answer; ``require_access`` refuses a league
known to be private to a request without them.

**Switches**: ``LEAGUE_LAB_ESPN_LEAGUES=off`` stops every ESPN league read (``espn_not_configured``: the kill switch
should ESPN object; default on); ``LEAGUE_LAB_ESPN_PRIVATE=on`` opens the private path (default off).

**Budget**: a token bucket of ``LEAGUE_LAB_ESPN_LEAGUE_PER_MIN`` calls a minute (default 30); HTTP 429 backs off for a
minute (``ESPNBusy``). Caches by kind (``TTL_S``); an expired answer is served when ESPN fails (stale on error).

**Fixtures**: ``LEAGUE_LAB_ESPN_LEAGUE_FIXTURES=<dir>`` reads ``<dir>/<league>/<view>.json`` (``mSettings``,
``mStatus``, ``mTeam``, ``mRoster``, ``mMatchupScore``, ``mTransactions2_<week>``, ``kona_player_info``) through the same
caches and bucket; a ``<dir>/<league>/_private`` file makes the league answer 401 without cookies; no ``<league>``
directory is a 404. (``LEAGUE_LAB_ESPN_FIXTURES`` is the ESPN *news* feed's fixture variable — a different thing.)
"""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterator, Mapping
from contextvars import ContextVar
from pathlib import Path
from typing import Any

from .sleeper_client import LeagueNotFound, SleeperBusy, SleeperUnavailable, TokenBucket

ESPN_API = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl"
FIXTURES_ENV = "LEAGUE_LAB_ESPN_LEAGUE_FIXTURES"
API_ENV = "LEAGUE_LAB_ESPN_LEAGUE_API"            # (LEAGUE_LAB_ESPN_API is the injury feed's)
SEASON_ENV = "LEAGUE_LAB_ESPN_SEASON"
PER_MIN_ENV = "LEAGUE_LAB_ESPN_LEAGUE_PER_MIN"    # (LEAGUE_LAB_ESPN_PER_MIN is the injury feed's)
PRIVATE_ENV = "LEAGUE_LAB_ESPN_PRIVATE"
ENABLED_ENV = "LEAGUE_LAB_ESPN_LEAGUES"         # off: no ESPN league is read (the kill switch; default on)
SECRET_ENV = "LEAGUE_LAB_API_SECRET"
DEFAULT_PER_MIN = 30
PREFIX = "espn:"
VERSION = "0.1"
USER_AGENT = f"league-lab/{VERSION} (isuckatfantasy beta; read-only; docs/ESPN_TERMS.md)"
FIRST_SEASON = 2018                      # the /seasons/<y>/segments/0 endpoint; older seasons are leagueHistory

TTL_S: dict[str, float] = {
    "settings": 24 * 3600, "status": 10 * 60, "teams": 3600, "rosters": 10 * 60, "schedule": 5 * 60,
    "transactions": 10 * 60, "free_agents": 3600,
}
VIEW_OF = {"settings": "mSettings", "status": "mStatus", "teams": "mTeam", "rosters": "mRoster",
           "schedule": "mMatchupScore", "transactions": "mTransactions2", "free_agents": "kona_player_info"}
TRANSACTION_FILTER = {"transactions": {"filterType": {"value": ["FREEAGENT", "WAIVER", "TRADE_ACCEPT"]}}}
FREE_AGENT_SLOTS = [0, 2, 4, 6, 16, 17, 23]
FREE_AGENT_LIMIT = 150


def free_agent_filter(limit: int = FREE_AGENT_LIMIT) -> dict:
    return {"players": {"filterStatus": {"value": ["FREEAGENT", "WAIVERS"]}, "filterSlotIds": {"value": FREE_AGENT_SLOTS},
                        "limit": int(limit), "sortPercOwned": {"sortPriority": 1, "sortAsc": False}}}


# ================================================================================================ ESPN's id tables
# Lineup slot ids (espn-api football/constant.py POSITION_MAP) -> the slot name League Lab solves (lineup.slot_eligibility
# reads it), or None: not a slot we model (IDP, punter, head coach, ESPN's team-QB / "ER" / rookie slots) — left out
# of ``roster_positions`` and said so on the league card. 20 (bench) and 21 (IR) are not starting slots.
SLOT_IDS: dict[int, tuple[str, str | None]] = {
    0: ("QB", "QB"), 1: ("TQB", None), 2: ("RB", "RB"), 3: ("RB/WR", "WRRB_FLEX"), 4: ("WR", "WR"),
    5: ("WR/TE", "REC_FLEX"), 6: ("TE", "TE"), 7: ("OP", "SUPER_FLEX"), 8: ("DT", None), 9: ("DE", None),
    10: ("LB", None), 11: ("DL", None), 12: ("CB", None), 13: ("S", None), 14: ("DB", None), 15: ("DP", None),
    16: ("D/ST", "DEF"), 17: ("K", "K"), 18: ("P", None), 19: ("HC", None), 20: ("BE", "BN"), 21: ("IR", "IR"),
    22: ("", None), 23: ("FLEX", "FLEX"), 24: ("ER", None), 25: ("Rookie", None),
}
BENCH_SLOT, IR_SLOT = 20, 21
IDP_SLOT_IDS = frozenset({8, 9, 10, 11, 12, 13, 14, 15})
# Sleeper's order for roster_positions (QB first … K, DEF last)
SLOT_ORDER = {"QB": 0, "RB": 1, "WR": 2, "TE": 3, "WRRB_FLEX": 4, "REC_FLEX": 5, "FLEX": 6, "SUPER_FLEX": 7, "K": 8,
              "DEF": 9}

# A player's own position: ``player.defaultPositionId`` (ESPN's position ids — not the slot ids; espn-api reads the
# position from ``eligibleSlots`` instead, which is the fallback here: the first slot that is a single position).
POSITION_IDS = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 7: "P", 9: "DT", 10: "DE", 11: "LB", 12: "CB", 13: "S",
                14: "HC", 16: "DEF"}
SLOT_POSITION = {0: "QB", 2: "RB", 4: "WR", 6: "TE", 16: "DEF", 17: "K"}

# Pro team ids (espn-api PRO_TEAM_MAP) -> Sleeper's team codes (ESPN's WSH is Sleeper's WAS). A D/ST's player id is
# ``-16000 - proTeamId`` (-16001 Atlanta … -16034 Houston).
PRO_TEAMS = {1: "ATL", 2: "BUF", 3: "CHI", 4: "CIN", 5: "CLE", 6: "DAL", 7: "DEN", 8: "DET", 9: "GB", 10: "TEN",
             11: "IND", 12: "KC", 13: "LV", 14: "LAR", 15: "MIA", 16: "MIN", 17: "NE", 18: "NO", 19: "NYG", 20: "NYJ",
             21: "PHI", 22: "ARI", 23: "PIT", 24: "LAC", 25: "SF", 26: "SEA", 27: "TB", 28: "WAS", 29: "CAR",
             30: "JAX", 33: "BAL", 34: "HOU"}
DST_BASE = -16000

# ESPN injury words -> Sleeper's
INJURY = {"QUESTIONABLE": "Questionable", "DOUBTFUL": "Doubtful", "OUT": "Out", "INJURY_RESERVE": "IR",
          "SUSPENSION": "Sus", "DAY_TO_DAY": "Questionable", "PROBABLE": None, "ACTIVE": None, "NORMAL": None}


def dst_team(espn_player_id: Any) -> str | None:
    """A D/ST's player id (-16012) -> the Sleeper team code (KC); None for anyone else."""
    try:
        i = int(espn_player_id)
    except (TypeError, ValueError):
        return None
    return PRO_TEAMS.get(DST_BASE - i) if i < 0 else None


# ------------------------------------------------------------------------------------------------ scoring
# ESPN scoring stat id -> what it is (espn-api SETTINGS_SCORING_FORMAT_MAP's label) and how it lands on Sleeper's
# ``scoring_settings`` keys: a list of (key, multiplier) — the item's points times the multiplier are added to each key
# — or a kind handled below. ``None``: no Sleeper key; listed as unpriced with ESPN's label. Per-player items use
# ``points``; a D/ST item uses ``pointsOverrides["16"]`` (slot 16 = D/ST) when ESPN gives one.
STAT_LABELS = {
    0: "each pass attempted", 1: "each pass completed", 2: "each incomplete pass", 3: "passing yards", 4: "TD pass",
    5: "every 5 passing yards", 6: "every 10 passing yards", 7: "every 20 passing yards", 8: "every 25 passing yards",
    9: "every 50 passing yards", 10: "every 100 passing yards", 11: "every 5 pass completions",
    12: "every 10 pass completions", 13: "every 5 pass incompletions", 14: "every 10 pass incompletions",
    15: "40+ yard TD pass bonus", 16: "50+ yard TD pass bonus", 17: "300-399 yard passing game",
    18: "400+ yard passing game", 19: "2pt passing conversion", 20: "interceptions thrown",
    21: "passing completion pct", 22: "passing yards per game", 23: "rushing attempts", 24: "rushing yards",
    25: "TD rush", 26: "2pt rushing conversion", 27: "every 5 rushing yards", 28: "every 10 rushing yards",
    29: "every 20 rushing yards", 30: "every 25 rushing yards", 31: "every 50 rushing yards",
    32: "every 100 rushing yards", 33: "every 5 rush attempts", 34: "every 10 rush attempts",
    35: "40+ yard TD rush bonus", 36: "50+ yard TD rush bonus", 37: "100-199 yard rushing game",
    38: "200+ yard rushing game", 39: "rushing yards per attempt", 40: "rushing yards per game", 41: "receptions",
    42: "receiving yards", 43: "TD reception", 44: "2pt receiving conversion", 45: "40+ yard TD rec bonus",
    46: "50+ yard TD rec bonus", 47: "every 5 receiving yards", 48: "every 10 receiving yards",
    49: "every 20 receiving yards", 50: "every 25 receiving yards", 51: "every 50 receiving yards",
    52: "every 100 receiving yards", 53: "each reception", 54: "every 5 receptions", 55: "every 10 receptions",
    56: "100-199 yard receiving game", 57: "200+ yard receiving game", 58: "receiving target",
    59: "receiving yards after catch", 60: "receiving yards per catch", 61: "receiving yards per game",
    62: "total 2pt conversions", 63: "fumble recovered for TD", 64: "sacked", 65: "passing fumbles",
    66: "rushing fumbles", 67: "receiving fumbles", 68: "total fumbles", 69: "passing fumbles lost",
    70: "rushing fumbles lost", 71: "receiving fumbles lost", 72: "total fumbles lost", 73: "total turnovers",
    74: "FG made (50+ yards)", 75: "FG attempted (50+ yards)", 76: "FG missed (50+ yards)", 77: "FG made (40-49 yards)",
    78: "FG attempted (40-49 yards)", 79: "FG missed (40-49 yards)", 80: "FG made (0-39 yards)",
    81: "FG attempted (0-39 yards)", 82: "FG missed (0-39 yards)", 83: "total FG made", 84: "total FG attempted",
    85: "total FG missed", 86: "each PAT made", 87: "each PAT attempted", 88: "each PAT missed",
    89: "0 points allowed", 90: "1-6 points allowed", 91: "7-13 points allowed", 92: "14-17 points allowed",
    93: "blocked punt or FG return for TD", 94: "fumble or INT return for TD", 95: "each interception",
    96: "each fumble recovered", 97: "blocked punt, PAT or FG", 98: "each safety", 99: "each sack", 100: "1/2 sack",
    101: "kickoff return TD", 102: "punt return TD", 103: "interception return TD", 104: "fumble return TD",
    105: "total return TD", 106: "each fumble forced", 107: "assisted tackles", 108: "solo tackles",
    109: "total tackles", 110: "every 3 total tackles", 111: "every 5 total tackles", 112: "stuffs",
    113: "passes defensed", 114: "kickoff return yards", 115: "punt return yards", 116: "every 10 kickoff return yards",
    117: "every 25 kickoff return yards", 118: "every 10 punt return yards", 119: "every 25 punt return yards",
    120: "points allowed", 121: "18-21 points allowed", 122: "22-27 points allowed", 123: "28-34 points allowed",
    124: "35-45 points allowed", 125: "46+ points allowed", 126: "points allowed per game", 127: "yards allowed",
    128: "less than 100 total yards allowed", 129: "100-199 total yards allowed", 130: "200-299 total yards allowed",
    131: "300-349 total yards allowed", 132: "350-399 total yards allowed", 133: "400-449 total yards allowed",
    134: "450-499 total yards allowed", 135: "500-549 total yards allowed", 136: "550+ total yards allowed",
    137: "yards allowed per game", 155: "team win", 156: "team loss", 157: "team tie", 158: "points scored",
    175: "0-9 yd TD pass bonus", 176: "10-19 yd TD pass bonus", 177: "20-29 yd TD pass bonus",
    178: "30-39 yd TD pass bonus", 179: "0-9 yd TD rush bonus", 180: "10-19 yd TD rush bonus",
    181: "20-29 yd TD rush bonus", 182: "30-39 yd TD rush bonus", 183: "0-9 yd TD rec bonus",
    184: "10-19 yd TD rec bonus", 185: "20-29 yd TD rec bonus", 186: "30-39 yd TD rec bonus",
    187: "D/ST points allowed", 188: "D/ST 0 points allowed", 189: "D/ST 1-6 points allowed",
    190: "D/ST 7-13 points allowed", 191: "D/ST 14-17 points allowed", 192: "D/ST 18-21 points allowed",
    193: "D/ST 22-27 points allowed", 194: "D/ST 28-34 points allowed", 195: "D/ST 35-45 points allowed",
    196: "D/ST 46+ points allowed", 198: "FG made (50-59 yards)", 199: "FG attempted (50-59 yards)",
    200: "FG missed (50-59 yards)", 201: "FG made (60+ yards)", 202: "FG attempted (60+ yards)",
    203: "FG missed (60+ yards)", 204: "offensive 2pt return", 205: "defensive 2pt return", 206: "2pt return",
    207: "offensive 1pt safety", 208: "defensive 1pt safety", 209: "1pt safety", 210: "games played",
    211: "passing first down", 212: "rushing first down", 213: "receiving first down", 214: "FG made yards",
    215: "FG missed yards", 216: "FG attempt yards",
}
_FG_SHORT = ["fgm_0_19", "fgm_20_29", "fgm_30_39"]
_FGMISS_SHORT = ["fgmiss_0_19", "fgmiss_20_29", "fgmiss_30_39"]
_FGM_ALL = [*_FG_SHORT, "fgm_40_49", "fgm_50p"]
# player (offense / kicker) items: stat id -> [(Sleeper key, multiplier)]
PLAYER_STATS: dict[int, list[tuple[str, float]]] = {
    0: [("pass_att", 1)], 1: [("pass_cmp", 1)], 2: [("pass_inc", 1)], 3: [("pass_yd", 1)], 4: [("pass_td", 1)],
    15: [("pass_td_40p", 1)], 16: [("pass_td_50p", 1)], 17: [("bonus_pass_yd_300", 1)],
    18: [("bonus_pass_yd_400", 1)], 19: [("pass_2pt", 1)], 20: [("pass_int", 1)],
    23: [("rush_att", 1)], 24: [("rush_yd", 1)], 25: [("rush_td", 1)], 26: [("rush_2pt", 1)],
    35: [("rush_td_40p", 1)], 36: [("rush_td_50p", 1)], 37: [("bonus_rush_yd_100", 1)], 38: [("bonus_rush_yd_200", 1)],
    41: [("rec", 1)], 42: [("rec_yd", 1)], 43: [("rec_td", 1)], 44: [("rec_2pt", 1)], 45: [("rec_td_40p", 1)],
    46: [("rec_td_50p", 1)], 53: [("rec", 1)], 56: [("bonus_rec_yd_100", 1)], 57: [("bonus_rec_yd_200", 1)],
    58: [("rec_tgt", 1)], 62: [("pass_2pt", 1), ("rush_2pt", 1), ("rec_2pt", 1)], 63: [("fum_rec_td", 1)],
    64: [("pass_sack", 1)], 68: [("fum", 1)], 72: [("fum_lost", 1)], 73: [("pass_int", 1), ("fum_lost", 1)],
    74: [("fgm_50p", 1)], 76: [("fgmiss_50p", 1)], 77: [("fgm_40_49", 1)], 79: [("fgmiss_40_49", 1)],
    80: [(k, 1) for k in _FG_SHORT], 82: [(k, 1) for k in _FGMISS_SHORT], 83: [(k, 1) for k in _FGM_ALL],
    85: [("fgmiss", 1)], 86: [("xpm", 1)], 87: [("xpm", 1), ("xpmiss", 1)], 88: [("xpmiss", 1)],
    # an attempt pays on a make and on a miss
    75: [("fgm_50p", 1), ("fgmiss_50p", 1)], 78: [("fgm_40_49", 1), ("fgmiss_40_49", 1)],
    81: [*[(k, 1) for k in _FG_SHORT], *[(k, 1) for k in _FGMISS_SHORT]], 84: [*[(k, 1) for k in _FGM_ALL], ("fgmiss", 1)],
    198: [("fgm_50p", 1)], 199: [("fgm_50p", 1), ("fgmiss_50p", 1)], 200: [("fgmiss_50p", 1)],
    101: [("st_td", 1)], 102: [("st_td", 1)], 114: [("kr_yd", 1)], 115: [("pr_yd", 1)],
    211: [("pass_fd", 1)], 212: [("rush_fd", 1)], 213: [("rec_fd", 1)],
}
# "every N units" items: ESPN pays a whole point per N; Sleeper prices per unit: points / N a unit (approximated)
PER_N: dict[int, tuple[str, int]] = {5: ("pass_yd", 5), 6: ("pass_yd", 10), 7: ("pass_yd", 20), 8: ("pass_yd", 25),
                                     9: ("pass_yd", 50), 10: ("pass_yd", 100), 11: ("pass_cmp", 5), 12: ("pass_cmp", 10),
                                     13: ("pass_inc", 5), 14: ("pass_inc", 10), 27: ("rush_yd", 5), 28: ("rush_yd", 10),
                                     29: ("rush_yd", 20), 30: ("rush_yd", 25), 31: ("rush_yd", 50), 32: ("rush_yd", 100),
                                     33: ("rush_att", 5), 34: ("rush_att", 10), 47: ("rec_yd", 5), 48: ("rec_yd", 10),
                                     49: ("rec_yd", 20), 50: ("rec_yd", 25), 51: ("rec_yd", 50), 52: ("rec_yd", 100),
                                     54: ("rec", 5), 55: ("rec", 10), 116: ("kr_yd", 10), 117: ("kr_yd", 25),
                                     118: ("pr_yd", 10), 119: ("pr_yd", 25)}
# fumbles by kind (passing / rushing / receiving): one Sleeper key for any fumble
FUMBLE_PARTS = {65: "fum", 66: "fum", 67: "fum", 69: "fum_lost", 70: "fum_lost", 71: "fum_lost"}
# D/ST items: stat id -> [(Sleeper key, multiplier)]
DST_STATS: dict[int, list[tuple[str, float]]] = {
    93: [("def_st_td", 1)], 94: [("def_td", 1)], 95: [("int", 1)], 96: [("fum_rec", 1)], 97: [("blk_kick", 1)],
    98: [("safe", 1)], 99: [("sack", 1)], 100: [("sack", 2)], 101: [("def_st_td", 1)], 102: [("def_st_td", 1)],
    103: [("def_td", 1)], 104: [("def_td", 1)], 105: [("def_td", 1), ("def_st_td", 1)], 106: [("ff", 1)],
    205: [("def_2pt", 1)], 206: [("def_2pt", 1)],
    128: [("yds_allow_0_100", 1)], 129: [("yds_allow_100_199", 1)], 130: [("yds_allow_200_299", 1)],
    131: [("yds_allow_300_349", 1)], 132: [("yds_allow_350_399", 1)], 133: [("yds_allow_400_449", 1)],
    134: [("yds_allow_450_499", 1)], 135: [("yds_allow_500_549", 1)], 136: [("yds_allow_550p", 1)],
}
# points-allowed bands (ESPN's, inclusive; None = no top): stat id -> (low, high). 187-196 are the "D/ST points allowed"
# copies some leagues use instead of 89-125.
PA_BANDS: dict[int, tuple[int, int | None]] = {89: (0, 0), 90: (1, 6), 91: (7, 13), 92: (14, 17), 121: (18, 21),
                                               122: (22, 27), 123: (28, 34), 124: (35, 45), 125: (46, None),
                                               188: (0, 0), 189: (1, 6), 190: (7, 13), 191: (14, 17), 192: (18, 21),
                                               193: (22, 27), 194: (28, 34), 195: (35, 45), 196: (46, None)}
SLEEPER_PA = [("pts_allow_0", 0, 0), ("pts_allow_1_6", 1, 6), ("pts_allow_7_13", 7, 13),
              ("pts_allow_14_20", 14, 20), ("pts_allow_21_27", 21, 27), ("pts_allow_28_34", 28, 34),
              ("pts_allow_35p", 35, 45)]
# slot ids a position-specific override can name -> the Sleeper reception premium key
REC_PREMIUM = {2: "bonus_rec_rb", 4: "bonus_rec_wr", 6: "bonus_rec_te"}
DST_SLOT = "16"


def _num(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def scoring(settings: Mapping) -> tuple[dict[str, float], dict]:
    """ESPN ``settings.scoringSettings`` -> (Sleeper ``scoring_settings``, report). The report: ``approximated``
    (sentences: "every N yards" priced per yard, points-allowed bands averaged onto Sleeper's, a position-specific
    rate priced at the base), ``unpriced`` (ESPN's labels with no Sleeper key: priced at nothing), ``pa_bands`` (ESPN's
    own points-allowed bands as read), ``fg_60`` (the 60+ yard FG points), ``scoring_type`` (H2H_POINTS, …), ``categories`` (True for a categories
    league: not priced as points)."""
    ss = settings.get("scoringSettings") if isinstance(settings.get("scoringSettings"), Mapping) else settings
    items = [x for x in (ss.get("scoringItems") or []) if isinstance(x, Mapping)]
    sc: dict[str, float] = {}
    approx: list[str] = []
    unpriced: dict[int, str] = {}
    pa: list[tuple[int, int | None, float]] = []
    fg60: float | None = None
    by_id: dict[int, list[Mapping]] = {}
    for it in items:
        try:
            by_id.setdefault(int(it.get("statId")), []).append(it)
        except (TypeError, ValueError):
            continue

    def add(key: str, val: float) -> None:
        if val:
            sc[key] = round(sc.get(key, 0.0) + val, 6)

    def label(sid: int) -> str:
        return STAT_LABELS.get(sid, f"ESPN stat {sid}")

    returns: dict[str, list[float]] = {}           # def_td / def_st_td / st_td from several ESPN items: averaged
    for sid, its in sorted(by_id.items()):
        it = its[0]
        base = _num(it.get("points"))
        over = {str(k): _num(v) for k, v in (it.get("pointsOverrides") or {}).items()}
        dst = over.get(DST_SLOT, base if sid in DST_STATS or sid in PA_BANDS else 0.0)
        others = {k: v for k, v in over.items() if k != DST_SLOT and v != base}
        if sid in PA_BANDS:
            lo, hi = PA_BANDS[sid]
            if not any(a == lo for a, _, _ in pa):     # 89-125 and their 187-196 copies: the first one read
                pa.append((lo, hi, dst))
            continue
        if sid in (101, 102):                      # a return TD: a player's (st_td) and a D/ST's (def_st_td)
            if base:
                returns.setdefault("st_td", []).append(base)
            if dst:
                returns.setdefault("def_st_td", []).append(dst)
            continue
        if sid in (93, 94, 103, 104, 105):
            if dst:
                for key, m in DST_STATS[sid]:
                    returns.setdefault(key, []).append(dst * m)
            continue
        if sid in DST_STATS:
            for key, m in DST_STATS[sid]:
                add(key, dst * m)
            continue
        if sid in (201,):                          # FG 60+: Sleeper stops at 50+ (the spec carries it exactly)
            fg60 = base
            continue
        if sid in (202, 203):
            if base:
                unpriced[sid] = label(sid)
            continue
        if sid in PER_N:
            key, n = PER_N[sid]
            if base:
                add(key, base / n)
                approx.append(f"{label(sid)}: ESPN pays {base:g} per {n}; priced at {base / n:g} a unit")
            continue
        if sid in FUMBLE_PARTS:
            if base:
                add(FUMBLE_PARTS[sid], base)
                approx.append(f"{label(sid)}: priced on every fumble ({'lost' if 'lost' in label(sid) else 'any'})")
            continue
        if sid in PLAYER_STATS:
            for key, m in PLAYER_STATS[sid]:
                add(key, base * m)
            if others:
                if sid in (41, 53):
                    for slot, v in others.items():
                        prem = REC_PREMIUM.get(int(slot)) if slot.isdigit() else None
                        if prem:
                            add(prem, v - base)
                        else:
                            approx.append(f"{label(sid)}: ESPN pays {v:g} at {SLOT_IDS.get(int(slot), (slot,))[0]}; "
                                          f"priced at {base:g}")
                else:
                    approx.append(f"{label(sid)}: ESPN pays some positions differently; priced at {base:g}")
            continue
        if base or any(over.values()):
            unpriced[sid] = label(sid)
    for key, vals in returns.items():
        sc[key] = round(sum(vals) / len(vals), 6)
        if len(set(vals)) > 1:
            approx.append(f"return touchdowns ({key}): ESPN's {', '.join(f'{v:g}' for v in vals)} averaged")
    if any(p for _, _, p in pa):
        pa.sort(key=lambda b: b[0])
        for key, lo, hi in SLEEPER_PA:
            vals = [next((p for a, b, p in pa if a <= x and (b is None or x <= b)), 0.0) for x in range(lo, hi + 1)]
            v = round(sum(vals) / len(vals), 3)
            if v:
                sc[key] = v
        if [(a, b) for a, b, _ in pa] != [(lo, hi) for _, lo, hi in SLEEPER_PA][:len(pa)]:
            approx.append("points allowed: ESPN's bands (" + ", ".join(f"{a}+" if b is None else (f"{a}" if a == b else f"{a}-{b}")
                                                                    for a, b, _ in pa)
                          + ") are averaged onto Sleeper's (0, 1-6, 7-13, 14-20, 21-27, 28-34, 35+), point by point")
    if fg60 is not None and round(fg60 - sc.get("fgm_50p", 0.0), 6) != 0:
        if "fgm_50p" not in sc:
            sc["fgm_50p"] = fg60
        else:
            approx.append(f"FG made (60+ yards): ESPN pays {fg60:g}; priced at the 50+ points ({sc['fgm_50p']:g})")
    stype = str(ss.get("scoringType") or "H2H_POINTS")
    cats = "CATEGOR" in stype.upper() or "ROTO" in stype.upper()
    return sc, {"approximated": approx, "unpriced": sorted(set(unpriced.values())), "unpriced_ids": sorted(unpriced),
                "pa_bands": [list(b) for b in pa], "fg_60": fg60, "scoring_type": stype, "categories": cats}


def slots(settings: Mapping) -> tuple[list[str], dict]:
    """ESPN ``settings.rosterSettings.lineupSlotCounts`` ({slot id: count}) -> Sleeper ``roster_positions`` (QB … K,
    DEF in Sleeper's order, then ``BN`` × bench) and a note: ``left_out`` (ESPN's names of every starting spot not
    modelled, one per spot), ``idp`` (the IDP slot names, once each: DT, DE, LB, DL, CB, S, DB, DP), ``unknown`` (the
    others, once each: TQB, P, HC, ER, Rookie), ``bench``, ``ir`` (Sleeper's ``reserve_slots``)."""
    rs = settings.get("rosterSettings") if isinstance(settings.get("rosterSettings"), Mapping) else settings
    counts: dict[int, int] = {}
    for k, v in (rs.get("lineupSlotCounts") or {}).items():
        try:
            if int(v) > 0:
                counts[int(k)] = int(v)
        except (TypeError, ValueError):
            continue
    out: list[str] = []
    left: list[str] = []
    idp: list[str] = []
    unknown: list[str] = []
    for sid, n in sorted(counts.items()):
        if sid in (BENCH_SLOT, IR_SLOT):
            continue
        espn_name, ours = SLOT_IDS.get(sid, (f"slot {sid}", None))
        if ours is None:
            name = espn_name or f"slot {sid}"
            left += [name] * n
            (idp if sid in IDP_SLOT_IDS else unknown).append(name)
            continue
        out += [ours] * n
    out.sort(key=lambda s: SLOT_ORDER.get(s, 99))
    bench = counts.get(BENCH_SLOT, 0)
    # ``idp`` / ``unknown``: the names once each, as MFL's note carries them (the card reads ``idp`` as a list)
    return out + ["BN"] * bench, {"left_out": left, "idp": idp, "unknown": unknown, "bench": bench,
                                  "ir": counts.get(IR_SLOT, 0)}


def slot_name(slot_id: Any) -> str | None:
    """A lineupSlotId -> our slot name (BN, IR included); None for a slot not modelled."""
    try:
        return SLOT_IDS.get(int(slot_id), ("", None))[1]
    except (TypeError, ValueError):
        return None


def player_position(player: Mapping) -> str | None:
    """ESPN's player record -> QB / RB / WR / TE / K / DEF (others: ESPN's word, P / DT / LB …)."""
    pid = player.get("defaultPositionId")
    try:
        if int(pid) in POSITION_IDS:
            return POSITION_IDS[int(pid)]
    except (TypeError, ValueError):
        pass
    for s in player.get("eligibleSlots") or []:
        try:
            if int(s) in SLOT_POSITION:
                return SLOT_POSITION[int(s)]
        except (TypeError, ValueError):
            continue
    return None


# ================================================================================================ keys and links
_LEAGUE = re.compile(r"^\d{1,12}$")
_KEY = re.compile(r"^espn:(?:(\d{4}):)?(\d{1,12})$", re.I)
WHERE = "the number after leagueId= in your league's address (fantasy.espn.com/football/league?leagueId=4242)"


class ESPNBusy(SleeperBusy):
    """Our ESPN budget is spent for the moment (or ESPN asked us to slow down)."""


class ESPNUnavailable(SleeperUnavailable):
    """ESPN could not be reached (or a fixture is missing)."""


def _err(exc: LeagueNotFound, code: str, fix: str | None, league_id: str | None = None) -> LeagueNotFound:
    exc.code = code                     # type: ignore[attr-defined]
    exc.fix = fix                       # type: ignore[attr-defined]
    exc.league_id = league_id           # type: ignore[attr-defined]
    return exc


class LeaguePrivate(LeagueNotFound):
    """ESPN answered 401: the league is private (or the cookies given do not open it). ``code`` espn_league_private."""

    def __init__(self, league_id: str, *, with_cookies: bool = False) -> None:
        if with_cookies:
            words = (f"ESPN would not share league {league_id} with the cookies you gave: they may have expired (ESPN "
                     "signs you out after a while) or belong to an account that is not in this league.")
            fix = "Copy espn_s2 and SWID again from fantasy.espn.com, or ask the commissioner to make the league public."
        else:
            words = (f"ESPN league {league_id} is private. ESPN has no sign-in for other apps; a public league works by "
                     "its id (Settings → Basic Settings → League Visibility in ESPN)")
            fix = ("Or use “Private league?” to read it with your own ESPN cookies: they stay in your browser."
                   if private_enabled() else "Ask the commissioner to make the league public, then try again.")
        super().__init__(words)
        _err(self, "espn_league_private", fix, league_id)
        self.with_cookies = with_cookies


def unknown_league(league_id: str, season: int | None = None) -> LeagueNotFound:
    when = f" in {season}" if season else " this season"
    return _err(LeagueNotFound(f"ESPN has no league {league_id}{when}."), "espn_league_unknown",
                f"Check the id: it is {WHERE}.", league_id)


def enabled() -> bool:
    """``LEAGUE_LAB_ESPN_LEAGUES`` is not off (default on): the kill switch for every ESPN league read."""
    return str(os.environ.get(ENABLED_ENV) or "on").strip().lower() not in ("off", "0", "false", "no")


def switched_off(league_id: str | None = None) -> LeagueNotFound:
    return _err(LeagueNotFound("ESPN leagues are switched off on this server."), "espn_not_configured",
                "A Sleeper or MyFantasyLeague league works as before.", league_id)


def invalid_link(text: Any = None) -> LeagueNotFound:
    return _err(LeagueNotFound("That is not an ESPN league link or id."), "espn_link_invalid",
                f"Paste your league's address, or the league id alone: {WHERE}.")


def setup_words(exc: BaseException, league_id: str | None = None) -> tuple[str, str, str | None]:
    """(code, words, fix) for II-5's ``SetupError`` from an ESPN error (the exception's own when it carries them)."""
    code = getattr(exc, "code", None)
    if code:
        return str(code), str(exc), getattr(exc, "fix", None)
    if league_id is None:
        e = invalid_link()
    else:
        e = unknown_league(str(league_id))
    return e.code, str(e), e.fix                   # type: ignore[attr-defined]


def is_espn(key: Any) -> bool:
    return str(key or "").strip().lower().startswith(PREFIX)


def check_league(league_id: Any) -> str:
    s = str(league_id).strip()
    if not _LEAGUE.match(s):
        raise invalid_link(league_id)
    return str(int(s))


def parse_key(key: Any) -> tuple[str, int | None]:
    """``espn:4242`` -> ("4242", None); ``espn:2025:4242`` -> ("4242", 2025). Anything else: ``espn_link_invalid``."""
    m = _KEY.match(str(key or "").strip())
    if not m:
        raise invalid_link(key)
    season = int(m.group(1)) if m.group(1) else None
    if season is not None and season < FIRST_SEASON:
        raise invalid_link(key)
    return str(int(m.group(2))), season


def check_key(key: Any) -> str:
    """The canonical key: ``espn:<id>`` or ``espn:<season>:<id>``."""
    lid, season = parse_key(key)
    return f"{PREFIX}{season}:{lid}" if season else f"{PREFIX}{lid}"


def make_key(league_id: Any, season: int | None = None) -> str:
    lid = check_league(league_id)
    return f"{PREFIX}{int(season)}:{lid}" if season else f"{PREFIX}{lid}"


def parse_link(text: Any) -> tuple[str, str | None, int | None]:
    """A pasted ESPN link (or a bare id, or a key) -> (league id, ESPN team id or None, season or None):
    ``4242``, ``espn:4242``, ``fantasy.espn.com/football/league?leagueId=4242``,
    ``https://fantasy.espn.com/football/team?leagueId=4242&teamId=3&seasonId=2026``."""
    s = str(text or "").strip()
    if not s:
        raise invalid_link(text)
    if is_espn(s):
        lid, season = parse_key(s)
        return lid, None, season
    if _LEAGUE.match(s):
        return str(int(s)), None, None
    u = urllib.parse.urlparse(s if "://" in s else "https://" + s)
    if not (u.hostname or "").lower().endswith("espn.com"):
        raise invalid_link(text)
    q = {k.lower(): v for k, v in urllib.parse.parse_qs(u.query).items()}
    lid = (q.get("leagueid") or [None])[0]
    if not lid or not _LEAGUE.match(lid.strip()):
        raise invalid_link(text)
    tid = (q.get("teamid") or [None])[0]
    tid = str(int(tid)) if tid and tid.strip().isdigit() else None
    season = (q.get("seasonid") or [None])[0]
    year = int(season) if season and season.strip().isdigit() and FIRST_SEASON <= int(season) <= 2100 else None
    return str(int(lid)), tid, year


def season_now() -> int:
    """``LEAGUE_LAB_ESPN_SEASON``, else the NFL season of today: the calendar year from March, the year before in
    January and February (ESPN rolls its fantasy season over in the spring)."""
    env = os.environ.get(SEASON_ENV)
    if env and env.strip().isdigit():
        return int(env)
    try:
        from . import clock
        t = clock.now()
        y, mo = t.year, t.month
    except Exception:  # noqa: BLE001 - the pinned clock is a nicety: the system clock answers otherwise
        g = time.gmtime()
        y, mo = g.tm_year, g.tm_mon
    return y if mo >= 3 else y - 1


def _per_minute() -> float:
    try:
        return max(1.0, float(os.environ.get(PER_MIN_ENV) or DEFAULT_PER_MIN))
    except ValueError:
        return float(DEFAULT_PER_MIN)


# ================================================================================================ the private path
AUTH: ContextVar[tuple[str, str] | None] = ContextVar("league_lab_espn_auth", default=None)
_DIGEST_KEY = secrets.token_bytes(32)          # per process: a digest is only compared within this process
_SWID = re.compile(r"^\{?([0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12})\}?$")
_S2 = re.compile(r"^[A-Za-z0-9%+/=_.\-]{40,2048}$")


def private_enabled() -> bool:
    """``LEAGUE_LAB_ESPN_PRIVATE=on`` and a ``LEAGUE_LAB_API_SECRET`` to encrypt the cookie with (16+ characters)."""
    on = str(os.environ.get(PRIVATE_ENV) or "off").strip().lower() in ("on", "1", "true", "yes")
    return on and len(os.environ.get(SECRET_ENV) or "") >= 16


def clean_cookies(espn_s2: Any, swid: Any) -> tuple[str, str] | None:
    """The pair as ESPN wants it (``SWID`` in braces, upper case), or None when either does not look like ESPN's."""
    s2 = str(espn_s2 or "").strip()
    m = _SWID.match(str(swid or "").strip())
    if not m or not _S2.match(s2):
        return None
    return s2, "{" + m.group(1).upper() + "}"


def digest(pair: tuple[str, str] | None) -> str | None:
    if not pair:
        return None
    return hmac.new(_DIGEST_KEY, f"{pair[0]}|{pair[1]}".encode(), hashlib.sha256).hexdigest()[:32]


@contextlib.contextmanager
def using_cookies(pair: tuple[str, str] | None) -> Iterator[None]:
    """``AUTH`` for the block (the API's middleware, and tests). The switch off: nothing is set."""
    token = AUTH.set(pair if (pair and private_enabled()) else None)
    try:
        yield
    finally:
        AUTH.reset(token)


def current_auth() -> tuple[str, str] | None:
    pair = AUTH.get()
    return pair if (pair and private_enabled()) else None


# ================================================================================================ trimming
# ESPN's answers carry far more than we read: a roster entry's player has every stat line of the season, rankings,
# outlooks and ownership (espn-api's own test data: one league's week-1 rosters are 17 MB of JSON). Only the fields
# the adapter reads are kept in the cache (the server has 512 MB: docs/DEPLOY.md § Memory).
PLAYER_KEEP = ("id", "fullName", "firstName", "lastName", "defaultPositionId", "eligibleSlots", "proTeamId",
               "injuryStatus", "injured", "active")
TEAM_KEEP = ("id", "abbrev", "name", "location", "nickname", "owners", "primaryOwner", "record", "playoffSeed",
             "waiverRank", "transactionCounter", "divisionId", "points")
SIDE_KEEP = ("teamId", "totalPoints", "pointsByScoringPeriod")
TOP_KEEP = ("id", "seasonId", "scoringPeriodId", "segmentId", "gameId", "status", "settings", "members", "_synthetic")


def _pick(d: Any, keep: tuple[str, ...]) -> dict:
    return {k: d[k] for k in keep if isinstance(d, Mapping) and k in d}


def _player(p: Any) -> dict:
    return _pick(p, PLAYER_KEEP)


def trim(kind: str, data: dict) -> dict:
    """The answer with only what ``espn_leagues`` reads (the rest dropped before it is cached)."""
    out = _pick(data, TOP_KEEP)
    if kind == "teams":
        out["teams"] = [_pick(t, TEAM_KEEP) for t in data.get("teams") or [] if isinstance(t, Mapping)]
    elif kind == "rosters":
        teams = []
        for t in data.get("teams") or []:
            if not isinstance(t, Mapping):
                continue
            ents = []
            for e in ((t.get("roster") or {}).get("entries") or []):
                if not isinstance(e, Mapping):
                    continue
                pe = e.get("playerPoolEntry") or {}
                ents.append({"playerId": e.get("playerId", pe.get("id")), "lineupSlotId": e.get("lineupSlotId"),
                             "acquisitionType": e.get("acquisitionType"),
                             "playerPoolEntry": {"id": pe.get("id"), "player": _player(pe.get("player"))}})
            teams.append({"id": t.get("id"), "roster": {"entries": ents}})
        out["teams"] = teams
    elif kind == "schedule":
        out["schedule"] = [{**_pick(m, ("id", "matchupPeriodId", "winner", "playoffTierType")),
                            **{s: _pick(m[s], SIDE_KEEP) for s in ("home", "away") if isinstance(m.get(s), Mapping)}}
                           for m in data.get("schedule") or [] if isinstance(m, Mapping)]
    elif kind == "transactions":
        out["transactions"] = [{**_pick(t, ("id", "type", "status", "teamId", "scoringPeriodId", "processDate",
                                            "acceptedDate", "proposedDate", "bidAmount")),
                                "items": [_pick(i, ("type", "playerId", "fromTeamId", "toTeamId"))
                                          for i in t.get("items") or [] if isinstance(i, Mapping)]}
                               for t in data.get("transactions") or [] if isinstance(t, Mapping)]
    elif kind == "free_agents":
        out["players"] = [{**_pick(p, ("id", "onTeamId", "status")), "player": _player(p.get("player"))}
                          for p in data.get("players") or [] if isinstance(p, Mapping)]
    return out


# ================================================================================================ the client
class ESPN:
    """Read-only ESPN fantasy football client (see the module docstring). ``fetch`` (tests): ``(url, headers) ->
    (HTTP status, body text)``."""

    def __init__(self, fixtures: str | Path | None = None, season: int | None = None, base: str | None = None,
                 timeout: float = 10.0, *, clock: Callable[[], float] = time.monotonic,
                 bucket: TokenBucket | None = None,
                 fetch: Callable[[str, dict[str, str]], tuple[int, str]] | None = None) -> None:
        fx = fixtures if fixtures is not None else os.environ.get(FIXTURES_ENV)
        self.fixtures = Path(fx) if fx else None
        self._season = int(season) if season else None
        self.base = (base or os.environ.get(API_ENV) or ESPN_API).rstrip("/")
        self.timeout = timeout
        self.clock = clock
        self.bucket = bucket or TokenBucket(_per_minute(), clock=clock)
        self._fetch = fetch
        self.calls = 0
        self.stale_served = 0
        self.last_error: str | None = None             # "mRoster: HTTP 500" — what /api/status shows (no cookies, no query)
        self._backoff_until = 0.0
        self._cache: dict[str, tuple[float, float, str, Any]] = {}
        self._read_at: dict[str, float] = {}
        self.wall: Callable[[], float] = time.time
        # (league id, season) -> {"public": bool | None, "readers": digests that read it}; never the cookies
        self.access: dict[tuple[str, int], dict] = {}
        self._lock = threading.Lock()

    @property
    def season(self) -> int:
        return self._season or season_now()

    def season_of(self, season: int | None) -> int:
        return int(season) if season else self.season

    # ------------------------------------------------------------------ the one read
    def url(self, league_id: str, season: int, view: str, week: int | None = None) -> str:
        q: list[tuple[str, str]] = [("view", view)]
        if week is not None:
            q.append(("scoringPeriodId", str(int(week))))
        return f"{self.base}/seasons/{int(season)}/segments/0/leagues/{league_id}?{urllib.parse.urlencode(q)}"

    def _http(self, url: str, headers: dict[str, str]) -> tuple[int, str]:
        if self._fetch is not None:
            return self._fetch(url, headers)
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:  # noqa: S310 - a fixed https host
                return int(r.status), r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            return int(exc.code), ""
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ESPNUnavailable(f"ESPN {self._redact(url)}: {type(exc).__name__}") from exc

    @staticmethod
    def _redact(url: str) -> str:
        return url.split("?", 1)[0]

    def _fixture(self, league_id: str, kind: str, week: int | None, auth: tuple[str, str] | None) -> tuple[int, str]:
        assert self.fixtures is not None
        d = self.fixtures / league_id
        if not d.is_dir():
            return 404, ""
        if (d / "_private").exists() and not auth:
            return 401, ""
        name = VIEW_OF[kind] + (f"_{int(week)}" if kind == "transactions" and week is not None else "")
        f = d / f"{name}.json"
        if not f.exists():
            raise ESPNUnavailable(f"no fixture {f}")
        return 200, f.read_text()

    def _get(self, kind: str, league_id: str, season: int, week: int | None = None,
             filt: Mapping | None = None) -> dict:
        lid = check_league(league_id)
        if not enabled():
            raise switched_off(lid)
        season = self.season_of(season)
        auth = current_auth()
        dg = digest(auth)
        url = self.url(lid, season, VIEW_OF[kind], week)
        key = url + (f"|f={json.dumps(filt, sort_keys=True)}" if filt else "") + (f"|a={dg}" if dg else "")
        now = self.clock()
        with self._lock:
            hit = self._cache.get(key)
        if hit is not None and hit[0] > now:
            return hit[3]
        if now < self._backoff_until or not self.bucket.take():
            if hit is not None:
                self.stale_served += 1
                return hit[3]
            raise ESPNBusy("busy, try again in a minute")
        self.calls += 1
        try:
            if self.fixtures is not None and self._fetch is None:
                status, text = self._fixture(lid, kind, week, auth)
            else:
                headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
                if filt:
                    headers["x-fantasy-filter"] = json.dumps(filt)
                if auth:
                    headers["Cookie"] = f"espn_s2={auth[0]}; SWID={auth[1]}"
                status, text = self._http(url, headers)
        except ESPNUnavailable as exc:
            self.last_error = f"{VIEW_OF[kind]}: {str(exc).rsplit(': ', 1)[-1]}"
            if hit is not None:
                self.stale_served += 1
                return hit[3]
            raise
        if status == 429:
            self._backoff_until = self.clock() + 60
            if hit is not None:
                self.stale_served += 1
                return hit[3]
            raise ESPNBusy("busy, try again in a minute")
        if status in (401, 403):
            with self._lock:
                self.access.setdefault((lid, season), {"public": None, "readers": set()})["public"] = False
            raise LeaguePrivate(lid, with_cookies=bool(auth))
        if status == 404:
            raise unknown_league(lid, season)
        if status != 200:
            self.last_error = f"{VIEW_OF[kind]}: HTTP {status}"
            if hit is not None:
                self.stale_served += 1
                return hit[3]
            raise ESPNUnavailable(f"ESPN {self._redact(url)}: HTTP {status}")
        try:
            data = json.loads(text or "null")
        except json.JSONDecodeError as exc:
            self.last_error = f"{VIEW_OF[kind]}: not JSON"
            raise ESPNUnavailable(f"ESPN {VIEW_OF[kind]}: not JSON") from exc
        if isinstance(data, list):                  # espn-api: a list answer is the league in a list
            data = data[0] if data and isinstance(data[0], dict) else {}
        if not isinstance(data, dict):
            self.last_error = f"{VIEW_OF[kind]}: not a league"
            raise ESPNUnavailable(f"ESPN {VIEW_OF[kind]}: not a league")
        self._note_access(lid, season, data, dg)
        data = trim(kind, data)
        with self._lock:
            self._cache[key] = (now + TTL_S[kind], now, kind, data)
            self._read_at[f"{kind}|{lid}|{season}"] = self.wall()
        return data

    def _note_access(self, lid: str, season: int, data: Mapping, dg: str | None) -> None:
        public = (data.get("settings") or {}).get("isPublic") if isinstance(data.get("settings"), Mapping) else None
        with self._lock:
            a = self.access.setdefault((lid, season), {"public": None, "readers": set()})
            if public is not None:
                a["public"] = bool(public)
            if dg:
                a["readers"].add(dg)

    def require_access(self, league_id: str, season: int | None = None) -> None:
        """Raise ``LeaguePrivate`` when this league is known to be private and this request may not see it (the memo
        caches above this client key by league only: IK-3 calls this first). No cookies: refused. Cookies that have
        not read it yet: one read of the settings with them decides (ESPN answers or says 401)."""
        lid, season = check_league(league_id), self.season_of(season)
        with self._lock:
            a = self.access.get((lid, season))
            if not a or a.get("public") is not False:
                return
            readers = set(a.get("readers") or ())
        dg = digest(current_auth())
        if dg is None:
            raise LeaguePrivate(lid)
        if dg not in readers:
            self.settings(lid, season)                 # with this request's cookies: 401 -> LeaguePrivate

    def fetched_at(self, kind: str, league_id: str, season: int | None = None) -> float | None:
        with self._lock:
            return self._read_at.get(f"{kind}|{check_league(league_id)}|{self.season_of(season)}")

    # ------------------------------------------------------------------ the calls
    def settings(self, league_id: str, season: int | None = None) -> dict:
        return self._get("settings", league_id, self.season_of(season))

    def status(self, league_id: str, season: int | None = None) -> dict:
        return self._get("status", league_id, self.season_of(season))

    def teams(self, league_id: str, season: int | None = None) -> dict:
        return self._get("teams", league_id, self.season_of(season))

    def rosters(self, league_id: str, season: int | None = None, week: int | None = None) -> dict:
        return self._get("rosters", league_id, self.season_of(season), week)

    def schedule(self, league_id: str, season: int | None = None) -> dict:
        return self._get("schedule", league_id, self.season_of(season))

    def transactions(self, league_id: str, season: int | None, week: int) -> dict:
        return self._get("transactions", league_id, self.season_of(season), int(week), TRANSACTION_FILTER)

    def free_agents(self, league_id: str, season: int | None, week: int | None, limit: int = FREE_AGENT_LIMIT) -> dict:
        return self._get("free_agents", league_id, self.season_of(season), week, free_agent_filter(limit))

    def stats(self) -> dict:
        now = self.clock()
        with self._lock:
            entries = list(self._cache.values())
        kinds: dict[str, dict] = {}
        for exp, fetched, kind, _ in entries:
            k = kinds.setdefault(kind, {"entries": 0, "fresh": 0, "oldest_s": 0.0, "ttl_s": TTL_S[kind]})
            k["entries"] += 1
            k["fresh"] += int(exp > now)
            k["oldest_s"] = round(max(k["oldest_s"], now - fetched), 1)
        return {"mode": "fixtures" if self.fixtures is not None else "live", "season": self.season, "calls": self.calls,
                "stale_served": self.stale_served, "private_enabled": private_enabled(), "enabled": enabled(),
                "last_error": self.last_error,
                "bucket": {"tokens": round(self.bucket.tokens(), 1), "capacity": self.bucket.capacity,
                           "per_minute": self.bucket.per_minute, "refused": self.bucket.refused},
                "cache": kinds}
