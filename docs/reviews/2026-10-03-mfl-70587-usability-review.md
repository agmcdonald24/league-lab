# League Lab: casual-user review and development handoff

*Third outside review, received 2026-10-03 evening (Andrew: "had my outside agent review again, taking like a
perspective of my dad … just incorporate that. I don't want to lose sight of all the other waves and all the plans
that we have … squeeze it in"). Reviewed against the live server at `042f199` (Wave I-C), before Wave I-D (team
units on Season / Team / the League screen, the news line) reached it. Verbatim; the PO's reading is in
`PROJECT_PLAN.md` § Iteration 17 "Fourth: the casual-user review" and the wave is I-E.*

Reviewed October 3, 2026, afternoon Eastern time, on the live Render deployment.

**Goal:** A manager who knows football but does not enjoy analytics should be able to identify a useful action, understand its consequence, and carry it out without an explanation from the developer. Keep the deeper analytics available for users who want them.

**Scope:** Desktop walkthrough of MFL league 70587, Make Football Great Again. Big Mac Attack (team 8) was the example roster; the owner has not confirmed that it is his father's team. This was a live UI review, not a source-code audit, forecast validation, mobile test, or recommendation to make the displayed trades. No league transactions were submitted.

## What has improved

- The four main destinations—My Team, Waivers, Trades, Players—are much clearer than the previous navigation.
- Weekly cards now distinguish close calls and already-set choices, provide a reason, and offer direct comparison links.
- Waivers now has Help now, Bye coverage, Stashes, and All available views.
- Trade exploration and the calculator have separate destinations; detailed lineups can be expanded.
- Player pages retain the main navigation.
- MFL lookup by league number worked. After choosing a team, opening the app again returned to that team.
- Team QB, team kicker, combined WR/TE slots, and a double-header matchup are visible in the MFL dashboard.

Keep these improvements. The next release should emphasize correctness, clearer meaning, and fewer competing decisions.

## P0: correct MFL behavior before asking a casual user to rely on it

### 1. The trade calculator loses an MFL team-QB asset

**Reproduction:** Open Big Mac Attack, go to Trades, and choose the headline proposal: Houston Texans QB plus Bhayshul Tuten for Rashee Rice from Madeyes Revenge. Click "Try this trade."

The Finder displayed +0.7 this week and +9.5 across weeks 4–7 for Big Mac Attack. The calculator opened with only Tuten selected on the give side, even though the URL included the Houston team-QB identifier. It analyzed Tuten for Rice, displayed +4.6 this week and +13.3 over four weeks, and changed the verdict to "No deal," 0/100.

Manually checking Houston Texans QB changed the checkbox and URL, but the summary still said only Tuten, the result stayed the same, and the after-trade lineup still included Houston. The detail described the package as a one-for-one trade.

**Required outcome:** The selected assets, URL, request, response, summary, roster-size change, and before/after lineups must describe the identical trade. Treat provider-prefixed IDs as opaque identifiers. The UI evidence suggests an identity-handling problem; the exact cause needs code inspection.

**Acceptance:** Test Finder-to-calculator navigation, manual selection, reload, and shared links with ordinary players, MFL team QBs, team kickers, and defenses. Never silently discard an unsupported asset; show an explicit unavailable-analysis state instead.

### 2. A team quarterback is described as filling a defense vacancy

The second "three strongest moves" card on Waivers named **Arizona Cardinals QB**, tagged TMQB, and said it fills the empty DEF slot in week 7 when Jacksonville is on a bye. The Bye coverage view itself listed defenses.

**Required outcome:** Generate the explanation from the actual lineup changes produced by the evaluated move. A generic team need must not be attached to an unrelated candidate.

**Acceptance:** Every named incoming asset is eligible for the stated slot and actually fills it in the evaluated lineup. No QB-to-DEF explanation. Check team QB, team kicker, combined WR/TE slots, and bye-week cases.

### 3. MFL identity and data-availability copy is inconsistent

Observed on Tuten's player page:

- "On the bench in Sleeper" while reviewing an MFL roster.
- "Sleeper's number for this week is not in yet."
- A chart states 12.0 points per game, while another message says his points per game in this league are not shown yet.

Team QB and kicker entries in the trade calculator also carried an FA badge whose accessible label was "Free agent," despite appearing on the team's roster. The league setup heading still describes only Sleeper scoring, and the league menu says "Other leagues (your Sleeper username)."

**Acceptance:** Provider names and roster ownership must match the selected league. Show HOU/CHI or a team-unit badge for team assets; never use "Free agent" as a missing-NFL-team fallback. A metric cannot simultaneously be presented as available and unavailable. Historical numbers must identify whether they come from MFL's official scores or reconstructed scoring.

