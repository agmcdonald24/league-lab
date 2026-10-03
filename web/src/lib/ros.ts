// Rest of season (GET /api/ros): the screen's answer line and its numbers. The words follow the Streamlit Rankings
// page's "Rest of season" block (app/pages/4_Rankings.py, with app/lib/ros.py's whole points and range words): the
// /api/ros contract carries numbers only, so the sentence is assembled here (a request to F3: send it).
import type { RosPlayer } from "./api";

/** Round half up to a whole point (app/lib/ros.py `whole`); null stays null. */
export function whole(v: number | null | undefined): number | null {
  return v === null || v === undefined || Number.isNaN(v) ? null : Math.floor(v + 0.5);
}

/** "118–166", null without a range (ros.range_words). */
export function rangeWords(p: { p10: number | null; p90: number | null }): string | null {
  const lo = whole(p.p10);
  const hi = whole(p.p90);
  return lo === null || hi === null ? null : `${lo}–${hi}`;
}

/** "weeks 4–16" / "week 16" (ros.weeks_span). */
export function weeksSpan(first: number | null, last: number | null): string | null {
  if (first === null || last === null) return null;
  return first === last ? `week ${first}` : `weeks ${first}–${last}`;
}

/** The rank shown in the list: the position rank, or on "All" the overall rank (the API's `rank` if it sends one,
 * else the list's order: the list comes sorted by it). */
export function rankOf(p: RosPlayer, i: number, position: string): number | null {
  if (position === "ALL") return p.rank ?? i + 1;
  return p.pos_rank;
}

/** "**#1 WR for the rest of the season: Chris Olave, 241 points over 13 games** (likely 205–280) · playoffs: 52." */
export function answerLine(top: RosPlayer, position: string): string {
  const what = position === "ALL" ? "overall" : position;
  const label = position === "ALL" ? `${top.player_name} (${top.position})` : top.player_name;
  const games = top.ros_games ?? 0;
  let s = `**#1 ${what} for the rest of the season: ${label}, ${whole(top.ros_points)} points over ${games} game${games === 1 ? "" : "s"}**`;
  const rng = rangeWords(top);
  if (rng) s += ` (likely ${rng})`;
  const po = whole(top.playoff_points);
  if (po !== null && po > 0) s += ` · playoffs: ${po}`;
  return s + ".";
}

/** "Yours: #4 Amon-Ra St. Brown 176 · #19 Zay Flowers 127 … and 2 more in the table." ("" without a team) */
export function yoursLine(players: RosPlayer[], team: number | null, position: string): string {
  if (team === null) return "";
  const mine = players.map((p, i) => ({ p, k: rankOf(p, i, position) })).filter((x) => x.p.rostered_by_roster_id === team && x.k !== null);
  if (!mine.length) return `Yours: none of your players in this top ${players.length}.`;
  const shown = mine.slice(0, 4).map((x) => `#${x.k} ${x.p.player_name} ${whole(x.p.ros_points)}`);
  const more = mine.length > 4 ? ` … and ${mine.length - 4} more in the table` : "";
  return `Yours: ${shown.join(" · ")}${more}.`;
}

// ---- IA-3 (Wave I-A): the table's pieces, the sort, the range bar, the honesty line
/** The piece columns per position (per game, projected): the API's `piece_columns` when it sends them. */
export const PIECE_COLUMNS: Record<string, string[]> = {
  QB: ["attempts", "passing_yards", "passing_tds", "passing_interceptions"],
  RB: ["carries", "rushing_yards", "targets", "receptions", "receiving_yards", "tds"],
  WR: ["targets", "receptions", "receiving_yards", "tds"],
  TE: ["targets", "receptions", "receiving_yards", "tds"],
};
/** Column header (short) and its words (the header's title and the expanded row's label). */
export const PIECE_LABELS: Record<string, [string, string]> = {
  attempts: ["Att", "passes"],
  passing_yards: ["Pass yd", "passing yards"],
  passing_tds: ["Pass TD", "passing TDs"],
  passing_interceptions: ["INT", "interceptions"],
  carries: ["Car", "carries"],
  rushing_yards: ["Rush yd", "rushing yards"],
  targets: ["Tgt", "targets"],
  receptions: ["Rec", "catches"],
  receiving_yards: ["Rec yd", "receiving yards"],
  tds: ["TD", "touchdowns"],
};

/** A piece as people say it: whole yards and passes, one decimal for counts, two for a share of a touchdown. */
export function pieceText(key: string, v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  if (key.endsWith("yards") || key === "attempts") return v.toFixed(0);
  if (key.endsWith("tds") || key === "passing_interceptions") return v.toFixed(2);
  return v.toFixed(1);
}

export type SortKey = "rank" | "ros_points" | "ros_games" | "playoff_points" | "range" | `pg:${string}`;

/** The value a column sorts by (null last either way). */
export function sortValue(p: RosPlayer, key: SortKey, i: number, position: string): number | null {
  if (key === "rank") return rankOf(p, i, position) ?? null;
  if (key === "range") return p.p10 === null || p.p90 === null ? null : p.p90 - p.p10;
  if (key.startsWith("pg:")) return p.per_game?.[key.slice(3)] ?? null;
  const v = p[key as "ros_points" | "ros_games" | "playoff_points"];
  return v ?? null;
}

/** The list sorted by a column (stable; unknown last); rank ascends by default, the numbers descend. */
export function sortPlayers(players: RosPlayer[], key: SortKey, dir: "asc" | "desc", position: string): RosPlayer[] {
  const rows = players.map((p, i) => ({ p, i, v: sortValue(p, key, i, position) }));
  rows.sort((a, b) => {
    if (a.v === null && b.v === null) return a.i - b.i;
    if (a.v === null) return 1;
    if (b.v === null) return -1;
    const d = dir === "asc" ? a.v - b.v : b.v - a.v;
    return d !== 0 ? d : a.i - b.i;
  });
  return rows.map((r) => r.p);
}

/** The small range bar: where p10, the points and p90 sit on a 0..max scale, in percent (null without a range). */
export function rangeBar(p: { p10: number | null; p90: number | null; ros_points: number | null }, max: number) {
  if (p.p10 === null || p.p90 === null || p.ros_points === null || !(max > 0)) return null;
  const pc = (v: number) => Math.max(0, Math.min(100, (v / max) * 100));
  return { lo: pc(p.p10), hi: pc(p.p90), mid: pc(p.ros_points) };
}

/** "bye week 11" / "byes 9, 14" / "" */
export function byeWords(weeks: number[] | undefined): string {
  if (!weeks?.length) return "";
  return weeks.length === 1 ? `bye week ${weeks[0]}` : `byes ${weeks.join(", ")}`;
}

/** The ROS screen's top paragraph when the API does not send it (about.py RANKINGS_HOWTO is the source). */
export const RANKINGS_HOWTO =
  "**How to read the rankings.** We project each player from his work, not his name: his targets, carries and " +
  "passes, his role, how fast his offense plays and the defenses left on his schedule. A star whose targets are " +
  "down reads lower than his name; a quarterback who starts and throws 35 times a game counts like any starter " +
  "while he starts. In a superflex league, or one that pays 6 points for a passing touchdown, quarterbacks lead " +
  "the list by design, and among them volume beats reputation. Sleeper's own number is there to compare: where " +
  "ours is far from it, open his card and read why before you trade on it.";
// ---- end IA-3
