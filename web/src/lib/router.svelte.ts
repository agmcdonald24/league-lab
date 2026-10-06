// A small router on the History API: "/" (My Week, or the sign-in when no league is known), "/leagues" (sign in with a
// Sleeper username, pick a league), "/player/<gsis>", "/ros" (rest of season), "/about" (about the numbers + the
// record; "/record" still opens it), the research screens ("/trends", "/matchups", "/players", "/receivers",
// "/compare") and the decisions screens ("/waivers", "/trades", "/team", "/league"; Wave G, G4).
// IB-1 (Wave I-B): the paths stay; the tab bar groups them by task (components/TopBar.svelte: My Team · Waivers ·
// Trades · Players). The research pane is a query parameter on any screen (`?pane=<gsis>&from=…`, lib/pane.svelte.ts).
// * A tap on a same-site link is handled here (no reload, same session, one history entry).
// * Changing the league or team rewrites the URL in place (replace), so Back goes to the previous PAGE.
// * Each history entry remembers its scroll position; Back restores it.

export type RouteName =
  | "week"
  | "player"
  | "leagues"
  | "ros"
  | "about"
  | "trends"
  | "matchups"
  | "players"
  | "receivers"
  | "compare"
  | "waivers"
  | "trades"
  | "team"
  | "league"
  // ---- IA-2: the trade calculator, its own link in the Decisions row
  | "trade-calc"
  // ---- IK-4: the account (sign in by email, the saved leagues)
  | "account"
  // ---- IL-5: the watchlist (the players the account saved)
  | "watchlist"
  // ---- IM-5: DFS (no league needed)
  | "dfs"
  // ---- IN-1: the home page ("/home"; "/" when no league is remembered), the blog ("/blog") and a post ("/blog/<slug>")
  | "home"
  | "blog"
  | "post";

const NAMED: Record<string, RouteName> = {
  "/leagues": "leagues",
  "/ros": "ros",
  "/about": "about",
  "/record": "about", // Wave F links: "Our record" folded into "About the numbers"
  "/trends": "trends",
  "/matchups": "matchups",
  "/players": "players",
  "/receivers": "receivers",
  "/compare": "compare",
  "/waivers": "waivers",
  "/trades": "trades",
  "/team": "team",
  "/league": "league",
  "/trade-calc": "trade-calc", // ---- IA-2
  "/account": "account", // ---- IK-4
  "/watchlist": "watchlist", // ---- IL-5
  "/dfs": "dfs", // ---- IM-5
  "/home": "home", // ---- IN-1
  "/blog": "blog", // ---- IN-1
};

export interface Route {
  name: RouteName;
  gsis: string | null;
  params: URLSearchParams;
  depth: number; // how many in-app pages are behind this one (0 = the app was opened here)
  slug: string | null; // ---- IN-1: a blog post's slug ("/blog/<slug>"), else null
}

function parse(): Route {
  const path = location.pathname.replace(/\/+$/, "") || "/";
  const m = path.match(/^\/player\/([^/]+)$/);
  const depth = typeof history.state?.depth === "number" ? history.state.depth : 0;
  const post = path.match(/^\/blog\/([a-z0-9-]{1,80})$/); // ---- IN-1: a post (the API checks the slug again)
  const params = new URLSearchParams(location.search);
  // ---- IN-1: "/" is the home page when no league is in the URL nor remembered on this device (a returning manager's
  // "/" is his week); "/home" always is
  const home = path === "/" && !params.get("league") && !rememberedLeague();
  const name: RouteName = m ? "player" : post ? "post" : home ? "home" : (NAMED[path] ?? "week");
  return { name, gsis: m ? decodeURIComponent(m[1]) : null, params, depth, slug: post ? post[1] : null };
}

// ---- IN-1: lib/prefs.ts's key, read here without importing prefs (the router stays free of the app's modules)
function rememberedLeague(): boolean {
  try {
    return !!localStorage.getItem("ll.league");
  } catch {
    return false;
  }
}

export const route = $state<{ current: Route }>({ current: parse() });
// the path on screen (popstate compares the new one to it: the pane's entries share the screen's path)
let lastPath = typeof location !== "undefined" ? location.pathname : "/";
// ---- II-6: the whole URL on screen (path + query): what a Back leaves, for the pop hook below
let lastHref = typeof location !== "undefined" ? location.pathname + location.search : "/";

if (typeof history !== "undefined") {
  history.scrollRestoration = "manual";
  if (history.state?.depth === undefined) history.replaceState({ ...(history.state ?? {}), depth: 0, scroll: 0 }, "");
}

function saveScroll(): void {
  history.replaceState({ ...(history.state ?? {}), scroll: window.scrollY }, "");
}

