# League Lab / isuckatfantasy: competitive review and next design iteration

Reviewed October 10, 2026, approximately 9:42–9:55 PM Eastern. Prepared for Andrew and the development agents.

## Recommendation

Build the clearest way to understand what a fantasy decision changes in your actual league: who starts, who sits, what you give up, what you could do instead, and what new information could reverse the decision.

The current product is materially improving. Player drawers, sortable advanced stats, cornerback-change warnings, waiver alternatives and rejection of implausible trades are already present. Preserve those capabilities. The next iteration should make their meaning obvious and their strength of evidence consistent.

Roster awareness is a necessary feature, not an exclusive advantage. VegasLytics now has a working league-imported trade optimizer with before/after lineups, drops, waiver fills and market-value checks. A claim that other calculators universally ignore rosters would be inaccurate. The opportunity is better decision comparison, contextual evidence and usability. Superiority remains a hypothesis until independently tested.

## Review scope and limits

Inspected the live League Lab Sleeper dashboard, player stats and Michael Wilson drawer, trade finder, known Folk/Stafford/Reichard calculator case, matchups and waivers. Also loaded Big Mac Attack in MFL league 70587. Inspected all five supplied competitor sites visually and through their visible controls. Imported the public League of Scrubs ID into VegasLytics, selected MacZaddy and expanded its free first trade. No trades or waiver claims were submitted. No accounts, subscriptions, credentials or uploads were created. No production code was changed.

YUFA review covers provider selection, the Sleeper username entry screen and manual-import instructions, not its downstream private analysis. VegasLytics paid recommendations were not opened. This is a product and interface review, not a model accuracy comparison, mobile-device audit, load test or renewed source-code dependability audit. Numbers are snapshots that can change after refreshes. Competitor marketing claims and League Lab's validation disclosures were not independently reproduced.

## What to learn from each competitor

| Product | Observed strength | What to adopt | Where League Lab could do better |
| --- | --- | --- | --- |
| YUFA | One provider choice followed by one task. ESPN and Sleeper buttons, disabled Yahoo with explanation, manual option. | Progressive onboarding: provider → required identifier → league → team. Clear unsupported-provider states. | Confirm imported scoring and roster slots before offering advice. Manual fallback should validate extracted rosters rather than require blind trust in an AI response. |
| VegasLytics | Vegas-prop projections, changes from initial odds, missing-prop disclosure, league-imported trade optimizer with actual lineup effects. | Compact send/receive cards, two-sided before/after consequences and explicit market-value checks. | Compare trades against genuinely obtainable alternatives; distinguish market price, roster benefit and plausibility; treat missing forecasts as unknown. |
| First Down Studio | Readable rankings table: position tabs, search, scoring, stat columns, tier dividers and differences from expert consensus. | Calm table styling, restrained controls, visible tiers and sortability. | Attach the ranking to the user's actual eligible slots and replacement options; make advanced research immediately useful to a roster decision. |
| Fantasy Gridiron | Compact team-by-position matchup matrix; Usage table with carries, targets, target share, red-zone touches, goal-line carries and snap share. Player timelines and roster-import controls are visible. | Efficient matchup scan, a small set of meaningful usage columns, time windows and definitions. | Surface changed personnel next to historical matchup grades and connect the evidence to a real start/sit or acquisition choice. Do not infer defensive assignments from target direction alone. |
| Fantasy Football Tiers | Clearly teaches same-tier decisions and separates consensus ordering from upside. Position/scoring charts and accompanying tier text. | Close-call groups and explicit distinctions between expected points and upside. | Show only the user's relevant options, with plain-language reasons and calibrated uncertainty. Dense charts can remain optional research. |

Do not clone the combined feature inventory. More themes, tabs and dashboards would increase the burden of finding an answer. These sites demonstrate useful individual patterns, not a requirement to reproduce every screen.

## Current app: progress worth preserving

