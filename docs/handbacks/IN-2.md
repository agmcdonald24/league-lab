# IN-2 hand-back — the lab without a league: scoring choices, a value for every player, the trade calculator

**Task**: Wave I-N, IN-2 (docs: `/home/claude/waveIN/BRIEF.md` § IN-2). **Branch**: `dev/IN2` from `main` `967b2d9`.
**Plan sections touched**: ANY_LEAGUE § reference keys, METRICS (a new definition, rv1.0), WORDS, CHANGELOG.

## Done, against the numbered list

1. **Scoring choices — done.** The key is a closed family: `ref:<ppr|half|std|espn|yahoo>[.sf][.tep][.p6][.t8|.t10|.t14]`,
   canonical, lower case, strictly parsed in one place (`platforms.parse_reference`, `ref_key`, `REF_KEYS`; the web's
   `lib/refleague.ts` `parseRef` is the same grammar). **160 valid keys** (5 scorings × superflex × TE premium × 6-pt pass
   TD × 4 sizes); 20 distinct scorings, 5 of them a fitted reference exactly (`ref:half` = `ref:yahoo` = `scrubs`,
   `ref:ppr`, `ref:std`, `ref:ppr.tep` = `te_premium`); the other 15 are priced on request with the nearest reference's
   range stretched (`anyleague.approximate_ranges`), and every answer's `pricing.words` says which ("Priced in Half PPR:
   the ranges are fitted for this scoring every night." / "Priced on request in ESPN default: … the nearest scoring we
   fit every night (PPR), stretched …"). ESPN default = PPR with −2 per interception; Yahoo default = Half PPR's offense
   exactly (−1 per interception) — a test per differing rule (receptions, interceptions) prices a stat line in both.
   The picker (`components/scoring/ScoringPicker.svelte`, where the league picker is): scoring with its rule line, the
   Sleeper sentence, superflex / TE premium / 6-pt pass TD, 8 / 10 / 12 / 14 teams; "PPR +2" on a phone; the choice is in
   the URL (`league=`) and remembered on the device (`prefs.refKey` / `ll.scoring`, try/catch; never `ll.league`);
   **Open your league** stays beside it. "No league" is gone: the API's `league_name` for a reference key is the key in
   words ("Half PPR", "PPR · superflex · 10 teams"), `platforms.SHORT/LONG["reference"]` = "Any league".
   Caches: a key's priced weeks and rest of season are keyed by its scoring (`Shape.scoring_key`: ≤ 20 entries for 160
   keys); the value tables live in a new memo region `ref_values` (≤ 24 keys, 10 minutes, ~0.3 MB a key); `shape()`
   refuses every key outside `REF_KEYS` before any cache is read (tested: a hostile key is 404 and never an entry).
