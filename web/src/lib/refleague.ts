// ---- IM-3 (Wave I-M): browse the lab without a league. `ref:ppr` / `ref:half` / `ref:std` are the API's reference league
// keys (api/league_lab_api/refleague.py): the NFL-wide research priced in that scoring, no rosters. The research screens
// (Players: Stats · Trends · Matchups · Compare, a player's page and drawer, About, DFS) work with one; the decision
// screens (My Team, Waivers) show the invitation card instead. A reference key is never a "remembered league"
// (lib/prefs.ts never stores one as the league) and travels in the URL (`?league=ref:half`).
// ---- IN-2 (Wave I-N): the key is a small closed family — `ref:<scoring>[.sf][.tep][.p6][.t8|.t10|.t14]` (the API's
// `platforms.parse_reference`, the same grammar): five scorings (PPR, Half PPR, Standard, ESPN default, Yahoo default),
// superflex, TE premium, 6-pt passing touchdowns, 8 / 10 / 12 / 14 teams — 160 keys. The picker's choice is remembered
// per viewer (`prefs.refKey`) and travels in the URL. The Trades tab opens the calculator (never the invitation card).
import type { RouteName } from "./router.svelte";
import { prefs } from "./prefs";

export type RefBase = "ppr" | "half" | "std" | "espn" | "yahoo";
export type RefTeams = 8 | 10 | 12 | 14;
export interface RefShape {
  base: RefBase;
  sf: boolean;
  tep: boolean;
  p6: boolean;
  teams: RefTeams;
}

export const REF_BASES: { id: RefBase; label: string; rules: string }[] = [
  { id: "ppr", label: "PPR", rules: "1 point per catch, 4 per passing touchdown, −1 per interception." },
  { id: "half", label: "Half PPR", rules: "Half a point per catch, 4 per passing touchdown, −1 per interception." },
  { id: "std", label: "Standard", rules: "No points for a catch, 4 per passing touchdown, −1 per interception." },
  { id: "espn", label: "ESPN default", rules: "ESPN's default: 1 point per catch, 4 per passing touchdown, −2 per interception." },
  { id: "yahoo", label: "Yahoo default", rules: "Yahoo's default: half a point per catch, 4 per passing touchdown, −1 per interception (the same points as Half PPR)." },
];
export const REF_OPTIONS: { id: "sf" | "tep" | "p6"; label: string; help: string }[] = [
  { id: "sf", label: "Superflex", help: "A second spot a quarterback can fill" },
  { id: "tep", label: "TE premium", help: "+0.5 per tight-end catch" },
  { id: "p6", label: "6-pt pass TD", help: "6 points per passing touchdown instead of 4" },
];
export const REF_TEAMS: RefTeams[] = [8, 10, 12, 14];
export const REF_TEAMS_DEFAULT: RefTeams = 12;
export const SLEEPER_WORDS = "Sleeper has no single default: a Sleeper league picks PPR, Half PPR or Standard when it is made.";
const OPTION_WORDS = { sf: "superflex", tep: "TE premium", p6: "6-pt pass TD" } as const;
const KEY_RE = /^ref:(ppr|half|std|espn|yahoo)(\.sf)?(\.tep)?(\.p6)?(?:\.t(8|10|14))?$/;

/** The canonical key of a shape (the API's `platforms.ref_key`). */
export function refKey(s: RefShape): string {
  return `ref:${s.base}${s.sf ? ".sf" : ""}${s.tep ? ".tep" : ""}${s.p6 ? ".p6" : ""}${s.teams === REF_TEAMS_DEFAULT ? "" : `.t${s.teams}`}`;
}

/** The shape of a canonical key (case aside), else null: strict, the API's grammar. */
export function parseRef(league: string | null | undefined): RefShape | null {
  const k = (league ?? "").trim().toLowerCase();
  const m = KEY_RE.exec(k);
  if (!m) return null;
  return { base: m[1] as RefBase, sf: !!m[2], tep: !!m[3], p6: !!m[4], teams: (m[5] ? Number(m[5]) : REF_TEAMS_DEFAULT) as RefTeams };
}