- The dashboard puts a specific close call first: keep Boston over questionable Jefferson for now, with status recheck before kickoff and acknowledgement that the change is already in Sleeper.
- Player links open an in-context side drawer. Michael Wilson had Overview, Usage, Game log and News tabs, compare and full-page actions. This addresses the earlier request to avoid repeatedly leaving the research table.
- Stats now expose sortable target share and many deeper measures. Per-game wording has been corrected. A 14-column receiver key-stat view and an optional 97-column full view are available.
- The Wilson profile explicitly flags changed Detroit corners, dates the injury source and says the historical defense rank is unadjusted and personnel context is not in the forecast. This is meaningful progress on the original matchup/news criticism.
- Trade Finder says no compelling trade was found rather than inventing an appealing offer. It compares both teams with their alternatives and rejects implausible packages.
- The previous Folk → Stafford + Reichard example now has a consistent primary replacement basis. Top and detailed main figures were +3.1 for MacZaddy and −6.5 for Run Bijan Run over weeks 5–8. Its text correctly described Maye replacing Stafford at QB and Folk replacing Reichard at K. It remained implausible and inferior to MacZaddy's modeled waiver alternative. These specific earlier defects should not be reported as still unfixed.
- Big Mac Attack loaded with its unusual team QB, team K and WR/TE roster slots. That is useful league specificity, although advice still needs clearer uncertainty handling.

## Problems reproduced in this pass

### 1. The dashboard asks the reader to reconcile several matchup forecasts

MacZaddy's header displayed 125 versus 105, followed by 50% with 118 versus 117 and one player on each team having played. It also showed best lineup 125.07. These may describe different lineups or include live actuals differently, but the labels do not make that distinction clear.

The recommendation said Boston was already in the Sleeper lineup; the table headed “Your lineup” displayed Jefferson at FLEX2 with a note that the call keeps Boston there. This may be a model-optimal lineup, but the user has to discover that interpretation.

**Required:** One primary matchup view. Label it “Live matchup: actual points plus forecasts for remaining players” when that is its basis. Put “Best projected lineup” in an optional comparison. Name the lineup table “Current Sleeper lineup” or “Recommended lineup,” according to its actual contents. Do not place an optimal lineup under an ambiguous ownership label.

### 2. Statistical power is exposed before the user chooses a question

The Stats screen initially opened for this browser with 97 columns and a long row of group toggles. It also showed both global and local player search. The receiver key-stat preset improved it, but 14 metrics plus identity/ownership is still a wide first view.

**Required:** Start with six to eight relevant metrics, retain the full table, and make custom views discoverable after the user enters research. Suggested presets: Production, Opportunity, Role changes, Efficiency, Advanced. Persist preferences by view and position so choosing an exhaustive QB view does not force an exhaustive WR view. Avoid asserting that the observed full-table state is every new visitor's default until that is checked.

### 3. The drawer is a long profile compressed into a narrow space

Wilson's Overview repeated projected points and ranges, then included eight percentile ratings, a plain average of those ratings, points-versus-projection history, another projection block, role, availability, value and signals. One role block required five games and said too early; another said role steady over four games using a different alert definition. Both may be technically valid, but that is difficult to understand in one overview.

**Required:** Overview contains one forecast, one roster consequence, three evidence bullets, injury/context status and the next relevant action. Usage gets the detailed role measures; Game log gets forecast history; News gets sourced updates. Define one visible role-status vocabulary. Keep different statistical detectors in methodology details. Remove the arithmetic average of unrelated percentile ratings from the primary view; it is not a validated player grade.

### 4. Horizon uncertainty conflicts with the strength of recommendations

The calculator disclosure said “two to eight weeks ahead no better than chance, quarterbacks weak; the trade's range not graded.” The same screen called the next four weeks “near enough to trust.” Waivers called Tampa Bay defense the strongest move, +4.7 over four weeks, while disclosing that defenses and kickers at those horizons are no better than chance. The precise scope and benchmark of these disclosures need confirmation from the evaluation results; this review does not establish that every position/horizon is uninformative.

**Required:** Audit the validation text against the actual metrics. Remove “near enough to trust.” For weak position/horizon combinations, present an exploratory estimate with clear uncertainty rather than “best move.” Default to a supported horizon, and avoid selling a multiweek optimizer as validated before it is. The model should be allowed to say “insufficient evidence for a confident recommendation.”

Big Mac Attack recommended Chicago team QB over Houston by approximately one point. A lower paragraph said Chicago's starter was unclear because listing and depth chart disagreed. Attach that uncertainty to the recommendation itself and use “check starter first” for a close difference until the ambiguity is resolved.

### 5. Useful caveats and research are scattered across paragraphs

Trade Finder starts with rejection counts and a waiver recommendation, then mixes fit values and production-versus-opportunity gaps. “Fit +2.6” requires interpretation. The news feed occupies a card while saying nothing has changed since the morning build. Waivers expose the internal relation name `analytics.mart_league_transactions`, which adds no user value. The matchup list switches between “gives up the 2nd-most” and “#31 toughest,” making users reverse the ranking direction.

