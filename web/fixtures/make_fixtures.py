"""Build web/fixtures/*.json: one file per API response the web app's fixture tests serve (plan F2, Wave F).

    # an API on the clone (no Sleeper: the house leagues come from the database) + Postgres reachable as postgres
    (cd api && uv run uvicorn league_lab_api.main:app --port 8681) &
    PGPASSWORD=… python3 web/fixtures/make_fixtures.py            # API=http://localhost:8681 DB=league_lab_f2

Three kinds of file (web/fixtures/README.md lists them):
* SAVED from today's API (routes that exist): /api/leagues, rosters, My Week (dynasty roster 12, Scrubs roster 2,
  week 4), the player cards of both lineups, search, status. The contract's new My Week fields are added on top:
  `source: "database"` and the `opponent` object (the clone has no week-4 matchups, so the opponent is picked
  by hand: dynasty 12 vs roster 11, Scrubs 2 vs roster 1, `lineup_value` = that roster's week-4 starters in
  ops.lineups); the player cards get `ros` (from the mart) and `missing: []`.
* FROM THE MARTS in the contract's shape (routes F3 builds): /api/ros per position (mart_player_ros_projection +
  the owner from mart_player_availability), /api/record (the clone's record is empty: Scrubs is saved as the real
  empty answer; the dynasty's three scored weeks are HAND-WRITTEN so the table has rows).
* HAND-WRITTEN: /api/leagues?username= (a fictional Sleeper user "fixture_user" with the two house leagues and the
  fictional "Test League" 9000000000000000001, and "fixture_commish" who has no team in it), the errors, and the
  whole Test League: 10 made-up teams, a made-up roster for team 3 built from real players (their week-4
  projections and ranges in Scrubs scoring), My Week, the player cards (`missing: ["value"]`), rest of season,
  and `available: false` for the record — the "any league" path with no database behind it.
"""

from __future__ import annotations

import copy
import json
import os
import subprocess
import urllib.request
from pathlib import Path

API = os.environ.get("API", "http://localhost:8681")
DB = os.environ.get("DB", "league_lab_f2")
OUT = Path(__file__).resolve().parent
DYN, SCRUBS, TEST = "1321941740235550720", "1389709692405551104", "9000000000000000001"
WEEK, SEASON = 4, 2026


def api(path: str):
    with urllib.request.urlopen(API + path) as r:
        return json.load(r)


def sql(q: str):
    out = subprocess.run(["psql", "-U", "postgres", "-h", "localhost", "-d", DB, "-At", "-c", f"select coalesce(json_agg(t), '[]') from ({q}) t"],
                         check=True, capture_output=True, text=True).stdout
    return json.loads(out)


def save(name: str, data) -> None:
    p = OUT / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")


def ros_row(league: str, gsis: str):
    r = sql(f"""select ros_points, ros_games, ros_p10, ros_p90, ros_rank_pos, playoff_points, from_week, last_week
               from analytics.mart_player_ros_projection where league_id = '{league}' and gsis_id = '{gsis}'""")
    if not r:
        return None
    r = r[0]
    return {"points": r["ros_points"], "games": r["ros_games"], "p10": r["ros_p10"], "p90": r["ros_p90"], "pos_rank": r["ros_rank_pos"],
            "playoff_points": r["playoff_points"], "from_week": r["from_week"], "last_week": r["last_week"]}


def lineup_value(league: str, roster: int) -> float:
    r = sql(f"""select round(sum(value)::numeric, 2) as v from ops.lineups
               where league_id = '{league}' and season = {SEASON} and week = {WEEK} and roster_id = {roster} and role = 'starter'
                 and run_at = (select max(run_at) from ops.lineups where league_id = '{league}' and season = {SEASON} and week = {WEEK})""")
    return float(r[0]["v"])


# ------------------------------------------------------------------ saved from the API (+ the contract's new fields)
house = api("/api/leagues")
save("leagues.json", house)
save("status.json", api("/api/status"))
rosters = {lg: api(f"/api/leagues/{lg}/rosters") for lg in (DYN, SCRUBS)}
for lg, rs in rosters.items():
    save(f"rosters_{lg}.json", rs)

