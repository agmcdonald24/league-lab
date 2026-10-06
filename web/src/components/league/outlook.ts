// IN-6 (Wave I-N): the words and numbers of the League screen's power rankings and season outlook (GET /api/league/outlook).
import type { OutlookRow, PowerRow } from "../../lib/api";

/** "8th" */
export function ordinal(n: number): string {
  const t = n % 100;
  if (t >= 10 && t <= 20) return `${n}th`;
  return `${n}${({ 1: "st", 2: "nd", 3: "rd" } as Record<number, string>)[n % 10] ?? "th"}`;
}

/** "3–1" / "3–1–1" */
export function record(w: number, l: number, t: number): string {
  return `${w}–${l}${t ? `–${t}` : ""}`;
}

/** A chance as the page prints it: never 0% or 100% unless proven (clinched / out); "—" for unknown. */
export function chance(p: number | null | undefined, status: OutlookRow["status"] = null): string {
  if (status === "clinched") return "In";
  if (status === "eliminated") return "Out";
  if (p === null || p === undefined || Number.isNaN(p)) return "—";
  if (p < 0.005) return "<1%";
  if (p > 0.995) return ">99%";
  return `${Math.round(p * 100)}%`;
}

/** The projected final record from the simulated wins: "8.5–5.5" (the mean: one decimal; a season's games = played + left). */
export function projectedRecord(o: OutlookRow, p: PowerRow | undefined): string {
  const played = p ? p.wins + p.losses + p.ties : 0;
  const games = played + o.games_left;
  const w = o.wins_mean;
  const l = Math.max(0, games - w);
  const one = (x: number) => (Math.abs(x - Math.round(x)) < 0.05 ? String(Math.round(x)) : x.toFixed(1));
  return `${one(w)}–${one(l)}`;
}

/** "6 to 11 wins" (1 season in 10 below, 1 in 10 above) */
export function winsRange(o: OutlookRow): string {
  const lo = Math.floor(o.wins_p10);
  const hi = Math.ceil(o.wins_p90);
  return lo === hi ? `${lo} wins` : `${lo} to ${hi} wins`;
}

/** "112.0 · 7th-hardest" (rank 1 = the hardest schedule left) */
export function scheduleLeft(p: PowerRow, n: number): string {
  if (p.schedule_left === null || p.schedule_left_rank === null) return "—";
  const r = p.schedule_left_rank;
  const words = r === 1 ? "hardest" : r === n ? "easiest" : `${ordinal(r)}-hardest`;
  return `${p.schedule_left.toFixed(1)} · ${words}`;
}

/** "soft schedule so far" / "hard schedule so far" from the API's gap words; null without them */
export function gapTag(p: PowerRow): string | null {
  if (!p.gap_words) return null;
  return p.gap_words.includes("soft") ? "Soft schedule so far" : "Hard schedule so far";
}

// ---- IO-2 (Wave I-O): movement since last week's kept ranking (never from anything else: the API sends `moved` only
// from a stored snapshot)
/** "▲ 2" / "▼ 1" / "–" (the same place) */
export function movedWords(m: number): string {
  return m > 0 ? `▲ ${m}` : m < 0 ? `▼ ${-m}` : "–";
}
/** "Up 2 places since last week's ranking" (the tooltip and the screen reader's words) */
export function movedLabel(m: number): string {
  const n = Math.abs(m);
  if (!m) return "The same place as last week's ranking";
  return `${m > 0 ? "Up" : "Down"} ${n} place${n === 1 ? "" : "s"} since last week's ranking`;
}
/** "+6 since last week" / "−4 since last week"; null when it moved less than a point or is unknown */
export function oddsChange(c: number | null | undefined): string | null {
  if (c === null || c === undefined || Number.isNaN(c) || Math.abs(c) < 1) return null;
  return `${c > 0 ? "+" : "−"}${Math.abs(Math.round(c))} since last week`;
}
// ---- end IO-2
