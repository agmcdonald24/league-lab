# League Lab: from data explorer to decision platform

Review and proposed development brief · September 29, 2026 · author: Andrew (with a second-model review)
Adopted as Iteration 9b / Wave B in `PROJECT_PLAN.md` with the adjustments listed there.

**Recommendation:** make roster decisions the organizing principle of the next release. Build one shared engine that understands every legal starting slot, evaluates the change a move makes to a team, and explains the evidence. Keep the existing data pipeline and projection work as inputs to that engine.

## What I reviewed

- Live Streamlit app: Home, personalized Waiver Wire for MacZaddy, Matchups, Rankings, a switch to Forever Unclean Dynasty, and League navigation. The app reported NFL and Sleeper loads at September 29, 12:00 UTC, with week 3 complete and week 4 next.
- Repository: `agmcdonald24/league-lab`, commit `911ba1e`, including the Wave A changes, handoff, backlog, model code, lineup and positional-strength SQL, waiver SQL, matchup pages, routes import, and metric definitions.
- Fresh local validation: `uv sync --locked`; `uv run pytest -q` → **29 passed**; `uv run ruff check src app tests` → **all checks passed**.
- This was a live workflow review and a code review. I did not rebuild the production database, independently rerun the historical model backtest, or change/deploy application code. Backtest results described in project documents remain the project's reported results.

## What is already worth keeping

The identity mapping, raw data retention, scoring maps, shared denominators, dbt models, usage metrics, and explicit missing-data handling provide useful foundations. Projection v2 adds component forecasts, league-specific pricing, and estimated outcome ranges. The new scoring label and personalized waiver shortlist improve the experience.

The remaining gap is substantial but specific: most screens still expose ingredients from which the manager must assemble a decision. Advanced analytics become useful when they explain an actionable difference between alternatives on this roster.

## Confirmed gaps in the current implementation

