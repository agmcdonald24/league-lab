### IT-3 — inside a league: the last readers, and the caveats on screen (Wave I-T, 2026-10-09)

Task: `/home/claude/waveIT/BRIEF.md` § IT-3. Branch `dev/IT3` from `main` `7341acc`, worktree `/home/claude/wt-iq2`,
database `league_lab_im4` (the real 2026 board; Sleeper directory copy of 2026-10-05 12:00 UTC).

#### 1. The readers, one by one

| Reader | Before | Now |
|---|---|---|
| `decisions.waiver_views` (Waivers' views: which claim is offered) | `availability.cannot_play(gs)` = the older overlay's live snapshot (`now()`: ESPN + Sleeper only, no stored record, no stale-word rule) filtered by `SITS_CODES` — **not** the same path as the lists | `league_gate.blocks(gs)` + `sits` (the stored record + Sleeper + ESPN, last week's game words dropped): one path |
| `decisions.best_waiver_move` (the trade verdict's "best waiver move") | the same `availability.cannot_play` call | **not changed**: it is IT-1's tonight (their item 4 re-searches it on the basis); the one-line change is the same as above |
| `watchlist.py` | — | already moved by the PO (`player.status_note`, Wave I-S glue): nothing to do |
| `anyleague.unit_lines` (MFL's team-quarterback unit: which QB's line the unit carries) | `report_status.isin(UNIT_SKIP_STATUS)` = ("Out", "Doubtful"), this module's own codes | `availability_gate.sits(report_block(report_status))` — the same week's own report row, asked through the gate; Out and (while it measures unlikely) Doubtful sit, Questionable plays. Today's output is identical (Doubtful is unlikely); it follows IT-2's definition without an edit. `UNIT_SKIP_STATUS` stays as a name (`test_ip5` imports it), unread |
| `mart_player_role_alerts` → `research.role_alerts` (the alerts lists) | the mart's `is_live` only (built from the nightly's game data) | a request-time gate: an alert for a player `league_gate` says sits this week is not listed |
| The card's Signals block (`player.py`) | a role-up alert offered "Upside: if it holds …" for a player who sits | "Upside: none this week — IR (knee - acl) · Sleeper, Sep 28." |
| The card's points chart (`/api/player/{gsis}/projections`: `ratings.player_projections` — the chart reads this route, not `research.player_games`, which carries only the games) | the mart's live-week projection under a head that says 0.0 | the card's week of a player who sits: 0.0 with `sits` = the reason; a played week (the record) is never touched |
| Kickers in the on-demand lineup values (`ondemand.lineup_values`) | — | a free-agent kicker already asks `league_gate` there (IS-2); a rostered kicker's week comes from `lineup.py`'s K branch (`kp["report_status"] in ("Out", "Doubtful")`), which is IT-2's file tonight (their item 6) — **not changed by me** |

#### 2. The card's chart — see the table above (`ratings.player_projections`, a marked `# ---- IT-3` block).

#### 3. The caveats on screen

`/api/my-week` and `/api/waivers` carried `provenance` and `caveats` since IS-2; now both screens draw them with
`ProvenanceLine.svelte` (My Week under the lineup, Waivers under the strongest moves). The caveat's sentence is a
lineup's (`league_gate.lineup_words`; the trade's sentence kept as `verdict_words`): "Tampa Bay's starter is unclear:
Jalon Daniels is listed, the depth chart puts Baker Mayfield first. Baker Mayfield's projection assumes the listing —
check who starts before kickoff." / "Seattle's starter was set by hand (Sam Darnold, not the listed Drew Lock): Sam
Darnold's projection assumes Darnold starts." Waivers' caveats are now about the claims it suggests (`moves`), not the
whole free-agent browse (IS-2 named every quarterback in the browse: three caveats on a QB page with no QB claim).

#### 4. Mahomes at WR2 — a real slot fault, exposed by the fixtures' stale lineup

Reproduced on `league_lab_im4` with the fixture Sleeper answers (week 5): `current_starters` (the fixture's recorded
Sleeper roster for Scrubs team 2) = Mahomes QB, **12490 RB**, Hampton RB, Jefferson WR, Washington WR, Kelce TE,
K. Williams FLEX, **12526 FLEX, 6650 K, KC DEF** — four of them are no longer on the roster this database holds (the
fixture was recorded weeks earlier). The best lineup has no QB (Mahomes and Young on a bye). `pair_moves` tried to pair
the incoming receivers with the out Mahomes: his own slot (QB) admits no receiver, so it tried the slot chain — and the
chain counted every starter of unknown position (the four who left the roster) as a **wildcard that fits any slot**,
so one of them "filled" QB and the receiver "fit": "Start Wilson at WR in place of Mahomes" (WR2).

So: the fixtures' stale lineup is what showed it, but **the fault is real**. The live shape can produce it whenever
Sleeper's submitted lineup still names a player who has left the roster (IO-4's case — "left the roster, still in the
lineup" exists because Sleeper's answer did that) at the same time as an out nobody on the roster can replace. Fixed in
`myweek.pair_moves`: a starter of unknown position keeps his own slot in the chain (he is not moved and fills nothing
else). After the fix the same page says "Your quarterback spot is open: Mahomes and Young are on a bye … Mahomes is
still in your Sleeper lineup: start the player you add in his place." and "Start Wilson at WR (an open spot in your
Sleeper lineup)." Test: `test_a_starter_who_left_the_roster_is_not_a_wildcard_in_the_slot_chain` (fails on the old
chain: it returns `("wilson", "qb")`), plus a legal chain that still pairs.

