// ---- II-2 (Wave I-I, the fifth review § 3 "Use one shared player viewer everywhere"): the player drawer — THE player
// inspection component. Every player link on a league screen opens it (a lineup row, a waiver candidate, a receiver,
// a Team / Season row, a trade player, a matchup reference, a search hit, a name inside a sentence); the screen under
// it keeps its search, filters, sort, page, selection and scroll. The markup is components/PlayerPane.svelte (mounted
// once by App.svelte); IB-1's lib/pane.svelte.ts keeps its exports and delegates here.
//
// * URL: `?pane=<key>&from=<from>` on the screen's own path (IB-1's keys). The first open pushes ONE history entry
//   (browser Back closes the drawer before it leaves the screen); opening another player swaps in place.
// * Focus: the drawer takes focus on open (its title); closing it (×, Escape, Back, Full page excepted) returns focus to
//   the control that opened it.
// * Sections: Overview · Usage · Game log · News (the choice sticks while players are swapped); "Expand" opens all of
//   them in a modal lightbox (<dialog>, Escape collapses it back to the drawer).
// * Cache: the card by player + league + team + season + data version (/api/status `updated_at`); a slower, older
//   response never overwrites a newer selection (a request token).
// * Analytics: `onPlayerOpen(fn)` — INF-1's `select_content` hook (ids only, never names).
// * Every `<a href="/player/<key>…">` is caught by the router's link hook (lib/router.svelte.ts `setLinkHook`): a route
//   needs no change for its names to open the drawer; `playerLink(key, opts)` adds a context (IB-1's actions) or a
//   name that is not an `<a>` to a player page. `data-full-page` on a link keeps it a page link.
import type { Attachment } from "svelte/attachments";
import { get, forget, paths, peek, type PlayerCard, type Status } from "./api";
import { withContext, type LinkContext } from "./md";
import type { PaneContext, PaneFrom } from "./pane.svelte";
import { navigate, route, setLinkHook, setParams, setPopHook } from "./router.svelte";
import { track } from "./analytics"; // INF-1

export type DrawerSection = "overview" | "usage" | "gamelog" | "news";
export const DRAWER_SECTIONS: { key: DrawerSection; label: string }[] = [
  { key: "overview", label: "Overview" },
  { key: "usage", label: "Usage" },
  { key: "gamelog", label: "Game log" },
  { key: "news", label: "News" },
];
const FROM: PaneFrom[] = ["lineup", "waiver", "trade", "search", "list"];

export interface OpenPlayerOptions {
  /** Where it was opened (analytics; default: the screen on screen — "players", "waivers", "receivers", "team", …). */
  origin?: string;
  /** IB-1's action context (`lineup` → Compare with my starter, `waiver` → Evaluate add / drop, `trade` → Add to trade). */
  from?: PaneFrom;
  context?: PaneContext;
  /** The control focus returns to on close (default: the focused element, or the link tapped). */
  returnFocus?: HTMLElement | null;
}

/** What INF-1's `select_content` receives: ids only. */
export interface PlayerOpenEvent {
  content_type: "player";
  item_id: string;
  origin: string;
  league_key: string | null;
  roster_id: number | null;
}

// the context of the drawer on screen, keyed by key + from (a swap back finds it again); in memory only: after a
// reload only "Full player page" and "Add to compare" are offered, never a dead button
const memo = $state<{ key: string; context: PaneContext; origin: string }>({ key: "", context: {}, origin: "" });
const ui = $state<{ expanded: boolean; section: DrawerSection; mounted: boolean }>({ expanded: false, section: "overview", mounted: false });
let returnTo: HTMLElement | null = null;

/** The drawer on screen (from the URL) and its in-memory state. */
export const drawer = {
  get key(): string | null {
    return route.current.name === "player" ? null : route.current.params.get("pane");
  },
  get from(): PaneFrom {
    const f = route.current.params.get("from") as PaneFrom | null;
    return f && FROM.includes(f) ? f : "list";
  },
  get context(): PaneContext {
    return memo.key === `${this.key}|${this.from}` ? memo.context : {};
  },
  get origin(): string {
    return memo.key === `${this.key}|${this.from}` ? memo.origin : "link";
  },
  get expanded(): boolean {
    return ui.expanded;
  },
  get section(): DrawerSection {
    return ui.section;
  },
};

/** PlayerPane says it is on screen (the link hook only acts where the drawer can open). */
export function drawerMounted(on: boolean): void {
  ui.mounted = on;
}

export function setSection(s: DrawerSection): void {
  ui.section = s;
}

export function setExpanded(on: boolean): void {
  ui.expanded = on;
}

const inDrawer = (el: Element | null | undefined) => !!el?.closest?.("[data-drawer]");

// ---- the analytics hook (INF-1)
// eslint-disable-next-line svelte/prefer-svelte-reactivity -- a list of callbacks, never observed
const listeners = new Set<(e: PlayerOpenEvent) => void>();

