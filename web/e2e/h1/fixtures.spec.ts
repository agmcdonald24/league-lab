// Wave H (H1) on fixtures: the upside stash and buy low / sell high on Waivers, "What it leans on most" and the grades on
// About — phone 390 × 844 and desktop 1300 × 900 (the projects of playwright.fixtures.config.ts), the house leagues and
// the Test League (on demand). Every number checked is read from the fixture served (web/fixtures/*.json, saved from
// the API by web/fixtures/save_h1_fixtures.py). Named fixtures.spec.ts so `npm run e2e:fixtures` runs it.
import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { DYNASTY, FIXTURES, SCRUBS, serveFixtures, TEST_LEAGUE } from "../fixtures";
import { serveDecisions } from "../decisions-fixtures";

// eslint-disable-next-line @typescript-eslint/no-explicit-any -- fixture JSON, read as written
const fx = (name: string): any => JSON.parse(readFileSync(join(FIXTURES, name), "utf8"));
const plain = (s: string) => s.replace(/\*\*/g, "").replace(/\*/g, "");
const sg = (x: number) => (Math.abs(x) >= 0.05 ? `${x > 0 ? "+" : "−"}${Math.abs(x).toFixed(1)}` : "+0.0");

async function noSidewaysScroll(page: Page) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(sw).toBeLessThanOrEqual(iw);
}

test.beforeEach(async ({ context }) => {
  await serveFixtures(context);
  await serveDecisions(context);
});

test("waivers: the upside stash and buy low / sell high, with the screen's own words (Scrubs, dynasty)", async ({ page }) => {
  for (const [league, team] of [[SCRUBS, 2], [DYNASTY, 12]] as const) {
    const w = fx(`waivers_${league}_${team}_ALL.json`);
    await page.goto(`/waivers?league=${league}&team=${team}`);
    await expect(page.getByTestId("waiver-answer")).toBeVisible();
    const up = page.getByTestId("upside");
    await expect(up).toBeVisible();
    const st = w.upside.stashes;
    await expect(up.getByTestId("stash")).toHaveCount(Math.min(3, st.length));
    if (st.length) {
      await expect(up.getByTestId("stash-headline").first()).toContainText(plain(st[0].headline).slice(0, 40));
      await expect(up.getByTestId("stash-player").first()).toContainText(st[0].scenario_value.toFixed(1));
      await expect(up.getByTestId("stash-lines").first()).toContainText(plain(st[0].lines[0]).slice(0, 30));
    }
    // IA-2: buy low / sell high moved to the Trades screen (GET /api/trades/lists); Waivers points there
    await expect(page.getByTestId("buy-sell-moved")).toBeVisible();
    await expect(page.getByTestId("buy-sell")).toHaveCount(0);
    await page.goto(`/trades?league=${league}&team=${team}`);
    const tl = fx(`trades_lists_${league}_${team}.json`);
    await expect(page.getByTestId("buy-line")).toContainText(plain(tl.buy_line).slice(0, 50));
    await expect(page.getByTestId("sell-line")).toContainText(plain(tl.sell_line).slice(0, 50));
    const best = Object.values(tl.best_buy_by_position) as { player: { player_name: string }; fit_horizon: number }[];
    await expect(page.getByTestId("buy-best")).toHaveCount(best.length);
    if (best.length) await expect(page.getByTestId("buy-best").first()).toContainText(sg(best[0].fit_horizon));
    await page.getByTestId("buy-list").locator("summary, button").first().click();
    await expect(page.getByTestId("buy-row")).toHaveCount(tl.buy_low.length);
    await expect(page.getByTestId("buy-row").first()).toContainText(tl.buy_low[0].player.player_name);
    await noSidewaysScroll(page);
  }
  await page.getByTestId("howto").locator("summary, button").first().click();
  await expect(page.getByTestId("howto")).toContainText("Buy low"); // the Trades screen's (IA-2)
  await page.goto(`/waivers?league=${DYNASTY}&team=12`);
  await page.getByTestId("howto").locator("summary, button").first().click();
  await expect(page.getByTestId("howto")).toContainText("Upside stash");
});

test("waivers on demand (Test League): the NFL-wide stash, said so; the trade lists", async ({ page }) => {
  const w = fx(`waivers_${TEST_LEAGUE}_3_ALL.json`);
  await page.goto(`/waivers?league=${TEST_LEAGUE}&team=3`);
  await expect(page.getByTestId("upside")).toBeVisible();
  await expect(page.getByTestId("stash-why")).toContainText("not on request");
  await expect(page.getByTestId("stash")).toHaveCount(Math.min(3, w.upside.stashes.length));
  await expect(page.getByTestId("stash-headline").first()).toContainText(plain(w.upside.stashes[0].headline).slice(0, 40));
  await page.goto(`/trades?league=${TEST_LEAGUE}&team=3`); // IA-2: the trade lists are on Trades
  await expect(page.getByTestId("buy-line")).toContainText(plain(fx(`trades_lists_${TEST_LEAGUE}_3.json`).buy_line).slice(0, 50));
  await noSidewaysScroll(page);
});

test("about: what it leans on most (bars per position) and the grades (tiles), house and Test League", async ({ page }) => {
  const a = fx(`about_${DYNASTY}.json`);
  await page.goto(`/about?league=${DYNASTY}&team=12`);
  await expect(page.getByTestId("importance")).toBeVisible();
  const first = a.importance.positions[0];
  await expect(page.getByTestId("importance-lead")).toContainText(plain(first.lead).slice(0, 40));
  await expect(page.getByTestId("importance-bar")).toHaveCount(first.features.length);
  await expect(page.getByTestId("importance-bar").first()).toContainText(`+${first.features[0].importance.toFixed(2)}`);
  const rb = a.importance.positions.find((p: { position: string }) => p.position === "RB");
  await page.getByTestId("importance-pos").getByRole("button", { name: "RB" }).click();
  await expect(page.getByTestId("importance-lead")).toContainText(plain(rb.lead).slice(0, 40));
  await expect(page.getByTestId("importance-how")).toContainText("How we measured it");
  const g = a.grades.positions[0];
  await expect(page.getByTestId("grades-answer")).toContainText(a.grades.answer.slice(0, 40));
  await expect(page.getByTestId("grade-card")).toHaveCount(a.grades.positions.length);
  await expect(page.getByTestId("grade-order").first()).toContainText(g.season.spearman.toFixed(2));
  await expect(page.getByTestId("grade-order").first()).toContainText(g.backtest.spearman.toFixed(2));
  await expect(page.getByTestId("grade-miss").first()).toContainText(g.season.mae.toFixed(1));
  await noSidewaysScroll(page);

  const t = fx(`about_${TEST_LEAGUE}.json`);
  await page.goto(`/about?league=${TEST_LEAGUE}&team=3`);
  await expect(page.getByTestId("about-why")).toContainText(t.why.slice(0, 40));
  await expect(page.getByTestId("importance-bar").first()).toBeVisible();
  await expect(page.getByTestId("grade-card")).toHaveCount(t.grades.positions.length);
});
