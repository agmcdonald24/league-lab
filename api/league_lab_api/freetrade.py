"""The trade calculator without a league (Wave I-N, IN-2): ``GET /api/trade-calc/free?league=ref:…&give=&get=``.

Two sides of up to six players each (gsis ids; picks are not in scope), priced in a reference key's scoring
(``refleague``: the closed family of scorings and league shapes). Each player's **value** is the one the player pane
shows for that key (``refleague.value_table``: rest-of-season points — this week to the last regular-season week —
above the best player a typical league of that shape leaves free at his position). The answer:

* per player: his value, rest-of-season points and their 80% range, his position rank (by value and by points), and
  his weekly outlook (this week's projection and range, points per game over the rest of the season);
* per side: the value added up, and the 80% range of the season points the side holds (each player's range read as
  a normal, players independent: the sum of the variances);
* the gap (what you get − what you give) with its 80% range; **about even** when that range holds zero, or the two
  sides are within 10 points or 10% (``trades.about_even``, the league calculator's rule) — and how much of the gap
  is one player;
* the roster-spot effect of an uneven trade, stated and not added in: the side getting fewer players gets a spot back,
  worth one replacement-level player (0 above replacement by definition, so the values do not move);
* what a league would add, in one line.

Nothing here is keyed to a user; the cache is ``refleague``'s (keyed by the 160 keys). The route is in the ``research``
bucket (``ratelimit.bucket_for``). Unknown is not zero: a player with no rest-of-season projection makes his side's sum
unknown, and the answer says who.
"""

from __future__ import annotations

import math
import re
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from league_lab import trades as T
from league_lab.sleeper_client import LeagueNotFound

from . import refleague, ros_grade  # ---- IQ-4: ros_grade

router = APIRouter()
PATH = "/api/trade-calc/free"
MAX_SIDE = 6
MAX_PARAM = 120                       # six gsis ids and their commas fit in 6 x 10 + 5 = 65 characters
GSIS = re.compile(r"^00-\d{7}$")
Z80 = 1.2815515655446004              # the 80% range of a normal: ± 1.28 standard deviations
NO_STORE = {"Cache-Control": "no-store"}
CACHE = {"Cache-Control": "private, max-age=120"}
LEAGUE_WORDS = "Open your league to see what this does to your lineup."
NAMES_SQL = """select gsis_id, player_name, position from analytics.dim_player where gsis_id = any(%s)"""


class Bad(ValueError):
    pass


def ids(text: str | None, side: str) -> list[str]:
    """A side's gsis ids from ``a,b,c`` (order kept, repeats once); Bad for a malformed id or more than six."""
    s = str(text or "")
    if len(s) > MAX_PARAM:
        raise Bad(f"{side}: at most {MAX_SIDE} players")
    out: list[str] = []
    for part in s.split(","):
        p = part.strip()
        if not p:
            continue
        if not GSIS.match(p):
            raise Bad(f"{side}: {p[:16]!r} is not a player id")
        if p not in out:
            out.append(p)
    if len(out) > MAX_SIDE:
        raise Bad(f"{side}: at most {MAX_SIDE} players")
    return out


def _num(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) or math.isinf(f) else f


def _sd(row: dict) -> float | None:
    lo, hi = _num(row.get("ros_p10")), _num(row.get("ros_p90"))
    return None if lo is None or hi is None else max(0.0, (hi - lo) / (2 * Z80))


def _this_week(key: str, first: int | None, gsis_ids: list[str]) -> dict[str, dict]:
    """This week's projection and 80% range (the priced week the pane shows), per gsis id."""
    if first is None or not gsis_ids:
        return {}
    try:
        from league_lab import anyleague as A

        from .db import query
        sh = refleague.shape(key)
        season, _f, _l = refleague._window()
        pr = A.price_week(query, sh.scoring_key, refleague.scoring_of(sh), refleague.slots_of(sh), season, first)
    except Exception:  # noqa: BLE001 - no priced week: the outlook says "not available", never 0
        return {}
    out: dict[str, dict] = {}
    for g in gsis_ids:
        p = _num(pr.proj.get(g)) if g in pr.proj.index else None
        if p is None:
            k = pr.kd.get("K")
            if k is not None and not k.empty and "unit_id" in k:
                hit = k[k["unit_id"].astype(str) == g]
                if not hit.empty:
                    r = hit.iloc[0]
                    out[g] = {"points": _num(r.get("proj_points")), "p10": _num(r.get("p10")), "p90": _num(r.get("p90"))}
            continue
        rg = pr.ranges.loc[g] if g in pr.ranges.index else None
        out[g] = {"points": round(p, 2), "p10": None if rg is None else _num(rg.get("p10")),
                  "p90": None if rg is None else _num(rg.get("p90"))}
    return out


