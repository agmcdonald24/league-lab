"""IQ-4 (Wave I-Q): ``league-lab audit-lists`` — the trust guard. Every list a stranger can open without a league
(this week and rest of season; QB RB WR TE K DEF; Half PPR, PPR and Standard: the reference keys ``ref:half``,
``ref:ppr``, ``ref:std``; the free calculator's values rank as the rest of season to the last regular-season week does)
is read the way the site builds it (``anyleague.price_week`` for this week, ``anyleague.ros_table`` for the rest of the
season, the reference scorings and the typical league's slots ``refleague`` uses), and the rows a knowledgeable reader
would laugh at are printed, each with the reason it was flagged:

* **coverage** (the first line of the report): every team with a game in a list's window has its players in it; a
  team missing from a list is the bug the PO found on 7 Oct (the bye week);
* **projection against what they have scored**: a top-12 (QB, TE, K, DEF) / top-24 (RB, WR) projection whose points
  per game this season (3+ games) rank below ``FAR`` x that cut, and a top-5 scorer (3+ games) outside the list's top
  15 / 30 — unless his status explains it (Out, a reserve list, a bye this week), which the row then says;
* **status**: a player ruled Out / on a reserve list projected above a backup's ``OUT_FLOOR`` this week; a team with no
  quarterback above ``QB_STARTER`` this week, or with two; a quarterback projected as the starter who took no dropback
  in his team's last game while another did, and the reverse (IQ-2's ``analytics.mart_starter_check`` is printed when
  it exists; the section says so when it does not);
* **agreement**: per position, among the top 24 by this week's projection, the rank correlation of this week with the
  later weeks' mean (the guard's number, ``assert_rest_of_season_follows_the_market_week``);
* **rank moves**: rest-of-season moves of more than ``RANK_MOVE`` places since the previous run with no game played and
  no status change between. Yesterday's board is not kept in the database (``ops.projections`` holds the newest fit
  of an unplayed week only): the previous run's ranks are read from ``logs/list_audit_ranks.json`` when it is there.

Exit code 0 always (never a nightly stop): a compact markdown report on stdout and in ``logs/list_audit.md``. Read
only (the database is never written). The rules are pure functions of frames (``tests/test_iq4_audit.py``).
"""

from __future__ import annotations

import json
import logging
import math
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from . import availability_gate as AG  # ---- IS-1: sits() for the first rule

log = logging.getLogger(__name__)
Query = Callable[[str, tuple], pd.DataFrame]

REFERENCES = {"ref:half": ("scrubs", "Half PPR"), "ref:ppr": ("ppr", "PPR"), "ref:std": ("standard", "Standard")}
SLOTS = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "K", "DEF"] + ["BN"] * 6     # refleague's typical league
POSITIONS = ("QB", "RB", "WR", "TE", "K", "DEF")
TOP = {"QB": 12, "TE": 12, "K": 12, "DEF": 12, "RB": 24, "WR": 24}      # a starter's cut at the position
DEPTH = {"QB": 15, "TE": 15, "K": 15, "DEF": 15, "RB": 30, "WR": 30}    # where a top-5 scorer must be
FAR = 2.0               # "far below": points-per-game rank beyond twice the cut (25th+ QB, 49th+ RB)
MIN_GAMES = 3
TOP_SCORERS = 5
OUT_FLOOR = 3.0         # a backup's projection: an Out / reserve player above it this week is flagged
QB_STARTER = 10.0       # a quarterback projected above it this week is projected as a starter
AGREE_N = 24
AGREE_FLOOR = {"QB": 0.55, "RB": 0.65, "WR": 0.65, "TE": 0.65}          # the guard's floors (K / DEF: none)
RANK_MOVE = 10
OUT_REPORT = {"Out", "Doubtful"}
RESERVE = {"RES", "IR", "PUP", "SUS", "NON", "EXE", "NFI"}
MAX_ROWS = 12           # per section and scoring, the rest counted
RANKS_FILE = "list_audit_ranks.json"


@dataclass
class Board:
    """One list: ``rows`` has player_key, gsis_id, player_name, position, team, proj, rank (by position), status, bye."""
    key: str
    label: str
    view: str               # "week" | "season" | "value"
    position: str
    rows: pd.DataFrame
    window: tuple[int, int] | None = None
    playing: frozenset[str] | None = None      # the teams with a game this week (a bye explains a missing player)


@dataclass
class Report:
    week: int | None
    season: int
    lines: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)

    def add(self, *ls: str) -> None:
        self.lines.extend(ls)


