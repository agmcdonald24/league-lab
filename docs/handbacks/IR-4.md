# IR-4 — say what is verified, and carry uncertainty into the verdict (Wave I-R, 2026-10-08)

Task: the dependability review's P1 3 (BRIEF.md § IR-4). Branch `dev/IR4` from `main` `3dfa01d`; database
`league_lab_im4` (written: `ops.context_grade` only, regraded once with the new kinds). Nothing pushed or merged.

## What is done (all five, in the brief's order)

1. **Provenance with every analysis** — `api/league_lab_api/provenance.py`. The `provenance` key on `/api/rankings`
   (week and season), `/api/ros`, `/api/trade-calc/free`, `POST /api/trades/evaluate` and `/api/player/{gsis}`:

   ```
   {"model_version": "v3.6",          # the stored board's newest non-K/DEF version (ops.projections), else the code's
    "kd_model_version": "kd1.0"|null, # only when K or DEF are in scope
    "published_at": ISO|null,         # max(ops.projections.fitted_at): the board's publication (IR-3's publication id can replace it)
    "horizon": {"first", "last", "market_week", "words": "weeks 5–18"},
    "checks": [{"span": "next"|"later"|"season_range"|"trade_gap", "position", "status": "graded"|"graded_weak"|"chance"|"not_graded",
                "words", "ref": "docs/METRICS.md § …", "mae", "order"}],
    "status": the weakest status of the checks, "beta": bool, "words": "<the one quiet line>"}
   ```
   One query (`BOARD_SQL`, a group-by of `ops.projections`, cached 10 minutes in `db.query`'s region); a missing table
   or failed read gives the code's version and no time (never a guessed one); every hook is wrapped (a stamp never costs
   a screen). The statuses are constants with their METRICS reference. The line, as each screen shows it
   (`ProvenanceLine.svelte`, `text-xs text-ink-3`, no colour):
   * Rankings, this week: "Model v3.6, data published 7 Oct, 8:05 pm ET · week 5 · checked on 2021–2025: next week graded."
   * Rankings rest of season, `/ros`: "Model v3.6, data published … · weeks 5–17 · checked on 2021–2025: next week graded;
     two to eight weeks ahead graded, weak; the season total's range not graded." (all positions: "next week graded,
     kickers and defenses weak; two to eight weeks ahead graded, quarterbacks weak, kickers and defenses no better than
     chance; …")
   * Free calculator and the league trade evaluation (under the verdict): "Beta · Model v3.6, data published … · weeks 5–8 ·
     checked on 2021–2025: next week graded; two to eight weeks ahead graded, quarterbacks weak; …; the trade's range not graded."
   * The player card (under "How to read this"): the line for his position, this week to the season's end.
   (My database's board is v3.5, so its recordings say "Model v3.5": the line reports the stored board, not the code.)
2. **About**: "its recipe stays the same all season" replaced ("… and the model itself has changed during the season:
   every version and its date is under "What changed and when" below."); new sections **What changed and when** (8
   dated versions v2.0 → v3.6 + kd1.0, "Now: v3.6 …, data published …", and "This season's weeks, by the version they
   were made with: weeks 1–3: v2.0; week 4: v3.0; weeks 5–18: v3.5" read from the board) and **What each number has
   been checked against** (a card per position: next week, two to eight weeks, next four weeks, rest of season, with the
   QB baseline; "Not graded yet: …"; the useful-decision sentence; the starter rule). The "+0.7 per team per week" claim
   keeps its qualifier, now directly under the claim ("* Weeks 1–4 were played before this record existed: their lineups
   were rebuilt after kickoff …", was at the foot of the block). **Beta**: "Beta · " opens the line under the trade
   verdict (free and league); the home says "Beta. What each number has been checked against, and what has not, is on
   About the numbers." (link `/about#checked`).
3. **Starter uncertainty reaches the decision** (`provenance.caveats_for`, `effect`, `apply`; METRICS § "Starter
   uncertainty in a decision"). **Rule**: a decision that depends on a quarterback whose team's starter is *unclear*
   (`starters.unclear`, U1, not corrected) — or on an MFL team-QB unit of that team — is **withheld** (numbers stay, no
   recommendation); one that depends on a starter *set by hand* (`starters.corrected`) is **softened** (a lean, never a
   firm call, with whom it assumes). Why: U1's flag was right about a stale listing 12 times in 27 (2025 – 2026 wk 4),
   and starter vs backup is ~10 points a week (SEA wk 5: 15.0 vs 4.3) — more than the 10-point "about even" band over
   four weeks; a correction rests on evidence but a person made it. Receivers / backs / tight ends of such a team carry
   nothing (their models do not read the QB inputs). Data: `caveats` [{kind, effect, team, players, words}],
   `caveat_effect`, `caveat_rule` on the free calculator and the league trade evaluation. **Applied** to the free
   calculator's verdict (withheld: "No verdict: it depends on who starts for Tampa Bay.", no lean → no colour; softened:
   "… (a lean: it assumes Darnold starts)."; the original in `words_unqualified`). "Who should I start?" already
   withholds the call on an unclear QB (IQ-2's "no call").
4. **The horizons the trade calculator uses, graded by position, in the record** — `ops.context_grade` kinds `horizon`
   (20 rows: next week, 2–8 weeks, next four weeks, rest of season × position, with the QB baseline) and `useful` (4
   rows), written by `context_record.write_grade` (`horizon_grade_rows`; no new table), read on `/api/context/record`
   as `horizon.cells`. Numbers (2021–2025, as of weeks 3/5/7/9, both house scorings; order = Spearman / miss in points
   per game; source METRICS § "What each number has been checked against (IR-4)"):

   | window | QB v3.6 vs B2 (his record + role, opponent, line) | RB vs his own points per game | WR | TE |
   |---|---|---|---|---|
   | next week | 0.587 / 6.44 vs 0.575 / 6.60 | 0.686 / 4.52 vs 0.644 / 4.70 | 0.618 / 4.44 vs 0.572 / 4.64 | 0.599 / 3.25 vs 0.519 / 3.45 |
   | 2–8 weeks ahead | 0.495 / 7.41 vs 0.497 / 7.45 (weak) | 0.636 / 4.73 vs 0.599 / 4.95 | 0.569 / 4.62 vs 0.542 / 4.77 | 0.545 / 3.42 vs 0.485 / 3.59 |
   | **next four weeks** (h 1–4) | 0.538 / 6.93 vs 0.537 / 7.00 | 0.664 / 4.64 vs 0.624 / 4.82 | 0.595 / 4.49 vs 0.560 / 4.64 | 0.570 / 3.35 vs 0.501 / 3.54 |
   | **rest of season** (h 1–8) | 0.509 / 7.28 vs 0.510 / 7.33 | 0.642 / 4.71 vs 0.605 / 4.92 | 0.575 / 4.60 vs 0.546 / 4.75 | 0.553 / 3.40 vs 0.489 / 3.57 |

   (order / miss in points per game.) RB / WR / TE beat their own record in every window, 5 of 5 seasons (the
   baseline run, `ir4_useful.py --baseline`, defined and committed `b148812` 10:49 before its run 10:50–10:55; the
   rows where he has a record); QB is level with B2 beyond next week (IQ-3). K / DEF: next week 0.095 / 0.257 (weak),
   2–8 weeks 0.028 / 0.040 (no better than chance; IQ-4). These are per-week misses pooled over the window's weeks, not
   window totals.
5. **The "useful decision" grade (ud1.0)** — defined in METRICS and committed (`b03ccac`, 10:29 ET) before the run
   (`scripts/analysis/ir4_useful.py`, 10:30–10:37, 20 fits): close one-for-ones (projected four-week totals within 20 %),
   share where the calculator's side scored more over the four weeks, against the side his own per-game record favours:

   | | pairs | calculator | his own record | by season (calc / record) 2021 … 2025 | verdict (rule: > 50 % and above the record in ≥ 4 of 5) |
   |---|---|---|---|---|---|
   | QB (v3.5 rows) | 3,680 | 0.594 | **0.615** | .580/.647 .578/.590 .632/.643 .593/.594 .586/.603 | no better than his own record (0 of 5) |
   | RB | 6,320 | **0.575** | 0.552 | .554/.586 .572/.513 .578/.554 .603/.582 .569/.524 | useful (4 of 5) |
   | WR | 8,643 | **0.584** | 0.539 | .604/.613 .615/.558 .553/.526 .566/.498 .583/.500 | useful (4 of 5) |
   | TE | 2,939 | **0.555** | 0.524 | .544/.535 .547/.474 .572/.545 .562/.500 .550/.565 | useful (4 of 5) |

   Not about even (gap > 10 %): QB 0.640 / 0.640, RB 0.611 / 0.572, WR 0.629 / 0.569, TE 0.601 / 0.523. On About: "Is
   the trade calculator right? … 58 times in 100 at receiver, 57 at running back and 56 at tight end — more often than
   the side his own per-game record favours (54, 55 and 52). At quarterback 59 in 100, but the side his own per-game
   record favours did better (62). 50 would be a coin flip."

## Still ungraded (said on About and in METRICS)

The ranges around a season total and around a trade's gap (weekly ranges added as independent); a trade of several
players or across positions and the lineup effect in a league (ud1.0 is one-for-one, same position); K / DEF over a
window as a total; QB ud1.0 on v3.6's rows (hb1.0 not in the run);
whether the other manager accepts. The horizon rows are the studies' numbers, not a prospective record: the nightly
rewrites later weeks every night, so no week-W projection of week W+3 survives to be graded (a prospective record needs
the rest-of-season board frozen at each kickoff — a new table, the PO's call).

## The one call IR-2 / the PO must add (the league trade verdict)

`POST /api/trades/evaluate` already carries `provenance`, `caveats`, `caveat_effect`, `caveat_rule` (hook in
`main.trades_evaluate`, after `decisions.evaluate`). What is **not** done: the league verdict itself is not withheld or
softened (IR-2 owns `decisions.evaluate` and the screen). In IR-2's one decision object, after its primary verdict:

```python
ruled = provenance.apply(decision["verdict"], out.get("caveats") or [])   # {"verdict": str | None, "effect", "words"}
# None = withheld: show ruled["words"] in the verdict's place, no dial colour; "soften": the verdict as a lean + ruled["words"]
```
(or `provenance.caveats_for(out["give"] + out["get"], ctx.season, ctx.this_week)` if built before the hook). Start /
sit already withholds on an unclear QB (IQ-2); a corrected QB's call is not softened there (IR-1 owns StartAnswer);
waivers and My Week lineups: `provenance.for_players(players, season, week)` gives the same caveats — not wired.

## Edits outside my files (each in a marked `IR-4` block)

* `api/league_lab_api/rankings_api.py` 696–699 (the route: `provenance.with_rankings(rankings(…))`)
* `api/league_lab_api/main.py` 446 (`/api/player`: `provenance.with_card`), 456 (`/api/ros`: `with_ros`), 680
  (`/api/trades/evaluate`: `with_trade`), 995–999 (the import block at the end). No new route; no limiter change.
* `api/league_lab_api/freetrade.py` 265–266 (`provenance.with_free_trade(evaluate(…))`)
* `api/league_lab_api/context_record.py` 51–56 (EMPTY's `horizon`), 108–117 (`_build`'s cells)
* `src/league_lab/context_record.py` 857 (`grade_rows` += `horizon_grade_rows`), 1620–1687 (the block)
* `api/tests/test_ip3.py` 88 (the summary's key set + `horizon`)
* `api/league_lab_api/ros_grade.py` 12–13, 24: `QB_LATER_MAE` 7.56 → 7.41 (v3.6), the sentence says 7.4;
  `api/tests/test_iq4.py` 122 and 134 updated on purpose; `web/e2e/iq4/fixtures.spec.ts` 25 and
  `web/fixtures/iq4/api_iq4.json` (the sentence 7.6 → 7.4, 4 places)
* `web/src/routes/Rankings.svelte` 21, 269; `Ros.svelte` 29, 227; `components/scoring/FreeTrade.svelte` 18, 232;
  `routes/decisions/TradeCalc.svelte` 40, 384 (the line under `data-testid="verdict"`); `routes/Player.svelte` 15,
  165; `routes/Home.svelte` 106 (beta); `web/src/lib/api.ts` 2777–2875 (types, at the end)
* `web/src/lib/about.ts` 58; `About.svelte` (mine) 137–184, 244–245; `api/league_lab_api/about.py` 260–261
* `dbt/seeds/metric_registry.csv` (one row: `useful_decision,ud1.0`); `docs/METRICS.md`, `docs/WORDS.md`,
  `CHANGELOG.md` (the IR-4 bullet under `## 2026-10-08 — Wave I-R (dependability)`)

## Tests

* Mine: `api/tests/test_ir4.py` 19 passed (18 tests, one run for week and season; pure: the line per screen, statuses, spans, no-board fallback, withhold / soften
  / receivers / MFL TMQB / failing flags, the free verdict, About's block, the record rows = the constants, the site
  reads them; database: rankings week + season, ros, free calculator, card, about).
* Edited modules' API tests: test_h1, test_ig3, test_in2, test_ip2, test_iq2, test_iq4, test_im3, test_ia3, test_io1,
  test_io4, test_ip3: 293 passed, 1 skipped, 2 failed — `test_h1::test_waivers_trade_lists_on_demand_equal_the_house_path`
  (in `known_api_failures.txt`) and `test_ip3::test_without_the_table_every_key_is_quiet`, which pins the record
  summary's keys: updated on purpose for the new `horizon` key (line 88), then test_ip3 + test_io1 + test_ir4: 48 passed.
* Root (`check_root.sh`, final): 1619 passed, 4 failed, 3 skipped — no new failure (the first run's one new failure,
  `test_metric_registry::test_every_documented_metric_has_a_registry_row` for ud1.0, fixed with the registry row).
* ruff clean; copy standard clean; `npm run lint` (eslint + svelte-check + tsc) 0 errors 0 warnings; `npm run build` ok.
* e2e `web/e2e/ir4` + `web/e2e/iq4` (port 8947): 20 passed (ir4 12) (phone 375, desktop 1300; no sideways scroll), on answers recorded from the
  app on `league_lab_im4` (`web/fixtures/ir4/api_ir4.json`); `web/e2e/iq4`: 8 passed. TradeCalc (league) has no
  fixture answer for `POST /api/trades/evaluate`: its line is type-checked, not browser-tested.
* Screenshots: `docs/handbacks/ir4/*.jpg` (rankings, ros, free trade, card, About × 2, home; phone and desktop).

## Face validity

No list order or number changed (provenance labels; the record gets constants). What changed and was checked:

| Screen (week 5, `league_lab_im4`) | What it now says | Right? |
|---|---|---|
| Rankings QB rest of season | "Model v3.5, data published 7 Oct, 8:05 pm ET · weeks 5–17 · … two to eight weeks ahead graded, weak; the season total's range not graded." | the board is v3.5 (fitted 00:05 UTC 8 Oct = 8:05 pm ET 7 Oct); QB 2–8 order 0.495 < 0.50 |
| Free calculator Darnold → Hubbard | "You get more: 103 points … (a lean: it assumes Darnold starts)." + the Seattle sentence | SEA's override (Darnold set, Lock listed) is in force |
| Free calculator Mayfield → Hubbard | "No verdict: it depends on who starts for Tampa Bay." (was "You get more: 103 …") | TB is U1-unclear this week: Jalon Daniels listed, the depth chart puts Baker Mayfield first |
| A Seattle receiver in a trade | no caveat | his projection does not read the QB (IQ-2) |

Week-5 flags on this database: unclear TB (Daniels, Mayfield); corrected SEA (Darnold / Lock), CHI (Bagent / Keenum).

## Found, not mine

* The free calculator's window ends week 18 while `/ros` and Rankings for the same key end week 17 (refleague's
  `last_week` vs the ros window): "weeks 5–18" vs "weeks 5–17" on two screens of the same scoring.
* "Who should I start?" shows a corrected QB's call as firmly as any other (IQ-2 kept it); under this rule it would be a
  lean (IR-1's screen).
* `about.py`'s `about()` puts `timings_ms` into the cached dict on a miss (shared object): harmless today.

## Next

Freeze the rest-of-season board at each kickoff (a prospective horizon record); ud1.0 for packages and cross-position
trades through the league calculator's own lineup math, and QB on v3.6's rows; IR-2's `provenance.apply` call.
