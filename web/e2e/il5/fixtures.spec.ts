// Wave I-L (IL-5): the watchlist screen and the drawer's Watch / Watching, under accounts on (IK-4's pattern: an
// in-test account server keeps the state; its answers copy the shapes recorded from the real API on the clone —
// web/fixtures/ik4/*.json and web/fixtures/il5/watchlist.json, written by api/tests/test_il5.py with IL5_RECORD=1).
// The players are League of Scrubs's (three free agents whose drawer cards II-2 recorded, a rostered receiver and one
// of team 2's). Phone at 375 and desktop at 1300. GA is stubbed (nothing leaves the machine): the two events carry
// the player's id, never a name.
import { expect, test, type BrowserContext, type Page, type Route } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { SCRUBS, serveFixtures } from "../fixtures";

const IK4 = join(import.meta.dirname, "..", "..", "fixtures", "ik4");
const IL5 = join(import.meta.dirname, "..", "..", "fixtures", "il5");
const read = <T>(dir: string, name: string) => JSON.parse(readFileSync(join(dir, name), "utf8")) as T;
const SHOTS = process.env.SHOTS_DIR ?? join(import.meta.dirname, "..", ".out");
const GOOGLE = /^https:\/\/([a-z0-9-]+\.)*(google-analytics\.com|googletagmanager\.com|google\.com|doubleclick\.net)\//;
const Q = `league=${SCRUBS}&team=2`;

type Row = { player_key: string; player_name: string | null } & Record<string, unknown>;
const ANSWER = read<{ players: Row[] } & Record<string, unknown>>(IL5, "watchlist.json");

/** The account API for one test: signed in (or not), the watchlist in memory. */
class AccountServer {
  signedIn = true;
  watch: { league: string | null; player_key: string }[] = ANSWER.players.map((p) => ({ league: null, player_key: p.player_key }));
  calls: string[] = [];

  async attach(context: BrowserContext): Promise<void> {
    await context.route(/\/api\/account(\/|$|\?)/, async (route: Route) => {
      const req = route.request();
      const url = new URL(req.url());
      const p = url.pathname.replace(/^\/api\/account/, "") || "/";
      const m = req.method();
      this.calls.push(`${m} ${p}${url.search}`);
      const send = (status: number, body: unknown) => route.fulfill({ status, contentType: "application/json", headers: { "Cache-Control": "no-store" }, body: JSON.stringify(body) });
      if (p === "/status") return send(200, this.signedIn ? read(IK4, "status_signed_in.json") : read(IK4, "status_signed_out.json"));
      if (!this.signedIn) return send(401, { error: "Sign in with your email to see your account.", code: "signed_out" });
      if (p === "/me" && m === "GET") {
        const watchlist = this.watch.map((w) => ({ league_key: w.league ? `sleeper:2026:${w.league}` : null, league: w.league, player_key: w.player_key, added_at: "2026-10-05T12:00:00+00:00" }));
        return send(200, { ...read<object>(IK4, "me.json"), leagues: [], default_league: null, preferences: [], watchlist, connections: [] });
      }
      if (p === "/watchlist" && m === "GET") {
        const keep = new Set(this.watch.map((w) => w.player_key));
        const players = ANSWER.players.filter((r) => keep.has(r.player_key));
        return send(200, { ...ANSWER, league: url.searchParams.get("league"), count: players.length, shown: players.length, players });
      }
      if (p === "/watchlist" && m === "PUT") {
        const b = req.postDataJSON() as { player_key: string; league: string | null };
        if (!this.watch.some((w) => w.player_key === b.player_key && w.league === (b.league ?? null))) this.watch.push({ league: b.league ?? null, player_key: b.player_key });
        return send(200, { ok: true });
      }
      if (p === "/watchlist" && m === "DELETE") {
        const k = url.searchParams.get("player_key");
        const l = url.searchParams.get("league");
        this.watch = this.watch.filter((w) => !(w.player_key === k && (w.league ?? null) === (l ?? null)));
        return send(200, { ok: true });
      }
      if (p === "/leagues" && m === "PUT") return send(200, { ok: true, saved: 0 });
      return send(404, { error: `no account route ${m} ${p}` });
    });
  }
}