# ------------------------------------------------------------------------------------------------ the rules
def status_of(report_status, roster_status) -> str | None:
    """Out / Doubtful / a reserve list in words, else None (Questionable explains nothing)."""
    rs = str(report_status or "").strip()
    if rs in OUT_REPORT:
        return rs
    ro = str(roster_status or "").strip().upper()
    if ro in RESERVE:
        return "on a reserve list" if ro != "IR" else "on injured reserve"
    return None


def missing_teams(rows: pd.DataFrame, teams: Iterable[str]) -> list[str]:
    """Teams expected in a list (a game in its window) that have no player in it."""
    have = {str(t) for t in rows["team"].dropna()} if len(rows) else set()
    return sorted(set(teams) - have)


def ppg_ranks(points: pd.DataFrame) -> pd.DataFrame:
    """``points``: player_key, position, week, points (one row per game played this season) -> player_key, position,
    games, ppg, ppg_rank (by position among players with ``MIN_GAMES``+ games; NULL below that)."""
    if points.empty:
        return pd.DataFrame(columns=["player_key", "position", "games", "ppg", "ppg_rank"])
    g = points.groupby(["player_key", "position"], as_index=False).agg(games=("points", "size"), ppg=("points", "mean"))
    if "player_name" in points and "team" in points:          # his name and newest team, for a row not in a list
        last = points.sort_values("week").drop_duplicates("player_key", keep="last").set_index("player_key")
        g["player_name"] = g["player_key"].map(last["player_name"])
        g["team"] = g["player_key"].map(last["team"])
    ok = g[g["games"] >= MIN_GAMES].sort_values(["position", "ppg", "player_key"], ascending=[True, False, True])
    g["ppg_rank"] = (ok.groupby("position").cumcount() + 1).reindex(g.index)
    return g


def against_scored(board: Board, ppg: pd.DataFrame) -> tuple[list[dict], list[dict]]:
    """(flagged, explained): a top-``TOP`` projection whose points-per-game rank is beyond ``FAR`` x the cut; a top-5
    scorer outside the top ``DEPTH`` (or not in the list) — explained when his status or a bye says why."""
    pos = board.position
    r = board.rows.merge(ppg[ppg["position"] == pos][["player_key", "games", "ppg", "ppg_rank"]], on="player_key", how="left")
    cut, far = TOP[pos], FAR * TOP[pos]
    flagged, explained = [], []
    top = r[r["rank"] <= cut]
    for x in top.itertuples():
        if pd.notna(x.ppg_rank) and x.ppg_rank > far:
            flagged.append({"kind": "projected high, scoring low", "player": x.player_name, "team": x.team,
                            "rank": int(x.rank), "proj": x.proj, "ppg": x.ppg, "ppg_rank": int(x.ppg_rank),
                            "games": int(x.games), "why": f"#{int(x.rank)} here, #{int(x.ppg_rank)} in points per game "
                                                          f"({x.ppg:.1f} in {int(x.games)} games)"})
    best = ppg[(ppg["position"] == pos) & ppg["ppg_rank"].le(TOP_SCORERS)]
    by_key = r.set_index("player_key")
    for b in best.itertuples():
        row = by_key.loc[b.player_key] if b.player_key in by_key.index else None
        if isinstance(row, pd.DataFrame):
            row = row.iloc[0]
        rank = None if row is None or pd.isna(row["rank"]) else int(row["rank"])
        if rank is not None and rank <= DEPTH[pos]:
            continue
        name = row["player_name"] if row is not None else (_s(getattr(b, "player_name", None)) or b.player_key)
        team = row["team"] if row is not None else _s(getattr(b, "team", None))
        if row is not None:
            st = _s(row.get("status")) or ("a bye this week" if _yes(row.get("bye")) else None)
        else:                       # not in the list: a bye this week explains it on this week's list
            st = "a bye this week" if board.playing is not None and team and team not in board.playing else None
        item = {"kind": "top scorer ranked low", "player": name, "team": team, "rank": rank, "ppg": b.ppg,
                "ppg_rank": int(b.ppg_rank), "games": int(b.games),
                "why": f"#{int(b.ppg_rank)} in points per game ({b.ppg:.1f} in {int(b.games)} games), "
                       + (f"#{rank} here" if rank is not None else "not in the list")}
        if st:
            item["why"] += f" — explained: {st}"
            explained.append(item)
        else:
            flagged.append(item)
    return flagged, explained