#### 5. Waivers tops against the directory (after the chain's `project`)

The API on `league_lab_im4` after the chain's `project` (real clock: Waivers decides week 5 — refleague's window; the
stored record gates week 6, the live week since Thursday's kickoff), the overlay off (no outside world here: the stored
record and the directory copy decide). "Directory" is Sleeper's copy of 2026-10-05 12:00 UTC as it stands
(`injury_status` / `status` / team / `news_updated`); "one definition" is `league_status.blocks` over it.

### League of Scrubs · Waivers, all positions (week 5) — the browse, top 10
| # | Player | Pos | Week proj | Directory (injury_status / status / team / news) | One definition | PPG (g) |
|---|---|---|---|---|---|---|
| 1 | Jacoby Brissett | QB | 20.36 | nan / Active / ARI / Oct 4 | no word | 15.76 (4) |
| 2 | Jayden Daniels | QB | 17.97 | Out / Active / WAS / Oct 4 | no word | 16.2 (2) |
| 3 | Bo Nix | QB | 17.96 | nan / Active / DEN / Oct 4 | no word | 15.07 (4) |
| 4 | Kyler Murray | QB | 17.44 | nan / Active / MIN / Oct 4 | no word | 7.84 (3) |
| 5 | Deshaun Watson | QB | 16.31 | nan / Active / CLE / Oct 2 | no word | 17.23 (4) |
| 6 | C.J. Stroud | QB | 16.19 | nan / Active / HOU / Oct 5 | no word | 17.06 (4) |
| 7 | Malik Willis | QB | 15.96 | nan / Active / MIA / Oct 4 | no word | 10.92 (4) |
| 8 | Aaron Rodgers | QB | 15.86 | nan / Active / PIT / Oct 2 | no word | 16.29 (4) |
| 9 | Kirk Cousins | QB | 15.51 | nan / Active / LV / Oct 5 | no word | 20.71 (4) |
| 10 | Daniel Jones | QB | 15.48 | nan / Active / IND / Oct 4 | no word | 10.07 (4) |

