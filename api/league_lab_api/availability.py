"""The availability overlay (Wave I-0, I0-A): who can play, as of minutes ago, applied at request time.

The nightly build takes availability from the NFL injury report via nflverse (rebuilt once a day; nflverse's file lags
the report by hours). Justin Jefferson was ruled Out at 2:35 PM ET on a Friday and My Week still told Andrew to start
him that evening. This module overlays two fresher sources on whatever the build said:

* **ESPN's injuries feed** (``league_lab.injury_feed``): every 15 minutes on a game day, hourly otherwise.
* **Sleeper's player directory** (``sleeper_client.players()``, cached a day: Sleeper asks for one call a day):
  ``injury_status`` (Out / Doubtful / Questionable / IR / PUP / Sus / DNR ...) and ``status`` (Inactive = not on an
  active NFL roster), dated by its ``news_updated``.

ESPN athletes are mapped to gsis through the directory's ``espn_id`` first, the id table (``db_playerids.csv``) second.

**The rule.** Per player the newer of the two sources wins (ESPN's ``date``; Sleeper's ``news_updated`` — a Sleeper
entry without one never beats an ESPN entry). *Cannot play* = Out, Doubtful, IR, PUP, NFI, Suspended, Inactive;
*flagged* = Questionable. A status from a copy fetched before the nightly build ran is ignored by the lineup (the build
already saw that news or newer). ``now(gsis_ids)`` answers it; ``checked_at()`` says when ESPN was last read.

**Where it applies** (marked ``# ---- I0-A`` blocks): My Week (``apply_to_rows``: the lineup re-solved with
``lineup.solve`` when a starter or bench player can no longer play, or a player the build sat as Out can play again;
the changed rows carry a chip and a reason; ``changes`` says who moved, in words), Trends (no Out / IR / PUP /
suspended player in "due" or "hot"), Waivers (no claim of a player who cannot play; one QB per NFL team), trades (an
Out player is worth 0 this week), rest of season (``injury_status``), ``/api/status``.

Off when ``LEAGUE_LAB_AVAILABILITY=off``, and in fixture mode unless ESPN has fixtures too (``LEAGUE_LAB_ESPN_FIXTURES``):
a test or this sandbox never calls ESPN.
"""

from __future__ import annotations

import csv
import math
import os
import threading
import time
from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from league_lab import anyleague as A
from league_lab import injury_feed as F
from league_lab import lineup as LU
from league_lab import memo, player_ids, provider_trouble  # ---- IP-5: provider_trouble

from .db import query

SWITCH_ENV = "LEAGUE_LAB_AVAILABILITY"
IDS_CSV_ENV = "LEAGUE_LAB_PLAYER_IDS_CSV"
CANNOT_PLAY = frozenset({"OUT", "DOUBTFUL", "IR", "PUP", "NFI", "SUS", "INACTIVE"})
NOT_IN_TRENDS = frozenset({"OUT", "IR", "PUP", "NFI", "SUS", "INACTIVE"})        # Trends: Doubtful stays listed
FLAGGED = frozenset({"QUESTIONABLE"})
LABEL = {"OUT": "Out", "DOUBTFUL": "Doubtful", "QUESTIONABLE": "Questionable", "IR": "IR", "PUP": "PUP", "NFI": "NFI",
         "SUS": "Suspended", "INACTIVE": "Inactive", "ACTIVE": None}
WORDS = {"OUT": "is out", "DOUBTFUL": "is doubtful", "IR": "is on injured reserve", "PUP": "is on the PUP list",
         "NFI": "is on the non-football injury list", "SUS": "is suspended", "INACTIVE": "is not on the active roster"}
CHIP = {"OUT": "OUT", "DOUBTFUL": "DOUBTFUL", "IR": "IR", "PUP": "IR", "NFI": "IR", "SUS": "OUT", "INACTIVE": "OUT"}
# the build's own "cannot play" reasons that an injury status explains (bye, IR slot, taxi ... are not overlaid)
BUILD_STATUS_REASONS = {"Out": "OUT", "Doubtful": "DOUBTFUL", "NFL injured reserve": "IR"}
SLEEPER_CODES = {"OUT": "OUT", "DOUBTFUL": "DOUBTFUL", "QUESTIONABLE": "QUESTIONABLE", "IR": "IR", "PUP": "PUP",
                 "NFI": "NFI", "SUS": "SUS", "DNR": "OUT", "COV": "OUT"}       # NA: Sleeper's meaning is unclear: ignored
STAMP_FRESH_S = 3600
SNAPSHOT_TTL_S = 120


def enabled() -> bool:
    if (os.environ.get(SWITCH_ENV) or "").lower() in ("off", "0", "false", "no"):
        return False
    return bool(os.environ.get(F.FIXTURES_ENV)) or not os.environ.get(A.FIXTURES_ENV)


# ------------------------------------------------------------------------------ statuses
def espn_code(e: Mapping) -> str | None:
    s, f = str(e.get("status") or "").strip().lower(), str(e.get("fantasy") or "").strip().upper()
    if f.startswith("PUP"):
        return "PUP"
    if f.startswith("NFI"):
        return "NFI"
    if f.startswith("SUSP") or s.startswith("susp"):
        return "SUS"
    if s == "injured reserve" or f.startswith("IR"):
        return "IR"
    return {"out": "OUT", "doubtful": "DOUBTFUL", "questionable": "QUESTIONABLE", "active": "ACTIVE",
            "day-to-day": "QUESTIONABLE"}.get(s)


def sleeper_code(p: Mapping) -> str | None:
    inj = str(p.get("injury_status") or "").strip().upper()
    if inj:
        return SLEEPER_CODES.get(inj)
    if str(p.get("status") or "") == "Inactive" and p.get("team"):
        return "INACTIVE"
    return "ACTIVE" if p.get("team") else None


