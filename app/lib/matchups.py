"""Matchups page logic (plan R-14 cornerbacks, R-15 defense vs position, R-11 two players side by side).

Pure helpers shared by `app/pages/5_Matchups.py` and `tests/test_matchups.py`: every sentence a card shows
is built here from mart rows, so the words and the table next to them carry the same numbers.
Marts: `mart_cb_matchups`, `mart_cb_rankings`, `mart_receiver_vs_cb`, `mart_defense_position_profile`,
`mart_defense_vs_position_current`, `mart_player_week_projections` (docs/METRICS.md § Cornerback matchups,
§ Matchup comparison).

`call_cover` and `rank_corners` are Python twins of the two rules the marts apply in SQL (the likely cover in
`mart_cb_matchups`, the rank and label in `mart_cb_rankings`): the unit tests pin the rules on fixtures, and
the evidence script checks the twins against every mart row."""

from __future__ import annotations

import math

import pandas as pd

SLOT_WORDS = {"LCB": "left corner", "RCB": "right corner", "NB": "slot corner"}
GIVES_UP_WORDS = {
    "volume": "gives up volume",
    "big plays": "gives up big plays",
    "volume and big plays": "gives up volume and big plays",
    "little of either": "gives up little of either",
    "about average": "is about average",
}
MIN_LOCATED_TARGETS = 15    # fewer targets with a direction since last season -> no cornerback call
CLEAR_LEAN = 0.15           # side share minus the other side's: 15+ points = a clear lean
SHRINK_TARGETS = 30         # adjusted yards per target is shrunk toward the pool with this many targets
LEAN_RANKS = 6              # two defenses' adjusted ranks this far apart = the matchup leans one way


def _blank(v) -> bool:
    if v is None:
        return True
    try:
        return bool(pd.isna(v))
    except (TypeError, ValueError):
        return False


def last_name(name) -> str:
    """'Amon-Ra St. Brown' -> 'St. Brown', 'Will Lee III' -> 'Lee', 'Jaycee Horn' -> 'Horn'."""
    parts = str(name or "").split()
    while len(parts) > 1 and parts[-1].rstrip(".") in ("Jr", "Sr", "II", "III", "IV", "V"):
        parts = parts[:-1]
    if len(parts) >= 3 and parts[-2].rstrip(".") in ("St", "Van", "Von", "De", "Le", "La", "Du"):
        return " ".join(parts[-2:])
    return parts[-1] if parts else ""


def seasons_text(first, last) -> str:
    """2024 / 2022–25."""
    if _blank(first):
        return ""
    first, last = int(first), int(last if not _blank(last) else first)
    return f"{first}" if first == last else f"{first}–{str(last)[-2:]}"


def line_text(rec, yds, tgt) -> str:
    """'5 catches for 55 yards on 7 targets' (1 catch / 1 target singular)."""
    rec, yds, tgt = (0 if _blank(v) else int(v) for v in (rec, yds, tgt))
    return f"{rec} catch{'es' if rec != 1 else ''} for {yds} yards on {tgt} target{'s' if tgt != 1 else ''}"


def pct(v) -> str:
    return "—" if _blank(v) else f"{float(v) * 100:.0f}%"


def most(rank) -> str:
    """1 -> 'the most', 4 -> 'the 4th-most', 22 -> 'the 22nd-most'."""
    rank = int(rank)
    if rank == 1:
        return "the most"
    suffix = "th" if 10 <= rank % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(rank % 10, "th")
    return f"the {rank}{suffix}-most"


