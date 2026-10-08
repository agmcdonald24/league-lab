"""Who cannot play (Wave I-R, IR-1): one definition, one place (docs/METRICS.md § "Who cannot play").

Andrew, 2026-10-08: De'Von Achane, on injured reserve with a torn ACL, was the 21st running back on Rankings. The site
knew (the player card said "IR (knee - acl) · Sleeper, Sep 28"); the availability overlay was applied on My Week and the
card only, and the stored projections ``project`` writes knew nothing. This module is the definition every surface
reads, the stored gate ``projections.project`` applies before it writes, and the audit's rule.

**The definition** (``classify``):

* ``cannot_play`` (this week): on injured reserve, the PUP list, the non-football injury list, suspended, ruled Out,
  or on no NFL team (released, retired, unsigned). He gets no startable number this week.
* ``out_indefinitely``: on a reserve list with no return in sight — injured reserve, PUP, NFI, suspended. He gets no
  rest-of-season number until his status changes (never a guess at a return date).
* ``doubtful``: flagged, never removed. Questionable: untouched.

**The sources, and which one wins** (``pick``): Sleeper's player directory (``injury_status``, ``status``, ``team``,
dated by ``news_updated``; the nightly loads it into ``raw.sleeper_player``, the API reads it through the availability
snapshot) and ESPN's injuries feed (the API's overlay, dated by the item). The freshest explicit status wins. A game
status (Out / Doubtful / Questionable) dated before the previous week's last game is last week's and rules nothing
(``stale_game_status``). nflverse's weekly injury report is never a source here: midweek its newest row is last
week's game status (``mart_player_availability.injury_status`` read on a Wednesday is last Sunday's "Out"). nflverse's
weekly roster status of the week projected (``RES`` = reserve) is the fallback only when no Sleeper directory copy
exists at all — never "everyone is healthy".
"""

from __future__ import annotations

import json
import logging
import math
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime

import pandas as pd

log = logging.getLogger(__name__)

CANNOT_PLAY = frozenset({"IR", "PUP", "NFI", "SUS", "OUT", "NO_TEAM", "INACTIVE"})
OUT_INDEFINITELY = frozenset({"IR", "PUP", "NFI", "SUS"})
GAME_STATUS = frozenset({"OUT", "DOUBTFUL", "QUESTIONABLE"})
# ---- IS-1 (Wave I-S): a status that rarely plays. The rule was written before the numbers were read (docs/METRICS.md
# § "Who cannot play", av1.1): a game status whose players played in fewer than UNLIKELY_BELOW of cases is `unlikely`
# — he sits this week exactly as a player who cannot play (sits()), but is not out indefinitely. P_PLAY is the
# measured rate (2016-2025 regular seasons, QB / RB / WR / TE on nflverse's final report, "played" = any offensive or
# special-teams snap, or a stat): Doubtful 6 of 520 (1.2 %), Questionable 2,860 of 4,294 (66.6 %), Out 2 of 3,165.
UNLIKELY_BELOW = 0.25
P_PLAY = {"OUT": 0.0, "DOUBTFUL": 0.01, "QUESTIONABLE": 0.67}
UNLIKELY = frozenset(c for c, p in P_PLAY.items() if p < UNLIKELY_BELOW and c not in CANNOT_PLAY)   # {"DOUBTFUL"}
SITS_CODES = CANNOT_PLAY | UNLIKELY            # the codes sits() is true for: the older overlay's CANNOT_PLAY is this set
FLAGGED = frozenset(c for c in GAME_STATUS if c not in SITS_CODES)                                  # {"QUESTIONABLE"}
# ---- end IS-1
CODES = (*sorted(CANNOT_PLAY), "DOUBTFUL", "QUESTIONABLE", "ACTIVE")

LABEL = {"IR": "IR", "PUP": "PUP", "NFI": "NFI", "SUS": "Suspended", "OUT": "Out", "NO_TEAM": "No team",
         "INACTIVE": "Inactive", "DOUBTFUL": "Doubtful", "QUESTIONABLE": "Questionable", "ACTIVE": None}
REASON = {"IR": "on injured reserve", "PUP": "on the PUP list", "NFI": "on the non-football injury list",
          "SUS": "suspended", "OUT": "ruled out this week", "NO_TEAM": "not on an NFL team",
          "INACTIVE": "not on an active NFL roster", "DOUBTFUL": "doubtful this week"}
