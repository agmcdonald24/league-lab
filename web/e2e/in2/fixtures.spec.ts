// Wave I-N (IN-2): the lab without a league — the scoring picker (scoring, options, league size; remembered, in the URL),
// the tabs while browsing (Players · Trades · DFS: no My Team, no Waivers), a player's pane with his value in a typical
// league of that shape and no ownership line, and the trade calculator without a league (two sides by search, the
// answer in words with its uncertainty, Swap sides = the mirror answer). Phone at 375 and desktop at 1300; screenshots
// into docs/handbacks/in2/ (SHOTS_IN2) and e2e/.out.
//
// Two modes, as IM-3's: default (the fixtures suite) answers every `ref:` call from web/fixtures/in2/api_in2.json and
// the rest from serveFixtures; IN2_LIVE=http://localhost:8762 (the fixture API serving web/dist) walks the real server
// and records the `ref:` answers into api_in2.json.
import { expect, test, type BrowserContext, type Page } from "@playwright/test";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { serveFixtures } from "../fixtures";

const LIVE = process.env.IN2_LIVE ?? "";
const DIR = join(import.meta.dirname, "..", "..", "fixtures", "in2");
const RECORDED = join(DIR, "api_in2.json");
const SHOTS = process.env.SHOTS_IN2 ?? join(import.meta.dirname, "..", ".out");
const PUKA = "00-0039075";
const BIJAN = "00-0038542";
const ARSB = "00-0036963";
type Recorded = Record<string, { status: number; body: unknown }>;

if (LIVE) test.use({ baseURL: LIVE });

const keyOf = (u: URL) => {
  const q = [...u.searchParams.entries()].sort(([a], [b]) => a.localeCompare(b));
  return `${u.pathname}?${new URLSearchParams(q).toString()}`;
};
const isRefCall = (u: URL) => /^ref:/i.test(u.searchParams.get("league") ?? "") || /^\/api\/leagues\/ref:/i.test(decodeURIComponent(u.pathname));
const recorded: Recorded = existsSync(RECORDED) ? (JSON.parse(readFileSync(RECORDED, "utf8")) as Recorded) : {};

async function api(context: BrowserContext): Promise<{ calls: string[] }> {
  const calls: string[] = [];
  await context.route(/^https:\/\/static\.www\.nfl\.com\//, (route) => route.abort());
  await context.route(/^https:\/\/([a-z0-9-]+\.)*(google-analytics\.com|googletagmanager\.com)\//, (route) => route.abort());
  if (LIVE) {
    await context.route(/\/api\//, async (route) => {
      const u = new URL(route.request().url());
      calls.push(u.pathname + u.search);
      try {
        const res = await route.fetch();
        if (isRefCall(u) && route.request().method() === "GET") {
          try {
            recorded[keyOf(u)] = { status: res.status(), body: await res.json() };
          } catch {
            /* not JSON */
          }
        }
        await route.fulfill({ response: res });
      } catch {
        /* the page closed with the request in flight */
      }
    });
    return { calls };
  }
  await serveFixtures(context);
  await context.route(/\/api\//, async (route) => {
    const u = new URL(route.request().url());
    calls.push(u.pathname + u.search);
    if (!isRefCall(u)) return route.fallback();
    const league = u.searchParams.get("league");
    const hit =
      recorded[keyOf(u)] ??
      Object.entries(recorded).find(([k]) => k.startsWith(`${u.pathname}?`) && new URLSearchParams(k.split("?")[1]).get("league") === league)?.[1];
    if (!hit) return route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ error: `not recorded: ${keyOf(u)}` }) });
    return route.fulfill({ status: hit.status, contentType: "application/json", body: JSON.stringify(hit.body) });
  });
  return { calls };
}

async function noSidewaysScroll(page: Page) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(sw, "no sideways page scroll").toBeLessThanOrEqual(iw + 1);
}

const shot = (page: Page, name: string, full = false) => {
  mkdirSync(SHOTS, { recursive: true });
  return page.screenshot({ path: join(SHOTS, `${name}.png`), fullPage: full });
};

test.beforeEach(async ({ page, isMobile }) => {
  if (isMobile) await page.setViewportSize({ width: 375, height: 812 });
});

test.afterAll(() => {
  if (!LIVE) return;
  mkdirSync(DIR, { recursive: true });
  const trim = (v: unknown): unknown =>
    Array.isArray(v) ? v.slice(0, 60).map(trim) : v && typeof v === "object" ? Object.fromEntries(Object.entries(v).map(([k, x]) => [k, trim(x)])) : v;
  writeFileSync(RECORDED, JSON.stringify(trim(recorded)));
});