League of Scrubs · the strongest moves:
- add Jacoby Brissett (QB) — directory nan / Active; one definition: no word
- add T.J. Hockenson (TE) — directory nan / Active; one definition: no word
- add New England Patriots (DEF) — directory — / —; one definition: no word
moves' adds, first 10: [('Jacoby Brissett', 'no word'), ('Bo Nix', 'no word'), ('Kyler Murray', 'no word'), ('Deshaun Watson', 'no word'), ('C.J. Stroud', 'no word'), ('Malik Willis', 'no word'), ('Aaron Rodgers', 'no word'), ('Kirk Cousins', 'no word'), ('Daniel Jones', 'no word'), ('Tyson Bagent', 'no word')]
League of Scrubs · moves listed: 56; adds who sit this week: 0 []
League of Scrubs · provenance: True; caveats: ["Chicago's starter was set by hand (Tyson Bagent, not the listed Case Keenum): Tyson Bagent's projection assumes Bagent starts.", "Seattle's starter was set by hand (Sam Darnold, not the listed Drew Lock): Drew Lock's projection assumes Darnold starts."]

### Forever Unclean Dynasty · Waivers, all positions (week 5) — the browse, top 10
| # | Player | Pos | Week proj | Directory (injury_status / status / team / news) | One definition | PPG (g) |
|---|---|---|---|---|---|---|
| 1 | Xavier Hutchinson | WR | 8.82 | nan / Active / HOU / Oct 5 | no word | 7.25 (4) |
| 2 | Ryan Flournoy | WR | 8.72 | nan / Active / DAL / Oct 5 | no word | 5.85 (4) |
| 3 | Kendrick Bourne | WR | 8.66 | nan / Active / ARI / Oct 3 | no word | 7.6 (3) |
| 4 | Michael Mayer | TE | 8.66 | nan / Active / LV / Oct 4 | no word | 10.73 (4) |
| 5 | Tyler Higbee | TE | 8.47 | nan / Active / LAR / Oct 3 | no word | 11.03 (3) |
| 6 | Cooper Rush | QB | 7.56 | nan / Active / ATL / Sep 24 | no word | 4.73 (2) |
| 7 | Mitchell Tinsley | WR | 7.43 | nan / Active / CIN / Sep 29 | no word | 7.9 (1) |
| 8 | Michael Carter | RB | 6.77 | Out / Active / TEN / Oct 4 | no word | None (None) |
| 9 | Darnell Washington | TE | 6.62 | nan / Active / PIT / Oct 2 | no word | 6.73 (4) |
| 10 | Ty Johnson | RB | 6.34 | nan / Active / BUF / Oct 4 | no word | 6.1 (2) |

Forever Unclean Dynasty · the strongest moves:
- add Michael Mayer (TE) — directory nan / Active; one definition: no word
moves' adds, first 10: [('Michael Mayer', 'no word'), ('Tyler Higbee', 'no word'), ('Darnell Washington', 'no word'), ('Zach Ertz', 'no word'), ('Tommy Tremble', 'no word'), ('Dawson Knox', 'no word'), ('Austin Hooper', 'no word'), ('Erick All', 'no word'), ('Cole Kmet', 'no word'), ('Jeremy Ruckert', 'no word')]
Forever Unclean Dynasty · moves listed: 60; adds who sit this week: 0 []
Forever Unclean Dynasty · provenance: True; caveats: []

