### IX-2 — the player card: who he is, a shorter Overview, his splits (Wave I-X, 2026-10-11)

Start 01:43 ET, end 02:40 ET. Branch `dev/IX2` from `integ/IX` (IX-1 at `07d73b0`), worktree
`/home/claude/wt-iq4`, database `league_lab_iq4`.

#### 1. Done / not done / cut

* **Done — who he is**: `bio` on the card's answer for every league kind and no league (the route adds it after the
  house or on-demand card): "6'0" · 205 lb · 26 years old · 6th season · LSU · 2021 · round 1, pick 5", under the
  name in the head (drawer and full page; none for a team defense). A missing fact is left out; a missing draft row is
  never printed "Undrafted" (the data cannot tell undrafted from unknown: Austin Ekeler has no draft row).
* **Done — the Overview** (drawer): the head (one forecast, with the bio), the reason, the actions, the sections. Out
  of the first view: the ratings (to Usage, **without their plain average** — removed from the full page too), the
  points chart (to Game log), the projection section's four tiles (the head carries the projection and its range;
  the full page keeps that one set). **Cut**: the "one line of what it means for this roster" and the "three evidence
  bullets" as new blocks — the Overview keeps today's sections (projection, role, availability with the news line,
  value, signals) below the head; not restructured into bullets for the clock.
* **Done — one role vocabulary**: the web no longer rewrites "no alert" into "role steady over N games" / "not enough
  games to say"; the signals section's no-alert sentence leaves; the Role section's words (roles.role_change: "Too early
  to say …", rising / falling / steady with the games) are the card's only role words; a fired alert still shows.
* **Done — Usage**: "By game situation" (targets, share, carries, share, with his team's plays behind each group; under
  20 plays: "too few to read" and no share; empty columns hidden: no carries column of zeros for a receiver) and the
  ratings. **The left-early mark** and **target share on the field** with its sample are on the Game log (each marked
  game, the closed kind, under 10 offensive snaps a dash and "too few snaps", the key saying 2026 is an estimate).
  **Not shown: the projected target share** — see § 7.
* **Done — the phone**: the card is a full-height sheet (375 × 900 at 0, 0) with its close button; closing returns the
  Players list to where it was (query, sort and scroll: 692 px before and after). Nothing to fix.
* **Cut**: a season "Target share on the field" value on Usage (the card's answer has no window value; IX-3's Stats
  row carries it).

**The situation groups (IX-3, use the same words)** — from `mart_player_context`'s five score-state buckets:
**When trailing** = his team behind by 9 or more (`trailing_9plus`) · **Within a score** = 8 points or fewer either
way, tied included (`trailing_1_8`, `tied`, `leading_1_8`) · **When leading** = his team ahead by 9 or more
(`leading_9plus`). Plays behind a group = his team's dropbacks + carries in it; under 20, "too few to read".

**The field for IX-3**: `/api/player/{gsis}/games`, per game, beside IX-1's `left_early` / `left_early_reason`:
**`left_early_kind`** (`"hurt"` | `"short"` | null) and **`left_early_words`** ("Left early: 15 snaps (20% of the
team's; usually 94%); hurt on a play in the 2nd quarter" / "Played far less than usual: 12 snaps (18% of the team's;
usually 80%)"), written in `onfield.left_early_case`. "hurt" only when the reason carries the play-by-play's injury
note (the one closed form `int_player_game_on_field` writes: "; hurt on a play in the …").

#### 2. Commits

