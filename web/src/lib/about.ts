import { APP_NAME } from "./brand";
// "About the numbers" (Wave G): the model explanation, in the words of the Streamlit Rankings page's "The model"
// expander (app/pages/4_Rankings.py), cut into the sections the screen shows. The league's name goes where the page
// names the scoring. docs/WORDS.md: plain words, one gloss per technical number.

export interface AboutSection {
  key: string;
  title: string;
  text: string; // markdown (lib/md)
}

export const MODEL_ANSWER =
  `**${APP_NAME} trains its own model**: these are not Sleeper's or ESPN's projections. It predicts each player's stat line from what was known before kickoff, then your league's scoring turns the line into points.`;

export function aboutSections(leagueName: string): AboutSection[] {
  return [
    {
      key: "learned",
      title: "What it learned from",
      text:
        "The regular-season games QBs, RBs, WRs and TEs played from 2016 to last season (over 50,000 of them), each with only what was known before kickoff: " +
        "his season and last-3-game numbers, his share of his team's targets, carries and snaps, how often he was the quarterback's first look, last season, " +
        "the opponent's defense against his position, the Vegas line, home or away, the injury report, who starts at quarterback and whether his team's top target is out.",
    },
    {
      key: "predicts",
      title: "What it predicts",
      text:
        "The stat line, not points. For each position there is one small model per stat: targets, catches, receiving yards and touchdowns, carries, rushing yards and " +
        "touchdowns, and for quarterbacks pass attempts, passing yards, touchdowns and interceptions. Each is a gradient-boosted model: a few hundred small decision " +
        `trees, each one fixing the mistakes of the ones before it. Then **${leagueName}**'s scoring turns the stat line into points, which is why the same player ` +
        "projects differently in each league.",
    },
    {
      key: "ranges",
      title: "The ranges",
      text:
        // ---- IF-4: the dictionary's words (was "Most weeks", "floor", "ceiling")
        "The **typical range** (the middle 50% of outcomes) and the **low-end** and **high-end outcomes** come from separate models that learned how far off the " +
        "projection usually is for a player like this one, then widened or narrowed until they held on seasons they had never seen, separately for cheap, " +
        "mid-priced and expensive projections: half his weeks land in the typical range (a quarter below it, a quarter above), 8 in 10 between the low-end " +
        "outcome (a bad week: 1 week in 10 lands below it) and the high-end outcome (a good week: 1 week in 10 lands above it).",
    },
    {
      key: "graded",
      title: "How it was graded",
      text:
        "Trained on the past, graded on seasons it never saw: each season from 2021 to 2025 was predicted by a model trained only on the seasons before it. " +
        "The grade is the **order score** (Spearman: how well the projected order of players matched the order they really finished in, 1 = perfect, 0 = no better " +
        "than random) and the **average miss** in points. This season's grades score the **kickoff board**: the projections as they stood when each week's first game " +
        "kicked off, locked from then on, so they score what you actually saw, not a later re-run.",
    },
    {
      key: "unknown",
      title: "What it does not know",
      text:
        "Injury news after the morning refresh, the weather, how the game actually goes (a blowout sends starters to the bench early), and coaching decisions made " +
        "during the week. Check the news before kickoff. It is refreshed every morning with the newest games, and the model itself has changed during the season: every version and its date is under \"What changed and when\" below.", // ---- IR-4: was "its recipe stays the same all season" (v3.0 → v3.6 since week 4)
    },
    {
      key: "tried",
      title: "What we tried",
      text:
        "**Kept: who plays next to him.** The model knows who is starting at quarterback this week (and whether that is the quarterback a player's recent games were " +
        "played with), and whether his team's top target or top ball carrier is out. Graded the same way on 2021 to 2025, the quarterback order score went up by " +
        "0.045 in every one of the five seasons and the average miss fell by about half a point per game; for running backs, receivers and tight ends the " +
        "top-teammate-out inputs add about 0.005 to the order score, in every season tested.  \n" +
        "**Left out**: the kickoff time and rest days, the weather, how fast and how often a team throws, injuries on the offensive line and a player's own injury " +
        "history. None made the projections better on seasons they had not seen (Vegas lines already price most of it). We keep a new input only when it helps in " +
        "at least 2 of the 3 seasons tested, not just on average.",
    },
  ];
}
