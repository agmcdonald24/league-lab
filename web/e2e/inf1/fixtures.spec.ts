// Wave I-I (INF-1): Google Analytics 4 on fixtures. gtag.js is answered by a stub (nothing leaves the machine: every
// Google host is intercepted, the stub sends nothing) and the test reads what the app queued in `window.dataLayer`:
// a page_view per route change, a screen_view with the league key, the team number, the platform and the release, the
// product events (login, select_content, edit_link_click, compare_open, trade_evaluate, waiver_view) — ids only —
// nothing on the sign-in screen, nothing in fixture mode by default, nothing from a LEAGUE_LAB_GA=off build.
// Phone 375 and desktop 1300.
import { expect, test, type BrowserContext, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { extname, join } from "node:path";
import { DYNASTY, FIXTURE_PASSWORD, FIXTURES, serveFixtures, TEST_LEAGUE } from "../fixtures";
import { serveDecisions } from "../decisions-fixtures";

const ID = "G-HJWGHZ79BG";
const RELEASE = "fixture-2026.10.04";
const GOOGLE = /^https:\/\/([a-z0-9-]+\.)*(google-analytics\.com|googletagmanager\.com|google\.com|doubleclick\.net)\//;
const Q = `league=${TEST_LEAGUE}&team=3`;
// every parameter the app may send (anything else — a name, a search, a password — fails the test)
const ALLOWED = new Set([
  "page_location", "page_path", "page_title", "league_key", "roster_id", "platform", "release", "screen_name", "method",
  "content_type", "item_id", "origin", "from", "link_platform", "has_pair", "partner_roster_id", "give_count", "get_count",
  "send_page_view", "allow_google_signals", "allow_ad_personalization_signals",
]);

type Cmd = [string, ...unknown[]];
type Ev = { name: string; p: Record<string, unknown> };
interface Seen {
  scripts: string[]; // gtag.js asked for (the stub answered)
  beacons: string[]; // anything else to a Google host (aborted: there must be none — the stub sends nothing)
}

/** Answer Google's hosts (gtag.js: a stub that does nothing) and /api/health (the release); `force`: GA on (an init
 *  script sets window.__llGa = "on" — fixture mode is off by default). */
async function stubGa(context: BrowserContext, force = true): Promise<Seen> {
  const seen: Seen = { scripts: [], beacons: [] };
  await context.route(GOOGLE, async (route) => {
    const url = route.request().url();
    if (url.startsWith("https://www.googletagmanager.com/gtag/js")) {
      seen.scripts.push(url);
      return route.fulfill({ status: 200, contentType: "text/javascript", body: "window.__gaStub = (window.__gaStub || 0) + 1;" });
    }
    seen.beacons.push(url);
    return route.abort();
  });
  await context.route(/\/api\/health$/, (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true, version: RELEASE }) }),
  );
  if (force) await context.addInitScript(() => ((window as unknown as { __llGa: string }).__llGa = "on"));
  return seen;
}

/** What the app queued for gtag (each entry is gtag's `arguments`). */
async function layer(page: Page): Promise<Cmd[] | null> {
  return page.evaluate(() => {
    const dl = (window as unknown as { dataLayer?: ArrayLike<unknown>[] }).dataLayer;
    return dl ? Array.from(dl, (a) => Array.from(a).map((x) => (x instanceof Date ? "<date>" : x))) as [string, ...unknown[]][] : null;
  });
}
const eventsOf = (l: Cmd[] | null): Ev[] =>
  (l ?? []).filter((c) => c[0] === "event").map((c) => ({ name: String(c[1]), p: (c[2] ?? {}) as Record<string, unknown> }));
const names = async (page: Page) => eventsOf(await layer(page)).map((e) => e.name);

/** Ids only: every parameter allow-listed, the address without any query but league / team, no names anywhere. */
function idsOnly(l: Cmd[] | null, banned: string[]) {
  const text = JSON.stringify(l);
  for (const b of banned) expect(text, `"${b}" was sent to Google Analytics`).not.toContain(b);
  for (const c of l ?? []) {
    const p = (c[0] === "event" ? c[2] : c[0] === "config" || c[0] === "set" ? c[c.length - 1] : null) as Record<string, unknown> | null;
    for (const k of Object.keys(p ?? {})) expect(ALLOWED.has(k), `parameter "${k}" is not on the list`).toBe(true);
    const loc = p?.page_location;
    if (typeof loc === "string") expect([...new URL(loc).searchParams.keys()].every((k) => k === "league" || k === "team")).toBe(true);
  }
}

