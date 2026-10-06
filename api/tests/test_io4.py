"""Wave I-O, IO-4 — the fix list and two things left twice.

1. Two players, one last name: My Week says "M. Washington" when Parker Washington is on the same roster.
2. A submitted lineup holding a player who has left the roster: one roster alert per spot, in words a manager can act on.
3. The matchup board: started / final games below the games to come ("Still to play" by default), the league's own
   defense rank in a real league, the context record's sentence when IO-1's module is there.
4. The role-change columns on Stats (one implementation with DFS: ``league_lab.role_trend``).
5. Each client's own share of the providers' budget (``ratelimit`` → ``league_lab.provider_share``).
"""

from __future__ import annotations

import re
import sys
import types

import pandas as pd
import pytest

from league_lab_api import myweek as M

from .conftest import ANDREW, SCRUBS, needs_db
from .test_in5 import FLEX_FLIP, SUBMITTED, _row, morning


# ------------------------------------------------------------------ 1. two players, one last name
def _two_washingtons(parker_value: float = 10.4) -> pd.DataFrame:
    rows = morning()
    rows.loc[rows["sleeper_player_id"] == "11624", "value"] = parker_value
    malik = _row("bench", None, "11610", "Malik Washington", "WR", 6.2)
    return pd.concat([rows, pd.DataFrame([malik])], ignore_index=True)


def test_short_name_uses_the_first_initial_only_on_a_collision():
    roster = ["Malik Washington", "Parker Washington", "Justin Jefferson", "Jacory Croskey-Merritt"]
    assert M.short_name("Parker Washington", "WR", roster) == "P. Washington"
    assert M.short_name("Malik Washington", "WR", roster) == "M. Washington"
    assert M.short_name("Justin Jefferson", "WR", roster) == "Jefferson"           # nobody else changes
    assert M.short_name("Jacory Croskey-Merritt", "RB", roster) == "Croskey-Merritt"
    assert M.short_name("Parker Washington", "WR", ["Parker Washington", "Justin Jefferson"]) == "Washington"
    assert M.short_name("Denver Broncos", "DEF", ["Denver Broncos"]) == "Denver Broncos"
    # a first initial both share keeps the full name (never two "J. Allen"s)
    assert M.short_name("Josh Allen", "QB", ["Josh Allen", "Jaylen Allen"]) == "Josh Allen"
    # suffixes: "Mike Washington Jr." is a Washington too
    assert M.short_name("Malik Washington", "WR", ["Malik Washington", "Mike Washington Jr."]) == "Malik Washington"
    assert M.short_name(None, "WR", roster) == ""


def test_andrews_two_washingtons_in_an_action_and_a_review_line():
    rows = _two_washingtons()
    res = M.build_actions(rows, [dict(FLEX_FLIP, margin=1.21, status="change", strength="lean")], SUBMITTED, SCRUBS)
    swap = [a for a in res["actions"] if "Washington" in a["action"]]
    assert [a["action"] for a in swap] == ["Start P. Washington at FLEX in place of Croskey-Merritt."]
    assert swap[0]["start"][0]["name"] == "P. Washington"
    # the coin flip, as the review line says it (the live sentence "Washington or Croskey-Merritt" was ambiguous)
    res = M.build_actions(_two_washingtons(9.25), [dict(FLEX_FLIP)], SUBMITTED, SCRUBS)
    assert [r["words"] for r in res["review"]] == [
        "P. Washington or Croskey-Merritt at FLEX: a coin flip, 0.1 points apart; your lineup has Croskey-Merritt — no "
        "clear upgrade."]
    text = " ".join(a["action"] + " " + a["reason"] for a in res["actions"]) + " ".join(r["words"] for r in res["review"])
    assert not re.search(r"(?<!\. )\bWashington\b", text.replace("[", " ").replace("]", " "))
    assert "Mahomes" in text and "M. Mahomes" not in text                         # nobody else changes


