// ---- INF-1 (Wave I-I): Google Analytics 4, beside the first-party count (lib/usage.ts). docs/HOSTING.md § "Usage".
//
// * Loaded once, on first use — only after sign-in (App.svelte calls in only when the app is on screen), never on the
//   sign-in screen: gtag.js is not in index.html. While the sign-in screen is up again (a cookie expired), GA's own
//   switch `window["ga-disable-<id>"]` is on, so it sends nothing there either.
// * Ids only: the league key, the team (roster) number, the platform, the release (/api/health `version`), the route,
//   a player's id. Never a username, a team or manager name, a password, a search box's text, or any other query
//   parameter (`page_location` keeps only `league` and `team`). No user id, no Google signals, no ad personalisation.
// * The page views are ours (`send_page_view: false`): one `page_view` per route change (path, league, team).
// * The switch: LEAGUE_LAB_GA at build time (vite.config.ts → __LL_GA__). "off": nothing loads, ever (dead code).
//   "on": always. Unset ("auto"): only on the production host (brand.ts GA_HOSTS) and never under automation
//   (navigator.webdriver) — so `npm run dev`, `vite preview`, the fixture e2e runs and the measure runs send nothing.
//   An e2e that wants it sets `window.__llGa = "on"` in an init script (an "off" build ignores it).
import { GA_HOSTS, GA_MEASUREMENT_ID } from "./brand";

declare const __LL_GA__: "on" | "off" | "auto";

type Params = Record<string, string | number | boolean | null | undefined>;
type Gtag = (...args: unknown[]) => void;
interface GaWindow {
  dataLayer?: unknown[];
  gtag?: Gtag;
  __llGa?: string;
}

const MODE: "on" | "off" | "auto" = __LL_GA__; // vite.config.ts `define` (dev, build and preview alike)
// an "off" build folds this to "" — the bundle then holds no gtag URL at all (the e2e checks it)
const SCRIPT = __LL_GA__ === "off" ? "" : "https://www.googletagmanager.com/gtag/js?id=";
const DISABLE = `ga-disable-${GA_MEASUREMENT_ID}`;

/** Is GA on for this page? (The build switch, then the test override, then the production host.) */
export function gaEnabled(): boolean {
  if (MODE === "off" || typeof window === "undefined") return false;
  const forced = (window as GaWindow).__llGa;
  if (forced === "on") return true;
  if (forced === "off") return false;
  if (MODE === "on") return true;
  return GA_HOSTS.includes(location.hostname) && !navigator.webdriver;
}

// the context every event carries (the screen on view): ids only
const ctx: { league_key: string | null; roster_id: number | null; platform: string | null } = { league_key: null, roster_id: null, platform: null };
let release = "unknown";
let ready: Promise<Gtag | null> | null = null;

// ---- IK-3: espn / yahoo by the key's prefix too
const platformOf = (league: string | null): string | null =>
  league ? (/^(mfl|espn|yahoo):/i.test(league) ? league.split(":", 1)[0].toLowerCase() : "sleeper") : null;

/** The page's address without anything but the league and the team (a search, a filter, a username never leave). */
function location_(): string {
  const q = new URLSearchParams();
  if (ctx.league_key) q.set("league", ctx.league_key);
  if (ctx.roster_id !== null) q.set("team", String(ctx.roster_id));
  const s = q.toString();
  return `${location.origin}${location.pathname}${s ? `?${s}` : ""}`;
}

async function releaseStamp(): Promise<string> {
  try {
    const ctl = new AbortController();
    const t = setTimeout(() => ctl.abort(), 2500);
    const res = await fetch("/api/health", { signal: ctl.signal, credentials: "same-origin", headers: { Accept: "application/json" } });
    clearTimeout(t);
    const v = res.ok ? ((await res.json()) as { version?: unknown }).version : null;
    return typeof v === "string" && v.trim() ? v.trim().slice(0, 40) : "unknown";
  } catch {
    return "unknown";
  }
}

/** gtag, set up once (the release first, so the first event already carries it). Null when GA is off. */
function load(): Promise<Gtag | null> {
  if (ready) return ready;
  if (!gaEnabled() || !SCRIPT) return (ready = Promise.resolve(null));
  ready = releaseStamp().then((r) => {
    release = r;
    const w = window as unknown as GaWindow;
    w.dataLayer = w.dataLayer || [];
    // gtag.js reads the `arguments` object itself (not an array): Google's snippet, typed
    w.gtag = function gtag() {
      // eslint-disable-next-line prefer-rest-params
      w.dataLayer!.push(arguments);
    };
    w.gtag("js", new Date());
    w.gtag("config", GA_MEASUREMENT_ID, {
      send_page_view: false, // ours: one page_view per route change (pageView below)
      allow_google_signals: false,
      allow_ad_personalization_signals: false,
      page_location: location_(),
      release,
    });
    const s = document.createElement("script");
    s.async = true;
    s.src = SCRIPT + encodeURIComponent(GA_MEASUREMENT_ID);
    document.head.appendChild(s);
    document.addEventListener("click", onClick, true);
    return w.gtag;
  });
  return ready;
}

