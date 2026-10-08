"""IS-2 (Wave I-S): the league screens' one status read — ``availability.statuses`` + ``availability.sits``.

Every reader inside a league (Waivers' browse and its moves, the trade fill's free agents, the card, the rest-of-season
lineup values) asks the request-time blocks here — the nightly's stored record plus the overlay's Sleeper directory and
ESPN feed, the definition of ``league_lab.availability_gate`` — and never a status field or a set of codes of its own.
On a database without the stored record (between a deploy and the refresh) the overlay alone answers; with the overlay
off too, nobody is left out by a request-time read (the stored board's 0 still applies).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from league_lab import league_status as LS

from . import availability


def week() -> tuple[int | None, int | None]:
    """(season, the week the league screens decide): refleague's window, the same week ``/api/ros`` gates."""
    return availability._current()


def blocks(gsis_ids: Iterable[str] | None, season: int | None = None, wk: int | None = None) -> dict[str, dict]:
    """{gsis: block} for the players asked (every player with a word when None); {} on any failure."""
    if season is None or wk is None:
        season, wk = week()
    try:
        ids = None if gsis_ids is None else [g for g in gsis_ids if isinstance(g, str) and g]
        return availability.statuses(ids, season, wk)
    except Exception:  # noqa: BLE001 - the stored board's 0 still applies
        return {}


def sits(block: Mapping | None) -> bool:
    """``availability.sits``; anything that is not a block (None, a frame's NaN) is no word."""
    return availability.sits(dict(block)) if isinstance(block, Mapping) and block else False


note = LS.note
