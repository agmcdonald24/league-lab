// My Week's two header lines, from the API's own words and numbers.
import type { ActionKind, MyWeek, Opponent, Waivers, WeekAction } from "./api"; // IE-1: ActionKind, Waivers, WeekAction

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

// ---- IB-3 (Wave I-B): the My Week card's default content — a status per call (Roster alert / Already set / Close call;
// IN-5: "Roster alert" was "Change needed"), the call in one line, its strength, one reason, a Compare button; the odds, the ranges and the numbers behind
// "Why?". IB-0's API sends `status` / `strength` on each card; until it does (or for an answer saved before), they are
// derived here the same way (cards.is_coin_flip; the starter's `is_current_starter` on the lineup rows).
import type { DecisionCard, LineupRow } from "./api";

export type CardStatus = "change" | "set" | "close";
export type CardStrength = "clear" | "lean" | "coin flip";
// ---- IN-5 (Wave I-N, Andrew 2026-10-06: "you could probably just say, like, roster alert instead of change needed")
export const STATUS_WORD: Record<CardStatus, string> = { change: "Roster alert", set: "Already set", close: "Close call" };
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

// ---- IE-1 (Wave I-E, the casual-user review § "weekly action list"): My Week's first layer — the API's actions (a
// change the submitted lineup needs, then a close call), plus Waivers' `home_action` (a claim that changes this week's
// starters) when there is room: at most three, the most urgent first.
export const ACTION_WORD: Record<ActionKind, string> = { change: "Roster alert", close: "Close call", move: "Waiver claim" }; // IN-5: was "Change needed"
export const MAX_ACTIONS = 3;

/** The actions to show: My Week's, then the claim from Waivers when there is room and it is not about a player an
 * action already names (the one it adds, or the one it drops). */
export function homeActions(d: MyWeek, w: Waivers | null | undefined): WeekAction[] {
  const acts = [...(d.actions ?? [])];
  const move = w?.home_action;
  if (move && acts.length < MAX_ACTIONS) {
    const named = new Set(acts.flatMap((a) => [...a.start, ...a.sit].map((p) => p.key)));
    // not about a player an action already names: neither the one it adds nor the one it drops
    const drop = move.drop?.key;
    if (!move.start.some((p) => p.key && named.has(p.key)) && !(drop && named.has(drop))) acts.push(move);
  }
  return acts.slice(0, MAX_ACTIONS).sort((a, b) => a.urgency - b.urgency);
}
// ---- end IE-1

// ---- IN-5 (Wave I-N): an open starting spot's next step — Waivers at its position (the screen reads ?position=); a
// flex or a team unit: every free agent
const WAIVER_POSITIONS = new Set(["QB", "RB", "WR", "TE", "K", "DEF"]);
export function waiversFor(slotType: string | null | undefined): string {
  const t = String(slotType ?? "").toUpperCase().replace(/\d+$/, "");
  return WAIVER_POSITIONS.has(t) ? `/waivers?position=${t}` : "/waivers";
}
// ---- end IN-5

// ---- IX-4 (Wave I-X; the review of 10 October § 1): ONE matchup summary. The API sends `matchup`
// (`myweek.matchup_summary`); an answer saved before it carries the same numbers in `lineup_value`, `opponent` and
// `win`, so the same words are built from them here (the API's sentence wins when it is there).
import type { Matchup, MatchupGame, WinProbability } from "./api";

export const MATCHUP_BEFORE_BASIS = "Each side's best lineup by our projections.";
export const MATCHUP_LIVE_BASIS = "Points scored so far plus projections for players still to play";
export const MATCHUP_NO_POINTS = "a game has kicked off; no points are in yet";
export const MATCHUP_NO_LIVE = "Each side's best lineup by our projections; this league's live scores are not read yet.";
export const MATCHUP_FINAL_BASIS = "Points scored: every starter on both sides has played.";

function pts(a: number, b: number): [string, string] {
  const fine = Math.round(a) === Math.round(b) && Math.abs(a - b) >= 0.05;
  return fine ? [a.toFixed(1), b.toFixed(1)] : [String(Math.round(a)), String(Math.round(b))];
}

/** "You're a clear underdog this week: 31%." — the chance without the totals (myweek.chance_words). */
export function chanceWords(w: WinProbability | null | undefined): string | null {
  if (!w || w.p === null || w.p === undefined || w.percent === null || !w.words) return null;
  return w.words === "a coin flip" ? `This week is a coin flip: ${w.percent}%.` : `You're ${w.words} this week: ${w.percent}%.`;
}