test("the picker: scoring, options and size in the URL and remembered; the tabs while browsing", async ({ context, page }, info) => {
  await api(context);
  const wide = info.project.name === "desktop";
  await page.goto("/players?league=ref:half");
  await expect(page.getByTestId("ref-picker")).toBeVisible();
  await expect(page.getByTestId(wide ? "ref-label" : "ref-short")).toHaveText("Half PPR");
  await expect(page.getByTestId("ref-open")).toHaveText("Open your league");
  // the tabs: Players · Trades · DFS — My Team and Waivers are behind "Open your league"
  await expect(page.getByTestId("tab-players")).toBeVisible();
  await expect(page.getByTestId("tab-trades")).toBeVisible();
  await expect(page.getByTestId("tab-dfs")).toBeVisible();
  await expect(page.getByTestId("tab-myteam")).toHaveCount(0);
  await expect(page.getByTestId("tab-waivers")).toHaveCount(0);
  await expect(page.locator("body")).not.toContainText("No league");
  await expect(page.getByTestId("players").getByRole("link", { name: /Smith-Njigba|St\. Brown|Chase|Nacua|Jefferson|Lamb/ }).first()).toBeVisible({ timeout: 30_000 });

  await page.getByTestId("ref-button").click();
  const panel = page.getByTestId("ref-panel");
  await expect(panel).toBeVisible();
  await expect(page.getByTestId("ref-sleeper")).toHaveText("Sleeper has no single default: a Sleeper league picks PPR, Half PPR or Standard when it is made.");
  await page.getByTestId("ref-base-ppr").click();
  await expect(page).toHaveURL(/league=ref(%3A|:)ppr(&|$)/);
  await expect(page.getByTestId("ref-rules")).toContainText("1 point per catch");
  await page.getByTestId("ref-opt-sf").locator("input").check();
  await expect(page).toHaveURL(/league=ref(%3A|:)ppr\.sf(&|$)/);
  const stats = page.waitForResponse((r) => r.url().includes("/api/players?") && /league=ref(%3A|:)ppr\.sf\.t10/.test(r.url()));
  await page.getByTestId("ref-teams-10").click();
  await expect(page).toHaveURL(/league=ref(%3A|:)ppr\.sf\.t10(&|$)/);
  expect((await stats).status()).toBe(200);
  await noSidewaysScroll(page);
  await shot(page, `in2-picker-${info.project.name}`);
  await page.getByTestId("ref-done").click();
  await expect(panel).toHaveCount(0);
  await expect(page.getByTestId(wide ? "ref-label" : "ref-short")).toHaveText(wide ? "PPR · superflex · 10 teams" : "PPR +2");
  expect(await page.evaluate(() => localStorage.getItem("ll.scoring"))).toBe("ref:ppr.sf.t10");
  expect(await page.evaluate(() => localStorage.getItem("ll.league"))).toBeNull(); // never "the league"
  await expect(page.getByTestId("players").getByRole("link", { name: /Smith-Njigba|St\. Brown|Chase|Nacua|Jefferson|Lamb/ }).first()).toBeVisible({ timeout: 30_000 });
  // the Stats table's value column (after the points), sorted by it on a tap; no "whose" chips while browsing
  await expect(page.getByTestId("sort-ros_value")).toHaveCount(1);
  await expect(page.getByTestId("who")).toHaveCount(0);
  await page.getByTestId("sort-ros_value").click();
  await expect(page).toHaveURL(/sort=ros_value/);
  // the PPR · superflex · 10-team values: a quarterback leads (in Half PPR, one quarterback, Bijan Robinson at 202 does)
  await expect(page.getByTestId("players")).toContainText("Patrick Mahomes, 205");
  await shot(page, `in2-stats-${info.project.name}`);
  // Compare: each side's value in the picked shape
  await page.goto(`/compare?league=ref:ppr.sf.t10&a=${PUKA}&b=${ARSB}`);
  await expect(page.getByText("Value (a typical league)")).toBeVisible({ timeout: 30_000 });
});

