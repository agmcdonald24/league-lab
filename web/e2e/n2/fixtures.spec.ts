// N2: PlayerWire's briefs on the news line — "News · 2 h ago · <headline> · Minnesota Vikings via PlayerWire › OFFICIAL"
// with the brief's one-sentence news under it (muted, full width, cut at a word to 220 characters). Justin Jefferson's
// Scrubs card (web/fixtures/player/) with `news` as the API sends it (api/league_lab_api/news.py: PlayerWire first,
// ESPN fills the rest), dated relative to the test's clock. An ESPN item still renders exactly as in N1 (e2e/n1/).
import { expect, test, type BrowserContext, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { FIXTURES, SCRUBS, serveFixtures } from "../fixtures";

const JJ = "00-0036322";
const HOUR = 3_600_000;
const SUMMARY =
  "Justin Jefferson (ankle) has been ruled out for Sunday's game against the Dolphins after missing practice all week; the Vikings expect him back for Week 5 against the Saints, and Jordan Addison should lead the receivers in snaps while T.J. Hockenson sees more work.";

function brief(now: number, over: Record<string, unknown> = {}) {
  return {
    headline: "Jefferson (ankle) ruled out for Sunday",
    date: new Date(now - 2 * HOUR - 5 * 60_000).toISOString(),
    source: "Minnesota Vikings via PlayerWire",
    url: "https://www.vikings.com/news/injury-report-week-5",
    summary: SUMMARY,
    kind: "playerwire",
    verification: "official",
    related: false,
    ...over,
  };
}

const ESPN_ITEM = (now: number) => ({
  headline: "Fantasy football Week 4 inactives: Daniels, DeVonta to sit; McConkey questionable",
  date: new Date(now - 14 * HOUR).toISOString(),
  source: "ESPN",
  url: "https://www.espn.com/fantasy/football/story/_/page/FFSundayInactives-50077553/fantasy-football-injuries-nfl-week-4-inactive-active",
  kind: "espn",
});

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

const shots = (name: string) => join(process.env.SHOTS_DIR ?? join(import.meta.dirname, "..", ".out"), name);

test.beforeEach(async ({ context }) => {
  await serveFixtures(context);
});

test("a PlayerWire brief on his page: headline, source, tag, then its news under it", async ({ page, context }, info) => {
  if (info.project.name === "phone") await page.setViewportSize({ width: 375, height: 812 });
  const now = Date.now();
  await withNews(context, [brief(now), ESPN_ITEM(now)]);
  await page.goto(`/player/${JJ}?league=${SCRUBS}&team=2`);
  const avail = page.getByTestId("section-availability");
  const line = avail.getByTestId("player-news");
  await expect(line).toBeVisible();
  await expect(line).toContainText(/News · 2 h ago · Jefferson \(ankle\) ruled out for Sunday · Minnesota Vikings via PlayerWire ›/);
  await expect(line).not.toContainText("Week 4 inactives"); // the first item only
  const tag = line.getByTestId("player-news-verification");
  await expect(tag).toHaveText("official");
  await expect(tag).toHaveClass(/bg-accent-soft/);
  const link = line.getByTestId("player-news-link");
  await expect(link).toHaveAttribute("href", "https://www.vikings.com/news/injury-report-week-5");
  await expect(link).toHaveAttribute("target", "_blank");
  await expect(link).toHaveAttribute("rel", "noopener noreferrer");
  // the summary: under the headline, the line's full width, cut at a word to 220 characters, the whole text in its title
  const summary = line.getByTestId("player-news-summary");
  await expect(summary).toBeVisible();
  const text = (await summary.textContent()) ?? "";
  expect(text.length).toBeLessThanOrEqual(221);
  expect(text.endsWith("…")).toBe(true);
  expect(SUMMARY.startsWith(text.slice(0, -1))).toBe(true);
  await expect(summary).toHaveAttribute("title", SUMMARY);
  const lb = (await line.boundingBox())!;
  const sb = (await summary.boundingBox())!;
  const hb = (await line.getByTestId("player-news-headline").boundingBox())!;
  expect(sb.y).toBeGreaterThan(hb.y); // below the headline
  expect(sb.width).toBeGreaterThan(lb.width * 0.9); // full width
  // still the last line of the availability section
  const lastBlock = await avail.locator("p").evaluateAll((ps) => ps.map((p) => p.getAttribute("data-testid")));
  expect(lastBlock.at(-1)).toBe("player-news");
  await noSidewaysScroll(page);
  expect(lb.x + lb.width).toBeLessThanOrEqual((page.viewportSize()?.width ?? 0) + 0.5);
  await avail.screenshot({ path: shots(`n2_page_${info.project.name}.png`) });
});

test("a PlayerWire brief in the pane, at a phone's width", async ({ page, context }, info) => {
  if (info.project.name === "phone") await page.setViewportSize({ width: 375, height: 812 });
  await withNews(context, [brief(Date.now(), { verification: "reported" })]);
  await page.goto(`/?league=${SCRUBS}&team=2&pane=${JJ}&from=list`);
  const pane = page.getByTestId("pane");
  await expect(pane.getByTestId("pane-card")).toContainText("Jefferson");
  const line = pane.getByTestId("pane-section-availability").getByTestId("pane-news");
  await expect(line).toContainText("Minnesota Vikings via PlayerWire ›");
  await expect(line.getByTestId("pane-news-verification")).toHaveText("reported");
  await expect(line.getByTestId("pane-news-summary")).toContainText("Justin Jefferson (ankle) has been ruled out");
  await line.scrollIntoViewIfNeeded();
  await pane.getByTestId("pane-section-availability").screenshot({ path: shots(`n2_pane_${info.project.name}.png`) });
  const pb = (await pane.boundingBox())!;
  const b = (await line.boundingBox())!;
  expect(b.x + b.width).toBeLessThanOrEqual(pb.x + pb.width + 0.5);
  await noSidewaysScroll(page);
});

test("a disputed brief wears the warning tag; a short summary is shown whole", async ({ page, context }) => {
  await withNews(context, [brief(Date.now(), { verification: "disputed", summary: "Two reports disagree on his status." })]);
  await page.goto(`/player/${JJ}?league=${SCRUBS}&team=2`);
  const line = page.getByTestId("player-news");
  await expect(line.getByTestId("player-news-verification")).toHaveText("disputed");
  await expect(line.getByTestId("player-news-verification")).toHaveClass(/bg-warn-soft/);
  await expect(line.getByTestId("player-news-summary")).toHaveText("Two reports disagree on his status.");
});

test("an ESPN item first: N1's line exactly, no summary, no tag", async ({ page, context }) => {
  await withNews(context, [ESPN_ITEM(Date.now())]);
  await page.goto(`/player/${JJ}?league=${SCRUBS}&team=2`);
  const line = page.getByTestId("player-news");
  await expect(line).toHaveText("News · 14 h ago · Fantasy football Week 4 inactives: Daniels, DeVonta to sit; McConkey questionable · ESPN ›· context only, not in the projection"); // integ: II-4's forecast words on every card news line
  await expect(line.getByTestId("player-news-summary")).toHaveCount(0);
  await expect(line.getByTestId("player-news-verification")).toHaveCount(0);
});

test("About says where the briefs come from", async ({ page }) => {
  await page.goto(`/about?league=${SCRUBS}&team=2`);
  await expect(page.getByTestId("about-news-playerwire")).toContainText("PlayerWire brief first");
  await expect(page.getByTestId("about-news-source")).toContainText("isuckatfantasy keeps only the headline, its date, the source and the link."); // IG-2
});
