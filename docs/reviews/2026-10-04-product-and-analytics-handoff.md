# League Lab: product and analytics implementation handoff

*(The fifth outside review, verbatim; received from Andrew 2026-10-04 15:10 ET with "next wave. plus agent feedback in
this markdown. plus I logged into my google analytics for you to create tracking on this." Reviewed `c47c5ea` on
2026-10-04, desktop, League of Scrubs, MacZaddy (roster 2), week 4.)*

Review date: October 4, 2026
Live application: https://league-lab.onrender.com/
Primary review context: League of Scrubs, league `1389709692405551104`, MacZaddy, team `2`, week 4.

## Objective

Make League Lab a dependable decision and research platform for experienced fantasy managers: league-specific analysis, useful comparisons, realistic trades, and quick access to the evidence behind a recommendation. Keep the interface understandable without removing analytical depth. Technical comfort and fantasy expertise are separate considerations.

This brief incorporates the owner's latest feedback and a fresh desktop walkthrough. It is an implementation plan, not a code or model audit. Backend causes below are hypotheses where indicated. Mobile behavior, the latest MFL 70587 build, and private-provider authentication were not retested in this pass. Preserve earlier fixes and regression coverage, including MFL team-quarterback handling.

## What is already working—and should be reused

- The main navigation and Team/League structure provide a useful foundation. Keep these recognizable.
- **Players → Players already has a sortable table.** Filtering WRs and sorting `Tgt %` worked. The richer Receivers view is separate, which makes the capability hard to discover.
- **Players → Players already opens a player drawer.** Kyren Williams opened beside the table; Escape closed it while retaining the RB filter, search, and sort. Extend this component rather than building competing player viewers.
- **Carry share is already exposed on a player card:** Kyren showed 47.5%, alongside target share, snap share, and red-zone share. It is missing from the inspected bulk table. Routes run were not found in the inspected views; their ingestion/model availability remains unverified.
- Matchup explanations have improved. Sutton's page states the points-allowed sample and lack of opponent adjustment, names expected cornerbacks, and says personnel context is not incorporated into the forecast. Preserve that transparency.
- Waiver reasoning now includes replacement/drop considerations, and the trade finder compares its suggestions with a waiver alternative. These are useful foundations to strengthen.

## Delivery order

| Priority | Work | Completion criterion |
|---|---|---|
| P0 | Audit lineup eligibility, locked players, and Team benchmarks | All displayed comparisons use legal lineups and consistent units; numerical and narrative results agree |
| P0 | Repair trade candidate evaluation | The verified Folk package is evaluated against realistic alternatives for both teams; implausible exchanges are not promoted |
| P1 | Extend the shared player drawer; unify research tables | Waivers, Receivers, Players, and other player links support uninterrupted inspection |
| P1 | Clarify Season, news impact, horizons, and metric copy | Users can distinguish roster contribution, acquisition benefit, historical stats, and forecasts |
| P1 | Expose existing advanced metrics | Verified data already ingested appears in sortable, documented position presets |
| P2 | Accounts, profiles, and provider-specific onboarding | A user can save and revisit multiple leagues with explicit sync status |
| P2 | ESPN feasibility and additional providers/data | Integrations have validated access, rules coverage, operating costs, and sustainable data rights |

## 1. Fix calculation and explanation inconsistencies

### Observed evidence

On **Team → Strength by slot**, Puka's WR projection was **14.8**, while the same section stated **league average 5.0 / best 7.3**. FLEX showed a similar inconsistency: Michael Wilson **11.7**, average **2.5**, best **4.3**. The caption describes projected starter points. These cannot all be the same measure over the stated comparison set.

Kyren's RB replacement/margin explanation names **Malik Washington**, who is a WR. The player card says Kyren starts at RB1 and losing him costs **5.18**, with Washington **7.56** coming in. This could be a lineup reassignment through FLEX, but the UI does not explain a legal chain. The home lineup also showed Jacory Croskey-Merritt locked after his game started. Validate whether the proposed reassignment respects that lock; do not assume a WR can directly replace an RB.

### Required changes

