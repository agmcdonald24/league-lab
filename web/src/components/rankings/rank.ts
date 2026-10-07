// ---- IP-2 (Wave I-P): the rankings screen's pure pieces (no component state): the position words, the URL's picks,
// the range bar's scale, the kickoff words, the Compare link for two to four picked players.
import type { RankPosition, RankRow, RankView } from "../../lib/api";
import { withContext } from "../../lib/md";

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

/** The scale the rows on screen share. This week: from 0 to the highest high end (a floor of 0 is a real week). The
 * rest of the season: the spread around each projection (a season's range is narrow against its total, so on a scale
 * from 0 every bar would be a sliver at one end) — the tick in the middle, the widest spread on the page reaching the
 * edges, the numbers printed beside it. */
export type Scale = { kind: "points"; hi: number } | { kind: "spread"; w: number };
export function scaleOf(rows: RankRow[], view: RankView = "week"): Scale {
  if (view === "week") return { kind: "points", hi: Math.max(1, ...rows.map((r) => r.p90 ?? r.proj_points ?? 0)) };
  const w = Math.max(
    1,
    ...rows.map((r) => (r.proj_points == null ? 0 : Math.max(r.proj_points - (r.p10 ?? r.proj_points), (r.p90 ?? r.proj_points) - r.proj_points))),
  );
  return { kind: "spread", w };
}

/** The range bar on that scale: the low end, the high end and the projection, in percent. */
export function bar(r: RankRow, s: Scale) {
  if (r.p10 === null || r.p90 === null || r.proj_points === null) return null;
  const clip = (v: number) => Math.max(0, Math.min(100, v));
  if (s.kind === "points") {
    const pc = (v: number) => clip((v / s.hi) * 100);
    return { lo: pc(r.p10), hi: pc(r.p90), mid: pc(r.proj_points) };
  }
  const pc = (v: number) => clip(50 + ((v - r.proj_points!) / s.w) * 50);
  return { lo: pc(r.p10), hi: pc(r.p90), mid: 50 };
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

/** True where a new tier starts (the first row of the page counts when it opens a tier). A row without a tier (a
 * starter unclear, the rest of the season) never draws a line and is skipped when looking back. */
export function tierBreak(rows: RankRow[], i: number): boolean {
  const t = rows[i]?.tier;
  if (t == null) return false;
  for (let j = i - 1; j >= 0; j--) if (rows[j]?.tier != null) return rows[j].tier !== t;
  return true;
}
// ---- end IP-2