def test_a_keep_sentence_names_both_washingtons_apart():
    # the live sentence "Start Washington ahead of Jefferson and Croskey-Merritt for now." (a close call with a hurt
    # player): with Malik on the roster too it reads "P. Washington"
    rows = _two_washingtons(9.25)
    rows.loc[rows["sleeper_player_id"] == "11624", "report_status"] = "Questionable"
    sub = {**SUBMITTED}
    res = M.build_actions(rows, [dict(FLEX_FLIP, tiebreak={"kind": "injury", "side": "key", "pick": "Washington"})], sub,
                          SCRUBS)
    words = " ".join(a["action"] for a in res["actions"]) + " ".join(r["words"] for r in res["review"])
    assert "P. Washington" in words and not re.search(r"(?<!P\. )(?<!M\. )Washington", words.replace("[", ""))


@needs_db
def test_his_roster_from_the_database_has_both_washingtons(client):
    r = client.get(f"/api/my-week?league={SCRUBS}&team={ANDREW[SCRUBS]}")
    assert r.status_code == 200
    j = r.json()
    names = [x.get("player_name") for x in j.get("lineup", []) + j.get("lineup_full", []) if isinstance(x, dict)]
    text = " ".join(str(a.get(k) or "") for a in j.get("actions") or [] for k in ("action", "reason"))
    text += " ".join(str(r.get("words") or "") for r in j.get("review") or [])
    assert {"Malik Washington", "Parker Washington"} <= set(names)
    print("names:", [n for n in names if n and "Washington" in n], "| text:", text[:400])
    assert not re.search(r"(?<!\. )\bWashington\b", text.replace("[", " ").replace("]", " "))


# ------------------------------------------------------------------ 2. a lineup holding a player who is gone
def _full_week() -> pd.DataFrame:
    """A roster with every spot filled by the best lineup (no open spot): Shough at QB, Washington at FLEX."""
    rows = morning(qb=_row("starter", "QB", "12497", "Tyler Shough", "QB", 16.2))
    rows.loc[rows["slot"] == "TE", ["role", "sleeper_player_id", "player_name", "position", "value", "is_empty_slot",
                                    "kickoff_at"]] = ["starter", "12520", "Terrance Ferguson", "TE", 5.8, False,
                                                      pd.Timestamp("2026-10-11 17:00", tz="UTC")]
    rows = rows[~((rows["role"] == "unplayable") & (rows["sleeper_player_id"] == "12520"))]
    return rows.reset_index(drop=True)


SUB_FULL = {"12497": "QB", "8150": "RB", "12507": "RB", "4983": "WR", "11635": "WR", "12520": "TE", "12514": "FLEX",
            "11624": "FLEX", "4227": "K", "DEN": "DEF"}


def test_a_player_who_left_the_roster_is_one_alert_per_spot():
    rows = _full_week()
    assert M.build_actions(rows, [], SUB_FULL, SCRUBS)["actions"] == []          # the lineup as the best one: nothing
    # Washington's FLEX spot holds a player the roster no longer has ("9999"): the best lineup starts Washington there
    sub = {k: v for k, v in SUB_FULL.items() if k != "11624"} | {"9999": "FLEX"}
    res = M.build_actions(rows, [], sub, SCRUBS)
    for a in res["actions"]:
        print("action:", a["action"], "|", a["reason"])
    assert [a["action"] for a in res["actions"]] == [
        "A player in your Sleeper lineup is no longer on your roster — set that spot again."]
    a = res["actions"][0]
    assert a["reason"] == "Our lineup starts Washington there (your FLEX spot)."
    assert a["kind"] == "change" and a["slot_label"] == "FLEX" and [p["key"] for p in a["start"]] == ["11624"]
    assert a["lock"]["words"] and a["submitted"] is False
    text = " ".join(x["action"] + x["reason"] for x in res["actions"])
    assert "Take player" not in text and "player no longer on your roster out of" not in text
    # two such spots: one alert each (the second has nobody left over to name)
    sub2 = {k: v for k, v in sub.items() if k != "12514"} | {"9998": "FLEX"}
    gone = [x for x in M.build_actions(rows, [], sub2, SCRUBS)["actions"] if x.get("gone")]
    assert len(gone) == 2 and len({x["action"] for x in gone}) == 1
    assert sorted(x["reason"] for x in gone)[0].startswith("Our lineup starts ")
    # an MFL league says its own name
    mfl = [x for x in M.build_actions(rows, [], sub, "mfl:70587")["actions"] if x.get("gone")]
    assert len(mfl) == 1 and mfl[0]["action"] == (f"A player in your {M.platform_name('mfl:70587')} lineup is no longer on "
                                                  "your roster — set that spot again.") and "Sleeper" not in mfl[0]["action"]


