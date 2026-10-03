# Words — how League Lab talks on its pages

The reader is a league-mate who plays fantasy football on Sleeper and has never heard of dbt, Spearman or
a quantile. Every string a page shows follows this file: the "How to read this" boxes, cards, captions,
column tooltips (`help=` in `app/lib/table.py`), Home's "What's new" (`app/whats_new.md`) and the model
explainer on Rankings. Docs for developers (`METRICS.md`, `STATUS.md`) keep the technical words.

## The rules

1. **Say what to do first.** A "How to read this" box is three to five bullets that answer "what do I do
   with this?": start him, claim him, sell him, check the news. Definitions come second.
2. **Short sentences, no hedging.** One idea per sentence. No "leverage", "robust", "signal" when "sign"
   will do. Colons and full stops over dashes.
3. **One gloss per technical number**, in brackets, the first time it appears on a page:
   "floor–ceiling (the range 8 weeks in 10 land in)".
4. **Never on a page**: model or table names (`v2`, `mart_…`, `gsis_id`, `P10`, `quantile`, `z-score`,
   `permutation`, `residual`, `as-of`, `walk-forward`, `denominator`, `proxy`). The one exception: Rankings'
   "The model" section names *Spearman* once, with its gloss, because the grade tables are headed with it.
5. **Numbers keep their units**: "+2.1 points this week", "0.45 apart", "43% of the time".
6. **Name the league's scoring** when a number depends on it ("in League of Scrubs scoring"); say "one scale
   for every league" for the NFL-wide pages, not "reference scoring".
7. **Unknown is not zero**, in words too: "no projection yet", "not charted before 2022", never a silent 0.

## Term → the words we use

