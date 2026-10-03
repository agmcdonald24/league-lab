// The research screens' words and small sums (Wave G, G3). Words follow docs/WORDS.md: "expected points a game: what
// his targets and carries are usually worth"; below expectation = due to pick up, above = due to cool off (IA-1: Andrew's
// "below / above expectation" in place of "due / running hot").
import { fmt } from "./theme";

export const NEAR = 0.5; // points a game: closer than this to his work is "about what his work is worth"

export function gapWords(gap: number | null | undefined): string {
  if (gap === null || gap === undefined) return "no expected points yet";
  if (gap > NEAR) return "above expectation: expect him to cool off";
  if (gap < -NEAR) return "below expectation: expect him to pick up";
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
