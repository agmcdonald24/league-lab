// ---- JA-1 (Wave J-A): the weeks you choose — the URL keys of the week slider (components/stretch/WeekSlider.svelte),
// shared by Stats and (JA-2) Compare and Matchups. Keys: `window` (season | last3 | last5 | last3w | last5w | weeks),
// `weeks` (A, "3-4", with window=weeks), `vs` (B, "1-2": a second stretch to compare with). Season is the default and
// writes nothing.
export type Win = "season" | "last3" | "last5" | "last3w" | "last5w" | "weeks";
export type Range = [number, number];
export const WINS: Win[] = ["season", "last3", "last5", "last3w", "last5w", "weeks"];
export const STRETCH_KEYS = ["window", "weeks", "vs"] as const;

export function parseRange(s: string | null | undefined): Range | null {
  const m = (s ?? "").match(/^(\d{1,2})-(\d{1,2})$/);
  if (!m) return null;
  const lo = Number(m[1]);
  const hi = Number(m[2]);
  return lo >= 1 && lo <= hi && hi <= 22 ? [lo, hi] : null;
}
export const rangeKey = (r: Range) => `${r[0]}-${r[1]}`;

export interface Stretch {
  win: Win;
  weeks: Range | null; // window=weeks only
  vs: Range | null;
}
export function readStretch(params: URLSearchParams): Stretch {
  const w = params.get("window") as Win | null;
  const win: Win = w && WINS.includes(w) ? w : "season";
  const weeks = parseRange(params.get("weeks"));
  return { win: win === "weeks" && !weeks ? "season" : win, weeks: win === "weeks" ? weeks : null, vs: parseRange(params.get("vs")) };
}

/** A's weeks for a week-based window, within the season's played weeks [first, last]; null for his last N games. */
export function weeksOf(s: Stretch, first: number, last: number): Range | null {
  const c = (r: Range): Range => [Math.max(first, Math.min(r[0], last)), Math.max(first, Math.min(r[1], last))];
  if (s.win === "season") return [first, last];
  if (s.win === "last3w") return c([last - 2, last]);
  if (s.win === "last5w") return c([last - 4, last]);
  if (s.win === "weeks" && s.weeks) return c(s.weeks);
  return null;
}

const span = (r: Range) => (r[0] === r[1] ? `Week ${r[0]}` : `Weeks ${r[0]}–${r[1]}`);
const count = (r: Range) => `${r[1] - r[0] + 1} week${r[1] === r[0] ? "" : "s"}`;
/** The choice in words: "Weeks 3–4 · 2 weeks", "Week 2 · 1 week", "Season · weeks 1–4", "Last 3 games played". */
export function words(s: Stretch, first: number, last: number): string {
  if (s.win === "last3" || s.win === "last5") return `His last ${s.win === "last3" ? 3 : 5} games played (any weeks)`;
  const r = weeksOf(s, first, last)!;
  if (s.win === "season") return `Season · ${span(r).toLowerCase()}`;
  return `${span(r)} · ${count(r)}`;
}
export const rangeWords = (r: Range) => `${span(r)} · ${count(r)}`;
export const rangeName = (r: Range) => span(r).toLowerCase(); // "weeks 1–2" in a sentence

/** "The weeks before": the same length, ending where A starts (cut at the first week); null when A starts the season. */
export function weeksBefore(a: Range, first: number): Range | null {
  if (a[0] <= first) return null;
  const n = a[1] - a[0] + 1;
  return [Math.max(first, a[0] - n), a[0] - 1];
}
/** "The rest of the season": every played week outside A on one side — before it when A ends the season, else after. */
export function restOfSeason(a: Range, first: number, last: number): Range | null {
  if (a[1] < last) return [a[1] + 1, last];
  if (a[0] > first) return [first, a[0] - 1];
  return null;
}

/** The URL keys for A (and B): the whole season writes nothing; a week range writes window=weeks&weeks=lo-hi. */
export function stretchParams(win: Win, a: Range | null, vs: Range | null, first: number, last: number): Record<string, string | null> {
  if (win === "weeks" && a && a[0] === first && a[1] === last) return { window: null, weeks: null, vs: vs ? rangeKey(vs) : null };
  if (win === "weeks" && a) return { window: "weeks", weeks: rangeKey(a), vs: vs ? rangeKey(vs) : null };
  return { window: win === "season" ? null : win, weeks: null, vs: vs && (win === "season" || win === "last3w" || win === "last5w") ? rangeKey(vs) : null };
}
// ---- end JA-1