/** Every key of the family (160). */
export const REF_KEYS: string[] = REF_BASES.flatMap((b) =>
  [false, true].flatMap((sf) => [false, true].flatMap((tep) => [false, true].flatMap((p6) => REF_TEAMS.map((teams) => refKey({ base: b.id, sf, tep, p6, teams }))))),
);
export type RefKey = string;
export const REF_DEFAULT = "ref:half";
/** IM-3's three keys in words (kept for older readers). */
export const REF_LABEL: Record<string, string> = { "ref:ppr": "PPR", "ref:half": "Half PPR", "ref:std": "Standard" };

export const isRef = (league: string | null | undefined): boolean => !!league && league.trim().toLowerCase().startsWith("ref:");

const baseLabel = (b: RefBase) => REF_BASES.find((x) => x.id === b)?.label ?? "Half PPR";

/** The scoring alone ("Half PPR · TE premium"): what a number is priced in. */
export function refScoringLabel(league: string | null | undefined): string {
  const s = parseRef(league) ?? parseRef(REF_DEFAULT)!;
  return [baseLabel(s.base), ...(s.tep ? [OPTION_WORDS.tep] : []), ...(s.p6 ? [OPTION_WORDS.p6] : [])].join(" · ");
}

/** The key in words, as the API's `refleague.label`: "Half PPR", "PPR · superflex · 10 teams". */
export const refLabel = (league: string | null | undefined): string => {
  const s = parseRef(league) ?? parseRef(REF_DEFAULT)!;
  const bits: string[] = [baseLabel(s.base)];
  if (s.sf) bits.push(OPTION_WORDS.sf);
  if (s.tep) bits.push(OPTION_WORDS.tep);
  if (s.p6) bits.push(OPTION_WORDS.p6);
  if (s.teams !== REF_TEAMS_DEFAULT) bits.push(`${s.teams} teams`);
  return bits.join(" · ");
};

/** The short form for a phone's bar: "Half PPR", "PPR +2" (the options and the size, counted). */
export function refShort(league: string | null | undefined): string {
  const s = parseRef(league) ?? parseRef(REF_DEFAULT)!;
  const n = (s.sf ? 1 : 0) + (s.tep ? 1 : 0) + (s.p6 ? 1 : 0) + (s.teams !== REF_TEAMS_DEFAULT ? 1 : 0);
  return n ? `${baseLabel(s.base)} +${n}` : baseLabel(s.base);
}

/** "Value in a 12-team Half PPR league, one quarterback" (the API's `Shape.assumes`). */
export function refAssumes(league: string | null | undefined): string {
  const s = parseRef(league) ?? parseRef(REF_DEFAULT)!;
  return `Value in ${s.teams === 8 ? "an" : "a"} ${s.teams}-team ${refScoringLabel(league)} league, ${s.sf ? "two quarterbacks (superflex)" : "one quarterback"}`;
}

/** The key this viewer picked last (remembered on the device), else Half PPR. */
export function refPreferred(): string {
  const k = prefs.refKey();
  return k && parseRef(k) ? refKey(parseRef(k)!) : REF_DEFAULT;
}

/** The screens that need a league and a team: with a reference key they show the invitation card. IN-2: not Trades —
 *  the Trades tab opens the calculator without a league. */
export const NEEDS_LEAGUE: ReadonlySet<RouteName> = new Set<RouteName>(["week", "team", "league", "waivers", "watchlist"]);

/** Where "Browse the lab" goes: Players · Stats in the viewer's scoring (Half PPR at first). */
export const BROWSE_HREF = `/players?league=${refPreferred()}`;
export const INVITE_WORDS = "Open your league to see your lineup, waivers and trades.";
/** The one quiet line at the foot of a player's pane and page while browsing. */
export const PANE_FOOT = "Open your league to see who has him and what he is worth to your team.";
/** What a league would add to the calculator. */
export const CALC_FOOT = "Open your league to see what this does to your lineup.";
