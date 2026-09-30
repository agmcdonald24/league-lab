"""T-02 acceptance on the database (Trade Finder page, AppTest): the page renders with no simulation in the URL, with
a pasted one and with a broken one; a pasted URL reproduces the same simulation; the fit and market lines carry exactly
the numbers the captions and the tables show; the simulator equals league_lab.trades.evaluate on the same board and
opens on the best partner's trade; the buy-low list filters by position and by owner. Andrew's two teams: dynasty roster 12, League of Scrubs roster 2.
Skipped when the database (.env) is not reachable."""

import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

APP = Path(__file__).resolve().parents[1] / "app"
PAGE = APP / "pages" / "6_Trade_Finder.py"
CASES = [("1321941740235550720", 12), ("1389709692405551104", 2)]


@pytest.fixture(scope="module")
def conn():
    psycopg = pytest.importorskip("psycopg")
    from league_lab.config import get_settings

    try:
        c = psycopg.connect(get_settings().pipeline_dsn(), connect_timeout=3, autocommit=True)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"no database: {exc}")
    with c:
        if not c.execute("select to_regclass('analytics.mart_league_roster_horizon')").fetchone()[0]:
            pytest.skip("mart_league_roster_horizon not built")
        yield c


def run_page(league_id: str, roster_id: int, **params):
    from streamlit.testing.v1 import AppTest

    if str(APP) not in sys.path:
        sys.path.insert(0, str(APP))
    at = AppTest.from_file(str(PAGE), default_timeout=240)
    at.query_params["league"] = league_id
    at.query_params["team"] = str(roster_id)
    for k, v in params.items():
        at.query_params[k] = v
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def _one(v) -> str:
    """AppTest keeps a query parameter as a list of values."""
    return str(v[0]) if isinstance(v, list | tuple) else str(v)


def _frame(conn, sql: str, params: tuple):
    import pandas as pd

    cur = conn.execute(sql, params)
    return pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])


def sim_state(at) -> dict:
    """What the simulator shows: the verdict, the fit and market lines, the rank and size lines, the two lineup headers
    and captions, and every table on the page (moving players, both lineups, the lists)."""
    md = [m.value for m in at.markdown]
    return {
        "verdict": next((m for m in md if m.startswith("**You give ")), None),
        "fit": next((m for m in md if m.startswith("**Fit**")), None),
        "fair": next((m for m in md if m.startswith("**Market**")), None),
        "rank": next((m for m in md if m.startswith("League rank")), None),
        "size": next((m for m in md if m.startswith("Roster size")), None),
        "heads": [m for m in md if "lineup, week" in m],
        "caps": [c.value for c in at.caption if c.value.startswith(("Weeks", "Week ", "Starts after", "Sits after", "Empty after"))],
        "tables": [d.value.to_json() for d in at.dataframe],
        "qp": {k: _one(at.query_params[k]) for k in ("partner", "give", "get") if k in at.query_params},
    }


def board_for(conn, league_id):
    from league_lab.roster_value import RosterBoard
    from league_lab.trades import MARKET_SQL, REPLACEMENT_SQL, market_by_player, price_by_player

    rows = _frame(conn, """select roster_id, week, this_week, role, slot, slot_type, sleeper_player_id, gsis_id, player_name, position,
                                 fantasy_positions, player_value, value_source, lineup_margin, is_locked, reason
                          from analytics.mart_league_roster_horizon where league_id = %s""", (league_id,))
    slots, season = conn.execute("select roster_positions, season from analytics.dim_league_season where league_id = %s",
                                 (league_id,)).fetchone()
    week = int(rows["this_week"].iloc[0])
    mk = _frame(conn, MARKET_SQL, (league_id, season, week))
    repl = _frame(conn, REPLACEMENT_SQL, (league_id, season, week, league_id))
    b = RosterBoard(rows.to_dict("records"), list(slots))
    market = market_by_player(b, dict(zip(mk["player_key"], mk["season_points"], strict=True)))
    prices = price_by_player(b, market, dict(zip(repl["position"], repl["replacement"], strict=True)))
    return b, market, prices


def table_with(at, column: str):
    """The first table on the page that has `column` (tables inside collapsed expanders are in the tree too)."""
    return next(d.value for d in at.dataframe if column in d.value.columns)


def _qs(v) -> list[str]:
    return [x for x in str(v).split(",") if x]


