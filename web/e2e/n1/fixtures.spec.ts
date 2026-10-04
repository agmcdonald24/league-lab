// Wave I-D (N1): the news line on the player card — "News · 2 h ago · <headline> · RotoWire via ESPN ›" under the
// availability lines, on the full page and in the research pane, at 375 px (inside the phone project) and on desktop.
// Justin Jefferson's Scrubs card (web/fixtures/player/) with `news` as the API sends it (api/league_lab_api/news.py:
// at most 3, newest first; the headlines are ESPN's, recorded 2026-10-03 in api/tests/fixtures/espn/news_4262921.json),
// dated relative to the test's clock so "2 h ago" holds on any day. A card without news shows no line.
import { expect, test, type BrowserContext, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { FIXTURES, SCRUBS, serveFixtures } from "../fixtures";

const JJ = "00-0036322";
const HOUR = 3_600_000;
const LONG =
  "Jefferson (ankle) has been already been ruled out for Sunday's game against the Dolphins, but the Vikings are hopeful that the superstar wide receiver will return for Week 5 against the Saints, Jeremy Fowler of ESPN reports.";

function newsFor(now: number) {
  return [
    { headline: LONG, date: new Date(now - 2 * HOUR - 5 * 60_000).toISOString(), source: "RotoWire via ESPN", url: "https://www.espn.com/nfl/player/_/id/4262921" },
    {
      headline: "Fantasy football Week 4 inactives: Daniels, DeVonta to sit; McConkey questionable",
      date: new Date(now - 14 * HOUR).toISOString(),
      source: "ESPN",
      url: "https://www.espn.com/fantasy/football/story/_/page/FFSundayInactives-50077553/fantasy-football-injuries-nfl-week-4-inactive-active",
    },
  ];
}

async function withNews(context: BrowserContext, news: unknown[]) {
  const card = JSON.parse(readFileSync(join(FIXTURES, "player", `${SCRUBS}_${JJ}.json`), "utf8")) as Record<string, unknown>;
  await context.route(new RegExp(`/api/player/${JJ}(\\?|$)`), (route) =>
    route.fulfill({ status: 200, contentType: "application/json", headers: { "Cache-Control": "no-store" }, body: JSON.stringify({ ...card, news }) }),
  );
}

async function noSidewaysScroll(page: Page) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(sw, "page wider than the screen").toBeLessThanOrEqual(iw);
}

test.beforeEach(async ({ context }) => {
  await serveFixtures(context);
});

test("the news line on his page: under the availability lines, the newest headline, linked out", async ({ page, context }, info) => {
  if (info.project.name === "phone") await page.setViewportSize({ width: 375, height: 812 });
  await withNews(context, newsFor(Date.now()));
  await page.goto(`/player/${JJ}?league=${SCRUBS}&team=2`);
  const avail = page.getByTestId("section-availability");
  await expect(avail).toContainText("No injury designation.");
  const line = avail.getByTestId("player-news");
  await expect(line).toBeVisible();
  await expect(line).toContainText(/News · 2 h ago · Jefferson \(ankle\) has been already been ruled out/);
  await expect(line).toContainText("RotoWire via ESPN ›");
  await expect(line).not.toContainText("Week 4 inactives"); // the newest only
  // a 220-character blurb is cut at a word; the whole headline is its title
  const head = line.getByTestId("player-news-headline");
  expect(((await head.textContent()) ?? "").length).toBeLessThanOrEqual(111);
  await expect(head).toHaveText(/…$/);
  await expect(head).toHaveAttribute("title", LONG);
  const link = line.getByTestId("player-news-link");
  await expect(link).toHaveAttribute("href", "https://www.espn.com/nfl/player/_/id/4262921");
  await expect(link).toHaveAttribute("target", "_blank");
  await expect(link).toHaveAttribute("rel", "noopener noreferrer");
  // under the availability lines: after the section's last line
  const lastBlock = await avail.locator("p").evaluateAll((ps) => ps.map((p) => p.getAttribute("data-testid")));
  expect(lastBlock.at(-1)).toBe("player-news");
  await noSidewaysScroll(page);
  const box = (await line.boundingBox())!;
  expect(box.x + box.width).toBeLessThanOrEqual((page.viewportSize()?.width ?? 0) + 0.5);
  await avail.screenshot({ path: join(process.env.SHOTS_DIR ?? join(import.meta.dirname, "..", ".out"), `n1_page_${info.project.name}.png`) });
});

test("the news line in the pane, at a phone's width", async ({ page, context }, info) => {
  if (info.project.name === "phone") await page.setViewportSize({ width: 375, height: 812 });
  await withNews(context, newsFor(Date.now()));
  await page.goto(`/?league=${SCRUBS}&team=2&pane=${JJ}&from=list`);
  const pane = page.getByTestId("pane");
  await expect(pane).toBeVisible();
  await expect(pane.getByTestId("pane-card")).toContainText("Jefferson");
  const line = pane.getByTestId("pane-section-availability").getByTestId("pane-news");
  await expect(line).toContainText(/News · 2 h ago · Jefferson \(ankle\)/);
  await expect(line.getByTestId("pane-news-link")).toHaveText("RotoWire via ESPN ›");
  await expect(line.getByTestId("pane-news-link")).toHaveAttribute("target", "_blank");
  await line.scrollIntoViewIfNeeded();
  await pane.getByTestId("pane-section-availability").screenshot({
    path: join(process.env.SHOTS_DIR ?? join(import.meta.dirname, "..", ".out"), `n1_pane_${info.project.name}.png`),
  });
  const pb = (await pane.boundingBox())!;
  const lb = (await line.boundingBox())!;
  expect(lb.x + lb.width).toBeLessThanOrEqual(pb.x + pb.width + 0.5);
  await noSidewaysScroll(page);
});

test("no news (none in 14 days, the feed off or out): no line", async ({ page, context }) => {
  await withNews(context, []);
  await page.goto(`/player/${JJ}?league=${SCRUBS}&team=2`);
  await expect(page.getByTestId("section-availability")).toContainText("No injury designation.");
  await expect(page.getByTestId("player-news")).toHaveCount(0);
});

test("ESPN's own story: named ESPN, linked to the story", async ({ page, context }) => {
  const now = Date.now();
  await withNews(context, [newsFor(now)[1]]);
  await page.goto(`/player/${JJ}?league=${SCRUBS}&team=2`);
  const line = page.getByTestId("player-news");
  await expect(line).toContainText("News · 14 h ago · Fantasy football Week 4 inactives: Daniels, DeVonta to sit; McConkey questionable · ESPN ›");
  await expect(line.getByTestId("player-news-link")).toHaveAttribute("href", /^https:\/\/www\.espn\.com\/fantasy\/football\/story\//);
});

test("About names where the news line comes from", async ({ page }) => {
  await page.goto(`/about?league=${SCRUBS}&team=2`);
  await expect(page.getByTestId("about-news-source")).toContainText("ESPN's public player news");
  await expect(page.getByTestId("about-news-source")).toContainText("isuckatfantasy keeps only the headline, its date, the source and the link."); // IG-2
});