# ---- IR-1 (Wave I-R): the site's definition and sources (league_lab.availability_gate), the report's first rule
def still_ranked(boards: list[Board], st: Mapping[str, dict]) -> list[dict]:
    """Players who cannot play and are still ranked or valued: this week's lists, a player who cannot play this week
    with a projection above 0; the season's lists and the free calculator's values, a player out indefinitely with
    rest-of-season points above 0."""
    out = []
    for b in boards:
        want = "sits" if b.view == "week" else "out_indefinitely"          # ---- IS-1: the week asks sits()
        if b.rows is None or b.rows.empty or "gsis_id" not in b.rows:
            continue
        for x in b.rows.itertuples():
            s = st.get(getattr(x, "gsis_id", None)) if isinstance(getattr(x, "gsis_id", None), str) else None
            hit = AG.sits(s) if want == "sits" else bool((s or {}).get(want))
            if s is None or not hit or pd.isna(x.proj) or float(x.proj) <= 0:
                continue
            title = {"week": "this week", "season": "rest of season", "value": "calculator value"}[b.view]
            out.append({"player": x.player_name, "team": x.team, "position": x.position, "view": title, "label": b.label,
                        "proj": float(x.proj), "rank": int(x.rank), "why": s.get("why")})
    return out
# ---- end IR-1


def out_but_projected(week_rows: pd.DataFrame) -> list[dict]:
    """A player ruled Out / Doubtful / on a reserve list projected above ``OUT_FLOOR`` this week."""
    out = []
    for x in week_rows.itertuples():
        st = _s(getattr(x, "status", None))
        if st and pd.notna(x.proj) and float(x.proj) > OUT_FLOOR:
            out.append({"player": x.player_name, "team": x.team, "position": x.position, "proj": float(x.proj),
                        "why": f"{st}, projected {float(x.proj):.1f} (above a backup's {OUT_FLOOR:.0f})"})
    return out


def qbs_per_team(qb_rows: pd.DataFrame, teams_playing: Iterable[str]) -> list[dict]:
    """A team (with a game this week) with no quarterback above ``QB_STARTER``, or with two or more."""
    out = []
    for t in sorted(teams_playing):
        g = qb_rows[(qb_rows["team"] == t) & qb_rows["proj"].gt(QB_STARTER)]
        if len(g) == 0:
            top = qb_rows[qb_rows["team"] == t].sort_values("proj", ascending=False).head(1)
            who = (f"best {top['player_name'].iloc[0]} {float(top['proj'].iloc[0]):.1f}" if len(top) else "no quarterback")
            out.append({"team": t, "why": f"no quarterback above {QB_STARTER:.0f} ({who})"})
        elif len(g) >= 2:
            names = ", ".join(f"{n} {p:.1f}" for n, p in zip(g["player_name"], g["proj"], strict=True))
            out.append({"team": t, "why": f"{len(g)} quarterbacks above {QB_STARTER:.0f}: {names}"})
    return out


def starter_vs_last_game(qb_rows: pd.DataFrame, last: pd.DataFrame) -> list[dict]:
    """``last``: team, gsis_id, player_name, dropbacks, week — every quarterback of the team's newest played game.
    The projected starter (the team's best projection above ``QB_STARTER``) took no dropback there while another
    did; or the quarterback who led them is not the projected starter (and is not ruled out)."""
    out = []
    for t, g in qb_rows[qb_rows["proj"].gt(QB_STARTER)].sort_values("proj", ascending=False).groupby("team", sort=True):
        s = g.iloc[0]
        lg = last[last["team"] == t]
        if lg.empty or float(lg["dropbacks"].max() or 0) <= 0:
            continue
        lead = lg.sort_values("dropbacks", ascending=False).iloc[0]
        wk = int(lead["week"])
        mine = lg[lg["gsis_id"] == s["gsis_id"]]
        took = float(mine["dropbacks"].iloc[0]) if len(mine) else 0.0
        if lead["gsis_id"] == s["gsis_id"]:
            continue
        lead_row = qb_rows[qb_rows["gsis_id"] == lead["gsis_id"]]
        lead_status = _s(lead_row["status"].iloc[0]) if len(lead_row) and "status" in lead_row else None
        if took <= 0:
            why = (f"projected starter {s['player_name']} ({float(s['proj']):.1f}) took no dropback in week {wk}; "
                   f"{lead['player_name']} led them ({int(lead['dropbacks'])})")
        elif not lead_status:
            why = (f"{lead['player_name']} led week {wk}'s dropbacks ({int(lead['dropbacks'])}) but "
                   f"{s['player_name']} is projected as the starter ({float(s['proj']):.1f}; {int(took)} dropbacks)")
        else:
            continue
        out.append({"team": t, "why": why})
    return out


def agreement(season_rows: pd.DataFrame, week: int) -> float | None:
    """Among the top ``AGREE_N`` by this week's projection, the rank correlation of this week with the later weeks'
    mean (``weeks``: [[week, points], …] per row). None with fewer than 8 players."""
    this, later = [], []
    for ws in season_rows["weeks"]:
        d = {int(w): float(p) for w, p in (ws or [])}
        if week in d and len(d) > 1:
            this.append(d[week])
            later.append(np.mean([p for w, p in d.items() if w != week]))
    if len(this) < 8:
        return None
    f = pd.DataFrame({"this": this, "later": later}).sort_values("this", ascending=False).head(AGREE_N)
    return float(f["this"].rank().corr(f["later"].rank()))


