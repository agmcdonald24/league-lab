"""The scoring check (Wave I-C, IC-1): do we score a league the way the league scores itself?

For one league and one scored week, every rostered player's **actual** points as the platform scored them against
ours: ``scoring.price_detail`` (the league's ``ScoringSpec``) on the player's actual stat line from
``analytics.fct_player_game`` (gsis through ``analytics.player_id_map`` for Sleeper, the nflverse id table for MFL;
its ``*_tds_10p/40p/50p`` counts make MFL's touchdown-distance bands exact). The platform's points:

* Sleeper, a house league: ``staging.stg_sleeper__matchup_players.points`` (Sleeper's ``players_points``);
  any other Sleeper league (or a week the copy lacks): the on-demand ``/matchups/<week>`` call's ``players_points``.
* MyFantasyLeague: ``weeklyResults`` — every rostered player's ``score`` (team units included: a ``TMQB`` is the
  team's quarterbacks' summed line priced with QB's rules, a ``TMPK`` the team's kickers', a ``Def`` the team's
  defense line from ``analytics.mart_kd_week``).

The answer: ``{league, week, n, within_0_1, within_1, misses: [{player, position, theirs, ours, gap, likely_rule}],
suspect_rules, sql, words, ...}``. ``likely_rule`` is the rule family whose removal (or whose one missing event)
closes the gap; ``suspect_rules`` counts them. House leagues also compare the spec with the dbt macro's twin
(``analytics.fct_player_game_league.points`` = ``league_points`` over the same rows) and list where they disagree.

The players counted (``n``): rostered, matched to an NFL player, and either with a game this week or with points
from the platform. Weeks with no stat rows (the clone is a 2026-09-26 snapshot: weeks 1-2 are complete) are said
in ``words``, never scored as zeros.
"""

from __future__ import annotations

import math
import time
from collections import Counter
from collections.abc import Callable, Mapping
from typing import Any

import pandas as pd

from .scoring import ScoringSpec, price_detail

Query = Callable[[str, tuple], pd.DataFrame]

# Sleeper's own per-player points for a house league: the analytics twin first (the API's read-only role reads
# analytics only), the staging view second (the pipeline role), the on-demand matchups call last
HOUSE_POINTS_SQLS = ("""
select w.sleeper_player_id, w.roster_id, w.points_observed as points, w.is_starter
from analytics.league_player_week w
where w.league_id = %s and w.week = %s""", """
select m.sleeper_player_id, m.roster_id, m.points, m.is_starter
from staging.stg_sleeper__matchup_players m
where m.league_id = %s and m.week = %s""")
IDMAP_SQL = "select sleeper_id, gsis_id from analytics.player_id_map where sleeper_id = any(%s)"
STAT_COLS = ("passing_yards passing_tds passing_interceptions passing_2pt_conversions passing_first_downs completions "
             "attempts rushing_yards rushing_tds rushing_2pt_conversions rushing_first_downs carries receptions targets "
             "receiving_yards receiving_tds receiving_2pt_conversions receiving_first_downs special_teams_tds "
             "fumble_recovery_tds fumbles_total fumbles_lost_total fg_made fg_missed fg_blocked fg_made_0_19 "
             "fg_made_20_29 fg_made_30_39 fg_made_40_49 fg_made_50_59 fg_made_60_ fg_missed_0_19 fg_missed_20_29 "
             "fg_missed_30_39 fg_missed_40_49 fg_missed_50_59 fg_missed_60_ pat_made pat_missed pat_blocked "
             "pass_tds_40p pass_tds_50p rush_tds_40p rush_tds_50p rec_tds_40p rec_tds_50p").split()
TEN_YARD_CUTS = ("pass_tds_10p", "rush_tds_10p", "rec_tds_10p")
STATS_SQL = """
select g.*
from analytics.fct_player_game g
where g.season = %s and g.week = %s and g.season_type = 'REG' and (g.gsis_id = any(%s) or g.team = any(%s))"""
DEF_SQL = """
select unit_id, team, out_sacks as sacks, out_interceptions as interceptions, out_fumble_recoveries as fumble_recoveries,
       out_forced_fumbles as forced_fumbles, out_def_tds as def_tds, out_st_tds as st_tds, out_safeties as safeties,
       out_blocked_kicks as blocked_kicks, out_points_allowed as points_allowed
from analytics.mart_kd_week where season = %s and week = %s and position = 'DEF' and played"""
SQL_TWIN_SQL = """
select gsis_id, points from analytics.fct_player_game_league
where league_id = %s and season = %s and week = %s and season_type = 'REG'"""
WEEKS_SQL = "select week, count(*) as n from analytics.fct_player_game where season = %s and season_type = 'REG' group by 1"