# ------------------------------------------------------------------ 3. the matchup board
from league_lab_api import matchup_board as MB  # noqa: E402

SUNDAY_230 = "2026-10-04T18:30:00Z"      # week 4, Sunday 2:30 PM ET: Thursday's game final, the 1:00 PM games started


def test_game_state_reads_the_clock_not_a_future_final_flag():
    now = pd.Timestamp("2026-10-04T18:30:00Z")
    assert MB.game_state(pd.Timestamp("2026-10-04T20:25Z"), True, now) is None        # final in the data, not yet kicked off
    assert MB.game_state(pd.Timestamp("2026-10-04T17:00Z"), False, now) == "started"
    assert MB.game_state(pd.Timestamp("2026-10-04T17:00Z"), True, now) == "final"
    assert MB.game_state(pd.Timestamp("2026-10-02T00:15Z"), False, now) == "final"    # 4 hours on: over
    assert MB.game_state(None, True, now) is None


@needs_db
def test_board_puts_started_games_below_and_still_to_play_first(client):
    from league_lab import clock
    MB.clear()
    with clock.pinned(SUNDAY_230):
        j = client.get("/api/matchups/board?league=ref:half&position=WR&show=all&limit=100").json()
        default = client.get("/api/matchups/board?league=ref:half&position=WR&limit=100").json()
        bad = client.get("/api/matchups/board?league=ref:half&show=later")
    states = [r["game_state"] for r in j["rows"]]
    print("week", j["week"], "games started", j["started_games"], "of", len(j["games"]), "players started",
          j["started_players"], "of", j["total"])
    assert j["week"] == 4 and j["show"] == "all" and 0 < j["started_games"] < len(j["games"])
    assert {"final", "started"} <= set(states) | {"started"} and "final" in states
    first_started = next(i for i, s in enumerate(states) if s)
    assert all(s is None for s in states[:first_started]) and all(s for s in states[first_started:])
    assert j["total"] == len(j["rows"]) or j["total"] > 100
    # the default once a game has started: "Still to play" — none of them, the counts follow
    assert default["show"] == "to_play" and default["total"] == j["total"] - j["started_players"]
    assert all(r["game_state"] is None for r in default["rows"])
    assert sum(default["counts"].values()) == default["total"]
    assert {g["state"] for g in default["games"]} >= {None, "final"}
    assert bad.status_code == 400
    # before any kickoff (the suite's Saturday): Thursday's game is final, so "Still to play" is the default too
    MB.clear()
    sat = client.get("/api/matchups/board?league=ref:half&position=WR").json()
    assert sat["started_games"] >= 1 and sat["show"] == "to_play"