# ------------------------------------------------------------------------------------------ R-14: the rules
def call_cover(tgt_left, tgt_middle, tgt_right, position: str, lcb=None, rcb=None, nb=None,
               has_depth_chart: bool = True) -> dict:
    """The likely-cover rule of `mart_cb_matchups` (its Python twin). Targets by pass location since the start
    of last season (the offense's view); the opponent's rank-1 corners by depth-chart slot (ids or None).
    Returns call_status, alignment_lean, side_share, other_side_share, call_strength, likely_cover_slot,
    other_cover_slot. The offense's left faces the defense's right corner."""
    left, middle, right = int(tgt_left or 0), int(tgt_middle or 0), int(tgt_right or 0)
    located = left + middle + right
    ls = round(left / located, 3) if located else None
    rs = round(right / located, 3) if located else None
    side_share = max(ls, rs) if located else None
    other_share = min(ls, rs) if located else None
    if position == "TE":
        lean = "tight end"
    elif located < MIN_LOCATED_TARGETS:
        lean = "too few targets"
    else:
        lean = "left" if left > right else "right"
    if not has_depth_chart:
        status = "no depth chart yet"
    elif position == "TE":
        status = "tight end"
    elif lean == "too few targets":
        status = "too few targets"
    else:
        status = "called"
    slot = strength = other = None
    if status == "called":
        if lean == "left" and rcb:
            slot = "RCB"
        elif lean == "right" and lcb:
            slot = "LCB"
        elif lcb:
            slot = "LCB"
        elif rcb:
            slot = "RCB"
        elif nb:
            slot = "NB"
        strength = "clear" if side_share - other_share >= CLEAR_LEAN - 1e-9 else "even"
        if strength == "even" and slot == "LCB" and rcb:
            other = "RCB"
        elif strength == "even" and slot == "RCB" and lcb:
            other = "LCB"
    return {"call_status": status, "alignment_lean": lean, "located_targets": located, "side_share": side_share,
            "other_side_share": other_share, "call_strength": strength, "likely_cover_slot": slot,
            "other_cover_slot": other}


def cb_label(rank, n) -> str | None:
    """The plain label of a corner's rank among n: the top quarter 'shutdown', the bottom quarter 'target', the
    rest 'solid' (mart_cb_rankings.quality_label)."""
    if _blank(rank) or _blank(n) or int(n) <= 0:
        return None
    rank, n = int(rank), int(n)
    q = math.ceil(n / 4)
    if rank <= q:
        return "shutdown"
    if rank > n - q:
        return "target"
    return "solid"


def passer_rating(completions, targets, yards, tds, ints) -> float | None:
    """The NFL passer rating on summed components (targets as attempts), each part clamped to [0, 2.375]."""
    if not targets:
        return None
    c, t, y, td, i = (float(x) for x in (completions, targets, yards, tds, ints))
    clamp = lambda v: min(max(v, 0.0), 2.375)  # noqa: E731
    return 100 / 6 * (clamp((c / t - 0.3) * 5) + clamp((y / t - 3) * 0.25) + clamp(td / t * 20) + clamp(2.375 - i / t * 25))


def rank_corners(df: pd.DataFrame) -> pd.DataFrame:
    """The rank rule of `mart_cb_rankings` for ONE season x window (its Python twin). Needs per corner: is_cb,
    coverage_snaps, min_coverage_snaps, targets, completions_allowed, yards_allowed, tds_allowed, interceptions,
    exp_ypt_faced (the offenses' expected yards per target, weighted by his targets). Adds is_ranked,
    targets_per_coverage_snap, yards_per_target_allowed, adj_yards_per_target, passer_rating_allowed, z_*,
    quality_score, quality_rank (1 = hardest to throw on), n_ranked, quality_label."""
    d = df.copy()
    num = lambda c: pd.to_numeric(d[c], errors="coerce")  # noqa: E731
    snaps, tg, yds = num("coverage_snaps"), num("targets"), num("yards_allowed")
    d["targets_per_coverage_snap"] = (tg / snaps).where(snaps > 0)
    d["yards_per_target_allowed"] = (yds / tg).where(tg > 0)
    d["passer_rating_allowed"] = [passer_rating(r.completions_allowed, r.targets, r.yards_allowed, r.tds_allowed, r.interceptions)
                                  for r in d.itertuples()]
    exp = num("exp_ypt_faced")
    d["is_ranked"] = d["is_cb"].astype(bool) & (snaps >= num("min_coverage_snaps")) & (tg > 0) & exp.notna()
    pool = d[d["is_ranked"]]
    pool_ypt = pd.to_numeric(pool["yards_allowed"]).sum() / pd.to_numeric(pool["targets"]).sum() if not pool.empty else float("nan")
    pool_exp = (exp[d["is_ranked"]] * tg[d["is_ranked"]]).sum() / tg[d["is_ranked"]].sum() if not pool.empty else float("nan")
    d["adj_yards_per_target"] = (((d["yards_per_target_allowed"] - exp + pool_exp) * tg + pool_ypt * SHRINK_TARGETS)
                                 / (tg + SHRINK_TARGETS)).where(tg > 0)
    for z, col in (("z_targets", "targets_per_coverage_snap"), ("z_yards", "adj_yards_per_target"), ("z_rating", "passer_rating_allowed")):
        v = pd.to_numeric(d.loc[d["is_ranked"], col])
        d[z] = ((pd.to_numeric(d[col]) - v.mean()) / v.std(ddof=1)).where(d["is_ranked"])
    d["quality_score"] = (-(d["z_targets"] + d["z_yards"] + d["z_rating"]) / 3).where(d["is_ranked"])
    n = int(d["is_ranked"].sum())
    d["n_ranked"] = n
    d["quality_rank"] = d["quality_score"].rank(ascending=False, method="min").where(d["is_ranked"])
    d["quality_label"] = [cb_label(r, n) if not _blank(r) else None for r in d["quality_rank"]]
    return d


