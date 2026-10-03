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
  const ours = d.lineup_value ?? null;
  // I-C: a double header (MFL leagues can play twice in a week): "vs **A** and **B** — they project 98 and 104"
  const more = (o.also ?? []).filter((x) => x && x.team_name);
  let s = `Week ${d.week} vs **${o.team_name}**` + more.map((x) => ` and **${x.team_name}**`).join("");
  const theirs = o.lineup_value;
  if (theirs !== null && theirs !== undefined) {
    // whole points; one decimal when whole points would hide a real difference (110.69 vs 111.15)
    const fine = ours !== null && Math.round(theirs) === Math.round(ours) && Math.abs(theirs - ours) >= 0.05;
    const f = (v: number) => (fine ? v.toFixed(1) : String(Math.round(v)));
    const vals = [theirs, ...more.map((x) => x.lineup_value)].filter((v): v is number => v !== null && v !== undefined);
    s += more.length ? ` (a double header) — they project ${vals.map(f).join(" and ")}` : `, projects ${f(theirs)}`;
    if (ours !== null) s += ` — you project ${f(ours)}`;
  } else if (more.length) {
    s += " (a double header)";
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

// ---- IB-3 (Wave I-B): the My Week card's default content — a status per call (Change needed / Already set / Close
// call), the call in one line, its strength, one reason, a Compare button; the odds, the ranges and the numbers behind
// "Why?". IB-0's API sends `status` / `strength` on each card; until it does (or for an answer saved before), they are
// derived here the same way (cards.is_coin_flip; the starter's `is_current_starter` on the lineup rows).
import type { DecisionCard, LineupRow } from "./api";

export type CardStatus = "change" | "set" | "close";
export type CardStrength = "clear" | "lean" | "coin flip";
export const STATUS_WORD: Record<CardStatus, string> = { change: "Change needed", set: "Already set", close: "Close call" };
export const STRENGTH_WORD: Record<CardStrength, string> = { clear: "Clear", lean: "Lean", "coin flip": "Coin flip" };
const CLOSE_PWIN = 0.55; // cards.CLOSE_PWIN
const COIN_FLIP = 1.0; // cards.COIN_FLIP (points, without a percentage)

type Card = DecisionCard & { p_win?: number | null; status?: CardStatus | null; strength?: CardStrength | null };
type Row = LineupRow & { is_current_starter?: boolean | null };

/** cards.is_coin_flip: under 55% when the odds exist, else under a point apart. */
export function isCoinFlip(c: Card): boolean {
  return c.p_win !== null && c.p_win !== undefined ? c.p_win < CLOSE_PWIN : (c.margin ?? 0) < COIN_FLIP;
}

/** The call's status: the API's, else close on a coin flip, else set / change from Sleeper's current lineup (null: not
 * known — the card shows no status chip rather than a guess). */
export function cardStatus(c: Card, rows: Row[]): CardStatus | null {
  if (c.status) return c.status;
  if (isCoinFlip(c)) return "close";
  const me = rows.find((r) => r.gsis_id !== null && r.gsis_id === c.gsis_id);
  if (me?.is_current_starter === null || me?.is_current_starter === undefined) return null;
  return me.is_current_starter ? "set" : "change";
}

/** The strength word: clear (3+ points apart or 70%+), lean, coin flip. */
export function cardStrength(c: Card): CardStrength {
  if (c.strength) return c.strength;
  if (isCoinFlip(c)) return "coin flip";
  return (c.margin ?? 0) >= 3 || (c.p_win ?? 0) >= 0.7 ? "clear" : "lean";
}

/** The call in one line, both names whole and linked: "Start **[A](…)** over [B](…)" / "**[A](…)** or **[B](…)**". */
export function cardCall(c: Card, status: CardStatus | null): string {
  const a = c.gsis_id ? `[${c.player_name}](/player/${c.gsis_id})` : c.player_name;
  const b = c.alt_name ? (c.alt_gsis_id ? `[${c.alt_name}](/player/${c.alt_gsis_id})` : c.alt_name) : null;
  if (!b) return `Start **${a}**`;
  if (status === "close") return `**${a}** or **${b}**`;
  return `${status === "set" ? "Keep" : "Start"} **${a}** over ${b}`;
}

/** The blocks behind "Why?": everything but the headline (the first block) and the reason sentence. */
export function whyBlocks(c: Card) {
  return c.blocks.filter((b, i) => i > 0 && !(c.why && b.text === c.why));
}

/** Compare prefilled with both players (null when one has no card). */
export function compareHref(c: Card): string | null {
  return c.gsis_id && c.alt_gsis_id ? `/compare?a=${encodeURIComponent(c.gsis_id)}&b=${encodeURIComponent(c.alt_gsis_id)}` : null;
}
// ---- end IB-3
