"""Hotfix 2026-10-07: the player card's answer carries his picture (dim_player.headshot_url; the contract since Wave G,
never sent — the page and the drawer drew a silhouette for every player)."""

import pytest

from league_lab_api import db

from .conftest import needs_db

SCRUBS, DYNASTY = "1389709692405551104", "1321941740235550720"


def _face(gsis: str):
    rows = db.query("select headshot_url from analytics.dim_player where gsis_id = %s", (gsis,))
    v = rows.iloc[0]["headshot_url"] if not rows.empty else None
    return v if isinstance(v, str) and v else None


@needs_db
@pytest.mark.parametrize("league,team", [("ref:half", None), ("ref:ppr.sf", None), (SCRUBS, 2), (DYNASTY, 12)])
def test_the_card_carries_the_players_picture(client, league, team):
    gsis = "00-0039075"                                                          # Puka Nacua
    face = _face(gsis)
    assert face and face.startswith("https://")                                  # the database has his picture
    q = f"/api/player/{gsis}?league={league}" + (f"&team={team}" if team else "")
    r = client.get(q)
    assert r.status_code == 200, r.text
    assert r.json()["headshot_url"] == face


@needs_db
def test_no_picture_is_none_never_an_empty_string(client):
    rows = db.query("""select gsis_id from analytics.dim_player
                       where (headshot_url is null or headshot_url = '') and position in ('QB', 'RB', 'WR', 'TE')
                         and last_season = 2026 limit 1""")
    if rows.empty:
        pytest.skip("every 2026 skill player has a picture in this database")
    r = client.get(f"/api/player/{rows.iloc[0]['gsis_id']}?league=ref:half")
    if r.status_code == 200:
        assert r.json()["headshot_url"] is None


@needs_db
def test_a_defense_has_no_picture(client):
    r = client.get("/api/player/DEN?league=ref:half")
    assert r.status_code == 200 and r.json()["headshot_url"] is None
