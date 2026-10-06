"""IN-5 (Wave I-N): an id as text on an answer's way out — never the words of a missing value.

A frame turns a missing Sleeper id (an open lineup slot, a player with no id) into NaN and ``str()`` makes it the text
``"nan"`` (``None`` → ``"None"``); the screens key their lists by these ids, and two equal keys stopped the Team screen
(2026-10-06, `decisions._sid` — the PO's hotfix — is the same rule for one place). Every id an answer sends that comes
from a frame or a provider goes through ``text_id``.
"""

from __future__ import annotations

MISSING = frozenset({"nan", "none", "null", "nat", "undefined", ""})


def text_id(x) -> str | None:
    """The id as text; None for a missing one (None, NaN, NaT, "nan", "None", "", whitespace). A whole float (8150.0,
    from an integer column a NaN turned into floats) loses its ".0"."""
    if x is None:
        return None
    if isinstance(x, float):
        if x != x:                      # NaN
            return None
        if x.is_integer():
            return str(int(x))
    try:
        import pandas as pd
        if x is pd.NaT:
            return None
    except Exception:  # noqa: BLE001 - pandas is always there; never a failure for an id
        pass
    s = str(x).strip()
    return None if s.lower() in MISSING else s
