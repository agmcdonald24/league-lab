// ---- IM-3 (Wave I-M): browse the lab without a league. `ref:ppr` / `ref:half` / `ref:std` are the API's reference league
// keys (api/league_lab_api/refleague.py): the NFL-wide research priced in that scoring, no rosters. The research screens
// (Players: Stats · Trends · Matchups · Compare, a player's page and drawer, About, DFS) work with one; the decision
// screens (My Team, Waivers, Trades) show the invitation card instead. A reference key is never a "remembered league"
// (lib/prefs.ts never stores one) and travels in the URL (`?league=ref:half`).
import type { RouteName } from "./router.svelte";

export const REF_KEYS = ["ref:ppr", "ref:half", "ref:std"] as const;
export type RefKey = (typeof REF_KEYS)[number];
export const REF_DEFAULT: RefKey = "ref:half";
export const REF_LABEL: Record<RefKey, string> = { "ref:ppr": "PPR", "ref:half": "Half PPR", "ref:std": "Standard" };

export const isRef = (league: string | null | undefined): boolean => !!league && league.trim().toLowerCase().startsWith("ref:");
export const refLabel = (league: string | null | undefined): string =>
  REF_LABEL[(league ?? "").trim().toLowerCase() as RefKey] ?? REF_LABEL[REF_DEFAULT];

/** The screens that need a league and a team: with a reference key they show the invitation card. */
export const NEEDS_LEAGUE: ReadonlySet<RouteName> = new Set<RouteName>(["week", "team", "league", "waivers", "trades", "trade-calc", "watchlist"]);

/** Where "Browse the lab" goes: Players · Stats on Half PPR. */
export const BROWSE_HREF = `/players?league=${REF_DEFAULT}`;
export const INVITE_WORDS = "Open your league to see your lineup, waivers and trades.";