@pytest.mark.parametrize(("league_id", "roster_id"), CASES)
def test_simulation_is_the_evaluator_and_the_link_reproduces_it(conn, league_id, roster_id):
    import pandas as pd

    from league_lab import trades as T

    at = run_page(league_id, roster_id)
    first = sim_state(at)
    # no package in the URL: the page opens on the best partner's best trade and writes it to the URL
    assert first["fair"] and first["fit"] and first["verdict"] and set(first["qp"]) == {"partner", "give", "get"}
    b, market, prices = board_for(conn, league_id)
    give, get = _qs(first["qp"]["give"]), _qs(first["qp"]["get"])
    t = T.evaluate(b, give, get, market=market, prices=prices)
    span = f"weeks {t.weeks[0]}–{t.weeks[-1]}"
    assert b.owner(get[0]) == int(first["qp"]["partner"])
    # the partner card's trade is the one the simulator opens on, and it raises both lineups over the horizon
    best = next(p.best for p in T.partners(b, roster_id) if p.best is not None)
    assert (list(best.give), list(best.get)) == (give, get)
    assert t.mine.gain_horizon >= 0.01 and t.theirs.gain_horizon >= 0.01
    assert first["fit"] == T.fit_line(t, span) and first["fair"] == T.fairness_line(t)
    assert first["verdict"].endswith(T.verdict(t, span))
    # the market line's numbers are the market table's column, summed
    nums = [int(x) for x in re.findall(r"\*\*(\d+)\*\*", first["fair"])]
    moving = table_with(at, "moving_to")
    to = moving["moving_to"].tolist()
    assert nums[0] == int(sum(v for v, d in zip(moving["market_price"], to, strict=True) if d != "You" and pd.notna(v)))
    assert nums[1] == int(sum(v for v, d in zip(moving["market_price"], to, strict=True) if d == "You" and pd.notna(v)))
    mine_head, theirs_head = first["heads"]
    assert f"({t.mine.gain_week:+.1f})" in mine_head and f"({t.theirs.gain_week:+.1f})" in theirs_head
    assert f"{t.mine.before[0]:.2f} → {t.mine.after[0]:.2f}" in mine_head
    horizon_caps = [c for c in first["caps"] if c.startswith("Weeks")]
    assert f"({t.mine.gain_horizon:+.1f})" in horizon_caps[0] and f"({t.theirs.gain_horizon:+.1f})" in horizon_caps[1]
    assert f"Depth (the bench's own lineup): {t.mine.bench_before:.2f} → {t.mine.bench_after:.2f}" in horizon_caps[0]
    # the lineup table's changes add up to the lineup's change
    lineup = table_with(at, "trade_change")
    assert abs(lineup["trade_change"].fillna(0).sum() - (t.mine.after[0] - t.mine.before[0])) < 0.011
    # a link with another trade (the second partner's) opens that trade, and the URL the page then writes, pasted
    # into a fresh session, shows the same simulation again
    second = next(p.best for p in T.partners(b, roster_id)[1:] if p.best is not None)
    params = {"partner": str(second.partner), "give": ",".join(second.give), "get": ",".join(second.get)}
    other = sim_state(run_page(league_id, roster_id, **params))
    assert other["qp"] == params and other["fit"] != first["fit"]
    t2 = T.evaluate(b, second.give, second.get, market=market, prices=prices)
    assert other["fit"] == T.fit_line(t2, span) and other["fair"] == T.fairness_line(t2)
    again = sim_state(run_page(league_id, roster_id, **other["qp"]))
    assert again == other
    assert sim_state(run_page(league_id, roster_id, **first["qp"])) == first


@pytest.mark.parametrize(("league_id", "roster_id"), CASES)
def test_broken_links_render(conn, league_id, roster_id):
    at = run_page(league_id, roster_id, partner="999", give="nobody,also-nobody", get="zzz")
    caps = [c.value for c in at.caption]
    assert any(c.startswith("Left out from the link") and "team 999" in c for c in caps)
    at = run_page(league_id, roster_id, partner="x", give="", get="")
    assert any(i.value.startswith("Tick at least one player") for i in at.info)


def test_buy_low_filters_by_position_and_owner(conn):
    league_id, roster_id = CASES[1]
    at = run_page(league_id, roster_id)
    n_all = len(at.dataframe)
    at.segmented_control(key="tf_position").set_value("RB").run()
    buy = table_with(at, "gain_week")
    names = [parse_qs(urlsplit(u).query)["name"][0] for u in buy["player"]]
    assert names and all(n.endswith("(RB)") for n in names)
    owners = conn.execute("""select roster_id, team_name from analytics.dim_league_member where league_id = %s and roster_id <> %s
                             order by team_name""", (league_id, roster_id)).fetchall()
    rid, team_name = next((r, t) for r, t in owners if t in set(buy["manager"]))
    at.selectbox(key="tf_owner").set_value(rid).run()
    buy2 = table_with(at, "gain_week")
    assert len(buy2) <= len(buy) and set(buy2["manager"]) == {team_name}
    assert all(parse_qs(urlsplit(u).query)["name"][0].endswith("(RB)") for u in buy2["player"])
    assert len(at.dataframe) <= n_all
