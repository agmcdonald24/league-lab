// My Week's two header lines, from the API's own words and numbers.
import type { MyWeek, Opponent } from "./api";

function opponentObject(d: MyWeek): Opponent | null {
  return d.opponent && typeof d.opponent === "object" ? d.opponent : null;
}

/** Home's record line without the team name (the heading shows it): "0-2, #10 in the league". When the API sends the
 * contract's opponent object, the "week 4 vs **X**" part moves to its own line (opponentLine), so it is dropped here. */
export function recordLine(d: MyWeek): string {
  const parts = d.summary.split(" · ").slice(1);
  return (opponentObject(d) ? parts.filter((p) => !/^week \d+ vs /.test(p)) : parts).join(" · ");
}

/** "Week 5 vs **Team**, projects 108 — you project 112" (whole points, as in the plan's example);
 * just "Week 5 vs **Team**" when a value is missing; "" without a matchup (a bye week, the playoffs not reached). */
export function opponentLine(d: MyWeek): string {
  const o = opponentObject(d);
  if (!o || !o.team_name || d.week === null) return "";
  let s = `Week ${d.week} vs **${o.team_name}**`;
  const theirs = o.lineup_value;
  const ours = d.lineup_value ?? null;
  if (theirs !== null && theirs !== undefined) {
    // whole points; one decimal when whole points would hide a real difference (110.69 vs 111.15)
    const fine = ours !== null && Math.round(theirs) === Math.round(ours) && Math.abs(theirs - ours) >= 0.05;
    const f = (v: number) => (fine ? v.toFixed(1) : String(Math.round(v)));
    s += `, projects ${f(theirs)}`;
    if (ours !== null) s += ` — you project ${f(ours)}`;
  }
  return s;
}

/** I0-A: "Injuries checked 2:40 PM" (the viewer's local time; the weekday too when it was not today); "" without a stamp. */
export function checkedLine(iso: string | null | undefined, now: Date = new Date()): string {
  if (!iso) return "";
  const t = new Date(iso);
  if (Number.isNaN(t.getTime())) return "";
  const time = t.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  const day = t.toDateString() === now.toDateString() ? "" : `${t.toLocaleDateString([], { weekday: "short" })} `;
  return `Injuries checked ${day}${time}`;
}
