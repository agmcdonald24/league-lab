// The decision screens' words (plan G4): the Streamlit pages' sentences, ported where the API does not send them
// (app/pages/2_Waiver_Wire.py `_headline`, 1_Team_Hub.py's cards, 8_League.py's luck line, 6_Trade_Finder.py's
// partner card). Numbers keep their units; unknown is not zero (docs/WORDS.md).
import type { AllPlayRow, LeagueView, PartnerRow, Team, TradePlayer, TradeWindow, WaiverMove, Waivers } from "./api";
import { APP_NAME } from "./brand";

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
// ---- IC-4 (Wave I-D): the team units' slots in words, as cards.slot_label says them ("team QB", "team K")
const UNIT_SLOT: Record<string, string> = { TMQB: "team QB", TMPK: "team K" };
export const slotLabel = (s: string | null | undefined): string => UNIT_SLOT[s ?? ""] ?? (s ?? "").replace("SUPER_FLEX", "Superflex");
// ---- end IC-4

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

/** "typical range 9–16" (P25–P75; IF-4: the dictionary's words, was "most weeks"), else "low-end to high-end 6–19"
 * (P10–P90), else nothing. */
export function rangeWords(p25?: number | null, p75?: number | null, p10?: number | null, p90?: number | null): string | null {
  if (p25 != null && p75 != null) return `typical range ${Math.round(p25)}–${Math.round(p75)}`;
  if (p10 != null && p90 != null) return `low-end to high-end ${Math.round(p10)}–${Math.round(p90)}`;
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

// ---- IE-0 (Wave I-E): asset keys are opaque — "8131", "HOU", "12490", "mfl:0682" (an MFL team QB), "mfl:TMQB-KC". The
// old /^[\w-]+$/ dropped the colon, so the calculator opened the Finder's "Houston Texans QB + Tuten" as Tuten alone.
// A key is anything without a comma or a space, at most 64 characters; blanks and repeats drop, the order is kept.
const KEY = /^[^\s,]{1,64}$/;
export const isAssetKey = (x: string): boolean => KEY.test(x);

/** Ids in a URL ("8131,11563", "mfl:0682,12490"): the package is the link (6_Trade_Finder.py). */
export function parseIds(s: string | null): string[] {
  const out: string[] = [];
  for (const x of (s ?? "").split(",").map((v) => v.trim())) if (isAssetKey(x) && !out.includes(x)) out.push(x);
  return out;
}
// ---- end IE-0

/** The screens' error line (the Wave F pages' words). */
export function errorWords(e: unknown): string {
  const status = typeof e === "object" && e !== null && "status" in e ? (e as { status: number }).status : null;
  if (status === 404) return `${APP_NAME} cannot find this for your league on Sleeper. Pick another league or team above.`;
  if (status === 502) return "Sleeper did not answer. Try again in a minute.";
  if (status === 503) return "The numbers are not ready yet. Try again in a few minutes.";
  return e instanceof Error ? e.message : String(e);
}

// ---- IA-2 (Wave I-A): the window a trade is priced over (api decisions.py WINDOWS / WINDOW_LABELS / WINDOW_WHY)
export const WINDOW_TABS: { key: TradeWindow; label: string }[] = [
  { key: "week", label: "This week" },
  { key: "next4", label: "Next 4" },
  { key: "ros", label: "Rest of season" },
  { key: "playoffs", label: "Playoffs" },
];
const WINDOW_WHY: Record<TradeWindow, string> = {
  week: "this week only: the lineup you set for Sunday",
  next4: "the next four weeks: far enough to matter, near enough to trust",
  ros: "every week left to this league's final, playoffs included: the longest view, the least sure",
  playoffs: "the weeks of this league's playoffs: what the trade does when it counts most",
};

/** The URL's ?window= (anything else: the default, the next four weeks). */
export function windowOf(v: string | null | undefined): TradeWindow {
  return v === "week" || v === "ros" || v === "playoffs" ? v : "next4";
}

/** The window control's one line: "Weeks 4–7: the next four weeks: far enough to matter, near enough to trust." */
export function windowWhy(w: TradeWindow, span: string | null): string {
  const why = WINDOW_WHY[w];
  return span ? `${span[0].toUpperCase()}${span.slice(1)}: ${why}.` : `${why[0].toUpperCase()}${why.slice(1)}.`;
}

/** The dial's label from the other side's gain over the window (api decisions.py `interest`: the same thresholds). */
export function interestLabel(theirGain: number): EffectLabel {
  return effectLabel(theirGain); // IE-1: the effect on their starters (was No deal / Maybe / Likely / Hard to say no)
}
// ---- end IA-2

// ---- IB-2 (Wave I-B): Waivers' views, the partner card's one reason, the research pane behind a guard
import type { Attachment } from "svelte/attachments";
import type { WaiverView } from "./api";

export const VIEW_TABS: { key: WaiverView; label: string }[] = [
  { key: "help", label: "Help now" },
  { key: "bye", label: "Bye coverage" },
  { key: "stash", label: "Stashes" },
  { key: "all", label: "All available" },
];

/** The URL's ?view= (anything else: the answer's default, else Help now). */
export function viewOf(v: string | null | undefined, fallback: WaiverView = "help"): WaiverView {
  return v === "help" || v === "bye" || v === "stash" || v === "all" ? v : fallback;
}

/** A partner suggestion's one reason (a fact, not the paragraph): when the gain comes, or who cannot play. */
export function partnerReason(p: PartnerRow, span: string): string {
  const out = p.get.find((x) => x.cannot_play);
  if (out) return `${out.player_name} cannot play this week (${String(out.cannot_play).toLowerCase()}): the gain comes after it.`;
  const starter = p.get.slice().sort((a, b) => (b.this_week ?? 0) - (a.this_week ?? 0))[0];
  if (p.you_gain_week >= 0.05 && starter) return `${starter.player_name} starts for you this week: ${s1(p.you_gain_week)} now, ${s1(p.you_gain_horizon)} over ${span}.`;
  if (p.you_gain_horizon >= 0.05) return `Nothing changes this week; your lineup gains ${s1(p.you_gain_horizon)} over ${span}.`;
  return `Your lineup does not gain over ${span}: they do (${s1(p.they_gain_horizon)}).`;
}

// The research pane (IB-1's PlayerPane, web/src/lib/pane.svelte.ts, PANE_API.md). Behind a guard so this branch builds
// without it: an eager glob is a static import when the file exists and {} when it does not. Without the pane a name
// link stays a plain link to the full page (its href), and `openPlayer` goes to the full page.
type PaneFrom = "lineup" | "waiver" | "trade" | "search" | "list";
interface PaneOpts {
  from?: PaneFrom;
  context?: { name?: string | null; add?: string | null; drop?: string | null; sleeper_id?: string | null; side?: "give" | "get"; partner?: number | null };
}
interface PaneModule {
  openPane?: (gsis: string, opts?: PaneOpts) => void;
  paneLink?: (gsis: string | null | undefined, opts?: PaneOpts) => Attachment;
}
const paneModules = import.meta.glob<PaneModule>("./pane.svelte.ts", { eager: true });
const pane: PaneModule | undefined = Object.values(paneModules)[0];

/** True when the research pane is in the build (IB-1). */
export const hasPane = (): boolean => typeof pane?.openPane === "function";

/** The pane on a name link (`{@attach paneAt(gsis, {...})}`): a tap opens the pane, the href stays real. */
export function paneAt(gsis: string | null | undefined, opts: PaneOpts): Attachment {
  if (gsis && pane?.paneLink) return pane.paneLink(gsis, opts);
  return () => {};
}

/** A whole-row tap: the pane when it is in the build, else the full page through `go` (the router's navigate). */
export function openPlayer(gsis: string | null | undefined, opts: PaneOpts, go: () => void): void {
  if (gsis && pane?.openPane) pane.openPane(gsis, opts);
  else go();
}
// ---- end IB-2

// ---- IE-1 (Wave I-E, the casual-user review § "replace the interest dial"): the dial is the effect on their starters —
// the partner's best-lineup gain over the window (api decisions.py `effect_label`: the same thresholds) — in outcome
// words, never an acceptance claim. The tone: weaker = bad, about even = neutral, improves = good.
import type { EffectLabel } from "./api";
export const EFFECT_TITLE = "Effect on their starters";
export function effectLabel(g: number): EffectLabel {
  return g < -0.05 ? "Makes their lineup weaker" : g < 2 ? "About even" : g <= 6 ? "Improves their lineup" : "Improves it a lot";
}
export function effectTone(label: string): "text-bad" | "text-ink-2" | "text-good" {
  return label === "Makes their lineup weaker" || label === "No deal" ? "text-bad" : label === "About even" || label === "Maybe" ? "text-ink-2" : "text-good";
}
// ---- end IE-1
