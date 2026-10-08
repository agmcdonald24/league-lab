"""Wave I-Q (IQ-2): the starter-source study's pure part (scripts/analysis/iq2_starter_source.py; docs/METRICS.md §
"Who starts"). Hand-built team-games, no database.

* the truth is the team's dropback leader; a stale listing's QB took no dropback; the newest played game before the
  week is read, never the week's own;
* the depth chart is read as of the newest snapshot strictly before kickoff;
* each candidate's pick (S1 depth QB1, S2 first available, S3 listing unless ruled out, S4 two sources agree), the
  rule's numbers and verdict, the unclear triggers U0 - U3.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "analysis"))
import iq2_starter_source as Q  # noqa: E402

K = "2025-10-{d:02d}T17:00:00Z"


def games():
    # SEA: weeks 3-5, Lock listed every week (stale: Darnold leads 3-5); BUF: Allen listed and leads; ARI: week 6 the
    # listing (Brissett) is right while the chart keeps the hurt starter (Murray, Questionable, INA on game day)
    rows = [(2025, 3, "g3s", K.format(d=1), "SEA", "lock"), (2025, 4, "g4s", K.format(d=8), "SEA", "lock"),
            (2025, 5, "g5s", K.format(d=15), "SEA", "lock"),
            (2025, 4, "g4b", K.format(d=8), "BUF", "allen"), (2025, 5, "g5b", K.format(d=15), "BUF", "allen"),
            (2025, 5, "g5a", K.format(d=15), "ARI", "brissett"), (2025, 6, "g6a", K.format(d=22), "ARI", "brissett")]
    return pd.DataFrame(rows, columns=["season", "week", "game_id", "kickoff_at", "team", "listed_id"])


def dropbacks():
    rows = [("g3s", "SEA", "darnold", 40.0), ("g4s", "SEA", "darnold", 30.0), ("g5s", "SEA", "darnold", 35.0),
            ("g4b", "BUF", "allen", 33.0), ("g5b", "BUF", "allen", 31.0), ("g5b", "BUF", "backup", 2.0),
            ("g5a", "ARI", "brissett", 30.0), ("g6a", "ARI", "brissett", 28.0)]
    return pd.DataFrame(rows, columns=["game_id", "team", "gsis_id", "dropbacks"])


def depth():
    rows = [("SEA", "2025-09-30T06:00:00Z", "lock", 1, 9), ("SEA", "2025-09-30T06:00:00Z", "darnold", 2, 9),
            ("SEA", "2025-10-07T06:00:00Z", "darnold", 1, 9), ("SEA", "2025-10-07T06:00:00Z", "lock", 2, 9),
            ("SEA", "2025-10-15T18:00:00Z", "milroe", 1, 9),        # after week 5's kickoff: never read for it
            ("BUF", "2025-10-07T06:00:00Z", "allen", 1, 9),
            ("ARI", "2025-10-14T06:00:00Z", "murray", 1, 9), ("ARI", "2025-10-14T06:00:00Z", "brissett", 2, 9)]
    return pd.DataFrame(rows, columns=["team", "snapshot_at", "gsis_id", "pos_rank", "pos_slot"])


def frame(report=(), roster=()):
    g = Q.team_games(games(), dropbacks())
    d = dropbacks()
    dropped = set(zip(d["team"], d["gsis_id"], d["game_id"], strict=True))
    gid = g[g["played"]].set_index(["team", "season", "week"])["game_id"].to_dict()
    g["listed_last_dropped"] = [(t, L, gid.get((t, s, lw))) in dropped if lw == lw else False
                                for t, L, s, lw in zip(g["team"], g["listed_id"], g["season"], g["last_week"], strict=True)]
    g["depth"] = Q.depth_before(g, depth())
    rep = pd.DataFrame(list(report), columns=["season", "week", "gsis_id", "report_status"])
    ros = pd.DataFrame(list(roster), columns=["season", "week", "gsis_id", "roster_status"])
    return Q.triggers(Q.picks(g, Q.ruled_out(g, rep, ros)))


def test_truth_stale_and_the_newest_game_before_the_week():
    g = frame().set_index(["team", "week"])
    assert g.loc[("SEA", 3), "truth_id"] == "darnold" and bool(g.loc[("SEA", 3), "stale"])
    assert pd.isna(g.loc[("SEA", 3), "last_id"])                        # no game before week 3
    assert g.loc[("SEA", 5), "last_id"] == "darnold" and g.loc[("SEA", 5), "last_week"] == 4
    assert not bool(g.loc[("BUF", 5), "stale"]) and not bool(g.loc[("BUF", 5), "in_game_change"])


def test_the_depth_chart_is_read_before_kickoff():
    g = frame().set_index(["team", "week"])
    assert g.loc[("SEA", 3), "depth"] == ["lock", "darnold"]            # 2025-09-30, before 2025-10-01's kickoff
    assert g.loc[("SEA", 4), "depth"] == ["darnold", "lock"]            # 2025-10-07, before 2025-10-08
    assert g.loc[("SEA", 5), "depth"] == ["darnold", "lock"]            # not the 10-15 18:00 one, after the 17:00 kickoff
    assert g.loc[("ARI", 6), "depth"] == ["murray", "brissett"]


def test_each_candidate_and_the_rule():
    # Murray is Questionable (never "out") and INA on game day (never read): the chart's first available is Murray
    g = frame(report=[(2025, 6, "murray", "Questionable")], roster=[(2025, 6, "murray", "INA")]).set_index(["team", "week"])
    assert g.loc[("SEA", 5), "S1"] == "darnold" and g.loc[("SEA", 5), "S2"] == "darnold"
    assert g.loc[("SEA", 5), "S3"] == "lock"                            # Lock is not ruled out: the listing stands
    assert g.loc[("SEA", 5), "S4"] == "darnold"                         # the chart's first available = last game's leader
    assert g.loc[("ARI", 6), "S2"] == "murray" and g.loc[("ARI", 6), "S4"] == "brissett"   # S4 needs the last game too
    s = Q.score(frame(), "S4")             # SEA week 3: the chart still had Lock first and no game before it: still wrong
    assert (s["team_games"], s["stale"], s["stale_fixed"], s["fixed"], s["newly_broken"], s["still_wrong"]) == (7, 3, 2, 2, 0, 1)
    assert s["a_acc"] and s["b_fix60"] and s["c_break_1_in_6"] and s["passes_abc"]
    # ruled out: the report's Out, or a reserve list -> S3 falls to the chart's first available
    g2 = frame(report=[(2025, 5, "lock", "Out")]).set_index(["team", "week"])
    assert g2.loc[("SEA", 5), "S3"] == "darnold"
    g3 = frame(roster=[(2025, 4, "lock", "RES")]).set_index(["team", "week"])
    assert g3.loc[("SEA", 4), "S2"] == "darnold" and g3.loc[("SEA", 4), "S3"] == "darnold"


def test_the_verdict_and_the_triggers():
    s = Q.score(frame(report=[(2025, 6, "murray", "Questionable")]), "S2")
    assert s["newly_broken"] == 2 and s["fixed"] == 2 and not s["c_break_1_in_6"]   # ARI weeks 5-6: 2 > 2 / 6
    assert s["acc"] == s["acc_listing"] and s["a_acc"] and not s["passes_abc"]
    t = Q.trigger_table(frame()).set_index("trigger")
    # U0: SEA weeks 4-5 (Lock listed, Darnold led the game before); U1: SEA weeks 4-5 and ARI weeks 5-6 (the chart's
    # Murray against the listed Brissett); SEA week 3 is stale and nothing before kickoff says so
    assert t.loc["U0", "flags"] == 2 and t.loc["U1", "flags"] == 4 and t.loc["U2", "flags"] == 4 and t.loc["U3", "flags"] == 2
    assert t.loc["U0", "stale_caught"] == 2 and t.loc["U1", "flags_not_stale"] == 2 and t.loc["U0", "stale"] == 3
