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