export interface NavigateOptions {
  replace?: boolean; // rewrite this history entry (no Back step)
  keepScroll?: boolean; // a new entry on the same screen (the pane): the screen stays where it is
  top?: boolean; // with `replace`: a new page in this entry (the pane's "Full page"), scrolled to the top
  state?: Record<string, unknown>; // extra fields on the history entry (the pane marks the entries it pushed)
}

export function navigate(href: string, opts: NavigateOptions = {}): void {
  // eslint-disable-next-line svelte/prefer-svelte-reactivity -- parsed once, never observed
  const url = new URL(href, location.href);
  if (url.origin !== location.origin) {
    location.href = href;
    return;
  }
  const target = url.pathname + url.search;
  if (opts.replace) {
    const extra = opts.top ? { scroll: 0 } : {};
    history.replaceState({ ...(history.state ?? {}), ...extra, ...(opts.state ?? {}) }, "", target);
    if (opts.top) window.scrollTo(0, 0);
  } else {
    saveScroll();
    const depth = (history.state?.depth ?? 0) + 1;
    const scroll = opts.keepScroll ? window.scrollY : 0;
    history.pushState({ depth, scroll, ...(opts.state ?? {}) }, "", target);
    if (!opts.keepScroll) window.scrollTo(0, 0);
  }
  lastPath = url.pathname;
  lastHref = target; // ---- II-6
  route.current = parse();
}

/** Rewrite the query string in place (league / team picks): no new history entry. */
export function setParams(updates: Record<string, string | null>): void {
  // eslint-disable-next-line svelte/prefer-svelte-reactivity -- a scratch copy; the route state is replaced below
  const qs = new URLSearchParams(location.search);
  for (const [k, v] of Object.entries(updates)) {
    if (v === null || v === "") qs.delete(k);
    else qs.set(k, v);
  }
  const s = qs.toString();
  history.replaceState({ ...(history.state ?? {}) }, "", location.pathname + (s ? `?${s}` : ""));
  lastHref = location.pathname + location.search; // ---- II-6
  route.current = parse();
}

/** Back to the previous in-app page, or to My Week when the app was opened on this page. */
export function back(fallback: string): void {
  if ((history.state?.depth ?? 0) > 0) history.back();
  else navigate(fallback, { replace: true });
}

let pendingScroll: number | null = null;

if (typeof window !== "undefined") {
  window.addEventListener("popstate", () => {
    // ---- II-6: the pop hook may rewrite the entry just landed on before anything renders it (here, in this one
    // listener: a second popstate listener would run after a microtask checkpoint, so the screen would see the old URL)
    const landed = location.pathname + location.search;
    const fix = popHook?.(lastHref, landed) ?? null;
    if (fix && fix !== landed) history.replaceState({ ...(history.state ?? {}) }, "", fix);
    lastHref = location.pathname + location.search;
    // ---- end II-6
    // the same screen (the pane opened or closed over it): it never moved, nothing to restore
    const samePage = location.pathname === lastPath;
    pendingScroll = samePage ? null : typeof history.state?.scroll === "number" ? history.state.scroll : 0;
    lastPath = location.pathname;
    route.current = parse();
  });
}

/** Called by a page once its content is on screen: restores the scroll position of a Back. */
export function restoreScroll(): void {
  if (pendingScroll === null) return;
  const y = pendingScroll;
  pendingScroll = null;
  requestAnimationFrame(() => window.scrollTo(0, y));
}

// ---- II-2 (Wave I-I): a hook that may take a tap on a link before the router navigates (the player drawer takes
// `/player/<key>` links: lib/player-drawer.svelte.ts). True = handled, the router does nothing.
type LinkHook = (href: string, a: HTMLAnchorElement) => boolean;
let linkHook: LinkHook | null = null;
export function setLinkHook(fn: LinkHook | null): void {
  linkHook = fn;
}
// ---- end II-2

// ---- II-6 (Wave I-J): a hook that may rewrite the history entry a Back (or `history.back()`) lands on, before the
// screen sees it: `left` is the URL being left, `landed` the entry's URL; a string replaces the entry's URL in place.
// The player drawer uses it: a parameter the screen wrote while the drawer was open (a search, a filter) stays.
type PopHook = (left: string, landed: string) => string | null;
let popHook: PopHook | null = null;
export function setPopHook(fn: PopHook | null): void {
  popHook = fn;
}
// ---- end II-6

/** Intercept taps on same-site links anywhere in the app (cards' names, tables, search results). */
export function interceptLinks(root: HTMLElement): () => void {
  const onClick = (e: MouseEvent) => {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    const a = (e.target as Element | null)?.closest?.("a");
    if (!a || a.target === "_blank" || a.hasAttribute("download")) return;
    const href = a.getAttribute("href");
    if (!href || !href.startsWith("/") || href.startsWith("/api/")) return;
    e.preventDefault();
    if (linkHook?.(href, a)) return; // ---- II-2: the player drawer
    navigate(href);
  };
  root.addEventListener("click", onClick);
  return () => root.removeEventListener("click", onClick);
}