1. Audit the values feeding each bar, average, maximum, percentile/rank, and explanatory sentence. Use one metric, scoring system, horizon, and eligible comparison population throughout. The precise backend cause was not established in this review.
2. Compute replacement effects by re-optimizing a **legal** lineup. Respect position eligibility, all starting slots, FLEX/Superflex, provider-specific team assets, injury eligibility, and already-locked players/slots.
3. If a legal FLEX cascade is responsible, show it: "RB moves from FLEX to RB; WR fills the open FLEX." If no legal move exists, say so.
4. Use full names when surnames collide. "Over Washington" is ambiguous with both Parker and Malik on this roster.
5. Represent roster allotment: RB1 and RB2, WR1 and WR2, and each FLEX slot. A position group's best player alone cannot describe the strength of all required starters. Offer group totals and usable depth as secondary summaries.
6. Generate explanatory text from the same structured result as the displayed numbers. The trade page currently says "Nothing changes this week" beside a **−1.5** weekly change in the Mahomes/Maye example.

**Acceptance:** fixtures cover locked FLEX, multiple eligible positions, identical surnames, empty slots, and MFL team QBs. For a shared metric/population, the displayed maximum cannot be below a member's value. Team, lineup, player card, and transaction explanations reconcile.

## 2. Make trade recommendations credible

### Reproduced example

The finder suggested sending **Nick Folk** to **Run Bijan Run** for **Matthew Stafford + Will Reichard**. It labeled the other team's starter effect "Improves it a lot." Its weekly table showed:

| Team | Week 4 | Week 5 | Week 6 | Week 7 |
|---|---:|---:|---:|---:|
| MacZaddy | +0.1 | +19.4 | −8.4 | 0.0 |
| Run Bijan Run | −0.1 | −0.5 | +8.4 | 0.0 |

Displayed four-week benefit to MacZaddy: **+11.2**, with an explicit notice that a Brissett waiver claim gives **+19.9**. The table suggests bye-week coverage is a major driver. That is an inference from the output, not a confirmed inspection of trade-engine code.

The top "Best partner" suggestion, Mahomes for Maye, also failed its own waiver comparison. The engine needs permission to return **"No compelling trade found."**

### Required evaluation layers

1. **Transaction legality:** ownership, roster limits, required drop(s), locked assets, position requirements, and the provider's rules.
2. **Both teams' realistic alternatives:** compare doing nothing, legal internal moves, plausible waiver/free-agent coverage, and the proposed trade. Explicitly distinguish guaranteed available players from claims that might be lost. Do not manufacture a huge benefit by assuming a manager leaves a future kicker or QB slot empty.
3. **Full roster utility:** starting-lineup benefit by week, bye coverage, depth lost, injury contingencies, roster-slot cost, and rest-of-season effects. In dynasty/keeper formats include their different horizons and supported assets; disclose unsupported pick/keeper rules.
4. **Market plausibility:** account for positional scarcity, league size/scoring, player tier, role security, upside, and credible market inputs where available. Starter-point gain is not exchange value. A bench QB can have zero immediate lineup contribution and still have trade/insurance value.
5. **Recommendation threshold:** promote a small set of defensible candidates with a reason both managers might engage. Put marginal ideas behind "Explore alternatives." Do not fill a quota with weak trades.

Use format-aware guardrails around kicker/defense exchanges. Do not solve this by hardcoding these three names or banning every cross-position trade. A 1-QB shallow league and a deep Superflex league require different scarcity assumptions.

The trade card should show: **you give / you get; required drops; your lineup effect; their lineup effect; depth or future cost; waiver alternative; why they might consider it; reasons they might refuse.** Separate "improves their starters" from "plausible offer." Do not display a numerical acceptance probability without calibrated evidence.

**Acceptance:** the Folk package is a regression fixture, alongside legitimate unequal-size trades and deep/Superflex cases. Both teams receive equivalent treatment of free-agent alternatives. If market inputs are missing, identify the output as a roster-fit idea rather than an attractive offer. Empty or weak candidate sets produce an honest empty state.

## 3. Use one shared player viewer everywhere

### Current inconsistency

- **Players table → Kyren:** opens an in-page side drawer; Escape works.
- **Waivers → All available → WR → Courtland Sutton:** navigates to a standalone player page.
- **Receivers → Parker Washington:** also navigates to a standalone player page.
- Returning from Sutton preserved the waiver view and WR filter. The observed issue is the interruption/new page, not proven loss of all filters.

### Required behavior

Reuse the existing drawer as the shared player inspection component. Offer an expanded lightbox for deeper exploration and retain an explicit **Full player page** link. Apply it consistently to waivers, receiver tables, team/season rows, trade players, matchup references, and search results.

