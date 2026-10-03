// The web app at both viewports (projects "phone" = iPhone 13 UA at 390 × 844 with touch, "desktop" = 1300 × 900):
// no sideways scroll, the answer on the first screen, a name is one tap and stays in this tab, Back works,
// the league / team pick is remembered, search, the password gate (when E2E_GATED_URL is set).
import { expect, test, type Page } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { join } from "node:path";

const DYNASTY = "1321941740235550720";
const SCRUBS = "1389709692405551104";
const TEAMS: [string, number, string][] = [
  [DYNASTY, 12, "dyn12"],
  [SCRUBS, 2, "scrubs2"],
];
const SHOTS = process.env.SHOTS_DIR ?? join(import.meta.dirname, ".out");
mkdirSync(SHOTS, { recursive: true });

async function noSidewaysScroll(page: Page) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(sw, "page wider than the screen").toBeLessThanOrEqual(iw);
}

async function tapOrClick(page: Page, loc: ReturnType<Page["locator"]>, isMobile: boolean) {
  if (isMobile) await loc.tap();
  else await loc.click();
}

for (const [league, team, tag] of TEAMS) {
  test(`My Week ${tag}: the answer is the first screen, no sideways scroll, tables of five columns at most`, async ({ page }, info) => {
    await page.goto(`/?league=${league}&team=${team}`);
    const first = page.getByTestId("decision-card").first();
    await expect(first).toBeVisible();
    await noSidewaysScroll(page);
    const vh = page.viewportSize()!.height;
    const box = (await first.boundingBox())!;
    expect(box.y + box.height, "the first card ends below the first screen").toBeLessThanOrEqual(vh);
    expect(await page.getByTestId("lineup").locator("thead th").count()).toBeLessThanOrEqual(5);
    await page.screenshot({ path: join(SHOTS, `web_week_${tag}_${info.project.name}_fold.png`) });
    await page.getByTestId("lineup-full").locator("summary").click();
    await expect(page.getByTestId("lineup-full-table")).toBeVisible();
    expect(await page.getByTestId("lineup-full-table").locator("thead th").count()).toBeLessThanOrEqual(5);
    await page.getByTestId("howto").locator("summary").click();
    await noSidewaysScroll(page);
    await page.screenshot({ path: join(SHOTS, `web_week_${tag}_${info.project.name}_full.png`), fullPage: true });
  });
}

