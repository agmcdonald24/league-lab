// ---- II-4 (Wave I-I; the product and analytics review § 7–8): My Week's "What changed" as a decision-impact feed and
// the home's three clocks. The API sends each line's five parts (INTERFACES.md § II-4); an answer from before Wave I-I
// (no `decision_status`) renders as IF-4 drew it.
import type { ChangedLine, DecisionStatus } from "./api";

/** The chip's look per decision status (changed = the warn colour, watch = the accent, none = neutral). */
export const DECISION_CHIP: Record<DecisionStatus, string> = {
  changed: "bg-warn-soft text-warn",
  watch: "bg-accent-soft text-accent",
  none: "bg-raised text-ink-2",
};
export const DECISION_MARK: Record<DecisionStatus, string> = { changed: "⚠︎ ", watch: "◔ ", none: "" };

/** A long sentence run cut after its first sentence (the rest behind "More"); short text whole. */
export function splitLead(text: string | null | undefined, max = 160): { lead: string; rest: string } {
  const t = (text ?? "").trim();
  if (t.length <= max) return { lead: t, rest: "" };
  const m = /^(.{40,}?[.!?])\s+(?=[A-Z(“"])/.exec(t);
  if (m && m[1].length <= max + 60) return { lead: m[1], rest: t.slice(m[0].length).trim() };
  const cut = t.lastIndexOf(" ", max);
  const at = cut > 40 ? cut : max;
  return { lead: `${t.slice(0, at)}…`, rest: t.slice(at).trim() };
}

/** The developments first (the API's order: changed → watch → none), the game recaps apart. */
export function splitRecaps(lines: ChangedLine[]): { developments: ChangedLine[]; recaps: ChangedLine[] } {
  return {
    developments: lines.filter((l) => l.item_kind !== "recap"),
    recaps: lines.filter((l) => l.item_kind === "recap"),
  };
}

/** Where the line's next step goes (the player's page, Compare with him first). */
export function nextHref(l: ChangedLine): string | null {
  const n = l.next_step;
  if (!n || !n.gsis_id) return null;
  if (n.kind === "compare") return `/compare?a=${encodeURIComponent(n.gsis_id)}`;
  return `/player/${encodeURIComponent(n.gsis_id)}`;
}

/** "2:40 PM ET" today, "Sat 7:41 AM ET" another day — a stamp, never a warning (PO 2026-10-04). */
export function stampET(iso: string | null | undefined, now: Date = new Date()): string | null {
  if (!iso) return null;
  const t = new Date(iso);
  if (Number.isNaN(t.getTime())) return null;
  const tz = "America/New_York";
  const time = t.toLocaleTimeString("en-US", { timeZone: tz, hour: "numeric", minute: "2-digit" });
  const day = (d: Date) => d.toLocaleDateString("en-US", { timeZone: tz });
  const wd = day(t) === day(now) ? "" : `${t.toLocaleDateString("en-US", { timeZone: tz, weekday: "short" })} `;
  return `${wd}${time} ET`;
}
// ---- end II-4