The current narrow drawer repeats a large amount of full-page content. Give it a compact initial view with **Overview / Usage / Game log / News** sections, an expand control, and an add-to-compare action. Keep the active league and scoring visible. Avoid a long paragraph of projection components as the first thing a manager must parse.

Preserve search, filters, sort, pagination, selected rows, and scroll when opening/closing. Load details inside the panel, keep the underlying list usable, cache by the relevant player/league/scoring/season/data version, and prevent an older response from overwriting a newly selected player.

**Acceptance:** open several players consecutively without full-page navigation; close with Escape/close control; browser Back closes an opened panel before leaving the research view; focus returns to the originating control. An expanded modal has proper dialog/focus behavior; a nonmodal drawer remains keyboard accessible. Deep links and Full page retain league context. Test mobile as a full-height sheet—mobile was not reviewed here.

## 4. Consolidate Players and Receivers into a Stats Explorer

The existing player table is a useful starting point. Extend it and expose it clearly; do not add a third disconnected research screen. Keep the attractive receiver role card as an optional detail view.

Suggested navigation: keep main **Players**; organize its research tabs as **Stats / Trends / Matchups / Compare**. Receivers becomes a Stats preset, with a corresponding Running Backs preset. Preserve existing URLs through redirects or equivalent routes.

Required controls:

- Position, ownership (all / mine / free agents / other teams), NFL team, player search.
- Season, last 3 games, last 5 games, and custom week range; explicitly distinguish last games played from last calendar weeks.
- Totals / per-game mode for compatible counting stats; percentages and rates retain their own denominators.
- Minimum games/opportunities filters, visible sample counts, numeric ascending/descending sorting, and a column picker.
- Sticky player identity column and header, saved presets, and selection of two to four players for comparison.
- Null/unavailable data displayed as `—`, with the reason available; never silently convert it to zero. Sort across the full result set before pagination.

### Position presets

| Preset | Default columns | Additional columns when verified available |
|---|---|---|
| WR / TE | Games, fantasy points per game, targets per game, target share, receiving yards per game, snap share | Routes run, route participation, targets per route run, yards per route run, air-yard share, average depth of target, first-read target share, red-zone targets, catchable-target rate |
| RB | Games, fantasy points per game, carries per game, carry share, targets per game, snap share, rushing yards per game, receiving yards per game | RB-only backfield carry share, inside-the-5 carries/share, red-zone opportunities, routes run, route participation, targets per route run, rushing yards over expected per attempt |
| QB | Games, fantasy points per game, pass attempts per game, passing yards per game, rush attempts per game, rushing yards per game | Completion percentage above expectation, time to throw, scramble/designed-rush split where verified, pressure-related splits where licensed |

Receiving yards per game and target share must be directly sortable. Show the richer existing first-read and air-yard metrics in table columns, once their coverage and denominators are audited. Keep default column sets manageable; the column picker exposes depth.

**Acceptance:** a user can answer "Which available WRs have the highest target share, and how do their yards per game compare?" without opening every player. Adding a player to Compare and closing their card preserves the research state. Card, table, and export/API values—if exports exist—agree.

## 5. Establish a shared metric dictionary and copy standard

Use **per game**, **per target**, **per route run**, and **per attempt** consistently. Replace current phrases such as "targets a game," "points a game," and "yards a target." Audit headings, chart labels, tooltips, summaries, accessibility labels, and generated text. Compact headers can use understandable abbreviations with full-name definitions.

| Label | Required meaning |
|---|---|
| Receiving yards per game | Receiving yards divided by games played in the selected sample; specify how an appearance is counted |
| Target share | Player targets / eligible team targets for the same selected games; define exclusions and handling of missed games |
| Carry share | Player qualifying rush attempts / team qualifying rush attempts in the same games; explicitly document kneel-down and other exclusions |
| RB backfield carry share | Player carries / carries by the team's RBs; keep separate from team carry share, which includes other eligible rushers |
| Route participation | Routes run / team dropbacks in the relevant sample, following the chosen provider's definition |
| Targets per route run | Targets / routes run from compatible, matched coverage |
| Yards per route run | Receiving yards / routes run from compatible, matched coverage |
| First-read target share | Publish the exact numerator and denominator supplied or derived; do not imply knowledge of every first-read assignment from targeted-play data alone |
| Red-zone share | State share of what: carries, targets, or opportunities, and the denominator/location rule; avoid an unexplained combined percentage |
| Expected fantasy points | Opportunity-based estimate if that is the actual model; distinguish it from points projected for a future week |

