# JB-4 — the card explains "points over expected" (Wave J-B)

Start 10:47 ET, end 11:06 ET (2026-10-14). Branch `dev/JB4` from `integ/JB`, worktree `/home/claude/wt-iq4`, database
`league_lab_iq4` (read only). Ports 8932 (this branch's API: provider fixtures set, availability / usage / news off,
any other outside call refused by a dead proxy; for the screens), 8937 (e2e).

## 1. Done / not done / cut

* **1. One sentence on the card — done** (`api/league_lab_api/poe.py`, answered as `expected_line {kind, words,
  targets, carries, expected, actual, games}` on `/api/player/{gsis}`; drawer: the Usage tab, after the ratings, the
  game situations and the projected target share, above the Usage section's shares; full page: after the role chart and
  the situations). Season to date: his played regular-season games with an expected value, the four numbers summed over
  the same games (AGENTS rule 4); points from `research.league_games` — the Stats column's own source (the league
  mart for a house league, priced in the scoring for a reference key or an on-demand league). Rounded to whole points
  (halves up); the gap is in the verb ("he has 44" / "he has 79"). **The rule I picked:** a receiver (WR, TE) counts
  targets, a back (RB) carries + targets; under 20 of them: nothing; a quarterback: nothing (his expected points are
  mostly passing, which a count of targets or carries does not describe); a game without an expected value (or with
  its points unknown) is left out with its targets and carries; none left: nothing — never 0. The sentence never says
  why.
* **2. The How-to-read line — done.** The Stats column **Points over expected** now says depth of target, field
  position and down are allowed for, and the one caveat (a bad throw lowers his points, not his expected points);
  **Expected fantasy points** says how each target and carry is valued. **About has no expected-points paragraph**
  (nor a methods page): I said it in `docs/METRICS.md`'s expected-points row instead and did not add a new About
  section — the PO's call.
* **3. WORDS, tests, the card's e2e at 375 — done.**

## 2. Commits

`bd6e169` 1. the sentence (API + drawer + full page) · `62d57e7` 2. the How-to-read line, METRICS · `83bd6a3` 3. words,
tests, e2e, screens · (this hand-back).

## 3. Evidence

* **Michael Wilson (WR, ARI), weeks 1–4**, League of Scrubs: "His 44 targets usually bring about 64 points; he has 44.
  Depth of target is already allowed for." (44 targets, 63.8 expected, 44.3 actual, 4 games — the PO's numbers;
  `mart_league_player_season`: 63.83 / 44.30 / 4 games with an expected value). Forever Unclean Dynasty: "… about 77
  points; he has 57." Half PPR (`ref:half`): about 64; he has 44. MFL 70587 (fixtures): about 50; he has 32.
* Kyren Williams (RB), League of Scrubs: "His 54 carries and 25 targets usually bring about 64 points; he has 79.
  Depth of target and field position are already allowed for." Puka Nacua (21 targets in 2 games): "… about 32 points;
  he has 33." Colbie Young (rookie, under 20): no line. Lamar Jackson (QB): no line.
* The card's Value tile ("From past opportunities 16.0", −4.9) and the Game log chart's "on work worth 16.0" are the
  same numbers per game (63.8 / 4).
* Before → after, the Stats How-to-read for **Points over expected**: "… Positive: he scored more than his
  opportunities usually bring." → "… Positive: he scored more than his opportunities usually bring. Depth of target,
  field position and down are already allowed for: each target and carry is valued from its air yards, where on the
  field it came and the down, so short targets carry fewer expected points than deep ones. A bad throw lowers his
  points, not his expected points."
* Screens: `docs/handbacks/jb4/jb4_drawer_usage_{phone,desktop}.jpg`, `jb4_page_{phone,desktop}.jpg` (Wilson, live;
  phone at 375).

## 4. Tests

* `api/tests/test_jb4.py`: **7 passed** — a receiver's sentence (the sum, whole points, above and below), a back's,
  the thresholds (19 / 20 targets; 19 / 20 carries + targets; a QB, a kicker, no position), unknown is never 0 (no
  expected value: nothing; a game without one is left out with its targets; playoffs and games not played left out;
  halves up), a failure to read costs no card, Wilson on the database against `mart_league_player_season` (and each
  league its own scoring; a QB without a line), the Stats definitions.
* The test files of the card's route and of the Stats module (41 files, outside calls refused): **573 passed, 38
  failed, 10 skipped**; 37 of the failures are the known ones (`/home/claude/waveIP/known_api_failures.txt` and the
  six that fail on `integ/IZ` itself, IZ-3's hand-back); the new one is JB-3's, not this package's (§ 7).
* e2e (fixtures, phone and desktop): `ip4`, `ii2`, `iz3`, `ix3`, `jb4` **54 passed**, 10 skipped (the live walks);
  `jb4` live on 8932: **2 passed** (the screens).
* `npm run lint` 0 errors; `npm run build` ok; `copy_standard.py --check` clean; ruff clean.
* `scripts/gate.sh python` last: **GATE PASSED** (root 783 passed, api 40 passed, ruff).

## 5. Edits outside my files

`api/league_lab_api/main.py` (the card route: one marked block `# ---- JB-4`), `api/league_lab_api/stats.py` (two
column definitions, marked), `web/src/lib/api.ts` (one field on `PlayerCard`), `web/src/components/PlayerPane.svelte`
and `web/src/routes/Player.svelte` (one line each, marked), `docs/WORDS.md`, `docs/METRICS.md`, `CHANGELOG.md`.

## 6. PO lines

* None needed (no PO-owned file). If About should say it too: one sentence for its methods block — "Expected points
  value each target and carry from its air yards, field position and down, so a receiver on short routes is expected
  to score less than one on deep ones."
* The rule for the sentence (20 targets; a back's carries + targets; no quarterback) is in `poe.py`'s docstring and
  WORDS; change `MIN_TOUCHES` if you want another line.

## 7. Found, not mine

* `tests/test_io4.py::test_every_pool_carries_the_client_or_says_why_not` fails on this branch: "a thread pool that
  drops the request's client: [('api/league_lab_api/warm.py', 'on_publication')]" — JB-3's warm-up pool (on
  `integ/JB` already; this package does not touch `warm.py`). Either carry the client into that pool or list it with
  its reason in the test's allow-list.
* About has no expected-points paragraph (§ 1, item 2).

## 8. Next

* The sentence could name the league-wide comparison the PO quoted (aDOT 9.0 against 11.0 for NFL WRs) — the brief
  kept it out of the card; it belongs with the role lines if wanted.