FULL_WEEK_ROWS = 600            # a complete NFL week has 1,000+ player-game rows; week 3's Thursday game alone 68

PIECE_WORDS = {
    "band": "the flat yardage bonus", "distance": "touchdowns by distance", "step": "yards per whole 10",
    "rate": "the per-unit rate", "premium": "the position's catch premium",
}


def _num(v: Any) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if math.isnan(f) else f


def piece_words(piece: str) -> str:
    """``band:rushing_yards:100`` -> "the +bonus at 100 rushing yards" (plain words for a rule family)."""
    kind, _, rest = piece.partition(":")
    if kind == "band":
        stat, _, lo = rest.partition(":")
        return f"the bonus at {lo} {stat.replace('_', ' ')}"
    if kind == "distance":
        return f"{rest.replace('_', ' ')} by distance"
    if kind == "step":
        return f"{rest.replace('_', ' ')} paid per whole unit"
    if kind == "premium":
        return f"the premium on {rest.replace('_', ' ')}"
    if kind == "rate":
        return rest.replace("_", " ")
    if kind == "count":
        return f"the count of {rest.split(' (')[0].replace('_', ' ')} (one more or fewer than our stat line)"
    if kind == "missing":
        return rest
    return piece


def likely_rule(theirs: float, pieces: Mapping[str, float], spec: ScoringSpec, position: str | None,
                approx: bool) -> str:
    """The rule family that best explains ``ours - theirs``: one of our pieces whose removal closes the gap to
    within a point, else one event we cannot see (a touchdown of some length, a 2-pt conversion, a return), else a
    distance guess (``approx``), else "unexplained"."""
    ours = sum(pieces.values())
    gap = ours - theirs
    best, best_d = None, abs(gap)
    for k, v in pieces.items():
        d = abs(gap - v)
        if d < best_d and d <= 1.0:
            best, best_d = k, d
    if best is not None:
        return best
    if approx and abs(gap) <= 6.5:
        return "distance:approximated (no play-by-play length for this touchdown)"
    r = spec.rules_for(position)
    for stat, w in (r.rates.items() if r else []):     # one event more or fewer than our count (a sack, a catch)
        if w and abs(abs(gap) - abs(w)) <= 0.01 and stat not in ("passing_yards", "rushing_yards", "receiving_yards"):
            return f"count:{stat} (one more or fewer than our stat line)"
    td_values = sorted({b[2] for bs in (r.distance.values() if r else []) for b in bs} | {6.0, 4.0})
    for v in td_values:
        if abs(-gap - v) <= 1.0:
            return "missing:a touchdown we do not see (a return or fumble TD, or a lateral)"
    if abs(-gap - 2.0) <= 0.5:
        return "missing:a 2-pt conversion or a defensive / special-teams play"
    if r is not None and r.steps and abs(gap) <= 1.0:
        return "step:rounding of yards per whole unit"
    return "unexplained"


def _sleeper_points(client, league_id: str, week: int, query: Query | None = None) -> tuple[pd.DataFrame, str]:
    """Sleeper's per-player points for the week: the copy's matchup rows when it has them, else the on-demand
    matchups call's ``players_points``."""
    for sql, src in zip(HOUSE_POINTS_SQLS, ("analytics.league_player_week", "staging.stg_sleeper__matchup_players"),
                        strict=True):
        if query is None:
            break
        try:
            d = query(sql, (str(league_id), int(week)))
        except Exception:  # noqa: BLE001 - a role or copy without the relation: the next source
            continue
        if d is not None and not d.empty and bool((pd.to_numeric(d["points"], errors="coerce").fillna(0) != 0).any()):
            return d.assign(points=pd.to_numeric(d["points"], errors="coerce")), src
    rows = []
    for m in client.matchups(league_id, week) or []:
        starters = set(map(str, m.get("starters") or []))
        for pid, pts in (m.get("players_points") or {}).items():
            rows.append({"sleeper_player_id": str(pid), "roster_id": m.get("roster_id"), "points": _num(pts),
                         "is_starter": str(pid) in starters})
    return pd.DataFrame(rows, columns=["sleeper_player_id", "roster_id", "points", "is_starter"]), "sleeper matchups"