| Term (code, docs) | On a page |
|---|---|
| projection v2, `proj_points` | the projection; "League Lab's own model" when contrasting with the old one |
| baseline (OLS formula) | the old formula |
| P10 / floor | floor: a bad week for him (1 week in 10 lands below it) |
| P90 / ceiling | ceiling: a good week for him (1 week in 10 lands above it) |
| P10–P90 interval, 80% interval | between floor and ceiling (8 weeks in 10 land there) |
| P50 | the middle outcome |
| P25–P75, 50% range (D6) | most weeks: "most weeks 9–16" (half his weeks land there: a quarter below, a quarter above); leads on a card and on the Rankings board, the floor–ceiling behind it |
| P(A outscores B), win probability (D6) | "Tucker outscores Monangai 54% of the time": whole percent, never 0 or 100 |
| 50–55% / 55–65% / 65%+ (D6) | a coin flip / a lean / clear (the card's headline word; the margin's words only when there is no percentage: a kicker, a defense) |
| same-game correlation (D6) | "teammates and players facing each other are not independent (a shootout lifts both)" |
| interval width | the gap between floor and ceiling; "Range" |
| coverage_80 | how often the real score landed between floor and ceiling (the aim is 8 in 10) |
| Spearman, rank correlation | the order score: how well the projected order matched the real one (1 = perfect, 0 = random) |
| top-N hit rate | how many of the week's real top 12 / top 24 it had in its top group |
| MAE | the average miss, in points |
| backtest, walk-forward, held-out season | graded on past seasons it never saw (trained on the past, graded on seasons it never saw) |
| kickoff board, frozen board (B5) | the projections as they stood at the week's first kickoff, locked since |
| refit values | a re-run of the same model (for weeks played before boards were locked) |
| drift | how the model is doing this season |
| gradient-boosted regressor | a gradient-boosted model: a few hundred small decision trees, each fixing the mistakes of the ones before it |
| component model | one small model per stat (targets, catches, yards, touchdowns …) |
| priced line, scoring map | the stat line counted your league's way |
| permutation importance | points of error added when the model can't use that number (we scramble it between players) |
| feature | input; "what the model looks at" |
| `targets_pg_l3` and the other inputs | `projections.FEATURE_LABELS` ("Targets per game, last 3 games") |
| xPPG, expected points | expected points per game: what his targets and carries are usually worth |
| PPG − xPPG | **below / above expectation** (IA-1; was "due" / "running hot"): "Getting the targets of a 10.5-point player, scoring 3.6" — then one cause the numbers support or none: "no touchdowns on 4 red-zone targets", "4 touchdown passes in 2 games", "his quarterback changed", "his share of the targets fell from 25% to 12%" |
| target share, carry share | his share of his team's targets / carries |
| snap % | share of plays he is on the field |
| first-read share | how often he is the quarterback's first look |
| route participation, routes proxy | how often he is on the field when the quarterback drops back (an estimate) |
| TPRR / YPRR | targets / yards per route |
| aDOT, air yards | how far downfield his targets travel |
| implied team total | the points Vegas expects his team to score |
| opp rank | the matchup rank: 1 = the defense that gives up the most to his position (the matchup you want); on the Matchups screen (IB-3) the tough rank instead, 1 = the toughest |
| opp rank in a sentence (IA-1) | "the Colts, who give up the 2nd-most points to running backs" (rank ≤ 10) / "the 7th-fewest" (rank ≥ 23); the middle is not worth a sentence |
| a decision card's reason (IA-1, `cards.reason_line`) | one sentence under the call: the strongest reason for the starter and the strongest against the other player ("Hampton's share of the carries rose from 57% to 72% last game; Croskey-Merritt's share of the carries fell from 50% to 38% last game"); under 55% (or under 1 point apart without a percentage): "Too close to call: the projection says A by 0.5, the ranges say either. Go with B on the matchup: …" (injury first, then matchup, role, betting line); last names, whole names when two share one |
| implied total in a sentence (IA-1) | "Vegas expects Willis's Dolphins to score only 16" (≤ 18) / "… to score 27" (≥ 26) |
| z / Strength, "beyond noise" | how unusual the change is for him (1 = worth a look, 2 = clear); bigger than his usual week-to-week swing |
| momentum | his role trend |
| lineup value (B1) | the projected points of your best lineup |
| margin (B1) | how much your lineup loses without him; "apart" on a card |
| weakest slot | your closest call |
| bench value / depth | what your bench alone could put out |
| lineup gain, fit (B2, B3) | what the move adds to your lineup, in points |
| all-play | your record if you had played every team every week |
| luck_wins | wins above (+) or below (−) what your points deserve |
| reference league / reference scoring | League of Scrubs scoring; "one scale for every league" on NFL-wide pages |
| partition (Data Status) | the pieces a source comes in, usually one per season |
| role alert (R-10), `direction` up / down | a bigger / smaller role; "Role alerts this week" |
| `kind` absence_beneficiary / depth_move / new_team / role_up / role_down | Filling in (or Taking over the work) / New starter · Lost his starting job / Bigger (smaller) role on his new team / Bigger role / Smaller role |
| `cause_text`, trigger | "Why: …" — a teammate out injured or back, benched, a depth-chart move, traded; "the coaches changed his role" when there is none |
| `games_held`, confidence | "one game so far" / "two games so far" / "three games: this is his role now"; column "Held" |
| expiry | "It ends when X returns" / "Check again after week N: by then his projection has caught up if it holds" |
| larger-role scenario (R-12), `presentation = 'what if'` | "What if the new role holds: 11.3 in week 4 (projection 7.1, +4.2)"; never a chance |
| scenario backtest hit rate | "tested on 2023–2025: after 285 alerts like this the next three games landed nearer it than the projection 46% of the time" |
| upside stash (`ops.waiver_upside`) | Upside stash: his role is growing before his points do |
| rest of season, ROS (E2), `ros_points` | rest of season: "Rest of season: 232 points over 13 games"; "through this league's final" when the window matters; "ROS rank" only as a column header |
| `ros_p10`–`ros_p90` (E2, weeks taken as independent) | likely: "(likely 190–273)"; the gloss "where 8 seasons in 10 would land if every week were its own roll of the dice; a role change or an injury moves the weeks together, so the real range is wider" |
| `ros_rank_pos` (E2) | "WR4 in this league" (every player at the position, rostered or free agent); "not ranked (on injured reserve)" |
| `weeks_with_lines` (E2) | "Only week 4 has betting lines yet: the later weeks lean on his usage and the schedule" |
| stat-line pieces × scoring (IA-3) | "Why this number": "8.9 targets → 5.5 catches → 96 yards → 0.48 TDs → 15.4 points a game × 12 games = 185", then one line a piece ("5.5 catches × 0.5 = +2.7", "8.9 targets (no points on their own)"); what a per-unit price cannot show is its own line: "yardage bonuses (a big game pays extra in this league)" or "the small pieces and rounding" |
| market line, `market_points` (IA-3) | "Sleeper has him at 16.2." (this week, this league's scoring); under 70% / over 140% of it: "We're well under (over) the market: our number follows his recent usage. Treat it with care."; none: "Sleeper's number for this week is not in yet." |
| `piece_columns` (IA-3) | per game, projected: Att · Pass yd · Pass TD · INT (QB); Car · Rush yd · Tgt · Rec · Rec yd · TD (RB); Tgt · Rec · Rec yd · TD (WR / TE) |
| the rankings' honesty line (IA-3, `about.RANKINGS_HOWTO`) | "How to read the rankings": from his work, not his name; superflex / 6-point passing TDs put quarterbacks on top by design; Sleeper's number is there to compare |
| matchup tone (IB-3) | **Favorable / Neutral / Difficult**: the word in the state color, ▲ / ▼ beside it; "No read" when no ranked corner is named |
| tough rank (IB-3) | one direction on the Matchups screen: "#1 = the toughest for the offense" ("#3 toughest vs RB", small and grey under the tone) |
| cornerback certainty (IB-3, `call_strength`) | **likely** (his targets lean 15+ points to one side) · **unclear** (either outside corner) · **no call**; beside the tone, never a "shutdown" badge: "the 17th-hardest of 74 starting corners to throw on" |
| value to my lineup (IB-3, `lineup_points`) | "Value to my lineup": what he adds to your best lineup over the weeks left; one of yours = what you lose without him; "Your QB2 only plays in week 7: 16 points over your next-best there", "Your backup QB never starts for you behind Mahomes: he adds nothing to your lineup (insurance only)", "Free agent: would start for you in 12 of 13 weeks left, +20 points to your lineup" |
| card status (IB-3, IB-0's `status`) | **Change needed** (the call is not in your Sleeper lineup) · **Already set** · **Close call** (a coin flip); the strength word: Clear · Lean · Coin flip |
| yardstick (Receivers, U-17) | what the season's top-12 at the position (the 12 with the most points a game) average |
| combined slot `WR+TE1` (IC-2, `cards.slot_label`) | "WR/TE 1" (the league's own slot, its parts joined by a slash; "RB/WR/TE 2") |
| team unit `TMQB` / `TMPK` (IC-2) | "team QB" / "team K" in the slot column; the player is "Kansas City Chiefs QB" / "… K" (his team's quarterbacks / kicker as one player, MyFantasyLeague's) |
| no eligible slot (IC-2, `lineup.no_slot_reason`) | **No slot** in the list, "No slot for a K in this league" as the reason — never "Can't play" (kept for injury, bye, IR, a locked bench player) |
| asset key (IE-0, the calculator's `give` / `get`) | never on a page; a key the analysis cannot use reads "Can't analyse **Houston Texans QB** (you get): on Big Mac Attack's roster, not Madeyes Revenge's." with "Take out of the trade" |
| a waiver reason in a later week (IE-0, `_bye_reason`) | only the candidate's own: "Fills your empty DEF in week 7, when Jacksonville Jaguars is on a bye" (a defense) · "Starts at WR/TE 3 in week 7, when McConkey is on a bye" (a starter he can stand in for) · else "Would not start for you this week; helps in week 7." |
| the platform in a sentence (IE-0) | the league's own: "on the bench in MFL", "starting in his MFL lineup"; Sleeper's number (the market line) only on a Sleeper league |
| points per game on an on-demand card (IE-0) | one statement with its source: "Points per game: 10.5 over 2 games, reconstructed in this league's MFL scoring from his stat lines" (the chart's number) |
| no NFL team (IE-0, `TeamBadge`) | no chip; never "FA" / "Free agent" for a missing team ("Free agent" is a player nobody in the league has) |

## Adding to it

A new metric or page adds its row here in the same change as its `help=` text. A release adds one entry to
`app/whats_new.md` (three to six bullets, newest on top) next to its `CHANGELOG.md` entry.