@needs_db
def test_a_real_league_reads_the_defense_rank_the_heatmap_shows(client):
    MB.clear()
    j = client.get(f"/api/matchups/board?league={SCRUBS}&position=WR&show=all&limit=100").json()
    heat = client.get(f"/api/matchups/defense?league={SCRUBS}&position=WR").json()
    assert j["defense_source"] == "league"
    tough = {t["defense"]: t["tough_rank"] for t in heat["teams"] if t["position"] == "WR"}
    differ = 0
    for r in j["rows"]:
        d = r["context"]["defense"]
        assert d["tough_rank"] == tough.get(r["opponent"]), (r["player_name"], r["opponent"])
        ref = MB.matchup_context(j["season"], j["week"], [r["gsis_id"]]).get(r["gsis_id"])
        differ += bool(ref and ref["defense"]["tough_rank"] != d["tough_rank"])
    print("rows", len(j["rows"]), "rows whose reference rank differs from the league's:", differ)
    # browsing keeps the reference mart
    b = client.get("/api/matchups/board?league=ref:half&position=WR&show=all&limit=50").json()
    assert b["defense_source"] == "reference"
    for r in b["rows"]:
        ref = MB.matchup_context(b["season"], b["week"], [r["gsis_id"]])[r["gsis_id"]]
        assert r["context"]["defense"] == ref["defense"] and r["context"]["tone"] == ref["tone"]


def test_the_record_sentence_replaces_not_graded_only_when_graded(monkeypatch):
    assert MB.projection_words() == MB.PROJECTION_WORDS                 # IO-1's module absent in this branch
    fake = types.ModuleType("league_lab_api.context_record")
    words = ("Receivers facing a likely shutdown corner scored 0.3 points under their projection on average over 212 "
             "games (−0.9 to +0.4) — no measurable effect")
    fake.summary = lambda: {"corner": {"graded": True, "n": 212, "words": words},
                            "worth": {"graded": False, "n": 0, "words": None}}
    monkeypatch.setitem(sys.modules, "league_lab_api.context_record", fake)
    import league_lab_api
    monkeypatch.setattr(league_lab_api, "context_record", fake, raising=False)
    got = MB.projection_words()
    assert got.endswith(words + ".") and "has not been graded yet" not in got
    assert got.startswith("What the projection counts:")
    fake.summary = lambda: {"corner": {"graded": False, "n": 0, "words": None}, "worth": {"graded": False, "n": 0,
                                                                                           "words": None}}
    assert MB.projection_words() == MB.PROJECTION_WORDS
    def boom():
        raise RuntimeError("no table")
    fake.summary = boom
    assert MB.projection_words() == MB.PROJECTION_WORDS


# ------------------------------------------------------------------ 4. the role-change columns on Stats
from league_lab import role_trend as RT  # noqa: E402
from league_lab_api import stats as ST  # noqa: E402


def _rg(gid, pos, rows):
    """(week, targets, team_targets, carries, team_carries, snaps, snap_pct) per game, played."""
    return [{"gsis_id": gid, "position": pos, "week": w, "played": True, "targets": t, "team_targets": tt, "carries": c,
             "team_carries": tc, "offense_snaps": s, "offense_snap_pct": sp} for w, t, tt, c, tc, s, sp in rows]


def test_role_columns_are_dfs_arithmetic_signed_in_points_of_share():
    g = pd.DataFrame(_rg("wr", "WR", [(1, 4, 40, 0, 25, 40, 40 / 65), (2, 5, 35, 0, 25, 42, 42 / 66),
                                      (3, 9, 36, 0, 25, 60, 60 / 64), (4, 10, 34, 0, 25, 62, 62 / 66)])
                     + _rg("rb", "RB", [(1, 2, 40, 10, 25, 30, 0.5), (2, 2, 35, 12, 25, 30, 0.5),
                                        (3, 2, 36, 18, 25, 40, 0.6), (4, 2, 34, 20, 25, 40, 0.6)])
                     + _rg("new", "WR", [(3, 9, 36, 0, 25, 60, 0.9), (4, 10, 34, 0, 25, 62, 0.9)]))
    pos = pd.Series({"wr": "WR", "rb": "RB", "new": "WR"})
    out = ST.role_columns(g, pos)
    assert out.loc["wr", "target_share_change"] == pytest.approx(19 / 70 - 9 / 75, abs=1e-4)      # summed / summed
    assert out.loc["wr", "snap_share_change"] == pytest.approx(122 / 130 - 82 / 131, abs=1e-4)
    assert pd.isna(out.loc["wr", "carry_share_change"])                         # a running back's measure
    assert out.loc["rb", "carry_share_change"] == pytest.approx(38 / 50 - 22 / 50, abs=1e-4)
    assert pd.isna(out.loc["new", "target_share_change"])                       # 2 games, none before: unknown, not 0
    assert out.loc["wr", "role_games_recent"] == 2 and out.loc["wr", "role_games_before"] == 2
    # DFS reads the same numbers (one implementation)
    one = g[g["gsis_id"] == "wr"].assign(team_snaps=lambda d: (d["offense_snaps"] / d["offense_snap_pct"]).round())
    r = RT.role_trend(one, "WR")
    ts = next(m for m in r["measures"] if m["measure"] == "target_share")
    assert ts["change"] == pytest.approx(out.loc["wr", "target_share_change"], abs=1e-3)