def _stat_line(row: Mapping) -> dict:
    line = {c: _num(row.get(c)) for c in STAT_COLS}
    for c in TEN_YARD_CUTS:                  # the 10-yard cut (fct_player_game since Wave I-C); older copies approximate it
        if row.get(c) is not None:
            line[c] = _num(row.get(c))
    line["position"] = row.get("position")
    return line


def _sum_lines(lines: list[dict]) -> dict:
    out: dict[str, Any] = {}
    for ln in lines:
        for k, v in ln.items():
            if k.endswith("_lengths"):
                out[k] = (out.get(k) or []) + list(v)
            elif isinstance(v, (int, float)):
                out[k] = out.get(k, 0.0) + v
    for fam in ("passing_tds", "rushing_tds", "receiving_tds"):   # a unit's lengths only when every QB's are known
        if f"{fam}_lengths" in out and len(out[f"{fam}_lengths"]) != int(round(out.get(fam, 0))):
            out.pop(f"{fam}_lengths")
    return out


def scored_weeks(query: Query, season: int) -> list[int]:
    """Weeks of ``season`` whose stat rows look complete (a full slate, not one Thursday game)."""
    d = query(WEEKS_SQL, (int(season),))
    return sorted(int(r.week) for r in d.itertuples() if int(r.n) >= FULL_WEEK_ROWS)


def compare(rows: list[dict], spec: ScoringSpec) -> dict:
    """rows: {player, position, gsis_id?, theirs, line (stat dict) | None, unit?} -> the counts, misses, suspects."""
    n = w01 = w1 = 0
    misses, approx_n = [], 0
    for r in rows:
        line = r.get("line")
        if line is None:
            continue
        pieces, approx = price_detail(line, spec, r.get("position"))
        ours = round(sum(pieces.values()), 2)
        theirs = round(_num(r.get("theirs")), 2)
        gap = round(ours - theirs, 2)
        n += 1
        approx_n += int(approx)
        w01 += int(abs(gap) <= 0.1 + 1e-9)
        w1 += int(abs(gap) <= 1.0 + 1e-9)
        r["ours"], r["gap"], r["pieces"] = ours, gap, pieces
        if abs(gap) > 1.0 + 1e-9:
            misses.append({"player": r.get("player"), "position": r.get("position"), "gsis_id": r.get("gsis_id"),
                           "theirs": theirs, "ours": ours, "gap": gap,
                           "likely_rule": likely_rule(theirs, pieces, spec, r.get("position"), approx),
                           "pieces": {k: round(v, 2) for k, v in pieces.items()}})
    misses.sort(key=lambda m: -abs(m["gap"]))
    fam = Counter(m["likely_rule"].split(" (")[0] for m in misses)
    suspects = [{"rule": k, "words": piece_words(k), "misses": v} for k, v in fam.most_common()]
    return {"n": n, "within_0_1": w01, "within_1": w1, "misses": misses, "suspect_rules": suspects,
            "approximated_rows": approx_n}


def _words(out: dict) -> str:
    if not out["n"]:
        return out.get("why_empty") or "No scored players to check for this week."
    pct = 100.0 * out["within_1"] / out["n"]
    s = (f"Week {out['week']} check: we match the league's own points for {out['within_1']} of {out['n']} players "
         f"within 1 point ({pct:.0f}%), {out['within_0_1']} to the tenth.")
    if out["misses"]:
        top = "; ".join(f"{m['player']} (theirs {m['theirs']:g}, ours {m['ours']:g}: {piece_words(m['likely_rule'])})"
                        for m in out["misses"][:3])
        s += f" The misses: {top}" + ("…" if len(out["misses"]) > 3 else ".")
    if out.get("approximated_rows"):
        s += f" {out['approximated_rows']} players' touchdowns by distance were approximated (no play-by-play length)."
    return s


