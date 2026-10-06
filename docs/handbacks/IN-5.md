# IN-5 — My Week says what it means, and no screen can go blank (Wave I-N, 2026-10-06)

Branch `dev/IN5` from `main` `967b2d9` (the PO's hotfix). Dev IN-5. Worktree `/home/claude/wt-in5`.

## Andrew's morning — before / after

The database holds the nightly's **week-5 rows**: League of Scrubs roster 2 has its QB and TE slots empty (Mahomes,
Young, Kelce on a bye; Coleman and Charbonnet on IR). With the clock pinned to his report (Tue 09:20 ET) and his Sleeper
lineup reconstructed (Mahomes at QB, Kelce at TE, Croskey-Merritt in the second FLEX — the sandbox's Sleeper fixture is
an older roster), the three versions of `myweek.build_actions` on the same rows and cards:

| | My Week's actions |
|---|---|
| before (the code live at 09:20) | "Start Jefferson at FLEX (or Boston: a coin flip) in place of **Kelce**." · "**Start** Mahomes out of your lineup." |
| PO hotfix (`967b2d9`) | "Start Jefferson at FLEX (or Boston: a coin flip) in place of Kelce." · "Take Mahomes out of your lineup." |
| **IN-5** | "Your quarterback spot is open: Mahomes and Young are on a bye. Add a quarterback before Sun 1:00 PM ET." · "Your tight end spot is open: Kelce is on a bye. Add a tight end before Sun 1:00 PM ET." · "Start Jefferson at FLEX (or Boston: a coin flip) in place of Croskey-Merritt." |

The hand-built frame of the brief (two open spots, six who cannot play, one FLEX coin flip; `test_in5.morning()`)
reproduces Andrew's exact live sentences on the old code — "Make 2 changes: Washington at FLEX (or Croskey-Merritt: a
coin flip) in place of Mahomes; Croskey-Merritt out of your lineup." and "Start Kelce out of your lineup." — and gives
"Your quarterback spot is open: Mahomes and Young are on a bye. Add a quarterback before Sun 1:00 PM ET." · "Your tight
end spot is open: Kelce is on a bye and Ferguson is out. Add a tight end before Sun 1:00 PM ET." + the review line
"Washington or Croskey-Merritt at FLEX: a coin flip, 0.1 points apart; your lineup has Croskey-Merritt — no clear
upgrade." (0.06 apart: under the 0.5-point action bar, as before). Each open spot's reason: "Nobody else on your roster
can play quarterback this week. Mahomes is still in your Sleeper lineup: start the player you add in his place."; its
link **Find a quarterback on Waivers ›** (`/waivers?position=QB`).

## Done (the numbered list)

1. **Open spots** (`api/league_lab_api/myweek.py`, marked `IN-5`): `fits` (bipartite matching: the submitted lineup
   with the swap made still fits its slot codes — the slot chain), the pairing takes a direct fit first, then a chain
   fit, never the old fallback `ins[0]`; ties sorted by key (the old order followed a `set`). `open_spots`: one action
   per open slot type (the best lineup's `is_empty_slot` starters), kind `change` (a roster alert, urgency 1, first
   among same-time actions), `open_slot` {slot_type, slots, position, words, players, named}, `href`, `href_label`;
   the outs it takes over leave the pairs. `open_deadline`: the kickoff most of the roster's games still to start share
   (the main slate), earliest on a tie, "before his game kicks off" when none. The coin-flip clause once per action and
   never for a player the same action takes out. `more_words`: "1 more roster alert: …".