# ------------------------------------------------------------------------------------------ R-14: the words
def corner_ref(name, slot, rank, label, n) -> str:
    """'Mike Jackson (left corner, #37 of 74, solid)' / 'Will Lee III (right corner, unranked: too few snaps)'."""
    where = SLOT_WORDS.get(str(slot), "corner")
    if not _blank(rank) and not _blank(n):
        return f"{name} ({where}, #{int(rank)} of {int(n)}, {label})"
    return f"{name} ({where}, unranked: too few snaps)"


def cb_history(r, who: str) -> str:
    """What he did against this defense this season (before the week) and with the likely cover on the field
    before; empty when neither happened."""
    parts = []
    if int(r.get("games_vs_opp") or 0) > 0:
        parts.append(f"{line_text(r['receptions_vs_opp'], r['yards_vs_opp'], r['targets_vs_opp'])} against {r['opponent']} this season")
    if int(r.get("games_vs_cover") or 0) > 0:
        ev = str(r.get("evidence_vs_cover") or "")
        where = f"in games {who} played" if ev == "same_game" else f"with {who} on the field"
        parts.append(f"{line_text(r['receptions_vs_cover'], r['yards_vs_cover'], r['targets_vs_cover'])} {where} "
                     f"({seasons_text(r['first_season_vs_cover'], r['last_season_vs_cover'])})")
    if not parts:
        return ""
    text = "; ".join(parts)
    return " " + text[:1].upper() + text[1:] + "."


def cb_line(r) -> str:
    """One markdown line per receiver for the cornerback card (plan R-14), from one mart_cb_matchups row:
    '**Amon-Ra St. Brown** vs CAR: no clear side (37% of his targets one way, 33% the other): **Mike Jackson**
    (left corner, #37 of 74, solid) or **Will Lee III** (right corner, unranked: too few snaps).'"""
    r = pd.Series(r)
    name, opp, status = r["player_name"], r["opponent"], r["call_status"]
    head = f"**{name}** vs {opp}"
    n = r.get("cb_n_ranked")
    if status == "no depth chart yet":
        return f"{head}: no depth chart for {opp} yet, so no cornerback call."
    if status == "tight end":
        return f"{head}: tight ends mostly draw linebackers and safeties, so no cornerback call."
    if status == "too few targets":
        outs = " and ".join(corner_ref(r[f"{s}_name"], s.upper(), r.get(f"{s}_rank"), r.get(f"{s}_label"), n)
                            for s in ("lcb", "rcb") if not _blank(r.get(f"{s}_name")))
        return (f"{head}: too few targets since {int(r['season']) - 1} to tell which side he works "
                f"({int(r['located_targets'] or 0)} with a direction); {opp}'s outside corners: {outs or 'not listed'}.")
    cover = corner_ref(r["likely_cover_name"], r["likely_cover_slot"], r.get("cover_rank"), r.get("cover_label"), n)
    who = last_name(r["likely_cover_name"])
    if r.get("call_strength") == "clear":
        line = (f"{head}: likely across from **{cover}** — {pct(r['side_share'])} of his targets went to that side, "
                f"{pct(r['other_side_share'])} to the other.")
    else:
        other = ""
        if not _blank(r.get("other_cover_name")):
            s = str(r["other_cover_slot"]).lower()
            other = f" or **{corner_ref(r['other_cover_name'], r['other_cover_slot'], r.get(f'{s}_rank'), r.get(f'{s}_label'), n)}**"
        line = (f"{head}: no clear side ({pct(r['side_share'])} of his targets one way, {pct(r['other_side_share'])} "
                f"the other): **{cover}**{other}.")
    return line + cb_history(r, who)