def test_the_moved_role_trend_is_the_old_one_on_random_players():
    """The function as it was in src/league_lab/dfs.py (main cf8e743), kept here verbatim as the reference: the moved
    implementation gives the same answer on 1,500 random players (measures missing, zero denominators, short samples)."""
    import numpy as np

    from league_lab import dfs as D

    def old_ratio(g, num, den):
        if num not in g or den not in g:
            return None
        ok = g[num].notna() & g[den].notna() & (pd.to_numeric(g[den], errors="coerce") > 0)
        if not ok.any() or ok.sum() < len(g):
            return None
        d = float(pd.to_numeric(g.loc[ok, den]).sum())
        if d < RT.ROLE_MIN_DEN.get(den, 1.0) * len(g) / RT.ROLE_RECENT:
            return None
        return float(pd.to_numeric(g.loc[ok, num]).sum()) / d

    def old_role_trend(games, position):
        if position not in ("RB", "WR", "TE") or games is None or games.empty:
            return None
        g = games.sort_values("week")
        recent, before = g.tail(RT.ROLE_RECENT), g.iloc[: max(0, len(g) - RT.ROLE_RECENT)]
        if len(recent) < RT.ROLE_RECENT or len(before) < RT.ROLE_MIN_BEFORE:
            return None
        moved = []
        for name, m in RT.ROLE_MEASURES.items():
            if position not in m["pos"]:
                continue
            a, b = old_ratio(recent, m["num"], m["den"]), old_ratio(before, m["num"], m["den"])
            if a is None or b is None:
                continue
            if abs(a - b) >= m["move"] - 1e-9:
                moved.append({"measure": name, "recent": round(a, 3), "before": round(b, 3), "change": round(a - b, 3),
                              "signal": m["signal"], "words": m["words"]})
        ups, downs = [x for x in moved if x["change"] > 0], [x for x in moved if x["change"] < 0]
        if not moved or (ups and downs):
            return None
        up = bool(ups)
        parts = [f"{x['recent']:.0%} {x['words']} ({x['before']:.0%})" for x in moved]
        signals = {x["signal"] for x in moved}
        return {"trend": "up" if up else "down", "tone": "favorable" if up else "difficult",
                "words": (f"Role {'up' if up else 'down'} in his last two games (the {len(before)} before in brackets): "
                          + ", ".join(parts) + "."), "measures": moved,
                "signal": "role" if "role" in signals else "routes", "games": [len(recent), len(before)]}

    rng = np.random.default_rng(4)
    said = 0
    for i in range(1500):
        n = int(rng.integers(0, 8))
        weeks = sorted(rng.choice(np.arange(1, 18), size=n, replace=False)) if n else []
        rows = []
        for w in weeks:
            tt, tc, ts, td = (int(rng.integers(15, 45)), int(rng.integers(10, 35)), int(rng.integers(40, 80)),
                              int(rng.integers(15, 45)))
            rows.append({"week": int(w), "targets": int(rng.integers(0, 14)), "team_targets": tt if rng.random() > 0.03 else 0,
                         "carries": int(rng.integers(0, 25)), "team_carries": tc,
                         "offense_snaps": None if rng.random() < 0.05 else int(rng.integers(5, ts)), "team_snaps": ts,
                         "routes": None if rng.random() < 0.5 else int(rng.integers(0, td)),
                         "team_dropbacks_with_participation": td})
        g = pd.DataFrame(rows, columns=["week", "targets", "team_targets", "carries", "team_carries", "offense_snaps",
                                        "team_snaps", "routes", "team_dropbacks_with_participation"])
        g = g.sample(frac=1.0, random_state=i) if len(g) else g                          # rows in any order
        pos = ("WR", "RB", "TE", "QB")[i % 4]
        new, old = D.role_trend(g, pos), old_role_trend(g, pos)
        assert new == old, (i, pos, g.to_dict("records"), new, old)
        said += new is not None
    print("players with a trend said:", said, "of 1500")
    assert said > 50


