"""IF-1 (Wave I-F, the decision-quality review § "value the bench before prescribing drops") on the review's own case:
League of Scrubs roster 6 ("GoodGameBuddy"), whose mart held "Claim Daniel Carlson, drop Marvin Harrison Jr." (horizon
gain 13.46, `is_best_drop`) while the roster has Evan McPherson at K. The database is shared read-only: the engine runs
in memory (`waivers.load_and_sweep(only=…)` reads, never writes) and the API's rows are monkeypatched."""

from __future__ import annotations

import pandas as pd
import psycopg
import pytest
from league_lab import waivers as W

from league_lab_api import decisions

from .conftest import SCRUBS, needs_db

TEAM = 6
CARLSON, MCPHERSON, HARRISON = "Daniel Carlson", "Evan McPherson", "Marvin Harrison"


def _waivers(client, team: int = TEAM) -> dict:
    return client.get("/api/waivers", params={"league": SCRUBS, "team": team}).json()


def _moves(w: dict) -> list[dict]:
    return [*(w.get("moves") or []), *[c["move"] for c in w.get("top3") or []],
            *[c["move"] for c in w["views"]["help"]["moves"]], *[c["move"] for c in w["views"]["bye"]["moves"]]]


_ENGINE: dict = {}


def engine_rows(sql) -> pd.DataFrame:
    """The nightly's rows for roster 6 as the IF-1 engine writes them (computed in memory, read-only), dressed with the
    mart's own columns (team name, the add's NFL team, the published lineup value, the freshness flags)."""
    if "rows" not in _ENGINE:
        season = sql("select max(season) as s from ops.lineup_totals where not is_realised")[0]["s"]
        from league_lab.config import get_settings  # the engine reads staging (the pipeline role), read-only
        try:
            conn = psycopg.connect(get_settings().pipeline_dsn(), connect_timeout=5)
        except Exception as e:  # noqa: BLE001
            pytest.skip(f"the pipeline role is not reachable: {e}")
        with conn:
            conn.read_only = True
            rows, _, _ = W.load_and_sweep(conn, int(season), only=(SCRUBS, TEAM))
            conn.rollback()
        mart = pd.DataFrame(sql("select * from analytics.mart_waiver_moves where league_id = %s and roster_id = %s", (SCRUBS, TEAM)))
        df = pd.DataFrame(rows, columns=W.ALL_COLUMNS)
        team = {c: mart[c].iloc[0] for c in ("team_name", "manager_name", "lineup_value", "on_current_lineup", "inputs_current")
                if c in mart}
        df = df.assign(**team, add_team=df["add_sleeper_id"].map(dict(zip(mart["add_sleeper_id"], mart["add_team"], strict=True))))
        _ENGINE["rows"] = df.sort_values("move_rank", na_position="first").reset_index(drop=True)
    return _ENGINE["rows"].copy()


def _patch_rows(monkeypatch, df: pd.DataFrame) -> None:
    real = decisions.query

    def fake(q, params=()):
        if q == decisions.MOVES_SQL and params and str(params[0]) == SCRUBS and int(params[1]) == TEAM:
            return df.copy()
        return real(q, params)
    monkeypatch.setattr(decisions, "query", fake)


def _carlson(w: dict) -> dict:
    ms = [m for m in _moves(w) if (m.get("add") or {}).get("player_name") == CARLSON]
    assert ms, "Carlson's claim is on the answer"
    return ms[0]


# ------------------------------------------------------------------------------ the engine (the nightly's rows)
@needs_db
def test_the_engine_drops_mcpherson_for_carlson(sql):
    """B3 (a mart written before IF-1's writer) dropped Harrison for Carlson (equal horizon gains, the fewest rest-of-
    season points); the engine evaluates Carlson for McPherson as the direct replacement and names him the best drop.
    IG-3 (Wave I-G) re-pins the mart half to the rule instead of the clone's age: a mart the writer filled with the cost
    names choose_drops' drop (McPherson); one written before the cost still holds B3's (Harrison) — either way the
    gain is the same 13.46."""
    mart = sql("""select * from analytics.mart_waiver_moves where league_id = %s and roster_id = %s and add_name = %s
                  and is_best_drop""", (SCRUBS, TEAM, CARLSON))
    assert mart and mart[0]["horizon_gain"] == pytest.approx(13.46)
    if mart[0].get("drop_cost") is not None:                       # the writer ran with IF-1's cost (IG-3 on the clone)
        assert mart[0]["drop_name"] == MCPHERSON and mart[0]["drop_is_incumbent"]
    else:                                                          # a mart written before the cost: B3's drop
        assert mart[0]["drop_name"].startswith(HARRISON)
    df = engine_rows(sql)
    c = df[(df["add_name"] == CARLSON)]
    best = c[c["is_best_drop"].astype(bool)].iloc[0]
    assert best["drop_name"] == MCPHERSON and bool(best["drop_is_incumbent"])
    assert best["horizon_gain"] == pytest.approx(13.46) and best["net_horizon_gain"] == pytest.approx(13.46)
    assert set(c["drop_name"]) >= {MCPHERSON} and c["drop_name"].str.startswith(HARRISON).any()   # every legal pair evaluated
    # every claim on the roster no longer shares one drop
    drops = set(df.loc[df["is_best_drop"].fillna(False).astype(bool), "drop_name"].dropna())
    assert len(drops) >= 3 and MCPHERSON in drops and "Kirk Cousins" in drops
    # the cost pieces are on every drop row; McPherson against the wire's best K, Harrison against the best WR
    for col in ("drop_cost", "drop_lineup_loss", "drop_depth_lost", "drop_future_starts", "drop_season_value",
                "net_weekly_gain", "net_horizon_gain", "is_worthwhile"):
        assert df.loc[df["drop_sleeper_id"].notna(), col].notna().all(), col
    h = c[c["drop_name"].str.startswith(HARRISON)].iloc[0]
    assert h["drop_season_points"] == pytest.approx(79.08) and h["drop_season_value"] == 0.0
    assert best["drop_season_points"] == pytest.approx(104.5) and best["drop_replacement_points"] == pytest.approx(126.54)


