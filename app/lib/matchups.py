"""Matchups page logic (plan R-14 cornerbacks, R-15 defense vs position, R-11 two players side by side).

Pure helpers shared by `app/pages/5_Matchups.py` and `tests/test_matchups.py`: every sentence a card shows
is built here from mart rows, so the words and the table next to them carry the same numbers.
Marts: `mart_cb_matchup_week`, `mart_cb_coverage`, `mart_receiver_vs_cb`, `mart_defense_position_profile`,
`mart_defense_vs_position_current`, `mart_player_week_projections` (docs/METRICS.md § Cornerback matchups,
§ Matchup comparison)."""

from __future__ import annotations

import pandas as pd

SLOT_WORDS = {"LCB": "left corner", "RCB": "right corner", "NB": "slot corner"}
GIVES_UP_WORDS = {
    "volume": "gives up volume",
    "big plays": "gives up big plays",
    "volume and big plays": "gives up volume and big plays",
    "little of either": "gives up little of either",
    "about average": "is about average",
}
CLOSE_POINTS = 1.0          # projections closer than this are "close" (the cards' coin-flip line is 1 point too)
CEILING_POINTS = 1.0        # a ceiling / floor gap worth naming


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
    rec, yds, tgt = int(rec or 0), int(yds or 0), int(tgt or 0)
    return f"{rec} catch{'es' if rec != 1 else ''} for {yds} yards on {tgt} target{'s' if tgt != 1 else ''}"


# ------------------------------------------------------------------------------------------ R-14 cornerbacks
def cb_rank_text(r) -> str:
    """'thrown at often: #67 of 82 corners, 1 = least' / 'not ranked: under 380 pass plays in coverage since 2025'."""
    if bool(r.get("cover_is_ranked")) and not _blank(r.get("cover_rank_targets_per_snap")):
        rank, n = int(r["cover_rank_targets_per_snap"]), int(r["cb_n_ranked"])
        return f"{rank_words(rank, n)}: #{rank} of {n} corners, 1 = least"
    if _blank(r.get("cb_min_coverage_snaps")):
        return "not ranked"
    return f"not ranked: under {int(r['cb_min_coverage_snaps'])} pass plays in coverage since {int(r['season']) - 1}"


def cb_history(r) -> str:
    """His line against this defense this season, and with the likely cover on the field before."""
    opp = r["opponent"]
    parts = []
    if int(r.get("games_vs_opp") or 0) > 0:
        parts.append(f"{line_text(r['receptions_vs_opp'], r['yards_vs_opp'], r['targets_vs_opp'])} against {opp} this season")
    else:
        parts.append(f"no game against {opp} yet this season")
    if int(r.get("games_vs_cover") or 0) > 0 and not _blank(r.get("likely_cover_name")):
        ev = str(r.get("evidence_vs_cover") or "")
        who = last_name(r["likely_cover_name"])
        where = (f"in games {who} played" if ev == "same_game" else f"with {who} on the field")
        parts.append(f"{line_text(r['receptions_vs_cover'], r['yards_vs_cover'], r['targets_vs_cover'])} {where} "
                     f"({seasons_text(r['first_season_vs_cover'], r['last_season_vs_cover'])})")
    text = "; ".join(parts)
    return text[:1].upper() + text[1:] + "."


