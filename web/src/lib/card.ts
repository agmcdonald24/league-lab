// The player card's sections in the order the full page and the research pane show them (IB-1 lifted it from
// routes/Player.svelte so the pane shows the same card): the answer first — this week's projection and where he sits
// in the lineup — then the rest.
import type { Block, PlayerCard, Section, SectionKey } from "./api";
import { plain } from "./md";
import { teamLabel } from "./theme";

// ---- IL-1 (Wave I-L): the Role block (the API's `role` section: league_lab.roles) right after the projection and its
// "Why this number"
export const SECTION_ORDER: SectionKey[] = ["projection", "role", "value", "availability", "usage", "signals"];
const NAMES: Record<string, string> = { usage: "Usage", projection: "Projection", availability: "Availability", value: "Value", signals: "Signals", role: "Role" };
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
    .map((x) => ({ key: x.key, sec: dictionary(x.sec) })) // ---- IE-2
    .map((x) => ({ key: x.key, sec: clearer(x.key, x.sec, d) })); // ---- IF-4
}

// ---- IF-4 (Wave I-F, the decision-quality review's table): the card's words made exact, on the web (the API's card is
// the console's player page, pinned by the parity tests). (1) "No role change detected" never beside "not enough
// games": the role line says which comparison is valid — "not enough games to say" before his fourth game (the same
// rule as the trend call), else "role steady over N games"; absence of a detected change is not proof of stability.
// (2) A metric tile with no value is defined and says it is not available for this player (first-read and red-zone
// share with their denominators), instead of looking broken.
const TILE_DEFS: Record<string, string> = {
  "First-read share":
    "How often he is the quarterback's first look: his first-read targets ÷ his team's charted dropbacks with a first read, in the games he played.",
  "Red-zone share":
    "His share of his team's red-zone chances (inside the opponent's 20): targets for a receiver or tight end, carries for a running back or quarterback, in the games he played.",
  "Snap share": "Share of his team's offensive plays he was on the field for, in the games he played.",
  // ---- II-4 (Wave I-I; the review § 5: Kyren's Carry share had no definition): docs/WORDS.md § "The copy standard"
  "Carry share":
    "His rush attempts ÷ his team's rush attempts, both summed over the games he played this season (not an average of weekly percentages). The team count is every rusher's attempts, quarterbacks included, as nflverse's weekly stats count them; kneel-downs are not removed. Not his share of the running backs' carries.",
  "Target share": "His targets ÷ his team's targets, both summed over the games he played this season (not an average of weekly percentages).",
  "Passes / game": "His pass attempts ÷ the games he played this season (per game).",
  // ---- end II-4
};
const NOT_AVAILABLE = "Not available for this player: no charted plays for him yet (unknown, not zero).";

function gamesFrom(d: PlayerCard): number | null {
  if (typeof d.games_played === "number") return d.games_played;
  const cap = (d.sections.usage?.blocks ?? []).map((b) => b.text ?? "").find((t) => /Season to date, \d+ game/.test(t));
  const m = cap?.match(/Season to date, (\d+) game/);
  return m ? Number(m[1]) : null;
}

export function roleWords(text: string, games: number | null): string {
  const NO_CHANGE = /Role: \*\*no role change detected\*\* in his last three games: his share of the snaps, targets and carries is where it has been\./;
  if (!NO_CHANGE.test(text)) return text;
  const said =
    games !== null && games < 4
      ? `Role: **not enough games to say** — ${games} game${games === 1 ? "" : "s"} so far; a change is called against his own earlier games, from his fourth game.`
      : `Role: **role steady over ${games ?? "his"} games** — no change in his share of the snaps, targets or carries past his usual swing in the last three.`;
  return text.replace(NO_CHANGE, said);
}