WEEK_WORDS = "{reason}: he will not play this week, so he is not ranked."
ROS_WORDS = "{reason}: no return date, so no rest-of-season value."
OUT_CALL = "{name} is out — {reason}."
# ---- IS-1: the words for a status that rarely plays, with its measured rate
UNLIKELY_WORDS = ("{label}: players listed {lower} have played about {n} in 100 times; not ranked this week.")
UNLIKELY_CALL = "{name} is {lower} — players listed {lower} have played about {n} in 100 times ({why})."
FLAG_WORDS = "{label}: players listed {lower} have played about {n} in 100 times; ranked as if he plays."

# Sleeper's codes (``injury_status``); NA has no settled meaning in Sleeper's directory: ignored
SLEEPER_INJURY = {"IR": "IR", "PUP": "PUP", "NFI": "NFI", "SUS": "SUS", "OUT": "OUT", "DNR": "OUT", "COV": "OUT",
                  "DOUBTFUL": "DOUBTFUL", "QUESTIONABLE": "QUESTIONABLE"}
# Sleeper's ``status`` when ``injury_status`` is empty (a reserve list it names in words)
SLEEPER_STATUS = {"injured reserve": "IR", "physically unable to perform": "PUP", "non-football injury": "NFI",
                  "suspended": "SUS"}
# nflverse's weekly roster status (the fallback only): RES = reserve (injured reserve / PUP / NFI), SUS = suspended
NFLVERSE_ROSTER = {"RES": "IR", "SUS": "SUS"}


# ------------------------------------------------------------------------------ the definition
def cannot_play(code: str | None) -> bool:
    return code in CANNOT_PLAY


def unlikely(code: str | None) -> bool:
    """IS-1: a status whose players played in fewer than ``UNLIKELY_BELOW`` of cases (Doubtful)."""
    return code in UNLIKELY


def out_indefinitely(code: str | None) -> bool:
    return code in OUT_INDEFINITELY