| Finding | Evidence | Consequence |
|---|---|---|
| FLEX is excluded from waiver and roster-strength allocation; SUPER_FLEX is treated as a QB slot | `app/pages/2_Waiver_Wire.py`, `dbt/models/marts/edge/mart_league_positional_strength.sql` | A player who improves a FLEX position can miss the shortlist. A superflex roster cannot be evaluated correctly by always assuming a second QB. |
| Positional strength uses season PPG for top-N players | Positional-strength mart; Trade Finder | It mixes realized scoring with forward-looking roster usefulness. IR status is selected but does not exclude a player from the starter totals. |
| The live shortlist can recommend marginal bench upgrades without resolving the actual move | MacZaddy showed three TEs whose projections were 1.8–2.2 below its TE1; they qualified on 0.3–1.1 higher historical PPG than its best bench TE | A comparison is useful evidence, but does not establish that a claim, drop, or extra TE roster spot is worthwhile. |
| Start/sit remains a comparison table | `app/pages/5_Matchups.py`; live screen | It orders players by position and xPPG/PPG, without producing a legal proposed lineup or using the v2 range in that board. |
| Matchup difficulty is largely raw fantasy points allowed by position | `mart_defense_vs_position.sql`, Matchups | Opponent strength, play volume, and scoring noise can masquerade as defensive weakness. The ranks also remain in reference-league scoring. |
| The general waiver table excludes zero-game players and defaults to two games | Waiver input/filter | New starters and speculative adds need their own path; a minimum-games rule should govern confidence, not discovery. |
| The routes proxy is historical participation, not charted routes | `docs/METRICS.md`; routes importer | It cannot supply current-season route participation or reliable current TPRR/YPRR without another feed. |
| Drift code exists, but the hosted view was unavailable | Live dynasty Rankings: "The season scoreboard is not built on this database yet" | Finish the publication step before treating model monitoring as available to users. (Root cause found 2026-09-29: `make project` rebuilt `mart_projection_backtest` without `+`, and dbt's view swap CASCADE-dropped the dependent drift view; fixed in the Makefile and `refresh.sh`.) |
| Past-week predictions are replaced during refits | `project()` and `_write()` in `src/league_lab/projections.py`; documented in STATUS | Drift is not a preserved record of what a manager saw before kickoff. |

The existing historical optimal-lineup SQL handles fixed slots and several FLEX types, but uses a greedy sequence and realized points. It is useful for retrospective analysis; the decision engine needs an exact allocator and forecasts available at the decision time.

## 1. Make roster value depend on usable starts

Build an exact player-to-slot assignment service, using maximum-weight matching or an integer solver. Inputs should include league scoring, actual slot definitions and player eligibility, roster and IR/taxi rules, week, kickoff/lock status, availability, and the selected forecast snapshot. Each player can fill at most one slot. SUPER_FLEX must retain all allowed positions.

Use this service everywhere: lineup suggestions, team rankings, waiver evaluation, roster-strength comparisons, and trade simulations. SQL can prepare inputs and publish results; it should not contain a different approximate lineup rule on each page.

For a proposed add/drop, the first useful measure is:

**Weekly lineup gain = best legal projected lineup after the move − best legal projected lineup before the move.**

This is an initial, transparent objective. It can later be extended to calibrated matchup win probability and multiple weeks without changing what constitutes a legal lineup.

Illustrative example, with all other slots unchanged:

| Option | Individual projection | Effect on this week's legal lineup |
|---|---:|---:|
| Existing QB3 behind two QBs projected for 25 and 24 | 22 | Does not enter the lineup |
| Add another QB projected for 23 | 23 | 0-point starting improvement |
| Add a WR projected for 12 who replaces a 9-point FLEX | 12 | +3-point starting improvement |

The QB3 can still be valuable. Display distinct measures rather than flattening everything into one player rank:

- **Starting value:** weekly contribution and the margin over the best eligible alternative.
- **Depth value:** usable starts over the next four weeks, bye coverage, and injury-contingency benefit relative to the actual waiver pool.
- **Upside value:** improvement if a supported role-change scenario happens.
- **Trade value:** usefulness to other rosters and an independently supported market estimate, when available.

For league roster rankings, rank full legal lineups on a common week or horizon. Show starter strength, FLEX strength, and depth separately. Explain a team's weakest replaceable slot. A bench player should not inflate its starting-power rank merely because QB scoring is high.

For multiple-week simulation, choose lineups using information that would be available at each decision. Do not choose the highest realized scorer after simulating outcomes and call that attainable bench value.

## 2. Turn deeper data into evidence about role

Organize player analysis into opportunity, role direction, efficiency, environment, and uncertainty. Avoid an opaque weighted sum of correlated statistics.

| Question | Metrics to use | Decision it supports |
|---|---|---|
| Is the player getting on the field for passing opportunities? | Actual routes and routes/team dropbacks; snap share as a separately labeled fallback | Emerging receiver, blocking TE, passing-down back |
| Does he earn targets while running routes? | Targets per route; verified first-read and designed-target shares | Distinguish increased playing time from increased involvement |
| Are the opportunities valuable? | Air yards, target depth, end-zone targets, carries inside the five, receiving work for RBs | Explain touchdown or explosive-play potential |
| Is a role changing? | Weekly usage trajectory, teammate absences/returns, depth changes, personnel and situation splits where available | Add before points catch up; avoid chasing a temporary replacement role |
| Is efficiency sustainable? | Yards per route, catchable targets, yards after catch, rushing efficiency with sufficient samples | Separate weak execution, difficult opportunities, and random scoring variation |
| Does the team environment support more work? | Dropbacks, pace, neutral-situation pass tendency, QB changes, offensive health | Explain why equal shares can produce different opportunity totals |

Several ingredients are already in the data model. The work is to unify them into explicit evidence with consistent windows and denominators, not simply add more columns.

Use last-game, recent, and season context together. A rookie's second game can trigger an "emerging role, limited evidence" alert even when it cannot support a stable rate estimate. Shrink sparse estimates toward appropriate historical/position baselines. Distinguish a durable role change from a one-week injury replacement or an unusual game script.

**Do not equate PPG below xPPG with bad luck or an automatic buy.** Poor QB play, difficult target quality, declining health, and persistent player efficiency can also cause the gap. For trade comparisons, reconcile scoring components: the current documentation notes that xPPG excludes bonuses, so the dynasty PPG-minus-xPPG gap includes a scoring-definition difference.

### Routes acquisition is an explicit work item

The existing `league-lab import-routes` CSV contract is a good starting point. Before choosing a provider, verify a sample that includes **all eligible receivers' routes**, stable player/game IDs, weekly publication timing, historical coverage, definitions, corrections, and permission to use and display the data in the intended product. A consumer subscription alone does not establish feed or redistribution rights.

The official nflverse schedule says participation data from 2023 onward arrives after the postseason. Public FTN charting is a separate subset and is published during the season. Neither should be described as an all-player live routes feed without verifying the fields [1][2][3].

The importer currently replaces a provider's entire season partition. Before automating weekly CSV delivery, change that contract to a safe game/week upsert or explicitly require a cumulative season export; otherwise a one-week import can erase earlier weeks from that provider.

There is also a definition issue to settle: League Lab maps `read_thrown=1` to first read based on its documented data inspection, while the current nflreadr dictionary maps `0` to first and `1` to second. Treat this as an unresolved source-definition conflict, obtain provider/maintainer confirmation, and test verified plays by source version. Code-frequency plausibility alone should not certify the meaning of a foundational recommendation signal [4].

## 3. Model upside as several different questions

The existing P10/P90 intervals are useful estimates of weekly scoring variation. They do not by themselves explain how a player becomes more valuable.

| Type of upside | Product output |
|---|---|
| Weekly scoring upside | Range, chance of exceeding the relevant starter threshold once calibrated, and what creates the high-end outcome |
| Expanding role | Base role and a supported larger-role scenario; evidence for the transition |
| Contingent opportunity | Expected role if a named teammate misses time; benefit and time-to-reassess |
| Dynasty development | Longer-horizon role/age/career evidence, separately labeled from this year's lineup value |

A useful stash explanation might say: "His route participation is rising, but he remains behind your current FLEX. Hold as a role-growth candidate; reconsider if participation falls when the injured starter returns." This is an illustrative output, not a current player recommendation.

Start with explicit scenarios and qualitative confidence. Publish precise breakout probabilities only after testing calibration. A P90 is neither a maximum nor an 80% confidence statement about the model being correct.

Later, use joint outcome simulations to compare lineup win probability. Preserve same-game and teammate dependence; do not sum individual P90s and call the sum a team ceiling. Likewise, "always maximize variance when the underdog" is too crude. The objective is the probability the whole lineup beats the opponent.

## 4. Make defensive matchups useful in the roster context

Default to the user's roster, with opponent, matchup assessment, reason, confidence, and the next three or four games. Allow side-by-side comparison of the players competing for the same slot.

Build matchup analytics in this order:

1. Separate opportunity allowed from efficiency allowed: attempts/targets/carries versus production per opportunity.
2. Adjust for the offensive quality and roles the defense has faced, using only information available before the evaluated week. Shrink early-season results toward a prior and expose the sample.
3. Connect defensive traits to player roles: rushing versus receiving RB work, short versus deep targets, and pressure/blitz context where current coverage is verified.
4. Add slot/outside alignment, man/zone and route-family interaction only after acquiring suitable coverage and route data. Do not infer a guaranteed WR–CB assignment from a depth chart.

Keep raw defense-vs-position ranks as a drill-down. The decision surface should say what makes the matchup favorable or difficult for this player and how much that should affect the choice. Score matchup impacts under the chosen league's rules or use clearly defined scoring-neutral components.

Distinguish offensive-player matchup analysis from **D/ST streaming**. League of Scrubs starts a defense, but the current player/projection paths focus on QB/RB/WR/TE/K. Add an explicit D/ST path before claiming to cover a complete lineup; handle kicker forecasts similarly.

## 5. Complete the actual waiver and trade decisions

**Waivers:** rank legal add/drop pairs against doing nothing. Show starting gain, depth/bye effect, the player being dropped, the role signal, confidence, and the conditions under which the move stops making sense. Separate "start now," "next-few-weeks cover," and "upside stash." Do not force a recommendation when the evidence is weak. Where supported, incorporate roster limits, waiver timing/priority, FAAB remaining, and ordered fallback claims. Begin with a justified bid range and assumptions; exact bids need evidence about league demand.

**Trades:** recompute both rosters before and after each proposed package. Include the required drop in a two-for-one deal and the available replacement player for the side opening a roster spot. Rank partners by complementary roster improvement. Show who gains usable starts and who takes on risk. Keep market value distinct from fit: being redundant on one team does not mean a player is cheap to acquire. Handle dynasty picks, keeper costs, and future years only in an explicit longer-horizon mode with their own data.

## 6. Streamline the experience around three tasks

Use three primary destinations: **My Week**, **Improve My Team**, and **Research**. Keep league/team/week context persistent and visible near the top. Treat the player card as a shared detail view reachable from every player name.

- **My Week:** proposed legal lineup; two or three meaningful start/sit decisions; injury/lock alerts; alternatives and next-matchup context.
- **Improve My Team:** a short list of add/drop opportunities, useful stashes, roster vulnerabilities, and trade fits.
- **Research:** the current rich tables, filters, receiver analysis, league history, and model diagnostics.

Each recommendation should have an action, a named alternative, expected roster effect, two or three supporting facts, the strongest reason it could fail, and the last relevant update. Expand for the full evidence. Avoid horizontal scrolling for the primary recommendation, and use an explicit no-change result when appropriate.

Keep the existing Streamlit app for this next slice. Reassess the frontend after testing whether managers can complete the decision flow; the current bottleneck is the decision logic and information design.

## Ordered implementation backlog

These are proposed additions/changes to `docs/PROJECT_PLAN.md`, not already approved repository changes. Preserve the existing U-12 and M-05 work, but broaden M-05 to cover exact allocation and roster value.

| Order | Deliverable | Acceptance criteria |
|---|---|---|
| 1A | Exact lineup service and common league-rule contract | Correct solutions for 1QB, 2QB, superflex, multiple/mixed FLEX slots, dual eligibility, byes, IR/taxi, unavailable players, locked starters, empty slots, and required D/ST/K handling. Compare small synthetic fixtures to exhaustive legal enumeration. |
| 1B | Roster usefulness and league roster rankings | QB3 does not inflate starting strength; a WR who improves FLEX is recognized; every rank declares horizon; depth and starter strength are separate; removing a player re-solves the full lineup. |
| 1C | U-12 player card and My Week | Show an actual proposed lineup, named alternatives, projected change, key usage evidence, and uncertainty on one screen. Every relevant player name opens the same card. |
| 1D | Trusted recommendation record | Persist forecast, roster/settings, relevant input timestamps, model version, alternatives and recommendation at decision time; do not rewrite closed decisions. Publish the missing drift relation. Flag stale injury data; retain the last validated publication if refresh fails. |
| 2A | Waiver add/drop engine | Evaluate actual legal moves and doing nothing; include zero-game candidates with honest uncertainty; account for the dropped player's future usefulness; separate current starters, cover, and stashes. |
| 2B | Role-change signals and routes source trial | Validate weekly role alerts against known cases; resolve first-read coding; audit provider route samples and freshness; safe incremental imports; no proxy represented as actual routes. Work on the feed trial can start alongside Release 1. |
| 3A | Matchup comparison | A manager can compare two FLEX options with opponent-adjusted evidence, sample size and source freshness; team schedule strip; raw ranks and CB details accessible on demand. |
| 3B | Scenario upside | Base and conditional-role scenarios with assumptions and an expiry/review condition; validate probabilities before exposing them; do not present future role changes as known. |
| 4 | Trade evaluator and partner finder | Full before/after legal lineup for both sides; two-for-one roster constraints and replacements accounted for; short- and long-horizon value separated. |
| Ongoing | Reliable refresh and evaluation | Atomic validated publication, last-good data, reproducible model/data versions, decision-time updates for injuries/availability near deadlines, historical correction audit, backup restore drill. |

**The first release should contain 1A–1D as one coherent usable slice.** The routes trial should not block it. It should answer: "Who should start, what is my weakest useful slot, and what evidence might change the answer?"

## How to tell whether it is working

**Correctness:** every recommended lineup/move is legal. Unsupported scoring and unavailable data are explicit. End-of-game outcomes used for evaluation reconcile to the league's actual scoring, including supported bonuses. Current projection outcomes omit long-TD counts, and threshold bonuses applied to a mean stat line are not the same as expected bonus points; close those gaps before claiming full-scoring forecast accuracy.

**Decision quality:** compare the recommended policy against the existing v2 lineup policy and a simple baseline using identical rosters, league rules, availability, and information cutoffs. Measure realized lineup-point improvement and uncertainty across weeks; retain forecast MAE/rank correlation as supporting diagnostics. Evaluate the realistic decision pool, not just every NFL player, and include availability failures in the decision-policy evaluation.

**Upside and waivers:** measure whether flagged players later gain role and earn useful starts over a declared horizon; count false alerts and the cost of the drop. Historical waiver backtests require historical ownership/availability, so preserve snapshots now and clearly label any earlier research as an approximation.

**Calibration:** assess interval coverage and width by position, role/sample size and availability category. When win probabilities are introduced, test them separately. Three quantiles do not identify a complete joint score distribution.

**Usability:** give a small set of managers three realistic tasks—set a FLEX, choose an add/drop, compare a trade. Proposed target: complete each core task in under two minutes and explain the recommendation and its caveat without opening several research tables.

Replace the existing M-05 "90% agreement with optimal lineup" acceptance rule if it means agreement with the highest realized scores after the games. The solver should be exactly correct for its supplied forecasts; the forecasting policy should earn its value in a time-valid test. Hindsight optimum is a diagnostic bound, not a realistic predictive promise.

The product has credible upside as a league-aware decision assistant: it can reduce research time, notice role changes early, and explain why a player matters to a particular team. Its predictive edge still has to be demonstrated. The most valuable next milestone is a smaller set of complete, testable decisions rather than a larger set of standalone metrics.

## Primary source checks

1. nflverse data update schedule: https://nflreadr.nflverse.com/articles/nflverse_data_schedule.html — participation timing and in-season charting schedule.
2. FTN charting loader: https://nflreadr.nflverse.com/reference/load_ftn_charting.html — public subset, timing and attribution.
3. Participation dictionary: https://nflreadr.nflverse.com/articles/dictionary_participation.html — on-field players and primary-receiver route fields.
4. FTN charting dictionary: https://nflreadr.nflverse.com/articles/dictionary_ftn_charting.html — published `read_thrown` mapping, checked September 29, 2026.
5. Repository: https://github.com/agmcdonald24/league-lab — reviewed at commit `911ba1e`.