function clearer(key: SectionKey, sec: Section, d: PlayerCard): Section {
  if (key === "signals") {
    const g = gamesFrom(d);
    return { ...sec, blocks: sec.blocks.map((b) => (b.text ? { ...b, text: roleWords(b.text, g) } : b)) };
  }
  if (key === "usage") {
    return {
      ...sec,
      blocks: sec.blocks.map((b) =>
        b.metrics
          ? {
              ...b,
              metrics: b.metrics.map((m) => {
                const def = TILE_DEFS[m.label] ?? null;
                const empty = m.value == null || m.value === "—" || m.value === "";
                if (!def && !empty) return m;
                return { ...m, value: empty ? "—" : m.value, help: [def ?? m.help, empty ? NOT_AVAILABLE : null].filter(Boolean).join(" ") };
              }),
            }
          : b,
      ),
    };
  }
  return sec;
}

/** The pane's focus: the blocks a decision needs stay; the week-by-week line, the next-4 list, the rest-of-season link
 * (projection) and the season tiles (value) go behind "More" in the pane (the full page shows everything). */
export function paneSplit(key: SectionKey, sec: Section): { main: Section; more: Section["blocks"] } {
  const isMore = (b: Section["blocks"][number]) => {
    const t = b.text ?? "";
    if (key === "projection") return /^Week by week/.test(t) || /^Next 4:/.test(t) || /^\[Every /.test(t);
    if (key === "value") return !!b.metrics;
    return false;
  };
  return { main: { ...sec, blocks: sec.blocks.filter((b) => !isMore(b)) }, more: sec.blocks.filter(isMore) };
}
// ---- end IF-4

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
  // ---- N2: a PlayerWire brief's one-sentence news under the headline (null for ESPN), and its verification tag
  summary: string | null; // cut at a word to SUMMARY_MAX characters
  summaryFull: string | null;
  verification: "official" | "reported" | "corroborated" | "disputed" | null;
}

export const NEWS_MAX = 110;
export const SUMMARY_MAX = 220; // N2
const VERIFICATION = new Set(["official", "reported", "corroborated", "disputed"]);

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
  const summary = n.summary?.trim() || null;
  const v = n.verification && VERIFICATION.has(n.verification) ? n.verification : null;
  return {
    ago: ago(n.date, now),
    headline: shortHeadline(n.headline),
    full: n.headline,
    source: n.source || "ESPN",
    url: n.url,
    summary: summary ? shortHeadline(summary, SUMMARY_MAX) : null,
    summaryFull: summary,
    verification: v,
  };
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

// ---- IG-1 (Wave I-G, AGENTS.md rule 5 "unknown is not zero"): a player with no projection row shows a dash and the
// words "no projection" (the dictionary row), never "0.00"; the API sends null (INTERFACES.md § IG-1)
export const NO_PROJECTION = "no projection";
export const NO_PROJECTION_TITLE = "No projection for him this week: unknown, not 0";

/** The player card's number label: "Week 4", "Week 4 · no projection" when the card has no projection (the number is a
 * dash, never 0.00). */
export function projLabel(week: number | null | undefined, proj: number | null | undefined): string {
  const base = week ? `Week ${week}` : "Projection";
  return proj === null || proj === undefined ? `${base} · ${NO_PROJECTION}` : base;
}

/** 12.34 / "—" for no number (unknown is not zero). */
export function projText(v: number | null | undefined, digits = 2): string {
  return v === null || v === undefined || Number.isNaN(v) ? "—" : v.toFixed(digits);
}
// ---- end IG-1

// ---- IP-4 (Wave I-P): the card's head — the numbers it leads with, read from what the card already carries (the
// Projection section's tiles, the schedule rows, the Availability lines, the value). Nothing is recomputed: a number on
// the head is the same number the section under it shows.
export interface HeadRange {
  p10: number | null;
  p25: number | null;
  p75: number | null;
  p90: number | null;
}

const num = (s: string | null | undefined): number | null => {
  if (s === null || s === undefined) return null;
  const v = Number(String(s).replace(/[^\d.-]/g, ""));
  return String(s).trim() === "" || String(s).trim() === "—" || Number.isNaN(v) ? null : v;
};

/** The projection's range from the Projection section's tiles (Floor, Most weeks "9–19", Ceiling): the API's labels,
 * read before the dictionary renames them. Unknown parts are null (a week frozen before the 50 % range existed). */