@needs_db
def test_the_answer_on_the_engines_rows(client, sql, monkeypatch):
    """The Waivers answer on the engine's rows: Carlson's card drops McPherson, names Harrison and his season value as
    the alternative, carries the cost pieces, and never says "he sits anyway"."""
    _patch_rows(monkeypatch, engine_rows(sql))
    w = _waivers(client)
    m = _carlson(w)
    assert m["drop"]["player_name"] == MCPHERSON
    assert m["drop_why"].startswith("Drop McPherson: Carlson replaces him at K.")
    assert "Harrison" in m["drop_why"] and "season points" in m["drop_why"]
    assert m["alternative_drop"]["player"]["player_name"].startswith(HARRISON)
    dc = m["drop_cost"]
    assert set(dc) >= {"lineup_loss", "depth_lost", "future_starts", "season_value", "upside", "cost", "piece"}
    assert m["net_horizon_gain"] == pytest.approx(13.46) and m["is_worthwhile"] is True
    words = [c.get("cost") or "" for c in [*w["top3"], *w["views"]["help"]["moves"], *w["views"]["bye"]["moves"]]]
    assert words and not any("sits anyway" in x for x in words)
    assert len({(m.get("drop") or {}).get("player_name") for m in _moves(w)}) >= 2
    assert w["no_worthwhile_move"] is None


@needs_db
def test_the_answer_on_todays_mart(client):
    """The mart as built tonight (before the cost columns): the API re-ranks on read with the season value — the same
    drop for Carlson, so the live server is right before the nightly is rebuilt."""
    w = _waivers(client)
    m = _carlson(w)
    assert m["drop"]["player_name"] == MCPHERSON and m["drop_cost"]["season_value"] == 0.0
    assert "Harrison" in m["drop_why"]
    assert {(c["move"].get("drop") or {}).get("player_name") for c in w["top3"]} != {"Marvin Harrison Jr."}


@needs_db
def test_no_worthwhile_move(client, sql, monkeypatch):
    """A roster whose every drop is worth more than what the claim adds (each drop 40 season points above the wire,
    no open spot): the Help-now view says so instead of a claim."""
    df = engine_rows(sql)
    has = df["drop_sleeper_id"].notna()
    df.loc[has, "drop_season_value"] = 40.0
    df = df[has | (df["list_kind"] == "nothing")]
    df["open_roster_spots"] = 0
    _patch_rows(monkeypatch, pd.DataFrame(W.choose_drops(df.to_dict("records")), columns=df.columns))
    w = _waivers(client)
    nw = w["no_worthwhile_move"]
    assert nw is not None and nw["words"].startswith("No claim is worth a roster spot this week")
    assert nw["best_net_week"] < W.WORTH_WEEK and nw["best_net_horizon"] < W.WORTH_HORIZON
    assert w["views"]["help"]["line"] == nw["words"] and w["top3"] == [] and w["views"]["help"]["moves"] == []
    assert w["home_action"] is None


@needs_db
def test_stashes_stay_a_watchlist(client, sql, monkeypatch):
    """Roster 6's stashes add nothing to the lineup if the role holds (+0.0 over weeks 4–7): no drop is recommended,
    the row says watch and what would change it (before: every one dropped Harrison)."""
    _patch_rows(monkeypatch, engine_rows(sql))
    st = _waivers(client)["upside"]["stashes"]
    assert st, "roster 6 has upside stashes on the clone"
    for s in st:
        if s.get("stash_source") == "writer":     # IG-3: the writer's call (choose_drops) is shown as written
            if s["stash_action"] == "watch":
                assert s["drop"] is None and s["watch_words"].startswith("Watch, no claim yet")
            continue
        if (s.get("holds_horizon_gain") or 0.0) - ((s.get("drop_cost") or {}).get("cost") or 0.0) < decisions.GAIN_EPS:
            assert s["stash_action"] == "watch" and s["drop"] is None and s["watch_words"].startswith("Watch, no claim yet")
        else:
            assert s["stash_action"] == "claim"


@needs_db
def test_best_waiver_move_for_the_trade_finder(sql, monkeypatch):
    """IF-2's alternative: the claim with the largest net gain over the waiver horizon, its drop and cost."""
    _patch_rows(monkeypatch, engine_rows(sql))
    b = decisions.best_waiver_move(SCRUBS, TEAM)
    assert b["kind"] == "waiver" and b["player"]["player_name"] == CARLSON and b["drop"]["player_name"] == MCPHERSON
    assert b["gain_window"] == pytest.approx(13.46) and b["weeks"] == [4, 5, 6, 7] and b["source"] == "waivers.best_waiver_move"
    assert b["drop_cost"]["cost"] == 0.0
