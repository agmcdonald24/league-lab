// Wave J-B (JB-1): About's "What changed and when" ends at v3.8 (fx1.0: the model knows when a back, receiver or tight
// end missed his team's last game). Two modes, as e2e/in3: default — /api/about for ref:half comes from
// web/fixtures/jb1/api_jb1.json (recorded from the fixture API), the rest from serveFixtures; JB1_LIVE=http://localhost:8930
// (the fixture API serving web/dist): the same walk against the real server, recording that answer.
// Phone at 375 and desktop at 1300; screenshots into docs/handbacks/jb1/ (SHOTS_JB1) or e2e/.out.
import { expect, test, type BrowserContext, type Page } from "@playwright/test";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { serveFixtures } from "../fixtures";

const LIVE = process.env.JB1_LIVE ?? "";
const DIR = join(import.meta.dirname, "..", "..", "fixtures", "jb1");
const RECORDED = join(DIR, "api_jb1.json");
const SHOTS = process.env.SHOTS_JB1 ?? join(import.meta.dirname, "..", ".out");

if (LIVE) test.use({ baseURL: LIVE });

async function api(context: BrowserContext): Promise<void> {
  await context.route(/^https?:\/\/(?!localhost)/, (route) => route.abort());
  if (LIVE) {
    await context.route(/\/api\/about\?/, async (route) => {
      const res = await route.fetch();
      const body = await res.json();
      mkdirSync(DIR, { recursive: true });
      writeFileSync(RECORDED, JSON.stringify({ status: res.status(), body }, null, 1));
      await route.fulfill({ response: res, json: body });
    });
    return;
  }
  await serveFixtures(context);
  if (existsSync(RECORDED)) {
    const rec = JSON.parse(readFileSync(RECORDED, "utf8")) as { status: number; body: unknown };
    await context.route(/\/api\/about\?/, (route) => route.fulfill({ status: rec.status, json: rec.body }));
  }
}

async function noSidewaysScroll(page: Page) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  expect(sw).toBeLessThanOrEqual(iw);
}

test("About: the model's versions end at v3.8 and say what it changed", async ({ page, context }, info) => {
  test.skip(!LIVE && !existsSync(RECORDED), "no recorded answer: run once with JB1_LIVE");
  await api(context);
  await page.setViewportSize(info.project.name === "phone" ? { width: 375, height: 812 } : { width: 1300, height: 900 });
  await page.goto("/about?league=ref:half");
  const list = page.getByTestId("about-versions-list");
  await expect(list).toContainText("v3.8");
  await expect(list).toContainText("missed his team's last game");
  await noSidewaysScroll(page);
  mkdirSync(SHOTS, { recursive: true });
  const last = list.locator("li").last();
  await expect(last).toContainText("v3.8");
  await last.evaluate((el) => el.scrollIntoView({ block: "center" }));
  await page.screenshot({ path: join(SHOTS, `jb1-about-versions-${info.project.name}.png`) });
});
