"""PO hotfix (2026-10-06): a roster with two open lineup spots broke the Team screen (both rows carried the id "nan"),
and a spot nobody on the bench can fill read "Start Kelce out of your lineup"."""
from league_lab_api import decisions as D
from league_lab_api import myweek as M


def test_an_open_slot_has_no_player_id():
    for nothing in (None, float("nan"), "nan", "NaN", ""):
        assert D._sid(nothing) is None
        assert D._player(nothing, None, None, None)["sleeper_id"] is None
    assert D._sid("8150") == "8150"
    assert D._sid(8150) == "8150"
    assert D._player("BUF", None, "Buffalo Bills", "DEF")["team"] == "BUF"
    assert D._player(float("nan"), None, None, "DEF")["team"] is None


def test_a_spot_nobody_can_fill_is_not_a_start():
    a = M._action("change", [], ["1466"], False, 0.0, ["1466"], [], [], [(None, "1466")], set(), "Sleeper",
                  name=lambda k: "Kelce", plain=lambda k: "Kelce", status=lambda k: None,
                  cant_words=lambda k: "is on a bye", val=lambda k: None, slot_of=lambda k: None)
    assert a["action"] == "Take Kelce out of your lineup."
    assert "Start" not in a["action"]