def cb_line(r) -> str:
    """One markdown line per receiver for the cornerback card (plan R-14):
    'Amon-Ra St. Brown vs CAR: likely across from him Mike Jackson (CAR's left corner; #67 of 82 corners by how
    rarely he is thrown at); he also works inside, against Jaycee Horn. No game against CAR yet this season; …'"""
    r = pd.Series(r)
    name, opp, status = r["player_name"], r["opponent"], r["call_status"]
    head = f"**{name}** vs {opp}"
    if status == "no depth chart yet":
        return f"{head}: no depth chart for {opp} yet, so no cornerback call."
    if status == "tight end":
        nb = f" {opp}'s slot corner, if he lines up wide: {r['nb_name']}." if not _blank(r.get("nb_name")) else ""
        return f"{head}: tight ends mostly draw linebackers and safeties, so no cornerback call.{nb}"
    if status == "too few targets":
        outs = " and ".join(str(n) for n in (r.get("lcb_name"), r.get("rcb_name")) if not _blank(n))
        return (f"{head}: too few targets since last season to tell which side he plays ({int(r['located_targets'] or 0)}); "
                f"{opp}'s outside corners are {outs or 'not listed'}.")
    slot = SLOT_WORDS.get(str(r["likely_cover_slot"]), "corner")
    line = f"{head}: likely across from him **{r['likely_cover_name']}** ({opp}'s {slot}; {cb_rank_text(r)})"
    if not _blank(r.get("inside_cover_name")):
        line += f"; he also works inside, against {r['inside_cover_name']}"
    return f"{line}. {cb_history(r)}"


def lean_text(r) -> str:
    """'Since the start of 2025, 199 of his targets had a direction: 33% to his left, 30% over the middle, 37% to his right.'"""
    r = pd.Series(r)
    n = int(r.get("located_targets") or 0)
    since = int(r["season"]) - 1
    if n == 0:
        return f"No targets with a direction since the start of {since}."
    pct = lambda v: f"{float(v) * 100:.0f}%"   # noqa: E731
    return (f"Since the start of {since}, {n} of his targets had a direction: {pct(r['left_share'])} to the left, "
            f"{pct(r['middle_share'])} over the middle, {pct(r['right_share'])} to the right (the offense's view).")


# ------------------------------------------------------------------------------------------ R-15 picture
def dvp_selection(dvp: pd.DataFrame, value: str, mine: dict[str, str] | None = None, n: int = 8) -> pd.DataFrame:
    """The rows the defense-vs-position chart shows: the top `n` and bottom `n` defenses by `value` (points
    allowed per game, most first) and every defense in `mine` (defense -> your players facing it), always;
    ordered most-allowed first, with `gap_before` = how many defenses are skipped before the row."""
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


# ------------------------------------------------------------------------------------------ R-11 side by side
def _pct(v) -> str:
    return "—" if _blank(v) else f"{float(v) * 100:.1f}%"


def _rank(v) -> str:
    return "" if _blank(v) else f" (#{int(v)})"


def rank_words(rank, n) -> str:
    """How often a corner is thrown at, from his rank (1 = thrown at least): the first third 'rarely thrown at',
    the last third 'thrown at often', else 'thrown at about average'."""
    rank, n = int(rank), int(n)
    if rank <= n / 3:
        return "rarely thrown at"
    if rank > 2 * n / 3:
        return "thrown at often"
    return "thrown at about average"


def comparison_rows(a: dict, b: dict) -> pd.DataFrame:
    """The side-by-side table (three columns: what, A, B). Every number the verdict uses is a row here. The defense
    rows: points allowed per game to the position, opportunities (touches + targets; a QB's attempts + carries) per
    game, yards per opportunity, TD rate, points above what the offenses it faced usually score, each with its rank
    (#1 = gives up the most), and the profile in words."""
    def col(p: dict) -> list[str]:
        if _blank(p.get("opponent")):
            return ["—"] * 9
        venue = "vs" if bool(p.get("is_home")) else "@"
        adj = p.get("adjusted_points_pg")
        return [
            "—" if _blank(p.get("proj_points")) else f"{float(p['proj_points']):.2f}",
            "—" if _blank(p.get("p10")) else f"{float(p['p10']):.1f} – {float(p['p90']):.1f}",
            f"{venue} {p['opponent']}",
            "—" if _blank(p.get("rank_points")) else f"{float(p['points_allowed_pg']):.1f}{_rank(p['rank_points'])}",
            "—" if _blank(p.get("opps_allowed_pg")) else f"{float(p['opps_allowed_pg']):.1f}{_rank(p['rank_opportunity'])}",
            "—" if _blank(p.get("yards_per_opp_allowed")) else f"{float(p['yards_per_opp_allowed']):.1f}{_rank(p['rank_efficiency'])}",
            "—" if _blank(p.get("td_rate_allowed")) else f"{_pct(p['td_rate_allowed'])}{_rank(p['rank_td_rate'])}",
            "—" if _blank(adj) else f"{float(adj):+.1f}{_rank(p['rank_adjusted'])}",
            "—" if _blank(p.get("gives_up")) else str(p["gives_up"]),
        ]
    what = ["Projection", "Floor – ceiling", "Opponent", "Points allowed / game", "Volume allowed / game",
            "Yards per touch", "Touchdown rate", "Vs the offenses faced", "Gives up"]
    return pd.DataFrame({"What": what, str(a.get("player_name")): col(a), str(b.get("player_name")): col(b)})