async function stubGa(context: BrowserContext) {
  await context.route(GOOGLE, async (route) => {
    if (route.request().url().startsWith("https://www.googletagmanager.com/gtag/js")) return route.fulfill({ status: 200, contentType: "text/javascript", body: "" });
    return route.abort();
  });
  await context.route(/\/api\/health$/, (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true, version: "fixture-il5" }) }));
  await context.addInitScript(() => ((window as unknown as { __llGa: string }).__llGa = "on"));
}

async function gaEvents(page: Page): Promise<{ name: string; p: Record<string, unknown> }[]> {
  return page.evaluate(() => {
    const dl = (window as unknown as { dataLayer?: ArrayLike<unknown>[] }).dataLayer;
    return Array.from(dl ?? [], (a) => Array.from(a))
      .filter((c) => c[0] === "event")
      .map((c) => ({ name: String(c[1]), p: (c[2] ?? {}) as Record<string, unknown> }));
  });
}

async function noSidewaysScroll(page: Page) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(sw, "page wider than the screen").toBeLessThanOrEqual(iw);
}

test.beforeEach(async ({ page, isMobile }) => {
  if (isMobile) await page.setViewportSize({ width: 375, height: 812 });
});

test("signed in: the saved players in this league, a name opens the drawer, Watching / Watch, Remove", async ({ context, page }, info) => {
  const server = new AccountServer();
  await serveFixtures(context);
  await server.attach(context);
  await stubGa(context);

  // the ⋯ menu's entry
  await page.goto(`/?${Q}`);
  await expect(page.getByTestId("myteam-foot")).toBeVisible();
  await page.getByTestId("overflow").click();
  await page.getByTestId("menu-watchlist").click();
  await expect(page).toHaveURL(new RegExp(`/watchlist\\?${Q}`));

  await expect(page.getByTestId("watchlist-stamp")).toHaveText("5 players · projected points in League of Scrubs scoring, week 4. Tap a name for his card.");
  const rows = page.getByTestId("watchlist-row");
  await expect(rows).toHaveCount(5);
  const first = rows.nth(0);
  await expect(first.getByTestId("watchlist-name")).toHaveText("Wan'Dale Robinson");
  await expect(first).toContainText("TEN");
  await expect(first.getByTestId("watchlist-status")).toHaveText("No injury designation");
  await expect(first.getByTestId("watchlist-proj")).toHaveText("8.3 projected");
  await expect(first.getByTestId("watchlist-owner")).toHaveText("Free agent");
  const flowers = page.locator('[data-testid="watchlist-row"][data-player="00-0039064"]');
  await expect(flowers.getByTestId("watchlist-status")).toHaveText("Questionable");
  await expect(flowers.getByTestId("watchlist-owner")).toHaveText("Rostered by Run Bijan Run");
  await expect(page.locator('[data-testid="watchlist-row"][data-player="00-0041496"]').getByTestId("watchlist-owner")).toHaveText("On your team");
  expect(server.calls).toContain(`GET /watchlist?league=${SCRUBS}&team=2`);
  await noSidewaysScroll(page);
  await page.screenshot({ path: join(SHOTS, `il5-watchlist-${info.project.name}.png`), fullPage: true });

  // a name opens the drawer (II-2's link hook), where he is "Watching"; a tap un-watches him (and he leaves the list)
  await first.getByTestId("watchlist-name").click();
  await expect(page.getByTestId("pane-title")).toHaveText("Wan'Dale Robinson");
  const btn = page.getByTestId("drawer-watch");
  await expect(btn).toHaveText("★ Watching");
  await expect(btn).toHaveAttribute("aria-pressed", "true");
  await page.screenshot({ path: join(SHOTS, `il5-drawer-watching-${info.project.name}.png`), fullPage: false });
  await btn.click();
  await expect(btn).toHaveText("☆ Watch");
  await expect.poll(() => server.watch.some((w) => w.player_key === "00-0038117")).toBe(false);
  await expect(rows).toHaveCount(4);
  await btn.click();
  await expect(btn).toHaveText("★ Watching");
  await expect.poll(() => server.watch.some((w) => w.player_key === "00-0038117" && w.league === null)).toBe(true);
  await expect(rows).toHaveCount(5);
  await page.getByTestId("pane-close").click();

  // Remove on a row
  await page.locator('[data-testid="watchlist-row"][data-player="00-0039880"]').getByTestId("watchlist-remove").click();
  await expect(rows).toHaveCount(4);
  await expect.poll(() => server.watch.map((w) => w.player_key)).not.toContain("00-0039880");
  await expect(page.getByTestId("watchlist-stamp")).toContainText("4 players");
  await noSidewaysScroll(page);

  // GA: the two events with the player's id and where the tap was — never a name
  const ev = await gaEvents(page);
  const mine = ev.filter((e) => e.name === "watchlist_add" || e.name === "watchlist_remove");
  expect(mine.map((e) => e.name)).toEqual(["watchlist_remove", "watchlist_add", "watchlist_remove"]);
  expect(mine.map((e) => e.p.item_id)).toEqual(["00-0038117", "00-0038117", "00-0039880"]);
  expect(mine[2].p.origin).toBe("watchlist");
  expect(JSON.stringify(mine)).not.toContain("Robinson");
});

