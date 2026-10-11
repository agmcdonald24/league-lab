# IZ-3 — the card says what he means for your roster (Wave I-Z)

Start 19:19 ET, end 19:43 ET (2026-10-11). Branch `dev/IZ3` from `integ/IZ`, worktree `/home/claude/wt-iq4`, database
`league_lab_iq4`. Ports 8922 (this branch's API on the database at Thursday 8 October 16:00 UTC, week 5, providers on
the local fixtures, outside calls refused by a dead proxy; for the screens), 8927 (e2e).

## 1. Done / not done / cut

* **Done — 1. One line of what he means for this roster** (`player.roster_line`, answered as `roster_line {kind, words,
  …}` on `/api/player/{gsis}?league=&team=`), right under the forecast. The cases: starts for you at a slot and by how
  much over the next man (or "nobody on your bench can take his place"); on your bench behind whom (or "his game has
  started"); can't play for you (My Week's own reason); a free agent who would start over whom and by how much this
  week (or in a spot nobody on your roster can fill); a free agent who would not (the lowest starter where he could
  play and his number); on another team (whose: the name the Availability section shows). No league (a reference
  scoring): nothing. A failure of My Week's lineup never costs the card (no line, 200).
* **Done — 2. At most three reasons** (`player.reasons`): role (the Role section's headline when it calls a change or a
  steady role; too early to call: his share of his group's targets and carries and of its points), matchup (the
  projection's "Next:" line, 1 = gives up the most), form (points per game against what his work was worth, the Value
  section's numbers). One sentence each, each ending where to read more (Usage, the schedule below, Game log); a reason
  with nothing to say is left out ("too early" with no shares; an unknown points per game).
* **Done — 3. The Overview's order**: head (forecast) → why → roster line → reasons → status (Availability with the
  news line, now once, above the actions) → actions; the sections below stay. Full page: head → roster line → reasons.
* **Done — 4. Both league paths, drawer and full page, 375 and 1300** (e2e live walk: League of Scrubs team 2 and MFL
  70587 team 1 on local fixtures).
* Not done: nothing cut.

## 2. Commits

`10af95e` the answer's roster line and reasons · `afba4a4` the Overview and the full page · `806825c` the role reason
when a change is too early; another team named · `5098c3e` tests · `480f4e9` on demand: another team named as
Availability does · `eeb75fb` e2e · `4bf5903` words, CHANGELOG, screens · (this hand-back).

## 3. Evidence

Where each number comes from (every one is shown elsewhere on the card or on My Week's "Recommended lineup"):
starter's slot, margin and the next man = My Week's lineup row (`slot`, `margin`, `margin_vs`); bench "behind" = My
Week's starters at his position; can't play = My Week's row `flag`; a free agent's gain = the card head's projection
(`proj_points`) minus the displaced starter's My Week `value` (the lowest starter whose slot admits his position, the
slot label My Week's); another team = the member row the Availability section names (house: `dim_league_member`; on
demand: the card's `rostered_by_team`, else the Availability text). Reasons = the card's own Role, projection ("Next:")
and Value sections.

League of Scrubs, team 2 (MacZaddy), week 5, clock Thursday 8 October 16:00 UTC, on `league_lab_iq4`:

| Case | Player | Roster line | Reasons (role · matchup · form) |
|---|---|---|---|
| starts | Kyren Williams (RB, 19.1) | Starts for you at RB1 this week; nobody on your bench can take his place. | 63% of his team's RBs' targets + carries, 77% of their points (wk 1–4) · vs BUF, #6 of 32 vs RB · 19.8 ppg on work worth 16.1 |
| bench | Justin Jefferson (WR) | On your bench this week; his game has started. | 30% / 43% (wk 1–3) · @ NO, #21 vs WR · 12.8 ppg on 8.9 |
| FA would start | Jacoby Brissett (QB, 20.2) | A free agent: he would start for you at QB, a spot nobody on your roster can fill this week (+20.2 this week). | 100% / 100% · vs DET, #1 vs QB · 15.8 ppg on 21.6 |
| FA would not | Ashton Dulin (WR, 3.4) | A free agent who would not start for you this week: Parker Washington, your lowest starter where he could play, projects 11.7. | 15% / 9% · @ PIT, #23 vs WR · 2.2 ppg on 3.7 |
| another team | Ja'Marr Chase (WR, 11.5) | On another team: Negrodamus (mjhend93). | 23% / 26% · @ MIA, #30 vs WR · 12.4 ppg on 10.0 |

My Week's rows those agree with: RB1 Kyren Williams 19.12, margin 19.12 with no reserve named ("no eligible reserve");
QB and TE "EMPTY: nobody can play"; WR2 Parker Washington 11.66; Jefferson "game started (bench)". On demand (MFL 70587
team 1, fixtures): Luther Burden III "Starts for you at WR/TE 1 this week, 1.2 points ahead of Robinson." (My Week:
WR/TE 1, 8.36, margin 1.2 vs Robinson); Chase "On another team: Klaby Crew." Reference scoring: no line, 3 reasons.

Screens (`docs/handbacks/iz3/`, JPEG q70, phone 375 and desktop 1300, drawer and full page): `iz3_house_starter_*`,
`iz3_house_fa_*`, `iz3_mfl_starter_*`, `iz3_mfl_other_*`.

## 4. Tests

* `api/tests/test_iz3.py`: **10 passed** — the five cases on hand-built rows (starter with and without a next man,
  bench behind whom, can't play, a free agent over a named starter / into an empty spot / who would not, another team
  by name on demand and from the Availability text, no lineup → no line), the reasons (three at most, each "More …",
  one with nothing to say left out), and on the database: **the line agrees with My Week's "Recommended lineup"** on
  both house leagues (League of Scrubs team 2, Forever Unclean Dynasty team 12: slot, margin, next man, bench names,
  each free agent's slot and gain against My Week's value), another team's player named as Availability does, the
  reference scoring without a line.
* The API test files of the card's route (29 files, outside calls refused): **440 passed, 37 failed, 10 skipped**; 31
  of the failures are on `/home/claude/waveIP/known_api_failures.txt`; the other 6 (`test_anyleague` on-demand lineup
  vs the mart ×3, `test_ig2` ×3 on PlayerWire briefs and the matchup evidence's names) also fail or error on
  `integ/IZ`'s own code against this copy (run from a scratch export); none reads the card's new fields.
* e2e (fixtures): `ip4`, `il1`, `if4`, `ii2`, `n1`, `n2` **68 passed** unchanged; `web/e2e/iz3` **4 passed** (fixture
  mode) and **8 passed** (live on 8922: house and MFL, drawer and full page, phone at 375 and desktop at 1300).
* `npm run lint` 0 errors; `npm run build` ok; `copy_standard.py --check` clean; ruff clean.
* `scripts/gate.sh python` last: **GATE PASSED** (src 783 passed, api 40 passed, ruff).

## 5. Edits outside my files

None. No PO-owned file touched.

## 6. PO lines

* The pinned specs (`web/e2e/ip4`, `il1`, `if4`, `ii2`, and `n1`, `n2` which read the news line) pass unchanged, 68 of
  68: they check each part is there, not status-before-actions, so nothing needed updating; `web/e2e/iz3` now pins the
  new order (drawer and full page).
* The house card answer did not carry the owner's team name (only the Availability text): the line reads it from the
  same member row; on demand, from `rostered_by_team` or the Availability text.

## 7. Found, not mine

* **An outside call, refused:** one check of the MFL path through the API with no provider fixtures set tried
  MyFantasyLeague and the proxy refused it (403); nothing came back. Every run after that set the MFL / Sleeper / ESPN
  fixture directories and a dead proxy, so nothing could leave the machine. The earlier house-league runs (the five
  cases above) set no dead proxy.
* On this copy at Thursday's clock, My Week's stored lineup marks team 2's reserves "game started (bench)" and two
  starters "locked (game started)" while the card's Availability says week 5 is "not locked yet" (the lineup was
  built after kickoff). With the ESPN fixture overlay on, Jefferson's line reads "Can't play for you this week (OUT)."
  (My Week's own flag).
* `test_anyleague` (on-demand lineup vs the mart) and three `test_ig2` tests fail on `integ/IZ` against this copy
  (above).

## 8. Next

* A bench line with names ("behind …") and a free agent "over" a named starter are tested on hand-built rows; on this
  copy at Thursday's clock, team 2's stored lineup has no bench rows (its reserves are "game started (bench)") and its
  empty QB and TE take any free agent at those spots. Worth a look on a fresh lineup build.
* The reasons could link straight to the tab they name (Usage, Game log) rather than say it.