2. **A value for every player without a league — done.** `refleague.values_from` (one function): season points over
   the league path's market window (this week → week 18, `anyleague.ros_table`) minus the replacement level of a
   *typical league of the chosen shape* (T teams start QB, 2 RB, 2 WR, TE, FLEX, SUPER_FLEX if superflex, K, DEF; FLEX /
   SUPER_FLEX filled from the best left; bench 6 a team over QB/RB/WR/TE in proportion to the starting spots).
   docs/METRICS.md § "Value without a league" (rv1.0, registry row `reference_value`). Shown on: the pane and the player
   page (the Value block leads with "**Value 153** — WR1 by value: 281 projected points over weeks 4–18, against 128 for
   the best free WR (Tre Harris)." and "Value in a 10-team PPR league, two quarterbacks (superflex): …"), the **Stats
   table** (a `Value` column beside the points in every preset, sortable, in the CSV; sorted by value the server sorts
   before it cuts the page), and **Compare** (a "Value (a typical league)" row).
3. **The trade calculator with no league — done.** `GET /api/trade-calc/free?league=&give=&get=` (`freetrade.py`,
   `research` bucket; gsis ids `^00-\d{7}$`, ≤ 6 a side, one side per player, 400 / 404 in words); the Trades tab opens
   it when browsing (`/trades?league=ref:…` redirects there; never the invitation card). Two sides by search; per player
   value, rank by value, this week's projection and range, per game over the season left; per side the value and the
   80% range of its season points; the gap in words with its 80% range ("You get more: 188 points of season value
   (likely +120 to +256)." / "About even: …, inside the uncertainty"), how much of it is one player, the roster-spot
   effect stated (one replacement-level player, 0 above replacement, not added), "Open your league to see what this
   does to your lineup." Shareable by URL; Swap sides. **The league calculator's path, payloads and tests are unchanged**
   (TradeCalc.svelte wraps its markup in `{#if isRef(league)} <FreeTrade/> {:else} …unchanged… {/if}`; the e2e suites
   of the league calculator, Trades, the drawer and the navigation pass untouched: 118 + 34).
4. **The pane and the player page while browsing — done.** Head: the key in words ("PPR · superflex · 10 teams · week
   4"); the value block (2); every "rostered by / free agent / your team" line is absent (header, Availability, Value,
   search hits' "· free agent", the How-to-read bullets rewritten for browsing, "League of Scrubs scoring" → "Half PPR
   scoring" in the matchup evidence); the foot: "Open your league to see who has him and what he is worth to your
   team." (the page: "Priced in PPR · superflex · 10 teams." before it; its Back says "Players").
5. **Tests and docs — done.** `api/tests/test_in2.py` (39), e2e `web/e2e/in2/fixtures.spec.ts` (4 walks × 375 / 1300,
   recordings `web/fixtures/in2/api_in2.json`), ANY_LEAGUE § "The family of reference keys", METRICS § "Value without a
   league", WORDS § "The lab without a league", CHANGELOG.

Also (small, in my files): the reference league now has a typical bracket (6 playoff teams, 4 at 8 teams), so a card's
"Rest of season" runs to week 17 (16), where IM-3's ran to week 15 (`playoff_teams` was missing → one round).

**Not done**: nothing on the list. Not in scope / left: draft picks; ESPN's and Yahoo's own K / DEF tables (the seed's
are used, said in the picker data and ANY_LEAGUE); App.svelte's invitation card (IN-1's file) still reads "You are
browsing without a league, in {refLabel(league)} scoring" — with a shaped key that reads "in PPR · superflex · 10 teams
scoring": IN-1 should use `refScoringLabel(league)` (exported).

## Files

Mine: `api/league_lab_api/refleague.py`, new `api/league_lab_api/freetrade.py`, `src/league_lab/platforms.py` (the
reference block + `check_key`), `web/src/lib/refleague.ts`, `web/src/lib/prefs.ts` (one marked block),
`web/src/components/TopBar.svelte`, `web/src/components/PlayerPane.svelte`, `web/src/routes/Player.svelte`,
`web/src/routes/Trades.svelte`, `web/src/routes/decisions/TradeCalc.svelte` (the branch only), new
`web/src/components/scoring/{ScoringPicker,FreeTrade}.svelte`, new `api/tests/test_in2.py`, new `web/e2e/in2/`,
`web/fixtures/in2/`, `docs/handbacks/in2/*.png`, this file.

Edits outside my files (marked `IN-2`): `api/league_lab_api/main.py` (the player card hook; `/api/players` and
`/api/players.csv` hooks for the value column; `/api/compare` hook; the router registration after IM-5's),
`api/league_lab_api/ratelimit.py` (`RESEARCH_EXACT |= {"/api/trade-calc/free"}`), `web/src/lib/api.ts` (block at the
end), `web/src/routes/Players.svelte` (`ros_value` in the All preset's default columns; no "whose" chips while
browsing, even while loading), `web/src/routes/Compare.svelte` (one row), `dbt/seeds/metric_registry.csv` (one appended
row, IN-6's file this wave — the root test `test_every_documented_metric_has_a_registry_row` needs it; no dbt run),
`api/tests/test_im3.py` (one expected string, on purpose: `league_name` "No league · Half PPR" → "Half PPR"),
`web/e2e/im3/fixtures.spec.ts` (on purpose: the picker instead of the select; My Team / Waivers are not tabs while
browsing and Trades is the calculator), `docs/WORDS.md` (the two IM-3 rows pointing here + a section),
`docs/ANY_LEAGUE.md`, `docs/METRICS.md`, `CHANGELOG.md`.

## Schema in / out

No new relation, nothing written to the database. Reads: `analytics_seeds.reference_scorings` (or the seed file),
the NFL-wide board through `anyleague.ros_table` / `price_week`, `analytics.dim_game`, `analytics.dim_player` (names of
unknown ids). Out: `GET /api/trade-calc/free` → `{league_id, league_name, scoring_label, assumes, value_words, pricing
{fitted, reference, words}, window {first, last, words}, give / get {players [{gsis_id, player_name, position, team,
value, ros_points, ros_p10, ros_p90, value_rank_pos, pos_rank, replacement, outlook {week, points, p10, p90, bye,
per_game, games}, no_projection}], n, value, ros_points, low, high, sd, unknown}, verdict {even, lean, gap, low, high,
one_player, words}, roster_spots {you_get_back, replacement_points, replacement_position, replacement_name, words} |
null, league_words, max_side}`. Additive on reference keys only: the player card's `ref_value`, `foot`, `scoring`;
the Stats frame's `ros_value` + catalogue entry + preset column; `/api/compare`'s `a.ros_value`, `b.ros_value`,
`value_assumes`. Real leagues: no field changed.

## Commands and evidence

* `cd api && OMP_NUM_THREADS=1 uv run pytest -q tests/test_in2.py` → **39 passed**; the existing files of the modules
  I edited: `tests/test_im3.py tests/test_ik4.py tests/test_im4.py tests/test_ik3.py` → **143 passed** (im3 again after
  the last change: 63 passed).
* `/home/claude/waveIN/check_root.sh /home/claude/wt-in2` → 4 failed (the known list), 1462 passed, **0 new**.
* `uv run ruff check src app tests api` → clean; `uv run python scripts/copy_standard.py --check` → clean;
  `cd web && npm run lint && npm run build` → 0 errors, 0 warnings, built.
* e2e (`FIXTURES_PORT=8720 npx playwright test --config playwright.fixtures.config.ts …`): `e2e/in2` **8 passed** on the
  recordings and 8 passed live against the fixture API (`IN2_LIVE=http://localhost:8762`); `e2e/im3` 9 passed (1
  desktop-only skip); the suites that touch the calculator, the tabs, the pane — `decisions ia2 ib1 ib2 ie0 ie1 ie2 if2
  ig1 ii1 ii2 inf1` — **118 passed**; `e2e/fixtures.spec.ts` **34 passed**.
* Screenshots (375 × 812 and 1300 × 900): `docs/handbacks/in2/in2-{picker,stats,pane,pane-value,player,calc}-{phone,
  desktop}.png` — no sideways scroll at 375 (asserted); at 1300 the picker is a panel under the bar, the calculator's
  sides sit side by side, the Stats table uses the width with the pane beside it.
* Timings on this box (fixture API, 2 cores shared by six): the free calculator **cold 1.67 s** for a scoring priced on
  request in a cold process (`ref:espn.sf.t14`), 0.56 s for `ref:half`, **warm 10–20 ms**; a browsing player card
  cold 2.47 s / warm 0.27 s; the Stats frame with the value column cold 1.88 s / warm 0.45 s; `value_table` cold
  0.79 s, another shape of the same scoring 0.01 s. Memory: `ref_values` 0.9 MB after three keys; RSS 206 MB.

## The sanity table: the top 12 by value at each position, `ref:half` beside League of Scrubs

League of Scrubs is Half PPR, 10 teams, real rosters (its value: `MARKET_SQL` − `REPLACEMENT_SQL`, the trade
calculator's market score). **The season points are identical** for every skill player below (the reference prices
the nightly's own lines; two defenses differ by 0.2–0.4), so the values differ only by the replacement level. They rank
alike at RB and WR (Spearman 1.00), TE 0.98 and QB 0.90 (Scrubs' ties at 0); the level differs: Scrubs' waiver wire
holds better players than a typical league leaves free (QB Malik Willis 243.1, RB 107.8, WR 124.5, TE 111.3: real
managers roster by name, need and byes, not by our projection), so `ref:half` reads 24–34 points higher at RB / WR / TE,
and its top quarterbacks are worth 25–58 where Scrubs' are 0–28. **Where they do not rank alike**: K (Scrubs' best free
kicker, Cameron Dicker 129.9, is the best kicker projected: every kicker there is 0) and DEF (Spearman 0.48: values of
0–8 points, ties at 0 in Scrubs). `ref:half.t10` (the same size as Scrubs) sits between the two, as it should.

**QB** — replacement: `ref:half` 212.6 (Justin Herbert), `ref:half.t10` 221.7, Scrubs 243.1; Spearman `ref:half` vs Scrubs over these 12: 0.90

| player | season pts (ref) | season pts (Scrubs) | value `ref:half` | value `ref:half.t10` | value Scrubs |
|---|---|---|---|---|---|
| Patrick Mahomes | 270.7 | 270.7 | 58.1 | 49.1 | 27.7 |
| Dak Prescott | 266.1 | 266.1 | 53.5 | 44.4 | 23.1 |
| Kyler Murray | 256.9 | 256.9 | 44.3 | 35.3 | 13.9 |
| Josh Allen | 248.3 | 248.3 | 35.6 | 26.6 | 5.2 |
| Drake Maye | 243.4 | 243.4 | 30.8 | 21.7 | 0.3 |
| Malik Willis | 243.1 | 243.1 | 30.4 | 21.4 | 0.0 |
| Jacoby Brissett | 238.8 | 238.8 | 26.2 | 17.2 | 0.0 |
| Jared Goff | 237.8 | 237.8 | 25.2 | 16.1 | 0.0 |
| C.J. Stroud | 237.8 | 237.8 | 25.2 | 16.1 | 0.0 |
| Brock Purdy | 237.8 | 237.8 | 25.1 | 16.1 | 0.0 |
| Matthew Stafford | 237.4 | 237.4 | 24.8 | 15.7 | 0.0 |
| Deshaun Watson | 237.2 | 237.2 | 24.6 | 15.5 | 0.0 |

**RB** — replacement: `ref:half` 81.5 (George Holani), `ref:half.t10` 93.9, Scrubs 107.8; Spearman `ref:half` vs Scrubs over these 12: 1.00

| player | season pts (ref) | season pts (Scrubs) | value `ref:half` | value `ref:half.t10` | value Scrubs |
|---|---|---|---|---|---|
| Bijan Robinson | 283.4 | 283.4 | 201.9 | 189.5 | 175.6 |
| Jahmyr Gibbs | 249.4 | 249.4 | 167.8 | 155.5 | 141.6 |
| Jonathan Taylor | 232.7 | 232.7 | 151.1 | 138.8 | 124.9 |
| James Cook | 227.0 | 227.0 | 145.5 | 133.1 | 119.3 |
| Christian McCaffrey | 221.0 | 221.0 | 139.5 | 127.2 | 113.3 |
| Kyren Williams | 217.1 | 217.1 | 135.5 | 123.2 | 109.3 |
| Javonte Williams | 213.2 | 213.2 | 131.6 | 119.3 | 105.4 |
| Derrick Henry | 212.7 | 212.7 | 131.2 | 118.8 | 104.9 |
| Kenneth Walker III | 210.8 | 210.8 | 129.3 | 116.9 | 103.1 |
| Ashton Jeanty | 204.1 | 204.1 | 122.5 | 110.2 | 96.3 |
| Chuba Hubbard | 190.5 | 190.5 | 109.0 | 96.6 | 82.8 |
| Jaylen Warren | 189.2 | 189.2 | 107.6 | 95.3 | 81.4 |

**WR** — replacement: `ref:half` 90.2 (Kendrick Bourne), `ref:half.t10` 103.2, Scrubs 124.5; Spearman `ref:half` vs Scrubs over these 12: 1.00

| player | season pts (ref) | season pts (Scrubs) | value `ref:half` | value `ref:half.t10` | value Scrubs |
|---|---|---|---|---|---|
| Puka Nacua | 230.0 | 230.0 | 139.8 | 126.8 | 105.4 |
| Chris Olave | 220.2 | 220.2 | 130.0 | 117.0 | 95.6 |
| Amon-Ra St. Brown | 216.0 | 216.0 | 125.8 | 112.8 | 91.5 |
| Jaxon Smith-Njigba | 208.2 | 208.2 | 118.0 | 105.0 | 83.6 |
| CeeDee Lamb | 206.1 | 206.1 | 115.9 | 103.0 | 81.6 |
| Drake London | 193.4 | 193.4 | 103.2 | 90.2 | 68.9 |
| Davante Adams | 191.4 | 191.4 | 101.2 | 88.2 | 66.9 |
| Nico Collins | 190.9 | 190.9 | 100.7 | 87.7 | 66.4 |
| Michael Wilson | 188.2 | 188.2 | 98.0 | 85.0 | 63.7 |
| Tee Higgins | 183.4 | 183.4 | 93.2 | 80.2 | 58.9 |
| Tetairoa McMillan | 180.9 | 180.9 | 90.7 | 77.7 | 56.3 |
| DeVonta Smith | 176.4 | 176.4 | 86.2 | 73.2 | 51.9 |

**TE** — replacement: `ref:half` 86.9 (Tyler Higbee), `ref:half.t10` 99.1, Scrubs 111.3; Spearman `ref:half` vs Scrubs over these 12: 0.98

| player | season pts (ref) | season pts (Scrubs) | value `ref:half` | value `ref:half.t10` | value Scrubs |
|---|---|---|---|---|---|
| Trey McBride | 180.9 | 180.9 | 94.0 | 81.8 | 69.6 |
| Brock Bowers | 148.7 | 148.7 | 61.8 | 49.6 | 37.4 |
| Tucker Kraft | 138.9 | 138.9 | 52.0 | 39.8 | 27.6 |
| Sam LaPorta | 133.5 | 133.5 | 46.6 | 34.3 | 22.1 |
| Tyler Warren | 127.4 | 127.4 | 40.5 | 28.3 | 16.1 |
| Travis Kelce | 116.1 | 116.1 | 29.2 | 16.9 | 4.7 |
| George Kittle | 116.0 | 116.0 | 29.1 | 16.9 | 4.6 |
| Dalton Schultz | 113.7 | 113.7 | 26.8 | 14.6 | 2.4 |
| T.J. Hockenson | 111.3 | 111.3 | 24.4 | 12.2 | 0.0 |
| Cade Otton | 110.0 | 110.0 | 23.1 | 10.9 | 0.0 |
| Harold Fannin Jr. | 108.6 | 108.6 | 21.7 | 9.5 | 0.0 |
| Dalton Kincaid | 107.2 | 107.2 | 20.3 | 8.1 | 0.0 |

**K** — replacement: `ref:half` 112.6 (Andre Szmyt), `ref:half.t10` 113.7, Scrubs 129.9; Spearman `ref:half` vs Scrubs over these 12: —

| player | season pts (ref) | season pts (Scrubs) | value `ref:half` | value `ref:half.t10` | value Scrubs |
|---|---|---|---|---|---|
| Cameron Dicker | 129.9 | 129.9 | 17.3 | 16.2 | 0.0 |
| Ka'imi Fairbairn | 126.7 | 126.7 | 14.1 | 13.0 | 0.0 |
| Daniel Carlson | 123.2 | 123.2 | 10.6 | 9.5 | 0.0 |
| Nick Folk | 122.1 | 122.1 | 9.5 | 8.5 | 0.0 |
| Will Reichard | 121.5 | 121.5 | 9.0 | 7.9 | 0.0 |
| Dominic Zvada | 120.7 | 120.7 | 8.1 | 7.0 | 0.0 |
| Chase McLaughlin | 118.9 | 118.9 | 6.3 | 5.2 | 0.0 |
| Chris Boswell | 117.7 | 117.7 | 5.1 | 4.0 | 0.0 |
| Jason Myers | 115.4 | 115.4 | 2.8 | 1.8 | 0.0 |
| Brandon Aubrey | 114.0 | 114.0 | 1.4 | 0.3 | 0.0 |
| Harrison Butker | 113.7 | 113.7 | 1.1 | 0.0 | 0.0 |
| Matt Gay | 113.0 | 113.0 | 0.4 | 0.0 | 0.0 |

**DEF** — replacement: `ref:half` 103.9 (Tampa Bay Buccaneers), `ref:half.t10` 104.9, Scrubs 111.5; Spearman `ref:half` vs Scrubs over these 12: 0.48

| player | season pts (ref) | season pts (Scrubs) | value `ref:half` | value `ref:half.t10` | value Scrubs |
|---|---|---|---|---|---|
| Seattle Seahawks | 112.2 | 112.2 | 8.4 | 7.4 | 0.7 |
| Houston Texans | 111.2 | 111.2 | 7.4 | 6.4 | 0.0 |
| Washington Commanders | 111.1 | 111.5 | 7.2 | 6.2 | 0.0 |
| Jacksonville Jaguars | 109.2 | 109.2 | 5.3 | 4.3 | 0.0 |
| Cleveland Browns | 108.2 | 108.2 | 4.3 | 3.3 | 0.0 |
| Pittsburgh Steelers | 107.9 | 107.9 | 4.1 | 3.1 | 0.0 |
| New Orleans Saints | 107.4 | 107.4 | 3.5 | 2.5 | 0.0 |
| Minnesota Vikings | 106.3 | 106.3 | 2.4 | 1.4 | 0.0 |
| New England Patriots | 106.1 | 106.1 | 2.2 | 1.2 | 0.0 |
| Atlanta Falcons | 106.1 | 106.1 | 2.2 | 1.2 | 0.0 |
| Carolina Panthers | 104.9 | 104.7 | 1.0 | 0.0 | 0.0 |
| Denver Broncos | 104.1 | 104.1 | 0.2 | 0.0 | 0.0 |

## Limitations

* The typical league is a model, not a market: no keeper costs, no draft picks, this season only; bench fixed at 6;
  K / DEF use the seed's kicking and defense rules for ESPN / Yahoo defaults.
* The calculator's 80% range reads each player's weeks as independent normals (the rest-of-season range's own
  assumption): a role change or an injury moves the weeks together, so the real range is wider (the card says so).
* A player card for a reference key carries two windows: "Rest of season" (to a typical league's final, week 17) in the
  Projection block and the value's "Points, wk 4–18" (the market window). Both are labelled.
* Kickers' and defenses' value rank like a typical league, not like Scrubs (above).

## The PO lines I need

* `app/whats_new.md` (yours): "- **Browse with your scoring.** Pick PPR, Half PPR, Standard, ESPN's or Yahoo's default,
  superflex, TE premium, 6-point passing touchdowns and the league size — every player gets a value, and the trade
  calculator works without a league."
* Nothing in `api/Dockerfile`, `render.yaml`, the workflows or the scripts (no new folder, no env variable).

## For whoever merges next to me

* IN-1 adds Home in TopBar: `refSections` orders browsing tabs Home · Players · Trades · DFS by section key (`home`
  first if that is its key); a section the list does not know goes last. IN-1's App.svelte invite line: use
  `refScoringLabel(league)` (above).
* Everyone: `refleague.label(key)` / `refLabel(league)` is the key in words (it may carry "superflex · 10 teams");
  for "… scoring" use `refScoringLabel` (web) / `refleague.shape(key).scoring_words` (API).

## Next task

Measure how far real leagues' scorings sit from the five fitted references (ANY_LEAGUE § "The ranges") now that 15
scorings are priced on request; a K / DEF reference for ESPN's and Yahoo's own tables.
