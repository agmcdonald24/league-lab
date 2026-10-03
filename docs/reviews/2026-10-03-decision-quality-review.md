# League Lab: decision quality and product review

*Fourth outside review, received 2026-10-03 late evening (Andrew: "next wave plus see this too"). Reviewed against
the live server at `f6315ae` (Wave I-E). Verbatim; the PO's reading is in `PROJECT_PLAN.md` § Iteration 17 "Fifth:
the decision-quality review" and the wave is I-F.*

Reviewed October 3, 2026, evening ET. Live deployment: https://league-lab.onrender.com/

## Product direction

Build for experienced fantasy managers who want better decisions with less research time. Familiarity with fantasy and comfort with software are separate dimensions. Clear navigation and plain explanations should preserve analytical depth. The product should earn its place by connecting information a manager would otherwise have to assemble across several sources.

The central product question is: **What changes my decision, why, and how much should I trust it?** A projection, a news headline, and a defensive ranking shown separately do not yet answer that question.

This review tested the live desktop interface. It covered League of Scrubs / GoodGameBuddy, the Williams–Tuten comparison, matchup details, waivers and stashes, and MFL 70587 / Big Mac Attack, including trade finder and calculator. Big Mac Attack is a test roster, not a confirmed identification of the user's father's team. No league transactions were submitted. Model descriptions below are disclosures from the deployed About page; this was not a fresh source-code or statistical audit. Mobile interaction was not tested.

## Improvements verified in this deployment

| Area | What now works | Why it matters |
|---|---|---|
| Navigation | Four main destinations, player search, contextual subnavigation | Core tasks are easier to find. |
| Player inspection | A roster click opens a player drawer with a direct comparison against the relevant starter | Preserves context and shortens research. |
| MFL trades | Houston team QB remains selected and participates in the calculated trade | The earlier silent omission is fixed in the tested example. |
| Lineup changes | Trade results explicitly show players entering and leaving the starting lineup | Avoids implying that slot renumbering changes an unchanged player's projection. |
| Trade labeling | The dial now says "Effect on their starters" | It no longer presents projected lineup gains as a manager acceptance score. |
| Alternatives and depth | Calculator identifies a free-agent alternative and notes lost backup coverage; finder identifies an unnecessary extra outgoing asset in one example | Moves toward whole-roster decisions. |
| MFL waivers | Arizona team QB no longer claims to fill a defensive vacancy; team assets have NFL team badges | Corrects misleading explanation and identity details. |
| Waiver timeframe | Current-week gains are emphasized for current-week moves | Easier to distinguish a weekly gain from a four-week total. |
| Close calls | MFL combines Nabers/Addison versus McConkey into one injury-dependent decision | Less repetitive and more actionable. |
| Upside stashes | Shows role changes, an injury connection, the limited sample, and a clearly labeled what-if | This is an existing foundation worth expanding. |

The earlier Tuten-versus-Williams close-call sentence was **not displayed on the current GoodGameBuddy home screen**. The screen instead said the lineup was set. The underlying comparison and historical matchup rank remain accessible.

## Priority 1: connect historical matchup evidence to current personnel

### Verified case: Jameson Williams at Carolina

The deployed app displayed:

- Tuten 10.02 projected points and Williams 9.80 in League of Scrubs scoring: a 0.22-point difference.
- Williams at Carolina, ranked #31 of 32 against WRs, with #1 defined as allowing the most points.
- In Matchups → bench receivers, the expected Carolina corners were **Will Lee III and Akayleb Evans**, both unranked for insufficient snaps.
- No explanatory connection between those replacements and the historical WR matchup ranking on the comparison/player card.

The Panthers officially announced on **September 30, 2026** that **Jaycee Horn and Mike Jackson went on injured reserve**. Their October 3 update identifies Evans and Lee as the replacement starters. Thus, some current personnel information is already reflected inside League Lab, but the recommendation surfaces do not reconcile it with the historical ranking.

This is a demonstrated explanation gap. The live UI alone does not prove whether, or how much, the numerical model already incorporates the injury through other inputs.

