"""IX-6 (Wave I-X): the card's Signals words after a game he left hurt (signals ra1.3 calls no role change from it, so
"his share is where it has been" would not be true either). Pure: the database read is replaced by a frame."""

from __future__ import annotations

import pandas as pd

from league_lab_api import onfield as OF

REASON = "15 snaps (20% of the team's; usually 94%); hurt on a play in the 2nd quarter"


def _latest(left_early, reason, week=4):
    return lambda sql, params: pd.DataFrame([{"week": week, "left_early": left_early, "reason": reason}])


def test_his_newest_game_left_hurt_gives_the_week(monkeypatch):
    monkeypatch.setattr(OF, "query", _latest(True, REASON))
    assert OF.latest_hurt_week("00-0036900", 2026) == 4
    assert OF.HURT_ROLE_WORDS.format(week=4).startswith(
        "Role: **no role change called**: he left his last game (week 4) hurt, and a game cut short by an injury is not "
        "read as a smaller role.")


def test_a_short_game_without_the_injury_note_or_a_full_game_is_not_hurt(monkeypatch):
    monkeypatch.setattr(OF, "query", _latest(True, "12 snaps (18% of the team's; usually 70%); no target or carry after half-time"))
    assert OF.latest_hurt_week("x", 2026) is None
    monkeypatch.setattr(OF, "query", _latest(False, None))
    assert OF.latest_hurt_week("x", 2026) is None
    monkeypatch.setattr(OF, "query", lambda sql, params: pd.DataFrame(columns=["week", "left_early", "reason"]))
    assert OF.latest_hurt_week("x", 2026) is None
    assert OF.latest_hurt_week("x", None) is None
