// The decision screens (plan G4) load on first use, each in its own chunk: the first screen (My Week) stays as small
// as Wave F measured it. The promise is kept, so a second visit renders at once (no loading flash).
import type { Component } from "svelte";
import type { LeagueOption } from "./leagues";

export type DecisionRoute = "waivers" | "trades" | "team" | "league" | "trade-calc";
type Page = Component<{ options: LeagueOption[]; league: string; team: number | null; onauth: () => void }>;

const loaders: Record<DecisionRoute, () => Promise<{ default: Page }>> = {
  waivers: () => import("../routes/Waivers.svelte"),
  trades: () => import("../routes/Trades.svelte"),
  team: () => import("../routes/Team.svelte"),
  league: () => import("../routes/League.svelte"),
  "trade-calc": () => import("../routes/decisions/TradeCalc.svelte"), // ---- IA-2: the trade calculator
};
const loaded = new Map<DecisionRoute, Promise<Page>>();

export const isDecision = (name: string): name is DecisionRoute => name in loaders;

export function decisionPage(name: DecisionRoute): Promise<Page> {
  let p = loaded.get(name);
  if (!p) {
    p = loaders[name]().then((m) => m.default);
    loaded.set(name, p);
  }
  return p;
}
