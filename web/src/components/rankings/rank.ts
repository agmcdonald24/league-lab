// ---- IP-2 (Wave I-P): the rankings screen's pure pieces (no component state): the position words, the URL's picks,
// the range bar's scale, the kickoff words, the Compare link for two to four picked players.
import type { RankPosition, RankRow, RankView } from "../../lib/api";
import { withContext } from "../../lib/md";
import { rangeBar } from "../../lib/ros";

export const POSITIONS: RankPosition[] = ["QB", "RB", "WR", "TE", "FLEX", "K", "DEF"];
export const DEFAULT_POSITION: RankPosition = "WR";
export const LIMIT = 50;
export const MAX_PICKS = 4;
export const PLURAL: Record<RankPosition, string> = {
  QB: "quarterbacks",
  RB: "running backs",
  WR: "wide receivers",
  TE: "tight ends",
  FLEX: "running backs, receivers and tight ends",
  K: "kickers",
  DEF: "defenses",
};
export const VIEWS: { key: RankView; label: string }[] = [
  { key: "week", label: "This week" },
  { key: "season", label: "Rest of season" },
];
const GSIS = /^\d{2}-\d{7}$/;

export function positionOf(param: string | null): RankPosition {
  const p = (param ?? "").toUpperCase() as RankPosition;
  return POSITIONS.includes(p) ? p : DEFAULT_POSITION;
}

export function viewOf(param: string | null): RankView {
  return param === "season" ? "season" : "week";
}

/** The picked players in the URL (`pick=a,b,c`): ids only, at most four, no repeats. */
export function picksOf(param: string | null): string[] {
  const out: string[] = [];
  for (const s of (param ?? "").split(",")) {
    const g = s.trim();
    if (GSIS.test(g) && !out.includes(g) && out.length < MAX_PICKS) out.push(g);
  }
  return out;
}

export function togglePick(picks: string[], gsis: string): string[] {
  if (picks.includes(gsis)) return picks.filter((g) => g !== gsis);
  return picks.length >= MAX_PICKS ? picks : [...picks, gsis];
}

/** Compare with the picks: a, b (the side-by-side) and c, d (the start answer takes up to four). */
export function compareHref(league: string, team: number | null, picks: string[]): string {
  const keys = ["a", "b", "c", "d"];
  const q = picks
    .slice(0, MAX_PICKS)
    .map((g, i) => `${keys[i]}=${encodeURIComponent(g)}`)
    .join("&");
  return withContext(`/compare?${q}`, { league, team });
}

/** The ids Compare's start answer reads: a, b, c, d in the URL (ids only, no repeats). */
export function compareIds(params: URLSearchParams): string[] {
  return picksOf(["a", "b", "c", "d"].map((k) => params.get(k) ?? "").join(","));
}

/** The range bar on one scale for the rows on screen: the low end, the high end and the projection, in percent. */
export function bar(r: RankRow, max: number) {
  return rangeBar({ p10: r.p10, p90: r.p90, ros_points: r.proj_points }, max);
}

export function scaleOf(rows: RankRow[]): number {
  return Math.max(1, ...rows.map((r) => r.p90 ?? r.proj_points ?? 0));
}

export function kickoff(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  return `${d.toLocaleString("en-US", { weekday: "short", hour: "numeric", minute: "2-digit", timeZone: "America/New_York" })} ET`;
}

export const STATE_WORD: Record<string, string> = {
  started: "Started",
  final: "Final",
};

/** His status when it says something (Questionable, Out …); Active says nothing. */
export function statusOf(r: RankRow): string | null {
  return r.report_status && r.report_status !== "Active" ? r.report_status : null;
}

/** True where a new tier starts (the first row of the page counts when it opens a tier). */
export function tierBreak(rows: RankRow[], i: number): boolean {
  const t = rows[i]?.tier;
  if (t == null) return false;
  return i === 0 || rows[i - 1]?.tier !== t;
}
// ---- end IP-2