test("the drawer offers Watch on any league screen when signed in, and the list follows", async ({ context, page }) => {
  const server = new AccountServer();
  server.watch = [];
  await serveFixtures(context);
  await server.attach(context);
  await page.goto(`/watchlist?${Q}`);
  await expect(page.getByTestId("watchlist-empty")).toHaveText("No players on your watchlist yet. Open any player's card and tap ☆ Watch.");
  await noSidewaysScroll(page);
  await page.goto(`/waivers?${Q}&pane=00-0038544`);
  await expect(page.getByTestId("pane-title")).toHaveText("Quentin Johnston");
  await page.getByTestId("drawer-watch").click();
  await expect(page.getByTestId("drawer-watch")).toHaveText("★ Watching");
  await expect.poll(() => server.watch).toEqual([{ league: null, player_key: "00-0038544" }]);
  await page.goto(`/watchlist?${Q}`);
  await expect(page.getByTestId("watchlist-row")).toHaveCount(1);
  await expect(page.getByTestId("watchlist-name")).toHaveText("Quentin Johnston");
});

test("signed out: one line to sign in, no Watch in the drawer; accounts off: one line, no menu item", async ({ context, page }, info) => {
  const server = new AccountServer();
  server.signedIn = false;
  await serveFixtures(context);
  await server.attach(context);
  await page.goto(`/watchlist?${Q}`);
  await expect(page.getByTestId("watchlist-signin")).toHaveText(
    "Sign in to keep a watchlist on any device: sign in with your email, then tap ☆ Watch on any player's card.",
  );
  await expect(page.getByTestId("watchlist-signin-link")).toHaveAttribute("href", "/account");
  await expect(page.getByTestId("watchlist-rows")).toHaveCount(0);
  await noSidewaysScroll(page);
  await page.screenshot({ path: join(SHOTS, `il5-signed-out-${info.project.name}.png`), fullPage: false });
  await page.goto(`/waivers?${Q}&pane=00-0038544`);
  await expect(page.getByTestId("pane-title")).toHaveText("Quentin Johnston");
  await expect(page.getByTestId("drawer-compare")).toBeVisible();
  await expect(page.getByTestId("drawer-watch")).toHaveCount(0);
  expect(server.calls.filter((c) => c.includes("/watchlist"))).toEqual([]);
});

