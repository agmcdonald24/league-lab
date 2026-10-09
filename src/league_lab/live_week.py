"""IV-1 (Wave I-V), fr1.1: the one place that answers "this player's number for the week under way".

``project`` with ``LEAGUE_LAB_FREEZE=game`` writes an overlay next to every stored projection table a live reader reads
(``OVERLAYS``): the started week's rows of the games that had not kicked off when it ran, the shape of the table it
overlays plus ``game_kickoff``. The stored tables are the record and are never rewritten (B5; docs/METRICS.md § "The
live week after its first kickoff"). A live reader's SQL goes through ``sql``: every ``from`` / ``join`` of a stored
table whose overlay is active becomes the stored rows without an overlay row, plus the overlay rows cast to the stored
table's own columns (``jsonb_populate_record``: by name, whatever columns either table has). An overlay that does not
exist (a database before the nightly that creates it) or is empty leaves the SQL unchanged, character for character:
today's behaviour. The graders (the decision record, drift, the projection record, the context record, the freeze
tests) never call this: they read the kickoff board.

The API calls ``sql`` in the one place every statement passes (``league_lab_api.db._run``); ``project``'s lineup and
waiver solves call it on their own reads (``lineup.load_inputs``)."""
from __future__ import annotations

import re
from collections.abc import Iterable

# stored table -> (its overlay, the key one overlay row replaces the stored rows of)
OVERLAYS: dict[str, tuple[str, tuple[str, ...]]] = {
    "ops.projections": ("ops.projection_live", ("league_id", "season", "week", "position", "gsis_id")),
    "ops.projection_lines": ("ops.projection_lines_live", ("season", "week", "gsis_id")),
    "ops.projection_ranges": ("ops.projection_ranges_live", ("scoring_name", "season", "week", "gsis_id")),
    "ops.kd_lines": ("ops.kd_lines_live", ("season", "week", "position", "unit_id")),
    "ops.kd_ranges": ("ops.kd_ranges_live", ("scoring_name", "season", "week", "position", "unit_id")),
}
LIVE_TABLES = tuple(o for o, _ in OVERLAYS.values())

_KEYWORDS = ("where", "order", "group", "left", "right", "inner", "outer", "full", "cross", "natural", "join", "on",
             "using", "limit", "offset", "union", "window", "having", "fetch", "for", "except", "intersect")
_FROM = re.compile(
    r"\b(?P<kw>from|join)(?P<ws>\s+)(?P<table>ops\.(?:projections|projection_lines|projection_ranges|kd_lines|kd_ranges))"
    r"\b(?![._])(?P<alias>\s+(?:as\s+)?(?!(?:" + "|".join(_KEYWORDS) + r")\b)[a-z_][a-z0-9_]*)?",
    re.IGNORECASE)


def relation(table: str) -> str:
    """The live relation for ``table`` (an ``OVERLAYS`` key): its rows without an overlay row, plus the overlay's rows
    as rows of ``table`` (no alias: the caller's)."""
    live, keys = OVERLAYS[table]
    match = " and ".join(f"v.{k} = s.{k}" for k in keys)
    return (f"(select s.* from {table} as s where not exists (select 1 from {live} as v where {match}) "
            f"union all select (jsonb_populate_record(null::{table}, to_jsonb(v))).* from {live} as v)")


def sql(text: str, active: Iterable[str] | None) -> str:
    """``text`` with every ``from`` / ``join`` of a table in ``active`` (stored tables whose overlay holds rows) made
    live; ``active`` empty or None: ``text`` itself."""
    act = frozenset(active or ())
    if not act or "ops." not in text:
        return text

    def sub(m: re.Match) -> str:
        t = m.group("table").lower()
        if t not in act:
            return m.group(0)
        alias = m.group("alias") or f" as {t.split('.', 1)[1]}"
        return f"{m.group('kw')}{m.group('ws')}{relation(t)}{alias}"

    return _FROM.sub(sub, text)


EXISTS_SQL = "select " + ", ".join(f"to_regclass('{o}') is not null as e{i}" for i, o in enumerate(LIVE_TABLES))


def _values(row) -> list:
    return list(row.values()) if isinstance(row, dict) else list(row)


def active(execute) -> frozenset[str]:
    """The stored tables whose overlay exists and holds a row. ``execute(sql) -> one row`` (a tuple or a dict) runs a
    statement on the reader's own connection. Two catalog-cheap statements; an overlay that is not there is not active."""
    exists = _values(execute(EXISTS_SQL))
    present = [b for b, e in zip(OVERLAYS, exists, strict=True) if e]
    if not present:
        return frozenset()
    rows = _values(execute("select " + ", ".join(f"exists (select 1 from {OVERLAYS[b][0]}) as h{i}"
                                                 for i, b in enumerate(present))))
    return frozenset(b for b, h in zip(present, rows, strict=True) if h)


def active_on(conn) -> frozenset[str]:
    """``active`` on a psycopg connection (``project``'s solves)."""
    def execute(q: str):
        with conn.cursor() as cur:
            cur.execute(q)
            return cur.fetchone()
    return active(execute)