def _player(g: str, row: dict | None, week: dict | None, first: int | None, names: dict) -> dict:
    if row is None:
        n = names.get(g, {})
        return {"gsis_id": g, "player_name": n.get("player_name") or g, "position": n.get("position"), "team": None,
                "value": None, "ros_points": None, "no_projection": True,
                "why": "no rest-of-season projection for him (unknown, not zero)"}
    games = int(row["ros_games"]) if _num(row.get("ros_games")) is not None else None
    ros = _num(row.get("ros_points"))
    wk = week or {}
    weeks = row.get("weeks_json") or []
    plays = any(int(w) == first for w, _p in weeks) if first is not None else False
    outlook = {"week": first, "points": wk.get("points"), "p10": wk.get("p10"), "p90": wk.get("p90"),
               "bye": first is not None and not plays,
               "per_game": round(ros / games, 1) if ros is not None and games else None, "games": games}
    return {"gsis_id": g, "player_name": row.get("player_name"), "position": row.get("position"),
            "team": row.get("team"), "value": _num(row.get("value")), "ros_points": ros,
            "ros_p10": _num(row.get("ros_p10")), "ros_p90": _num(row.get("ros_p90")),
            "value_rank_pos": int(row["value_rank_pos"]), "pos_rank": (int(row["ros_rank_pos"])
                                                                        if _num(row.get("ros_rank_pos")) is not None else None),
            "replacement": _num(row.get("replacement")), "outlook": outlook, "no_projection": False}


def _side(players: list[dict]) -> dict:
    known = [p for p in players if not p["no_projection"]]
    unknown = [p["player_name"] for p in players if p["no_projection"]]
    value = round(sum(p["value"] or 0.0 for p in known), 1) if not unknown else None
    pts = round(sum(p["ros_points"] or 0.0 for p in known), 1) if not unknown else None
    sds = [_sd(p) for p in known]
    sd = math.sqrt(sum(s * s for s in sds if s is not None)) if known and all(s is not None for s in sds) else None
    return {"players": players, "n": len(players), "value": value, "ros_points": pts,
            "low": None if sd is None or pts is None else round(max(0.0, pts - Z80 * sd), 1),
            "high": None if sd is None or pts is None else round(pts + Z80 * sd, 1),
            "sd": None if sd is None else round(sd, 2), "unknown": unknown}


def _pts(v: float) -> str:
    return f"{abs(v):.0f}"


def verdict(give: dict, get: dict) -> dict:
    """The gap in words with its uncertainty (see the module's doc). ``lean``: "get" (you get more), "give", or None."""
    if not give["n"] or not get["n"]:
        return {"even": None, "lean": None, "gap": None, "low": None, "high": None, "one_player": None,
                "words": "Add a player to each side to compare them."}
    if give["value"] is None or get["value"] is None:
        who = ", ".join(give["unknown"] + get["unknown"])
        return {"even": None, "lean": None, "gap": None, "low": None, "high": None, "one_player": None,
                "words": f"Not comparable yet: {who} has no rest-of-season projection (unknown, not zero)."}
    gap = round(get["value"] - give["value"], 1)
    sd = math.sqrt((give["sd"] or 0.0) ** 2 + (get["sd"] or 0.0) ** 2) if give["sd"] is not None and get["sd"] is not None else None
    low = None if sd is None else round(gap - Z80 * sd, 1)
    high = None if sd is None else round(gap + Z80 * sd, 1)
    inside = low is not None and high is not None and low <= 0 <= high
    even = bool(inside or T.about_even(give["value"], get["value"]))
    lean = None if even or gap == 0 else ("get" if gap > 0 else "give")
    rng = f" (likely {low:+.0f} to {high:+.0f})" if low is not None else ""
    if even:
        more = "more" if gap > 0 else "less"
        words = (f"About even: you get {_pts(gap)} points {more} season value than you give, inside the uncertainty"
                 f"{rng}." if abs(gap) >= 0.5 else f"About even: the two sides are worth the same{rng}.")
    elif lean == "get":
        words = f"You get more: {_pts(gap)} points of season value{rng}."
    else:
        words = f"You give more: {_pts(gap)} points of season value{rng}."
    one = None
    if abs(gap) >= 0.5:
        big = get if gap > 0 else give
        top = max((p for p in big["players"] if p["value"] is not None), key=lambda p: p["value"], default=None)
        if top is not None and top["value"]:
            share = min(1.0, top["value"] / abs(gap))
            one = {"gsis_id": top["gsis_id"], "player_name": top["player_name"], "value": top["value"],
                   "share": round(share, 2),
                   "words": (f"{top['player_name']} alone is worth more than the gap ({_pts(top['value'])} points)."
                             if share >= 1.0 else
                             f"{top['player_name']} is {_pts(top['value'])} of the {_pts(gap)}-point gap "
                             f"({share:.0%}).")}
    return {"even": even, "lean": lean, "gap": gap, "low": low, "high": high, "one_player": one, "words": words}


