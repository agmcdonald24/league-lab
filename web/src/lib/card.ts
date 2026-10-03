// The player card's sections in the order the full page and the research pane show them (IB-1 lifted it from
// routes/Player.svelte so the pane shows the same card): the answer first — this week's projection and where he sits
// in the lineup — then the rest.
import type { Block, PlayerCard, Section, SectionKey } from "./api";
import { plain } from "./md";
import { teamLabel } from "./theme";

export const SECTION_ORDER: SectionKey[] = ["projection", "value", "availability", "usage", "signals"];
const NAMES: Record<string, string> = { usage: "Usage", projection: "Projection", availability: "Availability", value: "Value", signals: "Signals" };
const RANKED = ["QB", "RB", "WR", "TE", "K", "DEF"];

// The Projection section plus the rest-of-season line: the API's sentence (app/lib/ros.py card_line) is in the
// section today; `ros.line` is added when the API sends it separately and the section does not already have it.
// Then a link to the rest-of-season list at his position.
function projection(d: PlayerCard): Section | undefined {
  const sec = d.sections.projection;
  if (!sec) return sec;
  const blocks = [...sec.blocks];
  const has = blocks.some((b) => (b.text ?? "").startsWith("Rest of season"));
  if (!has && d.ros?.line) blocks.push({ kind: "markdown", text: d.ros.line });
  // ---- IF-3: the matchup evidence right under "Next: week 4 @ CAR …" (the line that gives the rank)
  const next = blocks.findIndex((b) => (b.text ?? "").startsWith("Next: week"));
  const ev = matchupBlocks(d);
  if (ev.length) blocks.splice(next >= 0 ? next + 1 : blocks.length, 0, ...ev);
  // ---- end IF-3
  if ((has || d.ros) && RANKED.includes(d.position))
    blocks.push({ kind: "caption", text: `[Every ${d.position} for the rest of the season](/ros?position=${d.position})` });
  return { ...sec, blocks };
}

export function cardSections(d: PlayerCard): { key: SectionKey; sec: Section }[] {
  return SECTION_ORDER.map((k) => ({ key: k, sec: k === "projection" ? projection(d) : d.sections[k] }))
    .filter((x): x is { key: SectionKey; sec: Section } => !!x.sec)
    .map((x) => ({ key: x.key, sec: dictionary(x.sec) })); // ---- IE-2
}

// ---- IE-2 (Wave I-E): the review's metric dictionary on the card (docs/WORDS.md § "The dictionary"). The API's card is
// the console's player page (the parity tests pin its labels), so the product's words are applied here: the label
// and its help change, the value never does. Applied to the tiles' labels / help and the "How to read this" text.
export const CARD_WORDS: Record<string, { label: string; help?: string }> = {
  Projected: { label: "Projected points this week", help: "A forecast in this league's scoring, not a guarantee" },
  "Most weeks": { label: "Typical range", help: "The middle 50% of his modeled outcomes: a quarter of weeks below it, a quarter above" },
  Floor: { label: "Low-end outcome", help: "A modeled bad week: one week in ten he scores less (not his minimum)" },
  Ceiling: { label: "High-end outcome", help: "A modeled good week: one week in ten he scores more (not his maximum)" },
  Expected: {
    label: "From past opportunities",
    help: "Points suggested by his past opportunities: what his targets and carries were worth, looking back — not this week's forecast. The arrow is the observed gap.",
  },
  "Target share": { label: "Share of team passes", help: "Share of his team's passes thrown to him (targets), in the games he played" },
};

export function dictionary(sec: Section): Section {
  return {
    ...sec,
    blocks: sec.blocks.map((b) =>
      b.metrics ? { ...b, metrics: b.metrics.map((m) => (CARD_WORDS[m.label] ? { ...m, label: CARD_WORDS[m.label].label, help: CARD_WORDS[m.label].help ?? m.help } : m)) } : b,
    ),
  };
}