test("a player's pane while browsing: the scoring in the head, his value, no owner, the foot line", async ({ context, page }, info) => {
  await api(context);
  await page.goto(`/players?league=ref:ppr.sf.t10&pane=${PUKA}&from=search`);
  const pane = page.getByTestId("pane");
  await expect(pane).toBeVisible();
  await expect(page.getByTestId("drawer-league")).toContainText("PPR · superflex · 10 teams");
  const value = page.getByTestId("pane-section-value");
  await expect(value).toContainText("in a 10-team PPR league, two quarterbacks (superflex)", { timeout: 30_000 });
  await expect(value).toContainText("Value");
  await expect(pane).not.toContainText(/free agent|rostered by|No league|Waiver Wire/i);
  await expect(page.getByTestId("pane-foot")).toHaveText("Open your league to see who has him and what he is worth to your team.");
  await noSidewaysScroll(page);
  await shot(page, `in2-pane-${info.project.name}`);
  await page.getByTestId("pane-foot").scrollIntoViewIfNeeded();
  await value.scrollIntoViewIfNeeded();
  await shot(page, `in2-pane-value-${info.project.name}`);
  // the full page says the same
  await page.goto(`/player/${PUKA}?league=ref:ppr.sf.t10`);
  await expect(page.getByTestId("player-foot")).toContainText("Priced in PPR · superflex · 10 teams.");
  await expect(page.getByTestId("section-value")).toContainText("in a 10-team PPR league, two quarterbacks (superflex)");
  await expect(page.getByTestId("player")).not.toContainText(/free agent|No league/i);
  await expect(page.getByTestId("back")).toContainText("Players");
  await noSidewaysScroll(page);
  await shot(page, `in2-player-${info.project.name}`, true);
});

test("the trade calculator without a league: two sides by search, the answer in words, Swap sides mirrors it", async ({ context, page }, info) => {
  await api(context);
  await page.goto("/players?league=ref:half");
  await page.getByTestId("tab-trades").click();
  await expect(page).toHaveURL(/\/trade-calc\?league=ref(%3A|:)half/);
  await expect(page.getByTestId("free-trade")).toBeVisible();
  await expect(page.getByTestId("invite-card")).toHaveCount(0);
  await expect(page.getByTestId("ft-empty")).toContainText("Add a player to each side");
  await page.getByTestId("ft-search-give").fill("nacua");
  await page.getByTestId("ft-hit-give").first().click();
  await expect(page).toHaveURL(new RegExp(`give=${PUKA}`));
  await page.getByTestId("ft-search-get").fill("bijan");
  await page.getByTestId("ft-hit-get").first().click();
  await page.getByTestId("ft-search-get").fill("st. brown");
  await page.getByTestId("ft-hit-get").first().click();
  await expect(page).toHaveURL(new RegExp(`get=${BIJAN}(%2C|,)${ARSB}`));
  const words = page.getByTestId("ft-words");
  await expect(words).toContainText(/^(You get more|About even|You give more)/, { timeout: 30_000 });
  await expect(words).toContainText("You get more");
  await expect(page.getByTestId("ft-one")).toContainText("Bijan Robinson");
  await expect(page.getByTestId("ft-spots")).toContainText("You need 1 more roster spot");
  await expect(page.getByTestId("ft-give-row")).toHaveCount(1);
  await expect(page.getByTestId("ft-get-row")).toHaveCount(2);
  await expect(page.getByTestId("ft-outlook").first()).toContainText("week 4");
  await expect(page.getByTestId("ft-assumes")).toContainText("Value in a 12-team Half PPR league, one quarterback.");
  await expect(page.getByTestId("ft-open")).toHaveText("Open your league to see what this does to your lineup.");
  await expect(page.getByTestId("free-trade")).not.toContainText(/free agent|No league/i);
  await noSidewaysScroll(page);
  await shot(page, `in2-calc-${info.project.name}`, true);

  await page.getByTestId("ft-swap").click();
  await expect(page).toHaveURL(new RegExp(`give=${BIJAN}(%2C|,)${ARSB}`));
  await expect(words).toContainText("You give more", { timeout: 30_000 });
  await expect(page.getByTestId("ft-give-row")).toHaveCount(2);

  // a shared link opens the same trade in another scoring
  await page.goto(`/trade-calc?league=ref:std.t14&give=${PUKA}&get=${ARSB}`);
  await expect(page.getByTestId("ft-words")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("ft-assumes")).toContainText("Value in a 14-team Standard league, one quarterback.");
  await page.getByTestId("ft-how").locator("summary, button").first().click();
  await expect(page.getByTestId("ft-pricing")).toContainText("Standard");
  await noSidewaysScroll(page);
});

test("a decision screen while browsing still invites; Trades never does", async ({ context, page }) => {
  await api(context);
  await page.goto("/waivers?league=ref:half");
  await expect(page.getByTestId("invite-card")).toBeVisible();
  await page.goto("/trades?league=ref:yahoo");
  await expect(page).toHaveURL(/\/trade-calc\?league=ref(%3A|:)yahoo/);
  await expect(page.getByTestId("free-trade")).toBeVisible();
  await expect(page.getByTestId("invite-card")).toHaveCount(0);
});