@needs_db
def test_stats_role_columns_match_the_dfs_board_and_say_why_when_unknown(client):
    import time

    from league_lab_api import dfs as AD
    ST.clear()
    t = time.perf_counter()
    r = client.get(f"/api/players?league=ref:half&season=2026&window=season&position=WR,TE,RB&min_games=0&limit=1000")
    cold = time.perf_counter() - t
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    t = time.perf_counter()
    client.get(f"/api/players?league=ref:half&season=2026&window=season&position=WR,TE,RB&min_games=0&limit=1000")
    warm = time.perf_counter() - t
    cat = {c["id"]: c for c in d["catalogue"]}
    for cid in ("target_share_change", "carry_share_change", "snap_share_change"):
        c = cat[cid]
        assert c["group"] == "Role change" and c["available"] and c["numerator"] and c["denominator"] and c["reason"]
    rows = {p["gsis_id"]: p for p in d["players"]}
    have = {cid: sum(1 for p in rows.values() if p.get(cid) is not None) for cid in cat if cid.endswith("_change")}
    print(f"cold {cold:.2f} s, warm {warm:.2f} s; players {len(rows)}; with a value: {have}")
    assert all(v > 50 for k, v in have.items() if k != "carry_share_change") and have["carry_share_change"] > 20
    # DFS's board for week 5 reads the games before week 5 = this season's window (weeks 1-4): the same numbers
    role = AD._context_parts(2026, 5)["role"]
    checked = 0
    for gid, tr in role.items():
        if not tr or gid not in rows:
            continue
        for m in tr["measures"]:
            if m["measure"] == "route_rate":
                continue
            got = rows[gid].get(f"{m['measure']}_change")
            assert got is not None and got == pytest.approx(m["change"], abs=6e-4), (gid, m, got)
            checked += 1
    print("DFS role-trend measures checked against Stats:", checked)
    assert checked > 20
    # sortable: the biggest riser first, unknown last
    s = client.get("/api/players?league=ref:half&season=2026&window=season&position=WR&sort=target_share_change&dir=desc"
                   "&limit=1000&min_games=0").json()["players"]
    vals = [p.get("target_share_change") for p in s]
    known = [v for v in vals if v is not None]
    assert known == sorted(known, reverse=True) and vals[: len(known)] == known
    # a 3-game window cannot hold 2 games and 2 before them: unknown, never 0
    w3 = client.get("/api/players?league=ref:half&season=2026&window=last3&position=WR&limit=50").json()["players"]
    assert all(p.get("target_share_change") is None for p in w3)


def test_the_inventory_has_the_role_change_rows():
    from league_lab_api.settings import ROOT
    text = (ROOT / "docs" / "DATA_INVENTORY.md").read_text()
    for cid in ("target_share_change", "carry_share_change", "snap_share_change"):
        assert any(ln.startswith(f"| `{cid}` ") and "derived" in ln for ln in text.splitlines()), cid