def _ts(v) -> datetime | None:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=UTC)
    if isinstance(v, int | float):
        return datetime.fromtimestamp(float(v) / (1000.0 if v > 1e11 else 1.0), UTC)
    try:
        t = pd.Timestamp(v)
    except (ValueError, TypeError):
        return None
    if pd.isna(t):
        return None
    return (t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")).to_pydatetime()


def _iso(d: datetime | None) -> str | None:
    return None if d is None else d.astimezone(UTC).isoformat().replace("+00:00", "Z")


# ------------------------------------------------------------------------------ the id table (league_lab.player_ids)
# ---- I0-A + I0-B (PO merge): ESPN athlete id -> gsis from the nflverse id table. Tests: the small copy next to the
# ESPN fixtures (LEAGUE_LAB_ESPN_FIXTURES/db_playerids_espn.csv) or LEAGUE_LAB_PLAYER_IDS_CSV; the server: I0-B's
# player_ids.table(), which downloads db_playerids.csv into LEAGUE_LAB_CACHE_DIR at most once a day.
_ids: dict[str, tuple[float, dict[str, str]]] = {}


def _fixture_csv() -> Path | None:
    fx = os.environ.get(F.FIXTURES_ENV)
    if fx and not os.environ.get(IDS_CSV_ENV):
        p = Path(fx) / "db_playerids_espn.csv"
        if p.exists():
            return p
    return None


def espn_to_gsis() -> dict[str, str]:
    f = _fixture_csv()
    if f is None:
        return player_ids.table().espn_gsis
    key, mtime = str(f), f.stat().st_mtime
    hit = _ids.get(key)
    if hit is not None and hit[0] == mtime:
        return hit[1]
    out: dict[str, str] = {}
    try:
        with f.open(newline="") as fh:
            for r in csv.DictReader(fh):
                e, g = (r.get("espn_id") or "").strip(), (r.get("gsis_id") or "").strip()
                if e and g and e != "NA" and g != "NA":
                    out[e.split(".")[0]] = g
    except (OSError, csv.Error):
        return {}
    _ids[key] = (mtime, out)
    return out
# ---- end id table


# ------------------------------------------------------------------------------ the merged snapshot
class Snapshot:
    """Both sources mapped to gsis: ``espn`` / ``sleeper`` {gsis: entry}, ``sleeper_by_id`` {sleeper id: entry} (for a
    player the id maps do not know), the two copies' fetch times."""

    def __init__(self) -> None:
        self.espn: dict[str, dict] = {}
        self.sleeper: dict[str, dict] = {}
        self.sleeper_by_id: dict[str, dict] = {}
        self.espn_fetched: datetime | None = None
        self.sleeper_fetched: datetime | None = None
        self.unmapped_espn: list[dict] = []
        self.built = time.monotonic()


_snap: tuple[tuple, Snapshot] | None = None
_lock = threading.Lock()


def _sleeper_fetched(sl) -> datetime | None:
    hit = getattr(sl, "_cache", {}).get("/players/nfl")
    if not hit:
        return None
    return datetime.fromtimestamp(sl.wall() - (sl.clock() - hit[1]), UTC)


def _map_sleeper_ids(sids: list[str]) -> dict[str, str]:
    if not sids:
        return {}
    try:
        m = query("select sleeper_id, gsis_id from analytics.player_id_map where sleeper_id = any(%s)", (sorted(set(sids)),))
    except Exception:  # noqa: BLE001 - no database (a unit test): the directory's own gsis ids only
        return {}
    return {str(s): str(g) for s, g in zip(m["sleeper_id"], m["gsis_id"], strict=False) if isinstance(g, str) and g}


def snapshot(*, refresh: bool = True) -> Snapshot | None:
    """The merged copy, rebuilt when either source's copy changed (and at most every two minutes otherwise)."""
    global _snap
    if not enabled():
        return None
    fd = F.feed()
    if fd.is_game_day is F.default_game_day and fd.fixtures is None:
        fd.is_game_day = is_game_day             # the schedule decides the poll interval (15 min on a game day)
    esp = fd.snapshot(refresh=refresh)
    try:
        sl = A.sleeper()
        players = sl.players()
        s_fetched = _sleeper_fetched(sl)
    except (A.SleeperBusy, A.SleeperUnavailable):
        players, s_fetched = {}, None
    key = (None if esp is None else esp.get("fetched_at"), None if s_fetched is None else round(s_fetched.timestamp()), len(players))
    with _lock:
        if _snap is not None and _snap[0] == key and time.monotonic() - _snap[1].built < SNAPSHOT_TTL_S:
            return _snap[1]
    s = Snapshot()
    s.espn_fetched = None if esp is None else datetime.fromtimestamp(float(esp["fetched_at"]), UTC)
    s.sleeper_fetched = s_fetched
    by_espn: dict[str, str] = {}
    gsis_of: dict[str, str] = {}
    flagged_sids = []
    for sid, p in players.items():
        e = p.get("espn_id")
        if e not in (None, ""):
            by_espn[str(e).split(".")[0]] = str(sid)
        g = str(p.get("gsis_id") or "").strip()
        if g:
            gsis_of[str(sid)] = g
        if p.get("injury_status") or p.get("status") == "Inactive":
            flagged_sids.append(str(sid))
    need = [sid for sid in set(flagged_sids) | set(by_espn.values()) if sid not in gsis_of]
    gsis_of.update(_map_sleeper_ids(need))
    table = espn_to_gsis()
    for e in (esp or {}).get("entries") or []:
        code = espn_code(e)
        if code is None:
            continue
        sid = by_espn.get(str(e["espn_id"]))
        g = gsis_of.get(sid) if sid else None
        g = g or table.get(str(e["espn_id"]))
        if not g:
            s.unmapped_espn.append({"espn_id": e["espn_id"], "name": e.get("name"), "status": e.get("status")})
            continue
        s.espn[g] = {"code": code, "source": "ESPN", "as_of": _ts(e.get("date")), "fetched_at": s.espn_fetched,
                     "note": (e.get("injury") or "").lower() or None, "name": e.get("name"), "team": e.get("team"),
                     "return_date": e.get("return_date")}
        s.espn[g]["espn_id"] = str(e["espn_id"])            # ---- IG-2: the event's player key and ESPN page
    for sid in flagged_sids:
        p = players.get(sid) or {}
        code = sleeper_code(p)
        if code is None:
            continue
        ent = {"code": code, "source": "Sleeper", "as_of": _ts(p.get("news_updated")), "fetched_at": s_fetched,
               "note": (p.get("injury_body_part") or "").lower() or None, "name": p.get("full_name"), "team": p.get("team")}
        ent["sleeper_id"] = sid                                # ---- IG-2: the event's player key
        s.sleeper_by_id[sid] = ent
        if gsis_of.get(sid):
            s.sleeper[gsis_of[sid]] = ent
    s._players = players                         # noqa: SLF001 - a healthy player's Sleeper entry, made on request
    with _lock:
        _snap = (key, s)
    # ---- IG-2 (Wave I-G): the event store — the copy's own time (ESPN's feed timestamp) and the status moves since the
    # copy before, diffed on the events writer thread (events.observe_availability never waits, never raises)
    s.espn_timestamp = None if esp is None else esp.get("source_timestamp")
    from . import events
    events.observe_availability(s)
    # ---- end IG-2
    return s


def _pick(cands: list[dict]) -> dict | None:
    """The newest entry; a Sleeper entry without news_updated only when ESPN has nothing."""
    cands = [c for c in cands if c is not None]
    if not cands:
        return None
    floor = datetime(1970, 1, 1, tzinfo=UTC)
    return max(cands, key=lambda c: (c["as_of"] or floor, c["source"] == "ESPN"))


def _public(g: str, c: dict) -> dict:
    code = c["code"]
    return {"gsis_id": g, "status": LABEL.get(code), "code": code, "cannot_play": code in CANNOT_PLAY,
            "flagged": code in FLAGGED, "source": c["source"], "as_of": _iso(c["as_of"]), "fetched_at": _iso(c["fetched_at"]),
            "note": c.get("note"), "name": c.get("name")}


def now(gsis_ids: Iterable[str] | None = None, sleeper_of: Mapping[str, str] | None = None) -> dict[str, dict]:
    """{gsis: {status, code, cannot_play, flagged, source, as_of, fetched_at, note}} for the players asked (every player
    either source lists when ``gsis_ids`` is None). ``sleeper_of`` {gsis: sleeper id} lets a player the id maps do not
    know (or a healthy one) take Sleeper's entry. Empty when the overlay is off."""
    s = snapshot()
    if s is None:
        return {}
    ids = set(s.espn) | set(s.sleeper) if gsis_ids is None else {str(g) for g in gsis_ids if isinstance(g, str) and g}
    out = {}
    for g in ids:
        sl = s.sleeper.get(g)
        sid = (sleeper_of or {}).get(g)
        if sl is None and sid:
            sl = s.sleeper_by_id.get(str(sid))
            if sl is None:
                p = getattr(s, "_players", {}).get(str(sid))
                if p and p.get("news_updated") and sleeper_code(p) == "ACTIVE":
                    sl = {"code": "ACTIVE", "source": "Sleeper", "as_of": _ts(p.get("news_updated")),
                          "fetched_at": s.sleeper_fetched, "note": None, "name": p.get("full_name")}
        c = _pick([s.espn.get(g), sl])
        if c is not None:
            out[g] = _public(g, c)
    return out


def checked_at() -> datetime | None:
    """When ESPN's feed was last read (None: never, or the overlay is off)."""
    if not enabled():
        return None
    return F.feed().fetched_at()


def source_ages() -> dict:
    t = time.time()
    e = checked_at()
    s = _snap[1].sleeper_fetched if _snap is not None else None
    return {"espn_s": None if e is None else round(t - e.timestamp()), "sleeper_s": None if s is None else round(t - s.timestamp())}


def fresh() -> bool:
    e = checked_at()
    return e is not None and time.time() - e.timestamp() < STAMP_FRESH_S


def info() -> dict:
    """/api/status's block."""
    if not enabled():
        return {"enabled": False, "checked_at": None, "source_ages": {"espn_s": None, "sleeper_s": None}, "n_out": None}
    s = snapshot()
    allp = now() if s is not None else {}
    return {"enabled": True, "checked_at": _iso(checked_at()), "source_ages": source_ages(),
            "n_out": sum(1 for v in allp.values() if v["cannot_play"]),
            "n_questionable": sum(1 for v in allp.values() if v["flagged"]),
            "espn": F.feed().stats(), "unmapped_espn": 0 if s is None else len(s.unmapped_espn)}


# ------------------------------------------------------------------------------ game days (the poll interval)
_game_days: dict[date, bool] = {}


def is_game_day(d: date) -> bool:
    if d not in _game_days:
        try:
            r = query("""select exists (select 1 from analytics.dim_game
                         where (kickoff_at at time zone 'America/New_York')::date = %s) as g""", (d,))
            _game_days[d] = bool(r["g"].iloc[0])
        except Exception:  # noqa: BLE001 - no schedule: Thursday, Sunday, Monday
            return F.default_game_day(d)
    return _game_days[d]


# ------------------------------------------------------------------------------ the nightly build's time
_built: tuple[float, datetime | None] | None = None


def build_time() -> datetime | None:
    """When the nightly last solved the lineups (ops.lineup_totals.as_of): a source copy older than this is ignored."""
    global _built
    if _built is not None and time.monotonic() - _built[0] < 600:
        return _built[1]
    try:
        r = query("select max(as_of) as t from ops.lineup_totals where not is_realised", ())
        t = _ts(r["t"].iloc[0]) if not r.empty else None
    except Exception:  # noqa: BLE001
        t = None
    _built = (time.monotonic(), t)
    return t


# ------------------------------------------------------------------------------ My Week: the lineup frame
def _words(name: str, a: dict) -> str:
    w = WORDS.get(a["code"], "cannot play")
    return f"{name} {w}" + (f" ({a['note']})" if a.get("note") else "")


def _why(a: dict) -> str:
    """The row's reason: "Out (ankle) · ESPN, Oct 2 2:35 PM ET"."""
    when = ""
    if a.get("as_of"):
        t = pd.Timestamp(a["as_of"]).tz_convert("America/New_York")
        when = f", {t:%b} {t.day} {t:%-I:%M %p} ET"
    return f"{LABEL.get(a['code']) or a['code'].title()}" + (f" ({a['note']})" if a.get("note") else "") + f" · {a['source']}{when}"


def _build_as_of(rows: pd.DataFrame) -> datetime | None:
    if "as_of" in rows:
        ts = [t for t in (_ts(v) for v in rows["as_of"].dropna()) if t is not None]
        if ts:
            return max(ts)
    return None


def apply_to_rows(rows: pd.DataFrame, *, build_as_of: datetime | None = None, players: Mapping | None = None,
                  overlay: Mapping[str, dict] | None = None) -> tuple[pd.DataFrame, dict | None]:
    """The lineup frame (``cards.lineup_rows``' columns) with the overlay applied: statuses refreshed, and when a
    starter or bench player can no longer play (or a player the build sat as Out / Doubtful / NFL IR can play again)
    the lineup re-solved from the rows' own values with ``lineup.solve`` (the slots: the starter rows' slot types in
    order). Returns (rows, {checked_at, changes, flags, applied}) — the block is None when the overlay is off."""
    if not enabled() and overlay is None:
        return rows, None
    meta = {"checked_at": None, "changes": [], "flags": [], "applied": 0}
    if rows is None or rows.empty:
        meta["checked_at"] = _iso(checked_at())
        return rows, meta
    rows = rows.copy()
    for c in ("chip", "why"):
        rows[c] = None
    # ---- IP-5: a frame with no status at all reads report_status as float64 (all NaN); writing "Questionable" into it
    # was a TypeError (a 500 on an MFL league's week odds with the overlay on). The same values, as objects
    if "report_status" in rows and rows["report_status"].dtype.kind == "f":
        rows["report_status"] = rows["report_status"].astype(object)
    # ---- end IP-5
    gs = [g for g in rows["gsis_id"] if isinstance(g, str)]
    sleeper_of = {g: str(s) for g, s in zip(rows["gsis_id"], rows["sleeper_player_id"], strict=False)
                  if isinstance(g, str) and isinstance(s, str)}
    av = dict(overlay) if overlay is not None else now(gs, sleeper_of)
    meta["checked_at"] = _iso(checked_at())
    built = build_as_of or _build_as_of(rows)
    seen = rows["role"].isin(["starter", "bench", "unplayable"]) & ~rows["is_empty_slot"].astype(bool)
    moves: dict[int, dict] = {}                    # row index -> the overlay entry that changes his playability
    for i, r in rows[seen].iterrows():
        a = av.get(r["gsis_id"]) if isinstance(r["gsis_id"], str) else None
        if a is None:
            continue
        fetched = _ts(a.get("fetched_at"))
        if built is not None and fetched is not None and fetched < built:
            continue                               # the build ran after this copy was read: it knew
        locked = bool(r.get("locked_now"))
        code = a["code"]
        old_status = r.get("report_status") if isinstance(r.get("report_status"), str) else None
        new_status = LABEL.get(code)
        if code in CANNOT_PLAY and r["role"] in ("starter", "bench") and not locked:
            moves[i] = a
        elif code not in CANNOT_PLAY and r["role"] == "unplayable" and r.get("reason") in BUILD_STATUS_REASONS:
            moves[i] = a
        if new_status != old_status and not (old_status in (None, "Healthy") and new_status is None):
            rows.at[i, "report_status"] = new_status
            meta["applied"] += 1
            if code in FLAGGED and r["role"] != "unplayable":
                meta["flags"].append(f"{r['player_name']} is questionable" + (f" ({a['note']})" if a.get("note") else "")
                                     + " — he can play; check before kickoff")
        if code in CANNOT_PLAY:
            rows.at[i, "chip"] = CHIP[code]
            rows.at[i, "why"] = _why(a)
    if not moves:
        return rows, meta
    meta["applied"] += len(moves)
    new, changes = _resolve(rows, moves, players)
    meta["changes"] = changes
    # ---- IG-2 (Wave I-G): each change's citation, in the order of `changes` (one line per move): the player and the
    # overlay entry's source and time — My Week's "What changed" cites the stored event when there is one, else this
    meta["cites"] = [{"gsis_id": rows.at[i, "gsis_id"] if isinstance(rows.at[i, "gsis_id"], str) else None,
                      "code": a.get("code"), "source": a.get("source"), "as_of": a.get("as_of")} for i, a in moves.items()]
    # ---- end IG-2
    return new, meta


def _fantasy_positions(players: Mapping | None, sid) -> tuple[str, ...] | None:
    p = (players or {}).get(str(sid)) if sid is not None else None
    fp = (p or {}).get("fantasy_positions")
    return tuple(fp) if fp else None


def _resolve(rows: pd.DataFrame, moves: dict[int, dict], players: Mapping | None) -> tuple[pd.DataFrame, list[str]]:
    if players is None:
        try:
            players = A.sleeper().players()
        except (A.SleeperBusy, A.SleeperUnavailable):
            players = {}
    starters = rows[rows["role"] == "starter"].sort_values("slot_order")
    slots = [str(t) for t in starters["slot_type"]]
    keyed: dict[str, int] = {}
    plist = []
    for i, r in rows.iterrows():
        if r["role"] not in ("starter", "bench", "unplayable") or bool(r["is_empty_slot"]):
            continue
        pid = str(r["sleeper_player_id"]) if isinstance(r["sleeper_player_id"], str) else f"row{i}"
        keyed[pid] = i
        unvalued = r.get("value_source") == LU.UNVALUED or r["value"] is None or pd.isna(r["value"])
        val = None if unvalued else float(r["value"])
        base = dict(id=pid, position=r["position"], value=val, value_source=r.get("value_source"),
                    fantasy_positions=_fantasy_positions(players, r["sleeper_player_id"]),
                    status=r["report_status"] if isinstance(r["report_status"], str) else None)
        if i in moves:
            a = moves[i]
            if a["code"] in CANNOT_PLAY:
                plist.append(LU.Player(**base, playable=False, reason=LABEL.get(a["code"]) or a["code"]))
            else:
                plist.append(LU.Player(**base, playable=True))
        elif r["role"] == "unplayable":
            plist.append(LU.Player(**base, playable=False, reason=r.get("reason") or "cannot play"))
        elif bool(r.get("locked_now")):
            if r["role"] == "starter":
                plist.append(LU.Player(**base, locked_slot=r["slot_type"]))
            else:
                plist.append(LU.Player(**base, playable=False, reason="game started (bench)"))
        else:
            plist.append(LU.Player(**base))
    lu = LU.solve(plist, slots)
    bench_total = LU.solve(lu.bench, slots, margins=False).total
    w = lu.weakest
    n_unvalued = sum(1 for s in lu.starts if s.player is not None and s.player.value_source == LU.UNVALUED)
    tot = {"lineup_value": round(lu.total, 2), "bench_value": round(bench_total, 2),
           "weakest_slot": w.slot.label if w else None, "weakest_margin": None if w is None else round(w.margin, 2),
           "n_unvalued": n_unvalued}
    as_of = _build_as_of(rows)
    template = {c: None for c in rows.columns}
    out = []

    def take(p: LU.Player) -> dict:
        r = rows.loc[keyed[p.id]].to_dict()
        r.update({"slot": None, "slot_type": None, "slot_order": None, "bench_rank": None, "margin": None,
                  "is_empty_slot": False, "is_weakest_slot": False, "reason": None, "lineup_value": None, "bench_value": None,
                  "weakest_slot": None, "weakest_margin": None, "n_unvalued": None})
        return r

    for s in lu.starts:
        if s.player is None:
            r = dict(template)
            r.update({"role": "starter", "is_empty_slot": True, "is_locked": False, "locked_now": False, "kicked_off": False,
                      "value_source": None})
        else:
            r = take(s.player)
            r["role"] = "starter"
            r["margin"] = None if s.margin is None else round(s.margin, 2)
            r["is_locked"] = bool(s.locked) or bool(r.get("is_locked"))
        r.update({"slot": s.slot.label, "slot_type": s.slot.type, "slot_order": s.slot.order,
                  "is_weakest_slot": bool(w is not None and s.slot.label == w.slot.label), "as_of": as_of, **tot})
        out.append(r)
    for k, p in enumerate(lu.bench, 1):
        r = take(p)
        r.update({"role": "bench", "bench_rank": k})
        out.append(r)
    for p in lu.unplayable:
        r = take(p)
        r.update({"role": "unplayable", "reason": p.reason})
        out.append(r)
    new = pd.DataFrame(out, columns=rows.columns)
    for c in ("is_locked", "is_empty_slot", "kicked_off", "is_weakest_slot", "locked_now"):
        if c in new:
            new[c] = new[c].fillna(False).astype(bool)
    for c in ("value", "margin", "lineup_value", "bench_value", "weakest_margin"):
        if c in new:
            new[c] = pd.to_numeric(new[c], errors="coerce")
    return new, _changes(rows, new, moves)


def _changes(old: pd.DataFrame, new: pd.DataFrame, moves: dict[int, dict]) -> list[str]:
    """In words: "Justin Jefferson is out (ankle) — Jacory Croskey-Merritt starts at FLEX2". Each player who can no
    longer start is paired with a player who now starts: the one now in his slot, else one who could have played his
    slot (the narrowest slots first); none left = the slot stays empty, said so."""
    from .applib import cards

    def starting(df):
        s = df[(df["role"] == "starter") & ~df["is_empty_slot"].astype(bool)]
        return {str(r["sleeper_player_id"]): r for _, r in s.iterrows()}

    before, after = starting(old), starting(new)
    entered = [r for k, r in after.items() if k not in before]
    empty_now = [r for _, r in new[(new["role"] == "starter") & new["is_empty_slot"].astype(bool)].iterrows()]
    was_empty = set(old.loc[(old["role"] == "starter") & old["is_empty_slot"].astype(bool), "slot"])
    empty_now = [r for r in empty_now if r["slot"] not in was_empty]
    outs = [i for i, a in moves.items() if a["code"] in CANNOT_PLAY and old.loc[i, "role"] == "starter"]
    pair: dict[int, pd.Series | None] = {}
    used: set[str] = set()
    for i in outs:                                     # first pass: the player now in his slot
        e = next((x for x in entered if x["slot"] == old.loc[i, "slot"]), None)
        if e is not None:
            pair[i] = e
            used.add(str(e["sleeper_player_id"]))
    width = {i: len(LU.SLOT_ELIGIBILITY.get(str(old.loc[i, "slot_type"]), ())) for i in outs}
    for i in sorted((i for i in outs if i not in pair), key=lambda i: width[i]):
        ok = LU.SLOT_ELIGIBILITY.get(str(old.loc[i, "slot_type"]), frozenset())
        e = next((x for x in entered if str(x["sleeper_player_id"]) not in used and x["position"] in ok), None)
        pair[i] = e
        if e is not None:
            used.add(str(e["sleeper_player_id"]))
    for i in [i for i in outs if pair.get(i) is None]:     # a reshuffle: a teammate slid over, the new man elsewhere
        e = next((x for x in entered if str(x["sleeper_player_id"]) not in used), None)
        if e is not None and not any(x["slot_type"] == old.loc[i, "slot_type"] for x in empty_now):
            pair[i] = e
            used.add(str(e["sleeper_player_id"]))
    out = []
    for i, a in moves.items():
        r = old.loc[i]
        name = r["player_name"] or "A player"
        if a["code"] in CANNOT_PLAY:
            if r["role"] != "starter":
                out.append(f"{_words(name, a)} — he was on your bench; the lineup does not change")
                continue
            e = pair.get(i)
            if e is not None:
                out.append(f"{_words(name, a)} — {e['player_name']} starts at {cards.slot_label(e['slot'])}")
                continue
            k = next((n for n, x in enumerate(empty_now) if x["slot_type"] == r["slot_type"]), 0 if empty_now else None)
            if k is not None:
                hole = empty_now.pop(k)
                out.append(f"{_words(name, a)} — nobody on your bench can play {cards.slot_label(hole['slot'])}: it stays empty")
            else:
                out.append(f"{_words(name, a)} — the lineup reshuffles around him")
        else:
            k = str(r["sleeper_player_id"])
            if k in after:
                out.append(f"{name} can play again ({LABEL.get(a['code']) or 'active'}, {a['source']}) — he starts at "
                           f"{cards.slot_label(after[k]['slot'])}")
            else:
                out.append(f"{name} can play again ({LABEL.get(a['code']) or 'active'}, {a['source']}) — he goes to your bench")
    return out


# ------------------------------------------------------------------------------ the other screens
def cannot_play(gsis_ids: Iterable[str], codes: frozenset[str] = CANNOT_PLAY) -> dict[str, dict]:
    """{gsis: entry} of the players asked who cannot play now (``codes``: which statuses count)."""
    return {g: a for g, a in now(gsis_ids).items() if a["code"] in codes}


def injury_status(gsis_ids: Iterable[str]) -> dict[str, str | None]:
    return {g: a["status"] for g, a in now(gsis_ids).items()}


def stamp() -> dict:
    """The block a response carries: when ESPN was last read."""
    return {"checked_at": _iso(checked_at())}


def depth_order(sleeper_id) -> float:
    """Sleeper's depth_chart_order for a player (lower = higher on the chart); inf when unknown."""
    try:
        p = A.sleeper().players().get(str(sleeper_id)) or {}
    except (A.SleeperBusy, A.SleeperUnavailable):
        return math.inf
    v = p.get("depth_chart_order")
    try:
        return float(v) if v is not None else math.inf
    except (TypeError, ValueError):
        return math.inf


# ------------------------------------------------------------------------------ /api/waivers
def _gsis_of(p: Mapping | None) -> str | None:
    g = (p or {}).get("gsis_id")
    return g if isinstance(g, str) and g else None


def one_qb_per_team(items: list[dict], add_of=lambda m: m.get("add")) -> tuple[list[dict], list[dict]]:
    """Never two QBs of the same NFL team among the recommendations (Brissett and his backup Carson Beck were both
    suggested): per team the QB highest on Sleeper's depth chart (``depth_chart_order``) stays, else the better-ranked
    one (the list's order). Returns (kept, left out)."""
    best: dict[str, tuple[float, int]] = {}
    for k, m in enumerate(items):
        a = add_of(m) or {}
        if a.get("position") == "QB" and a.get("team"):
            key = (depth_order(a.get("sleeper_id")), k)
            if a["team"] not in best or key < best[a["team"]]:
                best[a["team"]] = key
    kept, gone = [], []
    for k, m in enumerate(items):
        a = add_of(m) or {}
        if a.get("position") == "QB" and a.get("team") and best[a["team"]][1] != k:
            gone.append(m)
        else:
            kept.append(m)
    return kept, gone


def waivers_overlay(out: dict) -> dict:
    """/api/waivers with the overlay: no claim (and no card) of a player who cannot play this week; a drop who cannot
    play this week costs nothing this week (``this_week`` 0, ``cannot_play`` his status); the free agents who cannot
    play this week left out, the others' ``injury_status`` refreshed; one QB per NFL team among the claims."""
    moves, cards_, fas = out.get("moves") or [], out.get("cards") or [], out.get("free_agents") or []
    ids = {_gsis_of(m.get("add")) for m in moves} | {_gsis_of(m.get("drop")) for m in moves} | {_gsis_of(f) for f in fas}
    ids |= {_gsis_of((c.get("move") or {}).get("add")) for c in cards_} | {_gsis_of((c.get("move") or {}).get("drop")) for c in cards_}
    av = now({g for g in ids if g})

    def blocked(p) -> dict | None:
        a = av.get(_gsis_of(p))
        return a if a is not None and a["cannot_play"] else None

    left = [m for m in moves if blocked(m.get("add"))]
    moves = [m for m in moves if not blocked(m.get("add"))]
    cards_ = [c for c in cards_ if not blocked((c.get("move") or {}).get("add"))]
    for m in [*moves, *[c.get("move") or {} for c in cards_]]:
        d = m.get("drop")
        a = blocked(d)
        if d is not None and a is not None:
            d["cannot_play"], d["this_week"] = a["status"], 0.0
    moves, same_team = one_qb_per_team(moves)
    gone = {id(c) for c in one_qb_per_team(cards_, lambda c: (c.get("move") or {}).get("add"))[1]}
    cards_ = [c for c in cards_ if id(c) not in gone]
    fa_out = [f for f in fas if blocked(f)]
    fas = [f for f in fas if not blocked(f)]
    for f in fas:
        a = av.get(_gsis_of(f))
        if a is not None:
            f["injury_status"] = a["status"]
    out["moves"], out["cards"], out["free_agents"] = moves, cards_, fas
    if out.get("total_moves") is not None:
        out["total_moves"] = max(0, int(out["total_moves"]) - len(left) - len(same_team))
    out["availability"] = {**stamp(), "claims_left_out": [{"player_name": (m.get("add") or {}).get("player_name"),
                                                           "status": blocked(m.get("add"))["status"]} for m in left],
                           "same_team_qbs_left_out": [(m.get("add") or {}).get("player_name") for m in same_team],
                           "free_agents_left_out": len(fa_out)}
    return out


# ------------------------------------------------------------------------------ /api/trades/*
def horizon_overlay(horizon: pd.DataFrame, this_week: int) -> tuple[pd.DataFrame, dict[str, str]]:
    """The trade board's rows with this week's availability: a player who cannot play this week is unplayable that
    week (worth 0 to any lineup: the board re-solves from the rows), a player the build sat as Out / Doubtful / NFL IR
    who can play again is back on the bench. Returns (rows, {sleeper id: status} of who cannot play this week)."""
    if horizon is None or horizon.empty or not enabled():
        return horizon, {}
    h = horizon.copy()
    wk = h["week"] == int(this_week)
    gs = [g for g in h.loc[wk, "gsis_id"] if isinstance(g, str)]
    av = now(gs)
    out: dict[str, str] = {}
    for i in h.index[wk]:
        a = av.get(h.at[i, "gsis_id"]) if isinstance(h.at[i, "gsis_id"], str) else None
        if a is None or bool(h.at[i, "is_locked"]):
            continue
        if a["cannot_play"]:
            out[str(h.at[i, "sleeper_player_id"])] = a["status"]
            if h.at[i, "role"] in ("starter", "bench"):
                h.at[i, "role"], h.at[i, "reason"] = "unplayable", a["status"]
        elif h.at[i, "role"] == "unplayable" and h.at[i, "reason"] in BUILD_STATUS_REASONS:
            h.at[i, "role"], h.at[i, "reason"] = "bench", None
    return h, out


# ------------------------------------------------------------------------------ /api/ros
def ros_overlay(players: list[dict]) -> list[dict]:
    """Each rest-of-season row's ``injury_status`` from the overlay (None: nothing reported)."""
    if not enabled():
        return players
    av = now([p.get("gsis_id") for p in players if p.get("gsis_id")])
    for p in players:
        a = av.get(p.get("gsis_id")) if p.get("gsis_id") else None
        p["injury_status"] = None if a is None else a["status"]
    return players


# ------------------------------------------------------------------------------ IB-0: one availability truth
# ---- IB-0 (Wave I-B): the roster context. The second review (2026-10-03) caught My Week saying "start Croskey-Merritt
# (Jefferson is out)" while Waivers said "drop him: he would not start" and the totals read 115.75 vs 117.3: I0-A's
# overlay re-solved the lineup on My Week only. ``roster_context`` is the one place a roster's week is read: the
# nightly's rows (``cards.lineup_rows``; any other league: ``anyleague.lineup_rows``) + ``now()``, re-solved by
# ``apply_to_rows`` when a status changed since the build. My Week, the opponent's total, Waivers, Team, the player
# card and the trade finder's board all read it, so the lineup total is one number on every screen.
CONTEXT_TTL_S = {"house": 600, "sleeper": 120}     # the query cache's 10 minutes; Sleeper's rosters move faster
STATUS_OF_REASON = {"Out": "OUT", "Doubtful": "DOUBTFUL", "NFL injured reserve": "IR", "IR slot": "IR"}
# INF-2 (Wave I-J): the memory budget's ``contexts`` region (was a dict cleared past 512 entries); the TTL per entry
_ctx_cache = memo.region("contexts", ttl=CONTEXT_TTL_S["house"])
CONTEXT_HOLD_S = 3600.0          # ---- IP-5: a roster's last good context, for a rebuild a provider refused (the LRU evicts)


def clear_context() -> None:
    _ctx_cache.clear()


def _f(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def _s(v) -> str | None:
    return v if isinstance(v, str) and v else None


class RosterContext:
    """One roster's week as every screen must see it. ``base`` = the build's rows (``cards.lineup_rows``' columns),
    ``rows`` = the same with the overlay (statuses, chips, the re-solved lineup), ``meta`` = ``apply_to_rows``' block
    (None when the overlay is off), ``od`` = the on-demand result (any league). Read-only: copy before changing."""

    def __init__(self, league_id: str, roster_id: int, week: int, season: int, house: bool, base: pd.DataFrame,
                 rows: pd.DataFrame, meta: dict | None, od=None) -> None:
        self.league_id, self.roster_id, self.week, self.season, self.house = str(league_id), int(roster_id), int(week), season, house
        self.base, self.rows, self.meta, self.od = base, rows, meta, od
        self.changes: list[str] = list((meta or {}).get("changes") or [])
        self.changed = bool(self.changes)              # one sentence per player whose playability moved: re-solved
        self.checked_at = (meta or {}).get("checked_at")
        self.as_of_build = _iso(_build_as_of(base)) if base is not None and not base.empty else None

    def _head(self, col: str):
        if self.rows is None or self.rows.empty or col not in self.rows:
            return None
        v = self.rows.loc[self.rows["role"] == "starter", col].dropna()
        return None if v.empty else v.iloc[0]

    @property
    def lineup_value(self) -> float | None:
        return _f(self._head("lineup_value"))

    @property
    def bench_value(self) -> float | None:
        return _f(self._head("bench_value"))

    @property
    def weakest_slot(self) -> str | None:
        return _s(self._head("weakest_slot"))

    @property
    def weakest_margin(self) -> float | None:
        return _f(self._head("weakest_margin"))

    def starters(self, frame: pd.DataFrame | None = None) -> dict[str, str]:
        """{Sleeper id: slot} of the starters (the context's; ``frame`` = another frame, e.g. ``base``)."""
        df = self.rows if frame is None else frame
        if df is None or df.empty:
            return {}
        s = df[(df["role"] == "starter") & ~df["is_empty_slot"].astype(bool)]
        return {str(r["sleeper_player_id"]): r["slot"] for _, r in s.iterrows() if isinstance(r["sleeper_player_id"], str)}

    def row_of(self, key: str | None) -> pd.Series | None:
        """His row (by gsis id or Sleeper id)."""
        if not key or self.rows is None or self.rows.empty:
            return None
        if getattr(self, "_index", None) is None:
            idx: dict[str, pd.Series] = {}
            for _, r in self.rows.iterrows():
                for k in (r["gsis_id"], r["sleeper_player_id"]):
                    if isinstance(k, str) and k and k not in idx:
                        idx[k] = r
            self._index = idx
        return self._index.get(str(key))

    def replacement(self, r: pd.Series) -> pd.Series | None:
        """The bench player who comes in if starter ``r`` sits (``horizon_frame``'s rule: worth value - margin to the
        cent, the better bench rank first)."""
        v, m = _f(r.get("value")), _f(r.get("margin"))
        if v is None or m is None or round((v - m) * 100) <= 0:
            return None
        b = self.rows[(self.rows["role"] == "bench")].copy()
        if b.empty:
            return None
        b = b[(pd.to_numeric(b["value"], errors="coerce") * 100).round() == round((v - m) * 100)]
        return None if b.empty else b.sort_values("bench_rank").iloc[0]

    def status_of(self, r: pd.Series) -> str:
        """OUT / DOUBTFUL / IR / Q / ok (the brief's words)."""
        if _s(r.get("chip")):
            return str(r["chip"])
        rep = _s(r.get("report_status"))
        if r["role"] == "unplayable":
            return STATUS_OF_REASON.get(_s(r.get("reason")) or "", STATUS_OF_REASON.get(rep or "", "OUT" if rep else "ok"))
        return "Q" if rep == "Questionable" else ("DOUBTFUL" if rep == "Doubtful" else "ok")

    def players(self) -> list[dict]:
        if self.rows is None or self.rows.empty:
            return []
        out = []
        for _, r in self.rows[~self.rows["is_empty_slot"].astype(bool)].iterrows():
            out.append({"sleeper_id": _s(r.get("sleeper_player_id")), "gsis_id": _s(r.get("gsis_id")),
                        "player_name": _s(r.get("player_name")), "position": _s(r.get("position")),
                        "status": self.status_of(r), "can_play": r["role"] in ("starter", "bench"),
                        "starter": r["role"] == "starter", "slot": _s(r.get("slot")), "value": _f(r.get("value")),
                        "locked": bool(r.get("locked_now")), "reason": _s(r.get("why")) or _s(r.get("reason"))})
        return out

    def summary(self) -> dict:
        """What a response carries: the total, who moved and why, the stamps."""
        return {"league_id": self.league_id, "roster_id": self.roster_id, "week": self.week,
                "lineup_value": self.lineup_value, "changed": self.changed, "changes": self.changes,
                "checked_at": self.checked_at, "as_of_build": self.as_of_build}

    def to_dict(self) -> dict:
        return {**self.summary(), "bench_value": self.bench_value, "weakest_slot": self.weakest_slot,
                "weakest_margin": self.weakest_margin, "players": self.players()}


def roster_context(league_id: str, roster_id: int, week: int | None = None, *, house: bool | None = None,
                   as_of: datetime | None = None, exclude_reference: str | None = None, client=None) -> RosterContext | None:
    """The overlay-adjusted roster of one team for the week (None after the regular season). ``house`` = a league the
    database keeps (default: ``myweek.known_league``; False = the on-demand path, as ``source=sleeper`` asks). Kept in
    process for the overlay's own interval, at most the query cache's 10 minutes (2 on demand), keyed by the league,
    the roster, the week, the overlay's stamp and the build; ``as_of`` / ``exclude_reference`` (tests) are never kept."""
    from .applib import cards
    from .myweek import known_league
    league_id = str(league_id)
    is_house = known_league(league_id) if house is None else bool(house)
    if is_house:
        season = cards.league_season(league_id)
    else:
        sl = client or A.sleeper()
        league_id = A.check_id(league_id)
        season = int(sl.league(league_id)["season"])
    if season is None:
        return None
    week = cards.decision_week(int(season)) if week is None else int(week)
    if week is None:
        return None
    on = enabled()
    if on:
        snapshot()                                  # the feed read first, so the stamp in the key is the one applied
    # ---- IP-5 (Wave I-P): the stamps are the entry's stamp, not its key — a build during which a provider read was
    # refused or failed (provider_trouble: the directory, a roster, an MFL id lookup) is never kept; the last good
    # context for this roster is served with its own stamps, else 503 busy (never an empty or wrong lineup kept for
    # the next manager). SECURITY_PUBLIC § 15.
    key = (league_id, int(roster_id), int(week), is_house, on)
    stamp = (_iso(checked_at()), _iso(build_time()))
    keep = as_of is None and exclude_reference is None
    ttl = min(CONTEXT_TTL_S["house" if is_house else "sleeper"], F.feed().interval_s() if on else 10 ** 9)

    def build() -> RosterContext:
        od = None
        if is_house:
            base = cards.lineup_rows(league_id, int(season), int(week), int(roster_id))
            rows, meta = apply_to_rows(base)
        else:
            od = A.lineup_rows(query, league_id, int(roster_id), int(week), as_of=as_of, client=client,
                               exclude_reference=exclude_reference)
            base = od.rows
            rows, meta = apply_to_rows(base, build_as_of=build_time())
        return RosterContext(league_id, int(roster_id), int(week), int(season), is_house, base, rows, meta, od)
    if not keep:
        return build()
    return provider_trouble.kept(_ctx_cache, key, build, ttl=ttl, stamp=stamp, hold_s=CONTEXT_HOLD_S)
    # ---- end IP-5


def contexts(league_id: str, roster_ids: Iterable[int], week: int | None = None, *, house: bool | None = None,
             workers: int = 4) -> dict[int, RosterContext | None]:
    """{roster id: context} for several rosters, read side by side (the house path's rows are one query each)."""
    import contextvars  # ---- IO-4 fix round (review L3)
    from concurrent.futures import ThreadPoolExecutor
    rids = sorted({int(r) for r in roster_ids})
    if len(rids) <= 1:
        return {r: roster_context(league_id, r, week, house=house) for r in rids}
    ctx = contextvars.copy_context()        # ---- IO-4 fix round: the request's client (provider_share) reaches each thread
    with ThreadPoolExecutor(max_workers=min(workers, len(rids))) as ex:
        got = list(ex.map(lambda r: ctx.copy().run(roster_context, league_id, r, week, house=house), rids))
    return dict(zip(rids, got, strict=True))


def touched(gsis_by_roster: Mapping[int, Iterable[str]]) -> set[int]:
    """The rosters the overlay can move this week: one of their starters or bench players (the caller passes those)
    cannot play now, by a copy newer than the build. The other rosters keep the build's lineup, so their context need
    not be built (the league views' cost)."""
    if not enabled():
        return set()
    ids = {g for gs in gsis_by_roster.values() for g in gs if isinstance(g, str) and g}
    av = now(ids)
    built = build_time()
    hit = {g for g, a in av.items() if a["cannot_play"] and (built is None or (_ts(a.get("fetched_at")) or built) >= built)}
    return {int(r) for r, gs in gsis_by_roster.items() if hit & {g for g in gs if isinstance(g, str)}}


# ------------------------------------------------------------------------------ IB-0: Waivers on the context
def _solver(rows: pd.DataFrame, players: Mapping | None, drop: str | None = None) -> list[LU.Player]:
    """The solver's view of a lineup frame (``_resolve``'s rules): who can play, who is locked where."""
    out = []
    for i, r in rows.iterrows():
        if r["role"] not in ("starter", "bench", "unplayable") or bool(r["is_empty_slot"]):
            continue
        pid = str(r["sleeper_player_id"]) if isinstance(r["sleeper_player_id"], str) else f"row{i}"
        if pid == drop:
            continue
        unvalued = r.get("value_source") == LU.UNVALUED or r["value"] is None or pd.isna(r["value"])
        base = dict(id=pid, position=r["position"], value=None if unvalued else float(r["value"]),
                    value_source=r.get("value_source"), fantasy_positions=_fantasy_positions(players, r["sleeper_player_id"]),
                    status=r["report_status"] if isinstance(r["report_status"], str) else None)
        if r["role"] == "unplayable":
            out.append(LU.Player(**base, playable=False, reason=r.get("reason") or "cannot play"))
        elif bool(r.get("locked_now")):
            if r["role"] == "starter":
                out.append(LU.Player(**base, locked_slot=r["slot_type"]))
            else:
                out.append(LU.Player(**base, playable=False, reason="game started (bench)"))
        else:
            out.append(LU.Player(**base))
    return out


def _slots(rows: pd.DataFrame) -> list[str]:
    return [str(t) for t in rows[rows["role"] == "starter"].sort_values("slot_order")["slot_type"]]


def moves_on_context(mv: pd.DataFrame, ctx: RosterContext | None, players: Mapping | None = None) -> pd.DataFrame:
    """``mart_waiver_moves``' rows (or the on-demand sweep's) with THIS week's part re-solved on the roster's context
    when the overlay moved the lineup: each move's week gain, lineup before / after, seat, displaced starter and the
    drop's cost this week come from ``lineup.solve`` on the context's players (the later weeks keep the build's);
    the horizon gain and the drop's cost follow; moves that no longer gain are left out; the ranks are re-run with
    ``waivers.rank_moves``' order. Unchanged when the overlay did not move this roster."""
    if mv is None or mv.empty or ctx is None or not ctx.changed or "list_kind" not in mv:
        return mv
    from league_lab import waivers as W
    if players is None:
        try:
            players = A.sleeper().players()
        except (A.SleeperBusy, A.SleeperUnavailable):
            players = {}
    slots = _slots(ctx.rows)
    if not slots:
        return mv
    now_p, base_p = _solver(ctx.rows, players), _solver(ctx.base, players)
    before = LU.solve(now_p, slots, margins=False)
    base_total = LU.solve(base_p, slots, margins=False).total
    drop_now: dict[str, float] = {}
    drop_base: dict[str, float] = {}
    starters_now = set(before.starter_ids)
    info = {str(r["sleeper_player_id"]): r for _, r in ctx.rows.iterrows() if isinstance(r["sleeper_player_id"], str)}

    def loss(d: str, ps: list[LU.Player], total: float, memo: dict) -> float:
        if d not in memo:
            memo[d] = total - LU.solve([p for p in ps if p.id != d], slots, margins=False).total
        return memo[d]

    out = []
    for r in mv.to_dict("records"):
        if r["list_kind"] == "nothing" or not isinstance(r.get("add_sleeper_id"), str):
            r["lineup_before"] = r["lineup_after"] = round(before.total, 2)
            out.append(r)
            continue
        d = r["drop_sleeper_id"] if isinstance(r.get("drop_sleeper_id"), str) else None
        av = _f(r.get("add_value"))
        add = LU.Player(id=str(r["add_sleeper_id"]), position=r["add_position"], value=av,
                        value_source=r.get("add_value_source") or "proj_points",
                        playable=not isinstance(r.get("add_reason"), str), reason=_s(r.get("add_reason")),
                        fantasy_positions=_fantasy_positions(players, r["add_sleeper_id"]))
        after = LU.solve([p for p in now_p if p.id != d] + [add], slots, margins=False)
        gains = [(_f(g) or 0.0) for g in (r["week_gains"] if isinstance(r.get("week_gains"), list | tuple | np.ndarray) else [])]
        old0 = gains[0] if gains else (_f(r.get("weekly_gain")) or 0.0)
        new0 = after.total - before.total
        gains = [new0, *gains[1:]] if gains else [new0]
        r["week_gains"] = [round(g, 2) for g in gains]
        r["weekly_gain"] = round(new0, 2)
        r["horizon_gain"] = round((_f(r.get("horizon_gain")) or 0.0) - old0 + new0, 2)
        r["lineup_before"], r["lineup_after"] = round(before.total, 2), round(after.total, 2)
        slot, stype, disp = W._seat(before, after, add.id, d)
        r["add_slot"], r["fills_empty_slot"] = slot, slot is not None and disp is None
        if "add_slot_type" in mv:
            r["add_slot_type"] = stype
        dr = info.get(disp) if disp else None
        r["displaced_sleeper_id"] = disp
        r["displaced_gsis_id"] = None if dr is None else _s(dr["gsis_id"])
        r["displaced_name"] = None if dr is None else _s(dr["player_name"])
        r["displaced_position"] = None if dr is None else _s(dr["position"])
        r["displaced_value"] = None if dr is None else _f(dr["value"])
        r["displaced_slot"] = None if dr is None else _s(dr["slot"])
        if d is not None:
            new_loss, old_loss = loss(d, now_p, before.total, drop_now), loss(d, base_p, base_total, drop_base)
            r["drop_horizon_loss"] = round(max(0.0, (_f(r.get("drop_horizon_loss")) or 0.0) - old_loss + new_loss), 2)
            r["drop_is_starter"] = d in starters_now
        r["list_kind"] = "start_now" if round(new0, 2) > 0 else "cover"
        if round(r["horizon_gain"], 2) > 0 or round(new0, 2) > 0:
            out.append(r)
    if not any(x["list_kind"] != "nothing" for x in out):
        head = mv.iloc[0].to_dict()
        for c in ("move_rank", "add_rank", "is_best_drop", "add_sleeper_id", "add_gsis_id", "add_name", "drop_sleeper_id",
                  "drop_gsis_id", "drop_name", "week_gains"):
            if c in head:
                head[c] = None
        head["list_kind"], head["weekly_gain"], head["horizon_gain"] = "nothing", 0.0, 0.0
        head["lineup_before"] = head["lineup_after"] = round(before.total, 2)
        return pd.DataFrame([head], columns=mv.columns).assign(lineup_value=round(before.total, 2))
    df = pd.DataFrame(out, columns=mv.columns)
    df = df.assign(_n=df["drop_sleeper_id"].map(lambda x: isinstance(x, str)),
                   _p=pd.to_numeric(df.get("drop_ros_points"), errors="coerce").fillna(0.0).round(2),
                   _h=-pd.to_numeric(df["horizon_gain"], errors="coerce").round(2),
                   _w=-pd.to_numeric(df["weekly_gain"], errors="coerce").round(2),
                   _d=df["drop_sleeper_id"].fillna(""))
    df = df.sort_values(["_h", "_w", "_n", "_p", "add_sleeper_id", "_d"]).drop(columns=["_n", "_p", "_h", "_w", "_d"])
    df = df.reset_index(drop=True)
    df["move_rank"] = range(1, len(df) + 1)
    first = ~df["add_sleeper_id"].duplicated()
    df["is_best_drop"] = first
    df["add_rank"] = None
    df.loc[first, "add_rank"] = range(1, int(first.sum()) + 1)
    if "lineup_value" in df:
        df["lineup_value"] = round(before.total, 2)
    return df


def drop_words(move: dict, ctx: RosterContext | None) -> dict:
    """A drop who starts this week by the context is never "would not start": ``starts_this_week`` / ``slot_this_week``
    on the drop, and the page's sentence replaced when it says so (the page's rule is a loss over 0.05, so a starter
    with an equal player behind him read "would not start")."""
    d = move.get("drop")
    if not d or ctx is None:
        return move
    r = ctx.row_of(d.get("gsis_id") or d.get("sleeper_id"))
    starts = r is not None and r["role"] == "starter" and not bool(r["is_empty_slot"])
    d["starts_this_week"] = bool(starts)
    d["slot_this_week"] = _s(r["slot"]) if starts else None
    if starts:
        from .applib import cards
        name, slot = d.get("player_name") or "He", cards.slot_label(r["slot"])
        loss = _f(d.get("horizon_loss")) or 0.0
        words = move.get("words") or {}

        def fix(x: str) -> str:
            if "would not start" not in x:
                return x
            span = x.split(" would not start for you in ", 1)[1].rstrip(".") if " would not start for you in " in x else None
            return (f"{name} starts at {slot} for you this week, but the player behind him is as good: dropping him costs "
                    f"your lineup {loss:.1f}" + (f" over {span}" if span else "") + " (already counted).")
        words["lines"] = [fix(x) for x in words.get("lines") or []]
    return move
# ---- end IB-0
