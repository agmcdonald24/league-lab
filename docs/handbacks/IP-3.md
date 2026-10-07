# IP-3 hand-back — grade what Trends and the role chips claim (Wave I-P, 2026-10-07)

**Task** Wave I-P, IP-3 (BRIEF § "IP-3"). **Branch** `dev/IP3` (from `main` `e4b5eec`). **Database** `league_lab_im4`
(the only writer; `uv run league-lab context-record` run first, as asked, then mine). Every table below is in
docs/METRICS.md § "Trends and the role trend, graded" (cx1.1) in full.

## Done (the numbered list)

1. **Does "below expectation" bounce back?** Every QB–TE player-week of 2021–2025 and 2026 weeks 1–4 with the tag
   rebuilt from the games **before** the week, followed over his next 1, 2 and 4 games: (a) against the projection made
   before each game, (b) raw (points per game next against before); by gap tercile, position and the reason the app
   prints. **Done.**
2. **Does "role up / down" carry forward?** The share over the next 1 / 2 / 4 games (does it hold, in points of share)
   and the miss against the projection (is it priced), by position. **Done** (2021–2025: 2026 weeks 1–4 have no call —
   the trend needs four games before the week).
3. **On the screens.** `summary()["trend"]` / `["role"]` (frozen and graded weekly in the record), Trends' head line,
   new row / help words. The role chip's sentence is below for the PO to place (DFS / Stats files not touched). **Done.**
4. Tests on hand-built rows, the freeze idempotent, `summary()` without the tables and with Wave I-O's shape; METRICS
   cx1.1 + 3 registry rows; WORDS; CHANGELOG. **Done.** No dbt model changed (rule 10); the registry seed rebuilt.

## The look-ahead finding

* **Trends' tag is never stored for a past week**: `mart_league_player_season.diff_per_game` (and `mart_player_trend_tags`)
  hold the season as it stands now — a past week read from them (or Trends with a past `season=`) has the week itself
  and every later game inside it. Clean for the next week to play. **What I did**: rebuilt the tag per past week from
  the games before it (`context_record.asof_trend` / `trend_asof_week`; test: a week's own game never enters its tag).
* The reason's "his quarterback changed" reads `pn_qb_changed` for the week itself (a projection input built before
  kickoff: as-of). Expected points are ffverse's per-game model of each game's own plays (not refitted by us).
