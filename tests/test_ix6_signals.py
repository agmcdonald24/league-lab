"""IX-6 (Wave I-X), item 2: a game he left hurt is not a role change (signals ra1.3). Ja'Marr Chase, 2026: 94% of the
snaps for three games, then 15 snaps (20%) in week 4 — hurt on a play in the 2nd quarter (the injury note named him:
lf1.0's LE-A) — the week Mitchell Tinsley came back. ra1.2 read it as "Smaller role … Why: Mitchell Tinsley back"."""

from __future__ import annotations

from dataclasses import replace

from league_lab import signals
from league_lab.signals import alerts_for_season

from .test_signals import G


def _cincinnati(hurt: bool, week5: bool = True) -> list:
    chase = [G("chase", 1, 0.94, tgt=4, team_tgt=34), G("chase", 2, 0.88, tgt=9, team_tgt=31),
             G("chase", 3, 1.00, tgt=12, team_tgt=37), G("chase", 4, 0.20, tgt=3, team_tgt=53)]
    chase[3] = replace(chase[3], hurt_early=hurt)
    if week5:
        chase.append(G("chase", 5, 0.93, tgt=10, team_tgt=33))
    tinsley = [G("tinsley", w, 0.0, status="out_injured") for w in (1, 2, 3)] + \
              [G("tinsley", w, 0.70, tgt=5) for w in (4, 5)]
    others = [G("wr2", w, 0.85, tgt=6) for w in range(1, 6)]
    return chase + tinsley + others


def _alerts(games) -> dict:
    return {(a.game.gsis_id, a.game.week): a for a in alerts_for_season(games, {}, {})}


def test_without_the_mark_the_drop_reads_as_a_smaller_role():
    """The control: the same games with no left-hurt mark give ra1.2's alert (so the test below means something)."""
    a = _alerts(_cincinnati(hurt=False, week5=False)).get(("chase", 4))
    assert a is not None and a.direction == "down"
    assert signals.change_text(a).startswith("snap share 94% → 20%")


def test_a_game_left_hurt_raises_no_alert_and_is_no_before_game():
    got = _alerts(_cincinnati(hurt=True))
    assert ("chase", 4) not in got                    # no "smaller role" from the injury exit
    assert ("chase", 5) not in got                    # and his week 5 at 93% is no "bigger role" against it
    assert not any(k[0] == "chase" for k in got)


def test_the_rule_version_moved():
    assert signals.SIGNALS_VERSION.startswith("ra1.3")