def lean_text(r) -> str:
    """'Since the start of 2025, 199 of his targets had a direction: 33% to the left, 30% over the middle, 37% to
    the right (the offense's view).'"""
    r = pd.Series(r)
    n = int(r.get("located_targets") or 0)
    since = int(r["season"]) - 1
    if n == 0:
        return f"No targets with a direction since the start of {since}."
    return (f"Since the start of {since}, {n} of his targets had a direction: {pct(r['left_share'])} to the left, "
            f"{pct(r['middle_share'])} over the middle, {pct(r['right_share'])} to the right (the offense's view).")


def cover_split(games: pd.DataFrame) -> pd.DataFrame:
    """His points per game by the corner we named across from him (plan R-14 evidence), one row per receiver:
    games against a 'shutdown' corner vs every other game with a named corner. `games`: one row per played game
    with gsis_id, player_name, cover_label, points (the league's scoring)."""
    cols = ["gsis_id", "player_name", "ppg_vs_shutdown", "games_vs_shutdown", "ppg_vs_rest", "games_vs_rest"]
    if games is None or games.empty:
        return pd.DataFrame(columns=cols)
    g = games.assign(points=pd.to_numeric(games["points"], errors="coerce"), top=games["cover_label"].eq("shutdown"))
    out = []
    for (gid, name), part in g.groupby(["gsis_id", "player_name"], sort=False):
        top, rest = part[part["top"]], part[~part["top"]]
        out.append({"gsis_id": gid, "player_name": name,
                    "ppg_vs_shutdown": round(top["points"].mean(), 1) if len(top) else None, "games_vs_shutdown": len(top),
                    "ppg_vs_rest": round(rest["points"].mean(), 1) if len(rest) else None, "games_vs_rest": len(rest)})
    return pd.DataFrame(out, columns=cols)


def cover_split_text(r) -> str:
    """'vs shutdown corners 14.2 per game (5 games), vs the rest 17.9 (14)'."""
    r = pd.Series(r)
    def part(ppg, g):
        return "no games" if not int(g or 0) else f"{float(ppg):.1f} per game ({int(g)} game{'s' if int(g) != 1 else ''})"
    return f"vs shutdown corners {part(r['ppg_vs_shutdown'], r['games_vs_shutdown'])}, vs the rest {part(r['ppg_vs_rest'], r['games_vs_rest'])}"


# ------------------------------------------------------------------------------------------ R-15 picture
def dvp_selection(dvp: pd.DataFrame, value: str, mine: dict[str, str] | None = None, n: int = 8) -> pd.DataFrame:
    """The rows the ranked-bars view shows: the top `n` and bottom `n` defenses by `value` (points allowed per
    game, most first) and every defense in `mine` (defense -> your players facing it), always; ordered
    most-allowed first, with `gap_before` = how many defenses are skipped before the row."""
    mine = mine or {}
    d = dvp.dropna(subset=[value]).copy()
    d[value] = pd.to_numeric(d[value], errors="coerce")
    d = d.sort_values([value, "defense"], ascending=[False, True]).reset_index(drop=True)
    d["order"] = range(1, len(d) + 1)
    keep = (d["order"] <= n) | (d["order"] > len(d) - n) | d["defense"].isin(list(mine))
    out = d[keep].copy()
    out["gap_before"] = out["order"].diff().fillna(out["order"].iloc[0] if not out.empty else 1).astype(int) - 1
    out["is_mine"] = out["defense"].isin(list(mine))
    out["facing"] = out["defense"].map(lambda t: mine.get(t, ""))
    return out.reset_index(drop=True)