def ts(v) -> datetime | None:
    """A timestamp from ms / s since the epoch, an ISO string or a datetime (UTC); None when unreadable."""
    if v is None or (isinstance(v, float) and math.isnan(v)) or v == "":
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=UTC)
    if isinstance(v, str) and v.strip().isdigit():
        v = int(v.strip())
    if isinstance(v, int | float):
        try:
            return datetime.fromtimestamp(float(v) / (1000.0 if v > 1e11 else 1.0), UTC)
        except (OverflowError, OSError, ValueError):
            return None
    try:
        t = pd.Timestamp(v)
    except (ValueError, TypeError):
        return None
    if pd.isna(t):
        return None
    return (t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")).to_pydatetime()


def iso(d: datetime | None) -> str | None:
    return None if d is None else d.astimezone(UTC).isoformat().replace("+00:00", "Z")


def sleeper_code(p: Mapping) -> str | None:
    """A Sleeper directory entry's code: its ``injury_status`` first, then a reserve list its ``status`` names, then no
    team (``NO_TEAM``), else ``ACTIVE``. None = nothing usable (an NA code)."""
    inj = str(p.get("injury_status") or "").strip().upper()
    if inj and inj not in ("NA", "ACTIVE"):
        return SLEEPER_INJURY.get(inj)
    st = str(p.get("status") or "").strip().lower()
    if st in SLEEPER_STATUS:
        return SLEEPER_STATUS[st]
    if not str(p.get("team") or "").strip():
        return "NO_TEAM"
    if st == "inactive" and not inj:
        return "INACTIVE"          # ---- IS-1: on a team's books, not on its active roster (the overlay's rule, one place)
    return "ACTIVE" if not inj or inj == "ACTIVE" else None


def stale_game_status(code: str | None, as_of: datetime | None, prev_week_end: datetime | None) -> bool:
    """A game status (Out / Doubtful / Questionable) dated before the previous week's last game was that week's."""
    return code in GAME_STATUS and as_of is not None and prev_week_end is not None and as_of < prev_week_end


def entry(code: str, source: str, *, as_of=None, fetched_at=None, note: str | None = None, name: str | None = None) -> dict:
    """One source's word on one player."""
    return {"code": code, "source": source, "as_of": ts(as_of), "fetched_at": ts(fetched_at),
            "note": (str(note).strip().lower() or None) if note else None, "name": name}


def pick(cands: Iterable[dict | None], prev_week_end: datetime | None = None) -> dict | None:
    """The freshest explicit word: stale game statuses dropped, then the newest ``as_of`` (an undated entry only when
    nothing is dated; ESPN before Sleeper on an equal time)."""
    cs = [c for c in cands if c is not None and c.get("code") and not stale_game_status(c["code"], c.get("as_of"), prev_week_end)]
    if not cs:
        return None
    floor = datetime(1970, 1, 1, tzinfo=UTC)
    return max(cs, key=lambda c: (c.get("as_of") or floor, c.get("source") == "ESPN"))


def when(d: datetime | None) -> str:
    if d is None:
        return ""
    t = pd.Timestamp(d).tz_convert("America/New_York")
    return f"{t:%b} {t.day}"


def classify(e: dict | None) -> dict:
    """The public block: ``status`` (the label), ``code``, ``cannot_play``, ``out_indefinitely``, ``doubtful``, ``source``,
    ``as_of``, ``why`` ("IR (knee - acl) · Sleeper, Sep 28"), ``words`` (the reason in a sentence: the week's, or the
    season's for an out-indefinitely player)."""
    if e is None:
        return {"status": None, "code": None, "cannot_play": False, "out_indefinitely": False, "doubtful": False,
                "unlikely": False, "p_play": None, "source": None, "as_of": None, "why": None, "reason": None, "week_words": None, "ros_words": None}
    code = e["code"]
    label = LABEL.get(code) or code.title()
    note = f" ({e['note']})" if e.get("note") else ""
    stamp = f" · {e['source']}" + (f", {when(e.get('as_of'))}" if e.get("as_of") else "")
    reason = REASON.get(code)
    # ---- IS-1: a status that rarely plays sits this week (not out indefinitely); the measured rate goes with it
    p_play = P_PLAY.get(code)
    week_words = WEEK_WORDS.format(reason=reason[0].upper() + reason[1:]) if cannot_play(code) and reason else None
    if unlikely(code):
        week_words = UNLIKELY_WORDS.format(label=label, lower=label.lower(), n=round(100 * p_play))
    flag_words = (FLAG_WORDS.format(label=label, lower=label.lower(), n=round(100 * p_play))
                  if code in FLAGGED and p_play is not None else None)
    return {"status": LABEL.get(code), "code": code, "cannot_play": cannot_play(code),
            "out_indefinitely": out_indefinitely(code), "doubtful": code == "DOUBTFUL",
            "unlikely": unlikely(code), "p_play": p_play,
            "source": e.get("source"),
            "as_of": iso(e.get("as_of")), "fetched_at": iso(e.get("fetched_at")), "note": e.get("note"),
            "why": f"{label}{note}{stamp}", "reason": reason, "week_words": week_words, "flag_words": flag_words,
            "ros_words": ROS_WORDS.format(reason=reason[0].upper() + reason[1:]) if out_indefinitely(code) and reason else None}


def sits(block: dict | None) -> bool:
    """PO (Wave I-S): THE question every list, lineup, value and verdict asks of a status block — is he left out this
    week? True when he cannot play, or (IS-1) when his status rarely plays (``unlikely``). One function so that no
    caller keeps its own set of codes."""
    return bool(block) and bool(block.get("cannot_play") or block.get("unlikely"))


def out_sentence(name: str, st: dict) -> str:
    """"Who should I start?"'s sentence for a player who cannot play: "Achane is out — on injured reserve (IR (knee -
    acl) · Sleeper, Sep 28)." Never a call on him. IS-1: a player whose status rarely plays: "Hall is doubtful — players
    listed doubtful have played about 1 in 100 times (Doubtful (quadriceps) · Sleeper, Oct 7)." """
    if st.get("unlikely") and st.get("p_play") is not None:
        lab = str(LABEL.get(str(st.get("code"))) or st.get("status") or "").lower()
        return UNLIKELY_CALL.format(name=name, lower=lab, n=round(100 * float(st["p_play"])), why=st.get("why"))
    return OUT_CALL.format(name=name, reason=f"{st.get('reason') or 'he cannot play'} ({st.get('why')})")


# ------------------------------------------------------------------------------ the stored copy (the nightly's)
DIRECTORY_SQL = """
select coalesce(nullif(p.gsis_id, ''), m.gsis_id) as gsis_id, p.player_id as sleeper_id, p.full_name, p.position,
       p.team, p.status, p.injury_status, p.payload ->> 'news_updated' as news_updated,
       p.payload ->> 'injury_body_part' as body_part, p.fetched_at
from raw.sleeper_player as p
left join analytics.player_id_map as m on m.sleeper_id = p.player_id
"""   # every position: Sleeper lists some ball carriers at another one (Scott Matlock, LAC: "DT", on IR, an RB here)
PREV_WEEK_END_SQL = """select max(kickoff_at) as t from analytics.dim_game
                       where season = %s and week = %s and season_type = 'REG'"""


def _rows(conn, sql: str, params: tuple = ()) -> pd.DataFrame:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])


