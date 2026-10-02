// The decision screens' words (plan G4): the Streamlit pages' sentences, ported where the API does not send them
// (app/pages/2_Waiver_Wire.py `_headline`, 1_Team_Hub.py's cards, 8_League.py's luck line, 6_Trade_Finder.py's
// partner card). Numbers keep their units; unknown is not zero (docs/WORDS.md).
import type { AllPlayRow, LeagueView, PartnerRow, Team, TradePlayer, WaiverMove, Waivers } from "./api";

export const f1 = (x: number | null | undefined): string => (x == null ? "—" : x.toFixed(1));
export const f2 = (x: number | null | undefined): string => (x == null ? "—" : x.toFixed(2));
/** "+3.4", never "-0.0" (trades.py `_s1`). */
export const s1 = (x: number | null | undefined): string => (x == null ? "—" : Math.abs(x) >= 0.05 ? `${x > 0 ? "+" : "−"}${Math.abs(x).toFixed(1)}` : "+0.0");
export const whole = (x: number | null | undefined): number | null => (x == null ? null : Math.floor(x + 0.5));

export function ordinal(n: number): string {
  const k = Math.round(n);
  const suffix = k % 100 >= 10 && k % 100 <= 20 ? "th" : ({ 1: "st", 2: "nd", 3: "rd" } as Record<number, string>)[k % 10] ?? "th";
  return `${k}${suffix}`;
}

/** "Superflex" for SUPER_FLEX, "FLEX" stays; slot numbers kept ("RB2"). */
export const slotLabel = (s: string | null | undefined): string => (s ?? "").replace("SUPER_FLEX", "Superflex");

// ------------------------------------------------------------------ waivers
function span(m: WaiverMove, week: number, last: number): string {
  void m;
  const n = last - week + 1;
  return n > 1 ? `the next ${n} weeks` : "this week only";
}

function weeksText(m: WaiverMove, week: number): string {
  const helped = (m.week_gains ?? []).map((g, i) => (g != null && g > 0.005 ? week + i : null)).filter((w): w is number => w !== null);
  if (!helped.length) return "";
  return (helped.length === 1 ? "week " : "weeks ") + helped.join(", ");
}

/** The card's answer in one sentence (the API's `words.headline`, else 2_Waiver_Wire.py `_headline` here):
 * "Claim A (TE), drop B: +2.9 this week at TE, +6.1 over the next 4 weeks". */
export function waiverHeadline(m: WaiverMove, week = 0, last = 0): string {
  if (m.words?.headline) return m.words.headline;
  const who = `${m.add.player_name} (${m.add.position})`;
  const claim = m.drop ? `Claim ${who}, drop ${m.drop.player_name}` : `Claim ${who}, no drop needed`;
  const wk = m.weekly_gain;
  const hz = m.horizon_gain;
  const sg = (x: number) => `${x >= 0 ? "+" : "−"}${Math.abs(x).toFixed(1)}`;
  if (wk > 0) return `${claim}: ${sg(wk)} this week${m.add_slot ? ` at ${m.add_slot}` : ""}, ${sg(hz)} over ${span(m, week, last)}`;
  const wt = weeksText(m, week);
  const when = wt && Math.abs(wk) < 0.05 ? `, all in ${wt}` : wt ? ` (${wt})` : "";
  const thisWeek = Math.abs(wk) < 0.05 ? "" : `, ${sg(wk)} this week`;
  return `${claim}: ${sg(hz)} over ${span(m, week, last)}${when}${thisWeek}`;
}

/** The screen's first line (markdown): the top claim's sentence, else the API's notice ("Nothing beats what you have."). */
export function waiverAnswer(w: Waivers): string {
  const top = w.cards.find((c) => c.title === "Top claim");
  if (top) return `**${waiverHeadline(top.move, w.week ?? 0, w.horizon_last_week ?? 0)}**`;
  if (w.notice) return w.notice;
  const n = (w.horizon_last_week ?? 0) - (w.week ?? 0) + 1;
  return `**Nothing beats what you have.**  \nNo free agent improves your lineup this week or over the next ${n} weeks (week-${w.week} lineup ${f1(w.lineup_value)}).`;
}