`11e2516` (the answer: `bio`, `situations`, `left_early_kind` / `left_early_words`), `850d8c1` (the card: bio line, the
Overview, Usage, Game log), `5c559b8` (the specs updated on purpose, a defense's chart, WORDS, CHANGELOG), and the last
commit (the situations table's empty columns, screenshots, this hand-back).

#### 3. Evidence (League of Scrubs, `league_lab_iq4`, a Saturday clock)

* **Ja'Marr Chase's card** — bio: "6'0" · 205 lb · 26 years old · 6th season · LSU · 2021 · round 1, pick 5".
  By game situation, 2026: When trailing 0 targets (28 plays of his team's) · Within a score 25 targets, 24% (170
  plays) · When leading 3, 11% (56 plays). Game log: "Week 4: Left early: 15 snaps (20% of the team's; usually 94%);
  hurt on a play in the 2nd quarter. Target share on the field: 28% (whole game 6%; 15 snaps)."
* Michael Wilson: "6'2" · 213 lb · 26 years old · 4th season · Stanford · 2023 · round 3, pick 94"; When leading:
  "14 plays of his team's: too few to read" (no share shown). Joe Burrow: "… LSU / Ohio State · 2020 · round 1, pick 1".
* **Before → after, the drawer's first view**: head · reason · actions · **ratings with "average of 8"** · **points
  chart** · projection (**four tiles** + lines) · role ("Too early to say …") · availability · value · signals
  (**"Role: not enough games to say …"** / **"role steady over N games"** rewritten from "no role change detected") →
  head **with the bio line** · reason · actions · projection (lines only) · role · availability · value · signals (a
  fired alert only). Usage: ratings (no average) · By game situation · Usage. Game log: the points chart · the points
  by week · the marked games.
* **The projected target share is not on the card (PO decision 3)**: the teams' summed projected targets for the live
  week (week 5 on this copy, `ops.projection_lines`, by `dim_player.latest_team`): median **40.1**, max **50.3**, **15 of
  30 teams above 40** — against 29.4 / 30.2 / 32.8 / 32.6 real targets per team in weeks 1–4. Michael Wilson's own:
  "8.6 of his team's 45.8 projected targets". Left for IX-1's developer (§ 7).
* The phone: the card at 375 is a full-height sheet (0, 0, 375 × 900) with its close; closing it from the Players list
  (WR, sorted by target share, scrolled to the 26th row) leaves the query, sort and scroll as they were (692 → 692 at
  375; 592 → 592 at 1300).
* Screenshots (`docs/handbacks/ix2/`, JPEG q70, 375 and 1300): `overview_*`, `usage_*`, `gamelog_*` (Chase). No
  sideways scroll (scrollWidth 375 / 1300), no page errors.

#### 4. Tests

* New: `api/tests/test_ix2.py` 3 passed (the bio line and what it leaves out; the situations' three groups and the
  small-sample words; "Left early" only with the injury note, the plain fact otherwise).
* API files of the routes whose answer changed (`test_ix2`, `test_ix1`, `test_player`, **`test_parity`**, `test_ip4`,
  `test_research`, `test_ia3`, `test_if4`, `test_ie0`, `test_in2`, `test_ir4`, `test_il5`, `test_ig1`): 10 failed /
  197 passed / 1 skipped — **all 10 in the known list**, 0 new. `test_parity` passes (no console diff needed).
* `scripts/gate.sh python`: GATE PASSED (root 783, api 40, ruff). Ruff and the copy standard clean; `npm run lint` 0
  errors (210 files); the build. No `src/` or `dbt/` edit (no `check_root.sh`, no chain: nothing the nightly reads).
* **e2e** (the card opens from most screens): the whole fixtures suite on phone and desktop through `io3`, then the
  desktop folders after it (`io4` … `v2`): **585 passed, 9 failed, 21 skipped**. The 9 failures are the blog editor's
  (`io3` 175, 263, 278, 316, 392, 450, 555; `iu6` 213), all on "This account does not write on the blog": the fixture
  API here has no editor account; they open no card. Not run: `io3` 370+ and `iu6` on desktop (the same editor
  tests; the run was stopped while they timed out). **Specs updated on purpose**: `ip4` (no ratings average; the head
  is the only projection — no tiles in the Projection section; the drawer test now finds the ratings on Usage and the
  chart on Game log; a defense's chart on its Game log tab), `if4` (the signals section says neither "no role change
  detected" nor "not enough games to say" / "role steady"), `ii2` (the head's number instead of the projection
  section's "Typical range"). `il1` passed unchanged.

#### 5. Edits outside my files

`api/league_lab_api/main.py` (the card route: two lines in an `# ---- IX-2` block adding `bio` and `situations`);
`api/league_lab_api/onfield.py` (the closed kind, as the PO asked); `web/src/lib/api.ts` (three types and two optional
fields on `PlayerCard`, marked); `web/e2e/ip4`, `if4`, `ii2` (below); `CHANGELOG.md`, `docs/WORDS.md`.

#### 6. The PO's lines

None.

#### 7. Found, not mine

* **The projected target share's team total is far from a real game** (above): 15 of 30 teams project more than 40
  targets in week 5 against about 31 real; the denominator likely counts every projected player listed on a team
  (`dim_player.latest_team`), backups and the inactive included. Not shown on the card until IX-1's developer looks.
* **Chase's role alert reads his injury exit as a smaller role**: "Smaller role: Ja'Marr Chase — snap share 94% → 20%,
  target share 29% → 6% since week 4 (one game so far). Why: Mitchell Tinsley back." The alert detector does not read
  IX-1's left-early mark (IX-6's subject: the inputs).
* The e2e `io3` / `iu6` blog-editor tests fail on this worktree's fixture API ("This account does not write on the
  blog": no editor account in the recipe); they open no card. I did not run them on the base branch to compare.

#### 8. Next

The Overview's roster line and three evidence bullets as blocks of their own (cut here); a season "Target share on the
field" on Usage from IX-3's window fields; the alert detector reading the left-early mark.
