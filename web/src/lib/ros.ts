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
