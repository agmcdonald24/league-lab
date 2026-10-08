"""IR-4 (Wave I-R, 2026-10-08): say what is verified, and carry uncertainty into the verdict (the dependability review's
P1 3; docs/METRICS.md § "What each number has been checked against (IR-4)"; docs/WORDS.md § "IR-4").

One object with every analysis (``/api/rankings``, ``/api/ros``, the free trade calculator, the trade evaluation and the
player card), the ``provenance`` key::

    {"model_version": "v3.6",            # the stored board's version for these weeks (ops.projections), else the code's
     "kd_model_version": "kd1.0" | None, # when kickers or defenses are in scope
     "published_at": ISO | None,         # the board's newest fit (max ops.projections.fitted_at): the data's publication
     "horizon": {"first": 5, "last": 18, "market_week": 5, "words": "weeks 5–18"},
     "checks": [{"span": "next" | "later" | "season_range" | "trade_gap", "position": "QB" | … | None,
                 "status": "graded" | "graded_weak" | "chance" | "not_graded", "words": str, "ref": str,
                 "mae": float | None, "order": float | None}],
     "status": the weakest status among the checks of the numbers shown,
     "beta": bool,                       # a trade verdict (the review: keep "beta" visible)
     "words": str}                       # the one quiet line the screen prints as it is

and, for a decision (``for_trade``, ``for_players``), ``caveats``: a list of ``{"kind", "effect": "withhold" | "soften",
"team", "players", "words"}`` with the stated rule (``RULE_WORDS``):

* a decision that depends on a quarterback whose team's starter is **unclear** (``starters.unclear``: the listing is
  disputed and nobody has corrected it), or on an MFL team-QB unit of that team, is **withheld**: the numbers stay, the
  recommendation does not. Why: the flag has been right 12 times in 27 (2025 – 2026 week 4, METRICS § "Who starts")
  and a starter's week against his backup's is about 10 points (Seattle's week 5: 15.0 against 4.3) — over a four-week
  window larger than the 10-point "about even" band every trade verdict uses.
* a decision that depends on a quarterback set **by hand** (``starters.corrected``) is **softened**: the verdict stands
  as a lean, never a firm call, with the sentence saying whom it assumes. Why: the correction rests on evidence (he led
  the team's dropbacks) but a person made it.
* a receiver, back or tight end of such a team carries no caveat: their projections do not read who throws to them
  (METRICS § "Who starts": ``FEATURES_BY_POSITION``, the QB inputs are the QB's only).

``apply(verdict_words, caveats)`` is the one call a verdict makes to honour the rule (the trade screen's owner adds it
where the decision is built; ``decisions.evaluate`` is not edited here).

Never raises on a request path: a failed read gives the code's model version, ``published_at`` None and the same
checks (they are constants with their METRICS reference, not a query).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from zoneinfo import ZoneInfo

import pandas as pd

from . import ros_grade, starters
from .db import query

log = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")

MODEL_VERSION = "v3.6"          # = league_lab.projections.MODEL_VERSION (pinned by api/tests/test_ir4.py)
KD_MODEL_VERSION = "kd1.0"      # = league_lab.kdef.KD_MODEL_VERSION
GRADED_ON = ros_grade.GRADED_ON

# ---- the board: one small aggregate of ops.projections (≈20k rows), cached 10 minutes in db.query's `sql` region
BOARD_SQL = """select model_version, min(week) as first_week, max(week) as last_week, max(fitted_at) as fitted_at
               from ops.projections
               where season = (select max(season) from ops.projections)
               group by model_version"""
BOARD_TTL = 600.0
EXISTS_SQL = "select to_regclass('ops.projections') is not null as ok"

# ---- what has been checked (docs/METRICS.md § "What each number has been checked against (IR-4)"): the horizon study
# (iq1_horizon.py, as of weeks 3 / 5 / 7 / 9 of 2021–2025, both house scorings; v3.5 = candidate ad, unchanged for RB /
# WR / TE by v3.6), the QB study (iq3_qb.py, v3.6 = hb1.0, against the naive baseline B2) and the K / DEF study
# (iq4_kd_horizon.py). "order" = Spearman, "mae" = points per game. Status rule (written 10:28 ET 2026-10-08, after
# these published numbers were known — it decides nothing, it labels): graded = order ≥ 0.50; graded_weak = order below
# 0.50, or no better than a simple baseline; chance = IQ-4's rule found the order no better than chance; not_graded =
# nothing has measured it.
REF_H = "docs/METRICS.md § v3.5 (IQ-1) and § v3.6 (IQ-3): the horizon study"
REF_KD = "docs/METRICS.md § Kickers and defenses beyond next week (IQ-4)"
REF_RANGE = "docs/METRICS.md § What each number has been checked against (IR-4)"
CHECKS: dict[tuple[str, str], dict] = {
    ("next", "QB"): {"status": "graded", "mae": 6.44, "order": 0.587, "ref": REF_H},
    ("next", "RB"): {"status": "graded", "mae": 4.52, "order": 0.686, "ref": REF_H},
    ("next", "WR"): {"status": "graded", "mae": 4.44, "order": 0.618, "ref": REF_H},
    ("next", "TE"): {"status": "graded", "mae": 3.25, "order": 0.599, "ref": REF_H},
    ("next", "K"): {"status": "graded_weak", "mae": 3.77, "order": 0.095, "ref": REF_KD},
    ("next", "DEF"): {"status": "graded_weak", "mae": 4.32, "order": 0.257, "ref": REF_KD},
    ("later", "QB"): {"status": "graded_weak", "mae": 7.41, "order": 0.495, "ref": REF_H},
    ("later", "RB"): {"status": "graded", "mae": 4.73, "order": 0.636, "ref": REF_H},     # IR-4's run: the rows with
    ("later", "WR"): {"status": "graded", "mae": 4.62, "order": 0.569, "ref": REF_H},     # a record (IQ-1's cells:
    ("later", "TE"): {"status": "graded", "mae": 3.42, "order": 0.545, "ref": REF_H},     # 4.70 / 4.59 / 3.41)
    ("later", "K"): {"status": "chance", "mae": 3.75, "order": 0.028, "ref": REF_KD},
    ("later", "DEF"): {"status": "chance", "mae": 4.78, "order": 0.040, "ref": REF_KD},
}
STATUS_ORDER = ("graded", "graded_weak", "chance", "not_graded")       # best to worst
STATUS_WORDS = {"graded": "graded", "graded_weak": "graded, weak", "chance": "no better than chance",
                "not_graded": "not graded"}
SPAN_WORDS = {"next": "next week", "later": "two to eight weeks ahead", "season_range": "the season total's range",
              "trade_gap": "the trade's range"}
POS_WORDS = {"QB": "quarterbacks", "RB": "running backs", "WR": "receivers", "TE": "tight ends", "K": "kickers",
             "DEF": "defenses"}
POSITIONS = tuple(POS_WORDS)


def _when(t) -> str | None:
    """2026-10-08T00:05Z -> "7 Oct, 8:05 pm ET" (the site's short date, Eastern time)."""
    try:
        ts = pd.Timestamp(t)
    except (TypeError, ValueError):
        return None
    if pd.isna(ts):
        return None
    ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts
    e = ts.tz_convert(ET)
    hour = e.hour % 12 or 12
    return f"{e.day} {e.strftime('%b')}, {hour}:{e.minute:02d} {'am' if e.hour < 12 else 'pm'} ET"


def board() -> dict:
    """{"model_version", "kd_model_version", "published_at", "versions": [{version, first_week, last_week}]} from the
    stored board; the code's versions and published_at None without it (never raises)."""
    out = {"model_version": MODEL_VERSION, "kd_model_version": KD_MODEL_VERSION, "published_at": None, "versions": [],
           "source": "code"}
    try:
        ok = query(EXISTS_SQL, ttl=BOARD_TTL)
        if ok.empty or not bool(ok.iloc[0, 0]):
            return out
        df = query(BOARD_SQL, ttl=BOARD_TTL)
    except Exception:  # noqa: BLE001 - a stamp must never cost a screen
        log.warning("provenance.board failed: the code's versions", exc_info=True)
        return out
    if df is None or df.empty:
        return out
    df = df.dropna(subset=["model_version"])
    kd = df[df["model_version"].astype(str).str.startswith("kd")]
    main = df[~df["model_version"].astype(str).str.startswith("kd")]
    if not main.empty:
        newest = main.sort_values("fitted_at").iloc[-1]
        out["model_version"] = str(newest["model_version"])
        out["source"] = "board"
    if not kd.empty:
        out["kd_model_version"] = str(kd.sort_values("fitted_at").iloc[-1]["model_version"])
    t = pd.to_datetime(df["fitted_at"], utc=True, errors="coerce").max()
    out["published_at"] = None if pd.isna(t) else t.isoformat()
    out["versions"] = [{"version": str(r.model_version), "first_week": int(r.first_week), "last_week": int(r.last_week)}
                       for r in main.sort_values("first_week").itertuples()]
    return out


def _int(v) -> int | None:
    try:
        return None if v is None or pd.isna(v) else int(v)
    except (TypeError, ValueError):
        return None


def horizon(first, last, market_week) -> dict:
    """The weeks the numbers cover: {"first", "last", "market_week", "words"}."""
    f, la, m = _int(first), _int(last), _int(market_week)
    if f is None and m is not None:
        f = m
    if la is None:
        la = f
    words = None if f is None else (f"week {f}" if la == f else f"weeks {f}–{la}")
    return {"first": f, "last": la, "market_week": m if m is not None else f, "words": words}


def spans(h: Mapping) -> list[str]:
    """Which graded spans the weeks touch: "next" (the market week), "later" (any week after it)."""
    f, la, m = h.get("first"), h.get("last"), h.get("market_week")
    if f is None:
        return []
    m = f if m is None else m
    out = []
    if f <= m <= (la if la is not None else f):
        out.append("next")
    if la is not None and la > m:
        out.append("later")
    return out


def checks(positions: Iterable[str], h: Mapping, *, season_range: bool = False, trade_gap: bool = False) -> list[dict]:
    pos = [p for p in dict.fromkeys(str(x).upper() for x in positions if x) if p in POSITIONS]
    out = []
    for sp in spans(h):
        for p in pos:
            c = CHECKS.get((sp, p))
            if c is None:
                continue
            out.append({"span": sp, "position": p, "status": c["status"], "mae": c["mae"], "order": c["order"],
                        "ref": c["ref"], "words": f"{POS_WORDS[p].capitalize()} {SPAN_WORDS[sp]}: "
                                                 f"{STATUS_WORDS[c['status']]} (order {c['order']:.2f})"})
    for flag, sp in ((season_range, "season_range"), (trade_gap, "trade_gap")):
        if flag:
            out.append({"span": sp, "position": None, "status": "not_graded", "mae": None, "order": None, "ref": REF_RANGE,
                        "words": f"{SPAN_WORDS[sp].capitalize()}: not graded"})
    return out


def worst(cs: list[dict]) -> str:
    if not cs:
        return "not_graded"
    return max((c["status"] for c in cs), key=STATUS_ORDER.index)


def _checked_words(cs: list[dict]) -> str:
    """"next week graded; two to eight weeks ahead graded, quarterbacks weak, kickers and defenses no better than
    chance; the season total's range not graded" — the positions named only where the status differs from the span's
    majority."""
    parts = []
    for sp in ("next", "later"):
        here = [c for c in cs if c["span"] == sp]
        if not here:
            continue
        base = "graded" if any(c["status"] == "graded" for c in here) else worst(here)
        odd: dict[str, list[str]] = {}
        for c in here:
            if c["status"] != base:
                odd.setdefault(c["status"], []).append(POS_WORDS[c["position"]])
        tail = "".join(f", {' and '.join(v)} {'weak' if s == 'graded_weak' else STATUS_WORDS[s]}" for s, v in odd.items())
        parts.append(f"{SPAN_WORDS[sp]} {STATUS_WORDS[base]}{tail}")
    for c in cs:
        if c["span"] in ("season_range", "trade_gap"):
            parts.append(f"{SPAN_WORDS[c['span']]} not graded")
    return "; ".join(parts)


def block(positions: Iterable[str], first=None, last=None, market_week=None, *, season_range: bool = False,
          trade_gap: bool = False, beta: bool = False) -> dict:
    """The ``provenance`` object (see the module's docstring)."""
    positions = [p for p in dict.fromkeys(str(x).upper() for x in (positions or []) if x)]
    if "ALL" in positions or "FLEX" in positions:
        extra = ("QB", "RB", "WR", "TE", "K", "DEF") if "ALL" in positions else ("RB", "WR", "TE")
        positions = [p for p in dict.fromkeys([*positions, *extra]) if p in POSITIONS]
    b = board()
    h = horizon(first, last, market_week)
    cs = checks(positions, h, season_range=season_range, trade_gap=trade_gap)
    kd = any(p in ("K", "DEF") for p in positions)
    version = f"Model {b['model_version']}" + (f" (kickers and defenses {b['kd_model_version']})" if kd else "")
    when = _when(b["published_at"])
    head = ("Beta · " if beta else "") + version + (f", data published {when}" if when else "")
    checked = _checked_words(cs)
    words = head + (f" · {h['words']}" if h["words"] else "") + (
        f" · checked on {GRADED_ON}: {checked}." if checked else ".")
    return {"model_version": b["model_version"], "kd_model_version": b["kd_model_version"] if kd else None,
            "published_at": b["published_at"], "horizon": h, "checks": cs, "status": worst(cs), "beta": bool(beta),
            "words": words}


# ------------------------------------------------------------------------------------------------ starter uncertainty
WITHHOLD, SOFTEN = "withhold", "soften"
RULE_WORDS = ("A decision that depends on a quarterback whose team's starter is unclear is withheld; one that depends on "
              "a starter set by hand is a lean, never a firm call.")
UNIT_POSITIONS = ("TMQB",)


def _last(name: str) -> str:
    return starters.last_name(name)


TEAM_ALIASES = {"LAR": "LA", "JAC": "JAX", "WSH": "WAS", "LVR": "LV", "OAK": "LV", "SD": "LAC", "STL": "LA"}


def _team(t) -> str:
    """One spelling of a team code (the schedule writes the Rams "LA"; MFL and Sleeper write "LAR")."""
    s = str(t or "").strip().upper()
    return TEAM_ALIASES.get(s, s)


def _who(p: Mapping) -> str:
    return str(p.get("player_name") or p.get("name") or p.get("gsis_id") or "this player")


def caveats_for(players: Iterable[Mapping], season, week) -> list[dict]:
    """The starter caveats of a decision that depends on ``players`` (dicts with ``gsis_id``, ``position``, ``team``,
    ``player_name``; an MFL team-QB unit: position TMQB and its ``team``), as of ``week`` (the decision's first week:
    the flag is the market week's). [] when nothing is flagged, or on any failure (a label never costs a decision)."""
    try:
        unc = starters.unclear(season, week) if season is not None and week is not None else {}
        cor = starters.corrected(season, week) if season is not None and week is not None else {}
    except Exception:  # noqa: BLE001
        log.warning("provenance.caveats_for(%s, %s): no flags", season, week, exc_info=True)
        return []
    if not unc and not cor:
        return []
    by_team_unc = {_team(v.get("team")): v for v in unc.values()}
    by_team_cor = {_team(v.get("team")): v for v in cor.values()}
    out: dict[tuple[str, str], dict] = {}
    for p in players or []:
        pos = str(p.get("position") or "").upper()
        gid = p.get("gsis_id")
        team = _team(p.get("team"))
        if pos == "QB" and gid:
            u, c = unc.get(str(gid)), cor.get(str(gid))
        elif pos in UNIT_POSITIONS and team:
            u, c = by_team_unc.get(team), by_team_cor.get(team)
        else:
            continue                       # their projections do not read who throws to them
        if u:
            k = ("starter_unclear", str(u.get("team")))
            cv = out.setdefault(k, {"kind": "starter_unclear", "effect": WITHHOLD, "team": u.get("team"), "players": [],
                                    "listed": u.get("listed"), "other": u.get("played")})
            cv["players"].append(_who(p))
        elif c:
            k = ("starter_set_by_hand", str(c.get("team")))
            cv = out.setdefault(k, {"kind": "starter_set_by_hand", "effect": SOFTEN, "team": c.get("team"), "players": [],
                                    "listed": c.get("listed"), "set": c.get("set")})
            cv["players"].append(_who(p))
    res = []
    for cv in out.values():
        team = starters.team_name(str(cv["team"]))
        who = " and ".join(dict.fromkeys(cv["players"]))
        if cv["kind"] == "starter_unclear":
            cv["words"] = (f"No verdict while {team}'s starter is unclear: {cv['listed']} is listed, the depth chart puts "
                           f"{cv['other']} first, and this depends on {who}. The numbers assume the listing.")
        else:
            listed = f", not the listed {cv['listed']}" if cv.get("listed") else ""
            cv["words"] = (f"{team}'s starter was set by hand ({cv['set']}{listed}); this depends on {who}, so read the "
                           f"verdict as a lean that assumes {_last(str(cv['set']))} starts.")
        res.append(cv)
    return sorted(res, key=lambda c: (c["effect"] != WITHHOLD, str(c["team"])))


def effect(caveats: Iterable[Mapping]) -> str | None:
    """The strongest effect: "withhold" over "soften"; None without a caveat."""
    eff = {c.get("effect") for c in caveats or []}
    return WITHHOLD if WITHHOLD in eff else SOFTEN if SOFTEN in eff else None


def apply(verdict: str | None, caveats: Iterable[Mapping]) -> dict:
    """The rule applied to a verdict: {"verdict": str | None (None = withheld), "effect", "words"} — withheld: no
    verdict, the caveat's sentence instead; softened: the verdict kept with the caveat's sentence after it (the screen
    shows it as a lean). The one call the trade decision makes."""
    cs = list(caveats or [])
    e = effect(cs)
    if e == WITHHOLD:
        return {"verdict": None, "effect": e, "words": " ".join(c["words"] for c in cs if c.get("effect") == WITHHOLD)}
    if e == SOFTEN:
        return {"verdict": verdict, "effect": e, "words": " ".join(c["words"] for c in cs)}
    return {"verdict": verdict, "effect": None, "words": None}


def _season_now() -> int:
    from league_lab import clock
    n = clock.now()
    return n.year if n.month >= 3 else n.year - 1


# ------------------------------------------------------------------------------------------------ one per route
def for_rankings(ans: Mapping) -> dict:
    """``/api/rankings``: the week view covers the market week; the season view weeks from_week–last_week."""
    if ans.get("week") is None:
        return {}
    pos = [ans.get("position") or "ALL"]
    if ans.get("view") == "season":
        p = block(pos, ans.get("from_week") or ans.get("week"), ans.get("last_week"), ans.get("week"), season_range=True)
    else:
        p = block(pos, ans.get("week"), ans.get("week"), ans.get("week"))
    return {"provenance": p}


def for_ros(ans: Mapping) -> dict:
    """``/api/ros``: weeks from_week–last_week (the first is the market week)."""
    f = ans.get("from_week")
    return {"provenance": block([ans.get("position") or "ALL"], f, ans.get("last_week"), f, season_range=True)}


def _players(ans: Mapping) -> list[dict]:
    out = []
    for side in ("give", "get"):
        v = ans.get(side)
        rows = v.get("players") if isinstance(v, Mapping) else v
        for p in rows or []:
            if isinstance(p, Mapping):
                out.append(dict(p))
    return out


def for_free_trade(ans: Mapping) -> dict:
    """The free calculator (no league): rest of season, the gap's range not graded; caveats for its quarterbacks."""
    w = ans.get("window") or {}
    ps = _players(ans)
    first = w.get("first")
    cvs = caveats_for(ps, _season_now(), first)
    out = {"provenance": block([p.get("position") for p in ps], first, w.get("last"), first, season_range=True,
                               trade_gap=True, beta=True),
           "caveats": cvs, "caveat_effect": effect(cvs), "caveat_rule": RULE_WORDS}
    v = ans.get("verdict")
    if cvs and isinstance(v, Mapping) and v.get("gap") is not None:     # the rule, applied to this calculator's verdict
        out["verdict"] = free_verdict(dict(v), cvs)
    return out


def free_verdict(v: dict, cvs: list[dict]) -> dict:
    """The free calculator's verdict under the rule: withheld — no lean (no colour), "No verdict: it depends on who
    starts for Tampa Bay."; softened — the words kept with "(a lean: it assumes Darnold starts)". The original words
    stay in ``words_unqualified``."""
    e = effect(cvs)
    out = {**v, "words_unqualified": v.get("words"), "caveat_effect": e}
    if e == WITHHOLD:
        teams = " and ".join(dict.fromkeys(starters.team_name(str(c["team"])) for c in cvs if c["effect"] == WITHHOLD))
        out.update(lean=None, even=None, words=f"No verdict: it depends on who starts for {teams}.")
    elif e == SOFTEN:
        who = " and ".join(dict.fromkeys(_last(str(c.get("set"))) for c in cvs if c["effect"] == SOFTEN))
        verb = "start" if " and " in who else "starts"
        out["words"] = f"{str(v.get('words') or '').rstrip('.')} (a lean: it assumes {who} {verb})."
    return out


def for_trade(ans: Mapping) -> dict:
    """The league trade evaluation (``POST /api/trades/evaluate``): the window's weeks, beta, the caveats."""
    weeks = [w for w in (ans.get("weeks") or []) if _int(w) is not None]
    first = _int(ans.get("week")) if ans.get("week") is not None else (min(weeks) if weeks else None)
    last = max(weeks) if weeks else first
    ps = _players(ans)
    cvs = caveats_for(ps, _season_now(), first)
    return {"provenance": block([p.get("position") for p in ps], min(weeks) if weeks else first, last, first,
                                trade_gap=True, beta=True),
            "caveats": cvs, "caveat_effect": effect(cvs), "caveat_rule": RULE_WORDS}


def for_players(players: Iterable[Mapping], season, week, *, last_week=None) -> dict:
    """A start / sit call, a waiver or a lineup: the same caveats and the provenance of ``week`` (… ``last_week``)."""
    ps = [dict(p) for p in players or []]
    cvs = caveats_for(ps, season, week)
    return {"provenance": block([p.get("position") for p in ps], week, last_week or week, week),
            "caveats": cvs, "caveat_effect": effect(cvs), "caveat_rule": RULE_WORDS}


def for_card(ans: Mapping) -> dict:
    """The player card: this week and the rest of the season of his position."""
    pos = ans.get("position")
    wk = None
    for k in ("week", "this_week", "market_week"):
        if _int(ans.get(k)) is not None:
            wk = _int(ans.get(k))
            break
    ros = ans.get("ros") if isinstance(ans.get("ros"), Mapping) else {}
    last = _int(ros.get("last_week")) if ros else None
    return {"provenance": block([pos] if pos else [], wk, last or wk, wk, season_range=bool(last))}


# ---- the routes' one-line hooks (each returns the answer with the keys added; never raises)
def _with(ans, fn):
    if not isinstance(ans, dict):
        return ans
    try:
        ans.update(fn(ans))
    except Exception:  # noqa: BLE001 - a stamp must never cost a screen
        log.warning("provenance: %s failed", getattr(fn, "__name__", fn), exc_info=True)
    return ans


def with_rankings(ans):
    return _with(ans, for_rankings)


def with_ros(ans):
    return _with(ans, for_ros)


def with_free_trade(ans):
    return _with(ans, for_free_trade)


def with_trade(ans):
    return _with(ans, for_trade)


def with_card(ans):
    return _with(ans, for_card)


# ---- PO (Wave I-R): the rule applied to IR-2's one decision object (`decision`), after `with_trade` put the caveats on
# the answer. Withheld: the verdict's place carries the caveat's sentence and there is no recommendation (the numbers
# stay); softened: the verdict stands and the recommendation is a lean that says whom it assumes. The unqualified
# words are kept beside them. Never raises; an answer without a decision or without caveats is returned as it is.
def rule_trade(ans):
    try:
        d = ans.get("decision") if isinstance(ans, dict) else None
        cvs = ans.get("caveats") if isinstance(ans, dict) else None
        if not isinstance(d, dict) or not cvs:
            return ans
        ruled = apply(d.get("verdict"), cvs)
        if ruled["effect"] is None:
            return ans
        d = dict(d)
        rec = dict(d.get("recommendation") or {})
        d["caveat"] = {"effect": ruled["effect"], "words": ruled["words"]}
        d["verdict_unqualified"] = d.get("verdict")
        rec["words_unqualified"], rec["label_unqualified"] = rec.get("words"), rec.get("label")
        if ruled["effect"] == WITHHOLD:
            d["verdict"] = ruled["words"]            # the caveat's own sentence: "No verdict while <team>'s starter is unclear: …"
            rec.update(credible=False, key="withheld", label="No recommendation",
                       words="The numbers below stand; the recommendation waits until the starter is known.")
            ans = {**ans, "verdict": d["verdict"]}
        else:
            rec["label"] = f"{rec.get('label') or 'A lean'} (a lean)"
            rec["words"] = f"{rec.get('words') or ''} {ruled['words']}".strip()
        d["recommendation"] = rec
        return {**ans, "decision": d}
    except Exception:  # noqa: BLE001 - provenance never breaks an answer
        log.warning("provenance.rule_trade failed", exc_info=True)
        return ans
# ---- end PO


# ------------------------------------------------------------------------------------------------ About (versions, checks)
# The model's versions this season (docs/METRICS.md, each section's date): About lists them; the sentence "its recipe
# stays the same all season" was false (v3.0 → v3.6 since week 4).
VERSIONS = (
    {"version": "v2.0", "date": "2026-09-26", "words": "Stat-line projections with a range: one small model per stat, "
                                                        "and your league's scoring turns the line into points."},
    {"version": "kd1.0", "date": "2026-09-30", "words": "Kickers and defenses get a model of their own."},
    {"version": "v3.0", "date": "2026-10-01", "words": "Who plays next to him: the starting quarterback, and whether "
                                                        "his team's top target or top ball carrier is out."},
    {"version": "v3.0 (cold starts)", "date": "2026-10-04", "words": "Rookies and players with few games start from "
                                                                      "what players like them usually do."},
    {"version": "v3.3", "date": "2026-10-05", "words": "A receiver on a new team is scaled by how such moves have "
                                                        "usually gone."},
    {"version": "v3.4", "date": "2026-10-07", "words": "A quarterback's passing touchdowns read the betting line."},
    {"version": "v3.5", "date": "2026-10-07", "words": "Weeks after next week, which have no betting line yet, use the "
                                                        "team's own scoring so far and next week's starters."},
    {"version": "v3.6", "date": "2026-10-07", "words": "A quarterback's weeks after next week blend the model with his "
                                                        "own per-game record."},
)
# The trade calculator's windows, graded per position (docs/METRICS.md § "What each number has been checked against
# (IR-4)"): each week's projection over the window scored against what happened that week (points per game, order =
# Spearman), pooled over the window's weeks; 2021–2025 as of weeks 3 / 5 / 7 / 9, both house scorings. "next4" = the
# next four weeks (horizons 1–4); "ros" = the rest of the season as far as the study reaches (horizons 1–8). QB: v3.6
# against the naive baseline B2 (his own per-game record with his role, the opponent and the line where there is one;
# iq3_qb.py); RB / WR / TE: v3.5 = v3.6 against his own points per game so far (ir4_useful.py --baseline, the rows
# where he has a record).
WINDOWS = {
    ("next4", "QB"): {"mae": 6.93, "order": 0.538, "base_mae": 7.00, "base_order": 0.537},
    ("next4", "RB"): {"mae": 4.64, "order": 0.664, "base_mae": 4.82, "base_order": 0.624},
    ("next4", "WR"): {"mae": 4.49, "order": 0.595, "base_mae": 4.64, "base_order": 0.560},
    ("next4", "TE"): {"mae": 3.35, "order": 0.570, "base_mae": 3.54, "base_order": 0.501},
    ("ros", "QB"): {"mae": 7.28, "order": 0.509, "base_mae": 7.33, "base_order": 0.510},
    ("ros", "RB"): {"mae": 4.71, "order": 0.642, "base_mae": 4.92, "base_order": 0.605},
    ("ros", "WR"): {"mae": 4.60, "order": 0.575, "base_mae": 4.75, "base_order": 0.546},
    ("ros", "TE"): {"mae": 3.40, "order": 0.553, "base_mae": 3.57, "base_order": 0.489},
}
NOT_GRADED = (
    "the ranges around a season total and around a trade's gap (they add weekly ranges as if the weeks were independent; "
    "the weekly ranges are graded one week ahead only)",
    "a trade of several players or across positions, and the lineup effect in your league (the useful-decision grade "
    "below is one-for-one, same position)",
    "kickers and defenses over the next four weeks or the rest of the season as a total (two to eight weeks ahead their "
    "order is no better than chance)",
    "quarterbacks' useful-decision grade on the current version (it was measured on the version before)",
)
# The useful-decision grade (ud1.0, docs/METRICS.md § "The useful decision grade"; scripts/analysis/ir4_useful.py,
# 2021–2025): on a close one-for-one (projected four-week totals within 20 %), how often the side the calculator favours
# scored more over those four weeks, against the side his own per-game record favours. QB rows are v3.5's.
USEFUL = {"QB": {"pairs": 3680, "rate": 0.594, "base": 0.615, "seasons": 0, "useful": False},
          "RB": {"pairs": 6320, "rate": 0.575, "base": 0.552, "seasons": 4, "useful": True},
          "WR": {"pairs": 8643, "rate": 0.584, "base": 0.539, "seasons": 4, "useful": True},
          "TE": {"pairs": 2939, "rate": 0.555, "base": 0.524, "seasons": 4, "useful": True}}
USEFUL_WORDS = ("Is the trade calculator right? On a close one-for-one between two players of the same position, graded "
                f"on {GRADED_ON}, the side it favours scored more over the next four weeks "
                f"{USEFUL['WR']['rate'] * 100:.0f} times in 100 at receiver, {USEFUL['RB']['rate'] * 100:.0f} at running "
                f"back and {USEFUL['TE']['rate'] * 100:.0f} at tight end — more often than the side his own per-game "
                f"record favours ({USEFUL['WR']['base'] * 100:.0f}, {USEFUL['RB']['base'] * 100:.0f} and "
                f"{USEFUL['TE']['base'] * 100:.0f}). At quarterback {USEFUL['QB']['rate'] * 100:.0f} in 100, but the side his own "
                f"per-game record favours did better ({USEFUL['QB']['base'] * 100:.0f}). 50 would be a coin flip.")
CHECKED_HEAD = ("What each number has been checked against: every projection below was scored on 2021–2025 seasons it "
                "never saw, against what happened that week. The order is the rank correlation (1 = perfect, 0 = no "
                "better than chance); the miss is in points per game.")


def _date_words(d: str) -> str:
    t = pd.Timestamp(d)
    return f"{t.day} {t.strftime('%b')}"


def about_block() -> dict:
    """``/api/about``'s ``versions`` and ``checked`` (About's two sections)."""
    b = board()
    weeks = []
    for v in b["versions"]:
        f, la = v["first_week"], v["last_week"]
        weeks.append(f"{'week' if f == la else 'weeks'} {f if f == la else f'{f}–{la}'}: {v['version']}")
    versions = [{**v, "date_words": _date_words(v["date"])} for v in VERSIONS]
    rows = []
    for pos in POSITIONS:
        r = {"position": pos}
        for sp in ("next", "later"):
            c = CHECKS.get((sp, pos))
            r[sp] = None if c is None else {"status": c["status"], "words": STATUS_WORDS[c["status"]], "mae": c["mae"],
                                            "order": c["order"]}
        for w in ("next4", "ros"):
            c = WINDOWS.get((w, pos))
            r[w] = None if c is None else dict(c)
        rows.append(r)
    return {"versions": {"current": b["model_version"], "kd": b["kd_model_version"], "published_at": b["published_at"],
                         "published_words": _when(b["published_at"]), "list": versions,
                         "by_week": "; ".join(weeks) if weeks else None,
                         "words": ("The model changes during the season, and every change is dated here. A week's "
                                   "projections are kept as they stood at its first kickoff, so earlier weeks keep the "
                                   "version they were made with.")},
            "checked": {"head": CHECKED_HEAD, "graded_on": GRADED_ON, "rows": rows, "not_graded": list(NOT_GRADED),
                        "windows_words": ("Next four weeks and rest of season: each week's projection in the window "
                                          "scored against that week (pooled over the window's weeks, not the window's "
                                          "total), against a simple baseline in brackets: his own points per game so "
                                          "far (for quarterbacks with his role, the opponent and the betting line)."),
                        "rule": RULE_WORDS, "useful": {"words": USEFUL_WORDS, "by_position": USEFUL}}}