* The projections graded against: 2023–2025 `ops.calibration_oof` (walk-forward v3.0); **2021–2022 projected
  walk-forward tonight in memory** with today's code (v3.3, fitted on 2016 to the season before; nothing stored);
  2026 weeks 1–3 the post-kickoff `refit` (IO-1's caveat), week 4 the kickoff board. Two model versions are mixed.

## The grade (Half PPR; 95% bootstrap resampling whole player-seasons; vs the rest = other tagged player-weeks, same positions)

| | Next | n | Raw pts/g next − before | vs the rest against the projection |
|---|---|---|---|---|
| below | 1 / 2 / 4 | 11,129 / 9,840 / 7,607 | +1.19 (+1.07 to +1.32) / +1.30 / +1.45 | **−0.27 (−0.43 to −0.12)** / −0.23 (−0.38 to −0.07) / −0.18 (−0.35 to −0.02) |
| above | 1 / 2 / 4 | 7,687 / 6,921 / 5,516 | −1.54 (−1.69 to −1.39) / −1.57 / −1.60 | **+0.36 (+0.17 to +0.53)** / +0.31 (+0.13 to +0.49) / +0.30 (+0.12 to +0.49) |

By size (next game, vs rest): below small −0.25, middle −0.18 (holds 0), large −0.39; above small +0.16 (holds 0),
middle +0.40, large +0.50. By position: below QB +0.18 (holds 0), RB −0.51, WR −0.21 (holds 0), TE −0.39; above QB −0.25
(holds 0), RB +0.59, WR +0.45, TE +0.22 (holds 0). By reason: below touchdowns −0.37, quarterback −0.61, share fell
−0.71, none −0.07 (holds 0); above touchdowns +0.70, quarterback −0.09 (holds 0), share rose +0.42, none +0.23.
**By season the direction is not steady**: below 2021 −0.76, 2022 −0.01, 2023 −0.41, 2024 −0.40, **2025 +0.22 (−0.14
to +0.55)**, 2026 −0.17; above 2021 +0.53 … 2024 +0.64, **2025 −0.17 (−0.51 to +0.18)**. **The record (2025 and 2026
weeks 1–4, what the site prints)**: below +0.17 (−0.15 to +0.49, 2,467), above −0.15 (−0.45 to +0.15, 1,815) — **no
measurable difference**. Subsets: 22 pre-registered (66 cells) + 4 check cells; every subset clear of 0 pooled comes
from 2021–2024 and none holds in 2025–26 (e.g. above × touchdowns +0.98 then −0.22) → **no row marked**.

**Role** (2021–2025): over the next two games a role up keeps 42% of its target-share move (+3.7 of +8.7 points, +3.4 to
+4.0), 60% of carry share (+12.2 of +20.3), 70% of snap share (+15.0 of +21.3); a role down 41% / 62% / 58%. Priced?
Role up +0.29 against the rest the next game (+0.07 to +0.49, 5,133), +0.20 over two (+0.01 to +0.39), +0.12 over four
(holds 0); by season +0.69, −0.01, +0.59, −0.03, +0.21; TE +0.43 (+0.06 to +0.81) the only position clear of 0 (6
subsets, 18 cells; not marked). Role down −0.13 (−0.35 to +0.09): no measurable effect. The record (2025): role up
+0.22 (−0.21 to +0.64, 1,022) — none. The projection reads `*_share_l3` (the two recent games are two thirds of it) and
`*_std`: a two-game move is mostly in the number already.

## What the screens say now

**Trends, before** (main): head "**Below expectation: Jameis Winston** (getting the throws and runs of a 15.3-point player,
scoring 3.6). **Above expectation: Jaxon Smith-Njigba** (…). Points per game in Forever Unclean Dynasty scoring." —
picked row: "…: 4 touchdowns in 2 games on 6 red-zone targets. 19.4 above what his opportunities suggest: an observed
gap, not a forecast." — help: "That is what happened, not a forecast — the gap may close or not; a buy needs a price,
which this screen does not have." / API help: "Above = running hot, below = due."
**After**: the same head + under it "Graded on 2025 and 2026 weeks 1–4 (Half PPR): in their next game, players below
expectation scored 1.5 points more than their average before and players above it 1.9 less — and their projections
already expected that (no measurable difference against them; 4,282 games)." — row: "… 19.4 above what his
opportunities suggest: what happened, and his projection already counts it." — help: "Graded on past weeks, players
like him scored more the next week, about as much as their projection already expected: the gap is what happened, not
a reason to buy on its own — look at his projection." + "**Graded**: <the record's sentence>".

**The role chip (DFS, Stats — for the PO to place; exact sentence)**: "Graded on 2021–2025 (Half PPR): a two-game role
change kept about half of its move over the next two games (snaps 70%, carries 60%, targets 42%), and his projection
already counts most of it — after a role up players finished 0.3 points above the rest against their projection the
next game (+0.1 to +0.5; 5,133 games), not every season; after a role down, no measurable difference."

## Files

`src/league_lab/context_record.py` (IP-3 blocks: as-of tag, outcomes, study, record columns, backfill, grade rows,
sentences, `python -m league_lab.context_record study`), `api/league_lab_api/context_record.py` (`trend`, `role`),
`api/league_lab_api/research.py` (`TRENDS_HOWTO`, `record` on `/api/trends`), `web/src/routes/Trends.svelte`,
`web/src/lib/research.ts`, `docs/METRICS.md` (cx1.1), `dbt/seeds/metric_registry.csv` (3 rows), tests
`tests/test_ip3_trend_record.py` (13), `api/tests/test_ip3.py` (16), e2e `web/e2e/ip3/fixtures.spec.ts` (+
`web/fixtures/ip3/context_record.json`, 1.7 KB), screenshots `docs/handbacks/ip3/` (3 JPEG, 263 KB).
**Outside my files** (marked / minimal): `src/league_lab/db.py` (`migrate` creates the two record tables — see below),
`web/src/lib/api.ts` (types at the end), `api/tests/test_io1.py` (one assertion: the route's keys are now a superset,
changed on purpose), `docs/WORDS.md` (one dictionary row points to the new section + the section), `CHANGELOG.md`.