OPP = {DYN: (12, 11), SCRUBS: (2, 1)}
players: dict[str, set[str]] = {DYN: set(), SCRUBS: {"00-0038824"}}          # + a free agent the old spec opens
for lg, (me, them) in OPP.items():
    mw = api(f"/api/my-week?league={lg}&team={me}")
    o = next(r for r in rosters[lg] if r["roster_id"] == them)
    mw["opponent"] = {"roster_id": them, "team_name": o["team_name"], "manager": o["manager_name"], "lineup_value": lineup_value(lg, them)}
    mw["source"] = "database"
    save(f"my-week_{lg}_{me}.json", mw)
    for row in mw["lineup"] + mw["lineup_full"]:
        if row["gsis_id"] and row["role"] != "unplayable":
            players[lg].add(row["gsis_id"])
    for c in mw["cards"]:
        players[lg].update(x for x in (c["gsis_id"], c["alt_gsis_id"]) if x)
for lg, ids in players.items():
    for g in sorted(ids):
        card = api(f"/api/player/{g}?league={lg}")
        card["ros"] = ros_row(lg, g)
        card["missing"] = []
        save(f"player/{lg}_{g}.json", card)
save(f"search_{DYN}.json", api(f"/api/search?league={DYN}&q=st%20brown"))


# ------------------------------------------------------------------ rest of season, from the mart in the contract's shape
def ros_list(league: str, position: str, owners: dict[str, tuple[int, str]] | None = None, limit: int = 50) -> dict:
    where = "" if position == "ALL" else f"and r.position = '{position}'"
    rank = "ros_rank_all" if position == "ALL" else "ros_rank_pos"
    src = SCRUBS if league == TEST else league
    rows = sql(f"""select r.gsis_id, r.player_key, r.player_name, r.position, r.team, r.ros_points, r.ros_games, r.playoff_points,
                          r.ros_p10 as p10, r.ros_p90 as p90, r.ros_rank_pos as pos_rank, r.{rank} as rank_here,
                          a.rostered_by_roster_id, a.rostered_by_team, r.from_week, r.last_week
                   from analytics.mart_player_ros_projection r
                   left join analytics.mart_player_availability a on a.league_id = r.league_id and coalesce(a.gsis_id, a.sleeper_id) = r.player_key
                   where r.league_id = '{src}' {where} and r.{rank} is not null order by r.{rank} limit {limit}""")
    out = []
    for r in rows:
        if owners is not None:                       # the Test League: its own (made-up) owners
            hit = owners.get(r["player_key"])
            r["rostered_by_roster_id"], r["rostered_by_team"] = hit if hit else (None, None)
        out.append({k: r[k] for k in ("gsis_id", "player_name", "position", "team", "ros_points", "ros_games", "playoff_points",
                                       "p10", "p90", "pos_rank", "rostered_by_roster_id", "rostered_by_team")})
    fw = rows[0]["from_week"] if rows else None
    lw = rows[0]["last_week"] if rows else None
    return {"league_id": league, "from_week": fw, "last_week": lw, "players": out}


for lg, poss in ((DYN, ("QB", "RB", "WR", "TE", "ALL")), (SCRUBS, ("QB", "RB", "WR", "TE", "K", "DEF", "ALL"))):
    for pos in poss:
        save(f"ros_{lg}_{pos}.json", ros_list(lg, pos))

# ------------------------------------------------------------------ our record
save(f"record_{SCRUBS}.json", {"league_id": SCRUBS, "from_week": None, "weeks": [], "summary": None})   # the clone's real answer: nothing yet


def rec(week, position, status, **kw):
    base = {"league_id": DYN, "league_name": "Forever Unclean Dynasty", "season": SEASON, "scope": "week", "week": week, "first_week": 1,
            "weeks_scored": None, "position": position, "status": status, "top_n": None, "n_both": None, "n_players": None,
            "ours_spearman": None, "sleeper_spearman": None, "ours_mae": None, "sleeper_mae": None, "ours_hit_rate": None,
            "sleeper_hit_rate": None, "pairs_listed": None, "pairs_n": None, "pairs_ours_right": None, "pairs_sleeper_right": None,
            "pairs_both_right": None, "pairs_neither_right": None, "pairs_disagree": None, "pairs_ours_right_disagree": None,
            "pairs_push": None, "pairs_no_sleeper": None}
    base.update(kw)
    return base


