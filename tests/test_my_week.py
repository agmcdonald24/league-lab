"""B4 acceptance on the database: Home's My Week shows exactly the proposed lineup of
`mart_lineup_recommendation` for the roster-week, and its decision cards are the smallest-margin unlocked
starters with the bench player who would come in. Andrew's two teams: dynasty roster 12, League of Scrubs
roster 2. Skipped when the database (.env) is not reachable.
"""

import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

APP = Path(__file__).resolve().parents[1] / "app"
CASES = [("1321941740235550720", 12), ("1389709692405551104", 2)]
LINK = re.compile(r"\[([^\]]+)\]\((Player\?[^)]+)\)")


@pytest.fixture(scope="module")
def conn():
    psycopg = pytest.importorskip("psycopg")
    from league_lab.config import get_settings

    try:
        c = psycopg.connect(get_settings().pipeline_dsn(), connect_timeout=3, autocommit=True)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"no database: {exc}")
    with c:
        if not c.execute("select to_regclass('analytics.mart_lineup_recommendation')").fetchone()[0]:
            pytest.skip("mart_lineup_recommendation not built")
        yield c


def _qs(url: str) -> dict:
    return {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}


def _run_home(league_id: str, roster_id: int):
    from streamlit.testing.v1 import AppTest

    if str(APP) not in sys.path:
        sys.path.insert(0, str(APP))
    at = AppTest.from_file(str(APP / "Home.py"), default_timeout=180)
    at.query_params["league"] = league_id
    at.query_params["team"] = str(roster_id)
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


@pytest.mark.parametrize(("league_id", "roster_id"), CASES)
def test_my_week_is_the_mart(conn, league_id, roster_id):
    at = _run_home(league_id, roster_id)
    head = next(h.value for h in at.subheader if h.value.startswith("My week"))
    week = int(re.search(r"week (\d+)", head).group(1))
    season = conn.execute("select season from analytics.dim_league_season where league_id = %s", (league_id,)).fetchone()[0]
    first_open = conn.execute(
        """select min(week) from (select week from analytics.dim_game where season = %s and season_type = 'REG'
           group by week having max(kickoff_at) > now()) w""", (season,)).fetchone()[0]
    assert week == first_open

    # 1. the lineup table = the mart's proposed lineup for that roster-week, slot by slot
    page = at.dataframe[0].value
    assert list(page.columns) == ["slot", "player_name", "player_value", "flag"]
    got = [(_qs(u).get("id"), _qs(u).get("name"), round(float(v), 2)) for u, v in zip(page["player_name"], page["player_value"], strict=True)]
    mart = conn.execute(
        """select gsis_id, player_name, round(player_value::numeric, 2)::float, slot, is_empty_slot
           from analytics.mart_lineup_recommendation
           where league_id = %s and season = %s and week = %s and roster_id = %s order by slot_order""",
        (league_id, season, week, roster_id)).fetchall()
    assert len(mart) >= 8
    assert got == [(g, n, v) for g, n, v, _, _ in mart]
    assert len(page) == len(mart)

    # 2. the cards: the smallest-margin unlocked, valued starters, each over the best bench player who can
    #    play that slot (for these rosters no teammate has to slide over), and the margin is the difference
    exp = conn.execute(
        """with elig(slot_type, pos) as (values ('QB','QB'),('RB','RB'),('WR','WR'),('TE','TE'),('K','K'),('DEF','DEF'),
               ('FLEX','RB'),('FLEX','WR'),('FLEX','TE'),('SUPER_FLEX','QB'),('SUPER_FLEX','RB'),('SUPER_FLEX','WR'),
               ('SUPER_FLEX','TE'),('REC_FLEX','WR'),('REC_FLEX','TE'),('WRRB_FLEX','RB'),('WRRB_FLEX','WR')),
           s as (select * from analytics.mart_lineup_recommendation
                 where league_id = %s and season = %s and week = %s and roster_id = %s
                   and not is_empty_slot and not is_locked and lineup_margin is not null and value_source <> 'unvalued'),
           b as (select * from ops.lineups where league_id = %s and season = %s and week = %s and roster_id = %s
                   and not is_realised and role = 'bench' and not is_locked)
           select s.slot, s.gsis_id, s.lineup_margin, s.player_value,
                  (select b.gsis_id from b join elig e on e.pos = b.position and e.slot_type = s.slot_type
                   order by b.value desc, b.bench_rank limit 1) as alt_gsis_id,
                  (select max(b.value) from b join elig e on e.pos = b.position and e.slot_type = s.slot_type) as alt_value,
                  -- when a teammate slides over, the one bench player whose value is his value minus the margin
                  (select b.gsis_id from b where abs(b.value - (s.player_value - s.lineup_margin)) <= 0.011
                   order by b.bench_rank limit 1) as entering
           from s order by s.lineup_margin, not s.is_weakest_slot, s.player_value, s.slot_order""",
        (league_id, season, week, roster_id) * 2).fetchall()
    expected = []
    for slot, g, m, v, alt, av, entering in exp:
        if abs(v - m) <= 0.011:
            continue                                              # nobody on the bench can replace him: no card
        expected.append((slot, g, alt if alt is not None and abs((v - av) - m) < 0.011 else entering))
    expected = expected[:3]
    cards = [m.value for m in at.markdown if re.match(r"\*\*[^*]+: start \[", m.value)]
    shown = []
    for text in cards:
        slot = re.match(r"\*\*([^:]+):", text).group(1)
        (_, me), (_, alt) = LINK.findall(text)[:2]
        shown.append((slot, _qs(me)["id"], _qs(alt)["id"]))
    from lib.cards import slot_label

    assert shown == [(slot_label(s), g, a) for s, g, a in expected]
    assert 2 <= len(shown) <= 3
    # the first card is the mart's weakest slot (the closest call of the week)
    weakest = conn.execute(
        """select distinct weakest_slot from analytics.mart_lineup_recommendation
           where league_id = %s and season = %s and week = %s and roster_id = %s""", (league_id, season, week, roster_id)).fetchone()[0]
    assert shown[0][0] == slot_label(weakest)