**Read against the directory**: nobody in either top 10, in the strongest moves or in the first ten claims is on a
reserve list, suspended or without a team; **0 of 56 (Scrubs) and 0 of 60 (Dynasty) suggested adds sit**. Two players
carry a Sleeper "Out" in the copy — Jayden Daniels and Michael Carter, both dated Oct 4 (Sunday of week 4) — and the
one definition calls them "no word" for week 5: a game status from before week 4's last kickoff (Monday Oct 5) is week
4's and rules nothing (IR-1's rule; on the live site Friday's fresh Sleeper / ESPN word decides). **No Doubtful player
appears anywhere on this copy**: every Doubtful in the Oct 5 copy is a week-4 word (the audit says the same: "unlikely to
play (Doubtful): 0"), so "now that Doubtful sits" cannot be shown on this database; it is covered by the gate's own
tests (a Doubtful block sits) and by `test_is2.py` / `test_it3.py`, which drive the readers with blocks.

#### The chain (`/home/claude/waveIT/chain.sh /home/claude/wt-iq2 league_lab_im4`, on commit `defe4c0`; ERROR 0 in every step)

```
== 02:24:23 db migrate
schemas and ops tables are in place
== 02:24:28 dbt build (full)
06:31:26  Done. PASS=732 WARN=5 ERROR=0 SKIP=0 NO-OP=0 TOTAL=737
== 02:31:27 project
02:31:41 INFO league_lab.calibration: fi1.0: market week 5; later weeks' lines from the teams' own season (7349 rows, shrink 3.0 games), personnel of the market week (444 rows moved)
02:36:54 INFO league_lab.calibration: hb1.0: market week 5; QB weeks after it blended with the naive line, weight by horizon {2: 0.0, 3: 0.45, 4: 0.25, 5: 0.35, 6: 0.6, 7: 0.95, 8: 0.75} (lambda 0.25, k 6.0); 1061 QB lines moved
02:37:01 INFO league_lab.kdef: kd League of Scrubs (551104): D/ST keys not projected (price 0): def_st_ff, def_st_fum_rec, st_ff, st_fum_rec
02:37:08 INFO league_lab.availability_gate: availability gate: week 6, Sleeper directory (copy of 2026-10-05T12:00:39.609393Z): 77 players who cannot play or are unlikely to play get 0 this week (77 of them out indefinitely: no later weeks)
projected 19844 rows for 2026 (2 league(s), weeks 1-18); wrote 13572 (weeks [6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18]), kept frozen weeks [1, 2, 3, 4, 5]
availability gate, week 6: Sleeper directory copy of 2026-10-05T12:00:39.609393Z; 77 players who cannot play or are unlikely to play get 0 this week, 77 of them
== 02:37:52 projection marts
06:38:07  Done. PASS=145 WARN=0 ERROR=0 SKIP=0 NO-OP=0 TOTAL=145
== 02:38:07 availability guards (as errors)
06:38:17  Done. PASS=2 WARN=0 ERROR=0 SKIP=0 NO-OP=0 TOTAL=2
== 02:38:17 audit
# List audit — 2026, week 5
_Built 2026-10-09 06:38 UTC; every list a visitor can open without a league (Half PPR, PPR, Standard; this week and rest of season; the free calculator's values)._

## Players who cannot play or are unlikely to play and are still ranked or valued: 0
_Who cannot play: 236 players, unlikely to play (Doubtful): 0, by Sleeper's directory (copy of 2026-10-05T12:00:39.609393Z; the directory alone, never the stored record it checks) (league_lab.availability_gate)._
- None: every player who cannot play or is unlikely to play is out of this week's lists, and every player out indefinitely out of the season lists and the calculator's values.
… (the audit's "projected against what they have scored" notes follow)
```

#### Screenshots (`docs/handbacks/it3/`, JPEG q70, 375 and 1300; the API on `league_lab_im4`)

* `myweek-provenance_*.jpg` — Forever Unclean Dynasty, team 12, under the lineup: "Tampa Bay's starter is unclear: Jalon
  Daniels is listed, the depth chart puts Baker Mayfield first. Jalon Daniels's projection assumes the listing — check
  who starts before kickoff." then "Model v3.6, data published 9 Oct, 2:31 am ET · week 5 · checked on 2021–2025: next
  week graded."
* `waivers-provenance_*.jpg` — League of Scrubs, team 2, under the strongest moves: "Chicago's starter was set by hand
  (Tyson Bagent, not the listed Case Keenum): Tyson Bagent's projection assumes Bagent starts." then the provenance line
  (weeks 5–8, "quarterbacks weak" beyond next week).
* No sideways scroll at 375 (scrollWidth 375), no page errors. The card's chart change (0.0 for the card's week of a
  player who sits, `sits` = the reason) is in the answer; the chart draws it as "projected 0.0 (0.0–0.0)" and the head
  and the projection block above it say why (no web change on the card).

#### Not done / cut for the clock

* `decisions.best_waiver_move` still calls `availability.cannot_play` — IT-1 owns it tonight (their item 4); the
  replacement is the same three lines as in `waiver_views`.