export function headRange(d: Pick<PlayerCard, "sections">): HeadRange {
  const ms = (d.sections.projection?.blocks ?? []).flatMap((b) => b.metrics ?? []);
  const by = (l: string) => ms.find((m) => m.label === l)?.value ?? null;
  const mid = (by("Most weeks") ?? "").split(/[–-]/);
  return { p10: num(by("Floor")), p25: mid.length === 2 ? num(mid[0]) : null, p75: mid.length === 2 ? num(mid[1]) : null, p90: num(by("Ceiling")) };
}

/** The head's number as the Projection tile prints it (the API's rounding: 8.25 → "8.2", where JS's toFixed says
 * "8.3"), so the head and the tile under it never disagree; the card's own number otherwise; "—" for none. */
export function headNumber(d: Pick<PlayerCard, "sections" | "proj_points">): string {
  if (d.proj_points === null || d.proj_points === undefined) return "—";
  const tile = (d.sections.projection?.blocks ?? []).flatMap((b) => b.metrics ?? []).find((m) => m.label === "Projected")?.value;
  return tile && /^-?\d+(\.\d)?$/.test(tile.trim()) ? tile.trim() : d.proj_points.toFixed(1);
}

export interface NextGame {
  week: number;
  opponent: string | null; // null = a bye
  home: boolean | null;
  rank: number | null; // the opponent's rank vs his position (1 = gives up the most)
  kickoff: string | null; // "Sun Oct 4, 1:00 PM ET" (the Availability line's words)
  locked: boolean;
}

/** This week's game: the schedule row of the card's week, the kickoff from the Availability line. */
export function nextGame(d: Pick<PlayerCard, "week" | "schedule" | "sections" | "locked">): NextGame | null {
  if (!d.week) return null;
  const row = (d.schedule ?? []).find((r) => r.week === d.week);
  const text = (d.sections.availability?.blocks ?? []).map((b) => b.text ?? "").join("\n");
  const k = text.match(/kickoff ([A-Z][a-z]{2} [A-Z][a-z]{2} \d{1,2}, \d{1,2}:\d{2} [AP]M) ET/) ?? text.match(/kicked off ([A-Z][a-z]{2} [A-Z][a-z]{2} \d{1,2}, \d{1,2}:\d{2} [AP]M) ET/);
  if (!row && !k) return null;
  return { week: d.week, opponent: row?.opponent ?? null, home: row?.is_home ?? null, rank: row?.opp_rank ?? null, kickoff: k ? `${k[1]} ET` : null, locked: !!d.locked };
}

export interface HeadValue {
  label: string; // "Value · Half PPR, rest of season"
  big: string; // "WR1"
  small: string; // "+140 over a free WR"
  help: string;
}

/** His value in the chosen scoring: browsing, the reference key's value (IN-2 `ref_value`); with a league, the Value
 * section's own tiles (his rank by points per game and his points per game, in the league's scoring). */
export function headValue(d: Pick<PlayerCard, "ref_value" | "sections" | "position" | "league_name">): HeadValue | null {
  const rv = d.ref_value;
  if (rv && rv.value !== null && rv.value !== undefined) {
    return {
      label: "Value, rest of season",
      big: `${rv.position}${rv.value_rank_pos}`,
      small: `${rv.value >= 0 ? "+" : "−"}${Math.abs(Math.round(rv.value))} over a free ${rv.position}`,
      help: rv.words ?? rv.assumes,
    };
  }
  const ms = (d.sections.value?.blocks ?? []).flatMap((b) => b.metrics ?? []);
  const rank = ms.find((m) => m.label === "Rank")?.value ?? null;
  const ppg = ms.find((m) => m.label === "Points / game")?.value ?? null;
  if (!rank && !ppg) return null;
  return {
    label: `${d.league_name} scoring, this season`,
    big: rank ?? ppg ?? "—",
    small: rank && ppg ? `${ppg} points per game` : "points per game",
    help: "His rank by points per game among every player at his position, and his points per game, in this league's scoring.",
  };
}

/** The status chip's tone: out-type designations read bad, questionable reads warn. */
export function statusTone(s: string | null | undefined): "bad" | "warn" | null {
  if (!s) return null;
  return /^(out|ir|pup|nfi|sus|doubtful|inactive|injured reserve)/i.test(s.trim()) ? "bad" : "warn";
}
// ---- end IP-4