**Required:** Use consistent units and time windows. Replace “Fit” with the calculation's actual meaning, verified against implementation. Use one matchup direction: “2nd-most points allowed to WRs.” Keep empty news quiet. Surface changes that affect a decision, with checked-at time and source, and avoid implying all news was checked when only one feed was. Remove internal storage names from product copy.

## Proposed simpler structure

Keep four primary destinations: **My Week, Waivers, Trades, Research**. Research contains Players, Stats, Rankings and Matchups. League and team stay in a persistent switcher. Move DFS under a secondary menu for this experiment; preserve its route. Optional accounts can save leagues, but should not block the first useful result.

| Screen | First thing the user sees | Detail available on demand |
| --- | --- | --- |
| My Week | One matchup summary and at most three decisions, ordered by urgency | Current/recommended lineup comparison, bench, sources and evidence |
| Waivers | Help now / Cover a bye / Stash; add/drop, when they start and why | Week-by-week effects, lost depth, fallback claims and full available-player table |
| Trades | Evaluate an offer / Find partners; a send/receive builder and one conclusion | Both slot-by-slot lineups, required cuts, waiver assumptions, market evidence and sensitivity |
| Research | Search, position, scoring, window and a compact preset table | Custom columns, advanced metrics, player drawer and compare tray |

Use a restrained neutral palette, one green primary action, consistent typography and compact row spacing. Color should emphasize changes and uncertainty, not imply that every positive model number is a good decision. Keep units visible and use one decimal for ordinary points. Maintain keyboard navigation, textual heatmap labels and adequate contrast.

On mobile, use a full-height player detail sheet with clear close/back behavior and a comparison tray; preserve table filters, sorting, selection and scroll position. This is a target requirement, not a claim that mobile behavior was verified today. Use the existing web application and components; a framework rewrite is not necessary to achieve this design.

## The trade decision that could distinguish the product

Every connected-league trade should answer these five questions in this order:

1. **What changes in my starters?** Identify each affected slot and displaced player; give weekly point effects and the chosen horizon.
2. **What does their team gain or lose?** Use the same rules and time window. Separate an understandable reason to consider the offer from a predicted acceptance probability.
3. **What is the cost beyond the package?** Required drops, usable bench depth, bye coverage, roster slots and eligibility.
4. **Could I achieve the goal another way?** Compare keeping the roster, a plausible waiver claim and the trade. Keep access assumptions visible. A future free agent cannot be guaranteed to remain available.
5. **What could change the answer?** Current injury uncertainty, role change, opponent personnel, missing data and uncertainty at the selected horizon.

Keep three dimensions separate: projected lineup benefit, estimated market price and offer plausibility. A backup QB can have little immediate starting value for its owner while still carrying market or injury-insurance value. Low current lineup contribution does not make a star free. Market estimates need a source and date; plausibility checks need league-format awareness, not a fake numerical acceptance score.

Allow a user to compare scenarios: “If this player is out,” “If the pickup is unavailable,” “If I want to retain this bench player.” Display changed assumptions explicitly. Do not manufacture injury probabilities or arbitrary numerical adjustments from news text. First implement reproducible scenarios using available data, then validate whether any automated adjustment improves forecasts.

## Analytics priorities

Use the existing data more effectively before acquiring expensive feeds. Prioritize target share, snap share, carry share with a stated denominator, red-zone/inside-five opportunities, expected points and recent role changes. Give evidence a time window, sample size and definition. Show both the observed change and whether it actually affects the forecast or remains contextual.

Routes run, route participation, targets per route and yards per route would improve opportunity analysis if trustworthy data and redistribution rights are available. Do not label snap counts as routes or derive route totals from targets. In the live full-table columns inspected, the “Snaps and routes” group exposed snap share; route columns were not visible. Check actual route coverage before retaining that group name. Missing means unavailable, not zero.

For matchups, retain the fast matrix but add a visible personnel-change flag next to affected roster players. Later evaluate opponent-adjusted position allowance, schedule strength and recency weighting against a baseline. Do not simply add a corner injury bonus to a projection that may already reflect current market news. Treat target-side tendencies as a contextual lean, never confirmed shadow coverage or a direct historical one-on-one matchup.

For upside, distinguish high-end scoring range, stable opportunity growth and contingent opportunity if a teammate is unavailable. Those are different questions. Tie each to the user's eligible slots and bench capacity. A bigger upper tail does not automatically improve matchup win probability; that requires validated distributions and dependence between players.

## Implementation order and acceptance criteria

### Pass 1: trustworthy, compact decisions