def directory_statuses(df: pd.DataFrame) -> dict[str, dict]:
    """{gsis: Sleeper's entry} from the directory's rows (``DIRECTORY_SQL``'s columns); a gsis id held by two Sleeper
    entries keeps the newer word."""
    out: dict[str, dict] = {}
    for r in df.to_dict("records"):
        g = r.get("gsis_id")
        if not isinstance(g, str) or not g:
            continue
        code = sleeper_code(r)
        if code is None:
            continue
        e = entry(code, "Sleeper", as_of=r.get("news_updated"), fetched_at=r.get("fetched_at"), note=r.get("body_part"),
                  name=r.get("full_name"))
        e["sleeper_id"] = r.get("sleeper_id")
        best = pick([out.get(g), e])
        out[g] = best if best is not None else e
    return out


def prev_week_end(conn, season: int, week: int) -> datetime | None:
    try:
        d = _rows(conn, PREV_WEEK_END_SQL, (int(season), int(week) - 1))
        return ts(d["t"].iloc[0]) if not d.empty else None
    except Exception:  # noqa: BLE001 - no schedule: a game status is taken at its word
        conn.rollback()
        return None


def stored(conn, season: int, week: int, roster_status: Mapping[str, str] | None = None) -> tuple[dict[str, dict], dict]:
    """({gsis: the stored word}, meta) for the week ``week`` of ``season`` from the Sleeper directory the nightly has
    just loaded (``raw.sleeper_player``: when tonight's fetch failed it still holds the last good copy, and meta says
    its date). No copy at all: the week's nflverse roster status (``roster_status`` {gsis: ACT / RES / ...}) — never
    "everyone is healthy". meta = {source, fetched_at, rows, fallback}."""
    meta: dict = {"source": "Sleeper directory", "fetched_at": None, "rows": 0, "fallback": False}
    try:
        d = _rows(conn, DIRECTORY_SQL)
    except Exception:  # noqa: BLE001 - no table (a fresh database): the fallback below
        conn.rollback()
        d = pd.DataFrame()
    pwe = prev_week_end(conn, season, week)
    if not d.empty:
        meta["rows"] = int(len(d))
        meta["fetched_at"] = iso(ts(pd.to_datetime(d["fetched_at"], utc=True).max()))
        out = {}
        for g, e in directory_statuses(d).items():
            if stale_game_status(e["code"], e.get("as_of"), pwe):
                continue
            out[g] = e
        return out, meta
    meta.update(source="nflverse weekly roster", fallback=True)
    out = {}
    for g, s in (roster_status or {}).items():
        code = NFLVERSE_ROSTER.get(str(s or "").upper())
        if code and isinstance(g, str):
            out[g] = entry(code, "NFL roster file")
    log.warning("availability gate: no Sleeper directory copy in raw.sleeper_player — the week's NFL roster status "
                "decides (%s players on a reserve list)", len(out))
    return out, meta


# ------------------------------------------------------------------------------ the stored projections (project)
NUMERIC_PREFIX = ("proj_",)
RANGE_COLS = ("proj_points", "p10", "p25", "p50", "p75", "p90")


def record_text(st: dict) -> str:
    """The frozen record's reason (``ops.projections.availability`` / ``ops.projection_lines.availability``): JSON."""
    keep = ("code", "status", "source", "as_of", "fetched_at", "note", "why", "out_indefinitely")
    return json.dumps({k: st.get(k) for k in keep}, sort_keys=True)