test("accounts off on the server: no menu item, one plain line on /watchlist", async ({ context, page }) => {
  await serveFixtures(context); // no account routes: /api/account/status answers 404 (an older server)
  await page.goto(`/?${Q}`);
  await page.getByTestId("overflow").click();
  await expect(page.getByTestId("menu-leagues")).toBeVisible();
  await expect(page.getByTestId("menu-watchlist")).toHaveCount(0);
  await page.goto(`/watchlist?${Q}`);
  await expect(page.getByTestId("watchlist-off")).toHaveText("A watchlist comes with an account, and accounts are not on for this server yet.");
});

// ---- the providers' switches on the setup screen (recorded from /api/providers by api/tests/test_il5.py)
async function providers(context: BrowserContext, name: string) {
  await context.route(/\/api\/providers$/, (route) => route.fulfill({ status: 200, contentType: "application/json", body: readFileSync(join(IL5, name), "utf8") }));
}

test("ESPN switched off on the server: the setup screen says so in place of the form", async ({ context, page }, info) => {
  await serveFixtures(context);
  await providers(context, "providers_espn_off.json");
  await page.goto("/leagues?platform=espn");
  await expect(page.getByTestId("espn-off")).toHaveText("ESPN leagues: not available right now. Sleeper and MyFantasyLeague leagues work as before.");
  await expect(page.getByTestId("espn-form")).toHaveCount(0);
  await expect(page.getByTestId("platform-note")).not.toContainText("not verified"); // off: the off line is the one said
  await noSidewaysScroll(page);
  await page.screenshot({ path: join(SHOTS, `il5-espn-off-${info.project.name}.png`), fullPage: false });
  await page.getByTestId("platform-yahoo").click();
  await expect(page.getByTestId("yahoo-setup")).toBeVisible();
});

test("ESPN and Yahoo verified (LEAGUE_LAB_PROVIDER_VERIFIED): no 'not verified' words anywhere on the setup screen", async ({ context, page }) => {
  await serveFixtures(context);
  await providers(context, "providers_verified.json");
  for (const p of ["espn", "yahoo"]) {
    await page.goto(`/leagues?platform=${p}`);
    await expect(page.getByTestId("provider-caps")).toBeVisible();
    await expect(page.getByTestId("platform-note")).not.toContainText("not verified");
    await page.getByTestId("provider-caps").locator("summary").click();
    await expect(page.getByTestId("provider-caps")).not.toContainText("not verified on a live league yet");
  }
  await expect(page.getByTestId("espn-form")).toHaveCount(0);
});

test("the account page lists the connections it keeps and the watchlist", async ({ context, page }) => {
  const server = new AccountServer();
  await serveFixtures(context);
  await server.attach(context);
  await context.route(/\/api\/account\/me$/, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ...read<object>(IK4, "me.json"),
        leagues: [],
        default_league: null,
        watchlist: server.watch.map((w) => ({ league_key: null, league: null, player_key: w.player_key, added_at: null })),
        connections: [
          { provider: "yahoo", external_user_id: "FIXTUREGUID3", connected_at: "2026-10-05T16:00:00+00:00", status: "active", last_sync_at: null },
          { provider: "espn", external_user_id: "espn-0123456789abcdef", connected_at: "2026-10-01T16:00:00+00:00", status: "expired", last_sync_at: null },
        ],
      }),
    }),
  );
  await page.goto("/account");
  await expect(page.getByTestId("account-watchlist")).toBeVisible();
  await expect(page.getByTestId("account-more")).toContainText("Your watchlist: 5 players.");
  await expect(page.locator('[data-testid="account-connection"][data-provider="yahoo"]')).toHaveText(
    "Yahoo: connected 2026-10-05 — it comes back on any device you sign in on.",
  );
  const espn = page.locator('[data-testid="account-connection"][data-provider="espn"]');
  await expect(espn).toContainText("ESPN: needs reconnecting (it no longer opens your leagues).");
  await expect(espn.getByTestId("account-reconnect")).toHaveAttribute("href", "/leagues?platform=espn");
  await expect(page.getByTestId("account-privacy")).toContainText("a Yahoo or ESPN connection only if you make one (encrypted) — nothing else");
  await noSidewaysScroll(page);
});
