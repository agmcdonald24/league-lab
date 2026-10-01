// A two-route router on the History API: "/" (My Week) and "/player/<gsis>".
// * A tap on a same-site link is handled here (no reload, same session, one history entry).
// * Changing the league or team rewrites the URL in place (replace), so Back goes to the previous PAGE.
// * Each history entry remembers its scroll position; Back restores it.

export interface Route {
  name: "week" | "player";
  gsis: string | null;
  params: URLSearchParams;
  depth: number; // how many in-app pages are behind this one (0 = the app was opened here)
}

function parse(): Route {
  const path = location.pathname;
  const m = path.match(/^\/player\/([^/]+)\/?$/);
  const depth = typeof history.state?.depth === "number" ? history.state.depth : 0;
  return { name: m ? "player" : "week", gsis: m ? decodeURIComponent(m[1]) : null, params: new URLSearchParams(location.search), depth };
}

export const route = $state<{ current: Route }>({ current: parse() });

if (typeof history !== "undefined") {
  history.scrollRestoration = "manual";
  if (history.state?.depth === undefined) history.replaceState({ ...(history.state ?? {}), depth: 0, scroll: 0 }, "");
}

function saveScroll(): void {
  history.replaceState({ ...(history.state ?? {}), scroll: window.scrollY }, "");
}

export function navigate(href: string, opts: { replace?: boolean } = {}): void {
  // eslint-disable-next-line svelte/prefer-svelte-reactivity -- parsed once, never observed
  const url = new URL(href, location.href);
  if (url.origin !== location.origin) {
    location.href = href;
    return;
  }
  const target = url.pathname + url.search;
  if (opts.replace) {
    history.replaceState({ ...(history.state ?? {}) }, "", target);
  } else {
    saveScroll();
    const depth = (history.state?.depth ?? 0) + 1;
    history.pushState({ depth, scroll: 0 }, "", target);
    window.scrollTo(0, 0);
  }
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
    pendingScroll = typeof history.state?.scroll === "number" ? history.state.scroll : 0;
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

/** Intercept taps on same-site links anywhere in the app (cards' names, tables, search results). */
export function interceptLinks(root: HTMLElement): () => void {
  const onClick = (e: MouseEvent) => {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    const a = (e.target as Element | null)?.closest?.("a");
    if (!a || a.target === "_blank" || a.hasAttribute("download")) return;
    const href = a.getAttribute("href");
    if (!href || !href.startsWith("/") || href.startsWith("/api/")) return;
    e.preventDefault();
    navigate(href);
  };
  root.addEventListener("click", onClick);
  return () => root.removeEventListener("click", onClick);
}