For multi-game shares, use the ratio of summed numerator and denominator, not an unweighted average of weekly percentages. Define aggregation for every rate. Show sample size, source/coverage, and refresh time in the help layer. A three-game season should not make "last 5" look like five observed games.

Kyren's Carry share currently appears as a disabled metric control while adjacent stats have explanations. Supply its definition and denominator through the shared dictionary.

## 6. Separate roster contribution from acquisition benefit on Season

The current **Value to my lineup** defaults to Everyone. Its own explanation uses two different counterfactuals: an owned player's value is what the lineup loses without him; someone else's value is what the lineup gains if he is added with **nobody dropped**. Bijan led the default view at roughly **+124**, although he belongs to another team. The arithmetic may be useful, but one label makes the results easy to misinterpret.

Use three clearly named views:

1. **My roster outlook** — default. Owned players, expected starts by week, contribution to legal starters, bye coverage, and usable depth. Preserve the original roster-aware objective.
2. **Potential upgrades** — other players. Clearly label hypothetical lineup improvement **before acquisition cost**. Free agents lead into an add/drop comparison; rostered players lead into a trade comparison that subtracts outgoing assets and required drops.
3. **Rest-of-season projections** — research ranking, with total points, points per game, expected games, range, and playoff-window totals.

Do not relabel hypothetical starter-point gain as market/trade value. A reserve with few expected starts can still offer contingent injury cover or have value to another roster; expose that separately without inflating current-lineup contribution.

**Acceptance:** an owner can immediately tell whether a number describes their existing team, an acquisition scenario, or raw projected scoring. Acquisition results state the counterfactual and costs included. All views use actual league slots and playoff weeks.

## 7. Make news a decision-impact feed

The homepage's Puka hip update is relevant and sourced, but it leaves the manager to decide whether it changes the recommendation or is already reflected in the projection. A generic footer said "Updated 1d ago" while injuries had a current check time and news was three hours old. Separate those clocks.

Each high-priority news item should contain:

- **What changed:** a short sourced fact, with event time and publication/verification time where available.
- **Why it matters here:** affected player(s), this league's roster/lineup or a watched waiver/trade target.
- **Decision status:** recommendation changed / watch for confirmation / no action currently indicated.
- **Forecast status:** included in the current projection, context only, or update pending. Never claim inclusion without a recorded update.
- **Next step:** inspect the player, compare alternatives, or view the relevant matchup.

Rank by decision relevance and urgency, deduplicate reports of the same event, distinguish new developments from game recaps, and allow expansion into the source detail. Keep news concise on the homepage; deeper evidence belongs in the player viewer.

For defensive matchups, combine the existing historical scoring baseline with expected personnel, injuries, and role/alignment context when supported. If key defenders change, flag that the historical sample may be less representative. Do not automatically turn "two corners out" into an invented point bonus. Preserve the current disclosure when personnel is contextual rather than modeled.

**Acceptance:** a key-defender-out fixture surfaces beside the positional matchup rank; stale historical averages cannot silently masquerade as a fully current matchup assessment. An injury report already priced into the projection is not double-counted. Missing/unverified news reduces confidence rather than creating a fabricated recommendation.

## 8. Tighten the homepage, Team, League, and waiver presentation

- **Homepage:** put the few consequential decisions first, then changes to watch, then lineup status. Collapse long alternative-drop explanations. Maintain access to all evidence in the drawer/details.
- **Waivers:** distinguish **helps this week / covers a future bye / upside stash**. The current top-three introduction says each adds value "this week," although the displayed leaders say no change this week and gain over weeks 4–7. Label the horizon where the benefit is shown. Identify alternatives that compete for the same drop/roster slot; a set of individually evaluated claims is not an executable combined plan.
- **Team:** retain the overall layout, repair benchmarks, show all required starter slots, and define "Depth (bench alone)." Raw bench point totals can overrate unusable surplus at one position.
- **League:** keep all-play and schedule-luck analysis. Replace "It evens out over a season" with language that does not promise convergence. Label bench-points hindsight as hindsight; hindsight-optimal scoring is different from an avoidable decision based on information available before kickoff.
- **Player card:** replace "Upside: nothing beyond the projection above" with "No additional modeled upside scenario available" when that is the actual meaning. An absent modeled scenario does not establish an absence of football upside.
- **Navigation:** "Players" inside "Players" hides the stats table's purpose. The Stats/Trends/Matchups/Compare naming above should remove this ambiguity.

