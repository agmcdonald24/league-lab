# IR-1 — nobody who cannot play is ranked, valued or projected (Wave I-R, 2026-10-08)

Branch `dev/IR1` (from `main` `3dfa01d`), worktree `/home/claude/wt-iq4`, database `league_lab_iq4` (2026 week 5, merged
v3.6 board, Sleeper directory copy of 2026-10-05 12:00 UTC). Plan § Wave I-R, METRICS § "Who cannot play" (av1.0),
WORDS § "Who cannot play".

## The definition and which source wins (`src/league_lab/availability_gate.py`)

* **cannot_play** (this week): IR, PUP, NFI, suspended, Out, no NFL team (released / retired / unsigned).
  **out_indefinitely**: IR, PUP, NFI, suspended. **Doubtful**: flagged, never removed. **Questionable**: untouched.
* Sources: Sleeper's directory (`injury_status` first, else a reserve list its `status` names, else no team; dated by
  `news_updated`) and ESPN's injuries feed (API only). **The freshest dated word wins** (ESPN first on an equal time; an
  undated word loses). A game status (Out / Doubtful / Questionable) dated before the previous week's last kickoff is
  last week's and rules nothing — this is why the 207 "Out" entries in this database's Monday-morning Sleeper copy rule
  nobody out of week 5. nflverse's weekly injury report is never a source; nflverse's weekly roster status (`RES`,
  `SUS`) is the fallback only when there is no Sleeper copy at all.
* One divergence kept on purpose: My Week's lineup solver still sits a Doubtful player (`availability.CANNOT_PLAY`,
  the lineup policy since Wave I-0); every list now flags him instead.

## `project` (the stored board)

