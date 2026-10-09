"""IS-2 (Wave I-S): the league readers ask the one question — ``availability_gate.sits(block)`` — and say why.

Before this, a dozen readers inside a league (waivers, the trade fill, the card, the scenario expiry ...) decided "can
he play" from ``analytics.mart_player_availability.injury_status`` — nflverse's newest weekly report row, which midweek
is last Sunday's game status and never lists a reserve list — or from a set of codes of their own. This module is how
``src/`` code reaches the one definition without importing the API (the dependency runs API -> ``src``):

* ``blocks(query, season, week)``: {gsis: ``availability_gate.classify`` block} from what the database holds of the
  site's sources (Sleeper's directory copy and the nightly's stored record; ``availability_gate.statuses_from_query``).
  The API passes its own request-time blocks (``availability.statuses``: the record + Sleeper + ESPN) instead.
* ``directory_block(sleeper_entry)``: the block of one entry of Sleeper's directory a caller already holds (the
  on-demand leagues hold the whole directory) — the same ``classify``, never a code tested here.
* ``note(block)``: the compact piece a screen reads beside a zero: the label, ``why`` ("IR (knee - acl) · Sleeper,
  Sep 28"), whether he sits this week, whether he is out indefinitely, and the sentence.

No status code and no status string is tested in this module: ``sits`` / ``out_indefinitely`` are the gate's.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping

import pandas as pd

from . import availability_gate as AG

Query = Callable[..., pd.DataFrame]


def conn_query(conn) -> Query:
    """A ``query(sql, params)`` -> DataFrame over a psycopg connection; a failed statement rolls back to a savepoint only
    (the nightly's open transaction keeps its writes)."""
    def q(sql: str, params: tuple = ()) -> pd.DataFrame:
        with conn.transaction(), conn.cursor() as cur:
            cur.execute(sql, params)
            return pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])
    return q


def blocks(query: Query, season: int | None, week: int | None) -> dict[str, dict]:
    """{gsis: block} of every player with a word for the week (``availability_gate.statuses_from_query``); {} when the
    week is unknown or nothing can be read (never a guess that everyone is out)."""
    if season is None or week is None:
        return {}
    try:
        out, _meta = AG.statuses_from_query(query, int(season), int(week))
    except Exception:  # noqa: BLE001 - no directory, no record: nobody is left out by this reader
        return {}
    return out


def directory_block(p: Mapping | None) -> dict | None:
    """The gate's block for one Sleeper directory entry (``injury_status``, ``status``, ``team``, ``news_updated``,
    ``injury_body_part``); None when the entry says nothing usable or he is active."""
    if not isinstance(p, Mapping):
        return None
    code = AG.sleeper_code(p)
    if code is None or code == "ACTIVE":
        return None
    return AG.classify(AG.entry(code, "Sleeper", as_of=p.get("news_updated"), note=p.get("injury_body_part"),
                                name=p.get("full_name")))


def record_block(text) -> dict | None:
    """The block of one stored record (``ops.projections.availability`` / ``ops.projection_lines.availability``: the
    JSON ``project`` writes for a player the gate left out of the live week); None for no record or an unreadable one."""
    if not isinstance(text, str) or not text:
        return None
    try:
        j = json.loads(text)
    except ValueError:
        return None
    if not isinstance(j, dict) or j.get("code") not in AG.CODES:
        return None
    return AG.classify(AG.entry(j["code"], str(j.get("source") or "Sleeper"), as_of=j.get("as_of"),
                                fetched_at=j.get("fetched_at"), note=j.get("note")))


def sits(block: Mapping | None) -> bool:
    """``availability_gate.sits``; anything that is not a block (None, a frame's NaN) is no word: he is not left out."""
    return AG.sits(dict(block)) if isinstance(block, Mapping) and block else False


def out_indefinitely(block: Mapping | None) -> bool:
    return isinstance(block, Mapping) and bool(block.get("out_indefinitely"))


def sitting(bl: Mapping[str, dict], ids: Iterable[str] | None = None) -> dict[str, dict]:
    """The blocks of the players (``ids``, or all) who are left out this week."""
    keys = bl.keys() if ids is None else [g for g in ids if isinstance(g, str) and g in bl]
    return {g: bl[g] for g in keys if sits(bl[g])}


def note(block: Mapping | None, position: str | None = None) -> dict | None:
    """What a league screen shows beside a player's number: ``status`` (the label), ``why`` (the label, the detail, the
    source and its date), ``sits`` (left out this week: his week is 0), ``out_indefinitely``, ``words`` (the reason in
    a sentence, None for a flag only), ``rate_words`` (IU-3: a flag's measured rate by ``position``, "Questionable:
    about 2 in 3 play" — the Rankings row's words; None otherwise). None when there is no word."""
    if not isinstance(block, Mapping) or not block.get("why"):
        return None
    out_ind = out_indefinitely(block)
    try:
        rate = AG.short_words(dict(block), position)                                    # ---- IU-3
    except Exception:  # noqa: BLE001 - no rate: the flag alone
        rate = None
    return {"status": block.get("status"), "why": block.get("why"), "sits": sits(block), "out_indefinitely": out_ind,
            "words": (block.get("ros_words") if out_ind else None) or block.get("week_words"), "rate_words": rate}


__all__ = ["blocks", "conn_query", "directory_block", "note", "out_indefinitely", "record_block", "sits", "sitting"]
