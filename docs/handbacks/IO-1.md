# IO-1 hand-back — grade the context, keep the record, weather (Wave I-O, 2026-10-06)

**Branch** `dev/IO1` (from `main` `cf8e743`). **Database** `league_lab_im1` (the only writer). Plan: Wave I-O,
IO-1 (BRIEF § "IO-1"); docs/METRICS.md § "The context record" (cx1.0) has every table below in full.

## Done (the numbered list)

1. **The corner calls, graded.** First what the call knew: `mart_cb_matchups`' call is clean (depth chart before
   kickoff, target sides before the week), **the corner's rank and quarter are look-ahead** for a past week (the mart
   joins `mart_cb_rankings` `two_seasons` *of that season*: the whole season as it stands, the week and later weeks
   included). 497 of 2,557 called 2025 receiver-weeks (19%) and 63 of 598 in 2026 weeks 1–4 (11%) carry a different
   quarter than the one known before the game. Built the as-of version (`context_record.cb_rank_asof`: same pool, same
   z-scores, same opponent adjustment, games before the week only); at season end it equals the mart exactly (2025 64/64
   ranks and quarters, 2026 69/69). The grade uses only the as-of quarter.
2. **"Worth a look", graded** — rebuilt per week through the screen's own `dfs.signals` / `dfs.worth` from as-of
   inputs (defense = `opp_rank_std` as the projection read it; role trend from games before the week, routes left out;
   the corner as in 1; weather = the last forecast kept before kickoff). **Not rebuilt as-of**: the betting line (nflverse
   keeps the closing line), 2025 weather (no forecasts kept: no weather signal in a rebuilt 2025 week), the availability
   overlay (a named corner out → "no call") and the list's "who cannot play" filter.
3. **The record.** `ops.context_record` (one row per player-week with a priced projection: the signals as shown,
   `worth` / `listed` under today's rule and `worth_corner` / `listed_corner` under Wave I-N's, the Half PPR projection
   at the freeze, `record_source` kickoff / reconstructed, `actual_points` / `miss` after the game) under
   `ops.lineup_record`'s freeze rule, and `ops.context_grade` (≈20 rows, replaced every run: what the site reads).
   `league-lab context-record`: idempotent, safe every night, never rewrites a frozen week.
4. **On the screen.** `api/league_lab_api/context_record.py` `summary()` (the fixed interface, + `corner.tiers`) and
   `GET /api/context/record` (`read` bucket). DFS: "Worth a look" prints the record's sentence instead of "no record
   behind this list yet"; the corner chip carries its quarter's graded words and loses its colour when the interval
   holds 0; **the rule changed** (below).