Before anything is written, for the live week (first REG week whose first game has not kicked off; today week 5):
a player who cannot play keeps his row with **every number 0** and `availability` = the reason as JSON (new nullable
column on `ops.projections` and `ops.projection_lines`, created by `db migrate` and the writers' DDL); a player out
indefinitely has **no row in any later week**. Why 0 and not "no row" this week: he scores 0 if he does not play (a
known 0), so lineups, waiver gains, a trade's week and the outlook sum the same rows; a missing row is "no value yet"
and `lineup.solve` could seat him as a filler. Frozen weeks are never touched (B5).
The copy is `raw.sleeper_player` (the nightly's fetch, upserted; a failed fetch leaves the last good copy, the replay
step's archive copy on a fresh database) — `project` prints `availability gate, week 5: Sleeper directory copy of
2026-10-05T12:00:39Z; 79 players who cannot play get 0 this week, 79 of them out indefinitely (no later weeks)`. No copy
at all: the week's NFL roster file decides and the line says FALLBACK (tested) — never "everyone is healthy".

## Every route, at request time (`availability.statuses`: the stored record + the overlay's Sleeper and ESPN words)

Rankings week (not ranked, not tiered, "Not playing" with status, source, time and the reason; FLEX the same; the
search filters it; cache key carries the set) · Rankings season (out indefinitely) · "Who should I start?" ("Achane is
out — on injured reserve (IR (knee - acl) · Sleeper, Sep 28). Start Judkins."; with 3–4 picks the call is among the
others) · `/api/ros` every view (`ondemand.ros` → `availability.ros_gate`) · the free calculator (no value, "Not
priced: …", out-this-week's outlook withheld) · Compare (`research._compare_gate`) · DFS (`dfs._statuses` reads the one
definition) · the matchup board (`matchup_board.gate_week`; the home's top projections and matchups read it) · the
player card's rest-of-season line. With the overlay off the stored record still applies (tested; run on week 5 below).

## Inventory (surface → knew before? → knows now? → source, freshness)

| Surface / table | Before | Now | Source |
|---|---|---|---|
| `ops.projections`, `ops.projection_lines`, `ops.projection_ranges` (`project`) | no (Achane 11.42 wk 5, 126.9 ROS) | yes: 0 + reason this week, no later weeks | Sleeper copy the nightly loaded (daily) |
| `mart_player_week_projections` (house) | `report_status` / `roster_status` (nflverse; `RES` only in `is_rankable`) | inherits the 0 | stored |
| `mart_player_ros_projection` (house) | unranked if `roster_status` ≠ ACT, total kept (Achane 126.9) | 0.0 over 1 game, unranked; `/api/ros` lists him with the reason | stored + request time |
| My Week / `roster_context` / ops.lineups | yes (overlay; lineup.py RES / Out / Doubtful) | unchanged + stored 0 | overlay (ESPN 15 min game days; Sleeper cached a day) |
| Waivers | this week (overlay drops claims); later weeks healthy | later weeks from the stored board (0 / none) | overlay + stored (nightly) |
| Trades' lists / partner search / trade board | this week (`horizon_overlay`); later weeks healthy | later weeks from the stored board | overlay + stored (nightly) |
| League outlook roster values | no | from the stored board (nightly) | stored |
| `/api/rankings` week | no (Achane #21 RB) | yes | statuses (record + Sleeper + ESPN) |
| `/api/rankings` season | house: `is_ranked`; ref: no | yes (out indefinitely) | statuses |
| `/api/rankings/start` | no | "He is out", no call on him | statuses |
| `/api/ros` (all views) | label only | removed, `not_playing` | statuses |
| `/api/trade-calc/free` | no | refuses to price | statuses |
| `/api/compare` | label only | no number, the reason, "He is out" | statuses |
| `/api/dfs/projections`, slate | overlay (its own def: Doubtful / Inactive out) + nflverse report | the one definition | statuses |
| `/api/matchups/board` (+ home top projections, home matchups) | no | yes, `not_playing` | statuses |
| Player card | status line (overlay) | + ROS withheld for out indefinitely | statuses |
| Stats | no projection column | — | — |
| `league-lab audit-lists` | nflverse report + roster status | the same definition and sources, first rule | Sleeper copy + record |

**Readers that treat `mart_player_availability.injury_status` (nflverse's newest report row: midweek, last week's) as
current** — not changed (not mine, flagged for the PO): `src/league_lab/trades.py:112` (free-agent replacement level),
`api/league_lab_api/decisions.py:243` (Waiver Wire free-agent browse), `src/league_lab/anyleague.py:1602` (on-demand
waivers' NFL status), `src/league_lab/waivers.py:639,1135` (the nightly's free-agent filter), `signals.py:909`,
`reports.py:226-302`, `ondemand.py:586,693`, `player.py:338` (the card's injury line), `mart_player_role_alerts.sql`
(the fingerprints in `waivers.py:559` / `mart_waiver_moves.sql:47` are cache keys only).

## The audit (`src/league_lab/audit.py`) and the stored check

First lines of `logs/list_audit.md` on `league_lab_iq4` after the gated `project`:

```
## Players who cannot play and are still ranked or valued: 0
_Who cannot play: 236 players by Sleeper's directory (copy of 2026-10-05T12:00:39.609393Z) and last night's stored record, freshest first (league_lab.availability_gate)._
- None: every player who cannot play is out of this week's lists, and every player out indefinitely out of the season lists and the calculator's values.
```

(236 = every directory entry who cannot play, free agents without a team included; 79 of them were on the board.)
`dbt/tests/assert_nobody_who_cannot_play_is_projected.sql`: the stored board (live week and later) against the
directory's reserve lists. Severity by var (warn inside the builds — the full build runs before `project` on last
night's board). Before the position fix it **warned 26 rows** (Scott Matlock, Sleeper position "DT", on IR, an RB on the
board): the gate now reads every Sleeper position. After: PASS; with `availability_gate_severity: error`: PASS.

### The PO's lines for `scripts/nightly.sh` (after `hard projection-marts …`, before `audit-lists`)

```bash
# ---- IR-1 (Wave I-R): nobody who cannot play is projected — a hard stop (the stored board against Sleeper's directory)
hard availability-gate dbt_step availability-gate test --select assert_nobody_who_cannot_play_is_projected --vars '{availability_gate_severity: error}'
```

### What the first nightly does differently

`db migrate` adds `ops.projections.availability` (and the `project` DDL adds `ops.projection_lines.availability`);
the full `dbt build` runs the new test as a warning on the restored board; `project` prints the gate line and writes
the live week's 0s with reasons and drops the later weeks of players out indefinitely (79 on this copy); the waiver,
lineup and trade tables solved inside `project` read those rows; the projection marts carry them; the audit's first
section is the new rule. Nothing else moves (frozen weeks: 0 cells changed).

**Week 5 freezes at 20:15 ET tonight and the nightly runs tomorrow at 07:37 ET.** The API (deploy) gates every
screen at request time from the overlay as soon as it is live; the stored week-5 record is only clean if a `project`
with this branch runs before 20:15 (a dispatched nightly). Otherwise week 5's frozen rows keep last night's numbers
(Achane 11.42) and the stored record has no `availability` for week 5 (the screens still gate through the overlay).

## Evidence (`league_lab_iq4`, `project` + the nightly's projection-marts selection)

* `project`: EXIT 0, 79 players gated; projection marts + guards: `PASS=144 WARN=0 ERROR=0` (incl.
  `assert_rest_of_season_follows_the_market_week`, `assert_house_projections_are_the_nfl_wide_rows`,
  `assert_projection_ranges_price_the_lines`, the new check).
* Frozen weeks 1–4: `ops.projections` 4,856 rows, `ops.projection_lines` 2,396, `ops.projection_ranges` 11,980 —
  identical before / after, **0 cells changed**.
* **De'Von Achane (gsis 00-0039040) is on IR in this database's snapshot**: Sleeper id 9226, `injury_status` IR,
  `status` Inactive, body part "Knee - ACL", `news_updated` 2026-09-28 (nflverse roster status week 5: RES).
  Before: Half PPR week 5 **11.42, #21 RB** (Andrew's 21st); ROS (League of Scrubs mart) 126.9 over 11 games,
  unranked. After: week 5 **0.00** (reason recorded), no later week; Rankings: not ranked, "Not playing"; ROS:
  listed, no number; "Who should I start?": "Achane is out — on injured reserve (IR (knee - acl) · Sleeper, Sep 28).
  Start Judkins."; free calculator: "Not priced: De'Von Achane — On injured reserve: no return date, so no
  rest-of-season value. (IR (knee - acl) · Sleeper, Sep 28). …"
* With the overlay off (`LEAGUE_LAB_AVAILABILITY=off`, the stored record alone), the API code on week 5: RB 110
  ranked / 14 tiers / 23 not playing; WR 170 / 33; TE 116 / 19; QB 83 / 4 (the tables below).

| Player | Pos | Status (source, date) | Wk 5 before | Wk 5 after | ROS before (games, rank) | ROS after (mart) |
|---|---|---|---|---|---|---|
| De'Von Achane | RB | IR (knee - acl) · Sleeper, Sep 28 | 11.42 | 0.00 | 126.9 (11, unranked) | 0.0 (1, unranked) |
| Travis Etienne | RB | IR (hamstring) · Sleeper, Oct 1 | 10.34 | 0.00 | 116.9 (11, unranked) | 0.0 (1, unranked) |
| Jordan Mason | RB | IR (thumb) · Sleeper, Oct 3 | 9.24 | 0.00 | 99.2 (11, unranked) | 0.0 (1, unranked) |
| Jadarian Price | RB | IR (chest) · Sleeper, Oct 4 | 8.59 | 0.00 | 89.9 (11, unranked) | 0.0 (1, unranked) |
| Alec Pierce | WR | IR (heel) · Sleeper, Oct 2 | 7.60 | 0.00 | 84.0 (11, unranked) | 0.0 (1, unranked) |
| James Conner | RB | IR (foot) · Sleeper, Oct 2 | 7.52 | 0.00 | 76.9 (11, unranked) | 0.0 (1, unranked) |
| Jaxson Dart | QB | IR (knee - meniscus) · Sleeper, Sep 30 | 7.24 | 0.00 | 91.5 (11, unranked) | 0.0 (1, unranked) |
| Jordyn Tyson | WR | IR (hamstring) · Sleeper, Oct 3 | 7.01 | 0.00 | 77.2 (11, unranked) | 0.0 (1, unranked) |
| Ricky Pearsall | WR | IR (knee - pcl) · Sleeper, Oct 3 | 6.69 | 0.00 | 73.1 (11, unranked) | 0.0 (1, unranked) |
| Trey Benson | RB | IR (knee) · Sleeper, Aug 25 | 6.67 | 0.00 | 68.6 (11, unranked) | 0.0 (1, unranked) |
| A.J. Brown | WR | IR (ankle) · Sleeper, Oct 4 | 6.57 | 0.00 | 84.3 (11, unranked) | 0.0 (1, unranked) |
| Zach Charbonnet | RB | PUP (knee - acl) · Sleeper, Oct 2 | 6.24 | 0.00 | 66.7 (11, unranked) | 0.0 (1, unranked) |
| Demarcus Robinson | WR | IR (ankle) · Sleeper, Sep 26 | 6.21 | 0.00 | 70.5 (11, unranked) | 0.0 (1, unranked) |
| Jonah Coleman | RB | IR (ankle) · Sleeper, Sep 26 | 6.13 | 0.00 | 66.4 (11, unranked) | 0.0 (1, unranked) |
| Isiah Pacheco | RB | IR (back) · Sleeper, Sep 14 | 5.75 | 0.00 | 60.4 (11, unranked) | 0.0 (1, unranked) |
| Dylan Sampson | RB | IR (knee) · Sleeper, Sep 15 | 5.48 | 0.00 | 57.5 (11, unranked) | 0.0 (1, unranked) |
| Terrance Ferguson | TE | IR (ankle) · Sleeper, Oct 2 | 5.42 | 0.00 | 55.3 (11, unranked) | 0.0 (1, unranked) |
| Jack Bech | WR | IR (forearm) · Sleeper, Sep 30 | 5.40 | 0.00 | 57.8 (11, unranked) | 0.0 (1, unranked) |
| David Njoku | TE | IR (lower leg) · Sleeper, Sep 23 | 5.28 | 0.00 | 58.5 (11, unranked) | 0.0 (1, unranked) |
| Chris Collier | RB | IR (undisclosed) · Sleeper, Aug 2 | 5.17 | 0.00 | 56.0 (11, unranked) | 0.0 (1, unranked) |
| Isaac Guerendo | RB | PUP (pectoral) · Sleeper, Aug 30 | 5.01 | 0.00 | 54.9 (11, unranked) | 0.0 (1, unranked) |
| Ronnie Rivers | RB | IR (calf) · Sleeper, Sep 23 | 4.84 | 0.00 | 51.3 (11, unranked) | 0.0 (1, unranked) |
| Tank Dell | WR | IR (knee - acl + mcl) · Sleeper, Sep 9 | 4.78 | 0.00 | 53.8 (11, unranked) | 0.0 (1, unranked) |
| Johnny Wilson | WR | IR (knee) · Sleeper, Aug 22 | 4.73 | 0.00 | 52.0 (11, unranked) | 0.0 (1, unranked) |
| Jayden Higgins | WR | IR (knee - acl) · Sleeper, Aug 21 | 4.53 | 0.00 | 51.5 (11, unranked) | 0.0 (1, unranked) |
| Ja'Kobi Lane | WR | IR (wrist) · Sleeper, Oct 3 | 4.53 | 0.00 | 48.2 (11, unranked) | 0.0 (1, unranked) |
| Jayden Reed | WR | IR (neck) · Sleeper, Sep 30 | 4.52 | 0.00 | 48.2 (11, unranked) | 0.0 (1, unranked) |
| Ty Chandler | RB | IR (knee) · Sleeper, Aug 25 | 4.50 | 0.00 | 49.7 (11, unranked) | 0.0 (1, unranked) |
| De'Zhaun Stribling | WR | IR (ankle) · Sleeper, Sep 19 | 4.33 | 0.00 | 47.6 (11, unranked) | 0.0 (1, unranked) |
| Andrei Iosivas | WR | IR (thumb) · Sleeper, Sep 26 | 4.20 | 0.00 | 46.6 (11, unranked) | 0.0 (1, unranked) |
| Dont'e Thornton Jr. | WR | IR (undisclosed) · Sleeper, Oct 2 | 4.00 | 0.00 | 42.5 (11, unranked) | 0.0 (1, unranked) |
| Malik Davis | RB | IR (hip) · Sleeper, Sep 12 | 3.93 | 0.00 | 42.2 (11, unranked) | 0.0 (1, unranked) |
| Tyrell Shavers | WR | PUP (knee - acl) · Sleeper, Sep 1 | 3.88 | 0.00 | 41.6 (11, unranked) | 0.0 (1, unranked) |
| Jake Tonges | TE | IR (knee) · Sleeper, Sep 16 | 3.78 | 0.00 | 42.2 (11, unranked) | 0.0 (1, unranked) |
| D.J. Montgomery | WR | IR (abdomen) · Sleeper, Aug 31 | 3.76 | 0.00 | 52.0 (11, unranked) | 0.0 (1, unranked) |
| Irvin Charles | WR | IR (undisclosed) · Sleeper, Aug 31 | 3.76 | 0.00 | 48.5 (11, unranked) | 0.0 (1, unranked) |
| Jeremy McNichols | RB | IR (quadriceps) · Sleeper, Aug 31 | 3.74 | 0.00 | 39.2 (11, unranked) | 0.0 (1, unranked) |
| Calvin Austin III | WR | IR (knee) · Sleeper, Aug 27 | 3.54 | 0.00 | 45.9 (11, unranked) | 0.0 (1, unranked) |
| David Sills | WR | IR (undisclosed) · Sleeper, Aug 31 | 3.45 | 0.00 | 44.4 (11, unranked) | 0.0 (1, unranked) |
| Dillon Gabriel | QB | IR (back) · Sleeper, Aug 31 | 3.44 | 0.00 | 41.6 (11, unranked) | 0.0 (1, unranked) |
| Mason Tipton | WR | PUP (groin) · Sleeper, Aug 31 | 3.43 | 0.00 | 37.6 (11, unranked) | 0.0 (1, unranked) |
| Christian Kirk | WR | IR (calf) · Sleeper, Oct 2 | 3.35 | 0.00 | 44.3 (11, unranked) | 0.0 (1, unranked) |
| Skylar Thompson | QB | IR (undisclosed) · Sleeper, Aug 12 | 3.33 | 0.00 | 37.5 (11, unranked) | 0.0 (1, unranked) |
| Kendrick Law | WR | IR (knee - acl) · Sleeper, Jun 18 | 3.26 | 0.00 | 35.9 (11, unranked) | 0.0 (1, unranked) |
| Josh Oliver | TE | IR (biceps) · Sleeper, Sep 29 | 3.10 | 0.00 | 33.8 (11, unranked) | 0.0 (1, unranked) |
| Brittain Brown | RB | IR (undisclosed) · Sleeper, Aug 31 | 3.09 | 0.00 | 33.1 (11, unranked) | 0.0 (1, unranked) |
| Scott Matlock | RB | IR (undisclosed) · Sleeper, Aug 31 | 2.97 | 0.00 | 32.1 (11, unranked) | 0.0 (1, unranked) |
| Luke Musgrave | TE | PUP (undisclosed) · Sleeper, Sep 1 | 2.89 | 0.00 | 31.8 (11, unranked) | 0.0 (1, unranked) |
| British Brooks | RB | IR (hamstring) · Sleeper, Oct 2 | 2.86 | 0.00 | 31.6 (11, unranked) | 0.0 (1, unranked) |
| Gunner Olszewski | WR | IR (achilles) · Sleeper, Jun 1 | 2.86 | 0.00 | 31.6 (11, unranked) | 0.0 (1, unranked) |
| Tim Patrick | WR | IR (groin) · Sleeper, Sep 12 | 2.85 | 0.00 | 36.6 (11, unranked) | 0.0 (1, unranked) |
| Cole Turner | TE | IR (undisclosed) · Sleeper, Aug 27 | 2.83 | 0.00 | 31.3 (11, unranked) | 0.0 (1, unranked) |
| Eli Stowers | TE | IR (hamstring) · Sleeper, Oct 3 | 2.77 | 0.00 | 30.5 (11, unranked) | 0.0 (1, unranked) |
| Graham Mertz | QB | IR (knee - acl) · Sleeper, Aug 16 | 2.76 | 0.00 | 36.5 (11, unranked) | 0.0 (1, unranked) |
| Myles Montgomery | RB | IR (undisclosed) · Sleeper, Aug 13 | 2.71 | 0.00 | 29.8 (11, unranked) | 0.0 (1, unranked) |
| Jalen McMillan | WR | IR (knee - pcl) · Sleeper, Sep 30 | 2.70 | 0.00 | 28.5 (11, unranked) | 0.0 (1, unranked) |
| Adam Randall | RB | IR (undisclosed) · Sleeper, Aug 31 | 2.62 | 0.00 | 28.8 (11, unranked) | 0.0 (1, unranked) |
| Savion Williams | WR | IR (undisclosed) · Sleeper, Sep 1 | 2.61 | 0.00 | 28.6 (11, unranked) | 0.0 (1, unranked) |
| KeAndre Lambert-Smith | WR | IR (hamstring) · Sleeper, Sep 15 | 2.54 | 0.00 | 28.3 (11, unranked) | 0.0 (1, unranked) |
| Omar Cooper Jr. | WR | IR (ankle) · Sleeper, Sep 19 | 2.45 | 0.00 | 26.0 (11, unranked) | 0.0 (1, unranked) |
| Julian Hill | TE | IR (knee) · Sleeper, Jun 2 | 2.40 | 0.00 | 26.3 (11, unranked) | 0.0 (1, unranked) |
| Nikola Kalinic | TE | IR (knee) · Sleeper, Aug 18 | 2.39 | 0.00 | 26.0 (11, unranked) | 0.0 (1, unranked) |
| Moliki Matavao | TE | IR (knee) · Sleeper, Aug 25 | 2.29 | 0.00 | 25.1 (11, unranked) | 0.0 (1, unranked) |
| Jake Bobo | WR | IR (knee) · Sleeper, Aug 22 | 2.28 | 0.00 | 24.7 (11, unranked) | 0.0 (1, unranked) |
| Beaux Collins | WR | IR (undisclosed) · Sleeper, Aug 31 | 2.27 | 0.00 | 29.0 (11, unranked) | 0.0 (1, unranked) |
| Tip Reiman | TE | PUP (ankle) · Sleeper, Sep 1 | 2.24 | 0.00 | 24.4 (11, unranked) | 0.0 (1, unranked) |
| Joe Royer | TE | PUP (personal) · Sleeper, Aug 30 | 2.21 | 0.00 | 24.3 (11, unranked) | 0.0 (1, unranked) |
| Caleb Lohner | TE | IR (lower body) · Sleeper, Aug 31 | 2.21 | 0.00 | 24.3 (11, unranked) | 0.0 (1, unranked) |
| Jaren Kanak | TE | IR (pectoral) · Sleeper, Aug 17 | 2.21 | 0.00 | 24.3 (11, unranked) | 0.0 (1, unranked) |
| Grant Calcaterra | TE | IR (back) · Sleeper, Sep 1 | 2.20 | 0.00 | 24.2 (11, unranked) | 0.0 (1, unranked) |
| Robbie Ouzts | RB | IR (undisclosed) · Sleeper, Aug 14 | 2.15 | 0.00 | 23.6 (11, unranked) | 0.0 (1, unranked) |
| Cole Burgess | WR | IR (undisclosed) · Sleeper, Aug 5 | 2.12 | 0.00 | 23.3 (11, unranked) | 0.0 (1, unranked) |
| Brock Rechsteiner | WR | Suspended (suspension) · Sleeper, Aug 30 | 2.11 | 0.00 | 23.3 (11, unranked) | 0.0 (1, unranked) |
| Trey Sermon | RB | IR (undisclosed) · Sleeper, Aug 19 | 2.08 | 0.00 | 23.1 (11, unranked) | 0.0 (1, unranked) |
| Will Mallory | TE | IR (thumb) · Sleeper, Aug 31 | 1.80 | 0.00 | 20.1 (11, unranked) | 0.0 (1, unranked) |
| Arian Smith | WR | IR (knee) · Sleeper, Sep 23 | 1.76 | 0.00 | 18.8 (11, unranked) | 0.0 (1, unranked) |
| Ben Yurosek | TE | IR (undisclosed) · Sleeper, Sep 8 | 1.70 | 0.00 | 18.5 (11, unranked) | 0.0 (1, unranked) |
| Carter Runyon | TE | IR (undisclosed) · Sleeper, Aug 31 | 1.64 | 0.00 | 18.3 (11, unranked) | 0.0 (1, unranked) |
| Princeton Fant | TE | IR (knee - acl + mcl) · Sleeper, Aug 7 | 1.28 | 0.00 | 14.1 (11, unranked) | 0.0 (1, unranked) |

players gated: 79; week-5 before > 0: 79; after > 0: 0; sum before 320.5

### QB top 15, week 5, Half PPR (before | after)
| # | Before | proj | ppg (g) | After | proj | ppg (g) |
|---|---|---|---|---|---|---|
| 1 | Josh Allen BUF | 21.9 | 28.7 (4) | Josh Allen BUF | 21.9 | 28.7 (4) |
| 2 | Dak Prescott DAL | 20.9 | 20.6 (4) | Dak Prescott DAL | 20.9 | 20.6 (4) |
| 3 | Jared Goff DET | 20.3 | 21.5 (4) | Jared Goff DET | 20.3 | 21.5 (4) |
| 4 | Jacoby Brissett ARI | 20.1 | 15.8 (4) | Jacoby Brissett ARI | 20.1 | 15.8 (4) |
| 5 | Matthew Stafford LA | 20.0 | 16.9 (4) | Matthew Stafford LA | 20.0 | 16.9 (4) |
| 6 | Drake Maye NE | 18.6 | 13.7 (4) | Drake Maye NE | 18.6 | 13.7 (4) |
| 7 | Bo Nix DEN | 17.9 | 15.1 (4) | Bo Nix DEN | 17.9 | 15.1 (4) |
| 8 | Jayden Daniels WAS | 17.9 | 16.2 (2) | Jayden Daniels WAS | 17.9 | 16.2 (2) |
| 9 | Kyler Murray MIN | 17.4 | 7.8 (3) | Kyler Murray MIN | 17.4 | 7.8 (3) |
| 10 | Trevor Lawrence JAX | 17.0 | 16.8 (4) | Trevor Lawrence JAX | 17.0 | 16.8 (4) |
| 11 | Lamar Jackson BAL | 16.8 | 20.0 (4) | Lamar Jackson BAL | 16.8 | 20.0 (4) |
| 12 | Justin Herbert LAC | 16.8 | 12.4 (4) | Justin Herbert LAC | 16.8 | 12.4 (4) |
| 13 | Brock Purdy SF | 16.8 | 25.4 (4) | Brock Purdy SF | 16.8 | 25.4 (4) |
| 14 | Jalen Hurts PHI | 16.7 | 17.5 (4) | Jalen Hurts PHI | 16.7 | 17.5 (4) |
| 15 | C.J. Stroud HOU | 16.3 | 17.1 (4) | C.J. Stroud HOU | 16.3 | 17.1 (4) |

### RB top 24, week 5, Half PPR (before | after)
| # | Before | proj | ppg (g) | After | proj | ppg (g) |
|---|---|---|---|---|---|---|
| 1 | Jahmyr Gibbs DET | 20.5 | 26.2 (4) | Jahmyr Gibbs DET | 20.5 | 26.2 (4) |
| 2 | Bijan Robinson ATL | 19.6 | 23.7 (3) | Bijan Robinson ATL | 19.6 | 23.7 (3) |
| 3 | Kyren Williams LA | 19.3 | 19.8 (4) | Kyren Williams LA | 19.3 | 19.8 (4) |
| 4 | Javonte Williams DAL | 17.7 | 18.6 (4) | Javonte Williams DAL | 17.7 | 18.6 (4) |
| 5 | Jonathan Taylor IND | 16.9 | 20.3 (4) | Jonathan Taylor IND | 16.9 | 20.3 (4) |
| 6 | James Cook BUF | 16.4 | 15.9 (4) | James Cook BUF | 16.4 | 15.9 (4) |
| 7 | Christian McCaffrey SF | 15.4 | 16.5 (4) | Christian McCaffrey SF | 15.4 | 16.5 (4) |
| 8 | Derrick Henry BAL | 15.2 | 21.8 (4) | Derrick Henry BAL | 15.2 | 21.8 (4) |
| 9 | Chase Brown CIN | 14.3 | 11.9 (4) | Chase Brown CIN | 14.3 | 11.9 (4) |
| 10 | Jaylen Warren PIT | 14.1 | 12.4 (4) | Jaylen Warren PIT | 14.1 | 12.4 (4) |
| 11 | D'Andre Swift CHI | 13.9 | 14.6 (4) | D'Andre Swift CHI | 13.9 | 14.6 (4) |
| 12 | Aaron Jones MIN | 13.7 | 11.8 (4) | Aaron Jones MIN | 13.7 | 11.8 (4) |
| 13 | Ashton Jeanty LV | 13.4 | 16.1 (4) | Ashton Jeanty LV | 13.4 | 16.1 (4) |
| 14 | Jeremiyah Love ARI | 13.2 | 10.8 (4) | Jeremiyah Love ARI | 13.2 | 10.8 (4) |
| 15 | Cam Skattebo NYG | 12.7 | 10.1 (4) | Cam Skattebo NYG | 12.7 | 10.1 (4) |
| 16 | Omarion Hampton LAC | 11.9 | 10.7 (4) | Omarion Hampton LAC | 11.9 | 10.7 (4) |
| 17 | Kyle Monangai CHI | 11.9 | 14.2 (4) | Kyle Monangai CHI | 11.9 | 14.2 (4) |
| 18 | Breece Hall NYJ | 11.8 | 12.5 (3) | Breece Hall NYJ | 11.8 | 12.5 (3) |
| 19 | Bucky Irving TB | 11.7 | 10.2 (4) | Bucky Irving TB | 11.7 | 10.2 (4) |
| 20 | Quinshon Judkins CLE | 11.7 | 10.2 (4) | Quinshon Judkins CLE | 11.7 | 10.2 (4) |
| 21 | De'Von Achane MIA **(IR)** | 11.4 | 7.0 (3) | Bhayshul Tuten JAX | 10.7 | 12.2 (4) |
| 22 | Bhayshul Tuten JAX | 10.7 | 12.2 (4) | Tony Pollard TEN | 10.0 | 8.6 (4) |
| 23 | Travis Etienne NO **(IR)** | 10.3 | 8.5 (3) | Rachaad White WAS | 9.8 | 8.5 (3) |
| 24 | Tony Pollard TEN | 10.0 | 8.6 (4) | Rhamondre Stevenson NE | 9.8 | 9.3 (4) |

### WR top 24, week 5, Half PPR (before | after)
| # | Before | proj | ppg (g) | After | proj | ppg (g) |
|---|---|---|---|---|---|---|
| 1 | Puka Nacua LA | 18.8 | 16.6 (2) | Puka Nacua LA | 18.8 | 16.6 (2) |
| 2 | Amon-Ra St. Brown DET | 17.4 | 18.9 (4) | Amon-Ra St. Brown DET | 17.4 | 18.9 (4) |
| 3 | CeeDee Lamb DAL | 15.6 | 23.4 (4) | CeeDee Lamb DAL | 15.6 | 23.4 (4) |
| 4 | Jaxon Smith-Njigba SEA | 15.4 | 25.2 (4) | Jaxon Smith-Njigba SEA | 15.4 | 25.2 (4) |
| 5 | Chris Olave NO | 14.7 | 19.0 (3) | Chris Olave NO | 14.7 | 19.0 (3) |
| 6 | Davante Adams LA | 14.4 | 15.5 (4) | Davante Adams LA | 14.4 | 15.5 (4) |
| 7 | Michael Wilson ARI | 14.3 | 11.1 (4) | Michael Wilson ARI | 14.3 | 11.1 (4) |
| 8 | Tee Higgins CIN | 13.4 | 14.7 (4) | Tee Higgins CIN | 13.4 | 14.7 (4) |
| 9 | Drake London ATL | 13.2 | 11.8 (3) | Drake London ATL | 13.2 | 11.8 (3) |
| 10 | Nico Collins HOU | 12.9 | 22.5 (2) | Nico Collins HOU | 12.9 | 22.5 (2) |
| 11 | Zay Flowers BAL | 12.2 | 19.4 (3) | Zay Flowers BAL | 12.2 | 19.4 (3) |
| 12 | George Pickens DAL | 11.8 | 7.9 (4) | George Pickens DAL | 11.8 | 7.9 (4) |
| 13 | DeVonta Smith PHI | 11.7 | 13.0 (3) | DeVonta Smith PHI | 11.7 | 13.0 (3) |
| 14 | Parker Washington JAX | 11.5 | 10.8 (4) | Parker Washington JAX | 11.5 | 10.8 (4) |
| 15 | Christian Watson GB | 11.4 | 16.8 (4) | Christian Watson GB | 11.4 | 16.8 (4) |
| 16 | Ja'Marr Chase CIN | 11.3 | 12.4 (4) | Ja'Marr Chase CIN | 11.3 | 12.4 (4) |
| 17 | Garrett Wilson NYJ | 11.1 | 12.8 (4) | Garrett Wilson NYJ | 11.1 | 12.8 (4) |
| 18 | Jameson Williams DET | 11.0 | 7.7 (4) | Jameson Williams DET | 11.0 | 7.7 (4) |
| 19 | Matthew Golden GB | 10.9 | 12.2 (4) | Matthew Golden GB | 10.9 | 12.2 (4) |
| 20 | DK Metcalf PIT | 10.8 | 8.8 (4) | DK Metcalf PIT | 10.8 | 8.8 (4) |
| 21 | Carnell Tate TEN | 10.5 | 8.9 (4) | Carnell Tate TEN | 10.5 | 8.9 (4) |
| 22 | Terry McLaurin WAS | 9.9 | 8.4 (3) | Terry McLaurin WAS | 9.9 | 8.4 (3) |
| 23 | Denzel Boston CLE | 9.8 | 12.2 (4) | Denzel Boston CLE | 9.8 | 12.2 (4) |
| 24 | Rome Odunze CHI | 9.8 | 7.6 (4) | Rome Odunze CHI | 9.8 | 7.6 (4) |

### TE top 24, week 5, Half PPR (before | after)
| # | Before | proj | ppg (g) | After | proj | ppg (g) |
|---|---|---|---|---|---|---|
| 1 | Trey McBride ARI | 14.4 | 13.2 (4) | Trey McBride ARI | 14.4 | 13.2 (4) |
| 2 | Sam LaPorta DET | 12.2 | 11.4 (4) | Sam LaPorta DET | 12.2 | 11.4 (4) |
| 3 | Brock Bowers LV | 10.2 | 20.1 (2) | Brock Bowers LV | 10.2 | 20.1 (2) |
| 4 | Tucker Kraft GB | 8.9 | 7.2 (4) | Tucker Kraft GB | 8.9 | 7.2 (4) |
| 5 | T.J. Hockenson MIN | 8.7 | 9.1 (4) | T.J. Hockenson MIN | 8.7 | 9.1 (4) |
| 6 | Dalton Kincaid BUF | 8.4 | 9.6 (4) | Dalton Kincaid BUF | 8.4 | 9.6 (4) |
| 7 | Tyler Warren IND | 8.3 | 9.2 (4) | Tyler Warren IND | 8.3 | 9.2 (4) |
| 8 | George Kittle SF | 8.2 | 14.1 (4) | George Kittle SF | 8.2 | 14.1 (4) |
| 9 | Dalton Schultz HOU | 7.9 | 8.0 (4) | Dalton Schultz HOU | 7.9 | 8.0 (4) |
| 10 | Jake Ferguson DAL | 7.8 | 7.6 (4) | Jake Ferguson DAL | 7.8 | 7.6 (4) |
| 11 | Cade Otton TB | 7.8 | 5.8 (4) | Cade Otton TB | 7.8 | 5.8 (4) |
| 12 | Mark Andrews BAL | 7.7 | 7.5 (4) | Mark Andrews BAL | 7.7 | 7.5 (4) |
| 13 | Brenton Strange JAX | 7.7 | 7.4 (4) | Brenton Strange JAX | 7.7 | 7.4 (4) |
| 14 | AJ Barner SEA | 7.6 | 5.2 (4) | AJ Barner SEA | 7.6 | 5.2 (4) |
| 15 | Isaiah Likely NYG | 7.5 | 10.5 (4) | Isaiah Likely NYG | 7.5 | 10.5 (4) |
| 16 | Tyler Higbee LA | 7.1 | 8.5 (3) | Tyler Higbee LA | 7.1 | 8.5 (3) |
| 17 | Hunter Henry NE | 7.1 | 4.8 (4) | Hunter Henry NE | 7.1 | 4.8 (4) |
| 18 | Kenyon Sadiq NYJ | 6.9 | 8.2 (4) | Kenyon Sadiq NYJ | 6.9 | 8.2 (4) |
| 19 | Harold Fannin Jr. CLE | 6.8 | 10.4 (4) | Harold Fannin Jr. CLE | 6.8 | 10.4 (4) |
| 20 | Juwan Johnson NO | 6.7 | 13.6 (3) | Juwan Johnson NO | 6.7 | 13.6 (3) |
| 21 | Michael Mayer LV | 6.7 | 8.2 (4) | Michael Mayer LV | 6.7 | 8.2 (4) |
| 22 | Colston Loveland CHI | 6.7 | 3.6 (4) | Colston Loveland CHI | 6.7 | 3.6 (4) |
| 23 | Pat Freiermuth PIT | 6.5 | 8.0 (4) | Pat Freiermuth PIT | 6.5 | 8.0 (4) |
| 24 | Mike Gesicki CIN | 6.2 | 13.0 (3) | Mike Gesicki CIN | 6.2 | 13.0 (3) |

(ROS "after" in the house mart is the week-5 0 over 1 game; every API list and the card withhold it with the reason.)

## Tests

See the hand-back message for the counts (own tests, edited modules' files with known / environmental failures, ruff,
copy standard, web lint + build, e2e at 375 and 1300, `check_root.sh`).

## Not done / limits

* Kickers' NFL-wide `ops.kd_lines` / `ops.kd_ranges` are not gated (house `ops.projections` K rows are).
* `refleague`'s value pane (Players' value columns without a league) and `player_share` (the player page's shell,
  from the board's cache) read the stored board only: right after the nightly, not at noon.
* The house ROS mart still holds 0.0 over 1 game for a player out indefinitely (its consumers in `decisions.py`,
  `anyleague.py` and the Streamlit pages were not changed to NULL at this deadline); the API withholds it.
* The overlay's own Sleeper copy is cached a day (Sleeper's one-call rule): "ruled out at noon" comes from ESPN.
* A Sleeper `NA` code and `Inactive` with a team rule nothing (no settled meaning).
