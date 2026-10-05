"""Role changes, opportunity vs production and contingent upside (IL-1, Wave I-L; the fifth review § 10, "Analytics
worth developing after the inventory"). Labels and numbers about the past, in words — no model feature, no change to a
projection, no probability, never "due for regression" or "will continue".

Pure functions on frames (the API runs the SQL below and prices the points in the league's scoring); every number comes
from ``analytics.fct_player_game`` (his game rows) with the team's denominators from ``fct_team_game`` as that table
already carries them (``team_targets``, ``team_carries``, ``team_red_zone_*``: AGENTS rule 4 — never a sum of player rows).

1. **Role change** (``role_change``): his **recent role** = his last 2 games with at least one offensive snap (a game
   with no snap count recorded counts when he played), against his **earlier role** = his games before those this
   season — at least 3, else "not enough games yet". Per game: carries, targets, red-zone touches (red-zone carries +
   red-zone targets: a count, never a combined percentage), and snap share (the mean of his per-game shares, the card's
   rule). A change is **named** only when (a) the recent sample is 2 games, (b) the difference is larger than one
   standard deviation of his earlier games (sample s.d., n − 1) and (c) it clears a floor so a near-zero metric cannot
   "change" — ``MIN_CHANGE``: 1.0 carries or targets per game, 0.5 red-zone touches per game, 5 points of snap share.
   Otherwise "steady" (with both numbers) or "too early to say" (with the counts).
2. **Opportunity vs production** (``opportunity_vs_production``): over his games on his current team this season, his
   share of his position group's opportunities (his targets + carries — + pass attempts for a QB — ÷ the same for his
   team's players at his position in those games: WR and TE together for a receiver) against his share of the group's
   fantasy points in the league's scoring (summed player rows: the only place a position's points exist). The gap is
   labelled in words only: **"production ahead of his volume"** when the production share is at least 5 points and
   25 % (relative) above the opportunity share, **"volume ahead of his production"** when it is at least 5 points and
   20 % below it, else **"in line"** — both shares always printed. Context printed beside it: his share of the whole
   team's targets + carries and his red-zone share (carries for a RB / QB, targets for a WR / TE — the copy standard),
   from ``fct_team_game``'s totals. Needs 2 games and a group with points.
3. **Contingent upside** (``pick_teammate`` + ``contingent_upside``): the one scenario our data states honestly — games
   a positional teammate missed. The teammate is the one on his current team, at his position (WR or TE for a
   receiver), with the highest opportunity share this season (targets for WR / TE, targets + carries for RB, pass
   attempts for QB; himself excluded). From 2024 on, same team only: the games he played while that teammate was on
   the team's roster that week (``player_team_history``: active, reserve or inactive) and did not play; with 2 or more,
   his per-game opportunity and points in them against the games they both played — the counts and the seasons in the
   words; with fewer, "no games without X to go on". Assumptions in the words; no probability.
"""

from __future__ import annotations

import math

import pandas as pd

RECENT_GAMES = 2
EARLIER_MIN = 3
MIN_CHANGE = {"carries": 1.0, "targets": 1.0, "red_zone_touches": 0.5, "snap_share": 0.05}
# opportunity vs production: a label needs the gap to clear both an absolute and a relative bar
OVP_ABS = 0.05
OVP_AHEAD = 1.25
OVP_BEHIND = 0.80
OVP_MIN_GAMES = 2
CONTINGENT_MIN_GAMES = 2
CONTINGENT_FROM = 2024
ON_ROSTER = ("ACT", "RES", "INA")
METRIC_WORDS = {"carries": "carries", "targets": "targets", "red_zone_touches": "red-zone touches",
                "snap_share": "snap share"}
METRIC_TITLE = {"carries": "Carries", "targets": "Targets", "red_zone_touches": "Red-zone touches",
                "snap_share": "Snap share"}
# which metric leads the headline for a position, in order of preference
LEAD = {"QB": ["carries", "snap_share", "red_zone_touches", "targets"],
        "RB": ["carries", "targets", "red_zone_touches", "snap_share"],
        "WR": ["targets", "snap_share", "red_zone_touches", "carries"],
        "TE": ["targets", "snap_share", "red_zone_touches", "carries"]}