## P1: make the default experience a weekly action list

Do not require a user to discover or configure a special simple mode. Make the first layer useful on its own; offer explanation and analytics beneath it.

Use three levels consistently:

1. **Action:** What should I do, and does anything need changing?
2. **Reason and consequence:** Why, who moves in or out, and what could change the recommendation?
3. **Analysis:** Ranges, weekly breakdowns, role metrics, scoring formulas, and model methodology.

The home page should show up to three distinct actions, ordered by urgency and practical importance. A valid answer is "Your lineup is set—nothing to change." Do not fill empty space with tiny projected improvements.

On the reviewed roster, separate cards compared Addison with McConkey and Nabers with McConkey. Both used McConkey's questionable designation as the tiebreaker. Combine related alternatives into one receiver decision, with a compact explanation. Make clear whether the suggested starters are already in the submitted MFL lineup or require a change.

**Illustrative wording based on the app's displayed information, not independently verified lineup advice:** "Keep Addison and Nabers ahead of McConkey for now. Their projections are close; McConkey's questionable status breaks the tie. Check his status again before kickoff."

Show a genuine time or event that requires attention. Use an explicit "Open MFL to edit lineup" action when supported. The app should state that reviewing a suggestion does not submit a lineup or claim. Do not imply that a calculation button executes a transaction.

**Acceptance:** A first-time user can identify whether action is needed, name the affected player, explain the reason, and find where to make the change within 30 seconds, without opening the methodology.

## P1: explain trades through starting-lineup changes

The trade result should lead with:

- Exact assets given and received, plus any required cut.
- A plain-language assessment of the effect on your team.
- Who enters your starters, who leaves, and any important loss of backup coverage.
- The other team's corresponding benefit or loss.
- A named timeframe and a comparison with holding or solving the need through waivers.

Keep the explanation that establishes the recommendation visible. Reserve detailed calculations for the expandable section.

### Separate player changes from slot movement

In the calculator's reduced Tuten-for-Rice scenario, the lineup detail showed Rice at WR/TE1 with +0.5, Watson at WR/TE2 with +3.5, and Nabers at WR/TE3 with +0.5. Watson and Nabers had merely moved between interchangeable numbered slots. Their individual projections had not improved.

The meaningful explanation of that displayed scenario is: Rice joins the starters, Addison moves to the bench, and the starting lineup's projected total rises by about 4.6 this week. The original proposed trade remains affected by the team-QB bug above; this example explains the display only.

**Acceptance:** Reordering identical starters among equivalent slots produces no claimed player improvement. Summarize changes in starter membership, then show the total lineup difference. Retain necessary positional reshuffles in detail.

### Replace the interest dial's implied acceptance prediction

"Their interest: 0/100," "Likely," and "Hard to say no" suggest knowledge of another manager's preferences. The help text instead defines these labels from projected lineup gain: under 2 points, 2–6, and above 6 across the selected horizon. That does not establish acceptance probability. The same six-point threshold also has different meaning across one week, a season, and different scoring systems.

Use "Effect on their starters" and descriptive outcomes such as "Improves their lineup" or "Makes their lineup weaker." Explain which need the trade fills. Any future acceptance model should be separately validated and clearly distinguished from lineup fit.

### Avoid unnecessary extra assets

The Finder showed Houston QB for Rice and Houston QB plus Tuten for Rice with the same +9.5 benefit to Big Mac Attack. The more expensive package was the headline suggestion. Prefer the least costly package that meets the objective, or explain why the extra asset is needed and what depth/upside is surrendered. Zero marginal starter points does not mean a bench player is worthless.

## P1: use a consistent metric dictionary

| Current wording or display | Suggested wording | Meaning that must be preserved |
|---|---|---|
| Proj / projected | Projected points this week | A forecast in the selected league's scoring, not a guarantee. Use one decimal by default. |
| You +9.5, weeks 4–7 | About 10 extra starter points total over the next four weeks | Sum of the change in the best legal starting lineup each week. Not 9.5 per week, and not the incoming players' total points. |
| Fit | Improvement to your starting lineup | Specify the horizon and whether the baseline is an optimized lineup or the currently submitted lineup. |
| Expected / work worth | Points suggested by his past opportunities | A backward-looking estimate from opportunities, distinct from the upcoming-week forecast. Explain the distinction beside the chart. |
| Market | Projected value above available replacements | This is a projection-derived measure, not observed trade prices. It must respect the league's eligible replacement slots. |
| Most weeks | Typical range | The current help text defines the middle 50% of modeled outcomes; "most" overstates that coverage. Show the percentage in the explanation. |
| Floor / ceiling | Low-end / high-end outcome | Modeled percentiles, not minimum or maximum possible scores. |
| Target share | Share of team passes thrown to him | For example, 20% means about one in five relevant team targets in the displayed window. Keep the denominator and period available. |
| Depth | Backup coverage | Say which position or future absence the backup protects. A bench-only lineup sum is not a direct estimate of insurance value. |
| TMQB / TMPK / WR+TE2 | Team QB / Team kicker / Receiver or tight end | Match the league's roster rules and use the same names across pages. |

