// ---- IF-4 (Wave I-F, the decision-quality review's table of language fixes): shared words. One matchup-rank direction
// everywhere, always said in words (the review: "prefer '2nd-fewest WR points allowed' to an unexplained #31"), the same
// as the console's `cards.rank_words`.
function ordinal(k: number): string {
  const s = k % 100 >= 10 && k % 100 <= 20 ? "th" : ({ 1: "st", 2: "nd", 3: "rd" } as Record<number, string>)[k % 10] ?? "th";
  return `${k}${s}`;
}

/** 31 of 32 vs WR → "2nd-fewest WR points allowed"; 5 → "5th-most WR points allowed"; "" when unknown. */
export function rankWords(rank: number | null | undefined, position: string | null | undefined, n = 32): string {
  if (rank == null || !Number.isFinite(rank)) return "";
  const pos = (position ?? "").toUpperCase() || "his position's";
  const k = Math.round(rank);
  if (k <= Math.floor((n + 1) / 2)) return k === 1 ? `the most ${pos} points allowed` : `${ordinal(k)}-most ${pos} points allowed`;
  const f = n + 1 - k;
  return f === 1 ? `the fewest ${pos} points allowed` : `${ordinal(f)}-fewest ${pos} points allowed`;
}
// ---- end IF-4
