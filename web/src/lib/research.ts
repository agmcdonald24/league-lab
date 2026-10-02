// The research screens' words and small sums (Wave G, G3). Words follow docs/WORDS.md: "expected points a game: what
// his targets and carries are usually worth"; below = due to pick up, above = due to cool off.
import { fmt } from "./theme";

export const NEAR = 0.5; // points a game: closer than this to his work is "about what his work is worth"

export function gapWords(gap: number | null | undefined): string {
  if (gap === null || gap === undefined) return "no expected points yet";
  if (gap > NEAR) return "running hot: due to cool off";
  if (gap < -NEAR) return "below his work: due to pick up";
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
