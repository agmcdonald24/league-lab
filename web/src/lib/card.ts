// The player card's sections in the order the full page and the research pane show them (IB-1 lifted it from
// routes/Player.svelte so the pane shows the same card): the answer first — this week's projection and where he sits
// in the lineup — then the rest.
import type { PlayerCard, Section, SectionKey } from "./api";
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
  if ((has || d.ros) && RANKED.includes(d.position))
    blocks.push({ kind: "caption", text: `[Every ${d.position} for the rest of the season](/ros?position=${d.position})` });
  return { ...sec, blocks };
}

export function cardSections(d: PlayerCard): { key: SectionKey; sec: Section }[] {
  return SECTION_ORDER.map((k) => ({ key: k, sec: k === "projection" ? projection(d) : d.sections[k] })).filter(
    (x): x is { key: SectionKey; sec: Section } => !!x.sec,
  );
}

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