### Required behavior

Show three distinct pieces of evidence:

1. **Historical results:** Carolina has allowed relatively few WR fantasy points in the available sample. Show games, scoring, period, and whether adjusted for opponents.
2. **What changed:** Both starting corners are on IR; identify the replacements, source, and effective date.
3. **Decision implication:** The historical ranking is less representative of this week's personnel. State whether this information is included in the forecast, is only contextual, or is awaiting a model update.

Do not automatically flip the recommendation or invent a fixed points bonus. Replacement quality, coverage structure, receiver role, pass rush, projected volume, and other model inputs may matter. The safe first improvement is to stop using an unqualified historical rank as a decisive tiebreaker.

Suggested explanation structure, **illustrative copy rather than a new forecast**:

> Tuten 10.0; Williams 9.8 — effectively even by the baseline projection. Carolina's strong historical WR results came with different starting personnel: Horn and Jackson are now on IR. The app lists Lee and Evans as replacements, with too little evidence for a reliable cornerback grade. Treat the historical matchup penalty cautiously. Show each player's role evidence and the forecast's treatment of this news before making the call.

### Engineering requirements

- Store structured events keyed to player, team, and game IDs, with source URL, publication time, effective time, ingestion time, status, and superseded status.
- Link defensive events to relevant offensive matchups; offensive events to teammates and opponents. A news feed attached only to the injured player's own card is insufficient.
- Attach the relevant evidence and prediction version to every recommendation. Expose whether each material event is included in the numerical forecast.
- Detect conflicting evidence: strong historical defense versus substantial personnel change; large snap increase versus unchanged route participation; usage decline versus recent touchdowns.
- Use a shared decision result across home, player, comparison, waivers, and trade views. Do not independently generate incompatible explanations.
- Language generation may summarize verified facts and calculated scenarios. It should not invent effects or select unverified football facts to justify an already chosen answer.

**Acceptance test:** With both starting corners on IR in an as-of fixture, Williams's comparison must flag the changed personnel, cite the event, identify its forecast treatment, and avoid presenting the old defensive rank as a conclusive reason to sit him.

## Priority 2: value the bench before prescribing drops

GoodGameBuddy's headline recommendation was:

> Claim Daniel Carlson, drop Marvin Harrison Jr.: about 2 more starter points this week.

Its reason was "he sits anyway." Carlson would replace Evan McPherson at kicker, but the recommended drop was Harrison. The waiver page repeatedly selected the same drop for different claims, and the stash page recommended dropping Harrison for players whose conditional scenario still generated zero starting-lineup improvement over weeks 4–7.

This is not a claim that Harrison must be undroppable based on name recognition. It is a failure to establish why that drop is better than releasing the displaced kicker or making no move. A player can have zero immediate starting contribution and still provide injury cover, future starts, an uncertain expanding role, or trade value.

### Required behavior

- Evaluate each legal add/drop pair, including replacing the incumbent at the same position. Respect locks, roster limits, provider rules, and protected players.
- Separate **starter gain**, **depth lost**, **future starting opportunities**, **upside scenarios**, and **roster flexibility**.
- Evaluate multiple future availability/role scenarios instead of assuming today's depth chart and mean forecasts remain certain.
- Use available replacement players to measure scarcity. Backup QB3 value differs sharply between 1QB and superflex; team QB scoring needs its own replacement baseline.
- Show the best drop, at least one reasonable alternative, and why the chosen option is preferable.
- Keep watchlist candidates distinct from recommended claims. A growing role alone does not establish that acquiring the player is worth sacrificing the proposed drop.
- Include "no worthwhile move" when expected gains are too small or uncertain relative to roster cost.

**Acceptance test:** Carlson versus McPherson must be evaluated as a legal direct replacement when allowed. Recommending a different drop requires an explicit roster-value reason. "Does not start in the next four weeks" alone cannot establish disposability.

## Priority 3: make trade recommendations compete with simpler alternatives

The current MFL finder headlines Houston team QB for Rashee Rice plus Carolina team QB. Finder and calculator now agree: about **+1.0 this week / +9.8 over weeks 4–7** for Big Mac Attack, and **−4.8 / +8.7** for the partner.