def gate_frame(df: pd.DataFrame, statuses: Mapping[str, dict], week: int) -> tuple[pd.DataFrame, list[dict]]:
    """A projection frame (``gsis_id``, ``week`` and its numbers) with the rule applied:

    * a player who cannot play in ``week``: his row of that week is kept with every number 0 (he scores nothing if he
      does not play — a known 0, so a lineup, a waiver gain, a trade's week and the outlook all sum the same rows)
      and ``availability`` = the reason (JSON, frozen with the week);
    * a player out indefinitely: his rows of every later week are removed (no rest-of-season number, no return date
      guessed).

    ``statuses`` = {gsis: ``classify``'d block}. Returns (frame, one dict per player changed)."""
    if df is None or df.empty or "gsis_id" not in df or "week" not in df:
        return df, []
    df = df.copy()
    if "availability" not in df:
        df["availability"] = None
    df["availability"] = df["availability"].astype(object)
    wk = pd.to_numeric(df["week"], errors="coerce")
    g = df["gsis_id"].astype(object)
    out_now = {k for k, s in statuses.items() if sits(s)}          # ---- IS-1: cannot play, or unlikely to play
    indef = {k for k, s in statuses.items() if s.get("out_indefinitely")}
    this = (wk == int(week)) & g.isin(out_now)
    nums = [c for c in df.columns if c.startswith(NUMERIC_PREFIX) or c in RANGE_COLS]
    report = []
    for k in sorted(set(g[this])):
        report.append({"gsis_id": k, **{c: statuses[k].get(c) for c in ("code", "why", "out_indefinitely")}})
    if this.any():
        df.loc[this, nums] = 0.0
        df.loc[this, "availability"] = [record_text(statuses[k]) for k in g[this]]
    later = (wk > int(week)) & g.isin(indef)
    df = df[~later].reset_index(drop=True)
    return df, report


def current_week(conn, season: int, now: datetime | None = None) -> int | None:
    """The week whose projections are still live: the first regular-season week whose first game has not kicked off."""
    now = now or datetime.now(UTC)
    d = _rows(conn, """select week, min(kickoff_at) as k from analytics.dim_game
                        where season = %s and season_type = 'REG' group by week order by week""", (int(season),))
    for w, k in zip(d["week"], d["k"], strict=True):
        t = ts(k)
        if t is not None and t > now:
            return int(w)
    return None


def drop_frame(df: pd.DataFrame, statuses: Mapping[str, dict], week: int, key: str = "unit_id") -> tuple[pd.DataFrame, list[str]]:
    """IS-1: a league-free K / DEF line table (``ops.kd_lines``, keyed by ``key``: a kicker's gsis id) with the rule
    applied by removing rows — the live week of a kicker who sits, every later week of one out indefinitely. Removed,
    not zeroed: ``ops.kd_ranges`` is the line priced plus fitted offsets, so a zero line would still carry a range; the
    house leagues' ``ops.projections`` K rows keep their 0 and the reason. Returns (frame, the ids removed)."""
    if df is None or df.empty or key not in df or "week" not in df:
        return df, []
    wk = pd.to_numeric(df["week"], errors="coerce")
    k = df[key].astype(str)
    now_out = {g for g, s in statuses.items() if sits(s)}
    indef = {g for g, s in statuses.items() if s.get("out_indefinitely")}
    gone = ((wk == int(week)) & k.isin(now_out)) | ((wk > int(week)) & k.isin(indef))
    return df[~gone].reset_index(drop=True), sorted(set(k[gone]))