def rank_moves(today: Mapping[str, dict], before: Mapping[str, dict]) -> list[dict]:
    """``{list key: {player_key: {rank, games, status, name}}}`` now and at the previous run -> moves of more than
    ``RANK_MOVE`` places with no game played and no status change between."""
    out = []
    for lk, rows in today.items():
        prev = before.get(lk) or {}
        for pk, r in rows.items():
            p = prev.get(pk)
            if not p or r.get("rank") is None or p.get("rank") is None:
                continue
            move = int(p["rank"]) - int(r["rank"])
            if abs(move) <= RANK_MOVE or r.get("games") != p.get("games") or r.get("status") != p.get("status"):
                continue
            out.append({"list": lk, "player": r.get("name"), "why": f"#{p['rank']} → #{r['rank']} "
                        f"({'up' if move > 0 else 'down'} {abs(move)}) with no game and no status change"})
    return out


# ------------------------------------------------------------------------------------------------ the data
def _yes(v) -> bool:
    return v is not None and not (isinstance(v, float) and math.isnan(v)) and bool(v)


def _s(v) -> str | None:
    return v if isinstance(v, str) and v else None


def _num(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def decision_week(query: Query, season: int) -> int | None:
    """The first regular-season week whose last game has not kicked off (``lib.ui.current_week``'s rule)."""
    from . import clock
    g = query("""select week, max(kickoff_at) as last from analytics.dim_game
                 where season = %s and season_type = 'REG' group by week order by week""", (int(season),))
    now = pd.Timestamp(clock.now())
    now = now.tz_localize("UTC") if now.tzinfo is None else now.tz_convert("UTC")
    for r in g.itertuples():
        last = pd.Timestamp(r.last)
        last = last.tz_localize("UTC") if last.tzinfo is None else last.tz_convert("UTC")
        if last > now:
            return int(r.week)
    return None


def reference_scorings(query: Query) -> dict[str, dict[str, float]]:
    from . import anyleague as A
    out = {}
    for r in query(A.REFERENCES_SQL, ()).itertuples():
        sc = r.scoring_settings if isinstance(r.scoring_settings, dict) else json.loads(r.scoring_settings or "{}")
        out[r.name] = {k: float(v) for k, v in sc.items() if v is not None}
    return out


def week_boards(query: Query, key: str, label: str, scoring: Mapping[str, float], season: int, week: int) -> list[Board]:
    from . import anyleague as A
    pr = A.price_week(query, key, scoring, SLOTS, season, week, cache=False)
    st = pr.board.status
    pos = pr.board.line["position"].reindex(pr.proj.index)
    sk = pd.DataFrame({"player_key": pr.proj.index, "gsis_id": pr.proj.index, "position": pos.to_numpy(),
                       "proj": pr.proj.to_numpy(dtype=float)})
    for c in ("team", "player_name", "report_status", "roster_status"):
        sk[c] = st[c].reindex(pr.proj.index).to_numpy() if c in st else None
    frames = [sk]
    for p, kd in pr.kd.items():
        if not kd.empty:
            frames.append(pd.DataFrame({"player_key": kd["unit_id"].astype(str).to_numpy(), "gsis_id": None, "position": p,
                                        "proj": pd.to_numeric(kd["proj_points"], errors="coerce").to_numpy(dtype=float),
                                        "team": kd["team"].to_numpy(), "player_name": kd["player_name"].to_numpy(),
                                        "report_status": kd.get("report_status"), "roster_status": kd.get("roster_status")}))
    d = pd.concat(frames, ignore_index=True)
    d = d[d["proj"].notna()]
    d["status"] = [status_of(a, b) for a, b in zip(d["report_status"], d["roster_status"], strict=True)]
    d["bye"] = False
    out = []
    for p in POSITIONS:
        g = d[d["position"] == p].sort_values(["proj", "player_key"], ascending=[False, True]).reset_index(drop=True)
        g["rank"] = np.arange(1, len(g) + 1)
        out.append(Board(key, label, "week", p, g, (week, week), frozenset(teams_with_games(query, season, week, week))))
    return out


def season_boards(query: Query, key: str, label: str, scoring: Mapping[str, float], season: int, week: int,
                  last_week: int, view: str) -> list[Board]:
    """The rest of season as Rankings / ``/ros`` show it (``view`` "season": the typical league's playoff window,
    ``ros_window``) or as the free calculator values it ("value": to the last regular-season week)."""
    from . import anyleague as A
    lg = {"league_id": key, "season": str(season), "scoring_settings": dict(scoring), "roster_positions": SLOTS,
          "settings": {"num_teams": 12, "playoff_week_start": 15, "playoff_teams": 6}}
    if view == "season":
        first, last, pws = A.ros_window(lg, week, last_week)
    else:
        first, last, pws = week, last_week, None
    df = A.ros_table(query, key, lg, first, last, pws)
    if df.empty:
        return [Board(key, label, view, p, pd.DataFrame(columns=["player_key", "team", "rank"]), (first, last))
                for p in POSITIONS]
    d = df[df["is_ranked"].fillna(True).astype(bool)].copy()
    d["proj"] = pd.to_numeric(d["ros_points"], errors="coerce")
    d["weeks"] = d["weeks_json"]
    d["bye"] = [week in [int(w) for w in (b or [])] for b in d["bye_weeks"]]
    d["status"] = [status_of(None, r) for r in d["roster_status"]]
    out = []
    for p in POSITIONS:
        g = d[d["position"] == p].sort_values(["proj", "player_key"], ascending=[False, True]).reset_index(drop=True)
        g["rank"] = np.arange(1, len(g) + 1)
        out.append(Board(key, label, view, p, g, (int(first), int(last))))
    return out


SKILL_POINTS_SQL = """select gsis_id as player_key, player_name, team, position, week, played, completions, attempts, passing_yards,
       passing_tds, passing_interceptions, sacks_suffered, sack_yards_lost, sack_fumbles, sack_fumbles_lost,
       passing_first_downs, passing_2pt_conversions, carries, rushing_yards, rushing_tds, rushing_fumbles,
       rushing_fumbles_lost, rushing_first_downs, rushing_2pt_conversions, receptions, targets, receiving_yards,
       receiving_tds, receiving_fumbles, receiving_fumbles_lost, receiving_first_downs, receiving_2pt_conversions,
       special_teams_tds, fumble_recovery_tds, fumbles_total, fumbles_lost_total, pass_tds_10p, pass_tds_40p,
       pass_tds_50p, rush_tds_10p, rush_tds_40p, rush_tds_50p, rec_tds_10p, rec_tds_40p, rec_tds_50p
from analytics.fct_player_game
where season = %s and season_type = 'REG' and week < %s and played and position = any(%s)"""
KD_POINTS_SQL = """select position, unit_id as player_key, player_name, team, week, out_fg_made_0_19, out_fg_made_20_29, out_fg_made_30_39,
       out_fg_made_40_49, out_fg_made_50p, out_fg_missed, out_fg_missed_0_19, out_fg_missed_20_29, out_fg_missed_30_39,
       out_fg_missed_40_49, out_fg_missed_50p, out_pat_made, out_pat_missed, out_sacks, out_interceptions,
       out_fumble_recoveries, out_forced_fumbles, out_def_tds, out_st_tds, out_safeties, out_blocked_kicks,
       out_points_allowed
from analytics.mart_kd_week where season = %s and week < %s and played"""


def scored(query: Query, season: int, week: int, scoring: Mapping[str, float]) -> pd.DataFrame:
    """Points per game this season (weeks before ``week``), in this scoring: ``ppg_ranks``' frame."""
    from . import kdef
    from .scoring import compute_points_frame
    sk = query(SKILL_POINTS_SQL, (int(season), int(week), ["QB", "RB", "WR", "TE"]))
    frames = []
    if not sk.empty:
        num = (sk.drop(columns=["player_key", "player_name", "team", "position", "week", "played"])
               .apply(pd.to_numeric, errors="coerce").fillna(0.0))
        num["position"] = sk["position"].to_numpy()
        frames.append(pd.DataFrame({"player_key": sk["player_key"], "player_name": sk["player_name"], "team": sk["team"],
                                    "position": sk["position"], "week": sk["week"],
                                    "points": np.asarray(compute_points_frame(num, scoring), dtype=float)}))
    try:
        kd = query(KD_POINTS_SQL, (int(season), int(week)))
    except Exception:  # noqa: BLE001 - no K / DEF mart: those lists are audited without points per game
        kd = pd.DataFrame()
    for p in ("K", "DEF"):
        g = kd[kd["position"] == p].copy() if not kd.empty else pd.DataFrame()
        if g.empty:
            continue
        for c in [c for c in g.columns if c.startswith("out_")]:
            g[c] = pd.to_numeric(g[c], errors="coerce").fillna(0.0).astype(float)
        if p == "DEF":
            g = kdef.with_pa_buckets(g, "out_")
        frames.append(pd.DataFrame({"player_key": g["player_key"].astype(str), "player_name": g["player_name"],
                                    "team": g["team"], "position": p, "week": g["week"],
                                    "points": kdef.price(g, p, scoring, "out_")}))
    return ppg_ranks(pd.concat(frames, ignore_index=True) if frames else pd.DataFrame())


LAST_GAME_SQL = """with last as (
    select team, max(week) as week from analytics.fct_player_game
    where season = %s and season_type = 'REG' and week < %s and played group by team)
select f.team, f.gsis_id, f.player_name, f.week, coalesce(f.dropbacks, f.attempts + coalesce(f.sacks_suffered, 0), 0) as dropbacks
from analytics.fct_player_game f join last l on l.team = f.team and l.week = f.week
where f.season = %s and f.season_type = 'REG' and f.position = 'QB'"""


def teams_with_games(query: Query, season: int, first: int, last: int) -> set[str]:
    from . import anyleague as A
    g = query(A.ROS_GAMES_SQL, (int(season),))
    g = g[(g["week"] >= first) & (g["week"] <= last)]
    return {str(t) for t in pd.concat([g["home_team"], g["away_team"]])}


def _has(query: Query, rel: str) -> bool:
    try:
        r = query("select to_regclass(%s) is not null as ok", (rel,))
        return bool(r["ok"].iloc[0])
    except Exception:  # noqa: BLE001
        return False


# ------------------------------------------------------------------------------------------------ the report
def _fmt(items: list[dict], label: str, extra: Callable[[dict], str] | None = None) -> list[str]:
    lines = []
    for it in items[:MAX_ROWS]:
        who = it.get("player") or it.get("team")
        team = f" ({it['team']})" if it.get("player") and it.get("team") else ""
        lines.append(f"- {label}{who}{team}: {it['why']}" + (extra(it) if extra else ""))
    if len(items) > MAX_ROWS:
        lines.append(f"- … and {len(items) - MAX_ROWS} more")
    return lines


def _group(per_key: dict[str, list[dict]], ident: Callable[[dict], tuple]) -> list[tuple[dict, list[str]]]:
    """The same flag in several scorings, once, with the scorings named."""
    seen: dict[tuple, tuple[dict, list[str]]] = {}
    for label, items in per_key.items():
        for it in items:
            k = ident(it)
            if k not in seen:
                seen[k] = (it, [])
            seen[k][1].append(label)
    return list(seen.values())


def build(query: Query, *, ranks_path: Path | None = None) -> Report:
    from . import clock
    season = int(clock.now().year if clock.now().month >= 3 else clock.now().year - 1)
    week = decision_week(query, season)
    rep = Report(week, season)
    rep.add(f"# List audit — {season}, week {week if week is not None else '(season over)'}",
            f"_Built {pd.Timestamp(clock.now()).strftime('%Y-%m-%d %H:%M UTC')}; every list a visitor can open without a "
            f"league (Half PPR, PPR, Standard; this week and rest of season; the free calculator's values)._", "")
    if week is None:
        rep.add("The regular season is over: nothing to audit.")
        return rep
    # ---- IR-1: the definition the site uses (availability_gate), from the sources the database holds
    gate_st, gate_meta = AG.statuses_from_query(query, season, week)
    # ---- end IR-1
    last_week = int(query("select max(week) as w from analytics.dim_game where season = %s and season_type = 'REG'",
                          (season,))["w"].iloc[0])
    scorings = reference_scorings(query)
    boards: list[Board] = []
    ppg: dict[str, pd.DataFrame] = {}
    for key, (name, label) in REFERENCES.items():
        sc = scorings.get(name)
        if sc is None:
            rep.add(f"- {label}: the reference scoring {name!r} is not on this database — not audited")
            continue
        for fn, args in ((week_boards, (week,)), (season_boards, (week, last_week, "season")),
                         (season_boards, (week, last_week, "value"))):
            try:
                boards += fn(query, key, label, sc, season, *args)
            except Exception as exc:  # noqa: BLE001 - one list failing is a finding, never a stop
                rep.add(f"- {label} {fn.__name__}: could not be built ({exc.__class__.__name__}: {str(exc)[:120]})")
        ppg[label] = scored(query, season, week, sc)

    # ---- IR-1 (Wave I-R): the hard rule, first: nobody who cannot play is ranked or valued
    sr = still_ranked(boards, gate_st)
    names = _group({lb: [it for it in sr if it["label"] == lb] for lb in {it["label"] for it in sr}},
                   lambda it: (it["player"], it["team"], it["view"]))
    n_players = len({(it["player"], it["team"]) for it in sr})
    rep.counts["cannot_play_ranked"] = n_players
    n_cp = sum(1 for v in gate_st.values() if v.get("cannot_play"))
    n_un = sum(1 for v in gate_st.values() if v.get("unlikely"))           # ---- IS-1
    rep.add(f"## Players who cannot play or are unlikely to play and are still ranked or valued: {n_players}",
            f"_Who cannot play: {n_cp} players, unlikely to play (Doubtful): {n_un}, by Sleeper's directory (copy of "
            f"{gate_meta.get('fetched_at') or 'no date'}; the directory alone, never the stored record it checks) "
            "(league_lab.availability_gate)._")
    rep.add(*([f"- **{it['player']} ({it['team']}, {it['position']}): {it['why']} — {it['view']} rank {it['rank']}, "
               f"{it['proj']:.1f} [{', '.join(lb)}]**" for it, lb in names[:MAX_ROWS * 2]]
              or ["- None: every player who cannot play or is unlikely to play is out of this week's lists, and every player out indefinitely "
                  "out of the season lists and the calculator's values."]), "")
    # ---- end IR-1
    # ---- coverage: the first section
    rep.add("## Coverage — every team in every list")
    miss = []
    playing = teams_with_games(query, season, week, week)
    for b in boards:
        want = playing if b.view == "week" else teams_with_games(query, season, *b.window)
        m = missing_teams(b.rows, want)
        if m:
            miss.append(f"- **{b.label} · {b.view} · {b.position}: missing {', '.join(m)}**")
    rep.counts["coverage"] = len(miss)
    rep.add(*(miss or ["- Every team with a game in a list's window has players in it (all "
                       f"{len(boards)} lists)."]), "")

    # ---- projection against what they have scored
    rep.add("## Projected against what they have scored (3+ games this season)")
    n_flag = 0
    for view in ("week", "season", "value"):
        for pos in POSITIONS:
            fl, ex = {}, {}
            for b in boards:
                if b.view == view and b.position == pos:
                    f, e = against_scored(b, ppg[b.label])
                    fl[b.label], ex[b.label] = f, e
            grouped = _group(fl, lambda it: (it["kind"], it["player"]))
            exg = _group(ex, lambda it: (it["kind"], it["player"]))
            if not grouped and not exg:
                continue
            title = {"week": "this week", "season": "rest of season", "value": "the free calculator's values"}[view]
            rep.add(f"### {pos} · {title}")
            for it, labels in grouped[:MAX_ROWS]:
                rep.add(f"- {it['player']} ({it['team']}): {it['why']} [{', '.join(labels)}]")
            if len(grouped) > MAX_ROWS:
                rep.add(f"- … and {len(grouped) - MAX_ROWS} more")
            if exg:
                rep.add("- explained by status: " + "; ".join(f"{it['player']} ({it['why'].split('explained: ')[-1]})"
                                                              for it, _ in exg))
            n_flag += len(grouped)
    rep.counts["against_scored"] = n_flag
    if not n_flag:
        rep.add("- Nothing flagged.")
    rep.add("")

    # ---- status
    rep.add("## Status this week")
    wk = [b for b in boards if b.view == "week"]
    outs = _group({b.label: out_but_projected(b.rows) for b in wk}, lambda it: (it["player"], it["team"]))
    n_status = len({r.player_key for b in wk for r in b.rows.itertuples() if _s(r.status)})
    n_report = len({r.player_key for b in wk for r in b.rows.itertuples() if _s(getattr(r, "report_status", None))})
    rep.add(f"- This week's board: {n_report} players carry an injury-report status (0 = the week's report is not out "
            f"yet); {n_status} are Out, Doubtful or on a reserve list.")
    rep.counts["out_projected"] = len(outs)
    rep.add(*([f"- {it['player']} ({it['team']}, {it['position']}): {it['why']} [{', '.join(lb)}]"
               for it, lb in outs[:MAX_ROWS]] or ["- No player ruled out or on a reserve list is projected above a backup."]))
    qb_boards = [b for b in wk if b.position == "QB"]
    qpt = _group({b.label: qbs_per_team(b.rows, playing) for b in qb_boards}, lambda it: (it["team"], it["why"]))
    rep.counts["qbs_per_team"] = len(qpt)
    rep.add(*([f"- {it['team']}: {it['why']} [{', '.join(lb)}]" for it, lb in qpt]
              or [f"- Every team playing this week has exactly one quarterback above {QB_STARTER:.0f}."]))
    rep.add("", "## Who starts")
    if _has(query, "analytics.mart_starter_check"):
        try:
            sc_rows = query("select * from analytics.mart_starter_check where week = %s", (week,))
            bad = sc_rows[~sc_rows["agree"].astype(bool)] if "agree" in sc_rows else sc_rows.iloc[0:0]
            rep.add(f"IQ-2's `analytics.mart_starter_check`, week {week}: {len(bad)} of {len(sc_rows)} teams disagree")
            for r in bad.head(MAX_ROWS).to_dict("records"):
                rep.add("- " + ", ".join(f"{k} {v}" for k, v in r.items() if k not in ("week", "agree") and v is not None))
        except Exception as exc:  # noqa: BLE001
            rep.add(f"- `analytics.mart_starter_check` could not be read ({exc.__class__.__name__})")
    else:
        rep.add("- IQ-2's `analytics.mart_starter_check` is not on this database yet; below, our own check: the "
                "projected starter against the dropbacks of the team's newest played game.")
    if qb_boards:
        last = query(LAST_GAME_SQL, (season, week, season))
        last["dropbacks"] = pd.to_numeric(last["dropbacks"], errors="coerce").fillna(0.0)
        sv = starter_vs_last_game(qb_boards[0].rows, last)
        rep.counts["starter_vs_last_game"] = len(sv)
        rep.add(*([f"- {it['team']}: {it['why']}" for it in sv]
                  or ["- Every projected starter led his team's dropbacks in its last game."]))
    rep.add("")

    # ---- agreement
    rep.add("## This week against the later weeks (top 24 by this week, rank correlation)")
    rep.add("| list | " + " | ".join(POSITIONS) + " |", "|---|" + "---|" * len(POSITIONS))
    low = 0
    for key, (_name, label) in REFERENCES.items():
        cells = []
        for pos in POSITIONS:
            b = next((x for x in boards if x.key == key and x.view == "season" and x.position == pos), None)
            a = agreement(b.rows, week) if b is not None and "weeks" in b.rows else None
            floor = AGREE_FLOOR.get(pos)
            bad = a is not None and floor is not None and a < floor
            low += int(bad)
            cells.append("–" if a is None else (f"**{a:.2f}** (floor {floor:.2f})" if bad else f"{a:.2f}"))
        rep.add(f"| {label} | " + " | ".join(cells) + " |")
    rep.counts["agreement_below_floor"] = low
    rep.add("")

    # ---- rank moves
    rep.add("## Rest-of-season rank moves since the previous run")
    today = {f"{b.label} · {b.position}": {str(r.player_key): {"rank": int(r.rank), "name": r.player_name,
                                                                 "games": None, "status": r.status}
                                            for r in b.rows.itertuples()}
             for b in boards if b.view == "season"}
    for lk, rows in today.items():
        g = ppg.get(lk.split(" · ")[0])
        games = dict(zip(g["player_key"], g["games"], strict=True)) if g is not None and len(g) else {}
        for pk, r in rows.items():
            r["games"] = int(games.get(pk, 0))
    before = None
    if ranks_path is not None and ranks_path.exists():
        try:
            before = json.loads(ranks_path.read_text())
        except Exception:  # noqa: BLE001 - an unreadable file is the same as none
            before = None
    if before is None:
        rep.add("- Yesterday's board is not kept anywhere (the database keeps only the newest fit of an unplayed week) "
                "and no earlier run of this audit left its ranks here: nothing to compare. This run's ranks are saved "
                f"in `logs/{RANKS_FILE}` for the next run on this machine.")
    else:
        mv = rank_moves(today, before.get("lists") or {})
        rep.counts["rank_moves"] = len(mv)
        rep.add(f"- Compared with the run of {before.get('built_at', '?')}:")
        rep.add(*(_fmt(mv, "") or [f"- No move of more than {RANK_MOVE} places without a game or a status change."]))
    if ranks_path is not None:
        try:
            ranks_path.write_text(json.dumps({"built_at": pd.Timestamp(clock.now()).isoformat(), "week": week,
                                              "lists": today}))
        except Exception as exc:  # noqa: BLE001 - the report stands without it
            rep.add(f"- (the ranks could not be saved: {exc.__class__.__name__})")
    rep.add("", "## Counts", ", ".join(f"{k} {v}" for k, v in rep.counts.items()))
    return rep


def run(out_dir: Path | None = None) -> str:
    """Build the report on the configured database, write ``logs/list_audit.md``, return the text. Never raises."""
    import psycopg

    from .config import PROJECT_ROOT, get_settings
    from .validation import frame_query
    out_dir = out_dir or PROJECT_ROOT / "logs"
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        with psycopg.connect(get_settings().pipeline_dsn()) as conn:
            conn.read_only = True
            rep = build(frame_query(conn), ranks_path=out_dir / RANKS_FILE)
        text = "\n".join(rep.lines) + "\n"
    except Exception as exc:  # noqa: BLE001 - exit 0 always: the audit's own failure is its report
        log.exception("audit-lists failed")
        text = f"# List audit\n\nThe audit could not run: {exc.__class__.__name__}: {str(exc)[:300]}\n"
    try:
        (out_dir / "list_audit.md").write_text(text)
    except Exception:  # noqa: BLE001
        pass
    return text