- Reconcile dashboard labels and lineup source. A tester must explain the primary matchup total and who is actually starting without opening methodology.
- Gate strong recommendations by data quality, position and horizon; resolve the four-week trust contradiction. Starter uncertainty must appear on the affected recommendation, not only below the lineup.
- Use one shared result object for trade conclusion, summary cards, weekly table and explanations. Preserve the fixed Folk example as a regression case.
- Reduce My Week to at most three decision cards and quiet empty news. Remove internal implementation labels.
- Make the same six-to-eight-column research preset work across position, search, sorting, drawer open/close and return navigation. Full stats remain available.
- Shorten the player Overview and unify visible role terminology. No duplicate projection block or unsupported overall player grade in the first view.

Acceptance: on desktop and a real mobile browser, a manager can identify the actionable decision and its main caveat within 30 seconds. Drawer close restores research context. The Folk package remains rejected; no explanatory replacement crosses positions. A small projection edge with an unresolved starter is not presented as a confident instruction.

### Pass 2: coherent alternative comparison

- Make keep / claim / trade comparable with the same scoring, horizon and acquisition assumptions.
- Add a compact two-team lineup-diff panel and explicit lost-depth/cut summary.
- Surface sourced injury/personnel changes beside the affected decision.
- Add a persistent comparison tray and meaningful preset views for production, opportunity and role changes.
- Instrument time to first useful result, task completion, misunderstanding and repeat visits. Do not treat page views or the count of simulated trades as decision quality.

Acceptance: an independent manager can explain which players enter and leave each lineup, whether a drop is needed, why the other manager might refuse and what the best alternative assumes. The manager can reach the relevant underlying metric without losing the offer or table state.

Do not expand into additional providers, a complete dynasty valuation engine, new machine-learning architectures or paid route feeds during these two passes unless a measured user blocker requires it.

## Validation and commercial implications

Have five to ten independent managers perform three real tasks in their own leagues: a start/sit close call, a waiver choice and a trade evaluation. Record whether they understand the result unaided, whether it adds information they did not already have, and whether they return voluntarily over three weeks. Ask which of the compared tools they would actually use and why. Success means improved comprehension and repeated usefulness, not praise for having many metrics.

Maintain frozen pre-kickoff forecasts and compare with provider forecasts or another licensed baseline on identical players, scoring and timestamps. Grade decision regret for close calls as well as point error; keep hindsight reconstructions separate. Evaluate longer horizons separately from next-week performance. Do not claim observed trades would have changed wins causally: the counterfactual roster and acquisition path are uncertain.

VegasLytics visibly offers a $1 weekend pass, $6.99 for 30 days without auto-renewal, $24.99 season access and $49.99 lifetime access. That establishes an observable competitor price, not evidence of purchases, profitability or demand. Avoid copying lifetime commitments before knowing recurring data and operating costs. Test a modest paid season offer only after the workflow earns return visits. A paid model needs documented data rights and a measured per-active-user cost budget; this review did not audit either.

The most promising product promise is: **“Understand what this move changes for your team, what you give up, and whether there's a better option.”** The next investment should earn evidence for that promise. A redesign can improve comprehension; it cannot establish predictive accuracy or willingness to pay by itself.

## Sources and observed pages

Primary product pages inspected directly; behavioral and pricing observations above are from the live interfaces, unless otherwise stated.

- [League Lab matchup screen](https://league-lab.onrender.com/matchups?league=1389709692405551104&team=2)
- [Known trade case](https://league-lab.onrender.com/trade-calc?league=1389709692405551104&team=2&partner=3&give=650&get=421%2C11792)
- [Big Mac Attack dashboard](https://league-lab.onrender.com/?league=mfl%3A70587&team=8)
- [YUFA supplied onboarding page](https://yufa.app/platforms); [manual flow inspected](https://yufa.app/platforms/manual)
- [VegasLytics projections](https://vegaslytics.com/); [trade optimizer tested](https://vegaslytics.com/trades)
- [First Down Studio rankings](https://www.firstdown.studio/rankings)
- [Fantasy Gridiron supplied matchups](https://fantasygridiron.io/matchups?season=2026&week=5); [usage page inspected](https://fantasygridiron.io/usage?season=2026&position=RB&period=w4)
- [Fantasy Football Tiers QB chart](https://fantasyfootballtiers.com/#QB)

The prior October 8 dependability handoff remains separate. This report records fixes reproduced today and newly observed design issues; it does not reopen or certify every prior reliability ticket.