/** The params without the unknowns (GA would keep an empty value). */
function clean(p: Params): Record<string, string | number | boolean> {
  const out: Record<string, string | number | boolean> = {};
  for (const [k, v] of Object.entries(p)) if (v !== null && v !== undefined && v !== "") out[k] = v;
  return out;
}

let lastPlayer = ""; // the last select_content's item_id, whichever path sent it (the drawer's hook or the URL's pane)

/** One event, with the screen's context and the release. Never throws, never waits the page. Any caller may use it
 *  (II-2's drawer: `track("select_content", { content_type: "player", item_id: key, origin })` — the URL's `pane`
 *  then does not count the same open twice). */
export function track(name: string, params: Params = {}): void {
  if (!gaEnabled()) return;
  if (name === "select_content" && params.item_id) lastPlayer = String(params.item_id);
  const snapshot = { ...ctx };
  load()
    .then((g) => g?.("event", name, clean({ ...snapshot, release, ...params })))
    .catch(() => {});
}

// the delegated taps (no route has to call in): "Open Sleeper / MFL to edit your lineup" (My Week, `edit-link`)
function onClick(e: Event): void {
  const a = (e.target as Element | null)?.closest?.('a[data-testid="edit-link"]');
  if (a) track("edit_link_click", { link_platform: ctx.platform });
}

let lastPage = "";
let lastScreen = "";
let lastPane = "";

/** The route on screen (App.svelte, beside `countView`, once signed in): a `page_view` when the path, the league or the
 *  team changed; a `screen_view` (the same dedup as the first-party count); the screens' own events (`waiver_view`,
 *  `compare_open`); a player's drawer opened (`select_content`: the URL's `pane`, IB-1's and II-2's key). */
export function screenView(screen: string, league: string | null, team: number | null): void {
  if (!gaEnabled()) return;
  pause(false);
  ctx.league_key = league;
  ctx.roster_id = team;
  ctx.platform = platformOf(league);
  const q = new URLSearchParams(location.search);
  const page = `${location.pathname}|${league ?? ""}|${team ?? ""}`;
  if (page !== lastPage) {
    lastPage = page;
    pageView(screen);
  }
  const key = `${screen}|${league ?? ""}|${team ?? ""}`;
  if (key !== lastScreen) {
    lastScreen = key;
    track("screen_view", { screen_name: screen });
    if (screen === "waivers") track("waiver_view");
    if (screen === "compare") track("compare_open", { has_pair: q.get("a") && q.get("b") ? 1 : 0 });
  }
  const pane = screen === "player" ? "" : (q.get("pane") ?? "");
  // the URL's pane is the fallback: when the drawer's own hook already sent this player (II-2's openPlayer → track),
  // the URL catching up is not a second open
  if (pane && pane !== lastPane && pane !== lastPlayer) trackPlayerOpen({ item_id: pane, origin: screen, from: q.get("from") });
  if (!pane) lastPlayer = ""; // closed: the next open of the same player counts again
  lastPane = pane;
}

/** A `page_view` of the route on screen (`page_location` without any query but league / team; the route's name as the
 *  title — a team name in the document's title never leaves). screenView calls it; exported for a test. */
export function pageView(screen: string): void {
  if (!gaEnabled()) return;
  const page_location = location_();
  const page_path = location.pathname;
  const snapshot = { ...ctx };
  load()
    .then((g) => {
      g?.("set", { page_location, page_title: screen });
      g?.("event", "page_view", clean({ page_location, page_path, page_title: screen, ...snapshot, release }));
    })
    .catch(() => {});
}

/** The beta's password was accepted (App.svelte `signedIn`). */
export function trackLogin(): void {
  track("login", { method: "password" });
}

/** A player's drawer opened (`select_content`). screenView sends it from the URL's `pane`; II-2's drawer may also call
 *  `track("select_content", …)` inside `openPlayer` (or `onPlayerOpen((e) => track("select_content", e))`) — the same
 *  open is counted once either way (`lastPlayer`). */
export function trackPlayerOpen(e: { item_id: string; origin?: string | null; from?: string | null }): void {
  track("select_content", { content_type: "player", item_id: e.item_id, origin: e.origin ?? null, from: e.from ?? null });
}

/** A trade evaluated (lib/api.ts `postEvaluate`): the partner's team number and the package's size — no names. */
export function trackTradeEvaluate(b: { partner: number; give: unknown[]; get: unknown[] }): void {
  track("trade_evaluate", { partner_roster_id: b.partner, give_count: b.give.length, get_count: b.get.length });
}

/** GA's own off switch while the sign-in screen is up (App.svelte): nothing is sent from it. */
export function pause(on: boolean): void {
  if (!gaEnabled()) return;
  (window as unknown as Record<string, unknown>)[DISABLE] = on;
}
// ---- end INF-1
