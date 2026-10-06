// ---- IN-5 (Wave I-N, Andrew 2026-10-06: "the What Changed below … you could probably just call that a news feed"): the
// block's heading; the code keeps its old name (`changed`, `what-changed`), a user only reads this one
export const NEWS_FEED = "News feed";
// ---- end IN-5

// ---- II-4 (Wave I-I; the product and analytics review § 7–8): My Week's "What changed" as a decision-impact feed and
// the home's three clocks. The API sends each line's five parts (INTERFACES.md § II-4); an answer from before Wave I-I
// (no `decision_status`) renders as IF-4 drew it.
import type { ChangedLine, DecisionStatus, WaiverCard } from "./api";

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

// ---- II-4 (Wave I-I; the review § 8 "Waivers"): the top claims say WHEN they help — this week, a future bye, later in
// the window, or an upside stash — and the claims that compete for the same roster spot are named (claims evaluated one
// by one are not a combined plan).
export type Horizon = { key: "now" | "bye" | "later" | "stash"; label: string; week: number | null };

const sg = (x: number) => `${x >= 0 ? "+" : "−"}${Math.abs(x).toFixed(1)}`;

/** When a claim helps (`week` = the decision week; `week_gains[i]` = week + i). */
export function horizonOf(c: WaiverCard, week: number): Horizon {
  const tw = c.this_week ?? c.move.weekly_gain ?? 0;
  if (tw >= 0.05) return { key: "now", label: `Helps this week (${sg(tw)})`, week };
  const gains = c.move.week_gains ?? [];
  const i = gains.findIndex((g) => (g ?? 0) >= 0.05);
  const w = i >= 0 ? week + i : null;
  if (c.move.list_kind === "cover" && w !== null) return { key: "bye", label: `Covers a bye in week ${w}`, week: w };
  if (w !== null) return { key: "later", label: `Helps from week ${w}`, week: w };
  return { key: "stash", label: "Upside stash: no lineup gain yet", week: null };
}

/** The intro above the top claims: what each one does and over which weeks (never "each adds this week" when it does not). */
export function topIntro(cards: WaiverCard[], week: number, last: number): string {
  if (!cards.length) return "";
  const hs = cards.map((c) => horizonOf(c, week));
  const n = cards.length;
  const head = n === 1 ? "The strongest claim" : `The ${n === 2 ? "two" : "three"} strongest claims`;
  const now = hs.filter((h) => h.key === "now").length;
  const bye = hs.filter((h) => h.key === "bye");
  const later = hs.filter((h) => h.key === "later");
  const stash = hs.filter((h) => h.key === "stash").length;
  const parts: string[] = [];
  if (now) parts.push(now === n ? (n === 1 ? "it helps this week" : "each helps this week") : `${now} help${now === 1 ? "s" : ""} this week`);
  if (bye.length) {
    const weeks = [...new Set(bye.map((h) => h.week))]; // PO: "weeks" counts the distinct weeks, not the claims
    parts.push(`${bye.length} cover${bye.length === 1 ? "s" : ""} a bye (week${weeks.length === 1 ? "" : "s"} ${weeks.join(", ")})`);
  }
  if (later.length) parts.push(`${later.length} help${later.length === 1 ? "s" : ""} later in the window`);
  if (stash) parts.push(`${stash} ${stash === 1 ? "is an upside stash" : "are upside stashes"}`);
  const span = last > week ? `weeks ${week}–${last}` : `week ${week}`;
  return `${head} below: ${parts.join(", ")}. Each card's total is its gain over ${span}.`;
}

/** Claims that compete for the same roster spot (the same drop, or the API's `alternative_to`): one line each. */
export function competing(cards: WaiverCard[]): string[] {
  const out: string[] = [];
  const byDrop = new Map<string, WaiverCard[]>();
  for (const c of cards) {
    const d = c.move.drop?.sleeper_id;
    if (d) byDrop.set(d, [...(byDrop.get(d) ?? []), c]);
  }
  for (const cs of byDrop.values()) {
    if (cs.length < 2) continue;
    const names = cs.map((c) => c.move.add.player_name);
    out.push(`${names.slice(0, -1).join(", ")} and ${names[names.length - 1]} compete for the same roster spot (each drops ${cs[0].move.drop?.player_name}): claim one of them.`);
  }
  for (const c of cards) {
    if (c.alternative_to && !out.some((l) => l.includes(c.move.add.player_name ?? "\u0000")))
      out.push(`${c.move.add.player_name} and ${c.alternative_to} compete for the same starting spot this week: claim one of them.`);
  }
  return out;
}
// ---- end II-4