## Schema

`ops.context_record` + `trend_games`, `trend_ppg`, `trend_gap`, `trend_tag`, `trend_reason` (`alter … add column if not
exists` in the DDL every run executes; rows written before them filled once by `backfill_trend`). On im4: 9,358 rows,
11 MB on disk after the one-time rewrite (≈ +0.3 MB of data). `ops.context_grade` 21 → 192 rows, 80 kB (kinds `trend`,
`trend_raw`, `role`; `summary` `trend` / `trend_head` / `role`). No new relation. Neon: ≈ +0.4 MB once vacuumed.

## Commands and evidence

`uv run league-lab context-record`: Wave I-O's tables in 17 s, then with IP-3 (migration + backfill of 8,790 rows) 13 s,
then 8–18 s a night (was ≈ 3 s: the bootstraps). Study: 21 s for the frames + 80 s for the 2021–22 in-memory fit.
Tests: `tests/test_ip3_trend_record.py` 13 passed; `api/tests/test_ip3.py` + `test_io1.py` 24 passed;
`test_i0a test_i0b test_ia1 test_im3 test_io4 test_n1 test_research test_io1 test_ip3` 198 passed, 6 failed (4 in the
known list; 2 in `test_io4` that assume the database has no `ops.context_grade` — see below); `test_metric_registry`
3 passed; `dbt build --select metric_registry` PASS 3; ruff clean; copy standard clean; `npm run lint && npm run build`
clean; e2e `ip3` 6 passed, `ia1` 10, `im3` + `ib1` 19, `ih1` (Trends) 2; `check_root.sh` no new failures.

## Without my rows / tables

Wave I-O's tables only (the live site until the nightly): `summary()` answers `corner` / `worth` as before and `trend` /
`role` graded False; `/api/trends` `record.graded` false → no head line; the new help and row words show (code).
No tables: the same, `summary()` all four graded False. The first nightly migrates the table itself (no line needed).

## Not mine, seen

* **The nightly would stop on a fresh database** (main, IO-1): `STATE_TABLES` lists `ops.context_record` /
  `ops.context_grade`, `restore_state` runs `select count(*)` on each right after `db migrate`, and `migrate` did not
  create them; the Actions Postgres is a fresh service container. Fixed with a marked block in `src/league_lab/db.py`
  (`migrate` runs the record's DDL) — the PO's call; without it, put the same DDL before `hard restore-state`.
* `api/tests/test_io4.py::test_the_honesty_line_with_and_without_the_record` and `::test_the_week_context_carries_the_
  corner_as_information` assume "this database has no ops.context_grade": they fail on any database with the record.
* The **Trades screen's buy-low / sell-high lists** (`roster_value.trade_candidates`: PPG − xPPG < 0 / > 0) rest on the
  same gap this grade found already priced; the player card's help (`api/league_lab_api/player.py`: "above = running
  hot, below = due") says what Trends no longer says.
* For the model's owner, not acted on: 2021–2024 suggests the projection pulled hot players back further than they went
  (2025 does not) — a harness candidate, not a fact.

## The PO lines

None required in `scripts/nightly.sh` (IO-1's `context-record` line migrates, backfills and grades). `app/whats_new.md`,
if wanted: "Trends now says what its gap has meant: graded on past weeks, players below expectation scored more the next
week — about as much as their projection already expected. A gap is what happened, not a reason to buy on its own."

## Next

Grade the record's kickoff weeks from 2026 week 5 (the same rows, `record_source = 'kickoff'`); retire or regrade
Trades' buy-low / sell-high on this result.