test.beforeEach(async ({ page }, info) => {
  if (info.project.name === "phone") await page.setViewportSize({ width: 375, height: 812 });
});

test("a page_view per route change and a screen_view with the league and the team — ids only", async ({ context, page }) => {
  await serveFixtures(context);
  const seen = await stubGa(context);
  await page.goto(`/?${Q}&pane_note=hello%20world`); // an extra query parameter never reaches Google
  await expect(page.getByTestId("myteam-foot")).toBeVisible();
  await expect.poll(() => names(page)).toEqual(["page_view", "screen_view"]);
  const l0 = await layer(page);
  // once: gtag.js for this property, the config with our page views and no Google signals / ad personalisation
  expect(seen.scripts).toEqual([`https://www.googletagmanager.com/gtag/js?id=${ID}`]);
  const config = l0!.find((c) => c[0] === "config")!;
  expect(config[1]).toBe(ID);
  expect(config[2]).toMatchObject({ send_page_view: false, allow_google_signals: false, allow_ad_personalization_signals: false, release: RELEASE });
  const ctx = { league_key: TEST_LEAGUE, roster_id: 3, platform: "sleeper", release: RELEASE };
  const [pv, sv] = eventsOf(l0);
  expect(pv.p).toEqual({ ...ctx, page_location: new URL(`/?${Q}`, page.url()).href, page_path: "/", page_title: "week" });
  expect(sv.p).toEqual({ ...ctx, screen_name: "week" });

  // in-app navigation (no reload): About, then Back to My Week — each a page_view and a screen_view
  await page.getByTestId("foot-about").click();
  await expect(page.getByTestId("usage-notice")).toContainText("Google Analytics");
  await expect.poll(() => names(page)).toEqual(["page_view", "screen_view", "page_view", "screen_view"]);
  await page.goBack();
  await expect(page.getByTestId("myteam-foot")).toBeVisible();
  await expect.poll(async () => (await names(page)).length).toBe(6);
  const evs = eventsOf(await layer(page));
  expect(evs.filter((e) => e.name === "page_view").map((e) => e.p.page_title)).toEqual(["week", "about", "week"]);
  expect(evs.filter((e) => e.name === "screen_view").map((e) => [e.p.screen_name, e.p.league_key, e.p.roster_id])).toEqual([
    ["week", TEST_LEAGUE, 3], ["about", TEST_LEAGUE, 3], ["week", TEST_LEAGUE, 3],
  ]);
  expect(evs.find((e) => e.p.page_title === "about")!.p.page_location).toBe(new URL(`/about?${Q}`, page.url()).href);
  await page.waitForTimeout(300); // nothing else arrives (the URL's league / team rewrite is not a view)
  expect(await names(page)).toHaveLength(6);
  idsOnly(await layer(page), ["Fixture Falcons", "fixture_user", "Hail Marys", "hailmary", "pane_note", "hello"]);
  expect(seen.scripts).toHaveLength(1); // loaded once
  expect(seen.beacons).toEqual([]);
});