However, the calculator itself identifies available Arizona team QB as worth approximately **+11.4 over the same four weeks**, and the waiver screen says this roster has an open spot. This does not prove the trade is worse under every longer-term objective, but its headline recommendation needs to acknowledge the stronger, lower-cost alternative under the displayed objective.

The earlier Houston team QB plus Tuten for Rice package now calculates correctly. It also illustrates a new concern: the calculator says "you get more season value" and then warns against giving 492 rest-of-season raw points for 164. Those appear to describe different value concepts without naming them. Raw point totals across positions and package sizes cannot substitute for roster-aware valuation.

### Required behavior

- Evaluate standing pat, best legal waiver move, and trade under the same horizon and scoring rules before ranking recommendations.
- Surface the extra benefit from trading beyond the best alternative. Where the trade does not beat a waiver, show why it may still help a different objective, or demote it.
- Preserve separate concepts: projected points, points that enter a legal lineup, depth/contingent value, and observed trade-market value if a real source exists.
- Remove blanket cross-position raw-point thresholds as the main fairness test. Normalize against replacement and account for bench cost and package size.
- Show actual starter changes on both sides and the weeks driving each gain. A four-week win can conceal a substantial loss this week.
- Explain trade search ordering. In the reviewed finder, the top headline and the first listed card were different trades; the ordering criterion was not apparent.

**Acceptance test:** For this saved MFL state, the finder must show that the Arizona team QB claim beats the headline trade on four-week starter points, or explicitly identify the additional objective that justifies preferring the trade.

## Priority 4: use clarity to expose the difficult decisions

The interface is visually calmer. Keep the main navigation and contextual drawer. Avoid reducing the home page to a single routine transaction and a blanket "nothing to change" when a meaningful close call exists.

Recommended home-page content:

- **Decisions worth reviewing:** close calls, material news conflicts, and a worthwhile roster move, ranked by relevance and uncertainty.
- **What changed since your last visit:** a small number of changes that affect this roster, with sources and timestamps.
- **Your lineup:** starters and bench, with a direct comparison at the relevant eligible slot.

For GoodGameBuddy, Williams versus Tuten should remain discoverable when the current starting lineup equals the projection optimizer's output. "No clear upgrade" is a more accurate conclusion than "nothing to change." A correct optimizer output does not eliminate uncertainty.

Keep the drawer focused on the decision: current role, recent change, matchup context, forecast uncertainty, and compare action. The current drawer contains much of the full player page, including a long week-by-week projection paragraph. Move the full season ledger and methodology to the full page or expansion controls.

### Specific interface and language fixes

| Observed issue | Recommended change |
|---|---|
| The expanded "bench" section repeats all starters before showing the bench | Show the bench directly or use a single roster table with sections. |
| "Margin" repeats an entire projection when no eligible reserve exists | Label the comparator; distinguish an empty replacement slot from an actual player alternative. |
| Matchup rank direction changes between screens | Standardize one direction everywhere and always label it; prefer "2nd-fewest WR points allowed" to an unexplained #31. |
| Comparison bolds "the better number" across RB and WR rows | Highlight decision-relevant differences; more carries for an RB is not inherently a reason he is better than a WR. |
| Three-game season and last-three-game sections duplicate one another | Collapse identical periods and show the sample size once. |
| Player page says "Typical range," comparison/About still say "most weeks" for the middle 50% | Standardize the label and explain the actual interval. |
| Some advanced metric tiles are disabled and lack definitions | Make definitions available without making non-actionable statistics appear broken. Explain the denominator of first-read and red-zone share. |
| "No role change detected" sits beside "not enough games" | State which comparison is valid and what evidence is insufficient; absence of a detected change is not proof of stability. |
| "Expect him to pick up" follows below-expected historical scoring | Describe underperformance and uncertainty; do not promise regression or label a buy-low without price evidence. |
| News on Williams's card uses a broad headline about DeVonta Smith | Surface the player-relevant fact or excerpt with the source, not just an article-level headline. |

