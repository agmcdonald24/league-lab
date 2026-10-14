// Wave J-B (JB-4): the card explains "points over expected" in one sentence — on the Usage tab of the drawer (by the
// role lines) and on the full page — season to date in the league's scoring. Phone at 375, desktop at 1300.
//
// Two modes. Default: the fixture API (serveFixtures) with the card's answer for Justin Jefferson in League of Scrubs
// carrying a sentence of the API's shape; a card without it shows nothing (never a 0). JB4_LIVE=http://localhost:<port>
// (the API on a database, serving web/dist, the provider fixtures set and news off): Michael Wilson (44 targets,
// 63.8 expected, 44.3 actual in League of Scrubs scoring), drawer and full page, with screenshots (JPEG, rule 12) into
// docs/handbacks/jb4/ (SHOTS_JB4) when set, else e2e/.out.
import { expect, test, type BrowserContext, type Locator, type Page, type TestInfo } from "@playwright/test";
import { mkdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { FIXTURES, SCRUBS, serveFixtures } from "../fixtures";

const LIVE = process.env.JB4_LIVE ?? "";
const SHOTS = process.env.SHOTS_JB4 ?? join(import.meta.dirname, "..", ".out");
mkdirSync(SHOTS, { recursive: true });
if (LIVE) test.use({ baseURL: LIVE });

const JJ = "00-0036322"; // Justin Jefferson (a fixture card)
const WILSON = "00-0038559"; // Michael Wilson (live)
const LINE = {
  kind: "receiver",
  words: "His 31 targets usually bring about 40 points; he has 38. Depth of target is already allowed for.",
  targets: 31,
  carries: 0,
  expected: 40.2,
  actual: 38.4,
  games: 3,
};

async function cardWith(context: BrowserContext, extra: Record<string, unknown>) {
  await serveFixtures(context);
  const card = JSON.parse(readFileSync(join(FIXTURES, "player", `${SCRUBS}_${JJ}.json`), "utf8")) as Record<string, unknown>;
  // registered after serveFixtures: this answer wins for his card (Playwright runs the last matching route first)
  await context.route(new RegExp(`/api/player/${JJ}\\?`), (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ...card, ...extra }) }),
  );
}

async function narrow(page: Page, info: TestInfo) {
  if (info.project.name === "phone") await page.setViewportSize({ width: 375, height: 812 });
}

async function tap(loc: Locator, isMobile: boolean) {
  if (isMobile) await loc.tap();
  else await loc.click();
}

async function noSidewaysScroll(page: Page) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(sw, "page wider than the screen").toBeLessThanOrEqual(iw);
}

async function shot(page: Page, name: string, info: TestInfo) {
  await page.screenshot({ path: join(SHOTS, `jb4_${name}_${info.project.name}.jpg`), type: "jpeg", quality: 70 });
}

test("the Usage tab says the sentence, by the role lines; the full page says it too", async ({ page, context, isMobile }, info) => {
  test.skip(!!LIVE, "the fixture answer");
  await cardWith(context, { expected_line: LINE });
  await narrow(page, info);
  await page.goto(`/players?league=${SCRUBS}&team=2&pane=${JJ}`);
  const pane = page.getByTestId("pane");
  await expect(pane.getByTestId("pane-card")).toBeVisible();
  await expect(pane.getByTestId("pane-expected-line")).toHaveCount(0); // not on the Overview
  await tap(pane.getByTestId("drawer-tab-usage"), isMobile);
  await expect(pane.getByTestId("pane-expected-line")).toHaveText(LINE.words);
  await noSidewaysScroll(page);
  await page.goto(`/player/${JJ}?league=${SCRUBS}&team=2`);
  await expect(page.getByTestId("player-expected-line")).toHaveText(LINE.words);
  await noSidewaysScroll(page);
});

test("no sentence in the answer (under 20 targets, a quarterback, no expected value): nothing drawn, never a 0", async ({ page, context, isMobile }, info) => {
  test.skip(!!LIVE, "the fixture answer");
  await cardWith(context, { expected_line: null });
  await narrow(page, info);
  await page.goto(`/players?league=${SCRUBS}&team=2&pane=${JJ}`);
  const pane = page.getByTestId("pane");
  await tap(pane.getByTestId("drawer-tab-usage"), isMobile);
  await expect(pane.getByTestId("drawer-usage")).toBeVisible();
  await expect(pane.getByTestId("pane-expected-line")).toHaveCount(0);
  await expect(pane.getByTestId("drawer-usage")).not.toContainText("usually bring about");
});

test("live: Michael Wilson — drawer Usage and full page", async ({ page, context, isMobile }, info) => {
  test.skip(!LIVE, "JB4_LIVE not set");
  test.setTimeout(120_000);
  await context.route(/^https?:\/\/(?!localhost)/, (route) => route.abort()); // headshots, GA: never fetched by a test
  await narrow(page, info);
  await page.goto(`/players?league=${SCRUBS}&team=2&pane=${WILSON}`);
  const pane = page.getByTestId("pane");
  await expect(pane.getByTestId("pane-card")).toBeVisible({ timeout: 60_000 });
  await tap(pane.getByTestId("drawer-tab-usage"), isMobile);
  const line = pane.getByTestId("pane-expected-line");
  await expect(line).toHaveText("His 44 targets usually bring about 64 points; he has 44. Depth of target is already allowed for.", { timeout: 60_000 });
  await line.scrollIntoViewIfNeeded();
  await noSidewaysScroll(page);
  await shot(page, "drawer_usage", info);
  await page.goto(`/player/${WILSON}?league=${SCRUBS}&team=2`);
  const full = page.getByTestId("player-expected-line");
  await expect(full).toBeVisible({ timeout: 60_000 });
  await full.scrollIntoViewIfNeeded();
  await noSidewaysScroll(page);
  await shot(page, "page", info);
});