/** The card's "How to read this" in the dictionary's words. */
export function howtoWords(t: string | null | undefined): string {
  return (t ?? "")
    .replace(/\*\*Most weeks\*\*/g, "**Typical range** (the middle 50% of outcomes)")
    .replace(/the \*\*floor\*\* and \*\*ceiling\*\* are a bad week and a good week/g, "the **low-end** and **high-end outcomes** are a modeled bad week and good week, not his minimum or maximum")
    .replace(/\*\*Projection\*\* is this week's projected points/g, "**Projected points this week** is a forecast, not a guarantee,");
}
// ---- end IE-2

/** The header line without the position and team the badges already show ("WR · DET · WR1 on the depth chart …"). */
export function cardHeadLine(d: PlayerCard): string {
  const parts = plain(d.header).split(" · ");
  const drop = new Set([d.position, d.team ?? "", teamLabel(d.team) ?? ""]);
  while (parts.length && drop.has(parts[0])) parts.shift();
  return parts.join(" · ");
}

/** The sections this league cannot show yet, by name ("Value"). */
export function cardMissing(d: PlayerCard): string[] {
  return (d.missing ?? []).filter((k) => !d.sections[k as SectionKey]).map((k) => NAMES[k] ?? k);
}

// ---- N1 (Wave I-D): the news line — "News · 2 h ago · <headline> · ESPN ›", the newest of `news` (the API keeps it
// at most 14 days old). `now` is injectable (tests). Ages: "just now" under a minute, "N min ago", "N h ago", "N d ago".
export function ago(iso: string, now: number = Date.now()): string {
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return "";
  const min = Math.floor(Math.max(0, now - t) / 60_000);
  if (min < 1) return "just now";
  if (min < 60) return `${min} min ago`;
  const h = Math.floor(min / 60);
  if (h < 24) return `${h} h ago`;
  return `${Math.floor(h / 24)} d ago`;
}

export interface NewsLine {
  ago: string;
  headline: string; // cut at a word to NEWS_MAX characters ("…"): a RotoWire blurb runs to 220
  full: string;
  source: string;
  url: string;
}

export const NEWS_MAX = 110;

export function shortHeadline(s: string, max: number = NEWS_MAX): string {
  const t = s.trim();
  if (t.length <= max) return t;
  const cut = t.slice(0, max + 1);
  const sp = cut.lastIndexOf(" ");
  return `${(sp > max * 0.6 ? cut.slice(0, sp) : t.slice(0, max)).replace(/[\s,;:.\-–—]+$/, "")}…`;
}

export function newsLine(d: Pick<PlayerCard, "news">, now: number = Date.now()): NewsLine | null {
  const n = (d.news ?? []).find((x) => x.headline && x.url?.startsWith("https://"));
  if (!n) return null;
  return { ago: ago(n.date, now), headline: shortHeadline(n.headline), full: n.headline, source: n.source || "ESPN", url: n.url };
}
// ---- end N1

// ---- IF-3 (Wave I-F, the decision-quality review § Priority 1): the card's matchup section — the matchup evidence
// (research.matchup_evidence via the card's `matchup_evidence`) in two sentences under the "Next:" line: the defense's
// history with the corners it was earned with, then what it means this week and the forecast's treatment ("contextual
// only; not in the forecast"). A receiver whose opponent's corners changed gets "Corners changed." first; a position
// without a personnel check gets the history sentence only (its second sentence would only say so).
export function matchupBlocks(d: Pick<PlayerCard, "matchup_evidence">): Block[] {
  const ev = d.matchup_evidence;
  if (!ev?.sentences?.length) return [];
  const out: Block[] = [{ kind: "caption", text: (ev.matchup_uncertain ? "**Corners changed.** " : "") + ev.sentences[0] }];
  if (ev.sentences[1] && ev.implication.kind !== "unchecked") out.push({ kind: "caption", text: ev.sentences[1] });
  return out;
}
// ---- end IF-3