5. **Weather.** `analytics.mart_game_weather` (557 rows, 192 kB; key test + not_null + "a forecast is from before
   kickoff"); DFS reads it only when it exists; the chip shows the numbers ("Wind 20 mph"), dashed (not in the projection).
6. Tests, METRICS (cx1.0) + 4 registry rows, DFS.md, WORDS, CHANGELOG.

## The grade (Half PPR = `ref:half`; miss = actual − projected; 95% bootstrap resampling whole games, 2,000 draws)

Projections made before the game: 2025 walk-forward (`ops.calibration_oof`, v3.0 fit on 2016–2024); 2026 weeks 1–3
the v2.0 refit labelled `refit` (fitted after those weeks kicked off: as-of features, not a kickoff record), week 4 the
kickoff board. "vs rest" = the group's mean miss minus the other called receivers' (the projection's bias cancels).

| Certainty / quarter (as-of) | n | games | Mean miss (95%) | Scored above | vs other called receivers (95%) |
|---|---|---|---|---|---|
| likely shutdown | 99 | 72 | −0.59 (−1.58 to +0.42) | 35% | −0.39 (−1.39 to +0.72) |
| likely solid | 133 | 100 | +0.32 (−0.61 to +1.33) | 35% | +0.57 (−0.48 to +1.63) |
| likely easy to throw on | 79 | 61 | −0.23 (−1.32 to +0.95) | 39% | −0.02 (−1.11 to +1.22) |
| likely unranked | 160 | 109 | +0.60 (−0.32 to +1.56) | 43% | +0.88 (−0.02 to +1.80) |
| unclear shutdown | 323 | 166 | −0.58 (−1.17 to 0.00) | 33% | −0.43 (−1.05 to +0.21) |
| unclear solid | 516 | 229 | +0.17 (−0.32 to +0.71) | 43% | +0.50 (−0.05 to +1.12) |
| unclear easy | 271 | 141 | −0.76 (−1.40 to −0.05) | 33% | −0.63 (−1.35 to +0.08) |
| unclear unranked | 609 | 238 | −0.37 (−0.82 to +0.07) | 35% | −0.21 (−0.75 to +0.29) |
| every called WR | 2,190 | 335 | −0.21 (−0.47 to +0.04) | 37% | |

**No measurable effect** for a likely shutdown or a likely easy corner; easy corners (any certainty) did no better
than the rest (−0.51, −1.15 to +0.09). The only interval clear of 0 is the middle quarter (solid, any certainty,
+0.59, +0.10 to +1.12): no direction, 1 of 12 cells, not acted on. Standard scoring (2025, the same fit re-priced):
likely shutdown −0.19 (−1.10 to +0.72, 73), likely easy −0.58 (−1.50 to +0.42, 56) — the same answer.

**Worth a look (Wave I-N's rule, rebuilt)**: 38 listed receiver-games in 30 games, mean miss +0.35 (−1.39 to +2.34),
scored above in 15 (39%) vs everyone else at the position 998 of 2,883 (35%); **+0.66 against the rest (−1.11 to +2.62)**,
+0.58 against the rest projected 6+ (−1.25 to +2.62) — **not distinguishable from chance**. 2025 alone −0.58 (−2.05 to
+0.81, 29); 2026 weeks 1–4 +4.57 (−1.44 to +10.47, 9). All 38 leaned on a likely easy corner.

**What changed on the screen because of it**: the cornerback call **no longer counts toward "Worth a look"**
(`dfs.WORTH_IGNORES = {"corner"}`). It was the only signal both outside the projection and able to be favourable, so the
list is **empty** and says why ("Nobody this week. The one signal outside the projection that could put a player here,
the cornerback call, made no measurable difference when graded, so it no longer counts; …"). Chosen from the corner's
grade alone; no replacement rule was tuned on these weeks (one looked at and **not** adopted: two favourable signals
without the corner, all in the projection already — +0.37, −0.02 to +0.74, in-sample). The record keeps grading the old
rule (`worth_corner`) on weeks it has not seen. Two existing assertions changed on purpose:
`tests/test_in4_dfs.py::test_signals_carry_their_projection_label` (today's rule → not listed; `ignore=()` → listed as
before) and `api/tests/test_in4.py::test_board_with_the_matchup_signal` (the list is empty, `worth_empty` said, Wave
I-N's rule would list them); `test_board_with_context_and_no_matchup_module`'s forecast check is relation-aware.

## Weather

Marks unchanged (`dfs.weather_flag`: wind ≥ 15 mph, precipitation ≥ 0.1 in, snow, < 32 °F). Basis (2016–2025, observed
weather, per game): 7.13 yards per attempt under 10 mph (1,329 games), 6.79 at 15–20 (120), 6.16 at 20+ (24); rain
0.1 in+ 6.48 (90) vs 7.07. **Not in the projection**: v3 reads no `wx_` column (test). Ungraded (2025 kept no forecasts).
2026 week 5: 9 outdoor games with a forecast, 6 domes; Green Bay 20 mph, one game 0.13 in of rain.

## Files

`src/league_lab/context_record.py` (new), `src/league_lab/cli.py` (the `context-record` command, marked),
`src/league_lab/dfs.py` (`WORTH_IGNORES`, `worth(…, ignore=)`), `api/league_lab_api/context_record.py` (new),
`api/league_lab_api/dfs.py` (weather from the mart, the record's words, the graded corner), `dbt/models/marts/nfl/
mart_game_weather.sql` (new) + `matchups.yml`, `dbt/seeds/metric_registry.csv` (4 rows), `web/src/routes/Dfs.svelte`,
`web/src/components/dfs/{Context.svelte,dfs.ts}`, tests `tests/test_io1_context_record.py`, `api/tests/test_io1.py`,
`web/e2e/io1/fixtures.spec.ts` (+ `web/fixtures/io1/`), docs METRICS / DFS / WORDS / CHANGELOG, screenshots
`docs/handbacks/io1/`. **Outside my files** (marked blocks): `api/league_lab_api/main.py` (router), `ratelimit.py`
(`/api/context/record` → `read`), `CHANGELOG.md`, `docs/WORDS.md`, `api/tests/test_in4.py`, `tests/test_in4_dfs.py`.

## Schema out

`ops.context_record` (record; 8,790 rows, 5.6 MB on the sandbox: 2025 5,829, 2026 weeks 1–4 2,393, week 5 568 frozen;
≈ 570 rows / 0.35 MB a week → ≈ 10 MB by season's end), `ops.context_grade` (19 rows, 16 kB), `analytics.mart_game_weather`
(557 rows, 192 kB). ops is published whole; the mart reaches the hosted copy through `api/league_lab_api/dfs.py`'s name
(`scripts/hosted_relations.py` lists it). Neon: +≈ 6 MB now.

## Commands and evidence

`uv run league-lab context-record` — first run 31 s (22 weeks rebuilt), then 2–3 s ("kept [1..18]; written [5]").
`uv run league-lab dbt build --select mart_game_weather+` PASS 4; `--select metric_registry` PASS 3.
Tests: `tests/test_io1_context_record.py` 11 passed (incl. a rolled-back DB test of the freeze); `tests/test_in4_dfs.py`
75 passed; `api/tests/test_io1.py` 7 passed; `test_in4 test_im5 test_im3` 110 passed; `test_ik4 test_im4 test_in1
test_in2 test_in3 test_in6` 190 passed; `tests/test_metric_registry.py` 3 passed; ruff clean; copy standard clean;
`npm run lint && npm run build` clean; e2e `e2e/io1` 4 passed (375 and 1300), `e2e/in4` 6 passed (unchanged);
`check_root.sh` 1,548 passed, 4 failed — **no new failures**.

## Without my relations (the live site until the nightly)

`summary()` → graded False, words None (cached 10 minutes, then looked at again); `GET /api/context/record` 200 with
that; DFS keeps Wave I-N's words ("no record behind it yet"), no graded chips, no weather; the rule change (the corner
not counting) is code and applies at once: the list is empty with its sentence. Tests for each.

## The PO lines

`scripts/nightly.sh`, after the IL-3 `grade-odds` block (before `save-record`):

```
# ---- IO-1 (Wave I-O): the context record (ops.context_record: the corner calls and "Worth a look" frozen before each
# week's first kickoff; played weeks with nothing stored rebuilt once from as-of inputs, labelled reconstructed; final
# games graded) and the grade the site reads (ops.context_grade). Idempotent; ~3 s a night (31 s the first).
SOFT_WHY="the record's kept weeks are untouched; a week missed tonight is rebuilt from as-of inputs (labelled reconstructed)" soft context-record uv run league-lab context-record
# ---- end IO-1
```

and after the M6 block (state / record tables):

```
# ---- IO-1 (Wave I-O): the context record cannot be recomputed after kickoff (record); its grade is state
STATE_TABLES="$STATE_TABLES ops.context_record ops.context_grade"
RECORD_TABLES="$RECORD_TABLES ops.context_record"
# ---- end IO-1
```

`scripts/sync_to_hosted.sh`, `render.yaml`, `api/Dockerfile`: nothing. **New env variables**: none. **New
dependencies**: none.

## Limitations

The record's live freeze reads `mart_player_week_features.opp_rank_std` for the defense (the projection's rank), not
`mart_defense_vs_position_current` as the screen does (they agreed for 2026 week 5's top five; not checked for every
team). The availability overlay is not in the record. 2026 weeks 1–3 are graded on refit projections. Unclear calls'
chips carry no graded words (their tone merges two corners). Not graded at all: the weather flag.

## Seen, not mine

* **IO-4 / the matchup board**: `combine_tone` still moves the board's one tone on a likely corner, and
  `PROJECTION_WORDS` says "Whether a tough corner lowers a receiver's points has not been graded yet." The grade says
  no measurable effect: the words should come from `summary()["corner"]["words"]` (the interface), and whether the
  corner should still move the tone is the PO's call. The home's corner sentence (IN-1) is the same.
* `mart_cb_matchups.cover_rank` for past weeks is look-ahead (its header says "latest, not as-of"); anything that grades
  from it needs `cb_rank_asof`.

## Next

Grade the record's kickoff weeks as they finish (the sentence switches to "Since 2026 week 5, …" once today's rule
lists anyone); keep the forecasts so the weather flag can be graded; if the record ever shows a quarter with an effect,
flip `WORTH_IGNORES` back with the numbers.