/** "most weeks 9–16" (P25–P75), else "a bad week to a good week 6–19" (P10–P90), else nothing. */
export function rangeWords(p25?: number | null, p75?: number | null, p10?: number | null, p90?: number | null): string | null {
  if (p25 != null && p75 != null) return `most weeks ${Math.round(p25)}–${Math.round(p75)}`;
  if (p10 != null && p90 != null) return `a bad week to a good week ${Math.round(p10)}–${Math.round(p90)}`;
  return null;
}

// ------------------------------------------------------------------ team hub
export function rankText(team: Team, measure: "lineup_value" | "horizon_value" | "bench_value"): string {
  const r = team.ranks?.[measure];
  return r ? `${ordinal(r.league_rank)} of ${r.n_rosters} in the league` : "";
}

/** The answer (markdown): 1_Team_Hub.py's first line as the API quotes it, else written here. */
export function teamAnswer(t: Team): string {
  return t.words?.lineup?.[0] ?? `**Week ${t.value.week}: your best lineup projects ${f1(t.value.lineup_value)}** — ${rankText(t, "lineup_value")}.`;
}

export function closestCall(t: Team): string | null {
  if (t.words?.lineup?.[1]) return t.words.lineup[1];
  const v = t.value;
  if (!v.weakest_slot) return (v.n_locked ?? 0) > 0 ? "Every starter's game has kicked off: no lineup calls left this week." : null;
  if (v.weakest_replacement_name)
    return `Your closest call: **${slotLabel(v.weakest_slot)}, ${v.weakest_player_name} over ${v.weakest_replacement_name} by ${f2(v.weakest_margin)}**.`;
  return `Your closest call: **${slotLabel(v.weakest_slot)}, ${v.weakest_player_name} (${v.weakest_position})**: nobody on the bench can fill in for him (he is worth ${f1(v.weakest_margin)} to the lineup).`;
}

/** "3 of 8 starters came by trade: A, B, C." (Team Hub's acquisition card). */
export function acquiredLine(t: Team): string | null {
  const starters = t.roster.filter((r) => r.role === "starter");
  if (!starters.length) return null;
  if (!starters.some((r) => r.acquired_how)) return null; // an on-demand league: no history to read
  const how = (r: (typeof starters)[number]) => (r.acquired_how === "free_agent" ? "waiver" : (r.acquired_how ?? "unknown"));
  const priority: Record<string, number> = { trade: 0, draft: 1, inherited: 2, waiver: 3, commissioner: 4 };
  const counts = new Map<string, number>();
  for (const r of starters) counts.set(how(r), (counts.get(how(r)) ?? 0) + 1);
  const top = [...counts.entries()].sort((a, b) => b[1] - a[1] || (priority[a[0]] ?? 9) - (priority[b[0]] ?? 9))[0];
  const phrase: Record<string, string> = {
    trade: "came by trade",
    draft: "are your own draft picks",
    waiver: "came off waivers or free agency",
    inherited: "came with the team when it changed hands",
    commissioner: "were placed by the commissioner",
  };
  const names = starters.filter((r) => how(r) === top[0]).map((r) => r.player_name);
  return `**${top[1]} of ${starters.length} starters ${phrase[top[0]] ?? "have no recorded move"}**: ${names.join(", ")}.`;
}

// ------------------------------------------------------------------ league
const nth = (k: number, word: string) => (k === 1 ? `the ${word}` : `the ${ordinal(k)}-${word}`);

/** League page's answer (markdown; 8_League.py's first line as the API quotes it, else written here): your luck and
 * your bench, or the league's luckiest / unluckiest without a team. The bench part needs the manager profiles (house leagues). */