weeks = []
for w, (pn, po, ps, pb, pd, pod, mae_o, mae_s) in {1: (36, 21, 19, 17, 6, 4, 5.84, 6.02), 2: (36, 20, 21, 18, 5, 2, 6.31, 6.27),
                                                   3: (35, 22, 18, 16, 8, 6, 5.97, 6.18)}.items():
    weeks.append(rec(w, "ALL", "scored", n_both=212, pairs_listed=36, pairs_n=pn, pairs_ours_right=po, pairs_sleeper_right=ps,
                     pairs_both_right=pb, pairs_neither_right=pn - po - ps + pb, pairs_disagree=pd, pairs_ours_right_disagree=pod,
                     ours_mae=mae_o, sleeper_mae=mae_s))
    for i, (pos, top) in enumerate((("QB", 12), ("RB", 24), ("WR", 36), ("TE", 12))):
        weeks.append(rec(w, pos, "scored", top_n=top, n_players=(32, 58, 84, 38)[i], ours_mae=round(mae_o + (0.9, 0.2, -0.3, -1.1)[i], 2),
                         sleeper_mae=round(mae_s + (0.7, 0.4, -0.2, -1.0)[i], 2), ours_spearman=(0.52, 0.48, 0.44, 0.39)[i] + 0.01 * w,
                         sleeper_spearman=(0.50, 0.49, 0.41, 0.40)[i] + 0.01 * w, ours_hit_rate=(0.67, 0.58, 0.56, 0.5)[i],
                         sleeper_hit_rate=(0.58, 0.58, 0.53, 0.5)[i]))
weeks.append(rec(4, "ALL", "in_play", n_both=214, pairs_listed=36))
summary = rec(None, "ALL", "scored", scope="season", weeks_scored=3, n_both=636, pairs_listed=108, pairs_n=107, pairs_ours_right=63,
              pairs_sleeper_right=58, pairs_both_right=51, pairs_neither_right=37, pairs_disagree=19, pairs_ours_right_disagree=12,
              ours_mae=6.04, sleeper_mae=6.16)
save(f"record_{DYN}.json", {"league_id": DYN, "from_week": 1, "weeks": weeks, "summary": summary})
save(f"record_{TEST}.json", {"available": False, "why": "the record is kept for the leagues the nightly scores"})

# ------------------------------------------------------------------ the fictional Test League (no database behind it)
TEAMS = ["Bench Mob", "Waiver Wire Warriors", "Fixture Falcons", "Kickoff Kings", "Practice Squad", "Two-Point Tries",
         "Goal Line Stand", "Hail Marys", "Red Zone Regulars", "Fourth and Long"]
MANAGERS = ["benchmob", "wwwarriors", "fixture_user", "kickoffkings", "psquad", "twopoint", "goalline", "hailmary", "redzone", "fourthlong"]
test_rosters = [{"roster_id": i + 1, "team_name": t, "manager_name": MANAGERS[i]} for i, t in enumerate(TEAMS)]
save(f"rosters_{TEST}.json", sorted(test_rosters, key=lambda r: r["team_name"]))
ME, THEM = 3, 8
LABEL = "10-team redraft · half PPR · 4‑pt pass TD"
user = {"user_id": "900000000000000003", "username": "fixture_user", "display_name": "Fixture User", "avatar": None}
by_name = {lg["league_id"]: lg for lg in house}
save("leagues_user_fixture_user.json", {"user": user, "season": SEASON, "leagues": sorted([
    {"league_id": DYN, "name": by_name[DYN]["league_name"], "season": SEASON, "total_rosters": 12, "scoring_label": by_name[DYN]["scoring_label"],
     "roster_id": 12, "team_name": "Shake & Bake", "status": "in_season", "in_database": True},
    {"league_id": SCRUBS, "name": by_name[SCRUBS]["league_name"], "season": SEASON, "total_rosters": 10, "scoring_label": by_name[SCRUBS]["scoring_label"],
     "roster_id": 2, "team_name": "MacZaddy", "status": "in_season", "in_database": True},
    {"league_id": TEST, "name": "Test League", "season": SEASON, "total_rosters": 10, "scoring_label": LABEL,
     "roster_id": ME, "team_name": "Fixture Falcons", "status": "in_season", "in_database": False},
], key=lambda x: x["name"])})
save("leagues_user_fixture_commish.json", {"user": {"user_id": "900000000000000099", "username": "fixture_commish", "display_name": "Fixture Commish",
                                                      "avatar": None}, "season": SEASON, "leagues": [
    {"league_id": TEST, "name": "Test League", "season": SEASON, "total_rosters": 10, "scoring_label": LABEL,
     "roster_id": None, "team_name": None, "status": "in_season", "in_database": False}]})
