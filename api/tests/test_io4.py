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

    def hist(ev):                                      # the evidence's defense history (research._history's shape)
        if isinstance(ev, dict):
            if "tough_rank" in ev and "scoring" in ev and "defense" in ev:
                return ev
            for v in ev.values():
                h = hist(v)
                if h:
                    return h
        return None
    seen = 0
    for r in j["rows"][:25]:
        h = hist(r.get("matchup_evidence"))
        if h:
            seen += 1
            assert h["tough_rank"] == r["context"]["defense"]["tough_rank"] and "Half PPR scoring" != h["scoring"], h
    assert seen >= 10
    # browsing keeps the reference mart
    b = client.get("/api/matchups/board?league=ref:half&position=WR&show=all&limit=50").json()
    assert b["defense_source"] == "reference"
    for r in b["rows"]:
        ref = MB.matchup_context(b["season"], b["week"], [r["gsis_id"]])[r["gsis_id"]]
        assert r["context"]["defense"] == ref["defense"] and r["context"]["tone"] == ref["tone"]


# IO-1's corner sentence as its grade writes it (``context_record.corner_sentence`` on the fix round's numbers)
RECORD_WORDS = ("Graded on 2025 and 2026 weeks 1–4 (Half PPR): receivers with a likely shutdown corner finished 0.4 points "
                "below the other receivers against their projection (−1.4 to +0.7; 99 games), those with a likely easy one "
                "level with them (−1.1 to +1.2; 79 games) — no measurable effect either way.")


def test_the_honesty_line_with_and_without_the_record(monkeypatch):
    from league_lab import context_record as LC

    from league_lab_api import context_record as CR
    rows = [{"corner_certainty": "likely", "corner_tier": "shutdown", "n": 99, "vs_rest": -0.39, "vs_rest_lo": -1.39,
             "vs_rest_hi": 0.72},
            {"corner_certainty": "likely", "corner_tier": "target", "n": 79, "vs_rest": -0.02, "vs_rest_lo": -1.11,
             "vs_rest_hi": 1.22}]
    assert LC.corner_sentence(rows, "2025 and 2026 weeks 1–4") == RECORD_WORDS
    # this database has no ops.context_grade: the real module answers "not graded", the line is the inputs alone
    CR.clear()
    assert MB.projection_words() == MB.PROJECTION_WORDS == MB.PROJECTION_HEAD
    for w in (MB.PROJECTION_WORDS, MB.TONE_WORDS):
        assert "not been graded" not in w and "not graded" not in w
    assert "Who plays cornerback is not in it" in MB.PROJECTION_WORDS and "shown for context" in MB.PROJECTION_WORDS
    # with the record: the inputs, then IO-1's sentence
    monkeypatch.setattr(CR, "summary", lambda: {"corner": {"graded": True, "n": 2190, "words": RECORD_WORDS, "tiers": {}},
                                                "worth": {"graded": False, "n": 0, "words": None}})
    got = MB.projection_words()
    assert got == f"{MB.PROJECTION_HEAD} {RECORD_WORDS}"
    monkeypatch.setattr(CR, "summary", lambda: {"corner": {"graded": False, "n": 0, "words": None}, "worth": {}})
    assert MB.projection_words() == MB.PROJECTION_WORDS

    def boom():
        raise RuntimeError("no table")
    monkeypatch.setattr(CR, "summary", boom)
    assert MB.projection_words() == MB.PROJECTION_WORDS


def test_the_corner_moves_nothing():
    """The PO's decision on IO-1's grade (no measurable effect): every combination gives the defense's tone."""
    import itertools
    for d, c, cert in itertools.product((*MB.TONES, None), (*MB.TONES, None), ("likely", "unclear", "no call", None)):
        assert MB.combine_tone(d, c, cert) == d
    assert MB._sentence({"words": "Kansas City gives up the 9th-fewest points to receivers"},
                        {"words": "McDuffie (a top-quarter corner, #2 of 74) is likely across from him", "tone": None,
                         "certainty": "likely"}, "difficult") == "Kansas City gives up the 9th-fewest points to receivers."