/** Subscribe to drawer opens (and swaps): INF-1 sends GA4 `select_content`. Returns the unsubscribe. */
export function onPlayerOpen(fn: (e: PlayerOpenEvent) => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

function emit(key: string, origin: string): void {
  const p = route.current.params;
  const t = p.get("team");
  const e: PlayerOpenEvent = { content_type: "player", item_id: key, origin, league_key: p.get("league"), roster_id: t && /^\d+$/.test(t) ? Number(t) : null };
  for (const fn of listeners) {
    try {
      fn(e);
    } catch {
      // an analytics listener never breaks the drawer
    }
  }
}

/** Open the drawer on player `key` (a gsis id, or a team unit's key such as "DET"). An open drawer is swapped in place
 *  (no extra Back step); the first open is a new history entry on the same screen (Back closes it, the screen does
 *  not scroll). */
export function openPlayer(key: string | null | undefined, opts: OpenPlayerOptions = {}): void {
  if (!key) return;
  const from = opts.from ?? "list";
  // eslint-disable-next-line svelte/prefer-svelte-reactivity -- a scratch copy of the query string
  const qs = new URLSearchParams(location.search);
  const open = qs.get("pane");
  const active = (opts.returnFocus ?? (typeof document !== "undefined" ? document.activeElement : null)) as HTMLElement | null;
  const fromInside = inDrawer(active);
  // a link inside the drawer swaps the player: focus still returns to what opened the drawer in the first place
  if (!fromInside) returnTo = active && active !== document.body ? active : open ? returnTo : null;
  const origin = opts.origin ?? (fromInside ? "drawer" : route.current.name);
  memo.key = `${key}|${from}`;
  memo.context = opts.context ?? {};
  memo.origin = origin;
  if (open === key && (qs.get("from") ?? "list") === from) return; // already on screen: nothing to count
  emit(key, origin);
  track("select_content", { content_type: "player", item_id: key, origin, from }); // INF-1: counted once (the URL's pane= path dedupes)
  if (open) {
    setParams({ pane: key, from });
    return;
  }
  ui.expanded = false;
  qs.set("pane", key);
  qs.set("from", from);
  navigate(`${location.pathname}?${qs.toString()}`, { keepScroll: true, state: { pane: true } });
}

/** Close the drawer: Back when the drawer added the history entry, else drop it from the URL in place. (II-6: the Back
 *  keeps what the screen wrote to the URL while the drawer was open — `screenUnderDrawer` below.) */
export function closePlayer(): void {
  ui.expanded = false;
  if (!route.current.params.get("pane")) return;
  if (history.state?.pane === true) history.back();
  else setParams({ pane: null, from: null });
}

/** Focus back to the control that opened the drawer (called once the drawer has left the screen). It never scrolls:
 *  the screen stays where the manager left it. A control that is gone (the list re-rendered) → the screen's <main>. */
export function restoreFocus(): void {
  const el = returnTo;
  returnTo = null;
  if (route.current.name === "player") return; // "Full player page": a new page, its own focus
  const target = el?.isConnected ? el : (document.querySelector("main") as HTMLElement | null);
  if (!target) return;
  if (target.tagName === "MAIN" && !target.hasAttribute("tabindex")) target.setAttribute("tabindex", "-1");
  target.focus({ preventScroll: true });
}

/** "Full player page": the player's own page in place of the drawer's entry, so Back lands on the screen without the
 *  drawer. League and team ride along. */
export function openFullPage(key: string, ctx: LinkContext): void {
  ui.expanded = false;
  returnTo = null;
  const href = withContext(`/player/${encodeURIComponent(key)}`, ctx);
  if (history.state?.pane === true) navigate(href, { replace: true, top: true, state: { pane: false } });
  else navigate(href);
}

/** For a name that is a link (`<a href="/player/<key>…">`): a plain tap opens the drawer with this context; Cmd / Ctrl /
 *  middle click still opens the full page. No key → nothing changes (a plain link). */
export function playerLink(key: string | null | undefined, opts: OpenPlayerOptions = {}): Attachment<HTMLElement> {
  return (el) => {
    if (!key) return;
    el.dataset.playerLink = key;
    const onClick = (e: MouseEvent) => {
      if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      e.preventDefault(); // the app's link handler (router.interceptLinks) then leaves it alone
      openPlayer(key, { ...opts, returnFocus: opts.returnFocus ?? el });
    };
    el.addEventListener("click", onClick);
    return () => {
      el.removeEventListener("click", onClick);
      delete el.dataset.playerLink;
    };
  };
}

// ---- every other player link: the router's link hook (a plain tap on `<a href="/player/<key>…">`)
const PLAYER_HREF = /^\/player\/([^/?#]+)/;
function hook(href: string, a: HTMLAnchorElement): boolean {
  if (!ui.mounted || route.current.name === "player" || a.hasAttribute("data-full-page")) return false;
  const m = href.match(PLAYER_HREF);
  if (!m) return false;
  const key = decodeURIComponent(m[1]);
  openPlayer(key, { returnFocus: a, context: { name: a.textContent?.trim() || null } });
  return true;
}
setLinkHook(hook);

// ---- II-6 (Wave I-J): a Back that closes the drawer (×, Escape, the browser's Back) lands on the entry before the
// first open. A parameter the screen wrote while the drawer was open — a search typed < 250 ms before the tap (its
// debounce lands after the open), a filter or sort changed beside the drawer from 900 px — is on the drawer's entry
// only, so the landed entry is rewritten to the screen as it is now, minus `pane` / `from`, before the screen renders
// it: one history entry per screen, Back still closes the drawer first, nothing typed is lost.
export function screenUnderDrawer(left: string, landed: string): string | null {
  // eslint-disable-next-line svelte/prefer-svelte-reactivity -- scratch copies of two URLs, never observed
  const a = new URL(left, "http://x");
  // eslint-disable-next-line svelte/prefer-svelte-reactivity -- the same
  const b = new URL(landed, "http://x");
  if (a.pathname !== b.pathname || !a.searchParams.has("pane") || b.searchParams.has("pane")) return null;
  a.searchParams.delete("pane");
  a.searchParams.delete("from");
  const screen = a.pathname + a.search;
  return screen !== b.pathname + b.search ? screen : null;
}
setPopHook(screenUnderDrawer);
// ---- end II-6

// ---- the card: cached by player + league + team (the path) + data version; the league key carries the scoring and
// the season (the API serves one season per league key; a new season is a new data build). A request token guards
// against a slower, older answer.
interface Entry {
  at: number;
  season: number | null;
  card: PlayerCard;
}
const TTL_MS = 5 * 60_000; // injuries and news move during the day without a new data build
const MAX = 80;
// eslint-disable-next-line svelte/prefer-svelte-reactivity -- a plain lookup, never observed
const cache = new Map<string, Entry>();
let version = "";

function dataVersion(): string {
  const v = peek<Status>(paths.status())?.updated_at ?? "";
  if (v && v !== version) {
    // a new data build: every card read before it is out of date (and so is the API module's copy of it)
    for (const k of cache.keys()) forget(k.slice(0, k.lastIndexOf("#")));
    cache.clear();
    version = v;
  }
  return version;
}

/** The cache key: the card's path (player + league + team) # the data version. */
export function cardKey(key: string, league: string, team: number | null): string {
  return `${paths.player(key, league, team)}#${dataVersion()}`;
}

/** The card if it is cached and fresh (renders synchronously on a swap back). */
export function cachedCard(key: string, league: string, team: number | null): PlayerCard | undefined {
  const hit = cache.get(cardKey(key, league, team));
  return hit && Date.now() - hit.at <= TTL_MS ? hit.card : undefined;
}

let token = 0;

/** Load a card for the drawer. Resolves `null` when a newer selection was made meanwhile: the caller ignores it, so an
 *  older, slower answer never overwrites the player on screen. */
export async function loadCard(key: string, league: string, team: number | null): Promise<PlayerCard | null> {
  const mine = ++token;
  const k = cardKey(key, league, team);
  const hit = cachedCard(key, league, team);
  if (hit) return hit;
  const card = await get<PlayerCard>(paths.player(key, league, team));
  cache.delete(k);
  cache.set(k, { at: Date.now(), season: card.season ?? null, card });
  while (cache.size > MAX) cache.delete(cache.keys().next().value as string);
  return mine === token ? card : null;
}

// ---- add to compare: a pair, kept for this tab and this league; the second pick opens Compare with both
export interface CompareItem {
  key: string;
  name: string;
}
function readTray(): { league: string; items: CompareItem[] } {
  try {
    const raw = sessionStorage.getItem("ll.drawer.compare");
    const v = raw ? JSON.parse(raw) : null;
    if (v && typeof v.league === "string" && Array.isArray(v.items)) return v;
  } catch {
    // private mode / no storage: the tray lives in memory only
  }
  return { league: "", items: [] };
}
const tray = $state(readTray());
function saveTray(): void {
  try {
    sessionStorage.setItem("ll.drawer.compare", JSON.stringify(tray));
  } catch {
    // in memory only
  }
}

/** The players waiting to be compared in this league (at most one: Compare is a pair). */
export function compareTray(league: string | null): CompareItem[] {
  return tray.league === league ? tray.items : [];
}

/** "Add to compare": the first pick waits in the tray (the screen stays); the second opens Compare with both. */
export function addToCompare(key: string, name: string, ctx: LinkContext): "waiting" | "opened" {
  const league = String(ctx.league ?? "");
  if (tray.league !== league) {
    tray.league = league;
    tray.items = [];
  }
  const other = tray.items.find((x) => x.key !== key);
  if (!other) {
    tray.items = [{ key, name }];
    saveTray();
    return "waiting";
  }
  tray.items = [];
  saveTray();
  ui.expanded = false;
  returnTo = null;
  const href = withContext(`/compare?a=${encodeURIComponent(other.key)}&b=${encodeURIComponent(key)}`, ctx);
  if (history.state?.pane === true) navigate(href, { replace: true, top: true, state: { pane: false } });
  else navigate(href);
  return "opened";
}

/** Take a player out of the tray. */
export function removeFromCompare(key: string): void {
  tray.items = tray.items.filter((x) => x.key !== key);
  saveTray();
}
// ---- end II-2
