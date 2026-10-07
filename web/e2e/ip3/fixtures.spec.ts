// Wave I-P (IP-3): Trends, graded. "Below / above expectation" was graded against the projection made before each next
// game (docs/METRICS.md § "Trends and the role trend, graded"): the gap closes in part the next week, and the
// projection already expects that — so the screen stops implying "buy low / sell high". With the record, Trends' head
// carries the record's line under its title and "How to read this" its full sentence; the picked player's line says
// "what happened, and his projection already counts it" with or without the record. The Trends answer is the dynasty
// league's recording (web/fixtures/trends_<id>.json) with `record` set the way the API sets it (`summary()["trend"]`,
// recorded from the fixture API on :8963 against league_lab_im4: web/fixtures/ip3/context_record.json, trimmed to what
// the screen reads). Phone at 375 and desktop at 1300; JPEG screenshots into docs/handbacks/ip3/.
import { expect, test, type BrowserContext, type Page, type Route } from "@playwright/test";
import { mkdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { DYNASTY, serveFixtures } from "../fixtures";

const FIX = join(import.meta.dirname, "..", "..", "fixtures");
const SHOTS = process.env.SHOTS_IP3 ?? join(import.meta.dirname, "..", "..", "..", "docs", "handbacks", "ip3");
mkdirSync(SHOTS, { recursive: true });
const RECORD = JSON.parse(readFileSync(join(FIX, "ip3", "context_record.json"), "utf8"));
const TRENDS = readFileSync(join(FIX, `trends_${DYNASTY}.json`), "utf8");
const PROMISE = /\b(due for|running hot|buy low|buy him|sell high|bounce back)\b/i;

async function trendsApi(context: BrowserContext, record: unknown | undefined) {
  await context.route(/\/api\/trends(\?|$)/, async (route: Route) => {
    const body = JSON.parse(TRENDS);
    if (record !== undefined) body.record = record;
    await route.fulfill({ status: 200, contentType: "application/json", headers: { "Cache-Control": "no-store" }, body: JSON.stringify(body) });
  });
}

async function noSideways(page: Page) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(sw, "page wider than the screen").toBeLessThanOrEqual(iw);
}

async function size(page: Page, name: string) {
  if (name === "phone") await page.setViewportSize({ width: 375, height: 812 });
}

test("Trends with the record: the grade under the title, words that send you to the projection", async ({ page, context }, info) => {
  expect(RECORD.trend.graded).toBe(true);
  expect(RECORD.trend.head).toMatch(/^Graded on 2025 and 2026 weeks 1–4 \(Half PPR\): in their next game, players below expectation scored/);
  await serveFixtures(context);
  await trendsApi(context, RECORD.trend);
  await size(page, info.project.name);
  await page.goto(`/trends?league=${DYNASTY}&team=12`);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Below and above expectation");
  await expect(page.getByTestId("trends-record")).toHaveText(RECORD.trend.head);
  await expect(page.getByTestId("answer")).toContainText("Below expectation:");
  await expect(page.getByTestId("trends-list").locator("li").first()).toBeVisible();
  if (info.project.name === "desktop") {
    // the picked player's line: what happened, already in his projection (never "an observed gap" or "due")
    await expect(page.getByTestId("trends-detail")).toContainText("his projection already counts it");
  }
  await noSideways(page);
  await page.screenshot({ path: join(SHOTS, `ip3-trends-${info.project.name}.jpg`), type: "jpeg", quality: 70, scale: "css", fullPage: false });
  // How to read this: the graded sentence and no promise
  await page.getByTestId("howto").locator("summary").click();
  const howto = page.getByTestId("howto");
  await expect(howto).toContainText("Graded on past weeks, players like him scored more the next week");
  await expect(howto).toContainText("not a reason to buy on its own");
  await expect(howto).toContainText(`Graded: ${RECORD.trend.words.replace(/\.$/, "")}`);
  expect((await page.getByTestId("trends").innerText()).match(PROMISE)).toBeNull();
  if (info.project.name === "phone") {
    await howto.scrollIntoViewIfNeeded();
    await page.screenshot({ path: join(SHOTS, `ip3-trends-howto-phone.jpg`), type: "jpeg", quality: 70, scale: "css", fullPage: false });
  }
});

test("Trends without the record: no grade line, the same honest words", async ({ page, context }, info) => {
  await serveFixtures(context);
  await trendsApi(context, { graded: false, n: 0, words: null, head: null, tags: {} });
  await size(page, info.project.name);
  await page.goto(`/trends?league=${DYNASTY}&team=12`);
  await expect(page.getByTestId("trends-list").locator("li").first()).toBeVisible();
  await expect(page.getByTestId("trends-record")).toHaveCount(0);
  if (info.project.name === "desktop") await expect(page.getByTestId("trends-detail")).toContainText("his projection already counts it");
  await page.getByTestId("howto").locator("summary").click();
  await expect(page.getByTestId("howto")).toContainText("about as much as their projection already expected");
  await expect(page.getByTestId("howto")).not.toContainText("Graded:");
  expect((await page.getByTestId("trends").innerText()).match(PROMISE)).toBeNull();
  await noSideways(page);
});

test("Trends from an API without the record key (an older deploy): the screen stands", async ({ page, context }, info) => {
  await serveFixtures(context);
  await trendsApi(context, undefined);
  await size(page, info.project.name);
  await page.goto(`/trends?league=${DYNASTY}&team=12`);
  await expect(page.getByTestId("trends-list").locator("li").first()).toBeVisible();
  await expect(page.getByTestId("trends-record")).toHaveCount(0);
  await noSideways(page);
});