@needs_db
def test_the_week_context_carries_the_corner_as_information(client):
    MB.clear()
    ctx = MB.matchup_context(2026, 4)
    wr = [c for c in ctx.values() if c["cb"] is not None]
    likely = [c for c in wr if c["cb"]["certainty"] == "likely"]
    assert wr and likely
    for c in wr:
        assert c["cb"]["tone"] is None and c["tone"] == c["defense"]["tone"]
        assert c["words"] == (f"{c['defense']['words']}." if c["defense"]["words"] else None)
        assert not any(w in (c["cb"]["words"] or "") for w in ("shutdown corner", "easy to throw on"))
    tiers = {c["cb"]["tier"] for c in likely}
    print("likely calls:", len(likely), "tiers:", sorted(t or "-" for t in tiers))
    assert tiers <= {"shutdown", "solid", "target", None} and tiers - {None}
    j = client.get("/api/matchups/board?league=ref:half&position=WR&show=all&limit=100").json()
    assert all(r["context"]["tone"] == r["context"]["defense"]["tone"] for r in j["rows"])
    assert j["projection_words"] == MB.PROJECTION_WORDS and j["tone_words"] == MB.TONE_WORDS


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
    r = client.get("/api/players?league=ref:half&season=2026&window=season&position=WR,TE,RB&min_games=0&limit=1000")
    cold = time.perf_counter() - t
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    t = time.perf_counter()
    client.get("/api/players?league=ref:half&season=2026&window=season&position=WR,TE,RB&min_games=0&limit=1000")
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


# ------------------------------------------------------------------ 5. each client's own share of the providers' budget
from league_lab import anyleague as A  # noqa: E402
from league_lab import provider_share as PS  # noqa: E402

from league_lab_api import ratelimit  # noqa: E402

ON_DEMAND = "9000000000000000001"             # the fixtures' Sleeper league that is not in the database (on demand)
SCREENS = ("/api/my-week?league={l}&team=1", "/api/team?league={l}&team=1", "/api/league?league={l}&team=1",
           "/api/league/outlook?league={l}&team=1")


class _Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def _cold() -> None:
    """A league this process has never answered: the Sleeper client's caches and every answer cache emptied."""
    from league_lab import memo

    from league_lab_api import availability, db
    A._default = None
    A.clear_priced()
    db.clear_cache()
    availability.clear_context()
    memo.BUDGET.clear()                                 # every answer cache (the outlook's schedule included)
    ratelimit.SEEN = ratelimit.Seen()


def _open_league(client, league: str, peer: str | None = None) -> list[int]:
    kw = {"headers": {}} if peer is None else {}
    return [client.get(p.format(l=league), **kw).status_code for p in SCREENS]


def test_the_share_counts_per_client_and_never_without_one():
    clk = _Clock()
    sh = PS.Shares({"sleeper": (60.0, 5.0)}, clock=clk)
    assert all(sh.take("sleeper", "1.2.3.4") for _ in range(5)) and not sh.take("sleeper", "1.2.3.4")
    assert sh.take("sleeper", "5.6.7.8")                       # another client: its own share
    assert sh.take("sleeper", None) and sh.take("espn", "1.2.3.4")   # no client / no share for that provider: no limit
    clk.t += 1.0                                               # one a second comes back
    assert sh.take("sleeper", "1.2.3.4") and not sh.take("sleeper", "1.2.3.4")
    assert sh.info()["sleeper"]["refused"] == 2
    off = PS.Shares({"sleeper": (1.0, 1.0)}, enabled=False)
    assert all(off.take("sleeper", "x") for _ in range(10))
    # memory: 20,000 clients in debt -> bounded
    big = PS.Shares({"sleeper": (60.0, 150.0)}, clock=clk, max_clients=5000)
    for i in range(20000):
        big.take("sleeper", f"10.0.{i // 250}.{i % 250}")
    assert len(big.shares["sleeper"].full_at) <= 5000