def check(query: Query, league: Mapping, week: int | None, *, client=None, players: Mapping | None = None,
          mfl_client=None, sql_twin: bool = True) -> dict:
    """The scoring check for a league (Sleeper-shaped dict from ``anyleague.sleeper().league``) and a week (None:
    the last complete week the copy holds)."""
    from . import anyleague as A
    t0 = time.perf_counter()
    lid = str(league.get("league_id"))
    season = int(league.get("season") or 0)
    spec = A.league_spec(league)
    weeks = scored_weeks(query, season)
    if week is None:
        last = int((league.get("settings") or {}).get("last_scored_leg") or 0)
        cands = [w for w in weeks if not last or w <= last] or weeks
        week = max(cands) if cands else 1
    week = int(week)
    out: dict[str, Any] = {"league": lid, "week": week, "season": season, "source": spec.source,
                           "scored_weeks": weeks, "spec_unpriced": [f"{u['name']} ({u['event']})" for u in spec.unpriced],
                           "spec_approximated": list(spec.approximated)}
    if week not in weeks:
        out.update(n=0, within_0_1=0, within_1=0, misses=[], suspect_rules=[], sql=None,
                   why_empty=(f"Week {week} is not complete in our NFL stats yet (complete weeks: "
                              f"{', '.join(map(str, weeks)) or 'none'}); the check needs a finished week."))
        out["words"] = _words(out)
        return out
    if lid.startswith("mfl:"):
        rows, unmatched, theirs_src = _mfl_rows(query, league, week, season, mfl_client)
    else:
        rows, unmatched, theirs_src = _sleeper_rows(query, league, week, season, client)
    res = compare(rows, spec)
    out.update(res)
    out["theirs_from"] = theirs_src
    out["unmatched"] = unmatched
    out["sql"] = _sql_twin(query, lid, season, week, rows) if sql_twin and not lid.startswith("mfl:") else None
    out["ms"] = round((time.perf_counter() - t0) * 1000, 1)
    out["words"] = _words(out)
    return out


def _sleeper_rows(query, league, week, season, client):
    from . import anyleague as A
    lid = str(league["league_id"])
    client = client or A.sleeper()
    pts, src = _sleeper_points(client, lid, week, query)
    if pts.empty:
        return [], [], src
    ids = sorted(set(pts["sleeper_player_id"].astype(str)))
    idmap = query(IDMAP_SQL, (ids,))
    to_gsis = dict(zip(idmap["sleeper_id"].astype(str), idmap["gsis_id"].astype(str), strict=False))
    teams = [i for i in ids if i.isalpha()]
    stats = query(STATS_SQL, (season, week, list(to_gsis.values()), []))
    by_gsis = {str(r["gsis_id"]): r for r in stats.to_dict("records")}
    defs = {str(r["team"]): r for r in query(DEF_SQL, (season, week)).to_dict("records")} if teams else {}
    rows, unmatched = [], []
    for r in pts.to_dict("records"):
        sid, theirs = str(r["sleeper_player_id"]), _num(r["points"])
        if sid.isalpha():                                   # a team defense: Sleeper's id is the team code
            d = defs.get(_nflverse(sid))
            if d is None:
                if theirs:
                    unmatched.append({"player": f"{sid} defense", "theirs": theirs, "why": "no defense line"})
                continue
            line = {k: _num(v) for k, v in d.items() if k not in ("unit_id", "team")}
            rows.append({"player": f"{sid} defense", "position": "DEF", "theirs": theirs, "line": line})
            continue
        g = to_gsis.get(sid)
        if g is None:
            if theirs:
                unmatched.append({"player": sid, "theirs": theirs, "why": "not in player_id_map"})
            continue
        st = by_gsis.get(g)
        if st is None:
            if theirs:
                unmatched.append({"player": sid, "gsis_id": g, "theirs": theirs, "why": "no stat row this week"})
            continue
        rows.append({"player": st.get("player_name"), "position": st.get("position"), "gsis_id": g, "theirs": theirs,
                     "line": _stat_line(st)})
    return rows, unmatched, src