def apply_to_project(conn, season: int, frames: dict[str, pd.DataFrame], target: pd.DataFrame | None = None,
                     now: datetime | None = None, drop: dict[str, pd.DataFrame] | None = None
                     ) -> tuple[dict[str, pd.DataFrame], dict]:
    """``projections.project``'s hook, before anything is written: every frame in ``frames`` (``pred``, ``lines``,
    ``ranges``) gated for the live week (``current_week``) by the stored copy (``stored``). Returns (frames, summary):
    the week, the source and its date, and every player changed (logged)."""
    week = current_week(conn, season, now)
    if week is None:
        return frames, {"week": None, "players": []}
    rs = {}
    if target is not None and not target.empty and "roster_status" in target:
        t = target[target["week"] == week]
        rs = dict(zip(t["gsis_id"], t["roster_status"], strict=False))
    raw, meta = stored(conn, season, week, rs)
    statuses = {g: classify(e) for g, e in raw.items()}
    statuses = {g: s for g, s in statuses.items() if sits(s)}      # ---- IS-1: the unlikely tier too (not indefinitely)
    out, players = {}, {}
    for name, df in frames.items():
        out[name], rep = gate_frame(df, statuses, week)
        for r in rep:
            players[r["gsis_id"]] = r
    kd_gone: list[str] = []
    for name, df in (drop or {}).items():                  # ---- IS-1: kickers' league-free lines (ops.kd_lines)
        out[name], ids = drop_frame(df, statuses, week)
        kd_gone += ids
    summary = {"week": week, **meta, "players": sorted(players.values(), key=lambda r: r["gsis_id"]),
               "kd_lines_removed": sorted(set(kd_gone))}
    log.info("availability gate: week %s, %s (copy of %s%s): %s players who cannot play or are unlikely to play get 0 this week (%s of them "
             "out indefinitely: no later weeks)", week, meta["source"], meta.get("fetched_at") or "no date",
             "; FALLBACK" if meta.get("fallback") else "", len(players),
             sum(1 for r in players.values() if r.get("out_indefinitely")))
    return out, summary


# ------------------------------------------------------------------------------ the audit's reader (a query function)
RECORD_SQL = """select gsis_id, availability from (
                    select distinct on (gsis_id) gsis_id, to_jsonb(l) ->> 'availability' as availability
                    from ops.projection_lines as l where season = %s and week = %s
                    order by gsis_id, (frozen_source is not null) desc, fitted_at desc nulls last) as x
                where availability is not null"""


def statuses_from_query(query, season: int, week: int, *, with_record: bool = False) -> tuple[dict[str, dict], dict]:
    """({gsis: ``classify`` block} of every player with a status, meta) from what the database holds of the site's
    sources: the Sleeper directory (``raw.sleeper_player``: the nightly's copy, stale game statuses dropped) and the
    nightly's stored record (``ops.projection_lines.availability``) — the freshest word wins, as on the site. ESPN's
    feed is the API's alone (not on the database)."""
    meta = {"source": "Sleeper directory", "fetched_at": None, "rows": 0}
    try:
        d = query(DIRECTORY_SQL, ())
    except Exception:  # noqa: BLE001
        d = pd.DataFrame()
    try:
        pw = query(PREV_WEEK_END_SQL, (int(season), int(week) - 1))
        pwe = ts(pw["t"].iloc[0]) if not pw.empty else None
    except Exception:  # noqa: BLE001
        pwe = None
    cands: dict[str, list[dict]] = {}
    if not d.empty:
        meta["rows"] = int(len(d))
        meta["fetched_at"] = iso(ts(pd.to_datetime(d["fetched_at"], utc=True).max()))
        for g, e in directory_statuses(d).items():
            cands.setdefault(g, []).append(e)
    # ---- IS-1: the audit reads the directory alone (a guard must not read the field it guards); the stored record only
    # when a caller asks for it
    rec = pd.DataFrame(columns=["gsis_id", "availability"])
    if with_record:
        try:
            rec = query(RECORD_SQL, (int(season), int(week)))
        except Exception:  # noqa: BLE001 - before the first gated nightly
            rec = pd.DataFrame(columns=["gsis_id", "availability"])
    for g, a in zip(rec["gsis_id"], rec["availability"], strict=True):
        try:
            j = json.loads(a) if isinstance(a, str) else None
        except ValueError:
            j = None
        if isinstance(g, str) and isinstance(j, dict) and j.get("code") in CODES:
            cands.setdefault(g, []).append(entry(j["code"], str(j.get("source") or "Sleeper"), as_of=j.get("as_of"),
                                                 fetched_at=j.get("fetched_at"), note=j.get("note")))
    out = {}
    for g, cs in cands.items():
        best = pick(cs, pwe)
        if best is not None and best["code"] != "ACTIVE":
            out[g] = classify(best)
    return out, meta