def test_env_numbers_and_switch(monkeypatch):
    monkeypatch.setenv("LEAGUE_LAB_PROVIDER_SHARE", "30,90")
    monkeypatch.setenv("LEAGUE_LAB_PROVIDER_SHARE_MFL", "6,20")
    s = PS.from_env()
    assert s.enabled and (s.shares["sleeper"].per_minute, s.shares["sleeper"].burst) == (30.0, 90.0)
    assert (s.shares["mfl"].per_minute, s.shares["mfl"].burst) == (6.0, 20.0)
    monkeypatch.setenv("LEAGUE_LAB_PROVIDER_SHARE", "off")
    assert not PS.from_env().enabled
    monkeypatch.setenv("LEAGUE_LAB_PROVIDER_SHARE", "nonsense")
    monkeypatch.delenv("LEAGUE_LAB_PROVIDER_SHARE_MFL")
    s = PS.from_env()
    assert s.enabled and (s.shares["sleeper"].per_minute, s.shares["sleeper"].burst) == PS.DEFAULTS["sleeper"]


def test_a_provider_client_refuses_busy_but_serves_what_it_has():
    from league_lab.sleeper_client import Sleeper, SleeperBusy, TokenBucket
    clk = _Clock()
    PS.reset(PS.Shares({"sleeper": (60.0, 2.0)}, clock=clk))
    try:
        fetched = []
        sl = Sleeper(fetch=lambda path: fetched.append(path) or {"league_id": "1", "name": path},
                     bucket=TokenBucket(1000), clock=clk)
        with PS.acting_for("1.2.3.4"):
            sl.league("1111111111")
            sl.league("2222222222")
            with pytest.raises(SleeperBusy):
                sl.league("3333333333")
            assert sl.league("1111111111")["name"]                 # cached: no call, no refusal
        sl.league("3333333333")                                    # the nightly / a test: no client, no share
        assert len(fetched) == 3
    finally:
        PS.reset()


@pytest.fixture
def limited(monkeypatch):
    """The limiter on (as on the site) with numbers that never refuse these requests themselves, the provider share
    on a fake clock; both put back after."""
    clk = _Clock()
    big = {n: (100000.0, 100000.0) for n in ratelimit.DEFAULTS}
    ratelimit.reset(ratelimit.Limiter(big, coarse={}, global_={}, clock=clk))
    PS.reset(PS.Shares(clock=clk))
    monkeypatch.setenv("LEAGUE_LAB_CPU_SLOTS", "0")
    yield clk
    monkeypatch.setenv("LEAGUE_LAB_RATE_LIMIT", "off")
    ratelimit.reset()
    PS.reset()


def test_one_league_opened_cold_costs_this_many_calls(client):
    _cold()
    sl = A.sleeper()
    before = sl.calls
    codes = _open_league(client, ON_DEMAND)
    assert codes == [200, 200, 200, 200], codes
    n = sl.calls - before
    _cold()
    sl = A.sleeper()
    lg = client.get("/api/leagues?username=andycatmac")
    print(f"one unknown Sleeper league opened cold (My Week, Team, League, outlook): {n} Sleeper calls; "
          f"/api/leagues?username= -> {lg.status_code}, {A.sleeper().calls} calls")
    assert 5 <= n <= PS.DEFAULTS["sleeper"][1] / 3      # three of them fit in the share's first minute