Do not mechanically convert "above expected" into a claim that a player must cool off, or "below expected" into a claim that he is due. Present the observed gap and the evidence for any forward-looking recommendation.

## P1: make waiver horizons visually unambiguous

On Help now, the Bears card highlighted **+12.4 across weeks 4–7**, while the immediate **+2.1** appeared in smaller copy. The current-week view should emphasize the current-week improvement. Future benefits should be secondary and explicitly cumulative.

Example presentation of the app's displayed estimate: "Bears defense instead of Jaguars: about 2 more starter points this week. You have room to add them. Also helps cover Jacksonville's week-7 bye." Put the four-week total in the supporting detail.

Avoid repeating the top recommendation in a hero sentence, a top-three card, and an identical first list row. Label alternatives as alternatives; do not imply all independent recommendations can be combined without re-evaluating roster capacity.

## P1: simplify setup while preserving scoring honesty

The MFL setup screen places a lengthy scoring formula and reconciliation report before the team picker. With the scoring details expanded, team selection falls below the first desktop screen.

Put league confirmation and team choice first. Use a concise "Custom MFL scoring; some components are estimated" status with details available. Keep material limitations visible beside affected recommendations, not buried only in setup.

The app reported 116 of 157 week-3 player scores within one point of the league, with examples around 4–5 points apart. This is historical scoring reconciliation, not a forecast-accuracy test. Audit those differences before treating small projected advantages as strong recommendations.

The disclosed projection limitations include approximated defensive points-allowed bands, no separate 60-plus-yard field-goal band, and omitted return TDs and two-point conversions. Validate the impact for this league's team units and unusual bonuses. Do not imply exact support for all scoring rules.

## P2: reduce visual and verbal effort

- Keep ordinary text comfortably readable and give low-contrast supporting text more contrast. Do not make essential timeframe labels the smallest text on the card.
- Prefer a short answer and one reason to several overlapping totals and ranges.
- Move the default-visible player scoring arithmetic, such as "0.42 rushing TDs × 6.98715," under "How we calculated this." Those multipliers are useful audit detail, not a first answer about a player.
- Replace the long inline week-by-week number string with an optional compact schedule table.
- Show actionable player status near the name. Keep team context and useful navigation visible.
- Use "Updated 2:51 PM ET" or relative freshness with an exact time available. Technical feed names belong in data details; MFL roster freshness should be separately identifiable.
- Verify the phone layout separately. This review establishes desktop findings only.

## Definition of done for the next iteration

1. The MFL team-asset trade and wrong-slot explanation defects are fixed and covered by meaningful regression tests.
2. Every displayed recommendation agrees on assets, roster ownership, eligibility, injuries, locks, timeframe, and scoring context.
3. A casual user can answer: "What do I do?", "Why?", "Who starts instead?", and "Have I actually submitted anything?" without reading a methodology section.
4. A trade's gain is explained as starting-lineup improvement over a named period; untouched players do not show gains caused solely by slot renumbering.
5. A user can distinguish next-week projection, past opportunity-based expectation, replacement value, and an estimate of another team's lineup benefit.
6. The user can finish three observed usability tasks without coaching: identify a lineup decision, evaluate one waiver, and explain a trade's benefit and cost. Record hesitation and wrong interpretations, not just clicks completed.

Suggested work order: MFL correctness → decision summaries and metric names → concise default layout → observed test with the intended user → additional analytics.

## Review locations

- Team: https://league-lab.onrender.com/?league=mfl%3A70587&team=8
- Waivers: https://league-lab.onrender.com/waivers?league=mfl%3A70587&team=8
- Trade handoff example: https://league-lab.onrender.com/trade-calc?league=mfl%3A70587&team=8&partner=12&give=mfl%3A0682,12490&get=10229
- Tuten player page: https://league-lab.onrender.com/player/00-0040719?league=mfl%3A70587&team=8
- League setup: https://league-lab.onrender.com/leagues — enter 70587.

These observations describe the deployed UI at review time. Data, rosters, and recommendations can change after refresh; the cited cases should become controlled regression fixtures rather than assertions about future live output.