def dvp_heat_frame(dvp: pd.DataFrame, positions: list[str], value: str, rank: str,
                   marks: dict[str, dict[str, str]] | None = None, only_marked: bool = False) -> pd.DataFrame:
    """The heatmap's rows (plan R-15): one row per defense with, per position, the value (points allowed per game)
    and the rank (1 = gives up the most). Your opponents (`marks`: defense -> {position: your players}) are pinned
    at the top; within each group the defenses that give up the most across the positions (mean rank) come first.
    Columns: defense, is_mine, facing, mean_rank, then `<pos>` (value) and `<pos>_rank` per position."""
    marks = marks or {}
    d = dvp[dvp["position"].isin(positions)]
    vals = d.pivot_table(index="defense", columns="position", values=value, aggfunc="first")
    ranks = d.pivot_table(index="defense", columns="position", values=rank, aggfunc="first")
    out = pd.DataFrame(index=vals.index)
    for p in positions:
        out[p] = vals[p] if p in vals.columns else float("nan")
        out[f"{p}_rank"] = ranks[p] if p in ranks.columns else float("nan")
    out["mean_rank"] = out[[f"{p}_rank" for p in positions]].mean(axis=1)
    out = out.reset_index().rename(columns={"index": "defense"})
    out["is_mine"] = out["defense"].isin(list(marks))
    out["facing"] = out["defense"].map(lambda t: "; ".join(f"{who} ({p})" for p, who in marks.get(t, {}).items()))
    if only_marked:
        out = out[out["is_mine"]]
    out = out.sort_values(["is_mine", "mean_rank", "defense"], ascending=[False, True, True]).reset_index(drop=True)
    return out


# ------------------------------------------------------------------------------------------ R-11 side by side
def _pct1(v) -> str:
    return "—" if _blank(v) else f"{float(v) * 100:.1f}%"


def _rank(v) -> str:
    return "" if _blank(v) else f" (#{int(v)})"


def _num(p: dict, value: str, rank: str, fmt: str = "{:.1f}") -> str:
    return "—" if _blank(p.get(value)) else fmt.format(float(p[value])) + _rank(p.get(rank))


def comparison_rows(a: dict, b: dict) -> pd.DataFrame:
    """The side-by-side table (three columns: what, A, B). Every number the verdict uses is a row here. The defense
    rows are what each opponent allowed to the player's position in its games before the week: points per game,
    targets and carries per game (carries only when a runner is in the pair), yards per target or carry, the TD
    rate, points above what the offenses it faced usually score, each with its rank (#1 = gives up the most),
    and the profile in words."""
    runner = any(str(p.get("position")) in ("RB", "QB") for p in (a, b))

    def col(p: dict) -> list[str]:
        n_rows = 10 if runner else 9
        if _blank(p.get("opponent")):
            return ["—"] * n_rows
        venue = "vs" if bool(p.get("is_home")) else "@"
        cells = [
            "—" if _blank(p.get("proj_points")) else f"{float(p['proj_points']):.2f}",
            "—" if _blank(p.get("p10")) else f"{float(p['p10']):.1f} – {float(p['p90']):.1f}",
            f"{venue} {p['opponent']}",
            _num(p, "points_allowed_pg", "rank_points"),
            _num(p, "targets_allowed_pg", "rank_targets"),
        ]
        if runner:
            cells.append(_num(p, "carries_allowed_pg", "rank_carries"))
        cells += [
            _num(p, "yards_per_opp_allowed", "rank_efficiency"),
            "—" if _blank(p.get("td_rate_allowed")) else f"{_pct1(p['td_rate_allowed'])}{_rank(p.get('rank_td_rate'))}",
            _num(p, "adjusted_points_pg", "rank_adjusted", "{:+.1f}"),
            "—" if _blank(p.get("gives_up")) else str(p["gives_up"]),
        ]
        return cells

    what = ["Projection", "Floor – ceiling", "Opponent", "Points allowed / game", "Targets allowed / game"]
    if runner:
        what.append("Carries allowed / game")
    what += ["Yards per target or carry", "Touchdown rate", "Vs the offenses faced", "Gives up"]
    return pd.DataFrame({"What": what, str(a.get("player_name")): col(a), str(b.get("player_name")): col(b)})


REASON_TOP = 10             # a defense's component rank this good is named as the reason ("the 4th-most carries")