export function luckLine(v: LeagueView, team: number | null): string {
  if (v.words?.headline) return v.words.headline;
  const rows = v.all_play.filter((r) => r.luck_wins != null);
  const bench = new Map((v.profiles ?? []).map((p) => [p.roster_id, p.total_bench_points_left ?? 0]));
  const weeks = `${v.weeks_scored} week${v.weeks_scored === 1 ? "" : "s"}`;
  if (!rows.length) return "No scored weeks yet this season: luck shows up after week 1.";
  const mine = team === null ? undefined : rows.find((r) => r.roster_id === team);
  if (mine) {
    const luck = mine.luck_wins as number;
    let luckTxt: string;
    if (Math.abs(luck) < 0.05) luckTxt = "Your record is exactly what your points deserve";
    else if (luck < 0) luckTxt = `You've been ${nth(rows.filter((r) => (r.luck_wins as number) < luck).length + 1, "unluckiest")} team by schedule (${s1(luck)} wins)`;
    else luckTxt = `You've been ${nth(rows.filter((r) => (r.luck_wins as number) > luck).length + 1, "luckiest")} team by schedule (${s1(luck)} wins)`;
    if (!bench.size) return `**${luckTxt}** (${weeks}).`;
    const b = bench.get(mine.roster_id) ?? 0;
    const kb = [...bench.values()].filter((x) => x > b).length + 1;
    const n = bench.size;
    const where = kb === 1 ? "the most in the league" : kb === n ? "the fewest in the league" : `the ${ordinal(kb)} most of ${n}`;
    return `**${luckTxt}; your bench has left ${Math.round(b)} points unstarted** (${where}, ${weeks}).`;
  }
  const lk = [...rows].sort((a, b) => (b.luck_wins as number) - (a.luck_wins as number));
  return `**Luckiest by schedule: ${lk[0].team_name} (${s1(lk[0].luck_wins)} wins); unluckiest: ${lk[lk.length - 1].team_name} (${s1(lk[lk.length - 1].luck_wins)})**: ${v.season}, ${weeks}.`;
}

export function allPlayRecord(r: AllPlayRow): string {
  return `${Math.round(r.all_play_wins)}-${Math.round(r.all_play_losses)}`;
}

/** A move's kind in plain words ("waiver claim", "free agent", "trade"). */
export function moveKind(type: string): string {
  return ({ waiver: "waiver claim", free_agent: "free agent", trade: "trade", commissioner: "commissioner" } as Record<string, string>)[type] ?? type;
}

/** One player's side of a move: "Add" / "Drop"; in a trade "Gets" / "Gives". */
export function moveWords(type: string, action: string): string {
  if (type === "trade") return action === "add" ? "Gets" : "Gives";
  return action === "add" ? "Add" : action === "drop" ? "Drop" : action;
}

// ------------------------------------------------------------------ trades
export function names(ps: TradePlayer[]): string {
  const n = ps.map((p) => p.player_name ?? "?");
  return n.length <= 1 ? (n[0] ?? "") : `${n.slice(0, -1).join(", ")} and ${n[n.length - 1]}`;
}

/** The partner finder's card: "Your A for their B: you +3.6 this week and +22.1 over weeks 4–7, them +5.6 and +22.0." */
export function partnerLine(p: PartnerRow, span: string): string {
  return (
    `Your ${names(p.give)} for their ${names(p.get)}: you **${s1(p.you_gain_week)}** this week and **${s1(p.you_gain_horizon)}** over ${span}, ` +
    `them **${s1(p.they_gain_week)}** and **${s1(p.they_gain_horizon)}**.`
  );
}

/** Ids in a URL ("8131,11563"): the package is the link (6_Trade_Finder.py). */
export function parseIds(s: string | null): string[] {
  return (s ?? "")
    .split(",")
    .map((x) => x.trim())
    .filter((x) => /^[\w-]+$/.test(x));
}

/** The screens' error line (the Wave F pages' words). */
export function errorWords(e: unknown): string {
  const status = typeof e === "object" && e !== null && "status" in e ? (e as { status: number }).status : null;
  if (status === 404) return "League Lab cannot find this for your league on Sleeper. Pick another league or team above.";
  if (status === 502) return "Sleeper did not answer. Try again in a minute.";
  if (status === 503) return "The numbers are not ready yet. Try again in a few minutes.";
  return e instanceof Error ? e.message : String(e);
}