def _mfl_rows(query, league, week, season, mfl_client):
    from . import mfl_client as M
    from . import player_ids as PI
    lid = str(league["league_id"]).removeprefix("mfl:")
    cl = mfl_client or M.MFL()
    res = cl.weekly_results(lid, week)
    scores: dict[str, float] = {}
    for m in M._as_list(res.get("matchup")) + [{"franchise": res.get("franchise")}]:
        for f in M._as_list(m.get("franchise")):
            for p in M._as_list(f.get("player")):
                scores[str(p.get("id"))] = _num(p.get("score"))
    if not scores:
        return [], [], "MyFantasyLeague weeklyResults (empty)"
    info = {str(p.get("id")): p for p in cl.players(sorted(scores))}
    gs = {i: PI.mfl_to_gsis(i) for i in scores}
    unit_teams = sorted({M.TEAM.get(str(info[i].get("team") or "").upper(), str(info[i].get("team") or "").upper())
                         for i in scores if i in info and str(info[i].get("position")) in ("TMQB", "TMPK", "Def", "TMDEF")})
    nfl_team = {v: v for v in unit_teams}
    stats = query(STATS_SQL, (season, week, [g for g in gs.values() if g], [_nflverse(t) for t in unit_teams]))
    recs = stats.to_dict("records")
    by_gsis = {str(r["gsis_id"]): r for r in recs}
    defs = {str(r["team"]): r for r in query(DEF_SQL, (season, week)).to_dict("records")}
    rows, unmatched = [], []
    for i, theirs in scores.items():
        p = info.get(i, {})
        pos = str(p.get("position") or "")
        name = str(p.get("name") or i)
        if pos in ("TMQB", "TMPK"):
            team = _nflverse(M.TEAM.get(str(p.get("team") or "").upper(), str(p.get("team") or "").upper()))
            want = "QB" if pos == "TMQB" else "K"
            lines = [_stat_line(r) for r in recs if r.get("team") == team and r.get("position") == want]
            rows.append({"player": name, "position": pos, "theirs": theirs, "unit": team,
                         "line": _sum_lines(lines) if lines else {"position": pos}})
            continue
        if pos in ("Def", "TMDEF"):
            team = _nflverse(M.TEAM.get(str(p.get("team") or "").upper(), str(p.get("team") or "").upper()))
            d = defs.get(team)
            if d is None:
                unmatched.append({"player": name, "theirs": theirs, "why": "no defense line"})
                continue
            rows.append({"player": name, "position": "DEF", "theirs": theirs,
                         "line": {k: _num(v) for k, v in d.items() if k not in ("unit_id", "team")}})
            continue
        g = gs.get(i)
        if not g:
            if theirs:
                unmatched.append({"player": name, "theirs": theirs, "why": "no id match"})
            continue
        st = by_gsis.get(g)
        if st is None:
            if theirs:
                unmatched.append({"player": name, "gsis_id": g, "theirs": theirs, "why": "no stat row this week"})
            continue
        rows.append({"player": st.get("player_name") or name, "position": M.POS.get(pos, pos) or st.get("position"),
                     "gsis_id": g, "theirs": theirs, "line": _stat_line(st)})
    del nfl_team
    return rows, unmatched, "MyFantasyLeague weeklyResults"


def _nflverse(team: str) -> str:
    """Sleeper's team code -> nflverse's (they differ for the Rams only)."""
    return {"LAR": "LA", "JAC": "JAX", "WSH": "WAS"}.get(team, team)


def _sql_twin(query: Query, lid: str, season: int, week: int, rows: list[dict]) -> dict | None:
    """House leagues: the dbt macro's points (``fct_player_game_league``, ``league_points`` over the same stat rows)
    against the spec's, player by player. A disagreement is a rule the SQL cannot express (a per-position premium,
    a first-down key) or a bug in one of the two."""
    try:
        d = query(SQL_TWIN_SQL, (lid, season, week))
    except Exception:  # noqa: BLE001 - the hosted copy does not carry it
        return None
    if d is None or d.empty:
        return None
    sqlp = {str(r.gsis_id): _num(r.points) for r in d.itertuples()}
    n, disagree = 0, []
    for r in rows:
        g = r.get("gsis_id")
        if not g or g not in sqlp or "ours" not in r:
            continue
        n += 1
        if abs(sqlp[g] - r["ours"]) > 0.01:
            disagree.append({"player": r.get("player"), "position": r.get("position"), "sql": round(sqlp[g], 2),
                             "spec": r["ours"], "theirs": r.get("theirs"), "gap": round(r["ours"] - sqlp[g], 2),
                             "pieces": {k: round(v, 2) for k, v in (r.get("pieces") or {}).items()}})
    return {"n": n, "agree": n - len(disagree), "disagree": disagree}