test("nothing on the sign-in screen; login once the password is accepted — never the password", async ({ context, page }) => {
  await serveFixtures(context, { gate: true });
  const seen = await stubGa(context);
  await page.goto(`/?${Q}`);
  await expect(page.getByTestId("login")).toBeVisible();
  await page.getByPlaceholder("Password").fill("wrong-guess");
  await page.getByRole("button", { name: "Open isuckatfantasy" }).click();
  await expect(page.getByTestId("login")).toBeVisible();
  await page.getByPlaceholder("Password").fill(FIXTURE_PASSWORD);
  await page.waitForTimeout(400);
  expect(seen.scripts).toEqual([]); // gtag.js is not even loaded on the sign-in screen
  expect(await layer(page)).toBeNull();
  await page.getByRole("button", { name: "Open isuckatfantasy" }).click();
  await expect(page.getByTestId("myteam-foot")).toBeVisible();
  await expect.poll(() => names(page)).toEqual(["login", "page_view", "screen_view"]);
  const evs = eventsOf(await layer(page));
  expect(evs[0].p).toEqual({ method: "password", release: RELEASE });
  idsOnly(await layer(page), [FIXTURE_PASSWORD, "wrong-guess", "Fixture Falcons", "fixture_user"]);
  expect((await names(page)).some((n) => n.startsWith("form"))).toBe(false);
  // GA's own switch is off now that the app is on screen (it is on while the sign-in screen shows)
  expect(await page.evaluate((id) => (window as unknown as Record<string, unknown>)[`ga-disable-${id}`], ID)).toBe(false);
  expect(seen.beacons).toEqual([]);
});

test("the product events: a player's drawer, the edit link, Compare, a trade evaluated, Waivers", async ({ context, page, isMobile }) => {
  await serveFixtures(context);
  await serveDecisions(context);
  const seen = await stubGa(context);
  // My Week with the edit link (the Test League's fixture has none: add Sleeper's), Sleeper itself never reached
  const week = JSON.parse(readFileSync(join(FIXTURES, `my-week_${TEST_LEAGUE}_3.json`), "utf8"));
  week.edit_link = { label: "Open Sleeper to edit your lineup", url: `https://sleeper.com/leagues/${TEST_LEAGUE}`, platform: "Sleeper" };
  week.actions ??= []; // the home's actions block (IE-1) carries the link
  await context.route(/\/api\/my-week\?/, (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(week) }));
  await context.route(/^https:\/\/sleeper\.com\//, (route) => route.fulfill({ status: 200, contentType: "text/html", body: "<p>Sleeper</p>" }));
  await page.goto(`/?${Q}`);
  await expect(page.getByTestId("myteam-foot")).toBeVisible();

  // select_content: a lineup name opens the drawer (the URL's pane=)
  const full = page.getByTestId("lineup-full");
  await full.locator("summary").click();
  const hall = page.getByTestId("lineup-full-table").getByRole("link", { name: "Breece Hall" });
  await hall.scrollIntoViewIfNeeded();
  if (isMobile) await hall.tap();
  else await hall.click();
  await expect(page.getByTestId("pane")).toBeVisible();
  await expect.poll(() => names(page)).toContain("select_content");
  const sc = eventsOf(await layer(page)).find((e) => e.name === "select_content")!;
  expect(sc.p).toEqual({ content_type: "player", item_id: "00-0038120", origin: "week", from: "lineup", league_key: TEST_LEAGUE, roster_id: 3, platform: "sleeper", release: RELEASE });
  await page.goBack(); // Back closes the drawer: not a new open
  await expect(page.getByTestId("pane")).toHaveCount(0);

  // edit_link_click: the manager taps "Open Sleeper to edit your lineup" (a new tab)
  const link = page.getByTestId("edit-link");
  await link.scrollIntoViewIfNeeded();
  const popup = page.waitForEvent("popup");
  await link.click();
  await (await popup).close();
  await expect.poll(() => names(page)).toContain("edit_link_click");
  const el = eventsOf(await layer(page)).find((e) => e.name === "edit_link_click")!;
  expect(el.p).toEqual({ link_platform: "sleeper", league_key: TEST_LEAGUE, roster_id: 3, platform: "sleeper", release: RELEASE });
  expect((await names(page)).filter((n) => n === "select_content")).toHaveLength(1);

  // compare_open, trade_evaluate, waiver_view (fresh loads of each screen)
  await page.goto(`/compare?${Q}`);
  await expect.poll(() => names(page)).toContain("compare_open");
  expect(eventsOf(await layer(page)).find((e) => e.name === "compare_open")!.p).toMatchObject({ league_key: TEST_LEAGUE, roster_id: 3, has_pair: 0 });

  await page.goto(`/trade-calc?league=${DYNASTY}&team=12&partner=1&give=11563&get=6904`);
  await expect.poll(() => names(page)).toContain("trade_evaluate");
  expect(eventsOf(await layer(page)).find((e) => e.name === "trade_evaluate")!.p).toEqual({
    partner_roster_id: 1, give_count: 1, get_count: 1, league_key: DYNASTY, roster_id: 12, platform: "sleeper", release: RELEASE,
  });

  await page.goto(`/waivers?league=${DYNASTY}&team=12`);
  await expect.poll(() => names(page)).toEqual(["page_view", "screen_view", "waiver_view"]);
  expect(eventsOf(await layer(page))[2].p).toEqual({ league_key: DYNASTY, roster_id: 12, platform: "sleeper", release: RELEASE });
  idsOnly(await layer(page), ["Fixture Falcons", "fixture_user"]);
  expect(seen.beacons).toEqual([]);
});