2. **Words**: "Change needed" → **Roster alert** (`lib/week.ts` `STATUS_WORD` / `ACTION_WORD`; the API never sent it);
   "What changed" → **News feed** (`lib/feed.ts` `NEWS_FEED`, MyWeek's heading; testid `what-changed` kept). WORDS.md §
   "My Week says what it means" + the three dictionary rows; `copy_standard.py --check` clean.
3. (a) e2e `web/e2e/in5` (10 tests: 5 × 375 / 1300) on `web/fixtures/in5/` (recorded through the real routes by
   `test_record_andrews_morning`, `IN5_RECORD=1`; `team_open_nan.json` = the 09:20 answer with both open ids "nan").
   (b) keyed `{#each}` audit below. (c) `App.svelte`: two `<svelte:boundary>` blocks (the whole app; each screen in the
   frame, the bar stays), reset when the screen changes; `ErrorCard crashed={screen}`: "This screen hit a problem" +
   Reload + GA `exception` {description: "screen: team", fatal: false, screen_name}. (d) `str()` ids on the way out:
   `decisions._alt_player` (sleeper_id, the name fallback), `od_transactions` and `recent_adds` (transaction_id — a
   missing one is `w<round>-<n>`, never "None" — and sleeper_player_id) through `decisions._sid`, which now refuses
   "None" / "null" too; `test_no_nan_text_on_the_house_answers` walks Team, My Week, League and Waivers for both house
   leagues (0 bad values), `test_record_andrews_morning` the open-spot answers (0).
4. **The five tests that turned red Monday ~20:00 ET** (`test_ia2` partners, `test_ib0` one-lineup-total × 2 dynasty,
   `test_ii1` Folk × 2): `analytics.mart_league_roster_horizon` is a **view** whose "this week" is the first REG week
   with `kickoff_at > now()` — the database's clock. Week 4's last kickoff was 2026-10-06 00:15 UTC (Mon 20:15 ET): the
   view moved to weeks 5–8 while the pinned suites are in week 4. Fix: dbt macro `league_lab_now()` =
   `coalesce(nullif(current_setting('league_lab.now', true), '')::timestamptz, now())` in the view; `db._run` sends the
   pinned clock as `set_config('league_lab.now', …, true)` in the statement's transaction **only when the clock is
   pinned** (LEAGUE_LAB_NOW / `clock.pin`; production sends nothing: the view reads `now()` as before). Verified
   read-only: the view's body at the pinned clock gives weeks 4–7 (5–8 at 09:20 Tuesday); with that body substituted
   for the view (a scratch plugin, deleted), `test_ia2` partners and `test_ii1` Folk × 2 pass; `test_ib0` dynasty × 2
   read `mart_league_roster_value` / `_slot_strength`, views over the horizon view, which a substitution cannot reach —
   expected to pass once the view is rebuilt, **not verified** (no dbt run here).

## Keyed `{#each}` audit (175 keyed in `web/src`)

Changed to `` `${id}#${i}` `` (cannot collide: the suffix is the place) — 42 lists in 19 files: LineChart (points ×2),
Picker (leagues, rosters), ScheduleTable (weeks), Table (every caller's `rowKey`), Tabs (items), TopBar (search hits),
stats/StatsTable (rows), About (features by rank, positions, calls, decision weeks, byPosition), Account (leagues,
connections, passkeys), Compare (hits, next4), MyWeek (the calls behind Why?, the cards), Players (selected ×3: a URL
can repeat a player), Receivers, Ros (rows, why pieces), Team (slots, slot groups, slot strength, weekly, record weeks,
calls, league rows; the roster: the PO's hotfix), Trends, Waivers (top 3, view moves, stashes, free agents), Watchlist,
WeekStrip. Left (client-defined constants, closed sets, column definitions, Map-grouped lists — unique by construction).
**Not changed, other packages' files** (an API id that could in principle repeat; each a one-line change if the owner
wants it): Heatmap rows/cols, MatchupEvidence `missing` (gsis), Matchups starters / corner rows (gsis) — IN-3; PlayerPane
metrics (label), Player why pieces (stat), Trades packages (sleeper_id), TradeCalc others / unavailable / give / get /
cut / starters in-out / weekly — IN-2; Dfs projRows / unmatched / skipped / under / over — IN-4; League standings / luck /
bench (roster_id), matchups (week), games (matchup_id), draft (pick_no) — IN-6; Leagues provider league / team lists —
IN-1. The boundaries catch any of them: a duplicate there is an error card, never a blank screen.

## Evidence

* `api/tests/test_in5.py` **18 tests**, all pass (7 s). `test_in0.py` passes.
* Modules edited — their API test files (37 files: myweek's 32 + decisions' transactions / alternatives): **72 failed /
  504 passed / 10 skipped** (661 s); 66 on `known_api_failures.txt`; the other **6 fail the same on `main`'s API code at
  10:30 ET** (`test_ig2` × 3: the event store's status / brief lines; `test_u1` × 3: usage rows) — not mine, see below.
  Re-run after the `db.py` change (10 files incl. ia2 / ib0 / ii1): 25 failed / 90 passed, all on the known list.
* `ruff check src app tests api` clean; `npm run lint` (177 files, 0 warnings) and `npm run build` clean;
  `copy_standard.py --check` clean; `league-lab dbt parse` clean.
* e2e `in5`: **10 passed** (375 and 1300). On `main`'s web code the same spec fails 3: the words, the duplicate-key
  answers (blank screen), the render error (blank screen). The two e2e files whose words changed on purpose:
  `e2e/ib3` (`/Change needed/` → `/Roster alert/`), `e2e/ie1` (`"Change needed"` → `"Roster alert"`). **Full fixtures
  suite: 441 passed / 3 skipped / 0 failed** (11.4 min; 431 before + the 10 new).
* Team's open rows also link to Waivers at the position ("Find one on Waivers ›", `lib/week.ts` `waiversFor`); the
  Team-related e2e specs (ii4, ic4, ik3, ii0, v2, decisions, ih2: 72) pass after it.
* Screenshots (`docs/handbacks/in5/`): My Week, Team (the "nan" answer) and its roster card, the error card — each phone
  and desktop; no
  sideways scroll at 375, the screen's column > 900 px at 1300.

## Words changed on purpose (old string → where)

`api/tests/test_ie1.py` ("1 more change" → "1 more roster alert"), `web/e2e/ib3`, `web/e2e/ie1`, `docs/WORDS.md` (rows
104, 148, 173 + the new section), `docs/DESIGN.md` (136), `docs/HOSTING.md` (727, 767), `docs/ANY_LEAGUE.md` (606).
Not changed: test names and comments that call the block "What changed" (internal names); `MatchupEvidence`'s "What
changed" (the corners line — another thing); `app/lib/table.py` "What changed" (the role-change column); the empty
line "Nothing has changed since the morning build." (recorded in 9 fixture answers).

## PO lines

* `docs/PROJECT_PLAN.md:455` "a status per call — Change needed, Already set," → "Roster alert (was Change needed),
  Already set,"; `docs/HANDOFF.md:155, 170` "What changed" → "the News feed (was What changed)".
* `app/whats_new.md` (new top entry): "My Week says what it means: a starting spot nobody on your roster can fill is
  its own roster alert, with who cannot play and a link to Waivers at that position; 'Change needed' is now 'Roster
  alert', 'What changed' is now 'News feed'; a screen that hits a problem shows a card with Reload instead of going
  blank." Its older entries (lines 110, 143) name "What changed" as history — leave them.
* Console pages: none carries "Change needed" or the news block's "What changed" (grep of `app/`).
* **The view**: the next nightly rebuilds `mart_league_roster_horizon` with `league_lab_now()` (production behaviour
  unchanged); on this sandbox `uv run league-lab dbt run --select mart_league_roster_horizon` then the five tests.

## Edits outside my files

`api/league_lab_api/decisions.py` (`_sid` "None"; `_alt_player`; `od_transactions`, `recent_adds` — six lines, marked),
`api/league_lab_api/db.py` (`pinned_now`, `_run`), `dbt/macros/league_lab_now.sql` (new),
`dbt/models/marts/edge/mart_league_roster_horizon.sql` (one line + comment), `web/src/App.svelte` (IN-1's: a script
block + two boundary blocks, marked), `web/src/lib/api.ts` (types at the end, marked), `web/src/components/TopBar.svelte`
(IN-2's: one key), 17 unowned screens / components (one key each), `docs/WORDS.md`, `CHANGELOG.md`, docs above.
No new env variable, no new dependency, nothing written to the database.

## Limitations / next

* The deadline is the roster's main slate, not the free agent's own kickoff (a Monday-night quarterback can be added
  later); the words say "before".
* The Streamlit twin and the root package's own database layer do not send `league_lab.now` (the root suite's four
  week-state failures may have the same cause: not checked).
* Next: the owners' one-line keys above; the view rebuild and the five tests; a real Sleeper lineup with two open spots
  once one exists in the fixtures.