# ---------------------------------------------------------------------------------------------- the SQL the API runs
GAME_COLS = ("gsis_id, player_name, game_id, season, week, team, position, played, snaps_known, offense_snaps, "
             "offense_snap_pct, targets, carries, attempts, red_zone_targets, red_zone_carries, team_targets, "
             "team_carries, team_attempts, team_red_zone_targets, team_red_zone_carries")
# his rows this regular season through the week
PLAYER_SEASON_SQL = f"""select {GAME_COLS} from analytics.fct_player_game
                        where gsis_id = %s and season = %s and season_type = 'REG' and week <= %s order by week"""
# his team's rows at a set of positions this regular season through the week (the group and the teammate pick)
TEAM_SEASON_SQL = f"""select {GAME_COLS} from analytics.fct_player_game
                      where team = %s and season = %s and season_type = 'REG' and week <= %s and position = any(%s)"""
# 2024 on, regular season, the team's rows for him and the teammate (same team only); params: team, since, season,
# season, through, ids
PAIR_SQL = f"""select {GAME_COLS} from analytics.fct_player_game
               where team = %s and season_type = 'REG' and season between %s and %s
                 and (season < %s or week <= %s) and gsis_id = any(%s)"""
# the weeks the teammate was on the team's roster (active, reserve or inactive), 2024 on; params: mate, team, since,
# season, season, through, statuses
ROSTER_SQL = """select season, week, game_id from analytics.player_team_history
                where gsis_id = %s and team = %s and season_type = 'REG' and season between %s and %s
                  and (season < %s or week <= %s) and roster_status = any(%s) and game_id is not null"""


# ---------------------------------------------------------------------------------------------- helpers
def _num(df: pd.DataFrame, col: str) -> pd.Series:
    return pd.to_numeric(df[col], errors="coerce") if col in df else pd.Series(float("nan"), index=df.index)


def _played(df: pd.DataFrame) -> pd.Series:
    return df["played"].fillna(False).astype(bool) if "played" in df else pd.Series(True, index=df.index)


def _with_snap(df: pd.DataFrame) -> pd.Series:
    """A game with at least one offensive snap; a game with no snap count recorded counts when he played."""
    played = _played(df)
    known = df["snaps_known"].fillna(False).astype(bool) if "snaps_known" in df else pd.Series(False, index=df.index)
    snaps = _num(df, "offense_snaps")
    pct = _num(df, "offense_snap_pct")
    has = (snaps > 0) | (snaps.isna() & (pct > 0))
    return (known & has) | (~known & played)


def _fmt(metric: str, v: float | None) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    return f"{v * 100:.0f}%" if metric == "snap_share" else f"{v:.1f}"


def _per_game(metric: str, v: float | None) -> str:
    return _fmt(metric, v) if metric == "snap_share" else f"{_fmt(metric, v)} per game"


def _games(n: int) -> str:
    return f"{n} game{'s' if n != 1 else ''}"


def _seasons(seasons) -> str:
    s = sorted({int(x) for x in seasons})
    if not s:
        return ""
    return str(s[0]) if len(s) == 1 else f"{s[0]}–{str(s[-1])[-2:]}"


def _pct(v: float | None) -> str:
    return "—" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{v * 100:.0f}%"


