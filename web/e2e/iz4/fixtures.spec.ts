// Wave I-Z (IZ-4): news on the decision it affects (the review's Pass 2: "surface sourced injury / personnel changes
// beside the affected decision"). Phone at 375 (no sideways page scroll) and desktop at 1300.
//
// The answers: League of Scrubs team 2's saved My Week answer of web/fixtures/ig2/api_ig2.json (Jefferson ruled out,
// the call "Start Wilson at FLEX … in place of Jefferson", two Jefferson lines and a Ferguson line in the News feed) —
// "before" as it was saved; "after" = the same answer put through the API's own `decision_news.attach`
// (web/fixtures/iz4/my-week_scrubs_2.json; the recipe in docs/handbacks/IZ-4.md). No news is invented: the lines are
// the saved feed's, moved.
import { expect, test, type Page, type Route } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { serveDecisions } from "../decisions-fixtures";
import { SCRUBS, serveFixtures } from "../fixtures";

const FX = join(import.meta.dirname, "..", "..", "fixtures");
const SHOTS = process.env.SHOTS_IZ4 ?? join(import.meta.dirname, "..", ".out");
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const AFTER: any = JSON.parse(readFileSync(join(FX, "iz4", "my-week_scrubs_2.json"), "utf8"));
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const BEFORE: any = JSON.parse(readFileSync(join(FX, "ig2", "api_ig2.json"), "utf8"))[`/api/my-week?league=${SCRUBS}&team=2`].body;

async function serveWeek(page: Page, body: unknown) {
  await page.route(/\/api\/my-week\?/, (route: Route) =>
    route.fulfill({ status: 200, contentType: "application/json", headers: { "Cache-Control": "no-store" }, body: JSON.stringify(body) }),
  );
}

test.beforeEach(async ({ context, page }, info) => {
  await serveFixtures(context);
  await serveDecisions(context);
  if (info.project.name === "phone") await page.setViewportSize({ width: 375, height: 812 });
});

async function noSidewaysScroll(page: Page) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(sw, "page wider than the screen").toBeLessThanOrEqual(iw);
}

const shot = (page: Page, name: string, project: string) =>
  page.screenshot({ path: join(SHOTS, `iz4-${name}-${project === "phone" ? "375" : "1300"}.jpg`), type: "jpeg", quality: 70, fullPage: true });

test("before (the saved answer): Jefferson's news sits in the feed, apart from the call that names him", async ({ page }, info) => {
  await serveWeek(page, BEFORE);
  await page.goto(`/?league=${SCRUBS}&team=2`);
  const feed = page.getByTestId("what-changed");
  await expect(feed).toBeVisible();
  await expect(feed).toContainText("Jefferson (ankle) ruled out for Sunday");
  await expect(page.getByTestId("decision-news")).toHaveCount(0);
  await shot(page, "scrubs2-before", info.project.name);
});

test("after: the two Jefferson lines sit on the call about him, the feed keeps the rest", async ({ page }, info) => {
  await serveWeek(page, AFTER);
  await page.goto(`/?league=${SCRUBS}&team=2`);
  const a = AFTER.actions.find((x: { news?: unknown[] }) => (x.news ?? []).length);
  expect(a, "the saved answer's call about Jefferson carries his news").toBeTruthy();
  const card = page.getByTestId("action-card").filter({ hasText: "in place of Jefferson" });
  await expect(card).toHaveCount(1);
  const lines = card.getByTestId("decision-news").getByTestId("decision-news-line");
  await expect(lines).toHaveCount(a.news.length);
  for (const [i, n] of a.news.entries()) {
    await expect(lines.nth(i)).toContainText(n.text);
    if (n.source) await expect(lines.nth(i)).toContainText(n.source);
    if (n.forecast_words) await expect(lines.nth(i).getByTestId("decision-news-forecast")).toHaveText(n.forecast_words);
    await expect(lines.nth(i).locator("time")).toHaveCount(n.at ? 1 : 0);
  }
  // the newest first
  const ats = a.news.map((n: { at: string | null }) => n.at ?? "");
  expect([...ats].sort().reverse()).toEqual(ats);
  // the feed: only what touches no decision; nothing about Jefferson
  const feed = page.getByTestId("what-changed");
  await expect(feed.getByTestId("changed-line")).toHaveCount(AFTER.changed.lines.length);
  await expect(feed).not.toContainText("Jefferson");
  await noSidewaysScroll(page);
  await shot(page, "scrubs2-after", info.project.name);
});

test("nothing is read from the news: the calls, their order and every number are the saved answer's", async ({ page }) => {
  const words = (d: { actions: { action: string; reason: string; gain: number | null }[] }) => d.actions.map((x) => [x.action, x.reason, x.gain]);
  expect(words(AFTER)).toEqual(words(BEFORE));
  expect(AFTER.lineup).toEqual(BEFORE.lineup);
  expect(AFTER.cards).toEqual(BEFORE.cards);
  await serveWeek(page, AFTER);
  await page.goto(`/?league=${SCRUBS}&team=2`);
  await expect(page.getByTestId("action-text").first()).toHaveText(BEFORE.actions[0].action.replace(/\[([^\]]+)\]\([^)]+\)/g, "$1"));
});

test("every line on decisions: no feed is drawn", async ({ page }) => {
  const all = structuredClone(AFTER);
  all.changed.lines = [];
  await serveWeek(page, all);
  await page.goto(`/?league=${SCRUBS}&team=2`);
  await expect(page.getByTestId("action-card").first()).toBeVisible();
  await expect(page.getByTestId("what-changed")).toHaveCount(0);
  await expect(page.getByTestId("decision-news")).toHaveCount(1);
});
