// IB-1 (Wave I-B): the research pane — a player's card beside the list (from 900 px) or as a sheet over the screen
// (a phone), opened from any player name: a lineup row, a waiver candidate, a trade list row, a search result, a
// research list. The contract other screens call is in this file; the markup is components/PlayerPane.svelte, mounted
// once by App.svelte. The open pane is in the URL (`?pane=<gsis>&from=<from>`): a phone's Back closes the sheet, a
// shared link opens it. The context (what the actions need) lives in memory only: after a reload only "Full page"
// is offered, never a dead button.
import type { Attachment } from "svelte/attachments";
import { withContext, type LinkContext } from "./md";
import { route } from "./router.svelte";
import { closePlayer, drawer, openFullPage as drawerFullPage, openPlayer, playerLink } from "./player-drawer.svelte"; // ---- II-2

export type PaneFrom = "lineup" | "waiver" | "trade" | "search" | "list";

export interface PaneContext {
  name?: string | null; // his name while his card loads
  // from "lineup": the player to compare him with (the slot's starter; for a starter, the best bench option)
  slot?: string | null;
  starter?: string | null; // gsis_id
  starterName?: string | null;
  // from "waiver": the claim (Waivers' moves are keyed by sleeper id)
  add?: string | null;
  drop?: string | null;
  // from "trade": the calculator's give= / get= (sleeper ids) and the partner's roster id
  sleeper_id?: string | null;
  side?: "give" | "get";
  partner?: number | null;
}

export interface PaneOptions {
  from?: PaneFrom;
  context?: PaneContext;
}

export interface PaneAction {
  key: "compare" | "waiver" | "trade";
  label: string;
  href: string;
}

// ---- II-2 (Wave I-I): the pane is the player drawer now — its state, open / close, focus, cache and the link hook are
// lib/player-drawer.svelte.ts; these names stay for the screens and components that call them.
/** The pane on screen: from the URL. */
export const pane = {
  get gsis(): string | null {
    return drawer.key;
  },
  get from(): PaneFrom {
    return drawer.from;
  },
  get context(): PaneContext {
    return drawer.context;
  },
};

/** Open the pane on player `gsis` (the drawer: `openPlayer`). */
export function openPane(gsis: string, opts: PaneOptions = {}): void {
  openPlayer(gsis, opts);
}

/** Close the pane (the drawer: `closePlayer`). */
export function closePane(): void {
  closePlayer();
}

/** "Full page": the player's own page in place of the pane's entry, so Back lands on the screen without the pane. */
export function openFullPage(gsis: string, ctx: LinkContext): void {
  drawerFullPage(gsis, ctx);
}
// ---- end II-2

/** The actions for where the pane was opened from (always followed by "Full page" in the pane). Missing context →
 *  no action. */
export function paneActions(gsis: string, from: PaneFrom, c: PaneContext, ctx: LinkContext): PaneAction[] {
  const out: PaneAction[] = [];
  if (from === "lineup" && c.starter && c.starter !== gsis) {
    const label = c.slot === "bench" || !c.slot ? "Compare with my starter" : "Compare with my best bench option";
    out.push({ key: "compare", label, href: withContext(`/compare?a=${enc(gsis)}&b=${enc(c.starter)}`, ctx) });
  }
  if (from === "waiver" && c.add) {
    const drop = c.drop ? `&drop=${enc(c.drop)}` : "";
    out.push({ key: "waiver", label: "Evaluate add / drop", href: withContext(`/waivers?add=${enc(c.add)}${drop}`, ctx) });
  }
  if (from === "trade" && c.sleeper_id && c.side && (c.side === "give" || c.partner !== null && c.partner !== undefined)) {
    out.push({ key: "trade", label: "Add to trade", href: withContext(tradeHref(c), ctx) });
  }
  return out;
}

const enc = encodeURIComponent;
const ids = (v: string | null) => (v ?? "").split(",").filter(Boolean);

// the calculator with him ticked: added to the package on screen when the calculator is open with the same partner
function tradeHref(c: PaneContext): string {
  const here = route.current;
  const onCalc = here.name === "trade-calc";
  const partner = c.side === "get" ? String(c.partner) : (here.params.get("partner") ?? null);
  const samePartner = onCalc && (c.side === "give" || here.params.get("partner") === partner);
  const give = samePartner ? ids(here.params.get("give")) : [];
  const get = samePartner ? ids(here.params.get("get")) : [];
  const list = c.side === "give" ? give : get;
  if (!list.includes(c.sleeper_id!)) list.push(c.sleeper_id!);
  const q: string[] = [];
  if (partner) q.push(`partner=${enc(partner)}`);
  if (give.length) q.push(`give=${give.map(enc).join(",")}`);
  if (get.length) q.push(`get=${get.map(enc).join(",")}`);
  const win = onCalc ? here.params.get("window") : null;
  if (win) q.push(`window=${enc(win)}`);
  return `/trade-calc?${q.join("&")}`;
}

/** For a name that is a link (`<a href="/player/<gsis>…">`): a plain tap opens the pane instead; Cmd / Ctrl /
 *  middle click still opens the full page. No gsis → nothing changes. (II-2: the drawer's `playerLink`.) */
export function paneLink(gsis: string | null | undefined, opts: PaneOptions = {}): Attachment<HTMLElement> {
  return playerLink(gsis, opts);
}

// ---- My Week's lineup rows: who to compare him with
const ELIGIBLE: Record<string, string[]> = {
  QB: ["QB"],
  RB: ["RB"],
  WR: ["WR"],
  TE: ["TE"],
  K: ["K"],
  DEF: ["DEF"],
  FLEX: ["RB", "WR", "TE"],
  SUPERFLEX: ["QB", "RB", "WR", "TE"],
};
const slotKind = (slot: string) => slot.toUpperCase().replace(/[\s_-]/g, "").replace(/\d+$/, "");

interface LineupLike {
  role?: string | null;
  slot: string;
  gsis_id?: string | null;
  player_name?: string | null;
  position?: string | null;
  value?: number | null;
}

/** The pane's options for a lineup row: a bench player is compared with the weakest starter he could replace (his
 *  position's slots and the flex ones), a starter with the best bench player who can fill his slot. `rows` = the
 *  whole roster (My Week's `lineup_full`). */
export function lineupPane(r: LineupLike, rows: LineupLike[]): PaneOptions {
  const name = r.player_name ?? null;
  const v = (x: LineupLike) => x.value ?? -Infinity;
  if (r.role === "starter") {
    const ok = ELIGIBLE[slotKind(r.slot)] ?? [r.position ?? ""];
    const alt = rows.filter((x) => x.role === "bench" && x.gsis_id && ok.includes(x.position ?? "")).sort((a, b) => v(b) - v(a))[0];
    return { from: "lineup", context: { name, slot: r.slot, starter: alt?.gsis_id ?? null, starterName: alt?.player_name ?? null } };
  }
  const pos = r.position ?? "";
  const slots = rows.filter((x) => x.role === "starter" && x.gsis_id && (ELIGIBLE[slotKind(x.slot)] ?? []).includes(pos));
  const weakest = slots.sort((a, b) => v(a) - v(b))[0];
  return { from: "lineup", context: { name, slot: "bench", starter: weakest?.gsis_id ?? null, starterName: weakest?.player_name ?? null } };
}