save("error_no_user.json", {"error": "no such Sleeper user"})
save("error_sleeper_down.json", {"error": "Sleeper did not answer"})
save("error_not_ready.json", {"error": "the numbers are not ready yet"})

# the made-up roster: real players (their week-4 projection and ranges in Scrubs scoring, which the Test League copies)
SLOTS = [("QB", "00-0034857"), ("RB1", "00-0039139"), ("RB2", "00-0032764"), ("WR1", "00-0038543"), ("WR2", "00-0036554"),
         ("TE", "00-0037744"), ("FLEX", "00-0036358"), ("K", "00-0036854")]
BENCH = ["00-0037834", "00-0038120", "00-0039064", "00-0038933"]
ids = [g for _, g in SLOTS] + BENCH
proj = {r["gsis_id"]: r for r in sql(f"""select p.gsis_id, p.player_name, p.position, p.proj_points, p.p10, p.p25, p.p75, p.p90, p.opponent, p.opp_rank_std
                                          from analytics.mart_player_week_projections p
                                          where p.league_id = '{SCRUBS}' and p.season = {SEASON} and p.week = {WEEK}
                                            and p.gsis_id in ({",".join(f"'{g}'" for g in ids)})""")}
kick = sql(f"select player_name, value from ops.lineups where league_id = '{SCRUBS}' and week = {WEEK} and gsis_id = '00-0036854' limit 1")
if "00-0036854" not in proj:
    proj["00-0036854"] = {"gsis_id": "00-0036854", "player_name": "Evan McPherson", "position": "K",
                          "proj_points": kick[0]["value"] if kick else 8.4, "opponent": None, "opp_rank_std": None}


def v(g):
    return round(float(proj[g]["proj_points"]), 2)


starters = [{"role": "starter", "slot": s if s not in ("RB1", "RB2", "WR1", "WR2") else s, "player_name": proj[g]["player_name"], "gsis_id": g,
             "position": proj[g]["position"], "value": v(g), "margin": None, "flag": ""} for s, g in SLOTS]
starters.append({"role": "starter", "slot": "DEF", "player_name": "Pittsburgh Steelers", "gsis_id": None, "position": "DEF", "value": 7.1,
                 "margin": None, "flag": ""})
best_bench = {"QB": "00-0037834", "RB": "00-0038120", "WR": "00-0038120", "TE": "00-0038933"}   # FLEX: Hall beats Flowers
for row in starters:
    alt = best_bench.get(row["position"])
    row["margin"] = round(row["value"] - v(alt), 2) if alt and row["value"] is not None and row["value"] > v(alt) else (row["value"] if row["position"] in ("K", "DEF") else 0.0)
bench = [{"role": "bench", "slot": f"Bench {i + 1}", "player_name": proj[g]["player_name"], "gsis_id": g, "position": proj[g]["position"],
          "value": v(g), "margin": None, "flag": ""} for i, g in enumerate(sorted(BENCH, key=v, reverse=True))]
total = round(sum(r["value"] for r in starters), 2)