def test_a_person_opening_three_leagues_in_a_minute_is_never_refused(client, limited):
    refused = []
    for _ in range(3):                                   # three unknown leagues (the same fixture, cold each time)
        _cold()
        limited.t += 15.0                                # 15 seconds apart: all three inside one minute
        refused += [c for c in _open_league(client, ON_DEMAND) if c != 200]
    info = PS.shares().info()["sleeper"]
    print(f"three leagues in 45 s: {info['calls']} Sleeper calls on this client's share, refused {info['refused']}")
    assert refused == [] and info["refused"] == 0


def test_a_script_opening_fifty_leagues_is_refused_busy_and_others_are_not(client, limited):
    codes = []
    for _ in range(50):                                  # fifty unknown leagues, 1.2 s apart (one minute in all)
        _cold()
        limited.t += 1.2
        codes += _open_league(client, ON_DEMAND)
    busy = [c for c in codes if c == 503]
    assert set(codes) <= {200, 503} and busy, codes    # refused in the app's busy words, never a 500
    first = codes.index(503) // len(SCREENS)
    print(f"fifty leagues in a minute: refused from league {first + 1}; {len(busy)} of {len(codes)} answers busy; "
          f"share: {PS.shares().info()['sleeper']}")
    r = client.get(SCREENS[0].format(l=ON_DEMAND))
    if r.status_code == 503:
        assert r.json()["error"] == "busy, try again in a minute"
    # another visitor is not refused: its own share
    _cold()
    with PS.acting_for("198.51.100.7"):
        assert A.sleeper().league(ON_DEMAND)["league_id"] == ON_DEMAND


def test_mfl_three_leagues_in_a_minute_are_never_refused(client, limited):
    calls = []
    for _ in range(3):
        _cold()
        limited.t += 15.0
        before = PS.shares().info()["mfl"]["calls"]
        codes = [client.get(p.format(l="mfl:70587")).status_code for p in SCREENS]
        calls.append(PS.shares().info()["mfl"]["calls"] - before)
        assert all(c == 200 for c in codes), codes
    info = PS.shares().info()["mfl"]
    print(f"mfl:70587 opened cold three times in 45 s: MFL calls per opening {calls}, refused {info['refused']}")
    assert info["refused"] == 0
    # all three at once (three tabs): 42 calls, under the 50 at once
    assert sum(calls) <= PS.DEFAULTS["mfl"][1]


@pytest.mark.parametrize("per_league", [25, 35])
def test_the_numbers_hold_for_a_live_league_cost(per_league):
    """Live, an unknown Sleeper league's first build also reads the outlook's remaining weeks (12-20 calls, the PO's
    measurement on 2026-10-06; the fixtures stop at their missing week 3): ~25-35 calls a league. Three in a minute
    pass; fifty are refused from the sixth or so, then about two a minute."""
    clk = _Clock()
    sh = PS.Shares(clock=clk)
    ok3 = True
    for _ in range(3):
        clk.t += 15.0
        ok3 &= all(sh.take("sleeper", "203.0.113.20") for _ in range(per_league))
    assert ok3
    sh = PS.Shares(clock=clk)
    done = 0
    for _ in range(50):
        clk.t += 1.2
        if all(sh.take("sleeper", "203.0.113.21") for _ in range(per_league)):
            done += 1
    print(f"{per_league} calls a league: fifty in a minute -> {done} built in full")
    assert done <= 8


def test_league_setup_threads_spend_the_same_clients_share():
    """``anyleague.user_leagues`` reads each league's rosters and users in a thread pool: the request's client reaches
    those threads (a script cannot dodge its share through league setup)."""
    clk = _Clock()
    _cold()
    PS.reset(PS.Shares({"sleeper": (60.0, 1000.0)}, clock=clk))
    try:
        with PS.acting_for("203.0.113.30"):
            got = A.user_leagues("test_manager", 2026)
        n = PS.shares().info()["sleeper"]["calls"]
        assert got["leagues"] and n >= 2 + 2 * len(got["leagues"]), n
        _cold()
        PS.reset(PS.Shares({"sleeper": (60.0, 3.0)}, clock=clk))
        with PS.acting_for("203.0.113.31"), pytest.raises(A.SleeperBusy):
            A.user_leagues("test_manager", 2026)
    finally:
        PS.reset()