test("fixture mode by default: GA is off — no gtag.js, no dataLayer", async ({ context, page }) => {
  await serveFixtures(context);
  const seen = await stubGa(context, false); // no override: localhost and automation keep it off
  await page.goto(`/?${Q}`);
  await expect(page.getByTestId("myteam-foot")).toBeVisible();
  await page.getByTestId("foot-about").click();
  await expect(page.getByTestId("usage-notice")).toBeVisible();
  await page.waitForTimeout(400);
  expect(seen.scripts).toEqual([]);
  expect(seen.beacons).toEqual([]);
  expect(await layer(page)).toBeNull();
});

// ---- LEAGUE_LAB_GA=off: a build of its own (in the OS temp folder — outside the repository, eslint and git; rebuilt
// when dist/ is newer), served to the page by route interception from that folder — even with the override on,
// nothing loads; the bundle has no gtag URL.
const DIST = join(import.meta.dirname, "..", "..", "dist");
const OFF = join(tmpdir(), `league-lab-inf1-ga-off-${process.env.FIXTURES_PORT ?? 8584}`);
const TYPES: Record<string, string> = { ".js": "text/javascript", ".css": "text/css", ".html": "text/html", ".json": "application/json", ".png": "image/png", ".svg": "image/svg+xml", ".webmanifest": "application/manifest+json", ".woff2": "font/woff2" };

function buildOff(): void {
  const fresh = existsSync(join(OFF, "index.html")) && existsSync(join(DIST, "index.html")) &&
    statSync(join(OFF, "index.html")).mtimeMs >= statSync(join(DIST, "index.html")).mtimeMs;
  if (fresh) return;
  execFileSync("npx", ["vite", "build", "--outDir", OFF, "--emptyOutDir"], {
    cwd: join(import.meta.dirname, "..", ".."), env: { ...process.env, LEAGUE_LAB_GA: "off" }, stdio: "ignore",
  });
}
const bundleText = (dir: string) =>
  readdirSync(join(dir, "assets")).filter((f) => f.endsWith(".js")).map((f) => readFileSync(join(dir, "assets", f), "utf8")).join("\n");

test.describe("a LEAGUE_LAB_GA=off build", () => {
  test.describe.configure({ timeout: 180_000 });
  test.beforeAll(() => buildOff());

  test("sends nothing, loads nothing — even with the override on", async ({ context, page }) => {
    expect(bundleText(OFF)).not.toContain("googletagmanager.com");
    expect(bundleText(DIST)).toContain("googletagmanager.com"); // the default build has it (auto: production host only)
    await context.route(/^http:\/\/localhost:\d+\/(?!api\/)/, async (route) => {
      const p = new URL(route.request().url()).pathname;
      const f = join(OFF, p);
      const file = p !== "/" && existsSync(f) && statSync(f).isFile() ? f : join(OFF, "index.html");
      await route.fulfill({ status: 200, contentType: TYPES[extname(file)] ?? "application/octet-stream", body: readFileSync(file) });
    });
    await serveFixtures(context);
    const seen = await stubGa(context, true);
    await page.goto(`/?${Q}`);
    await expect(page.getByTestId("myteam-foot")).toBeVisible();
    await page.getByTestId("foot-about").click();
    await expect(page.getByTestId("usage-notice")).toBeVisible();
    await page.waitForTimeout(400);
    expect(seen.scripts).toEqual([]);
    expect(seen.beacons).toEqual([]);
    expect(await layer(page)).toBeNull();
  });
});