def roster_spots(n_give: int, n_get: int, facts: dict) -> dict | None:
    """The spot effect of an uneven trade: stated, never added to the values."""
    k = n_give - n_get
    if k == 0 or not n_give or not n_get:
        return None
    elig = refleague.SUPERFLEX_ELIG if facts.get("superflex") else refleague.FLEX_ELIG   # what an open spot is filled by
    repl = {p: v for p, v in (facts.get("replacement") or {}).items() if p in elig}
    pos, pts = max(repl.items(), key=lambda x: x[1]) if repl else (None, None)
    who = (facts.get("replacement_name") or {}).get(pos) if pos else None
    span = (f"weeks {facts.get('from_week')}–{facts.get('last_week')}" if facts.get("from_week") is not None else "")
    worth = (f"about {pts:.0f} points over {span} ({who}, the best {pos} such a league leaves free)"
             if pts is not None and who else "one replacement-level player")
    n = abs(k)
    spots = "spot" if n == 1 else "spots"
    if k > 0:
        words = (f"You get {n} roster {spots} back: worth one replacement-level player{' each' if n > 1 else ''} — "
                 f"{worth}, which is 0 above replacement, so the values above do not count it.")
    else:
        each = " each" if n > 1 else ""
        words = (f"You need {n} more roster {spots}: you drop {'players' if n > 1 else 'a player'} worth about one "
                 f"replacement-level player{each} — {worth}, 0 above replacement, so the values above do not count it.")
    return {"you_get_back": k, "replacement_points": pts, "replacement_position": pos, "replacement_name": who,
            "words": words}


def evaluate(key: str, give_ids: list[str], get_ids: list[str]) -> dict:
    sh = refleague.shape(key)
    both = set(give_ids) & set(get_ids)
    if both:
        raise Bad("a player cannot be on both sides")
    table, facts = refleague.value_table(sh.key)
    rows = refleague.value_of(sh.key, give_ids + get_ids)
    first = facts.get("from_week")
    week = _this_week(sh.key, first, list(rows))
    missing = [g for g in give_ids + get_ids if g not in rows]
    names: dict = {}
    if missing:
        try:
            from .db import query
            df = query(NAMES_SQL, (missing,))
            names = {str(r.gsis_id): {"player_name": r.player_name, "position": r.position} for r in df.itertuples()}
        except Exception:  # noqa: BLE001 - the id is named as it was sent
            names = {}
    give = _side([_player(g, rows.get(g), week.get(g), first, names) for g in give_ids])
    get = _side([_player(g, rows.get(g), week.get(g), first, names) for g in get_ids])
    v = verdict(give, get)
    return {"league_id": sh.key, "league_name": sh.words, "scoring_label": sh.words,
            "assumes": sh.assumes, "value_words": facts.get("words"),
            "pricing": refleague.pricing(sh, facts.get("references")),
            "window": {"first": first, "last": facts.get("last_week"),
                       "words": (f"weeks {first}–{facts.get('last_week')}" if first is not None else None)},
            "give": give, "get": get, "verdict": v,
            "roster_spots": roster_spots(give["n"], get["n"], facts),
            "league_words": LEAGUE_WORDS, "max_side": MAX_SIDE,
            "ros_grade": ros_grade.block([p.get("position") for p in give["players"] + get["players"]], calc=True)}   # ---- IQ-4


def _err(status: int, words: str, code: str) -> JSONResponse:
    return JSONResponse({"error": words, "detail": words, "code": code}, status_code=status, headers=NO_STORE)


@router.get(PATH)
def free_trade(league: str = refleague.DEFAULT, give: str = "", get: str = ""):
    if len(str(league or "")) > 40:
        return _err(404, "Not a scoring we know.", "not_found")
    if not refleague.is_reference(league):
        return _err(400, "This calculator is for browsing without a league: open your league's own calculator.",
                    "not_reference")
    try:
        sh = refleague.shape(league)
        g, t = ids(give, "give"), ids(get, "get")
        from . import provenance  # ---- IR-4: what is verified, the starter caveats
        out = provenance.with_free_trade(evaluate(sh.key, g, t))      # ---- IR-4
    except LeagueNotFound:
        return _err(404, "Not a scoring we know.", "not_found")
    except Bad as exc:
        return _err(400, str(exc), "bad_request")
    from .main import clean
    return JSONResponse(clean(out), headers=CACHE)