# ------------------------------------------------------------------ fix round, review L3: no pool drops the client
# Every thread pool or thread the code starts: it carries the request's client (``contextvars.copy_context``), or it
# is listed here with why it does not need to. A new pool on a request path that is neither fails the test.
NEEDS_NO_CLIENT = {
    ("api/league_lab_api/events.py", "_start"): "the event store's writer thread: database writes, no provider call",
    ("api/league_lab_api/usage.py", "submit"): "the usage counts' writer thread: database writes, no provider call",
    ("api/league_lab_api/outlook_store.py", "offer"): "the outlook snapshots' writer thread: database writes only",
    ("api/league_lab_api/news.py", "recent"): "ESPN's player news: its own bucket (NF.feed), not Sleeper / MFL",
    ("src/league_lab/injury_feed.py", "snapshot"): "the injury feed's background refresh: one copy for everyone, ESPN",
}


def _pools() -> list[tuple[str, str, bool]]:
    import ast

    from league_lab_api.settings import ROOT
    out = []
    for rel in ("api/league_lab_api", "src/league_lab"):
        for f in sorted((ROOT / rel).glob("*.py")):
            text = f.read_text()
            for fn in ast.walk(ast.parse(text)):
                if isinstance(fn, ast.FunctionDef | ast.AsyncFunctionDef):
                    seg = ast.get_source_segment(text, fn) or ""
                    if "ThreadPoolExecutor(" in seg or "threading.Thread(" in seg:
                        out.append((f"{rel}/{f.name}", fn.name, "copy_context" in seg))
    return out


def test_every_pool_carries_the_client_or_says_why_not():
    pools = _pools()
    for path, fn, carries in pools:
        print(f"{path}:{fn}: {'carries the client' if carries else NEEDS_NO_CLIENT.get((path, fn), 'DROPS IT')}")
    assert {(p, f) for p, f, c in pools if c} >= {("api/league_lab_api/availability.py", "contexts"),
                                                  ("src/league_lab/anyleague.py", "user_leagues")}
    dropped = [(p, f) for p, f, c in pools if not c and (p, f) not in NEEDS_NO_CLIENT]
    assert dropped == [], f"a thread pool that drops the request's client: {dropped}"


def test_the_roster_contexts_pool_carries_the_client(monkeypatch):
    """Review L3: ``availability.contexts`` (reached from decisions through ``A.lineup_rows``) read rosters in a pool
    whose threads saw no client — their Sleeper calls were charged to the global bucket only."""
    import threading

    from league_lab_api import availability as AV
    seen = []

    def fake(league_id, rid, week=None, house=None):
        seen.append((PS.CLIENT.get(), threading.get_ident()))
        return None
    monkeypatch.setattr(AV, "roster_context", fake)
    with PS.acting_for("203.0.113.40"):
        AV.contexts("9000000000000000001", [1, 2, 3, 4, 5, 6], workers=4)
    assert len(seen) == 6 and {c for c, _ in seen} == {"203.0.113.40"}
    assert len({t for _, t in seen}) >= 1
    seen.clear()
    AV.contexts("9000000000000000001", [1, 2, 3])                   # no client (the nightly, a test): none in the threads
    assert {c for c, _ in seen} == {None}


def test_starlettes_threadpool_carries_the_client():
    """A sync route and ``run_in_threadpool`` (DFS, the blog editor) run in Starlette's threadpool: anyio copies the
    context, so the client set by the limiter's middleware is there."""
    import asyncio

    from starlette.concurrency import run_in_threadpool

    async def go():
        with PS.acting_for("203.0.113.41"):
            return await run_in_threadpool(PS.CLIENT.get)
    assert asyncio.run(go()) == "203.0.113.41"