def comparison_verdict(a: dict, b: dict) -> str:
    """One line in plain words from the same numbers as `comparison_rows`:
    'Both project close (12.1 vs 11.8); Olave's defense gives up volume, Nacua's gives up big plays — Nacua has the
    higher ceiling (24.0 vs 21.3).'"""
    na, nb = last_name(a.get("player_name")), last_name(b.get("player_name"))
    if na == nb:
        na, nb = str(a.get("player_name")), str(b.get("player_name"))
    pa, pb = a.get("proj_points"), b.get("proj_points")
    if _blank(pa) or _blank(pb):
        missing = [x for x, p in ((na, pa), (nb, pb)) if _blank(p)]
        return f"No projection this week for {' or '.join(missing)} (a bye, or no games yet), so no call."
    pa, pb = float(pa), float(pb)
    # two decimals like the lineup cards: 9.13 vs 9.07 must not read as "9.1 vs 9.1"
    if abs(pa - pb) < CLOSE_POINTS:
        head = f"Both project close ({pa:.2f} vs {pb:.2f})"
    else:
        hi = na if pa > pb else nb
        head = f"{hi} projects {abs(pa - pb):.2f} more ({max(pa, pb):.2f} vs {min(pa, pb):.2f})"
    ga, gb = a.get("gives_up"), b.get("gives_up")
    if _blank(ga) or _blank(gb):
        matchup = ""
    elif ga == gb:
        matchup = f"both defenses {GIVES_UP_WORDS.get(ga, ga).replace('gives', 'give').replace('is about', 'are about')}"
    else:
        matchup = f"{na}'s defense {GIVES_UP_WORDS.get(ga, ga)}, {nb}'s {GIVES_UP_WORDS.get(gb, gb)}"
    tail = []
    ceil_who = floor_who = None
    ca, cb_ = a.get("p90"), b.get("p90")
    if not (_blank(ca) or _blank(cb_)) and abs(float(ca) - float(cb_)) >= CEILING_POINTS:
        ceil_who = na if float(ca) > float(cb_) else nb
        ceil = f"({max(float(ca), float(cb_)):.1f} vs {min(float(ca), float(cb_)):.1f})"
    fa, fb = a.get("p10"), b.get("p10")
    if not (_blank(fa) or _blank(fb)) and abs(float(fa) - float(fb)) >= CEILING_POINTS:
        floor_who = na if float(fa) > float(fb) else nb
        flo = f"({max(float(fa), float(fb)):.1f} vs {min(float(fa), float(fb)):.1f})"
    if ceil_who and ceil_who == floor_who:
        tail.append(f"{ceil_who} has both the higher ceiling {ceil} and the safer floor {flo}")
    else:
        if ceil_who:
            tail.append(f"{ceil_who} has the higher ceiling {ceil}")
        if floor_who:
            tail.append(f"{floor_who} the safer floor {flo}")
    text = head + (f"; {matchup}" if matchup else "")
    if tail:
        text += " — " + ", ".join(tail)
    return text + "."