# ---------------------------------------------------------------------------------------------- 1. role change
def role_change(games: pd.DataFrame, position: str | None = None) -> dict:
    """His recent role (last 2 games with a snap) against his earlier role (3+ games before them this season).

    ``games``: his fct_player_game rows for the season through the week (any order). Returns ``{status, metrics:
    [{metric, recent, earlier, change, spread, games_recent, games_earlier, named, direction, words}], headline,
    games_recent, games_earlier}``; ``status`` is ``changed`` | ``steady`` | ``too_early``."""
    g = games.copy()
    if g.empty:
        return {"status": "too_early", "metrics": [], "games_recent": 0, "games_earlier": 0,
                "headline": "Too early to say: no games this season yet."}
    g = g[_with_snap(g)].sort_values("week")
    g["red_zone_touches"] = _num(g, "red_zone_carries").fillna(0) + _num(g, "red_zone_targets").fillna(0)
    g["snap_share"] = _num(g, "offense_snap_pct").where(
        g["snaps_known"].fillna(False).astype(bool) if "snaps_known" in g else True)
    for c in ("carries", "targets"):
        g[c] = _num(g, c).fillna(0)
    recent, earlier = g.tail(RECENT_GAMES), g.iloc[:max(0, len(g) - RECENT_GAMES)]
    nr, ne = len(recent), len(earlier)
    out = {"games_recent": nr, "games_earlier": ne, "metrics": []}
    if nr < RECENT_GAMES or ne < EARLIER_MIN:
        need = RECENT_GAMES + EARLIER_MIN
        out.update(status="too_early",
                   headline=(f"Too early to say: {_games(len(g))} with a snap so far this season; a change is called "
                             f"from his last {RECENT_GAMES} games against at least {EARLIER_MIN} before them "
                             f"({need} games)."))
        for m in METRIC_WORDS:
            rv = float(recent[m].mean()) if nr and recent[m].notna().any() else None
            out["metrics"].append({"metric": m, "recent": rv, "earlier": None, "change": None, "spread": None,
                                   "games_recent": nr, "games_earlier": ne, "named": False, "direction": None,
                                   "words": f"{METRIC_TITLE[m]}: too early to say ({_games(len(g))} so far)."})
        return out
    named = []
    for m in METRIC_WORDS:
        r, e = recent[m].dropna(), earlier[m].dropna()
        if len(r) < RECENT_GAMES or len(e) < EARLIER_MIN:      # snap share with games missing a snap count
            out["metrics"].append({"metric": m, "recent": float(r.mean()) if len(r) else None,
                                   "earlier": float(e.mean()) if len(e) else None, "change": None, "spread": None,
                                   "games_recent": len(r), "games_earlier": len(e), "named": False, "direction": None,
                                   "words": f"{METRIC_TITLE[m]}: not enough games with it recorded to compare."})
            continue
        rv, ev = float(r.mean()), float(e.mean())
        sd = float(e.std(ddof=1))
        ch = rv - ev
        is_named = abs(ch) > sd and abs(ch) >= MIN_CHANGE[m]
        direction = ("up" if ch > 0 else "down") if is_named else "steady"
        both = (f"{_per_game(m, rv)} in his last {RECENT_GAMES}, {_fmt(m, ev)} in the {len(e)} before"
                if m != "snap_share" else f"{_fmt(m, rv)} in his last {RECENT_GAMES}, {_fmt(m, ev)} in the {len(e)} before")
        swing = f"±{sd * 100:.0f} points" if m == "snap_share" else f"±{sd:.1f}"
        words = (f"{METRIC_TITLE[m]} {direction}: {both}." if is_named
                 else f"{METRIC_TITLE[m]} steady: {both} (inside his usual swing of {swing}).")
        row = {"metric": m, "recent": rv, "earlier": ev, "change": ch, "spread": sd, "games_recent": len(r),
               "games_earlier": len(e), "named": is_named, "direction": direction, "words": words}
        out["metrics"].append(row)
        if is_named:
            named.append(row)
    if named:
        order = LEAD.get(position or "", list(METRIC_WORDS))
        lead = sorted(named, key=lambda x: (order.index(x["metric"]) if x["metric"] in order else 9))[0]
        others = [x for x in named if x is not lead]
        tail = ("; " + "; ".join(f"{METRIC_WORDS[x['metric']]} {x['direction']} too" for x in others)) if others else ""
        out.update(status="changed", headline=lead["words"].rstrip(".") + tail + ".")
    else:
        out.update(status="steady",
                   headline=(f"Role steady: none of his carries, targets, red-zone touches or snap share in his last "
                             f"{RECENT_GAMES} games moved past his usual swing over the {ne} before."))
    return out


# ---------------------------------------------------------------------------------------------- 2. opportunity vs production
def group_positions(position: str) -> list[str]:
    return ["WR", "TE"] if position in ("WR", "TE") else [position]


def _opps(df: pd.DataFrame, position: str) -> pd.Series:
    o = _num(df, "targets").fillna(0) + _num(df, "carries").fillna(0)
    return o + _num(df, "attempts").fillna(0) if position == "QB" else o