## 9. Simplify onboarding and add accounts/profiles

The inspected entry screen still has separate Sleeper and MFL boxes. Use one **Fantasy platform** selector followed by the appropriate field or connection action. The owner's desired simple first step is right; every provider cannot necessarily use a username-only workflow.

Proposed flow: **Choose platform → enter the required identifier or connect → select season/leagues → select your team → land on My Team.** Explain where to find a league ID with a brief inline example. Validate and show specific recoverable errors. Keep guest exploration available; offer an account when saving leagues.

An account should save multiple provider connections, selected leagues/teams, a default league, watchlists, and table preferences. The profile needs a compact league list showing provider, season, league name, selected team, scoring/format, last successful sync, and connection status. Returning users should not repeat onboarding.

Implementation requirements:

- Separate League Lab sign-in identity from external league lookup/connection records. A public Sleeper username lookup is not proof of account ownership.
- Persist stable external identifiers. Namespace leagues by provider and season, and preserve team selections per league.
- Use reusable provider adapters with explicit capabilities for scoring, roster slots, matchups, players, waivers, transactions, and team assets. Unsupported data should be clearly unavailable rather than silently substituted.
- Scope user preferences and private league data correctly; shared public-player caches must not leak account-specific data. Support disconnect, expired-connection recovery, and idempotent background sync.
- Initially sync/read leagues. Sending trades or submitting claims is a separate product capability requiring explicit user action and provider support.

### Provider plan

