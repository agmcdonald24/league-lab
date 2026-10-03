// The research screens' words and small sums (Wave G, G3). Words follow docs/WORDS.md: "expected points a game: what
// his targets and carries are usually worth"; below expectation = due to pick up, above = due to cool off (IA-1: Andrew's
// "below / above expectation" in place of "due / running hot").
import { fmt } from "./theme";

export const NEAR = 0.5; // points a game: closer than this to his work is "about what his work is worth"

export function gapWords(gap: number | null | undefined): string {
  if (gap === null || gap === undefined) return "no expected points yet";
  // ---- IF-4 (the decision-quality review: no promise of regression): the observed gap, said as one
  if (gap > NEAR) return `${fmt.pts(gap)} above what his opportunities suggest: an observed gap, not a forecast`;
  if (gap < -NEAR) return `${fmt.pts(-gap)} below what his opportunities suggest: an observed gap, not a forecast`;
  return "about what his work is worth";
}

/** "14.9 a game on work worth 25.3" */
export function workLine(ppg: number | null, xppg: number | null): string {
  if (ppg === null) return "no games yet";
  return xppg === null ? `${fmt.pts(ppg)} a game` : `${fmt.pts(ppg)} a game on work worth ${fmt.pts(xppg)}`;
}

/** Who owns him, from the viewer's side: "yours" / the team / "free agent". */
export function ownerWord(p: { rostered_by_roster_id: number | null; rostered_by_team: string | null }, team: number | null): string {
  if (team !== null && p.rostered_by_roster_id === team) return "yours";
  return p.rostered_by_team ?? "free agent";
}

export type Who = "all" | "mine" | "fa" | "rostered";
export function whoFilter(who: Who, team: number | null) {
  return (p: { rostered_by_roster_id: number | null }) =>
    who === "all" ||
    (who === "mine" && team !== null && p.rostered_by_roster_id === team) ||
    (who === "fa" && p.rostered_by_roster_id === null) ||
    (who === "rostered" && p.rostered_by_roster_id !== null);
}

/** A matchup rank in words (1 = gives up the most to the position): the matchup you want … a tough one. */
export function rankWord(rank: number | null | undefined, n = 32): string {
  if (rank === null || rank === undefined) return "";
  if (rank <= Math.round(n / 4)) return "a good matchup";
  if (rank > n - Math.round(n / 4)) return "a tough matchup";
  return "an average matchup";
}

export const pct = (v: number | null | undefined) => fmt.pct(v);

// ---- IA-1: Trends in plain words
const WORK_WORDS: Record<string, string> = { QB: "the throws and runs", RB: "the carries and targets", WR: "the targets", TE: "the targets" };

/** "getting the targets of a 15.3-point player, scoring 3.6" (the API's `why` without its reason; for rows saved before it) */
export function expectLine(p: { position?: string | null; ppg: number | null; xppg: number | null }): string {
  if (p.ppg === null || p.ppg === undefined) return "no games yet";
  if (p.xppg === null || p.xppg === undefined) return `scoring ${fmt.pts(p.ppg)} a game`;
  const x = p.xppg.toFixed(1);
  const an = /^(8|11\.|18\.)/.test(x) ? "an" : "a";
  return `getting ${WORK_WORDS[p.position ?? ""] ?? "the work"} of ${an} ${x}-point player, scoring ${p.ppg.toFixed(1)}`;
}

/** "7.5 (7.0)": the last 3 games, the season in brackets; "—" when unknown (unknown is not zero) */
export function l3Season(l3: number | null | undefined, season: number | null | undefined): { l3: string; season: string } {
  const f = (v: number | null | undefined) => (v === null || v === undefined ? "—" : v.toFixed(1));
  return { l3: f(l3), season: f(season) };
}
// ---- end IA-1

// ---- IB-3 (Wave I-B): matchup meaning first. Favorable / Neutral / Difficult is the signal; the rank runs one way on
// the whole screen (1 = the toughest for the offense: the defense that gives up the fewest, the corner hardest to
// throw on) and is said in words where that reads better. The API sends `tone`, `tough_rank`, `rank_words` (defense)
// and `tone`, `certainty`, `named_corners` (cornerbacks); these mirror research.py for an answer saved before them.
export type Tone = "favorable" | "neutral" | "difficult";
export const TONE_WORD: Record<Tone, string> = { favorable: "Favorable", neutral: "Neutral", difficult: "Difficult" };
/** The tone's token (the state colors: good / ink-3 / bad) and a glyph, so color never carries the tone alone. */
export const TONE_COLOR: Record<Tone, string> = { favorable: "var(--ll-good)", neutral: "var(--ll-ink-3)", difficult: "var(--ll-bad)" };
export const TONE_GLYPH: Record<Tone, string> = { favorable: "▲", neutral: "", difficult: "▼" };
export const toneWash = (t: Tone | null | undefined, pct = 22) =>
  t ? `color-mix(in oklab, ${TONE_COLOR[t]} ${t === "neutral" ? Math.round(pct * 0.6) : pct}%, transparent)` : "var(--ll-sunken)";

/** How many ranks at each end of n are favorable / difficult: 10 of 32 (the card's reason line: ≤ 10, ≥ 23). */
export const toneEdge = (n: number) => Math.max(1, Math.round((n * 10) / 32));

/** The tone from the mart's rank (1 = gives up the most to the position) among n defenses. */
export function defenseTone(rankMost: number | null | undefined, n: number): Tone | null {
  if (rankMost === null || rankMost === undefined || !n) return null;
  const e = toneEdge(n);
  return rankMost <= e ? "favorable" : rankMost >= n + 1 - e ? "difficult" : "neutral";
}

/** The screen's rank: 1 = gives up the fewest (the toughest for the offense). */
export const toughRank = (rankMost: number | null | undefined, n: number) =>
  rankMost === null || rankMost === undefined || !n ? null : n + 1 - rankMost;

export function ordinal(k: number): string {
  const s = k % 100 >= 10 && k % 100 <= 20 ? "th" : ({ 1: "st", 2: "nd", 3: "rd" } as Record<number, string>)[k % 10] ?? "th";
  return `${k}${s}`;
}

/** "gives up the 2nd-most" / "gives up the 7th-fewest" (the nearer end). */
export function givesUpWords(rankMost: number | null | undefined, n: number): string | null {
  if (rankMost === null || rankMost === undefined || !n) return null;
  if (rankMost <= (n + 1) / 2) return rankMost === 1 ? "gives up the most" : `gives up the ${ordinal(rankMost)}-most`;
  const k = n + 1 - rankMost;
  return k === 1 ? "gives up the fewest" : `gives up the ${ordinal(k)}-fewest`;
}

const PLURAL: Record<string, string> = { QB: "QBs", RB: "RBs", WR: "WRs", TE: "TEs", K: "kickers" };
/** The short form for a row: "gives up the 2nd-most to RBs". */
export const givesUpShort = (rankMost: number | null | undefined, n: number, pos: string) => {
  const w = givesUpWords(rankMost, n);
  return w ? `${w} to ${PLURAL[pos] ?? pos}` : "";
};

/** A cornerback call's certainty as a chip word (the mart's call_strength): likely / unclear / no call. */
export function certaintyOf(m: { call_status: string | null; call_strength: string | null; certainty?: string | null }): string {
  if (m.certainty) return m.certainty;
  if (m.call_status !== "called") return "no call";
  return m.call_strength === "clear" ? "likely" : "unclear";
}
// ---- end IB-3