def opportunity_vs_production(his: pd.DataFrame, group: pd.DataFrame, position: str, *, scoring: str = "this league's",
                              team: str | None = None) -> dict:
    """His share of his position group's opportunities against its fantasy points, over his games on the team.

    ``his``: his played rows on the current team (with ``points``); ``group``: every row of the team's players at his
    position group in the same season (with ``points``; himself included)."""
    h = his[_played(his)].copy()
    n = int(h["game_id"].nunique()) if not h.empty else 0
    weeks = (int(h["week"].min()), int(h["week"].max())) if n else None
    base = {"games": n, "weeks": weeks, "label": None}
    if n < OVP_MIN_GAMES:
        return {**base, "status": "too_early",
                "words": f"Opportunity vs production: not enough games yet ({_games(n)} on this team; needs {OVP_MIN_GAMES})."}
    gr = group[group["game_id"].isin(set(h["game_id"])) & _played(group)]
    my_opp, grp_opp = float(_opps(h, position).sum()), float(_opps(gr, position).sum())
    my_pts, grp_pts = float(_num(h, "points").fillna(0).sum()), float(_num(gr, "points").fillna(0).sum())
    if grp_opp <= 0 or grp_pts <= 0:
        return {**base, "status": "no_data",
                "words": "Opportunity vs production: his position group has no opportunities or points to compare in these games."}
    opp_share, pts_share = my_opp / grp_opp, my_pts / grp_pts
    diff, ratio = pts_share - opp_share, (pts_share / opp_share if opp_share > 0 else math.inf)
    if diff >= OVP_ABS and ratio >= OVP_AHEAD:
        label = "production ahead of his volume"
    elif -diff >= OVP_ABS and ratio <= OVP_BEHIND:
        label = "volume ahead of his production"
    else:
        label = "in line"
    # the whole team's context, from fct_team_game's totals (summed over his games)
    team_den = _num(h, "team_targets").fillna(0) + _num(h, "team_carries").fillna(0)
    team_share = (float((_num(h, "targets").fillna(0) + _num(h, "carries").fillna(0)).sum()) / float(team_den.sum())
                  if float(team_den.sum()) > 0 else None)
    rz_num, rz_den, rz_word = (("red_zone_carries", "team_red_zone_carries", "red-zone carries")
                               if position in ("RB", "QB") else ("red_zone_targets", "team_red_zone_targets", "red-zone targets"))
    rz_d = float(_num(h, rz_den).fillna(0).sum())
    rz_share = float(_num(h, rz_num).fillna(0).sum()) / rz_d if rz_d > 0 else None
    grp = "WRs and TEs" if position in ("WR", "TE") else f"{position}s"
    unit = "pass attempts, targets and carries" if position == "QB" else "targets and carries"
    wk = f"week {weeks[0]}" if weeks[0] == weeks[1] else f"weeks {weeks[0]}–{weeks[1]}"
    words = (f"Opportunity vs production: **{label}** — {_pct(opp_share)} of the {unit} of his team's {grp}, "
             f"{_pct(pts_share)} of their fantasy points in {scoring} scoring ({wk}, {_games(n)}).")
    ctx = [f"{_pct(team_share)} of its targets + carries"] if team_share is not None else []
    if rz_share is not None:
        ctx.append(f"{_pct(rz_share)} of its {rz_word}")
    if ctx:
        words += " Of the whole team: " + ", ".join(ctx) + "."
    return {**base, "status": "ok", "label": label, "opportunity_share": opp_share, "production_share": pts_share,
            "team_opportunity_share": team_share, "red_zone_share": rz_share, "words": words, "team": team}


# ---------------------------------------------------------------------------------------------- 3. contingent upside
def _share_metric(position: str) -> tuple[list[str], list[str]]:
    """(the numerator columns, the team denominator columns) of the opportunity share the teammate is picked by."""
    if position in ("WR", "TE"):
        return ["targets"], ["team_targets"]
    if position == "QB":
        return ["attempts"], ["team_attempts"]
    return ["targets", "carries"], ["team_targets", "team_carries"]


