### IS-2 — inside a league: the same "can he play" check as the public lists, and the reason beside the zero (Wave I-S, 2026-10-08)

Task: `/home/claude/waveIS/BRIEF.md` § IS-2 (items 1 and 2; item 3 half: the data, not the start/sit softening). Branch `dev/IS2` from `main` `76b98df`,
worktree `/home/claude/wt-iq2`, database `league_lab_im4` (2026 week 5, Sleeper directory copy of 2026-10-05 12:00 UTC;
`db migrate` + `project` run once at 18:21–18:30 ET: "79 players who cannot play get 0 this week, 79 of them out
indefinitely").

#### How every league reader asks now

* **API** (`api/league_lab_api/league_gate.py`, new): `blocks(ids, season, week)` = `availability.statuses` (the
  stored record + the overlay's Sleeper and ESPN words), `sits` = `availability.sits`, `note(block)` = the piece a
  screen shows (`status`, `why`, `sits`, `out_indefinitely`, `words` = the block's `ros_words` / `week_words`). The
  week is refleague's window (`availability._current`, the week `/api/ros` gates).
* **src** (`src/league_lab/league_status.py`, new; no API import): `blocks(query, season, week)` =
  `availability_gate.statuses_from_query` (Sleeper's directory copy + the stored record, stale game statuses dropped),
  `directory_block(entry)` = `classify` over one Sleeper directory entry a caller already holds, `record_block(text)`
  = one stored record, `conn_query(conn)` (a failed statement rolls back to a savepoint only).
* No reader tests a status code or a status string: `sits()` decides "left out this week", `out_indefinitely`
  decides "every later week too", the words are the block's. When IS-1 sets `unlikely` (Doubtful), every
  request-time reader and every `league_status.blocks` reader picks it up without an edit; the two readers of the
  stored record alone (`lineup.py`, `REPLACEMENT_SQL`) pick it up when `project` writes the record for every player
  `sits()` leaves out (today `apply_to_project` writes it for `cannot_play` only — IS-1's call).

#### Reader by reader (week 5 on `league_lab_im4`; "the old field" = `mart_player_availability.injury_status`, nflverse's newest report row — on this copy week 4's game status)

| Reader | Decided from the old field | Decides now | What changed on `league_lab_im4` |
|---|---|---|---|
| `src/league_lab/trades.py` `REPLACEMENT_SQL` (replacement level: nightly waivers, reports, the API's trade context, the console page) | a free agent with `Out` / `IR` is not the replacement | a free agent the gate's stored record leaves out of a week of the horizon is not (`to_jsonb(p) ->> 'availability'`: answers on a database without the column) | nothing: all 10 position levels (Scrubs 6, Dynasty 4) identical |
| `decisions.FA_SQL` → `_free_agents` (Waivers, "Browse every free agent"; house leagues) | `Out` / `IR` left out; the old field shown as his status | out indefinitely: not listed; sits this week: listed at 0 with `availability.why` and the sentence; `injury_status` = the block's label | **Kyler Murray** (Scrubs; old field "Out" = week 4) is listed again: QB #4 of the browse at 17.44 — the Rankings rank him QB9 at 17.4 (before, Waivers hid a player the Rankings ranked) |
| `decisions.FA_POOL_SQL` → `_house_fa_pool` (the trade fill's free agents) | `Out` / `IR` left out; nflverse `report_status` Out / Doubtful unplayable | sits this week: unplayable that week with `why` as the reason; out indefinitely: every week | Kyler Murray back in the pool (as above); no `report_status` rows for week 5 in this copy |
| `anyleague.free_agents` (any Sleeper / ESPN / Yahoo league's free agents: Waivers, the Finder) | `Out` / `IR` of the mart row, else the directory's `injury_status` | the API's request-time blocks (`il4_free_agents` passes them); without them the directory entry's `classify` | not measurable here (needs a non-house league's directory); unit-tested |
| `src/league_lab/waivers.py` free agents (nightly adds) and `UPSIDE_SQL` (stashes) | `Out` / `IR` in SQL | `league_status.blocks` → `sits` | the free-agent set differs by Kyler Murray only (514 QB/RB/WR/TE free-agent rows; old left out 1, new 0); takes effect at the next `project` |
| `src/league_lab/signals.py` scenario expiry ("the teammate is back") | back = `ACT` and no designation at all in the mart (last week's word kept a scenario alive) | back = `ACT` and not `sits` | not measured (the scenarios are rewritten by the next `project`) |
| `ondemand.lineup_values` (rest of season, "lineup" view: a free agent's weeks) | the label against its own sets (`UNPLAYABLE_NOW`, `{IR, PUP, SUSPENDED}`) | sits: 0 this week; out indefinitely: 0 every week | not measured separately (the 79 recorded players) |
| `player.py` (the league card: status line, projection) | the old field + the older overlay's own codes; projection from the mart | the block: "⚠️ **IR (knee - acl) · Sleeper, Sep 28**. On injured reserve: …"; a player who sits gets no projection ("unavailable: …", `proj_points` 0.0) and no "Why this number" (it read the mart's 11.4) | **59 of 291 rostered skill players' lines change**: 34 lose last week's word ("Out" — Breece Hall, Justin Jefferson, Jayden Daniels, Kyler Murray …; "Questionable" — Burrow, Olave …) → "No injury designation"; 17 gain one (Achane, A.J. Brown, Etienne, Jordan Mason, Dart … "IR (…) · Sleeper, <date>"); 8 change word (Alec Pierce "Out" → "IR (heel) · Sleeper, Oct 2", Charbonnet "Out" → "PUP (knee - acl) · Sleeper, Oct 2" …). Achane's card: projection 11.44 (the mart, not yet rebuilt after `project`) → "unavailable: IR …", 0.0 |
| `src/league_lab/lineup.py` `_proposed_player` (the nightly lineup, skill positions) | nflverse `report_status` Out / Doubtful → sits | the stored record (`ops.projections.availability`) → `sits`; reason = the block's label ("Out", "IR" …); nflverse `RES` kept | 0 of 393 rostered skill players change in week 5 (30 sit before and after: `RES` + recorded; this copy has no week-5 report rows) |
| `roster_value.py` | no status read of its own (lineup roles / reasons) | inherits `lineup.py` | — |
| My Week (`myweek.lineup`), Team (`decisions.team`) — item 2 | a bare 0.00 (or "IR slot") | the row carries `sits` and the block's `why` beside his 0 | Scrubs team 2: Charbonnet "PUP (knee - acl) · Sleeper, Oct 2", Coleman "IR (ankle) · Sleeper, Sep 26"; Dynasty team 12: Adam Randall, Coleman |

**Face validity** (the API on `league_lab_im4`, overlay off — the stored record decides; week 5):

| List | Top (week 5 · status by the one definition · PPG (games)) |
|---|---|
| Scrubs, Waivers browse, all | Brissett 20.36 · no word · 15.8 (4); Daniels 17.97 · 16.2 (2); Nix 17.96 · 15.1 (4); **Murray 17.44 · no word · 7.8 (3)** (was hidden by last week's "Out"); Watson 16.31 · 17.2 (4); Stroud 16.19 · 17.1 (4) |
| Scrubs, Waivers browse, RB | Dowdle 9.27 · no word · 4.3 (2); K. Mitchell 8.27 · 6.6 (4); C. Rodriguez 7.51 · 5.7 (4); Allgeier 7.23 · 6.4 (4); B. Robinson 7.17 · 7.3 (3) |
| Dynasty, Waivers browse, RB | M. Carter 6.77 · no word · —; Ty Johnson 6.34 · 6.1 (2); Perine 6.07 · 3.6 (4); Sanders 5.96 · 5.1 (4) |
| Scrubs team 2, My Week | starters: K. Williams 19.25, Hampton 11.92, Nacua 17.60, Wilson 14.14, Washington 11.42, Jefferson 10.22 (QB and TE empty: Mahomes, Young, Kelce on a bye); can't play: Charbonnet 0.00 "PUP (knee - acl) · Sleeper, Oct 2", Coleman 0.00 "IR (ankle) · Sleeper, Sep 26" |

Nobody listed in these tops is on a reserve list or ruled out by the directory copy; Dowdle and Murray carried last
week's "Out" in the nflverse report and are ranked by the public lists on the same copy. (On the live site the
overlay's fresh Sleeper / ESPN word decides; Breece Hall is "Doubtful … Oct 7" there, which IS-1 decides.)

**Between a deploy and the refresh** (both `availability` columns renamed away on `league_lab_im4`, a fresh API):
My Week (both leagues), Waivers (Scrubs all; Dynasty RB and all), Team, the card (both leagues), Trades' lists, `/ros`
lineup view: all 200, no traceback. **The first try answered 500** on Dynasty's Waivers RB: a free agent without a
block became a frame's NaN, and `note()` called `.get` on it — fixed (every helper treats a non-block as no word) and
tested (`test_waiver_browse_without_any_record_answers`).

#### Tests

* `api/tests/test_is2.py` 6 passed; `tests/test_is2_league_status.py` 8 passed. **On the old readers 10 of the 14
  fail** (the 4 that pass are the helpers' own tests): Waivers browse keeps Achane (old field empty, block IR), the
  trade fill marks him playable, the on-demand list gets no blocks, the lineup sits on `report_status` and not on the
  record, `REPLACEMENT_SQL` reads `injury_status`, the browse 500s without a record.
* `tests/test_lineup.py::test_build_proposed_realised_locks_byes_and_flags` asserted the old rule (nflverse "Out" →
  sits): its player now carries the gate's record (`AG.record_text`), the same expected reason "Out". 265 passed.
* Root suite (`check_root.sh`, on `league_lab_im4`): 11 failed / 1669 passed / 3 skipped; new against the known list:
  `test_lineup.py::test_build_proposed_realised_locks_byes_and_flags` (fixed above),
  `test_ros.py::test_mart_matches_the_trade_engines_sum_on_the_same_weeks` (fails on `main`'s code on this database
  too: data state), `test_v1.py::test_close_calls_are_the_cards_decisions[2,3,4,9,10]` — failed in that run and in one
  targeted run right after it, then **passed 3 times in a row on the same code** (and on `main`'s code); I did not find
  the cause; the PO's merge run will say.
* API test files of the modules I edited (`test_myweek`, `test_player`, `test_decisions`, `test_i0a`, `test_ib0`,
  `test_il4`, `test_anyleague`, `test_ip5`, `test_ig3`, `test_ir4`, `test_ia3`, `test_ir0`, `test_is2`, on
  `league_lab_im4`): 27 failed / 184 passed / 1 skipped; 24 of the 27 are in the known list; the other 3
  (`test_decisions.py::test_waivers_house_route_is_the_mart[both leagues]`,
  `test_ib0.py::test_waivers_never_calls_an_overlay_starter_would_not_start[None]`) **fail the same on `main`'s code
  on this database** (data state: week 5 here, the known list is week 4's).
* `scripts/gate.sh python`: GATE PASSED (root 780, api 25, ruff). ruff clean; `copy_standard.py --check` clean;
  `npm run lint` 0 errors (207 files); build ok.
* **e2e, the whole fixtures suite** (every spec opens My Week, Team, Waivers or a card; both projects): 588 passed,
  1 failed, 23 skipped in 12.2 m. The failure, `il5/fixtures.spec.ts:91` [desktop] (the watchlist's analytics events:
  the third `watchlist_remove` missing), is not on a screen I changed and **passed on its own re-run** (`e2e/il5`: 14
  passed). No saved answer needed re-saving: the new fields are absent from the saved answers and the screens fall
  back to what they showed.
* QA at 375 and 1300 (`docs/handbacks/is2/`, on `league_lab_im4`, real clock): My Week's bench and can't-play list
  (Charbonnet 0.00 "IR slot / PUP (knee - acl) · Sleeper, Oct 2"), Team (the roster row's line), Achane's league card
  (the projection withheld, the status line); no sideways scroll at 375 (scrollWidth 375), no page errors. Waivers has no
  screenshot: no free agent on this copy has a word from the one definition (the reserve lists are also off the
  active-roster filter), so its screen looks as before; its change is in `test_is2.py`.

#### Not done / limits

* **Item 3, half**: `/api/waivers` and `/api/my-week` now carry `provenance`, `caveats`, `caveat_effect`,
  `caveat_rule` (`league_gate.with_waivers` / `with_lineup` → `provenance.for_players` over the players the answer
  names; `test_waivers_and_my_week_carry_provenance_and_the_starter_caveats`). On this database: Scrubs Waivers QB
  `withhold` with 3 caveats (Tampa Bay's starter unclear, Chicago's set by hand …), Dynasty My Week `withhold` (Jalon
  Daniels on the roster) — the caveat words are the trade's ("No verdict while …"): a screen that shows them on My Week
  needs its own words. **Not done**: no screen shows them yet
  (no `ProvenanceLine` on Waivers / My Week), and start/sit does not soften for a hand-set quarterback (the "Who should
  I start?" handler is IS-1's file tonight).
* `src/league_lab/reports.py` (the nightly's markdown report packs, five queries print or filter the old field),
  `anyleague.UNIT_SKIP_STATUS` (MFL's team-QB unit skips a QB by nflverse's Out / Doubtful), and
  `mart_player_role_alerts.sql` (`trigger_ended` from the old field; read by `research.py`'s alerts and the card's role
  block) are **not moved**; no request-time gate on the role alerts yet.
* The trade rosters' status cells (`Trades.svelte`, `TradeCard.svelte`: IS-3's files tonight) are not changed.
* `lineup.py` still sits a **kicker** on nflverse's report status (kickers are IS-1's item 5); `RES` (nflverse's weekly
  roster) is kept in `lineup.py`, `FA_SQL`, `FA_POOL_SQL` and the free-agent SQL as an "active NFL roster" filter.
* `REPLACEMENT_SQL` and `lineup.py` read the stored record only (the nightly's view), not the request-time overlay: a
  player ruled out after the nightly moves the lists at once, the replacement level and the stored lineup at the next
  `project`. My Week's re-solve on new news stays the older overlay's (`availability.apply_to_rows`, IS-1's constants).
* My Week and Team are checked on the database and in the screenshots, not by a unit test of `myweek.lineup` /
  `decisions.team`.

#### Edits outside my files

`api/league_lab_api/myweek.py` (one `# ---- IS-2` block at the end of `lineup()`: `sits` and the reason on each row);
`api/league_lab_api/decisions.py` (marked blocks: `FA_SQL`, `FA_POOL_SQL` + `_house_fa_pool`, `_free_agents`,
`il4_free_agents`' call, `team()`'s roster rows — none in the trade-basis functions); `web/src/components/LineupTable.svelte`
(the reason shows for a player who sits in every table, not only the full list); `tests/test_lineup.py` (above);
`api/league_lab_api/main.py` (the `/api/waivers` and `/api/my-week` handlers wrap their answer in
`league_gate.with_waivers` / `with_lineup`, marked `# ---- IS-2 item 3`; no new route); `CHANGELOG.md`, `docs/WORDS.md`.

#### PO lines

None needed in PO-owned files.

#### Found, not mine

* `api/league_lab_api/watchlist.py:110` reads `player.overlay_status` (the older overlay's own codes) for the
  watchlist's status: the next reader to move.
* `availability.ros_overlay` still sets `injury_status` from the older overlay (`now()`) before `ros_gate` overwrites it.
* `decisions.py` (the waiver views, ~4578 and ~5055) blocks a claim with `availability.cannot_play(...)` = the older
  overlay's `CANNOT_PLAY` (Doubtful and Inactive in it): it follows the one definition once IS-1 makes those constants a
  view of the gate (IS-1's item 3).

* The card's "Points against the projection" chart (`research.player_games`, `/api/player/{gsis}/games`) still draws
  week 5's live projection from the mart: on this copy, where only `project` ran and the marts were not rebuilt,
  Achane's chart shows about 11 for week 5 under a head that says 0.0. After a nightly the mart holds the 0; between
  `project` and the marts (and between a deploy and the refresh) a request-time gate there is needed — not my file.

#### Next

`reports.py`, `UNIT_SKIP_STATUS` and the role alerts on the one definition (the alerts at request time); the trade
rosters' status cells once IS-3's files settle; `project`'s record for every player `sits()` leaves out (so the nightly
lineup and the replacement level follow IS-1's Doubtful rule); item 3.