* A rostered kicker in `lineup.py` still sits by `kp["report_status"] in ("Out", "Doubtful")` — `lineup.py` is IT-2's
  tonight (their item 6). A free-agent kicker in the on-demand values already asks `league_gate`.
* The card's chart says "projected 0.0" for the week, not the reason itself (the head says it): a `sits` field is in
  the answer for a later web line.
* Waivers' caveats are about the suggested claims only; the free-agent browse names no caveat.

#### Tests

* New: `api/tests/test_it3.py` 6 passed (the slot chain — fails on the old chain, which returns `("wilson", "qb")`; the
  lineup words; role alerts leave out a player who sits; the card's chart gated for the card's week only; the team-QB
  unit and the waiver views ask the gate). `test_is2.py` 7 passed (its provenance test now expects the claims only).
* API files of the modules I edited (`test_it3`, `test_is2`, `test_myweek`, `test_player`, `test_in5`, `test_ip5`,
  `test_ip4`, `test_research`, `test_parity`, `test_ic2`, `test_if3`, `test_io1`, on `league_lab_im4`): 7 failed /
  168 passed — **all 7 in the known list**, 0 new by name. `test_parity` passed (the console page still matches the card).
* Root suite (`check_root.sh`): 4 failed / 1692 passed / 3 skipped, **0 new**.
* `scripts/gate.sh python`: GATE PASSED (root 781, api 29, ruff). ruff and the copy standard clean; `npm run lint` 0
  errors (207 files); the build.
* **e2e, the whole fixtures suite** (My Week and Waivers are opened by nearly every spec; both projects): **597
  passed, 17 skipped, 0 failed** in 15.3 m. No saved answer re-saved: the saved answers carry no `provenance` /
  `caveats`, and the line draws nothing without them. The screenshots it rewrites under `docs/handbacks/in*`, `io*`,
  `ip*` were checked out again.
* The chain: above, ERROR 0 in every step (dbt build PASS 732 / WARN 5 / ERROR 0; `project` week 6, 77 gated; the
  projection marts PASS 145; both availability guards as errors PASS 2; the audit's first line 0).

#### Edits outside my files

* `api/league_lab_api/ratings.py` (`player_projections`, one `# ---- IT-3` block): the card's chart reads this route,
  not `research.player_games` (which the brief names; it carries the games only).
* `api/league_lab_api/research.py` (`role_alerts`, one `# ---- IT-3` block): the alerts lists' only reader of the mart.
* `api/league_lab_api/decisions.py`: `waiver_views` only (a marked block; not `best_waiver_move`, IT-1's).
* `CHANGELOG.md`, `docs/WORDS.md`.

#### The PO's lines

None required (`test_parity` passes). For the console's twin of the card to say the same thing as the API card when a
player who sits has a role-up alert, `app/pages/0_Player.py` (it already has `gate_note`):

```diff
-            if r["direction"] == "up" and is_num(r["larger_points"]):
+            if r["direction"] == "up" and gate_note and gate_note.get("sits"):          # ---- IT-3
+                st.markdown(f"Upside: none this week — {gate_note['why']}.")
+            elif r["direction"] == "up" and is_num(r["larger_points"]):
                 st.markdown("Upside: " + scenario_phrase(r, league_name))
```

#### Found, not mine

* `decisions.best_waiver_move` calls `availability.cannot_play` (the older overlay's snapshot, no stored record): the
  verdict's "best waiver move" can propose a player the lists gate — IT-1's item 4 is where it goes.
* `lineup.py`'s K branch tests `("Out", "Doubtful")` itself (IT-2's item 6).
* On the live site the card's chart reason and the head come from two paths until IT-2's report source lands in
  `availability.statuses`: the head (`player.status_note`) also reads the week's own report; the chart asks
  `league_gate` (record + Sleeper + ESPN). A player Out only on the report has the head's reason and the mart's number
  in the chart until then.

#### Next

The trade rosters' status cells are IT-1's tonight; the chart's own line for "he sits" (the `sits` field is there);
`league_gate.blocks` should pick up IT-2's report source with no edit — check the chart and the role alerts after
their merge.