def pick_teammate(team_rows: pd.DataFrame, gsis: str, position: str) -> dict | None:
    """The teammate at his position (WR or TE for a receiver) with the highest opportunity share this season on the
    team (summed numerator ÷ the team's summed totals over the teammate's games), himself excluded."""
    t = team_rows[(team_rows["gsis_id"] != gsis) & team_rows["position"].isin(group_positions(position))
                  & _played(team_rows)]
    if t.empty:
        return None
    nums, dens = _share_metric(position)
    t = t.assign(_n=sum(_num(t, c).fillna(0) for c in nums), _d=sum(_num(t, c).fillna(0) for c in dens))
    agg = t.groupby("gsis_id").agg(_n=("_n", "sum"), _d=("_d", "sum"), player_name=("player_name", "max"),
                                   position=("position", "max"), games=("game_id", "nunique"))
    agg = agg[agg["_d"] > 0]
    if agg.empty:
        return None
    agg["share"] = agg["_n"] / agg["_d"]
    best = agg.sort_values(["share", "_n"], ascending=False).iloc[0]
    if best["share"] <= 0:
        return None
    return {"gsis_id": str(best.name), "player_name": str(best["player_name"]), "position": str(best["position"]),
            "share": float(best["share"]), "games": int(best["games"])}


def _opp_word(position: str) -> tuple[str, list[str]]:
    if position in ("WR", "TE"):
        return "targets", ["targets"]
    if position == "QB":
        return "pass attempts", ["attempts"]
    return "carries + targets", ["carries", "targets"]


def contingent_upside(his: pd.DataFrame, mate_games: pd.DataFrame, mate_roster: pd.DataFrame, mate: dict | None,
                      position: str, *, scoring: str = "this league's") -> dict:
    """His per-game opportunity and points in the games the teammate missed while on the team, against the games they
    both played (2024 on, same team only).

    ``his``: his rows on the team 2024 on (with ``points``); ``mate_games``: the teammate's rows on the team 2024 on;
    ``mate_roster``: the teammate's (season, week, game_id) on the team's roster (active, reserve, inactive)."""
    if mate is None:
        return {"status": "no_teammate", "games_without": 0,
                "words": "Contingent upside: no teammate at his position with a share of the work to go on."}
    name = mate["player_name"]
    h = his[_played(his)].copy()
    mate_played = set(mate_games.loc[_with_snap(mate_games), "game_id"]) if not mate_games.empty else set()
    on_team = set(mate_roster["game_id"]) if not mate_roster.empty else set()
    without = h[h["game_id"].isin(on_team) & ~h["game_id"].isin(mate_played)]
    with_ = h[h["game_id"].isin(mate_played)]
    n_wo, n_w = int(without["game_id"].nunique()), int(with_["game_id"].nunique())
    base = {"teammate": mate, "games_without": n_wo, "games_with": n_w,
            "seasons_without": sorted({int(s) for s in without["season"]})}
    if n_wo < CONTINGENT_MIN_GAMES:
        why = (f"only {_games(n_wo)} without him ({_seasons(without['season'])})" if n_wo
               else f"no game ({CONTINGENT_FROM} on) that {name} missed while on the roster")
        return {**base, "status": "not_enough",
                "words": f"Contingent upside: no games without {name} to go on — {why}; a scenario needs "
                         f"{CONTINGENT_MIN_GAMES}."}
    word, cols = _opp_word(position)

    def per_game(df: pd.DataFrame) -> tuple[float | None, float | None]:
        k = int(df["game_id"].nunique())
        if not k:
            return None, None
        opp = float(sum(_num(df, c).fillna(0).sum() for c in cols)) / k
        pts = _num(df, "points")
        return opp, (float(pts.sum()) / k if pts.notna().any() else None)

    o_wo, p_wo = per_game(without)
    o_w, p_w = per_game(with_)
    def pts(v: float | None) -> str:
        return "—" if v is None else f"{v:.1f}"

    words = (f"Contingent upside: in the {_games(n_wo)} without {name} ({_seasons(without['season'])}), "
             f"{o_wo:.1f} {word} and {pts(p_wo)} points per game")
    if n_w >= CONTINGENT_MIN_GAMES:
        words += f", against {o_w:.1f} and {pts(p_w)} in the {_games(n_w)} with him ({_seasons(with_['season'])})"
    else:
        words += (f"; {'only 1 game' if n_w == 1 else 'no game'} with him to compare against"
                  + (f" ({_seasons(with_['season'])})" if n_w else ""))
    words += (f". Same team only, {CONTINGENT_FROM} on, {scoring} scoring; games {name} missed while on the roster. "
              "What happened, not a forecast: the rest of the lineup and the opponents were not the same.")
    return {**base, "status": "ok", "without": {"opportunity": o_wo, "points": p_wo},
            "with": {"opportunity": o_w, "points": p_w}, "words": words}