test("a name in a card is one tap, stays in this tab and session, and Back returns to the same place", async ({ page, context, isMobile }, info) => {
  await page.goto(`/?league=${DYNASTY}&team=12`);
  const card = page.getByTestId("decision-card").first();
  await expect(card).toBeVisible();
  const link = card.locator("a").first();
  const name = (await link.textContent())!.trim();
  const href = (await link.getAttribute("href"))!;
  expect(href).toMatch(new RegExp(`^/player/[^?]+\\?league=${DYNASTY}&team=12$`));
  const historyBefore = await page.evaluate(() => history.length);
  let popups = 0;
  context.on("page", () => popups++);
  await tapOrClick(page, link, isMobile); // ONE tap
  await expect(page).toHaveURL(new RegExp(`/player/[^?]+\\?league=${DYNASTY}&team=12$`), { timeout: 3000 });
  await expect(page.getByTestId("player-name")).toHaveText(name);
  expect(popups, "a new tab opened").toBe(0);
  expect(context.pages()).toHaveLength(1);
  expect(await page.evaluate(() => history.length)).toBe(historyBefore + 1);
  await expect(page.getByTestId("section-projection")).toBeVisible();
  await noSidewaysScroll(page);
  // the in-app Back
  await expect(page.getByTestId("back")).toHaveText(/Back/);
  await tapOrClick(page, page.getByTestId("back"), isMobile);
  await expect(page).toHaveURL(new RegExp(`/\\?league=${DYNASTY}&team=12$`));
  await expect(page.getByTestId("decision-card").first()).toBeVisible();
  // the browser's Back and Forward
  await page.goForward();
  await expect(page.getByTestId("player-name")).toHaveText(name);
  await page.goBack();
  await expect(page.getByTestId("team-name")).toHaveText("Shake & Bake");
  // a name in the lineup table: one tap too
  await tapOrClick(page, page.getByTestId("lineup").locator("a").first(), isMobile);
  await expect(page).toHaveURL(/\/player\//);
  await expect(page.getByTestId("player-name")).toBeVisible();
  expect(popups).toBe(0);
  await page.screenshot({ path: join(SHOTS, `web_tap_${info.project.name}.png`) });
});

test("Back restores the scroll position of My Week", async ({ page, isMobile }) => {
  await page.goto(`/?league=${SCRUBS}&team=2`);
  await expect(page.getByTestId("lineup")).toBeVisible();
  const link = page.getByTestId("lineup").locator("a").last();
  await link.scrollIntoViewIfNeeded();
  const y = await page.evaluate(() => window.scrollY);
  await tapOrClick(page, link, isMobile);
  await expect(page.getByTestId("player-name")).toBeVisible();
  await page.goBack();
  await expect(page.getByTestId("lineup")).toBeVisible();
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(y);
});

const PLAYERS: [string, number, string, string][] = [
  [DYNASTY, 12, "00-0036963", "stbrown"], // rostered WR
  [SCRUBS, 2, "00-0035358", "mclaughlin"], // a kicker
  [SCRUBS, 2, "00-0038824", "fa"], // a free agent
];
for (const [league, team, gsis, tag] of PLAYERS) {
  test(`Player card ${tag}: five sections as cards, projection first, no sideways scroll`, async ({ page }, info) => {
    await page.goto(`/player/${gsis}?league=${league}&team=${team}`);
    await expect(page.getByTestId("player-name")).toBeVisible();
    for (const s of ["projection", "value", "availability", "usage", "signals"]) await expect(page.getByTestId(`section-${s}`)).toBeVisible();
    const proj = (await page.getByTestId("section-projection").boundingBox())!;
    expect(proj.y, "the projection starts below the first screen").toBeLessThan(page.viewportSize()!.height / 2);
    await noSidewaysScroll(page);
    // opened straight from a link (nothing behind it in the app): Back says "My week" and goes there, same league / team
    await expect(page.getByTestId("back")).toHaveText(/My week/);
    await page.screenshot({ path: join(SHOTS, `web_player_${tag}_${info.project.name}_fold.png`) });
    await page.screenshot({ path: join(SHOTS, `web_player_${tag}_${info.project.name}_full.png`), fullPage: true });
    await page.getByTestId("back").click();
    await expect(page).toHaveURL(new RegExp(`/\\?league=${league}&team=${team}$`));
  });
}

test("the league and team pick is remembered on this phone; picking does not add Back steps", async ({ page }) => {
  await page.goto(`/?league=${DYNASTY}&team=12`);
  await expect(page.getByTestId("team-name")).toHaveText("Shake & Bake");
  const h0 = await page.evaluate(() => history.length);
  await page.getByTestId("pick-league").selectOption(SCRUBS);
  await expect(page.getByTestId("pick-prompt")).toBeVisible(); // no team remembered for Scrubs yet in this browser
  await page.getByTestId("pick-team").selectOption("2");
  await expect(page.getByTestId("decision-card").first()).toBeVisible();
  await expect(page).toHaveURL(new RegExp(`\\?league=${SCRUBS}&team=2$`));
  expect(await page.evaluate(() => history.length)).toBe(h0);
  const scrubsTeam = await page.getByTestId("team-name").textContent();
  await page.goto("/"); // a bare visit (the home-screen icon's start URL)
  await expect(page.getByTestId("team-name")).toHaveText(scrubsTeam!);
  await expect(page).toHaveURL(new RegExp(`\\?league=${SCRUBS}&team=2$`));
  await page.getByTestId("pick-league").selectOption(DYNASTY); // back to the dynasty: its team is remembered too
  await expect(page.getByTestId("team-name")).toHaveText("Shake & Bake");
});

test("search on the player card", async ({ page, isMobile }) => {
  await page.goto(`/player/00-0035358?league=${DYNASTY}&team=12`);
  await expect(page.getByTestId("player-name")).toBeVisible();
  // IB-1: the search field is the top bar's (a magnifier under 1280 px); a hit opens the research pane
  if (!(await page.getByTestId("search").isVisible())) await tapOrClick(page, page.getByTestId("search-open"), isMobile);
  await page.getByTestId("search").fill("st brown");
  const hit = page.getByTestId("search-results").locator("a").first();
  await expect(hit).toContainText("Amon-Ra St. Brown");
  await tapOrClick(page, hit, isMobile);
  await tapOrClick(page, page.getByTestId("pane-full"), isMobile);
  await expect(page.getByTestId("player-name")).toHaveText("Amon-Ra St. Brown");
  await expect(page).toHaveURL(new RegExp(`/player/00-0036963\\?league=${DYNASTY}&team=12$`));
});

test("dark mode follows the system", async ({ browser }, info) => {
  const ctx = await browser.newContext({ ...info.project.use, colorScheme: "dark" });
  const page = await ctx.newPage();
  await page.goto(`${info.project.use.baseURL}/?league=${DYNASTY}&team=12`);
  await expect(page.getByTestId("decision-card").first()).toBeVisible();
  const bg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  expect(bg).not.toBe("rgb(255, 255, 255)");
  await page.screenshot({ path: join(SHOTS, `web_week_dark_${info.project.name}.png`) });
  await ctx.close();
});

test("installable: manifest, icons, service worker", async ({ page }) => {
  await page.goto(`/?league=${DYNASTY}&team=12`);
  await expect(page.getByTestId("decision-card").first()).toBeVisible();
  const manifest = await (await page.request.get("/manifest.webmanifest")).json();
  expect(manifest.display).toBe("standalone");
  expect(manifest.icons.map((i: { sizes: string }) => i.sizes)).toEqual(expect.arrayContaining(["192x192", "512x512"]));
  await expect.poll(() => page.evaluate(async () => !!(await navigator.serviceWorker.getRegistration())), { timeout: 10_000 }).toBe(true);
});

test("the password gate (E2E_GATED_URL: an API started with LEAGUE_LAB_APP_PASSWORD=E2E_GATED_PASSWORD)", async ({ browser }, info) => {
  const url = process.env.E2E_GATED_URL;
  test.skip(!url, "set E2E_GATED_URL and E2E_GATED_PASSWORD to run");
  const ctx = await browser.newContext({ ...info.project.use, baseURL: url });
  const page = await ctx.newPage();
  await page.goto(`/?league=${DYNASTY}&team=12`);
  await expect(page.getByTestId("login")).toBeVisible();
  expect((await page.request.get("/api/leagues")).status()).toBe(401);
  await page.getByPlaceholder("Password").fill("not it");
  await page.getByRole("button", { name: "Open League Lab" }).click();
  await expect(page.getByText("That is not it.")).toBeVisible();
  await page.getByPlaceholder("Password").fill(process.env.E2E_GATED_PASSWORD ?? "");
  await page.getByRole("button", { name: "Open League Lab" }).click();
  await expect(page.getByTestId("decision-card").first()).toBeVisible();
  // a name tap keeps the session (same tab, same cookie): no second password prompt
  await page.getByTestId("decision-card").first().locator("a").first().click();
  await expect(page.getByTestId("player-name")).toBeVisible();
  // and a new tab, or the home-screen icon tomorrow, is still signed in (the cookie lasts 180 days)
  const tab = await ctx.newPage();
  await tab.goto(`/?league=${DYNASTY}&team=12`);
  await expect(tab.getByTestId("decision-card").first()).toBeVisible();
  await ctx.close();
});