## The analytics worth building next

Prioritize measures that distinguish two plausible choices:

1. **Role quality:** route participation where a current, licensed source provides it; targets per route; first-read opportunity; receiving versus blocking snaps; two-minute and goal-line work. Show sample and freshness. Do not silently substitute snaps for routes.
2. **Matchup relevance:** opponent-adjusted historical performance, current personnel, outside/slot or role context when supported, and uncertainty. Passing-target direction is a proxy, not verified coverage assignment; shared time on the field is not a one-on-one matchup record.
3. **Conditional upside:** what has to happen for a player to become a starter, how large that role could become, and what evidence would invalidate the scenario. The current stash what-if is a good starting point. Avoid assigning unsupported probabilities.
4. **Roster opportunity:** how often the player would enter this particular legal lineup across upcoming weeks and plausible roster changes. Preserve bench and injury-cover value.
5. **Game objective:** eventually compare expected points with matchup win probability using calibrated joint outcomes, realized points, locks, and player correlations. Do not turn "underdog" into an automatic instruction to chase the player with the highest individual ceiling.

## Model validation and release gates

The deployed About page discloses per-stat gradient-boosted models, walk-forward grading, ranges, and current-season results. That is more useful than a generic "AI-powered" claim. Those disclosures do not independently establish that the news layer, trade suggestions, or waiver drops improve decisions.

The same page says the public record freezes at the week's first kickoff and that news after the morning refresh is not known. Audit the distinction between a frozen evaluation snapshot and the forecasts actually served later in the week. Sunday-relevant news needs an explicit freshness policy, even if Thursday snapshots remain available for a separate benchmark.

Use frozen as-of inputs, event timestamps, model versions, and per-game forecast records. Prevent post-outcome information from entering replay tests. Evaluate close-call decisions against sensible baselines; measure lineup points gained, decision regret, probability calibration, and results on news-affected cases. Include harmful-drop cases and provider-specific roster rules. Do not use one successful injury anecdote as evidence of a general quantitative adjustment.

MFL currently displays model grades using another league's scoring and says no direct projection record exists for this MFL league. Put that qualification next to the headline grade, not only below the metrics.

### Proposed next iteration

**First:** correct drop selection, connect personnel changes to matchup explanations, retain meaningful close calls, and reconcile shared value labels.

**Then:** compare trades with the best legal waiver alternative before ranking them, and create a single evidence-backed decision card used consistently across screens.

**Afterward:** add deeper role data and calibrated conditional scenarios only where coverage and testing support them. More statistics are valuable when they improve a decision or reveal why uncertainty remains.

## Verified review links and news sources

- [GoodGameBuddy dashboard](https://league-lab.onrender.com/?league=1389709692405551104&team=6)
- [Williams–Tuten comparison](https://league-lab.onrender.com/compare?a=00-0037240&b=00-0040719&league=1389709692405551104&team=6)
- [Matchup view inspected](https://league-lab.onrender.com/matchups?league=1389709692405551104&team=6&a=00-0040719&b=00-0037240)
- [GoodGameBuddy stashes](https://league-lab.onrender.com/waivers?league=1389709692405551104&team=6&view=stash)
- [Earlier MFL trade, now correctly calculated](https://league-lab.onrender.com/trade-calc?league=mfl%3A70587&team=8&partner=12&give=mfl%3A0682,12490&get=10229)
- [Current headline MFL trade](https://league-lab.onrender.com/trade-calc?league=mfl%3A70587&team=8&partner=12&give=mfl%3A0682&get=10229,mfl%3A0677)
- [Panthers official September 30 IR announcement](https://www.panthers.com/news/panthers-place-jaycee-horn-and-mike-jackson-on-injured-reserve)
- [Panthers October 3 roster update, including replacement corners](https://www.panthers.com/news/panthers-place-wide-receiver-xavier-legette-on-injured-reserve-lions-sunday-night-football-jalen-coker-status)

Live projections and recommendations can change after this review. Reproduce these cases from a captured fixture as well as the live application.