def _reason(p: dict) -> str | None:
    """The thing this player's defense gives up most, ranked (1 = the most): 'the 4th-most carries to RBs'; None when
    nothing ranks in the top REASON_TOP."""
    pos = str(p.get("position"))
    if pos == "RB":
        cands = [("carries", "rank_carries"), ("targets", "rank_targets"), ("yards per touch", "rank_efficiency"),
                 ("touchdowns per touch", "rank_td_rate")]
    elif pos == "QB":
        cands = [("throws and runs", "rank_opportunity"), ("yards per play", "rank_efficiency"),
                 ("touchdowns per play", "rank_td_rate")]
    else:
        cands = [("targets", "rank_targets"), ("yards per target", "rank_efficiency"), ("touchdowns per target", "rank_td_rate")]
    have = [(thing, int(p[col])) for thing, col in cands if not _blank(p.get(col))]
    if not have:
        return None
    thing, rank = min(have, key=lambda x: x[1])
    return f"{most(rank)} {thing} to {pos}s" if rank <= REASON_TOP else None


def matchup_lean(a: dict, b: dict) -> tuple[str | None, str]:
    """Which of the two matchups is kinder, from the defenses' opponent-adjusted rank (points allowed above what
    the offenses they faced usually score; 1 = gives up the most): (the leaning player's name, the reason), or
    (None, why not). Ranks within LEAN_RANKS of each other read as even."""
    ra, rb = a.get("rank_adjusted"), b.get("rank_adjusted")
    if _blank(ra) or _blank(rb):
        return None, "no games yet to read the matchups from"
    ra, rb = int(ra), int(rb)
    if abs(ra - rb) < LEAN_RANKS:
        return None, "the matchups are about even"
    lean, other = (a, b) if ra < rb else (b, a)
    why = _reason(lean)
    if why:
        return str(lean.get("player_name")), f"his defense gives up {why}"
    # no single thing stands out: say it with the opponent-adjusted ranks (the table's "Vs the offenses faced" row) —
    # PO (I-F, the decision-quality review): one rank direction everywhere, in words (cards.rank_words), never a bare #
    from .cards import rank_words
    return str(lean.get("player_name")), (
        f"{rank_words(min(ra, rb), lean.get('position'))} by his defense once the offenses it faced are counted, "
        f"{rank_words(max(ra, rb), other.get('position'))} by {last_name(other.get('player_name'))}'s")


def comparison_verdict(a: dict, b: dict, decision: dict | None = None) -> str:
    """One line in plain words from the same numbers as `comparison_rows` and the lineup cards (plan R-11):
    'The lineup says Tucker by 0.15; the matchup leans Monangai: his defense gives up the 4th-most carries to RBs.'
    `decision` = the lineup's call on this pair (gsis_id, alt_gsis_id, margin from lib.cards.decisions): the
    projection decides, the matchup is context."""
    na, nb = last_name(a.get("player_name")), last_name(b.get("player_name"))
    full = na == nb
    name = (lambda p: str(p.get("player_name"))) if full else (lambda p: last_name(p.get("player_name")))  # noqa: E731
    pa, pb = a.get("proj_points"), b.get("proj_points")
    if _blank(pa) or _blank(pb):
        missing = [name(p) for p in (a, b) if _blank(p.get("proj_points"))]
        return f"No projection this week for {' or '.join(missing)} (a bye, or no games yet), so no call."
    pair = {a.get("gsis_id"), b.get("gsis_id")}
    starter = None
    if decision and {decision.get("gsis_id"), decision.get("alt_gsis_id")} == pair and not _blank(decision.get("margin")):
        starter = a if a.get("gsis_id") == decision["gsis_id"] else b
        head = f"The lineup says {name(starter)} by {float(decision['margin']):.2f}"
    else:
        pa, pb = float(pa), float(pb)
        hi, lo = (a, b) if pa >= pb else (b, a)
        head = (f"{name(hi)} projects {abs(pa - pb):.2f} more ({max(pa, pb):.2f} vs {min(pa, pb):.2f})" if pa != pb
                else f"Both project {pa:.2f}")
    who, why = matchup_lean(a, b)
    if who is None:
        return f"{head}; {why}."
    lean = a if str(a.get("player_name")) == who else b
    if starter is not None and lean is starter:
        return f"{head}; the matchup agrees: {why}."
    return f"{head}; the matchup leans {name(lean)}: {why}."