| Provider | Next action |
|---|---|
| Sleeper | Preserve current integration; use stable user IDs after username lookup. Its documented API supports read-only access and league lookup, but current docs call for commercial licensing contact for commercial use. [Official API documentation](https://docs.sleeper.com/) |
| MyFantasyLeague | Preserve the working integration and validate unusual scoring, roster rules, team-QB assets, and league 70587 in regression testing. Confirm its provider-specific connection requirements before redesigning the form. |
| ESPN | Treat as an explicit priority from the owner. Run an access/authentication feasibility task covering public and private leagues, synchronization, scoring, and permitted use. This review did not establish an official supported OAuth integration. Public/private league visibility is documented, but visibility alone is not an integration contract. [ESPN support](https://support.espn.com/hc/en-us/articles/360000991871-Making-a-Private-League-Viewable-to-the-Public) |
| Yahoo | Evaluate as another early adapter: official developer material describes OAuth access and an application process. Confirm approval and granted capabilities before promising support. [Developer access](https://sports.yahoo.com/developer/access/) · [Documentation](https://sports.yahoo.com/developer/docs/) |
| Other platforms | Add after a capability/access assessment and evidence of demand. Do not display a supported badge for a placeholder integration. |

Do not make pasting browser session cookies the normal ESPN onboarding experience. If an authorized, maintainable private-league connection is not established, state the limitation and support only what is actually verified.

**Acceptance:** one account can save and switch multiple leagues/providers without mixing scoring or teams; a failed sync in one league does not break the others; reconnecting does not duplicate leagues; returning on another device restores saved selections.

## 10. Audit and expand the advanced-data layer

Start with a field inventory across ingestion, storage, feature engineering, models, and UI. For each metric record: identifier, definition, numerator/denominator, source, history/current-season coverage, refresh cadence, missingness, permitted use, model use, and existing UI exposure. Mark **verified present**, **derived**, **planned**, and **unavailable** separately. A variable mentioned in a model specification is not evidence that a current feed supplies it.

### Practical data options checked on October 4

| Data path | Useful additions | Important boundary |
|---|---|---|
| Existing app data + play-by-play/player stats | Carry/target shares, per-game volume, air-yard measures, red-zone/inside-the-5 usage; validate and derive the requested columns | Inspect actual coverage and join quality. "Available publicly" and "already ingested in this app" are different claims. |
| nflverse schedules/feeds | Historical and current statistical foundations; documented update schedules | Its participation data from 2023 onward is released after the postseason, not during the season. Do not build a current weekly routes feature on the assumption that this feed is live. [Availability schedule](https://nflreadr.nflverse.com/articles/nflverse_data_schedule.html) |
| nflverse FTN charting subset | Catchable/contested targets, drops, read-thrown and other charted play context | Audit the dictionary and available games. Targeted-play charting does not by itself supply every receiver's routes-run denominator. [Charting dictionary](https://nflreadr.nflverse.com/articles/dictionary_ftn_charting.html) |
| NFL Next Gen Stats through nflverse | Receiving separation/cushion and YAC above expectation; rushing yards over expected per attempt; QB completion percentage above expectation/time to throw | These are contextual aggregates, not pure player talent scores. Respect qualification/coverage and aggregation rules. [Metric dictionary](https://nflreadr.nflverse.com/articles/dictionary_nextgen_stats.html) |
| Licensed routes/participation feed | Routes run, route participation, targets/yards per route, and supported alignment/coverage splits | Obtain a sample and confirm exact fields, history, turnaround, coverage, display rights, and model-use rights before implementation. |

PFF now documents an API requiring **PFF Pro**. Its consumer/API terms restrict use to personal, nonpublic purposes and contain additional AI/data-use restrictions; a consumer subscription must not be assumed to license this public platform or its model. Establish appropriate permission before integrating it. [API guide](https://developer.pff.com/guide/) · [Current terms](https://www.pff.com/terms)

FTN offers a commercial charting/participation API. Its published starting price is **$5,000 annually for commercial use**, with use-case-dependent pricing; its FAQ describes roughly 24-hour charting turnaround and partner display permission with an exception for DVOA. This is an option to evaluate, not a purchasing recommendation. [FTN data](https://ftnfantasy.com/stats/sports-data)

At the owner's earlier low subscription-price target, first expose the useful data already present and measure demand. Budget licensed feeds separately from hosting/model costs. Do not commit to a data contract merely to populate a column whose decision value has not been demonstrated.

### Analytics worth developing after the inventory

- **Role changes:** trend in carries, targets, snaps, and verified routes, with sample-aware comparison to the player's own earlier role.
- **Opportunity versus production:** identify scoring supported by volume versus unusual conversion; label observed gaps without assuming automatic regression.
- **Contingent upside:** explicit scenarios such as a teammate being unavailable or a sustained role increase. Show assumptions and probability only when defensible.
- **Roster-specific value:** legal starting contribution, coverage, and marginal acquisition effects, distinct from market value.
- **Personnel-aware matchups:** historical baseline plus current personnel and supported role/coverage context; quantify adjustments only after validation.

Validate model additions with chronological, as-of-week evaluation. Features released after the decision date must not leak into a backtest. Compare incremental performance with a simple baseline, evaluate uncertainty calibration, and measure recommendation usefulness under real roster/waiver constraints. A more complex model is not sufficient evidence of better decisions.

## 11. Release checks and agent deliverables

Ask the implementing agent to return:

1. A short inventory of existing reusable UI/data/model components and confirmed gaps.
2. A small sequence of changes in the delivery order above, with the relevant acceptance checks attached.
3. Demonstrations of the shared drawer from Players, Waivers, and Receivers; sortable WR/RB presets; clarified Season views; and news forecast-status labels.
4. Correctness evidence for the benchmark discrepancy, legal replacement chains/locks, both-team waiver-aware trade evaluation, and the Folk regression example.
5. An account/provider capability matrix and an explicit ESPN feasibility outcome, rather than a vague "integration added."
6. A source/coverage/licensing inventory for new advanced columns, including the actual source of any routes data.

Do not fabricate current metric coverage, model quality, successful provider support, or trade acceptance probabilities. Use existing components where they work and keep the owner's analytical depth available through tables and player details.

## Verified live review links

These links capture the league/team context inspected; dynamic recommendations can change after data refreshes.

- [MacZaddy home](https://league-lab.onrender.com/?league=1389709692405551104&team=2)
- [Season](https://league-lab.onrender.com/ros?league=1389709692405551104&team=2)
- [Team](https://league-lab.onrender.com/team?league=1389709692405551104&team=2)
- [League](https://league-lab.onrender.com/league?league=1389709692405551104&team=2)
- [Waivers, available WRs](https://league-lab.onrender.com/waivers?league=1389709692405551104&team=2&view=all&position=WR)
- [Trade finder](https://league-lab.onrender.com/trades?league=1389709692405551104&team=2)
- [Receivers](https://league-lab.onrender.com/receivers?league=1389709692405551104&team=2)
- [Players table, WR target-share sort](https://league-lab.onrender.com/players?league=1389709692405551104&team=2&position=WR&sort=target_share&dir=desc)