function oneGame(week: number, team: string, mine: number | null, theirs: number | null, w: WinProbability | null | undefined): MatchupGame {
  const head = `Week ${week} vs **${team}**`;
  const started = (w?.n_started ?? 0) + (w?.opp_n_started ?? 0) > 0 || !!(w?.n_played || w?.opp_n_played);
  if (started && w && w.mine !== null && w.mine !== undefined && w.theirs !== null && w.theirs !== undefined) {
    const [a, b] = pts(w.mine, w.theirs);
    if (w.n_starters && w.n_played === w.n_starters && w.opp_n_played === w.opp_n_starters)
      return { state: "final", line: `${head}: ${a} to ${b}.`, basis: MATCHUP_FINAL_BASIS, chance: null, mine: w.mine, theirs: w.theirs };
    const played = w.played_words || MATCHUP_NO_POINTS;
    return { state: "live", line: `${head}: ${a} to ${b} expected.`, basis: `${MATCHUP_LIVE_BASIS} (${played}).`, chance: chanceWords(w), mine: w.mine, theirs: w.theirs };
  }
  if (mine === null || theirs === null) return { state: "before", line: `${head}.`, basis: null, chance: null, mine, theirs };
  const [a, b] = pts(mine, theirs);
  return { state: started ? "live" : "before", line: `${head}: you project ${a}, they project ${b}.`,
    basis: started ? MATCHUP_NO_LIVE : MATCHUP_BEFORE_BASIS, chance: started ? null : chanceWords(w), mine, theirs };
}

/** The one matchup summary: the API's, else built from the answer's own numbers; null without a matchup. */
export function matchupOf(d: MyWeek): Matchup | null {
  if (d.matchup !== undefined) return d.matchup;
  const o = opponentObject(d);
  if (!o || !o.team_name || d.week === null) return null;
  const w = d.win ?? null;
  const more = (o.also ?? []).filter((x) => x && x.team_name);
  const games = [oneGame(d.week, o.team_name, d.lineup_value ?? null, o.lineup_value ?? null, w),
    ...more.map((x) => oneGame(d.week as number, x.team_name as string, d.lineup_value ?? null, x.lineup_value ?? null,
      (w?.also ?? []).find((y) => y.opponent_roster_id === x.roster_id) ?? null))];
  return { ...games[0], ...(games.length > 1 ? { also: games.slice(1) } : {}), assumptions: w?.assumptions ?? null };
}

/** The league-rank sentence as detail, never a second total: an answer saved before IX-4 said "Your best lineup projects
 * **125.07** in week 5, 3rd of 12 in the league." — the rank is kept, the total dropped ("" without a rank). */
export function rankLine(d: MyWeek): string {
  const l = d.league_line ?? "";
  const old = /^Your best lineup projects \*\*[\d.]+\*\* in week (\d+)(?:, (.+?))?\.$/.exec(l);
  if (!old) return l;
  return old[2] ? `Your best lineup ranks ${old[2]} in week ${old[1]}.` : "";
}

/** At most three decisions first (the most urgent: a starter who cannot play, a call to re-check before a kickoff, a
 * claim before waivers run), the rest behind "More": the API's first three and its `more_actions`, the claim from
 * Waivers, then the close calls the lineup already follows. */
export function decisionsOf<R>(d: MyWeek, w: Waivers | null | undefined, review: R[]): { first: (WeekAction | R)[]; more: (WeekAction | R)[] } {
  const acts = [...(d.actions ?? []), ...(d.more_actions ?? [])];
  const move = w?.home_action;
  if (move) {
    // not about a player an action already names: neither the one it adds nor the one it drops (homeActions' rule)
    const named = new Set(acts.flatMap((a) => [...a.start, ...a.sit].map((p) => p.key)));
    const drop = move.drop?.key;
    if (!move.start.some((p) => p.key && named.has(p.key)) && !(drop && named.has(drop))) acts.push(move);
  }
  acts.sort((a, b) => a.urgency - b.urgency);
  const all: (WeekAction | R)[] = [...acts, ...review];
  return { first: all.slice(0, MAX_ACTIONS), more: all.slice(MAX_ACTIONS) };
}
// ---- end IX-4