def card(slot, slot_label, a, b, pct, word):
    pa, pb = proj[a], proj[b]
    lo = lambda p, x, y: f"{float(p[x]):.0f}–{float(p[y]):.0f}"  # noqa: E731
    vs = lambda p: f"{p['player_name']} vs {p['opponent']} (#{p['opp_rank_std']} vs {p['position']})" if p.get("opponent") else p["player_name"]  # noqa: E731
    return {"slot": slot, "slot_label": slot_label, "gsis_id": a, "player_name": pa["player_name"], "value": v(a), "alt_gsis_id": b,
            "alt_name": pb["player_name"], "alt_value": v(b), "margin": round(v(a) - v(b), 2), "verdict": word, "how": "bench",
            "p_win": pct / 100, "blocks": [
                {"kind": "markdown", "text": f"**{slot_label}: start [{pa['player_name']}](/player/{a}) over [{pb['player_name']}](/player/{b})**"},
                {"kind": "markdown", "text": f"**{pa['player_name']} outscores {pb['player_name']} {pct}% of the time — {word}.**"},
                {"kind": "markdown", "text": f"{v(a):.2f} vs {v(b):.2f} projected: {v(a) - v(b):.2f} apart."},
                {"kind": "caption", "text": f"Most weeks: {pa['player_name']} {lo(pa, 'p25', 'p75')}, {pb['player_name']} {lo(pb, 'p25', 'p75')}.  \n"
                                            f"A bad week to a good week: {pa['player_name']} {lo(pa, 'p10', 'p90')}, {pb['player_name']} {lo(pb, 'p10', 'p90')}.  \n"
                                            f"{vs(pa)} · {vs(pb)}"}]}


dyn_mw = json.loads((OUT / f"my-week_{SCRUBS}_2.json").read_text())
cards = sorted([card("FLEX", "FLEX", "00-0036358", "00-0038120", 54, "a coin flip"),
                card("RB2", "RB2", "00-0032764", "00-0038120", 61, "a lean"),
                card("TE", "TE", "00-0037744", "00-0038933", 72, "clear")], key=lambda c: c["p_win"])
test_mw = {
    "league_id": TEST, "league_name": "Test League", "season": SEASON, "scoring_label": LABEL, "roster_id": ME, "team_name": "Fixture Falcons",
    "manager_name": "fixture_user", "week": WEEK, "record": {"wins": 2, "losses": 1, "standing": 3},
    "opponent": {"roster_id": THEM, "team_name": TEAMS[THEM - 1], "manager": MANAGERS[THEM - 1], "lineup_value": 108.4},
    "source": "sleeper", "summary": "**Fixture Falcons** · 2-1, #3 in the league",
    "league_line": f"Your best lineup projects **{total:.2f}** in week {WEEK}.", "lineup_value": total, "cards": cards, "notice": None,
    "lineup": starters, "lineup_full": starters + bench, "howto": dyn_mw["howto"], "movers": [],
}
save(f"my-week_{TEST}_{ME}.json", test_mw)

owners = {g: (ME, "Fixture Falcons") for g in ids}
for pos in ("QB", "RB", "WR", "TE", "K", "DEF", "ALL"):
    save(f"ros_{TEST}_{pos}.json", ros_list(TEST, pos, owners))

# the Test League's player cards: the Scrubs card of the same player, retold for this league (on-demand: owner from the
# made-up rosters, no Value section — "missing" says so)
for g in ids:
    src = api(f"/api/player/{g}?league={SCRUBS}")
    c = json.loads(json.dumps(src).replace("League of Scrubs", "Test League"))
    c = copy.deepcopy(c)
    c["league_id"], c["league_name"] = TEST, "Test League"
    c["rostered_by_roster_id"], c["is_free_agent"] = ME, False
    pos = c["position"]
    c["header"] = f"{pos} · {c['team'] or 'no NFL team'} · on **Fixture Falcons** (fixture_user)"
    c["sections"]["availability"]["blocks"] = [{"kind": "markdown", "text": "Rostered by **Fixture Falcons** (fixture_user).  \n"
                                                + "  \n".join(b["text"].split("  \n", 1)[1] for b in src["sections"]["availability"]["blocks"][:1]
                                                              if "  \n" in b["text"])}]
    del c["sections"]["value"]
    c["missing"] = ["value"]
    c["ros"] = ros_row(SCRUBS, g)
    save(f"player/{TEST}_{g}.json", c)
print("fixtures:", len(list(OUT.rglob("*.json"))), "files in", OUT)
